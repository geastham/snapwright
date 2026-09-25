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
Prefer hollow shells (`inner=`/`inner_r=`) for anything wider than ~12 studs, capped at the
top, to save parts. Use only catalog colours (`assets/catalog.json`); prefer `core` tier.

```bash
python <skill>/scripts/sw.py preview design.py --out out/preview
```
Look at all four `preview_view*.png` next to the reference. Fix proportions and colours
before building. Iterate 2-4 times; this is where likeness comes from.

## 3. Build and check

```bash
python <skill>/scripts/sw.py build design.py --out out --audience adult --seeds 8
```
Exit code 0 = checks passed and the book was written; 2 = failures (book skipped unless
`--no-strict`). Read the log. For every failure or note, apply the matching fix from
`references/geometry-and-checks.md` (usually a design change: thicken a neck, add support
under an overhang, widen a 1-stud feature, simplify a colour speckle), then rebuild. Never
present a model with floating parts, multiple structures or a centre of mass under 3 mm
inside the footprint as buildable.

Report honestly: surface cells recoloured by the repair loop, single-stud joints, thin
necks, and part-colour combos not verified against a real catalog. Everything is "checked in
software"; nobody has built it until someone builds it.

## 4. Outputs (all in `out/`)

- `<slug>-instructions.pdf`: cover, parts inventory, numbered steps with callouts, finale
- `<slug>-viewer.html`: self-contained 3D viewer with build playback, parts list, checks
- `<slug>.ldr`: LDraw with STEP markers (opens in LeoCAD, Studio, Mecabricks)
- `<slug>-bricklink.xml`, `<slug>-rebrickable.csv`, `<slug>-parts.csv`
- `model.json`: canonical model (schema in `references/geometry-and-checks.md`)

Share the PDF and the viewer first. Give the headline numbers (parts, height, steps, lots),
anything the user should know before buying parts, and one concrete next improvement.

## 5. Photos to mosaics

For "make a mosaic of this photo": `model = Model(48, 48, 2)` then
`model.mosaic("photo.jpg", mode="flat")`, or `mode="upright"` with a height in plates of
roughly width x 2.5 for correct aspect. Offer a limited palette for a graphic look.

## Files

- `scripts/sw.py`: CLI (preview, build, viewer, book, sync-catalog)
- `scripts/snapwright/`: dsl, brickify, validate, steps, render, book, exporters, pipeline
- `assets/catalog.json`: parts and colours; `assets/viewer_template.html`
- `references/design-dsl.md`: every DSL call with examples. Read before writing a design.
- `references/geometry-and-checks.md`: units, connection rules, each check and how to fix it
- `references/book-style.md`: book conventions and what to avoid imitating
- `references/ip-and-naming.md`: subject choice, trademarks, disclaimers, selling designs
