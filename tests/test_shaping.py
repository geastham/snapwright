"""Surface shaping: slopes on tapers, inverted slopes under lips, rounds on columns; never on
boxes or hidden surfaces; always within the invariants."""
from collections import Counter

import numpy as np

from conftest import model_from_src, solve
from oracles import check_model, see_through_mask, visible

SHAPED = '''
model = Model(20, 20, 30, title="Shaped")
model.cone(10, 10, 9.5, 2.5, 0, 16, "white")
model.cone(10, 10, 2.5, 7.5, 16, 26, "red")
model.cylinder(10, 10, 0.8, 26, 30, "black")
'''


def _shapes(model):
    return Counter(p.get("shape", "box") for p in model["parts"])


def test_box_gets_no_shaping():
    model, _ = solve(model_from_src('model = Model(12, 12, 9)\nmodel.box(1, 1, 0, 11, 11, 9, "red")'), seeds=1)
    assert set(_shapes(model)) == {"box"}


def test_taper_flare_and_column_are_shaped():
    m = model_from_src(SHAPED)
    model, built = solve(m, seeds=2)
    sh = _shapes(model)
    assert sh["slope"] > 20 and sh["slope_inv"] > 4 and sh["round"] > 0, sh
    check_model(model, m.V, built, m.palette)
    assert model["stats"]["passed"], model["stats"]["failures"]
    vis = visible(built, see_through_mask(built, m.palette))
    for p in model["parts"]:
        if p.get("shape", "box") != "box":
            box = vis[p["x"]:p["x"] + p["dx"], p["z"]:p["z"] + p["dz"], p["y"]:p["y"] + p["h"]]
            assert box.any(), f"shaped part {p['id']} is entirely hidden"
    assert model["stats"]["shaped_cells"] == sum(p["dx"] * p["dz"] * p["h"] for p in model["parts"]
                                                 if p.get("shape", "box") != "box")


def test_no_shapes_flag():
    m = model_from_src(SHAPED)
    model, built = solve(m, seeds=1, shapes=False)
    assert set(_shapes(model)) == {"box"}
    assert all(p["kind"] in ("brick", "plate", "tile") for p in model["parts"])


def test_shaped_parts_have_per_cell_connectors():
    model, _ = solve(model_from_src(SHAPED), seeds=1)
    for p in model["parts"]:
        if p.get("shape") in ("slope", "slope_inv"):
            cells = {(x, z) for x in range(p["x"], p["x"] + p["dx"]) for z in range(p["z"], p["z"] + p["dz"])}
            assert {tuple(c) for c in p["top_cells"]} <= cells and {tuple(c) for c in p["bottom_cells"]} <= cells
            assert p["dir"] in (0, 1, 2, 3)


def test_schema_02_upgrades():
    from snapwright.pipeline import load_model
    m = load_model({"schema": "snapwright.model/0.2", "meta": {}, "parts": [], "steps": [], "stats": {}})
    assert m["schema"] == "snapwright.model/0.4" and m["meta"]["upgraded_from"] == "snapwright.model/0.2"


def test_cells_under_a_round_keep_their_colour():
    """A round brick leaves its footprint's corners open, so the cells under it show there.
    They must keep their design colour, not take the hidden-filler colour (the model's most
    common one): a yellow 2x2 post on a grey base once showed yellow corners."""
    m = model_from_src('''
model = Model(8, 8, 40)
model.box(1, 1, 0, 7, 7, 2, "light_bluish_gray")
model.box(3, 3, 2, 5, 5, 40, "yellow")
''')
    model, built = solve(m, seeds=1)
    rounds = [p for p in model["parts"] if p.get("shape") == "round"]
    assert rounds, "the lone 2x2 post should become round bricks"
    lowest = min(p["y"] for p in rounds)
    assert lowest == 2
    under = [p for p in model["parts"] if p["y"] <= lowest - 1 < p["y"] + p["h"]
             and p["x"] < 5 and 3 < p["x"] + p["dx"] and p["z"] < 5 and 3 < p["z"] + p["dz"]]
    assert under and all(p["color"] == "light_bluish_gray" for p in under), \
        [(p["part"], p["color"]) for p in under]


ZIGGURAT = '''
model = Model(24, 24, 18)
for k in range(6):
    model.box(2 + k, 2 + k, 3 * k, 22 - k, 22 - k, 3 * k + 3, "red")
'''

PLUS = '''
model = Model(26, 26, 15)
for k in range(5):     # a stepped plus: each arm narrows level by level, inside corners where they meet
    model.box(1 + k, 8 + k, 3 * k, 25 - k, 18 - k, 3 * k + 3, "red")
    model.box(8 + k, 1 + k, 3 * k, 18 - k, 25 - k, 3 * k + 3, "red")
'''


def test_corner_slopes_where_slope_runs_meet():
    """Outside corners of a stepped pyramid and inside corners of a stepped plus get 2 x 2 corner
    slopes, so the runs meet without open triangles; a stepped circle's jags don't."""
    for src, shape, want in ((ZIGGURAT, "slope_cvx", 16), (PLUS, "slope_ccv", 4)):
        m = model_from_src(src)
        model, built = solve(m, seeds=1)
        assert model["stats"]["passed"], model["stats"]["failures"]
        check_model(model, m.V, built, m.palette)
        n = _shapes(model)[shape]
        assert n >= want, (shape, _shapes(model))
    m = model_from_src('''
model = Model(15, 15, 40)
model.cone(7.5, 7.5, 5.5, 1.0, 0, 30, "red")
''')
    model, _ = solve(m, seeds=1)
    sh = _shapes(model)
    assert sh["slope_ccv"] == 0 and sh["slope"] > 10, sh


def test_corner_slopes_round_trip_through_ldraw(cat):
    from snapwright.exporters import parse_ldraw, to_ldraw
    model, _ = solve(model_from_src(ZIGGURAT), seeds=1)
    back = parse_ldraw(to_ldraw(model, cat), cat)
    key = lambda p: (p["part"], p["x"], p["z"], p["y"], p["dx"], p["dz"], p.get("dir", -1) if p["part"] in ("3045", "3046") else 0)   # noqa: E731
    assert sorted(map(key, back)) == sorted(map(key, model["parts"]))
