#!/usr/bin/env python3
"""Headless debug client / bot (no window).  Connects, joins and wanders randomly.

    python client.py --connect 192.168.1.20:47201 --name Bot1 --seconds 30
"""
import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from game.config import DEFAULT_GAME_PORT
from game.networking.client import NetClient


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--connect", required=True, help="host[:port]")
    ap.add_argument("--name", default="Bot")
    ap.add_argument("--seconds", type=float, default=30)
    a = ap.parse_args()
    host, _, port = a.connect.partition(":")
    c = NetClient()
    c.connect(host, int(port or DEFAULT_GAME_PORT), a.name)
    end = time.time() + a.seconds
    mx = my = 0
    nxt = 0
    while time.time() < end:
        for m in c.poll():
            if m["t"] in ("welcome", "pending", "rejected", "start", "end", "net_error", "closed"):
                print(m["t"], {k: v for k, v in m.items() if k not in ("map", "t")})
        if time.time() > nxt:
            nxt = time.time() + 1.0
            mx, my = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1), (0, 0)])
            c.send({"t": "input", "mx": mx, "my": my})
        c.keepalive()
        time.sleep(0.03)
    c.send({"t": "leave"})
    c.close()


if __name__ == "__main__":
    main()
