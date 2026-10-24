"""Developer notes: a small CRUD store backed by one JSON file (Qt-free).

    notes.json  ->  {"schema_version": 1, "notes": [ {id, title, body_html, body_text,
                                                      created_at, updated_at}, ... ]}

* Stored per Windows user (core.paths.data_dir() / "notes.json") by default.
* Writes are atomic (temp file + os.replace) and keep the previous version as notes.json.bak.
* An unreadable file is never overwritten: it is renamed notes.corrupt-<time>.json and an
  empty store is started (``recovered_from`` tells the UI). A file written by a newer app
  version is refused (NotesError) instead of being rewritten with data we do not understand.
* ``body_html`` is the minimal rich text produced by gui/notes_html.py; ``body_text`` is the
  plain text used for search and previews.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1
TITLE_MAX = 120
BODY_MAX = 200_000
DEFAULT_TITLE = "Untitled note"


class NotesError(Exception):
    """Invalid note data, or a notes file we must not touch."""


@dataclass
class Note:
    id: str
    title: str
    body_html: str = ""
    body_text: str = ""
    created_at: str = ""
    updated_at: str = ""

    def preview(self, limit: int = 90) -> str:
        flat = " ".join(self.body_text.split())
        return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _check(title: str, body_text: str, body_html: str) -> str:
    title = " ".join(title.split())            # one line, collapsed whitespace
    if len(title) > TITLE_MAX:
        raise NotesError(f"The heading is too long (max {TITLE_MAX} characters).")
    if len(body_text) > BODY_MAX or len(body_html) > BODY_MAX * 3:
        raise NotesError(f"The note is too long (max {BODY_MAX:,} characters).")
    return title or DEFAULT_TITLE


class NotesStore:
    def __init__(self, path: Path | None = None):
        if path is None:
            from core.paths import data_dir
            path = data_dir() / "notes.json"
        self.path = Path(path)
        self.recovered_from: Path | None = None     # set when a corrupt file was set aside
        self.skipped = 0                             # malformed entries ignored on load
        self.kept_damaged: Path | None = None        # copy of the original file when entries were skipped
        self._lock = threading.RLock()
        self._notes: dict[str, Note] = {}
        self._load()

    # ---- read ---------------------------------------------------------------- #

    def list(self) -> list[Note]:
        with self._lock:
            return sorted(self._notes.values(), key=lambda n: (n.updated_at, n.created_at), reverse=True)

    def get(self, note_id: str) -> Note | None:
        with self._lock:
            return self._notes.get(note_id)

    def search(self, query: str) -> list[Note]:
        words = query.casefold().split()
        if not words:
            return self.list()
        out = []
        for n in self.list():
            hay = f"{n.title}\n{n.body_text}".casefold()
            if all(w in hay for w in words):
                out.append(n)
        return out

    def __len__(self) -> int:
        return len(self._notes)

    # ---- write --------------------------------------------------------------- #

    # Every write is transactional: the in-memory state only changes if the file was written.
    # If saving fails (locked file, full disk…) the exception propagates and memory still
    # matches what is on disk, so a later successful save can never resurrect or drop a note.

    def create(self, title: str = "", body_html: str = "", body_text: str = "") -> Note:
        title = _check(title, body_text, body_html)
        with self._lock:
            now = _now()
            note = Note(id=uuid.uuid4().hex, title=title, body_html=body_html, body_text=body_text,
                        created_at=now, updated_at=now)
            self._commit({**self._notes, note.id: note})
            return note

    def update(self, note_id: str, *, title: str | None = None,
               body_html: str | None = None, body_text: str | None = None) -> Note:
        with self._lock:
            note = self._notes.get(note_id)
            if note is None:
                raise NotesError("This note no longer exists.")
            new_title = _check(note.title if title is None else title,
                               note.body_text if body_text is None else body_text,
                               note.body_html if body_html is None else body_html)
            changed = replace(
                note, title=new_title,
                body_html=note.body_html if body_html is None else body_html,
                body_text=note.body_text if body_text is None else body_text,
                updated_at=_now())
            self._commit({**self._notes, note_id: changed})
            return changed

    def delete(self, note_id: str) -> bool:
        with self._lock:
            if note_id not in self._notes:
                return False
            remaining = {k: v for k, v in self._notes.items() if k != note_id}
            self._commit(remaining)
            return True

    def _commit(self, new_notes: dict[str, Note]) -> None:
        """Write *new_notes* to disk; only then make it the in-memory state."""
        self._save(new_notes)
        self._notes = new_notes

    # ---- persistence --------------------------------------------------------- #

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("notes", []), list):
                raise ValueError("unexpected structure")
            version = int(data.get("schema_version", 0))
        except (OSError, ValueError, TypeError):
            self._set_aside()
            return
        if version > SCHEMA_VERSION:
            raise NotesError(
                f"{self.path.name} was written by a newer version of the app "
                f"(schema {version}). Update the app to open your notes.")
        for raw in data.get("notes", []):
            try:
                note = Note(
                    id=str(raw["id"]), title=str(raw.get("title", DEFAULT_TITLE)),
                    body_html=str(raw.get("body_html", "")), body_text=str(raw.get("body_text", "")),
                    created_at=str(raw.get("created_at", "")), updated_at=str(raw.get("updated_at", "")),
                )
            except (KeyError, TypeError, AttributeError):
                self.skipped += 1
                continue
            self._notes[note.id] = note
        if self.skipped:
            # entries we could not read would be dropped by the next save: keep the original file
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            keep = self.path.with_name(f"notes.damaged-{stamp}.json")
            try:
                shutil.copy2(self.path, keep)
                self.kept_damaged = keep
            except OSError:
                pass

    def _set_aside(self) -> None:
        """Keep an unreadable notes file (never overwrite it) and start empty."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = self.path.with_name(f"notes.corrupt-{stamp}.json")
        try:
            os.replace(self.path, target)
            self.recovered_from = target
        except OSError:
            # cannot even move it: keep the in-memory store empty, and refuse to save over it
            raise NotesError(f"{self.path.name} is unreadable and could not be set aside.")

    def _save(self, notes: dict[str, Note] | None = None) -> None:
        notes = self._notes if notes is None else notes
        ordered = sorted(notes.values(), key=lambda n: (n.updated_at, n.created_at), reverse=True)
        payload = {"schema_version": SCHEMA_VERSION, "notes": [asdict(n) for n in ordered]}
        text = json.dumps(payload, indent=1, ensure_ascii=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        if self.path.is_file():
            try:
                shutil.copy2(self.path, self.path.with_name(self.path.name + ".bak"))
            except OSError:
                pass                                    # a missing backup must not block saving
        os.replace(tmp, self.path)
