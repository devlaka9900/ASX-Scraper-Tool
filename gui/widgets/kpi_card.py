"""Stat tile: label (sentence case) + proportional-figure value that counts up."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QSizePolicy, QWidget

from gui import anim, icons, theme


class KpiCard(QFrame):
    clicked = Signal()

    def __init__(self, title: str, category: str | None = None, icon_name: str | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("card", "true")
        self._title = title
        self._category = category            # status category -> coloured marker
        self._icon_name = icon_name
        self._value = 0.0
        self._target = 0
        self._sub = ""
        self._active = False
        self._hover = False
        self._anim = None
        self.setMinimumSize(150, 92)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(96)
        self.setAccessibleName(title)
        self.setMouseTracking(True)
        if category:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        theme.bus.changed.connect(self.update)

    def set_value(self, value: int, sub: str = "", animate: bool = True) -> None:
        self._target = int(value)
        self._sub = sub
        self.setAccessibleDescription(f"{self._target:,} {sub}".strip())
        if animate:
            self._anim = anim.tween(self, self._value, self._target, 650, self._set_value)
        else:
            self._value = float(self._target)
            self.update()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def _set_value(self, v: float) -> None:
        self._value = v
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(170, 96)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)       # card border/background from QSS
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        if self._active or self._hover or self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(t.color("accent") if (self._active or self.hasFocus()) else t.color("border_strong"), 1.6))
            p.drawRoundedRect(r, 12, 12)

        pad = 16
        # marker: status glyph in its colour + label in ink
        x = pad
        if self._category:
            sw = QRectF(x, 15, 16, 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.category_color(self._category))
            p.drawRoundedRect(sw, 5, 5)
            glyph = icons.pixmap(theme.CATEGORY_ICON[self._category],
                                 "#0b0b0b" if self._category in ("updated", "no_date") else "#ffffff",
                                 11, self.devicePixelRatioF(), 2.8)
            p.drawPixmap(int(sw.left() + 2.5), int(sw.top() + 2.5), glyph)
            x += 24
        elif self._icon_name:
            p.drawPixmap(int(x), 14, icons.pixmap(self._icon_name, t["text_muted"], 18, self.devicePixelRatioF()))
            x += 26

        label_font = QFont(self.font())
        label_font.setPointSizeF(9.5)
        p.setFont(label_font)
        p.setPen(t.color("text_secondary"))
        p.drawText(QRectF(x, 8, self.width() - x - pad, 30),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._title)

        value_font = QFont(self.font())
        value_font.setPointSizeF(24)
        value_font.setWeight(QFont.Weight.DemiBold)
        p.setFont(value_font)
        p.setPen(t.color("text"))
        p.drawText(QRectF(pad, 38, self.width() - 2 * pad, 38),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"{int(round(self._value)):,}")
        if self._sub:
            sub_font = QFont(self.font())
            sub_font.setPointSizeF(9)
            p.setFont(sub_font)
            p.setPen(t.color("text_muted"))
            p.drawText(QRectF(pad, 70, self.width() - 2 * pad, 20),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._sub)
        p.end()

    def enterEvent(self, event) -> None:
        self._hover = bool(self._category)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if self._category and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def keyPressEvent(self, event) -> None:
        if self._category and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.update()
