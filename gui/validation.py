"""Input validation for the New Run form. Each validator returns an error
message, or None when the value is fine. Rules mirror main.py (non-empty ID,
http(s) URL, YYYY-MM-DD cutoff) plus guards for things the CLI never checked
(the DocumentId becomes a folder name). The Startpoint is optional free text: no rules, just trimmed."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from core.paths import can_write_into

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")
_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


STARTPOINT_MAX = 100


def clean_startpoint(value: str) -> str:
    """Optional free text: trimmed, whitespace collapsed, capped. Never an error."""
    return " ".join(value.split())[:STARTPOINT_MAX]


def project_id_error(value: str) -> str | None:
    """Validation of the DocumentId (stored internally as project_id)."""
    v = value.strip()
    if not v:
        return "DocumentId cannot be empty."
    if len(v) > 64:
        return "DocumentId is too long (max 64 characters)."
    if not _ID_RE.match(v):
        return "Use letters, numbers, spaces, dots, dashes or underscores (must start with a letter or number)."
    if v.endswith((".", " ")):
        return "DocumentId cannot end with a dot or space."
    if v.split(".")[0].strip().lower() in _RESERVED:
        return f"“{v}” is a reserved Windows name."
    return None


def url_error(value: str) -> str | None:
    v = value.strip()
    if not v:
        return "Page URL cannot be empty."
    parsed = urlparse(v)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "URL must start with http:// or https:// and include a host."
    return None


# <root>\<id>\downloads\<section>\<file>.pdf — the longest real ASX names are ~60 chars
_LONG_PATH_BUDGET = 260 - (len("\\downloads\\guidance_notes\\") + 70)


def long_path_warning(output_dir: str, project_id: str) -> str | None:
    """Soft warning (not an error): Windows' classic 260-char path limit."""
    full = Path(output_dir.strip()) / project_id.strip()
    if len(str(full.resolve() if full.is_absolute() else Path.cwd() / full)) > _LONG_PATH_BUDGET:
        return ("This folder path is very long. Windows limits full file paths to 260 characters, "
                "so some downloads may fail. Choose a shorter output folder or DocumentId.")
    return None


def output_dir_error(value: str) -> str | None:
    v = value.strip()
    if not v:
        return "Choose an output folder."
    p = Path(v)
    if p.exists() and not p.is_dir():
        return "That path is a file, not a folder."
    if not can_write_into(p):       # no mkdir: this runs while the user is typing
        return "This folder is not writable. Pick another one."
    return None
