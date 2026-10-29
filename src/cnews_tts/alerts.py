"""Alerte sonore quand un mot-clé est prononcé."""

from pathlib import Path
from typing import Iterable

from cnews_tts.hallucinations import normalize


def find_keywords(text: str, keywords: Iterable[str]) -> list[str]:
    """Mots-clés présents, sans accents ni majuscules : un mot seul couvre tous les mots qui commencent
    par lui (« immigr » → immigrés), une expression doit apparaître telle quelle."""
    words = normalize(text).split()
    padded = f" {' '.join(words)} "
    hits = []
    for kw in keywords:
        n = normalize(kw)
        if " " in n:
            found = f" {n} " in padded
        else:
            found = any(w.startswith(n) for w in words)
        if found:
            hits.append(kw)
    return hits


def play_alert(sound: Path | None = None) -> None:
    """Joue le .wav donné, ou le son d'alerte de Windows ; sans attendre la fin du son."""
    try:
        import winsound

        if sound:
            winsound.PlaySound(str(sound), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        else:
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        print("\a", end="", flush=True)
