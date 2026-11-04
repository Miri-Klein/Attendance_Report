"""Raw text -> TYPE_A / TYPE_B.

Not one keyword but a *set* of signals per type, each matched fuzzily, and the
type with the highest share of signals wins. A single OCR error (e.g. 'הפסקח'
instead of 'הפסקה') cannot flip the decision, and a page that matches neither
type well is rejected instead of being guessed.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from ..domain.exceptions import UnknownReportType
from ..domain.models import ReportType
from .cleaning import has_hebrew

SIGNALS: dict[ReportType, tuple[str, ...]] = {
    ReportType.TYPE_A: ("הפסקה", "מקום", "100%", "125%", "150%", "בונוס", "נסיעות"),
    ReportType.TYPE_B: ("הערות", "בשבוע", "חודשיות", "לשעה", "לתשלום", "העובד", "לחודש"),
}
MIN_SCORE = 0.5      # at least half of a type's signals must be present
FUZZY_RATIO = 0.75


def _present(signal: str, words: set[str]) -> bool:
    if signal in words:
        return True
    if len(signal) < 4 or not has_hebrew(signal):  # short words / numbers: exact only
        return False
    return any(SequenceMatcher(None, signal, w).ratio() >= FUZZY_RATIO for w in words)


def scores(raw_text: str) -> dict[ReportType, float]:
    words = {w.strip(":'\"|.") for w in raw_text.split()}
    return {t: sum(_present(s, words) for s in sig) / len(sig) for t, sig in SIGNALS.items()}


def classify(raw_text: str) -> ReportType:
    s = scores(raw_text)
    best = max(s, key=s.get)
    ranked = sorted(s.values(), reverse=True)
    if s[best] < MIN_SCORE or (len(ranked) > 1 and ranked[0] == ranked[1]):
        raise UnknownReportType(f"cannot tell the report type, scores={s}")
    return best
