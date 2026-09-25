"""Random 'blobby' designs for property tests: a grounded trunk with spheres, tubes, overhang
shelves, stair-step circles (cones widening upward), 1-stud colour speckles and see-through
patches. Deterministic per seed."""
from __future__ import annotations

import numpy as np

from snapwright.dsl import Model

OPAQUE = ["white", "red", "blue", "yellow", "dark_bluish_gray", "light_bluish_gray", "tan",
          "black", "green", "orange"]


def random_design(seed: int) -> Model:
    rng = np.random.default_rng(seed)
    NX = int(rng.integers(9, 16))
    NZ = int(rng.integers(9, 16))
    NY = int(rng.integers(18, 36))
    m = Model(NX, NZ, NY, title=f"Blob {seed}")
    cols = list(rng.choice(OPAQUE, size=4, replace=False))
    cx, cz = NX / 2, NZ / 2
    rmax = min(NX, NZ) / 2 - 0.5
    kind = rng.integers(3)
    if kind == 0:
        m.cylinder(cx, cz, r=rmax, y0=0, y1=3, color=cols[0])
    elif kind == 1:
        m.box(1, 1, 0, NX - 1, NZ - 1, 3, cols[0])
    else:
        m.ellipsoid(cx, 0, cz, rmax, 6, rmax, cols[0])
    top = int(rng.integers(NY // 2, NY - 3))
    tr = float(rng.uniform(1.6, rmax * 0.8))
    if rng.random() < 0.5:
        m.cylinder(cx, cz, r=tr, y0=3, y1=top, color=cols[1],
                   inner_r=tr - 1.6 if tr > 3.5 and rng.random() < 0.6 else None)
    else:
        m.cone(cx, cz, r0=tr, r1=max(1.2, tr * 0.6), y0=3, y1=top, color=cols[1])
    for _ in range(int(rng.integers(1, 5))):
        f = rng.integers(6)
        y = float(rng.uniform(4, NY - 2))
        if f == 0:    # sphere / blob hugging the trunk
            r_mm = float(rng.uniform(10, 32))
            ang = rng.uniform(0, 2 * np.pi)
            d = rng.uniform(0, tr)
            m.sphere(cx + d * np.cos(ang), y, cz + d * np.sin(ang), r_mm, str(rng.choice(cols)))
        elif f == 1:  # overhang shelf sticking out from the trunk
            y0 = int(y)
            x0 = int(cx - rng.uniform(0, tr))
            x1 = int(min(NX, cx + rng.uniform(tr, rmax + 1)))
            z0 = int(cz - rng.uniform(0.5, 2))
            m.box(x0, z0, y0, x1, z0 + int(rng.integers(1, 4)), y0 + int(rng.integers(1, 4)),
                  str(rng.choice(cols)))
        elif f == 2:  # stair-step circles: a cone widening upward (rings of overhangs)
            y0 = int(min(y, NY - 4))
            m.cone(cx, cz, r0=tr * 0.6, r1=min(rmax, tr + rng.uniform(1, 4)), y0=y0,
                   y1=min(NY, y0 + int(rng.integers(3, 8))), color=str(rng.choice(cols)))
        elif f == 3:  # tube section
            y0 = int(min(y, NY - 3))
            r = float(rng.uniform(2.5, rmax))
            m.cylinder(cx, cz, r=r, y0=y0, y1=min(NY, y0 + int(rng.integers(2, 9))),
                       color=str(rng.choice(cols)), inner_r=r - float(rng.uniform(1, 2)))
        elif f == 4:  # 1-stud colour speckles on whatever exists
            p = float(rng.uniform(0.02, 0.12))
            noise = np.random.default_rng(seed * 7 + 1).random(m.V.shape) < p
            m.fill(noise & (m.V > 0), str(rng.choice(OPAQUE)))
        else:         # see-through patch
            m.paint(lambda X, Y, Z, y=y: (np.abs(Y - y) < 2) & (X > cx), "trans_clear")
    return m
