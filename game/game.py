"""Application controller: screens, networking glue and the gameplay screen."""
from __future__ import annotations

import json
import os
import math
import secrets
import time
from typing import List, Optional

import pygame

from .audio import Audio
from .settings import Settings
from .ui.settings_screen import SettingsScreen
from .camera import Camera
from .config import (DEFAULT_GAME_PORT, FPS, GAME_NAME, MAX_NAME_LEN, SCREEN_H, SCREEN_W, TILE, settings_dir)
from .networking.client import NetClient
from .networking.discovery import DiscoveryListener, local_ipv4_addresses
from .networking.server import GameServer
from .rendering.effects import draw_interference, draw_vignette
from .rendering.renderer import LIGHT_RADIUS, LIGHT_RADIUS_DARK, WorldRenderer
from .weapons import ORDER, WEAPONS
from .ui.widgets import TextField
from .rendering.sprites import SpriteLibrary
from .session import Session
from .ui.browser import BrowserScreen
from .ui.hud import Hud
from .ui.lobby import LobbyScreen
from .ui.menu import MainMenu, MessageScreen, draw_background
from .ui.widgets import BTN_GREEN, BTN_RED, Button, draw_text, panel

REJECT_TEXT = {
    "rejected": "The host rejected your request.",
    "full": "That game is full.",
    "started": "That game has already started.",
    "version": "Game version mismatch.",
    "no_host": "The host is not available.",
    "timeout": "The host did not answer in time.",
}


class GameScreen:
    def __init__(self, app):
        self.app = app
        self.hud = Hud(app)
        self.cam = Camera(app.screen.get_width(), app.screen.get_height())
        self.paused = False
        self.resume = Button((540, 300, 200, 50), "RESUME", self._resume, BTN_GREEN)
        self.settings_btn = Button((540, 370, 200, 50), "SETTINGS", self._open_settings)
        self.leave = Button((540, 440, 200, 50), "DISCONNECT", app.leave_game, BTN_RED)
        self.end_btn = Button((540, 520, 200, 50), "MAIN MENU", app.leave_game, BTN_RED)
        self.end_lobby = Button((510, 450, 260, 50), "BACK TO LOBBY", app.return_lobby, BTN_GREEN)
        self.vcache = {}
        self.t = 0.0
        self.chat_field = TextField((0, 0, 520, 36), "", 120, False, "Say something... (Enter to send)")
        self.chatting = False

    def _resume(self):
        self.paused = False

    def _open_settings(self):
        self.app.net.send({"t": "input", "mx": 0, "my": 0, "aim": 0.0, "fire": False})
        pygame.mouse.set_visible(True)
        self.app.goto(SettingsScreen(self.app, self))

    def handle_event(self, e):
        s = self.app.session
        if s is None:
            return
        if s.end:
            self.end_btn.handle(e, self.app.audio)
            if self.app.is_host:
                self.end_lobby.handle(e, self.app.audio)
            return
        if self.chatting:
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                txt = self.chat_field.text.strip()
                if txt:
                    self.app.net.send({"t": "chat", "text": txt})
                self.chat_field.text = ""
                self.chat_field.focus = False
                self.chatting = False
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self.chat_field.text = ""
                self.chat_field.focus = False
                self.chatting = False
            else:
                self.chat_field.handle(e)
            return
        if self.hud.handle_event(e):
            return
        if self.paused:
            self.resume.handle(e, self.app.audio)
            self.settings_btn.handle(e, self.app.audio)
            self.leave.handle(e, self.app.audio)
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self.paused = False
            return
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                if self.hud.show_notes:
                    self.hud.show_notes = False
                else:
                    self.paused = True
            else:
                K = self.app.settings.keys
                if e.key == K["notes"]:
                    self.hud.show_notes = not self.hud.show_notes
                elif e.key == K["interact"]:
                    s.interact(self.app.net)
                elif e.key == K["map"]:
                    self.hud.minimap_big = not self.hud.minimap_big
                elif e.key == K["reload"]:
                    self.app.net.send({"t": "reload"})
                elif e.key == K["chat"]:
                    self.chatting = True
                    self.chat_field.focus = True
                    self.chat_field.text = ""
                elif e.key == K["weapon_next"]:
                    owned = [w for w in ORDER if w in s.owned]
                    i = owned.index(s.cur_weapon) if s.cur_weapon in owned else 0
                    self.app.net.send({"t": "weapon", "name": owned[(i + 1) % len(owned)]})
                else:
                    for idx in range(5):
                        if e.key == K[f"w{idx + 1}"] and ORDER[idx] in s.owned:
                            self.app.net.send({"t": "weapon", "name": ORDER[idx]})
        elif e.type == pygame.MOUSEWHEEL:
            owned = [w for w in ORDER if w in s.owned]
            if owned:
                i = owned.index(s.cur_weapon) if s.cur_weapon in owned else 0
                self.app.net.send({"t": "weapon", "name": owned[(i - e.y) % len(owned)]})

    def update(self, dt):
        s = self.app.session
        if s is None:
            return
        self.t += dt
        mx = my = 0.0
        if not (self.paused or self.chatting or self.hud.text_input_active() or s.popup or self.hud.show_notes):
            k = pygame.key.get_pressed()
            K = self.app.settings.keys
            mx = (k[K["right"]] or k[pygame.K_RIGHT]) - (k[K["left"]] or k[pygame.K_LEFT])
            my = (k[K["down"]] or k[pygame.K_DOWN]) - (k[K["up"]] or k[pygame.K_UP])
        aim, fire = s.aim, False
        if not (self.paused or self.chatting or self.hud.text_input_active() or s.popup or self.hud.show_notes or s.end):
            mxp, myp = pygame.mouse.get_pos()
            w, h = self.app.screen.get_size()
            aim = math.atan2(myp - (h // 2 - 8), mxp - w // 2)
            k = pygame.key.get_pressed()
            fire = bool(pygame.mouse.get_pressed()[0] or k[self.app.settings.keys["fire"]])
        s.update(dt, float(mx), float(my), self.app.net, aim, fire)
        want_hidden = not (self.paused or self.chatting or self.hud.text_input_active() or s.popup or self.hud.show_notes or s.end)
        if pygame.mouse.get_visible() == want_hidden:
            pygame.mouse.set_visible(not want_hidden)
        self.cam.resize(*self.app.screen.get_size())
        self.cam.follow(s.x, s.y)

    # ---- drawing
    def _pose_dir(self, moving: bool, face: float, aim: float):
        """Pick (pose, flip) for a front/back view character from movement and aim."""
        ca, sa = math.cos(aim), math.sin(aim)
        if sa < -0.7:
            return "back", ca < 0
        return None, ca < 0

    def _draw_shadow(self, screen, sx, sy, w=44):
        sh = pygame.Surface((w, 16), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 110), sh.get_rect())
        screen.blit(sh, (sx - w // 2, sy + 14))

    def _draw_player(self, screen, lib, x, y, aim, color, name, pid, moving, local, t, shoot_until=0.0, hurt=False, hp=100, weapon="pistol"):
        sx, sy = x - self.cam.x, y - self.cam.y
        skin = lib.skins[(pid - 1) % len(lib.skins)]
        self._draw_shadow(screen, sx, sy)
        # coloured identity ring on the floor
        ring = pygame.Surface((60, 26), pygame.SRCALPHA)
        pygame.draw.ellipse(ring, color + (255,), ring.get_rect(), 3)
        screen.blit(ring, (sx - 30, sy + 9))
        back, flip = self._pose_dir(moving, 0, aim)
        if hurt:
            pose = "hurt"
        elif back:
            pose = "back"
        elif moving:
            pose = "walk1" if int(t * 8) % 2 == 0 else "walk2"
        else:
            pose = "stand"
        bob = int(2 * math.sin(t * 16)) if moving else 0
        img = lib.char(skin, pose, flip)
        screen.blit(img, img.get_rect(midbottom=(sx, sy + 24 + bob)))
        # weapon
        gun = lib.gun(aim, weapon)
        gx, gy = sx + math.cos(aim) * 20, sy - 4 + math.sin(aim) * 14
        screen.blit(gun, gun.get_rect(center=(gx, gy)))
        if time.time() < shoot_until:
            tx, ty = sx + math.cos(aim) * 40, sy - 4 + math.sin(aim) * 30
            pygame.draw.circle(screen, (255, 240, 150), (int(tx), int(ty)), 7)
            pygame.draw.circle(screen, (255, 255, 255), (int(tx), int(ty)), 3)
        # number badge + name
        pygame.draw.circle(screen, color, (int(sx + 24), int(sy - 62)), 10)
        pygame.draw.circle(screen, (10, 16, 22), (int(sx + 24), int(sy - 62)), 10, 1)
        draw_text(screen, lib, str(pid), (sx + 24, sy - 63), 12, (10, 16, 22), center=True)
        img = lib.text(name, 15, (255, 255, 255) if local else (225, 235, 245))
        bg = img.get_rect(center=(sx, sy - 62)).inflate(10, 4)
        shade = pygame.Surface(bg.size, pygame.SRCALPHA)
        shade.fill((0, 0, 0, 140))
        screen.blit(shade, bg)
        screen.blit(img, img.get_rect(center=(sx, sy - 62)))
        if hp < 100:
            bw = 44
            pygame.draw.rect(screen, (40, 10, 10), (sx - bw // 2, sy - 52, bw, 5))
            pygame.draw.rect(screen, (90, 230, 120) if hp > 40 else (240, 80, 70), (sx - bw // 2, sy - 52, int(bw * hp / 100), 5))

    def _draw_zombie(self, screen, lib, z, t):
        sx, sy = z.x - self.cam.x, z.y - self.cam.y
        scale = {0: 0.78, 1: 0.72, 2: 1.0}.get(z.kind, 0.78)
        tint = {1: (255, 190, 190), 2: (200, 200, 230)}.get(z.kind)
        flip = math.cos(z.face) < 0
        moving, attacking = bool(z.flags & 1), bool(z.flags & 2)
        if time.time() < z.hurt_until:
            pose = "hurt"
        elif attacking:
            pose = "action1"
        elif moving:
            pose = "walk1" if int(t * (12 if z.kind == 1 else 7) + z.zid) % 2 == 0 else "walk2"
        else:
            pose = "stand"
        self._draw_shadow(screen, sx, sy, int(44 * scale / 0.78))
        img = lib.char("zombie", pose, flip, scale, tint)
        bob = int(2 * math.sin(t * 9 + z.zid)) if moving else 0
        screen.blit(img, img.get_rect(midbottom=(sx, sy + 24 + bob)))
        if z.hp < z.max_hp:
            bw = int(40 * scale / 0.78)
            top = sy - img.get_height() + 22
            pygame.draw.rect(screen, (40, 10, 10), (sx - bw // 2, top, bw, 5))
            pygame.draw.rect(screen, (230, 60, 60), (sx - bw // 2, top, int(bw * max(0, z.hp) / z.max_hp), 5))

    def draw(self, screen):
        app = self.app
        s = app.session
        lib = app.lib
        if s is None:
            screen.fill((0, 0, 0))
            return
        r = s.renderer
        cx, cy = self.cam.x, self.cam.y
        r.draw_static(screen, cx, cy)
        r.draw_doors(screen, cx, cy, s.state["doors"])
        s_state = {"camps": s.state.get("camps", []), "power": s.state["power"], "core": s.state["core"], "corrupt": s.state.get("corrupt", []), "opened": s.state.get("opened", [])}
        r.draw_objects(screen, cx, cy, s_state, s.read_keys, self.t, s.near.id if s.near else None)
        self._draw_ground_fx(screen, lib, s, cx, cy)
        dl0 = s.daylight()
        lim = (LIGHT_RADIUS_DARK if s.lights_out else r.light_r * (1.0 + 1.3 * dl0 if dl0 is not None else 1.0)) * 0.92
        now = time.time()
        actors = []
        for p in s.remote.values():
            if p.seen and p.connected and not p.dead and p.pid != s.pid and math.hypot(p.x - s.x, p.y - s.y) <= lim:
                actors.append((p.y, "p", p))
        for z in s.zombies.values():
            if math.hypot(z.x - s.x, z.y - s.y) <= lim:
                actors.append((z.y, "z", z))
        if not s.dead:
            actors.append((s.y, "me", None))
        actors.sort(key=lambda a: a[0])
        for _y, kind, o in actors:
            if kind == "p":
                self._draw_player(screen, lib, o.x, o.y, o.aim, o.color, o.name, o.pid, o.moving, False, self.t, o.shoot_until, False, o.hp, o.weapon)
            elif kind == "z":
                self._draw_zombie(screen, lib, o, self.t)
            else:
                self._draw_player(screen, lib, s.x, s.y, s.aim, Session_color(s.pid), app.player_name, s.pid, s.moving, True,
                                  self.t, s.shoot_until, now < s.hurt_until, s.hp, s.cur_weapon)
        for tr in s.tracers:
            a = max(0.0, 1 - (now - tr["t"]) / 0.12)
            base = tr.get("c", (255, 220, 120))
            col = tuple(int(c * (0.35 + 0.65 * a)) for c in base)
            pygame.draw.line(screen, col, (tr["x"] - cx, tr["y"] - cy), (tr["ex"] - cx, tr["ey"] - cy), 2)
        if s.boss:
            actors_boss = True
            self._draw_boss(screen, lib, s, cx, cy)
        for ob in s.orbs:
            ox, oy = ob[0] - cx, ob[1] - cy
            g = lib.glow(34, (190, 80, 255))
            screen.blit(g, (ox - 34, oy - 34), special_flags=pygame.BLEND_RGB_ADD)
            pygame.draw.circle(screen, (235, 200, 255), (int(ox), int(oy)), 7)
        dl = s.daylight()
        r.draw_darkness(screen, s.lights_out, s.flicker, dl)
        r.draw_glows(screen, cx, cy, s_state, s.read_keys, self.t)
        self._draw_supply_markers(screen, lib, s, cx, cy)
        self._draw_phantom(screen, lib, s)
        if s.interference:
            draw_interference(screen, self.t)
        draw_vignette(screen, self.vcache)
        self.hud.draw(screen, 1 / 60)
        self._draw_chat(screen, lib)
        self._draw_scare(screen, lib, s)
        if not pygame.mouse.get_visible():
            mxp, myp = pygame.mouse.get_pos()
            col = (255, 90, 90) if s.reloading or s.ammo <= 0 else (255, 255, 255)
            pygame.draw.circle(screen, col, (mxp, myp), 11, 2)
            pygame.draw.line(screen, col, (mxp - 17, myp), (mxp - 6, myp), 2)
            pygame.draw.line(screen, col, (mxp + 6, myp), (mxp + 17, myp), 2)
            pygame.draw.line(screen, col, (mxp, myp - 17), (mxp, myp - 6), 2)
            pygame.draw.line(screen, col, (mxp, myp + 6), (mxp, myp + 17), 2)
        if app.reconnecting:
            self._overlay(screen, "CONNECTION LOST", "Trying to reconnect...")
        elif self.paused and not s.end:
            self._overlay(screen, "PAUSED", "The station does not wait for you.")
            self.resume.draw(screen, lib)
            self.settings_btn.draw(screen, lib)
            self.leave.draw(screen, lib)
        if s.end:
            self._end(screen, s.end)
        self._shake(screen, s)

    # ---- extra effects
    def _draw_supply_markers(self, screen, lib, s, cx, cy):
        w, h = screen.get_size()
        for pk in s.pickups:
            if pk[1] != 2:
                continue
            x, y = pk[2] - cx, pk[3] - cy
            if 0 <= x <= w and 0 <= y <= h:
                g = lib.glow(150, (230, 190, 50))
                screen.blit(g, (x - 150, y - 150), special_flags=pygame.BLEND_RGB_ADD)
                for k in range(0, 260, 6):
                    a = max(0, 255 - k)
                    pygame.draw.line(screen, (a, int(a * 0.85), int(a * 0.25)), (x, y - k), (x, y - k - 4), 3)
            else:
                dx, dy = pk[2] - s.x, pk[3] - s.y
                ang = math.atan2(dy, dx)
                ex = max(30, min(w - 30, w // 2 + math.cos(ang) * w))
                ey = max(30, min(h - 30, h // 2 + math.sin(ang) * h))
                pts = [(ex + math.cos(ang) * 16, ey + math.sin(ang) * 16), (ex + math.cos(ang + 2.5) * 12, ey + math.sin(ang + 2.5) * 12),
                       (ex + math.cos(ang - 2.5) * 12, ey + math.sin(ang - 2.5) * 12)]
                pygame.draw.polygon(screen, (250, 210, 70), pts)
                dist = int(math.hypot(dx, dy) / TILE)
                draw_text(screen, lib, f"SUPPLY {dist}m", (ex, ey + (-24 if ey > 60 else 26)), 12, (250, 220, 120), center=True)

    def _draw_chat(self, screen, lib):
        now = time.time()
        w, h = screen.get_size()
        lines = [c for c in self.app.chat_log if now - c[2] < 12 or self.chatting][-7:]
        y = h - 118 - 22 * len(lines)
        for name, text, t0, pid in lines:
            a = 255 if self.chatting else int(255 * max(0.0, min(1.0, (12 - (now - t0)) / 3)))
            col = Session_color(pid) if pid else (200, 215, 230)
            n = lib.text(name + ":", 15, col)
            m = lib.text(text, 15, (235, 240, 245))
            bg = pygame.Surface((n.get_width() + m.get_width() + 18, 20), pygame.SRCALPHA)
            bg.fill((0, 0, 0, int(120 * a / 255)))
            screen.blit(bg, (12, y))
            n.set_alpha(a)
            m.set_alpha(a)
            screen.blit(n, (18, y + 2))
            screen.blit(m, (24 + n.get_width(), y + 2))
            y += 22
        if self.chatting:
            self.chat_field.rect.topleft = (12, h - 116)
            self.chat_field.draw(screen, lib, 1 / 60)

    def _draw_ground_fx(self, screen, lib, s, cx, cy):
        now = time.time()
        for pk in s.pickups:
            _id, kind, x, y = pk
            img = lib.sprites["pickup_ammo" if kind == 0 else ("pickup_medkit" if kind == 1 else "pickup_supply")]
            bob = 3 * math.sin(self.t * 4 + _id)
            screen.blit(img, (x - cx - 32, y - cy - 32 + bob))
        for tg in s.telegraphs:
            el = now - tg["t"]
            k = max(0.0, min(1.0, el / max(0.01, tg["dur"])))
            sx, sy = tg["x"] - cx, tg["y"] - cy
            if tg["shape"] == "circle":
                r = int(tg["r"])
                surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(surf, (255, 60, 60, int(40 + 90 * k)), (r, r), r)
                pygame.draw.circle(surf, (255, 120, 120, 220), (r, r), r, 3)
                pygame.draw.circle(surf, (255, 80, 80, 150), (r, r), int(r * k), 2)
                screen.blit(surf, (sx - r, sy - r))
            elif tg["shape"] == "ring":
                r = int(tg["r"] * (0.4 + 0.6 * k))
                pygame.draw.circle(screen, (255, 255, 255), (int(sx), int(sy)), r, 4)
            else:
                ang, ln = tg["ang"], tg["len"]
                ex, ey = sx + math.cos(ang) * ln, sy + math.sin(ang) * ln
                pw = 30
                nx, ny = -math.sin(ang) * pw, math.cos(ang) * pw
                poly = [(sx + nx, sy + ny), (ex + nx, ey + ny), (ex - nx, ey - ny), (sx - nx, sy - ny)]
                surf = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
                pygame.draw.polygon(surf, (255, 70, 60, int(40 + 90 * k)), poly)
                pygame.draw.polygon(surf, (255, 150, 140, 200), poly, 2)
                screen.blit(surf, (0, 0))

    def _draw_boss(self, screen, lib, s, cx, cy):
        x, y, hp, mx, phase, st, face = s.boss
        sx, sy = x - cx, y - cy
        now = self.t
        aura = lib.glow(110 + int(10 * math.sin(now * 5)), (150, 50, 220) if phase < 3 else (230, 40, 60))
        screen.blit(aura, (sx - aura.get_width() // 2, sy - aura.get_height() // 2 - 10), special_flags=pygame.BLEND_RGB_ADD)
        tint = (210, 150, 255) if phase < 3 else (255, 120, 120)
        pose = "action1" if st in (1, 2) else ("walk1" if int(now * 5) % 2 == 0 else "walk2")
        img = lib.char("zombie", pose, math.cos(face) < 0, 1.9, tint)
        shadow = pygame.Surface((130, 34), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 120), shadow.get_rect())
        screen.blit(shadow, (sx - 65, sy + 22))
        screen.blit(img, img.get_rect(midbottom=(sx, sy + 46 + int(3 * math.sin(now * 6)))))
        draw_text(screen, lib, "ECHO WARDEN", (sx, sy - img.get_height() + 40), 16, (230, 190, 255), center=True)

    def _draw_phantom(self, screen, lib, s):
        now = time.time()
        if s.phantom:
            el = now - s.phantom["t"]
            a = int(170 * max(0.0, 1 - el / 2.2))
            ang = s.phantom["ang"]
            w, h = screen.get_size()
            px = w // 2 + math.cos(ang) * 300
            py = h // 2 - 8 + math.sin(ang) * 210
            img = lib.char("zombie", "stand", False, 1.1, (0, 0, 0)).copy()
            img.set_alpha(a)
            screen.blit(img, img.get_rect(midbottom=(px, py)))
        if now < s.whisper_until:
            a = int(220 * min(1.0, (s.whisper_until - now) / 1.5))
            t = lib.text(s.whisper_text, 26, (170, 40, 40))
            t.set_alpha(a)
            w, h = screen.get_size()
            screen.blit(t, t.get_rect(center=(w // 2, h // 2 + 150)))

    def _draw_scare(self, screen, lib, s):
        now = time.time()
        w, h = screen.get_size()
        if s.flash_until > now:
            a = int(210 * (s.flash_until - now) / 0.5)
            fl = pygame.Surface((w, h), pygame.SRCALPHA)
            fl.fill(s.flash_color + (max(0, min(255, a)),))
            screen.blit(fl, (0, 0))
        if s.scare:
            el = now - s.scare["t"]
            k = max(0.0, 1 - el / 0.9)
            red = pygame.Surface((w, h), pygame.SRCALPHA)
            red.fill((90, 0, 0, int(200 * k)))
            screen.blit(red, (0, 0))
            if el < 0.55:
                img = lib.char("zombie", "action1" if s.scare["n"] % 2 else "stand", False, 6.4, (255, 170, 170))
                jit = (int(14 * math.sin(el * 90)), int(10 * math.cos(el * 70)))
                scale = 1.0 + 0.5 * (1 - min(1.0, el / 0.12))
                if scale != 1.0:
                    img = pygame.transform.rotozoom(img, 0, scale)
                screen.blit(img, img.get_rect(center=(w // 2 + jit[0], h // 2 + 120 + jit[1])))
            for _ in range(24):
                import random as _r
                y = _r.randint(0, h)
                pygame.draw.line(screen, (255, 255, 255), (0, y), (w, y), 1)

    def _shake(self, screen, s):
        now = time.time()
        if now < s.shake_until:
            import random as _r
            m = s.shake_mag * (s.shake_until - now) / 0.4
            dx, dy = _r.uniform(-m, m), _r.uniform(-m, m)
            snap = screen.copy()
            screen.blit(snap, (int(dx), int(dy)))

    def _overlay(self, screen, title, sub):
        lib = self.app.lib
        w, h = screen.get_size()
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        screen.blit(shade, (0, 0))
        draw_text(screen, lib, title, (w // 2, 230), 44, (150, 235, 255), center=True, narrow=False)
        draw_text(screen, lib, sub, (w // 2, 272), 18, (170, 185, 200), center=True)

    def _end(self, screen, end):
        lib = self.app.lib
        w, h = screen.get_size()
        win = end.get("phase") == "victory"
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((0, 20, 10, 190) if win else (30, 0, 0, 200))
        screen.blit(shade, (0, 0))
        if win:
            draw_text(screen, lib, "SIGNAL TRANSMITTED", (w // 2, 190), 56, (130, 255, 170), center=True, narrow=False)
            draw_text(screen, lib, "CONNECTION ESTABLISHED", (w // 2, 260), 30, (150, 235, 255), center=True)
            draw_text(screen, lib, "HELP IS ON THE WAY", (w // 2, 306), 30, (255, 230, 150), center=True)
        else:
            draw_text(screen, lib, "SIGNAL LOST", (w // 2, 190), 56, (255, 120, 120), center=True, narrow=False)
            draw_text(screen, lib, end.get("reason", ""), (w // 2, 260), 26, (255, 200, 200), center=True)
            draw_text(screen, lib, "No one is coming.", (w // 2, 306), 24, (200, 150, 150), center=True)
        t = int(end.get("time", 0))
        draw_text(screen, lib, f"Time {t // 60:02d}:{t % 60:02d}   Fragments {end.get('found', 0)}/5   Transmit attempts {end.get('attempts', 0)}",
                  (w // 2, 380), 18, center=True)
        ks = sorted(end.get("kills", []), key=lambda k: -k[1])[:5]
        if ks:
            draw_text(screen, lib, "ZOMBIES KILLED:  " + "   ".join(f"{n} {k}" for n, k in ks), (w // 2, 410), 16, (255, 200, 150), center=True)
        if self.app.is_host:
            self.end_lobby.draw(screen, lib)
        else:
            draw_text(screen, lib, "Waiting for the host...", (w // 2, 470), 16, (150, 165, 180), center=True)
        self.end_btn.draw(screen, lib)


def Session_color(pid):
    from .config import PLAYER_COLORS
    return PLAYER_COLORS[(pid - 1) % len(PLAYER_COLORS)]


class App:
    def __init__(self, size=(SCREEN_W, SCREEN_H)):
        pygame.init()
        pygame.display.set_caption(GAME_NAME)
        self.settings = Settings()
        self.fullscreen = (self.settings.fullscreen and os.environ.get("SDL_VIDEODRIVER") != "dummy"
                           and os.environ.get("TLS_WINDOWED") != "1")
        flags = pygame.SCALED | (pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE)
        try:
            self.screen = pygame.display.set_mode(size, flags)
        except pygame.error:
            self.fullscreen = False
            self.screen = pygame.display.set_mode(size, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.lib = SpriteLibrary()
        self.audio = Audio(self.settings)
        self.net = NetClient()
        self.server: Optional[GameServer] = None
        self.session: Optional[Session] = None
        self.listener: Optional[DiscoveryListener] = None
        self.running = True
        self.player_name = self._load_name()
        self.pid = 0
        self.is_host = False
        self.token = ""
        self.conn_info = None            # (host, port) of the current game
        self.lobby: dict = {}
        self.lobby_toasts: List[str] = []
        self.join_requests: List[dict] = []
        self.host_addr = ""
        self.single = False
        self.reconnecting = False
        self.reconnect_deadline = 0.0
        self.reconnect_next = 0.0
        self.closed_by_host = False
        self.chat_log: list = []
        self.selected_map = "research_station"
        self.scr = MainMenu(self)

    # ----------------------------------------------------------- settings
    def _load_name(self) -> str:
        return self.settings.name

    def set_name(self, name: str) -> None:
        name = (name or "").strip()[:MAX_NAME_LEN] or "Player"
        self.player_name = name
        self.settings.name = name
        self.settings.save()

    def toggle_fullscreen(self) -> None:
        try:
            pygame.display.toggle_fullscreen()
            self.fullscreen = not self.fullscreen
            self.settings.fullscreen = self.fullscreen
            self.settings.save()
        except pygame.error:
            pass

    # ----------------------------------------------------------- navigation
    def goto(self, scr) -> None:
        self.scr = scr

    def quit(self) -> None:
        self.running = False

    def listener_start(self) -> None:
        self.listener_stop()
        self.listener = DiscoveryListener()
        self.listener.start()

    def listener_stop(self) -> None:
        if self.listener:
            self.listener.stop()
            self.listener = None

    def open_browser(self) -> None:
        self.goto(BrowserScreen(self))

    def _reset_net(self) -> None:
        self.net.close()
        self.session = None
        self.lobby = {}
        self.chat_log = []
        self.join_requests = []
        self.lobby_toasts = []
        self.is_host = False
        self.token = ""
        self.pid = 0
        self.reconnecting = False
        self.closed_by_host = False

    def _stop_server(self) -> None:
        if self.server:
            self.server.stop()
            self.server = None

    # ------------------------------------------------------- hosting/joining
    def host_game(self, name: str, limit: int, seed_text: str, single: bool = False, map_id: str = None) -> None:
        self._reset_net()
        self._stop_server()
        self.single = single
        key = secrets.token_hex(8)
        seed = int(seed_text) if seed_text.strip().isdigit() else None
        port = DEFAULT_GAME_PORT
        for attempt in range(2):
            try:
                self.server = GameServer(name=name, port=port, max_players=limit, seed=seed, host_key=key, map_id=map_id or self.selected_map,
                                         discovery=not single, bind="127.0.0.1" if single else "0.0.0.0")
                self.server.start()
                break
            except OSError:
                self.server = None
                port = 0
        if not self.server:
            self.goto(MessageScreen(self, "COULD NOT START SERVER", "Network port unavailable."))
            return
        ips = local_ipv4_addresses()
        self.host_addr = f"{ips[0] if ips else '127.0.0.1'}:{self.server.port}"
        self.conn_info = ("127.0.0.1", self.server.port)
        self.net.connect("127.0.0.1", self.server.port, self.player_name, host_key=key)
        self.goto(MessageScreen(self, "STARTING SERVER", "Generating station...", "CANCEL", self.leave_game, spinner=True))

    def start_single_player(self) -> None:
        self.set_name(getattr(self.scr, "name", None).text if hasattr(self.scr, "name") else self.player_name)
        self.host_game("Solo", 1, "", single=True)

    def join_game(self, host: str, port: int) -> None:
        self._reset_net()
        self._stop_server()
        self.single = False
        self.conn_info = (host, port)
        self.net.connect(host, port, self.player_name)
        self.goto(MessageScreen(self, "CONNECTING", f"Contacting {host}...", "CANCEL", self.leave_game, spinner=True))

    def request_start(self) -> None:
        self.net.send({"t": "start"})

    def return_lobby(self) -> None:
        self.net.send({"t": "return_lobby"})

    def leave_game(self) -> None:
        self.net.send({"t": "leave"})
        self._reset_net()
        self._stop_server()
        self.goto(MainMenu(self))

    # ------------------------------------------------------------- messages
    def process_net(self) -> None:
        for m in self.net.poll():
            try:
                self._on_message(m)
            except Exception as e:  # never let a bad message kill the client
                print("client message error:", repr(e))

    def _on_message(self, m: dict) -> None:
        t = m.get("t")
        if t == "welcome":
            self.pid, self.token, self.is_host = m["pid"], m["token"], bool(m["host"])
            self.reconnecting = False
            if self.player_name != m.get("name"):
                self.player_name = m.get("name", self.player_name)
            if not isinstance(self.scr, (LobbyScreen, GameScreen)):
                self.goto(LobbyScreen(self))
            if self.single and m.get("phase") == "lobby":
                self.net.send({"t": "start"})
        elif t == "pending":
            self.goto(MessageScreen(self, "REQUEST SENT", "Waiting for host approval...", "CANCEL", self.leave_game, spinner=True))
        elif t == "rejected":
            self._reset_net()
            self.goto(MessageScreen(self, "COULD NOT JOIN", REJECT_TEXT.get(m.get("reason"), "Rejected.")))
        elif t == "chat":
            self.chat_log.append((m.get("name", "?"), m.get("text", ""), time.time(), m.get("pid", 0)))
            self.chat_log = self.chat_log[-40:]
            self.audio.play("key", 0.5, 0.05)
        elif t == "lobby":
            self.lobby = m
        elif t == "lobby_reset":
            self.session = None
            self.goto(LobbyScreen(self))
        elif t == "join_request":
            self.join_requests.append({"rid": m["rid"], "name": m["name"]})
            self.audio.play("join_request")
        elif t == "join_cancel":
            self.join_requests = [r for r in self.join_requests if r["rid"] != m.get("rid")]
        elif t == "start":
            if self.session and self.session.map.seed == m["map"]["seed"] and self.session.pid == m["pid"]:
                pass  # reconnect to same game: keep our exploration state
            else:
                self.session = Session(self.lib, m["map"], m["pid"], m["players"], m["time_limit"], self.audio, WorldRenderer)
            self.goto(GameScreen(self)) if not isinstance(self.scr, GameScreen) else None
        elif t == "closed":
            self.closed_by_host = True
            self.net.close()
            self.session = None
            self.goto(MessageScreen(self, "HOST LEFT", "The host closed the game."))
        elif t == "net_error":
            self._on_net_error(m.get("reason", ""))
        elif t == "toast" and not self.session:
            self.lobby_toasts.append(m.get("text", ""))
            self.lobby_toasts = self.lobby_toasts[-5:]
            if m.get("snd"):
                self.audio.play(m["snd"])
        elif self.session:
            self.session.apply(m)

    def _on_net_error(self, reason: str) -> None:
        if self.closed_by_host:
            return
        if self.session and not self.session.end and self.token and self.conn_info and not self.single:
            if not self.reconnecting:
                self.reconnecting = True
                self.reconnect_deadline = time.time() + 40
                self.reconnect_next = time.time() + 1.0
            return
        was_session = self.session is not None
        self._reset_net()
        self._stop_server()
        self.goto(MessageScreen(self, "DISCONNECTED", reason or "Connection lost."))

    def _reconnect_tick(self) -> None:
        if not self.reconnecting:
            return
        now = time.time()
        if now > self.reconnect_deadline:
            self.reconnecting = False
            self._reset_net()
            self.goto(MessageScreen(self, "DISCONNECTED", "Could not reconnect to the host."))
            return
        if now >= self.reconnect_next and not self.net.connected:
            self.reconnect_next = now + 2.0
            host, port = self.conn_info
            old_tok = self.token
            self.net.connect(host, port, self.player_name, token=old_tok)

    # ------------------------------------------------------------- main loop
    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.1)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                elif e.type == pygame.KEYDOWN and e.key == self.settings.keys["fullscreen"] and not isinstance(self.scr, SettingsScreen):
                    self.toggle_fullscreen()
                elif e.type == pygame.VIDEORESIZE:
                    pass
                else:
                    self.scr.handle_event(e)
            self.step(dt)
        self.shutdown()

    def step(self, dt: float) -> None:
        """One frame of update + draw (also used by tests)."""
        self.process_net()
        self.net.keepalive()
        self._reconnect_tick()
        self.scr.update(dt)
        self.scr.draw(self.screen)
        pygame.display.flip()

    def shutdown(self) -> None:
        try:
            self.net.send({"t": "leave"})
        except Exception:
            pass
        self.net.close()
        self.listener_stop()
        self._stop_server()
        pygame.quit()
