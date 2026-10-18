#!/usr/bin/env python3
"""Полный каталог того, что установлено в Claude Code на этой машине → data/catalog.json.

Только чтение (~/.claude, ~/.claude.json); значения env, аргументы и токены серверов не читаются и не пишутся,
домашний каталог заменяется на «~». Русские пояснения берутся из data/setup.json (ручной разбор), если есть.
Запуск: python3 -I build_catalog.py   (stdlib)
"""
import json
import os
import re
import sys
from pathlib import Path

HOME = Path.home()
CL = HOME / ".claude"
HERE = Path(__file__).resolve().parent
TODAY = "2026-10-18"


# статусы MCP по уведомлению сессии 2026-10-18 (подключение не повторялось отдельно)
SESSION_NEEDS_AUTH = {"plugin:data:hex", "plugin:marketing:ahrefs", "plugin:marketing:amplitude", "plugin:marketing:amplitude-eu", "plugin:marketing:canva", "plugin:marketing:hubspot", "plugin:marketing:klaviyo",
                      "plugin:marketing:similarweb", "plugin:marketing:slack", "plugin:marketing:supermetrics", "plugin:product-management:asana", "plugin:product-management:atlassian", "plugin:product-management:clickup",
                      "plugin:product-management:fireflies", "plugin:product-management:intercom", "plugin:product-management:linear", "plugin:product-management:monday", "plugin:product-management:pendo", "plugin:product-management:similarweb"}
SESSION_FAILED = {"plugin:data:definite", "plugin:telegram:telegram", "TestSprite"}
# подключения, которых нет в файлах ~/.claude: видны только в сессии (коннекторы claude.ai, расширения Chrome и VS Code)
SESSION_MCP = [
    {"name": "Claude Docs", "origin": "коннектор claude.ai", "type": "http", "target": "claude.ai (документы Claude)", "plugin": None, "status": "connected", "ru": "Создание и правка документов в claude.ai (create/read/update/batch/export). Вызывается, только если попросить сделать документ."},
    {"name": "claude-in-chrome", "origin": "расширение Chrome", "type": "stdio", "target": "расширение Claude in Chrome", "plugin": None, "status": "connected", "ru": "Управление вашим браузером Chrome: вкладки, клики, чтение страниц, скриншоты, запись GIF."},
    {"name": "claude-vscode", "origin": "расширение VS Code", "type": "stdio", "target": "расширение Claude Code для VS Code", "plugin": None, "status": "connected", "ru": "Диагностика кода из редактора (getDiagnostics)."},
]


def tilde(s):
    return str(s).replace(str(HOME), "~")


def read(p, n=None):
    try:
        t = Path(p).read_text(encoding="utf-8", errors="replace")
        return t if n is None else t[:n]
    except OSError:
        return ""


def jload(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return d


def frontmatter(text):
    """Мини-разбор YAML-шапки: key: value, блоки > и |, кавычки. Возвращает (dict, тело)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    fm, body, cur, buf, mode = {}, m.group(2), None, [], None

    def flush():
        if cur is not None:
            v = (" " if mode == ">" else "\n").join(x.strip() for x in buf).strip() if mode else " ".join(x.strip() for x in buf).strip()
            fm[cur] = v.strip("\"'")
    for line in m.group(1).split("\n"):
        k = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if k and not line.startswith((" ", "\t")):
            flush()
            cur, v = k.group(1), k.group(2).strip()
            if v in (">", "|", ">-", "|-"):
                mode, buf = v[0], []
            else:
                mode, buf = None, [v]
        elif cur is not None:
            buf.append(line)
    flush()
    return fm, body


def summary_of(body, n=420):
    lines = [x.strip() for x in body.split("\n")]
    out, head = [], ""
    for x in lines:
        if not x or x.startswith(("```", "|", "---", ">", "<!--")):
            continue
        if x.startswith("#"):
            head = head or x.lstrip("# ").strip()
            continue
        out.append(re.sub(r"[*_`]", "", x))
        if sum(len(y) for y in out) > n:
            break
    return head, " ".join(out)[:n]


def skill_entry(path, source, plugin=None, root=None):
    t = read(path)
    fm, body = frontmatter(t)
    head, summ = summary_of(body)
    name = fm.get("name") or Path(path).parent.name
    desc = fm.get("description", "")
    when = fm.get("when_to_use", "")
    manual = str(fm.get("disable-model-invocation", "")).lower() == "true"
    uinv = str(fm.get("user-invocable", "")).lower() != "false"
    slash = "/" + (plugin + ":" if plugin else "") + name
    d = Path(path).parent
    return {
        "kind": "skill", "name": name, "source": source, "plugin": plugin,
        "description": (desc + (" " + when if when else "")).strip(),
        "launch": ("только вручную: " + slash if manual else "сам по описанию (модель решает, что скил подходит) или вручную: " + slash if uinv else "только модель, по описанию"),
        "auto": not manual, "slash": slash if uinv else "",
        "heading": head, "what": summ, "argument_hint": fm.get("argument-hint", ""), "allowed_tools": fm.get("allowed-tools", ""), "model": fm.get("model", ""),
        "lines": t.count("\n") + 1, "has_scripts": (d / "scripts").is_dir(),
        "file": tilde(Path(path)).split("/cache/")[-1] if "/cache/" in str(path) else tilde(path),
    }


def md_entry(path, kind, source, plugin):
    t = read(path)
    fm, body = frontmatter(t)
    head, summ = summary_of(body)
    name = fm.get("name") or Path(path).stem
    slash = "/" + (plugin + ":" if plugin else "") + name
    base = {"kind": kind, "name": name, "source": source, "plugin": plugin, "description": fm.get("description", ""), "heading": head, "what": summ,
            "argument_hint": fm.get("argument-hint", ""), "allowed_tools": fm.get("allowed-tools", "") or fm.get("tools", ""), "model": fm.get("model", ""), "lines": t.count("\n") + 1,
            "file": tilde(path).split("/cache/")[-1] if "/cache/" in str(path) else tilde(path)}
    if kind == "command":
        base.update(launch="только вручную: " + slash, auto=False, slash=slash)
    else:
        base.update(launch="вызывается моделью как субагент (Agent) по описанию или вручную через @-упоминание", auto=True, slash="")
    return base


def hooks_of(hjson, source, plugin):
    out = []
    hs = (hjson or {}).get("hooks", {}) if isinstance(hjson, dict) else {}
    for ev, arr in hs.items():
        for blk in arr or []:
            for h in blk.get("hooks", []):
                cmd = re.sub(r"\s+", " ", str(h.get("command", h.get("prompt", ""))))
                out.append({"event": ev, "matcher": blk.get("matcher", ""), "type": h.get("type", "command"), "command": tilde(cmd)[:260], "timeout": h.get("timeout"),
                            "source": source, "plugin": plugin, "note": (hjson or {}).get("description", "")})
    return out


def mcp_of(pdir, plugin):
    out = []
    j = jload(Path(pdir) / ".mcp.json", {}) or {}
    srv = j.get("mcpServers", j) if isinstance(j, dict) else {}
    for n, v in srv.items():
        if not isinstance(v, dict):
            continue
        url = v.get("url", "")
        out.append({"name": n, "plugin": plugin, "type": v.get("type", "stdio" if v.get("command") else "?"), "target": re.sub(r"[?#].*$", "", url) if url else (os.path.basename(str(v.get("command", ""))) + " " + " ".join(str(a) for a in v.get("args", [])[:1])).strip(), "origin": "плагин " + plugin})
    return out


def collect_plugin(pdir, source, plugin, status, extra=None):
    pdir = Path(pdir)
    pj = jload(pdir / ".claude-plugin" / "plugin.json", {}) or {}
    comps = []
    sk = pj.get("skills")
    paths = []
    if isinstance(sk, list):
        for s in sk:
            paths.append((pdir / s).resolve())
    elif isinstance(sk, str):
        paths.append((pdir / sk).resolve())
    else:
        paths.append(pdir / "skills")
    seen = set()
    for p in paths:
        if (p / "SKILL.md").is_file():
            cands = [p / "SKILL.md"]
        elif p.is_dir():
            cands = sorted(p.glob("*/SKILL.md"))
        else:
            cands = []
        for c in cands:
            if c in seen:
                continue
            seen.add(c)
            comps.append(skill_entry(c, source, plugin))
    cd = pj.get("commands")
    cdirs = [pdir / c for c in cd] if isinstance(cd, list) else [pdir / (cd if isinstance(cd, str) else "commands")]
    for d in cdirs:
        if d.is_file():
            comps.append(md_entry(d, "command", source, plugin))
        elif d.is_dir():
            for f in sorted(d.glob("*.md")):
                comps.append(md_entry(f, "command", source, plugin))
    ad = pdir / "agents"
    if ad.is_dir():
        for f in sorted(ad.glob("*.md")):
            comps.append(md_entry(f, "agent", source, plugin))
    hj = None
    hp = pj.get("hooks")
    if isinstance(hp, dict):
        hj = pj
    elif isinstance(hp, str):
        hj = jload(pdir / hp, None)
    elif (pdir / "hooks" / "hooks.json").is_file():
        hj = jload(pdir / "hooks" / "hooks.json", None)
    hooks = hooks_of(hj, source, plugin)
    mcp = mcp_of(pdir, plugin)
    if isinstance(pj.get("mcpServers"), dict):
        for n, v in pj["mcpServers"].items():
            mcp.append({"name": n, "plugin": plugin, "type": v.get("type", "stdio"), "target": re.sub(r"[?#].*$", "", v.get("url", "") or str(v.get("command", ""))), "origin": "плагин " + plugin})
    rec = {"id": plugin, "name": pj.get("name", plugin), "version": pj.get("version", ""), "description": pj.get("description", ""), "source": source, "status": status,
           "license": pj.get("license", ""), "author": (pj.get("author") or {}).get("name", "") if isinstance(pj.get("author"), dict) else str(pj.get("author", "")),
           "counts": {"skills": sum(c["kind"] == "skill" for c in comps), "commands": sum(c["kind"] == "command" for c in comps), "agents": sum(c["kind"] == "agent" for c in comps), "hooks": len(hooks), "mcp": len(mcp)},
           "components": comps, "hooks": hooks, "mcp": mcp, "path": tilde(pdir).split("/plugins/")[-1]}
    rec.update(extra or {})
    return rec


def main():
    setup = jload(HERE / "setup.json", {}) or {}
    ru_pl = {p["name"]: p.get("summary", "") for p in setup.get("plugins", [])}
    ru_sk = {s["name"]: s.get("summary", "") for s in setup.get("owner_skills_detail", [])}
    ru_mcp = {m["name"]: m for m in setup.get("mcp_servers", [])}
    inst = jload(CL / "plugins" / "installed_plugins.json", {}).get("plugins", {})
    settings = jload(CL / "settings.json", {})
    enabled = settings.get("enabledPlugins", {})
    mk_own = {"claude-code-skills": "own", "claude-plugins-official": "official", "knowledge-work-plugins": "official", "anthropic-plugin-directory": "official"}
    plugins = []
    for pid, vers in inst.items():
        name, mk = pid.split("@")
        v = vers[0]
        st = "active" if enabled.get(pid, False) else "disabled"
        cache = CL / "plugins" / "cache" / mk / name
        olds = sorted(x.name for x in cache.iterdir() if x.is_dir() and x.name != Path(v["installPath"]).name) if cache.is_dir() else []
        rec = collect_plugin(v["installPath"], mk_own.get(mk, "third-party"), name, st, {"marketplace": mk, "installed_version": v.get("version"), "installed_at": v.get("installedAt", ""), "scope": v.get("scope"), "old_versions": len(olds)})
        rec["ru"] = ru_pl.get(name, "")
        plugins.append(rec)
    # плагины, синхронизированные через claude.ai
    sroot = CL / "plugins" / "synced"
    for b in sroot.glob("*"):
        if not b.is_dir():
            continue
        for d in sorted(b.glob("*~g2")):
            pj = jload(d / ".claude-plugin" / "plugin.json", {}) or {}
            meta = jload(str(d) + ".meta.json", {}) or {}
            nm = pj.get("name") or d.name
            rec = collect_plugin(d, "synced", nm, "active", {"marketplace": meta.get("marketplace_name", "claude.ai"), "installed_version": pj.get("version", ""), "scope": "claude.ai-sync", "old_versions": 0, "install_pref": meta.get("installation_preference", "")})
            rec["ru"] = ru_pl.get(nm, "")
            plugins.append(rec)
    # личные скилы и команды
    user = []
    for f in sorted(list((CL / "skills").glob("*/SKILL.md")) + list((CL / "skills" / "synced").glob("*/*/SKILL.md")) + list((CL / "skills" / "synced").glob("*/SKILL.md"))):
        if ".trash" in str(f):
            continue
        e = skill_entry(f, "user")
        e["ru"] = ru_sk.get(e["name"], "")
        e["file"] = tilde(f.parent).replace("~/.claude/", "~/.claude/") + "/SKILL.md"
        e["symlink"] = f.parent.is_symlink()
        user.append(e)
    for f in sorted((CL / "commands").glob("*.md")):
        e = md_entry(f, "command", "user", None)
        e["ru"] = ru_sk.get(e["name"], "")
        user.append(e)
    stray = [tilde(p) for p in (CL / "skills").glob("*.md")]
    # MCP
    cj = jload(HOME / ".claude.json", {})
    needs = jload(CL / "mcp-needs-auth-cache.json", {}) or {}
    mcp = []
    for n, v in (cj.get("mcpServers") or {}).items():
        t = v.get("type", "stdio")
        mcp.append({"name": n, "origin": "пользовательский (~/.claude.json)", "type": t, "target": re.sub(r"[?#].*$", "", v.get("url", "")) if v.get("url") else os.path.basename(str(v.get("command", ""))) + " (аргументы и env скрыты)", "plugin": None})
    for p in plugins:
        for m in p["mcp"]:
            mcp.append(dict(m))
    for m in mcp:
        full = "plugin:%s:%s" % (m["plugin"], m["name"]) if m.get("plugin") else m["name"]
        if full in SESSION_FAILED or m["name"] in SESSION_FAILED:
            m["status"] = "failed"
        elif full in needs or full in SESSION_NEEDS_AUTH:
            m["status"] = "needs-auth"
        else:
            m["status"] = "unknown"
        r = ru_mcp.get(m["name"]) or ru_mcp.get(full) or {}
        m["ru"] = r.get("used_for", "")
        m["data_to"] = r.get("data_goes_to", "")
        if r.get("status") in ("connected", "failed"):
            m["status"] = r["status"]
        if m.get("plugin") and any(p["name"] == m["plugin"] and p["status"] == "disabled" for p in plugins):
            m["status"] = "plugin-disabled"
    mcp.extend(dict(m, data_to=m.get("data_to", "")) for m in SESSION_MCP)
    # доступное в маркетплейсах, но не установленное
    mk_info, avail = [], []
    instnames = {pid for pid in inst}
    for mkdir in sorted((CL / "plugins" / "marketplaces").glob("*")):
        mj = jload(mkdir / ".claude-plugin" / "marketplace.json", None)
        if not mj:
            continue
        pls = mj.get("plugins", [])
        cnt = 0
        for x in pls:
            pid = x.get("name", "") + "@" + mkdir.name
            if pid in instnames:
                continue
            cnt += 1
            avail.append({"name": x.get("name", ""), "marketplace": mkdir.name, "description": (x.get("description") or "")[:260], "category": x.get("category", ""), "homepage": x.get("homepage", "")})
        mk_info.append({"name": mkdir.name, "plugins_total": len(pls), "installed": len(pls) - cnt, "available": cnt, "source": (jload(CL / "plugins" / "known_marketplaces.json", {}).get(mkdir.name, {}) or {}).get("source", {}).get("repo", "")})
    allhooks = [h for p in plugins for h in p["hooks"]]
    out = {"date": TODAY, "claude_code_version": setup.get("claude_code_version", ""), "plugins": plugins, "user_components": user, "stray_files": stray, "mcp": mcp,
           "marketplaces": mk_info, "available_not_installed": avail, "hooks": allhooks,
           "settings": {"enabledPlugins": {k: bool(v) for k, v in enabled.items()}, "keys": sorted(settings.keys()), "env_keys": sorted((settings.get("env") or {}).keys()), "model": settings.get("model"), "defaultMode": (settings.get("permissions") or {}).get("defaultMode")},
           "needs_auth": sorted(needs.keys())}
    all_c = [c for p in plugins for c in p["components"]] + user
    out["totals"] = {"plugins": len(plugins), "plugins_active": sum(p["status"] == "active" for p in plugins), "plugins_disabled": sum(p["status"] == "disabled" for p in plugins),
                     "skills": sum(c["kind"] == "skill" for c in all_c), "commands": sum(c["kind"] == "command" for c in all_c), "agents": sum(c["kind"] == "agent" for c in all_c),
                     "hooks": len(allhooks), "mcp": len(mcp), "available_not_installed": len(avail)}
    # пересечения (эвристики)
    out["interference"] = interference(all_c, plugins, mcp)
    dst = HERE / "catalog.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("catalog.json: %s" % json.dumps(out["totals"], ensure_ascii=False), "%.0f КБ" % (dst.stat().st_size / 1024))


STOP = set("with that this from your when use used using for the and are into any all can will you not have has but than then them they their what which whether such also more most each other only about over under after before while where who how out off its via per etc without within across between should would could may might including include includes new one two".split())


def toks(s):
    return {w for w in re.findall(r"[a-zа-я][a-zа-я0-9-]{3,}", s.lower()) if w not in STOP}


def interference(all_c, plugins, mcp):
    res = {}
    # 1. одинаковые имена
    by = {}
    for c in all_c:
        by.setdefault(c["name"], []).append(c)
    res["same_name"] = [{"name": n, "items": [{"kind": c["kind"], "source": (c["plugin"] or "личный"), "slash": c.get("slash", "")} for c in v]} for n, v in sorted(by.items()) if len(v) > 1 and len({(c["plugin"] or "user") for c in v}) > 1]
    # 2. хуки по событиям
    ev = {}
    for p in plugins:
        for h in p["hooks"]:
            ev.setdefault(h["event"], []).append({"plugin": p["name"], "matcher": h["matcher"], "command": h["command"], "timeout": h["timeout"]})
    res["hook_events"] = [{"event": k, "hooks": v, "count": len(v)} for k, v in sorted(ev.items())]
    # 3. похожие описания у скилов разных источников
    sk = [c for c in all_c if c["kind"] in ("skill", "agent") and c.get("description")]
    for c in sk:
        c["_t"] = toks(c["description"] + " " + c["name"].replace("-", " "))
    pairs = []
    for i, a in enumerate(sk):
        for b in sk[i + 1:]:
            if (a["plugin"] or "user") == (b["plugin"] or "user") or not a["_t"] or not b["_t"]:
                continue
            inter = a["_t"] & b["_t"]
            j = len(inter) / len(a["_t"] | b["_t"])
            if j >= 0.2 and len(inter) >= 6:
                pairs.append((j, a, b, sorted(inter, key=len, reverse=True)[:8]))
    pairs.sort(key=lambda x: -x[0])
    res["similar"] = [{"score": round(j, 2), "a": {"name": a["name"], "kind": a["kind"], "source": a["plugin"] or "личный"}, "b": {"name": b["name"], "kind": b["kind"], "source": b["plugin"] or "личный"}, "words": w} for j, a, b, w in pairs[:150]]
    for c in sk:
        c.pop("_t", None)
    # 4. группы MCP/плагинов по назначению (ручные ключевые слова)
    groups = {"Управление браузером и тесты в браузере": ["playwright", "browser", "chrome", "devtools", "testsprite"], "Документация и знания": ["context7", "docs", "notion", "confluence", "atlassian"], "Дизайн": ["figma", "canva", "design"],
              "Аналитика и данные": ["amplitude", "hex", "definite", "similarweb", "ahrefs", "supermetrics", "pendo", "bigquery", "snowflake"], "Задачи и трекеры": ["linear", "asana", "monday", "clickup", "atlassian", "jira"], "Коммуникации": ["slack", "intercom", "telegram", "fireflies"], "Маркетинг и CRM": ["hubspot", "klaviyo"], "Модели и датасеты": ["hf-mcp", "hugging"]}
    gl = []
    for g, kws in groups.items():
        items = sorted({m["name"] + (" (" + m["plugin"] + ")" if m.get("plugin") else "") for m in mcp if any(k in m["name"].lower() for k in kws)})
        if len(items) > 1:
            gl.append({"group": g, "items": items})
    res["mcp_groups"] = gl
    return res


if __name__ == "__main__":
    sys.exit(main())
