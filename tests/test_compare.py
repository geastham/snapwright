"""compare: silhouette IoU from the best view, hints, and the reference silhouette sources.
References are rendered from our own designs (no third-party photos)."""
import json
import os
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

from conftest import ROOT, Model
from snapwright import compare as C
from snapwright.catalog import hex_to_rgb
from snapwright.pipeline import load_design

SW = os.path.join(ROOT, "skills", "snapwright", "scripts", "sw.py")


def _photo(model, cat, path, az=20, el=10, bg=(200, 200, 200), noise=5, alpha=False, seed=0):
    px = 1.2
    pts, keys = C.model_points(model, px)
    mask, col, _ = C.project(None, az, el, px=px, points=pts)
    img = np.zeros(mask.shape + (3,), np.uint8)
    img[:] = bg
    for k, key in enumerate(keys, start=1):
        img[col == k] = hex_to_rgb(cat.colors[key]["hex"])
    pad = 40
    big = np.zeros((mask.shape[0] + 2 * pad, mask.shape[1] + 2 * pad, 3), np.uint8)
    big[:] = bg
    big[pad:-pad, pad:-pad] = img
    rng = np.random.default_rng(seed)
    big = np.clip(big + rng.normal(0, noise, big.shape), 0, 255).astype(np.uint8)
    if alpha:
        a = np.zeros(big.shape[:2], np.uint8)
        a[pad:-pad, pad:-pad] = mask * 255
        Image.fromarray(np.dstack([big, a])).save(path)
    else:
        Image.fromarray(big).save(path)
    return mask, pad


@pytest.fixture(scope="module")
def robot(cat):
    return load_design(os.path.join(ROOT, "examples", "robot", "design.py"), cat)


def test_model_matches_its_own_photo(robot, cat, tmp_path):
    _photo(robot, cat, tmp_path / "p.png", az=20, el=10)
    r = C.compare(robot, str(tmp_path / "p.png"), cat, out_png=str(tmp_path / "cmp.png"))
    assert r["iou"] >= 0.9 and r["reference"]["method"] == "background"
    assert abs((r["view"]["azimuth"] - 20 + 180) % 360 - 180) <= 15 and r["view"]["elevation"] <= 20
    assert r["colour_agreement"] >= 0.7 and not r["hints"]
    assert Image.open(tmp_path / "cmp.png").size[0] > 1000


def test_wrong_model_scores_low_with_hints(robot, cat, tmp_path):
    _photo(robot, cat, tmp_path / "p.png")
    lh = load_design(os.path.join(ROOT, "examples", "lighthouse", "design.py"), cat)
    r = C.compare(lh, str(tmp_path / "p.png"), cat)
    assert r["iou"] < 0.8 and r["hints"]


def test_alpha_and_mask_references(robot, cat, tmp_path):
    mask, pad = _photo(robot, cat, tmp_path / "cut.png", alpha=True, bg=(30, 120, 40), noise=40)
    r = C.compare(robot, str(tmp_path / "cut.png"), cat)
    assert r["reference"]["method"] == "alpha" and r["iou"] >= 0.9
    _photo(robot, cat, tmp_path / "busy.png", bg=(120, 120, 120), noise=60)
    m = np.zeros((mask.shape[0] + 2 * pad, mask.shape[1] + 2 * pad), np.uint8)
    m[pad:-pad, pad:-pad] = mask * 255
    Image.fromarray(m).save(tmp_path / "mask.png")
    r = C.compare(robot, str(tmp_path / "busy.png"), cat, mask_path=str(tmp_path / "mask.png"))
    assert r["reference"]["method"] == "mask" and r["iou"] >= 0.9


def test_busy_background_is_reported(cat, tmp_path):
    rng = np.random.default_rng(1)
    Image.fromarray(rng.integers(0, 255, (200, 160, 3), dtype=np.uint8)).save(tmp_path / "noise.png")
    try:
        rgb, mask, info = C.load_reference(str(tmp_path / "noise.png"))
        assert info["warning"]
    except ValueError as e:                               # or no subject at all: say why
        assert "busy" in str(e) and "--mask" in str(e)


def test_aspect_hint(cat, tmp_path):
    tall = Model(6, 6, 60)
    tall.box(0, 0, 0, 6, 6, 60, "red")
    wide = Model(12, 6, 30)
    wide.box(0, 0, 0, 12, 6, 30, "red")
    _photo(tall, cat, tmp_path / "tall.png", az=0, el=0)
    r = C.compare(wide, str(tmp_path / "tall.png"), cat)
    assert any("wider for its height" in h for h in r["hints"]), r["hints"]


def test_thin_details_found():
    m = Model(10, 10, 12)
    m.box(0, 0, 0, 10, 10, 12, "white")
    m.box(4, 9, 5, 5, 10, 6, "black")                     # a one-cell speck on the front
    m.box(1, 8, 2, 4, 10, 8, "red")                       # a proper 3-stud patch
    thin = m.thin_details()
    assert [t["color"] for t in thin] == ["black"]


def test_cli_compare(robot, cat, tmp_path):
    _photo(robot, cat, tmp_path / "p.png")
    out = tmp_path / "cmp"
    r = subprocess.run([sys.executable, SW, "compare", os.path.join(ROOT, "examples", "robot", "design.py"),
                        "--ref", str(tmp_path / "p.png"), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "silhouette IoU" in r.stdout and (out / "compare.png").exists()
    assert json.loads((out / "compare.json").read_text())["iou"] >= 0.9
