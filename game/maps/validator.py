"""Validation of generated maps.  Returns a list of human readable problems (empty = valid)."""
from __future__ import annotations

from collections import deque
from typing import Iterable, List, Set, Tuple

from .generator import FLOOR, MapData


def flood(m: MapData, starts: Iterable[Tuple[int, int]], lock_restricted: bool) -> bytearray:
    """4-connected flood fill over walkable cells.  Closed (locked restricted) doors are solid."""
    W, H = m.width, m.height
    solid = bytearray(m.solid)
    if lock_restricted:
        for d in m.doors:
            if d.restricted:
                for (x, y) in d.cells:
                    solid[y * W + x] = 1
    seen = bytearray(W * H)
    q = deque()
    for (x, y) in starts:
        if 0 <= x < W and 0 <= y < H and not solid[y * W + x] and not seen[y * W + x]:
            seen[y * W + x] = 1
            q.append((x, y))
    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < W and 0 <= ny < H:
                i = ny * W + nx
                if not seen[i] and not solid[i]:
                    seen[i] = 1
                    q.append((nx, ny))
    return seen


def object_access_cells(m: MapData, o) -> List[Tuple[int, int]]:
    cells = {(x, y) for y in range(o.y, o.y + o.h) for x in range(o.x, o.x + o.w)}
    out = []
    for (x, y) in cells:
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in cells and m.in_bounds(*n) and not m.solid[n[1] * m.width + n[0]]:
                out.append(n)
    return out


def validate_map(m: MapData) -> List[str]:
    errs: List[str] = []
    W, H = m.width, m.height
    if not (25 <= len(m.rooms) <= 45):
        errs.append(f"room count {len(m.rooms)} out of range")
    # --- rooms must not overlap (footprints incl. walls)
    for i, a in enumerate(m.rooms):
        ax0, ay0, ax1, ay1 = a.footprint
        if ax0 < 1 or ay0 < 1 or ax1 > W - 2 or ay1 > H - 2:
            errs.append(f"room {a.id} outside map")
        for b in m.rooms[i + 1:]:
            bx0, by0, bx1, by1 = b.footprint
            if not (ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0):
                errs.append(f"rooms {a.id} and {b.id} overlap")
    # --- doors on valid openings
    for d in m.doors:
        room = m.rooms[d.rooms[0]]
        for (cx, cy) in d.cells:
            if m.tile(cx, cy) != FLOOR:
                errs.append(f"door {d.id} cell not floor")
                continue
            inside = [n for n in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)) if room.contains(*n)]
            if len(inside) != 1:
                errs.append(f"door {d.id} not on room wall")
                continue
            n_in = inside[0]
            n_out = (2 * cx - n_in[0], 2 * cy - n_in[1])
            if m.tile(*n_out) != FLOOR or room.contains(*n_out):
                errs.append(f"door {d.id} opens onto nothing")
    # --- spawns
    if len(set(m.spawns)) < 16:
        errs.append("fewer than 16 spawn points")
    for (x, y) in m.spawns:
        if not m.in_bounds(x, y) or m.solid[y * W + x]:
            errs.append(f"spawn {x},{y} blocked")
    # --- object sanity
    for o in m.objects:
        for yy in range(o.y, o.y + o.h):
            for xx in range(o.x, o.x + o.w):
                if m.tile(xx, yy) != FLOOR or not m.rooms[o.room].contains(xx, yy):
                    errs.append(f"object {o.id} outside room floor")
    for p in m.props:
        for yy in range(p.y, p.y + p.h):
            for xx in range(p.x, p.x + p.w):
                if m.tile(xx, yy) != FLOOR:
                    errs.append("prop on non-floor")
    if errs:
        return errs[:10]
    # --- walkable space per room
    for r in m.rooms:
        free = sum(1 for (x, y) in ((x, y) for y in range(r.y, r.y + r.h) for x in range(r.x, r.x + r.w)) if not m.solid[y * W + x])
        if free < 0.5 * r.w * r.h:
            errs.append(f"room {r.id} too cluttered")
    if not m.spawns:
        return errs + ["no spawns"]
    # --- reachability with restricted doors LOCKED (pre-power)
    pre = flood(m, m.spawns[:1], lock_restricted=True)
    if any(not pre[y * W + x] for (x, y) in m.spawns):
        errs.append("a spawn point is unreachable")
    for r in m.rooms:
        if r.restricted:
            continue
        for y in range(r.y, r.y + r.h):
            for x in range(r.x, r.x + r.w):
                if not m.solid[y * W + x] and not pre[y * W + x]:
                    errs.append(f"open room {r.id} not fully reachable")
                    break
            else:
                continue
            break
    gen = m.object_by_id.get(m.meta.get("generator_id"))
    if gen is None or not any(pre[y * W + x] for (x, y) in object_access_cells(m, gen)):
        errs.append("generator unreachable before power")
    # --- everything reachable once power is on
    post = flood(m, m.spawns[:1], lock_restricted=False)
    for r in m.rooms:
        for y in range(r.y, r.y + r.h):
            for x in range(r.x, r.x + r.w):
                if not m.solid[y * W + x] and not post[y * W + x]:
                    errs.append(f"room {r.id} not fully reachable")
                    break
            else:
                continue
            break
    for oid in [m.meta.get("transmitter_id"), m.meta.get("core_id")] + list(m.meta.get("clue_ids", [])):
        o = m.object_by_id.get(oid)
        if o is None:
            errs.append(f"missing object {oid}")
            continue
        if not any(post[y * W + x] for (x, y) in object_access_cells(m, o)):
            errs.append(f"object {oid} unreachable")
    for o in m.objects:
        if not any(post[y * W + x] for (x, y) in object_access_cells(m, o)):
            errs.append(f"object {o.id} unreachable")
        if not o.needs_power and not any(pre[y * W + x] for (x, y) in object_access_cells(m, o)):
            errs.append(f"unpowered object {o.id} unreachable pre-power")
    # --- the fragments exist & answer is well formed
    ans = m.secret.get("answer") if m.secret else None
    if not ans or len(ans.get("freq", "")) != 3 or len(ans.get("chan", "")) != 2 or len(ans.get("seq", "")) != 3:
        errs.append("bad answer")
    if len(set(m.meta.get("clue_ids", []))) != 5:
        errs.append("missing clue terminals")
    return errs[:10]
