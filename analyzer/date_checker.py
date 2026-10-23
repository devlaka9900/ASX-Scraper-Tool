"""
Reads each downloaded PDF's internal metadata date (ModDate, then CreationDate),
categorises it against the cutoff as:
  "updated"     — pdf_meta_date > cutoff_date
  "not_updated" — pdf_meta_date <= cutoff_date
  "no_date"     — PDF has no date metadata

Also reads page counts. Both are done in a single fitz.open per file.
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF

from core.events import Cancelled, ProgressCb
from models import PDFEntry
from utils.file_utils import copy_pdf
from utils.logger import get_logger

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def analyse(
    entries: list[PDFEntry],
    cutoff: datetime,
    dirs: dict[str, Path],
    *,
    progress_cb: ProgressCb | None = None,
    cancel: threading.Event | None = None,
) -> list[PDFEntry]:
    """Read PDF metadata, categorise against cutoff, and copy to output folders."""
    total = len(entries)
    for done, entry in enumerate(entries, 1):
        if cancel is not None and cancel.is_set():
            raise Cancelled()

        if entry.download_error:
            entry.category = "download_error"
        else:
            _read_pdf_info(entry)
            _categorise(entry, cutoff, dirs)

        if progress_cb is not None:
            progress_cb("analyse", done, total, entry.name)

    _log_summary(entries, cutoff)
    return entries


def classify(resolved: datetime | None, cutoff: datetime) -> str:
    """Pure categorisation rule: no date / after cutoff / on-or-before cutoff."""
    if resolved is None:
        return "no_date"
    return "updated" if resolved > cutoff else "not_updated"


# --------------------------------------------------------------------------- #
# PDF read — page count + metadata date in one open
# --------------------------------------------------------------------------- #

def _read_pdf_info(entry: PDFEntry) -> None:
    """Open the PDF once: read page count and ModDate (or CreationDate)."""
    if not entry.local_path or not entry.local_path.exists():
        entry.date_source = "none"
        return

    try:
        doc = fitz.open(str(entry.local_path))
        entry.page_count = doc.page_count
        meta = doc.metadata
        doc.close()
    except Exception as exc:
        log.debug("Could not open PDF %s: %s", entry.name, exc)
        entry.date_source = "none"
        return

    for key in ("modDate", "creationDate"):
        parsed = _parse_pdf_date(meta.get(key, ""))
        if parsed:
            entry.pdf_meta_date = parsed
            entry.resolved_date = parsed
            entry.date_source = "pdf_metadata"
            return

    entry.date_source = "none"


read_pdf_info = _read_pdf_info   # public alias for the GUI date checker


def _parse_pdf_date(raw: str) -> datetime | None:
    if not raw:
        return None
    # PyMuPDF format: "D:YYYYMMDDHHmmSS±HH'mm'"
    raw = raw.strip()
    if raw.startswith("D:"):
        raw = raw[2:]
    digits = raw[:14]
    for fmt, length in (("%Y%m%d%H%M%S", 14), ("%Y%m%d%H%M", 12), ("%Y%m%d", 8)):
        try:
            return datetime.strptime(digits[:length], fmt)
        except ValueError:
            pass
    return None


# --------------------------------------------------------------------------- #
# Categorisation & file copying
# --------------------------------------------------------------------------- #

def _categorise(entry: PDFEntry, cutoff: datetime, dirs: dict[str, Path]) -> None:
    entry.category = classify(entry.resolved_date, cutoff)
    if entry.category == "no_date":
        if entry.local_path and entry.local_path.exists():
            copy_pdf(entry.local_path, dirs["no_date"])
    elif entry.category == "updated":
        if entry.local_path and entry.local_path.exists():
            copy_pdf(entry.local_path, dirs["updated"])


# --------------------------------------------------------------------------- #
# Summary log
# --------------------------------------------------------------------------- #

def _log_summary(entries: list[PDFEntry], cutoff: datetime) -> None:
    counts = {"updated": 0, "not_updated": 0, "no_date": 0, "download_error": 0}
    for e in entries:
        counts[e.category] = counts.get(e.category, 0) + 1

    log.info(
        "Analysis complete (cutoff %s) — updated: %d | not updated: %d | "
        "no date: %d | errors: %d",
        cutoff.date(),
        counts["updated"],
        counts["not_updated"],
        counts["no_date"],
        counts["download_error"],
    )
