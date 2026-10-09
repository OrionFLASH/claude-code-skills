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
  finding.py viewed <RUN_DIR> --id F-003         the annotated screenshots were looked at (Read) — before publication
  finding.py list <RUN_DIR> [--json]

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
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"ok": True, "id": a.id, "viewed": len(f.get("shots") or [])}, ensure_ascii=False))


def cmd_list(a):
    _, data = load(Path(a.run_dir))
    if a.json:
        print(json.dumps(data["findings"], ensure_ascii=False, indent=1))
        return
    for f in data["findings"]:
        shots = f.get("shots") or []
        notv = sum(1 for s in shots if s.get("annotated") and not s.get("viewed"))
        print(f"{f['id']} [{f.get('severity')}] {f.get('status') or 'NEW'} {f.get('title')}"
              + (f" · снимков {len(f.get('screenshots') or [])}" if f.get("screenshots") else "")
              + (f" · не просмотрено аннотаций: {notv}" if notv else ""))


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
    ls = sub.add_parser("list")
    ls.add_argument("run_dir")
    ls.add_argument("--json", action="store_true")
    a = ap.parse_args()
    {"add": cmd_add, "shot": cmd_shot, "viewed": cmd_viewed, "list": cmd_list}[a.cmd](a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
