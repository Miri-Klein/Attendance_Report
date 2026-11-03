"""Choose how to get words out of a PDF.

The real reports are scans (image only) -> OCR. Our own generated PDFs have a
text layer, which is read directly (exact, and much faster) - that is what the
round-trip tests use.
"""
from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

from .ocr import extract_ocr
from .raw import RawDocument
from .text_layer import extract_text_layer, has_text_layer

log = logging.getLogger(__name__)


class ExtractionMode(str, Enum):
    AUTO = "auto"        # text layer if the PDF has one, otherwise OCR
    TEXT = "text"
    OCR = "ocr"


def extract(pdf_path: Path, mode: ExtractionMode = ExtractionMode.AUTO) -> RawDocument:
    if mode is ExtractionMode.OCR or (mode is ExtractionMode.AUTO and not has_text_layer(pdf_path)):
        log.info("%s: using OCR", pdf_path.name)
        return extract_ocr(pdf_path)
    log.info("%s: using the PDF text layer", pdf_path.name)
    return extract_text_layer(pdf_path)
