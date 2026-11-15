"""DPI tab — single-stage DPI editor with stage overview text."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from atkctl_gui.ui._helpers import add_labelled_row, value_label


class DpiPanel(QWidget):
    """Read / write individual DPI stages."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._stages: list[tuple[int, int]] = []   # (x, y) per stage
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Stage overview (text summary of all stages) ────────────
        overview_group = QGroupBox("Stages")
        overview_layout = QVBoxLayout(overview_group)
        self.stages_label = value_label()
        self.stages_label.setWordWrap(True)
        overview_layout.addWidget(self.stages_label)
        self.active_stage_label = value_label()
        self.active_stage_label.setStyleSheet("font-size: 11px; color: #666;")
        overview_layout.addWidget(self.active_stage_label)
        layout.addWidget(overview_group)

        # ── Editor ──────────────────────────────────────────────────
        edit_group = QGroupBox("Edit Stage")
        edit_layout = QVBoxLayout(edit_group)
        row = QHBoxLayout()
        row.addWidget(QLabel("Stage:"))
        self.stage_combo = QComboBox()
        for i in range(8):
            self.stage_combo.addItem(f"Stage {i}", i)
        self.stage_combo.currentIndexChanged.connect(self._on_stage_changed)
        row.addWidget(self.stage_combo, 1)
        edit_layout.addLayout(row)

        self.x_spin = QSpinBox()
        self.x_spin.setRange(0, 65535)
        self.x_spin.setSingleStep(100)
        self.x_spin.setSuffix(" DPI")
        self.y_spin = QSpinBox()
        self.y_spin.setRange(0, 65535)
        self.y_spin.setSingleStep(100)
        self.y_spin.setSuffix(" DPI")
        add_labelled_row(edit_layout, "X DPI:", self.x_spin)
        add_labelled_row(edit_layout, "Y DPI:", self.y_spin)

        self.apply_btn = QPushButton("Write to Mouse")
        self.apply_btn.setToolTip("Write this stage's DPI to the device")
        edit_layout.addWidget(self.apply_btn, alignment=Qt.AlignRight)
        layout.addWidget(edit_group)

        layout.addStretch()

    # ── internal ───────────────────────────────────────────────────

    def _on_stage_changed(self, idx: int) -> None:
        """Load current stage values into the edit controls."""
        if idx < 0 or idx >= len(self._stages):
            return
        x, y = self._stages[idx]
        self.x_spin.setValue(x)
        self.y_spin.setValue(y)

    def populate(self, info: dict) -> None:
        """Load DPI block from a MouseInfo dict."""
        stages = info.get("dpi_stages", [])
        self._stages = list(stages) if stages else []
        active = info.get("active_dpi_stage")

        # Build a visual overview line
        parts = []
        for i, s in enumerate(self._stages):
            x, y = s
            if x == 0 and y == 0:
                parts.append(f"[{i}: —]")
            elif active == i:
                parts.append(f"[{i}: **{x}×{y}**]")
            else:
                parts.append(f"[{i}: {x}×{y}]")
        sep = "  "
        self.stages_label.setText(sep.join(parts))

        if active is not None:
            self.active_stage_label.setText(f"Active: stage {active}")
            if 0 <= active < 8:
                self.stage_combo.setCurrentIndex(active)
        else:
            self.active_stage_label.setText("Active: ?")

        # Populate the combo with current values
        for i in range(8):
            if i < len(self._stages):
                x, y = self._stages[i]
                text = f"Stage {i}"
                if x > 0 or y > 0:
                    text += f"  ({x}×{y})"
                self.stage_combo.setItemText(i, text)
            else:
                self.stage_combo.setItemText(i, f"Stage {i}  (—)")

        self._on_stage_changed(self.stage_combo.currentIndex())

    def current_stage(self) -> int:
        return self.stage_combo.currentData()

    def current_x_dpi(self) -> int:
        return self.x_spin.value()

    def current_y_dpi(self) -> int:
        return self.y_spin.value()