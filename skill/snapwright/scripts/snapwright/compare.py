"""Compare a design with a reference picture: silhouette overlap (IoU) from the best-matching
camera angle, a side-by-side image, and hints about what to change.

Reference silhouette, in order of preference: the image's alpha channel (a cut-out PNG), a
mask image, or a background colour estimated from the image border (works for a subject on a
plain backdrop; a busy border is reported). The model is rendered orthographically from
azimuth / elevation angles (azimuth 0 looks at the model's front, its +z face); both
silhouettes are cropped, scaled to the same height and centred, so size doesn't matter but
proportions do. Pure numpy / scipy / Pillow.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from .catalog import hex_to_rgb

STUD_MM, PLATE_MM = 8.0, 3.2
FRAME = 128            # normalised silhouette frame (pixels)
TARGET_IOU = 0.8


# ---- colour ---------------------------------------------------------------------------------

def rgb_to_lab(a):
    """sRGB (..., 3) uint8/float -> CIE Lab, vectorised."""
    a = np.asarray(a, dtype=np.float64) / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


# ---- reference ------------------------------------------------------------------------------

def _otsu(values, bins=128):
    h, edges = np.histogram(values, bins=bins)
    c = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(h)
    w1 = w0[-1] - w0
    m0 = np.cumsum(h * c) / np.maximum(w0, 1)
    m1 = (np.sum(h * c) - np.cumsum(h * c)) / np.maximum(w1, 1)
    return c[int(np.argmax(w0 * w1 * (m0 - m1) ** 2))]


def _clean(mask):
    from scipy import ndimage
    mask = ndimage.binary_opening(mask, iterations=1)
    mask = ndimage.binary_closing(mask, iterations=1)
    lab, n = ndimage.label(mask)
    if n > 1:
        sizes = np.bincount(lab.ravel())[1:]
        keep = np.nonzero(sizes >= 0.3 * sizes.max())[0] + 1
        mask = np.isin(lab, keep)
    return ndimage.binary_fill_holes(mask)


def load_reference(path, mask_path=None, max_side=512):
    """(rgb uint8 HxWx3, silhouette bool HxW, info dict)."""
    im = Image.open(path)
    im.thumbnail((max_side, max_side))
    rgba = np.asarray(im.convert("RGBA"))
    rgb = rgba[..., :3]
    info = {"method": None, "warning": None}
    if mask_path:
        m = Image.open(mask_path).convert("L").resize(im.size, Image.NEAREST)
        mask = np.asarray(m) > 127
        info["method"] = "mask"
    elif rgba[..., 3].min() < 250:
        mask = rgba[..., 3] > 127
        info["method"] = "alpha"
    else:
        H, W = rgb.shape[:2]
        b = max(2, int(0.03 * min(H, W)))
        lab = rgb_to_lab(rgb)
        border = np.concatenate([lab[:b].reshape(-1, 3), lab[-b:].reshape(-1, 3),
                                 lab[:, :b].reshape(-1, 3), lab[:, -b:].reshape(-1, 3)])
        from scipy import ndimage
        bg = np.median(border, axis=0)
        # distance from the backdrop colour, smoothed so pixel noise doesn't read as subject
        d = ndimage.gaussian_filter(np.linalg.norm(lab - bg, axis=-1), 1.5)
        db = np.concatenate([d[:b].ravel(), d[-b:].ravel(), d[:, :b].ravel(), d[:, -b:].ravel()])
        noise = float(np.percentile(db, 99))
        # a plain backdrop: anything clearly off the border's colour is subject; if that
        # swallows most of the picture the backdrop isn't plain, so split the histogram instead
        thr = max(1.5 * noise, 5.0)
        mask = d > thr
        if mask.mean() > 0.9:
            thr = max(_otsu(d), 1.5 * noise)
            mask = d > thr
        info["method"] = "background"
        edge = np.concatenate([mask[:b].ravel(), mask[-b:].ravel(), mask[:, :b].ravel(), mask[:, -b:].ravel()])
        if noise > 20:
            info["warning"] = "the background is busy; pass --mask for a reliable silhouette"
        elif edge.mean() > 0.2:
            info["warning"] = "the subject touches the picture's edge; crop wider or pass --mask"
    mask = _clean(mask)
    if not mask.any():
        why = info.get("warning") or "expected a subject on a plain background"
        raise ValueError(f"no subject found in the reference ({why}); pass --mask")
    return rgb, mask, info


# ---- model ----------------------------------------------------------------------------------

def camera(azimuth, elevation):
    """Unit vectors (right, up, towards camera) for a camera at azimuth/elevation (degrees);
    azimuth 0 looks at the +z face, positive azimuth walks round towards +x."""
    a, e = math.radians(azimuth), math.radians(elevation)
    d = np.array([math.sin(a) * math.cos(e), math.sin(e), math.cos(a) * math.cos(e)])
    r = np.cross([0.0, 1.0, 0.0], d)
    r /= np.linalg.norm(r)
    u = np.cross(d, r)
    return r, u, d


def _surface_points(V, px=1.5):
    """Sample points (mm, x y z) on the model's exposed faces, dense enough for `px` mm pixels,
    with each point's colour index."""
    F = V > 0
    P = np.pad(F, 1)
    sx = max(2, int(math.ceil(STUD_MM / px)) + 1)
    sy = max(2, int(math.ceil(PLATE_MM / px)) + 1)
    pts, cols = [], []
    # (neighbour offset in padded grid, which axis is fixed, fixed value 0/1)
    for (a, b, c), axis, side in (((2, 1, 1), 0, 1), ((0, 1, 1), 0, 0), ((1, 2, 1), 1, 1),
                                  ((1, 0, 1), 1, 0), ((1, 1, 2), 2, 1), ((1, 1, 0), 2, 0)):
        nx, nz, ny = F.shape
        nb = P[a:a + nx, b:b + nz, c:c + ny]
        xs, zs, ys = np.nonzero(F & ~nb)
        if not len(xs):
            continue
        n = {0: (sy, sx), 1: (sx, sy), 2: (sx, sx)}[axis]      # grid on the face's two free axes
        t1 = (np.arange(n[0]) + 0.5) / n[0]
        t2 = (np.arange(n[1]) + 0.5) / n[1]
        g1, g2 = [g.ravel() for g in np.meshgrid(t1, t2, indexing="ij")]
        if axis == 0:      # x fixed: free y, z
            ox, oy, oz = np.full_like(g1, side), g1, g2
        elif axis == 1:    # z fixed: free x, y
            ox, oy, oz = g1, g2, np.full_like(g1, side)
        else:              # y fixed: free x, z
            ox, oy, oz = g1, np.full_like(g1, side), g2
        pts.append(np.stack([((xs[:, None] + ox) * STUD_MM).ravel(), ((ys[:, None] + oy) * PLATE_MM).ravel(),
                             ((zs[:, None] + oz) * STUD_MM).ravel()], 1))
        cols.append(np.repeat(V[xs, zs, ys], len(g1)))
    return np.concatenate(pts), np.concatenate(cols)


def model_points(model, px):
    """Face samples of the whole model as built, sideways panels included, and the palette the
    colour indices refer to (the model's, then any colours only the panels use)."""
    pts, col = _surface_points(model.V, px)
    keys = list(model.palette)
    P, C = [pts], [col]
    for pn in getattr(model, "panels", []):
        sp = pn.spec
        idx = {i + 1: (keys.index(k) if k in keys else (keys.append(k) or len(keys) - 1)) + 1
               for i, k in enumerate(pn.palette)}
        for i, j, k in np.argwhere(pn.V > 0):             # panel x, z (rows), y (layers)
            lo, hi = sp.local_box_world(i, k, j, i + 1, k + 1, j + 1)
            n = max(2, int(math.ceil(max(hi - lo) / px)) + 1)
            t = (np.arange(n) + 0.5) / n
            g = np.stack(np.meshgrid(t, t, t, indexing="ij"), -1).reshape(-1, 3)
            P.append(lo + g * (hi - lo))
            C.append(np.full(len(g), idx[int(pn.V[i, j, k])]))
    return (np.concatenate(P), np.concatenate(C)), keys


def _extent(model):
    F = np.argwhere(model.V > 0)
    return max((F[:, 2].max() + 1) * PLATE_MM, (F[:, :2].max() + 1) * STUD_MM)


def project(V, azimuth, elevation, px=None, points=None):
    """Orthographic render: (mask HxW bool, colour index HxW (0 = none), mm per pixel).
    px: mm per pixel (default: model height / 160)."""
    from scipy import ndimage
    if points is None:
        F = np.argwhere(V > 0)
        ext = max((F[:, 2].max() + 1) * PLATE_MM, (F[:, :2].max() + 1) * STUD_MM)
        px = px or ext / 160.0
        points = _surface_points(V, px)
    pts, col = points
    r, u, d = camera(azimuth, elevation)
    U, W_, D = pts @ r, pts @ u, pts @ d
    if px is None:
        px = max(W_.max() - W_.min(), U.max() - U.min()) / 160.0
    i = np.floor((W_.max() - W_) / px).astype(np.int64)
    j = np.floor((U - U.min()) / px).astype(np.int64)
    H, W = i.max() + 1, j.max() + 1
    key = i * W + j
    order = np.lexsort((D, key))                    # nearest (largest D) last per pixel
    k, c = key[order], col[order]
    last = np.ones(len(k), dtype=bool)
    last[:-1] = k[1:] != k[:-1]
    img = np.zeros(H * W, dtype=np.int64)
    img[k[last]] = c[last]
    img = img.reshape(H, W)
    mask = ndimage.binary_closing(img > 0, iterations=1) | (img > 0)
    # fill closed-over pixels with the nearest colour
    if (mask & (img == 0)).any():
        _, (ii, jj) = ndimage.distance_transform_edt(img == 0, return_indices=True)
        img = np.where(mask, img[ii, jj], 0)
    return mask, img, px


# ---- normalised comparison ------------------------------------------------------------------

def normalise(mask, extra=None, frame=FRAME):
    """Crop to the silhouette, scale its height to 94% of the frame, centre it.
    extra: arrays of the same shape to transform the same way (nearest neighbour)."""
    rows, cols = np.nonzero(mask)
    r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    h, w = r1 - r0, c1 - c0
    s = 0.94 * frame / h
    nh, nw = max(1, round(h * s)), max(1, round(w * s))
    if nw > frame:                                  # very wide: fit the width instead
        s = 0.94 * frame / w
        nh, nw = max(1, round(h * s)), max(1, round(w * s))
    out = []
    for a in [mask] + list(extra or []):
        crop = a[r0:r1, c0:c1]
        if crop.dtype == bool:
            im = Image.fromarray(crop.astype(np.uint8) * 255).resize((nw, nh), Image.NEAREST)
            arr = np.asarray(im) > 127
            canvas = np.zeros((frame, frame), dtype=bool)
        elif crop.ndim == 3:
            arr = np.asarray(Image.fromarray(crop.astype(np.uint8)).resize((nw, nh), Image.BILINEAR))
            canvas = np.zeros((frame, frame, 3), dtype=np.uint8)
        else:
            arr = np.asarray(Image.fromarray(crop.astype(np.int32)).resize((nw, nh), Image.NEAREST))
            canvas = np.zeros((frame, frame), dtype=arr.dtype)
        t, l = (frame - nh) // 2, (frame - nw) // 2
        canvas[t:t + nh, l:l + nw] = arr
        out.append(canvas)
    return out


def iou(a, b):
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 0.0


def best_view(model, ref_norm, azimuths=range(0, 360, 15), elevations=(0, 15, 30)):
    """(iou, azimuth, elevation) of the view whose silhouette best matches ref_norm."""
    px = _extent(model) / 110.0
    pts, _ = model_points(model, px)
    best = (-1.0, 0, 0)

    def score(a, e):
        m, _, _ = project(None, a, e, px=px, points=pts)
        return iou(normalise(m)[0], ref_norm)
    for e in elevations:
        for a in azimuths:
            s = score(a, e)
            if s > best[0]:
                best = (s, a, e)
    _, a0, e0 = best
    for e in (e0 - 7.5, e0, e0 + 7.5):
        if not -10 <= e <= 45:
            continue
        for a in np.arange(a0 - 10, a0 + 10.1, 5):
            s = score(float(a) % 360, e)
            if s > best[0]:
                best = (s, float(a) % 360, e)
    return best


# ---- hints ----------------------------------------------------------------------------------

def hints(ref_n, mod_n, bands=10):
    """What to change, in words: aspect ratio and the height bands where the model is too wide
    or too narrow compared with the reference."""
    out = []

    def box(m):
        r, c = np.nonzero(m)
        return r.min(), r.max() + 1, c.min(), c.max() + 1
    rr0, rr1, rc0, rc1 = box(ref_n)
    mr0, mr1, mc0, mc1 = box(mod_n)
    ra, ma = (rc1 - rc0) / (rr1 - rr0), (mc1 - mc0) / (mr1 - mr0)
    if abs(ma / ra - 1) > 0.08:
        more = "wider" if ma > ra else "narrower"
        out.append(f"overall the model is {abs(ma / ra - 1):.0%} {more} for its height than the reference")
    ref_w = ref_n.sum(1).astype(float)
    mod_w = mod_n.sum(1).astype(float)
    top, bot = min(rr0, mr0), max(rr1, mr1)
    edges = np.linspace(top, bot, bands + 1).astype(int)
    scale = max(ref_w.max(), 1)
    diffs = []
    for k in range(bands):
        a, b = edges[k], max(edges[k] + 1, edges[k + 1])
        dw = (mod_w[a:b].mean() - ref_w[a:b].mean()) / scale
        if abs(dw) > 0.12:
            diffs.append((abs(dw), k, dw))
    for _, k, dw in sorted(diffs, reverse=True)[:3]:
        where = f"{k * 100 // bands}-{(k + 1) * 100 // bands}% down from the top"
        out.append(f"{where}: the model is {abs(dw):.0%} of the reference's width too "
                   f"{'wide' if dw > 0 else 'narrow'}")
    return out


def colour_agreement(ref_rgb_n, both, mod_col_n, palette, catalog):
    """Share of overlapping pixels where the reference's nearest palette colour is the model's
    colour there, and the most common disagreement (reference colour, model colour, share)."""
    if not both.any() or not palette:
        return None, None
    keys = list(palette)
    lab_pal = rgb_to_lab(np.array([hex_to_rgb(catalog.colors[k]["hex"]) for k in keys]))
    lab = rgb_to_lab(ref_rgb_n[both])
    nearest = np.argmin(((lab[:, None, :] - lab_pal[None]) ** 2).sum(-1), axis=1) + 1
    model = mod_col_n[both]
    ok = nearest == model
    top = None
    if (~ok).any():
        pairs = nearest[~ok] * 1000 + model[~ok]
        v, n = np.unique(pairs, return_counts=True)
        k = int(np.argmax(n))
        top = (keys[v[k] // 1000 - 1], keys[v[k] % 1000 - 1], float(n[k] / len(model)))
    return float(ok.mean()), top


# ---- the whole comparison -------------------------------------------------------------------

def compare(model, ref_path, catalog, mask_path=None, out_png=None):
    """Compare a Model with a reference picture. Returns a result dict; writes a side-by-side
    PNG (reference, model at the best view, overlap) if out_png is given."""
    rgb, ref_mask, info = load_reference(ref_path, mask_path)
    ref_n, ref_rgb_n = normalise(ref_mask, [rgb])
    score, az, el = best_view(model, ref_n)
    px = _extent(model) / 160.0
    pts, keys = model_points(model, px)
    mmask, mcol, _ = project(None, az, el, px=px, points=pts)
    mod_n, mod_col_n = normalise(mmask, [mcol])
    both = ref_n & mod_n
    agree, confusion = colour_agreement(ref_rgb_n, both, mod_col_n, keys, catalog)
    tips = hints(ref_n, mod_n)
    if agree is not None and agree < 0.6 and confusion:
        a, b, share = confusion
        tips.append(f"colour: where the reference looks {catalog.colors[a]['name'].lower()}, the model "
                    f"is {catalog.colors[b]['name'].lower()} ({share:.0%} of the overlap)")
    res = {"iou": round(score, 3), "target": TARGET_IOU, "view": {"azimuth": az, "elevation": el},
           "colour_agreement": None if agree is None else round(agree, 3), "hints": tips,
           "reference": info}
    if out_png:
        _side_by_side(rgb, ref_mask, keys, mmask, mcol, ref_n, mod_n, res, catalog, out_png)
    return res


def _side_by_side(rgb, ref_mask, keys, mmask, mcol, ref_n, mod_n, res, catalog, path, size=360):
    pal = {i + 1: hex_to_rgb(catalog.colors[k]["hex"]) for i, k in enumerate(keys)}
    # panel 1: the reference with its silhouette outline
    from scipy import ndimage
    ref = Image.fromarray(rgb).convert("RGB")
    edge = ref_mask & ~ndimage.binary_erosion(ref_mask, iterations=2)
    arr = np.asarray(ref).copy()
    arr[edge] = (255, 70, 40)
    ref = Image.fromarray(arr)
    ref.thumbnail((size, size))
    # panel 2: the model at the best view, flat colours
    m = np.full(mcol.shape + (3,), 251, dtype=np.uint8)
    for k, c in pal.items():
        m[mcol == k] = c
    mod = Image.fromarray(m)
    mod.thumbnail((size, size))
    # panel 3: overlap of the normalised silhouettes
    ov = np.full(ref_n.shape + (3,), 251, dtype=np.uint8)
    ov[ref_n & mod_n] = (190, 190, 190)
    ov[ref_n & ~mod_n] = (220, 60, 40)
    ov[mod_n & ~ref_n] = (40, 110, 200)
    ovl = Image.fromarray(ov).resize((size, size), Image.NEAREST)
    W = 3 * size + 40
    canvas = Image.new("RGB", (W, size + 80), (251, 250, 247))
    for k, im in enumerate((ref, mod, ovl)):
        canvas.paste(im, (10 + k * (size + 10) + (size - im.width) // 2, 40 + (size - im.height) // 2))
    d = ImageDraw.Draw(canvas)
    v = res["view"]
    d.text((10, 10), f"silhouette IoU {res['iou']:.2f} (target {res['target']})   best view: azimuth "
                     f"{v['azimuth']:.0f}, elevation {v['elevation']:.0f}", fill=(29, 35, 39))
    d.text((10, size + 50), "reference (outline = silhouette used)        model at best view        "
                            "overlap: grey both, red reference only, blue model only", fill=(107, 116, 121))
    canvas.save(path)
