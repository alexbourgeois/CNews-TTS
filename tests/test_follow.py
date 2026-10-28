from cnews_tts.follow import TranscriptFollower
from cnews_tts.transcripts import append_records_atomic


def rec(start, text):
    return {"start": start, "end": start, "text": text, "source": "x.aac"}


def test_first_poll_shows_backlog_of_newest_day(tmp_path):
    append_records_atomic(tmp_path / "2026-10-27.jsonl", [rec("2026-10-27T23:59:00.000+01:00", "hier")])
    append_records_atomic(tmp_path / "2026-10-28.jsonl",
                          [rec(f"2026-10-28T19:00:0{i}.000+01:00", f"phrase {i}") for i in range(5)])
    f = TranscriptFollower(tmp_path, backlog=3)
    assert f.poll() == ["19:00:02  phrase 2", "19:00:03  phrase 3", "19:00:04  phrase 4"]
    assert f.poll() == []


def test_poll_returns_only_new_lines_across_days(tmp_path):
    day1 = tmp_path / "2026-10-28.jsonl"
    append_records_atomic(day1, [rec("2026-10-28T23:58:00.000+01:00", "avant")])
    f = TranscriptFollower(tmp_path, backlog=0)
    assert f.poll() == []
    append_records_atomic(day1, [rec("2026-10-28T23:59:00.000+01:00", "fin de journée")])
    append_records_atomic(tmp_path / "2026-10-29.jsonl", [rec("2026-10-29T00:00:05.000+01:00", "minuit passé")])
    assert f.poll() == ["23:59:00  fin de journée", "00:00:05  minuit passé"]


def test_missing_directory(tmp_path):
    assert TranscriptFollower(tmp_path / "transcripts", backlog=10).poll() == []
