"""Agent 🤖 — placeholder page: "under construction / coming soon" with a slight animation.

Purely decorative: a robot that bobs gently over a soft glow, three pulsing dots and an
animated hazard-stripe bar. The animation only runs while the page is visible and is a
static picture when reduced motion is requested.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QMovie, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from core.paths import resource_path
from gui import anim, theme
from gui.widgets.common import card, label
from gui.widgets.watermark import WatermarkWidget

FRAME_MS = 33          # ~30 fps


class _Animated(QWidget):
    """Base: a phase counter that advances only while the widget is visible."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.phase = 0.0                      # seconds
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)
        theme.bus.changed.connect(self.update)

    def _tick(self) -> None:
        self.phase += FRAME_MS / 1000.0
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not anim.reduced_motion():
            self._timer.start()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    @property
    def running(self) -> bool:
        return self._timer.isActive()


ROBOT_GIF = "gui/resources/agent_robot.gif"     # 93x150 transparent loop, 132 frames (~4.4 s)
ROBOT_SIZE = QSize(112, 180)                    # drawn size (the GIF is scaled up smoothly)


class AgentHero(_Animated):
    """The animated robot (a GIF played with QMovie) over a soft pulsing glow, with three
    'thinking' dots underneath. Falls back to the 🤖 emoji if the GIF cannot be loaded."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(240, 236)
        self.setAccessibleName("Agent robot illustration")
        self._movie: QMovie | None = None
        path = resource_path(ROBOT_GIF)
        if path.exists():
            movie = QMovie(str(path))
            if movie.isValid():
                movie.setScaledSize(ROBOT_SIZE)
                movie.setCacheMode(QMovie.CacheMode.CacheAll)    # 132 small frames: decode once
                movie.frameChanged.connect(lambda _n: self.update())
                self._movie = movie
                movie.jumpToFrame(0)

    def sizeHint(self) -> QSize:
        return QSize(240, 236)

    # the GIF plays and pauses together with the other animation (visible + motion allowed)
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._movie is not None:
            if anim.reduced_motion():
                self._movie.jumpToFrame(0)
            else:
                self._movie.start()

    def hideEvent(self, event) -> None:
        if self._movie is not None:
            self._movie.setPaused(True)
        super().hideEvent(event)

    def paintEvent(self, _event) -> None:
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        cx, cy = self.width() / 2, 112.0
        pulse = 0.5 + 0.5 * math.sin(self.phase * 2 * math.pi / 3.2)

        # soft glow behind the robot
        glow = QColor(t["accent"])
        glow.setAlphaF(0.10 + 0.07 * pulse)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        r = 84 + 5 * pulse
        p.drawEllipse(QPointF(cx, cy), r, r)

        if self._movie is not None:
            frame = self._movie.currentPixmap()
            if not frame.isNull():
                dpr = frame.devicePixelRatio() or 1.0
                w, h = frame.width() / dpr, frame.height() / dpr
                p.drawPixmap(QPointF(cx - w / 2, cy - h / 2 - 4), frame)
        else:
            font = QFont("Segoe UI Emoji")
            font.setPointSizeF(54)
            p.setFont(font)
            p.setPen(t.color("text"))
            p.drawText(QRectF(cx - 60, cy - 50, 120, 100), Qt.AlignmentFlag.AlignCenter, "🤖")

        # three pulsing dots ("thinking")
        for i in range(3):
            k = 0.5 + 0.5 * math.sin(self.phase * 2 * math.pi / 1.2 - i * 0.8)
            p.setBrush(t.color("accent", 0.35 + 0.55 * k))
            p.drawEllipse(QPointF(cx - 16 + i * 16, 218), 3.4 + 1.4 * k, 3.4 + 1.4 * k)
        p.end()


class StripeBar(_Animated):
    """Hazard-stripe 'under construction' bar; the stripes slowly slide to the right."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(14)
        self.setMinimumWidth(320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Under construction")

    def paintEvent(self, _event) -> None:
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        p.setClipPath(clip)
        p.fillRect(rect, t.color("track"))
        stripe = t.color("no_date", 0.85)
        offset = (self.phase * 22.0) % 28.0
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(stripe)
        x = rect.left() - 28 + offset
        while x < rect.right() + 28:
            path = QPainterPath()
            path.moveTo(x, rect.bottom())
            path.lineTo(x + 14, rect.bottom())
            path.lineTo(x + 14 + rect.height(), rect.top())
            path.lineTo(x + rect.height(), rect.top())
            path.closeSubpath()
            p.drawPath(path)
            x += 28
        p.setClipping(False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(t.color("border_strong"), 1))
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        p.end()


class AgentPage(WatermarkWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.addStretch(2)

        panel = card()
        panel.setMaximumWidth(520)
        panel.setMinimumWidth(420)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(36, 26, 36, 30)
        pl.setSpacing(10)

        self.hero = AgentHero()
        pl.addWidget(self.hero, 0, Qt.AlignmentFlag.AlignHCenter)
        soon = label("SOON", "pill")
        soon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pl.addWidget(soon, 0, Qt.AlignmentFlag.AlignHCenter)
        title = label("Agent 🤖", "h1")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pl.addWidget(title)
        sub = label("Under construction — coming soon.", "secondary")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pl.addWidget(sub)
        pl.addSpacing(8)
        self.stripes = StripeBar()
        pl.addWidget(self.stripes)
        hint = label("Nothing to configure yet. Check back in a future release.", "caption")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pl.addWidget(hint)

        row = QVBoxLayout()
        row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        row.addWidget(panel)
        outer.addLayout(row)
        outer.addStretch(3)
