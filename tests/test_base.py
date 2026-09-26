"""Automatic base: a model that would tip gets a 2-plate stand under its footprint, counted
as added support and reported; base='off' leaves the balance failure in place."""
from conftest import Model, solve
from oracles import check_model

TIPPY = dict(w=16, d=6, h=30)


def _tippy():
    m = Model(TIPPY["w"], TIPPY["d"], TIPPY["h"], title="Tippy")
    m.box(0, 1, 0, 3, 5, 24, "red")                   # a slim column...
    m.box(0, 0, 24, 16, 6, 30, "blue")                # ...with a heavy block cantilevered on top
    return m


def test_without_base_it_tips():
    model, _ = solve(_tippy(), seeds=2, base="off")
    st = model["stats"]
    assert not st["passed"] and st["com_margin_mm"] < 3
    assert any("tips over" in f for f in st["failures"])


def test_auto_base_fixes_balance_and_is_counted():
    m = _tippy()
    model, built = solve(m, seeds=2)                   # base="auto" is the default
    st = model["stats"]
    assert st["passed"], st["failures"]
    assert st["com_margin_mm"] >= 3
    assert st["base_cells"] > 0 and st["added_cells"] >= st["base_cells"]
    from snapwright.validate import report_lines
    assert any(k == "change" and "base" in t for k, t in report_lines(st))
    assert model["grid"]["shape"][2] == TIPPY["h"] + 2


def test_explicit_base_is_design_not_repair():
    m = _tippy()
    m.base(layers=2, margin=1)
    model, built = solve(m, seeds=2, base="off")
    st = model["stats"]
    assert st["passed"], st["failures"]
    assert st.get("base_cells", 0) == 0 and st["added_cells"] == 0
    check_model(model, m.V, built, m.palette)


def test_balanced_models_get_no_base():
    m = Model(8, 8, 9)
    m.box(0, 0, 0, 8, 8, 9, "red")
    model, _ = solve(m, seeds=1)
    assert model["stats"].get("base_cells", 0) == 0
