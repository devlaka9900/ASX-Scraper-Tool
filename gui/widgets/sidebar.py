"""Left navigation rail: logo, four pages, theme toggle, version."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.version import APP_NAME, APP_VERSION
from gui import icons, theme
from gui.widgets.common import divider, label

NAV = (
    ("new_run",      "New run",      "plus",     "Alt+1"),
    ("results",      "Results",      "chart",    "Alt+2"),
    ("history",      "History",      "history",  "Alt+3"),
    ("date_checker", "Date checker", "calendar", "Alt+4"),
)


class Sidebar(QWidget):
    navigate = Signal(str)
    themeToggled = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(224)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 18, 14, 14)
        lay.setSpacing(6)

        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 0)
        brand.setSpacing(10)
        self._logo = QLabel()
        self._logo.setFixedSize(28, 28)
        brand.addWidget(self._logo)
        title = label(APP_NAME, "h3")
        title.setWordWrap(True)
        brand.addWidget(title, 1)
        lay.addLayout(brand)
        lay.addSpacing(18)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for key, text, icon_name, shortcut in NAV:
            btn = QPushButton(f"  {text}")
            btn.setProperty("nav", True)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setShortcut(shortcut)
            btn.setToolTip(f"{text} ({shortcut})")
            btn.setAccessibleName(text)
            btn.setIconSize(QSize(18, 18))
            btn.clicked.connect(lambda _=False, k=key: self.navigate.emit(k))
            self._group.addButton(btn)
            self._buttons[key] = btn
            lay.addWidget(btn)
        self._icon_names = {key: icon_name for key, _t, icon_name, _s in NAV}

        lay.addStretch(1)
        lay.addWidget(divider())
        lay.addSpacing(6)

        self._theme_btn = QPushButton()
        self._theme_btn.setProperty("nav", True)
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.setIconSize(QSize(18, 18))
        self._theme_btn.clicked.connect(self.themeToggled)
        lay.addWidget(self._theme_btn)

        lay.addWidget(label(f"v{APP_VERSION}", "caption"), 0, Qt.AlignmentFlag.AlignHCenter)

        theme.bus.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        t = theme.current()
        for key, btn in self._buttons.items():
            btn.setIcon(icons.icon(self._icon_names[key], t["text_secondary"], 18, on_color=t["accent_ink"]))
        self._logo.setPixmap(icons.pixmap("logo", t["accent"], 28, self.devicePixelRatioF(), 1.7))
        dark = t.is_dark
        self._theme_btn.setIcon(icons.icon("sun" if dark else "moon", t["text_secondary"], 18))
        self._theme_btn.setText("  Light theme" if dark else "  Dark theme")
        self._theme_btn.setToolTip("Switch theme")
        self._theme_btn.setAccessibleName("Switch theme")

    def select(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn is not None:
            btn.setChecked(True)

    def set_enabled(self, key: str, enabled: bool) -> None:
        btn = self._buttons.get(key)
        if btn is not None:
            btn.setEnabled(enabled)
