"""Sideways panels (SNOT: studs not on top): geometry shared by the DSL, packer, checks, book,
viewer and exporters.

A panel is built flat like any small model (its own grid: x across, z in rows, y in plate
layers upward), then tipped onto a face of the main model so its studs point outward:

    panel x (studs)   -> right, as seen from in front of the face
    panel y (plates)  -> outward, along the face normal (the panel's stud side)
    panel z (studs)   -> down (row 0 is the panel's top edge)

That is a proper rotation (no mirror): the builder tips the finished panel forward onto the
wall. Its bottom layer (panel y = 0) sits against the face and clips onto side studs of
anchor bricks (87087 / 11211 / 30414) built into the main model right behind the face.

Alignment: a side stud's centre is 5.6 mm above its brick's bottom and panel rows are 8 mm
apart, so with the panel's top edge on plate line T, row 0's anchor is a side-stud brick on
plates T-3..T-1 and every second row lines up again (5 plates = 16 mm = 2 rows):
anchor row j (even) sits on plates T - 3 - 2.5 j.

World coordinates here are millimetres (x, y up, z); the main grid is x, z in studs (8 mm)
and y in plates (3.2 mm).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

STUD_MM, PLATE_MM = 8.0, 3.2
SIDE_STUD_MM = 5.6
FACES = {"+x": 0, "+z": 1, "-x": 2, "-z": 3}
DIR_VEC = {0: (1, 0), 1: (0, 1), 2: (-1, 0), 3: (0, -1)}   # (x, z) outward normal per face


@dataclass
class PanelSpec:
    name: str
    face: int            # 0 +x, 1 +z, 2 -x, 3 -z: which way the panel faces (its studs point)
    a0: int              # first stud along the face (x for +-z faces, z for +-x faces)
    plane: int           # face plane, stud boundary coordinate (z for +-z faces, x for +-x)
    top: int             # plate line of the panel's top edge
    W: int               # studs across
    H: int               # rows (studs) down
    D: int               # plate layers outward

    @property
    def ztype(self) -> bool:
        return self.face in (1, 3)

    def frame(self):
        """Unit vectors (world x, y, z) of panel x (right), panel y (out), panel z (down)."""
        nx, nz = DIR_VEC[self.face]
        n = np.array([nx, 0.0, nz])
        up = np.array([0.0, 1.0, 0.0])
        r = np.cross(up, n)                     # right, seen from in front of the face
        return r, n, -up

    def origin(self):
        """World mm of the panel's (x=0, y=0, z=0) corner: left edge, face plane, top edge."""
        r, n, _ = self.frame()
        lo, hi = self.a0 * STUD_MM, (self.a0 + self.W) * STUD_MM
        along = lo if (r[0] + r[2]) > 0 else hi
        plane = self.plane * STUD_MM
        y = self.top * PLATE_MM
        return np.array([along, y, plane]) if self.ztype else np.array([plane, y, along])

    def to_world(self, lx, ly, lz):
        """Panel mm (x across, y out, z down) -> world mm (x, y, z)."""
        r, n, d = self.frame()
        return self.origin() + lx * r + ly * n + lz * d

    def local_box_world(self, x0, y0, z0, x1, y1, z1):
        """Panel cell box (studs, plates, studs) -> world axis-aligned box (lo, hi) in mm."""
        corners = np.array([self.to_world(a * STUD_MM, b * PLATE_MM, c * STUD_MM)
                            for a in (x0, x1) for b in (y0, y1) for c in (z0, z1)])
        return corners.min(0), corners.max(0)

    def world_box(self):
        return self.local_box_world(0, 0, 0, self.W, self.D, self.H)

    def rotation(self):
        """3x3 matrix: columns are world (x, y, z) directions of panel x, y (out), z."""
        r, n, d = self.frame()
        return np.stack([r, n, d], axis=1)

    # ---- main grid ---------------------------------------------------------------------
    def main_region(self):
        """Main-grid cell box the panel occupies (x0, x1, z0, z1, y0, y1), half-open."""
        lo, hi = self.world_box()
        x0, x1 = int(math.floor(lo[0] / STUD_MM + 1e-9)), int(math.ceil(hi[0] / STUD_MM - 1e-9))
        z0, z1 = int(math.floor(lo[2] / STUD_MM + 1e-9)), int(math.ceil(hi[2] / STUD_MM - 1e-9))
        y0, y1 = int(math.floor(lo[1] / PLATE_MM + 1e-9)), int(math.ceil(hi[1] / PLATE_MM - 1e-9))
        return x0, x1, z0, z1, y0, y1

    def slide_path(self, shape):
        """Main-grid cell box in front of the panel, out to the edge of the grid: the panel slides
        on through here, so nothing may be built there before it is attached."""
        x0, x1, z0, z1, y0, y1 = self.main_region()
        nx, nz = DIR_VEC[self.face]
        NX, NZ, _ = shape
        if nx > 0:
            x0, x1 = x1, NX
        elif nx < 0:
            x0, x1 = 0, x0
        elif nz > 0:
            z0, z1 = z1, NZ
        else:
            z0, z1 = 0, z0
        return x0, x1, z0, z1, y0, y1

    def behind(self, i):
        """Main-grid (x, z) of the cell right behind the face at panel column i."""
        nx, nz = DIR_VEC[self.face]
        r, _, _ = self.frame()
        along = self.a0 + i if (r[0] + r[2]) > 0 else self.a0 + self.W - 1 - i
        if self.ztype:
            z = self.plane - 1 if nz > 0 else self.plane
            return along, z
        x = self.plane - 1 if nx > 0 else self.plane
        return x, along

    def anchor_rows(self):
        """(row j, bottom plate p) for rows whose centre lines up with a side stud."""
        out = []
        for j in range(0, self.H, 2):
            p = self.top - 3 - (5 * j) // 2
            if p >= 0:
                out.append((j, p))
        return out

    def face_offset_mm(self):
        """How far the panel's outer face sits proud of (+) or inside (-) the stud grid."""
        depth = self.D * PLATE_MM
        return round(depth - math.ceil(depth / STUD_MM - 1e-9) * STUD_MM, 1)

    def to_json(self):
        return {"name": self.name, "face": self.face, "a0": self.a0, "plane": self.plane,
                "top": self.top, "W": self.W, "H": self.H, "D": self.D}

    @classmethod
    def from_json(cls, d):
        return cls(**{k: d[k] for k in ("name", "face", "a0", "plane", "top", "W", "H", "D")})


def part_world_box(spec: PanelSpec, p):
    """World mm box of a panel part (panel coordinates: x across, y out, z down)."""
    return spec.local_box_world(p["x"], p["y"], p["z"], p["x"] + p["dx"], p["y"] + p["h"],
                                p["z"] + p["dz"])


def anchor_requests(spec: PanelSpec):
    """Where anchor bricks go for one panel: [{panel, face, row, plate, cols: [(i, x, z)]}],
    one entry per anchor row, columns in panel order."""
    out = []
    for j, p in spec.anchor_rows():
        out.append({"panel": spec.name, "face": spec.face, "row": j, "plate": p,
                    "cols": [(i,) + spec.behind(i) for i in range(spec.W)]})
    return out


def anchored_cells(spec: PanelSpec, main_parts):
    """Panel cells (i, j) at layer 0 that sit on a side stud of an anchor brick."""
    cells = set()
    for p in main_parts:
        if p.get("anchor") != spec.name:
            continue
        for x, z in p["side_cells"]:
            for i in range(spec.W):
                if spec.behind(i) == (x, z):
                    cells.add((i, p["row"]))
    return cells


def panel_hold(spec: PanelSpec, parts, edges, anchored):
    """Which panel parts are held through the anchors. Returns (held ids, anchor studs used):
    a part is held if it covers an anchored cell on the bottom layer, or connects to one."""
    from .validate import DSU
    n = len(parts)
    d = DSU(max(n, 1))
    for i, j in edges:
        d.union(i, j)
    studs, roots = 0, set()
    for p in parts:
        if p["y"] != 0:
            continue
        for i, j in anchored:
            if p["x"] <= i < p["x"] + p["dx"] and p["z"] <= j < p["z"] + p["dz"]:
                studs += 1
                roots.add(d.find(p["id"]))
    held = {p["id"] for p in parts if d.find(p["id"]) in roots}
    return held, studs
