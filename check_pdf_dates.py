"""
Standalone date checker — loops through all downloaded PDFs,
reads their internal metadata date, and shows whether each is
updated or not relative to your cutoff date.

Usage:
    python check_pdf_dates.py

You will be prompted for the project ID and cutoff date.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import fitz
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

console = Console()


def _parse_pdf_date(raw: str) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("D:"):
        raw = raw[2:]
    digits = raw[:14]
    for fmt, length in (("%Y%m%d%H%M%S", 14), ("%Y%m%d%H%M", 12), ("%Y%m%d", 8)):
        try:
            return datetime.strptime(digits[:length], fmt)
        except ValueError:
            pass
    return None


def check_pdfs(downloads_dir: Path, cutoff: datetime) -> None:
    pdfs = sorted(downloads_dir.rglob("*.pdf"))
    if not pdfs:
        console.print(f"[red]No PDFs found under {downloads_dir}[/red]")
        return

    console.print(f"\nFound [bold]{len(pdfs)}[/bold] PDFs. Checking metadata dates against cutoff [bold]{cutoff.date()}[/bold]...\n")

    table = Table(show_header=True, header_style="bold cyan", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("File", no_wrap=False, min_width=40)
    table.add_column("PDF Date", width=12)
    table.add_column("Source", width=14)
    table.add_column("Status", width=14)

    updated = not_updated = no_date = 0

    for i, pdf_path in enumerate(pdfs, 1):
        try:
            doc = fitz.open(str(pdf_path))
            meta = doc.metadata
            doc.close()
        except Exception as e:
            table.add_row(str(i), pdf_path.name, "—", "error", f"[red]Error: {e}[/red]")
            continue

        # Try modDate first, then creationDate
        date = None
        source = "—"
        for key in ("modDate", "creationDate"):
            raw = meta.get(key, "")
            parsed = _parse_pdf_date(raw)
            if parsed:
                date = parsed
                source = key
                break

        if date is None:
            status = "[yellow]❓ No Date[/yellow]"
            date_str = "—"
            no_date += 1
        elif date > cutoff:
            status = "[green]✅ Updated[/green]"
            date_str = date.strftime("%Y-%m-%d")
            updated += 1
        else:
            status = "[dim]⏸ Not Updated[/dim]"
            date_str = date.strftime("%Y-%m-%d")
            not_updated += 1

        table.add_row(str(i), pdf_path.name, date_str, source, status)

    console.print(table)
    console.print(f"\n[bold green]✅ Updated:[/bold green]     {updated}")
    console.print(f"[bold yellow]❓ No Date:[/bold yellow]     {no_date}")
    console.print(f"[dim]⏸ Not Updated:[/dim]  {not_updated}")
    console.print(f"[dim]Total:[/dim]           {len(pdfs)}\n")


def main() -> None:
    project_id = Prompt.ask("[bold]Project ID[/bold] (e.g. 123)").strip()
    downloads_dir = Path("output") / project_id / "downloads"

    if not downloads_dir.exists():
        console.print(f"[red]Directory not found: {downloads_dir}[/red]")
        sys.exit(1)

    while True:
        raw = Prompt.ask("[bold]Cutoff Date[/bold] [dim](YYYY-MM-DD)[/dim]").strip()
        try:
            cutoff = datetime.strptime(raw, "%Y-%m-%d")
            break
        except ValueError:
            console.print("[red]Invalid date. Use YYYY-MM-DD (e.g. 2024-01-01).[/red]")

    check_pdfs(downloads_dir, cutoff)


if __name__ == "__main__":
    main()
