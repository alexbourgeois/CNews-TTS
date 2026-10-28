"""Appels à ffmpeg / ffprobe."""

import subprocess
from pathlib import Path

from cnews_tts.segments import SEGMENT_LIST, SEGMENT_PATTERN
from cnews_tts.stream import StreamInfo

RW_TIMEOUT_US = 30_000_000  # ffmpeg abandonne une lecture réseau bloquée au bout de 30 s


def build_ffmpeg_cmd(stream: StreamInfo, run_dir: Path, segment_seconds: int) -> list[str]:
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "warning", "-rw_timeout", str(RW_TIMEOUT_US)]
    if stream.headers:
        cmd += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in stream.headers.items())]
    cmd += [
        "-i", stream.url,
        "-map", "0:a:0", "-vn", "-c:a", "copy",
        "-f", "segment", "-segment_format", "adts",
        "-segment_time", str(segment_seconds), "-segment_atclocktime", "1",
        "-segment_list", str(run_dir / SEGMENT_LIST), "-segment_list_type", "csv",
        str(run_dir / SEGMENT_PATTERN),
    ]
    return cmd


def probe_duration(path: Path) -> float:
    """Durée en secondes d'un fichier audio, 0.0 s'il est illisible."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def stop_ffmpeg(proc: subprocess.Popen, timeout_s: float = 15.0) -> None:
    """Arrêt propre (touche q : ffmpeg termine le segment et la liste), sinon arrêt forcé."""
    if proc.poll() is not None:
        return
    try:
        proc.stdin.write(b"q")
        proc.stdin.flush()
    except (OSError, AttributeError):
        pass
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
