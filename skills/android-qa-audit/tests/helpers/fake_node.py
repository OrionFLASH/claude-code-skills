#!/usr/bin/env python3
"""Fake `node annotate.js` / `node sheet.js` for offline tests.
annotate.js: copies --in to --out (a PNG) and prints the report annotate.js prints
({out, items: [{color, label, overlapCost, contrast, inside, covers}]}). FAKE_NODE_BAD=1 — the first caption is
outside the picture and covers another box (to test the warnings). The spec is saved for inspection.
sheet.js --spec sheet.json: writes one tiny PNG per `per` items (out, or out-1.png, out-2.png …) and prints
{"sheets": [...]}; FAKE_NODE_BAD=1 — exit 1 without output.
"""
import json
import os
import shutil
import struct
import sys
import zlib


def arg(name):
    a = sys.argv
    return a[a.index(name) + 1] if name in a else None


def tiny_png(path):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(b"\x00\x10\x20\x30")) + chunk(b"IEND", b""))


def sheet():
    bad = os.environ.get("FAKE_NODE_BAD") == "1"
    spec = json.load(open(arg("--spec"), encoding="utf-8"))
    if bad:
        sys.stderr.write("chromium crashed\n")
        sys.exit(1)
    items, per, out = spec["items"], int(spec.get("per") or 8), spec["out"]
    sheets = []
    for i in range(0, len(items), per):
        name = out[:-4] + "-%d.png" % (i // per + 1) if len(items) > per else out
        tiny_png(name)
        sheets.append(os.path.abspath(name))
    print(json.dumps({"sheets": sheets}))


def main():
    if len(sys.argv) > 1 and sys.argv[1].endswith("sheet.js"):
        return sheet()
    src, spec, out = arg("--in"), arg("--spec"), arg("--out")
    data = json.load(open(spec, encoding="utf-8"))
    shutil.copyfile(src, out)
    bad = os.environ.get("FAKE_NODE_BAD") == "1"
    items = [{"color": "#FFD60A", "label": [10, 10, 200, 40], "overlapCost": 0, "contrast": 3.4,
              "inside": not (bad and i == 0), "covers": 120 if bad and i == 0 else 0} for i, _ in enumerate(data["items"])]
    print(json.dumps({"out": os.path.abspath(out), "items": items}))


if __name__ == "__main__":
    main()
