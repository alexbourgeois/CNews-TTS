"""Lecture de config.toml."""

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    video_id: str
    format_selector: str
    segment_seconds: int
    stall_timeout_s: float
    drift_tolerance_s: float
    data_dir: Path
    model: str
    device: str
    compute_type: str
    language: str
    timezone: str
    hallucination_blacklist: tuple[str, ...]
    alert_keywords: tuple[str, ...] = ()
    live_model: str = "large-v3-turbo"
    alert_sound: Path | None = None
    speech_voice: str = "fr_FR-siwis-medium"
    window_lifetime_s: float = 10.0
    game_port: int = 8000

    @property
    def voices_dir(self) -> Path:
        return self.data_dir / "voices"

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def transcripts_dir(self) -> Path:
        return self.data_dir / "transcripts"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def coverage_csv(self) -> Path:
        return self.data_dir / "coverage.csv"


def load_config(path: Path) -> Config:
    path = Path(path).resolve()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    capture, paths, transcribe = raw["capture"], raw["paths"], raw["transcribe"]
    sound = raw.get("alert", {}).get("sound")
    return Config(
        video_id=capture["video_id"],
        format_selector=capture["format"],
        segment_seconds=int(capture["segment_minutes"]) * 60,
        stall_timeout_s=float(capture["stall_timeout_s"]),
        drift_tolerance_s=float(capture["drift_tolerance_s"]),
        data_dir=path.parent / paths["data_dir"],
        model=transcribe["model"],
        device=transcribe["device"],
        compute_type=transcribe["compute_type"],
        language=transcribe["language"],
        timezone=transcribe["timezone"],
        hallucination_blacklist=tuple(transcribe["hallucination_blacklist"]),
        alert_keywords=tuple(raw.get("alert", {}).get("keywords", [])),
        live_model=raw.get("live", {}).get("model", "large-v3-turbo"),
        alert_sound=path.parent / sound if sound else None,
        speech_voice=raw.get("speech", {}).get("voice", "fr_FR-siwis-medium"),
        window_lifetime_s=float(raw.get("window", {}).get("lifetime_s", 10)),
        game_port=int(raw.get("game", {}).get("port", 8000)),
    )
