"""Invariant checks written independently of snapwright.validate, so tests don't grade the
validator with itself. Every check works on plain cells and parts."""
from __future__ import annotations

from collections import deque

import numpy as np


def occupancy(parts, shape):
    occ = -np.ones(shape, dtype=np.int64)
    for p in parts:
        sl = occ[p["x"]:p["x"] + p["dx"], p["z"]:p["z"] + p["dz"], p["y"]:p["y"] + p["h"]]
        assert (sl < 0).all(), f"part {p['id']} collides with {set(sl[sl >= 0].tolist())}"
        sl[...] = p["id"]
    return occ


def contacts(parts, occ):
    """{(lower, upper)} for every stud of a lower part inside an upper part."""
    out = set()
    NX, NZ, NY = occ.shape
    for p in parts:
        if not p["studs"]:
            continue
        top = p["y"] + p["h"]
        if top >= NY:
            continue
        above = occ[p["x"]:p["x"] + p["dx"], p["z"]:p["z"] + p["dz"], top]
        for q in set(above[above >= 0].tolist()):
            out.add((p["id"], q))
    return out


def visible(V, see_through=None):
    """Filled cells next to air (or see-through cells) reachable from outside; the table
    underneath is not an opening. Plain BFS, deliberately naive."""
    NX, NZ, NY = V.shape
    open_ = V == 0
    if see_through is not None:
        open_ = open_ | see_through
    outside = np.zeros((NX + 2, NZ + 2, NY + 1), dtype=bool)
    pad = np.ones((NX + 2, NZ + 2, NY + 1), dtype=bool)
    pad[1:-1, 1:-1, :NY] = open_
    q = deque([(0, 0, NY)])
    outside[0, 0, NY] = True
    while q:
        x, z, y = q.popleft()
        for a, b, c in ((x + 1, z, y), (x - 1, z, y), (x, z + 1, y), (x, z - 1, y), (x, z, y + 1), (x, z, y - 1)):
            if 0 <= a < NX + 2 and 0 <= b < NZ + 2 and 0 <= c < NY + 1 and pad[a, b, c] and not outside[a, b, c]:
                outside[a, b, c] = True
                q.append((a, b, c))
    vis = np.zeros(V.shape, dtype=bool)
    for x, z, y in np.argwhere(V > 0):
        X, Z = x + 1, z + 1
        nb = [(X + 1, Z, y), (X - 1, Z, y), (X, Z + 1, y), (X, Z - 1, y), (X, Z, y + 1)]
        if y > 0:
            nb.append((X, Z, y - 1))
        vis[x, z, y] = any(outside[n] for n in nb)
    return vis


def see_through_mask(V, palette):
    clear = np.zeros(V.shape, dtype=bool)
    for i, k in enumerate(palette):
        if k.startswith("trans"):
            clear |= V == i + 1
    return clear


def reachable_from_ground(parts, edges):
    nbr = {p["id"]: set() for p in parts}
    for i, j in edges:
        nbr[i].add(j)
        nbr[j].add(i)
    seen = {p["id"] for p in parts if p["y"] == 0}
    q = deque(seen)
    while q:
        i = q.popleft()
        for j in nbr[i]:
            if j not in seen:
                seen.add(j)
                q.append(j)
    return seen


def check_steps(parts, steps, occ, edges):
    """Every part appears in exactly one step, and when its step comes it can physically be
    put on: pressed down onto a placed part below (nothing placed directly above it yet), or
    pressed up into a placed part above (nothing placed directly below it)."""
    NY = occ.shape[2]
    step_of = {}
    for st in steps:
        for pid in st["parts"]:
            assert pid not in step_of, f"part {pid} in two steps"
            step_of[pid] = st["n"]
    assert set(step_of) == {p["id"] for p in parts}, "some parts are in no step"
    below = {p["id"]: set() for p in parts}
    above = {p["id"]: set() for p in parts}
    for i, j in edges:
        above[i].add(j)
        below[j].add(i)
    problems = []
    for p in parts:
        s = step_of[p["id"]]
        before = lambda q: step_of[q] < s                     # noqa: E731
        by_now = lambda q: step_of[q] <= s                    # noqa: E731
        fx = (slice(p["x"], p["x"] + p["dx"]), slice(p["z"], p["z"] + p["dz"]))
        top = p["y"] + p["h"]
        over = occ[fx[0], fx[1], top] if top < NY else np.array([-1])
        under = occ[fx[0], fx[1], p["y"] - 1] if p["y"] > 0 else np.array([-1])
        clear_above = not any(before(q) for q in set(over[over >= 0].tolist()))
        clear_below = not any(by_now(q) and q != p["id"] for q in set(under[under >= 0].tolist()))
        down = (p["y"] == 0 or any(by_now(q) for q in below[p["id"]])) and clear_above
        up = any(before(q) for q in above[p["id"]]) and clear_below and p["studs"]
        if not (down or up):
            problems.append(p["id"])
    return problems


def check_model(model, V_design, V_built, palette):
    """All invariants that must hold for every build, passing or not. Returns the contact set."""
    parts = model["parts"]
    shape = tuple(model["grid"]["shape"])
    st = model["stats"]
    occ = occupancy(parts, shape)                                     # no collisions
    assert st["collisions"] == 0
    assert ((occ >= 0) == (V_built > 0)).all(), "parts don't cover exactly the built voxels"
    clear = see_through_mask(V_built, palette)
    vis = visible(V_built, clear)
    for x, z, y in np.argwhere(vis):                                  # visible colours kept
        p = parts[occ[x, z, y]]
        want = palette[V_built[x, z, y] - 1]
        assert p["color"] == want, f"cell {(x, z, y)} shows {p['color']}, design says {want}"
    changed = (V_design > 0) & (V_built > 0) & (V_design != V_built) & vis
    assert st["recolored_cells"] == int(changed.sum()), "recolour count is not the real change"
    assert st["trimmed_cells"] == int(((V_design > 0) & (V_built == 0)).sum())
    added = int(((V_design == 0) & (V_built > 0)).sum())
    assert st.get("added_cells", 0) == added, "cells added without being counted"
    edges = contacts(parts, occ)
    reach = reachable_from_ground(parts, edges)
    assert st["floating"] == len(parts) - len(reach), "validator disagrees about floating parts"
    if st["passed"]:
        assert len(reach) == len(parts), "PASS but some parts are not reachable from the ground"
        problems = check_steps(parts, model["steps"], occ, edges)
        assert not problems, f"parts that can't be put on when their step comes: {problems[:10]}"
    return edges
