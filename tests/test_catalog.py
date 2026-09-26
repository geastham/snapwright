import pytest

from snapwright.catalog import Catalog, hex_to_rgb, rgb_to_lab


def test_catalog_loads_parts_and_colours(cat):
    assert {"brick", "plate", "tile"} <= {p.kind for p in cat.parts}
    assert all(not p.studs for p in cat.of_kind("tile"))
    areas = [p.area for p in cat.of_kind("plate")]
    assert areas == sorted(areas, reverse=True)          # biggest first


def test_unknown_colour_is_a_clear_error(cat):
    with pytest.raises(KeyError, match="Unknown colour"):
        cat.color("hot_pink_sparkle")


def test_availability_tiers(cat):
    assert cat.available("3001", "red") in ("likely", "verified")
    limited = [k for k, c in cat.colors.items() if c["tier"] != "core"]
    if limited and not cat.availability:
        assert cat.available("3001", limited[0]) == "unverified"


def test_nearest_colour(cat):
    assert cat.nearest((180, 0, 0)) == "red"
    assert cat.nearest((250, 250, 250)) == "white"
    assert not cat.nearest((255, 255, 0)).startswith("trans")


def test_lab_basics():
    assert hex_to_rgb("#FF8000") == (255, 128, 0)
    L, a, b = rgb_to_lab((255, 255, 255))
    assert abs(L - 100) < 0.5 and abs(a) < 0.5 and abs(b) < 0.5


def test_catalog_env_override(tmp_path, monkeypatch):
    import json
    import shutil
    from snapwright.catalog import DEFAULT_CATALOG
    p = tmp_path / "c.json"
    shutil.copy(DEFAULT_CATALOG, p)
    monkeypatch.setenv("SNAPWRIGHT_CATALOG", str(p))
    assert Catalog().path == str(p)
    assert json.load(open(p))["schema"].startswith("snapwright.catalog")


def test_connection_metadata(cat):
    slope, inv, tile, cheese = (cat.by_id[i] for i in ("3040", "3665", "3070b", "54200"))
    assert slope.local_cells("top") == {(0, 0)} and len(slope.local_cells("bottom")) == 2
    assert len(inv.local_cells("top")) == 2 and inv.local_cells("bottom") == {(0, 0)}
    assert tile.local_cells("top") == set() and len(tile.local_cells("bottom")) == 1
    assert cheese.h == 2 and cheese.local_cells("top") == set()
    for p in cat.parts:                                  # every part is exportable
        assert p.ldraw.endswith(".dat") and p.shape in ("box", "slope", "slope_inv", "round")


def test_place_cells_four_directions(cat):
    from snapwright.catalog import DIRS, place_cells
    t = cat.by_id["4286"]                                  # 3 deep, 1 wide
    for d, (ux, uz) in enumerate(DIRS):
        dx, dz, cell = place_cells(t, 10, 20, d)
        cells = [cell(i, 0) for i in range(3)]
        assert {c[0] for c in cells} <= set(range(10, 10 + dx))
        assert {c[1] for c in cells} <= set(range(20, 20 + dz))
        (bx, bz), (fx, fz) = cells[0], cells[-1]
        assert (fx - bx, fz - bz) == (2 * ux, 2 * uz)      # back row -> low front row along DIRS[d]


def test_schema_01_part_entries_get_box_defaults():
    from snapwright.catalog import _part_type
    t = _part_type({"id": "3001", "name": "Brick 2 x 4", "kind": "brick", "L": 4, "W": 2, "h": 3, "studs": True})
    assert t.shape == "box" and len(t.local_cells("top")) == 8 and t.ldraw == "3001.dat"
