"""Hebrew weekday names as they are printed in the reports."""
from __future__ import annotations

from datetime import date

# index = date.weekday()  (Monday=0 ... Sunday=6)
WEEKDAY_NAMES = (
    "יום שני",
    "יום שלישי",
    "יום רביעי",
    "יום חמישי",
    "יום שישי",
    "שבת",
    "יום ראשון",
)


# month labels as Excel prints them in Hebrew ("mmm-yy"): ינו-23
MONTH_ABBR = ("ינו", "פבר", "מרץ", "אפר", "מאי", "יונ", "יול", "אוג", "ספט", "אוק", "נוב", "דצמ")


def weekday_name(d: date) -> str:
    return WEEKDAY_NAMES[d.weekday()]


def weekday_short(d: date) -> str:
    """'ראשון' ... 'שישי', 'שבת' (type B prints the day without "יום")."""
    return WEEKDAY_NAMES[d.weekday()].split()[-1]


def month_label(year: int, month: int) -> str:
    return f"{MONTH_ABBR[month - 1]}-{year % 100:02d}"


def weekday_index(name: str) -> int | None:
    """Reverse lookup by the last word only, so a garbled "יום" prefix (OCR
    reads it as 'or') does not matter: 'or שני' -> Monday."""
    words = name.split()
    if not words:
        return None
    for i, full in enumerate(WEEKDAY_NAMES):
        if full.split()[-1] == words[-1]:
            return i
    return None
