"""Sideways panels (SNOT): geometry, anchoring, per-panel checks and steps."""
import numpy as np
import pytest
from PIL import Image

from conftest import Model, model_from_src, solve
from oracles import check_model
from snapwright.snot import SIDE_STUD_MM, PanelSpec

HEAD = '''
model = Model(12, 12, 36, title="Robot Head")
model.box(1, 1, 0, 11, 11, 33, "light_bluish_gray")
face = model.panel("Face", face="+z", at=2, top=30, width=8, height=8, depth=2)
face.box(0, 0, 0, 8, 8, 1, "black")
face.box(0, 0, 1, 8, 8, 2, "light_bluish_gray")
face.box(1, 1, 1, 3, 3, 2, "medium_azure")
face.box(5, 1, 1, 7, 3, 2, "medium_azure")
face.box(2, 5, 1, 6, 6, 2, "red")
'''


@pytest.mark.parametrize("face", [0, 1, 2, 3])
def test_frame_is_a_rotation_and_rows_line_up_with_side_studs(face):
    sp = PanelSpec("P", face, a0=2, plane=10, top=30, W=6, H=8, D=2)
    R = sp.rotation()
    assert np.allclose(R.T @ R, np.eye(3)) and np.isclose(np.linalg.det(R), 1.0)
    r, n, down = sp.frame()
    assert np.allclose(down, [0, -1, 0])
    # seen from in front of the face (camera out along n, up +y), panel x runs to the right
    cam_right = np.cross(-n, [0, 1, 0])
    assert np.allclose(r, cam_right)
    for j, p in sp.anchor_rows():
        row_centre = sp.to_world(0, 0, (j + 0.5) * 8.0)[1]
        stud = p * 3.2 + SIDE_STUD_MM
        assert abs(row_centre - stud) < 1e-9, (j, p)


def test_panel_carves_its_space_and_base_moves_it():
    m = Model(12, 12, 36)
    m.box(1, 1, 0, 11, 11, 33, "red")
    pn = m.panel("P", face="+z", at=2, top=30, width=8, height=8)
    x0, x1, z0, z1, y0, y1 = pn.spec.main_region()
    assert (m.V[x0:x1, z0:z1, y0:y1] == 0).all() and pn.spec.plane == 11
    m.base(layers=2, margin=1)
    assert pn.spec.top == 32 and pn.spec.plane == 11 and pn.spec.a0 == 2


def test_robot_head_builds_with_an_attached_panel():
    m = model_from_src(HEAD)
    model, built = solve(m, seeds=2)
    st = model["stats"]
    assert st["passed"], st["failures"]
    check_model(model, m.V, built, m.palette)
    sub = model["subassemblies"][0]
    assert sub["name"] == "Face" and sub["anchor_studs"] >= 2 and sub["held"] == len(sub["parts"])
    anchors = [p for p in model["parts"] if p.get("anchor") == "Face"]
    assert anchors and all(p["shape"] == "snot" and p["dir"] == 1 for p in anchors)
    kinds = [(s["kind"], s.get("sub")) for s in model["steps"]]
    attach = kinds.index(("attach", "Face"))
    first_sub = kinds.index(("subassembly", "Face"))
    assert first_sub < attach
    last_anchor = max(p["step"] for p in anchors)
    assert last_anchor < model["steps"][first_sub]["n"]
    ids = sorted(pid for s in model["steps"] if s.get("sub") == "Face" for pid in s["parts"])
    assert ids == list(range(len(sub["parts"])))
    assert [s["n"] for s in model["steps"]] == list(range(1, len(model["steps"]) + 1))
    assert st["parts"] == len(model["parts"]) + len(sub["parts"])
    assert sum(q for *_, q in model["bom"]) == st["parts"]


def test_panel_with_nothing_behind_it_fails():
    m = Model(12, 12, 36)
    m.box(1, 1, 0, 11, 11, 33, "white")
    m.box(2, 2, 3, 10, 11, 33, None)                         # hollow: no wall behind the face
    m.box(1, 1, 33, 11, 11, 36, "white")
    pn = m.panel("Sign", face="+z", at=2, plane=11, top=30, width=8, height=8)
    pn.box(0, 0, 0, 8, 8, 2, "red")
    model, _ = solve(m, seeds=1)
    st = model["stats"]
    assert not st["passed"]
    assert any("Sign" in f and "side stud" in f for f in st["failures"]), st["failures"]


def test_panel_mosaic_reads_upright(tmp_path):
    img = np.zeros((4, 4, 3), np.uint8)
    img[0], img[-1] = (180, 0, 0), (30, 90, 170)                # red top row, blue bottom row
    path = tmp_path / "flag.png"
    Image.fromarray(img).resize((32, 32), Image.NEAREST).save(path)
    m = Model(10, 10, 40)
    m.box(1, 1, 0, 9, 9, 36, "white")
    pn = m.panel("Flag", face="+z", at=3, top=30, width=4, height=4, depth=2)
    pn.mosaic(str(path), colors=["red", "blue", "black"])
    top_row = {pn.palette[v - 1] for v in pn.V[:, 0, 1]}
    bottom_row = {pn.palette[v - 1] for v in pn.V[:, 3, 1]}
    assert top_row == {"red"} and bottom_row == {"blue"}
