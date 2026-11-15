"""Background QThread for HID communication.

Keeps the UI responsive by running all blocking HID calls
in a separate thread and returning results via Qt signals.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal, Slot

from atkctl.protocol import (
    AtkDevice,
    MouseInfo,
    find_atk_hidraw5,
    POLLING_CODES_REV,
    lift_off_description,
)


class HIDWorker(QObject):
    """Worker object that lives on a QThread.

    Emit the **execute** signal with a callable to run it
    on the worker thread. Use the dedicated query/write methods
    as convenient entry points.
    """

    # ── Signals (received by main thread) ──────────────────────────
    connected = Signal(str)
    disconnected = Signal()
    error = Signal(str)
    battery_updated = Signal(object)  # MouseInfo
    status_updated = Signal(object)  # MouseInfo
    write_done = Signal(str, bool)   # command name, success

    # ── Signal to run arbitrary work on this thread ────────────────
    execute = Signal(object)  # Callable[[], None]

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._dev: AtkDevice | None = None
        self._path: str | None = None

        # Wire execute to self._run to dispatch on our thread
        self.execute.connect(self._run)

    @Slot(object)
    def _run(self, fn: Callable[[], None]) -> None:
        """Slot that runs a callable on the worker thread."""
        try:
            fn()
        except Exception as exc:
            self.error.emit(str(exc))

    # ── Device management ──────────────────────────────────────────

    def auto_detect(self) -> None:
        """Auto-detect the mouse and open it."""
        path = find_atk_hidraw5()
        if path is None:
            self.error.emit("No ATK mouse found. Plug it in and try again.")
            return
        self._open_path(path)

    def open_path(self, path: str) -> None:
        """Open a specific device path."""
        self._open_path(path)

    def _open_path(self, path: str) -> None:
        try:
            self.close()
            dev = AtkDevice(path)
            dev.open()
            self._dev = dev
            self._path = path
            self.connected.emit(path)
        except Exception as exc:
            self.error.emit(f"Failed to open {path}: {exc}")

    def close(self) -> None:
        if self._dev is not None:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None
            self._path = None
            self.disconnected.emit()

    # ── Reads ──────────────────────────────────────────────────────

    def refresh_battery(self) -> None:
        """Query battery (faster, minimal HID traffic)."""
        dev = self._dev
        if dev is None:
            self.error.emit("No device open.")
            return
        try:
            info = MouseInfo(path=self._path)
            info.battery = dev.query_battery()
            self.battery_updated.emit(info)
        except Exception as exc:
            self.error.emit(f"Battery read failed: {exc}")

    def refresh_all(self) -> None:
        """Query all telemetry (slow but complete)."""
        dev = self._dev
        if dev is None:
            self.error.emit("No device open.")
            return
        try:
            info = dev.read_all()
            info.path = self._path

            # Re-read config so we have every field
            cfg = dev.query_config()
            if cfg:
                info.polling_rate_hz = cfg.get("polling_rate_hz")
                info.debounce_ms = cfg.get("debounce_ms")
                info.motion_sync = cfg.get("motion_sync")
                info.angle_snap = cfg.get("angle_snap")
                info.ripple_control = cfg.get("ripple_control")
                info.sleep_timeout_s = cfg.get("sleep_seconds")
                lo_level = cfg.get("lift_off_level")
                if lo_level is not None:
                    info.lift_off = lift_off_description(lo_level)
                    # Store numeric level too — the GUI slider needs it
                    info.__dict__["lift_off_level"] = lo_level

            # Wireless mode
            if info.connection_type == "Wireless (2.4GHz)":
                try:
                    info.wireless_mode = dev.query_wireless_mode()
                except Exception:
                    pass

            self.status_updated.emit(info)
        except Exception as exc:
            self.error.emit(f"Status read failed: {exc}")

    # ── Writes ─────────────────────────────────────────────────────

    def write_polling_rate(self, hz: int) -> None:
        code = POLLING_CODES_REV.get(hz)
        if code is None:
            self.write_done.emit(f"polling_rate ({hz}Hz)", False)
            return
        ok = bool(self._dev and self._dev.set_polling_rate(code))
        self.write_done.emit("Polling rate", ok)

    def write_dpi(self, stage: int, x: int, y: int,
                  red: int = 255, green: int = 0, blue: int = 0) -> None:
        ok = bool(self._dev and self._dev.set_dpi(
            stage, x, y, red=red, green=green, blue=blue, enable=True))
        self.write_done.emit("DPI", ok)

    def write_debounce(self, ms: int) -> None:
        ok = bool(self._dev and self._dev.set_debounce(ms))
        self.write_done.emit("Debounce", ok)

    def write_lift_off(self, level: int) -> None:
        ok = bool(self._dev and self._dev.set_lift_off(level))
        self.write_done.emit("Lift-off", ok)

    def write_motion_sync(self, enabled: bool) -> None:
        ok = bool(self._dev and self._dev.set_motion_sync(enabled))
        self.write_done.emit("Motion Sync", ok)

    def write_angle_snap(self, enabled: bool) -> None:
        ok = bool(self._dev and self._dev.set_angle_snap(enabled))
        self.write_done.emit("Angle Snap", ok)

    def write_ripple(self, enabled: bool) -> None:
        ok = bool(self._dev and self._dev.set_ripple_control(enabled))
        self.write_done.emit("Ripple Control", ok)

    def write_sleep_timeout(self, seconds: int) -> None:
        ok = bool(self._dev and self._dev.set_sleep_timeout(seconds))
        self.write_done.emit("Sleep timeout", ok)

    