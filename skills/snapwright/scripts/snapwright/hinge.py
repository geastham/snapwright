"""Hinged panels and hand-placed curved tiles.

A hinged panel is a flat sub-build (a face, a sign, a screen) clicked onto the model at an
angle with pairs of locking hinge plates:

    fixed plate (44302, two fingers)  sits on a tread of the main model, fingers pointing
                                      the way the panel tips (`toward`)
    moving plate (44301, one finger)  is built under the panel's top rows; the panel swings
                                      down about the hinge axis to `angle` below horizontal

Locking hinges click in 22.5 degree steps, so the angle is a multiple of 22.5. The hinge axis
is half a stud beyond the end of each plate and 0.8 mm below its top surface (LDraw 44301a /
44302a: x 30, y 2 LDU from the plate's top centre), so with the fixed plate's cells ending at
stud line `edge` on plate level `y`:

    axis (along `toward`)  edge * 8 mm + 4 mm (towards the panel)
    axis height            (y + 1) * 3.2 mm - 0.8 mm

Panel coordinates follow sideways panels (snot.py): x across (to the right, seen square-on),
z rows down the slope from the hinge edge, y plate layers outward. The panel's grid has one
extra layer underneath, layer 0, for the moving hinge plates; the designer's layers are 1..D.

Curved tiles (macaroni, quarter and round tiles) can't come out of the voxel packer: the
design places them by hand with Panel.place(). Their outlines (from the LDraw geometry) decide
which cells they grip (a stud wholly under the tile), which cells they cover (no other tile
may go there) and which studs underneath would hit their rim (those cells get a flat tile one
layer down instead of a studded plate).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

STUD_MM, PLATE_MM = 8.0, 3.2
DIR_VEC = {0: (1, 0), 1: (0, 1), 2: (-1, 0), 3: (0, -1)}   # +x, +z, -x, -z
HINGE_FIXED, HINGE_MOVING = "44302", "44301"
AXIS_BEYOND_MM, AXIS_BELOW_TOP_MM = 4.0, 0.8
CLICK_DEG = 22.5
KNUCKLE_MM = 3.0                 # finger radius 6-6.4 LDU (2.6 mm) plus play
STUD_R = 0.29                    # stud radius, studs (4.8 mm across, a little play)

# ---- curved tiles ----------------------------------------------------------------------------
# Outlines at rot 0 in the part's footprint frame (studs; x along L, z along W), matching the
# LDraw part at the identity rotation (our x = LDraw X, our z = -LDraw Z). `origin` is where the
# LDraw origin sits in that frame (top of the tile).
TILES = {
    "27925": {"L": 2, "W": 2, "arc": ((0, 0), 1.0, 2.0), "origin": (0.5, 0.5)},   # 2x2 macaroni
    "27507": {"L": 4, "W": 4, "arc": ((0, 0), 3.0, 4.0), "origin": (0.0, 0.0)},   # 4x4 macaroni
    "25269": {"L": 1, "W": 1, "arc": ((0, 0), 0.0, 1.0), "origin": (0.5, 0.5)},   # quarter round
    "24246": {"L": 1, "W": 1, "half": True, "origin": (0.5, 0.5)},                # half circle
    "98138": {"L": 1, "W": 1, "circle": ((0.5, 0.5), 0.5), "origin": (0.5, 0.5)},
    "14769": {"L": 2, "W": 2, "circle": ((1.0, 1.0), 1.0), "origin": (1.0, 1.0)},
    "67095": {"L": 3, "W": 3, "circle": ((1.5, 1.5), 1.5), "origin": (1.5, 1.5)},
}


def _arc(c, r, a0, a1, n):
    t = np.linspace(a0, a1, n)
    return [(c[0] + r * math.cos(a), c[1] + r * math.sin(a)) for a in t]


def local_outline(pid, n=24):
    """The tile's outline at rot 0, footprint frame (studs), counter-clockwise."""
    t = TILES[pid]
    if "arc" in t:
        c, r0, r1 = t["arc"]
        pts = _arc(c, r1, 0, math.pi / 2, n)
        pts += _arc(c, r0, math.pi / 2, 0, n) if r0 > 0 else [c]
        return pts
    if "circle" in t:
        c, r = t["circle"]
        return _arc(c, r, 0, 2 * math.pi, 2 * n)[:-1]
    # half circle 1 x 1: square half at low z, round end towards +z
    return [(0, 0), (1, 0), (1, 0.5)] + _arc((0.5, 0.5), 0.5, 0, math.pi, n)[1:-1] + [(0, 0.5)]


def _rot(k, px, pz):
    """Quarter turns about +y in our (x, z): rot 1 takes +x to +z."""
    for _ in range(k % 4):
        px, pz = -pz, px
    return px, pz


def placed_geometry(pid, x, z, rot):
    """Outline (studs, grid frame) and LDraw origin (studs) of a placed curved tile whose
    rotated footprint's min corner is (x, z). Returns (outline pts, origin, dx, dz)."""
    t = TILES[pid]
    corners = [_rot(rot, a, b) for a in (0, t["L"]) for b in (0, t["W"])]
    mx, mz = min(c[0] for c in corners), min(c[1] for c in corners)
    dx = max(c[0] for c in corners) - mx
    dz = max(c[1] for c in corners) - mz
    pts = [(_rot(rot, a, b)[0] - mx + x, _rot(rot, a, b)[1] - mz + z) for a, b in local_outline(pid)]
    ox, oz = _rot(rot, *t["origin"])
    return pts, (ox - mx + x, oz - mz + z), int(round(dx)), int(round(dz))


def _inside(pts, px, pz):
    """Point-in-polygon for arrays of points."""
    px, pz = np.asarray(px, float), np.asarray(pz, float)
    inside = np.zeros(px.shape, bool)
    n = len(pts)
    for i in range(n):
        (x1, z1), (x2, z2) = pts[i], pts[(i + 1) % n]
        cond = (z1 > pz) != (z2 > pz)
        xi = (x2 - x1) * (pz - z1) / ((z2 - z1) or 1e-12) + x1
        inside ^= cond & (px < xi)
    return inside


def _coverage(pts, cx, cz, ss=10):
    """Fraction of cell (cx, cz) covered by the outline."""
    s = (np.arange(ss) + 0.5) / ss
    gx, gz = np.meshgrid(cx + s, cz + s)
    return float(_inside(pts, gx, gz).mean())


def _stud_hits(pts, cx, cz, ss=24):
    """How much of the stud of cell (cx, cz) lies under the outline: 0 (clear) .. 1 (wholly)."""
    a = np.linspace(0, 2 * math.pi, ss, endpoint=False)
    rr = np.array([0.0] + [STUD_R * 0.5] * 8 + [STUD_R] * ss)
    aa = np.concatenate([[0], np.linspace(0, 2 * math.pi, 8, endpoint=False), a])
    px, pz = cx + 0.5 + rr * np.cos(aa), cz + 0.5 + rr * np.sin(aa)
    return float(_inside(pts, px, pz).mean())


def tile_cells(pts, dx, dz, x, z):
    """For a placed tile: cells it covers (no other tile there), cells it grips (stud wholly
    under it) and cells whose stud would hit its rim (they need a flat top one layer down)."""
    covers, grips, clash = set(), set(), set()
    for i in range(x - 1, x + dx + 1):
        for j in range(z - 1, z + dz + 1):
            if _coverage(pts, i, j) > 0.01:
                covers.add((i, j))
            h = _stud_hits(pts, i, j)
            if h > 0.999:
                grips.add((i, j))
            elif h > 0:
                clash.add((i, j))
    return covers, grips, clash


@dataclass
class Placed:
    part: str
    x: int
    z: int
    rot: int
    color: str

    def geometry(self):
        return placed_geometry(self.part, self.x, self.z, self.rot)


# ---- hinged panels ---------------------------------------------------------------------------
@dataclass
class HingeSpec:
    name: str
    toward: int          # the way the panel tips down: 0 +x, 1 +z, 2 -x, 3 -z
    angle: float         # degrees below horizontal (a multiple of 22.5 for click hinges)
    edge: int            # stud line (along `toward`) where the fixed hinge plates end
    y: int               # plate level the fixed hinge plates sit on
    a0: int              # first stud across
    W: int               # studs across
    H: int               # rows down the slope
    D: int               # the designer's plate layers (the grid adds a hinge layer underneath)
    hinges: tuple = ()   # across stud coordinates (world) of the hinge pairs
    row: int = 0         # panel row over the moving plate's first stud
    mount: str = field(default="hinge")

    @property
    def along_x(self) -> bool:
        return self.toward in (0, 2)

    def frame(self):
        """World unit vectors of panel x (across, right as seen square-on), y (out, the face
        normal) and z (down the slope)."""
        ux, uz = DIR_VEC[self.toward]
        u = np.array([ux, 0.0, uz])
        a = math.radians(self.angle)
        d = math.cos(a) * u - math.sin(a) * np.array([0.0, 1.0, 0.0])
        n = math.sin(a) * u + math.cos(a) * np.array([0.0, 1.0, 0.0])
        return np.cross(n, d), n, d

    def rotation(self):
        r, n, d = self.frame()
        return np.stack([r, n, d], axis=1)

    def sign(self):
        ux, uz = DIR_VEC[self.toward]
        return ux + uz

    def axis_point(self):
        """World mm of the hinge axis at the panel's left edge (panel x = 0)."""
        r, _, _ = self.frame()
        along = self.edge * STUD_MM + AXIS_BEYOND_MM * self.sign()
        across_axis = 2 if self.along_x else 0
        across = self.a0 * STUD_MM if r[across_axis] > 0 else (self.a0 + self.W) * STUD_MM
        yv = (self.y + 1) * PLATE_MM - AXIS_BELOW_TOP_MM
        return np.array([along, yv, across]) if self.along_x else np.array([across, yv, along])

    def origin(self):
        """World mm of the panel grid's (0, 0, 0) corner: left edge, bottom of the hinge layer,
        top edge."""
        _, n, d = self.frame()
        e = AXIS_BEYOND_MM - STUD_MM * self.row
        return self.axis_point() + (AXIS_BELOW_TOP_MM - PLATE_MM) * n + e * d

    def to_world(self, lx, ly, lz):
        r, n, d = self.frame()
        return self.origin() + lx * r + ly * n + lz * d

    def grid_shape(self):
        return (self.W, self.H, self.D + 1)

    @property
    def top(self):
        """Plate line above the panel's highest point (for framing pictures)."""
        c = self.corners()
        return int(math.ceil(c[:, 1].max() / PLATE_MM))

    def corners(self):
        W, H, D = self.W * STUD_MM, self.H * STUD_MM, (self.D + 1) * PLATE_MM
        return np.array([self.to_world(a, b, c) for a in (0, W) for b in (0, D) for c in (0, H)])

    def column_of(self, across):
        """Panel column (x) of world stud `across`."""
        r, _, _ = self.frame()
        ax = 2 if self.along_x else 0
        return across - self.a0 if r[ax] > 0 else self.a0 + self.W - 1 - across

    # ---- the main model's side of the hinge ------------------------------------------------
    def fixed_cells(self, across):
        """Main-grid cells (x, z) of the fixed hinge plate at world stud `across`."""
        s = self.sign()
        along = [self.edge - 2, self.edge - 1] if s > 0 else [self.edge, self.edge + 1]
        return [(a, across) if self.along_x else (across, a) for a in along]

    def fixed_parts(self, color="black"):
        """Part dicts (no id yet) of the fixed hinge plates on the main model."""
        out = []
        for h in self.hinges:
            cells = self.fixed_cells(h)
            x0, z0 = min(c[0] for c in cells), min(c[1] for c in cells)
            dx, dz = (2, 1) if self.along_x else (1, 2)
            out.append({"part": HINGE_FIXED, "name": "Hinge Plate 1 x 2 Locking with 2 Fingers on End",
                        "kind": "hinge", "color": color, "x": x0, "z": z0, "y": self.y, "dx": dx,
                        "dz": dz, "h": 1, "rot": 0 if self.along_x else 1, "studs": True,
                        "shape": "hinge", "dir": self.toward, "hinge": self.name})
        return out

    def moving_parts(self, color="black"):
        """Part dicts of the moving hinge plates, in the panel grid (layer 0), fingers towards
        the hinge edge (panel -z)."""
        out = []
        for h in self.hinges:
            i = self.column_of(h)
            out.append({"part": HINGE_MOVING, "name": "Hinge Plate 1 x 2 Locking with 1 Finger on End",
                        "kind": "hinge", "color": color, "x": i, "z": self.row, "y": 0, "dx": 1,
                        "dz": 2, "h": 1, "rot": 1, "studs": True, "shape": "hinge", "dir": 3,
                        "hinge": self.name})
        return out

    def keep_clear(self, X, Y, Z, margin=0.4):
        """Which main-grid cells (arrays of cell centres: X, Z in studs, Y in plates) the panel,
        its hinge layer or the hinge knuckles would touch; the DSL carves them out."""
        c = np.stack([X * STUD_MM, Y * PLATE_MM, Z * STUD_MM], -1)
        h = np.array([STUD_MM, PLATE_MM, STUD_MM]) / 2 - margin
        R = self.rotation()
        ext = np.array([self.W * STUD_MM, (self.D + 1) * PLATE_MM, self.H * STUD_MM]) / 2
        hit = _boxes_touch(c, h, self.origin() + R @ ext, R, ext)
        A = self.axis_point()
        r, _, _ = self.frame()
        for g in self.hinges:                  # each knuckle: ~2.6 mm radius (LDraw), one stud wide
            i = self.column_of(g)
            mid = A + (i + 0.5) * STUD_MM * r
            Rk = np.stack([r, np.cross(r, [0.0, 1.0, 0.0]) if abs(r[1]) < 0.9 else [1.0, 0, 0],
                           [0.0, 1.0, 0.0]], axis=1)
            Rk[:, 1] = np.cross(Rk[:, 2], Rk[:, 0])
            hit |= _boxes_touch(c, h, mid, Rk, np.array([STUD_MM / 2, KNUCKLE_MM, KNUCKLE_MM]))
        return hit

    def to_json(self):
        return {"mount": "hinge", "name": self.name, "toward": self.toward, "angle": self.angle,
                "edge": self.edge, "y": self.y, "a0": self.a0, "W": self.W, "H": self.H,
                "D": self.D, "hinges": list(self.hinges), "row": self.row}

    @classmethod
    def from_json(cls, d):
        return cls(d["name"], d["toward"], d["angle"], d["edge"], d["y"], d["a0"], d["W"], d["H"],
                   d["D"], tuple(d["hinges"]), d.get("row", 0))

    def shift(self, dx, dz, dy):
        """The main grid grew (a base): move with it."""
        self.y += dy
        if self.along_x:
            self.edge += dx
            self.a0 += dz
            self.hinges = tuple(h + dz for h in self.hinges)
        else:
            self.edge += dz
            self.a0 += dx
            self.hinges = tuple(h + dx for h in self.hinges)


def _boxes_touch(c, h, b, R, e):
    """Axis-aligned boxes (centres c [..., 3], half sizes h [3]) against one oriented box
    (centre b, axes = columns of R, half sizes e): True where they overlap (separating axes)."""
    t = c - b
    A = [np.eye(3)[k] for k in range(3)]
    B = [R[:, k] for k in range(3)]
    axes = A + B + [np.cross(a, bb) for a in A for bb in B]
    sep = np.zeros(c.shape[:-1], bool)
    for L in axes:
        n = np.linalg.norm(L)
        if n < 1e-9:
            continue
        L = L / n
        ra = np.abs(L) @ h
        rb = sum(e[k] * abs(B[k] @ L) for k in range(3))
        sep |= np.abs(t @ L) > ra + rb
    return ~sep


def spec_from_json(d):
    """A panel spec from model.json: sideways (snot) or hinged."""
    if d.get("mount") == "hinge":
        return HingeSpec.from_json(d)
    from .snot import PanelSpec
    return PanelSpec.from_json(d)


def part_center_world(spec, q):
    """World mm centre of a panel part (either kind of panel)."""
    lo = np.array([q["x"], q["y"], q["z"]], float)
    hi = lo + np.array([q["dx"], q["h"], q["dz"]], float)
    c = (lo + hi) / 2
    return spec.to_world(c[0] * STUD_MM, c[1] * PLATE_MM, c[2] * STUD_MM)


# ---- packing a hinged panel -------------------------------------------------------------------
def pack_panel(pn, catalog, seeds=2, log=lambda *a: None):
    """Parts of a hinged panel in its grid (layer 0 hinges, layers 1..D the design):
    the moving hinge plates, base layers packed as studded plates, the top layer as tiles, and
    the hand-placed curved tiles. Cells a curved tile covers but doesn't grip get a flat tile
    one layer down, so no stud hits a rim. Returns (parts, notes)."""
    from .brickify import brickify
    sp = pn.spec
    V = pn.V                                  # design grid (W, H, D), 0 empty
    W, H, D = V.shape
    notes = []
    placed = list(getattr(pn, "placed", []))
    covers, grips, clash = set(), {}, set()
    for k, pl in enumerate(placed):
        pts, _, dx, dz = pl.geometry()
        c, g, cl = tile_cells(pts, dx, dz, pl.x, pl.z)
        covers |= c
        clash |= cl
        for cell in g:
            grips.setdefault(cell, []).append(k)
    # partly covered cells no tile grips: a flat tile one layer down (no stud to hit a rim,
    # and the gap between curves reads as one flat colour)
    clash = (covers | clash) - set(grips)
    top = D - 1
    Vt = V.copy()
    for (i, j) in covers:                     # nothing else on the top layer there
        if 0 <= i < W and 0 <= j < H:
            Vt[i, j, top] = 0
    parts = []

    def add(ps, dy):
        for p in ps:
            q = dict(p)
            q["y"] += dy
            q["id"] = len(parts)
            parts.append(q)

    for p in sp.moving_parts():
        add([p], 0)
    # base: layers 0 .. D-2 of the design, studded plates, except flat tiles where a stud
    # would hit a curved tile's rim (on the layer right under the tiles)
    base = Vt[:, :, :top].copy()
    flat = np.zeros_like(base)
    for (i, j) in clash:
        if 0 <= i < W and 0 <= j < H and top >= 1 and base[i, j, top - 1]:
            flat[i, j, top - 1] = base[i, j, top - 1]
            base[i, j, top - 1] = 0
    if base.any():
        ps, _, _ = brickify(base, pn.palette, catalog, seeds=seeds, finish="studs", log=log, shapes=False)
        add(ps, 1)
    if flat.any():
        add(_tiles(flat[:, :, top - 1], pn.palette, catalog, log), top)
    if Vt[:, :, top].any():
        add(_tiles(Vt[:, :, top], pn.palette, catalog, log), top + 1)
    for pl in placed:
        pts, org, dx, dz = pl.geometry()
        t = catalog.by_id[pl.part]
        parts.append({"id": len(parts), "part": pl.part, "name": t.name, "kind": "tile",
                      "color": pl.color, "x": pl.x, "z": pl.z, "y": top + 1, "dx": dx, "dz": dz,
                      "h": 1, "rot": pl.rot, "studs": False, "shape": "outline",
                      "outline": [[round(a, 4), round(b, 4)] for a, b in pts],
                      "origin": [round(org[0], 4), round(org[1], 4)]})
    if flat.any():
        notes.append(f"{int((flat > 0).sum())} cells around the curved tiles get flat tiles one layer down")
    return parts, notes


def _tiles(layer, palette, catalog, log):
    """One layer of cells as tiles: packed on a throwaway layer (the packer never puts tiles
    on the table), keeping only the tiles. Returns parts at y = 0."""
    from .brickify import brickify
    V = np.stack([layer, layer], axis=-1)
    # no repairs: separate islands are fine here (each sits on the panel), studding would not be
    ps, _, _ = brickify(V, palette, catalog, seeds=1, finish="tiles", log=log, shapes=False,
                        repair_rounds=0)
    out = [dict(p, y=0) for p in ps if p["y"] == 1]
    if any(p["kind"] != "tile" for p in out) or sum(p["dx"] * p["dz"] for p in out) != int((layer > 0).sum()):
        raise RuntimeError("tile layer did not pack as tiles")
    return out


def panel_connections(parts, grid_shape):
    """Stud links inside a hinged panel: box parts by occupancy, curved tiles by the cells
    they grip. Returns ({(i, j): studs}, collisions); ids are the parts' own."""
    from .validate import connection_graph, occupancy
    boxes = [p for p in parts if p.get("shape") != "outline"]
    back = [p["id"] for p in boxes]
    renum = [dict(p, id=k) for k, p in enumerate(boxes)]
    occ, coll = occupancy(renum, grid_shape)
    edges = {(back[a], back[b]): k for (a, b), k in connection_graph(renum, occ).items()}
    for p in parts:
        if p.get("shape") != "outline":
            continue
        _, grips, _ = tile_cells([tuple(v) for v in p["outline"]], p["dx"], p["dz"], p["x"], p["z"])
        y = p["y"] - 1
        for (i, j) in grips:
            if 0 <= i < grid_shape[0] and 0 <= j < grid_shape[1] and 0 <= y < grid_shape[2]:
                under = int(occ[i, j, y])
                if under >= 0:
                    key = tuple(sorted((back[under], p["id"])))
                    edges[key] = edges.get(key, 0) + 1
    return edges, coll


def tile_overlaps(parts):
    """Pairs of curved tiles (or a curved tile and a box tile on the same layer) that overlap."""
    out = []
    shaped = [p for p in parts if p.get("shape") == "outline"]
    for a in range(len(shaped)):
        pa = shaped[a]
        A = [tuple(v) for v in pa["outline"]]
        for b in range(a + 1, len(shaped)):
            pb = shaped[b]
            if pb["y"] != pa["y"]:
                continue
            B = [tuple(v) for v in pb["outline"]]
            if _polys_overlap(A, B):
                out.append((pa["id"], pb["id"]))
        for q in parts:
            if q.get("shape") == "outline" or q["y"] != pa["y"]:
                continue
            for i in range(q["x"], q["x"] + q["dx"]):
                for j in range(q["z"], q["z"] + q["dz"]):
                    if _coverage(A, i, j) > 0.01:
                        out.append((pa["id"], q["id"]))
                        break
                else:
                    continue
                break
    return out


def _polys_overlap(A, B, ss=0.05):
    """Do two outlines overlap by more than 2% of a stud's area?"""
    x0 = max(min(p[0] for p in A), min(p[0] for p in B))
    x1 = min(max(p[0] for p in A), max(p[0] for p in B))
    z0 = max(min(p[1] for p in A), min(p[1] for p in B))
    z1 = min(max(p[1] for p in A), max(p[1] for p in B))
    if x0 >= x1 or z0 >= z1:
        return False
    gx, gz = np.meshgrid(np.arange(x0 + ss / 2, x1, ss), np.arange(z0 + ss / 2, z1, ss))
    both = _inside(A, gx, gz) & _inside(B, gx, gz)
    return both.sum() * ss * ss > 0.02
