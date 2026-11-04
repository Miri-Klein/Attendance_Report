"""OCR helpers on the synthetic scans (in the repo; needs Poppler only)."""
import numpy as np
from pdf2image import convert_from_path

from attendance_report.parsing.ocr import LATIN_WORD, _is_grid_page, erase_grid_lines

from conftest import SYNTHETIC, needs_poppler


def _page(name):
    return np.array(convert_from_path(str(SYNTHETIC / f"{name}.pdf"), dpi=300, grayscale=True)[0])


@needs_poppler
def test_grid_detection():
    assert _is_grid_page(_page("type_b_synthetic_scan"))        # full table grid
    assert not _is_grid_page(_page("type_a_synthetic_scan"))    # only a title rule


@needs_poppler
def test_erasing_removes_lines_and_keeps_text():
    page = _page("type_b_synthetic_scan")
    clean = erase_grid_lines(page)
    ink_before, ink_after = (page < 128).sum(), (clean < 128).sum()
    assert ink_after < ink_before                 # the grid is gone ...
    assert ink_after > 0.3 * ink_before           # ... the text is not


def test_which_words_get_a_second_hebrew_look():
    for word in ("ND", "DTN", "naw", 'jr"', "or"):
        assert LATIN_WORD.match(word), word
    for word in ("08:00", "3", "גונן", "100%", "₪", "2,038.59"):
        assert not LATIN_WORD.match(word), word
