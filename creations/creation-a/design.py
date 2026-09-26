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
SHORE_Z = 30                      # land runs from the back (z = 0) to here; lake in front
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
if not DIORAMA:                   # tower only: just the land under the podium
    model.box(TX - 2, TZ - 2, 0, TX + W + 2, TZ + D + 2, LAND, "dark_bluish_gray")
if DIORAMA:
    model.box(0, 0, 0, NX, SHORE_Z, LAND, "dark_bluish_gray")                # land
    model.box(0, SHORE_Z, 0, NX, NZ, WATER, "dark_bluish_gray")               # lake bed
    # the water: tiles in two blues, ripples running across (east-west) like the reflections
    model.where(lambda X, Y, Z: (Z >= SHORE_Z) & (np.floor(Y) == WATER - 1), "medium_azure")
    model.where(lambda X, Y, Z: (Z >= SHORE_Z) & (np.floor(Y) == WATER - 1) & ((Z.astype(int) + (X.astype(int) // 6)) % 4 == 0),
                "blue")
    # grass along the shore, a path behind it
    model.where(lambda X, Y, Z: (Z >= SHORE_Z - 6) & (Z < SHORE_Z) & (np.floor(Y) == LAND - 1), "green")
    model.where(lambda X, Y, Z: (Z >= SHORE_Z - 8) & (Z < SHORE_Z - 6) & (np.floor(Y) == LAND - 1), "tan")

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

# ---- the bridge: a low deck on piers across the lake, on the east side ---------------------
if DIORAMA:
    BX0, BX1 = 40, 45                 # deck width (x)
    DECK = 7                          # deck underside, plates
    for pz in (SHORE_Z + 3, SHORE_Z + 9, SHORE_Z + 15):                     # piers
        model.box(BX0 + 1, pz, WATER, BX1 - 1, pz + 2, DECK, "light_bluish_gray")
    model.box(BX0, SHORE_Z - 2, DECK, BX1, NZ, DECK + 2, "light_bluish_gray")             # deck
    model.box(BX0, SHORE_Z - 2, LAND, BX1, SHORE_Z, DECK, "light_bluish_gray")            # abutment
    model.box(BX0, SHORE_Z - 2, DECK + 2, BX0 + 1, NZ, DECK + 3, "white")                 # parapets
    model.box(BX1 - 1, SHORE_Z - 2, DECK + 2, BX1, NZ, DECK + 3, "white")

# ---- a lower neighbour behind, to the east: blue glass with pale floor bands --------------
if DIORAMA:
    NB = (35, 4, 45, 16, 36)          # x0, z0, x1, z1, height above the land (plates)
    model.box(NB[0], NB[1], LAND, NB[2], NB[3], LAND + NB[4], "dark_blue")
    model.paint(lambda X, Y, Z: (X >= NB[0]) & (np.floor(Y - LAND) % 6 == 5), "light_bluish_gray")

model.hollow()

# ---- trees along the shore (added after hollowing so they stay solid) -----------------------
if DIORAMA:
    CANOPY = ["orange", "yellow", "green", "bright_light_orange", "dark_green", "orange", "yellow",
              "dark_red", "green", "orange"]
    # (x, z, canopy radius in studs, canopy centre height above the land in plates)
    TREES = [(3, 26, 2.6, 13), (8, 27, 2.2, 11), (13, 26, 2.9, 14), (18, 27, 2.3, 12),
             (23, 26, 2.7, 13), (28, 27, 2.2, 11), (33, 26, 2.8, 14), (37, 27, 2.0, 10)]
    for k, (cx, cz, r, h) in enumerate(TREES):
        # a 2 x 2 trunk: a canopy of 50-90 parts on a 1 x 1 trunk would hang on a single stud
        model.box(cx, cz - 1, LAND, cx + 2, cz + 1, LAND + h, "reddish_brown")
        model.ellipsoid(cx + 1, LAND + h, cz, r, r * 2.5, r, CANOPY[k % len(CANOPY)])
