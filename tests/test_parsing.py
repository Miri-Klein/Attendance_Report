"""Parsing the two real scans. Expected values were read off the scans by eye."""
from datetime import date, time
from decimal import Decimal

from attendance_report.domain.models import ReportType, compute_pay_summary
from attendance_report.parsing.raw import Line, RawWord
from attendance_report.parsing.type_a_parser import TypeAParser

# type B, January 2023: (day, entry, exit, total) for every worked day
B_TRUTH = [
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


def test_type_a_rows(report_a):
    assert report_a.report_type is ReportType.TYPE_A
    assert len(report_a.rows) == 22
    assert report_a.rows[0].work_date == date(2022, 10, 2)
    assert report_a.rows[-1].work_date == date(2022, 10, 31)
    for r in report_a.rows:
        assert r.break_minutes == 30 and r.total_hours == Decimal("6.50")
        assert r.location == "גליליון"
    shabbat = [r for r in report_a.rows if r.is_shabbat]
    assert [r.work_date.day for r in shabbat] == [8, 15, 22]
    assert all(r.buckets.shabbat_150 == Decimal("6.50") for r in shabbat)
    holiday = next(r for r in report_a.rows if r.work_date == date(2022, 10, 17))
    assert holiday.buckets.overtime_150 == Decimal("6.50") and holiday.buckets.regular_100 == 0
    late = next(r for r in report_a.rows if r.work_date == date(2022, 10, 22))
    assert (late.entry, late.exit) == (time(9), time(16))


def test_type_a_summary_and_header(report_a):
    s = report_a.summary
    assert (s.days, s.break_minutes, s.total_hours) == (22, 660, Decimal("143.00"))
    assert (s.buckets.regular_100, s.buckets.overtime_150, s.buckets.shabbat_150) == \
           (Decimal("117.00"), Decimal("6.50"), Decimal("19.50"))
    assert report_a.header_lines == ('נ.ע. הנשר כח אדם בע"מ',)
    assert report_a.employee_name == ""          # blacked out on the scan


def test_type_b_every_value_matches_the_scan(report_b):
    assert report_b.report_type is ReportType.TYPE_B
    assert len(report_b.rows) == 31              # every day of January
    worked = {r.work_date.day: r for r in report_b.rows if r.has_times}
    assert sorted(worked) == [d for d, *_ in B_TRUTH]
    for day, entry, exit_, total in B_TRUTH:
        r = worked[day]
        assert (r.entry, r.exit, r.total_hours) == (_t(entry), _t(exit_), Decimal(total)), day


def test_type_b_summary(report_b):
    s = report_b.summary
    assert s.hourly_rate == Decimal("32.35")
    assert s.total_pay == Decimal("2038.59")
    assert s.days == 21
    # the strongest check: pay recomputed from the parsed minutes equals the printed pay
    recomputed = compute_pay_summary(report_b.rows, s.hourly_rate)
    assert (recomputed.total_hours, recomputed.total_pay, recomputed.days) == \
           (Decimal("63.02"), Decimal("2038.59"), 21)


def test_ocr_repairs_are_reported(report_b):
    assert any("placed on" in w for w in report_b.warnings)     # garbled dates
    assert any("entry '3:02' -> 08:02" in w for w in report_b.warnings)


def test_missing_header_word_is_interpolated():
    labels = ["תאריך", "יום", "מקום", "כניסה", "יציאה", "nyoon", 'סה"כ', "100%", "125%", "150%", "שבת"]
    xs = [520, 460, 395, 345, 305, 265, 225, 185, 140, 100, 65]
    header = Line(tuple(RawWord(t, x - 5, x + 5, 0, 9) for t, x in zip(labels, xs)))
    anchors = TypeAParser()._locate_columns(header)
    assert anchors["break"] == (anchors["exit"] + anchors["total"]) / 2
