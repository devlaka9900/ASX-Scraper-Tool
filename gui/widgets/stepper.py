"""Five-step horizontal stepper (Scrape · Folders · Download · Analyse · Reports)."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from core.events import STAGE_LABELS, STAGES
from gui import anim, icons, theme


class Stepper(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._index = -1          # current step; len(STAGES) = all done
        self._state = "idle"      # idle | running | done | failed | cancelled
        self._pulse = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(86)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Run progress steps")
        theme.bus.changed.connect(self.update)

    def reset(self) -> None:
        self._index, self._state = -1, "idle"
        self._timer.stop()
        self.update()

    def set_stage(self, stage: str) -> None:
        idx = STAGES.index(stage) if stage in STAGES else -1
        self._index = max(self._index, idx)
        self._state = "running"
        if not anim.reduced_motion():
            self._timer.start()
        self.setAccessibleDescription(f"Step {self._index + 1} of {len(STAGES)}: {STAGE_LABELS.get(stage, stage)}")
        self.update()

    def finish(self, state: str) -> None:
        """state: done | failed | cancelled"""
        self._state = state
        if state == "done":
            self._index = len(STAGES)
        self._timer.stop()
        self.update()

    def _tick(self) -> None:
        self._pulse = (self._pulse + 0.035) % 1.0
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(600, 86)

    def paintEvent(self, _event) -> None:
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = len(STAGES)
        margin = 56.0
        step_w = (self.width() - 2 * margin) / (n - 1)
        cy = 24.0
        r = 14.0

        font = QFont(self.font())
        font.setPointSizeF(9.5)

        # connectors
        for i in range(n - 1):
            x1 = margin + i * step_w + r + 4
            x2 = margin + (i + 1) * step_w - r - 4
            done = self._index > i
            p.setPen(QPen(t.color("accent") if done else t.color("border_strong"), 2.4,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x1, cy), QPointF(x2, cy))

        for i, stage in enumerate(STAGES):
            cx = margin + i * step_w
            is_done = self._index > i
            is_current = self._index == i and self._state in ("running", "failed", "cancelled")
            failed_here = is_current and self._state == "failed"

            if is_current and self._state == "running":
                glow = 0.5 + 0.5 * math.sin(self._pulse * 2 * math.pi)
                halo = t.color("accent", 0.18 + 0.20 * glow)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(halo)
                p.drawEllipse(QPointF(cx, cy), r + 4 + 3 * glow, r + 4 + 3 * glow)

            if is_done:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(t.color("accent"))
                p.drawEllipse(QPointF(cx, cy), r, r)
                p.drawPixmap(QPointF(cx - 8, cy - 8), icons.pixmap("check", t["accent_text"], 16, self.devicePixelRatioF(), 2.6))
            elif failed_here:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(t.color("error"))
                p.drawEllipse(QPointF(cx, cy), r, r)
                p.drawPixmap(QPointF(cx - 8, cy - 8), icons.pixmap("x", "#ffffff", 16, self.devicePixelRatioF(), 2.6))
            else:
                ring = t.color("accent") if is_current else t.color("border_strong")
                p.setPen(QPen(ring, 2.2))
                p.setBrush(t.color("surface"))
                p.drawEllipse(QPointF(cx, cy), r, r)
                p.setFont(font)
                p.setPen(t.color("text" if is_current else "text_muted"))
                p.drawText(QRectF(cx - r, cy - r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter, str(i + 1))

            p.setFont(font)
            p.setPen(t.color("text" if (is_done or is_current) else "text_muted"))
            p.drawText(QRectF(cx - step_w / 2, cy + r + 8, step_w, 22), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                       STAGE_LABELS[stage])
        p.end()
