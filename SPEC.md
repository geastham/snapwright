# Snapwright: end-to-end spec (v0.1 scaffold → v1.0 public skill)

## 1. Product
A publishable Claude skill that turns a photo, sketch or description into a buildable brick
model and everything needed to build it: verified part layout, instruction book (PDF),
interactive 3D build viewer, LDraw file, and BrickLink / Rebrickable parts lists.
Works in claude.ai (sandboxed Python, no GPU, no network) and in Claude Code.

Audiences: (1) public skill users, (2) Open Conjecture's own two creations
(`creations/creation-a`, `creations/creation-b`), which double as the hardest acceptance tests.

## 2. Non-goals (v1)
Physics simulation of clutch force; motors/Technic-style mechanisms; minifigure-scale
characters; selling kits; any manufacturer's brand in names or visual style.

## 3. Pipeline
```
reference (photo/sketch/text)
  → design.py (Claude writes; DSL)            scripts/snapwright/dsl.py
  → preview renders, 4 views (Claude iterates) render.py
  → voxels (x, z studs; y plates)
  → brickify: parts + repair loop, N seeds     brickify.py
  → validate: connections, floating, etc.      validate.py
  → plan steps + camera views                   steps.py
  → exports: LDraw, BrickLink XML, CSVs         exporters.py
  → viewer.html (three.js)                      assets/viewer_template.html
  → instructions.pdf                            book.py
```
Canonical artifact: `model.json` (schema `snapwright.model/0.2`; 0.1 still read; see
`skill/snapwright/references/geometry-and-checks.md`). Every downstream output must be
regenerable from `model.json` alone.

## 4. Status of the v0.1 scaffold (what exists and runs)
- DSL: box, cylinder/tube, cone/frustum, ellipsoid, sphere, where, paint, carve, mirror_x, mosaic
- Packer: bricks/plates/tiles, exterior-visibility wildcards, plate margins, overhang anchoring
  (most-constrained first + lookahead), 3-stage repair loop, seed search
- Validator: collisions, connections, links, structures, floating, weak parts, necks, centre of
  mass vs footprint hull, mass, dims, part-colour availability
- Steps: bottom-up, feasibility (every part attaches to something placed), overhang steps,
  audience-based step size, per-level camera with hysteresis
- Renderer: Pillow isometric, part-boundary outlines, studs, highlight, 4 views
- Book: cover, inventory, 4 steps/page with callouts and turn markers, finale with checks
- Exports: LDraw (.ldr, STEP), BrickLink XML, Rebrickable CSV, CSV
- Viewer: instanced three.js build playback, scrubber, checks + parts panels, downloads
- Example: `examples/lighthouse` → 1,744 parts, 32.6 cm, 182 steps, PASS (v0.1)
- After M1 (v0.2): lighthouse 1,760 parts, 184 steps, PASS, ~19 s CPU with book, PDF 4.9 MB;
  `examples/keep` 5,068 parts in ~106 s; 85 tests (unit, fixtures, property, golden) in ~40 s

## 5. Milestones and acceptance criteria

### M1 Harden the core (tests first)
- Unit tests for every module; golden test on the lighthouse (parts ± 5%, PASS, deterministic
  for a fixed seed). `pytest -q` green, < 60 s.
- Property tests on random blobby models: never collisions; any PASS model has every part
  reachable from the ground; steps are feasible in order.
- Fix known issues in §7.
- Performance: lighthouse build (6 seeds, with book) < 30 s; 5,000-part model < 3 min.

### M2 Parts vocabulary v2
- Slopes (30°/45°, inverted) for tapered and curved silhouettes, driven by a surface-normal
  pass on the voxel grid; round plates/tiles 1x1 and 2x2 for curves; wedge plates optional.
- Hollowing: `Model.hollow(wall=2)` with automatic internal bracing columns every N studs.
- Base plates: optional stand/base generation to fix balance failures automatically.
- Catalog: all new parts with dims, connection points and LDraw origins; LDraw export verified
  by loading in LeoCAD (manual check documented with screenshots).

### M3 Sideways subassemblies (SNOT)
- Model faces or panels built sideways (like a face or chest plate) as separate subassembly
  grids, attached via bricks with studs on the side (87087, 11211, 30414).
- `steps` supports `kind: subassembly` + `attach`; book shows the subassembly in a boxed inset
  and an attach step; viewer animates the attach.
- Validator checks each subassembly on its own plus its anchor studs.

### M4 Reference-to-design quality loop
- `sw.py compare design.py --ref photo.jpg`: renders the voxel model from the camera angle that
  best matches the reference and writes a side-by-side plus a silhouette IoU score.
- SKILL.md guidance to iterate until silhouette IoU >= 0.8 and key features are >= 2 studs.
- `Model.from_mesh(path)` (OBJ/STL/GLB voxeliser, numpy only) for users who have 3D models.

### M5 Book and viewer polish
- Book: sub-step numbering for big levels, parts-to-find-first pages per bag (bags of ~150
  parts), page-level progress bar, A4/Letter, PDF < 5 MB for 2,000 parts (JPEG/indexed images).
- Viewer: step-by-step mode (next/prev), highlight new parts, exploded view of subassemblies,
  record-to-video, published-artifact safe (no external fetches beyond CDN three.js).
- Accessibility: colour names alongside swatches, never colour alone.

### M6 Publishable skill
- `skill/snapwright` is self-contained, < 2 MB, installs via `.skill` package.
- `evals/evals.json` (≥ 6 prompts incl. mosaic, kids model, photo sculpture, IP decline) run
  with skill-creator; description tuned for triggering.
- README with gallery (cover PNGs + viewer links), NOTICE, LICENSE, CONTRIBUTING.
- Rebrickable-verified catalog committed; `sync-catalog` documented.

### M7 Our two creations
- `creations/creation-a` and `creation-b` each: brief.md filled, design.py, PASS build,
  book, viewer, BOM; physical test build notes and fixes fed back into the packer.

## 6. Design principles
- Deterministic core, Claude on top: all geometry decisions reproducible from design.py + seed.
- Honest checks: every automatic change (recolour, trim, added support) is counted and shown.
- Everything regenerable from model.json; no hidden state.
- Pure Python + numpy/scipy/Pillow/reportlab so it runs in the claude.ai sandbox.
- Own visual identity; no manufacturer names or trade dress.

## 7. Known issues / backlog from v0.1
1. (M1: 10.2 → 4.9 MB via indexed-colour images; M5 continues) Instruction PDF is ~10 MB for 1.7k parts: switch step images to JPEG-in-PDF or smaller
   indexed PNGs; cache repeated renders.
2. Parts count is high for solid shapes (no hollowing yet) and tall tapers become plate stacks
   (no slopes yet).
3. (Done in M1: region-grown steps) Step planner orders within a level by colour then row; should cluster spatially (k-means or
   sweep) and prefer finishing one region before starting another.
4. (Done in M1: id-buffer visibility per level, per-step turn when parts hide) View choice is per level by centroid only; should score actual visibility of new parts in
   each candidate view (render-mask based) and pick the best.
5. (Done in M1: max-flow min-cut per load) `necks` metric is heuristic; replace with per-level min-cut on the connection graph.
6. Catalog availability is tiered, not verified, until `sync-catalog` runs with an API key.
7. (Done in M1: 2 staggered base layers, tested) Mosaic: flat mode's base layer relies on colour tiles to bridge base plates; add an explicit
   staggered base plate layer (or recommend a baseplate) and verify one structure.
8. (M1: export/re-import round-trip test; LeoCAD screenshot check still in M2) LDraw rotation/origin conventions need a round-trip test in LeoCAD.
9. Viewer has no step-by-step mode or new-part highlight yet.
10. No CLI `compare` / reference scoring yet (M4).
