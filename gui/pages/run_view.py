"""Live run view: stepper, overall progress, counters, throughput/ETA, log, Cancel."""
from __future__ import annotations

import time

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from core.events import FAILED_PREFIX
from core.pipeline import RunRequest
from gui import anim, icons, theme
from gui.widgets.common import ElidedLabel, IconButton, card, label
from gui.widgets.log_view import LogView
from gui.widgets.stepper import Stepper
from gui.widgets.watermark import WatermarkWidget

# share of the overall bar given to each stage
_WEIGHTS = {"scrape": (0.0, 0.06), "folders": (0.06, 0.02), "download": (0.08, 0.72),
            "analyse": (0.80, 0.16), "report": (0.96, 0.04)}
_STAGE_TITLE = {
    "scrape": "Fetching the page and finding PDF links…",
    "folders": "Creating output folders…",
    "download": "Downloading PDFs",
    "analyse": "Reading PDF dates and page counts",
    "report": "Writing reports",
}


def _fmt_eta(seconds: float) -> str:
    s = int(max(0, round(seconds)))
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60:02d}s"


class RunView(WatermarkWidget):
    cancelRequested = Signal()
    backRequested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(16)

        self._title = label("Running…", "h1")
        lay.addWidget(self._title)
        self._subtitle = ElidedLabel("", "secondary")
        lay.addWidget(self._subtitle)

        panel = card()
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(24, 20, 24, 20)
        pl.setSpacing(14)
        self._stepper = Stepper()
        pl.addWidget(self._stepper)

        self._stage_label = label("", "h3")
        pl.addWidget(self._stage_label)
        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)
        self._bar.setTextVisible(False)
        self._bar.setAccessibleName("Overall progress")
        pl.addWidget(self._bar)

        stats = QHBoxLayout()
        stats.setSpacing(24)
        self._count = label("", "secondary")
        self._rate = label("", "secondary")
        self._failed = label("", "secondary")
        stats.addWidget(self._count)
        stats.addWidget(self._rate)
        stats.addWidget(self._failed)
        stats.addStretch(1)
        pl.addLayout(stats)

        self._current = ElidedLabel("", "muted")
        pl.addWidget(self._current)
        lay.addWidget(panel)

        self._notice = card("flat")
        nl = QHBoxLayout(self._notice)
        nl.setContentsMargins(14, 12, 14, 12)
        nl.setSpacing(10)
        self._notice_icon = QLabel()
        self._notice_icon.setFixedSize(20, 20)
        nl.addWidget(self._notice_icon, 0, Qt.AlignmentFlag.AlignTop)
        self._notice_text = label("", None, wrap=True)
        nl.addWidget(self._notice_text, 1)
        self._notice.setVisible(False)
        lay.addWidget(self._notice)

        self._log = LogView()
        lay.addWidget(self._log, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._back = IconButton("Back to New run", "plus")
        self._back.clicked.connect(self.backRequested)
        self._back.setVisible(False)
        buttons.addWidget(self._back)
        self._cancel = IconButton("Cancel run", "stop", variant="danger", icon_role="text")
        self._cancel.clicked.connect(self._on_cancel)
        buttons.addWidget(self._cancel)
        lay.addLayout(buttons)

        self._smooth = 0.0          # displayed bar value (eased toward target)
        self._target = 0.0
        self._ease = QTimer(self)
        self._ease.setInterval(16)
        self._ease.timeout.connect(self._ease_tick)

        self._stage = ""
        self._stage_started = 0.0
        self._failed_n = 0
        self._notice_state = ""
        theme.bus.changed.connect(self._refresh_notice_icon)

    # ---- lifecycle ----------------------------------------------------------- #

    def begin(self, req: RunRequest) -> None:
        self._title.setText("Running…")
        start = f"  ·  Startpoint {req.startpoint}" if req.startpoint else ""
        self._subtitle.set_full_text(
            f"DocumentId {req.project_id}{start}  ·  cutoff {req.cutoff:%Y-%m-%d}  ·  {req.url}")
        self._stepper.reset()
        self._stage = ""
        self._failed_n = 0
        self._smooth = self._target = 0.0
        self._bar.setValue(0)
        self._stage_label.setText("Starting…")
        self._count.setText("")
        self._rate.setText("")
        self._failed.setText("")
        self._current.set_full_text("")
        self._notice.setVisible(False)
        self._back.setVisible(False)
        self._cancel.setVisible(True)
        self._cancel.setEnabled(True)
        self._cancel.setText("Cancel run")
        self._log.clear()

    def on_progress(self, stage: str, done: int, total: int, message: str) -> None:
        if stage != self._stage:
            self._stage = stage
            self._stage_started = time.monotonic()
            self._stepper.set_stage(stage)
        base, weight = _WEIGHTS.get(stage, (0.0, 0.0))
        frac = (done / total) if total else 0.0
        self._set_target(base + weight * frac)

        title = _STAGE_TITLE.get(stage, stage)
        if stage in ("download", "analyse"):
            self._stage_label.setText(f"{title}  —  {done:,} of {total:,}")
            self._count.setText(f"{done:,} / {total:,} files")
            elapsed = time.monotonic() - self._stage_started
            if done and elapsed >= 1.0:       # too noisy before the first second
                rate = done / elapsed
                self._rate.setText(f"{rate:.1f} files/s  ·  ETA {_fmt_eta((total - done) / rate)}")
            if message.startswith(FAILED_PREFIX):
                self._failed_n += 1
            self._current.set_full_text(message.removeprefix(FAILED_PREFIX))
        else:
            self._stage_label.setText(title)
            self._current.set_full_text(message)
        self._failed.setText(f"{self._failed_n} failed" if self._failed_n else "")

    def on_log(self, level: str, message: str) -> None:
        self._log.append(level, message)

    def finish_ok(self) -> None:
        self._set_target(1.0)
        self._stepper.finish("done")
        self._cancel.setVisible(False)
        self._stage_label.setText("Done")

    def finish_stopped(self, state: str, message: str) -> None:
        """state: failed | cancelled"""
        self._stepper.finish(state)
        self._title.setText("Run failed" if state == "failed" else "Run cancelled")
        self._stage_label.setText("Stopped before completion")
        self._cancel.setVisible(False)
        self._back.setVisible(True)
        self._notice_state = "error" if state == "failed" else "no_date"
        self._notice_text.setText(message if state == "failed"
                                  else "The run was cancelled. Files already downloaded are kept; "
                                       "no reports were written.")
        self._notice.setVisible(True)
        self._refresh_notice_icon()
        if state == "failed":
            self._log.expand(True)

    def _on_cancel(self) -> None:
        self._cancel.setEnabled(False)
        self._cancel.setText("Cancelling…")
        self.cancelRequested.emit()

    # ---- smooth bar ------------------------------------------------------------ #

    def _set_target(self, value: float) -> None:
        self._target = max(self._target, min(1.0, value))
        if anim.reduced_motion():
            self._smooth = self._target
            self._bar.setValue(int(self._smooth * 1000))
        elif not self._ease.isActive():
            self._ease.start()

    def _ease_tick(self) -> None:
        diff = self._target - self._smooth
        if abs(diff) < 0.0005:
            self._smooth = self._target
            self._ease.stop()
        else:
            self._smooth += diff * 0.18
        self._bar.setValue(int(self._smooth * 1000))

    def _refresh_notice_icon(self) -> None:
        if self._notice_state:
            self._notice_icon.setPixmap(icons.pixmap(
                "alert", theme.current()[self._notice_state], 20, self.devicePixelRatioF()))
