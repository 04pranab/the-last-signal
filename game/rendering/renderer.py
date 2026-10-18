"""World renderer: cached static chunks + dynamic doors, objects, players and lighting."""
from __future__ import annotations

import math
from collections import OrderedDict
from typing import Dict, List, Tuple

import pygame

from ..config import TILE
from ..maps.generator import FLOOR, WALL, MapData
from .sprites import SpriteLibrary

CHUNK = 8                      # tiles per chunk side (512 px)
CHUNK_PX = CHUNK * TILE
MAX_CHUNKS = 90
LIGHT_RADIUS = 8.5 * TILE
LIGHT_RADIUS_DARK = 3.2 * TILE


ROOM_TINT = {
    "main_lab": (150, 220, 255, 16), "lab": (150, 220, 255, 14), "archive": (255, 190, 110, 22), "server_wing": (80, 120, 255, 26),
    "security": (255, 170, 90, 18), "storage": (200, 170, 120, 16), "maintenance": (255, 200, 60, 20), "generator": (255, 160, 60, 24),
    "medical": (170, 255, 210, 18), "comms": (90, 255, 200, 22), "restricted": (255, 70, 70, 28), "quarters": (255, 210, 150, 16),
    "hub": (140, 190, 230, 12),
}


def name_ok(lib, n: str) -> bool:
    return n in lib.sprites


class WorldRenderer:
    def __init__(self, lib: SpriteLibrary, m: MapData):
        self.lib = lib
        self.m = m
        self.light_r = float(m.meta.get("light_tiles", 8.5)) * TILE
        self.ambient = int(m.meta.get("ambient", 236))
        self.lamps = [p for p in m.props if p.sprite == "lantern"]
        self._shadow: Dict[Tuple[int, int], pygame.Surface] = {}
        self._ao = {}
        self._tint = {}
        self.chunks: "OrderedDict[Tuple[int,int], pygame.Surface]" = OrderedDict()
        self.prop_index: Dict[Tuple[int, int], List] = {}
        for p in m.props:
            for cy in range(p.y // CHUNK, (p.y + p.h - 1) // CHUNK + 1):
                for cx in range(p.x // CHUNK, (p.x + p.w - 1) // CHUNK + 1):
                    self.prop_index.setdefault((cx, cy), []).append(p)
        self.room_floor = {r.id + 1: r.floor for r in m.rooms}

    # ---------------------------------------------------------- static chunks
    def _floor_surface(self, x: int, y: int, zone: int) -> pygame.Surface:
        key = self.room_floor.get(zone, "teal")
        fl = self.lib.floors
        if "grass_0" in fl:                       # open world ground
            if zone == 255:
                return fl["road_%d" % ((x * 7 + y * 3) % 4)]
            if zone == 0:
                s1 = ((x // 2) * 73856093 ^ (y // 2) * 19349663 ^ self.m.seed) % 100
                s2 = ((x // 7) * 83492791 ^ (y // 7) * 2654435761 ^ self.m.seed) % 100
                h = 0.3 * s1 + 0.7 * s2
                if h < 50:
                    return fl["grass_%d" % ((x * 3 + y * 5) % 4)]
                return fl["wasteland_%d" % ((x + y * 2) % 3)]
        if zone == 0 and "dirt_0" in fl:
            return fl["dirt_%d" % ((x * 3 + y * 5 + (x * y) % 3) % 4)]
        if key.startswith("teal") or zone == 0:
            return fl["teal_%d" % ((x * 3 + y * 5 + (x * y) % 3) % 5)]
        if key in ("dirt_1",) and "dirt_0" in fl:
            return fl["dirt_%d" % ((x + y) % 4)]
        if key == "wood_0":
            return fl["wood_%d" % ((x + y * 2) % 6)]
        if key == "lightwood":
            return fl["lightwood"]
        return fl.get(key, fl["teal_0"])

    def _build_chunk(self, cx: int, cy: int) -> pygame.Surface:
        m, lib = self.m, self.lib
        surf = pygame.Surface((CHUNK_PX, CHUNK_PX))
        surf.fill((5, 8, 12))
        W, H = m.width, m.height
        wall_top, wall_face = lib.sprites["wall_top"], lib.sprites["wall_face"]
        for ty in range(CHUNK):
            y = cy * CHUNK + ty
            if y < 0 or y >= H:
                continue
            for tx in range(CHUNK):
                x = cx * CHUNK + tx
                if x < 0 or x >= W:
                    continue
                t = m.tiles[y * W + x]
                if t == FLOOR:
                    surf.blit(self._floor_surface(x, y, m.zone[y * W + x]), (tx * TILE, ty * TILE))
                elif t == WALL:
                    below = y + 1 < H and m.tiles[(y + 1) * W + x] == FLOOR
                    surf.blit(wall_face if below else wall_top, (tx * TILE, ty * TILE))
        self._decorate(surf, cx, cy)
        for p in self.prop_index.get((cx, cy), []):
            img = lib.sprite(p.sprite, p.w, p.h, p.rot)
            px, py = (p.x - cx * CHUNK) * TILE, (p.y - cy * CHUNK) * TILE
            if p.solid and p.sprite not in ("lantern", "rails_h"):
                surf.blit(self._shadow_for(p.w * TILE, p.h * TILE), (px + 5, py + 8))
            surf.blit(img, (px, py))
        self._room_tints(surf, cx, cy)
        return surf

    # ---- visual polish baked into the static chunks
    def _shadow_for(self, w: int, h: int) -> pygame.Surface:
        s = self._shadow.get((w, h))
        if s is None:
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(s, (0, 0, 0, 80), (0, 0, w, h), border_radius=8)
            self._shadow[(w, h)] = s
        return s

    def _ao_surface(self, kind: str) -> pygame.Surface:
        s = self._ao.get(kind)
        if s is None:
            s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            for i in range(14):
                a = int(70 * (1 - i / 14) ** 2)
                if kind == "top":
                    pygame.draw.line(s, (0, 0, 0, a), (0, i), (TILE, i))
                elif kind == "left":
                    pygame.draw.line(s, (0, 0, 0, a), (i, 0), (i, TILE))
                else:
                    pygame.draw.line(s, (0, 0, 0, a), (TILE - 1 - i, 0), (TILE - 1 - i, TILE))
            self._ao[kind] = s
        return s

    def _decorate(self, surf, cx, cy) -> None:
        m, lib = self.m, self.lib
        W, H = m.width, m.height
        names = ["decal_blood_0", "decal_blood_1", "decal_blood_2", "decal_scorch", "decal_crack_a", "decal_crack_b", "decal_stain"]
        for ty in range(CHUNK):
            y = cy * CHUNK + ty
            if not 0 <= y < H:
                continue
            for tx in range(CHUNK):
                x = cx * CHUNK + tx
                if not 0 <= x < W or m.tiles[y * W + x] != FLOOR:
                    continue
                # ambient occlusion next to walls
                if y > 0 and m.tiles[(y - 1) * W + x] == WALL:
                    surf.blit(self._ao_surface("top"), (tx * TILE, ty * TILE))
                if x > 0 and m.tiles[y * W + x - 1] == WALL:
                    surf.blit(self._ao_surface("left"), (tx * TILE, ty * TILE))
                if x + 1 < W and m.tiles[y * W + x + 1] == WALL:
                    surf.blit(self._ao_surface("right"), (tx * TILE, ty * TILE))
                h = (x * 73856093 ^ y * 19349663 ^ m.seed) & 0xFFFF
                if h % 100 < 4 and name_ok(lib, names[h % len(names)]):
                    dec = lib.sprites[names[h % len(names)]]
                    surf.blit(dec, (tx * TILE, ty * TILE))

    def _room_tints(self, surf, cx, cy) -> None:
        m = self.m
        x0, y0 = cx * CHUNK, cy * CHUNK
        for r in m.rooms:
            col = ROOM_TINT.get(r.kind)
            if not col:
                continue
            ix0, iy0 = max(r.x, x0), max(r.y, y0)
            ix1, iy1 = min(r.x + r.w, x0 + CHUNK), min(r.y + r.h, y0 + CHUNK)
            if ix0 >= ix1 or iy0 >= iy1:
                continue
            key = ((ix1 - ix0) * TILE, (iy1 - iy0) * TILE, col)
            t = self._tint.get(key)
            if t is None:
                t = pygame.Surface(key[:2], pygame.SRCALPHA)
                t.fill(col)
                self._tint[key] = t
            surf.blit(t, ((ix0 - x0) * TILE, (iy0 - y0) * TILE))

    def chunk(self, cx: int, cy: int) -> pygame.Surface:
        key = (cx, cy)
        s = self.chunks.get(key)
        if s is None:
            s = self._build_chunk(cx, cy)
            self.chunks[key] = s
            while len(self.chunks) > MAX_CHUNKS:
                self.chunks.popitem(last=False)
        else:
            self.chunks.move_to_end(key)
        return s

    def draw_static(self, screen: pygame.Surface, cam_x: float, cam_y: float) -> None:
        w, h = screen.get_size()
        c0x, c0y = int(cam_x // CHUNK_PX), int(cam_y // CHUNK_PX)
        c1x, c1y = int((cam_x + w) // CHUNK_PX), int((cam_y + h) // CHUNK_PX)
        screen.fill((5, 8, 12))
        for cy in range(c0y, c1y + 1):
            for cx in range(c0x, c1x + 1):
                if cx < 0 or cy < 0 or cx * CHUNK >= self.m.width or cy * CHUNK >= self.m.height:
                    continue
                screen.blit(self.chunk(cx, cy), (cx * CHUNK_PX - cam_x, cy * CHUNK_PX - cam_y))

    # ----------------------------------------------------------- dynamic parts
    def draw_doors(self, screen, cam_x, cam_y, codes: List[int]) -> None:
        w, h = screen.get_size()
        lib = self.lib
        for d in self.m.doors:
            c0 = d.cells[0]
            sx, sy = c0[0] * TILE - cam_x, c0[1] * TILE - cam_y
            if sx < -2 * TILE or sy < -2 * TILE or sx > w + TILE or sy > h + TILE:
                continue
            code = codes[d.id] if d.id < len(codes) else 0
            is_open = code == 1
            for i, (x, y) in enumerate(d.cells):
                img = lib.door(is_open, d.vertical, i == 1)
                screen.blit(img, (x * TILE - cam_x, y * TILE - cam_y))
            # status light
            cx = (d.cells[0][0] + d.cells[-1][0] + 1) * TILE / 2 - cam_x
            cy = (d.cells[0][1] + d.cells[-1][1] + 1) * TILE / 2 - cam_y
            if code == 2:
                col = (230, 60, 60)
            elif code == 3:
                col = (255, 160, 30)
            elif is_open:
                col = (70, 220, 120)
            else:
                col = (110, 190, 255)
            pygame.draw.circle(screen, col, (int(cx), int(cy)), 5)
            pygame.draw.circle(screen, (20, 24, 30), (int(cx), int(cy)), 5, 1)

    def object_sprite_name(self, o, state, read_keys, t: float) -> str:
        fam = o.family
        if o.kind == "generator":
            return "generator_on" if state.get("power") else "generator_off"
        if o.kind == "core":
            return "signal_core_on" if state.get("core") else "signal_core_off"
        if o.kind == "transmitter":
            return "transmitter_on" if (state.get("power") and state.get("core")) else "transmitter_off"
        if o.kind == "camp":
            return "camp_on" if o.id in state.get("camps", ()) else "camp_off"
        if o.kind == "weapon_crate":
            return "weapon_crate_open" if o.id in state.get("opened", ()) else "weapon_crate_closed"
        if o.kind == "med_station":
            return "med_station"
        if o.kind == "camera":
            return "camera_console" if (state.get("power") or not o.needs_power) else "terminal_dead"
        if o.id in state.get("corrupt", ()):
            return "terminal_corrupt"
        if o.needs_power and not state.get("power"):
            return "terminal_dead"
        key = o.id
        if o.id.startswith("clue_"):
            key = o.id[5:]
        suffix = "read" if key in read_keys or o.id in read_keys else "idle"
        base = fam if fam in ("console_security", "archive", "medical") else "terminal"
        return f"{base}_{suffix}"

    def draw_objects(self, screen, cam_x, cam_y, state, read_keys, t: float, near_id=None) -> None:
        w, h = screen.get_size()
        lib = self.lib
        for o in self.m.objects:
            sx, sy = o.x * TILE - cam_x, o.y * TILE - cam_y
            if sx < -3 * TILE or sy < -3 * TILE or sx > w + TILE or sy > h + TILE:
                continue
            name = self.object_sprite_name(o, state, read_keys, t)
            img = lib.sprite(name, o.w, o.h, o.rot)
            screen.blit(img, (sx, sy))
            if o.kind == "terminal" and name.endswith("_idle") and not (o.needs_power and not state.get("power")):
                # pulsing beacon marks unread information
                pr = 4 + int(2 * (1 + math.sin(t * 4 + o.x)) / 2 * 2)
                pygame.draw.circle(screen, (90, 230, 255), (int(sx + o.w * TILE / 2), int(sy - 6)), pr, 2)
            if o.id == near_id:
                r = pygame.Rect(sx - 3, sy - 3, o.w * TILE + 6, o.h * TILE + 6)
                pygame.draw.rect(screen, (255, 255, 255), r, 2, border_radius=6)

    def draw_darkness(self, screen, lights_out: bool, flicker: int = 0, daylight: float = None) -> None:
        if daylight is not None and not lights_out:
            # open world: bright days, dark nights, orange dusk/dawn
            alpha = int(self.ambient * (1.0 - daylight) ** 1.2) + (flicker if daylight < 0.3 else 0)
            if alpha > 6:
                rad = int(self.light_r * (1.0 + 1.3 * daylight))
                screen.blit(self.lib.darkness(screen.get_size(), rad, max(8, min(250, alpha // 4 * 4))), (0, 0))
            if 0.12 < daylight < 0.78:
                k = 1.0 - abs(daylight - 0.45) / 0.33
                tint = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
                tint.fill((255, 120, 40, int(44 * max(0.0, k))))
                screen.blit(tint, (0, 0))
            return
        rad = int(LIGHT_RADIUS_DARK if lights_out else self.light_r)
        alpha = 250 if lights_out else max(200, min(252, self.ambient + flicker))
        dark = self.lib.darkness(screen.get_size(), rad, alpha)
        screen.blit(dark, (0, 0))

    def draw_glows(self, screen, cam_x, cam_y, state, read_keys, t: float) -> None:
        """Additive glows drawn AFTER the darkness so lit terminals / lanterns show up in the dark."""
        w, h = screen.get_size()
        lib = self.lib
        for p in self.lamps:
            sx, sy = (p.x + 0.5) * TILE - cam_x, (p.y + 0.5) * TILE - cam_y
            if -140 < sx < w + 140 and -140 < sy < h + 140:
                fl = 0.82 + 0.18 * math.sin(t * 7 + p.x * 3 + p.y)
                g = lib.glow(130, (int(255 * fl), int(170 * fl), int(70 * fl)))
                screen.blit(g, (sx - 130, sy - 130), special_flags=pygame.BLEND_RGB_ADD)
        for o in self.m.objects:
            sx, sy = (o.x + o.w / 2) * TILE - cam_x, (o.y + o.h / 2) * TILE - cam_y
            if not (-100 < sx < w + 100 and -100 < sy < h + 100):
                continue
            if o.kind == "terminal" and o.id not in state.get("corrupt", ()) and not (o.needs_power and not state.get("power")):
                key = o.id[5:] if o.id.startswith("clue_") else o.id
                if key in read_keys:
                    continue
                g = lib.glow(70, (30, 90, 120))
            elif o.kind in ("generator",) and not state.get("power"):
                g = lib.glow(90, (110, 50, 20))
            elif o.kind == "transmitter" and state.get("power") and state.get("core"):
                g = lib.glow(150, (30, 110, 120))
            elif o.kind == "camp" and o.id in state.get("camps", ()):
                fl = 0.8 + 0.2 * math.sin(t * 9 + o.x)
                g = lib.glow(150, (int(200 * fl), int(110 * fl), int(40 * fl)))
            elif o.kind == "camp":
                g = lib.glow(60, (60, 40, 20))
            elif o.kind == "med_station":
                g = lib.glow(80, (20, 90, 40))
            elif o.kind == "weapon_crate" and o.id not in state.get("opened", ()):
                g = lib.glow(80, (50, 110, 30))
            else:
                continue
            screen.blit(g, (sx - g.get_width() // 2, sy - g.get_height() // 2), special_flags=pygame.BLEND_RGB_ADD)
