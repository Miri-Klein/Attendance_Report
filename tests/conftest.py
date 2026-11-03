import shutil
from pathlib import Path

import pytest

from attendance_report.pipeline import read_report

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "input"
TYPE_A = SAMPLES / "type_a_scan.pdf"     # real scan: agency report, Oct 2022
TYPE_B = SAMPLES / "type_b_scan.pdf"     # real scan: employee card, Jan 2023

needs_ocr = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")


@pytest.fixture(scope="session")
def report_a():
    if shutil.which("tesseract") is None:
        pytest.skip("tesseract not installed")
    return read_report(TYPE_A)


@pytest.fixture(scope="session")
def report_b():
    if shutil.which("tesseract") is None:
        pytest.skip("tesseract not installed")
    return read_report(TYPE_B)
