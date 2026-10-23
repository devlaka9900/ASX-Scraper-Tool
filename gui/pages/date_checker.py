"""Date Checker: re-categorise already-downloaded PDFs against a new cutoff.

GUI port of check_pdf_dates.py — no scraping, no downloads, nothing is copied.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFileDialog, QHBoxLayout, QLineEdit, QProgressBar, QStackedWidget, QVBoxLayout, QWidget,
)

from core import datecheck
from core.summary import RunResult, scan_history
from gui import theme
from gui.settings import Settings
from gui.widgets.common import IconButton, card, label, primary
from gui.widgets.results_view import ResultsView


class DateCheckerPage(QWidget):
    checkRequested = Signal(object, object)       # Path, datetime

    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self._settings = settings
        self._busy = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 28, 0, 0)
        lay.setSpacing(0)

        head = QVBoxLayout()
        head.setContentsMargins(32, 0, 32, 0)
        head.setSpacing(16)
        head.addWidget(label("Date checker", "h1"))
        head.addWidget(label("Re-check the dates of PDFs you already downloaded against a different cutoff. "
                             "Nothing is downloaded, copied or overwritten.", "secondary", wrap=True))

        form = card()
        fl = QVBoxLayout(form)
        fl.setContentsMargins(20, 16, 20, 16)
        fl.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(label("Folder", "h3"))
        self._path = QLineEdit()
        self._path.setPlaceholderText("A project folder (contains downloads/), a downloads folder, or any folder of PDFs")
        self._path.setAccessibleName("Folder to check")
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._update_state)
        self._path.textChanged.connect(lambda _t: self._debounce.start())
        row1.addWidget(self._path, 1)
        self._runs = QComboBox()
        self._runs.setMinimumWidth(240)
        self._runs.setAccessibleName("Pick from earlier runs")
        self._runs.activated.connect(self._pick_run)
        row1.addWidget(self._runs)
        browse = IconButton("Browse…", "folder")
        browse.clicked.connect(self._browse)
        row1.addWidget(browse)
        fl.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(label("New cutoff", "h3"))
        self._cutoff = QDateEdit()
        self._cutoff.setCalendarPopup(True)
        self._cutoff.setDisplayFormat("yyyy-MM-dd")
        self._cutoff.setAccessibleName("New cutoff date")
        today = date.today()
        self._cutoff.setDate(QDate(today.year, today.month, today.day))
        self._cutoff.setMinimumWidth(160)
        row2.addWidget(self._cutoff)
        row2.addStretch(1)
        self._error = label("", "error")
        row2.addWidget(self._error)
        self._go = primary("Check dates", "play")
        self._go.setMinimumWidth(150)
        self._go.clicked.connect(self._submit)
        row2.addWidget(self._go)
        fl.addLayout(row2)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1000)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        fl.addWidget(self._progress)
        head.addWidget(form)
        lay.addLayout(head)

        self._stack = QStackedWidget()
        placeholder = QWidget()
        pl = QVBoxLayout(placeholder)
        pl.addStretch(1)
        hint = label("Pick a folder and a cutoff, then press Check dates.", "muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pl.addWidget(hint)
        pl.addStretch(2)
        self.view = ResultsView()
        self._export_btn = IconButton("Export reports", "download")
        self._export_btn.setToolTip("Write markdown + Excel reports into <project>/date_checks/<cutoff>_<time>/")
        self._export_btn.clicked.connect(self._export)
        self.view.add_action(self._export_btn)
        self._stack.addWidget(placeholder)
        self._stack.addWidget(self.view)
        lay.addSpacing(8)
        lay.addWidget(self._stack, 1)
        self._update_state()

    # ---- inputs -------------------------------------------------------------- #

    def refresh_runs(self) -> None:
        roots = list(dict.fromkeys([self._settings.output_dir, *self._settings.history_roots()]))
        seen: set[Path] = set()
        self._runs.blockSignals(True)
        self._runs.clear()
        self._runs.addItem("Pick from earlier runs…", None)
        for item in scan_history(roots):
            if item.base_dir in seen or not item.base_exists:
                continue
            seen.add(item.base_dir)
            self._runs.addItem(f"{item.meta.project_id}  ·  cutoff {item.meta.cutoff}", str(item.base_dir))
        self._runs.blockSignals(False)

    def set_source(self, folder: Path) -> None:
        self._path.setText(str(folder))

    def _pick_run(self, index: int) -> None:
        folder = self._runs.itemData(index)
        if folder:
            self._path.setText(folder)

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose folder of PDFs",
                                                  self._path.text() or str(self._settings.output_dir))
        if chosen:
            self._path.setText(chosen)

    def _folder_error(self) -> str | None:
        raw = self._path.text().strip()
        if not raw:
            return None
        p = Path(raw)
        if not p.is_dir():
            return "Folder not found."
        _base, downloads = datecheck.resolve_folder(p)
        if not any(downloads.rglob("*.pdf")):
            return "No PDFs found in this folder."
        return None

    def _update_state(self) -> None:
        err = self._folder_error()
        self._error.setText(err or "")
        self._error.setVisible(bool(err))
        self._go.setEnabled(bool(self._path.text().strip()) and err is None and not self._busy)

    def _submit(self) -> None:
        self._debounce.stop()
        self._update_state()
        if not self._go.isEnabled():
            return
        qd = self._cutoff.date()
        self.checkRequested.emit(Path(self._path.text().strip()), datetime(qd.year(), qd.month(), qd.day()))

    # ---- state driven by MainWindow --------------------------------------------- #

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._progress.setVisible(busy)
        if busy:
            self._progress.setValue(0)
        self._go.setText("Checking…" if busy else "Check dates")
        self._update_state()

    def on_progress(self, done: int, total: int) -> None:
        self._progress.setValue(int(1000 * done / total) if total else 0)

    def show_result(self, result: RunResult) -> None:
        self.view.set_result(result)
        self._stack.setCurrentWidget(self.view)

    def _export(self) -> None:
        result = self.view.result
        if result is None:
            return
        try:
            folder = datecheck.export_reports(result)
        except OSError as exc:
            self._error.setText(f"Export failed: {exc}")
            self._error.setVisible(True)
            return
        from gui import fileops
        fileops.open_path(folder)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh_runs()
