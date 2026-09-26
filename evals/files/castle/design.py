# A small original castle gatehouse: two towers, a wall with a gate, crenellations.
model = Model(28, 14, 48, title="Gatehouse", author="Eval fixture")
model.box(0, 0, 0, 28, 14, 3, "dark_bluish_gray")                        # plinth
model.box(1, 3, 3, 27, 11, 30, "light_bluish_gray")                      # wall
model.box(11, 3, 3, 17, 11, 18, None)                                    # gate passage
model.box(11, 3, 18, 17, 11, 21, "dark_bluish_gray")                     # lintel
for cx in (5, 23):                                                       # towers
    model.cylinder(cx, 7, 5, 3, 42, "light_bluish_gray", inner_r=2.5)
    model.cone(cx, 7, 5.5, 0.8, 42, 48, "dark_red")
model.where(lambda X, Y, Z: (Y >= 30) & (Y < 33) & (Z > 3) & (Z < 11) & (X > 9) & (X < 19)
            & ((np.floor(X) % 2) == 0), "light_bluish_gray")             # crenellations
model.box(12, 10, 21, 16, 11, 27, "reddish_brown")                       # banner
