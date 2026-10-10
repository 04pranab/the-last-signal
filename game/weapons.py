"""Weapon definitions (server authoritative, client uses them for HUD / visuals)."""
from __future__ import annotations

from typing import Dict, List

from .config import TILE

# damage per pellet, seconds between shots, clip size, reload seconds, spread (radians),
# pellets per shot, range (px), zombies a bullet can pierce, spare ammo when first picked up (None = infinite)
WEAPONS: Dict[str, dict] = {
    "pistol": {"label": "PISTOL", "dmg": 34, "cd": 0.28, "clip": 12, "reload": 1.2, "spread": 0.0, "pellets": 1,
               "range": 9.5 * TILE, "pierce": 1, "reserve": None, "color": (255, 220, 120), "scale": 2.0, "sprite": "weapon_gun"},
    "smg": {"label": "SMG", "dmg": 15, "cd": 0.09, "clip": 30, "reload": 1.6, "spread": 0.07, "pellets": 1,
            "range": 8.0 * TILE, "pierce": 1, "reserve": 120, "color": (255, 190, 90), "scale": 1.9, "sprite": "weapon_silencer"},
    "shotgun": {"label": "SHOTGUN", "dmg": 14, "cd": 0.85, "clip": 6, "reload": 2.0, "spread": 0.24, "pellets": 7,
                "range": 5.5 * TILE, "pierce": 1, "reserve": 30, "color": (255, 150, 80), "scale": 2.2, "sprite": "weapon_machine"},
    "rifle": {"label": "RIFLE", "dmg": 58, "cd": 0.5, "clip": 8, "reload": 1.8, "spread": 0.01, "pellets": 1,
              "range": 15.0 * TILE, "pierce": 3, "reserve": 40, "color": (190, 230, 255), "scale": 2.3, "sprite": "weapon_machine"},
    "plasma": {"label": "PLASMA", "dmg": 48, "cd": 0.22, "clip": 20, "reload": 1.8, "spread": 0.02, "pellets": 1,
               "range": 11.0 * TILE, "pierce": 4, "reserve": 80, "color": (120, 255, 255), "scale": 2.0, "sprite": "weapon_gun"},
}
ORDER: List[str] = ["pistol", "smg", "shotgun", "rifle", "plasma"]
INDEX = {n: i for i, n in enumerate(ORDER)}
CRATE_WEAPONS = ["smg", "shotgun", "rifle", "plasma"]
