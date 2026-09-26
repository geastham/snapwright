# Snapwright benchmark: a large hollow stone keep (original, generic subject), ~5,000+ parts.
# Used by `make bench` to check the M1 target: a 5,000-part model builds in under 3 minutes.
model = Model(48, 48, 141, title="Stone Keep", subtitle="Large benchmark build", author="Open Conjecture")

# stepped plinth
model.box(0, 0, 0, 48, 48, 3, "dark_bluish_gray")
model.box(1, 1, 3, 47, 47, 6, "dark_bluish_gray")

# hollow walls, 4 studs thick, weathered stone in 2 x 2-stud, 3-plate patches
model.box(2, 2, 6, 46, 46, 129, "light_bluish_gray")
model.box(6, 6, 9, 42, 42, 129, None)                      # hollow inside, floor at 6-9
model.paint(lambda X, Y, Z: (np.sin(np.floor(X / 2) * 1.3 + np.floor(Y / 3) * 0.9)
                             * np.cos(np.floor(Z / 2) * 1.7 + np.floor(Y / 3) * 0.4) > 0.35),
            "dark_bluish_gray")

# a string course every 24 plates
model.paint(lambda X, Y, Z: (Y % 24 >= 21) & (Y % 24 < 24), "tan")

# windows: 2 studs wide, 9 plates tall, dark, on all four faces
for yw in (30, 54, 78, 102):
    for c in (12, 20, 28, 34):
        model.box(c, 2, yw, c + 2, 6, yw + 9, "black")
        model.box(c, 42, yw, c + 2, 46, yw + 9, "black")
        model.box(2, c, yw, 6, c + 2, yw + 9, "black")
        model.box(42, c, yw, 46, c + 2, yw + 9, "black")

# roof deck and crenellations on top of the outer wall ring
model.box(2, 2, 129, 46, 46, 132, "dark_bluish_gray")
model.where(lambda X, Y, Z: (Y >= 132) & (Y < 141) & (X > 2) & (X < 46) & (Z > 2) & (Z < 46)
            & ((X < 5) | (X > 43) | (Z < 5) | (Z > 43))
            & ((((np.floor(X) + np.floor(Z)) // 3) % 2) == 0), "light_bluish_gray")

# door
model.box(22, 2, 9, 26, 6, 27, "reddish_brown")

# a central stone pillar carrying the roof deck
model.cylinder(24, 24, r=3.2, y0=9, y1=129, color="dark_bluish_gray")
