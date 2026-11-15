"""Performance tab — polling rate, debounce, lift-off distance."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from atkctl.commands import POLLING_CODES_REV
from atkctl_gui.ui._helpers import section_title

# ── Polling rate lookups ──────────────────────────────────────────────
POLLING_HZ_SORTED = sorted(POLLING_CODES_REV.keys())  # [125, 250, 500, 1000, …]

_ACTIVE_STYLE = (
    "background: #e0f2e0; border: 1px solid #22c55e; border-radius: 4px;"
    " padding: 1px 6px; font-size: 11px; color: #166534;"
)


class PerformancePanel(QWidget):
    """Settings that affect sensor response: polling, debounce, lift-off."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Polling rate ────────────────────────────────────────────
        pr_group = QGroupBox("Polling Rate")
        pr_layout = QVBoxLayout(pr_group)
        self.polling_combo = QComboBox()
        for hz in POLLING_HZ_SORTED:
            self.polling_combo.addItem(f"{hz} Hz", hz)
        self.polling_combo.setToolTip("Sensor report rate in Hz")
        self.polling_apply = QPushButton("Apply")
        self.polling_active = QLabel()
        self.polling_active.setStyleSheet(_ACTIVE_STYLE)
        row = QHBoxLayout()
        row.addWidget(self.polling_combo, 1)
        row.addWidget(self.polling_active)
        row.addWidget(self.polling_apply)
        pr_layout.addLayout(row)
        layout.addWidget(pr_group)

        # ── Debounce ────────────────────────────────────────────────
        db_group = QGroupBox("Debounce")
        db_layout = QVBoxLayout(db_group)
        self.debounce_spin = QSpinBox()
        self.debounce_spin.setRange(0, 255)
        self.debounce_spin.setSuffix(" ms")
        self.debounce_spin.setToolTip("Stabilisation time in ms (0–255)")
        self.debounce_apply = QPushButton("Apply")
        self.debounce_active = QLabel()
        self.debounce_active.setStyleSheet(_ACTIVE_STYLE)
        row = QHBoxLayout()
        row.addWidget(self.debounce_spin, 1)
        row.addWidget(self.debounce_active)
        row.addWidget(self.debounce_apply)
        db_layout.addLayout(row)
        layout.addWidget(db_group)

        # ── Lift-off distance ───────────────────────────────────────
        lo_group = QGroupBox("Lift-Off Distance (Silent Height)")
        lo_layout = QVBoxLayout(lo_group)
        self.liftoff_slider = QSlider()
        self.liftoff_slider.setRange(0, 10)
        self.liftoff_slider.setOrientation(Qt.Horizontal)
        self.liftoff_slider.setTickPosition(QSlider.TicksBelow)
        self.liftoff_slider.setTickInterval(1)
        self.liftoff_slider.setPageStep(1)
        self.liftoff_value_label = QLabel("—")
        self.liftoff_value_label.setStyleSheet("font-size: 12px;")
        self.liftoff_slider.valueChanged.connect(self._show_liftoff_label)
        lo_layout.addWidget(self.liftoff_slider)
        lo_layout.addWidget(self.liftoff_value_label)

        btn_row = QHBoxLayout()
        self.liftoff_active = QLabel()
        self.liftoff_active.setStyleSheet(_ACTIVE_STYLE)
        btn_row.addWidget(self.liftoff_active)
        btn_row.addStretch()
        self.liftoff_apply = QPushButton("Apply")
        btn_row.addWidget(self.liftoff_apply)
        lo_layout.addLayout(btn_row)
        layout.addWidget(lo_group)

        layout.addStretch()

    # ── helpers ────────────────────────────────────────────────────

    def _show_liftoff_label(self, val: int) -> None:
        mm = 0.7 + val * 0.1
        self.liftoff_value_label.setText(f"{mm:.1f} mm  (level {val})")

    def populate(self, info: dict) -> None:
        """Set controls to match current device state."""
        hz = info.get("polling_rate_hz")
        if hz is not None:
            idx = self.polling_combo.findData(hz)
            if idx >= 0:
                self.polling_combo.setCurrentIndex(idx)
            self.polling_active.setText(f"{hz} Hz")
        else:
            self.polling_active.hide()

        db = info.get("debounce_ms")
        if db is not None:
            self.debounce_spin.setValue(db)
            self.debounce_active.setText(f"{db} ms")
        else:
            self.debounce_active.hide()

        lo = info.get("lift_off")
        lo_level = info.get("lift_off_level")
        if lo_level is not None:
            self.liftoff_slider.setValue(max(0, lo_level - 1))
            self.liftoff_active.setText(lo or f"level {lo_level}")
        else:
            self.liftoff_active.hide()