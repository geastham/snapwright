"""Hinged panels (clicked on at an angle) and hand-placed curved tiles."""
import numpy as np
import pytest

from conftest import Model, model_from_src, solve
from oracles import check_model
from snapwright.hinge import (AXIS_BEYOND_MM, AXIS_BELOW_TOP_MM, HingeSpec, placed_geometry,
                              spec_from_json, tile_cells)

LANTERN = '''
model = Model(28, 16, 30, title="Hinge Test")
model.box(2, 2, 0, 12, 14, 20, "light_bluish_gray")
face = model.hinged_panel("Face", toward="+x", angle=45, edge=12, y=20, at=2, width=12, height=12,
                          depth=3, hinges=(4, 11))
face.box(0, 0, 0, 12, 12, 3, "green")
face.box(2, 2, 1, 10, 10, 2, "black")
face.box(2, 1, 2, 10, 2, 3, "black")
face.box(2, 10, 2, 10, 11, 3, "black")
for rot, (x, z) in enumerate([(6, 6), (2, 6), (2, 2), (6, 2)]):
    face.place("27507", x, z, "black", rot=rot)
for rot, (x, z) in enumerate([(6, 6), (4, 6), (4, 4), (6, 4)]):
    face.place("27925", x, z, "light_bluish_gray", rot=rot)
face.place("14769", 5, 5, "bright_green")
'''


@pytest.mark.parametrize("toward", [0, 1, 2, 3])
@pytest.mark.parametrize("angle", [22.5, 45, 67.5])
def test_frame_and_hinge_geometry(toward, angle):
    sp = HingeSpec("F", toward, angle, edge=10, y=20, a0=4, W=8, H=6, D=2, hinges=(5, 10))
    R = sp.rotation()
    assert np.allclose(R.T @ R, np.eye(3)) and np.isclose(np.linalg.det(R), 1.0)
    r, n, d = sp.frame()
    assert np.isclose(np.degrees(np.arcsin(-d[1])), angle)            # rows run down the slope
    assert n[1] > 0 and np.isclose(r[1], 0)                           # the face looks up and out
    # the moving plate's top, at its hinge end, sits 4 mm down the slope and 0.8 mm out from the
    # axis, like the fixed plate's does on the flat
    A = sp.axis_point()
    end = sp.to_world(0, 3.2, 0)
    assert np.allclose(end - A, AXIS_BELOW_TOP_MM * n + AXIS_BEYOND_MM * d)
    # the fixed plates end at `edge`, the axis half a stud beyond towards the panel
    for h in sp.hinges:
        cells = sp.fixed_cells(h)
        along = [c[0] if toward in (0, 2) else c[1] for c in cells]
        s = sp.sign()
        assert (max(along) + 1 == sp.edge) if s > 0 else (min(along) == sp.edge)
        assert 0 <= sp.column_of(h) < sp.W
    assert np.isclose(A[1], 21 * 3.2 - 0.8)


def test_curved_tile_outlines_grip_the_right_studs():
    # a 2x2 macaroni (quarter ring r 1-2 about its corner) grips the two studs on the ring
    pts, org, dx, dz = placed_geometry("27925", 4, 4, 0)
    covers, grips, clash = tile_cells(pts, dx, dz, 4, 4)
    assert (dx, dz, org) == (2, 2, (4.5, 4.5)) and grips == {(4, 5), (5, 4)}
    assert (5, 5) in covers and (5, 5) not in grips                   # the corner stud is under the rim
    # a quarter turn moves the ring's centre round the footprint's corners
    centres = []
    for k in range(4):
        pts, _, _, _ = placed_geometry("27507", 2, 2, k)
        xs, zs = [p[0] for p in pts], [p[1] for p in pts]
        centres.append((min(xs) if k in (0, 3) else max(xs), min(zs) if k in (0, 1) else max(zs)))
    assert centres == [(2, 2), (6, 2), (6, 6), (2, 6)]
    # a round 2x2 tile sits on all four studs
    pts, _, dx, dz = placed_geometry("14769", 5, 5, 0)
    assert tile_cells(pts, dx, dz, 5, 5)[1] == {(5, 5), (5, 6), (6, 5), (6, 6)}


def test_dsl_rules():
    m = Model(20, 12, 30)
    m.box(0, 0, 0, 10, 12, 20, "white")
    with pytest.raises(ValueError, match="22.5"):
        m.hinged_panel("P", toward="+x", angle=30, edge=10, y=20, at=2, width=8, height=6)
    pn = m.hinged_panel("P", toward="+x", angle=45, edge=10, y=20, at=2, width=8, height=6)
    assert pn.spec.hinges == (4, 7)                                   # a quarter in from each side
    assert (m.V[8:10, 4, 20] == 0).all()                              # hinge cells kept free
    with pytest.raises(ValueError, match="no outline"):
        pn.place("3001", 0, 0, "red")
    m2 = Model(12, 12, 20)
    m2.box(1, 1, 0, 11, 11, 16, "white")
    side = m2.panel("S", face="+z", at=2, width=4, height=4)
    with pytest.raises(ValueError, match="hinged panels"):
        side.place("27925", 0, 0, "red")


def test_lantern_face_builds_and_checks(cat):
    m = model_from_src(LANTERN)
    model, built = solve(m, catalog=cat, seeds=1)
    st = model["stats"]
    assert st["passed"], st["failures"]
    check_model(model, m.V, built, m.palette)
    sb = model["subassemblies"][0]
    assert sb["spec"]["mount"] == "hinge" and sb["hinges"] == 2 and sb["curved"] == 9
    assert sb["held"] == len(sb["parts"]) and not sb["failures"]
    fixed = [p for p in model["parts"] if p["part"] == "44302"]
    assert len(fixed) == 2 and all(p["y"] == 20 and p["dir"] == 0 for p in fixed)
    moving = [q for q in sb["parts"] if q["part"] == "44301"]
    assert len(moving) == 2 and all(q["y"] == 0 for q in moving)
    # the top layer is tiles and curved tiles only: no studs showing on the face
    top = max(q["y"] for q in sb["parts"])
    assert all(q["kind"] in ("tile", "tile_curved") or q.get("shape") == "outline"
               for q in sb["parts"] if q["y"] == top)
    kinds = [(s["kind"], s.get("sub")) for s in model["steps"]]
    assert kinds[-1] == ("attach", "Face")                           # the face goes on last
    assert any("clicked on at 45 degrees with 2 locking hinges" in t for _, t in
               __import__("snapwright.validate", fromlist=["x"]).report_lines(st))
    assert sum(q for *_, q in model["bom"]) == st["parts"]


def test_lantern_exports_render_and_viewer(cat, tmp_path):
    from snapwright import exporters, pipeline
    from snapwright.render import render_parts
    m = model_from_src(LANTERN)
    model, _ = solve(m, catalog=cat, seeds=1)
    text = exporters.to_ldraw(model, cat)
    files = exporters.split_mpd(text)
    face = files["hinge-test-face.ldr"]
    assert face.count("27507.dat") == 4 and face.count("44301b.dat") == 2
    key = lambda p: (p["part"], p["color"], p["x"], p["z"], p["y"])  # noqa: E731
    assert sorted(map(key, exporters.parse_ldraw(face, cat))) == sorted(map(key, model["subassemblies"][0]["parts"]))
    T, P = exporters.panel_placement(spec_from_json(model["subassemblies"][0]["spec"]))
    assert np.isclose(np.linalg.det(P), 1.0)
    xml = exporters.to_bricklink_xml(model["parts"] + model["subassemblies"][0]["parts"], cat)
    assert "<ITEMID>27507</ITEMID>" in xml and "<ITEMID>44302</ITEMID>" in xml
    sb = model["subassemblies"][0]
    cols = {q["id"]: cat.colors[q["color"]]["hex"] for q in sb["parts"]}
    flat = render_parts(sb["parts"], tuple(sb["grid"]), cols, cat, view=0, size=(300, 300))
    on = render_parts(model["parts"], tuple(model["grid"]["shape"]),
                      {p["id"]: cat.colors[p["color"]]["hex"] for p in model["parts"]}, cat, view=0,
                      panels=[dict(spec=spec_from_json(sb["spec"]), parts=sb["parts"], colors=cols)],
                      size=(300, 300))
    for im in (flat, on):
        assert im.getbbox() is not None
    # the face's colours show up in the picture of the whole model
    px = np.asarray(on.convert("RGB")).reshape(-1, 3)
    assert (np.abs(px - np.array([0x4B, 0x9F, 0x4A])).sum(1) < 60).any() or \
        (np.abs(px - np.array([0x55, 0xAA, 0x55])).sum(1) < 80).any()
    out = tmp_path / "v.html"
    pipeline.write_viewer(model, str(out), cat)
    html = out.read_text()
    assert '"mount":"hinge"' in html and '"outline":' in html


def test_order_lists_include_the_panel(cat, tmp_path):
    import csv
    import re
    from snapwright import pipeline
    design = tmp_path / "design.py"
    design.write_text(LANTERN)
    model = pipeline.build(str(design), str(tmp_path / "out"), catalog=cat, seeds=1, book=False,
                           viewer=False, log=lambda *a: None)
    total = model["stats"]["parts"]
    rows = list(csv.DictReader(open(tmp_path / "out" / "hinge-test-parts.csv")))
    assert sum(int(r["Qty"]) for r in rows) == total
    assert any(r["Part ID"] == "27507" for r in rows)
    xml = (tmp_path / "out" / "hinge-test-bricklink.xml").read_text()
    assert sum(int(q) for q in re.findall(r"<MINQTY>(\d+)</MINQTY>", xml)) == total
