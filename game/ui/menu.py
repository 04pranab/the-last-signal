"""Main menu, create-game form and simple message / connecting screens."""
from __future__ import annotations

import math

import pygame

from ..config import GAME_NAME, MAX_PLAYERS, VERSION
from .widgets import BTN_GREEN, BTN_RED, Button, TextField, draw_text, panel


def draw_background(screen, lib, t):
    w, h = screen.get_size()
    screen.fill((8, 14, 22))
    for i in range(0, h, 4):
        pygame.draw.line(screen, (10, 18, 28), (0, i), (w, i))
    star = lib.sprites.get("terminal_dead")
    for k in range(18):
        x = (k * 173 + t * (6 + k % 5)) % (w + 40) - 20
        y = (k * 97) % h
        pygame.draw.circle(screen, (30, 60, 80), (int(x), int(y)), 2 + k % 2)
    # pulsing signal rings from the title
    cx, cy = w // 2, 150
    for i in range(3):
        r = int(((t * 40 + i * 70) % 210) + 60)
        a = max(0, 90 - int((r - 60) * 0.45))
        s = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(s, (80, 220, 255, a), (r + 2, r + 2), r, 2)
        screen.blit(s, (cx - r - 2, cy - r - 2))


def draw_title(screen, lib, t, y=110):
    w = screen.get_width()
    draw_text(screen, lib, GAME_NAME, (w // 2, y), 64, (150, 235, 255), center=True, narrow=False)
    draw_text(screen, lib, "RESEARCH STATION A-17", (w // 2, y + 52), 22, (255, 200, 120), center=True)


class MainMenu:
    def __init__(self, app):
        self.app = app
        self.t = 0.0
        cx = 640
        self.name = TextField((cx - 170, 270, 340, 46), app.player_name, 16, False, "Callsign")
        self.map_btn = Button((cx - 170, 590, 340, 40), self._map_label(), self._cycle_map, size=16)
        self.buttons = [
            Button((cx - 170, 340, 340, 52), "SINGLE PLAYER", app.start_single_player, BTN_GREEN),
            Button((cx - 170, 402, 340, 52), "CREATE GAME", lambda: app.goto(CreateScreen(app))),
            Button((cx - 170, 464, 340, 52), "FIND LAN GAMES", app.open_browser),
            Button((cx - 170, 526, 340, 52), "QUIT", app.quit, BTN_RED),
        ]

    def _map_label(self):
        from ..maps import MAP_REGISTRY
        return "MAP: " + MAP_REGISTRY[self.app.selected_map].map_name.upper()

    def _cycle_map(self):
        from ..maps import MAP_REGISTRY
        ids = list(MAP_REGISTRY)
        self.app.selected_map = ids[(ids.index(self.app.selected_map) + 1) % len(ids)]
        self.map_btn.text = self._map_label()

    def handle_event(self, e):
        self.name.handle(e)
        self.map_btn.handle(e, self.app.audio)
        for b in self.buttons:
            if b.handle(e, self.app.audio):
                self.app.set_name(self.name.text)
                return

    def update(self, dt):
        self.t += dt

    def draw(self, screen):
        lib = self.app.lib
        draw_background(screen, lib, self.t)
        draw_title(screen, lib, self.t)
        draw_text(screen, lib, "CALLSIGN", (640 - 170, 245), 14, (150, 165, 180))
        self.name.draw(screen, lib, 1 / 60)
        for b in self.buttons:
            b.draw(screen, lib)
        self.map_btn.draw(screen, lib)
        draw_text(screen, lib, f"v{VERSION}   WASD move   E interact   TAB notebook   ESC menu", (640, 690), 14, (110, 125, 140), center=True)


class CreateScreen:
    def __init__(self, app):
        self.app = app
        self.t = 0.0
        self.limit = MAX_PLAYERS
        self.gname = TextField((470, 230, 340, 46), f"{app.player_name}'s Game"[:24], 24, False, "Game name")
        self.seed = TextField((470, 488, 340, 46), "", 10, True, "RANDOM")
        self.map_btn = Button((470, 410, 340, 36), "", self._cycle_map, size=16)
        self._cycle(0)
        self.btns = [
            Button((470, 330, 52, 46), "-", self._dec, size=26),
            Button((758, 330, 52, 46), "+", self._inc, size=26),
            Button((470, 556, 340, 54), "CREATE GAME", self._create, BTN_GREEN),
            Button((470, 620, 340, 46), "BACK", lambda: app.goto(MainMenu(app)), BTN_RED),
        ]

    def _cycle(self, d):
        from ..maps import MAP_REGISTRY
        ids = list(MAP_REGISTRY)
        self.app.selected_map = ids[(ids.index(self.app.selected_map) + d) % len(ids)]
        self.map_btn.text = MAP_REGISTRY[self.app.selected_map].map_name

    def _cycle_map(self):
        self._cycle(1)

    def _dec(self):
        self.limit = max(1, self.limit - 1)

    def _inc(self):
        self.limit = min(MAX_PLAYERS, self.limit + 1)

    def _create(self):
        self.app.host_game(self.gname.text.strip() or "Research Station", self.limit, self.seed.text)

    def handle_event(self, e):
        self.gname.handle(e)
        self.seed.handle(e)
        self.map_btn.handle(e, self.app.audio)
        for b in self.btns:
            b.handle(e, self.app.audio)

    def update(self, dt):
        self.t += dt

    def draw(self, screen):
        lib = self.app.lib
        draw_background(screen, lib, self.t)
        draw_text(screen, lib, "CREATE GAME", (640, 120), 40, (150, 235, 255), center=True, narrow=False)
        draw_text(screen, lib, "NAME", (470, 206), 14, (150, 165, 180))
        self.gname.draw(screen, lib, 1 / 60)
        draw_text(screen, lib, "PLAYER LIMIT", (470, 306), 14, (150, 165, 180))
        draw_text(screen, lib, str(self.limit), (640, 353), 28, center=True, narrow=False)
        draw_text(screen, lib, "MAP", (470, 392), 14, (150, 165, 180))
        self.map_btn.draw(screen, lib)
        draw_text(screen, lib, "SEED (empty = random)", (470, 466), 14, (150, 165, 180))
        self.seed.draw(screen, lib, 1 / 60)
        for b in self.btns:
            b.draw(screen, lib)


class MessageScreen:
    """Connecting / error / info screen with an optional cancel button."""

    def __init__(self, app, title, text="", button="BACK", on_click=None, spinner=False, tint=None):
        self.app, self.title, self.text, self.spinner = app, title, text, spinner
        self.t = 0.0
        cb = on_click or (lambda: app.goto(MainMenu(app)))
        self.btn = Button((540, 470, 200, 50), button, cb, tint or BTN_RED)

    def handle_event(self, e):
        self.btn.handle(e, self.app.audio)

    def update(self, dt):
        self.t += dt

    def draw(self, screen):
        lib = self.app.lib
        draw_background(screen, lib, self.t)
        box = pygame.Rect(0, 0, 640, 260)
        box.center = (640, 340)
        panel(screen, lib, box)
        draw_text(screen, lib, self.title, (640, 280), 32, (150, 235, 255), center=True, narrow=False)
        draw_text(screen, lib, self.text, (640, 345), 18, center=True)
        if self.spinner:
            for i in range(8):
                a = self.t * 4 + i * math.pi / 4
                pygame.draw.circle(screen, (80 + i * 20, 200, 255), (640 + int(26 * math.cos(a)), 405 + int(26 * math.sin(a))), 4)
        self.btn.draw(screen, lib)
