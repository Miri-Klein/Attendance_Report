from datetime import date, time
from decimal import Decimal

from attendance_report.parsing.cleaning import (clean_token, parse_date, parse_decimal,
                                                parse_duration_minutes, parse_time)


def test_ocr_lookalikes_in_times():
    assert parse_time("08:0O") == time(8, 0)
    assert parse_time("|5:00") == time(15, 0)
    assert parse_time("8:01") == time(8, 1)
    assert parse_time("41:01") is None             # seen on the type B scan
    assert parse_time("גן") is None


def test_dates_both_styles():
    assert parse_date("02/10/2022") == date(2022, 10, 2)   # type A
    assert parse_date("1/1/23") == date(2023, 1, 1)        # type B
    assert parse_date("17/10/2022‏") == date(2022, 10, 17)
    assert parse_date("29/14/23") is None                   # seen on the scan
    assert parse_date("5/1123") is None


def test_numbers():
    assert parse_decimal("2,038.59") == Decimal("2038.59")  # thousands separator
    assert parse_decimal("32.35 ₪".split()[0]) == Decimal("32.35")
    assert parse_decimal("6,50") == Decimal("6.50")         # OCR comma
    assert parse_decimal("0-00") is None
    assert parse_duration_minutes("11:00") == 660


def test_hebrew_text_is_not_touched():
    assert clean_token('בע״מ') == 'בע"מ'
