import math

import pytest

from game.config import TILE
from game.maps import generate_map
from game.state import GameWorld
from game.zombies import KINDS, MAX_ZOMBIES, Zombie

DT = 1 / 30


@pytest.fixture()
def world():
    return GameWorld(generate_map(18374621), echo=False, zombies=False)


def open_floor_near_spawn(w):
    x, y = w.map.spawns[0]
    return (x + 0.5) * TILE, (y + 0.5) * TILE


def free_run(w, x, y, cells=6):
    """Find a horizontal run of free cells starting at (x,y) going right."""
    cx, cy = int(x // TILE), int(y // TILE)
    return all(not w.solid_at(cx + i, cy) for i in range(cells))


def test_zombies_populate_away_from_spawn_and_on_free_cells():
    w = GameWorld(generate_map(18374621), echo=False)
    assert 15 <= len(w.zombies.zombies) <= MAX_ZOMBIES
    hub = w.map.rooms[w.map.meta["hub_room"]]
    hx, hy = hub.center
    for z in w.zombies.zombies.values():
        assert not w.solid_at(int(z.x // TILE), int(z.y // TILE))
        assert abs(z.x / TILE - hx) + abs(z.y / TILE - hy) >= 24


def test_shooting_kills_zombie_and_uses_ammo(world):
    p = world.add_player(1, "Om")
    p.x, p.y = open_floor_near_spawn(world)
    # find a straight free line
    for dx in range(4, 7):
        pass
    z = Zombie("walker", p.x + 3 * TILE, p.y)
    if not free_run(world, p.x, p.y, 4):
        pytest.skip("no straight line at spawn")
    world.zombies.zombies[z.id] = z
    z.awake = False
    world.set_input(1, 0, 0, 0.0, True)
    for _ in range(40):
        world.tick(DT)
        if z.id not in world.zombies.zombies:
            break
    assert z.id not in world.zombies.zombies and p.kills == 1
    assert p.ammo < p.clip


def test_walls_block_bullets(world):
    p = world.add_player(1, "Om")
    p.x, p.y = open_floor_near_spawn(world)
    # aim straight at a solid wall: zombie behind it must survive
    ang = None
    for a in (0, math.pi / 2, math.pi, -math.pi / 2):
        cx, cy = int(p.x // TILE), int(p.y // TILE)
        dx, dy = round(math.cos(a)), round(math.sin(a))
        run = 0
        while not world.solid_at(cx + dx * (run + 1), cy + dy * (run + 1)) and run < 12:
            run += 1
        if run < 8:
            ang, wall_dist = a, run + 1
            break
    assert ang is not None
    z = Zombie("brute", p.x + math.cos(ang) * (wall_dist + 2) * TILE, p.y + math.sin(ang) * (wall_dist + 2) * TILE)
    world.zombies.zombies[z.id] = z
    z.awake = False
    world.set_input(1, 0, 0, ang, True)
    for _ in range(20):
        world.tick(DT)
    assert z.hp == z.max_hp


def test_reload_and_empty_clip(world):
    p = world.add_player(1, "Om")
    p.ammo = 0
    world.set_input(1, 0, 0, 0.0, True)
    world.tick(DT)
    assert p.reload_until > world.t
    world.set_input(1, 0, 0, 0.0, False)
    for _ in range(int(1.6 / DT)):
        world.tick(DT)
    assert p.ammo == p.clip


def test_zombie_chases_and_damages_player_then_respawn(world):
    p = world.add_player(1, "Om")
    p.x, p.y = open_floor_near_spawn(world)
    p.invuln_until = 0
    z = Zombie("runner", p.x + 2.5 * TILE, p.y)
    if not free_run(world, p.x, p.y, 4):
        pytest.skip("no straight line at spawn")
    world.zombies.zombies[z.id] = z
    for _ in range(int(30 / DT)):
        world.tick(DT)
        if p.dead:
            break
    assert p.dead and p.deaths == 1
    # dead players cannot act and respawn after the timer with full health
    world.interact(1, "generator")
    assert not world.power
    world.zombies.zombies.clear()
    for _ in range(int(9 / DT)):
        world.tick(DT)
    assert not p.dead and p.hp == p.max_hp and world.t < world.time_limit


def test_zombie_pathfinds_around_walls():
    from collections import deque
    cands = None
    for seed in range(1, 25):
        w = GameWorld(generate_map(seed), echo=False, zombies=False)
        p = w.add_player(1, "Om")
        room = next(r for r in w.map.rooms if r.kind in ("lab", "storage") and r.w >= 8)
        free = [(x, y) for y in range(room.y, room.y + room.h) for x in range(room.x, room.x + room.w) if not w.solid_at(x, y)]
        sx, sy = free[len(free) // 2]
        p.x, p.y = (sx + .5) * TILE, (sy + .5) * TILE
        dist = {(sx, sy): 0}
        q = deque([(sx, sy)])
        while q:
            c = q.popleft()
            if dist[c] > 34:
                continue
            for n in ((c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)):
                if n not in dist and not w.path_solid(*n):
                    dist[n] = dist[c] + 1
                    q.append(n)
        # close as the crow flies but needs a long detour (a wall is in between)
        cands = [c for c, d in dist.items() if 20 <= d <= 34]
        if cands:
            break
    if not cands:
        pytest.skip("no detour cell on the tried maps")
    cx, cy = cands[0]
    z = Zombie("runner", (cx + .5) * TILE, (cy + .5) * TILE)
    w.zombies.zombies[z.id] = z
    z.awake = True
    z.alert_until = 1e9
    z.alert_pos = (p.x, p.y)
    for _ in range(int(60 / DT)):
        w.tick(DT)
        p.hp = p.max_hp
    assert math.hypot(z.x - p.x, z.y - p.y) < 3 * TILE


def test_surge_event_spawns_zombies_out_of_sight():
    w = GameWorld(generate_map(40), echo=True, zombies=False)
    p = w.add_player(1, "Om")
    before = len(w.zombies.zombies)
    assert w.echo.trigger("ZOMBIE_SURGE") == "ZOMBIE_SURGE"
    assert len(w.zombies.zombies) > before
    for z in w.zombies.zombies.values():
        assert math.hypot(z.x - p.x, z.y - p.y) >= 11 * TILE
        assert not w.solid_at(int(z.x // TILE), int(z.y // TILE))


def test_snapshot_contains_combat_state(world):
    world.add_player(1, "Om")
    z = Zombie("brute", 3000, 3000)
    world.zombies.zombies[z.id] = z
    snap = world.snapshot()
    assert len(snap["p"][0]) >= 8 and snap["z"][0][1] == KINDS["brute"]["idx"]
