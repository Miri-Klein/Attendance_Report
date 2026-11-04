"""OCR: scanned PDF -> words with positions (Tesseract + Hebrew pack).

For every page:
1. Render at 300 dpi (Poppler via pdf2image). The sample scans are 150 dpi
   JPEGs; rendering at 300 gives Tesseract larger glyphs.
2. Look at the page: is it a *full grid* (>= 5 long vertical lines)? Type B
   pages have 7, type A pages 3 short ones. The OCR never asks "which report
   type is this?" - it only looks at the image.
3. Grid page: erase the grid lines, then Tesseract --psm 4.
   Other pages: no erasing, Tesseract --psm 11.
4. Second look at two kinds of suspicious words. Each is cropped and read
   again on its own, with the one model that suits it:
   * Latin letters: the reports contain no English, so 'ND' or 'naw' is
     Hebrew misread by the English model -> Hebrew model:
     'ND DTN' -> 'כח אדם', 'naw' -> 'שבת', 'or' -> 'יום'.
   * A number in a box far too wide for it (a box for 5 characters holding
     '0'): digits next to Hebrew and '₪' get swallowed -> English model:
     '0' -> '45.50', '0' -> '3,649.10'.
5. Keep every word with its box, confidence and page number.

Why two settings - every alternative was tried on the four real scans:
  * Grid pages: Tesseract reads a border next to a digit as '|' or '1' and
    merges whole rows into garbage, so the lines are erased first. --psm 4
    reads the pay box above the table; --psm 11 broke it (rate read as '5').
  * Pages without a grid: erasing *hurt* (it removed strokes of digits).
    --psm 4 read 13 of 15 dates of the Feb 2023 type A scan as just '3';
    --psm 11 ("sparse text") read all 15, and the Oct 2022 scan stays correct.
    The parsers use word *positions* only, so psm 11 losing Tesseract's own
    line grouping costs nothing.
  * heb alone garbles numbers; heb+eng reads digits correctly.
  * OCR cell-by-cell was slower and worse (empty cells produced noise).
Tesseract returns Hebrew in logical order, so nothing is reversed here.
"""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

import numpy as np

from ..domain.exceptions import ExtractionError
from .cleaning import clean_token
from .raw import RawDocument, RawWord

log = logging.getLogger(__name__)

OCR_DPI = 300
MIN_CONFIDENCE = 10          # below this the token is almost always a border artefact
GRID_MIN_VLINES = 5          # >= 5 vertical lines longer than 1/12 page -> "full grid" page
PSM_GRID = "4"               # page segmentation mode for grid pages
PSM_PLAIN = "11"             # ... and for pages without a full grid
LATIN_WORD = re.compile(r"^[A-Za-z'\"‘’.,:|()]*[A-Za-z][A-Za-z'\"‘’.,:|()]*$")   # letters, no digits
HEBREW = re.compile(r"[\u0590-\u05FF]")


def extract_ocr(pdf_path: Path, lang: str = "heb+eng") -> RawDocument:
    import pytesseract                      # imported lazily: optional dependency
    from pdf2image import convert_from_path

    if shutil.which("tesseract") is None:
        raise ExtractionError("this PDF is a scan and needs OCR, but Tesseract is not installed "
                              "(see README: installation)")
    words: list[RawWord] = []
    for page_no, page in enumerate(convert_from_path(str(pdf_path), dpi=OCR_DPI, grayscale=True)):
        image = np.array(page)
        if _is_grid_page(image):
            log.info("%s p.%d: full table grid, erasing lines, psm %s", pdf_path.name, page_no + 1, PSM_GRID)
            image, psm = erase_grid_lines(image), PSM_GRID
        else:
            psm = PSM_PLAIN
        page_words = _ocr_page(pytesseract, image, lang, psm, page_no)
        words += [_second_look(pytesseract, image, w) for w in page_words]
    log.info("OCR found %d words in %s", len(words), pdf_path.name)
    return RawDocument(tuple(words), method="ocr", source_name=pdf_path.name)


def _ocr_page(pytesseract, image: np.ndarray, lang: str, psm: str, page_no: int) -> list[RawWord]:
    data = pytesseract.image_to_data(image, lang=lang, config=f"--psm {psm}",
                                     output_type=pytesseract.Output.DICT)
    words = []
    for i, raw in enumerate(data["text"]):
        text = clean_token(raw)
        conf = float(data["conf"][i])
        if not text or conf < MIN_CONFIDENCE:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append(RawWord(text, x, x + w, y, y + h, conf, page_no))
    return words


NUMBER_CHARS = re.compile(r"^[0-9.,:/₪ ]+$")
DIGIT_WIDTH = 0.75           # a digit is at most ~0.75 x the text height wide


def _second_look(pytesseract, image: np.ndarray, word: RawWord) -> RawWord:
    """Read a suspicious word again on its own (see step 4)."""
    if LATIN_WORD.match(word.text):
        text = _read_crop(pytesseract, image, word, "heb", "8")
        if HEBREW.search(text) and not re.search(r"[A-Za-z]", text):
            log.info("re-read '%s' as '%s' (Hebrew)", word.text, text)
            return _with_text(word, text)
    elif re.search(r"\d", word.text) and word.x1 - word.x0 > 2 * DIGIT_WIDTH * word.height * len(word.text):
        text = _read_crop(pytesseract, image, word, "eng", "7")
        if NUMBER_CHARS.match(text) and len(text) > len(word.text) and re.search(r"\d", text):
            log.info("re-read '%s' as '%s' (digits)", word.text, text)
            return _with_text(word, text)
    return word


def _read_crop(pytesseract, image: np.ndarray, word: RawWord, lang: str, psm: str) -> str:
    import cv2
    x0, x1, y0, y1 = int(word.x0) - 8, int(word.x1) + 8, int(word.top) - 8, int(word.bottom) + 8
    crop = image[max(0, y0):y1, max(0, x0):x1]
    if crop.size == 0:
        return ""
    crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    crop = cv2.copyMakeBorder(crop, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return clean_token(pytesseract.image_to_string(crop, lang=lang, config=f"--psm {psm}")).strip(".|:;-_= ")


def _with_text(word: RawWord, text: str) -> RawWord:
    return RawWord(text, word.x0, word.x1, word.top, word.bottom, word.conf, word.page)


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
