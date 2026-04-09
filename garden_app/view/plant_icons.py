"""Plant icon lookup and texture caching for the garden UI."""

from pathlib import Path


ICON_DIR = Path(__file__).resolve().parents[1] / "assets" / "plant_icons"
GENERIC_ICON_KEY = "generic"
ICON_EXT = ".png"

PLANT_ICON_BY_KEYWORD = (
    ("tomato", "tomato"),
    ("pepper", "pepper"),
    ("chili", "pepper"),
    ("jalapeno", "pepper"),
    ("eggplant", "eggplant"),
    ("cucumber", "vine"),
    ("pickles", "vine"),
    ("zucchini", "vine"),
    ("pumpkin", "squash"),
    ("butternut", "squash"),
    ("squash", "squash"),
    ("corn", "corn"),
    ("bean", "legume"),
    ("pea", "legume"),
    ("onion", "root"),
    ("leek", "root"),
    ("scallion", "root"),
    ("turnip", "root"),
    ("carrot", "root"),
    ("beet", "root"),
    ("radish", "root"),
    ("parsnip", "root"),
    ("broccoli", "brassica"),
    ("cauliflower", "brassica"),
    ("cabbage", "brassica"),
    ("brussels", "brassica"),
    ("kohlrabi", "brassica"),
    ("collard", "brassica"),
    ("kale", "brassica"),
    ("bok choy", "brassica"),
    ("lettuce", "leafy"),
    ("mache", "leafy"),
    ("chard", "leafy"),
    ("spinach", "leafy"),
    ("arugula", "leafy"),
    ("endive", "leafy"),
    ("cress", "leafy"),
    ("basil", "herb"),
    ("okra", "herb"),
    ("artichoke", "herb"),
    ("sunflower", "flower"),
)

_TEXTURE_CACHE = {}


def icon_key_for_plant(plant):
    """Return a stable icon key from explicit metadata or the plant name."""
    if isinstance(plant, dict):
        explicit_key = str(plant.get("icon_key", "")).strip().lower()
        if explicit_key:
            return explicit_key
        name = str(plant.get("name", "")).lower()
    else:
        name = str(plant).lower()

    for keyword, icon_key in PLANT_ICON_BY_KEYWORD:
        if keyword in name:
            return icon_key
    return GENERIC_ICON_KEY


def icon_source_for_key(icon_key):
    """Return the bundled PNG path for an icon key, falling back to generic."""
    clean_key = str(icon_key or GENERIC_ICON_KEY).strip().lower()
    candidate = ICON_DIR / f"{clean_key}{ICON_EXT}"
    if candidate.exists():
        return str(candidate)

    fallback = ICON_DIR / f"{GENERIC_ICON_KEY}{ICON_EXT}"
    if fallback.exists():
        return str(fallback)
    return ""


def resolve_icon_source(plant_or_key=None, icon_source=None):
    """Resolve an existing source path or derive one from a plant/key payload."""
    if icon_source:
        source_path = Path(str(icon_source))
        if source_path.exists():
            return str(source_path)

    if isinstance(plant_or_key, dict):
        source = plant_or_key.get("icon_source")
        if source and Path(str(source)).exists():
            return str(source)
        return icon_source_for_key(icon_key_for_plant(plant_or_key))

    return icon_source_for_key(plant_or_key or GENERIC_ICON_KEY)


def texture_for_icon(plant_or_key=None, icon_source=None):
    """Return a cached Kivy texture for an icon, or None if loading fails."""
    source = resolve_icon_source(plant_or_key, icon_source=icon_source)
    if not source:
        return None

    texture = _TEXTURE_CACHE.get(source)
    if texture is not None:
        return texture

    try:
        from kivy.core.window import Window  # noqa: F401
        from kivy.core.image import Image as CoreImage

        texture = CoreImage(source).texture
    except Exception:
        return None

    _TEXTURE_CACHE[source] = texture
    return texture
