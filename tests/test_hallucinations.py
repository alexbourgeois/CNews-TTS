import pytest

from cnews_tts.hallucinations import is_hallucination

BL = ("Sous-titrage ST' 501", "Sous-titres réalisés par la communauté d'Amara.org",
      "Sous-titrage Société Radio-Canada", "Merci d'avoir regardé cette vidéo")


@pytest.mark.parametrize("text", [" Sous-titrage ST' 501", "Sous-titrage ST’ 501.",
                                  "SOUS-TITRES RÉALISÉS PAR LA COMMUNAUTÉ D'AMARA.ORG",
                                  "Merci d'avoir regardé cette vidéo !", " ...", ""])
def test_hallucinations_dropped(text):
    assert is_hallucination(text, BL)


@pytest.mark.parametrize("text", ["Le gouvernement a présenté son budget.", "Merci d'avoir été avec nous ce soir."])
def test_real_speech_kept(text):
    assert not is_hallucination(text, BL)
