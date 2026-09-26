#!/usr/bin/env python3
"""Snapwright CLI.

  sw.py preview  design.py --out DIR            fast voxel renders (4 views) for design iteration
  sw.py build    design.py --out DIR [options]  full pipeline: parts, checks, steps, exports, viewer, book
                                                (--profile prints stage timings + a cProfile report)
  sw.py compare  design.py --ref PHOTO [--mask M] silhouette IoU from the best view + side by side
  sw.py viewer   model.json --out FILE          rebuild the 3D viewer from a model
  sw.py book     model.json --out FILE          rebuild the instruction PDF from a model
  sw.py sync-catalog [--key KEY]                refresh part-colour availability from Rebrickable
                                                (bulk downloads, or the API with a key; needs network)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from snapwright import pipeline  # noqa: E402
from snapwright.catalog import Catalog  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sw.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preview"); p.add_argument("design"); p.add_argument("--out", required=True)
    p.add_argument("--size", type=int, default=700)
    b = sub.add_parser("build"); b.add_argument("design"); b.add_argument("--out", required=True)
    b.add_argument("--seeds", type=int, default=8)
    b.add_argument("--finish", choices=["tiles", "studs"], default="tiles")
    b.add_argument("--audience", choices=["kids", "family", "adult", "expert"], default="adult")
    b.add_argument("--max-per-step", type=int)
    b.add_argument("--page", choices=["letter", "a4"], default="letter")
    b.add_argument("--no-book", action="store_true"); b.add_argument("--no-viewer", action="store_true")
    b.add_argument("--no-strict", action="store_true", help="write a draft book even if checks fail")
    b.add_argument("--base", choices=["auto", "off"], default="auto",
                   help="auto: stand a model that would tip on a 2-plate base (counted and reported)")
    b.add_argument("--no-shapes", action="store_true",
                   help="only bricks, plates and tiles: no slopes or round parts")
    b.add_argument("--profile", action="store_true",
                   help="print stage timings and write a cProfile report to OUT/profile.txt")
    cp = sub.add_parser("compare"); cp.add_argument("design"); cp.add_argument("--ref", required=True)
    cp.add_argument("--mask", help="black/white image of the subject, if the background is busy")
    cp.add_argument("--out", default="out/compare")
    v = sub.add_parser("viewer"); v.add_argument("model"); v.add_argument("--out", required=True)
    k = sub.add_parser("book"); k.add_argument("model"); k.add_argument("--out", required=True)
    k.add_argument("--page", choices=["letter", "a4"], default="letter")
    s = sub.add_parser("sync-catalog")
    s.add_argument("--key", default=os.environ.get("REBRICKABLE_KEY"),
                   help="use the Rebrickable API (else the free CSV downloads)")
    s.add_argument("--downloads", help="folder for the CSV downloads (default: assets/.rebrickable)")
    s.add_argument("--since", type=int, default=2005, help="count colours seen in sets from this year on")
    a = ap.parse_args(argv)

    if a.cmd == "preview":
        for path in pipeline.preview(a.design, a.out, size=a.size):
            print(path)
    elif a.cmd == "build":
        kw = dict(seeds=a.seeds, finish=a.finish, audience=a.audience, max_per_step=a.max_per_step,
                  book=not a.no_book, viewer=not a.no_viewer, page=a.page, strict=not a.no_strict,
                  shapes=not a.no_shapes, base=a.base)
        if a.profile:
            m = _profiled_build(a.design, a.out, kw)
        else:
            m = pipeline.build(a.design, a.out, **kw)
        sys.exit(0 if m["stats"]["passed"] else 2)
    elif a.cmd == "compare":
        pipeline.compare(a.design, a.ref, a.out, mask=a.mask)
    elif a.cmd == "viewer":
        pipeline.write_viewer(pipeline.load_model(a.model), a.out)
    elif a.cmd == "book":
        from snapwright.book import Book
        Book(pipeline.load_model(a.model), Catalog(), a.out, page=a.page).build()
    elif a.cmd == "sync-catalog":
        from snapwright.sync import sync
        sync(a.key, downloads=a.downloads, since=a.since)


def _profiled_build(design, out, kw):
    import cProfile
    import io
    import pstats
    timer = pipeline.Timer()
    prof = cProfile.Profile()
    m = prof.runcall(pipeline.build, design, out, timer=timer, **kw)
    print(timer.report())
    buf = io.StringIO()
    st = pstats.Stats(prof, stream=buf).sort_stats("cumulative")
    st.print_stats(40)
    st.sort_stats("tottime").print_stats(25)
    path = os.path.join(out, "profile.txt")
    with open(path, "w") as f:
        f.write(timer.report() + "\n\n" + buf.getvalue())
    print(f"profile -> {path}")
    return m


if __name__ == "__main__":
    main()
