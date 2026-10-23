"""Run results: in-memory types, run_summary.json (de)serialisation, history scan.

One loader (`load_run`) feeds both a live result and a History re-open, so the
GUI only has one rendering path. Everything here is Qt-free.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from core.version import APP_VERSION
from models import PDFEntry

SCHEMA_VERSION = 1
CATEGORIES = ("updated", "not_updated", "no_date", "download_error")
SUMMARY_NAME = "run_summary.json"
HISTORY_DIR = "history"

_DATETIME_FIELDS = ("upload_date", "http_date", "pdf_meta_date", "resolved_date")


class SummaryError(Exception):
    """Unreadable / unsupported run_summary.json."""


# --------------------------------------------------------------------------- #
# Types
# --------------------------------------------------------------------------- #

@dataclass
class RunMeta:
    run_id: str = ""
    project_id: str = ""
    url: str = ""
    cutoff: str = ""                     # YYYY-MM-DD
    started_at: str = ""
    finished_at: str = ""
    duration_s: float = 0.0
    status: str = "completed"            # completed | cancelled | failed
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    source_run: str | None = None
    output_root: str = ""                # informational only, never trusted for file access


@dataclass
class RunResult:
    meta: RunMeta
    entries: list[PDFEntry] = field(default_factory=list)
    base_dir: Path | None = None         # <output_root>/<project_id>
    kind: str = "run"                    # run | date_check

    @property
    def stats(self) -> dict[str, Any]:
        return compute_stats(self.entries)

    @property
    def cutoff_date(self) -> datetime:
        return datetime.strptime(self.meta.cutoff, "%Y-%m-%d")


@dataclass
class HistoryItem:
    path: Path                           # the history/run_*.json file
    meta: RunMeta
    stats: dict[str, Any]
    base_dir: Path
    base_exists: bool


# --------------------------------------------------------------------------- #
# Stats
# --------------------------------------------------------------------------- #

def compute_stats(entries: list[PDFEntry]) -> dict[str, Any]:
    counts = {c: 0 for c in CATEGORIES}
    by_section: dict[str, dict[str, int]] = {}
    updated_pages = total_pages = 0

    for e in entries:
        if e.category in counts:
            counts[e.category] += 1
        sec = by_section.setdefault(e.display_section, {c: 0 for c in CATEGORIES})
        if e.category in sec:
            sec[e.category] += 1
        total_pages += e.page_count or 0
        if e.category == "updated":
            updated_pages += e.page_count or 0

    return {
        "total": len(entries),
        **counts,
        "updated_pages": updated_pages,
        "total_pages": total_pages,
        "by_section": by_section,
    }


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #

def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def _rel_path(path: Path | None, base: Path | None) -> str | None:
    if path is None or base is None:
        return None
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def entry_to_dict(entry: PDFEntry, base: Path | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in fields(PDFEntry):
        value = getattr(entry, f.name)
        if f.name in _DATETIME_FIELDS:
            value = _iso(value)
        elif f.name == "local_path":
            value = _rel_path(value, base)
        out[f.name] = value
    return out


def _safe_join(base: Path, rel: str | None) -> Path | None:
    """Resolve a stored relative path under *base*. Rejects absolute / rooted /
    drive-qualified paths and '..' in either separator style, and anything that
    resolves outside *base* (a hand-edited summary must not point at other files)."""
    if not rel or not isinstance(rel, str):
        return None
    posix = PurePosixPath(rel.replace("\\", "/"))
    win = PureWindowsPath(rel)
    if posix.is_absolute() or win.drive or win.root or ".." in posix.parts:
        return None
    out = base.joinpath(*posix.parts)
    try:
        out.resolve().relative_to(base.resolve())
    except (ValueError, OSError):
        return None
    return out


def entry_from_dict(data: dict[str, Any], base: Path) -> PDFEntry:
    known = {f.name for f in fields(PDFEntry)}
    kwargs: dict[str, Any] = {}
    for key, value in data.items():
        if key not in known:
            continue
        if key in _DATETIME_FIELDS:
            try:
                value = datetime.fromisoformat(value) if value else None
            except ValueError:
                value = None
        elif key == "local_path":
            value = _safe_join(base, value)
        kwargs[key] = value
    kwargs.setdefault("name", "")
    kwargs.setdefault("url", "")
    kwargs.setdefault("section", "other")
    return PDFEntry(**kwargs)


def result_to_dict(result: RunResult) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "app_version": APP_VERSION,
        "kind": result.kind,
        "meta": asdict(result.meta),
        "stats": result.stats,
        "entries": [entry_to_dict(e, result.base_dir) for e in result.entries],
    }


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_summary(result: RunResult) -> Path:
    """Write the latest summary + a per-run archive used by History."""
    if result.base_dir is None:
        raise SummaryError("Result has no base directory")
    text = json.dumps(result_to_dict(result), indent=1, ensure_ascii=False)
    latest = result.base_dir / SUMMARY_NAME
    _atomic_write(latest, text)
    _atomic_write(result.base_dir / HISTORY_DIR / f"run_{result.meta.run_id}.json", text)
    return latest


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def _base_for(path: Path) -> Path:
    # Only the per-run archives live in <base>/history/; run_summary.json is in <base>
    # itself (even for a project that happens to be called "history").
    is_archive = path.parent.name == HISTORY_DIR and path.name != SUMMARY_NAME
    return path.parent.parent if is_archive else path.parent


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SummaryError(f"Cannot read {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise SummaryError(f"{path.name} is not a run summary")
    try:
        version = int(data.get("schema_version", 0))
    except (TypeError, ValueError) as exc:
        raise SummaryError(f"{path.name} has an invalid schema_version") from exc
    if version > SCHEMA_VERSION:
        raise SummaryError(
            f"{path.name} was written by a newer version of the app (schema "
            f"{version}); please update."
        )
    return data


def _meta_from(data: dict[str, Any]) -> RunMeta:
    known = {f.name for f in fields(RunMeta)}
    raw = data.get("meta")
    if not isinstance(raw, dict):
        return RunMeta()
    return RunMeta(**{k: v for k, v in raw.items() if k in known})


def load_run(path: Path) -> RunResult:
    data = _read_json(path)
    base = _base_for(path)
    return RunResult(
        meta=_meta_from(data),
        entries=[entry_from_dict(d, base) for d in data.get("entries", [])],
        base_dir=base,
        kind=data.get("kind", "run"),
    )


def scan_history(roots: list[Path]) -> list[HistoryItem]:
    """List runs found under *roots* (`<root>/*/history/run_*.json`), newest first.

    Only meta + stats are read, so this stays fast with many runs. Old CLI
    folders have no history/ directory and are therefore never listed.
    """
    items: list[HistoryItem] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob(f"*/{HISTORY_DIR}/run_*.json"):
            try:
                data = _read_json(path)
                stats = data.get("stats")
                base = _base_for(path)
                items.append(HistoryItem(
                    path=path,
                    meta=_meta_from(data),
                    stats=stats if isinstance(stats, dict) else {},
                    base_dir=base,
                    base_exists=(base / "downloads").is_dir() or (base / SUMMARY_NAME).is_file(),
                ))
            except (SummaryError, TypeError, ValueError, AttributeError):
                continue      # one foreign / hand-edited file must not hide every other run
    items.sort(key=lambda i: str(i.meta.started_at or ""), reverse=True)
    return items
