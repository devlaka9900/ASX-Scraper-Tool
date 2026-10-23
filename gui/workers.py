"""Background jobs: pipeline run and date check, each on its own QThread.

The workers never touch widgets; they only emit signals (queued to the GUI
thread). Cancel is a plain threading.Event set directly from the GUI thread.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core import datecheck
from core.events import FAILED_PREFIX, Cancelled
from core.pipeline import RunRequest, run_pipeline
from core.summary import RunResult
from utils import logger as core_logger


class _LogBridge(QObject):
    message = Signal(str, str)      # level, text


class QtLogHandler(logging.Handler):
    """Forwards core log records to the live-log panel (thread-safe via signal)."""

    def __init__(self, bridge: _LogBridge):
        super().__init__(level=logging.INFO)
        self._bridge = bridge
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._bridge.message.emit(record.levelname, self.format(record))
        except Exception:
            pass


class _Worker(QObject):
    progress = Signal(str, int, int, str)     # stage, done, total, message
    done = Signal(object)                     # RunResult
    failed = Signal(str)

    def __init__(self, job: Callable[[Callable, threading.Event], RunResult], cancel: threading.Event):
        super().__init__()
        self._job = job
        self._cancel = cancel
        self._last_emit = 0.0
        self._last_stage = ""

    def _on_progress(self, stage: str, done: int, total: int, msg: str) -> None:
        # throttle to ~20 updates/s, but never drop stage changes, the final tick, or a
        # failed-file message (the run view counts failures from those)
        now = time.monotonic()
        if (stage != self._last_stage or done >= total or msg.startswith(FAILED_PREFIX)
                or now - self._last_emit >= 0.05):
            self._last_stage, self._last_emit = stage, now
            self.progress.emit(stage, done, total, msg)

    @Slot()
    def run(self) -> None:
        try:
            result = self._job(self._on_progress, self._cancel)
        except Cancelled:
            self.failed.emit("Cancelled")
            return
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.done.emit(result)


class JobRunner(QObject):
    """Owns at most one running job and relays its signals to the GUI."""

    started = Signal(str)                     # "run" | "datecheck"
    progress = Signal(str, int, int, str)
    log = Signal(str, str)
    completed = Signal(str, object)           # kind, RunResult
    failed = Signal(str, str)                 # kind, message
    busyChanged = Signal(bool)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _Worker | None = None
        self._cancel = threading.Event()
        self._kind = ""
        self._bridge = _LogBridge()
        self._bridge.message.connect(self.log)
        self._handler = QtLogHandler(self._bridge)

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def start_run(self, req: RunRequest) -> None:
        self._start("run", lambda cb, cancel: run_pipeline(req, progress_cb=cb, cancel=cancel))

    def start_datecheck(self, path: Path, cutoff) -> None:
        self._start("datecheck",
                    lambda cb, cancel: datecheck.check_folder(path, cutoff, progress_cb=cb, cancel=cancel))

    def cancel(self) -> None:
        self._cancel.set()

    def shutdown(self) -> None:
        """Called on window close: cancel and wait for the thread."""
        self._cancel.set()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(8000)

    # ---- internals ---------------------------------------------------------- #

    def _start(self, kind: str, job) -> None:
        if self.busy:
            return
        self._kind = kind
        self._cancel = threading.Event()
        core_logger.add_handler(self._handler)

        thread = QThread()
        worker = _Worker(job, self._cancel)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.progress)
        worker.done.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        worker.done.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._cleanup)
        self._thread, self._worker = thread, worker
        # `started` first so listeners know the job kind when they see busy=True
        self.started.emit(kind)
        self.busyChanged.emit(True)
        thread.start()

    def _on_done(self, result: RunResult) -> None:
        self.completed.emit(self._kind, result)

    def _on_failed(self, message: str) -> None:
        self.failed.emit(self._kind, message)

    def _cleanup(self) -> None:
        core_logger.remove_handler(self._handler)
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._thread = self._worker = None
        self.busyChanged.emit(False)
