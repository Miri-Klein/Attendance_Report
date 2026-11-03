"""Cleaning raw tokens and turning cell text into typed values.

OCR output is never clean. Typical errors seen on the sample (Tesseract heb+eng):
  * invisible direction marks glued to tokens: '17/10/2022‏'
  * '|' / 'l' / 'I' instead of 1, 'O' / 'o' instead of 0
  * ',' or ';' instead of '.' / ':'
  * a date read as garbage ('222') -> cannot be fixed here, the parser
    repairs it from the neighbouring rows (see BaseParser).

Rule: global cleaning only removes things that are never data (direction
marks, typographic quotes). Character substitutions like O->0 are applied
*only* to cells that must be numeric, so Hebrew text is never touched.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, time
from decimal import Decimal, InvalidOperation

_BIDI_MARKS = dict.fromkeys(map(ord, "‎‏‪‫‬‭‮⁦⁧⁨⁩"))
_DIGIT_LOOKALIKES = str.maketrans({"O": "0", "o": "0", "D": "0", "|": "1", "l": "1",
                                   "I": "1", "S": "5", ",": ".", ";": ":"})

HEBREW = re.compile(r"[֐-׿]")


def clean_token(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_BIDI_MARKS)
    text = text.replace("״", '"').replace("”", '"').replace("“", '"').replace("׳", "'")
    return text.strip()


def has_hebrew(text: str) -> bool:
    return bool(HEBREW.search(text))


def _numeric(text: str) -> str:
    return clean_token(text).translate(_DIGIT_LOOKALIKES).replace(" ", "")


_TIME = re.compile(r"^(\d{1,2})[:.](\d{2})$")
_DATE = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})$")
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def parse_time(text: str) -> time | None:
    m = _TIME.match(_numeric(text))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return time(h, mi) if h < 24 and mi < 60 else None


def parse_duration_minutes(text: str) -> int | None:
    """'00:30' -> 30, '11:00' -> 660 (may exceed 24h in a summary)."""
    m = _TIME.match(_numeric(text))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def parse_date(text: str) -> date | None:
    m = _DATE.match(_numeric(text))
    if not m:
        return None
    year = int(m.group(3))
    year += 2000 if year < 100 else 0          # '1/1/23' -> 2023
    try:
        return date(year, int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


_THOUSANDS = re.compile(r"^\d{1,3}(,\d{3})+(\.\d+)?$")


def parse_decimal(text: str) -> Decimal | None:
    """'6.50' -> 6.50, '2,038.59' -> 2038.59, '6,50' (OCR comma) -> 6.50."""
    t = clean_token(text).replace("₪", "").strip()
    if _THOUSANDS.match(t):
        t = t.replace(",", "")
    t = _numeric(t)
    if not _NUMBER.match(t):
        return None
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def parse_int(text: str) -> int | None:
    d = parse_decimal(text)
    return int(d) if d is not None and d == d.to_integral_value() else None
