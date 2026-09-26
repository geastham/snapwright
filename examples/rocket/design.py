# Snapwright design file: a rocket from a 3-D model (rocket.stl, generated for this repo).
# The STL is Z-up in mm and has no colours: scale it to 25 cm, then paint the fins and nose.
# Units: x/z in studs (8 mm), y in plates (3.2 mm).
import os

HERE = os.path.dirname(os.path.abspath(__file__))
model = Model.from_mesh(os.path.join(HERE, "rocket.stl"), height_cm=25, up="z",
                        default_color="white", title="Little Rocket",
                        author="Open Conjecture")
model.subtitle = "From a 3-D model: fins thinner than a stud, kept and joined"
cx, cz = model.NX / 2, model.NZ / 2
body_r = 3.6                                                     # studs
model.paint(lambda X, Y, Z: ((X - cx) ** 2 + (Z - cz) ** 2 > body_r ** 2) & (Y < 20), "red")   # fins
model.paint(lambda X, Y, Z: Y >= 58, "red")                                                      # nose
