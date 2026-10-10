"""MAP 1: RESEARCH STATION A-17 generator."""
from __future__ import annotations

import random
from typing import Dict, List

from .generator import (BaseMapGenerator, GenerationError, Interactable, MapData, Prop, Room,
                        RoomCtx, RoomSpec)
from .. import clues as clue_mod

RESTRICTED = {"server_wing", "security", "comms", "restricted"}

ROOM_NAMES = {
    "hub": ["Central Atrium"],
    "main_lab": ["Main Laboratory", "Primary Research Hall"],
    "server_wing": ["Server Wing"],
    "lab": ["Research Lab {n}"],
    "archive": ["Data Archive"],
    "security": ["Security Wing"],
    "storage": ["Storage Bay {n}", "Cargo Store {n}"],
    "maintenance": ["Maintenance Section {n}"],
    "generator": ["Generator Hall"],
    "medical": ["Medical Wing", "Observation Ward"],
    "comms": ["Central Communications"],
    "restricted": ["Emergency Command", "Sealed Annex"],
    "quarters": ["Staff Quarters {n}", "Office {n}", "Break Room {n}"],
}

FLOORS = {
    "hub": "teal_0", "main_lab": "white", "server_wing": "server", "lab": "white", "archive": "wood_0",
    "security": "dark", "storage": "storage", "maintenance": "hazard", "generator": "hazard",
    "medical": "medical", "comms": "dark", "restricted": "server", "quarters": "lightwood",
}


class ResearchStationGenerator(BaseMapGenerator):
    ROOM_NAMES = ROOM_NAMES
    FLOORS = FLOORS
    map_id = "research_station"
    map_name = "Research Station A-17"
    width = 200
    height = 130

    def required_kinds(self):
        return {"hub", "comms", "generator", "server_wing", "archive", "security", "medical", "restricted", "main_lab"}

    # ------------------------------------------------------------------ plan
    def room_plan(self, rng: random.Random) -> List[RoomSpec]:
        counter: Dict[str, int] = {}

        def spec(kind, w, h, far=False, gap=3, restricted=None):
            counter[kind] = counter.get(kind, 0) + 1
            names = self.ROOM_NAMES[kind]
            name = rng.choice(names).format(n=f"{chr(64 + counter[kind])}-{rng.randint(1, 9)}")
            r = (kind in RESTRICTED) if restricted is None else restricted
            return RoomSpec(kind, name, w, h, r, self.FLOORS[kind], far, gap)

        plan: List[RoomSpec] = []
        plan.append(spec("hub", rng.randint(22, 28), rng.randint(16, 20)))
        plan.append(spec("comms", rng.randint(15, 19), rng.randint(12, 15), far=True))
        plan.append(spec("generator", rng.randint(10, 13), rng.randint(8, 10), far=True))
        plan.append(spec("server_wing", rng.randint(16, 24), rng.randint(11, 14)))
        plan.append(spec("archive", rng.randint(13, 18), rng.randint(9, 12)))
        plan.append(spec("security", rng.randint(9, 13), rng.randint(7, 10)))
        plan.append(spec("medical", rng.randint(11, 16), rng.randint(9, 12)))
        plan.append(spec("restricted", rng.randint(9, 12), rng.randint(7, 9)))
        for _ in range(rng.randint(1, 2)):
            plan.append(spec("main_lab", rng.randint(15, 22), rng.randint(10, 15)))
        for _ in range(rng.randint(3, 5)):
            plan.append(spec("lab", rng.randint(8, 14), rng.randint(6, 10)))
        for _ in range(rng.randint(3, 5)):
            plan.append(spec("storage", rng.randint(8, 14), rng.randint(6, 12)))
        for _ in range(rng.randint(2, 3)):
            plan.append(spec("maintenance", rng.randint(7, 11), rng.randint(5, 8)))
        target = rng.randint(30, 40)
        while len(plan) < target:
            kind = rng.choice(["quarters", "quarters", "quarters", "lab", "storage"])
            if kind == "quarters":
                plan.append(spec(kind, rng.randint(6, 9), rng.randint(5, 7), gap=2))
            elif kind == "lab":
                plan.append(spec(kind, rng.randint(7, 10), rng.randint(6, 8), gap=2))
            else:
                plan.append(spec(kind, rng.randint(7, 10), rng.randint(6, 8), gap=2))
        # place big required rooms first (hub first), the rest in random order
        head = plan[:8]
        tail = plan[8:]
        rng.shuffle(tail)
        return head + tail

    # ----------------------------------------------------------------- dress
    def dress_room(self, m: MapData, rng: random.Random, ctx: RoomCtx) -> None:
        fn = getattr(self, "_dress_" + ctx.room.kind, None)
        if fn:
            fn(m, rng, ctx)

    def _add_prop(self, m, ctx, sprite, x, y, w=1, h=1, rot=0, solid=True, allow_reserved=False):
        if ctx.place(x, y, w, h, allow_reserved=allow_reserved):
            m.props.append(Prop(sprite, x, y, w, h, rot, solid))
            return True
        return False

    def _wall_props(self, m, rng, ctx, sprite, count, w=1, h=1, oriented=True):
        """Place up to `count` props flush against walls.  Sprites are drawn facing down (south)."""
        n = 0
        for (x, y, rot, fw, fh) in ctx.wall_spots(w, h):
            if n >= count:
                break
            if self._add_prop(m, ctx, sprite, x, y, fw, fh, rot if oriented else 0):
                n += 1
        return n

    def _island_props(self, m, rng, ctx, sprites, count, w=1, h=1, margin=2):
        r = ctx.room
        n, tries = 0, 0
        while n < count and tries < count * 12:
            tries += 1
            if r.w - 2 * margin - w < 0 or r.h - 2 * margin - h < 0:
                break
            x = rng.randint(r.x + margin, r.x + r.w - margin - w)
            y = rng.randint(r.y + margin, r.y + r.h - margin - h)
            if self._add_prop(m, ctx, rng.choice(sprites) if isinstance(sprites, list) else sprites, x, y, w, h):
                n += 1
        return n

    def _dress_hub(self, m, rng, ctx):
        r = ctx.room
        step = rng.choice((5, 6))
        for y in range(r.y + 3, r.y + r.h - 3, step):
            for x in range(r.x + 4, r.x + r.w - 4, step):
                if rng.random() < 0.55 and not (abs(x - (r.x + r.w // 2)) < 4 and abs(y - (r.y + r.h // 2)) < 3):
                    self._add_prop(m, ctx, "pillar", x, y)
        self._wall_props(m, rng, ctx, "bush_green", 3, 2, 2, oriented=False)
        self._wall_props(m, rng, ctx, "sofa_green", 2, 3, 1)
        self._wall_props(m, rng, ctx, "locker", 2)

    def _dress_main_lab(self, m, rng, ctx):
        r = ctx.room
        for y in range(r.y + 3, r.y + r.h - 3, 4):
            for x in range(r.x + 3, r.x + r.w - 5, 6):
                if rng.random() < 0.7:
                    self._add_prop(m, ctx, "lab_table_long", x, y, 2, 1)
                    if rng.random() < 0.5:
                        self._add_prop(m, ctx, "terminal_dead", x + 2, y, 1, 1, solid=True)
        self._wall_props(m, rng, ctx, "centrifuge", 2, oriented=False)
        self._wall_props(m, rng, ctx, "shelf", rng.randint(2, 4))
        self._wall_props(m, rng, ctx, "lab_sink", 1, oriented=False)
        self._wall_props(m, rng, ctx, "terminal_dead", 2)
        self._wall_props(m, rng, ctx, "medical_cabinet", 1)

    def _dress_lab(self, m, rng, ctx):
        r = ctx.room
        self._island_props(m, rng, ctx, ["lab_table_long"], rng.randint(1, 3), 2, 1, margin=2)
        self._wall_props(m, rng, ctx, "lab_table", rng.randint(1, 3))
        self._wall_props(m, rng, ctx, "centrifuge", 1, oriented=False)
        self._wall_props(m, rng, ctx, "terminal_dead", 1)
        self._wall_props(m, rng, ctx, "shelf", rng.randint(0, 2))
        self._wall_props(m, rng, ctx, "lab_burner", 1, oriented=False)

    def _dress_server_wing(self, m, rng, ctx):
        r = ctx.room
        x = r.x + 2
        sprites = ["server_rack_a", "server_rack_b", "server_rack_c"]
        while x < r.x + r.w - 2:
            y = r.y + 2
            while y < r.y + r.h - 2:
                if rng.random() < 0.8:
                    self._add_prop(m, ctx, rng.choice(sprites), x, y)
                y += 1 if rng.random() < 0.85 else 2
            x += 3
        self._wall_props(m, rng, ctx, "electrical_panel", 2)

    def _dress_archive(self, m, rng, ctx):
        r = ctx.room
        for y in range(r.y + 2, r.y + r.h - 2, 3):
            x = r.x + 2
            while x < r.x + r.w - 2:
                seglen = rng.randint(2, 4)
                for k in range(seglen):
                    if x + k < r.x + r.w - 2:
                        self._add_prop(m, ctx, "shelf", x + k, y)
                x += seglen + rng.randint(1, 2)
        self._wall_props(m, rng, ctx, "filing_cabinet", 3)
        self._wall_props(m, rng, ctx, "shelf", 3)

    def _dress_security(self, m, rng, ctx):
        self._wall_props(m, rng, ctx, "locker", 3)
        self._wall_props(m, rng, ctx, "terminal_dead", 2)
        self._wall_props(m, rng, ctx, "filing_cabinet", 1)
        self._island_props(m, rng, ctx, ["lab_table"], 1, 1, 1, margin=3)

    def _dress_storage(self, m, rng, ctx):
        sprites = ["crate_wood_large", "crate_wood_b", "crate_metal", "barrel_orange", "barrel_teal", "crate_wood_small"]
        self._wall_props(m, rng, ctx, "shelf", rng.randint(1, 3))
        r = ctx.room
        for _ in range(rng.randint(3, 6)):
            x = rng.randint(r.x + 1, r.x + r.w - 3)
            y = rng.randint(r.y + 1, r.y + r.h - 3)
            for _k in range(rng.randint(1, 3)):
                self._add_prop(m, ctx, rng.choice(sprites), x + rng.randint(0, 1), y + rng.randint(0, 1), 1, 1, solid=True)
        self._wall_props(m, rng, ctx, "locker", 1)

    def _dress_maintenance(self, m, rng, ctx):
        self._wall_props(m, rng, ctx, "pipe_straight", rng.randint(3, 6))
        self._wall_props(m, rng, ctx, "pipe_valve", 1)
        self._wall_props(m, rng, ctx, "electrical_panel", 2)
        self._wall_props(m, rng, ctx, "battery_bank", 1, 2, 1)
        self._island_props(m, rng, ctx, ["barrel_orange", "crate_metal"], rng.randint(1, 3), 1, 1, margin=2)

    def _dress_generator(self, m, rng, ctx):
        self._wall_props(m, rng, ctx, "pipe_straight", 3)
        self._wall_props(m, rng, ctx, "pipe_hazard", 2)
        self._wall_props(m, rng, ctx, "electrical_panel", 2)
        self._wall_props(m, rng, ctx, "battery_bank", 2, 2, 1)
        self._island_props(m, rng, ctx, ["barrel_orange"], 2, 1, 1, margin=2)

    def _dress_medical(self, m, rng, ctx):
        r = ctx.room
        sprites = [("bed_orange_single", 1, 3), ("bed_green_double", 2, 3), ("bed_orange_double", 2, 3)]
        x = r.x + 2
        while x < r.x + r.w - 3:
            s, bw, bh = rng.choice(sprites)
            if self._add_prop(m, ctx, s, x, r.y + 1, bw, bh):
                x += bw + 1
            else:
                x += 1
        self._wall_props(m, rng, ctx, "med_scanner", 1, 2, 1)
        self._wall_props(m, rng, ctx, "medical_cabinet", 2)
        self._wall_props(m, rng, ctx, "terminal_dead", 1)

    def _dress_comms(self, m, rng, ctx):
        r = ctx.room
        # holo table in the middle-left, server racks and consoles along the sides
        self._add_prop(m, ctx, "holo_table", r.x + 3, r.y + r.h // 2 - 1, 2, 2)
        self._wall_props(m, rng, ctx, "server_rack_a", 3)
        self._wall_props(m, rng, ctx, "electrical_panel", 2)
        self._wall_props(m, rng, ctx, "terminal_dead", 2)

    def _dress_restricted(self, m, rng, ctx):
        self._wall_props(m, rng, ctx, "locker", 3)
        self._wall_props(m, rng, ctx, "crate_metal", 2)
        self._wall_props(m, rng, ctx, "filing_cabinet", 2)
        self._wall_props(m, rng, ctx, "med_scanner", 1, 2, 1)

    def _dress_quarters(self, m, rng, ctx):
        r = ctx.room
        if rng.random() < 0.6:
            s, bw, bh = rng.choice([("bed_orange_single", 1, 3), ("bed_green_double", 2, 3)])
            self._add_prop(m, ctx, s, r.x + rng.randint(0, max(0, r.w - bw - 1)), r.y, bw, min(bh, r.h - 3) if r.h > 4 else bh)
        self._wall_props(m, rng, ctx, "locker", 1)
        self._wall_props(m, rng, ctx, "desk_wood", 1, 3, 1)
        self._wall_props(m, rng, ctx, "shelf", rng.randint(0, 1))
        self._wall_props(m, rng, ctx, "bush_orange", 1, 2, 2, oriented=False)

    # ---------------------------------------------------------------- finish
    def _place_object(self, m, rng, ctx: RoomCtx, oid, kind, family, w, h, label, needs_power=False, wall=True):
        """Place an interactable in a room; returns Interactable or None."""
        spots = ctx.wall_spots(w, h) if wall else []
        if not wall or not spots:
            r = ctx.room
            spots = [(rng.randint(r.x + 2, r.x + r.w - 2 - w), rng.randint(r.y + 2, r.y + r.h - 2 - h), 0, w, h) for _ in range(60)]
        for (x, y, rot, fw, fh) in spots:
            if ctx.place(x, y, fw, fh, access=True):
                obj = Interactable(oid, kind, family, x, y, fw, fh, rot, ctx.room.id, label, needs_power)
                m.objects.append(obj)
                return obj
        return None

    # weapon crate room preferences (some are open from the start, some are behind restricted doors)
    CRATE_PREFS = {"shotgun": ["storage", "lab", "maintenance"], "smg": ["quarters", "lab", "archive", "storage"],
                   "rifle": ["security", "restricted", "server_wing"], "plasma": ["restricted", "server_wing", "medical"]}

    def _place_extras(self, m, rng, ctxs, by_kind, secret) -> None:
        """Weapon crates, medical stations and camera consoles (extra map functionality)."""
        secret["weapons"] = {}
        used = set()
        for wname, kinds in self.CRATE_PREFS.items():
            cands = []
            for k in kinds:
                opts = [r for r in by_kind.get(k, []) if r.id not in used]
                rng.shuffle(opts)
                cands.extend(opts)
            for r in cands:
                o = self._place_object(m, rng, ctxs[r.id], f"crate_{wname}", "weapon_crate", "weapon_crate", 1, 1, "WEAPON CRATE", needs_power=r.restricted)
                if o:
                    secret["weapons"][o.id] = wname
                    used.add(r.id)
                    break
        if len(secret["weapons"]) < 3:
            raise GenerationError("not enough weapon crates")
        for r in by_kind.get("medical", [])[:1] + by_kind.get("hub", [])[:1]:
            self._place_object(m, rng, ctxs[r.id], f"med_{r.id}", "med_station", "med_station", 1, 1, "MEDICAL STATION")
        for k in ("security", "server_wing"):
            for r in by_kind.get(k, [])[:1]:
                self._place_object(m, rng, ctxs[r.id], f"cam_{r.id}", "camera", "camera", 1, 1, "CAMERA NETWORK", needs_power=True)

    def finish(self, m: MapData, rng: random.Random, ctxs: Dict[int, RoomCtx]) -> None:
        by_kind: Dict[str, List[Room]] = {}
        for r in m.rooms:
            by_kind.setdefault(r.kind, []).append(r)
        hub = by_kind["hub"][0]

        # --- key machinery
        gen_room = by_kind["generator"][0]
        gen = self._place_object(m, rng, ctxs[gen_room.id], "generator", "generator", "generator", 2, 2, "BACKUP GENERATOR", wall=True)
        sw = by_kind["server_wing"][0]
        core = self._place_object(m, rng, ctxs[sw.id], "core", "core", "signal_core", 2, 2, "SIGNAL CORE", needs_power=True, wall=False)
        comms = by_kind["comms"][0]
        tx = None
        cc = ctxs[comms.id]
        # transmitter on the wall opposite the biggest door side, 3x3
        tx = self._place_object(m, rng, cc, "transmitter", "transmitter", "transmitter", 3, 3, "EMERGENCY TRANSMITTER", needs_power=True, wall=True)
        if not (gen and core and tx):
            raise GenerationError("could not place key machinery")
        m.meta.update({"generator_id": gen.id, "core_id": core.id, "transmitter_id": tx.id, "hub_room": hub.id,
                       "comms_room": comms.id, "server_room": sw.id, "generator_room": gen_room.id})

        # --- clues
        secret = clue_mod.make_secret(rng)
        needs = clue_mod.FRAGMENTS
        prefs = {
            "freq": ["archive", "main_lab", "lab"],
            "chan": ["security", "restricted", "archive"],
            "seq1": ["medical", "lab", "storage"],
            "seq2": ["storage", "lab", "main_lab", "quarters"],
            "seq3": ["server_wing", "restricted", "maintenance"],
        }
        used_rooms = set()
        fam_for = {"archive": "archive", "security": "console_security", "restricted": "console_security",
                   "medical": "medical"}
        frag_objs = {}
        for cid in needs:
            placed = None
            cands: List[Room] = []
            for k in prefs[cid]:
                opts = [r for r in by_kind.get(k, []) if r.id not in used_rooms]
                rng.shuffle(opts)
                cands.extend(opts)
            for r in cands:
                fam = fam_for.get(r.kind, "terminal")
                obj = self._place_object(m, rng, ctxs[r.id], "clue_" + cid, "terminal", fam, 1, 1,
                                         "SIGNAL TERMINAL", needs_power=r.restricted)
                if obj:
                    placed = (r, obj)
                    break
            if not placed:
                raise GenerationError("could not place clue " + cid)
            used_rooms.add(placed[0].id)
            placed[1].label = clue_mod.terminal_label(placed[0].kind)
            obj = placed[1]
            secret["objects"][obj.id] = {"kind": "clue", "clue": cid, "room": placed[0].name}
            frag_objs[cid] = obj
        m.meta["clue_ids"] = [frag_objs[c].id for c in needs]

        # --- notes (hints) + decoy logs spread over rooms
        note_defs = clue_mod.make_notes(rng, m, secret)
        candidates = [r for r in m.rooms if r.kind not in ("hub",)]
        rng.shuffle(candidates)
        n_logs = 0
        nd = 0
        for r in candidates:
            if n_logs >= 18:
                break
            if r.kind == "comms" and rng.random() < 0.6:
                continue
            fam = fam_for.get(r.kind, "terminal")
            if note_defs and (n_logs < len(note_defs) or rng.random() < 0.3):
                oid = f"note_{nd}"
                obj = self._place_object(m, rng, ctxs[r.id], oid, "terminal", fam, 1, 1, clue_mod.terminal_label(r.kind), needs_power=r.restricted)
                if obj:
                    secret["objects"][oid] = {"kind": "note", "note": note_defs[nd % len(note_defs)], "room": r.name}
                    nd += 1
                    n_logs += 1
                    continue
            elif rng.random() < 0.55:
                oid = f"log_{n_logs}"
                obj = self._place_object(m, rng, ctxs[r.id], oid, "terminal", fam, 1, 1, clue_mod.terminal_label(r.kind), needs_power=r.restricted)
                if obj:
                    secret["objects"][oid] = {"kind": "log", "log": clue_mod.random_log(rng, r), "room": r.name}
                    n_logs += 1
        # dead-end logs
        for (sx, sy) in m.meta.get("stubs", [])[:4]:
            pass
        m.secret = secret
        self._place_extras(m, rng, ctxs, by_kind, secret)

        # --- spawns in the hub (spaced free cells, reachable)
        hc = ctxs[hub.id]
        free = hc.free_cells()
        # prefer cells away from the lanes' immediate door steps, shuffle for variety
        rng.shuffle(free)
        spawns: List = []
        for (x, y) in free:
            if all((abs(x - sx) + abs(y - sy)) >= 2 for sx, sy in spawns):
                spawns.append((x, y))
            if len(spawns) >= 20:
                break
        if len(spawns) < 16:
            raise GenerationError("not enough spawn cells")
        m.spawns = spawns
