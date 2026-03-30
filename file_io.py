"""
file_io.py — Auto-save mixin, Save As / Open file-chooser popups, and notifications.

Import into main.py:
    from file_io import AutoSaveMixin, open_save_as_popup, open_load_popup
"""

from pathlib import Path

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput


AUTO_SAVE_FILENAME = "auto_save.json"
AUTO_SAVE_INTERVAL = 30  # seconds


def show_notification(message, error=False):
    """Show a small auto-closing info or error popup (dismisses after 2 s)."""
    popup = Popup(
        title="Error" if error else "Info",
        content=Label(text=message),
        size_hint=(0.6, 0.25),
    )
    popup.open()
    Clock.schedule_once(lambda dt: popup.dismiss(), 2)


def open_save_as_popup(controller):
    """Open a file-chooser popup so the user can save the plot to any path."""
    content = BoxLayout(orientation="vertical", spacing=10, padding=10)
    file_chooser = FileChooserListView(filters=["*.json"])
    filename_input = TextInput(
        hint_text="File name (e.g. my_garden.json)",
        size_hint_y=None,
        height=40,
    )
    save_btn = Button(text="Save", size_hint_y=None, height=40)

    def do_save(btn):
        selected = file_chooser.selection
        if selected and Path(selected[0]).is_dir():
            folder = selected[0]
        elif selected:
            folder = str(Path(selected[0]).parent)
        else:
            folder = file_chooser.path

        filename = filename_input.text.strip()
        if not filename:
            popup.dismiss()
            return
        if not filename.endswith(".json"):
            filename += ".json"
        full_path = str(Path(folder) / filename)
        try:
            controller.save_plot(full_path)
            popup.dismiss()
            show_notification(f"Saved to {full_path}")
        except Exception as exc:
            show_notification(f"Save error: {exc}", error=True)

    save_btn.bind(on_release=do_save)
    content.add_widget(file_chooser)
    content.add_widget(filename_input)
    content.add_widget(save_btn)

    popup = Popup(title="Save As", content=content, size_hint=(0.9, 0.9))
    popup.open()


def open_load_popup(controller):
    """Open a file-chooser popup so the user can load a garden plot JSON file."""
    content = BoxLayout(orientation="vertical", spacing=10, padding=10)
    file_chooser = FileChooserListView(filters=["*.json"])
    load_btn = Button(text="Open", size_hint_y=None, height=40)

    def do_load(btn):
        selected = file_chooser.selection
        if not selected or Path(selected[0]).is_dir():
            popup.dismiss()
            return
        try:
            controller.load_plot(selected[0])
            popup.dismiss()
            show_notification(f"Loaded {Path(selected[0]).name}")
        except Exception as exc:
            show_notification(f"Load error: {exc}", error=True)

    load_btn.bind(on_release=do_load)
    content.add_widget(file_chooser)
    content.add_widget(load_btn)

    popup = Popup(title="Open File", content=content, size_hint=(0.9, 0.9))
    popup.open()


class AutoSaveMixin:
    """Mixin for GardenSimApp that adds periodic auto-save, save-on-exit,
    and restore-on-start.

    Expects the host App to expose ``self.root.controller`` (GardenController).
    Uses the app's StorageManager data directory for the auto-save file.
    """

    def on_start(self):
        controller = self._get_controller()
        if controller is not None:
            try:
                controller.load_plot(AUTO_SAVE_FILENAME)
            except Exception:
                pass  # No auto-save yet on first run — that's fine.
        Clock.schedule_interval(self._do_auto_save, AUTO_SAVE_INTERVAL)

    def on_stop(self):
        self._do_auto_save()

    def _do_auto_save(self, dt=None):
        controller = self._get_controller()
        if controller is None:
            return
        try:
            controller.save_plot(AUTO_SAVE_FILENAME)
        except Exception as exc:
            print(f"Auto-save failed: {exc}")

    def _get_controller(self):
        return getattr(getattr(self, "root", None), "controller", None)
