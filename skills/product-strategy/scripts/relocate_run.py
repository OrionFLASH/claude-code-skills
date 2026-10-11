#!/usr/bin/env python3
"""Перенос папки прогона <OLD_OUT> → <NEW_OUT> с заменой абсолютных путей в текстовых файлах.

  relocate_run.py <OLD_OUT> <NEW_OUT> [--repo <repo>] [--move] [--absolute] [--with-node]
                  [--inside-repo | --no-inside-repo] [--branch <ветка>] [--fix-leftovers] [--dry-run] [--json]
  relocate_run.py <OUT> --scan-leftovers [--fix-leftovers] [--json]     только поиск (и замена) абсолютных путей

Что делает:
  1. Копирует <OLD_OUT> в <NEW_OUT> (по умолчанию; --move — перемещает). Каталог build/node (локальные npm-модули)
     по умолчанию не копируется (переустановка: check_env.py --install-node <NEW_OUT>); --with-node копирует. Если <OLD_OUT>
     уже не существует, а <NEW_OUT> есть (папку перенесли руками), только переписывает пути внутри <NEW_OUT>.
  2. Во всех текстовых файлах (*.md, *.json, *.csv, *.html, *.sh, *.mjs, *.py, *.log, *.txt, *.svg, *.css, *.yml, *.toml,
     *.tsv, *.jsonl …; файл < 5 МБ и не бинарный) заменяет старый путь <OLD_OUT> во всех формах (как передан, после
     resolve, с `~` вместо домашней папки, с /private и без него на macOS) на новый: если <NEW_OUT> внутри репозитория
     (--repo или найден `git rev-parse` от <NEW_OUT>) — на путь относительно репозитория (например strategy/2026-10-10),
     иначе на абсолютный <NEW_OUT> (--absolute — всегда абсолютный). Каталоги node_modules, .git и build/node не трогаются.
  3. build/run-config.json: output.dir = абсолютный <NEW_OUT>, output.inside_repo (по --inside-repo/--no-inside-repo,
     иначе вычисляется по репозиторию), output.git_branch (--branch; внутри репозитория при пустом значении —
     docs/strategy-<дата> или docs/concept-<имя>), repo.path (если репозиторий известен).
  4. <NEW_OUT>/.gitignore: строки `build/node/` и `node_modules/`; build/STATUS.md: запись о переносе.
  5. Отчёт: файлов просмотрено/изменено, замен, оставшиеся упоминания старого пути в обработанных файлах (должно быть 0),
     большие/бинарные файлы, где старый путь найден (их пересоберёт build_all.py). Пересборку скрипт НЕ запускает — печатает
     команду `build_all.py <NEW_OUT>`.
  6. Остатки (--scan-leftovers; при переносе — всегда): любые абсолютные пути (/Users/…, /home/…, /var/folders/…,
     C:\\Users\\…, развёрнутая домашняя папка) во всех текстовых файлах — файл:строка; build/run-config.json (output.dir,
     repo.path абсолютны по контракту) идёт отдельной строкой. --fix-leftovers заменяет домашнюю папку на `~` (кроме
     run-config.json). Остатки не меняют код выхода.
Отчёт сохраняется в <NEW_OUT>/build/relocate-report.json (кроме --dry-run); домашняя папка в нём — `~`, папка скилла — <SKILL_DIR>.
Код выхода: 0 — готово, упоминаний старого пути в обработанных файлах нет; 1 — остались упоминания; 2 — ошибка аргументов
(нет <OLD_OUT> и <NEW_OUT>, <NEW_OUT> уже существует и не пуст при копировании).
Только стандартная библиотека.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEXT_EXT = {".md", ".json", ".csv", ".html", ".sh", ".mjs", ".py", ".txt", ".svg", ".css", ".yml", ".yaml", ".log", ".tsv",
            ".toml", ".ini", ".cfg", ".jsonl", ".ndjson", ".xml", ".js", ".cjs", ".rst", ".mmd", ".out", ".err"}
ABS_RE = re.compile(r"(?:/Users/[^/\s\"'`]+|/home/[^/\s\"'`]+|/private/var/folders/|/var/folders/|[A-Za-z]:\\{1,2}Users\\{1,2})[^\s\"'`<>)\]]*")
CONTRACT_ABS = {"build/run-config.json"}       # output.dir и repo.path — абсолютные по контракту
MAX_BYTES = 5 * 1024 * 1024
SKIP_DIRS = {"node_modules", ".git"}


def is_skipped_dir(rel_parts):
    return any(p in SKIP_DIRS for p in rel_parts) or rel_parts[:2] == ("build", "node")


def walk(root, with_node):
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.is_symlink():
            continue
        parts = f.relative_to(root).parts
        if any(p in SKIP_DIRS for p in parts):
            continue
        if not with_node and parts[:2] == ("build", "node"):
            continue
        yield f


def read_text(f):
    """→ текст или None (бинарный/не UTF-8/слишком большой — причина во втором значении)."""
    try:
        size = f.stat().st_size
    except OSError:
        return None, "нет доступа"
    if f.suffix.lower() not in TEXT_EXT:
        return None, "расширение"
    if size > MAX_BYTES:
        return None, "больше 5 МБ"
    try:
        data = f.read_bytes()
    except OSError:
        return None, "нет доступа"
    if b"\x00" in data[:8192]:
        return None, "бинарный"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, "не UTF-8"


def path_forms(raw, resolved):
    """Все формы абсолютного пути: как передан, после resolve, с ~ и с /private (macOS) и без него. Относительные — нет."""
    forms = set()
    for x in (raw, str(resolved)):
        x = os.path.expanduser(x or "")
        if x and os.path.isabs(x):
            forms.add(x.rstrip("/") or "/")
    for x in list(forms):
        if x.startswith("/private/"):
            forms.add(x[len("/private"):])
        elif x.startswith(("/var/", "/tmp/", "/etc/")):
            forms.add("/private" + x)
    home = str(Path.home())
    for x in list(forms):
        if x == home or x.startswith(home + "/"):
            forms.add("~" + x[len(home):])
    return forms


def git_toplevel(path):
    """Корень git-репозитория для пути (или ближайшего существующего родителя) → Path | None."""
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        r = subprocess.run(["git", "-C", str(p), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return Path(r.stdout.strip()).resolve() if r.returncode == 0 and r.stdout.strip() else None


def tilde(text):
    home = str(Path.home())
    return re.sub(re.escape(home) + r"(?=/|\b|$)", "~", text) if home and home != "/" else text


def scan_leftovers(root, with_node=False, fix=False):
    """Абсолютные пути в текстовых файлах → {"files": [{file, line, text}], "contract": [...], "fixed": N}."""
    home = str(Path.home())
    hits, contract, fixed = [], [], 0
    for f in walk(root, with_node):
        text, _ = read_text(f)
        if text is None:
            continue
        rel = f.relative_to(root).as_posix()
        if fix and rel not in CONTRACT_ABS and home in text:
            new_text = tilde(text)
            if new_text != text:
                f.write_text(new_text, encoding="utf-8")
                fixed += 1
                text = new_text
        for i, line in enumerate(text.splitlines(), 1):
            m = ABS_RE.search(line) or (re.search(re.escape(home) + r"(?=/|\b)", line) if home and home != "/" else None)
            if m:
                rec = {"file": rel, "line": i, "text": tilde(m.group(0))[:120]}
                (contract if rel in CONTRACT_ABS else hits).append(rec)
    return {"files": hits, "contract": contract, "fixed": fixed}


def print_leftovers(lo, limit=20):
    print("абсолютных путей в файлах прогона: %d%s" % (len(lo["files"]), (" (заменено на ~ в %d файлах)" % lo["fixed"]) if lo["fixed"] else ""))
    for h in lo["files"][:limit]:
        print("  %s:%d  %s" % (h["file"], h["line"], h["text"]))
    if len(lo["files"]) > limit:
        print("  … ещё %d" % (len(lo["files"]) - limit))
    if lo["contract"]:
        print("  (build/run-config.json: %d — output.dir/repo.path абсолютны по контракту)" % len(lo["contract"]))
    if lo["files"] and not lo["fixed"]:
        print("  заменить домашнюю папку на ~: relocate_run.py <OUT> --scan-leftovers --fix-leftovers")


def pattern_for(paths):
    alts = sorted({p.rstrip("/") for p in paths if p}, key=len, reverse=True)
    return re.compile("(?:%s)(?![\\w\\-])" % "|".join(re.escape(a) for a in alts))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old_out", help="старая папка прогона (с --scan-leftovers — папка для проверки)")
    ap.add_argument("new_out", nargs="?", help="новая папка прогона")
    ap.add_argument("--repo", help="корень репозитория (для относительных путей и run-config.repo.path)")
    ap.add_argument("--move", action="store_true", help="переместить папку вместо копирования")
    ap.add_argument("--absolute", action="store_true", help="подставлять абсолютный путь <NEW_OUT> даже внутри репозитория")
    ap.add_argument("--with-node", action="store_true", help="копировать build/node (по умолчанию пропускается)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--inside-repo", dest="inside_repo", action="store_true", default=None, help="output.inside_repo = true")
    g.add_argument("--no-inside-repo", dest="inside_repo", action="store_false", help="output.inside_repo = false")
    ap.add_argument("--branch", help="output.git_branch")
    ap.add_argument("--scan-leftovers", action="store_true", help="найти абсолютные пути во всех текстовых файлах (без переноса, если нет NEW_OUT)")
    ap.add_argument("--fix-leftovers", action="store_true", help="заменить домашнюю папку на ~ в текстовых файлах (кроме run-config.json)")
    ap.add_argument("--dry-run", action="store_true", help="ничего не менять, только посчитать")
    ap.add_argument("--json", action="store_true", help="печатать отчёт JSON")
    a = ap.parse_args(argv)
    if a.new_out is None:
        if not a.scan_leftovers:
            ap.error("нужна NEW_OUT (или --scan-leftovers для проверки одной папки)")
        root = Path(a.old_out).expanduser().resolve()
        if not root.is_dir():
            print("ошибка: нет папки %s" % root, file=sys.stderr)
            return 2
        lo = scan_leftovers(root, a.with_node, fix=a.fix_leftovers and not a.dry_run)
        if a.json:
            print(json.dumps(lo, ensure_ascii=False, indent=2))
        else:
            print_leftovers(lo)
        return 0

    old_raw, new_raw = a.old_out.rstrip("/"), a.new_out.rstrip("/")
    old, new = Path(old_raw).expanduser().resolve(), Path(new_raw).expanduser().resolve()
    repo = Path(a.repo).expanduser().resolve() if a.repo else git_toplevel(new)
    repo_auto = bool(repo) and not a.repo
    same = old == new
    already_moved = (not old.exists()) and new.exists()
    if not old.exists() and not new.exists():
        print("ошибка: нет ни %s, ни %s" % (old, new), file=sys.stderr)
        return 2
    if not same and not already_moved and new.exists() and any(new.iterdir()):
        print("ошибка: %s уже существует и не пуст (удалите или выберите другой путь)" % new, file=sys.stderr)
        return 2
    if not same and not already_moved and (new == old or old in new.parents or new in old.parents):
        print("ошибка: папки вложены друг в друга", file=sys.stderr)
        return 2

    # чем заменять
    inside = bool(repo) and (repo == new or repo in new.parents)
    if inside and not a.absolute:
        replacement = new.relative_to(repo).as_posix() if new != repo else "."
        mode = "относительно репозитория"
    else:
        replacement = str(new)
        mode = "абсолютный"
    old_forms = path_forms(old_raw, old)
    pat = pattern_for(old_forms)

    # перенос
    actions = []
    if same or already_moved:
        actions.append("перенос не нужен (%s)" % ("тот же путь" if same else "папка уже на новом месте"))
    elif a.dry_run:
        actions.append("%s %s → %s (dry-run)" % ("переместить" if a.move else "скопировать", old, new))
    elif a.move:
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), str(new))
        actions.append("перемещено %s → %s" % (old, new))
    else:
        new.parent.mkdir(parents=True, exist_ok=True)

        def ignore_node(d, names):
            skip = set()
            if not a.with_node:
                skip |= {n for n in names if n == "node_modules"}
                if Path(d) == old / "build" and "node" in names:
                    skip.add("node")
            return skip
        shutil.copytree(old, new, ignore=ignore_node, dirs_exist_ok=True)
        actions.append("скопировано %s → %s" % (old, new))
    scan_root = old if (a.dry_run and old.exists() and not same and not already_moved) else new
    if not scan_root.exists():
        print("ошибка: нечего обрабатывать: %s" % scan_root, file=sys.stderr)
        return 2

    # замена
    scanned = changed = replaced = 0
    skipped, big_hits, changed_files = [], [], []
    for f in walk(scan_root, a.with_node):
        scanned += 1
        text, why = read_text(f)
        if text is None:
            if why in ("больше 5 МБ", "не UTF-8"):
                try:
                    if any(x.encode() in f.read_bytes() for x in old_forms):
                        big_hits.append({"file": f.relative_to(scan_root).as_posix(), "reason": why})
                except OSError:
                    pass
            if why != "расширение":
                skipped.append({"file": f.relative_to(scan_root).as_posix(), "reason": why})
            continue
        new_text, n = pat.subn(lambda _m: replacement, text)
        if n:
            changed += 1
            replaced += n
            changed_files.append({"file": f.relative_to(scan_root).as_posix(), "replacements": n})
            if not a.dry_run:
                f.write_text(new_text, encoding="utf-8")

    # служебные файлы
    extra = []
    if not a.dry_run:
        cfgp = new / "build" / "run-config.json"
        if cfgp.exists():
            try:
                cfg = json.loads(cfgp.read_text(encoding="utf-8"))
                o = cfg.setdefault("output", {})
                o["dir"] = str(new)
                if a.inside_repo is not None:
                    o["inside_repo"] = a.inside_repo
                elif repo:
                    o["inside_repo"] = inside
                if a.branch is not None:
                    o["git_branch"] = a.branch
                elif o.get("inside_repo") and not o.get("git_branch"):
                    o["git_branch"] = ("docs/concept-%s" % ((cfg.get("idea") or {}).get("slug") or new.name)) if cfg.get("mode") == "concept" \
                        else "docs/strategy-%s" % date.today().isoformat()
                if repo:
                    cfg.setdefault("repo", {})["path"] = str(repo)
                cfgp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                extra.append("build/run-config.json: output.dir=%s, inside_repo=%s, git_branch=%s" % (
                    tilde(str(new)), o.get("inside_repo"), o.get("git_branch") or "—") + (", repo.path" if repo else "")
                    + (" (репозиторий найден по git: %s)" % tilde(str(repo)) if repo_auto else ""))
            except (OSError, json.JSONDecodeError) as e:
                extra.append("build/run-config.json: не обновлён (%s)" % e)
        gi = new / ".gitignore"
        have = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
        add = [x for x in ("build/node/", "node_modules/") if x not in have]
        if add:
            gi.write_text("\n".join(have + add) + "\n", encoding="utf-8")
            extra.append(".gitignore: добавлено %s" % ", ".join(add))
        st = new / "build" / "STATUS.md"
        st.parent.mkdir(parents=True, exist_ok=True)
        shown = replacement if mode != "абсолютный" else tilde(str(new))          # без домашней папки пользователя
        note = "\n## Перенос папки прогона (%s)\n\n- Новый путь: `%s`\n- Заменено путей: %d в %d файлах (relocate_run.py; старый путь в файлах прогона не хранится).\n- Пересборка: `python3 <SKILL_DIR>/scripts/build_all.py %s`\n" % (
            date.today().isoformat(), shown, replaced, changed, shown)
        st.write_text((st.read_text(encoding="utf-8") if st.exists() else "# Статус\n") .rstrip("\n") + "\n" + note, encoding="utf-8")
        extra.append("build/STATUS.md: запись о переносе")

    # проверка остатков (после записи; в dry-run — по ожидаемому результату: считаем непокрытые, т.е. 0 в обработанных)
    remaining = []
    if not a.dry_run:
        for f in walk(new, a.with_node):
            text, _ = read_text(f)
            if text is not None and pat.search(text):
                remaining.append({"file": f.relative_to(new).as_posix(), "count": len(pat.findall(text))})
    cmd = "python3 %s %s" % (HERE / "build_all.py", replacement if mode != "абсолютный" else new)
    leftovers = scan_leftovers(new, a.with_node, fix=a.fix_leftovers) if not a.dry_run else {"files": [], "contract": [], "fixed": 0}
    report = {"ok": not remaining, "dry_run": a.dry_run, "old": str(old), "new": str(new), "replacement": replacement, "mode": mode, "actions": actions,
              "files_scanned": scanned, "files_changed": changed, "replacements": replaced, "remaining": remaining,
              "remaining_total": sum(r["count"] for r in remaining), "large_or_binary_with_old_path": big_hits, "skipped": skipped,
              "changed_files": changed_files, "updated": extra, "rebuild_command": cmd, "leftovers": leftovers}
    if not a.dry_run:
        (new / "build").mkdir(parents=True, exist_ok=True)
        saved = json.dumps(report, ensure_ascii=False, indent=2)
        for form in sorted(old_forms, key=len, reverse=True):
            saved = saved.replace(json.dumps(form, ensure_ascii=False)[1:-1], "<OLD_OUT>")   # старый путь в файлах прогона не оставляем
        saved = tilde(saved.replace(json.dumps(str(HERE), ensure_ascii=False)[1:-1], "<SKILL_DIR>/scripts"))
        (new / "build" / "relocate-report.json").write_text(saved + "\n", encoding="utf-8")
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for x in actions + extra:
            print(x)
        print("путь заменён на «%s» (%s): просмотрено файлов %d, изменено %d, замен %d%s" % (
            replacement, mode, scanned, changed, replaced, " (dry-run, файлы не тронуты)" if a.dry_run else ""))
        print("оставшихся упоминаний старого пути: %d%s" % (report["remaining_total"], "" if not remaining else " — в " + ", ".join(r["file"] for r in remaining[:10])))
        for b in big_hits:
            print("  пересоберите: в %s (%s) есть старый путь" % (b["file"], b["reason"]))
        print("пересборка (скрипт её не запускает): %s" % cmd)
        if not a.dry_run:
            print_leftovers(leftovers)
    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())
