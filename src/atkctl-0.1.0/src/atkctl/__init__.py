"""ATK Mouse — CLI tool for ATK A9 PRO MAX and compatible gaming mice."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("atkctl")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

del version, PackageNotFoundError

# Convenience re-exports: the types most callers need
from atkctl.device import HidDevice, AtkDeviceProtocol, FakeDevice  # noqa: E402, F401
from atkctl.models import BatteryStatus, MouseInfo  # noqa: E402, F401