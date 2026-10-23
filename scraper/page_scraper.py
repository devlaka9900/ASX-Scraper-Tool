"""
Fetches the target ASX page with requests, then extracts every PDF
link together with its Upload Date from the surrounding table.

Note: BeautifulSoup parses the full HTML source regardless of accordion/
details open-state, so no browser or JavaScript execution is needed.
"""
from __future__ import annotations

import warnings
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from config import ASX_BASE, PAGE_FETCH_TIMEOUT, USER_AGENT
from models import PDFEntry
from utils import net
from utils.file_utils import slugify
from utils.logger import get_logger

log = get_logger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": USER_AGENT})


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def scrape_pdf_links(url: str) -> list[PDFEntry]:
    """Return all PDF entries found on *url*, with upload dates where present."""
    log.info("Fetching page → %s", url)
    html = _fetch_page(url)
    entries = _parse_entries(html, url)
    log.info("Found %d PDF entries", len(entries))
    return entries


# --------------------------------------------------------------------------- #
# Page fetch
# --------------------------------------------------------------------------- #

def _fetch_page(url: str) -> str:
    try:
        response = _SESSION.get(url, timeout=PAGE_FETCH_TIMEOUT, verify=True)
    except requests.exceptions.SSLError:
        # Corporate SSL-inspection proxy — retry without verification
        log.warning("SSL verification failed; retrying without SSL verification (corporate proxy detected)")
        net.INSECURE_SSL = True
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = _SESSION.get(url, timeout=PAGE_FETCH_TIMEOUT, verify=False)

    response.raise_for_status()
    return response.text


# --------------------------------------------------------------------------- #
# HTML parsing
# --------------------------------------------------------------------------- #

def _parse_entries(html: str, base_url: str) -> list[PDFEntry]:
    soup = BeautifulSoup(html, "lxml")

    # Primary strategy: the page renders sections as tabs (AEM cmp-tabs component
    # — verified on both known ASX pages). Read whatever tabs actually exist and
    # take every PDF under each tab's own panel, instead of assuming a fixed set
    # of sections — different pages expose a different number/name of tabs
    # (e.g. the ASX 24 page has no "Appendices" tab at all).
    tab_entries = _entries_from_tabs(soup, base_url)
    if tab_entries is not None:
        return tab_entries

    # Fallback: no tab structure found — scan the whole page as before.
    return _entries_from_whole_page(soup, base_url)


def _entries_from_tabs(soup, base_url: str) -> list[PDFEntry] | None:
    tabs = soup.find_all(attrs={"data-cmp-hook-tabs": "tab"})
    panels = soup.find_all(attrs={"data-cmp-hook-tabs": "tabpanel"})
    if not tabs or len(tabs) != len(panels):
        return None

    entries: list[PDFEntry] = []
    for tab, panel in zip(tabs, panels):
        label = tab.get_text(strip=True)
        if not label:
            continue
        entries.extend(_entries_from_scope(panel, base_url, slugify(label), label))
    return entries


def _entries_from_whole_page(soup, base_url: str) -> list[PDFEntry]:
    entries: list[PDFEntry] = []

    # Strategy 1: scan every <table> for rows that contain a .pdf link
    for table in soup.find_all("table"):
        entries.extend(_entries_from_table(table, base_url))

    # Strategy 2: catch any .pdf links that are NOT inside tables
    table_links = {e.url for e in entries}
    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if not href.lower().endswith(".pdf"):
            continue
        full_url = _resolve_url(href, base_url)
        if full_url in table_links:
            continue
        section = _section_from_url(full_url)
        entries.append(PDFEntry(
            name=a.get_text(strip=True) or _url_name(full_url),
            url=full_url,
            section=section,
            section_label=section.replace("_", " ").title(),
        ))
        table_links.add(full_url)

    return entries


def _entries_from_scope(scope, base_url: str, section: str, label: str) -> list[PDFEntry]:
    """Same two-strategy scan as _entries_from_whole_page, but confined to one
    tab panel and tagged with that tab's own section slug/label."""
    entries: list[PDFEntry] = []
    for table in scope.find_all("table"):
        entries.extend(_entries_from_table(table, base_url, section, label))

    table_links = {e.url for e in entries}
    for a in scope.find_all("a", href=True):
        href: str = a["href"]
        if not href.lower().endswith(".pdf"):
            continue
        full_url = _resolve_url(href, base_url)
        if full_url in table_links:
            continue
        entries.append(PDFEntry(
            name=a.get_text(strip=True) or _url_name(full_url),
            url=full_url,
            section=section,
            section_label=label,
        ))
        table_links.add(full_url)

    return entries


def _entries_from_table(
    table, base_url: str, section: str | None = None, label: str | None = None
) -> list[PDFEntry]:
    rows = table.find_all("tr")
    if len(rows) < 2:
        return []

    date_col = _find_date_column(rows[0])
    entries: list[PDFEntry] = []

    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        a_tag = _find_pdf_anchor(cells)
        if not a_tag:
            continue

        href = a_tag["href"]
        full_url = _resolve_url(href, base_url)
        name = a_tag.get_text(strip=True) or _url_name(full_url)
        row_section = section if section is not None else _section_from_url(full_url)
        row_label = label if label is not None else row_section.replace("_", " ").title()

        upload_date: datetime | None = None
        if date_col is not None and date_col < len(cells):
            upload_date = _parse_date(cells[date_col].get_text(strip=True))

        entries.append(PDFEntry(
            name=name,
            url=full_url,
            section=row_section,
            section_label=row_label,
            upload_date=upload_date,
        ))

    return entries


def _find_date_column(header_row) -> int | None:
    cells = header_row.find_all(["th", "td"])
    for i, cell in enumerate(cells):
        text = cell.get_text(strip=True).lower()
        if "date" in text or "upload" in text or "modified" in text:
            return i
    return None


def _find_pdf_anchor(cells):
    for cell in cells:
        a = cell.find("a", href=lambda h: h and h.lower().endswith(".pdf"))
        if a:
            return a
    return None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _resolve_url(href: str, base_url: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return ASX_BASE + href
    return urljoin(base_url, href)


def _url_name(url: str) -> str:
    from pathlib import Path
    from urllib.parse import urlparse
    return Path(urlparse(url).path).name


def _section_from_url(url: str) -> str:
    path = url.lower()
    if "/waivers" in path:
        return "waivers"
    if "/guidance" in path:
        return "guidance_notes"
    if "/rules" in path:
        return "rules"
    return "other"


def _parse_date(text: str) -> datetime | None:
    if not text or text in {"-", "—", "n/a", "N/A", ""}:
        return None
    try:
        return dateutil_parser.parse(text, dayfirst=True)
    except Exception:
        return None
