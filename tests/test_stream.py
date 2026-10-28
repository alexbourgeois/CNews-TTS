import pytest

from cnews_tts.stream import StreamError, StreamInfo, stream_info_from_ytdlp


def test_stream_info_from_ytdlp():
    s = stream_info_from_ytdlp({"url": "https://x/live.m3u8?sec=abc", "http_headers": {"Referer": "https://www.dailymotion.com/"}})
    assert s == StreamInfo("https://x/live.m3u8?sec=abc", {"Referer": "https://www.dailymotion.com/"})


def test_stream_info_without_url_raises():
    with pytest.raises(StreamError):
        stream_info_from_ytdlp({"formats": []})
