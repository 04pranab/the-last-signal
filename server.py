#!/usr/bin/env python3
"""Dedicated (headless) server.  Normal players just use "Create Game" in the game itself.

    python server.py --name "My Game" --port 47201 --auto-accept
"""
import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from game.config import DEFAULT_GAME_PORT, MAX_PLAYERS
from game.networking.server import GameServer


def main():
    ap = argparse.ArgumentParser(description="THE LAST SIGNAL dedicated server")
    ap.add_argument("--name", default="Dedicated Station")
    ap.add_argument("--port", type=int, default=DEFAULT_GAME_PORT)
    ap.add_argument("--players", type=int, default=MAX_PLAYERS)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--auto-accept", action="store_true", help="accept every join request (the first player becomes host)")
    ap.add_argument("--no-discovery", action="store_true")
    ap.add_argument("--minutes", type=float, default=40)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    srv = GameServer(a.name, a.port, a.players, a.seed, auto_accept=a.auto_accept, discovery=not a.no_discovery,
                     time_limit=a.minutes * 60)
    port = srv.start()
    print(f"Server '{a.name}' listening on TCP {port}, seed {srv.seed}. Ctrl+C to stop.")
    try:
        while srv._running.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    srv.stop()


if __name__ == "__main__":
    main()
