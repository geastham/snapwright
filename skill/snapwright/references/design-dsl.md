# Design DSL

A design file is plain Python run with these names pre-imported: `Model`, `np`, `math`,
`mm_to_studs`, `mm_to_plates`, `STUD_MM`, `PLATE_MM`. It must end with a variable `model`.

Coordinates: `x` and `z` in studs, `y` in plates, `y = 0` is the table. Cell centres are at
`+0.5`. Later calls overwrite earlier ones. Colours are catalog keys (`"dark_bluish_gray"`),
`None` carves.

| Call | What it does |
|---|---|
| `Model(w, d, h, title=, subtitle=, author=)` | empty grid, w x d studs, h plates |
| `box(x0, z0, y0, x1, z1, y1, color)` | half-open box |
| `cylinder(cx, cz, r, y0, y1, color, inner_r=None)` | vertical cylinder or tube |
| `cone(cx, cz, r0, r1, y0, y1, color, inner=None)` | frustum; `inner` = wall thickness |
| `ellipsoid(cx, cy, cz, rx, ry, rz, color)` | rx/rz studs, ry plates |
| `sphere(cx, cy, cz, r_mm, color)` | true sphere, aspect handled |
| `where(fn, color)` | fill where `fn(X, Y, Z)` is true |
| `paint(fn, color)` | recolour filled voxels only (stripes, eyes, windows) |
| `carve(fn)` | remove voxels |
| `mirror_x(about=None)` | copy left half to right (symmetric subjects) |
| `mosaic(path, colors=None, mode="flat"|"upright", base_color=, depth=2, dither=False, base_layers=2)` | photo to mosaic; flat = `base_layers` plate layers + a picture layer (grid grows to fit) |
| `hollow(wall=2, cap=3, brace_every=8, brace=2, floor=True)` | remove hidden interior, keep a shell and 2x2 bracing columns; call last |
| `base(color="dark_bluish_gray", layers=2, margin=1)` | stand the model on a plate base (grid grows, model moves up) |
| `panel(name, face="+z", at=0, plane=None, top=None, width=4, height=4, depth=2)` | a sideways (SNOT) panel on a face; returns a panel model to paint |
| `grow_height(h)` | make the grid at least `h` plates tall |
| `islands()` | voxel groups touching neither the ground nor the rest (must be empty to build) |

`X, Y, Z` passed to lambdas are full numpy grids, so use `np.abs`, `np.hypot`, `&`, `|`.

## Patterns

Tapered hollow tower: `model.cone(C, C, 7, 5, 12, 78, "white", inner=2.2)`
Stripes: `model.paint(lambda X, Y, Z: ((Y - 12) // 12) % 2 == 1, "red")`
Window on the front only: `model.paint(lambda X, Y, Z: (np.abs(X - C) < 1) & (Z > C) & (Y >= 30) & (Y < 36), "dark_blue")`
Organic noise: `model.paint(lambda X, Y, Z: np.sin(X * 1.7) + np.cos(Z * 1.3) > 0.9, "light_bluish_gray")`

## Scale and likeness

- Features that carry identity (eyes, ears, beaks, windows) need at least 2 studs, or they
  vanish into speckle and the repair loop may recolour them.
- Vertical resolution is 2.5x horizontal. A round thing 10 studs wide is 25 plates tall.
- Thin vertical parts (< 2 x 2 studs) over ~8 plates tall are fragile; thicken or brace.
- Every overhang needs something to hang from: extend it inward over supported cells.
- Seal hollow shells with a solid cap so interiors stay hidden (hidden cells can use any colour).
  `hollow()` does this for you and only ever removes cells nobody can see.
- You don't place slopes or round parts: the build puts slopes on the stair steps of real
  tapers (it smooths the surface first, so near-vertical walls stay square), inverted slopes
  under 1-stud overhang lips, round bricks/plates on thin 1x1 and 2x2 columns, and round
  tiles on the stair-step corners of curves. Design the voxel shape; shaping follows it.

## Sideways panels

`model.panel(...)` makes a small model that is built flat and tipped onto a face of the main
model, studs pointing out, clipped onto side-stud bricks the build places right behind it.

- `face`: "+z", "-z", "+x" or "-x", the way the panel faces. Seen from in front of that face,
  panel `x` runs left to right, panel `z` counts rows DOWN from the top edge, and panel `y`
  counts plate layers outward (layer 0 against the model, the last layer is the surface).
- `at`: first stud along the face; `width`, `height` in studs; `depth` in plates (2 = a
  backing plate layer plus a tile layer).
- `plane`: the face plane as a stud boundary (default: the model's surface there); `top`:
  plate line of the panel's top edge (default: the top of the wall behind it).
- The panel's space is carved out of the model. The model must be solid right behind the
  panel: side-stud bricks go on anchor rows every 2 studs (5 plates = 2 studs).
- Paint it with the usual calls in panel coordinates; `panel.mosaic(img)` reads upright.
- A 2-plate panel sits 1.6 mm inside the surrounding surface (reported). Even heights keep
  both edges on plate lines. Panels use bricks, plates and tiles only (no surface shaping).
