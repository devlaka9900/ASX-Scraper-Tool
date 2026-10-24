"""`--selftest`: headless smoke test used as the build gate for the frozen exe.

Imports every heavy dependency, does a PDF/xlsx/summary round trip and renders
every page in both themes offscreen. Exit code 0 = healthy.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path


def _blank(image) -> bool:
    """True when a grabbed image has (almost) a single colour."""
    seen = set()
    step_x, step_y = max(1, image.width() // 40), max(1, image.height() // 40)
    for y in range(0, image.height(), step_y):
        for x in range(0, image.width(), step_x):
            seen.add(image.pixel(x, y))
            if len(seen) > 3:
                return False
    return True


def run(out_dir: Path | None = None) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if sys.platform == "win32":
        # the offscreen platform has no font database of its own -> text renders as boxes
        os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
    out = Path(out_dir or os.environ.get("ASX_SELFTEST_OUT") or tempfile.mkdtemp(prefix="asx_selftest_"))
    out.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def step(name: str, fn):
        try:
            detail = fn()
            lines.append(f"PASS  {name}" + (f"  {detail}" if detail else ""))
        except Exception:
            lines.append(f"FAIL  {name}\n{traceback.format_exc()}")
            raise

    ok = True
    try:
        def imports():
            import bs4, certifi, dateutil, fitz, lxml.etree, openpyxl, requests, rich, tqdm  # noqa: F401
            import PySide6
            if not Path(certifi.where()).exists():
                raise RuntimeError("certifi bundle missing: " + certifi.where())
            return f"PySide6 {PySide6.__version__}, PyMuPDF {fitz.__doc__.splitlines()[0][:40]}"

        def pdf_roundtrip():
            import fitz
            doc = fitz.open()
            doc.new_page()
            doc.set_metadata({"modDate": "D:20250101120000"})
            path = out / "probe.pdf"
            doc.save(str(path))
            doc.close()
            from analyzer.date_checker import read_pdf_info
            from models import PDFEntry
            e = PDFEntry(name="probe.pdf", url="", section="rules", local_path=path)
            read_pdf_info(e)
            if e.page_count != 1 or e.resolved_date is None:
                raise RuntimeError(f"unexpected read: pages={e.page_count} date={e.resolved_date}")

        def scrape_parse():
            # exercises bs4 + the lxml parser + dateutil exactly as the real scraper does
            from scraper.page_scraper import _parse_entries
            html = ('<html><body><div data-cmp-hook-tabs="tab">Rules</div>'
                    '<div data-cmp-hook-tabs="tabpanel"><table><tr><th>Name</th><th>Upload Date</th></tr>'
                    '<tr><td><a href="/docs/a.pdf">Doc A</a></td><td>15/03/2024</td></tr></table></div>'
                    '</body></html>')
            entries = _parse_entries(html, "https://example.test/page")
            if len(entries) != 1 or entries[0].section != "rules" or entries[0].upload_date is None \
                    or entries[0].upload_date.month != 3:
                raise RuntimeError(f"unexpected parse result: {entries}")

        def live_network():
            # optional (not part of the build gate): ASX_SELFTEST_URL=<asx page> proves TLS + scrape in the exe
            url = os.environ.get("ASX_SELFTEST_URL")
            if not url:
                return "skipped (set ASX_SELFTEST_URL to enable)"
            from scraper.page_scraper import scrape_pdf_links
            found = scrape_pdf_links(url)
            if not found:
                raise RuntimeError("no PDF links found on " + url)
            return f"{len(found)} PDF links from {url}"

        def reports_roundtrip():
            from core.summary import load_run, write_summary
            from gui.demo import make_demo_result
            from reporter.excel_report import write_excel_report
            from reporter.report_generator import write_reports
            base = out / "proj"
            base.mkdir(exist_ok=True)
            res = make_demo_result(60, base_dir=base)
            write_summary(res)
            back = load_run(base / "run_summary.json")
            if back.stats["total"] != res.stats["total"] or back.stats["updated"] != res.stats["updated"]:
                raise RuntimeError("summary round trip mismatch")
            dirs = {"base": base}
            write_reports(res.entries, dirs, "demo", res.meta.url, res.cutoff_date)
            write_excel_report(res.entries, dirs, "demo", res.meta.url, res.cutoff_date)
            for name in ("analysis_report.md", "updated_page_count.md", "report.xlsx"):
                if not (base / name).exists():
                    raise RuntimeError(f"missing {name}")

        def render_pages():
            from PySide6.QtCore import QSettings
            from PySide6.QtWidgets import QApplication
            from gui import theme
            from gui.demo import make_demo_result
            from gui.main_window import MainWindow
            from gui.settings import Settings

            app = QApplication.instance() or QApplication([sys.argv[0]])
            app.setStyle("Fusion")
            settings = Settings(QSettings(str(out / "selftest.ini"), QSettings.Format.IniFormat))
            shots = []
            from core.notes import NotesStore
            seeded = NotesStore(out / "selftest_notes.json")
            for title, html, text in (
                ("Release checklist", '<p><b>Before shipping</b></p><p>Run the <i>self-test</i>, then check the '
                 '<span style="color:#e5484d">crash log</span>.</p>', "Before shipping\nRun the self-test, then check the crash log."),
                ("Cutoff rules", "<p>Use the latest <u>Waivers</u> document when the cutoff is unknown.</p>",
                 "Use the latest Waivers document when the cutoff is unknown."),
            ):
                seeded.create(title, html, text)
            for mode in ("dark", "light"):
                theme.apply(app, mode)
                win = MainWindow(settings, notes_path=out / "selftest_notes.json")
                w, h = (int(v) for v in os.environ.get("ASX_SELFTEST_SIZE", "1280x820").split("x"))
                win.resize(w, h)
                win.show()
                demo = make_demo_result(240)
                win.results.show_result(demo, animate=False)
                win.date_checker.show_result(demo)
                win.history.refresh()
                pages = {
                    "new_run": win.new_run, "run": win.run_view, "results": win.results,
                    "history": win.history, "date_checker": win.date_checker,
                    "notes": win.notes, "agent": win.agent,
                }
                for name, page in pages.items():
                    win.stack.setCurrentWidget(page)
                    app.processEvents()
                    image = win.grab().toImage()
                    if _blank(image):
                        raise RuntimeError(f"{name} ({mode}) rendered blank")
                    path = out / f"{name}_{mode}.png"
                    image.save(str(path))
                    shots.append(path.name)
                    if name == "results":      # also capture the table at the bottom of the page
                        win.results.view.scroll_to_bottom()
                        app.processEvents()
                        win.grab().toImage().save(str(out / f"results_table_{mode}.png"))
                        shots.append(f"results_table_{mode}.png")
                win.close()
            return f"{len(shots)} screenshots in {out}"

        def notes_roundtrip():
            import re
            from PySide6.QtWidgets import QApplication
            from core.notes import NotesStore
            from gui.notes_html import sanitize_html
            _app = QApplication.instance() or QApplication([sys.argv[0]])
            store = NotesStore(out / "roundtrip_notes.json")
            n = store.create("Heading", "<p><b>x</b></p>", "x")
            store.update(n.id, body_html="<p>y</p>", body_text="y")
            if NotesStore(out / "roundtrip_notes.json").get(n.id).body_text != "y":
                raise RuntimeError("notes did not persist")
            if len(store.search("heading")) != 1 or not store.delete(n.id) or len(store):
                raise RuntimeError("notes search/delete failed")
            clean = sanitize_html('<script>x</script><p style="font-size:30pt">a <b>b</b><img src="c:/x.png"></p>')
            tags = set(re.findall(r"</?(\w+)", clean))
            if not tags <= {"p", "b", "i", "u", "span", "br"} or "font-size" in clean:
                raise RuntimeError(f"sanitizer let something through: {clean}")

        for name, fn in (("imports", imports), ("pdf round trip", pdf_roundtrip),
                         ("scraper parse (bs4 + lxml + dateutil)", scrape_parse),
                         ("live network scrape", live_network),
                         ("reports + summary round trip", reports_roundtrip),
                         ("notes store + sanitizer", notes_roundtrip),
                         ("render pages (both themes)", render_pages)):
            step(name, fn)
    except Exception:
        ok = False

    lines.append("RESULT  " + ("OK" if ok else "FAILED"))
    text = "\n".join(lines)
    try:
        (out / "selftest.log").write_text(text, encoding="utf-8")
    except OSError:
        pass
    print(text)
    return 0 if ok else 1
