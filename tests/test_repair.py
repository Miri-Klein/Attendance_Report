"""Cases taken from the real type B scan (true values checked by eye)."""
from datetime import time
from decimal import Decimal

from attendance_report.parsing.repair import TimeCells, reconcile


def test_consistent_row_is_kept():
    r = reconcile(TimeCells("8:01", "11:05", "3.07"))
    assert (r.entry, r.exit, r.total, r.note) == (time(8, 1), time(11, 5), Decimal("3.07"), "")


def test_3_read_instead_of_8():
    # 3:02 -> 11:00 would be 7.97 h; fixing the total instead is rejected
    # because a 03:02 entry is outside the working window
    r = reconcile(TimeCells("3:02", "11:00", "2.97"))
    assert r.entry == time(8, 2) and r.note


def test_impossible_exit():
    assert reconcile(TimeCells("8:00", "41:01", "3.02")).exit == time(11, 1)


def test_entry_split_in_two_tokens():
    assert reconcile(TimeCells("02 :8", "11:03", "3.02")).entry == time(8, 2)


def test_tie_goes_to_the_less_confident_value():
    # 8:04 / 11:03 / 3.03: fixing entry (8:01) or exit (11:06) are both one digit
    r = reconcile(TimeCells("8:04", "11:03", "3.03", entry_conf=60, exit_conf=95))
    assert (r.entry, r.exit) == (time(8, 1), time(11, 3))
    r = reconcile(TimeCells("8:04", "11:03", "3.03", entry_conf=95, exit_conf=60))
    assert (r.entry, r.exit) == (time(8, 4), time(11, 6))


def test_break_is_part_of_the_equation():
    assert reconcile(TimeCells("08:00", "15:00", "6.50"), break_minutes=30).note == ""
    r = reconcile(TimeCells("08:00", "15:00", "6.00"), break_minutes=30)
    net = (r.exit.hour * 60 + r.exit.minute) - (r.entry.hour * 60 + r.entry.minute) - 30
    assert Decimal(net) / 60 == r.total and r.note      # repaired to a consistent row


def test_empty_day_and_noise():
    assert reconcile(TimeCells("", "", "")).entry is None
    r = reconcile(TimeCells("", "", "0"))     # noise in a shaded Shabbat row
    assert r.entry is None and r.total == 0
