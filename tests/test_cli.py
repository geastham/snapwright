"""The CLI end to end, including regenerating every output from model.json alone."""
import json
import os
import subprocess
import sys

from conftest import ROOT

SW = os.path.join(ROOT, "skill", "snapwright", "scripts", "sw.py")
GOOD = '''model = Model(8, 8, 9, title="Cli Test")
model.box(0, 0, 0, 8, 8, 3, "dark_bluish_gray")
model.cylinder(4, 4, 3.5, 3, 9, "white", inner_r=1.5)
'''
BAD = '''model = Model(8, 8, 9, title="Cli Bad")
model.box(0, 0, 0, 8, 8, 2, "red")
model.box(2, 2, 5, 6, 6, 7, "blue")
'''


def run(*args):
    return subprocess.run([sys.executable, SW, *map(str, args)], capture_output=True, text=True)


def test_preview_build_and_regenerate(tmp_path):
    d = tmp_path / "d.py"
    d.write_text(GOOD)
    r = run("preview", d, "--out", tmp_path / "prev", "--size", 200)
    assert r.returncode == 0 and len(list((tmp_path / "prev").glob("preview_view*.png"))) == 4
    out = tmp_path / "out"
    r = run("build", d, "--out", out, "--seeds", 1, "--profile")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "timings:" in r.stdout and (out / "profile.txt").exists()
    names = {p.name for p in out.iterdir()}
    for n in ("model.json", "cli-test.ldr", "cli-test-bricklink.xml", "cli-test-rebrickable.csv",
              "cli-test-parts.csv", "cli-test-viewer.html", "cli-test-instructions.pdf"):
        assert n in names, n
    # everything regenerable from model.json alone
    r = run("viewer", out / "model.json", "--out", tmp_path / "v.html")
    assert r.returncode == 0
    assert (tmp_path / "v.html").read_text() == (out / "cli-test-viewer.html").read_text()
    r = run("book", out / "model.json", "--out", tmp_path / "b.pdf", "--page", "a4")
    assert r.returncode == 0 and (tmp_path / "b.pdf").stat().st_size > 10_000


def test_failing_build_exits_2_and_skips_book(tmp_path):
    d = tmp_path / "bad.py"
    d.write_text(BAD)
    r = run("build", d, "--out", tmp_path / "out", "--seeds", 1)
    assert r.returncode == 2
    assert "don't touch the rest of the model" in r.stdout
    assert not list((tmp_path / "out").glob("*.pdf"))
    m = json.loads((tmp_path / "out" / "model.json").read_text())
    assert not m["stats"]["passed"] and m["stats"]["failures"]
    r = run("build", d, "--out", tmp_path / "draft", "--seeds", 1, "--no-strict")
    assert r.returncode == 2 and list((tmp_path / "draft").glob("*.pdf"))


def test_v01_model_still_renders(tmp_path):
    """model.json from v0.1 (schema 0.1) must still regenerate the viewer and the book."""
    old = os.path.join(ROOT, "tests", "fixtures", "v0.1_model.json")
    m = json.load(open(old))
    m["stats"]["necks"] = [{"plate": 9, "strength": 2, "parts_above": 12}]   # 0.1-style neck
    p = tmp_path / "old.json"
    p.write_text(json.dumps(m))
    assert run("viewer", p, "--out", tmp_path / "v.html").returncode == 0
    r = run("book", p, "--out", tmp_path / "b.pdf")
    assert r.returncode == 0, r.stderr
    assert "snapwright.model/0.2" in (tmp_path / "v.html").read_text()
