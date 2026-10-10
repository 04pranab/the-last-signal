"""Sound manager: loads the supplied Kenney sounds, throttles repeats, survives missing audio devices."""
from __future__ import annotations

import array
import math
import random
import time
from typing import Dict

import pygame

from .config import COMMON_DIR


class Audio:
    def __init__(self):
        self.enabled = False
        self.sounds: Dict[str, "pygame.mixer.Sound"] = {}
        self.last: Dict[str, float] = {}
        self.volume = 0.6
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self.enabled = True
        except pygame.error:
            self.enabled = False
            return
        for f in (COMMON_DIR / "audio").glob("*.ogg"):
            try:
                self.sounds[f.stem] = pygame.mixer.Sound(str(f))
            except pygame.error:
                pass
        try:
            self._synth()
        except Exception:
            pass

    # ---- procedurally synthesised horror sounds (no external files needed)
    def _make(self, samples) -> "pygame.mixer.Sound":
        freq, fmt, ch = pygame.mixer.get_init()
        data = array.array("h")
        for v in samples:
            v = max(-1.0, min(1.0, v))
            iv = int(v * 30000)
            for _ in range(ch):
                data.append(iv)
        return pygame.mixer.Sound(buffer=data.tobytes())

    def _synth(self) -> None:
        sr = pygame.mixer.get_init()[0]
        rng = random.Random(7)

        def thump(t, f0, decay):
            return math.sin(2 * math.pi * f0 * t * (1 - 0.25 * t)) * math.exp(-t * decay)

        n = int(sr * 0.9)
        beat = []
        for i in range(n):
            t = i / sr
            v = thump(t, 58, 14) * 0.9
            if t > 0.22:
                v += thump(t - 0.22, 50, 16) * 0.7
            beat.append(v)
        self.sounds["heartbeat"] = self._make(beat)
        # whisper: band-limited noise with slow tremolo
        n = int(sr * 1.6)
        lp = 0.0
        wh = []
        for i in range(n):
            t = i / sr
            lp += (rng.uniform(-1, 1) - lp) * 0.25
            env = math.sin(math.pi * min(1.0, t / 1.6)) ** 2 * (0.6 + 0.4 * math.sin(t * 38))
            wh.append(lp * env * 0.55)
        self.sounds["whisper"] = self._make(wh)
        # jump scare stinger: noise burst + falling screech + sub boom
        n = int(sr * 1.1)
        st = []
        lp = 0.0
        for i in range(n):
            t = i / sr
            lp += (rng.uniform(-1, 1) - lp) * 0.6
            screech = math.sin(2 * math.pi * (1800 - 1500 * t) * t) * math.exp(-t * 3.2)
            boom = math.sin(2 * math.pi * 42 * t) * math.exp(-t * 4)
            st.append((lp * 0.5 * math.exp(-t * 5) + screech * 0.5 + boom * 0.8) * min(1.0, t * 400))
        self.sounds["stinger"] = self._make(st)
        # distant groan
        n = int(sr * 1.4)
        gr = [math.sin(2 * math.pi * (90 + 25 * math.sin(i / sr * 5)) * i / sr) * math.sin(math.pi * i / n) ** 2 * 0.5 for i in range(n)]
        self.sounds["groan"] = self._make(gr)

    def play(self, name: str, volume: float = 1.0, min_gap: float = 0.12) -> None:
        if not self.enabled or name not in self.sounds:
            return
        now = time.time()
        if now - self.last.get(name, 0) < min_gap:
            return
        self.last[name] = now
        s = self.sounds[name]
        s.set_volume(max(0.0, min(1.0, volume * self.volume)))
        s.play()
