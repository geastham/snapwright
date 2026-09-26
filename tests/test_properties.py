"""Property tests on random blobby designs (tests/blobby.py), checked by independent oracles.

For every design, passing or not: no collisions, parts cover exactly the built voxels,
visible colours are kept, and the reported recolour/trim/add counts equal the real change.
For every PASS design: every part is reachable from the ground and every step can be
followed in order. Set SNAPWRIGHT_PROPERTY_N for a longer run (default 16 designs)."""
import os

import pytest

from blobby import random_design
from conftest import solve
from oracles import check_model

N = int(os.environ.get("SNAPWRIGHT_PROPERTY_N", "16"))


@pytest.mark.parametrize("seed", range(N))
def test_blobby_invariants(seed):
    m = random_design(1000 + seed)
    model, built = solve(m, seeds=2)
    check_model(model, m.V, built, m.palette)


def test_blobby_mostly_pass():
    """Guard against the packer quietly getting worse: most random blobs must build."""
    passed = sum(solve(random_design(2000 + s), seeds=2)[0]["stats"]["passed"] for s in range(12))
    assert passed >= 9, f"only {passed}/12 random designs passed"
