# Tasks

Current milestone: **M3 Sideways subassemblies (SNOT)** (branch `m3-snot`). M1 and M2 merged
(PRs #1, #3). Spec: SPEC.md §5 M3.

## M3 checklist
- [x] LeoCAD check of the M2 export (docs/ldraw-check.md)
- [x] Catalog: side-stud bricks 87087, 11211, 30414 with side-stud metadata (from LDraw)
- [x] DSL: `model.panel(...)` returns a panel sub-model (own grid, own DSL) on a face of the
      model; carves its space from the main design; panel mosaics read upright from the front
- [x] Geometry: panel transform (built flat, tipped onto the face), anchor rows every 2 studs
      (5 plates) aligned to side studs 5.6 mm above a brick's bottom
- [x] Packer: side-stud anchor bricks placed behind each panel (claimed before packing)
- [x] Checks: each panel on its own (one structure, every part held through anchors, >= 2
      anchor studs), anchors aligned, panel/main collisions, balance including panels
- [x] Steps: panel steps (`kind: subassembly`) then an `attach` step after the last anchor
- [x] model.json 0.4: `subassemblies` [{name, side, grid, transform, anchors, parts}];
      reader for 0.3
- [x] Book: panel steps in a boxed inset; attach step; renderer draws panels in world views
- [x] Viewer: panels placed by their transform; attach animation
- [x] LDraw export of panels as MPD submodels (+ ldraw_check, LeoCAD); BOM includes panel parts
- [x] Example with a SNOT face and chest (examples/robot); tests (oracles per panel, all faces,
      random panels); docs
- [ ] PR; merge

SNOT facts (official LDraw library): 87087 / 11211 / 30414 side studs sit 10 LDU below the
top of the brick (5.6 mm above its bottom) on the -Z face, pointing -Z (our +z).

## M2 (done, PRs #2/#3)

### M2 checklist
- [x] Catalog 0.2: connection metadata per part (top studs / bottom sockets per cell, shape,
      LDraw file + native orientation/origin, BrickLink/Rebrickable ids); reader for 0.1
- [x] New parts: slopes 45 (3040, 3039), 33 (4286, 3298), cheese 30 (54200, 85984), inverted 45
      (3665, 3660), round plate/tile 1x1 and 2x2 (4073, 98138, 4032, 14769), round bricks
      (3062b, 3941), big plates (3958, 3036, 41539)
- [x] Connection model: per-cell studs/sockets in validator, packer support map, steps, oracles
- [x] Surface-normal pass: slopes on stair edges of tapers/curves, inverted slopes under
      overhangs, rounds on convex corners and thin columns; counted and reported
- [x] Renderer draws slopes, inverted slopes and rounds (book steps, icons, previews)
- [x] Viewer draws slopes and rounds (extruded slope profiles, cylinders, studs per cell)
- [x] LDraw export for new parts + round-trip test; checked against official LDraw geometry
      (tools/ldraw_check.py, docs/ldraw-check.md). LeoCAD screenshot: blocked (cask fails Gatekeeper)
- [x] `Model.hollow(wall=2, cap=3, brace_every=8)` with internal 2x2 bracing columns; hollow
      box and egg PASS with no major weak points and balance (tests). Saves ~35%+ mass, not parts
- [x] Base/stand: `--base auto` (default) stands a tipping model on a 2-plate base, counted as
      added support and reported; `Model.base()` for explicit stands; `--base off` to disable
- [x] Property tests + fixtures cover new parts (test_shaping, blob_1016, blob_1076); golden
      lighthouse 1,761 / 185 (M1 1,760 / 184)
- [x] SKILL.md / references / SPEC / README; book pages, viewer and LDraw renders inspected
- [x] PR with Decisions (https://github.com/geastham/snapwright/pull/2)

LDraw facts gathered from the official library (for the catalog and exporter):
- Box parts: origin top centre, long axis along LDraw X.
- 3040b/3039/4286/3298: origin top centre of the stud (back) row; body runs toward -Z; slope
  faces up toward -Z (our +z). Top studs back row only; bottom takes studs on every cell.
- 54200/85984 (cheese): origin at the BOTTOM centre, 2 plates tall, no studs, low side -Z.
- 3665a/3660: like 3040b but inverted: studs on both rows (front one open), bottom takes
  studs on the back row only.
- Rounds 4073/98138/14769/4032b/3062b/3941: centred, origin top.

## M1 (done, PR #1)

Baseline (v0.1, 2026-09-25): tests 4 passed in 67 s; lighthouse 1,744 parts / 182 steps /
4,540 connections, PASS; build with book 95 s wall / 49 s CPU; PDF 10.2 MB; deterministic
across runs (model.json identical apart from `meta.created`).

## M1 checklist
- [x] Baseline reproduced
- [x] Repo hygiene: .gitignore, stop tracking generated `out/` and `.DS_Store`
- [x] `--profile` flag: per-stage timings + cProfile dump
- [x] Unit tests for every module (catalog, dsl, brickify, validate, steps, render, book, exporters, pipeline/CLI)
- [x] Regression fixtures in `tests/fixtures/` (circle-corner overhang conflict, ...)
- [x] Property tests on random blobby models (spheres, tubes, overhangs, 1-stud speckles, stair-step circles):
      no collisions; PASS implies every part reachable from ground; steps feasible in order
- [x] Honest change counts: recoloured/trimmed computed from design vs built grid
- [x] Transparent parts: cells behind/inside trans colours keep their colour
- [x] Step feasibility includes insertion direction (from above / pressed from below)
- [x] §7.3 spatial step clustering: region growing; lighthouse mean step spread 4.53 -> 3.19 studs
- [x] §7.4 visibility-scored view choice (id-buffer): hidden new parts 2.6% -> 1.4% on random designs
      (+~2 turns per model); single hidden parts get an x-ray outline in M5
- [x] §7.5 min-cut necks: max-flow per load above each boundary; reports the piece that would
      break off. Lighthouse: now finds real 1-2 stud joints (gallery railing), old heuristic found none
- [x] §7.7 mosaic flat mode: 2 base plate layers (grid grows), repairs re-pack before touching
      the finish; dithered 16x16 noise mosaic = 1 structure, all picture parts tiles (test)
- [x] §7.8 LDraw round-trip test (exporters.parse_ldraw); LeoCAD screenshot check is M2
- [x] §7.1 PDF size: 10.2 MB -> 4.9 MB (indexed-colour images; M5 pushes further)
- [x] Performance: lighthouse with book 49 s -> ~19 s CPU; `make bench` (examples/keep, 5,068 parts,
      PASS) 106 s CPU with book (brickify 9 s, steps 22 s, book 74 s)
- [x] Golden test on the lighthouse (parts ± 5 %, PASS, deterministic across processes); 84 tests in 40 s
- [x] SKILL.md / references / SPEC / README updated; book pages, finale and viewer inspected (PNG)
- [x] PR opened with Decisions section (https://github.com/geastham/snapwright/pull/1); run summary posted

## Found so far
- Steps: deferred overhangs were resolved in one pass, so a part whose support was itself
  deferred got placed after the part above it (sandwiched, impossible to fit). Fixed:
  fixed-point resolution; overhang chains go on one link per step. Fixtures blob_003, 032, 020.
- recolored_cells was summed per repair round (double counts). Now the real design-vs-built
  difference; new `added_cells` stat. Fixture blob_020.
- Transparent colours were treated as opaque for visibility, so what's behind/inside them took
  arbitrary colours. Now see-through. Fixture blob_013, blob_026.
- Stair-step corners competing for one neighbour stranded 1x1 columns (repair couldn't fix).
  New: stranded cells become priority cells (packed first, must join a neighbour) plus a
  lone-cell rescue pass. Fixtures blob_013, blob_082 (rescue collision regression).
- Repair oscillated on mirrored stranded groups (fix one side, strand the other). Stranded
  groups are now labelled; priority cells must join a cell outside their own group, and the
  lookahead uses the same rule. Fixture blob_180.
- Trim repair deleted whole floating features (up to 208 voxels) and reported PASS. Design
  voxels not connected to the ground are never trimmed and FAIL with a join-them message
  (also warned at preview); trimming > 1% of the design FAILs. Fixture blob_082.
- Tiles on the ground layer connect to nothing (loose pieces). No tiles at y = 0.
- 300-design hunt: oracles clean; island-free FAILs 22 -> 8 (7 are honest >1% trims of
  unsupported shelves, 1 floating part: blobby seed 66, open).

- Viewer showed none of the auto-repairs (rule violation) and had a black canvas in light mode
  and a negative step counter at start. One report source (validate.report_lines) now feeds
  log, book finale and viewer (test_report.py). Viewer: transparent canvas, dt clamp, ?step=N.
- Book finale text overflowed into the footer once more lines were reported; views now shrink.
- Min-cut finds 12 weak points (<= 3 studs) on the lighthouse, e.g. a 7-part lantern stack on
  one stud at the gallery deck. Packer follow-up: prefer seeds/placements with fewer weak
  points (per-seed neck analysis costs ~1.75 s, so needs a cheaper proxy).

## Noted for later milestones
- M5: keep benchmark PDF is 20.5 MB for 5,068 parts; step view choice is 22 s there (per-step
  id-buffer renders) and could reuse one render per step.
- M5: draw an x-ray outline for a new part still hidden in its step's view (1-2% of parts).
- M6: evals.json eval 5 points at `examples/lighthouse/out/model.json`, which is no longer
  tracked; give that eval a committed fixture or have the eval generate it.
