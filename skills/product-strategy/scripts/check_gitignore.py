#!/usr/bin/env python3
"""Проверка, что файлы прогона не игнорируются git (перед коммитом результата в репозиторий).

  check_gitignore.py <OUT> [--repo R] [--fix] [--json]

Если <OUT> внутри git-репозитория, находит файлы прогона, которые git молча исключит из коммита (например, корневое правило
`build/` скрывает <OUT>/build с run-config.json, брифами и STATUS.md), и показывает правило (`git check-ignore -v`).
--fix пишет в <OUT>/.gitignore строки-исключения (`!build/` …): правила вложенного .gitignore сильнее родительских; `build/node/`
(Node-модули, если они лежат в результате) и временные файлы остаются игнорируемыми.
Код выхода: 0 — всё попадёт в коммит (или <OUT> вне репозитория), 1 — часть файлов игнорируется, 2 — ошибка.
Только стандартная библиотека.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

WANT = ("build", "data", "research", "deliverables", "charts", "mockups", "design-refs", "competitors")
ALLOWED_IGNORED = ("build/node/", "build/node", ".tmp", "__pycache__")


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def toplevel(path):
    code, out, _ = git(path, "rev-parse", "--show-toplevel")
    return Path(out.strip()).resolve() if code == 0 and out.strip() else None


def analyse(out_dir, repo=None):
    out = Path(out_dir).resolve()
    top = Path(repo).resolve() if repo else toplevel(out if out.exists() else out.parent)
    res = {"out": str(out), "repo": str(top) if top else None, "inside_repo": False, "ignored": [], "rules": {}, "tracked_or_new": 0}
    if not top:
        return res
    try:
        rel = out.relative_to(top)
    except ValueError:
        return res
    res["inside_repo"] = True
    code, status, err = git(top, "status", "--porcelain", "--ignored", "--untracked-files=all", "--", str(rel))
    if code != 0:
        res["error"] = err.strip()
        return res
    ignored = []
    for line in status.splitlines():
        if line.startswith("!!"):
            ignored.append(line[3:].strip())
    code, ls, _ = git(top, "ls-files", "-o", "-c", "--exclude-standard", "--", str(rel))
    res["tracked_or_new"] = len([x for x in ls.splitlines() if x.strip()])
    keep = []
    for p in ignored:
        sub = p[len(str(rel)) + 1:] if str(rel) != "." and p.startswith(str(rel) + "/") else p
        if any(a in sub for a in ALLOWED_IGNORED):
            continue
        keep.append(p)
    res["ignored"] = keep
    seen = set()
    for p in keep:
        sub = p[len(str(rel)) + 1:] if str(rel) != "." and p.startswith(str(rel) + "/") else p
        top_dir = sub.split("/")[0]
        if top_dir in seen:
            continue
        seen.add(top_dir)
        code, o, _ = git(top, "check-ignore", "-v", "--no-index", p.rstrip("/"))
        if o.strip():
            res["rules"][top_dir] = o.strip().split("\t")[0]
    return res


def fix(out_dir, res):
    out = Path(out_dir).resolve()
    gi = out / ".gitignore"
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    dirs = sorted({(p[len(str(Path(res["out"]).relative_to(res["repo"]))) + 1:] if p.startswith(str(Path(res["out"]).relative_to(res["repo"])) + "/") else p).split("/")[0]
                   for p in res["ignored"]})
    add = ["!%s/" % d for d in dirs if "!%s/" % d not in lines]
    if "build/node/" not in lines and (out / "build").exists():
        add.append("build/node/")
    if add:
        gi.write_text("\n".join(lines + add) + "\n", encoding="utf-8")
    return add


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--repo")
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = analyse(a.out, a.repo)
    if "error" in res:
        print("git: %s" % res["error"], file=sys.stderr)
        return 2
    if not res["inside_repo"]:
        msg = "OUT вне git-репозитория — проверка .gitignore не нужна"
        print(json.dumps({**res, "message": msg}, ensure_ascii=False) if a.json else msg)
        return 0
    added = fix(a.out, res) if a.fix and res["ignored"] else []
    if added:
        res = analyse(a.out, a.repo)
        res["fixed"] = added
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif not res["ignored"]:
        print("OK: файлы прогона не игнорируются git (в коммит попадёт %d файлов)%s" % (res["tracked_or_new"], "; добавлено в .gitignore: " + ", ".join(added) if added else ""))
    else:
        print("ВНИМАНИЕ: git молча исключит %d файл(ов)/папок прогона:" % len(res["ignored"]))
        for p in res["ignored"][:20]:
            print("  - %s" % p)
        for d, rule in res["rules"].items():
            print("  правило для %s/: %s" % (d, rule))
        print("Исправить: check_gitignore.py %s --fix (допишет «!<папка>/» в %s/.gitignore)" % (a.out, a.out))
    return 1 if res["ignored"] else 0


if __name__ == "__main__":
    sys.exit(main())
