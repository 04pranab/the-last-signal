import math

import pytest

from game.config import TILE
from game.maps import generate_map
from game.maps.validator import object_access_cells, validate_map
from game.networking.protocol import validate_client_message
from game.state import GameWorld
from game.weapons import CRATE_WEAPONS, ORDER, WEAPONS
from game.zombies import Zombie

DT = 1 / 30


def at(w, pid, oid):
    o = w.map.object_by_id[oid]
    ax, ay = object_access_cells(w.map, o)[0]
    p = w.players[pid]
    p.x, p.y = (ax + 0.5) * TILE, (ay + 0.5) * TILE


@pytest.fixture()
def world():
    w = GameWorld(generate_map(18374621), echo=False, zombies=False)
    w.add_player(1, "Om")
    return w


def drain(w, kind):
    return [m for t, m in w.drain() if m.get("t") == kind]


# ------------------------------------------------------------------ weapons
def test_crates_cover_all_weapon_types_and_give_weapons(world):
    wc = world.map.secret["weapons"]
    assert len(wc) >= 3 and set(wc.values()) <= set(CRATE_WEAPONS)
    world.power = True
    got = set()
    for oid, name in wc.items():
        at(world, 1, oid)
        world.interact(1, oid)
        got.add(name)
        assert name in world.players[1].inv
        world.interact(1, oid)                      # second time: empty
    assert got == set(wc.values()) and world.players[1].cur == list(wc.values())[-1]
    assert drain(world, "inv")


def test_switch_weapon_only_owned(world):
    p = world.players[1]
    world.switch_weapon(1, "rifle")
    assert p.cur == "pistol"
    world.give_weapon(p, "rifle", switch=False)
    world.switch_weapon(1, "rifle")
    assert p.cur == "rifle"


def test_shotgun_fires_pellets_and_rifle_pierces(world):
    p = world.players[1]
    p.x, p.y = (world.map.spawns[0][0] + .5) * TILE, (world.map.spawns[0][1] + .5) * TILE
    cx, cy = int(p.x // TILE), int(p.y // TILE)
    if not all(not world.solid_at(cx + i, cy) for i in range(9)):
        pytest.skip("no straight run at this spawn")
    # three zombies lined up in front of a rifle
    zs = [Zombie("walker", p.x + (2 + i * 1.2) * TILE, p.y) for i in range(3)]
    for z in zs:
        world.zombies.zombies[z.id] = z
    world.give_weapon(p, "rifle")
    world.set_input(1, 0, 0, 0.0, True)
    for _ in range(12):
        world.tick(DT)
    world.set_input(1, 0, 0, 0.0, False)
    hit = [z for z in zs if z.hp < z.max_hp or z.id not in world.zombies.zombies]
    assert len(hit) >= 2                              # pierced more than one
    shots = drain(world, "fx")
    assert any(m.get("w") == "rifle" for m in shots)
    p2 = world.add_player(2, "B")
    p2.x, p2.y = p.x, p.y
    world.give_weapon(p2, "shotgun")
    world.drain()
    world.set_input(2, 0, 0, 0.0, True)
    for _ in range(12):
        world.tick(DT)
    ev = [m for t, m in world.drain() if m.get("k") == "shot" and m.get("w") == "shotgun"]
    assert ev and len(ev[0]["ends"]) == WEAPONS["shotgun"]["pellets"]


def test_limited_ammo_reload_and_empty(world):
    p = world.players[1]
    world.give_weapon(p, "shotgun")
    p.reserve["shotgun"] = 6
    p.inv["shotgun"] = 0
    world.set_input(1, 0, 0, 0.0, False)
    world.reload(1)
    for _ in range(int(2.3 / DT)):
        world.tick(DT)
    assert p.inv["shotgun"] == 6 and p.reserve["shotgun"] == 0
    p.inv["shotgun"] = 0
    world.drain()
    world.reload(1)
    assert any(m.get("k") == "empty" for m in drain(world, "fx"))


def test_pickups_heal_and_give_ammo(world):
    p = world.players[1]
    p.hp = 40
    world.give_weapon(p, "smg", switch=False)
    before = p.reserve["smg"]
    world._new_pickup("medkit", p.x, p.y)
    world._new_pickup("ammo", p.x, p.y)
    world.tick(DT)
    assert p.hp >= 80 and p.reserve["smg"] > before
    assert not [pk for pk in world.pickups if abs(pk["x"] - p.x) < 40 and abs(pk["y"] - p.y) < 40]


def test_zombie_loot_drops(world):
    got = 0
    for i in range(80):
        z = Zombie("walker", 100 + i, 100)
        world.on_zombie_killed(z)
    assert len(world.pickups) > 4 or len(world.pickups) >= 1


# --------------------------------------------------------------------- boss
def boss_world():
    w = GameWorld(generate_map(18374621), echo=False, zombies=False)
    w.add_player(1, "Om")
    w.power = True
    at(w, 1, "core")
    w.interact(1, "core")
    return w


def test_boss_spawns_on_core_locks_transmitter_and_dies():
    w = boss_world()
    assert w.boss and w.boss.alive and w.core_online and not w.boss_defeated
    at(w, 1, "transmitter")
    w.drain()
    w.interact(1, "transmitter")
    assert not any(m.get("t") == "ui" for t, m in w.drain())          # locked
    w.transmit(1, "000", "00", "000")
    assert w.attempts == 0
    st = w.state_message()
    assert st["boss"]["on"] == "active" and any(t["id"] == "boss" for t in st["obj"]["tasks"])
    w.debug_kill_boss()
    assert w.boss_defeated and w.state_message()["boss"]["on"] == "dead"
    at(w, 1, "transmitter")
    w.drain()
    w.interact(1, "transmitter")
    assert any(m.get("t") == "ui" for t, m in w.drain())


def test_boss_attacks_hurt_and_phases_change():
    w = boss_world()
    b = w.boss
    p = w.players[1]
    room = b.room
    p.x, p.y = b.x + 100, b.y
    p.hp = p.max_hp = 100000.0
    seen = set()
    for _ in range(int(50 / DT)):
        w.tick(DT)
        p.invuln_until = 0
        if b.attack:
            seen.add(b.attack["kind"])
        if b.orbs:
            seen.add("orbs_live")
        if _ == int(20 / DT):
            b.damage(b.max_hp * 0.45, 1)          # into phase 2
        if _ == int(35 / DT):
            b.damage(b.max_hp * 0.3, 1)           # into phase 3
    assert b.phase == 3
    assert {"slam", "orbs"} <= seen
    assert p.hp < 100000.0
    msgs = [m for t, m in w.drain() if m.get("t") == "fx"]
    assert any(m.get("k") == "telegraph" for m in msgs)


def test_boss_hit_by_bullets_and_snapshot_rows():
    w = boss_world()
    p = w.players[1]
    b = w.boss
    cx, cy = int(b.x // TILE), int(b.y // TILE)
    # shoot from a free cell on a straight clear line
    for dist in range(3, 8):
        if all(not w.solid_at(cx - i, cy) for i in range(0, dist + 1)):
            p.x, p.y = b.x - dist * TILE * 0.9, b.y
            break
    else:
        pytest.skip("no clear lane")
    hp0 = b.hp
    w.give_weapon(p, "rifle")
    w.set_input(1, 0, 0, 0.0, True)
    w.tick(DT)
    assert b.hp < hp0
    snap = w.snapshot()
    assert "b" in snap and snap["b"][2] == int(b.hp)


# ---------------------------------------------------- map functions / events
def test_medical_station_heals_with_cooldown(world):
    st = next(o for o in world.map.objects if o.kind == "med_station")
    p = world.players[1]
    p.hp = 20
    at(world, 1, st.id)
    world.interact(1, st.id)
    assert p.hp >= 89
    p.hp = 20
    world.interact(1, st.id)
    assert p.hp == 20            # cooling down


def test_camera_console_scan(world):
    cam = next(o for o in world.map.objects if o.kind == "camera")
    world.power = True
    world.zombies.zombies[99] = Zombie("walker", 500, 500)
    at(world, 1, cam.id)
    world.drain()
    world.interact(1, cam.id)
    sc = drain(world, "scan")
    assert sc and sc[0]["zombies"]


def test_echo_rift_teleports_and_jumpscare_phantom_events():
    w = GameWorld(generate_map(41), echo=True, zombies=True)
    p = w.add_player(1, "Om")
    w.power = True
    before = (p.x, p.y)
    assert w.echo.trigger("ECHO_RIFT") == "ECHO_RIFT"
    assert (p.x, p.y) != before and not w.solid_at(int(p.x // TILE), int(p.y // TILE))
    assert any(m.get("k") == "teleport" for m in drain(w, "fx"))
    w.t += 3.0                      # past the post-teleport grace period
    n0 = len(w.zombies.zombies)
    assert w.echo.trigger("JUMPSCARE") == "JUMPSCARE"
    assert any(m.get("k") == "jumpscare" for m in drain(w, "fx"))
    assert len(w.zombies.zombies) == n0 + 1
    assert w.echo.trigger("PHANTOM") == "PHANTOM"


def test_continuous_zombie_spawning():
    w = GameWorld(generate_map(42), echo=False, zombies=True)
    w.add_player(1, "Om")
    w.zombies.zombies.clear()
    w.zombies.next_trickle = 0
    for _ in range(int(120 / DT)):
        w.tick(DT)
        w.players[1].hp = 100
    assert len(w.zombies.zombies) >= 3


# ------------------------------------------------------------ chat / protocol
def test_chat_and_weapon_messages_validated():
    assert validate_client_message({"t": "chat", "text": "hello\x00 team"})["text"] == "hello team"
    assert validate_client_message({"t": "chat", "text": "   "}) is None
    assert validate_client_message({"t": "chat", "text": 5}) is None
    assert len(validate_client_message({"t": "chat", "text": "x" * 500})["text"]) == 120
    assert validate_client_message({"t": "weapon", "name": "rifle"})["name"] == "rifle"
    assert validate_client_message({"t": "weapon", "name": "bazooka"}) is None


# ---------------------------------------------------------------- map 2
@pytest.mark.parametrize("seed", list(range(3000, 3030)))
def test_mining_complex_generates_valid_maps(seed):
    m = generate_map(seed, "mining_complex")
    assert m.name == "Underground Mining Complex" and validate_map(m) == []
    assert 25 <= len(m.rooms) <= 45 and len(m.secret["weapons"]) >= 3
    assert m.meta["light_tiles"] < 8


def test_mining_complex_differs_and_full_game_completes():
    a, b = generate_map(5, "research_station"), generate_map(5, "mining_complex")
    assert bytes(a.tiles) != bytes(b.tiles) and a.rooms[0].name != b.rooms[0].name
    w = GameWorld(b, echo=False, zombies=False)
    w.add_player(1, "Om")
    at(w, 1, "generator"); w.interact(1, "generator")
    for c in w.map.meta["clue_ids"]:
        at(w, 1, c); w.interact(1, c)
    at(w, 1, "core"); w.interact(1, "core")
    w.debug_kill_boss()
    at(w, 1, "transmitter")
    a_ = w.map.secret["answer"]
    w.transmit(1, a_["freq"], a_["chan"], a_["seq"])
    assert w.phase == "victory"
