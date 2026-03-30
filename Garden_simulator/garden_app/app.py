from pathlib import Path

from kivy.app import App
from kivy.core.window import Window

from .constants import COLOR_BG
from .model import GardenModel
from .controller import GardenController
from .storage import StorageManager
from .view.layout import GardenLayout
from .file_io import AutoSaveMixin
from .element_code_inspector import install_widget_creation_tracker

install_widget_creation_tracker(Path(__file__).resolve().parent)


class GardenSimApp(AutoSaveMixin, App):
    def build(self):
        Window.clearcolor = COLOR_BG
        self.storage_manager = StorageManager()
        model = GardenModel()
        controller = GardenController(model)
        layout = GardenLayout(model, controller)
        return layout


def main():
    GardenSimApp().run()


if __name__ == "__main__":
    main()
