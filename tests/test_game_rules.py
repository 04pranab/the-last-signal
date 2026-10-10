from collections import deque

import pytest

from game.config import TILE
from game.maps import generate_map
from game.maps.validator import object_access_cells
from game.state import GameWorld

DT = 1 / 30


@pytest.fixture()
def world():
    return GameWorld(generate_map(18374621), echo=False)


def stand_at_object(w, pid, oid):
    o = w.map.object_by_id[oid]
    ax, ay = object_access_cells(w.map, o)[0]
    p = w.players[pid]
    p.x, p.y = (ax + 0.5) * TILE, (ay + 0.5) * TILE


def bfs_path(w, start, goal):
    m = w.map
    def ok(x, y):
        if m.solid[y * m.width + x]:
            return False
        did = m.door_at.get((x, y))
        return not (did is not None and m.doors[did].restricted and not w.power)
    prev = {start: None}
    q = deque([start])
    while q:
        c = q.popleft()
        if c == goal:
            break
        for n in ((c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)):
            if n not in prev and ok(*n):
                prev[n] = c
                q.append(n)
    assert goal in prev
    path, c = [], goal
    while c:
        path.append(c)
        c = prev[c]
    return path[::-1]


def walk_to(w, pid, goal, max_ticks=6000):
    p = w.players[pid]
    path = bfs_path(w, (int(p.x // TILE), int(p.y // TILE)), goal)
    i = 1
    for _ in range(max_ticks):
        if i >= len(path):
            break
        tx, ty = (path[i][0] + 0.5) * TILE, (path[i][1] + 0.5) * TILE
        dx, dy = tx - p.x, ty - p.y
        if abs(dx) < 6 and abs(dy) < 6:
            i += 1
            continue
        w.set_input(pid, max(-1, min(1, dx)), max(-1, min(1, dy)))
        w.tick(DT)
    w.set_input(pid, 0, 0)
    return i >= len(path)


def full_playthrough(w, pid=1):
    stand_at_object(w, pid, "generator")
    w.interact(pid, "generator")
    for cid_obj in w.map.meta["clue_ids"]:
        stand_at_object(w, pid, cid_obj)
        w.interact(pid, cid_obj)
    stand_at_object(w, pid, "core")
    w.interact(pid, "core")
    assert w.boss is not None and not w.boss_defeated      # the Warden awakens and locks the transmitter
    w.debug_kill_boss()
    stand_at_object(w, pid, "transmitter")
    a = w.map.secret["answer"]
    w.transmit(pid, a["freq"], a["chan"], a["seq"])


def test_walk_from_spawn_to_generator_through_real_collision(world):
    p = world.add_player(1, "Om")
    g = world.map.object_by_id["generator"]
    goal = object_access_cells(world.map, g)[0]
    assert walk_to(world, 1, goal)
    world.interact(1, "generator")
    assert world.power


def test_restricted_doors_locked_until_power(world):
    m = world.map
    d = next(d for d in m.doors if d.restricted)
    assert world.door_codes()[d.id] == 2
    world.add_player(1, "Om")
    cx, cy = d.cells[0]
    p = world.players[1]
    p.x, p.y = (cx + 0.5) * TILE, (cy + 0.5) * TILE - 0   # stand in the doorway cell
    world.tick(DT)
    world.power = True
    world.tick(DT)
    assert world.door_codes()[d.id] in (0, 1)


def test_full_game_can_be_completed(world):
    world.add_player(1, "Om")
    full_playthrough(world)
    assert world.phase == "victory"
    assert len(world.found) == 5


def test_wrong_signal_rejected_game_continues_with_lockout(world):
    world.add_player(1, "Om")
    stand_at_object(world, 1, "generator"); world.interact(1, "generator")
    stand_at_object(world, 1, "core"); world.interact(1, "core")
    world.debug_kill_boss()
    stand_at_object(world, 1, "transmitter")
    world.drain()
    world.transmit(1, "000", "00", "000")
    msgs = [m for t, m in world.drain() if m["t"] == "tx_result"]
    assert msgs and not msgs[0]["ok"] and msgs[0]["msg"] == "SIGNAL REJECTED"
    assert world.phase == "playing"
    world.transmit(1, "111", "11", "111")
    assert [m["msg"] for t, m in world.drain() if m["t"] == "tx_result"] == ["RECHARGING - WAIT"]
    world.t += 5
    a = world.map.secret["answer"]
    world.transmit(1, a["freq"], a["chan"], a["seq"])
    assert world.phase == "victory"


def test_transmit_requires_power_core_and_range(world):
    world.add_player(1, "Om")
    a = world.map.secret["answer"]
    stand_at_object(world, 1, "transmitter")
    world.transmit(1, a["freq"], a["chan"], a["seq"])
    assert world.phase == "playing"          # offline
    world.power = world.core_online = True
    world.players[1].x, world.players[1].y = 100, 100
    world.transmit(1, a["freq"], a["chan"], a["seq"])
    assert world.phase == "playing"          # out of range


def test_invalid_transmit_formats_rejected(world):
    world.add_player(1, "Om")
    world.power = world.core_online = True
    stand_at_object(world, 1, "transmitter")
    for bad in (("12", "12", "123"), ("abc", "12", "123"), ("123", "1", "123"), ("123", "12", "12a")):
        world.transmit(1, *bad)
    assert world.phase == "playing" and world.attempts == 0


def test_interact_out_of_range_denied(world):
    world.add_player(1, "Om")
    world.players[1].x, world.players[1].y = 100, 100
    world.interact(1, "generator")
    assert not world.power


def test_unpowered_terminals_offline(world):
    world.add_player(1, "Om")
    o = next(o for o in world.map.objects if o.needs_power and o.kind == "terminal")
    stand_at_object(world, 1, o.id)
    world.drain()
    world.interact(1, o.id)
    assert any("NO POWER" in m.get("text", "") for t, m in world.drain())
    assert world.players[1].notes == []


def test_timeout_is_failure(world):
    world.add_player(1, "Om")
    world.time_limit = 1.0
    for _ in range(60):
        world.tick(DT)
    assert world.phase == "failure"
    world.interact(1, "generator")
    assert not world.power


def test_clients_cannot_set_position_or_state(world):
    p = world.add_player(1, "Om")
    x0 = p.x
    world.set_input(1, 1e9, 1e9)           # clamped to unit length
    world.tick(0.1)
    assert abs(p.x - x0) < 40 and abs(p.y - 4256) < 1e5
    world.set_input(99, 1, 1)               # invalid player id ignored


def test_echo_events_have_cooldowns_and_do_not_spam():
    w = GameWorld(generate_map(31), echo=True)
    w.add_player(1, "Om")
    starts = []
    for _ in range(int(900 / DT)):
        w.tick(DT)
        for t, m in w.drain():
            if m.get("k") == "echo":
                starts.append(w.t)
    assert 5 <= len(starts) <= 30
    assert min(starts) > 45
    assert all(b - a >= 29 for a, b in zip(starts, starts[1:]))


@pytest.mark.parametrize("ev", ["LIGHTS_OUT", "TERMINAL_CORRUPTION", "DOOR_MALFUNCTION", "SIGNAL_INTERFERENCE", "FALSE_TERMINAL_MESSAGE"])
def test_each_echo_event_applies_and_expires(ev):
    w = GameWorld(generate_map(32), echo=True)
    pl = w.add_player(1, "Om")
    d = next(d for d in w.map.doors if not d.restricted)
    pl.x, pl.y = (d.cells[0][0] + .5) * TILE, (d.cells[0][1] + .5) * TILE
    assert w.echo.trigger(ev) == ev
    w.echo.enabled = False          # ignore later random events
    st = w.state_message()
    assert any([st["lights"], st["intf"], st["corrupt"], st["false"], 2 in st["doors"] or 3 in st["doors"]])
    for _ in range(int(60 / DT)):
        w.tick(DT)
    st = w.state_message()
    assert not (st["lights"] or st["intf"] or st["corrupt"] or st["false"])


def test_false_message_is_marked_unstable_and_not_counted():
    w = GameWorld(generate_map(33), echo=False)
    w.add_player(1, "Om")
    oid = w.map.meta["clue_ids"][0]
    w.power = True
    w.false_until[oid] = 999
    stand_at_object(w, 1, oid)
    w.drain()
    w.interact(1, oid)
    entry = next(m["entry"] for t, m in w.drain() if m["t"] == "read")
    assert entry["integrity"] < 100 and not w.found
    w.false_until[oid] = 0
    w.interact(1, oid)
    entry2 = next(m["entry"] for t, m in w.drain() if m["t"] == "read")
    assert entry2["integrity"] == 100 and entry2["lines"] != entry["lines"] and len(w.found) == 1


def test_fifteen_players_fit_and_spawn_on_free_cells():
    w = GameWorld(generate_map(34), echo=False)
    for pid in range(1, 16):
        p = w.add_player(pid, f"P{pid}")
        assert not w.solid_at(int(p.x // TILE), int(p.y // TILE))
    assert len({(round(p.x), round(p.y)) for p in w.players.values()}) == 15
