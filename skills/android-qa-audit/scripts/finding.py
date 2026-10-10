#!/usr/bin/env python3
"""Findings without hand-written JSON (references/screenshots.md, run-files.md): add a finding to
<RUN_DIR>/findings.json with a screenshot and its annotation in one command, list them, mark the annotated
screenshot as viewed. The finding is checked against templates/finding.schema.json before it is written.

  finding.py add <RUN_DIR> --title T --severity high --direction functional [--check-id fn.x] [--type bug]
                 [--screen Activity] [--element "id=btn"] [--step "…"]… [--expected …] [--actual …]
                 [--shot screenshots/x.png] [--mark "x,y,w,h|подпись|error"]… [--ui raw/ui-….xml] [--density 420]
                 [--serial S] [--env key=value]… [--repro-rate 2/2] [--frequency always] [--suggestion …]
                 [--hypothesis …] [--source own:checklist] [--repro "find --text …"] [--id F-012] [--json]
  finding.py shot <RUN_DIR> --id F-003 --shot screenshots/y.png [--mark …]… [--ui …] [--density 420]
  finding.py viewed <RUN_DIR> --id F-003 [--clips]  the annotated screenshots (and with --clips the clips' frame
                                                  sheets) were looked at (Read) — before publication
  finding.py clip <RUN_DIR> --id F-003 --file clips/F-003-menu.mp4 [--kind error|ok|note|after] [--caption "…"]
                 [--step "…"]…   attach a clip (references/clips.md); a file outside clips/ is compressed into clips/
                 first (qa_clips.finalize: no sound, ≤ clips.max_mb, GIF, poster, frame sheet)
  finding.py clip-viewed <RUN_DIR> --id F-003 [--file clips/…mp4]   the frame sheet (clips/…-sheet.png) was looked at
  finding.py list <RUN_DIR> [--json]               also: clips and the ones not viewed yet

--shot outside <RUN_DIR>/screenshots/ is copied there as F-NNN-<name>.png. --mark draws the annotation
(annotate_android.py): shots: [{original, annotated, spec, marks, viewed}], screenshots: [annotated, original].
Without Node/Playwright the original and the spec are kept and the reason is printed (exit 0, warning).
--serial fills environment from the device (read-only: getprop, wm size/density, font scale, night mode).
Exit codes: 0 ok, 1 schema errors (nothing written), 2 bad input.
"""
import argparse
import json
import re
import shlex
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
sys.path.insert(0, str(HERE))
import miniyaml  # noqa: E402
import qa_clips  # noqa: E402 — clips of findings (1.5.0)
from masking import mask  # noqa: E402

SCHEMA = HERE.parent / "templates" / "finding.schema.json"


def fail(msg, code=2):
    sys.stderr.write(f"finding: {msg}\n")
    sys.exit(code)


def load(run_dir):
    p = Path(run_dir) / "findings.json"
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            data = {"run": {}, "findings": data}
        return p, data
    cfg = {}
    if (Path(run_dir) / "run-config.yaml").exists():
        cfg = miniyaml.load_file(Path(run_dir) / "run-config.yaml") or {}
    run = {"id": Path(run_dir).name, "app": (cfg.get("app") or {}).get("package") or "", "depth": cfg.get("depth") or "standard",
           "mode": cfg.get("mode") if cfg.get("mode") in ("live", "dry-run") else "dry-run",
           "started_at": datetime.now().isoformat(timespec="seconds")}
    return p, {"run": run, "findings": []}


def next_id(findings):
    nums = [int(m.group(1)) for f in findings for m in [re.match(r"^F-(\d+)$", str(f.get("id", "")))] if m]
    return f"F-{(max(nums) + 1) if nums else 1:03d}"


def validate_one(f):
    """Schema check of the new finding only (old findings of the file are not re-judged here)."""
    import validate_findings as vf
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = []
    vf.check(f, schema["$defs"]["finding"], schema, f.get("id", "finding"), errors)
    return errors


def device_env(serial):
    """environment from a device: api, android_version, device_profile (model), screen, font, dark mode (read-only)."""
    import sdkutil as su
    adb = su.Adb(serial)
    p = adb.getprop()
    s = su.device_summary(p)
    _, size, _ = adb.shell("wm", "size", timeout=10)
    _, dens, _ = adb.shell("wm", "density", timeout=10)
    _, fs, _ = adb.shell("settings", "get", "system", "font_scale", timeout=10)
    _, night, _ = adb.shell("cmd", "uimode", "night", timeout=10)
    _, mem, _ = adb.shell("cat", "/proc/meminfo", timeout=10)
    import adb_helpers as h
    env = {"api": s.get("api"), "android_version": s.get("release"), "device_profile": s.get("model"),
           "abi": s.get("abi"), "stand": "own-emulator" if s.get("emulator") else "real",
           "date": datetime.now().strftime("%Y-%m-%d")}
    sz, dn = h.parse_wm(size), h.parse_wm(dens)
    if sz:
        env["screen"] = f"{sz}@{dn}" if dn else sz
    try:
        env["font_scale"] = float(fs.strip())
    except ValueError:
        pass
    env["dark_mode"] = "yes" in night.lower()
    m = re.search(r"MemTotal:\s+(\d+)", mem)
    if m:
        env["ram_mb"] = int(m.group(1)) // 1024
    if s.get("avd_name"):
        env["avd"] = s["avd_name"]
    return {k: v for k, v in env.items() if v not in (None, "")}, int(dn) if dn and dn.isdigit() else None


def put_shot(run, fid, src):
    src = Path(src)
    if not src.is_absolute():
        src = (run / src) if (run / src).exists() else Path.cwd() / src
    if not src.is_file():
        fail(f"нет файла {src}")
    shots = run / "screenshots"
    try:
        rel = src.resolve().relative_to(run.resolve())
        if rel.parts[0] == "screenshots":
            return src, str(rel)
    except ValueError:
        pass
    shots.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.-]+", "-", src.stem)
    dest = shots / f"{fid}-{safe}{src.suffix}"
    shutil.copyfile(src, dest)
    return dest, str(dest.relative_to(run))


def attach(run, f, shot, marks, ui, density):
    """Add a screenshot (and its annotation) to finding f. Returns (shot entry, warning or None)."""
    path, rel = put_shot(run, f["id"], shot)
    entry = {"original": rel, "annotated": None, "marks": [], "viewed": False}
    warn = None
    if marks:
        import annotate_android as an
        try:
            parsed = [an.parse_mark(m) for m in marks]
            res = an.render(path, parsed, density or 420, None, an.ui_nodes(ui) if ui else None)
            entry.update({"annotated": str(Path(res["annotated"]).resolve().relative_to(run.resolve())),
                          "spec": str(Path(res["spec"]).resolve().relative_to(run.resolve())), "marks": res["marks"],
                          "check": {"ok": res["ok"], "warnings": res["warnings"]}})
            if res["warnings"]:
                warn = "аннотация: " + "; ".join(res["warnings"])
        except an.AnnotateError as ex:
            warn = f"аннотация не нарисована: {ex}"
            entry["marks"] = [m for m in marks]
    f.setdefault("shots", []).append(entry)
    shots = [x for x in [entry["annotated"], entry["original"]] if x]
    f["screenshots"] = list(dict.fromkeys(shots + [x for x in f.get("screenshots") or [] if isinstance(x, str)]))
    return entry, warn


def cmd_add(a):
    run = Path(a.run_dir)
    if not run.is_dir():
        fail(f"нет папки прогона {run}")
    path, data = load(run)
    fs = data["findings"]
    fid = a.id or next_id(fs)
    if any(f.get("id") == fid for f in fs):
        fail(f"находка {fid} уже есть — другой --id или finding.py shot")
    env, dens = (device_env(a.serial) if a.serial else ({}, None))
    for kv in a.env or []:
        k, _, v = kv.partition("=")
        env[k.strip()] = int(v) if v.strip().isdigit() else (float(v) if re.fullmatch(r"\d+\.\d+", v.strip()) else v.strip())
    f = {"id": fid, "direction": a.direction, "check_id": a.check_id or f"{a.direction.split('-')[0]}.manual",
         "type": a.type, "severity": a.severity, "title": mask(a.title), "screen": a.screen or "",
         "sources": a.source or ["own:checklist"]}
    for key, val in (("element", a.element), ("expected", a.expected), ("actual", a.actual), ("suggestion", a.suggestion),
                     ("hypothesis", a.hypothesis), ("repro_rate", a.repro_rate), ("frequency", a.frequency),
                     ("app_version", a.app_version), ("question", a.question)):
        if val:
            f[key] = mask(val) if isinstance(val, str) else val
    if a.step:
        f["steps"] = [mask(s) for s in a.step]
    if env:
        f["environment"] = env
    if a.repro:
        f["repro"] = {"adb": shlex.split(a.repro), "expect_exit": 0}
    warn = None
    fs.append(f)
    if a.shot:
        _, warn = attach(run, f, a.shot, a.mark, a.ui, a.density or dens)
    for clip in a.clip or []:
        add_clip(f, clip_entry(run, fid, clip, a.clip_kind, a.clip_caption, f.get("steps")))
    errors = validate_one(f)
    if errors:
        for e in errors:
            print("ERROR", e)
        fail("находка не записана — исправить поля", 1)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    out = {"ok": True, "id": fid, "file": str(path), "screenshots": f.get("screenshots", []), "warning": warn,
           "next": "посмотреть аннотированный снимок (Read), затем finding.py viewed " + f"{run} --id {fid}"
           if f.get("shots") and f["shots"][-1].get("annotated") else ""}
    print(json.dumps(out, ensure_ascii=False, indent=1 if a.json else None))


def find(data, fid):
    hit = [f for f in data["findings"] if f.get("id") == fid]
    if not hit:
        fail(f"нет находки {fid}")
    return hit[0]


def cmd_shot(a):
    run = Path(a.run_dir)
    path, data = load(run)
    f = find(data, a.id)
    dens = a.density
    entry, warn = attach(run, f, a.shot, a.mark, a.ui, dens)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"ok": True, "id": a.id, "shot": entry, "warning": warn}, ensure_ascii=False))


def cmd_viewed(a):
    run = Path(a.run_dir)
    path, data = load(run)
    f = find(data, a.id)
    for s in f.get("shots") or []:
        s["viewed"] = True
    clips = [c for c in f.get("clips") or [] if isinstance(c, dict)] if a.clips else []
    for c in clips:
        c["viewed"] = True
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"ok": True, "id": a.id, "viewed": len(f.get("shots") or []), "clips_viewed": len(clips)},
                     ensure_ascii=False))


# ---------- clips (1.5.0, references/clips.md) ----------

def resolve_file(run, value):
    p = Path(value)
    if not p.is_absolute():
        p = (run / p) if (run / p).exists() else Path.cwd() / p
    if not p.is_file():
        fail(f"нет файла {value}")
    return p


def clip_entry(run, fid, value, kind="error", caption="", steps=None):
    """findings[].clips[] entry for a file: a finished clip in clips/ (its GIF, poster and frame sheet are found by
    name) or any video — then it is compressed into clips/<F-NNN>-<name>.mp4 first (no sound, budget, sheet)."""
    run = Path(run)
    p = resolve_file(run, value)
    rc = miniyaml.load_file(run / "run-config.yaml") if (run / "run-config.yaml").exists() else {}
    cfg = {"clips": (rc or {}).get("clips") if isinstance((rc or {}).get("clips"), dict) else {}}
    try:
        import gitignore_helper
        gitignore_helper.ensure_run_ignore(run)
    except OSError:
        pass
    clips = (run / "clips").resolve()
    if p.suffix.lower() not in qa_clips.VIDEO_EXT:
        fail(f"{p.name}: нужен ролик ({', '.join(qa_clips.VIDEO_EXT)})")
    if p.resolve().parent == clips:
        side = lambda suffix: p.with_name(p.stem + suffix) if p.with_name(p.stem + suffix).is_file() else None  # noqa: E731
        sheet = side("-sheet.png")
        e = qa_clips.entry(p, run, kind, mask(caption or ""), gif=side(".gif"), poster_file=side("-poster.png"),
                           steps=steps, extra={"sheet": str(sheet.resolve().relative_to(run.resolve())) if sheet else None})
        issues = [x[1] for x in qa_clips.check_entry(dict(e, viewed=True), run, cfg)]
        if issues:
            e["warning"] = "; ".join(issues)
        return e
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", p.stem).strip("-.") or "clip"
    name = name if name.startswith(fid) else f"{fid}-{name}"
    n, i = name, 2
    while (run / "clips" / f"{n}.mp4").exists():
        n, i = f"{name}-{i}", i + 1
    fin = qa_clips.finalize(p, run, n, cfg, caption=mask(caption or ""), kind=kind, steps=steps)
    if not fin["ok"]:
        fail(f"ролик не сжат: {(fin.get('result') or {}).get('warning')}", 1)
    return fin["entry"]


def add_clip(f, e):
    """qa_clips.add_to_finding, but the viewed mark survives re-attaching the very same file (same sha256)."""
    old = next((c for c in f.get("clips") or [] if isinstance(c, dict) and c.get("file") == e["file"]), None)
    if old and old.get("viewed") and old.get("sha256") and old.get("sha256") == e.get("sha256"):
        e["viewed"] = True
    return qa_clips.add_to_finding(f, e)


def attach_clip(run_dir, fid, e):
    """Write a clip entry into finding fid (used by adb_helpers.py clip-stop / clip / clip-rolling save --finding)."""
    run = Path(run_dir)
    path, data = load(run)
    f = find(data, fid)
    add_clip(f, e)
    errors = validate_one(f)
    if errors:
        for x in errors:
            sys.stderr.write(f"finding: {x}\n")
        fail("ролик не записан в находку — схема", 1)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return f


def cmd_clip(a):
    run = Path(a.run_dir)
    path, data = load(run)
    f = find(data, a.id)
    e = clip_entry(run, a.id, a.file, a.kind, a.caption, a.step or f.get("steps"))
    add_clip(f, e)
    errors = validate_one(f)
    if errors:
        for x in errors:
            print("ERROR", x)
        fail("ролик не записан — исправить поля", 1)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    nxt = (f"посмотреть ленту кадров {e['sheet']} (Read), затем finding.py clip-viewed {run} --id {a.id} --file {e['file']}"
           if e.get("sheet") else "ленты кадров нет (без ffmpeg) — посмотреть кадры по шагам, затем finding.py clip-viewed")
    print(json.dumps({"ok": True, "id": a.id, "clip": e, "warning": e.get("warning"), "next": "" if e.get("viewed") else nxt},
                     ensure_ascii=False, indent=1 if a.json else None))


def cmd_clip_viewed(a):
    run = Path(a.run_dir)
    path, data = load(run)
    f = find(data, a.id)
    clips = [c for c in f.get("clips") or [] if isinstance(c, dict)]
    if a.file:
        want = a.file.replace("\\", "/")
        clips = [c for c in clips if c.get("file") == want or Path(c.get("file") or "").name == Path(want).name]
    if not clips:
        fail(f"у находки {a.id} нет {'такого ролика' if a.file else 'роликов'} (finding.py clip)")
    notes = []
    for c in clips:
        c["viewed"] = True
        if not (c.get("sheet") and (run / c["sheet"]).is_file()) and not c.get("frames"):
            notes.append(f"{c.get('file')}: ленты кадров нет — подтверждение только если ролик или кадры по шагам просмотрены")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"ok": True, "id": a.id, "clips_viewed": [c.get("file") for c in clips], "notes": notes},
                     ensure_ascii=False))


def cmd_list(a):
    _, data = load(Path(a.run_dir))
    if a.json:
        print(json.dumps(data["findings"], ensure_ascii=False, indent=1))
        return
    for f in data["findings"]:
        shots = f.get("shots") or []
        notv = sum(1 for s in shots if s.get("annotated") and not s.get("viewed"))
        clips = [c for c in f.get("clips") or [] if isinstance(c, dict)]
        notc = sum(1 for c in clips if not c.get("viewed"))
        print(f"{f['id']} [{f.get('severity')}] {f.get('status') or 'NEW'} {f.get('title')}"
              + (f" · снимков {len(f.get('screenshots') or [])}" if f.get("screenshots") else "")
              + (f" · не просмотрено аннотаций: {notv}" if notv else "")
              + (f" · роликов {len(clips)}" if clips else "")
              + (f" · не просмотрено роликов: {notc} (лента кадров → finding.py clip-viewed)" if notc else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    p.add_argument("run_dir")
    p.add_argument("--title", required=True)
    p.add_argument("--severity", required=True, choices=["critical", "high", "medium", "low", "info"])
    p.add_argument("--direction", required=True)
    p.add_argument("--check-id")
    p.add_argument("--type", default="bug")
    p.add_argument("--screen")
    p.add_argument("--element")
    p.add_argument("--step", action="append")
    p.add_argument("--expected")
    p.add_argument("--actual")
    p.add_argument("--suggestion")
    p.add_argument("--hypothesis")
    p.add_argument("--question")
    p.add_argument("--repro-rate")
    p.add_argument("--frequency", choices=["always", "sometimes", "once"])
    p.add_argument("--app-version")
    p.add_argument("--source", action="append")
    p.add_argument("--repro", help="аргументы adb_helpers.py для перепроверки: \"find --text Купить\"")
    p.add_argument("--serial", help="заполнить environment с устройства (только чтение)")
    p.add_argument("--env", action="append", help="key=value в environment (api=34, cell=c01, …)")
    p.add_argument("--id")
    p.add_argument("--json", action="store_true")
    p.add_argument("--clip", action="append", help="ролик находки (clips/….mp4 или любой ролик — будет сжат в clips/)")
    p.add_argument("--clip-kind", default="error", choices=list(qa_clips.KINDS))
    p.add_argument("--clip-caption", default="", help="подпись-факт ролика")
    for q in (p, sub.add_parser("shot")):
        if q is not p:
            q.add_argument("run_dir")
            q.add_argument("--id", required=True)
            q.add_argument("--shot", required=True)
        else:
            q.add_argument("--shot")
        q.add_argument("--mark", action="append", default=[])
        q.add_argument("--ui", help="raw/ui-….xml для отметок text=/id=/desc=")
        q.add_argument("--density", type=float, help="dpi снимка (по умолчанию — с --serial или 420)")
    v = sub.add_parser("viewed")
    v.add_argument("run_dir")
    v.add_argument("--id", required=True)
    v.add_argument("--clips", action="store_true", help="и ролики находки (их ленты кадров просмотрены)")
    cl = sub.add_parser("clip")
    cl.add_argument("run_dir")
    cl.add_argument("--id", required=True)
    cl.add_argument("--file", required=True, help="clips/F-003-menu.mp4 или любой ролик (будет сжат в clips/)")
    cl.add_argument("--kind", default="error", choices=list(qa_clips.KINDS))
    cl.add_argument("--caption", default="")
    cl.add_argument("--step", action="append")
    cl.add_argument("--json", action="store_true")
    cv = sub.add_parser("clip-viewed")
    cv.add_argument("run_dir")
    cv.add_argument("--id", required=True)
    cv.add_argument("--file", help="один ролик; без него — все ролики находки")
    ls = sub.add_parser("list")
    ls.add_argument("run_dir")
    ls.add_argument("--json", action="store_true")
    a = ap.parse_args()
    {"add": cmd_add, "shot": cmd_shot, "viewed": cmd_viewed, "list": cmd_list, "clip": cmd_clip,
     "clip-viewed": cmd_clip_viewed}[a.cmd](a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
