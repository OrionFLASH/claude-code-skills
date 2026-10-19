#!/usr/bin/env python3
"""Генератор REPORT.md и README сдачи из данных прогона (FB-016): оркестратор дописывает только помеченные места.

  report.py <OUT> [--write] [--force] [--if-missing]   каркас deliverables/REPORT.md по templates/report.md: все разделы
                                                        шаблона, заполненные из данных; места, которые знает только
                                                        оркестратор, — `<заполнить: …>`
  report.py <OUT> --check [--json]                       проверка готового REPORT.md: все разделы шаблона на месте,
                                                        мест `<заполнить` — 0 (код 1 — нет разделов или есть пропуски)
  report.py <OUT> --readme [--force]                     deliverables/README.md по templates/README-deliverables.md (вместо sed)

Источники: build/run-config.json, build/STATUS.md (фазы), data/idea.json, data/typesafe-concept.json, data/premises.json,
data/proposals.json, data/scores.json, data/decisions.json, data/fact-check.json, build/merge-report.json,
data/gap-audit-deps.json, build/deps-patch.json, data/proposals-draft-G8.json, data/sources-*.json, build/agents.json
(dispatch.py), build/interventions.jsonl (init_run.py --intervention), build/build-all-last.json (ворота и completeness),
build/owner-materials.md и sources.owner_docs[], idea.request_questions[] (маркеры [RQ01] в тексте), build/env.json.
Правленный вручную REPORT.md не затирается: без --force пишется deliverables/REPORT.generated.md (метка
`<!-- generated-by: report.py -->` + sha256 — по ней скрипт видит, что файл не правили). Пути в отчёте — относительные.
Только стандартная библиотека.
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))
TEMPLATE = SKILL / "templates" / "report.md"
README_TPL = SKILL / "templates" / "README-deliverables.md"
FILL = "<заполнить: %s>"
MARK = "<!-- generated-by: report.py · sha256:%s -->"
MARK_RE = re.compile(r"<!-- generated-by: report\.py · sha256:([0-9a-f]{12,64}) -->\s*$")
FILL_RE = re.compile(r"<заполнить")
CONCEPT_PHASE_FILES = {"C0": "build/env.json, build/STATUS.md", "C1": "research/idea-dossier.md, data/idea.json, build/search-plan.md",
                       "C2": "data/typesafe-concept.json", "C3": "build/seeds.md", "C4": "data/competitors.json, research/market.md",
                       "C4.5": "data/premises.json", "C5": "data/proposals.json", "C5.5": "research/gap-audit.md",
                       "C6": "data/scores.json, data/model.json", "C7": "research/strategy.md, data/gantt.json",
                       "C7.5": "build/deps-patch.json", "C8": "mockups/tokens.css, mockups/concepts/", "C8.5": "prototype/",
                       "C9": "deliverables/"}


def jload(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def rows_of(data, *keys):
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for k in keys:
            if isinstance(data.get(k), list):
                return [x for x in data[k] if isinstance(x, dict)]
    return []


def esc(s):
    return str(s if s is not None else "—").replace("|", "/").replace("\n", " ").strip() or "—"


def template_headings():
    try:
        return [line.strip() for line in TEMPLATE.read_text(encoding="utf-8").splitlines() if line.startswith("## ")]
    except OSError:
        return []


class Run:
    def __init__(self, out):
        self.out = Path(out).resolve()
        self.cfg = jload(self.out / "build" / "run-config.json", {}) or {}
        self.concept = self.cfg.get("mode") == "concept"

    def j(self, rel, default=None):
        return jload(self.out / rel, default)

    def exists(self, rel):
        return (self.out / rel).exists()

    def c(self, *keys, default=None):
        v = self.cfg
        for k in keys:
            if not isinstance(v, dict):
                return default
            v = v.get(k)
        return default if v in (None, "") else v


# ---------------------------------------------------------------- разделы
def s_product(r):
    L = []
    if r.concept:
        idea = r.j("data/idea.json", {}) or {}
        pitch = r.c("idea", "pitch_v2") or r.c("idea", "pitch") or idea.get("pitch")
        L.append("- Идея%s: %s" % (" (v%s после пересмотра)" % r.c("idea", "version") if r.c("idea", "pitch_v2") else "", esc(pitch)))
        aud = r.c("project", "audience") or "public"
        L.append("- Для кого: %s; тип продукта: %s; формы: %s; рынки: %s." % (
            {"personal": "только для владельца (личный режим)", "circle": "владелец и узкий круг", "personal_then_public": "сначала для себя, позже — возможно публично",
             "public": idea.get("segment_label") or "публичный продукт"}.get(aud, aud),
            esc(r.c("product", "type")), ", ".join(r.c("product", "forms") or []) or "—", ", ".join(r.c("strategy", "markets") or []) or "—"))
        L.append("- Продукта ещё нет (режим идеи): код, приложение и Issues не изучались; спрос — гипотеза.")
    else:
        L.append("- Продукт: %s%s." % (esc(r.c("product", "name")), " (%s)" % r.c("product", "type") if r.c("product", "type") else ""))
        L.append("- " + FILL % "что это, для кого, какую задачу решает (2–4 предложения); как запускал; что изучил")
    L.append("- " + FILL % "где уверенность выше и где ниже — и почему")
    return L


def phase_rows(r):
    sp = r.out / "build" / "STATUS.md"
    try:
        s = sp.read_text(encoding="utf-8")
    except OSError:
        return []
    return [(m.group(2), m.group(1) == "x", m.group(3)) for m in re.finditer(r"^- \[( |x)\] (C?[\d.]+)\. (.*)$", s, re.M)]


def s_phases(r):
    rows = phase_rows(r)
    L = ["| Фаза | Сделано | Файлы |", "|---|---|---|"]
    if not rows:
        L.append("| — | %s | `build/STATUS.md` |" % FILL % "фазы и чекпоинты (нет чек-листа в STATUS.md)")
    for num, done, text in rows:
        files = CONCEPT_PHASE_FILES.get(num, "") if r.concept else ""
        L.append("| %s. %s | %s | %s |" % (num, esc(text.split(":")[0]), "да" if done else "**нет**", "`%s`" % files if files else "—"))
    return L


def s_typesafe(r):
    L = []
    jev = r.j("data/typesafe-jev.json", None)
    if isinstance(jev, dict) and jev.get("skipped"):
        L.append("- TypeSafe Jev по предложениям: пропущен — %s." % jev["skipped"])
    elif isinstance(jev, dict):
        L.append("- TypeSafe Jev по предложениям: оценено %d (`data/typesafe-jev.json`)." % len(jev.get("items") or jev.get("results") or []))
    else:
        L.append("- TypeSafe Jev по предложениям: не запускался (`tools.typesafe` или нет ключа).")
    ag = (r.c("tools", "agents") or {})
    st = r.j("build/agents.json", {}) or {}
    tri = sum(1 for t in st.get("tasks") or [] if t.get("triage"))
    L.append("- Модели субагентов: %s; политика: модели — %s, effort — %s." % (
        "typesafe-triage у %d заданий" % tri if tri else "правило по умолчанию (references/orchestration.md)",
        ag.get("model_policy") or "не задана", ag.get("effort_policy") or "не задана"))
    env = r.j("build/env.json", {}) or {}
    have = [x["name"][6:] for x in env.get("rows") or [] if str(x.get("name", "")).startswith("skill:") and x.get("status") == "OK"]
    miss = [x["name"][6:] for x in env.get("rows") or [] if str(x.get("name", "")).startswith("skill:") and x.get("status") != "OK"]
    L.append("- Навыки: есть — %s; нет — %s." % (", ".join(have) or "—", ", ".join(miss) or "—"))
    return L


def s_registry(r):
    props = rows_of(r.j("data/proposals.json", []), "proposals")
    if not props:
        return ["Реестра нет (`data/proposals.json`)."]
    cats = Counter(p.get("category") for p in props)
    cls = Counter(p.get("evidence_class") for p in props)
    n = len(props)
    L = ["Всего: **%d** предложений." % n, "", "| Категория | Число | Доля |", "|---|---|---|"]
    for c, k in cats.most_common():
        L.append("| %s | %d | %d %% |" % (esc(c), k, round(100 * k / n)))
    ab = cls.get("A", 0) + cls.get("B", 0)
    L += ["", "Классы доказательств: A — %d, B — %d, C — %d, D — %d (A+B = %d %%)." % (cls.get("A", 0), cls.get("B", 0), cls.get("C", 0), cls.get("D", 0),
                                                                                    round(100 * ab / n))]
    mr = r.j("build/merge-report.json", {}) or {}
    if isinstance(mr, dict) and (mr.get("merged") or mr.get("pairs")):
        L.append("Слито дублей: %s (`build/merge-report.json`)." % (len(mr.get("merged") or mr.get("pairs") or [])))
    scores = rows_of(r.j("data/scores.json", []))
    if scores:
        L += ["", "### Топ-20", "| Ранг | Ранг с зависимостями | ID | Название | Категория | Класс | Composite | Приоритет | Горизонт |",
              "|---|---|---|---|---|---|---|---|---|"]
        for s in sorted(scores, key=lambda x: x.get("rank", 10 ** 6))[:20]:
            L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (s.get("rank"), s.get("dep_rank", "—"), s.get("id"), esc(s.get("title"))[:70],
                                                                    esc(s.get("category")), esc(s.get("evidence_class")),
                                                                    "%.3f" % s["composite"] if isinstance(s.get("composite"), (int, float)) else "—",
                                                                    esc(s.get("priority")), esc(s.get("horizon"))))
    return L


def s_bets(r):
    L = []
    if r.concept:
        ts = r.j("data/typesafe-concept.json", {}) or {}
        if ts.get("verdict"):
            L.append("Светофор жизнеспособности: **%s** — %s (жизнеспособность %s, риск %s; источник %s)." % (
                {"green": "зелёный", "yellow": "жёлтый", "red": "красный"}.get(ts["verdict"], ts["verdict"]), ts.get("verdict_label", ""),
                ts.get("viability"), ts.get("risk"), ts.get("source")))
            L.append("")
    dec = r.j("data/decisions.json", {}) or {}
    bets = [b for b in dec.get("bets") or [] if isinstance(b, dict)] if isinstance(dec, dict) else []
    if bets:
        for b in bets[:3]:
            L.append("%s. **Ставка %s:** %s (%s) — %s." % (b.get("id"), b.get("id"), esc(b.get("name") or b.get("what")),
                                                        ", ".join(b.get("proposals") or []) or "—", esc(b.get("effect") or FILL % "ожидаемый эффект")))
        ns = dec.get("north_star") or {}
        if isinstance(ns, dict) and ns.get("metric"):
            L.append("")
            L.append("North Star: %s%s." % (ns["metric"], " → %s" % ns["target"] if ns.get("target") else ""))
    else:
        L += ["1. **Ставка 1:** " + FILL % "из data/decisions.json (decisions.py) или раздела 1", "2. **Ставка 2:** …", "3. **Ставка 3:** …"]
    L += ["", "Ключевые выводы: " + FILL % "3–7 пунктов"]
    return L


def build_last(r):
    return r.j("build/build-all-last.json", {}) or {}


def s_failed(r):
    last = build_last(r)
    L = ["| Что | Почему | Как повлияло |", "|---|---|---|"]
    n = 0
    for st in last.get("steps") or []:
        if st.get("status") in ("FAIL", "SKIP", "WARN"):
            L.append("| шаг `%s` | %s | %s |" % (st.get("step"), esc(st.get("note")), FILL % "влияние"))
            n += 1
    comp = [c for c in (last.get("completeness") or []) if c.get("status") == "нет" and not c.get("accepted")]
    for c in comp:
        L.append("| %s | %s | %s |" % (esc(c.get("check")), esc(c.get("detail")), esc(c.get("todo"))))
        n += 1
    comps = rows_of(r.j("data/competitors.json", []))
    blocked = [c.get("name") or c.get("slug") for c in comps if c.get("shot_blocked")]
    if blocked:
        L.append("| скриншоты конкурентов (%d) | анти-бот защита | описание по тексту страницы: %s |" % (len(blocked), esc(", ".join(blocked[:6]))))
        n += 1
    if not n:
        L.append("| — | ворота сборки не нашли пропусков | — |")
    return L


def s_questions(r):
    p = r.out / "research" / "questions-owner.md"
    items = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*(?:\d+[.)]|[-*])\s+(.+)", line)
            if m and len(m.group(1)) > 10:
                items.append(m.group(1).strip())
            if len(items) >= 10:
                break
    if not items:
        return ["1. " + FILL % "вопросы владельцу (≤ 10; кандидаты — build_appendix.py)"]
    return ["%d. %s" % (i, x) for i, x in enumerate(items, 1)] + ["(полный список — `research/questions-owner.md`)"]


def s_cut(r):
    return ["- " + FILL % "что сокращено из-за глубины, бюджета, инструментов (или «ничего»)"]


def s_next(r):
    tf = (r.c("output", "tasks_file") or "")
    return ["- Чекпоинты: `build/STATUS.md` (`init_run.py <OUT> --status` — таблица с ETA); чек-лист: %s." % (
                "`TASKS.md` владельца (блок фаз)" if tf and "STRATEGY" not in tf else "`STRATEGY_TASKS.md` или блок фаз в `TASKS.md` владельца"),
            "- Пересборка: `python3 <SKILL_DIR>/scripts/build_all.py <OUT>` (подробно — `deliverables/README.md`); черновик — `--preview`.",
            "- Следующий шаг: " + FILL % "первая дешёвая проверка / первая задача"]


def s_decided(r):
    L = ["| Решение | Почему так | Как поменять |", "|---|---|---|"]
    for a in (r.c("assumptions") or [])[:20]:
        L.append("| %s | допущение прогона | `intake.py update <OUT> --set …` или ответ владельца |" % esc(a)[:160])
    d = r.c("design") or {}
    if isinstance(d, dict) and d.get("chosen"):
        L.append("| направление дизайна: %s | %s | `init_run.py <OUT> --impact \"дизайн\"` |" % (
            esc(d["chosen"]), "выбрал владелец" if d.get("chosen_by") == "owner" else "по умолчанию — рекомендованное"))
    if len(L) == 2:
        L.append("| " + FILL % "решения за владельца" + " | | |")
    return L


def s_tools(r):
    disc = str(r.c("disclosure") or "full").lower()
    if disc == "summary":
        return ["Подготовлено с помощью ИИ-инструментов (детали — в build/agents.json)."]
    if disc == "none":
        return ["(disclosure: none — раздел только в `build/agents-report.md`)"]
    try:
        sys.path.insert(0, str(HERE))
        import dispatch
        st = dispatch.load_state(r.out)
        if not st["tasks"]:
            return ["Запусков в `build/agents.json` нет — %s." % FILL % "агенты и токены по уведомлениям (dispatch.py done …)"]
        return dispatch.report_md(st, r.cfg)
    except Exception:                                  # noqa: BLE001
        return [FILL % "таблица dispatch.py <OUT> report"]


def s_off(r):
    L = ["| Что выключено | Где задано | Чем заменено / как повлияло |", "|---|---|---|"]
    for k, v in sorted((r.c("scope") or {}).items()):
        if v is False:
            L.append("| направление `%s` | `scope.%s=false` | %s |" % (k, k, FILL % "чем заменено"))
    for k, v in sorted((r.c("formats") or {}).items()):
        if v is False:
            L.append("| формат %s | `formats.%s=false` | — |" % (k.upper(), k))
    for k, v in sorted((r.c("phases") or {}).items()):
        if v is False:
            L.append("| фаза `%s` | `phases.%s=false` | — |" % (k, k))
    if len(L) == 2:
        L.append("| — | ничего не выключено | — |")
    return L


def s_factcheck(r):
    rows = rows_of(r.j("data/fact-check.json", []), "items", "discrepancies", "checks", "facts")
    if not rows:
        return ["Записей нет (`data/fact-check.json`)."]
    solved = [x for x in rows if x.get("resolved_value") not in (None, "") or str(x.get("status", "")).lower() in ("resolved", "решено")]
    L = ["Всего записей: %d (решено %d, открыто %d; применено к источникам: %d) — `data/fact-check.json`." % (
        len(rows), len(solved), len(rows) - len(solved), sum(1 for x in rows if x.get("applied"))), "",
         "| Факт | Было | Агент | Источник | Принято | Где исправлено |", "|---|---|---|---|---|---|"]
    for x in rows[:30]:
        fix = x.get("fix") or {}
        L.append("| %s | %s | %s | %s | %s | %s |" % (esc(x.get("fact") or x.get("claim")), esc(x.get("phase1_value") or x.get("was")),
                                                  esc(x.get("agent_value") or x.get("now")), esc(x.get("source"))[:80], esc(x.get("resolved_value")),
                                                  esc(fix.get("file") if isinstance(fix, dict) and x.get("applied") else x.get("note"))))
    return L


def s_changes(r):
    props = rows_of(r.j("data/proposals.json", []), "proposals")
    g7 = [p["id"] for p in props if any(str(m).startswith("G7-") for m in (p.get("merged_from") or [])) or str(p.get("source_group")) == "G7"]
    deps = r.j("data/gap-audit-deps.json", {}) or {}
    patch = r.j("build/deps-patch.json", None)
    g8 = rows_of(r.j("data/proposals-draft-G8.json", []), "proposals")
    srcs = [f.name for f in (r.out / "data").glob("sources-*.json")] if (r.out / "data").is_dir() else []
    L = ["- Добавлено аудитом пробелов: %d%s." % (len(g7), " (%s)" % ", ".join(g7[:12]) if g7 else ""),
         "- Записано предпосылок: %d (`data/gap-audit-deps.json`)." % (sum(len(v) for v in deps.values() if isinstance(v, list)) if isinstance(deps, dict) else 0),
         "- Зависимости от авторов разделов (C7.5): %s." % (
             "%d пар (`build/deps-patch.json`)" % len(rows_of(patch, "deps", "items") or (patch if isinstance(patch, list) else [])) if patch is not None else "не собирались"),
         "- Расхождения макетов и реестра (G8): черновиков %d (`data/proposals-draft-G8.json`)." % len(g8),
         "- Фрагменты источников агентов: %d (%s)." % (len(srcs), ", ".join(sorted(srcs)[:8]) or "—"),
         "- " + FILL % "конфликты, устаревшие допущения, как сдвинулись ставки и топ-20"]
    return L


def s_rq(r):
    rqs = [q for q in (r.c("idea", "request_questions") or []) if isinstance(q, dict)]
    if not rqs:
        return ["Вопросов из запроса не выделено (`idea.request_questions` пуст)."]
    texts = {}
    for f in sorted((r.out / "build" / "parts").glob("strategy-*.md")) + [r.out / "research" / "strategy.md"]:
        if f.exists():
            texts[f.relative_to(r.out).as_posix()] = f.read_text(encoding="utf-8", errors="replace")
    L = ["| RQ | Вопрос | Где ответ | Коротко |", "|---|---|---|---|"]
    for q in rqs:
        qid = q.get("id")
        where = []
        for rel, t in texts.items():
            if "[%s]" % qid in t:
                secs = [m.group(1) for m in re.finditer(r"(?m)^## (\d+)\.", t[:t.index("[%s]" % qid)])]
                where.append("%s%s" % (rel, (" § %s" % secs[-1]) if secs else ""))
        L.append("| %s | %s | %s | %s |" % (qid, esc(q.get("text"))[:120], ", ".join(where[:2]) or "**нет маркера [%s]**" % qid, FILL % "ответ в одну строку"))
    return L


def s_owner(r):
    docs = [d for d in (r.c("sources", "owner_docs") or []) if isinstance(d, (dict, str))]
    if not docs:
        return ["Материалов владельца нет (`sources.owner_docs` пуст)."]
    L = ["| Ссылка | Роль | Статус | Инструмент | Как использовано |", "|---|---|---|---|---|"]
    om = (r.out / "build" / "owner-materials.md")
    omt = om.read_text(encoding="utf-8", errors="replace") if om.exists() else ""
    for d in docs:
        d = d if isinstance(d, dict) else {"url": d}
        st = d.get("status")
        if not st:
            try:
                import build_all
                st = build_all.owner_status(omt, str(d.get("url")))
            except Exception:                          # noqa: BLE001
                st = "not_attempted"
        L.append("| %s | %s | %s | %s | %s |" % (esc(d.get("url"))[:90], esc(d.get("role")), "**%s**" % st if st == "not_attempted" else st,
                                              esc(d.get("tool")), esc(d.get("note") or FILL % "как использовано")))
    return L


def s_pivot(r):
    if not r.concept:
        return ["Не применяется (обычный режим)."]
    pr = r.j("data/premises.json", None)
    L = []
    if not isinstance(pr, dict):
        L.append("Пересмотр идеи не проводился (`data/premises.json` нет) — " + FILL % "почему (или pivot_check.py)")
    else:
        L += ["| Предпосылка | Вид | Статус | Источник |", "|---|---|---|---|"]
        lab = {"confirmed": "подтверждена", "refuted": "**опровергнута**", "partial": "частично"}
        for p in pr.get("premises") or []:
            L.append("| %s | %s | %s | %s |" % (esc(p.get("text"))[:120], esc(p.get("kind")), lab.get(p.get("status"), esc(p.get("status"))), esc(p.get("source"))[:80]))
        dec = pr.get("decision")
        L += ["", "Решение владельца: %s%s%s." % ({"keep": "продолжить с исходной идеей", "narrow": "принять сужение", "stop": "остановиться"}.get(dec, FILL % "решение (pivot_check.py --decide)"),
                                               " (по умолчанию)" if pr.get("by") == "default" else "",
                                               "; идея v2: %s" % pr["pitch_v2"] if pr.get("pitch_v2") else "")]
    d = r.c("design") or {}
    if isinstance(d, dict) and d.get("chosen"):
        L.append("Направление дизайна: %s — %s." % (d["chosen"], "выбрал владелец" if d.get("chosen_by") == "owner" else "по умолчанию (рекомендованное)"))
    return L


def s_interventions(r):
    p = r.out / "build" / "interventions.jsonl"
    recs = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                recs.append(json.loads(line))
            except ValueError:
                continue
    if not recs:
        return ["Журнал пуст (`build/interventions.jsonl`): ручных вмешательств не записано — " + FILL % "подтвердить, что их не было"]
    by = Counter(x.get("by") for x in recs)
    L = ["Всего: %d (владелец %d, оркестратор %d, агенты %d)%s." % (len(recs), by.get("owner", 0), by.get("orchestrator", 0), by.get("agent", 0),
                                                                  "; ретроспектива — `build/retro.md`" if r.exists("build/retro.md") else ""),
         "", "| Когда | Кто | Что | Почему | Файл |", "|---|---|---|---|---|"]
    for x in recs[:40]:
        L.append("| %s | %s | %s | %s | %s |" % (esc(x.get("ts"))[:16], esc(x.get("by")), esc(x.get("what"))[:100], esc(x.get("why"))[:80], esc(x.get("file"))))
    return L


def s_completeness(r):
    last = build_last(r)
    comp = last.get("completeness") or []
    if not comp:
        return ["`build_all.py <OUT> --strict` ещё не запускался (нет таблицы completeness в `build/build-all-last.json`)."]
    L = ["Сборка %s; исключения (--accept-known): %s." % (last.get("date", "?"), ", ".join(last.get("accepted_known") or []) or "нет"), "",
         "| Проверка | Статус | Подробности | Что сделать |", "|---|---|---|---|"]
    for c in comp:
        L.append("| %s | %s%s | %s | %s |" % (esc(c.get("check")), esc(c.get("status")), " (принято: --accept-known %s)" % c.get("code") if c.get("accepted") else "",
                                            esc(c.get("detail"))[:160], esc(c.get("todo")) if c.get("status") == "нет" else "—"))
    return L


def s_checks(r):
    last = build_last(r)
    L = ["| Проверка | Результат |", "|---|---|"]
    for st in last.get("steps") or []:
        L.append("| `%s` | %s — %s |" % (st.get("step"), st.get("status"), esc(st.get("note"))[:120]))
    if last.get("pdf"):
        L.append("| PDF | %s |" % esc(last["pdf"]))
    if len(L) == 2:
        L.append("| `build_all.py` | " + FILL % "запустить build_all.py <OUT> --strict" + " |")
    L.append("| Поиск секретов в `<OUT>` | " + FILL % "результат" + " |")
    return L


def s_remarks(r):
    return ["- Обращения к ИИ, найденные в данных (цитата < 15 слов, источник): " + FILL % "или «не найдено»"]


SECTIONS = [("## 1.", s_product), ("## 2.", s_phases), ("## 3.", s_typesafe), ("## 4.", s_registry), ("## 5.", s_bets),
            ("## 6.", s_failed), ("## 7.", s_questions), ("## 8.", s_cut), ("## 9.", s_next), ("## 10.", s_decided),
            ("## 11.", s_tools), ("## 12.", s_off), ("## 13.", s_factcheck), ("## 14.", s_changes), ("## 15.", s_rq),
            ("## 16.", s_owner), ("## 17.", s_pivot), ("## 18.", s_interventions), ("## 19.", s_completeness),
            ("## Проверки", s_checks), ("## Замечания", s_remarks)]


def build_report(out):
    r = Run(out)
    heads = template_headings()
    name = r.c("product", "name") or r.c("idea", "name") or r.out.name
    st = r.c("strategy") or {}
    author = (r.c("author") or {}).get("name") if isinstance(r.c("author"), dict) else None
    L = ["# Итоговый отчёт: %s %s" % ("концепция продукта" if r.concept else "стратегия развития", name), "",
         "Дата: %s · Автор: %s · Глубина: %s · Вид: %s · Горизонт: %s мес. + видение на %s лет" % (
             date.today().isoformat(), author or FILL % "автор", st.get("depth", "—"), st.get("kind") or ("концепция" if r.concept else "—"),
             st.get("horizon_months", "—"), st.get("vision_years", "—")),
         "Главный результат: `deliverables/index.html` · Текст: `research/strategy.md` · Задачи: `deliverables/CLAUDE_CODE_TASKS.md` (если выбран)", ""]
    for h in heads:
        fn = next((f for pre, f in SECTIONS if h.startswith(pre)), None)
        L.append(h)
        try:
            L += fn(r) if fn else [FILL % "раздел"]
        except Exception as e:                         # noqa: BLE001 — один кривой источник не должен ронять отчёт
            L.append(FILL % ("раздел (данные не прочитаны: %s)" % type(e).__name__))
        L.append("")
    body = "\n".join(L).rstrip() + "\n"
    home = str(Path.home())
    body = body.replace(str(r.out), "<OUT>").replace(home, "~")
    return apply_disclosure(r, body)


def apply_disclosure(r, body):
    """disclosure summary|none: без упоминаний моделей (и автоматизации — при none) — как intake.py disclosure-check."""
    level = str(r.c("disclosure") or "full").lower()
    if level == "full":
        return body
    body = body.replace("## 11. Использованные инструменты и токены", "## 11. Использованные инструменты")
    if level == "none":
        body = body.replace("## 3. TypeSafe и навыки", "## 3. Инструменты и навыки")
    try:
        sys.path.insert(0, str(HERE))
        import intake
        terms = [re.compile(rx, re.I if not rx.startswith("\\b(?:Opus") else 0) for rx, lv in intake.DISCLOSURE_TERMS if level == "none" or lv == "model"]
    except Exception:                                  # noqa: BLE001
        return body
    keep = []
    for line in body.splitlines():
        if not line.startswith("#") and any(t.search(line) for t in terms):
            continue
        keep.append(line)
    return "\n".join(keep).rstrip() + "\n"


def write_generated(dest, body, force=False):
    """Пишет файл с меткой sha; правленный вручную не затирается (→ *.generated.md)."""
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    text = body + MARK % sha + "\n"
    if dest.exists() and not force:
        old = dest.read_text(encoding="utf-8")
        m = MARK_RE.search(old.rstrip("\n").splitlines()[-1] if old.strip() else "")
        content = "\n".join(old.rstrip("\n").splitlines()[:-1]) + "\n" if m else None
        if not m or hashlib.sha256(content.encode("utf-8")).hexdigest()[:16] != m.group(1):
            alt = dest.with_name(dest.stem + ".generated" + dest.suffix)
            alt.write_text(text, encoding="utf-8")
            return alt, False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest, True


def check_report(out):
    """→ {"ok", "missing_sections", "fill", "exists"}: все разделы шаблона и 0 мест «<заполнить»."""
    p = Path(out) / "deliverables" / "REPORT.md"
    if not p.exists():
        return {"ok": False, "exists": False, "missing_sections": template_headings(), "fill": 0}
    text = p.read_text(encoding="utf-8", errors="replace")
    have = [line.strip() for line in text.splitlines() if line.startswith("## ")]
    missing = []
    for h in template_headings():
        num = re.match(r"## (\d+)\.", h)
        if num and not any(x.startswith("## %s." % num.group(1)) for x in have):
            missing.append(h)
        elif not num and not any(x.split(" (")[0] == h.split(" (")[0] for x in have):
            missing.append(h)
    fill = len(FILL_RE.findall(text))
    return {"ok": not missing and fill == 0, "exists": True, "missing_sections": missing, "fill": fill}


def build_readme(out):
    r = Run(out)
    try:
        t = README_TPL.read_text(encoding="utf-8")
    except OSError:
        return None
    name = r.c("product", "name") or r.c("idea", "name") or r.out.name
    author = (r.c("author") or {}).get("name") if isinstance(r.c("author"), dict) else ""
    vals = {"PRODUCT": name, "DATE": date.today().isoformat(), "AUTHOR": author or "—", "DEPTH": (r.c("strategy") or {}).get("depth", "—"),
            "YEAR": str(date.today().year)}
    t = re.sub(r"\{([A-Z]+)\}", lambda m: vals.get(m.group(1), m.group(0)), t)
    if r.concept:
        t = t.replace("# Стратегия развития", "# Концепция продукта", 1).replace("полный текст стратегии", "полный текст концепции")
    shots = r.c("output", "competitor_shots")
    if shots == "local":
        t = t.replace("скриншоты конкурентов (для внутреннего анализа)",
                      "скриншоты конкурентов — только локально (в git не входят: `output.competitor_shots: local`; на сайте — уменьшенные копии)")
    return t


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--write", action="store_true", help="записать deliverables/REPORT.md (по умолчанию — да)")
    ap.add_argument("--force", action="store_true", help="перезаписать правленный вручную файл")
    ap.add_argument("--if-missing", action="store_true", help="писать, только если REPORT.md ещё нет")
    ap.add_argument("--check", action="store_true", help="проверить готовый REPORT.md (разделы и места «<заполнить»)")
    ap.add_argument("--readme", action="store_true", help="deliverables/README.md по шаблону")
    ap.add_argument("--stdout", action="store_true", help="напечатать каркас, не записывая")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out).expanduser().resolve()
    if not out.is_dir():
        print("ошибка: нет папки %s" % out, file=sys.stderr)
        return 2
    if a.check:
        res = check_report(out)
        if a.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        elif not res["exists"]:
            print("REPORT.md нет: report.py <OUT> — каркас из данных")
        else:
            print("REPORT.md: разделов шаблона нет — %d%s; мест «<заполнить» — %d" % (
                len(res["missing_sections"]), (" (%s)" % "; ".join(res["missing_sections"][:5])) if res["missing_sections"] else "", res["fill"]))
        return 0 if res["ok"] else 1
    if a.readme:
        text = build_readme(out)
        if text is None:
            print("нет шаблона README-deliverables.md", file=sys.stderr)
            return 2
        if a.stdout:
            print(text)
            return 0
        dest, ok = write_generated(out / "deliverables" / "README.md", text.rstrip() + "\n", a.force)
        print("→ %s%s" % (dest.relative_to(out), "" if ok else " (README.md правили вручную — не затирается; --force перезапишет)"))
        return 0
    body = build_report(out)
    if a.stdout:
        print(body)
        return 0
    dest = out / "deliverables" / "REPORT.md"
    if a.if_missing and dest.exists():
        print("REPORT.md уже есть — не трогаю (--force без --if-missing перезапишет)")
        return 0
    dest, ok = write_generated(dest, body, a.force)
    fill = len(FILL_RE.findall(body))
    print("→ %s: разделов %d, мест «<заполнить» — %d%s" % (dest.relative_to(out), len(template_headings()), fill,
                                                         "" if ok else " (REPORT.md правили вручную — не затирается; --force перезапишет)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
