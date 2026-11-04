"""Choose how to get words out of a PDF.

The real reports are scans (image only) -> OCR. Our own generated PDFs have a
text layer, which is read directly (exact, and much faster) - that is what the
round-trip tests use. Both readers return every page.
"""
from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

import pdfplumber

from ..domain.exceptions import ExtractionError
from .ocr import extract_ocr
from .raw import RawDocument
from .text_layer import extract_text_layer, has_text_layer

log = logging.getLogger(__name__)


class ExtractionMode(str, Enum):
    AUTO = "auto"        # text layer if the PDF has one, otherwise OCR
    TEXT = "text"
    OCR = "ocr"


def extract(pdf_path: Path, mode: ExtractionMode = ExtractionMode.AUTO) -> RawDocument:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages = len(pdf.pages)
    except Exception as exc:  # not a PDF, damaged, encrypted...
        raise ExtractionError(f"{pdf_path.name}: not a readable PDF ({exc})") from exc
    if pages == 0:
        raise ExtractionError(f"{pdf_path.name}: the PDF has no pages")

    if mode is ExtractionMode.OCR or (mode is ExtractionMode.AUTO and not has_text_layer(pdf_path)):
        log.info("%s: using OCR on %d page(s)", pdf_path.name, pages)
        doc = extract_ocr(pdf_path)
    else:
        log.info("%s: using the PDF text layer (%d page(s))", pdf_path.name, pages)
        doc = extract_text_layer(pdf_path)
    if not doc.words:
        raise ExtractionError(f"{pdf_path.name}: no text found on any page")
    return doc
