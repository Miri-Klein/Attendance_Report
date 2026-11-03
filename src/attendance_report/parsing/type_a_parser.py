"""Type A (agency report, "נ.ע. הנשר"): only worked days are listed;
location, break, 100/125/150/Shabbat split; a totals line and a totals box."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace
from datetime import date
from decimal import Decimal

from ..domain.models import AttendanceRow, HourBuckets, ReportSummary, ReportType
from ..domain.validation import Limits
from .base_parser import BaseParser, BodyLine, Cells, Column, hebrew_words, numbers_in
from .cleaning import has_hebrew, parse_date, parse_decimal, parse_duration_minutes, parse_int
from .raw import Line
from .repair import reconcile

ZERO = Decimal("0.00")
LIMITS = Limits()

# Totals box: label word -> field. Checked in this order ("שבת 150%" before "150%").
BOX_LABELS = (("ימים", "days"), ('סה"כ', "total"), ("שבת", "shabbat"), ("100%", "h100"),
              ("125%", "h125"), ("150%", "h150"), ("בונוס", "bonus"), ("נסיעות", "travel"))


class TypeAParser(BaseParser):
    report_type = ReportType.TYPE_A
    columns = (
        Column("date", "תאריך"),
        Column("weekday", "יום"),
        Column("location", "מקום"),
        Column("entry", "כניסה"),
        Column("exit", "יציאה"),
        Column("break", "הפסקה"),
        Column("total", 'סה"כ'),
        Column("h100", "100%"),
        Column("h125", "125%"),
        Column("h150", "150%"),
        Column("shabbat", "שבת"),
    )

    def _build_rows(self, body, warnings):
        rows: list[AttendanceRow] = []
        summary_cells: Cells | None = None
        below: list[Line] = []
        prev: date | None = None
        for bl in body:
            if summary_cells is not None:          # everything after the totals line
                below.append(bl.line)
                continue
            if self._is_summary_line(bl.cells):
                summary_cells = bl.cells
                continue
            d = self._repair_date_by_weekday(bl.cells, prev, warnings)
            if d is None:
                below.append(bl.line)
                continue
            rows.append(self._parse_row(bl, d, warnings))
            prev = d
        return self._fill_unreadable_locations(rows, warnings), summary_cells, below

    def _parse_row(self, bl: BodyLine, work_date: date, warnings: list[str]) -> AttendanceRow:
        cells, tag = bl.cells, f"{work_date:%d/%m/%Y}"

        def num(key: str) -> Decimal:
            if not cells[key].text:
                return ZERO
            value = parse_decimal(cells[key].text)
            if value is None:
                warnings.append(f"{tag}: cannot read '{cells[key].text}' in column {key}")
                return ZERO
            return value

        buckets = HourBuckets(num("h100"), num("h125"), num("h150"), num("shabbat"))
        brk = parse_duration_minutes(cells["break"].text) or 0
        time_cells = self._time_cells(cells)
        # The total is printed twice: "סה"כ" and the sum of the rate columns.
        # If OCR broke one copy (seen: 7.33 read as 1.33) the other one fixes it.
        total = parse_decimal(cells["total"].text)
        if total != buckets.total and _plausible(buckets.total) and not _plausible(total):
            warnings.append(f"{tag}: total '{cells['total'].text}' looks misread, "
                            f"using the rate columns ({buckets.total})")
            time_cells = replace(time_cells, total=f"{buckets.total}")
        fixed = reconcile(time_cells, brk)
        if fixed.note:
            warnings.append(f"{tag}: {fixed.note}")
        if fixed.total != buckets.total:
            warnings.append(f"{tag}: total {fixed.total} != sum of rate columns {buckets.total}")
        return AttendanceRow(work_date=work_date, entry=fixed.entry, exit=fixed.exit,
                             total_hours=fixed.total, break_minutes=brk,
                             location=cells["location"].text, buckets=buckets)

    @staticmethod
    def _fill_unreadable_locations(rows: list[AttendanceRow], warnings: list[str]) -> list[AttendanceRow]:
        """'גליליון' is sometimes read as 'jr"'. Locations are a short list of
        sites, so an unreadable one gets the most frequent readable value."""
        readable = Counter(r.location for r in rows if has_hebrew(r.location))
        if not readable:
            return rows
        common = readable.most_common(1)[0][0]
        out = []
        for r in rows:
            if not has_hebrew(r.location):
                warnings.append(f"{r.work_date:%d/%m/%Y}: location '{r.location}' unreadable, "
                                f"using '{common}'")
                r = replace(r, location=common)
            out.append(r)
        return out

    @staticmethod
    def _is_summary_line(cells: Cells) -> bool:
        # The totals line has a day count where the date normally is, and no times.
        return (parse_date(cells["date"].text) is None and parse_int(cells["date"].text) is not None
                and not cells["entry"].text and parse_decimal(cells["total"].text) is not None)

    def _parse_summary(self, summary_cells, above, below, warnings):
        box = _read_box(below)
        if summary_cells is None and not box:
            warnings.append("no summary found")
            return None
        if summary_cells is not None:
            def dec(k):
                return parse_decimal(summary_cells[k].text) or ZERO
            days = parse_int(summary_cells["date"].text) or 0
            brk = parse_duration_minutes(summary_cells["break"].text) or 0
            total = dec("total")
            buckets = HourBuckets(dec("h100"), dec("h125"), dec("h150"), dec("shabbat"))
        else:  # only the box was readable
            days, brk = int(box.get("days", 0)), 0
            total = box.get("total", ZERO)
            buckets = HourBuckets(box.get("h100", ZERO), box.get("h125", ZERO),
                                  box.get("h150", ZERO), box.get("shabbat", ZERO))
        for key in ("bonus", "travel"):
            if key not in box:
                warnings.append(f"summary box: '{key}' not readable, using 0")
        return ReportSummary(days, brk, total, buckets,
                             box.get("bonus", Decimal("0")), box.get("travel", Decimal("0")))

    def _parse_metadata(self, above, warnings):
        # keep printed lines (company name); drop handwriting / scan noise
        header = tuple(line.text for line in above if hebrew_words(line.text))
        for text in header:
            if m := re.search(r"^(.*?)\s*ת\.ז\.\s*(\d*)", text):
                return header, m.group(1).strip(), m.group(2)
        warnings.append("employee name/id not readable (redacted in the scan?)")
        return header, "", ""


def _plausible(hours: Decimal | None) -> bool:
    return hours is not None and LIMITS.min_daily_hours <= hours <= LIMITS.max_daily_hours


def _read_box(lines: list[Line]) -> dict[str, Decimal]:
    found: dict[str, Decimal] = {}
    for line in lines:
        words = [w.text for w in line.words]
        for label, key in BOX_LABELS:
            if label in words:
                values = [v for v in map(parse_decimal, numbers_in(line)) if v is not None]
                if values and key not in found:
                    found[key] = values[0]
                break
    return found
