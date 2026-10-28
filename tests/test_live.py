from cnews_tts.live import plan_chunk

SR = 16000


def seg(a, b):
    return {"start": a, "end": b}


def test_waits_on_short_buffer():
    assert plan_chunk(SR // 2, [seg(0, 4800)]) is None


def test_waits_while_speech_runs_to_the_end():
    assert plan_chunk(48000, [seg(3200, 47200)]) is None


def test_cuts_in_the_pause_after_speech():
    assert plan_chunk(48000, [seg(3200, 38400)]) == (41600, True)


def test_forced_cut_in_the_largest_gap_when_too_long():
    assert plan_chunk(128000, [seg(0, 48000), seg(52800, 80000), seg(81600, 128000)]) == (50400, True)


def test_forced_cut_at_the_end_without_any_gap():
    assert plan_chunk(128000, [seg(0, 128000)]) == (128000, True)


def test_drops_long_silence_but_keeps_the_last_half_second():
    assert plan_chunk(48000, []) == (40000, False)
