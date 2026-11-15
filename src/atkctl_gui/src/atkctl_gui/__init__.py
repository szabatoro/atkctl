"""GUI frontend for atkctl — PySide6 configuration tool for ATK/VXE/VGN gaming mice."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("atkctl_gui")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

del version, PackageNotFoundError