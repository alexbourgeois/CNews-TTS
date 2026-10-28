"""Journal de couverture : intervalles réellement enregistrés, et trous entre eux."""

import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

FIELDS = ["start_utc", "end_utc", "audio"]

Interval = tuple[datetime, datetime]


def append_interval(coverage_csv: Path, start: datetime, end: datetime, audio_name: str) -> None:
    coverage_csv.parent.mkdir(parents=True, exist_ok=True)
    is_new = not coverage_csv.exists()
    with coverage_csv.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(FIELDS)
        writer.writerow([start.isoformat(), end.isoformat(), audio_name])


def read_intervals(coverage_csv: Path) -> list[Interval]:
    if not coverage_csv.exists():
        return []
    with coverage_csv.open(newline="", encoding="utf-8") as f:
        return [
            (datetime.fromisoformat(row["start_utc"]), datetime.fromisoformat(row["end_utc"]))
            for row in csv.DictReader(f)
        ]


def _merge(intervals: list[Interval], tolerance_s: float) -> list[Interval]:
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if merged and (start - merged[-1][1]).total_seconds() <= tolerance_s:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def find_gaps(intervals: list[Interval], tolerance_s: float = 5.0) -> list[Interval]:
    merged = _merge(intervals, tolerance_s)
    return [(a[1], b[0]) for a, b in zip(merged, merged[1:])]


def _fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s} s"
    return f"{s} s"


def coverage_report(coverage_csv: Path, tz: str, since: datetime | None = None, tolerance_s: float = 5.0) -> str:
    intervals = read_intervals(coverage_csv)
    if since is not None:
        intervals = [(max(a, since), b) for a, b in intervals if b > since]
    if not intervals:
        return "Aucune donnée de couverture."

    zone = ZoneInfo(tz)
    local = lambda dt: dt.astimezone(zone)
    merged = _merge(intervals, tolerance_s)
    first, last = merged[0][0], merged[-1][1]
    total = (last - first).total_seconds()
    covered = sum((b - a).total_seconds() for a, b in merged)
    pct = f"{100 * covered / total:.1f}".replace(".", ",") if total else "100,0"
    gaps = find_gaps(intervals, tolerance_s)

    lines = [
        f"Couverture du {local(first):%Y-%m-%d %H:%M:%S} au {local(last):%Y-%m-%d %H:%M:%S} (heure de {tz})",
        f"Enregistré : {_fmt_duration(covered)} sur {_fmt_duration(total)} ({pct} %)",
        f"Trous ({len(gaps)}) :" if gaps else "Aucun trou.",
    ]
    for a, b in gaps:
        a_l, b_l = local(a), local(b)
        end = f"{b_l:%H:%M:%S}" if a_l.date() == b_l.date() else f"{b_l:%Y-%m-%d %H:%M:%S}"
        lines.append(f"  {a_l:%Y-%m-%d} de {a_l:%H:%M:%S} à {end}  ({_fmt_duration((b - a).total_seconds())})")
    return "\n".join(lines)
