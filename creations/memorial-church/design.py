# Memorial Church, the Main Quad frontage. Units: x/z in studs (8 mm), y in plates (3.2 mm).
# The front faces +z. Heights come from reference/view_front.jpg, a generated front elevation
# (brief.md, section 7); the gable mosaic's colours are stored in mosaic_keys.json.
import json
import os
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "reference")

NX, NZ, NY = 54, 32, 90
G = 2                                  # plaza thickness: the building starts on plate 2
FX0, FX1 = 13, 41                      # facade block, x
CX = (FX0 + FX1) / 2                   # centre line (a grid line: symmetric features are even)
FZ = 16                                # front plane of the facade and the arcades
BZ0 = 5                                # back of the church block

model = Model(NX, NZ, NY, title="Memorial Church", subtitle="The Main Quad frontage", author="")

# ---- plaza: 2 plates, tan paving, dark tan edge, the round paving circle ----------------------
model.box(0, 0, 0, NX, NZ, G, "tan")
model.where(lambda X, Y, Z: (np.floor(Y) == G - 1) & ((X < 1) | (X > NX - 1) | (Z > NZ - 1)), "dark_tan")
PCX, PCZ = CX, 24.4


def ring(r0, r1):
    return lambda X, Y, Z: (np.floor(Y) == G - 1) & (np.hypot(X - PCX, Z - PCZ) >= r0) & (np.hypot(X - PCX, Z - PCZ) < r1)


model.where(ring(0, 7.4), "light_bluish_gray")
model.where(ring(6.6, 7.4), "dark_orange")                   # outer terracotta band
model.where(ring(4.2, 4.8), "tan")                           # inner ring
model.where(ring(0, 1.3), "dark_orange")                     # centre
for ang in range(0, 360, 45):                                # an eight-point rose between the rings
    a_ = np.radians(ang)
    px, pz = PCX + 5.7 * np.cos(a_), PCZ + 5.7 * np.sin(a_)
    model.where(lambda X, Y, Z, px=px, pz=pz: (np.floor(Y) == G - 1) & (np.hypot(X - px, Z - pz) < 0.75), "dark_orange")
for ang in (0, 90, 180, 270):
    a_ = np.radians(ang)
    px, pz = PCX + 2.8 * np.cos(a_), PCZ + 2.8 * np.sin(a_)
    model.where(lambda X, Y, Z, px=px, pz=pz: (np.floor(Y) == G - 1) & (np.hypot(X - px, Z - pz) < 1.0), "sand_green")

# ---- the church block behind the facade: walls, gable roof, drum towers ------------------------
EAVE, APEX = G + 50, G + 75
model.box(FX0, BZ0, G, FX1, FZ, EAVE, "tan")
half = (FX1 - FX0) / 2


def roof(X, Y, Z):
    h = EAVE + (APEX - EAVE) * np.clip(1 - np.abs(X - CX) / half, 0, 1)
    return (X >= FX0 - 0.5) & (X <= FX1 + 0.5) & (Z >= BZ0) & (Z < FZ - 2) & (Y >= EAVE) & (Y < h)


model.where(roof, "dark_orange")
# the gable wall at the front: tan, up to the rake
model.where(lambda X, Y, Z: (X >= FX0) & (X < FX1) & (Z >= FZ - 2) & (Z < FZ) & (Y >= EAVE)
            & (Y < EAVE + (APEX - EAVE) * np.clip(1 - np.abs(X - CX) / half, 0, 1)), "tan")
for tx in (FX0 - 1, FX1 + 1):           # drum towers beside the gable, behind the arcades
    model.cylinder(tx, BZ0 + 4, 2.6, G, G + 46, "tan")
    model.paint(lambda X, Y, Z, tx=tx: (np.floor(Y) >= G + 36) & (np.floor(Y) < G + 42)
                & (np.abs(X - tx) < 0.6) & (Z > BZ0 + 4), "dark_blue")                  # a window
    model.box(tx - 3, BZ0 + 1, G + 45, tx + 3, BZ0 + 7, G + 46, "dark_tan")         # cornice
    model.cone(tx, BZ0 + 4, 3.1, 0.6, G + 46, G + 55, "dark_orange")
# two round trees behind the arcades, as in the photos
for tx in (4.0, NX - 4.0):
    model.box(tx - 1, BZ0 + 2, G, tx + 1, BZ0 + 4, G + 22, "reddish_brown")
    model.ellipsoid(tx, G + 36, BZ0 + 3, 4.2, 15, 4.2, "green")
    canopy = lambda X, Y, Z, tx=tx: (((X - tx) / 4.2) ** 2 + ((Y - (G + 36)) / 15) ** 2       # noqa: E731
                                     + ((Z - (BZ0 + 3)) / 4.2) ** 2) <= 1
    model.paint(lambda X, Y, Z, canopy=canopy: canopy(X, Y, Z)
                & ((np.floor(X) + np.floor(Y / 3) + np.floor(Z)) % 3 == 0), "dark_green")

# ---- portal storey: three arched portals, gold mosaic spandrels, carved band -------------------
SPRING, R = G + 8.5, 3.0                # arch springing (plates), radius (studs)
ARCH_X = [(FX0 + 2, FX0 + 8), (FX0 + 11, FX0 + 17), (FX0 + 20, FX0 + 26)]


def portal(X, Y, Z):
    out = np.zeros(X.shape, bool)
    for a, b in ARCH_X:
        c = (a + b) / 2
        dy = (Y - SPRING) * 3.2 / 8.0    # plates -> studs
        inside = (X > a) & (X < b) & ((Y < SPRING) | ((X - c) ** 2 + dy ** 2 <= R ** 2))
        out |= inside
    return out & (Y >= G) & (Z >= FZ - 3) & (Z < FZ)


model.carve(portal)
for a, b in ARCH_X:                     # doors at the back of the porch
    model.box(a + 1, FZ - 4, G, b - 1, FZ - 3, G + 13, "reddish_brown")

# the spandrels: a gold mosaic band over the arches with five angel roundels (the photo shows
# them over the piers and between the arches)
BAND0, BAND1 = G + 23, G + 27
model.paint(lambda X, Y, Z: (X >= FX0 + 1) & (X < FX1 - 1) & (Z >= FZ - 1) & (Y >= G + 14) & (Y < BAND0),
            "bright_light_orange")
for rx in (FX0 + 2, FX0 + 9.5, CX, FX1 - 9.5, FX1 - 2):
    model.paint(lambda X, Y, Z, rx=rx: (Z >= FZ - 1) & (np.hypot(X - rx, (Y - (G + 19.5)) * 0.4) <= 1.25),
                "medium_azure")
    model.paint(lambda X, Y, Z, rx=rx: (Z >= FZ - 1) & (np.hypot(X - rx, (Y - (G + 19.5)) * 0.4) <= 0.6),
                "white")
for a, b in ARCH_X:                     # carved stone rings round the portal arches
    c = (a + b) / 2
    model.paint(lambda X, Y, Z, c=c: (Z >= FZ - 1) & (Y >= SPRING)
                & (np.hypot(X - c, (Y - SPRING) * 0.4) <= R + 0.9), "dark_tan")
model.box(FX0, FZ - 1, BAND0, FX1, FZ, BAND1, "dark_tan")        # the carved band
model.box(FX0, FZ - 1, G, FX1, FZ, G + 1, "dark_tan")            # plinth course

# ---- arcades: 3 bays each side on round columns, tile roofs --------------------------------------
AE, AR = G + 21, G + 27                 # arcade eaves, ridge
for x0, x1 in ((0, FX0), (FX1, NX)):
    model.box(x0, FZ - 4, G, x1, FZ - 3, AE, "tan")              # back wall
    model.box(x0, FZ - 1, G + 11, x1, FZ, AE, "tan")             # the arched front wall
    cols = range(x0, x1, 4) if x0 == 0 else range(x1 - 1, x0 - 1, -4)
    for c in cols:
        model.box(c, FZ - 1, G, c + 1, FZ, G + 11, "tan")        # columns
        model.box(c, FZ - 1, G + 10, c + 1, FZ, G + 11, "dark_tan")   # capitals
        model.box(c, FZ - 1, G, c + 1, FZ, G + 1, "dark_tan")    # bases
    model.box(x0, FZ - 4, AE - 1, x1, FZ, AE, "tan")             # ceiling ties front to back
    model.where(lambda X, Y, Z, x0=x0, x1=x1: (X >= x0) & (X < x1) & (Z >= FZ - 4.5) & (Z < FZ + 0.5)
                & (Y >= AE) & (Y < AR - (AR - AE) * np.abs(Z - (FZ - 2)) / 2.5), "dark_orange")
    for c in (cols if x0 == 0 else sorted(cols)):              # round the arch heads
        a = c + 1 if x0 == 0 else c - 3
        if a < x0 or a + 3 > x1:
            continue
        cx = a + 1.5
        model.paint(lambda X, Y, Z, cx=cx: (Z >= FZ - 1) & (Y >= G + 11)
                    & (np.hypot(X - cx, (Y - (G + 11)) * 0.4) <= 2.4), "dark_tan")
        model.carve(lambda X, Y, Z, cx=cx, a=a: (X > a) & (X < a + 3) & (Z >= FZ - 1) & (Z < FZ)
                    & (Y >= G + 11) & (((X - cx) ** 2 + ((Y - (G + 11)) * 0.4) ** 2) <= 1.5 ** 2))

# ---- the cross on the apex -----------------------------------------------------------------------
model.box(CX - 1, FZ - 2, APEX - 3, CX + 1, FZ - 1, APEX + 10, "dark_tan")
model.box(CX - 2, FZ - 2, APEX + 6, CX + 2, FZ - 1, APEX + 8, "dark_tan")

model.hollow()

# ---- the upper facade, built in plates: every plate edge is a mosaic pixel (a stud wide, a
# plate tall), 2.5x the vertical detail of an upright panel and a smoother gable edge ---------------
# The gable mosaic comes from the generated elevation (reference/detail_mosaic_upper_generated.png),
# quantised per source pixel so each figure keeps its own colour instead of averaging to tan; the
# windows are drawn by hand.
from PIL import ImageEnhance
from snapwright.catalog import hex_to_rgb, rgb_to_lab

W, Y0, ROWS = FX1 - FX0, G + 27, APEX - (G + 27)          # 28 studs x 48 plates, plate 29 up
PAL = [k for k in ("tan", "dark_tan", "bright_light_orange", "white", "red", "dark_red", "medium_azure", "blue",
                   "green", "dark_green", "orange", "reddish_brown", "yellow", "sand_green", "dark_blue",
                   "light_bluish_gray") if k in model.catalog.pixel_colours()]
QUIET = {"tan", "dark_tan", "light_bluish_gray", "orange", "bright_light_orange"}   # stone and gold ground
LAB = np.array([rgb_to_lab(hex_to_rgb(model.catalog.colors[k]["hex"])) for k in PAL])


def lab_img(a):
    a = a / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def mosaic_keys(path, cols, rows, share=0.12, sat=1.4, s=8):
    """Colour per cell: the loudest mosaic colour covering at least `share` of the cell, else
    the cell's majority colour (stone or gold ground). Row 0 is the top."""
    im = ImageEnhance.Color(Image.open(path).convert("RGB")).enhance(sat)
    a = np.asarray(im.resize((cols * s, rows * s), Image.LANCZOS)).astype(float)
    idx = ((lab_img(a)[..., None, :] - LAB[None, None]) ** 2).sum(-1).argmin(-1)
    keys = []
    for j in range(rows):
        row = []
        for i in range(cols):
            cnt = np.bincount(idx[j * s:(j + 1) * s, i * s:(i + 1) * s].ravel(), minlength=len(PAL)) / s ** 2
            loud = max((cnt[k], k) for k in range(len(PAL)) if PAL[k] not in QUIET)
            row.append(PAL[loud[1] if loud[0] >= share else int(cnt.argmax())])
        keys.append(row)
    return keys


# the colour grid is stored (mosaic_keys.json) so the model rebuilds exactly without the 2K source
_keys = os.path.join(HERE, "mosaic_keys.json")
keys = (json.load(open(_keys))["keys"] if os.path.exists(_keys)
        else mosaic_keys(os.path.join(REF, "detail_mosaic_upper_generated.png"), W, ROWS))
WIN_TOP = G + 50                                              # the window storey: plates 29-52
for j in range(ROWS):
    y = APEX - 1 - j
    for i in range(W):
        x = FX0 + i
        if model.V[x, FZ - 1, y] == 0:
            continue
        side = i < 3 or i >= W - 3                           # mosaic strips beside the windows
        model.box(x, FZ - 1, y, x + 1, FZ, y + 1, keys[j][i] if (y >= WIN_TOP or side) else "tan")


def front(fn):                                               # paint on the facade's face layer
    return lambda X, Y, Z: fn(X, Y, Z) & (Z >= FZ - 1)


# the rose window: arched, stained glass with a light centre and a cross of mullions
RC, RY, RR = CX, G + 40, 3.0
model.paint(front(lambda X, Y, Z: (np.abs(X - RC) <= RR + 0.9) & (Y >= G + 32) & (Y < RY)), "dark_tan")
model.paint(front(lambda X, Y, Z: (Y >= RY) & (np.hypot(X - RC, (Y - RY) * 0.4) <= RR + 0.9)), "dark_tan")
glass = lambda X, Y, Z: (((np.abs(X - RC) < RR) & (Y >= G + 33) & (Y < RY))            # noqa: E731
                         | ((Y >= RY) & (np.hypot(X - RC, (Y - RY) * 0.4) < RR)))
model.paint(front(glass), "dark_blue")
model.paint(front(lambda X, Y, Z: glass(X, Y, Z) & (np.hypot(X - RC, (Y - (G + 38)) * 0.4) < 1.3)), "medium_azure")
model.paint(front(lambda X, Y, Z: glass(X, Y, Z) & (np.floor(Y) == G + 38)), "light_bluish_gray")
# three slim arched windows each side, under a carved lintel
for wx in (FX0 + 4, FX0 + 6, FX0 + 8, FX1 - 5, FX1 - 7, FX1 - 9):
    model.box(wx, FZ - 1, G + 33, wx + 1, FZ, G + 42, "dark_blue")
    model.box(wx - 1, FZ - 1, G + 42, wx + 2, FZ, G + 43, "dark_tan")
    model.box(wx, FZ - 1, G + 43, wx + 1, FZ, G + 44, "dark_tan")
model.box(FX0 + 3, FZ - 1, G + 30, FX1 - 3, FZ, G + 32, "dark_tan")   # the balcony band under them
model.box(FX0 + 3, FZ - 1, G + 48, FX1 - 3, FZ, G + 50, "dark_tan")   # the moulding above
# stone trim along the gable's edges: the top two plates of each column
for x in range(FX0, FX1):
    col = np.nonzero(model.V[x, FZ - 1, WIN_TOP:])[0]
    if len(col):
        top = WIN_TOP + int(col.max())
        model.box(x, FZ - 1, max(WIN_TOP, top - 1), x + 1, FZ, top + 1, "dark_tan")
