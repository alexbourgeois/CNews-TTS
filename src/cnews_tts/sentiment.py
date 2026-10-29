"""Couleur des mots selon leur charge positive ou négative (lexique VADER français, notes de -4 à +4)."""

import re
from functools import lru_cache
from pathlib import Path

NEUTRAL_BELOW = 0.5  # |note| plus petite : mot neutre, couleur normale du terminal
STRONG_AT = 3.0  # |note| à partir de laquelle la couleur est la plus vive
GREY = (190, 190, 190)
RED = (255, 30, 30)
GREEN = (30, 220, 60)
WORD = re.compile(r"\w+")


@lru_cache(maxsize=1)
def load_lexicon() -> dict[str, float]:
    import vaderSentiment_fr

    lexicon = {}
    path = Path(vaderSentiment_fr.__file__).parent / "fr_lexicon.txt"
    for line in path.read_text(encoding="utf-8").splitlines():  # « mot->note »
        word, _, score = line.rpartition("->")
        try:
            lexicon[word] = float(score)
        except ValueError:
            continue
    return lexicon


def word_rgb(score: float) -> tuple[int, int, int] | None:
    """Du gris teinté (mot faiblement chargé) au rouge ou vert vif (fortement chargé)."""
    if abs(score) < NEUTRAL_BELOW:
        return None
    t = 0.35 + 0.65 * min((abs(score) - NEUTRAL_BELOW) / (STRONG_AT - NEUTRAL_BELOW), 1.0)
    target = RED if score < 0 else GREEN
    return tuple(round(g + (c - g) * t) for g, c in zip(GREY, target))


def colorize(text: str, lexicon: dict[str, float]) -> str:
    def paint(m: re.Match) -> str:
        score = lexicon.get(m.group().lower())
        rgb = word_rgb(score) if score is not None else None
        return f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m{m.group()}\x1b[0m" if rgb else m.group()

    return WORD.sub(paint, text)
