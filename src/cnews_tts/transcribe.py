"""Transcription par lots des fichiers audio terminés, avec faster-whisper."""

import importlib
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from cnews_tts.config import Config
from cnews_tts.hallucinations import is_hallucination
from cnews_tts.segments import pending_audio
from cnews_tts.timeutil import parse_stamp
from cnews_tts.transcripts import already_transcribed, append_records_atomic, day_file, make_record

log = logging.getLogger(__name__)


def register_nvidia_dlls() -> None:
    """Rend trouvables les DLL CUDA installées par pip (nvidia-cublas-cu12, nvidia-cudnn-cu12)."""
    for name in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        for base in module.__path__:
            bin_dir = Path(base) / "bin"
            if bin_dir.is_dir():
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def load_model(cfg: Config):
    register_nvidia_dlls()
    from faster_whisper import WhisperModel

    return WhisperModel(cfg.model, device=cfg.device, compute_type=cfg.compute_type)


def transcribe_file(model, audio_path: Path, cfg: Config) -> tuple[list[dict], float, int]:
    """(enregistrements gardés, durée de l'audio en s, nombre de segments écartés)."""
    audio_start = parse_stamp(audio_path.stem)
    segments, info = model.transcribe(
        str(audio_path), language=cfg.language, vad_filter=True, condition_on_previous_text=False, beam_size=5
    )
    records, dropped = [], 0
    for seg in segments:
        if is_hallucination(seg.text, cfg.hallucination_blacklist):
            dropped += 1
            continue
        records.append(make_record(audio_start, seg.start, seg.end, seg.text, audio_path.name, cfg.timezone,
                                   seg.avg_logprob, seg.no_speech_prob, seg.compression_ratio))
    return records, info.duration, dropped


@dataclass
class TranscribeSummary:
    files: int = 0
    failed: int = 0
    audio_seconds: float = 0.0
    wall_seconds: float = 0.0  # temps de transcription seul, hors chargement du modèle
    dropped: int = 0

    @property
    def speed(self) -> float:
        return self.audio_seconds / self.wall_seconds if self.wall_seconds else 0.0


def run_transcribe(
    cfg: Config, model=None, watch: bool = False, poll_s: float = 10.0, sleep: Callable[[float], None] = time.sleep
) -> TranscribeSummary:
    """Traite les fichiers en attente, y compris ceux terminés pendant le traitement, puis s'arrête.

    En mode watch, ne s'arrête pas : garde le modèle chargé et revérifie toutes les poll_s secondes
    (jusqu'à Ctrl+C).
    """
    summary = TranscribeSummary()
    failed: set[Path] = set()
    if watch:
        log.info("Mode continu : nouveaux fichiers vérifiés toutes les %.0f s (Ctrl+C pour arrêter)", poll_s)
    while True:
        while batch := [p for p in pending_audio(cfg.audio_dir) if p not in failed]:
            for path in batch:
                try:
                    audio_start = parse_stamp(path.stem)
                except ValueError:
                    log.error("Nom de fichier inattendu, ignoré : %s", path.name)
                    failed.add(path)
                    continue
                day = day_file(cfg.transcripts_dir, audio_start, cfg.timezone)
                if already_transcribed(day, path.name):
                    path.unlink()
                    log.info("%s déjà transcrit : audio supprimé", path.name)
                    continue
                if model is None:
                    log.info("Chargement du modèle %s sur %s…", cfg.model, cfg.device)
                    model = load_model(cfg)

                t0 = time.monotonic()
                try:
                    records, duration, dropped = transcribe_file(model, path, cfg)
                except Exception:
                    log.exception("Échec de la transcription de %s : fichier laissé en place", path.name)
                    failed.add(path)
                    continue
                append_records_atomic(day, records)
                path.unlink()
                elapsed = time.monotonic() - t0

                summary.files += 1
                summary.audio_seconds += duration
                summary.wall_seconds += elapsed
                summary.dropped += dropped
                speed = duration / elapsed if elapsed else 0.0
                log.info("[%d] %s — %.0f s d'audio en %.0f s (%.1f×), %d segment(s) écarté(s)",
                         summary.files, path.name, duration, elapsed, speed, dropped)
        if not watch:
            break
        sleep(poll_s)

    summary.failed = len(failed)
    log.info("Terminé : %d fichier(s), %.2f h d'audio, vitesse moyenne %.1f×, %d segment(s) écarté(s), "
             "%d fichier(s) en échec restant(s)", summary.files, summary.audio_seconds / 3600, summary.speed,
             summary.dropped, summary.failed)
    return summary
