import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "skill", "snapwright", "scripts"))
sys.path.insert(0, TESTS)

from snapwright.catalog import Catalog  # noqa: E402
from snapwright.dsl import Model, dsl_namespace  # noqa: E402
from snapwright import pipeline  # noqa: E402

FIXTURES = os.path.join(TESTS, "fixtures")


@pytest.fixture(scope="session")
def cat():
    return Catalog()


def quiet(*a, **k):
    pass


def model_from_src(src, catalog=None):
    ns = dsl_namespace()
    exec(src, ns)
    return ns["model"]


def solve(m, catalog=None, seeds=2, **kw):
    """Run brickify + checks + steps in memory. Returns (model dict, built voxels)."""
    return pipeline.solve(m, catalog or Catalog(), seeds=seeds, log=quiet, **kw)
