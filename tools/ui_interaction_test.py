"""Dev-only: drive the widgets headlessly and assert the interactive behaviour.

    .venv-build\\Scripts\\python.exe tools\\ui_interaction_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ["ASX_CHECKER_GUI"] = "1"
os.environ["ASX_CHECKER_LOG_DIR"] = tempfile.mkdtemp(prefix="asx_ui_logs_")

from PySide6.QtCore import QPoint, QPointF, QSettings, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gui import anim, theme  # noqa: E402
from gui.demo import make_demo_result  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from gui.settings import Settings  # noqa: E402

fails: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        fails.append(msg)


app = QApplication([])
app.setStyle("Fusion")
anim.set_reduced_motion(True)          # deterministic: no animations
ini = QSettings(str(Path(tempfile.mkdtemp()) / "t.ini"), QSettings.Format.IniFormat)
settings = Settings(ini)
theme.apply(app, "dark")
NOTES_PATH = Path(tempfile.mkdtemp(prefix="asx_ui_notes_")) / "notes.json"   # never the user's real notes
win = MainWindow(settings, notes_path=NOTES_PATH)
win.resize(1280, 820)
win.show()

demo = make_demo_result(240)
win.results.show_result(demo, animate=False)
win.navigate("results")
app.processEvents()
view = win.results.view
stats = demo.stats
total = stats["total"]

check(view._proxy.rowCount() == total, f"table shows all {total} rows")

# donut slice click -> category filter
rect = dict(view._donut._legend_rects)["updated"]
QTest.mouseClick(view._donut, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
check(view._cats == {"updated"} and view._proxy.rowCount() == stats["updated"],
      f"donut legend click filters to Updated ({view._proxy.rowCount()}/{stats['updated']})")
check(view._chips["updated"].isChecked() and not view._chips["all"].isChecked(), "chip state follows donut")
QTest.mouseClick(view._donut, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
check(not view._cats and view._proxy.rowCount() == total, "second click clears the filter")

# ring hit-test (not just the legend)
ring_c = view._donut._ring_rect.center()
r = view._donut._ring_rect.width() / 2 - view._donut._ring_rect.width() * 0.17 / 2
hit = view._donut._key_at(QPointF(ring_c.x(), ring_c.y() - r))   # 12 o'clock on the ring = first slice
check(hit == "updated", f"ring hit-test at 12 o'clock -> {hit}")

# bar segment click -> section + category
view._bars.set_data(list(stats["by_section"].items()), animate=False)
app.processEvents()
view._bars.repaint()
seg = next((h for h in view._bars._hit if h[2] == "not_updated"), None)
check(seg is not None, "bars expose hit rects")
if seg:
    QTest.mouseClick(view._bars, Qt.MouseButton.LeftButton, pos=seg[0].center().toPoint())
    expected = stats["by_section"][seg[1]]["not_updated"]
    check(view._section == seg[1] and view._cats == {"not_updated"} and view._proxy.rowCount() == expected,
          f"bar segment click -> {seg[1]} / not_updated ({view._proxy.rowCount()}/{expected})")
    check(view._section_combo.currentData() == seg[1], "section combo follows the bar click")

# KPI click
view._clear_categories()
QTest.mouseClick(view._kpis["no_date"], Qt.MouseButton.LeftButton)
check(view._cats == {"no_date"} and view._proxy.rowCount() == stats["no_date"], "KPI card click filters")
view._clear_categories()
check(view._proxy.rowCount() == total and view._section is None, "All chip clears category + section")

# search (debounced)
view._search.setText("waiver")
QTest.qWait(260)
n_waiver = view._proxy.rowCount()
check(0 < n_waiver < total and all("waiver" in (view._proxy.data(view._proxy.index(i, 0)) or "").casefold()
                                   or "waiver" in (view._proxy.data(view._proxy.index(i, 1)) or "").casefold()
                                   for i in range(n_waiver)), f"search filters rows ({n_waiver})")
view._search.setText("zzzz-nothing")
QTest.qWait(260)
check(view._proxy.rowCount() == 0 and view._stack.currentIndex() == 1, "empty state shown for no matches")
view._search.clear()
QTest.qWait(260)
check(view._proxy.rowCount() == total and view._stack.currentIndex() == 0, "clearing search restores rows")

# sorting by pages (numeric) and date
view._table.sortByColumn(4, Qt.SortOrder.AscendingOrder)
pages = [view._proxy.data(view._proxy.index(i, 4), Qt.ItemDataRole.UserRole) for i in range(total)]
check(pages == sorted(pages), "numeric sort by Pages")

# ---- New Run form validation ----------------------------------------------------------------
page = win.new_run
page._project.setText("")
check(not page._start.isEnabled(), "Start disabled with empty form")
page._project.setText("bad/name")
page._url.setText("ftp://x")
check(not page._start.isEnabled(), "Start disabled for invalid ID/URL")
page._project.setText("My-Project_1")
page._url.setText("https://www.asx.com.au/page")
page._output.setText(tempfile.mkdtemp())
check(page._cutoff.is_blank(), "cutoff field starts blank")
check(not page._start.isEnabled(), "Start stays disabled until a cutoff date is entered")
for bad in ("2024-02-30", "2024-13-01", "20240"):
    page._cutoff.clear()
    QTest.keyClicks(page._cutoff.edit(), bad.replace("-", ""))
    check(not page._start.isEnabled(), f"Start disabled for invalid date {bad!r} (typed as {page._cutoff.text()!r})")
page._cutoff.clear()
QTest.keyClicks(page._cutoff.edit(), "20240115")
check(page._cutoff.text() == "2024-01-15", f"typing digits auto-inserts dashes ({page._cutoff.text()!r})")
check(page._start.isEnabled(), "Start enabled once ID, URL, date and folder are valid")
from PySide6.QtWidgets import QPushButton  # noqa: E402
chips = [b for b in page.findChildren(QPushButton) if b.property("chip")]
check(not chips, "no quick-pick cutoff chips on New run")
from gui.pages import new_run as _nr  # noqa: E402
check("Waivers" in _nr.DEV_NOTE and any("Developer note" == w.text() for w in page.findChildren(type(page._project_err))),
      "developer note is shown")
got = []
win.runner.start_run = lambda req: None     # do not launch a real job from the form test
page.startRequested.connect(got.append)
QTest.mouseClick(page._start, Qt.MouseButton.LeftButton)
check(len(got) == 1 and got[0].project_id == "My-Project_1" and got[0].url.endswith("/page")
      and got[0].cutoff == datetime(2024, 1, 15), "Start emits a RunRequest with the typed cutoff")
check(settings.last_project_id == "My-Project_1", "inputs remembered in settings")

# ---- theme toggle ------------------------------------------------------------------------------
was_dark = theme.current().is_dark
win.sidebar.themeToggled.emit()
check(theme.current().is_dark != was_dark and settings.theme in ("dark", "light"), "theme toggle flips and persists")

# ---- keyboard: donut -----------------------------------------------------------------------------
view._clear_categories()
view._donut.setFocus()
QTest.keyClick(view._donut, Qt.Key.Key_Right)
QTest.keyClick(view._donut, Qt.Key.Key_Return)
check(len(view._cats) == 1, "keyboard: arrow + Enter on donut toggles a category")

# ---- v1.1.0: date input, close results, watermark ---------------------------------------------------------
from datetime import datetime  # noqa: E402
from gui.widgets.date_input import format_digits, parse_date  # noqa: E402

check(format_digits("20240501") == "2024-05-01" and format_digits("2024/05/01") == "2024-05-01"
      and format_digits("2024-0") == "2024-0" and format_digits("202") == "202", "format_digits")
check(parse_date("2024-02-29") is not None and parse_date("2023-02-29") is None, "parse_date is strict (leap years)")

# calendar popup fills the field
di = page._cutoff
di.clear()
di._open_calendar()
from PySide6.QtCore import QDate  # noqa: E402
di._popup.cal.clicked.emit(QDate(2025, 3, 7))
check(di.text() == "2025-03-07", f"calendar pick fills the field ({di.text()!r})")

# date checker: needs folder + date; close button and Esc return to the placeholder
dc = win.date_checker
win.navigate("date_checker")
app.processEvents()
dc._path.setText(str(Path(tempfile.mkdtemp())))
dc._update_state()
check(not dc._go.isEnabled(), "Check dates disabled without a date (and for an empty folder)")
dc.show_result(make_demo_result(30))
check(dc._stack.currentWidget() is dc.view and dc._close_btn.isVisible(), "result view shows a Close results button")
QTest.mouseClick(dc._close_btn, Qt.MouseButton.LeftButton)
check(dc._stack.currentWidget() is dc._placeholder and dc.view.result is None
      and dc.view._model.rowCount() == 0, "Close results returns to the form and clears the view")
dc.show_result(make_demo_result(30))
win.activateWindow()
app.processEvents()
QTest.keyClick(win, Qt.Key.Key_Escape)
check(dc._stack.currentWidget() is dc._placeholder, "Esc closes the result view")

# review fixes: partial dates are not dates, caret stays put, tab order, Esc vs search box
check(parse_date("2024-12-3") is None and parse_date("2024-1-05") is None and parse_date(" 2024-12-31 ") is not None,
      "partial dates (2024-12-3) are rejected, a full padded date is accepted")
di.clear()
QTest.keyClicks(di.edit(), "2024123")
check(di.error() is not None, "seven typed digits (2024-12-3) do not count as a valid cutoff")
di.clear()
QTest.keyClicks(di.edit(), "20240501")
di.edit().setCursorPosition(6)
QTest.keyClick(di.edit(), Qt.Key.Key_Backspace)
check(di.edit().cursorPosition() < len(di.text()), f"editing mid-date keeps the caret in place ({di.edit().cursorPosition()}/{len(di.text())})")
chain, w_ = [], di.edit()
for _ in range(3):
    w_ = w_.nextInFocusChain()
    chain.append(w_)
check(di.button() in chain[:1], "calendar button follows the date field in tab order")

dc.show_result(make_demo_result(30))
win.navigate("date_checker")
app.processEvents()
dc.view.search_box().setText("waiver")
dc.view.search_box().setFocus()
win.activateWindow()
app.processEvents()
QTest.keyClick(win, Qt.Key.Key_Escape)
check(dc._stack.currentWidget() is dc.view and dc.view.search_box().text() == "",
      "first Esc clears the search box without discarding the result")
QTest.keyClick(win, Qt.Key.Key_Escape)
check(dc._stack.currentWidget() is dc._placeholder, "second Esc closes the result")

# calendar fix: data-table padding must never apply to a bare QTableView (the calendar grid is one)
import re as _re  # noqa: E402
qss = app.styleSheet()
unscoped = [m.group(0) for m in _re.finditer(r"(?m)^QTableView(?:::item)?(?::\w+)?\s*\{[^}]*padding", qss)]
check(not unscoped, "no unscoped QTableView padding rule in the stylesheet")
check('QCalendarWidget QTableView::item { padding: 0px' in qss, "calendar cells have explicit zero padding")

# watermark: present but barely visible
from PySide6.QtGui import QImage  # noqa: E402
from gui.widgets.watermark import WatermarkWidget  # noqa: E402
for mode in ("dark", "light"):
    theme.apply(app, mode)
    wm = WatermarkWidget()
    wm.resize(600, 400)
    wm.show()
    app.processEvents()
    img = wm.grab().toImage()
    bg = img.pixel(1, 1)
    diffs = [max(abs(((img.pixel(x, y) >> s) & 255) - ((bg >> s) & 255)) for s in (0, 8, 16))
             for y in range(0, 400, 2) for x in range(0, 600, 2)]
    peak = max(diffs)
    check(3 <= peak <= 30, f"watermark ({mode}) is present but faint (peak colour delta {peak}/255)")
    # repaint cost must stay low: the pattern is cached, so a repaint is just a blit
    import time as _t  # noqa: E402
    wm.resize(1920, 1080)
    wm.grab()                                 # first paint renders the cache
    t0 = _t.perf_counter()
    for _ in range(5):
        wm.repaint()
    per = (_t.perf_counter() - t0) / 5 * 1000
    check(per < 25, f"watermark repaint is cheap at 1920x1080 ({per:.1f} ms)")
    wm.close()
theme.apply(app, "dark")

# ---- v1.2.0 ---------------------------------------------------------------------------------------------------
from gui import validation  # noqa: E402
from PySide6.QtWidgets import QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget  # noqa: E402
from PySide6.QtGui import QTextCursor  # noqa: E402

# DocumentId rename: no "Project ID" left in anything a user can read on these pages
def visible_strings(root):
    out = []
    for w in root.findChildren(QLabel):
        out.append(w.text())
    for w in root.findChildren(QLineEdit):
        out += [w.placeholderText(), w.accessibleName()]
    for w in root.findChildren(QPushButton):
        out += [w.text(), w.toolTip(), w.accessibleName()]
    for w in root.findChildren(QTableWidget):
        out += [w.horizontalHeaderItem(i).text() for i in range(w.columnCount())]
    return [s for s in out if s]

for name, root in (("New run", win.new_run), ("History", win.history), ("Date checker", win.date_checker),
                   ("Results", win.results), ("Running", win.run_view)):
    check(not any("project id" in s.casefold() for s in visible_strings(root)), f"no 'Project ID' text left on {name}")
check("DocumentId" in visible_strings(win.new_run), "New run labels the field DocumentId")
check(validation.project_id_error("") == "DocumentId cannot be empty." and "DocumentId" in (validation.project_id_error("a" * 70) or ""),
      "validation messages say DocumentId")

# Startpoint: optional, free text, reaches the request
got.clear()
page._project.setText("DOC-1")
page._url.setText("https://www.asx.com.au/page")
page._output.setText(tempfile.mkdtemp())
page._cutoff.clear()
QTest.keyClicks(page._cutoff.edit(), "20240115")
page._startpoint.setText("")
check(page._start.isEnabled(), "Start is enabled with an empty Startpoint (it is optional)")
QTest.mouseClick(page._start, Qt.MouseButton.LeftButton)
check(len(got) == 1 and got[0].startpoint == "", "empty Startpoint -> empty string in the request")
got.clear()
page._startpoint.setText("  Chapter   5 / weird: ✓ <b>  ")
QTest.mouseClick(page._start, Qt.MouseButton.LeftButton)
check(len(got) == 1 and got[0].startpoint == "Chapter 5 / weird: ✓ <b>", f"free text kept, only trimmed/collapsed ({got[0].startpoint!r})")
page._startpoint.setText("x" * 300)
check(len(page._startpoint.text()) == validation.STARTPOINT_MAX, "Startpoint is capped at 100 characters")
page._startpoint.clear()

# Startpoint shown next to the DocumentId (only when set)
demo_sp = make_demo_result(20)
demo_sp.meta.startpoint = "Chapter 5"
win.results.show_result(demo_sp, animate=False)
rv = win.results.view
check(not rv._startpoint.isHidden() and "Chapter 5" in rv._startpoint.text(), "Results header shows the Startpoint pill")
win.results.show_result(make_demo_result(20), animate=False)
check(rv._startpoint.isHidden(), "…and hides it when there is none")
from core.pipeline import RunRequest  # noqa: E402
from datetime import datetime as _dt  # noqa: E402
win.run_view.begin(RunRequest("DOC-1", "https://x", _dt(2024, 1, 15), Path("."), startpoint="Chapter 5"))
check("Startpoint Chapter 5" in win.run_view._subtitle.full_text() and "DocumentId DOC-1" in win.run_view._subtitle.full_text(),
      "Running view subtitle shows DocumentId and Startpoint")

# History: DocumentId + Startpoint columns, '—' when empty
from core.summary import write_summary  # noqa: E402
hist_root = Path(tempfile.mkdtemp(prefix="asx_hist_"))
for pid, sp_text, rid in (("DOC-A", "Chapter 5", "20261001_100000"), ("DOC-B", "", "20261002_100000")):
    r = make_demo_result(12, base_dir=hist_root / pid)
    r.meta.project_id, r.meta.startpoint, r.meta.run_id, r.meta.started_at = pid, sp_text, rid, f"2026-10-0{rid[7]}T10:00:00"
    (hist_root / pid).mkdir(parents=True)
    write_summary(r)
settings.add_history_root(hist_root)
win.history.refresh()
tbl = win.history._table
heads = [tbl.horizontalHeaderItem(i).text() for i in range(tbl.columnCount())]
check("DocumentId" in heads and "Startpoint" in heads and heads.index("Startpoint") == heads.index("DocumentId") + 1,
      f"History headers: {heads}")
cells = {tbl.item(r, heads.index("DocumentId")).text(): tbl.item(r, heads.index("Startpoint")).text() for r in range(tbl.rowCount())}
check(cells.get("DOC-A") == "Chapter 5" and cells.get("DOC-B") == "—", f"History startpoint cells {cells}")
dc.refresh_runs()
check(any("DOC-A  ·  Chapter 5" in dc._runs.itemText(i) for i in range(dc._runs.count())), "Date checker run picker shows the Startpoint")

# ---- sidebar ---------------------------------------------------------------------------------------------------
check(len(win.sidebar._buttons) == 6 and list(win.sidebar._buttons) == ["new_run", "results", "history", "date_checker", "notes", "agent"],
      "sidebar has six pages")
check(win.sidebar._buttons["notes"].shortcut().toString() == "Alt+5" and win.sidebar._buttons["agent"].shortcut().toString() == "Alt+6",
      "Alt+5 / Alt+6 shortcuts")
check("🤖" in win.sidebar._buttons["agent"].text(), "Agent entry carries the robot emoji")

# ---- Agent page ------------------------------------------------------------------------------------------------
anim.set_reduced_motion(False)
win.navigate("agent")
QTest.qWait(200)
check(win.agent.hero.running and win.agent.hero.phase > 0.05 and win.agent.stripes.phase > 0.05, "Agent animation runs while the page is visible")
from PySide6.QtGui import QMovie  # noqa: E402
mv = win.agent.hero._movie
check(mv is not None and mv.isValid() and mv.frameCount() > 100, f"Agent robot GIF loaded ({mv.frameCount() if mv else 0} frames)")
check(mv.state() == QMovie.MovieState.Running and mv.currentFrameNumber() > 0, "robot GIF is playing while the page is visible")
win.navigate("history")
QTest.qWait(80)
check(not win.agent.hero.running, "Agent animation stops when the page is hidden")
check(mv.state() == QMovie.MovieState.Paused, "robot GIF pauses when the page is hidden")
anim.set_reduced_motion(True)
win.navigate("agent")
phase_before = win.agent.hero.phase
QTest.qWait(150)
check(not win.agent.hero.running and win.agent.hero.phase == phase_before, "reduced motion: Agent page is static")
check(mv.state() != QMovie.MovieState.Running and mv.currentFrameNumber() == 0, "reduced motion: robot GIF shows frame 0 and does not play")
win.navigate("history")

# ---- Notes: full CRUD through the widgets ------------------------------------------------------------------------
from gui.notes_html import document_to_html, sanitize_html  # noqa: E402
from gui.pages.notes import NOTE_ROLE  # noqa: E402
notes = win.notes
check(notes.current_id() is None and notes._stack.currentWidget() is notes._empty, "Notes starts with the empty state")

real_exec, real_question = QMessageBox.exec, QMessageBox.question
def answer_exec(button):
    QMessageBox.exec = lambda self: button
def answer_question(button):
    QMessageBox.question = staticmethod(lambda *a, **k: button)

win.navigate("notes")
notes.new_note()
check(notes._stack.currentWidget() is notes._editor and notes._title.text() == "" and notes.current_id() is None,
      "New note opens a blank editor")
notes._title.setText("Alpha heading")
notes._body.setPlainText("hello brave world")
cur = notes._body.textCursor()
cur.setPosition(0); cur.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
notes._body.setTextCursor(cur)
notes._bold.setChecked(True); notes._apply_bold(True)
cur.setPosition(6); cur.setPosition(11, QTextCursor.MoveMode.KeepAnchor)
notes._body.setTextCursor(cur)
notes._apply_italic(True); notes._apply_underline(True); notes._apply_color("#e5484d")
check(notes._dirty and notes._status.text() == "Unsaved changes", "editing marks the note as unsaved")
check(notes.save() is True and not notes._dirty, "Save succeeds")
n_id = notes.current_id()
saved = notes._store.get(n_id)
check(n_id and saved.title == "Alpha heading" and saved.body_text == "hello brave world", "note stored with heading and text")
check("<b>hello</b>" in saved.body_html and "<i>" in saved.body_html and "<u>" in saved.body_html
      and 'color:#e5484d' in saved.body_html, f"bold / italic / underline / colour persisted: {saved.body_html}")
check(notes._list.count() == 1 and notes._count.text() == "1 note", "list shows the new note")

# Read: a fresh page over the same file renders the same formatting and a stable round trip
from core.notes import NotesStore  # noqa: E402
from gui.pages.notes import NotesPage  # noqa: E402
page2 = NotesPage(NotesStore(NOTES_PATH))
check(page2.current_id() == n_id and page2._title.text() == "Alpha heading", "reopened Notes page loads the saved note")
check(document_to_html(page2._body.document()) == saved.body_html, "formatting round-trips unchanged through load -> serialise")

# Update
notes._title.setText("Alpha renamed")
check(notes._dirty, "changing the heading marks the note unsaved")
check(notes.save() and notes._store.get(n_id).title == "Alpha renamed" and notes._list.count() == 1, "Update keeps one note, new heading")

# Unsaved-changes guard
notes._body.setPlainText("changed but unsaved")
answer_exec(QMessageBox.StandardButton.Cancel)
before = notes.current_id()
notes.new_note()
check(notes.current_id() == before and notes._dirty, "Cancel on the unsaved prompt keeps editing the same note")
answer_exec(QMessageBox.StandardButton.Discard)
notes.new_note()
check(notes.current_id() is None and not notes._dirty and notes._store.get(n_id).body_text == "hello brave world",
      "Discard drops the edits and opens a blank note; the stored note is unchanged")
notes._title.setText("Beta")
notes._body.setPlainText("second note")
check(notes.save() and len(notes._store) == 2, "Create a second note")
notes.new_note()                      # a new note, not an edit of Beta
notes._title.setText("Gamma")
notes._body.setPlainText("third")
notes.save()
check(len(notes._store) == 3 and notes._list.count() == 3, "three notes listed")

# Search
notes._search.setText("brave")
QTest.qWait(220)
check(notes._list.count() == 1 and "of 3" in notes._count.text(), f"search filters the list ({notes._count.text()})")
notes._search.clear()
QTest.qWait(220)
check(notes._list.count() == 3, "clearing the search restores the list")

# Switching notes with unsaved edits asks first
notes._list.setCurrentRow(0)
cur_id = notes.current_id()
notes._body.setPlainText("dirty edit")
answer_exec(QMessageBox.StandardButton.Cancel)
notes._list.setCurrentRow(2)
check(notes.current_id() == cur_id and notes._list.currentRow() == 0, "selecting another note is blocked on Cancel and the selection snaps back")
answer_exec(QMessageBox.StandardButton.Save)
notes._list.setCurrentRow(2)
check(notes.current_id() != cur_id and not notes._dirty, "Save in the prompt saves, then switches")

# Leaving the page / closing the window with unsaved edits
notes._body.setPlainText("unsaved again")
answer_exec(QMessageBox.StandardButton.Cancel)
win.navigate("history")
check(win.stack.currentWidget() is win.notes, "navigation away from dirty Notes is blocked on Cancel")
closed = win.close()
check(closed is False and win.isVisible() and notes._dirty, "closing the window is blocked on Cancel (edits kept)")
answer_exec(QMessageBox.StandardButton.Discard)
win.navigate("history")
check(win.stack.currentWidget() is win.history and not notes._dirty, "Discard lets navigation continue")
win.navigate("notes")

# Delete (confirmation)
count_before = len(notes._store)
answer_question(QMessageBox.StandardButton.No)
notes.delete_note()
check(len(notes._store) == count_before, "Delete answered No keeps the note")
answer_question(QMessageBox.StandardButton.Yes)
notes.delete_note()
check(len(notes._store) == count_before - 1 and notes._list.count() == count_before - 1, "Delete answered Yes removes it")
while len(notes._store):
    notes.delete_note()
check(len(notes._store) == 0 and notes._stack.currentWidget() is notes._empty, "deleting the last note shows the empty state")
QMessageBox.exec, QMessageBox.question = real_exec, real_question

# Empty note refuses to save; pasted rich text is flattened to plain text
notes.new_note()
answer_exec(QMessageBox.StandardButton.Ok)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
check(notes.save() is False and len(notes._store) == 0, "a completely empty note is not saved")
# typing format must not leak from the previous note: bold switched on earlier, new note types plain
check(not notes._bold.isChecked() and int(notes._body.currentCharFormat().fontWeight()) < 600
      and not notes._body.currentCharFormat().fontItalic(), "a new note starts with plain typing (no carried-over bold/italic)")
from PySide6.QtCore import QMimeData  # noqa: E402
from PySide6.QtWidgets import QApplication as _QA  # noqa: E402
md = QMimeData()
md.setHtml('<p style="font-size:40pt;font-family:Comic Sans MS"><b>pasted</b> <a href="http://x">link</a></p>')
md.setText("pasted link")
_QA.clipboard().setMimeData(md)
notes._body.paste()
pasted = document_to_html(notes._body.document())
check("<b>" not in pasted and "font" not in pasted and "href" not in pasted and "pasted link" in notes._body.toPlainText(),
      f"pasting rich text inserts plain text only ({pasted})")
notes._dirty = False
QMessageBox.exec = real_exec

# Sanitiser allow-list
import re as _re2  # noqa: E402
hostile = ('<script>alert(1)</script><p style="font-size:40pt;font-family:Comic Sans MS">x <b>b</b> '
           '<img src="C:/a.png"><a href="http://evil">l</a></p><table><tr><td>t</td></tr></table>')
clean = sanitize_html(hostile)
check(set(_re2.findall(r"</?(\w+)", clean)) <= {"p", "b", "i", "u", "span", "br"} and "font" not in clean
      and "alert" not in clean and "img" not in clean, f"sanitiser keeps only p/b/i/u/span/br ({clean})")

# --- review fixes: selection sync, real Discard, whitespace, sanitise on load ---------------------------------------
from PySide6.QtGui import QTextDocument  # noqa: E402
from gui.notes_html import load_html, plain_text  # noqa: E402
for sample in ("a    b", "  lead", "x\ty", "a\n\nb", "a\n", "", "line1\n\n  indented\n\tdeeper"):
    d1 = QTextDocument(); d1.setPlainText(sample)
    h1 = document_to_html(d1)
    d2 = QTextDocument(); load_html(d2, h1)
    check(plain_text(d2) == sample and document_to_html(d2) == h1, f"note text round-trips exactly: {sample!r}")

n_a = notes._store.create("Note A", "<p>alpha</p>", "alpha")
n_b = notes._store.create("Note B", "<p>bravo</p>", "bravo")
notes._populate()
notes._select_in_list(n_a.id)
notes._load(notes._store.get(n_a.id))
notes._body.setPlainText("alpha EDITED")
answer_exec(QMessageBox.StandardButton.Save)
row_b = next(r for r in range(notes._list.count()) if notes._list.item(r).data(NOTE_ROLE).id == n_b.id)
notes._list.setCurrentRow(row_b)
shown_id = notes._list.currentItem().data(NOTE_ROLE).id
check(notes.current_id() == n_b.id and shown_id == n_b.id and notes._title.text() == "Note B",
      "Save in the prompt: list highlight and editor show the same (new) note")
check(notes._store.get(n_a.id).body_text == "alpha EDITED", "…and the saved edit of the old note was stored")

# a real Discard: leaving the page reverts the editor, so coming back shows the stored text, not the discarded edit
notes._body.setPlainText("DISCARD ME")
check(notes._dirty, "edit marks dirty")
answer_exec(QMessageBox.StandardButton.Discard)
win.navigate("history")
check(win.stack.currentWidget() is win.history and not notes._dirty and notes._body.toPlainText() == "bravo",
      f"Discard really reverts the editor ({notes._body.toPlainText()!r})")
win.navigate("notes")
check(not notes._dirty and notes._body.toPlainText() == "bravo", "coming back to Notes shows the stored note, no stale guard")
# discarding a blank draft while leaving shows a note again instead of a lingering blank editor
notes.new_note()
notes._title.setText("draft only")
answer_exec(QMessageBox.StandardButton.Discard)
win.navigate("history")
win.navigate("notes")
check(notes.current_id() is not None and notes._title.text() != "draft only", "a discarded draft is gone; a stored note is shown")
# 'New note' after a Discard must stay blank (no deferred re-selection)
answer_exec(QMessageBox.StandardButton.Discard)
notes._body.setPlainText("dirty")
notes.new_note()
QTest.qWait(50)
check(notes.current_id() is None and notes._title.text() == "" and not notes._dirty, "New note after Discard stays a blank draft")
QMessageBox.exec = real_exec

# sanitise on load: a hand-edited note body cannot bring fonts / images / links into the editor
evil = notes._store.create("Evil", '<p style="font-size:44pt;font-family:Comic Sans MS"><img src="C:/x.png"><a href="http://evil">z</a>ok</p>', "ok")
notes._populate()
notes._select_in_list(evil.id)
notes._load(notes._store.get(evil.id))
loaded = document_to_html(notes._body.document())
check("img" not in loaded and "font" not in loaded and "href" not in loaded and "ok" in notes._body.toPlainText(),
      f"stored HTML is re-sanitised when a note is opened ({loaded})")
for n_ in list(notes._store.list()):
    notes._store.delete(n_.id)
notes._populate()
notes._select_first_or_empty()

# Corrupt notes file shows a banner instead of silently losing data
bad_dir = Path(tempfile.mkdtemp(prefix="asx_badnotes_"))
(bad_dir / "notes.json").write_text("not json at all", encoding="utf-8")
bad_page = NotesPage(NotesStore(bad_dir / "notes.json"))
check(not bad_page._banner.isHidden() and "notes.corrupt-" in bad_page._banner_text.text(), "corrupt notes file -> recovery banner")
# Unavailable (newer schema) -> the page explains instead of crashing
unav = NotesPage(None, "newer version")
check(unav._stack.currentWidget() is unav._unavailable and not unav._new_btn.isEnabled(), "unavailable store disables the page")

# ---- regressions found in review --------------------------------------------------------------------
# 1) page fades with animations ON: stop() on a finished/deleted animation used to raise
errors: list = []
sys.excepthook = lambda t, v, tb: errors.append(v)
anim.set_reduced_motion(False)
for key in ("history", "date_checker", "results", "new_run", "history", "results"):
    win.navigate(key)
    QTest.qWait(230)                 # longer than the 150 ms fade, so the animation is deleted
for key in ("results", "history", "new_run"):   # rapid navigation while a fade is still running
    win.navigate(key)
QTest.qWait(250)
check(not errors, f"animated navigation raises nothing ({errors[:1]})")
anim.set_reduced_motion(True)

# 2) date sort with pre-1970 dates (timestamp() raises OSError on Windows)
from datetime import datetime  # noqa: E402
from models import PDFEntry  # noqa: E402
old = make_demo_result(8)
old.entries[0].resolved_date = datetime(1899, 12, 30)
old.entries[1].resolved_date = datetime(1969, 12, 31)
win.results.show_result(old, animate=False)
try:
    view._table.sortByColumn(2, Qt.SortOrder.AscendingOrder)
    ok = True
except Exception as exc:  # noqa: BLE001
    ok = False
check(ok and not errors, "date sort handles pre-1970 dates")

# 3) typing an output path must not create folders
from gui import validation  # noqa: E402
probe_root = Path(tempfile.mkdtemp())
typed = probe_root / "D1" / "D2" / "D3"
page._output.setText(str(typed))
page._output.setText(str(typed) + "x")
check(not (probe_root / "D1").exists() and validation.output_dir_error(str(typed)) is None,
      "output validation is side-effect free and accepts a creatable path")
check(validation.output_dir_error(str(Path(sys.executable))) is not None, "a file path is rejected as output folder")

# 4) Enter must not start a run while busy
got.clear()
page.set_busy(True)
page._submit()
check(not got, "Enter/submit is ignored while busy")
page.set_busy(False)

win.close()                      # a clean shutdown must not crash
app.processEvents()
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
