"""Using the redundancy inside a row to fix what OCR misread.

Every row states the same fact twice: exit - entry - break == total.
So if exactly one of the three values was misread, the other two tell us
what it should be. Which one was misread? The candidate that needs the
*smallest change* to the characters OCR returned (edit distance on digits),
among candidates that give a plausible row. Ties go to the value OCR was
least confident about.

Examples from the real type B scan:
  entry '3:02', exit 11:00, total 2.97 -> entry 8:02   (3 and 8 look alike)
  entry 8:00, exit '41:01', total 3.02 -> exit 11:01   (41:01 is not a time)
  entry '02 :8' (split in two), exit 11:03, total 3.02 -> entry 8:02
Every fix is reported as a warning, never applied silently.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal

from ..domain.models import minutes_to_hours, minutes_to_time, time_to_minutes
from ..domain.validation import Limits
from .cleaning import parse_decimal, parse_time


@dataclass(frozen=True)
class TimeCells:
    entry: str
    exit: str
    total: str
    entry_conf: float = 100.0
    exit_conf: float = 100.0
    total_conf: float = 100.0


@dataclass(frozen=True)
class Reconciled:
    entry: time | None
    exit: time | None
    total: Decimal
    note: str = ""            # what was repaired (empty = nothing)


def reconcile(cells: TimeCells, break_minutes: int = 0, limits: Limits = Limits()) -> Reconciled:
    e, x, t = parse_time(cells.entry), parse_time(cells.exit), parse_decimal(cells.total)
    if e is None and x is None:
        # no shift on this day (weekend, vacation, shaded Shabbat row with noise)
        return Reconciled(None, None, Decimal("0.00"),
                          f"hours '{cells.total}' without entry/exit ignored" if t else "")
    if e is not None and x is not None and t is not None and _consistent(e, x, t, break_minutes):
        return Reconciled(e, x, t)

    candidates: list[tuple[int, float, str, Reconciled]] = []
    if x is not None and t is not None:                     # trust exit+total, rebuild entry
        m = time_to_minutes(x) - break_minutes - _hours_to_minutes(t)
        if 0 <= m < 24 * 60:
            new = minutes_to_time(m)
            candidates.append((_distance(cells.entry, new.strftime("%H:%M")), cells.entry_conf,
                               f"entry '{cells.entry}' -> {new:%H:%M}", Reconciled(new, x, t)))
    if e is not None and t is not None:                     # trust entry+total, rebuild exit
        m = time_to_minutes(e) + break_minutes + _hours_to_minutes(t)
        if 0 <= m < 24 * 60:
            new = minutes_to_time(m)
            candidates.append((_distance(cells.exit, new.strftime("%H:%M")), cells.exit_conf,
                               f"exit '{cells.exit}' -> {new:%H:%M}", Reconciled(e, new, t)))
    if e is not None and x is not None:                     # trust entry+exit, rebuild total
        net = time_to_minutes(x) - time_to_minutes(e) - break_minutes
        if net > 0:
            new_t = minutes_to_hours(net)
            candidates.append((_distance(cells.total, f"{new_t:.2f}"), cells.total_conf,
                               f"total '{cells.total}' -> {new_t}", Reconciled(e, x, new_t)))

    plausible = [c for c in candidates if _plausible(c[3], break_minutes, limits)]
    if not plausible:
        return Reconciled(e, x, t if t is not None else Decimal("0.00"),
                          f"cannot make entry '{cells.entry}' / exit '{cells.exit}' / "
                          f"total '{cells.total}' consistent")
    dist, _, note, best = min(plausible, key=lambda c: (c[0], c[1]))
    return Reconciled(best.entry, best.exit, best.total, note)


def _hours_to_minutes(hours: Decimal) -> int:
    return int((hours * 60).to_integral_value())


def _consistent(e: time, x: time, t: Decimal, break_minutes: int) -> bool:
    net = time_to_minutes(x) - time_to_minutes(e) - break_minutes
    return net > 0 and minutes_to_hours(net) == t


def _plausible(r: Reconciled, break_minutes: int, limits: Limits) -> bool:
    if r.entry < limits.earliest_entry or r.exit > limits.latest_exit or r.exit <= r.entry:
        return False
    return Decimal("0") < r.total <= limits.max_daily_hours


def _digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def _distance(a: str, b: str) -> int:
    """Levenshtein distance between the digit sequences ('3:02' vs '08:02' -> 1)."""
    a, b = _digits(a).lstrip("0"), _digits(b).lstrip("0")
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]
