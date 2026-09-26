"""The creation wizard's helpers: start a project folder, and check its reference images.

  sw.py new "Lakeside Sail Tower" [--dir .]      -> lakeside-sail-tower/ with brief.md,
                                                    reference/, design.py
  sw.py refs lakeside-sail-tower/ [--subject ..]  -> what the references show, masks,
                                                    colours, missing views and ready-to-paste
                                                    image-generation prompts for them

The flow the agent walks the user through is references/wizard.md.
"""
from __future__ import annotations

import json
import os
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .catalog import Catalog, hex_to_rgb
from .compare import load_reference

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")
# the views the likeness check and the designer use, most useful first
VIEWS = [
    ("view_front", "front", "azimuth 0", True),
    ("view_side", "side", "azimuth 90 or 270", True),
    ("view_three_quarter", "three-quarter", "azimuth 45, elevation 25", False),
    ("view_back", "back", "azimuth 180", False),
    ("view_top", "top", "straight down", False),
]

BRIEF = """# {title}

A Snapwright creation brief. The agent fills this in with you, one section at a time.

## 1. What it is
{subject}

## 2. Rights
Original / our own / generic / a real place / public domain: (one line)

## 3. Size and budget
Target height: __ cm (or a part budget). Standalone model or a diorama with ground?

## 4. Who builds it
Audience: kids / family / adult / expert. Finish: smooth tiles or studs.

## 5. Must-read features (3-5)
The things that make it recognisable, each at least 2 studs (16 mm) wide at this size.

## 6. Colours
Each region of the subject and the brick colour it becomes (`sw.py refs` suggests them).

## 7. Proportions
Where the main features sit, as fractions of the height and width (from the front view).

## 8. Structure
What stands on what; overhangs, thin parts, anything held or hung; a base or stand?

## 9. Outputs
Instruction book (PDF), 3D viewer, parts lists (BrickLink / Rebrickable), LDraw, build video.

## 10. Open questions
"""

DESIGN = '''# Snapwright design file for {title}. Units: x/z in studs (8 mm), y in plates (3.2 mm).
# The DSL is in the skill's references/design-dsl.md. Must define `model`.
model = Model(24, 24, 60, title="{title}", subtitle="", author="")
model.box(0, 0, 0, 24, 24, 2, "dark_bluish_gray")      # a base to start from
'''

REF_README = """Put reference images here.

- Photos: any names (photo_*.jpg is a good habit).
- Clean views, named so the tools can use them:
  view_front, view_side, view_three_quarter, view_back, view_top  (.png / .jpg / .webp)
  detail_<feature>  for close-ups of the features that matter.
- A plain, single-colour background gives a clean outline; `sw.py refs ..` makes the masks.

`sw.py refs <project>` reports which views are missing and prints image-generation prompts
for them.
"""


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "creation"


def new_project(title, parent=".", subject=""):
    """Create <parent>/<slug>/ with brief.md, reference/ and design.py. Returns the path."""
    path = os.path.join(parent, slugify(title))
    os.makedirs(os.path.join(path, "reference"), exist_ok=True)
    files = {"brief.md": BRIEF.format(title=title, subject=subject or "(one or two sentences)"),
             "design.py": DESIGN.format(title=title.replace('"', "'")),
             os.path.join("reference", "README.txt"): REF_README}
    for name, text in files.items():
        f = os.path.join(path, name)
        if not os.path.exists(f):                      # never overwrite the user's work
            with open(f, "w") as fh:
                fh.write(text)
    return path


def _role(name):
    stem = os.path.splitext(os.path.basename(name))[0].lower()
    for key, _, _, _ in VIEWS:
        if stem == key or stem.startswith(key + "_"):
            return key
    if stem.startswith(("view_right", "view_left")):
        return "view_side"
    if stem.startswith("detail_"):
        return "detail"
    return "photo"


def _colours(rgb, mask, cat, k=6):
    """The subject's main colours (share of its pixels) mapped to catalog colours."""
    px = rgb[mask]
    if len(px) < 50:
        return []
    im = Image.fromarray(px.reshape(1, -1, 3).astype(np.uint8))
    q = im.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    pal = np.array(q.getpalette()[: 3 * k]).reshape(-1, 3)
    counts = np.bincount(np.asarray(q).ravel(), minlength=k)
    out = {}
    for c, n in zip(pal, counts):
        if n:
            key = cat.nearest(tuple(int(v) for v in c))
            out[key] = out.get(key, 0) + int(n)
    tot = sum(out.values())
    return sorted(((key, round(n / tot, 3)) for key, n in out.items()), key=lambda kv: -kv[1])


def view_prompts(subject, missing):
    """Ready-to-paste prompts for an image generator, one per missing view."""
    subject = subject.strip().rstrip(".")
    common = (f"Subject: {subject}. Show ONLY the subject, whole and centred with about 10% margin, "
              "on a plain flat white background, no shadows, no other objects, no text or logos. "
              "Orthographic (straight-on, no perspective), flat even lighting, a clean simplified "
              "illustration style with flat colour regions. Keep exactly the proportions, colours "
              "and details of the attached reference images; add nothing new.")
    views = {"view_front": "the front, straight on",
             "view_side": "the side, straight on (a side elevation)",
             "view_three_quarter": "a three-quarter view from the front-right, slightly above",
             "view_back": "the back, straight on",
             "view_top": "straight down from above (a top/plan view)"}
    return {v: f"Draw {views[v]}. {common} Save as {v}.png." for v in missing if v in views}


def inspect_refs(project, subject=None, catalog=None, write=True):
    """Look at every reference image: role, outline (mask), background, subject aspect, colours.
    Writes reference/refs.json, masks for clean views and reference/contact_sheet.png.
    Returns the report dict."""
    cat = catalog or Catalog()
    ref = os.path.join(project, "reference")
    names = sorted(f for f in os.listdir(ref) if f.lower().endswith(IMAGE_EXT)
                   and not f.startswith(("mask_", "contact_sheet")))
    if subject is None:                                # the brief's first section, if written
        try:
            text = open(os.path.join(project, "brief.md")).read()
            m = re.search(r"## 1\. What it is\s*\n(.+?)\n\s*\n", text, re.S)
            subject = m.group(1).strip() if m and "(one or two" not in m.group(1) else None
        except OSError:
            subject = None
    items = []
    for f in names:
        path = os.path.join(ref, f)
        mask_path = os.path.join(ref, "mask_" + os.path.splitext(f)[0] + ".png")
        item = {"file": f, "role": _role(f)}
        try:
            rgb, mask, info = load_reference(path, mask_path if os.path.exists(mask_path) else None)
            ys, xs = np.nonzero(mask)
            item.update(outline=info["method"], warning=info["warning"],
                        subject_share=round(float(mask.mean()), 3),
                        aspect_h_over_w=round((int(np.ptp(ys)) + 1) / (int(np.ptp(xs)) + 1), 2),
                        colours=_colours(rgb, mask, cat))
            if write and info["method"] == "background" and not info["warning"] \
                    and item["role"].startswith("view_"):
                big = Image.open(path)
                Image.fromarray((mask * 255).astype(np.uint8)).resize(big.size, Image.NEAREST).save(mask_path)
                item["mask"] = os.path.basename(mask_path)
            elif os.path.exists(mask_path):
                item["mask"] = os.path.basename(mask_path)
            item["usable_for_likeness"] = item["role"].startswith("view_") and (
                "mask" in item or info["method"] in ("alpha", "mask"))
        except (ValueError, OSError) as e:
            item.update(outline=None, warning=str(e), usable_for_likeness=False)
        items.append(item)
    have = {i["role"] for i in items if i.get("usable_for_likeness")}
    missing = [v for v, _, _, _ in VIEWS if v not in have]
    needed = [v for v, _, _, req in VIEWS if req and v not in have]
    colours: dict = {}
    for i in items:
        for key, share in i.get("colours", []):
            colours[key] = colours.get(key, 0) + share
    tot = sum(colours.values()) or 1
    report = {"project": os.path.abspath(project), "subject": subject, "images": items,
              "views_ready": sorted(have), "views_missing": missing, "views_needed": needed,
              "colours": [(k, round(v / tot, 3)) for k, v in sorted(colours.items(), key=lambda kv: -kv[1])][:8],
              "prompts": view_prompts(subject or "the subject in the attached reference images", missing)}
    if write:
        with open(os.path.join(ref, "refs.json"), "w") as fh:
            json.dump(report, fh, indent=1)
        if items:
            contact_sheet(ref, items, cat).save(os.path.join(ref, "contact_sheet.png"))
    return report


def contact_sheet(ref, items, cat, cell=260):
    """Thumbnails with their role, outline and colour chips: one picture to check with the user."""
    cols = min(4, len(items))
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 58)), (247, 245, 240))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=14)
    except TypeError:
        font = ImageFont.load_default()
    for n, it in enumerate(items):
        x, y = (n % cols) * cell, (n // cols) * (cell + 58)
        im = Image.open(os.path.join(ref, it["file"])).convert("RGB")
        im.thumbnail((cell - 12, cell - 12))
        if it.get("mask"):                              # outline the silhouette in orange
            m = Image.open(os.path.join(ref, it["mask"])).convert("L").resize(im.size)
            edge = np.asarray(m) > 127
            e = edge ^ np.roll(edge, 1, 0) | edge ^ np.roll(edge, 1, 1)
            a = np.asarray(im).copy()
            a[e] = (245, 120, 20)
            im = Image.fromarray(a)
        sheet.paste(im, (x + 6, y + 6))
        ok = "ready" if it.get("usable_for_likeness") else ("photo" if it["role"] == "photo" else "needs a clean view")
        d.text((x + 8, y + cell - 2), f"{it['file'][:30]}  ({it['role']}, {ok})", fill=(40, 40, 40), font=font)
        for k, (key, share) in enumerate(it.get("colours", [])[:6]):
            d.rectangle([x + 8 + k * 40, y + cell + 20, x + 40 + k * 40, y + cell + 44],
                        fill=hex_to_rgb(cat.colors[key]["hex"]), outline=(90, 90, 90))
    return sheet


def report_text(r):
    """The refs report as plain lines for the terminal."""
    out = [f"{len(r['images'])} reference image(s) in {r['project']}/reference"]
    for i in r["images"]:
        cols = ", ".join(f"{k} {int(s * 100)}%" for k, s in i.get("colours", [])[:4])
        ok = "ready for the likeness check" if i.get("usable_for_likeness") else "photo / needs a clean view"
        out.append(f"  {i['file']}: {i['role']}, {ok}" + (f"; colours: {cols}" if cols else "")
                   + (f"; note: {i['warning']}" if i.get("warning") else ""))
    out.append("views ready: " + (", ".join(r["views_ready"]) or "none"))
    if r["views_missing"]:
        out.append("views missing: " + ", ".join(r["views_missing"])
                   + (f" (needed: {', '.join(r['views_needed'])})" if r["views_needed"] else ""))
        out.append("prompts for an image generator (attach the photos; one image per prompt):")
        for v, p in r["prompts"].items():
            out.append(f"  [{v}] {p}")
    if r["colours"]:
        out.append("suggested brick colours: " + ", ".join(f"{k} ({int(s * 100)}%)" for k, s in r["colours"]))
    out.append("contact sheet: reference/contact_sheet.png   report: reference/refs.json")
    return out
