"""Runs the transformation: picks the strategy once, loops over rows, validates.

Determinism: every row gets its own Random seeded with "<seed>:<date>". The
same file + the same seed always gives the same output, and changing one row
does not change the random numbers of the other rows. Python seeds Random
from a str via SHA-512, so this does not depend on PYTHONHASHSEED or on the
machine.
"""
from __future__ import annotations

import random
from dataclasses import replace

from ..domain.exceptions import EmptyReportError, InvariantViolation, TransformationError
from ..domain.models import AttendanceReport, ReportType
from ..domain.validation import check_invariants
from .strategies import (BaseTransformationStrategy, TypeATransformationStrategy,
                         TypeBTransformationStrategy)


def default_strategies() -> dict[ReportType, BaseTransformationStrategy]:
    return {
        ReportType.TYPE_A: TypeATransformationStrategy(),
        ReportType.TYPE_B: TypeBTransformationStrategy(),
    }


class TransformationService:
    def __init__(self, strategies: dict[ReportType, BaseTransformationStrategy] | None = None):
        self._strategies = strategies or default_strategies()

    def strategy_for(self, report: AttendanceReport) -> BaseTransformationStrategy:
        return self._strategies[report.report_type]

    def transform(self, report: AttendanceReport, seed: int | str = 42) -> AttendanceReport:
        if not any(r.has_times for r in report.rows):
            raise EmptyReportError("no attendance rows to vary")
        strategy = self.strategy_for(report)                     # chosen once, no if/elif
        rows = tuple(strategy.transform_row(row, random.Random(f"{seed}:{row.work_date.isoformat()}"))
                     for row in report.rows)
        new = replace(report, rows=rows, summary=strategy.build_summary(rows, report.summary),
                      warnings=())
        errors = self.check(new)
        if errors:  # a bug in the rules, never the input's fault
            raise InvariantViolation("; ".join(errors))
        return new

    def check(self, report: AttendanceReport) -> list[str]:
        """All invariants, with the totals recomputed the way this type computes them."""
        strategy = self.strategy_for(report)
        try:
            expected = strategy.build_summary(report.rows, report.summary)
        except TransformationError as exc:
            return [str(exc)]
        return check_invariants(report, strategy.rules.limits, expected)
