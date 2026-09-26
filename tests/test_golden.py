"""Golden test on the lighthouse: parts within 5 % of the recorded count, PASS, and the same
model.json (apart from the date) from two separate processes with different hash seeds."""
import json
import os
import subprocess
import sys

from conftest import ROOT

SW = os.path.join(ROOT, "skill", "snapwright", "scripts", "sw.py")
DESIGN = os.path.join(ROOT, "examples", "lighthouse", "design.py")
GOLDEN = {"parts": 1806, "steps": 188}      # M6 (verified colours, plate seams, repair); M2 1,761 / 185; M1 1,760 / 184; v0.1 1,744 / 182


def test_lighthouse_golden_and_deterministic(tmp_path):
    procs = []
    for hs in ("1", "2"):
        env = dict(os.environ, PYTHONHASHSEED=hs)
        procs.append(subprocess.Popen([sys.executable, SW, "build", DESIGN, "--out", str(tmp_path / hs),
                                       "--seeds", "6", "--no-book", "--no-viewer"],
                                      env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
    outs = [p.communicate()[0] for p in procs]
    assert all(p.returncode == 0 for p in procs), outs
    a, b = (json.loads((tmp_path / hs / "model.json").read_text()) for hs in ("1", "2"))
    for m in (a, b):
        m["meta"].pop("created")
    assert a == b, "same design + seeds gave different models"
    st = a["stats"]
    assert st["passed"]
    assert abs(st["parts"] - GOLDEN["parts"]) <= 0.05 * GOLDEN["parts"], st["parts"]
    assert abs(st["steps"] - GOLDEN["steps"]) <= 0.10 * GOLDEN["steps"], st["steps"]
