"""Transcription en direct : le son de ffmpeg arrive en continu, découpé en mémoire aux pauses de parole.

Quelques secondes de retard sur le flux, pour l'affichage et les alertes. N'écrit rien dans data/ :
le corpus d'analyse reste produit par capture + transcribe.
"""

import logging
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from cnews_tts.alerts import find_keywords, play_alert
from cnews_tts.condense import Condenser
from cnews_tts.config import Config
from cnews_tts.hallucinations import is_hallucination
from cnews_tts.media import build_live_cmd, stop_ffmpeg
from cnews_tts.sentiment import colorize, load_lexicon
from cnews_tts.speech import Speaker, ensure_voice
from cnews_tts.stream import StreamError, resolve_stream
from cnews_tts.transcribe import load_model

log = logging.getLogger(__name__)

SR = 16000
BLOCK_BYTES = SR // 10 * 2  # 100 ms de PCM 16 bits mono
MIN_CHUNK_S = 1.0
MIN_SILENCE_S = 0.3
MAX_CHUNK_S = 5.0
CUT_PAD_S = 0.2
STALL_TIMEOUT_S = 30


def plan_chunk(n: int, speech: list[dict], sr: int = SR) -> tuple[int, bool] | None:
    """Où couper un tampon de n échantillons : (coupure, à transcrire ?), ou None pour attendre la suite.

    speech : zones de parole détectées par le VAD (indices d'échantillons « start » / « end »).
    """
    if n < MIN_CHUNK_S * sr:
        return None
    if not speech:
        return (n - sr // 2, False) if n > 2 * sr else None
    last_end = speech[-1]["end"]
    if n - last_end >= MIN_SILENCE_S * sr:
        return min(n, last_end + int(CUT_PAD_S * sr)), True
    if n < MAX_CHUNK_S * sr:
        return None
    # Trop long sans pause nette : couper au milieu du plus grand blanc entre deux zones de parole.
    gaps = [(b["start"] - a["end"], (a["end"] + b["start"]) // 2) for a, b in zip(speech, speech[1:])]
    return (max(gaps)[1] if gaps else n), True


def _read_blocks(pipe, q: queue.Queue) -> None:
    while block := pipe.read(BLOCK_BYTES):
        q.put(block)
    q.put(None)


def _transcribe_stream(proc: subprocess.Popen, model, cfg: Config, keywords: tuple[str, ...], speaker=None,
                       condense=None, lexicon: dict[str, float] | None = None, sink: queue.Queue | None = None,
                       stop: threading.Event | None = None) -> None:
    stop = stop or threading.Event()
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    vad = VadOptions(min_silence_duration_ms=200, speech_pad_ms=100)
    tz = ZoneInfo(cfg.timezone)
    q: queue.Queue = queue.Queue()
    threading.Thread(target=_read_blocks, args=(proc.stdout, q), daemon=True).start()
    buf = np.zeros(0, dtype=np.float32)
    prompt = ""
    while not stop.is_set():
        blocks = [q.get(timeout=STALL_TIMEOUT_S)]
        while not q.empty():
            blocks.append(q.get_nowait())
        if None in blocks:
            return
        pcm = np.frombuffer(b"".join(blocks), dtype=np.int16).astype(np.float32) / 32768
        buf = np.concatenate([buf, pcm])

        plan = plan_chunk(len(buf), get_speech_timestamps(buf, vad))
        if plan is None:
            continue
        cut, has_speech = plan
        chunk, buf = buf[:cut], buf[cut:]
        if not has_speech:
            continue

        start = datetime.now(tz) - timedelta(seconds=(len(chunk) + len(buf)) / SR)
        segments, _ = model.transcribe(chunk, language=cfg.language, vad_filter=False,
                                       condition_on_previous_text=False, initial_prompt=prompt or None,
                                       without_timestamps=True)
        text = " ".join(s.text.strip() for s in segments
                        if not is_hallucination(s.text, cfg.hallucination_blacklist)).strip()
        if not text:
            continue
        prompt = text[-200:]
        shown = condense(text) if condense else text
        hits = find_keywords(text, keywords)  # sur la phrase entière : « titre de séjour » garde son « de »
        if hits:
            play_alert(cfg.alert_sound)
            log.info("alerte : %s", ", ".join(hits))
        elif not shown:
            continue
        painted = colorize(shown, lexicon) if lexicon else shown
        print(f"{start:%H:%M:%S}  {painted}" + (f"   <<< {', '.join(hits)}" if hits else ""), flush=True)
        if speaker and shown:
            speaker.say(shown)  # le texte seul, sans l'heure ni le marqueur d'alerte
        if sink is not None and shown:
            sink.put(shown)
        log.info("retard %.1f s — %s", (datetime.now(tz) - start).total_seconds(), text[:80])


def run_live(cfg: Config, keywords: tuple[str, ...] = (), speak: bool = False, condense: bool = False,
             color: bool = False, window: bool = False, game: bool = False) -> None:
    """Tourne jusqu'à Ctrl+C (ou la fermeture de la fenêtre) ; se reconnecte si le flux coupe."""
    sys.stdout.reconfigure(errors="replace")
    print(f"Chargement du modèle {cfg.live_model}…", flush=True)
    model = load_model(cfg, cfg.live_model)
    speaker = None
    if speak:
        print(f"Chargement de la voix {cfg.speech_voice}…", flush=True)
        speaker = Speaker(ensure_voice(cfg.voices_dir, cfg.speech_voice))
    condenser = Condenser() if condense else None
    lexicon = None
    if color:
        import colorama

        colorama.just_fix_windows_console()  # couleurs aussi dans l'ancienne console Windows
        lexicon = load_lexicon()
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    args = (model, cfg, keywords, speaker, condenser, lexicon)
    if not window:
        _live_loop(*args, None, threading.Event())
        return

    from cnews_tts.visual import run_window

    party = server = None
    banner = ""
    if game:
        from cnews_tts.game import Game, lan_address, start_server

        party = Game(None, load_lexicon())
        try:
            server = start_server(party, "0.0.0.0", cfg.game_port)
        except OSError as e:
            raise SystemExit(f"Port {cfg.game_port} indisponible ({e}) : changez [game] port dans config.toml")
        banner = f"Rejoindre : http://{lan_address()}:{cfg.game_port}"
        print(f"— jeu ouvert. {banner} (même Wi-Fi / réseau que ce PC) —", flush=True)

    words, stop = queue.Queue(), threading.Event()
    worker = threading.Thread(target=_live_loop, args=(*args, words, stop), daemon=True)
    worker.start()
    try:
        run_window(words, load_lexicon(), cfg.window_lifetime_s, stop, game=party, banner=banner)  # fil principal
    finally:
        stop.set()
        if server:
            server.shutdown()
        worker.join(timeout=20)


def _live_loop(model, cfg: Config, keywords, speaker, condenser, lexicon, sink: queue.Queue | None,
               stop: threading.Event) -> None:
    try:
        while not stop.is_set():
            try:
                stream = resolve_stream(cfg.video_id, cfg.format_selector)
            except StreamError as e:
                log.error("Impossible de résoudre le flux : %s", e)
                print("Flux indisponible, nouvel essai dans 10 s…", flush=True)
                stop.wait(10)
                continue
            print("— connecté au direct —", flush=True)
            with (cfg.logs_dir / "ffmpeg-live.log").open("ab") as ffmpeg_log:
                proc = subprocess.Popen(build_live_cmd(stream, SR), stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=ffmpeg_log)
                try:
                    _transcribe_stream(proc, model, cfg, keywords, speaker, condenser, lexicon, sink, stop)
                except queue.Empty:
                    log.warning("Plus de son depuis %d s", STALL_TIMEOUT_S)
                finally:
                    stop_ffmpeg(proc)
            if not stop.is_set():
                print("— flux interrompu, reconnexion… —", flush=True)
                stop.wait(5)
    except Exception:
        log.exception("Erreur dans la transcription du direct")
        raise
    finally:
        stop.set()  # avec la fenêtre : elle se ferme aussi
