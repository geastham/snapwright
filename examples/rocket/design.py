# Snapwright design file: a rocket from a 3-D model (rocket.stl, generated for this repo).
# The STL is Z-up in mm and has no colours: scale it to 25 cm, then paint the fins and nose.
# Units: x/z in studs (8 mm), y in plates (3.2 mm).
import os

HERE = os.path.dirname(os.path.abspath(__file__))
model = Model.from_mesh(os.path.join(HERE, "rocket.stl"), height_cm=25, up="z",
                        default_color="white", title="Little Rocket",
                        author="Open Conjecture")
model.subtitle = "From a 3-D model: fins thinner than a stud, kept and joined"
# the fins make the bounding box lopsided: find the body's axis from a layer above them
import numpy as np
xs, zs = np.nonzero(model.V[:, :, 40] > 0)
cx, cz = xs.mean() + 0.5, zs.mean() + 0.5
body_r = (xs.max() - xs.min() + 1) / 2 + 0.3                     # studs
model.paint(lambda X, Y, Z: ((X - cx) ** 2 + (Z - cz) ** 2 > body_r ** 2) & (Y < 20), "red")   # fins
model.paint(lambda X, Y, Z: Y >= 58, "red")                                                      # nose
