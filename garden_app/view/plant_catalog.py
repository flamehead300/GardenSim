from kivy.lang import Builder
from kivy.properties import BooleanProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp

# These imports register RecycleView widgets for KV loading.
from kivy.uix.recycleboxlayout import RecycleBoxLayout  # noqa: F401
from kivy.uix.recycleview import RecycleView  # noqa: F401

from ..growth import build_growth_payload
from .plant_icons import icon_key_for_plant, icon_source_for_key


PLANT_CATALOG = [
    {"id": 1, "name": "Tomato - Red Beefsteak", "sunCat": "full", "waterCat": "high", "tempCat": "warm", "timingCat": "indoor-late-apr", "timingText": "Start indoors in late April; transplant outside in late May to early June once frost risk is low.", "timingOrder": 3},
    {"id": 2, "name": "Tomato - Large Red Cherry", "sunCat": "full", "waterCat": "high", "tempCat": "warm", "timingCat": "indoor-late-apr", "timingText": "Start indoors in late April; transplant outside in late May to early June once frost risk is low.", "timingOrder": 3},
    {"id": 3, "name": "Tomato - Roma VF", "sunCat": "full", "waterCat": "high", "tempCat": "warm", "timingCat": "indoor-late-apr", "timingText": "Start indoors in late April; transplant outside in late May to early June once frost risk is low.", "timingOrder": 3},
    {"id": 4, "name": "Hot Pepper - Cayenne", "sunCat": "full", "waterCat": "medium", "tempCat": "hot", "timingCat": "indoor-now", "timingText": "Start indoors now; set outside in late May to early June after warm nights arrive.", "timingOrder": 1},
    {"id": 5, "name": "Hot Pepper - Jalapeno", "sunCat": "full", "waterCat": "medium", "tempCat": "hot", "timingCat": "indoor-now", "timingText": "Start indoors now; set outside in late May to early June after warm nights arrive.", "timingOrder": 1},
    {"id": 6, "name": "Sweet Bell Pepper - California Wonder", "sunCat": "full", "waterCat": "medium", "tempCat": "hot", "timingCat": "indoor-now", "timingText": "Start indoors now; set outside in late May to early June after warm nights arrive.", "timingOrder": 1},
    {"id": 7, "name": "Mild Chili Pepper - Poblano", "sunCat": "full", "waterCat": "medium", "tempCat": "hot", "timingCat": "indoor-now", "timingText": "Start indoors now; set outside in late May to early June after warm nights arrive.", "timingOrder": 1},
    {"id": 8, "name": "Pepper - Chocolate Beauty", "sunCat": "full", "waterCat": "medium", "tempCat": "hot", "timingCat": "indoor-now", "timingText": "Start indoors now; set outside in late May to early June after warm nights arrive.", "timingOrder": 1},
    {"id": 9, "name": "Pepper - Purple Beauty", "sunCat": "full", "waterCat": "medium", "tempCat": "hot", "timingCat": "indoor-now", "timingText": "Start indoors now; set outside in late May to early June after warm nights arrive.", "timingOrder": 1},
    {"id": 10, "name": "Eggplant - Black Beauty", "sunCat": "full", "waterCat": "high", "tempCat": "hot", "timingCat": "indoor-now", "timingText": "Start indoors now; transplant outside in late May to early June after the weather is reliably warm.", "timingOrder": 1},
    {"id": 11, "name": "Okra - Clemson Spineless 80", "sunCat": "full", "waterCat": "low", "tempCat": "hot", "timingCat": "direct-mid-may", "timingText": "Direct sow in mid-May once the soil has warmed.", "timingOrder": 5},
    {"id": 12, "name": "Cucumber - Marketmore 76", "sunCat": "full", "waterCat": "high", "tempCat": "hot", "timingCat": "indoor-early-may", "timingText": "Start indoors in early May or direct sow later; plant out in late May to early June.", "timingOrder": 4},
    {"id": 13, "name": "Cucumber - Boston Pickling", "sunCat": "full", "waterCat": "high", "tempCat": "hot", "timingCat": "indoor-early-may", "timingText": "Start indoors in early May or direct sow later; plant out in late May to early June.", "timingOrder": 4},
    {"id": 14, "name": "Yellow Squash - Golden Summer Crookneck", "sunCat": "full", "waterCat": "high", "tempCat": "hot", "timingCat": "indoor-early-may", "timingText": "Start indoors in early May or direct sow later; plant out in late May to early June.", "timingOrder": 4},
    {"id": 15, "name": "Butternut Squash - Waltham Butternut", "sunCat": "full", "waterCat": "high", "tempCat": "hot", "timingCat": "indoor-early-may", "timingText": "Start indoors in early May or direct sow later; plant out in late May to early June.", "timingOrder": 4},
    {"id": 16, "name": "Zucchini - Dark Green", "sunCat": "full", "waterCat": "high", "tempCat": "hot", "timingCat": "indoor-early-may", "timingText": "Start indoors in early May or direct sow later; plant out in late May to early June.", "timingOrder": 4},
    {"id": 17, "name": "Pumpkin - Sugar Pie", "sunCat": "full", "waterCat": "high", "tempCat": "hot", "timingCat": "indoor-early-may", "timingText": "Start indoors in early May or direct sow later; plant out in late May to early June.", "timingOrder": 4},
    {"id": 18, "name": "Pumpkin - Connecticut Field", "sunCat": "full", "waterCat": "high", "tempCat": "hot", "timingCat": "indoor-early-may", "timingText": "Start indoors in early May or direct sow later; plant out in late May to early June.", "timingOrder": 4},
    {"id": 19, "name": "Corn - Golden X Bantam F1", "sunCat": "full", "waterCat": "high", "tempCat": "warm", "timingCat": "direct-mid-may", "timingText": "Direct sow in mid-May once soil is warmer and frost danger is mostly past.", "timingOrder": 5},
    {"id": 20, "name": "Sweet Corn - Country Gentleman White Open Pollinated", "sunCat": "full", "waterCat": "high", "tempCat": "warm", "timingCat": "direct-mid-may", "timingText": "Direct sow in mid-May once soil is warmer and frost danger is mostly past.", "timingOrder": 5},
    {"id": 21, "name": "Bean - Contender", "sunCat": "full", "waterCat": "medium", "tempCat": "warm", "timingCat": "direct-mid-may", "timingText": "Direct sow in mid-May after frost danger eases and the soil has warmed.", "timingOrder": 5},
    {"id": 22, "name": "Pea - Oregon Sugar Pod II", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April as soon as the soil is workable.", "timingOrder": 2},
    {"id": 23, "name": "Long Day Onion - Yellow Sweet Spanish", "sunCat": "full", "waterCat": "high", "tempCat": "mild", "timingCat": "direct-late-apr", "timingText": "Sow or set out in late April.", "timingOrder": 2},
    {"id": 24, "name": "Short Day Onion - Red Burgundy", "sunCat": "full", "waterCat": "high", "tempCat": "mild", "timingCat": "direct-late-apr", "timingText": "Sow or set out in late April.", "timingOrder": 2},
    {"id": 25, "name": "Scallion Onion - Tokyo Long White", "sunCat": "full", "waterCat": "high", "tempCat": "mild", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April.", "timingOrder": 2},
    {"id": 26, "name": "Leek - American Flag", "sunCat": "full", "waterCat": "high", "tempCat": "mild", "timingCat": "direct-late-apr", "timingText": "Direct sow or transplant in late April.", "timingOrder": 2},
    {"id": 27, "name": "Turnip - Purple Top White Globe", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April.", "timingOrder": 2},
    {"id": 28, "name": "Carrot - Imperator 58", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April and keep evenly moist during germination.", "timingOrder": 2},
    {"id": 29, "name": "Carrot - Royal Chantenay", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April and keep evenly moist during germination.", "timingOrder": 2},
    {"id": 30, "name": "Carrot - Scarlet Nantes", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April and keep evenly moist during germination.", "timingOrder": 2},
    {"id": 31, "name": "Beet - Detroit Dark Red", "sunCat": "part", "waterCat": "medium", "tempCat": "mild", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April.", "timingOrder": 2},
    {"id": 32, "name": "Radish - Cherry Belle", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April; succession sow for repeat harvests.", "timingOrder": 2},
    {"id": 33, "name": "Radish - Red Arrow", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April; succession sow for repeat harvests.", "timingOrder": 2},
    {"id": 34, "name": "Radish - White Icicle", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April; succession sow for repeat harvests.", "timingOrder": 2},
    {"id": 35, "name": "Parsnips", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April and keep consistently moist while germinating.", "timingOrder": 2},
    {"id": 36, "name": "Lettuce - Romaine", "sunCat": "shade", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April; afternoon shade helps once summer heat increases.", "timingOrder": 2},
    {"id": 37, "name": "Lettuce - Iceberg", "sunCat": "shade", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April; afternoon shade helps once summer heat increases.", "timingOrder": 2},
    {"id": 38, "name": "Lettuce - Buttercrunch", "sunCat": "shade", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April; afternoon shade helps once summer heat increases.", "timingOrder": 2},
    {"id": 39, "name": "Lettuce - Cimarron Red", "sunCat": "shade", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April; afternoon shade helps once summer heat increases.", "timingOrder": 2},
    {"id": 40, "name": "Mache / Corn Salad", "sunCat": "shade", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April in cooler conditions.", "timingOrder": 2},
    {"id": 41, "name": "Swiss Chard - Ruby Red", "sunCat": "part", "waterCat": "medium", "tempCat": "mild", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April.", "timingOrder": 2},
    {"id": 42, "name": "Collard - Georgia Southern", "sunCat": "part", "waterCat": "medium", "tempCat": "mild", "timingCat": "direct-late-apr", "timingText": "Direct sow or transplant in late April.", "timingOrder": 2},
    {"id": 43, "name": "Spinach - Bloomsdale Long Standing", "sunCat": "shade", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April and keep evenly moist.", "timingOrder": 2},
    {"id": 44, "name": "Arugula - Roquette", "sunCat": "shade", "waterCat": "medium", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April.", "timingOrder": 2},
    {"id": 45, "name": "Endive - Curled Ruffec", "sunCat": "shade", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April.", "timingOrder": 2},
    {"id": 46, "name": "Cress - Curled", "sunCat": "shade", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April.", "timingOrder": 2},
    {"id": 47, "name": "Kale - Dwarf Siberian", "sunCat": "part", "waterCat": "medium", "tempCat": "mild", "timingCat": "direct-late-apr", "timingText": "Direct sow or transplant in late April.", "timingOrder": 2},
    {"id": 48, "name": "Bok Choy - Pak Choi Canton White Stem", "sunCat": "shade", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April; bolts more easily in heat.", "timingOrder": 2},
    {"id": 49, "name": "Broccoli - Waltham 29", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "indoor-now", "timingText": "Start indoors now; transplant outdoors in late April to early May.", "timingOrder": 1},
    {"id": 50, "name": "Broccoli Raab - Spring Rapini", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April.", "timingOrder": 2},
    {"id": 51, "name": "Kohlrabi - White Vienna", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April.", "timingOrder": 2},
    {"id": 52, "name": "Cauliflower - Snowball Y Improved", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "indoor-now", "timingText": "Start indoors now; transplant outdoors in late April to early May.", "timingOrder": 1},
    {"id": 53, "name": "Cabbage - Golden Acre", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "indoor-now", "timingText": "Start indoors now; transplant outdoors in late April to early May.", "timingOrder": 1},
    {"id": 54, "name": "Brussels Sprouts", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "indoor-now", "timingText": "Start indoors now; transplant outdoors in late April to early May.", "timingOrder": 1},
    {"id": 55, "name": "Sunflower - Black Oil", "sunCat": "full", "waterCat": "low", "tempCat": "warm", "timingCat": "direct-mid-may", "timingText": "Direct sow in mid-May after frost danger has mostly passed.", "timingOrder": 5},
    {"id": 56, "name": "Artichoke - Green Globe", "sunCat": "full", "waterCat": "high", "tempCat": "mild", "timingCat": "indoor-now", "timingText": "Start indoors now; transplant outside after hardening off in late April to early May.", "timingOrder": 1},
    {"id": 57, "name": "Basil - Thai", "sunCat": "full", "waterCat": "high", "tempCat": "hot", "timingCat": "indoor-now", "timingText": "Start indoors now; plant outside in late May to early June after frost danger is fully past.", "timingOrder": 1},
    {"id": 58, "name": "Peas - small bag", "sunCat": "part", "waterCat": "high", "tempCat": "cool", "timingCat": "direct-late-apr", "timingText": "Direct sow in late April as soon as the soil is workable.", "timingOrder": 2},
    {"id": 59, "name": "Pickles - small bag, assumed pickling cucumber seed", "sunCat": "full", "waterCat": "high", "tempCat": "hot", "timingCat": "indoor-early-may", "timingText": "Start indoors in early May or direct sow later; plant out in late May to early June.", "timingOrder": 4},
]

ROOT_RADIUS_BY_KEYWORD = (
    ("pumpkin", 5.0),
    ("butternut", 4.0),
    ("squash", 3.0),
    ("zucchini", 3.0),
    ("cucumber", 2.0),
    ("pickles", 2.0),
    ("tomato", 1.5),
    ("corn", 1.5),
    ("sunflower", 1.5),
    ("artichoke", 2.0),
    ("okra", 1.25),
    ("eggplant", 1.25),
    ("pepper", 1.0),
    ("chili", 1.0),
    ("broccoli", 1.0),
    ("cauliflower", 1.0),
    ("cabbage", 1.0),
    ("brussels", 1.0),
    ("kohlrabi", 0.8),
    ("basil", 0.75),
    ("bean", 0.75),
    ("pea", 0.5),
    ("carrot", 0.5),
    ("parsnip", 0.5),
    ("beet", 0.5),
    ("turnip", 0.5),
    ("radish", 0.35),
    ("onion", 0.35),
    ("leek", 0.35),
    ("scallion", 0.25),
    ("lettuce", 0.5),
    ("spinach", 0.5),
    ("arugula", 0.4),
    ("cress", 0.35),
    ("kale", 0.75),
    ("chard", 0.75),
    ("collard", 0.75),
    ("bok choy", 0.5),
)


STYLES = {
    "sun": {
        "full": {"text": "Full sun", "bg": "#fdebb3", "fg": "#825506"},
        "part": {"text": "Full sun / part sun", "bg": "#e8f0e3", "fg": "#395f2c"},
        "shade": {"text": "Part sun / shade", "bg": "#dcead8", "fg": "#245323"},
    },
    "water": {
        "high": {"text": "High", "bg": "#ffe2e2", "fg": "#a11a1a"},
        "medium": {"text": "Medium", "bg": "#fff0db", "fg": "#a05c0a"},
        "low": {"text": "Lower", "bg": "#e1f4e8", "fg": "#1f6541"},
    },
    "temp": {
        "cool": {"text": "50-70 F", "bg": "#e2f0ff", "fg": "#0f4b88"},
        "mild": {"text": "55-75 F", "bg": "#e5f6f0", "fg": "#16634a"},
        "warm": {"text": "65-85 F", "bg": "#fff3d8", "fg": "#8c5f00"},
        "hot": {"text": "70-95 F", "bg": "#ffe4cf", "fg": "#9a4b00"},
    },
    "timing": {
        "indoor-now": {"text": "Start indoors now", "bg": "#efe6ff", "fg": "#5c2ea3"},
        "direct-late-apr": {"text": "Late Apr direct sow", "bg": "#e7f7dc", "fg": "#336b19"},
        "indoor-late-apr": {"text": "Late Apr indoor start", "bg": "#edf0ff", "fg": "#314e9b"},
        "indoor-early-may": {"text": "Early May indoor start", "bg": "#fff1e0", "fg": "#965d00"},
        "direct-mid-may": {"text": "Mid-May direct sow", "bg": "#e0f5f5", "fg": "#0e6666"},
        "plant-late-may": {"text": "Late May plant-out", "bg": "#ffe9ef", "fg": "#9a294c"},
        "transplant-spring": {"text": "Spring transplant", "bg": "#eef8ea", "fg": "#2d6b2d"},
    },
}


def plant_root_radius_ft(plant):
    name = plant["name"].lower()
    for keyword, radius_ft in ROOT_RADIUS_BY_KEYWORD:
        if keyword in name:
            return radius_ft
    return 1.0


def build_placeable_plant(plant):
    icon_key = icon_key_for_plant(plant)
    growth = build_growth_payload(plant)
    return {
        **plant,
        **growth,
        "icon_key": icon_key,
        "icon_source": icon_source_for_key(icon_key),
        "root_radius_ft": plant_root_radius_ft(plant),
    }


class PlantIconButton(ButtonBehavior, Image):
    """Image widget that behaves like a button for catalog placement."""


class PlantSeedPaletteTile(ButtonBehavior, BoxLayout):
    """Compact tile used by the seed-stamp palette popup."""

    def __init__(self, plant, controller=None, popup_getter=None, **kwargs):
        super().__init__(**kwargs)
        self.plant_data = plant
        self.controller = controller
        self.popup_getter = popup_getter
        self.orientation = "vertical"
        self.padding = dp(4)
        self.spacing = dp(2)
        self.size_hint_y = None
        self.height = dp(60)

        self.add_widget(
            Image(
                source=plant.get("icon_source", ""),
                mipmap=True,
                fit_mode="contain",
                size_hint_y=0.62,
            )
        )
        self.add_widget(
            Label(
                text=self._short_label(plant.get("name", "Plant")),
                font_size=dp(9),
                color=(0.1, 0.18, 0.08, 1),
                halign="center",
                valign="middle",
                text_size=(dp(130), None),
                size_hint_y=0.38,
            )
        )

    @staticmethod
    def _short_label(name):
        text = str(name).split(" - ", 1)[0]
        return text[:22] + "..." if len(text) > 25 else text

    def on_release(self):
        if self.controller is None:
            return
        if self.controller.start_seed_stamp_mode(dict(self.plant_data)):
            popup = self.popup_getter() if callable(self.popup_getter) else None
            if popup is not None:
                popup.dismiss()


class PlantRow(BoxLayout):
    """RecycleView row for one plant catalog item."""

    index = NumericProperty(0)
    plant_id = StringProperty("")
    plant_name = StringProperty("")

    sun_text = StringProperty("")
    sun_bg = StringProperty("#ffffff")
    sun_fg = StringProperty("#000000")

    water_text = StringProperty("")
    water_bg = StringProperty("#ffffff")
    water_fg = StringProperty("#000000")

    temp_text = StringProperty("")
    temp_bg = StringProperty("#ffffff")
    temp_fg = StringProperty("#000000")

    timing_badge_text = StringProperty("")
    timing_desc = StringProperty("")
    timing_bg = StringProperty("#ffffff")
    timing_fg = StringProperty("#000000")
    icon_key = StringProperty("generic")
    icon_source = StringProperty("")
    root_radius_text = StringProperty("")
    plant_data = ObjectProperty(None, allownone=True)
    catalog_view = ObjectProperty(None, allownone=True)

    def place_plant(self):
        if self.catalog_view is not None and self.plant_data is not None:
            self.catalog_view.place_plant(self.plant_data)


class PlantCatalogView(BoxLayout):
    """Searchable, sortable reference chart embedded in the simulator."""

    sort_key = StringProperty("id")
    sort_asc = BooleanProperty(True)
    filter_text = StringProperty("")

    def __init__(self, controller=None, popup=None, **kwargs):
        self.controller = controller
        self.popup = popup
        super().__init__(**kwargs)
        self.update_data()

    def on_search(self, text):
        self.filter_text = text.lower()
        self.update_data()

    def reset_filter(self):
        self.ids.search_input.text = ""
        self.sort_key = "id"
        self.sort_asc = True
        self.filter_text = ""
        self.update_data()

    def sort_data(self, key):
        if self.sort_key == key:
            self.sort_asc = not self.sort_asc
        else:
            self.sort_key = key
            self.sort_asc = True
        self.update_data()

    def _get_sort_value(self, plant, key):
        if key == "id":
            return plant["id"]
        if key == "name":
            return plant["name"].lower()
        if key == "sunCat":
            return {"full": 1, "part": 2, "shade": 3}.get(plant["sunCat"], 9)
        if key == "waterCat":
            return {"high": 1, "medium": 2, "low": 3}.get(plant["waterCat"], 9)
        if key == "tempCat":
            return {"cool": 1, "mild": 2, "warm": 3, "hot": 4}.get(plant["tempCat"], 9)
        if key == "timingOrder":
            return plant["timingOrder"]
        return plant["id"]

    def _matches_filter(self, plant):
        if not self.filter_text:
            return True

        query = self.filter_text
        sun_text = STYLES["sun"][plant["sunCat"]]["text"].lower()
        water_text = STYLES["water"][plant["waterCat"]]["text"].lower()
        temp_text = STYLES["temp"][plant["tempCat"]]["text"].lower()
        timing_text = STYLES["timing"][plant["timingCat"]]["text"].lower()

        return (
            query in str(plant["id"])
            or query in plant["name"].lower()
            or query in sun_text
            or query in water_text
            or query in temp_text
            or query in timing_text
            or query in plant["timingText"].lower()
        )

    def update_data(self):
        filtered = [plant for plant in PLANT_CATALOG if self._matches_filter(plant)]
        filtered.sort(
            key=lambda plant: self._get_sort_value(plant, self.sort_key),
            reverse=not self.sort_asc,
        )

        self.ids.stats_label.text = f"Showing {len(filtered)} of {len(PLANT_CATALOG)} plants"
        self.ids.rv.data = [
            self._row_data(index, build_placeable_plant(plant))
            for index, plant in enumerate(filtered)
        ]

    def _row_data(self, index, plant):
        sun = STYLES["sun"][plant["sunCat"]]
        water = STYLES["water"][plant["waterCat"]]
        temp = STYLES["temp"][plant["tempCat"]]
        timing = STYLES["timing"][plant["timingCat"]]

        return {
            "index": index,
            "plant_id": str(plant["id"]),
            "plant_name": plant["name"],
            "sun_text": sun["text"],
            "sun_bg": sun["bg"],
            "sun_fg": sun["fg"],
            "water_text": water["text"],
            "water_bg": water["bg"],
            "water_fg": water["fg"],
            "temp_text": temp["text"],
            "temp_bg": temp["bg"],
            "temp_fg": temp["fg"],
            "timing_badge_text": timing["text"],
            "timing_desc": plant["timingText"],
            "timing_bg": timing["bg"],
            "timing_fg": timing["fg"],
            "icon_key": plant["icon_key"],
            "icon_source": plant["icon_source"],
            "root_radius_text": f"{plant['root_radius_ft']:.2g} ft roots",
            "plant_data": plant,
            "catalog_view": self,
        }

    def place_plant(self, plant):
        if self.controller is None:
            return
        if self.controller.start_plant_placement(dict(plant)) and self.popup is not None:
            self.popup.dismiss()


KV = """
#:import get_color_from_hex kivy.utils.get_color_from_hex
#:import dp kivy.metrics.dp

<BadgeLabel@Label>:
    bg_color: [1, 1, 1, 1]
    color_val: [0, 0, 0, 1]
    color: self.color_val
    font_size: dp(12)
    bold: True
    padding: dp(8), dp(4)
    size_hint: None, None
    size: self.texture_size
    canvas.before:
        Color:
            rgba: self.bg_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]

<SortButton@Button>:
    background_normal: ""
    background_color: get_color_from_hex("#eef3e2")
    color: get_color_from_hex("#294322")
    bold: True
    halign: "left"
    text_size: self.size
    padding: dp(10), 0
    valign: "middle"

<PlantIconButton>:
    mipmap: True
    fit_mode: "contain"

<PlantRow>:
    orientation: "horizontal"
    padding: dp(10)
    spacing: dp(10)
    size_hint_y: None
    height: dp(90)
    canvas.before:
        Color:
            rgba: get_color_from_hex("#ffffff") if self.index % 2 == 0 else get_color_from_hex("#fcfdf8")
        Rectangle:
            pos: self.pos
            size: self.size
        Color:
            rgba: get_color_from_hex("#e8eddd")
        Line:
            points: [self.x, self.y, self.right, self.y]
            width: 1

    Label:
        text: root.plant_id
        size_hint_x: 0.5
        color: get_color_from_hex("#49663a")
        bold: True

    PlantIconButton:
        source: root.icon_source
        size_hint_x: 0.45
        on_release: root.place_plant()

    Label:
        text: root.plant_name
        size_hint_x: 2.5
        color: get_color_from_hex("#1e3818")
        bold: True
        text_size: self.size
        halign: "left"
        valign: "middle"

    Label:
        text: root.root_radius_text
        size_hint_x: 0.8
        color: get_color_from_hex("#49663a")
        font_size: dp(12)
        text_size: self.size
        halign: "left"
        valign: "middle"

    AnchorLayout:
        size_hint_x: 1.2
        anchor_x: "left"
        BadgeLabel:
            text: root.sun_text
            bg_color: get_color_from_hex(root.sun_bg)
            color_val: get_color_from_hex(root.sun_fg)

    AnchorLayout:
        size_hint_x: 1
        anchor_x: "left"
        BadgeLabel:
            text: root.water_text
            bg_color: get_color_from_hex(root.water_bg)
            color_val: get_color_from_hex(root.water_fg)

    AnchorLayout:
        size_hint_x: 1
        anchor_x: "left"
        BadgeLabel:
            text: root.temp_text
            bg_color: get_color_from_hex(root.temp_bg)
            color_val: get_color_from_hex(root.temp_fg)

    BoxLayout:
        orientation: "vertical"
        size_hint_x: 3
        spacing: dp(4)
        AnchorLayout:
            anchor_x: "left"
            anchor_y: "bottom"
            BadgeLabel:
                text: root.timing_badge_text
                bg_color: get_color_from_hex(root.timing_bg)
                color_val: get_color_from_hex(root.timing_fg)
        Label:
            text: root.timing_desc
            color: get_color_from_hex("#5f7251")
            font_size: dp(12)
            text_size: self.width, None
            halign: "left"
            valign: "top"
            size_hint_y: 1.5

<PlantCatalogView>:
    orientation: "vertical"
    padding: dp(20)
    spacing: dp(10)

    BoxLayout:
        orientation: "vertical"
        size_hint_y: None
        height: dp(100)
        padding: dp(20)
        canvas.before:
            Color:
                rgba: get_color_from_hex("#2c5e2e")
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [dp(20)]

        Label:
            text: "Garden Planner Reference Chart"
            font_size: dp(24)
            bold: True
            color: 1, 1, 1, 1
            text_size: self.size
            halign: "left"
            valign: "middle"

        Label:
            text: "Original 1-59 numbering preserved. Sort or filter by sunlight, water, temperature, or Milwaukee planting timing."
            font_size: dp(14)
            color: 1, 1, 1, 0.9
            text_size: self.size
            halign: "left"
            valign: "middle"

    BoxLayout:
        size_hint_y: None
        height: dp(50)
        spacing: dp(10)

        TextInput:
            id: search_input
            hint_text: "Filter by plant, number, sun, water, temp..."
            multiline: False
            padding: dp(8), self.height / 2.0 - (self.line_height / 2.0), dp(8), 0
            size_hint_x: 0.7
            background_color: get_color_from_hex("#f7faef")
            on_text: root.on_search(self.text)

        Button:
            text: "Reset"
            size_hint_x: 0.15
            background_color: get_color_from_hex("#ffffff")
            color: get_color_from_hex("#20311c")
            bold: True
            on_release: root.reset_filter()

        Label:
            id: stats_label
            text: "Showing 59 of 59 plants"
            size_hint_x: 0.15
            color: get_color_from_hex("#5f7251")
            bold: True

    BoxLayout:
        size_hint_y: None
        height: dp(40)
        canvas.before:
            Color:
                rgba: get_color_from_hex("#cddfb5")
            Line:
                points: [self.x, self.y, self.right, self.y]
                width: 2

        SortButton:
            text: "#"
            size_hint_x: 0.5
            on_release: root.sort_data("id")
        SortButton:
            text: "Place"
            size_hint_x: 0.45
        SortButton:
            text: "Plant & variety"
            size_hint_x: 2.5
            on_release: root.sort_data("name")
        SortButton:
            text: "Root"
            size_hint_x: 0.8
        SortButton:
            text: "Sunlight"
            size_hint_x: 1.2
            on_release: root.sort_data("sunCat")
        SortButton:
            text: "Water"
            size_hint_x: 1
            on_release: root.sort_data("waterCat")
        SortButton:
            text: "Temperature"
            size_hint_x: 1
            on_release: root.sort_data("tempCat")
        SortButton:
            text: "Milwaukee planting timing"
            size_hint_x: 3
            on_release: root.sort_data("timingOrder")

    RecycleView:
        id: rv
        viewclass: "PlantRow"
        canvas.before:
            Color:
                rgba: get_color_from_hex("#ffffff")
            Rectangle:
                pos: self.pos
                size: self.size
        RecycleBoxLayout:
            default_size: None, dp(90)
            default_size_hint: 1, None
            size_hint_y: None
            height: self.minimum_height
            orientation: "vertical"
"""


Builder.load_string(KV)


def open_plant_catalog_popup(controller=None):
    """Open the searchable plant reference chart as a modal popup."""
    content = PlantCatalogView(controller=controller)
    popup = Popup(
        title="Plant Catalog",
        content=content,
        size_hint=(0.96, 0.92),
    )
    content.popup = popup
    popup.open()
    return popup


def open_seed_palette_popup(controller=None):
    """Open a compact plant seed palette for the drag-stamp tool."""
    content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
    content.add_widget(
        Label(
            text="Pick a plant seed, then drag across grid cells to stamp it.",
            size_hint_y=None,
            height=dp(28),
            color=(0.1, 0.18, 0.08, 1),
        )
    )

    scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
    grid = GridLayout(
        cols=4,
        spacing=dp(6),
        size_hint_y=None,
        row_default_height=dp(60),
        row_force_default=True,
    )
    grid.bind(minimum_height=grid.setter("height"))

    popup_holder = {}
    popup_getter = lambda: popup_holder.get("popup")
    for plant in PLANT_CATALOG:
        grid.add_widget(
            PlantSeedPaletteTile(
                build_placeable_plant(plant),
                controller=controller,
                popup_getter=popup_getter,
            )
        )

    scroll.add_widget(grid)
    content.add_widget(scroll)

    popup = Popup(
        title="Plant Seed Palette",
        content=content,
        size_hint=(0.72, 0.88),
    )
    popup_holder["popup"] = popup
    popup.open()
    return popup
