import hashlib

import pytest

from attendance_report.generation.html_renderer import HtmlRenderer
from attendance_report.generation.pdf_renderer import PdfRenderer
from attendance_report.parsing.extraction import ExtractionMode, extract
from attendance_report.pipeline import read_report, run

from conftest import TYPE_A, TYPE_B, needs_ocr

pytestmark = needs_ocr


@pytest.mark.parametrize("path", [TYPE_A, TYPE_B])
def test_output_reads_back_as_the_same_report(path, tmp_path):
    """Our parser, built for the source format, reads the generated file back
    into exactly the variant: same type, rows, totals and header."""
    result = run(path, tmp_path, [PdfRenderer()], seed=13)
    again = read_report(result.outputs[0])
    assert again.report_type == result.variant.report_type
    assert again.rows == result.variant.rows
    assert again.summary == result.variant.summary
    assert again.header_lines == result.variant.header_lines


@pytest.mark.parametrize("path, labels", [
    (TYPE_A, ["תאריך", "מקום", "כניסה", "יציאה", "הפסקה", "100%", "125%", "ימים", "נסיעות"]),
    (TYPE_B, ["תאריך", "בשבוע", "כניסה", "יציאה", "הערות", "לתשלום", "חודשיות", "לשעה"]),
])
def test_layout_matches_the_scan(path, labels, tmp_path):
    """OCR the generated PDF like a scan and compare where the fixed texts
    (column titles, box labels) are: within 1.5% of the page width/height."""
    out = run(path, tmp_path, [PdfRenderer()], seed=2).outputs[0]
    src = {w.text: w for w in extract(path).words}
    gen = {w.text: w for w in extract(out, ExtractionMode.OCR).words}
    common = [label for label in labels if label in src and label in gen]   # OCR may miss a few
    assert len(common) >= 4, common
    for label in common:
        s, g = src[label], gen[label]
        # right edge for right-aligned labels, centre for centred ones; OCR boxes
        # sometimes swallow a neighbouring border, so either may be off
        dx = min(abs(s.x1 - g.x1), abs(s.x_center - g.x_center))
        assert dx < 0.015 * 2480, label
        assert abs(s.top - g.top) < 0.015 * 3508, label


def test_input_file_is_never_changed(tmp_path):
    digest = hashlib.sha256(TYPE_A.read_bytes()).hexdigest()
    run(TYPE_A, tmp_path, [PdfRenderer(), HtmlRenderer()], seed=1)
    assert hashlib.sha256(TYPE_A.read_bytes()).hexdigest() == digest


def test_two_runs_give_identical_files(tmp_path):
    a = run(TYPE_B, tmp_path / "1", [PdfRenderer()], seed=5).outputs[0].read_bytes()
    b = run(TYPE_B, tmp_path / "2", [PdfRenderer()], seed=5).outputs[0].read_bytes()
    assert a == b


def test_html_output(tmp_path):
    out = run(TYPE_B, tmp_path, [HtmlRenderer()], seed=2)
    html = out.outputs[0].read_text(encoding="utf-8")
    assert 'dir="rtl"' in html and "ינו-23" in html and "₪" in html
    assert html.count("<tr") >= 31
