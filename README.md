# Snapwright

Design buildable brick models with Claude: photo, sketch or idea in; verified parts layout,
instruction book, 3D build viewer and parts lists out.

- **Design**: Claude writes a short design file in a voxel DSL and iterates on previews.
- **Brickify**: bricks, plates and tiles with staggered joints, anchored overhangs and a repair loop;
  slopes, inverted slopes and round parts where the surface tapers or curves; optional hollowing
  with internal bracing; an automatic base for models that would tip.
- **Check**: one structure, nothing floating, no collisions, balance, weak joints, colour availability.
- **Document**: step-by-step PDF, three.js viewer with build playback, LDraw, BrickLink XML, Rebrickable CSV.

Example: `examples/lighthouse` → 1,761 parts, 32.6 cm, 185 steps, all checks pass (about 20 s
with the book on a laptop). `make bench` builds a 5,000-part keep in under 2 minutes.

```bash
make setup
make test           # unit, regression-fixture, property and golden tests (~40 s)
make example        # builds examples/lighthouse/out/
python skill/snapwright/scripts/sw.py preview my_design.py --out out/preview
python skill/snapwright/scripts/sw.py build   my_design.py --out out --audience family
```

Install as a Claude skill: `make package` → upload `dist/snapwright.skill`.

Layout: `skill/snapwright/` (the skill), `examples/`, `creations/` (our own builds),
`evals/`, `tests/`, `docs/`. Roadmap and acceptance criteria: `SPEC.md`.

Unofficial and independent; see NOTICE.md. Checked in software only: build before you trust it.
