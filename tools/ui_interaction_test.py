"""Dev-only: drive the widgets headlessly and assert the interactive behaviour.

    .venv-build\\Scripts\\python.exe tools\\ui_interaction_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
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
win = MainWindow(settings)
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
check(page._start.isEnabled(), "Start enabled once ID, URL and folder are valid")
got = []
win.runner.start_run = lambda req: None     # do not launch a real job from the form test
page.startRequested.connect(got.append)
QTest.mouseClick(page._start, Qt.MouseButton.LeftButton)
check(len(got) == 1 and got[0].project_id == "My-Project_1" and got[0].url.endswith("/page"), "Start emits a RunRequest")
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
