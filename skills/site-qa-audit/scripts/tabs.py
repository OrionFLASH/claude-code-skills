#!/usr/bin/env python3
"""Tab registry of a run (S-6, S-7): <RUN_DIR>/tabs.json — who opened which tab, one tab per device profile.

  tabs.py open    <RUN_DIR> --owner qa-ux --profile pixel7 [--tool mcp|cli|cdp] [--session qa-ux] [--url URL]
                  [--target-id <CDP target id>] [--window-name qa-ux-pixel7]
                  register a tab BEFORE opening it; if this owner already has an open tab for this profile — exit 3
                  and its record: reuse it, do not open another one
  tabs.py close   <RUN_DIR> (--id T-003 | --owner qa-ux [--profile pixel7])        mark as closed (after closing it)
  tabs.py list    <RUN_DIR> [--open] [--json]
  tabs.py audit   <RUN_DIR> --cdp http://127.0.0.1:9222 [--domains example.com,*.example.com]
                  read-only: tabs of the user's browser (CDP /json/list): duplicates of one URL, tabs of the site that are
                  not in the registry; nothing is closed
  tabs.py cleanup <RUN_DIR> [--owner qa-ux] [--cdp URL] [--yes]
                  before finishing a step and the run: plan of what to close (default) / close (--yes): CDP tabs from the
                  registry are closed by their target id; CLI sessions and MCP tabs get the exact command to run;
                  tabs of node scripts (tool node) are marked closed when their process has ended (a running script is
                  never touched — it closes its own browser).
                  Only tabs from the registry are touched — never the user's own tabs.

Node scripts of the skill (scripts/node/lib.js → tabs()) write the same file with the same lock: tool «node» — a page
of the script's own browser (pid, script), tool «cdp» — a page the script created in the user's browser (target id).
They are registered without the «one tab per profile» check: such a tab cannot be reused by an executor.

Rules (references/parallelism.md): never `playwright-cli close-all` / `kill-all` and never close other sessions; close
only your named session (`playwright-cli -s=<qa-id> close`). Exit codes: 0 ok, 1 bad input, 3 tab already open.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import urlsplit


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Lock:
    """Cross-platform lock file next to tabs.json (several executors register tabs at the same time)."""

    def __init__(self, path, timeout=10.0):
        self.path, self.timeout, self.fd = str(path) + ".lock", timeout, None

    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > 60:  # stale lock of a crashed process
                        os.remove(self.path)
                        continue
                except OSError:
                    pass
                if time.time() > deadline:
                    raise SystemExit(f"tabs: файл занят ({self.path}) — повторите")
                time.sleep(0.05)

    def __exit__(self, *exc):
        os.close(self.fd)
        try:
            os.remove(self.path)
        except OSError:
            pass


def reg_path(run_dir):
    return Path(run_dir) / "tabs.json"


def load(run_dir):
    p = reg_path(run_dir)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"tabs": []}


def save(run_dir, data):
    p = reg_path(run_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def open_tabs(data, owner=None, profile=None):
    return [t for t in data["tabs"] if not t.get("closed_at") and (not owner or t["owner"] == owner)
            and (not profile or t["profile"] == profile)]


def pid_alive(pid):
    """Is the process still running? Never sends a signal (os.kill(pid, 0) on Windows would send CTRL_C_EVENT)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def close_command(t):
    if t.get("tool") == "cli":
        return f"playwright-cli -s={t.get('session') or t['owner']} close"
    if t.get("tool") == "mcp":
        return "Playwright MCP: browser_tabs action=close (вкладка " + (t.get("url") or t["id"]) + ")"
    if t.get("tool") == "cdp":
        return f"tabs.py cleanup <RUN_DIR> --cdp <URL> --yes (target {t.get('target_id') or '?'})"
    if t.get("tool") == "node":
        return f"дождаться завершения {t.get('script') or 'node-скрипта'} (pid {t.get('pid')}): он закрывает свой браузер сам"
    return "закрыть вручную"


def cdp_get(cdp, path):
    with urllib.request.urlopen(cdp.rstrip("/") + path, timeout=5) as r:
        body = r.read().decode("utf-8", "replace")
    try:
        return json.loads(body)
    except ValueError:
        return body


def host_ok(url, domains):
    h = (urlsplit(url).hostname or "").lower()
    for p in domains:
        p = p.lower()
        if (p.startswith("*.") and (h == p[2:] or h.endswith(p[1:]))) or fnmatch(h, p):
            return True
    return False


def cmd_open(a):
    with Lock(reg_path(a.run_dir)):
        data = load(a.run_dir)
        # tabs of node scripts live in the script's own browser (or are closed by it): never «reuse this one», and a node
        # record itself is never refused (like scripts/node/lib.js, which writes them without this check)
        same = [] if a.tool == "node" else [t for t in open_tabs(data, a.owner, a.profile) if t.get("tool") != "node"]
        if same:
            print(json.dumps({"exists": True, "tab": same[0], "hint": "одна вкладка на профиль устройства: используйте эту"},
                             ensure_ascii=False))
            return 3
        tid = f"T-{len(data['tabs']) + 1:03d}"
        tab = {"id": tid, "owner": a.owner, "profile": a.profile, "tool": a.tool, "session": a.session or a.owner,
               "url": a.url, "target_id": a.target_id, "window_name": a.window_name or f"{a.owner}-{a.profile}",
               "opened_at": now(), "closed_at": None}
        data["tabs"].append(tab)
        save(a.run_dir, data)
    print(json.dumps(tab, ensure_ascii=False))
    return 0


def cmd_close(a):
    if not a.id and not a.owner:
        print("tabs close: нужен --id или --owner")
        return 1
    with Lock(reg_path(a.run_dir)):
        data = load(a.run_dir)
        hit = [t for t in open_tabs(data, a.owner, a.profile) if not a.id or t["id"] == a.id]
        for t in hit:
            t["closed_at"] = now()
        save(a.run_dir, data)
    print(json.dumps({"closed": [t["id"] for t in hit]}, ensure_ascii=False))
    return 0


def cmd_list(a):
    data = load(a.run_dir)
    rows = open_tabs(data) if a.open else data["tabs"]
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    for t in rows:
        who = f" {t.get('script')}:{t.get('pid')}" if t.get("tool") == "node" else ""
        print(f"{t['id']} {t['owner']} {t['profile']} {t.get('tool')}{who} "
              f"{'открыта' if not t.get('closed_at') else 'закрыта'} {t.get('url') or ''}")
    print(f"tabs: всего {len(data['tabs'])}, открыто {len(open_tabs(data))}")
    return 0


def browser_pages(cdp):
    try:
        pages = cdp_get(cdp, "/json/list")
    except OSError as ex:
        raise SystemExit(f"tabs: нет ответа CDP {cdp}: {ex}")
    return [p for p in pages if isinstance(p, dict) and p.get("type") == "page"]


def cmd_audit(a):
    pages = browser_pages(a.cdp)
    domains = [d.strip() for d in (a.domains or "").split(",") if d.strip()]
    data = load(a.run_dir)
    registered = {t.get("target_id") for t in open_tabs(data) if t.get("target_id")}
    by_url = {}
    for p in pages:
        by_url.setdefault(p.get("url"), []).append(p)
    site = [p for p in pages if not domains or host_ok(p.get("url") or "", domains)]
    res = {"pages": len(pages), "site_pages": len(site),
           "duplicates": [{"url": u, "count": len(ps)} for u, ps in by_url.items() if len(ps) > 1],
           "unregistered_site_tabs": [p.get("url") for p in site if p.get("id") not in registered],
           "registered_open": len(registered)}
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


def cmd_cleanup(a):
    with Lock(reg_path(a.run_dir)):
        data = load(a.run_dir)
        todo = open_tabs(data, a.owner)
        plan = []
        alive = None
        if a.cdp and any(t.get("tool") == "cdp" for t in todo):
            alive = {p.get("id") for p in browser_pages(a.cdp)}
        for t in todo:
            step = {"id": t["id"], "owner": t["owner"], "profile": t["profile"], "tool": t.get("tool")}
            if t.get("tool") == "node":
                if pid_alive(t.get("pid")):
                    step["action"] = ("скрипт ещё работает (pid " + str(t.get("pid")) + "): дождаться завершения, "
                                      "он закрывает свой браузер сам; если pid занят другим процессом — tabs.py close "
                                      f"<RUN_DIR> --id {t['id']}")
                else:
                    step["action"] = "уже закрыта (процесс завершён)"
                    if a.yes:
                        t["closed_at"] = now()
            elif t.get("tool") == "cdp" and t.get("target_id") and a.cdp:
                if t["target_id"] not in (alive or set()):
                    step["action"] = "уже закрыта"
                    if a.yes:
                        t["closed_at"] = now()
                elif a.yes:
                    cdp_get(a.cdp, f"/json/close/{t['target_id']}")
                    t["closed_at"] = now()
                    step["action"] = "закрыта по CDP"
                else:
                    step["action"] = f"закрыть по CDP (target {t['target_id']})"
            else:
                step["action"] = "выполнить: " + close_command(t) + f", затем tabs.py close <RUN_DIR> --id {t['id']}"
            plan.append(step)
        if a.yes:
            save(a.run_dir, data)
    print(json.dumps({"plan" if not a.yes else "done": plan, "open_left": len(open_tabs(data, a.owner))},
                     ensure_ascii=False, indent=1))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["open", "close", "list", "audit", "cleanup"])
    ap.add_argument("run_dir")
    ap.add_argument("--owner")
    ap.add_argument("--profile")
    ap.add_argument("--tool", choices=["mcp", "cli", "cdp", "node"], default="cli")
    ap.add_argument("--session")
    ap.add_argument("--url")
    ap.add_argument("--target-id")
    ap.add_argument("--window-name")
    ap.add_argument("--id")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--cdp")
    ap.add_argument("--domains")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    if a.cmd == "open":
        if not (a.owner and a.profile):
            ap.error("open: нужны --owner и --profile")
        return cmd_open(a)
    if a.cmd == "audit" and not a.cdp:
        ap.error("audit: нужен --cdp")
    return {"close": cmd_close, "list": cmd_list, "audit": cmd_audit, "cleanup": cmd_cleanup}[a.cmd](a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
