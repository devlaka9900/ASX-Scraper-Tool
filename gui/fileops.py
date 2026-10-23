"""Open files/folders with the OS default handler."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def open_path(path: Path) -> bool:
    """Open a file or folder in its default application."""
    if not path.exists():
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def open_url(url: str) -> bool:
    return QDesktopServices.openUrl(QUrl(url))


def show_in_folder(path: Path) -> bool:
    """Reveal *path* in Explorer (selected); falls back to opening its folder."""
    if not path.exists():
        return False
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
        return True
    return open_path(path.parent)
