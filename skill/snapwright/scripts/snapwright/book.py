"""Instruction book: cover, parts inventory, numbered steps with per-step part callouts,
turn-the-model cues, a finished-model page with the software checks, and a disclaimer.

The visual language is deliberately our own (typography, colours, layout) rather than an
imitation of any manufacturer's official instruction style.
"""
from __future__ import annotations

import os
from collections import Counter

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter, A4
from PIL import Image
from reportlab import rl_config
from reportlab.pdfgen import canvas

from .pdfimage import draw_indexed
from .render import part_icon, render_parts
from .validate import report_lines

INK = HexColor("#1d2327")
SOFT = HexColor("#6b7479")
LINE = HexColor("#d9dcde")
ACC = HexColor("#ff4628")
PAPER = HexColor("#fbfaf7")
INSET = HexColor("#f1f4f6")
STEP_PX = 520          # step renders: ~140 dpi at their printed size


def _img(pil):
    """Flatten a render onto the paper colour (images go into the PDF as indexed colour)."""
    bg = Image.new("RGBA", pil.size, (251, 250, 247, 255))
    bg.alpha_composite(pil.convert("RGBA"))
    return bg.convert("RGB")


class Book:
    def __init__(self, model, catalog, path, page="letter", log=print):
        self.m, self.cat, self.path, self.log = model, catalog, path, log
        self.W, self.H = letter if page == "letter" else A4
        rl_config.useA85 = 0   # binary Flate streams: ASCII85 only adds 25% to every page
        self.c = canvas.Canvas(path, pagesize=(self.W, self.H), pageCompression=1)
        self.c.setTitle(model["meta"]["title"])
        self.c.setAuthor(model["meta"].get("author") or "")
        self.page_no = 0
        parts = model["parts"]
        self.shape = tuple(model["grid"]["shape"])
        self.colors = {p["id"]: catalog.colors[p["color"]]["hex"] for p in parts}
        self.studs = {p["id"]: p["studs"] for p in parts}
        self._icons = {}
        from .snot import PanelSpec
        self.subs = {}
        for sb in model.get("subassemblies", []):
            self.subs[sb["name"]] = {"spec": PanelSpec.from_json(sb["spec"]), "parts": sb["parts"],
                                     "grid": tuple(sb["grid"]),
                                     "colors": {q["id"]: catalog.colors[q["color"]]["hex"] for q in sb["parts"]}}
        self.attach_at = {st["sub"]: st["n"] for st in model["steps"] if st.get("kind") == "attach"}
        self.pal = self._palette()

    def _palette(self):
        """Every colour the renderer draws for this model (face shades, studs, edges, accent,
        paper): images are stored in exactly these colours."""
        from .render import ACCENT, _edge_col, _lift, _shade
        from .catalog import hex_to_rgb
        out = {(251, 250, 247), ACCENT, (255, 255, 255), (107, 116, 121)}
        for key in {p["color"] for p in self.all_parts()}:
            b = hex_to_rgb(self.cat.colors[key]["hex"])
            out |= {b, _lift(b, 0.12), _lift(b, 0.04), _lift(b, 0.22), _shade(b, 0.62), _shade(b, 0.8),
                    _shade(b, 0.72), _edge_col(b)}
        return sorted(out)

    def all_parts(self):
        return self.m["parts"] + [q for sb in self.subs.values() for q in sb["parts"]]

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

    def render(self, upto, highlight=(), view=0, px=760, sub=None, attach=None):
        """The model after step `upto` from quarter view `view`. sub: draw that panel on its own
        (it is built flat); attach: highlight that panel on the model."""
        if sub:
            sb = self.subs[sub]
            shown = [q for q in sb["parts"] if q.get("step", 0) <= upto]
            im = render_parts(shown, sb["grid"], sb["colors"], self.cat, view=view,
                              highlight=set(highlight), size=(px, px))
        else:
            shown = [p for p in self.m["parts"] if p.get("step", 0) <= upto]
            top = max((p["y"] + p["h"] for p in shown), default=1)
            NX, NZ, NY = self.shape
            panels = [dict(spec=sb["spec"], parts=sb["parts"], colors=sb["colors"], hl=(name == attach))
                      for name, sb in self.subs.items() if self.attach_at.get(name, 10 ** 9) <= upto]
            if panels:
                top = max(top, max(pn["spec"].top for pn in panels))
            frame = (NX, NZ, int(min(NY, max(NY * 0.25, top + 9))))
            im = render_parts(shown, self.shape, self.colors, self.cat, view=view, panels=panels,
                              highlight=set(highlight), size=(px, px), framing=frame)
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
        draw_indexed(c, self.render(n, view=0, px=1100), 36, 150, W - 72, W - 72, palette=self.pal)
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
        rows = Counter((p["part"], p["color"]) for p in self.all_parts())
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
                draw_indexed(c, self.icon(pid, col), x, y + 14, 70, 55)
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
        prev = {None: 0}                 # last view, per main model / per panel
        for s0 in range(0, len(steps), per_page):
            self._page()
            c = self.c
            for k, st in enumerate(steps[s0:s0 + per_page]):
                r, cc = divmod(k, 2)
                x0, y0 = 36 + cc * cw, self.H - 50 - (r + 1) * chh
                kind, sub = st.get("kind"), st.get("sub")
                if kind == "subassembly":         # a panel built on its own: boxed inset
                    c.setFillColor(INSET)
                    c.setStrokeColor(ACC)
                    c.setLineWidth(1.2)
                    c.roundRect(x0 + 4, y0 + 4, cw - 8, chh - 8, 8, stroke=1, fill=1)
                    c.setFillColor(ACC)
                    c.setFont("Helvetica-Bold", 8)
                    c.drawRightString(x0 + cw - 14, y0 + chh - 20, f"SUB-BUILD: {sub.upper()}")
                else:
                    c.setStrokeColor(LINE)
                    c.setLineWidth(0.6)
                    c.rect(x0 + 4, y0 + 4, cw - 8, chh - 8, stroke=1, fill=0)
                pool = self.subs[sub]["parts"] if kind == "subassembly" else parts
                cnt = Counter((pool[i]["part"], pool[i]["color"]) for i in st["parts"])
                per_row = max(1, int((cw - 80) // 44))
                rows = min(2, -(-len(cnt) // per_row)) if cnt else 1
                img_h = chh - 60 - rows * 46
                if kind == "attach":
                    im = self.render(st["n"], (), st["view"], px=STEP_PX, attach=sub)
                elif kind == "subassembly":
                    im = self.render(st["n"], st["parts"], st["view"], px=STEP_PX, sub=sub)
                else:
                    im = self.render(st["n"], st["parts"], st["view"], px=STEP_PX)
                draw_indexed(c, im, x0 + 14, y0 + 12, cw - 28, img_h, preserveAspectRatio=True, anchor="c",
                             palette=self.pal)
                c.setFillColor(INK)
                c.setFont("Helvetica-Bold", 26)
                c.drawString(x0 + 14, y0 + chh - 40, str(st["n"]))
                # callout: new parts this step, up to two rows
                items = sorted(cnt.items())
                shown = items[:per_row * 2]
                for j, ((pid, col), q) in enumerate(shown):
                    r2, c2 = divmod(j, per_row)
                    ix, iy = x0 + 60 + c2 * 44, y0 + chh - 50 - r2 * 46
                    draw_indexed(c, self.icon(pid, col), ix, iy, 40, 31)
                    c.setFont("Helvetica-Bold", 8)
                    c.setFillColor(INK)
                    c.drawString(ix + 2, iy - 8, f"{q}x")
                if len(items) > len(shown):
                    c.setFont("Helvetica", 8)
                    c.drawString(x0 + 60, y0 + chh - 150, f"+{len(items) - len(shown)} more")
                key = sub if kind == "subassembly" else None
                last = prev.get(key, 0)
                if st["view"] != last:
                    self._turn(x0 + 14, y0 + chh - 90, (st["view"] - last) % 4)
                prev[key] = st["view"]
                if kind == "attach":
                    c.setFont("Helvetica-Bold", 10)
                    c.setFillColor(INK)
                    c.drawString(x0 + 60, y0 + chh - 34, f"Attach the {sub} panel")
                    c.setFont("Helvetica", 8.5)
                    c.setFillColor(SOFT)
                    c.drawString(x0 + 60, y0 + chh - 48, "Tip it up and press it onto the side studs.")
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
        report = report_lines(st)
        # the checks block sits above the footer notes; the four views get what's left
        y = 62 + 13 * len(report)
        s = min((self.W - 90) / 2, (self.H - 80 - (y + 18)) / 2)
        x0 = (self.W - (2 * s + 18)) / 2
        for k in range(4):
            r, cc = divmod(k, 2)
            draw_indexed(c, self.render(n, view=k, px=700), x0 + cc * (s + 18), self.H - 80 - (r + 1) * s,
                         s, s, palette=self.pal)
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(INK)
        c.drawString(36, y, "Checked in software")
        for i, (kind, t) in enumerate(report):
            c.setFont("Helvetica-Bold" if kind == "fail" else "Helvetica", 9)
            c.setFillColor({"change": ACC, "fail": ACC, "note": SOFT}.get(kind, INK))
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
