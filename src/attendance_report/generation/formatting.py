"""Model values -> the exact strings printed in the report.

The renderers (PDF and HTML) share this, so both print identical text.
"""
from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from ..domain.calendar_he import month_label, weekday_name, weekday_short
from ..domain.models import AttendanceReport, AttendanceRow, ReportSummary
from .layouts import TableLayout


def hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def hours2(value: Decimal) -> str:
    return f"{value:.2f}"


def compact(value: Decimal) -> str:
    """117.00 -> '117', 6.50 -> '6.5' (style of the type A totals box)."""
    text = f"{value.normalize():f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def money(value: Decimal) -> str:
    return f"{value:,.2f} ₪"


def fmt_date(d: date, style: str) -> str:
    return d.strftime("%d/%m/%Y") if style == "dd/mm/yyyy" else f"{d.day}/{d.month}/{d.year % 100:02d}"


def fmt_time(t: time | None, style: str) -> str:
    if t is None:
        return ""
    return t.strftime("%H:%M") if style == "HH:MM" else f"{t.hour}:{t.minute:02d}"


def row_cell(row: AttendanceRow, key: str, table: TableLayout) -> str:
    b, worked = row.buckets, row.has_times
    if key == "date":
        return fmt_date(row.work_date, table.date_style)
    if key == "weekday":
        # always derived from the date -> they can never disagree
        return weekday_name(row.work_date) if table.weekday_style == "long" else weekday_short(row.work_date)
    if key in ("entry", "exit"):
        return fmt_time(getattr(row, key), table.time_style)
    if not worked:                      # empty day: nothing in the number columns
        return row.location if key == "location" else row.note if key == "note" else ""
    values = {
        "location": row.location,
        "break": hhmm(row.break_minutes),
        "total": hours2(row.total_hours),
        "h100": hours2(b.regular_100) if b else "",
        "h125": hours2(b.overtime_125) if b else "",
        "h150": hours2(b.overtime_150) if b else "",
        "shabbat": hours2(b.shabbat_150) if b else "",
        "note": row.note,
    }
    return values[key]


def summary_row_cell(s: ReportSummary, key: str) -> str:
    """The totals line at the bottom of the type A table."""
    values = {
        "date": str(s.days),
        "break": hhmm(s.break_minutes),
        "total": hours2(s.total_hours),
        "h100": hours2(s.buckets.regular_100),
        "h125": hours2(s.buckets.overtime_125),
        "h150": hours2(s.buckets.overtime_150),
        "shabbat": hours2(s.buckets.shabbat_150),
    }
    return values.get(key, "")


def box_value(report: AttendanceReport, key: str, style: str) -> str:
    s = report.summary
    if key == "employee_name":
        return report.employee_name
    if key == "month_label":
        d = report.rows[0].work_date
        return month_label(d.year, d.month)
    if s is None:
        return ""
    raw = {
        "days": Decimal(s.days),
        "total": s.total_hours,
        "h100": s.buckets.regular_100,
        "h125": s.buckets.overtime_125,
        "h150": s.buckets.overtime_150,
        "shabbat": s.buckets.shabbat_150,
        "bonus": s.bonus,
        "travel": s.travel,
        "rate": s.hourly_rate,
        "pay": s.total_pay,
    }[key]
    if raw is None:
        return ""
    return {
        "plain": lambda v: str(v),
        "int": lambda v: str(int(v)),
        "compact": compact,
        "hours2": hours2,
        "money": money,
    }[style](raw)
