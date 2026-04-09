import json
from pathlib import Path

from kivy.app import App

from .model import GardenModel


class StorageManager:
    """Persist serialized garden plots under the app's local data directory."""

    DEFAULT_FILENAME = "garden_plot.json"

    def __init__(self, filename=None, base_dir=None):
        self.filename = filename or self.DEFAULT_FILENAME
        self.base_dir = Path(base_dir) if base_dir is not None else None

    def get_storage_dir(self):
        """Resolve the writable data directory for local plot storage."""
        if self.base_dir is not None:
            storage_dir = self.base_dir
        else:
            app = App.get_running_app()
            if app is None:
                raise RuntimeError(
                    "StorageManager requires a running Kivy app or an explicit base_dir."
                )
            storage_dir = Path(app.user_data_dir)

        storage_dir.mkdir(parents=True, exist_ok=True)
        return storage_dir

    def get_plot_path(self, filename=None):
        """Return the fully qualified local JSON path for a stored plot."""
        return self.get_storage_dir() / (filename or self.filename)

    def save_model(self, model, filename=None):
        """Write one garden model to disk as JSON."""
        plot_path = self.get_plot_path(filename)
        with plot_path.open("w", encoding="utf-8") as handle:
            json.dump(model.to_dict(), handle, indent=2)
        return plot_path

    def load_payload(self, filename=None):
        """Read one serialized garden payload from disk."""
        plot_path = self.get_plot_path(filename)
        with plot_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def load_model(self, filename=None):
        """Restore a garden model from local JSON storage."""
        return GardenModel.from_dict(self.load_payload(filename))
