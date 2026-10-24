"""Design tokens + a single token-driven stylesheet for the dark/light themes.

Neutrals, ink and the status colours follow the dataviz reference palette.
Custom-painted widgets read `current()` in paintEvent and repaint on `bus.changed`.
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from gui import icons

# Status colours are fixed in both themes (reserved; never reused as series colours).
_STATUS = {
    "updated":     "#0ca30c",   # good
    "not_updated": "#898781",   # neutral
    "no_date":     "#fab219",   # warning
    "error":       "#d03b3b",   # critical
}

DARK = {
    "bg": "#0d0d0d", "sidebar": "#121211", "surface": "#1a1a19", "surface2": "#222221",
    "hover": "#2a2a28", "border": "#2c2c2a", "border_strong": "#3d3d3a",
    "text": "#f0efec", "text_secondary": "#c3c2b7", "text_muted": "#a09f98",
    "text_disabled": "#6a6964",
    "accent": "#3987e5", "accent_hover": "#5598e7", "accent_text": "#06090f",
    "accent_soft": "rgba(57,135,229,0.20)", "accent_ink": "#86b6ef",
    "danger": "#e66767", "danger_soft": "rgba(230,103,103,0.16)",
    "track": "#2c2c2a", "overlay": "#0d0d0d",
    **_STATUS,
}

LIGHT = {
    "bg": "#f9f9f7", "sidebar": "#f0efeb", "surface": "#fcfcfb", "surface2": "#f3f3f0",
    "hover": "#eceae5", "border": "#e1e0d9", "border_strong": "#c3c2b7",
    "text": "#0b0b0b", "text_secondary": "#52514e", "text_muted": "#66655f",
    "text_disabled": "#a8a7a0",
    "accent": "#2673cc", "accent_hover": "#1f5fb0", "accent_text": "#ffffff",   # white on accent: 4.77:1
    "accent_soft": "rgba(38,115,204,0.14)", "accent_ink": "#1c5cab",
    "danger": "#c4302f", "danger_soft": "rgba(196,48,47,0.12)",
    "track": "#e1e0d9", "overlay": "#f9f9f7",
    **_STATUS,
}

FONT_FAMILY = '"Segoe UI Variable Text", "Segoe UI", sans-serif'
MONO_FAMILY = '"Cascadia Mono", Consolas, monospace'


class Theme:
    def __init__(self, name: str, tokens: dict[str, str]):
        self.name = name
        self._tokens = tokens

    def __getitem__(self, key: str) -> str:
        return self._tokens[key]

    def color(self, key: str, alpha: float | None = None) -> QColor:
        c = QColor(self._tokens[key])
        if alpha is not None:
            c.setAlphaF(alpha)
        return c

    @property
    def is_dark(self) -> bool:
        return self.name == "dark"


class _Bus(QObject):
    changed = Signal()


bus = _Bus()
_current = Theme("dark", DARK)
_mode = "system"          # system | dark | light


def current() -> Theme:
    return _current


def mode() -> str:
    return _mode


# --------------------------------------------------------------------------- #
# Stylesheet
# --------------------------------------------------------------------------- #

_QSS = """
QToolTip { background: @surface2; color: @text; border: 1px solid @border_strong; padding: 6px 8px; }

QMainWindow, QDialog { background: @bg; }
QLabel { background: transparent; color: @text; }
QLabel[role="muted"] { color: @text_muted; }
QLabel[role="secondary"] { color: @text_secondary; }
QLabel[role="h1"] { font-size: 21pt; font-weight: 600; }
QLabel[role="h2"] { font-size: 13pt; font-weight: 600; }
QLabel[role="h3"] { font-size: 11pt; font-weight: 600; }
QLabel[role="caption"] { color: @text_muted; font-size: 9pt; }
QLabel[role="error"] { color: @danger; font-size: 9pt; }
QLabel[role="hint"] { color: @text_muted; font-size: 9pt; }
QLabel[role="pill"] {
    background: @accent_soft; color: @text; border: 1px solid @border_strong; border-radius: 12px;
    padding: 3px 12px; font-size: 9.5pt;
}

QFrame[card="true"] { background: @surface; border: 1px solid @border; border-radius: 12px; }
QFrame[card="flat"] { background: @surface2; border: 1px solid @border; border-radius: 10px; }
QWidget#sidebar { background: @sidebar; border-right: 1px solid @border; }
QWidget#sidebar QLabel { background: transparent; }
QFrame[divider="true"] { background: @border; border: none; max-height: 1px; min-height: 1px; }

QPushButton {
    background: @surface2; color: @text; border: 1px solid @border_strong;
    border-radius: 8px; padding: 8px 16px; min-height: 18px;
}
QPushButton:hover { background: @hover; }
QPushButton:pressed { background: @border; }
QPushButton:focus { border: 1px solid @accent; }
QPushButton:disabled { color: @text_disabled; background: @surface; border-color: @border; }
QPushButton[variant="primary"] {
    background: @accent; color: @accent_text; border: 1px solid @accent; font-weight: 600;
}
QPushButton[variant="primary"]:hover { background: @accent_hover; border-color: @accent_hover; }
QPushButton[variant="primary"]:pressed { background: @accent; }
QPushButton[variant="primary"]:disabled { background: @surface2; color: @text_disabled; border-color: @border; }
QPushButton[variant="danger"] { background: @danger_soft; color: @text; border: 1px solid @danger; }
QPushButton[variant="danger"]:hover { background: @danger; color: #ffffff; }
QPushButton[variant="ghost"] { background: transparent; border: 1px solid transparent; }
QPushButton[variant="ghost"]:hover { background: @hover; }
QPushButton[variant="ghost"]:focus { border: 1px solid @accent; }
QPushButton[variant="link"] { background: transparent; border: none; color: @accent_ink; padding: 4px 6px; }
QPushButton[variant="link"]:hover { text-decoration: underline; }

QPushButton[nav="true"] {
    background: transparent; border: 1px solid transparent; border-radius: 10px;
    text-align: left; padding: 10px 14px; color: @text_secondary; font-size: 10.5pt;
}
QPushButton[nav="true"]:hover { background: @hover; color: @text; }
QPushButton[nav="true"]:checked { background: @accent_soft; color: @text; font-weight: 600; }
QPushButton[nav="true"]:focus { border: 1px solid @accent; }
QPushButton[nav="true"]:disabled { color: @text_disabled; background: transparent; border-color: transparent; }

QPushButton[chip="true"] {
    background: transparent; border: 1px solid @border_strong; border-radius: 15px;
    padding: 4px 12px 4px 8px; min-height: 20px; color: @text_secondary;
}
QPushButton[chip="true"]:hover { background: @hover; }
QPushButton[chip="true"]:checked { background: @accent_soft; border-color: @accent; color: @text; }
QPushButton[chip="true"]:focus { border: 1px solid @accent; }

QLineEdit, QDateEdit, QComboBox, QSpinBox {
    background: @surface2; color: @text; border: 1px solid @border_strong; border-radius: 8px;
    padding: 8px 10px; min-height: 18px; selection-background-color: @accent; selection-color: @accent_text;
}
QLineEdit:hover, QDateEdit:hover, QComboBox:hover { border-color: @text_muted; }
QLineEdit:focus, QDateEdit:focus, QComboBox:focus { border: 1px solid @accent; }
QLineEdit[invalid="true"] { border: 1px solid @danger; }
QLineEdit:disabled, QDateEdit:disabled, QComboBox:disabled { color: @text_disabled; background: @surface; }
QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 28px; }
QComboBox::down-arrow, QDateEdit::down-arrow { image: url("@chevron"); width: 14px; height: 14px; }
QComboBox QAbstractItemView {
    background: @surface; color: @text; border: 1px solid @border_strong; border-radius: 8px;
    selection-background-color: @accent_soft; selection-color: @text; outline: none; padding: 4px;
}

QCalendarWidget QWidget { background: @surface; color: @text; }
QCalendarWidget QToolButton { background: transparent; color: @text; border: none; padding: 6px 10px; border-radius: 6px; }
QCalendarWidget QToolButton:hover { background: @hover; }
QCalendarWidget QMenu { background: @surface; color: @text; }
QCalendarWidget QSpinBox { background: @surface2; }
QCalendarWidget #qt_calendar_navigationbar { background: @surface2; }
QCalendarWidget QAbstractItemView:enabled {
    background: @surface; color: @text; selection-background-color: @accent; selection-color: @accent_text; outline: none;
}
QCalendarWidget QAbstractItemView:disabled { color: @text_muted; }
/* The day grid is a QTableView internally. Keep it free of the data-table padding/borders,
   otherwise the ~36px cells have no room left for two-digit days. */
QCalendarWidget QTableView { background: @surface; color: @text; border: none; outline: none; gridline-color: transparent; }
QCalendarWidget QTableView::item { padding: 0px; margin: 0px; border: none; }
QCalendarWidget QTableView::item:hover { background: @hover; }
QCalendarWidget QTableView::item:selected { background: @accent; color: @accent_text; }
QCalendarWidget QHeaderView { background: @surface; }
QCalendarWidget QHeaderView::section {
    background: @surface; color: @text_muted; border: none; padding: 4px 0px; font-weight: 600; font-size: 9pt;
}

QCheckBox { spacing: 10px; background: transparent; color: @text; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid @border_strong; border-radius: 5px; background: @surface2; }
QCheckBox::indicator:hover { border-color: @accent; }
QCheckBox::indicator:checked { background: @accent; border-color: @accent; image: url("@check"); }
QCheckBox:focus { color: @text; }

/* Data tables only (property set in ResultsView / HistoryPage). Never style bare QTableView:
   QCalendarWidget's day grid is one and would inherit the padding. */
QTableView[dataTable="true"] {
    background: @surface; alternate-background-color: @surface; color: @text; border: none;
    gridline-color: transparent; selection-background-color: @accent_soft; selection-color: @text; outline: none;
}
QTableView[dataTable="true"]::item { padding: 0 12px; border-bottom: 1px solid @border; }
QTableView[dataTable="true"]::item:hover { background: @hover; }
QTableView[dataTable="true"]::item:selected { background: @accent_soft; }
QTableView[dataTable="true"] QHeaderView { background: @surface; }
QTableView[dataTable="true"] QHeaderView::section {
    background: @surface; color: @text_muted; border: none; border-bottom: 1px solid @border_strong;
    padding: 10px 12px; font-weight: 600; font-size: 9pt;
}
QTableView[dataTable="true"] QHeaderView::section:hover { color: @text; }
QTableView[dataTable="true"] QTableCornerButton::section { background: @surface; border: none; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: @border_strong; border-radius: 4px; min-height: 32px; margin: 0 2px; }
QScrollBar::handle:vertical:hover { background: @text_muted; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: @border_strong; border-radius: 4px; min-width: 32px; margin: 2px 0; }
QScrollBar::handle:horizontal:hover { background: @text_muted; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QProgressBar { background: @track; border: none; border-radius: 5px; min-height: 10px; max-height: 10px; text-align: center; }
QProgressBar::chunk { background: @accent; border-radius: 5px; }

QPlainTextEdit {
    background: @surface2; color: @text_secondary; border: 1px solid @border; border-radius: 8px;
    padding: 8px; font-family: @mono; font-size: 9pt; selection-background-color: @accent; selection-color: @accent_text;
}
QTextEdit {
    background: transparent; color: @text; border: none; padding: 4px 2px;
    selection-background-color: @accent; selection-color: @accent_text; font-size: 10.5pt;
}
QListWidget[noteList="true"] { background: transparent; border: none; outline: none; }
QListWidget[noteList="true"]::item { border-radius: 8px; margin: 2px 0; }
QListWidget[noteList="true"]::item:hover { background: @hover; }
QListWidget[noteList="true"]::item:selected { background: @accent_soft; }
QPushButton[tool="true"] {
    background: transparent; border: 1px solid @border_strong; border-radius: 8px; padding: 0; min-height: 0;
    color: @text; font-size: 11pt;
}
QPushButton[tool="true"]:hover { background: @hover; }
QPushButton[tool="true"]:checked { background: @accent_soft; border-color: @accent; }
QPushButton[tool="true"]::menu-indicator { image: none; width: 0; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }

QMenu { background: @surface; color: @text; border: 1px solid @border_strong; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 8px 28px 8px 12px; border-radius: 6px; }
QMenu::item:selected { background: @hover; }
QMenu::item:disabled { color: @text_disabled; }
QMenu::separator { height: 1px; background: @border; margin: 6px 4px; }
QMessageBox, QFileDialog { background: @bg; }
"""


def build_qss(theme: Theme, assets: dict[str, str]) -> str:
    tokens = {**{k: theme[k] for k in (DARK if theme.is_dark else LIGHT)}, **assets, "mono": MONO_FAMILY}
    return re.sub(r"@(\w+)", lambda m: tokens[m.group(1)], _QSS)


def _write_assets(theme: Theme) -> dict[str, str]:
    """Render the small PNGs (dropdown chevron, checkmark) the stylesheet needs."""
    from core.paths import data_dir

    folder = data_dir() / "ui_cache" / theme.name
    folder.mkdir(parents=True, exist_ok=True)
    chevron = folder / "chevron.png"
    check = folder / "check.png"
    icons.pixmap("chevron", theme["text_secondary"], 14, 2.0, 2.2).save(str(chevron), "PNG")
    icons.pixmap("check", theme["accent_text"], 14, 2.0, 2.6).save(str(check), "PNG")
    return {"chevron": Path(chevron).as_posix(), "check": Path(check).as_posix()}


def _palette(theme: Theme) -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, theme.color("bg"))
    p.setColor(QPalette.ColorRole.WindowText, theme.color("text"))
    p.setColor(QPalette.ColorRole.Base, theme.color("surface"))
    p.setColor(QPalette.ColorRole.AlternateBase, theme.color("surface2"))
    p.setColor(QPalette.ColorRole.Text, theme.color("text"))
    p.setColor(QPalette.ColorRole.Button, theme.color("surface2"))
    p.setColor(QPalette.ColorRole.ButtonText, theme.color("text"))
    p.setColor(QPalette.ColorRole.ToolTipBase, theme.color("surface2"))
    p.setColor(QPalette.ColorRole.ToolTipText, theme.color("text"))
    p.setColor(QPalette.ColorRole.Highlight, theme.color("accent"))
    p.setColor(QPalette.ColorRole.HighlightedText, theme.color("accent_text"))
    p.setColor(QPalette.ColorRole.PlaceholderText, theme.color("text_muted"))
    p.setColor(QPalette.ColorRole.Link, theme.color("accent_ink"))
    return p


def _resolve(requested: str) -> str:
    if requested in ("dark", "light"):
        return requested
    scheme = QGuiApplication.styleHints().colorScheme()
    return "light" if scheme == Qt.ColorScheme.Light else "dark"


def apply(app: QApplication, requested: str = "system") -> None:
    """Apply 'system' | 'dark' | 'light' to the whole app and notify custom widgets."""
    global _current, _mode
    _mode = requested if requested in ("system", "dark", "light") else "system"

    hints = QGuiApplication.styleHints()
    if hasattr(hints, "setColorScheme"):   # Qt >= 6.8: also drives the native title bar
        hints.setColorScheme({
            "dark": Qt.ColorScheme.Dark,
            "light": Qt.ColorScheme.Light,
        }.get(_mode, Qt.ColorScheme.Unknown))

    name = _resolve(_mode)
    _current = Theme(name, DARK if name == "dark" else LIGHT)
    icons.clear_cache()
    app.setPalette(_palette(_current))
    app.setStyleSheet(build_qss(_current, _write_assets(_current)))
    bus.changed.emit()


def follow_system(app: QApplication) -> None:
    """Re-apply when the OS scheme flips while the mode is 'system'."""
    def _on_change(*_):
        if _mode == "system":
            apply(app, "system")
    QGuiApplication.styleHints().colorSchemeChanged.connect(_on_change)


# --------------------------------------------------------------------------- #
# Category presentation (shared by chips, charts, badges, KPI cards)
# --------------------------------------------------------------------------- #

CATEGORY_ORDER = ("updated", "not_updated", "no_date", "download_error")
CATEGORY_LABEL = {
    "updated": "Updated",
    "not_updated": "Not updated",
    "no_date": "No date found",
    "download_error": "Download error",
}
CATEGORY_ICON = {
    "updated": "check",
    "not_updated": "pause",
    "no_date": "question",
    "download_error": "x",
}
_CATEGORY_TOKEN = {
    "updated": "updated",
    "not_updated": "not_updated",
    "no_date": "no_date",
    "download_error": "error",
}


def category_color(category: str) -> QColor:
    return _current.color(_CATEGORY_TOKEN.get(category, "not_updated"))


def category_hex(category: str) -> str:
    return _current[_CATEGORY_TOKEN.get(category, "not_updated")]
