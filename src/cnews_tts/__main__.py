"""Ligne de commande : python -m cnews_tts [--config config.toml] <commande>."""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from cnews_tts.config import load_config
from cnews_tts.coverage import coverage_report

log = logging.getLogger("cnews_tts")


def _setup_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    log.setLevel(logging.INFO)
    for handler in (logging.StreamHandler(), logging.FileHandler(log_file, encoding="utf-8")):
        handler.setFormatter(fmt)
        log.addHandler(handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cnews_tts", description="Capture et transcription du direct CNews.")
    parser.add_argument("--config", type=Path, default=Path("config.toml"), help="fichier de réglages")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("capture", help="enregistrer le direct en continu (Ctrl+C pour arrêter)")
    p_tr = sub.add_parser("transcribe", help="transcrire les fichiers audio en attente, puis s'arrêter")
    p_tr.add_argument("--watch", action="store_true",
                      help="rester ouvert et transcrire chaque fichier dès qu'il est terminé (Ctrl+C pour arrêter)")

    p_follow = sub.add_parser("follow", help="afficher le texte au fur et à mesure (Ctrl+C pour arrêter)")
    p_follow.add_argument("--lines", type=int, default=10, help="nombre de phrases déjà transcrites à afficher")
    p_follow.add_argument("--alert", action="store_true",
                          help="jouer un son quand un mot de la liste [alert] de config.toml est prononcé")

    p_cov = sub.add_parser("coverage", help="afficher les périodes enregistrées et les trous")
    p_cov.add_argument("--since", help="date de début AAAA-MM-JJ (heure locale)")

    args = parser.parse_args(argv)
    cfg = load_config(args.config)

    if args.command == "capture":
        from cnews_tts.capture import run_capture

        _setup_logging(cfg.logs_dir / "capture.log")
        try:
            run_capture(cfg)
        except KeyboardInterrupt:
            log.info("Arrêt demandé : capture terminée proprement.")
        except Exception:
            log.exception("Erreur fatale : capture arrêtée")
            return 1
    elif args.command == "transcribe":
        from cnews_tts.transcribe import run_transcribe

        _setup_logging(cfg.logs_dir / "transcribe.log")
        try:
            if run_transcribe(cfg, watch=args.watch).failed:
                return 1
        except KeyboardInterrupt:
            log.info("Arrêt demandé : transcription interrompue (le fichier en cours sera repris).")
    elif args.command == "follow":
        from cnews_tts.follow import run_follow

        try:
            run_follow(cfg.transcripts_dir, args.lines, keywords=cfg.alert_keywords if args.alert else ())
        except KeyboardInterrupt:
            pass
    elif args.command == "coverage":
        since = None
        if args.since:
            since = datetime.fromisoformat(args.since).replace(tzinfo=ZoneInfo(cfg.timezone))
        print(coverage_report(cfg.coverage_csv, cfg.timezone, since))
    return 0


if __name__ == "__main__":
    sys.exit(main())
