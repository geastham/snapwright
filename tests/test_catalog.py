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
