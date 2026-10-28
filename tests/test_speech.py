import queue

from cnews_tts.speech import choose_voice, enqueue_latest


def test_choose_voice_prefers_french():
    voices = ["Microsoft Zira Desktop - English (United States)", "Microsoft Hortense Desktop - French"]
    assert choose_voice(voices) == 1
    assert choose_voice(voices[:1]) is None


def test_enqueue_latest_drops_oldest_to_stay_live():
    q = queue.Queue()
    for text in ("a", "b", "c"):
        enqueue_latest(q, text, max_backlog=2)
    assert [q.get_nowait() for _ in range(q.qsize())] == ["b", "c"]
