"""
ASX Reg Data
───────────────
Scrapes an ASX rules/guidance/waivers page, downloads every PDF,
identifies which were updated after a given cutoff date, and
produces structured output folders plus two markdown reports.

Usage:
    python main.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule

from analyzer.date_checker import analyse
from reporter.excel_report import write_excel_report
from reporter.report_generator import write_reports
from scraper.page_scraper import scrape_pdf_links
from scraper.pdf_downloader import download_all
from utils.file_utils import make_output_dirs
from utils.logger import get_logger

log = get_logger(__name__)
console = Console()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main() -> None:
    console.print(Panel.fit(
        "[bold cyan]ASX Reg Data[/bold cyan]\n"
        "[dim]Scrape · Download · Analyse · Report[/dim]\n"
        "[dim]ASX Domain Ownership — binura.lakshan@cube.global[/dim]",
        border_style="cyan",
    ))
    console.print()

    project_id, url, cutoff = _prompt_inputs()

    # 1 — Scrape
    console.print(Rule("[cyan]Scraping page for PDF links[/cyan]"))
    try:
        entries = scrape_pdf_links(url)
    except Exception as exc:
        console.print(f"[red]Scraping failed:[/red] {exc}")
        console.print("[yellow]Tip:[/yellow] Check the URL is reachable and that "
                      "[bold]pip install -r requirements.txt[/bold] completed successfully.")
        sys.exit(1)

    if not entries:
        console.print("[yellow]No PDF links found on that page. "
                      "Check the URL and try again.[/yellow]")
        sys.exit(0)

    console.print(f"  Found [bold]{len(entries)}[/bold] PDFs across "
                  f"{_section_summary(entries)}\n")

    console.print(Rule("[cyan]Setting up output folders[/cyan]"))
    sections = list(dict.fromkeys(e.section for e in entries))
    dirs = make_output_dirs(project_id, sections)
    console.print(f"  Output → [green]{dirs['base'].resolve()}[/green]\n")

    # 2 — Download
    console.print(Rule("[cyan]Downloading PDFs[/cyan]"))
    download_all(entries, dirs)
    console.print()

    # 3 — Analyse
    console.print(Rule("[cyan]Analysing dates[/cyan]"))
    analyse(entries, cutoff, dirs)
    console.print()

    # 4 — Report
    console.print(Rule("[cyan]Writing reports[/cyan]"))
    write_reports(entries, dirs, project_id, url, cutoff)
    write_excel_report(entries, dirs, project_id, url, cutoff)

    # 5 — Final summary
    _print_summary(entries, dirs, cutoff)


# --------------------------------------------------------------------------- #
# Input prompts
# --------------------------------------------------------------------------- #

def _prompt_inputs() -> tuple[str, str, datetime]:
    project_id = Prompt.ask("[bold]DocumentId[/bold]").strip()
    if not project_id:
        console.print("[red]DocumentId cannot be empty.[/red]")
        sys.exit(1)

    url = Prompt.ask("[bold]Page URL[/bold]").strip()
    if not url.startswith("http"):
        console.print("[red]URL must start with http:// or https://[/red]")
        sys.exit(1)

    while True:
        raw = Prompt.ask("[bold]Cutoff Date[/bold] [dim](YYYY-MM-DD)[/dim]").strip()
        try:
            cutoff = datetime.strptime(raw, "%Y-%m-%d")
            break
        except ValueError:
            console.print("[red]Invalid date. Use YYYY-MM-DD format (e.g. 2024-01-01).[/red]")

    console.print()
    console.print(f"  DocumentId : [bold]{project_id}[/bold]")
    console.print(f"  URL        : {url}")
    console.print(f"  Cutoff     : [bold]{cutoff.strftime('%Y-%m-%d')}[/bold]")
    console.print()

    return project_id, url, cutoff


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _section_summary(entries) -> str:
    from collections import Counter
    counts = Counter(e.display_section for e in entries)
    parts = [f"{count} {label}" for label, count in sorted(counts.items())]
    return ", ".join(parts)


def _print_summary(entries, dirs: dict[str, Path], cutoff: datetime) -> None:
    updated    = [e for e in entries if e.category == "updated"]
    no_date    = [e for e in entries if e.category == "no_date"]
    not_upd    = [e for e in entries if e.category == "not_updated"]
    errors     = [e for e in entries if e.category == "download_error"]

    console.print()
    console.print(Panel(
        f"[bold green]✅ Updated (after {cutoff.date()}):[/bold green]  {len(updated)}\n"
        f"[bold yellow]❓ No date found:[/bold yellow]               {len(no_date)}\n"
        f"[dim]⏸  Not updated:[/dim]                        {len(not_upd)}\n"
        f"[bold red]❌ Download errors:[/bold red]                  {len(errors)}\n\n"
        f"[cyan]Updated_Books[/cyan]  → {dirs['updated'].resolve()}\n"
        f"[cyan]Date_Not_Found[/cyan] → {dirs['no_date'].resolve()}\n"
        f"[cyan]Reports[/cyan]        → {dirs['base'].resolve()}\n"
        f"[cyan]Excel Report[/cyan]   → {(dirs['base'] / 'report.xlsx').resolve()}",
        title="[bold]Run Complete[/bold]",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
