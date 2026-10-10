import socket
import struct
import time

import pytest

from game.networking.client import NetClient
from game.networking.discovery import DiscoveryBroadcaster, DiscoveryListener
from game.networking.protocol import encode
from game.networking.server import GameServer


def wait_for(client, kind, timeout=5.0, store=None):
    end = time.time() + timeout
    buf = store if store is not None else []
    while time.time() < end:
        buf.extend(client.poll())
        for m in buf:
            if m["t"] == kind:
                buf.remove(m)
                return m
        time.sleep(0.02)
    raise AssertionError(f"timeout waiting for {kind}; got {[m['t'] for m in buf]}")


class Peer:
    def __init__(self, port, name, **kw):
        self.c = NetClient()
        self.buf = []
        self.c.connect("127.0.0.1", port, name, **kw)

    def wait(self, kind, timeout=5.0):
        return wait_for(self.c, kind, timeout, self.buf)

    def drain(self):
        self.buf.extend(self.c.poll())
        out, self.buf = self.buf, []
        return out


@pytest.fixture()
def server():
    s = GameServer("Test", 0, 15, seed=99, host_key="HK", discovery=False, echo=False)
    port = s.start()
    yield s, port
    s.stop()


def join(server_port, name, host_peer, accept=True):
    p = Peer(server_port, name)
    p.wait("pending")
    while True:
        req = host_peer.wait("join_request")
        if req["name"] == name[:16]:
            break
    host_peer.c.send({"t": "join_decision", "rid": req["rid"], "accept": accept})
    return p


def test_join_request_accept_and_reject(server):
    s, port = server
    host = Peer(port, "Host", host_key="HK")
    assert host.wait("welcome")["host"] is True
    p2 = join(port, "Pranab", host)
    w = p2.wait("welcome")
    assert w["pid"] == 2 and not w["host"]
    p3 = join(port, "Rejected", host, accept=False)
    assert p3.wait("rejected")["reason"] == "rejected"
    time.sleep(0.2)
    lobbies = [m for m in host.drain() if m["t"] == "lobby"]
    assert any(pl["name"] == "Pranab" for pl in lobbies[-1]["players"])
    assert not any(pl["name"] == "Rejected" for pl in lobbies[-1]["players"])


def test_full_server_rejects(server):
    s, port = server
    s.max_players = 2
    host = Peer(port, "Host", host_key="HK"); host.wait("welcome")
    join(port, "A", host).wait("welcome")
    c = Peer(port, "B")
    assert c.wait("rejected")["reason"] == "full"


def test_only_host_can_start_and_late_join_rejected(server):
    s, port = server
    host = Peer(port, "Host", host_key="HK"); host.wait("welcome")
    g = join(port, "Guest", host); g.wait("welcome")
    g.c.send({"t": "start"})
    time.sleep(0.3)
    assert s.phase == "lobby"
    host.c.send({"t": "start"})
    start = g.wait("start", 15)
    assert start["map"]["name"] == "Research Station A-17" and "answer" not in str(start["map"])
    late = Peer(port, "Late")
    assert late.wait("rejected")["reason"] == "started"


def test_synchronised_movement_and_authority(server):
    s, port = server
    host = Peer(port, "Host", host_key="HK"); host.wait("welcome")
    g = join(port, "Guest", host); g.wait("welcome")
    host.c.send({"t": "start"})
    host.wait("start", 15); g.wait("start", 15)
    g.c.send({"t": "input", "mx": 1, "my": 0})
    time.sleep(0.8)
    snaps = [m for m in host.drain() if m["t"] == "snap"]
    rows = {r[0]: r for r in snaps[-1]["p"]}
    x1 = rows[2][1]
    g.c.send({"t": "input", "mx": 0, "my": 0})
    g.c.send({"t": "input", "mx": 1e9, "my": 1e9})            # clamped
    g.c.send({"t": "set_pos", "x": 1, "y": 1})                  # unknown message ignored
    time.sleep(0.5)
    snaps = [m for m in host.drain() if m["t"] == "snap"]
    assert snaps and abs(snaps[-1]["p"][1][2]) > 10
    assert x1 > 0


def test_malformed_packets_do_not_crash_server(server):
    s, port = server
    host = Peer(port, "Host", host_key="HK"); host.wait("welcome")
    attacks = [b"\x00\x00\x00\x05junk!" * 5, b"\xff\xff\xff\xff", b"", b"GET / HTTP/1.1\r\n\r\n",
               struct.pack(">I", 10) + b"[1,2,3,4,5]", encode({"t": "hello", "proto": 1, "name": "x" * 5000}) ,
               encode({"t": "input", "mx": "bad"}) * 20, bytes(range(256)) * 50]
    for a in attacks:
        r = socket.create_connection(("127.0.0.1", port))
        try:
            r.sendall(a)
        except OSError:
            pass
        time.sleep(0.05)
        r.close()
    # half-open flood
    socks = [socket.create_connection(("127.0.0.1", port)) for _ in range(30)]
    time.sleep(0.2)
    for x in socks:
        x.close()
    host.c.send({"t": "ping", "n": 7})
    time.sleep(0.3)
    assert host.c.connected and s._thread.is_alive()
    assert s.stats["bad_frames"] > 0
    # server still accepts new players
    g = join(port, "StillOK", host)
    assert g.wait("welcome")["pid"] == 2


def test_disconnect_and_reconnect_with_token(server):
    s, port = server
    host = Peer(port, "Host", host_key="HK"); host.wait("welcome")
    g = join(port, "Guest", host)
    w = g.wait("welcome")
    host.c.send({"t": "start"})
    host.wait("start", 15); g.wait("start", 15)
    g.c.close()
    time.sleep(0.6)
    lobby = [m for m in host.drain() if m["t"] == "lobby"][-1]
    assert [p for p in lobby["players"] if p["pid"] == 2][0]["connected"] is False
    g2 = Peer(port, "Guest", token=w["token"])
    assert g2.wait("welcome")["pid"] == 2
    g2.wait("start", 10)
    assert s._thread.is_alive()


def test_host_leaving_closes_server_for_clients(server):
    s, port = server
    host = Peer(port, "Host", host_key="HK"); host.wait("welcome")
    g = join(port, "Guest", host); g.wait("welcome")
    host.c.send({"t": "leave"})
    msgs = []
    end = time.time() + 3
    while time.time() < end and not any(m["t"] in ("closed", "net_error") for m in msgs):
        msgs += g.c.poll()
        time.sleep(0.05)
    assert any(m["t"] in ("closed", "net_error") for m in msgs)


def test_eight_and_fifteen_players(server):
    s, port = server
    host = Peer(port, "Host", host_key="HK"); host.wait("welcome")
    peers = []
    for i in range(14):
        p = join(port, f"P{i}", host)
        p.wait("welcome")
        peers.append(p)
    host.c.send({"t": "start"})
    for p in [host] + peers:
        p.wait("start", 20)
    for i, p in enumerate(peers):
        p.c.send({"t": "input", "mx": 1 if i % 2 else -1, "my": 0.5})
    time.sleep(1.0)
    snaps = [m for m in host.drain() if m["t"] == "snap"]
    assert len(snaps[-1]["p"]) == 15
    # sync check: every client sees the same player set
    for p in peers[:5]:
        sn = [m for m in p.drain() if m["t"] == "snap"]
        assert len(sn[-1]["p"]) == 15


def test_lan_discovery_roundtrip():
    port = 47999
    lst = DiscoveryListener(port)
    lst.start()
    s = GameServer("Om's Game", 0, 15, seed=1, discovery=False)
    s.start()
    b = DiscoveryBroadcaster(s.discovery_info, port, interval=0.2)
    b.start()
    try:
        end = time.time() + 5
        games = []
        while time.time() < end and not games:
            games = lst.get_games()
            time.sleep(0.1)
        assert games and games[0]["name"] == "Om's Game" and games[0]["port"] == s.port and games[0]["max"] == 15
        assert games[0]["map"] == "Research Station A-17"
    finally:
        b.stop(); lst.stop(); s.stop()


def test_discovery_ignores_garbage():
    port = 47998
    lst = DiscoveryListener(port)
    lst.start()
    time.sleep(0.3)
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for junk in (b"hello", b"{}", b'{"magic":"THELASTSIGNAL"}', b'{"magic":"THELASTSIGNAL","server_id":"x","port":"abc"}', b"\xff\xfe"):
        u.sendto(junk, ("127.0.0.1", port))
    time.sleep(0.5)
    assert lst.get_games() == []
    lst.stop()


def test_restart_server_repeatedly():
    for _ in range(5):
        s = GameServer("R", 0, 15, seed=3, host_key="K", discovery=False)
        port = s.start()
        h = Peer(port, "H", host_key="K")
        h.wait("welcome")
        h.c.close()
        s.stop()
        assert not s._thread.is_alive()


def test_chat_broadcast_and_rate_limit(server):
    s, port = server
    host = Peer(port, "Host", host_key="HK"); host.wait("welcome")
    g = join(port, "Guest", host); g.wait("welcome")
    g.c.send({"t": "chat", "text": "hello crew"})
    msg = host.wait("chat")
    assert msg["name"] == "Guest" and msg["text"] == "hello crew" and msg["pid"] == 2
    for i in range(30):                                  # spam is rate limited
        g.c.send({"t": "chat", "text": f"spam {i}"})
    time.sleep(0.5)
    got = [m for m in host.drain() if m["t"] == "chat"]
    assert len(got) < 10


def test_map_2_selected_on_server_and_sent_to_clients():
    s = GameServer("Mine", 0, 15, seed=7, host_key="HK", discovery=False, echo=False, map_id="mining_complex")
    port = s.start()
    try:
        h = Peer(port, "Host", host_key="HK"); h.wait("welcome")
        assert s.discovery_info()["map"] == "Underground Mining Complex"
        h.c.send({"t": "start"})
        st = h.wait("start", 20)
        assert st["map"]["map_id"] == "mining_complex" and "answer" not in str(st["map"])
    finally:
        s.stop()
