"""The packaged skill is self-contained: zipped like `make package`, unpacked somewhere else,
it builds a model (book, viewer, exports) using nothing outside the package."""
import os
import subprocess
import sys
import zipfile

from conftest import ROOT

SKIP = ("__pycache__", ".DS_Store", ".rebrickable", ".tmp")


def _package(dest):
    src = os.path.join(ROOT, "skills", "snapwright")
    path = os.path.join(dest, "snapwright.skill")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for d, dirs, files in os.walk(src):
            dirs[:] = [x for x in dirs if not any(s in x for s in SKIP)]
            for f in files:
                if not any(s in f for s in SKIP):
                    full = os.path.join(d, f)
                    z.write(full, os.path.join("snapwright", os.path.relpath(full, src)))
    return path


def test_packaged_skill_is_small_and_self_contained(tmp_path):
    pkg = _package(tmp_path)
    assert os.path.getsize(pkg) < 2_000_000
    names = zipfile.ZipFile(pkg).namelist()
    assert "snapwright/SKILL.md" in names and "snapwright/assets/catalog.json" in names
    lines = open(os.path.join(ROOT, "skills", "snapwright", "SKILL.md")).read().count("\n")
    assert lines < 500
    zipfile.ZipFile(pkg).extractall(tmp_path / "installed")
    design = tmp_path / "design.py"
    design.write_text('model = Model(6, 6, 9, title="Tiny")\nmodel.box(1, 1, 0, 5, 5, 9, "red")\n')
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "SNAPWRIGHT_CATALOG")}
    r = subprocess.run([sys.executable, str(tmp_path / "installed" / "snapwright" / "scripts" / "sw.py"),
                        "build", str(design), "--out", str(tmp_path / "out"), "--seeds", "1"],
                       cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    out = os.listdir(tmp_path / "out")
    for f in ("tiny-instructions.pdf", "tiny-viewer.html", "tiny.ldr", "tiny-bricklink.xml", "model.json"):
        assert f in out, out
