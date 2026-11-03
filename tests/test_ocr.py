import numpy as np
from pdf2image import convert_from_path

from attendance_report.parsing.ocr import _is_grid_page, erase_grid_lines

from conftest import TYPE_A, TYPE_B, needs_ocr


def _page(path):
    return np.array(convert_from_path(str(path), dpi=300, grayscale=True)[0])


@needs_ocr
def test_grid_detection():
    assert _is_grid_page(_page(TYPE_B))        # full table grid
    assert not _is_grid_page(_page(TYPE_A))    # only a title rule


@needs_ocr
def test_erasing_keeps_text_and_removes_lines():
    page = _page(TYPE_B)
    clean = erase_grid_lines(page)
    # a long vertical table border (x ~ 1797 px) is gone, text pixels remain
    column = (clean[1200:2800, 1790:1805] < 128).sum()
    assert column < 0.05 * (page[1200:2800, 1790:1805] < 128).sum() + 50
    assert (clean < 128).sum() > 0.2 * (page < 128).sum()
