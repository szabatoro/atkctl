"""Shared helpers for panel widgets."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLayout, QWidget


def add_labelled_row(layout: QLayout, label: str, widget: QWidget) -> None:
    """Append a label | widget row to a layout (vertical or horizontal)."""
    row = QHBoxLayout()
    lbl = QLabel(label)
    lbl.setFixedWidth(100)
    lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    row.addWidget(lbl)
    row.addWidget(widget, 1)
    layout.addLayout(row)


def value_label(text: str = "—") -> QLabel:
    """Create a right-aligned value label suitable for data display."""
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    return lbl


def section_title(text: str) -> QLabel:
    """Create a bold section-title label."""
    lbl = QLabel(text)
    lbl.setStyleSheet("font-weight: bold; font-size: 13px; padding: 4px 0;")
    return lbl