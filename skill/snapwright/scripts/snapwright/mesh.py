"""Read triangle meshes (OBJ with MTL colours, STL ascii/binary, glTF/GLB with materials and
node transforms) and turn them into a voxel design. numpy only.

Voxelisation: every triangle is sampled densely enough for the 8 x 8 x 3.2 mm cells, marking
a shell; a closed shell is then filled solid (open meshes stay a shell). Material colours are
matched to the nearest catalog colour; hidden interior cells take the nearest surface colour.
"""
from __future__ import annotations

import base64
import json
import math
import os
import struct

import numpy as np

STUD_MM, PLATE_MM = 8.0, 3.2


# ---- loaders: each returns (triangles float (N, 3, 3), colours list[rgb | None] per triangle) --

def load_obj(path):
    verts, tris, cols = [], [], []
    mtl, cur = {}, None
    base = os.path.dirname(path)
    for line in open(path, errors="ignore"):
        t = line.split()
        if not t:
            continue
        if t[0] == "v":
            verts.append([float(a) for a in t[1:4]])
        elif t[0] == "mtllib":
            mtl.update(_load_mtl(os.path.join(base, " ".join(t[1:]))))
        elif t[0] == "usemtl":
            cur = mtl.get(" ".join(t[1:]))
        elif t[0] == "f":
            idx = []
            for v in t[1:]:
                i = int(v.split("/")[0])
                idx.append(i - 1 if i > 0 else len(verts) + i)
            for k in range(1, len(idx) - 1):          # fan-triangulate polygons
                tris.append([idx[0], idx[k], idx[k + 1]])
                cols.append(cur)
    V = np.array(verts, dtype=np.float64)
    return V[np.array(tris, dtype=np.int64)], cols


def _load_mtl(path):
    out, cur = {}, None
    if not os.path.exists(path):
        return out
    for line in open(path, errors="ignore"):
        t = line.split()
        if not t:
            continue
        if t[0] == "newmtl":
            cur = " ".join(t[1:])
        elif t[0] == "Kd" and cur is not None:
            out[cur] = tuple(int(round(255 * min(1.0, max(0.0, float(a))))) for a in t[1:4])
    return out


def load_stl(path):
    data = open(path, "rb").read()
    if len(data) >= 84:
        n = struct.unpack("<I", data[80:84])[0]
        if len(data) == 84 + 50 * n:                     # binary
            rec = np.frombuffer(data[84:], dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)),
                                                            ("a", "<u2")]), count=n)
            return rec["v"].astype(np.float64), [None] * n
    tris, cur = [], []
    for line in data.decode("ascii", errors="ignore").splitlines():
        t = line.split()
        if t and t[0] == "vertex":
            cur.append([float(a) for a in t[1:4]])
            if len(cur) == 3:
                tris.append(cur)
                cur = []
    return np.array(tris, dtype=np.float64).reshape(-1, 3, 3), [None] * len(tris)


_COMP = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def load_gltf(path):
    """glTF 2.0 (.glb, or .gltf with embedded / external buffers): triangle primitives of
    every node in the default scene, transformed, with baseColorFactor colours."""
    raw = open(path, "rb").read()
    buffers = []
    if raw[:4] == b"glTF":
        _, _, _ = struct.unpack("<4sII", raw[:12])
        off, doc, binchunk = 12, None, None
        while off < len(raw):
            ln, typ = struct.unpack("<II", raw[off:off + 8])
            chunk = raw[off + 8:off + 8 + ln]
            if typ == 0x4E4F534A:
                doc = json.loads(chunk.decode("utf-8"))
            elif typ == 0x004E4942:
                binchunk = chunk
            off += 8 + ln
    else:
        doc = json.loads(raw.decode("utf-8"))
    for i, b in enumerate(doc.get("buffers", [])):
        uri = b.get("uri")
        if uri is None:
            buffers.append(binchunk)
        elif uri.startswith("data:"):
            buffers.append(base64.b64decode(uri.split(",", 1)[1]))
        else:
            buffers.append(open(os.path.join(os.path.dirname(path), uri), "rb").read())

    def accessor(k):
        a = doc["accessors"][k]
        if "sparse" in a:
            raise ValueError("sparse glTF accessors aren't supported")
        bv = doc["bufferViews"][a["bufferView"]]
        dt = np.dtype(_COMP[a["componentType"]]).newbyteorder("<")
        n = _NCOMP[a["type"]]
        buf = buffers[bv["buffer"]]
        start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride", 0) or dt.itemsize * n
        count = a["count"]
        if stride == dt.itemsize * n:
            arr = np.frombuffer(buf, dtype=dt, count=count * n, offset=start)
        else:
            idx = start + np.arange(count)[:, None] * stride + np.arange(n)[None] * dt.itemsize
            arr = np.frombuffer(buf, dtype=np.uint8)[(idx[..., None] + np.arange(dt.itemsize)).reshape(-1)]
            arr = arr.view(dt)
        return arr.reshape(count, n) if n > 1 else arr

    def node_matrix(nd):
        if "matrix" in nd:
            return np.array(nd["matrix"], dtype=np.float64).reshape(4, 4).T
        M = np.eye(4)
        if "scale" in nd:
            M = np.diag(list(nd["scale"]) + [1.0]) @ M
        if "rotation" in nd:
            x, y, z, w = nd["rotation"]
            R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                          [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                          [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
            R4 = np.eye(4)
            R4[:3, :3] = R
            M = R4 @ M
        if "translation" in nd:
            T = np.eye(4)
            T[:3, 3] = nd["translation"]
            M = T @ M
        return M

    def srgb(c):
        c = min(1.0, max(0.0, c))
        return int(round(255 * (12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055)))

    tris, cols = [], []

    def visit(ni, parent):
        nd = doc["nodes"][ni]
        M = parent @ node_matrix(nd)
        if "mesh" in nd:
            for prim in doc["meshes"][nd["mesh"]]["primitives"]:
                if prim.get("mode", 4) != 4:
                    continue
                P = accessor(prim["attributes"]["POSITION"]).astype(np.float64)
                P = (np.c_[P, np.ones(len(P))] @ M.T)[:, :3]
                I = accessor(prim["indices"]).astype(np.int64) if "indices" in prim else np.arange(len(P))
                T = P[I.reshape(-1, 3)]
                col = None
                if "material" in prim:
                    f = doc["materials"][prim["material"]].get("pbrMetallicRoughness", {}).get("baseColorFactor")
                    if f:
                        col = tuple(srgb(c) for c in f[:3])
                tris.append(T)
                cols.extend([col] * len(T))
        for ch in nd.get("children", []):
            visit(ch, M)

    scene = doc.get("scenes", [{"nodes": list(range(len(doc.get("nodes", []))))}])[doc.get("scene", 0)]
    for ni in scene["nodes"]:
        visit(ni, np.eye(4))
    if not tris:
        raise ValueError(f"{path}: no triangle meshes found")
    return np.concatenate(tris), cols


def load_mesh(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".obj":
        return load_obj(path)
    if ext == ".stl":
        return load_stl(path)
    if ext in (".glb", ".gltf"):
        return load_gltf(path)
    raise ValueError(f"unsupported mesh format {ext!r}: use .obj, .stl, .glb or .gltf")


# ---- voxelisation -------------------------------------------------------------------------------

def orient(tris, up="y"):
    """Rotate so `up` ("y", "z" or "-z"...) becomes +y."""
    if up in ("y", "+y"):
        return tris
    if up in ("z", "+z"):          # (x, y, z) -> (x, z, -y): z up becomes y up
        return np.stack([tris[..., 0], tris[..., 2], -tris[..., 1]], -1)
    if up == "-z":
        return np.stack([tris[..., 0], -tris[..., 2], tris[..., 1]], -1)
    if up == "x":
        return np.stack([-tris[..., 1], tris[..., 0], tris[..., 2]], -1)
    raise ValueError(f"up must be y, z, -z or x, not {up!r}")


def voxelize(tris, tri_idx, size_mm, fill=True, spacing=1.2):
    """tris (N, 3, 3) in mm, already placed at the origin; tri_idx (N,) colour index per
    triangle. Returns V (x, z, y) int16 with colour indices (0 empty)."""
    from scipy import ndimage
    NX = max(1, int(math.ceil(size_mm[0] / STUD_MM - 1e-9)))
    NY = max(1, int(math.ceil(size_mm[1] / PLATE_MM - 1e-9)))
    NZ = max(1, int(math.ceil(size_mm[2] / STUD_MM - 1e-9)))
    V = np.zeros((NX, NZ, NY), dtype=np.int16)
    edge = np.max(np.linalg.norm(tris - np.roll(tris, 1, axis=1), axis=2), axis=1)
    subdiv = np.maximum(1, np.ceil(edge / spacing)).astype(np.int64)
    for n in np.unique(subdiv):
        sel = np.nonzero(subdiv == n)[0]
        a, b = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing="ij")
        keep = a + b <= n
        w1, w2 = a[keep] / n, b[keep] / n
        w0 = 1 - w1 - w2
        for c0 in range(0, len(sel), max(1, 2_000_000 // len(w0))):
            chunk = sel[c0:c0 + max(1, 2_000_000 // len(w0))]
            T = tris[chunk]
            pts = T[:, 0, None] * w0[None, :, None] + T[:, 1, None] * w1[None, :, None] + T[:, 2, None] * w2[None, :, None]
            ix = np.clip((pts[..., 0] / STUD_MM).astype(np.int64), 0, NX - 1)
            iy = np.clip((pts[..., 1] / PLATE_MM).astype(np.int64), 0, NY - 1)
            iz = np.clip((pts[..., 2] / STUD_MM).astype(np.int64), 0, NZ - 1)
            V[ix.ravel(), iz.ravel(), iy.ravel()] = np.repeat(tri_idx[chunk], len(w0))
    if fill:
        shell = V > 0
        solid = _inside_by_parity(tris, (NX, NZ, NY))
        if solid is None:                     # not watertight: fill whatever the shell encloses
            solid = ndimage.binary_fill_holes(shell)
        else:
            # cell centres inside the surface, plus thin parts the rays miss (fins, flags),
            # with the skin cells they grow from (their roots, next to the solid body)
            thin = _sheets(shell & ~ndimage.binary_dilation(solid, iterations=1))
            if thin.any():
                # roots: skin cells touching both the thin part and the solid body
                thin |= (ndimage.binary_dilation(thin, iterations=1) & shell
                         & ndimage.binary_dilation(solid, iterations=1))
            solid |= thin
        solid = join_diagonals(solid)
        solid |= _fill_corners(solid)
        out = np.zeros_like(V)
        _, (ii, jj, kk) = ndimage.distance_transform_edt(V == 0, return_indices=True)
        out[solid] = V[ii[solid], jj[solid], kk[solid]]
        return out
    return V


def _fill_corners(S):
    """Cells that complete a 2 x 2 square (in a layer) where three cells are filled and at
    least one of them is one stud thin (in no full 2 x 2 square). A thin part running
    diagonally across the grid (a fin) rasterises as a one-stud staircase that bricks can
    barely interlock along; filling its inside corners makes it a band about two studs wide.
    Inside corners of thicker walls are left alone."""
    full = S[:-1, :-1] & S[1:, :-1] & S[:-1, 1:] & S[1:, 1:]
    covered = np.zeros_like(S)
    covered[:-1, :-1] |= full
    covered[1:, :-1] |= full
    covered[:-1, 1:] |= full
    covered[1:, 1:] |= full
    thin = S & ~covered
    a, b, c, d = S[:-1, :-1], S[1:, :-1], S[:-1, 1:], S[1:, 1:]
    ta = thin[:-1, :-1] | thin[1:, :-1] | thin[:-1, 1:] | thin[1:, 1:]
    three = (a.astype(np.int8) + b + c + d == 3) & ta
    add = np.zeros_like(S)
    add[:-1, :-1] |= three & ~a
    add[1:, :-1] |= three & ~b
    add[:-1, 1:] |= three & ~c
    add[1:, 1:] |= three & ~d
    return add


def _sheets(T, min_span=3):
    """Thin parts worth keeping: pieces at least `min_span` studs long across (a fin, a flag).
    Small blobs are surface cells overshooting a tapering tip, not features."""
    from scipy import ndimage
    lab, n = ndimage.label(T, structure=np.ones((3, 3, 3), dtype=bool))
    keep = np.zeros(n + 1, dtype=bool)
    for k, sl in enumerate(ndimage.find_objects(lab), start=1):
        if sl is not None and max(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start) >= min_span:
            keep[k] = True
    return keep[lab] & T


def join_diagonals(S, rounds=12):
    """Bricks only join face to face. Where two face-connected pieces of S touch only along an
    edge (a thin diagonal fin rasterised as a staircase of cells), fill one of the two cells
    that would join them face-on (the more enclosed one, so a tapering tip doesn't widen),
    until nothing is joined only that way."""
    from scipy import ndimage
    S = S.copy()
    offs = [(1, 1, 0), (1, -1, 0), (1, 0, 1), (1, 0, -1), (0, 1, 1), (0, 1, -1)]
    six = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
    for _ in range(rounds):
        lab, n = ndimage.label(S)
        if n <= 1:
            break
        P = np.pad(lab, 1)
        F = np.pad(S, 1).astype(np.int8)
        nb = sum(F[tuple(slice(1 + d, F.shape[k] - 1 + d) for k, d in enumerate(o))] for o in six)
        nb = np.pad(nb, 1)
        add = np.zeros_like(S)
        for o in offs:
            other = P[tuple(slice(1 + d, P.shape[k] - 1 + d) for k, d in enumerate(o))]
            meet = (lab > 0) & (other > 0) & (other != lab)
            if not meet.any():
                continue
            k1, k2 = [k for k, d in enumerate(o) if d]
            s1 = tuple(slice(1 + (o[k] if k == k1 else 0), P.shape[k] - 1 + (o[k] if k == k1 else 0)) for k in range(3))
            s2 = tuple(slice(1 + (o[k] if k == k2 else 0), P.shape[k] - 1 + (o[k] if k == k2 else 0)) for k in range(3))
            meet &= (P[s1] == 0) & (P[s2] == 0)
            if not meet.any():
                continue
            first = nb[s1] >= nb[s2]            # the bridge cell with more filled neighbours
            idx = np.nonzero(meet)
            for pick, k in ((first[idx], k1), (~first[idx], k2)):
                pos = [a[pick] for a in idx]
                pos[k] = pos[k] + o[k]
                add[tuple(pos)] = True
        if not add.any():
            break
        S |= add
    return S


def _first(o):
    return next(k for k, d in enumerate(o) if d)


def _inside_by_parity(tris, shape):
    """Cells whose centre is inside a closed mesh: cast a vertical ray through every column
    centre and fill between pairs of crossings. None if the mesh doesn't look closed.
    A ray through a shared edge or vertex hits two or more triangles at the same point, which
    would flip inside and outside for the rest of the column: coincident hits count once, and
    the rays are cast at three slightly different offsets, each cell taking the majority of
    the columns that came out even."""
    votes = np.zeros(shape, dtype=np.int8)
    valid = np.zeros(shape[:2], dtype=np.int8)
    for k, (ox, oz) in enumerate(((1e-4, 2e-4), (3.1e-4, 1.3e-4), (2.3e-4, 3.7e-4))):
        r = _parity_once(tris, shape, ox, oz)
        if r is None:
            if k == 0:
                return None
            continue
        solid, ok = r
        votes += solid
        valid += ok
    return (votes * 2 > valid[:, :, None]) & (valid[:, :, None] > 0)


def _parity_once(tris, shape, ox, oz):
    """One set of vertical rays, offset (ox, oz) mm from the column centres. Returns (solid,
    columns with an even number of crossings) or None if the mesh doesn't look closed."""
    NX, NZ, NY = shape
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    lo = np.floor((np.minimum(np.minimum(a, b), c)[:, [0, 2]] / STUD_MM) - 0.5).astype(np.int64) + 1
    hi = np.floor((np.maximum(np.maximum(a, b), c)[:, [0, 2]] / STUD_MM) - 0.5).astype(np.int64)
    lo = np.maximum(lo, 0)
    hi[:, 0] = np.minimum(hi[:, 0], NX - 1)
    hi[:, 1] = np.minimum(hi[:, 1], NZ - 1)
    nx, nz = np.maximum(hi[:, 0] - lo[:, 0] + 1, 0), np.maximum(hi[:, 1] - lo[:, 1] + 1, 0)
    cnt = nx * nz
    if not cnt.sum():
        return None
    t = np.repeat(np.arange(len(tris)), cnt)
    k = np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    ix = lo[t, 0] + k // nz[t]
    iz = lo[t, 1] + k % nz[t]
    px, pz = (ix + 0.5) * STUD_MM + ox, (iz + 0.5) * STUD_MM + oz
    A, B, C = a[t], b[t], c[t]
    d = (B[:, 2] - C[:, 2]) * (A[:, 0] - C[:, 0]) + (C[:, 0] - B[:, 0]) * (A[:, 2] - C[:, 2])
    ok = np.abs(d) > 1e-12
    d = np.where(ok, d, 1.0)
    w0 = ((B[:, 2] - C[:, 2]) * (px - C[:, 0]) + (C[:, 0] - B[:, 0]) * (pz - C[:, 2])) / d
    w1 = ((C[:, 2] - A[:, 2]) * (px - C[:, 0]) + (A[:, 0] - C[:, 0]) * (pz - C[:, 2])) / d
    w2 = 1 - w0 - w1
    hit = ok & (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
    y = w0 * A[:, 1] + w1 * B[:, 1] + w2 * C[:, 1]
    up = (((B[:, 2] - A[:, 2]) * (C[:, 0] - A[:, 0]) - (B[:, 0] - A[:, 0]) * (C[:, 2] - A[:, 2])) > 0)[hit]
    col = (ix * NZ + iz)[hit]
    y = y[hit]
    order = np.lexsort((up, y, col))
    col, y, up = col[order], y[order], up[order]
    if not len(col):
        return None
    # the same surface hit twice (through a shared edge or vertex): same point, same facing.
    # Two surfaces that touch (a cap on a cap) face opposite ways and both count.
    dup = np.r_[False, (np.diff(col) == 0) & (np.diff(y) < 1e-6) & (up[1:] == up[:-1])]
    col, y = col[~dup], y[~dup]
    starts = np.r_[0, np.nonzero(np.diff(col))[0] + 1]
    counts = np.diff(np.r_[starts, len(col)])
    if (counts % 2).mean() > 0.05:
        return None
    solid = np.zeros(shape, dtype=bool)
    ok = np.zeros(shape[:2], dtype=bool)
    centres = (np.arange(NY) + 0.5) * PLATE_MM
    for s0, n in zip(starts, counts):
        if n % 2:
            continue
        cx, cz = divmod(int(col[s0]), NZ)
        ok[cx, cz] = True
        ys = y[s0:s0 + n]
        for k2 in range(0, n, 2):
            solid[cx, cz] |= (centres >= ys[k2]) & (centres < ys[k2 + 1])
    return solid, ok
