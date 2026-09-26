"""Software checks for a brick model. Nothing here replaces building it for real.

Checks
  collisions      two parts claiming the same cell
  connections     stud-to-tube contacts (a part with studs directly under another part)
  structures      connected components of the connection graph
  floating        parts not connected (through any path) to a part resting on the ground
  weak_parts      parts wider than 1x1 held by a single stud (they can swivel or pop off)
  necks           pieces held on by very few studs (min cut on the connection graph)
  balance         centre of mass vs the ground footprint (convex hull), margin in mm
  availability    part-colour combos not verified against the catalog
"""
from __future__ import annotations

import numpy as np

STUD_MM, PLATE_MM = 8.0, 3.2
MAX_TRIM_FRACTION = 0.01   # trimming more of the design than this means it needs support


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


def stud_socket_grids(parts, shape):
    """Per-cell connectors: stud[x, z, y] where a part's top layer has a stud at that cell,
    socket[x, z, y] where a part's bottom layer takes a stud there. Box parts have studs on
    every top cell (if `studs`) and sockets on every bottom cell; shaped parts list theirs in
    `top_cells` / `bottom_cells` (world [x, z])."""
    stud = np.zeros(shape, dtype=bool)
    sock = np.zeros(shape, dtype=bool)
    for p in parts:
        top, bot = p["y"] + p["h"] - 1, p["y"]
        if "top_cells" in p:
            for x, z in p["top_cells"]:
                stud[x, z, top] = True
        elif p["studs"]:
            stud[p["x"]:p["x"] + p["dx"], p["z"]:p["z"] + p["dz"], top] = True
        if "bottom_cells" in p:
            for x, z in p["bottom_cells"]:
                sock[x, z, bot] = True
        else:
            sock[p["x"]:p["x"] + p["dx"], p["z"]:p["z"] + p["dz"], bot] = True
    return stud, sock


def connection_graph(parts, occ):
    """Return {(lower, upper): studs} for every stud contact: a stud on the lower part's top
    cell under a socket on the upper part's bottom cell."""
    stud, sock = stud_socket_grids(parts, occ.shape)
    a, b = occ[:, :, :-1], occ[:, :, 1:]
    m = (a >= 0) & (b >= 0) & (a != b) & stud[:, :, :-1] & sock[:, :, 1:]
    la, ub = a[m], b[m]
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


def find_necks(parts, edges, shape, max_studs=3, min_parts=6):
    """Weak points: for every plate boundary, each connected group of parts above it is a
    load; its max flow (in studs) from the ground through the connection graph is the
    fewest studs that hold it up. When that is <= max_studs, report the piece that would
    break off (the side of the min cut away from the ground) if it has >= min_parts parts.
    Several boundaries can find the same cut; each cut is reported once."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import breadth_first_order, connected_components, maximum_flow

    n = len(parts)
    if n == 0 or not edges:
        return []
    S, T = n, n + 1
    BIG = 10 ** 6
    ei = np.array([k for k in edges], dtype=np.int64).reshape(-1, 2)
    ek = np.array(list(edges.values()), dtype=np.int64)
    ground = np.array([p["id"] for p in parts if p["y"] == 0], dtype=np.int64)
    ys = np.array([p["y"] for p in parts])
    mass = np.array([part_mass_g(p) for p in parts])
    base_r = np.concatenate([ei[:, 0], ei[:, 1], np.full(len(ground), S)])
    base_c = np.concatenate([ei[:, 1], ei[:, 0], ground])
    base_v = np.concatenate([ek, ek, np.full(len(ground), BIG)])
    seen, found = set(), {}
    for b in range(1, shape[2]):
        up = np.nonzero(ys >= b)[0]
        if len(up) < min_parts:
            continue
        keep = (ys[ei[:, 0]] >= b) & (ys[ei[:, 1]] >= b)
        sub = csr_matrix((np.ones(int(keep.sum())), (ei[keep, 0], ei[keep, 1])), shape=(n, n))
        _, lab = connected_components(sub, directed=False)
        for comp in np.unique(lab[up]):
            C = up[lab[up] == comp]
            key = C.tobytes()
            if key in seen:
                continue
            seen.add(key)
            r = np.concatenate([base_r, C])
            c = np.concatenate([base_c, np.full(len(C), T)])
            v = np.concatenate([base_v, np.full(len(C), BIG)])
            cap = csr_matrix((v.astype(np.int32), (r, c)), shape=(n + 2, n + 2))
            res = maximum_flow(cap, S, T)
            if res.flow_value == 0 or res.flow_value > max_studs:
                continue          # floating (reported elsewhere) or strong enough
            # residual reachability from the ground gives the cut nearest the ground
            resid = (cap - res.flow).tocsr()
            resid.data = np.where(resid.data > 0, 1, 0)
            resid.eliminate_zeros()
            reach = np.zeros(n + 2, dtype=bool)
            reach[breadth_first_order(resid, S, directed=True, return_predecessors=False)] = True
            piece = np.nonzero(~reach[:n])[0]
            if len(piece) < min_parts:
                continue
            cut = tuple(sorted((int(i), int(j)) for i, j in ei
                               if reach[i] != reach[j]))
            if cut in found and found[cut]["plate"] <= b:
                continue
            found[cut] = {"plate": int(min(ys[piece])), "strength": int(res.flow_value),
                          "parts_above": int(len(piece)), "mass_g": round(float(mass[piece].sum()), 1),
                          "cut": [list(e) for e in cut]}
    return sorted(found.values(), key=lambda d: (d["strength"], -d["parts_above"], d["plate"]))


def validate(parts, shape, catalog=None, with_necks=True) -> dict:
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

    necks = find_necks(parts, edges, shape) if with_necks else []

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
    shaped: dict = {}
    shaped_cells = 0
    for p in parts:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
        if p.get("shape", "box") != "box":
            shaped[p["shape"]] = shaped.get(p["shape"], 0) + 1
            shaped_cells += p["dx"] * p["dz"] * p["h"]

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
        "shaped": shaped,
        "shaped_cells": shaped_cells,
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
    if stats.get("floating_voxels"):
        fails.append(f"{stats['floating_voxels']} design voxels don't touch the rest of the model "
                     f"or the ground (join them in the design)")
    removed = stats.get("trimmed_cells", 0)
    if removed and removed > MAX_TRIM_FRACTION * max(1, stats.get("design_voxels", 0)):
        fails.append(f"repairs trimmed {removed} design cells ({100 * removed / max(1, stats['design_voxels']):.1f}%); "
                     f"add support in the design instead")
    if stats["com_margin_mm"] < 3:
        fails.append(f"centre of mass only {stats['com_margin_mm']} mm inside the footprint (tips over)")
    return (not fails), fails


def report_lines(stats) -> list[tuple[str, str]]:
    """The software checks as (kind, text) lines, kind = check | change | note. One source for
    the CLI log, the book finale and the viewer, so the three always say the same thing.
    Every automatic change the packer made to the design is a `change` line."""
    st = stats
    s_ = lambda n, w: f"{n:,} {w}" + ("" if n == 1 else "s")  # noqa: E731
    out = [
        ("check", f"{st['parts']:,} parts, {st['connections']:,} stud connections, "
                  f"{s_(st['structures'], 'structure')}"),
        ("check", f"{s_(st['collisions'], 'collision')}, {st['floating']} floating parts, "
                  f"{s_(len(st['weak_parts']), 'single-stud joint')}"),
        ("check", f"Centre of mass {st['com_margin_mm']} mm inside the base footprint"),
        ("check", f"About {st['mass_g'] / 1000:.2f} kg, {st['width_cm']} x {st['depth_cm']} x "
                  f"{st['height_cm']} cm (estimated)"),
    ]
    changes = [(st.get("recolored_cells", 0), "visible cell recoloured", "visible cells recoloured"),
               (st.get("trimmed_cells", 0), "overhang cell trimmed", "overhang cells trimmed"),
               (st.get("added_cells", 0), "support cell added", "support cells added"),
               (st.get("studded_cells", 0), "top cell uses a studded plate instead of a tile",
                "top cells use studded plates instead of tiles")]
    for n, one, many in changes:
        if n:
            out.append(("change", f"Auto-repair: {n:,} {one if n == 1 else many}"))
    sh = st.get("shaped") or {}
    if sh:
        names = {"slope": ("slope", "slopes"), "slope_inv": ("inverted slope", "inverted slopes"),
                 "round": ("round part", "round parts")}
        bits = [f"{n} {names[k][0] if n == 1 else names[k][1]}" for k, n in sorted(sh.items()) if k in names]
        out.append(("note", "Surface shaping: " + ", ".join(bits) + " smooth the voxel steps"))
    necks = st.get("necks") or []
    for nk in necks[:3]:
        g = f" ({nk['mass_g']:.0f} g)" if nk.get("mass_g") is not None else ""
        out.append(("note", f"Weak point: {nk['parts_above']} parts{g} from plate "
                            f"{nk['plate']} up are held by {s_(nk['strength'], 'stud')}"))
    if len(necks) > 3:
        out.append(("note", f"... and {len(necks) - 3} more weak points held by 3 studs or fewer"))
    if st.get("unverified_combos"):
        out.append(("note", f"{len(st['unverified_combos'])} part-colour combos not yet verified "
                            f"against a parts catalog"))
    for f in st.get("failures", []):
        out.append(("fail", f"FAIL: {f}"))
    return out
