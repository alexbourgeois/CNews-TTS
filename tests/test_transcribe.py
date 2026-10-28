import dataclasses
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from cnews_tts import transcribe
from cnews_tts.config import load_config
from cnews_tts.transcribe import run_transcribe

REPO = Path(__file__).resolve().parents[1]


class Seg:
    def __init__(self, start, end, text):
        self.start, self.end, self.text = start, end, text
        self.avg_logprob, self.no_speech_prob, self.compression_ratio = -0.2, 0.01, 1.3


class FakeModel:
    def __init__(self, fail_on=None):
        self.calls, self.fail_on = [], fail_on

    def transcribe(self, path, **kw):
        self.calls.append((Path(path).name, kw))
        if Path(path).name == self.fail_on:
            raise RuntimeError("fichier illisible")
        return iter([Seg(0.0, 2.0, "Bonjour."), Seg(2.0, 4.0, "Sous-titrage ST' 501")]), SimpleNamespace(duration=600.0)


A, B = "20261028T180000Z.aac", "20261028T181000Z.aac"


@pytest.fixture
def cfg(tmp_path):
    c = dataclasses.replace(load_config(REPO / "config.toml"), data_dir=tmp_path)
    c.audio_dir.mkdir(parents=True)
    for n in (A, B):
        (c.audio_dir / n).write_bytes(b"x")
    return c


def sources(cfg):
    day = cfg.transcripts_dir / "2026-10-28.jsonl"
    return [json.loads(line)["source"] for line in day.read_text(encoding="utf-8").splitlines()]


def test_transcribes_filters_and_deletes_audio(cfg):
    s = run_transcribe(cfg, model=FakeModel())
    assert (s.files, s.failed, s.dropped) == (2, 0, 2)
    assert sources(cfg) == [A, B]
    assert list(cfg.audio_dir.iterdir()) == []


def test_whisper_options(cfg):
    m = FakeModel()
    run_transcribe(cfg, model=m)
    kw = m.calls[0][1]
    assert kw["language"] == "fr" and kw["vad_filter"] is True and kw["condition_on_previous_text"] is False


def test_failed_file_is_kept_and_rerun_has_no_loss_or_duplicate(cfg):
    s = run_transcribe(cfg, model=FakeModel(fail_on=B))
    assert s.failed == 1 and not (cfg.audio_dir / A).exists() and (cfg.audio_dir / B).exists()
    run_transcribe(cfg, model=FakeModel())
    assert sources(cfg) == [A, B]


def test_faster_whisper_decodes_captured_aac(tmp_path):
    # faster-whisper 1.2.1 appelle av.open(..., metadata_errors=...), supprimé dans PyAV 19
    from faster_whisper import decode_audio

    f = tmp_path / "x.aac"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=d=3", "-c:a", "aac", "-f", "adts", str(f)], check=True)
    assert abs(len(decode_audio(str(f))) - 3 * 16000) < 1600


def test_already_transcribed_audio_deleted_without_model_call(cfg):
    run_transcribe(cfg, model=FakeModel())
    (cfg.audio_dir / A).write_bytes(b"x")  # simule un arrêt entre écriture et suppression
    m = FakeModel()
    run_transcribe(cfg, model=m)
    assert m.calls == [] and not (cfg.audio_dir / A).exists()
    assert sources(cfg) == [A, B]


def test_watch_mode_loads_model_once_and_picks_up_new_files(cfg, monkeypatch):
    loads, sleeps = [], []
    C = "20261028T182000Z.aac"

    def fake_load(c):
        loads.append(1)
        return FakeModel()

    def fake_sleep(s):
        sleeps.append(s)
        if len(sleeps) == 1:
            (cfg.audio_dir / C).write_bytes(b"x")  # la capture termine un nouveau fichier
        else:
            raise KeyboardInterrupt

    monkeypatch.setattr(transcribe, "load_model", fake_load)
    with pytest.raises(KeyboardInterrupt):
        run_transcribe(cfg, watch=True, poll_s=7, sleep=fake_sleep)
    assert loads == [1]
    assert sleeps == [7, 7]
    assert sources(cfg) == [A, B, C]
