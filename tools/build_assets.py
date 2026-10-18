#!/usr/bin/env python3
"""Asset pipeline for THE LAST SIGNAL.

Reads the supplied Kenney asset packs (the extracted ``asset/`` directory) and
writes the cleaned, renamed sprites actually used by the game into ``assets/``.
Also draws a handful of sci-fi props procedurally (server racks, terminals,
generator, transmitter ...) because none of the supplied 2D packs contain
top-down sci-fi machinery (the space-station / modular-space kits are 3D only).

Requires Pillow (build-time only; the game itself only needs pygame).

Usage:
    python tools/build_assets.py /path/to/extracted/asset
"""
import json
import math
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageChops

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
MAP = OUT / "maps" / "research_station"
S = 4  # supersampling for procedural art
TS = 64

# ------------------------------------------------------------------ palette
TEAL = (155, 188, 192)
SLATE = (45, 59, 70)
DARK = (28, 36, 44)
ORANGE = (232, 112, 26)
TAN = (200, 138, 79)
WHITE = (238, 250, 245)
CYAN = (77, 224, 255)
GREEN = (43, 179, 95)
RED = (229, 72, 77)
AMBER = (255, 176, 32)
STEEL = (120, 134, 146)


def tile_img(src, n):
    return Image.open(src / "PNG" / "Tiles" / f"tile_{n:02d}.png").convert("RGBA")


def sheet_crop(src, c0, r0, c1, r1, trim=True):
    sheet = Image.open(src / "Tilesheet" / "tilesheet_complete.png").convert("RGBA")
    im = sheet.crop((c0 * TS, r0 * TS, c1 * TS, r1 * TS))
    if trim:
        bb = im.getbbox()
        if bb:
            im = im.crop(bb)
    return im


# ------------------------------------------------------- drawing helpers
class Cv:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.im = Image.new("RGBA", (w * TS * S, h * TS * S), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def _b(self, box):
        return [v * S for v in box]

    def rect(self, box, fill, outline=None, r=0, width=1):
        if r:
            self.d.rounded_rectangle(self._b(box), r * S, fill=fill, outline=outline, width=max(1, int(width * S)))
        else:
            self.d.rectangle(self._b(box), fill=fill, outline=outline, width=max(1, int(width * S)))

    def ell(self, box, fill, outline=None, width=1):
        self.d.ellipse(self._b(box), fill=fill, outline=outline, width=max(1, int(width * S)))

    def line(self, pts, fill, width=1):
        self.d.line([v * S for p in pts for v in p], fill=fill, width=int(width * S))

    def done(self):
        return self.im.resize((self.w * TS, self.h * TS), Image.LANCZOS)


def glow(cv, cx, cy, r, color, alpha=90):
    layer = Image.new("RGBA", cv.im.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for i in range(6, 0, -1):
        a = int(alpha * (i / 6) ** 2 / 3)
        rr = r * (1 + (6 - i) * 0.25)
        ld.ellipse([(cx - rr) * S, (cy - rr) * S, (cx + rr) * S, (cy + rr) * S], fill=color + (a,))
    # keep glow inside the already-drawn (opaque) pixels so sprites keep their silhouette
    mask = cv.im.split()[3]
    layer.putalpha(ImageChops.multiply(layer.split()[3], mask))
    cv.im = Image.alpha_composite(cv.im, layer)
    cv.d = ImageDraw.Draw(cv.im)


def housing(cv, box, body=SLATE, edge=DARK, r=4):
    cv.rect(box, edge, r=r)
    x0, y0, x1, y1 = box
    cv.rect((x0 + 1.5, y0 + 1.5, x1 - 1.5, y1 - 1.5), body, r=max(r - 1, 1))


def screen(cv, box, color, on=True, lines=True):
    x0, y0, x1, y1 = box
    cv.rect(box, DARK, r=2)
    cv.rect((x0 + 1.5, y0 + 1.5, x1 - 1.5, y1 - 1.5), color if on else (30, 40, 48), r=1)
    if on and lines:
        yy = y0 + 4
        while yy < y1 - 3:
            cv.line([(x0 + 4, yy), (x1 - 4 - (yy * 7 % 9), yy)], tuple(max(c - 90, 0) for c in color), 1)
            yy += 4


def make_terminal(color, on=True, corrupt=False, dead=False):
    cv = Cv(1, 1)
    housing(cv, (6, 4, 58, 60), r=5)
    cv.rect((10, 38, 54, 55), (60, 75, 88), r=2)  # keyboard deck
    for i in range(6):
        for j in range(2):
            cv.rect((13 + i * 6.6, 41 + j * 6, 18 + i * 6.6, 45 + j * 6), (110, 130, 145), r=1)
    if dead:
        screen(cv, (10, 8, 54, 34), (40, 48, 56), on=False)
    elif corrupt:
        screen(cv, (10, 8, 54, 34), (190, 60, 70), on=True, lines=False)
        for k in range(7):
            y = 10 + k * 3.4
            cv.rect((11 + (k * 13) % 17, y, 30 + (k * 29) % 22, y + 1.6), (255, 200, 200))
    else:
        screen(cv, (10, 8, 54, 34), color, on=on)
        if on:
            glow(cv, 32, 21, 26, color, 60)
            screen(cv, (10, 8, 54, 34), color, on=on)
    return cv.done()


def make_server(variant=0):
    cv = Cv(1, 1)
    housing(cv, (8, 3, 56, 61), r=3)
    for i in range(5):
        y = 7 + i * 10.5
        cv.rect((12, y, 52, y + 8), (22, 28, 36), r=1)
        for k in range(4):
            lit = (i * 3 + k + variant) % 3
            col = [GREEN, CYAN, AMBER][lit] if (i + k + variant) % 4 else (70, 80, 90)
            cv.ell((44 - k * 4.5, y + 2.5, 47 - k * 4.5, y + 5.5), col)
        cv.line([(15, y + 3), (30, y + 3)], (60, 74, 88), 1.2)
        cv.line([(15, y + 6), (26, y + 6)], (60, 74, 88), 1.2)
    return cv.done()


def make_lab_table(w=2):
    cv = Cv(w, 1)
    W = w * 64
    housing(cv, (3, 8, W - 3, 56), body=(214, 230, 232), edge=(110, 130, 140), r=4)
    cv.rect((7, 12, W - 7, 52), (232, 244, 244), r=3)
    # beakers / flasks viewed from above
    spots = [(16, 30, CYAN), (W / 2, 24, GREEN), (W - 18, 34, ORANGE)] if w > 1 else [(32, 30, CYAN)]
    for x, y, c in spots:
        cv.ell((x - 7, y - 7, x + 7, y + 7), (190, 210, 214), outline=(120, 140, 150), width=1.2)
        cv.ell((x - 4.5, y - 4.5, x + 4.5, y + 4.5), c)
    if w > 1:
        cv.rect((W / 2 + 12, 40, W / 2 + 28, 49), (60, 75, 88), r=1)
        cv.rect((W / 2 + 14, 42, W / 2 + 26, 47), (80, 200, 230), r=1)
    return cv.done()


def make_centrifuge():
    cv = Cv(1, 1)
    housing(cv, (6, 6, 58, 58), body=(214, 230, 232), edge=(110, 130, 140), r=8)
    cv.ell((14, 14, 50, 50), (60, 75, 88))
    cv.ell((17, 17, 47, 47), (40, 52, 62))
    for k in range(6):
        import math
        a = k * math.pi / 3
        cv.ell((32 + 10 * math.cos(a) - 3, 32 + 10 * math.sin(a) - 3, 32 + 10 * math.cos(a) + 3, 32 + 10 * math.sin(a) + 3), CYAN)
    cv.ell((29, 29, 35, 35), (200, 210, 215))
    return cv.done()


def make_shelf():
    cv = Cv(1, 1)
    housing(cv, (3, 6, 61, 58), body=(150, 104, 62), edge=(96, 62, 34), r=2)
    cols = [(180, 60, 60), (60, 120, 180), (230, 180, 60), (90, 160, 100), (200, 200, 210), (140, 80, 160)]
    for row in range(3):
        y = 10 + row * 16
        x = 7
        i = row
        while x < 54:
            w = 4 + (i * 5) % 4
            cv.rect((x, y, x + w, y + 13), cols[i % len(cols)], r=1)
            x += w + 1
            i += 1
        cv.line([(5, y + 14.5), (59, y + 14.5)], (96, 62, 34), 1.5)
    return cv.done()


def make_cabinet():
    cv = Cv(1, 1)
    housing(cv, (8, 6, 56, 58), body=(150, 165, 175), edge=(80, 94, 106), r=2)
    for k in range(3):
        y = 10 + k * 16
        cv.rect((12, y, 52, y + 13), (170, 184, 192), outline=(80, 94, 106), r=1)
        cv.rect((26, y + 5, 38, y + 8), (60, 70, 80), r=1)
    return cv.done()


def make_locker():
    cv = Cv(1, 1)
    housing(cv, (6, 6, 58, 58), body=(88, 112, 128), edge=(40, 56, 68), r=2)
    cv.line([(32, 8), (32, 56)], (40, 56, 68), 1.5)
    for x in (20, 44):
        for k in range(3):
            cv.line([(x - 6, 14 + k * 3), (x + 6, 14 + k * 3)], (50, 70, 84), 1)
        cv.rect((x + 2, 36, x + 5, 44), (200, 210, 215), r=1)
    return cv.done()


def make_barrel(color=ORANGE):
    cv = Cv(1, 1)
    cv.ell((9, 9, 55, 55), tuple(int(c * 0.55) for c in color))
    cv.ell((11, 11, 53, 53), color)
    cv.ell((17, 17, 47, 47), tuple(int(c * 0.8) for c in color), outline=tuple(int(c * 0.55) for c in color), width=1.5)
    cv.ell((27, 27, 37, 37), (60, 60, 66))
    return cv.done()


def make_pipe(kind="straight"):
    cv = Cv(1, 1)
    if kind == "straight":
        cv.rect((0, 22, 64, 42), (90, 100, 108), r=0)
        cv.rect((0, 24, 64, 30), (170, 182, 190))
        for x in (10, 52):
            cv.rect((x - 3, 19, x + 3, 45), (60, 70, 78), r=1)
    elif kind == "valve":
        cv.rect((0, 22, 64, 42), (90, 100, 108))
        cv.rect((0, 24, 64, 30), (170, 182, 190))
        cv.ell((20, 20, 44, 44), RED, outline=(110, 30, 34), width=2)
        cv.line([(24, 32), (40, 32)], (255, 230, 230), 2)
        cv.line([(32, 24), (32, 40)], (255, 230, 230), 2)
    else:  # warm pipe segment with hazard marks
        cv.rect((0, 22, 64, 42), (110, 96, 70))
        for x in range(-10, 64, 14):
            cv.d.polygon([((x) * S, 42 * S), ((x + 7) * S, 42 * S), ((x + 14) * S, 22 * S), ((x + 7) * S, 22 * S)], fill=AMBER + (255,))
    return cv.done()


def make_panel():
    cv = Cv(1, 1)
    housing(cv, (8, 4, 56, 60), body=(80, 94, 106), edge=DARK, r=3)
    cv.rect((14, 10, 50, 30), (30, 38, 46), r=2)
    for i in range(4):
        cv.ell((17 + i * 8.5, 14, 22 + i * 8.5, 19), [GREEN, AMBER, RED, CYAN][i])
    cv.rect((14, 34, 50, 54), (60, 72, 84), r=2)
    for i in range(3):
        cv.rect((18 + i * 11, 38, 23 + i * 11, 50), (200, 60, 50) if i == 1 else (170, 180, 190), r=1)
    return cv.done()


def make_battery():
    cv = Cv(2, 1)
    housing(cv, (3, 8, 125, 56), body=(70, 84, 96), edge=DARK, r=4)
    for i in range(5):
        x = 9 + i * 23
        cv.rect((x, 13, x + 18, 51), (36, 46, 56), r=2)
        cv.rect((x + 3, 16, x + 15, 24), AMBER if i % 2 else GREEN, r=1)
        cv.rect((x + 3, 28, x + 15, 48), (60, 74, 86), r=1)
    return cv.done()


def make_generator(on):
    import math
    cv = Cv(2, 2)
    housing(cv, (4, 4, 124, 124), body=(80, 94, 106), edge=DARK, r=8)
    cv.rect((12, 12, 116, 116), (60, 72, 84), r=6)
    cv.ell((26, 20, 102, 96), (30, 38, 46))
    cv.ell((30, 24, 98, 92), (42, 52, 62))
    for k in range(6):
        a = k * math.pi / 3 + (0.3 if on else 0)
        cv.d.polygon([(64 * S, 58 * S), ((64 + 30 * math.cos(a - 0.35)) * S, (58 + 30 * math.sin(a - 0.35)) * S),
                      ((64 + 30 * math.cos(a + 0.35)) * S, (58 + 30 * math.sin(a + 0.35)) * S)], fill=(150, 165, 175, 255))
    cv.ell((58, 52, 70, 64), (200, 210, 215))
    # status panel
    cv.rect((24, 100, 104, 112), DARK, r=2)
    col = GREEN if on else RED
    for i in range(5):
        cv.rect((28 + i * 15, 103, 38 + i * 15, 109), col if (on or i < 1) else (70, 40, 44), r=1)
    if on:
        glow(cv, 64, 58, 50, GREEN, 50)
    return cv.done()


def make_core(on):
    cv = Cv(2, 2)
    housing(cv, (4, 4, 124, 124), body=(56, 66, 82), edge=DARK, r=8)
    cv.ell((22, 22, 106, 106), (24, 30, 40), outline=(90, 104, 120), width=3)
    c = CYAN if on else (60, 90, 100)
    if on:
        glow(cv, 64, 64, 36, CYAN, 120)
    cv.ell((38, 38, 90, 90), c if on else (50, 70, 80))
    cv.ell((50, 50, 78, 78), WHITE if on else (80, 100, 110))
    for a in range(4):
        import math
        t = a * math.pi / 2 + math.pi / 4
        cv.line([(64 + 30 * math.cos(t), 64 + 30 * math.sin(t)), (64 + 46 * math.cos(t), 64 + 46 * math.sin(t))], c, 3)
    for i in range(4):
        cv.rect((14 + i * 8, 112, 20 + i * 8, 118), GREEN if on else (60, 80, 70), r=1)
    return cv.done()


def make_transmitter(on):
    import math
    cv = Cv(3, 3)
    W = 192
    housing(cv, (4, 4, W - 4, W - 4), body=(48, 58, 74), edge=DARK, r=12)
    for i in range(0, W, 24):
        cv.line([(8 + i, 8), (8 + i, W - 8)], (56, 68, 84), 1)
        cv.line([(8, 8 + i), (W - 8, 8 + i)], (56, 68, 84), 1)
    ring = CYAN if on else (70, 96, 110)
    cv.ell((24, 24, W - 24, W - 24), (24, 30, 40), outline=(110, 124, 140), width=4)
    cv.ell((40, 40, W - 40, W - 40), (180, 196, 208), outline=(110, 124, 140), width=3)
    cv.ell((56, 56, W - 56, W - 56), (100, 114, 128))
    cv.ell((76, 76, W - 76, W - 76), (200, 212, 220))
    if on:
        glow(cv, W / 2, W / 2, 70, CYAN, 140)
    for k in range(3):
        r = 34 + k * 14
        cv.d.arc([(W / 2 - r) * S, (W / 2 - r) * S, (W / 2 + r) * S, (W / 2 + r) * S], 200, 340, fill=ring + (255,), width=3 * S)
    # antenna mast
    cv.line([(W / 2, W / 2), (W / 2 + 40, W / 2 - 40)], (230, 235, 240), 4)
    cv.ell((W / 2 + 36, W / 2 - 44, W / 2 + 46, W / 2 - 34), RED if not on else GREEN)
    # panel lights along bottom
    for i in range(9):
        cv.rect((22 + i * 18, W - 22, 32 + i * 18, W - 14), ring if (on or i == 0) else (50, 60, 70), r=1)
    cv.rect((4, 4, 12, 12), AMBER)
    cv.rect((W - 12, 4, W - 4, 12), AMBER)
    return cv.done()


def make_holo():
    import math
    cv = Cv(2, 2)
    housing(cv, (6, 6, 122, 122), body=(52, 64, 80), edge=DARK, r=10)
    cv.ell((20, 20, 108, 108), (24, 36, 48), outline=CYAN, width=2)
    glow(cv, 64, 64, 30, CYAN, 90)
    cv.ell((44, 44, 84, 84), (60, 150, 180), outline=CYAN, width=1.5)
    cv.d.arc([34 * S, 34 * S, 94 * S, 94 * S], 20, 200, fill=CYAN + (255,), width=2 * S)
    for k in range(6):
        a = k * math.pi / 3
        cv.ell((64 + 36 * math.cos(a) - 2.5, 64 + 36 * math.sin(a) - 2.5, 64 + 36 * math.cos(a) + 2.5, 64 + 36 * math.sin(a) + 2.5), CYAN)
    return cv.done()


def make_pillar():
    cv = Cv(1, 1)
    cv.rect((10, 10, 54, 54), DARK, r=5)
    cv.rect((13, 13, 51, 51), (84, 100, 114), r=4)
    cv.rect((19, 19, 45, 45), (110, 126, 140), r=3)
    cv.line([(19, 19), (45, 45)], (84, 100, 114), 1)
    cv.line([(45, 19), (19, 45)], (84, 100, 114), 1)
    return cv.done()


def make_scanner():
    cv = Cv(2, 1)
    housing(cv, (3, 6, 125, 58), body=(214, 230, 232), edge=(110, 130, 140), r=10)
    cv.rect((14, 14, 90, 50), (30, 44, 58), r=6)
    cv.rect((18, 18, 86, 46), (60, 130, 150), r=4)
    cv.line([(22, 32), (36, 32), (42, 24), (50, 40), (58, 32), (82, 32)], WHITE, 1.6)
    cv.rect((96, 16, 120, 48), (60, 75, 88), r=3)
    for k in range(3):
        cv.ell((101, 20 + k * 10, 108, 27 + k * 10), [GREEN, AMBER, RED][k])
    return cv.done()


def make_medcab():
    cv = Cv(1, 1)
    housing(cv, (6, 6, 58, 58), body=(232, 244, 244), edge=(120, 140, 150), r=3)
    cv.rect((28, 14, 36, 50), RED, r=1)
    cv.rect((14, 27, 50, 37), RED, r=1)
    return cv.done()


def make_crate_metal():
    cv = Cv(1, 1)
    housing(cv, (6, 6, 58, 58), body=(106, 120, 132), edge=DARK, r=3)
    cv.rect((12, 12, 52, 52), (90, 104, 116), outline=(60, 72, 84), r=2)
    cv.line([(12, 12), (52, 52)], (60, 72, 84), 2)
    cv.line([(52, 12), (12, 52)], (60, 72, 84), 2)
    return cv.done()


def make_door(color_trim):
    cv = Cv(1, 1)
    cv.rect((0, 12, 64, 52), DARK)
    cv.rect((1, 14, 64, 50), (96, 110, 122))
    cv.rect((1, 14, 64, 20), (140, 154, 166))
    cv.rect((1, 44, 64, 50), (70, 82, 94))
    cv.rect((60, 12, 64, 52), DARK)  # seam
    for y in (26, 32, 38):
        cv.line([(8, y), (50, y)], (74, 88, 100), 1.2)
    cv.rect((4, 22, 10, 42), color_trim, r=1)
    return cv.done()


def make_door_open():
    cv = Cv(1, 1)
    cv.rect((0, 14, 12, 50), DARK)
    cv.rect((1, 15, 11, 49), (96, 110, 122))
    cv.rect((1, 15, 11, 21), (140, 154, 166))
    return cv.done()


# ----------------------------------------------------------- floors & walls
def tint(im, mul, add=(0, 0, 0)):
    r, g, b, a = im.split()
    ch = []
    for c, m, ad in zip((r, g, b), mul, add):
        ch.append(c.point(lambda v, m=m, ad=ad: max(0, min(255, int(v * m + ad)))))
    return Image.merge("RGBA", (*ch, a))


def make_floor_server(base):
    im = tint(base, (0.42, 0.52, 0.62))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 63, 63], outline=(26, 38, 50, 255))
    d.line([(32, 0), (32, 63)], fill=(26, 38, 50, 255))
    d.line([(0, 32), (63, 32)], fill=(26, 38, 50, 255))
    return im


def make_floor_hazard(base):
    im = tint(base, (0.6, 0.6, 0.62))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 63, 63], outline=(40, 46, 52, 255))
    for x in range(-64, 64, 16):
        d.polygon([(x, 63), (x + 6, 63), (x + 70, 0), (x + 64, 0)], fill=(212, 160, 30, 90))
    return im


def make_wall_top():
    cv = Cv(1, 1)
    cv.rect((0, 0, 64, 64), (36, 48, 58))
    cv.rect((2, 2, 62, 62), (50, 66, 80))
    cv.rect((6, 6, 58, 58), (42, 56, 68))
    for p in ((6, 6), (58, 6), (6, 58), (58, 58)):
        cv.ell((p[0] - 1.5, p[1] - 1.5, p[0] + 1.5, p[1] + 1.5), (120, 138, 150))
    return cv.done()


def make_wall_face():
    cv = Cv(1, 1)
    cv.rect((0, 0, 64, 64), (30, 40, 50))
    cv.rect((0, 0, 64, 40), (66, 86, 100))
    cv.rect((0, 0, 64, 6), (96, 118, 132))
    cv.rect((0, 40, 64, 46), (22, 30, 38))
    cv.rect((0, 46, 64, 64), (40, 52, 62))
    for x in range(0, 64, 16):
        cv.line([(x, 6), (x, 40)], (50, 68, 80), 1)
    cv.line([(0, 22), (64, 22)], (80, 100, 114), 1)
    cv.rect((0, 56, 64, 64), (255, 255, 255, 18))
    return cv.done()


# ------------------------------------------------------- v2 sprites (crates, stations, decals, mining)
import random as _random


def make_weapon_crate(open_=False):
    cv = Cv(1, 1)
    housing(cv, (6, 10, 58, 58), body=(70, 96, 64), edge=(28, 40, 26), r=4)
    cv.rect((10, 14, 54, 54), (86, 114, 76), outline=(40, 58, 36), r=3)
    for x in (16, 48):
        cv.rect((x - 2, 14, x + 2, 54), (60, 84, 54))
    cv.rect((6, 28, 58, 36), (230, 200, 60))   # hazard stripe
    for x in range(8, 58, 12):
        cv.d.polygon([(x * S, 36 * S), ((x + 6) * S, 36 * S), ((x + 12) * S, 28 * S), ((x + 6) * S, 28 * S)], fill=(40, 40, 40, 255))
    if open_:
        cv.rect((10, 14, 54, 30), (30, 36, 30), r=3)
        cv.rect((14, 18, 50, 26), (20, 24, 22), r=2)
        cv.rect((6, 6, 58, 12), (96, 124, 86), r=2)
    else:
        cv.rect((26, 20, 38, 26), (230, 230, 230), r=1)
        cv.line([(22, 46), (42, 46)], (230, 230, 230), 3)
        cv.rect((38, 43, 46, 49), (230, 230, 230), r=1)
        glow(cv, 32, 32, 26, (120, 255, 140), 60)
    return cv.done()


def make_med_station():
    cv = Cv(1, 1)
    housing(cv, (8, 4, 56, 60), body=(236, 246, 246), edge=(90, 120, 130), r=5)
    cv.rect((14, 10, 50, 34), (30, 44, 56), r=3)
    cv.rect((29, 14, 35, 30), (230, 70, 70))
    cv.rect((22, 19, 42, 25), (230, 70, 70))
    glow(cv, 32, 22, 22, (255, 120, 120), 40)
    cv.rect((14, 40, 50, 54), (200, 220, 222), r=2)
    cv.ell((18, 44, 26, 52), GREEN)
    cv.rect((30, 44, 46, 50), (120, 150, 156), r=1)
    return cv.done()


def make_camera_console():
    cv = Cv(1, 1)
    housing(cv, (4, 6, 60, 58), body=(52, 62, 76), edge=DARK, r=4)
    for i in range(2):
        for j in range(2):
            x, y = 9 + i * 25, 10 + j * 19
            cv.rect((x, y, x + 22, y + 16), (16, 22, 28), r=2)
            cv.rect((x + 2, y + 2, x + 20, y + 14), (60, 110, 80) if (i + j) % 2 == 0 else (110, 90, 40), r=1)
            cv.line([(x + 4, y + 11), (x + 8, y + 7), (x + 13, y + 10), (x + 18, y + 5)], (200, 255, 210), 1)
    cv.rect((10, 48, 54, 55), (36, 44, 54), r=1)
    cv.ell((46, 49, 51, 54), RED)
    return cv.done()


def make_pickup(kind):
    cv = Cv(1, 1)
    if kind == "medkit":
        housing(cv, (14, 16, 50, 48), body=(240, 248, 248), edge=(110, 130, 140), r=4)
        cv.rect((29, 21, 35, 43), RED)
        cv.rect((21, 29, 43, 35), RED)
        glow(cv, 32, 32, 20, (255, 100, 100), 60)
    else:
        housing(cv, (14, 18, 50, 46), body=(86, 100, 70), edge=(34, 44, 30), r=3)
        for i in range(4):
            cv.rect((20 + i * 7, 22, 25 + i * 7, 40), (230, 190, 70), r=1)
            cv.rect((20 + i * 7, 22, 25 + i * 7, 27), (200, 200, 205), r=1)
        glow(cv, 32, 32, 20, (255, 220, 110), 55)
    return cv.done()


def make_decal(kind, seed):
    rng = _random.Random(seed)
    cv = Cv(1, 1)
    if kind == "blood":
        for _ in range(9):
            x, y, r = rng.uniform(14, 50), rng.uniform(14, 50), rng.uniform(2.5, 9)
            cv.ell((x - r, y - r, x + r, y + r), (110 + rng.randint(0, 30), 14, 18, 190))
        for _ in range(6):
            x, y = rng.uniform(8, 56), rng.uniform(8, 56)
            cv.ell((x - 1.5, y - 1.5, x + 1.5, y + 1.5), (120, 16, 20, 200))
    elif kind == "scorch":
        for _ in range(7):
            x, y, r = rng.uniform(16, 48), rng.uniform(16, 48), rng.uniform(6, 15)
            cv.ell((x - r, y - r, x + r, y + r), (10, 10, 12, 80))
    elif kind == "crack":
        x, y = rng.uniform(8, 20), rng.uniform(8, 56)
        pts = [(x, y)]
        for _ in range(7):
            x += rng.uniform(4, 9)
            y += rng.uniform(-8, 8)
            pts.append((x, y))
        cv.line(pts, (20, 24, 28, 200), 1.6)
    else:  # stain
        for _ in range(6):
            x, y, r = rng.uniform(14, 50), rng.uniform(14, 50), rng.uniform(5, 13)
            cv.ell((x - r, y - r, x + r, y + r), (40, 60, 66, 70))
    return cv.done()


def make_rock_wall(face):
    rng = _random.Random(7 if face else 3)
    cv = Cv(1, 1)
    base = (62, 52, 46) if face else (44, 37, 33)
    cv.rect((0, 0, 64, 64), base)
    for _ in range(34):
        x, y, r = rng.uniform(0, 64), rng.uniform(0, 64), rng.uniform(4, 11)
        sh = rng.randint(-16, 16)
        cv.ell((x - r, y - r, x + r, y + r), (base[0] + sh, base[1] + sh, base[2] + sh))
    if face:
        cv.rect((0, 0, 64, 7), (112, 94, 80))
        cv.rect((0, 40, 64, 46), (28, 22, 20))
        cv.rect((0, 46, 64, 64), (44, 36, 32))
        for x in range(4, 64, 14):
            cv.line([(x, 8), (x + rng.randint(-3, 3), 38)], (40, 32, 28), 1.4)
    return cv.done()


def make_ore_cart():
    cv = Cv(2, 1)
    housing(cv, (4, 8, 124, 56), body=(112, 100, 88), edge=(40, 34, 30), r=5)
    cv.rect((10, 14, 118, 50), (60, 52, 46), r=4)
    rng = _random.Random(11)
    for _ in range(22):
        x, y, r = rng.uniform(16, 112), rng.uniform(18, 46), rng.uniform(3, 7)
        c = (90 + rng.randint(-14, 14),) * 3
        cv.ell((x - r, y - r, x + r, y + r), c)
    for _ in range(7):
        x, y = rng.uniform(18, 110), rng.uniform(20, 44)
        cv.ell((x - 2, y - 2, x + 2, y + 2), (250, 200, 70))
    for x in (14, 110):
        cv.rect((x - 4, 6, x + 4, 12), (30, 26, 24))
        cv.rect((x - 4, 52, x + 4, 58), (30, 26, 24))
    return cv.done()


def make_rails(horizontal=True):
    cv = Cv(1, 1)
    for k in range(4):
        cv.rect((6 + k * 16, 12, 12 + k * 16, 52), (96, 70, 44))
    cv.rect((0, 18, 64, 23), (150, 156, 162))
    cv.rect((0, 41, 64, 46), (150, 156, 162))
    im = cv.done()
    return im


def make_drill():
    import math
    cv = Cv(2, 2)
    housing(cv, (4, 4, 124, 124), body=(220, 170, 40), edge=(80, 60, 14), r=10)
    cv.ell((24, 24, 104, 104), (60, 56, 52))
    cv.ell((32, 32, 96, 96), (110, 106, 100))
    for k in range(8):
        a = k * math.pi / 4
        cv.line([(64, 64), (64 + 28 * math.cos(a), 64 + 28 * math.sin(a))], (170, 168, 160), 5)
    cv.ell((54, 54, 74, 74), (230, 60, 50))
    for i in range(6):
        cv.rect((10 + i * 18, 108, 20 + i * 18, 118), (40, 36, 30) if i % 2 else (240, 200, 50))
    return cv.done()


def make_beam():
    cv = Cv(1, 1)
    cv.rect((12, 12, 52, 52), (40, 28, 18), r=3)
    cv.rect((15, 15, 49, 49), (112, 80, 48), r=2)
    cv.line([(15, 15), (49, 49)], (80, 56, 34), 2)
    cv.line([(49, 15), (15, 49)], (80, 56, 34), 2)
    return cv.done()


def make_ore_pile():
    rng = _random.Random(21)
    cv = Cv(1, 1)
    cv.ell((6, 10, 58, 58), (30, 26, 24))
    for _ in range(26):
        x, y, r = rng.uniform(14, 50), rng.uniform(16, 50), rng.uniform(4, 9)
        c = rng.randint(70, 118)
        cv.ell((x - r, y - r, x + r, y + r), (c, c - 6, c - 12))
    for _ in range(6):
        x, y = rng.uniform(16, 48), rng.uniform(18, 48)
        cv.ell((x - 2, y - 2, x + 2, y + 2), (250, 200, 70))
    return cv.done()


def make_tnt():
    cv = Cv(1, 1)
    housing(cv, (8, 10, 56, 58), body=(190, 50, 44), edge=(70, 16, 14), r=3)
    for k in range(4):
        cv.rect((12 + k * 11, 14, 18 + k * 11, 54), (150, 36, 32))
    cv.rect((8, 28, 56, 40), (240, 230, 210))
    cv.line([(18, 34), (26, 34)], (60, 20, 18), 3)
    cv.line([(31, 30), (31, 38)], (60, 20, 18), 3)
    cv.line([(36, 34), (46, 34)], (60, 20, 18), 3)
    return cv.done()


def make_lantern():
    cv = Cv(1, 1)
    glow(cv, 32, 32, 18, (255, 190, 90), 140) if False else None
    cv.ell((22, 22, 42, 42), (60, 44, 24))
    cv.ell((25, 25, 39, 39), (255, 200, 100))
    cv.ell((29, 29, 35, 35), (255, 250, 220))
    return cv.done()


def make_pump():
    cv = Cv(2, 2)
    housing(cv, (4, 4, 124, 124), body=(70, 100, 120), edge=DARK, r=10)
    cv.ell((26, 26, 102, 102), (36, 56, 70), outline=(150, 190, 210), width=4)
    cv.ell((44, 44, 84, 84), (110, 160, 190))
    cv.rect((56, 6, 72, 36), (150, 156, 162), r=2)
    cv.rect((6, 56, 36, 72), (150, 156, 162), r=2)
    for i in range(4):
        cv.rect((14 + i * 26, 108, 30 + i * 26, 116), GREEN if i % 2 == 0 else AMBER, r=1)
    return cv.done()


def make_dirt_floor(base, seed, dark=1.0):
    im = tint(base, (0.62 * dark, 0.52 * dark, 0.44 * dark))
    rng = _random.Random(seed)
    d = ImageDraw.Draw(im)
    for _ in range(26):
        x, y = rng.randint(0, 62), rng.randint(0, 62)
        v = rng.randint(-14, 14)
        d.ellipse([x, y, x + rng.randint(2, 6), y + rng.randint(1, 4)], fill=(90 + v, 74 + v, 62 + v, 255))
    return im


def build_v2(asset_root, extra_root):
    """Second pass: new interactables, decals, pickups and the Mining Complex tileset."""
    k_tds = asset_root / "kenney_top-down-shooter"
    manifest = json.loads((MAP / "manifest.json").read_text())

    def reg(name, im, group="props"):
        rel = f"{group}/{name}.png"
        save(im, MAP / rel)
        manifest["sprites"][name] = {"file": rel, "w": im.width, "h": im.height, "group": group}

    reg("weapon_crate_closed", make_weapon_crate(False), "terminals")
    reg("weapon_crate_open", make_weapon_crate(True), "terminals")
    reg("med_station", make_med_station(), "terminals")
    reg("camera_console", make_camera_console(), "terminals")
    reg("pickup_medkit", make_pickup("medkit"), "props")
    reg("pickup_ammo", make_pickup("ammo"), "props")
    for i in range(3):
        reg(f"decal_blood_{i}", make_decal("blood", 40 + i), "decorations")
    reg("decal_scorch", make_decal("scorch", 5), "decorations")
    reg("decal_crack_a", make_decal("crack", 6), "decorations")
    reg("decal_crack_b", make_decal("crack", 9), "decorations")
    reg("decal_stain", make_decal("stain", 12), "decorations")
    (MAP / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))

    # ---- mining complex: own manifest overlay (sprites/floors listed here override research_station ones)
    MM = OUT / "maps" / "mining_complex"
    mm = {"tile_size": TS, "sprites": {}, "floors": {}}

    def regm(name, im, group):
        rel = f"{group}/{name}.png"
        save(im, MM / rel)
        mm["sprites"][name] = {"file": rel, "w": im.width, "h": im.height, "group": group}

    regm("wall_top", make_rock_wall(False), "walls")
    regm("wall_face", make_rock_wall(True), "walls")
    regm("ore_cart", make_ore_cart(), "props")
    regm("rails_h", make_rails(), "props")
    regm("drill", make_drill(), "machinery")
    regm("beam", make_beam(), "props")
    regm("ore_pile", make_ore_pile(), "props")
    regm("tnt_crate", make_tnt(), "props")
    regm("lantern", make_lantern(), "decorations")
    regm("pump", make_pump(), "machinery")
    base5, base6 = tile_img(k_tds, 5), tile_img(k_tds, 6)
    floors = {}
    for i in range(4):
        floors[f"dirt_{i}"] = make_dirt_floor(base5 if i % 2 == 0 else base6, 100 + i)
    floors["rock"] = make_dirt_floor(tile_img(k_tds, 8), 200, 0.85)
    floors["mine_dark"] = make_dirt_floor(tile_img(k_tds, 9), 300, 0.62)
    floors["mine_wood"] = tint(tile_img(k_tds, 43), (0.82, 0.74, 0.66))
    floors["mine_metal"] = make_floor_server(tile_img(k_tds, 9))
    floors["mine_hazard"] = make_floor_hazard(tile_img(k_tds, 10))
    for name, im in floors.items():
        save(im, MM / "floor" / f"{name}.png")
        mm["floors"][name] = f"floor/{name}.png"
    (MM / "manifest.json").write_text(json.dumps(mm, indent=1, sort_keys=True))
    print("v2 sprites:", len(manifest["sprites"]), "mining:", len(mm["sprites"]), len(mm["floors"]))


# ---------------------------------------------------------------- v3: open world (The Dead Zone)
def make_tree(seed, dead=False):
    rng = _random.Random(seed)
    if dead:
        cv = Cv(1, 1)
        cv.ell((14, 44, 50, 58), (0, 0, 0, 70))
        cv.line([(32, 54), (32, 30)], (58, 44, 34), 5)
        for _ in range(6):
            x0, y0 = 32, rng.uniform(26, 40)
            ang = rng.uniform(-1.2, 1.2)
            cv.line([(x0, y0), (x0 + 22 * math.sin(ang), y0 - 18 * math.cos(ang))], (74, 58, 44), 3)
        return cv.done()
    cv = Cv(2, 2)
    cv.ell((14, 70, 118, 122), (0, 0, 0, 80))
    cv.rect((56, 72, 72, 110), (70, 48, 30), r=3)
    base = [(30, 70, 40), (38, 86, 46), (48, 100, 54)]
    for layer in range(3):
        for _ in range(7):
            x, y, r = rng.uniform(34, 94), rng.uniform(22 + layer * 6, 70), rng.uniform(18, 28)
            c = base[layer]
            cv.ell((x - r, y - r, x + r, y + r), c)
    for _ in range(14):
        x, y, r = rng.uniform(34, 94), rng.uniform(20, 66), rng.uniform(4, 8)
        cv.ell((x - r, y - r, x + r, y + r), (96, 140, 76))
    return cv.done()


def make_rock(seed, w=1):
    rng = _random.Random(seed)
    cv = Cv(w, 1)
    W = 64 * w
    cv.ell((8, 36, W - 8, 60), (0, 0, 0, 70))
    for _ in range(5):
        x, y, r = rng.uniform(16, W - 16), rng.uniform(26, 42), rng.uniform(11, 18)
        c = rng.randint(92, 132)
        cv.ell((x - r, y - r, x + r, y + r), (c, c - 4, c - 10))
        cv.ell((x - r * 0.6, y - r * 0.8, x + r * 0.1, y - r * 0.1), (c + 28, c + 24, c + 16))
    return cv.done()


def make_wreck():
    cv = Cv(2, 1)
    cv.rect((8, 10, 122, 58), (0, 0, 0, 70), r=8)
    housing(cv, (6, 8, 120, 54), body=(124, 70, 44), edge=(46, 28, 20), r=9)
    cv.rect((78, 14, 112, 48), (60, 76, 86), r=4)
    cv.rect((84, 18, 108, 44), (36, 46, 54), r=3)
    cv.rect((14, 14, 70, 48), (146, 84, 52), r=4)
    for k in range(6):
        cv.line([(20 + k * 8, 18), (26 + k * 8, 44)], (96, 52, 32), 2)
    cv.ell((96, 6, 116, 16), (30, 30, 30))
    cv.ell((12, 44, 32, 56), (30, 30, 30))
    return cv.done()


def make_tent():
    cv = Cv(2, 2)
    cv.rect((14, 22, 118, 118), (0, 0, 0, 60), r=10)
    cv.d.polygon([(64 * S, 12 * S), (116 * S, 108 * S), (12 * S, 108 * S)], fill=(150, 126, 84, 255))
    cv.d.polygon([(64 * S, 12 * S), (116 * S, 108 * S), (64 * S, 108 * S)], fill=(120, 98, 62, 255))
    cv.d.polygon([(64 * S, 54 * S), (84 * S, 108 * S), (44 * S, 108 * S)], fill=(40, 32, 26, 255))
    cv.line([(64, 12), (64, 54)], (90, 70, 44), 3)
    return cv.done()


def make_sandbags():
    cv = Cv(1, 1)
    cv.rect((6, 36, 58, 58), (0, 0, 0, 60), r=6)
    for row in range(2):
        for k in range(3):
            x = 8 + k * 17 + row * 8
            cv.rect((x, 24 + row * 14, x + 18, 36 + row * 14), (160, 140, 96) if (k + row) % 2 else (146, 126, 86), outline=(90, 78, 52), r=5)
    return cv.done()


def make_camp(lit):
    cv = Cv(1, 1)
    cv.ell((8, 12, 56, 60), (0, 0, 0, 70))
    for a in range(0, 360, 45):
        x, y = 32 + 20 * math.cos(math.radians(a)), 34 + 18 * math.sin(math.radians(a))
        cv.ell((x - 6, y - 5, x + 6, y + 5), (96, 94, 90))
    cv.line([(18, 44), (46, 24)], (86, 60, 36), 5)
    cv.line([(18, 24), (46, 44)], (96, 68, 40), 5)
    if lit:
        glow(cv, 32, 34, 30, (255, 150, 50), 130)
        cv.d.polygon([(32 * S, 12 * S), (46 * S, 38 * S), (32 * S, 46 * S), (18 * S, 38 * S)], fill=(255, 130, 30, 255))
        cv.d.polygon([(32 * S, 22 * S), (40 * S, 38 * S), (32 * S, 42 * S), (24 * S, 38 * S)], fill=(255, 220, 90, 255))
    else:
        cv.ell((24, 28, 40, 42), (40, 36, 34))
    return cv.done()


def make_supply():
    cv = Cv(1, 1)
    glow(cv, 32, 36, 30, (255, 220, 90), 100)
    housing(cv, (10, 18, 54, 54), body=(196, 150, 50), edge=(70, 50, 14), r=4)
    cv.rect((10, 32, 54, 40), (60, 44, 20))
    cv.rect((28, 22, 36, 50), (250, 240, 200))
    cv.line([(14, 18), (32, 4), (50, 18)], (240, 240, 240), 2)
    return cv.done()


def make_asphalt(seed):
    rng = _random.Random(seed)
    im = Image.new("RGBA", (64, 64), (60, 62, 66, 255))
    d = ImageDraw.Draw(im)
    for _ in range(70):
        x, y = rng.randint(0, 63), rng.randint(0, 63)
        v = rng.randint(-10, 10)
        d.rectangle([x, y, x + rng.randint(1, 3), y + rng.randint(1, 2)], fill=(60 + v, 62 + v, 66 + v, 255))
    if seed % 3 == 0:
        x = rng.randint(6, 40)
        d.line([(x, 0), (x + rng.randint(-8, 8), 63)], fill=(34, 34, 38, 255), width=1)
    return im


def make_grass(base, seed, dead):
    rng = _random.Random(seed)
    im = tint(base, (0.62, 0.7, 0.5) if not dead else (0.78, 0.72, 0.5))
    d = ImageDraw.Draw(im)
    for _ in range(18):
        x, y = rng.randint(2, 60), rng.randint(2, 60)
        v = rng.randint(-14, 14)
        d.line([(x, y), (x + rng.randint(-2, 2), y - rng.randint(3, 6))], fill=(70 + v, 110 + v, 52 + v, 255) if not dead else (120 + v, 100 + v, 56 + v, 255))
    return im


def make_concrete_wall(face):
    rng = _random.Random(31 if face else 17)
    cv = Cv(1, 1)
    base = (118, 120, 122) if face else (86, 88, 92)
    cv.rect((0, 0, 64, 64), base)
    for _ in range(26):
        x, y, r = rng.uniform(0, 64), rng.uniform(0, 64), rng.uniform(3, 9)
        sh = rng.randint(-12, 12)
        cv.ell((x - r, y - r, x + r, y + r), (base[0] + sh, base[1] + sh, base[2] + sh))
    if face:
        cv.rect((0, 0, 64, 7), (166, 168, 170))
        cv.rect((0, 40, 64, 47), (52, 54, 58))
        cv.rect((0, 47, 64, 64), (74, 76, 80))
        for x in (10, 36, 54):
            cv.line([(x, 8), (x + rng.randint(-2, 2), 38)], (84, 86, 88), 1.4)
        cv.rect((0, 22, 64, 26), (130, 70, 40))
    else:
        for x in (8, 56):
            for y in (8, 56):
                cv.ell((x - 2, y - 2, x + 2, y + 2), (150, 152, 156))
    return cv.done()


def build_v3(asset_root):
    k_tds = asset_root / "kenney_top-down-shooter"
    OW = OUT / "maps" / "open_world"
    mm = {"tile_size": TS, "sprites": {}, "floors": {}}

    def regm(name, im, group):
        rel = f"{group}/{name}.png"
        save(im, OW / rel)
        mm["sprites"][name] = {"file": rel, "w": im.width, "h": im.height, "group": group}

    regm("wall_top", make_concrete_wall(False), "walls")
    regm("wall_face", make_concrete_wall(True), "walls")
    regm("tree_a", make_tree(1), "decorations")
    regm("tree_b", make_tree(2), "decorations")
    regm("dead_tree", make_tree(3, dead=True), "decorations")
    regm("rock_a", make_rock(4), "decorations")
    regm("rock_b", make_rock(5, 2), "decorations")
    regm("car_wreck", make_wreck(), "props")
    regm("tent", make_tent(), "props")
    regm("sandbags", make_sandbags(), "props")
    regm("camp_off", make_camp(False), "terminals")
    regm("camp_on", make_camp(True), "terminals")
    regm("pickup_supply", make_supply(), "props")
    floors = {}
    for i in range(4):
        floors[f"grass_{i}"] = make_grass(tile_img(k_tds, 1 + i), 500 + i, False)
    for i in range(3):
        floors[f"wasteland_{i}"] = make_grass(tile_img(k_tds, 5 + (i % 2)), 600 + i, True)
    for i in range(4):
        floors[f"road_{i}"] = make_asphalt(i)
    floors["concrete"] = tint(tile_img(k_tds, 12), (0.72, 0.74, 0.76))
    floors["ow_wood"] = tint(tile_img(k_tds, 44), (0.8, 0.72, 0.64))
    floors["ow_metal"] = make_floor_server(tile_img(k_tds, 8))
    floors["ow_dark"] = tint(tile_img(k_tds, 9), (0.55, 0.6, 0.65))
    for name, im in floors.items():
        save(im, OW / "floor" / f"{name}.png")
        mm["floors"][name] = f"floor/{name}.png"
    (OW / "manifest.json").write_text(json.dumps(mm, indent=1, sort_keys=True))
    print("open world:", len(mm["sprites"]), len(mm["floors"]))


# ------------------------------------------------------------------ main
def save(im, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


def main(asset_root: Path):
    k_tds = asset_root / "kenney_top-down-shooter"
    manifest = {"tile_size": TS, "sprites": {}, "floors": {}}

    def reg(group, name, im, solid=False, w=None, h=None):
        rel = f"{group}/{name}.png"
        save(im, MAP / rel)
        manifest["sprites"][name] = {"file": rel, "w": im.width, "h": im.height, "group": group}

    # ---- floors (supplied tiles, some tinted)
    floors = {}
    for i, n in enumerate((7, 8, 9, 10, 11)):
        floors[f"teal_{i}"] = tile_img(k_tds, n)
    floors["white"] = tile_img(k_tds, 12)
    for i, n in enumerate((42, 43, 44, 45, 46, 47)):
        floors[f"wood_{i}"] = tile_img(k_tds, n)
    floors["lightwood"] = tile_img(k_tds, 96)
    floors["server"] = make_floor_server(floors["teal_2"])
    floors["hazard"] = make_floor_hazard(floors["teal_3"])
    floors["storage"] = tint(floors["teal_1"], (0.78, 0.78, 0.8))
    floors["dark"] = tint(floors["teal_4"], (0.6, 0.66, 0.72))
    floors["medical"] = tint(floors["white"], (0.93, 1.0, 1.0))
    for name, im in floors.items():
        save(im, MAP / "floor" / f"{name}.png")
        manifest["floors"][name] = f"floor/{name}.png"

    # ---- walls
    reg("walls", "wall_top", make_wall_top())
    reg("walls", "wall_face", make_wall_face())

    # ---- doors
    reg("doors", "door_closed", make_door((200, 210, 218)))
    reg("doors", "door_open", make_door_open())

    # ---- terminals / interactive machinery
    reg("terminals", "terminal_idle", make_terminal((60, 190, 235)))
    reg("terminals", "terminal_read", make_terminal((60, 150, 120)))
    reg("terminals", "terminal_corrupt", make_terminal(RED, corrupt=True))
    reg("terminals", "terminal_dead", make_terminal((0, 0, 0), dead=True))
    reg("terminals", "console_security_idle", make_terminal((255, 176, 32)))
    reg("terminals", "console_security_read", make_terminal((150, 118, 60)))
    reg("terminals", "archive_idle", make_terminal((120, 220, 130)))
    reg("terminals", "archive_read", make_terminal((70, 130, 90)))
    reg("terminals", "medical_idle", make_terminal((200, 245, 250)))
    reg("terminals", "medical_read", make_terminal((120, 150, 150)))
    reg("machinery", "generator_off", make_generator(False))
    reg("machinery", "generator_on", make_generator(True))
    reg("machinery", "signal_core_off", make_core(False))
    reg("machinery", "signal_core_on", make_core(True))
    reg("machinery", "transmitter_off", make_transmitter(False))
    reg("machinery", "transmitter_on", make_transmitter(True))
    reg("machinery", "server_rack_a", make_server(0))
    reg("machinery", "server_rack_b", make_server(1))
    reg("machinery", "server_rack_c", make_server(2))
    reg("machinery", "centrifuge", make_centrifuge())
    reg("machinery", "electrical_panel", make_panel())
    reg("machinery", "battery_bank", make_battery())
    reg("machinery", "holo_table", make_holo())
    reg("machinery", "med_scanner", make_scanner())
    reg("machinery", "pipe_straight", make_pipe("straight"))
    reg("machinery", "pipe_valve", make_pipe("valve"))
    reg("machinery", "pipe_hazard", make_pipe("hazard"))

    # ---- furniture
    reg("furniture", "lab_table_long", make_lab_table(2))
    reg("furniture", "lab_table", make_lab_table(1))
    reg("furniture", "shelf", make_shelf())
    reg("furniture", "filing_cabinet", make_cabinet())
    reg("furniture", "locker", make_locker())
    reg("furniture", "medical_cabinet", make_medcab())
    reg("furniture", "pillar", make_pillar())
    # supplied furniture (Kenney top-down shooter tilesheet)
    reg("furniture", "bed_green_double", sheet_crop(k_tds, 21, 0, 23, 4))
    reg("furniture", "bed_orange_single", sheet_crop(k_tds, 23, 0, 24, 4))
    reg("furniture", "bed_orange_double", sheet_crop(k_tds, 24, 0, 26, 4))
    reg("furniture", "sofa_green", sheet_crop(k_tds, 14, 16, 17, 17))
    reg("furniture", "chair_green", sheet_crop(k_tds, 17, 16, 18, 17))
    reg("furniture", "chair_blue", sheet_crop(k_tds, 18, 16, 19, 17))
    reg("furniture", "desk_wood", sheet_crop(k_tds, 23, 17, 26, 18, trim=False))
    reg("furniture", "table_round", sheet_crop(k_tds, 18, 18, 19, 19))

    # ---- props / decorations
    reg("props", "crate_wood_large", tile_img(k_tds, 129))
    reg("props", "crate_wood_small", tile_img(k_tds, 130))
    reg("props", "crate_wood_b", tile_img(k_tds, 156))
    reg("props", "crate_wood_small_b", tile_img(k_tds, 157))
    reg("props", "crate_metal", make_crate_metal())
    reg("props", "barrel_orange", make_barrel(ORANGE))
    reg("props", "barrel_teal", make_barrel((70, 150, 160)))
    reg("props", "lab_burner", tile_img(k_tds, 297))
    reg("props", "lab_stove", tile_img(k_tds, 294))
    reg("props", "lab_sink", tile_img(k_tds, 323))
    reg("decorations", "bush_green", sheet_crop(k_tds, 18, 6, 20, 8))
    reg("decorations", "bush_orange", sheet_crop(k_tds, 20, 6, 22, 8))
    reg("decorations", "rug_orange", tile_img(k_tds, 346))
    reg("decorations", "rug_green", tile_img(k_tds, 349))

    # ---- characters: side/front-view crew + zombies (Kenney Platformer Characters, 2nd asset root)
    extra_root = Path(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
    ch_out = OUT / "common" / "characters"
    ch_out.mkdir(parents=True, exist_ok=True)
    for old in ch_out.glob("*.png"):
        old.unlink()
    if extra_root and (extra_root / "kenney_platformer-characters").exists():
        pc = extra_root / "kenney_platformer-characters" / "PNG"
        for folder, pre in (("Player", "player"), ("Female", "female"), ("Adventurer", "adventurer"),
                            ("Soldier", "soldier"), ("Zombie", "zombie")):
            for pose in ("stand", "walk1", "walk2", "action1", "hurt", "back"):
                shutil.copy(pc / folder / "Poses" / f"{pre}_{pose}.png", ch_out / f"{pre}_{pose}.png")
        shutil.copy(pc.parent / "License.txt", OUT / "licenses" / "kenney_platformer-characters_License.txt")
    for wn in ("weapon_gun", "weapon_machine", "weapon_silencer"):
        shutil.copy(k_tds / "PNG" / f"{wn}.png", ch_out / f"{wn}.png")

    # ---- UI (supplied Kenney UI pack: space expansion)
    ui = asset_root / "kenney_ui-pack-space-expansion" / "PNG" / "Extra" / "Default"
    for f in ("button_rectangle.png", "button_rectangle_depth.png", "panel_glass.png",
              "panel_rectangle.png", "panel_rectangle_screws.png", "button_square.png"):
        shutil.copy(ui / f, OUT / "common" / "ui" / f)
    for f in ("Kenney Future.ttf", "Kenney Future Narrow.ttf"):
        shutil.copy(asset_root / "kenney_ui-pack-space-expansion" / "Font" / f,
                    OUT / "common" / "fonts" / f.replace(" ", ""))

    # ---- icons (supplied Kenney game icons, white, 1x)
    icons = ["signal1", "signal3"]
    ic_src = asset_root / "kenney_game-icons" / "PNG" / "White" / "1x"
    for ic in icons:
        p = ic_src / f"{ic}.png"
        if p.exists():
            shutil.copy(p, OUT / "common" / "icons" / f"{ic}.png")

    # ---- audio (supplied Kenney interface + sci-fi sounds)
    ia = asset_root / "kenney_interface-sounds" / "Audio"
    sa = asset_root / "kenney_sci-fi-sounds" / "Audio"
    sounds = {
        "click": ia / "click_002.ogg",
        "hover": ia / "tick_002.ogg",
        "back": ia / "back_001.ogg",
        "join_request": ia / "question_002.ogg",
        "player_joined": ia / "confirmation_001.ogg",
        "player_left": ia / "drop_002.ogg",
        "error": ia / "error_004.ogg",
        "success": ia / "confirmation_003.ogg",
        "terminal": sa / "computerNoise_001.ogg",
        "door_open": sa / "doorOpen_001.ogg",
        "door_close": sa / "doorClose_001.ogg",
        "echo": sa / "forceField_002.ogg",
        "echo_glitch": ia / "glitch_002.ogg",
        "transmitter": sa / "spaceEngineLarge_001.ogg",
        "generator": sa / "spaceEngineLow_002.ogg",
        "victory": sa / "laserLarge_003.ogg",
        "victory2": ia / "confirmation_004.ogg",
        "failure": sa / "lowFrequency_explosion_001.ogg",
        "key": ia / "tick_001.ogg",
        "shot": sa / "laserSmall_001.ogg",
        "zombie_hit": sa / "impactMetal_002.ogg",
        "zombie_die": sa / "explosionCrunch_001.ogg",
        "hurt": sa / "impactMetal_000.ogg",
        "reload": sa / "computerNoise_002.ogg",
        "empty": ia / "tick_002.ogg",
        "surge": sa / "lowFrequency_explosion_000.ogg",
    }
    for name, p in sounds.items():
        shutil.copy(p, OUT / "common" / "audio" / f"{name}.ogg")

    # ---- licenses of the packs actually used
    used = ["kenney_top-down-shooter", "kenney_ui-pack-space-expansion", "kenney_game-icons",
            "kenney_particle-pack", "kenney_interface-sounds", "kenney_sci-fi-sounds"]
    for pack in used:
        d = asset_root / pack
        for cand in ("License.txt", "license.txt"):
            if (d / cand).exists():
                shutil.copy(d / cand, OUT / "licenses" / f"{pack}_License.txt")

    # ---- optional second asset root (light masks, key prompts)
    extra = Path(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
    if extra and (extra / "kenney_light-masks-1.0").exists():
        (OUT / "common" / "lighting").mkdir(parents=True, exist_ok=True)
        shutil.copy(extra / "kenney_light-masks-1.0" / "Transparent" / "circle_b.png", OUT / "common" / "lighting" / "light_mask.png")
        shutil.copy(extra / "kenney_light-masks-1.0" / "License.txt", OUT / "licenses" / "kenney_light-masks_License.txt")

    (MAP / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    print("sprites:", len(manifest["sprites"]), "floors:", len(manifest["floors"]))
    build_v2(asset_root, extra)
    build_v3(asset_root)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(Path(sys.argv[1]))
