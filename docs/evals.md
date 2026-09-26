# Evals

`evals/evals.json` holds seven end-to-end prompts, each with named assertions. The inputs in
`evals/files/` were all generated for this repo: a cartoon dog, a sunset, a rocket STL, a
lamp that tips over and a gatehouse. The prompts were run with the skill-creator loop, each
by a fresh agent **with** the skill and **without** it (the baseline may write its own
tools). `evals/grade.py` grades every run with Snapwright's own validator: other runs' parts
are converted to grid boxes first, so "the model passes" means the same thing for both
configurations. Workspaces (`skills/snapwright-workspace/`) are git-ignored.

```bash
python evals/grade.py skills/snapwright-workspace/iteration-N
python -m scripts.aggregate_benchmark skills/snapwright-workspace/iteration-N --skill-name snapwright   # from skill-creator
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
MagicaVoxel, patio bricks, and others). Result, with each query run 3 times with Opus 5.5 in a clean project: **20/20**. All 10
should-trigger queries loaded the skill 3/3 times, including the "fix my failing build log"
case, and all 10 near-misses stayed off 0/3. skill-creator's `run_loop` found nothing to
improve, so the description is unchanged.

Getting a clean measurement took three fixes to the harness (in a local copy of
skill-creator's `run_eval.py`):
- **Skill folder, not command file:** the skill under test is installed as
  `.claude/skills/<name>/SKILL.md`. This Claude Code version lists `.claude/commands` files
  as slash commands only, so the model never saw them (0% recall).
- **Isolation from the installed copy:** `claude -p` runs with `--setting-sources project`,
  so a copy of the skill already on the account can't answer in place of the one under
  test.
- **Real name:** each query gets its own throwaway project with the skill under its real
  name. Earlier runs used a suffixed name (`snapwright-skill-1a2b`), which looks like an odd
  different skill and got 17-25% recall.

Proposed rewrites are screened for brand names before use: one early proposal put a
manufacturer's brand in the description, which NOTICE.md rules out.
