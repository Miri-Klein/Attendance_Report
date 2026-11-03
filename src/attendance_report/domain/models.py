"""The contract between all pipeline stages.

From here on nobody knows which PDF (or which OCR engine) the data came from.
Parsers produce an AttendanceReport, the transformation turns one
AttendanceReport into a new one, and renderers only ever read it.

Design choices (see DECISIONS.md):
* Times are ``datetime.time`` and durations are whole minutes (``int``).
  Strings are parsed exactly once, in the parser, and formatted exactly once,
  in the renderer. All arithmetic happens on numbers.
* Hour amounts shown in the report (6.19, 147.55 ...) are ``Decimal`` with two
  places, so that sums are exact and the summary always equals the rows.
* Everything is ``frozen``: the transformation cannot mutate the source report
  by accident, it must build a new object.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

TWO_PLACES = Decimal("0.01")


class ReportType(str, Enum):
    TYPE_A = "TYPE_A"  # agency report: location, break, 100/125/150/Shabbat split, totals row + box
    TYPE_B = "TYPE_B"  # employee card: every day of the month, entry/exit/total/notes, pay box on top


def minutes_to_hours(minutes: int) -> Decimal:
    """510 minutes -> Decimal('8.50')."""
    return (Decimal(minutes) / Decimal(60)).quantize(TWO_PLACES, ROUND_HALF_UP)


def time_to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def minutes_to_time(m: int) -> time:
    if not 0 <= m < 24 * 60:
        raise ValueError(f"minute-of-day out of range: {m}")
    return time(m // 60, m % 60)


@dataclass(frozen=True)
class HourBuckets:
    """Split of a day's (or a month's) hours by pay rate. Type A only."""

    regular_100: Decimal = Decimal("0.00")
    overtime_125: Decimal = Decimal("0.00")
    overtime_150: Decimal = Decimal("0.00")
    shabbat_150: Decimal = Decimal("0.00")

    @property
    def total(self) -> Decimal:
        return self.regular_100 + self.overtime_125 + self.overtime_150 + self.shabbat_150

    def __add__(self, other: "HourBuckets") -> "HourBuckets":
        return HourBuckets(
            self.regular_100 + other.regular_100,
            self.overtime_125 + other.overtime_125,
            self.overtime_150 + other.overtime_150,
            self.shabbat_150 + other.shabbat_150,
        )


@dataclass(frozen=True)
class AttendanceRow:
    """One line of the attendance table.

    Fields marked "A" exist only in type A reports; in type B they keep their
    neutral default. ``total_hours`` is stored (not only computed) because the
    source document prints it and we must be able to read a source whose
    numbers do not add up (the sample files really do contain such rows).
    """

    work_date: date
    entry: time | None             # None = no times on this day (e.g. vacation)
    exit: time | None
    total_hours: Decimal           # as printed in the "סה"כ" column
    break_minutes: int = 0         # A
    location: str = ""            # A ("מקום")
    buckets: HourBuckets | None = None  # A: 100% / 125% / 150% / Shabbat
    note: str = ""                # B ("הערות")

    @property
    def has_times(self) -> bool:
        return self.entry is not None and self.exit is not None

    @property
    def net_minutes(self) -> int:
        """Exit - entry - break, in minutes. 0 if the day has no times."""
        if not self.has_times:
            return 0
        return time_to_minutes(self.exit) - time_to_minutes(self.entry) - self.break_minutes

    @property
    def is_shabbat(self) -> bool:
        return self.work_date.weekday() == 5  # Monday=0 ... Saturday=5


@dataclass(frozen=True)
class ReportSummary:
    """Totals. Type A prints them as the last table row and again in a box;
    type B prints days / hours / rate / pay in a box above the table."""

    days: int
    break_minutes: int
    total_hours: Decimal
    buckets: HourBuckets
    bonus: Decimal = Decimal("0")     # A: passed through, not derived from rows
    travel: Decimal = Decimal("0")    # A: passed through, not derived from rows
    hourly_rate: Decimal | None = None  # B: passed through ("מחיר לשעה")
    total_pay: Decimal | None = None    # B: hours x rate


@dataclass(frozen=True)
class AttendanceReport:
    report_type: ReportType
    header_lines: tuple[str, ...]     # printed above the table, kept verbatim
    rows: tuple[AttendanceRow, ...]
    summary: ReportSummary | None = None
    employee_name: str = ""
    employee_id: str = ""
    source_name: str = ""            # file name, for logging only
    warnings: tuple[str, ...] = field(default=(), compare=False)


def compute_summary(rows: tuple[AttendanceRow, ...] | list[AttendanceRow],
                    bonus: Decimal = Decimal("0"),
                    travel: Decimal = Decimal("0")) -> ReportSummary:
    """Type A totals: sums of the *rounded* per-row values that are printed,
    so a reader adding up the column on paper gets exactly the printed total
    (the scan: 22 x 6.50 = 143.00)."""
    buckets = HourBuckets()
    for r in rows:
        if r.buckets is not None:
            buckets = buckets + r.buckets
    return ReportSummary(
        days=sum(1 for r in rows if r.has_times),
        break_minutes=sum(r.break_minutes for r in rows if r.has_times),
        total_hours=sum((r.total_hours for r in rows), Decimal("0.00")),
        buckets=buckets,
        bonus=bonus,
        travel=travel,
    )


def compute_pay_summary(rows: tuple[AttendanceRow, ...] | list[AttendanceRow],
                        hourly_rate: Decimal) -> ReportSummary:
    """Type B totals: hours are summed in *minutes* and rounded once.

    Checked against the scan: the rows add up to 3,781 minutes = 63.0167 h,
    printed as 63.02, and pay = 63.0167 x 32.35 = 2,038.59 (with the rounded
    63.02 it would be 2,038.70, which is not what the source prints).
    """
    minutes = sum(r.net_minutes for r in rows if r.has_times)
    pay = (Decimal(minutes) * hourly_rate / Decimal(60)).quantize(TWO_PLACES, ROUND_HALF_UP)
    return ReportSummary(
        days=sum(1 for r in rows if r.has_times),
        break_minutes=0,
        total_hours=minutes_to_hours(minutes),
        buckets=HourBuckets(),
        hourly_rate=hourly_rate,
        total_pay=pay,
    )
