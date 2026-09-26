from conftest import Catalog, model_from_src, solve
from snapwright.validate import DSU, _hull, _margin, connection_graph, occupancy, validate, verdict


def part(i, x, z, y, dx=1, dz=1, h=1, studs=True):
    return {"id": i, "part": "3024", "color": "red", "x": x, "z": z, "y": y, "dx": dx, "dz": dz,
            "h": h, "studs": studs, "kind": "plate"}


def test_occupancy_counts_collisions():
    parts = [part(0, 0, 0, 0, dx=2), part(1, 1, 0, 0)]
    _, col = occupancy(parts, (3, 3, 3))
    assert col == 1


def test_connection_graph_needs_studs_below():
    parts = [part(0, 0, 0, 0, dx=2, studs=False), part(1, 0, 0, 1, dx=2)]
    occ, _ = occupancy(parts, (2, 1, 2))
    assert connection_graph(parts, occ) == {}
    parts[0]["studs"] = True
    assert connection_graph(parts, occ) == {(0, 1): 2}


def test_floating_and_structures():
    parts = [part(0, 0, 0, 0), part(1, 0, 0, 1), part(2, 3, 0, 2)]
    st = validate(parts, (4, 1, 3))
    assert st["floating"] == 1 and st["structures"] == 2
    ok, fails = verdict(st)
    assert not ok and any("floating" in f for f in fails)


def test_hull_margin_inside_and_outside():
    hull = _hull([(0, 0), (4, 0), (4, 4), (0, 4)])
    assert abs(_margin((2, 2), hull) - 2) < 1e-9
    assert _margin((5, 2), hull) < 0


def test_dsu():
    d = DSU(4)
    d.union(0, 1)
    d.union(2, 3)
    assert d.find(0) == d.find(1) != d.find(2)


def _stack(parts, x, z, y0, y1, dx=1, dz=1):
    for y in range(y0, y1):
        parts.append(part(len(parts), x, z, y, dx=dx, dz=dz))


def test_neck_single_column():
    """A 4x4 block held up by a 1x1 column: the column is a neck."""
    parts = []
    _stack(parts, 0, 0, 0, 3, dx=4, dz=4)
    _stack(parts, 1, 1, 3, 6)
    _stack(parts, 0, 0, 6, 14, dx=4, dz=4)
    necks = validate(parts, (4, 4, 14))["necks"]
    assert necks and min(n["strength"] for n in necks) == 1


def test_neck_on_an_arm_beside_a_strong_body():
    """A heavy arm hangs off a solid body by two studs. The body carries plenty of studs at
    the same height, so a per-level sum misses it; a min-cut per component finds it."""
    parts = []
    _stack(parts, 0, 0, 0, 10, dx=4, dz=4)             # body: 4x4 plates
    parts.append(part(len(parts), 0, 0, 10, dx=3, dz=4))
    _stack(parts, 0, 0, 11, 20, dx=4, dz=4)
    parts.append(part(len(parts), 3, 1, 10, dx=4))     # arm plate x=3..6, gripped at x=3 only
    _stack(parts, 5, 1, 11, 18, dx=2)                  # a lump standing on the arm
    _stack(parts, 6, 1, 4, 10)                         # and a column hanging under it
    st = validate(parts, (8, 4, 20))
    assert st["floating"] == 0
    arm = [n for n in st["necks"] if n["strength"] == 2]
    assert arm, st["necks"]
    assert arm[0]["parts_above"] >= 13


def test_solid_brick_tower_has_no_necks(cat):
    m = model_from_src('model = Model(6, 6, 30)\nmodel.box(0, 0, 0, 6, 6, 30, "blue")')
    model, _ = solve(m, catalog=cat, seeds=1)
    assert model["stats"]["necks"] == []


def test_shaped_connectors():
    """A 2x1 slope has a stud on its back cell only; an inverted slope takes a stud under its
    back cell only. Contacts must follow the cells, not the part's footprint."""
    base = part(0, 0, 0, 0, dx=2)                                   # 1x2 plate under both cells
    slope = dict(part(1, 0, 0, 1, dx=2, h=3), top_cells=[[0, 0]], shape="slope", dir=0)
    over_back = part(2, 0, 0, 4)                                    # on the studded back cell
    over_front = part(3, 1, 0, 4)                                   # on the sloped front cell
    parts = [base, slope, over_back, over_front]
    occ, _ = occupancy(parts, (2, 1, 5))
    e = connection_graph(parts, occ)
    assert e[(0, 1)] == 2 and e[(1, 2)] == 1 and (1, 3) not in e
    inv = dict(part(1, 0, 0, 1, dx=2, h=3), bottom_cells=[[0, 0]], shape="slope_inv", dir=0)
    parts = [base, inv]
    occ, _ = occupancy(parts, (2, 1, 5))
    assert connection_graph(parts, occ) == {(0, 1): 1}
