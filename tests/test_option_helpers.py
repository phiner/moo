from __future__ import annotations

from datetime import date

from mooc.opend.option import _num, _parse_date, _parse_float_list


def test_parse_date_from_timestamp_string():
    assert _parse_date("2026-11-18") == date(2026, 11, 18)
    assert _parse_date("2026-11-18 00:00:00") == date(2026, 11, 18)


def test_parse_float_list_from_bracketed_repr():
    assert _parse_float_list("[279.9]") == [279.9]
    assert _parse_float_list("[-0.48]") == [-0.48]
    assert _parse_float_list("N/A") == []


def test_num_handles_missing_markers():
    assert _num("N/A") is None
    assert _num("") is None
    assert _num("1.25") == 1.25
    assert _num(None) is None
