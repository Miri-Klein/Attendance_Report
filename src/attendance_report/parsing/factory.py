"""The only place that knows which parser class serves which report type.

Adding type C = write TypeCParser and add one line here.
"""
from __future__ import annotations

from ..domain.models import ReportType
from .base_parser import BaseParser
from .type_a_parser import TypeAParser
from .type_b_parser import TypeBParser

_PARSERS: dict[ReportType, type[BaseParser]] = {
    ReportType.TYPE_A: TypeAParser,
    ReportType.TYPE_B: TypeBParser,
}


def get_parser(report_type: ReportType) -> BaseParser:
    try:
        return _PARSERS[report_type]()
    except KeyError:
        raise ValueError(f"no parser registered for {report_type}") from None
