"""Shared Kivy widget style dictionaries for runtime UI modules."""

BTN_FLAT = {
    "background_normal": "",
    "background_color": (0.15, 0.17, 0.19, 1),
    "color": (0.82, 0.88, 0.82, 1),
    "font_size": "13sp",
}

BTN_ACTION = {
    "background_normal": "",
    "background_color": (0.09, 0.42, 0.24, 1),
    "color": (0.9, 0.96, 0.9, 1),
    "font_size": "13sp",
    "bold": True,
}

BTN_DANGER = {
    "background_normal": "",
    "background_color": (0.5, 0.16, 0.14, 1),
    "color": (0.95, 0.9, 0.9, 1),
    "font_size": "13sp",
}

BTN_BLUE = {
    "background_normal": "",
    "background_color": (0.1, 0.32, 0.52, 1),
    "color": (0.9, 0.95, 1, 1),
    "font_size": "13sp",
}

INPUT_FLAT = {
    "background_normal": "",
    "background_color": (0.08, 0.09, 0.1, 1),
    "foreground_color": (0.86, 0.9, 0.86, 1),
    "cursor_color": (0.25, 0.55, 0.75, 1),
}


def style(base, **overrides):
    """Return a one-off style copy with local overrides applied."""
    merged = dict(base)
    merged.update(overrides)
    return merged
