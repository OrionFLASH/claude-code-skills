#!/usr/bin/env python3
"""Build graph.json for the ECC study from ECC sources (static read only).

Usage:  python3 -I build_graph.py <ECC_ROOT> <OUT_JSON>

Standard library only (owner's "Work" mode). Never executes ECC code.

Edge confidence:
  explicit      structured link: command frontmatter `agent:`, `subagent_type`
                in a prompt, hooks/hooks.json script argument, dispatcher
                require()/table, literal path or `spawnSync('claude', ...)` in code
  text-mention  the name appears in prose of a command / agent / skill / rule
                (context-checked for ambiguous one-word names)
  inferred      derived through a helper (e.g. getSessionsDir() ->
                ~/.claude/session-data/) or from a phrase like "save to"
"""
import json
import os
import re
import sys

ROOT = sys.argv[1]
OUT = sys.argv[2]
COMMIT = "b92f181b3b748d1abbc2afd94af6aa7d8c8fca29"
MAX_NODES = 400


def rd(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as f:
        return f.read()


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    fm, body = {}, text
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            mm = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
            if mm:
                fm[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    return fm, body, (m.group(0).count("\n") if m else 0)


def line_of(text, idx):
    return text.count("\n", 0, idx) + 1


def short(s, n=180):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


nodes, edges, seen_edges = {}, [], set()


def add_node(nid, ntype, label, group="", summary="", file="", auto=False, layer=""):
    if nid not in nodes:
        nodes[nid] = dict(id=nid, type=ntype, label=label, group=group,
                          summary=summary, file=file, auto=auto, layer=layer)
    return nid


def add_edge(a, b, kind, label, evidence, confidence):
    key = (a, b, kind)
    if a == b or key in seen_edges:
        return
    seen_edges.add(key)
    edges.append(dict(**{"from": a, "to": b}, kind=kind, label=label,
                      evidence=evidence, confidence=confidence))


# ---------------------------------------------------------------- inventory
cmd_files = sorted(f for f in os.listdir(os.path.join(ROOT, "commands")) if f.endswith(".md"))
agent_files = sorted(f for f in os.listdir(os.path.join(ROOT, "agents")) if f.endswith(".md"))
skill_dirs = sorted(d for d in os.listdir(os.path.join(ROOT, "skills"))
                    if os.path.isfile(os.path.join(ROOT, "skills", d, "SKILL.md")))
CMDS = [f[:-3] for f in cmd_files]
AGENTS = [f[:-3] for f in agent_files]
SKILLS = skill_dirs


def group_for(name, desc):
    n, d = name.lower(), (desc or "").lower()
    langs = ["python", "go", "golang", "rust", "kotlin", "flutter", "dart", "cpp", "c++", "react",
             "vue", "java", "swift", "csharp", "fsharp", "php", "ruby", "django", "fastapi",
             "gradle", "typescript", "pytorch", "harmonyos", "laravel", "springboot", "quarkus",
             "angular", "nuxt", "nextjs", "perl", "android"]
    rules = [
        ("orchestration", ["orch-", "gan-", "santa", "loop", "multi-", "council", "team-", "devfleet",
                           "dmux", "parallel", "autonomous", "ralphinho", "plan-orchestrate"]),
        ("memory-learning", ["instinct", "learn", "evolve", "promote", "prune", "projects", "session",
                             "checkpoint", "continuous-learning", "homunculus", "memory", "skill-create",
                             "skill-health", "aside", "strategic-compact", "context-"]),
        ("security", ["security", "gateguard", "safety", "secret", "hipaa", "phi", "sanitizer"]),
        ("review", ["review", "reviewer", "comment-analyzer", "silent-failure", "type-design",
                    "simplifier", "pr-test-analyzer", "astra"]),
        ("planning", ["plan", "prd", "prp", "architect", "spec-miner", "feature-dev", "blueprint",
                      "epic"]),
        ("testing", ["test", "tdd", "e2e", "coverage", "verification", "qa"]),
        ("build", ["build", "resolver", "quality-gate", "refactor", "dead code"]),
        ("business-content", ["marketing", "seo", "content", "brand", "article", "investor", "social",
                              "email", "lead", "crosspost", "video", "growth"]),
        ("ops-devops", ["pm2", "deploy", "docker", "kubernetes", "network", "homelab", "jira",
                        "pr", "commit", "git", "cost", "token", "update-", "codemaps", "setup-pm",
                        "auto-update", "project-init", "harness", "hookify", "skill-host", "ecc-guide",
                        "model-route", "chief-of-staff", "doc-updater", "docs-lookup", "opensource"]),
        ("research", ["research", "search", "explorer", "lookup", "osint", "scientific"]),
    ]
    for lg in langs:
        if re.search(r"(^|[-_ ])" + re.escape(lg) + r"($|[-_ ])", n):
            return "language:" + ("go" if lg == "golang" else lg)
    for g, keys in rules:
        if any(k in n for k in keys):
            return g
    for g, keys in rules:
        if any(k in d for k in keys):
            return g
    return "general"


cmd_meta, agent_meta, skill_meta = {}, {}, {}
for name in CMDS:
    rel = f"commands/{name}.md"
    t = rd(rel)
    fm, body, _ = frontmatter(t)
    cmd_meta[name] = (rel, t, fm)
for name in AGENTS:
    rel = f"agents/{name}.md"
    t = rd(rel)
    fm, body, _ = frontmatter(t)
    agent_meta[name] = (rel, t, fm)
for name in SKILLS:
    rel = f"skills/{name}/SKILL.md"
    t = rd(rel)
    fm, body, _ = frontmatter(t)
    skill_meta[name] = (rel, t, fm)

USER = add_node("user:owner", "user", "Пользователь", "user", "Человек, вызывающий команды вручную", "", False, "user")
PLUGIN = add_node("plugin:ecc", "plugin", "ecc (plugin)", "plugin",
                  "Claude Code plugin: skills/, commands/, agents/, hooks/hooks.json",
                  ".claude-plugin/plugin.json", True, "user")

for name, (rel, t, fm) in cmd_meta.items():
    auto = False  # slash commands are user-typed
    add_node(f"cmd:{name}", "command", f"/{name}", group_for(name, fm.get("description")),
             short(fm.get("description")), rel, auto, "commands")
    add_edge(USER, f"cmd:{name}", "invokes", "вручную: /" + name, f"{rel}:1", "explicit")

for name, (rel, t, fm) in agent_meta.items():
    desc = fm.get("description", "")
    proactive = bool(re.search(r"PROACTIVELY|proactively|Automatically activated|MUST BE USED", desc))
    add_node(f"agent:{name}", "agent", name, group_for(name, desc), short(desc), rel, proactive, "agents")

# ---------------------------------------------------------------- matchers
def ctx_ok(text, s, e, kind):
    """For ambiguous single-word names require nearby context."""
    pre = text[max(0, s - 2): s]
    post = text[e: e + 2]
    if pre.endswith("`") or post.startswith("`") or pre.endswith("ecc:") or text[max(0, s - 4): s] == "ecc:":
        return True
    win = text[max(0, s - 40): e + 40].lower()
    if kind == "agent":
        return bool(re.search(r"agent|subagent|delegate", win))
    if kind == "skill":
        return bool(re.search(r"skill", win))
    return False


def find_mentions(text, names, kind):
    """Yield (name, index). kind in agent|skill|command."""
    out = []
    for n in names:
        if kind == "command":
            pat = r"(?<![\w/.:-])/(?:project:|ecc:)?" + re.escape(n) + r"(?![\w-])"
        else:
            pat = r"(?<![\w/.:-])(?:ecc:)?" + re.escape(n) + r"(?![\w-])"
        for m in re.finditer(pat, text):
            s, e = m.start(), m.end()
            if kind != "command":
                # skip if this is actually a /command token or part of a path other than skills/<n>
                if text[max(0, s - 1): s] == "/":
                    continue
                single = "-" not in n
                if single and not ctx_ok(text, s, e, kind):
                    continue
            out.append((n, s))
            break  # first occurrence is enough for evidence
    # explicit skills/<name>/ path references
    if kind == "skill":
        for m in re.finditer(r"skills/([a-z0-9][a-z0-9-]*)/", text):
            if m.group(1) in names and all(m.group(1) != o[0] for o in out):
                out.append((m.group(1), m.start()))
    return out


def directive(text, idx, name):
    win = text[max(0, idx - 80): idx + len(name) + 40].lower()
    return bool(re.search(r"invoke|delegat|launch|spawn|subagent_type|run the|use the|call", win))


# ---------------------------------------------------------------- command edges
referenced_skills = {}

for name, (rel, t, fm) in cmd_meta.items():
    src = f"cmd:{name}"
    ag = fm.get("agent")
    if ag:
        a = ag.split(":")[-1]
        if a in agent_meta:
            add_edge(src, f"agent:{a}", "invokes", "frontmatter agent:", f"{rel}:{line_of(t, t.find('agent:'))}", "explicit")
    for m in re.finditer(r'subagent_type[^\n]{0,6}?["`]([\w:-]+)["`]', t):
        a = m.group(1).split(":")[-1]
        if a in agent_meta:
            add_edge(src, f"agent:{a}", "invokes", "subagent_type", f"{rel}:{line_of(t, m.start())}", "explicit")
    for a, i in find_mentions(t, AGENTS, "agent"):
        lbl = "текст: " + ("велит вызвать агента" if directive(t, i, a) else "упоминает агента")
        add_edge(src, f"agent:{a}", "invokes", lbl, f"{rel}:{line_of(t, i)}", "text-mention")
    for s, i in find_mentions(t, SKILLS, "skill"):
        referenced_skills.setdefault(s, f"{rel}:{line_of(t, i)}")
        add_edge(src, f"skill:{s}", "uses", "текст: использует скил", f"{rel}:{line_of(t, i)}", "text-mention")
    for c, i in find_mentions(t, CMDS, "command"):
        if c != name:
            add_edge(src, f"cmd:{c}", "uses", "текст: ссылается на /" + c, f"{rel}:{line_of(t, i)}", "text-mention")

# ---------------------------------------------------------------- agent edges
for name, (rel, t, fm) in agent_meta.items():
    src = f"agent:{name}"
    for m in re.finditer(r'subagent_type[^\n]{0,6}?["`]([\w:-]+)["`]', t):
        a = m.group(1).split(":")[-1]
        if a in agent_meta and a != name:
            add_edge(src, f"agent:{a}", "spawns", "subagent_type", f"{rel}:{line_of(t, m.start())}", "explicit")
    for a, i in find_mentions(t, [x for x in AGENTS if x != name], "agent"):
        add_edge(src, f"agent:{a}", "uses", "текст: упоминает агента", f"{rel}:{line_of(t, i)}", "text-mention")
    for s, i in find_mentions(t, SKILLS, "skill"):
        referenced_skills.setdefault(s, f"{rel}:{line_of(t, i)}")
        add_edge(src, f"skill:{s}", "uses", "текст: опирается на скил", f"{rel}:{line_of(t, i)}", "text-mention")
    for c, i in find_mentions(t, CMDS, "command"):
        add_edge(src, f"cmd:{c}", "uses", "текст: советует /" + c, f"{rel}:{line_of(t, i)}", "text-mention")

# ---------------------------------------------------------------- rules (common, always loaded once installed)
rules_dir = os.path.join(ROOT, "rules", "common")
for f in sorted(os.listdir(rules_dir)):
    if not f.endswith(".md"):
        continue
    rel = f"rules/common/{f}"
    t = rd(rel)
    rid = add_node(f"rule:common/{f[:-3]}", "rule", f"rules/common/{f}", "rules",
                   short(re.sub(r"^#.*\n", "", t, count=1)[:400]), rel, True, "skills")
    for a, i in find_mentions(t, AGENTS, "agent"):
        add_edge(rid, f"agent:{a}", "configures", "правило упоминает агента", f"{rel}:{line_of(t, i)}", "text-mention")
    for s, i in find_mentions(t, SKILLS, "skill"):
        referenced_skills.setdefault(s, f"{rel}:{line_of(t, i)}")
        add_edge(rid, f"skill:{s}", "configures", "правило упоминает скил", f"{rel}:{line_of(t, i)}", "text-mention")
    for c, i in find_mentions(t, CMDS, "command"):
        add_edge(rid, f"cmd:{c}", "configures", "правило советует /" + c, f"{rel}:{line_of(t, i)}", "text-mention")

# ---------------------------------------------------------------- hooks
hooks_rel = "hooks/hooks.json"
hooks_text = rd(hooks_rel)
hooks_json = json.loads(hooks_text)
meta = json.loads(rd("hooks/hooks.metadata.json"))["entries"]

STORAGE = {
    # id: (label, summary)
    "file:session-data": ("~/.claude/session-data/*.tmp", "Сводки сессий (задачи, файлы, инструменты, LLM-сводка)"),
    "file:metrics-costs": ("~/.claude/metrics/costs.jsonl", "Журнал стоимости/токенов по сессиям"),
    "file:metrics-tool-usage": ("~/.claude/metrics/tool-usage.jsonl", "Журнал вызовов инструментов (для ECC2)"),
    "file:bash-log": ("~/.claude/bash-commands.log", "Журнал Bash-команд (аудит)"),
    "file:cost-log": ("~/.claude/cost-tracker.log", "Журнал Bash-команд (cost)"),
    "file:skill-runs": ("~/.claude/state/skill-runs.jsonl", "Запуски скилов (имя, версия, исход)"),
    "file:homunculus": ("~/.local/share/ecc-homunculus/", "Наблюдения и инстинкты continuous-learning-v2"),
    "file:learned-skills": ("~/.claude/skills/learned/", "Выученные скилы (/learn, evaluate-session)"),
    "file:mcp-health": ("~/.claude/mcp-health-cache.json", "Кэш здоровья MCP-серверов"),
    "file:plan-canvas": ("~/.claude/plan-canvas/sessions.json", "Сессии Plan Canvas и отзывы из браузера"),
    "file:tmp-metrics": ("$TMPDIR/ecc-metrics-<session>.json", "Агрегат сессии для статуслайна и монитора контекста"),
    "file:edit-accumulator": ("$TMPDIR (список правленых JS/TS)", "Накопитель путей для пакетного format/typecheck"),
    "file:state-store": ("ECC state store (governance_events)", "События governance (секреты, нарушения)"),
    "file:transcript": ("Транскрипт Claude Code (transcript_path)", "JSONL-транскрипт текущей сессии (читается хуками)"),
    "file:hookify-rules": (".claude/hookify.*.local.md (проект)", "Локальные правила Hookify"),
    "file:project-files": ("Файлы проекта", "Код, который правят/форматируют хуки"),
    "file:gateguard-metrics": ("~/.gateguard/ (state + metrics.jsonl)", "Состояние GateGuard (какие файлы уже проверены) и события-метрики с кодами причин; GATEGUARD_STATE_DIR"),
}


def storage(fid):
    lbl, summ = STORAGE[fid]
    return add_node(fid, "file", lbl, "storage", summ, "", False, "storage")


add_node("cli:claude-p", "cli", "claude -p (вложенный вызов)", "child-process",
         "Дочерний процесс Claude Code CLI: отправляет промпт в Anthropic от имени пользователя", "scripts/lib/llm-summary.js", True, "hooks")
add_node("cli:observe-sh", "cli", "observe.sh", "child-process",
         "Bash-скрипт continuous-learning-v2: пишет наблюдения инструментов", "skills/continuous-learning-v2/hooks/observe.sh", True, "hooks")
add_node("cli:observer-loop", "cli", "observer-loop.sh (фон)", "child-process",
         "Фоновый наблюдатель: раз в N минут запускает claude --model haiku (выключен по умолчанию)",
         "skills/continuous-learning-v2/agents/observer-loop.sh", False, "hooks")
add_node("cli:osascript", "cli", "osascript / iTerm2", "child-process", "Системные уведомления macOS",
         "scripts/hooks/desktop-notify.js", True, "hooks")
add_node("cli:formatters", "cli", "biome/prettier/tsc/ruff/gofmt", "child-process",
         "Внешние форматтеры и тайпчекеры проекта", "scripts/hooks/quality-gate.js", True, "hooks")

hook_ids = {}


def hook_node(hid, script, desc, profiles, event, line, extra=""):
    nid = f"hook:{hid}"
    add_node(nid, "hook", hid, "hook:" + event, short(desc + (f" [профили: {profiles}]" if profiles else "") + extra),
             script, True, "hooks")
    hook_ids[hid] = (nid, script)
    return nid


ev_lines = {}
for ev in hooks_json["hooks"]:
    ev_lines[ev] = line_of(hooks_text, hooks_text.find(f'"{ev}"'))
    add_node(f"event:{ev}", "event", ev, "event", f"Событие Claude Code {ev}", hooks_rel, True, "hooks")
    add_edge(PLUGIN, f"event:{ev}", "configures", "регистрирует хуки события", f"{hooks_rel}:{ev_lines[ev]}", "explicit")

# locate each hook entry's line by scanning commands in order
cursor = 0
for ev, arr in hooks_json["hooks"].items():
    for k, entry in enumerate(arr):
        mdesc = (meta.get(ev) or [{}] * (k + 1))[k] if k < len(meta.get(ev, [])) else {}
        for h in entry.get("hooks", []):
            cmd = h.get("command", "")
            pos = hooks_text.find('"command"', cursor)
            cursor = pos + 1
            line = line_of(hooks_text, pos)
            m = re.search(r'run-with-flags\.js\s+(\S+)\s+(scripts/hooks/[\w.-]+)\s+([\w,]+)', cmd)
            m2 = re.search(r'"\s+(\S+:\S+)\s+(scripts/hooks/[\w.-]+)\s+([\w,]+)', cmd)
            if m or m2:
                hid, script, prof = (m or m2).groups()
            elif "pre-bash-dispatcher" in cmd:
                hid, script, prof = "pre:bash:dispatcher", "scripts/hooks/pre-bash-dispatcher.js", ""
            elif "session-start-bootstrap" in cmd:
                hid, script, prof = "session:start", "scripts/hooks/session-start-bootstrap.js", "minimal,standard,strict"
            elif "posttooluse-dispatcher" in cmd:
                mode = "sync" if cmd.rstrip().endswith("sync") and not cmd.rstrip().endswith("async") else "async"
                hid, script, prof = f"post:dispatcher:{mode}", "scripts/hooks/posttooluse-dispatcher.js", ""
            else:
                continue
            desc = mdesc.get("description", "") if isinstance(mdesc, dict) else ""
            extra = f"; matcher={entry.get('matcher')}" if entry.get("matcher") else ""
            if h.get("async"):
                extra += "; async"
            nid = hook_node(hid, script, desc or hid, prof, ev, line, extra)
            add_edge(f"event:{ev}", nid, "triggers",
                     f"matcher {entry.get('matcher') or '*'}", f"{hooks_rel}:{line}", "explicit")

# dispatcher sub-hooks (explicit: tables in code)
for disp_rel, parent_ids, table_re in [
    ("scripts/hooks/bash-hook-dispatcher.js", ["pre:bash:dispatcher"], r"id:\s*'((?:pre|post):bash:[\w-]+)'"),
    ("scripts/hooks/posttooluse-dispatcher.js", ["post:dispatcher:sync", "post:dispatcher:async"],
     r"id:\s*'(post:[\w:-]+)'"),
]:
    t = rd(disp_rel)
    for m in re.finditer(table_re, t):
        sid = m.group(1)
        line = line_of(t, m.start())
        seg = t[m.start(): m.start() + 300]
        sm = re.search(r"script:\s*'(scripts/hooks/[\w.-]+)'", seg)
        pm = re.search(r"profiles:\s*'([\w,]+)'", seg)
        script = sm.group(1) if sm else ""
        if not script:
            # bash table: map id -> require() of run function
            fn = re.search(r"run:\s*rawInput\s*=>\s*(\w+)\(", seg)
            if fn:
                rq = re.search(r"run:\s*" + fn.group(1) + r"\s*\}\s*=\s*require\('\./([\w.-]+)'\)", t)
                if rq:
                    script = f"scripts/hooks/{rq.group(1)}.js"
        if sid.startswith("post:bash:") and "posttooluse" in disp_rel:
            continue
        prof = pm.group(1) if pm else ("standard,strict (по умолчанию)" if not pm else "")
        nid = f"hook:{sid}"
        add_node(nid, "hook", sid, "hook:sub", short(f"Под-хук диспетчера; профили: {prof}"), script, True, "hooks")
        hook_ids.setdefault(sid, (nid, script))
        if "posttooluse" in disp_rel:
            # sync vs async table: SYNC table appears first in the file
            parent = "post:dispatcher:sync" if m.start() < t.find("const ASYNC_HOOKS") else "post:dispatcher:async"
            parent_ids_use = [parent]
        else:
            parent_ids_use = parent_ids
        for p in parent_ids_use:
            if "bash-hook" in disp_rel and sid.startswith("post:bash:"):
                continue  # post-bash table is run from the PostToolUse async dispatcher (below)
            add_edge(f"hook:{p}", nid, "spawns", "вызывает в процессе (dispatcher table)", f"{disp_rel}:{line}", "explicit")
# post-bash sub-hooks run from the posttooluse dispatcher via bash-hook-dispatcher
bt = rd("scripts/hooks/bash-hook-dispatcher.js")
for m in re.finditer(r"id:\s*'(post:bash:[\w-]+)'", bt):
    add_edge("hook:post:dispatcher:async", f"hook:{m.group(1)}", "spawns", "через runPostBash (matcher Bash, async)",
             f"scripts/hooks/posttooluse-dispatcher.js:{line_of(rd('scripts/hooks/posttooluse-dispatcher.js'), rd('scripts/hooks/posttooluse-dispatcher.js').find('runPostBash'))}",
             "explicit")
# session-start bootstrap -> session-start.js
sbt = rd("scripts/hooks/session-start-bootstrap.js")
i = sbt.find("scripts/hooks/session-start.js")
add_node("hook:session:start:loader", "hook", "session-start.js", "hook:SessionStart",
         "Загружает последнюю сводку сессии, список инстинктов и выученных скилов в контекст", "scripts/hooks/session-start.js", True, "hooks")
hook_ids["session:start:loader"] = ("hook:session:start:loader", "scripts/hooks/session-start.js")
add_edge("hook:session:start", "hook:session:start:loader", "spawns", "spawnSync node session-start.js",
         f"scripts/hooks/session-start-bootstrap.js:{line_of(sbt, i)}", "explicit")

# ------------- hook -> storage / child process edges (scan code; explicit if literal, inferred if helper)
HELPER_MAP = [
    (r"getSessionsDir\(\)", "file:session-data", "inferred", "getSessionsDir() -> ~/.claude/session-data"),
    (r"getLearnedSkillsDir\(\)", "file:learned-skills", "inferred", "getLearnedSkillsDir() -> ~/.claude/skills/learned"),
    (r"getHomunculusDir\(\)", "file:homunculus", "inferred", "getHomunculusDir() -> ecc-homunculus"),
    (r"'costs\.jsonl'|costs\.jsonl", "file:metrics-costs", "explicit", "литерал costs.jsonl"),
    (r"tool-usage\.jsonl|METRICS_FILE_NAME", "file:metrics-tool-usage", "explicit", "литерал tool-usage.jsonl"),
    (r"'bash-commands\.log'", "file:bash-log", "explicit", "литерал bash-commands.log"),
    (r"'cost-tracker\.log'", "file:cost-log", "explicit", "литерал cost-tracker.log"),
    (r"mcp-health-cache\.json", "file:mcp-health", "explicit", "литерал mcp-health-cache.json"),
    (r"'sessions\.json'", "file:plan-canvas", "explicit", "литерал sessions.json (plan-canvas)"),
    (r"ecc-metrics-", "file:tmp-metrics", "explicit", "литерал ecc-metrics-<session>"),
    (r"transcript_path|transcriptPath", "file:transcript", "explicit", "читает transcript_path из stdin"),
    (r"governance_events|appendGovernance|recordGovernance", "file:state-store", "explicit", "пишет governance_events"),
    (r"hookify\.|loadHookifyRules|\.local\.md", "file:hookify-rules", "explicit", "читает правила Hookify"),
    (r"(?i)accumulat|ecc-edited-", "file:edit-accumulator", "explicit", "накопитель путей $TMPDIR/ecc-edited-<session>.txt"),
    (r"skill-runs|recordSkillExecution", "file:skill-runs", "inferred", "через skill-evolution/tracker.js -> ~/.claude/state/skill-runs.jsonl"),
    (r"appendMetrics\(", "file:gateguard-metrics", "inferred", "gateguard-metrics.appendMetrics -> metrics.jsonl"),
]
READ_ONLY = {"file:transcript", "file:hookify-rules"}
for hid, (nid, script) in list(hook_ids.items()):
    if not script or not os.path.isfile(os.path.join(ROOT, script)):
        continue
    if script.endswith(("dispatcher.js", "bootstrap.js")):
        continue
    t = rd(script)
    for pat, fid, conf, why in HELPER_MAP:
        m = re.search(pat, t)
        if not m:
            continue
        if fid == "file:edit-accumulator" and "accumulator" not in script and "stop-format" not in script:
            continue
        storage(fid)
        reads = fid in READ_ONLY or (fid == "file:edit-accumulator" and "stop-format" in script) \
            or (fid == "file:tmp-metrics" and "context-monitor" in script) \
            or (fid == "file:session-data" and "session-start" in script) \
            or (fid == "file:learned-skills" and "session-start" in script) \
            or (fid == "file:homunculus" and "session-start" in script) \
            or (fid == "file:metrics-costs" and "metrics-bridge" in script)
        kind = "reads" if reads else "writes"
        if fid == "file:learned-skills" and "evaluate-session" in script:
            kind, why = "uses", "только печатает подсказку с путём; сам файлы не пишет"
        if fid == "file:bash-log" and hid.endswith("-cost") or fid == "file:cost-log" and hid.endswith("-audit"):
            continue
        add_edge(nid, fid, kind, why, f"{script}:{line_of(t, m.start())}", conf)
    if re.search(r"generateSessionSummary\(", t):
        lt = rd("scripts/lib/llm-summary.js")
        add_edge(nid, "cli:claude-p", "spawns",
                 "claude --model ${ECC_LLM_SUMMARY_MODEL:-haiku} -p <последние ходы транскрипта>",
                 f"scripts/lib/llm-summary.js:{line_of(lt, lt.find(chr(39) + 'claude' + chr(39)))}", "explicit")
    if "observe.sh" in t or "OBSERVE_RELATIVE_PATH" in t:
        add_edge(nid, "cli:observe-sh", "spawns", "spawnSync bash observe.sh <phase>",
                 f"{script}:{line_of(t, t.find('spawnSync(shell'))}", "explicit")
    if "osascript" in t:
        add_edge(nid, "cli:osascript", "spawns", "spawnSync osascript", f"{script}:{line_of(t, t.find('osascript'))}", "explicit")
    if "auto-tmux-dev" in script:
        add_node("cli:tmux", "cli", "tmux", "child-process", "Запуск dev-сервера в фоновой tmux-сессии", script, True, "hooks")
        add_edge(nid, "cli:tmux", "spawns", "переписывает команду dev-сервера в tmux new-session", f"{script}:{line_of(t, t.find('tmux new-session'))}", "explicit")
    if re.search(r"biome|prettier|tsc|ruff|gofmt", t) and re.search(r"spawn|exec", t) and "config-protection" not in script:
        m = re.search(r"biome|prettier|ruff|gofmt|tsc", t)
        add_edge(nid, "cli:formatters", "spawns", "запускает форматтер/тайпчекер", f"{script}:{line_of(t, m.start())}", "explicit")
        storage("file:project-files")
        if re.search(r"--write|format", t):
            add_edge(nid, "file:project-files", "writes", "форматирует правленые файлы на месте", f"{script}:{line_of(t, m.start())}", "inferred")
    if hid.startswith(("pre:edit-write:gateguard", "pre:bash:gateguard", "pre:powershell:gateguard", "pre:config-protection", "pre:bash:block-no-verify")):
        storage("file:project-files")
        add_edge(nid, "file:project-files", "reads", "может заблокировать правку/команду (deny)", f"{script}:1", "inferred")

# observe.sh -> homunculus; observer loop -> claude
ot = rd("skills/continuous-learning-v2/hooks/observe.sh")
storage("file:homunculus")
add_edge("cli:observe-sh", "file:homunculus", "writes", "observations.jsonl (проект)",
         f"skills/continuous-learning-v2/hooks/observe.sh:{line_of(ot, ot.find('OBSERVATIONS_FILE='))}", "explicit")
ol = rd("skills/continuous-learning-v2/agents/observer-loop.sh")
add_edge("cli:observer-loop", "file:homunculus", "reads", "читает observations, пишет instincts",
         "skills/continuous-learning-v2/agents/observer-loop.sh:1", "inferred")
add_edge("cli:observer-loop", "cli:claude-p", "spawns", "claude --model ${ECC_OBSERVER_MODEL:-haiku} --print",
         f"skills/continuous-learning-v2/agents/observer-loop.sh:{line_of(ol, ol.find('claude --model'))}", "explicit")
storage("file:session-data")
storage("file:transcript")
add_edge("cli:claude-p", "file:transcript", "reads", "получает до N последних ходов транскрипта в промпте",
         "scripts/lib/llm-summary.js:37", "explicit")

# ---------------------------------------------------------------- command -> storage / cli mentions
CMD_STORAGE = [
    (r"session-data", "file:session-data"),
    (r"costs\.jsonl|cost-tracker", "file:metrics-costs"),
    (r"skill-runs", "file:skill-runs"),
    (r"homunculus|instinct-cli\.py|instincts?/|[Ii]nstincts", "file:homunculus"),
    (r"skills/learned", "file:learned-skills"),
    (r"plan-canvas", "file:plan-canvas"),
    (r"hookify\.[\w*-]*\.local\.md|\.claude/hookify", "file:hookify-rules"),
]
for name, (rel, t, fm) in list(cmd_meta.items()) + [(n, v) for n, v in agent_meta.items()]:
    src = f"cmd:{name}" if rel.startswith("commands/") else f"agent:{name}"
    for pat, fid in CMD_STORAGE:
        m = re.search(pat, t)
        if not m:
            continue
        win = t[max(0, m.start() - 160): m.end() + 60].lower()
        if re.search(r"save|write|creat|append|export|persist|stor|import|promot|prune|delet|record", win):
            kind = "writes"
        elif re.search(r"load|read|list|show|resum|status|report|inspect|scan|analy", win):
            kind = "reads"
        else:
            kind = "uses"
        storage(fid)
        add_edge(src, fid, kind, "текст: путь/хранилище", f"{rel}:{line_of(t, m.start())}", "inferred")

# CLI bins from package.json and scripts referenced by commands
pkg = json.loads(rd("package.json"))
pk_text = rd("package.json")
for b, path in pkg.get("bin", {}).items():
    add_node(f"cli:{b}", "cli", b, "cli", f"npm bin -> {path}", path, False, "user")
    add_edge(USER, f"cli:{b}", "invokes", "вручную в терминале", f"package.json:{line_of(pk_text, pk_text.find(chr(34) + b + chr(34)))}", "explicit")
for name, (rel, t, fm) in cmd_meta.items():
    for m in re.finditer(r"(?:scripts|skills/[\w-]+/scripts)/[\w/.-]+\.(?:js|mjs|py|sh)", t):
        p = m.group(0)
        nid = f"cli:{p}"
        add_node(nid, "cli", os.path.basename(p), "script", "Скрипт ECC, запускаемый командой", p, False, "hooks")
        add_edge(f"cmd:{name}", nid, "spawns", "команда велит запустить скрипт", f"{rel}:{line_of(t, m.start())}", "text-mention")
    for b in pkg.get("bin", {}):
        m = re.search(r"(?<![\w-])" + re.escape(b) + r"(?![\w-])", t)
        if m and b != "ecc":
            add_edge(f"cmd:{name}", f"cli:{b}", "spawns", "команда использует CLI", f"{rel}:{line_of(t, m.start())}", "text-mention")
    if re.search(r"(?<![\w-])codex(?![\w-])", t, re.I):
        add_node("cli:codex", "cli", "codex (внешний CLI)", "external", "OpenAI Codex CLI — сторонний провайдер (код уходит в OpenAI)", "", False, "hooks")
        m = re.search(r"codex", t, re.I)
        add_edge(f"cmd:{name}", "cli:codex", "spawns", "внешний провайдер", f"{rel}:{line_of(t, m.start())}", "text-mention")

# ---------------------------------------------------------------- MCP catalog (not installed by plugin)
mt = rd("mcp-configs/mcp-servers.json")
mcp = json.loads(mt)
mcp = mcp.get("mcpServers", mcp)
mcp_names = list(mcp.keys())
all_texts = [(f"cmd:{n}", v[0], v[1]) for n, v in cmd_meta.items()] + \
            [(f"agent:{n}", v[0], v[1]) for n, v in agent_meta.items()]
for src, rel, t in all_texts:
    for sname in mcp_names:
        pat = r"mcp__" + re.escape(sname) + r"|" + re.escape(sname) + r"\s+MCP|MCP[^\n]{0,30}\b" + re.escape(sname) + r"\b"
        m = re.search(pat, t, re.I)
        if m:
            add_node(f"mcp:{sname}", "mcp", sname, "mcp-catalog",
                     "Сервер из каталога mcp-configs/mcp-servers.json (плагином не ставится)", "mcp-configs/mcp-servers.json", False, "storage")
            add_edge(src, f"mcp:{sname}", "uses", "текст: MCP", f"{rel}:{line_of(t, m.start())}", "text-mention")

# ---------------------------------------------------------------- skills (only referenced ones, cap)
budget = MAX_NODES - len(nodes)
ranked = sorted(referenced_skills.keys(), key=lambda s: -sum(1 for e in edges if e["to"] == f"skill:{s}"))
kept = set(ranked[:max(0, budget)])
dropped_skills = ranked[max(0, budget):]
# hook scripts that point at skills (e.g. observe-runner -> continuous-learning-v2)
hook_skill_refs = []
for hid, (nid, script) in hook_ids.items():
    if script and os.path.isfile(os.path.join(ROOT, script)):
        t = rd(script)
        for m in re.finditer(r"skills['\",\s/]+([a-z0-9][a-z0-9-]+)", t):
            if m.group(1) in skill_meta:
                hook_skill_refs.append((nid, m.group(1), f"{script}:{line_of(t, m.start())}"))
for _, sk, ev in hook_skill_refs:
    referenced_skills.setdefault(sk, ev)
    kept.add(sk)
# second degree: skills mentioned by already-kept skills, until the node cap
second = {}
for s0 in list(kept):
    t0 = skill_meta[s0][1]
    for s2, i in find_mentions(t0, [x for x in SKILLS if x not in kept], "skill"):
        second[s2] = second.get(s2, 0) + 1
room = MAX_NODES - len(nodes) - len(kept)
for s2 in sorted(second, key=lambda x: (-second[x], x))[:max(0, room)]:
    kept.add(s2)
second_degree_added = sorted(s for s in second if s in kept)
for s in kept:
    rel, t, fm = skill_meta[s]
    add_node(f"skill:{s}", "skill", s, group_for(s, fm.get("description")), short(fm.get("description")), rel, True, "skills")
edges[:] = [e for e in edges if not (e["to"].startswith("skill:") and e["to"][6:] not in kept)]
# skill -> agent / skill / command (only among kept nodes)
for s in sorted(kept):
    rel, t, fm = skill_meta[s]
    src = f"skill:{s}"
    for m in re.finditer(r'subagent_type[^\n]{0,6}?["`]([\w:-]+)["`]', t):
        a = m.group(1).split(":")[-1]
        if a in agent_meta:
            add_edge(src, f"agent:{a}", "spawns", "subagent_type", f"{rel}:{line_of(t, m.start())}", "explicit")
    for a, i in find_mentions(t, AGENTS, "agent"):
        lbl = "текст: " + ("велит вызвать агента" if directive(t, i, a) else "упоминает агента")
        add_edge(src, f"agent:{a}", "invokes", lbl, f"{rel}:{line_of(t, i)}", "text-mention")
    for s2, i in find_mentions(t, [x for x in kept if x != s], "skill"):
        add_edge(src, f"skill:{s2}", "loads", "текст: ссылается на скил", f"{rel}:{line_of(t, i)}", "text-mention")
    for c, i in find_mentions(t, CMDS, "command"):
        add_edge(src, f"cmd:{c}", "uses", "текст: ссылается на /" + c, f"{rel}:{line_of(t, i)}", "text-mention")

for nid, sk, ev in hook_skill_refs:
    add_edge(nid, f"skill:{sk}", "loads", "хук-скрипт ссылается на файлы скила", ev, "explicit")
# continuous-learning-v2 skill owns observe.sh
if "continuous-learning-v2" in kept:
    add_edge("skill:continuous-learning-v2", "cli:observe-sh", "configures", "скил содержит хук-скрипт",
             "skills/continuous-learning-v2/hooks/observe.sh:1", "explicit")
    add_edge("skill:continuous-learning-v2", "cli:observer-loop", "configures", "скил содержит фонового наблюдателя (enabled:false)",
             "skills/continuous-learning-v2/config.json:4", "explicit")

# drop edges whose endpoints are missing
edges[:] = [e for e in edges if e["from"] in nodes and e["to"] in nodes]

# github URLs for evidence
for e in edges:
    ev = e["evidence"]
    if ":" in ev:
        f, ln = ev.rsplit(":", 1)
        e["url"] = f"https://github.com/affaan-m/ECC/blob/{COMMIT}/{f}#L{ln}"

# ---------------------------------------------------------------- stats
from collections import Counter
deg = Counter()
for e in edges:
    deg[e["from"]] += 1
    deg[e["to"]] += 1
connected_cmds = {e["from"] for e in edges if e["from"].startswith("cmd:") and e["to"] != "user:owner" and not e["to"].startswith("user")}
stats = {
    "commit": COMMIT,
    "generator": "docs/ecc/2026-10-13/data/build_graph.py (python3 -I build_graph.py <ECC> graph.json)",
    "nodes": len(nodes),
    "edges": len(edges),
    "nodes_by_type": dict(Counter(n["type"] for n in nodes.values())),
    "edges_by_kind": dict(Counter(e["kind"] for e in edges)),
    "edges_by_confidence": dict(Counter(e["confidence"] for e in edges)),
    "commands_total": len(CMDS), "agents_total": len(AGENTS), "skills_total": len(SKILLS),
    "skills_in_graph": len(kept), "skills_referenced_but_dropped_by_cap": dropped_skills,
    "skills_second_degree_added": second_degree_added,
    "commands_with_outgoing_links": len(connected_cmds),
    "commands_with_frontmatter_agent": sorted(n for n, v in cmd_meta.items() if v[2].get("agent")),
    "agents_proactive": sorted(n for n, v in agent_meta.items() if nodes[f"agent:{n}"]["auto"]),
    "agents_never_referenced": sorted(a for a in AGENTS if not any(e["to"] == f"agent:{a}" for e in edges)),
    "top_hubs": [dict(id=k, degree=v) for k, v in deg.most_common(15)],
    "notes": [
        "Только у одной команды есть поле agent: в frontmatter (security-scan -> ecc:security-reviewer); остальные связи команда->агент взяты из текста.",
        "Для однословных имён (planner, architect, council, seo…) упоминание засчитывается только при контексте (бэктики, 'agent'/'skill' рядом, префикс ecc:).",
        "Узлы skill — только скилы, на которые ссылаются команды/агенты/правила; лимит узлов 400.",
        "MCP-узлы — из каталога mcp-configs/mcp-servers.json; плагин mcpServers пуст ({}), т.е. сам ничего не подключает.",
    ],
}
order = {"user": 0, "plugin": 1, "command": 2, "agent": 3, "skill": 4, "rule": 5, "event": 6, "hook": 7, "cli": 8, "mcp": 9, "file": 10}
out = {
    "nodes": sorted(nodes.values(), key=lambda n: (order.get(n["type"], 99), n["id"])),
    "edges": edges,
    "layers": ["user", "commands", "agents", "skills", "hooks", "storage"],
    "stats": stats,
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(json.dumps({k: stats[k] for k in ("nodes", "edges", "nodes_by_type", "edges_by_confidence", "skills_in_graph")}, ensure_ascii=False))
print("dropped:", len(dropped_skills), "never-referenced agents:", stats["agents_never_referenced"])
