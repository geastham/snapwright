"""Model.hollow: hollow shells with internal bracing still pass the checks, and hollowing
never changes what can be seen."""
import numpy as np

from conftest import Model, solve
from oracles import check_model, visible

BOX = dict(w=20, d=20, h=30)


def _box(color="tan"):
    m = Model(BOX["w"], BOX["d"], BOX["h"])
    m.box(0, 0, 0, BOX["w"], BOX["d"], BOX["h"], color)
    return m


def _egg():
    m = Model(22, 22, 50)
    m.ellipsoid(11, 22, 11, 10.5, 22, 10.5, "white")
    m.paint(lambda X, Y, Z: Y < 8, "dark_bluish_gray")
    return m


def test_hollow_keeps_the_visible_surface():
    for make in (_box, _egg):
        m = make()
        before = m.V.copy()
        vis = visible(before)
        m.hollow(wall=2)
        assert (m.V[vis] == before[vis]).all(), "hollowing changed a visible cell"
        assert m.voxel_count() < 0.75 * (before > 0).sum()


def test_hollow_leaves_walls_caps_and_braces():
    m = _box()
    m.hollow(wall=2, cap=3, brace_every=8, brace=2)
    V = m.V > 0
    assert V[:2].all() and V[:, :2].all() and V[:, :, :3].all() and V[:, :, -3:].all()
    inside = ~V[2:-2, 2:-2, 3:-3]
    assert inside.any()
    # braces: some interior columns stay solid from floor to ceiling
    cols = V[2:-2, 2:-2, 3:-3].all(axis=2)
    assert cols.sum() >= 4 and not cols.all()


def test_hollow_box_builds_with_no_major_weak_points():
    solid, _ = solve(_box(), seeds=2)
    m = _box()
    m.hollow(wall=2)
    model, built = solve(m, seeds=2)
    st = model["stats"]
    assert st["passed"], st["failures"]
    check_model(model, m.V, built, m.palette)
    # hidden solid interiors already pack into big bricks, so hollowing saves plastic (mass,
    # cost), not part count; it must not cost many more parts either
    assert st["mass_g"] < 0.75 * solid["stats"]["mass_g"]
    assert st["parts"] < 1.1 * solid["stats"]["parts"]
    assert not [n for n in st["necks"] if n["parts_above"] > 0.05 * st["parts"]], st["necks"][:3]


def test_hollow_egg_passes_balance_and_necks():
    m = _egg()
    m.hollow(wall=2)
    model, built = solve(m, seeds=2)
    st = model["stats"]
    assert st["passed"], st["failures"]
    check_model(model, m.V, built, m.palette)
    assert st["com_margin_mm"] >= 3
    assert not [n for n in st["necks"] if n["parts_above"] > 0.05 * st["parts"]], st["necks"][:3]


def test_hollow_open_bottom():
    m = _box()
    m.hollow(wall=2, floor=False)
    assert not (m.V[5:15, 5:15, 0] > 0).all()           # the floor is open inside the walls
    assert (m.V[:2, :, 0] > 0).all()                     # walls still reach the table
