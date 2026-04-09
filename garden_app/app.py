from pathlib import Path
import os
import time

from kivy.app import App
from kivy.core.window import Window

from .constants import COLOR_BG
from .model import GardenModel
from .controller import GardenController
from .storage import StorageManager
from storage.repositories import SQLiteSimulationRepository
from .view.layout import GardenLayout
from .file_io import AutoSaveMixin
from .element_code_inspector import install_widget_creation_tracker

if os.environ.get("GARDEN_ENABLE_WIDGET_INSPECTOR") == "1":
    install_widget_creation_tracker(Path(__file__).resolve().parent)


class GardenSimApp(AutoSaveMixin, App):
    title = "Garden Simulator"

    def build(self):
        Window.clearcolor = COLOR_BG
        self.storage_manager = StorageManager()
        self.simulation_repository = SQLiteSimulationRepository(
            Path(self.user_data_dir) / "simulation_state.sqlite"
        )
        self._paused_at = None
        self.model = GardenModel()
        self.controller = GardenController(
            self.model,
            simulation_repositories=(self.simulation_repository,),
        )
        self._paused_monotonic_at = None
        layout = GardenLayout(self.model, self.controller)
        return layout

    def on_start(self):
        super().on_start()
        self._catch_up_from_persisted_simulation_time()
        try:
            Window.raise_window()
        except Exception:
            pass

    def on_pause(self):
        self._paused_at = time.time()
        self._paused_monotonic_at = time.monotonic()
        self._persist_simulation_snapshot(self._paused_at)
        return True

    def on_resume(self):
        if self._paused_at is None:
            return
        if self._paused_monotonic_at is None:
            elapsed = time.time() - self._paused_at
        else:
            elapsed = time.monotonic() - self._paused_monotonic_at
        self._paused_at = None
        self._paused_monotonic_at = None
        self.controller.catch_up_simulation(elapsed)
        self._persist_simulation_snapshot()

    def on_stop(self):
        self._persist_simulation_snapshot()
        super().on_stop()

    def _persist_simulation_snapshot(self, saved_at=None):
        controller = getattr(self, "controller", None)
        repository = getattr(self, "simulation_repository", None)
        if controller is None or repository is None:
            return
        try:
            controller.sim_engine.sync_persistence_checkpoint(
                force=True,
                saved_at=saved_at,
            )
        except Exception as exc:
            print(f"Simulation snapshot failed: {exc}")

    def _catch_up_from_persisted_simulation_time(self):
        controller = getattr(self, "controller", None)
        repository = getattr(self, "simulation_repository", None)
        if controller is None or repository is None:
            return 0
        saved_at = repository.load_last_simulated_time()
        if saved_at is None:
            return 0
        if not controller.sim_world.garden_grid:
            stored_world = repository.load_world()
            if stored_world.garden_grid:
                controller.load_simulation_world(
                    stored_world,
                    last_simulated_unix_time=saved_at,
                    sync_shapes=True,
                )
        if not controller.sim_world.garden_grid:
            return 0
        elapsed = time.time() - saved_at
        ran = controller.catch_up_simulation(elapsed)
        if ran > 0:
            self._persist_simulation_snapshot()
        return ran


def main():
    GardenSimApp().run()


if __name__ == "__main__":
    main()
