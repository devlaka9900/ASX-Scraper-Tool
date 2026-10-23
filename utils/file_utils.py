import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

from config import OUTPUT_ROOT, FOLDER_UPDATED, FOLDER_NO_DATE


def slugify(label: str) -> str:
    """Filesystem-safe slug for a scraped section/tab label, e.g. 'Guidance notes' -> 'guidance_notes'."""
    slug = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
    return slug or "other"


def make_output_dirs(
    project_id: str, sections: list[str], root: Path | None = None
) -> dict[str, Path]:
    """Create the project's output folders. *sections* are the distinct section
    slugs discovered while scraping — one downloads/{slug} subfolder per section.
    *root* overrides the default output root (used by the GUI)."""
    base = (root or OUTPUT_ROOT) / project_id
    dirs: dict[str, Path] = {
        "base": base,
        "downloads": base / "downloads",
        "updated":   base / FOLDER_UPDATED,
        "no_date":   base / FOLDER_NO_DATE,
    }
    for slug in sections:
        dirs[slug] = base / "downloads" / slug
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def section_dir(dirs: dict[str, Path], section: str) -> Path:
    key = section if section in dirs else "downloads"
    return dirs[key]


def url_filename(url: str) -> str:
    return Path(urlparse(url).path).name or "document.pdf"


def safe_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", "_", name.strip())
    name = name[:200]
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


def copy_pdf(src: Path, dest_dir: Path) -> Path:
    dest = dest_dir / src.name
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{src.stem}_{counter}{src.suffix}"
        counter += 1
    shutil.copy2(src, dest)
    return dest
