"""Lobby screen: player list, host controls and join-request prompts."""
from __future__ import annotations

import pygame

from ..config import PLAYER_COLORS
from .menu import draw_background
import time

from .widgets import BTN_GREEN, BTN_RED, Button, TextField, draw_text, panel


class LobbyScreen:
    def __init__(self, app):
        self.app = app
        self.t = 0.0
        self.start_btn = Button((470, 620, 340, 56), "START GAME", app.request_start, BTN_GREEN)
        self.leave_btn = Button((40, 640, 180, 44), "LEAVE", app.leave_game, BTN_RED, size=18)
        self.chat = TextField((920, 600, 330, 36), "", 120, False, "Chat (Enter)")
        self.accept = Button((0, 0, 150, 46), "ACCEPT", self._accept, BTN_GREEN)
        self.reject = Button((0, 0, 150, 46), "REJECT", self._reject, BTN_RED)

    def _accept(self):
        if self.app.join_requests:
            r = self.app.join_requests.pop(0)
            self.app.net.send({"t": "join_decision", "rid": r["rid"], "accept": True})

    def _reject(self):
        if self.app.join_requests:
            r = self.app.join_requests.pop(0)
            self.app.net.send({"t": "join_decision", "rid": r["rid"], "accept": False})

    def handle_event(self, e):
        if self.app.join_requests and self.app.is_host:
            self.accept.handle(e, self.app.audio)
            self.reject.handle(e, self.app.audio)
            return
        self.chat.handle(e)
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.chat.focus:
            if self.chat.text.strip():
                self.app.net.send({"t": "chat", "text": self.chat.text.strip()})
            self.chat.text = ""
        self.leave_btn.handle(e, self.app.audio)
        if self.app.is_host:
            self.start_btn.handle(e, self.app.audio)

    def update(self, dt):
        self.t += dt

    def draw(self, screen):
        app, lib = self.app, self.app.lib
        lob = app.lobby or {}
        draw_background(screen, lib, self.t)
        draw_text(screen, lib, "LOBBY", (640, 56), 40, (150, 235, 255), center=True, narrow=False)
        draw_text(screen, lib, lob.get("map", "Research Station A-17"), (640, 106), 22, (255, 200, 120), center=True)
        draw_text(screen, lib, f"{lob.get('name', '')}   seed {lob.get('seed', '')}", (640, 134), 16, (150, 165, 180), center=True)
        box = pygame.Rect(380, 170, 520, 430)
        panel(screen, lib, box)
        players = lob.get("players", [])
        draw_text(screen, lib, "PLAYERS", (box.x + 24, box.y + 16), 16, (150, 165, 180))
        cnt = len([p for p in players if p["connected"]])
        draw_text(screen, lib, f"{cnt} / {lob.get('max', 15)}", (box.right - 24, box.y + 16), 16, right=True)
        y = box.y + 46
        for p in players:
            col = PLAYER_COLORS[(p["pid"] - 1) % len(PLAYER_COLORS)]
            pygame.draw.circle(screen, col, (box.x + 38, y + 12), 9)
            name = p["name"] + ("  (host)" if p["host"] else "") + ("" if p["connected"] else "  (offline)")
            draw_text(screen, lib, name, (box.x + 60, y), 20, (230, 240, 245) if p["connected"] else (120, 130, 140))
            y += 25
        if app.is_host:
            self.start_btn.draw(screen, lib)
            if app.host_addr:
                draw_text(screen, lib, f"Other computers on this LAN will find this game automatically.   (debug: {app.host_addr})", (640, 590), 13, (110, 125, 140), center=True)
        else:
            draw_text(screen, lib, "Waiting for the host to start the game...", (640, 640), 20, (170, 185, 200), center=True)
        self.leave_btn.draw(screen, lib)
        # lobby chat box
        cb = pygame.Rect(920, 200, 330, 390)
        panel(screen, lib, cb)
        draw_text(screen, lib, "CREW CHAT", (cb.x + 18, cb.y + 12), 14, (150, 165, 180))
        yy = cb.bottom - 28
        for name, text, t0, pid in reversed(app.chat_log[-14:]):
            draw_text(screen, lib, f"{name}: {text}"[:34], (cb.x + 16, yy), 14)
            yy -= 22
        self.chat.draw(screen, lib, 1 / 60)
        # toast
        for i, t in enumerate(app.lobby_toasts[-3:]):
            draw_text(screen, lib, t, (640, 690 - i * 22), 15, (170, 220, 255), center=True)
        # join request prompt
        if app.join_requests and app.is_host:
            shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 150))
            screen.blit(shade, (0, 0))
            b = pygame.Rect(0, 0, 520, 240)
            b.center = (640, 360)
            panel(screen, lib, b, (30, 56, 84))
            draw_text(screen, lib, "PLAYER REQUEST", (640, b.y + 40), 30, (150, 235, 255), center=True, narrow=False)
            draw_text(screen, lib, f"{app.join_requests[0]['name']} wants to join.", (640, b.y + 100), 22, center=True)
            if len(app.join_requests) > 1:
                draw_text(screen, lib, f"(+{len(app.join_requests) - 1} more waiting)", (640, b.y + 130), 14, (150, 165, 180), center=True)
            self.accept.rect.topleft = (b.x + 70, b.bottom - 76)
            self.reject.rect.topleft = (b.right - 220, b.bottom - 76)
            self.accept.draw(screen, lib)
            self.reject.draw(screen, lib)
