from cnews_tts.alerts import find_keywords

KW = ("immigr", "OQTF", "demandeur d'asile", "étranger")


def test_finds_word_stems_and_phrases():
    assert find_keywords("Les immigrés et les OQTF", KW) == ["immigr", "OQTF"]
    assert find_keywords("Un demandeur d’asile débouté", KW) == ["demandeur d'asile"]
    assert find_keywords("Des ÉTRANGÈRES en situation irrégulière", KW) == ["étranger"]


def test_ignores_unrelated_text():
    assert find_keywords("Le PSG a gagné ce soir, il faut qu'on choisisse", KW) == []
