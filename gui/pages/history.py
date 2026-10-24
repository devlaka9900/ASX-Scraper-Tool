"""History: runs made with this app (each writes history/run_<id>.json)."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QModelIndex, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QMenu, QStackedWidget, QStyledItemDelegate,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.summary import CATEGORIES, HistoryItem, scan_history
from gui import fileops, icons, theme
from gui.settings import Settings
from gui.widgets.common import IconButton, card, label
from gui.widgets.watermark import WatermarkWidget

COLS = ("Run", "DocumentId", "Startpoint", "Cutoff", "Result", "PDFs", "Duration", "Status")
C_RUN, C_PROJECT, C_START, C_CUTOFF, C_RESULT, C_PDFS, C_DUR, C_STATUS = range(8)
ITEM_ROLE = Qt.ItemDataRole.UserRole
_STATUS_LABEL = {"completed": "Completed", "cancelled": "Cancelled", "failed": "Failed"}


class _ResultBarDelegate(QStyledItemDelegate):
    """Mini stacked bar of the four categories (2px gaps, 4px radius)."""

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        opt = option.__class__(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style()
        style.drawControl(style.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        item: HistoryItem = index.data(ITEM_ROLE)
        stats = item.stats or {}
        total = sum(stats.get(c, 0) for c in CATEGORIES)
        rect = QRectF(option.rect.adjusted(12, 0, -12, 0))
        bar = QRectF(rect.left(), rect.center().y() - 5, rect.width(), 10)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if total <= 0:
            painter.setBrush(theme.current().color("track"))
            painter.drawRoundedRect(bar, 4, 4)
        else:
            segs = [(c, stats.get(c, 0)) for c in CATEGORIES if stats.get(c, 0) > 0]
            usable = bar.width() - 2 * (len(segs) - 1)
            x = bar.left()
            for i, (cat, n) in enumerate(segs):
                w = max(3.0, usable * n / total)
                painter.setBrush(theme.category_color(cat))
                painter.drawRoundedRect(QRectF(x, bar.top(), w, bar.height()), 3 if i == len(segs) - 1 else 0.8, 3 if i == len(segs) - 1 else 0.8)
                x += w + 2
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(180, 44)


class HistoryPage(QWidget):
    openRequested = Signal(object)           # HistoryItem

    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self._settings = settings
        self._items: list[HistoryItem] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(16)
        lay.addWidget(label("History", "h1"))
        lay.addWidget(label("Runs made with this app. Double-click one to reopen its results.", "secondary"))

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._open_btn = IconButton("Open results", "chart", variant="primary")
        self._open_btn.clicked.connect(self._open_selected)
        self._folder_btn = IconButton("Open folder", "folder")
        self._folder_btn.clicked.connect(self._open_folder)
        self._remove_btn = IconButton("Remove from list", "trash")
        self._remove_btn.setToolTip("Hides this run from the list. Files on disk are not deleted.")
        self._remove_btn.clicked.connect(self._remove_selected)
        refresh = IconButton("Refresh", "refresh", variant="ghost")
        refresh.clicked.connect(self.refresh)
        for b in (self._open_btn, self._folder_btn, self._remove_btn):
            actions.addWidget(b)
        actions.addStretch(1)
        actions.addWidget(refresh)
        lay.addLayout(actions)

        holder = card()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        self._table = QTableWidget(0, len(COLS))
        self._table.setProperty("dataTable", True)
        self._table.setHorizontalHeaderLabels(COLS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.setWordWrap(False)                    # long ids/startpoints elide instead of wrapping
        self._table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(44)
        self._table.setAccessibleName("Run history")
        self._table.setItemDelegateForColumn(C_RESULT, _ResultBarDelegate(self._table))
        header = self._table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(C_PROJECT, QHeaderView.ResizeMode.Stretch)
        # at the 1100px minimum the DocumentId (stretch column) must still get ~150px
        for col, width in ((C_RUN, 122), (C_START, 128), (C_CUTOFF, 88), (C_RESULT, 100), (C_PDFS, 52),
                           (C_DUR, 76), (C_STATUS, 94)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            header.resizeSection(col, width)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._table.doubleClicked.connect(lambda _i: self._open_selected())
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._menu)

        self._empty = WatermarkWidget()
        el = QVBoxLayout(self._empty)
        el.addStretch(1)
        t = label("No runs yet", "h2")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h = label("Runs you start from New run will be listed here.", "muted")
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(t)
        el.addWidget(h)
        el.addStretch(1)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._table)
        self._stack.addWidget(self._empty)
        hl.addWidget(self._stack)
        lay.addWidget(holder, 1)
        self._update_buttons()

    # ---- data ----------------------------------------------------------------- #

    def refresh(self) -> None:
        roots = list(dict.fromkeys([self._settings.output_dir, *self._settings.history_roots()]))
        removed = self._settings.removed_history()
        self._items = [i for i in scan_history(roots) if str(i.path) not in removed]
        self._table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            m, s = item.meta, item.stats
            when = _fmt(m.started_at)
            cells = {
                C_RUN: when, C_PROJECT: m.project_id, C_START: m.startpoint or "—",
                C_CUTOFF: m.cutoff, C_RESULT: "",
                C_PDFS: f"{s.get('total', 0):,}",
                C_DUR: f"{m.duration_s:.0f} s" if m.duration_s else "—",
                C_STATUS: _STATUS_LABEL.get(m.status, m.status) + ("" if item.base_exists else " (files missing)"),
            }
            for col, text in cells.items():
                cell = QTableWidgetItem(text)
                cell.setData(ITEM_ROLE, item)
                if col in (C_PROJECT, C_START) and text and text != "—":
                    cell.setToolTip(text)             # full text when the column is narrow
                if col == C_PDFS:
                    cell.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
                if col == C_RESULT:
                    cell.setToolTip(
                        f"Updated {s.get('updated', 0)} · Not updated {s.get('not_updated', 0)} · "
                        f"No date {s.get('no_date', 0)} · Errors {s.get('download_error', 0)}")
                self._table.setItem(row, col, cell)
        self._stack.setCurrentIndex(0 if self._items else 1)
        self._update_buttons()

    def _selected(self) -> HistoryItem | None:
        rows = self._table.selectionModel().selectedRows() if self._table.selectionModel() else []
        if not rows:
            return None
        return self._table.item(rows[0].row(), 0).data(ITEM_ROLE)

    def _update_buttons(self) -> None:
        item = self._selected()
        can_open = item is not None and item.meta.status == "completed" and item.base_exists
        self._open_btn.setEnabled(can_open)
        self._open_btn.setToolTip("" if can_open or item is None else
                                  "Only completed runs with their files on disk can be reopened.")
        self._folder_btn.setEnabled(item is not None and item.base_dir.exists())
        self._remove_btn.setEnabled(item is not None)

    def _open_selected(self) -> None:
        item = self._selected()
        if item is not None and item.meta.status == "completed" and item.base_exists:
            self.openRequested.emit(item)

    def _open_folder(self) -> None:
        item = self._selected()
        if item is not None:
            fileops.open_path(item.base_dir)

    def _remove_selected(self) -> None:
        item = self._selected()
        if item is not None:
            self._settings.remove_history_item(item.path)
            self.refresh()

    def _menu(self, pos) -> None:
        if self._selected() is None:
            return
        menu = QMenu(self)
        a_open = menu.addAction("Open results")
        a_folder = menu.addAction("Open folder")
        menu.addSeparator()
        a_rm = menu.addAction("Remove from list")
        a_open.setEnabled(self._open_btn.isEnabled())
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is a_open:
            self._open_selected()
        elif chosen is a_folder:
            self._open_folder()
        elif chosen is a_rm:
            self._remove_selected()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()


def _fmt(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso or "—"
