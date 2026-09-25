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
  * Steps are chunked spatially (row by row) and capped at `max_per_step` parts, fewer
    for young builders.
  * A camera view (quarter turn, 0-3) is chosen per step so new parts face the reader,
    with hysteresis so the model doesn't spin every page.
"""
from __future__ import annotations

from collections import defaultdict

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
    by_level = defaultdict(list)
    for p in parts:
        by_level[p["y"]].append(p["id"])
    pending = []  # overhangs waiting for an anchor
    NX, NZ, _ = shape
    cx, cz = NX / 2, NZ / 2

    def placeable(pid):
        return parts[pid]["y"] == 0 or any(placed[q] for q in nbrs[pid])

    def emit(ids, kind="build"):
        if not ids:
            return
        # spatial chunking: sort by row then column, split evenly
        ids = sorted(ids, key=lambda i: (parts[i]["color"], parts[i]["z"] // 4, parts[i]["x"]))
        k = max(1, -(-len(ids) // max_per_step))
        size = -(-len(ids) // k)
        for s in range(0, len(ids), size):
            chunk = ids[s:s + size]
            for i in chunk:
                placed[i] = True
            steps.append({"parts": chunk, "kind": kind})

    for y in sorted(by_level):
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
            now = down or up
            if not now:
                break
            pending = [pid for pid in pending if pid not in set(now)]
            emit(now, kind="build" if down else "overhang")
    if pending:  # anything left is unreachable; put it last so the checks flag it
        emit(pending, kind="unanchored")

    # views: decided per plate level (not per step) from where that level's parts sit,
    # with strong hysteresis, so the reader isn't asked to turn the model every page
    level_parts = defaultdict(list)
    for st in steps:
        level_parts[parts[st["parts"][0]]["y"]].extend(st["parts"])
    view, level_view = 0, {}
    faces = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
    for y in sorted(level_parts):
        ids = level_parts[y]
        mx = sum(parts[i]["x"] + parts[i]["dx"] / 2 for i in ids) / len(ids) - cx
        mz = sum(parts[i]["z"] + parts[i]["dz"] / 2 for i in ids) / len(ids) - cz
        scores = [mx * fx + mz * fz for fx, fz in faces]
        best = max(range(4), key=lambda k: scores[k])
        if scores[best] - scores[view] > max(3.0, 0.25 * max(NX, NZ)):
            view = best
        level_view[y] = view
    for st in steps:
        st["view"] = level_view[parts[st["parts"][0]]["y"]]
    for i, st in enumerate(steps):
        st["n"] = i + 1
        for pid in st["parts"]:
            parts[pid]["step"] = i + 1
    return steps
