"""LAN game browser (UDP broadcast discovery) with a debug manual-IP fallback."""
from __future__ import annotations

import pygame

from ..config import DEFAULT_GAME_PORT
from .menu import MainMenu, draw_background
from .widgets import BTN_GREEN, BTN_RED, Button, TextField, draw_text, panel


class BrowserScreen:
    def __init__(self, app):
        self.app = app
        self.t = 0.0
        self.sel = -1
        self.games = []
        self.rects = []
        self.join_btn = Button((860, 590, 300, 52), "REQUEST TO JOIN", self._join, BTN_GREEN, enabled=False)
        self.back = Button((120, 590, 200, 52), "BACK", self._back, BTN_RED)
        self.ip = TextField((420, 640, 280, 40), "", 40, False, "host:port (debug)")
        self.ip_btn = Button((710, 640, 130, 40), "CONNECT", self._manual, size=16)
        app.listener_start()

    def _back(self):
        self.app.listener_stop()
        self.app.goto(MainMenu(self.app))

    def _join(self):
        if 0 <= self.sel < len(self.games):
            g = self.games[self.sel]
            self.app.listener_stop()
            self.app.join_game(g["host"], g["port"])

    def _manual(self):
        txt = self.ip.text.strip()
        if not txt:
            return
        host, _, port = txt.partition(":")
        try:
            port = int(port) if port else DEFAULT_GAME_PORT
        except ValueError:
            return
        self.app.listener_stop()
        self.app.join_game(host, port)

    def handle_event(self, e):
        self.ip.handle(e)
        self.back.handle(e, self.app.audio)
        self.join_btn.handle(e, self.app.audio)
        self.ip_btn.handle(e, self.app.audio)
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, r in enumerate(self.rects):
                if r.collidepoint(e.pos):
                    self.sel = i
                    self.app.audio.play("click")

    def update(self, dt):
        self.t += dt
        self.games = self.app.listener.get_games() if self.app.listener else []
        if self.sel >= len(self.games):
            self.sel = -1
        g = self.games[self.sel] if self.sel >= 0 else None
        self.join_btn.enabled = bool(g and g["state"] == "lobby" and g["players"] < g["max"])

    def draw(self, screen):
        lib = self.app.lib
        draw_background(screen, lib, self.t)
        draw_text(screen, lib, "THE LAST SIGNAL", (640, 50), 40, (150, 235, 255), center=True, narrow=False)
        draw_text(screen, lib, "LAN GAMES", (640, 100), 22, (255, 200, 120), center=True)
        box = pygame.Rect(120, 140, 1040, 430)
        panel(screen, lib, box)
        self.rects = []
        if self.app.listener and self.app.listener.error:
            draw_text(screen, lib, self.app.listener.error[:80], (640, 330), 18, (255, 130, 130), center=True)
        elif not self.games:
            dots = "." * (int(self.t * 2) % 4)
            draw_text(screen, lib, "Searching for games on your network" + dots, (640, 340), 20, (170, 185, 200), center=True)
        y = box.y + 20
        for i, g in enumerate(self.games[:8]):
            r = pygame.Rect(box.x + 20, y, box.w - 40, 46)
            self.rects.append(r)
            col = (60, 110, 160) if i == self.sel else (28, 44, 62)
            pygame.draw.rect(screen, col, r, border_radius=8)
            draw_text(screen, lib, g["name"], (r.x + 16, r.y + 12), 22)
            draw_text(screen, lib, g["map"], (r.x + 380, r.y + 14), 17, (255, 200, 120))
            draw_text(screen, lib, f"{g['players']} / {g['max']} players", (r.x + 640, r.y + 14), 17)
            st = "IN LOBBY" if g["state"] == "lobby" else "IN PROGRESS"
            draw_text(screen, lib, st, (r.right - 16, r.y + 14), 16, (130, 240, 160) if g["state"] == "lobby" else (255, 140, 120), right=True)
            y += 52
        self.join_btn.draw(screen, lib)
        self.back.draw(screen, lib)
        self.ip.draw(screen, lib, 1 / 60)
        self.ip_btn.draw(screen, lib)
        draw_text(screen, lib, "Manual IP is for debugging only. Normal play uses discovery.", (420, 622), 13, (110, 125, 140))
