import numpy as np

from conftest import Catalog, Model, solve
from snapwright.brickify import FitMaps, Packer, _shapes, exterior_visible, see_through


def test_sealed_interior_is_hidden():
    V = np.zeros((6, 6, 6), dtype=np.int16)
    V[:, :, :] = 1
    vis = exterior_visible(V)
    assert not vis[2, 2, 2] and vis[0, 0, 0] and vis[3, 3, 5]
    assert not exterior_visible(V)[2, 2, 0]


def test_see_through_cells_expose_what_is_behind():
    V = np.ones((5, 5, 5), dtype=np.int16)
    V[0, :, :] = 2                                         # a transparent face
    clear = see_through(V, ["white", "trans_clear"])
    assert not exterior_visible(V)[1, 2, 2]
    assert exterior_visible(V, clear)[1, 2, 2]


def _brute_fits(free, col, under, x, z, dx, dz):
    NX, NZ = free.shape
    if x < 0 or z < 0 or x + dx > NX or z + dz > NZ or not free[x:x + dx, z:z + dz].all():
        return None
    sub = col[x:x + dx, z:z + dz]
    if (sub < 0).any() or len(np.unique(sub[sub > 0])) > 1:
        return None
    if under is not None and not under[x:x + dx, z:z + dz].any():
        return None
    v = sub[sub > 0]
    return int(v[0]) if len(v) else 0


def test_fitmaps_match_brute_force(cat):
    rng = np.random.default_rng(1)
    shapes = _shapes(cat.of_kind("plate"))
    for _ in range(20):
        free = rng.random((9, 7)) < 0.8
        col = rng.integers(-1, 3, (9, 7)) * (rng.random((9, 7)) < 0.5)
        under = rng.random((9, 7)) < 0.5
        fm = FitMaps(shapes, free, col, under)
        for k, (t, rot, dx, dz) in enumerate(shapes):
            for x in range(9):
                for z in range(7):
                    want = _brute_fits(free, col, under, x, z, dx, dz)
                    assert fm.ok[k][x, z] == (want is not None), (t.id, rot, x, z)
                    if want is not None:
                        assert fm.color[k][x, z] == want


def test_packing_is_deterministic_per_seed(cat):
    m = Model(10, 10, 12)
    m.cylinder(5, 5, 4.5, 0, 12, "white", inner_r=2)
    m.paint(lambda X, Y, Z: Y % 6 < 3, "red")
    a = Packer(m.V, m.palette, cat, seed=3).run()
    b = Packer(m.V, m.palette, cat, seed=3).run()
    assert a == b


def test_no_tiles_on_the_ground_and_studs_finish(cat):
    m = Model(8, 8, 3)
    m.box(0, 0, 0, 8, 8, 1, "red")
    m.box(2, 2, 1, 6, 6, 3, "blue")
    model, _ = solve(m, catalog=cat, seeds=1)
    assert not any(p["kind"] == "tile" and p["y"] == 0 for p in model["parts"])
    model, _ = solve(m, catalog=cat, seeds=1, finish="studs")
    assert not any(p["kind"] == "tile" for p in model["parts"])


def test_fin_of_another_colour_touching_only_side_on():
    """A red fin standing against a white body touches it only side-on, across visible
    surface cells, so no part can span the colour boundary. The repair recolours one contact
    cell (one plate across the boundary holds the whole stacked fin), not the fin column by
    column."""
    from conftest import model_from_src, solve
    m = model_from_src('''
model = Model(12, 12, 24)
model.box(5, 0, 0, 6, 12, 24, "white")      # a wall one stud thick: both faces show
model.box(6, 5, 0, 11, 6, 12, "red")        # fins on either face
model.box(0, 7, 0, 5, 8, 12, "red")
''')
    model, _ = solve(m, seeds=1)
    st = model["stats"]
    assert st["passed"], st["failures"]
    assert 0 < st["recolored_cells"] <= 4, st["recolored_cells"]
