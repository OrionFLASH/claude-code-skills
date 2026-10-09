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
  annotate_android.py sheet (FILE… | --dir DIR [--glob "*-annotated.png"] | --soak raw/soak-….json) --out sheet.png
                      [--cols 4] [--per 8] [--thumb 240] [--html-only]
        contact sheet: thumbnails with captions, ≤ per shots per PNG (one Read instead of eight) via node/sheet.js;
        an HTML grid next to it (<out>.html) is always written — without Node only it (exit 4).

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
        p = subprocess.run([node, str(NODE_DIR / "annotate.js"), "--in", str(src.resolve()),     # node runs in NODE_DIR:
                            "--spec", str(spec_path.resolve()), "--out", str(out.resolve())],   # absolute paths only
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


def image_size(path):
    """(width, height) of a PNG (IHDR) or JPEG (SOF) — stdlib only; unknown — None."""
    try:
        with open(path, "rb") as f:
            head = f.read(64 * 1024)
    except OSError:
        return None
    if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
        return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    if head[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(head):
            if head[i] != 0xFF:
                i += 1
                continue
            marker, size = head[i + 1], int.from_bytes(head[i + 2:i + 4], "big")
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                return int.from_bytes(head[i + 7:i + 9], "big"), int.from_bytes(head[i + 5:i + 7], "big")
            i += 2 + size
    return None


def sheet_inputs(files=(), from_dir=None, glob="*.png", soak=None):
    """Screenshots for a contact sheet: explicit files, a folder (glob, by name) or a soak summary (its screenshots)."""
    out = [Path(f) for f in files]
    if from_dir:   # natural order: t5m before t10m
        out += sorted((p for p in Path(from_dir).glob(glob) if p.is_file()),
                      key=lambda p: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", p.name)])
    if soak:
        try:
            data = json.loads(Path(soak).read_text(encoding="utf-8"))
        except (OSError, ValueError) as ex:
            raise AnnotateError(f"--soak: не читается сводка {soak}: {ex}", 2)
        base = Path(soak).resolve().parent.parent / "screenshots"
        for s in data.get("screenshots") or []:
            p = Path(s)
            out.append(p if p.is_file() else base / p.name)    # the run folder may have been moved
    seen, res = set(), []
    for p in out:
        if p.suffix.lower() in (".png", ".jpg", ".jpeg") and p.is_file() and p.resolve() not in seen:
            seen.add(p.resolve())
            res.append(p)
    return res


def sheet_html(items, html_path, cols):
    """A contact sheet for people (stdlib, always): an HTML grid with relative links and captions."""
    from html import escape
    rows = []
    for it in items:
        rel = os.path.relpath(it["file"], Path(html_path).resolve().parent).replace(os.sep, "/")  # both resolved
        rows.append(f'<figure><a href="{escape(rel)}"><img src="{escape(rel)}" loading="lazy" alt="{escape(it["caption"])}"></a>'
                    f'<figcaption>{escape(it["caption"])}</figcaption></figure>')
    Path(html_path).write_text(
        "<!doctype html>\n<meta charset=\"utf-8\"><title>Контактный лист</title>\n<style>body{margin:0;padding:8px;"
        "background:#1b1b1b;color:#eee;font:12px -apple-system,'Segoe UI',Arial,sans-serif;display:grid;"
        f"grid-template-columns:repeat({cols},minmax(0,1fr));gap:12px}}figure{{margin:0}}img{{width:100%;height:auto;"
        "display:block;border:1px solid #555;background:#fff}figcaption{padding:3px 0;word-break:break-all}</style>\n"
        + "\n".join(rows) + "\n", encoding="utf-8")
    return str(html_path)


def contact_sheet(files, out, cols=4, per=8, thumb=240, html_only=False):
    """Contact sheet: always an HTML grid (<out>.html); a PNG sheet (≤ per shots each, for one Read) through
    node/sheet.js when Node + Playwright are available, otherwise AnnotateError(4) — the HTML is still written."""
    if not files:
        raise AnnotateError("нет снимков для листа (файлы, --dir или --soak)", 2)
    if not 1 <= cols <= 8 or not 1 <= per <= 24 or not 80 <= thumb <= 600:
        raise AnnotateError("--cols 1–8, --per 1–24, --thumb 80–600", 2)
    out = Path(out)
    if out.suffix.lower() != ".png":
        raise AnnotateError("--out: файл .png (листов больше одного — -1.png, -2.png …)", 2)
    out.parent.mkdir(parents=True, exist_ok=True)
    items = []
    for f in files:
        size = image_size(f)
        items.append({"file": str(Path(f).resolve()), "caption": Path(f).stem + (f" · {size[0]}×{size[1]}" if size else "")})
    res = {"ok": False, "count": len(items), "html": sheet_html(items, out.with_suffix(".html"), cols), "sheets": []}
    if html_only:
        res["ok"] = True
        return res
    spec = out.with_suffix(".sheet.json")
    spec.write_text(json.dumps({"out": str(out.resolve()), "cols": cols, "per": per, "thumb": thumb, "items": items},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        node, modules = node_cmd()
    except AnnotateError as ex:
        raise AnnotateError(f"{ex} — собран только HTML-лист для человека: {res['html']}; модели смотреть снимки по одному", 4)
    try:
        p = subprocess.run([node, str(NODE_DIR / "sheet.js"), "--spec", str(spec.resolve())], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=dict(os.environ, NODE_PATH=str(modules)),
                           cwd=str(NODE_DIR), timeout=300)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise AnnotateError(f"sheet.js не запустился: {ex}", 5)
    try:
        sheets = json.loads(p.stdout.strip().splitlines()[-1]).get("sheets") or []
    except (ValueError, IndexError, AttributeError):
        sheets = []
    if p.returncode != 0 or not sheets or not all(Path(s).is_file() for s in sheets):
        raise AnnotateError(f"sheet.js: код {p.returncode}: {(p.stderr or p.stdout).strip()[-300:]}", 5)
    res.update({"ok": True, "sheets": sheets, "per": per,
                "must_view": f"посмотреть {', '.join(Path(s).name for s in sheets)} (Read; по {per} снимков на лист) — "
                             "подозрительный снимок открыть целиком"})
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
    s = sub.add_parser("sheet")
    s.add_argument("files", nargs="*", help="PNG/JPEG снимки")
    s.add_argument("--dir", help="папка со снимками (вместо списка или вместе с ним)")
    s.add_argument("--glob", default="*.png", help="шаблон имён в --dir (по умолчанию *.png)")
    s.add_argument("--soak", help="сводка raw/soak-<tag>-<serial>.json: её скриншоты")
    s.add_argument("--out", required=True, help="лист .png (рядом — .html для человека)")
    s.add_argument("--cols", type=int, default=4)
    s.add_argument("--per", type=int, default=8, help="снимков на лист (больше — несколько листов)")
    s.add_argument("--thumb", type=int, default=240, help="ширина миниатюры, px")
    s.add_argument("--html-only", action="store_true", help="только HTML-лист (без Node)")
    a = ap.parse_args()
    try:
        if a.cmd == "sheet":
            try:
                res = contact_sheet(sheet_inputs(a.files, a.dir, a.glob, a.soak), a.out, a.cols, a.per, a.thumb, a.html_only)
            except AnnotateError as ex:
                html = Path(a.out).with_suffix(".html")
                print(json.dumps({"ok": False, "error": str(ex), "html": str(html) if html.is_file() else None},
                                 ensure_ascii=False))
                sys.exit(ex.code)
            print(json.dumps(res, ensure_ascii=False, indent=1))
            return
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
