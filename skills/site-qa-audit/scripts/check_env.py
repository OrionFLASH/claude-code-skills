#!/usr/bin/env python3
"""Проверка окружения site-qa-audit при каждом запуске (references/setup.md).

  check_env.py [--fast] [--json out.json] [--no-browsers]
    --fast         не опрашивать `claude mcp list` (медленно) — Playwright MCP проверяется по списку плагинов
    --no-browsers  не запускать браузеры для проверки
    --json FILE    сохранить результат (таблица + доступные плагины/скилы/браузеры) для прогона

Печатает таблицу «компонент / версия / статус / примечание / как исправить».
Код выхода: 0 — можно работать, 1 — есть FAIL в обязательных компонентах.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
import envcheck as ec  # noqa: E402

NODE_DIR = HERE / "node"

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
    a = ap.parse_args()

    rows = [ec.Row("ОС", ec.os_name())]
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
    chrome_host = list(Path.home().glob("Library/Application Support/Google/Chrome/NativeMessagingHosts/com.anthropic*")) + \
        list(Path.home().glob(".config/google-chrome/NativeMessagingHosts/com.anthropic*"))
    rows.append(ec.Row("Claude in Chrome", "", ec.OK if chrome_host else ec.WARN,
                       "" if chrome_host else "нет native host — режим current-screen только через Playwright",
                       "расширение Claude in Chrome + /chrome"))

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

    print(f"## Окружение site-qa-audit\n")
    ec.print_table(rows)
    required = {"git", "node", "npm", "npx", py, "gh", "gh auth", "Playwright MCP", "браузер chromium",
                "playwright", "@axe-core/playwright", "lighthouse"}
    fails = [r for r in rows if r["status"] == ec.FAIL and r["component"] in required]
    print(f"\nИтог: {'можно работать' if not fails else 'нужно исправить: ' + ', '.join(r['component'] for r in fails)}")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps({"rows": rows, "browsers": browsers, "playwright_mcp": mcp_ok,
                                            "playwright_cli": bool(shutil.which("playwright-cli")),
                                            "claude_in_chrome": bool(chrome_host), "enhancers": available,
                                            "banned": BANNED, "disabled_plugins": disabled},
                                           ensure_ascii=False, indent=2), encoding="utf-8")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
