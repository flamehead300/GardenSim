import datetime
import math

from kivy.event import EventDispatcher
from kivy.properties import (
    BooleanProperty, ListProperty, NumericProperty,
    ObjectProperty, StringProperty,
)

from .utils import minutes_from_time_str, clone_shape, default_timezone_name
from .constants import (
    DEFAULT_CATEGORY,
    MAP_OVERLAY_CALIBRATION_IDLE,
    MAP_OVERLAY_CALIBRATION_MODES,
)


class GardenModel(EventDispatcher):
    """Holds the entire state of the Garden simulation."""
    width_ft = NumericProperty(60.0)
    height_ft = NumericProperty(60.0)
    scale = NumericProperty(20.0)
    offset_x = NumericProperty(0.0)
    offset_y = NumericProperty(0.0)

    lat = NumericProperty(40.7128)
    lon = NumericProperty(-74.0060)
    map_overlay_anchor_lat = NumericProperty(40.7128)
    map_overlay_anchor_lon = NumericProperty(-74.0060)
    map_overlay_rotation_deg = NumericProperty(0.0)
    map_overlay_y_axis_sign = NumericProperty(1.0)
    map_overlay_is_calibrated = BooleanProperty(False)
    map_overlay_anchor_locked = BooleanProperty(False)
    map_overlay_calibration_mode = StringProperty(MAP_OVERLAY_CALIBRATION_IDLE)
    map_overlay_calibration_a_x_ft = NumericProperty(0.0)
    map_overlay_calibration_a_y_ft = NumericProperty(0.0)
    map_overlay_calibration_a_lat = NumericProperty(40.7128)
    map_overlay_calibration_a_lon = NumericProperty(-74.0060)
    map_overlay_calibration_b_x_ft = NumericProperty(60.0)
    map_overlay_calibration_b_y_ft = NumericProperty(0.0)
    map_overlay_calibration_b_lat = NumericProperty(40.7128)
    map_overlay_calibration_b_lon = NumericProperty(-74.0060)
    timezone_name = StringProperty(default_timezone_name())
    date_str = StringProperty(datetime.date.today().isoformat())
    time_str = StringProperty(datetime.datetime.now().strftime("%H:%M:%S"))
    time_minutes = NumericProperty(minutes_from_time_str(datetime.datetime.now().strftime("%H:%M:%S")))
    sun_azimuth = NumericProperty(0.0)
    sun_elevation = NumericProperty(0.0)

    shapes = ListProperty([])
    draw_mode = ObjectProperty(None, allownone=True)
    drag_start = ObjectProperty(None, allownone=True)
    drag_rect = ObjectProperty(None, allownone=True)
    drag_circle = ObjectProperty(None, allownone=True)
    drag_strip = ObjectProperty(None, allownone=True)
    poly_points = ListProperty([])
    pending_plant = ObjectProperty(None, allownone=True)
    plant_preview = ObjectProperty(None, allownone=True)
    sunlight_overlay = ListProperty([])

    draw_category = StringProperty(DEFAULT_CATEGORY)
    snap_to_grid = BooleanProperty(False)
    grid_size = NumericProperty(1.0)
    snap_preview = ObjectProperty(None, allownone=True)
    selected_idx = NumericProperty(-1)
    move_mode = BooleanProperty(False)
    move_start = ObjectProperty(None, allownone=True)
    prop_visible = BooleanProperty(False)

    @staticmethod
    def _serialize_geom(value):
        """Convert tuple-backed geometry into JSON-friendly lists."""
        if isinstance(value, (list, tuple)):
            return [GardenModel._serialize_geom(item) for item in value]
        return value

    @staticmethod
    def _deserialize_geom(value):
        """Restore JSON list geometry back into immutable tuples."""
        if isinstance(value, list):
            return tuple(GardenModel._deserialize_geom(item) for item in value)
        return value

    @classmethod
    def _shape_from_dict(cls, raw_shape):
        """Restore one serialized shape payload."""
        if not isinstance(raw_shape, dict):
            raise ValueError("Serialized shapes must be dictionaries.")
        shape = dict(raw_shape)
        shape["geom"] = cls._deserialize_geom(shape.get("geom", ()))
        return shape

    def to_dict(self):
        """Serialize persistent garden state into a server-friendly payload."""
        return {
            "width_ft": self.width_ft,
            "height_ft": self.height_ft,
            "lat": self.lat,
            "lon": self.lon,
            "map_overlay_anchor_lat": self.map_overlay_anchor_lat,
            "map_overlay_anchor_lon": self.map_overlay_anchor_lon,
            "map_overlay_rotation_deg": self.map_overlay_rotation_deg,
            "map_overlay_y_axis_sign": self.map_overlay_y_axis_sign,
            "map_overlay_is_calibrated": self.map_overlay_is_calibrated,
            "map_overlay_anchor_locked": self.map_overlay_anchor_locked,
            "map_overlay_calibration_mode": self.map_overlay_calibration_mode,
            "map_overlay_calibration_a_x_ft": self.map_overlay_calibration_a_x_ft,
            "map_overlay_calibration_a_y_ft": self.map_overlay_calibration_a_y_ft,
            "map_overlay_calibration_a_lat": self.map_overlay_calibration_a_lat,
            "map_overlay_calibration_a_lon": self.map_overlay_calibration_a_lon,
            "map_overlay_calibration_b_x_ft": self.map_overlay_calibration_b_x_ft,
            "map_overlay_calibration_b_y_ft": self.map_overlay_calibration_b_y_ft,
            "map_overlay_calibration_b_lat": self.map_overlay_calibration_b_lat,
            "map_overlay_calibration_b_lon": self.map_overlay_calibration_b_lon,
            "timezone_name": self.timezone_name,
            "date_str": self.date_str,
            "time_str": self.time_str,
            "shapes": [
                {
                    **shape,
                    "geom": self._serialize_geom(shape.get("geom", ())),
                }
                for shape in self.shapes
            ],
        }

    @classmethod
    def from_dict(cls, payload):
        """Build a model instance from serialized persistent garden state."""
        if not isinstance(payload, dict):
            raise ValueError("Garden payload must be a dictionary.")

        model = cls()
        model.width_ft = float(payload.get("width_ft", model.width_ft))
        model.height_ft = float(payload.get("height_ft", model.height_ft))
        model.lat = float(payload.get("lat", model.lat))
        model.lon = float(payload.get("lon", model.lon))
        cls._restore_map_overlay_state(model, payload)
        model.timezone_name = str(payload.get("timezone_name", model.timezone_name))
        model.date_str = str(payload.get("date_str", model.date_str))
        model.time_str = str(payload.get("time_str", model.time_str))
        model.time_minutes = minutes_from_time_str(model.time_str)

        raw_shapes = payload.get("shapes", [])
        if not isinstance(raw_shapes, list):
            raise ValueError("Serialized shapes must be a list.")
        model.shapes = [cls._shape_from_dict(shape) for shape in raw_shapes]
        return model

    @staticmethod
    def _payload_float(payload, key, default):
        try:
            value = float(payload.get(key, default))
        except (TypeError, ValueError):
            return float(default)
        if not math.isfinite(value):
            return float(default)
        return value

    @staticmethod
    def _payload_bool(payload, key, default=False):
        value = payload.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @classmethod
    def _restore_map_overlay_state(cls, model, payload):
        model.map_overlay_anchor_lat = cls._payload_float(
            payload,
            "map_overlay_anchor_lat",
            model.lat,
        )
        model.map_overlay_anchor_lon = cls._payload_float(
            payload,
            "map_overlay_anchor_lon",
            model.lon,
        )
        model.map_overlay_rotation_deg = cls._payload_float(
            payload,
            "map_overlay_rotation_deg",
            0.0,
        )
        model.map_overlay_y_axis_sign = (
            1.0
            if cls._payload_float(payload, "map_overlay_y_axis_sign", 1.0) >= 0.0
            else -1.0
        )
        calibration_mode = str(
            payload.get("map_overlay_calibration_mode", MAP_OVERLAY_CALIBRATION_IDLE)
        )
        if calibration_mode not in MAP_OVERLAY_CALIBRATION_MODES:
            calibration_mode = MAP_OVERLAY_CALIBRATION_IDLE
        model.map_overlay_calibration_a_x_ft = cls._payload_float(
            payload,
            "map_overlay_calibration_a_x_ft",
            0.0,
        )
        model.map_overlay_calibration_a_y_ft = cls._payload_float(
            payload,
            "map_overlay_calibration_a_y_ft",
            0.0,
        )
        model.map_overlay_calibration_a_lat = cls._payload_float(
            payload,
            "map_overlay_calibration_a_lat",
            model.map_overlay_anchor_lat,
        )
        model.map_overlay_calibration_a_lon = cls._payload_float(
            payload,
            "map_overlay_calibration_a_lon",
            model.map_overlay_anchor_lon,
        )
        model.map_overlay_calibration_b_x_ft = cls._payload_float(
            payload,
            "map_overlay_calibration_b_x_ft",
            model.width_ft,
        )
        model.map_overlay_calibration_b_y_ft = cls._payload_float(
            payload,
            "map_overlay_calibration_b_y_ft",
            0.0,
        )
        model.map_overlay_calibration_b_lat = cls._payload_float(
            payload,
            "map_overlay_calibration_b_lat",
            model.map_overlay_anchor_lat,
        )
        model.map_overlay_calibration_b_lon = cls._payload_float(
            payload,
            "map_overlay_calibration_b_lon",
            model.map_overlay_anchor_lon,
        )

        required_keys = (
            "map_overlay_anchor_lat",
            "map_overlay_anchor_lon",
            "map_overlay_rotation_deg",
            "map_overlay_y_axis_sign",
            "map_overlay_calibration_a_x_ft",
            "map_overlay_calibration_a_y_ft",
            "map_overlay_calibration_a_lat",
            "map_overlay_calibration_a_lon",
            "map_overlay_calibration_b_x_ft",
            "map_overlay_calibration_b_y_ft",
            "map_overlay_calibration_b_lat",
            "map_overlay_calibration_b_lon",
        )
        model.map_overlay_is_calibrated = bool(
            cls._payload_bool(payload, "map_overlay_is_calibrated", False)
            and all(key in payload for key in required_keys)
        )
        model.map_overlay_anchor_locked = cls._payload_bool(
            payload,
            "map_overlay_anchor_locked",
            default=model.map_overlay_is_calibrated,
        )
        model.map_overlay_calibration_mode = (
            MAP_OVERLAY_CALIBRATION_IDLE
            if calibration_mode != MAP_OVERLAY_CALIBRATION_IDLE
            else calibration_mode
        )
