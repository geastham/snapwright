"""File exports: LDraw (.ldr with STEPs), BrickLink wanted list, Rebrickable CSV, plain CSV.

LDraw conventions: 1 stud = 20 LDU, 1 plate = 8 LDU, -Y is up, part origin at the top
centre of the part. We map (x, y, z) -> (x, -y, -z), which is a proper rotation, so the
model is not mirrored. Long axis along X is identity; along Z is a 90 degree turn about Y.
"""
from __future__ import annotations

import csv
import io
from collections import Counter
from xml.sax.saxutils import escape


def bom(parts):
    """[(part_id, color_key, qty)] sorted by colour then part."""
    c = Counter((p["part"], p["color"]) for p in parts)
    return sorted(((k[0], k[1], q) for k, q in c.items()), key=lambda r: (r[1], r[0]))


def to_ldraw(model, catalog) -> str:
    parts, steps = model["parts"], model["steps"]
    meta = model["meta"]
    out = io.StringIO()
    out.write(f"0 {meta['title']}\n0 Name: {meta.get('slug', 'model')}.ldr\n")
    out.write(f"0 Author: {meta.get('author') or 'Snapwright'}\n")
    out.write("0 Unofficial fan design generated with Snapwright. Not affiliated with any brick manufacturer.\n")
    for st in steps:
        for pid in st["parts"]:
            p = parts[pid]
            col = catalog.colors[p["color"]]["ldraw"]
            X = (p["x"] + p["dx"] / 2) * 20
            Z = -(p["z"] + p["dz"] / 2) * 20
            Y = -(p["y"] + p["h"]) * 8
            m = "1 0 0 0 1 0 0 0 1" if p["rot"] == 0 else "0 0 1 0 1 0 -1 0 0"
            out.write(f"1 {col} {X:g} {Y:g} {Z:g} {m} {p['part']}.dat\n")
        out.write("0 STEP\n")
    return out.getvalue()


def to_bricklink_xml(parts, catalog) -> str:
    rows = [f"  <ITEM><ITEMTYPE>P</ITEMTYPE><ITEMID>{escape(pid)}</ITEMID>"
            f"<COLOR>{catalog.colors[c]['bricklink']}</COLOR><MINQTY>{q}</MINQTY></ITEM>"
            for pid, c, q in bom(parts)]
    return "<INVENTORY>\n" + "\n".join(rows) + "\n</INVENTORY>\n"


def to_rebrickable_csv(parts, catalog) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Part", "Color", "Quantity"])
    for pid, c, q in bom(parts):
        w.writerow([pid, catalog.colors[c]["rebrickable"], q])
    return buf.getvalue()


def to_csv(parts, catalog) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Part ID", "Part", "Colour", "BrickLink colour ID", "Qty", "Availability"])
    for pid, c, q in bom(parts):
        w.writerow([pid, catalog.by_id[pid].name, catalog.colors[c]["name"],
                    catalog.colors[c]["bricklink"], q, catalog.available(pid, c)])
    return buf.getvalue()
