"""Capture continue : ffmpeg enregistre le direct, relancé à chaque arrêt."""

import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path

from cnews_tts.config import Config
from cnews_tts.media import build_ffmpeg_cmd, probe_duration, stop_ffmpeg
from cnews_tts.segments import SEGMENT_GLOB, finalize_run, promote_completed, recover_runs
from cnews_tts.stream import StreamError, resolve_stream
from cnews_tts.timeutil import format_stamp, to_local_iso, utc_now

log = logging.getLogger(__name__)

POLL_S = 5.0
BASE_BACKOFF_S = 5.0
MAX_BACKOFF_S = 300.0


def next_backoff(current: float, productive: bool, base: float = BASE_BACKOFF_S, cap: float = MAX_BACKOFF_S) -> float:
    return base if productive else min(current * 2, cap)


def is_drifted(now: datetime, last_end: datetime, tolerance_s: float) -> bool:
    return abs((now - last_end).total_seconds()) > tolerance_s


def loop_was_suspended(elapsed_s: float, expected_s: float, slack_s: float = 30.0) -> bool:
    return elapsed_s > expected_s + slack_s


class StallDetector:
    """Signale un flux figé : aucune croissance des fichiers depuis plus de timeout_s."""

    def __init__(self, timeout_s: float, now: float):
        self.timeout_s = timeout_s
        self._bytes = 0
        self._last_change = now

    def update(self, total_bytes: int, now: float) -> bool:
        if total_bytes != self._bytes:
            self._bytes = total_bytes
            self._last_change = now
            return False
        return now - self._last_change > self.timeout_s


def _run_bytes(run_dir: Path) -> int:
    total = 0
    for p in run_dir.glob(SEGMENT_GLOB):
        try:
            total += p.stat().st_size
        except FileNotFoundError:
            pass  # promu entre-temps
    return total


def _watch(proc: subprocess.Popen, run_dir: Path, cfg: Config) -> tuple[str, int]:
    """Surveille ffmpeg ; renvoie la raison de l'arrêt et le nombre de segments promus."""
    stall = StallDetector(cfg.stall_timeout_s, time.monotonic())
    promoted = 0
    last_tick = time.time()
    while proc.poll() is None:
        time.sleep(POLL_S)
        now_wall = time.time()
        if loop_was_suspended(now_wall - last_tick, POLL_S):
            return f"réveil après {now_wall - last_tick:.0f} s d'interruption (mise en veille ?)", promoted
        last_tick = now_wall

        done = promote_completed(run_dir, cfg.audio_dir, cfg.coverage_csv)
        for p in done:
            log.info("Segment terminé : %s (%s, %.0f s)", p.path.name, to_local_iso(p.start, cfg.timezone),
                     (p.end - p.start).total_seconds())
        promoted += len(done)
        if done and is_drifted(utc_now(), done[-1].end, cfg.drift_tolerance_s):
            delta = (utc_now() - done[-1].end).total_seconds()
            return f"décalage de {delta:.0f} s entre l'horloge et le flux", promoted

        if stall.update(_run_bytes(run_dir), time.monotonic()):
            return f"flux figé depuis {cfg.stall_timeout_s:.0f} s", promoted
    return f"ffmpeg s'est arrêté (code {proc.returncode})", promoted


def _capture_once(cfg: Config) -> bool:
    """Un run de ffmpeg, de la résolution du flux à la promotion du dernier segment. Vrai si productif."""
    try:
        stream = resolve_stream(cfg.video_id, cfg.format_selector)
    except StreamError as e:
        log.error("Impossible de résoudre le flux %s : %s", cfg.video_id, e)
        return False

    run_dir = cfg.work_dir / format_stamp(utc_now())
    run_dir.mkdir(parents=True)
    log.info("Capture démarrée (run %s)", run_dir.name)
    promoted = 0
    reason = "arrêt demandé"
    with (cfg.logs_dir / "ffmpeg.log").open("ab") as ffmpeg_log:
        ffmpeg_log.write(f"=== run {run_dir.name} ===\n".encode())
        ffmpeg_log.flush()
        proc = subprocess.Popen(
            build_ffmpeg_cmd(stream, run_dir, cfg.segment_seconds),
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=ffmpeg_log,
        )
        try:
            reason, promoted = _watch(proc, run_dir, cfg)
        finally:
            stop_ffmpeg(proc)
            last = finalize_run(run_dir, cfg.audio_dir, cfg.coverage_csv, probe_duration)
            for p in last:
                log.info("Segment terminé : %s (%s, %.0f s)", p.path.name, to_local_iso(p.start, cfg.timezone),
                         (p.end - p.start).total_seconds())
            promoted += len(last)
            log.warning("Capture interrompue : %s ; %d segment(s) dans ce run", reason, promoted)
    return promoted > 0


def run_capture(cfg: Config) -> None:
    """Tourne jusqu'à Ctrl+C (KeyboardInterrupt, propagé à l'appelant après un arrêt propre)."""
    for d in (cfg.work_dir, cfg.audio_dir, cfg.logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    backoff = BASE_BACKOFF_S
    while True:
        try:
            # À chaque tour : runs abandonnés au démarrage, ou laissés par un fichier verrouillé.
            recovered = recover_runs(cfg.work_dir, cfg.audio_dir, cfg.coverage_csv, probe_duration)
            if recovered:
                log.info("%d segment(s) récupéré(s) d'un run précédent interrompu", len(recovered))
            productive = _capture_once(cfg)
        except Exception:
            log.exception("Erreur inattendue pendant la capture")
            productive = False
        backoff = next_backoff(backoff, productive)
        log.info("Nouvelle tentative dans %.0f s", backoff)
        time.sleep(backoff)
