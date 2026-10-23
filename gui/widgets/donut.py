"""Category donut with an always-visible legend (counts + share).

Custom QPainter widget (QtCharts lives in PySide6-Addons, which we avoid).
Marks follow the dataviz specs: 2px surface gap between slices, legend always
present, value text in ink tokens (never the series colour), hover tooltip.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from gui import anim, icons, theme

GAP_PX = 2.0


class DonutChart(QWidget):
    sliceClicked = Signal(str)       # category key
    sliceHovered = Signal(str)       # "" when none

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._items: list[tuple[str, str, int]] = []   # (key, label, count)
        self._progress = 1.0
        self._hover: str | None = None
        self._active: set[str] = set()                  # categories currently filtered on
        self._focus_index = -1
        self._ring_rect = QRectF()
        self._legend_rects: list[tuple[str, QRectF]] = []
        self._anim = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(420, 210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAccessibleName("Category chart")
        theme.bus.changed.connect(self.update)

    # ---- data ------------------------------------------------------------ #

    def set_data(self, items: list[tuple[str, str, int]], animate: bool = True) -> None:
        self._items = items
        self._focus_index = -1
        self._hover = None
        if animate:
            self._progress = 0.0
            self._anim = anim.tween(self, 0, 1, 750, self._set_progress,
                                    easing=anim.QEasingCurve.Type.OutCubic)
        else:
            self._progress = 1.0
        summary = ", ".join(f"{label} {count}" for _k, label, count in items)
        self.setAccessibleDescription(summary)
        self.update()

    def set_active(self, categories: set[str]) -> None:
        self._active = set(categories)
        self.update()

    def _set_progress(self, v: float) -> None:
        self._progress = v
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(520, 230)

    @property
    def _total(self) -> int:
        return sum(c for _k, _l, c in self._items)

    # ---- painting -------------------------------------------------------- #

    def _layout(self) -> None:
        w, h = self.width(), self.height()
        side = max(80.0, min(h - 24.0, w * 0.46))
        self._ring_rect = QRectF(12.0, (h - side) / 2.0, side, side)

    def _slice_spans(self) -> list[tuple[str, float, float]]:
        """(key, start_deg, sweep_deg) clockwise from 12 o'clock, gaps removed."""
        total = self._total
        spans: list[tuple[str, float, float]] = []
        if total <= 0:
            return spans
        nonzero = [(k, c) for k, _l, c in self._items if c > 0]
        r_mid = self._ring_rect.width() * 0.5 * 0.86
        gap_deg = 0.0 if len(nonzero) < 2 else math.degrees(GAP_PX / max(r_mid, 1.0))
        pos = 0.0
        for key, count in nonzero:
            sweep_full = 360.0 * count / total
            sweep = max(0.0, sweep_full - gap_deg)
            # the whole ring sweeps in clockwise as progress goes 0 -> 1
            spans.append((key, (pos + gap_deg / 2.0) * self._progress, sweep * self._progress))
            pos += sweep_full
        return spans

    def paintEvent(self, _event) -> None:
        t = theme.current()
        self._layout()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = self._ring_rect
        thick = ring.width() * 0.17
        r_outer = ring.width() / 2.0
        arc_rect = ring.adjusted(thick / 2 + 4, thick / 2 + 4, -thick / 2 - 4, -thick / 2 - 4)

        # track
        pen = QPen(t.color("track"), thick, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(arc_rect, 0, 360 * 16)

        dim_others = bool(self._active) or self._hover is not None
        for key, start, sweep in self._slice_spans():
            color = theme.category_color(key)
            focused = key == self._hover or key in self._active
            if dim_others and not focused:
                color.setAlphaF(0.35)
            width = thick + (5 if key == self._hover else 0)
            p.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawArc(arc_rect, int((90.0 - start) * 16), int(-sweep * 16))

        # centre text
        total = self._total
        big = QFont(self.font())
        big.setPointSizeF(22)
        big.setWeight(QFont.Weight.DemiBold)
        small = QFont(self.font())
        small.setPointSizeF(9)
        c = ring.center()
        p.setPen(t.color("text"))
        p.setFont(big)
        shown = int(round(total * self._progress))
        p.drawText(QRectF(c.x() - 60, c.y() - 28, 120, 34), Qt.AlignmentFlag.AlignCenter, f"{shown:,}")
        p.setPen(t.color("text_muted"))
        p.setFont(small)
        p.drawText(QRectF(c.x() - 60, c.y() + 6, 120, 20), Qt.AlignmentFlag.AlignCenter,
                   "PDFs" if total else "No data")

        self._paint_legend(p, t, total)
        p.end()

    def _paint_legend(self, p: QPainter, t, total: int) -> None:
        x0 = self._ring_rect.right() + 28
        row_h = 38.0
        n = len(self._items)
        y0 = (self.height() - n * row_h) / 2.0
        width = max(160.0, self.width() - x0 - 12)
        self._legend_rects = []
        name_font = QFont(self.font())
        name_font.setPointSizeF(10)
        val_font = QFont(self.font())
        val_font.setPointSizeF(10)
        val_font.setWeight(QFont.Weight.DemiBold)
        for i, (key, label, count) in enumerate(self._items):
            rect = QRectF(x0, y0 + i * row_h, width, row_h - 4)
            self._legend_rects.append((key, rect))
            focused = key == self._hover or key in self._active or i == self._focus_index
            if focused:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(t.color("hover") if key != self._hover else t.color("surface2"))
                p.drawRoundedRect(rect, 8, 8)
            # swatch with status glyph (colour is never the only cue)
            sw = QRectF(rect.left() + 10, rect.center().y() - 9, 18, 18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.category_color(key))
            p.drawRoundedRect(sw, 5, 5)
            glyph = icons.pixmap(theme.CATEGORY_ICON[key], "#0b0b0b" if key in ("updated", "no_date") else "#ffffff",
                                 12, self.devicePixelRatioF(), 2.6)
            p.drawPixmap(QPointF(sw.left() + 3, sw.top() + 3), glyph)
            # label + value in ink tokens
            p.setFont(name_font)
            p.setPen(t.color("text"))
            p.drawText(QRectF(sw.right() + 10, rect.top(), width - 120, rect.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
            pct = f"{100 * count / total:.0f}%" if total else "–"
            p.setFont(val_font)
            p.drawText(QRectF(rect.right() - 110, rect.top(), 58, rect.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, f"{count:,}")
            p.setFont(name_font)
            p.setPen(t.color("text_muted"))
            p.drawText(QRectF(rect.right() - 48, rect.top(), 40, rect.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, pct)
            if i == self._focus_index and self.hasFocus():
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(t.color("accent"), 2))
                p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)

    # ---- interaction ------------------------------------------------------ #

    def _key_at(self, pos: QPointF) -> str | None:
        for key, rect in self._legend_rects:
            if rect.contains(pos):
                return key
        ring = self._ring_rect
        c = ring.center()
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        dist = math.hypot(dx, dy)
        r_out = ring.width() / 2.0
        thick = ring.width() * 0.17
        if self._total > 0 and r_out - thick - 10 <= dist <= r_out + 2:
            ang = (math.degrees(math.atan2(dx, -dy)) + 360.0) % 360.0   # clockwise from 12 o'clock
            pos_deg = 0.0
            for key, _l, count in self._items:
                if count <= 0:
                    continue
                span = 360.0 * count / self._total
                if pos_deg <= ang < pos_deg + span:
                    return key
                pos_deg += span
        return None

    def mouseMoveEvent(self, event) -> None:
        key = self._key_at(event.position())
        if key != self._hover:
            self._hover = key
            self.setCursor(Qt.CursorShape.PointingHandCursor if key else Qt.CursorShape.ArrowCursor)
            self.sliceHovered.emit(key or "")
            self.update()
        if key:
            for k, label, count in self._items:
                if k == key:
                    pct = 100 * count / self._total if self._total else 0
                    QToolTip.showText(event.globalPosition().toPoint(),
                                      f"{label}: {count:,} ({pct:.0f}%)", self)
                    break
        else:
            QToolTip.hideText()

    def leaveEvent(self, _event) -> None:
        if self._hover is not None:
            self._hover = None
            self.sliceHovered.emit("")
            self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            key = self._key_at(event.position())
            if key:
                self.sliceClicked.emit(key)

    def keyPressEvent(self, event) -> None:
        n = len(self._items)
        if n and event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self._focus_index = (self._focus_index + 1) % n
            self.update()
        elif n and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._focus_index = (self._focus_index - 1) % n
            self.update()
        elif n and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self._focus_index >= 0:
            self.sliceClicked.emit(self._items[self._focus_index][0])
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        if self._focus_index < 0 and self._items:
            self._focus_index = 0
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.update()
