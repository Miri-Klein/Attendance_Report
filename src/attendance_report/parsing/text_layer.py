"""Read words directly from the PDF text layer (no OCR).

Used when the PDF is digital. The sample PDFs are digital (made with
ReportLab), and reading the text layer is exact, so we prefer it and fall back
to OCR only for scanned pages.

Quirk: the generator stored Hebrew in *visual* order, so 'בע"מ' is stored as
'מ"עב'. Every word that contains Hebrew letters is reversed back to logical
order. Numbers and dates are stored left-to-right and are left alone.
"""
from __future__ import annotations

from pathlib import Path

import pdfplumber

from .cleaning import clean_token, has_hebrew
from .raw import RawDocument, RawWord


def extract_text_layer(pdf_path: Path, page_number: int = 0) -> RawDocument:
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_number]
        words = []
        for w in page.extract_words(keep_blank_chars=False, use_text_flow=False):
            text = clean_token(w["text"])
            if not text:
                continue
            if has_hebrew(text):
                text = text[::-1]
            words.append(RawWord(text, w["x0"], w["x1"], w["top"], w["bottom"]))
    return RawDocument(tuple(words), method="text-layer", source_name=pdf_path.name)


def has_text_layer(pdf_path: Path, min_chars: int = 20) -> bool:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages[0].chars) >= min_chars
