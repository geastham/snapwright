# Snapwright design file: Lakeside Sail Tower (creation A), a lakefront diorama.
# Units: x/z studs (8 mm), y plates (3.2 mm). Front (+z) = south: the lake is in front, the
# tower stands behind a shore of autumn trees, and a low bridge crosses the lake on the right.
#
# Tower form, measured from the reference photos and the generated south and side elevations
# (reference/, git-ignored):
#   * west face, the "sail": a face of vertical fins whose edge curves east as it rises,
#     x_w(t) = 0.23 W t^4 (flat for the lower half, sweeping in near the top)
#   * the blade: a thin white fin up the south-west corner that follows that curve and rises
#     ~9% above the flat roof to a point: the spike seen from the lake
#   * south face: steps back floor by floor into terraces (white bands from the lake), and
#     recedes slowly overall, depth(t) = D (1 - 0.29 t^3)
#   * east edge: steps in steadily, x_e(t) = W (1 - 0.44 t)
#   * north face: straight up; flat roof at the top
# t = height fraction of the tower above the podium (1 at the roof). Floors step every
# 3 plates (one brick). Set SAIL_TOWER_ONLY=1 to build the tower without the diorama (for
# the likeness check against the elevations).
import math
import os

import numpy as np

DIORAMA = not os.environ.get("SAIL_TOWER_ONLY")

# ---- layout -----------------------------------------------------------------------------
NX, NZ = 48, 48
LAND = 4                          # land height, plates (the lake surface is lower)
WATER = 3                         # lake surface, plates
W, D = 22, 18                     # tower footprint, studs (x west->east, z north->south)
TX, TZ = 7, 4                     # tower's north-west corner
PODIUM = 6                        # podium height above the land, plates
TOWER = 108                       # roof height above the podium, plates
BLADE = 1.09                      # blade tip height, as a fraction of TOWER
FLOOR = 3                         # plates per terrace step
P0 = LAND + PODIUM                # plate where the tower starts
NY = P0 + int(math.ceil(TOWER * BLADE))

model = Model(NX, NZ, NY, title="Lakeside Sail Tower",
              subtitle="A curved-sail tower on the lakefront, with a shore of autumn trees",
              author="Open Conjecture")

# ---- ground: land at the back, lake in front ----------------------------------------------
# The shore runs straight across in front of the tower, then curves back on the east side,
# where the lake reaches in behind a bridge (as in reference/context_lakefront.jpg).
SHORE_Z = 32


def shore(X):                     # z of the waterline at x
    s = np.clip((X - 30) / 16, 0, 1)
    return SHORE_Z - 12 * s * s * (3 - 2 * s)


if not DIORAMA:                   # tower only: just the land under the podium
    model.box(TX - 2, TZ - 2, 0, TX + W + 2, TZ + D + 2, LAND, "dark_bluish_gray")
if DIORAMA:
    lake = lambda X, Z: Z >= shore(X)                                     # noqa: E731
    model.where(lambda X, Y, Z: ~lake(X, Z) & (Y < LAND), "dark_bluish_gray")       # land
    model.where(lambda X, Y, Z: lake(X, Z) & (Y < WATER), "dark_bluish_gray")       # lake bed
    # the water: tiles in two blues, ripples running across (east-west) like the reflections
    top = lambda Y, h: np.floor(Y) == h - 1                                # noqa: E731
    model.paint(lambda X, Y, Z: lake(X, Z) & top(Y, WATER), "medium_azure")
    model.paint(lambda X, Y, Z: lake(X, Z) & top(Y, WATER) & ((Z.astype(int) + (X.astype(int) // 6)) % 4 == 0),
                "blue")
    # a sandy edge at the waterline, grass behind it, a path behind that
    model.paint(lambda X, Y, Z: ~lake(X, Z) & top(Y, LAND) & (Z >= shore(X) - 8), "green")
    model.paint(lambda X, Y, Z: ~lake(X, Z) & top(Y, LAND) & (Z >= shore(X) - 1.5), "tan")
    model.paint(lambda X, Y, Z: ~lake(X, Z) & top(Y, LAND) & (Z >= shore(X) - 10) & (Z < shore(X) - 8), "tan")

# ---- the tower ----------------------------------------------------------------------------
def x_west(t):
    return TX + 0.23 * W * t ** 4


def x_east(t):
    return TX + W * (1 - 0.44 * t)


def z_south(t):                   # north edge at z = TZ; the south face steps back towards it
    return TZ + D * (1 - 0.29 * t ** 3)


def tower(X, Y, Z):
    t = (Y - P0) / TOWER
    ts = ((Y - P0) // FLOOR) * FLOOR / TOWER
    return (Y >= P0) & (t < 1) & (X >= x_west(t)) & (X < x_east(ts)) & (Z >= TZ) & (Z < z_south(ts))


def blade(X, Y, Z):               # the south-west corner, 2 x 2 studs, rising above the roof:
    t = (Y - P0) / TOWER          # part of the tower (a separate 1-stud fin beside the glass
    xw, zs = x_west(t), z_south(t)   # would only touch it sideways across a colour change)
    # 3 deep: above the roof it drifts east and north at once, and 2 x 2 would overlap the
    # layer below by a single stud
    return (Y >= P0) & (t < BLADE) & (X >= xw) & (X < xw + 2) & (Z >= zs - 3) & (Z < zs)


model.box(TX - 2, TZ - 2, LAND, TX + W + 2, TZ + D + 2, P0, "dark_bluish_gray")   # podium
model.where(tower, "light_bluish_gray")
model.where(blade, "white")


def terrace(X, Y, Z):             # the top plate of every second step on the south face: a thin
    ts = ((Y - P0) // FLOOR) * FLOOR / TOWER     # white band over grey glass, as in the elevation
    return ((Y >= P0) & (np.floor(Y - P0) % (2 * FLOOR) == 2 * FLOOR - 1) & (Z >= z_south(ts) - 1)
            & (X >= TX))
model.paint(terrace, "white")

# the sail's fins: white stripes on the west face (cells whose west side is open), one stud
# wide every other stud, following the curve as it recedes
F = model.V > 0
west = F.copy()
west[1:] &= ~F[:-1]
# (not on the north corner: a 1-stud colour column there shows on two sides and can't bond)
model.paint(lambda X, Y, Z: west & (Y >= P0) & (Z.astype(int) % 2 == 0) & (Z >= TZ + 2), "white")

# ---- the bridge: a low deck on piers, running east from the shore across the inlet --------
if DIORAMA:
    BZ0, BZ1 = 24, 29                 # deck width (z)
    DECK = 7                          # deck underside, plates
    for px in (39, 44):                                                     # piers
        model.box(px, BZ0 + 1, WATER, px + 2, BZ1 - 1, DECK, "light_bluish_gray")
    model.box(34, BZ0, DECK, NX, BZ1, DECK + 2, "light_bluish_gray")                     # deck
    model.box(34, BZ0, LAND, 36, BZ1, DECK, "light_bluish_gray")                         # abutment
    model.box(34, BZ0, DECK + 2, NX, BZ0 + 1, DECK + 3, "white")                         # parapets
    model.box(34, BZ1 - 1, DECK + 2, NX, BZ1, DECK + 3, "white")

model.hollow()

# ---- trees along the shore (added after hollowing so they stay solid) -----------------------
# Two staggered rows of autumn trees between the podium and the water: round canopies in
# orange, yellow and greens, with a few tall narrow conifers, as in the lakefront reference.
# Every tree stands on a 2 x 2 trunk (a canopy of 50-90 parts on a 1 x 1 trunk would hang on
# a single stud).
if DIORAMA:
    COLOURS = ["orange", "yellow", "green", "bright_light_orange", "orange", "dark_green",
               "yellow", "dark_red", "orange", "green", "bright_light_orange", "yellow"]
    rows = [(26.5, 1, 5), (29.5, 3.5, 5)]            # (z, first x, spacing)
    k = 0
    for z, x0, step in rows:
        x = x0
        while x < 33:
            r = 2.0 + 0.8 * ((k * 7) % 5) / 4                   # canopy radius 2.0-2.8 studs
            h = 10 + (k * 5) % 6                                # canopy centre height, plates
            cx, cz = int(x), int(z)
            model.box(cx, cz - 1, LAND, cx + 2, cz + 1, LAND + h, "reddish_brown")
            if k % 5 == 3:                                      # a narrow conifer
                model.cone(cx + 1, cz, 2.0, 0.6, LAND + 4, LAND + h + 10, "dark_green")
            else:
                model.ellipsoid(cx + 1, LAND + h, cz, r, r * 2.5, r, COLOURS[k % len(COLOURS)])
            x += step
            k += 1
