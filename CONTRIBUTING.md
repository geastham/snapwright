# Contributing to Snapwright

Thanks for helping. Snapwright's promise is that what it says is buildable is buildable, so
most of this page is about not breaking that.

## Set up

```bash
python -m venv .venv && . .venv/bin/activate
make setup          # numpy, scipy, pillow, reportlab + pytest, pytest-xdist
make test           # ~40 s on a laptop, all cores
make example        # builds examples/lighthouse/out/ (must PASS)
```

Runtime code (everything under `skill/snapwright/`) may only use numpy, scipy, pillow and
reportlab, may not use the network (except `sw.py sync-catalog`), and may not need a GPU. The
skill must run in the claude.ai sandbox and stay under 2 MB zipped (`make package`).

## Ground rules

- **Buildability first.** Never loosen a check to make a model pass. If a model fails, fix the
  geometry or the algorithm. A change that makes `examples/lighthouse` FAIL, or moves its part
  count by more than 5% without an explanation in the PR, is a regression.
- **Be honest about automatic changes.** Every recolour, trim, added part, studded-instead-of-
  tiled cell or automatic base is counted in `stats` and shown in the build log, the book and
  the viewer. They all read `validate.report_lines`; add new kinds of change there.
- **model.json is canonical.** Every output (book, viewer, LDraw, parts lists) must be
  regenerable from it alone. On a breaking change, bump `SCHEMA` in `pipeline.py` and keep a
  reader for the previous version (`pipeline.load_model`); `tests/fixtures/v0.1_model.json`
  shows how.
- **Deterministic.** Same design, catalog and seeds give the same model. No wall-clock or
  unseeded randomness in the core.
- **Tests first for geometry.** When you find a model the packer, checker or step planner gets
  wrong, reduce it to a fixture in `tests/fixtures/` (a small design `.py` or a voxel `.npz`)
  with the expected outcome, watch it fail, then fix it. `tests/oracles.py` holds independent
  re-implementations of the invariants; don't make it import the code it checks.
- **Look at the outputs.** Tests don't catch an ugly page. For book or viewer changes, render
  some pages (`pdftoppm -r 60 -f 1 -l 6 book.pdf page`) and open the viewer before sending.
- Keep `SKILL.md` under 500 lines; put detail in `skill/snapwright/references/`.

## Names, brands and third-party work

Read `NOTICE.md` and `skill/snapwright/references/ip-and-naming.md`. In short:

- No toy-brick manufacturer brand in any name, title, file name, UI string, example or test.
  Say "brick", "interlocking brick", "compatible bricks".
- Don't imitate official instruction-book styling.
- Don't copy code from other brick-model projects or demos; implement from first principles
  and cite papers or public specs (the LDraw file format, Rebrickable's CSV dumps) instead.
- Test images, meshes and designs must be your own work (generated or drawn); no downloaded
  photos of third-party characters or products.

## Generated files

Outputs go in `out/` folders, which git ignores. Never commit PDFs, packaged `.skill` files or
any file over 1 MB; `tests/test_repo_hygiene.py` enforces this. Large books ship as release
assets.

## The parts catalog

`skill/snapwright/assets/catalog.json` lists the parts and colours the packer may use, with
connection metadata (`top`, `bottom`, `side`), LDraw file names and origins, and marketplace
ids. To add a part:

1. Add the entry. Check its size, origin and stud/socket cells against the LDraw part
   (`tools/ldraw_check.py`, see `docs/ldraw-check.md`).
2. If Rebrickable numbers it differently, set `rebrickable` (for example 4073 is 6141 there).
3. Refresh availability: `python skill/snapwright/scripts/sw.py sync-catalog`. It downloads
   Rebrickable's free CSV dumps (about 16 MB, cached in `assets/.rebrickable/`, which git
   ignores) and records which colours the part has appeared in since 2005. With
   `--key YOUR_KEY` it uses the Rebrickable API instead. Commit the updated `catalog.json`.
4. Run `make test` and `make example`.

## Pull requests

- One milestone or topic per branch, small commits, `make test` and `make example` green.
- Say in the PR what changed for users, which calls you made and why ("Decisions"), and paste
  lighthouse part and step counts before and after.
- Update `TASKS.md`, and `SPEC.md` if you close a backlog item.

## Evals

`evals/evals.json` holds end-to-end prompts with checkable assertions, and `evals/files/`
holds their inputs (all generated here). They're run with the skill-creator eval loop, with
and without the skill. Add an eval when you fix something users would notice.
