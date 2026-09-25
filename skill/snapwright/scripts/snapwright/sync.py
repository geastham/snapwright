"""Refresh part-colour availability in assets/catalog.json from the Rebrickable API.

Needs a free Rebrickable API key and network access. Writes catalog["availability"] as
{part_id: [colour keys that exist for that mould]}. After syncing, the validator reports
combos as 'verified' or 'unverified' instead of 'likely'.
"""
import json
import time
import urllib.request

from .catalog import DEFAULT_CATALOG

API = "https://rebrickable.com/api/v3/lego/parts/{pid}/colors/?page_size=500"


def sync(key, path=DEFAULT_CATALOG):
    if not key:
        raise SystemExit("Pass --key or set REBRICKABLE_KEY")
    cat = json.load(open(path))
    by_rb = {c["rebrickable"]: k for k, c in cat["colors"].items()}
    avail = {}
    for p in cat["parts"]:
        req = urllib.request.Request(API.format(pid=p["id"]), headers={"Authorization": f"key {key}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        avail[p["id"]] = sorted(by_rb[c["color_id"]] for c in data.get("results", []) if c["color_id"] in by_rb)
        print(p["id"], len(avail[p["id"]]))
        time.sleep(1.1)  # stay under the API rate limit
    cat["availability"] = avail
    json.dump(cat, open(path, "w"), indent=1)
    print("catalog updated:", path)
