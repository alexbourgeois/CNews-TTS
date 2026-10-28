import subprocess

from cnews_tts.media import build_ffmpeg_cmd, build_live_cmd, probe_duration, stop_ffmpeg
from cnews_tts.stream import StreamInfo


def test_build_ffmpeg_cmd(tmp_path):
    cmd = build_ffmpeg_cmd(StreamInfo("https://x/live.m3u8", {"User-Agent": "UA"}), tmp_path, 600)

    def arg(flag):
        return cmd[cmd.index(flag) + 1]

    assert cmd[0] == "ffmpeg"
    assert arg("-i") == "https://x/live.m3u8"
    assert arg("-headers") == "User-Agent: UA\r\n"
    assert cmd.index("-headers") < cmd.index("-i") and cmd.index("-rw_timeout") < cmd.index("-i")
    for flag, val in [("-rw_timeout", "30000000"), ("-map", "0:a:0"), ("-c:a", "copy"), ("-f", "segment"),
                      ("-segment_format", "adts"), ("-segment_time", "600"), ("-segment_atclocktime", "1"),
                      ("-segment_list_type", "csv")]:
        assert arg(flag) == val
    assert "-vn" in cmd
    assert arg("-segment_list") == str(tmp_path / "segments.csv")
    assert cmd[-1] == str(tmp_path / "seg_%05d.aac")


def test_build_ffmpeg_cmd_without_headers(tmp_path):
    assert "-headers" not in build_ffmpeg_cmd(StreamInfo("u", {}), tmp_path, 600)


def test_probe_duration_on_generated_aac(tmp_path):
    f = tmp_path / "x.aac"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=d=3", "-c:a", "aac", str(f)], check=True)
    assert abs(probe_duration(f) - 3.0) < 0.3


def test_probe_duration_unreadable(tmp_path):
    (tmp_path / "bad.aac").write_bytes(b"not audio")
    assert probe_duration(tmp_path / "bad.aac") == 0.0


def test_stop_ffmpeg_is_graceful():
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine", "-f", "null", "-"], stdin=subprocess.PIPE)
    stop_ffmpeg(p, timeout_s=10)
    assert p.returncode == 0


def test_build_live_cmd_streams_pcm_from_the_live_edge():
    cmd = build_live_cmd(StreamInfo("https://x/live.m3u8", {"User-Agent": "UA"}))

    def arg(flag):
        return cmd[cmd.index(flag) + 1]

    assert cmd.index("-headers") < cmd.index("-i") and cmd.index("-live_start_index") < cmd.index("-i")
    assert arg("-live_start_index") == "-1" and arg("-i") == "https://x/live.m3u8"
    assert (arg("-ac"), arg("-ar"), arg("-f")) == ("1", "16000", "s16le")
    assert cmd[-1] == "pipe:1"
