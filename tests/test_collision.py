from game.collision import blocked_rect, move_with_collision
from game.config import PLAYER_HALF, TILE


def wall_at(tx, ty):
    return tx >= 5 or tx < 0 or ty < 0 or ty >= 5


def test_cannot_walk_through_wall():
    x, y = 2.5 * TILE, 2.5 * TILE
    for _ in range(200):
        x, y = move_with_collision(wall_at, x, y, 20, 0, PLAYER_HALF)
    assert x + PLAYER_HALF <= 5 * TILE + 1e-6


def test_wall_sliding():
    x, y = 4.0 * TILE, 2.5 * TILE
    nx, ny = move_with_collision(wall_at, x, y, 50, 30, PLAYER_HALF)
    assert ny > y and nx <= 5 * TILE - PLAYER_HALF + 1e-6


def test_no_tunnelling_with_huge_step():
    x, y = 3.0 * TILE, 2.5 * TILE
    nx, ny = move_with_collision(wall_at, x, y, 1000, 0, PLAYER_HALF)
    assert nx + PLAYER_HALF <= 5 * TILE + 1e-6


def test_free_move():
    nx, ny = move_with_collision(wall_at, 160, 160, 10, 10, PLAYER_HALF)
    assert (nx, ny) == (170, 170)


def test_blocked_rect_corner():
    assert blocked_rect(wall_at, 5 * TILE + 1, 100, PLAYER_HALF)
