# Tasks

Current milestone: **M1 Harden the core** (branch `m1-hardening`). Spec: SPEC.md §5 M1, §7.

Baseline (v0.1, 2026-09-25): tests 4 passed in 67 s; lighthouse 1,744 parts / 182 steps /
4,540 connections, PASS; build with book 95 s wall / 49 s CPU; PDF 10.2 MB; deterministic
across runs (model.json identical apart from `meta.created`).

## M1 checklist
- [x] Baseline reproduced
- [x] Repo hygiene: .gitignore, stop tracking generated `out/` and `.DS_Store`
- [x] `--profile` flag: per-stage timings + cProfile dump
- [ ] Unit tests for every module (catalog, dsl, brickify, validate, steps, render, book, exporters, pipeline/CLI)
- [x] Regression fixtures in `tests/fixtures/` (circle-corner overhang conflict, ...)
- [~] Property tests on random blobby models (generator + oracles done; pytest wrapper pending) (spheres, tubes, overhangs, 1-stud speckles, stair-step circles):
      no collisions; PASS implies every part reachable from ground; steps feasible in order
- [x] Honest change counts: recoloured/trimmed computed from design vs built grid
- [x] Transparent parts: cells behind/inside trans colours keep their colour
- [x] Step feasibility includes insertion direction (from above / pressed from below)
- [ ] §7.3 spatial step clustering (finish one region before the next)
- [ ] §7.4 visibility-scored view choice (render-mask based)
- [ ] §7.5 min-cut necks on the connection graph
- [ ] §7.7 mosaic flat mode: staggered base plate layers, verified one structure
- [ ] §7.8 LDraw round-trip test
- [ ] §7.1 PDF size (lighthouse PDF well under 5 MB)
- [ ] Performance: lighthouse build (6 seeds, with book) < 30 s; 5,000-part model < 3 min
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
- Open: blobby seeds 180, 240, 266, 299 FAIL honestly after these fixes; investigate.

## Noted for later milestones
- M6: evals.json eval 5 points at `examples/lighthouse/out/model.json`, which is no longer
  tracked; give that eval a committed fixture or have the eval generate it.
