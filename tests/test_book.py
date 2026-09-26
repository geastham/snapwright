"""Book layout: sub-step labels, bags with parts pages, colour names beside every callout icon,
progress bar, all lots shown, A4 and Letter."""
import json
import re
import subprocess
import zlib

from conftest import Catalog, pipeline
from snapwright.book import Book
from snapwright.steps import label_and_bag


def _text(path):
    data = open(path, "rb").read()
    out = []
    for m in re.finditer(rb"stream\r?\n", data):
        try:
            out.append(zlib.decompressobj().decompress(data[m.end():]).decode("latin-1"))
        except zlib.error:
            pass
    return "".join(out)


def test_labels_and_bags():
    steps = [{"n": i + 1, "parts": list(range(40)), "level": lv, "kind": "build"}
             for i, lv in enumerate([0, 0, 0, 3, 6, 6, 9])]
    n = label_and_bag(steps, bag_size=100)
    assert [s["label"] for s in steps] == ["1.1", "1.2", "1.3", "2", "3.1", "3.2", "4"]
    assert n == 4
    # bags only break between numbered steps
    for a, b in zip(steps, steps[1:]):
        if a["bag"] != b["bag"]:
            assert a["label"].split(".")[0] != b["label"].split(".")[0]


def test_book_has_bags_labels_and_named_colours(tmp_path, cat):
    src = tmp_path / "d.py"
    src.write_text('model = Model(14, 14, 30, title="Book Test")\n'
                   'model.box(0, 0, 0, 14, 14, 3, "dark_bluish_gray")\n'
                   'model.cylinder(7, 7, 6, 3, 30, "white", inner_r=4)\n'
                   'model.paint(lambda X, Y, Z: (Y // 6) % 2 == 1, "red")\n')
    model = pipeline.build(str(src), str(tmp_path / "out"), seeds=1, log=lambda *a: None)
    pdf = tmp_path / "out" / "book-test-instructions.pdf"
    text = _text(pdf)
    assert model["stats"]["bags"] >= 2
    assert "(Bag 1) Tj" in text and "(Bag 2) Tj" in text and "Find these first" in text
    assert re.search(r"\(\d+\.\d\) Tj", text)                       # sub-step labels
    assert "more part types" not in text                            # every lot is shown
    names = {c["name"] for k, c in cat.colors.items() if k in model["colors"]}
    for nm in names:                                                # colour named, never colour alone
        assert f"({nm}) Tj" in text, nm
    assert "Bag 1 of" in text
    for page in ("a4", "letter"):
        Book(json.loads((tmp_path / "out" / "model.json").read_text()), Catalog(),
             str(tmp_path / f"{page}.pdf"), page=page, log=lambda *a: None).build()
        assert (tmp_path / f"{page}.pdf").stat().st_size > 20_000


def test_viewer_controls_and_no_external_fetches(tmp_path, cat):
    import shutil
    src = tmp_path / "d.py"
    src.write_text('model = Model(8, 8, 9, title="Viewer Test")\nmodel.box(0, 0, 0, 8, 8, 9, "red")\n')
    pipeline.build(str(src), str(tmp_path / "out"), seeds=1, book=False, log=lambda *a: None)
    html = (tmp_path / "out" / "viewer-test-viewer.html").read_text()
    for el in ('id="bPrev"', 'id="bNext"', 'id="bPlay"', 'id="bRec"', 'id="bExplode"', 'aria-label="Previous step"',
               "MediaRecorder", "ArrowRight"):
        assert el in html, el
    urls = set(re.findall(r"https?://[^\s\"'`)]+", html))
    assert urls and all(u.startswith("https://cdn.jsdelivr.net/npm/three@") for u in urls), urls
    node = shutil.which("node")
    if node:                                             # the viewer's module parses
        js = re.search(r'<script type="module">(.*?)</script>', html, re.S).group(1)
        (tmp_path / "v.mjs").write_text(js)
        r = subprocess.run([node, "--check", str(tmp_path / "v.mjs")], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
