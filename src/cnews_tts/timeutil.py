"""Horodatages : noms de fichiers en UTC, sorties en heure locale avec décalage."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

STAMP_FORMAT = "%Y%m%dT%H%M%SZ"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_stamp(dt: datetime) -> str:
    """20261028T180000Z — secondes tronquées."""
    return dt.astimezone(timezone.utc).strftime(STAMP_FORMAT)


def parse_stamp(s: str) -> datetime:
    """Inverse de format_stamp ; ValueError si le texte n'a pas ce format."""
    return datetime.strptime(s, STAMP_FORMAT).replace(tzinfo=timezone.utc)


def to_local_iso(dt: datetime, tz: str) -> str:
    """2026-10-28T19:00:03.120+01:00"""
    return dt.astimezone(ZoneInfo(tz)).isoformat(timespec="milliseconds")


def local_day(dt: datetime, tz: str) -> str:
    return dt.astimezone(ZoneInfo(tz)).date().isoformat()
