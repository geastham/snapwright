"""Every regression fixture must build, satisfy the invariant oracles and PASS."""
import glob
import os

import numpy as np
import pytest

from conftest import FIXTURES, Model, dsl_namespace, solve
from oracles import check_model

CASES = sorted(glob.glob(os.path.join(FIXTURES, "*.py")) + glob.glob(os.path.join(FIXTURES, "*.npz")))


def load(path):
    if path.endswith(".py"):
        ns = dsl_namespace()
        exec(open(path).read(), ns)
        return ns["model"], ns.get("EXPECT", {"passed": True})
    d = np.load(path)
    V, palette = d["V"], [str(c) for c in d["palette"]]
    m = Model(*V.shape, title=os.path.basename(path))
    for c in palette:
        m._idx(c)
    m.V[...] = V
    return m, {"passed": True}


@pytest.mark.parametrize("path", CASES, ids=[os.path.basename(c) for c in CASES])
def test_fixture(path):
    m, expect = load(path)
    model, built = solve(m, seeds=3)
    check_model(model, m.V, built, m.palette)
    for k, v in expect.items():
        assert model["stats"][k] == v, (k, model["stats"][k], model["stats"]["failures"])
