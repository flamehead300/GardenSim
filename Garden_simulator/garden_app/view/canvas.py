import logging
import math

try:
    from kivy.core.text import CoreLabel
except ImportError:
    from kivy.core.text import Label as CoreLabel

from kivy.graphics import Color, Ellipse, Line, Mesh, Rectangle
from kivy.uix.stencilview import StencilView

from ..utils import (
    hex_to_rgba,
    interior_label_point,
    strip_midpoint,
    strip_polygon_from_centerline,
    triangulate_polygon_ear_clipping,
    validate_polygon_points,
)
from ..constants import (
    COLOR_PANEL, COLOR_CANVAS, COLOR_GRID, COLOR_GRID_SNAP,
    COLOR_SHADOW, COLOR_PREVIEW_FILL, COLOR_PREVIEW_OUT,
    COLOR_SELECT, COLOR_SNAP_PREVIEW, COLOR_SUN, COLOR_SUN_ARROW,
    COLOR_SUN_BELOW, COLOR_TEXT, COLOR_LABEL_TEXT,
    CATEGORIES, DEFAULT_CATEGORY, DEFAULT_STRIP_WIDTH_FT,
)

LOGGER = logging.getLogger(__name__)


class GardenCanvas(StencilView):
    """Canvas widget that renders the garden and proxies touch input."""
    TAP_SLOP_PX = 10

    def __init__(self, model, controller, **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.controller = controller
        self.size_hint = (1, 1)
        self._active_touches = {}
        self._logged_polygon_fill_failures = set()

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
        )

    def _on_state_change(self, *_args):
        self.redraw()

    def _is_editing_gesture(self):
        return self.model.draw_mode is not None or self.model.move_mode

    def world_to_canvas(self, x_ft, y_ft):
        scale = self.model.scale
        return (
            self.x + self.model.offset_x + x_ft * scale,
            self.y + self.model.offset_y + y_ft * scale,
        )

    def canvas_to_world(self, cx, cy):
        scale = self.model.scale
        x_ft = (cx - self.model.offset_x) / scale
        y_ft = (cy - self.model.offset_y) / scale
        x_ft = max(0.0, min(x_ft, self.model.width_ft))
        y_ft = max(0.0, min(y_ft, self.model.height_ft))
        return x_ft, y_ft

    def _world_from_touch(self, touch):
        # touch coordinates arrive in the parent's space. To get the position
        # relative to the canvas's own origin, subtract self.x and self.y
        local_x = touch.x - self.x
        local_y = touch.y - self.y
        local_x = max(0.0, min(local_x, self.width))
        local_y = max(0.0, min(local_y, self.height))
        return self.canvas_to_world(local_x, local_y)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)

        if self._is_editing_gesture():
            touch.grab(self)
            self.controller.on_mouse_press(self._world_from_touch(touch))
            return True

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
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self.controller.on_mouse_drag(self._world_from_touch(touch))
            return True

        touch_id = touch.uid
        if touch_id not in self._active_touches:
            return super().on_touch_move(touch)

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

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self.controller.on_mouse_release(self._world_from_touch(touch))
            return True

        entry = self._active_touches.pop(touch.uid, None)
        if entry is None:
            return super().on_touch_up(touch)

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

    def _draw_text(self, x_ft, y_ft, text, anchor="center", font_size=12, color=COLOR_TEXT):
        if not text:
            return
        label = CoreLabel(text=str(text), font_size=font_size, color=color)
        label.refresh()
        texture = label.texture
        width, height = texture.size
        px, py = self.world_to_canvas(x_ft, y_ft)

        if anchor == "center":
            px -= width / 2.0
            py -= height / 2.0
        elif anchor == "south":
            px -= width / 2.0
        elif anchor == "west":
            py -= height / 2.0

        with self.canvas:
            Color(1, 1, 1, 1)
            Rectangle(texture=texture, pos=(px, py), size=(width, height))

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

    def redraw(self):
        self.canvas.clear()
        if self.width <= 0 or self.height <= 0:
            return

        w_ft = self.model.width_ft
        h_ft = self.model.height_ft
        scale = self.model.scale
        viewport_x = self.x
        viewport_y = self.y
        viewport_w = self.width
        viewport_h = self.height
        world_x = self.x + self.model.offset_x
        world_y = self.y + self.model.offset_y
        world_w = w_ft * scale
        world_h = h_ft * scale

        with self.canvas:
            Color(*COLOR_PANEL)
            Rectangle(pos=(viewport_x, viewport_y), size=(viewport_w, viewport_h))
            Color(*COLOR_CANVAS)
            Rectangle(pos=(world_x, world_y), size=(world_w, world_h))

        for x_ft in range(0, int(w_ft) + 1):
            x_px, _ = self.world_to_canvas(x_ft, 0)
            with self.canvas:
                Color(*COLOR_GRID)
                Line(points=[x_px, world_y, x_px, world_y + world_h], width=1)
        for y_ft in range(0, int(h_ft) + 1):
            _, y_px = self.world_to_canvas(0, y_ft)
            with self.canvas:
                Color(*COLOR_GRID)
                Line(points=[world_x, y_px, world_x + world_w, y_px], width=1)

        if self.model.snap_to_grid and self.model.grid_size > 0:
            snap_step = self.model.grid_size
            x_ft = 0.0
            while x_ft <= w_ft + 1e-9:
                x_px, _ = self.world_to_canvas(x_ft, 0)
                with self.canvas:
                    Color(*COLOR_GRID_SNAP)
                    Line(points=[x_px, world_y, x_px, world_y + world_h], width=1)
                x_ft += snap_step

            y_ft = 0.0
            while y_ft <= h_ft + 1e-9:
                _, y_px = self.world_to_canvas(0, y_ft)
                with self.canvas:
                    Color(*COLOR_GRID_SNAP)
                    Line(points=[world_x, y_px, world_x + world_w, y_px], width=1)
                y_ft += snap_step

        step = 5
        if scale < 2:
            step = 20
        elif scale < 5:
            step = 10

        for x_ft in range(0, int(w_ft) + 1, step):
            self._draw_text(x_ft, 0.2, str(x_ft), anchor="south", font_size=8, color=COLOR_LABEL_TEXT)
        for y_ft in range(0, int(h_ft) + 1, step):
            self._draw_text(0.2, y_ft, str(y_ft), anchor="west", font_size=8, color=COLOR_LABEL_TEXT)

        shadow_vector = self.controller.get_shadow_vector()
        for shape in self.model.shapes:
            shadow = self.controller.get_shadow_poly(shape, shadow_vector)
            if shadow is None:
                continue
            if isinstance(shadow, tuple) and shadow[0] == "ellipse":
                _, cx_ft, cy_ft, radius_ft = shadow
                cx_px, cy_px = self.world_to_canvas(cx_ft, cy_ft)
                radius_px = radius_ft * scale
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

            if shape_type == "rect":
                x1, y1, x2, y2 = shape["geom"]
                x1_px, y1_px = self.world_to_canvas(x1, y1)
                x2_px, y2_px = self.world_to_canvas(x2, y2)
                left = min(x1_px, x2_px)
                bottom = min(y1_px, y2_px)
                width = abs(x2_px - x1_px)
                height = abs(y2_px - y1_px)
                with self.canvas:
                    Color(*fill)
                    Rectangle(pos=(left, bottom), size=(width, height))
                    Color(*outline)
                    Line(rectangle=(left, bottom, width, height), width=line_width)
                mx = (x1 + x2) / 2.0
                my = (y1 + y2) / 2.0
            elif shape_type == "circle":
                cx_ft, cy_ft, radius_ft = shape["geom"]
                cx_px, cy_px = self.world_to_canvas(cx_ft, cy_ft)
                radius_px = radius_ft * scale
                with self.canvas:
                    Color(*fill)
                    Ellipse(
                        pos=(cx_px - radius_px, cy_px - radius_px),
                        size=(radius_px * 2.0, radius_px * 2.0),
                    )
                    Color(*outline)
                    Line(circle=(cx_px, cy_px, radius_px), width=line_width)
                mx = cx_ft
                my = cy_ft
            elif shape_type == "polygon":
                points = shape["geom"]
                is_valid_polygon, polygon_points, polygon_triangles = self._prepare_polygon_fill(points)
                self._draw_polygon_fill(
                    points,
                    fill,
                    triangles=polygon_triangles,
                    log_failure=False,
                )
                self._draw_polygon_outline(points, outline, width=line_width)
                label_point = (
                    interior_label_point(polygon_points, triangles=polygon_triangles)
                    if is_valid_polygon
                    else None
                )
                if label_point is None:
                    continue
                mx, my = label_point
            elif shape_type == "strip":
                point_a, point_b = shape["geom"]
                strip_points = strip_polygon_from_centerline(
                    point_a,
                    point_b,
                    shape.get("width_ft", DEFAULT_STRIP_WIDTH_FT),
                )
                if not strip_points:
                    self._draw_segment(point_a, point_b, outline, width=line_width)
                    continue

                _, _, strip_triangles = self._prepare_polygon_fill(strip_points)
                self._draw_polygon_fill(
                    strip_points,
                    fill,
                    triangles=strip_triangles,
                    log_failure=False,
                )
                self._draw_polygon_outline(strip_points, outline, width=line_width)
                mx, my = strip_midpoint(point_a, point_b)
            else:
                continue

            label_color = hex_to_rgba("#E8F5E8") if category != "Garden" else hex_to_rgba("#1B4F26")
            label_text = f"{category[0]}\n{shape['height_ft']:.1f}ft"
            self._draw_text(mx, my, label_text, font_size=9, color=label_color)

        if self.model.drag_rect:
            x1, y1, x2, y2 = self.model.drag_rect
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
            radius_px = radius_ft * scale
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
