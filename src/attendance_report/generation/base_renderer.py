"""Renderers know only AttendanceReport (+ the page layout). Nothing about OCR or parsing."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..domain.models import AttendanceReport
from .layouts import LAYOUTS, PageLayout


class BaseRenderer(ABC):
    extension: str

    def render(self, report: AttendanceReport, out_path: Path) -> Path:
        out_path = out_path.with_suffix(self.extension)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self._write(report, LAYOUTS[report.report_type], out_path)
        return out_path

    @abstractmethod
    def _write(self, report: AttendanceReport, layout: PageLayout, out_path: Path) -> None: ...
