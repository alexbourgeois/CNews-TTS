"""Jeu multijoueur sur le réseau local : chacun tape dans son navigateur les mots qui tombent dans la fenêtre
du serveur, pour les effacer. Un mot rouge explose et blesse les autres joueurs, un vert soigne celui qui l'a tapé.

Pas de comptes : le nom suffit (le reprendre, c'est reprendre la partie de ce joueur).
"""

import json
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from cnews_tts.hallucinations import normalize
from cnews_tts.sentiment import NEUTRAL_BELOW

MAX_HP = 100
HP_PER_POINT = 8  # dégâts ou soin par point de charge du mot : « guerre » (-2,9) enlève 23 PV
RESPAWN_S = 10  # un joueur KO revient avec tous ses PV au bout de ce délai
MAX_NAME = 20
PAGE = Path(__file__).with_name("game_page.html")


@dataclass
class Player:
    name: str
    hp: int = MAX_HP
    score: int = 0
    ko_until: float = 0.0


class Game:
    """État partagé entre le serveur web (un fil par requête) et la fenêtre : tout passe par self.lock."""

    def __init__(self, world, lexicon: dict[str, float]):
        self.world = world  # WordWorld de la fenêtre ; branché par run_window
        self.lexicon = lexicon
        self.lock = threading.RLock()
        self.players: dict[str, Player] = {}
        self.events: deque[str] = deque(maxlen=30)
        self.effects: list[tuple[float, float, str, float]] = []  # (x, y, genre, début) à dessiner
        self.missed = 0  # mots partis sans avoir été tapés

    def join(self, name: str) -> Player:
        name = name.strip()[:MAX_NAME]
        if not name:
            raise ValueError("nom vide")
        with self.lock:
            if name not in self.players:
                self.players[name] = Player(name)
                self.events.append(f"{name} rejoint la partie")
            return self.players[name]

    def erase(self, name: str, typed: str, now: float) -> dict:
        with self.lock:
            player = self.join(name)
            self._revive(player, now)
            if player.hp == 0:
                return {"ok": False, "kind": "ko", "message": f"KO : retour dans {player.ko_until - now:.0f} s"}
            target = normalize(typed)
            blocks = self.world.blocks if self.world else []
            block = next((b for b in blocks if target and normalize(b.text) == target), None)
            if block is None:
                return {"ok": False, "kind": "absent", "message": f"« {typed.strip()} » n'est pas à l'écran"}

            score = self.lexicon.get(block.text.lower(), 0.0)
            amount = round(HP_PER_POINT * abs(score))
            x, y = block.body.position
            player.score += 1
            if score <= -NEUTRAL_BELOW:
                kind = "rouge"
                self.world.explode(block)
                message = f"{player.name} fait exploser « {block.text} » : -{amount} PV aux autres"
                for other in self.players.values():
                    if other is player or other.hp == 0:
                        continue
                    other.hp = max(0, other.hp - amount)
                    if other.hp == 0:
                        other.ko_until = now + RESPAWN_S
                        self.events.append(f"{other.name} est KO")
            elif score >= NEUTRAL_BELOW:
                kind = "vert"
                self.world.remove(block)
                player.hp = min(MAX_HP, player.hp + amount)
                message = f"{player.name} récupère {amount} PV avec « {block.text} »"
            else:
                kind = "neutre"
                self.world.remove(block)
                message = f"{player.name} efface « {block.text} »"
            self.events.append(message)
            self.effects.append((x, y, kind, now))
            return {"ok": True, "kind": kind, "message": message}

    def state(self, name: str, now: float) -> dict:
        with self.lock:
            for player in self.players.values():
                self._revive(player, now)
            me = self.players.get(name.strip())
            ranking = sorted(self.players.values(), key=lambda p: (-p.score, p.name))
            return {
                "me": self._public(me, now) if me else None,
                "players": [self._public(p, now) for p in ranking],
                "events": list(self.events)[-8:][::-1],
                "words": len(self.world.blocks) if self.world else 0,
                "missed": self.missed,
            }

    @staticmethod
    def _revive(player: Player, now: float) -> None:
        if player.hp == 0 and now >= player.ko_until:
            player.hp = MAX_HP

    @staticmethod
    def _public(player: Player, now: float) -> dict:
        ko = max(0, round(player.ko_until - now)) if player.hp == 0 else 0
        return {"name": player.name, "hp": player.hp, "score": player.score, "ko": ko}


def start_server(game: Game, host: str = "0.0.0.0", port: int = 8000, clock=time.monotonic) -> ThreadingHTTPServer:
    """Serveur web en tâche de fond : la page du joueur et trois appels JSON (rejoindre, taper, état)."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/state":
                self._json(game.state(parse_qs(url.query).get("name", [""])[0], clock()))
            else:
                self._send(404, b"", "text/plain")

        def do_POST(self):
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if self.path == "/api/join":
                    self._json({"name": game.join(str(data.get("name", ""))).name})
                elif self.path == "/api/type":
                    self._json(game.erase(str(data.get("name", "")), str(data.get("word", "")), clock()))
                else:
                    self._send(404, b"", "text/plain")
            except ValueError as e:  # JSON illisible ou nom vide
                self._json({"error": str(e)}, 400)

        def _json(self, obj, status: int = 200):
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _send(self, status: int, body: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # pas une ligne par requête dans la console
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def lan_address() -> str:
    """Adresse de ce PC sur le réseau local (aucun paquet n'est envoyé)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.0.2.1", 80))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"
