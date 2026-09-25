# Tasks

Current milestone: **M1 Harden the core** (branch `m1-hardening`). Spec: SPEC.md §5 M1, §7.

Baseline (v0.1, 2026-09-25): tests 4 passed in 67 s; lighthouse 1,744 parts / 182 steps /
4,540 connections, PASS; build with book 95 s wall / 49 s CPU; PDF 10.2 MB; deterministic
across runs (model.json identical apart from `meta.created`).

## M1 checklist
- [x] Baseline reproduced
- [x] Repo hygiene: .gitignore, stop tracking generated `out/` and `.DS_Store`
- [x] `--profile` flag: per-stage timings + cProfile dump
- [~] Unit tests for every module (validate, steps, exporters done; (catalog, dsl, brickify, validate, steps, render, book, exporters, pipeline/CLI)
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
- [ ] §7.7 mosaic flat mode: staggered base plate layers, verified one structure
- [x] §7.8 LDraw round-trip test (exporters.parse_ldraw); LeoCAD screenshot check is M2
- [x] §7.1 PDF size: 10.2 MB -> 4.9 MB (indexed-colour images; M5 pushes further)
- [~] Performance: lighthouse build with book 49 s -> 14.4 s CPU (done); 5,000-part model < 3 min (pending)
- [ ] Golden test on the lighthouse (parts ± 5 %, PASS, deterministic); `pytest -q` < 60 s
- [ ] SKILL.md / references / SPEC / README updated; outputs visually inspected
- [ ] PR opened with Decisions section; run summary posted

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

## Noted for later milestones
- M5: draw an x-ray outline for a new part still hidden in its step's view (1-2% of parts).
- M6: evals.json eval 5 points at `examples/lighthouse/out/model.json`, which is no longer
  tracked; give that eval a committed fixture or have the eval generate it.
