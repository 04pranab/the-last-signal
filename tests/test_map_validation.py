from game.maps import generate_map
from game.maps.generator import FLOOR, WALL
from game.maps.validator import flood, object_access_cells, validate_map


def test_validator_accepts_good_map():
    assert validate_map(generate_map(5)) == []


def test_validator_detects_blocked_transmitter():
    m = generate_map(6)
    tx = m.object_by_id[m.meta["transmitter_id"]]
    # wall off every access cell of the transmitter
    for (x, y) in object_access_cells(m, tx):
        m.tiles[y * m.width + x] = WALL
    m.finalize()
    assert any("transmitter" in e for e in validate_map(m))


def test_validator_detects_blocked_spawn():
    m = generate_map(7)
    x, y = m.spawns[0]
    m.tiles[y * m.width + x] = WALL
    m.finalize()
    assert validate_map(m)


def test_validator_detects_overlapping_rooms():
    m = generate_map(8)
    a, b = m.rooms[0], m.rooms[1]
    b.x, b.y = a.x + 1, a.y + 1
    assert any("overlap" in e for e in validate_map(m))


def test_spawns_and_objectives_reachable_when_unpowered_and_powered():
    m = generate_map(9)
    pre = flood(m, m.spawns[:1], True)
    post = flood(m, m.spawns[:1], False)
    g = m.object_by_id["generator"]
    assert any(pre[y * m.width + x] for x, y in object_access_cells(m, g))
    tx = m.object_by_id["transmitter"]
    assert not any(pre[y * m.width + x] for x, y in object_access_cells(m, tx))   # restricted until power
    assert any(post[y * m.width + x] for x, y in object_access_cells(m, tx))
    for (x, y) in m.spawns:
        assert pre[y * m.width + x]


def test_doors_on_valid_openings():
    m = generate_map(10)
    for d in m.doors:
        for c in d.cells:
            assert m.tile(*c) == FLOOR
