"""Lecture à voix haute du direct, avec une voix neuronale française (Piper, hors ligne)."""

import logging
import os
import queue
import shutil
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

LENGTH_SCALE = 0.9  # < 1 : débit plus rapide (un plateau TV parle vite), > 1 : plus lent
MAX_BACKLOG = 2  # au-delà, les phrases les plus anciennes sont sautées pour rester au direct


def enqueue_latest(q: queue.Queue, text: str, max_backlog: int = MAX_BACKLOG) -> None:
    while q.qsize() >= max_backlog:
        try:
            q.get_nowait()
        except queue.Empty:
            break
    q.put(text)


def _piper_download(name: str, target: Path) -> None:
    from piper.download_voices import download_voice

    download_voice(name, target)


def ensure_voice(voices_dir: Path, name: str, download=_piper_download, attempts: int = 5,
                 wait_s: float = 3.0) -> Path:
    """Chemin du modèle de voix, téléchargé au premier usage (~60 Mo).

    Le téléchargement se fait dans un dossier à part : une coupure ne laisse jamais une voix incomplète.
    """
    model = voices_dir / f"{name}.onnx"
    config = voices_dir / f"{name}.onnx.json"
    if model.is_file() and config.is_file():
        return model
    tmp = voices_dir / "telechargement"
    for attempt in range(1, attempts + 1):
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        try:
            download(name, tmp)
            break
        except Exception as e:
            if attempt == attempts:
                raise
            log.warning("Téléchargement de la voix %s interrompu (%s), nouvel essai", name, e)
            time.sleep(wait_s)
    os.replace(tmp / config.name, config)
    os.replace(tmp / model.name, model)
    shutil.rmtree(tmp, ignore_errors=True)
    return model


class Speaker:
    """Lit les phrases dans un fil séparé, pour ne pas retarder la transcription."""

    def __init__(self, model_path: Path):
        from piper import PiperVoice

        self._voice = PiperVoice.load(str(model_path))
        self._q: queue.Queue = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def say(self, text: str) -> None:
        enqueue_latest(self._q, text)

    def _run(self) -> None:
        while True:
            try:
                self._speak_forever()
            except Exception:  # sortie audio débranchée (enceinte Bluetooth…) : on rouvre
                log.exception("Lecture à voix haute interrompue, reprise dans 5 s")
                time.sleep(5)

    def _speak_forever(self) -> None:
        import sounddevice as sd
        from piper import SynthesisConfig

        syn = SynthesisConfig(length_scale=LENGTH_SCALE)
        with sd.RawOutputStream(samplerate=self._voice.config.sample_rate, channels=1, dtype="int16") as out:
            while True:
                for chunk in self._voice.synthesize(self._q.get(), syn):
                    out.write(chunk.audio_int16_bytes)
