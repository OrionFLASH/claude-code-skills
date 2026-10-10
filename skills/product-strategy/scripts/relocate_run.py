#!/usr/bin/env python3
"""Перенос папки прогона <OLD_OUT> → <NEW_OUT> с заменой абсолютных путей в текстовых файлах.

  relocate_run.py <OLD_OUT> <NEW_OUT> [--repo <repo>] [--move] [--absolute] [--with-node]
                  [--inside-repo | --no-inside-repo] [--branch <ветка>] [--dry-run] [--json]

Что делает:
  1. Копирует <OLD_OUT> в <NEW_OUT> (по умолчанию; --move — перемещает). Каталог build/node (локальные npm-модули)
     по умолчанию не копируется (переустановка: check_env.py --install-node <NEW_OUT>); --with-node копирует. Если <OLD_OUT>
     уже не существует, а <NEW_OUT> есть (папку перенесли руками), только переписывает пути внутри <NEW_OUT>.
  2. Во всех текстовых файлах (*.md, *.json, *.csv, *.html, *.sh, *.mjs, *.py, а также *.txt, *.svg, *.css, *.yml; файл < 5 МБ
     и не бинарный) заменяет старый абсолютный путь <OLD_OUT> на новый: с --repo, если <NEW_OUT> внутри репозитория —
     на путь относительно репозитория (например strategy/2026-10-10), иначе на абсолютный <NEW_OUT> (--absolute — всегда
     абсолютный). Каталоги node_modules, .git и build/node не трогаются.
  3. build/run-config.json: output.dir = абсолютный <NEW_OUT>, output.inside_repo (по --inside-repo/--no-inside-repo,
     иначе вычисляется из --repo), output.git_branch (--branch), repo.path (если задан --repo).
  4. <NEW_OUT>/.gitignore: строки `build/node/` и `node_modules/`; build/STATUS.md: запись о переносе.
  5. Отчёт: файлов просмотрено/изменено, замен, оставшиеся упоминания старого пути в обработанных файлах (должно быть 0),
     большие/бинарные файлы, где старый путь найден (их пересоберёт build_all.py). Пересборку скрипт НЕ запускает — печатает
     команду `build_all.py <NEW_OUT>`.
Отчёт сохраняется в <NEW_OUT>/build/relocate-report.json (кроме --dry-run).
Код выхода: 0 — готово, упоминаний старого пути в обработанных файлах нет; 1 — остались упоминания; 2 — ошибка аргументов
(нет <OLD_OUT> и <NEW_OUT>, <NEW_OUT> уже существует и не пуст при копировании).
Только стандартная библиотека.
"""
import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEXT_EXT = {".md", ".json", ".csv", ".html", ".sh", ".mjs", ".py", ".txt", ".svg", ".css", ".yml", ".yaml"}
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


def pattern_for(paths):
    alts = sorted({p.rstrip("/") for p in paths if p}, key=len, reverse=True)
    return re.compile("(?:%s)(?![\\w\\-])" % "|".join(re.escape(a) for a in alts))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old_out", help="старая папка прогона")
    ap.add_argument("new_out", help="новая папка прогона")
    ap.add_argument("--repo", help="корень репозитория (для относительных путей и run-config.repo.path)")
    ap.add_argument("--move", action="store_true", help="переместить папку вместо копирования")
    ap.add_argument("--absolute", action="store_true", help="подставлять абсолютный путь <NEW_OUT> даже внутри репозитория")
    ap.add_argument("--with-node", action="store_true", help="копировать build/node (по умолчанию пропускается)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--inside-repo", dest="inside_repo", action="store_true", default=None, help="output.inside_repo = true")
    g.add_argument("--no-inside-repo", dest="inside_repo", action="store_false", help="output.inside_repo = false")
    ap.add_argument("--branch", help="output.git_branch")
    ap.add_argument("--dry-run", action="store_true", help="ничего не менять, только посчитать")
    ap.add_argument("--json", action="store_true", help="печатать отчёт JSON")
    a = ap.parse_args(argv)

    old_raw, new_raw = a.old_out.rstrip("/"), a.new_out.rstrip("/")
    old, new = Path(old_raw).expanduser().resolve(), Path(new_raw).expanduser().resolve()
    repo = Path(a.repo).expanduser().resolve() if a.repo else None
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
    old_forms = {old_raw, str(old)}
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
                if repo:
                    cfg.setdefault("repo", {})["path"] = str(repo)
                cfgp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                extra.append("build/run-config.json: output.dir, inside_repo, git_branch" + (", repo.path" if repo else ""))
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
        note = "\n## Перенос папки прогона (%s)\n\n- Новый путь: `%s`\n- Заменено путей: %d в %d файлах (relocate_run.py; старый путь в файлах прогона не хранится).\n- Пересборка: `python3 %s %s`\n" % (
            date.today().isoformat(), new, replaced, changed, HERE / "build_all.py", replacement if mode != "абсолютный" else new)
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
    report = {"ok": not remaining, "dry_run": a.dry_run, "old": str(old), "new": str(new), "replacement": replacement, "mode": mode, "actions": actions,
              "files_scanned": scanned, "files_changed": changed, "replacements": replaced, "remaining": remaining,
              "remaining_total": sum(r["count"] for r in remaining), "large_or_binary_with_old_path": big_hits, "skipped": skipped,
              "changed_files": changed_files, "updated": extra, "rebuild_command": cmd}
    if not a.dry_run:
        (new / "build").mkdir(parents=True, exist_ok=True)
        saved = json.dumps(report, ensure_ascii=False, indent=2)
        for form in sorted(old_forms, key=len, reverse=True):
            saved = saved.replace(json.dumps(form, ensure_ascii=False)[1:-1], "<OLD_OUT>")   # старый путь в файлах прогона не оставляем
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
    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())
