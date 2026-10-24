"""Main window: sidebar + page stack, wiring between pages and the job runner."""
from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QMessageBox, QWidget

from core.notes import NotesError, NotesStore
from core.paths import resource_path
from core.pipeline import RunRequest
from core.summary import RunResult, SummaryError, load_run
from core.version import APP_NAME
from gui import theme
from gui.pages.agent import AgentPage
from gui.pages.date_checker import DateCheckerPage
from gui.pages.history import HistoryPage
from gui.pages.new_run import NewRunPage
from gui.pages.notes import NotesPage
from gui.pages.results import ResultsPage
from gui.pages.run_view import RunView
from gui.settings import Settings
from gui.widgets.fade_stack import FadeStack
from gui.widgets.sidebar import Sidebar
from gui.workers import JobRunner


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, notes_path=None):
        super().__init__()
        self._settings = settings
        self._run_screen_active = False
        self._active_kind = ""

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1100, 720)
        icon_path = resource_path("gui/resources/app.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        central = QWidget()
        self.setCentralWidget(central)
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self.sidebar = Sidebar()
        row.addWidget(self.sidebar)
        self.stack = FadeStack()
        row.addWidget(self.stack, 1)

        self.new_run = NewRunPage(settings)
        self.run_view = RunView()
        self.results = ResultsPage()
        self.history = HistoryPage(settings)
        self.date_checker = DateCheckerPage(settings)
        try:
            notes_store, notes_error = NotesStore(notes_path), None
        except (NotesError, OSError) as exc:
            notes_store, notes_error = None, str(exc)
        self.notes = NotesPage(notes_store, notes_error)
        self.notes_store = notes_store
        self.agent = AgentPage()
        for page in (self.new_run, self.run_view, self.results, self.history, self.date_checker,
                     self.notes, self.agent):
            self.stack.addWidget(page)

        self.runner = JobRunner(self)
        self._wire()

        geometry = settings.geometry
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1280, 820)
        self.sidebar.select("new_run")
        self.stack.setCurrentWidget(self.new_run)
        theme.bus.changed.connect(self._apply_titlebar)

    # ---- wiring ---------------------------------------------------------------- #

    def _wire(self) -> None:
        self.sidebar.navigate.connect(self.navigate)
        self.sidebar.themeToggled.connect(self._toggle_theme)

        self.new_run.startRequested.connect(self._start_run)
        self.run_view.cancelRequested.connect(self.runner.cancel)
        self.run_view.backRequested.connect(self._back_to_form)
        self.results.newRunRequested.connect(lambda: self.navigate("new_run"))
        self.results.historyRequested.connect(lambda: self.navigate("history"))
        self.history.openRequested.connect(self._open_history_item)
        self.date_checker.checkRequested.connect(self._start_datecheck)

        self.runner.started.connect(self._on_started)
        self.runner.progress.connect(self._on_progress)
        self.runner.log.connect(self.run_view.on_log)
        self.runner.completed.connect(self._on_completed)
        self.runner.failed.connect(self._on_failed)
        self.runner.busyChanged.connect(self._on_busy)

    def navigate(self, key: str) -> None:
        target = {
            "new_run": self.run_view if self._run_screen_active else self.new_run,
            "results": self.results,
            "history": self.history,
            "date_checker": self.date_checker,
            "notes": self.notes,
            "agent": self.agent,
        }[key]
        # leaving the Notes page with unsaved edits: ask first, and stay if the user cancels
        if self.stack.currentWidget() is self.notes and target is not self.notes and not self.notes.can_leave():
            self.sidebar.select("notes")
            return
        self.sidebar.select(key)
        self.stack.fade_to(target)
        if key == "new_run" and target is self.new_run:
            self.new_run.focus_first()

    # ---- run lifecycle ------------------------------------------------------------ #

    def _start_run(self, req: RunRequest) -> None:
        if self.runner.busy:
            return
        self._run_screen_active = True
        self.run_view.begin(req)
        self.runner.start_run(req)
        self.navigate("new_run")

    def _start_datecheck(self, path, cutoff) -> None:
        if self.runner.busy:
            return
        self.runner.start_datecheck(path, cutoff)

    def _back_to_form(self) -> None:
        self._run_screen_active = False
        self.navigate("new_run")

    def _on_started(self, kind: str) -> None:
        self._active_kind = kind

    def _on_busy(self, busy: bool) -> None:
        self.new_run.set_busy(busy)
        self.date_checker.set_busy(busy and self._active_kind == "datecheck")

    def _on_progress(self, stage: str, done: int, total: int, message: str) -> None:
        if self._active_kind == "run":
            self.run_view.on_progress(stage, done, total, message)
        elif stage == "analyse":
            self.date_checker.on_progress(done, total)

    def _on_completed(self, kind: str, result: RunResult) -> None:
        if kind == "datecheck":
            self.date_checker.show_result(result)
            return
        status = result.meta.status
        if status == "completed":
            self._settings.add_history_root(result.base_dir.parent if result.base_dir else self._settings.output_dir)
            self.run_view.finish_ok()
            current = self.stack.currentWidget()
            if current in (self.run_view, self.new_run):
                self.results.show_result(result)
                # let the stepper finish visibly, then reveal the dashboard
                QTimer.singleShot(450, self._show_results_after_run)
            else:
                # The user moved on while the run was going: don't yank them away or replace
                # a result they may be reading. The run is in History (and Results, unless
                # they are looking at an older run right now).
                self._run_screen_active = False
                if current is not self.results:
                    self.results.show_result(result)
        else:
            self.run_view.finish_stopped(status, result.meta.error or "The run did not complete.")

    def _show_results_after_run(self) -> None:
        self._run_screen_active = False
        if self.stack.currentWidget() in (self.run_view, self.new_run):
            self.navigate("results")

    def _on_failed(self, kind: str, message: str) -> None:
        if kind == "run":
            self.run_view.finish_stopped("failed", message)
        elif message != "Cancelled":
            QMessageBox.warning(self, APP_NAME, f"The date check failed:\n\n{message}")

    def _open_history_item(self, item) -> None:
        try:
            result = load_run(item.path)
        except SummaryError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.results.show_result(result)
        self.navigate("results")

    # ---- theme -------------------------------------------------------------------- #

    def _toggle_theme(self) -> None:
        new = "light" if theme.current().is_dark else "dark"
        self._settings.theme = new
        theme.apply(QApplication.instance(), new)

    def _apply_titlebar(self) -> None:
        """Fallback for dark title bars (Qt 6.8+ normally handles it via the colour scheme)."""
        if sys.platform != "win32" or not self.isVisible():
            return
        try:
            value = ctypes.c_int(1 if theme.current().is_dark else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(self.winId()), 20, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_titlebar()

    # ---- close ---------------------------------------------------------------------- #

    def closeEvent(self, event) -> None:
        if self.notes.has_unsaved() and not self.notes.can_leave():
            event.ignore()
            return
        if self.runner.busy:
            answer = QMessageBox.question(
                self, APP_NAME, "A job is still running. Cancel it and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.runner.shutdown()
        self._settings.geometry = self.saveGeometry()
        self._settings.sync()
        event.accept()
