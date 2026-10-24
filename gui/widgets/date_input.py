"""Typed YYYY-MM-DD date field with a calendar popup — the app's single date entry.

The field starts blank on purpose: the user must enter the cutoff date. Typing
auto-inserts the dashes; the calendar is an optional helper. Parsing is strict
(`%Y-%m-%d`, same rule as the CLI), so impossible dates such as 2024-02-30 are rejected.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from PySide6.QtCore import QDate, QPoint, Qt, Signal
from PySide6.QtGui import QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget,
)

from gui import theme
from gui.widgets.common import IconButton, repolish

_DAYS = (
    Qt.DayOfWeek.Monday, Qt.DayOfWeek.Tuesday, Qt.DayOfWeek.Wednesday, Qt.DayOfWeek.Thursday,
    Qt.DayOfWeek.Friday, Qt.DayOfWeek.Saturday, Qt.DayOfWeek.Sunday,
)


def format_digits(raw: str) -> str:
    """'20240501' / '2024/05/01' / '2024-05' -> '2024-05-01' / '2024-05-01' / '2024-05'."""
    digits = re.sub(r"\D", "", raw)[:8]
    out = digits[:4]
    if len(digits) > 4:
        out += "-" + digits[4:6]
    if len(digits) > 6:
        out += "-" + digits[6:8]
    return out


_FULL_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_date(text: str) -> datetime | None:
    """Strict YYYY-MM-DD. strptime alone accepts '2024-12-3' (-> Dec 3), which would
    silently turn a half-typed date into a valid-looking cutoff, so require full width."""
    value = text.strip()
    if not _FULL_DATE.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def style_calendar(cal: QCalendarWidget) -> None:
    """Readable calendar in both themes. Weekends are red by default in Qt (poor
    contrast on dark), so every weekday gets the normal ink colour instead."""
    t = theme.current()
    cal.setGridVisible(False)
    cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
    cal.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
    cal.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
    day = QTextCharFormat()
    day.setForeground(t.color("text"))
    for d in _DAYS:
        cal.setWeekdayTextFormat(d, day)
    head = QTextCharFormat()
    head.setForeground(t.color("text_muted"))
    head.setFontWeight(600)
    cal.setHeaderTextFormat(head)


class _CalendarPopup(QFrame):
    picked = Signal(QDate)

    def __init__(self, parent: QWidget):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setProperty("card", "true")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.cal = QCalendarWidget()
        self.cal.setMinimumSize(320, 270)
        self.cal.setAccessibleName("Calendar")
        self.cal.clicked.connect(self._on_pick)
        self.cal.activated.connect(self._on_pick)
        lay.addWidget(self.cal)
        style_calendar(self.cal)
        theme.bus.changed.connect(lambda: style_calendar(self.cal))

    def _on_pick(self, qd: QDate) -> None:
        self.picked.emit(qd)
        self.close()


class DateInput(QWidget):
    changed = Signal()            # text changed
    blurred = Signal()            # editing finished (focus left / Enter)
    returnPressed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("YYYY-MM-DD")
        self._edit.setMaxLength(10)
        self._edit.setMinimumWidth(150)
        self._edit.textEdited.connect(self._on_edited)
        self._edit.textChanged.connect(lambda _t: self.changed.emit())
        self._edit.editingFinished.connect(self.blurred)
        self._edit.returnPressed.connect(self.returnPressed)
        lay.addWidget(self._edit, 1)

        self._button = IconButton("", "calendar", variant="ghost", size=18)
        self._button.setToolTip("Pick from calendar")
        self._button.setAccessibleName("Open calendar")
        self._button.setFixedWidth(40)
        self._button.clicked.connect(self._open_calendar)
        lay.addWidget(self._button)

        self._popup = _CalendarPopup(self)
        self._popup.picked.connect(self._on_picked)
        self.setFocusProxy(self._edit)

    # ---- value ------------------------------------------------------------- #

    def text(self) -> str:
        return self._edit.text().strip()

    def date(self) -> datetime | None:
        return parse_date(self.text())

    def is_blank(self) -> bool:
        return not self.text()

    def error(self) -> str | None:
        if self.is_blank():
            return "Enter the cutoff date (YYYY-MM-DD)."
        if self.date() is None:
            return "Enter a real date as YYYY-MM-DD, for example 2024-01-01."
        return None

    def set_date(self, value: date | datetime) -> None:
        self._edit.setText(value.strftime("%Y-%m-%d"))

    def clear(self) -> None:
        self._edit.clear()

    def set_invalid(self, invalid: bool) -> None:
        self._edit.setProperty("invalid", invalid)
        repolish(self._edit)

    def set_accessible_name(self, name: str) -> None:
        self._edit.setAccessibleName(name)

    def edit(self) -> QLineEdit:
        return self._edit

    # ---- internals ------------------------------------------------------------ #

    def _on_edited(self, text: str) -> None:
        formatted = format_digits(text)
        if formatted != text:
            # keep the caret next to the same digit instead of jumping to the end
            digits_before = len(re.sub(r"\D", "", text[: self._edit.cursorPosition()]))
            self._edit.setText(formatted)
            pos = digits_before if digits_before <= 4 else (digits_before + 1 if digits_before <= 6 else digits_before + 2)
            self._edit.setCursorPosition(min(pos, len(formatted)))

    def button(self) -> QWidget:
        return self._button

    def _open_calendar(self) -> None:
        current = self.date() or datetime.now()
        self._popup.cal.setSelectedDate(QDate(current.year, current.month, current.day))
        style_calendar(self._popup.cal)
        self._popup.adjustSize()
        # open below the field; flip above / slide left when the screen edge is in the way
        screen = self._edit.screen().availableGeometry()
        w, h = self._popup.width(), self._popup.height()
        below = self._edit.mapToGlobal(QPoint(0, self._edit.height() + 6))
        x = min(max(below.x(), screen.left()), screen.right() - w + 1)
        y = below.y()
        if y + h > screen.bottom() + 1:
            y = self._edit.mapToGlobal(QPoint(0, -h - 6)).y()
        self._popup.move(x, max(y, screen.top()))
        self._popup.show()
        self._popup.cal.setFocus()

    def _on_picked(self, qd: QDate) -> None:
        self._edit.setText(f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}")
        self.blurred.emit()
