"""Surface shaping: where the voxel surface steps, use slopes, inverted slopes and round parts
instead of square corners. Runs before normal packing and claims its cells first.

A surface-normal pass on the voxel grid. Normals come from the occupancy smoothed over ~1.5
studs, so a slope goes only where the underlying surface really leans (a tall wall whose
outline stair-steps at a diagonal stays square). Only visible surfaces are shaped. Per
horizontal direction d (the way a face points):
  * slope      stair edge of a taper: a cell with air above and air in front (d), and the
               model rising behind it by at most two slope heights before stepping in again
               (so a wall or pillar standing on a flat top is not mistaken for a taper).
               3-plate steps take 45 degree slopes (2 deep) or 33 degree slopes (3 deep);
               2-plate steps take 30 degree slopes. The back row keeps its studs.
  * slope_inv  overhang lip: a cell with air below and in front, backed by a cell that stands
               on the model; the underside becomes a 45 degree chamfer and the part is held
               by its back socket and all its top studs.
  * round      thin columns (1x1 or 2x2 with air all round) become round bricks / plates, and
               the stair-step "teeth" on top of curves (convex corners whose edges both step)
               get a round 1x1 tile (or plate for a studded finish).

Every candidate needs one visible colour (hidden cells are wildcards), must rest on the
model, and avoids cells the repair loop has marked. Choice is greedy and deterministic:
bigger parts first, then bottom-up, then position. Nothing here changes which cells are
filled; the shaped parts change how the surface reads, and are counted and reported.
"""
from __future__ import annotations

import numpy as np

from .catalog import DIRS, place_cells


def _nb(A, ux, uz, fill=False):
    """A shifted so out[x, z] = A[x + ux, z + uz] (out of bounds = fill)."""
    out = np.full(A.shape, fill, dtype=A.dtype)
    NX, NZ = A.shape[:2]
    xs = slice(max(0, -ux), NX - max(0, ux))
    zs = slice(max(0, -uz), NZ - max(0, uz))
    xd = slice(max(0, ux), NX - max(0, -ux) if -ux > 0 else NX)
    zd = slice(max(0, uz), NZ - max(0, -uz) if -uz > 0 else NZ)
    out[xs, zs] = A[xd, zd]
    return out


def _colour(req, cells):
    vals = {int(req[c]) for c in cells} - {0}
    if len(vals) > 1:
        return None
    return vals.pop() if vals else 0


STUD_MM, PLATE_MM = 8.0, 3.2
TILT = 0.35          # a sloped surface: normal at least ~20 degrees from both flat and vertical


def surface_normals(F, sigma_mm=12.0):
    """Outward surface normals of the voxel shape, smoothed over ~1.5 studs in real
    millimetres (so a tall wall reads as vertical even where its outline stair-steps).
    Returns (nx, nz, ny) arrays, unit length where the shape has a surface."""
    from scipy.ndimage import gaussian_filter
    B = gaussian_filter(F.astype(np.float32), sigma=(sigma_mm / STUD_MM, sigma_mm / STUD_MM,
                                                     sigma_mm / PLATE_MM), mode="constant")
    gx, gz, gy = np.gradient(B, STUD_MM, STUD_MM, PLATE_MM)
    n = np.sqrt(gx * gx + gy * gy + gz * gz) + 1e-9
    return -gx / n, -gz / n, -gy / n


def find_shapes(V, req, catalog, finish="tiles", blocked=None, visible=None):
    """Placements for shaped parts: list of dicts {t, x, z, y, dx, dz, h, dir, color,
    top_cells, bottom_cells}. `req` is the required colour per cell (0 = hidden wildcard);
    `blocked` marks cells shaping must leave to the normal packer; `visible` marks cells seen
    from outside (shaping a hidden surface would only cost parts)."""
    NX, NZ, NY = V.shape
    F = V > 0
    visible = np.ones(V.shape, dtype=bool) if visible is None else visible
    nxs, nzs, nys = surface_normals(F)

    def tilted(x, z, y, ux, uz, upward=True):
        """The smoothed surface at this cell leans the way a slope facing (ux, uz) would."""
        ny = nys[x, z, y] if upward else -nys[x, z, y]
        return ny >= TILT and nxs[x, z, y] * ux + nzs[x, z, y] * uz >= TILT
    blocked = np.zeros(V.shape, dtype=bool) if blocked is None else blocked
    taken = np.zeros(V.shape, dtype=bool)
    up = np.zeros_like(F)
    up[:, :, :-1] = F[:, :, 1:]                       # cell above is filled
    down = np.zeros_like(F)
    down[:, :, 1:] = F[:, :, :-1]                     # cell below is filled
    out = []

    def free(cells, y0, h):
        for x, z in cells:
            if not (0 <= x < NX and 0 <= z < NZ) or y0 < 0 or y0 + h > NY:
                return False
            if not F[x, z, y0:y0 + h].all() or taken[x, z, y0:y0 + h].any() \
                    or blocked[x, z, y0:y0 + h].any():
                return False
        return True

    def claim(t, dir_, x, z, y0, dx, dz, cells_ij, colour):
        cells = [c for c, _ in cells_ij]
        for cx, cz in cells:
            taken[cx, cz, y0:y0 + t.h] = True
        top = t.local_cells("top")
        bot = t.local_cells("bottom")
        out.append({"t": t, "x": int(x), "z": int(z), "y": int(y0), "dx": int(dx), "dz": int(dz),
                    "h": t.h, "dir": int(dir_), "color": int(colour),
                    "top_cells": sorted([int(cx), int(cz)] for (cx, cz), ij in cells_ij if ij in top),
                    "bottom_cells": sorted([int(cx), int(cz)] for (cx, cz), ij in cells_ij if ij in bot)})

    def try_place(t, dir_, x, z, y0):
        """Place t with footprint min corner (x, z) facing dir_, bottom at y0, if it fits."""
        dx, dz, cell = place_cells(t, x, z, dir_)
        cells_ij = [(cell(i, j), (i, j)) for i in range(t.L) for j in range(t.W)]
        cells = [c for c, _ in cells_ij]
        if not free(cells, y0, t.h):
            return False
        colour = _colour(req, [(cx, cz, yy) for cx, cz in cells for yy in range(y0, y0 + t.h)])
        if colour is None:
            return False
        if y0 > 0 and not any(F[cx, cz, y0 - 1] for cx, cz in cells):
            return False
        claim(t, dir_, x, z, y0, dx, dz, cells_ij, colour)
        return True

    # ---- round columns: 1x1 / 2x2 with air all round -------------------------------------
    rounds = {(p.L, p.h, p.studs): p for p in catalog.shaped("round")}
    open1 = ~F
    ring1 = np.ones_like(F)
    for ux, uz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ring1 &= _nb(open1, ux, uz, True)
    for y in range(NY):
        for x, z in np.argwhere(F[:, :, y] & ring1[:, :, y]):
            if taken[x, z, y]:
                continue
            h = 3 if (3 <= NY - y and F[x, z, y:y + 3].all() and ring1[x, z, y:y + 3].all()) else 1
            if h == 1 and (y == 0 or not F[x, z, y - 1]):
                continue
            want_studs = h == 3 or finish != "tiles" or up[x, z, y]
            t = rounds.get((1, h, True if h == 3 else want_studs))
            if t is not None:
                try_place(t, 0, x, z, y)
    # 2x2 blocks with nothing around them
    for y in range(NY):
        blk = F[:-1, :-1, y] & F[1:, :-1, y] & F[:-1, 1:, y] & F[1:, 1:, y]
        for x, z in np.argwhere(blk):
            ring = [(x + a, z + b) for a in range(-1, 3) for b in range(-1, 3)
                    if not (0 <= a <= 1 and 0 <= b <= 1)]
            if any(0 <= a < NX and 0 <= b < NZ and F[a, b, y] for a, b in ring):
                continue
            if y > 0 and not F[x:x + 2, z:z + 2, y - 1].any():
                continue
            h = 3 if y + 3 <= NY and F[x:x + 2, z:z + 2, y:y + 3].all() and not any(
                0 <= a < NX and 0 <= b < NZ and F[a, b, y:y + 3].any() for a, b in ring) else 1
            if h == 1 and y == 0:
                continue
            want_studs = h == 3 or finish != "tiles" or up[x:x + 2, z:z + 2, y].any()
            t = rounds.get((2, h, True if h == 3 else want_studs))
            if t is not None:
                try_place(t, 0, x, z, y)

    # ---- slopes on stair edges -------------------------------------------------------------
    slopes = catalog.shaped("slope")        # biggest first: 33 3x2, 45 2x2, 33 3x1, 45 2x1, 30 ...

    def inside(x, z):
        return 0 <= x < NX and 0 <= z < NZ

    def rise(x, z, top):
        """Filled plates straight above `top` in column (x, z). A taper steps in again soon;
        a wall or a pillar rising far behind an edge is not a taper and gets no slope."""
        n = 0
        while top + 1 + n < NY and F[x, z, top + 1 + n]:
            n += 1
        return n

    def edge_ok(t, ux, uz, fx, fz, top):
        """Front (low) cell (fx, fz) with its top plate at `top` is a stair edge facing (ux, uz)
        that slope type t fits: air above and in front, the model continuing up behind."""
        if not inside(fx, fz) or not F[fx, fz, top] or up[fx, fz, top] or not visible[fx, fz, top]:
            return False
        if not tilted(fx, fz, top, ux, uz):
            return False
        nx, nz = fx + ux, fz + uz
        for k in range(min(t.h, 3) - 1):                       # air in front (2 plates for bricks)
            if inside(nx, nz) and F[nx, nz, top - k]:
                return False
        if t.L == 1:                                            # 30 degree: a step rises behind
            bx, bz = fx - ux, fz - uz
            return inside(bx, bz) and F[bx, bz, top] and 1 <= rise(bx, bz, top) <= 2 * t.h
        for k in range(1, t.L - 1):                             # middle rows open above
            if up[fx - k * ux, fz - k * uz, top] if inside(fx - k * ux, fz - k * uz) else True:
                return False
        bx, bz = fx - (t.L - 1) * ux, fz - (t.L - 1) * uz       # back row: model goes on up
        return inside(bx, bz) and 1 <= rise(bx, bz, top) <= 2 * t.h

    cands = []
    for dir_, (ux, uz) in enumerate(DIRS):
        px, pz = (0, 1) if ux else (1, 0)                       # perpendicular (width) axis
        for t in slopes:
            for y0 in range(0, NY - t.h + 1):
                top = y0 + t.h - 1
                m = F[:, :, y0:top + 1].all(2) & ~up[:, :, top]
                for fx, fz in np.argwhere(m):
                    fx, fz = int(fx), int(fz)
                    if all(edge_ok(t, ux, uz, fx + j * px, fz + j * pz, top) for j in range(t.W)):
                        cands.append((-(t.area * t.h), y0, fx, fz, dir_, t))
    cands.sort(key=lambda c: (c[0], c[1], c[2], c[3], c[4], c[5].id))
    for _, y0, fx, fz, dir_, t in cands:
        ux, uz = DIRS[dir_]
        bx, bz = fx - (t.L - 1) * ux, fz - (t.L - 1) * uz
        try_place(t, dir_, min(fx, bx), min(fz, bz), y0)

    # ---- inverted slopes under overhang lips -------------------------------------------------
    def lip_ok(ux, uz, fx, fz, u, h):
        """(fx, fz) at plate u is an overhang lip facing (ux, uz): filled for h plates, air
        below and in front, and backed by a cell that stands on the model."""
        if not inside(fx, fz) or not F[fx, fz, u:u + h].all() or down[fx, fz, u] or not visible[fx, fz, u]:
            return False
        if not tilted(fx, fz, u, ux, uz, upward=False):
            return False
        nx, nz = fx + ux, fz + uz
        if inside(nx, nz) and (F[nx, nz, u] or F[nx, nz, u + 1]):
            return False
        bx, bz = fx - ux, fz - uz
        return inside(bx, bz) and bool(down[bx, bz, u])

    for t in catalog.shaped("slope_inv"):
        for dir_, (ux, uz) in enumerate(DIRS):
            px, pz = (0, 1) if ux else (1, 0)
            for u in range(1, NY - t.h + 1):
                m = F[:, :, u:u + t.h].all(2) & ~down[:, :, u]
                for fx, fz in np.argwhere(m):
                    fx, fz = int(fx), int(fz)
                    if all(lip_ok(ux, uz, fx + j * px, fz + j * pz, u, t.h) for j in range(t.W)):
                        try_place(t, dir_, min(fx, fx - ux), min(fz, fz - uz), u)

    # ---- round 1x1 on convex top corners of curves ---------------------------------------------
    # Only the "teeth" of a stair-stepped curve are rounded: corners where both edges step.
    # A corner with a straight run on either side (a box, or the flat side of a circle) stays
    # square, so walls and rims don't sprout rows of round tiles.
    corner_t = rounds.get((1, 1, finish != "tiles"))
    if corner_t is not None:
        def straight(x, z, y, ax, az, bx, bz):
            """Edge facing (ax, az) runs straight away from open side (bx, bz) for 2 cells."""
            for k in (1, 2):
                cx, cz = x - k * bx, z - k * bz
                if not inside(cx, cz) or not F[cx, cz, y]:
                    return False
                ox, oz = cx + ax, cz + az
                if inside(ox, oz) and F[ox, oz, y]:
                    return False
            return True

        m = F & ~up & down & visible
        for x, z, y in np.argwhere(m):
            x, z, y = int(x), int(z), int(y)
            opens = [not (inside(x + ux, z + uz) and F[x + ux, z + uz, y]) for ux, uz in DIRS]
            for k in range(4):
                if opens[k] and opens[(k + 1) % 4]:
                    (ax, az), (bx, bz) = DIRS[k], DIRS[(k + 1) % 4]
                    if not (straight(x, z, y, ax, az, bx, bz) or straight(x, z, y, bx, bz, ax, az)):
                        try_place(corner_t, 0, x, z, y)
                    break
    return out
