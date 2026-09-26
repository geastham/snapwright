# Snapwright design file. Units: x/z studs (8 mm), y plates (3.2 mm). See
# skills/snapwright/references/design-dsl.md. Must define `model`.
model = Model(24, 24, 60, title="Untitled creation", subtitle="", author="Open Conjecture")
C = 12
model.cylinder(C, C, r=10, y0=0, y1=3, color="dark_bluish_gray")   # base
# block out main masses, then detail, then paint
