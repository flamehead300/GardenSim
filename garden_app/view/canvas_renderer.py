"""Shared garden shape rendering plan used by canvas and map layers."""

from __future__ import annotations

from math import cos, pi, sin

from ..constants import DEFAULT_STRIP_WIDTH_FT
from ..utils import (
    interior_label_point,
    strip_midpoint,
    strip_polygon_from_centerline,
    triangulate_polygon_ear_clipping,
    validate_polygon_points,
)


CIRCLE_SEGMENTS = 32


def circle_points_ft(cx_ft, cy_ft, radius_ft, segments=CIRCLE_SEGMENTS):
    radius = max(0.0, float(radius_ft))
    if radius <= 0.0:
        return ()
    return tuple(
        (
            float(cx_ft) + radius * cos((2.0 * pi * index) / segments),
            float(cy_ft) + radius * sin((2.0 * pi * index) / segments),
        )
        for index in range(segments)
    )


def hose_render_primitives(shape, grid_size):
    try:
        cx_ft, cy_ft, radius_ft = shape["geom"]
    except (KeyError, TypeError, ValueError):
        return [], []

    connections = shape.get("hose_connections") or ()
    radius_ft = max(0.03, float(radius_ft))
    grid_span_ft = max(0.1, float(grid_size) * 0.48)
    if not connections:
        return [
            {
                "points": circle_points_ft(
                    cx_ft,
                    cy_ft,
                    max(0.06, grid_span_ft * 0.28),
                    segments=12,
                ),
                "fill": (0.15, 0.52, 1.0, 0.28),
                "outline": (0.05, 0.30, 0.67, 0.92),
            }
        ], []

    offsets = {
        "N": (0.0, grid_span_ft),
        "E": (grid_span_ft, 0.0),
        "S": (0.0, -grid_span_ft),
        "W": (-grid_span_ft, 0.0),
    }
    polygons = [
        {
            "points": circle_points_ft(cx_ft, cy_ft, max(radius_ft * 0.78, 0.04), segments=16),
            "fill": (0.05, 0.30, 0.67, 0.92),
            "outline": (0.05, 0.30, 0.67, 0.92),
        },
        {
            "points": circle_points_ft(cx_ft, cy_ft, max(radius_ft * 0.42, 0.025), segments=16),
            "fill": (0.33, 0.75, 1.0, 0.96),
            "outline": (0.33, 0.75, 1.0, 0.96),
        },
    ]
    for direction in connections:
        dx_ft, dy_ft = offsets.get(direction, (0.0, 0.0))
        segment = ((cx_ft, cy_ft), (cx_ft + dx_ft, cy_ft + dy_ft))
        outer_points = strip_polygon_from_centerline(segment[0], segment[1], radius_ft * 1.56)
        inner_points = strip_polygon_from_centerline(segment[0], segment[1], radius_ft * 0.84)
        if outer_points:
            polygons.append(
                {
                    "points": outer_points,
                    "fill": (0.05, 0.30, 0.67, 0.92),
                    "outline": (0.05, 0.30, 0.67, 0.92),
                }
            )
        if inner_points:
            polygons.append(
                {
                    "points": inner_points,
                    "fill": (0.33, 0.75, 1.0, 0.96),
                    "outline": (0.33, 0.75, 1.0, 0.96),
                }
            )
    return polygons, []


def shape_render_plan(shape, fill, outline, grid_size):
    shape_type = shape.get("type")
    if shape.get("grid_item") == "irrigation_hose":
        polygons, lines = hose_render_primitives(shape, grid_size)
        return {"polygons": polygons, "lines": lines, "label_point": None}

    polygons = []
    lines = []
    label_point = None

    if shape_type == "rect":
        x1, y1, x2, y2 = shape["geom"]
        polygons.append({"points": ((x1, y1), (x2, y1), (x2, y2), (x1, y2)), "fill": fill, "outline": outline})
        label_point = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    elif shape_type == "circle":
        cx_ft, cy_ft, radius_ft = shape["geom"]
        polygons.append({"points": circle_points_ft(cx_ft, cy_ft, radius_ft), "fill": fill, "outline": outline})
        label_point = (cx_ft, cy_ft)
    elif shape_type == "polygon":
        points = shape["geom"]
        polygons.append({"points": points, "fill": fill, "outline": outline})
        is_valid, polygon_points, _message = validate_polygon_points(points)
        if is_valid:
            triangles = triangulate_polygon_ear_clipping(polygon_points)
            label_point = interior_label_point(polygon_points, triangles=triangles)
    elif shape_type == "strip":
        point_a, point_b = shape["geom"]
        strip_points = strip_polygon_from_centerline(
            point_a,
            point_b,
            shape.get("width_ft", DEFAULT_STRIP_WIDTH_FT),
        )
        if strip_points:
            polygons.append({"points": strip_points, "fill": fill, "outline": outline})
        else:
            lines.append({"points": (point_a, point_b), "color": outline, "width": 2})
        label_point = strip_midpoint(point_a, point_b)
    else:
        return None

    return {"polygons": polygons, "lines": lines, "label_point": label_point}
