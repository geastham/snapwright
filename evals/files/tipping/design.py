# A reading lamp that tips over: a slim post with a heavy shade cantilevered to one side.
model = Model(20, 10, 60, title="Reading Lamp", author="Eval fixture")
model.box(6, 3, 0, 10, 7, 2, "dark_bluish_gray")          # small foot
model.box(7, 4, 2, 9, 6, 48, "black")                    # post
model.box(7, 4, 48, 19, 6, 51, "black")                  # arm reaching out
model.cone(15, 5, 4.5, 2.5, 51, 60, "yellow", inner=1.5) # shade on the far end
model.box(11, 3, 51, 19, 7, 53, "yellow")                # shade collar joining the arm
