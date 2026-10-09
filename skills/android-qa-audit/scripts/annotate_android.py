#!/usr/bin/env python3
"""Annotated Android screenshots for findings and issues (references/screenshots.md): thin dashed outline, a thin
arrow and a short caption (✕ error / ? question / • note), palette yellow #FFD60A / green #30D158 / purple #BF5AF2,
≤ 3 marks per shot. Drawing is done by scripts/node/annotate.js (a vendored copy of site-qa-audit's annotate.js,
Chromium via Playwright); this script converts device pixels to the spec, finds element boxes in a dump-ui tree and
checks the result (caption inside the picture, no caption over other boxes, colour contrast).

  annotate_android.py render --in shot.png --mark "x,y,w,h|Подпись|error" [--mark "text=Удалить|Подпись|question"]
                      [--ui raw/ui-….xml] [--density 420] [--out shot-annotated.png] [--json]
  annotate_android.py batch marks.json --shots DIR --out DIR [--density 420]
        marks.json: [{"id": "F-001", "src": "shot.png", "marks": [{"box": [x, y, w, h], "label": "…", "kind": "error"}],
                      "extra": [{"src": "…", "marks": […]}]}]
  annotate_android.py box --ui raw/ui-….xml (--text T | --desc D | --id ID)      box of an element for --mark
  annotate_android.py check                                                     node + playwright available?

Marks: "x,y,w,h|label|kind" — pixels of the screenshot (as in dump-ui bounds); "text=…|…", "desc=…|…", "id=…|…" —
the element from --ui (or a fresh dump when called by adb_helpers.py screenshot --mark); "x,y,w,h|@avoid" — an area
the caption must not cover. kind: error (default) | question | note. Scale: density / 160 (420 dpi → 2.625).
Node: ANDROID_QA_NODE (default `node` in PATH); modules: ANDROID_QA_NODE_MODULES or <SKILL_DIR>/scripts/node/
node_modules (npm install there, locally). Without them: «не поддерживается: …», the original and spec are kept.
Exit codes: 0 ok, 1 annotated with warnings, 2 bad input, 4 not supported (no node / playwright), 5 failed.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NODE_DIR = HERE / "node"
KINDS = ("error", "question", "note")
MAX_MARKS = 3
MAX_LABEL = 60


class AnnotateError(Exception):
    def __init__(self, message, code=5):
        super().__init__(message)
        self.code = code


def parse_mark(text):
    """'x,y,w,h|label|kind' | 'text=…|label|kind' | 'x,y,w,h|@avoid' -> dict."""
    parts = [p.strip() for p in str(text).split("|")]
    if not parts or not parts[0]:
        raise AnnotateError(f"пустая отметка: {text!r}", 2)
    target, label = parts[0], (parts[1] if len(parts) > 1 else "")
    kind = (parts[2] if len(parts) > 2 and parts[2] else "error").lower()
    mark = {"label": label, "kind": kind, "box": None, "target": None, "avoid": label == "@avoid"}
    m = re.match(r"^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?),(\d+(?:\.\d+)?),(\d+(?:\.\d+)?)$", target)
    if m:
        mark["box"] = [float(x) for x in m.groups()]
    else:
        m = re.match(r"^(text|desc|id)=(.+)$", target)
        if not m:
            raise AnnotateError(f"цель отметки: x,y,w,h или text=/desc=/id=… — получено {target!r}", 2)
        mark["target"] = (m.group(1), m.group(2))
    if not mark["avoid"] and kind not in KINDS:
        raise AnnotateError(f"вид отметки {kind!r}: error | question | note", 2)
    return mark


def ui_nodes(path):
    """Nodes with bounds from a dump-ui XML (raw/ui-*.xml) or its --json (all_nodes / texts)."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        d = json.loads(text)
        out = []
        for n in d.get("all_nodes") or d.get("texts") or d.get("elements") or []:
            b = n.get("bounds") or [0, 0, 0, 0]
            out.append({"text": n.get("text") or n.get("label") or "", "desc": n.get("desc") or "", "id": n.get("id") or "",
                        "bounds": b})
        return out
    sys.path.insert(0, str(HERE))
    import adb_helpers  # noqa: E402 — parse_ui only (no device access)
    return adb_helpers.parse_ui(text)


def find_box(nodes, kind, value):
    """[x, y, w, h] of the element: exact text/desc/id first, then a substring; the smallest wins."""
    want = value.strip().lower()

    def val(n):
        v = n.get(kind) or ""
        return v.split(":id/")[-1].lower() if kind == "id" else v.strip().lower()
    exact = [n for n in nodes if val(n) == want]
    pool = exact or [n for n in nodes if want and want in val(n)]
    if not pool:
        return None
    b = min(pool, key=lambda n: (n["bounds"][2] - n["bounds"][0]) * (n["bounds"][3] - n["bounds"][1]))["bounds"]
    return [b[0], b[1], b[2] - b[0], b[3] - b[1]]


def resolve(marks, nodes):
    for m in marks:
        if m["box"] is None and m["target"]:
            if nodes is None:
                raise AnnotateError(f"отметка {m['target'][0]}={m['target'][1]}: нужно дерево (--ui или dump-ui)", 2)
            m["box"] = find_box(nodes, *m["target"])
            if m["box"] is None:
                raise AnnotateError(f"на экране нет элемента {m['target'][0]}=«{m['target'][1]}» (dump-ui --texts)", 4)
    return marks


def make_spec(marks, density):
    scale = (density or 160) / 160.0
    items = [{"box": [round(v / scale, 1) for v in m["box"]], "label": m["label"], "kind": m["kind"]}
             for m in marks if not m["avoid"]]
    avoid = [[round(v / scale, 1) for v in m["box"]] for m in marks if m["avoid"]]
    warnings = []
    if len(items) > MAX_MARKS:
        warnings.append(f"отметок {len(items)} — больше {MAX_MARKS} на снимок: разбить на несколько скриншотов")
    for it in items:
        if len(it["label"]) > MAX_LABEL:
            warnings.append(f"подпись длиннее {MAX_LABEL} символов: «{it['label'][:40]}…» — сократить до факта")
        if not it["label"]:
            warnings.append("отметка без подписи — только рамка")
    spec = {"scale": scale, "items": items}
    if avoid:
        spec["avoid"] = avoid
    return spec, warnings


def node_cmd():
    """(node executable, NODE_PATH folder) or AnnotateError(code 4) with the reason."""
    node = os.environ.get("ANDROID_QA_NODE") or shutil.which("node")
    if not node:
        raise AnnotateError("не поддерживается: нет Node.js ≥ 18 (INSTALL.md → «Аннотации скриншотов»); исходный снимок "
                            "и spec сохранены — нарисовать позже или вручную", 4)
    modules = Path(os.environ.get("ANDROID_QA_NODE_MODULES") or NODE_DIR / "node_modules")
    if not (modules / "playwright").is_dir():
        raise AnnotateError(f"не поддерживается: нет модуля playwright в {modules} — локально: cd {NODE_DIR} && npm install "
                            "&& npx playwright install chromium (только с согласия пользователя)", 4)
    return node, modules


def render(src, marks, density, out=None, nodes=None):
    """Annotate one screenshot. Returns {original, annotated, spec, ok, warnings, items}."""
    src = Path(src)
    if not src.is_file():
        raise AnnotateError(f"нет файла {src}", 2)
    marks = resolve([dict(m) for m in marks], nodes)
    spec, warnings = make_spec(marks, density)
    spec_path = src.with_name(src.stem + ".spec.json")
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    out = Path(out) if out else src.with_name(src.stem + "-annotated.png")
    res = {"original": str(src), "annotated": None, "spec": str(spec_path), "ok": False, "warnings": warnings,
           "marks": [{"box": [int(v) for v in m["box"]], "label": m["label"], "kind": m["kind"]} for m in marks
                     if not m["avoid"]]}
    node, modules = node_cmd()
    env = dict(os.environ, NODE_PATH=str(modules))
    try:
        p = subprocess.run([node, str(NODE_DIR / "annotate.js"), "--in", str(src), "--spec", str(spec_path), "--out", str(out)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(NODE_DIR),
                           timeout=180)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise AnnotateError(f"annotate.js не запустился: {ex}", 5)
    if p.returncode != 0 or not out.is_file():
        raise AnnotateError(f"annotate.js: код {p.returncode}: {(p.stderr or p.stdout).strip()[-300:]}", 5)
    try:
        report = json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        report = {"items": []}
    items = report.get("items") or []
    for i, it in enumerate(items, 1):
        if it.get("inside") is False:
            warnings.append(f"подпись {i} выходит за край снимка")
        if (it.get("covers") or 0) > 0:
            warnings.append(f"подпись {i} закрывает другую рамку или подпись ({it['covers']} px²)")
        if it.get("contrast") is not None and it["contrast"] < 2:
            warnings.append(f"цвет отметки {i} плохо виден на фоне (контраст {it['contrast']})")
    res.update({"annotated": str(out), "ok": not warnings, "items": items, "canvas": report.get("canvas"),
                "must_view": f"посмотреть {out.name} (Read) до ссылки в находке; правки — подпись в {spec_path.name} и "
                             f"annotate_android.py render заново"})
    return res


def batch(marks_file, shots, out_dir, density):
    data = json.loads(Path(marks_file).read_text(encoding="utf-8"))
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    results = []
    for f in data:
        jobs = [(f["src"], f["marks"], f"{f['id']}.png")] + \
            [(e["src"], e["marks"], f"{f['id']}-{i}.png") for i, e in enumerate(f.get("extra") or [], 2)]
        for src, ms, name in jobs:
            marks = [{"box": m["box"], "label": m.get("label", ""), "kind": m.get("kind", "error"), "target": None,
                      "avoid": False} for m in ms]
            try:
                results.append(dict(render(Path(shots) / src, marks, density, Path(out_dir) / name), id=f["id"]))
            except AnnotateError as ex:
                results.append({"id": f["id"], "original": src, "ok": False, "error": str(ex)})
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--in", dest="src", required=True)
    r.add_argument("--mark", action="append", default=[], required=True)
    r.add_argument("--ui", help="dump-ui: raw/ui-….xml или --json файл")
    r.add_argument("--density", type=float, default=420, help="dpi устройства (wm density), по умолчанию 420")
    r.add_argument("--out")
    r.add_argument("--json", action="store_true")
    b = sub.add_parser("batch")
    b.add_argument("marks")
    b.add_argument("--shots", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--density", type=float, default=420)
    x = sub.add_parser("box")
    x.add_argument("--ui", required=True)
    g = x.add_mutually_exclusive_group(required=True)
    g.add_argument("--text")
    g.add_argument("--desc")
    g.add_argument("--id")
    sub.add_parser("check")
    a = ap.parse_args()
    try:
        if a.cmd == "check":
            node, modules = node_cmd()
            print(json.dumps({"ok": True, "node": node, "node_modules": str(modules)}, ensure_ascii=False))
            return
        if a.cmd == "box":
            kind, value = next((k, v) for k, v in (("text", a.text), ("desc", a.desc), ("id", a.id)) if v)
            box = find_box(ui_nodes(a.ui), kind, value)
            if box is None:
                raise AnnotateError(f"нет элемента {kind}=«{value}»", 4)
            print(json.dumps({"box": box, "mark": f"{','.join(map(str, box))}|<подпись>|error"}, ensure_ascii=False))
            return
        if a.cmd == "batch":
            res = batch(a.marks, a.shots, a.out, a.density)
            print(json.dumps(res, ensure_ascii=False, indent=1))
            sys.exit(0 if all(x.get("ok") for x in res) else 1)
        marks = [parse_mark(m) for m in a.mark]
        res = render(a.src, marks, a.density, a.out, ui_nodes(a.ui) if a.ui else None)
        print(json.dumps(res, ensure_ascii=False, indent=1 if a.json else None))
        sys.exit(0 if res["ok"] else 1)
    except AnnotateError as ex:
        print(json.dumps({"ok": False, "error": str(ex)}, ensure_ascii=False))
        sys.exit(ex.code)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
