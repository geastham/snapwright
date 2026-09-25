# Working in this repo (for coding agents)

- Read SPEC.md first; it defines milestones, acceptance criteria and the known-issues backlog.
- The installable skill is `skill/snapwright/`. Everything it needs at runtime lives inside it.
  Anything outside (tests, examples, creations, docs) is for development only.
- Runtime deps stay limited to numpy, scipy, pillow, reportlab. No network at runtime except
  the optional `sync-catalog` command. No GPU.
- Run `make test` and `make example` before every commit. A change that makes the lighthouse
  FAIL is a regression.
- Every automatic geometry change (recolour, trim, added support) must be counted in stats and
  surfaced in the log, book and viewer.
- model.json is canonical; outputs must be regenerable from it alone. Bump the schema version
  on breaking changes and keep a reader for the previous version.
- Never use a brick manufacturer's brand in names, titles, file names or UI; follow NOTICE.md.
- Keep SKILL.md under 500 lines; put detail in references/.
- Generated outputs go in `out/` folders (git-ignored). Never commit books (PDFs), packaged
  skills or files over 1 MB; they ship as release assets. `tests/test_repo_hygiene.py` enforces it.
