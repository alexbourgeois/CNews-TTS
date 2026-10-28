import dataclasses
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cnews_tts import capture
from cnews_tts.__main__ import main
from cnews_tts.capture import StallDetector, is_drifted, loop_was_suspended, next_backoff
from cnews_tts.config import load_config

UTC = timezone.utc
REPO = Path(__file__).resolve().parents[1]


def t(h, m, s=0):
    return datetime(2026, 10, 28, h, m, s, tzinfo=UTC)


def test_next_backoff():
    assert next_backoff(80, productive=True) == 5
    assert next_backoff(5, productive=False) == 10
    assert next_backoff(200, productive=False) == 300


def test_is_drifted():
    assert not is_drifted(t(18, 10, 30), t(18, 10), 120)
    assert is_drifted(t(18, 10, 30), t(17, 0), 120)  # horloge partie devant (veille)
    assert is_drifted(t(17, 0), t(18, 10), 120)


def test_loop_was_suspended():
    assert not loop_was_suspended(5.4, expected_s=5)
    assert loop_was_suspended(3600, expected_s=5)


def test_stall_detector():
    d = StallDetector(timeout_s=120, now=0)
    assert not d.update(100, now=10)
    assert not d.update(100, now=129)
    assert d.update(100, now=131)
    assert not d.update(200, now=140)


def test_run_capture_survives_unexpected_errors(tmp_path, monkeypatch, caplog):
    cfg = dataclasses.replace(load_config(REPO / "config.toml"), data_dir=tmp_path)
    calls = []

    def fake_once(c):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError("coverage.csv verrouillé")
        raise KeyboardInterrupt

    monkeypatch.setattr(capture, "_capture_once", fake_once)
    monkeypatch.setattr(capture.time, "sleep", lambda s: None)
    with pytest.raises(KeyboardInterrupt):
        capture.run_capture(cfg)
    assert len(calls) == 2
    assert "coverage.csv verrouillé" in caplog.text


def test_main_logs_fatal_capture_error(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text((REPO / "config.toml").read_text(encoding="utf-8"), encoding="utf-8")

    def boom(cfg):
        raise RuntimeError("panne inattendue")

    monkeypatch.setattr(capture, "run_capture", boom)
    try:
        assert main(["--config", str(tmp_path / "config.toml"), "capture"]) == 1
    finally:
        log = logging.getLogger("cnews_tts")
        for h in list(log.handlers):
            log.removeHandler(h)
            h.close()
    assert "panne inattendue" in (tmp_path / "data" / "logs" / "capture.log").read_text(encoding="utf-8")
