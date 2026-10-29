"""Résolution de l'URL HLS d'un direct (Dailymotion, france.tv…) avec yt-dlp."""

from dataclasses import dataclass

import yt_dlp


class StreamError(Exception):
    pass


@dataclass(frozen=True)
class StreamInfo:
    url: str
    headers: dict[str, str]


def stream_info_from_ytdlp(info: dict) -> StreamInfo:
    if not info.get("url"):
        raise StreamError("yt-dlp n'a renvoyé aucune URL de flux")
    return StreamInfo(info["url"], dict(info.get("http_headers", {})))


def resolve_stream(page_url: str, format_selector: str) -> StreamInfo:
    opts = {"format": format_selector, "quiet": True, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(page_url, download=False)
    except Exception as e:
        raise StreamError(str(e)) from e
    return stream_info_from_ytdlp(info)
