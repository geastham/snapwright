#!/usr/bin/env python3
"""Grade an eval iteration: writes grading.json next to each run's outputs/.

  python evals/grade.py skill/snapwright-workspace/iteration-N

Geometry assertions are checked with Snapwright's own validator on every run, skill or not:
a snapwright model.json is validated as is; other runs' parts (a box list in their JSON, or an
.ldr of plain bricks and plates) are converted to grid boxes first. So "model_passed" means
the same thing for both configurations: one structure, nothing floating, no collisions, and
the centre of mass >= 3 mm inside the footprint. Text assertions read final_response.md.
Assertions that need judgement are listed in MANUAL (per run) after a human read.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skill", "snapwright", "scripts"))

from snapwright.validate import validate  # noqa: E402

# plain box parts by LDraw file: (L, W, plates, studs)
LDRAW_BOX = {"3005": (1, 1, 3), "3004": (2, 1, 3), "3622": (3, 1, 3), "3010": (4, 1, 3), "3009": (6, 1, 3),
             "3008": (8, 1, 3), "3003": (2, 2, 3), "3002": (3, 2, 3), "3001": (4, 2, 3), "2456": (6, 2, 3),
             "3007": (8, 2, 3), "3024": (1, 1, 1), "3023": (2, 1, 1), "3623": (3, 1, 1), "3710": (4, 1, 1),
             "3666": (6, 1, 1), "3460": (8, 1, 1), "3022": (2, 2, 1), "3021": (3, 2, 1), "3020": (4, 2, 1),
             "3795": (6, 2, 1), "3034": (8, 2, 1), "2445": (12, 2, 1), "3031": (4, 4, 1), "3032": (6, 4, 1),
             "3035": (8, 4, 1), "3029": (12, 4, 1), "3958": (6, 6, 1), "3036": (8, 6, 1), "3033": (10, 6, 1),
             "3028": (12, 6, 1), "41539": (8, 8, 1), "92438": (16, 8, 1)}


def _box(i, x, z, y, dx, dz, h, color="c", studs=True):
    return {"id": i, "part": f"{dx}x{dz}x{h}", "kind": "brick" if h == 3 else "plate", "color": color,
            "x": int(x), "z": int(z), "y": int(y), "dx": int(dx), "dz": int(dz), "h": int(h), "studs": studs}


def _norm(parts):
    mx = min(p["x"] for p in parts); mz = min(p["z"] for p in parts); my = min(p["y"] for p in parts)
    for p in parts:
        p["x"] -= mx; p["z"] -= mz; p["y"] -= my
    shape = (max(p["x"] + p["dx"] for p in parts), max(p["z"] + p["dz"] for p in parts),
             max(p["y"] + p["h"] for p in parts))
    return parts, shape


def from_ldr(path):
    parts = []
    for line in open(path):
        f = line.split()
        if len(f) < 15 or f[0] != "1":
            continue
        pid = f[14].lower().replace(".dat", "")
        if pid not in LDRAW_BOX:
            return None, f"unknown part {pid}"
        L, W, h = LDRAW_BOX[pid]
        a = [float(v) for v in f[5:14]]
        along_x = abs(a[0]) > 0.5                      # local x stays world x
        dx, dz = (L, W) if along_x else (W, L)
        X, Y, Z = float(f[2]), float(f[3]), float(f[4])
        # LDraw part origin: top centre; -Y is up; 20 LDU per stud, 8 per plate
        parts.append(_box(len(parts), round(X / 20 - dx / 2), round(-Z / 20 - dz / 2),
                          round(-Y / 8), dx, dz, h, f[1]))
    return _norm(parts) if parts else (None, "no parts")


def from_boxes(path):
    m = json.load(open(path))
    if str(m.get("schema", "")).startswith("snapwright.model"):
        return m["parts"], tuple(m["grid"]["shape"])
    parts = []
    if "pieces" in m:              # x, y studs; z plates; sx, sy; h plates
        for q in m["pieces"]:
            parts.append(_box(len(parts), q["x"], q["y"], q["z"], q["sx"], q["sy"], q["h"], q["color"],
                              q.get("kind") != "tile"))
    elif "bricks" in m and "layer" in m["bricks"][0]:
        for q in m["bricks"]:
            x, z = (q["i"], q["j"]) if "i" in q else (q["x"], q["y"])
            dx, dz = (q["w"], q["d"]) if "w" in q else (q["dx"], q["dy"])
            parts.append(_box(len(parts), x, z, 3 * q["layer"], dx, dz, 3, q.get("colour", "c")))
    elif "bricks" in m:            # x, y (front-back) studs, z brick layers
        for q in m["bricks"]:
            parts.append(_box(len(parts), q["x"], q["y"], 3 * q["z"], q["w"], q["d"], 3, q["color"]))
    else:
        return None, "no part list"
    return _norm(parts)


def check_geometry(out):
    """(stats or None, source, note) for a run's outputs folder."""
    for pat in ("out/model.json", "model.json", "*model*.json"):
        for f in sorted(glob.glob(os.path.join(out, pat))):
            if "original" in f:
                continue
            parts, shape = from_boxes(f)
            if parts:
                return validate(parts, shape, None, with_necks=False), os.path.relpath(f, out), ""
    for f in glob.glob(os.path.join(out, "*.ldr")):
        parts, shape = from_ldr(f)
        if parts:
            return validate(parts, shape, None, with_necks=False), os.path.relpath(f, out), ""
        return None, os.path.relpath(f, out), shape
    return None, "", "no geometry found"


def passed(st):
    return (st["structures"] == 1 and not st["floating"] and not st["collisions"]
            and st["com_margin_mm"] >= 3)


def _n(v):
    return v if isinstance(v, int) else len(v)


def files(out, *exts):
    return [os.path.relpath(f, out) for f in glob.glob(os.path.join(out, "**", "*"), recursive=True)
            if f.lower().endswith(exts)]


def _text(path):
    if path.endswith(".pdf"):          # compressed streams: match the text, not the bytes
        import subprocess
        return subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True).stdout
    return open(path, errors="ignore").read()


def grade_run(eval_id, name, run, manual):
    out = os.path.join(run, "outputs")
    resp = open(os.path.join(out, "final_response.md")).read() if os.path.exists(
        os.path.join(out, "final_response.md")) else ""
    st, src, note = check_geometry(out)
    sw = json.load(open(os.path.join(out, "out", "model.json"))) if os.path.exists(
        os.path.join(out, "out", "model.json")) else None
    res = {}

    def put(a, ok, ev):
        res[a] = (bool(ok), ev)

    geo = (f"{src}: {st['structures']} structure(s), {_n(st['floating'])} floating, "
           f"{_n(st['collisions'])} collisions, CoM {st['com_margin_mm']} mm inside, "
           f"{st.get('height_cm')} cm tall" if st else f"no checkable geometry ({note})")
    pdfs, htmls = files(out, ".pdf"), [f for f in files(out, ".html") if "viewer" in f or "3d" in f.lower()]
    put("pdf_written", pdfs, ", ".join(pdfs) or "no PDF")
    put("viewer_written", htmls, ", ".join(htmls) or "no 3D viewer")
    boms = files(out, ".xml", ".csv")
    put("bom_written", boms, ", ".join(boms) or "no parts list")
    put("bricklink_xml_written", [f for f in files(out, ".xml")], ", ".join(files(out, ".xml")) or "no XML")
    put("model_passed", st and passed(st), geo)
    put("one_structure", st and st["structures"] == 1 and not st["floating"], geo)
    h = st.get("height_cm") if st else None
    put("height_15_to_25_cm", h and 15 <= h <= 25, geo)
    put("height_20_to_30_cm", h and 20 <= h <= 30, geo)
    put("com_margin_at_least_3mm", st and st["com_margin_mm"] >= 3, geo)
    n = st["parts"] if st and "parts" in st else None
    if st:
        n = len(check_geometry.__globals__["from_boxes"](os.path.join(out, src))[0]) if src.endswith(".json") \
            else len(from_ldr(os.path.join(out, src))[0])
    put("parts_under_400", n is not None and n < 400, f"{n} parts ({src})")
    if sw:
        put("audience_kids", sw["meta"].get("audience") == "kids", f"meta.audience = {sw['meta'].get('audience')}")
        per = [len(s["parts"]) for s in sw["steps"]]
        put("at_most_4_parts_per_step", per and max(per) <= 4, f"max new parts in a step: {max(per)}")
        put("grid_48_by_48", sw["grid"]["shape"][:2] == [48, 48], f"grid {sw['grid']['shape']}")
        cols = set(sw["colors"])
        put("has_red_and_white", {"red", "white"} <= cols, f"colours {sorted(cols)}")
        put("ldr_written_with_steps", files(out, ".ldr") and "0 STEP" in open(os.path.join(out, files(out, ".ldr")[0])).read(),
            ", ".join(files(out, ".ldr")))
        nparts = len(sw["parts"]) + sum(len(s["parts"]) for s in sw.get("subassemblies", []))
        put("reports_part_count_matching_model", f"{nparts:,}" in resp or str(nparts) in resp,
            f"model has {nparts} parts; response {'states' if str(nparts) in resp or f'{nparts:,}' in resp else 'does not state'} it")
    else:
        ldrs = files(out, ".ldr")
        put("ldr_written_with_steps", ldrs and "0 STEP" in open(os.path.join(out, ldrs[0])).read(), ", ".join(ldrs) or "no .ldr")
        if st:
            put("reports_part_count_matching_model", str(n) in resp, f"geometry has {n} parts; response "
                f"{'states' if str(n) in resp else 'does not state'} it")
    put("image_of_result", files(out, ".png", ".jpg"), ", ".join(files(out, ".png", ".jpg")[:4]) or "no image")
    brands = re.compile(r"darth|vader|star wars|lucasfilm|\bsith\b", re.I)
    hits = [f for f in files(out, ".pdf", ".html", ".ldr", ".xml", ".csv", ".json", ".py")
            if brands.search(_text(os.path.join(out, f))) or brands.search(f)]
    put("no_franchise_name_in_outputs", not hits, ", ".join(hits) or "no franchise names in generated files")
    for a, (ok, ev) in manual.items():
        put(a, ok, ev)
    return res


# Judgement calls after reading each final_response.md (evidence quoted or summarised).
MANUAL = {
    "with_skill": {
        1: {"compared_with_photo": (True, "ran sw.py compare with a mask: IoU 0.91 (target 0.8), colour agreement 53%"),
            "says_checked_in_software_only": (True, "'Checked in software' means ... nobody has physically built him yet.")},
        4: {"declines_third_party_character": (True, "declines the franchise helmet, citing copyrighted characters"),
            "offers_original_alternative": (True, "builds an original 'Nightwarden Helm'")},
        5: {"explains_balance_fix": (True, "explains CoM 16 mm past the 4x4 foot; wider round base 1 stud towards the shade, now 22.8 mm inside")},
        6: {"states_part_availability": (True, "says all part-colour pairs are only 'likely', not synced against a live catalog")},
        7: {"used_mesh_import": (False, "'I didn't use a straight conversion of the mesh': from_mesh lost the sub-stud fins, so it rebuilt from measurements")},
    },
    "without_skill": {
        1: {"compared_with_photo": (False, "no measured comparison with the photo (outline trimmed to it, no score or overlay)"),
            "says_checked_in_software_only": (False, "only 'Checked structure: every brick locks into the rest'; no caveat that it is unbuilt")},
        2: {"model_passed": (True, "1x1 plates on a 48x48 baseplate: every plate held by its stud (checked by construction)"),
            "one_structure": (True, "all plates on one baseplate"),
            "grid_48_by_48": (True, "mosaic.json size 48")},
        3: {"audience_kids": (True, "booklet written for a 7-year-old (big numbers, tips, colour-coded sections)"),
            "at_most_4_parts_per_step": (False, "model.json pieces per step: up to 10 (32 steps for 165 pieces)")},
        4: {"declines_third_party_character": (True, "declines the replica, citing Lucasfilm/Disney"),
            "offers_original_alternative": (True, "builds an original 'Shadow Kabuto'")},
        5: {"explains_balance_fix": (True, "explains CoM ~19 mm past the foot; 8x16 plate base, 32 mm inside")},
        6: {"states_part_availability": (True, "'Studio's colour and price checks will show any that are hard to find'")},
        7: {"used_mesh_import": (True, "wrote its own STL voxelizer (src/voxelize.py) from the mesh"),
            "has_red_and_white": (True, "165 white, 82 red bricks")},
    },
}


# Per-iteration evidence where the responses changed (same judgement rules).
MANUAL_BY_ITERATION = {
    "iteration-2": {"with_skill": {
        1: {"compared_with_photo": (True, "ran compare: outline matches the photo at 90% IoU (target 80%)"),
            "says_checked_in_software_only": (True, "'checked in software only; nobody has built it yet'")},
        4: {"declines_third_party_character": (True, "'I can't make Darth Vader's helmet: it's a copyrighted film character design'"),
            "offers_original_alternative": (True, "original 'Nightwarden' helm")},
        5: {"explains_balance_fix": (True, "CoM 16 mm outside the 4x4 foot -> 16x8 plinth, 32 mm inside")},
        6: {"states_part_availability": (True, "'all 68 part-colour combos have appeared in real sets since 2005 (Rebrickable)'")},
        7: {"used_mesh_import": (False, "rebuilt from measurements: 'a straight voxel import ... came out lumpy' (the parity bug "
                                        "behind this was fixed after the run)")},
    }},
}


def main(it):
    evals = json.load(open(os.path.join(ROOT, "evals", "evals.json")))["evals"]
    for ev in evals:
        d = glob.glob(os.path.join(it, f"eval-{ev['id']}-*"))[0]
        for cfg in ("with_skill", "without_skill"):
            for run in sorted(glob.glob(os.path.join(d, cfg, "run-*"))) or [os.path.join(d, cfg)]:
                man = dict(MANUAL[cfg].get(ev["id"], {}))
                man.update(MANUAL_BY_ITERATION.get(os.path.basename(os.path.normpath(it)), {})
                           .get(cfg, {}).get(ev["id"], {}))
                res = grade_run(ev["id"], ev["name"], run, man)
                exp = [{"text": a, "passed": res[a][0], "evidence": res[a][1]} if a in res
                       else {"text": a, "passed": False, "evidence": "not graded"} for a in ev["assertions"]]
                k = sum(e["passed"] for e in exp)
                g = {"expectations": exp, "summary": {"passed": k, "failed": len(exp) - k, "total": len(exp),
                                                       "pass_rate": round(k / len(exp), 3)}}
                json.dump(g, open(os.path.join(run, "grading.json"), "w"), indent=1)
                print(f"eval {ev['id']} {cfg:14s} {k}/{len(exp)}  " +
                      " ".join(("+" if e["passed"] else "-") + e["text"] for e in exp))


if __name__ == "__main__":
    main(sys.argv[1])
