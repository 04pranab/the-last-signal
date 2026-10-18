"""Gameplay HUD: objective, signal progress, prompts, minimap, popups, transmitter panel, notebook."""
from __future__ import annotations

import math
import time

import pygame

from ..config import TILE
from .widgets import BTN_GREEN, BTN_RED, Button, TextField, draw_text, panel


class Hud:
    def __init__(self, app):
        self.app = app
        self.lib = app.lib
        self.tx_fields = [TextField((0, 0, 110, 44), "", 3, True, "000"),
                          TextField((0, 0, 110, 44), "", 2, True, "00"),
                          TextField((0, 0, 110, 44), "", 3, True, "000")]
        self.btn_tx = Button((0, 0, 200, 46), "TRANSMIT", self._transmit, BTN_GREEN)
        self.btn_close = Button((0, 0, 120, 46), "CLOSE", self._close_panel, BTN_RED)
        self.show_notes = False
        self.minimap_big = False

    # --------------------------------------------------------------- actions
    def _transmit(self):
        s = self.app.session
        f, c, q = (x.text for x in self.tx_fields)
        s.tx_msg, s.tx_msg_ok = "Transmitting...", False
        s.send_transmit(self.app.net, f, c, q)

    def _close_panel(self):
        self.app.session.panel = None
        for f in self.tx_fields:
            f.focus = False

    def text_input_active(self) -> bool:
        s = self.app.session
        return s.panel == "transmitter"

    def handle_event(self, e) -> bool:
        s = self.app.session
        if s.panel == "transmitter":
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self._close_panel()
                return True
            if e.type == pygame.KEYDOWN and e.key == pygame.K_TAB:
                for i, f in enumerate(self.tx_fields):
                    if f.focus:
                        f.focus = False
                        self.tx_fields[(i + 1) % 3].focus = True
                        break
                else:
                    self.tx_fields[0].focus = True
                return True
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._transmit()
                return True
            for f in self.tx_fields:
                f.handle(e)
            self.btn_tx.handle(e, self.app.audio)
            self.btn_close.handle(e, self.app.audio)
            return True
        if s.popup:
            if (e.type == pygame.KEYDOWN and e.key in (self.app.settings.keys["interact"], pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE)) or \
                    (e.type == pygame.MOUSEBUTTONDOWN):
                s.popup = None
                return True
        return False

    # ------------------------------------------------------------------ draw
    def draw(self, screen, dt: float):
        s = self.app.session
        lib = self.lib
        w, h = screen.get_size()
        st = s.state
        # --- left panel: player + objective
        r = pygame.Rect(12, 12, 400, 206)
        panel(screen, lib, r)
        me = s.remote.get(s.pid)
        draw_text(screen, lib, f"{self.app.player_name}  #{s.pid}", (r.x + 18, r.y + 12), 20, (140, 230, 255))
        words, lines, cur = st["obj"]["text"].split(), [], ""
        for wd in words:
            if len(cur) + len(wd) + 1 > 34 and cur:
                lines.append(cur)
                cur = wd
            else:
                cur = (cur + " " + wd).strip()
        lines.append(cur)
        for i, ln in enumerate(lines[:2]):
            draw_text(screen, lib, ln, (r.x + 18, r.y + 38 + i * 19), 14, (255, 230, 150))
        y = r.y + 82
        for task in st["obj"]["tasks"]:
            col = (110, 230, 150) if task["done"] else (200, 210, 220)
            mark = "[+]" if task["done"] else "[ ]"
            draw_text(screen, lib, f"{mark} {task['label']}", (r.x + 18, y), 13, col)
            y += 19
        # signal progress bar
        found = len(st.get("found", []))
        bx = pygame.Rect(r.x + 18, r.bottom - 22, 364, 8)
        pygame.draw.rect(screen, (20, 30, 40), bx, border_radius=4)
        fw = int(bx.w * found / 5)
        if s.interference:
            fw = int(fw * (0.5 + 0.5 * ((time.time() * 13) % 1)))
        pygame.draw.rect(screen, (80, 220, 255), (bx.x, bx.y, fw, bx.h), border_radius=4)
        # --- top right: timer + connection
        tl = int(s.time_left())
        tcol = (255, 110, 110) if tl < 300 else (230, 240, 245)
        rr = pygame.Rect(w - 232, 12, 220, 74)
        panel(screen, lib, rr)
        draw_text(screen, lib, "%02d:%02d" % (tl // 60, tl % 60), (rr.x + 18, rr.y + 10), 30, tcol, narrow=False)
        net = self.app.net
        ok = net.connected and time.time() - net.last_rx < 3
        screen.blit(lib.icon("signal3" if ok else "signal1", 18, (110, 230, 150) if ok else (240, 100, 100)), (rr.x + 18, rr.y + 46))
        draw_text(screen, lib, f"{net.latency_ms} ms" if ok else "NO SIGNAL", (rr.x + 42, rr.y + 46), 14)
        pcount = sum(1 for p in s.remote.values() if p.connected and p.pid != s.pid) + 1
        draw_text(screen, lib, f"{pcount} online", (rr.right - 18, rr.y + 46), 14, right=True)
        dl = s.daylight()
        if dl is not None:
            from .. import daynight
            lab = daynight.label(s.clock())
            col = {"DAY": (255, 230, 140), "DUSK": (255, 170, 90), "DAWN": (255, 190, 120), "NIGHT": (130, 160, 255)}[lab]
            draw_text(screen, lib, lab, (rr.right - 18, rr.y + 10), 15, col, right=True)
        if s.discover:
            a = max(0.0, min(1.0, (3.2 - (time.time() - s.discover["t"])) / 1.2))
            t1 = lib.text("DISCOVERED", 13, (150, 200, 230))
            t2 = lib.text(s.discover["text"].upper(), 28, (255, 235, 170), narrow=False)
            t1.set_alpha(int(255 * a))
            t2.set_alpha(int(255 * a))
            screen.blit(t1, t1.get_rect(center=(w // 2, 118)))
            screen.blit(t2, t2.get_rect(center=(w // 2, 146)))
        # --- minimap
        if self.minimap_big:
            self._world_map(screen, s, w, h)
        else:
            self._minimap(screen, s, w, h)
        self._combat_hud(screen, s, w, h)
        # --- interaction prompt
        if s.near and not s.panel and not s.popup and not s.end:
            o = s.near
            txt = o.label
            box = pygame.Rect(0, 0, 360, 46)
            box.midbottom = (w // 2, h - 40)
            panel(screen, lib, box)
            if lib.key_e and self.app.settings.keys["interact"] == pygame.K_e:
                k = pygame.transform.smoothscale(lib.key_e, (30, 30))
                screen.blit(k, (box.x + 14, box.y + 8))
            else:
                kb = pygame.Rect(box.x + 12, box.y + 8, 34, 30)
                pygame.draw.rect(screen, (230, 238, 245), kb, border_radius=6)
                pygame.draw.rect(screen, (90, 110, 130), kb, 2, border_radius=6)
                draw_text(screen, lib, self.app.settings.key_name("interact")[:4], kb.center, 12, (20, 30, 40), center=True)
            draw_text(screen, lib, "INTERACT", (box.x + 54, box.y + 7), 14, (140, 230, 255))
            draw_text(screen, lib, txt, (box.x + 54, box.y + 22), 15)
        # --- toasts
        ty = 74 if (s.state.get("boss", {}).get("on") == "active") else 18
        now = time.time()
        for t in s.toasts[-4:]:
            col = {"error": (255, 130, 130), "good": (130, 240, 160)}.get(t["kind"], (230, 240, 245))
            img = lib.text(t["text"], 17, col)
            bw = img.get_width() + 30
            box = pygame.Rect(0, 0, bw, 34)
            box.midtop = (w // 2, ty)
            alpha_ok = now - t["t"] < 4.2
            if alpha_ok:
                panel(screen, lib, box)
                screen.blit(img, (box.x + 15, box.y + 7))
                ty += 40
        # --- echo banner
        if s.banner:
            img = lib.text(s.banner["text"], 22, (255, 120, 140))
            box = img.get_rect(center=(w // 2, h - 120)).inflate(40, 20)
            panel(screen, lib, box, (70, 30, 50))
            screen.blit(img, img.get_rect(center=box.center))
        if s.popup:
            self._popup(screen, s.popup["entry"])
        if s.panel == "transmitter":
            self._transmitter(screen, dt)
        if self.show_notes:
            self._notes(screen, s)

    def _combat_hud(self, screen, s, w, h):
        lib = self.lib
        now = time.time()
        # damage flash
        if now < s.hurt_until:
            a = int(120 * (s.hurt_until - now) / 0.35)
            fl = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(fl, (220, 20, 20, a), (0, 0, w, h), 40)
            screen.blit(fl, (0, 0))
        if s.hp < 35 and not s.dead:
            fl = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(fl, (200, 0, 0, int(40 + 30 * math.sin(now * 6))), (0, 0, w, h), 30)
            screen.blit(fl, (0, 0))
        # hp + weapon panel bottom-left
        from ..weapons import ORDER, WEAPONS
        r = pygame.Rect(12, h - 112, 400, 100)
        panel(screen, lib, r)
        draw_text(screen, lib, "HEALTH", (r.x + 18, r.y + 10), 13, (150, 165, 180))
        bar = pygame.Rect(r.x + 18, r.y + 28, 364, 14)
        pygame.draw.rect(screen, (30, 14, 16), bar, border_radius=6)
        frac = max(0.0, min(1.0, s.hp / 100))
        pygame.draw.rect(screen, (90, 230, 120) if frac > 0.4 else (240, 80, 70), (bar.x, bar.y, int(bar.w * frac), bar.h), border_radius=6)
        draw_text(screen, lib, f"{int(s.hp)}", (bar.right - 6, bar.y - 1), 13, (10, 20, 20), right=True)
        # weapon slots
        for i, name in enumerate(ORDER):
            bx = pygame.Rect(r.x + 18 + i * 56, r.y + 50, 50, 40)
            owned = name in s.owned
            cur = name == s.cur_weapon
            pygame.draw.rect(screen, (60, 110, 160) if cur else ((20, 32, 44) if owned else (14, 20, 26)), bx, border_radius=6)
            pygame.draw.rect(screen, (255, 230, 150) if cur else (60, 76, 92), bx, 2, border_radius=6)
            draw_text(screen, lib, str(i + 1), (bx.x + 5, bx.y + 2), 11, (150, 165, 180))
            if owned:
                g = lib.gun(0.0, name)
                k = min(1.0, 40 / max(1, g.get_width()))
                if k < 1.0:
                    g = pygame.transform.smoothscale(g, (int(g.get_width() * k), max(1, int(g.get_height() * k))))
                screen.blit(g, g.get_rect(center=(bx.centerx, bx.centery + 6)))
            else:
                draw_text(screen, lib, "?", (bx.centerx, bx.centery + 4), 18, (60, 76, 92), center=True)
        res = s.reserve_now
        res_txt = "INF" if res == -1 else str(res)
        wl = WEAPONS.get(s.cur_weapon, WEAPONS["pistol"])
        txt = "RELOADING..." if s.reloading else f"{wl['label']}  {s.ammo}/{wl['clip']}  |  {res_txt}"
        draw_text(screen, lib, txt, (r.right - 14, r.y + 8), 15, (255, 120, 120) if (s.reloading or s.ammo == 0) else (255, 230, 150), right=True)
        # boss bar
        bs = s.state.get("boss", {})
        if bs.get("on") == "active" and bs.get("max"):
            bw = 560
            br = pygame.Rect(w // 2 - bw // 2, 20, bw, 18)
            pygame.draw.rect(screen, (20, 8, 28), br.inflate(8, 8), border_radius=8)
            pygame.draw.rect(screen, (60, 20, 70), br, border_radius=6)
            f = max(0.0, bs["hp"] / max(1, bs["max"]))
            pygame.draw.rect(screen, (190, 70, 255) if bs["phase"] < 3 else (255, 60, 70), (br.x, br.y, int(br.w * f), br.h), border_radius=6)
            draw_text(screen, lib, f"THE ECHO WARDEN   -   PHASE {bs['phase']}", (w // 2, br.bottom + 14), 14, (230, 190, 255), center=True)
        # first-seconds control hint
        if s.t < 14:
            st = self.app.settings
            kn = st.key_name
            hint = (f"{kn('up')}{kn('left')}{kn('down')}{kn('right')} move   MOUSE aim   LMB shoot   {kn('reload')} reload   "
                    f"{kn('w1')}-{kn('w5')}/{kn('weapon_next')}/wheel weapons   {kn('interact')} interact   {kn('chat')} chat   {kn('notes')} notes")
            draw_text(screen, lib, hint, (w // 2, h - 140), 15, (200, 215, 230), center=True)
        if s.dead:
            shade = pygame.Surface((w, h), pygame.SRCALPHA)
            shade.fill((60, 0, 0, 150))
            screen.blit(shade, (0, 0))
            left = max(0, 8 - (now - s.dead_since))
            draw_text(screen, lib, "YOU WERE OVERWHELMED", (w // 2, h // 2 - 30), 44, (255, 120, 120), center=True, narrow=False)
            draw_text(screen, lib, f"Respawning at the Atrium in {int(left) + 1}...", (w // 2, h // 2 + 20), 22, (255, 210, 210), center=True)

    def _minimap(self, screen, s, w, h):
        mm = s.mini
        scale = 1
        mw, mh = mm.get_width() * scale, mm.get_height() * scale
        if scale != 1:
            surf = pygame.transform.scale(mm, (mw, mh))
        else:
            surf = mm
        box = pygame.Rect(w - mw - 24, h - mh - 24, mw + 12, mh + 12)
        panel(screen, self.lib, box)
        screen.blit(surf, (box.x + 6, box.y + 6))
        for p in s.remote.values():
            if p.connected and p.seen:
                tx, ty = int(p.x // TILE), int(p.y // TILE)
                if s.discovered[ty * s.map.width + tx]:
                    pygame.draw.circle(screen, p.color, (box.x + 6 + tx * scale, box.y + 6 + ty * scale), 2 * scale)
        if s.scan:
            for zx, zy, _k in s.scan["z"]:
                pygame.draw.circle(screen, (255, 70, 70), (box.x + 6 + int(zx // TILE) * scale, box.y + 6 + int(zy // TILE) * scale), 2 * scale)
            if s.scan.get("boss"):
                bx, by = s.scan["boss"]
                pygame.draw.circle(screen, (210, 100, 255), (box.x + 6 + int(bx // TILE) * scale, box.y + 6 + int(by // TILE) * scale), 4 * scale)
        for pk in s.pickups:
            if pk[1] == 2:
                pygame.draw.circle(screen, (255, 215, 60), (box.x + 6 + int(pk[2] // TILE) * scale, box.y + 6 + int(pk[3] // TILE) * scale), 4)
        px, py = int(s.x // TILE), int(s.y // TILE)
        pygame.draw.circle(screen, (255, 255, 255), (box.x + 6 + px * scale, box.y + 6 + py * scale), 3 * scale)
        pygame.draw.circle(screen, (60, 160, 255), (box.x + 6 + px * scale, box.y + 6 + py * scale), 2 * scale)

    def _world_map(self, screen, s, w, h):
        """Big map (M): explored area, discovered places with names, camps, supply drops, players."""
        lib = self.lib
        mm = s.mini
        scale = max(1, min(5, (w - 160) // mm.get_width(), (h - 190) // mm.get_height()))
        mw, mh = mm.get_width() * scale, mm.get_height() * scale
        box = pygame.Rect(0, 0, mw + 24, mh + 64)
        box.center = (w // 2, h // 2 + 6)
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        screen.blit(shade, (0, 0))
        panel(screen, lib, box, (18, 32, 48))
        draw_text(screen, lib, "WORLD MAP", (box.centerx, box.y + 22), 20, (150, 235, 255), center=True)
        ox, oy = box.x + 12, box.y + 44
        screen.blit(pygame.transform.scale(mm, (mw, mh)), (ox, oy))
        m = s.map
        for rid in s.visited_rooms:
            r = m.rooms[rid]
            cx, cy = ox + int((r.x + r.w / 2) * scale), oy + int((r.y + r.h / 2) * scale)
            img = lib.text(r.name, 12, (255, 235, 170))
            bg = img.get_rect(center=(cx, cy)).inflate(6, 2)
            sh = pygame.Surface(bg.size, pygame.SRCALPHA)
            sh.fill((0, 0, 0, 150))
            screen.blit(sh, bg)
            screen.blit(img, img.get_rect(center=(cx, cy)))
        for o in m.objects:
            if o.kind == "camp" and s.discovered[min(len(s.discovered) - 1, o.y * m.width + o.x)]:
                lit = o.id in s.state.get("camps", ())
                pygame.draw.circle(screen, (255, 160, 50) if lit else (150, 110, 70), (ox + o.x * scale, oy + o.y * scale), 4)
        for pk in s.pickups:
            if pk[1] == 2:
                pygame.draw.circle(screen, (255, 215, 60), (ox + int(pk[2] // TILE) * scale, oy + int(pk[3] // TILE) * scale), 6)
                draw_text(screen, lib, "SUPPLY", (ox + int(pk[2] // TILE) * scale, oy + int(pk[3] // TILE) * scale - 14), 12, (255, 230, 120), center=True)
        for p in s.remote.values():
            if p.connected and p.seen:
                pygame.draw.circle(screen, p.color, (ox + int(p.x // TILE) * scale, oy + int(p.y // TILE) * scale), 4)
        pygame.draw.circle(screen, (255, 255, 255), (ox + int(s.x // TILE) * scale, oy + int(s.y // TILE) * scale), 6)
        pygame.draw.circle(screen, (60, 160, 255), (ox + int(s.x // TILE) * scale, oy + int(s.y // TILE) * scale), 4)
        if s.scan:
            for zx, zy, _k in s.scan["z"]:
                pygame.draw.circle(screen, (255, 70, 70), (ox + int(zx // TILE) * scale, oy + int(zy // TILE) * scale), 3)
        draw_text(screen, lib, "white = you   orange = campfires   gold = supply drops   (press the map key to close)", (box.centerx, box.bottom - 16), 12, (150, 165, 180), center=True)

    def _popup(self, screen, entry):
        lib = self.lib
        w, h = screen.get_size()
        box = pygame.Rect(0, 0, 520, 130 + 30 * len(entry["lines"]))
        box.center = (w // 2, h // 2 - 30)
        panel(screen, lib, box, (30, 50, 70))
        draw_text(screen, lib, entry["title"], (box.centerx, box.y + 30), 24, (255, 230, 150), center=True)
        y = box.y + 66
        for ln in entry["lines"]:
            big = ln.isdigit()
            draw_text(screen, lib, ln, (box.centerx, y + (10 if big else 0)), 46 if big else 20,
                      (140, 240, 255) if big else (230, 240, 245), center=True, narrow=not big)
            y += 56 if big else 30
        integ = entry.get("integrity", 100)
        col = (110, 230, 150) if integ >= 100 else (255, 120, 120)
        draw_text(screen, lib, f"SIGNAL INTEGRITY {integ}%" + ("" if integ >= 100 else "  - UNSTABLE"), (box.centerx, box.bottom - 36), 15, col, center=True)
        draw_text(screen, lib, "[E] close", (box.centerx, box.bottom - 16), 13, (150, 165, 180), center=True)

    def _transmitter(self, screen, dt):
        lib = self.lib
        s = self.app.session
        w, h = screen.get_size()
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        screen.blit(shade, (0, 0))
        box = pygame.Rect(0, 0, 620, 420)
        box.center = (w // 2, h // 2)
        panel(screen, lib, box, (24, 44, 66))
        draw_text(screen, lib, "EMERGENCY TRANSMITTER", (box.centerx, box.y + 36), 28, (140, 240, 255), center=True, narrow=False)
        labels = [("Frequency", "3 digits"), ("Channel", "2 digits"), ("Sequence", "3 digits")]
        y = box.y + 92
        for (lab, hint), f in zip(labels, self.tx_fields):
            draw_text(screen, lib, lab + ":", (box.x + 70, y + 10), 22)
            f.rect.topleft = (box.x + 270, y)
            f.draw(screen, lib, dt)
            draw_text(screen, lib, hint, (f.rect.right + 16, y + 14), 14, (150, 165, 180))
            y += 62
        self.btn_tx.rect.topleft = (box.x + 90, box.bottom - 120)
        self.btn_close.rect.topleft = (box.right - 210, box.bottom - 120)
        self.btn_tx.draw(screen, lib)
        self.btn_close.draw(screen, lib)
        if s.interference:
            msg, col = "SIGNAL INTERFERENCE - transmission blocked", (255, 160, 80)
        else:
            msg, col = s.tx_msg, ((120, 240, 160) if s.tx_msg_ok else (255, 130, 130))
        draw_text(screen, lib, msg, (box.centerx, box.bottom - 40), 17, col, center=True)

    def _notes(self, screen, s):
        lib = self.lib
        w, h = screen.get_size()
        box = pygame.Rect(0, 0, 760, 560)
        box.center = (w // 2, h // 2)
        panel(screen, lib, box, (22, 38, 56))
        draw_text(screen, lib, "NOTEBOOK  (TAB to close)", (box.centerx, box.y + 28), 22, (140, 240, 255), center=True)
        notes = s.notes
        if not notes:
            draw_text(screen, lib, "Nothing recorded yet. Read terminals to collect information.", (box.centerx, box.centery), 17, (170, 185, 200), center=True)
        col_w = 340
        for i, n in enumerate(notes[-8:]):
            cx = box.x + 30 + (i % 2) * (col_w + 20)
            cy = box.y + 64 + (i // 2) * 118
            r = pygame.Rect(cx, cy, col_w, 108)
            pygame.draw.rect(screen, (14, 24, 34), r, border_radius=8)
            integ = n.get("integrity", 100)
            pygame.draw.rect(screen, (110, 230, 150) if integ >= 100 else (255, 120, 120), r, 2, border_radius=8)
            draw_text(screen, lib, n["title"], (r.x + 12, r.y + 8), 15, (255, 230, 150))
            yy = r.y + 30
            for ln in n["lines"][:3]:
                draw_text(screen, lib, ln[:34], (r.x + 12, yy), 15)
                yy += 20
            if integ < 100:
                draw_text(screen, lib, f"UNSTABLE {integ}%", (r.right - 10, r.y + 8), 13, (255, 120, 120), right=True)
