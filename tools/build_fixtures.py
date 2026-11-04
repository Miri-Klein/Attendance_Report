"""Build the synthetic test fixtures (run once; needs Tesseract).

    python -m tools.build_fixtures        (from the project root)

For each report type:
1. invent a report: made-up company, employee, month and hours, built to be
   fully consistent (every total equals exit - entry - break, etc.)
2. draw it with our own PdfRenderer -> samples/synthetic/<name>.pdf
3. "scan" it: render to a 150 dpi greyscale JPEG image and wrap it in a PDF
   with no text layer, exactly like the real scans -> <name>_scan.pdf
4. run the real OCR on the scan and save the words -> tests/fixtures/<name>.words.json
5. inject a few OCR errors that were really seen on the real scans
   ('3:02' for '8:02', '41:01', a date read as '13', 'כח אדם' read as 'ND DTN'...)
   so the repair logic is tested too; they are listed inside the JSON
6. save the true report -> tests/fixtures/<name>.truth.json

Nothing here comes from the private scans: no company, name, date or hour.
"""
from __future__ import annotations

import io
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

from attendance_report.domain.models import (AttendanceReport, AttendanceRow, ReportType,
                                             compute_pay_summary, compute_summary, minutes_to_hours,
                                             time_to_minutes)
from attendance_report.generation.pdf_renderer import PdfRenderer
from attendance_report.parsing.ocr import extract_ocr
from attendance_report.parsing.raw import RawDocument, RawWord
from attendance_report.transformation.rules import TYPE_A_RULES
from attendance_report.transformation.strategies import DayKind, split_hours
from tests.fixture_io import FIXTURES, save_truth, save_words

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = ROOT / "samples" / "synthetic"


# ---- 1. invented reports ------------------------------------------------------
def _row_a(d: date, entry: str, exit_: str, location: str, kind: DayKind = DayKind.REGULAR) -> AttendanceRow:
    e, x = time(*map(int, entry.split(":"))), time(*map(int, exit_.split(":")))
    total = minutes_to_hours(time_to_minutes(x) - time_to_minutes(e) - 30)
    return AttendanceRow(d, e, x, total, 30, location, split_hours(total, kind, TYPE_A_RULES))


def synthetic_type_a() -> AttendanceReport:
    """March 2024, invented agency 'דוגמה שירותי כח אדם בע"מ'. Includes two
    Shabbat days, a 150% holiday-type day and a day with 125% overtime."""
    plan = {  # day -> (entry, exit, location)
        3: ("08:00", "15:30", "מחסן"), 4: ("08:00", "15:30", "מחסן"), 5: ("07:30", "15:00", "מחסן"),
        6: ("08:00", "16:00", "משרד"), 7: ("08:00", "15:30", "מחסן"), 9: ("09:00", "14:30", "מחסן"),
        10: ("08:00", "15:30", "מחסן"), 11: ("07:00", "17:00", "מחסן"), 12: ("08:00", "15:30", "משרד"),
        13: ("08:00", "15:30", "מחסן"), 14: ("08:30", "16:00", "מחסן"), 16: ("09:00", "14:30", "מחסן"),
        17: ("08:00", "15:30", "מחסן"), 18: ("08:00", "15:30", "מחסן"), 19: ("08:00", "15:30", "משרד"),
        24: ("08:00", "14:00", "מחסן"), 25: ("08:00", "15:30", "מחסן"), 26: ("08:00", "15:30", "מחסן"),
    }
    rows = []
    for day, (e, x, loc) in plan.items():
        d = date(2024, 3, day)
        kind = DayKind.SHABBAT if d.weekday() == 5 else DayKind.SPECIAL if day == 24 else DayKind.REGULAR
        rows.append(_row_a(d, e, x, loc, kind))
    rows = tuple(rows)
    return AttendanceReport(ReportType.TYPE_A, ('דוגמה שירותי כח אדם בע"מ',), rows,
                            compute_summary(rows), source_name="type_a_synthetic.pdf")


def synthetic_type_b() -> AttendanceReport:
    """February 2024 (29 days, so the 31-line card ends with 1/3 and 2/3),
    invented employee 'ישראל ישראלי', rate 45.50, a vacation day with a note."""
    punches = {  # day -> (entry, exit)
        1: ("9:02", "13:05"), 4: ("8:58", "13:01"), 5: ("9:04", "12:57"), 6: ("9:01", "13:00"),
        7: ("9:00", "13:03"), 8: ("8:59", "12:58"), 11: ("9:03", "13:04"), 12: ("8:07", "12:06"),
        13: ("9:00", "13:00"), 14: ("9:05", "13:08"), 15: ("9:01", "12:59"), 18: ("9:02", "13:01"),
        19: ("8:56", "12:55"), 20: ("9:04", "13:12"), 21: ("9:00", "13:02"), 25: ("9:01", "13:00"),
        26: ("9:03", "13:06"), 27: ("8:59", "12:57"), 28: ("9:00", "13:01"), 29: ("9:02", "13:04"),
    }
    notes = {22: "חופשה"}
    rows = []
    for k in range(31):                                   # the printed card has 31 lines
        d = date(2024, 2, 1) + timedelta(days=k)
        if d.month == 2 and d.day in punches:
            e, x = (time(*map(int, t.split(":"))) for t in punches[d.day])
            rows.append(AttendanceRow(d, e, x, minutes_to_hours(time_to_minutes(x) - time_to_minutes(e))))
        else:
            rows.append(AttendanceRow(d, None, None, Decimal("0.00"), note=notes.get(d.day, "") if d.month == 2 else ""))
    rows = tuple(rows)
    return AttendanceReport(ReportType.TYPE_B, (), rows, compute_pay_summary(rows, Decimal("45.50")),
                            employee_name="ישראל ישראלי", source_name="type_b_synthetic.pdf")


# ---- 3. "scan" ------------------------------------------------------------------
def make_scan(pdf: Path, out: Path) -> None:
    from pdf2image import convert_from_path
    page = convert_from_path(str(pdf), dpi=150, grayscale=True)[0]
    buf = io.BytesIO()
    page.save(buf, "JPEG", quality=80)                    # like the real scans: 150 dpi JPEG
    buf.seek(0)
    from PIL import Image
    Image.open(buf).save(out, "PDF", resolution=150)


# ---- 5. injected OCR errors ------------------------------------------------------
def inject(doc: RawDocument, changes: list[tuple[str, str, str]]) -> tuple[RawDocument, list[str]]:
    """changes: (true text, wrong text, which) where which = 'right'/'left' picks
    the occurrence furthest right/left on the page (only used when the text
    appears twice in one row, e.g. a total printed in 'סה"כ' and in '100%')."""
    words = list(doc.words)
    done = []
    for true, wrong, which in changes:
        hits = [i for i, w in enumerate(words) if w.text == true]
        if not hits:
            raise SystemExit(f"cannot inject: '{true}' not found in the OCR output")
        pick = max(hits, key=lambda i: words[i].x0) if which == "right" else min(hits, key=lambda i: words[i].x0)
        w = words[pick]
        words[pick] = RawWord(wrong, w.x0, w.x1, w.top, w.bottom, w.conf, w.page)
        done.append(f"'{true}' -> '{wrong}'")
    return RawDocument(tuple(words), doc.method, doc.source_name), done


INJECTIONS = {
    "type_a_synthetic": [
        ("13/03/2024", "3", "right"),         # a date read as just '3' (seen on the Feb 2023 scan)
        ("מחסן", 'jr"', "right"),             # location read in Latin letters
    ],
    "type_b_synthetic": [
        ("8:07", "3:07", "right"),            # 8 read as 3 (seen twice on the Jan 2023 scan)
        ("13:12", "43:12", "right"),          # impossible time ('41:01' on the scan)
        ("15/2/24", "13", "right"),           # date reduced to '13'
    ],
}


def main() -> None:
    SYNTHETIC.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for report in (synthetic_type_a(), synthetic_type_b()):
        name = Path(report.source_name).stem
        digital = PdfRenderer().render(report, SYNTHETIC / name)
        scan = SYNTHETIC / f"{name}_scan.pdf"
        make_scan(digital, scan)
        doc = extract_ocr(scan)
        doc, injected = inject(doc, INJECTIONS[name])
        save_words(doc, FIXTURES / f"{name}.words.json", injected)
        save_truth(report, FIXTURES / f"{name}.truth.json")
        print(f"{name}: {len(doc.words)} words, injected {injected}")


if __name__ == "__main__":
    main()
