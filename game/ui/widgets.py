"""Small widget toolkit drawn with the supplied Kenney UI frames."""
from __future__ import annotations

from typing import Callable, Optional

import pygame

PANEL_TINT = (40, 62, 84)
BTN_TINT = (70, 150, 210)
BTN_HOVER = (110, 200, 255)
BTN_OFF = (80, 90, 100)
BTN_GREEN = (70, 190, 120)
BTN_RED = (210, 80, 80)


def panel(screen, lib, rect: pygame.Rect, tint=PANEL_TINT) -> None:
    screen.blit(lib.frame("panel_rectangle_screws", rect.w, rect.h, tint), rect.topleft)


def draw_text(screen, lib, text, pos, size=18, color=(230, 240, 245), center=False, right=False, narrow=True):
    img = lib.text(text, size, color, narrow)
    r = img.get_rect()
    if center:
        r.center = pos
    elif right:
        r.topright = pos
    else:
        r.topleft = pos
    screen.blit(img, r)
    return r


class Button:
    def __init__(self, rect, text, callback: Callable, tint=BTN_TINT, enabled=True, size=22):
        self.rect = pygame.Rect(rect)
        self.text, self.callback, self.tint, self.enabled, self.size = text, callback, tint, enabled, size
        self.hover = False

    def handle(self, e, audio=None) -> bool:
        if e.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(e.pos)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.enabled and self.rect.collidepoint(e.pos):
            if audio:
                audio.play("click")
            self.callback()
            return True
        return False

    def draw(self, screen, lib):
        tint = BTN_OFF if not self.enabled else (BTN_HOVER if self.hover else self.tint)
        img = lib.frame("button_rectangle_depth", self.rect.w, self.rect.h, tint, 14)
        screen.blit(img, self.rect.topleft)
        col = (20, 30, 40) if self.enabled else (150, 160, 170)
        draw_text(screen, lib, self.text, (self.rect.centerx, self.rect.centery - 2), self.size, col, center=True)


class TextField:
    def __init__(self, rect, text="", max_len=16, numeric=False, placeholder=""):
        self.rect = pygame.Rect(rect)
        self.text, self.max_len, self.numeric, self.placeholder = text, max_len, numeric, placeholder
        self.focus = False
        self.blink = 0.0

    def handle(self, e) -> None:
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.focus = self.rect.collidepoint(e.pos)
        elif e.type == pygame.KEYDOWN and self.focus:
            if e.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB, pygame.K_ESCAPE):
                pass
            elif e.unicode and e.unicode.isprintable() and len(self.text) < self.max_len:
                if self.numeric and not e.unicode.isdigit():
                    return
                self.text += e.unicode

    def draw(self, screen, lib, dt=0.0):
        self.blink = (self.blink + dt) % 1.0
        tint = (230, 240, 255) if self.focus else (170, 185, 200)
        screen.blit(lib.frame("panel_glass", self.rect.w, self.rect.h, tint, 12), self.rect.topleft)
        if self.text or self.focus:
            s = self.text + ("|" if self.focus and self.blink < 0.5 else "")
            draw_text(screen, lib, s, (self.rect.x + 12, self.rect.centery - 11), 20, (20, 30, 40))
        else:
            draw_text(screen, lib, self.placeholder, (self.rect.x + 12, self.rect.centery - 11), 20, (110, 120, 130))


class Slider:
    """Horizontal 0..1 slider (drag with the mouse)."""

    def __init__(self, rect, value: float, on_change=None, on_release=None):
        self.rect = pygame.Rect(rect)
        self.value = value
        self.on_change, self.on_release = on_change, on_release
        self.drag = False

    def _set_from(self, x):
        v = (x - self.rect.x) / max(1, self.rect.w)
        self.value = max(0.0, min(1.0, v))
        if self.on_change:
            self.on_change(self.value)

    def handle(self, e) -> None:
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.inflate(0, 20).collidepoint(e.pos):
            self.drag = True
            self._set_from(e.pos[0])
        elif e.type == pygame.MOUSEMOTION and self.drag:
            self._set_from(e.pos[0])
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.drag:
            self.drag = False
            if self.on_release:
                self.on_release(self.value)

    def draw(self, screen, lib):
        r = self.rect
        pygame.draw.rect(screen, (20, 30, 42), (r.x, r.centery - 5, r.w, 10), border_radius=5)
        pygame.draw.rect(screen, (90, 190, 255), (r.x, r.centery - 5, int(r.w * self.value), 10), border_radius=5)
        pygame.draw.circle(screen, (240, 248, 255), (r.x + int(r.w * self.value), r.centery), 11)
        pygame.draw.circle(screen, (60, 120, 170), (r.x + int(r.w * self.value), r.centery), 11, 2)
