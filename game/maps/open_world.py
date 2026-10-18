"""MAP 3: THE DEAD ZONE - an open-world outdoor map.

Walled outposts (rooms with doors) are scattered over a large open landscape of grass, wasteland, forests, rocks and
wrecks, linked by roads.  Nothing forces a route: you can wander anywhere, light campfires (respawn points), chase
supply drops and survive the nights.  The objective chain is the same signal chain, but its pieces are spread over
different outposts, so exploring in any order works.
"""
from __future__ import annotations

import random
from typing import Dict, List

from .generator import FLOOR, VOID, WALL, Interactable, MapData, Prop, RoomCtx, RoomSpec
from .research_station import ResearchStationGenerator

NAMES = {
    "hub": ["Survivor Camp"],
    "main_lab": ["Old Laboratory", "Abandoned Clinic Hall"],
    "server_wing": ["Command Bunker"],
    "lab": ["Field Lab {n}", "Radio Hut {n}"],
    "archive": ["Field Archive"],
    "security": ["Armory Outpost"],
    "storage": ["Warehouse {n}", "Supply Shed {n}"],
    "maintenance": ["Workshop {n}"],
    "generator": ["Pump Station"],
    "medical": ["Field Hospital"],
    "comms": ["Relay Tower"],
    "restricted": ["Sealed Bunker", "Forgotten Vault"],
    "quarters": ["Cabin {n}", "Farmhouse {n}", "Roadside Shack {n}"],
}
FLOOR_STYLE = {
    "hub": "concrete", "main_lab": "ow_metal", "server_wing": "ow_metal", "lab": "ow_wood", "archive": "ow_wood",
    "security": "ow_dark", "storage": "concrete", "maintenance": "ow_dark", "generator": "ow_dark",
    "medical": "concrete", "comms": "ow_metal", "restricted": "ow_dark", "quarters": "ow_wood",
}
ROAD = 255


class OpenWorldGenerator(ResearchStationGenerator):
    ROOM_NAMES = NAMES
    FLOORS = FLOOR_STYLE
    map_id = "open_world"
    map_name = "The Dead Zone"
    width = 210
    height = 150
    MIN_ROOMS = 30
    STUBS = False
    CLUSTER_SD = (18, 13)
    FAR_RANGE = (30, 56)
    EXTRA_EDGE_P = 0.5
    EXTRA_EDGE_DIST = 60

    # ---------------------------------------------------------------- plan
    def room_plan(self, rng: random.Random) -> List[RoomSpec]:
        counter: Dict[str, int] = {}

        def spec(kind, w, h, far=False, restricted=None):
            counter[kind] = counter.get(kind, 0) + 1
            name = rng.choice(self.ROOM_NAMES[kind]).format(n=f"{chr(64 + counter[kind])}-{rng.randint(1, 9)}")
            r = (kind in {"server_wing", "security", "comms", "restricted"}) if restricted is None else restricted
            return RoomSpec(kind, name, w, h, r, self.FLOORS[kind], far, 3 if kind in ("lab", "storage", "maintenance", "quarters") else 5)

        plan = [spec("hub", rng.randint(22, 26), rng.randint(15, 18)),
                spec("comms", rng.randint(14, 17), rng.randint(11, 14), far=True),
                spec("generator", rng.randint(10, 12), rng.randint(8, 10), far=True),
                spec("server_wing", rng.randint(14, 18), rng.randint(10, 13)),
                spec("archive", rng.randint(11, 14), rng.randint(8, 10)),
                spec("security", rng.randint(9, 12), rng.randint(7, 9)),
                spec("medical", rng.randint(11, 14), rng.randint(8, 11)),
                spec("restricted", rng.randint(9, 11), rng.randint(7, 9)),
                spec("main_lab", rng.randint(14, 18), rng.randint(10, 13))]
        tail = []
        for _ in range(rng.randint(5, 7)):
            tail.append(spec("lab", rng.randint(7, 10), rng.randint(6, 8)))
        for _ in range(rng.randint(5, 7)):
            tail.append(spec("storage", rng.randint(8, 12), rng.randint(6, 8)))
        for _ in range(rng.randint(3, 5)):
            tail.append(spec("maintenance", rng.randint(7, 9), rng.randint(6, 7)))
        for _ in range(rng.randint(12, 16)):
            tail.append(spec("quarters", rng.randint(6, 8), rng.randint(5, 7)))
        rng.shuffle(tail)
        return plan + tail

    # --------------------------------------------------------------- build
    def _build(self, rng, seed):
        m = super()._build(rng, seed)
        m.meta.update({"daynight": True, "light_tiles": 7.5, "ambient": 214, "room_range": [self.MIN_ROOMS, 64],
                       "zombie_cap": 85, "outdoor_packs": 13, "wander": True, "supply_drops": True, "reveal": 12})
        return m

    def _derive_walls(self, m: MapData) -> None:
        """Outposts get walls; everything else becomes open ground (roads are marked); map edge = cliffs."""
        W, H = m.width, m.height
        t = m.tiles
        for room in m.rooms:
            x0, y0, x1, y1 = room.footprint
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    if (x in (x0, x1) or y in (y0, y1)) and t[y * W + x] == VOID:
                        t[y * W + x] = WALL
        for i in range(W * H):
            if t[i] == VOID:
                t[i] = FLOOR
        for i, v in enumerate(self.corr):
            if v and t[i] == FLOOR and m.zone[i] == 0:
                m.zone[i] = ROAD
        B = 3
        for y in range(H):
            for x in range(W):
                if x < B or y < B or x >= W - B or y >= H - B:
                    t[y * W + x] = WALL
                    m.zone[y * W + x] = 0

    # ------------------------------------------------------------ dressing
    def _dress_hub(self, m, rng, ctx):
        r = ctx.room
        self._wall_props(m, rng, ctx, "tent", 3, 2, 2, oriented=False)
        self._wall_props(m, rng, ctx, "sandbags", 5)
        self._wall_props(m, rng, ctx, "crate_wood_large", 3)
        self._wall_props(m, rng, ctx, "barrel_orange", 2)
        self._island_props(m, rng, ctx, ["sandbags", "crate_wood_b"], 3, 1, 1, margin=3)

    def _dress_quarters(self, m, rng, ctx):
        super()._dress_quarters(m, rng, ctx)

    # ------------------------------------------------------------- finish
    def finish(self, m: MapData, rng: random.Random, ctxs: Dict[int, RoomCtx]) -> None:
        super().finish(m, rng, ctxs)
        self._scatter(m, rng)

    def _scatter(self, m: MapData, rng: random.Random) -> None:
        W, H = m.width, m.height
        occ = bytearray(W * H)      # cells where scenery must not go

        def mark(x0, y0, x1, y1):
            for y in range(max(0, y0), min(H - 1, y1) + 1):
                for x in range(max(0, x0), min(W - 1, x1) + 1):
                    occ[y * W + x] = 1

        for r in m.rooms:
            x0, y0, x1, y1 = r.footprint
            mark(x0 - 2, y0 - 2, x1 + 2, y1 + 2)
        for d in m.doors:
            for (cx, cy) in d.cells:
                mark(cx - 3, cy - 3, cx + 3, cy + 3)
        for i, v in enumerate(self.corr):
            if v:
                x, y = i % W, i // W
                mark(x - 1, y - 1, x + 1, y + 1)
        mark(0, 0, W - 1, 7)
        mark(0, H - 8, W - 1, H - 1)
        mark(0, 0, 7, H - 1)
        mark(W - 8, 0, W - 1, H - 1)
        for p in m.props:
            mark(p.x - 1, p.y - 1, p.x + p.w, p.y + p.h)

        def free(x, y, w, h):
            if x < 4 or y < 4 or x + w >= W - 4 or y + h >= H - 4:
                return False
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    i = yy * W + xx
                    if occ[i] or m.tiles[i] != FLOOR or m.zone[i] != 0:
                        return False
            return True

        def put(sprite, x, y, w, h, solid=True):
            m.props.append(Prop(sprite, x, y, w, h, 0, solid))
            mark(x - 1, y - 1, x + w, y + h)

        # forests: dense clusters of trees (these make big areas feel different from open fields)
        for _ in range(rng.randint(14, 20)):
            cx, cy = rng.randint(14, W - 14), rng.randint(14, H - 14)
            for _k in range(rng.randint(14, 34)):
                x, y = int(rng.gauss(cx, 7)), int(rng.gauss(cy, 5))
                r = rng.random()
                if r < 0.45 and free(x, y, 2, 2):
                    put("tree_a" if rng.random() < 0.5 else "tree_b", x, y, 2, 2)
                elif r < 0.8 and free(x, y, 1, 1):
                    put("dead_tree", x, y, 1, 1)
                elif free(x, y, 1, 1):
                    put("rock_a", x, y, 1, 1)
        # scattered rocks and boulders
        for _ in range(110):
            x, y = rng.randint(6, W - 8), rng.randint(6, H - 8)
            if rng.random() < 0.7 and free(x, y, 1, 1):
                put("rock_a", x, y, 1, 1)
            elif free(x, y, 2, 1):
                put("rock_b", x, y, 2, 1)
        # wrecked cars next to roads
        road_cells = [(i % W, i // W) for i, v in enumerate(self.corr) if v]
        for _ in range(40):
            if not road_cells:
                break
            cx, cy = rng.choice(road_cells)
            for dx, dy in ((0, -4), (0, 4), (4, 0), (-5, 0)):
                if free(cx + dx, cy + dy, 2, 1):
                    put("car_wreck", cx + dx, cy + dy, 2, 1)
                    break
        # campfires (interactive respawn points) with a tent or two, spread over the map
        hub = m.rooms[m.meta["hub_room"]]
        camps: List[tuple] = []
        hx, hy = hub.center
        for _ in range(900):
            if len(camps) >= 6:
                break
            x, y = rng.randint(14, W - 16), rng.randint(14, H - 16)
            if abs(x - hx) + abs(y - hy) < 45 or any(abs(x - c[0]) + abs(y - c[1]) < 55 for c in camps):
                continue
            if free(x, y, 6, 6):
                camps.append((x, y))
        for i, (x, y) in enumerate(camps):
            m.objects.append(Interactable(f"camp_{i}", "camp", "camp", x + 2, y + 2, 1, 1, 0, -1, "CAMPFIRE (set respawn)"))
            mark(x - 1, y - 1, x + 7, y + 7)
            if free(x, y, 2, 2):
                put("tent", x, y, 2, 2)
            if free(x + 4, y + 3, 2, 2):
                put("tent", x + 4, y + 3, 2, 2)
            if free(x + 4, y, 1, 1):
                put("sandbags", x + 4, y, 1, 1)
        # a camp inside the survivor compound too
        taken = set()
        for p in m.props:
            taken.update((xx, yy) for yy in range(p.y, p.y + p.h) for xx in range(p.x, p.x + p.w))
        for o in m.objects:
            taken.update((xx, yy) for yy in range(o.y, o.y + o.h) for xx in range(o.x, o.x + o.w))
        hctx_cells = [(x, y) for y in range(hub.y + 3, hub.y + hub.h - 3) for x in range(hub.x + 3, hub.x + hub.w - 3)
                      if (x, y) not in taken and m.tiles[y * W + x] == FLOOR]
        rng.shuffle(hctx_cells)
        spawn_set = {tuple(s) for s in m.spawns}
        for (x, y) in hctx_cells:
            if (x, y) in spawn_set:
                continue
            m.objects.append(Interactable("camp_home", "camp", "camp", x, y, 1, 1, 0, hub.id, "CAMPFIRE (set respawn)"))
            break
        m.meta["camps"] = [o.id for o in m.objects if o.kind == "camp"]
