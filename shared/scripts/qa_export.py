#!/usr/bin/env python3
"""Copy the FINAL results of a QA run to another folder (report_destinations: folder) — not the run folder.

Shared module (shared/scripts/qa_export.py, vendored into <skill>/scripts/shared/ via .shared);
a skill exposes it as scripts/export_results.py (thin wrapper calling qa_export.main()).

  export_results.py <RUN_DIR> --to <PATH> [--name NAME] [--screenshots referenced|all|none] [--overwrite]
                    [--dry-run] [--json]

Copied into <PATH>/<NAME>/ (NAME — the run folder name: <YYYY-MM-DD>-<host|package>):
  summary.md, report.md (required), findings.json (if present) and screenshots:
  referenced (default) — images listed in findings[].screenshots that lie in <RUN_DIR>/screenshots/;
  all — every image in <RUN_DIR>/screenshots/; none — no images.
Never copied: raw/, logs/ (logcat, actions, blocked), apk/ (APK, AAB, SHA256SUMS), recordings/, drafts/, journal.md,
run-config.yaml, env.json, stands.json and anything else of the run folder. Relative paths are kept
(screenshots/x.png), so links in report.md keep working.
A file with the same name and different content is not overwritten: nothing is copied, exit 1 with the list
(ask the user, then --overwrite or another --name). Identical files are skipped.
Exit: 0 copied (or already there), 1 conflicts, 2 error (no report.md / summary.md, destination inside the run).
Python 3.8+, standard library only.
"""
import argparse
import filecmp
import json
import shutil
import sys
from pathlib import Path

REQUIRED = ["summary.md", "report.md"]
OPTIONAL = ["findings.json"]
SHOTS = "screenshots"
IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def fail(msg):
    sys.stderr.write(f"export_results: {msg}\n")
    sys.exit(2)


def inside(path, folder):
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except ValueError:
        return False


def referenced_shots(run, findings):
    """(list of Path inside RUN_DIR/screenshots, list of skipped (ref, reason))."""
    shots_dir = run / SHOTS
    out, skipped = [], []
    items = findings.get("findings", []) if isinstance(findings, dict) else (findings or [])
    for f in items if isinstance(items, list) else []:
        for ref in (f.get("screenshots") or []) if isinstance(f, dict) else []:
            if not isinstance(ref, str) or not ref.strip():
                continue
            p = Path(ref).expanduser()
            if not p.is_absolute():
                p = run / ref if (run / ref).exists() or "/" in ref.replace("\\", "/") else shots_dir / ref
            if not p.is_file():
                skipped.append((ref, "файла нет"))
            elif not inside(p, shots_dir):
                skipped.append((ref, f"не в {SHOTS}/ папки прогона"))
            elif p.suffix.lower() not in IMAGES:
                skipped.append((ref, "не изображение"))
            elif p.resolve() not in [x.resolve() for x in out]:
                out.append(p)
    return out, skipped


def plan(run, dest, mode):
    for name in REQUIRED:
        if not (run / name).is_file():
            fail(f"нет {run / name} — сначала build_report.py report/summary")
    files = [run / n for n in REQUIRED] + [run / n for n in OPTIONAL if (run / n).is_file()]
    skipped = []
    if mode != "none" and (run / SHOTS).is_dir():
        if mode == "all":
            files += sorted(p for p in (run / SHOTS).rglob("*") if p.is_file() and p.suffix.lower() in IMAGES)
        else:
            try:
                data = json.loads((run / "findings.json").read_text(encoding="utf-8")) if (run / "findings.json").is_file() else {}
            except ValueError:
                data = {}
            shots, skipped = referenced_shots(run, data)
            files += shots
    rows = []
    for src in files:
        rel = src.resolve().relative_to(run.resolve())
        dst = dest / rel
        state = "new" if not dst.exists() else ("same" if dst.is_file() and filecmp.cmp(src, dst, shallow=False) else "conflict")
        rows.append({"file": rel.as_posix(), "src": str(src), "dst": str(dst), "state": state})
    return rows, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--to", required=True, help="папка назначения (report_destinations: folder → path)")
    ap.add_argument("--name", help="имя подпапки; по умолчанию — имя папки прогона (<YYYY-MM-DD>-<host|package>)")
    ap.add_argument("--screenshots", default="referenced", choices=["referenced", "all", "none"])
    ap.add_argument("--overwrite", action="store_true", help="перезаписать отличающиеся файлы (только после «да»)")
    ap.add_argument("--dry-run", action="store_true", help="только план")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    run = Path(a.run_dir).expanduser()
    if not run.is_dir():
        fail(f"нет папки прогона {run}")
    run = run.resolve()
    name = a.name or run.name
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        fail(f"недопустимое имя подпапки «{name}»")
    dest = (Path(a.to).expanduser().resolve() / name)
    if inside(dest, run) or inside(run, dest):
        fail(f"{dest}: папка назначения не может быть внутри папки прогона (и наоборот)")
    rows, skipped = plan(run, dest, a.screenshots)
    conflicts = [r for r in rows if r["state"] == "conflict"]
    result = {"run_dir": str(run), "dest": str(dest), "screenshots": a.screenshots, "files": rows,
              "skipped": [{"ref": r, "reason": why} for r, why in skipped], "conflicts": [r["file"] for r in conflicts],
              "copied": [], "dry_run": a.dry_run}
    code = 0
    if conflicts and not a.overwrite:
        code = 1
    elif not a.dry_run:
        for r in rows:
            if r["state"] == "same":
                continue
            Path(r["dst"]).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(r["src"], r["dst"])
            result["copied"].append(r["file"])
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        shots = sum(1 for r in rows if r["file"].startswith(SHOTS + "/"))
        print(f"итоги прогона → {dest}")
        for r in rows:
            mark = {"new": "копировать", "same": "уже есть (то же содержимое)", "conflict": "КОНФЛИКТ: файл отличается"}[r["state"]]
            print(f"  {r['file']:<40} {mark}")
        for ref, why in skipped:
            print(f"  пропущено {ref}: {why}")
        if code == 1:
            print("Ничего не скопировано: одноимённые файлы отличаются — спросить пользователя: перезаписать (--overwrite) "
                  "или другое имя (--name)")
        elif a.dry_run:
            print("План без изменений (--dry-run).")
        else:
            print(f"скопировано файлов: {len(result['copied'])} (скриншотов в наборе: {shots}); raw/, logs/, apk/, "
                  "recordings/, drafts/ не копируются")
            print(f"строка для «Куда записаны итоги»: | {dest}/ | итоговые файлы: "
                  f"{', '.join(r['file'] for r in rows if '/' not in r['file'])}, скриншотов {shots} |")
    sys.exit(code)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
