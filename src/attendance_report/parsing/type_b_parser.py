"""Type B (employee card, "כרטיס עובד לחודש"): one line for *every* day of the
month (weekends empty, Shabbat shaded; a short month continues with empty
lines of the next month), entry/exit/total/notes, and a box above the table
with days, monthly hours, hourly rate and pay."""
from __future__ import annotations

import calendar
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

from ..domain.exceptions import ParseError
from ..domain.models import AttendanceRow, HourBuckets, ReportSummary, ReportType
from .base_parser import BaseParser, BodyLine, Cell, Cells, Column, hebrew_words, numbers_in
from .cleaning import parse_date, parse_decimal
from .raw import Line
from .repair import reconcile

# words that identify each line of the box above the table
BOX_LABELS = (("עבודה", "days"), ("חודשיות", "hours"), ("לשעה", "rate"), ("לתשלום", "pay"))
NOTE_MIN_CONF = 60   # shaded/empty cells produce low-confidence Hebrew-looking noise
FORM_LINES = 31      # the printed card always has 31 day lines


class TypeBParser(BaseParser):
    report_type = ReportType.TYPE_B
    columns = (
        Column("date", "תאריך"),
        Column("weekday", "בשבוע"),
        Column("entry", "כניסה"),
        Column("exit", "יציאה"),
        Column("total", "שעות"),
        Column("note", "הערות"),
    )

    def _build_rows(self, body, warnings):
        """Every calendar day has a line, at a fixed vertical pitch. So the date
        of a line follows from its *position*: fit day = a + b*y on the lines
        whose date OCR read correctly, then place every line (including ones
        with an unreadable date, like '13' or '29/14/23') into its day.

        * The fit is done per page (each page has its own top margin).
        * The printed form always has 31 lines, so a short month continues
          with lines of the next month (Sept 2022 ends with a shaded
          '1/10/22', which OCR reads as '225%'). Lines up to 31 are kept, so
          the output has the same lines as the source; validation makes sure
          no *worked* day falls outside the month.
        """
        dated = [(bl, parse_date(bl.cells["date"].text)) for bl in body]
        months = Counter((d.year, d.month) for _, d in dated if d)
        if not months:
            warnings.append("no readable dates")
            return [], None, [bl.line for bl in body]
        year, month = months.most_common(1)[0][0]
        start = date(year, month, 1)
        n_days = calendar.monthrange(year, month)[1]

        def slot_of(d: date) -> int:          # 1 = first of the month, 31 = 1/10 in September
            return (d - start).days + 1

        fits = _fit_pages([(bl.page, bl.y, slot_of(d)) for bl, d in dated
                           if d and 1 <= slot_of(d) <= n_days + 7])

        per_slot: dict[int, list[BodyLine]] = {}
        below: list[Line] = []
        last_slot = n_days
        for bl, d in dated:
            a, b = fits[bl.page]
            slot = round(a + b * bl.y)
            if slot < 1:
                continue
            if slot > FORM_LINES:                # below the printed table
                below.append(bl.line)
                continue
            last_slot = max(last_slot, slot)     # a line past the month end is still a table line
            where = start + timedelta(days=slot - 1)
            if d is None and bl.cells["date"].text:
                warnings.append(f"unreadable date '{bl.cells['date'].text}' placed on "
                                f"{where:%d/%m/%Y} by its position")
            elif d is not None and d != where:
                warnings.append(f"date read as {d:%d/%m/%Y} but its position says "
                                f"{where:%d/%m/%Y}; position wins")
            per_slot.setdefault(slot, []).append(bl)

        rows = []
        for slot in range(1, last_slot + 1):
            cells = _merge_cells(per_slot.get(slot, []), [c.key for c in self.columns])
            rows.append(self._parse_row(start + timedelta(days=slot - 1), cells, warnings))
        return rows, None, below

    def _parse_row(self, work_date: date, cells: Cells, warnings: list[str]) -> AttendanceRow:
        fixed = reconcile(self._time_cells(cells))
        if fixed.note:
            warnings.append(f"{work_date:%d/%m/%Y}: {fixed.note}")
        note = cells["note"]
        text = " ".join(hebrew_words(note.text)) if note.conf >= NOTE_MIN_CONF else ""
        return AttendanceRow(work_date=work_date, entry=fixed.entry, exit=fixed.exit,
                             total_hours=fixed.total, note=text)

    def _parse_summary(self, summary_cells, above, below, warnings):
        box: dict[str, Decimal] = {}
        for line in above:
            words = " ".join(w.text for w in line.words)
            for label, key in BOX_LABELS:
                if label in words:
                    values = [v for v in map(parse_decimal, numbers_in(line)) if v is not None]
                    if values:
                        box[key] = values[0]
        rate = box.get("rate")
        if rate is None and box.get("pay") and box.get("hours"):
            rate = (box["pay"] / box["hours"]).quantize(Decimal("0.01"))
            warnings.append(f"hourly rate unreadable, derived from pay / hours = {rate}")
        if rate is None:
            warnings.append("hourly rate not found")
        hours, pay = box.get("hours"), box.get("pay")
        if rate and pay and (hours is None or abs(hours * rate - pay) > rate):
            # hours x rate must be about the pay; if not, OCR broke the hours
            fixed = (pay / rate).quantize(Decimal("0.01"))
            warnings.append(f"monthly hours read as '{hours}' do not match pay / rate, using {fixed}")
            box["hours"] = fixed
        return ReportSummary(days=int(box.get("days", 0)), break_minutes=0,
                             total_hours=box.get("hours", Decimal("0")),
                             buckets=HourBuckets(),
                             hourly_rate=rate, total_pay=box.get("pay"))

    def _parse_metadata(self, above, warnings):
        for line in above:
            words = list(line.words)
            label = next((i for i, w in enumerate(words) if w.text.startswith("העובד")), None)
            if label is None:
                continue
            # the label and the name can come out glued: 'העובד:ישראל'
            glued = words[label].text.partition(":")[2].strip("'\" ")
            value = ([glued] if glued and words[label].conf >= NOTE_MIN_CONF else []) + \
                    [w.text for w in words[label + 1:] if w.conf >= NOTE_MIN_CONF and hebrew_words(w.text)]
            if value:
                return (), " ".join(value), ""
        warnings.append("employee name not readable (redacted in the scan?)")
        return (), "", ""


def _fit_pages(points: list[tuple[int, float, int]]) -> dict[int, tuple[float, float]]:
    """(page, y, day) -> {page: (a, b)} with day = a + b*y on each page.

    A page with a single readable date borrows the pitch (b) of another page;
    a page with none cannot be placed and is an error, not a guess."""
    pages = sorted({p for p, _, _ in points})
    fits: dict[int, tuple[float, float]] = {}
    for page in pages:
        pts = [(y, d) for p, y, d in points if p == page]
        if len(pts) >= 2:
            fits[page] = _fit_day_position(pts)
    if not fits:
        raise ParseError("need at least two readable dates on a page to place the rows")
    pitch = next(iter(fits.values()))[1]
    for page in pages:
        if page not in fits:
            y, d = next((y, d) for p, y, d in points if p == page)
            fits[page] = (d - pitch * y, pitch)
    return _DefaultFits(fits)


class _DefaultFits(dict):
    """Lines on a page without any readable date: report clearly."""

    def __missing__(self, page):
        raise ParseError(f"page {page + 1}: no readable date to place its rows")


def _fit_day_position(points: list[tuple[float, int]]) -> tuple[float, float]:
    """Least squares day = a + b*y, refitted once without outliers (> 0.4 day)."""
    def fit(pts):
        n = len(pts)
        my = sum(y for y, _ in pts) / n
        md = sum(d for _, d in pts) / n
        b = sum((y - my) * (d - md) for y, d in pts) / sum((y - my) ** 2 for y, _ in pts)
        return md - b * my, b
    a, b = fit(points)
    inliers = [(y, d) for y, d in points if abs(a + b * y - d) <= 0.4]
    return fit(inliers) if len(inliers) >= 2 else (a, b)


def _merge_cells(lines: list[BodyLine], keys: list[str]) -> Cells:
    """OCR sometimes splits one table row into two text lines; join them."""
    out: Cells = {}
    for k in keys:
        parts = [bl.cells[k] for bl in lines if bl.cells[k].text]
        out[k] = Cell(" ".join(p.text for p in parts), min((p.conf for p in parts), default=100.0))
    return out
