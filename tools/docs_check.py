"""Structural check of docs/index.html (no browser needed).

    python tools/docs_check.py

Asserts: every tab button has exactly one panel and vice versa, ids are unique,
internal #anchors resolve, the file has no external resources (it must work offline),
and mentions the current app version.
"""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.version import APP_VERSION  # noqa: E402

DOC = ROOT / "docs" / "index.html"


class Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: list[str] = []
        self.tabs: list[dict] = []
        self.panels: list[dict] = []
        self.links: list[str] = []
        self.resources: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.append(a["id"])
        if a.get("role") == "tab":
            self.tabs.append(a)
        if a.get("role") == "tabpanel":
            self.panels.append(a)
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        for key in ("src", "href"):
            if key in a and tag in ("script", "link", "img", "iframe", "source"):
                self.resources.append(a[key])


def main() -> int:
    html = DOC.read_text(encoding="utf-8")
    c = Collector()
    c.feed(html)
    problems: list[str] = []

    dupes = {i for i in c.ids if c.ids.count(i) > 1}
    if dupes:
        problems.append(f"duplicate ids: {sorted(dupes)}")

    panel_ids = {p["id"] for p in c.panels}
    for t in c.tabs:
        panel = t.get("aria-controls", "")
        if panel not in panel_ids:
            problems.append(f"tab {t.get('id')} controls missing panel {panel!r}")
        if t.get("data-tab") and f"tab-{t['data-tab']}" != panel:
            problems.append(f"tab {t.get('id')}: data-tab does not match aria-controls")
    tab_targets = {t.get("aria-controls") for t in c.tabs}
    for p in c.panels:
        if p["id"] not in tab_targets:
            problems.append(f"panel {p['id']} has no tab button")
        if p.get("aria-labelledby") not in set(c.ids):
            problems.append(f"panel {p['id']} aria-labelledby points nowhere")

    for href in c.links:
        if href.startswith("#") and href[1:] not in set(c.ids):
            problems.append(f"broken anchor {href}")
        if re.match(r"https?://", href):
            problems.append(f"external link {href}")
    for res in c.resources:
        problems.append(f"external/linked resource {res} (docs must be self-contained)")
    if re.search(r"url\(\s*['\"]?https?://|@import", html):
        problems.append("CSS references an external resource")
    if f"v{APP_VERSION}" not in html:
        problems.append(f"docs do not mention v{APP_VERSION}")
    # versioning rule MAJOR.FEATURE.FIX: three numbers, and a Changelog entry for this release
    if not re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION):
        problems.append(f"APP_VERSION {APP_VERSION!r} must look like MAJOR.FEATURE.FIX (e.g. 1.2.0)")
    changelog = re.search(r'id="tab-changelog".*?</section>', html, flags=re.S)
    if not changelog or f"<h3>{APP_VERSION}</h3>" not in changelog.group(0):
        problems.append(f"the Changelog tab has no '<h3>{APP_VERSION}</h3>' entry")
    if "@" in re.sub(r"<style.*?</style>|<script.*?</script>", "", html, flags=re.S) and \
            re.search(r"[\w.]+@[\w.]+\.\w+", re.sub(r"<style.*?</style>|<script.*?</script>", "", html, flags=re.S)):
        problems.append("an e-mail address appears in the docs (the maintainer address must not)")

    print(f"{len(c.tabs)} tabs, {len(c.panels)} panels, {len(c.ids)} ids, {len(c.links)} links")
    if problems:
        for p in problems:
            print("FAIL ", p)
        return 1
    print("DOCS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
