from pathlib import Path

import pytest

from cnews_tts.config import load_config

REPO = Path(__file__).resolve().parents[1]


def test_load_repo_config():
    cfg = load_config(REPO / "config.toml")
    assert cfg.source == "cnews"
    assert cfg.stream_url == "https://www.dailymotion.com/video/x3b68jn"
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
    assert cfg.window_lifetime_s > 0  # réglage libre de l'utilisateur
    assert cfg.game_port == 8000


def test_alert_sound_is_relative_to_config(tmp_path):
    text = (REPO / "config.toml").read_text(encoding="utf-8")
    (tmp_path / "config.toml").write_text(text.replace("[alert]\n", '[alert]\nsound = "sons/alerte.wav"\n'),
                                          encoding="utf-8")
    assert load_config(tmp_path / "config.toml").alert_sound == tmp_path / "sons" / "alerte.wav"


def test_france4_source_has_its_own_data_but_shares_the_voice():
    cfg = load_config(REPO / "config.toml", source="france4")
    assert cfg.source == "france4"
    assert cfg.stream_url == "https://www.france.tv/france-4/direct.html"
    assert "language=fr" in cfg.format_selector  # piste française, pas l'audiodescription
    assert cfg.data_dir == REPO / "data" / "france4"
    assert cfg.voices_dir == REPO / "data" / "voices"


def test_unknown_source_lists_the_known_ones():
    with pytest.raises(ValueError, match="cnews, france4"):
        load_config(REPO / "config.toml", source="tf1")


def test_cli_source_before_or_after_the_command(tmp_path, capsys):
    from cnews_tts.__main__ import main

    config = tmp_path / "config.toml"
    config.write_text((REPO / "config.toml").read_text(encoding="utf-8"), encoding="utf-8")
    assert main(["--config", str(config), "--source", "france4", "coverage"]) == 0
    assert main(["--config", str(config), "coverage", "--source", "france4"]) == 0
    assert capsys.readouterr().out.count("Aucune donnée de couverture.") == 2
    with pytest.raises(SystemExit):
        main(["--config", str(config), "coverage", "--source", "tf1"])
