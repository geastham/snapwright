import csv
import io
import xml.etree.ElementTree as ET

from conftest import Catalog, model_from_src, solve
from snapwright import exporters

SRC = '''
model = Model(10, 8, 12, title="Export Test")
model.box(0, 0, 0, 10, 8, 3, "dark_bluish_gray")
model.box(1, 1, 3, 9, 7, 9, "red")
model.box(3, 2, 9, 7, 6, 12, "white")
model.box(9, 0, 3, 10, 2, 5, "yellow")
'''


def _model(cat):
    model, _ = solve(model_from_src(SRC), catalog=cat, seeds=1)
    assert model["stats"]["passed"], model["stats"]["failures"]
    return model


def test_ldraw_round_trip(cat):
    """Export to LDraw and read it back: same parts, colours, positions, sizes and steps.
    Checks the origin (top centre), -Y up, Z flip and the 90 degree turn for Z-long parts."""
    model = _model(cat)
    back = exporters.parse_ldraw(exporters.to_ldraw(model, cat), cat)
    key = lambda p: (p["part"], p["color"], p["x"], p["z"], p["y"], p["dx"], p["dz"], p["h"])
    assert sorted(map(key, back)) == sorted(map(key, model["parts"]))
    step_of = {key(p): p["step"] for p in model["parts"]}
    assert all(step_of[key(p)] == p["step"] for p in back)
    assert any(p["rot"] == 1 for p in model["parts"]), "test should include a Z-long part"


def test_ldraw_header_has_no_brand(cat):
    text = exporters.to_ldraw(_model(cat), cat)
    assert "LEGO" not in text.upper().replace("NOT AFFILIATED", "")
    assert text.count("0 STEP") == len(_model(cat)["steps"])


def test_bricklink_and_rebrickable_quantities_match_bom(cat):
    model = _model(cat)
    total = sum(q for _, _, q in exporters.bom(model["parts"]))
    assert total == len(model["parts"])
    root = ET.fromstring(exporters.to_bricklink_xml(model["parts"], cat))
    assert sum(int(i.find("MINQTY").text) for i in root.iter("ITEM")) == total
    rows = list(csv.DictReader(io.StringIO(exporters.to_rebrickable_csv(model["parts"], cat))))
    assert sum(int(r["Quantity"]) for r in rows) == total
    rows = list(csv.DictReader(io.StringIO(exporters.to_csv(model["parts"], cat))))
    assert {r["Availability"] for r in rows} <= {"verified", "likely", "unverified"}
