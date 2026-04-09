import datetime
import json
import math
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from astral import Observer
from astral.sun import azimuth, elevation

from kivy.app import App
from kivy.clock import Clock
from kivy.event import EventDispatcher
from kivy.properties import BooleanProperty

try:
    from timezonefinder import TimezoneFinder
except ImportError:
    TimezoneFinder = None

from .utils import (
    clone_shape, replace_shape, remove_shape, insert_shape,
    GEOM_EPSILON,
    minutes_from_time_str, time_str_from_minutes,
    point_in_polygon, strip_length, strip_polygon_from_centerline,
    validate_polygon_points,
)
from .constants import (
    CATEGORIES,
    DEFAULT_STRIP_WIDTH_FT,
    MAP_OVERLAY_CALIBRATION_IDLE,
    MAP_OVERLAY_CALIBRATION_TWO_POINT,
    MIN_STRIP_LENGTH_FT,
    MIN_STRIP_WIDTH_FT,
)
from .model import GardenModel
from .growth import ensure_growth_payload, update_growth
from .map_projection import calibrate_garden_overlay, garden_ft_to_latlon
from .simulation.constants import (
    DEFAULT_CATCHUP_CHUNK_TICKS,
    DEFAULT_ENGINE_SYNC_INTERVAL_TICKS,
    DEFAULT_HOSE_CAPACITY,
    DEFAULT_HOSE_FLOW_RATE,
    DEFAULT_HOSE_INITIAL_WATER,
    DEFAULT_PLANT_GROWTH_RATE,
    DEFAULT_PLANT_HEALTH,
    DEFAULT_PLANT_MAX_HEALTH,
    DEFAULT_PLANT_VITALITY,
    DEFAULT_PLANT_WATER_CONSUMPTION,
    DEFAULT_SPIGOT_FLOW_RATE,
)
from .simulation.entities.base import GridEntity
from .simulation.entities.hose import HoseEntity
from .simulation.entities.plant import PlantEntity
from .simulation.entities.spigot import SpigotEntity
from .simulation.engine import SimulationEngine
from .simulation.world import SimulationWorld
from .commands import (
    AddShapeCommand, DeleteShapeCommand, MoveShapeCommand,
    ModifyPropertyCommand, CommandHistory,
)
from .storage import StorageManager


class GardenController(EventDispatcher):
    """Handles business logic, user input translation, and model mutation."""
    can_undo = BooleanProperty(False)
    can_redo = BooleanProperty(False)
    GRID_STAMP_MODES = {
        "irrigation_hose": "Irrigation Hose",
        "carrot_seed": "Carrot Seed",
    }
    SEASON_LENGTH_DAYS = {
        "cool": 65,
        "mild": 95,
        "warm": 115,
        "hot": 120,
    }
    SEASON_SAMPLE_HOURS = (8, 10, 12, 14, 16, 18)
    SUNLIGHT_GRID_COLS = 16
    SUNLIGHT_GRID_ROWS = 16
    GEOCODER_URL = "https://nominatim.openstreetmap.org/search"
    GEOCODER_USER_AGENT = "GardenSimulator/1.0 (+desktop garden planner)"

    __events__ = ('on_alert',)

    def __init__(self, model: GardenModel, simulation_repositories=None, **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.command_history = CommandHistory(self)
        self._move_command_before = None
        self._sunlight_token = 0
        self._active_grid_stamp_cells = set()
        self._last_grid_stamp_cell = None
        self._grid_stamp_touch_active = False
        self._grid_stamp_plant = None
        self.sim_world = SimulationWorld()
        self.sim_engine = SimulationEngine(
            self.sim_world,
            repositories=tuple(simulation_repositories or ()),
        )
        # Dict-based spatial index: (col, row) -> GridEntity
        self._grid_index: dict = self.sim_world.garden_grid
        # Active-component sets: only items that need per-tick processing
        self._active_hose_cells: set = self.sim_world.active_hoses
        self._active_plant_cells: set = self.sim_world.active_plants
        self._active_spigot_cells: set = self.sim_world.active_spigots
        self._geocode_cache = {}
        self._timezone_lookup_cache = {}
        self._timezone_finder = None
        self._refresh_shape_grid_cells()
        self._sync_history_state()

    def on_alert(self, title, message):
        """Event dispatcher for UI alerts. Bound by the layout."""
        pass

    def _resolve_storage_manager(self):
        """Return the app storage manager, or a default local manager."""
        app = App.get_running_app()
        if app is not None and hasattr(app, "storage_manager"):
            return app.storage_manager
        return StorageManager()

    def build_sync_payload(self):
        """Prepare a plain dictionary payload for server synchronization."""
        return self.model.to_dict()

    def start_plant_placement(self, plant):
        """Enter plant placement mode using root-zone metadata from catalog."""
        if not isinstance(plant, dict):
            self.dispatch("on_alert", "Plant Catalog", "Invalid plant selection.")
            return False

        self.cancel_drawing()
        self.deselect()
        plant_payload = ensure_growth_payload(plant)
        plant_payload["root_radius_ft"] = float(plant_payload.get("root_radius_ft", 1.0))
        self.model.pending_plant = plant_payload
        self.model.draw_mode = "plant"
        self._start_sunlight_computation(plant_payload)
        return True

    def _start_sunlight_computation(self, plant):
        """Compute the sunlight overlay on a background thread."""
        self._sunlight_token += 1
        token = self._sunlight_token
        self.model.sunlight_overlay = []

        def _compute():
            overlay = self.build_sunlight_overlay(plant)
            if self._sunlight_token == token:
                Clock.schedule_once(lambda _dt: self._apply_sunlight_overlay(overlay, token), 0)

        threading.Thread(target=_compute, daemon=True).start()

    def _apply_sunlight_overlay(self, overlay, token):
        if self._sunlight_token == token and self.model.pending_plant is not None:
            self.model.sunlight_overlay = overlay

    def save_plot(self, filename=None, storage_manager=None):
        """Persist the current garden plot to local JSON storage."""
        manager = storage_manager or self._resolve_storage_manager()
        return manager.save_model(self.model, filename)

    def _restore_persistent_state(self, loaded_model):
        """Replace current durable plot state with loaded model data."""
        self.cancel_drawing()
        self.deselect()

        self.model.width_ft = loaded_model.width_ft
        self.model.height_ft = loaded_model.height_ft
        self.model.shapes = [
            self._shape_with_grid_cell(shape) for shape in loaded_model.shapes
        ]
        self.model.offset_x = 0.0
        self.model.offset_y = 0.0
        self.model.snap_preview = None
        self._rebuild_garden_grid()
        self.model.timezone_name = loaded_model.timezone_name
        self.update_sun(
            loaded_model.lat,
            loaded_model.lon,
            loaded_model.date_str,
            loaded_model.time_str,
            loaded_model.timezone_name,
            show_errors=False,
        )

        self.command_history = CommandHistory(self)
        self._sync_history_state()

    def load_plot(self, filename=None, storage_manager=None):
        """Load a locally stored garden plot into the current controller state."""
        manager = storage_manager or self._resolve_storage_manager()
        loaded_model = manager.load_model(filename)
        self._restore_persistent_state(loaded_model)
        return manager.get_plot_path(filename)

    def apply_dimensions(self, w_text, h_text):
        try:
            width_ft = float(w_text)
            height_ft = float(h_text)
            if not (3 <= width_ft <= 100 and 3 <= height_ft <= 100):
                raise ValueError

            self.model.width_ft = width_ft
            self.model.height_ft = height_ft
            self._refresh_shape_grid_cells()
            self.update_sun(self.model.lat, self.model.lon, self.model.date_str, self.model.time_str, show_errors=False)
            return True
        except ValueError:
            self.dispatch('on_alert', "Invalid Input", "Dimensions must be 3-100 feet.")
            return False

    def zoom_in(self, anchor_local=None):
        self.zoom_view(1.2, anchor_local=anchor_local)

    def zoom_out(self, anchor_local=None):
        self.zoom_view(1.0 / 1.2, anchor_local=anchor_local)

    def pan_view(self, dx, dy):
        self.model.offset_x += dx
        self.model.offset_y += dy

    def zoom_view(self, scale_factor, anchor_local=None):
        if scale_factor <= 0:
            return

        old_scale = self.model.scale
        new_scale = max(0.5, min(200.0, old_scale * scale_factor))
        if abs(new_scale - old_scale) <= 1e-9:
            return

        if anchor_local is None:
            anchor_x, anchor_y = 0.0, 0.0
        else:
            anchor_x = float(anchor_local[0])
            anchor_y = float(anchor_local[1])

        world_x = (anchor_x - self.model.offset_x) / old_scale
        world_y = (anchor_y - self.model.offset_y) / old_scale

        self.model.scale = new_scale
        self.model.offset_x = anchor_x - world_x * new_scale
        self.model.offset_y = anchor_y - world_y * new_scale

    def set_snap_to_grid(self, enabled):
        self.model.snap_to_grid = bool(enabled)
        if not self.model.snap_to_grid:
            self.model.snap_preview = None

    def set_grid_size(self, value):
        try:
            grid_size = float(value)
            if grid_size <= 0:
                raise ValueError
        except (TypeError, ValueError):
            self.dispatch("on_alert", "Invalid Input", "Grid size must be a positive number.")
            return False

        self.model.grid_size = grid_size
        self._refresh_shape_grid_cells()
        return True

    def update_sun(
        self,
        lat_text,
        lon_text,
        date_str,
        time_str,
        timezone_text=None,
        show_errors=True,
    ):
        try:
            lat = float(lat_text)
            lon = float(lon_text)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
        except ValueError:
            if show_errors:
                self.dispatch('on_alert', "Invalid Input", "Please enter valid latitude and longitude.")
            return False

        try:
            date_value = datetime.date.fromisoformat(date_str)
            time_value = datetime.time.fromisoformat(time_str)
        except ValueError:
            if show_errors:
                self.dispatch('on_alert', "Invalid Input", "Date must be YYYY-MM-DD and time HH:MM:SS.")
            return False

        timezone_name = self.timezone_name_for_location(lat, lon)
        if not timezone_name:
            timezone_name = str(timezone_text or self.model.timezone_name).strip()
        try:
            timezone_value = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            if show_errors:
                self.dispatch(
                    'on_alert',
                    "Invalid Input",
                    "Timezone must be a valid IANA zone like America/New_York.",
                )
            return False

        self.model.lat = lat
        self.model.lon = lon
        if not self.model.map_overlay_anchor_locked:
            self._set_map_overlay_anchor(lat, lon)
        self.model.timezone_name = timezone_name
        self.model.date_str = date_str
        self.model.time_str = time_str
        self.model.time_minutes = minutes_from_time_str(time_str)

        dt_value = datetime.datetime.combine(date_value, time_value, tzinfo=timezone_value)
        observer = Observer(latitude=lat, longitude=lon, elevation=0)
        self.model.sun_azimuth = azimuth(observer, dt_value)
        self.model.sun_elevation = elevation(observer, dt_value)
        return True

    def _get_timezone_finder(self):
        if TimezoneFinder is None:
            return None
        if self._timezone_finder is None:
            self._timezone_finder = TimezoneFinder(in_memory=True)
        return self._timezone_finder

    def timezone_name_for_location(self, lat, lon):
        try:
            lat_value = float(lat)
            lon_value = float(lon)
        except (TypeError, ValueError):
            return None

        cache_key = (round(lat_value, 5), round(lon_value, 5))
        if cache_key in self._timezone_lookup_cache:
            return self._timezone_lookup_cache[cache_key]

        finder = self._get_timezone_finder()
        if finder is None:
            return None

        try:
            timezone_name = finder.timezone_at(lng=lon_value, lat=lat_value)
        except Exception:
            return None
        if not timezone_name:
            return None

        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            return None

        self._timezone_lookup_cache[cache_key] = timezone_name
        return timezone_name

    def geocode_address(self, address_text, show_errors=True):
        query = str(address_text or "").strip()
        if not query:
            if show_errors:
                self.dispatch("on_alert", "Invalid Input", "Please enter a street address or place name.")
            return None

        cached = self._geocode_cache.get(query.casefold())
        if cached is not None:
            return dict(cached)

        params = {
            "q": query,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
        }
        email = str(os.environ.get("GARDEN_GEOCODER_EMAIL", "")).strip()
        if email:
            params["email"] = email
        url = "{}?{}".format(
            os.environ.get("GARDEN_GEOCODER_URL", self.GEOCODER_URL),
            urllib.parse.urlencode(params),
        )
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": os.environ.get(
                    "GARDEN_GEOCODER_USER_AGENT",
                    self.GEOCODER_USER_AGENT,
                ),
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
            ValueError,
        ):
            if show_errors:
                self.dispatch(
                    "on_alert",
                    "Address Search",
                    "Could not look up that address right now.",
                )
            return None

        if not payload:
            if show_errors:
                self.dispatch(
                    "on_alert",
                    "Address Search",
                    "No map result was found for that address.",
                )
            return None

        result = payload[0]
        try:
            geocode = {
                "lat": float(result["lat"]),
                "lon": float(result["lon"]),
                "display_name": str(result.get("display_name", query)),
            }
        except (KeyError, TypeError, ValueError):
            if show_errors:
                self.dispatch(
                    "on_alert",
                    "Address Search",
                    "The geocoder returned an unreadable result.",
                )
            return None

        self._geocode_cache[query.casefold()] = dict(geocode)
        return geocode

    def apply_map_overlay_calibration(self, geo_a, geo_b, local_a=None, local_b=None):
        local_a = (0.0, 0.0) if local_a is None else local_a
        local_b = (float(self.model.width_ft), 0.0) if local_b is None else local_b
        try:
            anchor_lat, anchor_lon, theta_deg = calibrate_garden_overlay(
                local_a,
                geo_a,
                local_b,
                geo_b,
                y_axis_sign=self.model.map_overlay_y_axis_sign,
            )
        except (TypeError, ValueError) as exc:
            self.dispatch("on_alert", "Map Calibration", str(exc))
            return False

        self.model.map_overlay_anchor_lat = anchor_lat
        self.model.map_overlay_anchor_lon = anchor_lon
        self.model.map_overlay_rotation_deg = theta_deg
        self.model.map_overlay_is_calibrated = True
        self.model.map_overlay_anchor_locked = True
        self.model.map_overlay_calibration_mode = MAP_OVERLAY_CALIBRATION_IDLE
        self.model.map_overlay_calibration_a_x_ft = float(local_a[0])
        self.model.map_overlay_calibration_a_y_ft = float(local_a[1])
        self.model.map_overlay_calibration_a_lat = float(geo_a[0])
        self.model.map_overlay_calibration_a_lon = float(geo_a[1])
        self.model.map_overlay_calibration_b_x_ft = float(local_b[0])
        self.model.map_overlay_calibration_b_y_ft = float(local_b[1])
        self.model.map_overlay_calibration_b_lat = float(geo_b[0])
        self.model.map_overlay_calibration_b_lon = float(geo_b[1])
        return True

    def set_map_overlay_y_axis_sign(self, y_axis_sign):
        try:
            sign = 1.0 if float(y_axis_sign) >= 0.0 else -1.0
        except (TypeError, ValueError):
            sign = 1.0
        self.model.map_overlay_y_axis_sign = sign
        self._refresh_map_overlay_calibration_geo_points()
        return sign

    def toggle_map_overlay_y_axis_sign(self):
        return self.set_map_overlay_y_axis_sign(-float(self.model.map_overlay_y_axis_sign))

    def _refresh_map_overlay_calibration_geo_points(self):
        if not self.model.map_overlay_is_calibrated:
            return
        a_lat, a_lon = garden_ft_to_latlon(
            self.model.map_overlay_calibration_a_x_ft,
            self.model.map_overlay_calibration_a_y_ft,
            self.model.map_overlay_anchor_lat,
            self.model.map_overlay_anchor_lon,
            self.model.map_overlay_rotation_deg,
            y_axis_sign=self.model.map_overlay_y_axis_sign,
        )
        b_lat, b_lon = garden_ft_to_latlon(
            self.model.map_overlay_calibration_b_x_ft,
            self.model.map_overlay_calibration_b_y_ft,
            self.model.map_overlay_anchor_lat,
            self.model.map_overlay_anchor_lon,
            self.model.map_overlay_rotation_deg,
            y_axis_sign=self.model.map_overlay_y_axis_sign,
        )
        self.model.map_overlay_calibration_a_lat = a_lat
        self.model.map_overlay_calibration_a_lon = a_lon
        self.model.map_overlay_calibration_b_lat = b_lat
        self.model.map_overlay_calibration_b_lon = b_lon

    def _set_map_overlay_anchor(self, lat, lon):
        self.model.map_overlay_anchor_lat = float(lat)
        self.model.map_overlay_anchor_lon = float(lon)
        self._refresh_map_overlay_calibration_geo_points()

    def set_map_overlay_anchor_locked(self, locked):
        self.model.map_overlay_anchor_locked = bool(locked)
        if not self.model.map_overlay_anchor_locked:
            self._set_map_overlay_anchor(self.model.lat, self.model.lon)
        return self.model.map_overlay_anchor_locked

    def toggle_map_overlay_anchor_locked(self):
        return self.set_map_overlay_anchor_locked(not self.model.map_overlay_anchor_locked)

    def begin_map_overlay_calibration(self):
        self.model.map_overlay_calibration_mode = MAP_OVERLAY_CALIBRATION_TWO_POINT
        return True

    def cancel_map_overlay_calibration(self):
        self.model.map_overlay_calibration_mode = MAP_OVERLAY_CALIBRATION_IDLE
        return True

    def simulate_day_shadows(self, date_str, minutes=None, timezone_text=None):
        """Update sun state using the current slider-selected minute of day."""
        if minutes is not None:
            self.model.time_minutes = max(0, min(1440, int(round(minutes))))
        simulated_time = time_str_from_minutes(self.model.time_minutes)
        self.model.time_str = simulated_time
        return self.update_sun(
            self.model.lat,
            self.model.lon,
            date_str,
            simulated_time,
            timezone_text or self.model.timezone_name,
            show_errors=False,
        )

    def set_draw_mode(self, mode):
        self.cancel_drawing()
        self.deselect()
        self.model.draw_mode = mode

    def set_grid_stamp_mode(self, mode):
        """Select a drag tool that stamps one item per newly entered grid cell."""
        if mode not in self.GRID_STAMP_MODES:
            self.dispatch("on_alert", "Drag Tool", "Unknown grid stamp tool.")
            return False
        self.cancel_drawing()
        self.deselect()
        self._active_grid_stamp_cells = set()
        self._grid_stamp_plant = None
        self.model.draw_mode = mode
        self._grid_stamp_touch_active = False
        return True

    def start_seed_stamp_mode(self, plant):
        """Select the plant used by the seed drag-stamp tool."""
        if not isinstance(plant, dict):
            self.dispatch("on_alert", "Seed Palette", "Invalid plant selection.")
            return False

        self.cancel_drawing()
        self.deselect()
        plant_payload = ensure_growth_payload(plant)
        plant_payload["root_radius_ft"] = float(plant_payload.get("root_radius_ft", 1.0))
        self._grid_stamp_plant = plant_payload
        self.model.pending_plant = plant_payload
        self.model.draw_mode = "carrot_seed"
        self._grid_stamp_touch_active = False
        return True

    def cancel_drawing(self):
        self._sunlight_token += 1
        self._active_grid_stamp_cells = set()
        self._last_grid_stamp_cell = None
        self._grid_stamp_touch_active = False
        self._grid_stamp_plant = None
        self._clear_preview()
        self.model.poly_points = []
        self.model.drag_start = None
        self.model.draw_mode = None
        self.model.pending_plant = None
        self.model.plant_preview = None
        self.model.sunlight_overlay = []

    def clear_shapes(self):
        if not self.model.shapes:
            return
        deleted_items = list(enumerate(self.model.shapes))
        self.cancel_drawing()
        self.command_history.execute(
            DeleteShapeCommand(self, deleted_items, restore_selection=False)
        )

    def set_draw_category(self, category):
        self.model.draw_category = category

    def _snap(self, world):
        if not self.model.snap_to_grid or self.model.grid_size <= 0:
            self.model.snap_preview = None
            return tuple(world)

        grid_size = self.model.grid_size
        snapped_x = round(world[0] / grid_size) * grid_size
        snapped_y = round(world[1] / grid_size) * grid_size
        snapped_x = max(0.0, min(snapped_x, self.model.width_ft))
        snapped_y = max(0.0, min(snapped_y, self.model.height_ft))
        snapped = (snapped_x, snapped_y)
        self.model.snap_preview = snapped
        return snapped

    def world_to_grid_cell(self, world):
        """Convert world coordinates to nearest grid col/row and snapped world point."""
        grid_size = max(float(self.model.grid_size), GEOM_EPSILON)
        max_col = max(0, int(math.ceil(self.model.width_ft / grid_size)))
        max_row = max(0, int(math.ceil(self.model.height_ft / grid_size)))
        wx = max(0.0, min(float(world[0]), self.model.width_ft))
        wy = max(0.0, min(float(world[1]), self.model.height_ft))
        col = max(0, min(max_col, int(round(wx / grid_size))))
        row = max(0, min(max_row, int(round(wy / grid_size))))
        snapped = (
            max(0.0, min(col * grid_size, self.model.width_ft)),
            max(0.0, min(row * grid_size, self.model.height_ft)),
        )
        return col, row, snapped

    def grid_cell_to_world(self, grid_cell):
        """Return the snapped world coordinate for a grid col/row."""
        grid_size = max(float(self.model.grid_size), GEOM_EPSILON)
        col, row = grid_cell
        return (
            max(0.0, min(float(col) * grid_size, self.model.width_ft)),
            max(0.0, min(float(row) * grid_size, self.model.height_ft)),
        )

    def _snap_to_grid_cell(self, world):
        col, row, snapped = self.world_to_grid_cell(world)
        self.model.snap_preview = snapped
        return snapped, (col, row)

    def _grid_cell_is_empty(self, col, row):
        return (col, row) not in self._grid_index

    def _shape_grid_cell(self, shape):
        if shape.get("type") != "circle":
            return None
        if not shape.get("plant") and not shape.get("grid_item"):
            return None
        try:
            center_x, center_y = shape["geom"][:2]
        except (KeyError, TypeError, ValueError):
            return None
        col, row, _snapped = self.world_to_grid_cell((center_x, center_y))
        return col, row

    def _rebuild_garden_grid(self):
        """Rebuild the headless simulation spatial hash from current shapes."""
        previous_tick_count = getattr(self.sim_world, "tick_count", 0)
        previous_engine = getattr(self, "sim_engine", None)
        sim_world = SimulationWorld()
        sim_world.tick_count = previous_tick_count
        for idx, shape in enumerate(self.model.shapes):
            cell = self._shape_grid_cell(shape)
            if cell is None:
                continue
            key = (int(cell[0]), int(cell[1]))
            if sim_world.get_entity(*key) is not None:
                continue
            sim_world.add_entity(self._shape_to_sim_entity(idx, shape, key))
        self.sim_world = sim_world
        self._grid_index = sim_world.garden_grid
        self._active_hose_cells = sim_world.active_hoses
        self._active_plant_cells = sim_world.active_plants
        self._active_spigot_cells = sim_world.active_spigots
        self.sim_engine = SimulationEngine(
            sim_world,
            repositories=getattr(previous_engine, "repositories", ()),
            sync_interval_ticks=getattr(
                previous_engine,
                "sync_interval_ticks",
                DEFAULT_ENGINE_SYNC_INTERVAL_TICKS,
            ),
            last_sync_time=getattr(previous_engine, "last_sync_time", None),
            last_persisted_tick=getattr(previous_engine, "_last_persisted_tick", None),
        )
        self._refresh_hose_sprites()

    def load_simulation_world(
        self,
        sim_world,
        last_simulated_unix_time=None,
        sync_shapes=False,
    ):
        """Replace the headless simulation world, optionally mirroring it to shapes."""
        previous_engine = getattr(self, "sim_engine", None)
        self.sim_world = sim_world
        self._grid_index = sim_world.garden_grid
        self._active_hose_cells = sim_world.active_hoses
        self._active_plant_cells = sim_world.active_plants
        self._active_spigot_cells = sim_world.active_spigots
        self.sim_engine = SimulationEngine(
            sim_world,
            repositories=getattr(previous_engine, "repositories", ()),
            sync_interval_ticks=getattr(
                previous_engine,
                "sync_interval_ticks",
                DEFAULT_ENGINE_SYNC_INTERVAL_TICKS,
            ),
            catch_up_chunk_ticks=getattr(
                previous_engine,
                "catch_up_chunk_ticks",
                DEFAULT_CATCHUP_CHUNK_TICKS,
            ),
            last_sync_time=last_simulated_unix_time,
            last_simulated_unix_time=last_simulated_unix_time,
            last_persisted_tick=sim_world.tick_count,
        )
        if sync_shapes:
            self.model.shapes = [
                shape
                for shape in (
                    self._sim_entity_to_shape(entity)
                    for _pos, entity in sorted(sim_world.garden_grid.items())
                )
                if shape is not None
            ]
            self._rebuild_garden_grid()

    def _sim_entity_to_shape(self, entity):
        center = self.grid_cell_to_world(entity.grid_pos)
        if isinstance(entity, HoseEntity):
            return {
                "type": "circle",
                "category": "Irrigation Hose",
                "height_ft": 0.0,
                "locked_orientation": False,
                "geom": (center[0], center[1], self._grid_stamp_radius("irrigation_hose")),
                "grid_item": "irrigation_hose",
                "grid_cell": entity.grid_pos,
                "hose_capacity": entity.max_capacity,
                "hose_flow_rate": entity.flow_rate,
                "water_level": entity.water_level,
            }
        if isinstance(entity, PlantEntity):
            radius_ft = self._grid_stamp_radius("carrot_seed")
            plant = ensure_growth_payload(
                {
                    "name": entity.plant_name,
                    "growth_progress": entity.growth_progress,
                    "growth_state": entity.growth_state,
                    "visual_stage": entity.visual_stage,
                    "sprite_source": entity.sprite_source,
                    "health": entity.health,
                    "max_health": entity.max_health,
                    "vitality": entity.vitality,
                    "fertilizer": entity.fertilizer,
                    "has_water": entity.has_water,
                    "growth_rate": entity.growth_rate_per_tick,
                    "growth_rate_per_tick": entity.growth_rate_per_tick,
                    "water_consumption": entity.water_consumption_per_tick,
                    "water_consumption_per_tick": entity.water_consumption_per_tick,
                    "root_radius_ft": radius_ft,
                }
            )
            return {
                "type": "circle",
                "category": "Plant",
                "height_ft": 0.0,
                "locked_orientation": False,
                "geom": (center[0], center[1], radius_ft),
                "grid_item": "carrot_seed",
                "grid_cell": entity.grid_pos,
                "plant": plant,
            }
        if isinstance(entity, SpigotEntity):
            return {
                "type": "circle",
                "category": "Irrigation Hose",
                "height_ft": 0.0,
                "locked_orientation": False,
                "geom": (center[0], center[1], self._grid_stamp_radius("irrigation_hose")),
                "grid_item": "spigot",
                "grid_cell": entity.grid_pos,
                "spigot_flow_rate": entity.flow_rate,
            }
        return None

    def _shape_to_sim_entity(self, idx, shape, grid_pos):
        col, row = grid_pos
        entity_id = f"shape:{idx}"
        grid_item = shape.get("grid_item")
        if grid_item == "irrigation_hose":
            return HoseEntity(
                col,
                row,
                entity_id=entity_id,
                max_capacity=float(shape.get("hose_capacity", DEFAULT_HOSE_CAPACITY)),
                flow_rate=float(shape.get("hose_flow_rate", DEFAULT_HOSE_FLOW_RATE)),
                water_level=float(shape.get("water_level", DEFAULT_HOSE_INITIAL_WATER)),
            )
        if grid_item == "spigot":
            return SpigotEntity(
                col,
                row,
                entity_id=entity_id,
                flow_rate=float(shape.get("spigot_flow_rate", DEFAULT_SPIGOT_FLOW_RATE)),
            )
        if shape.get("plant"):
            plant = ensure_growth_payload(shape["plant"])
            return PlantEntity(
                col,
                row,
                entity_id=entity_id,
                plant_name=plant.get("name", "Plant"),
                growth_progress=float(plant.get("growth_progress", 0.0)),
                health=float(plant.get("health", DEFAULT_PLANT_HEALTH)),
                water_consumption_per_tick=float(
                    plant.get(
                        "water_consumption_per_tick",
                        plant.get("water_consumption", DEFAULT_PLANT_WATER_CONSUMPTION),
                    )
                ),
                growth_rate_per_tick=float(
                    plant.get(
                        "growth_rate_per_tick",
                        plant.get("growth_rate", DEFAULT_PLANT_GROWTH_RATE),
                    )
                ),
                visual_stage=plant.get("visual_stage", plant.get("growth_state", "SEED")),
                sprite_source=plant.get("sprite_source", plant.get("growth_sprite", "seed")),
                growth_state=plant.get("growth_state", "SEED"),
                growth_rate=plant.get("growth_rate"),
                max_health=float(plant.get("max_health", DEFAULT_PLANT_MAX_HEALTH)),
                vitality=float(plant.get("vitality", DEFAULT_PLANT_VITALITY)),
                water_consumption=plant.get("water_consumption"),
                fertilizer=float(plant.get("fertilizer", 1.0)),
                has_water=bool(plant.get("has_water", False)),
            )
        return GridEntity(col, row, entity_id=entity_id, entity_type=grid_item or "occupied")

    def _hose_sprite_for_connections(self, connections):
        dirs = set(connections)
        if not dirs:
            return "isolated", 0
        if len(dirs) == 1:
            direction = next(iter(dirs))
            return "end", {"E": 0, "N": 90, "W": 180, "S": 270}[direction]
        if len(dirs) == 2:
            if dirs == {"E", "W"}:
                return "straight", 0
            if dirs == {"N", "S"}:
                return "straight", 90
            return "corner", {
                frozenset(("N", "E")): 0,
                frozenset(("N", "W")): 90,
                frozenset(("S", "W")): 180,
                frozenset(("S", "E")): 270,
            }[frozenset(dirs)]
        if len(dirs) == 3:
            missing = ({"N", "E", "S", "W"} - dirs).pop()
            return "tee", {"W": 0, "S": 90, "E": 180, "N": 270}[missing]
        return "cross", 0

    def _refresh_hose_sprites(self):
        hose_cells = self._active_hose_cells
        if not hose_cells:
            return

        offsets = (("N", 0, 1), ("E", 1, 0), ("S", 0, -1), ("W", -1, 0))
        changed = False
        refreshed = []
        for shape in self.model.shapes:
            if shape.get("grid_item") != "irrigation_hose":
                refreshed.append(shape)
                continue

            cell = shape.get("grid_cell")
            if cell is None:
                refreshed.append(shape)
                continue

            col, row = tuple(cell)
            connections = tuple(
                direction
                for direction, delta_col, delta_row in offsets
                if (col + delta_col, row + delta_row) in hose_cells
            )
            sprite, rotation = self._hose_sprite_for_connections(connections)
            next_shape = {
                **shape,
                "hose_connections": connections,
                "hose_sprite": sprite,
                "hose_rotation": rotation,
            }
            changed = changed or next_shape != shape
            refreshed.append(next_shape)

        if changed:
            self.model.shapes = refreshed

    def _cell_has_water(self, col, row):
        """Return True if a hose occupies the cell or any of its 4 neighbours."""
        hose = self._active_hose_cells
        return (
            (col, row) in hose
            or (col + 1, row) in hose
            or (col - 1, row) in hose
            or (col, row + 1) in hose
            or (col, row - 1) in hose
        )

    def _plant_has_water(self, shape):
        cell = shape.get("grid_cell")
        if cell is None:
            return False
        return self._cell_has_water(cell[0], cell[1])

    def _plant_has_fertilizer(self, shape):
        plant = shape.get("plant") or {}
        try:
            return float(plant.get("fertilizer", 1.0)) > 0.0
        except (TypeError, ValueError):
            return True

    def tick_growth(self, tick_days=1.0):
        """Advance growth only for active (placed) plants."""
        if not self._active_plant_cells:
            return False

        # Build a lookup from grid_cell to shape index for the active set only.
        cell_to_idx = {}
        for idx, shape in enumerate(self.model.shapes):
            cell = shape.get("grid_cell")
            if cell is not None and shape.get("plant"):
                cell_to_idx[tuple(cell)] = idx

        next_shapes = list(self.model.shapes)
        changed = False

        for cell in self._active_plant_cells:
            idx = cell_to_idx.get(cell)
            if idx is None:
                continue

            shape = self.model.shapes[idx]
            next_shape = clone_shape(shape)
            plant = ensure_growth_payload(next_shape["plant"])
            before = (
                plant["growth_progress"],
                plant["growth_state"],
                plant.get("growth_sprite"),
                plant.get("output"),
                plant.get("has_water"),
                plant.get("has_fertilizer"),
                plant.get("health"),
                plant.get("vitality"),
            )
            update_growth(
                plant,
                tick_days=tick_days,
                has_water=self._plant_has_water(next_shape),
                has_fertilizer=self._plant_has_fertilizer(next_shape),
            )
            after = (
                plant["growth_progress"],
                plant["growth_state"],
                plant.get("growth_sprite"),
                plant.get("output"),
                plant.get("has_water"),
                plant.get("has_fertilizer"),
                plant.get("health"),
                plant.get("vitality"),
            )
            next_shape["plant"] = plant
            if before != after:
                next_shapes[idx] = self._shape_with_grid_cell(next_shape)
                changed = True

        if changed:
            self.model.shapes = next_shapes
            self._rebuild_garden_grid()
        return changed

    def tick_growth_minutes(self, simulation_minutes=1.0):
        """Advance growth using simulation minutes, where 1440 minutes = 1 day."""
        try:
            minutes = max(0.0, float(simulation_minutes))
        except (TypeError, ValueError):
            minutes = 0.0
        return self.tick_growth(minutes / 1440.0)

    def run_simulation_ticks(self, ticks):
        """Run deterministic headless ticks and sync state into Kivy shape dicts."""
        ran = self.sim_engine.run_ticks(ticks)
        if ran <= 0:
            return 0
        self._sync_sim_world_state_to_shapes()
        return ran

    def _sync_sim_world_state_to_shapes(self):
        next_shapes = list(self.model.shapes)
        changed = False
        for idx, shape in enumerate(self.model.shapes):
            entity = self.sim_world.get_entity_by_id(f"shape:{idx}")
            if isinstance(entity, PlantEntity) and shape.get("plant"):
                plant = ensure_growth_payload(shape["plant"])
                plant.update(
                    {
                        "growth_progress": entity.growth_progress,
                        "growth_state": entity.growth_state,
                        "visual_stage": entity.visual_stage,
                        "sprite_source": entity.sprite_source,
                        "health": entity.health,
                        "max_health": entity.max_health,
                        "vitality": entity.vitality,
                        "has_water": entity.has_water,
                        "fertilizer": entity.fertilizer,
                        "growth_rate": entity.growth_rate_per_tick,
                        "growth_rate_per_tick": entity.growth_rate_per_tick,
                        "water_consumption": entity.water_consumption_per_tick,
                        "water_consumption_per_tick": entity.water_consumption_per_tick,
                    }
                )
                plant = ensure_growth_payload(plant)
                if plant != shape["plant"]:
                    next_shapes[idx] = {**shape, "plant": plant}
                    changed = True
            elif isinstance(entity, HoseEntity) and shape.get("grid_item") == "irrigation_hose":
                water_level = entity.water_level
                if (
                    shape.get("water_level") != water_level
                    or shape.get("hose_capacity") != entity.max_capacity
                    or shape.get("hose_flow_rate") != entity.flow_rate
                ):
                    next_shapes[idx] = {
                        **shape,
                        "water_level": water_level,
                        "hose_capacity": entity.max_capacity,
                        "hose_flow_rate": entity.flow_rate,
                    }
                    changed = True

        if changed:
            self.model.shapes = next_shapes
            self._rebuild_garden_grid()
        return changed

    def catch_up_simulation(self, elapsed_seconds):
        """Run bounded offline catch-up using the deterministic base tick."""
        try:
            elapsed = max(0.0, float(elapsed_seconds))
        except (TypeError, ValueError):
            elapsed = 0.0
        ran = self.sim_engine.catch_up_simulation(elapsed)
        if ran > 0:
            self._sync_sim_world_state_to_shapes()
        return ran

    def _shape_with_grid_cell(self, shape):
        normalized = clone_shape(shape)
        if normalized.get("plant"):
            normalized["plant"] = ensure_growth_payload(normalized["plant"])
        cell = self._shape_grid_cell(normalized)
        if cell is not None:
            normalized["grid_cell"] = cell
        elif "grid_cell" in normalized:
            normalized.pop("grid_cell")
        return normalized

    def _refresh_shape_grid_cells(self):
        self.model.shapes = [
            self._shape_with_grid_cell(shape) for shape in self.model.shapes
        ]
        self._rebuild_garden_grid()

    def _grid_stamp_radius(self, mode):
        grid_size = max(float(self.model.grid_size), GEOM_EPSILON)
        if mode == "irrigation_hose":
            return max(0.06, min(grid_size * 0.36, 0.35))
        return max(0.05, min(grid_size * 0.28, 0.35))

    def _build_grid_stamp_shape(self, mode, center, grid_cell):
        radius_ft = self._grid_stamp_radius(mode)
        if mode == "irrigation_hose":
            return {
                "type": "circle",
                "category": "Irrigation Hose",
                "height_ft": 0.0,
                "locked_orientation": False,
                "geom": (center[0], center[1], radius_ft),
                "grid_item": "irrigation_hose",
                "grid_cell": grid_cell,
                "hose_capacity": DEFAULT_HOSE_CAPACITY,
                "hose_flow_rate": DEFAULT_HOSE_FLOW_RATE,
                "water_level": DEFAULT_HOSE_INITIAL_WATER,
            }

        plant_source = self._grid_stamp_plant or {
            "id": 28,
            "name": "Carrot Seed",
            "icon_key": "root",
            "root_radius_ft": radius_ft,
            "maturity_days": 75,
        }
        plant = ensure_growth_payload(plant_source)
        plant["root_radius_ft"] = float(plant.get("root_radius_ft", radius_ft))
        return {
            "type": "circle",
            "category": "Plant",
            "height_ft": 0.0,
            "locked_orientation": False,
            "geom": (center[0], center[1], radius_ft),
            "grid_item": "carrot_seed",
            "grid_cell": grid_cell,
            "plant": plant,
        }

    def _grid_line_cells(self, start_cell, end_cell):
        """Return grid cells crossed between two cells using Bresenham steps."""
        start_col, start_row = start_cell
        end_col, end_row = end_cell
        delta_col = abs(end_col - start_col)
        delta_row = -abs(end_row - start_row)
        step_col = 1 if start_col < end_col else -1
        step_row = 1 if start_row < end_row else -1
        error = delta_col + delta_row
        col, row = start_col, start_row
        cells = []

        while True:
            cells.append((col, row))
            if col == end_col and row == end_row:
                return cells
            doubled_error = 2 * error
            if doubled_error >= delta_row:
                error += delta_row
                col += step_col
            if doubled_error <= delta_col:
                error += delta_col
                row += step_row

    def _stamp_grid_cell(self, mode, grid_cell):
        if grid_cell in self._active_grid_stamp_cells:
            return False

        self._active_grid_stamp_cells.add(grid_cell)
        if not self._grid_cell_is_empty(*grid_cell):
            return False

        new_shape = self._build_grid_stamp_shape(
            mode,
            self.grid_cell_to_world(grid_cell),
            grid_cell,
        )
        self.command_history.execute(AddShapeCommand(self, new_shape))
        self.deselect()
        self.model.draw_mode = mode
        return True

    def _stamp_grid_tool_at(self, world):
        mode = self.model.draw_mode
        if mode not in self.GRID_STAMP_MODES:
            return False
        if not self._grid_stamp_touch_active:
            return False

        snapped_world, grid_cell = self._snap_to_grid_cell(world)
        if self._last_grid_stamp_cell == grid_cell:
            self.model.snap_preview = snapped_world
            return False

        cells = (
            [grid_cell]
            if self._last_grid_stamp_cell is None
            else self._grid_line_cells(self._last_grid_stamp_cell, grid_cell)
        )
        stamped = False
        for cell in cells:
            stamped = self._stamp_grid_cell(mode, cell) or stamped
        self._last_grid_stamp_cell = grid_cell
        self.model.snap_preview = snapped_world
        return stamped

    def _clear_preview(self):
        self.model.drag_rect = None
        self.model.drag_circle = None
        self.model.drag_strip = None
        self.model.snap_preview = None
        self.model.plant_preview = None

    def _clear_move_tracking(self):
        self.model.move_start = None
        self._move_command_before = None

    def _sync_history_state(self):
        self.can_undo = self.command_history.can_undo
        self.can_redo = self.command_history.can_redo

    def undo(self):
        self._clear_move_tracking()
        self.command_history.undo()

    def redo(self):
        self._clear_move_tracking()
        self.command_history.redo()

    def select_shape(self, idx):
        self.model.selected_idx = idx

    def deselect(self):
        self.model.selected_idx = -1
        self.model.move_mode = False
        self._clear_move_tracking()

    def delete_selected(self):
        if self.model.selected_idx == -1:
            return
        idx = self.model.selected_idx
        self.command_history.execute(
            DeleteShapeCommand(
                self,
                [(idx, self.model.shapes[idx])],
                restore_selection=True,
            )
        )

    def toggle_move_mode(self):
        if self.model.selected_idx == -1:
            return
        if not self.model.move_mode:
            self.cancel_drawing()
            self.model.move_mode = True
        else:
            self.model.move_mode = False
        self._clear_move_tracking()

    def apply_prop_changes(self, category, height_text, geometry_dict, locked):
        if self.model.selected_idx == -1:
            return

        idx = self.model.selected_idx
        old_shape = self.model.shapes[idx]
        if category not in CATEGORIES:
            self.dispatch('on_alert', "Invalid Input", "Please choose a valid category.")
            return

        try:
            height_ft = float(height_text)
        except ValueError:
            self.dispatch('on_alert', "Invalid Input", "Please enter valid numeric values.")
            return

        shape_type = old_shape["type"]
        if shape_type == "rect":
            old_x1, old_y1, old_x2, old_y2 = old_shape["geom"]
            x_ft = geometry_dict.get("x", old_x1)
            y_ft = geometry_dict.get("y", old_y1)
            width_ft = abs(geometry_dict.get("width", old_x2 - old_x1))
            height_geom_ft = abs(geometry_dict.get("height", old_y2 - old_y1))
            new_geom = (x_ft, y_ft, x_ft + width_ft, y_ft + height_geom_ft)
            extra_updates = {}
        elif shape_type == "circle":
            old_cx, old_cy, old_radius = old_shape["geom"]
            diameter_ft = abs(geometry_dict.get("diameter", old_radius * 2.0))
            new_geom = (
                geometry_dict.get("cx", old_cx),
                geometry_dict.get("cy", old_cy),
                diameter_ft / 2.0,
            )
            extra_updates = {}
        elif shape_type == "strip":
            old_point_a, old_point_b = old_shape["geom"]
            point_a = (
                geometry_dict.get("x1", old_point_a[0]),
                geometry_dict.get("y1", old_point_a[1]),
            )
            point_b = (
                geometry_dict.get("x2", old_point_b[0]),
                geometry_dict.get("y2", old_point_b[1]),
            )
            validated_a, validated_b, validated_width = self._validated_strip_geom(
                point_a,
                point_b,
                geometry_dict.get(
                    "width_ft",
                    old_shape.get("width_ft", DEFAULT_STRIP_WIDTH_FT),
                ),
            )
            if validated_a is None:
                self.dispatch("on_alert", "Invalid Input", validated_width)
                return
            new_geom = (validated_a, validated_b)
            extra_updates = {"width_ft": validated_width}
        else:
            new_geom = tuple(old_shape["geom"])
            extra_updates = {}

        new_shape = {
            **old_shape,
            "category": category,
            "height_ft": height_ft,
            "locked_orientation": locked,
            "geom": new_geom,
            **extra_updates,
        }
        if new_shape == old_shape:
            return
        self.command_history.execute(
            ModifyPropertyCommand(self, idx, old_shape, new_shape)
        )

    def _append_and_select_shape(self, new_shape):
        self.cancel_drawing()
        self.model.move_mode = False
        self._clear_move_tracking()
        self.command_history.execute(AddShapeCommand(self, new_shape))

    def _build_strip_preview(self, point_a, point_b, width_ft=DEFAULT_STRIP_WIDTH_FT):
        point_a = (float(point_a[0]), float(point_a[1]))
        point_b = (float(point_b[0]), float(point_b[1]))
        return {
            "geom": (point_a, point_b),
            "width_ft": float(width_ft),
            "points": strip_polygon_from_centerline(point_a, point_b, width_ft),
        }

    def _validated_strip_geom(self, point_a, point_b, width_ft):
        try:
            point_a = (float(point_a[0]), float(point_a[1]))
            point_b = (float(point_b[0]), float(point_b[1]))
            width_ft = float(width_ft)
        except (TypeError, ValueError, IndexError):
            return None, None, "Strip geometry must contain numeric endpoints and width."

        if strip_length(point_a, point_b) < MIN_STRIP_LENGTH_FT:
            return None, None, f"A strip must be at least {MIN_STRIP_LENGTH_FT:g} ft long."
        if width_ft < MIN_STRIP_WIDTH_FT:
            return None, None, f"A strip must be at least {MIN_STRIP_WIDTH_FT:g} ft wide."
        return point_a, point_b, width_ft

    def add_strip(self, point_a, point_b, width_ft=None, category=None, locked_orientation=False):
        width_ft = DEFAULT_STRIP_WIDTH_FT if width_ft is None else width_ft
        validated_a, validated_b, validated_width = self._validated_strip_geom(
            point_a,
            point_b,
            width_ft,
        )
        if validated_a is None:
            self.dispatch("on_alert", "Strip", validated_width)
            return False

        strip_category = category or self.model.draw_category
        self._append_and_select_shape(
            {
                "type": "strip",
                "category": strip_category,
                "height_ft": CATEGORIES[strip_category]["height_ft"],
                "locked_orientation": bool(locked_orientation),
                "geom": (validated_a, validated_b),
                "width_ft": validated_width,
            }
        )
        return True

    def _insert_shape_direct(self, idx, shape, select_new=False):
        idx = max(0, min(idx, len(self.model.shapes)))
        self.model.shapes = insert_shape(self.model.shapes, idx, self._shape_with_grid_cell(shape))
        self._rebuild_garden_grid()
        if select_new:
            self.select_shape(idx)
        elif self.model.selected_idx >= idx:
            self.model.selected_idx += 1
        return idx

    def _remove_shape_direct(self, idx):
        if not (0 <= idx < len(self.model.shapes)):
            return None
        removed_shape = clone_shape(self.model.shapes[idx])
        self.model.shapes = remove_shape(self.model.shapes, idx)
        self._rebuild_garden_grid()
        if self.model.selected_idx == idx:
            self.model.selected_idx = -1
            self.model.move_mode = False
            self._clear_move_tracking()
        elif self.model.selected_idx > idx:
            self.model.selected_idx -= 1
        return removed_shape

    def _replace_shape_direct(self, idx, shape):
        if not (0 <= idx < len(self.model.shapes)):
            return
        self.model.shapes = replace_shape(self.model.shapes, idx, self._shape_with_grid_cell(shape))
        self._rebuild_garden_grid()

    def _translated_shape(self, shape, dx, dy):
        shape_type = shape["type"]
        if shape_type == "rect":
            x1, y1, x2, y2 = shape["geom"]
            new_geom = (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
        elif shape_type == "circle":
            cx, cy, radius = shape["geom"]
            new_geom = (cx + dx, cy + dy, radius)
        elif shape_type == "polygon":
            new_geom = tuple((x_ft + dx, y_ft + dy) for x_ft, y_ft in shape["geom"])
        elif shape_type == "strip":
            point_a, point_b = shape["geom"]
            new_geom = (
                (point_a[0] + dx, point_a[1] + dy),
                (point_b[0] + dx, point_b[1] + dy),
            )
        else:
            return clone_shape(shape)
        return {**shape, "geom": new_geom}

    def _shape_translation_delta(self, old_shape, new_shape):
        shape_type = old_shape["type"]
        if shape_type == "rect":
            old_x, old_y = old_shape["geom"][:2]
            new_x, new_y = new_shape["geom"][:2]
        elif shape_type == "circle":
            old_x, old_y = old_shape["geom"][:2]
            new_x, new_y = new_shape["geom"][:2]
        elif shape_type == "polygon":
            old_x, old_y = old_shape["geom"][0]
            new_x, new_y = new_shape["geom"][0]
        elif shape_type == "strip":
            old_x, old_y = old_shape["geom"][0]
            new_x, new_y = new_shape["geom"][0]
        else:
            return 0.0, 0.0
        return new_x - old_x, new_y - old_y

    def _preview_translate_shape(self, idx, dx, dy):
        if not (0 <= idx < len(self.model.shapes)):
            return
        new_shape = self._translated_shape(self.model.shapes[idx], dx, dy)
        self.model.shapes = replace_shape(self.model.shapes, idx, self._shape_with_grid_cell(new_shape))
        self._rebuild_garden_grid()

    def on_mouse_press(self, world):
        if self.model.draw_mode in self.GRID_STAMP_MODES:
            self._active_grid_stamp_cells = set()
            self._last_grid_stamp_cell = None
            self._grid_stamp_touch_active = True
            self._stamp_grid_tool_at(world)
            return

        if self.model.draw_mode == "plant" and self.model.pending_plant is not None:
            snapped_world, grid_cell = self._snap_to_grid_cell(world)
            self.model.drag_start = snapped_world
            self._update_plant_preview(snapped_world, grid_cell=grid_cell)
            return

        if self.model.move_mode and self.model.selected_idx != -1:
            world = self._snap(world)
            self.model.move_start = world
            self._move_command_before = clone_shape(self.model.shapes[self.model.selected_idx])
            return

        if self.model.draw_mode is not None:
            world = self._snap(world)
            if self.model.draw_mode == "polygon":
                if self.model.poly_points:
                    last_x, last_y = self.model.poly_points[-1]
                    if (
                        abs(world[0] - last_x) <= GEOM_EPSILON
                        and abs(world[1] - last_y) <= GEOM_EPSILON
                    ):
                        return
                self.model.poly_points = list(self.model.poly_points) + [tuple(world)]
            else:
                self.model.drag_start = world
                if self.model.draw_mode == "rect":
                    x_ft, y_ft = world
                    self.model.drag_rect = (x_ft, y_ft, x_ft, y_ft)
                elif self.model.draw_mode == "circle":
                    x_ft, y_ft = world
                    self.model.drag_circle = (x_ft, y_ft, 0.0)
                elif self.model.draw_mode == "strip":
                    self.model.drag_strip = self._build_strip_preview(
                        world,
                        world,
                    )
            return

        self.model.snap_preview = None
        wx, wy = world
        for idx in range(len(self.model.shapes) - 1, -1, -1):
            if self.shape_contains(self.model.shapes[idx], wx, wy):
                self.select_shape(idx)
                return
        self.deselect()

    def on_mouse_drag(self, world):
        if self.model.draw_mode in self.GRID_STAMP_MODES:
            self._stamp_grid_tool_at(world)
            return

        if self.model.draw_mode == "plant" and self.model.pending_plant is not None:
            snapped_world, grid_cell = self._snap_to_grid_cell(world)
            self._update_plant_preview(snapped_world, grid_cell=grid_cell)
            return

        if self.model.move_mode and self.model.selected_idx != -1 and self.model.move_start is not None:
            world = self._snap(world)
            dx = world[0] - self.model.move_start[0]
            dy = world[1] - self.model.move_start[1]
            self._preview_translate_shape(self.model.selected_idx, dx, dy)
            self.model.move_start = world
            return

        if self.model.draw_mode == "rect" and self.model.drag_start is not None:
            world = self._snap(world)
            x0, y0 = self.model.drag_start
            x1, y1 = world
            self.model.drag_rect = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        elif self.model.draw_mode == "circle" and self.model.drag_start is not None:
            world = self._snap(world)
            x0, y0 = self.model.drag_start
            radius = math.hypot(world[0] - x0, world[1] - y0)
            self.model.drag_circle = (x0, y0, radius)
        elif self.model.draw_mode == "strip" and self.model.drag_start is not None:
            world = self._snap(world)
            self.model.drag_strip = self._build_strip_preview(
                self.model.drag_start,
                world,
            )

    def on_mouse_release(self, world):
        if self.model.draw_mode in self.GRID_STAMP_MODES:
            self._active_grid_stamp_cells = set()
            self._last_grid_stamp_cell = None
            self._grid_stamp_touch_active = False
            return

        if self.model.draw_mode == "plant" and self.model.pending_plant is not None:
            snapped_world, grid_cell = self._snap_to_grid_cell(world)
            self._update_plant_preview(snapped_world, grid_cell=grid_cell)
            preview = self.model.plant_preview
            if not preview:
                return
            if not preview.get("can_place", True):
                col, row = preview.get("grid_cell", ("?", "?"))
                self.dispatch(
                    "on_alert",
                    "Plant Placement",
                    f"Grid cell ({col}, {row}) is already occupied.",
                )
                return

            plant = ensure_growth_payload(preview["plant"])
            center_x, center_y = preview["center"]
            root_radius_ft = float(preview["radius_ft"])
            new_shape = {
                "type": "circle",
                "category": "Plant",
                "height_ft": 0.0,
                "locked_orientation": False,
                "geom": (center_x, center_y, root_radius_ft),
                "plant": plant,
                "sun_score": preview.get("sun_score"),
                "grid_cell": preview.get("grid_cell"),
            }
            self._append_and_select_shape(new_shape)
            return

        if self.model.move_mode and self.model.selected_idx != -1:
            idx = self.model.selected_idx
            current_start = self.model.move_start
            if current_start is not None:
                snapped_world = self._snap(world)
                dx = snapped_world[0] - current_start[0]
                dy = snapped_world[1] - current_start[1]
                if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                    self._preview_translate_shape(idx, dx, dy)
                    self.model.move_start = snapped_world
            before_shape = self._move_command_before
            self._clear_move_tracking()
            self.model.snap_preview = None
            if before_shape is None or not (0 <= idx < len(self.model.shapes)):
                return

            after_shape = clone_shape(self.model.shapes[idx])
            if after_shape["geom"] == before_shape["geom"]:
                return

            self._replace_shape_direct(idx, before_shape)
            dx, dy = self._shape_translation_delta(before_shape, after_shape)
            self._translate_shape(idx, dx, dy)
            return

        if self.model.draw_mode not in ("rect", "circle", "strip") or self.model.drag_start is None:
            return

        x0, y0 = self.model.drag_start
        x1, y1 = self._snap(world)
        if self.model.draw_mode in ("rect", "circle") and abs(x1 - x0) < 0.1 and abs(y1 - y0) < 0.1:
            self._clear_preview()
            self.model.drag_start = None
            return

        category = self.model.draw_category
        height_ft = CATEGORIES[category]["height_ft"]

        new_shape = {
            "category": category,
            "height_ft": height_ft,
            "locked_orientation": False,
        }

        if self.model.draw_mode == "rect":
            new_shape["type"] = "rect"
            new_shape["geom"] = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        elif self.model.draw_mode == "circle":
            new_shape["type"] = "circle"
            new_shape["geom"] = (x0, y0, math.hypot(x1 - x0, y1 - y0))
        else:
            if not self.add_strip(
                (x0, y0),
                (x1, y1),
                DEFAULT_STRIP_WIDTH_FT,
                category=category,
                locked_orientation=False,
            ):
                self._clear_preview()
                self.model.drag_start = None
            return

        self._append_and_select_shape(new_shape)

    def finish_polygon(self):
        # Polygon contract: one ordered outer ring stored as open boundary
        # vertices. Valid polygons must be simple, non-zero-area, and may be
        # convex or concave.
        is_valid, polygon_points, message = validate_polygon_points(self.model.poly_points)
        if not is_valid:
            self.dispatch("on_alert", "Polygon", message)
            return

        category = self.model.draw_category
        self._append_and_select_shape(
            {
                "type": "polygon",
                "category": category,
                "height_ft": CATEGORIES[category]["height_ft"],
                "locked_orientation": False,
                "geom": polygon_points,
            },
        )

    def _translate_shape(self, idx, dx, dy):
        if not (0 <= idx < len(self.model.shapes)):
            return
        old_shape = clone_shape(self.model.shapes[idx])
        new_shape = self._translated_shape(old_shape, dx, dy)
        if new_shape["geom"] == old_shape["geom"]:
            return
        self.command_history.execute(MoveShapeCommand(self, idx, old_shape, new_shape))

    def shape_contains(self, shape, wx, wy):
        shape_type = shape["type"]
        if shape_type == "rect":
            x1, y1, x2, y2 = shape["geom"]
            return min(x1, x2) <= wx <= max(x1, x2) and min(y1, y2) <= wy <= max(y1, y2)
        if shape_type == "circle":
            cx, cy, radius = shape["geom"]
            return math.hypot(wx - cx, wy - cy) <= radius
        if shape_type == "polygon":
            return point_in_polygon(wx, wy, shape["geom"])
        if shape_type == "strip":
            strip_polygon = strip_polygon_from_centerline(
                shape["geom"][0],
                shape["geom"][1],
                shape.get("width_ft", DEFAULT_STRIP_WIDTH_FT),
            )
            return bool(strip_polygon) and point_in_polygon(wx, wy, strip_polygon)
        return False

    def shape_index_at_world(self, world):
        wx, wy = world
        for idx in range(len(self.model.shapes) - 1, -1, -1):
            if self.shape_contains(self.model.shapes[idx], wx, wy):
                return idx
        return -1

    def get_shadow_vector(self):
        return self._shadow_vector_for(self.model.sun_azimuth, self.model.sun_elevation)

    def _shadow_vector_for(self, sun_azimuth, sun_elevation):
        if sun_elevation <= 0:
            return None
        length = 1.0 / math.tan(math.radians(sun_elevation))
        azimuth_rad = math.radians(sun_azimuth)
        return -length * math.sin(azimuth_rad), -length * math.cos(azimuth_rad)

    def _update_plant_preview(self, world, grid_cell=None):
        plant = self.model.pending_plant
        if plant is None:
            return

        if grid_cell is None:
            _col, _row, snapped_world = self.world_to_grid_cell(world)
            world = snapped_world
            grid_cell = (_col, _row)

        col, row = grid_cell
        radius_ft = float(plant.get("root_radius_ft", 1.0))
        self.model.plant_preview = {
            "plant": plant,
            "center": tuple(world),
            "radius_ft": radius_ft,
            "sun_score": self.sunlight_score_at(world),
            "grid_cell": (col, row),
            "can_place": self._grid_cell_is_empty(col, row),
        }

    def sunlight_score_at(self, world):
        if not self.model.sunlight_overlay:
            return None

        wx, wy = world
        cols = self.SUNLIGHT_GRID_COLS
        rows = self.SUNLIGHT_GRID_ROWS
        if self.model.width_ft <= 0 or self.model.height_ft <= 0:
            return None

        cell_w = self.model.width_ft / cols
        cell_h = self.model.height_ft / rows
        if cell_w <= 0 or cell_h <= 0:
            return None

        col = max(0, min(cols - 1, int(wx / cell_w)))
        row = max(0, min(rows - 1, int(wy / cell_h)))
        index = row * cols + col
        if index >= len(self.model.sunlight_overlay):
            return None
        return self.model.sunlight_overlay[index]["score"]

    def build_sunlight_overlay(self, plant=None):
        """Build an approximate seasonal sunlight grid from sun path and shadows."""
        try:
            date_start = datetime.date.fromisoformat(self.model.date_str)
            timezone_value = ZoneInfo(self.model.timezone_name)
        except (TypeError, ValueError, ZoneInfoNotFoundError):
            return []

        try:
            observer = Observer(latitude=float(self.model.lat), longitude=float(self.model.lon), elevation=0)
        except (TypeError, ValueError):
            return []

        temp_category = (plant or {}).get("tempCat", "warm")
        season_days = self.SEASON_LENGTH_DAYS.get(temp_category, 100)
        day_step = max(1, season_days // 6)

        samples = []
        for day_offset in range(0, season_days + 1, day_step):
            sample_date = date_start + datetime.timedelta(days=day_offset)
            for hour in self.SEASON_SAMPLE_HOURS:
                sample_dt = datetime.datetime.combine(
                    sample_date,
                    datetime.time(hour=hour),
                    tzinfo=timezone_value,
                )
                sun_elevation = elevation(observer, sample_dt)
                if sun_elevation <= 3:
                    continue
                samples.append((azimuth(observer, sample_dt), sun_elevation))

        if not samples:
            return []

        cols = self.SUNLIGHT_GRID_COLS
        rows = self.SUNLIGHT_GRID_ROWS
        cell_w = self.model.width_ft / cols
        cell_h = self.model.height_ft / rows
        overlay = []

        for row in range(rows):
            for col in range(cols):
                x_ft = col * cell_w
                y_ft = row * cell_h
                point = (x_ft + cell_w / 2.0, y_ft + cell_h / 2.0)
                lit_count = 0

                for sun_azimuth, sun_elevation in samples:
                    shadow_vector = self._shadow_vector_for(sun_azimuth, sun_elevation)
                    is_shadowed = any(
                        self._shape_casts_shadow_on_point(shape, point, shadow_vector)
                        for shape in self.model.shapes
                    )
                    if not is_shadowed:
                        lit_count += 1

                overlay.append(
                    {
                        "x": x_ft,
                        "y": y_ft,
                        "w": cell_w,
                        "h": cell_h,
                        "score": lit_count / len(samples),
                    }
                )

        return overlay

    def _shape_casts_shadow_on_point(self, shape, point, shadow_vector):
        if shape.get("height_ft", 0.0) <= 0:
            return False
        shadow = self.get_shadow_poly(shape, shadow_vector)
        if shadow is None:
            return False

        if isinstance(shadow, tuple) and shadow[0] == "ellipse":
            _kind, cx_ft, cy_ft, radius_ft = shadow
            return math.hypot(point[0] - cx_ft, point[1] - cy_ft) <= radius_ft
        return point_in_polygon(point[0], point[1], shadow)

    def get_shadow_poly(self, shape, shadow_vector):
        height_ft = shape.get("height_ft", 0.0)
        if height_ft <= 0 or shadow_vector is None:
            return None

        offset_x = shadow_vector[0] * height_ft
        offset_y = shadow_vector[1] * height_ft
        shape_type = shape["type"]

        if shape_type == "rect":
            x1, y1, x2, y2 = shape["geom"]
            base_points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        elif shape_type == "circle":
            cx, cy, radius = shape["geom"]
            return "ellipse", cx + offset_x, cy + offset_y, radius
        elif shape_type == "polygon":
            base_points = list(shape["geom"])
        elif shape_type == "strip":
            strip_polygon = strip_polygon_from_centerline(
                shape["geom"][0],
                shape["geom"][1],
                shape.get("width_ft", DEFAULT_STRIP_WIDTH_FT),
            )
            if not strip_polygon:
                return None
            base_points = list(strip_polygon)
        else:
            return None

        projected = [(x_ft + offset_x, y_ft + offset_y) for x_ft, y_ft in base_points]
        hull = self._convex_hull(base_points + projected)
        return hull if len(hull) >= 3 else None

    def _convex_hull(self, points):
        unique_points = sorted(set(points))
        if len(unique_points) <= 1:
            return unique_points

        def cross(origin, point_a, point_b):
            return (point_a[0] - origin[0]) * (point_b[1] - origin[1]) - (
                point_a[1] - origin[1]
            ) * (point_b[0] - origin[0])

        lower = []
        for point in unique_points:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
                lower.pop()
            lower.append(point)

        upper = []
        for point in reversed(unique_points):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
                upper.pop()
            upper.append(point)

        return lower[:-1] + upper[:-1]
