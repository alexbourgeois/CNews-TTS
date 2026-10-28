from datetime import datetime, timezone

from cnews_tts import segments
from cnews_tts.coverage import read_intervals
from cnews_tts.segments import (
    SegmentEntry,
    finalize_run,
    pending_audio,
    promote_completed,
    read_segment_list,
    recover_runs,
)

UTC = timezone.utc
RUN = "20261028T175812Z"


def make_run(root, csv_text, files):
    run = root / "work" / RUN
    run.mkdir(parents=True)
    for f in files:
        (run / f).write_bytes(b"x" * 10)
    if csv_text is not None:
        (run / "segments.csv").write_text(csv_text, encoding="utf-8")
    return run


def test_read_segment_list_ignores_partial_last_line(tmp_path):
    p = tmp_path / "segments.csv"
    p.write_text("seg_00000.aac,0.000000,108.000000\nseg_00001.aac,108.0000", encoding="utf-8")
    assert read_segment_list(p) == [SegmentEntry("seg_00000.aac", 0.0, 108.0)]


def test_promote_completed_leaves_in_progress_file(tmp_path):
    run = make_run(tmp_path, "seg_00000.aac,0.000000,108.000000\n", ["seg_00000.aac", "seg_00001.aac"])
    audio, cov = tmp_path / "audio", tmp_path / "coverage.csv"
    out = promote_completed(run, audio, cov)
    assert [p.path.name for p in out] == ["20261028T175812Z.aac"]
    assert out[0].end == datetime(2026, 10, 28, 18, 0, 0, tzinfo=UTC)
    assert (audio / "20261028T175812Z.aac").exists()
    assert (run / "seg_00001.aac").exists()
    assert read_intervals(cov) == [(out[0].start, out[0].end)]


def test_promote_completed_is_idempotent(tmp_path):
    run = make_run(tmp_path, "seg_00000.aac,0.000000,108.000000\n", ["seg_00000.aac"])
    promote_completed(run, tmp_path / "audio", tmp_path / "c.csv")
    assert promote_completed(run, tmp_path / "audio", tmp_path / "c.csv") == []


def test_finalize_run_promotes_unlisted_last_segment(tmp_path):
    run = make_run(tmp_path, "seg_00000.aac,0.000000,108.000000\n", ["seg_00000.aac", "seg_00001.aac"])
    out = finalize_run(run, tmp_path / "audio", tmp_path / "c.csv", probe_duration=lambda p: 42.0)
    assert sorted(p.path.name for p in out) == ["20261028T175812Z.aac", "20261028T180000Z.aac"]
    assert max(p.end for p in out) == datetime(2026, 10, 28, 18, 0, 42, tzinfo=UTC)
    assert not run.exists()


def test_finalize_run_drops_tiny_leftover(tmp_path):
    run = make_run(tmp_path, None, ["seg_00000.aac"])
    assert finalize_run(run, tmp_path / "audio", tmp_path / "c.csv", probe_duration=lambda p: 0.4) == []
    assert not run.exists()


def test_finalize_run_keeps_locked_segment_for_later_recovery(tmp_path):
    run = make_run(tmp_path, "seg_00000.aac,0.000000,108.000000\n", ["seg_00000.aac", "seg_00001.aac"])
    with open(run / "seg_00001.aac", "rb"):  # un ffmpeg orphelin écrit encore dedans
        out = finalize_run(run, tmp_path / "audio", tmp_path / "c.csv", probe_duration=lambda p: 42.0)
    assert [p.path.name for p in out] == ["20261028T175812Z.aac"]
    assert (run / "seg_00001.aac").exists()
    out = recover_runs(tmp_path / "work", tmp_path / "audio", tmp_path / "c.csv", probe_duration=lambda p: 42.0)
    assert [p.path.name for p in out] == ["20261028T180000Z.aac"]
    assert not run.exists()


def test_finalize_run_survives_locked_coverage_csv(tmp_path, monkeypatch):
    run = make_run(tmp_path, "seg_00000.aac,0.000000,108.000000\n", ["seg_00000.aac"])

    def locked(*args):
        raise PermissionError("coverage.csv ouvert dans Excel")

    monkeypatch.setattr(segments, "append_interval", locked)
    assert finalize_run(run, tmp_path / "audio", tmp_path / "c.csv", probe_duration=lambda p: 42.0) == []
    assert (run / "seg_00000.aac").exists()
    monkeypatch.undo()
    out = recover_runs(tmp_path / "work", tmp_path / "audio", tmp_path / "c.csv", probe_duration=lambda p: 42.0)
    assert [p.path.name for p in out] == ["20261028T175812Z.aac"]


def test_recover_runs_handles_abandoned_run_without_list(tmp_path):
    make_run(tmp_path, None, ["seg_00000.aac"])
    out = recover_runs(tmp_path / "work", tmp_path / "audio", tmp_path / "c.csv", probe_duration=lambda p: 300.0)
    assert [p.path.name for p in out] == ["20261028T175812Z.aac"]
    assert list((tmp_path / "work").iterdir()) == []


def test_pending_audio_sorted_and_ignores_tmp_and_subdirs(tmp_path):
    audio = tmp_path / "audio"
    audio.mkdir()
    for n in ["20261028T181000Z.aac", "20261028T180000Z.aac", "x.aac.tmp"]:
        (audio / n).write_bytes(b"x")
    (audio / "sub").mkdir()
    (audio / "sub" / "20261028T170000Z.aac").write_bytes(b"x")
    assert [p.name for p in pending_audio(audio)] == ["20261028T180000Z.aac", "20261028T181000Z.aac"]
