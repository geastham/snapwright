#!/usr/bin/env python3
"""Dev-only: build the README gallery (docs/gallery/): a cover render and the 3D viewer per
example, plus gallery.json with the headline numbers. The viewers are served by GitHub Pages
from docs/, so the README can link to them.

  python tools/gallery.py [example ...]      (default: every folder in examples/)

Builds each example into examples/<name>/out first if its model.json is missing or older than
its design file.
"""
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skill", "snapwright", "scripts"))

from snapwright.book import Book  # noqa: E402
from snapwright.catalog import Catalog  # noqa: E402
from snapwright.render import render_parts  # noqa: E402

OUT = os.path.join(ROOT, "docs", "gallery")
SEEDS = {"keep": 6, "lighthouse": 6}


def build(name):
    d = os.path.join(ROOT, "examples", name)
    model = os.path.join(d, "out", "model.json")
    design = os.path.join(d, "design.py")
    if not os.path.exists(model) or os.path.getmtime(model) < os.path.getmtime(design):
        subprocess.run([sys.executable, os.path.join(ROOT, "skill", "snapwright", "scripts", "sw.py"), "build",
                        design, "--out", os.path.join(d, "out"), "--seeds", str(SEEDS.get(name, 8))], check=True)
    return json.load(open(model)), os.path.join(d, "out")


def cover(m, cat, path, px=900):
    """The finished model from the book's cover view, cropped, on a transparent background."""
    b = Book(m, cat, os.devnull, log=lambda *a: None)
    panels = [dict(spec=sb["spec"], parts=sb["parts"], colors=sb["colors"], hl=False) for sb in b.subs.values()]
    im = render_parts(m["parts"], b.shape, b.colors, cat, view=0, panels=panels, size=(px, px))
    im.crop(im.getbbox()).save(path, optimize=True)


def main(names):
    cat = Catalog()
    os.makedirs(OUT, exist_ok=True)
    index = []
    for name in names:
        m, out = build(name)
        slug, st = m["meta"]["slug"], m["stats"]
        cover(m, cat, os.path.join(OUT, f"{slug}.png"))
        shutil.copy(os.path.join(out, f"{slug}-viewer.html"), os.path.join(OUT, f"{slug}.html"))
        index.append({"example": name, "slug": slug, "title": m["meta"]["title"], "parts": st["parts"],
                      "height_cm": st["height_cm"], "steps": len({s["label"].split(".")[0] for s in m["steps"]}),
                      "passed": st["passed"]})
        print(f"{name}: {st['parts']:,} parts, {st['height_cm']} cm, {'PASS' if st['passed'] else 'FAIL'}")
    json.dump(index, open(os.path.join(OUT, "gallery.json"), "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1:] or sorted(n for n in os.listdir(os.path.join(ROOT, "examples"))
                                if os.path.exists(os.path.join(ROOT, "examples", n, "design.py"))))
