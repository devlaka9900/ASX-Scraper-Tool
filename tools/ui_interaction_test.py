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

from core.paths import data_dir, documents_dir  # noqa: E402
from core.version import APP_NAME  # noqa: E402
from PySide6.QtWidgets import QLabel as _QLabel  # noqa: E402
check(APP_NAME == "ASX Reg Data" and win.windowTitle() == "ASX Reg Data", f"window title / APP_NAME is {win.windowTitle()!r}")
_real_lad = os.environ.get("LOCALAPPDATA")
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="asx_lad_")          # data_dir() creates the folder: keep it in temp
try:
    _dd_name = data_dir().name
finally:
    if _real_lad is None:
        os.environ.pop("LOCALAPPDATA", None)
    else:
        os.environ["LOCALAPPDATA"] = _real_lad
check(_dd_name == "ASX Reg Data" and documents_dir().name == "ASX Reg Data", "data and documents folders are named 'ASX Reg Data'")
check(any(l.text() == APP_NAME for l in win.sidebar.findChildren(_QLabel)), "sidebar shows the app name")

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
page._confirm = lambda req: True            # the real confirm dialog is modal; it is tested separately below
QTest.mouseClick(page._start, Qt.MouseButton.LeftButton)
check(len(got) == 1 and got[0].project_id == "My-Project_1" and got[0].url.endswith("/page")
      and got[0].cutoff == datetime(2024, 1, 15), "Start emits a RunRequest with the typed cutoff")
check(settings.last_project_id == "My-Project_1", "inputs remembered in settings")

# ---- v1.3.0: New Run confirmation dialog ----------------------------------------------------------------------
from PySide6.QtWidgets import QDialog  # noqa: E402
from core.pipeline import RunRequest as _RR  # noqa: E402
from gui.pages.new_run import RunConfirmDialog  # noqa: E402
from gui.widgets.common import ElidedLabel as _EL  # noqa: E402

seen: list = []
page._confirm = lambda req: (seen.append(req) or False)          # user picks "Back to edit"
got.clear()
page._project.setText("BACK-1")
page._url.setText("https://www.asx.com.au/back")
fields_before = (page._project.text(), page._url.text(), page._cutoff.text(), page._output.text(), page._startpoint.text())
out_before, last_before = settings.output_dir, settings.last_project_id
page._submit()
check(len(seen) == 1 and not got, "Back to edit: the confirmation was shown but startRequested is NOT emitted")
check(settings.output_dir == out_before and settings.last_project_id == last_before == "My-Project_1",
      "Back to edit: settings (output dir, last DocumentId) are unchanged")
check((page._project.text(), page._url.text(), page._cutoff.text(), page._output.text(), page._startpoint.text()) == fields_before
      and page._start.isEnabled(), "Back to edit: the form keeps its text and Start stays enabled")

seen.clear()
page._confirm = lambda req: (seen.append(req) or True)           # user picks "Confirm & start"
page._submit()
check(len(seen) == 1 and len(got) == 1 and got[0] is seen[0] and got[0].project_id == "BACK-1",
      "Confirm: _confirm called once with the request, then startRequested is emitted with it")
check(settings.last_project_id == "BACK-1", "Confirm: inputs are remembered only after confirming")
got.clear()

# the real dialog: contents + buttons
req_full = _RR("DOC-Z", "https://www.asx.com.au/some/very/long/page", datetime(2025, 3, 7), Path(tempfile.gettempdir()),
               overwrite_downloads=True, startpoint="Chapter 5")
dlg = RunConfirmDialog(req_full)
def dval(d, name):
    w = next((x for x in d.findChildren(_EL) if x.accessibleName() == name), None)
    return w.full_text() if w is not None else None
check(dlg.windowTitle() == "Confirm run" and dlg.isModal(), "confirm dialog is a modal 'Confirm run' window")
check(dval(dlg, "DocumentId value") == "DOC-Z" and dval(dlg, "Startpoint value") == "Chapter 5"
      and dval(dlg, "Page URL value") == req_full.url and dval(dlg, "Cutoff date value") == "2025-03-07"
      and dval(dlg, "Output folder value") == str(req_full.output_root) and dval(dlg, "Re-download value") == "Yes",
      "confirm dialog shows DocumentId, Startpoint, Page URL, Cutoff date, Output folder, Re-download")
req_min = _RR("DOC-Y", "https://x", datetime(2025, 3, 7), Path("."), overwrite_downloads=False, startpoint="")
dlg2 = RunConfirmDialog(req_min)
check(dval(dlg2, "Startpoint value") == "—" and dval(dlg2, "Re-download value") == "No",
      "confirm dialog shows '—' for an empty Startpoint and 'No' for Re-download off")
btns = {b.text(): b for b in dlg2.findChildren(QPushButton)}
check({"Back to edit", "Confirm and start"} <= set(btns) and dlg2._confirm_btn.isDefault(),
      "confirm dialog has 'Back to edit' and a default 'Confirm and start' button")
btns["Back to edit"].click()
check(dlg2.result() == QDialog.DialogCode.Rejected, "clicking 'Back to edit' rejects the dialog")
dlg3 = RunConfirmDialog(req_min)
dlg3._confirm_btn.click()
check(dlg3.result() == QDialog.DialogCode.Accepted, "clicking 'Confirm & start' accepts the dialog")

# NewRunPage._confirm wires the dialog result through (patched exec, no real modal loop)
real_dlg_exec = RunConfirmDialog.exec
page2_ = type(page)  # the unbound method under test
for outcome, expect in ((QDialog.DialogCode.Accepted, True), (QDialog.DialogCode.Rejected, False)):
    RunConfirmDialog.exec = lambda self, o=outcome: o
    check(page2_._confirm(page, req_min) is expect, f"_confirm returns {expect} when the dialog is {outcome.name}")
RunConfirmDialog.exec = real_dlg_exec
page._confirm = lambda req: True                                 # keep stubbing for the flows below

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

# Results page: Close results button + Esc return to the empty state
rp = win.results
rp.show_result(make_demo_result(30), animate=False)
win.navigate("results")
app.processEvents()
check(rp.has_result() and rp._stack.currentWidget() is rp.view and rp._close_btn.isVisible(),
      "Results shows a Close results button with a result open")
QTest.mouseClick(rp._close_btn, Qt.MouseButton.LeftButton)
check(not rp.has_result() and rp._stack.currentWidget() is rp._empty and rp.view.result is None
      and rp.view._proxy.rowCount() == 0, "Close results clears the result and shows the empty state")
rp.show_result(make_demo_result(30), animate=False)
check(rp._stack.currentWidget() is rp.view and rp.view._proxy.rowCount() == 30, "a new result after closing shows the result view again")
win.activateWindow()
app.processEvents()
QTest.keyClick(win, Qt.Key.Key_Escape)
check(rp._stack.currentWidget() is rp._empty and not rp.has_result(), "Esc closes the Results result view")
QTest.keyClick(win, Qt.Key.Key_Escape)
check(rp._stack.currentWidget() is rp._empty, "Esc on the empty Results state does nothing")
rp.show_result(make_demo_result(30), animate=False)
rp.view.search_box().setText("waiver")
rp.view.search_box().setFocus()
win.activateWindow()
app.processEvents()
QTest.keyClick(win, Qt.Key.Key_Escape)
check(rp._stack.currentWidget() is rp.view and rp.view.search_box().text() == "",
      "first Esc clears the Results search box without closing the result")
QTest.keyClick(win, Qt.Key.Key_Escape)
check(rp._stack.currentWidget() is rp._empty, "second Esc closes the Results result")
rp.show_result(make_demo_result(240), animate=False)      # restore what the following checks expect

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
check("Pages updated" in heads and "Total pages" in heads and heads.index("Pages updated") == heads.index("PDFs") + 1
      and heads.index("Total pages") == heads.index("Pages updated") + 1, "History has 'Pages updated' and 'Total pages' columns after PDFs")
r_doc = {tbl.item(r, heads.index("DocumentId")).text(): r for r in range(tbl.rowCount())}
want = make_demo_result(12).stats
okc = all(tbl.item(r_doc[d], heads.index("Pages updated")).text() == f"{want['updated_pages']:,}"
          and tbl.item(r_doc[d], heads.index("Total pages")).text() == f"{want['total_pages']:,}" for d in ("DOC-A", "DOC-B"))
check(okc and want["total_pages"] > 0, f"History page-count cells match the stored stats ({want['updated_pages']:,} / {want['total_pages']:,})")
align = tbl.item(r_doc["DOC-A"], heads.index("Total pages")).textAlignment()
check(bool(align & int(Qt.AlignmentFlag.AlignRight)), "page-count cells are right-aligned")
# older history files have no page counts -> 0
import json as _json  # noqa: E402
old_root = Path(tempfile.mkdtemp(prefix="asx_hist_old_"))
r_old = make_demo_result(5, base_dir=old_root / "DOC-OLD")
r_old.meta.project_id, r_old.meta.run_id, r_old.meta.started_at = "DOC-OLD", "20261003_100000", "2026-10-03T10:00:00"
(old_root / "DOC-OLD").mkdir(parents=True)
write_summary(r_old)
for jf in (old_root / "DOC-OLD").rglob("run_*.json"):
    d_ = _json.loads(jf.read_text(encoding="utf-8"))
    d_["stats"].pop("updated_pages", None)
    d_["stats"].pop("total_pages", None)
    jf.write_text(_json.dumps(d_), encoding="utf-8")
settings.add_history_root(old_root)
win.history.refresh()
r_doc = {tbl.item(r, heads.index("DocumentId")).text(): r for r in range(tbl.rowCount())}
check("DOC-OLD" in r_doc and tbl.item(r_doc["DOC-OLD"], heads.index("Pages updated")).text() == "0"
      and tbl.item(r_doc["DOC-OLD"], heads.index("Total pages")).text() == "0", "a history file without page counts shows 0 / 0")
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

# ---- Notes: list page, read-only viewer, editor ---------------------------------------------------------------------
from gui.notes_html import document_to_html, sanitize_html  # noqa: E402
from gui.pages.notes import NOTE_ROLE, NoteViewDialog  # noqa: E402
notes = win.notes
check(notes.current_id() is None and notes._stack.currentWidget() is notes._list_page
      and notes._list_stack.currentWidget() is notes._empty and notes._empty_title.text() == "No notes yet",
      "Notes starts on the list page with the 'No notes yet' empty state")

real_exec, real_question = QMessageBox.exec, QMessageBox.question
def answer_exec(button):
    QMessageBox.exec = lambda self: button
def answer_question(button):
    QMessageBox.question = staticmethod(lambda *a, **k: button)

# the viewer is modal: stub exec() so it records the dialog and reports the button the "user" pressed
real_view_exec = NoteViewDialog.exec
viewers: list = []
def answer_viewer(action):
    def fake(self, a=action):
        viewers.append(self)
        self.action = a
        return 1 if a else 0
    NoteViewDialog.exec = fake

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
check(notes.save() is True and not notes._dirty and notes._stack.currentWidget() is notes._editor,
      "save() succeeds and stays on the editor")
n_id = notes.current_id()
saved = notes._store.get(n_id)
check(n_id and saved.title == "Alpha heading" and saved.body_text == "hello brave world", "note stored with heading and text")
check("<b>hello</b>" in saved.body_html and "<i>" in saved.body_html and "<u>" in saved.body_html
      and 'color:#e5484d' in saved.body_html, f"bold / italic / underline / colour persisted: {saved.body_html}")
check(notes._list.count() == 1 and notes._count.text() == "1 note", "list shows the new note")

# Save button / Ctrl+S: save, then return to the list
notes._title.setText("Alpha heading!")
notes._save_btn.click()
check(notes._stack.currentWidget() is notes._list_page and notes.current_id() is None and not notes._dirty
      and notes._store.get(n_id).title == "Alpha heading!", "Save button saves and returns to the list")
notes._store.update(n_id, title="Alpha heading")
notes._populate()
notes.edit_note(n_id)
check(notes._stack.currentWidget() is notes._editor and not notes._dirty, "edit_note opens the stored note in the editor")
notes._save_and_close()
check(notes._stack.currentWidget() is notes._editor, "Save is a no-op while the note is clean")
notes._title.setText("Alpha shortcut")
notes._save_and_close()                                   # what Ctrl+S is wired to
check(notes._stack.currentWidget() is notes._list_page and notes._store.get(n_id).title == "Alpha shortcut",
      "Ctrl+S path (_save_and_close) saves and returns to the list")
notes._store.update(n_id, title="Alpha heading")
notes._populate()

# Read: a fresh page over the same file lands on the list and renders the same formatting (round trip)
from core.notes import NotesStore  # noqa: E402
from gui.pages.notes import NotesPage  # noqa: E402
page2 = NotesPage(NotesStore(NOTES_PATH))
check(page2._stack.currentWidget() is page2._list_page and page2.current_id() is None and page2._list.count() == 1,
      "reopened Notes page lists the saved note and opens on the list")
page2.edit_note(n_id)
check(page2._title.text() == "Alpha heading" and document_to_html(page2._body.document()) == notes._store.get(n_id).body_html,
      "formatting round-trips unchanged through load -> serialise")

# Update (from the editor)
notes.edit_note(n_id)
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
ids = {n.title: n.id for n in notes._store.list()}

# Search (the search box lives on the list page)
notes.back_to_list()
notes._search.setText("brave")
QTest.qWait(220)
check(notes._list.count() == 1 and "of 3" in notes._count.text(), f"search filters the list ({notes._count.text()})")
notes._search.setText("zzzz-nothing")
QTest.qWait(220)
check(notes._list.count() == 0 and notes._list_stack.currentWidget() is notes._empty
      and notes._empty_title.text() == "No matching notes", "a search with no match shows 'No matching notes'")
notes._search.clear()
QTest.qWait(220)
check(notes._list.count() == 3 and notes._list_stack.currentWidget() is notes._list, "clearing the search restores the list")

# Viewer: a click opens a read-only dialog and does NOT switch to the editor
row_alpha = next(r for r in range(notes._list.count()) if notes._list.item(r).data(NOTE_ROLE).id == n_id)
answer_viewer(None)                                       # user presses Close
viewers.clear()
notes._list.itemClicked.emit(notes._list.item(row_alpha))
check(len(viewers) == 1 and viewers[0]._title.text() == "Alpha renamed" and viewers[0]._body.isReadOnly()
      and notes._stack.currentWidget() is notes._list_page and notes.current_id() is None and not notes._viewing,
      "clicking a note opens the read-only viewer and stays on the list")
viewers.clear()
notes._list.itemActivated.emit(notes._list.item(row_alpha))
check(len(viewers) == 1, "Enter (itemActivated) also opens the viewer")
viewers.clear()
notes._viewing = True
notes.view_note(n_id)
notes._viewing = False
check(not viewers, "a second viewer is not opened while one is already open")
dlg_n = NoteViewDialog(notes._store.get(n_id))
check({b.text() for b in dlg_n.findChildren(QPushButton)} >= {"Edit", "Close", "Delete"}
      and "Created" in dlg_n._meta.text() and "Updated" in dlg_n._meta.text(),
      "viewer has Edit / Delete / Close and shows created / updated times")
check(dlg_n.action is None, "viewer action is None until a button is used")
dlg_n._close_btn.click()
check(dlg_n.action is None, "viewer Close leaves action as None")
dlg_n._edit_btn.click()
check(dlg_n.action == "edit", "viewer Edit sets action 'edit'")
hostile_note = notes._store.create(
    "Hostile", '<p style="font-size:44pt;font-family:Comic Sans MS"><img src="C:/x.png"><a href="http://evil">z</a>ok</p>', "ok")
dlg_h = NoteViewDialog(hostile_note)
shown = document_to_html(dlg_h._body.document())
check(dlg_h._body.isReadOnly() and "img" not in shown and "href" not in shown and "font" not in shown
      and "ok" in dlg_h._body.toPlainText(), f"viewer body is read-only and sanitised ({shown})")
notes._store.delete(hostile_note.id)
notes._populate()
# viewer Edit -> editor
answer_viewer("edit")
notes.view_note(n_id)
check(notes._stack.currentWidget() is notes._editor and notes.current_id() == n_id and notes._title.text() == "Alpha renamed",
      "viewer Edit opens that note in the editor")
# viewer Delete -> confirmation -> removed, still on the list
notes.back_to_list()
answer_viewer("delete")
answer_question(QMessageBox.StandardButton.No)
notes.view_note(ids["Gamma"])
check(notes._store.get(ids["Gamma"]) is not None and len(notes._store) == 3, "viewer Delete answered No keeps the note")
answer_question(QMessageBox.StandardButton.Yes)
notes.view_note(ids["Gamma"])
check(notes._store.get(ids["Gamma"]) is None and len(notes._store) == 2 and notes._list.count() == 2
      and notes._stack.currentWidget() is notes._list_page, "viewer Delete answered Yes removes the note and stays on the list")
g = notes._store.create("Gamma", "<p>third</p>", "third")
ids["Gamma"] = g.id
notes._populate()
NoteViewDialog.exec = real_view_exec

# Back to notes / switching notes with unsaved edits asks first
notes.edit_note(ids["Gamma"])
notes._body.setPlainText("dirty edit")
answer_exec(QMessageBox.StandardButton.Cancel)
notes.back_to_list()
check(notes._stack.currentWidget() is notes._editor and notes._dirty and notes.current_id() == ids["Gamma"],
      "Back to notes is blocked on Cancel (edits kept)")
answer_exec(QMessageBox.StandardButton.Save)
notes.back_to_list()
check(notes._stack.currentWidget() is notes._list_page and not notes._dirty and notes.current_id() is None
      and notes._store.get(ids["Gamma"]).body_text == "dirty edit", "Back to notes with Save saves, then shows the list")
notes.edit_note(ids["Gamma"])
notes._body.setPlainText("dirty again")
answer_exec(QMessageBox.StandardButton.Discard)
notes.back_to_list()
check(notes._stack.currentWidget() is notes._list_page and not notes._dirty
      and notes._store.get(ids["Gamma"]).body_text == "dirty edit", "Back to notes with Discard drops the edits and shows the list")
notes.edit_note(ids["Gamma"])
cur_id = notes.current_id()
notes._body.setPlainText("dirty edit 2")
answer_exec(QMessageBox.StandardButton.Cancel)
notes.edit_note(n_id)
check(notes.current_id() == cur_id and notes._dirty, "opening another note while dirty is blocked on Cancel")
answer_exec(QMessageBox.StandardButton.Save)
notes.edit_note(n_id)
check(notes.current_id() == n_id and not notes._dirty and notes._store.get(cur_id).body_text == "dirty edit 2",
      "opening another note while dirty: Save in the prompt saves, then switches")

# Leaving the page / closing the window with unsaved edits
notes._body.setPlainText("unsaved again")
answer_exec(QMessageBox.StandardButton.Cancel)
win.navigate("history")
check(win.stack.currentWidget() is win.notes, "navigation away from dirty Notes is blocked on Cancel")
check(notes.can_leave() is False and notes._stack.currentWidget() is notes._editor,
      "can_leave is False on Cancel and stays on the editor")
closed = win.close()
check(closed is False and win.isVisible() and notes._dirty, "closing the window is blocked on Cancel (edits kept)")
answer_exec(QMessageBox.StandardButton.Discard)
win.navigate("history")
check(win.stack.currentWidget() is win.history and not notes._dirty and notes._stack.currentWidget() is notes._list_page
      and notes._store.get(n_id).body_text == "hello brave world", "Discard lets navigation continue and Notes returns to the list")
win.navigate("notes")
check(notes._stack.currentWidget() is notes._list_page, "coming back to Notes lands on the list")
notes.edit_note(n_id)
notes._body.setPlainText("saved by leaving")
answer_exec(QMessageBox.StandardButton.Save)
win.navigate("history")
check(win.stack.currentWidget() is win.history and notes._stack.currentWidget() is notes._list_page
      and notes._store.get(n_id).body_text == "saved by leaving", "Save in the leave prompt saves, then navigation continues")
notes._store.update(n_id, body_text="hello brave world")
win.navigate("notes")

# Delete from the editor (confirmation) returns to the list
notes.edit_note(n_id)
count_before = len(notes._store)
answer_question(QMessageBox.StandardButton.No)
notes.delete_note()
check(len(notes._store) == count_before and notes._stack.currentWidget() is notes._editor, "Delete answered No keeps the note")
answer_question(QMessageBox.StandardButton.Yes)
notes.delete_note()
check(len(notes._store) == count_before - 1 and notes._list.count() == count_before - 1
      and notes._stack.currentWidget() is notes._list_page and notes.current_id() is None,
      "Delete answered Yes removes it and returns to the list")
notes.new_note()
notes._title.setText("throwaway draft")
notes.delete_note()
check(notes._stack.currentWidget() is notes._list_page and len(notes._store) == count_before - 1,
      "Delete on an unsaved draft discards it and returns to the list")
for n_ in list(notes._store.list()):
    notes._delete_stored(n_.id)
check(len(notes._store) == 0 and notes._stack.currentWidget() is notes._list_page
      and notes._list_stack.currentWidget() is notes._empty and notes._empty_title.text() == "No notes yet",
      "deleting the last note shows the empty state on the list page")
QMessageBox.exec, QMessageBox.question = real_exec, real_question

# Empty note refuses to save; pasted rich text is flattened to plain text
notes.new_note()
answer_exec(QMessageBox.StandardButton.Ok)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
check(notes.save() is False and len(notes._store) == 0, "a completely empty note is not saved")
notes._save_and_close()
check(notes._stack.currentWidget() is notes._editor, "Save on an empty note stays on the editor")
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

# --- review fixes: real Discard, whitespace, sanitise on load ---------------------------------------------------------
from PySide6.QtGui import QTextDocument  # noqa: E402
from gui.notes_html import load_html, plain_text  # noqa: E402
for sample in ("a    b", "  lead", "x\ty", "a\n\nb", "a\n", "", "line1\n\n  indented\n\tdeeper"):
    d1 = QTextDocument(); d1.setPlainText(sample)
    h1 = document_to_html(d1)
    d2 = QTextDocument(); load_html(d2, h1)
    check(plain_text(d2) == sample and document_to_html(d2) == h1, f"note text round-trips exactly: {sample!r}")

n_a = notes._store.create("Note A", "<p>alpha</p>", "alpha")
n_b = notes._store.create("Note B", "<p>bravo</p>", "bravo")
notes._show_list()
notes._populate()
notes.edit_note(n_a.id)
notes._body.setPlainText("alpha EDITED")
answer_exec(QMessageBox.StandardButton.Save)
notes.edit_note(n_b.id)
check(notes.current_id() == n_b.id and notes._title.text() == "Note B" and notes._stack.currentWidget() is notes._editor,
      "Save in the prompt: the editor shows the newly opened note")
check(notes._store.get(n_a.id).body_text == "alpha EDITED", "…and the saved edit of the old note was stored")

# a real Discard: leaving the page drops the edit, so the stored note is untouched and Notes comes back on the list
notes._body.setPlainText("DISCARD ME")
check(notes._dirty, "edit marks dirty")
answer_exec(QMessageBox.StandardButton.Discard)
win.navigate("history")
check(win.stack.currentWidget() is win.history and not notes._dirty and notes._stack.currentWidget() is notes._list_page
      and notes._store.get(n_b.id).body_text == "bravo", "Discard really drops the edit (stored note unchanged, list shown)")
win.navigate("notes")
check(not notes._dirty and notes._stack.currentWidget() is notes._list_page and notes.current_id() is None,
      "coming back to Notes shows the list, no stale guard")
# discarding a blank draft while leaving shows the list instead of a lingering blank editor
notes.new_note()
notes._title.setText("draft only")
answer_exec(QMessageBox.StandardButton.Discard)
win.navigate("history")
win.navigate("notes")
check(notes.current_id() is None and notes._stack.currentWidget() is notes._list_page and notes._title.text() != "draft only"
      and len(notes._store) == 2, "a discarded draft is gone and the list is shown")
# 'New note' after a Discard must stay blank (no deferred re-selection)
notes.edit_note(n_b.id)
answer_exec(QMessageBox.StandardButton.Discard)
notes._body.setPlainText("dirty")
notes.new_note()
QTest.qWait(50)
check(notes.current_id() is None and notes._title.text() == "" and not notes._dirty, "New note after Discard stays a blank draft")
QMessageBox.exec = real_exec

# sanitise on load: a hand-edited note body cannot bring fonts / images / links into the editor
evil = notes._store.create(
    "Evil", '<p style="font-size:44pt;font-family:Comic Sans MS"><img src="C:/x.png"><a href="http://evil">z</a>ok</p>', "ok")
notes._populate()
notes.edit_note(evil.id)
loaded = document_to_html(notes._body.document())
check("img" not in loaded and "font" not in loaded and "href" not in loaded and "ok" in notes._body.toPlainText(),
      f"stored HTML is re-sanitised when a note is opened ({loaded})")
for n_ in list(notes._store.list()):
    notes._store.delete(n_.id)
notes._populate()
notes._show_list()
check(notes._stack.currentWidget() is notes._list_page and notes._list_stack.currentWidget() is notes._empty,
      "emptied store shows the empty list state")

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
