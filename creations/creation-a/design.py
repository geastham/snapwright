# Snapwright design file: Lakeside Sail Tower (creation A). Units: x/z studs (8 mm), y plates
# (3.2 mm). Front (+z) = the south face, seen from the lake; x runs west -> east.
#
# Form, measured from the two reference photos (reference/, git-ignored):
#   * west face, the "sail": a tall face of vertical fins whose edge recedes east as it rises
#     (from the lake: flat at first, then sweeping in to the peak), x_w(t) ~ 0.48 W t^4
#   * south face: steps back floor by floor as it rises; the setbacks are the terraces that
#     read as white horizontal bands from the lake, depth(t) ~ 1 - 0.75 t
#   * east edge: steps in slightly, x_e(t) ~ W (1 - 0.36 t)
#   * north face: straight up
# t = height fraction of the tower above the podium. Floors step every 3 plates (one brick).
import math

W, D = 25, 20                    # tower footprint, studs (x west->east, z north->south)
PODIUM = 6                       # podium height, plates
TOWER = 108                      # tower height above the podium, plates
FLOOR = 3                        # plates per terrace step
M = 2                            # margin around the tower on the podium, studs
NX, NZ, NY = W + 2 * M, D + 2 * M, PODIUM + TOWER

model = Model(NX, NZ, NY, title="Lakeside Sail Tower",
              subtitle="A curved-sail office tower with stepped terraces", author="Open Conjecture")


def storey(y):
    """Height fraction of the terrace step containing plate y (0 at the podium top)."""
    return (((y - PODIUM) // FLOOR) * FLOOR) / TOWER


def x_west(t):
    return M + 0.48 * W * t ** 4


def x_east(t):
    return M + W * (1 - 0.36 * t)


def z_south(t):                   # north edge at z = M, south face steps back towards it
    return M + D * (1 - 0.75 * t)


def tower(X, Y, Z):
    t = (Y - PODIUM) / TOWER
    ts = ((Y - PODIUM) // FLOOR) * FLOOR / TOWER
    return ((Y >= PODIUM) & (X >= x_west(t)) & (X < x_east(ts)) & (Z >= M) & (Z < z_south(ts)))


model.box(0, 0, 0, NX, NZ, PODIUM, "dark_bluish_gray")                  # podium
model.where(tower, "light_bluish_gray")

# terrace edges: the top plate of every step on the south face is a white band
def terrace(X, Y, Z):
    ts = ((Y - PODIUM) // FLOOR) * FLOOR / TOWER
    return (Y >= PODIUM) & ((Y - PODIUM) % FLOOR == FLOOR - 1) & (Z >= z_south(ts) - 1)
model.paint(terrace, "white")

# the sail's vertical fins: white stripes on every cell of the west face (the cells whose
# west side is open), one stud wide every other stud, so they follow the curve as it recedes
import numpy as np
F = model.V > 0
west = F.copy()
west[1:] &= ~F[:-1]
model.paint(lambda X, Y, Z: west & (Y >= PODIUM) & (Z.astype(int) % 2 == 0), "white")

model.hollow()
