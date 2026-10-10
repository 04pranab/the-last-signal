"""Map data model and the reusable procedural-generation framework.

A concrete map (e.g. the research station) subclasses :class:`BaseMapGenerator`
and supplies a room plan, room dressing and objective/clue placement.  The base
class owns the generic, map independent work: room packing, corridor routing,
doors, wall derivation, validation/retry loop and (de)serialisation.
"""
from __future__ import annotations

import base64
import heapq
import random
import zlib
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

VOID, FLOOR, WALL = 0, 1, 2
PAYLOAD_VERSION = 1


class GenerationError(Exception):
    pass


# --------------------------------------------------------------- data model
@dataclass
class Room:
    id: int
    kind: str
    name: str
    x: int
    y: int
    w: int
    h: int
    restricted: bool = False
    floor: str = "teal"
    doors: List[int] = field(default_factory=list)

    @property
    def center(self) -> Tuple[float, float]:
        return (self.x + self.w / 2.0, self.y + self.h / 2.0)

    @property
    def footprint(self) -> Tuple[int, int, int, int]:
        """x0, y0, x1, y1 (inclusive) of interior plus the surrounding wall ring."""
        return (self.x - 1, self.y - 1, self.x + self.w, self.y + self.h)

    def contains(self, cx: int, cy: int) -> bool:
        return self.x <= cx < self.x + self.w and self.y <= cy < self.y + self.h


@dataclass
class Door:
    id: int
    x: int
    y: int
    vertical: bool          # True: door lies in an E/W wall and spans two rows
    rooms: List[int]        # rooms this door belongs to (the room it opens into)
    restricted: bool = False

    @property
    def cells(self) -> List[Tuple[int, int]]:
        return [(self.x, self.y), (self.x, self.y + 1)] if self.vertical else [(self.x, self.y), (self.x + 1, self.y)]


@dataclass
class Prop:
    sprite: str
    x: int
    y: int
    w: int = 1
    h: int = 1
    rot: int = 0
    solid: bool = True


@dataclass
class Interactable:
    id: str
    kind: str            # terminal | generator | core | transmitter
    family: str          # sprite family (terminal, archive, console_security, medical, generator ...)
    x: int
    y: int
    w: int = 1
    h: int = 1
    rot: int = 0
    room: int = 0
    label: str = "TERMINAL"
    needs_power: bool = False


class MapData:
    """All static information about one generated map."""

    def __init__(self, width: int, height: int, seed: int, name: str, map_id: str):
        self.width = width
        self.height = height
        self.seed = seed
        self.name = name
        self.map_id = map_id
        self.tiles = bytearray(width * height)
        self.zone = bytearray(width * height)   # room id + 1 (0 = corridor / void)
        self.rooms: List[Room] = []
        self.doors: List[Door] = []
        self.props: List[Prop] = []
        self.objects: List[Interactable] = []
        self.spawns: List[Tuple[int, int]] = []
        self.meta: Dict[str, object] = {}
        self.secret: Dict[str, object] = {}     # server only: answers & clue texts
        self.attempts = 1
        # derived
        self.solid = bytearray(width * height)
        self.door_at: Dict[Tuple[int, int], int] = {}
        self.object_by_id: Dict[str, Interactable] = {}

    # ---- helpers
    def idx(self, x: int, y: int) -> int:
        return y * self.width + x

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def tile(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.tiles[y * self.width + x]
        return VOID

    def finalize(self) -> None:
        """Compute derived collision data."""
        w, h = self.width, self.height
        self.solid = bytearray(w * h)
        for i, t in enumerate(self.tiles):
            self.solid[i] = 0 if t == FLOOR else 1
        for p in self.props:
            if p.solid:
                for yy in range(p.y, p.y + p.h):
                    for xx in range(p.x, p.x + p.w):
                        if 0 <= xx < w and 0 <= yy < h:
                            self.solid[yy * w + xx] = 1
        for o in self.objects:
            for yy in range(o.y, o.y + o.h):
                for xx in range(o.x, o.x + o.w):
                    if 0 <= xx < w and 0 <= yy < h:
                        self.solid[yy * w + xx] = 1
        self.door_at = {}
        for d in self.doors:
            for c in d.cells:
                self.door_at[c] = d.id
        self.object_by_id = {o.id: o for o in self.objects}

    # ---- (de)serialisation of the public (client visible) part
    def to_payload(self) -> dict:
        return {
            "v": PAYLOAD_VERSION,
            "map_id": self.map_id,
            "name": self.name,
            "seed": self.seed,
            "w": self.width,
            "h": self.height,
            "tiles": base64.b64encode(zlib.compress(bytes(self.tiles), 6)).decode("ascii"),
            "zone": base64.b64encode(zlib.compress(bytes(self.zone), 6)).decode("ascii"),
            "rooms": [asdict(r) for r in self.rooms],
            "doors": [asdict(d) for d in self.doors],
            "props": [[p.sprite, p.x, p.y, p.w, p.h, p.rot, 1 if p.solid else 0] for p in self.props],
            "objects": [asdict(o) for o in self.objects],
            "spawns": [list(s) for s in self.spawns],
            "meta": self.meta,
        }

    @classmethod
    def from_payload(cls, p: dict) -> "MapData":
        w, h = int(p["w"]), int(p["h"])
        if not (8 <= w <= 600 and 8 <= h <= 600):
            raise ValueError("bad map size")
        m = cls(w, h, int(p["seed"]), str(p["name"]), str(p.get("map_id", "")))
        m.tiles = bytearray(zlib.decompress(base64.b64decode(p["tiles"])))
        m.zone = bytearray(zlib.decompress(base64.b64decode(p["zone"])))
        if len(m.tiles) != w * h or len(m.zone) != w * h:
            raise ValueError("bad map data size")
        m.rooms = [Room(**r) for r in p["rooms"]]
        m.doors = [Door(**d) for d in p["doors"]]
        m.props = [Prop(sprite=a[0], x=a[1], y=a[2], w=a[3], h=a[4], rot=a[5], solid=bool(a[6])) for a in p["props"]]
        m.objects = [Interactable(**o) for o in p["objects"]]
        m.spawns = [tuple(s) for s in p["spawns"]]
        m.meta = dict(p.get("meta", {}))
        m.finalize()
        return m


# --------------------------------------------------------------- room plan
@dataclass
class RoomSpec:
    kind: str
    name: str
    w: int
    h: int
    restricted: bool = False
    floor: str = "teal"
    far_from_hub: bool = False
    gap: int = 3


# --------------------------------------------------------------- room ctx
class RoomCtx:
    """Occupancy helper used while dressing a room with props."""

    def __init__(self, m: MapData, room: Room, rng: random.Random):
        self.m, self.room, self.rng = m, room, rng
        self.blocked = set()
        self.reserved = set()
        self._compute_lanes()

    def _compute_lanes(self) -> None:
        r = self.room
        for did in r.doors:
            d = self.m.doors[did]
            for (cx, cy) in d.cells:
                # step inwards up to 2 cells
                for step in (1, 2):
                    if cy == r.y - 1:
                        c = (cx, cy + step)
                    elif cy == r.y + r.h:
                        c = (cx, cy - step)
                    elif cx == r.x - 1:
                        c = (cx + step, cy)
                    else:
                        c = (cx - step, cy)
                    self.reserved.add(c)
                    # widen the lane by one on each side
                    if d.vertical:
                        self.reserved.add((c[0], c[1] - 1))
                        self.reserved.add((c[0], c[1] + 1))
                    else:
                        self.reserved.add((c[0] - 1, c[1]))
                        self.reserved.add((c[0] + 1, c[1]))

    def interior(self) -> List[Tuple[int, int]]:
        r = self.room
        return [(x, y) for y in range(r.y, r.y + r.h) for x in range(r.x, r.x + r.w)]

    def _door_inside_cells(self) -> List[Tuple[int, int]]:
        r, out = self.room, []
        for did in r.doors:
            for (cx, cy) in self.m.doors[did].cells:
                if cy == r.y - 1:
                    out.append((cx, cy + 1))
                elif cy == r.y + r.h:
                    out.append((cx, cy - 1))
                elif cx == r.x - 1:
                    out.append((cx + 1, cy))
                else:
                    out.append((cx - 1, cy))
        return out

    def _connected(self, extra) -> bool:
        r = self.room
        blocked = self.blocked | extra
        starts = [c for c in self._door_inside_cells() if c not in blocked]
        if not starts:
            return False
        total = r.w * r.h - len(blocked)
        seen = {starts[0]}
        stack = [starts[0]]
        while stack:
            x, y = stack.pop()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) in seen or (nx, ny) in blocked or not r.contains(nx, ny):
                    continue
                seen.add((nx, ny))
                stack.append((nx, ny))
        if len(seen) != total:
            return False
        return all(c in seen or c in blocked for c in starts)

    def footprint(self, x, y, w, h):
        return [(xx, yy) for yy in range(y, y + h) for xx in range(x, x + w)]

    def can_place(self, x, y, w, h, access=False, allow_reserved=False) -> bool:
        r = self.room
        cells = self.footprint(x, y, w, h)
        for c in cells:
            if not r.contains(*c) or c in self.blocked:
                return False
            if not allow_reserved and c in self.reserved:
                return False
        if len(self.blocked) + len(cells) > 0.42 * r.w * r.h:
            return False
        if access:
            ok = False
            cs = set(cells)
            for (cx, cy) in cells:
                for n in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if n not in cs and r.contains(*n) and n not in self.blocked:
                        ok = True
            if not ok:
                return False
        return self._connected(set(cells))

    def place(self, x, y, w, h, access=False, allow_reserved=False) -> bool:
        if self.can_place(x, y, w, h, access, allow_reserved):
            self.blocked.update(self.footprint(x, y, w, h))
            return True
        return False

    def wall_spots(self, w: int, h: int):
        """Positions flush against a wall: yields (x, y, rot, fw, fh)."""
        r = self.room
        spots = []
        for x in range(r.x, r.x + r.w - w + 1):
            spots.append((x, r.y, 0, w, h))                       # north wall, faces south
            spots.append((x, r.y + r.h - h, 2, w, h))             # south wall
        for y in range(r.y, r.y + r.h - w + 1):
            spots.append((r.x, y, 1, h, w))                       # west wall, rot 90
            spots.append((r.x + r.w - h, y, 3, h, w))             # east wall, rot 270
        self.rng.shuffle(spots)
        return spots

    def free_cells(self):
        return [c for c in self.interior() if c not in self.blocked]


# --------------------------------------------------------------- generator
class BaseMapGenerator:
    """Template-method generator.  Subclasses override the hook methods."""

    map_id = "base"
    map_name = "Base Map"
    width = 200
    height = 130
    max_attempts = 25

    # ---- hooks
    def room_plan(self, rng: random.Random) -> List[RoomSpec]:
        raise NotImplementedError

    def dress_room(self, m: MapData, rng: random.Random, ctx: RoomCtx) -> None:
        pass

    def finish(self, m: MapData, rng: random.Random, ctxs: Dict[int, RoomCtx]) -> None:
        pass

    def restricted_kinds(self) -> set:
        return set()

    # ---- public API
    def generate(self, seed: int):
        from .validator import validate_map
        last_errors: List[str] = []
        for attempt in range(self.max_attempts):
            rng = random.Random((int(seed) * 1_000_003 + attempt * 7919) & 0xFFFFFFFF)
            try:
                m = self._build(rng, int(seed))
            except GenerationError as e:
                last_errors = [str(e)]
                continue
            errors = validate_map(m)
            if not errors:
                m.attempts = attempt + 1
                return m
            last_errors = errors
        raise GenerationError(f"could not generate a valid map for seed {seed}: {last_errors[:3]}")

    # ---- build pipeline
    def _build(self, rng: random.Random, seed: int) -> MapData:
        W, H = self.width, self.height
        m = MapData(W, H, seed, self.map_name, self.map_id)
        self.occ = bytearray(W * H)       # room footprints
        self.near = bytearray(W * H)      # dilated footprints (corridor cost)
        self.corr = bytearray(W * H)      # corridor cells
        plan = self.room_plan(rng)
        self._place_rooms(m, rng, plan)
        self._connect(m, rng)
        self._stubs(m, rng)
        self._derive_walls(m)
        m.finalize()
        ctxs: Dict[int, RoomCtx] = {}
        for room in m.rooms:
            ctx = RoomCtx(m, room, rng)
            ctxs[room.id] = ctx
            self.dress_room(m, rng, ctx)
        self.finish(m, rng, ctxs)
        m.finalize()
        return m

    # ---- rooms
    def _place_rooms(self, m: MapData, rng: random.Random, plan: List[RoomSpec]) -> None:
        W, H = m.width, m.height
        centers = [(rng.randint(30, W - 30), rng.randint(25, H - 25)) for _ in range(rng.randint(4, 6))]
        hub_center = (W // 2 + rng.randint(-25, 25), H // 2 + rng.randint(-15, 15))
        hub_spec_done = False
        placed: List[Room] = []
        for spec in plan:
            ok = False
            for _try in range(400):
                if spec.kind == "hub" and not hub_spec_done:
                    cx, cy = hub_center
                    px, py = cx + rng.randint(-6, 6) - spec.w // 2, cy + rng.randint(-4, 4) - spec.h // 2
                elif spec.far_from_hub and placed and rng.random() < 0.85:
                    hub = placed[0]
                    ang_x = rng.choice((-1, 1))
                    px = int(hub.x + hub.w / 2 + ang_x * rng.randint(45, 80) - spec.w / 2)
                    py = int(hub.y + hub.h / 2 + rng.randint(-45, 45) - spec.h / 2)
                elif rng.random() < 0.7:
                    cx, cy = rng.choice(centers)
                    px = int(rng.gauss(cx, 22)) - spec.w // 2
                    py = int(rng.gauss(cy, 14)) - spec.h // 2
                else:
                    px = rng.randint(4, W - spec.w - 5)
                    py = rng.randint(4, H - spec.h - 5)
                if px < 3 or py < 3 or px + spec.w > W - 4 or py + spec.h > H - 4:
                    continue
                gap = spec.gap if rng.random() < 0.7 else spec.gap + 1
                x0, y0, x1, y1 = px - 1 - gap, py - 1 - gap, px + spec.w + gap, py + spec.h + gap
                if self._area_used(m, x0, y0, x1, y1):
                    continue
                room = Room(len(m.rooms), spec.kind, spec.name, px, py, spec.w, spec.h, spec.restricted, spec.floor)
                m.rooms.append(room)
                placed.append(room)
                self._stamp_room(m, room)
                ok = True
                if spec.kind == "hub":
                    hub_spec_done = True
                break
            if not ok:
                if spec.kind in self.required_kinds():
                    raise GenerationError(f"could not place required room {spec.kind}")
        if len(m.rooms) < 25:
            raise GenerationError("too few rooms placed")

    def required_kinds(self) -> set:
        return set()

    def _area_used(self, m, x0, y0, x1, y1) -> bool:
        W, H = m.width, m.height
        for y in range(max(0, y0), min(H - 1, y1) + 1):
            row = y * W
            for x in range(max(0, x0), min(W - 1, x1) + 1):
                if self.occ[row + x]:
                    return True
        return False

    def _stamp_room(self, m: MapData, room: Room) -> None:
        W = m.width
        x0, y0, x1, y1 = room.footprint
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.occ[y * W + x] = 1
        for y in range(y0 - 1, y1 + 2):
            for x in range(x0 - 1, x1 + 2):
                if 0 <= x < W and 0 <= y < m.height:
                    self.near[y * W + x] = 1
        for y in range(room.y, room.y + room.h):
            for x in range(room.x, room.x + room.w):
                m.tiles[y * W + x] = FLOOR
                m.zone[y * W + x] = room.id + 1

    # ---- connectivity
    def _connect(self, m: MapData, rng: random.Random) -> None:
        restricted = [r for r in m.rooms if r.restricted]
        open_rooms = [r for r in m.rooms if not r.restricted]

        def dist(a: Room, b: Room) -> float:
            return abs(a.center[0] - b.center[0]) + abs(a.center[1] - b.center[1])

        # Prim MST over open rooms with noisy weights
        in_tree = {open_rooms[0].id}
        edges: List[Tuple[Room, Room]] = []
        noise = {}
        while len(in_tree) < len(open_rooms):
            best = None
            for a in open_rooms:
                if a.id not in in_tree:
                    continue
                for b in open_rooms:
                    if b.id in in_tree:
                        continue
                    key = (min(a.id, b.id), max(a.id, b.id))
                    if key not in noise:
                        noise[key] = rng.uniform(0.8, 1.35)
                    wgt = dist(a, b) * noise[key]
                    if best is None or wgt < best[0]:
                        best = (wgt, a, b)
            _, a, b = best
            in_tree.add(b.id)
            edges.append((a, b))
        used = {(min(a.id, b.id), max(a.id, b.id)) for a, b in edges}
        # extra loop edges between nearby open rooms
        extra = []
        for a in open_rooms:
            near = sorted((b for b in open_rooms if b.id != a.id), key=lambda b: dist(a, b))[:3]
            for b in near:
                key = (min(a.id, b.id), max(a.id, b.id))
                if key not in used and dist(a, b) < 70 and rng.random() < 0.22:
                    used.add(key)
                    extra.append((a, b))
        # restricted rooms attach as leaves (one door; sometimes a second to another open room)
        leaf = []
        for r in restricted:
            cands = sorted(open_rooms, key=lambda b: dist(r, b))[:4]
            leaf.append((r, cands[0]))
            if len(cands) > 1 and rng.random() < 0.5:
                leaf.append((r, rng.choice(cands[1:])))
        for a, b in edges:
            wdt = 3 if (min(a.w, b.w) >= 10 and rng.random() < 0.7) else 2
            if not self._link(m, rng, a, b, wdt):
                raise GenerationError("mst link failed")
        for a, b in extra:
            self._link(m, rng, a, b, 2)
        first = True
        for r, b in leaf:
            ok = self._link(m, rng, r, b, 2)
            if first and not ok:
                raise GenerationError("restricted link failed")
            first = False
        for r in restricted:
            if not r.doors:
                raise GenerationError("restricted room without door")

    def _link(self, m: MapData, rng: random.Random, a: Room, b: Room, width: int) -> bool:
        da = self._choose_door(m, rng, a, b.center)
        if da is None:
            return False
        db = self._choose_door(m, rng, b, a.center, reserve=da)
        if db is None:
            return False
        path = self._route(m, rng, da["anchor"], db["anchor"])
        if path is None:
            return False
        W = m.width
        self._commit_door(m, a, da)
        self._commit_door(m, b, db)
        for (x, y) in path:
            for dx in range(width):
                for dy in range(width):
                    cx, cy = x + dx, y + dy
                    if 0 < cx < W - 1 and 0 < cy < m.height - 1 and not self.occ[cy * W + cx]:
                        m.tiles[cy * W + cx] = FLOOR
                        self.corr[cy * W + cx] = 1
        return True

    def _choose_door(self, m, rng, room: Room, target, reserve=None):
        tx, ty = target
        cx, cy = room.center
        dx, dy = tx - cx, ty - cy
        sides = []
        if abs(dx) * room.h >= abs(dy) * room.w:
            sides = ["E", "W"] if dx > 0 else ["W", "E"]
            sides += ["S", "N"] if dy > 0 else ["N", "S"]
        else:
            sides = ["S", "N"] if dy > 0 else ["N", "S"]
            sides += ["E", "W"] if dx > 0 else ["W", "E"]
        existing = [m.doors[i] for i in room.doors]
        for side in sides[:3]:
            cands = []
            if side in ("N", "S"):
                ring_y = room.y - 1 if side == "N" else room.y + room.h
                for x in range(room.x + 1, room.x + room.w - 2):
                    cands.append(((x, ring_y), False, (x, ring_y - 1 if side == "N" else ring_y + 1), abs(x + 1 - tx)))
            else:
                ring_x = room.x - 1 if side == "W" else room.x + room.w
                for y in range(room.y + 1, room.y + room.h - 2):
                    cands.append(((ring_x, y), True, (ring_x - 1 if side == "W" else ring_x + 1, y), abs(y + 1 - ty)))
            rng.shuffle(cands)
            cands.sort(key=lambda c: c[3] + rng.random() * 8)
            for (pos, vertical, anchor, _score) in cands[:40]:
                if any(abs(pos[0] - d.x) + abs(pos[1] - d.y) < 5 for d in existing):
                    continue
                if reserve is not None and abs(pos[0] - reserve["pos"][0]) + abs(pos[1] - reserve["pos"][1]) < 4 and reserve["room"] == room.id:
                    continue
                # lane cells (2x2 brush at anchor) must be free of other rooms' footprints
                good = True
                for ddx in range(2):
                    for ddy in range(2):
                        lx, ly = anchor[0] + ddx, anchor[1] + ddy
                        if not (0 < lx < m.width - 1 and 0 < ly < m.height - 1):
                            good = False
                        elif self.occ[ly * m.width + lx] and not self._in_fp(room, lx, ly):
                            good = False
                if good:
                    return {"pos": pos, "vertical": vertical, "anchor": anchor, "room": room.id}
        return None

    @staticmethod
    def _in_fp(room: Room, x, y) -> bool:
        x0, y0, x1, y1 = room.footprint
        return x0 <= x <= x1 and y0 <= y <= y1

    def _commit_door(self, m: MapData, room: Room, d) -> None:
        door = Door(len(m.doors), d["pos"][0], d["pos"][1], d["vertical"], [room.id], room.restricted)
        m.doors.append(door)
        room.doors.append(door.id)
        for (x, y) in door.cells:
            m.tiles[y * m.width + x] = FLOOR

    # ---- corridor routing
    def _route(self, m, rng, start, goal):
        # cheap candidates first: L and Z shapes
        cands = []
        sx, sy = start
        gx, gy = goal
        cands.append(self._hv(sx, sy, gx, gy))
        cands.append(self._vh(sx, sy, gx, gy))
        for _ in range(10):
            if rng.random() < 0.5 and gx != sx:
                mx = rng.randint(min(sx, gx), max(sx, gx))
                cands.append(self._hv(sx, sy, mx, sy)[:-1] + self._vh(mx, sy, mx, gy) [:-1] + self._hv(mx, gy, gx, gy))
            elif gy != sy:
                my = rng.randint(min(sy, gy), max(sy, gy))
                cands.append(self._vh(sx, sy, sx, my)[:-1] + self._hv(sx, my, gx, my)[:-1] + self._vh(gx, my, gx, gy))
        W = m.width
        rng.shuffle(cands)
        best = None
        for path in cands:
            if self._path_free(m, path):
                cost = sum(1 + 2 * self.near[y * W + x] - 0.6 * self.corr[y * W + x] for x, y in path)
                if best is None or cost < best[0]:
                    best = (cost, path)
        if best:
            return best[1]
        return self._astar(m, rng, start, goal)

    @staticmethod
    def _hv(x0, y0, x1, y1):
        pts = []
        step = 1 if x1 >= x0 else -1
        for x in range(x0, x1 + step, step):
            pts.append((x, y0))
        step = 1 if y1 >= y0 else -1
        for y in range(y0 + step, y1 + step, step) if y1 != y0 else []:
            pts.append((x1, y))
        return pts

    @staticmethod
    def _vh(x0, y0, x1, y1):
        pts = []
        step = 1 if y1 >= y0 else -1
        for y in range(y0, y1 + step, step):
            pts.append((x0, y))
        step = 1 if x1 >= x0 else -1
        for x in range(x0 + step, x1 + step, step) if x1 != x0 else []:
            pts.append((x, y1))
        return pts

    def _path_free(self, m, path) -> bool:
        W, H = m.width, m.height
        for (x, y) in path:
            if not (2 <= x < W - 4 and 2 <= y < H - 4):
                return False
            # brush footprint (3x3 worst case) must avoid rooms
            if self.occ[y * W + x]:
                return False
        return True

    def _astar(self, m, rng, start, goal):
        W, H = m.width, m.height
        sx, sy = start
        gx, gy = goal
        if self.occ[sy * W + sx] or self.occ[gy * W + gx]:
            return None
        INF = 1e18
        dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))
        best = {}
        heap = [(abs(sx - gx) + abs(sy - gy), 0.0, sx, sy, -1)]
        parent = {}
        best[(sx, sy, -1)] = 0.0
        found = None
        n = 0
        while heap:
            f, g, x, y, d = heapq.heappop(heap)
            if g > best.get((x, y, d), INF):
                continue
            if (x, y) == (gx, gy):
                found = (x, y, d)
                break
            n += 1
            if n > 90000:
                break
            for nd, (dx, dy) in enumerate(dirs):
                nx, ny = x + dx, y + dy
                if not (2 <= nx < W - 4 and 2 <= ny < H - 4):
                    continue
                i = ny * W + nx
                if self.occ[i]:
                    continue
                cost = 1.0 + 2.5 * self.near[i] - 0.5 * self.corr[i]
                if d != -1 and nd != d:
                    cost += 2.0
                ng = g + cost
                key = (nx, ny, nd)
                if ng < best.get(key, INF):
                    best[key] = ng
                    parent[key] = (x, y, d)
                    heapq.heappush(heap, (ng + abs(nx - gx) + abs(ny - gy), ng, nx, ny, nd))
        if found is None:
            return None
        path = []
        cur = found
        while cur in parent or (cur[0], cur[1]) == (sx, sy):
            path.append((cur[0], cur[1]))
            if (cur[0], cur[1]) == (sx, sy) and cur[2] == -1:
                break
            cur = parent[cur]
        path.reverse()
        return path

    # ---- dead ends
    def _stubs(self, m: MapData, rng: random.Random) -> None:
        W, H = m.width, m.height
        corr_cells = [(i % W, i // W) for i, v in enumerate(self.corr) if v]
        if not corr_cells:
            return
        made = 0
        for _ in range(120):
            if made >= rng.randint(6, 12):
                break
            x, y = rng.choice(corr_cells)
            dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
            length = rng.randint(7, 20)
            cells = []
            ok = True
            for k in range(2, length + 2):
                cx, cy = x + dx * k, y + dy * k
                brush = [(cx + a, cy + b) for a in range(2) for b in range(2)]
                for (bx, by) in brush:
                    if not (3 < bx < W - 4 and 3 < by < H - 4) or self.occ[by * W + bx] or self.near[by * W + bx]:
                        ok = False
                    elif k > 2 and self.corr[by * W + bx]:
                        ok = False
                if not ok:
                    break
                cells.append(brush)
            if ok and len(cells) >= 6:
                for brush in cells:
                    for (bx, by) in brush:
                        m.tiles[by * W + bx] = FLOOR
                        self.corr[by * W + bx] = 1
                made += 1
                m.meta.setdefault("stubs", []).append([cells[-1][0][0], cells[-1][0][1]])

    # ---- walls
    def _derive_walls(self, m: MapData) -> None:
        W, H = m.width, m.height
        t = m.tiles
        for y in range(H):
            for x in range(W):
                if t[y * W + x] != VOID:
                    continue
                near = False
                for yy in (y - 1, y, y + 1):
                    if 0 <= yy < H:
                        for xx in (x - 1, x, x + 1):
                            if 0 <= xx < W and t[yy * W + xx] == FLOOR:
                                near = True
                                break
                    if near:
                        break
                if near:
                    t[y * W + x] = WALL
