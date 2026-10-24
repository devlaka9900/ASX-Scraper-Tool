"""
Generates two markdown reports inside the project output folder:
  - analysis_report.md   full inventory with dates, sources, and categories
  - updated_page_count.md  page-count breakdown for updated PDFs only
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from models import PDFEntry
from utils.logger import get_logger

log = get_logger(__name__)

_CATEGORY_LABEL = {
    "updated":        "✅ Updated",
    "not_updated":    "⏸ Not Updated",
    "no_date":        "❓ No Date Found",
    "download_error": "❌ Download Error",
}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def write_reports(
    entries: list[PDFEntry],
    dirs: dict[str, Path],
    project_id: str,
    url: str,
    cutoff: datetime,
) -> None:
    _write_analysis_report(entries, dirs, project_id, url, cutoff)
    _write_page_count_report(entries, dirs, cutoff)


# --------------------------------------------------------------------------- #
# Analysis report
# --------------------------------------------------------------------------- #

def _write_analysis_report(
    entries: list[PDFEntry],
    dirs: dict[str, Path],
    project_id: str,
    url: str,
    cutoff: datetime,
) -> None:
    out = dirs["base"] / "analysis_report.md"
    counts = _count_by_category(entries)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []

    # ---- Header ----
    lines += [
        "# ASX PDF Analysis Report",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| DocumentId | `{project_id}` |",
        f"| Source URL | {url} |",
        f"| Cutoff Date | **{cutoff.strftime('%Y-%m-%d')}** |",
        f"| Run At | {now} |",
        f"| Total PDFs Found | {len(entries)} |",
        "",
    ]

    # ---- Summary counts ----
    lines += [
        "## Summary",
        "",
        "| Category | Count |",
        "|----------|-------|",
    ]
    for cat, label in _CATEGORY_LABEL.items():
        lines.append(f"| {label} | {counts.get(cat, 0)} |")
    lines.append("")

    # ---- Updated PDFs ----
    updated = [e for e in entries if e.category == "updated"]
    if updated:
        lines += [
            "## Updated PDFs",
            f"> PDFs with a date **after** {cutoff.strftime('%Y-%m-%d')}",
            "",
            "| # | Name | Section | Date | Date Source | Pages |",
            "|---|------|---------|------|-------------|-------|",
        ]
        for i, e in enumerate(updated, 1):
            lines.append(
                f"| {i} | {e.name} | {e.display_section} | {e.display_date} "
                f"| {e.date_source} | {e.page_count or '—'} |"
            )
        lines.append("")

    # ---- No-date PDFs ----
    no_date = [e for e in entries if e.category == "no_date"]
    if no_date:
        lines += [
            "## PDFs With No Date Found",
            "> These were copied to the `Date_Not_Found` folder.",
            "",
            "| # | Name | Section | Pages |",
            "|---|------|---------|-------|",
        ]
        for i, e in enumerate(no_date, 1):
            lines.append(f"| {i} | {e.name} | {e.display_section} | {e.page_count or '—'} |")
        lines.append("")

    # ---- Not updated PDFs ----
    not_updated = [e for e in entries if e.category == "not_updated"]
    if not_updated:
        lines += [
            "## Not Updated PDFs",
            f"> PDFs with a date **on or before** {cutoff.strftime('%Y-%m-%d')}",
            "",
            "| # | Name | Section | Date | Date Source | Pages |",
            "|---|------|---------|------|-------------|-------|",
        ]
        for i, e in enumerate(not_updated, 1):
            lines.append(
                f"| {i} | {e.name} | {e.display_section} | {e.display_date} "
                f"| {e.date_source} | {e.page_count or '—'} |"
            )
        lines.append("")

    # ---- Download errors ----
    errors = [e for e in entries if e.category == "download_error"]
    if errors:
        lines += [
            "## Download Errors",
            "",
            "| # | Name | URL | Error |",
            "|---|------|-----|-------|",
        ]
        for i, e in enumerate(errors, 1):
            lines.append(f"| {i} | {e.name} | {e.url} | {e.download_error} |")
        lines.append("")

    # ---- Full inventory ----
    lines += [
        "## Full Inventory",
        "",
        "| # | Name | Section | Date | Date Source | Category | Pages |",
        "|---|------|---------|------|-------------|----------|-------|",
    ]
    for i, e in enumerate(entries, 1):
        label = _CATEGORY_LABEL.get(e.category, e.category)
        lines.append(
            f"| {i} | {e.name} | {e.display_section} | {e.display_date} "
            f"| {e.date_source or '—'} | {label} | {e.page_count or '—'} |"
        )
    lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    log.info("Analysis report → %s", out)


# --------------------------------------------------------------------------- #
# Page count report
# --------------------------------------------------------------------------- #

def _write_page_count_report(
    entries: list[PDFEntry],
    dirs: dict[str, Path],
    cutoff: datetime,
) -> None:
    out = dirs["base"] / "updated_page_count.md"
    updated = [e for e in entries if e.category == "updated"]

    lines: list[str] = [
        "# Updated PDF Page Count",
        "",
        f"> Documents updated after **{cutoff.strftime('%Y-%m-%d')}**",
        "",
        "| # | Name | Section | Date | Pages |",
        "|---|------|---------|------|-------|",
    ]

    total_pages = 0
    for i, e in enumerate(updated, 1):
        lines.append(
            f"| {i} | {e.name} | {e.display_section} | {e.display_date} | {e.page_count or '—'} |"
        )
        total_pages += e.page_count

    lines += [
        "",
        f"**Total Updated PDFs:** {len(updated)}",
        f"**Total Pages:** {total_pages}",
        "",
    ]

    out.write_text("\n".join(lines), encoding="utf-8")
    log.info("Page count report → %s", out)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _count_by_category(entries: list[PDFEntry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.category] = counts.get(e.category, 0) + 1
    return counts
