from cnews_tts.visual import WordWorld

W, H = 800, 600


def run(world, seconds):
    for _ in range(int(seconds * 120)):
        world.step(1 / 120)


def inside(world, block):
    x, y = block.body.position
    return 0 <= x <= W and 0 <= y <= H


def test_word_falls_and_rests_on_floor():
    world = WordWorld(W, H)
    block = world.add("guerre", (100, 40), now=0, x=400)
    assert block.body.position.y < 100  # apparaît en haut
    run(world, 4)
    assert abs(block.body.position.y - (H - 20)) < 3
    assert abs(block.body.velocity.y) < 5


def test_words_pile_up():
    world = WordWorld(W, H)
    a = world.add("paix", (120, 40), now=0, x=400)
    run(world, 2)
    b = world.add("loi", (120, 40), now=2, x=400)
    run(world, 3)
    assert abs((a.body.position.y - b.body.position.y) - 40) < 4


def test_thrown_word_bounces_but_stays_in_window():
    world = WordWorld(W, H)
    block = world.add("viol", (100, 40), now=0, x=400)
    block.body.velocity = (20000, -20000)
    for _ in range(4 * 120):
        world.step(1 / 120)
        assert inside(world, block)


def test_words_expire_unless_held():
    world = WordWorld(W, H, lifetime_s=10)
    held = world.add("tenu", (100, 40), now=0, x=200)
    free = world.add("libre", (100, 40), now=0, x=600)
    run(world, 3)
    assert world.expire(now=9.9) == []
    assert world.grab(held.body.position)
    assert world.expire(now=10.5) == [free]
    assert world.alpha(held, now=10.5) == 255  # tenu : reste bien visible
    world.release(now=12)  # lâché après sa fin de vie : s'efface en douceur
    assert world.expire(now=12.5) == []
    assert world.expire(now=13.1) == [held]
    assert world.blocks == []


def test_grabbed_word_follows_the_mouse():
    world = WordWorld(W, H)
    block = world.add("mot", (100, 40), now=0, x=200)
    run(world, 3)
    assert not world.grab((700, 100))  # rien sous la souris
    assert world.grab(block.body.position)
    world.drag((600, 200))
    run(world, 2)
    x, y = block.body.position
    assert abs(x - 600) < 30 and abs(y - 200) < 30


def test_alpha_fades_during_last_second():
    world = WordWorld(W, H, lifetime_s=10)
    block = world.add("mot", (100, 40), now=0, x=200)
    assert world.alpha(block, now=5) == 255
    assert 100 < world.alpha(block, now=9.5) < 155


def test_block_colors_follow_sentiment():
    from cnews_tts.visual import NEUTRAL_BG, block_colors

    lex = {"guerre": -2.9, "victoire": 2.8}
    (r, g, _), _ = block_colors("Guerre", lex)
    assert r > 200 and g < 100
    (r, g, _), _ = block_colors("victoire", lex)
    assert g > 180 and r < 100
    assert block_colors("loi", lex)[0] == NEUTRAL_BG


def test_split_words_drops_punctuation():
    from cnews_tts.visual import split_words

    assert split_words("« Bonjour », dit-il… 3000 euros !") == ["Bonjour", "dit-il", "3000", "euros"]
