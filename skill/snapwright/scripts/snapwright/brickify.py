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
  * Repair loop for parts left outside the main structure, least invasive first: (1) re-pack
    them first so each stranded group joins a neighbour, with no bricks around them so plates
    interlock, (2) studded plates instead of tiles above them, (3) nudge visible colours to the
    neighbour, (4) last resort, trim overhang cells nothing can hold (never floating design
    islands). Colour and geometry changes are counted.
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


def see_through(V: np.ndarray, palette: list[str]) -> np.ndarray:
    """Cells made of transparent colours: you can see into and through them."""
    clear = [i + 1 for i, k in enumerate(palette) if str(k).startswith("trans")]
    return np.isin(V, clear) if clear else np.zeros(V.shape, dtype=bool)


def exterior_visible(V: np.ndarray, clear: np.ndarray | None = None) -> np.ndarray:
    """Filled cells that touch empty space connected to the outside (table side excluded).
    `clear` marks see-through cells: light passes through them, so they and whatever is
    behind them are visible too (a solid transparent lantern shows its core)."""
    NX, NZ, NY = V.shape
    open_ = V == 0 if clear is None else (V == 0) | clear
    # pad x/z both sides and the top; the bottom (table) is not an opening
    empty = np.pad(open_, ((1, 1), (1, 1), (0, 1)), constant_values=True)
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
                 no_tile: np.ndarray | None = None, priority: np.ndarray | None = None,
                 shapes: bool = True, anchors: list | None = None, live_from: int = 1):
        self.V = V
        self.no_tile = no_tile if no_tile is not None else np.zeros(V.shape, dtype=bool)
        self.no_brick = no_brick if no_brick is not None else np.zeros(V.shape, dtype=bool)
        # stranded-group label per cell (0 = none): packed first, at any offset, and must
        # join a cell outside their own group
        self.priority = priority if priority is not None else np.zeros(V.shape, dtype=np.int32)
        # labels below live_from belong to groups an earlier round already joined to the main
        # structure (kept so that area is still packed first); they count as main
        self.live_from = live_from
        self.rescued = 0
        self.shapes = shapes
        self.anchors = anchors or []
        self.palette = palette
        self.cat = catalog
        self.rng = random.Random(seed)
        self.jitter = 0.05 if seed == 0 else 1.2
        self.finish = finish
        self.use_bricks = use_bricks
        NX, NZ, NY = V.shape
        self.shape = (NX, NZ, NY)
        self.owner = -np.ones(V.shape, dtype=np.int32)
        self.stud_top = np.zeros(V.shape, dtype=bool)   # cells whose top offers a stud
        self.parts: list[dict] = []
        lim = lambda t: t.L <= max_len
        self.bricks = [t for t in catalog.of_kind("brick") if lim(t)]
        self.plates = [t for t in catalog.of_kind("plate") if lim(t)]
        self.tiles = [t for t in catalog.of_kind("tile") if lim(t)]
        self.vis = exterior_visible(V, see_through(V, palette))
        # colour requirement per cell: palette index if visible, 0 = wildcard (hidden)
        self.req = np.where(self.vis, V, 0).astype(np.int16)
        if interior is None:
            opaque = [i + 1 for i, k in enumerate(palette) if not k.startswith("trans")]
            vals, cnt = np.unique(V[np.isin(V, opaque)], return_counts=True)
            interior = int(vals[np.argmax(cnt)]) if len(vals) else 1
        self.interior = interior
        self.allow = allowed_colours(catalog, palette, interior)
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
        if self.anchors:
            self._place_anchors()
        if self.shapes:
            self._shape_surface()
        for c in range((NY + 2) // 3):
            y0 = 3 * c
            pref = c % 2
            if self.use_bricks and y0 + 3 <= NY and self.bricks:
                f = filled[:, :, y0] & filled[:, :, y0 + 1] & filled[:, :, y0 + 2]
                r = self.req[:, :, y0:y0 + 3]
                colmax = r.max(2)
                colmin = np.where(r > 0, r, 32767).min(2)
                consistent = (colmax == 0) | (colmax == colmin)
                mask = (f & consistent & self.supported[:, :, y0] & ~self.no_brick[:, :, y0:y0 + 3].any(2)
                        & (self.owner[:, :, y0:y0 + 3] < 0).all(2))
                if self.finish == "tiles":
                    mask &= ~self.top_exposed[:, :, y0 + 2]
                # cells in this course that must be plate stacks can't interlock with bricks
                # beside them, so give them a one-stud plate margin to bridge into
                # (cells already claimed by shaped parts are solid like bricks: no margin)
                plate_only = filled[:, :, y0:y0 + 3].any(2) & ~mask & ~(self.owner[:, :, y0:y0 + 3] >= 0).all(2)
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
                # no tiles on the table: nothing under them and no studs on top, so they would be loose
                if self.finish == "tiles" and self.tiles and y > 0:
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
        if any(p.get("dead") for p in self.parts):
            self.parts = [p for p in self.parts if not p.get("dead")]
            for i, p in enumerate(self.parts):
                p["id"] = i
                self.owner[p["x"]:p["x"] + p["dx"], p["z"]:p["z"] + p["dz"], p["y"]:p["y"] + p["h"]] = i
        return self.parts

    def _place_anchors(self):
        """Side-stud bricks right behind each sideways panel, on the rows that line up with the
        panel's studs (see snot.py). Longest bricks first along each row; a column is skipped
        if the model isn't solid there or the colour can't match."""
        snots = sorted((t for t in self.cat.parts if t.shape == "snot"), key=lambda t: -t.L)
        for req in self.anchors:
            y = req["plate"]
            cols = [(i, x, z) for i, x, z in req["cols"]
                    if 0 <= x < self.shape[0] and 0 <= z < self.shape[1] and y + 3 <= self.shape[2]
                    and (self.V[x, z, y:y + 3] > 0).all() and (self.owner[x, z, y:y + 3] < 0).all()]
            k = 0
            while k < len(cols):
                for t in snots:
                    run = cols[k:k + t.L]
                    if len(run) < t.L or any(run[m][0] != run[0][0] + m for m in range(t.L)):
                        continue
                    cells = [(x, z) for _, x, z in run]
                    vals = {int(self.req[x, z, yy]) for x, z in cells for yy in range(y, y + 3)} - {0}
                    if len(vals) > 1 or not self._ok(t, next(iter(vals), 0)):
                        continue
                    xs, zs = [c[0] for c in cells], [c[1] for c in cells]
                    x0, z0 = min(xs), min(zs)
                    dx, dz = max(xs) - x0 + 1, max(zs) - z0 + 1
                    pid = len(self.parts)
                    self.owner[x0:x0 + dx, z0:z0 + dz, y:y + 3] = pid
                    self.stud_top[x0:x0 + dx, z0:z0 + dz, y + 2] = True
                    color = self.palette[(vals.pop() if vals else self.interior) - 1]
                    self.parts.append({"id": pid, "part": t.id, "name": t.name, "kind": t.kind,
                                       "color": color, "x": x0, "z": z0, "y": y, "dx": dx, "dz": dz,
                                       "h": 3, "rot": req["face"], "studs": True, "shape": "snot",
                                       "dir": req["face"], "side_cells": [[int(a), int(b)] for a, b in cells],
                                       "anchor": req["panel"], "row": req["row"]})
                    k += t.L
                    break
                else:
                    k += 1

    def _ok(self, t, cidx):
        """May part type t come in palette colour cidx (0 = the interior colour)?"""
        return self.allow is None or bool(self.allow[t.id][cidx])

    def _shape_surface(self):
        """Slopes, inverted slopes and round parts claim their cells before normal packing
        (see shaping.py). Cells the repair loop is working on are left alone, and so are
        shapes that aren't made in the colour needed (normal packing covers those cells)."""
        from .shaping import find_shapes
        blocked = self.no_brick | (self.priority > 0)
        for s in find_shapes(self.V, self.req, self.cat, self.finish, blocked, visible=self.vis):
            t = s["t"]
            if not self._ok(t, s["color"] or 0):
                continue
            pid = len(self.parts)
            x, z, y, dx, dz, h = s["x"], s["z"], s["y"], s["dx"], s["dz"], s["h"]
            self.owner[x:x + dx, z:z + dz, y:y + h] = pid
            for cx, cz in s["top_cells"]:
                self.stud_top[cx, cz, y + h - 1] = True
            color = self.palette[(s["color"] or self.interior) - 1]
            self.parts.append({"id": pid, "part": t.id, "name": t.name, "kind": t.kind, "color": color,
                               "x": x, "z": z, "y": y, "dx": dx, "dz": dz, "h": h, "rot": s["dir"],
                               "studs": bool(s["top_cells"]), "shape": t.shape, "dir": s["dir"],
                               "top_cells": s["top_cells"], "bottom_cells": s["bottom_cells"]})
            self._uncover(t.shape, s["dir"], x, z, y, dx, dz, h)

    def _uncover(self, shape, dir_, x, z, y, dx, dz, h):
        """A shaped part doesn't fill its whole box, so some neighbours that counted as hidden
        now show: the cells under a round part (its footprint's corners are open) and the
        cells beside a slope's triangular ends. They keep their design colour instead of
        taking the hidden-filler colour."""
        NX, NZ, NY = self.shape
        cells = []
        if shape == "round" and y > 0:
            cells.append((slice(x, x + dx), slice(z, z + dz), y - 1))
        elif shape in ("slope", "slope_inv"):
            ys = slice(y, y + h)
            if dir_ in (0, 2):          # slopes along x: triangles face -z and +z
                cells += [(slice(x, x + dx), z - 1, ys), (slice(x, x + dx), z + dz, ys)]
            else:
                cells += [(x - 1, slice(z, z + dz), ys), (x + dx, slice(z, z + dz), ys)]
        for cx, cz, cy in cells:
            if isinstance(cx, int) and not 0 <= cx < NX or isinstance(cz, int) and not 0 <= cz < NZ:
                continue
            sl = (cx, cz, cy)
            free = (self.V[sl] > 0) & (self.owner[sl] < 0)
            self.req[sl] = np.where(free, self.V[sl], self.req[sl])

    # ---- packing ----------------------------------------------------------
    def _score(self, x, z, dx, dz, y, pref, h=1):
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
            # long seams matter in stacked plates (flat bases, floors); brick walls already
            # bond through the bridging bonus
            if h == 1 and all(self.parts[i]["h"] == 1 for i in ids):
                score -= SEAM * _seam_run(self.owner[:, :, y - 1], x, z, dx, dz)
        if (dx > dz and pref == 0) or (dz > dx and pref == 1):
            score += 0.6
        return score + self.rng.random() * self.jitter

    def _place(self, t, x, z, y, dx, dz, h, cidx, free, rot):
        pid = len(self.parts)
        self.owner[x:x + dx, z:z + dz, y:y + h] = pid
        self.stud_top[x:x + dx, z:z + dz, y + h - 1] = t.studs
        free[x:x + dx, z:z + dz] = False
        color = self.palette[(cidx or self.interior) - 1]
        self.parts.append({"id": pid, "part": t.id, "name": t.name, "kind": t.kind, "color": color,
                           "x": int(x), "z": int(z), "y": int(y), "dx": int(dx), "dz": int(dz),
                           "h": int(h), "rot": rot, "studs": t.studs})

    def _pack(self, mask, col, y, h, types, pref):
        if not mask.any():
            return
        start = len(self.parts)
        self._pack_layer(mask, col, y, h, types, pref)
        if (self.priority[:, :, y] > 0).any():
            for _ in range(4):  # a rescue can free a neighbour for the next one
                if not self._rescue(start, col, y, h, types):
                    break

    def _rescue(self, start, col, y, h, types):
        """Greedy packing can strand a priority cell as a lone 1x1 when two corners compete
        for the same neighbour. Take a cell from an adjacent part placed in this pass and
        re-cover that part's other cells, if every new piece still rests on something.
        Returns how many lone cells were joined."""
        NX, NZ, _ = self.shape
        done = 0
        shapes = sorted(_shapes(types), key=lambda s: -(s[2] * s[3]))
        under = self.stud_top[:, :, y - 1] if y > 0 else np.ones((NX, NZ), dtype=bool)

        def colour(cells):
            vals = {int(col[c]) for c in cells} - {0}
            return None if len(vals) > 1 or any(col[c] < 0 for c in cells) else (vals.pop() if vals else 0)

        def cover(cells):
            """Rectangles of catalog shapes exactly covering `cells`, biggest first, or None."""
            left, out = set(cells), []
            while left:
                x, z = min(left)
                for t, rot, dx, dz in shapes:
                    rect = {(x + i, z + j) for i in range(dx) for j in range(dz)}
                    if rect <= left and colour(rect) is not None and self._ok(t, colour(rect)) \
                            and any(under[c] for c in rect):
                        out.append((t, rot, x, z, dx, dz, colour(rect)))
                        left -= rect
                        break
                else:
                    return None
            return out

        for pid in range(start, len(self.parts)):
            p = self.parts[pid]
            if p.get("dead") or p["dx"] * p["dz"] != 1 or not self.priority[p["x"], p["z"], y]:
                continue
            x, z = p["x"], p["z"]
            best = None
            for a, b in ((x + 1, z), (x - 1, z), (x, z + 1), (x, z - 1)):
                if not (0 <= a < NX and 0 <= b < NZ):
                    continue
                q = int(self.owner[a, b, y])
                if q < start or q == pid or self.parts[q]["h"] != h or self.parts[q]["y"] != y:
                    continue
                Q = self.parts[q]
                qcells = {(Q["x"] + i, Q["z"] + j) for i in range(Q["dx"]) for j in range(Q["dz"])}
                pool = qcells | {(x, z)}
                for t, rot, dx, dz in shapes:
                    for ox in range(dx):
                        for oz in range(dz):
                            ax, az = x - ox, z - oz
                            rect = {(ax + i, az + j) for i in range(dx) for j in range(dz)}
                            if (a, b) not in rect or not rect <= pool or colour(rect) is None \
                                    or not self._ok(t, colour(rect)) or not any(under[c] for c in rect):
                                continue
                            # it must join the lone cell to another group, not just its own
                            if all(self.priority[c[0], c[1], y] == self.priority[x, z, y] for c in rect):
                                continue
                            rest = cover(pool - rect)
                            if rest is None:
                                continue
                            plan = [(t, rot, ax, az, dx, dz, colour(rect))] + rest
                            lone = sum(1 for r in rest if r[4] * r[5] == 1
                                       and self.priority[r[2], r[3], y])
                            cost = len(plan) + 3 * lone
                            if best is None or cost < best[0]:
                                best = (cost, q, plan)
            if best is None:
                continue
            _, q, plan = best
            if len(plan) == 1:          # the joined part swallowed the neighbour whole
                self.parts[q]["dead"] = True
            for slot, (t, rot, ax, az, dx, dz, c) in zip([pid, q] + [None] * len(plan), plan):
                slot = len(self.parts) if slot is None else slot
                entry = {"id": slot, "part": t.id, "name": t.name, "kind": t.kind,
                         "color": self.palette[(c or self.interior) - 1], "x": int(ax), "z": int(az),
                         "y": int(y), "dx": int(dx), "dz": int(dz), "h": int(h), "rot": rot,
                         "studs": t.studs}
                if slot == len(self.parts):
                    self.parts.append(entry)
                else:
                    self.parts[slot] = entry
                self.owner[ax:ax + dx, az:az + dz, y:y + h] = slot
                self.stud_top[ax:ax + dx, az:az + dz, y + h - 1] = t.studs
            self.rescued += 1
            done += 1
        return done

    def _pack_layer(self, mask, col, y, h, types, pref):
        free = mask.copy()
        shapes = _shapes(types)
        # phase 1: overhanging cells (and repair-priority cells), any anchor offset, must
        # include a supported cell; on the ground layer everything is supported
        prio = free & (self.priority[:, :, y] > 0)
        if y > 0 or prio.any():
            under = self.stud_top[:, :, y - 1] if y > 0 else np.ones(free.shape, dtype=bool)
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
            fm = FitMaps(shapes, free, col, under, allow=self.allow)
            # a supported priority cell only counts as covered by a part that joins it to a
            # neighbour; a lone 1x1 there is what stranded it (left to phase 2 as a fallback)
            prio_layer = self.priority[:, :, y]

            def joining(x, z):
                """Placements that join a supported priority cell to something outside its
                own stranded group (the only kind that fixes it): into the main structure if
                it can, else into a neighbouring stranded group (two groups side by side
                would otherwise only ever join each other)."""
                g = prio_layer[x, z]
                if g < self.live_from:          # already joined in an earlier round
                    return fm.options(x, z, 2)
                out, main = [], []
                for o in fm.options(x, z, 2):
                    win = prio_layer[o[1]:o[1] + o[3], o[2]:o[2] + o[4]]
                    other = win != g
                    if other.any():
                        out.append(o)
                        if (other & (win < self.live_from)).any():
                            main.append(o)
                return main or out

            def options(x, z):
                if not under[x, z]:
                    return fm.options(x, z)
                # no way to join from here: anything goes, even a 1x1, so the lookahead can
                # keep a neighbour's only join free
                return joining(x, z) or fm.options(x, z, 2 if self.priority[x, z, y] < self.live_from else 1)

            def strands(a, b, ax, az, dx, dz):
                """Would taking rectangle (ax, az, dx, dz) leave cell (a, b) no way to be
                covered (overhang) or joined (priority cell)?"""
                if not under[a, b]:
                    return not fm.any_option_avoiding(a, b, ax, az, dx, dz)
                had = joining(a, b)
                return bool(had) and all(o[1] < ax + dx and ax < o[1] + o[3] and o[2] < az + dz
                                         and az < o[2] + o[4] for o in had)
            # most constrained first (fewest ways to anchor), then farthest from support
            hanging = free & (~under | prio)
            hang = [tuple(c) for c in np.argwhere(hanging)]
            hang.sort(key=lambda c: (len(options(*c)), -dist[c]))
            for x, z in hang:
                if not free[x, z]:
                    continue
                cands = sorted(((self._score(c[1], c[2], c[3], c[4], y, pref, h), i, c)
                                for i, c in enumerate(options(x, z))), reverse=True)[:48]
                best, bs = None, -1e9
                for sc, _, cand in cands:
                    t, ax, az, dx, dz, c, rot = cand
                    # lookahead: don't take the last anchor of a neighbouring overhang cell
                    free[ax:ax + dx, az:az + dz] = False
                    stranded = 0
                    for a in range(max(0, ax - 1), min(free.shape[0], ax + dx + 1)):
                        for b in range(max(0, az - 1), min(free.shape[1], az + dz + 1)):
                            if free[a, b] and hanging[a, b] and strands(a, b, ax, az, dx, dz):
                                stranded += 1
                    free[ax:ax + dx, az:az + dz] = True
                    sc -= 40.0 * stranded
                    if sc > bs:
                        best, bs = cand, sc
                if best:
                    t, ax, az, dx, dz, c, rot = best
                    self._place(t, ax, az, y, dx, dz, h, c, free, rot)
                    fm.occupy(ax, az, dx, dz)
        # phase 2: scan order, rectangle anchored at the first free cell
        fm = FitMaps(shapes, free, col, allow=self.allow)
        key = (lambda c: (c[0], c[1])) if pref == 1 else (lambda c: (c[1], c[0]))
        for x, z in sorted(map(tuple, np.argwhere(free)), key=key):
            if not free[x, z]:
                continue
            best, bs = None, -1e9
            for k, (t, rot, dx, dz) in enumerate(shapes):
                if not fm.ok[k][x, z]:
                    continue
                s = self._score(x, z, dx, dz, y, pref, h)
                if s > bs:
                    best, bs = (t, dx, dz, int(fm.color[k][x, z]), rot), s
            if best is None:
                continue  # left for the plate pass
            t, dx, dz, c, rot = best
            self._place(t, x, z, y, dx, dz, h, c, free, rot)
            fm.occupy(x, z, dx, dz)


SEAM, SEAM_MIN = 3.0, 6   # score per stud of a whole side (>= SEAM_MIN long) on a joint below


def _seam_run(B, x, z, dx, dz):
    """Studs of the rectangle's sides that lie, whole, on a joint between two parts in the
    layer below (owner grid B): the seam then runs straight up through both layers. A short
    or partly offset side is normal running bond; long whole-side seams are what split a
    flat base into strips. Edges on the model's outline don't count."""
    NX, NZ = B.shape
    n = 0
    if dz >= SEAM_MIN:
        for a in ((x - 1, x), (x + dx - 1, x + dx)):
            if 0 <= a[0] and a[1] < NX:
                l, r = B[a[0], z:z + dz], B[a[1], z:z + dz]
                if ((l >= 0) & (r >= 0) & (l != r)).all():
                    n += dz
    if dx >= SEAM_MIN:
        for a in ((z - 1, z), (z + dz - 1, z + dz)):
            if 0 <= a[0] and a[1] < NZ:
                l, r = B[x:x + dx, a[0]], B[x:x + dx, a[1]]
                if ((l >= 0) & (r >= 0) & (l != r)).all():
                    n += dx
    return n


def allowed_colours(catalog, palette, interior):
    """{part id: bool array over palette index (0 = interior colour)}: which colours each part
    may take, from the catalog's verified availability. None when the catalog has none (then
    every combo is allowed and reported by tier). The 1x1 brick, plate and tile stay allowed
    in every colour, so a cell can always be covered; the checks still flag such a combo as
    unverified."""
    if not catalog.availability:
        return None
    out = {}
    for t in catalog.parts:
        a = np.array([True] + [catalog.available(t.id, k) != "unverified" for k in palette])
        if t.shape == "box" and t.L == t.W == 1:
            a[:] = True
        a[0] = a[interior]
        out[t.id] = a
    return out


def _shapes(types):
    """(type, rot, dx, dz) in the packer's fixed iteration order."""
    out = []
    for t in types:
        for rot in ((0,) if t.L == t.W else (0, 1)):
            dx, dz = (t.L, t.W) if rot == 0 else (t.W, t.L)
            out.append((t, rot, dx, dz))
    return out


def _integral(stack):
    """Summed-area tables for a stack of 2-D layers, zero row/column in front (int64)."""
    k, a, b = stack.shape
    S = np.zeros((k, a + 1, b + 1), dtype=np.int64)
    S[:, 1:, 1:] = stack.astype(np.int64).cumsum(1).cumsum(2)
    return S


def _wsum(S, dx, dz):
    """Sum of every dx x dz window; result[..., i, j] covers a[..., i:i+dx, j:j+dz]."""
    return S[:, dx:, dz:] - S[:, :-dx, dz:] - S[:, dx:, :-dz] + S[:, :-dx, :-dz]


class FitMaps:
    """Where each part shape can be placed on one layer, kept current as parts are placed.

    ok[k][ax, az] is True when shape k anchored at (ax, az) lies on free cells, sees at most
    one required colour (0 = wildcard), no forbidden (-1) cells, and, if `under` is given,
    rests on at least one occupied cell below. color[k] holds the colour it would take, and
    `allow` ({part id: bool per palette index}) rules out colours a part isn't made in.
    Window tests use summed-area tables over the free cells' bounding box; colours are
    uniform exactly when n * sum(v^2) == sum(v)^2 over the n required cells.
    This replaces per-rectangle numpy slicing, which dominated packing time.
    """

    def __init__(self, shapes, free, col, under=None, allow=None):
        NX, NZ = free.shape
        self.shapes = shapes
        self.ok = [np.zeros((NX, NZ), dtype=bool) for _ in shapes]
        self.color = [np.zeros((NX, NZ), dtype=np.int32) for _ in shapes]
        idx = np.argwhere(free)
        if not len(idx):
            return
        (x0, z0), (x1, z1) = idx.min(0), idx.max(0) + 1
        fr = free[x0:x1, z0:z1]
        c = col[x0:x1, z0:z1].astype(np.int64)
        pos = np.where(c > 0, c, 0)
        layers = [fr, c < 0, pos > 0, pos, pos * pos]
        if under is not None:
            layers.append(under[x0:x1, z0:z1])
        tables = _integral(np.stack(layers))
        cache: dict = {}
        for k, (t, rot, dx, dz) in enumerate(shapes):
            if dx > x1 - x0 or dz > z1 - z0:
                continue
            if (dx, dz) not in cache:
                w = _wsum(tables, dx, dz)
                n, sv = w[2], w[3]
                good = (w[0] == dx * dz) & (w[1] == 0) & (n * w[4] == sv * sv)
                if under is not None:
                    good &= w[5] > 0
                colour = np.where(n > 0, sv // np.maximum(n, 1), 0)
                cache[dx, dz] = (good, colour)
            good, colour = cache[dx, dz]
            if allow is not None and t.id in allow:
                good = good & allow[t.id][np.clip(colour, 0, len(allow[t.id]) - 1)]
            gx, gz = good.shape
            self.ok[k][x0:x0 + gx, z0:z0 + gz] = good
            self.color[k][x0:x0 + gx, z0:z0 + gz] = colour

    def occupy(self, x, z, dx, dz):
        """Cells x..x+dx, z..z+dz were taken: no shape may be anchored overlapping them."""
        for k, (_, _, kdx, kdz) in enumerate(self.shapes):
            self.ok[k][max(0, x - kdx + 1):x + dx, max(0, z - kdz + 1):z + dz] = False

    def options(self, x, z, min_area=1):
        """Every placement covering cell (x, z), in the packer's historical order
        (shape, then anchor offset ox, then oz, both counting away from the cell)."""
        out = []
        for k, (t, rot, dx, dz) in enumerate(self.shapes):
            if dx * dz < min_area:
                continue
            sub = self.ok[k][max(0, x - dx + 1):x + 1, max(0, z - dz + 1):z + 1]
            if not sub.any():
                continue
            col = self.color[k]
            for i, j in np.argwhere(sub[::-1, ::-1]):
                ax, az = x - int(i), z - int(j)
                out.append((t, ax, az, dx, dz, int(col[ax, az]), rot))
        return out

    def any_option_avoiding(self, x, z, rx, rz, rdx, rdz, min_area=1):
        """Could cell (x, z) still be covered if rectangle (rx, rz, rdx, rdz) were taken?"""
        for k, (_, _, dx, dz) in enumerate(self.shapes):
            if dx * dz < min_area:
                continue
            x0, z0 = max(0, x - dx + 1), max(0, z - dz + 1)
            sub = self.ok[k][x0:x + 1, z0:z + 1]
            if not sub.any():
                continue
            for i, j in np.argwhere(sub):
                ax, az = x0 + int(i), z0 + int(j)
                if ax + dx <= rx or rx + rdx <= ax or az + dz <= rz or rz + rdz <= az:
                    return True
        return False


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


def floating_voxels(V: np.ndarray) -> np.ndarray:
    """Design voxels in face-connected groups that never touch the ground. No packing can
    hold these, and trimming them would silently delete a feature, so they are left for the
    checks to fail and the designer to join."""
    if _ndi is None:  # pragma: no cover
        return np.zeros(V.shape, dtype=bool)
    lab, _ = _ndi.label(V > 0)
    grounded = np.unique(lab[:, :, 0])
    return (lab > 0) & ~np.isin(lab, grounded[grounded > 0])


def _repair(V, parts, shape, no_brick, no_tile, priority, recolor, trim=False, keep=None,
            studs_up=True):
    """Every round: pack the cells of stranded parts first, at any offset, so they bridge into
    their neighbours, and stop using bricks around them so plates can interlock.
    studs_up: also use studded plates instead of tiles right above them (changes the finish).
    recolor: nudge visible cells of stranded parts to the adjacent main colour.
    trim: remove overhang cells nothing can hold (never cells of floating design islands)."""
    occ, d, main, bad = _stranded(parts, shape)
    if keep is not None:   # parts inside floating design islands can't be helped by repairs
        bad = [p for p in bad if not keep[p["x"]:p["x"] + p["dx"], p["z"]:p["z"] + p["dz"],
                                          p["y"]:p["y"] + p["h"]].all()]
    if not bad:
        return 0, -1
    NX, NZ, NY = shape
    zone = changed = 0
    label = int(priority.max()) + 1
    groups: dict = {}
    for p in bad:
        g = groups.setdefault(d.find(p["id"]), label + len(groups))
        pr = priority[p["x"]:p["x"] + p["dx"], p["z"]:p["z"] + p["dz"], p["y"]:p["y"] + p["h"]]
        zone += int((pr != g).sum())
        pr[...] = g             # latest group wins, so a group must join what's around it
        x0, x1 = max(0, p["x"] - 1), min(NX, p["x"] + p["dx"] + 1)
        z0, z1 = max(0, p["z"] - 1), min(NZ, p["z"] + p["dz"] + 1)
        c0 = (p["y"] // 3) * 3
        c1 = min(NY, ((p["y"] + p["h"] - 1) // 3) * 3 + 3)
        sl = no_brick[x0:x1, z0:z1, c0:c1]
        zone += int((~sl).sum())
        sl[...] = True
        # studded plates (not tiles) directly above can hang this part from its neighbours
        top = p["y"] + p["h"]
        if studs_up and top < NY:
            tl = no_tile[x0:x1, z0:z1, top]
            zone += int((~tl).sum())
            tl[...] = True
        if trim:
            # last resort: an overhang that nothing can hold is removed (rounds off corners)
            for x in range(p["x"], p["x"] + p["dx"]):
                for z in range(p["z"], p["z"] + p["dz"]):
                    for y in range(p["y"], p["y"] + p["h"]):
                        if y > 0 and V[x, z, y - 1] == 0 and V[x, z, y] != 0 \
                                and not (keep is not None and keep[x, z, y]):
                            V[x, z, y] = 0
                            changed -= 1  # negative = trimmed, tracked separately
            continue
    if recolor:
        changed += _recolour_contacts(V, bad, occ, d, main, shape)
    return changed, zone


def _recolour_contacts(V, bad, occ, d, main, shape):
    """Recolour step: per stranded group, ONE cell where it touches the main structure takes
    the main colour there (the middle-height contact, preferring cells with more main
    neighbours). One plate across the colour boundary is enough to join the group: its
    stacked parts hold on to that plate. Recolouring every contact cell instead eroded
    features such as a fin column by column. Returns the number of cells changed."""
    NX, NZ, NY = shape
    groups: dict = {}
    for p in bad:
        groups.setdefault(d.find(p["id"]), []).append(p)
    changed = 0
    for ps in groups.values():
        contacts = []
        for p in ps:
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
                                contacts.append((y, -votes[newc], x, z, newc))
        if not contacts:
            continue
        ys = sorted(c[0] for c in contacts)
        mid = ys[len(ys) // 2]
        y, _, x, z, newc = min(contacts, key=lambda c: (abs(c[0] - mid), c[1], c[0], c[2], c[3]))
        V[x, z, y] = newc
        changed += 1
    return changed


def _studded_by_repair(parts, W, no_tile, finish) -> int:
    """Visible top cells that the tiled finish would cover with tiles but that got studded
    plates because a repair needed the studs to hold something."""
    if finish != "tiles":
        return 0
    top = np.zeros(W.shape, dtype=bool)
    top[:, :, :-1] = (W[:, :, :-1] > 0) & (W[:, :, 1:] == 0)
    top[:, :, -1] = W[:, :, -1] > 0
    n = 0
    for p in parts:
        if p["kind"] == "plate" and p["y"] > 0:
            sl = (slice(p["x"], p["x"] + p["dx"]), slice(p["z"], p["z"] + p["dz"]), p["y"])
            n += int((top[sl] & no_tile[sl]).sum())
    return n


def change_counts(V, W, palette) -> dict:
    """What the automatic repairs really changed, from the design grid V vs the built grid W:
    visible cells whose colour differs, design cells removed, and cells added."""
    vis = exterior_visible(W, see_through(W, palette))
    return {"recolored_cells": int(((V > 0) & (W > 0) & (V != W) & vis).sum()),
            "trimmed_cells": int(((V > 0) & (W == 0)).sum()),
            "added_cells": int(((V == 0) & (W > 0)).sum())}


def brickify(V, palette, catalog, seeds=8, finish="tiles", use_bricks=True, max_len=8,
             repair_rounds=12, log=print, shapes=True, anchors=None):
    """Try several seeds (each with a repair loop), validate, keep the best.
    Returns (parts, stats, V_final) where V_final includes any repair recolouring."""
    from .validate import validate
    best = None
    islands = floating_voxels(V)
    for s in range(seeds):
        W = V.copy()
        no_brick = np.zeros(V.shape, dtype=bool)
        no_tile = np.zeros(V.shape, dtype=bool)
        priority = np.zeros(V.shape, dtype=np.int32)
        # repair stages, least invasive first: 0 re-pack, 1 + studded plates above, 2 + recolour,
        # 3 + trim. A stage runs while it makes progress (fewer stranded parts: joining one
        # group along a thin staircase can strand the next), and gives way after 2 idle rounds.
        stage, least, idle, live = 0, None, 0, 1
        for rnd in range(repair_rounds + 1):
            parts = Packer(W, palette, catalog, seed=s, finish=finish, use_bricks=use_bricks,
                           max_len=max_len, no_brick=no_brick, no_tile=no_tile,
                           priority=priority, shapes=shapes, anchors=anchors, live_from=live).run()
            stats = validate(parts, W.shape, catalog, with_necks=False)
            if (stats["floating"] == 0 and stats["structures"] == 1) or rnd == repair_rounds:
                break
            score = (stats["structures"], stats["floating"])
            if least is None or score < least:
                least, idle = score, 0
            else:
                idle += 1
                if idle >= 2 and stage < 3:
                    stage, idle = stage + 1, 0
            live = int(priority.max()) + 1            # this round's stranded groups get these
            ch, zone = _repair(W, parts, W.shape, no_brick, no_tile, priority, keep=islands,
                               studs_up=stage >= 1, recolor=stage == 2, trim=stage >= 3)
            if zone < 0 or (ch == 0 and zone == 0 and stage >= 3):   # nothing repairable left
                break
        stats.update(change_counts(V, W, palette))
        stats["studded_cells"] = _studded_by_repair(parts, W, no_tile, finish)
        stats["design_voxels"] = int((V > 0).sum())
        stats["floating_voxels"] = int(islands.sum())
        changes = (stats["recolored_cells"] + stats["trimmed_cells"] + stats["added_cells"]
                   + stats["studded_cells"])
        key = (stats["floating"], stats["structures"], len(stats["weak_parts"]), changes,
               -stats["links"], len(parts))
        log(f"  seed {s}: {len(parts)} parts, {stats['links']} part-to-part links, "
            f"{stats['structures']} structure(s), {stats['floating']} floating, "
            f"{len(stats['weak_parts'])} weak, {stats['recolored_cells']} recoloured, "
            f"{stats['trimmed_cells']} trimmed, {stats['studded_cells']} studded")
        if best is None or key < best[0]:
            best = (key, s, parts, stats, W)
    _, seed, parts, stats, W = best
    from .validate import connection_graph, find_necks, occupancy
    occ, _ = occupancy(parts, W.shape)
    stats["necks"] = find_necks(parts, connection_graph(parts, occ), W.shape)
    stats["seed"] = seed
    return parts, stats, W
