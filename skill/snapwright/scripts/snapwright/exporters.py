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


def parse_ldraw(text, catalog):
    """Read an .ldr written by to_ldraw back into grid boxes (the inverse mapping).
    Returns [{part, color, x, z, y, dx, dz, h, rot, step}]. Only handles the axis-aligned
    placements we write; used to check the export round-trips exactly."""
    by_ldraw = {c["ldraw"]: k for k, c in catalog.colors.items()}
    out, step = [], 1
    for line in text.splitlines():
        f = line.split()
        if not f:
            continue
        if f[0] == "0" and len(f) > 1 and f[1] == "STEP":
            step += 1
            continue
        if f[0] != "1":
            continue
        col, X, Y, Z = int(f[1]), float(f[2]), float(f[3]), float(f[4])
        m = [float(v) for v in f[5:14]]
        pid = f[14][:-4] if f[14].endswith(".dat") else f[14]
        t = catalog.by_id[pid]
        if m == [1, 0, 0, 0, 1, 0, 0, 0, 1]:
            dx, dz, rot = t.L, t.W, 0
        elif m == [0, 0, 1, 0, 1, 0, -1, 0, 0]:
            dx, dz, rot = t.W, t.L, 1
        else:
            raise ValueError(f"unsupported rotation in: {line}")
        out.append({"part": pid, "color": by_ldraw[col], "rot": rot, "step": step,
                    "x": round(X / 20 - dx / 2), "z": round(-Z / 20 - dz / 2),
                    "y": round(-Y / 8) - t.h, "dx": dx, "dz": dz, "h": t.h})
    return out


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
