# Snapwright design file: a striped lighthouse on a rocky base (original, generic subject).
# Units: x/z in studs (8 mm), y in plates (3.2 mm). 3 plates = 1 brick.
# Run:  python skill/snapwright/scripts/sw.py preview examples/lighthouse/design.py --out out/lh
#       python skill/snapwright/scripts/sw.py build   examples/lighthouse/design.py --out out/lh

model = Model(22, 22, 102, title="Harbour Lighthouse",
              subtitle="An original brick-built display model", author="Open Conjecture")
C = 11  # centre, studs

# rocky base: a flattened, lumpy dome of gray, with a tan path
model.cylinder(C, C, r=10.8, y0=0, y1=3, color="dark_bluish_gray")
model.cone(C, C, r0=10.5, r1=7.5, y0=3, y1=12, color="dark_bluish_gray")
model.paint(lambda X, Y, Z: (np.sin(X * 1.7) + np.cos(Z * 1.3) + (Y % 5) * 0.2) > 0.9, "light_bluish_gray")
model.box(C - 1, 0, 3, C + 1, C - 5, 12, None)                       # notch for a path
model.box(C - 1, 1, 0, C + 1, C - 5, 3, "tan")                       # path on the ground layer
model.where(lambda X, Y, Z: (abs(X - C) < 1) & (Z < C - 5) & (Z > 1) & (Y < 3 + (Z - 1) * 0.8), "tan")

# tower: a tube that narrows, with red bands every 12 plates
model.cone(C, C, r0=7.2, r1=5.2, y0=12, y1=78, color="white", inner=2.2)
model.paint(lambda X, Y, Z: (Y >= 12) & (Y < 78) & (((Y - 12) // 12) % 2 == 1), "red")
model.paint(lambda X, Y, Z: (np.abs(X - C) < 1) & (Z > C) & (Y >= 30) & (Y < 36), "dark_blue")  # windows
model.paint(lambda X, Y, Z: (np.abs(X - C) < 1) & (Z > C) & (Y >= 54) & (Y < 60), "dark_blue")

# gallery deck and railing
model.cylinder(C, C, r=7.4, y0=78, y1=80, color="dark_bluish_gray")
model.cylinder(C, C, r=7.4, y0=80, y1=83, color="black", inner_r=6.4)

# lantern room: glowing glass with four black mullions and a black crown band
model.cylinder(C, C, r=4.2, y0=80, y1=92, color="trans_yellow")
model.where(lambda X, Y, Z: (Y >= 80) & (Y < 90) & (np.hypot(X - C, Z - C) <= 4.2)
            & ((np.abs(X - C) < 1) | (np.abs(Z - C) < 1)) & (np.hypot(X - C, Z - C) > 2.5), "black")
model.cylinder(C, C, r=4.2, y0=90, y1=92, color="black")
model.cone(C, C, r0=5.2, r1=0.8, y0=92, y1=100, color="red")
model.cylinder(C, C, r=0.8, y0=100, y1=102, color="black")
