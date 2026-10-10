#!/usr/bin/env python3
"""Проверка и установка инструментов product-strategy (references/tools.md).

  check_env.py [--out <OUT>] [--json FILE] [--session-skills "a,b,…"] [--quiet]
      таблица «компонент / статус / версия / зачем / как исправить»; код 0 — можно работать, 1 — нет обязательного
  check_env.py --install-node [<OUT>]
      локальная установка Node-модулей (playwright, pptxgenjs) в кэш пользователя ~/.cache/product-strategy/node и Chromium;
      ничего не ставит глобально — это единственная установка, которую скилл делает без вопроса; путь пишется в run-config
  check_env.py --print-node-dir [--out <OUT>]   папка модулей (для --node-dir / PS_NODE_DIR)
  check_env.py --plan [--out <OUT>]
      что не хватает и какие команды поставят это (для вопроса пользователю: системные пакеты, pip, плагины)

Статусы: OK, WARN (есть замена или не обязательно), MISS (нет), FAIL (нет обязательного).
Уровни: required — без него нельзя; recommended — без него хуже (меньше форматов или уверенности); optional — усилители.
--session-skills — имена скиллов, которые видит текущая сессия Claude Code (агент передаёт свой список): по ним
проверяются плагины, установленные не через installed_plugins.json. Только стандартная библиотека.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NODE_PKG = HERE / "node" / "package.json"
HOME = Path.home()
CLAUDE = HOME / ".claude"

# Скиллы/плагины-усилители: имя → (уровень, фазы, как поставить). Имя — префикс плагина или имя скилла.
ENHANCERS = [
    ("superpowers", "recommended", "план и брейншторм (фаза 0)", "claude plugin install superpowers@claude-plugins-official"),
    ("typesafe-triage", "recommended", "выбор модели субагентов, --batch", "claude plugin marketplace add OrionFLASH/claude-code-skills && claude plugin install typesafe-triage@claude-code-skills"),
    ("typesafe", "optional", "оценка предложений Jev (typesafe_eval.py)", "claude plugin marketplace add typesafe-ai/skills && claude plugin install typesafe@typesafe-ai"),
    ("marketing", "optional", "конкуренты, кампании, контент", "claude plugin marketplace add anthropics/knowledge-work-plugins && claude plugin install marketing@knowledge-work-plugins"),
    ("product-management", "optional", "спеки, исследование, брейншторм", "claude plugin marketplace add anthropics/knowledge-work-plugins && claude plugin install product-management@knowledge-work-plugins"),
    ("data", "optional", "анализ и проверка данных", "claude plugin marketplace add anthropics/knowledge-work-plugins && claude plugin install data@knowledge-work-plugins"),
    ("cro-audit-and-test-kit", "optional", "CRO-аудит, A/B-планы", "claude plugin install cro-audit-and-test-kit@anthropic-plugin-directory"),
    ("marketing-ideas-kit", "optional", "идеи, ранжирование, окупаемость", "claude plugin install marketing-ideas-kit@anthropic-plugin-directory"),
    ("churn-prevention-kit", "optional", "удержание и отток", "claude plugin install churn-prevention-kit@anthropic-plugin-directory"),
    ("seo", "optional", "SEO/GEO-аудит и кластеры", "см. INSTALL.md → «Дополнительные модули» (скилл seo)"),
    ("ux-audit", "optional", "UX-аудит запущенного приложения", "см. INSTALL.md → «Дополнительные модули» (ux-audit)"),
    ("ui-ux-pro-max", "optional", "дизайн-решения макетов", "см. INSTALL.md → «Дополнительные модули» (ui-ux-pro-max)"),
    ("frontend-design", "optional", "дизайн макетов", "claude plugin install frontend-design@claude-plugins-official"),
    ("dataviz", "optional", "правила графиков", "встроенный скилл Claude Code (dataviz)"),
    ("playwright", "optional", "Playwright MCP для ручного просмотра", "claude plugin install playwright@claude-plugins-official"),
    ("site-qa-audit", "optional", "глубокий аудит сайта", "claude plugin install site-qa-audit@claude-code-skills"),
]


def run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def version_of(cmd, rx=r"(\d+\.\d+(?:\.\d+)?)"):
    if not shutil.which(cmd[0]):
        return None
    code, out = run(cmd)
    m = re.search(rx, out)
    return m.group(1) if (code == 0 and m) else None


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:3])


CACHE_NODE = Path.home() / ".cache" / "product-strategy" / "node"


def node_dir(out):
    """Папка Node-модулей: env PS_NODE_DIR → run-config tools.node_dir → <OUT>/build/node (прежние прогоны) → кэш пользователя
    ~/.cache/product-strategy/node (по умолчанию: результат остаётся чистым и переносимым, модули общие для прогонов)."""
    if os.environ.get("PS_NODE_DIR"):
        return Path(os.environ["PS_NODE_DIR"]).expanduser()
    if out:
        cfg = Path(out) / "build" / "run-config.json"
        try:
            nd = (json.loads(cfg.read_text(encoding="utf-8")).get("tools") or {}).get("node_dir")
            if nd:
                return Path(nd).expanduser()
        except (OSError, ValueError):
            pass
        legacy = Path(out) / "build" / "node"
        if (legacy / "node_modules").is_dir():
            return legacy
    return CACHE_NODE


def has_node_module(nd, name):
    return bool(nd) and (nd / "node_modules" / name / "package.json").exists()


def chromium_cached():
    roots = [Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])] if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") else []
    roots += [HOME / "Library" / "Caches" / "ms-playwright", HOME / ".cache" / "ms-playwright",
              Path(os.environ.get("LOCALAPPDATA", HOME)) / "ms-playwright"]
    for r in roots:
        if r.is_dir() and any(p.name.startswith("chromium") for p in r.iterdir()):
            return str(r)
    return None


def session_skills_file(out):
    return Path(out) / "build" / "session-skills.txt" if out else None


def load_session_skills(explicit, out):
    """Скиллы сессии: явный --session-skills → env PS_SESSION_SKILLS → файл прогона (его пишет первый вызов). Один источник правды
    для таблицы и --plan: иначе скилл, видимый в сессии, в плане выглядит как «нужно согласие»."""
    names = [x.strip() for x in explicit if x.strip()]
    if not names and os.environ.get("PS_SESSION_SKILLS"):
        names = [x.strip() for x in os.environ["PS_SESSION_SKILLS"].split(",") if x.strip()]
    f = session_skills_file(out)
    if not names and f and f.is_file():
        names = [x.strip() for x in f.read_text(encoding="utf-8").split(",") if x.strip()]
    if names and f:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(",".join(names), encoding="utf-8")
    return names


def installed_skills(session=None):
    """Имена плагинов и скиллов из всех источников: installed_plugins.json, ~/.claude/skills, кэш плагинов, сессия."""
    names = set()
    try:
        data = json.loads((CLAUDE / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        for key in (data.get("plugins") or data):
            names.add(key.split("@")[0])
    except (OSError, ValueError):
        pass
    for base in (CLAUDE / "skills",):
        if base.is_dir():
            names.update(p.name for p in base.iterdir() if (p / "SKILL.md").exists())
    cache = CLAUDE / "plugins" / "cache"
    if cache.is_dir():
        for mp in cache.iterdir():
            if mp.is_dir():
                names.update(p.name for p in mp.iterdir() if p.is_dir())
    for s in session or []:
        s = s.strip()
        if s:
            names.add(s.split(":")[0])
            names.add(s)
    return names


def python_mod(name):
    code, out = run([sys.executable, "-c", "import %s,sys;print(getattr(%s,'__version__','?'))" % (name, name)])
    return out.strip().splitlines()[-1] if code == 0 and out.strip() else None


def collect(out=None, session=None):
    rows = []

    def add(name, level, status, version, why, fix=""):
        rows.append({"name": name, "level": level, "status": status, "version": version or "", "why": why, "fix": fix})

    pv = "%d.%d.%d" % sys.version_info[:3]
    add("python3", "required", "OK" if sys.version_info >= (3, 10) else "FAIL", pv, "все скрипты скилла",
        "" if sys.version_info >= (3, 10) else "поставьте Python 3.10+ (python.org или brew install python)")
    gv = version_of(["git", "--version"])
    add("git", "required", "OK" if gv else "FAIL", gv, "история репозитория, ветка результата", "" if gv else "brew install git / https://git-scm.com")
    nv = version_of(["node", "--version"])
    ok_node = bool(nv) and vtuple(nv) >= (18,)
    add("node", "recommended", "OK" if ok_node else "MISS", nv, "скриншоты, smoke-тест страницы, PPTX, PDF",
        "" if ok_node else "brew install node (нужен 18+) или https://nodejs.org")
    npv = version_of(["npm", "--version"])
    add("npm", "recommended", "OK" if npv else "MISS", npv, "локальная установка модулей прогона", "" if npv else "ставится вместе с node")
    nd = node_dir(out)
    fix_node = "python3 %s --install-node%s" % (Path(__file__).resolve(), (" " + str(out)) if out else "")
    for mod, why in (("playwright", "браузер: аудит сайта, макеты, конкуренты, smoke, PDF"), ("pptxgenjs", "презентация PPTX")):
        ok = has_node_module(nd, mod)
        add("node:" + mod, "recommended", "OK" if ok else ("MISS" if out else "WARN"), "", why,
            "" if ok else fix_node)
    ch = chromium_cached()
    add("chromium (playwright)", "recommended", "OK" if ch else "MISS", ch or "", "движок для скриншотов и PDF",
        "" if ch else fix_node + "  (ставит и браузер)")
    ghv = version_of(["gh", "--version"])
    if ghv:
        code, txt = run(["gh", "auth", "status"])
        add("gh", "recommended", "OK" if code == 0 else "WARN", ghv, "Issues/PR репозитория (только чтение)",
            "" if code == 0 else "gh auth login (делает пользователь сам)")
    else:
        add("gh", "recommended", "MISS", "", "Issues/PR репозитория (только чтение)", "brew install gh && gh auth login")
    for mod, lvl, why, fix in (("certifi", "optional", "сертификаты для check_links.py", "pip install --user certifi"),
                               ("openpyxl", "optional", "дополнительная проверка XLSX в тестах", "pip install --user openpyxl")):
        v = python_mod(mod)
        add("py:" + mod, lvl, "OK" if v else "WARN", v, why, "" if v else fix)
    key = bool(os.environ.get("TYPESAFE_API_KEY"))
    add("TYPESAFE_API_KEY", "optional", "OK" if key else "WARN", "задан" if key else "", "оценка предложений Jev",
        "" if key else "ключ с console.typesafe.ai → env TYPESAFE_API_KEY (значение не печатается)")
    lo = version_of(["soffice", "--version"])
    add("libreoffice", "optional", "OK" if lo else "WARN", lo, "необязательно: PDF печатается через Chromium", "")
    have = installed_skills(session)
    for name, lvl, why, fix in ENHANCERS:
        ok = name in have or any(h.startswith(name + ":") for h in have)
        add("skill:" + name, lvl, "OK" if ok else ("MISS" if lvl == "recommended" else "WARN"), "", why, "" if ok else fix)
    return rows


def install_node(out=None):
    """Локальная установка модулей: по умолчанию в кэш пользователя ~/.cache/product-strategy/node (общий для прогонов; PS_NODE_DIR
    или run-config tools.node_dir меняют место), пакеты — из scripts/node/package.json + Chromium для Playwright. Глобально не ставит.
    Путь записывается в <OUT>/build/run-config.json (tools.node_dir), если есть."""
    if not shutil.which("npm"):
        print("нет npm: поставьте Node.js 18+ (brew install node или https://nodejs.org) и повторите", file=sys.stderr)
        return 2
    nd = node_dir(out).resolve()
    nd.mkdir(parents=True, exist_ok=True)
    if NODE_PKG.exists():
        shutil.copyfile(NODE_PKG, nd / "package.json")
        cmd = ["npm", "install", "--prefix", str(nd), "--no-audit", "--no-fund"]
    else:
        (nd / "package.json").write_text('{"name":"product-strategy-node","private":true,"type":"module"}\n', encoding="utf-8")
        cmd = ["npm", "install", "--prefix", str(nd), "--no-audit", "--no-fund", "playwright", "pptxgenjs"]
    print("$ " + " ".join(cmd))
    code = subprocess.call(cmd)
    if code:
        return code
    if not chromium_cached():
        npx = shutil.which("npx") or "npx"
        cmd = [npx, "--prefix", str(nd), "playwright", "install", "chromium"]
        print("$ " + " ".join(cmd))
        code = subprocess.call(cmd, cwd=str(nd))
    if out and code == 0:
        cfgp = Path(out) / "build" / "run-config.json"
        try:
            cfg = json.loads(cfgp.read_text(encoding="utf-8"))
            cfg.setdefault("tools", {})["node_dir"] = str(nd)
            cfgp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, ValueError):
            pass
    print("готово: PS_NODE_DIR=%s" % nd if code == 0 else "ошибка установки (код %d)" % code)
    return code


def print_table(rows):
    w = max(len(r["name"]) for r in rows)
    print("%-*s  %-11s  %-5s  %-12s  %s" % (w, "компонент", "уровень", "стат.", "версия", "зачем / как исправить"))
    for r in rows:
        tail = r["why"] + (" → " + r["fix"] if r["fix"] else "")
        print("%-*s  %-11s  %-5s  %-12s  %s" % (w, r["name"], r["level"], r["status"], (r["version"] or "")[:12], tail))


def plan(rows):
    auto = [r for r in rows if r["status"] != "OK" and r["name"].startswith(("node:", "chromium"))]
    ask = [r for r in rows if r["status"] in ("MISS", "FAIL") and r not in auto and r["fix"]]
    opt = [r for r in rows if r["status"] == "WARN" and r["fix"] and r not in auto]
    return {"auto_local": auto, "ask_user": ask, "optional": opt}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", help="папка прогона <OUT> (для проверки локальных Node-модулей)")
    ap.add_argument("--json", help="сохранить результат в файл (обычно <OUT>/build/env.json)")
    ap.add_argument("--session-skills", default="", help="скиллы, видимые в текущей сессии, через запятую")
    ap.add_argument("--install-node", nargs="?", const="", metavar="OUT", help="поставить Node-модули в кэш пользователя "
                    "(~/.cache/product-strategy/node; PS_NODE_DIR меняет место); OUT — записать путь в run-config")
    ap.add_argument("--print-node-dir", action="store_true", help="напечатать папку Node-модулей (для --node-dir и PS_NODE_DIR)")
    ap.add_argument("--plan", action="store_true", help="что поставить: автоматически (локально) и с вопросом пользователю")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    if a.print_node_dir:
        print(node_dir(a.out))
        return 0
    if a.install_node is not None:
        return install_node(a.install_node or a.out)
    rows = collect(a.out, load_session_skills(a.session_skills.split(","), a.out))
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps({"rows": rows, "plan": plan(rows)}, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.plan:
        p = plan(rows)
        print("Поставлю сам (локально, в папку прогона, без вопроса):")
        for r in p["auto_local"]:
            print("  - %s: %s" % (r["name"], r["fix"]))
        print("Нужно согласие пользователя (системные пакеты, плагины, вход):")
        for r in p["ask_user"]:
            print("  - %s (%s): %s" % (r["name"], r["why"], r["fix"]))
        print("Необязательные усилители:")
        for r in p["optional"]:
            print("  - %s (%s): %s" % (r["name"], r["why"], r["fix"]))
    elif not a.quiet:
        print_table(rows)
    fail = [r for r in rows if r["status"] == "FAIL"]
    if not a.quiet:
        print("\nИтог: %s" % ("можно работать" if not fail else "нет обязательного: " + ", ".join(r["name"] for r in fail)))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
