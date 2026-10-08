#!/usr/bin/env python3
"""Проверка окружения site-qa-audit при каждом запуске (references/setup.md).

  check_env.py [--fast] [--json out.json] [--no-browsers]
    --fast         не опрашивать `claude mcp list` (медленно) — Playwright MCP проверяется по списку плагинов
    --no-browsers  не запускать браузеры для проверки
    --json FILE    сохранить результат (таблица + доступные плагины/скилы/браузеры) для прогона
    --session-tools "a,b,…" | --session-tools-file FILE
                   имена инструментов, которые видит текущая сессия Claude Code (агент передаёт свой список):
                   по ним пишется, какие браузерные инструменты доступны именно сейчас, а не только «настроены»
    --browser-tools-only   только раздел «Браузерные инструменты» (быстро, без claude/gh/браузеров)
    --cdp-ports 9222,9223  проверить браузер с отладочным портом на localhost (подключение по CDP)

Печатает таблицу «компонент / версия / статус / примечание / как исправить».
Код выхода: 0 — можно работать, 1 — есть FAIL в обязательных компонентах.
"""
import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
sys.path.insert(0, str(HERE))
import envcheck as ec  # noqa: E402
import skill_dir as sd  # noqa: E402

# SKILL_DIR of the run (S-1): SITE_QA_AUDIT_DIR / this copy / installed plugin — never a developer working copy if an
# installed one exists. Fix commands below point at it.
SKILL = sd.find()
NODE_DIR = (Path(SKILL["skill_dir"]) if SKILL["skill_dir"] else HERE.parent) / "scripts" / "node"

# Внешние усилители: имя -> (тип, где искать, направления). Используются, только если найдены.
ENHANCERS = {
    "ux-audit": ("skill", "jezweb/claude-skills dev-tools", ["functional", "ux", "product"]),
    "e2e-test": ("skill", "coderphonui/opentest", ["functional"]),
    "ux-test": ("skill", "coderphonui/opentest", ["ux"]),
    "ux-heuristics": ("skill", "alpham8/agentic-webdev", ["ux"]),
    "laws-of-ux": ("skill", "alpham8/agentic-webdev", ["ux", "visual-ui"]),
    "ux-design-principles": ("skill", "alpham8/agentic-webdev", ["visual-ui"]),
    "ui-audit-redesign": ("skill", "alpham8/agentic-webdev", ["visual-ui", "product"]),
    "frontend-design": ("skill", "anthropic frontend-design", ["product"]),
    "resilience-audit": ("skill", "neonwatty/qa-skills", ["logic-state"]),
    "adversarial-audit": ("skill", "neonwatty/qa-skills (только пассивно)", ["logic-state"]),
    "agent:mobile-ux-auditor": ("agent", "neonwatty/qa-skills", ["responsive-cross-browser"]),
    "agent:qa-tester": ("agent", "browser-devtools", ["functional"]),
    "agent:accessibility-auditor": ("agent", "browser-devtools", ["accessibility"]),
    "agent:performance-analyzer": ("agent", "browser-devtools", ["performance"]),
    "agent:design-qa": ("agent", "browser-devtools", ["visual-ui"]),
}
# Никогда не используются (активные атаки / нагрузка) — см. references/plugins-map.md.
BANNED = {
    "agent:adversarial-breaker": "активные атаки (XSS/SQLi/удаления)",
    "agent:security-auditor": "смешивает пассивные и активные проверки без контроля",
    "perf-test": "k6 — нагрузочное тестирование",
    "security-scan": "сканер уязвимостей",
    "run-qa": "сам запускает агентов без правил скила",
    "submit-learnings": "публикует issue в репозиторий плагина",
}



def find_chrome_native_host():
    """Мост Claude Code ↔ расширение Claude in Chrome (native messaging host).

    Читаем конкретную папку через os.listdir: на macOS папка профиля Chrome защищена (TCC),
    и Path.glob, обходящий родительские каталоги, молча возвращает пустой список.
    """
    home = Path.home()
    dirs = [home / "Library/Application Support/Google/Chrome/NativeMessagingHosts",
            home / ".config/google-chrome/NativeMessagingHosts",
            home / ".config/chromium/NativeMessagingHosts"]
    for d in dirs:
        try:
            if any(f.startswith("com.anthropic") for f in os.listdir(d)):
                return True
        except OSError:
            continue
    if sys.platform == "win32":  # на Windows host регистрируется в реестре
        code, _ = ec.run(["reg", "query",
                          r"HKCU\Software\Google\Chrome\NativeMessagingHosts\com.anthropic.claude_code_browser_extension"])
        return code == 0
    return False


BROWSER_TOOL_GROUPS = [  # (key, title, regex over tool names)
    ("playwright_mcp", "Playwright MCP", re.compile(r"playwright.*__browser_", re.I)),
    ("claude_in_chrome", "Claude in Chrome", re.compile(r"^mcp__claude-in-chrome__", re.I)),
    ("chrome_devtools_mcp", "Chrome DevTools MCP", re.compile(r"chrome-devtools|chrome_devtools", re.I)),
]
KEY_TOOLS = {"playwright_mcp": ["browser_navigate", "browser_snapshot", "browser_take_screenshot",
                                "browser_run_code_unsafe", "browser_evaluate", "browser_network_requests"],
             "claude_in_chrome": ["tabs_context_mcp", "navigate", "read_page", "computer", "javascript_tool"]}


def parse_session_tools(a):
    names = []
    if a.session_tools:
        names += re.split(r"[\s,]+", a.session_tools)
    if a.session_tools_file:
        names += re.split(r"[\s,]+", Path(a.session_tools_file).read_text(encoding="utf-8"))
    return [x for x in names if x] if (a.session_tools or a.session_tools_file) else None


def probe_cdp(ports):
    """Browsers listening on a local remote-debugging port (connect via CDP)."""
    import urllib.request
    found = {}
    for port in ports:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.7) as r:
                info = json.loads(r.read().decode("utf-8", "replace"))
                found[str(port)] = info.get("Browser") or "?"
        except Exception:  # noqa: BLE001 — closed port, timeout, not a browser
            continue
    return found


def browser_tools(session, mcp_configured, chrome_host, cdp):
    """Rows and JSON about which browser tools are usable in the current session."""
    rows, res = [], {"session_tools_known": session is not None, "groups": {}}
    for key, title, rx in BROWSER_TOOL_GROUPS:
        have = sorted(n for n in session or [] if rx.search(n))
        short = [re.sub(r"^.*__", "", n) for n in have]
        configured = {"playwright_mcp": mcp_configured, "claude_in_chrome": chrome_host}.get(key)
        res["groups"][key] = {"in_session": bool(have) if session is not None else None, "tools": short,
                              "configured": configured}
        if session is None:
            status = ec.WARN
            note = ("настроен; " if configured else "не настроен; " if configured is False else "") + \
                "есть ли в этой сессии — неизвестно (передайте --session-tools)"
        elif have:
            missing = [k for k in KEY_TOOLS.get(key, []) if k not in short]
            status = ec.OK
            note = f"в сессии: {len(have)} инструментов ({', '.join(short[:6])}{'…' if len(short) > 6 else ''})"
            if missing:
                note += "; нет: " + ", ".join(missing)
                if "browser_run_code_unsafe" in missing:
                    note += " (nav_lock.js и snap_mcp.js не запустить)"
        else:
            status = ec.WARN
            note = "в этой сессии нет" + (" (настроен — нужен перезапуск/включение)" if configured else "")
        if key == "chrome_devtools_mcp" and not have:
            continue
        rows.append(ec.Row(f"{title} (сессия)", "", status, note))
    cli = shutil.which("playwright-cli")
    rows.append(ec.Row("playwright-cli (сессия)", "", ec.OK if cli else ec.WARN,
                       "доступен: параллельные потоки -s=qa-<id>" if cli else "нет — один браузерный поток"))
    res["playwright_cli"] = bool(cli)
    rows.append(ec.Row("CDP на localhost", ",".join(cdp) if cdp else "", ec.OK if cdp else ec.WARN,
                       "; ".join(f"порт {p}: {b}" for p, b in cdp.items()) if cdp
                       else "нет браузера с --remote-debugging-port (режим auth: manual-cdp недоступен)"))
    res["cdp"] = cdp
    usable = [t for k, t, _ in BROWSER_TOOL_GROUPS if res["groups"][k]["in_session"]]
    usable += ["playwright-cli"] if cli else []
    usable += [f"CDP :{p}" for p in cdp]
    res["usable_now"] = usable
    return rows, res


def usable_line(bres, session):
    if session is None:
        rest = [x for x in bres["usable_now"]]
        return ("Доступно в этой сессии: MCP-инструменты — неизвестно (нужен --session-tools)"
                + (f"; вне MCP: {', '.join(rest)}" if rest else ""))
    return "Доступно в этой сессии: " + (", ".join(bres["usable_now"]) or "ничего")


def check_node_deps(rows):
    pkg = NODE_DIR / "node_modules"
    if not pkg.exists():
        rows.append(ec.Row("node deps (scripts/node)", "", ec.FAIL, "не установлены", f"cd {NODE_DIR} && npm install"))
        return False
    ok = True
    for dep in ("playwright", "@axe-core/playwright", "lighthouse"):
        pj = pkg / dep / "package.json"
        if pj.exists():
            rows.append(ec.Row(dep, json.loads(pj.read_text(encoding="utf-8"))["version"], ec.OK, "локально в scripts/node"))
        else:
            ok = False
            rows.append(ec.Row(dep, "", ec.FAIL, "нет в scripts/node", f"cd {NODE_DIR} && npm install"))
    return ok


def probe_browsers(rows):
    """Реально запускает каждый браузер (node/probe.js): наличие файлов в кэше не гарантирует запуск."""
    code, out = ec.run(["node", "probe.js", "chromium", "firefox", "webkit"], timeout=150, cwd=str(NODE_DIR))
    try:
        browsers = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        rows.append(ec.Row("браузеры Playwright", "", ec.FAIL, out.strip()[:120], f"cd {NODE_DIR} && npx playwright install"))
        return {}
    for name, r in browsers.items():
        if r["ok"]:
            rows.append(ec.Row(f"браузер {name}", r["version"], ec.OK))
        else:
            rows.append(ec.Row(f"браузер {name}", "", ec.FAIL if name == "chromium" else ec.WARN,
                               "не запускается: " + r["error"], f"cd {NODE_DIR} && npx playwright install {name}"))
    return {k: v["ok"] for k, v in browsers.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--no-browsers", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--session-tools")
    ap.add_argument("--session-tools-file")
    ap.add_argument("--browser-tools-only", action="store_true")
    ap.add_argument("--cdp-ports", default="9222")
    a = ap.parse_args()
    session = parse_session_tools(a)
    cdp = probe_cdp([p for p in a.cdp_ports.split(",") if p.strip()])

    if a.browser_tools_only:
        brows, bres = browser_tools(session, None, find_chrome_native_host(), cdp)
        print("## Браузерные инструменты\n")
        ec.print_table(brows)
        print("\n" + usable_line(bres, session))
        if a.json:
            Path(a.json).parent.mkdir(parents=True, exist_ok=True)
            Path(a.json).write_text(json.dumps({"browser_tools": bres}, ensure_ascii=False, indent=2), encoding="utf-8")
        sys.exit(0 if bres["usable_now"] or session is None else 1)

    rows = [ec.Row("ОС", ec.os_name())]
    if SKILL["skill_dir"]:
        note = f"источник: {SKILL['source']}, версия {SKILL['version'] or '?'}; проверено: папка есть"
        if SKILL["warnings"]:
            note += "; " + "; ".join(SKILL["warnings"])
        rows.append(ec.Row("SKILL_DIR", SKILL["skill_dir"], ec.WARN if SKILL["source"] == "dev-checkout" or
                           (os.environ.get(sd.ENV) and SKILL["source"] != "env") else ec.OK, note,
                           f'для постоянного пути: ~/.claude/settings.json → "env": {{"{sd.ENV}": "<путь>"}}'))
    else:
        rows.append(ec.Row("SKILL_DIR", "", ec.FAIL, "установленный site-qa-audit не найден", "INSTALL.md (маркетплейс) "
                           f"или {sd.ENV}"))
    rows.append(ec.tool_version("git", fix="https://git-scm.com"))
    rows.append(ec.tool_version("node", min_version=(18, 0, 0), fix="https://nodejs.org (LTS)"))
    rows.append(ec.tool_version("npm"))
    rows.append(ec.tool_version("npx"))
    py = "python3" if shutil.which("python3") else "python"
    rows.append(ec.tool_version(py, min_version=(3, 8, 0)))
    rows.append(ec.tool_version("gh", fix="https://cli.github.com"))
    rows.append(ec.gh_status())
    rows.append(ec.tool_version("claude"))
    rows.append(ec.tool_version("playwright-cli", fix="npm install -g @playwright/cli@latest  (нужен для параллельных браузерных потоков)"))
    if rows[-1]["status"] == ec.FAIL:
        rows[-1]["status"] = ec.WARN
    check_node_deps(rows)
    browsers = {} if a.no_browsers else probe_browsers(rows)

    plugins = ec.claude_plugins()
    mcp_ok = any(p.get("enabled") and "playwright" in (p.get("mcpServers") or {}) for p in plugins)
    if not a.fast:
        servers = ec.claude_mcp_servers()
        mcp_ok = any("playwright" in k.lower() and v["ok"] for k, v in servers.items()) or mcp_ok
    rows.append(ec.Row("Playwright MCP", "", ec.OK if mcp_ok else ec.FAIL, "" if mcp_ok else "не подключён",
                       "/plugin install playwright@claude-plugins-official  или  claude mcp add --transport stdio "
                       "--scope user playwright -- npx -y @playwright/mcp@latest"))
    out_root = os.environ.get("SITE_QA_OUTPUT_DIR")
    if out_root:
        p = Path(out_root).expanduser()
        rows.append(ec.Row("SITE_QA_OUTPUT_DIR", str(p), ec.OK if p.is_dir() else ec.WARN,
                           "папка результатов по умолчанию" + ("" if p.is_dir() else " — папки нет, будет создана"), ""))
    else:
        rows.append(ec.Row("SITE_QA_OUTPUT_DIR", "", ec.WARN, "не задана — результаты в <папка запуска Claude Code>/qa-runs/",
                           'добавить в ~/.claude/settings.json → "env": {"SITE_QA_OUTPUT_DIR": "<путь>"}'))
    chrome_host = find_chrome_native_host()
    rows.append(ec.Row("Claude in Chrome", "", ec.OK if chrome_host else ec.WARN,
                       "native host есть; инструменты mcp__claude-in-chrome__* появляются в сессии, запущенной с "
                       "включённым Chrome (claude --chrome или /chrome)" if chrome_host
                       else "нет native host — режим current-screen только через Playwright",
                       "расширение Claude (Anthropic) в Chrome + запуск `claude --chrome` или /chrome"))

    available = {}
    skills = set(ec.user_skills())
    pskills = ec.plugin_skills(plugins)
    for name, (kind, origin, dirs) in ENHANCERS.items():
        src = "~/.claude/skills" if name in skills else pskills.get(name)
        if src:
            available[name] = {"kind": kind, "source": src, "origin": origin, "directions": dirs}
    disabled = [p["id"] for p in plugins if not p.get("enabled")]
    rows.append(ec.Row("плагины-усилители", str(len(available)), ec.OK if available else ec.WARN,
                       ", ".join(sorted(available)) or "нет — работа по собственным чек-листам",
                       "см. references/plugins-map.md"))
    if disabled:
        rows.append(ec.Row("отключённые плагины", str(len(disabled)), ec.OK, ", ".join(disabled)))

    brows, bres = browser_tools(session, mcp_ok, bool(chrome_host), cdp)
    print(f"## Окружение site-qa-audit\n")
    print(f"SKILL_DIR: {SKILL['skill_dir'] or 'не найден'}" + (f"  ({SKILL['source']}, {SKILL['version']})" if SKILL["skill_dir"] else "")
          + "\nЭтот путь подставляется в блок правил §4 и задания исполнителей; перед работой исполнитель проверяет "
          "его: python3 <SKILL_DIR>/scripts/skill_dir.py --check <SKILL_DIR>\n")
    ec.print_table(rows)
    print("\n## Браузерные инструменты\n")
    ec.print_table(brows)
    print("\n" + usable_line(bres, session))
    required = {"SKILL_DIR", "git", "node", "npm", "npx", py, "gh", "gh auth", "Playwright MCP", "браузер chromium",
                "playwright", "@axe-core/playwright", "lighthouse"}
    fails = [r for r in rows if r["status"] == ec.FAIL and r["component"] in required]
    print(f"\nИтог: {'можно работать' if not fails else 'нужно исправить: ' + ', '.join(r['component'] for r in fails)}")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps({"skill_dir": SKILL["skill_dir"], "skill_dir_source": SKILL["source"],
                                            "skill_version": SKILL["version"],
                                            "rows": rows, "browsers": browsers, "playwright_mcp": mcp_ok,
                                            "playwright_cli": bool(shutil.which("playwright-cli")),
                                            "claude_in_chrome": bool(chrome_host), "output_dir": out_root, "enhancers": available,
                                            "banned": BANNED, "disabled_plugins": disabled, "browser_tools": bres},
                                           ensure_ascii=False, indent=2), encoding="utf-8")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
