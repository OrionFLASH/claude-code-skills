#!/usr/bin/env python3
"""Actual folder of the installed site-qa-audit skill (SKILL_DIR) — one stable path for the run and its executors.

  skill_dir.py                 print SKILL_DIR (absolute path)
  skill_dir.py --json          SKILL_DIR, source, version, all candidates and warnings
  skill_dir.py --check PATH    exit 0 if PATH is a usable skill folder (SKILL.md + scripts/url_guard.py), else 1
  skill_dir.py --export        `export SITE_QA_AUDIT_DIR="…"` line for the shell

Where it looks, in this order (the first usable one wins):
  1. SITE_QA_AUDIT_DIR (environment; set it in ~/.claude/settings.json → env for a fixed path);
  2. the folder of this script, unless it is a developer working copy of the skills repository;
  3. the installed plugin: ~/.claude/plugins/installed_plugins.json → installPath;
  4. the plugin cache: ~/.claude/plugins/cache/<marketplace>/site-qa-audit/<newest version>/;
  5. ~/.claude/skills/site-qa-audit, then <cwd>/.claude/skills/site-qa-audit;
  6. the developer working copy (only if nothing else is installed; marked source=dev-checkout).
Symlinks are not resolved: a path like ~/.claude/skills/site-qa-audit stays as it is.
Exit codes: 0 found, 1 nothing usable (or --check failed).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

NAME = "site-qa-audit"
ENV = "SITE_QA_AUDIT_DIR"
MARKER = Path("scripts") / "url_guard.py"


def version_of(d):
    try:
        return json.loads((d / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        return None


def problem(d):
    """None if d is a usable skill folder, else the reason."""
    if not d:
        return "путь не задан"
    d = Path(d)
    if not d.is_dir():
        return "папки нет"
    skill = d / "SKILL.md"
    if not skill.is_file():
        return "нет SKILL.md"
    head = skill.read_text(encoding="utf-8", errors="replace")[:2000]
    if not re.search(rf"^name:\s*{re.escape(NAME)}\s*$", head, re.M):
        return f"SKILL.md не от {NAME}"
    if not (d / MARKER).is_file():
        return f"нет {MARKER.as_posix()}"
    return None


def is_dev_checkout(d):
    root = Path(d).parent.parent
    return Path(d).parent.name == "skills" and (root / "tools" / "validate.sh").is_file() and \
        (root / ".claude-plugin" / "marketplace.json").is_file()


def vkey(v):
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.+-]", v or "0"))


def plugin_candidates(home):
    out = []
    reg = home / ".claude" / "plugins" / "installed_plugins.json"
    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
        plugins = data.get("plugins", data) if isinstance(data, dict) else {}
        for key, entries in plugins.items():
            if key.split("@")[0] != NAME:
                continue
            for e in entries if isinstance(entries, list) else [entries]:
                if isinstance(e, dict) and e.get("installPath"):
                    out.append(("plugin", Path(e["installPath"])))
    except (OSError, ValueError, AttributeError):
        pass
    cache = home / ".claude" / "plugins" / "cache"
    found = []
    try:
        for market in sorted(cache.iterdir()):
            base = market / NAME
            if base.is_dir():
                found += [v for v in base.iterdir() if v.is_dir()]
    except OSError:
        pass
    # claude-code-skills first, then newest version
    found.sort(key=lambda p: (p.parent.parent.name != "claude-code-skills", tuple(-x for x in vkey(p.name))))
    out += [("plugin-cache", p) for p in found]
    return out


def candidates(cwd=None):
    home = Path.home()
    own = Path(os.path.abspath(os.path.dirname(__file__))).parent
    env = os.environ.get(ENV)
    out = []
    if env:
        out.append(("env", Path(os.path.abspath(os.path.expanduser(env)))))
    if not is_dev_checkout(own):
        out.append(("self", own))
    out += plugin_candidates(home)
    out.append(("user-skills", home / ".claude" / "skills" / NAME))
    out.append(("project-skills", Path(cwd or os.getcwd()) / ".claude" / "skills" / NAME))
    if is_dev_checkout(own):
        out.append(("dev-checkout", own))
    return out


def find(cwd=None):
    rows, chosen, warnings, seen = [], None, [], set()
    for source, path in candidates(cwd):
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        why = problem(path)
        rows.append({"source": source, "path": key, "ok": why is None, "problem": why, "version": version_of(path) if why is None else None})
        if why and source == "env":
            warnings.append(f"{ENV}={key} не подходит: {why} — используется следующий вариант")
        if why is None and chosen is None:
            chosen = rows[-1]
    if chosen and chosen["source"] == "dev-checkout":
        warnings.append("найдена только рабочая копия репозитория скилов (разработка): для прогонов установите скил "
                        f"(INSTALL.md) или задайте {ENV}")
    own = str(Path(os.path.abspath(os.path.dirname(__file__))).parent)
    if chosen and chosen["path"] != own:
        warnings.append(f"скрипт запущен из {own}, а SKILL_DIR прогона — {chosen['path']} (версия {chosen['version']}): "
                        "в заданиях используйте SKILL_DIR")
    return {"skill_dir": chosen["path"] if chosen else None, "source": chosen["source"] if chosen else None,
            "version": chosen["version"] if chosen else None, "env": os.environ.get(ENV), "candidates": rows,
            "warnings": warnings}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", metavar="PATH")
    ap.add_argument("--export", action="store_true")
    a = ap.parse_args()
    if a.check is not None:
        why = problem(Path(os.path.expanduser(a.check)))
        if why:
            print(f"SKILL_DIR недоступен: {a.check}: {why} — СТОП, скрипты скила по этому пути не запускаются")
            sys.exit(1)
        print(f"ok {os.path.abspath(os.path.expanduser(a.check))} {version_of(Path(os.path.expanduser(a.check))) or ''}".rstrip())
        return
    res = find()
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    elif not res["skill_dir"]:
        sys.stderr.write("skill_dir: установленный site-qa-audit не найден (INSTALL.md)\n")
    elif a.export:
        print(f'export {ENV}="{res["skill_dir"]}"')
    else:
        print(res["skill_dir"])
        for w in res["warnings"]:
            sys.stderr.write(f"skill_dir: {w}\n")
    sys.exit(0 if res["skill_dir"] else 1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
