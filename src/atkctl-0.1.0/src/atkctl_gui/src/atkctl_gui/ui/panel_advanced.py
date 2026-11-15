"""Advanced tab — toggles, sleep timeout."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from atkctl_gui.ui._helpers import value_label

_ON_STYLE = "color: #166534; font-weight: bold; font-size: 11px; padding: 0 4px;"
_OFF_STYLE = "color: #991b1b; font-weight: bold; font-size: 11px; padding: 0 4px;"
_UNK_STYLE = "color: #999; font-size: 11px; padding: 0 4px;"


class AdvancedPanel(QWidget):
    """On/off toggles, sleep timeout."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Toggle switches (as checkboxes) ─────────────────────────
        toggle_group = QGroupBox("Features")
        toggle_layout = QVBoxLayout(toggle_group)

        self.motion_sync_cb = QCheckBox("Motion Sync")
        self.motion_sync_cb.setToolTip(
            "Locks X/Y timing for consistent diagonal movement"
        )
        self.angle_snap_cb = QCheckBox("Angle Snap (Linear Correction)")
        self.angle_snap_cb.setToolTip(
            "Snaps cursor angle to 45° increments at low speed"
        )
        self.ripple_cb = QCheckBox("Ripple Control")
        self.ripple_cb.setToolTip(
            "Filters surface vibrations from the sensor"
        )

        # Status badges next to each toggle
        self.ms_badge = QLabel()
        self.as_badge = QLabel()
        self.rc_badge = QLabel()

        toggle_layout.addWidget(_togglerow(self.motion_sync_cb, self.ms_badge))
        toggle_layout.addWidget(_togglerow(self.angle_snap_cb, self.as_badge))
        toggle_layout.addWidget(_togglerow(self.ripple_cb, self.rc_badge))

        # Apply button for toggles
        toggle_btn_row = QHBoxLayout()
        self.toggle_apply = QPushButton("Apply Toggles")
        self.toggle_apply.setToolTip("Send the toggle states above to the mouse")
        toggle_btn_row.addStretch()
        toggle_btn_row.addWidget(self.toggle_apply)
        toggle_layout.addLayout(toggle_btn_row)

        layout.addWidget(toggle_group)

        # ── Sleep timeout ──────────────────────────────────────────
        sleep_group = QGroupBox("Auto-Sleep")
        sleep_layout = QVBoxLayout(sleep_group)
        self.sleep_spin = QSpinBox()
        self.sleep_spin.setRange(0, 3600)
        self.sleep_spin.setSuffix(" s")
        self.sleep_spin.setSpecialValueText("Disabled")
        self.sleep_spin.setToolTip("0 = never sleep")
        self.sleep_active = value_label()
        self.sleep_active.setStyleSheet(
            "background: #e0f2e0; border: 1px solid #22c55e; border-radius: 4px;"
            " padding: 1px 6px; font-size: 11px; color: #166534;"
        )
        row = QHBoxLayout()
        self.sleep_apply = QPushButton("Apply")
        row.addWidget(self.sleep_spin, 1)
        row.addWidget(self.sleep_active)
        row.addWidget(self.sleep_apply)
        sleep_layout.addLayout(row)
        layout.addWidget(sleep_group)

        layout.addStretch()

    def populate(self, info: dict) -> None:
        """Set controls to match device state."""
        ms = info.get("motion_sync")
        self._set_tristate(self.motion_sync_cb, ms, self.ms_badge)

        as_ = info.get("angle_snap")
        self._set_tristate(self.angle_snap_cb, as_, self.as_badge)

        rc = info.get("ripple_control")
        self._set_tristate(self.ripple_cb, rc, self.rc_badge)

        sleep_s = info.get("sleep_timeout_s")
        if sleep_s is not None:
            self.sleep_spin.setValue(sleep_s)
            desc = f"{sleep_s}s" if sleep_s > 0 else "Disabled"
            self.sleep_active.setText(desc)
        else:
            self.sleep_active.setText("?")

    def _set_tristate(self, cb: QCheckBox, val: bool | None,
                      badge: QLabel) -> None:
        if val is None:
            cb.setCheckState(Qt.PartiallyChecked)
            badge.setText("(?)")
            badge.setStyleSheet(_UNK_STYLE)
        else:
            cb.setChecked(val)
            badge.setText("ON" if val else "OFF")
            badge.setStyleSheet(_ON_STYLE if val else _OFF_STYLE)


def _togglerow(cb: QCheckBox, badge: QLabel) -> QWidget:
    row = QHBoxLayout()
    row.addWidget(cb)
    row.addWidget(badge)
    row.addStretch()
    w = QWidget()
    w.setLayout(row)
    return w