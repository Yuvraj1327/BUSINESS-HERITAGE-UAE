"""CSV and Excel export of a `ReportOut` (Step 12). The export is produced from the very same rows as the screen:
title, applied filters, generation time (Dubai) and the summary totals first, then the complete table (no paging)."""

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font

from app.schemas.analytics import ReportColumn, ReportOut
from app.utils.time import BUSINESS_TZ

CSV_TYPE = "text/csv; charset=utf-8"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def filename(report: ReportOut, ext: str) -> str:
    f = report.filters
    return f"alsafa_{report.key}_{f.date_from.isoformat()}_{f.date_to.isoformat()}.{ext}"


def _meta(report: ReportOut) -> list[tuple[str, str]]:
    f = report.filters
    meta = [
        ("Report", report.title),
        ("Company", "ALSAFA Heritage Laundry"),
        ("Generated (Dubai time)", report.generated_at.strftime("%Y-%m-%d %H:%M")),
        ("Date range", f"{f.date_from.isoformat()} to {f.date_to.isoformat()}"),
        ("Grouping", f.period),
        ("Branch", f.branch_name),
        ("Currency", "AED"),
    ]
    if f.account:
        meta.append(("Account", f.account))
    return meta


def _text(v: Any) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(_DANGEROUS) else s  # stops spreadsheet formula injection


def _dubai(v: datetime) -> datetime:
    """Business time (Asia/Dubai) as a naive wall-clock value, which is what both file formats can hold."""
    return v.astimezone(BUSINESS_TZ).replace(tzinfo=None) if v.tzinfo else v


def _csv_cell(v: Any, col: ReportColumn) -> str:
    if v is None:
        return ""
    if col.kind == "money":
        return f"{Decimal(str(v)):.2f}"
    if col.kind in ("int", "pct"):
        return str(v)
    if isinstance(v, datetime):
        return _dubai(v).strftime("%Y-%m-%d %H:%M")
    if isinstance(v, date):
        return v.isoformat()
    return _text(v)


def to_csv(report: ReportOut) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    for k, v in _meta(report):
        w.writerow([k, v])
    w.writerow([])
    if report.summary:
        w.writerow(["Summary totals"])
        for s in report.summary:
            col = ReportColumn(key="s", label=s.label, kind=s.kind)
            w.writerow([s.label, _csv_cell(s.value, col)])
        w.writerow([])
    w.writerow([c.label for c in report.columns])
    for r in report.rows:
        w.writerow([_csv_cell(r.get(c.key), c) for c in report.columns])
    if report.notes:
        w.writerow([])
        for n in report.notes:
            w.writerow(["Note", n])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM so Excel reads UTF-8 correctly


def _xl_value(v: Any, col: ReportColumn) -> Any:
    if v is None:
        return None
    if col.kind == "money":
        return float(Decimal(str(v)))
    if col.kind in ("int", "pct"):
        return float(v) if col.kind == "pct" else int(v)
    if isinstance(v, datetime):
        return _dubai(v)  # Excel has no time zones: write Dubai wall-clock time
    if isinstance(v, date):
        return v
    return _text(v)


def to_xlsx(report: ReportOut) -> bytes:
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Report")
    bold = Font(bold=True)
    widths = [max(14, len(c.label) + 2) for c in report.columns]
    for i, wd in enumerate(widths):
        ws.column_dimensions["ABCDEFGHIJKLMNOPQRSTUVWXYZ"[i]].width = min(wd, 48)

    def head(text: str) -> Any:
        c = WriteOnlyCell(ws, value=text)
        c.font = bold
        return c

    ws.append([head("ALSAFA Heritage Laundry"), report.title])
    for k, v in _meta(report)[2:]:
        ws.append([head(k), v])
    ws.append([])
    if report.summary:
        ws.append([head("Summary totals")])
        for s in report.summary:
            col = ReportColumn(key="s", label=s.label, kind=s.kind)
            cell = WriteOnlyCell(ws, value=_xl_value(s.value, col))
            if s.kind == "money":
                cell.number_format = '#,##0.00 "AED"'
            ws.append([head(s.label), cell])
        ws.append([])
    ws.append([head(c.label) for c in report.columns])
    for r in report.rows:
        cells = []
        for c in report.columns:
            cell = WriteOnlyCell(ws, value=_xl_value(r.get(c.key), c))
            if c.kind == "money":
                cell.number_format = "#,##0.00"
            elif c.kind == "date":
                cell.number_format = "yyyy-mm-dd"
            elif c.kind == "datetime":
                cell.number_format = "yyyy-mm-dd hh:mm"
            elif c.kind == "pct":
                cell.number_format = "0.0"
            cells.append(cell)
        ws.append(cells)
    if report.notes:
        ws.append([])
        for n in report.notes:
            ws.append([head("Note"), n])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
