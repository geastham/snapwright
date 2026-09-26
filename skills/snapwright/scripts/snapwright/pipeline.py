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
    # the order lists cover everything, panels (built separately) included
    everything = parts + [q for sb in model.get("subassemblies", []) for q in sb["parts"]]
    _write(out, f"{slug}-bricklink.xml", exporters.to_bricklink_xml(everything, cat))
    _write(out, f"{slug}-rebrickable.csv", exporters.to_rebrickable_csv(everything, cat))
    _write(out, f"{slug}-parts.csv", exporters.to_csv(everything, cat))
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
    hinged = [pn for pn in panels if getattr(pn.spec, "mount", "") == "hinge"]
    sideways = [pn for pn in panels if pn not in hinged]

    def pack():
        anchors = [r for pn in sideways for r in anchor_requests(pn.spec)] or None
        held = _hinge_placeholders(m, hinged, cat)
        parts, stats, V_final = brickify(m.V, m.palette, cat, seeds=seeds, finish=finish, log=log,
                                         shapes=shapes, anchors=anchors)
        if hinged:
            parts, stats = _swap_hinges(m, hinged, held, parts, stats, V_final, cat, log)
        return parts, stats, V_final

    parts, stats, V_final = pack()
    if base == "auto" and stats["com_margin_mm"] < 3 and stats["floating"] == 0 \
            and stats["structures"] == 1:
        n = m.base(layers=2, margin=1)
        log(f"  auto-repair: centre of mass only {stats['com_margin_mm']} mm inside the footprint; "
            f"adding a 2-plate base ({n} cells) and rebuilding")
        parts, stats, V_final = pack()
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


def _hinge_placeholders(m, hinged, cat):
    """Hold the fixed hinge plates' cells with a colour the model doesn't use while packing, so
    the model under them gets studs (not tiles). Returns (palette index, [(x, z, y)])."""
    if not hinged:
        return None
    spare = next(k for k in ("yellow", "orange", "red", "blue", "white", "tan") if k not in m.palette)
    idx = m._idx(spare)
    cells = []
    for pn in hinged:
        sp = pn.spec
        for h in sp.hinges:
            for (x, z) in sp.fixed_cells(h):
                m.V[x, z, sp.y] = idx
                cells.append((x, z, sp.y))
    return idx, cells


def _swap_hinges(m, hinged, held, parts, stats, V_final, cat, log):
    """Replace the placeholder parts with the fixed hinge plates and re-check the model."""
    from .validate import validate
    idx, cells = held
    spare = m.palette[idx - 1]
    cellset = set(cells)
    drop = {p["id"] for p in parts if p["color"] == spare}
    for p in parts:
        if p["id"] in drop:
            own = {(p["x"] + a, p["z"] + b, p["y"] + c) for a in range(p["dx"]) for b in range(p["dz"])
                   for c in range(p["h"])}
            if not own <= cellset:
                raise RuntimeError("hinge placeholder packed together with other cells")
    kept = [p for p in parts if p["id"] not in drop]
    for pn in hinged:                  # the hinge plates are part of the design from here on
        colour = getattr(pn.spec, "hinge_color", "black")
        k = m._idx(colour)
        for h in pn.spec.hinges:
            for (x, z) in pn.spec.fixed_cells(h):
                m.V[x, z, pn.spec.y] = k
                V_final[x, z, pn.spec.y] = k
        kept += pn.spec.fixed_parts(colour)
    for k, p in enumerate(kept):
        p["id"] = k
    fresh = validate(kept, m.V.shape, cat)
    for k, v in fresh.items():
        stats[k] = v
    n = sum(len(pn.spec.hinges) for pn in hinged)
    log(f"  hinges: {n} locking hinge plates on the model for {len(hinged)} hinged panel(s)")
    return kept, stats


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
        if getattr(sp, "mount", "") == "hinge":
            sb, psteps, pf, masses = _solve_hinged(pn, parts, stats, cat, seeds, mps, log)
            fails += pf
            extra_mass += masses
            inserts.setdefault(len(steps), []).extend(psteps)
            subs.append(sb)
            continue
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
        if getattr(sp, "mount", "") == "hinge":
            continue
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
                        "offset_mm": sb["face_offset_mm"],
                        **({"mount": "hinge", "angle": sb["spec"]["angle"], "hinges": sb["hinges"],
                            "curved": sb["curved"]} if sb["spec"].get("mount") == "hinge" else {})}
                       for sb in subs]
    if extra_mass:
        from .validate import com_margin_with
        stats["com_margin_mm"] = com_margin_with(parts, extra_mass)
        if stats["com_margin_mm"] < 3:
            fails.append(f"centre of mass only {stats['com_margin_mm']} mm inside the footprint "
                         f"with the panels on (tips over)")
    return subs, merged, fails


def _solve_hinged(pn, parts, stats, cat, seeds, mps, log):
    """Pack and check one hinged panel. Returns (subassembly, its steps + attach step,
    failures, [(mass g, x, z)])."""
    from .hinge import pack_panel, panel_connections, part_center_world, tile_overlaps
    from .validate import DSU, part_mass_g
    sp = pn.spec
    grid = sp.grid_shape()
    log(f"  panel {sp.name}: {pn.voxel_count():,} voxels, {sp.W} x {sp.H} studs, {sp.D} plates deep, "
        f"hinged at {sp.angle:g} degrees, {len(getattr(pn, 'placed', []))} curved tiles")
    pparts, notes = pack_panel(pn, cat, seeds=max(2, seeds // 2))
    edges, coll = panel_connections(pparts, grid)
    d = DSU(max(len(pparts), 1))
    for a, b in edges:
        d.union(a, b)
    roots = {d.find(p["id"]) for p in pparts if p.get("kind") == "hinge"}
    held = [p["id"] for p in pparts if d.find(p["id"]) in roots]
    n_hinges = sum(1 for p in pparts if p.get("kind") == "hinge")
    pf = []
    if n_hinges < 2:
        pf.append(f"panel {sp.name}: held by {n_hinges} hinge(s); it needs at least 2")
    if len(held) < len(pparts):
        pf.append(f"panel {sp.name}: {len(pparts) - len(held)} parts not held through the hinges")
    if coll:
        pf.append(f"panel {sp.name}: {coll} colliding cells")
    over = tile_overlaps(pparts)
    if over:
        pf.append(f"panel {sp.name}: {len(over)} curved tiles overlap other tiles")
    fixed = [p for p in parts if p.get("hinge") == sp.name]
    if len(fixed) != len(sp.hinges):
        pf.append(f"panel {sp.name}: {len(fixed)} of {len(sp.hinges)} hinge plates on the model")
    # nothing of the main model may be where the panel, its hinge layer or the knuckles go
    import numpy as np
    hit = []
    for p in parts:
        if p.get("hinge") == sp.name:
            continue
        X, Z, Y = np.meshgrid(np.arange(p["x"], p["x"] + p["dx"]) + 0.5, np.arange(p["z"], p["z"] + p["dz"]) + 0.5,
                              np.arange(p["y"], p["y"] + p["h"]) + 0.5, indexing="ij")
        if sp.keep_clear(X, Y, Z).any():
            hit.append(p["id"])
    if hit:
        pf.append(f"panel {sp.name}: {len(hit)} model parts are in the panel's space")
    for f in pf:
        log(f"  FAIL: {f}")
    for nt in notes:
        log(f"  panel {sp.name}: {nt}")
    masses = []
    for q in pparts:
        c = part_center_world(sp, q)
        masses.append((part_mass_g(q), c[0] / 8.0, c[2] / 8.0))
    psteps = plan_steps(pparts, edges, grid, max_per_step=mps)
    for st in psteps:
        st["kind"], st["sub"] = "subassembly", sp.name
    attach = {"parts": [], "kind": "attach", "sub": sp.name, "level": 0, "view": FACE_VIEWS[sp.toward][0]}
    curved = sum(1 for q in pparts if q.get("shape") == "outline")
    sb = {"name": sp.name, "spec": sp.to_json(), "grid": list(grid), "parts": pparts,
          "anchor_studs": 2 * n_hinges, "hinges": n_hinges, "held": len(held), "face_offset_mm": 0,
          "curved": curved,
          "stats": {"parts": len(pparts), "connections": int(sum(edges.values())),
                    "structures": len({d.find(p["id"]) for p in pparts}), "floating": len(pparts) - len(held),
                    "collisions": coll, "mass_g": round(sum(part_mass_g(q) for q in pparts), 1)},
          "failures": pf}
    log(f"  panel {sp.name}: {len(pparts)} parts ({curved} curved tiles), on {n_hinges} click hinges"
        + ("; FAIL" if pf else ""))
    return sb, psteps + [attach], pf, masses


def _viewer_hinged(sb, step):
    """A hinged panel for the viewer: its frame (panel mm -> world mm) and each part in panel
    mm: a box, or a curved tile's outline; plus the studs left showing."""
    from .hinge import HingeSpec
    sp = HingeSpec.from_json(sb["spec"])
    R, O = sp.rotation(), sp.origin()
    S, P = 8.0, 3.2
    parts, occ_top = [], {}
    for q in sb["parts"]:
        occ_top.update({(q["x"] + a, q["z"] + b, q["y"] + q["h"] - 1): q["id"]
                        for a in range(q["dx"]) for b in range(q["dz"])})
    covered = set()
    for q in sb["parts"]:
        if q.get("shape") == "outline":
            from .hinge import tile_cells
            c, g, _ = tile_cells([tuple(v) for v in q["outline"]], q["dx"], q["dz"], q["x"], q["z"])
            covered |= {(i, j, q["y"] - 1) for (i, j) in c}
    studs = []
    for q in sb["parts"]:
        e = {"color": q["color"], "step": q.get("step", 0)}
        if q.get("shape") == "outline":
            e["outline"] = [[round(a * S, 2), round(b * S, 2)] for a, b in q["outline"]]
            e["y0"], e["y1"] = q["y"] * P, (q["y"] + q["h"]) * P
        else:
            e["lo"] = [q["x"] * S, q["y"] * P, q["z"] * S]
            e["hi"] = [(q["x"] + q["dx"]) * S, (q["y"] + q["h"]) * P, (q["z"] + q["dz"]) * S]
            if q.get("studs"):
                for a in range(q["dx"]):
                    for b in range(q["dz"]):
                        cell = (q["x"] + a, q["z"] + b, q["y"] + q["h"] - 1)
                        above = (cell[0], cell[1], cell[2] + 1)
                        if above not in occ_top and cell not in covered:
                            studs.append([(cell[0] + 0.5) * S, (cell[2] + 1) * P, (cell[1] + 0.5) * S,
                                          q["color"]])
        parts.append(e)
    return {"name": sb["name"], "mount": "hinge", "step": step,
            "R": [round(float(v), 6) for v in R.ravel()], "O": [round(float(v), 3) for v in O],
            "n": [float(v) for v in R[:, 1]], "parts": parts, "studs": studs}


def _viewer_panels(model):
    """Sideways panels for the viewer: world boxes (mm) per part, the face normal (the way the
    panel slides on) and the step it is attached in."""
    from .snot import PanelSpec, part_world_box
    attach = {st["sub"]: st["n"] for st in model["steps"] if st.get("kind") == "attach"}
    out = []
    for sb in model.get("subassemblies", []):
        if sb["spec"].get("mount") == "hinge":
            out.append(_viewer_hinged(sb, attach.get(sb["name"], len(model["steps"]))))
            continue
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
