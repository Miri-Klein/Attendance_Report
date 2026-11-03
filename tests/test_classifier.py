import pytest

from attendance_report.domain.models import ReportType
from attendance_report.parsing.classifier import UnknownReportType, classify

from conftest import TYPE_A, TYPE_B, needs_ocr
from attendance_report.parsing.extraction import extract


@needs_ocr
@pytest.mark.parametrize("path, expected", [(TYPE_A, ReportType.TYPE_A), (TYPE_B, ReportType.TYPE_B)])
def test_real_scans_are_classified(path, expected):
    assert classify(extract(path).text) == expected


def test_one_garbled_keyword_does_not_flip_the_type():
    text = 'תאריך יום מקום כניסה יציאה הפסקח סה"כ 100% 125% 150% שבת'   # הפסקה misread
    assert classify(text) == ReportType.TYPE_A


def test_type_b_signals():
    assert classify('שם העובד: סה"כ ימי עבודה לחודש מחיר לשעה סה"כ לתשלום') == ReportType.TYPE_B


def test_unrelated_text_is_rejected():
    with pytest.raises(UnknownReportType):
        classify("חשבונית מס קבלה סכום")
