#!/usr/bin/env python3
"""Dev-only: check an exported .ldr against the official LDraw part geometry.

For every part line, resolve the real part (subparts and primitives) from an LDraw library
folder, transform it, and check that
  * its bounding box (without studs) matches the grid box model.json says it occupies, and
  * for slopes, the sloped face points the way the part's `dir` says (inverted slopes: the
    chamfer underneath faces that way).
Then render the model from the official triangles to a PNG, as an independent picture of
what LDraw editors (LeoCAD, Studio, ...) will show.

  python tools/ldraw_check.py OUT/model.json OUT/model.ldr --lib PATH/ldraw --png check.png

Needs the LDraw library (https://library.ldraw.org/library/updates/complete.zip). Not part
of the skill: it is a development check for the exporter.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skill", "snapwright", "scripts"))

from snapwright.catalog import Catalog  # noqa: E402

_cache = {}
_inline = {}          # submodels from the checked file itself (MPD)


def load(lib, name):
    name = name.replace("\\", "/").lower()
    if name in _inline:
        return _inline[name]
    if name in _cache:
        return _cache[name]
    for sub in ("parts", "p", "p/48", "models"):
        f = os.path.join(lib, sub, name)
        if os.path.exists(f):
            _cache[name] = open(f, errors="ignore").read().splitlines()
            return _cache[name]
    _cache[name] = []
    return []


def triangles(lib, name, M=np.eye(3), o=np.zeros(3), depth=0, out=None, stud=False):
    """World triangles of an LDraw file: list of (3x3 array, is_stud)."""
    out = [] if out is None else out
    for line in load(lib, name):
        t = line.split()
        if not t:
            continue
        if t[0] == "1" and len(t) >= 15 and depth < 12:
            p = np.array([float(a) for a in t[2:5]])
            R = np.array([float(a) for a in t[5:14]]).reshape(3, 3)
            sub = t[14].lower()
            triangles(lib, sub, M @ R, o + M @ p, depth + 1, out, stud or sub.startswith("stud"))
        elif t[0] in ("3", "4"):
            n = int(t[0])
            v = np.array([float(a) for a in t[2:2 + 3 * n]]).reshape(n, 3)
            v = (M @ v.T).T + o
            out.append((v[[0, 1, 2]], stud))
            if n == 4:
                out.append((v[[0, 2, 3]], stud))
    return out


DIRS_LDRAW = {0: (1, 0), 1: (0, -1), 2: (-1, 0), 3: (0, 1)}   # our +x, +z, -x, -z in LDraw (X, Z)


def _body_box(tris):
    body = np.concatenate([tri for tri, s in tris if not s])
    return body.min(0), body.max(0)


def _slope_problem(p, t, tris, pid):
    want = DIRS_LDRAW[p["dir"]]
    area = {}
    for tri, s in tris:
        if s:
            continue
        n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        a = np.linalg.norm(n) / 2
        if a == 0:
            continue
        n = n / (2 * a)
        hz = math.hypot(n[0], n[2])
        if hz < 0.3 or abs(n[1]) < 0.3:
            continue
        key = (round(n[0] / hz), round(n[2] / hz), n[1] < 0)      # -Y is up in LDraw
        area[key] = area.get(key, 0) + a
    # LDraw winding isn't always outward: take the slanted plane with the most area and orient
    # it outward (up-facing for slopes, down-facing for inverted slopes)
    if area:
        (ax, az, up_), _ = max(area.items(), key=lambda kv: kv[1])
        if up_ != (t.shape == "slope"):
            ax, az = -ax, -az
        if (ax, az) != want:
            return (f"part {pid} {p['part']} dir {p['dir']}: sloped face points {(ax, az)} in LDraw, "
                    f"expected {want}")
    return None


def _corner_problem(p, t, tris, pid):
    """A corner slope's two largest slanted faces (up-facing) point along its dir and dir + 1."""
    want = {DIRS_LDRAW[p["dir"]], DIRS_LDRAW[(p["dir"] + 1) % 4]}
    area = {}
    for tri, s in tris:
        if s:
            continue
        n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        a = np.linalg.norm(n) / 2
        if a == 0:
            continue
        n = n / (2 * a)
        if n[1] > 0:                                          # make it up-facing (-Y is up)
            n = -n
        hz = math.hypot(n[0], n[2])
        if hz < 0.3 or abs(n[1]) < 0.3:
            continue
        key = (round(n[0] / hz), round(n[2] / hz))
        area[key] = area.get(key, 0) + a
    got = {k for k, _ in sorted(area.items(), key=lambda kv: -kv[1])[:2]}
    if got != want:
        return f"part {pid} {p['part']} dir {p['dir']}: slanted faces point {sorted(got)} in LDraw, expected {sorted(want)}"
    return None


def check(model, ldr_text, lib, cat):
    from snapwright.exporters import split_mpd
    from snapwright.snot import PanelSpec, part_world_box
    parts = model["parts"]
    files = split_mpd(ldr_text)
    main = ldr_text if None in files else next(iter(files.values()))
    _inline.clear()
    _inline.update({k.lower(): v.splitlines() for k, v in files.items() if k})
    lines = [l.split() for l in main.splitlines() if l.startswith("1 ")]
    subref = [f for f in lines if f[14].lower() in _inline]
    lines = [f for f in lines if f[14].lower() not in _inline]
    order = [pid for st in model["steps"] if not st.get("sub") for pid in st["parts"]]
    assert len(lines) == len(order), "line count differs from part count"
    problems, tris_all = [], []
    for pid, f in zip(order, lines):
        p = parts[pid]
        t = cat.by_id[p["part"]]
        o = np.array([float(a) for a in f[2:5]])
        R = np.array([float(a) for a in f[5:14]]).reshape(3, 3)
        tris = triangles(lib, f[14], R, o)
        if not tris:
            problems.append(f"{p['part']}: {f[14]} not found in the library")
            continue
        lo, hi = _body_box(tris)
        got = {"x": lo[0] / 20, "dx": (hi[0] - lo[0]) / 20, "z": -hi[2] / 20, "dz": (hi[2] - lo[2]) / 20,
               "y": -hi[1] / 8, "h": (hi[1] - lo[1]) / 8}
        for k in ("x", "z", "y", "dx", "dz", "h"):
            if abs(got[k] - p[k]) > 0.15:
                problems.append(f"part {pid} {p['part']} dir {p.get('dir')}: {k} is {got[k]:.2f} in LDraw, "
                                f"{p[k]} in the model")
                break
        if t.shape in ("slope_cvx", "slope_ccv"):
            bad = _corner_problem(p, t, tris, pid)
            if bad:
                problems.append(bad)
        elif t.shape in ("slope", "slope_inv"):
            bad = _slope_problem(p, t, tris, pid)
            if bad:
                problems.append(bad)
        col = model["colors"][p["color"]]["hex"]
        tris_all += [(tri, col) for tri, _ in tris]
    # sideways panels: each part, placed through the submodel reference, must land on its
    # world box
    subs = {sb["name"]: sb for sb in model.get("subassemblies", [])}
    by_file = {}
    for name, sb in subs.items():
        import re
        by_file[f"{model['meta']['slug']}-{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')}.ldr"] = sb
    for f in subref:
        sb = by_file[f[14].lower()]
        spec = PanelSpec.from_json(sb["spec"])
        T = np.array([float(a) for a in f[2:5]])
        Pm = np.array([float(a) for a in f[5:14]]).reshape(3, 3)
        order = [pid for st in model["steps"] if st.get("kind") == "subassembly" and st["sub"] == sb["name"]
                 for pid in st["parts"]]
        sl = [l.split() for l in _inline[f[14].lower()] if l.startswith("1 ")]
        assert len(sl) == len(order), f"panel {sb['name']}: line count differs"
        for pid, g in zip(order, sl):
            q = sb["parts"][pid]
            o = T + Pm @ np.array([float(a) for a in g[2:5]])
            R = Pm @ np.array([float(a) for a in g[5:14]]).reshape(3, 3)
            tris = triangles(lib, g[14], R, o)
            lo, hi = _body_box(tris)
            wlo, whi = part_world_box(spec, q)          # mm -> LDraw: X = x/0.4, Y = -y/0.4, Z = -z/0.4
            want_lo = np.array([wlo[0], -whi[1], -whi[2]]) / 0.4
            want_hi = np.array([whi[0], -wlo[1], -wlo[2]]) / 0.4
            if np.abs(lo - want_lo).max() > 2 or np.abs(hi - want_hi).max() > 2:
                problems.append(f"panel {sb['name']} part {pid} {q['part']}: lands at {lo.round(1)}-{hi.round(1)} "
                                f"LDU, expected {want_lo.round(1)}-{want_hi.round(1)}")
            col = model["colors"][q["color"]]["hex"]
            tris_all += [(tri, col) for tri, _ in tris]
    return problems, tris_all


def render(tris, path, size=900):
    from PIL import Image, ImageDraw
    el, az = math.radians(30), math.radians(45)
    # LDraw: -Y up. View from +X, -Z (our +x, +z) and above.
    def proj(v):
        x, y, z = v[..., 0], -v[..., 1], -v[..., 2]
        u = (x - z) * math.cos(az)
        w = (x + z) * math.sin(az) * math.sin(el) - y * math.cos(el)
        d = (x + z) * math.cos(el) * math.cos(az) + y * math.sin(el)
        return u, w, d
    P = np.stack([np.stack(proj(t), -1) for t, _ in tris])
    lo, hi = P[..., :2].reshape(-1, 2).min(0), P[..., :2].reshape(-1, 2).max(0)
    s = (size * 0.9) / max(hi - lo)
    img = Image.new("RGB", (size, size), (251, 250, 247))
    d = ImageDraw.Draw(img)
    light = np.array([0.4, 0.8, 0.45])
    order = np.argsort(P[:, :, 2].mean(1))
    for k in order:
        tri, col = tris[k]
        n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        n = n / (np.linalg.norm(n) + 1e-9)
        n = np.array([n[0], -n[1], -n[2]])
        f = 0.55 + 0.45 * abs(float(n @ light))
        rgb = tuple(int(int(col[i:i + 2], 16) * f) for i in (1, 3, 5))
        pts = [((P[k, m, 0] - lo[0]) * s + size * 0.05, (P[k, m, 1] - lo[1]) * s + size * 0.05) for m in range(3)]
        d.polygon(pts, fill=rgb)
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("ldr")
    ap.add_argument("--lib", required=True)
    ap.add_argument("--png")
    a = ap.parse_args()
    model = json.load(open(a.model))
    problems, tris = check(model, open(a.ldr).read(), a.lib, Catalog())
    for p in problems[:40]:
        print("PROBLEM:", p)
    n = len(model["parts"]) + sum(len(sb["parts"]) for sb in model.get("subassemblies", []))
    print(f"{n} parts checked against the official LDraw geometry: "
          f"{'OK' if not problems else f'{len(problems)} problems'}")
    if a.png:
        render(tris, a.png)
        print("render ->", a.png)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
