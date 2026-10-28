"""Lecture à voix haute du direct, avec la voix française de Windows (SAPI, hors ligne)."""

import queue
import threading

RATE = 2  # de -10 (lent) à 10 (rapide) : un plateau TV parle vite
MAX_BACKLOG = 2  # au-delà, les phrases les plus anciennes sont sautées pour rester au direct


def choose_voice(descriptions: list[str]) -> int | None:
    for i, desc in enumerate(descriptions):
        if "french" in desc.lower() or "français" in desc.lower():
            return i
    return None


def enqueue_latest(q: queue.Queue, text: str, max_backlog: int = MAX_BACKLOG) -> None:
    while q.qsize() >= max_backlog:
        try:
            q.get_nowait()
        except queue.Empty:
            break
    q.put(text)


class Speaker:
    """Lit les phrases dans un fil séparé, pour ne pas retarder la transcription."""

    def __init__(self):
        self._q: queue.Queue = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def say(self, text: str) -> None:
        enqueue_latest(self._q, text)

    def _run(self) -> None:
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        voice = comtypes.client.CreateObject("SAPI.SpVoice")
        tokens = voice.GetVoices()
        index = choose_voice([tokens.Item(i).GetDescription() for i in range(tokens.Count)])
        if index is not None:
            voice.Voice = tokens.Item(index)
        voice.Rate = RATE
        while True:
            voice.Speak(self._q.get())
