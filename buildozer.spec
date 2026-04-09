[app]

# Application title shown on the device / in the app store
title = Garden Simulator

# Python package name (no spaces, no hyphens)
package.name = gardensimulator

# Reverse-domain identifier
package.domain = org.flame.garden

# Entry point
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
main = main.py

# App version
version = 1.0.0

# Comma-separated list of requirements (Python packages + kivy/buildozer builtins).
# NOTE: tkinter is a CPython built-in that is NOT available on Android/iOS.
# If you want to deploy to mobile you must port the UI to Kivy or KivyMD.
# For a desktop build (target = desktop, see below) tkinter works fine.
requirements = python3,kivy,astral,tzdata,anthropic,kivy_garden.mapview

# Supported orientations
orientation = portrait

# Android permissions (add as needed)
android.permissions = INTERNET

# Target Android API level
android.api = 33
android.minapi = 21

# Android SDK/NDK (buildozer will download these automatically)
android.sdk = 33
android.ndk = 25b

# iOS deployment target (if building for iOS)
ios.kivy_ios_url = https://github.com/kivy/kivy-ios
ios.kivy_ios_branch = master

# Log level: 0 = error only, 1 = info, 2 = debug (default: 1)
log_level = 1

# Warn only; set to 0 to stop the build on any warning
warn_on_root = 1

[buildozer]

# (Optional) path to a local copy of the android SDK/NDK
# android.sdk_path = /path/to/android-sdk
# android.ndk_path = /path/to/android-ndk

# Desktop target — use this if you only want a Windows/macOS/Linux binary.
# Run:  buildozer desktop debug
# Requires PyInstaller or cx_Freeze depending on the platform plugin.
# target = desktop
