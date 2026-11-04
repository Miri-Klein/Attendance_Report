"""Generation. Round trips run on the synthetic reports (always run); the
comparison with a real scan needs the private scans and Tesseract."""
import hashlib

import pytest

from attendance_report.generation.html_renderer import HtmlRenderer
from attendance_report.generation.pdf_renderer import PdfRenderer
from attendance_report.parsing.extraction import ExtractionMode, extract
from attendance_report.pipeline import read_report, run
from attendance_report.transformation.service import TransformationService

from conftest import SCANS, SYNTHETIC, needs_tesseract

SERVICE = TransformationService()


@pytest.mark.parametrize("which", ["report_a", "report_b"])
def test_output_reads_back_as_the_same_report(which, request, tmp_path):
    """Our parser, built for the source format, reads the generated file back
    into exactly the variant: same type, rows, totals and header."""
    variant = SERVICE.transform(request.getfixturevalue(which), seed=13)
    out = PdfRenderer().render(variant, tmp_path / "variant")
    again = read_report(out)                       # text layer: no OCR needed
    assert again.report_type == variant.report_type
    assert again.rows == variant.rows
    assert again.summary == variant.summary
    assert again.header_lines == variant.header_lines
    assert again.employee_name == variant.employee_name


def test_input_file_is_never_changed(tmp_path):
    source = SYNTHETIC / "type_b_synthetic.pdf"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    run(source, tmp_path, [PdfRenderer(), HtmlRenderer()], seed=1)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest


def test_two_runs_give_identical_files(report_b, tmp_path):
    a = PdfRenderer().render(SERVICE.transform(report_b, 5), tmp_path / "one").read_bytes()
    b = PdfRenderer().render(SERVICE.transform(report_b, 5), tmp_path / "two").read_bytes()
    assert a == b


def test_html_output(report_b, tmp_path):
    out = HtmlRenderer().render(SERVICE.transform(report_b, 2), tmp_path / "v")
    html = out.read_text(encoding="utf-8")
    assert 'dir="rtl"' in html and "פבר-24" in html and "₪" in html and "חופשה" in html
    assert html.count("<tr") >= 31


@needs_tesseract
@pytest.mark.parametrize("key, labels", [
    ("a1", ["תאריך", "מקום", "כניסה", "יציאה", "הפסקה", "100%", "125%", "ימים", "נסיעות"]),
    ("b1", ["תאריך", "בשבוע", "כניסה", "יציאה", "הערות", "לתשלום", "חודשיות", "לשעה"]),
])
def test_layout_matches_the_real_scan(key, labels, tmp_path):
    """OCR the generated PDF like a scan and compare where the fixed texts
    (column titles, box labels) are: within 1.5% of the page width/height."""
    path = SCANS[key]
    if not path.exists():
        pytest.skip(f"real scan {path.name} not available (private, not in the repo)")
    out = run(path, tmp_path, [PdfRenderer()], seed=2).outputs[0]
    # a label can appear twice ('100%' as a column title and in the box): use the topmost
    src = {w.text: w for w in sorted(extract(path).words, key=lambda w: -w.top)}
    gen = {w.text: w for w in sorted(extract(out, ExtractionMode.OCR).words, key=lambda w: -w.top)}
    common = [label for label in labels if label in src and label in gen]   # OCR may miss a few
    assert len(common) >= 4, common
    for label in common:
        s, g = src[label], gen[label]
        dx = min(abs(s.x1 - g.x1), abs(s.x_center - g.x_center))
        assert dx < 0.015 * 2480, label
        assert abs(s.top - g.top) < 0.015 * 3508, label


@needs_tesseract
@pytest.mark.parametrize("name", ["type_a_synthetic_scan", "type_b_synthetic_scan"])
def test_full_pipeline_on_synthetic_scans(name, tmp_path):
    """End to end with real OCR, on the invented reports (in the repo)."""
    result = run(SYNTHETIC / f"{name}.pdf", tmp_path, [PdfRenderer()], seed=1)
    assert SERVICE.check(result.variant) == []
    assert result.outputs[0].exists()
