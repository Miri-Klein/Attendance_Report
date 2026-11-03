"""Strategy: one class per report type decides how a row changes and how the
totals are recomputed.

Shared logic (moving entry/exit inside the working window) lives in the base
class; each type adds only what is specific to it. The service that loops over
the rows never asks "which type is this?".
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import replace
from decimal import Decimal
from enum import Enum

from ..domain.models import (AttendanceRow, HourBuckets, ReportSummary, compute_pay_summary,
                             compute_summary, minutes_to_hours, minutes_to_time, time_to_minutes)
from .rules import TYPE_A_RULES, TYPE_B_RULES, TransformationRules

ZERO = Decimal("0.00")


class MissingRateError(ValueError):
    pass


class BaseTransformationStrategy(ABC):

    def __init__(self, rules: TransformationRules):
        self.rules = rules

    @abstractmethod
    def transform_row(self, row: AttendanceRow, rng: random.Random) -> AttendanceRow: ...

    @abstractmethod
    def build_summary(self, rows: tuple[AttendanceRow, ...],
                      original: ReportSummary | None) -> ReportSummary | None: ...

    # ---- shared helper -----------------------------------------------------
    def _vary_times(self, row: AttendanceRow, rng: random.Random, break_minutes: int) -> tuple[int, int]:
        """Return new (entry, net worked) in minutes.

        Baseline for the worked time is the printed total (fallback: exit -
        entry - break). Then:
          * entry  += k*step, |k*step| <= max_entry_shift
          * worked += j*step, |j*step| <= max_duration_shift
          * clamp worked to [min_daily, max_daily]
          * if exit would pass latest_exit, move the whole shift earlier
        """
        r, lim, step = self.rules, self.rules.limits, self.rules.step_minutes
        baseline = int(row.total_hours * 60) if row.total_hours > 0 else row.net_minutes
        k = rng.randint(-r.max_entry_shift_minutes // step, r.max_entry_shift_minutes // step)
        j = rng.randint(-r.max_duration_shift_minutes // step, r.max_duration_shift_minutes // step)

        entry = _round_to(time_to_minutes(row.entry), step) + k * step
        worked = _round_to(baseline, step) + j * step
        worked = max(int(lim.min_daily_hours * 60), min(int(lim.max_daily_hours * 60), worked))

        earliest, latest = time_to_minutes(lim.earliest_entry), time_to_minutes(lim.latest_exit)
        entry = max(entry, earliest)
        overflow = entry + worked + break_minutes - latest
        if overflow > 0:
            entry = max(earliest, entry - overflow)
            worked = min(worked, latest - entry - break_minutes)
        return entry, worked


class DayKind(Enum):
    REGULAR = "regular"     # 100%, then 125%, then 150%
    SHABBAT = "shabbat"     # everything in the Shabbat column
    SPECIAL = "special"     # everything at 150% (holiday; e.g. 17/10/2022 in the scan)


class TypeATransformationStrategy(BaseTransformationStrategy):
    """Shift entry/exit, keep the break, recompute total and the rate split.

    The rate category of a day is taken from the *source* row: Shabbat by the
    date; a weekday whose hours were all paid at 150% (a holiday) stays a
    150% day. No holiday calendar is needed and the employer's own decision
    is preserved.
    """

    def __init__(self, rules: TransformationRules = TYPE_A_RULES):
        super().__init__(rules)

    def transform_row(self, row, rng):
        if not row.has_times:
            return row
        entry, worked = self._vary_times(row, rng, row.break_minutes)
        total = minutes_to_hours(worked)
        return replace(
            row,
            entry=minutes_to_time(entry),
            exit=minutes_to_time(entry + worked + row.break_minutes),
            total_hours=total,
            buckets=split_hours(total, day_kind(row), self.rules),
        )

    def build_summary(self, rows, original):
        bonus = original.bonus if original else Decimal("0")
        travel = original.travel if original else Decimal("0")
        return compute_summary(rows, bonus, travel)


class TypeBTransformationStrategy(BaseTransformationStrategy):
    """Shift the clock punches by single minutes, recompute total, days and pay.
    Days without punches (weekends, Shabbat) stay empty."""

    def __init__(self, rules: TransformationRules = TYPE_B_RULES):
        super().__init__(rules)

    def transform_row(self, row, rng):
        if not row.has_times:
            return row
        entry, worked = self._vary_times(row, rng, break_minutes=0)
        return replace(row, entry=minutes_to_time(entry),
                       exit=minutes_to_time(entry + worked),
                       total_hours=minutes_to_hours(worked))

    def build_summary(self, rows, original):
        if original is None or original.hourly_rate is None:
            raise MissingRateError("hourly rate was not read from the source, cannot compute pay")
        return compute_pay_summary(rows, original.hourly_rate)


def day_kind(row: AttendanceRow) -> DayKind:
    if row.is_shabbat:
        return DayKind.SHABBAT
    b = row.buckets
    if b is not None and row.total_hours > 0 and b.regular_100 == 0 and b.overtime_150 == row.total_hours:
        return DayKind.SPECIAL
    return DayKind.REGULAR


def split_hours(total: Decimal, kind: DayKind, rules: TransformationRules) -> HourBuckets:
    """Regular day: first 8h at 100%, next 2h at 125%, the rest at 150%.
    Computed by subtraction, so the buckets always add up to the total exactly."""
    if kind is DayKind.SHABBAT:
        return HourBuckets(ZERO, ZERO, ZERO, total)
    if kind is DayKind.SPECIAL:
        return HourBuckets(ZERO, ZERO, total, ZERO)
    regular = min(total, rules.regular_hours)
    ot125 = min(total - regular, rules.overtime_125_hours)
    ot150 = total - regular - ot125
    return HourBuckets(regular.quantize(ZERO), ot125.quantize(ZERO), ot150.quantize(ZERO), ZERO)


def _round_to(minutes: int, step: int) -> int:
    return int(round(minutes / step)) * step
