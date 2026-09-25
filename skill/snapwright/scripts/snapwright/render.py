"""Isometric renderer (Pillow only, no GPU, runs in any sandbox).

Draws the model cell by cell (1 stud x 1 stud x 1 plate), back to front, only the faces
that can be seen, with outlines only on part boundaries so each part reads as one piece.
New parts in a step get an accent outline.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from .catalog import hex_to_rgb

STUD_MM, PLATE_MM = 8.0, 3.2
EL = math.radians(30)
C45 = math.cos(math.radians(45))
SE, CE = math.sin(EL), math.cos(EL)
DIR = np.array([C45 * CE, SE, C45 * CE])  # towards the camera (x, y, z)
STUD_R, STUD_H = 2.4, 1.8
ACCENT = (255, 70, 40)


def proj(X, Y, Z):
    return ((X - Z) * C45, (X + Z) * C45 * SE - Y * CE)


def rotate_grid(G, k):
    k %= 4
    if k == 0:
        return G
    if k == 1:
        return np.flip(G, 0).transpose(1, 0, 2)
    if k == 2:
        return np.flip(np.flip(G, 0), 1)
    return np.flip(G, 1).transpose(1, 0, 2)


def _shade(rgb, f):
    return tuple(max(0, min(255, int(c * f))) for c in rgb)


def _lift(rgb, f):
    return tuple(int(c + (255 - c) * f) for c in rgb)


def _edge_col(rgb):
    lum = 0.3 * rgb[0] + 0.59 * rgb[1] + 0.11 * rgb[2]
    return (120, 120, 120) if lum < 60 else _shade(rgb, 0.45)


def fit(shape, W, H, pad=0.06):
    NX, NZ, NY = shape
    xs, ys = [], []
    for X in (0, NX * STUD_MM):
        for Z in (0, NZ * STUD_MM):
            for Y in (0, NY * PLATE_MM + STUD_H):
                u, v = proj(X, Y, Z)
                xs.append(u)
                ys.append(v)
    du, dv = max(xs) - min(xs), max(ys) - min(ys)
    s = min(W * (1 - 2 * pad) / max(du, 1e-6), H * (1 - 2 * pad) / max(dv, 1e-6))
    ox = W / 2 - s * (max(xs) + min(xs)) / 2
    oy = H / 2 - s * (max(ys) + min(ys)) / 2
    return s, ox, oy


def render_grid(G, colors, studs, highlight=None, ghost=None, size=(900, 900), view=0,
                framing=None, bg=(255, 255, 255, 0), ss=2, fade=None):
    """G: int grid (x, z, y) of ids (-1 empty). colors[id] -> hex, studs[id] -> bool.
    highlight: set of ids drawn with accent outline. fade: set of ids drawn washed out.
    framing: (shape, W, H) to keep scale fixed across steps (use the full model)."""
    G = rotate_grid(G, view)
    NX, NZ, NY = G.shape
    W, H = size
    Ws, Hs = W * ss, H * ss
    fshape = framing if framing is not None else G.shape
    if framing is not None and view % 2 == 1:
        fshape = (framing[1], framing[0], framing[2])
    s, ox, oy = fit(fshape, Ws, Hs)
    # centre the model's footprint in the frame when framing is larger than G
    img = Image.new("RGBA", (Ws, Hs), bg)
    d = ImageDraw.Draw(img)
    highlight = highlight or set()
    fade = fade or set()
    rgbc = {}

    def P(X, Y, Z):
        u, v = proj(X, Y, Z)
        return (ox + s * u, oy + s * v)

    filled = np.argwhere(G >= 0)
    if not len(filled):
        return img.resize((W, H), Image.LANCZOS)
    # visibility culling
    def empty(x, z, y):
        return x >= NX or z >= NZ or y >= NY or x < 0 or z < 0 or y < 0 or G[x, z, y] < 0

    vis = []
    for x, z, y in filled:
        top = empty(x, z, y + 1)
        fx = empty(x + 1, z, y)
        fz = empty(x, z + 1, y)
        if top or fx or fz:
            c = np.array([(x + .5) * STUD_MM, (y + .5) * PLATE_MM, (z + .5) * STUD_MM])
            vis.append((float(c @ DIR), x, z, y, top, fx, fz))
    vis.sort()
    lw = max(1, int(round(s * 0.35)))
    hw = max(2, int(round(s * 0.9)))

    def same(pid, x, z, y):
        return not empty(x, z, y) and G[x, z, y] == pid

    for _, x, z, y, top, fx, fz in vis:
        pid = int(G[x, z, y])
        if pid not in rgbc:
            base = hex_to_rgb(colors[pid])
            if pid in fade:
                base = _lift(base, 0.72)
            rgbc[pid] = base
        base = rgbc[pid]
        ec = ACCENT if pid in highlight else _edge_col(base)
        ew = hw if pid in highlight else lw
        X0, X1 = x * STUD_MM, (x + 1) * STUD_MM
        Z0, Z1 = z * STUD_MM, (z + 1) * STUD_MM
        Y0, Y1 = y * PLATE_MM, (y + 1) * PLATE_MM
        if fz:
            q = [P(X0, Y0, Z1), P(X1, Y0, Z1), P(X1, Y1, Z1), P(X0, Y1, Z1)]
            d.polygon(q, fill=_shade(base, 0.62))
            if not same(pid, x, z, y + 1): d.line([q[3], q[2]], fill=ec, width=ew)
            if not same(pid, x, z, y - 1): d.line([q[0], q[1]], fill=ec, width=ew)
            if not same(pid, x - 1, z, y): d.line([q[0], q[3]], fill=ec, width=ew)
            if not same(pid, x + 1, z, y): d.line([q[1], q[2]], fill=ec, width=ew)
        if fx:
            q = [P(X1, Y0, Z0), P(X1, Y0, Z1), P(X1, Y1, Z1), P(X1, Y1, Z0)]
            d.polygon(q, fill=_shade(base, 0.8))
            if not same(pid, x, z, y + 1): d.line([q[3], q[2]], fill=ec, width=ew)
            if not same(pid, x, z, y - 1): d.line([q[0], q[1]], fill=ec, width=ew)
            if not same(pid, x, z - 1, y): d.line([q[0], q[3]], fill=ec, width=ew)
            if not same(pid, x, z + 1, y): d.line([q[1], q[2]], fill=ec, width=ew)
        if top:
            q = [P(X0, Y1, Z0), P(X1, Y1, Z0), P(X1, Y1, Z1), P(X0, Y1, Z1)]
            d.polygon(q, fill=_lift(base, 0.12))
            if not same(pid, x, z - 1, y): d.line([q[0], q[1]], fill=ec, width=ew)
            if not same(pid, x + 1, z, y): d.line([q[1], q[2]], fill=ec, width=ew)
            if not same(pid, x, z + 1, y): d.line([q[2], q[3]], fill=ec, width=ew)
            if not same(pid, x - 1, z, y): d.line([q[3], q[0]], fill=ec, width=ew)
            if studs.get(pid, True) if isinstance(studs, dict) else studs[pid]:
                cx, cy = P(X0 + 4, Y1, Z0 + 4)
                rx, ry = STUD_R * s, STUD_R * s * SE
                hh = STUD_H * s * CE
                d.rectangle([cx - rx, cy - hh, cx + rx, cy], fill=_shade(base, 0.72))
                d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=_shade(base, 0.72))
                d.ellipse([cx - rx, cy - hh - ry, cx + rx, cy - hh + ry], fill=_lift(base, 0.22),
                          outline=_edge_col(base) if pid not in highlight else ACCENT,
                          width=max(1, lw - 1 if pid not in highlight else lw))
    return img.resize((W, H), Image.LANCZOS)


# ---- helpers used by the book / CLI ---------------------------------------

def model_grid(parts, shape, upto_step=None, only=None):
    G = -np.ones(shape, dtype=np.int32)
    for p in parts:
        if only is not None and p["id"] not in only:
            continue
        if upto_step is not None and p.get("step", 0) > upto_step:
            continue
        G[p["x"]:p["x"] + p["dx"], p["z"]:p["z"] + p["dz"], p["y"]:p["y"] + p["h"]] = p["id"]
    return G


def part_icon(ptype, color_hex, size=(140, 110)):
    L, W, h = ptype.L, ptype.W, ptype.h
    G = np.zeros((L, W, h), dtype=np.int32)
    return render_grid(G, {0: color_hex}, {0: ptype.studs}, size=size, ss=3)


def voxel_preview(V, palette, catalog, size=(900, 900), view=0):
    G = V.astype(np.int32) - 1
    colors = {i: catalog.colors[c]["hex"] for i, c in enumerate(palette)}
    studs = {i: True for i in range(len(palette))}
    return render_grid(G, colors, studs, size=size, view=view)
