import os

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.stencilview import StencilView

from ..constants import COLOR_TEXT, COLOR_TEXT_DIM
from .styles import BTN_FLAT, style


MAP_SOURCE_PRESETS = {
    "street": {
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "cache_key": "osm_standard",
        "min_zoom": 0,
        "max_zoom": 19,
        "default_zoom": 19,
        "recenter_zoom": 18,
        "attribution": "© OpenStreetMap contributors",
    },
    "topo": {
        "url": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        "cache_key": "opentopomap",
        "min_zoom": 0,
        "max_zoom": 17,
        "default_zoom": 17,
        "recenter_zoom": 15,
        "attribution": "Map data: OpenStreetMap, SRTM | Style: OpenTopoMap",
        "subdomains": "abc",
    },
}


class TerrainMapPanel(BoxLayout):
    """Persistent terrain map centered on the garden location."""
    MAP_TAP_SLOP_PX = 10

    def __init__(self, model, controller, **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.controller = controller
        self.orientation = "vertical"
        self.spacing = 4
        self.padding = 4
        self.map_view = None
        self.map_container = None
        self.map_overlay_host = None
        self.overlay_widget = None
        self.marker = None
        self.garden_layer = None
        self.calibration_status = None
        self.calibrate_button = None
        self.y_axis_button = None
        self.anchor_lock_button = None
        self._placeholder_widget = None
        self._viewport_change_callback = None
        self._map_debug_enabled = os.environ.get("GARDEN_DEBUG_TERRAIN_MAP") == "1"
        self._map_stage = self._terrain_map_stage()
        self._map_source_key, self._map_source_config = self._terrain_map_source_config()
        self._map_interaction_enabled = False
        self._has_centered = False
        self._map_touch_ids = set()
        self._map_editor_touches = {}
        self._map_tap_candidates = {}
        self._calibration_geo_a = None
        self._calibration_step = None
        self._overlay_revision = 0

        self._debug(f"terrain: init start stage={self._map_stage}")
        self._build_ui()
        self._debug("terrain: init complete")
        self.model.bind(lat=self._sync_location, lon=self._sync_location)
        self.model.bind(
            width_ft=lambda *_args: self._sync_calibration_status(),
            map_overlay_is_calibrated=lambda *_args: self._sync_calibration_status(),
            map_overlay_anchor_locked=lambda *_args: self._sync_calibration_status(),
            map_overlay_calibration_mode=lambda *_args: self._sync_calibration_status(),
            map_overlay_rotation_deg=lambda *_args: self._sync_calibration_status(),
            map_overlay_y_axis_sign=lambda *_args: self._sync_calibration_status(),
        )
        Clock.schedule_once(lambda *_args: self.sync_location(force=True), 0)

    def _terrain_map_stage(self):
        stage = os.environ.get("GARDEN_TERRAIN_MAP_STAGE", "full").strip().casefold()
        allowed_stages = {"map_only", "marker_only", "layer_no_edit", "full"}
        if stage not in allowed_stages:
            print(
                f"terrain: unknown GARDEN_TERRAIN_MAP_STAGE={stage!r}; "
                "using 'full'"
            )
            return "full"
        return stage

    def _terrain_map_source_config(self):
        source_key = os.environ.get("GARDEN_TERRAIN_MAP_SOURCE", "street").strip().casefold()
        if source_key not in MAP_SOURCE_PRESETS:
            print(
                f"terrain: unknown GARDEN_TERRAIN_MAP_SOURCE={source_key!r}; "
                "using 'street'"
            )
            source_key = "street"
        return source_key, dict(MAP_SOURCE_PRESETS[source_key])

    def _default_map_zoom(self):
        if self._map_source_config is None:
            return 18
        return int(self._map_source_config.get("default_zoom", 18))

    def _recenter_zoom_floor(self):
        if self._map_source_config is None:
            return 15
        return int(self._map_source_config.get("recenter_zoom", 15))

    def _map_source_kwargs(self):
        if self._map_source_config is None:
            return {}
        return {
            key: value
            for key, value in self._map_source_config.items()
            if key not in {"default_zoom", "recenter_zoom"}
        }

    def _debug(self, message):
        if self._map_debug_enabled:
            print(message, flush=True)

    def _build_ui(self):
        btn_flat = style(BTN_FLAT, font_size="12sp")
        header = BoxLayout(size_hint_y=None, height=30, spacing=4)
        header.add_widget(
            Label(
                text="Terrain Map",
                color=COLOR_TEXT,
                bold=True,
                size_hint_x=0.25,
            )
        )
        self.y_axis_button = Button(text=self._y_axis_button_text(), size_hint_x=0.17, **btn_flat)
        self.y_axis_button.bind(on_release=lambda *_args: self.toggle_y_axis())
        header.add_widget(self.y_axis_button)
        self.anchor_lock_button = Button(text=self._anchor_lock_button_text(), size_hint_x=0.20, **btn_flat)
        self.anchor_lock_button.bind(on_release=lambda *_args: self.toggle_anchor_lock())
        header.add_widget(self.anchor_lock_button)
        self.calibrate_button = Button(text="Calibrate", size_hint_x=0.20, **btn_flat)
        self.calibrate_button.bind(on_release=lambda *_args: self.start_calibration())
        header.add_widget(self.calibrate_button)
        recenter_button = Button(text="Recenter", size_hint_x=0.18, **btn_flat)
        recenter_button.bind(on_release=lambda *_args: self.sync_location(force=True))
        header.add_widget(recenter_button)
        self.add_widget(header)
        self.calibration_status = Label(
            text=self._calibration_status_text(),
            color=COLOR_TEXT_DIM,
            font_size="10sp",
            size_hint_y=None,
            height=24,
        )
        self.add_widget(self.calibration_status)

        self.map_container = StencilView(size_hint=(1, 1))
        self.map_overlay_host = FloatLayout(size_hint=(1, 1))
        self.map_container.add_widget(self.map_overlay_host)
        self.map_container.bind(
            pos=lambda *_args: self._sync_map_bounds(),
            size=lambda *_args: self._sync_map_bounds(),
        )
        self.add_widget(self.map_container)

        if os.environ.get("GARDEN_DISABLE_TERRAIN_MAP") == "1":
            self._debug("terrain: disabled by GARDEN_DISABLE_TERRAIN_MAP=1")
            self._placeholder_widget = Label(
                text="Terrain map disabled by GARDEN_DISABLE_TERRAIN_MAP=1.",
                color=COLOR_TEXT_DIM,
                text_size=(260, None),
                halign="center",
                valign="middle",
                size_hint=(1, 1),
            )
            self.map_overlay_host.add_widget(self._placeholder_widget)
            self._sync_map_bounds()
            self.add_widget(
                Label(
                    text="Overlay calibration: A=(0,0), B=(garden width,0).",
                    color=COLOR_TEXT_DIM,
                    font_size="10sp",
                    size_hint_y=None,
                    height=24,
                )
            )
            return

        try:
            self._debug("terrain: importing MapView")
            from kivy_garden.mapview import MapMarker, MapSource, MapView
            from kivy_garden.mapview import downloader as mapview_downloader
            from .map_garden_layer import GardenMapLayer
        except ImportError:
            self._debug("terrain: MapView import failed")
            self._placeholder_widget = Label(
                text=(
                    "Install kivy_garden.mapview to show terrain tiles here.\n"
                    "Run pip install -r requirements.txt in the project venv."
                ),
                color=COLOR_TEXT_DIM,
                text_size=(260, None),
                halign="center",
                valign="middle",
                size_hint=(1, 1),
            )
            self.map_overlay_host.add_widget(self._placeholder_widget)
            self._sync_map_bounds()
            self.add_widget(
                Label(
                    text="Overlay calibration: A=(0,0), B=(garden width,0).",
                    color=COLOR_TEXT_DIM,
                    font_size="10sp",
                    size_hint_y=None,
                    height=24,
                )
            )
            return

        mapview_downloader.USER_AGENT = os.environ.get(
            "GARDEN_TERRAIN_MAP_USER_AGENT",
            "GardenSimulator/1.0 (+desktop garden planner)",
        )

        class TrackingMapView(MapView):
            def __init__(tracking_self, panel, **map_kwargs):
                tracking_self._terrain_panel = panel
                super().__init__(**map_kwargs)

            def on_touch_down(tracking_self, touch):
                if not tracking_self._terrain_panel._map_interaction_enabled:
                    return super().on_touch_down(touch)
                if tracking_self.collide_point(*touch.pos):
                    tracking_self._terrain_panel._map_touch_ids.add(touch.uid)
                    if tracking_self._terrain_panel._handle_calibration_touch(
                        tracking_self,
                        touch,
                    ):
                        return True
                    if tracking_self._terrain_panel._handle_editor_touch_down(
                        tracking_self,
                        touch,
                    ):
                        return True
                    tracking_self._terrain_panel._track_map_selection_candidate(
                        tracking_self,
                        touch,
                    )
                return super().on_touch_down(touch)

            def on_touch_move(tracking_self, touch):
                if not tracking_self._terrain_panel._map_interaction_enabled:
                    return super().on_touch_move(touch)
                if touch.grab_current is tracking_self and tracking_self._terrain_panel._handle_editor_touch_move(
                    tracking_self,
                    touch,
                ):
                    return True
                return super().on_touch_move(touch)

            def on_touch_up(tracking_self, touch):
                if not tracking_self._terrain_panel._map_interaction_enabled:
                    return super().on_touch_up(touch)
                try:
                    if touch.grab_current is tracking_self and tracking_self._terrain_panel._handle_editor_touch_up(
                        tracking_self,
                        touch,
                    ):
                        touch.ungrab(tracking_self)
                        return True
                    handled = super().on_touch_up(touch)
                    selected = tracking_self._terrain_panel._handle_map_selection_tap_up(
                        tracking_self,
                        touch,
                    )
                    return handled or selected
                finally:
                    tracking_self._terrain_panel._map_touch_ids.discard(touch.uid)

        self._debug("terrain: creating MapSource")
        terrain_source = MapSource(**self._map_source_kwargs())
        self._debug("terrain: creating MapView")
        self.map_view = TrackingMapView(
            self,
            lat=self.model.lat,
            lon=self.model.lon,
            zoom=self._default_map_zoom(),
            map_source=terrain_source,
            double_tap_zoom=True,
        )
        self._debug(f"terrain: MapView created {self.map_view!r}")
        self.map_view.bind(
            lat=lambda *_args: self._notify_overlay_changed(),
            lon=lambda *_args: self._notify_overlay_changed(),
            zoom=lambda *_args: self._notify_overlay_changed(),
            pos=lambda *_args: self._notify_overlay_changed(),
            size=lambda *_args: self._notify_overlay_changed(),
        )
        self.map_view._scatter.bind(transform=lambda *_args: self._notify_overlay_changed())
        self.map_overlay_host.add_widget(self.map_view)
        if self._map_stage in {"marker_only", "layer_no_edit", "full"}:
            self._debug("terrain: creating MapMarker")
            self.marker = MapMarker(lat=self.model.lat, lon=self.model.lon)
            self.map_view.add_marker(self.marker)
            self._debug("terrain: marker added")
        if self._map_stage in {"layer_no_edit", "full"}:
            self._debug("terrain: creating GardenMapLayer")
            self.garden_layer = GardenMapLayer(
                self.model,
                self.controller,
                render_model_shapes=False,
            )
            self._debug("terrain: adding layer")
            self.map_view.add_layer(self.garden_layer)
            self._debug("terrain: layer added")
        self._map_interaction_enabled = (
            self._map_stage == "full"
            and os.environ.get("GARDEN_DISABLE_MAP_EDITING") != "1"
        )
        if not self._map_interaction_enabled:
            self._debug("terrain: custom map editing disabled")
        self._sync_map_bounds()

        self.add_widget(
            Label(
                text="Overlay calibration: A=(0,0), B=(garden width,0).",
                color=COLOR_TEXT_DIM,
                font_size="10sp",
                size_hint_y=None,
                height=24,
            )
        )

    @property
    def overlay_revision(self):
        return getattr(self, "_overlay_revision", 0)

    def set_viewport_change_callback(self, callback):
        self._viewport_change_callback = callback
        if callback is not None:
            callback()

    def can_project_overlay(self):
        return self.map_view is not None and self.garden_layer is not None

    def zoom_label_text(self):
        if self.map_view is not None:
            return f"Map Zoom: {float(self.map_view.zoom):.0f}"
        return f"View Scale: {self.model.scale:.1f} px/ft"

    def attach_overlay(self, overlay_widget):
        if overlay_widget is None or self.map_overlay_host is None:
            return False
        if self.overlay_widget is not None and self.overlay_widget.parent is self.map_overlay_host:
            self.map_overlay_host.remove_widget(self.overlay_widget)
        self.overlay_widget = overlay_widget
        self.overlay_widget.size_hint = (None, None)
        self.map_overlay_host.add_widget(self.overlay_widget)
        self._sync_map_bounds()
        self._notify_overlay_changed()
        return True

    def _sync_map_bounds(self):
        if self.map_container is None or self.map_overlay_host is None:
            return
        self.map_overlay_host.pos = self.map_container.pos
        self.map_overlay_host.size = self.map_container.size
        if self.map_view is not None:
            self.map_view.pos = self.map_overlay_host.pos
            self.map_view.size = self.map_overlay_host.size
        if self.overlay_widget is not None:
            self.overlay_widget.pos = self.map_overlay_host.pos
            self.overlay_widget.size = self.map_overlay_host.size
        if self._placeholder_widget is not None:
            self._placeholder_widget.pos = self.map_overlay_host.pos
            self._placeholder_widget.size = self.map_overlay_host.size
            self._placeholder_widget.text_size = self.map_overlay_host.size
        self._debug(
            f"terrain: map bounds container={getattr(self.map_container, 'pos', None)}/{getattr(self.map_container, 'size', None)} "
            f"host={self.map_overlay_host.pos}/{self.map_overlay_host.size}"
        )
        if self.garden_layer is not None:
            self.garden_layer.reposition()
        self._notify_overlay_changed()

    def _notify_overlay_changed(self):
        self._overlay_revision = getattr(self, "_overlay_revision", 0) + 1
        overlay_widget = getattr(self, "overlay_widget", None)
        if overlay_widget is not None:
            try:
                overlay_widget._on_state_change()
            except Exception:
                pass
        callback = getattr(self, "_viewport_change_callback", None)
        if callback is not None:
            try:
                callback()
            except Exception:
                pass

    def garden_ft_to_overlay_xy(self, x_ft, y_ft):
        if not self.can_project_overlay():
            return None
        local_x, local_y = self.garden_layer.garden_ft_to_map_widget_xy(
            self.map_view,
            x_ft,
            y_ft,
        )
        origin_x, origin_y = self.map_view.pos
        return origin_x + local_x, origin_y + local_y

    def overlay_xy_to_garden_ft(self, x, y, clamp=True):
        if not self.can_project_overlay():
            return None
        return self.garden_layer.map_widget_xy_to_garden_ft(
            self.map_view,
            x,
            y,
            clamp=clamp,
        )

    def zoom_in_at_center(self):
        if self.map_view is not None:
            self.map_view.animated_diff_scale_at(1, *self.map_view.center)
            self._notify_overlay_changed()
            return True
        if self.overlay_widget is None:
            return False
        anchor_local = (self.overlay_widget.width / 2.0, self.overlay_widget.height / 2.0)
        self.controller.zoom_in(anchor_local)
        self._notify_overlay_changed()
        return True

    def zoom_out_at_center(self):
        if self.map_view is not None:
            self.map_view.animated_diff_scale_at(-1, *self.map_view.center)
            self._notify_overlay_changed()
            return True
        if self.overlay_widget is None:
            return False
        anchor_local = (self.overlay_widget.width / 2.0, self.overlay_widget.height / 2.0)
        self.controller.zoom_out(anchor_local)
        self._notify_overlay_changed()
        return True

    def _calibration_status_text(self):
        y_text = "+y right-handed from +x" if self.model.map_overlay_y_axis_sign >= 0.0 else "+y mirrored from +x"
        lock_text = "anchor locked" if self.model.map_overlay_anchor_locked else "anchor follows location"
        if self._calibration_step == "A":
            return "Calibration: tap map point A for garden local (0, 0)."
        if self._calibration_step == "B":
            return f"Calibration: tap map point B for local ({self.model.width_ft:.1f}, 0); {y_text}."
        if self.model.map_overlay_is_calibrated:
            return f"Calibrated: rotation {self.model.map_overlay_rotation_deg:.1f} deg, {y_text}; {lock_text}."
        return f"Not calibrated: origin=(0,0), +x east, {y_text}; {lock_text}."

    def _y_axis_button_text(self):
        return "Y +Up" if self.model.map_overlay_y_axis_sign >= 0.0 else "Y +Down"

    def _anchor_lock_button_text(self):
        return "Locked" if self.model.map_overlay_anchor_locked else "Follow"

    def _sync_calibration_status(self):
        if self.calibration_status is not None:
            self.calibration_status.text = self._calibration_status_text()
        if self.calibrate_button is not None:
            self.calibrate_button.text = "Cancel" if self._calibration_step else "Calibrate"
        if self.y_axis_button is not None:
            self.y_axis_button.text = self._y_axis_button_text()
        if self.anchor_lock_button is not None:
            self.anchor_lock_button.text = self._anchor_lock_button_text()

    def toggle_y_axis(self):
        self.controller.toggle_map_overlay_y_axis_sign()
        self._sync_calibration_status()
        if self.garden_layer is not None:
            self.garden_layer.reposition()
        self._notify_overlay_changed()
        return True

    def toggle_anchor_lock(self):
        self.controller.toggle_map_overlay_anchor_locked()
        self._sync_calibration_status()
        if self.garden_layer is not None:
            self.garden_layer.reposition()
        self._notify_overlay_changed()
        return True

    def start_calibration(self):
        if self.map_view is None:
            return False
        if self._calibration_step is not None:
            self._calibration_step = None
            self._calibration_geo_a = None
            self.controller.cancel_map_overlay_calibration()
            self._sync_calibration_status()
            return False
        self._calibration_step = "A"
        self._calibration_geo_a = None
        self.controller.begin_map_overlay_calibration()
        self._sync_calibration_status()
        return True

    def _handle_calibration_touch(self, map_view, touch):
        if self._calibration_step is None:
            return False
        if getattr(touch, "is_mouse_scrolling", False):
            return False

        local_x, local_y = map_view.to_widget(touch.x, touch.y, relative=True)
        coordinate = map_view.get_latlon_at(local_x, local_y, map_view.zoom)
        geo = (float(coordinate.lat), float(coordinate.lon))

        if self._calibration_step == "A":
            self._calibration_geo_a = geo
            self._calibration_step = "B"
            self._sync_calibration_status()
            return True

        success = self.controller.apply_map_overlay_calibration(
            self._calibration_geo_a,
            geo,
            local_a=(0.0, 0.0),
            local_b=(float(self.model.width_ft), 0.0),
        )
        self._calibration_step = None
        self._calibration_geo_a = None
        if not success:
            self.controller.cancel_map_overlay_calibration()
        self._sync_calibration_status()
        if success and self.garden_layer is not None:
            self.garden_layer.reposition()
        self._notify_overlay_changed()
        return True

    def _is_map_editor_active(self):
        return self.model.draw_mode is not None or (
            self.model.move_mode and self.model.selected_idx != -1
        )

    def _map_touch_to_world(self, map_view, touch, clamp=False):
        if self.garden_layer is None:
            return None
        return self.garden_layer.touch_to_garden_ft(map_view, touch, clamp=clamp)

    def _handle_editor_touch_down(self, map_view, touch):
        if not self._is_map_editor_active():
            return False
        if getattr(touch, "is_mouse_scrolling", False):
            return False
        world = self._map_touch_to_world(map_view, touch, clamp=True)
        if world is None:
            return False
        touch.grab(map_view)
        self._map_editor_touches[touch.uid] = {"start": touch.pos, "world": world}
        self.controller.on_mouse_press(world)
        return True

    def _handle_editor_touch_move(self, map_view, touch):
        if touch.uid not in self._map_editor_touches:
            return False
        world = self._map_touch_to_world(map_view, touch, clamp=True)
        if world is None:
            return True
        self._map_editor_touches[touch.uid]["world"] = world
        self.controller.on_mouse_drag(world)
        return True

    def _handle_editor_touch_up(self, map_view, touch):
        if touch.uid not in self._map_editor_touches:
            return False
        world = self._map_touch_to_world(map_view, touch, clamp=True)
        self._map_editor_touches.pop(touch.uid, None)
        if world is not None:
            self.controller.on_mouse_release(world)
        return True

    def _track_map_selection_candidate(self, map_view, touch):
        if self._is_map_editor_active() or getattr(touch, "is_mouse_scrolling", False):
            return False
        world = self._map_touch_to_world(map_view, touch, clamp=False)
        if world is None:
            return False
        self._map_tap_candidates[touch.uid] = {
            "start": touch.pos,
            "idx": self.controller.shape_index_at_world(world),
        }
        return True

    def _handle_map_selection_tap_up(self, map_view, touch):
        candidate = self._map_tap_candidates.pop(touch.uid, None)
        if candidate is None:
            return False
        moved_px = (
            (touch.x - candidate["start"][0]) ** 2
            + (touch.y - candidate["start"][1]) ** 2
        ) ** 0.5
        if moved_px > self.MAP_TAP_SLOP_PX:
            return False

        world = self._map_touch_to_world(map_view, touch, clamp=False)
        if world is None:
            return False
        end_idx = self.controller.shape_index_at_world(world)
        if end_idx == candidate["idx"] and end_idx != -1:
            self.controller.select_shape(end_idx)
        elif end_idx == -1:
            self.controller.deselect()
        else:
            return False
        return True

    def sync_location(self, force=False):
        self._sync_location(force=force)

    def _sync_location(self, *_args, force=False):
        if self.map_view is None:
            return

        lat = float(self.model.lat)
        lon = float(self.model.lon)
        if self.marker is not None:
            self.marker.lat = lat
            self.marker.lon = lon
        if self.garden_layer is not None:
            self.garden_layer.reposition()

        should_center = force or not self._has_centered or not self._map_touch_ids
        if not should_center:
            self._notify_overlay_changed()
            return

        self.map_view.lat = lat
        self.map_view.lon = lon
        if force or self.map_view.zoom < self._recenter_zoom_floor():
            self.map_view.zoom = max(self._recenter_zoom_floor(), self.map_view.zoom)
        self.map_view.center_on(lat, lon)
        self._has_centered = True
        self._notify_overlay_changed()
