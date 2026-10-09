#!/usr/bin/env python3
"""Browser window of the run: visible (headed) or hidden, and slow-mo — one place for the whole run.

  browser_mode.py show <RUN_DIR> [--cli | --json]
      effective mode: run-config.yaml → browser.headed/slowmo, else SITE_QA_HEADLESS/SITE_QA_SLOWMO, else visible;
      refreshes <RUN_DIR>/playwright-cli.json. --cli: only the options for `playwright-cli -s=<qa-id> open <URL> …`
  browser_mode.py set <RUN_DIR> (--headed | --headless | --default) [--slowmo MS]
      write run-config.yaml → browser, re-export rules.json and <RUN_DIR>/playwright-cli.json: every NEXT start of a
      node script of the skill (they read rules.json) and every next
      `playwright-cli -s=<qa-id> open <URL> --config <RUN_DIR>/playwright-cli.json` use the new mode; no message to the
      executors is needed. Open playwright-cli sessions keep their window until reopened; Playwright MCP is
      configured when it starts (--headless) and does not switch.

<RUN_DIR>/playwright-cli.json (playwright-cli --config): browser.launchOptions {headless, slowMo} of the run and, for a
local app (site.local_roots), allowUnrestrictedFileAccess: true — playwright-cli blocks file:// without it; the guard
(url_guard.py nav before every goto) stays the boundary.

Order for node scripts (scripts/node/lib.js → browserMode): --headed/--headless of the command > run-config >
environment > visible window (slow-mo 250 ms). references/devices-auth.md → «Окно браузера».
"""
import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import runcfg  # noqa: E402
import url_guard  # noqa: E402


CLI_CONFIG = "playwright-cli.json"


def write_cli_config(run_dir, res=None):
    """<RUN_DIR>/playwright-cli.json for `playwright-cli open --config`: window of the run, file:// for local apps."""
    run_dir = Path(run_dir)
    res = res or effective(run_dir)
    cfg = runcfg.load(run_dir / "run-config.yaml")
    try:
        local = bool(url_guard.local_roots_of(cfg))
    except url_guard.GuardUnavailable:
        local = False
    lo = {"headless": not res["headed"]}
    if res["headed"] and res["slowmo"]:
        lo["slowMo"] = res["slowmo"]
    data = {"browser": {"launchOptions": lo}}
    if local:
        data["allowUnrestrictedFileAccess"] = True
    path = run_dir / CLI_CONFIG
    if run_dir.is_dir():
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def effective(run_dir):
    cfg = runcfg.load(Path(run_dir) / "run-config.yaml")
    b = url_guard.browser_of(cfg)
    env_h = os.environ.get("SITE_QA_HEADLESS")
    if b["headed"] is not None:
        headed, source = b["headed"], "run-config"
    elif env_h not in (None, ""):
        headed, source = env_h != "1", "env SITE_QA_HEADLESS"
    else:
        headed, source = True, "по умолчанию"
    slowmo = b["slowmo"] if b["slowmo"] is not None else int(os.environ.get("SITE_QA_SLOWMO") or 250)
    return {"headed": headed, "slowmo": slowmo if headed else 0, "source": source, "config": b,
            "playwright_cli": f"--config {Path(run_dir) / CLI_CONFIG}" + (" --headed" if headed else ""),
            "env": f"SITE_QA_HEADLESS={'0' if headed else '1'}" + (f" SITE_QA_SLOWMO={slowmo}" if headed else "")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show", help="текущий режим окна прогона")
    s.add_argument("run_dir")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--cli", action="store_true", help="только флаг для playwright-cli open")
    g.add_argument("--json", action="store_true")
    w = sub.add_parser("set", help="изменить режим окна (run-config.yaml и rules.json)")
    w.add_argument("run_dir")
    m = w.add_mutually_exclusive_group(required=True)
    m.add_argument("--headed", action="store_true", help="окно видно")
    m.add_argument("--headless", action="store_true", help="без окна")
    m.add_argument("--default", action="store_true", help="снять настройку: env или видимое окно")
    w.add_argument("--slowmo", type=int, help="замедление действий в видимом окне, мс")
    a = ap.parse_args()
    if a.cmd == "set":
        cfg_path = Path(a.run_dir) / "run-config.yaml"
        old = (runcfg.load(cfg_path).get("browser") or {})
        new = {"headed": True if a.headed else False if a.headless else None,
               "slowmo": a.slowmo if a.slowmo is not None else (old.get("slowmo") if isinstance(old, dict) else None)}
        runcfg.set_top(cfg_path, "browser", new)
        rex = runcfg.reexport_rules(a.run_dir)
        res = effective(a.run_dir)
        write_cli_config(a.run_dir, res)
        print(f"окно браузера: {'видно' if res['headed'] else 'скрыто'}" +
              (f", замедление {res['slowmo']} мс" if res["headed"] else "") + f" (источник: {res['source']})")
        print("  rules.json пересобран — node-скрипты возьмут режим при следующем запуске" if rex and rex["code"] == 0
              else "  rules.json нет — режим попадёт в него при url_guard.py export")
        print(f"  playwright-cli: open <URL> {res['playwright_cli']}; открытые сессии — после переоткрытия своей сессии")
        if rex and rex["code"] != 0:
            print(f"  ОШИБКА export: {rex['output']}", file=sys.stderr)
            sys.exit(4)
        return
    res = effective(a.run_dir)
    write_cli_config(a.run_dir, res)
    if a.cli:
        print(res["playwright_cli"])
    elif a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print(f"окно браузера: {'видно' if res['headed'] else 'скрыто'}" +
              (f", замедление {res['slowmo']} мс" if res["headed"] else "") + f" (источник: {res['source']}); "
              f"playwright-cli: open <URL> {res['playwright_cli']}; node-скрипты: из rules.json")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
