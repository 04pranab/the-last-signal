"""Network client: background reader thread + thread-safe send; messages are polled by the game loop."""
from __future__ import annotations

import queue
import socket
import threading
import time
from typing import List, Optional

from ..config import PROTOCOL_VERSION, VERSION
from .protocol import FrameBuffer, ProtocolError, encode, server_frame_buffer


class NetClient:
    def __init__(self):
        self.sock: Optional[socket.socket] = None
        self.q: "queue.Queue[dict]" = queue.Queue()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self.connected = False
        self.error = ""
        self.last_rx = 0.0
        self.latency_ms = 0
        self._ping_sent = {}
        self._last_ping = 0.0

    def connect(self, host: str, port: int, name: str, token: str = "", host_key: str = "") -> None:
        """Start connecting in the background; results arrive via poll() (welcome/rejected/net_error)."""
        self.close()
        self.error = ""
        self._thread = threading.Thread(target=self._run, args=(host, port, name, token, host_key), daemon=True)
        self._thread.start()

    def _run(self, host, port, name, token, host_key):
        try:
            s = socket.create_connection((host, port), timeout=5.0)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.settimeout(0.5)
        except OSError as e:
            self.q.put({"t": "net_error", "reason": f"connect failed: {e}"})
            return
        self.sock = s
        self.connected = True
        self.last_rx = time.time()
        self.send({"t": "hello", "name": name, "proto": PROTOCOL_VERSION, "ver": VERSION, "token": token, "host_key": host_key})
        fb = server_frame_buffer()
        while self.connected:
            try:
                data = s.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            self.last_rx = time.time()
            try:
                for m in fb.feed(data):
                    if m.get("t") == "pong":
                        sent = self._ping_sent.pop(m.get("n"), None)
                        if sent:
                            self.latency_ms = int((time.time() - sent) * 1000)
                    else:
                        self.q.put(m)
            except ProtocolError:
                break
        was = self.connected
        self.connected = False
        try:
            s.close()
        except OSError:
            pass
        if was:
            self.q.put({"t": "net_error", "reason": "connection lost"})

    def send(self, msg: dict) -> bool:
        s = self.sock
        if not s:
            return False
        try:
            with self._lock:
                s.settimeout(2.0)
                s.sendall(encode(msg))
                s.settimeout(0.5)
            return True
        except OSError:
            if self.connected:
                self.connected = False
                self.q.put({"t": "net_error", "reason": "send failed"})
            return False

    def keepalive(self) -> None:
        now = time.time()
        if self.connected and now - self._last_ping > 1.5:
            self._last_ping = now
            n = int(now * 1000) & 0x7FFFFFFF
            self._ping_sent[n] = now
            if len(self._ping_sent) > 20:
                self._ping_sent.clear()
            self.send({"t": "ping", "n": n})

    def poll(self) -> List[dict]:
        out = []
        while True:
            try:
                out.append(self.q.get_nowait())
            except queue.Empty:
                return out

    def close(self) -> None:
        self.connected = False
        s, self.sock = self.sock, None
        if s:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
