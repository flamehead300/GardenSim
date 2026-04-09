from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from ..utils import format_number
from ..constants import (
    CATEGORIES,
    DEFAULT_CATEGORY,
    DEFAULT_STRIP_WIDTH_FT,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
)
from .styles import BTN_ACTION, BTN_BLUE, BTN_DANGER, BTN_FLAT, INPUT_FLAT


class PropertyPanel(BoxLayout):
    """Editable property panel for the selected shape."""

    def __init__(self, model, controller, **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.controller = controller

        self.orientation = "vertical"
        self.size_hint_y = None
        self.height = 0
        self.spacing = 6
        self.padding = 6
        self.visible = False
        self.geom_inputs = {}
        self._preferred_height = 130 # Optimized height for columns

        self.category_spinner = None
        self.height_input = None
        self.lock_cb = None
        self.geom_grid = None
        self.btn_move = None

        self._build_ui()

        # Observe model state that affects the property panel directly
        self.model.bind(shapes=self._on_shapes_changed)

    def _build_ui(self):
        btn_flat = BTN_FLAT
        btn_action = BTN_ACTION
        btn_danger = BTN_DANGER
        btn_blue = BTN_BLUE
        self.input_flat = INPUT_FLAT

        top_row = BoxLayout(size_hint_y=None, height=34, spacing=6)
        top_row.add_widget(Label(text="Category:", size_hint_x=0.15, color=COLOR_TEXT))
        self.category_spinner = Spinner(
            text=DEFAULT_CATEGORY,
            values=list(CATEGORIES.keys()),
            size_hint_x=0.25,
            **btn_flat
        )
        self.category_spinner.bind(text=self._on_prop_cat_change)
        top_row.add_widget(self.category_spinner)

        top_row.add_widget(Label(text="Height (ft):", size_hint_x=0.15, color=COLOR_TEXT))
        self.height_input = TextInput(text="0", multiline=False, size_hint_x=0.15, **self.input_flat)
        top_row.add_widget(self.height_input)

        self.lock_cb = CheckBox(size_hint_x=None, width=34)
        top_row.add_widget(self.lock_cb)
        top_row.add_widget(Label(text="Lock Orientation", size_hint_x=0.25, color=COLOR_TEXT))
        self.add_widget(top_row)

        # Switched to 4 columns for a sleek horizontal grid
        self.geom_grid = GridLayout(
            cols=4,
            size_hint_y=None,
            height=0,
            spacing=6,
            row_default_height=32,
            row_force_default=True,
        )
        self.add_widget(self.geom_grid)

        button_row = BoxLayout(size_hint_y=None, height=40, spacing=6)
        apply_button = Button(text="Apply Changes", **btn_action)
        apply_button.bind(on_press=self._apply_changes)
        button_row.add_widget(apply_button)

        delete_button = Button(text="Delete Shape", **btn_danger)
        delete_button.bind(on_press=lambda *a: self.controller.delete_selected())
        button_row.add_widget(delete_button)

        self.btn_move = Button(text="Move Mode", **btn_blue)
        self.btn_move.bind(on_press=lambda *a: self.controller.toggle_move_mode())
        button_row.add_widget(self.btn_move)

        deselect_button = Button(text="Deselect", **btn_flat)
        deselect_button.bind(on_press=lambda *a: self.controller.deselect())
        button_row.add_widget(deselect_button)

        self.add_widget(button_row)

    def _on_shapes_changed(self, *_args):
        if self.visible and self.model.selected_idx != -1:
            if 0 <= self.model.selected_idx < len(self.model.shapes):
                self.update_geometry_fields(self.model.shapes[self.model.selected_idx])

    def _on_prop_cat_change(self, _instance=None, text=None):
        category = text or self.category_spinner.text
        if category in CATEGORIES:
            self.height_input.text = format_number(CATEGORIES[category]["height_ft"])

    def _apply_changes(self, *_args):
        category = self.category_spinner.text
        height_text = self.height_input.text
        geom = self.get_geometry_values()
        locked = self.lock_cb.active
        self.controller.apply_prop_changes(category, height_text, geom, locked)

    def _reset_geometry_grid(self):
        self.geom_grid.clear_widgets()
        self.geom_inputs = {}

    def _add_geom_input(self, key, label_text, value):
        self.geom_grid.add_widget(Label(text=label_text, size_hint_y=None, height=32, color=COLOR_TEXT))
        widget = TextInput(text=format_number(value), multiline=False, size_hint_y=None, height=32, **self.input_flat)
        self.geom_grid.add_widget(widget)
        self.geom_inputs[key] = widget

    def set_move_mode(self, enabled):
        if self.btn_move is not None:
            self.btn_move.text = "Exit Move Mode" if enabled else "Move Mode"

    def populate(self, shape):
        self.category_spinner.text = shape.get("category", DEFAULT_CATEGORY)
        self.height_input.text = format_number(shape.get("height_ft", 0.0))
        self.lock_cb.active = shape.get("locked_orientation", False)

        self._reset_geometry_grid()
        shape_type = shape["type"]
        if shape_type == "rect":
            x1, y1, x2, y2 = shape["geom"]
            self._add_geom_input("x", "X:", x1)
            self._add_geom_input("y", "Y:", y1)
            self._add_geom_input("width", "Width:", abs(x2 - x1))
            self._add_geom_input("height", "Height:", abs(y2 - y1))
            self.geom_grid.height = 70
            self._preferred_height = 160
        elif shape_type == "circle":
            cx, cy, radius = shape["geom"]
            self._add_geom_input("cx", "Center X:", cx)
            self._add_geom_input("cy", "Center Y:", cy)
            self._add_geom_input("diameter", "Diameter:", radius * 2.0)
            self.geom_grid.add_widget(Label(text="")) # Filler for grid alignment
            self.geom_grid.add_widget(Label(text=""))
            self.geom_grid.height = 70
            self._preferred_height = 160
        elif shape_type == "strip":
            point_a, point_b = shape["geom"]
            self._add_geom_input("x1", "X1:", point_a[0])
            self._add_geom_input("y1", "Y1:", point_a[1])
            self._add_geom_input("x2", "X2:", point_b[0])
            self._add_geom_input("y2", "Y2:", point_b[1])
            self._add_geom_input("width_ft", "Width:", shape.get("width_ft", DEFAULT_STRIP_WIDTH_FT))
            self.geom_grid.add_widget(Label(text=""))
            self.geom_grid.add_widget(Label(text=""))
            self.geom_grid.height = 108
            self._preferred_height = 196
        else:
            self.geom_grid.add_widget(Label(text="Polygon - use Move Mode to reposition.", color=COLOR_TEXT_DIM))
            self.geom_grid.add_widget(Label(text=""))
            self.geom_grid.add_widget(Label(text=""))
            self.geom_grid.add_widget(Label(text=""))
            self.geom_grid.height = 36
            self._preferred_height = 126

        if self.visible:
            self.height = self._preferred_height

    def update_geometry_fields(self, shape):
        if shape["type"] == "rect" and {"x", "y", "width", "height"} <= set(self.geom_inputs):
            x1, y1, x2, y2 = shape["geom"]
            self.geom_inputs["x"].text = format_number(x1)
            self.geom_inputs["y"].text = format_number(y1)
            self.geom_inputs["width"].text = format_number(abs(x2 - x1))
            self.geom_inputs["height"].text = format_number(abs(y2 - y1))
        elif shape["type"] == "circle" and {"cx", "cy", "diameter"} <= set(self.geom_inputs):
            cx, cy, radius = shape["geom"]
            self.geom_inputs["cx"].text = format_number(cx)
            self.geom_inputs["cy"].text = format_number(cy)
            self.geom_inputs["diameter"].text = format_number(radius * 2.0)
        elif shape["type"] == "strip" and {"x1", "y1", "x2", "y2", "width_ft"} <= set(self.geom_inputs):
            point_a, point_b = shape["geom"]
            self.geom_inputs["x1"].text = format_number(point_a[0])
            self.geom_inputs["y1"].text = format_number(point_a[1])
            self.geom_inputs["x2"].text = format_number(point_b[0])
            self.geom_inputs["y2"].text = format_number(point_b[1])
            self.geom_inputs["width_ft"].text = format_number(shape.get("width_ft", DEFAULT_STRIP_WIDTH_FT))

    def get_geometry_values(self):
        values = {}
        for key, widget in self.geom_inputs.items():
            try:
                values[key] = float(widget.text)
            except ValueError:
                values[key] = 0.0
        return values

    def show(self):
        if not self.visible:
            self.height = self._preferred_height
            self.visible = True

    def hide(self):
        if self.visible:
            self.height = 0
            self.visible = False
