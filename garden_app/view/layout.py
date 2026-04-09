from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from ..utils import format_number, time_str_from_minutes
from ..constants import (
    COLOR_BG, COLOR_TEXT, COLOR_TEXT_DIM, COLOR_ACCENT,
    CATEGORIES, DEFAULT_CATEGORY, TIMEZONE_OPTIONS,
)
from .canvas import GardenCanvas
from .plant_catalog import open_plant_catalog_popup, open_seed_palette_popup
from .property_panel import PropertyPanel
from .styles import BTN_ACTION, BTN_BLUE, BTN_DANGER, BTN_FLAT, INPUT_FLAT
from .terrain_map import TerrainMapPanel
from ..element_code_inspector import (
    build_widget_report, handle_right_click, make_report, snippet_from_callable,
)
from ..file_io import open_save_as_popup, open_load_popup


class GardenLayout(BoxLayout):
    """Root view layout. Combines UI controls, Canvas, and PropertyPanel."""

    def __init__(self, model, controller, **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.controller = controller

        self.orientation = "vertical"
        self.spacing = 6
        self.padding = 6
        with self.canvas.before:
            Color(*COLOR_BG)
            self._background_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(
            pos=lambda *_args: setattr(self._background_rect, "pos", self.pos),
            size=lambda *_args: setattr(self._background_rect, "size", self.size),
        )

        self.w_input = None
        self.h_input = None
        self.zoom_label = None
        self.undo_button = None
        self.redo_button = None
        self.snap_toggle = None
        self.grid_size_spinner = None
        self.location_mode_spinner = None
        self.location_input_host = None
        self.coords_input_host = None
        self.lat_input = None
        self.lon_input = None
        self.address_input = None
        self.location_apply_button = None
        self.tz_spinner = None
        self.date_input = None
        self.time_input = None
        self.time_slider = None
        self.time_slider_label = None
        self.sun_info = None
        self.mode_label = None
        self.finish_poly_btn = None
        self.cat_buttons = {}
        self._syncing_time_slider = False

        self.canvas_widget = None
        self.terrain_map_panel = None
        self.prop_panel = None

        self.setup_ui()

        # Connect to controller events (like alerts)
        self.controller.bind(on_alert=self.show_alert)
        self.controller.bind(
            can_undo=self._update_history_buttons,
            can_redo=self._update_history_buttons,
        )

        # Connect UI updates to Model state via event binding
        self.model.bind(
            scale=self._update_zoom_label,
            sun_azimuth=self._update_sun_label,
            sun_elevation=self._update_sun_label,
            width_ft=self._update_dimensions,
            height_ft=self._update_dimensions,
            lat=self._update_sun_controls,
            lon=self._update_sun_controls,
            date_str=self._update_sun_controls,
            time_str=self._update_time_controls,
            timezone_name=self._update_timezone_input,
            selected_idx=self._on_selection_change,
            move_mode=self._on_move_mode_change,
            pending_plant=self._update_mode_ui,
            snap_to_grid=self._update_snap_controls,
            grid_size=self._update_snap_controls,
            draw_mode=self._update_mode_ui,
            poly_points=self._update_mode_ui
        )
        self._update_history_buttons()
        self._update_snap_controls()
        self._update_sun_controls()
        self._update_time_controls()
        self._update_timezone_input()

        # Run initial calculations
        Clock.schedule_once(lambda *_args: self.controller.apply_dimensions(
            self.w_input.text, self.h_input.text
        ), 0)

    def setup_ui(self):
        btn_flat = BTN_FLAT
        btn_action = BTN_ACTION
        btn_danger = BTN_DANGER
        btn_blue = BTN_BLUE
        input_flat = INPUT_FLAT

        controls = BoxLayout(orientation="vertical", size_hint_y=None, height=206, spacing=6)

        # --- Row 1: Document Settings, Size & Zoom ---
        row1 = BoxLayout(size_hint_y=None, height=34, spacing=6)
        open_btn = Button(text="Open", size_hint_x=0.08, **btn_blue)
        open_btn.bind(on_press=lambda *a: open_load_popup(self.controller))
        row1.add_widget(open_btn)

        save_as_btn = Button(text="Save As", size_hint_x=0.08, **btn_blue)
        save_as_btn.bind(on_press=lambda *a: open_save_as_popup(self.controller))
        row1.add_widget(save_as_btn)

        plant_catalog_btn = Button(text="Plant Catalog", size_hint_x=0.10, **btn_blue)
        plant_catalog_btn.bind(on_press=lambda *a: open_plant_catalog_popup(self.controller))
        row1.add_widget(plant_catalog_btn)

        row1.add_widget(Label(text="|  Size (ft):", size_hint_x=0.08, color=COLOR_TEXT))
        self.w_input = TextInput(text=format_number(self.model.width_ft), multiline=False, size_hint_x=0.06, **input_flat)
        self.w_input.bind(on_text_validate=self.apply_dimensions, focus=self._on_dimension_focus)
        row1.add_widget(self.w_input)
        
        row1.add_widget(Label(text="x", size_hint_x=0.02, color=COLOR_TEXT))
        self.h_input = TextInput(text=format_number(self.model.height_ft), multiline=False, size_hint_x=0.06, **input_flat)
        self.h_input.bind(on_text_validate=self.apply_dimensions, focus=self._on_dimension_focus)
        row1.add_widget(self.h_input)

        row1.add_widget(Label(text="|  Zoom:", size_hint_x=0.06, color=COLOR_TEXT))
        zoom_out_button = Button(text="-", size_hint_x=0.04, **btn_flat)
        zoom_out_button.bind(
            on_press=lambda *a: self.terrain_map_panel.zoom_out_at_center()
            if self.terrain_map_panel is not None else None
        )
        row1.add_widget(zoom_out_button)

        zoom_in_button = Button(text="+", size_hint_x=0.04, **btn_flat)
        zoom_in_button.bind(
            on_press=lambda *a: self.terrain_map_panel.zoom_in_at_center()
            if self.terrain_map_panel is not None else None
        )
        row1.add_widget(zoom_in_button)

        self.zoom_label = Label(text="Map Zoom: --", size_hint_x=0.12, color=COLOR_TEXT_DIM)
        row1.add_widget(self.zoom_label)

        self.undo_button = Button(text="Undo", size_hint_x=0.08, disabled=True, **btn_flat)
        self.undo_button.bind(on_press=lambda *a: self.controller.undo())
        row1.add_widget(self.undo_button)

        self.redo_button = Button(text="Redo", size_hint_x=0.08, disabled=True, **btn_flat)
        self.redo_button.bind(on_press=lambda *a: self.controller.redo())
        row1.add_widget(self.redo_button)
        row1.add_widget(Label(text="", size_hint_x=0.10))  # Spacer
        controls.add_widget(row1)

        # --- Row 2: Location, Date & Sun Updates ---
        row2 = BoxLayout(size_hint_y=None, height=34, spacing=6)
        row2.add_widget(Label(text="Location:", size_hint_x=0.07, color=COLOR_TEXT))
        self.location_mode_spinner = Spinner(
            text="Coordinates",
            values=("Coordinates", "Address"),
            size_hint_x=0.11,
            **btn_flat,
        )
        self.location_mode_spinner.bind(text=self._on_location_mode_change)
        row2.add_widget(self.location_mode_spinner)

        self.location_input_host = BoxLayout(size_hint_x=0.20, spacing=4)
        self.coords_input_host = BoxLayout(spacing=4)
        self.lat_input = TextInput(
            text=str(self.model.lat),
            hint_text="Latitude",
            multiline=False,
            size_hint_x=0.5,
            **input_flat,
        )
        self.lon_input = TextInput(
            text=str(self.model.lon),
            hint_text="Longitude",
            multiline=False,
            size_hint_x=0.5,
            **input_flat,
        )
        self.coords_input_host.add_widget(self.lat_input)
        self.coords_input_host.add_widget(self.lon_input)
        self.address_input = TextInput(
            text="",
            hint_text="Street address or place",
            multiline=False,
            size_hint_x=1,
            **input_flat,
        )
        self.address_input.bind(on_text_validate=self.apply_sun)
        row2.add_widget(self.location_input_host)

        row2.add_widget(Label(text="Date/Time:", size_hint_x=0.07, color=COLOR_TEXT))
        self.date_input = TextInput(text=self.model.date_str, multiline=False, size_hint_x=0.09, **input_flat)
        row2.add_widget(self.date_input)
        self.time_input = TextInput(text=self.model.time_str, multiline=False, size_hint_x=0.07, **input_flat)
        row2.add_widget(self.time_input)

        self.tz_spinner = Spinner(text=self.model.timezone_name, values=TIMEZONE_OPTIONS, size_hint_x=0.16, **btn_flat)
        row2.add_widget(self.tz_spinner)

        self.location_apply_button = Button(text="Update Sun", size_hint_x=0.08, **btn_blue)
        self.location_apply_button.bind(on_press=self.apply_sun)
        row2.add_widget(self.location_apply_button)

        self.sun_info = Label(text="Sun: Azimuth --- | Elev ---", size_hint_x=0.15, color=COLOR_ACCENT)
        row2.add_widget(self.sun_info)
        controls.add_widget(row2)

        # --- Row 3: Timelapse & Grid Options ---
        row3 = BoxLayout(size_hint_y=None, height=34, spacing=6)
        row3.add_widget(Label(text="Time-Lapse:", size_hint_x=0.10, color=COLOR_TEXT))
        self.time_slider = Slider(min=0, max=1440, step=1, value=self.model.time_minutes, size_hint_x=0.40)
        self.time_slider.bind(value=self._on_time_slider_change)
        row3.add_widget(self.time_slider)
        
        self.time_slider_label = Label(text=time_str_from_minutes(self.model.time_minutes, include_seconds=False), size_hint_x=0.08, color=COLOR_TEXT_DIM)
        row3.add_widget(self.time_slider_label)

        row3.add_widget(Label(text="|  Grid:", size_hint_x=0.06, color=COLOR_TEXT))
        self.snap_toggle = ToggleButton(text="Snap", size_hint_x=0.08, state="down" if self.model.snap_to_grid else "normal", **btn_flat)
        self.snap_toggle.bind(on_press=lambda instance: self.controller.set_snap_to_grid(instance.state == "down"))
        row3.add_widget(self.snap_toggle)

        self.grid_size_spinner = Spinner(text=format_number(self.model.grid_size), values=("0.25", "0.5", "1", "2", "5"), size_hint_x=0.08, **btn_flat)
        self.grid_size_spinner.bind(text=lambda _instance, value: self.controller.set_grid_size(value))
        row3.add_widget(self.grid_size_spinner)

        row3.add_widget(
            Label(
                text="Map drag pans terrain when no edit tool is active | Wheel: map zoom",
                size_hint_x=0.20,
                color=COLOR_TEXT_DIM,
            )
        )
        controls.add_widget(row3)

        # --- Row 4: Drawing Tools & Categories ---
        row4 = BoxLayout(size_hint_y=None, height=34, spacing=6)
        row4.add_widget(Label(text="Add:", size_hint_x=0.05, color=COLOR_TEXT))

        cat_layout = BoxLayout(spacing=2, size_hint_x=0.28)
        for category, cfg in CATEGORIES.items():
            button = ToggleButton(
                text=f"{category} ({cfg['height_ft']}ft)",
                group="category",
                state="down" if category == DEFAULT_CATEGORY else "normal",
                **btn_flat
            )
            button.bind(on_press=self._on_cat_press)
            cat_layout.add_widget(button)
            self.cat_buttons[category] = button
        row4.add_widget(cat_layout)

        row4.add_widget(Label(text="| Shape:", size_hint_x=0.06, color=COLOR_TEXT))
        for mode, label in (
            ("rect", "Rect"),
            ("circle", "Circle"),
            ("polygon", "Poly"),
            ("strip", "Strip"),
        ):
            button = Button(text=label, size_hint_x=0.06, **btn_flat)
            button.bind(on_press=lambda _i, d_mode=mode: self.controller.set_draw_mode(d_mode))
            row4.add_widget(button)

        self.finish_poly_btn = Button(text="Finish", size_hint_x=0.08, disabled=True, **btn_action)
        self.finish_poly_btn.bind(on_press=lambda *a: self.controller.finish_polygon())
        row4.add_widget(self.finish_poly_btn)

        cancel_button = Button(text="Cancel", size_hint_x=0.08, **btn_danger)
        cancel_button.bind(on_press=lambda *a: self.controller.cancel_drawing())
        row4.add_widget(cancel_button)

        clear_button = Button(text="Clear All", size_hint_x=0.08, **btn_danger)
        clear_button.bind(on_press=lambda *a: self.controller.clear_shapes())
        row4.add_widget(clear_button)

        self.mode_label = Label(text="Mode: None | Select shape", size_hint_x=0.19, color=COLOR_TEXT_DIM)
        row4.add_widget(self.mode_label)
        controls.add_widget(row4)

        # --- Row 5: Drag-to-stamp grid tools ---
        row5 = BoxLayout(size_hint_y=None, height=34, spacing=6)
        row5.add_widget(Label(text="Drag Tools:", size_hint_x=0.10, color=COLOR_TEXT))

        hose_button = Button(text="Irrigation Hose", size_hint_x=0.16, **btn_blue)
        hose_button.bind(on_press=lambda *_args: self.controller.set_grid_stamp_mode("irrigation_hose"))
        row5.add_widget(hose_button)

        carrot_button = Button(text="Plant Seeds", size_hint_x=0.14, **btn_blue)
        carrot_button.bind(on_press=lambda *_args: open_seed_palette_popup(self.controller))
        row5.add_widget(carrot_button)

        grow_button = Button(text="Grow 1 Day", size_hint_x=0.14, **btn_action)
        grow_button.bind(on_press=self.tick_growth_one_day)
        row5.add_widget(grow_button)

        row5.add_widget(
            Label(
                text="Growth needs fertilizer plus a hose in the same or adjacent grid cell.",
                size_hint_x=0.46,
                color=COLOR_TEXT_DIM,
            )
        )
        controls.add_widget(row5)

        self.add_widget(controls)

        self.terrain_map_panel = TerrainMapPanel(self.model, self.controller)
        self.canvas_widget = GardenCanvas(
            self.model,
            self.controller,
            transparent_background=True,
            map_panel=self.terrain_map_panel,
            show_grid_overlay=False,
        )
        self.terrain_map_panel.attach_overlay(self.canvas_widget)
        self.terrain_map_panel.set_viewport_change_callback(self._update_zoom_label)
        self.add_widget(self.terrain_map_panel)

        # Property Panel (hidden initially)
        self.prop_panel = PropertyPanel(self.model, self.controller)
        self.add_widget(self.prop_panel)
        self.prop_panel.hide()
        self._sync_location_mode_ui()

    # --- UI Updaters ---

    def _update_zoom_label(self, *_args):
        if self.zoom_label is None:
            return
        if self.terrain_map_panel is not None:
            self.zoom_label.text = self.terrain_map_panel.zoom_label_text()
            return
        self.zoom_label.text = f"View Scale: {self.model.scale:.1f} px/ft"

    def _update_history_buttons(self, *_args):
        if self.undo_button is not None:
            self.undo_button.disabled = not self.controller.can_undo
        if self.redo_button is not None:
            self.redo_button.disabled = not self.controller.can_redo

    def _update_snap_controls(self, *_args):
        if self.snap_toggle is not None:
            self.snap_toggle.state = "down" if self.model.snap_to_grid else "normal"
        if self.grid_size_spinner is not None:
            self.grid_size_spinner.text = format_number(self.model.grid_size)

    def _update_sun_label(self, *_args):
        self.sun_info.text = f"Sun: Azimuth {self.model.sun_azimuth:.1f} | Elev {self.model.sun_elevation:.1f}"

    def _update_sun_controls(self, *_args):
        if self.lat_input is not None:
            self.lat_input.text = str(self.model.lat)
        if self.lon_input is not None:
            self.lon_input.text = str(self.model.lon)
        if self.date_input is not None:
            self.date_input.text = self.model.date_str

    def _location_mode(self):
        if self.location_mode_spinner is None:
            return "coordinates"
        if str(self.location_mode_spinner.text).strip().casefold() == "address":
            return "address"
        return "coordinates"

    def _on_location_mode_change(self, *_args):
        self._sync_location_mode_ui()

    def _sync_location_mode_ui(self):
        if self.location_input_host is None:
            return
        self.location_input_host.clear_widgets()
        if self._location_mode() == "address":
            self.location_input_host.add_widget(self.address_input)
            if self.location_apply_button is not None:
                self.location_apply_button.text = "Find + Sun"
            return
        self.location_input_host.add_widget(self.coords_input_host)
        if self.location_apply_button is not None:
            self.location_apply_button.text = "Update Sun"

    def _update_time_controls(self, *_args):
        if self.time_input is not None:
            self.time_input.text = self.model.time_str
        if self.time_slider is not None:
            self._syncing_time_slider = True
            self.time_slider.value = self.model.time_minutes
            self._syncing_time_slider = False
        if self.time_slider_label is not None:
            self.time_slider_label.text = time_str_from_minutes(
                self.model.time_minutes,
                include_seconds=False,
            )

    def _update_timezone_input(self, *_args):
        if self.tz_spinner is not None:
            self.tz_spinner.text = self.model.timezone_name

    def _update_dimensions(self, *_args):
        self.w_input.text = format_number(self.model.width_ft)
        self.h_input.text = format_number(self.model.height_ft)

    def _on_selection_change(self, instance, idx):
        if idx == -1:
            self.prop_panel.hide()
        else:
            self.prop_panel.populate(self.model.shapes[idx])
            self.prop_panel.set_move_mode(self.model.move_mode)
            self.prop_panel.show()
        self._update_mode_ui()

    def _on_move_mode_change(self, instance, move_mode):
        self.prop_panel.set_move_mode(move_mode)
        self._update_mode_ui()

    def _update_mode_ui(self, *_args):
        mode = self.model.draw_mode
        self.finish_poly_btn.disabled = (mode != "polygon")
        if mode:
            if mode == "plant" and self.model.pending_plant:
                self.mode_label.text = f"Mode: Place {self.model.pending_plant.get('name', 'Plant')}"
            elif mode == "irrigation_hose":
                self.mode_label.text = "Mode: Irrigation Hose | drag across grid"
            elif mode == "carrot_seed":
                plant_name = "Plant Seed"
                if self.model.pending_plant:
                    plant_name = self.model.pending_plant.get("name", plant_name)
                self.mode_label.text = f"Mode: {plant_name} seed | drag across grid"
            else:
                self.mode_label.text = f"Mode: {mode.capitalize()}"
        elif self.model.move_mode and self.model.selected_idx != -1:
            self.mode_label.text = "Mode: Move shape"
        elif self.model.selected_idx != -1:
            self.mode_label.text = "Mode: Shape selected"
        else:
            self.mode_label.text = "Mode: None | Select shape"

    # --- Actions ---

    def _on_dimension_focus(self, _instance, focused):
        if not focused:
            self.apply_dimensions()

    def apply_dimensions(self, *_args):
        success = self.controller.apply_dimensions(self.w_input.text, self.h_input.text)
        if not success:
            self.w_input.text = format_number(self.model.width_ft)
            self.h_input.text = format_number(self.model.height_ft)

    def apply_sun(self, *_args):
        lat_text = self.lat_input.text
        lon_text = self.lon_input.text
        if self._location_mode() == "address":
            geocode = self.controller.geocode_address(self.address_input.text)
            if geocode is None:
                return
            lat_text = f"{geocode['lat']:.7f}".rstrip("0").rstrip(".")
            lon_text = f"{geocode['lon']:.7f}".rstrip("0").rstrip(".")
            self.lat_input.text = lat_text
            self.lon_input.text = lon_text

        success = self.controller.update_sun(
            lat_text,
            lon_text,
            self.date_input.text,
            self.time_input.text,
            self.tz_spinner.text,
        )
        if success and self.terrain_map_panel is not None:
            self.terrain_map_panel.sync_location(force=True)

    def tick_growth_one_day(self, *_args):
        if not self.controller.tick_growth(1.0):
            self.show_alert(
                None,
                "Growth",
                "No plants grew. Plants need fertilizer plus an irrigation hose in the same or adjacent grid cell.",
            )

    def _on_time_slider_change(self, _instance, value):
        if self._syncing_time_slider:
            return
        self.controller.simulate_day_shadows(
            self.date_input.text,
            int(value),
            self.tz_spinner.text,
        )

    def _on_cat_press(self, instance):
        category = instance.text.split(" (", 1)[0]
        self.controller.set_draw_category(category)
        for cat, button in self.cat_buttons.items():
            button.state = "down" if cat == category else "normal"

    def _canvas_anchor_local(self):
        if self.canvas_widget is None:
            return 0.0, 0.0
        return self.canvas_widget.width / 2.0, self.canvas_widget.height / 2.0

    def show_alert(self, instance, title, message):
        popup = Popup(
            title=title,
            content=Label(text=message),
            size_hint=(0.55, 0.35),
        )
        popup.open()

    # --- Element Inspector Integration ---

    def on_touch_down(self, touch):
        if handle_right_click(self, touch, self._build_inspection_report):
            return True
        return super().on_touch_down(touch)

    def _build_inspection_report(self, widget, touch):
        shape_report = self._build_shape_inspection_report(widget, touch)
        if shape_report is not None:
            return shape_report
        return build_widget_report(widget)

    def _build_shape_inspection_report(self, widget, touch):
        if widget is not self.canvas_widget:
            return None

        world_x, world_y = self.canvas_widget._world_from_touch(touch)
        for index in range(len(self.model.shapes) - 1, -1, -1):
            shape = self.model.shapes[index]
            if self.controller.shape_contains(shape, world_x, world_y):
                return self._shape_report(index, shape, world_x, world_y)
        return None

    def _shape_report(self, index, shape, world_x, world_y):
        shape_type = shape["type"]

        if shape_type == "polygon":
            creation_snippet = snippet_from_callable(
                self.controller.finish_polygon,
                "Polygon creation logic",
                highlight='"type": "polygon"',
                context=6,
            )
        elif shape_type == "strip":
            creation_snippet = snippet_from_callable(
                self.controller.add_strip,
                "Strip creation logic",
                highlight='"type": "strip"',
                context=6,
            )
        else:
            creation_snippet = snippet_from_callable(
                self.controller.on_mouse_release,
                "Shape creation logic",
                highlight=f'"type": "{shape_type}"',
                context=6,
            )

        render_markers = {
            "rect": 'if shape_type == "rect":',
            "circle": 'elif shape_type == "circle":',
            "polygon": 'elif shape_type == "polygon":',
            "strip": 'elif shape_type == "strip":',
        }

        return make_report(
            title=f"Right-click inspector: shape {index}",
            details=[
                f"Shape type: {shape_type}",
                f"Category: {shape.get('category', DEFAULT_CATEGORY)}",
                f"Height: {format_number(shape.get('height_ft', 0.0))} ft",
                f"World click: ({format_number(world_x)}, {format_number(world_y)})",
                f"Geometry payload: {shape.get('geom')!r}",
            ],
            snippets=[
                creation_snippet,
                snippet_from_callable(
                    self.controller.shape_contains,
                    "Shape hit-test logic",
                    highlight=f'if shape_type == "{shape_type}":',
                    context=4,
                ),
                snippet_from_callable(
                    self.canvas_widget.redraw,
                    "Canvas render logic",
                    highlight=render_markers[shape_type],
                    context=8,
                    max_lines=40,
                ),
            ],
        )
