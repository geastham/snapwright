"""Order parts into build steps a person can follow.

Rules
  * Bottom-up by plate level; each step holds parts from one level (or a deferred overhang).
  * Every part must click onto something already placed (or the table) when its step comes,
    and there must be room to put it on: pressed down while nothing is placed directly above
    it, or pressed up from below while nothing is placed directly below it.
    Parts that only connect to parts above them (overhangs) are deferred and pushed on
    from below right after their anchor is placed. Deferred parts are re-checked until
    nothing changes, so a part whose support was itself deferred is still pressed down
    before anything covers it.
  * Steps are grown as compact regions (finish one area before starting the next), capped
    at `max_per_step` parts, fewer for young builders. Colour is a tie-breaker.
  * A camera view (quarter turn, 0-3) is chosen per level from which view actually shows
    the new parts (a coarse id-buffer render), with hysteresis so the model doesn't spin
    every page.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict

from .render import model_grid, visible_samples

AUDIENCE_MAX = {"kids": 4, "family": 7, "adult": 12, "expert": 20}


def plan_steps(parts, edges, shape, max_per_step=8):
    n = len(parts)
    nbrs = defaultdict(set)
    below = defaultdict(set)
    above = defaultdict(set)
    for (i, j) in edges:
        nbrs[i].add(j)
        nbrs[j].add(i)
        above[i].add(j)
        below[j].add(i)
    placed = [False] * n
    steps = []
    # parts directly above / below each part (touching, connected or not)
    import numpy as np
    occ = -np.ones(shape, dtype=np.int64)
    for p in parts:
        occ[p["x"]:p["x"] + p["dx"], p["z"]:p["z"] + p["dz"], p["y"]:p["y"] + p["h"]] = p["id"]
    over, under = defaultdict(set), defaultdict(set)
    for p in parts:
        top, bot = p["y"] + p["h"], p["y"] - 1
        fx = (slice(p["x"], p["x"] + p["dx"]), slice(p["z"], p["z"] + p["dz"]))
        if top < shape[2]:
            over[p["id"]] = {int(q) for q in np.unique(occ[fx[0], fx[1], top]) if q >= 0}
        if bot >= 0:
            under[p["id"]] = {int(q) for q in np.unique(occ[fx[0], fx[1], bot]) if q >= 0}

    def no_sandwich(batch, from_below=False):
        """Keep parts that don't close the last open side of a part still waiting to go on
        (it would be trapped between two placed parts); the rest go in a later batch.
        Accepted one at a time: bottom-up when pressing down, top-down when pressing up."""
        order = sorted(batch, key=lambda i: (parts[i]["y"], i), reverse=from_below)
        waiting = set(pending) - set(batch)
        taken: set = set()

        def shut(ids):
            return any(placed[r] or r in taken for r in ids)
        for c in order:
            # c shuts the top of a waiting part under it (trapped if its bottom is shut) and
            # the bottom of a waiting part over it (trapped if its top is shut)
            if any(q in waiting and shut(under[q]) for q in under[c]) or \
                    any(q in waiting and shut(over[q]) for q in over[c]):
                continue
            taken.add(c)
        return [c for c in batch if c in taken] or batch[:1]
    by_level = defaultdict(list)
    for p in parts:
        by_level[p["y"]].append(p["id"])
    pending = []  # overhangs waiting for an anchor

    def placeable(pid):
        return parts[pid]["y"] == 0 or any(placed[q] for q in nbrs[pid])

    level = 0

    def emit(ids, kind="build"):
        if not ids:
            return
        for chunk in cluster(parts, ids, max_per_step):
            for i in chunk:
                placed[i] = True
            steps.append({"parts": chunk, "kind": kind, "level": level})

    for y in sorted(by_level):
        level = y
        ready, later = [], []
        for pid in by_level[y]:
            (ready if placeable(pid) else later).append(pid)
        # bricks connect to plates at the same level placed in the same step batch
        progress = True
        while later and progress:
            progress = False
            for pid in list(later):
                if any(q in ready for q in nbrs[pid]):
                    ready.append(pid)
                    later.remove(pid)
                    progress = True
        emit(ready)
        pending.extend(later)
        # place deferred parts that can now go on, until nothing changes: first those that
        # sit on something placed (pressed down as usual), then true overhangs (pressed up)
        while pending:
            down = [pid for pid in pending if any(placed[q] for q in below[pid])]
            up = [] if down else [pid for pid in pending if any(placed[q] for q in above[pid])]
            # a chain of overhangs goes on one link per step, top link first
            up = [pid for pid in up if not (above[pid] & set(up))]
            now = no_sandwich(down) if down else no_sandwich(up, from_below=True)
            if not now:
                break
            pending = [pid for pid in pending if pid not in set(now)]
            emit(now, kind="build" if down else "overhang")
    if pending:  # anything left is unreachable; put it last so the checks flag it
        emit(pending, kind="unanchored")

    for i, st in enumerate(steps):
        st["n"] = i + 1
        for pid in st["parts"]:
            parts[pid]["step"] = i + 1
    choose_views(parts, steps, shape)
    return steps


def cluster(parts, ids, max_per_step):
    """Split one batch into steps of compact regions: grow each step from a seed by adding
    the part nearest its centroid (a different colour costs a little extra distance), then
    seed the next step next to where the last one ended, so the build sweeps round."""
    if len(ids) <= max_per_step:
        return [sorted(ids)]
    k = math.ceil(len(ids) / max_per_step)
    size = math.ceil(len(ids) / k)
    c = {i: (parts[i]["x"] + parts[i]["dx"] / 2, parts[i]["z"] + parts[i]["dz"] / 2) for i in ids}
    mx = sum(p[0] for p in c.values()) / len(c)
    mz = sum(p[1] for p in c.values()) / len(c)
    left = set(ids)
    # start at the part farthest from the middle (an outer edge), lowest id on ties
    seed = max(sorted(left), key=lambda i: (c[i][0] - mx) ** 2 + (c[i][1] - mz) ** 2)
    out = []
    while left:
        group, gx, gz = [seed], c[seed][0], c[seed][1]
        left.discard(seed)
        colours = Counter([parts[seed]["color"]])
        while left and len(group) < size:
            main = colours.most_common(1)[0][0]
            nxt = min(sorted(left), key=lambda i: math.hypot(c[i][0] - gx, c[i][1] - gz)
                      + (1.5 if parts[i]["color"] != main else 0.0))
            group.append(nxt)
            left.discard(nxt)
            colours[parts[nxt]["color"]] += 1
            gx += (c[nxt][0] - gx) / len(group)
            gz += (c[nxt][1] - gz) / len(group)
        out.append(sorted(group))
        if left:
            lx, lz = c[group[-1]]
            seed = min(sorted(left), key=lambda i: math.hypot(c[i][0] - lx, c[i][1] - lz))
    return out


def choose_views(parts, steps, shape, min_gain=0.15):
    """One camera view per level: the quarter turn that shows the most of that level's new
    parts (id-buffer visibility on the model as it stands after the level). Keep the current
    view unless another shows clearly more, so the reader turns the model rarely."""
    groups = defaultdict(list)
    for st in steps:
        groups[st["level"]].append(st)
    view = 0
    for lv in sorted(groups):
        sts = groups[lv]
        new = [pid for st in sts for pid in st["parts"]]
        G = model_grid(parts, shape, upto_step=sts[-1]["n"])
        scores = []
        for k in range(4):
            seen = visible_samples(G, k)
            shown = sum(1 for pid in new if seen.get(pid, 0) >= 2)
            scores.append(shown + 1e-4 * sum(seen.get(pid, 0) for pid in new))
        best = max(range(4), key=lambda k: (scores[k], -((k - view) % 4 != 0)))
        if scores[best] - scores[view] > max(1.0, min_gain * len(new)):
            view = best
        for st in sts:
            st["view"] = view
        # a step whose new parts hide in the level's view (a plate down between bricks, say)
        # turns for that step only, to the view that shows the most of them
        for st in sts:
            Gs = model_grid(parts, shape, upto_step=st["n"])
            here = visible_samples(Gs, view)
            if sum(1 for pid in st["parts"] if here.get(pid, 0) < 2) < 2:
                continue
            per = [here if k == view else visible_samples(Gs, k) for k in range(4)]
            shown = [sum(1 for pid in st["parts"] if per[k].get(pid, 0) >= 2) for k in range(4)]
            hidden = len(st["parts"]) - shown[view]
            if hidden >= max(2, 0.25 * len(st["parts"])):
                best = max(range(4), key=lambda k: (shown[k], k == view))
                if shown[best] > shown[view]:
                    st["view"] = best
