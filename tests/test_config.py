from pathlib import Path

from cnews_tts.config import load_config

REPO = Path(__file__).resolve().parents[1]


def test_load_repo_config():
    cfg = load_config(REPO / "config.toml")
    assert cfg.video_id == "x3b68jn"
    assert cfg.format_selector == "bestaudio/worst"
    assert cfg.segment_seconds == 60
    assert cfg.drift_tolerance_s == 30
    assert cfg.data_dir == REPO / "data"
    assert cfg.audio_dir == REPO / "data" / "audio"
    assert cfg.coverage_csv == REPO / "data" / "coverage.csv"
    assert cfg.model == "large-v3" and cfg.language == "fr"
    assert "Sous-titrage ST' 501" in cfg.hallucination_blacklist
    assert "immigr" in cfg.alert_keywords
    assert cfg.live_model == "large-v3-turbo"
    assert cfg.alert_sound is None
    assert cfg.speech_voice == "fr_FR-siwis-medium"
    assert cfg.voices_dir == REPO / "data" / "voices"
    assert cfg.window_lifetime_s == 10
    assert cfg.game_port == 8000


def test_alert_sound_is_relative_to_config(tmp_path):
    text = (REPO / "config.toml").read_text(encoding="utf-8")
    (tmp_path / "config.toml").write_text(text.replace("[alert]\n", '[alert]\nsound = "sons/alerte.wav"\n'),
                                          encoding="utf-8")
    assert load_config(tmp_path / "config.toml").alert_sound == tmp_path / "sons" / "alerte.wav"
