"""Dashboard tab — device overview, battery, connection status."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from atkctl_gui.ui._helpers import add_labelled_row, value_label


class DashboardPanel(QWidget):
    """Top-level overview of the mouse with visual indicators."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Device info group ──────────────────────────────────────
        dev_group = QGroupBox("Device")
        dev_layout = QVBoxLayout(dev_group)
        self.path_label = value_label()
        self.firmware_badge = value_label()
        self.connection_badge = QLabel()
        self.wireless_badge = QLabel()
        add_labelled_row(dev_layout, "Path:", self.path_label)
        add_labelled_row(dev_layout, "Firmware:", self.firmware_badge)
        add_labelled_row(dev_layout, "Connection:", self.connection_badge)

        # Wireless mode shown below connection when present
        self.wireless_row = QHBoxLayout()
        self.wireless_row.addSpacing(108)  # align under connection badge
        self.wireless_row.addWidget(self.wireless_badge)
        dev_layout.addLayout(self.wireless_row)
        self.wireless_row_label = QLabel("")
        layout.addWidget(dev_group)

        # ── Battery group with progress bar + percentage beside ────
        bat_group = QGroupBox("Battery")
        bat_layout = QVBoxLayout(bat_group)

        bar_row = QHBoxLayout()
        self.battery_bar = QProgressBar()
        self.battery_bar.setRange(0, 100)
        self.battery_bar.setFormat("")  # no text inside
        self.battery_bar.setFixedHeight(22)
        self.battery_bar.setTextVisible(False)
        bar_row.addWidget(self.battery_bar, 1)
        self.battery_pct = QLabel("—")
        self.battery_pct.setFixedWidth(42)
        self.battery_pct.setStyleSheet("font-weight: bold; font-size: 14px;")
        bar_row.addWidget(self.battery_pct)
        bat_layout.addLayout(bar_row)

        meta_row = QHBoxLayout()
        meta_row.addWidget(QLabel("Status:"))
        self.charge_label = value_label()
        meta_row.addWidget(self.charge_label)
        meta_row.addStretch()
        bat_layout.addLayout(meta_row)

        layout.addWidget(bat_group)

        # ── Refresh button ─────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Re-read all device telemetry")
        btn_row.addStretch()
        btn_row.addWidget(self.refresh_btn)
        layout.addLayout(btn_row)

        layout.addStretch()

    def populate(self, info: dict) -> None:
        """Update widgets from a MouseInfo-as-dict."""
        self.path_label.setText(info.get("path") or "—")

        fw = info.get("firmware") or info.get("version")
        self.firmware_badge.setText(fw or "—")

        conn = info.get("connection_type")
        if conn:
            self.connection_badge.setText(f"● {conn}")
            if conn == "Wireless (2.4GHz)":
                self.connection_badge.setStyleSheet(
                    "color: #2563eb; font-weight: bold;"
                )
            else:
                self.connection_badge.setStyleSheet(
                    "color: #16a34a; font-weight: bold;"
                )
        else:
            self.connection_badge.setText("?")
            self.connection_badge.setStyleSheet("")

        wm = info.get("wireless_mode")
        if wm:
            self.wireless_badge.setText(f"     ↳ {wm}")
            self.wireless_badge.setStyleSheet("color: #666; font-style: italic;")
            self.wireless_row_label.setText("")
        else:
            self.wireless_badge.setText("")

        bat = info.get("battery")
        if bat and bat.get("level", 0) > 0:
            level = bat["level"]
            self.battery_bar.setValue(level)
            self.battery_pct.setText(f"{level}%")
            # Colour the bar by level
            if level <= 15:
                colour = "#dc2626"  # red
            elif level <= 40:
                colour = "#f97316"  # orange
            else:
                colour = "#22c55e"  # green
            self.battery_bar.setStyleSheet(
                f"QProgressBar::chunk {{ background: {colour}; }}"
            )
            chg = bat.get("charging")
            self.charge_label.setText(
                "🔌 Charging" if chg else "🔋 Discharging"
            )
        else:
            self.battery_bar.setValue(0)
            self.battery_bar.setStyleSheet("")
            self.battery_pct.setText("💤")
            self.charge_label.setText("Sleeping")