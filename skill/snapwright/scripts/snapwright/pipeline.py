"""design.py -> voxels -> parts -> checks -> steps -> exports, viewer, book."""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import runpy
import time

import numpy as np

from . import __version__, exporters
from .brickify import brickify
from .catalog import Catalog
from .dsl import Model, dsl_namespace
from .render import voxel_preview
from .steps import AUDIENCE_MAX, plan_steps
from .validate import connection_graph, occupancy, report_lines, validate, verdict

DISCLAIMER = ("Unofficial fan design. Not affiliated with, sponsored or endorsed by the LEGO Group "
              "or any other brick manufacturer.")
ASSETS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "assets"))
SCHEMA = "snapwright.model/0.4"


def load_model(path_or_dict) -> dict:
    """Read model.json, upgrading older schemas in memory so every output can be regenerated.

    0.3 -> 0.4: `subassemblies` (sideways panels with their own parts; their steps have
    `sub` and kinds subassembly / attach); older files have none.
    0.2 -> 0.3: parts may be shaped (shape, dir, top_cells, bottom_cells: per-cell studs and
    sockets); 0.2 files have only box parts, so nothing changes but the schema tag.
    0.1 -> 0.2: steps gain `level`; stats gain added_cells, studded_cells, floating_voxels,
    design_voxels (0 when unknown); necks were a per-level heuristic ({plate, strength,
    parts_above}) and are kept as they are, with mass_g unknown (None)."""
    m = path_or_dict if isinstance(path_or_dict, dict) else json.load(open(path_or_dict))
    schema = m.get("schema", "")
    if schema == SCHEMA:
        return m
    if schema in ("snapwright.model/0.2", "snapwright.model/0.3"):
        m["schema"] = SCHEMA
        m.setdefault("subassemblies", [])
        m.setdefault("meta", {}).setdefault("upgraded_from", schema)
        return m
    if schema != "snapwright.model/0.1":
        raise SystemExit(f"unknown model schema {schema!r}; this snapwright reads 0.1 to 0.4")
    parts = m["parts"]
    for st in m["steps"]:
        st.setdefault("level", min(parts[i]["y"] for i in st["parts"]))
    stats = m["stats"]
    for k in ("added_cells", "studded_cells", "floating_voxels", "design_voxels",
              "recolored_cells", "trimmed_cells"):
        stats.setdefault(k, 0)
    for nk in stats.get("necks", []):
        nk.setdefault("mass_g", None)
    m["schema"] = SCHEMA
    m.setdefault("subassemblies", [])
    m.setdefault("meta", {}).setdefault("upgraded_from", schema)
    return m


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
    _warn_thin(m, print)
    return paths


def _warn_thin(m, log):
    thin = m.thin_details()
    if thin:
        eg = ", ".join(f"{t['color']} at {t['at']}" for t in thin[:3])
        log(f"  note: {len(thin)} colour details are only 1 stud across ({eg}{', ...' if len(thin) > 3 else ''}); "
            f"make features that matter at least 2 studs")


def compare(design, ref, out, mask=None, catalog=None):
    """Compare a design with a reference picture: writes compare.png / compare.json in `out`."""
    from .compare import compare as run
    cat = catalog or Catalog()
    m = load_design(design, cat)
    os.makedirs(out, exist_ok=True)
    res = run(m, ref, cat, mask_path=mask, out_png=os.path.join(out, "compare.png"))
    res["thin_details"] = len(m.thin_details())
    with open(os.path.join(out, "compare.json"), "w") as f:
        json.dump(res, f, indent=1)
    v = res["view"]
    ok = res["iou"] >= res["target"]
    print(f"{m.title}: silhouette IoU {res['iou']:.2f} ({'meets' if ok else 'below'} the {res['target']} target), "
          f"best view azimuth {v['azimuth']:.0f}, elevation {v['elevation']:.0f}"
          + (f", colour agreement {res['colour_agreement']:.0%}" if res["colour_agreement"] is not None else ""))
    if res["reference"].get("warning"):
        print(f"  reference: {res['reference']['warning']}")
    for h in res["hints"]:
        print(f"  - {h}")
    _warn_thin(m, print)
    print(f"  side by side -> {os.path.join(out, 'compare.png')}")
    return res


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
          timer=None, shapes=True, base="auto"):
    """Full pipeline from a design file to every output in `out`. Returns model.json."""
    tm = timer or Timer()
    cat = catalog or Catalog()
    m = load_design(design, cat)
    tm.lap("design")
    os.makedirs(out, exist_ok=True)
    model, V_final = solve(m, cat, seeds=seeds, finish=finish, audience=audience,
                           max_per_step=max_per_step, design_file=os.path.basename(design),
                           log=log, timer=tm, shapes=shapes, base=base)
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
        write_viewer(model, os.path.join(out, f"{slug}-viewer.html"), cat)
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
    log("summary (also in the book finale and the viewer):")
    for _, t in report_lines(s):
        log(f"  {t}")
    log(f"done: {s['parts']:,} parts, {s['steps']} steps, {s['connections']:,} connections, "
        f"{'PASS' if ok else 'FAIL'}")
    return model


def solve(m: Model, cat: Catalog, seeds=8, finish="tiles", audience="adult", max_per_step=None,
          design_file="design.py", log=print, timer=None, shapes=True, base="auto"):
    """Design model -> parts, checks and steps, in memory. Returns (model dict, built voxels).
    base="auto": if the model would tip over (and is otherwise one sound structure), stand it
    on a 2-plate base and rebuild; `m` then includes the base, which is counted as added
    support. base="off" leaves balance failures for the designer."""
    tm = timer or Timer()
    log(f"[1/6] design: {m.title} - {m.voxel_count():,} voxels on {m.NX}x{m.NZ}x{m.NY}")
    _warn_islands(m, log)

    log("[2/6] brickify")
    from .snot import anchor_requests
    panels = list(getattr(m, "panels", []))
    anchors = [r for pn in panels for r in anchor_requests(pn.spec)] or None
    parts, stats, V_final = brickify(m.V, m.palette, cat, seeds=seeds, finish=finish, log=log,
                                     shapes=shapes, anchors=anchors)
    if base == "auto" and stats["com_margin_mm"] < 3 and stats["floating"] == 0 \
            and stats["structures"] == 1:
        n = m.base(layers=2, margin=1)
        log(f"  auto-repair: centre of mass only {stats['com_margin_mm']} mm inside the footprint; "
            f"adding a 2-plate base ({n} cells) and rebuilding")
        anchors = [r for pn in panels for r in anchor_requests(pn.spec)] or None
        parts, stats, V_final = brickify(m.V, m.palette, cat, seeds=seeds, finish=finish, log=log,
                                         shapes=shapes, anchors=anchors)
        stats["added_cells"] += n
        stats["base_cells"] = n
    tm.lap("brickify")
    if stats.get("recolored_cells"):
        log(f"  note: {stats['recolored_cells']} surface cells recoloured to keep the model in one piece")
    if stats.get("trimmed_cells"):
        log(f"  note: {stats['trimmed_cells']} unsupportable overhang cells trimmed")
    if stats.get("studded_cells"):
        log(f"  note: {stats['studded_cells']} top cells use studded plates instead of tiles to hold "
            f"parts together")

    log("[3/6] checks")
    ok, fails = verdict(stats)
    for f in fails:
        log(f"  FAIL: {f}")
    if stats["weak_parts"]:
        log(f"  note: {len(stats['weak_parts'])} single-stud joints")
    for nk in stats["necks"][:6]:
        log(f"  note: {nk['parts_above']} parts ({nk['mass_g']:.0f} g) from plate {nk['plate']} up "
            f"are held by {nk['strength']} stud(s)")
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
    subs = []
    if panels:
        subs, steps, pfails = _solve_panels(panels, parts, steps, stats, cat, seeds, finish, mps, log)
        for f in pfails:
            log(f"  FAIL: {f}")
        fails += pfails
        ok = ok and not pfails

    from .steps import label_and_bag
    numbered = label_and_bag(steps)
    tm.lap("steps")
    stats.pop("per_part_studs", None)
    everything = parts + [q for sb in subs for q in sb["parts"]]
    used = sorted({p["color"] for p in everything})
    if subs:
        stats["main_parts"] = len(parts)
        stats["parts"] = len(everything)
        stats["unique_lots"] = len({(p["part"], p["color"]) for p in everything})
    model = {
        "schema": SCHEMA,
        "meta": {"title": m.title, "subtitle": m.subtitle, "author": m.author,
                 "slug": slugify(m.title), "disclaimer": DISCLAIMER,
                 "created": _dt.date.today().isoformat(), "generator": f"snapwright {__version__}",
                 "design_file": design_file, "finish": finish, "audience": audience,
                 "shapes": shapes, "base": base},
        "grid": {"shape": list(m.V.shape), "stud_mm": 8.0, "plate_mm": 3.2},
        "colors": {k: cat.colors[k] for k in used},
        "catalog_names": {p["part"]: p["name"] for p in everything},
        "parts": parts,
        "subassemblies": subs,
        "steps": steps,
        "bom": [list(r) for r in exporters.bom(everything)],
        "stats": {**stats, "steps": len(steps), "numbered_steps": numbered,
                  "bags": max((st["bag"] for st in steps), default=0), "passed": ok, "failures": fails},
    }
    return model, V_final


def _viewer_part(p, cat):
    """The fields the viewer needs; shaped parts add shape, dir, catalog L / lip, studs."""
    q = {k: p[k] for k in ("x", "y", "z", "dx", "dz", "h", "color", "studs", "step")}
    if p.get("shape", "box") in ("slope", "slope_inv", "slope_cvx", "slope_ccv", "round"):     # side-stud bricks draw as boxes
        t = cat.by_id.get(p["part"]) if cat else None
        q.update(shape=p["shape"], dir=p.get("dir", 0), L=t.L if t else max(p["dx"], p["dz"]),
                 lip=t.lip if t else 0.5)
        if "top_cells" in p:
            q["tc"] = p["top_cells"]
    return q


FACE_VIEWS = {0: (0, 3), 1: (0, 1), 2: (1, 2), 3: (2, 3)}   # quarter views that show each face


def _solve_panels(panels, parts, steps, stats, cat, seeds, finish, mps, log):
    """Pack and check each sideways panel on its own, then weave its steps into the book:
    the panel's own steps and an attach step right after its last anchor brick goes in.
    Returns (subassemblies, steps, failures)."""
    from .snot import anchored_cells, panel_hold, part_world_box
    from .validate import part_mass_g
    subs, fails = [], []
    step_of = {pid: st["n"] for st in steps for pid in st["parts"]}
    extra_mass = []
    inserts = {}                                    # main step index -> [panel steps]
    for pn in panels:
        sp = pn.spec
        log(f"  panel {sp.name}: {pn.voxel_count():,} voxels, {sp.W} x {sp.H} studs, {sp.D} plates deep")
        pparts, pstats, _ = brickify(pn.V, pn.palette, cat, seeds=max(2, seeds // 2), finish=finish,
                                     log=lambda *a: None, shapes=False)
        pocc, _ = occupancy(pparts, pn.V.shape)
        pedges = connection_graph(pparts, pocc)
        anchored = anchored_cells(sp, parts)
        held, studs = panel_hold(sp, pparts, pedges, anchored)
        pf = []
        if studs < 2:
            pf.append(f"panel {sp.name}: held by {studs} side stud(s); it needs at least 2 (the model "
                      f"must be solid right behind the panel on its anchor rows)")
        if len(held) < len(pparts):
            pf.append(f"panel {sp.name}: {len(pparts) - len(held)} parts not held through the side studs")
        for f in verdict({**pstats, "com_margin_mm": 99})[1]:
            pf.append(f"panel {sp.name}: {f}")
        # nothing of the main model may be where the panel goes
        x0, x1, z0, z1, y0, y1 = sp.main_region()
        hit = [p["id"] for p in parts if p["x"] < x1 and x0 < p["x"] + p["dx"] and p["z"] < z1
               and z0 < p["z"] + p["dz"] and p["y"] < y1 and y0 < p["y"] + p["h"]]
        if hit:
            pf.append(f"panel {sp.name}: {len(hit)} model parts are in the panel's space")
        fails += pf
        for q in pparts:
            lo, hi = part_world_box(sp, q)
            c = (lo + hi) / 2
            extra_mass.append((part_mass_g(q), c[0] / 8.0, c[2] / 8.0))
        psteps = plan_steps(pparts, pedges, pn.V.shape, max_per_step=mps)
        for st in psteps:
            st["kind"], st["sub"] = "subassembly", sp.name
        ends = [step_of[p["id"]] for p in parts if p.get("anchor") == sp.name]
        after = max(ends) if ends else len(steps)
        prev_view = steps[after - 1]["view"] if steps else 0
        views = FACE_VIEWS[sp.face]
        attach = {"parts": [], "kind": "attach", "sub": sp.name, "level": steps[after - 1]["level"] if steps else 0,
                  "view": prev_view if prev_view in views else views[0]}
        inserts.setdefault(after, []).extend(psteps + [attach])
        subs.append({"name": sp.name, "spec": sp.to_json(), "grid": list(pn.V.shape),
                     "parts": pparts, "anchor_studs": studs, "held": len(held),
                     "face_offset_mm": sp.face_offset_mm(),
                     "stats": {k: pstats[k] for k in ("parts", "connections", "structures", "floating",
                                                      "collisions", "mass_g")},
                     "failures": pf})
        log(f"  panel {sp.name}: {len(pparts)} parts, attached by {studs} side studs"
            + (f"; FAIL" if pf else ""))
    # weave the panel steps in and renumber everything
    merged = []
    for k, st in enumerate(steps, start=1):
        merged.append(st)
        merged.extend(inserts.get(k, []))
    merged.extend(inserts.get(len(steps) + 1, []))
    by_sub = {sb["name"]: sb for sb in subs}
    for n, st in enumerate(merged, start=1):
        st["n"] = n
        pool = by_sub[st["sub"]]["parts"] if st.get("sub") else parts
        for pid in st["parts"]:
            pool[pid]["step"] = n
    # a panel slides on along its face normal: nothing built before its attach step may be in the way
    grid = (max((p["x"] + p["dx"] for p in parts), default=0) + 64,
            max((p["z"] + p["dz"] for p in parts), default=0) + 64, 0)
    for pn in panels:
        sp = pn.spec
        n_attach = next(st["n"] for st in merged if st.get("kind") == "attach" and st["sub"] == sp.name)
        x0, x1, z0, z1, y0, y1 = sp.slide_path(grid)
        block = [p for p in parts if p.get("step", 0) < n_attach and p["x"] < x1 and x0 < p["x"] + p["dx"]
                 and p["z"] < z1 and z0 < p["z"] + p["dz"] and p["y"] < y1 and y0 < p["y"] + p["h"]]
        if block:
            f = (f"panel {sp.name}: {len(block)} parts built before it is attached are in front of it "
                 f"(it can't slide onto its side studs)")
            fails.append(f)
            next(sb for sb in subs if sb["name"] == sp.name)["failures"].append(f)
    stats["panels"] = [{"name": sb["name"], "parts": len(sb["parts"]), "studs": sb["anchor_studs"],
                        "offset_mm": sb["face_offset_mm"]} for sb in subs]
    if extra_mass:
        from .validate import com_margin_with
        stats["com_margin_mm"] = com_margin_with(parts, extra_mass)
        if stats["com_margin_mm"] < 3:
            fails.append(f"centre of mass only {stats['com_margin_mm']} mm inside the footprint "
                         f"with the panels on (tips over)")
    return subs, merged, fails


def _viewer_panels(model):
    """Sideways panels for the viewer: world boxes (mm) per part, the face normal (the way the
    panel slides on) and the step it is attached in."""
    from .snot import PanelSpec, part_world_box
    attach = {st["sub"]: st["n"] for st in model["steps"] if st.get("kind") == "attach"}
    out = []
    for sb in model.get("subassemblies", []):
        sp = PanelSpec.from_json(sb["spec"])
        _, n, _ = sp.frame()
        boxes = []
        for q in sb["parts"]:
            lo, hi = part_world_box(sp, q)
            boxes.append({"lo": [round(float(v), 2) for v in lo], "hi": [round(float(v), 2) for v in hi],
                          "color": q["color"]})
        out.append({"name": sb["name"], "n": [float(n[0]), 0.0, float(n[2])],
                    "step": attach.get(sb["name"], len(model["steps"])), "parts": boxes})
    return out


def write_viewer(model, path, catalog=None, embed_three=True):
    """The self-contained 3D viewer. embed_three: include three.js (~720 KB, MIT; from
    assets/vendor) so it works offline and in sandboxed previews; else load it from a CDN."""
    cat = catalog or Catalog()
    with open(os.path.join(ASSETS, "viewer_template.html")) as f:
        html = f.read()
    slim = dict(model)
    slim["parts"] = [_viewer_part(p, cat) for p in model["parts"]]
    slim["steps"] = [{"n": s["n"], "label": s.get("label", str(s["n"])), "bag": s.get("bag", 1),
                      "kind": s.get("kind", "build")} for s in model["steps"]]
    slim["report"] = [{"kind": k, "text": t} for k, t in report_lines(model["stats"])]
    slim["panels"] = _viewer_panels(model)
    slim.pop("subassemblies", None)
    data = json.dumps(slim, separators=(",", ":")).replace("</", "<\\/")
    three = orbit = ""
    if embed_three:
        vendor = os.path.join(ASSETS, "vendor")
        three = open(os.path.join(vendor, "three.module.min.js"), encoding="utf-8").read()
        orbit = open(os.path.join(vendor, "OrbitControls.js"), encoding="utf-8").read()
    # the model JSON goes in last: nothing inside it is treated as a placeholder
    html = (html.replace("__THREE_SRC__", three).replace("__ORBIT_SRC__", orbit)
            .replace("__TITLE__", model["meta"]["title"]).replace("__MODEL_JSON__", data))
    _write(os.path.dirname(path), os.path.basename(path), html)


def _write(d, name, text):
    with open(os.path.join(d, name), "w") as f:
        f.write(text)
