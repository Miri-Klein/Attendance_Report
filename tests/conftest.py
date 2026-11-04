"""Shared test fixtures.

Two kinds of input:

* **Synthetic** (always available): invented reports, saved as the words the
  OCR returned for them (tests/fixtures/*.json, built by tools/build_fixtures.py).
  No Tesseract and no private data needed, so most tests run anywhere.
* **Real scans** (optional): samples/input/*.pdf are real attendance reports
  of another person and are not in the repository. Tests that need them are
  skipped with a clear reason when they are missing.
"""
import shutil
from pathlib import Path

import pytest

from attendance_report.parsing.classifier import classify
from attendance_report.parsing.factory import get_parser
from attendance_report.pipeline import read_report
from fixture_io import load_truth, load_words

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples" / "input"
SYNTHETIC = ROOT / "samples" / "synthetic"

SCANS = {
    "a1": SAMPLES / "type_a_scan.pdf",      # agency report, Oct 2022
    "b1": SAMPLES / "type_b_scan.pdf",      # employee card, Jan 2023
    "a2": SAMPLES / "type_a_scan_2.pdf",    # agency report, Feb 2023
    "b2": SAMPLES / "type_b_scan_2.pdf",    # employee card, Sep 2022
}

HAVE_TESSERACT = shutil.which("tesseract") is not None
HAVE_POPPLER = shutil.which("pdftoppm") is not None

needs_tesseract = pytest.mark.skipif(not (HAVE_TESSERACT and HAVE_POPPLER),
                                     reason="needs Tesseract and Poppler")
needs_poppler = pytest.mark.skipif(not HAVE_POPPLER, reason="needs Poppler")


def parse_fixture(name: str):
    doc = load_words(name)
    return get_parser(classify(doc.text)).parse(doc)


# ---- synthetic: always available -------------------------------------------
@pytest.fixture(scope="session")
def report_a():
    return parse_fixture("type_a_synthetic")


@pytest.fixture(scope="session")
def report_b():
    return parse_fixture("type_b_synthetic")


@pytest.fixture(scope="session")
def truth_a():
    return load_truth("type_a_synthetic")


@pytest.fixture(scope="session")
def truth_b():
    return load_truth("type_b_synthetic")


# ---- real scans: optional ------------------------------------------------------
@pytest.fixture(scope="session")
def scan():
    """scan('b1') -> the parsed real scan, or skip if it is not available."""
    cache = {}

    def get(key: str):
        if not (HAVE_TESSERACT and HAVE_POPPLER):
            pytest.skip("needs Tesseract and Poppler")
        if not SCANS[key].exists():
            pytest.skip(f"real scan {SCANS[key].name} not in samples/input/ (private, not in the repo)")
        if key not in cache:
            cache[key] = read_report(SCANS[key])
        return cache[key]
    return get
