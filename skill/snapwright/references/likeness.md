# Likeness: compare a design with a reference

```bash
python <skill>/scripts/sw.py compare design.py --ref photo.jpg [--mask mask.png] [--out DIR]
```

## What it does
1. Cuts the subject out of the reference: the alpha channel of a cut-out PNG, else `--mask`
   (white = subject), else a backdrop colour estimated from the picture's border. The last
   works for a subject on a plain backdrop; it warns when the border is busy or the subject
   runs off the edge. Then pass `--mask`, or crop the photo tighter onto a plain area.
2. Renders the model (sideways panels included) from a grid of camera angles, compares
   silhouettes scaled to the same height (so size doesn't matter, proportions do), refines
   around the best, and breaks front/back ties by colour.
3. Reports silhouette IoU (0-1), the best view, colour agreement, hints, and writes
   `compare.png` + `compare.json`.

## Reading the result
- IoU >= 0.8: the outline is right; spend remaining effort on colours and details.
- 0.6-0.8: proportions are off; the hints say where. "overall the model is 15% wider for its
  height": change the overall width/height ratio. "30-40% down from the top: 25% too
  narrow": that height band (counting from the top of the subject) needs to be wider.
- < 0.6: wrong pose or viewpoint, or the reference cut-out failed; check `compare.png`.
- Colour agreement is low when shading darkens the photo (grey vs dark grey) or when the
  palette is wrong. The colour hint names the biggest confusion; use judgement.
- The best view is a hint about pose: if it isn't the angle the photo was taken from, the
  model's pose or proportions differ in a way the silhouette can't explain.

## Designing for recognisable detail
- Features that make the subject recognisable (eyes, windows, markings) at least 2 studs;
  `preview` and `compare` list visible colour details only 1 stud across.
- Faces and signs with fine detail: build them as sideways panels (`model.panel`), where a
  pixel is a stud tall instead of a plate.

## From a 3-D model
`Model.from_mesh(path, height_cm=20, width_cm=None, up="y", colors=None,
default_color="light_bluish_gray", fill=True)` reads .obj (+ .mtl colours), .stl (ascii or
binary), .glb / .gltf (node transforms, base colours). `up="z"` for CAD/STL exports that are
Z-up. Closed meshes are filled solid (cell centres inside the surface), open ones keep the
shell. Colours map to the nearest catalog colour (restrict with `colors=[...]`). Refine the
result like any design; `hollow()` large solids.
