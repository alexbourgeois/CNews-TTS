"""Affichage du texte au fur et à mesure qu'il est transcrit."""

import json
import sys
import time
from pathlib import Path


def format_line(record: dict) -> str:
    """19:39:09  Et si on sait se persuader…"""
    return f"{record['start'][11:19]}  {record['text']}"


def _parse(lines: list[str]) -> list[str]:
    return [format_line(json.loads(line)) for line in lines if line.strip()]


class TranscriptFollower:
    """Suit tous les fichiers jour : un texte arrivé en retard dans la veille est aussi affiché."""

    def __init__(self, transcripts_dir: Path, backlog: int = 10):
        self.transcripts_dir = transcripts_dir
        self.backlog = backlog
        self._offsets: dict[Path, int] | None = None

    def poll(self) -> list[str]:
        files = sorted(self.transcripts_dir.glob("*.jsonl"))
        if self._offsets is None:
            self._offsets = {p: p.stat().st_size for p in files}
            if not files or self.backlog <= 0:
                return []
            lines = files[-1].read_text(encoding="utf-8").splitlines()
            return _parse(lines[-self.backlog:])

        new = []
        for p in files:
            size = p.stat().st_size
            offset = self._offsets.get(p, 0)
            if size < offset:  # fichier réécrit plus court : on repart du début
                offset = 0
            if size == offset:
                continue
            with p.open("rb") as f:
                f.seek(offset)
                chunk = f.read()
            end = chunk.rfind(b"\n") + 1  # lignes complètes seulement
            self._offsets[p] = offset + end
            new += _parse(chunk[:end].decode("utf-8").splitlines())
        return new


def run_follow(transcripts_dir: Path, backlog: int = 10, poll_s: float = 2.0) -> None:
    """Tourne jusqu'à Ctrl+C."""
    sys.stdout.reconfigure(errors="replace")
    follower = TranscriptFollower(transcripts_dir, backlog)
    while True:
        for line in follower.poll():
            print(line, flush=True)
        time.sleep(poll_s)
