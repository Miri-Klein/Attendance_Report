"""Build the PDF from scratch with ReportLab, imitating the scanned source.

The page is drawn from the layout (data measured on the scans): text lines,
the table (title row, rows, optional full grid, grey Shabbat cells, totals
line) and the label/value boxes.

Hebrew: ReportLab draws characters left-to-right and knows nothing about RTL,
so every string goes through the Unicode bidi algorithm (python-bidi, base
direction RTL) and is then drawn right-aligned or centred. The font must
contain Hebrew: Liberation Sans (regular + bold) is bundled, metric-compatible
with Arial, the font of the source reports.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from ..domain.models import AttendanceReport
from .base_renderer import BaseRenderer
from .formatting import box_value, row_cell, summary_row_cell
from .layouts import KeyValueBox, PageLayout, TableLayout

try:                                   # python-bidi >= 0.5
    from bidi import get_display
except ImportError:                    # pragma: no cover - older python-bidi
    from bidi.algorithm import get_display

FONTS_DIR = Path(__file__).parent / "fonts"
REGULAR, BOLD = "LiberationSans", "LiberationSans-Bold"
PAGE_W, PAGE_H = A4


def _register_fonts() -> None:
    for name, file in ((REGULAR, "LiberationSans-Regular.ttf"), (BOLD, "LiberationSans-Bold.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(FONTS_DIR / file)))


class PdfRenderer(BaseRenderer):
    extension = ".pdf"

    def _write(self, report: AttendanceReport, layout: PageLayout, out_path: Path) -> None:
        _register_fonts()
        c = Canvas(str(out_path), pagesize=A4, invariant=1)   # invariant=1: byte-identical reruns
        page = _Page(c, layout.shade_gray)

        for t in layout.texts:
            index = int(t.key.split(":")[1])
            if index < len(report.header_lines):
                page.text(report.header_lines[index], t.right, t.baseline, t.size, t.bold, "right")
        table_bottom = self._table(page, report, layout.table)
        for box in layout.boxes:
            self._box(page, report, box, table_bottom)
        if layout.redaction and not report.employee_name:   # last: on top of grey cells
            r = layout.redaction
            page.redact(r.x0, r.top, r.x1, r.bottom)
        c.showPage()
        c.save()

    @staticmethod
    def _table(page: "_Page", report: AttendanceReport, t: TableLayout) -> float:
        rows_top = t.top + t.header_height
        n = len(report.rows) + (1 if t.summary_row and report.summary else 0)
        bottom = rows_top + n * t.row_height

        # grey cells first, text and lines on top
        for col in t.columns:
            if col.key in t.shade_header:
                page.shade(col.x0, t.top, col.x1, rows_top)
        for i, row in enumerate(report.rows):
            if row.is_shabbat:
                for col in t.columns:
                    if col.key in t.shade_shabbat:
                        y = rows_top + i * t.row_height
                        page.shade(col.x0, y, col.x1, y + t.row_height)

        # lines
        page.hline(t.x0, t.x1, t.top, t.line_width)
        for col in t.columns:                       # separators between column titles
            page.vline(col.x1, t.top, rows_top, t.line_width)
        if t.full_grid:
            page.vline(t.x0, t.top, bottom, t.line_width)
            for col in t.columns:
                page.vline(col.x1, rows_top, bottom, t.line_width)
            for k in range(len(report.rows) + 1):
                page.hline(t.x0, t.x1, rows_top + k * t.row_height, t.line_width)

        # column titles (1 or 2 lines)
        for col in t.columns:
            for line, base in zip(col.header.split("\n"), t.header_baselines[-len(col.header.split("\n")):]):
                if line:
                    page.cell_text(line, col, base, t.font_size, t.header_bold)

        # rows
        for i, row in enumerate(report.rows):
            base = rows_top + i * t.row_height + t.row_baseline
            for col in t.columns:
                page.cell_text(row_cell(row, col.key, t), col, base, t.font_size, t.body_bold)
        if t.summary_row and report.summary:
            base = rows_top + len(report.rows) * t.row_height + t.row_baseline
            for col in t.columns:
                page.cell_text(summary_row_cell(report.summary, col.key), col, base,
                               t.font_size, t.body_bold)
        return bottom

    @staticmethod
    def _box(page: "_Page", report: AttendanceReport, b: KeyValueBox, table_bottom: float) -> None:
        top = table_bottom + b.top if b.after_table else b.top
        bottom = top + len(b.rows) * b.row_height
        for k, row in enumerate(b.rows):
            y0, y1 = top + k * b.row_height, top + (k + 1) * b.row_height
            if row.split:
                if b.shade_label:
                    page.shade(b.divider, y0, b.x1, y1)
                if b.shade_value:
                    page.shade(b.x0, y0, b.divider, y1)
                page.vline(b.divider, y0, y1, b.line_width)
            base = y0 + b.baseline
            if row.label:
                page.aligned(row.label, b.divider, b.x1, base, b.font_size, b.bold, b.label_align)
            if row.key:
                value = box_value(report, row.key, row.style)
                if row.key == "employee_name" and not value:
                    continue        # the redaction bar stands in for it
                page.aligned(value, b.x0, b.divider, base, b.font_size, b.bold, b.value_align)
        for k in range(len(b.rows) + 1):
            page.hline(b.x0, b.x1, top + k * b.row_height, b.line_width)
        page.vline(b.x0, top, bottom, b.line_width)
        page.vline(b.x1, top, bottom, b.line_width)


class _Page:
    """Thin wrapper: works in top-down coordinates like the measured layout."""

    def __init__(self, canvas: Canvas, gray: float):
        self.c = canvas
        self.gray = gray

    def text(self, s: str, x: float, baseline: float, size: float, bold: bool, align: str) -> None:
        if not s:
            return
        self.c.setFont(BOLD if bold else REGULAR, size)
        self.c.setFillGray(0)
        y = PAGE_H - baseline
        visual = get_display(s, base_dir="R")
        if align == "center":
            self.c.drawCentredString(x, y, visual)
        else:
            self.c.drawRightString(x, y, visual)

    def cell_text(self, s: str, col, baseline: float, size: float, bold: bool) -> None:
        self.aligned(s, col.x0, col.x1, baseline, size, bold, col.align, col.pad)

    def aligned(self, s: str, x0: float, x1: float, baseline: float, size: float, bold: bool,
                align: str, pad: float = 3.0) -> None:
        if align == "center":
            self.text(s, (x0 + x1) / 2, baseline, size, bold, "center")
        else:
            self.text(s, x1 - pad, baseline, size, bold, "right")

    def hline(self, x0: float, x1: float, y: float, width: float) -> None:
        self.c.setLineWidth(width)
        self.c.line(x0, PAGE_H - y, x1, PAGE_H - y)

    def vline(self, x: float, y0: float, y1: float, width: float) -> None:
        self.c.setLineWidth(width)
        self.c.line(x, PAGE_H - y0, x, PAGE_H - y1)

    def shade(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.c.setFillGray(self.gray)
        self.c.rect(x0, PAGE_H - y1, x1 - x0, y1 - y0, stroke=0, fill=1)
        self.c.setFillGray(0)

    def redact(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.c.setFillGray(0)
        r = (y1 - y0) / 2
        self.c.roundRect(x0, PAGE_H - y1, x1 - x0, y1 - y0, r, stroke=0, fill=1)
