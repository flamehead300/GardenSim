import datetime

from kivy.event import EventDispatcher
from kivy.properties import (
    BooleanProperty, ListProperty, NumericProperty,
    ObjectProperty, StringProperty,
)

from .utils import minutes_from_time_str, clone_shape, default_timezone_name
from .constants import DEFAULT_CATEGORY


class GardenModel(EventDispatcher):
    """Holds the entire state of the Garden simulation."""
    width_ft = NumericProperty(60.0)
    height_ft = NumericProperty(60.0)
    scale = NumericProperty(20.0)
    offset_x = NumericProperty(0.0)
    offset_y = NumericProperty(0.0)

    lat = NumericProperty(40.7128)
    lon = NumericProperty(-74.0060)
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
        model.timezone_name = str(payload.get("timezone_name", model.timezone_name))
        model.date_str = str(payload.get("date_str", model.date_str))
        model.time_str = str(payload.get("time_str", model.time_str))
        model.time_minutes = minutes_from_time_str(model.time_str)

        raw_shapes = payload.get("shapes", [])
        if not isinstance(raw_shapes, list):
            raise ValueError("Serialized shapes must be a list.")
        model.shapes = [cls._shape_from_dict(shape) for shape in raw_shapes]
        return model
