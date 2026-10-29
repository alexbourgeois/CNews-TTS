"""Fenêtre des mots du direct : chaque mot tombe en bloc coloré, rebondit, s'empile, se lance à la souris
et s'efface au bout de sa durée de vie. Physique pymunk, affichage pygame."""

import math
import os
import queue
import random
import re
import threading
import time
from dataclasses import dataclass

import pymunk

from cnews_tts.sentiment import GREEN, GREY, RED, word_rgb

GRAVITY = 900  # px/s²
WALL = 200  # murs épais hors de la fenêtre : un mot lancé fort ne les traverse pas
MAX_SPEED = 3000  # px/s
MAX_BLOCKS = 200
FADE_S = 1.0  # le mot s'efface pendant sa dernière seconde
SPAWN_EVERY_S = 0.15  # les mots d'une même phrase tombent l'un après l'autre
MAX_PENDING = 40
SUBSTEPS = 4
BLAST_RADIUS = 320  # px : portée du souffle d'un mot rouge qui explose
BLAST_SPEED = 1100  # px/s donnés à un mot collé à l'explosion, moins en s'éloignant
BACKGROUND = (18, 20, 26)
NEUTRAL_BG = (70, 76, 92)
PAD_X, PAD_Y = 12, 6
WORD = re.compile(r"\w+(?:[-']\w+)*")


@dataclass(eq=False)
class Block:
    text: str
    body: pymunk.Body
    shape: pymunk.Poly
    born: float
    surface: object = None  # image du bloc (pygame)


class WordWorld:
    """La simulation seule, sans affichage : coordonnées en pixels, y vers le bas."""

    def __init__(self, width: int, height: int, lifetime_s: float = 10.0):
        self.space = pymunk.Space()
        self.space.gravity = (0, GRAVITY)
        self.lifetime_s = lifetime_s
        self.blocks: list[Block] = []
        self._walls: list[pymunk.Poly] = []
        self._mouse = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        self._joint: pymunk.PivotJoint | None = None
        self._held: Block | None = None
        self.resize(width, height)

    def resize(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        if self._walls:
            self.space.remove(*self._walls)
        t = WALL
        boxes = [(-t, -t, 0, height + t), (width, -t, width + t, height + t),
                 (-t, -t, width + t, 0), (-t, height, width + t, height + t)]
        self._walls = [pymunk.Poly(self.space.static_body, [(l, top), (r, top), (r, b), (l, b)])
                       for l, top, r, b in boxes]
        for wall in self._walls:
            wall.friction, wall.elasticity = 0.8, 0.4
        self.space.add(*self._walls)
        for block in self.blocks:  # fenêtre rétrécie : les mots restent dedans
            x, y = block.body.position
            block.body.position = (min(max(x, 10), width - 10), min(max(y, 10), height - 10))

    def add(self, text: str, size: tuple[int, int], now: float, x: float | None = None, spin: float = 0.0,
            surface=None) -> Block:
        w, h = size
        mass = w * h / 1000
        body = pymunk.Body(mass, pymunk.moment_for_box(mass, size))
        if x is None:
            x = random.uniform(w / 2, max(w / 2, self.width - w / 2))
        body.position = (x, h / 2 + 2)
        body.angular_velocity = spin
        shape = pymunk.Poly.create_box(body, size, radius=1)
        shape.friction, shape.elasticity = 0.7, 0.3
        self.space.add(body, shape)
        block = Block(text, body, shape, now, surface)
        self.blocks.append(block)
        if len(self.blocks) > MAX_BLOCKS:
            self.remove(self.blocks[0])
        return block

    def step(self, dt: float) -> None:
        for block in self.blocks:  # avant le pas : pymunk déplace les corps avant d'appeler velocity_func
            if block.body.velocity.length > MAX_SPEED:
                block.body.velocity = block.body.velocity.scale_to_length(MAX_SPEED)
        self.space.step(dt)

    def grab(self, point) -> bool:
        hit = self.space.point_query_nearest(point, 0, pymunk.ShapeFilter())
        if hit is None or hit.shape.body.body_type != pymunk.Body.DYNAMIC:
            return False
        self.release()
        body = hit.shape.body
        self._mouse.position = point
        self._joint = pymunk.PivotJoint(self._mouse, body, (0, 0), body.world_to_local(point))
        self._joint.max_force = 20000 * body.mass
        self._joint.error_bias = (1 - 0.15) ** 60
        self.space.add(self._joint)
        self._held = next(b for b in self.blocks if b.body is body)
        return True

    def drag(self, point) -> None:
        self._mouse.position = point

    def release(self, now: float | None = None) -> None:
        if self._joint is not None:
            self.space.remove(self._joint)
        if self._held is not None and now is not None:  # déjà en fin de vie : une seconde pour s'effacer
            self._held.born = max(self._held.born, now - self.lifetime_s + FADE_S)
        self._joint = self._held = None

    def expire(self, now: float) -> list[Block]:
        old = [b for b in self.blocks if now - b.born >= self.lifetime_s and b is not self._held]
        for block in old:
            self.remove(block)
        return old

    def alpha(self, block: Block, now: float) -> int:
        if block is self._held:
            return 255
        left = self.lifetime_s - (now - block.born)
        return round(255 * max(0.0, min(1.0, left / FADE_S)))

    def explode(self, block: Block) -> None:
        """Retire le mot et souffle ses voisins, d'autant plus fort qu'ils sont près."""
        center = block.body.position
        self.remove(block)
        for other in self.blocks:
            offset = other.body.position - center
            if offset.length >= BLAST_RADIUS:
                continue
            direction = (offset.normalized() if offset.length else pymunk.Vec2d(0, -1)) + (0, -0.6)
            other.body.velocity += direction.normalized() * BLAST_SPEED * (1 - offset.length / BLAST_RADIUS)
            other.body.angular_velocity += random.uniform(-6, 6)

    def remove(self, block: Block) -> None:
        if block is self._held:
            self.release()
        self.space.remove(block.body, block.shape)
        self.blocks.remove(block)


def split_words(text: str) -> list[str]:
    return WORD.findall(text)


def block_colors(word: str, lexicon: dict[str, float]) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """(fond, texte) : rouge à vert selon la charge du mot, gris-bleu s'il est neutre."""
    score = lexicon.get(word.lower())
    bg = (word_rgb(score) if score is not None else None) or NEUTRAL_BG
    luminance = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
    return bg, ((20, 20, 20) if luminance > 150 else (245, 245, 245))


def _render_block(pygame, font, text: str, lexicon: dict[str, float]):
    bg, fg = block_colors(text, lexicon)
    label = font.render(text, True, fg)
    surface = pygame.Surface((label.get_width() + 2 * PAD_X, label.get_height() + 2 * PAD_Y), pygame.SRCALPHA)
    pygame.draw.rect(surface, bg, surface.get_rect(), border_radius=8)
    surface.blit(label, (PAD_X, PAD_Y))
    return surface


EFFECT_S = 0.6  # durée de l'onde d'un mot effacé
EFFECT_COLORS = {"rouge": RED, "vert": GREEN, "neutre": GREY}


def _draw_game(pygame, screen, font, game, now: float, banner: str) -> None:
    """Ondes des mots effacés, tableau des joueurs, adresse à ouvrir et mots ratés (appelé sous game.lock)."""
    game.effects[:] = [e for e in game.effects if now - e[3] < EFFECT_S]
    for x, y, kind, t0 in game.effects:
        age = (now - t0) / EFFECT_S
        radius = round(20 + (BLAST_RADIUS if kind == "rouge" else 90) * age)
        pygame.draw.circle(screen, EFFECT_COLORS[kind], (round(x), round(y)), radius, max(1, round(8 * (1 - age))))
    lines = [(banner, (150, 160, 180))]
    for p in sorted(game.players.values(), key=lambda p: (-p.score, p.name)):
        color = RED if p.hp <= 25 else (255, 173, 51) if p.hp <= 50 else (235, 238, 243)
        lines.append((f"{p.name}   {'KO' if p.hp == 0 else str(p.hp) + ' PV'}   {p.score} pts", color))
    y = 12
    for line, color in lines:
        screen.blit(font.render(line, True, color), (14, y))
        y += font.get_linesize()
    missed = font.render(f"ratés : {game.missed}", True, (150, 160, 180))
    screen.blit(missed, (screen.get_width() - missed.get_width() - 14, 12))


def run_window(words: queue.Queue, lexicon: dict[str, float], lifetime_s: float, stop: threading.Event,
               size: tuple[int, int] = (1000, 700), game=None, banner: str = "",
               title: str = "Mots du direct") -> None:
    """Boucle de la fenêtre (fil principal), jusqu'à sa fermeture ou stop. words : textes à faire tomber.

    Avec game, les joueurs effacent les mots depuis le serveur web : physique et dessin se font sous game.lock.
    """
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame

    pygame.init()
    screen = pygame.display.set_mode(size, pygame.RESIZABLE)
    pygame.display.set_caption(title)
    font = pygame.font.SysFont("segoeui,arial", 26, bold=True)
    small = pygame.font.SysFont("segoeui,arial", 20, bold=True)
    clock = pygame.time.Clock()
    world = WordWorld(*size, lifetime_s=lifetime_s)
    lock = threading.Lock()
    if game is not None:
        game.world, lock = world, game.lock
    pending: list[str] = []
    next_spawn = 0.0
    try:
        while not stop.is_set():
            dt = min(clock.tick(60) / 1000, 1 / 20)  # hors du verrou : attend la prochaine image
            now = time.monotonic()
            with lock:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return
                    if event.type == pygame.VIDEORESIZE:
                        world.resize(event.w, event.h)
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        world.grab(event.pos)
                    elif event.type == pygame.MOUSEMOTION:
                        world.drag(event.pos)
                    elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                        world.release(now)
                while not words.empty():
                    pending.extend(split_words(words.get_nowait()))
                del pending[:-MAX_PENDING]  # trop en retard : on saute les plus anciens
                if pending and now >= next_spawn:
                    text = pending.pop(0)
                    surface = _render_block(pygame, font, text, lexicon)
                    world.add(text, surface.get_size(), now, spin=random.uniform(-1.5, 1.5), surface=surface)
                    next_spawn = now + SPAWN_EVERY_S

                for _ in range(SUBSTEPS):
                    world.step(dt / SUBSTEPS)
                expired = world.expire(now)

                screen.fill(BACKGROUND)
                for block in world.blocks:
                    image = pygame.transform.rotate(block.surface, -math.degrees(block.body.angle))
                    image.set_alpha(world.alpha(block, now))
                    x, y = block.body.position
                    screen.blit(image, image.get_rect(center=(round(x), round(y))))
                if game is not None:
                    game.missed += len(expired)
                    _draw_game(pygame, screen, small, game, now, banner)
            pygame.display.flip()
    finally:
        pygame.quit()
