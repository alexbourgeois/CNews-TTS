from pathlib import Path

from cnews_tts.config import load_config

REPO = Path(__file__).resolve().parents[1]


def test_load_repo_config():
    cfg = load_config(REPO / "config.toml")
    assert cfg.video_id == "x3b68jn"
    assert cfg.format_selector == "bestaudio/worst"
    assert cfg.segment_seconds == 600
    assert cfg.data_dir == REPO / "data"
    assert cfg.audio_dir == REPO / "data" / "audio"
    assert cfg.coverage_csv == REPO / "data" / "coverage.csv"
    assert cfg.model == "large-v3" and cfg.language == "fr"
    assert "Sous-titrage ST' 501" in cfg.hallucination_blacklist
