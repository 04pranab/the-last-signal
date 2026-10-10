"""Stable top-down camera centred on the local player."""
from __future__ import annotations


class Camera:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.x = 0.0
        self.y = 0.0

    def resize(self, w: int, h: int) -> None:
        self.w, self.h = w, h

    def follow(self, tx: float, ty: float, snap: bool = False) -> None:
        # no smoothing: keeps controls crisp; rounding avoids sub-pixel shimmer
        self.x = round(tx - self.w / 2)
        self.y = round(ty - self.h / 2)

    def world_to_screen(self, wx: float, wy: float):
        return wx - self.x, wy - self.y

    def view_rect(self):
        return self.x, self.y, self.w, self.h
