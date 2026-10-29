import json
import urllib.request

import pytest

from cnews_tts.game import MAX_HP, RESPAWN_S, Game, start_server
from cnews_tts.visual import WordWorld

LEX = {"guerre": -2.9, "victoire": 2.8, "sécurité": 1.0, "gris": 0.2}


def make(*names):
    world = WordWorld(800, 600)
    game = Game(world, LEX)
    for name in names:
        game.join(name)
    return game, world


def drop(world, text, x=400):
    return world.add(text, (100, 40), now=0, x=x)


def test_join_by_name_keeps_state():
    game, _ = make()
    game.join("Alex").score = 5
    assert game.join(" Alex ").score == 5
    with pytest.raises(ValueError):
        game.join("  ")


def test_typing_a_word_erases_it_and_scores():
    game, world = make("Alex")
    drop(world, "Gouvernement")
    assert not game.erase("Alex", "loi", now=1)["ok"]
    result = game.erase("Alex", "gouvernement", now=1)
    assert result["ok"] and result["kind"] == "neutre"
    assert world.blocks == [] and game.players["Alex"].score == 1


def test_matching_ignores_case_and_accents():
    game, world = make("Alex")
    drop(world, "Sécurité")
    assert game.erase("Alex", "SECURITE", now=1)["ok"]


def test_red_word_explodes_on_the_others():
    game, world = make("A", "B", "C")
    drop(world, "guerre")
    assert game.erase("A", "guerre", now=1)["kind"] == "rouge"
    a, b, c = (game.players[n] for n in "ABC")
    assert a.hp == MAX_HP
    assert b.hp == c.hp < MAX_HP


def test_green_word_heals_up_to_max():
    game, world = make("A")
    game.players["A"].hp = 50
    drop(world, "victoire")
    assert game.erase("A", "victoire", now=1)["kind"] == "vert"
    assert 50 < game.players["A"].hp < MAX_HP
    game.players["A"].hp = MAX_HP - 1
    drop(world, "victoire")
    game.erase("A", "victoire", now=2)
    assert game.players["A"].hp == MAX_HP


def test_ko_player_waits_then_comes_back():
    game, world = make("A", "B")
    game.players["B"].hp = 5
    drop(world, "guerre")
    game.erase("A", "guerre", now=1)
    assert game.players["B"].hp == 0
    drop(world, "loi")
    assert game.erase("B", "loi", now=2)["kind"] == "ko"
    assert game.state("B", now=1 + RESPAWN_S)["me"]["hp"] == MAX_HP
    assert game.erase("B", "loi", now=1 + RESPAWN_S)["ok"]


def test_explosion_pushes_neighbours_away():
    world = WordWorld(800, 600)
    bomb, near = drop(world, "guerre", x=400), drop(world, "loi", x=520)
    for _ in range(240):
        world.step(1 / 120)
    world.explode(bomb)
    assert bomb not in world.blocks
    assert near.body.velocity.x > 100


def _call(url, data=None):
    body = json.dumps(data).encode() if data is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data=body)) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if response.headers.get_content_type() == "application/json" else raw


def test_http_join_type_and_state():
    game, world = make()
    drop(world, "guerre")
    server = start_server(game, "127.0.0.1", 0)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert "<input" in _call(base + "/")
        assert _call(base + "/api/join", {"name": "Alex"}) == {"name": "Alex"}
        assert _call(base + "/api/type", {"name": "Alex", "word": "guerre"})["kind"] == "rouge"
        state = _call(base + "/api/state?name=Alex")
        assert state["me"]["score"] == 1 and state["players"][0]["name"] == "Alex"
    finally:
        server.shutdown()
