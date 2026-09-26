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
