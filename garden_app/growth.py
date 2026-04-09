"""Plant growth state and tick logic for placed garden plants."""

from .simulation.constants import (
    DEFAULT_GROWTH_TICK_DAYS,
    DEFAULT_MATURITY_DAYS,
    DEFAULT_PLANT_FERTILIZER,
    DEFAULT_PLANT_HEALTH,
    DEFAULT_PLANT_GROWTH_RATE,
    DEFAULT_PLANT_MAX_HEALTH,
    DEFAULT_PLANT_NAME,
    DEFAULT_PLANT_VITALITY,
    DEFAULT_PLANT_WATER_CONSUMPTION,
    GROWTH_FRUITING_THRESHOLD,
    GROWTH_MATURE_THRESHOLD,
    GROWTH_SPROUT_THRESHOLD,
    GROWTH_STATE_DEAD,
    GROWTH_STATE_FRUITING,
    GROWTH_STATE_MATURE,
    GROWTH_STATE_SEED,
    GROWTH_STATE_SPROUT,
    HEALTH_DEAD_THRESHOLD,
    HEALTH_DECAY_PER_DRY_TICK,
    HEALTH_RECOVERY_PER_WET_TICK,
    MAX_GROWTH_PROGRESS,
    MIN_ELAPSED_SECONDS,
    MIN_GROWTH_PROGRESS,
    MIN_MATURITY_DAYS,
    MISSING_MATURITY_DAYS,
    MIN_PLANT_FERTILIZER,
    MIN_PLANT_MAX_HEALTH,
    MIN_PLANT_VITALITY,
    PLANT_STATES,
    VITALITY_DECAY_PER_DRY_TICK,
    VITALITY_RECOVERY_PER_WET_TICK,
)


GARDEN_PLANTS = [
    {"id": 1, "name": "Tomato - Red Beefsteak", "maturity_days": 85},
    {"id": 2, "name": "Tomato - Large Red Cherry", "maturity_days": 72},
    {"id": 3, "name": "Tomato - Roma VF", "maturity_days": 78},
    {"id": 4, "name": "Hot Pepper - Cayenne", "maturity_days": 75},
    {"id": 5, "name": "Hot Pepper - Jalapeno", "maturity_days": 72},
    {"id": 6, "name": "Sweet Bell Pepper - California Wonder", "maturity_days": 75},
    {"id": 7, "name": "Mild Chili Pepper - Poblano", "maturity_days": 75},
    {"id": 8, "name": "Pepper - Chocolate Beauty", "maturity_days": 75},
    {"id": 9, "name": "Pepper - Purple Beauty", "maturity_days": 75},
    {"id": 10, "name": "Eggplant - Black Beauty", "maturity_days": 75},
    {"id": 11, "name": "Okra - Clemson Spineless 80", "maturity_days": 55},
    {"id": 12, "name": "Cucumber - Marketmore 76", "maturity_days": 60},
    {"id": 13, "name": "Cucumber - Boston Pickling", "maturity_days": 55},
    {"id": 14, "name": "Yellow Squash - Golden Summer Crookneck", "maturity_days": 52},
    {"id": 15, "name": "Butternut Squash - Waltham Butternut", "maturity_days": 95},
    {"id": 16, "name": "Zucchini - Dark Green", "maturity_days": 50},
    {"id": 17, "name": "Pumpkin - Sugar Pie", "maturity_days": 95},
    {"id": 18, "name": "Pumpkin - Connecticut Field", "maturity_days": 110},
    {"id": 19, "name": "Corn - Golden X Bantam F1", "maturity_days": 80},
    {"id": 20, "name": "Sweet Corn - Country Gentleman White Open Pollinated", "maturity_days": 90},
    {"id": 21, "name": "Bean - Contender", "maturity_days": 50},
    {"id": 22, "name": "Pea - Oregon Sugar Pod II", "maturity_days": 60},
    {"id": 23, "name": "Long Day Onion - Yellow Sweet Spanish", "maturity_days": 110},
    {"id": 24, "name": "Short Day Onion - Red Burgundy", "maturity_days": 100},
    {"id": 25, "name": "Scallion Onion - Tokyo Long White", "maturity_days": 65},
    {"id": 26, "name": "Leek - American Flag", "maturity_days": 110},
    {"id": 27, "name": "Turnip - Purple Top White Globe", "maturity_days": 55},
    {"id": 28, "name": "Carrot - Imperator 58", "maturity_days": 75},
    {"id": 29, "name": "Carrot - Royal Chantenay", "maturity_days": 70},
    {"id": 30, "name": "Carrot - Scarlet Nantes", "maturity_days": 68},
    {"id": 31, "name": "Beet - Detroit Dark Red", "maturity_days": 60},
    {"id": 32, "name": "Radish - Cherry Belle", "maturity_days": 22},
    {"id": 33, "name": "Radish - Red Arrow", "maturity_days": 28},
    {"id": 34, "name": "Radish - White Icicle", "maturity_days": 30},
    {"id": 35, "name": "Parsnips", "maturity_days": 110},
    {"id": 36, "name": "Lettuce - Romaine", "maturity_days": 60},
    {"id": 37, "name": "Lettuce - Iceberg", "maturity_days": 75},
    {"id": 38, "name": "Lettuce - Buttercrunch", "maturity_days": 58},
    {"id": 39, "name": "Lettuce - Cimarron Red", "maturity_days": 55},
    {"id": 40, "name": "Mache / Corn Salad", "maturity_days": 50},
    {"id": 41, "name": "Swiss Chard - Ruby Red", "maturity_days": 55},
    {"id": 42, "name": "Collard - Georgia Southern", "maturity_days": 60},
    {"id": 43, "name": "Spinach - Bloomsdale Long Standing", "maturity_days": 45},
    {"id": 44, "name": "Arugula - Roquette", "maturity_days": 40},
    {"id": 45, "name": "Endive - Curled Ruffec", "maturity_days": 55},
    {"id": 46, "name": "Cress - Curled", "maturity_days": 30},
    {"id": 47, "name": "Kale - Dwarf Siberian", "maturity_days": 55},
    {"id": 48, "name": "Bok Choy - Pak Choi Canton White Stem", "maturity_days": 45},
    {"id": 49, "name": "Broccoli - Waltham 29", "maturity_days": 75},
    {"id": 50, "name": "Broccoli Raab - Spring Rapini", "maturity_days": 45},
    {"id": 51, "name": "Kohlrabi - White Vienna", "maturity_days": 55},
    {"id": 52, "name": "Cauliflower - Snowball Y Improved", "maturity_days": 75},
    {"id": 53, "name": "Cabbage - Golden Acre", "maturity_days": 65},
    {"id": 54, "name": "Brussels Sprouts", "maturity_days": 90},
    {"id": 55, "name": "Sunflower - Black Oil", "maturity_days": 80},
    {"id": 56, "name": "Artichoke - Green Globe", "maturity_days": 120},
    {"id": 57, "name": "Basil - Thai", "maturity_days": 60},
    {"id": 58, "name": "Peas - small bag", "maturity_days": 60},
    {"id": 59, "name": "Pickles - small bag, assumed pickling cucumber seed", "maturity_days": 55},
]

for _plant in GARDEN_PLANTS:
    _plant["progress_per_day"] = MAX_GROWTH_PROGRESS / _plant["maturity_days"]
    _plant["growth_progress"] = MIN_GROWTH_PROGRESS
    _plant["growth_state"] = GROWTH_STATE_SEED

_MATURITY_DAYS_BY_ID = {plant["id"]: plant["maturity_days"] for plant in GARDEN_PLANTS}
_MATURITY_DAYS_BY_NAME = {
    plant["name"].casefold(): plant["maturity_days"] for plant in GARDEN_PLANTS
}


def _clean_name(name):
    return str(name or "").replace("\u2014", "-").replace("\u2013", "-").casefold().strip()


def maturity_days_for_plant(plant):
    """Return maturity days from explicit metadata, id, or normalized name."""
    if not isinstance(plant, dict):
        return DEFAULT_MATURITY_DAYS

    try:
        explicit_days = int(plant.get("maturity_days", MISSING_MATURITY_DAYS))
        if explicit_days >= MIN_MATURITY_DAYS:
            return explicit_days
    except (TypeError, ValueError):
        pass

    try:
        plant_id = int(plant.get("id"))
    except (TypeError, ValueError):
        plant_id = None
    if plant_id in _MATURITY_DAYS_BY_ID:
        return _MATURITY_DAYS_BY_ID[plant_id]

    return _MATURITY_DAYS_BY_NAME.get(_clean_name(plant.get("name")), DEFAULT_MATURITY_DAYS)


def growth_state_for_progress(progress, current_state=None):
    """Map a 0-100 growth percentage to the active plant state."""
    if current_state == GROWTH_STATE_DEAD:
        return GROWTH_STATE_DEAD

    try:
        value = float(progress)
    except (TypeError, ValueError):
        value = MIN_GROWTH_PROGRESS

    if value < GROWTH_SPROUT_THRESHOLD:
        return GROWTH_STATE_SEED
    if value < GROWTH_MATURE_THRESHOLD:
        return GROWTH_STATE_SPROUT
    if value < GROWTH_FRUITING_THRESHOLD:
        return GROWTH_STATE_MATURE
    return GROWTH_STATE_FRUITING


def growth_sprite_for_state(state):
    """Return a stable sprite key for state-specific rendering."""
    state_value = str(state or GROWTH_STATE_SEED).upper()
    if state_value not in PLANT_STATES:
        state_value = GROWTH_STATE_SEED
    return state_value.casefold()


def output_for_plant(plant):
    """Return the ripe output name once a plant reaches full progress."""
    name = str((plant or {}).get("name", DEFAULT_PLANT_NAME))
    clean_name = _clean_name(name)
    if "tomato" in clean_name:
        return "Ripe Tomatoes"
    if "carrot" in clean_name:
        return "Ripe Carrots"
    if "pepper" in clean_name or "chili" in clean_name:
        return "Ripe Peppers"
    if "cucumber" in clean_name or "pickle" in clean_name:
        return "Ripe Cucumbers"
    crop_name = name.split(" - ", 1)[0].strip() or DEFAULT_PLANT_NAME
    return f"Ripe {crop_name}"


def ensure_growth_payload(plant):
    """Return a plant dict with growth defaults filled in."""
    payload = dict(plant or {})
    maturity_days = maturity_days_for_plant(payload)
    payload["maturity_days"] = maturity_days
    payload["progress_per_day"] = MAX_GROWTH_PROGRESS / max(MIN_MATURITY_DAYS, maturity_days)

    try:
        progress = float(payload.get("growth_progress", MIN_GROWTH_PROGRESS))
    except (TypeError, ValueError):
        progress = MIN_GROWTH_PROGRESS
    payload["growth_progress"] = max(MIN_GROWTH_PROGRESS, min(MAX_GROWTH_PROGRESS, progress))

    state = str(payload.get("growth_state") or "").upper()
    if state not in PLANT_STATES:
        state = growth_state_for_progress(payload["growth_progress"])
    elif state != GROWTH_STATE_DEAD:
        state = growth_state_for_progress(payload["growth_progress"], current_state=state)
    payload["growth_state"] = state
    payload["growth_sprite"] = growth_sprite_for_state(state)
    try:
        payload["growth_rate"] = float(payload.get("growth_rate", DEFAULT_PLANT_GROWTH_RATE))
    except (TypeError, ValueError):
        payload["growth_rate"] = DEFAULT_PLANT_GROWTH_RATE
    try:
        payload["water_consumption"] = float(
            payload.get("water_consumption", DEFAULT_PLANT_WATER_CONSUMPTION)
        )
    except (TypeError, ValueError):
        payload["water_consumption"] = DEFAULT_PLANT_WATER_CONSUMPTION

    try:
        payload["fertilizer"] = max(
            MIN_PLANT_FERTILIZER,
            float(payload.get("fertilizer", DEFAULT_PLANT_FERTILIZER)),
        )
    except (TypeError, ValueError):
        payload["fertilizer"] = DEFAULT_PLANT_FERTILIZER

    try:
        payload["max_health"] = max(
            MIN_PLANT_MAX_HEALTH,
            float(payload.get("max_health", DEFAULT_PLANT_MAX_HEALTH)),
        )
    except (TypeError, ValueError):
        payload["max_health"] = DEFAULT_PLANT_MAX_HEALTH
    try:
        health = float(payload.get("health", DEFAULT_PLANT_HEALTH))
    except (TypeError, ValueError):
        health = DEFAULT_PLANT_HEALTH
    payload["health"] = max(HEALTH_DEAD_THRESHOLD, min(payload["max_health"], health))
    try:
        vitality = float(payload.get("vitality", DEFAULT_PLANT_VITALITY))
    except (TypeError, ValueError):
        vitality = DEFAULT_PLANT_VITALITY
    payload["vitality"] = max(MIN_PLANT_VITALITY, min(DEFAULT_PLANT_VITALITY, vitality))

    payload["has_water"] = bool(payload.get("has_water", False))
    payload["has_fertilizer"] = bool(payload["fertilizer"] > MIN_PLANT_FERTILIZER)

    if payload["health"] <= HEALTH_DEAD_THRESHOLD:
        payload["growth_state"] = GROWTH_STATE_DEAD
        payload["growth_sprite"] = growth_sprite_for_state(GROWTH_STATE_DEAD)

    if payload["growth_progress"] >= MAX_GROWTH_PROGRESS and not payload.get("output"):
        payload["output"] = output_for_plant(payload)
    return payload


def build_growth_payload(plant):
    """Build initial growth metadata for a catalog plant."""
    return ensure_growth_payload(plant)


def update_growth(plant, tick_days=DEFAULT_GROWTH_TICK_DAYS, has_water=True, has_fertilizer=True):
    """Advance one plant's growth in-place when water and fertilizer are present."""
    payload = ensure_growth_payload(plant)
    plant.clear()
    plant.update(payload)

    try:
        days = max(MIN_ELAPSED_SECONDS, float(tick_days))
    except (TypeError, ValueError):
        days = MIN_ELAPSED_SECONDS
    if days <= MIN_ELAPSED_SECONDS:
        return False

    if plant["growth_state"] == GROWTH_STATE_DEAD:
        return False

    plant["has_water"] = bool(has_water)
    plant["has_fertilizer"] = bool(has_fertilizer)
    if not plant["has_water"] or not plant["has_fertilizer"]:
        before_health = (plant["health"], plant["vitality"], plant["growth_state"])
        plant["health"] = max(HEALTH_DEAD_THRESHOLD, plant["health"] - HEALTH_DECAY_PER_DRY_TICK)
        plant["vitality"] = max(MIN_PLANT_VITALITY, plant["vitality"] - VITALITY_DECAY_PER_DRY_TICK)
        if plant["health"] <= HEALTH_DEAD_THRESHOLD:
            plant["growth_state"] = GROWTH_STATE_DEAD
            plant["growth_sprite"] = growth_sprite_for_state(GROWTH_STATE_DEAD)
        return before_health != (plant["health"], plant["vitality"], plant["growth_state"])

    before_health = (plant["health"], plant["vitality"])
    plant["health"] = min(plant["max_health"], plant["health"] + HEALTH_RECOVERY_PER_WET_TICK)
    plant["vitality"] = min(DEFAULT_PLANT_VITALITY, plant["vitality"] + VITALITY_RECOVERY_PER_WET_TICK)

    if plant["health"] <= HEALTH_DEAD_THRESHOLD:
        plant["growth_state"] = GROWTH_STATE_DEAD
        plant["growth_sprite"] = growth_sprite_for_state(GROWTH_STATE_DEAD)
        return False

    before = (
        plant["growth_progress"],
        plant["growth_state"],
        plant.get("growth_sprite"),
        plant.get("output"),
        *before_health,
    )
    plant["growth_progress"] = min(
        MAX_GROWTH_PROGRESS,
        plant["growth_progress"]
        + plant["progress_per_day"] * days * (plant["vitality"] / DEFAULT_PLANT_VITALITY),
    )
    plant["growth_state"] = growth_state_for_progress(plant["growth_progress"])
    plant["growth_sprite"] = growth_sprite_for_state(plant["growth_state"])
    if plant["growth_progress"] >= MAX_GROWTH_PROGRESS:
        plant["output"] = output_for_plant(plant)

    after = (
        plant["growth_progress"],
        plant["growth_state"],
        plant.get("growth_sprite"),
        plant.get("output"),
        plant["health"],
        plant["vitality"],
    )
    return after != before
