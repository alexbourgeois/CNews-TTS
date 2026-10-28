"""Ligne de commande : python -m cnews_tts [--config config.toml] <commande>."""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from cnews_tts.config import load_config
from cnews_tts.coverage import coverage_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cnews_tts", description="Capture et transcription du direct CNews.")
    parser.add_argument("--config", type=Path, default=Path("config.toml"), help="fichier de réglages")
    sub = parser.add_subparsers(dest="command", required=True)

    p_cov = sub.add_parser("coverage", help="afficher les périodes enregistrées et les trous")
    p_cov.add_argument("--since", help="date de début AAAA-MM-JJ (heure locale)")

    args = parser.parse_args(argv)
    cfg = load_config(args.config)

    if args.command == "coverage":
        since = None
        if args.since:
            since = datetime.fromisoformat(args.since).replace(tzinfo=ZoneInfo(cfg.timezone))
        print(coverage_report(cfg.coverage_csv, cfg.timezone, since))
    return 0


if __name__ == "__main__":
    sys.exit(main())
