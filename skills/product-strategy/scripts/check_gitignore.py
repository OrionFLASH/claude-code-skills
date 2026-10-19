#!/usr/bin/env python3
"""Проверка, что файлы прогона не игнорируются git (перед коммитом результата в репозиторий).

  check_gitignore.py <OUT> [--repo R] [--fix] [--shots git|local|previews] [--json]

Если <OUT> внутри git-репозитория, находит файлы прогона, которые git молча исключит из коммита (например, корневое правило
`build/` скрывает <OUT>/build с run-config.json, брифами и STATUS.md), и показывает правило (`git check-ignore -v`) —
для каждого правила отдельно: какое правило какие файлы скрывает (а не «правило для папки»).
Системные файлы (`.DS_Store`, `Thumbs.db`, `desktop.ini`), служебные папки (`build/node/`, `build/tmp/`, `build/preview/`,
`build/pdf-preview/`, `node_modules/`, `__pycache__`) и `*.tmp` игнорироваться ДОЛЖНЫ — это не потеря файлов.
--fix пишет в <OUT>/.gitignore строки-исключения (`!build/` …): правила вложенного .gitignore сильнее родительских; служебные
строки (`build/node/`, `build/tmp/`, `build/preview/`, `build/pdf-preview/`, `node_modules/`, `.DS_Store`, `Thumbs.db`)
дописываются при --fix всегда. Ещё --fix добавляет в корневой .gitignore репозитория служебные папки инструментов
(`.playwright-mcp/`), если они лежат в корне, и печатает посторонние папки (в git они не нужны).
--shots — скриншоты конкурентов (FB-042): git — коммитить (по умолчанию, если репозиторий приватный), local — только локально
(`competitors/shots/` в <OUT>/.gitignore, сайт берёт уменьшенные копии из `deliverables/assets/img`), previews — в git только
уменьшенные копии сайта. Без флага берётся run-config `output.competitor_shots`; при видимости репозитория public/unknown и
пустом выборе печатается вопрос владельцу.
Код выхода: 0 — всё попадёт в коммит (или <OUT> вне репозитория), 1 — часть файлов игнорируется, 2 — ошибка.
Только стандартная библиотека.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

WANT = ("build", "data", "research", "deliverables", "charts", "mockups", "design-refs", "competitors")
SYSTEM_NAMES = (".DS_Store", "Thumbs.db", "desktop.ini", "Desktop.ini")
ALLOWED_IGNORED = ("build/node/", "build/node", "build/tmp/", "build/tmp", "build/preview/", "build/preview",
                   "build/pdf-preview/", "build/pdf-preview", "node_modules", ".tmp", "__pycache__") + SYSTEM_NAMES
SERVICE_LINES = ["build/node/", "build/tmp/", "build/preview/", "build/pdf-preview/", "node_modules/", ".DS_Store", "Thumbs.db"]
TOOL_DIRS = (".playwright-mcp",)                       # служебные папки инструментов в корне репозитория → в корневой .gitignore
FOREIGN_HINTS = (".playwright-mcp", "test-results", "playwright-report", ".pytest_cache", "__pycache__")
SHOTS_LINE = "competitors/shots/"
SHOTS_CHOICES = ("git", "local", "previews")


def git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True)
    except OSError as e:
        return 127, "", str(e)
    return r.returncode, r.stdout, r.stderr


def toplevel(path):
    code, out, _ = git(path, "rev-parse", "--show-toplevel")
    return Path(out.strip()).resolve() if code == 0 and out.strip() else None


def load_cfg(out):
    try:
        return json.loads((Path(out) / "build" / "run-config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def shots_choice(cfg, explicit=None):
    v = explicit or ((cfg.get("output") or {}).get("competitor_shots"))
    return v if v in SHOTS_CHOICES else None


def visibility(cfg):
    v = (cfg.get("project") or {}).get("repo_visibility") or ((cfg.get("git") or {}).get("visibility"))
    return str(v or "unknown").lower()


def _sub(p, rel):
    return p[len(str(rel)) + 1:] if str(rel) != "." and p.startswith(str(rel) + "/") else p


def allowed(sub, shots_local=False):
    name = sub.rstrip("/").split("/")[-1]
    if name in SYSTEM_NAMES or any(a in sub for a in ALLOWED_IGNORED if "/" in a or a.startswith(".")):
        return True
    if any(part in ("node_modules", "__pycache__") for part in sub.split("/")):
        return True
    return bool(shots_local and (sub.startswith(SHOTS_LINE) or sub.rstrip("/") == SHOTS_LINE.rstrip("/")))


def analyse(out_dir, repo=None, shots_local=False):
    out = Path(out_dir).resolve()
    top = Path(repo).resolve() if repo else toplevel(out if out.exists() else out.parent)
    res = {"out": str(out), "repo": str(top) if top else None, "inside_repo": False, "ignored": [], "rules": {}, "rule_files": {},
           "tracked_or_new": 0, "system_ignored": 0}
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
    ignored = [line[3:].strip() for line in status.splitlines() if line.startswith("!!")]
    code, ls, _ = git(top, "ls-files", "-o", "-c", "--exclude-standard", "--", str(rel))
    res["tracked_or_new"] = len([x for x in ls.splitlines() if x.strip()])
    keep = []
    for p in ignored:
        sub = _sub(p, rel)
        if allowed(sub, shots_local):
            if sub.rstrip("/").split("/")[-1] in SYSTEM_NAMES:
                res["system_ignored"] += 1
            continue
        keep.append(p)
    res["ignored"] = keep
    by_rule = {}
    for i, p in enumerate(keep):                        # правило — для каждого файла (первые 200), сгруппировано по правилу
        top_dir = _sub(p, rel).split("/")[0]
        if i >= 200 and top_dir in res["rules"]:
            rule = res["rules"][top_dir]
        else:
            code, o, _ = git(top, "check-ignore", "-v", "--no-index", p.rstrip("/"))
            rule = o.strip().split("\t")[0] if o.strip() else "правило не найдено (git check-ignore)"
        by_rule.setdefault(rule, []).append(_sub(p, rel))
        res["rules"].setdefault(top_dir, rule)
    res["rule_files"] = by_rule
    return res


def foreign_dirs(top, out=None):
    """Посторонние служебные папки инструментов: в корне репозитория и в <OUT>."""
    found = []
    for base in [top] + ([Path(out)] if out else []):
        if not base or not Path(base).is_dir():
            continue
        for name in FOREIGN_HINTS:
            if (Path(base) / name).exists():
                found.append(str((Path(base) / name).relative_to(top)) if top and Path(base).resolve().is_relative_to(top) else name)
    return sorted(set(found))


def fix_root(top):
    """Служебные папки инструментов из корня репозитория → в корневой .gitignore (только те, что реально есть)."""
    if not top:
        return []
    gi = Path(top) / ".gitignore"
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    add = ["%s/" % d for d in TOOL_DIRS if (Path(top) / d).exists() and "%s/" % d not in lines and d not in lines]
    if add:
        gi.write_text("\n".join(lines + add) + "\n", encoding="utf-8")
    return add


def fix(out_dir, res, shots=None):
    out = Path(out_dir).resolve()
    if not out.is_dir():
        return []
    gi = out / ".gitignore"
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    rel = str(Path(res["out"]).relative_to(res["repo"])) if res.get("repo") else "."
    dirs = sorted({_sub(p, rel).split("/")[0] for p in res["ignored"]})
    add = ["!%s/" % d for d in dirs if "!%s/" % d not in lines and not (shots == "local" and d == "competitors" and
                                                                        all(_sub(p, rel).startswith(SHOTS_LINE) for p in res["ignored"]
                                                                            if _sub(p, rel).split("/")[0] == d))]
    for s in SERVICE_LINES:
        if s not in lines and s not in add and (s != "build/node/" or (out / "build").exists()):
            add.append(s)
    if shots == "local" and SHOTS_LINE not in lines:
        add.append(SHOTS_LINE)
    if shots in ("git", "previews") and SHOTS_LINE in lines:
        lines = [x for x in lines if x != SHOTS_LINE]
        gi.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if add:
        gi.write_text("\n".join(lines + add) + "\n", encoding="utf-8")
    return add


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--repo")
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--shots", choices=SHOTS_CHOICES, help="скриншоты конкурентов: git | local | previews (FB-042)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_cfg(a.out)
    shots = shots_choice(cfg, a.shots)
    res = analyse(a.out, a.repo, shots_local=shots == "local")
    if "error" in res:
        print("git: %s" % res["error"], file=sys.stderr)
        return 2
    if not res["inside_repo"]:
        msg = "OUT вне git-репозитория — проверка .gitignore не нужна"
        print(json.dumps({**res, "message": msg}, ensure_ascii=False) if a.json else msg)
        return 0
    top = Path(res["repo"])
    added = fix(a.out, res, shots) if (a.fix or a.shots) else []
    root_added = fix_root(top) if a.fix else []
    if added or root_added:
        res = analyse(a.out, a.repo, shots_local=shots == "local")
        res["fixed"] = added
        res["fixed_root"] = root_added
    res["foreign"] = foreign_dirs(top, a.out)
    res["shots"] = shots
    vis = visibility(cfg)
    res["shots_question"] = (not shots and vis in ("public", "unknown", "") and (Path(a.out) / "competitors" / "shots").is_dir()
                             and any((Path(a.out) / "competitors" / "shots").iterdir()))
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif not res["ignored"]:
        print("OK: файлы прогона не игнорируются git (в коммит попадёт %d файлов)%s%s%s" % (
            res["tracked_or_new"], "; добавлено в .gitignore: " + ", ".join(added) if added else "",
            "; в корневой .gitignore: " + ", ".join(root_added) if root_added else "",
            "; системные файлы (.DS_Store и т. п.) игнорируются как положено: %d" % res["system_ignored"] if res["system_ignored"] else ""))
    else:
        print("ВНИМАНИЕ: git молча исключит %d файл(ов)/папок прогона:" % len(res["ignored"]))
        for p in res["ignored"][:20]:
            print("  - %s" % p)
        for rule, files in res["rule_files"].items():
            print("  правило %s скрывает: %s%s" % (rule, ", ".join(files[:5]), " …" if len(files) > 5 else ""))
        print("Исправить: check_gitignore.py %s --fix (допишет «!<папка>/» в %s/.gitignore)" % (a.out, a.out))
    if not a.json:
        if res["foreign"]:
            print("Посторонние служебные папки (в git не нужны): %s%s" % (", ".join(res["foreign"]),
                  "" if a.fix else " — check_gitignore.py <OUT> --fix допишет .playwright-mcp/ в корневой .gitignore"))
        if shots == "local":
            print("Скриншоты конкурентов: только локально (competitors/shots/ в .gitignore; сайт — уменьшенные копии в deliverables/assets/img)")
        elif res["shots_question"]:
            print("ВОПРОС ВЛАДЕЛЬЦУ: видимость репозитория %s — скриншоты чужих сайтов в git / только локально / сжатые превью? "
                  "Ответ → run-config output.competitor_shots и check_gitignore.py <OUT> --shots <выбор> (references/safety.md, §5)" % vis)
    return 1 if res["ignored"] else 0


if __name__ == "__main__":
    sys.exit(main())
