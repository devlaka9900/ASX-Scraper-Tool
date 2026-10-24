"""Results page: the shared dashboard, or an empty state before any run."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

from core.summary import RunResult
from gui import icons, theme
from gui.widgets.common import IconButton, label
from gui.widgets.results_view import ResultsView
from gui.widgets.watermark import WatermarkWidget


class ResultsPage(QWidget):
    newRunRequested = Signal()
    historyRequested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        lay.addWidget(self._stack)

        empty = WatermarkWidget()
        el = QVBoxLayout(empty)
        el.addStretch(2)
        self._empty_icon = QLabel()
        self._empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(self._empty_icon)
        title = label("No results yet", "h2")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(title)
        hint = label("Start a run, or open an earlier one from History.", "muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(hint)
        el.addSpacing(12)
        row = QVBoxLayout()
        start = IconButton("Start a run", "plus", variant="primary")
        start.clicked.connect(self.newRunRequested)
        start.setFixedWidth(180)
        hist = IconButton("Open History", "history")
        hist.clicked.connect(self.historyRequested)
        hist.setFixedWidth(180)
        row.addWidget(start, 0, Qt.AlignmentFlag.AlignCenter)
        row.addWidget(hist, 0, Qt.AlignmentFlag.AlignCenter)
        el.addLayout(row)
        el.addStretch(3)

        self.view = ResultsView()
        self._stack.addWidget(empty)
        self._stack.addWidget(self.view)
        theme.bus.changed.connect(self._refresh_icon)
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        self._empty_icon.setPixmap(icons.pixmap("chart", theme.current()["text_muted"], 44,
                                                self.devicePixelRatioF(), 1.4))

    def has_result(self) -> bool:
        return self.view.result is not None

    def show_result(self, result: RunResult, animate: bool = True) -> None:
        self.view.set_result(result, animate)
        self._stack.setCurrentWidget(self.view)
