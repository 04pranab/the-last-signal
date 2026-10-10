"""THE ECHO: server side environmental anomaly / event system.

Events are small classes registered in ``EVENTS``.  The :class:`EchoDirector`
schedules them with global cooldowns so they never spam or become unfair.  More
sophisticated behaviour (movement, targeting players ...) can later be added as
new event classes or a new director without touching networking or the world.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional

from .config import TILE

FIRST_EVENT_DELAY = 50.0
MIN_GAP = 30.0
MAX_GAP = 65.0
SAME_EVENT_COOLDOWN = 110.0
OBJECT_COOLDOWN = 150.0


class EchoEvent:
    name = "base"
    weight = 1.0
    duration = (10.0, 15.0)
    text = "THE ECHO stirs."

    def can_start(self, world) -> bool:
        return True

    def start(self, world, rng: random.Random, dur: float) -> Optional[dict]:
        """Apply the event.  Return extra payload for clients or None to cancel."""
        return {}


class LightsOut(EchoEvent):
    name = "LIGHTS_OUT"
    weight = 1.0
    duration = (12.0, 18.0)
    text = "The lights die. THE ECHO is near."

    def can_start(self, world):
        return world.t >= world.fx.get("lights_until", 0)

    def start(self, world, rng, dur):
        world.fx["lights_until"] = world.t + dur
        return {}


class TerminalCorruption(EchoEvent):
    name = "TERMINAL_CORRUPTION"
    weight = 1.2
    duration = (20.0, 30.0)
    text = "Terminals are filling with static."

    def start(self, world, rng, dur):
        cands = [o for o in world.map.objects
                 if o.kind == "terminal" and world.t >= world.obj_cooldown.get(o.id, 0)
                 and world.t >= world.corrupt_until.get(o.id, 0)]
        if not cands:
            return None
        rng.shuffle(cands)
        chosen = cands[: rng.randint(1, 2)]
        for o in chosen:
            world.corrupt_until[o.id] = world.t + dur
            world.obj_cooldown[o.id] = world.t + dur + OBJECT_COOLDOWN
        return {"objs": [o.id for o in chosen]}


class DoorMalfunction(EchoEvent):
    name = "DOOR_MALFUNCTION"
    weight = 1.0
    duration = (9.0, 14.0)
    text = "Doors are jamming across the station."

    def start(self, world, rng, dur):
        # pick doors near a random connected player, never ones a player is standing in
        pls = [p for p in world.players.values() if p.connected]
        if not pls:
            return None
        p = rng.choice(pls)
        cands = []
        for d in world.map.doors:
            cx, cy = d.cells[0]
            if abs(cx * TILE - p.x) + abs(cy * TILE - p.y) < 14 * TILE and world.t >= world.jam_until.get(d.id, 0):
                cands.append(d)
        if not cands:
            return None
        rng.shuffle(cands)
        chosen = cands[: rng.randint(2, 4)]
        for d in chosen:
            world.jam_until[d.id] = world.t + dur
        return {"doors": [d.id for d in chosen]}


class SignalInterference(EchoEvent):
    name = "SIGNAL_INTERFERENCE"
    weight = 0.9
    duration = (12.0, 20.0)
    text = "Signal interference. Transmissions are failing."

    def can_start(self, world):
        return world.t >= world.fx.get("intf_until", 0)

    def start(self, world, rng, dur):
        world.fx["intf_until"] = world.t + dur
        return {}


class FalseTerminalMessage(EchoEvent):
    name = "FALSE_TERMINAL_MESSAGE"
    weight = 1.1
    duration = (30.0, 45.0)
    text = "THE ECHO is whispering false data into the terminals."

    def start(self, world, rng, dur):
        cands = [oid for oid in world.map.meta.get("clue_ids", [])
                 if world.t >= world.obj_cooldown.get(oid, 0) and world.t >= world.false_until.get(oid, 0)]
        if not cands:
            return None
        oid = rng.choice(cands)
        world.false_until[oid] = world.t + dur
        world.obj_cooldown[oid] = world.t + dur + OBJECT_COOLDOWN
        return {"objs": [oid]}


class ZombieSurge(EchoEvent):
    name = "ZOMBIE_SURGE"
    weight = 0.9
    duration = (10.0, 12.0)
    text = "THE ECHO is raising the dead. They are coming for you."

    def start(self, world, rng, dur):
        pls = [p for p in world.players.values() if p.connected and not p.dead]
        if not pls:
            return None
        p = rng.choice(pls)
        n = world.zombies.spawn_group(rng.randint(4, 3 + max(2, min(6, len(pls) * 2))), (p.x, p.y))
        if n == 0:
            return None
        return {"n": n}


class EchoRift(EchoEvent):
    """Teleports a random player to a random room of the station."""
    name = "ECHO_RIFT"
    weight = 0.8
    duration = (3.0, 3.0)
    text = "THE ECHO tears open a rift."

    def start(self, world, rng, dur):
        pls = [p for p in world.players.values() if p.connected and not p.dead]
        if not pls:
            return None
        p = rng.choice(pls)
        if not world.teleport_player(p.pid, rng):
            return None
        return {"pid": p.pid, "text": f"THE ECHO tore {p.name} through a rift!"}


class Jumpscare(EchoEvent):
    """A runner lunges out of the dark right behind one player, with a screen scare."""
    name = "JUMPSCARE"
    weight = 0.9
    duration = (4.0, 4.0)
    text = ""

    def can_start(self, world):
        return world.zombies_enabled

    def start(self, world, rng, dur):
        pls = [p for p in world.players.values() if p.connected and not p.dead and world.t > p.invuln_until]
        if not pls:
            return None
        p = rng.choice(pls)
        # runner appears 5-7 tiles away on a free cell, awake and hunting
        made = None
        for _ in range(80):
            a = rng.uniform(0, 6.283)
            d = rng.uniform(5.0, 7.0) * TILE
            x, y = p.x + math.cos(a) * d, p.y + math.sin(a) * d
            if not world.solid_at(int(x // TILE), int(y // TILE)):
                made = world.zombies.add("runner", x, y, awake=True)
                break
        if not made:
            return None
        world.send(p.pid, {"t": "fx", "k": "jumpscare", "n": rng.randint(0, 2)})
        return {"silent": True, "pid": p.pid}


class Phantom(EchoEvent):
    """Harmless hallucination: shadows and whispers for one player."""
    name = "PHANTOM"
    weight = 0.9
    duration = (6.0, 6.0)
    text = ""

    def start(self, world, rng, dur):
        pls = [p for p in world.players.values() if p.connected and not p.dead]
        if not pls:
            return None
        p = rng.choice(pls)
        world.send(p.pid, {"t": "fx", "k": "phantom", "n": rng.randint(0, 2)})
        return {"silent": True, "pid": p.pid}


EVENTS: Dict[str, EchoEvent] = {e.name: e for e in (LightsOut(), TerminalCorruption(), DoorMalfunction(),
                                                      SignalInterference(), FalseTerminalMessage(), ZombieSurge(), EchoRift(), Jumpscare(), Phantom())}


class EchoDirector:
    def __init__(self, world, seed: int = 0, enabled: bool = True):
        self.world = world
        self.rng = random.Random((seed ^ 0xEC40) & 0xFFFFFFFF)
        self.enabled = enabled
        self.next_at = FIRST_EVENT_DELAY + self.rng.uniform(0, 30)
        self.last_by_event: Dict[str, float] = {}
        self.count = 0

    def update(self) -> None:
        w = self.world
        if not self.enabled or w.phase != "playing" or w.t < self.next_at:
            return
        if not any(p.connected for p in w.players.values()):
            return
        self.trigger()

    def trigger(self, name: Optional[str] = None) -> Optional[str]:
        """Start an event now (random if name is None).  Returns the event name or None."""
        w = self.world
        options: List[EchoEvent] = []
        for ev in EVENTS.values():
            if name and ev.name != name:
                continue
            if not name and w.t - self.last_by_event.get(ev.name, -1e9) < SAME_EVENT_COOLDOWN:
                continue
            if ev.can_start(w):
                options.append(ev)
        self.next_at = w.t + self.rng.uniform(MIN_GAP, MAX_GAP)
        if not options:
            return None
        ev = self.rng.choices(options, weights=[e.weight for e in options])[0]
        dur = self.rng.uniform(*ev.duration)
        payload = ev.start(w, self.rng, dur)
        if payload is None:
            return None
        self.last_by_event[ev.name] = w.t
        self.count += 1
        if payload.get("silent"):
            self.next_at = w.t + self.rng.uniform(MIN_GAP * 0.6, MAX_GAP * 0.7)
        else:
            msg = {"t": "ev", "k": "echo", "ev": ev.name, "dur": round(dur, 1), "text": ev.text}
            msg.update(payload)
            w.broadcast(msg)
        w.dirty = True
        return ev.name
