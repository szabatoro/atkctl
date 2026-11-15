"""ATK Mouse protocol — compatibility re-export shim.

This module re-exports everything from the split-out modules
(commands_, models_, framing_, discovery_, device_) so that
existing ``from atkctl.protocol import ...`` imports keep working.

New code should import directly from the sub-modules.

.. _commands: atkctl.commands
.. _models:    atkctl.models
.. _framing:   atkctl.framing
.. _discovery: atkctl.discovery
.. _device:   atkctl.device
"""

# ── Commands ──────────────────────────────────────────────────────────
from atkctl.commands import (  # noqa: F401
    CMD_BATTERY,
    CMD_CONFIG,
    CMD_GET_ONLINE,
    CMD_SET_DPI,
    CMD_SET_LOD,
    CMD_SET_MOTION_SYNC,
    CMD_SET_DEBOUNCE,
    CMD_DONGLE_LED,
    CMD_READ_EEPROM,
    CMD_DEVICE_INFO,
    CMD_WIRELESS_MODE,
    CMD_DONGLE_VERSION,
    CMD_DEVICE_VERSION,
    CMD_SET_PROFILE,
    CMD_WRITE_DPI,
    CMD_SET_RIPPLE,
    CMD_SET_POLLING,
    CMD_SET_ANGLE,
    CMD_SET_SLEEP,
    CMD_SET_DONGLE_LIGHT,
    CMD_SET_LONG_RANGE,
    POLLING_CODES,
    POLLING_CODES_REV,
    SLOT_WIRED,
    SLOT_WIRELESS,
    EEPROM,
    PACKET_SIZE,
    REPORT_ID,
)

# ── Models ────────────────────────────────────────────────────────────
from atkctl.models import (  # noqa: F401
    BatteryStatus,
    MouseInfo,
    LIFT_OFF_LABELS,
    lift_off_description,
    PanelData,
    mouse_info_to_panel_data,
)

# ── Framing ───────────────────────────────────────────────────────────
from atkctl.framing import (  # noqa: F401
    _calc_checksum,
    build_request,
    parse_response,
)

# ── Discovery ─────────────────────────────────────────────────────────
from atkctl.discovery import (  # noqa: F401
    find_atk_hidraw5,
    enumerate_atk_interfaces,
)

# ── Device ────────────────────────────────────────────────────────────
from atkctl.device import (  # noqa: F401
    AtkDeviceProtocol,
    HidDevice,
    FakeDevice,
    create_device,
)

# Keep AtkDevice as an alias for backward compatibility
AtkDevice = HidDevice
__all__ = [
    # Commands
    "CMD_BATTERY", "CMD_CONFIG", "CMD_GET_ONLINE", "CMD_SET_DPI",
    "CMD_SET_LOD", "CMD_SET_MOTION_SYNC", "CMD_SET_DEBOUNCE",
    "CMD_DONGLE_LED", "CMD_READ_EEPROM", "CMD_DEVICE_INFO",
    "CMD_WIRELESS_MODE", "CMD_DONGLE_VERSION", "CMD_DEVICE_VERSION",
    "CMD_SET_PROFILE", "CMD_WRITE_DPI", "CMD_SET_RIPPLE",
    "CMD_SET_POLLING", "CMD_SET_ANGLE", "CMD_SET_SLEEP",
    "CMD_SET_DONGLE_LIGHT", "CMD_SET_LONG_RANGE",
    "POLLING_CODES", "POLLING_CODES_REV", "SLOT_WIRED", "SLOT_WIRELESS",
    "EEPROM", "PACKET_SIZE", "REPORT_ID",
    # Models
    "BatteryStatus", "MouseInfo", "LIFT_OFF_LABELS", "lift_off_description",
    "PanelData", "mouse_info_to_panel_data",
    # Framing
    "_calc_checksum", "build_request", "parse_response",
    # Discovery
    "find_atk_hidraw5", "enumerate_atk_interfaces",
    # Device
    "AtkDeviceProtocol", "HidDevice", "AtkDevice", "FakeDevice", "create_device",
]