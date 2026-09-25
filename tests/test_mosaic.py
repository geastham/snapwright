import numpy as np
from PIL import Image

from conftest import Model, solve
from oracles import check_model


def _noise_image(path, w=16, h=16, seed=0):
    rng = np.random.default_rng(seed)
    Image.fromarray(rng.integers(0, 256, (h, w, 3), dtype=np.uint8)).resize((w * 8, h * 8), Image.NEAREST).save(path)


def test_flat_mosaic_is_one_structure(tmp_path, cat):
    """Speckled colour tiles can't bridge base plates on their own; the staggered base
    layers must hold the mosaic together."""
    img = tmp_path / "noise.png"
    _noise_image(img)
    m = Model(16, 16, 3, catalog=cat)
    m.mosaic(str(img), mode="flat", dither=True)          # many colours, mostly 1x1 tiles
    model, built = solve(m, catalog=cat, seeds=2)
    st = model["stats"]
    assert st["passed"], st["failures"]
    assert st["structures"] == 1 and st["recolored_cells"] == 0
    check_model(model, m.V, built, m.palette)
    top = built.shape[2] - 1
    assert (built[:, :, top] > 0).all(), "the picture layer covers the whole mosaic"
    picture = [p for p in model["parts"] if p["y"] == top]
    assert all(p["kind"] == "tile" for p in picture), "picture layer kept its smooth tile finish"


def test_flat_mosaic_grows_grid_for_base_layers(tmp_path, cat):
    img = tmp_path / "noise.png"
    _noise_image(img, 8, 8)
    m = Model(8, 8, 1, catalog=cat)
    m.mosaic(str(img), mode="flat")
    assert m.NY == 3 and m.V.shape[2] == 3


def test_upright_mosaic_passes(tmp_path, cat):
    img = tmp_path / "noise.png"
    _noise_image(img, 12, 20, seed=3)
    m = Model(12, 4, 30, catalog=cat)
    m.mosaic(str(img), colors=["red", "white", "black"], mode="upright", depth=2)
    model, built = solve(m, catalog=cat, seeds=2)
    check_model(model, m.V, built, m.palette)
