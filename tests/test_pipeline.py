import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "snapwright", "scripts"))

from snapwright import pipeline  # noqa: E402
from snapwright.validate import validate, occupancy, connection_graph  # noqa: E402

TINY = '''
model = Model(10, 10, 24, title="Test Tower")
model.cylinder(5, 5, r=4.5, y0=0, y1=3, color="dark_bluish_gray")
model.cone(5, 5, r0=3.5, r1=2.5, y0=3, y1=21, color="white", inner=1.5)
model.paint(lambda X, Y, Z: (Y // 6) % 2 == 1, "red")
model.cone(5, 5, r0=3.8, r1=0.8, y0=21, y1=24, color="red")
'''


def _build(tmp_path, src=TINY, **kw):
    d = tmp_path / "d.py"
    d.write_text(src)
    return pipeline.build(str(d), str(tmp_path / "out"), seeds=3, book=kw.get("book", False),
                          viewer=True, log=lambda *a: None)


def test_tiny_model_passes(tmp_path):
    m = _build(tmp_path)
    s = m["stats"]
    assert s["passed"], s["failures"]
    assert s["collisions"] == 0 and s["floating"] == 0 and s["structures"] == 1


def test_steps_are_feasible_in_order(tmp_path):
    m = _build(tmp_path)
    parts = m["parts"]
    occ, _ = occupancy(parts, tuple(m["grid"]["shape"]))
    edges = connection_graph(parts, occ)
    nbrs = {}
    for i, j in edges:
        nbrs.setdefault(i, set()).add(j)
        nbrs.setdefault(j, set()).add(i)
    placed = set()
    for st in m["steps"]:
        for pid in st["parts"]:
            assert parts[pid]["y"] == 0 or nbrs.get(pid, set()) & (placed | set(st["parts"])), pid
        placed |= set(st["parts"])
    assert len(placed) == len(parts)


def test_exports(tmp_path):
    m = _build(tmp_path)
    out = tmp_path / "out"
    slug = m["meta"]["slug"]
    ldr = (out / f"{slug}.ldr").read_text()
    assert sum(1 for l in ldr.splitlines() if l.startswith("1 ")) == len(m["parts"])
    assert ldr.count("0 STEP") == len(m["steps"])
    xml = (out / f"{slug}-bricklink.xml").read_text()
    assert xml.count("<ITEM>") == len(m["bom"])
    assert "__MODEL_JSON__" not in (out / f"{slug}-viewer.html").read_text()
    assert json.loads((out / "model.json").read_text())["schema"] == "snapwright.model/0.4"


def test_book(tmp_path):
    m = _build(tmp_path, book=True)
    assert (tmp_path / "out" / f"{m['meta']['slug']}-instructions.pdf").stat().st_size > 10_000
