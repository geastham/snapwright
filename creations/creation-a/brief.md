# Creation brief: Lakeside Sail Tower (creation A)

Adapted from the brief prepared on 2026-09-26 with two reference photos. Corrections are
marked **[changed]**.

## 1. Name
Lakeside Sail Tower (a working title, and generic on purpose: no owner, tenant or developer
names).

## 2. What it is / why we're building it
A display model of a modern office tower with a curved, sail-like west face covered in
vertical fins, and a south face that steps back floor by floor into terraces. It's a
shelf/desk display piece for architecture fans, static and lit from outside.

## 3. Subject rights **[changed]**
This is a real, recognisable landmark (a recent tower on a lakefront downtown), not a generic
building. Snapwright's guidance lists real landmarks as good subjects, so building and
publishing our own model of it is fine; the model carries no owner, tenant or architect names.
Recent buildings can have architectural-design protection, so check with an IP lawyer before
selling kits or instructions.

## 4. Reference **[changed]**
Only two photos arrived with the brief. The generated views and close-ups it lists were not
included and are still needed (see 15).

| file (reference/, git-ignored) | view | source | notes |
|---|---|---|---|
| photo_lake_south.png | from the south across the lake, ground level | photo | west (sail) face seen obliquely on the left; terraced south face; trees hide the base |
| photo_aerial.jpg | from the west, elevated | photo | the sail face almost head-on; south terraces stepping down on the right; base cut off |
| view_front.jpg + mask_view_front.png | south elevation | generated | used for the likeness score (IoU 0.92) |
| view_side.jpg + mask_view_side.png | west elevation (probably) | generated | its terraces are drawn on the north side: an artefact, not modelled |
| context_lakefront.jpg | lakefront from the south | generated | diorama layout: tree rows, curved shore, bridge across the inlet |
| view_back/right/top/three_quarter, detail_* | | generated | not supplied; not needed so far |

## 5. Target size and budget **[changed]**
- **Measured from the photos:** width about 0.55 x height; depth about 0.45 x height.
- **First design:** 36.5 cm tall (6-plate podium + 108 plates); tower footprint 25 x 20
  studs on a 29 x 24 podium; hollow with a 2-stud shell.
- **Result:** 1,948 parts, about 2.0 kg, PASS.
- **Versus the brief:** 1,948 is above the brief's 1,200-1,600. A version about 30 cm tall
  (21 x 16 studs) should land around 1,300.

## 6. Audience and finish
Adult / expert. Tiled tops (smooth).

## 7. Colour palette
| region | key |
|---|---|
| glass and body | light_bluish_gray |
| fins on the sail face | white stripes, 1 stud wide, every other stud |
| terrace edges on the south face | white band on each step |
| podium | dark_bluish_gray |
| trees (optional strip) | green, orange, yellow |

## 8. Must-read features
1. **The sail:** the west face's edge sweeps east near the top, to a peak (from the lake,
   flat up to about 40% of the height, then curving in).
2. **The terraces:** the south face steps back at every floor (every brick), from full depth
   at the podium to about a quarter of the depth at the top.
3. **The fins:** vertical white stripes on the sail face.
4. **The peak:** it should end in a point, higher than the terrace roof. It currently ends
   in a small flat block.

## 9. Proportion table (from the lake view, fraction of tower height above the podium)
| height | west edge (fraction of width, receding east) | east edge | depth left |
|---|---|---|---|
| 0.0 | 0.00 | 1.00 | 1.00 |
| 0.4 | 0.01 | 0.86 | 0.70 |
| 0.6 | 0.06 | 0.78 | 0.55 |
| 0.8 | 0.20 | 0.71 | 0.40 |
| 1.0 | 0.48 | 0.64 | 0.25 |

## 10. Structure **[changed]**
- It stands on its own podium; the centre of mass is 80 mm inside the footprint.
- It's hollow with internal brace columns. There are no hinges, Technic parts or pins: the
  build uses plain bricks, plates, tiles, slopes and round parts. A curved face can't be a
  sideways panel (panels are flat), so the fins are coloured stripes on the voxel surface.
- **Weak points** (8 spots held by 1-3 studs, 1-5 g each): mostly the 1-stud fin stripes and
  the podium corner. To fix in the next pass.

## 11. Sideways-panel candidates **[changed]**
None for now: the flat faces carry no picture, and the curved sail can't be a panel.

## 12. Nice-to-haves
A strip of small trees along the podium edge (green / orange / yellow). Trans-clear glass is
left out, since the opaque grey reads better at this scale.

## 13. Outputs needed
PDF instructions, 3D viewer, LDraw, BrickLink list, physical test build.

## 14. Acceptance
- Software checks PASS, with no weak point under 2 studs.
- Silhouette IoU >= 0.8 against a clean front (south) view, and against the aerial (west)
  view if we get a mask for it.
- Every must-read feature is at least 2 studs.
- The part count is inside the budget we agree.
- Likeness sign-off: Project Lead. Physical build: Lead Builder.

## Decisions (2026-09-26)
- Budget: over 2,000 parts is fine. Diorama: yes (lake, a shore with autumn trees, a bridge).
- Build so far: 3,334 parts, 38.4 x 38.4 x 41 cm, 3.5 kg, PASS. Weak points are all held
  by >= 2 studs. South-elevation IoU is 0.92 for the tower alone
  (`SAIL_TOWER_ONLY=1 sw.py compare ...`).

## 15. Open questions
1. Please bring the generated reference views and masks, especially clean south and west
   elevations; the likeness score needs them.
2. Budget: keep about 36 cm / ~1,950 parts, or go to about 30 cm / ~1,300?
3. Diorama: the building on its podium only (recommended), a tree strip, or the lake and
   bridge?
