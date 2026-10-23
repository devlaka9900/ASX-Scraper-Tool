from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class PDFEntry:
    name: str
    url: str
    section: str                            # filesystem-safe slug, e.g. "rules" | "guidance_notes" | "waivers" | "appendices"
    section_label: str = ""                 # raw section/tab label as scraped, e.g. "Guidance notes"

    upload_date: Optional[datetime] = None  # date shown in the page table
    http_date: Optional[datetime] = None    # HTTP Last-Modified header
    pdf_meta_date: Optional[datetime] = None  # PDF /ModDate or /CreationDate

    resolved_date: Optional[datetime] = None  # best available date (set by analyzer)
    date_source: str = ""                   # "pdf_metadata" | "none"

    local_path: Optional[Path] = None
    page_count: int = 0
    download_error: str = ""

    category: str = ""                      # "updated" | "not_updated" | "no_date"

    @property
    def display_date(self) -> str:
        if self.resolved_date:
            return self.resolved_date.strftime("%Y-%m-%d")
        return "—"

    @property
    def display_section(self) -> str:
        if self.section_label:
            return self.section_label
        return self.section.replace("_", " ").title()
