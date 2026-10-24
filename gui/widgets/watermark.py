"""Barely-visible tiled watermark painted behind a page's content.

At normal viewing it reads as a plain background; it only shows up when you look
closely (or raise the screen contrast). Used as the base class of a few empty
states / the run page — never on forms or tables, so readability is unaffected.

Painting thousands of rotated text tiles is expensive (tens of ms on large windows),
so the pattern is rendered once into a transparent pixmap and blitted on every
repaint; it is only re-rendered when the size, theme or screen scale changes.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QFontMetricsF, QImage, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

from core._sig import signature
from gui import theme

ANGLE_DEG = -24.0
ALPHA_DARK = 0.028       # share of the ink colour blended over the background
ALPHA_LIGHT = 0.036
TILE_GAP_X = 70.0
TILE_GAP_Y = 64.0


def paint_watermark(p: QPainter, rect: QRectF) -> None:
    """Tile the signature diagonally over *rect* (only the part that is visible)."""
    t = theme.current()
    font = QFont(p.font())
    font.setPointSizeF(9)
    font.setWeight(QFont.Weight.Normal)
    fm = QFontMetricsF(font)
    text = signature()
    w, h = fm.horizontalAdvance(text), fm.height()

    # rotate about the centre; find the extent of `rect` in the rotated frame so the loops
    # cover only what is visible (the old square covered ~4x the area)
    to_screen = QTransform()
    to_screen.translate(rect.center().x(), rect.center().y())
    to_screen.rotate(ANGLE_DEG)
    inverse, ok = to_screen.inverted()
    corners = [inverse.map(QPointF(x, y)) for x in (rect.left(), rect.right()) for y in (rect.top(), rect.bottom())]
    min_x, max_x = min(c.x() for c in corners), max(c.x() for c in corners)
    min_y, max_y = min(c.y() for c in corners), max(c.y() for c in corners)

    p.save()
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setFont(font)
    p.setPen(t.color("text", ALPHA_DARK if t.is_dark else ALPHA_LIGHT))
    p.setTransform(to_screen, True)
    step_x, step_y = w + TILE_GAP_X, h + TILE_GAP_Y
    row = int((min_y - h) // step_y)
    y = row * step_y
    while y < max_y:
        x = (row % 2) * (step_x / 2.0)                       # brick offset so tiles don't line up
        x += ((min_x - w - x) // step_x) * step_x            # start at the first tile that can be visible
        while x < max_x:
            p.drawText(QRectF(x, y, w, h), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            x += step_x
        y += step_y
        row += 1
    p.restore()


class WatermarkWidget(QWidget):
    """A plain QWidget that paints the watermark first, then its children. It does not
    fill a background: the window / the card behind it supplies the colour."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._cache: QPixmap | None = None
        self._cache_key: tuple | None = None
        theme.bus.changed.connect(self.update)

    def _watermark_pixmap(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), round(dpr, 2), theme.current().name)
        if self._cache is None or key != self._cache_key:
            image = QImage(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)),
                           QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            image.setDevicePixelRatio(dpr)
            painter = QPainter(image)
            painter.setFont(self.font())
            paint_watermark(painter, QRectF(0, 0, self.width(), self.height()))
            painter.end()
            self._cache = QPixmap.fromImage(image)
            self._cache_key = key
        return self._cache

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.drawPixmap(0, 0, self._watermark_pixmap())
        p.end()
        super().paintEvent(event)
