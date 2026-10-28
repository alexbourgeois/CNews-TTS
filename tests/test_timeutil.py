from datetime import datetime, timezone

import pytest

from cnews_tts.timeutil import format_stamp, local_day, parse_stamp, to_local_iso

UTC = timezone.utc


def test_stamp_roundtrip():
    dt = datetime(2026, 10, 28, 18, 0, 0, tzinfo=UTC)
    assert format_stamp(dt) == "20261028T180000Z"
    assert parse_stamp("20261028T180000Z") == dt


def test_format_stamp_truncates_subseconds():
    assert format_stamp(datetime(2026, 10, 28, 18, 0, 0, 999000, tzinfo=UTC)) == "20261028T180000Z"


def test_parse_stamp_rejects_other_names():
    with pytest.raises(ValueError):
        parse_stamp("seg_00001")


def test_local_iso_millis_and_offset():
    dt = datetime(2026, 10, 28, 18, 0, 3, 120000, tzinfo=UTC)
    assert to_local_iso(dt, "Europe/Paris") == "2026-10-28T19:00:03.120+01:00"


def test_dst_fallback_hour_is_unambiguous():
    a = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    b = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
    assert to_local_iso(a, "Europe/Paris") == "2026-10-25T02:30:00.000+02:00"
    assert to_local_iso(b, "Europe/Paris") == "2026-10-25T02:30:00.000+01:00"
    assert format_stamp(a) != format_stamp(b)


def test_local_day_uses_paris_date():
    assert local_day(datetime(2026, 10, 28, 23, 30, tzinfo=UTC), "Europe/Paris") == "2026-10-29"
