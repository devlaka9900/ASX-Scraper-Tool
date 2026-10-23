"""Dev-only end-to-end test against a local HTTP server (no ASX access needed).

    .venv-build\\Scripts\\python.exe tools\\e2e_local.py

Covers: pipeline categories, run_summary/history, re-run without duplicates,
cancel (fast + no .part leftovers), date checker, and the Qt JobRunner signals.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["ASX_CHECKER_GUI"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"

WORK = Path(tempfile.mkdtemp(prefix="asx_e2e_"))
os.environ["ASX_CHECKER_LOG_DIR"] = str(WORK / "logs")

import fitz  # noqa: E402

FILES: dict[str, bytes] = {}


def _pdf(mod: str | None, pages: int = 2) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.set_metadata({"modDate": mod or "", "creationDate": mod or ""})
    data = doc.tobytes()
    doc.close()
    return data


FILES["a.pdf"] = _pdf("D:20250601120000")             # updated   (cutoff 2024-01-01)
FILES["b.pdf"] = _pdf("D:20230101120000")             # not updated
FILES["c.pdf"] = _pdf(None)                           # no date
FILES["e.pdf"] = b"<html>not a pdf</html>"            # unreadable -> no date
# d.pdf is linked but 404s -> download_error
SLOW_BYTES = _pdf("D:20250101000000", pages=1) + b"\0" * (3 * 1024 * 1024)

PORT = 0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_GET(self):
        if self.path == "/page":
            rows = "".join(
                f'<tr><td><a href="http://127.0.0.1:{PORT}/files/{n}">{n}</a></td><td>01/01/2025</td></tr>'
                for n in ("a.pdf", "b.pdf", "c.pdf", "d.pdf", "e.pdf"))
            self._send(200, f"<html><body><table><tr><th>Name</th><th>Upload Date</th></tr>{rows}</table></body></html>".encode(),
                       "text/html")
        elif self.path == "/slowpage":
            rows = "".join(
                f'<tr><td><a href="http://127.0.0.1:{PORT}/slow/s{i}.pdf">s{i}.pdf</a></td><td>01/01/2025</td></tr>'
                for i in range(12))
            self._send(200, f"<html><body><table><tr><th>Name</th><th>Upload Date</th></tr>{rows}</table></body></html>".encode(),
                       "text/html")
        elif self.path.startswith("/files/") and self.path.split("/")[-1] in FILES:
            self._send(200, FILES[self.path.split("/")[-1]], "application/pdf")
        elif self.path.startswith("/slow/"):
            self.send_response(200)
            self.send_header("Content-Length", str(len(SLOW_BYTES)))
            self.end_headers()
            try:
                for i in range(0, len(SLOW_BYTES), 64 * 1024):
                    self.wfile.write(SLOW_BYTES[i:i + 64 * 1024])
                    time.sleep(0.08)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
        else:
            self._send(404, b"nope", "text/plain")

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
PORT = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{PORT}"

from core.pipeline import RunRequest, run_pipeline  # noqa: E402
from core.summary import load_run, scan_history  # noqa: E402
from core import datecheck  # noqa: E402

fails: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        fails.append(msg)


out_root = WORK / "output"
cutoff = datetime(2024, 1, 1)

# ---- 1. normal run ----------------------------------------------------------------
req = RunRequest("e2e-1", f"{BASE}/page", cutoff, out_root)
events: list[tuple] = []
res = run_pipeline(req, progress_cb=lambda *a: events.append(a))
st = res.stats
check(res.meta.status == "completed", f"run completed (status={res.meta.status} err={res.meta.error})")
check((st["updated"], st["not_updated"], st["no_date"], st["download_error"]) == (1, 1, 2, 1),
      f"categories 1/1/2/1 -> {(st['updated'], st['not_updated'], st['no_date'], st['download_error'])}")
check(st["updated_pages"] == 2 and st["total_pages"] >= 4, f"page counts ({st['updated_pages']}/{st['total_pages']})")
stages = [e[0] for e in events]
check(all(s in stages for s in ("scrape", "folders", "download", "analyse", "report")), "all five stages reported progress")
check(any(str(e[3]).startswith("✗ ") for e in events if e[0] == "download"), "failed download flagged with ✗ prefix")
base = out_root / "e2e-1"
check((base / "run_summary.json").exists() and any((base / "history").glob("run_*.json")), "summary + history archive written")
check((base / "report.xlsx").exists() and (base / "analysis_report.md").exists(), "reports written")
check(sorted(p.name for p in (base / "Updated_Books").glob("*.pdf")) == ["a.pdf"], "Updated_Books holds only a.pdf")
check(not list(base.rglob("*.part")), "no .part files left")

back = load_run(base / "run_summary.json")
check(back.stats["updated"] == 1 and back.entries[0].local_path is not None
      and back.entries[0].local_path.exists(), "load_run restores entries with usable local paths")
hist = scan_history([out_root])
check(len(hist) == 1 and hist[0].meta.project_id == "e2e-1" and hist[0].base_exists, "scan_history lists the run")

# ---- 2. re-run: no _1 duplicates ---------------------------------------------------
time.sleep(1.1)   # distinct run_id
res2 = run_pipeline(req)
names = sorted(p.name for p in (base / "Updated_Books").glob("*.pdf")) + sorted(p.name for p in (base / "Date_Not_Found").glob("*.pdf"))
check(res2.meta.status == "completed" and not any("_1" in n for n in names), f"re-run leaves no duplicates ({names})")
check(len(scan_history([out_root])) == 2, "history now has 2 runs")

# ---- 3. date check -------------------------------------------------------------------
chk = datecheck.check_folder(base, datetime(2020, 1, 1))
check(chk.stats["updated"] == 2 and chk.stats["not_updated"] == 0, f"date check @2020: both dated PDFs updated ({chk.stats['updated']}/{chk.stats['not_updated']})")
check(any(e.category == "download_error" for e in chk.entries), "date check keeps the missing d.pdf as an error row")
check(chk.entries[0].url.startswith("http"), "date check recovered URLs from the earlier summary")
exp = datecheck.export_reports(chk)
check((exp / "report.xlsx").exists(), "date check export writes reports into date_checks/")

# ---- 4. cancel -------------------------------------------------------------------------
cancel = threading.Event()
t0 = time.monotonic()
threading.Timer(0.6, cancel.set).start()
res3 = run_pipeline(RunRequest("e2e-cancel", f"{BASE}/slowpage", cutoff, out_root), cancel=cancel)
dt = time.monotonic() - t0
cbase = out_root / "e2e-cancel"
check(res3.meta.status == "cancelled", f"cancelled status ({res3.meta.status})")
check(dt < 5, f"cancel returned quickly ({dt:.1f}s)")
check(not list(cbase.rglob("*.part")), "cancel left no .part files")
check(not (cbase / "analysis_report.md").exists(), "cancel skipped report writing")
check(len(scan_history([out_root])) == 3, "cancelled run is in history")

# ---- 5. failure paths -------------------------------------------------------------------
bad = run_pipeline(RunRequest("e2e-bad", "http://127.0.0.1:1/nothing", cutoff, out_root))
check(bad.meta.status == "failed" and bad.meta.error, f"unreachable URL -> failed with message ({(bad.meta.error or '')[:60]}...)")

# ---- 6. Qt JobRunner ---------------------------------------------------------------------
from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from gui.workers import JobRunner  # noqa: E402

app = QApplication([])
runner = JobRunner()
got = {"started": [], "progress": 0, "log": [], "completed": [], "failed": [], "busy": []}
runner.started.connect(got["started"].append)
runner.progress.connect(lambda *a: got.__setitem__("progress", got["progress"] + 1))
runner.log.connect(lambda lvl, msg: got["log"].append((lvl, msg)))
runner.completed.connect(lambda k, r: got["completed"].append((k, r)))
runner.failed.connect(lambda k, m: got["failed"].append((k, m)))
runner.busyChanged.connect(got["busy"].append)


def wait_until(pred, timeout=30):
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(20)
    deadline = time.monotonic() + timeout

    def tick():
        if pred() or time.monotonic() > deadline:
            loop.quit()
    poll.timeout.connect(tick)
    poll.start()
    loop.exec()
    poll.stop()
    return pred()


runner.start_run(RunRequest("e2e-qt", f"{BASE}/page", cutoff, out_root))
check(runner.busy, "runner busy right after start")
ok = wait_until(lambda: got["completed"] and got["busy"][-1:] == [False])
check(ok, "JobRunner: completed + busy->False")
check(got["started"] == ["run"] and got["progress"] > 5, f"JobRunner: started + {got['progress']} progress signals")
check(any("Fetching page" in m or "Found" in m for _l, m in got["log"]), f"JobRunner: live log relayed ({len(got['log'])} lines)")
check(got["completed"][0][1].meta.status == "completed", "JobRunner: result is a completed RunResult")

runner.start_datecheck(out_root / "e2e-qt", datetime(2020, 1, 1))
ok = wait_until(lambda: len(got["completed"]) == 2 and got["busy"][-1:] == [False])
check(ok and got["completed"][1][0] == "datecheck" and got["completed"][1][1].stats["updated"] == 2, "JobRunner: date check job")

runner.start_run(RunRequest("e2e-qt2", f"{BASE}/slowpage", cutoff, out_root))
QTimer.singleShot(500, runner.cancel)
ok = wait_until(lambda: len(got["completed"]) == 3 and got["busy"][-1:] == [False])
check(ok and got["completed"][2][1].meta.status == "cancelled", "JobRunner: cancel -> cancelled result")

# ---- 7. regressions found in review ---------------------------------------------------------------
import json  # noqa: E402
from core.summary import _safe_join, SummaryError  # noqa: E402

b = out_root / "e2e-1"
check(_safe_join(b, "downloads/rules/a.pdf") == b / "downloads/rules/a.pdf", "safe_join keeps normal relative paths")
for bad in ("..\\..\\x.pdf", "\\Windows\\x.exe", "C:\\x.pdf", "C:x.pdf", "../x.pdf", "/etc/x", "a/../../x.pdf", "", None):
    check(_safe_join(b, bad) is None, f"safe_join rejects {bad!r}")

# a project literally called "history": summary beside it, archive inside history/
hres = run_pipeline(RunRequest("history", f"{BASE}/page", cutoff, out_root))
hbase = out_root / "history"
loaded = load_run(hbase / "run_summary.json")
check(loaded.base_dir == hbase and loaded.entries[0].local_path is not None and loaded.entries[0].local_path.exists(),
      "project named 'history': run_summary.json resolves its own folder")
arch = next((hbase / "history").glob("run_*.json"))
check(load_run(arch).base_dir == hbase, "project named 'history': archive resolves its own folder")

# malformed history files must not hide the good ones
good_before = len(scan_history([out_root]))
bad_dir = out_root / "broken" / "history"
bad_dir.mkdir(parents=True)
for i, payload in enumerate(['{"schema_version": null}', '{"schema_version": "x"}', '{"meta": []}',
                             '{"meta": {"started_at": null}, "stats": 5}', "not json", "[]"]):
    (bad_dir / f"run_bad{i}.json").write_text(payload, encoding="utf-8")
try:
    items = scan_history([out_root])
    check(len([i for i in items if i.meta.project_id]) >= good_before, f"scan_history survives malformed files ({len(items)} items)")
except Exception as exc:  # noqa: BLE001
    check(False, f"scan_history raised {type(exc).__name__}: {exc}")

# ---- 8. JobRunner ordering + failure messages never throttled --------------------------------------
order: list[str] = []
r2 = JobRunner()
r2.started.connect(lambda k: order.append("started"))
r2.busyChanged.connect(lambda b_: order.append(f"busy={b_}"))
r2.start_datecheck(out_root / "e2e-qt", datetime(2020, 1, 1))
wait_until(lambda: order[-1:] == ["busy=False"])
check(order[:2] == ["started", "busy=True"], f"started is emitted before busy=True ({order[:2]})")

from gui.workers import _Worker  # noqa: E402
w = _Worker(lambda cb, ev: None, threading.Event())
seen: list[str] = []
w.progress.connect(lambda s, d, t, m: seen.append(m))
for i in range(50):
    w._on_progress("download", i + 1, 500, "✗ fail%d" % i)      # burst, far inside one 50 ms window
check(len(seen) == 50, f"all failed-file messages are forwarded ({len(seen)}/50)")

print()
print("work dir:", WORK)
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
server.shutdown()
sys.exit(1 if fails else 0)
