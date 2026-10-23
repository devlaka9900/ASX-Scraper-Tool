"""Per-section stacked horizontal bars (Updated / Not updated / No date / Error).

Mark specs: bars <= 24px thick, 4px rounded data-end with a square baseline edge,
2px surface gap between touching segments, total at the bar tip, hairline guides.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from gui import anim, theme

BAR_H = 20.0
ROW_H = 38.0
GAP_PX = 2.0
RADIUS = 4.0
LEGEND_H = 30.0


class StackedBars(QWidget):
    segmentClicked = Signal(str, str)      # section label, category key
    segmentHovered = Signal(str, str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._rows: list[tuple[str, dict[str, int]]] = []   # (section label, {category: n})
        self._progress = 1.0
        self._active: set[str] = set()
        self._section_filter: str | None = None
        self._hit: list[tuple[QRectF, str, str, int]] = []   # rect, section, category, count
        self._hover: tuple[str, str] | None = None
        self._anim = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAccessibleName("Books per section chart")
        theme.bus.changed.connect(self.update)

    def set_data(self, rows: list[tuple[str, dict[str, int]]], animate: bool = True) -> None:
        self._rows = rows
        self._hover = None
        self.setMinimumHeight(int(LEGEND_H + max(1, len(rows)) * ROW_H + 8))
        self.updateGeometry()
        self.setAccessibleDescription("; ".join(
            f"{label}: " + ", ".join(f"{theme.CATEGORY_LABEL[c]} {counts.get(c, 0)}" for c in theme.CATEGORY_ORDER)
            for label, counts in rows))
        if animate:
            self._progress = 0.0
            self._anim = anim.tween(self, 0, 1, 700, self._set_progress)
        else:
            self._progress = 1.0
        self.update()

    def set_filter(self, categories: set[str], section: str | None) -> None:
        self._active = set(categories)
        self._section_filter = section
        self.update()

    def _set_progress(self, v: float) -> None:
        self._progress = v
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(520, int(LEGEND_H + max(1, len(self._rows)) * ROW_H + 8))

    def paintEvent(self, _event) -> None:
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._hit = []

        label_font = QFont(self.font())
        label_font.setPointSizeF(10)
        value_font = QFont(label_font)
        value_font.setWeight(QFont.Weight.DemiBold)
        fm = QFontMetricsF(label_font)

        self._paint_legend(p, t, label_font)

        if not self._rows:
            p.setPen(t.color("text_muted"))
            p.setFont(label_font)
            p.drawText(QRectF(0, LEGEND_H, self.width(), 60), Qt.AlignmentFlag.AlignCenter, "No data")
            p.end()
            return

        label_w = min(190.0, max(fm.horizontalAdvance(lbl) for lbl, _ in self._rows) + 12)
        value_w = 56.0
        x0 = label_w + 8
        avail = max(40.0, self.width() - x0 - value_w - 8)
        max_total = max(1, max(sum(c.values()) for _l, c in self._rows))
        n = len(self._rows)
        stagger = 0.08

        # one hairline baseline (single axis)
        p.setPen(QPen(t.color("border_strong"), 1))
        p.drawLine(QPointF(x0, LEGEND_H), QPointF(x0, LEGEND_H + n * ROW_H))

        for i, (label, counts) in enumerate(self._rows):
            top = LEGEND_H + i * ROW_H
            y = top + (ROW_H - BAR_H) / 2.0
            dim_row = self._section_filter is not None and self._section_filter != label
            row_t = max(0.0, min(1.0, self._progress * (1 + stagger * (n - 1)) - i * stagger))

            p.setFont(label_font)
            p.setPen(t.color("text_secondary" if dim_row else "text"))
            p.drawText(QRectF(0, top, label_w, ROW_H), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       fm.elidedText(label, Qt.TextElideMode.ElideRight, label_w))

            total = sum(counts.get(c, 0) for c in theme.CATEGORY_ORDER)
            segs = [(c, counts.get(c, 0)) for c in theme.CATEGORY_ORDER if counts.get(c, 0) > 0]
            bar_w = avail * total / max_total * row_t
            n_gaps = max(0, len(segs) - 1)
            usable = max(0.0, bar_w - GAP_PX * n_gaps)
            x = x0
            for si, (cat, cnt) in enumerate(segs):
                w = max(3.0, usable * cnt / total) if total else 0.0
                rect = QRectF(x, y, w, BAR_H)
                color = theme.category_color(cat)
                focused = (not self._active or cat in self._active) and not dim_row
                hovered = self._hover == (label, cat)
                if not focused and not hovered:
                    color.setAlphaF(0.30)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color)
                p.drawPath(self._seg_path(rect, last=(si == len(segs) - 1)))
                if row_t >= 1.0:
                    self._hit.append((rect, label, cat, cnt))
                x += w + GAP_PX

            # total at the bar tip (ink token, never the series colour)
            p.setFont(value_font)
            p.setPen(t.color("text_secondary" if dim_row else "text"))
            p.drawText(QRectF(x0 + bar_w + 8, top, value_w, ROW_H),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       f"{int(round(total * row_t)):,}")
        p.end()

    @staticmethod
    def _seg_path(rect: QRectF, last: bool) -> QPainterPath:
        """Square on the baseline side; 4px rounded only at the bar's data-end."""
        path = QPainterPath()
        if not last or rect.width() < RADIUS * 2:
            path.addRect(rect)
            return path
        r = RADIUS
        path.moveTo(rect.left(), rect.top())
        path.lineTo(rect.right() - r, rect.top())
        path.arcTo(QRectF(rect.right() - 2 * r, rect.top(), 2 * r, 2 * r), 90, -90)
        path.lineTo(rect.right(), rect.bottom() - r)
        path.arcTo(QRectF(rect.right() - 2 * r, rect.bottom() - 2 * r, 2 * r, 2 * r), 0, -90)
        path.lineTo(rect.left(), rect.bottom())
        path.closeSubpath()
        return path

    def _paint_legend(self, p: QPainter, t, font: QFont) -> None:
        p.setFont(font)
        fm = QFontMetricsF(font)
        x = 8.0
        for cat in theme.CATEGORY_ORDER:
            label = theme.CATEGORY_LABEL[cat]
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.category_color(cat))
            p.drawRoundedRect(QRectF(x, 8, 12, 12), 3, 3)
            p.setPen(t.color("text_secondary"))
            w = fm.horizontalAdvance(label)
            p.drawText(QRectF(x + 18, 2, w + 4, 24), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
            x += 18 + w + 22

    # ---- interaction ------------------------------------------------------ #

    def _segment_at(self, pos: QPointF):
        for rect, section, cat, count in self._hit:
            if rect.adjusted(0, -4, 0, 4).contains(pos):
                return rect, section, cat, count
        return None

    def mouseMoveEvent(self, event) -> None:
        hit = self._segment_at(event.position())
        new = (hit[1], hit[2]) if hit else None
        if new != self._hover:
            self._hover = new
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor)
            self.segmentHovered.emit(*(new or ("", "")))
            self.update()
        if hit:
            _rect, section, cat, count = hit
            QToolTip.showText(event.globalPosition().toPoint(),
                              f"{section} · {theme.CATEGORY_LABEL[cat]}: {count:,}", self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, _event) -> None:
        if self._hover is not None:
            self._hover = None
            self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._segment_at(event.position())
            if hit:
                self.segmentClicked.emit(hit[1], hit[2])
