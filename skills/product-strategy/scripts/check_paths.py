#!/usr/bin/env python3
"""Проверка «агент писал не туда»: файлы, изменённые за волну, против разрешённых путей из раздела «Выдача» брифов.

  check_paths.py <OUT> --start <волна>                                  снимок файлов <OUT> (и git status репозитория)
  check_paths.py <OUT> --wave <волна> --briefs B1.md [B2.md …] [--allow GLOB …] [--json]
                                                                        проверка после волны по снимку
  check_paths.py <OUT> --since <ISO-время | файл> --briefs …            без снимка: файлы новее метки (как find -newer)
  check_paths.py <OUT> --list-allowed --briefs …                        разрешённые шаблоны из «Выдачи» брифов

Снимок — build/waves/<волна>.json: {относительный путь: [размер, mtime_ns]} по <OUT> и список изменённых файлов репозитория
вне <OUT> (`git status --porcelain`); абсолютных путей в нём нет. Проверка находит новые, изменённые и удалённые файлы
и сверяет их с шаблонами:
  - раздел «Выдача» каждого брифа (`## Выдача …` до следующего заголовка): пути в обратных кавычках до первого « — »
    пункта; `{OUT}/`, `<OUT>/` и путь <OUT> от корня репозитория срезаются; `<…>`, `{…}`, `NN`, `xx`, `…` → `*`;
    путь без папки наследует папку первого пути предложения; имена скриптов (*.py, *.mjs) пропускаются; к разрешённому `X.html` добавляются `X*.png` (снимки макетов); предложение со словами «не трогать», «не создавать»,
    «не писать», «не редактир» — запрет (его пути не разрешаются);
  - служебные файлы оркестратора (build/STATUS.md, STRATEGY_TASKS.md, build/briefs/*, build/agents.json,
    build/dispatch.json, build/triage-*.json, build/waves/*) — разрешены, если не задан --no-default-allow;
  - --allow GLOB — дополнительные разрешения (например, общий файл, который в эту волну правит сам оркестратор).
Изменения репозитория вне <OUT>, которых не было в снимке, — всегда нарушение.
Код выхода: 0 — всё в разрешённых путях; 1 — есть записи вне путей; 2 — ошибка (нет снимка, брифа, папки).
Только стандартная библиотека.
"""
import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SKIP_PARTS = {"node_modules", ".git", "__pycache__", ".pytest_cache"}
SKIP_PREFIX = ("build/node/", "build/waves/")
SKIP_SUFFIX = (".tmp", ".pyc", ".swp")
SKIP_NAMES = {".DS_Store", "Thumbs.db"}
ORCHESTRATOR_ALLOW = ["build/STATUS.md", "STRATEGY_TASKS.md", "build/briefs/*", "build/agents.json", "build/dispatch.json",
                      "build/triage-*.json", "build/waves/*"]
DENY_WORDS = re.compile(r"не\s+трогать|не\s+создавать|не\s+писать|не\s+редактир|не\s+менять|запрещ", re.I)
TICK = re.compile(r"`([^`]+)`")
PATHLIKE = re.compile(r"/|\.[A-Za-z0-9]{1,5}$")
SCRIPT_EXT = (".py", ".mjs", ".cjs", ".sh", ".js")


def git(repo, *args, timeout=60):
    try:
        r = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return r.returncode, r.stdout


def repo_root(out):
    code, so = git(out, "rev-parse", "--show-toplevel")
    return Path(so.strip()).resolve() if code == 0 and so.strip() else None


def out_rel(out, repo):
    if not repo:
        return None
    try:
        r = Path(out).resolve().relative_to(repo).as_posix()
    except ValueError:
        return None
    return "" if r == "." else r


def skipped(rel):
    parts = rel.split("/")
    return (any(p in SKIP_PARTS for p in parts) or rel.startswith(SKIP_PREFIX) or rel.endswith(SKIP_SUFFIX)
            or parts[-1] in SKIP_NAMES)


def snapshot_files(out):
    res = {}
    for root, dirs, files in os.walk(out):
        dirs[:] = [d for d in dirs if d not in SKIP_PARTS]
        for f in files:
            full = Path(root) / f
            rel = full.relative_to(out).as_posix()
            if skipped(rel) or full.is_symlink():
                continue
            try:
                st = full.stat()
            except OSError:
                continue
            res[rel] = [st.st_size, st.st_mtime_ns]
    return res


def repo_changes(repo, orel):
    """Изменённые/новые файлы репозитория вне <OUT> (git status --porcelain)."""
    if not repo:
        return []
    code, so = git(repo, "status", "--porcelain", "--untracked-files=all")
    if code != 0:
        return []
    res = []
    for line in so.splitlines():
        p = line[3:].strip().strip('"')
        if " -> " in p:
            p = p.split(" -> ", 1)[1]
        if orel is not None and orel and (p == orel or p.startswith(orel + "/")):
            continue
        if orel == "":                      # <OUT> — корень репозитория: всё «внутри»
            continue
        res.append(p)
    return sorted(set(res))


# ---------------------------------------------------------------- разбор брифа

def outputs_section(text):
    """Строки раздела «Выдача» (до следующего заголовка того же или более высокого уровня)."""
    lines = text.splitlines()
    res, level = [], None
    for ln in lines:
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            if level is not None and len(m.group(1)) <= level:
                break
            if level is None and re.search(r"Выдача|Output", m.group(2), re.I):
                level = len(m.group(1))
                continue
        if level is not None:
            res.append(ln)
    return res


def to_glob(token, orel):
    t = token.strip().strip(".,;:")
    for pre in ("{OUT}/", "<OUT>/", "./"):
        if t.startswith(pre):
            t = t[len(pre):]
    if orel and t.startswith(orel + "/"):
        t = t[len(orel) + 1:]
    t = re.sub(r"<[^>]*>|\{[^}]*\}|…|\.\.\.", "*", t)
    t = re.sub(r"\bNN\b", "*", t)
    t = re.sub(r"(?<=[A-Z])xx\b", "*", t)
    t = re.sub(r"\*+", "*", t)
    if t.endswith("/"):
        t += "*"
    return t


def brief_patterns(text, orel=None):
    """→ (разрешённые шаблоны, запрещённые шаблоны) из раздела «Выдача»."""
    allow, deny = [], []
    for ln in outputs_section(text):
        if not ln.strip():
            continue
        body = re.sub(r"^\s*[-*]\s+", "", ln)
        for sentence in re.split(r"(?<=[.;])\s+(?=[А-ЯA-Z])", body):
            target = deny if DENY_WORDS.search(sentence) else allow
            head = sentence.split(" — ", 1)[0]              # после « — » — описание (там бывают ссылки на чужие файлы)
            first_dir = ""
            for tok in TICK.findall(head):
                tok = tok.strip()
                if " " in tok or not PATHLIKE.search(tok) or tok.startswith(("http", "{\"", "[")):
                    continue
                if "/" not in tok and tok.endswith(SCRIPT_EXT):
                    continue                                # имя скрипта, а не путь выдачи
                g = to_glob(tok, orel)
                if not g or g == "*":
                    continue
                if "/" not in g and first_dir:
                    g = first_dir + g
                elif "/" in g and not first_dir:
                    first_dir = g.rsplit("/", 1)[0] + "/"
                if g not in target:
                    target.append(g)
    for g in list(allow):                                   # снимки макетов (shoot_mockups.mjs) — рядом с HTML
        if g.endswith(".html"):
            for extra in (g[:-5] + ".png", g[:-5] + "*.png"):
                if extra not in allow:
                    allow.append(extra)
    return allow, deny


def matches(rel, patterns):
    return any(fnmatch.fnmatchcase(rel, p) or (p.endswith("/*") and rel.startswith(p[:-1])) for p in patterns)


# ---------------------------------------------------------------- проверка

def changed_since_snapshot(snap, now):
    res = []
    for rel, meta in now.items():
        if rel not in snap:
            res.append((rel, "новый"))
        elif list(meta) != list(snap[rel]):
            res.append((rel, "изменён"))
    for rel in snap:
        if rel not in now:
            res.append((rel, "удалён"))
    return sorted(res)


def changed_since_time(now, ts_ns):
    return sorted((rel, "новый/изменён") for rel, (_size, mt) in now.items() if mt > ts_ns)


def parse_since(value):
    p = Path(value).expanduser()
    if p.exists():
        return p.stat().st_mtime_ns
    try:
        return int(datetime.fromisoformat(value).timestamp() * 1e9)
    except ValueError:
        raise SystemExit("ошибка: --since — ISO-время (2026-10-11T12:00) или путь к файлу-метке")


def check(out, briefs, extra_allow=(), wave=None, since=None, default_allow=True):
    """→ отчёт {changed, violations, outside, allowed_by_brief, patterns}."""
    out = Path(out).resolve()
    repo = repo_root(out)
    orel = out_rel(out, repo)
    allow, deny, by_brief = [], [], {}
    for b in briefs:
        bp = Path(b)
        if not bp.is_absolute() and not bp.exists() and (out / b).exists():
            bp = out / b
        if not bp.is_file():
            raise FileNotFoundError(b)
        a, d = brief_patterns(bp.read_text(encoding="utf-8"), orel)
        by_brief[bp.name] = a
        allow += a
        deny += d
    allow += list(extra_allow) + (ORCHESTRATOR_ALLOW if default_allow else [])
    now = snapshot_files(out)
    outside_before = []
    if wave:
        sp = out / "build" / "waves" / ("%s.json" % wave)
        if not sp.is_file():
            raise FileNotFoundError("снимок волны %s (сначала --start %s)" % (wave, wave))
        snap = json.loads(sp.read_text(encoding="utf-8"))
        changed = changed_since_snapshot(snap.get("files") or {}, now)
        outside_before = snap.get("git_outside") or []
    else:
        changed = changed_since_time(now, since)
    violations = []
    for rel, kind in changed:
        explicit = list(extra_allow) + (ORCHESTRATOR_ALLOW if default_allow else [])
        if matches(rel, deny) and not matches(rel, explicit):
            violations.append({"file": rel, "change": kind, "why": "запрещён брифом («не трогать»)"})
        elif not matches(rel, allow):
            violations.append({"file": rel, "change": kind, "why": "нет в «Выдаче» брифов"})
    outside = [p for p in repo_changes(repo, orel) if p not in outside_before] if wave else []
    for p in outside:
        violations.append({"file": "../" + p if orel else p, "change": "вне <OUT>", "why": "изменение репозитория вне папки прогона"})
    allowed_counts = {name: sum(1 for rel, _ in changed if matches(rel, pats)) for name, pats in by_brief.items()}
    return {"wave": wave, "changed": [{"file": r, "change": k} for r, k in changed], "violations": violations,
            "outside_repo": outside, "allowed_by_brief": allowed_counts, "patterns": {"allow": allow, "deny": deny}}


def start(out, wave):
    out = Path(out).resolve()
    repo = repo_root(out)
    snap = {"wave": wave, "created": datetime.now().isoformat(timespec="seconds"), "files": snapshot_files(out),
            "git_outside": repo_changes(repo, out_rel(out, repo))}
    d = out / "build" / "waves"
    d.mkdir(parents=True, exist_ok=True)
    (d / ("%s.json" % wave)).write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return snap


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--start", metavar="ВОЛНА", help="снять снимок перед волной")
    ap.add_argument("--wave", metavar="ВОЛНА", help="проверить изменения с момента снимка волны")
    ap.add_argument("--since", help="ISO-время или файл-метка (вместо снимка)")
    ap.add_argument("--briefs", nargs="*", default=[], help="брифы волны (build/briefs/*.md)")
    ap.add_argument("--allow", nargs="*", default=[], help="дополнительные разрешённые шаблоны (относительно <OUT>)")
    ap.add_argument("--no-default-allow", action="store_true", help="не разрешать служебные файлы оркестратора")
    ap.add_argument("--list-allowed", action="store_true", help="показать шаблоны из «Выдачи» брифов и выйти")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out).expanduser()
    if not out.is_dir():
        print("ошибка: нет папки %s" % out, file=sys.stderr)
        return 2
    if a.start:
        snap = start(out, a.start)
        print("снимок волны %s: %d файлов → build/waves/%s.json" % (a.start, len(snap["files"]), a.start))
        return 0
    if a.list_allowed:
        orel = out_rel(out, repo_root(out))
        res = {}
        for b in a.briefs:
            bp = Path(b) if Path(b).is_file() else out / b
            if not bp.is_file():
                print("ошибка: нет брифа %s" % b, file=sys.stderr)
                return 2
            al, de = brief_patterns(bp.read_text(encoding="utf-8"), orel)
            res[bp.name] = {"allow": al, "deny": de}
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if not a.wave and not a.since:
        ap.error("нужен --start, --wave или --since")
    if not a.briefs:
        ap.error("нужны --briefs (брифы волны)")
    try:
        rep = check(out, a.briefs, a.allow, wave=a.wave, since=parse_since(a.since) if a.since and not a.wave else None,
                    default_allow=not a.no_default_allow)
    except FileNotFoundError as e:
        print("ошибка: нет %s" % e, file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("check_paths: изменено файлов %d, вне разрешённых путей %d%s" % (
            len(rep["changed"]), len(rep["violations"]), (" (волна %s)" % a.wave) if a.wave else ""))
        for name, n in rep["allowed_by_brief"].items():
            print("  %s: в своих путях %d" % (name, n))
        for v in rep["violations"]:
            print("  НАРУШЕНИЕ %-10s %s — %s" % (v["change"], v["file"], v["why"]))
        if rep["violations"]:
            print("Разобрать: откатить чужую запись или разрешить явно (--allow), если её делал оркестратор.")
    return 1 if rep["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
