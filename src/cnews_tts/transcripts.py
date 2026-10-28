"""Fichiers de transcription : un JSON Lines par jour (heure locale), écrits de façon atomique."""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from cnews_tts.timeutil import local_day, to_local_iso

REPLACE_ATTEMPTS = 25
REPLACE_WAIT_S = 0.2


def make_record(
    audio_start: datetime, seg_start: float, seg_end: float, text: str, source: str, tz: str,
    avg_logprob: float, no_speech_prob: float, compression_ratio: float,
) -> dict:
    return {
        "start": to_local_iso(audio_start + timedelta(seconds=seg_start), tz),
        "end": to_local_iso(audio_start + timedelta(seconds=seg_end), tz),
        "text": text.strip(),
        "source": source,
        "avg_logprob": round(avg_logprob, 3),
        "no_speech_prob": round(no_speech_prob, 3),
        "compression_ratio": round(compression_ratio, 3),
    }


def day_file(transcripts_dir: Path, audio_start: datetime, tz: str) -> Path:
    """Tout le contenu d'un fichier audio va dans le jour de son début."""
    return transcripts_dir / f"{local_day(audio_start, tz)}.jsonl"


def already_transcribed(day_path: Path, source: str) -> bool:
    if not day_path.exists():
        return False
    with day_path.open(encoding="utf-8") as f:
        return any(json.loads(line).get("source") == source for line in f if line.strip())


def append_records_atomic(day_path: Path, records: list[dict]) -> None:
    """Réécrit le fichier du jour (existant + nouvelles lignes) via un .tmp : jamais de fichier à moitié écrit."""
    if not records:
        return
    day_path.parent.mkdir(parents=True, exist_ok=True)
    existing = day_path.read_bytes() if day_path.exists() else b""
    if existing and not existing.endswith(b"\n"):
        existing += b"\n"
    new = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records).encode("utf-8")
    tmp = day_path.with_name(day_path.name + ".tmp")
    with tmp.open("wb") as f:
        f.write(existing + new)
        f.flush()
        os.fsync(f.fileno())  # sur disque avant que l'audio correspondant soit supprimé
    # Sous Windows, le remplacement échoue tant qu'un lecteur (follow, éditeur) tient le fichier ouvert.
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            os.replace(tmp, day_path)
            return
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(REPLACE_WAIT_S)
