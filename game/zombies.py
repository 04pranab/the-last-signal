"""Server side zombies: spawning, chasing (BFS pathing), melee attacks and damage."""
from __future__ import annotations

import math
import random
from collections import deque
from typing import Dict, List, Optional, Tuple

from .collision import move_with_collision
from .config import TILE

KINDS = {
    "walker": {"idx": 0, "hp": 60, "speed": 82.0, "dmg": 12, "scale": 1.0, "radius": 22},
    "runner": {"idx": 1, "hp": 38, "speed": 140.0, "dmg": 8, "scale": 0.92, "radius": 20},
    "brute": {"idx": 2, "hp": 170, "speed": 62.0, "dmg": 24, "scale": 1.3, "radius": 30},
}
KIND_BY_IDX = {v["idx"]: k for k, v in KINDS.items()}
ZOMBIE_HALF = 15
AGGRO = 7.0 * TILE
DEAGGRO = 16.0 * TILE
ATTACK_RANGE = 40.0
ATTACK_COOLDOWN = 1.0
MAX_ZOMBIES = 70
SAFE_RADIUS_TILES = 24      # no zombies this close to the spawn hub at the start


class Zombie:
    _next_id = 1

    def __init__(self, kind: str, x: float, y: float):
        self.id = Zombie._next_id
        Zombie._next_id += 1
        self.kind = kind
        spec = KINDS[kind]
        self.hp = spec["hp"]
        self.max_hp = spec["hp"]
        self.x, self.y = x, y
        self.face = 0.0
        self.awake = False
        self.alert_until = 0.0
        self.alert_pos: Optional[Tuple[float, float]] = None
        self.path: List[Tuple[int, int]] = []
        self.repath_at = 0.0
        self.attack_at = 0.0
        self.attacked_until = 0.0
        self.moving = False
        self.wander_next = 0.0
        self.wdx = 0.0
        self.wdy = 0.0

    @property
    def radius(self) -> float:
        return KINDS[self.kind]["radius"]


class ZombieManager:
    def __init__(self, world, rng: random.Random):
        self.world = world
        self.rng = rng
        self.zombies: Dict[int, Zombie] = {}
        self.next_trickle = 40.0
        self.fields: Dict[int, Tuple[float, Tuple[int, int], Dict[Tuple[int, int], int]]] = {}

    # one BFS "flow field" per hunted player, shared by every zombie chasing that player
    def _field(self, pid: int, gx: int, gy: int, limit: int = 3200) -> Dict[Tuple[int, int], int]:
        now = self.world.t
        cached = self.fields.get(pid)
        if cached and now - cached[0] < 0.5 and cached[1] == (gx, gy):
            return cached[2]
        w = self.world
        dist = {(gx, gy): 0}
        q = deque([(gx, gy)])
        n = 0
        while q and n < limit:
            c = q.popleft()
            n += 1
            d = dist[c] + 1
            for nb in ((c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)):
                if nb not in dist and not w.path_solid(*nb):
                    dist[nb] = d
                    q.append(nb)
        self.fields[pid] = (now, (gx, gy), dist)
        return dist

    def _step_from_field(self, field, cx: int, cy: int):
        best, bd = None, field.get((cx, cy), 1 << 30)
        for nb in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            d = field.get(nb)
            if d is not None and d < bd:
                best, bd = nb, d
        return best

    # ------------------------------------------------------------- spawning
    def _free_cells(self, room) -> List[Tuple[int, int]]:
        m = self.world.map
        return [(x, y) for y in range(room.y + 1, room.y + room.h - 1) for x in range(room.x + 1, room.x + room.w - 1)
                if not m.solid[y * m.width + x]]

    def _pick_kind(self) -> str:
        r = self.rng.random()
        return "walker" if r < 0.68 else ("runner" if r < 0.9 else "brute")

    def populate(self) -> None:
        m = self.world.map
        hub = m.rooms[m.meta["hub_room"]]
        hx, hy = hub.center
        counts = {"storage": (1, 2), "lab": (0, 2), "maintenance": (1, 2), "quarters": (0, 2), "main_lab": (2, 4),
                  "medical": (1, 3), "archive": (1, 3), "server_wing": (2, 4), "security": (1, 3), "restricted": (1, 3),
                  "generator": (1, 3), "comms": (1, 2)}
        for room in m.rooms:
            if room.kind not in counts:
                continue
            cx, cy = room.center
            if abs(cx - hx) + abs(cy - hy) < SAFE_RADIUS_TILES:
                continue
            cells = self._free_cells(room)
            if not cells:
                continue
            for _ in range(self.rng.randint(*counts[room.kind])):
                if len(self.zombies) >= self.world.zombie_cap:
                    return
                cx_, cy_ = self.rng.choice(cells)
                z = Zombie(self._pick_kind(), (cx_ + 0.5) * TILE, (cy_ + 0.5) * TILE)
                self.zombies[z.id] = z

    def populate_paths(self) -> None:
        """Zombies in the corridors / on the roads / across open ground, so travelling between rooms is never empty."""
        m = self.world.map
        W = m.width
        hub = m.rooms[m.meta["hub_room"]]
        hx, hy = hub.center
        outdoor = bool(m.meta.get("outdoor_packs"))
        cells = [(i % W, i // W) for i, z in enumerate(m.zone) if (z == 0 or z == 255) and m.tiles[i] == 1 and not m.solid[i]]
        if not cells:
            return
        n_packs = int(m.meta.get("outdoor_packs", 0)) or 14
        for _ in range(n_packs):
            if len(self.zombies) >= self.world.zombie_cap:
                return
            for _try in range(60):
                cx, cy = self.rng.choice(cells)
                if abs(cx - hx) + abs(cy - hy) < SAFE_RADIUS_TILES + 8:
                    continue
                size = self.rng.randint(2, 5) if outdoor else self.rng.randint(1, 2)
                for _k in range(size):
                    x, y = cx + self.rng.randint(-2, 2), cy + self.rng.randint(-2, 2)
                    if not m.solid[y * W + x] and len(self.zombies) < self.world.zombie_cap:
                        self.add(self._pick_kind(), (x + .5) * TILE, (y + .5) * TILE)
                break

    def add(self, kind: str, x: float, y: float, awake: bool = False) -> Zombie:
        z = Zombie(kind, x, y)
        z.awake = awake
        if awake:
            z.alert_until = self.world.t + 20
        self.zombies[z.id] = z
        return z

    def trickle(self) -> None:
        """Slow stream of new zombies so the station never feels cleared."""
        w = self.world
        if not getattr(w, "zombies_enabled", True) or w.t < self.next_trickle:
            return
        alive = [p for p in w.players.values() if p.connected and not p.dead]
        if not alive:
            return
        self.next_trickle = w.t + self.rng.uniform(12, 22) * (0.7 if w.power else 1.0) * (1.0 - 0.45 * (1.0 - w.daylight() if w.daynight else 0.0))
        night = 1.0 - w.daylight() if w.daynight else 0.0
        cap = min(w.zombie_cap, 26 + 5 * len(alive) + (8 if w.power else 0) + int(12 * night))
        if len(self.zombies) >= cap:
            return
        p = self.rng.choice(alive)
        self.spawn_group(self.rng.randint(1, 3), (p.x, p.y))

    def spawn_group(self, n: int, around_pid_pos: Tuple[float, float]) -> int:
        """Spawn up to n zombies 12-20 tiles away from a player (used by the Echo surge)."""
        m = self.world.map
        px, py = around_pid_pos
        made = 0
        for _ in range(400):
            if made >= n or len(self.zombies) >= MAX_ZOMBIES:
                break
            tx = int(px // TILE) + self.rng.randint(-20, 20)
            ty = int(py // TILE) + self.rng.randint(-20, 20)
            d = math.hypot(tx - px / TILE, ty - py / TILE)
            if d < 12 or d > 21 or not (1 <= tx < m.width - 1 and 1 <= ty < m.height - 1):
                continue
            if self.world.solid_at(tx, ty):
                continue
            if any(math.hypot((tx + .5) * TILE - p.x, (ty + .5) * TILE - p.y) < 11 * TILE
                   for p in self.world.players.values() if p.connected):
                continue
            z = Zombie("walker" if self.rng.random() < 0.7 else "runner", (tx + 0.5) * TILE, (ty + 0.5) * TILE)
            z.awake = True
            z.alert_until = self.world.t + 25
            z.alert_pos = (px, py)
            self.zombies[z.id] = z
            made += 1
        return made

    # --------------------------------------------------------------- events
    def alert(self, x: float, y: float, radius: float, seconds: float = 8.0) -> None:
        r2 = radius * radius
        for z in self.zombies.values():
            if (z.x - x) ** 2 + (z.y - y) ** 2 < r2:
                z.alert_until = max(z.alert_until, self.world.t + seconds)
                z.alert_pos = (x, y)

    def damage(self, z: Zombie, dmg: float, pid: int) -> bool:
        """Apply damage; returns True if the zombie died."""
        z.hp -= dmg
        z.awake = True
        z.alert_until = max(z.alert_until, self.world.t + 10)
        p = self.world.players.get(pid)
        if p:
            z.alert_pos = (p.x, p.y)
        if z.hp <= 0:
            self.zombies.pop(z.id, None)
            if p:
                p.kills += 1
            self.world.on_zombie_killed(z)
            return True
        return False

    # ------------------------------------------------------------------- AI
    def _bfs_path(self, sx: int, sy: int, gx: int, gy: int, limit: int = 2600) -> List[Tuple[int, int]]:
        w = self.world
        if (sx, sy) == (gx, gy):
            return []
        prev = {(sx, sy): None}
        q = deque([(sx, sy)])
        found = False
        n = 0
        while q and n < limit:
            c = q.popleft()
            n += 1
            if c == (gx, gy):
                found = True
                break
            for nb in ((c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)):
                if nb in prev or w.path_solid(*nb):
                    continue
                prev[nb] = c
                q.append(nb)
        if not found:
            return []
        path, c = [], (gx, gy)
        while c != (sx, sy):
            path.append(c)
            c = prev[c]
        path.reverse()
        return path

    def update(self, dt: float) -> None:
        w = self.world
        now = w.t
        targets = [p for p in w.players.values() if p.connected and not p.dead]
        zs = list(self.zombies.values())
        aggro = AGGRO * (1.0 + 0.45 * (1.0 - w.daylight())) if w.daynight else AGGRO
        wander = bool(w.map.meta.get("wander"))
        for z in zs:
            spec = KINDS[z.kind]
            best, bd = None, 1e18
            for p in targets:
                d2 = (p.x - z.x) ** 2 + (p.y - z.y) ** 2
                if d2 < bd:
                    best, bd = p, d2
            alerted = now < z.alert_until
            if best is not None and (bd < aggro * aggro or (alerted and bd < (DEAGGRO * 1.4) ** 2)):
                z.awake = True
            elif z.awake and (best is None or bd > DEAGGRO * DEAGGRO) and not alerted:
                z.awake = False
            z.moving = False
            if not z.awake:
                if wander:
                    self._wander(z, dt, now)
                continue
            goal = (best.x, best.y) if best is not None else z.alert_pos
            if goal is None:
                continue
            dist = math.sqrt((goal[0] - z.x) ** 2 + (goal[1] - z.y) ** 2)
            # melee
            if best is not None and dist < ATTACK_RANGE and now >= z.attack_at:
                z.attack_at = now + ATTACK_COOLDOWN
                z.attacked_until = now + 0.35
                w.hurt_player(best.pid, spec["dmg"], "zombie")
            tx, ty = goal
            if dist > 30:
                if best is not None and dist > 1.4 * TILE:
                    field = self._field(best.pid, int(best.x // TILE), int(best.y // TILE))
                    nxt = self._step_from_field(field, int(z.x // TILE), int(z.y // TILE))
                    if nxt is not None:
                        tx, ty = (nxt[0] + .5) * TILE, (nxt[1] + .5) * TILE
                dx, dy = tx - z.x, ty - z.y
                n = math.hypot(dx, dy) or 1.0
                step = spec["speed"] * dt
                nx, ny = move_with_collision(w.solid_at, z.x, z.y, dx / n * step, dy / n * step, ZOMBIE_HALF)
                z.moving = (nx, ny) != (z.x, z.y)
                if abs(dx) > 2:
                    z.face = 0.0 if dx > 0 else math.pi
                z.x, z.y = nx, ny
        # simple separation so a horde does not stack on one spot
        for i in range(len(zs)):
            a = zs[i]
            if not a.awake:
                continue
            for j in range(i + 1, len(zs)):
                b = zs[j]
                dx, dy = b.x - a.x, b.y - a.y
                d2 = dx * dx + dy * dy
                if 0 < d2 < 26 * 26:
                    d = math.sqrt(d2)
                    push = (26 - d) * 0.5
                    ox, oy = dx / d * push * 0.35, dy / d * push * 0.35
                    b.x, b.y = move_with_collision(w.solid_at, b.x, b.y, ox, oy, ZOMBIE_HALF)
                    a.x, a.y = move_with_collision(w.solid_at, a.x, a.y, -ox, -oy, ZOMBIE_HALF)

    def _wander(self, z, dt: float, now: float) -> None:
        """Idle zombies shamble around (open world): a roaming feel instead of statues."""
        w = self.world
        if now >= z.wander_next:
            z.wander_next = now + self.rng.uniform(2.5, 7.0)
            if self.rng.random() < 0.6:
                a = self.rng.uniform(0, 6.283)
                z.wdx, z.wdy = math.cos(a), math.sin(a)
            else:
                z.wdx = z.wdy = 0.0
        if z.wdx or z.wdy:
            sp = 34.0 * dt
            nx, ny = move_with_collision(w.solid_at, z.x, z.y, z.wdx * sp, z.wdy * sp, ZOMBIE_HALF)
            z.moving = (nx, ny) != (z.x, z.y)
            if not z.moving:
                z.wdx = z.wdy = 0.0
            if abs(z.wdx) > 0.2:
                z.face = 0.0 if z.wdx > 0 else math.pi
            z.x, z.y = nx, ny

    def snapshot_rows(self) -> list:
        now = self.world.t
        rows = []
        for z in self.zombies.values():
            flags = (1 if z.moving else 0) | (2 if now < z.attacked_until else 0) | (4 if z.awake else 0)
            rows.append([z.id, KINDS[z.kind]["idx"], round(z.x, 1), round(z.y, 1), round(z.face, 2), int(z.hp), flags])
        return rows
