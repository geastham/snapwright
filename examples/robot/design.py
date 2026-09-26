# Snapwright design file: a friendly robot with a sideways-built (SNOT) face and chest display.
# Original, generic subject. Units: x/z in studs (8 mm), y in plates (3.2 mm). 3 plates = 1 brick.
# Panels are built flat and clipped onto side studs; see references/design-dsl.md, "Sideways panels".

model = Model(16, 12, 78, title="Signal Robot",
              subtitle="An original brick-built robot with sideways-built face and chest",
              author="Open Conjecture")

# feet and legs
model.box(2, 2, 0, 7, 10, 3, "dark_bluish_gray")
model.box(9, 2, 0, 14, 10, 3, "dark_bluish_gray")
model.box(3, 4, 3, 6, 8, 18, "light_bluish_gray")
model.box(10, 4, 3, 13, 8, 18, "light_bluish_gray")

# body
model.box(1, 2, 18, 15, 10, 51, "medium_azure")
model.box(1, 2, 18, 15, 10, 21, "dark_blue")                       # waist band

# arms
model.box(0, 4, 24, 1, 8, 48, "light_bluish_gray")
model.box(15, 4, 24, 16, 8, 48, "light_bluish_gray")

# neck and head
model.box(6, 4, 51, 10, 8, 54, "dark_bluish_gray")
model.box(3, 2, 54, 13, 10, 75, "light_bluish_gray")
model.cylinder(8, 6, 0.8, 75, 78, "red")                           # antenna

# chest display: a sideways panel, 10 x 6 studs: a screen showing four signal bars
chest = model.panel("Chest", face="+z", at=3, top=48, width=10, height=6, depth=2)
chest.box(0, 0, 0, 10, 6, 1, "black")
chest.box(0, 0, 1, 10, 6, 2, "dark_bluish_gray")                  # frame
chest.box(1, 1, 1, 9, 5, 2, "black")                              # screen
for k in range(4):                                                # bars rise left to right
    chest.box(1 + 2 * k, 4 - k, 1, 2 + 2 * k, 5, 2, "lime" if k < 3 else "yellow")

# face: 8 x 6 studs, two eyes and a smile
face = model.panel("Face", face="+z", at=4, top=72, width=8, height=6, depth=2)
face.box(0, 0, 0, 8, 6, 1, "black")
face.box(0, 0, 1, 8, 6, 2, "white")
face.box(1, 1, 1, 3, 3, 2, "black")
face.box(5, 1, 1, 7, 3, 2, "black")
face.box(2, 4, 1, 6, 5, 2, "red")
face.box(1, 3, 1, 2, 4, 2, "red")
face.box(6, 3, 1, 7, 4, 2, "red")
