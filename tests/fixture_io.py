"""Save / load test fixtures as JSON.

A fixture = what the OCR returned for a *synthetic* report (invented company,
invented employee, invented hours), plus the true report it was made from.
Tests load the words and run the real classifier + parser on them, so they
need neither Tesseract nor the private sample scans.

Built by:  python -m tools.build_fixtures   (needs Tesseract, run once)
"""
from __future__ import annotations

import json
from datetime import date, time
from decimal import Decimal
from pathlib import Path

from attendance_report.domain.models import (AttendanceReport, AttendanceRow, HourBuckets,
                                             ReportSummary, ReportType)
from attendance_report.parsing.raw import RawDocument, RawWord

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ---- OCR words ---------------------------------------------------------------
def save_words(doc: RawDocument, path: Path, injected: list[str]) -> None:
    data = {
        "source": doc.source_name,
        "method": doc.method,
        "injected_ocr_errors": injected,
        "words": [[w.text, round(w.x0, 1), round(w.x1, 1), round(w.top, 1), round(w.bottom, 1),
                   round(w.conf, 1), w.page] for w in doc.words],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")


def load_words(name: str) -> RawDocument:
    data = json.loads((FIXTURES / f"{name}.words.json").read_text(encoding="utf-8"))
    words = tuple(RawWord(t, x0, x1, top, bottom, conf, page)
                  for t, x0, x1, top, bottom, conf, page in data["words"])
    return RawDocument(words, method=data["method"], source_name=data["source"])


def injected_errors(name: str) -> list[str]:
    data = json.loads((FIXTURES / f"{name}.words.json").read_text(encoding="utf-8"))
    return data["injected_ocr_errors"]


# ---- the true report -----------------------------------------------------------
def _t(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t else None


def save_truth(report: AttendanceReport, path: Path) -> None:
    s = report.summary
    data = {
        "report_type": report.report_type.value,
        "header_lines": list(report.header_lines),
        "employee_name": report.employee_name,
        "rows": [{
            "date": r.work_date.isoformat(), "entry": _t(r.entry), "exit": _t(r.exit),
            "total": str(r.total_hours), "break": r.break_minutes, "location": r.location,
            "buckets": None if r.buckets is None else [str(r.buckets.regular_100), str(r.buckets.overtime_125),
                                                      str(r.buckets.overtime_150), str(r.buckets.shabbat_150)],
            "note": r.note,
        } for r in report.rows],
        "summary": None if s is None else {
            "days": s.days, "break": s.break_minutes, "total": str(s.total_hours),
            "buckets": [str(s.buckets.regular_100), str(s.buckets.overtime_125),
                        str(s.buckets.overtime_150), str(s.buckets.shabbat_150)],
            "bonus": str(s.bonus), "travel": str(s.travel),
            "rate": None if s.hourly_rate is None else str(s.hourly_rate),
            "pay": None if s.total_pay is None else str(s.total_pay),
        },
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load_truth(name: str) -> AttendanceReport:
    data = json.loads((FIXTURES / f"{name}.truth.json").read_text(encoding="utf-8"))

    def tm(s: str | None) -> time | None:
        return None if s is None else time(*map(int, s.split(":")))

    def bk(b: list[str] | None) -> HourBuckets | None:
        return None if b is None else HourBuckets(*map(Decimal, b))

    rows = tuple(AttendanceRow(date.fromisoformat(r["date"]), tm(r["entry"]), tm(r["exit"]),
                               Decimal(r["total"]), r["break"], r["location"], bk(r["buckets"]), r["note"])
                 for r in data["rows"])
    s = data["summary"]
    summary = None if s is None else ReportSummary(
        s["days"], s["break"], Decimal(s["total"]), bk(s["buckets"]), Decimal(s["bonus"]),
        Decimal(s["travel"]), None if s["rate"] is None else Decimal(s["rate"]),
        None if s["pay"] is None else Decimal(s["pay"]))
    return AttendanceReport(ReportType(data["report_type"]), tuple(data["header_lines"]), rows, summary,
                            data["employee_name"])
