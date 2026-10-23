"""
Downloads PDFs concurrently, captures HTTP Last-Modified headers,
and stores each file under the correct section subfolder.
"""
from __future__ import annotations

import os
import sys
import threading
import uuid
from concurrent.futures import (
    CancelledError,
    FIRST_COMPLETED,
    ThreadPoolExecutor,
    wait,
)
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from tqdm import tqdm

from config import DOWNLOAD_CHUNK, DOWNLOAD_TIMEOUT, DOWNLOAD_WORKERS, USER_AGENT
from core.events import FAILED_PREFIX, Cancelled, ProgressCb
from models import PDFEntry
from utils import net
from utils.file_utils import section_dir, url_filename
from utils.logger import get_logger

log = get_logger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": USER_AGENT})

_ssl_warned = False


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def download_all(
    entries: list[PDFEntry],
    dirs: dict[str, Path],
    *,
    progress_cb: ProgressCb | None = None,
    cancel: threading.Event | None = None,
    overwrite: bool = False,
) -> list[PDFEntry]:
    """Download every entry in parallel; mutates each entry with local_path and http_date.

    *progress_cb* / *cancel* are used by the GUI; the CLI calls this without
    them and gets the original tqdm progress bar.
    """
    log.info("Downloading %d PDFs with %d workers", len(entries), DOWNLOAD_WORKERS)

    total = len(entries)
    done = 0
    show_bar = progress_cb is None and sys.stderr is not None

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        futures = {
            pool.submit(_download_one, entry, dirs, cancel, overwrite): entry
            for entry in entries
        }
        pending = set(futures)
        bar = tqdm(total=total, desc="Downloading PDFs", unit="file", disable=not show_bar)
        try:
            while pending:
                if cancel is not None and cancel.is_set():
                    for fut in pending:
                        fut.cancel()
                finished, pending = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
                for fut in finished:
                    entry = futures[fut]
                    try:
                        fut.result()
                    except (Cancelled, CancelledError):
                        entry.download_error = "cancelled"
                    except Exception as exc:
                        entry.download_error = str(exc)
                        log.warning("Failed to download %s — %s", entry.name, exc)
                    done += 1
                    bar.update(1)
                    if progress_cb is not None:
                        failed = entry.download_error and entry.download_error != "cancelled"
                        progress_cb("download", done, total, f"{FAILED_PREFIX}{entry.name}" if failed else entry.name)
        finally:
            bar.close()

    ok = sum(1 for e in entries if not e.download_error)
    log.info("Downloaded %d/%d PDFs successfully", ok, len(entries))
    return entries


# --------------------------------------------------------------------------- #
# Internal
# --------------------------------------------------------------------------- #

def _download_one(
    entry: PDFEntry,
    dirs: dict[str, Path],
    cancel: threading.Event | None = None,
    overwrite: bool = False,
) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled()

    dest_dir = section_dir(dirs, entry.section)
    filename = url_filename(entry.url)
    dest = dest_dir / filename

    if dest.exists() and not overwrite:
        log.debug("Already exists, skipping: %s", filename)
        entry.local_path = dest
        return

    response = _SESSION.get(
        entry.url, stream=True, timeout=DOWNLOAD_TIMEOUT, verify=_verify_ssl()
    )
    # Unique, *short* temp name: a cancelled/crashed download never leaves a truncated
    # file that the exists() shortcut above would later treat as complete, and the
    # name stays shorter than the real one so deep folders don't hit Windows' 260-char limit.
    part = dest.with_name(f"~{uuid.uuid4().hex[:8]}.part")
    try:
        response.raise_for_status()
        entry.http_date = _parse_http_date(response.headers.get("Last-Modified"))

        with open(part, "wb") as fh:
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                if chunk:
                    fh.write(chunk)
        os.replace(part, dest)
    finally:
        response.close()
        try:
            part.unlink()
        except FileNotFoundError:
            pass

    entry.local_path = dest
    log.debug("Saved: %s", dest.name)


def _verify_ssl() -> bool:
    """Mirror the scraper's corporate-proxy fallback (see utils.net)."""
    global _ssl_warned
    if not net.INSECURE_SSL:
        return True
    if not _ssl_warned:
        _ssl_warned = True
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        log.warning("Downloading without SSL verification (page fetch needed the same fallback)")
    return False


def _parse_http_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).replace(tzinfo=None)
    except Exception:
        return None
