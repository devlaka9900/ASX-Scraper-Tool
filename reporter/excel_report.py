"""
Generates report.xlsx inside the project output folder as a single sheet,
single table listing every downloaded book (tagged with its Section), plus
a right-hand summary panel of formulas that behaves like a pivot table —
openpyxl cannot write a real interactive Excel PivotTable object, so this
recalculates from the table automatically instead of being a static snapshot.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from models import PDFEntry
from utils.file_utils import slugify
from utils.logger import get_logger

log = get_logger(__name__)

_BOOK_STATUS_LABEL = {
    "updated":        "Updated",
    "not_updated":    "Not Updated",
    "no_date":        "No Date Found",
    "download_error": "Download Error",
}
_BOOK_STATUS_FILL = {
    "Updated":        "E2EFDA",
    "Not Updated":    "F2F2F2",
    "No Date Found":  "FFF2CC",
    "Download Error": "FCE4E4",
}

_DEV_STATUSES = ["Todo", "Inprogress", "In-review", "Fixing"]
_DEV_FILL = {
    "Todo":       "D9D9D9",
    "Inprogress": "BDD7EE",
    "In-review":  "F8CBAD",
    "Fixing":     "FFC7CE",
}

_QA_STATUSES = ["QA PASS", "QA Fail", "Reviewing"]
_QA_FILL = {
    "QA PASS":   "C6EFCE",
    "QA Fail":   "FFC7CE",
    "Reviewing": "FFEB9C",
}

_NAVY = "305496"
_HEADER_FILL = PatternFill("solid", fgColor=_NAVY)
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_BANNER_FONT = Font(bold=True, color="FFFFFF", size=12)
_ZEBRA_FILL = PatternFill("solid", fgColor="F2F2F2")

_THIN_SIDE = Side(style="thin", color="B7B7B7")
_THIN_BORDER = Border(left=_THIN_SIDE, right=_THIN_SIDE, top=_THIN_SIDE, bottom=_THIN_SIDE)
_GROUP_BOTTOM = Border(
    left=_THIN_SIDE, right=_THIN_SIDE, top=_THIN_SIDE,
    bottom=Side(style="medium", color="808080"),
)

# title, min width, max width
_COLUMNS = [
    ("Document ID", 12, 16),
    ("Section", 12, 24),
    ("Document Name", 20, 60),
    ("Date Modified/Created", 14, 22),
    ("Book Status", 14, 18),
    ("Page Count", 10, 12),
    ("Dev Status", 12, 16),
    ("QA Status", 12, 16),
]

_GUTTER_COL = len(_COLUMNS) + 1   # one blank column between table and panel
_PANEL_COL = _GUTTER_COL + 1
_PANEL_SPAN = 4


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def write_excel_report(
    entries: list[PDFEntry],
    dirs: dict[str, Path],
    project_id: str,
    url: str,
    cutoff: datetime,
) -> None:
    groups = _group_by_section(entries)
    ordered_entries = [e for group in groups.values() for e in group]

    wb = Workbook()
    ws = wb.active
    ws.title = "Report"

    _write_table(ws, groups, ordered_entries)
    _write_summary_panel(ws, groups, ordered_entries, project_id, url, cutoff)

    out = dirs["base"] / "report.xlsx"
    wb.save(out)
    log.info("Excel report → %s", out)


# --------------------------------------------------------------------------- #
# Grouping / document IDs
# --------------------------------------------------------------------------- #

def _group_by_section(entries: list[PDFEntry]) -> dict[str, list[PDFEntry]]:
    groups: dict[str, list[PDFEntry]] = {}
    for entry in entries:
        groups.setdefault(entry.display_section, []).append(entry)
    return groups


def _section_prefix(group_entries: list[PDFEntry], label: str, used: set[str]) -> str:
    slug = group_entries[0].section if group_entries else slugify(label)
    base_prefix = (slug[:3] or "sec").upper()
    prefix = base_prefix
    n = 2
    while prefix in used:
        prefix = f"{base_prefix}{n}"
        n += 1
    used.add(prefix)
    return prefix


# --------------------------------------------------------------------------- #
# Main table
# --------------------------------------------------------------------------- #

def _write_table(ws, groups: dict[str, list[PDFEntry]], ordered_entries: list[PDFEntry]) -> None:
    for col, (title, _min, _max) in enumerate(_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.border = _THIN_BORDER
        cell.alignment = Alignment(horizontal="center")
    ws.row_dimensions[1].height = 20

    col_max_len = [len(title) for title, _min, _max in _COLUMNS]
    used_prefixes: set[str] = set()
    row = 2
    for label, group_entries in groups.items():
        prefix = _section_prefix(group_entries, label, used_prefixes)
        for i, entry in enumerate(group_entries, start=1):
            is_last_in_group = i == len(group_entries)
            values = [
                f"{prefix}-{i:04d}",
                label,
                entry.name,
                entry.display_date,
                _BOOK_STATUS_LABEL.get(entry.category, entry.category or "—"),
                entry.page_count or 0,
                None,   # Dev Status — analyst fills in
                None,   # QA Status — analyst fills in
            ]
            for col, value in enumerate(values, start=1):
                cell = ws.cell(row=row, column=col, value=value)
                cell.border = _GROUP_BOTTOM if is_last_in_group else _THIN_BORDER
                cell.alignment = Alignment(horizontal="left" if col == 3 else "center")
                if row % 2 == 0:
                    cell.fill = _ZEBRA_FILL
                col_max_len[col - 1] = max(col_max_len[col - 1], len(str(value)) if value is not None else 0)

            status_cell = ws.cell(row=row, column=5)
            fill_color = _BOOK_STATUS_FILL.get(status_cell.value)
            if fill_color:
                status_cell.fill = PatternFill("solid", fgColor=fill_color)

            row += 1

    last_row = row - 1
    for col, (title, min_w, max_w) in enumerate(_COLUMNS, start=1):
        width = max(min_w, min(max_w, col_max_len[col - 1] + 2))
        ws.column_dimensions[get_column_letter(col)].width = width

    ws.freeze_panes = "C2"
    if last_row > 1:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(_COLUMNS))}{last_row}"
        _apply_status_column(ws, last_row, column=7, statuses=_DEV_STATUSES, fills=_DEV_FILL)
        _apply_status_column(ws, last_row, column=8, statuses=_QA_STATUSES, fills=_QA_FILL)


def _apply_status_column(ws, last_row: int, column: int, statuses: list[str], fills: dict[str, str]) -> None:
    col_letter = get_column_letter(column)
    cell_range = f"{col_letter}2:{col_letter}{last_row}"

    dv = DataValidation(type="list", formula1=f'"{",".join(statuses)}"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(cell_range)

    for status, color in fills.items():
        fill = PatternFill("solid", fgColor=color)
        ws.conditional_formatting.add(
            cell_range,
            FormulaRule(formula=[f'${col_letter}2="{status}"'], fill=fill),
        )


# --------------------------------------------------------------------------- #
# Summary / pivot-style panel
# --------------------------------------------------------------------------- #

def _banner(ws, row: int, col: int, text: str) -> None:
    ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col + _PANEL_SPAN - 1)
    cell = ws.cell(row=row, column=col, value=text)
    cell.font = _BANNER_FONT
    cell.fill = _HEADER_FILL
    cell.alignment = Alignment(horizontal="left", vertical="center")
    for c in range(col, col + _PANEL_SPAN):
        ws.cell(row=row, column=c).border = _THIN_BORDER
    ws.row_dimensions[row].height = 20


def _kv_row(ws, row: int, col: int, key: str, value) -> None:
    kc = ws.cell(row=row, column=col, value=key)
    kc.font = Font(bold=True)
    kc.border = _THIN_BORDER
    vc = ws.cell(row=row, column=col + 1, value=value)
    vc.border = _THIN_BORDER
    vc.alignment = Alignment(wrap_text=True)


def _write_summary_panel(
    ws,
    groups: dict[str, list[PDFEntry]],
    ordered_entries: list[PDFEntry],
    project_id: str,
    url: str,
    cutoff: datetime,
) -> None:
    last_row = max(len(ordered_entries) + 1, 2)
    col = _PANEL_COL

    ws.column_dimensions[get_column_letter(_GUTTER_COL)].width = 3
    ws.column_dimensions[get_column_letter(col)].width = 26
    for c in range(col + 1, col + _PANEL_SPAN):
        ws.column_dimensions[get_column_letter(c)].width = 16

    id_col = get_column_letter(1)
    section_col = get_column_letter(2)
    status_col = get_column_letter(5)
    pages_col = get_column_letter(6)
    dev_col = get_column_letter(7)
    qa_col = get_column_letter(8)

    row = 1
    _banner(ws, row, col, "Summary")
    row += 1
    for key, value in [
        ("Project ID", project_id),
        ("Source URL", url),
        ("Cutoff Date", cutoff.strftime("%Y-%m-%d")),
        ("Run At", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    ]:
        _kv_row(ws, row, col, key, value)
        row += 1

    row += 1
    _banner(ws, row, col, "Insights")
    row += 1
    for key, formula in [
        ("Total Books", f"=COUNTA({id_col}2:{id_col}{last_row})"),
        ("Total Page Count", f"=SUM({pages_col}2:{pages_col}{last_row})"),
        ("Number of Updated Books", f'=COUNTIF({status_col}2:{status_col}{last_row},"Updated")'),
        ("Updated Page Count",
         f'=SUMIFS({pages_col}2:{pages_col}{last_row},{status_col}2:{status_col}{last_row},"Updated")'),
        ("Number of Not Updated Books", f'=COUNTIF({status_col}2:{status_col}{last_row},"Not Updated")'),
        ("Books With No Date Found", f'=COUNTIF({status_col}2:{status_col}{last_row},"No Date Found")'),
        ("Download Errors", f'=COUNTIF({status_col}2:{status_col}{last_row},"Download Error")'),
    ]:
        _kv_row(ws, row, col, key, formula)
        row += 1

    row += 1
    _banner(ws, row, col, "Section Breakdown")
    row += 1
    header_row = row
    for i, title in enumerate(["Section", "Books", "Updated", "Total Pages"]):
        cell = ws.cell(row=header_row, column=col + i, value=title)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.border = _THIN_BORDER
    row += 1
    for label in groups:
        label_ref = f"{get_column_letter(col)}{row}"
        ws.cell(row=row, column=col, value=label).border = _THIN_BORDER
        ws.cell(row=row, column=col + 1,
                value=f"=COUNTIF({section_col}2:{section_col}{last_row},{label_ref})").border = _THIN_BORDER
        ws.cell(row=row, column=col + 2,
                value=f'=COUNTIFS({section_col}2:{section_col}{last_row},{label_ref},'
                      f'{status_col}2:{status_col}{last_row},"Updated")').border = _THIN_BORDER
        ws.cell(row=row, column=col + 3,
                value=f"=SUMIFS({pages_col}2:{pages_col}{last_row},{section_col}2:{section_col}{last_row},{label_ref})"
                ).border = _THIN_BORDER
        if (row - header_row) % 2 == 0:
            for c in range(col, col + 4):
                ws.cell(row=row, column=c).fill = _ZEBRA_FILL
        row += 1

    row += 1
    _banner(ws, row, col, "Dev Status Breakdown")
    row += 1
    for status in _DEV_STATUSES:
        ws.cell(row=row, column=col, value=status).border = _THIN_BORDER
        ws.cell(row=row, column=col + 1,
                value=f'=COUNTIF({dev_col}2:{dev_col}{last_row},"{status}")').border = _THIN_BORDER
        row += 1

    row += 1
    _banner(ws, row, col, "QA Status Breakdown")
    row += 1
    for status in _QA_STATUSES:
        ws.cell(row=row, column=col, value=status).border = _THIN_BORDER
        ws.cell(row=row, column=col + 1,
                value=f'=COUNTIF({qa_col}2:{qa_col}{last_row},"{status}")').border = _THIN_BORDER
        row += 1
