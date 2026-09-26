import numpy as np

from conftest import Model


def test_box_is_half_open():
    m = Model(10, 10, 10)
    m.box(2, 3, 1, 5, 7, 4, "red")
    assert m.voxel_count() == 3 * 4 * 3
    assert m.V[2, 3, 1] and not m.V[5, 3, 1]


def test_cylinder_tube_and_cone():
    m = Model(20, 20, 10)
    m.cylinder(10, 10, 5, 0, 1, "white")
    solid = m.voxel_count()
    m2 = Model(20, 20, 10)
    m2.cylinder(10, 10, 5, 0, 1, "white", inner_r=3)
    assert 0 < m2.voxel_count() < solid
    assert m2.V[10, 10, 0] == 0                           # hollow centre
    m3 = Model(20, 20, 10)
    m3.cone(10, 10, 6, 2, 0, 10, "white")
    assert (m3.V[:, :, 0] > 0).sum() > (m3.V[:, :, 9] > 0).sum()


def test_sphere_handles_aspect():
    m = Model(20, 20, 50)
    m.sphere(10, 25, 10, 40, "red")                        # 40 mm: 5 studs, 12.5 plates
    idx = np.argwhere(m.V > 0)
    w = idx[:, 0].max() - idx[:, 0].min() + 1
    h = idx[:, 2].max() - idx[:, 2].min() + 1
    assert abs(w * 8 - h * 3.2) < 8                        # round in millimetres


def test_paint_only_recolours_filled():
    m = Model(6, 6, 6)
    m.box(0, 0, 0, 3, 6, 6, "red")
    m.paint(lambda X, Y, Z: X > 0, "blue")
    assert m.voxel_count() == 3 * 6 * 6
    assert m.palette[m.V[1, 0, 0] - 1] == "blue"


def test_carve_and_mirror():
    m = Model(8, 4, 2)
    m.box(0, 0, 0, 3, 4, 2, "red")
    m.mirror_x()
    assert (m.V[7] == m.V[0]).all() and (m.V[5] == m.V[2]).all()
    m.carve(lambda X, Y, Z: Y > 1)
    assert not m.V[:, :, 1].any()


def test_islands_and_grow():
    m = Model(10, 10, 10)
    m.box(0, 0, 0, 4, 4, 3, "red")
    m.box(6, 6, 5, 8, 8, 7, "blue")                        # floating
    isl = m.islands()
    assert len(isl) == 1 and isl[0]["voxels"] == 8
    m.grow_height(14)
    assert m.V.shape == (10, 10, 14) and m.Y.shape == (10, 10, 14) and m.voxel_count() == 56


def test_numpy_strings_become_plain_strings():
    m = Model(2, 2, 2)
    m.box(0, 0, 0, 2, 2, 1, np.str_("red"))
    assert type(m.palette[0]) is str


def test_size_cm():
    m = Model(10, 10, 30)
    m.box(0, 0, 0, 10, 5, 30, "red")
    assert m.size_cm() == (8.0, 9.6, 4.0)                  # w, h, d
