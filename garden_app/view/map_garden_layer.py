"""MapView layer that projects garden-world feet onto terrain tiles."""

from __future__ import annotations

import os

from kivy.graphics import Color, InstructionGroup, Line, Mesh
from kivy_garden.mapview import MapLayer

from ..constants import CATEGORIES, DEFAULT_CATEGORY
from ..map_projection import garden_ft_to_latlon, latlon_to_garden_ft
from ..utils import triangulate_polygon_ear_clipping
from .canvas_renderer import circle_points_ft, shape_render_plan


def compensated_get_window_xy_from(view, lat, lon, zoom):
    px, py = view.get_window_xy_from(lat, lon, zoom)
    origin_x, origin_y = view.to_window(0, 0, initial=False)
    pos_x, pos_y = view.pos
    return px - pos_x + origin_x, py - pos_y + origin_y


class GardenMapLayer(MapLayer):
    def __init__(self, model, controller, render_model_shapes=True, **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.controller = controller
        self.render_model_shapes = bool(render_model_shapes)
        self._debug_enabled = (
            os.environ.get("GARDEN_DEBUG_TERRAIN_MAP") == "1"
            or os.environ.get("GARDEN_DEBUG_MAP_LAYER") == "1"
        )
        self._debug_counts = {}
        self._instructions = InstructionGroup()
        self.canvas.add(self._instructions)
        self._debug("map_layer: init")
        self.model.bind(
            shapes=lambda *_args: self.reposition(),
            map_overlay_anchor_lat=lambda *_args: self.reposition(),
            map_overlay_anchor_lon=lambda *_args: self.reposition(),
            map_overlay_rotation_deg=lambda *_args: self.reposition(),
            map_overlay_y_axis_sign=lambda *_args: self.reposition(),
            grid_size=lambda *_args: self.reposition(),
        )

    def _debug(self, message):
        if self._debug_enabled:
            print(message, flush=True)

    def _debug_limited(self, key, message, limit=3):
        count = self._debug_counts.get(key, 0)
        if count >= limit:
            return
        self._debug_counts[key] = count + 1
        self._debug(message)

    @property
    def anchor_lat(self):
        return float(self.model.map_overlay_anchor_lat)

    @property
    def anchor_lon(self):
        return float(self.model.map_overlay_anchor_lon)

    @property
    def theta_deg(self):
        return float(self.model.map_overlay_rotation_deg)

    @property
    def y_axis_sign(self):
        return 1.0 if float(self.model.map_overlay_y_axis_sign) >= 0.0 else -1.0

    def reposition(self):
        self._debug_limited(
            "reposition",
            f"map_layer: reposition parent={self.parent!r} shapes={len(self.model.shapes)}",
        )
        self._instructions.clear()
        if self.parent is None:
            return
        if not self.render_model_shapes:
            return

        for shape in self.model.shapes:
            self._draw_shape(shape)

    def unload(self):
        self._instructions.clear()

    def _local_ft_to_latlon(self, x_ft, y_ft):
        self._debug_limited(
            "project",
            f"map_layer: project local_ft=({x_ft:.3f}, {y_ft:.3f}) "
            f"anchor=({self.anchor_lat:.6f}, {self.anchor_lon:.6f}) "
            f"theta={self.theta_deg:.3f} y_sign={self.y_axis_sign:.1f}",
            limit=1,
        )
        return garden_ft_to_latlon(
            x_ft,
            y_ft,
            self.anchor_lat,
            self.anchor_lon,
            self.theta_deg,
            y_axis_sign=self.y_axis_sign,
        )

    def latlon_to_garden_ft(self, lat, lon, clamp=False):
        x_ft, y_ft = latlon_to_garden_ft(
            lat,
            lon,
            self.anchor_lat,
            self.anchor_lon,
            self.theta_deg,
            y_axis_sign=self.y_axis_sign,
        )
        if not clamp:
            return x_ft, y_ft
        return (
            max(0.0, min(x_ft, float(self.model.width_ft))),
            max(0.0, min(y_ft, float(self.model.height_ft))),
        )

    def map_widget_xy_to_garden_ft(self, map_view, x, y, clamp=False):
        coordinate = map_view.get_latlon_at(float(x), float(y), map_view.zoom)
        return self.latlon_to_garden_ft(
            float(coordinate.lat),
            float(coordinate.lon),
            clamp=clamp,
        )

    def latlon_to_map_widget_xy(self, map_view, lat, lon):
        px, py = compensated_get_window_xy_from(map_view, lat, lon, map_view.zoom)
        return px - float(map_view.x), py - float(map_view.y)

    def garden_ft_to_map_widget_xy(self, map_view, x_ft, y_ft):
        lat, lon = self._local_ft_to_latlon(float(x_ft), float(y_ft))
        return self.latlon_to_map_widget_xy(map_view, lat, lon)

    def touch_to_garden_ft(self, map_view, touch, clamp=False):
        local_x, local_y = map_view.to_widget(touch.x, touch.y, relative=True)
        garden_ft = self.map_widget_xy_to_garden_ft(map_view, local_x, local_y, clamp=clamp)
        self._debug_limited(
            "touch",
            f"map_layer: touch ({touch.x:.1f}, {touch.y:.1f}) -> "
            f"widget=({local_x:.1f}, {local_y:.1f}) -> "
            f"garden=({garden_ft[0]:.3f}, {garden_ft[1]:.3f})",
            limit=1,
        )
        return garden_ft

    def _latlon_to_layer_xy(self, lat, lon):
        view = self.parent
        px, py = compensated_get_window_xy_from(view, lat, lon, view.zoom)
        px -= view.delta_x
        py -= view.delta_y
        layer_xy = view._scatter.to_local(px, py)
        self._debug_limited(
            "latlon",
            f"map_layer: latlon=({lat:.6f}, {lon:.6f}) -> layer={layer_xy}",
            limit=1,
        )
        return layer_xy

    def _point_to_layer_xy(self, point_ft):
        lat, lon = self._local_ft_to_latlon(point_ft[0], point_ft[1])
        return self._latlon_to_layer_xy(lat, lon)

    def _points_to_layer_points(self, points_ft):
        points = []
        for point in points_ft:
            px, py = self._point_to_layer_xy(point)
            points.extend([px, py])
        return points

    def _draw_shape(self, shape):
        shape_type = shape.get("type")
        category = shape.get("category", DEFAULT_CATEGORY)
        category_cfg = CATEGORIES.get(category, CATEGORIES[DEFAULT_CATEGORY])
        fill = category_cfg["fill"]
        outline = category_cfg["outline"]
        plan = shape_render_plan(shape, fill, outline, self.model.grid_size)
        if plan is None:
            return

        for polygon in plan["polygons"]:
            self._draw_polygon(polygon["points"], polygon["fill"], polygon["outline"])
        for line in plan["lines"]:
            self._draw_line(line["points"], line["color"], width=line["width"])

        if shape.get("plant") and shape_type == "circle":
            self._draw_plant_marker(shape)

    def _draw_polygon(self, points_ft, fill, outline):
        if len(points_ft) < 3:
            return

        triangles = triangulate_polygon_ear_clipping(points_ft)
        if triangles:
            vertices = []
            indices = []
            vertex_index = 0
            for triangle in triangles:
                for point in triangle:
                    px, py = self._point_to_layer_xy(point)
                    vertices.extend([px, py, 0, 0])
                    indices.append(vertex_index)
                    vertex_index += 1
            self._instructions.add(Color(*fill))
            self._instructions.add(Mesh(vertices=vertices, indices=indices, mode="triangles"))

        outline_points = self._points_to_layer_points(points_ft)
        if len(outline_points) >= 4:
            self._instructions.add(Color(*outline))
            self._instructions.add(Line(points=outline_points, width=1.4, close=True))

    def _draw_line(self, points_ft, color, width=2):
        points = self._points_to_layer_points(points_ft)
        if len(points) < 4:
            return
        self._instructions.add(Color(*color))
        self._instructions.add(Line(points=points, width=width))

    def _draw_plant_marker(self, shape):
        plant = shape.get("plant") or {}
        try:
            cx_ft, cy_ft, radius_ft = shape["geom"]
        except (KeyError, TypeError, ValueError):
            return
        progress = max(0.0, min(100.0, float(plant.get("growth_progress", 0.0))))
        marker_radius = max(0.08, min(float(radius_ft) * 0.32, 0.35))
        color = (
            (0.88, 0.39, 0.24, 0.86)
            if progress >= 100.0
            else (0.20, 0.72, 0.25, 0.78)
        )
        self._draw_polygon(
            circle_points_ft(cx_ft, cy_ft, marker_radius, segments=12),
            color,
            (0.92, 1.0, 0.78, 0.95),
        )
