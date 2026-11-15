"""atkctl-gui — PySide6-based configuration UI for ATK/VXE/VGN gaming mice.

Launches a tabbed configuration window with full read/write access
to mouse settings. Runs HID operations on a background QThread to
keep the UI responsive.
"""

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from atkctl.protocol import MouseInfo
from atkctl_gui.ui.panel_dashboard import DashboardPanel
from atkctl_gui.ui.panel_performance import PerformancePanel
from atkctl_gui.ui.panel_dpi import DpiPanel
from atkctl_gui.ui.panel_advanced import AdvancedPanel
from atkctl_gui.worker import HIDWorker


def _info_to_dict(info: MouseInfo) -> dict:
    """Convert a MouseInfo dataclass to a plain dict for panel.populate()."""
    d: dict = {}
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
    d["lift_off_level"] = getattr(info, "lift_off_level", None)
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


class MainWindow(QMainWindow):
    """Main configuration window with tabbed panels."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ATK Mouse Config")
        self.setMinimumSize(520, 480)
        self.resize(560, 540)

        # ── Busy-state tracking ────────────────────────────────────
        self._busy_count = 0

        # ── Thread setup ───────────────────────────────────────────
        self._thread = QThread(self)
        self._worker = HIDWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._schedule_auto_detect)
        self._worker.connected.connect(self._on_connected)
        self._worker.error.connect(self._on_error)
        self._worker.battery_updated.connect(self._on_battery)
        self._worker.status_updated.connect(self._on_status)
        self._worker.write_done.connect(self._on_write_done)

        # ── Central widget ─────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # Device path bar
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Device:"))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Auto-detected")
        self.path_edit.setReadOnly(True)
        path_layout.addWidget(self.path_edit, 1)
        self.manual_path_btn = QPushButton("Open…")
        self.manual_path_btn.setToolTip("Open a specific HID device path")
        self.manual_path_btn.clicked.connect(self._on_manual_path)
        path_layout.addWidget(self.manual_path_btn)
        self.reconnect_btn = QPushButton("Auto")
        self.reconnect_btn.setToolTip("Auto-detect the mouse")
        self.reconnect_btn.clicked.connect(self._schedule_auto_detect)
        path_layout.addWidget(self.reconnect_btn)
        main_layout.addLayout(path_layout)

        # Tabs
        self.tabs = QTabWidget()
        self.dashboard = DashboardPanel()
        self.performance = PerformancePanel()
        self.dpi_panel = DpiPanel()
        self.advanced = AdvancedPanel()
        self.tabs.addTab(self.dashboard, "Dashboard")
        self.tabs.addTab(self.performance, "Performance")
        self.tabs.addTab(self.dpi_panel, "DPI")
        self.tabs.addTab(self.advanced, "Advanced")
        main_layout.addWidget(self.tabs, 1)

        # Bottom: "Refresh All" and "Save All"
        btn_bar = QHBoxLayout()
        self.refresh_all_btn = QPushButton("Refresh All")
        self.refresh_all_btn.clicked.connect(self._on_refresh_all)
        btn_bar.addWidget(self.refresh_all_btn)

        main_layout.addLayout(btn_bar)

        # Status bar with progress bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_progress = QProgressBar()
        self.status_progress.setRange(0, 0)  # indeterminate
        self.status_progress.setFixedWidth(160)
        self.status_progress.setFixedHeight(16)
        self.status_progress.hide()
        self.status_bar.addPermanentWidget(self.status_progress)
        self.status_bar.showMessage("Connecting…")

        # ── Wire per-section Apply buttons ─────────────────────────
        self.dashboard.refresh_btn.clicked.connect(self._on_refresh_all)
        self.performance.polling_apply.clicked.connect(self._on_apply_polling)
        self.performance.debounce_apply.clicked.connect(self._on_apply_debounce)
        self.performance.liftoff_apply.clicked.connect(self._on_apply_liftoff)
        self.dpi_panel.apply_btn.clicked.connect(self._on_apply_dpi)
        self.advanced.toggle_apply.clicked.connect(self._on_apply_toggles)
        self.advanced.sleep_apply.clicked.connect(self._on_apply_sleep)
        

        # Collect all interactive buttons so we can lock them
        self._all_buttons = [
            self.manual_path_btn,
            self.reconnect_btn,
            self.refresh_all_btn,
            
            self.dashboard.refresh_btn,
            self.performance.polling_apply,
            self.performance.debounce_apply,
            self.performance.liftoff_apply,
            self.dpi_panel.apply_btn,
            self.advanced.toggle_apply,
            self.advanced.sleep_apply,
            
        ]

        # ── Start the thread ───────────────────────────────────────
        self._thread.start()

    # ── Busy-state helpers ─────────────────────────────────────────

    def _set_busy(self, busy: bool) -> None:
        if busy:
            self._busy_count += 1
        else:
            self._busy_count = max(0, self._busy_count - 1)

        active = self._busy_count > 0
        for btn in self._all_buttons:
            btn.setEnabled(not active)

        if active:
            self.status_bar.showMessage("Fetching…")
            self.status_progress.show()
        else:
            self.status_progress.hide()

    # ── Worker dispatch helpers ────────────────────────────────────

    def _execute(self, fn, *args) -> None:
        """Queue a callable to run on the worker thread."""
        import functools
        cb = functools.partial(fn, *args) if args else fn
        self._set_busy(True)
        self._worker.execute.emit(cb)

    def _schedule_auto_detect(self) -> None:
        # auto_detect is quick (just HID enumeration + open); no busy token needed.
        # refresh_all is where the real waiting happens.
        self._worker.execute.emit(self._worker.auto_detect)

    # ── Slots (run on MAIN thread) ─────────────────────────────────

    def _on_connected(self, path: str) -> None:
        self.path_edit.setText(path)
        self.path_edit.setReadOnly(True)
        self.status_bar.showMessage(f"Connected: {path} — fetching…")
        self._execute(self._worker.refresh_all)

    def _on_error(self, msg: str) -> None:
        self._set_busy(False)
        self.status_bar.showMessage(f"⚠ {msg}")
        if "not found" in msg.lower() and not self.path_edit.text():
            self.path_edit.setPlaceholderText("No device — enter path or click Auto")

    def _on_battery(self, info: MouseInfo) -> None:
        d = _info_to_dict(info)
        self.dashboard.populate(d)
        self._set_busy(False)

    def _on_status(self, info: MouseInfo) -> None:
        d = _info_to_dict(info)
        self.dashboard.populate(d)
        self.performance.populate(d)
        self.dpi_panel.populate(d)
        self.advanced.populate(d)
        self._set_busy(False)
        self.status_bar.showMessage("Status refreshed", 5000)

    def _on_write_done(self, command: str, ok: bool) -> None:
        self._set_busy(False)
        if ok:
            self.status_bar.showMessage(f"✓ {command} written", 5000)
            # Re-read to reflect changes
            self._execute(self._worker.refresh_all)
        else:
            self.status_bar.showMessage(f"✗ {command} failed — no device response", 10000)
            QMessageBox.warning(self, "Write Failed",
                                f"Could not write {command}.\nMouse may be asleep or disconnected.")

    # ── UI action handlers ─────────────────────────────────────────

    def _on_manual_path(self) -> None:
        """Let the user type a device path directly."""
        path, ok = QInputDialog.getText(
            self, "Device Path",
            "Enter HID path (e.g. /dev/hidraw5):",
            text=self.path_edit.text(),
        )
        if ok and path.strip():
            self.path_edit.setText(path.strip())
            self._execute(self._worker.open_path, path.strip())

    def _on_refresh_all(self) -> None:
        self.status_bar.showMessage("Fetching…")
        self._execute(self._worker.refresh_all)

    def _on_apply_polling(self) -> None:
        hz = self.performance.polling_combo.currentData()
        self._execute(self._worker.write_polling_rate, hz)

    def _on_apply_debounce(self) -> None:
        ms = self.performance.debounce_spin.value()
        self._execute(self._worker.write_debounce, ms)

    def _on_apply_liftoff(self) -> None:
        level = self.performance.liftoff_slider.value()
        self._execute(self._worker.write_lift_off, level)

    def _on_apply_dpi(self) -> None:
        stage = self.dpi_panel.current_stage()
        x = self.dpi_panel.current_x_dpi()
        y = self.dpi_panel.current_y_dpi()
        self._execute(self._worker.write_dpi, stage, x, y)

    def _on_apply_toggles(self) -> None:
        ms = self.advanced.motion_sync_cb.isChecked()
        self._execute(self._worker.write_motion_sync, ms)
        as_ = self.advanced.angle_snap_cb.isChecked()
        self._execute(self._worker.write_angle_snap, as_)
        rc = self.advanced.ripple_cb.isChecked()
        self._execute(self._worker.write_ripple, rc)

    def _on_apply_sleep(self) -> None:
        seconds = self.advanced.sleep_spin.value()
        self._execute(self._worker.write_sleep_timeout, seconds)

    # ── Cleanup ────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._worker.close()
        self._thread.quit()
        self._thread.wait()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("atkctl-gui")
    app.setOrganizationName("atkctl")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()