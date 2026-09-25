"""Turn a coloured voxel grid into real parts.

Strategy (per seed):
  * Visibility: flood-fill the empty space from outside. Cells that can't be seen (inside
    solid masses, inside sealed hollows) are wildcards: they take whatever colour lets the
    part be bigger and better connected. Visible cells keep their exact colour.
  * Work up in brick courses (3 plates). Where a column's visible colour is constant through
    the whole course, it's a brick candidate; pack bricks there first.
  * The rest is packed plate layer by plate layer. Visible top cells that sit on something
    get tiles (smooth finish); overhanging cells are packed first and must share a part with
    at least one supported cell, so rims and ledges are anchored.
  * Greedy per cell, scored by area, by how many distinct parts below it bridges (running
    bond), and by alternating long-axis direction between courses.
  * Repair loop for parts left outside the main structure: (1) no bricks around them so plates
    interlock, (2) studded plates instead of tiles above them, (3) nudge visible colours to the
    neighbour, (4) last resort, trim overhang cells nothing can hold. All changes are counted.
  * Several seeds are tried; the validator picks the best.
"""
from __future__ import annotations

import random

import numpy as np

from .catalog import Catalog

try:
    from scipy import ndimage as _ndi
except Exception:  # pragma: no cover
    _ndi = None


def exterior_visible(V: np.ndarray) -> np.ndarray:
    """Filled cells that touch empty space connected to the outside (table side excluded)."""
    NX, NZ, NY = V.shape
    # pad x/z both sides and the top; the bottom (table) is not an opening
    empty = np.pad(V == 0, ((1, 1), (1, 1), (0, 1)), constant_values=True)
    if _ndi is not None:
        lab, _ = _ndi.label(empty)
        outside = lab == lab[0, 0, -1]
    else:  # BFS fallback
        outside = np.zeros_like(empty)
        stack = [(0, 0, empty.shape[2] - 1)]
        S = empty.shape
        while stack:
            x, z, y = stack.pop()
            if outside[x, z, y] or not empty[x, z, y]:
                continue
            outside[x, z, y] = True
            for dx, dz, dy in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
                a, b, c = x + dx, z + dz, y + dy
                if 0 <= a < S[0] and 0 <= b < S[1] and 0 <= c < S[2]:
                    stack.append((a, b, c))
    op = outside                                  # (NX+2, NZ+2, NY+1)
    vis = np.zeros(V.shape, dtype=bool)
    vis |= op[2:, 1:-1, :NY]                      # +x neighbour
    vis |= op[:-2, 1:-1, :NY]                     # -x
    vis |= op[1:-1, 2:, :NY]                      # +z
    vis |= op[1:-1, :-2, :NY]                     # -z
    vis |= op[1:-1, 1:-1, 1:NY + 1]               # +y
    vis[:, :, 1:] |= op[1:-1, 1:-1, :NY - 1]      # -y (not for the ground layer)
    return vis & (V > 0)


class Packer:
    def __init__(self, V: np.ndarray, palette: list[str], catalog: Catalog, seed: int = 0,
                 finish: str = "tiles", use_bricks: bool = True, max_len: int = 8,
                 interior: int | None = None, no_brick: np.ndarray | None = None,
                 no_tile: np.ndarray | None = None):
        self.V = V
        self.no_tile = no_tile if no_tile is not None else np.zeros(V.shape, dtype=bool)
        self.no_brick = no_brick if no_brick is not None else np.zeros(V.shape, dtype=bool)
        self.palette = palette
        self.cat = catalog
        self.rng = random.Random(seed)
        self.jitter = 0.05 if seed == 0 else 1.2
        self.finish = finish
        self.use_bricks = use_bricks
        NX, NZ, NY = V.shape
        self.shape = (NX, NZ, NY)
        self.owner = -np.ones(V.shape, dtype=np.int32)
        self.parts: list[dict] = []
        lim = lambda t: t.L <= max_len
        self.bricks = [t for t in catalog.of_kind("brick") if lim(t)]
        self.plates = [t for t in catalog.of_kind("plate") if lim(t)]
        self.tiles = [t for t in catalog.of_kind("tile") if lim(t)]
        self.vis = exterior_visible(V)
        # colour requirement per cell: palette index if visible, 0 = wildcard (hidden)
        self.req = np.where(self.vis, V, 0).astype(np.int16)
        if interior is None:
            opaque = [i + 1 for i, k in enumerate(palette) if not k.startswith("trans")]
            vals, cnt = np.unique(V[np.isin(V, opaque)], return_counts=True)
            interior = int(vals[np.argmax(cnt)]) if len(vals) else 1
        self.interior = interior
        top = np.zeros(V.shape, dtype=bool)
        top[:, :, :-1] = (V[:, :, :-1] > 0) & (V[:, :, 1:] == 0)
        top[:, :, -1] = V[:, :, -1] > 0
        self.top_exposed = top & self.vis
        sup = np.zeros(V.shape, dtype=bool)
        sup[:, :, 0] = V[:, :, 0] > 0
        sup[:, :, 1:] = (V[:, :, 1:] > 0) & (V[:, :, :-1] > 0)
        self.supported = sup

    def run(self) -> list[dict]:
        NX, NZ, NY = self.shape
        filled = self.V > 0
        for c in range((NY + 2) // 3):
            y0 = 3 * c
            pref = c % 2
            if self.use_bricks and y0 + 3 <= NY and self.bricks:
                f = filled[:, :, y0] & filled[:, :, y0 + 1] & filled[:, :, y0 + 2]
                r = self.req[:, :, y0:y0 + 3]
                colmax = r.max(2)
                colmin = np.where(r > 0, r, 32767).min(2)
                consistent = (colmax == 0) | (colmax == colmin)
                mask = f & consistent & self.supported[:, :, y0] & ~self.no_brick[:, :, y0:y0 + 3].any(2)
                if self.finish == "tiles":
                    mask &= ~self.top_exposed[:, :, y0 + 2]
                # cells in this course that must be plate stacks can't interlock with bricks
                # beside them, so give them a one-stud plate margin to bridge into
                plate_only = filled[:, :, y0:y0 + 3].any(2) & ~mask
                if plate_only.any():
                    grown = plate_only.copy()
                    grown[1:, :] |= plate_only[:-1, :]
                    grown[:-1, :] |= plate_only[1:, :]
                    grown[:, 1:] |= plate_only[:, :-1]
                    grown[:, :-1] |= plate_only[:, 1:]
                    mask &= ~grown
                ccol = np.where(consistent, colmax, -1)
                self._pack(mask, ccol, y0, 3, self.bricks, pref)
            for y in range(y0, min(y0 + 3, NY)):
                rem = filled[:, :, y] & (self.owner[:, :, y] < 0)
                col = self.req[:, :, y]
                if self.finish == "tiles" and self.tiles:
                    tmask = rem & self.top_exposed[:, :, y] & self.supported[:, :, y] & ~self.no_tile[:, :, y]
                    hang = rem & ~self.supported[:, :, y]
                    if hang.any():  # plates next to an overhang must be free to anchor it
                        g = hang.copy()
                        g[1:, :] |= hang[:-1, :]; g[:-1, :] |= hang[1:, :]
                        g[:, 1:] |= hang[:, :-1]; g[:, :-1] |= hang[:, 1:]
                        g[1:, 1:] |= hang[:-1, :-1]; g[:-1, :-1] |= hang[1:, 1:]
                        g[1:, :-1] |= hang[:-1, 1:]; g[:-1, 1:] |= hang[1:, :-1]
                        tmask &= ~g
                    self._pack(rem & ~tmask, col, y, 1, self.plates, (pref + y) % 2)
                    self._pack(tmask, col, y, 1, self.tiles, (pref + y) % 2)
                else:
                    self._pack(rem, col, y, 1, self.plates, (pref + y) % 2)
        return self.parts

    # ---- packing ----------------------------------------------------------
    def _fits(self, free, col, x, z, dx, dz):
        NX, NZ, _ = self.shape
        if x < 0 or z < 0 or x + dx > NX or z + dz > NZ:
            return None
        if not free[x:x + dx, z:z + dz].all():
            return None
        sub = col[x:x + dx, z:z + dz]
        if (sub < 0).any():
            return None
        vals = np.unique(sub[sub > 0])
        if len(vals) > 1:
            return None
        return int(vals[0]) if len(vals) else 0

    def _score(self, x, z, dx, dz, y, pref):
        score = float(dx * dz)
        if y > 0:
            below = self.owner[x:x + dx, z:z + dz, y - 1]
            ids = np.unique(below[below >= 0])
            score += 2.5 * len(ids)
            if len(ids) == 0:
                score -= 25.0          # nothing underneath: only as a last resort
            elif len(ids) == 1:
                p = self.parts[ids[0]]
                if p["x"] == x and p["z"] == z and p["dx"] == dx and p["dz"] == dz:
                    score -= 3.0      # exact stack = seam straight through
        if (dx > dz and pref == 0) or (dz > dx and pref == 1):
            score += 0.6
        return score + self.rng.random() * self.jitter

    def _place(self, t, x, z, y, dx, dz, h, cidx, free, rot):
        pid = len(self.parts)
        self.owner[x:x + dx, z:z + dz, y:y + h] = pid
        free[x:x + dx, z:z + dz] = False
        color = self.palette[(cidx or self.interior) - 1]
        self.parts.append({"id": pid, "part": t.id, "name": t.name, "kind": t.kind, "color": color,
                           "x": int(x), "z": int(z), "y": int(y), "dx": int(dx), "dz": int(dz),
                           "h": int(h), "rot": rot, "studs": t.studs})

    def _pack(self, mask, col, y, h, types, pref):
        if not mask.any():
            return
        free = mask.copy()
        # phase 1: overhanging cells, any anchor offset, must include a supported cell
        if y > 0:
            under = self.owner[:, :, y - 1] >= 0
            # farthest-from-support first, so outer rings claim a path inward before inner rings
            dist = np.full(free.shape, 10 ** 6, dtype=np.int32)
            frontier = [tuple(c) for c in np.argwhere(free & under)]
            for c in frontier:
                dist[c] = 0
            while frontier:
                nxt = []
                for x, z in frontier:
                    for a, b in ((x + 1, z), (x - 1, z), (x, z + 1), (x, z - 1)):
                        if 0 <= a < free.shape[0] and 0 <= b < free.shape[1] and free[a, b] \
                                and dist[a, b] > dist[x, z] + 1:
                            dist[a, b] = dist[x, z] + 1
                            nxt.append((a, b))
                frontier = nxt
            def options(x, z):
                out = []
                for t in types:
                    for rot in ((0,) if t.L == t.W else (0, 1)):
                        dx, dz = (t.L, t.W) if rot == 0 else (t.W, t.L)
                        for ox in range(dx):
                            for oz in range(dz):
                                ax, az = x - ox, z - oz
                                c = self._fits(free, col, ax, az, dx, dz)
                                if c is not None and under[ax:ax + dx, az:az + dz].any():
                                    out.append((t, ax, az, dx, dz, c, rot))
                return out
            # most constrained first (fewest ways to anchor), then farthest from support
            hang = [tuple(c) for c in np.argwhere(free & ~under)]
            hang.sort(key=lambda c: (len(options(*c)), -dist[c]))
            hanging = free & ~under
            for x, z in hang:
                if not free[x, z]:
                    continue
                cands = sorted(((self._score(c[1], c[2], c[3], c[4], y, pref), i, c)
                                for i, c in enumerate(options(x, z))), reverse=True)[:48]
                best, bs = None, -1e9
                for sc, _, cand in cands:
                    t, ax, az, dx, dz, c, rot = cand
                    # lookahead: don't take the last anchor of a neighbouring overhang cell
                    free[ax:ax + dx, az:az + dz] = False
                    stranded = 0
                    for a in range(max(0, ax - 1), min(free.shape[0], ax + dx + 1)):
                        for b in range(max(0, az - 1), min(free.shape[1], az + dz + 1)):
                            if free[a, b] and hanging[a, b] and not options(a, b):
                                stranded += 1
                    free[ax:ax + dx, az:az + dz] = True
                    sc -= 40.0 * stranded
                    if sc > bs:
                        best, bs = cand, sc
                if best:
                    t, ax, az, dx, dz, c, rot = best
                    self._place(t, ax, az, y, dx, dz, h, c, free, rot)
        # phase 2: scan order, rectangle anchored at the first free cell
        key = (lambda c: (c[0], c[1])) if pref == 1 else (lambda c: (c[1], c[0]))
        for x, z in sorted(map(tuple, np.argwhere(free)), key=key):
            if not free[x, z]:
                continue
            best, bs = None, -1e9
            for t in types:
                for rot in ((0,) if t.L == t.W else (0, 1)):
                    dx, dz = (t.L, t.W) if rot == 0 else (t.W, t.L)
                    c = self._fits(free, col, x, z, dx, dz)
                    if c is None:
                        continue
                    s = self._score(x, z, dx, dz, y, pref)
                    if s > bs:
                        best, bs = (t, dx, dz, c, rot), s
            if best is None:
                continue  # left for the plate pass
            t, dx, dz, c, rot = best
            self._place(t, x, z, y, dx, dz, h, c, free, rot)


def _stranded(parts, shape):
    from .validate import occupancy, connection_graph, DSU
    occ, _ = occupancy(parts, shape)
    edges = connection_graph(parts, occ)
    d = DSU(len(parts))
    for (i, j) in edges:
        d.union(i, j)
    sizes: dict = {}
    for p in parts:
        r = d.find(p["id"])
        sizes[r] = sizes.get(r, 0) + 1
    main = max(sizes, key=sizes.get)
    return occ, d, main, [p for p in parts if d.find(p["id"]) != main]


def _repair(V, parts, shape, no_brick, no_tile, recolor, trim=False):
    """Round without recolour: stop using bricks around stranded parts so plates can interlock.
    Round with recolour: nudge visible cells of stranded parts to the adjacent main colour."""
    occ, d, main, bad = _stranded(parts, shape)
    NX, NZ, NY = shape
    zone = changed = 0
    for p in bad:
        x0, x1 = max(0, p["x"] - 1), min(NX, p["x"] + p["dx"] + 1)
        z0, z1 = max(0, p["z"] - 1), min(NZ, p["z"] + p["dz"] + 1)
        c0 = (p["y"] // 3) * 3
        c1 = min(NY, ((p["y"] + p["h"] - 1) // 3) * 3 + 3)
        sl = no_brick[x0:x1, z0:z1, c0:c1]
        zone += int((~sl).sum())
        sl[...] = True
        # studded plates (not tiles) directly above can hang this part from its neighbours
        top = p["y"] + p["h"]
        if top < NY:
            tl = no_tile[x0:x1, z0:z1, top]
            zone += int((~tl).sum())
            tl[...] = True
        if trim:
            # last resort: an overhang that nothing can hold is removed (rounds off corners)
            for x in range(p["x"], p["x"] + p["dx"]):
                for z in range(p["z"], p["z"] + p["dz"]):
                    for y in range(p["y"], p["y"] + p["h"]):
                        if y > 0 and V[x, z, y - 1] == 0 and V[x, z, y] != 0:
                            V[x, z, y] = 0
                            changed -= 1  # negative = trimmed, tracked separately
            continue
        if not recolor:
            continue
        for x in range(p["x"], p["x"] + p["dx"]):
            for z in range(p["z"], p["z"] + p["dz"]):
                for y in range(p["y"], p["y"] + p["h"]):
                    votes: dict = {}
                    for a, b, c in ((x + 1, z, y), (x - 1, z, y), (x, z + 1, y), (x, z - 1, y),
                                    (x, z, y + 1), (x, z, y - 1)):
                        if 0 <= a < NX and 0 <= b < NZ and 0 <= c < NY and occ[a, b, c] >= 0 \
                                and d.find(int(occ[a, b, c])) == main:
                            v = int(V[a, b, c])
                            votes[v] = votes.get(v, 0) + 1
                    if votes:
                        newc = max(votes, key=votes.get)
                        if V[x, z, y] != newc:
                            V[x, z, y] = newc
                            changed += 1
    return changed, zone


def brickify(V, palette, catalog, seeds=8, finish="tiles", use_bricks=True, max_len=8,
             repair_rounds=6, log=print):
    """Try several seeds (each with a repair loop), validate, keep the best.
    Returns (parts, stats, V_final) where V_final includes any repair recolouring."""
    from .validate import validate
    best = None
    for s in range(seeds):
        W = V.copy()
        no_brick = np.zeros(V.shape, dtype=bool)
        no_tile = np.zeros(V.shape, dtype=bool)
        recolored = trimmed = 0
        for rnd in range(repair_rounds + 1):
            parts = Packer(W, palette, catalog, seed=s, finish=finish, use_bricks=use_bricks,
                           max_len=max_len, no_brick=no_brick, no_tile=no_tile).run()
            stats = validate(parts, W.shape, catalog)
            if (stats["floating"] == 0 and stats["structures"] == 1) or rnd == repair_rounds:
                break
            ch, zone = _repair(W, parts, W.shape, no_brick, no_tile, recolor=rnd in (2, 3),
                               trim=rnd >= 4)
            if ch < 0:
                trimmed -= ch
            else:
                recolored += ch
            if ch == 0 and zone == 0 and rnd >= 4:
                break
        stats["trimmed_cells"] = trimmed
        stats["recolored_cells"] = recolored
        key = (stats["floating"], stats["structures"], len(stats["weak_parts"]), trimmed + recolored,
               -stats["links"], len(parts))
        log(f"  seed {s}: {len(parts)} parts, {stats['links']} part-to-part links, "
            f"{stats['structures']} structure(s), {stats['floating']} floating, "
            f"{len(stats['weak_parts'])} weak, {recolored} recoloured, {trimmed} trimmed")
        if best is None or key < best[0]:
            best = (key, s, parts, stats, W)
    _, seed, parts, stats, W = best
    stats["seed"] = seed
    return parts, stats, W
