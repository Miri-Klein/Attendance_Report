import shutil
from pathlib import Path

import pytest

from attendance_report.pipeline import read_report

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "input"
TYPE_A = SAMPLES / "type_a_scan.pdf"     # scan of an agency report (not in the repository)
TYPE_B = SAMPLES / "type_b_scan.pdf"     # scan of an employee card (not in the repository)

_HAVE_OCR = shutil.which("tesseract") is not None
_HAVE_SAMPLES = TYPE_A.exists() and TYPE_B.exists()

# The sample scans are real reports and are not published. Tests that need
# them are skipped (with a clear reason) when they are missing.
needs_ocr = pytest.mark.skipif(not (_HAVE_OCR and _HAVE_SAMPLES),
                               reason="needs tesseract and samples/input/type_a_scan.pdf + type_b_scan.pdf")


def _require():
    if not _HAVE_OCR:
        pytest.skip("tesseract not installed")
    if not _HAVE_SAMPLES:
        pytest.skip("sample scans not found in samples/input/")


@pytest.fixture(scope="session")
def report_a():
    _require()
    return read_report(TYPE_A)


@pytest.fixture(scope="session")
def report_b():
    _require()
    return read_report(TYPE_B)
