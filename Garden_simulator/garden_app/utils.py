import datetime
import math
from zoneinfo import available_timezones

from kivy.utils import get_color_from_hex


GEOM_EPSILON = 1e-9


def hex_to_rgba(hex_color, alpha=1.0):
    """Convert a hex color to an RGBA tuple."""
    red, green, blue, _ = get_color_from_hex(hex_color)
    return red, green, blue, alpha


def format_number(value, digits=3):
    """Format numeric fields without noisy trailing zeroes."""
    text = f"{value:.{digits}f}"
    text = text.rstrip("0").rstrip(".")
    return text or "0"


def minutes_from_time_str(time_str):
    """Convert an ISO time string into whole minutes from midnight."""
    parsed_time = datetime.time.fromisoformat(time_str)
    return parsed_time.hour * 60 + parsed_time.minute


def time_str_from_minutes(minutes, include_seconds=True):
    """Convert whole minutes from midnight into a normalized time string."""
    clamped_minutes = max(0, min(1439, int(round(minutes))))

    hours, mins = divmod(clamped_minutes, 60)
    if include_seconds:
        return f"{hours:02d}:{mins:02d}:00"
    return f"{hours:02d}:{mins:02d}"


def default_timezone_name():
    """Return the default IANA timezone used for solar calculations."""
    return "America/New_York"


def available_timezone_names():
    """Return sorted IANA timezone names for the UI dropdown."""
    try:
        return tuple(sorted(available_timezones()))
    except Exception:
        return (
            "UTC",
            "America/New_York",
            "America/Chicago",
            "America/Denver",
            "America/Los_Angeles",
            "Europe/London",
            "Europe/Paris",
            "Asia/Tokyo",
            "Australia/Sydney",
        )


def replace_shape(shapes, idx, new_shape):
    """Return a new shape list with one item replaced."""
    new_shapes = list(shapes)
    new_shapes[idx] = new_shape
    return new_shapes


def remove_shape(shapes, idx):
    """Return a new shape list with the target item removed."""
    return [shape for i, shape in enumerate(shapes) if i != idx]


def append_shape(shapes, new_shape):
    """Return a new shape list with one item appended."""
    return [*shapes, new_shape]


def insert_shape(shapes, idx, new_shape):
    """Return a new shape list with one item inserted."""
    return [*shapes[:idx], new_shape, *shapes[idx:]]


def clone_shape(shape):
    """Return a shallow shape clone with an immutable geometry payload."""
    return {**shape, "geom": tuple(shape["geom"])}


def _coerce_point(point):
    return float(point[0]), float(point[1])


def _coerce_points(points):
    return tuple(_coerce_point(point) for point in points)


def _points_match(point_a, point_b, epsilon=GEOM_EPSILON):
    return (
        abs(point_a[0] - point_b[0]) <= epsilon
        and abs(point_a[1] - point_b[1]) <= epsilon
    )


def _cross(origin, point_a, point_b):
    return (point_a[0] - origin[0]) * (point_b[1] - origin[1]) - (
        point_a[1] - origin[1]
    ) * (point_b[0] - origin[0])


def _point_on_segment(point, seg_start, seg_end, epsilon=GEOM_EPSILON):
    if abs(_cross(seg_start, seg_end, point)) > epsilon:
        return False
    return (
        min(seg_start[0], seg_end[0]) - epsilon <= point[0] <= max(seg_start[0], seg_end[0]) + epsilon
        and min(seg_start[1], seg_end[1]) - epsilon <= point[1] <= max(seg_start[1], seg_end[1]) + epsilon
    )


def _open_polygon_points(points):
    coerced = list(_coerce_points(points))
    if len(coerced) >= 2 and _points_match(coerced[0], coerced[-1]):
        coerced.pop()
    return tuple(coerced)


def _distinct_points(points):
    distinct = []
    for point in points:
        if not any(_points_match(point, existing) for existing in distinct):
            distinct.append(point)
    return tuple(distinct)


def polygon_signed_area(points):
    """Return the signed shoelace area for an open-ring polygon."""
    polygon = _open_polygon_points(points)
    if len(polygon) < 3:
        return 0.0

    signed_double_area = 0.0
    for index, point in enumerate(polygon):
        next_point = polygon[(index + 1) % len(polygon)]
        signed_double_area += point[0] * next_point[1] - next_point[0] * point[1]
    return signed_double_area / 2.0


def polygon_area(points):
    return abs(polygon_signed_area(points))


def normalize_polygon_winding(points, clockwise=False):
    """Return an open-ring polygon with a predictable winding order."""
    polygon = _open_polygon_points(points)
    signed_area = polygon_signed_area(polygon)
    if abs(signed_area) <= GEOM_EPSILON:
        return polygon

    wants_negative = bool(clockwise)
    has_negative = signed_area < 0
    if wants_negative == has_negative:
        return polygon
    return tuple(reversed(polygon))


def has_duplicate_consecutive_points(points):
    polygon = _open_polygon_points(points)
    return any(
        _points_match(point_a, point_b)
        for point_a, point_b in zip(polygon, polygon[1:])
    )


def segments_intersect(a1, a2, b1, b2, allow_shared_endpoints=False):
    """Return True when two line segments intersect or overlap."""
    a1 = _coerce_point(a1)
    a2 = _coerce_point(a2)
    b1 = _coerce_point(b1)
    b2 = _coerce_point(b2)

    shared_endpoint = any(
        _points_match(point_a, point_b)
        for point_a in (a1, a2)
        for point_b in (b1, b2)
    )

    o1 = _cross(a1, a2, b1)
    o2 = _cross(a1, a2, b2)
    o3 = _cross(b1, b2, a1)
    o4 = _cross(b1, b2, a2)

    intersects = False
    if (
        ((o1 > GEOM_EPSILON and o2 < -GEOM_EPSILON) or (o1 < -GEOM_EPSILON and o2 > GEOM_EPSILON))
        and ((o3 > GEOM_EPSILON and o4 < -GEOM_EPSILON) or (o3 < -GEOM_EPSILON and o4 > GEOM_EPSILON))
    ):
        intersects = True
    elif abs(o1) <= GEOM_EPSILON and _point_on_segment(b1, a1, a2):
        intersects = True
    elif abs(o2) <= GEOM_EPSILON and _point_on_segment(b2, a1, a2):
        intersects = True
    elif abs(o3) <= GEOM_EPSILON and _point_on_segment(a1, b1, b2):
        intersects = True
    elif abs(o4) <= GEOM_EPSILON and _point_on_segment(a2, b1, b2):
        intersects = True

    if not intersects:
        return False

    if allow_shared_endpoints and shared_endpoint:
        collinear = all(abs(value) <= GEOM_EPSILON for value in (o1, o2, o3, o4))
        return collinear
    return True


def is_simple_polygon(points):
    """Return True for a simple polygon; concave polygons are allowed."""
    is_valid, _polygon, _message = validate_polygon_points(points)
    return is_valid


def strip_polygon_from_centerline(p1, p2, width_ft):
    """Return the four strip corners generated from a centerline and width."""
    p1 = _coerce_point(p1)
    p2 = _coerce_point(p2)
    width_ft = float(width_ft)

    length = strip_length(p1, p2)
    if length <= GEOM_EPSILON or width_ft <= GEOM_EPSILON:
        return None

    dx = (p2[0] - p1[0]) / length
    dy = (p2[1] - p1[1]) / length
    half_width = width_ft / 2.0
    perp_x = -dy * half_width
    perp_y = dx * half_width

    corners = (
        (p1[0] + perp_x, p1[1] + perp_y),
        (p2[0] + perp_x, p2[1] + perp_y),
        (p2[0] - perp_x, p2[1] - perp_y),
        (p1[0] - perp_x, p1[1] - perp_y),
    )
    return normalize_polygon_winding(corners)


def strip_midpoint(p1, p2):
    p1 = _coerce_point(p1)
    p2 = _coerce_point(p2)
    return (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0


def strip_length(p1, p2):
    p1 = _coerce_point(p1)
    p2 = _coerce_point(p2)
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def polygon_centroid(points):
    """Return the true centroid for a non-degenerate polygon."""
    polygon = _open_polygon_points(points)
    signed_area = polygon_signed_area(polygon)
    if abs(signed_area) <= GEOM_EPSILON:
        return None

    centroid_x = 0.0
    centroid_y = 0.0
    for index, point in enumerate(polygon):
        next_point = polygon[(index + 1) % len(polygon)]
        cross = point[0] * next_point[1] - next_point[0] * point[1]
        centroid_x += (point[0] + next_point[0]) * cross
        centroid_y += (point[1] + next_point[1]) * cross

    scale = 1.0 / (6.0 * signed_area)
    return centroid_x * scale, centroid_y * scale


def point_in_polygon(x, y, points):
    polygon = _open_polygon_points(points)
    if len(polygon) < 3:
        return False

    point = (float(x), float(y))
    inside = False
    for index, point_a in enumerate(polygon):
        point_b = polygon[(index + 1) % len(polygon)]
        if _point_on_segment(point, point_a, point_b):
            return True

        intersects = ((point_a[1] > point[1]) != (point_b[1] > point[1])) and (
            point[0]
            < (point_b[0] - point_a[0]) * (point[1] - point_a[1]) / (point_b[1] - point_a[1]) + point_a[0]
        )
        if intersects:
            inside = not inside
    return inside


def _point_in_triangle(point, triangle):
    point_a, point_b, point_c = triangle
    cross_ab = _cross(point_a, point_b, point)
    cross_bc = _cross(point_b, point_c, point)
    cross_ca = _cross(point_c, point_a, point)
    return (
        cross_ab >= -GEOM_EPSILON
        and cross_bc >= -GEOM_EPSILON
        and cross_ca >= -GEOM_EPSILON
    )


def _triangle_centroid(triangle):
    return (
        (triangle[0][0] + triangle[1][0] + triangle[2][0]) / 3.0,
        (triangle[0][1] + triangle[1][1] + triangle[2][1]) / 3.0,
    )


def _scanline_interior_point(points):
    polygon = _open_polygon_points(points)
    if len(polygon) < 3:
        return None

    ys = sorted({point[1] for point in polygon})
    candidate_ys = []
    centroid = polygon_centroid(polygon)
    if centroid is not None:
        candidate_ys.append(centroid[1])

    if ys:
        candidate_ys.append((ys[0] + ys[-1]) / 2.0)
    for low, high in zip(ys, ys[1:]):
        if abs(high - low) > GEOM_EPSILON:
            candidate_ys.append((low + high) / 2.0)

    for y in candidate_ys:
        intersections = []
        for index, point_a in enumerate(polygon):
            point_b = polygon[(index + 1) % len(polygon)]
            if abs(point_a[1] - point_b[1]) <= GEOM_EPSILON:
                continue
            if (point_a[1] > y) != (point_b[1] > y):
                x = point_a[0] + (y - point_a[1]) * (point_b[0] - point_a[0]) / (point_b[1] - point_a[1])
                intersections.append(x)

        intersections.sort()
        widest_interval = None
        widest_width = -1.0
        for left, right in zip(intersections[0::2], intersections[1::2]):
            width = right - left
            if width > widest_width + GEOM_EPSILON:
                widest_width = width
                widest_interval = (left, right)

        if widest_interval is None or widest_width <= GEOM_EPSILON:
            continue

        candidate = ((widest_interval[0] + widest_interval[1]) / 2.0, y)
        if point_in_polygon(candidate[0], candidate[1], polygon):
            return candidate
    return None


def interior_label_point(points, triangles=None):
    polygon = _open_polygon_points(points)
    if len(polygon) < 3:
        return None

    centroid = polygon_centroid(polygon)
    if centroid is not None and point_in_polygon(centroid[0], centroid[1], polygon):
        return centroid

    if triangles is None:
        triangles = triangulate_polygon_ear_clipping(polygon)

    if triangles:
        largest_triangle = max(triangles, key=polygon_area)
        triangle_center = _triangle_centroid(largest_triangle)
        if point_in_polygon(triangle_center[0], triangle_center[1], polygon):
            return triangle_center

    return _scanline_interior_point(polygon)


def triangulate_polygon_ear_clipping(points):
    """Triangulate a simple polygon using ear clipping; return None on failure."""
    is_valid, polygon, _message = validate_polygon_points(points)
    if not is_valid:
        return None

    polygon = normalize_polygon_winding(polygon)
    remaining = list(range(len(polygon)))
    triangles = []
    max_passes = len(remaining) * len(remaining)
    passes = 0

    while len(remaining) > 3 and passes < max_passes:
        ear_found = False
        for local_index, curr_idx in enumerate(remaining):
            prev_idx = remaining[local_index - 1]
            next_idx = remaining[(local_index + 1) % len(remaining)]
            triangle = (polygon[prev_idx], polygon[curr_idx], polygon[next_idx])

            if polygon_area(triangle) <= GEOM_EPSILON:
                continue
            if _cross(*triangle) <= GEOM_EPSILON:
                continue

            contains_vertex = False
            for other_idx in remaining:
                if other_idx in (prev_idx, curr_idx, next_idx):
                    continue
                if _point_in_triangle(polygon[other_idx], triangle):
                    contains_vertex = True
                    break

            if contains_vertex:
                continue

            triangles.append(triangle)
            del remaining[local_index]
            ear_found = True
            break

        if not ear_found:
            return None
        passes += 1

    if len(remaining) != 3:
        return None

    final_triangle = tuple(polygon[index] for index in remaining)
    if polygon_area(final_triangle) <= GEOM_EPSILON:
        return None

    triangles.append(final_triangle)
    return tuple(triangles)


def validate_polygon_points(points):
    """
    Enforce the polygon contract used by creation and rendering.

    A stored polygon is an ordered boundary vertex list for one outer ring.
    The ring stays open in storage, so the first vertex is not repeated at the end.
    Valid polygons need at least 3 distinct points, non-zero area, no duplicate
    consecutive points, no non-adjacent edge intersections, and may be convex or concave.
    """
    polygon = _open_polygon_points(points)

    if len(polygon) < 3:
        return False, polygon, "A polygon needs at least 3 points."
    if has_duplicate_consecutive_points(polygon):
        return False, polygon, "Polygon points cannot repeat consecutively."
    if len(_distinct_points(polygon)) < 3:
        return False, polygon, "A polygon needs at least 3 distinct points."
    if polygon_area(polygon) <= GEOM_EPSILON:
        return False, polygon, "Polygon area must be non-zero."

    edge_count = len(polygon)
    for edge_index in range(edge_count):
        a1 = polygon[edge_index]
        a2 = polygon[(edge_index + 1) % edge_count]
        for other_index in range(edge_index + 1, edge_count):
            if other_index == edge_index:
                continue
            if other_index == (edge_index + 1) % edge_count:
                continue
            if edge_index == (other_index + 1) % edge_count:
                continue

            b1 = polygon[other_index]
            b2 = polygon[(other_index + 1) % edge_count]
            if segments_intersect(a1, a2, b1, b2):
                return False, polygon, "Polygon edges cannot intersect."

    return True, normalize_polygon_winding(polygon), ""


def is_convex_polygon(points):
    """Return True when a polygon is strictly convex."""
    polygon = _open_polygon_points(points)
    if len(polygon) < 3:
        return False

    orientation = 0
    for index in range(len(polygon)):
        cross = _cross(
            polygon[index],
            polygon[(index + 1) % len(polygon)],
            polygon[(index + 2) % len(polygon)],
        )
        if abs(cross) <= GEOM_EPSILON:
            continue

        sign = 1 if cross > 0 else -1
        if orientation == 0:
            orientation = sign
        elif sign != orientation:
            return False

    return orientation != 0
