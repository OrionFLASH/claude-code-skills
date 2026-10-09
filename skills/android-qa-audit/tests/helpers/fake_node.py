#!/usr/bin/env python3
"""Fake `node annotate.js` for offline tests: copies --in to --out (a PNG) and prints the report annotate.js prints
({out, items: [{color, label, overlapCost, contrast, inside, covers}]}). FAKE_NODE_BAD=1 — the first caption is
outside the picture and covers another box (to test the warnings). The spec is saved for inspection.
"""
import json
import os
import shutil
import sys


def arg(name):
    a = sys.argv
    return a[a.index(name) + 1] if name in a else None


def main():
    src, spec, out = arg("--in"), arg("--spec"), arg("--out")
    data = json.load(open(spec, encoding="utf-8"))
    shutil.copyfile(src, out)
    bad = os.environ.get("FAKE_NODE_BAD") == "1"
    items = [{"color": "#FFD60A", "label": [10, 10, 200, 40], "overlapCost": 0, "contrast": 3.4,
              "inside": not (bad and i == 0), "covers": 120 if bad and i == 0 else 0} for i, _ in enumerate(data["items"])]
    print(json.dumps({"out": os.path.abspath(out), "items": items}))


if __name__ == "__main__":
    main()
