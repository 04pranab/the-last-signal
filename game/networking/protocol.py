"""Wire protocol: length-prefixed JSON frames + strict message validation.

Frame  = 4 byte big-endian length + UTF-8 JSON object.
Nothing received from the network is ever executed or unpickled; messages are
plain JSON that is type-checked against a schema before it reaches game code.
"""
from __future__ import annotations

import json
import math
import struct
from typing import Any, Dict, List, Optional

from ..config import MAX_CLIENT_FRAME, MAX_NAME_LEN, MAX_SERVER_FRAME


class ProtocolError(Exception):
    """Unrecoverable framing problem (connection must be dropped)."""


class BadMessage(Exception):
    """A single frame was malformed (can be skipped)."""


def encode(msg: dict) -> bytes:
    data = json.dumps(msg, separators=(",", ":")).encode("utf-8")
    return struct.pack(">I", len(data)) + data


class FrameBuffer:
    """Incremental frame decoder.  `feed()` yields decoded dicts; bad frames raise BadMessage via `errors`."""

    def __init__(self, max_frame: int = MAX_CLIENT_FRAME):
        self.buf = bytearray()
        self.max_frame = max_frame
        self.errors = 0

    def feed(self, data: bytes) -> List[dict]:
        self.buf.extend(data)
        out: List[dict] = []
        while True:
            if len(self.buf) < 4:
                break
            (n,) = struct.unpack(">I", self.buf[:4])
            if n == 0 or n > self.max_frame:
                raise ProtocolError(f"illegal frame length {n}")
            if len(self.buf) < 4 + n:
                break
            payload = bytes(self.buf[4:4 + n])
            del self.buf[:4 + n]
            try:
                obj = json.loads(payload.decode("utf-8"))
                if not isinstance(obj, dict) or not isinstance(obj.get("t"), str):
                    raise ValueError("not a message object")
                out.append(obj)
            except (ValueError, UnicodeDecodeError, RecursionError):
                self.errors += 1
        return out


def server_frame_buffer() -> FrameBuffer:
    return FrameBuffer(MAX_SERVER_FRAME)


# ---------------------------------------------------------------- validation
def _num(v: Any, lo: float, hi: float) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return max(lo, min(hi, float(v)))


def _str(v: Any, maxlen: int) -> Optional[str]:
    if not isinstance(v, str):
        return None
    return v[:maxlen]


def clean_name(name: Any) -> str:
    s = name if isinstance(name, str) else ""
    s = "".join(ch for ch in s if ch.isprintable() and ch not in "<>\\\"'`").strip()
    return s[:MAX_NAME_LEN] or "Player"


def validate_client_message(msg: dict) -> Optional[dict]:
    """Return a sanitised copy of a client->server message, or None if it is invalid."""
    t = msg.get("t")
    if t == "hello":
        proto = msg.get("proto")
        if isinstance(proto, bool) or not isinstance(proto, int):
            return None
        return {"t": "hello", "name": clean_name(msg.get("name")), "proto": proto,
                "ver": _str(msg.get("ver", ""), 16) or "", "token": _str(msg.get("token", ""), 64) or "",
                "host_key": _str(msg.get("host_key", ""), 64) or ""}
    if t == "input":
        mx, my = _num(msg.get("mx"), -1, 1), _num(msg.get("my"), -1, 1)
        if mx is None or my is None:
            return None
        aim = _num(msg.get("aim", 0.0), -7.0, 7.0)
        fire = msg.get("fire", False)
        return {"t": "input", "mx": mx, "my": my, "aim": aim if aim is not None else 0.0, "fire": fire if isinstance(fire, bool) else False}
    if t == "interact":
        oid = _str(msg.get("oid"), 40)
        return {"t": "interact", "oid": oid} if oid else None
    if t == "transmit":
        f, c, s = _str(msg.get("freq"), 8), _str(msg.get("chan"), 8), _str(msg.get("seq"), 8)
        if f is None or c is None or s is None:
            return None
        return {"t": "transmit", "freq": f, "chan": c, "seq": s}
    if t in ("start", "leave", "ping", "return_lobby", "reload"):
        n = msg.get("n")
        return {"t": t, "n": n if isinstance(n, int) and not isinstance(n, bool) else 0}
    if t == "weapon":
        name = _str(msg.get("name"), 12)
        from ..weapons import WEAPONS
        return {"t": "weapon", "name": name} if name in WEAPONS else None
    if t == "chat":
        txt = _str(msg.get("text"), 140)
        if txt is None:
            return None
        txt = "".join(ch for ch in txt if ch.isprintable()).strip()
        return {"t": "chat", "text": txt[:120]} if txt else None
    if t == "join_decision":
        rid = msg.get("rid")
        acc = msg.get("accept")
        if isinstance(rid, bool) or not isinstance(rid, int) or not isinstance(acc, bool):
            return None
        return {"t": "join_decision", "rid": rid, "accept": acc}
    return None
