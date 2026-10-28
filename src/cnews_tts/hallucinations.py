"""Phrases que Whisper invente sur les silences et la musique."""

import re
import unicodedata
from typing import Iterable


def normalize(text: str) -> str:
    """Minuscules, sans accents ni ponctuation, espaces simples."""
    text = unicodedata.normalize("NFKD", text.replace("’", "'"))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[\W_]+", " ", text).strip()


def is_hallucination(text: str, blacklist: Iterable[str]) -> bool:
    """Vrai si le texte est vide une fois normalisé, ou contient (mots entiers) une phrase de la liste noire."""
    norm = normalize(text)
    if not norm:
        return True
    padded = f" {norm} "
    return any(f" {normalize(entry)} " in padded for entry in blacklist)
