"""Player model (server side authoritative record + client mirror)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .config import PLAYER_COLORS


@dataclass
class Player:
    pid: int
    name: str
    x: float = 0.0
    y: float = 0.0
    mx: float = 0.0          # last validated movement input (-1..1)
    my: float = 0.0
    face: float = 0.0        # facing angle in radians
    connected: bool = True
    token: str = ""
    char: int = 0
    last_input_t: float = 0.0
    notes: List[dict] = field(default_factory=list)
    transmit_ready_at: float = 0.0
    # combat
    hp: float = 100.0
    max_hp: float = 100.0
    aim: float = 0.0
    fire: bool = False
    next_shot: float = 0.0
    reload_until: float = 0.0
    dead_until: float = 0.0
    dead: bool = False
    invuln_until: float = 0.0
    last_damage: float = -99.0
    kills: int = 0
    deaths: int = 0
    cur: str = "pistol"
    inv: dict = field(default_factory=lambda: {"pistol": 12})     # owned weapon -> rounds in clip
    reserve: dict = field(default_factory=lambda: {"pistol": None})  # spare ammo (None = infinite)
    heal_ready_at: float = 0.0
    scan_ready_at: float = 0.0

    @property
    def ammo(self) -> int:
        return self.inv.get(self.cur, 0)

    @ammo.setter
    def ammo(self, v: int) -> None:
        self.inv[self.cur] = int(v)

    @property
    def clip(self) -> int:
        from .weapons import WEAPONS
        return WEAPONS[self.cur]["clip"]

    @property
    def color(self):
        return PLAYER_COLORS[(self.pid - 1) % len(PLAYER_COLORS)]

    @property
    def moving(self) -> bool:
        return abs(self.mx) > 0.01 or abs(self.my) > 0.01
