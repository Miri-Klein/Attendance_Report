"""Reports that continue on a second page (always run, no OCR needed).

The one-page synthetic fixture is split into two pages, the way a printed
report continues: page 2 starts with the column titles again, then the rest
of the rows. Parsing both versions must give the same report.
"""
import pytest
from reportlab.pdfgen.canvas import Canvas

from attendance_report.domain.exceptions import ExtractionError, ParseError
from attendance_report.parsing.classifier import classify
from attendance_report.parsing.extraction import ExtractionMode, extract
from attendance_report.parsing.factory import get_parser
from attendance_report.parsing.raw import RawDocument, RawWord
from fixture_io import load_words


def split_in_two(doc: RawDocument, rows_on_first_page: int) -> RawDocument:
    parser = get_parser(classify(doc.text))
    lines = doc.lines()
    first, last = parser._header_span(lines)
    header = [w for line in lines[first:last + 1] for w in line.words]
    cut = last + 1 + rows_on_first_page
    shift = lines[cut].top - lines[last + 1].top          # page 2 rows start where page 1 rows did
    words = [w for line in lines[:cut] for w in line.words]
    words += [RawWord(w.text, w.x0, w.x1, w.top, w.bottom, w.conf, 1) for w in header]
    words += [RawWord(w.text, w.x0, w.x1, w.top - shift, w.bottom - shift, w.conf, 1)
              for line in lines[cut:] for w in line.words]
    return RawDocument(tuple(words), doc.method, doc.source_name)


def parse(doc):
    return get_parser(classify(doc.text)).parse(doc)


@pytest.mark.parametrize("name, rows_on_first_page", [
    ("type_a_synthetic", 8),
    ("type_b_synthetic", 14),
])
def test_two_pages_give_the_same_report(name, rows_on_first_page):
    one = load_words(name)
    two = split_in_two(one, rows_on_first_page)
    assert two.pages == 2
    a, b = parse(one), parse(two)
    assert b.rows == a.rows
    assert b.summary == a.summary


def test_type_b_page_without_any_readable_date_is_an_error_not_a_guess():
    doc = split_in_two(load_words("type_b_synthetic"), 14)
    parser = get_parser(classify(doc.text))
    page2 = [line for line in doc.lines() if line.page == 1]
    first, last = parser._header_span(page2)
    date_x = max(w.x_center for w in page2[last].words)          # the date column is rightmost
    kept = tuple(w for w in doc.words
                 if not (w.page == 1 and abs(w.x_center - date_x) < 60 and w.top > page2[last].top))
    with pytest.raises(ParseError, match="page 2"):
        parse(RawDocument(kept, doc.method, doc.source_name))


def test_text_layer_reads_every_page(tmp_path):
    path = tmp_path / "two_pages.pdf"
    c = Canvas(str(path))
    for text in ("page one", "page two"):
        c.drawString(100, 700, text)
        c.showPage()
    c.save()
    doc = extract(path, ExtractionMode.TEXT)
    assert doc.pages == 2
    assert {w.text for w in doc.words if w.page == 1} == {"page", "two"}


def test_not_a_pdf_is_a_clear_error(tmp_path):
    path = tmp_path / "notes.pdf"
    path.write_text("this is not a PDF")
    with pytest.raises(ExtractionError, match="not a readable PDF"):
        extract(path)
