from datetime import datetime, timezone

from cnews_tts.transcripts import already_transcribed, append_records_atomic, day_file, make_record

UTC = timezone.utc


def test_make_record():
    r = make_record(datetime(2026, 10, 28, 18, 0, tzinfo=UTC), 3.12, 7.8, "  Bonjour à tous. ",
                    "20261028T180000Z.aac", "Europe/Paris", avg_logprob=-0.21234, no_speech_prob=0.01,
                    compression_ratio=1.4)
    assert r == {"start": "2026-10-28T19:00:03.120+01:00", "end": "2026-10-28T19:00:07.800+01:00",
                 "text": "Bonjour à tous.", "source": "20261028T180000Z.aac",
                 "avg_logprob": -0.212, "no_speech_prob": 0.01, "compression_ratio": 1.4}


def test_day_file_uses_paris_date(tmp_path):
    assert day_file(tmp_path, datetime(2026, 10, 28, 23, 30, tzinfo=UTC), "Europe/Paris") == tmp_path / "2026-10-29.jsonl"


def test_append_atomic_and_already_transcribed(tmp_path):
    p = tmp_path / "2026-10-28.jsonl"
    append_records_atomic(p, [{"source": "a.aac", "text": "Été"}])
    append_records_atomic(p, [{"source": "b.aac", "text": "x"}])
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and "Été" in lines[0]
    assert already_transcribed(p, "a.aac") and not already_transcribed(p, "c.aac")
    assert list(tmp_path.glob("*.tmp")) == []


def test_append_empty_is_noop(tmp_path):
    append_records_atomic(tmp_path / "d.jsonl", [])
    assert not (tmp_path / "d.jsonl").exists()


def test_already_transcribed_missing_file(tmp_path):
    assert not already_transcribed(tmp_path / "nope.jsonl", "a.aac")
