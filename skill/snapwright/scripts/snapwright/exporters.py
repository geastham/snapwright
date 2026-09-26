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


# LDraw rotation per direction a slope's low side faces (our +x, +z, -x, -z). Native LDraw
# slopes face -Z, which is our +z because we write Z = -z.
SLOPE_MATRIX = {0: "0 0 -1 0 1 0 1 0 0", 1: "1 0 0 0 1 0 0 0 1",
                2: "0 0 1 0 1 0 -1 0 0", 3: "-1 0 0 0 1 0 0 0 -1"}
BOX_MATRIX = {0: "1 0 0 0 1 0 0 0 1", 1: "0 0 1 0 1 0 -1 0 0"}


def ldraw_line(p, t, col) -> str:
    """One LDraw type-1 line for part dict p (catalog type t, LDraw colour col).
    Mapping (x, y, z) -> (20x, -8y, -20z): 1 stud = 20 LDU, 1 plate = 8 LDU, -Y up."""
    x, z, y, dx, dz, h = p["x"], p["z"], p["y"], p["dx"], p["dz"], p["h"]
    if t.shape in ("slope", "slope_inv"):
        d = p.get("dir", 0)
        m = SLOPE_MATRIX[d]
        if t.ldraw_origin == "bottom":             # 30 degree 2/3-height: bottom centre
            X, Z, Y = (x + dx / 2) * 20, -(z + dz / 2) * 20, -y * 8
        else:                                      # top centre of the back (studded) row
            cx = {0: x + 0.5, 2: x + dx - 0.5}.get(d, x + dx / 2)
            cz = {1: z + 0.5, 3: z + dz - 0.5}.get(d, z + dz / 2)
            X, Z, Y = cx * 20, -cz * 20, -(y + h) * 8
    else:
        m = BOX_MATRIX[p["rot"] if t.shape == "box" else 0]
        X, Z, Y = (x + dx / 2) * 20, -(z + dz / 2) * 20, -(y + h) * 8
    return f"1 {col} {X:g} {Y:g} {Z:g} {m} {t.ldraw or t.id + '.dat'}\n"


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
            out.write(ldraw_line(p, catalog.by_id[p["part"]], catalog.colors[p["color"]]["ldraw"]))
        out.write("0 STEP\n")
    return out.getvalue()


def parse_ldraw(text, catalog):
    """Read an .ldr written by to_ldraw back into grid boxes (the inverse mapping).
    Returns [{part, color, x, z, y, dx, dz, h, rot, dir, step}]. Only handles the axis-aligned
    placements we write; used to check the export round-trips exactly."""
    by_ldraw = {c["ldraw"]: k for k, c in catalog.colors.items()}
    by_file = {t.ldraw.lower(): t for t in catalog.parts}
    slope_dir = {v: k for k, v in SLOPE_MATRIX.items()}
    box_rot = {v: k for k, v in BOX_MATRIX.items()}
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
        m = " ".join(str(int(float(v))) for v in f[5:14])
        t = by_file[f[14].lower()]
        rec = {"part": t.id, "color": by_ldraw[col], "step": step, "h": t.h}
        if t.shape in ("slope", "slope_inv"):
            d = slope_dir[m]
            dx, dz = (t.L, t.W) if d in (0, 2) else (t.W, t.L)
            cx, cz = X / 20, -Z / 20
            if t.ldraw_origin == "bottom":
                x, z, y = cx - dx / 2, cz - dz / 2, -Y / 8
            else:
                x = {0: cx - 0.5, 2: cx + 0.5 - dx}.get(d, cx - dx / 2)
                z = {1: cz - 0.5, 3: cz + 0.5 - dz}.get(d, cz - dz / 2)
                y = -Y / 8 - t.h
            rec.update(rot=d, dir=d)
        else:
            r = box_rot[m]
            dx, dz = (t.L, t.W) if r == 0 else (t.W, t.L)
            x, z, y = X / 20 - dx / 2, -Z / 20 - dz / 2, -Y / 8 - t.h
            rec.update(rot=r)
        rec.update(x=round(x), z=round(z), y=round(y), dx=dx, dz=dz)
        out.append(rec)
    return out


def to_bricklink_xml(parts, catalog) -> str:
    rows = [f"  <ITEM><ITEMTYPE>P</ITEMTYPE><ITEMID>{escape(catalog.by_id[pid].bricklink or pid)}</ITEMID>"
            f"<COLOR>{catalog.colors[c]['bricklink']}</COLOR><MINQTY>{q}</MINQTY></ITEM>"
            for pid, c, q in bom(parts)]
    return "<INVENTORY>\n" + "\n".join(rows) + "\n</INVENTORY>\n"


def to_rebrickable_csv(parts, catalog) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Part", "Color", "Quantity"])
    for pid, c, q in bom(parts):
        w.writerow([catalog.by_id[pid].rebrickable or pid, catalog.colors[c]["rebrickable"], q])
    return buf.getvalue()


def to_csv(parts, catalog) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Part ID", "Part", "Colour", "BrickLink colour ID", "Qty", "Availability"])
    for pid, c, q in bom(parts):
        w.writerow([pid, catalog.by_id[pid].name, catalog.colors[c]["name"],
                    catalog.colors[c]["bricklink"], q, catalog.available(pid, c)])
    return buf.getvalue()
