"""A build video: the model assembling itself, part by part, in build order.

Frames come from the same renderer as the book (so the video looks like the instructions):
parts drop into place in step order, several in flight at once, with a caption and a part
counter; then the finished model holds and turns through its other three sides. Frames are
piped to ffmpeg (H.264 MP4, 4:2:0, faststart: plays in browsers and on social sites). Without
ffmpeg the video is written as an animated WebP instead.
"""
from __future__ import annotations

import math
import shutil
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .catalog import Catalog
from .render import render_parts
from .snot import PanelSpec

PAPER = (247, 245, 240)
INK = (38, 38, 38)
SOFT = (120, 120, 120)
DROP = 14            # plates a part falls from
FALL = 9             # frames a part takes to land


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                      # Pillow < 10.1: bitmap font only
        return ImageFont.load_default()


def _ease_out(u):
    return 1 - (1 - u) ** 3


def build_video(model, path, catalog=None, seconds=24.0, fps=30, size=(1080, 1080), view=0,
                hold=1.5, turn=True, credit="Snapwright", log=print):
    """Write the build video to `path` (.mp4, or .webp without ffmpeg). Returns the path."""
    cat = catalog or Catalog()
    W, H = size[0] // 2 * 2, size[1] // 2 * 2
    NX, NZ, NY = model["grid"]["shape"]
    shape = (NX, NZ, NY + DROP)
    frame_box = (NX, NZ, NY + DROP // 2)
    parts = model["parts"]
    cols = {p["id"]: cat.colors[p["color"]]["hex"] for p in parts}
    order = sorted(parts, key=lambda p: (p.get("step", 0), p["y"], p["x"], p["z"]))
    attach = {st["sub"]: st["n"] for st in model["steps"] if st.get("kind") == "attach"}
    subs = [dict(spec=PanelSpec.from_json(sb["spec"]), parts=sb["parts"], step=attach.get(sb["name"], 0),
                 colors={q["id"]: cat.colors[q["color"]]["hex"] for q in sb["parts"]})
            for sb in model.get("subassemblies", [])]

    build_frames = max(1, int(seconds * fps))
    n = len(order)
    # when each part starts to fall: eased so the first and last parts take their time
    starts = [int(round(build_frames * (0.5 - 0.5 * math.cos(math.pi * k / max(1, n - 1))))) for k in range(n)]
    title = model["meta"]["title"]
    big, small = _font(max(18, H // 24)), _font(max(14, H // 40))
    pw = int(min(W, H) * 0.9)

    top_h = int(H * 0.84)                      # picture area; the caption sits below it

    crops = {}

    def crop_for(v):
        """The finished model's outline in view v, with room above it for falling parts: every
        frame of that view is cut to this same box, so the model fills the frame and never jumps."""
        if v not in crops:
            full = render(order, v)
            x0, y0, x1, y1 = full.getbbox() or (0, 0, full.width, full.height)
            mx, my = int((x1 - x0) * 0.06), int((y1 - y0) * 0.1)
            crops[v] = (max(0, x0 - mx), max(0, y0 - my), min(full.width, x1 + mx), min(full.height, y1 + mx))
        return crops[v]

    def compose(img, placed, v):
        """The render centred on paper, with the caption."""
        img = img.crop(crop_for(v))
        out = Image.new("RGB", (W, H), PAPER)
        s = min(W * 0.94 / img.width, top_h / img.height)
        img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
        out.paste(img, ((W - img.width) // 2, (top_h - img.height) // 2 + int(H * 0.02)), img)
        d = ImageDraw.Draw(out)
        x0, y0 = int(W * 0.05), int(H * 0.87)
        d.text((x0, y0), title, fill=INK, font=big)
        d.text((x0, y0 + int(H * 0.055)), f"{placed:,} / {n:,} parts", fill=SOFT, font=small)
        if credit:
            d.text((W - x0, y0 + int(H * 0.055)), credit, fill=SOFT, font=small, anchor="ra")
        return out

    def render(shown, v):
        step_now = max((p.get("step", 0) for p in shown), default=0)
        pans = [dict(spec=s["spec"], parts=s["parts"], colors=s["colors"], hl=False)
                for s in subs if s["step"] and s["step"] <= step_now]
        allc = dict(cols)
        return render_parts(shown, shape, allc, cat, view=v, panels=pans or None, size=(pw, pw),
                            framing=frame_box)

    frames, count = [], [0]
    webp_every = max(1, fps // 15)             # an animated WebP only needs ~15 fps

    def emit(img):
        if writer is not None:
            writer.stdin.write(np.asarray(img, dtype=np.uint8).tobytes())
        elif count[0] % webp_every == 0:       # keep a small copy only
            frames.append(img.resize((min(W, 720), int(H * min(W, 720) / W)), Image.LANCZOS))
        count[0] += 1

    ffmpeg = shutil.which("ffmpeg")
    use_mp4 = bool(ffmpeg) and str(path).lower().endswith(".mp4")
    if not use_mp4 and str(path).lower().endswith(".mp4"):
        path = str(path)[:-4] + ".webp"
        log("  ffmpeg not found: writing an animated WebP instead")
    writer = None
    if use_mp4:
        writer = subprocess.Popen([ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                   "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-c:v", "libx264",
                                   "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
                                   "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)
    total = build_frames + FALL
    for f in range(total + 1):
        shown, placed = [], 0
        for k, p in enumerate(order):
            a = f - starts[k]
            if a < 0:
                break
            u = min(1.0, a / FALL)
            if u >= 1:
                placed += 1
                shown.append(p)
            else:
                shown.append(dict(p, y=p["y"] + int(round(DROP * (1 - _ease_out(u))))))
        emit(compose(render(shown, view), placed, view))
        if f % (fps * 2) == 0:
            log(f"  video: frame {f} of {total} ({placed:,} parts placed)")
    final = [compose(render(order, (view + k) % 4), n, (view + k) % 4) for k in range(4 if turn else 1)]
    for _ in range(int(hold * fps)):
        emit(final[0])
    if turn:                                   # the other three sides, dissolving into each other
        for k in range(1, 5):
            a, b = final[(k - 1) % 4], final[k % 4]
            for i in range(int(0.6 * fps)):
                emit(Image.blend(a, b, (i + 1) / int(0.6 * fps)))
            for _ in range(int(0.9 * fps)):
                emit(b)
    if writer is not None:
        writer.stdin.close()
        if writer.wait() != 0:
            raise RuntimeError("ffmpeg failed to write the video")
    else:
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 * webp_every / fps),
                       loop=0, quality=80)
    log(f"  video -> {path}")
    return path
