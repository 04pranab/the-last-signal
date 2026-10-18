"""Settings: sound (mute, per-category volume, horror ambience) and fully rebindable controls."""
from __future__ import annotations

import pygame

from ..settings import ACTIONS, LABELS
from .menu import draw_background
from .widgets import BTN_GREEN, BTN_RED, Button, Slider, draw_text, panel


class SettingsScreen:
    def __init__(self, app, back):
        self.app, self.back = app, back
        self.t = 0.0
        self.st = app.settings
        self.waiting = None            # action id waiting for a key press
        self.sliders = []
        rows = [("MASTER", None, "master"), ("MENU / UI", "ui", None), ("WEAPONS & HITS", "effects", None),
                ("DOORS & MACHINES", "world", None), ("HORROR AMBIENCE", "ambient", None)]
        y = 170
        for label, cat, _ in rows:
            val = self.st.master if cat is None else self.st.vol[cat]
            sl = Slider((130, y + 14, 260, 20), val, self._make_change(cat), self._make_release(cat))
            self.sliders.append((label, sl))
            y += 62
        self.mute_btn = Button((60, 500, 330, 44), "", self._toggle_mute, size=18)
        self.amb_btn = Button((60, 552, 330, 44), "", self._toggle_amb, size=18)
        self.fs_btn = Button((60, 604, 330, 44), "", self._toggle_fs, size=18)
        self.reset_btn = Button((470, 640, 300, 44), "RESET CONTROLS", self._reset, size=18)
        self.back_btn = Button((1000, 640, 220, 44), "BACK", self._back, BTN_GREEN, size=18)
        self.rows = []          # (action, rect)
        self._refresh()

    # ---- callbacks
    def _make_change(self, cat):
        def f(v):
            if cat is None:
                self.st.master = v
            else:
                self.st.vol[cat] = v
        return f

    def _make_release(self, cat):
        def f(v):
            self.st.save()
            self.app.audio.preview(cat or "ui")
        return f

    def _toggle_mute(self):
        self.st.mute = not self.st.mute
        self.st.save()
        self._refresh()

    def _toggle_amb(self):
        self.st.ambient_on = not self.st.ambient_on
        self.st.save()
        self._refresh()

    def _toggle_fs(self):
        self.app.toggle_fullscreen()
        self._refresh()

    def _reset(self):
        self.st.reset_keys()
        self.st.save()
        self.waiting = None

    def _back(self):
        self.st.save()
        self.app.goto(self.back)

    def _refresh(self):
        self.mute_btn.text = "SOUND: OFF (MUTED)" if self.st.mute else "SOUND: ON"
        self.mute_btn.tint = BTN_RED if self.st.mute else BTN_GREEN
        self.amb_btn.text = "HORROR AMBIENCE: ON" if self.st.ambient_on else "HORROR AMBIENCE: OFF"
        self.fs_btn.text = "FULLSCREEN: ON" if self.app.fullscreen else "FULLSCREEN: OFF"

    # ---- events
    def handle_event(self, e):
        if self.waiting:
            if e.type == pygame.KEYDOWN:
                if e.key != pygame.K_ESCAPE:
                    self.st.bind(self.waiting, e.key)
                    self.st.save()
                self.waiting = None
            elif e.type == pygame.MOUSEBUTTONDOWN:
                self.waiting = None
            return
        for _, sl in self.sliders:
            sl.handle(e)
        for b in (self.mute_btn, self.amb_btn, self.fs_btn, self.reset_btn, self.back_btn):
            b.handle(e, self.app.audio)
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for a, r in self.rows:
                if r.collidepoint(e.pos):
                    self.waiting = a
                    self.app.audio.play("click")
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self._back()

    def update(self, dt):
        self.t += dt

    def draw(self, screen):
        lib = self.app.lib
        draw_background(screen, lib, self.t)
        draw_text(screen, lib, "SETTINGS", (640, 60), 40, (150, 235, 255), center=True, narrow=False)
        # sound panel
        sp = pygame.Rect(40, 110, 370, 560)
        panel(screen, lib, sp)
        draw_text(screen, lib, "SOUND", (sp.x + 20, sp.y + 14), 18, (255, 200, 120))
        for i, (label, sl) in enumerate(self.sliders):
            y = 170 + i * 62
            draw_text(screen, lib, label, (60, y - 14), 13, (150, 165, 180))
            sl.draw(screen, lib)
            draw_text(screen, lib, f"{int(sl.value * 100)}%", (400, y + 14), 14, right=True)
        self.mute_btn.draw(screen, lib)
        self.amb_btn.draw(screen, lib)
        self.fs_btn.draw(screen, lib)
        # controls panel
        cp = pygame.Rect(430, 110, 810, 510)
        panel(screen, lib, cp)
        draw_text(screen, lib, "CONTROLS  (click a row, then press the new key)", (cp.x + 20, cp.y + 14), 16, (255, 200, 120))
        self.rows = []
        per_col = 9
        for i, (aid, label, _d) in enumerate(ACTIONS):
            col, row = divmod(i, per_col)
            r = pygame.Rect(cp.x + 20 + col * 395, cp.y + 56 + row * 48, 375, 40)
            self.rows.append((aid, r))
            waiting = self.waiting == aid
            pygame.draw.rect(screen, (60, 110, 160) if waiting else (24, 38, 54), r, border_radius=8)
            pygame.draw.rect(screen, (255, 230, 150) if waiting else (60, 80, 100), r, 2, border_radius=8)
            draw_text(screen, lib, label, (r.x + 14, r.y + 10), 15)
            kn = "press a key..." if waiting else self.st.key_name(aid)
            draw_text(screen, lib, kn, (r.right - 14, r.y + 10), 15, (255, 230, 150) if not waiting else (255, 255, 255), right=True)
        draw_text(screen, lib, "Arrow keys always work for movement. ESC = pause menu and cannot be rebound.", (cp.x + 20, cp.bottom - 28), 13, (130, 145, 160))
        self.reset_btn.draw(screen, lib)
        self.back_btn.draw(screen, lib)
