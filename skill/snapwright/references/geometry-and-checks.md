# Geometry, connection rules and checks

## Units
1 stud = 8 mm (LDraw 20 LDU); 1 plate = 3.2 mm (8 LDU); 1 brick = 3 plates. Grid cell =
1 x 1 stud x 1 plate. A part occupies an axis-aligned box of cells.

## What counts as connected
Two parts connect where a stud on the lower part's top sits under a socket on the upper
part's bottom: each such cell = 1 stud contact. Box parts have studs on every top cell
(none for tiles) and sockets on every bottom cell. Shaped parts list theirs per cell in the
catalog (`top` / `bottom`): a slope has studs only on its back row; an inverted slope has
studs on top of both rows but takes studs only under its back row; 30 degree 2/3 slopes and
round tiles have none on top. Side-by-side parts do not connect. A model is sound when every part links (through any path)
to a part standing on the table, and everything is one structure.

## How the packer builds
Courses of 3 plates; bricks where the visible colour runs through the course; plates
elsewhere with a one-stud plate margin next to bricks so plate zones interlock; tiles on
visible, supported tops (never on the ground layer, where they would touch nothing);
overhangs anchored first, most-constrained first, with lookahead. Hidden cells (not
reachable from outside air) take any colour; transparent colours count as see-through, so
whatever is inside or behind them keeps its designed colour.

Before packing, surface shaping claims visible stair edges of tapers for slopes (45/33
degree on 3-plate steps, 30 degree on 2-plate steps), 1-stud overhang lips for inverted
slopes, and thin columns and curve corners for round parts. A slope goes only where the
surface smoothed over ~1.5 studs actually leans (at least ~20 degrees from flat and from
vertical) and the model rises behind it by at most two slope heights; boxes stay square.
Shaped parts are counted in `stats.shaped` / `shaped_cells` and reported (`--no-shapes` off).

Several seeds, each with a repair loop for parts left outside the main structure, least
invasive first:
1. re-pack: cells of each stranded group are packed first and must join a cell outside the
   group; a lone 1x1 left over can take a cell from an adjacent part; no bricks around them;
2. studded plates instead of tiles right above them (`studded_cells`);
3. nudge visible colours to the neighbouring colour (`recolored_cells`);
4. last resort, trim overhang cells nothing can hold (`trimmed_cells`). Voxels that don't
   touch the ground in the design (`floating_voxels`) are never trimmed.

Every automatic change is counted from the design grid vs the built grid and listed in the
CLI summary, the book finale and the viewer (all from `validate.report_lines`).

## Checks and fixes

Hard failures (the book is skipped unless `--no-strict`):

| Check | Fails when | Fix in the design |
|---|---|---|
| floating_voxels | design voxels in a group that touches neither the ground nor the rest (also warned by `preview`) | join the group to the model, or give it its own support |
| collisions | two parts in one cell | only possible in hand-edited model.json; rebuild |
| floating | part not linked to the grounded structure | add support under it, extend the overhang inward, merge with a neighbour of the same colour |
| structures > 1 | model falls apart into pieces | same as floating; look for 1-stud-wide colour islands and paint them 2 wide |
| trimmed > 1% | repairs had to cut away more than 1% of the design | add support under the overhang (a column, a bracket, a wider course below) |
| com_margin_mm < 3 | tips over (only with `--base off`; by default a 2-plate base is added and reported) | widen the base, `model.base()`, move mass back over the feet |
| unanchored steps | a part can't be attached in any order | overhang with nothing above or beside; redesign |

Notes (printed in the book and viewer; fix them when you can):

| Note | Means | Fix in the design |
|---|---|---|
| weak point (necks) | a piece of >= 6 parts is held on by <= 3 studs: the minimum cut between it and the ground in the stud-connection graph | thicken the join to at least 2 x 2 studs, overlap courses across it, or accept it for light decorative bits |
| weak_parts | part > 1x1 held by one stud | thicken the join, or accept for decorative ends |
| recolored_cells > 0 | the repair loop changed visible colour | usually a 1-stud colour speckle; simplify it |
| studded_cells > 0 | tops that should be smooth tiles got studded plates to hold parts together | usually harmless; to avoid, widen the part it holds or overlap it with the course above |
| base_cells > 0 | the model would have tipped; a 2-plate base was added under it | accept it, or move mass over the footprint and build with `--base off` |
| surface shaping | slopes / rounds replace square steps on visible tapers and curves | none needed; `--no-shapes` if you want only bricks, plates and tiles |
| unverified_combos | part-colour pair not in a verified catalog | run `sw.py sync-catalog`, or swap to a core colour |

## Sideways panels (SNOT)
A panel is its own small grid built flat (x across, y layers up, z rows) and tipped onto a
face: panel x -> right seen from the front, panel y -> out, panel z -> down (a rotation, not a
mirror). Side-stud bricks (87087, 11211, 30414) have their side studs 5.6 mm above their
bottom; with the panel's top edge on plate line T, anchor row j (even) sits on plates
T - 3 - 2.5 j, so every second panel row clips onto side studs. Checks per panel: one
structure, every part held through the side studs, at least 2 side studs, nothing of the model
in its space; the panel's mass counts in the balance check. Failures are prefixed with the
panel's name. Fix "held by 0 side studs" by making the model solid right behind the panel.

## Steps
Bottom-up by plate level. Each part is placed when it can click onto something already
placed and there is room to press it on: down onto parts below, or (overhangs) up into
parts above with nothing below it yet. Steps are compact regions of at most `max_per_step`
parts. The camera turns only between levels, to the quarter view that shows the most new
parts (id-buffer render), or for a single step when two or more of its parts would be hidden.
Each sideways panel's steps (`kind: subassembly`, `sub: name`) come right after its last
anchor brick, followed by an `attach` step (no parts).

## model.json (schema snapwright.model/0.4)
`meta` (title, slug, author, disclaimer, finish, audience), `grid.shape` [x, z, y],
`colors` (used subset of the catalog), `parts[]` {id, part, name, kind, color, x, z, y, dx,
dz, h, rot, studs, step}, `steps[]` {n, parts[], kind: build|overhang|unanchored, level,
view 0-3}, `bom` [[part, color, qty]], `stats` (see validate.py), `stats.passed`,
`stats.failures`. Shaped parts add `shape` (slope, slope_inv, round), `dir` (0-3: low side
faces +x, +z, -x, -z) and `top_cells` / `bottom_cells` ([x, z] cells with studs / sockets).
`stats.shaped`, `shaped_cells`, `base_cells`. `subassemblies[]` {name, spec {face, a0, plane,
top, W, H, D}, grid, parts (panel coordinates), anchor_studs, held, face_offset_mm, stats,
failures}; anchor bricks in `parts` have shape snot, `dir`, `side_cells`, `anchor` (panel
name) and `row`. `stats.panels` summarises them. `stats.necks[]` {plate, strength (studs), parts_above, mass_g, cut
[[lower, upper] part ids]}. Change counts: recolored_cells, trimmed_cells, added_cells,
studded_cells; floating_voxels, design_voxels. Schema 0.1 to 0.3 files are upgraded on
read (`pipeline.load_model`).
