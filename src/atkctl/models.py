"""Data models for ATK mouse telemetry.

Dataclasses for device state, plus helper functions for
human-readable descriptions of device parameters.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

LIFT_OFF_LABELS: dict[int, str] = {
    1: "Low",
    4: "Medium",
    11: "High",
}


def lift_off_description(level: int) -> str:
    """Human-readable lift-off distance from level (1-11)."""
    mm = 0.6 + level * 0.1  # level 1 → 0.7 mm, level 11 → 1.7 mm
    label = LIFT_OFF_LABELS.get(level)
    if label:
        return f"{mm:.1f} mm  ({label})"
    return f"{mm:.1f} mm"


@dataclass
class BatteryStatus:
    level: int
    charging: bool = False
    voltage_mv: Optional[int] = None
    raw_data: Optional[bytes] = None


@dataclass
class MouseInfo:
    """Full device snapshot."""
    battery: Optional[BatteryStatus] = None
    version: Optional[str] = None
    polling_rate_hz: Optional[int] = None
    dpi: Optional[int] = None
    dpi_stages: list[tuple[int, int]] = field(default_factory=list)
    active_dpi_stage: Optional[int] = None
    dpi_stage_count: Optional[int] = None
    connection_type: Optional[str] = None
    wireless_mode: Optional[str] = None
    dongle_led_mode: Optional[str] = None
    lift_off: Optional[str] = None
    lift_off_level: Optional[int] = None  # numeric level (1-11), populated by read_all()
    debounce_ms: Optional[int] = None
    motion_sync: Optional[bool] = None
    angle_snap: Optional[bool] = None
    sleep_timeout_s: Optional[int] = None
    ripple_control: Optional[bool] = None
    device_info: Optional[dict[str, Any]] = None
    slot: Optional[int] = None
    pid: Optional[int] = None
    path: Optional[str] = None
    firmware: Optional[str] = None


# ── Typed interface between worker and GUI panels ──────────────────────

from typing import TypedDict  # noqa: E402 (intentional grouping)


class PanelData(TypedDict, total=False):
    """Shape of the dict passed to GUI panel ``populate()`` methods.

    All fields are optional so partial updates are valid
    (e.g. battery-only refresh).
    """
    path: str
    connection_type: str
    wireless_mode: str
    firmware: str
    version: str
    polling_rate_hz: int
    debounce_ms: int
    motion_sync: bool
    angle_snap: bool
    ripple_control: bool
    sleep_timeout_s: int
    lift_off: str
    lift_off_level: int
    dpi: int
    dpi_stages: list[tuple[int, int]]
    active_dpi_stage: int
    dpi_stage_count: int
    battery: dict[str, Any]


def mouse_info_to_panel_data(info: MouseInfo) -> PanelData:
    """Convert a MouseInfo dataclass to a PanelData dict."""
    d: PanelData = {}
    if info is None:
        return d

    d["path"] = info.path
    d["connection_type"] = info.connection_type
    d["wireless_mode"] = info.wireless_mode
    d["firmware"] = info.firmware
    d["version"] = info.version
    d["polling_rate_hz"] = info.polling_rate_hz
    d["debounce_ms"] = info.debounce_ms
    d["motion_sync"] = info.motion_sync
    d["angle_snap"] = info.angle_snap
    d["ripple_control"] = info.ripple_control
    d["sleep_timeout_s"] = info.sleep_timeout_s
    d["lift_off"] = info.lift_off
    d["lift_off_level"] = info.lift_off_level
    d["dpi"] = info.dpi
    d["dpi_stages"] = info.dpi_stages
    d["active_dpi_stage"] = info.active_dpi_stage
    d["dpi_stage_count"] = info.dpi_stage_count

    if info.battery:
        d["battery"] = {
            "level": info.battery.level,
            "charging": info.battery.charging,
            "voltage_mv": info.battery.voltage_mv,
        }
    return d