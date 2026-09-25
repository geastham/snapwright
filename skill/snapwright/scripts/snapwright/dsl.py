"""Design DSL: describe a model as coloured voxels on the stud/plate grid.

Coordinates: x and z are in studs (1 stud = 8 mm), y is in plates (1 plate = 3.2 mm,
a brick is 3 plates). y = 0 is the ground. A voxel is one 1x1 stud cell, one plate tall.

Every primitive takes a colour key from the catalog (e.g. "dark_bluish_gray"), or None
to carve. Later calls overwrite earlier ones, so block out big shapes first, then detail.

    model = Model(24, 24, 120, title="Lighthouse")
    model.cylinder(12, 12, r=8, y0=0, y1=60, color="white", inner_r=5)
    model.paint(lambda X, Y, Z: (Y // 12) % 2 == 1, "red")   # stripes on filled voxels
"""
from __future__ import annotations

import math

import numpy as np

from .catalog import Catalog, hex_to_rgb

STUD_MM = 8.0
PLATE_MM = 3.2


def mm_to_studs(mm: float) -> float:
    return mm / STUD_MM


def mm_to_plates(mm: float) -> float:
    return mm / PLATE_MM


class Model:
    def __init__(self, width: int, depth: int, height: int, title: str = "Untitled build",
                 author: str = "", subtitle: str = "", catalog: Catalog | None = None):
        self.NX, self.NZ, self.NY = int(width), int(depth), int(height)
        self.V = np.zeros((self.NX, self.NZ, self.NY), dtype=np.int16)  # 0 = empty
        self.palette: list[str] = []
        self.title, self.author, self.subtitle = title, author, subtitle
        self.catalog = catalog or Catalog()
        self.notes: list[str] = []
        x = np.arange(self.NX) + 0.5
        z = np.arange(self.NZ) + 0.5
        y = np.arange(self.NY) + 0.5
        self.X, self.Z, self.Y = np.meshgrid(x, z, y, indexing="ij")

    # ---- internals ---------------------------------------------------
    def _idx(self, color):
        if color is None:
            return 0
        self.catalog.color(color)  # validates key
        if color not in self.palette:
            self.palette.append(color)
        return self.palette.index(color) + 1

    def fill(self, mask, color):
        """Set every voxel in a boolean mask to colour (None carves)."""
        self.V[mask] = self._idx(color)
        return self

    # ---- solids ------------------------------------------------------
    def box(self, x0, z0, y0, x1, z1, y1, color):
        """Axis-aligned box, half-open: covers x0 <= x < x1 (studs), y0 <= y < y1 (plates)."""
        m = ((self.X >= x0) & (self.X < x1) & (self.Z >= z0) & (self.Z < z1)
             & (self.Y >= y0) & (self.Y < y1))
        return self.fill(m, color)

    def cylinder(self, cx, cz, r, y0, y1, color, inner_r: float | None = None):
        """Vertical cylinder (or tube if inner_r) centred at stud coords cx, cz."""
        d = np.hypot(self.X - cx, self.Z - cz)
        m = (d <= r) & (self.Y >= y0) & (self.Y < y1)
        if inner_r:
            m &= d > inner_r
        return self.fill(m, color)

    def cone(self, cx, cz, r0, r1, y0, y1, color, inner: float | None = None):
        """Vertical frustum: radius r0 at y0 tapering linearly to r1 at y1."""
        t = np.clip((self.Y - y0) / max(1e-9, (y1 - y0)), 0, 1)
        r = r0 + (r1 - r0) * t
        d = np.hypot(self.X - cx, self.Z - cz)
        m = (d <= r) & (self.Y >= y0) & (self.Y < y1)
        if inner:
            m &= d > (r - inner)
        return self.fill(m, color)

    def ellipsoid(self, cx, cy, cz, rx, ry, rz, color):
        """Ellipsoid. cx, cz, rx, rz in studs; cy, ry in plates."""
        m = (((self.X - cx) / rx) ** 2 + ((self.Y - cy) / ry) ** 2 + ((self.Z - cz) / rz) ** 2) <= 1
        return self.fill(m, color)

    def sphere(self, cx, cy, cz, r_mm, color):
        """True sphere of radius r_mm (handles the stud/plate aspect ratio for you)."""
        return self.ellipsoid(cx, cy, cz, r_mm / STUD_MM, r_mm / PLATE_MM, r_mm / STUD_MM, color)

    def where(self, fn, color):
        """Fill wherever fn(X, Y, Z) is true. X, Z in studs, Y in plates (cell centres)."""
        return self.fill(fn(self.X, self.Y, self.Z), color)

    def paint(self, fn, color):
        """Recolour only voxels that are already filled."""
        return self.fill(fn(self.X, self.Y, self.Z) & (self.V > 0), color)

    def carve(self, fn):
        return self.fill(fn(self.X, self.Y, self.Z), None)

    def mirror_x(self, about: float | None = None):
        """Mirror the left half onto the right half (about the centre by default)."""
        c = self.NX / 2 if about is None else about
        for xi in range(self.NX):
            src = int(math.floor(2 * c - (xi + 0.5)))
            if xi + 0.5 > c and 0 <= src < self.NX:
                self.V[xi] = self.V[src]
        return self

    # ---- images ------------------------------------------------------
    def mosaic(self, image_path: str, colors: list[str] | None = None, mode: str = "flat",
               base_color: str = "black", depth: int = 2, dither: bool = False):
        """Photo -> mosaic sized to this model.

        flat:    lies on the ground; 1 base plate layer + 1 colour layer (tiled by default).
        upright: stands up in the x-y plane, `depth` studs thick; image rows map to plates.
        """
        from PIL import Image
        img = Image.open(image_path).convert("RGB")
        if mode == "flat":
            w, h = self.NX, self.NZ
        else:
            w, h = self.NX, self.NY
        img = img.resize((w, h), Image.LANCZOS)
        px = np.asarray(img).astype(float)
        keys = colors or [k for k, c in self.catalog.colors.items()
                          if c["tier"] == "core" and not k.startswith("trans")]
        cache: dict = {}
        grid = np.empty((w, h), dtype=object)
        err = np.zeros_like(px)
        for j in range(h):
            for i in range(w):
                rgb = np.clip(px[j, i] + err[j, i], 0, 255)
                k = tuple(int(v) // 4 for v in rgb)
                if k not in cache:
                    cache[k] = self.catalog.nearest(rgb, keys)
                c = cache[k]
                grid[i, j] = c
                if dither:
                    e = rgb - np.array(hex_to_rgb(self.catalog.colors[c]["hex"]))
                    for di, dj, f in ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16)):
                        if 0 <= i + di < w and 0 <= j + dj < h:
                            err[j + dj, i + di] += e * f
        if mode == "flat":
            self.V[:, :, 0] = self._idx(base_color)
            for i in range(w):
                for j in range(h):
                    self.V[i, h - 1 - j, 1] = self._idx(grid[i, j])  # image top -> back row
        else:
            z0 = max(0, (self.NZ - depth) // 2)
            for i in range(w):
                for j in range(h):
                    self.V[i, z0:z0 + depth, h - 1 - j] = self._idx(grid[i, j])
        return self

    # ---- info --------------------------------------------------------
    def voxel_count(self) -> int:
        return int((self.V > 0).sum())

    def size_cm(self):
        filled = np.argwhere(self.V > 0)
        if not len(filled):
            return (0, 0, 0)
        lo, hi = filled.min(0), filled.max(0) + 1
        return (round((hi[0] - lo[0]) * STUD_MM / 10, 1), round((hi[2] - lo[2]) * PLATE_MM / 10, 1),
                round((hi[1] - lo[1]) * STUD_MM / 10, 1))


def dsl_namespace():
    """Names injected into design files."""
    return {"Model": Model, "np": np, "math": math, "mm_to_studs": mm_to_studs,
            "mm_to_plates": mm_to_plates, "STUD_MM": STUD_MM, "PLATE_MM": PLATE_MM}
