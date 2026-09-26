"""Refresh part-colour availability in assets/catalog.json from Rebrickable.

Two sources, same result:

  * bulk downloads (default, no key): Rebrickable's free CSV dumps (inventory_parts, inventories,
    sets, part_relationships). A part-colour combo counts as available if the plain part (or a
    mould variant of it) appears in that colour in any set released since `since`. Prints do
    not count: a printed tile is a different element.
  * the API (`key`): /parts/{id}/colors/ per catalog part. Slower (one request a second) and
    counts every colour Rebrickable knows for the mould, whatever the year.

Writes catalog["availability"] = {part_id: [colour keys]} and catalog["availability_meta"]
(source, date, since). After syncing, the validator reports combos as 'verified' or
'unverified' instead of 'likely'. This is the only command that uses the network.
"""
from __future__ import annotations

import csv
import datetime
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.request

from .catalog import DEFAULT_CATALOG

API = "https://rebrickable.com/api/v3/lego/parts/{pid}/colors/?page_size=500"
CDN = "https://cdn.rebrickable.com/media/downloads/{name}.csv.gz"
DUMPS = ("sets", "inventories", "inventory_parts", "part_relationships", "colors")


def sync(key=None, path=DEFAULT_CATALOG, downloads=None, since=2005, log=print):
    cat = json.load(open(path))
    if key:
        avail = from_api(cat, key, log)
        meta = {"source": "rebrickable api"}
    else:
        folder = downloads or os.path.join(os.path.dirname(path), ".rebrickable")
        fetch_dumps(folder, log)
        avail = from_dumps(cat, folder, since, log)
        meta = {"source": "rebrickable downloads", "since": since}
    empty = [p for p, cols in avail.items() if not cols]
    if empty:
        raise SystemExit("no colours found for " + ", ".join(empty) + ": check their `rebrickable` "
                         "ids in the catalog (catalog not changed)")
    meta["date"] = datetime.date.today().isoformat()
    cat["availability"] = avail
    cat["availability_meta"] = meta
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cat, f, indent=1)
        f.write("\n")
    os.replace(tmp, path)
    n = sum(len(v) for v in avail.values())
    log(f"catalog updated: {path} ({n} part-colour combos over {len(avail)} parts)")
    return avail


# ---- bulk downloads ---------------------------------------------------------------------------
def fetch_dumps(folder, log=print):
    """Download the CSV dumps into `folder` unless they are already there."""
    os.makedirs(folder, exist_ok=True)
    for name in DUMPS:
        dest = os.path.join(folder, name + ".csv.gz")
        if os.path.exists(dest):
            continue
        log(f"downloading {name}.csv.gz")
        with urllib.request.urlopen(CDN.format(name=name), timeout=120) as r, open(dest + ".part", "wb") as f:
            f.write(r.read())
        os.replace(dest + ".part", dest)


def _rows(folder, name):
    with gzip.open(os.path.join(folder, name + ".csv.gz"), "rt", newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def rb_ids(cat):
    """Rebrickable part number of each catalog part."""
    return {p["id"]: p.get("rebrickable") or p["id"] for p in cat["parts"]}


def from_dumps(cat, folder, since=2005, log=print):
    ids = rb_ids(cat)
    # mould variants (rel_type M) have the same shape: 3069a/3069b, 4032a/4032b, ...
    group = {rb: {rb} for rb in ids.values()}
    for r in _rows(folder, "part_relationships"):
        if r["rel_type"] != "M":
            continue
        a, b = r["child_part_num"], r["parent_part_num"]
        for g, other in ((a, b), (b, a)):
            if g in group:
                group[g].add(other)
    owner = {v: rb for rb, vs in group.items() for v in vs}
    _check_colours(cat, folder, log)
    year = {r["set_num"]: int(r["year"]) for r in _rows(folder, "sets")}
    recent = {r["id"] for r in _rows(folder, "inventories") if year.get(r["set_num"], 0) >= since}
    by_rb = {int(c["rebrickable"]): k for k, c in cat["colors"].items()}
    seen = {rb: set() for rb in group}
    for r in _rows(folder, "inventory_parts"):
        rb = owner.get(r["part_num"])
        if rb is None or r["inventory_id"] not in recent:
            continue
        k = by_rb.get(int(r["color_id"]))
        if k:
            seen[rb].add(k)
    return {pid: sorted(seen[rb]) for pid, rb in ids.items()}


def _check_colours(cat, folder, log):
    """Warn if a catalog colour's Rebrickable id names a different colour than we think."""
    names = {int(r["id"]): r["name"] for r in _rows(folder, "colors")}
    for k, c in cat["colors"].items():
        got = names.get(int(c["rebrickable"]))
        if got is None or _norm(got) != _norm(c["name"]):
            log(f"  warning: colour {k} ({c['name']}) has Rebrickable id {c['rebrickable']} = {got}")


def _norm(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


# ---- API --------------------------------------------------------------------------------------
def from_api(cat, key, log=print):
    by_rb = {int(c["rebrickable"]): k for k, c in cat["colors"].items()}
    avail = {}
    for pid, rb in rb_ids(cat).items():
        cols, url = set(), API.format(pid=rb)
        while url:
            data = _get(url, key)
            cols |= {by_rb[c["color_id"]] for c in data.get("results", []) if c["color_id"] in by_rb}
            url = data.get("next")
        avail[pid] = sorted(cols)
        log(f"  {pid}: {len(cols)} colours")
        time.sleep(1.1)  # stay under the API rate limit
    return avail


def _get(url, key, tries=5):
    for i in range(tries):
        req = urllib.request.Request(url, headers={"Authorization": f"key {key}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(io.TextIOWrapper(r, encoding="utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"results": []}
            if e.code == 429 and i < tries - 1:
                time.sleep(5 * (i + 1))
                continue
            raise
    return {"results": []}
