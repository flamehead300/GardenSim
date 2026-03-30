import datetime
import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from astral import Observer
from astral.sun import azimuth, elevation

from kivy.app import App
from kivy.event import EventDispatcher
from kivy.properties import BooleanProperty

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
    MIN_STRIP_LENGTH_FT,
    MIN_STRIP_WIDTH_FT,
)
from .model import GardenModel
from .commands import (
    AddShapeCommand, DeleteShapeCommand, MoveShapeCommand,
    ModifyPropertyCommand, CommandHistory,
)
from .storage import StorageManager


class GardenController(EventDispatcher):
    """Handles business logic, user input translation, and model mutation."""
    can_undo = BooleanProperty(False)
    can_redo = BooleanProperty(False)

    __events__ = ('on_alert',)

    def __init__(self, model: GardenModel, **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.command_history = CommandHistory(self)
        self._move_command_before = None
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
        self.model.shapes = [clone_shape(shape) for shape in loaded_model.shapes]
        self.model.offset_x = 0.0
        self.model.offset_y = 0.0
        self.model.snap_preview = None
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
        self.model.timezone_name = timezone_name
        self.model.date_str = date_str
        self.model.time_str = time_str
        self.model.time_minutes = minutes_from_time_str(time_str)

        dt_value = datetime.datetime.combine(date_value, time_value, tzinfo=timezone_value)
        observer = Observer(latitude=lat, longitude=lon, elevation=0)
        self.model.sun_azimuth = azimuth(observer, dt_value)
        self.model.sun_elevation = elevation(observer, dt_value)
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

    def cancel_drawing(self):
        self._clear_preview()
        self.model.poly_points = []
        self.model.drag_start = None
        self.model.draw_mode = None

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

    def _clear_preview(self):
        self.model.drag_rect = None
        self.model.drag_circle = None
        self.model.drag_strip = None
        self.model.snap_preview = None

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
        self.model.shapes = insert_shape(self.model.shapes, idx, clone_shape(shape))
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
        self.model.shapes = replace_shape(self.model.shapes, idx, clone_shape(shape))

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
        self.model.shapes = replace_shape(self.model.shapes, idx, new_shape)

    def on_mouse_press(self, world):
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

    def get_shadow_vector(self):
        if self.model.sun_elevation <= 0:
            return None
        length = 1.0 / math.tan(math.radians(self.model.sun_elevation))
        azimuth_rad = math.radians(self.model.sun_azimuth)
        return -length * math.sin(azimuth_rad), -length * math.cos(azimuth_rad)

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
