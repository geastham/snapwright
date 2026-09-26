---
name: snapwright
description: Design buildable brick models (the interlocking stud-and-tube kind) from a photo, sketch or description, verify in software that every part really connects, and produce a step-by-step instruction book (PDF), an interactive 3D build viewer, LDraw files and BrickLink/Rebrickable parts lists. Use this skill whenever someone wants to turn an image, character, object, building, pet, logo of their own, or idea into a brick build, brick sculpture or brick mosaic; asks for building instructions, a parts list or a BOM for a brick model; mentions MOCs, BrickLink, Rebrickable, LDraw or Studio files; or wants a buildable toy-brick version of anything, even if they don't say "skill" or name a file format.
---

# Snapwright

Turn an idea into a brick model someone can actually build: shape, real parts, checks, steps, book.

The pipeline is deterministic Python in `scripts/`. Your job is the part code can't do: read
the reference, choose scale and palette, write the design file, look at previews, fix what
looks wrong, and interpret the checks.

## 0. Before designing: subject and IP

Build original subjects, the user's own creations, generic things (animals, buildings,
vehicles, objects, landscapes), real places, or public-domain works. If asked to recreate a
known character, mascot, logo or commercial set someone else owns, say so in one sentence and
offer an original design in a similar spirit instead. Never put a toy-brick manufacturer's
brand name in a model title, file name or book. Read `references/ip-and-naming.md` if the
user wants to sell or publish designs.

## 1. Intake (ask at most one short question; otherwise pick sensible defaults and say so)

Settle: subject and reference, target size (cm) or part budget, audience (kids / family /
adult / expert, which sets parts per step), finish (smooth tiled tops or studs), and outputs
wanted. Defaults: 20-35 cm tall display model, adult, tiled finish, all outputs.
Rules of thumb: 1 stud = 8 mm, 1 plate = 3.2 mm, 1 brick = 3 plates. Solid sculptures cost
roughly 1 part per 5-6 voxels; hollow shells far less.

## 2. Design file

Write `design.py` with the DSL in `references/design-dsl.md`. Block out big masses first,
then detail, then paint colours. Keep it an honest likeness at the chosen resolution: pick a
scale where the features that make the subject recognisable are at least 2 studs wide.
For solid masses wider than ~12 studs, finish the design with `model.hollow()` (keeps a
2-stud shell, 3-plate caps and internal bracing columns; saves plastic and weight) or build
shells directly with `inner=`/`inner_r=`. Use only catalog colours (`assets/catalog.json`);
prefer `core` tier. Tapers, domes and flares don't need special handling: the build smooths
them with slopes, inverted slopes and round parts automatically.

```bash
python <skill>/scripts/sw.py preview design.py --out out/preview
```
Look at all four `preview_view*.png` next to the reference. Fix proportions and colours
before building. Iterate 2-4 times; this is where likeness comes from. If preview prints a
`warning: ... voxels ... don't touch the rest of the model or the ground`, join that part
to the model now: nothing can hold it up and the build will fail.

## 3. Build and check

```bash
python <skill>/scripts/sw.py build design.py --out out --audience adult --seeds 8
```
Exit code 0 = checks passed and the book was written; 2 = failures (book skipped unless
`--no-strict`). By default the build shapes visible tapers and curves with slopes and round
parts (`--no-shapes` for bricks, plates and tiles only) and stands a model that would tip
over on a 2-plate base (`--base off` to keep the failure and fix the design yourself). Read the `summary` block at the end of the log: it is exactly what the book
finale and the viewer will say. For every FAIL or note, apply the matching fix from
`references/geometry-and-checks.md` (usually a design change: join a floating part, add
support under an overhang, thicken a weak point, widen a 1-stud feature, simplify a colour
speckle), then rebuild. Never present a model with floating parts, multiple structures,
large trims or a centre of mass under 3 mm inside the footprint as buildable.

Report honestly, from the summary: every auto-repair (cells recoloured, overhang cells
trimmed, tops that got studded plates instead of tiles, an added base), the surface shaping
(slopes and rounds change the silhouette slightly), weak points (pieces held by 3 studs or
fewer), single-stud joints, and part-colour combos not verified against a real catalog.
Everything is "checked in software"; nobody has built it until someone builds it.
Builds are deterministic: the same design file and seeds give the same model. Add
`--profile` to see where time goes on big models (a 5,000-part model takes ~2 minutes).

## 4. Outputs (all in `out/`)

- `<slug>-instructions.pdf`: cover, parts inventory, numbered steps with callouts, finale
- `<slug>-viewer.html`: self-contained 3D viewer with build playback, parts list, checks
  (open with `?step=N` to start paused at step N)
- `<slug>.ldr`: LDraw with STEP markers (opens in LeoCAD, Studio, Mecabricks)
- `<slug>-bricklink.xml`, `<slug>-rebrickable.csv`, `<slug>-parts.csv`
- `model.json`: canonical model (schema in `references/geometry-and-checks.md`)

Share the PDF and the viewer first. Give the headline numbers (parts, height, steps, lots),
anything the user should know before buying parts, and one concrete next improvement.

## 5. Photos to mosaics

For "make a mosaic of this photo": `model = Model(48, 48, 3)` then
`model.mosaic("photo.jpg", mode="flat")`: two staggered base plate layers hold it together
and the picture is a layer of tiles on top (the grid grows if it is too short). Or
`mode="upright"` with a height in plates of roughly width x 2.5 for correct aspect. Offer a
limited palette for a graphic look.

## Files

- `scripts/sw.py`: CLI (preview, build, viewer, book, sync-catalog)
- `scripts/snapwright/`: dsl, brickify, validate, steps, render, book, exporters, pipeline
- `assets/catalog.json`: parts and colours; `assets/viewer_template.html`
- `references/design-dsl.md`: every DSL call with examples. Read before writing a design.
- `references/geometry-and-checks.md`: units, connection rules, repairs, each check and its fix,
  model.json schema
- `references/book-style.md`: book conventions and what to avoid imitating
- `references/ip-and-naming.md`: subject choice, trademarks, disclaimers, selling designs
