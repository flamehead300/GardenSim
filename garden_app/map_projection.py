"""Pure geographic projection helpers for the garden map overlay."""

from __future__ import annotations

from math import atan2, cos, degrees, radians, sin


FT_TO_M = 0.3048
METERS_PER_DEG_LAT = 111_320.0
MIN_METERS_PER_DEG_LON = 1.0


def meters_per_deg_lon_at(lat):
    return max(
        MIN_METERS_PER_DEG_LON,
        abs(METERS_PER_DEG_LAT * cos(radians(float(lat)))),
    )


def normalize_y_axis_sign(y_axis_sign):
    try:
        return 1.0 if float(y_axis_sign) >= 0.0 else -1.0
    except (TypeError, ValueError):
        return 1.0


def garden_ft_to_east_north_m(x_ft, y_ft, theta_deg, y_axis_sign=1.0):
    theta = radians(float(theta_deg))
    signed_y_ft = float(y_ft) * normalize_y_axis_sign(y_axis_sign)
    east_ft = float(x_ft) * cos(theta) - signed_y_ft * sin(theta)
    north_ft = float(x_ft) * sin(theta) + signed_y_ft * cos(theta)
    return east_ft * FT_TO_M, north_ft * FT_TO_M


def east_north_m_to_latlon(anchor_lat, anchor_lon, east_m, north_m):
    anchor_lat = float(anchor_lat)
    anchor_lon = float(anchor_lon)
    return (
        anchor_lat + (float(north_m) / METERS_PER_DEG_LAT),
        anchor_lon + (float(east_m) / meters_per_deg_lon_at(anchor_lat)),
    )


def latlon_to_east_north_m(anchor_lat, anchor_lon, lat, lon):
    anchor_lat = float(anchor_lat)
    anchor_lon = float(anchor_lon)
    return (
        (float(lon) - anchor_lon) * meters_per_deg_lon_at(anchor_lat),
        (float(lat) - anchor_lat) * METERS_PER_DEG_LAT,
    )


def garden_ft_to_latlon(x_ft, y_ft, anchor_lat, anchor_lon, theta_deg, y_axis_sign=1.0):
    east_m, north_m = garden_ft_to_east_north_m(
        x_ft,
        y_ft,
        theta_deg,
        y_axis_sign=y_axis_sign,
    )
    return east_north_m_to_latlon(anchor_lat, anchor_lon, east_m, north_m)


def latlon_to_garden_ft(lat, lon, anchor_lat, anchor_lon, theta_deg, y_axis_sign=1.0):
    east_m, north_m = latlon_to_east_north_m(anchor_lat, anchor_lon, lat, lon)
    east_ft = east_m / FT_TO_M
    north_ft = north_m / FT_TO_M
    theta = radians(float(theta_deg))
    x_ft = east_ft * cos(theta) + north_ft * sin(theta)
    signed_y_ft = -east_ft * sin(theta) + north_ft * cos(theta)
    y_ft = signed_y_ft * normalize_y_axis_sign(y_axis_sign)
    return x_ft, y_ft


def normalize_degrees(angle_deg):
    return ((float(angle_deg) + 180.0) % 360.0) - 180.0


def calibrate_garden_overlay(local_a, geo_a, local_b, geo_b, y_axis_sign=1.0):
    ax_ft, ay_ft = float(local_a[0]), float(local_a[1])
    bx_ft, by_ft = float(local_b[0]), float(local_b[1])
    a_lat, a_lon = float(geo_a[0]), float(geo_a[1])
    b_lat, b_lon = float(geo_b[0]), float(geo_b[1])

    local_dx_ft = bx_ft - ax_ft
    local_dy_ft = by_ft - ay_ft
    local_distance_ft = (local_dx_ft * local_dx_ft + local_dy_ft * local_dy_ft) ** 0.5
    if local_distance_ft <= 0.0001:
        raise ValueError("Calibration local points must be distinct.")

    real_east_m, real_north_m = latlon_to_east_north_m(a_lat, a_lon, b_lat, b_lon)
    real_distance_m = (real_east_m * real_east_m + real_north_m * real_north_m) ** 0.5
    if real_distance_m <= 0.0001:
        raise ValueError("Calibration map points must be distinct.")

    signed_local_dy_ft = local_dy_ft * normalize_y_axis_sign(y_axis_sign)
    local_angle_deg = degrees(atan2(signed_local_dy_ft, local_dx_ft))
    real_angle_deg = degrees(atan2(real_north_m, real_east_m))
    theta_deg = normalize_degrees(real_angle_deg - local_angle_deg)

    offset_east_m, offset_north_m = garden_ft_to_east_north_m(
        ax_ft,
        ay_ft,
        theta_deg,
        y_axis_sign=y_axis_sign,
    )
    origin_lat = a_lat - (offset_north_m / METERS_PER_DEG_LAT)
    origin_lon = a_lon - (offset_east_m / meters_per_deg_lon_at(a_lat))
    return origin_lat, origin_lon, theta_deg
