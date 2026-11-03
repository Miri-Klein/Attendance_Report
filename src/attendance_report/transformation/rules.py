"""All the numbers that define a "believable" variation, one set per report type.

They differ because the sources differ: type A times are round (08:00, 15:00)
and shifts are ~6.5 h; type B times are minute-precise clock punches
(8:01, 11:05) and shifts are ~3 h.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from decimal import Decimal

from ..domain.validation import Limits


@dataclass(frozen=True)
class TransformationRules:
    step_minutes: int = 5                 # times move in steps of this size
    max_entry_shift_minutes: int = 30     # entry moves by at most +- this
    max_duration_shift_minutes: int = 30  # worked time changes by at most +- this
    regular_hours: Decimal = Decimal("8")      # A: hours at 100% per weekday
    overtime_125_hours: Decimal = Decimal("2")  # A: next hours at 125%, the rest at 150%
    limits: Limits = field(default_factory=Limits)


TYPE_A_RULES = TransformationRules()

TYPE_B_RULES = TransformationRules(
    step_minutes=1,                      # clock punches: 8:01, 8:03 ...
    max_entry_shift_minutes=8,
    max_duration_shift_minutes=10,
    limits=Limits(earliest_entry=time(6, 0), latest_exit=time(22, 0),
                  min_daily_hours=Decimal("2"), max_daily_hours=Decimal("12")),
)
