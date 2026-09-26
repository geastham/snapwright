"""Every automatic change and weak point must be surfaced identically in the CLI log, the
book finale and the viewer (they all come from validate.report_lines)."""
import json
import re
import zlib

from conftest import pipeline, quiet
from snapwright.validate import report_lines

STATS = {"parts": 10, "connections": 20, "structures": 1, "collisions": 0, "floating": 0,
         "weak_parts": [3], "com_margin_mm": 12.5, "mass_g": 30.0, "width_cm": 4, "depth_cm": 4,
         "height_cm": 3, "recolored_cells": 2, "trimmed_cells": 1, "added_cells": 0,
         "studded_cells": 5, "unverified_combos": [{"part": "3024", "color": "red"}],
         "necks": [{"plate": 7, "strength": 1, "parts_above": 9, "mass_g": 4.0}], "failures": []}


def test_report_lines_list_every_change():
    text = "\n".join(t for _, t in report_lines(STATS))
    assert "2 visible cells recoloured" in text
    assert "1 overhang cell trimmed" in text
    assert "5 top cells use studded plates" in text
    assert "held by 1 stud" in text
    assert "support" not in text                         # zero counts are not listed
    kinds = {k for k, _ in report_lines(STATS)}
    assert {"check", "change", "note"} <= kinds


def _pdf_text(path):
    """Decompressed content of every Flate stream in the PDF (page text lives there)."""
    data = open(path, "rb").read()
    out = []
    for m in re.finditer(rb"stream\r?\n", data):
        try:
            out.append(zlib.decompressobj().decompress(data[m.end():]).decode("latin-1"))
        except zlib.error:
            pass
    return "".join(out)


def test_log_book_and_viewer_agree(tmp_path):
    src = tmp_path / "d.py"
    src.write_text('model = Model(8, 8, 12, title="Report Test")\n'
                   'model.box(0, 0, 0, 8, 8, 3, "dark_bluish_gray")\n'
                   'model.cylinder(4, 4, 3, 3, 12, "white", inner_r=1.5)\n')
    lines = []
    model = pipeline.build(str(src), str(tmp_path / "out"), seeds=1, log=lines.append)
    report = [t for _, t in report_lines(model["stats"])]
    log = "\n".join(lines)
    html = (tmp_path / "out" / "report-test-viewer.html").read_text()
    viewer = json.loads(re.search(r'<script id="model" type="application/json">(.*?)</script>', html, re.S)
                        .group(1).replace("<\\/", "</"))["report"]
    pdf = _pdf_text(tmp_path / "out" / "report-test-instructions.pdf")
    for t in report:
        assert t in log
        assert any(r["text"] == t for r in viewer)
        assert t.replace("(", "\\(").replace(")", "\\)") in pdf, t
