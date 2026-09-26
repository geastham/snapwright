"""The build video: frames from the book renderer, parts dropping in build order; MP4 through
ffmpeg when it's installed, an animated WebP otherwise."""
import shutil
import subprocess

import pytest
from PIL import Image

from conftest import model_from_src, solve

SRC = '''
model = Model(8, 8, 9, title="Video Test")
model.box(0, 0, 0, 8, 8, 3, "blue")
model.box(2, 2, 3, 6, 6, 9, "red")
'''


def _model():
    model, _ = solve(model_from_src(SRC), seeds=1)
    return model


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_video_mp4(tmp_path, cat):
    from snapwright.video import build_video
    out = build_video(_model(), str(tmp_path / "b.mp4"), cat, seconds=1, fps=8, size=(320, 400),
                      log=lambda *a: None)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,pix_fmt",
                            "-of", "compact", out], capture_output=True, text=True).stdout
    assert "h264" in probe and "width=320" in probe and "height=400" in probe and "yuv420p" in probe


def test_video_webp_without_ffmpeg(tmp_path, cat, monkeypatch):
    import snapwright.video as V
    monkeypatch.setattr(V.shutil, "which", lambda name: None)
    out = V.build_video(_model(), str(tmp_path / "b.mp4"), cat, seconds=1, fps=15, size=(240, 240),
                        turn=False, log=lambda *a: None)
    assert out.endswith(".webp")
    im = Image.open(out)
    assert im.is_animated and im.n_frames > 10


def test_wizard_new_project_and_refs(tmp_path, cat):
    """`sw.py new` scaffolds a creation; `sw.py refs` finds clean views (mask, colours), lists
    missing views and writes one image-generation prompt per missing view."""
    import numpy as np
    from snapwright.wizard import inspect_refs, new_project
    proj = new_project("Red Box", str(tmp_path), subject="A plain red box.")
    a = np.full((200, 160, 3), 255, np.uint8)
    a[40:180, 30:130] = (200, 20, 20)
    Image.fromarray(a).save(f"{proj}/reference/view_front.png")
    r = inspect_refs(proj, catalog=cat)
    front = r["images"][0]
    assert front["usable_for_likeness"] and front["mask"] == "mask_view_front.png"
    assert front["colours"][0][0] == "red" and abs(front["aspect_h_over_w"] - 1.4) < 0.05
    assert r["views_needed"] == ["view_side"] and "view_side" in r["prompts"]
    assert "A plain red box" in r["prompts"]["view_side"] and ".." not in r["prompts"]["view_side"]
