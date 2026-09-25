import numpy as np

from conftest import Catalog, Model
from snapwright.render import model_grid, part_icon, render_grid, rotate_grid, voxel_preview


def test_rotate_grid_four_turns_is_identity():
    G = np.arange(2 * 3 * 4).reshape(2, 3, 4)
    R = G
    for _ in range(4):
        R = rotate_grid(R, 1)
    assert (R == G).all()
    assert rotate_grid(G, 1).shape == (3, 2, 4)


def test_render_highlight_and_empty():
    G = -np.ones((3, 3, 2), int)
    G[:, :, 0] = 0
    G[1, 1, 1] = 1
    colors, studs = {0: "#1E5AA8", 1: "#B40000"}, {0: True, 1: True}
    a = np.asarray(render_grid(G, colors, studs, size=(200, 200)))
    b = np.asarray(render_grid(G, colors, studs, highlight={1}, size=(200, 200)))
    assert a.shape == (200, 200, 4) and (a != b).any()
    empty = np.asarray(render_grid(-np.ones((2, 2, 2), int), colors, studs, size=(50, 50)))
    assert empty[..., 3].max() == 0


def test_model_grid_up_to_step():
    parts = [{"id": 0, "x": 0, "z": 0, "y": 0, "dx": 2, "dz": 1, "h": 1, "step": 1},
             {"id": 1, "x": 0, "z": 0, "y": 1, "dx": 1, "dz": 1, "h": 3, "step": 2}]
    assert (model_grid(parts, (2, 1, 4), upto_step=1) >= 0).sum() == 2
    assert (model_grid(parts, (2, 1, 4)) >= 0).sum() == 5


def test_icon_and_preview(cat):
    assert part_icon(cat.by_id["3001"], "#B40000").size == (140, 110)
    m = Model(4, 4, 3)
    m.box(0, 0, 0, 4, 4, 3, "red")
    assert voxel_preview(m.V, m.palette, cat, size=(120, 120), view=2).size == (120, 120)
