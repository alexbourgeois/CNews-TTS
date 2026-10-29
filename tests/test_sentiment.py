import re

from cnews_tts.sentiment import colorize, load_lexicon, word_rgb

LEX = {"guerre": -2.9, "paix": 2.5, "gris": 0.2}


def test_lexicon_scores_news_words():
    lex = load_lexicon()
    assert lex["guerre"] < 0 < lex["victoire"]
    assert "gouvernement" not in lex


def test_stronger_words_get_stronger_colors():
    red_weak, red_strong = word_rgb(-1.0), word_rgb(-3.5)
    assert red_strong[0] >= red_weak[0] and red_strong[1] < red_weak[1]  # plus rouge, moins de vert
    green_weak, green_strong = word_rgb(1.0), word_rgb(3.0)
    assert green_strong[1] >= green_weak[1] and green_strong[0] < green_weak[0]
    assert word_rgb(0.2) is None  # quasi neutre : couleur normale


def test_colorize_only_touches_charged_words():
    out = colorize("La Guerre et la paix, gris gouvernement", LEX)
    assert re.sub(r"\x1b\[[0-9;]*m", "", out) == "La Guerre et la paix, gris gouvernement"
    colored = re.findall(r"\x1b\[38;2;(\d+);(\d+);(\d+)m(\w+)\x1b\[0m", out)
    assert [w for *_, w in colored] == ["Guerre", "paix"]
    (r1, g1, _, _), (r2, g2, _, _) = colored
    assert int(r1) > int(g1) and int(g2) > int(r2)
