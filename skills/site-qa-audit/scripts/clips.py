#!/usr/bin/env python3
"""Ролики находок site-qa-audit (references/clips.md): тонкая обёртка над scripts/shared/qa_clips.py.

  clips.py finalize <RUN_DIR> --src raw.webm --name F-004-menu [--caption "…"] [--kind error|ok|note|after]
                    [--finding F-004] [--step "…" …] [--start 0.0] [--subdir clips] [--format mp4|gif|both]
                    [--max-seconds 10] [--max-mb 3] [--no-burn-caption] [--keep-raw]
      сжать под бюджет (H.264, без звука), GIF (короткий ролик), постер, ленту кадров → <RUN_DIR>/clips/<name>.mp4|.gif|
      -poster.png|-sheet.png; с --finding — запись в findings[].clips[] (и путь в recordings[]) файла findings.json.
      Печатает JSON одной строкой {ok, clip, files, warnings}. Код 0 готово, 1 готово с предупреждением (бюджет, нет
      ffmpeg — ролик сохранён как есть), 2 ошибка входа.
  clips.py check <RUN_DIR> [--id F-004] [--json]     все ролики находок: файл, размер, длительность, звук, sha, viewed, GIF
  clips.py viewed <RUN_DIR> --id F-004 [--file clips/F-004-menu.mp4] [--force]
                                                      отметить просмотр — ТОЛЬКО после Read ленты кадров (-sheet.png)
  clips.py list <RUN_DIR> [--json]                   ролики по находкам
  clips.py sheet <RUN_DIR> (--id F-004 | --file clips/F-004-menu.mp4) [--frames 8]   пересобрать ленту кадров
  clips.py caps [--json]                             что умеет окружение: ffmpeg/ffprobe, кодеки, Playwright screencast
  clips.py policy "<текст находки>" [--run-dir RUN_DIR] [--mode auto|on|off] [--direction D]
                                                      нужен ли ролик (qa_clips.should_record с clips.mode из run-config)
  clips.py settings [RUN_DIR]                        настройки clips: из run-config с умолчаниями (JSON)
  clips.py ignore <RUN_DIR>                          clips/ и recordings/ в <RUN_DIR>/.gitignore (finalize делает сам)

Пути в записях — относительно <RUN_DIR>. Непросмотренный ролик (viewed: false) в черновики issues и публикацию не идёт.
Модули для других скриптов скила: clips_of, normalize_finding_clips, clip_files, fmt_seconds, fmt_mb.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
sys.path.insert(0, str(HERE))
import miniyaml  # noqa: E402
import qa_clips  # noqa: E402

NODE_DIR = HERE / "node"
CLIP_EXT = (".mp4", ".webm", ".mov", ".gif")
IGNORE_LINES = ["clips/", "recordings/"]


# ---------- общие функции (ingest_findings, build_report, render_draft, publish_shots, export_results) ----------
def load_cfg(run_dir):
    p = Path(run_dir) / "run-config.yaml" if run_dir else None
    if p and p.is_file():
        try:
            return miniyaml.load_file(str(p)) or {}
        except Exception:  # noqa: BLE001 — битый run-config не мешает роликам: умолчания
            return {}
    return {}


def settings_of(run_dir=None):
    return qa_clips.settings(load_cfg(run_dir))


def clips_of(finding):
    """Ролики находки как список словарей (строка-путь → {"file": путь}); мусор пропускается."""
    out = []
    for c in (finding or {}).get("clips") or []:
        if isinstance(c, str) and c.strip():
            out.append({"file": c.strip()})
        elif isinstance(c, dict) and c.get("file"):
            out.append(c)
    return out


def _inside(path, folder):
    try:
        Path(path).resolve().relative_to(Path(folder).resolve())
        return True
    except ValueError:
        return False


def normalize_finding_clips(finding, run_dir, cfg=None):
    """Проверить и привести finding['clips'] к записям qa_clips.entry (на месте). -> список предупреждений.
    Не принимается (удаляется из находки): файл вне <RUN_DIR>, нет файла, расширение не ролика. Больше бюджета ×1,05,
    звук, длиннее max_seconds — принимается с предупреждением."""
    raw = finding.get("clips")
    if raw in (None, []):
        return []
    s = qa_clips.settings(cfg or {})
    run = Path(run_dir).resolve()
    fid = finding.get("id") or finding.get("title") or "?"
    warnings, kept = [], []
    for c in raw if isinstance(raw, list) else [raw]:
        rec = {"file": c} if isinstance(c, str) else dict(c) if isinstance(c, dict) else None
        if not rec or not rec.get("file"):
            warnings.append(f"{fid}: ролик без пути к файлу — не принят")
            continue
        ref = str(rec["file"]).strip()
        p = Path(ref).expanduser()
        p = p if p.is_absolute() else run / ref
        if not _inside(p, run):
            warnings.append(f"{fid}: ролик {ref} вне папки прогона — не принят (только <RUN_DIR>/clips/)")
            continue
        if p.suffix.lower() not in CLIP_EXT:
            warnings.append(f"{fid}: {ref} — не ролик ({', '.join(CLIP_EXT)}) — не принят")
            continue
        if not p.is_file():
            warnings.append(f"{fid}: файл ролика не найден: {ref} — не принят")
            continue
        rel = p.resolve().relative_to(run).as_posix()
        if "sha256" not in rec or "bytes" not in rec:
            base = qa_clips.entry(p, run, rec.get("kind") or "error", rec.get("caption") or "", steps=rec.get("steps"))
            base.update({k: v for k, v in rec.items() if v not in (None, "") and k != "file"})
            rec = base
        rec["file"] = rel
        rec["kind"] = rec.get("kind") if rec.get("kind") in qa_clips.KINDS else "error"
        rec.setdefault("viewed", False)
        size = p.stat().st_size
        if size > s["max_mb"] * 1048576 * 1.05:
            warnings.append(f"{fid}: ролик {rel} {size / 1048576:.2f} МБ больше бюджета {s['max_mb']:.1f} МБ — сократить "
                            "(clips.py finalize с меньшим --max-seconds)")
        if rec.get("audio"):
            warnings.append(f"{fid}: в ролике {rel} есть звук — пересобрать через clips.py finalize (без звука)")
        if rec.get("seconds") and rec["seconds"] > s["max_seconds"] + 0.5:
            warnings.append(f"{fid}: ролик {rel} длиннее {s['max_seconds']:.0f} с")
        for k in ("gif", "poster", "sheet"):
            v = rec.get(k)
            if v and not ((run / v).is_file() and _inside(run / v, run)):
                warnings.append(f"{fid}: {k} {v} не найден — поле убрано")
                rec[k] = None
        kept.append(rec)
    finding["clips"] = kept
    if kept:
        rec_list = [r for r in finding.get("recordings") or [] if isinstance(r, str)]
        for r in kept:
            if r["file"] not in rec_list:
                rec_list.append(r["file"])
        finding["recordings"] = rec_list
    else:
        finding.pop("clips", None)
    return warnings


def clip_files(run_dir, findings, viewed_only=True, ids=None):
    """[(id находки, относительный путь, абсолютный путь, kind: video|gif|poster)] для публикации."""
    out, run = [], Path(run_dir)
    for f in findings or []:
        if ids and f.get("id") not in ids:
            continue
        if (f.get("evidence") or {}).get("sensitive"):
            continue
        for c in clips_of(f):
            if viewed_only and not c.get("viewed"):
                continue
            for key, kind in (("file", "video"), ("gif", "gif")):
                v = c.get(key)
                if v and (run / v).is_file() and _inside(run / v, run):
                    out.append((f.get("id"), v, run / v, kind))
    return out


def fmt_seconds(x):
    if not x:
        return "?"
    x = float(x)
    return (f"{x:.0f}" if abs(x - round(x)) < 0.05 else f"{x:.1f}".replace(".", ",")) + " с"


def fmt_mb(n):
    if not n:
        return "?"
    mb = float(n) / 1048576
    return (f"{mb:.2f}" if mb < 0.1 else f"{mb:.1f}").replace(".", ",") + " МБ"


def ensure_ignored(run_dir):
    """clips/ и recordings/ — в <RUN_DIR>/.gitignore (ролики не коммитятся даже при git.allow_commit_results)."""
    p = Path(run_dir) / ".gitignore"
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    have = {ln.strip() for ln in text.splitlines()}
    add = [x for x in IGNORE_LINES if x not in have and "/" + x not in have]
    if add:
        p.parent.mkdir(parents=True, exist_ok=True)
        head = "" if not text or text.endswith("\n") else "\n"
        p.write_text(text + head + "# site-qa-audit: ролики находок не коммитятся (references/clips.md)\n" +
                     "\n".join(add) + "\n", encoding="utf-8")
    return {"file": str(p), "added": add}


def playwright_info(node_dir=NODE_DIR):
    """Версия Playwright скила и есть ли page.screencast (по типам пакета, без запуска браузера)."""
    core = Path(node_dir) / "node_modules" / "playwright-core"
    info = {"version": None, "screencast": False, "path": str(core)}
    try:
        info["version"] = json.loads((core / "package.json").read_text(encoding="utf-8")).get("version")
        types = (core / "types" / "types.d.ts").read_text(encoding="utf-8", errors="replace")
        info["screencast"] = bool(re.search(r"\bscreencast:\s*Screencast\b", types))
    except (OSError, ValueError):
        pass
    return info


# ---------- findings.json ----------
def _findings_path(run_dir):
    return Path(run_dir) / "findings.json"


def _load_findings(run_dir):
    p = _findings_path(run_dir)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _save_findings(run_dir, data):
    p = _findings_path(run_dir)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def _items(data):
    return (data.get("findings") if isinstance(data, dict) else data) or []


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- команды ----------
def cmd_finalize(a):
    run = Path(a.run_dir)
    src = Path(a.src)
    if not run.is_dir():
        return _out({"ok": False, "error": f"нет папки прогона {run}"}, 2)
    if not src.is_file() or src.stat().st_size == 0:
        return _out({"ok": False, "error": f"исходный ролик пуст или не найден: {src}"}, 2)
    if not re.fullmatch(r"[\w.-]+", a.name) or a.name.startswith("."):
        return _out({"ok": False, "error": f"имя ролика «{a.name}»: латиница, цифры, «-», «_», «.» (F-004-menu)"}, 2)
    sub = (a.subdir or "clips").strip("/")
    if not sub or ".." in Path(sub).parts or Path(sub).is_absolute():
        return _out({"ok": False, "error": f"--subdir {a.subdir}: папка внутри прогона (clips)"}, 2)
    cfg = dict(settings_of(run))
    for k, v in (("format", a.format), ("max_seconds", a.max_seconds), ("max_mb", a.max_mb)):
        if v is not None:
            cfg[k] = v
    if a.no_burn_caption:
        cfg["caption"] = False  # подпись уже в кадре (clip.js рисует её в странице)
    if a.keep_raw:
        cfg["keep_raw"] = True
    s = qa_clips.settings(cfg)
    steps = list(a.step or [])
    if a.steps_json:
        try:
            steps += [str(x) for x in json.loads(Path(a.steps_json).read_text(encoding="utf-8"))]
        except (OSError, ValueError) as ex:
            return _out({"ok": False, "error": f"--steps-json: {ex}"}, 2)
    name = re.sub(r"\.(mp4|webm|mov|gif)$", "", a.name, flags=re.I)
    res = qa_clips.finalize(src, run, name, cfg=s, caption=a.caption or "", kind=a.kind, start=a.start or 0.0,
                            steps=steps, subdir=sub)
    if not res["ok"]:
        return _out({"ok": False, "error": res["result"].get("warning") or "ролик не сохранён", "result": res["result"]}, 2)
    e = res["entry"]
    if a.caption:
        e["caption"] = a.caption
    warnings = [w for w in [res["result"].get("warning"),
                            None if res["poster"].get("ok") else "постер: " + str(res["poster"].get("warning")),
                            None if res["sheet"].get("ok") else "лента кадров: " + str(res["sheet"].get("warning")) +
                            " — посмотреть ролик по скриншотам шагов"] if w]
    if e.get("audio"):
        warnings.append("в ролике осталась звуковая дорожка")
    br = qa_clips.black_ratio(run / e["file"]) if qa_clips.find_ffmpeg() else None
    if br is not None and br >= 0.8:
        warnings.append(f"ролик почти весь чёрный ({br:.0%} кадров): вкладка свёрнута или страница не отрисована — повторить")
    files = {k: str((run / e[k]).resolve()) for k in ("file", "gif", "poster", "sheet") if e.get(k)}
    ign = ensure_ignored(run)
    out = {"ok": True, "clip": e, "files": files, "warnings": warnings, "gitignore": ign["file"]}
    if a.finding:
        data = _load_findings(run)
        f = next((x for x in _items(data) if x.get("id") == a.finding), None) if data else None
        if f is None:
            warnings.append(f"находка {a.finding} не найдена в findings.json — ролик не записан в находку "
                            "(добавить позже: clips в блоке qa-findings или clips.py finalize … --finding)")
        else:
            qa_clips.add_to_finding(f, e)
            _save_findings(run, data)
            out["finding"] = a.finding
    if files.get("sheet"):
        out["next"] = (f"посмотреть ленту кадров (Read {files['sheet']}) и подтвердить: clips.py viewed {run} "
                       f"--id {a.finding or '<F-NNN>'} --file {e['file']}")
    return _out(out, 1 if warnings else 0)


def _out(obj, code):
    print(json.dumps(obj, ensure_ascii=False))
    return code


def _iter_clips(run, ids=None):
    data = _load_findings(run)
    if data is None:
        return None, []
    rows = []
    for f in _items(data):
        if ids and f.get("id") not in ids:
            continue
        for c in clips_of(f):
            rows.append((f, c))
    return data, rows


def cmd_check(a):
    run = Path(a.run_dir)
    data, rows = _iter_clips(run, {a.id} if a.id else None)
    if data is None:
        print(f"clips: нет {run}/findings.json", file=sys.stderr)
        return 2
    cfg = load_cfg(run)
    res = []
    for f, c in rows:
        issues = qa_clips.check_entry(c, run, cfg)
        if not issues and c.get("poster") and not (run / c["poster"]).is_file():
            issues.append(("poster-missing", f"постер не найден: {c['poster']}"))
        p = Path(c["file"])
        if not p.is_absolute() and not _inside(run / p, run):
            issues.insert(0, ("outside", "ролик вне папки прогона"))
        res.append({"id": f.get("id"), "file": c.get("file"), "seconds": c.get("seconds"), "bytes": c.get("bytes"),
                    "viewed": bool(c.get("viewed")), "issues": [{"code": k, "text": t} for k, t in issues]})
    bad = [r for r in res if r["issues"]]
    if a.json:
        print(json.dumps({"clips": res, "ok": not bad}, ensure_ascii=False, indent=1))
    else:
        if not res:
            print("роликов в находках нет")
        for r in res:
            mark = "OK" if not r["issues"] else "; ".join(i["text"] for i in r["issues"])
            print(f"{r['id']}  {r['file']}  {fmt_seconds(r['seconds'])}  {fmt_mb(r['bytes'])}  {mark}")
        if bad:
            print(f"с замечаниями: {len(bad)} из {len(res)} (непросмотренные в черновики и публикацию не идут)")
    return 1 if bad else 0


def cmd_viewed(a):
    run = Path(a.run_dir)
    data = _load_findings(run)
    if data is None:
        print(f"clips: нет {run}/findings.json", file=sys.stderr)
        return 2
    f = next((x for x in _items(data) if x.get("id") == a.id), None)
    if f is None:
        print(f"clips: находка {a.id} не найдена", file=sys.stderr)
        return 2
    changed, problems = [], []
    new = []
    for c in f.get("clips") or []:
        rec = {"file": c} if isinstance(c, str) else c
        if not isinstance(rec, dict) or (a.file and rec.get("file") != a.file):
            new.append(c)
            continue
        p = run / rec["file"]
        sheet = rec.get("sheet")
        if not p.is_file():
            problems.append(f"{rec['file']}: файла нет")
        elif rec.get("sha256") and qa_clips.sha256(p) != rec["sha256"]:
            problems.append(f"{rec['file']}: файл изменился после записи (sha256) — пересобрать clips.py finalize")
        elif not (sheet and (run / sheet).is_file()) and not a.force:
            problems.append(f"{rec['file']}: нет ленты кадров — clips.py sheet {run} --file {rec['file']}, Read, затем "
                            "viewed (без ffmpeg: просмотреть скриншоты шагов и --force)")
        else:
            rec["viewed"] = True
            rec["viewed_at"] = _now()
            changed.append(rec["file"])
        new.append(rec)
    if not changed and not problems:
        problems.append("у находки нет такого ролика" if a.file else "у находки нет роликов")
    if changed:
        f["clips"] = new
        _save_findings(run, data)
    print(json.dumps({"id": a.id, "viewed": changed, "problems": problems}, ensure_ascii=False))
    return 0 if changed and not problems else 1


def cmd_list(a):
    run = Path(a.run_dir)
    data, rows = _iter_clips(run)
    if data is None:
        print(f"clips: нет {run}/findings.json", file=sys.stderr)
        return 2
    items = [{"id": f.get("id"), "kind": c.get("kind"), "seconds": c.get("seconds"), "bytes": c.get("bytes"),
              "viewed": bool(c.get("viewed")), "file": c.get("file"), "gif": c.get("gif"), "sheet": c.get("sheet"),
              "caption": c.get("caption")} for f, c in rows]
    if a.json:
        print(json.dumps(items, ensure_ascii=False, indent=1))
    else:
        for i in items:
            print(f"{i['id']}  {i['kind'] or ''}  {fmt_seconds(i['seconds'])}  {fmt_mb(i['bytes'])}  "
                  f"{'просмотрен' if i['viewed'] else 'НЕ просмотрен'}  {i['file']}" + (f"  «{i['caption']}»" if i["caption"] else ""))
        if not items:
            print("роликов в находках нет")
    return 0


def cmd_sheet(a):
    run = Path(a.run_dir)
    targets = []
    if a.file:
        targets = [a.file]
    else:
        data, rows = _iter_clips(run, {a.id} if a.id else None)
        if data is None:
            print(f"clips: нет {run}/findings.json", file=sys.stderr)
            return 2
        targets = [c["file"] for _, c in rows]
    if not targets:
        print("clips: нечего собирать (нет роликов)", file=sys.stderr)
        return 2
    out, code = [], 0
    data = _load_findings(run) if not a.file else None
    for rel in targets:
        p = run / rel
        if not p.is_file() or not _inside(p, run):
            out.append({"file": rel, "ok": False, "warning": "файла нет или он вне прогона"})
            code = 1
            continue
        r = qa_clips.sheet(p, p.with_name(p.stem + "-sheet.png"), frames=a.frames)
        out.append(dict(r, source=rel))
        code = code or (0 if r.get("ok") else 1)
        if r.get("ok") and data is not None:  # the entry gets the sheet path (was null without ffmpeg)
            for fnd in _items(data):
                for c in fnd.get("clips") or []:
                    if isinstance(c, dict) and c.get("file") == rel:
                        c["sheet"] = Path(r["file"]).resolve().relative_to(run.resolve()).as_posix()
    if data is not None:
        _save_findings(run, data)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return code


def cmd_caps(a):
    caps = qa_clips.capabilities()
    caps["playwright"] = playwright_info()
    caps["recording"] = ("page.screencast (Playwright %s): launch и CDP" % caps["playwright"]["version"]
                         if caps["playwright"]["screencast"] else
                         "recordVideo контекста (Playwright %s): только launch, по CDP — нет" % caps["playwright"]["version"]
                         if caps["playwright"]["version"] else "Playwright не установлен: cd scripts/node && npm install")
    if a.json:
        print(json.dumps(caps, ensure_ascii=False, indent=1))
        return 0
    print(f"ffmpeg:   {caps['ffmpeg'] or 'нет'}" + (f" ({caps['version']}; libx264 {'да' if caps['libx264'] else 'нет'}, "
                                                      f"GIF {'да' if caps['gif'] else 'нет'})" if caps["ffmpeg"] else
                                                      " — ролик сохранится без сжатия, без GIF, постера и ленты кадров"))
    print(f"ffprobe:  {caps['ffprobe'] or 'нет'}")
    print(f"запись:   {caps['recording']}")
    if not caps["ffmpeg"]:
        print("поставить (только с согласия пользователя): brew install ffmpeg | sudo apt install ffmpeg | "
              "winget install Gyan.FFmpeg; или QA_FFMPEG=<путь к ffmpeg>")
    return 0


def cmd_policy(a):
    mode = a.mode or settings_of(a.run_dir)["mode"]
    rec, why = qa_clips.should_record(a.text, mode, a.direction)
    print(json.dumps({"record": rec, "reason": why, "mode": mode}, ensure_ascii=False))
    return 0


def cmd_settings(a):
    print(json.dumps(settings_of(a.run_dir), ensure_ascii=False))
    return 0


def cmd_ignore(a):
    if not Path(a.run_dir).is_dir():
        print(f"clips: нет папки прогона {a.run_dir}", file=sys.stderr)
        return 2
    print(json.dumps(ensure_ignored(a.run_dir), ensure_ascii=False))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="clips.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("finalize", help="сжать, GIF, постер, лента кадров, запись в находку")
    f.add_argument("run_dir")
    f.add_argument("--src", required=True)
    f.add_argument("--name", required=True)
    f.add_argument("--caption", default="")
    f.add_argument("--kind", default="error", choices=list(qa_clips.KINDS))
    f.add_argument("--finding")
    f.add_argument("--step", action="append")
    f.add_argument("--steps-json")
    f.add_argument("--start", type=float, default=0.0)
    f.add_argument("--subdir", default="clips")
    f.add_argument("--format", choices=["mp4", "gif", "both"])
    f.add_argument("--max-seconds", type=float)
    f.add_argument("--max-mb", type=float)
    f.add_argument("--no-burn-caption", action="store_true", help="подпись уже в кадре — не дублировать drawtext")
    f.add_argument("--keep-raw", action="store_true")
    c = sub.add_parser("check")
    c.add_argument("run_dir")
    c.add_argument("--id")
    c.add_argument("--json", action="store_true")
    v = sub.add_parser("viewed")
    v.add_argument("run_dir")
    v.add_argument("--id", required=True)
    v.add_argument("--file")
    v.add_argument("--force", action="store_true", help="без ленты кадров (просмотрены скриншоты шагов)")
    ls = sub.add_parser("list")
    ls.add_argument("run_dir")
    ls.add_argument("--json", action="store_true")
    sh = sub.add_parser("sheet")
    sh.add_argument("run_dir")
    sh.add_argument("--id")
    sh.add_argument("--file")
    sh.add_argument("--frames", type=int, default=8)
    cp = sub.add_parser("caps")
    cp.add_argument("--json", action="store_true")
    po = sub.add_parser("policy")
    po.add_argument("text")
    po.add_argument("--run-dir")
    po.add_argument("--mode", choices=["auto", "on", "off"])
    po.add_argument("--direction")
    st = sub.add_parser("settings")
    st.add_argument("run_dir", nargs="?")
    ig = sub.add_parser("ignore")
    ig.add_argument("run_dir")
    a = ap.parse_args(argv)
    return {"finalize": cmd_finalize, "check": cmd_check, "viewed": cmd_viewed, "list": cmd_list, "sheet": cmd_sheet,
            "caps": cmd_caps, "policy": cmd_policy, "settings": cmd_settings, "ignore": cmd_ignore}[a.cmd](a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
