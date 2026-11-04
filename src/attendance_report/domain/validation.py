"""Invariants: rules that must hold for every report we *generate*.

They are written once, here, and used in three places:
  1. after parsing  -> reported as warnings (the source itself may break them;
     the sample file does: 08:00-15:00 minus 00:30 is 6.50, but it prints 6.19)
  2. after transforming -> any violation is a bug, the pipeline stops
  3. in the test-suite
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal

from .models import AttendanceReport, ReportSummary, ReportType, minutes_to_hours


@dataclass(frozen=True)
class Limits:
    earliest_entry: time = time(6, 0)
    latest_exit: time = time(22, 0)
    min_daily_hours: Decimal = Decimal("3")
    max_daily_hours: Decimal = Decimal("12")
    max_monthly_hours: Decimal = Decimal("260")


def check_invariants(report: AttendanceReport, limits: Limits = Limits(),
                     expected_summary: ReportSummary | None = None) -> list[str]:
    """``expected_summary``: the totals recomputed from the rows (how they are
    computed differs per report type, so the caller - the strategy - supplies it)."""
    errors: list[str] = []
    # empty lines may run into the next month (type B prints 31 lines always),
    # but every *worked* day must be in the report's month
    if report.rows:
        first = report.rows[0].work_date
        for r in report.rows:
            if r.has_times and (r.work_date.year, r.work_date.month) != (first.year, first.month):
                errors.append(f"{r.work_date:%d/%m/%Y}: worked day outside the report month")

    dates = [r.work_date for r in report.rows]
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        errors.append("dates are not strictly increasing")

    for r in report.rows:
        tag = r.work_date.strftime("%d/%m/%Y")
        if not r.has_times:
            if r.total_hours != 0:
                errors.append(f"{tag}: hours without entry/exit")
            continue
        if r.exit <= r.entry:
            errors.append(f"{tag}: exit {r.exit} is not after entry {r.entry}")
        if r.entry < limits.earliest_entry or r.exit > limits.latest_exit:
            errors.append(f"{tag}: times outside working window")
        if r.net_minutes <= 0:
            errors.append(f"{tag}: break is longer than the shift")
            continue
        if r.total_hours != minutes_to_hours(r.net_minutes):
            errors.append(f"{tag}: total {r.total_hours} != exit-entry-break "
                          f"{minutes_to_hours(r.net_minutes)}")
        if not limits.min_daily_hours <= r.total_hours <= limits.max_daily_hours:
            errors.append(f"{tag}: {r.total_hours} hours is outside the daily range")
        if report.report_type is ReportType.TYPE_A:
            if r.buckets is None:
                errors.append(f"{tag}: missing 100/125/150 split")
            else:
                if r.buckets.total != r.total_hours:
                    errors.append(f"{tag}: 100/125/150/Shabbat do not add up to total")
                if r.is_shabbat and r.buckets.shabbat_150 != r.total_hours:
                    errors.append(f"{tag}: Shabbat hours not in the Shabbat column")
                if r.buckets.regular_100 > 0 and r.buckets.overtime_150 > 0 \
                        and r.buckets.overtime_125 == 0:
                    errors.append(f"{tag}: 150% overtime without 125% first")
                if not r.is_shabbat and r.buckets.shabbat_150 != 0:
                    errors.append(f"{tag}: Shabbat hours on a weekday")

    if report.summary is not None and expected_summary is not None:
        if report.summary != expected_summary:
            errors.append("summary does not equal the sum of the rows")
        if expected_summary.total_hours > limits.max_monthly_hours:
            errors.append(f"monthly total {expected_summary.total_hours} is above the limit")
    return errors

