# Regression: stair-step circle rings that widen upward. Corner cells of each new ring can
# only be anchored through one neighbour, and two corners can compete for the same anchor
# (the "circle-corner overhang conflict"); the packer's most-constrained-first order and
# lookahead must anchor all of them without trimming.
EXPECT = {"passed": True, "trimmed_cells": 0, "recolored_cells": 0}
model = Model(16, 16, 20, title="Circle corner overhang")
model.cylinder(8, 8, r=3.2, y0=0, y1=6, color="dark_bluish_gray")
model.cone(8, 8, r0=3.2, r1=7.6, y0=6, y1=14, color="white", inner=2.2)
model.cylinder(8, 8, r=7.6, y0=14, y1=15, color="red")
