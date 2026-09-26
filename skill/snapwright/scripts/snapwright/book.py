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
        if any("label" not in st or "bag" not in st for st in model["steps"]):
            from .steps import label_and_bag
            label_and_bag(model["steps"])
        self.bags = max((st["bag"] for st in model["steps"]), default=1)
        self.numbered = len({(st["label"].split(".")[0]) for st in model["steps"]})

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
        bags = f"   ·   {self.bags} bags" if self.bags > 1 else ""
        line = (f"{st['parts']:,} parts   ·   {st['height_cm']} cm tall   ·   {self.numbered} steps{bags}   ·   "
                f"{st['unique_lots']} lots")
        c.drawString(42, 120, line)
        c.setFont("Helvetica", 8)
        c.setFillColor(SOFT)
        c.drawString(42, 100, meta.get("disclaimer", ""))
        if meta.get("author"):
            c.drawString(42, 88, f"Design: {meta['author']}")

    def inventory(self):
        self._parts_pages(Counter((p["part"], p["color"]) for p in self.all_parts()), "Parts")

    def _parts_pages(self, rows, title, subtitle=None, dense=False):
        """Grid of part icons with quantity, name, colour name and part number."""
        items = sorted(rows.items(), key=lambda kv: (kv[0][1], kv[0][0]))
        cols, ch = (4, 58) if dense else (3, 74)
        cw = (self.W - 72) / cols
        iw, ih = (52, 41) if dense else (70, 55)
        top = 110 if subtitle else 90
        per_page = cols * int((self.H - top - 60) // ch)
        for start in range(0, len(items), per_page):
            self._page()
            c = self.c
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 18)
            c.drawString(36, self.H - 56, title if start == 0 else f"{title} (continued)")
            if subtitle:
                c.setFont("Helvetica", 10)
                c.setFillColor(SOFT)
                c.drawString(36, self.H - 74, subtitle)
            for k, ((pid, col), q) in enumerate(items[start:start + per_page]):
                r, cc = divmod(k, cols)
                x, y = 36 + cc * cw, self.H - top - (r + 1) * ch
                draw_indexed(c, self.icon(pid, col), x, y + 14, iw, ih)
                tx = x + iw + 4
                c.setFillColor(INK)
                c.setFont("Helvetica-Bold", 11 if dense else 12)
                c.drawString(tx, y + ih - 4, f"{q}x")
                c.setFont("Helvetica", 6.5 if dense else 7.5)
                c.setFillColor(SOFT)
                c.drawString(tx, y + ih - 15, self.cat.by_id[pid].name)
                c.drawString(tx, y + ih - 24, f"{self.cat.colors[col]['name']} · #{pid}")

    def _bag_page(self, bag, steps):
        rows = Counter()
        for st in steps:
            pool = self.subs[st["sub"]]["parts"] if st.get("kind") == "subassembly" else self.m["parts"]
            rows.update((pool[i]["part"], pool[i]["color"]) for i in st["parts"])
        first, last = steps[0]["label"].split(".")[0], steps[-1]["label"].split(".")[0]
        self._parts_pages(rows, f"Bag {bag}", f"{sum(rows.values())} parts for steps {first} to {last}. "
                                              f"Find these first.", dense=True)

    def _progress(self, done, total, bag):
        c = self.c
        x0, x1, y = 120, self.W - 90, 35
        c.setStrokeColor(LINE)
        c.setLineWidth(3)
        c.line(x0, y, x1, y)
        c.setStrokeColor(ACC)
        c.line(x0, y, x0 + (x1 - x0) * done / max(1, total), y)
        c.setFont("Helvetica", 7)
        c.setFillColor(SOFT)
        c.drawRightString(x0 - 8, y - 2.5, f"Bag {bag} of {self.bags}" if self.bags > 1 else "")

    def steps(self):
        steps = self.m["steps"]
        parts = self.m["parts"]
        per_page = 4
        cw, chh = (self.W - 72) / 2, (self.H - 90) / 2
        prev = {None: 0}                 # last view, per main model / per panel
        pages = []                       # (bag, [steps]) with a new page at every bag
        for st in steps:
            if not pages or pages[-1][0] != st["bag"] or len(pages[-1][1]) == per_page:
                pages.append((st["bag"], []))
            pages[-1][1].append(st)
        shown_bag = None
        for bag, page_steps in pages:
            if self.bags > 1 and bag != shown_bag:
                self._bag_page(bag, [st for st in steps if st["bag"] == bag])
                shown_bag = bag
            self._page()
            c = self.c
            self._progress(page_steps[-1]["n"], len(steps), bag)
            for k, st in enumerate(page_steps):
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
                    c.drawRightString(x0 + cw - 14, y0 + 12, f"SUB-BUILD: {sub.upper()}")
                else:
                    c.setStrokeColor(LINE)
                    c.setLineWidth(0.6)
                    c.rect(x0 + 4, y0 + 4, cw - 8, chh - 8, stroke=1, fill=0)
                pool = self.subs[sub]["parts"] if kind == "subassembly" else parts
                cnt = Counter((pool[i]["part"], pool[i]["color"]) for i in st["parts"])
                per_row = max(1, int((cw - 74) // 48))
                rows = min(3, -(-len(cnt) // per_row)) if cnt else 1
                img_h = chh - 60 - rows * 50
                if kind == "attach":
                    im = self.render(st["n"], (), st["view"], px=STEP_PX, attach=sub)
                elif kind == "subassembly":
                    im = self.render(st["n"], st["parts"], st["view"], px=STEP_PX, sub=sub)
                else:
                    im = self.render(st["n"], st["parts"], st["view"], px=STEP_PX)
                draw_indexed(c, im, x0 + 14, y0 + 12, cw - 28, img_h, preserveAspectRatio=True, anchor="c",
                             palette=self.pal)
                c.setFillColor(INK)
                label = st.get("label", str(st["n"]))
                c.setFont("Helvetica-Bold", 26 if "." not in label else 20)
                c.drawString(x0 + 14, y0 + chh - 40, label)
                # callout: new parts this step, up to two rows
                items = sorted(cnt.items())
                shown = items[:per_row * 3]
                for j, ((pid, col), q) in enumerate(shown):
                    r2, c2 = divmod(j, per_row)
                    ix, iy = x0 + 64 + c2 * 48, y0 + chh - 50 - r2 * 50
                    draw_indexed(c, self.icon(pid, col), ix, iy, 40, 31)
                    c.setFont("Helvetica-Bold", 8)
                    c.setFillColor(INK)
                    c.drawString(ix + 2, iy - 7, f"{q}x")
                    c.setFont("Helvetica", 4.8)       # colour by name too, never colour alone
                    c.setFillColor(SOFT)
                    c.drawString(ix + 2, iy - 13, self.cat.colors[col]["name"])
                if len(items) > len(shown):
                    c.setFont("Helvetica-Bold", 8)
                    c.setFillColor(ACC)
                    c.drawString(x0 + 64, y0 + chh - 50 - 3 * 50 + 10,
                                 f"+{len(items) - len(shown)} more part types: see the bag list")
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
            self.log(f"  book: steps {page_steps[0]['n']}-{page_steps[-1]['n']} of {len(steps)}")

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
