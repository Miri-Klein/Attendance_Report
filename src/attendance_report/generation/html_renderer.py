"""HTML version of the same report: quick to inspect in a browser, RTL-native.

Same layout data and the same formatting functions as the PDF, laid out with
normal HTML tables instead of absolute coordinates.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

from ..domain.models import AttendanceReport
from .base_renderer import BaseRenderer
from .formatting import box_value, row_cell, summary_row_cell
from .layouts import KeyValueBox, PageLayout

CSS = """
body { font-family: Arial, 'Liberation Sans', sans-serif; direction: rtl; width: 190mm;
       margin: 10mm auto; color: #000; background: #fff; }
p.head { font-weight: bold; font-size: 12pt; margin: 0 0 4px; }
.redacted { display: inline-block; background: #000; border-radius: 8px; width: 140px; height: 14px; }
table { border-collapse: collapse; margin: 10px 0; }
table.data { width: 100%; }
th { font-weight: bold; padding: 1px 4px; border-top: 1px solid #000; border-left: 1px solid #000;
     white-space: pre-line; vertical-align: bottom; text-align: right; }
td { padding: 1px 4px; text-align: right; }
td.c, th.c { text-align: center; }
table.grid th, table.grid td { border: 1px solid #000; }
table.grid td { font-weight: bold; }
.shade { background: #a6a6a6; }
table.box { border: 1.2px solid #000; margin-right: auto; margin-left: 0; }
table.box td { border: 1px solid #000; min-width: 60px; }
"""


class HtmlRenderer(BaseRenderer):
    extension = ".html"

    def _write(self, report: AttendanceReport, layout: PageLayout, out_path: Path) -> None:
        t = layout.table
        out = ['<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">',
               f"<title>{escape(report.source_name or 'attendance report')}</title>",
               f"<style>{CSS}</style></head><body>"]
        for line in report.header_lines[:len(layout.texts)]:
            out.append(f'<p class="head">{escape(line)}</p>')
        if layout.redaction and not report.employee_name and not any(
                r.key == "employee_name" for b in layout.boxes for r in b.rows):
            out.append('<p><span class="redacted"></span></p>')

        before = [b for b in layout.boxes if not b.after_table and b.top < t.top]
        after = [b for b in layout.boxes if b not in before]
        for box in before:
            out.append(self._box(report, box))

        cls = "data grid" if t.full_grid else "data"
        out.append(f'<table class="{cls}"><thead><tr>')
        for c in t.columns:
            shade = " shade" if c.key in t.shade_header else ""
            align = " c" if c.align == "center" else ""
            out.append(f'<th class="{align}{shade}">{escape(c.header.strip())}</th>')
        out.append("</tr></thead><tbody>")
        for row in report.rows:
            out.append("<tr>")
            for c in t.columns:
                classes = ["c"] if c.align == "center" else []
                if row.is_shabbat and c.key in t.shade_shabbat:
                    classes.append("shade")
                out.append(f'<td class="{" ".join(classes)}">{escape(row_cell(row, c.key, t))}</td>')
            out.append("</tr>")
        if t.summary_row and report.summary:
            out.append("<tr>" + "".join(
                f"<td>{escape(summary_row_cell(report.summary, c.key))}</td>" for c in t.columns) + "</tr>")
        out.append("</tbody></table>")
        for box in after:
            out.append(self._box(report, box))
        out.append("</body></html>")
        out_path.write_text("\n".join(out), encoding="utf-8")

    @staticmethod
    def _box(report: AttendanceReport, box: KeyValueBox) -> str:
        cells = []
        for r in box.rows:
            if not r.split:
                cells.append('<tr><td colspan="2">&nbsp;</td></tr>')
                continue
            value = box_value(report, r.key, r.style) if r.key else ""
            value_html = escape(value) if value or r.key != "employee_name" else '<span class="redacted"></span>'
            lab = ' class="shade"' if box.shade_label else ""
            val = ' class="shade"' if box.shade_value else ""
            weight = "bold" if box.bold else "normal"
            cells.append(f'<tr style="font-weight:{weight}"><td{lab}>{escape(r.label)}</td>'
                         f"<td{val}>{value_html}</td></tr>")
        return '<table class="box">' + "".join(cells) + "</table>"
