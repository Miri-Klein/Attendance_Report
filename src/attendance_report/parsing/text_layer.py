"""Read words directly from the PDF text layer (no OCR).

Used when the PDF is digital - in this project that is our *own* output
(the round-trip tests read it back). Reading the text layer is exact and fast.

Quirk: ReportLab stores Hebrew in *visual* order, so 'בע"מ' is stored as
'מ"עב'. Every word that contains Hebrew letters is reversed back to logical
order. Numbers and dates are stored left-to-right and are left alone.
"""
from __future__ import annotations

from pathlib import Path

import pdfplumber

from .cleaning import clean_token, has_hebrew
from .raw import RawDocument, RawWord


def extract_text_layer(pdf_path: Path) -> RawDocument:
    """All pages; every word remembers its page number."""
    words = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages):
            for w in page.extract_words(keep_blank_chars=False, use_text_flow=False):
                text = clean_token(w["text"])
                if not text:
                    continue
                if has_hebrew(text):
                    text = text[::-1]
                words.append(RawWord(text, w["x0"], w["x1"], w["top"], w["bottom"], page=page_no))
    return RawDocument(tuple(words), method="text-layer", source_name=pdf_path.name)


def has_text_layer(pdf_path: Path, min_chars: int = 20) -> bool:
    with pdfplumber.open(pdf_path) as pdf:
        return sum(len(p.chars) for p in pdf.pages) >= min_chars
