"""Interaction helpers: which interactable (if any) a position can use."""
from __future__ import annotations

import math
from typing import Optional

from .config import INTERACT_RANGE, TILE
from .maps.generator import Interactable, MapData


def distance_to_object(o: Interactable, px: float, py: float) -> float:
    """Distance from a point to the object's rectangle (pixels)."""
    x0, y0 = o.x * TILE, o.y * TILE
    x1, y1 = (o.x + o.w) * TILE, (o.y + o.h) * TILE
    dx = max(x0 - px, 0, px - x1)
    dy = max(y0 - py, 0, py - y1)
    return math.hypot(dx, dy)


def can_interact(o: Interactable, px: float, py: float) -> bool:
    return distance_to_object(o, px, py) <= INTERACT_RANGE * 0.6


def nearest_interactable(m: MapData, px: float, py: float) -> Optional[Interactable]:
    best, bd = None, 1e9
    tx, ty = int(px // TILE), int(py // TILE)
    for o in m.objects:
        if o.x - 4 <= tx <= o.x + o.w + 4 and o.y - 4 <= ty <= o.y + o.h + 4:
            d = distance_to_object(o, px, py)
            if d <= INTERACT_RANGE * 0.6 and d < bd:
                best, bd = o, d
    return best
