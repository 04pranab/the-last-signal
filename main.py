#!/usr/bin/env python3
"""THE LAST SIGNAL - launcher."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    from game.game import App
    App().run()


if __name__ == "__main__":
    main()
