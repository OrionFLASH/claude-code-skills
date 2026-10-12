#!/usr/bin/env python3
"""Build inventory.json for ECC (static read only; never executes ECC code).
Usage: python3 -I build.py <ECC_ROOT> <OUT_JSON>
"""
import json, os, re, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fm import parse_fm
from domains import DOMAINS, SKILL_DOMAINS, AGENT_DOMAINS, COMMAND_DOMAINS, invert
import ru_summaries as RU
import components as COMP

ROOT = os.path.abspath(sys.argv[1])
OUT = sys.argv[2]
COMMIT = "b92f181b3b748d1abbc2afd94af6aa7d8c8fca29"
BLOB = f"https://github.com/affaan-m/ECC/blob/{COMMIT}/"


def rd(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


def nfiles(p):
    full = os.path.join(ROOT, p)
    if os.path.isfile(full):
        return 1
    return sum(len(fs) for _, _, fs in os.walk(full))


def first_sentence(s, limit=220):
    s = re.sub(r"\s+", " ", s or "").strip()
    m = re.match(r"(.+?[.!?。])(\s|$)", s)
    out = m.group(1) if m else s
    if len(out) > limit:
        cut = out[:limit].rsplit(" ", 1)[0]
        out = cut.rstrip(",;:—-") + "…"
    return out


def quote_lt15(s, anchor_re):
    """Return a <15-word excerpt of s around the first anchor match."""
    s = re.sub(r"\s+", " ", s)
    sentences = re.split(r"(?<=[.!?])\s+", s)
    for sen in sentences:
        if re.search(anchor_re, sen):
            words = sen.split()
            if len(words) <= 14:
                return sen
            idx = next(i for i, w in enumerate(words) if re.search(anchor_re, " ".join(words[i:i + 3])))
            start = max(0, idx - 2)
            return " ".join(words[start:start + 14])
    return None


SKILL_DOM = invert(SKILL_DOMAINS)
AGENT_DOM = invert(AGENT_DOMAINS)
CMD_DOM = invert(COMMAND_DOMAINS)

# ---------------- install modules (for skill -> module) ----------------
mods = json.loads(rd("manifests/install-modules.json"))["modules"]
skill2mod = {}
for m in mods:
    for p in m.get("paths", []):
        if p.startswith("skills/"):
            skill2mod.setdefault(p.split("/")[1], []).append(m["id"])
profiles = json.loads(rd("manifests/install-profiles.json"))["profiles"]
pi_core_skills = set(os.listdir(os.path.join(ROOT, "pi/core/skills")))

# ---------------- skills ----------------
CODE_EXT = (".py", ".js", ".mjs", ".cjs", ".ts", ".sh", ".ps1", ".rb", ".go", ".rs")
skill_names = sorted(d for d in os.listdir(os.path.join(ROOT, "skills"))
                     if os.path.isfile(os.path.join(ROOT, "skills", d, "SKILL.md")))
skills = []
for s in skill_names:
    p = f"skills/{s}/SKILL.md"
    text = rd(p)
    fmd, body = parse_fm(text)
    desc = re.sub(r"\s+", " ", fmd.get("description", "")).strip()
    sdir = os.path.join(ROOT, "skills", s)
    scripts, other_files = [], []
    for r, _, fs in os.walk(sdir):
        for f in fs:
            rel = os.path.relpath(os.path.join(r, f), ROOT)
            if rel == p:
                continue
            if f.endswith(CODE_EXT):
                scripts.append(rel)
            else:
                other_files.append(rel)
    hint = None
    m = re.search(r"((?:Use|Invoke|Activate|Trigger|Apply)[^.]*?\b(?:when|for|after|before|whenever|if)\b[^.]*\.?)", desc)
    if m:
        hint = m.group(1).strip()
    elif re.search(r"\bUse\b", desc):
        hint = desc[desc.index("Use"):][:240]
    if s not in SKILL_DOM:
        raise SystemExit(f"skill without domain: {s}")
    meta = fmd.get("metadata") if isinstance(fmd.get("metadata"), dict) else {}
    skills.append({
        "name": s,
        "file": p,
        "url": BLOB + p,
        "domain": SKILL_DOM[s],
        "install_module": skill2mod.get(s, []),
        "in_pi_core": s in pi_core_skills,
        "origin": meta.get("origin") or fmd.get("origin") or None,
        "description": desc,
        "lines": text.count("\n") + (0 if text.endswith("\n") else 1),
        "has_scripts": bool(scripts),
        "scripts": sorted(scripts),
        "extra_files": len(other_files),
        "tools": fmd.get("tools") or fmd.get("allowed-tools") or None,
        "auto_invoke_hint": hint,
        "summary": first_sentence(desc),
        "summary_lang": "en (машинное сокращение description)",
    })

skill_set = set(skill_names)
# ---------------- agents ----------------
agent_files = sorted(f for f in os.listdir(os.path.join(ROOT, "agents")) if f.endswith(".md"))
agent_names = [f[:-3] for f in agent_files]
agent_set = set(agent_names)

GENERIC_SKILLS = {"seo", "taste", "council", "benchmark", "accessibility", "blueprint", "ck",
                  "uncloud", "videodb", "crosspost", "gateguard", "x-api"}


def find_skills(text, self_name=None):
    found = {}
    for s in skill_set:
        if s == self_name:
            continue
        e = re.escape(s)
        pats = [rf"skills/{e}\b", rf"`/?{e}`\s*skill", rf"\b{e}\s+skill\b", rf"skill[:\s]+`?{e}`?\b",
                rf"ecc:{e}\b"]
        if s not in GENERIC_SKILLS and "-" in s:
            pats.append(rf"`{e}`")
        for pt in pats:
            m = re.search(pt, text)
            if m:
                found[s] = text[:m.start()].count("\n") + 1
                break
    return found


def find_agents(text, self_name=None):
    explicit, mention = {}, {}
    for a in agent_set:
        if a == self_name:
            continue
        e = re.escape(a)
        ex = [rf"ecc:{e}\b", rf"\*\*{e}\*\*\s+agent", rf"`{e}`\s+agent", rf"\b{e}\s+agent\b",
              rf"subagent_type[\"'`\s:=]+[\"'`]?(?:ecc:)?{e}\b", rf"^agent:\s*(?:ecc:)?{e}\b",
              rf"\b[Uu]se `{e}`", rf"delegates? to (?:the )?`?{e}\b", rf"[Ll]aunch (?:the |an? )?`?{e}`?"]
        hit = None
        for pt in ex:
            m = re.search(pt, text, re.M)
            if m:
                hit = m; break
        if hit:
            explicit[a] = text[:hit.start()].count("\n") + 1
            continue
        mt = [rf"`{e}`", rf"\*\*{e}\*\*", rf"agents/{e}\.md"] + ([rf"(?<![\w/-]){e}(?![\w/-])"] if "-" in a else [])
        for pt in mt:
            m = re.search(pt, text)
            if m:
                mention[a] = text[:m.start()].count("\n") + 1
                break
    return explicit, mention


PROACTIVE_RE = r"PROACTIVELY|[Pp]roactively|MUST BE USED|Use immediately|Automatically activated|Triggered by"
agents = []
for f in agent_files:
    p = f"agents/{f}"
    text = rd(p)
    fmd, body = parse_fm(text)
    name = fmd.get("name") or f[:-3]
    desc = re.sub(r"\s+", " ", fmd.get("description", "")).strip()
    tools = [t.strip() for t in re.split(r",", fmd.get("tools", "")) if t.strip()] if isinstance(fmd.get("tools"), str) else (fmd.get("tools") or [])
    proactive = bool(re.search(r"PROACTIVELY|[Pp]roactively|MUST BE USED|Use immediately|Automatically activated", desc))
    phrase = quote_lt15(desc, PROACTIVE_RE) if re.search(PROACTIVE_RE, desc) else None
    sk = find_skills(body)
    ag_ex, ag_mt = find_agents(body, name)
    if name not in AGENT_DOM:
        raise SystemExit(f"agent without domain: {name}")
    role = ("build-resolver" if name.endswith("-resolver") else
            "reviewer" if name.endswith("-reviewer") or name in ("code-reviewer",) else
            "architect" if name.endswith("architect") else
            "planner" if name.endswith("planner") or name == "planner" else
            "analyzer" if name.endswith(("analyzer", "hunter", "explorer", "miner")) else
            "operator")
    strong = len(re.findall(r"\b(ALWAYS|NEVER|MUST|CRITICAL|IMPORTANT)\b", body))
    agents.append({
        "name": name,
        "file": p,
        "url": BLOB + p,
        "description": desc,
        "model": fmd.get("model"),
        "tools": tools,
        "can_write": any(t in tools for t in ("Write", "Edit", "MultiEdit")),
        "can_bash": "Bash" in tools,
        "proactive": proactive,
        "proactive_phrase": phrase,
        "domain": AGENT_DOM[name],
        "role": role,
        "skills_used": sorted(sk),
        "agents_referenced": sorted(ag_ex),
        "commands_using": [],
        "lines": text.count("\n") + 1,
        "prompt_defense_baseline": "## Prompt Defense Baseline" in body,
        "strong_directive_words": strong,
        "summary": RU.AGENTS.get(name) or first_sentence(desc),
    })
agent_by = {a["name"]: a for a in agents}

# ---------------- commands ----------------
docmap = {}
for ln in rd("docs/COMMAND-AGENT-MAP.md").split("\n"):
    m = re.match(r"^\|\s*`/([a-z0-9-]+)`\s*\|\s*([^|]*)\|", ln)
    if m:
        ags = [a for a in re.findall(r"[a-z0-9-]+", m.group(2)) if a in agent_set]
        docmap[m.group(1)] = ags
cmd_files = sorted(f for f in os.listdir(os.path.join(ROOT, "commands")) if f.endswith(".md"))
SCRIPT_RE = re.compile(r"(?:node|python3?|bash|sh)\s+[\"']?(?:\$\{?CLAUDE_PLUGIN_ROOT\}?/|~/\.claude/|\$\{?ECC_ROOT\}?/)?((?:scripts|skills|workflows)/[\w./-]+\.(?:js|mjs|cjs|py|sh))")
WF_RE = re.compile(r"(workflows/[\w.-]+\.workflow\.js)")
NPX_RE = re.compile(r"\bnpx\s+(?:-y\s+)?([@\w./-]+)")
commands = []
for f in cmd_files:
    p = f"commands/{f}"
    text = rd(p)
    fmd, body = parse_fm(text)
    name = f[:-3]
    desc = re.sub(r"\s+", " ", fmd.get("description", "")).strip()
    fm_agent = fmd.get("agent")
    fm_agent = fm_agent.split(":")[-1] if isinstance(fm_agent, str) and fm_agent else None
    ag_ex, ag_mt = find_agents(desc + "\n" + body)
    if fm_agent:
        ag_ex.setdefault(fm_agent, 1)
    sk = find_skills(desc + "\n" + body)
    scripts = sorted(set(SCRIPT_RE.findall(body)))
    wfs = sorted(set(WF_RE.findall(body)))
    npx = sorted(set(x for x in NPX_RE.findall(body) if not x.startswith("-")))
    lines = text.count("\n") + 1
    low = (desc + " " + body[:1500]).lower()
    shim_words = bool(re.search(r"slash-command entrypoint|thin slash-command|surface for|wrapper (that kicks off|for)|wraps the|alias of|thin cli wrapper|invokes the [\w-]+ skill|uses the [\w-]+ skill", low))
    if ag_ex:
        kind = "agent"
    elif shim_words or ((scripts or wfs) and lines < 80) or (sk and lines < 60):
        kind = "shim"
    else:
        kind = "inline"
    if name not in CMD_DOM:
        raise SystemExit(f"command without domain: {name}")
    ov = getattr(RU, "COMMAND_OVERRIDES", {}).get(name, {})
    if "agents" in ov:
        ag_ex = {a: 1 for a in ov["agents"]}
        kind = ov.get("kind", "agent" if ag_ex else kind)
    elif "kind" in ov:
        kind = ov["kind"]
    if ov.get("drop_agents"):
        for a in ov["drop_agents"]:
            ag_ex.pop(a, None); ag_mt[a] = 1
        if not ag_ex and kind == "agent":
            kind = ov.get("kind", "inline")
    primary = fm_agent or (min(ag_ex, key=lambda a: ag_ex[a]) if ag_ex else None)
    dmi = str(fmd.get("disable-model-invocation", "")).lower() == "true"
    commands.append({
        "name": "/" + name,
        "file": p,
        "url": BLOB + p,
        "description": desc,
        "argument_hint": fmd.get("argument-hint"),
        "kind": kind,
        "agent": primary,
        "agents": sorted(ag_ex),
        "agents_mentioned": sorted(ag_mt),
        "skills": sorted(sk),
        "scripts": scripts,
        "workflows": wfs,
        "npx": npx,
        "domain": CMD_DOM[name],
        "manual_only": True,
        "model_invocable": not dmi,
        "agents_per_docs_map": docmap.get(name),
        "frontmatter_model": fmd.get("model"),
        "note": ov.get("note"),
        "allowed_tools": fmd.get("allowed-tools"),
        "lines": lines,
        "summary": RU.COMMANDS.get(name) or first_sentence(desc),
    })
    for a in ag_ex:
        if a in agent_by:
            agent_by[a]["commands_using"].append("/" + name)

cmd_names = {c["name"][1:] for c in commands}
for a in agents:
    for m in re.findall(r"(?<![\w/])/([a-z][a-z0-9-]+)", a["description"]):
        if m in cmd_names:
            a["commands_using"].append("/" + m)
    a["commands_using"] = sorted(set(a["commands_using"]))
    a["commands_per_docs_map"] = sorted("/" + c for c, ags in docmap.items() if a["name"] in ags)
for sk in skills:
    sk["used_by_commands"] = sorted(c["name"] for c in commands if sk["name"] in c["skills"])
    sk["used_by_agents"] = sorted(a["name"] for a in agents if sk["name"] in a["skills_used"])

# ---------------- legacy shims ----------------
legacy = []
for f in sorted(os.listdir(os.path.join(ROOT, "legacy-command-shims/commands"))):
    p = f"legacy-command-shims/commands/{f}"
    fmd, body = parse_fm(rd(p))
    legacy.append({"name": "/" + f[:-3], "file": p, "description": re.sub(r"\s+", " ", fmd.get("description", "")).strip(),
                   "skills": sorted(find_skills(body)), "loaded_by_default": False})

# ---------------- rules ----------------
rules_common, rules_lang = [], []
for f in sorted(os.listdir(os.path.join(ROOT, "rules/common"))):
    p = f"rules/common/{f}"
    text = rd(p)
    fmd, body = parse_fm(text)
    h = re.search(r"^#\s+(.+)$", body, re.M)
    rules_common.append({"file": p, "url": BLOB + p, "always_loaded": "paths" not in fmd,
                         "title": h.group(1).strip() if h else f,
                         "lines": text.count("\n") + 1,
                         "summary": RU.RULES_COMMON.get(f, h.group(1).strip() if h else f)})
for d in sorted(os.listdir(os.path.join(ROOT, "rules"))):
    full = os.path.join(ROOT, "rules", d)
    if not os.path.isdir(full) or d == "common":
        continue
    files = sorted(os.listdir(full))
    globs, nopaths = [], []
    for f in files:
        fmd, _ = parse_fm(rd(f"rules/{d}/{f}"))
        ps = fmd.get("paths")
        if isinstance(ps, list) and ps:
            for g in ps:
                if g not in globs:
                    globs.append(g)
        else:
            nopaths.append(f)
    rules_lang.append({"lang": d, "dir": f"rules/{d}/", "files": len(files), "file_names": files,
                       "paths_globs": globs, "files_without_paths": nopaths,
                       "summary": RU.RULES_LANG.get(d, "")})
rules_total = nfiles("rules")
rules_md_no_readme = sum(1 for r, _, fs in os.walk(os.path.join(ROOT, "rules")) for f in fs if f.endswith(".md") and f != "README.md")

# ---------------- MCP ----------------
mcp_cat = json.loads(rd("mcp-configs/mcp-servers.json"))["mcpServers"]
catalog = []
for name, cfg in mcp_cat.items():
    remote = cfg.get("type") in ("http", "sse") or "url" in cfg
    env_keys = sorted(k for k, v in (cfg.get("env") or {}).items() if "YOUR_" in str(v) or "KEY" in k or "TOKEN" in k)
    hdr_keys = sorted(k for k, v in (cfg.get("headers") or {}).items())
    info = COMP.MCP_INFO.get(name, {})
    catalog.append({
        "name": name,
        "kind": "remote" if remote else "local",
        "transport": cfg.get("type", "stdio") if remote else "stdio",
        "launch": cfg.get("url") if remote else " ".join([cfg.get("command", "")] + cfg.get("args", [])),
        "pinned_version": (lambda a: (re.search(r"@(\d[\w.]*)$", a) or re.search(r"==(\d[\w.]*)$", a)).group(1) if (re.search(r"@(\d[\w.]*)$", a) or re.search(r"==(\d[\w.]*)$", a)) else ("latest" if a.endswith("@latest") else None))(next((x for x in cfg.get("args", []) if not x.startswith("-")), "")) if not remote else None,
        "needs_keys": env_keys + [f"header:{h}" for h in hdr_keys] + info.get("extra_keys", []),
        "sends_data_to": info.get("sends", ""),
        "summary": info.get("ru") or first_sentence(cfg.get("description", "")),
        "description": cfg.get("description", ""),
    })
root_mcp = json.loads(rd(".mcp.json"))["mcpServers"]
plugin_json = json.loads(rd(".claude-plugin/plugin.json"))

# ---------------- hooks count ----------------
hooks_json = json.loads(rd("hooks/hooks.json"))
hh = hooks_json.get("hooks", hooks_json)
hook_entries = sum(len(v) for v in hh.values())
hook_commands = sum(len(e.get("hooks", [])) for v in hh.values() for e in v)
hook_by_event = {k: len(v) for k, v in hh.items()}


def count_hooks_file(p):
    try:
        d = json.loads(rd(p))
    except Exception as e:
        return None
    h = d.get("hooks", d.get("events", d))
    if isinstance(h, dict):
        return sum(len(v) if isinstance(v, list) else 1 for v in h.values() if not isinstance(v, str))
    if isinstance(h, list):
        return len(h)
    return None


other_hook_files = {}
for p in ["hooks/codex-hooks.json", "hooks/qoder-hooks.json", "hooks/memory-persistence/hooks.json",
          ".cursor/hooks.json", "scaffolds/cursor/hooks.json"]:
    if os.path.exists(os.path.join(ROOT, p)):
        other_hook_files[p] = count_hooks_file(p)
other_hook_files["hooks/hermes/ (python)"] = len(os.listdir(os.path.join(ROOT, "hooks/hermes")))
other_hook_files[".kiro/hooks/ (files)"] = nfiles(".kiro/hooks")
other_hook_files["scripts/hooks/ (hook scripts)"] = nfiles("scripts/hooks")

# ---------------- counts & claims ----------------
counts = {
    "agents": len(agents),
    "skills": len(skills),
    "commands": len(commands),
    "rules_files": rules_total,
    "hook_entries": hook_entries,
    "mcp_servers": len(catalog),
}
counts_detail = {
    "agents_by_model": {},
    "agents_proactive": sum(a["proactive"] for a in agents),
    "skills_with_scripts": sum(s["has_scripts"] for s in skills),
    "skills_total_lines": sum(s["lines"] for s in skills),
    "skills_in_pi_core": sum(s["in_pi_core"] for s in skills),
    "commands_by_kind": {},
    "commands_model_invocable": sum(c["model_invocable"] for c in commands),
    "legacy_command_shims_not_loaded": len(legacy),
    "rules_md_without_readme": rules_md_no_readme,
    "rules_common_files": len(rules_common),
    "rules_language_dirs": len(rules_lang),
    "rules_language_files": sum(r["files"] for r in rules_lang),
    "hook_entries_by_event": hook_by_event,
    "hook_commands_in_hooks_json": hook_commands,
    "hook_files_other_harnesses": other_hook_files,
    "mcp_in_claude_plugin": len(plugin_json.get("mcpServers") or {}),
    "mcp_root_dot_mcp_json": list(root_mcp.keys()),
    "mcp_catalog_remote": sum(1 for c in catalog if c["kind"] == "remote"),
    "mcp_catalog_local": sum(1 for c in catalog if c["kind"] == "local"),
    "mcp_catalog_needing_keys": sum(1 for c in catalog if c["needs_keys"]),
    "scripts_dir_files": nfiles("scripts"),
    "tests_files": nfiles("tests"),
    "docs_files": nfiles("docs"),
    "npm_bins": json.loads(rd("package.json")).get("bin"),
}
for a in agents:
    counts_detail["agents_by_model"][a["model"]] = counts_detail["agents_by_model"].get(a["model"], 0) + 1
for c in commands:
    counts_detail["commands_by_kind"][c["kind"]] = counts_detail["commands_by_kind"].get(c["kind"], 0) + 1


def grep_line(path, pat):
    for i, ln in enumerate(rd(path).split("\n"), 1):
        if re.search(pat, ln):
            return i, ln.strip()[:160]
    return None, None


claims = []
for path, pat, what in [
    (".claude-plugin/plugin.json", r"71 agents, 311 skills", "plugin.json description: 71 agents, 311 skills, 97 legacy command shims"),
    ("README.md", r"311 skills", "README: 71 agents / 311 skills / 97 legacy command shims"),
    ("README.md", r"95 legacy command shims", "README (раздел Qoder CLI) называет 95 legacy command shims — расходится с 97 в commands/"),
    ("README.md", r"281 skills", "README, блок «What changed in v2.0.0»: 281 skills, 67 agents, 94 command shims — исторические числа версии 2.0.0, не текущие"),
    ("SOUL.md", r"71 specialized agents", "SOUL.md: 71 agents, 311 skills, 97 commands"),
    ("AGENTS.md", r"311 skills", "AGENTS.md: 311 skills, 97 commands"),
    ("rules/common/agents.md", r"69 agents", "rules/common/agents.md: «full roster of 69 agents» — устарело (фактически 71)"),
    (".codex-plugin/plugin.json", r"281 ECC skills", ".codex-plugin/plugin.json shortDescription: «281 ECC skills» — устарело (фактически 311)"),
]:
    ln, txt = grep_line(path, pat)
    if ln:
        claims.append({"file": path, "line": ln, "url": f"{BLOB}{path}#L{ln}", "claim": what, "excerpt": txt})

# ---------------- top level ----------------
top_level = []
for e in COMP.TOP_LEVEL:
    e = dict(e)
    e["files"] = nfiles(e["path"].rstrip("/")) if os.path.exists(os.path.join(ROOT, e["path"].rstrip("/"))) else 0
    top_level.append(e)
covered = {e["path"].rstrip("/") for e in top_level}
missing_top = [x for x in sorted(os.listdir(ROOT)) if x not in covered and x != ".git"]

# ---------------- domains ----------------
domains = []
for did, title, descr in DOMAINS:
    domains.append({
        "id": did, "title": title,
        "agents": sum(1 for a in agents if a["domain"] == did),
        "skills": sum(1 for s in skills if s["domain"] == did),
        "commands": sum(1 for c in commands if c["domain"] == did),
        "description": descr,
        "agent_names": [a["name"] for a in agents if a["domain"] == did],
        "command_names": [c["name"] for c in commands if c["domain"] == did],
    })

# install profiles (summary for convenience)
prof = [{"id": k, "modules": v.get("modules", []), "description": v.get("description", "")} for k, v in profiles.items()]
modules = [{"id": m["id"], "kind": m.get("kind"), "description": m.get("description", ""), "paths": len(m.get("paths", [])),
            "skills": sum(1 for p in m.get("paths", []) if p.startswith("skills/"))} for m in mods]

inv = {
    "commit": COMMIT,
    "commit_date": "2026-10-11",
    "version": rd("VERSION").strip(),
    "repo": "https://github.com/affaan-m/ECC",
    "generated": "2026-10-13",
    "method": "Статическое чтение свежей копии (--depth 1) Python-скриптом: frontmatter агентов/команд/скилов/правил, hooks/hooks.json, mcp-configs/mcp-servers.json, manifests/*.json, package.json. Код ECC не запускался.",
    "counts": counts,
    "counts_detail": counts_detail,
    "counts_check": {
        "ok": counts["agents"] == 71 and counts["skills"] == 311 and counts["commands"] == 97,
        "expected_from_manifest": {"agents": 71, "skills": 311, "commands": 97},
        "previous_report_2d515e4": {"agents": 71, "skills": 306, "commands": 97, "hook_entries": 27, "rules_files": 122},
        "delta_vs_previous": {"skills": counts["skills"] - 306, "agents": counts["agents"] - 71,
                              "commands": counts["commands"] - 97, "hook_entries": counts["hook_entries"] - 27,
                              "rules_files": counts["rules_files"] - 122},
        "notes": [
            "rules_files = все файлы в rules/ (включая rules/README.md); без README — " + str(rules_md_no_readme) + ".",
            "hook_entries = записи (matcher-блоки) в hooks/hooks.json для Claude Code; хуки для других харнессов посчитаны отдельно в counts_detail.hook_files_other_harnesses.",
            "mcp_servers = записи каталога mcp-configs/mcp-servers.json (не ставятся плагином автоматически: в plugin.json \"mcpServers\": {}). Отдельно .mcp.json в корне содержит chrome-devtools для Codex/ручной настройки.",
            "pi/core/skills содержит 132 скила: 131 совпадает по имени со skills/, плюс ecc-council (переименованная копия council).",
            "Расхождение с docs/COMMAND-AGENT-MAP.md: карта приписывает агентов командам /build-fix, /code-review, /refactor-clean, /update-docs, /update-codemaps, /go-test, /loop-*, /multi-*, /plan, но в текущих файлах commands/ эти команды агентов не вызывают (работают inline) — см. поле agents_per_docs_map.",
            "Команды: 97 файлов в commands/ (загружаются плагином) + 12 архивных legacy-command-shims (по умолчанию не загружаются).",
        ],
        "claims_in_repo": claims,
    },
    "install_profiles": prof,
    "install_modules": modules,
    "top_level": top_level,
    "top_level_uncovered": missing_top,
    "agents": agents,
    "skills": skills,
    "commands": commands,
    "legacy_command_shims": legacy,
    "rules": {
        "installed_by_plugin": False,
        "how_installed": "Плагины Claude Code не умеют раздавать rules (README.md: «Claude Code plugins cannot distribute `rules`»). Правила копируются вручную или установщиком (install.sh / ecc-install, модуль rules-core) в ~/.claude/rules/ecc/ или .claude/rules/. Файлы без frontmatter `paths` грузятся всегда; файлы языков с `paths` — только при работе с подходящими файлами.",
        "evidence": [{"file": "README.md", "line": grep_line("README.md", r"plugins cannot distribute `rules`")[0]},
                     {"file": "rules/README.md", "line": 1}],
        "common": rules_common,
        "languages": rules_lang,
        "total_files": rules_total,
    },
    "mcp": {
        "in_plugin": [],
        "in_plugin_note": "В .claude-plugin/plugin.json явно стоит \"mcpServers\": {} — это отказ от автозагрузки корневого .mcp.json при установке плагина Claude Code (см. .claude-plugin/PLUGIN_SCHEMA_NOTES.md). Значит, плагин сам MCP-серверы не добавляет.",
        "root_dot_mcp_json": [{"name": k, "launch": " ".join([v.get("command", "")] + v.get("args", [])), "used_by": "Codex-плагин и ручная настройка; для Claude-плагина отключено"} for k, v in root_mcp.items()],
        "catalog_file": "mcp-configs/mcp-servers.json",
        "catalog_usage": "Шаблон для ручного копирования в ~/.claude.json (mcpServers) с заменой YOUR_*_HERE; установщик (модуль platform-configs) копирует каталог, отключение при установке — ECC_DISABLED_MCPS=… (из _comments каталога). Совет каталога: держать включёнными < 10 MCP.",
        "catalog": catalog,
    },
    "other_components": COMP.OTHER,
    "domains": domains,
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(inv, f, ensure_ascii=False, indent=2)
    f.write("\n")

print(json.dumps(counts, ensure_ascii=False))
print("by kind", counts_detail["commands_by_kind"], "by model", counts_detail["agents_by_model"])
print("uncovered top-level:", missing_top)
