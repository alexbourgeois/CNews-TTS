from datetime import datetime, timezone

from cnews_tts.capture import StallDetector, is_drifted, loop_was_suspended, next_backoff

UTC = timezone.utc


def t(h, m, s=0):
    return datetime(2026, 10, 28, h, m, s, tzinfo=UTC)


def test_next_backoff():
    assert next_backoff(80, productive=True) == 5
    assert next_backoff(5, productive=False) == 10
    assert next_backoff(200, productive=False) == 300


def test_is_drifted():
    assert not is_drifted(t(18, 10, 30), t(18, 10), 120)
    assert is_drifted(t(18, 10, 30), t(17, 0), 120)  # horloge partie devant (veille)
    assert is_drifted(t(17, 0), t(18, 10), 120)


def test_loop_was_suspended():
    assert not loop_was_suspended(5.4, expected_s=5)
    assert loop_was_suspended(3600, expected_s=5)


def test_stall_detector():
    d = StallDetector(timeout_s=120, now=0)
    assert not d.update(100, now=10)
    assert not d.update(100, now=129)
    assert d.update(100, now=131)
    assert not d.update(200, now=140)
