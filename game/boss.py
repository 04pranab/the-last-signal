"""THE ECHO WARDEN - the boss guarding the Emergency Transmitter (server side)."""
from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple

from .collision import move_with_collision
from .config import TILE

BOSS_RADIUS = 46
BOSS_HALF = 26
ORB_SPEED = 235.0
ORB_DAMAGE = 12
ORB_LIFE = 3.4
ORB_RADIUS = 13

ST_IDLE, ST_TELEGRAPH, ST_ATTACK, ST_DEAD = 0, 1, 2, 3


class Boss:
    def __init__(self, world, room, max_hp: float, rng: random.Random):
        self.world = world
        self.room = room
        self.rng = rng
        self.max_hp = float(max_hp)
        self.hp = float(max_hp)
        free = [(x, y) for y in range(room.y + 2, room.y + room.h - 2) for x in range(room.x + 2, room.x + room.w - 2)
                if not world.solid_at(x, y)]
        cx, cy = room.center
        free.sort(key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)
        fx, fy = free[0] if free else (int(cx), int(cy))
        self.x, self.y = (fx + 0.5) * TILE, (fy + 0.5) * TILE
        self.phase = 1
        self.state = ST_IDLE
        self.face = 0.0
        self.next_attack_at = world.t + 3.0
        self.attack = None            # dict(kind, start, dur, data)
        self.recover_until = 0.0
        self.next_summon_at = world.t + 12.0
        self.orbs: List[dict] = []
        self.engaged = False

    # ------------------------------------------------------------------ helpers
    @property
    def alive(self) -> bool:
        return self.hp > 0

    def _in_room(self, x: float, y: float, margin: float = 1.5) -> bool:
        r = self.room
        return (r.x - margin) * TILE <= x <= (r.x + r.w + margin) * TILE and (r.y - margin) * TILE <= y <= (r.y + r.h + margin) * TILE

    def _targets(self):
        return [p for p in self.world.players.values() if p.connected and not p.dead and self._in_room(p.x, p.y)]

    def damage(self, dmg: float, pid: int) -> bool:
        if not self.alive:
            return False
        if not self.engaged:
            self.engaged = True
        self.hp -= dmg
        pl = self.world.players.get(pid)
        if self.hp <= 0:
            self.hp = 0
            self.state = ST_DEAD
            self.orbs.clear()
            if pl:
                pl.kills += 5
            return True
        frac = self.hp / self.max_hp
        newp = 1 if frac > 0.6 else (2 if frac > 0.3 else 3)
        if newp != self.phase:
            self.phase = newp
            self.world.broadcast({"t": "ev", "k": "boss_phase", "phase": newp,
                                  "text": "THE ECHO WARDEN SCREAMS." if newp == 2 else "THE ECHO WARDEN IS ENRAGED!"})
            self.next_attack_at = self.world.t + 1.2
        return False

    # ------------------------------------------------------------------- update
    def update(self, dt: float) -> None:
        w = self.world
        if not self.alive:
            return
        self._update_orbs(dt)
        targets = self._targets()
        if not targets and not self.engaged:
            self.state = ST_IDLE
            return
        if not targets:
            self.state = ST_IDLE
            self.attack = None
            return
        t = min(targets, key=lambda p: (p.x - self.x) ** 2 + (p.y - self.y) ** 2)
        now = w.t
        speed = {1: 88.0, 2: 108.0, 3: 132.0}[self.phase]
        if self.attack:
            self._run_attack(dt, t, now)
            return
        self.state = ST_IDLE
        dx, dy = t.x - self.x, t.y - self.y
        d = math.hypot(dx, dy)
        if abs(dx) > 4:
            self.face = 0.0 if dx > 0 else math.pi
        if d > 80 and now >= self.recover_until:
            nx, ny = move_with_collision(w.solid_at, self.x, self.y, dx / d * speed * dt, dy / d * speed * dt, BOSS_HALF)
            self.x, self.y = nx, ny
        if now >= self.next_attack_at and now >= self.recover_until:
            self._start_attack(t, now)

    def _pick(self) -> str:
        r = self.rng.random()
        if self.phase == 1:
            return "slam" if r < 0.5 else "orbs"
        if self.phase == 2:
            return "slam" if r < 0.28 else ("orbs" if r < 0.56 else ("charge" if r < 0.82 else "summon"))
        return "slam" if r < 0.22 else ("orbs" if r < 0.5 else ("charge" if r < 0.8 else "summon"))

    def _start_attack(self, target, now: float) -> None:
        kind = self._pick()
        if kind == "summon" and now < self.next_summon_at:
            kind = "orbs"
        w = self.world
        if kind == "slam":
            r = 135 if self.phase == 1 else 165
            self.attack = {"kind": "slam", "start": now, "dur": 0.95, "r": r, "done": False}
            w.broadcast({"t": "fx", "k": "telegraph", "shape": "circle", "x": round(self.x), "y": round(self.y), "r": r, "dur": 0.95})
            self.state = ST_TELEGRAPH
        elif kind == "orbs":
            self.attack = {"kind": "orbs", "start": now, "dur": 0.7, "done": False}
            w.broadcast({"t": "fx", "k": "boss_cast", "x": round(self.x), "y": round(self.y)})
            self.state = ST_TELEGRAPH
        elif kind == "charge":
            ang = math.atan2(target.y - self.y, target.x - self.x)
            self.attack = {"kind": "charge", "start": now, "dur": 0.85 + 0.55, "ang": ang, "hit": False}
            w.broadcast({"t": "fx", "k": "telegraph", "shape": "line", "x": round(self.x), "y": round(self.y), "ang": round(ang, 3),
                         "len": 520, "dur": 0.85})
            self.state = ST_TELEGRAPH
        else:
            self.attack = {"kind": "summon", "start": now, "dur": 1.2, "done": False}
            w.broadcast({"t": "fx", "k": "boss_cast", "x": round(self.x), "y": round(self.y)})
            self.state = ST_TELEGRAPH

    def _run_attack(self, dt: float, target, now: float) -> None:
        a = self.attack
        w = self.world
        el = now - a["start"]
        if a["kind"] == "slam":
            if not a["done"] and el >= 0.95:
                a["done"] = True
                self.state = ST_ATTACK
                w.broadcast({"t": "fx", "k": "slam", "x": round(self.x), "y": round(self.y), "r": a["r"]})
                for p in list(w.players.values()):
                    if p.connected and not p.dead and math.hypot(p.x - self.x, p.y - self.y) < a["r"]:
                        w.hurt_player(p.pid, 30, "boss")
            if el >= 1.4:
                self._end_attack(now)
        elif a["kind"] == "orbs":
            if not a["done"] and el >= 0.7:
                a["done"] = True
                self.state = ST_ATTACK
                n = {1: 8, 2: 12, 3: 16}[self.phase]
                base = math.atan2(target.y - self.y, target.x - self.x)
                off = self.rng.uniform(0, math.pi * 2 / n)
                for i in range(n):
                    ang = off + i * math.pi * 2 / n
                    sp = ORB_SPEED + (35 if self.phase == 3 else 0)
                    self.orbs.append({"x": self.x, "y": self.y, "vx": math.cos(ang) * sp, "vy": math.sin(ang) * sp, "end": now + ORB_LIFE})
                if self.phase >= 2:   # an aimed volley as well
                    for k in (-0.18, 0, 0.18):
                        self.orbs.append({"x": self.x, "y": self.y, "vx": math.cos(base + k) * 300, "vy": math.sin(base + k) * 300, "end": now + ORB_LIFE})
            if el >= 1.1:
                self._end_attack(now)
        elif a["kind"] == "charge":
            if el < 0.85:
                self.state = ST_TELEGRAPH
            else:
                self.state = ST_ATTACK
                step = 640 * dt
                nx, ny = move_with_collision(w.solid_at, self.x, self.y, math.cos(a["ang"]) * step, math.sin(a["ang"]) * step, BOSS_HALF)
                moved = (nx, ny) != (self.x, self.y)
                self.x, self.y = nx, ny
                if not a["hit"]:
                    for p in w.players.values():
                        if p.connected and not p.dead and math.hypot(p.x - self.x, p.y - self.y) < 60:
                            w.hurt_player(p.pid, 35, "boss")
                            a["hit"] = True
                if not moved or el >= a["dur"]:
                    self._end_attack(now, extra=0.5)
        else:   # summon
            if not a["done"] and el >= 1.2:
                a["done"] = True
                self.next_summon_at = now + 14.0
                self._summon()
            if el >= 1.6:
                self._end_attack(now)

    def _end_attack(self, now: float, extra: float = 0.0) -> None:
        self.attack = None
        self.state = ST_IDLE
        gap = {1: 3.0, 2: 2.3, 3: 1.6}[self.phase]
        self.recover_until = now + 0.4 + extra
        self.next_attack_at = now + gap

    def _summon(self) -> None:
        w = self.world
        r = self.room
        made = 0
        for _ in range(60):
            if made >= 4:
                break
            tx = self.rng.randint(r.x + 1, r.x + r.w - 2)
            ty = self.rng.randint(r.y + 1, r.y + r.h - 2)
            if w.solid_at(tx, ty):
                continue
            w.zombies.add("walker" if self.rng.random() < 0.6 else "runner", (tx + .5) * TILE, (ty + .5) * TILE, awake=True)
            made += 1
        w.broadcast({"t": "ev", "k": "boss_summon", "text": "The Warden calls the dead."})

    def _update_orbs(self, dt: float) -> None:
        w = self.world
        keep = []
        for o in self.orbs:
            o["x"] += o["vx"] * dt
            o["y"] += o["vy"] * dt
            if w.t >= o["end"] or w.solid_at(int(o["x"] // TILE), int(o["y"] // TILE)):
                continue
            hit = False
            for p in w.players.values():
                if p.connected and not p.dead and (p.x - o["x"]) ** 2 + (p.y - o["y"]) ** 2 < (ORB_RADIUS + 15) ** 2:
                    w.hurt_player(p.pid, ORB_DAMAGE, "orb")
                    hit = True
                    break
            if not hit:
                keep.append(o)
        self.orbs = keep

    def snapshot_row(self) -> list:
        return [round(self.x, 1), round(self.y, 1), int(self.hp), int(self.max_hp), self.phase, self.state, round(self.face, 2)]

    def orb_rows(self) -> list:
        return [[round(o["x"]), round(o["y"])] for o in self.orbs[:48]]
