"""Global configuration constants for THE LAST SIGNAL."""
import os
from pathlib import Path

GAME_NAME = "THE LAST SIGNAL"
VERSION = "1.1.0"
PROTOCOL_VERSION = 1
DISCOVERY_MAGIC = "THELASTSIGNAL"

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT_DIR / "assets"
COMMON_DIR = ASSET_DIR / "common"
MAP_ASSET_DIR = ASSET_DIR / "maps"


def settings_dir() -> Path:
    """Per-user settings directory (works on Windows and Linux)."""
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "the_last_signal"


# --- display ---------------------------------------------------------
SCREEN_W = 1280
SCREEN_H = 720
FPS = 60
TILE = 64

# --- networking ------------------------------------------------------
DISCOVERY_PORT = 47200
DEFAULT_GAME_PORT = 47201
DISCOVERY_INTERVAL = 1.0
DISCOVERY_TTL = 4.0
MAX_PLAYERS = 15
MAX_CLIENT_FRAME = 64 * 1024          # bytes a client may send in one frame
MAX_SERVER_FRAME = 4 * 1024 * 1024    # bytes a client accepts from a server
SERVER_TICK = 30                      # simulation Hz
SNAPSHOT_HZ = 15                      # player snapshot Hz
CLIENT_TIMEOUT = 12.0                 # seconds of silence before a client is dropped
PENDING_TIMEOUT = 60.0                # host decision timeout for join requests
RECONNECT_GRACE = 90.0                # seconds a disconnected player keeps their slot
MAX_OUT_BUFFER = 2 * 1024 * 1024      # drop clients that can't keep up
MAX_NAME_LEN = 16

# --- gameplay --------------------------------------------------------
PLAYER_SPEED = 230.0      # pixels / second
PLAYER_HALF = 14          # half extent of the player collision box (px)
INTERACT_RANGE = 1.7 * TILE
GAME_TIME_LIMIT = 40 * 60  # seconds
TRANSMIT_LOCKOUT = 4.0
DOOR_OPEN_RADIUS = 1.9 * TILE
DOOR_CLOSE_DELAY = 0.8

# --- map -------------------------------------------------------------
MAP_W = 200
MAP_H = 130
MAP_MAX_ATTEMPTS = 25

PLAYER_COLORS = [
    (255, 99, 99), (255, 170, 60), (250, 230, 80), (150, 230, 80), (70, 220, 120),
    (60, 220, 210), (80, 170, 255), (110, 120, 255), (180, 110, 255), (240, 110, 240),
    (255, 120, 170), (200, 200, 200), (170, 120, 80), (120, 255, 200), (255, 255, 255),
]
