"""What every extractor (text layer or OCR) hands to the rest of the pipeline.

A list of words with their position on the page, in *logical* Hebrew order.
Keeping positions (and not only a flat string) is what lets the parser put
each value in the right column even when a cell is empty - e.g. the summary
row of type A has nothing under "כניסה"/"יציאה", so reading tokens by order
would shift every value one column to the right.

Multi-page reports: every word knows its page. Lines are built page by page
and ordered (page, height), so a line never mixes words from two pages.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class RawWord:
    text: str
    x0: float
    x1: float
    top: float               # measured from the top of *its own* page
    bottom: float
    conf: float = 100.0      # OCR confidence 0-100; text-layer words are certain
    page: int = 0

    @property
    def x_center(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass(frozen=True)
class Line:
    words: tuple[RawWord, ...]  # right-to-left (reading order of a Hebrew line)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def y_center(self) -> float:
        return sum((w.top + w.bottom) / 2 for w in self.words) / len(self.words)

    @property
    def page(self) -> int:
        return self.words[0].page


@dataclass(frozen=True)
class RawDocument:
    words: tuple[RawWord, ...]
    method: str          # "text-layer" or "ocr"
    source_name: str = ""

    def lines(self) -> list[Line]:
        return build_lines(self.words)

    @property
    def pages(self) -> int:
        return 1 + max((w.page for w in self.words), default=0)

    @property
    def text(self) -> str:
        """The plain raw string (one line per table row)."""
        return "\n".join(line.text for line in self.lines())


def build_lines(words: tuple[RawWord, ...] | list[RawWord]) -> list[Line]:
    """Group words whose vertical centres are close into one line, page by page.

    The tolerance is relative to the typical word height, so the same code
    works for PDF points (text layer) and for 300-dpi pixels (OCR).
    """
    if not words:
        return []
    tol = 0.5 * median(w.height for w in words)
    ordered = sorted(words, key=lambda w: (w.page, (w.top + w.bottom) / 2))
    groups: list[list[RawWord]] = []
    for w in ordered:
        c = (w.top + w.bottom) / 2
        if groups and groups[-1][0].page == w.page and abs(c - _centre(groups[-1])) <= tol:
            groups[-1].append(w)
        else:
            groups.append([w])
    return [Line(tuple(sorted(g, key=lambda w: -w.x_center))) for g in groups]


def _centre(group: list[RawWord]) -> float:
    return sum((w.top + w.bottom) / 2 for w in group) / len(group)
