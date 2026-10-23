"""Table plumbing for the results view: model, filter proxy, badge delegate."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QPointF, QRectF, QSize, QSortFilterProxyModel, Qt,
)
from PySide6.QtGui import QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from gui import icons, theme
from models import PDFEntry

COLUMNS = ("File", "Section", "Date", "Date source", "Pages", "Status", "URL")
COL_FILE, COL_SECTION, COL_DATE, COL_SOURCE, COL_PAGES, COL_STATUS, COL_URL = range(7)

SORT_ROLE = Qt.ItemDataRole.UserRole
ENTRY_ROLE = Qt.ItemDataRole.UserRole + 1

_SOURCE_LABEL = {"pdf_metadata": "PDF metadata", "none": "—", "": "—"}
_EPOCH = datetime(1970, 1, 1)


class ResultsModel(QAbstractTableModel):
    def __init__(self, entries: list[PDFEntry] | None = None, parent=None):
        super().__init__(parent)
        self._entries: list[PDFEntry] = entries or []

    def set_entries(self, entries: list[PDFEntry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return COLUMNS[section]
            if role == Qt.ItemDataRole.TextAlignmentRole and section == COL_PAGES:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        e = self._entries[index.row()]
        col = index.column()

        if role == ENTRY_ROLE:
            return e
        if role == SORT_ROLE:
            if col == COL_DATE:
                # pure-Python key: datetime.timestamp() raises OSError for pre-1970 dates on Windows
                return (e.resolved_date - _EPOCH).total_seconds() if e.resolved_date else -1e18
            if col == COL_PAGES:
                return e.page_count or 0
            if col == COL_STATUS:
                order = theme.CATEGORY_ORDER
                return order.index(e.category) if e.category in order else len(order)
            return self._text(e, col).casefold()
        if role == Qt.ItemDataRole.DisplayRole:
            return self._text(e, col)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col == COL_PAGES:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            if col == COL_STATUS:
                return self._status_tip(e)
            if col in (COL_FILE, COL_URL):
                return self._text(e, col)
        if role == Qt.ItemDataRole.ForegroundRole and col in (COL_SOURCE, COL_URL, COL_SECTION):
            return theme.current().color("text_secondary")
        return None

    @staticmethod
    def _text(e: PDFEntry, col: int) -> str:
        if col == COL_FILE:
            return e.name
        if col == COL_SECTION:
            return e.display_section
        if col == COL_DATE:
            return e.display_date
        if col == COL_SOURCE:
            return _SOURCE_LABEL.get(e.date_source, e.date_source or "—")
        if col == COL_PAGES:
            return f"{e.page_count:,}" if e.page_count else "—"
        if col == COL_STATUS:
            return theme.CATEGORY_LABEL.get(e.category, e.category or "—")
        if col == COL_URL:
            return e.url or "—"
        return ""

    @staticmethod
    def _status_tip(e: PDFEntry) -> str:
        label = theme.CATEGORY_LABEL.get(e.category, e.category or "")
        if e.category == "download_error":
            return f"{label}: {e.download_error}"
        if e.category == "no_date" and e.local_path is not None and not e.page_count:
            return f"{label}. The file exists but could not be read as a PDF (0 pages)."
        return label


class ResultsProxy(QSortFilterProxyModel):
    """AND of text search, category set and section; filters are applied explicitly
    (setDynamicSortFilter(False) + invalidateFilter) so typing stays cheap."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDynamicSortFilter(False)
        self.setSortRole(SORT_ROLE)
        self._text = ""
        self._cats: set[str] = set()
        self._section: str | None = None

    def set_filters(self, text: str, cats: set[str], section: str | None) -> None:
        self._text = text.strip().casefold()
        self._cats = set(cats)
        self._section = section
        self.invalidateFilter()

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        model = self.sourceModel()
        e: PDFEntry = model.data(model.index(row, 0, parent), ENTRY_ROLE)
        if self._cats and e.category not in self._cats:
            return False
        if self._section is not None and e.display_section != self._section:
            return False
        if self._text:
            hay = f"{e.name} {e.url} {e.display_section}".casefold()
            if self._text not in hay:
                return False
        return True


class BadgeDelegate(QStyledItemDelegate):
    """Status pill: tinted background + glyph + label in ink (never colour alone)."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        t = theme.current()
        # row background (hover / selection) from the style
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        entry: PDFEntry = index.data(ENTRY_ROLE)
        cat = entry.category
        color = theme.category_color(cat)

        font = QFont(option.font)
        font.setPointSizeF(9.5)
        font.setWeight(QFont.Weight.Medium)
        fm = QFontMetricsF(font)
        w = fm.horizontalAdvance(text) + 46
        h = 26.0
        rect = QRectF(option.rect.left() + 8, option.rect.center().y() - h / 2, w, h)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tint = QRectF(rect)
        bg = theme.category_color(cat)
        bg.setAlphaF(0.18 if t.is_dark else 0.16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(tint, h / 2, h / 2)

        dot = QRectF(rect.left() + 6, rect.center().y() - 8, 16, 16)
        painter.setBrush(color)
        painter.drawEllipse(dot)
        ink = "#0b0b0b" if cat in ("updated", "no_date") else "#ffffff"
        glyph = icons.pixmap(theme.CATEGORY_ICON.get(cat, "question"), ink, 10, painter.device().devicePixelRatioF(), 3.0)
        painter.drawPixmap(QPointF(dot.left() + 3, dot.top() + 3), glyph)

        painter.setFont(font)
        painter.setPen(t.color("text"))
        painter.drawText(QRectF(dot.right() + 6, rect.top(), rect.width() - 30, h),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        font = QFont(option.font)
        font.setPointSizeF(9.5)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        return QSize(int(QFontMetricsF(font).horizontalAdvance(text)) + 70, 40)
