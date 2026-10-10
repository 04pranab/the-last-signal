"""Authoritative game server (single threaded, selectors based).

One instance owns the lobby and, once started, the :class:`GameWorld`.  It is
safe against malformed packets: every frame is schema-validated, bad frames
are counted and the offending connection is dropped after a few strikes;
exceptions in message handlers never propagate out of the server loop.
"""
from __future__ import annotations

import logging
import random
import secrets
import selectors
import socket
import threading
import time
from typing import Dict, List, Optional

from ..config import (CLIENT_TIMEOUT, DISCOVERY_PORT, GAME_TIME_LIMIT, MAX_OUT_BUFFER, MAX_PLAYERS,
                      PENDING_TIMEOUT, PROTOCOL_VERSION, RECONNECT_GRACE, SERVER_TICK, SNAPSHOT_HZ, VERSION)
from ..maps import DEFAULT_MAP, MAP_REGISTRY, generate_map
from ..state import GameWorld
from .discovery import DiscoveryBroadcaster
from .protocol import FrameBuffer, ProtocolError, encode, validate_client_message

log = logging.getLogger("tls.server")

MAX_MSGS_PER_SEC = 400
MAX_STRIKES = 6


class Conn:
    def __init__(self, sock: socket.socket, addr):
        self.sock = sock
        self.addr = addr
        self.fb = FrameBuffer()
        self.out = bytearray()
        self.state = "new"          # new | pending | active | closed
        self.pid = 0
        self.rid = 0
        self.name = ""
        self.last_rx = time.time()
        self.created = time.time()
        self.strikes = 0
        self.win_start = time.time()
        self.win_count = 0
        self.want_write = False


class Slot:
    def __init__(self, pid: int, name: str, token: str):
        self.pid, self.name, self.token = pid, name, token
        self.conn: Optional[Conn] = None
        self.host = False
        self.connected = True
        self.left_at = 0.0


class GameServer:
    def __init__(self, name: str = "Research Station", port: int = 0, max_players: int = MAX_PLAYERS,
                 seed: Optional[int] = None, map_id: str = DEFAULT_MAP, host_key: str = "",
                 auto_accept: bool = False, bind: str = "0.0.0.0", discovery: bool = True,
                 discovery_port: int = DISCOVERY_PORT, time_limit: float = GAME_TIME_LIMIT, echo: bool = True):
        self.name = name[:24] or "Game"
        self.max_players = max(1, min(MAX_PLAYERS, int(max_players)))
        self.seed = int(seed) if seed is not None else random.SystemRandom().randint(1, 2 ** 31 - 1)
        self.map_id = map_id if map_id in MAP_REGISTRY else DEFAULT_MAP
        self.host_key = host_key
        self.auto_accept = auto_accept
        self.bind = bind
        self.use_discovery = discovery
        self.discovery_port = discovery_port
        self.time_limit = time_limit
        self.echo = echo
        self.server_id = secrets.token_hex(6)

        self.sel = selectors.DefaultSelector()
        self.lsock: Optional[socket.socket] = None
        self.port = port
        self.conns: List[Conn] = []
        self.slots: Dict[int, Slot] = {}
        self.pending: Dict[int, Conn] = {}
        self._next_rid = 1
        self.phase = "lobby"       # lobby | playing | ended
        self.world: Optional[GameWorld] = None
        self.map = None
        self.map_error: Optional[str] = None
        self._map_thread: Optional[threading.Thread] = None
        self._thread: Optional[threading.Thread] = None
        self._running = threading.Event()
        self._last_snap = 0.0
        self._last_state = 0.0
        self._last_full = 0.0
        self.discovery: Optional[DiscoveryBroadcaster] = None
        self._empty_since: Optional[float] = None
        self.stats = {"bad_frames": 0, "dropped": 0}

    # ------------------------------------------------------------ lifecycle
    def start(self) -> int:
        self.lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.lsock.bind((self.bind, self.port))
        self.lsock.listen(32)
        self.lsock.setblocking(False)
        self.port = self.lsock.getsockname()[1]
        self.sel.register(self.lsock, selectors.EVENT_READ, data="listen")
        self._start_map_generation()
        self._running.set()
        self._thread = threading.Thread(target=self._run, name="game-server", daemon=True)
        self._thread.start()
        if self.use_discovery:
            self.discovery = DiscoveryBroadcaster(self.discovery_info, self.discovery_port)
            self.discovery.start()
        return self.port

    def stop(self) -> None:
        if not self._running.is_set() and self._thread is None:
            return
        self._running.clear()
        if self.discovery:
            self.discovery.stop()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=3.0)
        self._cleanup()

    def _cleanup(self) -> None:
        for c in list(self.conns):
            try:
                c.sock.close()
            except OSError:
                pass
        self.conns.clear()
        try:
            if self.lsock:
                self.sel.unregister(self.lsock)
                self.lsock.close()
        except (OSError, KeyError, ValueError):
            pass
        self.lsock = None
        try:
            self.sel.close()
        except Exception:
            pass

    def discovery_info(self) -> dict:
        return {"server_id": self.server_id, "name": self.name, "port": self.port,
                "players": len([s for s in self.slots.values() if s.connected]), "max": self.max_players,
                "map": MAP_REGISTRY[self.map_id].map_name, "state": self.phase}

    def _start_map_generation(self) -> None:
        self.map, self.map_error = None, None

        def work(seed=self.seed):
            try:
                self.map = generate_map(seed, self.map_id)
            except Exception as e:  # pragma: no cover
                self.map_error = str(e)
                log.exception("map generation failed")

        self._map_thread = threading.Thread(target=work, name="map-gen", daemon=True)
        self._map_thread.start()

    # ------------------------------------------------------------- main loop
    def _run(self) -> None:
        tick = 1.0 / SERVER_TICK
        next_tick = time.time() + tick
        last = time.time()
        while self._running.is_set():
            now = time.time()
            timeout = max(0.0, min(tick, next_tick - now))
            try:
                events = self.sel.select(timeout)
            except (OSError, ValueError):
                break
            for key, mask in events:
                try:
                    if key.data == "listen":
                        self._accept()
                    else:
                        conn: Conn = key.data
                        if mask & selectors.EVENT_READ:
                            self._read(conn)
                        if mask & selectors.EVENT_WRITE and conn.state != "closed":
                            self._flush(conn)
                except Exception:
                    log.exception("connection handler error")
            now = time.time()
            if now >= next_tick:
                dt = min(now - last, 0.1)
                last = now
                next_tick = now + tick
                try:
                    self._tick(dt, now)
                except Exception:
                    log.exception("tick error")
        self._cleanup()

    def _accept(self) -> None:
        while True:
            try:
                s, addr = self.lsock.accept()
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                return
            if len(self.conns) >= 64:
                s.close()
                continue
            s.setblocking(False)
            try:
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
            c = Conn(s, addr)
            self.conns.append(c)
            self.sel.register(s, selectors.EVENT_READ, data=c)

    # --------------------------------------------------------------- io
    def _read(self, c: Conn) -> None:
        try:
            data = c.sock.recv(65536)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            self._drop(c, "socket error")
            return
        if not data:
            self._drop(c, "closed")
            return
        c.last_rx = time.time()
        try:
            msgs = c.fb.feed(data)
        except ProtocolError:
            self.stats["bad_frames"] += 1
            self._drop(c, "protocol error")
            return
        if c.fb.errors:
            self.stats["bad_frames"] += c.fb.errors
            c.strikes += c.fb.errors
            c.fb.errors = 0
            if c.strikes >= MAX_STRIKES:
                self._drop(c, "too many malformed frames")
                return
        now = time.time()
        for raw in msgs:
            if c.state == "closed":
                return
            if now - c.win_start > 1.0:
                c.win_start, c.win_count = now, 0
            c.win_count += 1
            if c.win_count > MAX_MSGS_PER_SEC:
                self._drop(c, "flooding")
                return
            msg = validate_client_message(raw)
            if msg is None:
                c.strikes += 1
                self.stats["bad_frames"] += 1
                if c.strikes >= MAX_STRIKES:
                    self._drop(c, "invalid messages")
                    return
                continue
            try:
                self._handle(c, msg)
            except Exception:
                log.exception("message handler error")
                c.strikes += 1

    def send(self, c: Conn, msg: dict) -> None:
        self.send_raw(c, encode(msg))

    def send_raw(self, c: Conn, data: bytes) -> None:
        if c.state == "closed":
            return
        c.out.extend(data)
        if len(c.out) > MAX_OUT_BUFFER:
            self.stats["dropped"] += 1
            self._drop(c, "send buffer overflow")
            return
        self._flush(c)

    def _flush(self, c: Conn) -> None:
        if c.state == "closed":
            return
        while c.out:
            try:
                n = c.sock.send(c.out)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                self._drop(c, "send error")
                return
            if n <= 0:
                break
            del c.out[:n]
        want = bool(c.out)
        if want != c.want_write:
            c.want_write = want
            try:
                self.sel.modify(c.sock, selectors.EVENT_READ | (selectors.EVENT_WRITE if want else 0), data=c)
            except (KeyError, ValueError, OSError):
                pass

    def _drop(self, c: Conn, reason: str = "") -> None:
        if c.state == "closed":
            return
        prev = c.state
        c.state = "closed"
        try:
            self.sel.unregister(c.sock)
        except (KeyError, ValueError):
            pass
        try:
            c.sock.close()
        except OSError:
            pass
        if c in self.conns:
            self.conns.remove(c)
        if c.rid in self.pending:
            del self.pending[c.rid]
            host = self._host_conn()
            if host:
                self.send(host, {"t": "join_cancel", "rid": c.rid})
        if prev == "active" and c.pid in self.slots:
            self._player_disconnected(self.slots[c.pid], c, reason)

    # ----------------------------------------------------------- handlers
    def _host_conn(self) -> Optional[Conn]:
        for s in self.slots.values():
            if s.host and s.conn and s.conn.state == "active":
                return s.conn
        return None

    def _handle(self, c: Conn, m: dict) -> None:
        t = m["t"]
        if c.state == "new":
            if t == "hello":
                self._hello(c, m)
            else:
                c.strikes += 1
            return
        if c.state == "pending":
            if t == "leave":
                self._drop(c, "left")
            return
        if c.state != "active":
            return
        slot = self.slots.get(c.pid)
        if slot is None:
            return
        if t == "ping":
            self.send(c, {"t": "pong", "n": m["n"]})
        elif t == "leave":
            self._drop(c, "left")
        elif t == "join_decision":
            if slot.host:
                self._decide(m["rid"], m["accept"])
        elif t == "chat":
            now = time.time()
            if now - getattr(slot, "last_chat", 0.0) >= 0.6:
                slot.last_chat = now
                self._broadcast({"t": "chat", "pid": slot.pid, "name": slot.name, "text": m["text"]})
        elif t == "start":
            if slot.host and self.phase == "lobby":
                self._start_game()
        elif t == "return_lobby":
            if slot.host and self.phase == "ended":
                self._back_to_lobby()
        elif self.phase == "playing" and self.world:
            if t == "input":
                self.world.set_input(c.pid, m["mx"], m["my"], m["aim"], m["fire"])
            elif t == "reload":
                self.world.reload(c.pid)
            elif t == "weapon":
                self.world.switch_weapon(c.pid, m["name"])
            elif t == "interact":
                self.world.interact(c.pid, m["oid"])
            elif t == "transmit":
                self.world.transmit(c.pid, m["freq"], m["chan"], m["seq"])

    def _reject(self, c: Conn, reason: str) -> None:
        self.send(c, {"t": "rejected", "reason": reason})
        self._flush(c)
        self._drop(c, "rejected")

    def _hello(self, c: Conn, m: dict) -> None:
        if m["proto"] != PROTOCOL_VERSION:
            self._reject(c, "version")
            return
        c.name = m["name"]
        # reconnect with a valid token
        if m["token"]:
            for slot in self.slots.values():
                if slot.token == m["token"] and not slot.connected:
                    self._attach(slot, c)
                    return
        is_host_key = bool(self.host_key) and m["host_key"] == self.host_key
        if is_host_key and not any(s.host for s in self.slots.values()):
            self._accept_player(c, host=True)
            return
        if self.phase != "lobby":
            self._reject(c, "started")
            return
        if len([s for s in self.slots.values() if s.connected]) + len(self.pending) >= self.max_players:
            self._reject(c, "full")
            return
        if self.auto_accept:
            self._accept_player(c, host=not self.slots)
            return
        host = self._host_conn()
        if host is None:
            self._reject(c, "no_host")
            return
        c.state = "pending"
        c.rid = self._next_rid
        self._next_rid += 1
        self.pending[c.rid] = c
        self.send(c, {"t": "pending"})
        self.send(host, {"t": "join_request", "rid": c.rid, "name": c.name})

    def _decide(self, rid: int, accept: bool) -> None:
        c = self.pending.pop(rid, None)
        if c is None or c.state != "pending":
            return
        if not accept:
            self._reject(c, "rejected")
            return
        if self.phase != "lobby":
            self._reject(c, "started")
            return
        if len([s for s in self.slots.values() if s.connected]) >= self.max_players:
            self._reject(c, "full")
            return
        c.rid = 0
        self._accept_player(c, host=False)

    def _accept_player(self, c: Conn, host: bool) -> None:
        pid = next((i for i in range(1, MAX_PLAYERS + 1) if i not in self.slots), 0)
        if pid == 0:
            self._reject(c, "full")
            return
        slot = Slot(pid, self._unique_name(c.name), secrets.token_hex(12))
        slot.host = host
        self.slots[pid] = slot
        if self.world and self.phase == "playing":
            self.world.add_player(pid, slot.name, slot.token)
        self._attach(slot, c, fresh=True)

    def _unique_name(self, name: str) -> str:
        names = {s.name for s in self.slots.values()}
        if name not in names:
            return name
        for i in range(2, 100):
            cand = f"{name[:12]}{i}"
            if cand not in names:
                return cand
        return name

    def _attach(self, slot: Slot, c: Conn, fresh: bool = False) -> None:
        slot.conn, slot.connected = c, True
        c.pid, c.state = slot.pid, "active"
        self.send(c, {"t": "welcome", "pid": slot.pid, "token": slot.token, "host": slot.host,
                      "name": slot.name, "game": self.name, "max": self.max_players, "seed": self.seed,
                      "map": MAP_REGISTRY[self.map_id].map_name, "phase": self.phase})
        if self.world:
            self.world.set_connected(slot.pid, True)
            self._send_start(c, slot)
            if not fresh:
                self._broadcast({"t": "toast", "text": f"{slot.name} reconnected.", "kind": "info", "snd": "player_joined"}, exclude=c)
        else:
            self._broadcast({"t": "toast", "text": f"{slot.name} joined.", "kind": "info", "snd": "player_joined"}, exclude=c)
        self._broadcast_lobby()

    def _player_disconnected(self, slot: Slot, c: Conn, reason: str) -> None:
        if slot.conn is not c:
            return
        slot.conn = None
        slot.connected = False
        slot.left_at = time.time()
        if self.phase == "lobby":
            del self.slots[slot.pid]
            if slot.host and self.host_key:
                self._broadcast({"t": "closed", "reason": "host_left"})
                self._running.clear()
                return
            self._broadcast({"t": "toast", "text": f"{slot.name} left.", "kind": "info", "snd": "player_left"})
        else:
            if self.world:
                self.world.set_connected(slot.pid, False)
            if slot.host and self.host_key:
                self._broadcast({"t": "closed", "reason": "host_left"})
                self._running.clear()
                return
            self._broadcast({"t": "toast", "text": f"{slot.name} disconnected.", "kind": "error", "snd": "player_left"})
        self._broadcast_lobby()

    # ------------------------------------------------------------ lobby/game
    def lobby_message(self) -> dict:
        return {"t": "lobby", "name": self.name, "max": self.max_players, "seed": self.seed, "state": self.phase,
                "map": MAP_REGISTRY[self.map_id].map_name,
                "players": [{"pid": s.pid, "name": s.name, "host": s.host, "connected": s.connected}
                            for s in sorted(self.slots.values(), key=lambda s: s.pid)]}

    def _broadcast_lobby(self) -> None:
        self._broadcast(self.lobby_message())

    def _broadcast(self, msg: dict, exclude: Optional[Conn] = None) -> None:
        data = encode(msg)
        for s in list(self.slots.values()):
            if s.conn and s.conn.state == "active" and s.conn is not exclude:
                self.send_raw(s.conn, data)

    def _start_game(self) -> None:
        if self._map_thread:
            self._map_thread.join(timeout=30)
        if self.map is None:
            host = self._host_conn()
            if host:
                self.send(host, {"t": "toast", "text": "Map generation failed: " + str(self.map_error), "kind": "error"})
            return
        connected = [s for s in self.slots.values() if s.connected]
        if not connected:
            return
        self.world = GameWorld(self.map, self.time_limit, echo=self.echo)
        for s in sorted(self.slots.values(), key=lambda s: s.pid):
            self.world.add_player(s.pid, s.name, s.token)
            if not s.connected:
                self.world.set_connected(s.pid, False)
        self.phase = "playing"
        self._payload_cache = None
        for s in connected:
            self._send_start(s.conn, s)
        self._broadcast_lobby()

    def _send_start(self, c: Conn, slot: Slot) -> None:
        if not self.world:
            return
        if getattr(self, "_payload_cache", None) is None:
            self._payload_cache = self.map.to_payload()
        self.send(c, {"t": "start", "pid": slot.pid, "map": self._payload_cache, "time_limit": self.time_limit,
                      "players": [{"pid": p.pid, "name": p.name} for p in self.world.players.values()]})
        self.send(c, self.world.state_message())
        self.send(c, self.world.snapshot())
        p = self.world.players.get(slot.pid)
        if p:
            self.send(c, {"t": "notes", "notes": p.notes})
            self.send(c, self.world._inv_msg(p))

    def _back_to_lobby(self) -> None:
        self.world = None
        self.phase = "lobby"
        self.seed = random.SystemRandom().randint(1, 2 ** 31 - 1)
        for pid in [pid for pid, s in self.slots.items() if not s.connected]:
            del self.slots[pid]
        self._payload_cache = None
        self._start_map_generation()
        self._broadcast({"t": "lobby_reset"})
        self._broadcast_lobby()

    # ------------------------------------------------------------------ tick
    def _tick(self, dt: float, now: float) -> None:
        # housekeeping: timeouts
        for c in list(self.conns):
            if c.state == "active" and now - c.last_rx > CLIENT_TIMEOUT:
                self._drop(c, "timeout")
            elif c.state == "pending" and now - c.created > PENDING_TIMEOUT:
                self._reject(c, "timeout")
            elif c.state == "new" and now - c.created > 10:
                self._drop(c, "no hello")
        if self.phase == "playing" and self.world:
            w = self.world
            w.tick(dt)
            for target, msg in w.drain():
                if target is None:
                    self._broadcast(msg)
                else:
                    s = self.slots.get(target)
                    if s and s.conn and s.conn.state == "active":
                        self.send(s.conn, msg)
            if now - self._last_snap >= 1.0 / SNAPSHOT_HZ:
                self._last_snap = now
                self._broadcast(w.snapshot())
            if (w.dirty and now - self._last_state >= 0.1) or now - self._last_full >= 2.0:
                w.dirty = False
                self._last_state = self._last_full = now
                self._broadcast(w.state_message())
            if w.phase != "playing":
                self.phase = "ended"
                self._broadcast_lobby()
            # everybody gone for too long -> end the game
            if not any(s.connected for s in self.slots.values()):
                if self._empty_since is None:
                    self._empty_since = now
                elif now - self._empty_since > RECONNECT_GRACE:
                    w.finish("failure", "ALL PLAYERS LEFT")
            else:
                self._empty_since = None
