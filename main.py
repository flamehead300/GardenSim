"""Garden Plot Simulator — entry point."""
import os
import sys


if sys.platform == "win32" and os.environ.get("GARDEN_USE_ANGLE") == "1":
    os.environ.setdefault("KIVY_GL_BACKEND", "angle_sdl2")

from garden_app.app import main

if __name__ == "__main__":
    main()
