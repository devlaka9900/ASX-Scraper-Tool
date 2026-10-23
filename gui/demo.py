"""Deterministic fake results for the self-test and for screenshots."""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

from core.summary import RunMeta, RunResult
from models import PDFEntry

_SECTIONS = (
    ("rules", "Rules", "Chapter {:02d}"),
    ("guidance_notes", "Guidance Notes", "Guidance Note {:02d}"),
    ("waivers", "Waivers", "Waiver Decision {:02d}"),
    ("appendices", "Appendices", "Appendix {:02d}A"),
)


def make_demo_result(n: int = 240, base_dir: Path | None = None, seed: int = 7) -> RunResult:
    rng = random.Random(seed)
    cutoff = datetime(2024, 1, 1)
    entries: list[PDFEntry] = []
    weights = (("updated", 0.30), ("not_updated", 0.58), ("no_date", 0.07), ("download_error", 0.05))
    for i in range(n):
        slug, label, pattern = _SECTIONS[i % len(_SECTIONS) if i % 7 else rng.randrange(len(_SECTIONS))]
        cat = rng.choices([w[0] for w in weights], [w[1] for w in weights])[0]
        name = pattern.format(i % 40 + 1)
        entry = PDFEntry(
            name=name, url=f"https://www.asx.com.au/documents/rules/{slug}/{name.replace(' ', '_')}_{i}.pdf",
            section=slug, section_label=label, category=cat,
        )
        if cat in ("updated", "not_updated"):
            delta = timedelta(days=rng.randint(1, 600))
            entry.resolved_date = cutoff + delta if cat == "updated" else cutoff - delta
            entry.pdf_meta_date = entry.resolved_date
            entry.date_source = "pdf_metadata"
            entry.page_count = rng.randint(2, 90)
        elif cat == "no_date":
            entry.page_count = rng.randint(0, 12)
        else:
            entry.download_error = "404 Client Error: Not Found for url"
        entries.append(entry)

    meta = RunMeta(
        run_id="20261023_101500", project_id="AU--DEMO--REG--ASX-24",
        url="https://www.asx.com.au/about/regulation/rules-guidance-notes-and-waivers/asx-24-operating-rules-guidance-notes-and-waivers",
        cutoff=cutoff.strftime("%Y-%m-%d"), started_at="2026-10-23T10:15:00",
        finished_at="2026-10-23T10:16:12", duration_s=72.0, output_root=str(base_dir.parent if base_dir else ""),
    )
    return RunResult(meta=meta, entries=entries, base_dir=base_dir)
