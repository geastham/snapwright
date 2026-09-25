"""Software checks for a brick model. Nothing here replaces building it for real.

Checks
  collisions      two parts claiming the same cell
  connections     stud-to-tube contacts (a part with studs directly under another part)
  structures      connected components of the connection graph
  floating        parts not connected (through any path) to a part resting on the ground
  weak_parts      parts wider than 1x1 held by a single stud (they can swivel or pop off)
  necks           plate boundaries where very few studs carry everything above
  balance         centre of mass vs the ground footprint (convex hull), margin in mm
  availability    part-colour combos not verified against the catalog
"""
from __future__ import annotations

import numpy as np

STUD_MM, PLATE_MM = 8.0, 3.2


def part_mass_g(p) -> float:
    # fitted to typical weights: 2x4 brick ~2.3 g, 2x4 plate ~1.4 g
    return 0.119 * p["dx"] * p["dz"] + 0.056 * p["dx"] * p["dz"] * p["h"]


def occupancy(parts, shape):
    occ = -np.ones(shape, dtype=np.int32)
    collisions = 0
    for p in parts:
        sl = occ[p["x"]:p["x"] + p["dx"], p["z"]:p["z"] + p["dz"], p["y"]:p["y"] + p["h"]]
        collisions += int((sl >= 0).sum())
        sl[...] = p["id"]
    return occ, collisions


def connection_graph(parts, occ):
    """Return {(lower, upper): studs} for every stud contact."""
    studs = np.array([p["studs"] for p in parts], dtype=bool)
    a, b = occ[:, :, :-1], occ[:, :, 1:]
    m = (a >= 0) & (b >= 0) & (a != b)
    la, ub = a[m], b[m]
    keep = studs[la]
    la, ub = la[keep], ub[keep]
    edges: dict = {}
    for i, j in zip(la.tolist(), ub.tolist()):
        edges[(i, j)] = edges.get((i, j), 0) + 1
    return edges


class DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def _hull(pts):
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def _margin(pt, hull):
    """Signed distance from pt to hull edges (positive = inside)."""
    if len(hull) < 3:
        return -1.0
    best = 1e18
    inside = True
    n = len(hull)
    for i in range(n):
        (x1, y1), (x2, y2) = hull[i], hull[(i + 1) % n]
        ex, ey = x2 - x1, y2 - y1
        L = (ex * ex + ey * ey) ** 0.5 or 1e-9
        d = ((pt[0] - x1) * ey - (pt[1] - y1) * ex) / L  # >0 right of edge
        # hull is CCW, interior is on the left => cross < 0 on the left
        dist = -d
        if dist < 0:
            inside = False
        best = min(best, abs(dist))
    return best if inside else -best


def validate(parts, shape, catalog=None) -> dict:
    n = len(parts)
    occ, collisions = occupancy(parts, shape)
    edges = connection_graph(parts, occ)
    dsu = DSU(max(n, 1))
    per_part = [0] * n
    for (i, j), k in edges.items():
        dsu.union(i, j)
        per_part[i] += k
        per_part[j] += k
    grounded_roots = {dsu.find(p["id"]) for p in parts if p["y"] == 0}
    roots = {dsu.find(p["id"]) for p in parts}
    floating = [p["id"] for p in parts if dsu.find(p["id"]) not in grounded_roots]

    weak = [p["id"] for p in parts if p["dx"] * p["dz"] > 1 and per_part[p["id"]] == 1 and p["y"] > 0]

    # necks: at each plate boundary, stud contacts starting there plus cells of parts that
    # span straight through it; low totals under a lot of model are fragile points
    NY = shape[2]
    cross = np.zeros(NY + 1, dtype=int)
    for (i, j), k in edges.items():
        cross[parts[j]["y"]] += k
    span = np.zeros(NY + 1, dtype=int)
    starts = np.zeros(NY + 1, dtype=int)
    for p in parts:
        starts[p["y"]] += 1
        for yy in range(p["y"] + 1, p["y"] + p["h"]):
            span[yy] += p["dx"] * p["dz"]
    above = np.cumsum(starts[::-1])[::-1]
    necks = [{"plate": int(y), "strength": int(cross[y] + span[y]), "parts_above": int(above[y])}
             for y in range(1, NY) if above[y] >= 6 and cross[y] + span[y] <= 3]

    # balance
    mass = [part_mass_g(p) for p in parts]
    M = sum(mass) or 1.0
    cx = sum(m * (p["x"] + p["dx"] / 2) for m, p in zip(mass, parts)) / M
    cz = sum(m * (p["z"] + p["dz"] / 2) for m, p in zip(mass, parts)) / M
    ground = [(p["x"] + a, p["z"] + b) for p in parts if p["y"] == 0
              for a in (0, p["dx"]) for b in (0, p["dz"])]
    hull = _hull(ground)
    margin = _margin((cx, cz), hull) * STUD_MM if hull else -1

    unverified = []
    if catalog is not None:
        seen = set()
        for p in parts:
            k = (p["part"], p["color"])
            if k not in seen:
                seen.add(k)
                if catalog.available(*k) == "unverified":
                    unverified.append({"part": k[0], "color": k[1]})

    filled = np.argwhere(occ >= 0)
    if len(filled):
        lo, hi = filled.min(0), filled.max(0) + 1
        dims = {"width_cm": round((hi[0] - lo[0]) * STUD_MM / 10, 1),
                "depth_cm": round((hi[1] - lo[1]) * STUD_MM / 10, 1),
                "height_cm": round((hi[2] - lo[2]) * PLATE_MM / 10, 1)}
    else:
        dims = {"width_cm": 0, "depth_cm": 0, "height_cm": 0}

    kinds: dict = {}
    for p in parts:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1

    return {
        "parts": n,
        "unique_lots": len({(p["part"], p["color"]) for p in parts}),
        "connections": int(sum(edges.values())),
        "links": len(edges),
        "collisions": collisions,
        "structures": len(roots),
        "floating": len(floating),
        "floating_ids": floating[:200],
        "weak_parts": weak,
        "necks": necks,
        "mass_g": round(M, 1),
        "com_margin_mm": round(margin, 1),
        "unverified_combos": unverified,
        "kinds": kinds,
        **dims,
        "per_part_studs": per_part,
    }


def verdict(stats) -> tuple[bool, list[str]]:
    """Hard failures block the book; notes are printed in it."""
    fails = []
    if stats["collisions"]:
        fails.append(f"{stats['collisions']} colliding cells")
    if stats["floating"]:
        fails.append(f"{stats['floating']} floating parts")
    if stats["structures"] > 1:
        fails.append(f"{stats['structures']} separate structures")
    if stats["com_margin_mm"] < 3:
        fails.append(f"centre of mass only {stats['com_margin_mm']} mm inside the footprint (tips over)")
    return (not fails), fails
