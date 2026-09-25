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

    if not (G >= 0).any():
        return img.resize((W, H), Image.LANCZOS)
    # neighbour lookups on a padded grid (-1 = empty), all vectorised
    Gp = np.pad(G, 1, constant_values=-1)

    def nb(dx, dz, dy):
        return Gp[1 + dx:1 + dx + NX, 1 + dz:1 + dz + NZ, 1 + dy:1 + dy + NY]

    filled = G >= 0
    top_m, fx_m, fz_m = nb(0, 0, 1) < 0, nb(1, 0, 0) < 0, nb(0, 1, 0) < 0
    vis_m = filled & (top_m | fx_m | fz_m)
    xs, zs, ys = np.nonzero(vis_m)
    depth = ((xs + .5) * STUD_MM * DIR[0] + (ys + .5) * PLATE_MM * DIR[1] + (zs + .5) * STUD_MM * DIR[2])
    order = np.lexsort((ys, zs, xs, depth))            # back to front, ties as before
    xs, zs, ys = xs[order], zs[order], ys[order]
    pid_a = G[xs, zs, ys]
    same = {k: (nb(*k)[xs, zs, ys] == pid_a) for k in
            ((0, 0, 1), (0, 0, -1), (-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0))}
    flags = [top_m[xs, zs, ys], fx_m[xs, zs, ys], fz_m[xs, zs, ys]] + [same[k] for k in (
        (0, 0, 1), (0, 0, -1), (-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0))]
    X0, Z0, Y0 = xs * STUD_MM, zs * STUD_MM, ys * PLATE_MM
    X1, Z1, Y1 = X0 + STUD_MM, Z0 + STUD_MM, Y0 + PLATE_MM

    def Pv(X, Y, Z):
        u, v = proj(X, Y, Z)
        return list(zip((ox + s * u).tolist(), (oy + s * v).tolist()))

    p001, p101, p111, p011 = Pv(X0, Y0, Z1), Pv(X1, Y0, Z1), Pv(X1, Y1, Z1), Pv(X0, Y1, Z1)
    p100, p110, p010 = Pv(X1, Y0, Z0), Pv(X1, Y1, Z0), Pv(X0, Y1, Z0)
    stud = Pv(X0 + 4, Y1, Z0 + 4)
    lw = max(1, int(round(s * 0.35)))
    hw = max(2, int(round(s * 0.9)))
    rx, ry, hh = STUD_R * s, STUD_R * s * SE, STUD_H * s * CE
    fcache = {}
    rows = zip(pid_a.tolist(), *[f.tolist() for f in flags])
    for i, (pid, top, fx, fz, s_up, s_dn, s_xm, s_xp, s_zm, s_zp) in enumerate(rows):
        if pid not in fcache:
            base = hex_to_rgb(colors[pid])
            if pid in fade:
                base = _lift(base, 0.72)
            hi = pid in highlight
            fcache[pid] = (base, ACCENT if hi else _edge_col(base), hw if hi else lw, _shade(base, 0.62),
                           _shade(base, 0.8), _lift(base, 0.12), _shade(base, 0.72), _lift(base, 0.22),
                           ACCENT if hi else _edge_col(base), max(1, lw if hi else lw - 1),
                           studs.get(pid, True) if isinstance(studs, dict) else studs[pid])
        base, ec, ew, c_fz, c_fx, c_top, c_sd, c_sl, s_ec, s_w, has_stud = fcache[pid]
        if fz:
            q = [p001[i], p101[i], p111[i], p011[i]]
            d.polygon(q, fill=c_fz)
            if not s_up: d.line([q[3], q[2]], fill=ec, width=ew)
            if not s_dn: d.line([q[0], q[1]], fill=ec, width=ew)
            if not s_xm: d.line([q[0], q[3]], fill=ec, width=ew)
            if not s_xp: d.line([q[1], q[2]], fill=ec, width=ew)
        if fx:
            q = [p100[i], p101[i], p111[i], p110[i]]
            d.polygon(q, fill=c_fx)
            if not s_up: d.line([q[3], q[2]], fill=ec, width=ew)
            if not s_dn: d.line([q[0], q[1]], fill=ec, width=ew)
            if not s_zm: d.line([q[0], q[3]], fill=ec, width=ew)
            if not s_zp: d.line([q[1], q[2]], fill=ec, width=ew)
        if top:
            q = [p010[i], p110[i], p111[i], p011[i]]
            d.polygon(q, fill=c_top)
            if not s_zm: d.line([q[0], q[1]], fill=ec, width=ew)
            if not s_xp: d.line([q[1], q[2]], fill=ec, width=ew)
            if not s_zp: d.line([q[2], q[3]], fill=ec, width=ew)
            if not s_xm: d.line([q[3], q[0]], fill=ec, width=ew)
            if has_stud:
                cx, cy = stud[i]
                d.rectangle([cx - rx, cy - hh, cx + rx, cy], fill=c_sd)
                d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=c_sd)
                d.ellipse([cx - rx, cy - hh - ry, cx + rx, cy - hh + ry], fill=c_sl, outline=s_ec, width=s_w)
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
