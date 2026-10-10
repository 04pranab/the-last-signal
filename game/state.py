"""Authoritative game world (no networking, no rendering).

The server owns exactly one :class:`GameWorld`.  Clients only send *intents*
(movement vector, interact, transmit); everything is validated here.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

from . import clues as clue_mod
from .collision import move_with_collision
from .config import (DOOR_CLOSE_DELAY, DOOR_OPEN_RADIUS, GAME_TIME_LIMIT, INTERACT_RANGE, PLAYER_HALF,
                     PLAYER_SPEED, TILE, TRANSMIT_LOCKOUT)
from .echo import EchoDirector
from .interaction import can_interact
from .maps.generator import MapData
from .objectives import objective_status
from .zombies import ZombieManager, MAX_ZOMBIES
from .boss import Boss
from .weapons import ORDER, WEAPONS, CRATE_WEAPONS
from .player import Player

# door state codes sent to clients
D_CLOSED, D_OPEN, D_LOCKED, D_JAMMED = 0, 1, 2, 3


class GameWorld:
    def __init__(self, map_data: MapData, time_limit: float = GAME_TIME_LIMIT, echo: bool = True, zombies: bool = True, boss: bool = True):
        self.map = map_data
        self.time_limit = float(time_limit)
        self.t = 0.0
        self.phase = "playing"          # playing | victory | failure
        self.end_reason = ""
        self.players: Dict[int, Player] = {}
        self.door_open: List[bool] = [False] * len(map_data.doors)
        self.door_close_at: List[float] = [0.0] * len(map_data.doors)
        self.jam_until: Dict[int, float] = {}
        self.corrupt_until: Dict[str, float] = {}
        self.false_until: Dict[str, float] = {}
        self.false_values: Dict[str, str] = {}
        self.obj_cooldown: Dict[str, float] = {}
        self.fx: Dict[str, float] = {}
        self.power = False
        self.core_online = False
        self.found: set = set()                 # clue ids the team has verified
        self.attempts = 0
        self.dirty = True
        self.outbox: List[Tuple[Optional[int], dict]] = []   # (pid or None for all, message)
        self.echo = EchoDirector(self, seed=map_data.seed, enabled=echo)
        self._frng = random.Random(map_data.seed ^ 0xFA15E)
        self._solid_cache = None
        self.zombies_enabled = zombies
        self.boss_enabled = boss
        self.boss: Optional[Boss] = None
        self.boss_defeated = False
        self.pickups: List[dict] = []
        self._pk_id = 1
        self.crates_opened: set = set()
        self.zombies = ZombieManager(self, random.Random(map_data.seed ^ 0x2B1E))
        if zombies:
            self.zombies.populate()
        self._init_pickups()

    def _init_pickups(self) -> None:
        rng = random.Random(self.map.seed ^ 0x91C)
        m = self.map
        for room in m.rooms:
            n = {"medical": 2, "storage": 1, "security": 1, "maintenance": 1}.get(room.kind, 0)
            for _ in range(n):
                for _try in range(30):
                    x, y = rng.randint(room.x, room.x + room.w - 1), rng.randint(room.y, room.y + room.h - 1)
                    if not m.solid[y * m.width + x] and (x, y) not in {tuple(c) for c in m.spawns}:
                        self._new_pickup("medkit" if room.kind in ("medical", "security") else "ammo", (x + .5) * TILE, (y + .5) * TILE, 1e9)
                        break

    # ------------------------------------------------------------- messaging
    def broadcast(self, msg: dict) -> None:
        self.outbox.append((None, msg))

    def send(self, pid: int, msg: dict) -> None:
        self.outbox.append((pid, msg))

    def toast(self, pid: Optional[int], text: str, kind: str = "info", sound: str = "") -> None:
        msg = {"t": "toast", "text": text, "kind": kind}
        if sound:
            msg["snd"] = sound
        self.outbox.append((pid, msg))

    def drain(self) -> List[Tuple[Optional[int], dict]]:
        out, self.outbox = self.outbox, []
        return out

    # --------------------------------------------------------------- players
    def spawn_position(self, pid: int) -> Tuple[float, float]:
        sp = self.map.spawns
        x, y = sp[(pid - 1) % len(sp)]
        return (x + 0.5) * TILE, (y + 0.5) * TILE

    def add_player(self, pid: int, name: str, token: str = "") -> Player:
        p = Player(pid=pid, name=name, token=token, char=(pid - 1) % 8)
        p.x, p.y = self.spawn_position(pid)
        self.players[pid] = p
        self.dirty = True
        return p

    def remove_player(self, pid: int) -> None:
        self.players.pop(pid, None)
        self.dirty = True

    def set_connected(self, pid: int, connected: bool) -> None:
        p = self.players.get(pid)
        if p:
            p.connected = connected
            if not connected:
                p.mx = p.my = 0.0
            self.dirty = True

    def set_input(self, pid: int, mx: float, my: float, aim: float = None, fire: bool = None) -> None:
        p = self.players.get(pid)
        if not p or not p.connected or self.phase != "playing":
            return
        n = math.hypot(mx, my)
        if n > 1.0:
            mx, my = mx / n, my / n
        p.mx, p.my = mx, my
        if aim is not None and math.isfinite(aim):
            p.aim = aim
        if fire is not None:
            p.fire = bool(fire)
        if p.dead:
            p.mx = p.my = 0.0
            p.fire = False

    # ---------------------------------------------------------------- combat
    RESPAWN_TIME = 8.0

    # ---- inventory
    def _inv_msg(self, p) -> dict:
        return {"t": "inv", "cur": p.cur, "owned": [w for w in ORDER if w in p.inv],
                "clip": dict(p.inv), "reserve": {k: v for k, v in p.reserve.items()}}

    def send_inv(self, p) -> None:
        self.send(p.pid, self._inv_msg(p))

    def give_weapon(self, p, name: str, switch: bool = True) -> bool:
        spec = WEAPONS[name]
        new = name not in p.inv
        if new:
            p.inv[name] = spec["clip"]
            p.reserve[name] = spec["reserve"]
        elif p.reserve.get(name) is not None:
            p.reserve[name] += spec["clip"] * 2
        if switch and new:
            self.switch_weapon(p.pid, name, quiet=True)
        self.send_inv(p)
        return new

    def switch_weapon(self, pid: int, name: str, quiet: bool = False) -> None:
        p = self.players.get(pid)
        if not p or p.dead or name not in p.inv or name == p.cur:
            return
        p.cur = name
        p.reload_until = 0.0
        p.next_shot = self.t + 0.25
        if not quiet:
            self.send_inv(p)
        else:
            self.dirty = True

    def reload(self, pid: int) -> None:
        p = self.players.get(pid)
        if not p or p.dead or self.phase != "playing" or self.t < p.reload_until:
            return
        spec = WEAPONS[p.cur]
        res = p.reserve.get(p.cur)
        if p.ammo >= spec["clip"]:
            return
        if res is not None and res <= 0:
            self.send(pid, {"t": "fx", "k": "empty"})
            return
        p.reload_until = self.t + spec["reload"]
        self.send(pid, {"t": "fx", "k": "reload"})

    def _finish_reload(self, p) -> None:
        spec = WEAPONS[p.cur]
        need = spec["clip"] - p.ammo
        res = p.reserve.get(p.cur)
        take = need if res is None else min(need, res)
        p.ammo += take
        if res is not None:
            p.reserve[p.cur] = res - take
        self.send_inv(p)

    def _shoot(self, p) -> None:
        spec = WEAPONS[p.cur]
        if self.t < p.next_shot or self.t < p.reload_until:
            return
        if p.ammo <= 0:
            self.reload(p.pid)
            return
        p.ammo -= 1
        p.next_shot = self.t + spec["cd"]
        sx, sy = p.x + math.cos(p.aim) * 20, p.y + math.sin(p.aim) * 20
        any_hit = killed = False
        ends = []
        boss = self.boss if (self.boss and self.boss.alive) else None
        for _ in range(spec["pellets"]):
            ang = p.aim + self._frng.uniform(-spec["spread"], spec["spread"])
            dx, dy = math.cos(ang), math.sin(ang)
            ex, ey = sx, sy
            pierce = spec["pierce"]
            hit_ids = set()
            steps = int(spec["range"] // 6)
            for i in range(1, steps + 1):
                px, py = sx + dx * 6 * i, sy + dy * 6 * i
                if self.solid_at(int(px // TILE), int(py // TILE)):
                    break
                ex, ey = px, py
                stop = False
                for z in list(self.zombies.zombies.values()):
                    if z.id in hit_ids:
                        continue
                    r = z.radius
                    if abs(px - z.x) < r and abs(py - z.y + 8) < r + 12:
                        hit_ids.add(z.id)
                        any_hit = True
                        if self.zombies.damage(z, spec["dmg"], p.pid):
                            killed = True
                        pierce -= 1
                        if pierce <= 0:
                            stop = True
                            break
                if not stop and boss and "boss" not in hit_ids and math.hypot(px - boss.x, py - boss.y + 10) < 46:
                    hit_ids.add("boss")
                    any_hit = True
                    if boss.damage(spec["dmg"], p.pid):
                        self._boss_died()
                        killed = True
                    pierce -= 1
                    if pierce <= 0:
                        stop = True
                if stop:
                    break
            ends.append((round(ex), round(ey)))
        self.broadcast({"t": "fx", "k": "shot", "pid": p.pid, "x": round(sx), "y": round(sy), "ends": ends,
                        "ex": ends[0][0], "ey": ends[0][1], "hit": any_hit, "kill": killed, "w": p.cur})
        self.zombies.alert(p.x, p.y, (13 if p.cur == "shotgun" else 11) * TILE, 8.0)
        if p.ammo <= 0:
            self.reload(p.pid)

    def hurt_player(self, pid: int, dmg: float, source: str = "") -> None:
        p = self.players.get(pid)
        if not p or p.dead or not p.connected or self.t < p.invuln_until or self.phase != "playing":
            return
        p.hp -= dmg
        p.last_damage = self.t
        self.send(pid, {"t": "fx", "k": "hurt", "hp": int(max(p.hp, 0)), "src": source})
        if p.hp <= 0:
            p.hp = 0
            p.dead = True
            p.deaths += 1
            p.dead_until = self.t + self.RESPAWN_TIME
            p.mx = p.my = 0.0
            p.fire = False
            who = "the Echo Warden" if source in ("boss", "orb") else "zombies"
            self.broadcast({"t": "toast", "text": f"{p.name} was overwhelmed by {who}.", "kind": "error", "snd": "player_left"})
            self.dirty = True

    def _update_combat(self, dt: float) -> None:
        for p in self.players.values():
            if not p.connected:
                continue
            if p.dead:
                if self.t >= p.dead_until:
                    p.dead = False
                    p.hp = p.max_hp
                    p.inv[p.cur] = max(p.inv.get(p.cur, 0), WEAPONS[p.cur]["clip"] // 2)
                    p.x, p.y = self.spawn_position(p.pid)
                    p.invuln_until = self.t + 3.0
                    self.send(p.pid, {"t": "fx", "k": "respawn", "x": p.x, "y": p.y})
                    self.send_inv(p)
                continue
            if p.reload_until and self.t >= p.reload_until:
                p.reload_until = 0.0
                self._finish_reload(p)
            if p.hp < p.max_hp and self.t - p.last_damage > 6.0:
                p.hp = min(p.max_hp, p.hp + 2.0 * dt)
            if p.fire:
                self._shoot(p)
            self._collect_pickups(p)

    # ---- pickups & loot
    def _new_pickup(self, kind: str, x: float, y: float, ttl: float = 90.0) -> None:
        if len(self.pickups) >= 40:
            return
        self.pickups.append({"id": self._pk_id, "kind": kind, "x": x, "y": y, "end": self.t + ttl})
        self._pk_id += 1

    def on_zombie_killed(self, z) -> None:
        r = self._frng.random()
        if r < 0.14:
            self._new_pickup("ammo", z.x, z.y)
        elif r < 0.24:
            self._new_pickup("medkit", z.x, z.y)

    def _collect_pickups(self, p) -> None:
        for pk in list(self.pickups):
            if (pk["x"] - p.x) ** 2 + (pk["y"] - p.y) ** 2 > 34 * 34:
                continue
            if pk["kind"] == "medkit":
                if p.hp >= p.max_hp - 1:
                    continue
                p.hp = min(p.max_hp, p.hp + 45)
                self.send(p.pid, {"t": "toast", "text": "Medkit +45 HP", "kind": "good", "snd": "success"})
            else:
                gained = False
                for name in p.inv:
                    if p.reserve.get(name) is not None:
                        p.reserve[name] += WEAPONS[name]["clip"]
                        gained = True
                if not gained:
                    continue
                self.send(p.pid, {"t": "toast", "text": "Ammo collected", "kind": "good", "snd": "success"})
                self.send_inv(p)
            self.pickups.remove(pk)
            self.dirty = True

    # ---- boss
    def _spawn_boss(self) -> None:
        if self.boss or not self.boss_enabled:
            return
        room = self.map.rooms[self.map.meta["comms_room"]]
        n = max(1, len([p for p in self.players.values() if p.connected]))
        self.boss = Boss(self, room, 900 + 520 * (n - 1), random.Random(self.map.seed ^ 0xB055))
        self.dirty = True
        self.broadcast({"t": "ev", "k": "boss", "text": f"THE ECHO WARDEN has awakened in {room.name}!"})

    def _boss_died(self) -> None:
        self.boss_defeated = True
        self.dirty = True
        b = self.boss
        self.broadcast({"t": "ev", "k": "boss_dead", "text": "THE ECHO WARDEN is destroyed. The transmitter is free!"})
        if b:
            for i in range(3):
                self._new_pickup("medkit", b.x + (i - 1) * 40, b.y + 40, 240)
            self._new_pickup("ammo", b.x, b.y - 40, 240)

    def debug_kill_boss(self) -> None:
        """Test / dev helper."""
        if self.boss and self.boss.alive:
            self.boss.hp = 1
            if self.boss.damage(5, 0):
                self._boss_died()
        elif not self.boss:
            self.boss_defeated = True

    def solid_at(self, tx: int, ty: int) -> bool:
        m = self.map
        if tx < 0 or ty < 0 or tx >= m.width or ty >= m.height:
            return True
        if m.solid[ty * m.width + tx]:
            return True
        did = m.door_at.get((tx, ty))
        if did is not None and not self.door_open[did]:
            return True
        return False

    def path_solid(self, tx: int, ty: int) -> bool:
        """Solidity for path planning: closed doors count as passable unless locked or jammed."""
        m = self.map
        if tx < 0 or ty < 0 or tx >= m.width or ty >= m.height:
            return True
        if m.solid[ty * m.width + tx]:
            return True
        did = m.door_at.get((tx, ty))
        if did is not None:
            d = m.doors[did]
            if (d.restricted and not self.power) or self.t < self.jam_until.get(did, 0):
                return True
        return False

    # ------------------------------------------------------------------ tick
    def tick(self, dt: float) -> None:
        dt = min(max(dt, 0.0), 0.1)
        if self.phase != "playing":
            return
        self.t += dt
        for p in self.players.values():
            if p.connected and p.moving and not p.dead:
                dx, dy = p.mx * PLAYER_SPEED * dt, p.my * PLAYER_SPEED * dt
                nx, ny = move_with_collision(self.solid_at, p.x, p.y, dx, dy, PLAYER_HALF)
                if (nx, ny) != (p.x, p.y):
                    p.face = math.atan2(p.my, p.mx)
                p.x, p.y = nx, ny
        self._update_combat(dt)
        self.zombies.update(dt)
        self.zombies.trickle()
        if self.boss:
            self.boss.update(dt)
        if self.pickups:
            self.pickups = [pk for pk in self.pickups if pk["end"] > self.t]
        self._update_doors()
        self.echo.update()
        if self.t >= self.time_limit:
            self.finish("failure", "TIME EXPIRED")

    def _update_doors(self) -> None:
        m = self.map
        r2 = DOOR_OPEN_RADIUS ** 2
        conn = [p for p in self.players.values() if p.connected and not p.dead]
        zl = [z for z in self.zombies.zombies.values() if z.awake]
        for d in m.doors:
            i = d.id
            locked = d.restricted and not self.power
            jammed = self.t < self.jam_until.get(i, 0)
            cx = (d.cells[0][0] + d.cells[-1][0] + 1) * TILE / 2
            cy = (d.cells[0][1] + d.cells[-1][1] + 1) * TILE / 2
            near = False
            occupied = False
            for p in conn:
                dx, dy = p.x - cx, p.y - cy
                dd = dx * dx + dy * dy
                if dd < r2:
                    near = True
                if dd < (TILE * 1.6) ** 2:
                    # is the player's box touching a door cell? then never slam it shut
                    for (tx, ty) in d.cells:
                        if (abs(p.x - (tx + 0.5) * TILE) < TILE / 2 + PLAYER_HALF and
                                abs(p.y - (ty + 0.5) * TILE) < TILE / 2 + PLAYER_HALF):
                            occupied = True
            if not near:
                for z in zl:
                    dx, dy = z.x - cx, z.y - cy
                    if dx * dx + dy * dy < (TILE * 1.5) ** 2:
                        near = True
                        break
            want_open = False
            if not (locked or jammed) and near:
                want_open = True
                self.door_close_at[i] = self.t + DOOR_CLOSE_DELAY
            elif self.door_open[i] and not (locked or jammed) and self.t < self.door_close_at[i]:
                want_open = True
            if self.door_open[i] and not want_open and occupied:
                want_open = True  # keep open until the doorway is clear
            if want_open != self.door_open[i]:
                self.door_open[i] = want_open
                self.dirty = True
        # state flips caused by timers (locks/jams expiring) are visible as door code changes
        # so mark dirty periodically
        if int(self.t * 4) != int((self.t - 0.034) * 4):
            self.dirty = True

    # ------------------------------------------------------------ interaction
    def interact(self, pid: int, oid: str) -> None:
        p = self.players.get(pid)
        if not p or not p.connected or p.dead or self.phase != "playing":
            return
        o = self.map.object_by_id.get(oid)
        if o is None or not can_interact(o, p.x, p.y):
            self.toast(pid, "Too far away.", "error", "error")
            return
        if o.kind == "generator":
            if self.power:
                self.toast(pid, "Generator already online.", "info")
            else:
                self.power = True
                self.dirty = True
                self.broadcast({"t": "ev", "k": "power", "pid": pid, "text": f"{p.name} restored power. Restricted doors unlocked."})
        elif o.kind == "core":
            if not self.power:
                self.toast(pid, "NO POWER. Restore the generator first.", "error", "error")
            elif self.core_online:
                self.toast(pid, "Signal core already calibrated.", "info")
            else:
                self.core_online = True
                self.dirty = True
                self.broadcast({"t": "ev", "k": "core", "pid": pid, "text": f"{p.name} calibrated the signal core."})
                self._spawn_boss()
        elif o.kind == "transmitter":
            if not self.power:
                self.toast(pid, "NO POWER. Restore the generator first.", "error", "error")
            elif not self.core_online:
                self.toast(pid, "Signal core is offline. Calibrate it in the Server Wing.", "error", "error")
            elif self.boss_enabled and not self.boss_defeated:
                self.toast(pid, "The transmitter is locked by the Echo. Destroy the Warden!", "error", "error")
            else:
                self.send(pid, {"t": "ui", "ui": "transmitter", "oid": oid,
                                "intf": max(0.0, self.fx.get("intf_until", 0) - self.t)})
        elif o.kind == "terminal":
            self._read_terminal(p, o)
        elif o.kind == "weapon_crate":
            self._open_crate(p, o)
        elif o.kind == "med_station":
            if self.t < p.heal_ready_at:
                self.toast(pid, f"Medical station recharging ({int(p.heal_ready_at - self.t) + 1}s).", "error", "error")
            elif p.hp >= p.max_hp - 1:
                self.toast(pid, "You are already healthy.", "info")
            else:
                p.hp = min(p.max_hp, p.hp + 70)
                p.heal_ready_at = self.t + 45
                self.toast(pid, "Wounds treated (+70 HP).", "good", "success")
        elif o.kind == "camera":
            if o.needs_power and not self.power:
                self.toast(pid, "NO POWER. Camera network offline.", "error", "error")
            elif self.t < p.scan_ready_at:
                self.toast(pid, f"Cameras rebooting ({int(p.scan_ready_at - self.t) + 1}s).", "error", "error")
            else:
                p.scan_ready_at = self.t + 50
                zs = [[round(z.x), round(z.y), z.kind[0]] for z in self.zombies.zombies.values()]
                bs = [round(self.boss.x), round(self.boss.y)] if self.boss and self.boss.alive else None
                self.send(pid, {"t": "scan", "zombies": zs, "boss": bs, "dur": 22})
                self.toast(pid, "Camera network online: hostiles marked on the map.", "good", "terminal")

    def _open_crate(self, p: Player, o) -> None:
        if o.id in self.crates_opened:
            self.toast(p.pid, "The crate is empty.", "info")
            return
        name = (self.map.secret.get("weapons") or {}).get(o.id, "smg")
        self.crates_opened.add(o.id)
        self.dirty = True
        new = self.give_weapon(p, name)
        self.toast(p.pid, f"Found: {WEAPONS[name]['label']}!" if new else f"{WEAPONS[name]['label']} ammo +{WEAPONS[name]['clip'] * 2}", "good", "success")
        if name == "plasma":
            self.broadcast({"t": "toast", "text": f"{p.name} found the PLASMA rifle!", "kind": "good"})

    def _read_terminal(self, p: Player, o) -> None:
        if o.needs_power and not self.power:
            self.toast(p.pid, "NO POWER. This terminal is offline.", "error", "error")
            return
        if self.t < self.corrupt_until.get(o.id, 0):
            self.toast(p.pid, "TERMINAL CORRUPTED - only static.", "error", "error")
            return
        info = (self.map.secret.get("objects") or {}).get(o.id)
        if not info:
            self.toast(p.pid, "Nothing useful here.", "info")
            return
        kind = info["kind"]
        integrity = 100
        if kind == "clue":
            cid = info["clue"]
            answer = self.map.secret["answer"]
            fv = None
            if self.t < self.false_until.get(o.id, 0):
                if o.id not in self.false_values:
                    self.false_values[o.id] = clue_mod.false_value(cid, answer, self._frng)
                fv = self.false_values[o.id]
                integrity = self._frng.randint(38, 78)
            title, lines = clue_mod.fragment_text(cid, answer, fv)
            key = cid
            if fv is None and cid not in self.found:
                self.found.add(cid)
                self.dirty = True
                self.broadcast({"t": "ev", "k": "fragment", "pid": p.pid, "text": f"{p.name} recovered a signal fragment."})
        elif kind == "note":
            title, lines = info["note"]["title"], list(info["note"]["lines"])
            key = o.id
        else:
            title, lines = info["log"]["title"], list(info["log"]["lines"])
            key = o.id
        entry = {"key": key, "title": title, "lines": lines, "integrity": integrity, "room": info.get("room", ""), "t": round(self.t)}
        replaced = False
        for i, n in enumerate(p.notes):
            if n["key"] == key:
                p.notes[i] = entry
                replaced = True
        if not replaced:
            p.notes.append(entry)
        self.send(p.pid, {"t": "read", "oid": o.id, "entry": entry})
        self.send(p.pid, {"t": "notes", "notes": p.notes})

    def transmit(self, pid: int, freq: str, chan: str, seq: str) -> None:
        p = self.players.get(pid)
        if not p or not p.connected or self.phase != "playing":
            return
        tx = self.map.object_by_id.get(self.map.meta["transmitter_id"])
        if tx is None or not can_interact(tx, p.x, p.y):
            self.send(pid, {"t": "tx_result", "ok": False, "msg": "OUT OF RANGE", "close": True})
            return
        if not (self.power and self.core_online):
            self.send(pid, {"t": "tx_result", "ok": False, "msg": "TRANSMITTER OFFLINE"})
            return
        if self.boss_enabled and not self.boss_defeated:
            self.send(pid, {"t": "tx_result", "ok": False, "msg": "LOCKED BY THE ECHO WARDEN"})
            return
        if self.t < self.fx.get("intf_until", 0):
            self.send(pid, {"t": "tx_result", "ok": False, "msg": "SIGNAL INTERFERENCE - WAIT"})
            return
        if self.t < p.transmit_ready_at:
            self.send(pid, {"t": "tx_result", "ok": False, "msg": "RECHARGING - WAIT"})
            return
        if not (freq.isdigit() and len(freq) == 3 and chan.isdigit() and len(chan) == 2 and seq.isdigit() and len(seq) == 3):
            self.send(pid, {"t": "tx_result", "ok": False, "msg": "INVALID ENTRY (3 / 2 / 3 digits)"})
            return
        self.attempts += 1
        matched = clue_mod.answer_matches(self.map.secret["answer"], freq, chan, seq)
        if matched == 3:
            self.send(pid, {"t": "tx_result", "ok": True, "msg": "SIGNAL TRANSMITTED"})
            self.finish("victory", "SIGNAL TRANSMITTED")
        else:
            p.transmit_ready_at = self.t + TRANSMIT_LOCKOUT
            self.send(pid, {"t": "tx_result", "ok": False, "msg": "SIGNAL REJECTED", "matched": matched,
                            "lockout": TRANSMIT_LOCKOUT})
            self.broadcast({"t": "ev", "k": "rejected", "pid": pid, "text": f"{p.name}: SIGNAL REJECTED ({self.attempts} attempts)"})

    def random_floor_cell(self, rng, avoid_comms: bool = True):
        m = self.map
        for _ in range(200):
            room = rng.choice(m.rooms)
            if avoid_comms and room.id == m.meta.get("comms_room"):
                continue
            if room.restricted and not self.power:
                continue
            x, y = rng.randint(room.x, room.x + room.w - 1), rng.randint(room.y, room.y + room.h - 1)
            if not m.solid[y * m.width + x]:
                return x, y
        return None

    def teleport_player(self, pid: int, rng) -> bool:
        p = self.players.get(pid)
        if not p or p.dead or not p.connected:
            return False
        cell = self.random_floor_cell(rng)
        if cell is None:
            return False
        p.x, p.y = (cell[0] + .5) * TILE, (cell[1] + .5) * TILE
        p.invuln_until = max(p.invuln_until, self.t + 2.0)
        self.send(pid, {"t": "fx", "k": "teleport", "x": p.x, "y": p.y})
        return True

    def finish(self, phase: str, reason: str) -> None:
        if self.phase != "playing":
            return
        self.phase = phase
        self.end_reason = reason
        for p in self.players.values():
            p.mx = p.my = 0.0
        self.dirty = True
        self.broadcast({"t": "end", "phase": phase, "reason": reason, "time": round(self.t, 1),
                        "attempts": self.attempts, "found": len(self.found),
                        "kills": [[p.name, p.kills] for p in self.players.values()]})

    # ---------------------------------------------------------------- views
    def door_codes(self) -> List[int]:
        codes = []
        for d in self.map.doors:
            if self.t < self.jam_until.get(d.id, 0) and not self.door_open[d.id]:
                codes.append(D_JAMMED)
            elif d.restricted and not self.power and not self.door_open[d.id]:
                codes.append(D_LOCKED)
            else:
                codes.append(D_OPEN if self.door_open[d.id] else D_CLOSED)
        return codes

    def state_message(self) -> dict:
        bs = "off" if not self.boss_enabled else ("dead" if self.boss_defeated else ("active" if self.boss else "sleeping"))
        obj = objective_status(self.power, len(self.found), self.core_online, self.phase == "victory", bs)
        return {
            "t": "state",
            "clock": round(self.t, 2),
            "left": max(0.0, round(self.time_limit - self.t, 1)),
            "phase": self.phase,
            "power": self.power,
            "core": self.core_online,
            "found": sorted(self.found),
            "doors": self.door_codes(),
            "corrupt": [o for o, u in self.corrupt_until.items() if u > self.t],
            "false": [o for o, u in self.false_until.items() if u > self.t],
            "lights": round(max(0.0, self.fx.get("lights_until", 0) - self.t), 1),
            "intf": round(max(0.0, self.fx.get("intf_until", 0) - self.t), 1),
            "obj": obj,
            "attempts": self.attempts,
            "opened": sorted(self.crates_opened),
            "boss": {"on": bs, "hp": int(self.boss.hp) if self.boss else 0, "max": int(self.boss.max_hp) if self.boss else 0,
                     "phase": self.boss.phase if self.boss else 0},
        }

    def snapshot(self) -> dict:
        rows = []
        for p in self.players.values():
            flags = (1 if p.moving and not p.dead else 0) | (2 if p.connected else 0) | (4 if p.dead else 0) | (8 if self.t < p.reload_until else 0)
            rows.append([p.pid, round(p.x, 1), round(p.y, 1), round(p.face, 2), flags, int(p.hp), p.ammo, round(p.aim, 2),
                         ORDER.index(p.cur), -1 if p.reserve.get(p.cur) is None else p.reserve.get(p.cur)])
        msg = {"t": "snap", "c": round(self.t, 2), "p": rows, "z": self.zombies.snapshot_rows()}
        if self.boss and self.boss.alive:
            msg["b"] = self.boss.snapshot_row()
            msg["o"] = self.boss.orb_rows()
        if self.pickups:
            msg["k"] = [[pk["id"], 0 if pk["kind"] == "ammo" else 1, round(pk["x"]), round(pk["y"])] for pk in self.pickups[:40]]
        return msg
