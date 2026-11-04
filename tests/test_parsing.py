"""Parsing.

Synthetic fixtures: the parser must rebuild the invented report *exactly*,
including the OCR errors injected into the fixture (listed inside its JSON).
Real scans (optional): expected values were read off the scans by eye.
"""
from datetime import date, time
from decimal import Decimal

from attendance_report.domain.models import ReportType, compute_pay_summary, compute_summary
from attendance_report.parsing.raw import Line, RawWord
from attendance_report.parsing.type_a_parser import TypeAParser
from fixture_io import injected_errors


# ---- synthetic (always run) ---------------------------------------------------
def test_type_a_fixture_is_rebuilt_exactly(report_a, truth_a):
    assert report_a.report_type is ReportType.TYPE_A
    assert report_a.rows == truth_a.rows
    assert report_a.summary == truth_a.summary
    assert report_a.header_lines == truth_a.header_lines


def test_type_b_fixture_is_rebuilt_exactly(report_b, truth_b):
    assert report_b.report_type is ReportType.TYPE_B
    assert report_b.rows == truth_b.rows               # 31 lines: Feb 2024 + 1/3, 2/3
    assert report_b.summary == truth_b.summary          # rate 45.50, pay 3,649.10
    assert report_b.employee_name == "ישראל ישראלי"


def test_injected_ocr_errors_are_repaired_and_reported(report_a, report_b):
    assert len(injected_errors("type_a_synthetic")) == 2
    assert len(injected_errors("type_b_synthetic")) == 3
    assert any("unreadable date '3' repaired to 13/03/2024" in w for w in report_a.warnings)
    assert any("location 'jr\"' unreadable" in w for w in report_a.warnings)
    assert any("entry '3:07' -> 08:07" in w for w in report_b.warnings)
    assert any("exit '43:12' -> 13:12" in w for w in report_b.warnings)
    assert any("unreadable date '13' placed on 15/02/2024" in w for w in report_b.warnings)


def test_type_b_next_month_lines_are_kept_empty(report_b):
    tail = report_b.rows[-2:]
    assert [r.work_date for r in tail] == [date(2024, 3, 1), date(2024, 3, 2)]
    assert not any(r.has_times for r in tail)


def test_type_b_note_on_a_day_off(report_b):
    day = next(r for r in report_b.rows if r.work_date == date(2024, 2, 22))
    assert day.note == "חופשה" and not day.has_times


def test_missing_header_word_is_interpolated():
    labels = ["תאריך", "יום", "מקום", "כניסה", "יציאה", "nyoon", 'סה"כ', "100%", "125%", "150%", "שבת"]
    xs = [520, 460, 395, 345, 305, 265, 225, 185, 140, 100, 65]
    header = Line(tuple(RawWord(t, x - 5, x + 5, 0, 9) for t, x in zip(labels, xs)))
    anchors = TypeAParser()._locate_columns(header)
    assert anchors["break"] == (anchors["exit"] + anchors["total"]) / 2


# ---- real scans (skipped when not available) -----------------------------------
B1_TRUTH = [  # type B, January 2023: (day, entry, exit, total) for every worked day
    (1, "8:01", "11:05", "3.07"), (2, "8:03", "11:03", "3.00"), (3, "8:04", "10:57", "2.88"),
    (4, "8:01", "10:59", "2.97"), (8, "8:02", "11:03", "3.02"), (9, "8:00", "10:57", "2.95"),
    (10, "8:03", "11:01", "2.97"), (11, "8:00", "11:02", "3.03"), (15, "8:04", "11:01", "2.95"),
    (16, "8:02", "11:03", "3.02"), (17, "8:00", "11:01", "3.02"), (18, "8:01", "11:02", "3.02"),
    (19, "8:06", "11:02", "2.93"), (22, "8:02", "11:03", "3.02"), (23, "8:10", "11:12", "3.03"),
    (24, "8:01", "11:04", "3.05"), (25, "8:06", "11:03", "2.95"), (26, "8:02", "11:00", "2.97"),
    (29, "8:01", "11:03", "3.03"), (30, "8:02", "11:01", "2.98"), (31, "8:00", "11:10", "3.17"),
]


def _t(s):
    h, m = s.split(":")
    return time(int(h), int(m))


def test_scan_a1(scan):
    r = scan("a1")
    assert len(r.rows) == 22 and r.rows[0].work_date == date(2022, 10, 2)
    assert all(x.total_hours == Decimal("6.50") and x.location == "גליליון" for x in r.rows)
    holiday = next(x for x in r.rows if x.work_date == date(2022, 10, 17))
    assert holiday.buckets.overtime_150 == Decimal("6.50") and holiday.buckets.regular_100 == 0
    assert (r.summary.days, r.summary.total_hours) == (22, Decimal("143.00"))
    assert r.header_lines == ('נ.ע. הנשר כח אדם בע"מ',)


def test_scan_a2(scan):
    r = scan("a2")
    assert len(r.rows) == 15 and r.rows[-1].work_date == date(2023, 2, 27)
    assert all(x.location == "גונן" for x in r.rows)
    late = next(x for x in r.rows if x.work_date == date(2023, 2, 16))
    assert (late.entry, late.exit) == (time(9), time(17))
    assert r.summary == compute_summary(r.rows)            # 15 days, 110.50 hours
    assert r.header_lines == ('נ.ע. הנשר כח אדם בע"מ',)   # 'כח אדם' was read as 'ND DTN'


def test_scan_b1_every_value(scan):
    r = scan("b1")
    assert len(r.rows) == 31
    worked = {x.work_date.day: x for x in r.rows if x.has_times}
    assert sorted(worked) == [d for d, *_ in B1_TRUTH]
    for day, entry, exit_, total in B1_TRUTH:
        x = worked[day]
        assert (x.entry, x.exit, x.total_hours) == (_t(entry), _t(exit_), Decimal(total)), day
    s = compute_pay_summary(r.rows, r.summary.hourly_rate)
    assert (s.total_hours, s.total_pay) == (Decimal("63.02"), Decimal("2038.59"))   # as printed


def test_scan_b2(scan):
    r = scan("b2")
    assert len(r.rows) == 31 and r.rows[-1].work_date == date(2022, 10, 1)   # 31-line card
    assert sum(x.has_times for x in r.rows) == 24
    assert all((x.entry, x.exit) == (time(8, 30), time(12)) for x in r.rows if x.has_times)
    notes = {x.work_date.day: x.note for x in r.rows if x.note}
    assert notes == {25: "ערב ראש השנה", 26: "ראש השנה", 27: "ראש השנה"}
    assert (r.summary.hourly_rate, r.summary.total_pay) == (Decimal("30.65"), Decimal("2574.60"))
    # the card prints 20 work days, but lists 24 (24 x 3.50 = the printed 84.00 hours)
    assert r.summary.days == 20
    assert compute_pay_summary(r.rows, r.summary.hourly_rate).days == 24
