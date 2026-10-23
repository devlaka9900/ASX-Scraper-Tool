"""Orchestrates scrape → download → analyse → report for the GUI.

Mirrors the steps of main.py but never prints, never calls sys.exit, and
reports progress / honours cancellation through callbacks.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from analyzer.date_checker import analyse
from core.events import Cancelled, ProgressCb
from core.summary import RunMeta, RunResult, write_summary
from reporter.excel_report import write_excel_report
from reporter.report_generator import write_reports
from scraper.page_scraper import scrape_pdf_links
from scraper.pdf_downloader import download_all
from utils import net
from utils.file_utils import make_output_dirs
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class RunRequest:
    project_id: str
    url: str
    cutoff: datetime
    output_root: Path
    overwrite_downloads: bool = False


def run_pipeline(
    req: RunRequest,
    *,
    progress_cb: ProgressCb | None = None,
    cancel: threading.Event | None = None,
) -> RunResult:
    """Run the whole job. Never raises: problems end up in result.meta.status/error."""
    started = datetime.now()
    meta = RunMeta(
        run_id=started.strftime("%Y%m%d_%H%M%S"),
        project_id=req.project_id,
        url=req.url,
        cutoff=req.cutoff.strftime("%Y-%m-%d"),
        started_at=started.isoformat(timespec="seconds"),
        output_root=str(req.output_root),
    )
    result = RunResult(meta=meta)

    def emit(stage: str, done: int, total: int, msg: str = "") -> None:
        if progress_cb is not None:
            progress_cb(stage, done, total, msg)

    def check_cancel() -> None:
        if cancel is not None and cancel.is_set():
            raise Cancelled()

    try:
        net.INSECURE_SSL = False

        # 1 — Scrape (a single blocking request; cancel is checked either side)
        check_cancel()
        emit("scrape", 0, 1, "Fetching page")
        entries = scrape_pdf_links(req.url)
        check_cancel()
        if not entries:
            meta.status = "failed"
            meta.error = "No PDF links found on that page. Check the URL and try again."
            return _finish(result, started)
        emit("scrape", 1, 1, f"Found {len(entries)} PDFs")
        result.entries = entries

        # 2 — Folders
        emit("folders", 0, 1, "Creating output folders")
        sections = list(dict.fromkeys(e.section for e in entries))
        dirs = make_output_dirs(req.project_id, sections, root=req.output_root)
        result.base_dir = dirs["base"]
        emit("folders", 1, 1, str(dirs["base"]))

        # 3 — Download
        check_cancel()
        download_all(
            entries, dirs,
            progress_cb=progress_cb, cancel=cancel, overwrite=req.overwrite_downloads,
        )
        check_cancel()

        # 4 — Analyse. Clear earlier copies first so re-runs don't pile up
        # name_1.pdf / name_2.pdf duplicates in the copy-target folders.
        _purge_pdfs(dirs["updated"])
        _purge_pdfs(dirs["no_date"])
        analyse(entries, req.cutoff, dirs, progress_cb=progress_cb, cancel=cancel)

        # 5 — Reports
        emit("report", 0, 3, "Markdown reports")
        write_reports(entries, dirs, req.project_id, req.url, req.cutoff)
        emit("report", 1, 3, "Excel report")
        try:
            write_excel_report(entries, dirs, req.project_id, req.url, req.cutoff)
        except PermissionError:
            msg = "report.xlsx is open in another program — Excel report was not updated."
            log.warning(msg)
            meta.warnings.append(msg)
        emit("report", 2, 3, "Saving run summary")

    except Cancelled:
        meta.status = "cancelled"
        log.info("Run cancelled by user")
    except Exception as exc:  # noqa: BLE001 — surfaced to the user, not swallowed
        log.exception("Run failed")
        meta.status = "failed"
        meta.error = f"{type(exc).__name__}: {exc}"

    return _finish(result, started)


def _finish(result: RunResult, started: datetime) -> RunResult:
    meta = result.meta
    finished = datetime.now()
    meta.finished_at = finished.isoformat(timespec="seconds")
    meta.duration_s = round((finished - started).total_seconds(), 1)
    if result.base_dir is not None:
        try:
            write_summary(result)
        except OSError as exc:
            log.warning("Could not write run summary: %s", exc)
            meta.warnings.append(f"Run summary could not be saved: {exc}")
    return result


def _purge_pdfs(folder: Path) -> None:
    for pdf in folder.glob("*.pdf"):
        try:
            pdf.unlink()
        except OSError as exc:
            log.warning("Could not remove %s: %s", pdf.name, exc)
