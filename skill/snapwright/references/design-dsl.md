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
| `mosaic(path, colors=None, mode="flat"|"upright", base_color=, depth=2, dither=False)` | photo to mosaic |

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
