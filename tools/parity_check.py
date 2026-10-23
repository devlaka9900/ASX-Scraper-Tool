"""Dev-only: run core.pipeline and the original CLI on the same URL/cutoff and
compare category counts.

    python tools/parity_check.py <project_id> <url> <YYYY-MM-DD> [work_dir]

Both runs write into work_dir (default: a fresh temp folder), never into the
real output/ folder.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LABELS = {
    "Updated": "updated",
    "Not Updated": "not_updated",
    "No Date Found": "no_date",
    "Download Error": "download_error",
}


def _cli_counts(report: Path) -> dict[str, int]:
    counts = dict.fromkeys(LABELS.values(), 0)
    for line in report.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or "|" not in line[2:]:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 2 or not cells[1].isdigit():
            continue
        name = re.sub(r"^[^A-Za-z]+", "", cells[0])        # drop the leading emoji
        if name in LABELS:                                 # exact match: "Updated" != "Not Updated"
            counts[LABELS[name]] = int(cells[1])
    return counts


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    project_id, url, cutoff_raw = sys.argv[1:4]
    work = Path(sys.argv[4]) if len(sys.argv) > 4 else Path(tempfile.mkdtemp(prefix="asx_parity_"))
    cutoff = datetime.strptime(cutoff_raw, "%Y-%m-%d")

    # 1) CLI in its own cwd (it writes ./output and ./logs)
    cli_cwd = work / "cli"
    cli_cwd.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(ROOT)}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "main.py")],
        input=f"{project_id}\n{url}\n{cutoff_raw}\n", text=True, encoding="utf-8",
        cwd=cli_cwd, env=env, capture_output=True,
    )
    if proc.returncode != 0:
        print("CLI failed:\n", proc.stdout[-2000:], proc.stderr[-2000:])
        return 1
    cli = _cli_counts(cli_cwd / "output" / project_id / "analysis_report.md")

    # 2) Pipeline against its own output root
    os.environ["ASX_CHECKER_LOG_DIR"] = str(work / "gui_logs")
    from core.pipeline import RunRequest, run_pipeline

    result = run_pipeline(RunRequest(project_id, url, cutoff, work / "gui_output"))
    if result.meta.status != "completed":
        print("Pipeline status:", result.meta.status, result.meta.error)
        return 1
    stats = result.stats
    gui = {k: stats[k] for k in LABELS.values()}

    print("work dir :", work)
    print("CLI      :", cli)
    print("pipeline :", gui)
    same = cli == gui
    print("PARITY OK" if same else "MISMATCH")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
