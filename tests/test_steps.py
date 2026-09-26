import numpy as np

from conftest import model_from_src, solve
from snapwright.render import model_grid, visible_samples
from snapwright.steps import choose_views, cluster


def part(i, x, z, y, dx=1, dz=1, h=1, color="red", studs=True):
    return {"id": i, "part": "p", "color": color, "x": x, "z": z, "y": y, "dx": dx, "dz": dz,
            "h": h, "studs": studs, "kind": "plate"}


def test_cluster_partitions_and_caps():
    parts = [part(i, i % 10, i // 10, 0) for i in range(47)]
    groups = cluster(parts, list(range(47)), 8)
    flat = sorted(i for g in groups for i in g)
    assert flat == list(range(47))
    assert all(len(g) <= 8 for g in groups)
    assert groups == cluster(parts, list(range(47)), 8)       # deterministic


def test_cluster_is_compact():
    """A 12 x 2 strip in steps of 4 should come out as 2 x 2 blocks, not scattered."""
    parts = [part(i, i % 12, i // 12, 0) for i in range(24)]
    for g in cluster(parts, list(range(24)), 4):
        xs = [parts[i]["x"] for i in g]
        assert max(xs) - min(xs) <= 2, g


def test_view_turns_to_show_parts_behind_a_wall():
    """New plates hidden behind a tall wall on the camera side of view 0 must get a view
    that shows them."""
    parts = [part(0, 0, 0, 0, dx=8, dz=8, color="white")]
    for k in range(8):   # a wall along the camera-facing edges (x = 7 and z = 7), 12 plates tall
        parts.append(part(len(parts), 7, k, 1, h=12))
        if k < 7:
            parts.append(part(len(parts), k, 7, 1, h=12))
    first = len(parts)
    for x in range(2, 5):
        for z in range(2, 5):
            parts.append(part(len(parts), x, z, 1))
    steps = [{"n": 1, "parts": [0], "kind": "build", "level": 0},
             {"n": 2, "parts": list(range(1, first)), "kind": "build", "level": 1},
             {"n": 3, "parts": list(range(first, len(parts))), "kind": "build", "level": 2}]
    for st in steps:
        for pid in st["parts"]:
            parts[pid]["step"] = st["n"]
    choose_views(parts, steps, (8, 8, 14))
    G = model_grid(parts, (8, 8, 14))
    seen0 = visible_samples(G, 0)
    assert sum(seen0.get(i, 0) >= 2 for i in range(first, len(parts))) < 9   # hidden in view 0
    seen = visible_samples(G, steps[2]["view"])
    assert all(seen.get(i, 0) >= 2 for i in range(first, len(parts))), steps[2]["view"]


def test_visible_samples_flat_slab_all_views():
    G = -np.ones((5, 5, 2), int)
    G[:, :, 0] = np.arange(25).reshape(5, 5)
    for k in range(4):
        s = visible_samples(G, k)
        assert all(s.get(i, 0) >= 2 for i in range(25))


def test_every_step_has_a_level_and_view():
    m = model_from_src('model = Model(8, 8, 9)\nmodel.box(0, 0, 0, 8, 8, 9, "blue")')
    model, _ = solve(m, seeds=1)
    for st in model["steps"]:
        assert st["view"] in (0, 1, 2, 3) and "level" in st
