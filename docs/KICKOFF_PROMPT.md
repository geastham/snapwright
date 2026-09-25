# Kickoff prompt for the coding agent

Paste everything below the line into Claude Code (or your coding agent) from the repo root.

---

You're taking over **Snapwright**, an open-source Claude skill that turns a photo, sketch or description into a buildable interlocking-brick model plus everything needed to build it: a verified part layout, a step-by-step instruction book (PDF), an interactive 3D build viewer, an LDraw file, and BrickLink/Rebrickable parts lists. Open Conjecture will publish it for others to use, and we'll use it for two of our own creations. Your job is to take the working v0.1 scaffold in this repo to a v1.0 we can publish, milestone by milestone.

## Read first, in this order
1. `CLAUDE.md`: repo rules. Follow them throughout.
2. `SPEC.md`: product, pipeline, milestones M1-M7 with acceptance criteria, and the known-issues backlog (§7).
3. `skill/snapwright/SKILL.md` and `skill/snapwright/references/*`: how the skill is used at runtime by Claude in a sandbox. Anything you build must keep working there.
4. The code in `skill/snapwright/scripts/snapwright/`, then `tests/` and `examples/lighthouse/design.py`.

Then run `make setup && make test && make example` and confirm the baseline: tests green, lighthouse PASS at about 1,744 parts / 182 steps. Tell me if the baseline doesn't reproduce before changing anything.

## What matters most
- **Buildability is the product.** A model is only done if every part connects to one grounded structure, nothing collides, it balances, and the steps can be followed in order. Never weaken a check to make something pass; fix the geometry or the algorithm.
- **Honesty about automatic changes.** Every recolour, trim or added support is counted in stats and surfaced in the CLI log, the book finale and the viewer. "Checked in software" is not "built".
- **Runs in the claude.ai sandbox.** Runtime dependencies stay numpy, scipy, pillow, reportlab. No network at runtime except `sync-catalog`. No GPU. Keep the whole skill folder under ~2 MB.
- **Deterministic core.** The same design.py + seed gives the same model.json. Every output must be regenerable from model.json alone.
- **IP hygiene.** No toy-brick manufacturer brand in any name, title, file name, UI string or logo. Don't imitate official instruction-book styling. Follow `NOTICE.md` and `references/ip-and-naming.md`. Do not copy code from other brick-model demos; implement from first principles.

## How to work
- One milestone at a time, M1 → M7, each on its own branch (`m1-hardening`, `m2-parts-v2`, …) with small, focused commits. Open a PR per milestone if the remote is set up; otherwise merge to `main` after I confirm.
- Keep a `TASKS.md` at the repo root with the current milestone's checklist and tick items as you go, so progress survives context resets.
- Tests first for anything touching geometry: write a failing test that reproduces the issue, then fix it. Add each hard case you hit (like the circle-corner overhang conflict already covered) as a regression fixture in `tests/fixtures/`.
- After every meaningful change run `make test` and `make example`. A lighthouse that stops passing, or whose part count moves more than 5% without an explanation, is a regression.
- Look at your outputs, not just the numbers. Render PDF pages to PNG (`pdftoppm -r 50 -png`) and inspect them; open the viewer HTML in a headless browser if available and screenshot it. Fix what looks wrong.
- When a design decision has real trade-offs (part count vs fidelity, a schema change, a new dependency), make the reasonable call, note it in the PR description under "Decisions", and keep going. Only stop to ask when a choice is expensive to reverse.

## Milestone notes beyond SPEC.md
- **M1 hardening:** add property tests on randomly generated blobby models (spheres, tubes, overhangs, 1-stud colour speckles, stair-step circles). Clear the §7 backlog items that are pure engineering (PDF size, step clustering, visibility-scored view choice, min-cut necks, LDraw round-trip test). Add a `--profile` flag and get the lighthouse build with book under 30 s.
- **M2 parts v2:** slopes and round parts need connection-point metadata in the catalog (which faces have studs/tubes). Extend the renderer to draw them. Hollowing must add internal bracing so hollow shells still pass the neck and balance checks.
- **M3 SNOT subassemblies:** model sideways panels as their own grids with a transform, attached through side-stud parts. Checks run per subassembly plus the attach anchors. The book shows each subassembly in an inset box before its attach step.
- **M4 likeness loop:** `sw.py compare design.py --ref photo.jpg` (silhouette IoU plus side-by-side image). Update SKILL.md so Claude iterates until IoU ≥ 0.8. Add `Model.from_mesh` for OBJ/STL/GLB with numpy-only voxelisation.
- **M5 polish:** bag splitting (~150 parts per bag with a "parts for this bag" page), sub-steps for large levels, viewer step mode with new-part highlight, PDF under 5 MB for 2,000 parts.
- **M6 publish:** run the skill-creator eval loop on `evals/evals.json` (add real test images you create yourself, no third-party photos), tune the SKILL.md description for triggering, write CONTRIBUTING.md, add a README gallery with cover images and viewer links, and produce `dist/snapwright.skill` via `make package`.
- **M7 our creations:** stop and ask me for the briefs for `creations/creation-a` and `creations/creation-b` (fill in `brief.md` with me), then design, iterate on previews against the references, build to PASS, and produce the book, viewer and BOM for each. Log every packer weakness they expose as an issue and fix the general cause, not just the instance.

## Definition of done for each milestone
All acceptance criteria in SPEC.md for that milestone are met; `make test` is green; `make example` passes; the new or changed outputs have been visually inspected; SKILL.md and references are updated for any user-visible change; `TASKS.md` is updated; and you've posted a short run summary.

## Run summary format (end of every session or milestone)
- **Done:** what changed, with the key numbers (parts, steps, pass/fail, timings, PDF size).
- **Decisions:** calls you made and why.
- **Found:** bugs or limits discovered, and where they're tracked.
- **Blocked on me:** only things you truly need from me (briefs, API keys, naming or licensing calls).

Start now with the baseline check, then M1.
