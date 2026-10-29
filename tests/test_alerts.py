from cnews_tts.alerts import find_keywords

KW = ("immigr", "OQTF", "demandeur d'asile", "étranger")


def test_finds_word_stems_and_phrases():
    assert find_keywords("Les immigrés et les OQTF", KW) == ["immigr", "OQTF"]
    assert find_keywords("Un demandeur d’asile débouté", KW) == ["demandeur d'asile"]
    assert find_keywords("Des ÉTRANGÈRES en situation irrégulière", KW) == ["étranger"]


def test_ignores_unrelated_text():
    assert find_keywords("Le PSG a gagné ce soir, il faut qu'on choisisse", KW) == []


def test_play_alert_plays_the_wav_file(tmp_path, monkeypatch, capsys):
    import wave
    import winsound

    from cnews_tts.alerts import play_alert

    wav = tmp_path / "alerte.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(8000)
        w.writeframes(b"\0\0" * 800)
    calls = []
    real = winsound.PlaySound
    monkeypatch.setattr(winsound, "PlaySound", lambda sound, flags: (calls.append((sound, flags)), real(sound, flags)))
    play_alert(wav)
    assert calls == [(str(wav), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)]
    assert capsys.readouterr().out == ""  # pas de repli sur le bip
