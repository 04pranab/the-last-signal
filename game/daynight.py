"""Day / night cycle shared by the server (zombie behaviour) and the client (lighting)."""
from __future__ import annotations

import math

DAY_LENGTH = 420.0      # seconds for a full day (7 minutes)
START_PHASE = 0.22      # the game starts in the morning


def phase(t: float) -> float:
    return ((t / DAY_LENGTH) + START_PHASE) % 1.0


def daylight(t: float) -> float:
    """0.0 = deepest night, 1.0 = full day (smooth)."""
    p = phase(t)
    v = 0.5 + 0.5 * math.cos(2 * math.pi * (p - 0.38))
    return max(0.0, min(1.0, (v - 0.12) / 0.7))


def label(t: float) -> str:
    d = daylight(t)
    p = phase(t)
    if d > 0.72:
        return "DAY"
    if d < 0.2:
        return "NIGHT"
    return "DUSK" if p > 0.38 else "DAWN"
