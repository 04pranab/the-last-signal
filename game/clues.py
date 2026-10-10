"""Clue definitions: signal fragments, notes, decoy logs and false (Echo) variants."""
from __future__ import annotations

import random
from typing import Dict, List, Tuple

FRAGMENTS = ["freq", "chan", "seq1", "seq2", "seq3"]

TERMINAL_LABELS = {
    "archive": "ARCHIVE TERMINAL", "security": "SECURITY CONSOLE", "medical": "MEDICAL TERMINAL",
    "server_wing": "SERVER TERMINAL", "lab": "LAB TERMINAL", "main_lab": "LAB TERMINAL",
    "storage": "INVENTORY TERMINAL", "maintenance": "SERVICE TERMINAL", "comms": "COMMS TERMINAL",
    "restricted": "COMMAND CONSOLE", "quarters": "PERSONAL TERMINAL", "generator": "SERVICE TERMINAL",
    "hub": "INFO KIOSK",
}


def terminal_label(kind: str) -> str:
    return TERMINAL_LABELS.get(kind, "TERMINAL")


def make_secret(rng: random.Random) -> dict:
    freq = str(rng.randint(100, 999))
    chan = "%02d" % rng.randint(1, 99)
    seq = "".join(str(rng.randint(0, 9)) for _ in range(3))
    return {"answer": {"freq": freq, "chan": chan, "seq": seq}, "objects": {}}


def fragment_text(cid: str, answer: dict, false_value: str = None) -> Tuple[str, List[str]]:
    """Return (title, lines) for a fragment; `false_value` replaces the true value (Echo)."""
    if cid == "freq":
        return "SIGNAL FRAGMENT", ["Frequency:", false_value or answer["freq"]]
    if cid == "chan":
        return "SIGNAL FRAGMENT", ["Channel:", false_value or answer["chan"]]
    n = int(cid[3:])
    val = false_value or answer["seq"][n - 1]
    return "SIGNAL FRAGMENT", [f"Sequence position {n}:", val]


def false_value(cid: str, answer: dict, rng: random.Random) -> str:
    if cid == "freq":
        while True:
            v = str(rng.randint(100, 999))
            if v != answer["freq"]:
                return v
    if cid == "chan":
        while True:
            v = "%02d" % rng.randint(1, 99)
            if v != answer["chan"]:
                return v
    n = int(cid[3:])
    true = answer["seq"][n - 1]
    while True:
        v = str(rng.randint(0, 9))
        if v != true:
            return v


def answer_matches(answer: dict, freq: str, chan: str, seq: str) -> int:
    n = 0
    n += freq == answer["freq"]
    n += chan == answer["chan"]
    n += seq == answer["seq"]
    return n


def make_notes(rng: random.Random, m, secret: dict) -> List[dict]:
    rooms = {}
    for oid, info in secret["objects"].items():
        if info.get("kind") == "clue":
            rooms[info["clue"]] = info["room"]
    gen_room = m.rooms[m.meta["generator_room"]].name
    srv = m.rooms[m.meta["server_room"]].name
    comms = m.rooms[m.meta["comms_room"]].name
    notes = [
        {"title": "SIGNAL NOTE", "lines": ["The final sequence contains", "three numbers."]},
        {"title": "SIGNAL NOTE", "lines": ["Transmission needs a frequency,", "a channel and a sequence."]},
        {"title": "ENGINEERING LOG", "lines": ["Backup generator is housed in:", gen_room + ".", "Restricted doors need power."]},
        {"title": "ENGINEERING LOG", "lines": ["Signal core must be calibrated", "before transmitting.", "Location: " + srv + "."]},
        {"title": "COMMS LOG", "lines": ["Emergency transmitter is in:", comms + "."]},
        {"title": "ARCHIVE INDEX", "lines": ["Frequency record filed in:", rooms.get("freq", "the Archive") + "."]},
        {"title": "SECURITY MEMO", "lines": ["Channel assignment stored in:", rooms.get("chan", "Security") + "."]},
        {"title": "SIGNAL NOTE", "lines": ["Sequence positions 1, 2 and 3", "were split between three rooms."]},
        {"title": "SIGNAL NOTE", "lines": ["Sequence position 1 backup:", rooms.get("seq1", "?") + "."]},
        {"title": "SIGNAL NOTE", "lines": ["Sequence position 3 backup:", rooms.get("seq3", "?") + "."]},
    ]
    rng.shuffle(notes)
    return notes


LOGS = {
    "default": [
        ["Automated log:", "Systems nominal until", "contact was lost."],
        ["Last backup 03:12.", "Echo interference detected", "on all channels."],
        ["Please do not remove", "samples from this area."],
        ["Maintenance ticket #4471", "still open."],
        ["Power fluctuation again.", "Third time this week."],
    ],
    "medical": [["Patient notes sealed.", "Observation ward evacuated."], ["Vitals offline.", "Cause unknown."]],
    "archive": [["Index rebuilt after the", "outage. Some records", "may be corrupt."]],
    "lab": [["Experiment 17 paused.", "Readings do not match", "the model."], ["Sample cooling failed."]],
    "storage": [["Inventory mismatch:", "12 crates unaccounted for."]],
    "security": [["Door access log", "cleared by unknown user."], ["Camera 6 shows static."]],
    "server_wing": [["Core temperature high.", "Fans at maximum."]],
    "quarters": [["Off shift. If anyone finds", "this, the signal never", "came from outside."]],
    "maintenance": [["Valve 3 is stuck.", "Do NOT force it."]],
    "main_lab": [["A-17 anomaly analysis:", "the Echo repeats what it", "hears. Do not trust it."]],
}


def random_log(rng: random.Random, room) -> dict:
    pool = LOGS.get(room.kind, []) + LOGS["default"]
    return {"title": "STATION LOG", "lines": rng.choice(pool)}
