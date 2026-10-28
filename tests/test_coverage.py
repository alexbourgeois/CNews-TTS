from datetime import datetime, timezone

from cnews_tts.coverage import append_interval, coverage_report, find_gaps, read_intervals

UTC = timezone.utc


def t(h, m, s=0):
    return datetime(2026, 10, 28, h, m, s, tzinfo=UTC)


def test_append_and_read(tmp_path):
    csv = tmp_path / "coverage.csv"
    append_interval(csv, t(18, 0), t(18, 10), "a.aac")
    append_interval(csv, t(18, 10), t(18, 20), "b.aac")
    assert read_intervals(csv) == [(t(18, 0), t(18, 10)), (t(18, 10), t(18, 20))]


def test_read_missing_file(tmp_path):
    assert read_intervals(tmp_path / "nope.csv") == []


def test_no_gap_for_contiguous_overlapping_or_duplicate():
    iv = [(t(18, 10, 2), t(18, 20)), (t(18, 0), t(18, 10)), (t(18, 0), t(18, 10)), (t(18, 15), t(18, 20))]
    assert find_gaps(iv, tolerance_s=5) == []


def test_gap_reported():
    assert find_gaps([(t(18, 0), t(18, 10)), (t(18, 14), t(18, 20))], tolerance_s=5) == [(t(18, 10), t(18, 14))]


def test_report_shows_gap_in_paris_time(tmp_path):
    csv = tmp_path / "coverage.csv"
    append_interval(csv, t(18, 0), t(18, 10), "a.aac")
    append_interval(csv, t(18, 14), t(18, 20), "b.aac")
    r = coverage_report(csv, "Europe/Paris")
    assert "Trous (1)" in r and "19:10:00" in r and "19:14:00" in r


def test_report_without_data(tmp_path):
    assert "Aucune donnée de couverture" in coverage_report(tmp_path / "nope.csv", "Europe/Paris")
