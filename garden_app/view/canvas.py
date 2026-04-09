import logging
import math

from kivy.clock import Clock

try:
    from kivy.core.text import CoreLabel
except ImportError:
    from kivy.core.text import Label as CoreLabel

from kivy.graphics import Color, Ellipse, InstructionGroup, Line, Mesh, Rectangle
from kivy.uix.widget import Widget

from ..utils import (
    hex_to_rgba,
    triangulate_polygon_ear_clipping,
    validate_polygon_points,
)
from ..constants import (
    COLOR_PANEL, COLOR_CANVAS, COLOR_GRID, COLOR_GRID_SNAP,
    COLOR_SHADOW, COLOR_PREVIEW_FILL, COLOR_PREVIEW_OUT,
    COLOR_SELECT, COLOR_SNAP_PREVIEW, COLOR_SUN, COLOR_SUN_ARROW,
    COLOR_SUN_BELOW, COLOR_TEXT, COLOR_LABEL_TEXT,
    CATEGORIES, DEFAULT_CATEGORY,
)
from .plant_icons import icon_key_for_plant, texture_for_icon
from .canvas_renderer import shape_render_plan

LOGGER = logging.getLogger(__name__)


class GardenCanvas(Widget):
    """Canvas widget that renders the garden and proxies touch input."""
    TAP_SLOP_PX = 10

    def __init__(
        self,
        model,
        controller,
        transparent_background=False,
        map_panel=None,
        show_grid_overlay=False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.model = model
        self.controller = controller
        self.transparent_background = bool(transparent_background)
        self.map_panel = map_panel
        self.show_grid_overlay = bool(show_grid_overlay)
        self.size_hint = (1, 1)
        self._active_touches = {}
        self._grabbed_touch_modes = {}
        self._logged_polygon_fill_failures = set()
        self._redraw_event = None
        self._text_texture_cache = {}
        self._static_canvas_signature = None
        self._static_canvas_group = None

        self.bind(pos=self._on_state_change, size=self._on_state_change)

        # Observe model state to trigger redraws seamlessly
        self.model.bind(
            width_ft=self._on_state_change,
            height_ft=self._on_state_change,
            scale=self._on_state_change,
            offset_x=self._on_state_change,
            offset_y=self._on_state_change,
            shapes=self._on_state_change,
            draw_mode=self._on_state_change,
            drag_rect=self._on_state_change,
            drag_circle=self._on_state_change,
            drag_strip=self._on_state_change,
            poly_points=self._on_state_change,
            snap_to_grid=self._on_state_change,
            grid_size=self._on_state_change,
            snap_preview=self._on_state_change,
            selected_idx=self._on_state_change,
            sun_azimuth=self._on_state_change,
            sun_elevation=self._on_state_change,
            pending_plant=self._on_state_change,
            plant_preview=self._on_state_change,
            sunlight_overlay=self._on_state_change,
        )

    def _on_state_change(self, *_args):
        if self._redraw_event is None:
            self._redraw_event = Clock.schedule_once(self._redraw_from_clock, 0)

    def _redraw_from_clock(self, *_args):
        self._redraw_event = None
        self.redraw()

    def _is_editing_gesture(self):
        return self.model.draw_mode is not None or self.model.move_mode

    def _use_overlay_projection(self):
        return (
            self.map_panel is not None
            and getattr(self.map_panel, "can_project_overlay", lambda: False)()
        )

    def _pixels_per_ft_at(self, x_ft, y_ft):
        if not self._use_overlay_projection():
            return float(self.model.scale)

        x_candidates = [
            min(float(self.model.width_ft), float(x_ft) + 1.0),
            max(0.0, float(x_ft) - 1.0),
        ]
        y_candidates = [
            min(float(self.model.height_ft), float(y_ft) + 1.0),
            max(0.0, float(y_ft) - 1.0),
        ]
        origin_x, origin_y = self.world_to_canvas(x_ft, y_ft)
        scales = []
        for other_x in x_candidates:
            if abs(other_x - float(x_ft)) <= 1e-6:
                continue
            px, py = self.world_to_canvas(other_x, y_ft)
            scales.append(math.hypot(px - origin_x, py - origin_y) / abs(other_x - float(x_ft)))
            break
        for other_y in y_candidates:
            if abs(other_y - float(y_ft)) <= 1e-6:
                continue
            px, py = self.world_to_canvas(x_ft, other_y)
            scales.append(math.hypot(px - origin_x, py - origin_y) / abs(other_y - float(y_ft)))
            break
        if not scales:
            return float(self.model.scale)
        return sum(scales) / len(scales)

    def _radius_px_at(self, x_ft, y_ft, radius_ft):
        if radius_ft <= 0:
            return 0.0
        if not self._use_overlay_projection():
            return float(radius_ft) * float(self.model.scale)
        center_x, center_y = self.world_to_canvas(x_ft, y_ft)
        edge_points = []
        if x_ft + radius_ft <= float(self.model.width_ft):
            edge_points.append(self.world_to_canvas(x_ft + radius_ft, y_ft))
        elif x_ft - radius_ft >= 0.0:
            edge_points.append(self.world_to_canvas(x_ft - radius_ft, y_ft))
        if y_ft + radius_ft <= float(self.model.height_ft):
            edge_points.append(self.world_to_canvas(x_ft, y_ft + radius_ft))
        elif y_ft - radius_ft >= 0.0:
            edge_points.append(self.world_to_canvas(x_ft, y_ft - radius_ft))
        if not edge_points:
            return float(radius_ft) * float(self.model.scale)
        distances = [
            math.hypot(px - center_x, py - center_y)
            for px, py in edge_points
        ]
        return sum(distances) / len(distances)

    def _rect_points(self, x_ft, y_ft, w_ft, h_ft):
        return [
            (x_ft, y_ft),
            (x_ft + w_ft, y_ft),
            (x_ft + w_ft, y_ft + h_ft),
            (x_ft, y_ft + h_ft),
        ]

    def world_to_canvas(self, x_ft, y_ft):
        if self._use_overlay_projection():
            overlay_xy = self.map_panel.garden_ft_to_overlay_xy(x_ft, y_ft)
            if overlay_xy is not None:
                return overlay_xy
        scale = self.model.scale
        return (
            self.x + self.model.offset_x + x_ft * scale,
            self.y + self.model.offset_y + y_ft * scale,
        )

    def canvas_to_world(self, cx, cy):
        if self._use_overlay_projection():
            world = self.map_panel.overlay_xy_to_garden_ft(
                self.x + float(cx),
                self.y + float(cy),
                clamp=True,
            )
            if world is not None:
                return world
        scale = self.model.scale
        x_ft = (cx - self.model.offset_x) / scale
        y_ft = (cy - self.model.offset_y) / scale
        x_ft = max(0.0, min(x_ft, self.model.width_ft))
        y_ft = max(0.0, min(y_ft, self.model.height_ft))
        return x_ft, y_ft

    def _world_from_touch(self, touch):
        # Standalone mode uses local canvas coordinates. Overlay mode keeps the
        # same API and lets canvas_to_world convert back to map/widget space.
        local_x = touch.x - self.x
        local_y = touch.y - self.y
        local_x = max(0.0, min(local_x, self.width))
        local_y = max(0.0, min(local_y, self.height))
        return self.canvas_to_world(local_x, local_y)

    def screen_to_grid_cell(self, x, y):
        """Snap screen coordinates to the nearest garden grid col/row."""
        local_x = max(0.0, min(float(x) - self.x, self.width))
        local_y = max(0.0, min(float(y) - self.y, self.height))
        return self.controller.world_to_grid_cell(
            self.canvas_to_world(local_x, local_y)
        )

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)

        overlay_mode = self._use_overlay_projection()
        editing = self._is_editing_gesture()

        if getattr(touch, "is_mouse_scrolling", False):
            if overlay_mode:
                return super().on_touch_down(touch)
            anchor_local = (touch.x - self.x, touch.y - self.y)
            if getattr(touch, "button", "") == "scrollup":
                self.controller.zoom_in(anchor_local)
            else:
                self.controller.zoom_out(anchor_local)
            return True

        if overlay_mode and not editing:
            return super().on_touch_down(touch)

        if getattr(touch, "button", "") == "middle":
            if overlay_mode:
                return super().on_touch_down(touch)
            touch.grab(self)
            self._grabbed_touch_modes[touch.uid] = "pan"
            self._begin_navigation_touch(touch)
            return True

        if editing:
            touch.grab(self)
            self._grabbed_touch_modes[touch.uid] = "edit"
            self.controller.on_mouse_press(self._world_from_touch(touch))
            return True

        touch.grab(self)
        self._grabbed_touch_modes[touch.uid] = "pan"
        self._begin_navigation_touch(touch)
        return True

    def _begin_navigation_touch(self, touch):
        touch_id = touch.uid
        self._active_touches[touch_id] = {
            "start": touch.pos,
            "prev": touch.pos,
            "pos": touch.pos,
            "had_multitouch": False,
        }
        if len(self._active_touches) > 1:
            for entry in self._active_touches.values():
                entry["had_multitouch"] = True

    def _update_navigation_touch(self, touch):
        touch_id = touch.uid
        if touch_id not in self._active_touches:
            return False

        entry = self._active_touches[touch_id]
        entry["prev"] = entry["pos"]
        entry["pos"] = touch.pos

        if len(self._active_touches) == 1:
            dx = entry["pos"][0] - entry["prev"][0]
            dy = entry["pos"][1] - entry["prev"][1]
            if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                self.controller.pan_view(dx, dy)
            return True

        if len(self._active_touches) == 2:
            first, second = list(self._active_touches.values())
            prev_mid_x = (first["prev"][0] + second["prev"][0]) / 2.0
            prev_mid_y = (first["prev"][1] + second["prev"][1]) / 2.0
            curr_mid_x = (first["pos"][0] + second["pos"][0]) / 2.0
            curr_mid_y = (first["pos"][1] + second["pos"][1]) / 2.0
            self.controller.pan_view(curr_mid_x - prev_mid_x, curr_mid_y - prev_mid_y)

            prev_dist = math.hypot(
                first["prev"][0] - second["prev"][0],
                first["prev"][1] - second["prev"][1],
            )
            curr_dist = math.hypot(
                first["pos"][0] - second["pos"][0],
                first["pos"][1] - second["pos"][1],
            )
            if prev_dist > 1e-6 and curr_dist > 1e-6:
                self.controller.zoom_view(
                    curr_dist / prev_dist,
                    anchor_local=(curr_mid_x - self.x, curr_mid_y - self.y),
                )
            return True

        return True

    def _end_navigation_touch(self, touch):
        entry = self._active_touches.pop(touch.uid, None)
        if entry is None:
            return False

        if len(self._active_touches) == 1:
            remaining_entry = next(iter(self._active_touches.values()))
            remaining_entry["prev"] = remaining_entry["pos"]

        if entry["had_multitouch"]:
            return True

        dx = touch.x - entry["start"][0]
        dy = touch.y - entry["start"][1]
        moved = math.hypot(dx, dy)
        if moved <= self.TAP_SLOP_PX and self.collide_point(*touch.pos):
            self.controller.on_mouse_press(self._world_from_touch(touch))
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            mode = self._grabbed_touch_modes.get(touch.uid)
            if mode == "edit":
                self.controller.on_mouse_drag(self._world_from_touch(touch))
                return True
            if mode == "pan":
                return self._update_navigation_touch(touch)

        if self._use_overlay_projection():
            return super().on_touch_move(touch)

        if touch.uid in self._active_touches:
            return self._update_navigation_touch(touch)
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            mode = self._grabbed_touch_modes.pop(touch.uid, None)
            touch.ungrab(self)
            if mode == "edit":
                self.controller.on_mouse_release(self._world_from_touch(touch))
                return True
            if mode == "pan":
                return self._end_navigation_touch(touch)

        if self._use_overlay_projection():
            return super().on_touch_up(touch)

        if touch.uid in self._active_touches:
            return self._end_navigation_touch(touch)
        return super().on_touch_up(touch)

    def _text_texture(self, text, font_size, color):
        text_value = str(text)
        color_key = tuple(round(float(component), 4) for component in color)
        key = (text_value, str(font_size), color_key)
        texture = self._text_texture_cache.get(key)
        if texture is not None:
            return texture

        if len(self._text_texture_cache) > 512:
            self._text_texture_cache.clear()

        label = CoreLabel(text=text_value, font_size=font_size, color=color)
        label.refresh()
        texture = label.texture
        self._text_texture_cache[key] = texture
        return texture

    def _add_text_px(self, target, px, py, text, anchor="center", font_size=12, color=COLOR_TEXT):
        if not text:
            return
        texture = self._text_texture(text, font_size, color)
        width, height = texture.size

        if anchor == "center":
            px -= width / 2.0
            py -= height / 2.0
        elif anchor == "south":
            px -= width / 2.0
        elif anchor == "west":
            py -= height / 2.0

        target.add(Color(1, 1, 1, 1))
        target.add(Rectangle(texture=texture, pos=(px, py), size=(width, height)))

    def _draw_text(self, x_ft, y_ft, text, anchor="center", font_size=12, color=COLOR_TEXT):
        px, py = self.world_to_canvas(x_ft, y_ft)
        self._add_text_px(self.canvas, px, py, text, anchor=anchor, font_size=font_size, color=color)

    def _add_plant_icon_px(self, target, px, py, plant, size_px):
        texture = texture_for_icon(plant)
        if texture is None:
            fallback = icon_key_for_plant(plant)[:3].upper()
            self._add_text_px(
                target,
                px,
                py,
                fallback,
                anchor="center",
                font_size=9,
                color=hex_to_rgba("#E8F5E8"),
            )
            return False

        half_size = size_px / 2.0
        target.add(Color(1, 1, 1, 1))
        target.add(
            Rectangle(
                texture=texture,
                pos=(px - half_size, py - half_size),
                size=(size_px, size_px),
            )
        )
        return True

    def _draw_plant_icon_px(self, px, py, plant, size_px):
        return self._add_plant_icon_px(self.canvas, px, py, plant, size_px)

    def _growth_state_color(self, state):
        return {
            "SEED": hex_to_rgba("#8D6E63", 0.92),
            "SPROUT": hex_to_rgba("#9CCC65", 0.92),
            "MATURE": hex_to_rgba("#2E7D32", 0.92),
            "FRUITING": hex_to_rgba("#EF5350", 0.94),
            "DEAD": hex_to_rgba("#6D4C41", 0.88),
        }.get(str(state or "SEED").upper(), hex_to_rgba("#8D6E63", 0.92))

    def _growth_icon_scale(self, state):
        return {
            "SEED": 0.45,
            "SPROUT": 0.65,
            "MATURE": 0.85,
            "FRUITING": 1.0,
            "DEAD": 0.72,
        }.get(str(state or "SEED").upper(), 0.45)

    def _plant_progress(self, plant):
        try:
            progress = float((plant or {}).get("growth_progress", 0.0))
        except (TypeError, ValueError):
            progress = 0.0
        return max(0.0, min(100.0, progress))

    def _add_growth_stage_px(self, target, px, py, plant, radius_px):
        state = str((plant or {}).get("growth_state", "SEED")).upper()
        progress = self._plant_progress(plant)
        color = self._growth_state_color(state)
        radius = max(5.0, radius_px)
        progress_degrees = 360.0 * (progress / 100.0)

        target.add(Color(0.05, 0.11, 0.05, 0.42))
        target.add(Ellipse(pos=(px - radius, py - radius), size=(radius * 2.0, radius * 2.0)))
        target.add(Color(*color))
        target.add(Line(circle=(px, py, radius), width=2))
        if progress_degrees > 0.0:
            target.add(Color(*hex_to_rgba("#FDD835", 0.95)))
            target.add(Line(circle=(px, py, radius + 3.0, 0.0, progress_degrees), width=2))

        if state == "SEED":
            seed_radius = max(3.0, radius * 0.20)
            target.add(Color(*color))
            target.add(Ellipse(pos=(px - seed_radius, py - seed_radius), size=(seed_radius * 2.0, seed_radius * 2.0)))
        elif state == "SPROUT":
            target.add(Color(*color))
            target.add(Line(points=[px, py - radius * 0.35, px, py + radius * 0.35], width=2))
            target.add(Line(points=[px, py, px - radius * 0.28, py + radius * 0.18], width=2))
            target.add(Line(points=[px, py, px + radius * 0.28, py + radius * 0.18], width=2))
        elif state == "DEAD":
            target.add(Color(*hex_to_rgba("#2E1A12", 0.95)))
            target.add(Line(points=[px - radius * 0.35, py - radius * 0.35, px + radius * 0.35, py + radius * 0.35], width=2))
            target.add(Line(points=[px - radius * 0.35, py + radius * 0.35, px + radius * 0.35, py - radius * 0.35], width=2))

    def _polygon_failure_key(self, points):
        return tuple((round(x_ft, 6), round(y_ft, 6)) for x_ft, y_ft in points)

    def _log_polygon_fill_failure(self, points, message):
        key = self._polygon_failure_key(points)
        if key in self._logged_polygon_fill_failures:
            return
        LOGGER.warning("Polygon fill fallback: %s | points=%s", message, key)
        self._logged_polygon_fill_failures.add(key)

    def _prepare_polygon_fill(self, points, log_failure=True):
        is_valid, polygon_points, message = validate_polygon_points(points)
        if not is_valid:
            if log_failure:
                self._log_polygon_fill_failure(polygon_points or points, message)
            return False, polygon_points, None

        triangles = triangulate_polygon_ear_clipping(polygon_points)
        if triangles is None:
            if log_failure:
                self._log_polygon_fill_failure(
                    polygon_points,
                    "Ear clipping failed for a simple polygon.",
                )
            return True, polygon_points, None

        self._logged_polygon_fill_failures.discard(
            self._polygon_failure_key(polygon_points)
        )
        return True, polygon_points, triangles

    def _draw_polygon_fill(self, points, color, triangles=None, log_failure=True):
        if triangles is None:
            _is_valid, _polygon_points, triangles = self._prepare_polygon_fill(
                points,
                log_failure=log_failure,
            )
        if not triangles:
            return False

        vertices = []
        indices = []
        vertex_index = 0
        for triangle in triangles:
            for x_ft, y_ft in triangle:
                px, py = self.world_to_canvas(x_ft, y_ft)
                vertices.extend([px, py, 0, 0])
                indices.append(vertex_index)
                vertex_index += 1

        with self.canvas:
            Color(*color)
            Mesh(vertices=vertices, indices=indices, mode="triangles")
        return True

    def _draw_polygon_outline(self, points, color, width=1):
        if len(points) < 2:
            return
        line_points = []
        for x_ft, y_ft in points:
            px, py = self.world_to_canvas(x_ft, y_ft)
            line_points.extend([px, py])
        with self.canvas:
            Color(*color)
            Line(points=line_points, width=width, close=True)

    def _draw_segment(self, point_a, point_b, color, width=1):
        x1_px, y1_px = self.world_to_canvas(point_a[0], point_a[1])
        x2_px, y2_px = self.world_to_canvas(point_b[0], point_b[1])
        with self.canvas:
            Color(*color)
            Line(points=[x1_px, y1_px, x2_px, y2_px], width=width)

    def _draw_polyline_points(self, points, color, width=1):
        line_points = []
        for x_ft, y_ft in points:
            px, py = self.world_to_canvas(x_ft, y_ft)
            line_points.extend([px, py])
        if len(line_points) < 4:
            return
        with self.canvas:
            Color(*color)
            Line(points=line_points, width=width)

    def _sunlight_color(self, score):
        score = max(0.0, min(1.0, float(score)))
        if score < 0.45:
            return 0.18, 0.35, 0.95, 0.24
        if score < 0.70:
            return 1.0, 0.82, 0.18, 0.24
        return 0.1, 0.85, 0.28, 0.24

    def _draw_sunlight_overlay(self):
        if not self.model.sunlight_overlay:
            return
        for cell in self.model.sunlight_overlay:
            if self._use_overlay_projection():
                self._draw_polygon_fill(
                    self._rect_points(cell["x"], cell["y"], cell["w"], cell["h"]),
                    self._sunlight_color(cell["score"]),
                    log_failure=False,
                )
                continue
            x_px, y_px = self.world_to_canvas(cell["x"], cell["y"])
            w_px = cell["w"] * self.model.scale
            h_px = cell["h"] * self.model.scale
            with self.canvas:
                Color(*self._sunlight_color(cell["score"]))
                Rectangle(pos=(x_px, y_px), size=(w_px, h_px))

    def _static_signature(self):
        if self._use_overlay_projection():
            map_view = getattr(self.map_panel, "map_view", None)
            return (
                round(float(self.x), 3),
                round(float(self.y), 3),
                round(float(self.width), 3),
                round(float(self.height), 3),
                round(float(self.model.width_ft), 3),
                round(float(self.model.height_ft), 3),
                bool(self.transparent_background),
                bool(self.show_grid_overlay),
                bool(self.model.snap_to_grid),
                round(float(self.model.grid_size), 3),
                int(getattr(self.map_panel, "overlay_revision", 0)),
                round(float(getattr(map_view, "zoom", 0.0)), 3) if map_view is not None else 0.0,
                round(float(getattr(map_view, "lat", 0.0)), 6) if map_view is not None else 0.0,
                round(float(getattr(map_view, "lon", 0.0)), 6) if map_view is not None else 0.0,
            )
        return (
            round(float(self.x), 3),
            round(float(self.y), 3),
            round(float(self.width), 3),
            round(float(self.height), 3),
            round(float(self.model.width_ft), 3),
            round(float(self.model.height_ft), 3),
            round(float(self.model.scale), 3),
            round(float(self.model.offset_x), 3),
            round(float(self.model.offset_y), 3),
            bool(self.model.snap_to_grid),
            round(float(self.model.grid_size), 3),
        )

    def _build_static_canvas_group(self):
        group = InstructionGroup()
        w_ft = self.model.width_ft
        h_ft = self.model.height_ft
        viewport_x = self.x
        viewport_y = self.y
        viewport_w = self.width
        viewport_h = self.height
        draw_grid_overlay = not self.transparent_background or self.show_grid_overlay

        if not self.transparent_background:
            scale = self.model.scale
            world_x = self.x + self.model.offset_x
            world_y = self.y + self.model.offset_y
            world_w = w_ft * scale
            world_h = h_ft * scale
            group.add(Color(*COLOR_PANEL))
            group.add(Rectangle(pos=(viewport_x, viewport_y), size=(viewport_w, viewport_h)))
            group.add(Color(*COLOR_CANVAS))
            group.add(Rectangle(pos=(world_x, world_y), size=(world_w, world_h)))
        elif not draw_grid_overlay:
            return group

        if self._use_overlay_projection():
            if draw_grid_overlay:
                for x_ft in range(0, int(w_ft) + 1):
                    x1_px, y1_px = self.world_to_canvas(x_ft, 0)
                    x2_px, y2_px = self.world_to_canvas(x_ft, h_ft)
                    group.add(Color(*COLOR_GRID))
                    group.add(Line(points=[x1_px, y1_px, x2_px, y2_px], width=1))
                for y_ft in range(0, int(h_ft) + 1):
                    x1_px, y1_px = self.world_to_canvas(0, y_ft)
                    x2_px, y2_px = self.world_to_canvas(w_ft, y_ft)
                    group.add(Color(*COLOR_GRID))
                    group.add(Line(points=[x1_px, y1_px, x2_px, y2_px], width=1))

                if self.model.snap_to_grid and self.model.grid_size > 0:
                    snap_step = self.model.grid_size
                    x_ft = 0.0
                    while x_ft <= w_ft + 1e-9:
                        x1_px, y1_px = self.world_to_canvas(x_ft, 0)
                        x2_px, y2_px = self.world_to_canvas(x_ft, h_ft)
                        group.add(Color(*COLOR_GRID_SNAP))
                        group.add(Line(points=[x1_px, y1_px, x2_px, y2_px], width=1))
                        x_ft += snap_step

                    y_ft = 0.0
                    while y_ft <= h_ft + 1e-9:
                        x1_px, y1_px = self.world_to_canvas(0, y_ft)
                        x2_px, y2_px = self.world_to_canvas(w_ft, y_ft)
                        group.add(Color(*COLOR_GRID_SNAP))
                        group.add(Line(points=[x1_px, y1_px, x2_px, y2_px], width=1))
                        y_ft += snap_step
            return group

        scale = self.model.scale
        world_x = self.x + self.model.offset_x
        world_y = self.y + self.model.offset_y
        world_w = w_ft * scale
        world_h = h_ft * scale

        if draw_grid_overlay:
            for x_ft in range(0, int(w_ft) + 1):
                x_px, _ = self.world_to_canvas(x_ft, 0)
                group.add(Color(*COLOR_GRID))
                group.add(Line(points=[x_px, world_y, x_px, world_y + world_h], width=1))
            for y_ft in range(0, int(h_ft) + 1):
                _, y_px = self.world_to_canvas(0, y_ft)
                group.add(Color(*COLOR_GRID))
                group.add(Line(points=[world_x, y_px, world_x + world_w, y_px], width=1))

            if self.model.snap_to_grid and self.model.grid_size > 0:
                snap_step = self.model.grid_size
                x_ft = 0.0
                while x_ft <= w_ft + 1e-9:
                    x_px, _ = self.world_to_canvas(x_ft, 0)
                    group.add(Color(*COLOR_GRID_SNAP))
                    group.add(Line(points=[x_px, world_y, x_px, world_y + world_h], width=1))
                    x_ft += snap_step

                y_ft = 0.0
                while y_ft <= h_ft + 1e-9:
                    _, y_px = self.world_to_canvas(0, y_ft)
                    group.add(Color(*COLOR_GRID_SNAP))
                    group.add(Line(points=[world_x, y_px, world_x + world_w, y_px], width=1))
                    y_ft += snap_step

        if not self.transparent_background:
            step = 5
            if scale < 2:
                step = 20
            elif scale < 5:
                step = 10

            for x_ft in range(0, int(w_ft) + 1, step):
                px, py = self.world_to_canvas(x_ft, 0.2)
                self._add_text_px(
                    group,
                    px,
                    py,
                    str(x_ft),
                    anchor="south",
                    font_size=8,
                    color=COLOR_LABEL_TEXT,
                )
            for y_ft in range(0, int(h_ft) + 1, step):
                px, py = self.world_to_canvas(0.2, y_ft)
                self._add_text_px(
                    group,
                    px,
                    py,
                    str(y_ft),
                    anchor="west",
                    font_size=8,
                    color=COLOR_LABEL_TEXT,
                )

        return group

    def _add_static_canvas(self):
        signature = self._static_signature()
        if (
            self._static_canvas_group is None
            or self._static_canvas_signature != signature
        ):
            self._static_canvas_group = self._build_static_canvas_group()
            self._static_canvas_signature = signature
        self.canvas.add(self._static_canvas_group)

    def _draw_plant_preview(self):
        preview = self.model.plant_preview
        if not preview:
            return

        center_x, center_y = preview["center"]
        radius_ft = preview["radius_ft"]
        center_x_px, center_y_px = self.world_to_canvas(center_x, center_y)
        radius_px = self._radius_px_at(center_x, center_y, radius_ft)
        can_place = preview.get("can_place", True)
        fill_color = (0.36, 0.98, 0.48, 0.28) if can_place else (1.0, 0.18, 0.12, 0.32)
        outline_color = (0.05, 0.95, 0.25, 0.92) if can_place else (1.0, 0.12, 0.08, 0.95)
        with self.canvas:
            Color(*fill_color)
            Ellipse(
                pos=(center_x_px - radius_px, center_y_px - radius_px),
                size=(radius_px * 2.0, radius_px * 2.0),
            )
            Color(*outline_color)
            Line(circle=(center_x_px, center_y_px, radius_px), width=2)

        plant = preview.get("plant", {})
        sun_score = preview.get("sun_score")
        score_text = "sun n/a" if sun_score is None else f"{sun_score * 100:.0f}% sun"
        grid_text = f"cell {preview['grid_cell']}" if preview.get("grid_cell") is not None else "cell n/a"
        status_text = "ok" if can_place else "occupied"
        name = plant.get("name", "Plant").split(" - ", 1)[0]
        state = plant.get("growth_state", "SEED")
        progress = self._plant_progress(plant)
        icon_size_px = max(22, min(44, radius_px * 0.9 if radius_px > 0 else 28))
        self._add_growth_stage_px(self.canvas, center_x_px, center_y_px + 10, plant, max(10, icon_size_px * 0.58))
        self._draw_plant_icon_px(
            center_x_px,
            center_y_px + 10,
            plant,
            icon_size_px * self._growth_icon_scale(state),
        )
        self._add_text_px(
            self.canvas,
            center_x_px,
            center_y_px - icon_size_px / 2.0 - 12,
            f"{name}\n{state} {progress:.0f}% | {radius_ft:.1f} ft roots | {score_text}\n{grid_text} | {status_text}",
            font_size=10,
            color=hex_to_rgba("#E8F5E8"),
        )

    def redraw(self):
        if self._redraw_event is not None:
            self._redraw_event.cancel()
            self._redraw_event = None

        self.canvas.clear()
        if self.width <= 0 or self.height <= 0:
            return

        w_ft = self.model.width_ft
        h_ft = self.model.height_ft
        scale = self.model.scale

        self._add_static_canvas()
        self._draw_sunlight_overlay()

        shadow_vector = self.controller.get_shadow_vector()
        for shape in self.model.shapes:
            shadow = self.controller.get_shadow_poly(shape, shadow_vector)
            if shadow is None:
                continue
            if isinstance(shadow, tuple) and shadow[0] == "ellipse":
                _, cx_ft, cy_ft, radius_ft = shadow
                cx_px, cy_px = self.world_to_canvas(cx_ft, cy_ft)
                radius_px = self._radius_px_at(cx_ft, cy_ft, radius_ft)
                with self.canvas:
                    Color(*COLOR_SHADOW)
                    Ellipse(
                        pos=(cx_px - radius_px, cy_px - radius_px),
                        size=(radius_px * 2.0, radius_px * 2.0),
                    )
            elif len(shadow) >= 3:
                self._draw_polygon_fill(shadow, COLOR_SHADOW)

        for index, shape in enumerate(self.model.shapes):
            selected = index == self.model.selected_idx
            category = shape.get("category", DEFAULT_CATEGORY)
            category_cfg = CATEGORIES.get(category, CATEGORIES[DEFAULT_CATEGORY])
            fill = category_cfg["fill"]
            outline = COLOR_SELECT if selected else category_cfg["outline"]
            line_width = 3 if selected else 2
            shape_type = shape["type"]
            plan = shape_render_plan(shape, fill, outline, self.model.grid_size)
            if plan is None:
                continue

            for polygon in plan["polygons"]:
                self._draw_polygon_fill(
                    polygon["points"],
                    polygon["fill"],
                    log_failure=False,
                )
                self._draw_polygon_outline(
                    polygon["points"],
                    polygon["outline"],
                    width=line_width,
                )
            for line in plan["lines"]:
                self._draw_polyline_points(
                    line["points"],
                    line["color"] if not selected else COLOR_SELECT,
                    width=max(line_width, line["width"]),
                )

            label_point = plan["label_point"]
            if label_point is None:
                if shape.get("grid_item") == "irrigation_hose":
                    continue
                continue
            mx, my = label_point

            if shape.get("plant"):
                plant = shape["plant"]
                label_color = hex_to_rgba("#E8F5E8")
                name = plant.get("name", "Plant").split(" - ", 1)[0][:12]
                state = plant.get("growth_state", "SEED")
                progress = self._plant_progress(plant)
                px, py = self.world_to_canvas(mx, my)
                icon_size_px = 24
                if shape_type == "circle":
                    icon_size_px = max(
                        18,
                        min(34, self._radius_px_at(shape["geom"][0], shape["geom"][1], shape["geom"][2]) * 0.8),
                    )
                self._add_growth_stage_px(self.canvas, px, py + 8, plant, max(9, icon_size_px * 0.58))
                self._draw_plant_icon_px(
                    px,
                    py + 8,
                    plant,
                    icon_size_px * self._growth_icon_scale(state),
                )
                if shape.get("grid_item") == "carrot_seed":
                    continue
                output = plant.get("output")
                label = f"{name}\n{state[:3]} {progress:.0f}%"
                if output:
                    label = f"{name}\n{output}"
                self._add_text_px(
                    self.canvas,
                    px,
                    py - icon_size_px / 2.0 - 6,
                    label,
                    font_size=8,
                    color=label_color,
                )
                continue

            if shape.get("grid_item") == "irrigation_hose":
                continue

            label_color = hex_to_rgba("#E8F5E8") if category != "Garden" else hex_to_rgba("#1B4F26")
            label_text = f"{category[0]}\n{shape['height_ft']:.1f}ft"
            self._draw_text(mx, my, label_text, font_size=9, color=label_color)

        self._draw_plant_preview()

        if self.model.drag_rect:
            x1, y1, x2, y2 = self.model.drag_rect
            if self._use_overlay_projection():
                rect_points = self._rect_points(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
                self._draw_polygon_fill(rect_points, COLOR_PREVIEW_FILL, log_failure=False)
                self._draw_polygon_outline(rect_points, COLOR_PREVIEW_OUT, width=2)
            else:
                x1_px, y1_px = self.world_to_canvas(x1, y1)
                x2_px, y2_px = self.world_to_canvas(x2, y2)
                left = min(x1_px, x2_px)
                bottom = min(y1_px, y2_px)
                width = abs(x2_px - x1_px)
                height = abs(y2_px - y1_px)
                with self.canvas:
                    Color(*COLOR_PREVIEW_FILL)
                    Rectangle(pos=(left, bottom), size=(width, height))
                    Color(*COLOR_PREVIEW_OUT)
                    Line(rectangle=(left, bottom, width, height), width=2)

        if self.model.drag_circle:
            cx_ft, cy_ft, radius_ft = self.model.drag_circle
            cx_px, cy_px = self.world_to_canvas(cx_ft, cy_ft)
            radius_px = self._radius_px_at(cx_ft, cy_ft, radius_ft)
            with self.canvas:
                Color(*COLOR_PREVIEW_FILL)
                Ellipse(
                    pos=(cx_px - radius_px, cy_px - radius_px),
                    size=(radius_px * 2.0, radius_px * 2.0),
                )
                Color(*COLOR_PREVIEW_OUT)
                Line(circle=(cx_px, cy_px, radius_px), width=2)

        if self.model.drag_strip:
            preview_points = self.model.drag_strip.get("points")
            if preview_points:
                self._draw_polygon_fill(
                    preview_points,
                    COLOR_PREVIEW_FILL,
                    log_failure=False,
                )
                self._draw_polygon_outline(
                    preview_points,
                    COLOR_PREVIEW_OUT,
                    width=2,
                )
            else:
                point_a, point_b = self.model.drag_strip["geom"]
                self._draw_segment(point_a, point_b, COLOR_PREVIEW_OUT, width=2)

        if self.model.draw_mode == "polygon" and self.model.poly_points:
            for x_ft, y_ft in self.model.poly_points:
                px, py = self.world_to_canvas(x_ft, y_ft)
                with self.canvas:
                    Color(*COLOR_PREVIEW_OUT)
                    Line(circle=(px, py, 3), width=2)
            if len(self.model.poly_points) > 1:
                preview_line = []
                for x_ft, y_ft in self.model.poly_points:
                    px, py = self.world_to_canvas(x_ft, y_ft)
                    preview_line.extend([px, py])
                with self.canvas:
                    Color(*COLOR_PREVIEW_OUT)
                    Line(points=preview_line, width=2)

        if self.model.snap_preview is not None and self._is_editing_gesture():
            preview_x, preview_y = self.model.snap_preview
            px, py = self.world_to_canvas(preview_x, preview_y)
            with self.canvas:
                Color(*COLOR_SNAP_PREVIEW)
                Line(circle=(px, py, 3), width=2)

        if self.model.sun_elevation > 0:
            center_x = w_ft / 2.0
            center_y = h_ft / 2.0
            azimuth_rad = math.radians(self.model.sun_azimuth)
            length_ft = min(w_ft, h_ft) / 5.0
            end_x = center_x + math.sin(azimuth_rad) * length_ft
            end_y = center_y + math.cos(azimuth_rad) * length_ft
            cx_px, cy_px = self.world_to_canvas(center_x, center_y)
            ex_px, ey_px = self.world_to_canvas(end_x, end_y)
            angle = math.atan2(ey_px - cy_px, ex_px - cx_px)
            arrow_length = 8
            left_x = ex_px - arrow_length * math.cos(angle + math.pi * 0.8)
            left_y = ey_px - arrow_length * math.sin(angle + math.pi * 0.8)
            right_x = ex_px - arrow_length * math.cos(angle - math.pi * 0.8)
            right_y = ey_px - arrow_length * math.sin(angle - math.pi * 0.8)

            with self.canvas:
                Color(*COLOR_SUN_ARROW)
                Line(points=[cx_px, cy_px, ex_px, ey_px], width=2)
                Line(points=[ex_px, ey_px, left_x, left_y], width=2)
                Line(points=[ex_px, ey_px, right_x, right_y], width=2)
                Color(*COLOR_SUN)
                Line(circle=(cx_px, cy_px, 5), width=2)

            self._draw_text(
                center_x,
                center_y + 0.6,
                f"{self.model.sun_elevation:.0f} deg",
                font_size=9,
                color=COLOR_SUN,
            )
        else:
            self._draw_text(
                w_ft / 2.0,
                h_ft / 2.0,
                "Sun below horizon",
                font_size=12,
                color=COLOR_SUN_BELOW,
            )
