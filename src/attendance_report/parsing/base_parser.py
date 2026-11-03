"""Template Method: the parsing *flow* is identical for every report type.

    find the header (1-2 lines) -> locate columns -> put the words of every
    line below it into columns -> let the subclass turn those lines into
    rows (+ the totals line) -> read the summary -> read metadata -> report

Subclasses fill in only what differs: which columns exist, how lines become
dated rows, how one row is read, where the summary is, what the metadata is.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, timedelta
from difflib import SequenceMatcher

from ..domain.calendar_he import weekday_index
from ..domain.models import AttendanceReport, AttendanceRow, ReportSummary, ReportType
from .cleaning import has_hebrew, parse_date
from .raw import Line, RawDocument, RawWord
from .repair import TimeCells

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Cell:
    text: str = ""
    conf: float = 100.0      # lowest OCR confidence among the cell's words


Cells = dict[str, Cell]      # column key -> what was found in that column on one line


@dataclass(frozen=True)
class BodyLine:
    line: Line
    cells: Cells

    @property
    def y(self) -> float:
        return self.line.y_center


@dataclass(frozen=True)
class Column:
    key: str
    label: str               # one distinctive header word


class ParseError(ValueError):
    pass


class BaseParser(ABC):
    report_type: ReportType
    columns: tuple[Column, ...]
    min_header_share = 0.5   # share of column labels that must be recognised

    # ---- the shared flow ---------------------------------------------------
    def parse(self, doc: RawDocument) -> AttendanceReport:
        lines = doc.lines()
        first, last = self._find_header(lines)
        anchors = self._locate_columns(_merge(lines[first:last + 1]))
        above = lines[:first]
        body = [BodyLine(line, self._to_cells(line, anchors)) for line in lines[last + 1:]]

        warnings: list[str] = []
        rows, summary_cells, below = self._build_rows(body, warnings)
        summary = self._parse_summary(summary_cells, above, below, warnings)
        header_lines, name, emp_id = self._parse_metadata(above, warnings)
        if not rows:
            warnings.append("no attendance rows were found")
        for w in warnings:
            log.warning("%s: %s", doc.source_name, w)
        return AttendanceReport(self.report_type, header_lines, tuple(rows), summary,
                                name, emp_id, doc.source_name, tuple(warnings))

    def _find_header(self, lines: list[Line]) -> tuple[int, int]:
        """Header = the first line (or pair of lines: type B prints two-line
        column titles) where enough column labels are recognised."""
        need = max(2, round(self.min_header_share * len(self.columns)))

        def hits(window: list[Line]) -> int:
            merged = _merge(window)
            return sum(self._match_label(c.label, merged) is not None for c in self.columns)

        for i in range(len(lines)):
            if hits(lines[i:i + 1]) >= need:
                return i, i
            # a two-line header only counts if *both* lines hold column titles,
            # otherwise the line above the table (company name) would be eaten
            if i + 1 < len(lines) and hits(lines[i:i + 1]) and hits(lines[i + 1:i + 2]) \
                    and hits(lines[i:i + 2]) >= need:
                return i, i + 1
        raise ParseError(f"{self.report_type.value}: table header not found")

    def _locate_columns(self, header: Line) -> dict[str, float]:
        """Column key -> x centre of its header word.

        OCR destroys some header words ('כניסה' -> 'non'). Columns are in a
        known order, so a missing anchor is interpolated from its recognised
        neighbours (or extrapolated at the edges) instead of failing the file.
        """
        found: dict[int, float] = {}
        for i, col in enumerate(self.columns):
            idx = self._match_label(col.label, header)
            if idx is not None:
                found[i] = header.words[idx].x_center
        if len(found) < 2:
            raise ParseError(f"{self.report_type.value}: too few column headers recognised")
        known = sorted(found)
        anchors = {}
        for i, col in enumerate(self.columns):
            if i in found:
                anchors[col.key] = found[i]
                continue
            left = max((k for k in known if k < i), default=None)
            right = min((k for k in known if k > i), default=None)
            if left is None:
                left, right = known[0], known[1]
            elif right is None:
                left, right = known[-2], known[-1]
            anchors[col.key] = found[left] + (found[right] - found[left]) * (i - left) / (right - left)
            log.info("column '%s' not recognised in header, estimated at x=%.0f",
                     col.label, anchors[col.key])
        return anchors

    @staticmethod
    def _match_label(label: str, line: Line) -> int | None:
        """Index of the word matching the label: exact match first, then fuzzy.
        (Exact first matters: 'שעות' is 86% similar to 'שעת', another column.)"""
        texts = [w.text.strip(":|") for w in line.words]
        for i, t in enumerate(texts):
            if t == label:
                return i
        for i, t in enumerate(texts):
            if _similar(label, t):
                return i
        return None

    @staticmethod
    def _to_cells(line: Line, anchors: dict[str, float]) -> Cells:
        """Each word goes to the column whose header centre is nearest."""
        found: dict[str, list[RawWord]] = {k: [] for k in anchors}
        for w in line.words:  # right-to-left, so multi-word cells keep reading order
            if set(w.text) <= set("|[]=_-—~'\"\\/"):   # pure border/noise glyphs
                continue
            found[min(anchors, key=lambda k: abs(anchors[k] - w.x_center))].append(w)
        return {k: Cell(" ".join(w.text for w in ws), min((w.conf for w in ws), default=100.0))
                for k, ws in found.items()}

    # ---- shared helpers subclasses may use ---------------------------------
    @staticmethod
    def _repair_date_by_weekday(cells: Cells, prev: date | None, warnings: list[str]) -> date | None:
        """Date of a row in a report that lists only some days. If OCR garbled
        it, the next date after the previous row with the printed weekday."""
        d = parse_date(cells["date"].text)
        label = cells.get("weekday", Cell()).text
        idx = weekday_index(label) if label else None
        if d is not None:
            if idx is not None and idx != d.weekday():
                warnings.append(f"{d:%d/%m/%Y}: printed weekday '{label}' does not match the date")
            return d
        if idx is None or prev is None or not cells["date"].text:
            return None
        for step in range(1, 8):
            cand = prev + timedelta(days=step)
            if cand.weekday() == idx:
                warnings.append(f"unreadable date '{cells['date'].text}' repaired to {cand:%d/%m/%Y}")
                return cand
        return None

    @staticmethod
    def _time_cells(cells: Cells) -> TimeCells:
        return TimeCells(cells["entry"].text, cells["exit"].text, cells["total"].text,
                         cells["entry"].conf, cells["exit"].conf, cells["total"].conf)

    # ---- the steps that differ ---------------------------------------------
    @abstractmethod
    def _build_rows(self, body: list[BodyLine], warnings: list[str]
                    ) -> tuple[list[AttendanceRow], Cells | None, list[Line]]:
        """-> (rows, the totals line if the table has one, lines below the table)"""

    @abstractmethod
    def _parse_summary(self, summary_cells: Cells | None, above: list[Line], below: list[Line],
                       warnings: list[str]) -> ReportSummary | None: ...

    @abstractmethod
    def _parse_metadata(self, above: list[Line], warnings: list[str]
                        ) -> tuple[tuple[str, ...], str, str]:
        """-> (header lines to print, employee name, employee id)"""


def _merge(lines: list[Line]) -> Line:
    words = [w for line in lines for w in line.words]
    return Line(tuple(sorted(words, key=lambda w: -w.x_center)))


def _similar(a: str, b: str) -> bool:
    """Fuzzy match for Hebrew words only. Numbers must match exactly:
    '150%' and '125%' are 75% similar but are different columns."""
    return has_hebrew(a) and len(a) >= 4 and SequenceMatcher(None, a, b).ratio() >= 0.75


def numbers_in(line: Line) -> list[str]:
    """Tokens of a line that look like amounts (used for key/value boxes)."""
    return [w.text for w in line.words if any(ch.isdigit() for ch in w.text) and not w.text.endswith("%")]


def hebrew_words(text: str, min_len: int = 2) -> list[str]:
    return [w for w in text.split() if has_hebrew(w) and len(w.strip("\"'.:")) >= min_len]
