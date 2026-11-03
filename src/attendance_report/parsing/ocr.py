"""OCR: scanned PDF page -> words with positions (Tesseract + Hebrew pack).

Steps
1. Render the page at 300 dpi (Poppler via pdf2image). The sample scans are
   150 dpi JPEGs; rendering at 300 gives Tesseract larger glyphs.
2. If the page is a full grid (>= 5 long vertical lines; type B has 7, type A
   has 3 short ones), erase the grid lines first. Tesseract reads a table border next to a digit as
   '|' or '1' and often merges whole rows into garbage.
   Pages without a full grid (type A) are left untouched: on them the same
   erasing *hurt* (it removed strokes of digits).
3. Tesseract heb+eng, --psm 4, keep every word with its box.

Settings were chosen by trying the alternatives on the real scans:
  * heb alone garbles every number; heb+eng reads digits correctly.
  * --psm 4 reads the summary boxes; --psm 6 skipped them.
  * OCR cell-by-cell (crop each grid cell) was slower (20s) and *worse*:
    empty cells produced noise like 'So' and '--%'.
Tesseract returns Hebrew in logical order, so nothing is reversed here.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from .cleaning import clean_token
from .raw import RawDocument, RawWord

log = logging.getLogger(__name__)

OCR_DPI = 300
MIN_CONFIDENCE = 10          # below this the token is almost always a border artefact
GRID_MIN_VLINES = 5          # >= 5 vertical lines longer than 1/12 page -> "full grid" page


def extract_ocr(pdf_path: Path, page_number: int = 0, lang: str = "heb+eng") -> RawDocument:
    import pytesseract                      # imported lazily: optional dependency
    from pdf2image import convert_from_path

    page = convert_from_path(str(pdf_path), dpi=OCR_DPI, grayscale=True,
                             first_page=page_number + 1, last_page=page_number + 1)[0]
    image = np.array(page)
    if _is_grid_page(image):
        log.info("%s: full table grid detected, erasing grid lines before OCR", pdf_path.name)
        image = erase_grid_lines(image)

    data = pytesseract.image_to_data(image, lang=lang, config="--psm 4",
                                     output_type=pytesseract.Output.DICT)
    words = []
    for i, raw in enumerate(data["text"]):
        text = clean_token(raw)
        conf = float(data["conf"][i])
        if not text or conf < MIN_CONFIDENCE:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append(RawWord(text, x, x + w, y, y + h, conf))
    log.info("OCR found %d words in %s", len(words), pdf_path.name)
    return RawDocument(tuple(words), method="ocr", source_name=pdf_path.name)


def _binarize(gray: np.ndarray) -> np.ndarray:
    import cv2
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)


def _line_masks(ink: np.ndarray, h_len: int, v_len: int) -> tuple[np.ndarray, np.ndarray]:
    import cv2
    h = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1)))
    v = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len)))
    return h, v


def _is_grid_page(gray: np.ndarray) -> bool:
    import cv2
    ink = _binarize(gray)
    _, v = _line_masks(ink, 80, gray.shape[0] // 12)
    n, _, stats, _ = cv2.connectedComponentsWithStats(v)
    return n - 1 >= GRID_MIN_VLINES


def erase_grid_lines(gray: np.ndarray) -> np.ndarray:
    """Black text on white, with long horizontal/vertical strokes removed.

    Kernel lengths (80 px / 60 px at 300 dpi) are about twice the height of a
    digit, so lines go and characters stay.
    """
    import cv2
    ink = _binarize(gray)
    h, v = _line_masks(ink, 80, 60)
    lines = cv2.dilate(h | v, np.ones((5, 5), np.uint8))
    ink[lines > 0] = 0
    return 255 - ink
