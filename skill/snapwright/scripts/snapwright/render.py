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
                framing=None, bg=(255, 255, 255, 0), ss=2, fade=None, geom=None, stud_grid=None):
    """G: int grid (x, z, y) of ids (-1 empty). colors[id] -> hex, studs[id] -> bool.
    highlight: set of ids drawn with accent outline. fade: set of ids drawn washed out.
    framing: (shape, W, H) to keep scale fixed across steps (use the full model).
    geom: {id: part dict} for shaped parts (slopes, rounds), in G's frame (so view must be 0;
    use render_parts to rotate). stud_grid: per-cell studs on top, overriding `studs`."""
    if geom and view:
        raise ValueError("render shaped parts with render_parts (rotates the parts, not the grid)")
    G = rotate_grid(G, view)
    geom = geom or {}
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
    if geom:
        # shaped cells don't fill their box: neighbours must draw the faces they'd hide
        shaped = np.isin(G, np.array(sorted(geom), dtype=G.dtype))
        Gs = np.where(shaped, -1, G)
        Gsp = np.pad(Gs, 1, constant_values=-1)

        def nbs(dx, dz, dy):
            return Gsp[1 + dx:1 + dx + NX, 1 + dz:1 + dz + NZ, 1 + dy:1 + dy + NY]
        top_m, fx_m, fz_m = nbs(0, 0, 1) < 0, nbs(1, 0, 0) < 0, nbs(0, 1, 0) < 0
        vis_m = filled & (top_m | fx_m | fz_m | shaped)
    else:
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
    cell_stud = stud_grid[xs, zs, ys].tolist() if stud_grid is not None else None
    for i, (pid, top, fx, fz, s_up, s_dn, s_xm, s_xp, s_zm, s_zp) in enumerate(rows):
        if pid in geom:
            _draw_shaped(d, geom[pid], int(xs[i]), int(zs[i]), int(ys[i]), G, colors[pid],
                         pid in highlight, pid in fade, (s, ox, oy), lw, hw,
                         bool(cell_stud[i]) if cell_stud is not None else False, fx, fz)
            continue
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
        if cell_stud is not None:
            has_stud = cell_stud[i]
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


# ---- shaped parts: slopes, inverted slopes, rounds ---------------------------------------

def _clip(poly, f):
    """Clip a 3-D polygon to the half-space f(p) >= 0 (f affine). Sutherland-Hodgman."""
    out = []
    n = len(poly)
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        fa, fb = f(a), f(b)
        if fa >= 0:
            out.append(a)
        if (fa >= 0) != (fb >= 0):
            t = fa / (fa - fb)
            out.append(tuple(a[m] + t * (b[m] - a[m]) for m in range(3)))
    return out


def _profile(p, u):
    """(bottom, top) of a shaped part at distance u (studs) from its back edge, in plates
    above the part's base."""
    L, h, lip = p["L"], p["h"], p.get("lip", 0.0)
    if p["shape"] == "slope":
        if L == 1:
            return 0.0, h - (h - lip) * min(1.0, max(0.0, u))
        return 0.0, h if u <= 1 else h - (h - lip) * (u - 1) / (L - 1)
    if p["shape"] == "slope_inv":
        return (0.0 if u <= 1 else (h - lip) * (u - 1) / (L - 1)), float(h)
    return 0.0, float(h)


def _u(p, X, Z):
    """Distance (studs) of point (X, Z) from the back edge of a directional part."""
    d = p.get("dir", 0)
    if d == 0:
        return X - p["x"]
    if d == 2:
        return p["x"] + p["dx"] - X
    if d == 1:
        return Z - p["z"]
    return p["z"] + p["dz"] - Z


def _draw_shaped(d, p, x, z, y, G, color, hi, faded, frame, lw, hw, stud, open_x, open_z):
    """Draw one cell of a slope, inverted slope or round part: the cell box clipped by the
    part's surface, lit like the boxes, outlined only on the part's boundary."""
    s, ox, oy = frame
    base = hex_to_rgb(color)
    if faded:
        base = _lift(base, 0.72)
    ec = ACCENT if hi else _edge_col(base)
    ew = hw if hi else lw
    k = y - p["y"]                                      # this cell's plate within the part
    NX, NZ, NY = G.shape
    pid = G[x, z, y]

    def P(q):
        u, v = proj(q[0] * STUD_MM, q[1] * PLATE_MM, q[2] * STUD_MM)
        return (ox + s * u, oy + s * v)

    def same(a, b, c):
        return 0 <= a < NX and 0 <= b < NZ and 0 <= c < NY and G[a, b, c] == pid

    def outline(poly, internal):
        n = len(poly)
        for m in range(n):
            a, b = poly[m], poly[(m + 1) % n]
            if not internal(a, b):
                d.line([P(a), P(b)], fill=ec, width=ew)

    def on(a, b, axis, val):
        return abs(a[axis] - val) < 1e-6 and abs(b[axis] - val) < 1e-6

    def internal(a, b):
        """Edge lies on a face shared with another cell of the same part."""
        return ((on(a, b, 0, x) and same(x - 1, z, y)) or (on(a, b, 0, x + 1) and same(x + 1, z, y))
                or (on(a, b, 2, z) and same(x, z - 1, y)) or (on(a, b, 2, z + 1) and same(x, z + 1, y))
                or (on(a, b, 1, y) and same(x, z, y - 1)) or (on(a, b, 1, y + 1) and same(x, z, y + 1)))

    if p["shape"] == "round":
        _draw_round_cell(d, p, x, z, y, k, base, ec, ew, P, stud, s, lw)
        return
    top_f = lambda q: (p["y"] + _profile(p, _u(p, q[0], q[2]))[1]) - q[1]    # noqa: E731
    bot_f = lambda q: q[1] - (p["y"] + _profile(p, _u(p, q[0], q[2]))[0])    # noqa: E731
    slab = (lambda q: q[1] - y, lambda q: (y + 1) - q[1])

    def solid(poly):
        for f in (top_f, bot_f):
            poly = _clip(poly, f)
            if len(poly) < 3:
                return []
        return poly

    if open_z:                                           # +z side face
        q = solid([(x, y, z + 1), (x + 1, y, z + 1), (x + 1, y + 1, z + 1), (x, y + 1, z + 1)])
        if q:
            d.polygon([P(c) for c in q], fill=_shade(base, 0.62))
            outline(q, internal)
    if open_x:                                           # +x side face
        q = solid([(x + 1, y, z), (x + 1, y, z + 1), (x + 1, y + 1, z + 1), (x + 1, y + 1, z)])
        if q:
            d.polygon([P(c) for c in q], fill=_shade(base, 0.8))
            outline(q, internal)
    # the top surface over this cell, cut to this cell's plate
    corners = [(x, z), (x + 1, z), (x + 1, z + 1), (x, z + 1)]
    q = [(cx, p["y"] + _profile(p, _u(p, cx, cz))[1], cz) for cx, cz in corners]
    flat = max(c[1] for c in q) - min(c[1] for c in q) < 1e-6
    for f in slab:
        q = _clip(q, f)
        if len(q) < 3:
            return
    if flat and abs(q[0][1] - (y + 1)) > 1e-6:
        return                                           # flat top belongs to a higher cell
    if flat and same(x, z, y + 1):
        return
    light = 0.12 if flat else 0.04
    d.polygon([P(c) for c in q], fill=_lift(base, light))
    outline(q, lambda a, b: internal(a, b) and not (flat is False and on(a, b, 1, y + 1)))
    if stud and flat:
        cx, cy = P((x + 0.5, y + 1, z + 0.5))
        rx, ry, hh = STUD_R * s, STUD_R * s * SE, STUD_H * s * CE
        d.rectangle([cx - rx, cy - hh, cx + rx, cy], fill=_shade(base, 0.72))
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=_shade(base, 0.72))
        d.ellipse([cx - rx, cy - hh - ry, cx + rx, cy - hh + ry], fill=_lift(base, 0.22),
                  outline=ec, width=max(1, ew - 1))


def _draw_round_cell(d, p, x, z, y, k, base, ec, ew, P, stud, s, lw):
    """One cell of a round part: the part of its cylinder inside this cell's quadrant."""
    cx, cz = p["x"] + p["dx"] / 2, p["z"] + p["dz"] / 2
    r = min(p["dx"], p["dz"]) / 2 * 0.98
    # angles of the circle that fall in this cell
    lo_x, hi_x, lo_z, hi_z = x, x + 1, z, z + 1
    angs = [a for a in np.linspace(0, 2 * math.pi, 73)[:-1]
            if lo_x - 1e-9 <= cx + r * math.cos(a) <= hi_x + 1e-9 and lo_z - 1e-9 <= cz + r * math.sin(a) <= hi_z + 1e-9]
    if not angs:
        return
    # sort along the arc (handle wrap-around at 0)
    angs.sort()
    gaps = [(angs[(m + 1) % len(angs)] - angs[m]) % (2 * math.pi) for m in range(len(angs))]
    start = (gaps.index(max(gaps)) + 1) % len(angs)
    angs = angs[start:] + angs[:start]
    y0, y1 = y, y + 1
    # side: only the half facing the camera (+x, +z)
    vis = [a for a in angs if math.cos(a) + math.sin(a) > -1e-9]
    if len(vis) >= 2:
        topa = [(cx + r * math.cos(a), y1, cz + r * math.sin(a)) for a in vis]
        bota = [(cx + r * math.cos(a), y0, cz + r * math.sin(a)) for a in reversed(vis)]
        d.polygon([P(c) for c in topa + bota], fill=_shade(base, 0.72))
        d.line([P(c) for c in bota], fill=ec, width=ew) if k == 0 else None
    if k == p["h"] - 1:
        whole = len(angs) >= 70
        pts = [(cx + r * math.cos(a), y1, cz + r * math.sin(a)) for a in angs]
        poly = pts if whole else [(cx, y1, cz)] + pts if (x <= cx <= x + 1 and z <= cz <= z + 1) else \
            [(min(max(cx, x), x + 1), y1, min(max(cz, z), z + 1))] + pts
        d.polygon([P(c) for c in poly], fill=_lift(base, 0.12))
        d.line([P(c) for c in pts] + ([P(pts[0])] if whole else []), fill=ec, width=ew)
        if stud:
            sx, sy = P((x + 0.5, y1, z + 0.5))
            rx, ry, hh = STUD_R * s, STUD_R * s * SE, STUD_H * s * CE
            d.rectangle([sx - rx, sy - hh, sx + rx, sy], fill=_shade(base, 0.72))
            d.ellipse([sx - rx, sy - ry, sx + rx, sy + ry], fill=_shade(base, 0.72))
            d.ellipse([sx - rx, sy - hh - ry, sx + rx, sy - hh + ry], fill=_lift(base, 0.22),
                      outline=ec, width=max(1, lw - 1))


def rotate_parts(parts, shape, k):
    """Parts as seen after rotate_grid(G, k): footprints, directions and connector cells move
    with the grid. Returns (new parts, new shape)."""
    k %= 4
    NX, NZ, NY = shape
    if k == 0:
        return parts, shape

    def cell(x, z):
        if k == 1:
            return z, NX - 1 - x
        if k == 2:
            return NX - 1 - x, NZ - 1 - z
        return NZ - 1 - z, x
    out = []
    for p in parts:
        q = dict(p)
        xs = [cell(p["x"], p["z"]), cell(p["x"] + p["dx"] - 1, p["z"] + p["dz"] - 1)]
        q["x"], q["z"] = min(a for a, _ in xs), min(b for _, b in xs)
        if k % 2:
            q["dx"], q["dz"] = p["dz"], p["dx"]
        if "dir" in p:
            q["dir"] = (p["dir"] - k) % 4
        for key in ("top_cells", "bottom_cells"):
            if key in p:
                q[key] = [list(cell(a, b)) for a, b in p[key]]
        out.append(q)
    return out, ((NZ, NX, NY) if k % 2 else shape)


def stud_grid_of(parts, shape):
    g = np.zeros(shape, dtype=bool)
    for p in parts:
        top = p["y"] + p["h"] - 1
        if "top_cells" in p:
            for a, b in p["top_cells"]:
                g[a, b, top] = True
        elif p.get("studs"):
            g[p["x"]:p["x"] + p["dx"], p["z"]:p["z"] + p["dz"], top] = True
    return g


def render_parts(parts, shape, colors, catalog=None, view=0, **kw):
    """Render a list of part dicts (any shapes) from quarter view `view`. colors: {id: hex}."""
    rp, rshape = rotate_parts(parts, shape, view)
    G = model_grid(rp, rshape)
    geom = {}
    for p in rp:
        if p.get("shape", "box") != "box":
            q = dict(p)
            if catalog is not None:
                t = catalog.by_id[p["part"]]
                q.update(L=t.L, lip=t.lip)
            else:
                q.update(L=max(p["dx"], p["dz"]) if p["shape"] != "round" else 1, lip=0.5)
            geom[p["id"]] = q
    framing = kw.pop("framing", None)
    if framing is not None and view % 2:
        framing = (framing[1], framing[0], framing[2])
    return render_grid(G, colors, {}, geom=geom, stud_grid=stud_grid_of(rp, rshape),
                       framing=framing, view=0, **kw)


def visible_samples(G, view=0, spp=4):
    """How much of each part the camera sees in `view`, as a count of face samples that win
    the depth test (a coarse id-buffer, same camera as render_grid). Returns {pid: count}."""
    G = rotate_grid(G, view)
    NX, NZ, NY = G.shape
    if not (G >= 0).any():
        return {}
    Gp = np.pad(G, 1, constant_values=-1)

    def nb(dx, dz, dy):
        return Gp[1 + dx:1 + dx + NX, 1 + dz:1 + dz + NZ, 1 + dy:1 + dy + NY]

    filled = G >= 0
    t = (np.arange(spp) + 0.5) / spp
    a, b = [m.ravel() for m in np.meshgrid(t, t, indexing="ij")]
    pts, ids = [], []
    for mask, fn in (
            (filled & (nb(0, 0, 1) < 0), lambda x, z, y: (x + a, y + 1 + 0 * a, z + b)),   # top
            (filled & (nb(1, 0, 0) < 0), lambda x, z, y: (x + 1 + 0 * a, y + b, z + a)),   # +x side
            (filled & (nb(0, 1, 0) < 0), lambda x, z, y: (x + a, y + b, z + 1 + 0 * a))):  # +z side
        xs, zs, ys = np.nonzero(mask)
        if not len(xs):
            continue
        X, Y, Z = fn(xs[:, None], zs[:, None], ys[:, None])
        pts.append((X.ravel() * STUD_MM, Y.ravel() * PLATE_MM, Z.ravel() * STUD_MM))
        ids.append(np.repeat(G[xs, zs, ys], spp * spp))
    X = np.concatenate([p[0] for p in pts])
    Y = np.concatenate([p[1] for p in pts])
    Z = np.concatenate([p[2] for p in pts])
    pid = np.concatenate(ids)
    u, v = proj(X, Y, Z)
    px = STUD_MM * C45 / (spp - 1)          # a bit coarser than the sample spacing: no holes
    iu = np.floor(u / px).astype(np.int64)
    iv = np.floor(v / px).astype(np.int64)
    key = (iu - iu.min()) * (iv.max() - iv.min() + 1) + (iv - iv.min())
    depth = X * DIR[0] + Y * DIR[1] + Z * DIR[2]  # larger = nearer the camera
    order = np.lexsort((depth, key))
    last = np.ones(len(order), dtype=bool)
    last[:-1] = key[order][1:] != key[order][:-1]
    win = pid[order][last]
    vals, cnt = np.unique(win, return_counts=True)
    return dict(zip(vals.tolist(), cnt.tolist()))


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
    """A single part, drawn as it looks (slopes face the viewer)."""
    from .catalog import place_cells
    dir_ = 1 if ptype.shape in ("slope", "slope_inv") else 0
    if ptype.shape in ("slope", "slope_inv"):
        dx, dz, cell = place_cells(ptype, 0, 0, dir_)
        cells = {(i, j): cell(i, j) for i in range(ptype.L) for j in range(ptype.W)}
        p = {"id": 0, "part": ptype.id, "x": 0, "z": 0, "y": 0, "dx": dx, "dz": dz, "h": ptype.h,
             "shape": ptype.shape, "dir": dir_, "studs": ptype.studs,
             "top_cells": [list(cells[c]) for c in sorted(ptype.local_cells("top"))],
             "bottom_cells": [list(cells[c]) for c in sorted(ptype.local_cells("bottom"))]}
    else:
        p = {"id": 0, "part": ptype.id, "x": 0, "z": 0, "y": 0, "dx": ptype.L, "dz": ptype.W,
             "h": ptype.h, "shape": ptype.shape, "studs": ptype.studs}
    geom_p = dict(p, L=ptype.L, lip=ptype.lip)
    G = model_grid([p], (p["dx"], p["dz"], p["h"]))
    geom = {0: geom_p} if ptype.shape != "box" else None
    return render_grid(G, {0: color_hex}, {0: ptype.studs}, size=size, ss=3, geom=geom,
                       stud_grid=stud_grid_of([p], G.shape))


def voxel_preview(V, palette, catalog, size=(900, 900), view=0):
    G = V.astype(np.int32) - 1
    colors = {i: catalog.colors[c]["hex"] for i, c in enumerate(palette)}
    studs = {i: True for i in range(len(palette))}
    return render_grid(G, colors, studs, size=size, view=view)
