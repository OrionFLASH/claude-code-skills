#!/usr/bin/env python3
"""Диспетчер заданий субагентов: очередь, зависимости, модели, параллелизм ≤ N, статус по волнам, прогноз объёма.

Диспетчер агентов НЕ запускает: вызовы Agent делает оркестратор. Скрипт выдаёт задания, готовые к запуску (зависимости
выполнены, свободен слот, пути выдачи не пересекаются с работающими), и принимает отметки о завершении. Состояние — в
<OUT>/build/agents.json (id, волна, бриф, модель план/факт, effort, зависимости, пути, бюджеты поиска и открытий план/факт,
токены, минуты, итог, попытки) — из него скрипт заполняет раздел 11 REPORT.md.

  dispatch.py <OUT> add --id G3 --brief build/briefs/registry-generator-G3.md [--wave 5-titles] [--phase 5]
                        [--kind titles | --model sonnet] [--effort high] [--deps G1,G2] [--paths data/x.json,…]
                        [--search 2] [--fetch 0] [--task "суть в 1–2 фразах для триажа"]
  dispatch.py <OUT> load tasks.json            список заданий теми же полями (id, brief, wave, kind|model, deps, paths …)
  dispatch.py <OUT> ready [--max N] [--start] [--json]
                                                готовые к запуску (≤ N − работающих; N — tools.max_parallel_agents, 5);
                                                --start — сразу отметить их «работает» и снять снимок волны (check_paths)
  dispatch.py <OUT> start ID [ID …]            отметить «работает» вручную
  dispatch.py <OUT> done ID [--tokens N] [--minutes M] [--model-actual X] [--result ok|rework|failed]
                        [--search N] [--fetch N] [--note "…"]
                                                итог агента (из уведомления о завершении); rework — задание снова в очереди
                                                (попытка сохраняется), failed — зависимые задания блокируются
  dispatch.py <OUT> close-wave W [--no-merge]  после волны: check_paths.py по брифам волны и merge_sources.py --keep-ids
                                                (если есть data/sources-*.json); итог — в agents.json → waves
  dispatch.py <OUT> status [--json]            таблица по волнам и сумма
  dispatch.py <OUT> report [--write]           таблица для раздела 11 REPORT.md (с учётом run-config disclosure);
                                                --write — в build/agents-report.md
  dispatch.py <OUT> triage W [--run <typesafe_triage.py> | --apply triage-result.json] [--confirmed]
                                                build/triage-<W>.json из очереди; --run — вызвать typesafe_triage.py --batch,
                                                --apply — взять готовый JSON; модель и effort записываются в задания волны
  dispatch.py <OUT> forecast [--depth D] [--parallel N] [--json] [--from-agents] [--fast]
                                                прогноз до «Начинаю?»: агенты, токены (по моделям), часы — по фазам;
                                                режим идеи — фазы C4…C8.5 (интеграция с платформой, право, прототип — по
                                                run-config); --fast — «быстрая концепция» (≈10 агентов, 2–3 ч, SM 10.7)
  dispatch.py <OUT> fast-plan [--write]         состав «быстрой концепции»: задания по волнам и что опускается;
                                                --write — build/tasks-fast.json (дальше dispatch.py <OUT> load …)
  dispatch.py <OUT> owners [--json]             общие пути: шаблоны выдачи, которые есть у двух и более заданий одной
                                                волны (два агента не пишут в один файл — назначьте владельца)

Политика агентов (FB-003) — run-config tools.agents {model_policy: triage | default | custom, effort_policy: explicit | none, note}:
effort выдаётся в `ready` только при effort_policy = explicit (нет поля tools.agents — как в 1.4: effort, если задан);
model_policy = triage — `ready` напоминает про `triage <волна>` для заданий без триажа, custom — печатает tools.agents.note,
default — модели по правилам скилла.
Новые брифы 1.5 (WP-G): вид и волна выводятся из имени брифа, если --kind/--model не заданы (research-integration →
integration/C4, research-datasources → datasources, research-ai → ai, research-owner-refs → owner_refs,
concept-ai-observability и concept-admin → module/C7, strategy-summary → summary/C7, prototype-core|shell|mode-*|regression →
prototype_core|prototype_shell|prototype_mode|prototype_regression/C8.5); прогноз режима идеи добавляет модули C4/C7 по
idea.facets (ai_role, data_sources_needed, owner_repos/owner_docs, admin_needed) и шаги C8.5 (ядро → оболочка → режимы × N →
регрессия). Агенты пишут в общий <OUT>:
isolation (worktree) не ставится никогда — build/triage-<волна>.json несёт "shared_out": true, а isolation из ответа
триажа снимается (FB-013).
Прогноз: таблица глубины (references/phases.md) × типовые затраты на задание; калибровка — два реальных прогона
(standard ≈ 27 агентов / 6,3 млн токенов / 6 ч при 5 параллельных; deep ≈ 50 / 11 млн / 4–5 ч); точность ±30 %.
Выключенные направления (scope.*=false, phases.gap_audit=false) из прогноза убираются.
Только стандартная библиотека.
"""
import argparse
import fnmatch
import json
import math
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

STATUSES = ("pending", "running", "done", "failed")
# тип задания → (модель по умолчанию — references/orchestration.md, тыс. токенов, минут)
KINDS = {
    "research": ("sonnet", 230, 25), "legal": ("opus", 300, 30), "cards": ("sonnet", 150, 15), "readers": ("sonnet", 150, 15),
    "ux": ("sonnet", 150, 20), "titles": ("sonnet", 60, 8), "details": ("sonnet", 180, 22), "audit": ("opus", 280, 30),
    "scorer": ("opus", 200, 20), "section": ("opus", 220, 28), "specs": ("opus", 250, 30), "experiments": ("opus", 200, 25),
    "plan": ("sonnet", 120, 15), "mockups": ("opus", 230, 30), "flows": ("opus", 140, 20), "refs": ("opus", 180, 25),
    "fixes": ("sonnet", 100, 15), "integration": ("opus", 280, 30), "canvas": ("opus", 180, 20), "design": ("opus", 200, 25),
    "prototype": ("opus", 300, 40),
    # 1.5.0 (WP-G): модули C4/C7, резюме, фаза C8.5 по шагам — references/orchestration.md, «Модель по умолчанию»
    "datasources": ("sonnet", 230, 25), "ai": ("opus", 260, 30), "owner_refs": ("opus", 180, 20), "module": ("opus", 200, 25),
    "summary": ("opus", 120, 15), "prototype_core": ("opus", 300, 40), "prototype_shell": ("opus", 260, 35),
    "prototype_mode": ("sonnet", 200, 30), "prototype_regression": ("sonnet", 220, 30),
}
# бриф → вид задания (для add без --kind; G7): новые брифы 1.5.0 и их волны
BRIEF_KINDS = {"research-integration": ("integration", "C4"), "research-datasources": ("datasources", "C4"), "research-ai": ("ai", "C4"),
               "research-owner-refs": ("owner_refs", "C4"), "concept-ai-observability": ("module", "C7"), "concept-admin": ("module", "C7"),
               "strategy-summary": ("summary", "C7"), "prototype-core": ("prototype_core", "C8.5"),
               "prototype-shell": ("prototype_shell", "C8.5"), "prototype-mode": ("prototype_mode", "C8.5"),
               "prototype-regression": ("prototype_regression", "C8.5")}
# порядок шагов C8.5: ядро → оболочка → режимы (параллельно, общих путей нет) → регрессия
PROTO_ORDER = ["prototype_core", "prototype_shell", "prototype_mode", "prototype_regression"]
KIND_TITLES = {"research": "сбор данных фазы 4", "legal": "правовой обзор", "cards": "карточки конкурентов", "readers": "инвентарь функций по папкам",
               "ux": "UX-разбор скриншотов", "titles": "реестр, проход 1", "details": "реестр, проход 2", "audit": "аудит пробелов",
               "scorer": "второй оценщик", "section": "разделы стратегии", "specs": "спецификации", "experiments": "эксперименты",
               "plan": "Гант и Kanban", "mockups": "макеты", "flows": "блок-схемы", "refs": "design-refs", "fixes": "правки по дефектам",
               "integration": "техническая интеграция с платформой", "canvas": "канвасы и SWOT", "design": "направления дизайна",
               "prototype": "рабочий прототип", "datasources": "источники данных и лицензии", "ai": "ИИ в продукте",
               "owner_refs": "референсы владельца", "module": "модули C7 (ИИ-наблюдаемость, администрирование)",
               "summary": "резюме (раздел 1)", "prototype_core": "прототип: ядро", "prototype_shell": "прототип: оболочка",
               "prototype_mode": "прототип: режим", "prototype_regression": "прототип: регрессия"}
# режим идеи (mode: concept): фазы C4…C8.5; аналоги/сообщества/запросы/события — research, право и интеграция — по run-config
CONCEPT_AGENTS = {
    "quick": {"C4": {"research": 2}, "C5": {"details": 3}, "C7": {"canvas": 1, "section": 2, "specs": 1, "experiments": 1},
              "C8": {"design": 1, "mockups": 1, "flows": 1}},
    "standard": {"C4": {"research": 4, "legal": 1, "cards": 1}, "C5": {"titles": 5, "details": 5}, "C5.5": {"audit": 1},
                 "C7": {"canvas": 1, "section": 4, "specs": 1, "experiments": 1}, "C8": {"design": 1, "mockups": 2, "flows": 1, "refs": 1}},
    "deep": {"C4": {"research": 4, "legal": 1, "cards": 2}, "C5": {"titles": 6, "details": 6}, "C5.5": {"audit": 1}, "C6": {"scorer": 1},
             "C7": {"canvas": 1, "section": 5, "specs": 2, "experiments": 1}, "C8": {"design": 1, "mockups": 3, "flows": 2, "refs": 2},
             "C9": {"fixes": 1}},
    "exhaustive": {"C4": {"research": 4, "legal": 1, "cards": 3}, "C5": {"titles": 8, "details": 8}, "C5.5": {"audit": 2}, "C6": {"scorer": 1},
                   "C7": {"canvas": 1, "section": 5, "specs": 3, "experiments": 2}, "C8": {"design": 1, "mockups": 4, "flows": 2, "refs": 3},
                   "C9": {"fixes": 2}},
}
# «быстрая концепция» (SM 10.7): ≈10 агентов, 2–3 часа; что опускается — FAST_SKIPPED
FAST_AGENTS = {"C4": {"research": 2}, "C5": {"details": 2}, "C7": {"section": 2, "experiments": 1}, "C8": {"mockups": 1}}
FAST_SKIPPED = ["второй проход реестра (titles) — один проход details с разведением тем через OTHER_TITLES",
                "отдельные агенты запросов и событий — свёрнуты в один бриф рынка (сообщества + спрос + события)",
                "карточки конкурентов по скриншотам — только снимки shoot_competitors.mjs",
                "аудит предпосылок C5.5 — оркестратор сам по gap-audit-facts.md (топ-15)",
                "канвасы — в части разделов; спеки — в брифе экспериментов (топ-3)",
                "design-refs, вторые схемы, второй оценщик, рабочий прототип",
                "направления дизайна — одно рекомендованное + вопрос владельцу, 4 макета"]
FAST_TASKS = [   # состав «быстрой концепции»: id, бриф, kind, волна, зависимости
    {"id": "A1", "brief": "build/briefs/concept-analogs.md", "kind": "research", "wave": "C4"},
    {"id": "M1", "brief": "build/briefs/research-communities.md", "kind": "research", "wave": "C4",
     "task": "рынок одним агентом: сообщества, спрос и события (быстрая концепция)"},
    {"id": "L1", "brief": "build/briefs/research-legal.md", "kind": "legal", "wave": "C4", "when": "legal"},
    {"id": "I1", "brief": "build/briefs/research-integration.md", "kind": "integration", "wave": "C4", "when": "platform"},
    {"id": "G1", "brief": "build/briefs/registry-generator-G1.md", "kind": "details", "wave": "C5", "deps": ["A1", "M1"]},
    {"id": "G2", "brief": "build/briefs/registry-generator-G2.md", "kind": "details", "wave": "C5", "deps": ["A1", "M1"]},
    {"id": "S1", "brief": "build/briefs/strategy-section-S1.md", "kind": "section", "wave": "C7", "deps": ["G1", "G2"]},
    {"id": "S2", "brief": "build/briefs/strategy-section-S2.md", "kind": "section", "wave": "C7", "deps": ["G1", "G2"]},
    {"id": "X1", "brief": "build/briefs/experiments.md", "kind": "experiments", "wave": "C7", "deps": ["G1", "G2"]},
    {"id": "D1", "brief": "build/briefs/concept-design.md", "kind": "mockups", "wave": "C8", "deps": ["G1", "G2"]},
]
# число заданий по фазам и глубине (references/phases.md → «Масштабирование по глубине»)
DEPTH_AGENTS = {
    "quick": {"4": {"research": 3, "cards": 1}, "5": {"details": 3},
              "7": {"section": 2, "specs": 1, "experiments": 1, "plan": 1}, "8": {"mockups": 1, "flows": 1}},
    "standard": {"4": {"research": 4, "legal": 1, "cards": 1}, "5": {"titles": 6, "details": 6}, "5.5": {"audit": 1},
                 "7": {"section": 4, "specs": 1, "experiments": 1, "plan": 1}, "8": {"mockups": 3, "flows": 1, "refs": 1}},
    "deep": {"1": {"readers": 2}, "2": {"ux": 1}, "4": {"research": 4, "legal": 1, "cards": 2}, "5": {"titles": 7, "details": 7},
             "5.5": {"audit": 1}, "6": {"scorer": 1}, "7": {"section": 5, "specs": 2, "experiments": 1, "plan": 1},
             "8": {"mockups": 4, "flows": 2, "refs": 2}, "9": {"fixes": 2}},
    "exhaustive": {"1": {"readers": 4}, "2": {"ux": 1}, "4": {"research": 4, "legal": 1, "cards": 3}, "5": {"titles": 9, "details": 9},
                   "5.5": {"audit": 2}, "6": {"scorer": 1}, "7": {"section": 5, "specs": 3, "experiments": 2, "plan": 1},
                   "8": {"mockups": 5, "flows": 2, "refs": 3}, "9": {"fixes": 2}},
}
TOKEN_MULT = {"quick": 0.8, "standard": 1.0, "deep": 1.15, "exhaustive": 1.3}
MINUTE_MULT = {"quick": 0.9, "standard": 1.0, "deep": 0.85, "exhaustive": 0.9}
ORCH = {"quick": (500, 90), "standard": (900, 150), "deep": (1600, 120), "exhaustive": (2200, 200)}   # оркестратор: тыс. токенов, минут
PHASE_ORDER = ["1", "2", "4", "5", "5.5", "6", "7", "8", "9"]
PROMPT = ("Прочитай и выполни бриф {brief} целиком. Пиши только в пути, перечисленные в разделе «Выдача». "
          "Последнее сообщение — отчёт по формату брифа.")


def now():
    return datetime.now().isoformat(timespec="seconds")


def load_cfg(out):
    try:
        return json.loads((out / "build" / "run-config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def state_path(out):
    return out / "build" / "agents.json"


def load_state(out):
    try:
        st = json.loads(state_path(out).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        st = {}
    st.setdefault("version", 1)
    st.setdefault("tasks", [])
    st.setdefault("waves", {})
    return st


def save_state(out, st):
    st["updated"] = now()
    state_path(out).parent.mkdir(parents=True, exist_ok=True)
    state_path(out).write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def max_parallel(cfg, override=None):
    if override:
        return max(1, int(override))
    t = cfg.get("tools") or {}
    if t.get("subagents") is False:
        return 1
    return max(1, int(t.get("max_parallel_agents") or 5))


def agents_policy(cfg):
    """run-config tools.agents → (model_policy | None, effort_policy | None). Нет поля — (None, None): поведение 1.4."""
    ag = (cfg.get("tools") or {}).get("agents")
    if not isinstance(ag, dict):
        return None, None
    mp = str(ag.get("model_policy") or "").strip().lower() or None
    ep = str(ag.get("effort_policy") or "").strip().lower() or None
    return mp, ep


def effort_out(cfg, effort):
    """effort для вызова Agent: только при effort_policy = explicit (FB-003); без политики — как задан (1.4)."""
    _mp, ep = agents_policy(cfg)
    if ep is None:
        return effort
    return effort if ep == "explicit" else None


def out_display(out):
    """<OUT> от корня репозитория (для промпта агенту без домашней папки)."""
    try:
        import check_paths
        repo = check_paths.repo_root(out)
        rel = check_paths.out_rel(out, repo)
    except Exception:                                # noqa: BLE001 — запасной вариант ниже
        rel = None
    return rel if rel else (rel if rel == "" else "<OUT>")


def brief_paths(out, brief):
    """Пути выдачи из раздела «Выдача» брифа (check_paths.brief_patterns)."""
    bp = out / brief if not Path(brief).is_absolute() else Path(brief)
    if not bp.is_file():
        return []
    try:
        import check_paths
        repo = check_paths.repo_root(out)
        return check_paths.brief_patterns(bp.read_text(encoding="utf-8"), check_paths.out_rel(out, repo))[0]
    except Exception:                                # noqa: BLE001
        return []


def brief_goal(out, brief):
    """Первая содержательная строка раздела «Цель» брифа — суть задания для триажа."""
    bp = out / brief
    try:
        text = bp.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r"^#+\s*Цель[^\n]*\n+(.+?)(?:\n\s*\n|\n#)", text, re.M | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:300] if m else ""


def split_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in str(v).split(",") if x.strip()]


def brief_kind(brief):
    """build/briefs/prototype-mode-pro.md → ("prototype_mode", "C8.5"); не новый бриф 1.5.0 → None."""
    stem = Path(str(brief or "")).stem
    for name in sorted(BRIEF_KINDS, key=len, reverse=True):
        if stem == name or stem.startswith(name + "-"):
            return BRIEF_KINDS[name]
    return None


def make_task(out, d):
    if not d.get("id"):
        raise ValueError("у задания нет id")
    kind = d.get("kind")
    if kind and kind not in KINDS:
        raise ValueError("неизвестный kind %s (есть: %s)" % (kind, ", ".join(KINDS)))
    brief = d.get("brief") or ""
    bk = brief_kind(brief)
    if not kind and not d.get("model") and bk:          # новые брифы 1.5.0: вид и волна по имени брифа (G7)
        kind = bk[0]
        if not d.get("wave") and not d.get("phase"):
            d = dict(d, wave=bk[1])
    model = d.get("model") or (KINDS[kind][0] if kind else "sonnet")
    paths = split_list(d.get("paths")) or (brief_paths(out, brief) if brief else [])
    return {"id": str(d["id"]), "wave": str(d.get("wave") or d.get("phase") or "1"), "phase": str(d.get("phase") or ""),
            "kind": kind, "brief": brief, "task": d.get("task") or (brief_goal(out, brief) if brief else ""),
            "model": model, "effort": d.get("effort"), "deps": split_list(d.get("deps")), "paths": paths,
            "budget": {"search": d.get("search"), "fetch": d.get("fetch")}, "actual": {"search": None, "fetch": None},
            "status": "pending", "model_actual": None, "tokens": None, "minutes": None, "result": None,
            "started": None, "finished": None, "attempts": [], "note": d.get("note") or "", "triage": None}


def add_tasks(out, items):
    st = load_state(out)
    ids = {t["id"] for t in st["tasks"]}
    added = []
    for d in items:
        t = make_task(out, d)
        if t["id"] in ids:
            raise ValueError("задание %s уже есть" % t["id"])
        st["tasks"].append(t)
        ids.add(t["id"])
        added.append(t["id"])
    unknown = sorted({dep for t in st["tasks"] for dep in t["deps"] if dep not in ids})
    save_state(out, st)
    return added, unknown


def overlap(p1, p2):
    return p1 == p2 or fnmatch.fnmatchcase(p1, p2) or fnmatch.fnmatchcase(p2, p1)


def shared_paths(st):
    """Общие пути выдачи у заданий одной волны (SM 6.3: параллельные агенты перезаписывали общие снимки) →
    [{"wave", "path", "tasks": [id…]}]."""
    res = []
    by_wave = {}
    for t in st["tasks"]:
        by_wave.setdefault(t["wave"], []).append(t)
    for w, ts in by_wave.items():
        for i, a in enumerate(ts):
            for b in ts[i + 1:]:
                for pa in a["paths"]:
                    for pb in b["paths"]:
                        if overlap(pa, pb):
                            res.append({"wave": w, "path": pa if pa == pb else "%s ~ %s" % (pa, pb), "tasks": [a["id"], b["id"]]})
    return res


def ready_tasks(st, limit):
    by_id = {t["id"]: t for t in st["tasks"]}
    running = [t for t in st["tasks"] if t["status"] == "running"]
    slots = max(0, limit - len(running))
    busy = [p for t in running for p in t["paths"]]
    res, blocked = [], []
    for t in st["tasks"]:
        if t["status"] != "pending":
            continue
        deps = [by_id.get(d) for d in t["deps"]]
        if any(d is None or d["status"] == "failed" for d in deps):
            blocked.append((t["id"], "зависимость не выполнена/нет: %s" % ", ".join(
                x for x in t["deps"] if by_id.get(x) is None or by_id[x]["status"] == "failed")))
            continue
        if any(d["status"] != "done" for d in deps):
            continue
        clash = [p for p in t["paths"] if any(overlap(p, b) for b in busy)]
        if clash:
            blocked.append((t["id"], "пути пересекаются с работающими: %s" % ", ".join(clash[:3])))
            continue
        if len(res) >= slots:
            continue
        res.append(t)
        busy += t["paths"]
    return res, blocked, slots


def mark_running(out, st, ids):
    started = []
    waves = set()
    for t in st["tasks"]:
        if t["id"] in ids and t["status"] in ("pending",):
            t["status"], t["started"] = "running", now()
            started.append(t["id"])
            waves.add(t["wave"])
    for w in waves:                                       # снимок волны для check_paths — один раз, перед первым запуском
        snap = out / "build" / "waves" / ("%s.json" % w)
        if not snap.exists():
            try:
                import check_paths
                check_paths.start(out, w)
                st["waves"].setdefault(w, {})["snapshot"] = "build/waves/%s.json" % w
            except Exception as e:                        # noqa: BLE001
                st["waves"].setdefault(w, {})["snapshot_error"] = str(e)[:120]
    return started


def minutes_between(a, b):
    try:
        return round((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 60, 1)
    except (TypeError, ValueError):
        return None


def mark_done(out, st, tid, a):
    t = next((x for x in st["tasks"] if x["id"] == tid), None)
    if t is None:
        raise ValueError("нет задания %s" % tid)
    fin = now()
    minutes = a.minutes if a.minutes is not None else (minutes_between(t["started"], fin) if t["started"] else None)
    attempt = {"started": t["started"], "finished": fin, "tokens": a.tokens, "minutes": minutes, "model_actual": a.model_actual or t["model"],
               "result": a.result, "search": a.search, "fetch": a.fetch, "note": a.note or ""}
    t["attempts"].append(attempt)
    t["tokens"] = sum(x["tokens"] or 0 for x in t["attempts"]) or None
    t["minutes"] = round(sum(x["minutes"] or 0 for x in t["attempts"]), 1) or None
    t["model_actual"] = attempt["model_actual"]
    t["actual"] = {"search": sum(x["search"] or 0 for x in t["attempts"]) if any(x["search"] is not None for x in t["attempts"]) else None,
                   "fetch": sum(x["fetch"] or 0 for x in t["attempts"]) if any(x["fetch"] is not None for x in t["attempts"]) else None}
    t["result"] = a.result
    if a.note:
        t["note"] = a.note
    if a.result == "rework":
        t["status"], t["started"], t["finished"] = "pending", None, None
    else:
        t["status"], t["finished"] = ("failed" if a.result == "failed" else "done"), fin
    wave_tasks = [x for x in st["tasks"] if x["wave"] == t["wave"]]
    return t, all(x["status"] in ("done", "failed") for x in wave_tasks)


def close_wave(out, st, wave, merge=True):
    tasks = [t for t in st["tasks"] if t["wave"] == wave]
    if not tasks:
        raise ValueError("нет заданий волны %s" % wave)
    info = st["waves"].setdefault(wave, {})
    briefs = [t["brief"] for t in tasks if t["brief"] and (out / t["brief"]).is_file()]
    if (out / "build" / "waves" / ("%s.json" % wave)).is_file() and briefs:
        r = subprocess.run([sys.executable, str(HERE / "check_paths.py"), str(out), "--wave", wave, "--briefs", *briefs, "--json"],
                           capture_output=True, text=True, timeout=300)
        try:
            rep = json.loads(r.stdout)
            info["check_paths"] = {"code": r.returncode, "violations": rep.get("violations", [])}
        except json.JSONDecodeError:
            info["check_paths"] = {"code": r.returncode, "error": (r.stderr or r.stdout).strip()[:200]}
    else:
        info["check_paths"] = {"code": None, "skipped": "нет снимка волны или брифов (снимок снимает ready --start)"}
    if merge and list((out / "data").glob("sources-*.json")):
        r = subprocess.run([sys.executable, str(HERE / "merge_sources.py"), str(out), "--keep-ids"], capture_output=True, text=True, timeout=600)
        info["merge_sources"] = {"code": r.returncode, "summary": (r.stdout.strip().splitlines() or [""])[-1][:200]}
    else:
        info["merge_sources"] = {"code": None, "skipped": "--no-merge" if not merge else "нет data/sources-*.json"}
    info["closed"] = now()
    return info


# ---------------------------------------------------------------- отчёт

def fmt_tokens(n):
    if not n:
        return "—"
    return "%.2f млн" % (n / 1e6) if n >= 100000 else "%d тыс." % round(n / 1000)


def report_md(st, cfg):
    disclosure = (cfg.get("disclosure") or "full").lower()
    tasks = st["tasks"]
    tok = sum(t["tokens"] or 0 for t in tasks)
    mins = sum(t["minutes"] or 0 for t in tasks)
    if disclosure == "summary":
        return ["Подготовлено с помощью ИИ-инструментов (детали — в build/agents.json)."]
    L = []
    if disclosure == "none":
        L.append("<!-- disclosure: none — этот раздел только для build/, в REPORT.md не переносится -->")
    L += ["| Волна / агент | Модель (план → факт) | Токены | Минуты | Поиск / открытия (факт из плана) | Итог |", "|---|---|---|---|---|---|"]
    for t in tasks:
        b, f = t.get("budget") or {}, t.get("actual") or {}
        bud = "%s / %s" % ("%s из %s" % (f.get("search") if f.get("search") is not None else "—", b.get("search") if b.get("search") is not None else "—"),
                           "%s из %s" % (f.get("fetch") if f.get("fetch") is not None else "—", b.get("fetch") if b.get("fetch") is not None else "—"))
        model = t["model"] + ((" → " + t["model_actual"]) if t.get("model_actual") and t["model_actual"] != t["model"] else "")
        res = {"done": t.get("result") or "ok", "failed": "не выполнено", "running": "работает", "pending": "в очереди"}.get(t["status"], t["status"])
        if len(t.get("attempts") or []) > 1:
            res += " (попыток: %d)" % len(t["attempts"])
        L.append("| %s / %s | %s | %s | %s | %s | %s |" % (t["wave"], t["id"], model, fmt_tokens(t["tokens"]),
                                                       t["minutes"] if t["minutes"] is not None else "—", bud, res))
    sb = sum((t.get("budget") or {}).get("search") or 0 for t in tasks)
    sf = sum((t.get("actual") or {}).get("search") or 0 for t in tasks)
    L += ["", "Всего агентов: %d (выполнено %d, не выполнено %d); токены: %s; минут агентов: %s. Веб-поиск агентов: %s из %s запланированных." % (
        len(tasks), sum(1 for t in tasks if t["status"] == "done"), sum(1 for t in tasks if t["status"] == "failed"), fmt_tokens(tok),
        round(mins), sf or "—", sb or "—")]
    waves = wave_totals(st)                              # учёт токенов по волнам (SM 6.3, 12 п. 19)
    if waves:
        L += ["", "| Волна | Агентов | Токены | Минут агентов | Модели (факт) |", "|---|---|---|---|---|"]
        for w in waves:
            L.append("| %s | %d | %s | %s | %s |" % (w["wave"], w["agents"], fmt_tokens(w["tokens"]), round(w["minutes"]) if w["minutes"] else "—",
                                                    ", ".join("%s × %d" % kv for kv in sorted(w["models"].items())) or "—"))
    no_tok = [t["id"] for t in tasks if t["status"] == "done" and not t.get("tokens")]
    if no_tok:
        L.append("Без записанных токенов: %s (dispatch.py <OUT> done <id> --tokens N — из уведомления о завершении)." % ", ".join(no_tok))
    return L


def wave_totals(st):
    """Сумма по волнам: агенты, токены, минуты, фактические модели."""
    res = []
    for t in st["tasks"]:
        w = next((x for x in res if x["wave"] == t["wave"]), None)
        if w is None:
            w = {"wave": t["wave"], "agents": 0, "tokens": 0, "minutes": 0.0, "models": {}}
            res.append(w)
        w["agents"] += 1
        w["tokens"] += t.get("tokens") or 0
        w["minutes"] += t.get("minutes") or 0
        m = t.get("model_actual") or t.get("model")
        if m:
            w["models"][m] = w["models"].get(m, 0) + 1
    return res


def status_lines(st, limit):
    L = []
    waves = []
    for t in st["tasks"]:
        if t["wave"] not in waves:
            waves.append(t["wave"])
    for w in waves:
        ts = [t for t in st["tasks"] if t["wave"] == w]
        cnt = {s: sum(1 for t in ts if t["status"] == s) for s in STATUSES}
        closed = (st["waves"].get(w) or {}).get("closed")
        L.append("Волна %s: %d заданий — готово %d, работает %d, в очереди %d, не выполнено %d%s" % (
            w, len(ts), cnt["done"], cnt["running"], cnt["pending"], cnt["failed"], " · закрыта" if closed else ""))
        for t in ts:
            L.append("  %-10s %-8s %-7s %-12s %s" % (t["id"], t["status"], t["model_actual"] or t["model"], fmt_tokens(t["tokens"]),
                                                   ("%s мин" % t["minutes"]) if t["minutes"] is not None else ""))
    tok = sum(t["tokens"] or 0 for t in st["tasks"])
    L.append("Итого: заданий %d, токены %s, лимит параллельных %d" % (len(st["tasks"]), fmt_tokens(tok), limit))
    return L


# ---------------------------------------------------------------- прогноз

def scoped_agents(depth, cfg):
    """Задания по фазам с учётом выключенных направлений."""
    plan = {ph: dict(kinds) for ph, kinds in DEPTH_AGENTS[depth].items()}
    sc = cfg.get("scope") or {}
    ph4 = plan.get("4", {})
    if "research" in ph4:
        enabled = sum(1 for k in ("competitors", "communities", "keywords", "events") if sc.get(k, True) is not False)
        ph4["research"] = min(ph4["research"], enabled)
    if sc.get("legal") is False:
        ph4.pop("legal", None)
    if sc.get("competitors") is False:
        ph4.pop("cards", None)
    if sc.get("app_run") is False:
        plan.get("2", {}).pop("ux", None)
    if (cfg.get("phases") or {}).get("gap_audit") is False:
        plan.pop("5.5", None)
    p8 = plan.get("8", {})
    if sc.get("design_mockups") is False:
        p8.pop("mockups", None)
    if sc.get("design_refs") is False:
        p8.pop("refs", None)
    if sc.get("experiments") == 0:
        plan.get("7", {}).pop("experiments", None)
    if sc.get("repo_analysis") is False:
        plan.get("1", {}).pop("readers", None)
    return {ph: {k: v for k, v in kinds.items() if v} for ph, kinds in plan.items()}


def wave_minutes(minutes, parallel):
    xs = sorted(minutes, reverse=True)
    return sum(xs[i] for i in range(0, len(xs), parallel)) if xs else 0


def concept_flags(cfg):
    """Признаки режима идеи для состава агентов: чувствительная область (право), внешняя платформа, прототип, один проход."""
    idea = cfg.get("idea") or {}
    fc = idea.get("facets") or {}
    sc = cfg.get("scope") or {}
    legal = sc.get("legal") is True or bool(fc.get("sensitive"))
    if sc.get("legal") is False:
        legal = False
    platform = bool(fc.get("platform_dependency"))
    proto = (cfg.get("phases") or {}).get("prototype") is True or bool(fc.get("prototype_needed"))
    one_pass = str((cfg.get("registry") or {}).get("passes") or "") == "1"
    ai_role = fc.get("ai_role") if fc.get("ai_role") is not None else fc.get("ai")
    ai = bool(ai_role) and str(ai_role).lower() not in ("none", "no", "нет", "без ии", "false", "[]")
    datasrc = bool(fc.get("data_sources_needed"))
    docs = [x for x in (cfg.get("sources") or {}).get("owner_docs") or [] if isinstance(x, dict)]
    owner_refs = bool(fc.get("owner_repos")) or any(str(x.get("role") or "") in ("base", "follow", "ref") for x in docs)
    admin = fc.get("admin_needed") is True or bool(fc.get("admin_who") or fc.get("admin_settings"))
    modes = [m for m in ((cfg.get("design") or {}).get("modes") or []) if m]
    return {"legal": legal, "platform": platform, "prototype": proto, "one_pass": one_pass, "ai": ai, "datasources": datasrc,
            "owner_refs": owner_refs, "admin": admin, "modes": len(modes) or 1}


def concept_agents(depth, cfg, fast=False):
    """Задания по фазам режима идеи (C4…C9) с учётом run-config."""
    fl = concept_flags(cfg)
    plan = {ph: dict(k) for ph, k in (FAST_AGENTS if fast else CONCEPT_AGENTS[depth]).items()}
    sc = cfg.get("scope") or {}
    c4 = plan.setdefault("C4", {})
    if not fast and "research" in c4:
        enabled = 1 + sum(1 for k in ("communities", "keywords", "events") if sc.get(k, True) is not False)   # + аналоги
        c4["research"] = min(c4["research"], enabled)
    if fl["legal"]:
        c4["legal"] = max(1, c4.get("legal", 0))
    else:
        c4.pop("legal", None)
    if fl["platform"]:
        c4["integration"] = 1
    if not fast:                                          # модули C4/C7 по признакам идеи (G7, WP-G)
        if fl["datasources"]:
            c4["datasources"] = 1
        if fl["ai"]:
            c4["ai"] = 1
        if fl["owner_refs"]:
            c4["owner_refs"] = 1
        c7 = plan.setdefault("C7", {})
        if fl["ai"]:
            c7["module"] = c7.get("module", 0) + 1
        if fl["admin"]:
            c7["module"] = c7.get("module", 0) + 1
    if sc.get("competitors") is False:
        c4.pop("cards", None)
    if fl["one_pass"] and "titles" in plan.get("C5", {}):
        plan["C5"].pop("titles", None)
    if (cfg.get("phases") or {}).get("gap_audit") is False:
        plan.pop("C5.5", None)
    c8 = plan.get("C8", {})
    if sc.get("design_mockups") is False:
        c8.pop("mockups", None)
        c8.pop("design", None)
    if sc.get("design_refs") is False:
        c8.pop("refs", None)
    if sc.get("experiments") == 0:
        plan.get("C7", {}).pop("experiments", None)
    if fl["prototype"] and not fast:                      # ядро → оболочка → режимы × N → регрессия (references/prototype.md)
        if depth == "quick":
            plan["C8.5"] = {"prototype_core": 1}
        else:
            plan["C8.5"] = {"prototype_core": 1, "prototype_shell": 1,
                            "prototype_mode": fl["modes"] if depth in ("deep", "exhaustive") else 1, "prototype_regression": 1}
    return {ph: {k: v for k, v in kinds.items() if v} for ph, kinds in plan.items()}


CONCEPT_ORDER = ["C4", "C5", "C5.5", "C6", "C7", "C8", "C8.5", "C9"]


def forecast(depth, parallel, cfg, fast=False):
    concept = (cfg or {}).get("mode") == "concept"
    plan = concept_agents(depth, cfg, fast) if (concept or fast) else scoped_agents(depth, cfg)
    order = CONCEPT_ORDER if (concept or fast) else PHASE_ORDER
    tm, mm = TOKEN_MULT[depth], MINUTE_MULT[depth]
    rows, by_model = [], {}
    total_agents = total_tok = 0
    pool78 = []
    total_min = 0.0
    for ph in order:
        kinds = plan.get(ph) or {}
        n = sum(kinds.values())
        tok = sum(KINDS[k][1] * c for k, c in kinds.items()) * tm
        for k, c in kinds.items():
            by_model[KINDS[k][0]] = by_model.get(KINDS[k][0], 0) + KINDS[k][1] * c * tm
        mins_list = [KINDS[k][2] * mm for k, c in kinds.items() for _ in range(c)]
        if ph in ("5", "C5"):                             # проход 1 и проход 2 — последовательно
            mins = wave_minutes([KINDS["titles"][2] * mm] * kinds.get("titles", 0), parallel) + \
                wave_minutes([KINDS["details"][2] * mm] * kinds.get("details", 0), parallel)
        elif ph in ("7", "8", "C7", "C8"):                # фазы 7 и 8 идут общими волнами
            pool78 += mins_list
            mins = None
        elif ph == "C8.5" and any(k in kinds for k in PROTO_ORDER):   # шаги прототипа последовательно, режимы — параллельно
            mins = sum(wave_minutes([KINDS[k][2] * mm] * kinds.get(k, 0), parallel) for k in PROTO_ORDER) + \
                wave_minutes([KINDS[k][2] * mm for k, c in kinds.items() if k not in PROTO_ORDER for _ in range(c)], parallel)
        else:
            mins = wave_minutes(mins_list, parallel)
        if mins is not None:
            total_min += mins
        total_agents += n
        total_tok += tok
        if n:
            rows.append({"phase": ph, "agents": n, "kinds": {KIND_TITLES[k]: c for k, c in kinds.items()},
                         "tokens_m": round(tok / 1000, 2), "minutes": None if mins is None else round(mins)})
    m78 = wave_minutes(pool78, parallel)
    total_min += m78
    for r in rows:
        if r["phase"] in ("7", "8", "C7", "C8") and r["minutes"] is None:
            r["minutes"] = "≈%d (7+8 вместе)" % round(m78)
    o_tok, o_min = ORCH[depth]
    if fast:
        o_tok, o_min = ORCH["quick"]
    by_model["opus (оркестратор)"] = o_tok * 1.0
    total_tok += o_tok
    total_min += o_min
    hours = total_min / 60
    res = {"depth": depth, "parallel": parallel, "agents": total_agents, "tokens_m": round(total_tok / 1000, 1),
           "tokens_range_m": [round(total_tok * 0.7 / 1000, 1), round(total_tok * 1.3 / 1000, 1)],
           "hours": round(hours, 1), "hours_range": [round(hours * 0.7, 1), round(hours * 1.3, 1)],
           "tokens_by_model_m": {k: round(v / 1000, 2) for k, v in sorted(by_model.items())},
           "orchestrator": {"tokens_m": round(o_tok / 1000, 2), "minutes": o_min}, "phases": rows,
           "basis": "таблица глубины × типовые затраты; калибровка: standard ≈ 27 агентов / 6,3 млн / 6 ч, deep ≈ 50 / 11 млн / 4–5 ч; ±30 %"}
    if concept or fast:
        res["mode"] = "concept-fast" if fast else "concept"
    if fast:
        res["skipped"] = FAST_SKIPPED
    return res


def fast_tasks(cfg):
    """Состав «быстрой концепции» с учётом run-config (право — только в чувствительной области, интеграция — при платформе)."""
    fl = concept_flags(cfg)
    res = []
    for t in FAST_TASKS:
        if t.get("when") == "legal" and not fl["legal"]:
            continue
        if t.get("when") == "platform" and not fl["platform"]:
            continue
        res.append({k: v for k, v in t.items() if k != "when"})
    return res


def forecast_lines(fc, actual=None):
    L = ["Прогноз объёма прогона (глубина %s, параллельно ≤ %d) — оценка, ±30 %%:" % (fc["depth"], fc["parallel"]),
         "  агентов ≈ %d; токенов ≈ %.1f млн (%.1f–%.1f); время по часам ≈ %.1f ч (%.1f–%.1f)" % (
             fc["agents"], fc["tokens_m"], fc["tokens_range_m"][0], fc["tokens_range_m"][1], fc["hours"], fc["hours_range"][0], fc["hours_range"][1]),
         "  токены по моделям, млн: " + ", ".join("%s %.2f" % kv for kv in fc["tokens_by_model_m"].items()),
         "  | Фаза | Агентов | Что | Токены, млн | Минут |", "  |---|---|---|---|---|"]
    for r in fc["phases"]:
        L.append("  | %s | %d | %s | %.2f | %s |" % (r["phase"], r["agents"], ", ".join("%s × %d" % kv for kv in r["kinds"].items()),
                                                 r["tokens_m"], r["minutes"]))
    L.append("  | оркестратор | — | опрос, синтез, слияние, оценка, сборка, QA | %.2f | %d |" % (fc["orchestrator"]["tokens_m"], fc["orchestrator"]["minutes"]))
    L.append("  Основа: " + fc["basis"])
    if fc.get("skipped"):
        L.append("  Быстрая концепция опускает: " + "; ".join(fc["skipped"]))
    if actual:
        L.append("  Факт по build/agents.json: агентов %d, токены %s, минут агентов %d" % (actual["agents"], fmt_tokens(actual["tokens"]), actual["minutes"]))
    return L


# ---------------------------------------------------------------- триаж

def triage_file(out, st, wave):
    tasks = [t for t in st["tasks"] if t["wave"] == wave and t["status"] == "pending"]
    if not tasks:
        raise ValueError("в волне %s нет заданий в очереди" % wave)
    # shared_out: агенты пишут в общий <OUT> — isolation (worktree) не нужен и вреден: результат из worktree не вернётся (FB-013)
    items = [{"id": t["id"], "task": t["task"] or (KIND_TITLES.get(t["kind"]) or t["id"]), "paths": t["paths"], "shared_out": True}
             for t in tasks]
    path = out / "build" / ("triage-%s.json" % wave)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path, items


def apply_triage(st, wave, result, confirmed=False, cfg=None):
    rows = (result or {}).get("tasks") or []
    by_id = {t["id"]: t for t in st["tasks"] if t["wave"] == wave}
    applied = []
    _mp, ep = agents_policy(cfg or {})
    for r in rows:
        t = by_id.get(str(r.get("id")))
        if not t:
            continue
        model = r.get("model") if confirmed or not r.get("confirm") else (r.get("fallback") or r.get("model"))
        effort = r.get("effort") if confirmed or not r.get("effort_confirm") else (r.get("effort_fallback") or r.get("effort"))
        if model:
            t["model"] = model
        t["effort"] = effort if ep in (None, "explicit") else None      # effort_policy = none — не регулировать (FB-003)
        t["triage"] = "typesafe-triage"
        if r.get("isolation"):
            t["note"] = ((t.get("note") or "") + " isolation снят: агенты пишут в общий <OUT>").strip()
        applied.append((t["id"], t["model"], t["effort"]))
    if result and result.get("ask") and not confirmed:
        st["waves"].setdefault(wave, {})["triage_ask"] = result["ask"]
    return applied


# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", help="папка прогона <OUT>")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add", help="добавить задание")
    p.add_argument("--id", required=True)
    p.add_argument("--brief", default="")
    p.add_argument("--wave")
    p.add_argument("--phase")
    p.add_argument("--kind", choices=sorted(KINDS))
    p.add_argument("--model")
    p.add_argument("--effort")
    p.add_argument("--deps", default="")
    p.add_argument("--paths", default="")
    p.add_argument("--search", type=int)
    p.add_argument("--fetch", type=int)
    p.add_argument("--task", default="")
    p.add_argument("--note", default="")
    p = sub.add_parser("load", help="добавить задания из JSON-файла")
    p.add_argument("file")
    p = sub.add_parser("ready", help="задания, готовые к запуску")
    p.add_argument("--max", type=int)
    p.add_argument("--start", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("start", help="отметить «работает»")
    p.add_argument("ids", nargs="+")
    p = sub.add_parser("done", help="итог агента")
    p.add_argument("id")
    p.add_argument("--tokens", type=int)
    p.add_argument("--minutes", type=float)
    p.add_argument("--model-actual")
    p.add_argument("--result", choices=("ok", "rework", "failed"), default="ok")
    p.add_argument("--search", type=int)
    p.add_argument("--fetch", type=int)
    p.add_argument("--note", default="")
    p = sub.add_parser("close-wave", help="после волны: check_paths и merge_sources")
    p.add_argument("wave")
    p.add_argument("--no-merge", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("status", help="статус по волнам")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("report", help="таблица раздела 11 REPORT.md")
    p.add_argument("--write", action="store_true")
    p = sub.add_parser("triage", help="пакетный триаж моделей волны")
    p.add_argument("wave")
    p.add_argument("--run", metavar="TYPESAFE_TRIAGE_PY")
    p.add_argument("--apply", metavar="RESULT_JSON")
    p.add_argument("--confirmed", action="store_true", help="пользователь подтвердил haiku/fable/low/max")
    p = sub.add_parser("forecast", help="прогноз агентов, токенов и часов")
    p.add_argument("--depth", choices=sorted(DEPTH_AGENTS))
    p.add_argument("--parallel", type=int)
    p.add_argument("--json", action="store_true")
    p.add_argument("--from-agents", action="store_true", help="рядом — факт из build/agents.json")
    p.add_argument("--fast", action="store_true", help="«быстрая концепция»: ≈10 агентов (что опускается — в выводе)")
    p = sub.add_parser("fast-plan", help="состав «быстрой концепции» (задания по волнам)")
    p.add_argument("--write", action="store_true", help="записать build/tasks-fast.json")
    p = sub.add_parser("owners", help="общие пути выдачи у заданий одной волны")
    p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out).expanduser().resolve()
    cfg = load_cfg(out)
    if a.cmd == "fast-plan":
        tasks = fast_tasks(cfg)
        if a.write:
            (out / "build").mkdir(parents=True, exist_ok=True)
            (out / "build" / "tasks-fast.json").write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("→ build/tasks-fast.json (%d заданий): dispatch.py <OUT> load build/tasks-fast.json" % len(tasks))
        for t in tasks:
            print("- %s · волна %s · %s · %s%s" % (t["id"], t["wave"], KIND_TITLES.get(t["kind"], t["kind"]), t["brief"],
                                                ("; после %s" % ", ".join(t["deps"])) if t.get("deps") else ""))
        print("Опускается: " + "; ".join(FAST_SKIPPED))
        return 0
    if a.cmd == "forecast":
        depth = a.depth or (cfg.get("strategy") or {}).get("depth") or "standard"
        if depth not in DEPTH_AGENTS:
            depth = "standard"
        fast = a.fast or bool((cfg.get("strategy") or {}).get("fast_concept"))
        fc = forecast(depth, max_parallel(cfg, a.parallel), cfg, fast=fast)
        actual = None
        if a.from_agents:
            st = load_state(out)
            actual = {"agents": len(st["tasks"]), "tokens": sum(t["tokens"] or 0 for t in st["tasks"]),
                      "minutes": round(sum(t["minutes"] or 0 for t in st["tasks"]))}
            fc["actual"] = actual
        print(json.dumps(fc, ensure_ascii=False, indent=2) if a.json else "\n".join(forecast_lines(fc, actual)))
        return 0
    if not out.is_dir():
        print("ошибка: нет папки %s" % out, file=sys.stderr)
        return 2
    limit = max_parallel(cfg, getattr(a, "max", None))
    try:
        if a.cmd in ("add", "load"):
            if a.cmd == "add":
                items = [{k: getattr(a, k) for k in ("id", "brief", "wave", "phase", "kind", "model", "effort", "deps", "paths",
                                                     "search", "fetch", "task", "note")}]
            else:
                data = json.loads(Path(a.file).read_text(encoding="utf-8"))
                items = data.get("tasks", []) if isinstance(data, dict) else data
            added, unknown = add_tasks(out, items)
            print("добавлено заданий: %d (%s)" % (len(added), ", ".join(added)))
            if unknown:
                print("ВНИМАНИЕ: зависимости без заданий: %s" % ", ".join(unknown), file=sys.stderr)
            for s in shared_paths(load_state(out)):
                if set(s["tasks"]) & set(added):
                    print("ВНИМАНИЕ: общий путь %s у %s (волна %s) — одновременно не запустятся; назначьте владельца общего файла"
                          % (s["path"], " и ".join(s["tasks"]), s["wave"]), file=sys.stderr)
            return 0
        st = load_state(out)
        if a.cmd == "owners":
            sh = shared_paths(st)
            if a.json:
                print(json.dumps(sh, ensure_ascii=False, indent=2))
            else:
                for s in sh:
                    print("общий путь %s: %s (волна %s)" % (s["path"], ", ".join(s["tasks"]), s["wave"]))
                if not sh:
                    print("общих путей выдачи нет")
            return 1 if sh else 0
        if a.cmd == "ready":
            res, blocked, slots = ready_tasks(st, limit)
            started = mark_running(out, st, [t["id"] for t in res]) if a.start else []
            if a.start:
                save_state(out, st)
            od = out_display(out)
            mp, ep = agents_policy(cfg)
            items = [{"id": t["id"], "wave": t["wave"], "model": t["model"], "effort": effort_out(cfg, t["effort"]), "brief": t["brief"],
                      "isolation": None, "prompt": PROMPT.format(brief=("%s/%s" % (od, t["brief"])) if od else t["brief"])} for t in res]
            untriaged = [t["id"] for t in res if not t.get("triage")] if mp == "triage" else []
            if a.json:
                print(json.dumps({"ready": items, "blocked": [{"id": i, "why": w} for i, w in blocked], "free_slots": slots,
                                  "started": started, "policy": {"model": mp, "effort": ep,
                                                                 "note": ((cfg.get("tools") or {}).get("agents") or {}).get("note") if mp == "custom" else None},
                                  "untriaged": untriaged,
                                  "isolation": "не ставить: агенты пишут в общий <OUT>"}, ensure_ascii=False, indent=2))
            else:
                running = sum(1 for t in st["tasks"] if t["status"] == "running")
                print("свободных слотов: %d из %d; готово к запуску: %d%s" % (slots, limit, len(items), " (отмечены «работает»)" if a.start else ""))
                for it in items:
                    print("- %s · Agent(model=\"%s\"%s) · %s" % (it["id"], it["model"], (", effort=\"%s\"" % it["effort"]) if it["effort"] else "", it["prompt"]))
                if items:
                    print("  isolation не ставить: агенты пишут в общий <OUT>, пути разведены брифами")
                if untriaged:
                    print("  политика моделей triage: без триажа — %s → dispatch.py <OUT> triage <волна> --run <typesafe_triage.py>" % ", ".join(untriaged))
                if items and mp == "custom":
                    print("  политика моделей custom: %s" % (((cfg.get("tools") or {}).get("agents") or {}).get("note") or "правила владельца не записаны (tools.agents.note)"))
                elif items and mp == "default":
                    print("  политика моделей default: модели по правилам скилла (references/orchestration.md, «Выбор модели»)")
                if items and ep not in (None, "explicit"):
                    print("  effort не задаётся (tools.agents.effort_policy = %s)" % ep)
                for i, w in blocked:
                    print("  ждёт %s: %s" % (i, w))
                if not items and not running and all(t["status"] in ("done", "failed") for t in st["tasks"]):
                    print("очередь пуста: все задания завершены")
            return 0
        if a.cmd == "start":
            started = mark_running(out, st, set(a.ids))
            save_state(out, st)
            print("работает: %s" % (", ".join(started) or "—"))
            return 0 if started else 1
        if a.cmd == "done":
            t, wave_done = mark_done(out, st, a.id, a)
            save_state(out, st)
            print("%s: %s (токены %s, минут %s)" % (t["id"], {"pending": "снова в очереди (доработка)"}.get(t["status"], t["status"]),
                                                  fmt_tokens(t["tokens"]), t["minutes"] if t["minutes"] is not None else "—"))
            if wave_done:
                print("волна %s завершена → dispatch.py %s close-wave %s (check_paths + merge_sources)" % (t["wave"], "<OUT>", t["wave"]))
            return 0
        if a.cmd == "close-wave":
            info = close_wave(out, st, a.wave, merge=not a.no_merge)
            save_state(out, st)
            if a.json:
                print(json.dumps(info, ensure_ascii=False, indent=2))
            else:
                cp = info.get("check_paths") or {}
                print("волна %s: check_paths — %s; merge_sources — %s" % (
                    a.wave, cp.get("skipped") or ("нарушений %d" % len(cp.get("violations") or [])),
                    (info.get("merge_sources") or {}).get("skipped") or (info.get("merge_sources") or {}).get("summary")))
                for v in cp.get("violations") or []:
                    print("  НАРУШЕНИЕ %s — %s" % (v.get("file"), v.get("why")))
            return 1 if (info.get("check_paths") or {}).get("violations") else 0
        if a.cmd == "status":
            print(json.dumps(st, ensure_ascii=False, indent=2) if a.json else "\n".join(status_lines(st, limit)))
            return 0
        if a.cmd == "report":
            text = "\n".join(report_md(st, cfg)) + "\n"
            if (cfg.get("disclosure") or "full").lower() != "summary" and st["tasks"]:
                depth = (cfg.get("strategy") or {}).get("depth") or "standard"
                fc = forecast(depth if depth in DEPTH_AGENTS else "standard", max_parallel(cfg), cfg,
                              fast=bool((cfg.get("strategy") or {}).get("fast_concept")))
                text += ("\nПрогноз до старта: агентов %d, токенов %.1f млн, %.1f ч; факт: агентов %d, токенов %s, минут агентов %d.\n" % (
                    fc["agents"], fc["tokens_m"], fc["hours"], len(st["tasks"]), fmt_tokens(sum(t["tokens"] or 0 for t in st["tasks"])),
                    round(sum(t["minutes"] or 0 for t in st["tasks"]))))
            if a.write:
                (out / "build" / "agents-report.md").write_text("## 11. Использованные инструменты и токены\n\n" + text, encoding="utf-8")
                print("→ build/agents-report.md")
            print(text, end="")
            return 0
        if a.cmd == "triage":
            path, items = triage_file(out, st, a.wave)
            print("build/%s: %d заданий" % (path.name, len(items)))
            result = None
            if a.run:
                r = subprocess.run([sys.executable, a.run, "--batch", str(path), "--json"], capture_output=True, text=True, timeout=900)
                if r.returncode != 0:
                    print("typesafe_triage.py --batch: код %d — %s" % (r.returncode, (r.stderr or r.stdout).strip()[:200]), file=sys.stderr)
                    return 1
                result = json.loads(r.stdout)
            elif a.apply:
                result = json.loads(Path(a.apply).read_text(encoding="utf-8"))
            if result is not None:
                applied = apply_triage(st, a.wave, result, a.confirmed, cfg)
                save_state(out, st)
                for i, m, e in applied:
                    print("  %s → model=%s, effort=%s" % (i, m, e or "—"))
                if result.get("ask") and not a.confirmed:
                    print("нужно подтверждение пользователя (один вопрос на пакет): до ответа взяты запасные sonnet/opus и medium/xhigh; "
                          "после «да» — повторить с --confirmed")
            else:
                print("дальше: python3 <typesafe-triage>/scripts/typesafe_triage.py --batch build/%s --json > build/triage-%s.result.json; "
                      "dispatch.py <OUT> triage %s --apply build/triage-%s.result.json" % (path.name, a.wave, a.wave, a.wave))
            return 0
    except (ValueError, json.JSONDecodeError, OSError) as e:
        print("ошибка: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
