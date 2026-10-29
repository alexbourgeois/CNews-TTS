import queue

import pytest

from cnews_tts.speech import enqueue_latest, ensure_voice


def test_enqueue_latest_drops_oldest_to_stay_live():
    q = queue.Queue()
    for text in ("a", "b", "c"):
        enqueue_latest(q, text, max_backlog=2)
    assert [q.get_nowait() for _ in range(q.qsize())] == ["b", "c"]


def _fake_download(fail_times):
    calls = []

    def download(name, target):
        calls.append(name)
        (target / f"{name}.onnx").write_bytes(b"partiel")
        if len(calls) <= fail_times:
            raise ConnectionResetError("connexion fermée par l'hôte distant")
        (target / f"{name}.onnx").write_bytes(b"modele")
        (target / f"{name}.onnx.json").write_text("{}")

    return download, calls


def test_ensure_voice_retries_and_downloads_once(tmp_path):
    download, calls = _fake_download(fail_times=1)
    model = ensure_voice(tmp_path, "fr_FR-x-medium", download=download, wait_s=0)
    assert model == tmp_path / "fr_FR-x-medium.onnx" and model.read_bytes() == b"modele"
    assert ensure_voice(tmp_path, "fr_FR-x-medium", download=download, wait_s=0) == model
    assert len(calls) == 2


def test_ensure_voice_never_leaves_a_partial_model(tmp_path):
    download, _ = _fake_download(fail_times=99)
    with pytest.raises(ConnectionResetError):
        ensure_voice(tmp_path, "fr_FR-x-medium", download=download, attempts=2, wait_s=0)
    assert not list(tmp_path.glob("*.onnx"))
