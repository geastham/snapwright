# Evals

`evals/evals.json` holds seven end-to-end prompts, each with named assertions. The inputs in
`evals/files/` were all generated for this repo: a cartoon dog, a sunset, a rocket STL, a
lamp that tips over and a gatehouse. The prompts were run with the skill-creator loop, each
by a fresh agent **with** the skill and **without** it (the baseline may write its own
tools). `evals/grade.py` grades every run with Snapwright's own validator: other runs' parts
are converted to grid boxes first, so "the model passes" means the same thing for both
configurations. Workspaces (`skill/snapwright-workspace/`) are git-ignored.

```bash
python evals/grade.py skill/snapwright-workspace/iteration-N
python -m scripts.aggregate_benchmark skill/snapwright-workspace/iteration-N --skill-name snapwright   # from skill-creator
```

## Results

| | pass rate | time per task | tokens |
|---|---|---|---|
| without the skill (baseline) | 91% | 611 s | 132k |
| with the skill, iteration 1 | 97% | 328 s | 114k |
| with the skill, iteration 2 (after the fixes below) | 97% | 255 s | 97k |

Most assertions don't separate the two: capable baselines wrote their own voxelisers, greedy
tilers and PDF renderers, and their models passed the same structural checks. The
differences are in what the assertions don't measure:

- **Build order:** the dog baseline has bricks that hang from the layer above and must be
  pushed up from underneath.
- **Surface and parts:** baselines use only bricks, so every surface is stepped; they have no
  slopes, tiles, sub-steps or bags, and no verified part-colour data.
- **Speed:** with the skill, tasks take less than half the time.

## What the runs found, and the general fixes

| found by | problem | fix |
|---|---|---|
| sunset mosaic | the 48 x 48 base packed into two identical grids of 8 x 8 plates, so every seam ran straight through | whole-side seams (6+ studs) continued through stacked plates cost score |
| sunset mosaic | the default palette was core colours only (no bright light orange) | default palette = every opaque colour made as a 1x1 tile and plate |
| tipping lamp | cells under a round post took the hidden-filler colour and showed at its corners | cells under round parts and beside slope ends keep their design colour |
| rocket STL | fins thinner than a stud were lost or came out touching only at their corners | sheets are kept with their roots, edge-only contacts bridged, one-stud staircases widened |
| rocket STL | red fins against a white body failed even after 34 recoloured cells | repair recolours one contact cell per group; groups blocked only by colour are recoloured at once; stages escalate on lack of progress; the best round is kept |
| rocket STL (iteration 2) | the nose narrowed then widened | rays through shared edges and touching caps no longer flip inside and outside |
| pet photo | the face panel landed on the front of the paws | a panel's default plane comes from its own rows |
| castle, kids lighthouse | agents reported "likely" availability as "verified" | the catalog is now verified (Rebrickable set inventories) and the summary always states availability |

Still open: open triangles where slopes meet at the corners of stepped cones. This needs
corner slopes (SPEC backlog item 11).

## Triggering

`evals/trigger_eval.json` has 20 realistic queries: 10 that should use the skill and 10
near-misses that shouldn't (a BrickLink XML script, STL to 3MF, cross-stitch, Minecraft,
MagicaVoxel, patio bricks, and others). With the current description, each query run 3
times with Opus 5.5 (a query counts as triggered when at least 2 of 3 runs load the skill):

- **Scores:** 19/20 correct. All 10 near-misses stayed off (0/3 each), and 9 of the 10
  should-trigger queries triggered (7 of them 3/3).
- **The miss:** "the build log for my design.py says 'FAIL: 2 separate structures' ...
  what should I change?" (1/3). Claude often answers that kind of question directly. The
  description now also names fixing a failing design or build log; that left the 10
  negatives at 0/3 and the miss at 1/3.
- **The optimisation loop:** skill-creator's `run_loop` wasn't used to rewrite the
  description, for two reasons. The test account already had this skill installed with the
  same description, and the model used that copy instead of the harness's temporary one (so
  the harness saw 0% recall); a proposed rewrite also put a manufacturer's brand in the
  description, which NOTICE.md rules out. The runs above count a trigger of either copy,
  which is valid only because both carry the description under test.
