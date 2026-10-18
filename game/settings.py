"""Persistent user settings: sound levels, key bindings, fullscreen, player name."""
from __future__ import annotations

import json
from typing import Dict

import pygame

from .config import MAX_NAME_LEN, settings_dir

# action id -> (label, default key)
ACTIONS = [
    ("up", "Move up", pygame.K_w), ("down", "Move down", pygame.K_s), ("left", "Move left", pygame.K_a),
    ("right", "Move right", pygame.K_d), ("fire", "Shoot (also left mouse)", pygame.K_SPACE),
    ("reload", "Reload", pygame.K_r), ("interact", "Interact", pygame.K_e), ("weapon_next", "Next weapon", pygame.K_q),
    ("w1", "Weapon 1", pygame.K_1), ("w2", "Weapon 2", pygame.K_2), ("w3", "Weapon 3", pygame.K_3),
    ("w4", "Weapon 4", pygame.K_4), ("w5", "Weapon 5", pygame.K_5), ("chat", "Chat", pygame.K_t),
    ("notes", "Notebook", pygame.K_TAB), ("map", "Big map", pygame.K_m), ("fullscreen", "Fullscreen", pygame.K_F11),
]
DEFAULT_KEYS: Dict[str, int] = {a: k for a, _l, k in ACTIONS}
LABELS: Dict[str, str] = {a: l for a, l, _k in ACTIONS}

# sound name -> category
CATEGORY = {}
for _n in ("click", "hover", "back", "join_request", "player_joined", "player_left", "error", "success", "key", "empty"):
    CATEGORY[_n] = "ui"
for _n in ("shot", "zombie_hit", "zombie_die", "hurt", "reload", "surge"):
    CATEGORY[_n] = "effects"
for _n in ("door_open", "door_close", "terminal", "generator", "transmitter", "victory", "victory2", "failure"):
    CATEGORY[_n] = "world"
for _n in ("echo", "echo_glitch", "heartbeat", "whisper", "stinger", "groan"):
    CATEGORY[_n] = "ambient"


class Settings:
    def __init__(self):
        self.name = "Player"
        self.master = 0.5
        self.vol = {"ui": 0.6, "effects": 0.7, "world": 0.6, "ambient": 0.3}
        self.mute = False
        self.ambient_on = True        # heartbeat / whispers / groans / stingers
        self.fullscreen = True
        self.keys: Dict[str, int] = dict(DEFAULT_KEYS)
        self.load()

    @property
    def path(self):
        return settings_dir() / "settings.json"

    def load(self) -> None:
        try:
            d = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        if not isinstance(d, dict):
            return
        self.name = str(d.get("name", self.name))[:MAX_NAME_LEN] or "Player"
        self.master = _clamp(d.get("master", self.master))
        for k in self.vol:
            self.vol[k] = _clamp(d.get("vol", {}).get(k, self.vol[k])) if isinstance(d.get("vol"), dict) else self.vol[k]
        self.mute = bool(d.get("mute", self.mute))
        self.ambient_on = bool(d.get("ambient_on", self.ambient_on))
        self.fullscreen = bool(d.get("fullscreen", self.fullscreen))
        keys = d.get("keys")
        if isinstance(keys, dict):
            for a in DEFAULT_KEYS:
                v = keys.get(a)
                if isinstance(v, int) and not isinstance(v, bool) and 0 < v < 1 << 31:
                    self.keys[a] = v

    def save(self) -> None:
        try:
            d = settings_dir()
            d.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"name": self.name, "master": self.master, "vol": self.vol, "mute": self.mute,
                                             "ambient_on": self.ambient_on, "fullscreen": self.fullscreen, "keys": self.keys}))
        except OSError:
            pass

    def bind(self, action: str, key: int) -> None:
        """Assign a key; if another action had it the two actions swap keys (no duplicate bindings)."""
        old = self.keys[action]
        for a, k in self.keys.items():
            if a != action and k == key:
                self.keys[a] = old
        self.keys[action] = key

    def reset_keys(self) -> None:
        self.keys = dict(DEFAULT_KEYS)

    def key_name(self, action: str) -> str:
        return pygame.key.name(self.keys[action]).upper() or "?"


def _clamp(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.5
