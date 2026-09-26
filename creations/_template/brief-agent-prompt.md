# Prompt: build a creation brief from reference images

Paste everything below the line into a fresh agent session that has an image-generation tool.
Fill in the three bracketed fields first. The agent's output (a brief plus a reference folder)
is what you bring back to the Snapwright session for design and build.

---

You are preparing a **design brief** for a brick model (the interlocking stud-and-tube kind).
Another engineer will turn it into a buildable model with an automated pipeline. That pipeline
voxelises a design, packs real parts and checks the structure in software, then scores the
likeness by matching the model's silhouette against reference images from the best camera
angle. Your job is to hand over everything that pipeline and its designer need, so they never
have to guess.

**Creation:** [creation-a or creation-b]
**Subject, in one line:** [e.g. "a life-size human skull held like a lantern, with a light inside"]
**Source images I'm giving you:** [list the files, or "see attached"]

## 0. Ground rules (read first)

- **Rights:** the subject must be original, our own IP, a generic thing (animal, object,
  building, landscape) or public domain. If the images show a character, mascot, logo,
  vehicle design or product someone else owns, **stop and ask me** before going further.
- **No brand names:** never use a toy-brick manufacturer's brand in the name, file names or
  text. Say "brick", "brick model" or "compatible bricks".
- **Generated images are interpretations:** you may use your image-generation tool to make
  the missing reference views (section 3). Every generated image must be recorded as
  generated, with the model used and the prompt, and must not add features the source
  images don't support. Where you had to guess, say so.
- **Ask, don't invent:** if the source images conflict, or a must-have fact is missing (the
  size, what's on the back), ask me at most 3 short questions in one message. Otherwise
  choose sensible defaults and list them under "Assumptions".

## 1. Units and limits

Put numbers in these units, because the build works in them:

- **Grid:** 1 stud = 8 mm across (x and z); 1 plate = 3.2 mm high (y); 1 brick = 3 plates = 9.6 mm.
- **Detail size:** a feature must be at least **2 studs (16 mm)** wide at the chosen scale to
  read clearly. Anything smaller turns into speckle. Flag every must-read feature that would
  be smaller than that, and propose a scale or a stylisation.
- **Part count:** a solid sculpture costs about 1 part per 5-6 voxels (a voxel is 1 stud x
  1 plate). Anything over ~12 studs wide is built hollow, with a 2-stud shell and internal
  bracing, which cuts the count a lot. Give a size and a rough part-count range, so the scale
  is set with the budget in mind.
- **Flat pictured faces:** a face, sign or screen can be built sideways as a flat panel of
  studs facing outward, giving finer vertical detail. Name any candidates, with their
  approximate size in studs.
- **Colours:** use only these colour keys.
  - **Core, preferred:** white, black, red, blue, yellow, green, orange, tan, dark_tan,
    reddish_brown, light_bluish_gray, dark_bluish_gray, dark_blue, dark_red, dark_green.
  - **Limited:** lime, medium_azure, sand_green, bright_light_orange, pearl_gold (not made
    as small tiles), trans_clear, trans_yellow, trans_red.

  Map every visible colour in the reference to one of these keys. Where no key is close,
  say which you chose and why.

## 2. Measurements and proportions

From the source images, work out and state:

- The real-world size of the subject, if it's a real thing, and the **target model size**
  (height, width and depth in cm, and the same in studs and plates). Give a recommended
  scale and one alternative (smaller/cheaper or bigger/more detailed), each with an estimated
  part count.
- A **proportion table**: where the main features sit, as a fraction of total height from
  the bottom, and their widths as a fraction of total width, seen from the front and from the
  side. Example rows: "eye sockets: 0.55-0.68 of height, each 0.28 of width". The likeness
  check reports errors in height bands, so this table is what the designer will correct against.
- The **centre of mass and footprint**: what stands on what, and where the weight sits. Say
  whether it can stand on its own footprint or needs a base or stand. If it's meant to be held
  or hung (a lantern handle, a wall mount), say how and where.
- **Thin and overhanging parts:** anything thinner than 2 studs, anything that sticks out
  unsupported, and anything floating (not touching the rest). Each one needs a plan: thicken
  it, support it, join it or drop it.

## 3. Reference image set (generate what's missing)

The likeness check needs **clean orthographic-style views** of the subject:

- one subject, whole, centred, with about 10% margin;
- a plain background in one flat colour that clearly differs from every colour on the
  subject (pure white unless the subject is white; then mid grey or saturated green);
- flat, even lighting, no strong shadows;
- a long-lens or orthographic look (no wide-angle distortion);
- the same scale and the same ground line in every view.

Produce these views (source images where they exist, otherwise generated), named exactly:

| file | view | camera |
|---|---|---|
| `view_front.png` | front | azimuth 0 deg, elevation 0 |
| `view_right.png` | subject's right side | azimuth 90 |
| `view_back.png` | back | azimuth 180 |
| `view_left.png` | subject's left side | azimuth 270 |
| `view_top.png` | top, looking down | elevation 90 |
| `view_three_quarter.png` | front-right, from slightly above | azimuth 45, elevation 25 |

Then add a **detail close-up** for each must-read feature (`detail_<feature>.png`), on the
same plain background, with the feature filling most of the frame.

**Masks:** for each `view_*.png`, write `mask_<view>.png` at the same size: the subject white,
everything else black, with holes (such as gaps between arms and body) left black. Make them
from the plain background by colour threshold, then check each one by eye.

**When generating views:**

- Condition on the source images, and describe the subject exactly as it appears. Add
  nothing new: no accessories, textures or colour changes.
- Keep proportions identical across views. Check it: overlay or measure each generated view
  against the front view at matching heights (top of head, widest point, base) and
  regenerate any view that disagrees by more than ~5% of height.
- Prefer a slightly simplified, clean-edged rendering over a photoreal one: flat colour
  regions help both the silhouette and the colour check.
- Record each generation in `reference/manifest.json`: model name, prompt, seed if
  available, which source images it was conditioned on, and which parts are guesses.

If a 3-D model of the subject exists (or you can make one from the images with an
image-to-3D tool), include it as `reference/model.glb`, `.obj` or `.stl`. Record its units,
which axis is up and where it came from. The pipeline can start from a mesh.

## 4. The brief

Write `creations/[creation-x]/brief.md` with exactly these sections:

1. **Name:** original, with no brand names.
2. **What it is / why we're building it:** 2-4 sentences, plus how it will be used (display,
   handled by kids, lit from inside, hung...).
3. **Subject rights:** original, our own IP, generic or public domain, with one sentence of
   justification.
4. **Reference:** a table of every file in `reference/`: view, source or generated, notes.
5. **Target size and budget:** recommended scale (cm, studs x studs x plates), part-count
   range, and the alternative scale.
6. **Audience:** kids / family / adult / expert. **Finish:** tiled tops (smooth) or studs.
7. **Colour palette:** a table mapping each region of the subject to a colour key, noting
   near-misses (e.g. "caramel fur -> orange; nearest alternatives dark_tan, pearl_gold").
8. **Must-read features:** 3-5 of them, ranked. For each: where it is (proportion table
   reference), its size in studs at the target scale, the colour key, and how it could be
   built (solid shape, carved recess, sideways panel, painted surface).
9. **Proportion table:** from section 2.
10. **Structure:** stance and footprint, centre of mass, base or stand needed, thin parts,
    overhangs, floating parts, and each one's plan. Also anything hollow or see-through
    (for a lantern: where the light goes, and which faces are open or trans-coloured).
11. **Sideways-panel candidates:** faces or flat pictured areas, with their size in studs.
12. **Nice-to-haves:** features to include if the budget allows, and ones to leave out first.
13. **Outputs needed:** PDF instructions / 3D viewer / LDraw / BrickLink list / physical test
    build.
14. **Acceptance:**
    - software checks PASS;
    - silhouette IoU >= 0.8 against `view_front.png` (and `view_right.png` if it matters);
    - every must-read feature >= 2 studs;
    - part count within budget;
    - likeness sign-off by [name];
    - physical build by [name].
15. **Assumptions and open questions:** everything you guessed, and anything only I can answer.

## 5. Hand-back checklist

Before you finish, confirm:

- [ ] `brief.md` has all 15 sections, and no brand names appear anywhere.
- [ ] All six views plus the detail close-ups exist, with masks, and each mask was checked
      by eye.
- [ ] Generated views agree with the front view in proportions (say how you measured it).
- [ ] `manifest.json` lists every image, marking source vs generated.
- [ ] Every must-read feature is >= 2 studs at the recommended scale, or the brief says how
      it is stylised.
- [ ] Every thin, overhanging or floating part has a plan.

Finish with a short summary for me: the recommended scale and part range, the must-read
features, the three biggest risks for buildability or likeness, and any questions.
