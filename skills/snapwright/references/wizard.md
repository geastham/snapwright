# The creation wizard

A guided path from "I want to make a brick X" to a model someone can build. Use it whenever
the user starts a new creation, asks "how do I start?", or brings a pile of reference
pictures. For a one-line request ("a small lighthouse") skip straight to stage 4 with sensible
defaults; the wizard is for when getting the likeness right matters.

The rhythm: **every stage ends by showing the user something concrete** (a picture, the
numbers) and asking **at most one question**. Say which stage you're on ("Step 3 of 7:
references") so they know where they are. Keep the user's words for things (their name for
the model, their dog's name).

## 1. Kickoff: the three questions

Ask these in one message, each with a default so "just go" works:

1. **What is it, and whose is it?** One sentence. If it's someone else's character, logo or
   set, say so kindly and offer an original in the same spirit (see ip-and-naming.md). Real
   places and buildings are fine.
2. **How big, or how many pieces?** Default: 25-35 cm tall display model; for kids, under 400
   pieces.
3. **Who builds it?** kids / family / adult / expert (sets the step size). Default: adult.

Also offer: a standalone model or a small **diorama** (ground, water, trees)?

## 2. Start the project

```bash
python <skill>/scripts/sw.py new "Biscuit the Dog" --dir . --subject "A cartoon dog ..."
```
It makes `biscuit-the-dog/` with `brief.md`, `reference/` and `design.py`. Tell the user to
drop their pictures into `reference/` (or attach them; you copy them in). Photos from several
sides help most; one good photo is enough to start.

## 3. References: what we have, what we need

```bash
python <skill>/scripts/sw.py refs biscuit-the-dog
```
It finds each subject's outline, makes masks for clean views, suggests brick colours, lists
the views still missing, and prints **one ready-to-paste image-generation prompt per missing
view** (a straight-on front and side are the ones that matter). Show the user
`reference/contact_sheet.png` and the missing-view list.

- **If you have an image-generation tool**, generate the missing views yourself from the
  printed prompts, attaching the user's photos, and save them as `reference/view_front.png`
  and so on. Otherwise give the user the prompts to paste into their image tool, and wait
  for the images.
- Generated views are *interpretations*: check each against the photos (same proportions, no
  invented features) before relying on it, and note in the brief which views are generated.
- A busy photo background is fine for looking at, but not for the likeness score: the score
  needs a clean view (plain background) or a mask.

Run `refs` again after new images arrive. Checkpoint: "These are the references I'll design
from. Anything wrong or missing?"

## 4. The brief

Fill in `brief.md` with the user's answers and what the references show:
- **Size in studs and plates:** 1 stud = 8 mm, 1 plate = 3.2 mm, 1 brick = 3 plates.
- **3-5 must-read features:** each at least 2 studs wide at that size. If one isn't,
  propose a bigger model or a bolder version.
- **Colours:** start from `refs`' suggestions and prefer core colours.
- **A proportion table:** where the features sit, as fractions of the height.
- **Structure:** overhangs, thin parts, and a base if it would tip.

Estimate the part count: roughly 1 part per 5-6 voxels solid, far fewer if hollow.
Checkpoint: the scale and the rough part count, the one decision that's expensive to change
later.

## 5. Block-out and likeness

Write `design.py` (design-dsl.md): big masses first, then the features, then colours. Then:
```bash
python <skill>/scripts/sw.py preview biscuit-the-dog/design.py --out biscuit-the-dog/out/preview
python <skill>/scripts/sw.py compare biscuit-the-dog/design.py \
    --ref biscuit-the-dog/reference/view_front.png --out biscuit-the-dog/out/compare
```
Iterate on your own while the hints are clear, usually 2-5 rounds, until the outline overlap
(IoU) is at least 0.8 and the must-read features read. Then show the user the preview and
`compare.png` side by side. Checkpoint: "Does this look like Biscuit? Anything to change?"
User feedback beats the score: a recognisable ear matters more than 2% of IoU.

## 6. Build and check

```bash
python <skill>/scripts/sw.py build biscuit-the-dog/design.py --out biscuit-the-dog/out --audience family
```
Fix every FAIL and any weak point you can in the design (geometry-and-checks.md), then
rebuild. Show a render of the built model and the summary: parts, size, weight, steps, bags,
and every automatic repair. Checkpoint only if a fix changes the look ("the tail needs to be
thicker to hold on: OK?").

## 7. Hand over

The outputs, in `out/`:
- **`<slug>-instructions.pdf`:** the instruction book, ready to print. The cover,
  a parts list, bags, then the steps.
- **`<slug>-viewer.html`:** the 3D viewer. It opens in any browser, offline too.
- **`<slug>-bricklink.xml`:** the order list. On BrickLink: Want -> Upload, paste it,
  then *Buy All* to find shops that have everything.
- **`<slug>-rebrickable.csv`:** for Rebrickable (import as a part list; compare with
  what you own).
- **`<slug>-parts.csv`:** a readable parts list, with a BrickLink link per part.
- **`<slug>.ldr`:** for Studio, LeoCAD and Mecabricks.
- **`sw.py video out/model.json --out out/build.mp4`:** the build video, on request
  (great for sharing).

Give the headline numbers, anything to know before buying parts, and one idea for a next
version.

## 8. After a real build (optional)

If the user builds it and something doesn't click, fix the design and rebuild, and tell
them what changed. That feedback is gold for the packer too.
