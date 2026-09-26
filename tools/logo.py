#!/usr/bin/env python3
"""Dev-only: draw the Snapwright logo (SVG for the README, PNGs for avatars and social cards).

The wordmark is built, not typeset: every letter is a 5 x 7 mosaic of little studded tiles,
"snap" in orange and "wright" in azure, next to an isometric 2 x 2 brick. Everything is drawn
here from simple geometry, so there is no font licence to worry about and nothing borrowed
from any toy company's trade dress.

  python tools/logo.py            # writes docs/brand/*.svg / *.png
"""
import math
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "brand")

ORANGE, ORANGE_HI, ORANGE_LO, ORANGE_DK = "#F59E2E", "#FFC266", "#D9791A", "#B85F10"
AZURE, AZURE_HI = "#2FA7C9", "#7FD3EA"
INK = "#1F2A33"

# 5 x 7 mosaic letters (rows top to bottom, "#" = a tile)
FONT = {
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "N": ["#...#", "##..#", "#.#.#", "#.#.#", "#..##", "#...#", "#...#"],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "I": ["###", ".#.", ".#.", ".#.", ".#.", ".#.", "###"],
    "G": [".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
}


def _tiles(word, x0, y0, t, gap, colour):
    """(x, y, size, colour) for each tile of `word`, left to right."""
    out, x = [], x0
    for ch in word:
        rows = FONT[ch]
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                if cell == "#":
                    out.append((x + c * (t + gap), y0 + r * (t + gap), t, colour))
        x += (len(rows[0]) + 1) * (t + gap)
    return out, x


def _brick(cx, cy, s):
    """Isometric 2 x 2 brick centred on (cx, cy), unit s: faces (polygons, colour) and studs."""
    c, h = math.cos(math.radians(30)) * s, 0.5 * s
    height = 1.15 * s

    def iso(i, j, k):
        return (cx + (i - j) * c, cy + (i + j) * h - k)
    top = [iso(-1, -1, height), iso(1, -1, height), iso(1, 1, height), iso(-1, 1, height)]
    left = [iso(-1, 1, height), iso(1, 1, height), iso(1, 1, 0), iso(-1, 1, 0)]
    right = [iso(1, -1, height), iso(1, 1, height), iso(1, 1, 0), iso(1, -1, 0)]
    faces = [(top, ORANGE_HI), (left, ORANGE), (right, ORANGE_LO)]
    studs = []
    for i, j in ((-0.5, -0.5), (0.5, -0.5), (-0.5, 0.5), (0.5, 0.5)):
        x, y = iso(i, j, height)
        studs.append((x, y, 0.36 * c, 0.36 * h, 0.28 * s))
    return faces, studs


def layout(scale=1.0):
    """All shapes of the horizontal logo, in pixels at `scale` (1.0 = 1040 x 200)."""
    t, gap = 14 * scale, 3 * scale
    icon = _brick(95 * scale, 118 * scale, 46 * scale)
    y0 = 40 * scale
    snap, x = _tiles("SNAP", 215 * scale, y0, t, gap, ORANGE)
    wright, x = _tiles("WRIGHT", x + 6 * scale, y0, t, gap, AZURE)
    return icon, snap + wright, (x, 200 * scale)


def svg(scale=1.0):
    (faces, studs), tiles, (w, h) = layout(scale)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" '
             f'height="{h:.0f}" role="img" aria-label="Snapwright">', "<title>Snapwright</title>"]
    for poly, col in faces:
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in poly)
        parts.append(f'<polygon points="{pts}" fill="{col}" stroke="{ORANGE_DK}" stroke-width="{2 * scale:.1f}" '
                     f'stroke-linejoin="round"/>')
    for x, y, rx, ry, hh in studs:
        parts.append(f'<rect x="{x - rx:.1f}" y="{y - hh:.1f}" width="{2 * rx:.1f}" height="{hh:.1f}" fill="{ORANGE}"/>')
        parts.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{ORANGE}"/>')
        parts.append(f'<ellipse cx="{x:.1f}" cy="{y - hh:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{ORANGE_HI}" '
                     f'stroke="{ORANGE_DK}" stroke-width="{1.2 * scale:.1f}"/>')
    for x, y, s, col in tiles:
        hi = ORANGE_HI if col == ORANGE else AZURE_HI
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{s:.1f}" height="{s:.1f}" rx="{s * 0.18:.1f}" fill="{col}"/>')
        parts.append(f'<circle cx="{x + s / 2:.1f}" cy="{y + s / 2:.1f}" r="{s * 0.26:.1f}" fill="{hi}"/>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def png(scale=1.0, bg=None, pad=0):
    (faces, studs), tiles, (w, h) = layout(scale * 4)            # draw 4x, then shrink: smooth edges
    W, H = int(w + 8 * pad * scale), int(h + 8 * pad * scale)
    img = Image.new("RGBA", (W, H), bg or (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    o = 4 * pad * scale
    sh = lambda p: [(x + o, y + o) for x, y in p]                 # noqa: E731
    for poly, col in faces:
        d.polygon(sh(poly), fill=col, outline=ORANGE_DK, width=int(8 * scale))
    for x, y, rx, ry, hh in studs:
        x, y = x + o, y + o
        d.rectangle([x - rx, y - hh, x + rx, y], fill=ORANGE)
        d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=ORANGE)
        d.ellipse([x - rx, y - hh - ry, x + rx, y - hh + ry], fill=ORANGE_HI, outline=ORANGE_DK, width=int(5 * scale))
    for x, y, s, col in tiles:
        x, y = x + o, y + o
        hi = ORANGE_HI if col == ORANGE else AZURE_HI
        d.rounded_rectangle([x, y, x + s, y + s], radius=s * 0.18, fill=col)
        r = s * 0.26
        d.ellipse([x + s / 2 - r, y + s / 2 - r, x + s / 2 + r, y + s / 2 + r], fill=hi)
    return img.resize((W // 4, H // 4), Image.LANCZOS)


def icon_png(size=512, bg="#FFF8EC"):
    """The brick alone, centred on a rounded square: avatars, favicons."""
    img = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size * 4 - 1, size * 4 - 1], radius=size * 0.9, fill=bg)
    faces, studs = _brick(size * 2, size * 2.45, size * 0.85)
    for poly, col in faces:
        d.polygon(poly, fill=col, outline=ORANGE_DK, width=int(size * 0.035))
    for x, y, rx, ry, hh in studs:
        d.rectangle([x - rx, y - hh, x + rx, y], fill=ORANGE)
        d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=ORANGE)
        d.ellipse([x - rx, y - hh - ry, x + rx, y - hh + ry], fill=ORANGE_HI, outline=ORANGE_DK,
                  width=int(size * 0.02))
    return img.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "snapwright-logo.svg"), "w").write(svg())
    png(1.0).save(os.path.join(OUT, "snapwright-logo.png"))
    icon_png().save(os.path.join(OUT, "snapwright-icon.png"))
    print("wrote", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
