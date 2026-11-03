from dataclasses import FrozenInstanceError, replace
from datetime import date, time
from decimal import ROUND_HALF_UP, Decimal

import pytest

from attendance_report.domain.models import AttendanceRow, HourBuckets
from attendance_report.transformation.rules import TYPE_A_RULES, TYPE_B_RULES
from attendance_report.transformation.service import EmptyReportError, TransformationService
from attendance_report.transformation.strategies import DayKind, MissingRateError, split_hours

SERVICE = TransformationService()


def test_same_seed_same_output(report_a, report_b):
    for r in (report_a, report_b):
        assert SERVICE.transform(r, 7) == SERVICE.transform(r, 7)


def test_different_seed_different_output(report_a):
    assert SERVICE.transform(report_a, 1).rows != SERVICE.transform(report_a, 2).rows


@pytest.mark.parametrize("seed", range(150))
def test_invariants_hold_for_many_seeds(report_a, report_b, seed):
    for report in (report_a, report_b):
        assert SERVICE.check(SERVICE.transform(report, seed)) == []


def test_source_is_not_modified(report_a):
    before = replace(report_a)
    SERVICE.transform(report_a, 3)
    assert report_a == before
    with pytest.raises(FrozenInstanceError):
        report_a.rows[0].entry = time(9)


def test_only_times_change(report_a, report_b):
    for report in (report_a, report_b):
        new = SERVICE.transform(report, 5)
        assert new.header_lines == report.header_lines
        for old, cur in zip(report.rows, new.rows):
            assert (cur.work_date, cur.location, cur.note, cur.break_minutes, cur.has_times) == \
                   (old.work_date, old.location, old.note, old.break_minutes, old.has_times)


def test_type_a_keeps_rate_category(report_a):
    new = SERVICE.transform(report_a, 11)
    by_date = {r.work_date: r for r in new.rows}
    holiday = by_date[date(2022, 10, 17)]
    assert holiday.buckets.overtime_150 == holiday.total_hours and holiday.buckets.regular_100 == 0
    for r in new.rows:
        if r.is_shabbat:
            assert r.buckets.shabbat_150 == r.total_hours


def test_type_a_shifts_are_round(report_a):
    for old, cur in zip(report_a.rows, SERVICE.transform(report_a, 11).rows):
        shift = abs((cur.entry.hour * 60 + cur.entry.minute) - (old.entry.hour * 60 + old.entry.minute))
        assert shift <= TYPE_A_RULES.max_entry_shift_minutes and cur.entry.minute % 5 == 0


def test_type_b_minute_level_and_empty_days(report_b):
    new = SERVICE.transform(report_b, 4)
    for old, cur in zip(report_b.rows, new.rows):
        if not old.has_times:
            assert cur == old
            continue
        shift = abs((cur.entry.hour * 60 + cur.entry.minute) - (old.entry.hour * 60 + old.entry.minute))
        assert shift <= TYPE_B_RULES.max_entry_shift_minutes
    assert any(r.entry.minute % 5 for r in new.rows if r.has_times)   # not rounded like A


def test_type_b_pay_recomputed(report_b):
    new = SERVICE.transform(report_b, 9)
    s = new.summary
    minutes = sum(r.net_minutes for r in new.rows if r.has_times)
    assert s.hourly_rate == report_b.summary.hourly_rate
    assert s.total_pay == (Decimal(minutes) * s.hourly_rate / 60).quantize(Decimal("0.01"), ROUND_HALF_UP)
    assert s.days == 21


def test_type_a_summary_recomputed(report_a):
    new = SERVICE.transform(report_a, 9)
    assert new.summary.total_hours == sum(r.total_hours for r in new.rows)
    assert new.summary.days == 22


def test_split_hours():
    r = TYPE_A_RULES
    assert split_hours(Decimal("7.50"), DayKind.REGULAR, r) == HourBuckets(Decimal("7.50"))
    assert split_hours(Decimal("9.25"), DayKind.REGULAR, r) == HourBuckets(Decimal("8.00"), Decimal("1.25"))
    assert split_hours(Decimal("11.00"), DayKind.REGULAR, r) == \
        HourBuckets(Decimal("8.00"), Decimal("2.00"), Decimal("1.00"))
    assert split_hours(Decimal("6.00"), DayKind.SHABBAT, r).shabbat_150 == Decimal("6.00")
    assert split_hours(Decimal("6.00"), DayKind.SPECIAL, r).overtime_150 == Decimal("6.00")


def test_late_shift_is_pulled_back(report_a):
    late = AttendanceRow(date(2022, 10, 2), time(13, 0), time(21, 50), Decimal("11.50"), 30,
                         "גליליון", HourBuckets(Decimal("11.50")))
    report = replace(report_a, rows=(late,), summary=None)
    for seed in range(50):
        assert SERVICE.transform(report, seed).rows[0].exit <= TYPE_A_RULES.limits.latest_exit


def test_empty_report_is_rejected(report_a):
    with pytest.raises(EmptyReportError):
        SERVICE.transform(replace(report_a, rows=()), 1)


def test_type_b_without_rate_is_rejected(report_b):
    no_rate = replace(report_b, summary=replace(report_b.summary, hourly_rate=None))
    with pytest.raises(MissingRateError):
        SERVICE.transform(no_rate, 1)
