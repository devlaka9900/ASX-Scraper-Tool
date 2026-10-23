"""GUI port of check_pdf_dates.py: re-categorise already-downloaded PDFs against a
new cutoff. Read-only — nothing is copied and no existing report is touched.
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from analyzer.date_checker import classify, read_pdf_info
from core.events import Cancelled, ProgressCb
from core.summary import SUMMARY_NAME, RunMeta, RunResult, load_run
from models import PDFEntry
from reporter.excel_report import write_excel_report
from reporter.report_generator import write_reports
from utils.file_utils import url_filename
from utils.logger import get_logger

log = get_logger(__name__)


def resolve_folder(path: Path) -> tuple[Path, Path]:
    """Return (project_base, downloads_dir) for a project folder, a downloads
    folder, or any plain folder of PDFs."""
    if (path / "downloads").is_dir():
        return path, path / "downloads"
    if path.name.lower() == "downloads":
        return path.parent, path
    return path, path


def check_folder(
    path: Path,
    cutoff: datetime,
    *,
    progress_cb: ProgressCb | None = None,
    cancel: threading.Event | None = None,
) -> RunResult:
    started = datetime.now()
    base, downloads = resolve_folder(path)
    pdfs = sorted(downloads.rglob("*.pdf"))

    known, source_run, source_url = _known_entries(base)   # from an earlier run, if any

    entries: list[PDFEntry] = []
    seen: set[tuple[str, str]] = set()
    total = len(pdfs)

    for done, pdf in enumerate(pdfs, 1):
        if cancel is not None and cancel.is_set():
            raise Cancelled()

        rel = pdf.relative_to(downloads)
        section = rel.parts[0] if len(rel.parts) > 1 else "other"
        key = (section, pdf.name)
        seen.add(key)

        src = known.get(key)
        entry = PDFEntry(
            name=src.name if src else pdf.name,
            url=src.url if src else "",
            section=section,
            section_label=src.section_label if src else "",
            upload_date=src.upload_date if src else None,
            local_path=pdf,
        )
        read_pdf_info(entry)
        entry.category = classify(entry.resolved_date, cutoff)
        entries.append(entry)

        if progress_cb is not None:
            progress_cb("analyse", done, total, pdf.name)

    # Entries the earlier run knew about but whose file is gone
    for key, src in known.items():
        if key in seen:
            continue
        entries.append(PDFEntry(
            name=src.name, url=src.url, section=src.section,
            section_label=src.section_label,
            download_error=src.download_error or "File not found on disk",
            category="download_error",
        ))

    finished = datetime.now()
    meta = RunMeta(
        run_id=started.strftime("%Y%m%d_%H%M%S"),
        project_id=base.name,
        url=source_url,
        cutoff=cutoff.strftime("%Y-%m-%d"),
        started_at=started.isoformat(timespec="seconds"),
        finished_at=finished.isoformat(timespec="seconds"),
        duration_s=round((finished - started).total_seconds(), 1),
        source_run=source_run,
        output_root=str(base.parent),
    )
    return RunResult(meta=meta, entries=entries, base_dir=base, kind="date_check")


def export_reports(result: RunResult) -> Path:
    """Write md + xlsx reports into <project>/date_checks/<cutoff>_<timestamp>/."""
    assert result.base_dir is not None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = result.base_dir / "date_checks" / f"{result.meta.cutoff}_{stamp}"
    export_dir.mkdir(parents=True, exist_ok=True)
    dirs = {"base": export_dir}
    cutoff = result.cutoff_date
    write_reports(result.entries, dirs, result.meta.project_id, result.meta.url, cutoff)
    write_excel_report(result.entries, dirs, result.meta.project_id, result.meta.url, cutoff)
    return export_dir


def _known_entries(base: Path) -> tuple[dict[tuple[str, str], PDFEntry], str | None, str]:
    """(entries keyed by (section, filename), run_id, url) from <base>/run_summary.json.
    Empty when there is no usable summary."""
    summary = base / SUMMARY_NAME
    if not summary.is_file():
        return {}, None, ""
    try:
        run = load_run(summary)
    except Exception as exc:  # corrupt/newer summary: fall back to filenames only
        log.warning("Ignoring unreadable summary %s: %s", summary, exc)
        return {}, None, ""
    entries = {(e.section, url_filename(e.url)): e for e in run.entries if e.url}
    return entries, run.meta.run_id, run.meta.url
