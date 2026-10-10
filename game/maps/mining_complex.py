"""MAP 2: UNDERGROUND MINING COMPLEX.

Reuses the whole generation framework (rooms, corridors, doors, validation, objectives, weapon crates ...) and only
supplies a different room naming / floor palette / dressing, a darker mood and its own tileset overlay
(assets/maps/mining_complex).
"""
from __future__ import annotations

import random

from .generator import MapData, RoomCtx
from .research_station import ResearchStationGenerator

NAMES = {
    "hub": ["Main Shaft Station"],
    "main_lab": ["Ore Processing Hall", "Crusher Hall"],
    "server_wing": ["Control Room"],
    "lab": ["Geology Lab {n}", "Assay Office {n}"],
    "archive": ["Survey Archive"],
    "security": ["Blast Vault Security"],
    "storage": ["Ore Store {n}", "Powder Store {n}"],
    "maintenance": ["Tunnel Section {n}"],
    "generator": ["Pump House"],
    "medical": ["Mine Infirmary"],
    "comms": ["Surface Relay Chamber"],
    "restricted": ["Collapsed Annex", "Sealed Drift"],
    "quarters": ["Miners' Bunks {n}", "Foreman's Office {n}", "Mess Hall {n}"],
}
FLOOR = {
    "hub": "rock", "main_lab": "mine_metal", "server_wing": "mine_metal", "lab": "mine_wood", "archive": "mine_wood",
    "security": "mine_dark", "storage": "dirt_1", "maintenance": "mine_dark", "generator": "mine_dark",
    "medical": "mine_wood", "comms": "mine_metal", "restricted": "mine_dark", "quarters": "mine_wood",
}


class MiningComplexGenerator(ResearchStationGenerator):
    ROOM_NAMES = NAMES
    FLOORS = FLOOR
    map_id = "mining_complex"
    map_name = "Underground Mining Complex"
    width = 190
    height = 130

    def _build(self, rng, seed):
        m = super()._build(rng, seed)
        m.meta["light_tiles"] = 7.2      # darker, tighter lantern light than the research station
        m.meta["ambient"] = 244
        return m

    # --- dressing with mining props (sprites live in the mining tileset overlay)
    def _dress_hub(self, m, rng, ctx):
        r = ctx.room
        for y in range(r.y + 3, r.y + r.h - 3, 6):
            for x in range(r.x + 4, r.x + r.w - 4, 6):
                if rng.random() < 0.55 and not (abs(x - (r.x + r.w // 2)) < 4 and abs(y - (r.y + r.h // 2)) < 3):
                    self._add_prop(m, ctx, "beam", x, y)
        self._wall_props(m, rng, ctx, "ore_cart", 2, 2, 1)
        self._wall_props(m, rng, ctx, "lantern", 4, 1, 1)
        self._wall_props(m, rng, ctx, "locker", 1)

    def _dress_main_lab(self, m, rng, ctx):
        self._island_props(m, rng, ctx, ["drill"], 1, 2, 2, margin=3)
        self._wall_props(m, rng, ctx, "ore_cart", 3, 2, 1)
        self._wall_props(m, rng, ctx, "ore_pile", 4)
        self._wall_props(m, rng, ctx, "electrical_panel", 2)
        self._wall_props(m, rng, ctx, "lantern", 3)

    def _dress_storage(self, m, rng, ctx):
        self._wall_props(m, rng, ctx, "tnt_crate", rng.randint(2, 5))
        self._wall_props(m, rng, ctx, "ore_pile", rng.randint(2, 4))
        self._wall_props(m, rng, ctx, "crate_wood_large", 3)
        self._island_props(m, rng, ctx, ["ore_cart"], 1, 2, 1, margin=2)
        self._wall_props(m, rng, ctx, "lantern", 2)

    def _dress_maintenance(self, m, rng, ctx):
        self._wall_props(m, rng, ctx, "pipe_straight", rng.randint(2, 5))
        self._wall_props(m, rng, ctx, "beam", 3)
        self._wall_props(m, rng, ctx, "electrical_panel", 1)
        self._wall_props(m, rng, ctx, "lantern", 2)
        self._island_props(m, rng, ctx, ["barrel_orange", "tnt_crate"], 2, 1, 1, margin=2)

    def _dress_generator(self, m, rng, ctx):
        self._island_props(m, rng, ctx, ["pump"], 1, 2, 2, margin=3)
        self._wall_props(m, rng, ctx, "pipe_valve", 2)
        self._wall_props(m, rng, ctx, "pipe_straight", 3)
        self._wall_props(m, rng, ctx, "battery_bank", 2, 2, 1)
        self._wall_props(m, rng, ctx, "lantern", 2)

    def _dress_quarters(self, m, rng, ctx):
        r = ctx.room
        if rng.random() < 0.7:
            s, bw, bh = rng.choice([("bed_orange_single", 1, 3), ("bed_green_double", 2, 3)])
            self._add_prop(m, ctx, s, r.x + rng.randint(0, max(0, r.w - bw - 1)), r.y, bw, min(bh, r.h - 3) if r.h > 4 else bh)
        self._wall_props(m, rng, ctx, "locker", 1)
        self._wall_props(m, rng, ctx, "desk_wood", 1, 3, 1)
        self._wall_props(m, rng, ctx, "lantern", 2)

    def _dress_restricted(self, m, rng, ctx):
        self._wall_props(m, rng, ctx, "tnt_crate", 4)
        self._wall_props(m, rng, ctx, "crate_metal", 3)
        self._wall_props(m, rng, ctx, "ore_pile", 3)
        self._wall_props(m, rng, ctx, "lantern", 2)
