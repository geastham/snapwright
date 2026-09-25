"""Instruction book: cover, parts inventory, numbered steps with per-step part callouts,
turn-the-model cues, a finished-model page with the software checks, and a disclaimer.

The visual language is deliberately our own (typography, colours, layout) rather than an
imitation of any manufacturer's official instruction style.
"""
from __future__ import annotations

import io
import os
from collections import Counter

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .render import model_grid, part_icon, render_grid

INK = HexColor("#1d2327")
SOFT = HexColor("#6b7479")
LINE = HexColor("#d9dcde")
ACC = HexColor("#ff4628")
PAPER = HexColor("#fbfaf7")


def _img(pil, colors=96):
    bg = __import__("PIL.Image", fromlist=["Image"]).new("RGBA", pil.size, (251, 250, 247, 255))
    bg.alpha_composite(pil.convert("RGBA"))
    b = io.BytesIO()
    bg.convert("RGB").quantize(colors, dither=0).save(b, "PNG", optimize=True)
    b.seek(0)
    return ImageReader(b)


class Book:
    def __init__(self, model, catalog, path, page="letter", log=print):
        self.m, self.cat, self.path, self.log = model, catalog, path, log
        self.W, self.H = letter if page == "letter" else A4
        self.c = canvas.Canvas(path, pagesize=(self.W, self.H))
        self.c.setTitle(model["meta"]["title"])
        self.c.setAuthor(model["meta"].get("author") or "")
        self.page_no = 0
        parts = model["parts"]
        self.shape = tuple(model["grid"]["shape"])
        self.colors = {p["id"]: catalog.colors[p["color"]]["hex"] for p in parts}
        self.studs = {p["id"]: p["studs"] for p in parts}
        self._icons = {}

    # ---- chrome -------------------------------------------------------
    def _page(self, footer=True):
        c = self.c
        if self.page_no:
            c.showPage()
        self.page_no += 1
        c.setFillColor(PAPER)
        c.rect(0, 0, self.W, self.H, stroke=0, fill=1)
        if footer and self.page_no > 1:
            c.setFont("Helvetica", 8)
            c.setFillColor(SOFT)
            c.drawString(36, 22, self.m["meta"]["title"])
            c.drawRightString(self.W - 36, 22, str(self.page_no))

    def icon(self, part_id, color):
        k = (part_id, color)
        if k not in self._icons:
            self._icons[k] = _img(part_icon(self.cat.by_id[part_id], self.cat.colors[color]["hex"]))
        return self._icons[k]

    def render(self, upto, highlight=(), view=0, px=760):
        G = model_grid(self.m["parts"], self.shape, upto_step=upto)
        built = [p["y"] + p["h"] for p in self.m["parts"] if p.get("step", 0) <= upto]
        top = max(built) if built else 1
        NX, NZ, NY = self.shape
        frame = (NX, NZ, int(min(NY, max(NY * 0.25, top + 9))))
        im = render_grid(G, self.colors, self.studs, highlight=set(highlight), view=view,
                         size=(px, px), framing=frame)
        bb = im.getbbox()
        if bb:  # crop to the model with a small margin; placement keeps the aspect ratio
            m = int(px * 0.03)
            im = im.crop((max(0, bb[0] - m), max(0, bb[1] - m), min(px, bb[2] + m), min(px, bb[3] + m)))
        return _img(im)

    # ---- pages --------------------------------------------------------
    def cover(self):
        self._page(footer=False)
        c, W, H, meta, st = self.c, self.W, self.H, self.m["meta"], self.m["stats"]
        n = len(self.m["steps"])
        c.drawImage(self.render(n, view=0, px=1100), 36, 150, W - 72, W - 72, mask="auto")
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 34)
        c.drawString(40, H - 78, meta["title"])
        if meta.get("subtitle"):
            c.setFont("Helvetica", 13)
            c.setFillColor(SOFT)
            c.drawString(42, H - 100, meta["subtitle"])
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(INK)
        line = (f"{st['parts']:,} parts   ·   {st['height_cm']} cm tall   ·   {n} steps   ·   "
                f"{st['unique_lots']} lots")
        c.drawString(42, 120, line)
        c.setFont("Helvetica", 8)
        c.setFillColor(SOFT)
        c.drawString(42, 100, meta.get("disclaimer", ""))
        if meta.get("author"):
            c.drawString(42, 88, f"Design: {meta['author']}")

    def inventory(self):
        rows = Counter((p["part"], p["color"]) for p in self.m["parts"])
        items = sorted(rows.items(), key=lambda kv: (kv[0][1], kv[0][0]))
        cols, cw, ch = 3, (self.W - 72) / 3, 74
        per_page = cols * int((self.H - 150) // ch)
        for start in range(0, len(items), per_page):
            self._page()
            c = self.c
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 18)
            c.drawString(36, self.H - 56, "Parts" if start == 0 else "Parts (continued)")
            for k, ((pid, col), q) in enumerate(items[start:start + per_page]):
                r, cc = divmod(k, cols)
                x, y = 36 + cc * cw, self.H - 90 - (r + 1) * ch
                c.drawImage(self.icon(pid, col), x, y + 14, 70, 55, mask="auto")
                c.setFillColor(INK)
                c.setFont("Helvetica-Bold", 12)
                c.drawString(x + 74, y + 48, f"{q}x")
                c.setFont("Helvetica", 7.5)
                c.setFillColor(SOFT)
                c.drawString(x + 74, y + 36, self.cat.by_id[pid].name)
                c.drawString(x + 74, y + 26, f"{self.cat.colors[col]['name']} · #{pid}")

    def steps(self):
        steps = self.m["steps"]
        parts = self.m["parts"]
        per_page = 4
        cw, chh = (self.W - 72) / 2, (self.H - 90) / 2
        prev_view = 0
        for s0 in range(0, len(steps), per_page):
            self._page()
            c = self.c
            for k, st in enumerate(steps[s0:s0 + per_page]):
                r, cc = divmod(k, 2)
                x0, y0 = 36 + cc * cw, self.H - 50 - (r + 1) * chh
                c.setStrokeColor(LINE)
                c.setLineWidth(0.6)
                c.rect(x0 + 4, y0 + 4, cw - 8, chh - 8, stroke=1, fill=0)
                cnt = Counter((parts[i]["part"], parts[i]["color"]) for i in st["parts"])
                per_row = max(1, int((cw - 80) // 44))
                rows = min(2, -(-len(cnt) // per_row))
                img_h = chh - 60 - rows * 46
                c.drawImage(self.render(st["n"], st["parts"], st["view"], px=620), x0 + 14, y0 + 12,
                            cw - 28, img_h, mask="auto", preserveAspectRatio=True, anchor="c")
                c.setFillColor(INK)
                c.setFont("Helvetica-Bold", 26)
                c.drawString(x0 + 14, y0 + chh - 40, str(st["n"]))
                # callout: new parts this step, up to two rows
                items = sorted(cnt.items())
                shown = items[:per_row * 2]
                for j, ((pid, col), q) in enumerate(shown):
                    r2, c2 = divmod(j, per_row)
                    ix, iy = x0 + 60 + c2 * 44, y0 + chh - 50 - r2 * 46
                    c.drawImage(self.icon(pid, col), ix, iy, 40, 31, mask="auto")
                    c.setFont("Helvetica-Bold", 8)
                    c.setFillColor(INK)
                    c.drawString(ix + 2, iy - 8, f"{q}x")
                if len(items) > len(shown):
                    c.setFont("Helvetica", 8)
                    c.drawString(x0 + 60, y0 + chh - 150, f"+{len(items) - len(shown)} more")
                if st["view"] != prev_view:
                    self._turn(x0 + 14, y0 + chh - 90, (st["view"] - prev_view) % 4)
                prev_view = st["view"]
                if st.get("kind") == "overhang":
                    c.setFont("Helvetica-Oblique", 8)
                    c.setFillColor(SOFT)
                    c.drawString(x0 + 14, y0 + 16, "Press these on from underneath.")
            self.log(f"  book: steps {s0 + 1}-{min(s0 + per_page, len(steps))} of {len(steps)}")

    def _turn(self, x, y, quarters):
        c = self.c
        c.setStrokeColor(ACC)
        c.setFillColor(ACC)
        c.setLineWidth(2.2)
        c.arc(x, y, x + 30, y + 30, 20, 280)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(x + 15, y + 11, {1: "90°", 2: "180°", 3: "90°"}[quarters])

    def finale(self):
        self._page()
        c, st = self.c, self.m["stats"]
        n = len(self.m["steps"])
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(36, self.H - 56, "Finished")
        s = (self.W - 90) / 2
        for k in range(4):
            r, cc = divmod(k, 2)
            c.drawImage(self.render(n, view=k, px=700), 36 + cc * (s + 18), self.H - 80 - (r + 1) * s,
                        s, s, mask="auto")
        y = self.H - 100 - 2 * s
        c.setFont("Helvetica-Bold", 10)
        c.drawString(36, y, "Checked in software")
        c.setFont("Helvetica", 9)
        lines = [
            f"{st['parts']:,} parts, {st['connections']:,} stud connections, {st['structures']} structure",
            f"{st['collisions']} collisions, {st['floating']} floating parts, {len(st['weak_parts'])} single-stud joints",
            f"Centre of mass {st['com_margin_mm']} mm inside the base footprint",
            f"About {st['mass_g'] / 1000:.2f} kg, {st['width_cm']} x {st['depth_cm']} x {st['height_cm']} cm (estimated)",
        ]
        if st.get("recolored_cells") or st.get("trimmed_cells"):
            lines.append(f"Auto-repairs: {st.get('recolored_cells', 0)} surface cells recoloured, "
                         f"{st.get('trimmed_cells', 0)} overhang cells trimmed")
        if st.get("unverified_combos"):
            lines.append(f"{len(st['unverified_combos'])} part-colour combos not yet verified against a parts catalog")
        for i, t in enumerate(lines):
            c.drawString(36, y - 16 - i * 13, t)
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(SOFT)
        c.drawString(36, 44, "Verified on a computer only. Clutch strength and handling are untested until someone builds it.")
        c.drawString(36, 32, self.m["meta"].get("disclaimer", ""))

    def build(self):
        self.cover()
        self.inventory()
        self.steps()
        self.finale()
        self.c.save()
        return self.path
