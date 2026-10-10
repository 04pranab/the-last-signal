import time

import pytest

from game.maps import generate_map
from game.maps.validator import validate_map

SEEDS = list(range(1000, 1100))   # 100 different seeds


@pytest.fixture(scope="module")
def maps():
    return {s: generate_map(s) for s in SEEDS}


def test_100_seeds_generate_and_validate(maps):
    for s, m in maps.items():
        assert validate_map(m) == [], f"seed {s}"
        assert 25 <= len(m.rooms) <= 45
        assert m.width >= 180 and m.height >= 120
        assert len(set(m.spawns)) >= 16


def test_same_seed_same_map():
    a, b = generate_map(18374621), generate_map(18374621)
    assert bytes(a.tiles) == bytes(b.tiles)
    assert [(p.sprite, p.x, p.y) for p in a.props] == [(p.sprite, p.x, p.y) for p in b.props]
    assert a.secret["answer"] == b.secret["answer"]


def test_different_seeds_differ(maps):
    layouts = {bytes(m.tiles) for m in maps.values()}
    assert len(layouts) == len(maps)
    answers = {m.secret["answer"]["freq"] + m.secret["answer"]["seq"] for m in maps.values()}
    assert len(answers) > 80
    # clue terminals are not always in the same place
    first = {tuple((m.object_by_id[c].x, m.object_by_id[c].y) for c in m.meta["clue_ids"]) for m in maps.values()}
    assert len(first) == len(maps)


def test_room_variety(maps):
    sizes = {(r.w, r.h) for m in maps.values() for r in m.rooms}
    assert len(sizes) > 50
    kinds = {r.kind for m in maps.values() for r in m.rooms}
    assert {"hub", "comms", "server_wing", "archive", "security", "medical", "maintenance", "storage", "lab"} <= kinds


def test_generation_speed():
    t = time.time()
    generate_map(424242)
    assert time.time() - t < 5


def test_payload_roundtrip_hides_secrets():
    from game.maps.generator import MapData
    m = generate_map(77)
    p = m.to_payload()
    assert "secret" not in p and "answer" not in str(p)
    m2 = MapData.from_payload(p)
    assert bytes(m2.tiles) == bytes(m.tiles) and len(m2.objects) == len(m.objects)
    assert bytes(m2.solid) == bytes(m.solid)
