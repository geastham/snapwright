"""design.py -> voxels -> parts -> checks -> steps -> exports, viewer, book."""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import runpy
import time

import numpy as np

from . import exporters
from .brickify import brickify
from .catalog import Catalog
from .dsl import Model, dsl_namespace
from .render import voxel_preview
from .steps import AUDIENCE_MAX, plan_steps
from .validate import connection_graph, occupancy, validate, verdict

DISCLAIMER = ("Unofficial fan design. Not affiliated with, sponsored or endorsed by the LEGO Group "
              "or any other brick manufacturer.")
ASSETS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "assets"))


def load_design(path: str, catalog: Catalog) -> Model:
    ns = dsl_namespace()
    ns["CATALOG"] = catalog
    g = runpy.run_path(path, init_globals=ns)
    m = g.get("model")
    if not isinstance(m, Model):
        raise SystemExit(f"{path} must define `model = Model(...)`")
    return m


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "model"


def preview(design, out, views=(0, 1, 2, 3), catalog=None, size=700):
    cat = catalog or Catalog()
    m = load_design(design, cat)
    os.makedirs(out, exist_ok=True)
    paths = []
    for k in views:
        p = os.path.join(out, f"preview_view{k}.png")
        voxel_preview(m.V, m.palette, cat, size=(size, size), view=k).save(p)
        paths.append(p)
    w, h, d = m.size_cm()
    print(f"{m.title}: {m.voxel_count():,} voxels, ~{w} x {d} x {h} cm (w x d x h), "
          f"colours: {', '.join(m.palette)}")
    _warn_islands(m, print)
    return paths


def _warn_islands(m, log):
    for isl in m.islands():
        log(f"  warning: {isl['voxels']} voxels at x {isl['x']}, z {isl['z']}, y {isl['y']} don't "
            f"touch the rest of the model or the ground; join them or the build will fail")


class Timer:
    """Wall-clock time per pipeline stage (kept out of model.json so it stays deterministic)."""

    def __init__(self):
        self.t0 = self.last = time.perf_counter()
        self.stages: dict = {}

    def lap(self, name):
        now = time.perf_counter()
        self.stages[name] = self.stages.get(name, 0.0) + now - self.last
        self.last = now

    def report(self):
        total = self.last - self.t0
        rows = [f"  {k:<10} {v:6.2f} s" for k, v in self.stages.items()]
        return "\n".join(["timings:"] + rows + [f"  {'total':<10} {total:6.2f} s"])


def build(design, out, seeds=8, finish="tiles", audience="adult", max_per_step=None,
          book=True, viewer=True, page="letter", strict=True, catalog=None, log=print,
          timer=None):
    """Full pipeline from a design file to every output in `out`. Returns model.json."""
    tm = timer or Timer()
    cat = catalog or Catalog()
    m = load_design(design, cat)
    tm.lap("design")
    os.makedirs(out, exist_ok=True)
    model, V_final = solve(m, cat, seeds=seeds, finish=finish, audience=audience,
                           max_per_step=max_per_step, design_file=os.path.basename(design),
                           log=log, timer=tm)
    ok = model["stats"]["passed"]
    parts = model["parts"]
    slug = model["meta"]["slug"]
    with open(os.path.join(out, "model.json"), "w") as f:
        json.dump(model, f)
    log(f"[5/6] exports -> {out}")
    _write(out, f"{slug}.ldr", exporters.to_ldraw(model, cat))
    _write(out, f"{slug}-bricklink.xml", exporters.to_bricklink_xml(parts, cat))
    _write(out, f"{slug}-rebrickable.csv", exporters.to_rebrickable_csv(parts, cat))
    _write(out, f"{slug}-parts.csv", exporters.to_csv(parts, cat))
    np.savez_compressed(os.path.join(out, "voxels.npz"), V=m.V, V_built=V_final, palette=np.array(m.palette))
    tm.lap("exports")
    if viewer:
        write_viewer(model, os.path.join(out, f"{slug}-viewer.html"))
        tm.lap("viewer")
    if book:
        if ok or not strict:
            from .book import Book
            log("[6/6] book")
            Book(model, cat, os.path.join(out, f"{slug}-instructions.pdf"), page=page, log=log).build()
        else:
            log("[6/6] book skipped: fix the failures above (or pass --no-strict for a draft)")
        tm.lap("book")
    s = model["stats"]
    log(f"done: {s['parts']:,} parts, {s['steps']} steps, {s['connections']:,} connections, "
        f"{'PASS' if ok else 'FAIL'}")
    return model


def solve(m: Model, cat: Catalog, seeds=8, finish="tiles", audience="adult", max_per_step=None,
          design_file="design.py", log=print, timer=None):
    """Design model -> parts, checks and steps, in memory. Returns (model dict, built voxels)."""
    tm = timer or Timer()
    log(f"[1/6] design: {m.title} - {m.voxel_count():,} voxels on {m.NX}x{m.NZ}x{m.NY}")
    _warn_islands(m, log)

    log("[2/6] brickify")
    parts, stats, V_final = brickify(m.V, m.palette, cat, seeds=seeds, finish=finish, log=log)
    tm.lap("brickify")
    if stats.get("recolored_cells"):
        log(f"  note: {stats['recolored_cells']} surface cells recoloured to keep the model in one piece")
    if stats.get("trimmed_cells"):
        log(f"  note: {stats['trimmed_cells']} unsupportable overhang cells trimmed")

    log("[3/6] checks")
    ok, fails = verdict(stats)
    for f in fails:
        log(f"  FAIL: {f}")
    if stats["weak_parts"]:
        log(f"  note: {len(stats['weak_parts'])} single-stud joints")
    if stats["necks"]:
        log(f"  note: thin necks at plates {[n['plate'] for n in stats['necks']][:8]}")
    if stats["unverified_combos"]:
        log(f"  note: {len(stats['unverified_combos'])} part-colour combos unverified")

    tm.lap("checks")
    log("[4/6] steps")
    occ, _ = occupancy(parts, m.V.shape)
    edges = connection_graph(parts, occ)
    mps = max_per_step or AUDIENCE_MAX.get(audience, 12)
    steps = plan_steps(parts, edges, m.V.shape, max_per_step=mps)
    unanchored = sum(len(s["parts"]) for s in steps if s["kind"] == "unanchored")
    if unanchored:
        fails.append(f"{unanchored} parts cannot be attached in any order")
        ok = False

    tm.lap("steps")
    stats.pop("per_part_studs", None)
    used = sorted({p["color"] for p in parts})
    model = {
        "schema": "snapwright.model/0.1",
        "meta": {"title": m.title, "subtitle": m.subtitle, "author": m.author,
                 "slug": slugify(m.title), "disclaimer": DISCLAIMER,
                 "created": _dt.date.today().isoformat(), "generator": "snapwright 0.1",
                 "design_file": design_file, "finish": finish, "audience": audience},
        "grid": {"shape": list(m.V.shape), "stud_mm": 8.0, "plate_mm": 3.2},
        "colors": {k: cat.colors[k] for k in used},
        "catalog_names": {p["part"]: p["name"] for p in parts},
        "parts": parts,
        "steps": steps,
        "bom": [list(r) for r in exporters.bom(parts)],
        "stats": {**stats, "steps": len(steps), "passed": ok, "failures": fails},
    }
    return model, V_final


def write_viewer(model, path):
    with open(os.path.join(ASSETS, "viewer_template.html")) as f:
        html = f.read()
    slim = dict(model)
    slim["parts"] = [{k: p[k] for k in ("x", "y", "z", "dx", "dz", "h", "color", "studs", "step")}
                     for p in model["parts"]]
    slim["steps"] = [{"n": s["n"]} for s in model["steps"]]
    data = json.dumps(slim, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("__MODEL_JSON__", data).replace("__TITLE__", model["meta"]["title"])
    _write(os.path.dirname(path), os.path.basename(path), html)


def _write(d, name, text):
    with open(os.path.join(d, name), "w") as f:
        f.write(text)
