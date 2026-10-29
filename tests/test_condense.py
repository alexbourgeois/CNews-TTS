import pytest

from cnews_tts.condense import Condenser


@pytest.fixture(scope="module")
def condense():
    return Condenser()


def test_keeps_nouns_infinitives_adjectives(condense):
    text = "Le gouvernement a présenté ce matin un nouveau projet de loi sur l'immigration clandestine."
    assert condense(text) == "gouvernement présenter matin nouveau projet loi immigration clandestine"


def test_keeps_numbers_and_proper_names(condense):
    assert condense("Bruno Retailleau veut expulser 3000 clandestins.") == \
        "Bruno Retailleau vouloir expulser 3000 clandestins"


def test_nothing_left(condense):
    assert condense("Et alors, vous, vous y êtes ?") == ""


def test_keeps_hyphenated_words_whole(condense):
    assert condense("Les centres-villes se vident le week-end.") == "centres-villes vider week-end"
