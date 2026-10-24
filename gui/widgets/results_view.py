"""Shared results dashboard (Results page + Date Checker page).

KPI cards, category donut, per-section bars, a searchable/sortable table and
action buttons. Chips, charts, KPI cards and the section combo are all views of
one filter state (`_cats`, `_section`, search text) so they stay in sync.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QBoxLayout, QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QScrollArea, QStackedWidget, QTableView, QVBoxLayout, QWidget,
)

from config import FOLDER_NO_DATE, FOLDER_UPDATED
from core.summary import RunResult
from gui import fileops, icons, theme
from gui.widgets.common import ElidedLabel, IconButton, card, label, repolish
from gui.widgets.donut import DonutChart
from gui.widgets.kpi_card import KpiCard
from gui.widgets.results_table import (
    COL_DATE, COL_FILE, COL_PAGES, COL_SECTION, COL_SOURCE, COL_STATUS, COL_URL,
    ENTRY_ROLE, BadgeDelegate, ResultsModel, ResultsProxy,
)
from gui.widgets.stacked_bars import StackedBars
from models import PDFEntry

WIDE_BREAKPOINT = 1060


def _badge_icon(category: str) -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(theme.category_color(category))
    p.drawEllipse(2, 2, 28, 28)
    ink = "#0b0b0b" if category in ("updated", "no_date") else "#ffffff"
    p.drawPixmap(8, 8, icons.pixmap(theme.CATEGORY_ICON[category], ink, 16, 1.0, 3.0))
    p.end()
    return QIcon(pm)


class _UrlLabel(ElidedLabel):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


def _fmt_duration(seconds: float) -> str:
    s = int(round(seconds))
    if s < 60:
        return f"{s} s"
    m, s = divmod(s, 60)
    return f"{m} min {s:02d} s"


def _fmt_stamp(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso or "—"


class ResultsView(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._result: RunResult | None = None
        self._cats: set[str] = set()
        self._section: str | None = None
        self._syncing = False
        self._wide: bool | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        self._scroll = scroll
        content = QWidget()
        scroll.setWidget(content)
        self._root = QVBoxLayout(content)
        self._root.setContentsMargins(32, 28, 32, 32)
        self._root.setSpacing(18)

        self._build_header()
        self._build_banner()
        self._build_actions()
        self._build_kpis()
        self._build_charts()
        self._build_table_card()
        self._root.addStretch(0)

        theme.bus.changed.connect(self._on_theme)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def _build_header(self) -> None:
        box = QVBoxLayout()
        box.setSpacing(4)
        box.addWidget(label("DocumentId", "caption"))
        top = QHBoxLayout()
        top.setSpacing(12)
        self._title = label("", "h1")
        self._tag = label("", "caption")
        self._tag.setVisible(False)
        self._startpoint = label("", "pill")          # optional Startpoint, next to the DocumentId
        self._startpoint.setVisible(False)
        top.addWidget(self._title)
        top.addWidget(self._startpoint, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self._tag, 0, Qt.AlignmentFlag.AlignBottom)
        top.addStretch(1)
        self._header_extra = QHBoxLayout()
        self._header_extra.setSpacing(8)
        top.addLayout(self._header_extra)
        box.addLayout(top)
        self._meta = label("", "secondary")
        box.addWidget(self._meta)
        self._url = _UrlLabel("", "muted")
        self._url.setCursor(Qt.CursorShape.PointingHandCursor)
        self._url.clicked.connect(lambda: self._url.full_text() and fileops.open_url(self._url.full_text()))
        box.addWidget(self._url)
        self._root.addLayout(box)

    def _build_banner(self) -> None:
        self._banner = card("flat")
        row = QHBoxLayout(self._banner)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)
        self._banner_icon = QLabel()
        self._banner_icon.setFixedSize(20, 20)
        row.addWidget(self._banner_icon, 0, Qt.AlignmentFlag.AlignTop)
        self._banner_text = label("", None, wrap=True)
        row.addWidget(self._banner_text, 1)
        self._banner.setVisible(False)
        self._root.addWidget(self._banner)

    def _build_actions(self) -> None:
        self._actions = QHBoxLayout()
        self._actions.setSpacing(8)
        self._action_buttons: dict[str, IconButton] = {}
        for key, text, icon_name in (
            ("base", "Output folder", "folder"),
            ("updated", "Updated books", "folder"),
            ("no_date", "Date not found", "folder"),
            ("xlsx", "report.xlsx", "sheet"),
            ("md", "Analysis report", "file"),
        ):
            btn = IconButton(text, icon_name)
            btn.clicked.connect(lambda _=False, k=key: self._open_action(k))
            self._action_buttons[key] = btn
            self._actions.addWidget(btn)
        self._actions.addStretch(1)
        self._extra_actions = QHBoxLayout()
        self._extra_actions.setSpacing(8)
        self._actions.addLayout(self._extra_actions)
        self._root.addLayout(self._actions)

    def _build_kpis(self) -> None:
        self._kpi_grid = QGridLayout()
        self._kpi_grid.setSpacing(12)
        self._kpis: dict[str, KpiCard] = {
            "total":          KpiCard("Total PDFs", icon_name="layers"),
            "updated":        KpiCard("Updated", "updated"),
            "not_updated":    KpiCard("Not updated", "not_updated"),
            "no_date":        KpiCard("No date found", "no_date"),
            "download_error": KpiCard("Download errors", "download_error"),
            "pages":          KpiCard("Updated pages", icon_name="file"),
        }
        for cat in theme.CATEGORY_ORDER:
            self._kpis[cat].clicked.connect(lambda c=cat: self._toggle_category(c))
        self._root.addLayout(self._kpi_grid)

    def _build_charts(self) -> None:
        self._charts = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._charts.setSpacing(12)

        donut_card = card()
        dl = QVBoxLayout(donut_card)
        dl.setContentsMargins(20, 16, 20, 12)
        dl.addWidget(label("Status breakdown", "h3"))
        dl.addWidget(label("Click a slice to filter the table", "caption"))
        self._donut = DonutChart()
        self._donut.sliceClicked.connect(self._toggle_category)
        dl.addWidget(self._donut, 1)

        bars_card = card()
        bl = QVBoxLayout(bars_card)
        bl.setContentsMargins(20, 16, 20, 12)
        bl.addWidget(label("Books per section", "h3"))
        bl.addWidget(label("Click a segment to filter by section and status", "caption"))
        self._bars = StackedBars()
        self._bars.segmentClicked.connect(self._on_segment)
        bl.addWidget(self._bars, 1)

        self._charts.addWidget(donut_card, 1)
        self._charts.addWidget(bars_card, 1)
        self._root.addLayout(self._charts)

    def _build_table_card(self) -> None:
        tcard = card()
        tcard.setMinimumHeight(560)
        lay = QVBoxLayout(tcard)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(12)

        # two rows (search · section · count / status chips) so the minimum width stays small
        bar = QHBoxLayout()
        bar.setContentsMargins(20, 0, 20, 0)
        bar.setSpacing(8)
        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(20, 0, 20, 0)
        chip_row.setSpacing(8)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search documents  (Ctrl+F)")
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(220)
        self._search.setMaximumWidth(420)
        self._search.setAccessibleName("Search documents")
        self._search_action = QAction(self)
        self._search.addAction(self._search_action, QLineEdit.ActionPosition.LeadingPosition)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._apply)
        self._search.textChanged.connect(lambda _t: self._debounce.start())
        bar.addWidget(self._search)

        self._chips: dict[str, IconButton] = {}
        all_chip = IconButton("All", None, size=14)
        all_chip.setProperty("chip", True)
        all_chip.setCheckable(True)
        all_chip.clicked.connect(self._clear_categories)
        self._chips["all"] = all_chip
        chip_row.addWidget(all_chip)
        for cat in theme.CATEGORY_ORDER:
            chip = IconButton(theme.CATEGORY_LABEL[cat], None, size=14)
            chip.setProperty("chip", True)
            chip.setCheckable(True)
            chip.setIcon(_badge_icon(cat))
            chip.setIconSize(QSize(16, 16))
            chip.clicked.connect(lambda _=False, c=cat: self._toggle_category(c))
            self._chips[cat] = chip
            chip_row.addWidget(chip)
        chip_row.addStretch(1)

        bar.addStretch(1)
        self._section_combo = QComboBox()
        self._section_combo.setAccessibleName("Filter by section")
        self._section_combo.setMinimumWidth(150)
        self._section_combo.currentIndexChanged.connect(self._on_combo)
        bar.addWidget(self._section_combo)
        self._count = label("", "caption")
        self._count.setMinimumWidth(80)
        self._count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bar.addWidget(self._count)
        lay.addLayout(bar)
        lay.addLayout(chip_row)

        self._model = ResultsModel(parent=self)
        self._proxy = ResultsProxy(self)
        self._proxy.setSourceModel(self._model)

        self._table = QTableView()
        self._table.setProperty("dataTable", True)
        self._table.setModel(self._proxy)
        self._table.setItemDelegateForColumn(COL_STATUS, BadgeDelegate(self._table))
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.setWordWrap(False)
        self._table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(42)
        self._table.setAccessibleName("Documents")
        header = self._table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)   # unsorted until a header is clicked
        header.setSectionResizeMode(COL_FILE, QHeaderView.ResizeMode.Stretch)
        for col, width in ((COL_SECTION, 150), (COL_DATE, 112), (COL_SOURCE, 130),
                           (COL_PAGES, 80), (COL_STATUS, 186), (COL_URL, 260)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            header.resizeSection(col, width)
        self._table.setColumnHidden(COL_SOURCE, True)
        self._table.setColumnHidden(COL_URL, True)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._header_menu)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._row_menu)
        self._table.doubleClicked.connect(lambda idx: self._open_entry(self._entry_at(idx)))

        self._empty = label("No PDFs match these filters.", "muted")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._table)
        self._stack.addWidget(self._empty)
        lay.addWidget(self._stack, 1)
        self._root.addWidget(tcard)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def add_header_widget(self, widget: QWidget) -> None:
        self._header_extra.addWidget(widget)

    def add_action(self, widget: QWidget) -> None:
        self._extra_actions.addWidget(widget)

    @property
    def result(self) -> RunResult | None:
        return self._result

    def set_result(self, result: RunResult, animate: bool = True) -> None:
        self._result = result
        meta, stats = result.meta, result.stats
        self._cats, self._section = set(), None
        self._search.blockSignals(True)
        self._search.clear()
        self._search.blockSignals(False)

        self._title.setText(meta.project_id or "Results")
        shown = self._startpoint.fontMetrics().elidedText(
            f"Startpoint · {meta.startpoint}", Qt.TextElideMode.ElideRight, 340) if meta.startpoint else ""
        self._startpoint.setText(shown)
        self._startpoint.setToolTip(meta.startpoint)
        self._startpoint.setVisible(bool(meta.startpoint))
        is_check = result.kind == "date_check"
        self._tag.setVisible(is_check)
        self._tag.setText("DATE CHECK" if is_check else "")
        parts = [f"Cutoff {meta.cutoff}", f"Run {_fmt_stamp(meta.started_at)}"]
        if meta.duration_s:
            parts.append(_fmt_duration(meta.duration_s))
        if meta.source_run:
            parts.append(f"from run {meta.source_run}")
        self._meta.setText("  ·  ".join(parts))
        self._url.set_full_text(meta.url)
        self._url.setVisible(bool(meta.url))
        self._update_banner(result)
        self._update_actions(result)

        total = stats["total"]
        sections = len(stats["by_section"])
        cutoff = meta.cutoff
        self._kpis["total"].set_value(total, f"in {sections} section{'s' if sections != 1 else ''}", animate)
        self._kpis["updated"].set_value(stats["updated"], f"dated after {cutoff}", animate)
        self._kpis["not_updated"].set_value(stats["not_updated"], f"on or before {cutoff}", animate)
        self._kpis["no_date"].set_value(stats["no_date"], "no readable date", animate)
        self._kpis["download_error"].set_value(stats["download_error"], "see Status tooltip", animate)
        self._kpis["pages"].set_value(stats["updated_pages"], f"of {stats['total_pages']:,} total pages", animate)

        self._donut.set_data(
            [(c, theme.CATEGORY_LABEL[c], stats[c]) for c in theme.CATEGORY_ORDER], animate)
        self._bars.set_data(list(stats["by_section"].items()), animate)

        self._model.set_entries(result.entries)
        self._chips["all"].setText(f"All  {total:,}")
        for c in theme.CATEGORY_ORDER:
            self._chips[c].setText(f"{theme.CATEGORY_LABEL[c]}  {stats[c]:,}")

        self._syncing = True
        self._section_combo.clear()
        self._section_combo.addItem("All sections", None)
        for sec in stats["by_section"]:
            self._section_combo.addItem(sec, sec)
        self._syncing = False
        self._relayout()
        self._apply()

    def clear(self) -> None:
        """Drop the shown result and reset every part of the dashboard."""
        self._result = None
        self._cats, self._section = set(), None
        self._search.blockSignals(True)
        self._search.clear()
        self._search.blockSignals(False)
        self._model.set_entries([])
        self._proxy.set_filters("", set(), None)
        self._syncing = True
        self._section_combo.clear()
        self._syncing = False
        for card_ in self._kpis.values():
            card_.set_value(0, "", animate=False)
            card_.set_active(False)
        self._donut.set_data([], animate=False)
        self._bars.set_data([], animate=False)
        self._banner.setVisible(False)
        self._title.setText("")
        self._startpoint.setVisible(False)
        self._meta.setText("")
        self._url.set_full_text("")
        self._count.setText("")
        self._stack.setCurrentIndex(0)

    def search_box(self) -> QLineEdit:
        return self._search

    def scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ------------------------------------------------------------------ #
    # Header pieces
    # ------------------------------------------------------------------ #

    def _update_banner(self, result: RunResult) -> None:
        meta = result.meta
        msgs: list[str] = []
        icon_name, color = "alert", "no_date"
        if meta.status == "cancelled":
            msgs.append("This run was cancelled — results are partial and no reports were written.")
        elif meta.status == "failed":
            msgs.append(meta.error or "This run failed.")
            color = "error"
        msgs.extend(meta.warnings)
        self._banner.setVisible(bool(msgs))
        if msgs:
            self._banner_text.setText("\n".join(msgs))
            self._banner_icon.setPixmap(icons.pixmap(icon_name, theme.current()[color], 20, self.devicePixelRatioF()))

    def _paths(self, result: RunResult) -> dict[str, Path | None]:
        base = result.base_dir
        if base is None:
            return {k: None for k in self._action_buttons}
        return {
            "base": base,
            "updated": base / FOLDER_UPDATED,
            "no_date": base / FOLDER_NO_DATE,
            "xlsx": base / "report.xlsx",
            "md": base / "analysis_report.md",
        }

    def _update_actions(self, result: RunResult) -> None:
        paths = self._paths(result)
        check = result.kind == "date_check"
        for key, btn in self._action_buttons.items():
            btn.setVisible(not check or key == "base")
            p = paths[key]
            btn.setEnabled(bool(p and p.exists()))

    def _open_action(self, key: str) -> None:
        if self._result is None:
            return
        p = self._paths(self._result).get(key)
        if p is not None:
            fileops.open_path(p)

    # ------------------------------------------------------------------ #
    # Filtering
    # ------------------------------------------------------------------ #

    def _toggle_category(self, cat: str) -> None:
        self._cats ^= {cat}
        self._apply()

    def _clear_categories(self) -> None:
        self._cats.clear()
        self._section = None
        self._apply()

    def _on_segment(self, section: str, cat: str) -> None:
        if self._section == section and self._cats == {cat}:
            self._section, self._cats = None, set()
        else:
            self._section, self._cats = section, {cat}
        self._apply()

    def _on_combo(self, _index: int) -> None:
        if self._syncing:
            return
        self._section = self._section_combo.currentData()
        self._apply()

    def _focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    def _apply(self) -> None:
        self._proxy.set_filters(self._search.text(), self._cats, self._section)
        self._syncing = True
        for cat in theme.CATEGORY_ORDER:
            self._chips[cat].setChecked(cat in self._cats)
            self._kpis[cat].set_active(cat in self._cats)
        self._chips["all"].setChecked(not self._cats and self._section is None)
        idx = self._section_combo.findData(self._section) if self._section else 0
        self._section_combo.setCurrentIndex(max(idx, 0))
        self._syncing = False
        self._donut.set_active(self._cats)
        self._bars.set_filter(self._cats, self._section)
        shown, total = self._proxy.rowCount(), self._model.rowCount()
        self._count.setText(f"{shown:,} of {total:,}")
        self._stack.setCurrentIndex(0 if shown else 1)

    # ------------------------------------------------------------------ #
    # Table interactions
    # ------------------------------------------------------------------ #

    def _entry_at(self, proxy_index) -> PDFEntry | None:
        if not proxy_index.isValid():
            return None
        return self._proxy.data(proxy_index, ENTRY_ROLE)

    def _open_entry(self, entry: PDFEntry | None) -> None:
        if entry is not None and entry.local_path is not None:
            fileops.open_path(entry.local_path)

    def _row_menu(self, pos: QPoint) -> None:
        entry = self._entry_at(self._table.indexAt(pos))
        if entry is None:
            return
        has_file = bool(entry.local_path and entry.local_path.exists())
        menu = QMenu(self)
        t = theme.current()
        a_open = menu.addAction(icons.icon("external", t["text_secondary"], 16), "Open PDF")
        a_show = menu.addAction(icons.icon("folder", t["text_secondary"], 16), "Show in folder")
        menu.addSeparator()
        a_url = menu.addAction(icons.icon("copy", t["text_secondary"], 16), "Copy URL")
        a_name = menu.addAction(icons.icon("copy", t["text_secondary"], 16), "Copy file name")
        a_open.setEnabled(has_file)
        a_show.setEnabled(has_file)
        a_url.setEnabled(bool(entry.url))
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is a_open:
            self._open_entry(entry)
        elif chosen is a_show and entry.local_path:
            fileops.show_in_folder(entry.local_path)
        elif chosen is a_url:
            QGuiApplication.clipboard().setText(entry.url)
        elif chosen is a_name:
            QGuiApplication.clipboard().setText(entry.name)

    def _header_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        for col, name in ((COL_SOURCE, "Date source"), (COL_URL, "URL")):
            act = menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(not self._table.isColumnHidden(col))
            act.toggled.connect(lambda on, c=col: self._table.setColumnHidden(c, not on))
        menu.exec(self._table.horizontalHeader().mapToGlobal(pos))

    # ------------------------------------------------------------------ #
    # Responsive layout / theme
    # ------------------------------------------------------------------ #

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        wide = self.width() >= WIDE_BREAKPOINT
        if wide == self._wide:
            return
        self._wide = wide
        while self._kpi_grid.count():
            self._kpi_grid.takeAt(0)
        order = ["total", "updated", "not_updated", "no_date", "download_error", "pages"]
        cols = 6 if wide else 3
        for i, key in enumerate(order):
            self._kpi_grid.addWidget(self._kpis[key], i // cols, i % cols)
        for c in range(6):
            self._kpi_grid.setColumnStretch(c, 1 if c < cols else 0)
        self._charts.setDirection(QBoxLayout.Direction.LeftToRight if wide else QBoxLayout.Direction.TopToBottom)

    def _on_theme(self) -> None:
        t = theme.current()
        self._search_action.setIcon(icons.icon("search", t["text_muted"], 16))
        for cat in theme.CATEGORY_ORDER:
            self._chips[cat].setIcon(_badge_icon(cat))
        if self._result is not None:
            self._update_banner(self._result)
        self._table.viewport().update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._on_theme()
