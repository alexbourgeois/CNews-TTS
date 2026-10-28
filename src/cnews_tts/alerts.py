"""Alerte sonore quand un mot-clé est prononcé."""

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


def play_alert() -> None:
    try:
        import winsound

        winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        print("\a", end="", flush=True)
