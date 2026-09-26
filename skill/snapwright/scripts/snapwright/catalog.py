"""Parts and colour catalog: loading, lookup, and perceptual colour matching."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CATALOG = os.path.normpath(os.path.join(HERE, "..", "..", "assets", "catalog.json"))


DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))   # +x, +z, -x, -z: which way a slope's low side faces


@dataclass(frozen=True)
class PartType:
    id: str
    name: str
    kind: str      # brick | plate | tile | slope | slope_inv | round
    L: int         # long side, studs (for slopes: from the back, studded row to the low front row)
    W: int         # short side, studs
    h: int         # height in plates
    studs: bool    # any studs on top
    shape: str = "box"          # box | slope | slope_inv | round | snot
    top: object = "all"         # "all" | "none" | ((i, j), ...) cells with a stud on top
    bottom: object = "all"      # "all" | "none" | ((i, j), ...) cells that take a stud underneath
    ldraw: str = ""
    ldraw_origin: str = "top"   # top | stud_row_top | bottom
    lip: float = 0.0            # slopes: height (plates) of the vertical face at the low edge
    auto: bool = False          # may be placed by the surface-shaping pass
    side: tuple = ()            # cells (i, j) with a stud on the side face (points local +z)
    side_mm: float = 0.0        # height of the side studs' centres above the part's bottom
    bricklink: str = ""
    rebrickable: str = ""

    @property
    def area(self) -> int:
        return self.L * self.W

    def local_cells(self, which: str) -> set:
        """Local cells (i, j) with a stud on top (which='top') or a socket underneath."""
        v = getattr(self, which)
        if v == "all":
            return {(i, j) for i in range(self.L) for j in range(self.W)}
        if v == "none":
            return set()
        return {tuple(c) for c in v}


def place_cells(t: PartType, x: int, z: int, dir_: int):
    """World footprint of a directional part whose footprint's min corner is (x, z).
    Returns (dx, dz, cell) where cell(i, j) maps local cell -> world (x, z). Local i runs
    from the back row (i = 0) towards the low side, which faces DIRS[dir_]."""
    L, W = t.L, t.W
    if dir_ == 0:
        return L, W, lambda i, j: (x + i, z + j)
    if dir_ == 2:
        return L, W, lambda i, j: (x + L - 1 - i, z + j)
    if dir_ == 1:
        return W, L, lambda i, j: (x + j, z + i)
    return W, L, lambda i, j: (x + j, z + L - 1 - i)


class Catalog:
    def __init__(self, path: str | None = None):
        self.path = path or os.environ.get("SNAPWRIGHT_CATALOG", DEFAULT_CATALOG)
        with open(self.path) as f:
            raw = json.load(f)
        self.raw = raw
        self.units = raw["units"]
        self.colors: dict[str, dict] = raw["colors"]
        self.parts: list[PartType] = [_part_type(p) for p in raw["parts"]]
        self.by_id = {p.id: p for p in self.parts}
        self.availability: dict = raw.get("availability", {})

    # ---- parts -------------------------------------------------------
    def of_kind(self, kind: str) -> list[PartType]:
        return sorted((p for p in self.parts if p.kind == kind), key=lambda p: (-p.area, -p.L))

    def shaped(self, shape: str) -> list[PartType]:
        """Parts the surface-shaping pass may use, biggest first."""
        return sorted((p for p in self.parts if p.shape == shape and p.auto),
                      key=lambda p: (-p.area * p.h, -p.L, p.id))

    def available(self, part_id: str, color: str) -> str:
        """Return 'verified', 'likely' or 'unverified' for a part-colour combo."""
        if self.availability:
            ok = color in self.availability.get(part_id, [])
            return "verified" if ok else "unverified"
        tier = self.colors.get(color, {}).get("tier")
        return "likely" if tier == "core" else "unverified"

    # ---- colours -----------------------------------------------------
    def color(self, key: str) -> dict:
        if key not in self.colors:
            raise KeyError(f"Unknown colour '{key}'. Known: {', '.join(sorted(self.colors))}")
        return self.colors[key]

    def nearest(self, rgb, allowed: list[str] | None = None, include_trans: bool = False) -> str:
        keys = allowed or [k for k in self.colors if include_trans or not k.startswith("trans")]
        lab = rgb_to_lab(rgb)
        best, bd = None, 1e18
        for k in keys:
            d = _dist2(lab, rgb_to_lab(hex_to_rgb(self.colors[k]["hex"])))
            if d < bd:
                best, bd = k, d
        return best


def _part_type(p: dict) -> PartType:
    """Catalog entry -> PartType. Schema 0.1 entries (no connection metadata) get the box
    defaults: studs on every top cell if `studs`, sockets on every bottom cell."""
    q = dict(p)
    q.setdefault("top", "all" if q.get("studs") else "none")
    for k in ("top", "bottom", "side"):
        if isinstance(q.get(k), list):
            q[k] = tuple(tuple(c) for c in q[k])
    q.setdefault("ldraw", q["id"] + ".dat")
    q.setdefault("bricklink", q["id"])
    q.setdefault("rebrickable", q["id"])
    known = PartType.__dataclass_fields__
    return PartType(**{k: v for k, v in q.items() if k in known})


def hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_lab(rgb):
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb[:3])
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _dist2(a, b):
    return sum((p - q) ** 2 for p, q in zip(a, b))
