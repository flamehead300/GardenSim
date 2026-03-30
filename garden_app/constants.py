from .utils import hex_to_rgba, available_timezone_names


COLOR_BG = hex_to_rgba("#1A2E1A")
COLOR_PANEL = hex_to_rgba("#243824")
COLOR_FRAME = hex_to_rgba("#2E4A2E")
COLOR_BUTTON = hex_to_rgba("#3A6B3A")
COLOR_BUTTON_ACTIVE = hex_to_rgba("#4CAF50")
COLOR_TEXT = hex_to_rgba("#D8EDD8")
COLOR_TEXT_DIM = hex_to_rgba("#7AAF7A")
COLOR_ACCENT = hex_to_rgba("#7DCE82")
COLOR_BORDER = hex_to_rgba("#3A5A3A")
COLOR_CANVAS = hex_to_rgba("#3A5C2A")
COLOR_GRID = hex_to_rgba("#4A7A3A")
COLOR_GRID_SNAP = hex_to_rgba("#FFFFFF", 0.12)
COLOR_LABEL_TEXT = hex_to_rgba("#C8E6C8")
COLOR_SHADOW = hex_to_rgba("#111111", 0.35)
COLOR_PREVIEW_FILL = hex_to_rgba("#FFFDE7", 0.55)
COLOR_PREVIEW_OUT = hex_to_rgba("#2196F3")
COLOR_SELECT = hex_to_rgba("#FF6600")
COLOR_SNAP_PREVIEW = hex_to_rgba("#FFFFFF")
COLOR_SUN = hex_to_rgba("#FFD740")
COLOR_SUN_ARROW = hex_to_rgba("#FF5252")
COLOR_SUN_BELOW = hex_to_rgba("#90CAF9")

DEFAULT_STRIP_WIDTH_FT = 0.10
MIN_STRIP_WIDTH_FT = 0.01
MIN_STRIP_LENGTH_FT = 0.01

CATEGORIES = {
    "Garden": {
        "height_ft": 0.0,
        "fill": hex_to_rgba("#90EE90"),
        "outline": hex_to_rgba("#2E8B22"),
    },
    "Foliage": {
        "height_ft": 0.5,
        "fill": hex_to_rgba("#3A7D44"),
        "outline": hex_to_rgba("#1B4F26"),
    },
    "Structure": {
        "height_ft": 10.0,
        "fill": hex_to_rgba("#B0B0B0"),
        "outline": hex_to_rgba("#606060"),
    },
}
DEFAULT_CATEGORY = "Garden"

TIMEZONE_OPTIONS = available_timezone_names()
