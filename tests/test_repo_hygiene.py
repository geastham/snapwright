"""Generated books and large files must never be committed (they ship as release assets)."""
import os
import subprocess

import pytest

from conftest import ROOT

MAX_BYTES = 1_000_000


def tracked():
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [f for f in out.stdout.decode().split("\0") if f]


def test_no_books_outputs_or_large_files_tracked():
    bad = []
    for f in tracked():
        p = os.path.join(ROOT, f)
        parts = f.split("/")
        if f.lower().endswith((".pdf", ".skill")) or "out" in parts or "dist" in parts:
            bad.append(f"{f}: generated output")
        elif os.path.isfile(p) and os.path.getsize(p) > MAX_BYTES:
            bad.append(f"{f}: {os.path.getsize(p):,} bytes (> {MAX_BYTES:,})")
    assert not bad, "don't commit these (git rm --cached them):\n" + "\n".join(bad)
