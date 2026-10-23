"""Tiny widget factories shared by the pages."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QWidget

from gui import icons, theme


def repolish(widget: QWidget) -> None:
    """Re-evaluate QSS after changing a dynamic property."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    return lbl


class ElidedLabel(QLabel):
    """Single-line label that elides in the middle instead of forcing the layout wider."""

    def __init__(self, text: str = "", role: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        if role:
            self.setProperty("role", role)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text if text else "")
        self._elide()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def minimumSizeHint(self) -> QSize:
        return QSize(40, super().minimumSizeHint().height())

    def _elide(self) -> None:
        shown = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle, max(10, self.width()))
        super().setText(shown)


def card(kind: str = "true") -> QFrame:
    frame = QFrame()
    frame.setProperty("card", kind)
    return frame


def divider() -> QFrame:
    line = QFrame()
    line.setProperty("divider", True)
    line.setFrameShape(QFrame.Shape.NoFrame)
    return line


class IconButton(QPushButton):
    """QPushButton whose icon is re-coloured whenever the theme changes."""

    def __init__(self, text: str = "", icon_name: str | None = None, variant: str | None = None,
                 size: int = 18, icon_role: str = "text_secondary", parent: QWidget | None = None):
        super().__init__(text, parent)
        self._icon_name = icon_name
        self._icon_role = icon_role
        self._size = size
        if variant:
            self.setProperty("variant", variant)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        theme.bus.changed.connect(self._refresh_icon)
        self._refresh_icon()

    def set_icon(self, name: str | None) -> None:
        self._icon_name = name
        if name is None:
            self.setIcon(QIcon())
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        if not self._icon_name:
            return   # caller manages its own QIcon (e.g. filter chips)
        t = theme.current()
        role = self._icon_role
        if self.property("variant") == "primary":
            role = "accent_text"
        self.setIcon(icons.icon(self._icon_name, t[role], self._size, on_color=t["accent_ink"]))
        self.setIconSize(QSize(self._size, self._size))


def primary(text: str, icon_name: str | None = None) -> IconButton:
    return IconButton(text, icon_name, variant="primary")


def secondary(text: str, icon_name: str | None = None) -> IconButton:
    return IconButton(text, icon_name)


def ghost(text: str, icon_name: str | None = None) -> IconButton:
    return IconButton(text, icon_name, variant="ghost")
