"""Objective chain for Map 1 (derived from authoritative world state)."""
from __future__ import annotations

from typing import Dict, List

from .clues import FRAGMENTS

STAGES = ["power", "fragments", "core", "transmit"]


def objective_status(power: bool, found: int, core_online: bool, victory: bool, boss: str = "off") -> Dict:
    need = len(FRAGMENTS)
    tasks: List[Dict] = [
        {"id": "power", "label": "Restore power", "done": power},
        {"id": "fragments", "label": f"Signal fragments ({found}/{need})", "done": found >= need},
        {"id": "core", "label": "Calibrate signal core", "done": core_online},
        *([{"id": "boss", "label": "Destroy the Echo Warden", "done": boss == "dead"}] if boss != "off" else []),
        {"id": "transmit", "label": "Transmit distress signal", "done": victory},
    ]
    if victory:
        text = "Distress signal transmitted."
    elif not power:
        text = "Explore the station. Restore power at the backup generator."
    elif found < need:
        text = f"Find signal fragments in terminals across the station ({found}/{need})."
    elif not core_online:
        text = "Calibrate the signal core in the Server Wing."
    elif boss in ("active", "sleeping") and boss != "off":
        text = "The Echo Warden guards Central Communications. Find weapons. Destroy it."
    else:
        text = "Reach the Emergency Transmitter and enter the signal."
    # fragments and core can be done in any order once power is on
    if power and not core_online and found < need:
        text = f"Find signal fragments ({found}/{need}) and calibrate the signal core."
    return {"text": text, "tasks": tasks}
