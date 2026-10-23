"""Collapsible live-log panel."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

from gui.widgets.common import IconButton

MAX_LINES = 5000


class LogView(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._toggle = IconButton("Live log", "chevron_r", variant="ghost", size=16)
        self._toggle.setCheckable(True)
        self._toggle.toggled.connect(self._on_toggle)
        self._toggle.setStyleSheet("text-align: left;")
        lay.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignLeft)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(MAX_LINES)
        self._text.setMinimumHeight(150)
        self._text.setAccessibleName("Live log")
        self._text.setVisible(False)
        lay.addWidget(self._text, 1)

    def _on_toggle(self, on: bool) -> None:
        self._text.setVisible(on)
        self._toggle.set_icon("chevron" if on else "chevron_r")

    def clear(self) -> None:
        self._text.clear()

    def append(self, level: str, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self._text.appendPlainText(f"{stamp}  {level:<7} {message}")

    def expand(self, on: bool = True) -> None:
        self._toggle.setChecked(on)
