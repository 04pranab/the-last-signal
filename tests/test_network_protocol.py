import json
import struct

import pytest

from game.networking.protocol import (FrameBuffer, ProtocolError, clean_name, encode,
                                      validate_client_message)


def test_roundtrip_and_fragmentation():
    msgs = [{"t": "input", "mx": 1, "my": 0}, {"t": "ping", "n": 3}]
    data = b"".join(encode(m) for m in msgs)
    fb = FrameBuffer()
    out = []
    for i in range(0, len(data), 3):          # byte-trickle
        out += fb.feed(data[i:i + 3])
    assert out == msgs


def test_oversize_and_zero_frames_rejected():
    with pytest.raises(ProtocolError):
        FrameBuffer().feed(struct.pack(">I", 10 ** 9) + b"x")
    with pytest.raises(ProtocolError):
        FrameBuffer().feed(struct.pack(">I", 0))


def test_bad_json_is_skipped_not_fatal():
    fb = FrameBuffer()
    bad = b"{not json"
    good = encode({"t": "ping"})
    out = fb.feed(struct.pack(">I", len(bad)) + bad + good)
    assert out == [{"t": "ping"}] and fb.errors == 1


def test_non_object_and_untyped_rejected():
    fb = FrameBuffer()
    for payload in (b"[1,2]", b"123", b'{"x":1}', b'{"t":5}', b"\xff\xfe"):
        fb.feed(struct.pack(">I", len(payload)) + payload)
    assert fb.errors == 5


def test_deep_nesting_does_not_crash():
    fb = FrameBuffer()
    payload = b"[" * 20000 + b"]" * 20000
    fb.feed(struct.pack(">I", len(payload)) + payload)
    assert fb.errors == 1


@pytest.mark.parametrize("bad", [
    {"t": "input", "mx": "a", "my": 0}, {"t": "input", "mx": float("nan"), "my": 0}, {"t": "input", "mx": True, "my": 0},
    {"t": "interact"}, {"t": "interact", "oid": 5}, {"t": "transmit", "freq": 1, "chan": "1", "seq": "1"},
    {"t": "hello", "proto": "1"}, {"t": "join_decision", "rid": "x", "accept": True}, {"t": "evil"}, {"t": "join_decision", "rid": 1},
])
def test_validate_rejects(bad):
    assert validate_client_message(bad) is None


def test_validate_clamps_and_cleans():
    m = validate_client_message({"t": "input", "mx": 99, "my": -99})
    assert m["mx"] == 1 and m["my"] == -1
    h = validate_client_message({"t": "hello", "proto": 1, "name": "<b>Om</b>\x00" + "x" * 100})
    assert "<" not in h["name"] and len(h["name"]) <= 16
    assert clean_name(None) == "Player"
