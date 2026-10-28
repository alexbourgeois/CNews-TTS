"""Segments audio : passage du dossier de travail de ffmpeg vers data/audio/.

Un « run » est un lancement de ffmpeg ; son dossier porte l'heure UTC de lancement.
Un segment n'est promu que lorsqu'il est terminé : listé dans segments.csv par ffmpeg,
ou restant après l'arrêt de ffmpeg (dernier segment, éventuellement non listé).
"""

import csv
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from cnews_tts.coverage import append_interval
from cnews_tts.timeutil import format_stamp, parse_stamp

SEGMENT_LIST = "segments.csv"
SEGMENT_PATTERN = "seg_%05d.aac"
SEGMENT_GLOB = "seg_*.aac"
MIN_LEFTOVER_S = 1.0


@dataclass(frozen=True)
class SegmentEntry:
    filename: str
    start_rel: float
    end_rel: float


@dataclass(frozen=True)
class Promoted:
    path: Path
    start: datetime
    end: datetime


def read_segment_list(csv_path: Path) -> list[SegmentEntry]:
    """Lignes complètes de la liste ffmpeg ; une dernière ligne sans fin de ligne est en cours d'écriture."""
    try:
        text = csv_path.read_text(encoding="utf-8")
    except OSError:
        return []
    entries = []
    for line in text.splitlines(keepends=True):
        if not line.endswith("\n"):
            break
        row = next(csv.reader([line]))
        if len(row) == 3:
            entries.append(SegmentEntry(Path(row[0]).name, float(row[1]), float(row[2])))
    return entries


def _promote(run_dir: Path, src: Path, start_rel: float, end_rel: float, audio_dir: Path, coverage_csv: Path) -> Promoted:
    run_start = parse_stamp(run_dir.name)
    start = run_start + timedelta(seconds=start_rel)
    end = run_start + timedelta(seconds=end_rel)
    audio_dir.mkdir(parents=True, exist_ok=True)
    dest = audio_dir / f"{format_stamp(start)}{src.suffix}"
    # La couverture d'abord : un arrêt entre les deux donne au pire une ligne en double, jamais un trou.
    append_interval(coverage_csv, start, end, dest.name)
    os.replace(src, dest)
    return Promoted(dest, start, end)


def promote_completed(run_dir: Path, audio_dir: Path, coverage_csv: Path) -> list[Promoted]:
    promoted = []
    for entry in read_segment_list(run_dir / SEGMENT_LIST):
        src = run_dir / entry.filename
        if not src.exists():
            continue
        try:
            promoted.append(_promote(run_dir, src, entry.start_rel, entry.end_rel, audio_dir, coverage_csv))
        except PermissionError:
            continue  # encore ouvert par ffmpeg : nouvel essai au prochain passage
    return promoted


def finalize_run(
    run_dir: Path, audio_dir: Path, coverage_csv: Path, probe_duration: Callable[[Path], float]
) -> list[Promoted]:
    """À appeler quand ffmpeg est arrêté : promeut tout ce qui reste, puis supprime le dossier du run.

    Un fichier verrouillé (ffmpeg orphelin, coverage.csv ouvert ailleurs…) reste dans le run,
    qui est alors conservé pour une prochaine récupération.
    """
    promoted = promote_completed(run_dir, audio_dir, coverage_csv)
    entries = {e.filename: e for e in read_segment_list(run_dir / SEGMENT_LIST)}
    next_start = max((e.end_rel for e in entries.values()), default=0.0)
    for src in sorted(run_dir.glob(SEGMENT_GLOB)):
        entry = entries.get(src.name)
        try:
            if entry is not None:
                promoted.append(_promote(run_dir, src, entry.start_rel, entry.end_rel, audio_dir, coverage_csv))
                continue
            duration = probe_duration(src)
            if duration < MIN_LEFTOVER_S:
                src.unlink()
                continue
            promoted.append(_promote(run_dir, src, next_start, next_start + duration, audio_dir, coverage_csv))
            next_start += duration
        except PermissionError:
            continue
    if not any(run_dir.glob(SEGMENT_GLOB)):
        shutil.rmtree(run_dir)
    return promoted


def recover_runs(
    work_dir: Path, audio_dir: Path, coverage_csv: Path, probe_duration: Callable[[Path], float]
) -> list[Promoted]:
    """Récupère les runs abandonnés (capture tuée ou plantée)."""
    if not work_dir.exists():
        return []
    promoted = []
    for run_dir in sorted(p for p in work_dir.iterdir() if p.is_dir()):
        try:
            parse_stamp(run_dir.name)
        except ValueError:
            continue
        promoted += finalize_run(run_dir, audio_dir, coverage_csv, probe_duration)
    return promoted


def pending_audio(audio_dir: Path) -> list[Path]:
    """Fichiers terminés en attente de transcription, du plus ancien au plus récent."""
    return sorted(p for p in audio_dir.glob("*.aac") if p.is_file())
