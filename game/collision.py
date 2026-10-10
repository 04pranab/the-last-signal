"""Tile based AABB collision shared by the server (authoritative) and the client (prediction)."""
from __future__ import annotations

import math
from typing import Callable

from .config import TILE


def blocked_rect(solid_at: Callable[[int, int], bool], cx: float, cy: float, half: float) -> bool:
    x0 = int(math.floor((cx - half) / TILE))
    x1 = int(math.floor((cx + half - 1e-6) / TILE))
    y0 = int(math.floor((cy - half) / TILE))
    y1 = int(math.floor((cy + half - 1e-6) / TILE))
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            if solid_at(tx, ty):
                return True
    return False


def move_with_collision(solid_at, x: float, y: float, dx: float, dy: float, half: float):
    """Move an axis aligned box by (dx, dy), resolving each axis separately (wall sliding)."""
    # split long moves so a fast player can never tunnel through a thin wall
    dist = max(abs(dx), abs(dy))
    steps = max(1, int(dist // (TILE * 0.4)) + 1)
    sx, sy = dx / steps, dy / steps
    for _ in range(steps):
        if sx:
            nx = x + sx
            if not blocked_rect(solid_at, nx, y, half):
                x = nx
            else:
                # snap flush against the obstacle
                if sx > 0:
                    tx = int(math.floor((nx + half - 1e-6) / TILE))
                    x = min(x, tx * TILE - half)
                else:
                    tx = int(math.floor((nx - half) / TILE))
                    x = max(x, (tx + 1) * TILE + half)
                if blocked_rect(solid_at, x, y, half):
                    x -= sx
        if sy:
            ny = y + sy
            if not blocked_rect(solid_at, x, ny, half):
                y = ny
            else:
                if sy > 0:
                    ty = int(math.floor((ny + half - 1e-6) / TILE))
                    y = min(y, ty * TILE - half)
                else:
                    ty = int(math.floor((ny - half) / TILE))
                    y = max(y, (ty + 1) * TILE + half)
                if blocked_rect(solid_at, x, y, half):
                    y -= sy
    return x, y
