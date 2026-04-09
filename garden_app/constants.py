from .utils import hex_to_rgba, available_timezone_names


COLOR_BG = hex_to_rgba("#0E1A0E")
COLOR_PANEL = hex_to_rgba("#162416")
COLOR_FRAME = hex_to_rgba("#1F331F")
COLOR_BUTTON = hex_to_rgba("#244A24")
COLOR_BUTTON_ACTIVE = hex_to_rgba("#2F7A35")
COLOR_TEXT = hex_to_rgba("#C7DDC7")
COLOR_TEXT_DIM = hex_to_rgba("#6F9A6F")
COLOR_ACCENT = hex_to_rgba("#63A96A")
COLOR_BORDER = hex_to_rgba("#284428")
COLOR_CANVAS = hex_to_rgba("#263F1F")
COLOR_GRID = hex_to_rgba("#345A2A")
COLOR_GRID_SNAP = hex_to_rgba("#FFFFFF", 0.06)
COLOR_LABEL_TEXT = hex_to_rgba("#AAC8AA")
COLOR_SHADOW = hex_to_rgba("#111111", 0.35)
COLOR_PREVIEW_FILL = hex_to_rgba("#FFFDE7", 0.35)
COLOR_PREVIEW_OUT = hex_to_rgba("#1B76B7")
COLOR_SELECT = hex_to_rgba("#CC5200")
COLOR_SNAP_PREVIEW = hex_to_rgba("#D7EAD7")
COLOR_SUN = hex_to_rgba("#D9A920")
COLOR_SUN_ARROW = hex_to_rgba("#D13C3C")
COLOR_SUN_BELOW = hex_to_rgba("#6DA8D8")

DEFAULT_STRIP_WIDTH_FT = 0.10
MIN_STRIP_WIDTH_FT = 0.01
MIN_STRIP_LENGTH_FT = 0.01

MAP_OVERLAY_CALIBRATION_IDLE = "idle"
MAP_OVERLAY_CALIBRATION_TWO_POINT = "two_point"
MAP_OVERLAY_CALIBRATION_MODES = (
    MAP_OVERLAY_CALIBRATION_IDLE,
    MAP_OVERLAY_CALIBRATION_TWO_POINT,
)


CATEGORIES = {
    "Garden": {
        "height_ft": 0.0,
        "fill": hex_to_rgba("#5F9D5F"),
        "outline": hex_to_rgba("#236E2A"),
    },
    "Foliage": {
        "height_ft": 0.5,
        "fill": hex_to_rgba("#2C6333"),
        "outline": hex_to_rgba("#1B4F26"),
    },
    "Plant": {
        "height_ft": 0.0,
        "fill": hex_to_rgba("#55AA5E", 0.35),
        "outline": hex_to_rgba("#1F7A3A"),
    },
    "Irrigation Hose": {
        "height_ft": 0.0,
        "fill": hex_to_rgba("#2D79B8", 0.65),
        "outline": hex_to_rgba("#0A4A8A"),
    },
    "Structure": {
        "height_ft": 10.0,
        "fill": hex_to_rgba("#787878"),
        "outline": hex_to_rgba("#4A4A4A"),
    },
}
DEFAULT_CATEGORY = "Garden"

TIMEZONE_OPTIONS = available_timezone_names()
