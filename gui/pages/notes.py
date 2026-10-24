"""Notes: developer notes with a heading and a short rich-text body (full CRUD).

Formatting is limited on purpose: bold, italic, underline and text colour (see gui/notes_html.py).
Notes live in core.notes.NotesStore (per-user JSON file).
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QModelIndex, QPoint, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction, QBrush, QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap, QShortcut, QTextCharFormat, QTextCursor,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QPushButton, QStackedWidget, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTextEdit, QVBoxLayout, QWidget,
)

from core.notes import BODY_MAX, TITLE_MAX, Note, NotesError, NotesStore
from gui import icons, theme
from gui.notes_html import PALETTE, document_to_html, load_html, plain_text, sanitize_html
from gui.widgets.common import IconButton, card, divider, label, primary
from gui.widgets.watermark import WatermarkWidget

NOTE_ROLE = Qt.ItemDataRole.UserRole


def _fmt_time(iso: str) -> str:
    try:
        when = datetime.fromisoformat(iso)
    except ValueError:
        return iso or ""
    now = datetime.now()
    if when.date() == now.date():
        return f"Today {when:%H:%M}"
    if when.year == now.year:
        return f"{when:%d %b %H:%M}"
    return f"{when:%d %b %Y}"


class _NoteDelegate(QStyledItemDelegate):
    """Two-line list row: heading (bold) + one-line preview, updated time on the right."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        opt.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        note: Note = index.data(NOTE_ROLE)
        t = theme.current()
        rect = QRectF(option.rect).adjusted(14, 8, -14, -8)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        title_font = QFont(option.font)
        title_font.setPointSizeF(10.5)
        title_font.setWeight(QFont.Weight.DemiBold)
        small = QFont(option.font)
        small.setPointSizeF(9)

        painter.setFont(small)
        stamp = _fmt_time(note.updated_at)
        stamp_w = painter.fontMetrics().horizontalAdvance(stamp) + 4
        painter.setPen(t.color("text_muted"))
        painter.drawText(QRectF(rect.right() - stamp_w, rect.top(), stamp_w, 20),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, stamp)

        painter.setFont(title_font)
        painter.setPen(t.color("text"))
        title = painter.fontMetrics().elidedText(note.title, Qt.TextElideMode.ElideRight, int(rect.width() - stamp_w - 8))
        painter.drawText(QRectF(rect.left(), rect.top(), rect.width() - stamp_w - 8, 20),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)

        painter.setFont(small)
        painter.setPen(t.color("text_secondary"))
        preview = painter.fontMetrics().elidedText(note.preview(200) or "No text", Qt.TextElideMode.ElideRight, int(rect.width()))
        painter.drawText(QRectF(rect.left(), rect.top() + 24, rect.width(), 20),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, preview)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        view = self.parent()
        width = view.viewport().width() - 2 if view is not None else option.rect.width()
        return QSize(max(width, 120), 62)


def _tool_button(text: str, tip: str, font: QFont | None = None) -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("tool", True)
    btn.setCheckable(True)
    btn.setToolTip(tip)
    btn.setAccessibleName(tip)
    btn.setFixedSize(36, 34)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if font is not None:
        btn.setFont(font)
    return btn


class NotesPage(QWidget):
    def __init__(self, store: NotesStore | None, error: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._store = store
        self._error = error
        self._current_id: str | None = None
        self._dirty = False
        self._loading = False
        self._suppress_select = False
        self._last_color: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(14)
        root.addWidget(label("Notes", "h1"))
        root.addWidget(label("Keep developer notes: a heading and text with bold, italic, underline and colour.",
                             "secondary"))

        self._banner = card("flat")
        bl = QHBoxLayout(self._banner)
        bl.setContentsMargins(14, 10, 14, 10)
        self._banner_text = label("", None, wrap=True)
        bl.addWidget(self._banner_text)
        self._banner.setVisible(False)
        root.addWidget(self._banner)

        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, 1)

        # ---- left: search + list ---------------------------------------------------- #
        left = card()
        left.setFixedWidth(330)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(14, 14, 14, 12)
        ll.setSpacing(10)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search notes  (Ctrl+F)")
        self._search.setClearButtonEnabled(True)
        self._search.setAccessibleName("Search notes")
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(lambda: self._populate(select_id=self._current_id))
        self._search.textChanged.connect(lambda _t: self._debounce.start())
        ll.addWidget(self._search)
        self._new_btn = primary("New note", "plus")
        self._new_btn.setToolTip("Create a note (Ctrl+N)")
        self._new_btn.clicked.connect(self.new_note)
        ll.addWidget(self._new_btn)
        self._list = QListWidget()
        self._list.setProperty("noteList", True)
        self._list.setItemDelegate(_NoteDelegate(self._list))
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setUniformItemSizes(True)
        self._list.setAccessibleName("Notes list")
        self._list.currentItemChanged.connect(self._on_current_changed)
        ll.addWidget(self._list, 1)
        self._count = label("", "caption")
        ll.addWidget(self._count)
        body.addWidget(left)

        # ---- right: stack [empty | editor | unavailable] ------------------------------- #
        self._stack = QStackedWidget()
        body.addWidget(self._stack, 1)

        empty = WatermarkWidget()
        el = QVBoxLayout(empty)
        el.addStretch(1)
        t1 = label("No notes yet", "h2")
        t1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t2 = label("Create your first note to get started.", "muted")
        t2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(t1)
        el.addWidget(t2)
        el.addStretch(1)
        self._empty = empty

        editor = card()
        ed = QVBoxLayout(editor)
        ed.setContentsMargins(20, 18, 20, 16)
        ed.setSpacing(10)
        self._title = QLineEdit()
        self._title.setMaxLength(TITLE_MAX)
        self._title.setPlaceholderText("Heading")
        self._title.setAccessibleName("Note heading")
        title_font = QFont(self._title.font())
        title_font.setPointSizeF(13)
        title_font.setWeight(QFont.Weight.DemiBold)
        self._title.setFont(title_font)
        self._title.textChanged.connect(lambda _t: self._mark_dirty())
        ed.addWidget(self._title)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        bold_font = QFont(); bold_font.setBold(True)
        italic_font = QFont(); italic_font.setItalic(True)
        underline_font = QFont(); underline_font.setUnderline(True)
        self._bold = _tool_button("B", "Bold (Ctrl+B)", bold_font)
        self._italic = _tool_button("I", "Italic (Ctrl+I)", italic_font)
        self._underline = _tool_button("U", "Underline (Ctrl+U)", underline_font)
        self._bold.clicked.connect(self._apply_bold)
        self._italic.clicked.connect(self._apply_italic)
        self._underline.clicked.connect(self._apply_underline)
        self._color_btn = QPushButton("A")
        self._color_btn.setProperty("tool", True)
        self._color_btn.setToolTip("Text colour")
        self._color_btn.setAccessibleName("Text colour")
        self._color_btn.setFixedSize(52, 34)
        self._color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color_menu = QMenu(self)
        self._color_btn.setMenu(self._color_menu)
        for w in (self._bold, self._italic, self._underline, self._color_btn):
            bar.addWidget(w)
        bar.addStretch(1)
        self._status = label("", "caption")
        bar.addWidget(self._status)
        ed.addLayout(bar)
        ed.addWidget(divider())

        self._body = QTextEdit()
        self._body.setAcceptRichText(False)          # pasted text is plain; formatting only via the toolbar
        self._body.setPlaceholderText("Write your note…")
        self._body.setAccessibleName("Note text")
        self._body.document().setDefaultStyleSheet("p { margin-top: 0px; margin-bottom: 0px; }")
        self._body.document().contentsChanged.connect(self._mark_dirty)
        self._body.currentCharFormatChanged.connect(self._sync_toolbar)
        ed.addWidget(self._body, 1)

        foot = QHBoxLayout()
        self._delete_btn = IconButton("Delete", "trash", variant="danger", icon_role="text")
        self._delete_btn.setToolTip("Delete this note")
        self._delete_btn.clicked.connect(self.delete_note)
        foot.addWidget(self._delete_btn)
        foot.addStretch(1)
        self._meta = label("", "caption")
        foot.addWidget(self._meta)
        self._save_btn = primary("Save", "check")
        self._save_btn.setToolTip("Save (Ctrl+S)")
        self._save_btn.setMinimumWidth(110)
        self._save_btn.clicked.connect(self.save)
        foot.addWidget(self._save_btn)
        ed.addLayout(foot)
        self._editor = editor

        unavailable = WatermarkWidget()
        ul = QVBoxLayout(unavailable)
        ul.addStretch(1)
        self._unavail_text = label("", "muted", wrap=True)
        self._unavail_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ul.addWidget(label("Notes are unavailable", "h2"), 0, Qt.AlignmentFlag.AlignCenter)
        ul.addWidget(self._unavail_text)
        ul.addStretch(1)
        self._unavailable = unavailable

        for page in (self._empty, self._editor, self._unavailable):
            self._stack.addWidget(page)

        for seq, slot in (("Ctrl+S", self.save), ("Ctrl+N", self.new_note)):
            QShortcut(QKeySequence(seq), self, activated=slot, context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: (self._search.setFocus(), self._search.selectAll()),
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

        theme.bus.changed.connect(self._on_theme)
        self._build_color_menu()
        self._update_color_button()

        if store is None:
            self._unavail_text.setText(error or "The notes file could not be opened.")
            self._stack.setCurrentWidget(self._unavailable)
            for w in (self._search, self._new_btn, self._list):
                w.setEnabled(False)
        else:
            if store.recovered_from is not None:
                self._show_banner(f"Your notes file could not be read. It was kept as “{store.recovered_from.name}” "
                                  "and a new list was started.")
            elif store.skipped:
                kept = f" The original file was kept as “{store.kept_damaged.name}”." if store.kept_damaged else ""
                self._show_banner(f"{store.skipped} damaged note(s) in the notes file could not be read and were "
                                  f"skipped.{kept}")
            self._populate()
            self._select_first_or_empty()

    # ------------------------------------------------------------------ #
    # List
    # ------------------------------------------------------------------ #

    def _show_banner(self, text: str) -> None:
        self._banner_text.setText(text)
        self._banner.setVisible(True)

    def _populate(self, select_id: str | None = None) -> None:
        if self._store is None:
            return
        notes = self._store.search(self._search.text())
        self._suppress_select = True
        self._list.clear()
        for n in notes:
            item = QListWidgetItem()
            item.setData(NOTE_ROLE, n)
            item.setToolTip(n.title)
            self._list.addItem(item)
            if select_id and n.id == select_id:
                self._list.setCurrentItem(item)
        self._suppress_select = False
        total = len(self._store)
        query = self._search.text().strip()
        self._count.setText(f"{len(notes)} of {total} notes" if query else f"{total} note{'s' if total != 1 else ''}")

    def _select_first_or_empty(self) -> None:
        if self._list.count():
            self._list.setCurrentRow(0)            # triggers _on_current_changed -> loads it
        else:
            self._current_id = None
            self._stack.setCurrentWidget(self._empty)

    def _on_current_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        if self._suppress_select or current is None:
            return
        note: Note = current.data(NOTE_ROLE)
        if note.id == self._current_id:
            return
        if not self._confirm_discard():
            self._suppress_select = True            # put the selection back on the note being edited
            if previous is not None:
                self._list.setCurrentItem(previous)
            else:
                self._list.setCurrentRow(-1)
            self._suppress_select = False
            return
        self._load(note)
        # a "Save" answer inside the prompt rebuilt the list around the *old* note; put the
        # highlight back on the note that is actually shown in the editor
        self._select_in_list(note.id)

    def _reset_typing_format(self) -> None:
        """A cleared / reloaded editor starts with plain typing (otherwise bold, italic, underline
        or a colour switched on in the previous note would carry over into the next one)."""
        self._body.setCurrentCharFormat(QTextCharFormat())
        self._sync_toolbar(QTextCharFormat())

    def _select_in_list(self, note_id: str) -> None:
        self._suppress_select = True
        try:
            for row in range(self._list.count()):
                item = self._list.item(row)
                if item.data(NOTE_ROLE).id == note_id:
                    self._list.setCurrentItem(item)
                    break
        finally:
            self._suppress_select = False

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #

    def new_note(self) -> None:
        if self._store is None or not self._confirm_discard():
            return
        self._suppress_select = True
        self._list.clearSelection()
        self._list.setCurrentRow(-1)
        self._suppress_select = False
        self._loading = True
        self._current_id = None
        self._title.clear()
        self._body.clear()
        self._reset_typing_format()
        self._body.document().clearUndoRedoStacks()
        self._loading = False
        self._dirty = False
        self._refresh_state("New note — not saved yet")
        self._stack.setCurrentWidget(self._editor)
        self._title.setFocus()

    def _load(self, note: Note) -> None:
        self._loading = True
        self._current_id = note.id
        self._title.setText(note.title)
        # re-canonicalise on load too: a hand-edited notes.json can never add fonts, links or images
        load_html(self._body.document(), sanitize_html(note.body_html))
        self._body.document().clearUndoRedoStacks()
        self._body.moveCursor(QTextCursor.MoveOperation.Start)
        self._reset_typing_format()
        self._loading = False
        self._dirty = False
        self._refresh_state(f"Saved {_fmt_time(note.updated_at)}")
        self._meta.setText(f"Created {_fmt_time(note.created_at)}")
        self._stack.setCurrentWidget(self._editor)

    def save(self) -> bool:
        if self._store is None or self._stack.currentWidget() is not self._editor:
            return True
        doc = self._body.document()
        html, text = document_to_html(doc), plain_text(doc)
        if not self._title.text().strip() and not text.strip():
            QMessageBox.information(self, "Notes", "Enter a heading or some text before saving.")
            return False
        if len(text) > BODY_MAX:
            QMessageBox.warning(self, "Notes", f"The note is too long (max {BODY_MAX:,} characters).")
            return False
        try:
            if self._current_id is None:
                note = self._store.create(self._title.text(), html, text)
            else:
                note = self._store.update(self._current_id, title=self._title.text(), body_html=html, body_text=text)
        except (NotesError, OSError) as exc:
            QMessageBox.warning(self, "Notes", f"The note could not be saved:\n\n{exc}")
            return False
        self._current_id = note.id
        self._dirty = False
        self._loading = True
        self._title.setText(note.title)               # reflects the collapsed / default heading
        self._loading = False
        self._populate(select_id=note.id)
        self._refresh_state(f"Saved {_fmt_time(note.updated_at)}")
        self._meta.setText(f"Created {_fmt_time(note.created_at)}")
        return True

    def delete_note(self) -> None:
        if self._store is None:
            return
        if self._current_id is None:                    # an unsaved draft: just discard it
            if self._dirty:
                answer = QMessageBox.question(self, "Notes", "Discard this unsaved note?",
                                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                              QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
            self._dirty = False
            self._populate()
            self._select_first_or_empty()
            return
        note = self._store.get(self._current_id)
        name = note.title if note else "this note"
        answer = QMessageBox.question(self, "Delete note", f"Delete “{name}”?\n\nThis cannot be undone.",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._store.delete(self._current_id)
        except OSError as exc:
            QMessageBox.warning(self, "Notes", f"The note could not be deleted:\n\n{exc}")
            return
        self._current_id = None
        self._dirty = False
        self._populate()
        self._select_first_or_empty()

    # ------------------------------------------------------------------ #
    # Unsaved-changes guard
    # ------------------------------------------------------------------ #

    def has_unsaved(self) -> bool:
        return self._dirty

    def _confirm_discard(self) -> bool:
        """True when it is fine to leave the current note (saved, discarded, or nothing to lose)."""
        if not self._dirty:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Unsaved changes")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("This note has unsaved changes.")
        box.setInformativeText("Do you want to save them?")
        box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                               | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        choice = box.exec()
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        if choice == QMessageBox.StandardButton.Discard:
            self._revert_editor()
            return True
        return False

    def _revert_editor(self) -> None:
        """Really discard the unsaved edits: show the stored note again (or empty a draft), so
        nothing stale remains in the editor and the guard is not silently dropped."""
        stored = self._store.get(self._current_id) if (self._store and self._current_id) else None
        if stored is not None:
            self._load(stored)                      # also clears the dirty flag
            return
        self._loading = True
        self._current_id = None
        self._title.clear()
        self._body.clear()
        self._reset_typing_format()
        self._body.document().clearUndoRedoStacks()
        self._loading = False
        self._dirty = False
        self._refresh_state("")

    def can_leave(self) -> bool:
        """Called before navigating away / closing. A discarded blank draft must not linger in
        the editor, so show the first note (or the empty state) afterwards."""
        had_draft = self._dirty and self._current_id is None
        if not self._confirm_discard():
            return False
        if had_draft and self._store is not None:
            self._select_first_or_empty()
        return True

    def _mark_dirty(self) -> None:
        if self._loading or self._stack.currentWidget() is not self._editor:
            return
        if not self._dirty:
            self._dirty = True
            self._refresh_state("Unsaved changes")

    def _refresh_state(self, status: str) -> None:
        self._status.setText(status)
        self._save_btn.setEnabled(self._dirty or self._current_id is None)
        self._delete_btn.setEnabled(True)
        if not self._dirty and self._current_id is None:
            self._meta.setText("")

    # ------------------------------------------------------------------ #
    # Formatting toolbar
    # ------------------------------------------------------------------ #

    def _merge(self, fmt: QTextCharFormat) -> None:
        self._body.mergeCurrentCharFormat(fmt)
        self._body.setFocus()

    def _apply_bold(self, checked: bool) -> None:
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold if checked else QFont.Weight.Normal)
        self._merge(fmt)

    def _apply_italic(self, checked: bool) -> None:
        fmt = QTextCharFormat()
        fmt.setFontItalic(checked)
        self._merge(fmt)

    def _apply_underline(self, checked: bool) -> None:
        fmt = QTextCharFormat()
        fmt.setFontUnderline(checked)
        self._merge(fmt)

    def _apply_color(self, hex_color: str | None) -> None:
        fmt = QTextCharFormat()
        # "Default" = the current theme's text colour; the serializer stores that as "no colour"
        fmt.setForeground(QBrush(QColor(hex_color) if hex_color else theme.current().color("text")))
        self._last_color = hex_color
        self._update_color_button()
        self._merge(fmt)

    def _sync_toolbar(self, fmt: QTextCharFormat) -> None:
        for btn, on in ((self._bold, int(fmt.fontWeight()) >= 600), (self._italic, fmt.fontItalic()),
                        (self._underline, fmt.fontUnderline())):
            btn.blockSignals(True)
            btn.setChecked(bool(on))
            btn.blockSignals(False)

    def _build_color_menu(self) -> None:
        self._color_menu.clear()
        default = QAction("Default colour", self._color_menu)
        default.triggered.connect(lambda: self._apply_color(None))
        self._color_menu.addAction(default)
        self._color_menu.addSeparator()
        for name, hex_color in PALETTE:
            pm = QPixmap(16, 16)
            pm.fill(QColor(hex_color))
            act = QAction(QIcon(pm), name, self._color_menu)
            act.triggered.connect(lambda _=False, c=hex_color: self._apply_color(c))
            self._color_menu.addAction(act)

    def _update_color_button(self) -> None:
        pm = QPixmap(26, 26)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self._last_color) if self._last_color else theme.current().color("text_secondary")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(3, 21, 20, 4), 2, 2)       # colour bar under the "A"
        p.end()
        self._color_btn.setIcon(pm)
        self._color_btn.setIconSize(QSize(22, 22))

    # ------------------------------------------------------------------ #
    # Theme
    # ------------------------------------------------------------------ #

    def _on_theme(self) -> None:
        self._build_color_menu()
        self._update_color_button()
        if self._stack.currentWidget() is self._editor:
            # re-canonicalise so default-coloured text follows the new theme; keep caret and dirty state
            doc = self._body.document()
            html = document_to_html(doc)
            pos, dirty, loading = self._body.textCursor().position(), self._dirty, self._loading
            self._loading = True
            load_html(doc, html)
            cursor = self._body.textCursor()
            cursor.setPosition(min(pos, max(0, doc.characterCount() - 1)))
            self._body.setTextCursor(cursor)
            self._loading, self._dirty = loading, dirty
        self._list.viewport().update()

    # ------------------------------------------------------------------ #
    # Test / integration helpers
    # ------------------------------------------------------------------ #

    def current_id(self) -> str | None:
        return self._current_id
