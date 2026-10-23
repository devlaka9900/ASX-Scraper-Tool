"""Progress / cancellation primitives shared by the pipeline and the GUI.

No Qt imports here — the core must stay usable from the CLI.
"""
from __future__ import annotations

from typing import Callable

# (stage, done, total, message)
ProgressCb = Callable[[str, int, int, str], None]

STAGES = ("scrape", "folders", "download", "analyse", "report")
STAGE_LABELS = {
    "scrape":   "Scrape",
    "folders":  "Folders",
    "download": "Download",
    "analyse":  "Analyse",
    "report":   "Reports",
}


FAILED_PREFIX = "✗ "   # download progress messages starting with this denote a failed file


class Cancelled(Exception):
    """Raised inside worker code when the user cancelled the run."""
