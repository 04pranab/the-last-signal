"""Screen space effects (Echo interference glitch, vignette)."""
from __future__ import annotations

import random

import pygame


def draw_interference(screen: pygame.Surface, t: float, strength: float = 1.0) -> None:
    w, h = screen.get_size()
    rng = random.Random(int(t * 12))
    for _ in range(int(6 * strength)):
        y = rng.randint(0, h - 4)
        bh = rng.randint(2, 10)
        s = pygame.Surface((w, bh), pygame.SRCALPHA)
        s.fill((120, 220, 255, rng.randint(10, 38)))
        screen.blit(s, (rng.randint(-6, 6), y))


def draw_vignette(screen: pygame.Surface, cache: dict) -> None:
    size = screen.get_size()
    v = cache.get(size)
    if v is None:
        v = pygame.Surface(size, pygame.SRCALPHA)
        w, h = size
        for i in range(24):
            a = int(110 * (1 - i / 24) ** 2)
            pygame.draw.rect(v, (0, 0, 0, a), (i * 3, i * 3, w - i * 6, h - i * 6), 3)
        cache[size] = v
    screen.blit(v, (0, 0))
