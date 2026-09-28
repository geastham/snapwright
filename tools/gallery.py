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
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "snapwright", "scripts"))

from snapwright.book import Book  # noqa: E402
from snapwright.catalog import Catalog  # noqa: E402
from snapwright.render import render_parts  # noqa: E402

OUT = os.path.join(ROOT, "docs", "gallery")
SEEDS = {"keep": 6, "lighthouse": 6}


def build(name):
    """name: an example (examples/<name>) or a folder path such as creations/creation-a."""
    d = os.path.join(ROOT, name) if os.path.isdir(os.path.join(ROOT, name)) and "/" in name \
        else os.path.join(ROOT, "examples", name)
    model = os.path.join(d, "out", "model.json")
    design = os.path.join(d, "design.py")
    if not os.path.exists(model) or os.path.getmtime(model) < os.path.getmtime(design):
        subprocess.run([sys.executable, os.path.join(ROOT, "skills", "snapwright", "scripts", "sw.py"), "build",
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
    path = os.path.join(OUT, "gallery.json")
    index = [e for e in (json.load(open(path)) if os.path.exists(path) else []) if e["example"] not in names]
    for name in names:
        m, out = build(name)
        slug, st = m["meta"]["slug"], m["stats"]
        cover(m, cat, os.path.join(OUT, f"{slug}.png"))
        # the gallery is served online: load three.js from the CDN (keeps each file under 1 MB)
        from snapwright.pipeline import write_viewer
        write_viewer(m, os.path.join(OUT, f"{slug}.html"), cat, embed_three=False)
        index.append({"example": name, "slug": slug, "title": m["meta"]["title"], "parts": st["parts"],
                      "height_cm": st["height_cm"], "steps": len({s["label"].split(".")[0] for s in m["steps"]}),
                      "passed": st["passed"]})
        print(f"{name}: {st['parts']:,} parts, {st['height_cm']} cm, {'PASS' if st['passed'] else 'FAIL'}")
    index = sorted(index, key=lambda e: e["example"])
    for e in index:
        e["blurb"] = BLURBS.get(e["slug"], "")
        d = os.path.join(ROOT, e["example"] if "/" in e["example"] else os.path.join("examples", e["example"]), "out")
        e["video"] = os.path.exists(os.path.join(d, f"{e['slug']}-build.mp4"))
    json.dump(index, open(path, "w"), indent=1)
    write_library(index)


# ---- the creations library: docs/gallery/index.html (GitHub Pages) -------------------------------
RELEASE = "https://github.com/geastham/snapwright/releases/download/library/"
ORDER = ["memorial-church", "lakeside-sail-tower", "harbour-lighthouse", "stone-keep", "signal-robot",
         "little-rocket"]
BLURBS = {
    "memorial-church": "Stanford's Memorial Church from the Main Quad. The gable mosaic is built from plate "
                       "edges: every pixel is a stud wide and a plate tall.",
    "lakeside-sail-tower": "A lakefront diorama, designed from two photos.",
    "harbour-lighthouse": "Slopes and rounds smooth the tapers.",
    "stone-keep": "Hollow walls with bracing inside.",
    "signal-robot": "Face and chest built sideways onto side studs.",
    "little-rocket": "Straight from an STL file.",
}


def release_files(slug, video=False):
    """The files a creation ships in the `library` release: (label, file name, hint)."""
    out = [("Instructions (PDF)", f"{slug}-instructions.pdf", "the book, ready to print"),
           ("BrickLink list", f"{slug}-bricklink.xml", "Want \u2192 Upload, then Buy All"),
           ("Parts list (CSV)", f"{slug}-parts.csv", "a spreadsheet with a link per part"),
           ("Rebrickable", f"{slug}-rebrickable.csv", "compare with what you own"),
           ("LDraw", f"{slug}.ldr", "Studio, LeoCAD, Mecabricks"),
           ("Offline 3D viewer", f"{slug}-viewer.html", "works without internet")]
    if video:
        out.append(("Build video", f"{slug}-build.mp4", "the model assembling itself"))
    return out


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Snapwright creations</title>
<meta name="description" content="Brick models designed with Snapwright: instruction books, 3D viewers and parts lists, free to download.">
<style>
:root{--bg:#f7f5f0;--card:#ffffff;--ink:#1f2a33;--soft:#5f686e;--line:#e6e1d6;--accent:#f58a1e;--accent-ink:#ffffff;--chip:#f1ede4}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#15191c;--card:#1e2428;--ink:#ecebe7;--soft:#a3abb0;--line:#2e363b;--accent:#f59e2e;--accent-ink:#15191c;--chip:#262d32}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
a{color:inherit}header{max-width:1120px;margin:0 auto;padding:40px 16px 8px;text-align:center}
header img{width:min(460px,90%);height:auto}header p{color:var(--soft);max-width:640px;margin:12px auto 0}
.nav{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin:18px 0 0}
.nav a{text-decoration:none;font-size:14px;padding:6px 12px;border:1px solid var(--line);border-radius:999px;background:var(--card)}
main{max-width:1120px;margin:0 auto;padding:24px 16px 56px;display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;overflow:hidden;display:flex;flex-direction:column;scroll-margin-top:16px}
.card:target{outline:3px solid var(--accent)}
.pic{background:#f3f0e8;height:280px;display:flex;align-items:center;justify-content:center;padding:14px;overflow:hidden}
.pic img{max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain}
.body{padding:16px 18px 18px;display:flex;flex-direction:column;gap:10px;flex:1}
h2{font-size:20px;margin:0}.meta{color:var(--soft);font-size:14px;margin:0}.blurb{margin:0;font-size:15px}
.open{display:inline-block;text-align:center;text-decoration:none;font-weight:600;background:var(--accent);color:var(--accent-ink);padding:10px 14px;border-radius:10px}
ul{list-style:none;margin:0;padding:0;display:grid;gap:6px}
li a{display:flex;justify-content:space-between;gap:10px;text-decoration:none;padding:8px 10px;border-radius:8px;background:var(--chip);font-size:14px}
li a span{color:var(--soft);font-size:13px;text-align:right}
footer{max-width:1120px;margin:0 auto;padding:0 16px 40px;color:var(--soft);font-size:13px;text-align:center}
</style></head><body>
<header>
<img src="../brand/snapwright-logo.svg" alt="Snapwright">
<p>Brick models designed with <a href="https://github.com/geastham/snapwright">Snapwright</a>, an open-source
Claude skill. Each one is checked in software: every part connects, nothing floats, it stands up, and every part
comes in the colour it asks for. Everything here is free to download.</p>
<div class="nav"><a href="https://github.com/geastham/snapwright/blob/main/docs/ordering.md">How to order the parts</a>
<a href="https://github.com/geastham/snapwright">Make your own</a></div>
</header>
<main>
__CARDS__
</main>
<footer>Unofficial fan designs. Not affiliated with, sponsored or endorsed by any brick manufacturer.
Books and files are free for personal use.</footer>
</body></html>
"""


def write_library(index):
    """docs/gallery/index.html: a card per creation with its 3D viewer and downloads."""
    import html
    by_slug = {e["slug"]: e for e in index}
    order = [s for s in ORDER if s in by_slug] + sorted(s for s in by_slug if s not in ORDER)
    cards = []
    for slug in order:
        e = by_slug[slug]
        links = "".join(f'<li><a href="{RELEASE}{f}" download>{html.escape(label)}<span>{html.escape(hint)}</span></a></li>'
                        for label, f, hint in release_files(slug, e.get("video")))
        cards.append(f"""<article class="card" id="{slug}">
<a class="pic" href="{slug}.html"><img src="{slug}.png" alt="{html.escape(e['title'])}" loading="lazy"></a>
<div class="body"><h2>{html.escape(e['title'])}</h2>
<p class="meta">{e['parts']:,} parts \u00b7 {e['height_cm']:g} cm tall \u00b7 {e['steps']} steps</p>
<p class="blurb">{html.escape(e.get('blurb', ''))}</p>
<a class="open" href="{slug}.html">Open in 3D</a>
<ul>{links}</ul></div></article>""")
    with open(os.path.join(OUT, "index.html"), "w") as f:
        f.write(PAGE.replace("__CARDS__", "\n".join(cards)))


if __name__ == "__main__":
    main(sys.argv[1:] or sorted(n for n in os.listdir(os.path.join(ROOT, "examples"))
                                if os.path.exists(os.path.join(ROOT, "examples", n, "design.py"))))
