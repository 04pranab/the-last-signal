"""LAN game discovery over UDP broadcast."""
from __future__ import annotations

import json
import socket
import threading
import time
from typing import Callable, Dict, List, Optional

from ..config import DISCOVERY_INTERVAL, DISCOVERY_MAGIC, DISCOVERY_PORT, DISCOVERY_TTL, VERSION


def local_ipv4_addresses() -> List[str]:
    """Best effort list of this machine's IPv4 addresses (no packets are actually sent)."""
    addrs = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        addrs.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addrs.add(info[4][0])
    except OSError:
        pass
    return [a for a in addrs if not a.startswith("127.") and a != "0.0.0.0"]


def broadcast_targets() -> List[str]:
    targets = ["255.255.255.255", "127.0.0.1"]
    for a in local_ipv4_addresses():
        parts = a.split(".")
        if len(parts) == 4:
            targets.append(".".join(parts[:3] + ["255"]))   # assume /24 directed broadcast
    seen, out = set(), []
    for t in targets:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


class DiscoveryBroadcaster:
    """Host side: periodically announces the game on the LAN."""

    def __init__(self, info_fn: Callable[[], dict], port: int = DISCOVERY_PORT, interval: float = DISCOVERY_INTERVAL):
        self.info_fn, self.port, self.interval = info_fn, port, interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="discovery-tx", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except OSError:
            pass
        targets = broadcast_targets()
        last_refresh = time.time()
        while not self._stop.is_set():
            try:
                info = dict(self.info_fn())
                info.update({"magic": DISCOVERY_MAGIC, "ver": VERSION})
                data = json.dumps(info, separators=(",", ":")).encode("utf-8")
                for t in targets:
                    try:
                        sock.sendto(data, (t, self.port))
                    except OSError:
                        pass
            except Exception:
                pass
            if time.time() - last_refresh > 30:
                targets = broadcast_targets()
                last_refresh = time.time()
            self._stop.wait(self.interval)
        sock.close()


class DiscoveryListener:
    """Client side: collects announcements into a table of live games."""

    def __init__(self, port: int = DISCOVERY_PORT):
        self.port = port
        self.games: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.error: Optional[str] = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="discovery-rx", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def _open(self) -> Optional[socket.socket]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        try:
            sock.bind(("", self.port))
        except OSError as e:
            self.error = f"cannot listen on UDP {self.port}: {e}"
            sock.close()
            return None
        sock.settimeout(0.3)
        return sock

    def _run(self) -> None:
        sock = self._open()
        if sock is None:
            return
        while not self._stop.is_set():
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                info = json.loads(data.decode("utf-8"))
                if not isinstance(info, dict) or info.get("magic") != DISCOVERY_MAGIC:
                    continue
                sid = str(info["server_id"])[:64]
                entry = {
                    "server_id": sid, "name": str(info.get("name", "?"))[:32], "host": addr[0],
                    "port": int(info["port"]), "players": int(info.get("players", 0)),
                    "max": int(info.get("max", 15)), "map": str(info.get("map", "?"))[:32],
                    "state": str(info.get("state", "lobby"))[:12], "ver": str(info.get("ver", ""))[:16],
                    "seen": time.time(),
                }
                if not (0 < entry["port"] < 65536):
                    continue
            except (ValueError, KeyError, TypeError, UnicodeDecodeError):
                continue
            with self._lock:
                self.games[sid] = entry
        sock.close()

    def get_games(self) -> List[dict]:
        now = time.time()
        with self._lock:
            for k in [k for k, g in self.games.items() if now - g["seen"] > DISCOVERY_TTL]:
                del self.games[k]
            return sorted(self.games.values(), key=lambda g: g["name"].lower())
