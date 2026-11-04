import pytest

from attendance_report.domain.exceptions import AttendanceReportError, UnknownReportType
from attendance_report.domain.models import ReportType
from attendance_report.parsing.classifier import classify
from fixture_io import load_words


@pytest.mark.parametrize("name, expected", [
    ("type_a_synthetic", ReportType.TYPE_A),
    ("type_b_synthetic", ReportType.TYPE_B),
])
def test_synthetic_reports_are_classified(name, expected):
    assert classify(load_words(name).text) == expected


@pytest.mark.parametrize("key, expected", [
    ("a1", ReportType.TYPE_A), ("a2", ReportType.TYPE_A),
    ("b1", ReportType.TYPE_B), ("b2", ReportType.TYPE_B),
])
def test_all_four_real_scans_are_classified(scan, key, expected):
    assert scan(key).report_type == expected


def test_one_garbled_keyword_does_not_flip_the_type():
    text = 'תאריך יום מקום כניסה יציאה הפסקח סה"כ 100% 125% 150% שבת'   # הפסקה misread
    assert classify(text) == ReportType.TYPE_A


def test_type_b_signals():
    assert classify('שם העובד: סה"כ ימי עבודה לחודש מחיר לשעה סה"כ לתשלום') == ReportType.TYPE_B


def test_unrelated_text_is_rejected_clearly():
    with pytest.raises(UnknownReportType) as err:
        classify("חשבונית מס קבלה סכום")
    assert "cannot tell the report type" in str(err.value)
    assert isinstance(err.value, AttendanceReportError)
