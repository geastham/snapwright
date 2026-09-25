# Geometry, connection rules and checks

## Units
1 stud = 8 mm (LDraw 20 LDU); 1 plate = 3.2 mm (8 LDU); 1 brick = 3 plates. Grid cell =
1 x 1 stud x 1 plate. A part occupies an axis-aligned box of cells.

## What counts as connected
Two parts connect when a part with studs on top sits directly under another part: each
shared cell = 1 stud contact. Tiles have no studs, so nothing connects on top of them.
Side-by-side parts do not connect. A model is sound when every part links (through any path)
to a part standing on the table, and everything is one structure.

## How the packer builds
Courses of 3 plates; bricks where the visible colour runs through the course; plates
elsewhere with a one-stud plate margin next to bricks so plate zones interlock; tiles on
visible, supported tops; overhangs anchored first, most-constrained first, with lookahead;
hidden cells (not reachable from outside air) take any colour. Several seeds, each with a
repair loop: (1) switch stranded areas to interlocking plates, (2) allow studded plates
instead of tiles above stranded parts so they hang from neighbours, (3) only then nudge
visible surface colours. All recolouring is counted in `recolored_cells`.

## Checks and fixes

| Check | Fails when | Fix in the design |
|---|---|---|
| collisions | two parts in one cell | only possible in hand-edited models.json; rebuild |
| floating | part not linked to the grounded structure | add support under it, extend the overhang inward, merge with a neighbour of the same colour |
| structures > 1 | model falls apart into pieces | same as floating; look for 1-stud-wide colour islands and paint them 2 wide |
| com_margin_mm < 3 | tips over | widen the base, add a stand or base plate, move mass back over the feet |
| weak_parts | part > 1x1 held by one stud | thicken the join, or accept for decorative ends |
| necks | a plate boundary with <= 3 contacts under >= 6 parts | make that section at least 2 x 2 studs, overlap courses |
| unverified_combos | part-colour pair not in a verified catalog | run `sw.py sync-catalog`, or swap to a core colour |
| recolored_cells > 0 | the repair loop changed visible colour | usually a 1-stud colour speckle; simplify it |
| unanchored steps | a part can't be attached in any order | overhang with nothing above or beside; redesign |

## model.json (schema snapwright.model/0.1)
`meta` (title, slug, author, disclaimer, finish, audience), `grid.shape` [x, z, y],
`colors` (used subset of the catalog), `parts[]` {id, part, name, kind, color, x, z, y, dx,
dz, h, rot, studs, step}, `steps[]` {n, parts[], kind: build|overhang|unanchored, view 0-3},
`bom` [[part, color, qty]], `stats` (see validate.py), `stats.passed`, `stats.failures`.
