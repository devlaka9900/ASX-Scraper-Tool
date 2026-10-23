"""Typed wrapper around QSettings (HKCU registry on Windows)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings

from core.paths import default_output_dir, is_writable, documents_dir


class Settings:
    def __init__(self, qsettings: QSettings | None = None):
        self._s = qsettings or QSettings("CUBE", "ASXPDFChecker")

    # ---- appearance -------------------------------------------------------- #

    @property
    def theme(self) -> str:
        v = str(self._s.value("ui/theme", "system"))
        return v if v in ("system", "dark", "light") else "system"

    @theme.setter
    def theme(self, value: str) -> None:
        self._s.setValue("ui/theme", value)

    @property
    def reduced_motion(self) -> bool | None:
        v = self._s.value("ui/reduced_motion", None)
        if v is None:
            return None
        return str(v).lower() in ("1", "true")

    @property
    def geometry(self) -> QByteArray | None:
        v = self._s.value("ui/geometry", None)
        return v if isinstance(v, QByteArray) else None

    @geometry.setter
    def geometry(self, value: QByteArray) -> None:
        self._s.setValue("ui/geometry", value)

    # ---- run inputs --------------------------------------------------------- #

    @property
    def output_dir(self) -> Path:
        """Remembered output folder; falls back to the default when it can't be used."""
        raw = str(self._s.value("output/dir", "") or "")
        if raw:
            p = Path(raw)
            if is_writable(p):
                return p
        return default_output_dir()

    @output_dir.setter
    def output_dir(self, value: Path) -> None:
        self._s.setValue("output/dir", str(value))

    @property
    def last_project_id(self) -> str:
        return str(self._s.value("run/last_project_id", "") or "")

    @property
    def last_url(self) -> str:
        return str(self._s.value("run/last_url", "") or "")

    @property
    def last_cutoff(self) -> str:
        return str(self._s.value("run/last_cutoff", "") or "")

    def remember_run(self, project_id: str, url: str, cutoff: str) -> None:
        self._s.setValue("run/last_project_id", project_id)
        self._s.setValue("run/last_url", url)
        self._s.setValue("run/last_cutoff", cutoff)

    # ---- history roots ------------------------------------------------------- #

    def history_roots(self) -> list[Path]:
        raw = self._s.value("history/roots", []) or []
        if isinstance(raw, str):
            raw = [raw]
        return [Path(r) for r in raw]

    def add_history_root(self, root: Path) -> None:
        roots = [str(r) for r in self.history_roots()]
        if str(root) not in roots:
            roots.append(str(root))
            self._s.setValue("history/roots", roots)

    def removed_history(self) -> set[str]:
        raw = self._s.value("history/removed", []) or []
        if isinstance(raw, str):
            raw = [raw]
        return set(raw)

    def remove_history_item(self, path: Path) -> None:
        removed = self.removed_history()
        removed.add(str(path))
        self._s.setValue("history/removed", sorted(removed))

    def sync(self) -> None:
        self._s.sync()
