"""Sprite / font / UI-frame library built on the processed asset manifest."""
from __future__ import annotations

import json
import math
from typing import Dict, Tuple

import pygame

from ..config import COMMON_DIR, MAP_ASSET_DIR, TILE


class SpriteLibrary:
    def __init__(self, map_id: str = "research_station"):
        self.dir = MAP_ASSET_DIR / map_id
        self.manifest = json.loads((self.dir / "manifest.json").read_text())
        self.sprites: Dict[str, pygame.Surface] = {}
        self.floors: Dict[str, pygame.Surface] = {}
        self._rot: Dict[Tuple, pygame.Surface] = {}
        self._fonts: Dict[Tuple[str, int], pygame.font.Font] = {}
        self._frames: Dict[Tuple, pygame.Surface] = {}
        self._icons: Dict[Tuple[str, int, tuple], pygame.Surface] = {}
        for name, info in self.manifest["sprites"].items():
            self.sprites[name] = pygame.image.load(str(self.dir / info["file"])).convert_alpha()
        for name, rel in self.manifest["floors"].items():
            self.floors[name] = pygame.image.load(str(self.dir / rel)).convert()
        self._base_sprites = dict(self.sprites)
        self._base_floors = dict(self.floors)
        self.map_id = map_id
        self.char_raw: Dict[str, pygame.Surface] = {}
        for f in (COMMON_DIR / "characters").glob("*.png"):
            self.char_raw[f.stem] = pygame.image.load(str(f)).convert_alpha()
        self._chars: Dict[Tuple, pygame.Surface] = {}
        self.skins = ["player", "female", "adventurer", "soldier"]
        self.ui = {p.stem: pygame.image.load(str(p)).convert_alpha() for p in (COMMON_DIR / "ui").glob("*.png")}
        self.light_mask = pygame.image.load(str(COMMON_DIR / "lighting" / "light_mask.png")).convert_alpha()
        kp = COMMON_DIR / "prompts" / "key_e.png"
        self.key_e = pygame.image.load(str(kp)).convert_alpha() if kp.exists() else None
        self._dark: Dict[Tuple, pygame.Surface] = {}

    def set_map(self, map_id: str) -> None:
        """Switch the active tileset: research_station base + optional per-map overlay."""
        if map_id == self.map_id and getattr(self, "_overlay_done", False):
            return
        self.sprites = dict(self._base_sprites)
        self.floors = dict(self._base_floors)
        self._rot.clear()
        self.map_id = map_id
        ov = MAP_ASSET_DIR / map_id / "manifest.json"
        if map_id != "research_station" and ov.exists():
            man = json.loads(ov.read_text())
            for name, info in man["sprites"].items():
                self.sprites[name] = pygame.image.load(str(MAP_ASSET_DIR / map_id / info["file"])).convert_alpha()
            for name, rel in man["floors"].items():
                self.floors[name] = pygame.image.load(str(MAP_ASSET_DIR / map_id / rel)).convert()
        self._overlay_done = True
        self._dark.clear()

    # ---- sprites
    def sprite(self, name: str, w: int, h: int, rot: int = 0, flip: bool = False) -> pygame.Surface:
        key = (name, w, h, rot, flip)
        s = self._rot.get(key)
        if s is None:
            img = self.sprites.get(name) or self.sprites["crate_metal"]
            if flip:
                img = pygame.transform.flip(img, True, False)
            if rot:
                img = pygame.transform.rotate(img, 90 * rot)
            tw, th = w * TILE, h * TILE
            if img.get_size() != (tw, th):
                img = pygame.transform.smoothscale(img, (tw, th))
            s = img
            self._rot[key] = s
        return s

    def door(self, open_: bool, vertical: bool, second: bool) -> pygame.Surface:
        key = ("door", open_, vertical, second)
        s = self._rot.get(key)
        if s is None:
            img = self.sprites["door_open" if open_ else "door_closed"]
            if second:
                img = pygame.transform.flip(img, True, False)
            if vertical:
                img = pygame.transform.rotate(img, 90)
            self._rot[key] = s = img
        return s

    # ---- fonts
    def font(self, size: int, narrow: bool = True) -> pygame.font.Font:
        key = ("n" if narrow else "w", size)
        f = self._fonts.get(key)
        if f is None:
            fn = "KenneyFutureNarrow.ttf" if narrow else "KenneyFuture.ttf"
            try:
                f = pygame.font.Font(str(COMMON_DIR / "fonts" / fn), size)
            except (pygame.error, FileNotFoundError):
                f = pygame.font.Font(None, size + 6)
            self._fonts[key] = f
        return f

    def text(self, s: str, size: int, color=(230, 240, 245), narrow: bool = True) -> pygame.Surface:
        return self.font(size, narrow).render(s, True, color)

    # ---- characters (front/back view poses, flipped for left/right)
    def char(self, skin: str, pose: str, flip: bool = False, scale: float = 0.78, tint=None) -> pygame.Surface:
        key = (skin, pose, flip, scale, tint)
        s = self._chars.get(key)
        if s is None:
            img = self.char_raw.get(f"{skin}_{pose}") or self.char_raw[f"{skin}_stand"]
            w, h = img.get_size()
            img = pygame.transform.smoothscale(img, (int(w * scale), int(h * scale)))
            if flip:
                img = pygame.transform.flip(img, True, False)
            if tint:
                img = img.copy()
                img.fill(tint, special_flags=pygame.BLEND_RGB_MULT)
            self._chars[key] = s = img
        return s

    def gun(self, angle: float, weapon: str = "pistol") -> pygame.Surface:
        from ..weapons import WEAPONS
        a = round(math.degrees(angle) / 6) * 6
        key = ("gun", weapon, a)
        s = self._chars.get(key)
        if s is None:
            spec = WEAPONS.get(weapon, WEAPONS["pistol"])
            img = self.char_raw[spec["sprite"]]
            sc = spec["scale"]
            img = pygame.transform.scale(img, (int(img.get_width() * sc), int(img.get_height() * sc)))
            if weapon == "plasma":
                img = img.copy()
                img.fill((120, 255, 255), special_flags=pygame.BLEND_RGB_MULT)
            elif weapon == "rifle":
                img = img.copy()
                img.fill((200, 220, 255), special_flags=pygame.BLEND_RGB_MULT)
            elif weapon == "shotgun":
                img = img.copy()
                img.fill((255, 190, 130), special_flags=pygame.BLEND_RGB_MULT)
            if abs(a) > 90:
                img = pygame.transform.flip(img, False, True)
            self._chars[key] = s = pygame.transform.rotate(img, -a)
        return s

    # ---- UI frames (9-slice, tinted)
    def frame(self, kind: str, w: int, h: int, tint=(255, 255, 255), border: int = 16) -> pygame.Surface:
        key = (kind, w, h, tint, border)
        s = self._frames.get(key)
        if s is not None:
            return s
        src = self.ui[kind]
        sw, sh = src.get_size()
        b = min(border, sw // 2 - 1, sh // 2 - 1)
        out = pygame.Surface((w, h), pygame.SRCALPHA)
        xs = [(0, b, 0, b), (b, w - b, b, sw - b), (w - b, w, sw - b, sw)]
        ys = [(0, b, 0, b), (b, h - b, b, sh - b), (h - b, h, sh - b, sh)]
        for (dx0, dx1, sx0, sx1) in xs:
            for (dy0, dy1, sy0, sy1) in ys:
                if dx1 - dx0 <= 0 or dy1 - dy0 <= 0:
                    continue
                piece = src.subsurface((sx0, sy0, sx1 - sx0, sy1 - sy0))
                if piece.get_size() != (dx1 - dx0, dy1 - dy0):
                    piece = pygame.transform.smoothscale(piece, (dx1 - dx0, dy1 - dy0))
                out.blit(piece, (dx0, dy0))
        if tint != (255, 255, 255):
            out.fill(tint + (255,), special_flags=pygame.BLEND_RGBA_MULT)
        self._frames[key] = out
        return out

    def icon(self, name: str, size: int, color=(255, 255, 255)) -> pygame.Surface:
        key = (name, size, color)
        s = self._icons.get(key)
        if s is None:
            p = COMMON_DIR / "icons" / f"{name}.png"
            if p.exists():
                img = pygame.image.load(str(p)).convert_alpha()
                img = pygame.transform.smoothscale(img, (size, size))
                if color != (255, 255, 255):
                    img.fill(color + (255,), special_flags=pygame.BLEND_RGBA_MULT)
            else:
                img = pygame.Surface((size, size), pygame.SRCALPHA)
            self._icons[key] = s = img
        return s

    def glow(self, radius: int, color) -> pygame.Surface:
        key = ("glow", radius, color)
        g = self._chars.get(key)
        if g is None:
            d = radius * 2
            g = pygame.Surface((d, d))
            g.fill((0, 0, 0))
            m = pygame.transform.smoothscale(self.light_mask, (d, d))
            tinted = pygame.Surface((d, d), pygame.SRCALPHA)
            tinted.fill(color + (255,))
            tinted.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            g.blit(tinted, (0, 0))
            self._chars[key] = g
        return g

    # ---- darkness overlay with a light-mask hole centred on the screen
    def darkness(self, size: Tuple[int, int], radius_px: int, alpha: int = 238) -> pygame.Surface:
        key = (size, radius_px, alpha)
        s = self._dark.get(key)
        if s is None:
            if len(self._dark) > 8:
                self._dark.clear()
            s = pygame.Surface(size, pygame.SRCALPHA)
            s.fill((4, 8, 14, alpha))
            d = radius_px * 2
            m = pygame.transform.smoothscale(self.light_mask, (d, d))
            s.blit(m, (size[0] // 2 - radius_px, size[1] // 2 - radius_px), special_flags=pygame.BLEND_RGBA_SUB)
            self._dark[key] = s
        return s
