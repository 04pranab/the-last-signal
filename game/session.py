"""Client side game session: mirrors the server state, predicts the local player."""
from __future__ import annotations

import math
import time
from typing import Dict, List, Optional

import pygame

from .collision import move_with_collision
from .config import PLAYER_COLORS, PLAYER_HALF, PLAYER_SPEED, TILE
from .interaction import nearest_interactable
from .maps.generator import FLOOR, WALL, MapData

REVEAL_RADIUS = 9


class Remote:
    def __init__(self, pid: int, name: str):
        self.pid, self.name = pid, name
        self.x = self.y = self.tx = self.ty = 0.0
        self.face = 0.0
        self.moving = False
        self.connected = True
        self.seen = False
        self.hp = 100
        self.dead = False
        self.aim = 0.0
        self.shoot_until = 0.0
        self.hurt_until = 0.0
        self.weapon = "pistol"

    @property
    def color(self):
        return PLAYER_COLORS[(self.pid - 1) % len(PLAYER_COLORS)]


class ZRemote:
    def __init__(self, zid: int, kind: int, x: float, y: float):
        self.zid, self.kind = zid, kind
        self.x = self.tx = x
        self.y = self.ty = y
        self.face = 0.0
        self.hp = 1
        self.max_hp = 1
        self.flags = 0
        self.hurt_until = 0.0
        self.seen_t = time.time()


ZMAXHP = {0: 60, 1: 38, 2: 170}


class Session:
    def __init__(self, lib, payload: dict, pid: int, players: List[dict], time_limit: float, audio, renderer_cls):
        self.lib, self.audio = lib, audio
        self.map = MapData.from_payload(payload)
        lib.set_map(payload.get("map_id") or "research_station")
        self.renderer = renderer_cls(lib, self.map)
        self.pid = pid
        self.time_limit = time_limit
        self.remote: Dict[int, Remote] = {p["pid"]: Remote(p["pid"], p["name"]) for p in players}
        self.state: dict = {"opened": [], "boss": {"on": "off", "hp": 0, "max": 0, "phase": 0}, "doors": [0] * len(self.map.doors), "power": False, "core": False, "found": [],
                            "corrupt": [], "false": [], "lights": 0, "intf": 0, "left": time_limit,
                            "obj": {"text": "", "tasks": []}, "phase": "playing"}
        self.state_at = time.time()
        self.notes: List[dict] = []
        self.read_keys: set = set()
        self.toasts: List[dict] = []
        self.banner: Optional[dict] = None
        self.popup: Optional[dict] = None
        self.panel: Optional[str] = None
        self.tx_msg = ""
        self.tx_msg_ok = False
        self.end: Optional[dict] = None
        self.x = self.y = 0.0
        self.have_pos = False
        self.face = 0.0
        self.moving = False
        self.last_sent = (9, 9, 9, False)
        self.last_send_t = 0.0
        self.discovered = bytearray(self.map.width * self.map.height)
        self.mini = pygame.Surface((self.map.width, self.map.height))
        self.mini.fill((6, 10, 14))
        self.last_reveal = (-99, -99)
        self.near = None
        self.t = 0.0
        self.last_door_snd = 0.0
        self.prev_doors: List[int] = list(self.state["doors"])
        self.lights_until = 0.0
        self.intf_until = 0.0
        self.names_by_pid = {p["pid"]: p["name"] for p in players}
        # combat
        self.zombies: Dict[int, ZRemote] = {}
        self.hp = 100
        self.ammo = 12
        self.dead = False
        self.reloading = False
        self.aim = 0.0
        self.fire = False
        self.tracers: List[dict] = []
        self.hurt_until = 0.0
        self.shoot_until = 0.0
        self.dead_since = 0.0
        self.last_dir = 0          # 0 front, 1 right, -1 left, 2 back
        self.walk_t = 0.0
        # inventory / world extras
        self.cur_weapon = "pistol"
        self.owned = ["pistol"]
        self.clips = {"pistol": 12}
        self.reserve = {"pistol": None}
        self.pickups: List[list] = []
        self.boss: Optional[list] = None
        self.orbs: List[list] = []
        self.telegraphs: List[dict] = []
        self.scan: Optional[dict] = None
        self.shake_until = 0.0
        self.shake_mag = 0.0
        self.flash_until = 0.0
        self.flash_color = (255, 255, 255)
        self.scare: Optional[dict] = None
        self.phantom: Optional[dict] = None
        self.whisper_text = ""
        self.whisper_until = 0.0
        self.next_ambient = time.time() + 25
        self.next_beat = 0.0
        self.flicker = 0
        self.reserve_now = -1

    # ----------------------------------------------------------------- helpers
    def solid_at(self, tx: int, ty: int) -> bool:
        m = self.map
        if tx < 0 or ty < 0 or tx >= m.width or ty >= m.height:
            return True
        if m.solid[ty * m.width + tx]:
            return True
        did = m.door_at.get((tx, ty))
        if did is not None and self.state["doors"][did] != 1:
            return True
        return False

    @property
    def lights_out(self) -> bool:
        return time.time() < self.lights_until

    @property
    def interference(self) -> bool:
        return time.time() < self.intf_until

    def time_left(self) -> float:
        left = self.state.get("left", 0.0)
        if self.state.get("phase") == "playing":
            left -= time.time() - self.state_at
        return max(0.0, left)

    def toast(self, text: str, kind: str = "info") -> None:
        self.toasts.append({"text": text, "kind": kind, "t": time.time()})
        self.toasts = self.toasts[-5:]

    # --------------------------------------------------------------- messages
    def apply(self, msg: dict) -> None:
        t = msg.get("t")
        if t == "snap":
            self._snap(msg)
        elif t == "state":
            self._state(msg)
        elif t == "notes":
            self.notes = list(msg.get("notes", []))
            self.read_keys = {n["key"] for n in self.notes}
        elif t == "read":
            self.popup = {"entry": msg["entry"], "t": time.time()}
            self.read_keys.add(msg["entry"]["key"])
            self.audio.play("terminal")
        elif t == "ui":
            if msg.get("ui") == "transmitter":
                self.panel = "transmitter"
                self.tx_msg = ""
                self.audio.play("terminal")
        elif t == "tx_result":
            self.tx_msg = msg.get("msg", "")
            self.tx_msg_ok = bool(msg.get("ok"))
            if msg.get("matched") is not None:
                self.tx_msg += f"  ({msg['matched']}/3 fields correct)"
            if msg.get("ok"):
                self.audio.play("transmitter")
            else:
                self.audio.play("error")
            if msg.get("close"):
                self.panel = None
        elif t == "toast":
            self.toast(msg.get("text", ""), msg.get("kind", "info"))
            if msg.get("snd"):
                self.audio.play(msg["snd"])
        elif t == "inv":
            self.cur_weapon = msg.get("cur", "pistol")
            self.owned = msg.get("owned", ["pistol"])
            self.clips = msg.get("clip", {})
            self.reserve = msg.get("reserve", {})
            self.weapon = self.cur_weapon
        elif t == "scan":
            self.scan = {"z": msg.get("zombies", []), "boss": msg.get("boss"), "until": time.time() + float(msg.get("dur", 20))}
        elif t == "fx":
            self._fx(msg)
        elif t == "ev":
            self._event(msg)
        elif t == "end":
            self.end = msg
            self.panel = None
            if msg.get("phase") == "victory":
                self.audio.play("victory")
                self.audio.play("victory2")
            else:
                self.audio.play("failure")

    def _event(self, msg: dict) -> None:
        k = msg.get("k")
        text = msg.get("text", "")
        if k == "echo":
            self.banner = {"text": "THE ECHO: " + text, "t": time.time()}
            self.audio.play("echo")
            self.audio.play("echo_glitch")
            dur = float(msg.get("dur", 10))
            if msg.get("ev") == "ECHO_RIFT":
                self.banner = {"text": text, "t": time.time()}
            if msg.get("ev") == "LIGHTS_OUT":
                self.lights_until = time.time() + dur
            elif msg.get("ev") == "SIGNAL_INTERFERENCE":
                self.intf_until = time.time() + dur
        elif k == "boss":
            self.banner = {"text": text, "t": time.time()}
            self.shake_until, self.shake_mag = time.time() + 0.8, 6
            self.audio.play("surge", 1.0)
            self.audio.play("stinger", 0.6)
        elif k == "boss_phase":
            self.banner = {"text": text, "t": time.time()}
            self.shake_until, self.shake_mag = time.time() + 0.5, 7
            self.audio.play("stinger", 0.6)
        elif k == "boss_summon":
            self.toast(text, "error")
            self.audio.play("groan", 0.8)
        elif k == "boss_dead":
            self.banner = {"text": text, "t": time.time()}
            self.flash_until, self.flash_color = time.time() + 0.6, (255, 240, 200)
            self.audio.play("victory2")
            self.audio.play("success")
        elif k == "power":
            self.toast(text, "good")
            self.audio.play("generator")
        elif k == "core":
            self.toast(text, "good")
            self.audio.play("success")
        elif k == "fragment":
            self.toast(text, "good")
            self.audio.play("success")
        else:
            self.toast(text, "info")

    def _state(self, msg: dict) -> None:
        old = self.state.get("doors", [])
        self.state.update({k: v for k, v in msg.items() if k != "t"})
        self.state_at = time.time()
        if len(self.state["doors"]) != len(self.map.doors):
            self.state["doors"] = [0] * len(self.map.doors)
        # door sounds (only for doors close to us, throttled)
        now = time.time()
        if now - self.last_door_snd > 0.15:
            for i, (a, b) in enumerate(zip(self.prev_doors, self.state["doors"])):
                if (a == 1) != (b == 1):
                    d = self.map.doors[i]
                    cx, cy = d.cells[0]
                    if math.hypot(cx * TILE - self.x, cy * TILE - self.y) < 7 * TILE:
                        self.audio.play("door_open" if b == 1 else "door_close", 0.5, 0.15)
                        self.last_door_snd = now
                        break
        self.prev_doors = list(self.state["doors"])
        lt = float(msg.get("lights", 0))
        if lt > 0:
            self.lights_until = max(self.lights_until, now + lt)
        elif lt == 0 and self.lights_until > now + 0.6:
            self.lights_until = now
        it = float(msg.get("intf", 0))
        if it > 0:
            self.intf_until = max(self.intf_until, now + it)
        elif it == 0:
            self.intf_until = min(self.intf_until, now)

    def _snap(self, msg: dict) -> None:
        now = time.time()
        for row in msg.get("p", []):
            try:
                pid, x, y, face, flags = row[:5]
                hp = row[5] if len(row) > 5 else 100
                ammo = row[6] if len(row) > 6 else 12
                aim = row[7] if len(row) > 7 else face
                widx = row[8] if len(row) > 8 else 0
                res = row[9] if len(row) > 9 else -1
            except (ValueError, TypeError):
                continue
            if pid == self.pid:
                self.hp, self.ammo = hp, ammo
                self.reserve_now = res
                self.reloading = bool(flags & 8)
                dead = bool(flags & 4)
                if dead and not self.dead:
                    self.dead_since = now
                self.dead = dead
                if not self.have_pos:
                    self.x, self.y, self.have_pos = x, y, True
                else:
                    err = math.hypot(x - self.x, y - self.y)
                    if err > 120:
                        self.x, self.y = x, y
                    elif err > 22:
                        self.x += (x - self.x) * 0.25
                        self.y += (y - self.y) * 0.25
                continue
            r = self.remote.get(pid)
            if r is None:
                r = self.remote[pid] = Remote(pid, f"P{pid}")
            r.tx, r.ty, r.face, r.aim = x, y, face, aim
            from .weapons import ORDER
            r.weapon = ORDER[widx] if 0 <= widx < len(ORDER) else "pistol"
            r.moving = bool(flags & 1)
            r.connected = bool(flags & 2)
            r.dead = bool(flags & 4)
            r.hp = hp
            if not r.seen:
                r.x, r.y, r.seen = x, y, True
        seen = set()
        for row in msg.get("z", []):
            try:
                zid, kind, x, y, face, hp, flags = row
            except (ValueError, TypeError):
                continue
            seen.add(zid)
            z = self.zombies.get(zid)
            if z is None:
                z = self.zombies[zid] = ZRemote(zid, kind, x, y)
                z.max_hp = ZMAXHP.get(kind, 60)
                z.hp = hp
            if hp < z.hp:
                z.hurt_until = now + 0.18
            z.hp, z.tx, z.ty, z.face, z.flags, z.seen_t = hp, x, y, face, flags, now
        for zid in [k for k in self.zombies if k not in seen]:
            del self.zombies[zid]
        self.boss = msg.get("b")
        self.orbs = msg.get("o", [])
        self.pickups = msg.get("k", [])

    def _fx(self, msg: dict) -> None:
        k = msg.get("k")
        now = time.time()
        if k == "shot":
            from .weapons import WEAPONS
            col = WEAPONS.get(msg.get("w", "pistol"), WEAPONS["pistol"])["color"]
            for (ex, ey) in msg.get("ends", [(msg["ex"], msg["ey"])]):
                self.tracers.append({"x": msg["x"], "y": msg["y"], "ex": ex, "ey": ey, "t": now, "hit": msg.get("hit"), "c": col})
            self.tracers = self.tracers[-40:]
            pid = msg.get("pid")
            dist = math.hypot(msg["x"] - self.x, msg["y"] - self.y)
            if dist < 12 * TILE:
                self.audio.play("shot", 0.45 if pid != self.pid else 0.7, 0.04)
            if pid == self.pid:
                self.shoot_until = now + 0.07
                if msg.get("w") == "shotgun":
                    self.shake_until, self.shake_mag = now + 0.12, 3
            elif pid in self.remote:
                self.remote[pid].shoot_until = now + 0.07
            if msg.get("hit"):
                self.audio.play("zombie_die" if msg.get("kill") else "zombie_hit", 0.6, 0.08)
        elif k == "hurt":
            self.hurt_until = now + 0.35
            self.audio.play("hurt", 0.8, 0.1)
            if msg.get("src") in ("boss", "orb"):
                self.shake_until, self.shake_mag = now + 0.25, 6
        elif k == "reload":
            self.audio.play("reload", 0.6)
        elif k == "empty":
            self.audio.play("empty", 0.7)
            self.toast("Out of ammo for this weapon.", "error")
        elif k == "respawn":
            self.x, self.y = msg["x"], msg["y"]
            self.audio.play("success")
        elif k == "telegraph":
            self.telegraphs.append(dict(msg, t=now))
            self.audio.play("echo", 0.35, 0.3)
        elif k == "slam":
            self.shake_until, self.shake_mag = now + 0.45, 9
            self.audio.play("surge", 0.7, 0.3)
            self.telegraphs.append({"shape": "ring", "x": msg["x"], "y": msg["y"], "r": msg["r"], "dur": 0.35, "t": now})
        elif k == "boss_cast":
            self.audio.play("echo_glitch", 0.5, 0.3)
        elif k == "teleport":
            self.x, self.y = msg["x"], msg["y"]
            self.flash_until, self.flash_color = now + 0.5, (180, 255, 255)
            self.shake_until, self.shake_mag = now + 0.3, 5
            self.audio.play("echo", 0.9)
            self.audio.play("echo_glitch", 0.7)
            self.toast("THE ECHO tore you through a rift!", "error")
        elif k == "jumpscare":
            self.scare = {"t": now, "n": msg.get("n", 0)}
            self.shake_until, self.shake_mag = now + 0.6, 10
            self.audio.play("stinger", 1.0, 0.5)
        elif k == "phantom":
            self.phantom = {"t": now, "n": msg.get("n", 0), "ang": self.t * 3.7 % 6.283}
            self.whisper_text = ["...behind you...", "...it hears you...", "...you are not alone..."][msg.get("n", 0) % 3]
            self.whisper_until = now + 3.0
            self.audio.play("whisper", 0.8, 1.0)

    def update(self, dt: float, mx: float, my: float, net, aim: float = 0.0, fire: bool = False) -> None:
        self.t += dt
        n = math.hypot(mx, my)
        if n > 1:
            mx, my = mx / n, my / n
        if self.end or not self.have_pos or self.dead:
            mx = my = 0
            fire = False
        self.aim, self.fire = aim, fire
        if mx or my:
            self.x, self.y = move_with_collision(self.solid_at, self.x, self.y, mx * PLAYER_SPEED * dt, my * PLAYER_SPEED * dt, PLAYER_HALF)
            self.face = math.atan2(my, mx)
        self.moving = bool(mx or my)
        self.walk_t += dt
        now = time.time()
        cur = (round(mx, 2), round(my, 2), round(aim, 1), bool(fire))
        if (cur != self.last_sent and now - self.last_send_t > 0.04) or now - self.last_send_t > 0.3:
            net.send({"t": "input", "mx": cur[0], "my": cur[1], "aim": cur[2], "fire": cur[3]})
            self.last_sent, self.last_send_t = cur, now
        k = min(1.0, dt * 16)
        for r in self.remote.values():
            r.x += (r.tx - r.x) * k
            r.y += (r.ty - r.y) * k
        for z in self.zombies.values():
            z.x += (z.tx - z.x) * k
            z.y += (z.ty - z.y) * k
        self.tracers = [t for t in self.tracers if now - t["t"] < 0.12]
        self.telegraphs = [t for t in self.telegraphs if now - t["t"] < t.get("dur", 1.0) + 0.1]
        if self.scare and now - self.scare["t"] > 0.9:
            self.scare = None
        if self.phantom and now - self.phantom["t"] > 2.2:
            self.phantom = None
        if self.scan and now > self.scan["until"]:
            self.scan = None
        # dread: heartbeat that speeds up as zombies close in, flickering light, distant noises
        nearest = min([math.hypot(z.x - self.x, z.y - self.y) for z in self.zombies.values()] +
                      ([math.hypot(self.boss[0] - self.x, self.boss[1] - self.y)] if self.boss else []) + [1e9])
        danger = max(0.0, min(1.0, 1.0 - nearest / (8 * TILE)))
        if self.hp < 35 and not self.dead:
            danger = max(danger, 0.8)
        if danger > 0.05 and now >= self.next_beat and not self.dead:
            self.audio.play("heartbeat", 0.25 + 0.6 * danger, 0.2)
            self.next_beat = now + 1.15 - 0.7 * danger
        self.flicker = int(self.rng_flicker(now, danger))
        if now >= self.next_ambient:
            self.next_ambient = now + 22 + (now * 7919 % 25)
            self.audio.play(["groan", "door_close", "echo", "whisper"][int(now) % 4], 0.22, 1.0)
        self.hurt_until = self.hurt_until
        self.near = nearest_interactable(self.map, self.x, self.y) if self.have_pos else None
        self._reveal()
        if self.toasts:
            self.toasts = [t for t in self.toasts if now - t["t"] < 5.0]
        if self.banner and now - self.banner["t"] > 6:
            self.banner = None

    def rng_flicker(self, now: float, danger: float) -> float:
        base = 0.0
        if int(now * 3.1) % 29 == 0:
            base += 14 * math.sin(now * 90)
        return base + danger * -6

    def _reveal(self) -> None:
        tx, ty = int(self.x // TILE), int(self.y // TILE)
        if (tx, ty) == self.last_reveal:
            return
        self.last_reveal = (tx, ty)
        m = self.map
        W, H = m.width, m.height
        r = REVEAL_RADIUS
        for y in range(max(0, ty - r), min(H, ty + r + 1)):
            for x in range(max(0, tx - r), min(W, tx + r + 1)):
                if (x - tx) ** 2 + (y - ty) ** 2 > r * r:
                    continue
                i = y * W + x
                if self.discovered[i]:
                    continue
                self.discovered[i] = 1
                t = m.tiles[i]
                if t == FLOOR:
                    self.mini.set_at((x, y), (96, 132, 144) if m.zone[i] == 0 else (120, 160, 170))
                elif t == WALL:
                    self.mini.set_at((x, y), (36, 48, 60))

    def interact(self, net) -> None:
        if self.near and not self.end and not self.dead:
            net.send({"t": "interact", "oid": self.near.id})

    def send_transmit(self, net, freq: str, chan: str, seq: str) -> None:
        net.send({"t": "transmit", "freq": freq, "chan": chan, "seq": seq})
