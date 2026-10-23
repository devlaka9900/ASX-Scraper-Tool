"""Where things live, both when run from source and when frozen by PyInstaller."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from core.version import APP_NAME


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def app_dir() -> Path:
    """Folder that holds the exe (frozen) or the project (source)."""
    return Path(sys.executable).resolve().parent if is_frozen() else project_root()


def resource_path(rel: str) -> Path:
    """Read-only bundled resource (PyInstaller puts them under sys._MEIPASS)."""
    base = Path(getattr(sys, "_MEIPASS", project_root()))
    return base / rel


def data_dir() -> Path:
    """Per-user writable folder for logs, crash reports, etc."""
    root = os.environ.get("LOCALAPPDATA")
    base = Path(root) if root else Path.home() / ".local" / "share"
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_writable(path: Path) -> bool:
    """Real write probe — os.access is unreliable on Windows."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".probe", delete=True):
            pass
        return True
    except OSError:
        return False


def can_write_into(path: Path) -> bool:
    """Side-effect-free writability check: probes the nearest existing ancestor,
    never creates folders (safe to call while the user is still typing a path)."""
    probe = path if path.is_absolute() else Path.cwd() / path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    if not probe.is_dir():
        return False
    try:
        with tempfile.NamedTemporaryFile(dir=probe, prefix=".probe", delete=True):
            pass
        return True
    except OSError:
        return False


def documents_dir() -> Path:
    return Path.home() / "Documents" / APP_NAME


def default_output_dir() -> Path:
    """`output/` next to the exe; falls back to Documents when not writable."""
    preferred = app_dir() / "output"
    if is_writable(preferred):
        return preferred
    return documents_dir() / "output"
