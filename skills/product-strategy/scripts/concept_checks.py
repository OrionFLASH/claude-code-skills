#!/usr/bin/env python3
"""Проверки режима идеи до «Начинаю?» и вход прогона (references/intake.md, «Режим идеи: опрос 1.5»).

  run_checks(cfg)        противоречия ответов (CONCEPT_CONFLICTS, FB-053, SM 3.2, 3.4) и ёмкость MVP против срока
                         (FB-054) → находки {id, severity, message, header, question, options, why}; каждая находка с
                         вариантами — уточняющий вопрос до «Начинаю?» (intake добавляет в follow_up)
  apply_decisions(cfg)   ответы на эти вопросы (idea.decisions.<id> = ключ варианта) → поля run-config (идемпотентно)
  mvp_capacity(cfg)      типовой объём MVP по ответу «MVP» против ёмкости за срок MVP (capacity.py, одна величина
                         project.capacity.day_hours) → {need: [lo, hi], have, fits: yes|tight|no, line}
  traffic_card(doc)      красный/жёлтый светофор (data/typesafe-concept.json) → карточка «что дальше» с вариантом
                         «Продолжить с нарезкой на очереди» (SM 3.3); build_slicing(cfg, doc) → блок slicing
  git_state(path)        no_repo | unborn | normal, origin, текущая и основная ветка (FB-041, SM 6.5)
  ensure_branch(top, b)  создать и переключить ветку прогона до первой записи (FB-034); безопасно: только если сейчас
                         основная ветка или пустой репозиторий, ветки ещё нет; иначе — ничего не трогать и сказать почему
  owner_rules(top)       правила владельца из CLAUDE.md (~/.claude/CLAUDE.md, <repo>/CLAUDE.md, <repo>/.claude/CLAUDE.md):
                         ветка на задачу, слияние сам/по запросу, push, удаление веток, чек-лист TASKS.md (FB-040)

Модуль не импортирует intake. Только стандартная библиотека.
"""
import json
import os
import re
import subprocess
from pathlib import Path

import capacity as cap_mod

# типовой объём MVP в днях разработки по ответу «MVP» (c17) — константы для предупреждения на опросе (FB-054)
MVP_DAYS = {"single_feature": (10, 20), "landing": (3, 7), "concierge": (5, 15), "full": (60, 120)}
MVP_LABELS = {"single_feature": "Одна ключевая функция", "landing": "Лендинг и лист ожидания", "concierge": "Ручной сервис за интерфейсом",
              "full": "Полноценная первая версия"}
WEEKS_PER_MONTH = 52 / 12.0


def _f(cfg):
    return ((cfg.get("idea") or {}).get("facets")) or {}


def _explicit(cfg):
    """id вопросов, на которые владелец ответил сам (не значение по умолчанию, не автопилот)."""
    ans = (cfg.get("idea") or {}).get("answers") or {}
    return {k for k, v in ans.items() if not v.get("default") and not v.get("confirmed_default")}


def _num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def fmt(x):
    s = ("%.1f" % x).rstrip("0").rstrip(".")
    return s.replace(".", ",")


# ---------------------------------------------------------------- ёмкость MVP (FB-054)
def mvp_capacity(cfg):
    f = _f(cfg)
    mvp = f.get("mvp") or "single_feature"
    lo, hi = MVP_DAYS.get(mvp, MVP_DAYS["single_feature"])
    weeks = _num(f.get("mvp_weeks"), 6) or 6
    months = weeks / WEEKS_PER_MONTH
    c = cap_mod.capacity(cfg, months)
    have = c["dev_days"]
    team = c.get("team_size") or 1                          # capacity.py: hours_per_week — на человека, команда умножает
    per_week = c["hours_per_week"] * team * c["dev_share"] / c["day_hours"]
    fits = "yes" if have >= hi else "tight" if have >= lo else "no"
    need_weeks = int(-(-lo // per_week)) if per_week > 0 else None
    line = "%s ≈ %d–%d дн. разработки, а за %s нед. есть ≈ %s дн. (%s ч/нед на разработку, день %s ч)" % (
        MVP_LABELS.get(mvp, mvp), lo, hi, fmt(weeks), fmt(have), fmt(c["hours_per_week"] * team * c["dev_share"]), fmt(c["day_hours"]))
    verdict = {"yes": "помещается", "tight": "впритык: помещается только нижняя граница", "no": "не помещается"}[fits]
    return {"mvp": mvp, "need": [lo, hi], "have": round(have, 1), "weeks": weeks, "fits": fits, "need_weeks": need_weeks,
            "per_week_days": round(per_week, 2), "line": "%s — %s" % (line, verdict), "capacity_line": c["line"]}


# ---------------------------------------------------------------- правила противоречий (FB-053, SM 3.2, 3.4)
def _r_own_community(cfg, ex, f):
    if {"c08", "c10"} <= ex and f.get("niche") == "own_community" and f.get("access") == "none":
        return ("high", "c08 «Сообщество, где я свой» и c10 «Нет, начинаю с нуля» противоречат: в сообществе, где вы свой, доступ к людям обычно есть.",
                "Сообщество", "Вы назвали своё сообщество, но и «доступа к аудитории нет». Что верно?", [
                    ("Есть знакомые в сообществе (Recommended)", "5–20 человек для интервью", "acquaintances", {"idea.facets.access": "acquaintances"}),
                    ("Своя аудитория в сообществе", "Канал или чат, где меня читают", "own_audience", {"idea.facets.access": "own_audience"}),
                    ("Доступа нет: сегмент — узкая ниша", "Сообщество — только ориентир", "no_access", {"idea.facets.niche": "narrow"})])


def _r_mvp_capacity(cfg, ex, f):
    mc = mvp_capacity(cfg)
    if mc["fits"] != "no":
        return None
    weeks = mc["need_weeks"]
    return ("high", "%s. Выберите: одна функция / продлить срок / оставить (риск)." % mc["line"],
            "Ёмкость MVP", "%s ≈ %d–%d дн., а за %s нед. есть ≈ %s дн. разработки. Что меняем?" % (
                MVP_LABELS.get(mc["mvp"], mc["mvp"]), mc["need"][0], mc["need"][1], fmt(mc["weeks"]), fmt(mc["have"])), [
                ("Одна ключевая функция (Recommended)", "MVP — самый узкий сквозной сценарий", "single_feature", {"idea.facets.mvp": "single_feature"}),
                ("Продлить срок до %s нед." % (weeks or "?"), "Объём прежний, выпуск позже", "extend",
                 {"idea.facets.mvp_weeks": weeks} if weeks else {}),
                ("Оставить как есть (риск)", "Риск срыва срока — в отчёт", "risk", {"idea.capacity_ack": "risk"})])


def _r_revenue(cfg, ex, f):
    st, pj = cfg.get("strategy") or {}, cfg.get("project") or {}
    zero = (st.get("budget") or {}).get("variants") == ["zero"]
    hours = _num(f.get("hours_week"), 10)
    if "c29" in ex and f.get("revenue_goal") == "main_income" and zero and (pj.get("team_size") or 1) == 1 and hours <= 20:
        return ("medium", "c29 «Основной доход» при нулевом бюджете, одном человеке и ≤ 20 ч/нед — цель дохода нереалистична для старта.",
                "Цель дохода", "«Основной доход» при нулевом бюджете и %s ч/нед. Какую цель берём на первый год?" % fmt(hours), [
                    ("Окупить расходы (Recommended)", "Реалистичная цель первого года", "break_even", {"idea.facets.revenue_goal": "break_even"}),
                    ("Подработка", "Дополнительный доход", "side_income", {"idea.facets.revenue_goal": "side_income"}),
                    ("Оставить основной доход", "Риск — в отчёт и светофор", "keep", {"idea.revenue_ack": "risk"})])


def _r_b2b_social(cfg, ex, f):
    if {"c06", "c09"} <= ex and f.get("segment") == "b2b" and "social" in (f.get("channels") or []):
        return ("medium", "c06 «Компании (B2B)» и c09 «Соцсети и видео»: решения в компаниях редко принимают через соцсети.",
                "Каналы B2B", "Продукт для компаний, а каналы — соцсети и видео. Что верно?", [
                    ("Каналы найти в исследовании (Recommended)", "Профильные площадки B2B", "research", {"idea.facets.channels": ["research"]}),
                    ("Сегмент — малый бизнес", "Самозанятые и мастера живут в соцсетях", "smb", {"idea.facets.segment": "smb"}),
                    ("Оставить как есть", "Соцсети — для узнаваемости", "keep", {})])


def _r_sensitive_exclusive(cfg, ex, f):
    ans = ((cfg.get("idea") or {}).get("answers") or {}).get("c38") or {}
    if ans.get("exclusive_conflict"):
        others = [x for x in ans.get("answer") or [] if not str(x).startswith("Нет")]
        areas = [x for x in f.get("sensitive") or [] if x and x != "custom"]
        return ("high", "c38: выбраны «Нет, обычные данные» и %s одновременно — варианты взаимоисключающие." % ", ".join("«%s»" % x for x in others),
                "Чувств. обл.", "В «Область» отмечены и «Нет», и %s. Что верно?" % ", ".join("«%s»" % x for x in others), [
                    ("Есть чувствительная область (Recommended)", "Правовой разбор обязателен: %s" % ", ".join(others), "sensitive",
                     {"idea.facets.sensitive": areas or ["custom"], "scope.legal": True}),
                    ("Нет, обычные данные", "Только базовые правила", "none", {"idea.facets.sensitive": [], "scope.legal": False})])


def _r_personal_money(cfg, ex, f):
    pj, st = cfg.get("project") or {}, cfg.get("strategy") or {}
    if str(pj.get("audience") or "public") in ("personal", "circle") and (
            ("c26" in ex and st.get("paid_tier") == "yes") or ("c39" in ex and re.search(r"платящ|доход", str(st.get("success_criteria"))))):
        return ("medium", "Личный режим («только для меня / узкий круг»), но выбрана платная модель или денежный критерий успеха.",
                "Деньги лично", "Приложение для себя, но выбрана платная модель. Что верно?", [
                    ("Без денег: личный инструмент (Recommended)", "Модель — стоимость владения", "personal",
                     {"strategy.monetization": "none", "strategy.paid_tier": "no"}),
                    ("Сначала для себя, потом наружу", "Личный режим и условия выпуска", "then_public",
                     {"project.audience": "personal_then_public", "project.release_outward": True}),
                    ("Публичный продукт", "Полный разбор рынка и денег", "public", {"project.audience": "public"})])


def _r_no_dev(cfg, ex, f):
    pj, st = cfg.get("project") or {}, cfg.get("strategy") or {}
    skills = f.get("skills") or []
    if "c33" in ex and skills and "dev" not in skills and (pj.get("team_size") or 1) == 1 and \
            (st.get("budget") or {}).get("variants") == ["zero"] and not f.get("contractors"):
        return ("medium", "Один человек без навыков разработки и с нулевым бюджетом — кто будет делать продукт?",
                "Кто разраб.", "Разработки среди навыков нет, бюджет нулевой. Кто делает продукт?", [
                    ("Сам с ИИ-помощником (Recommended)", "Учусь по ходу, MVP проще", "self_ai", {"idea.facets.builder": "self_ai"}),
                    ("No-code конструктор", "Без программирования", "nocode", {"idea.facets.builder": "nocode"}),
                    ("Найду подрядчика", "Нужен бюджет", "contractor", {"idea.facets.contractors": True})])


def _r_ai_hardware(cfg, ex, f):
    if f.get("ai") == "core" and f.get("ai_where") in ("local", "local_then_cloud") and f.get("ai_hardware") == "browser_only":
        return ("medium", "ИИ-ядро на локальной модели, но у пользователей «только браузер, без установки».",
                "ИИ и железо", "Модель локальная, а пользователи без установки. Что меняем?", [
                    ("Облачный API с откатом (Recommended)", "Модель в облаке", "cloud", {"idea.facets.ai_where": "cloud"}),
                    ("Требовать установку модели", "Инструкция и проверка железа", "install", {"idea.facets.ai_hardware": "laptop_16_32"}),
                    ("Свой сервер с GPU", "Модель на сервере", "server", {"idea.facets.ai_where": "server"})])


def _r_competitors(cfg, ex, f):
    lst = (cfg.get("sources") or {}).get("competitor_list") or []
    if "c22" in ex and f.get("competitors_known") == "none_claimed" and lst:
        return ("medium", "c22 «Уверен, что аналогов нет», но в запросе названы: %s." % ", ".join(map(str, lst[:4])),
                "Аналоги есть", "Вы указали, что аналогов нет, но в запросе есть %s. Что верно?" % ", ".join(map(str, lst[:3])), [
                    ("Это аналоги, учесть (Recommended)", "Сравнение с ними обязательно", "listed", {"idea.facets.competitors_known": "listed"}),
                    ("Это не аналоги", "Только ориентиры", "refs", {})])


def _r_revenue_model(cfg, ex, f):
    st = cfg.get("strategy") or {}
    if {"c29", "c26"} <= ex and f.get("revenue_goal") == "none" and st.get("paid_tier") == "yes" and \
            str((cfg.get("project") or {}).get("audience") or "public") == "public":
        return ("info", "c29 «Деньги не важны», но c26 — платная модель.", "Доход/модель",
                "Деньги не важны, но модель платная. Что верно?", [
                    ("Бесплатно, донаты (Recommended)", "Без платного уровня", "free", {"strategy.monetization": "donations", "strategy.paid_tier": "no"}),
                    ("Платно, чтобы покрыть расходы", "Цель — окупить расходы", "break_even", {"idea.facets.revenue_goal": "break_even"})])


CONCEPT_CONFLICTS = [
    ("own_community_no_access", _r_own_community),
    ("mvp_capacity", _r_mvp_capacity),
    ("revenue_vs_resources", _r_revenue),
    ("b2b_social", _r_b2b_social),
    ("sensitive_exclusive", _r_sensitive_exclusive),
    ("personal_money", _r_personal_money),
    ("no_dev_skills", _r_no_dev),
    ("ai_local_browser", _r_ai_hardware),
    ("competitors_claimed_none", _r_competitors),
    ("revenue_none_paid", _r_revenue_model),
]
CHECK_HEADERS = {}            # header карточки → id правила (для ответов через concept-apply/update)


def _info_notes(cfg):
    """Связки, требующие уточнений, но не противоречия: ИИ-ядро + личные данные/финансы (SM 2.3)."""
    f = _f(cfg)
    notes = []
    if f.get("ai") == "core" and (f.get("data") in ("personal", "sensitive") or [x for x in f.get("sensitive") or [] if x]):
        notes.append({"id": "ai_core_sensitive", "severity": "info",
                      "message": "ИИ — ядро и личные данные/чувствительная область — юридически чувствительная связка: блок «Предметная "
                                 "область и право» задаётся обязательно (intake.py concept-blocks)."})
    mc = mvp_capacity(cfg)
    if mc["fits"] == "tight":
        notes.append({"id": "mvp_capacity_tight", "severity": "info", "message": "Ёмкость: %s." % mc["line"]})
    return notes


def run_checks(cfg):
    """Все правила → находки (с вариантами — уточняющие вопросы; решённые через idea.decisions — помечены resolved)."""
    f = _f(cfg)
    ex = _explicit(cfg)
    decided = ((cfg.get("idea") or {}).get("decisions")) or {}
    out = []
    for rid, fn in CONCEPT_CONFLICTS:
        try:
            r = fn(cfg, ex, f)
        except Exception as e:                                # noqa: BLE001 — проверка не должна ронять опрос
            r = None
            out.append({"id": rid, "severity": "info", "message": "проверка не выполнена: %s" % e})
        if not r:
            continue
        sev, msg, header, question, opts = r
        CHECK_HEADERS[header] = rid
        out.append({"id": rid, "severity": sev, "message": msg, "header": header, "question": question,
                    "options": [{"label": l, "description": d, "key": k, "set": m} for l, d, k, m in opts],
                    "resolved": rid in decided, "decision": decided.get(rid)})
    return out + _info_notes(cfg)


def apply_decisions(cfg, set_path):
    """idea.decisions {rule: ключ} → значения вариантов (set_path — функция intake.set_path). Повтор безопасен:
    применённые решения помечаются в idea.decisions_applied. → заметки."""
    idea = cfg.setdefault("idea", {})
    dec = idea.get("decisions") or {}
    applied = idea.setdefault("decisions_applied", {})
    notes = []
    if not dec:
        return notes
    snapshot = dict(dec)
    for it in run_checks_all_options(cfg):
        rid = it["id"]
        if rid not in snapshot or applied.get(rid) == snapshot[rid]:
            continue
        key = snapshot[rid]
        opt = next((o for o in it["options"] if o["key"] == key or o["label"] == key or
                    o["label"].replace(" (Recommended)", "") == str(key).replace(" (Recommended)", "")), None)
        if opt is None:                                     # подпись с числом («Продлить срок до 46 нед.») — по началу фразы
            head = re.sub(r"\s*\d.*$", "", str(key)).strip().lower()
            opt = next((o for o in it["options"] if head and len(head) >= 6 and o["label"].lower().startswith(head)), None)
        if opt is None:
            cfg.setdefault("assumptions", []).append("Решение «%s»: свой ответ «%s» — учесть вручную" % (it.get("header", rid), key))
            applied[rid] = key
            continue
        for p, v in opt["set"].items():
            set_path(cfg, p, v)
        applied[rid] = key
        notes.append("%s: %s" % (it.get("header", rid), opt["label"].replace(" (Recommended)", "")))
        cfg.setdefault("assumptions", []).append("Решение владельца до старта — %s: %s" % (it.get("header", rid), opt["label"].replace(" (Recommended)", "")))
    return notes


def run_checks_all_options(cfg):
    """Находки с вариантами для применения решений: снимок idea.checks (варианты по ответам ДО решения) + текущие."""
    saved = [x for x in ((cfg.get("idea") or {}).get("checks") or []) if x.get("options")]
    ids = {x["id"] for x in saved}
    return saved + [x for x in run_checks(cfg) if x.get("options") and x["id"] not in ids]


# ---------------------------------------------------------------- светофор и нарезка на очереди (SM 3.3)
SLICE_QUEUES = [
    ("alpha", "α — один сквозной сценарий", "проверить главную ценность одним сценарием на себе и 3–5 людях",
     "MVP-α работает от начала до конца; дешёвые проверки красных зон пройдены"),
    ("beta", "β — первые пользователи", "закрыть боли первых пользователей и слабые места светофора",
     "α используется регулярно (не реже раза в неделю) и критерий успеха α выполнен"),
    ("v1", "v1 — полная первая версия", "остальной объём MVP по реестру",
     "β удерживает пользователей, ёмкость следующих 2–3 месяцев подтверждена"),
    ("v2", "v2 — расширение", "новые направления и тяжёлые функции (видение)",
     "v1 стабильна; решение владельца о расширении"),
]
WEAK_LABELS = {"pain": "острота боли", "reach": "доступ к аудитории", "switch": "готовность сменить способ", "distinct": "отличие",
               "feasible": "ресурсы и выполнимость", "revenue": "доход", "timing": "время выхода", "ban_risk": "право и запреты"}
WEAK_TESTS = {"pain": "5 интервью о проблеме", "reach": "найти 20 человек из аудитории за неделю", "switch": "фейковая дверь на лендинге",
              "distinct": "сравнение с 3 аналогами на одном сценарии", "feasible": "прототип ядра за 1–2 недели",
              "revenue": "предзаказ или ценовой опрос", "timing": "проверка трендов и событий", "ban_risk": "чек-лист права до разработки"}


def traffic_card(doc):
    """data/typesafe-concept.json → follow_up-карточка при red/yellow (или None при green/нет данных)."""
    v = (doc or {}).get("verdict")
    if v not in ("red", "yellow"):
        return None
    weak = [WEAK_LABELS.get(k, k) for k in (doc.get("weak") or [])][:4]
    label = {"red": "красный", "yellow": "жёлтый"}[v]
    q = "Светофор %s (жизнеспособность %s%s). Что дальше?" % (label, str(doc.get("viability", "—")).replace(".", ","),
                                                              "; слабые места: " + ", ".join(weak) if weak else "")
    return {"header": "Светофор", "question": q, "options": [
        ("Продолжить с нарезкой на очереди (Recommended)", "MVP — один сквозной сценарий; очереди α/β/v1/v2 с условиями входа", "slice"),
        ("Продолжить без изменений", "План как есть, риски — в отчёт", "continue"),
        ("Уточнить идею", "Вернуться к опросу и сузить идею", "refine"),
        ("Остановиться", "Концепцию не продолжать", "stop")], "verdict": v}


def build_slicing(cfg, doc=None):
    """Нарезка на очереди: очереди α, β, v1, v2 с целью, условием входа и ёмкостью; приоритет — снижать слабые места
    светофора дешёвыми проверками. → блок slicing для run-config (C — сущность реестра, B/E — Гант)."""
    h = int(_num((cfg.get("strategy") or {}).get("horizon_months"), 6) or 6)
    split = {"alpha": 1.5, "beta": 1.5, "v1": max(1.0, h - 3.0), "v2": 6.0}
    queues = []
    for qid, name, goal, enter in SLICE_QUEUES:
        months = split[qid]
        c = cap_mod.capacity(cfg, months)
        queues.append({"id": qid, "name": name, "goal": goal, "enter_when": enter, "months": months,
                       "capacity_days": c["dev_days"], "capacity_line": c["line"]})
    weak = [k for k in ((doc or {}).get("weak") or [])]
    return {"enabled": True, "source": "светофор %s" % ((doc or {}).get("verdict") or "—"), "queues": queues,
            "mvp": "один сквозной сценарий (α)", "cut_rule": "в очередь берётся только то, что нужно для её цели; остальное — в следующую очередь",
            "priorities": [{"weak": k, "label": WEAK_LABELS.get(k, k), "cheap_test": WEAK_TESTS.get(k, "дешёвая проверка")} for k in weak]}


# ---------------------------------------------------------------- git (FB-041, FB-034, SM 6.5)
def _git(path, *args, timeout=10):
    try:
        r = subprocess.run(["git", "-C", str(path)] + list(args), capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


def git_state(path):
    """{state: no_repo|unborn|normal, top, branch, default_branch, has_origin, visibility: unknown, dirty}. Только чтение."""
    p = Path(path).expanduser()
    while not p.exists() and p != p.parent:
        p = p.parent
    rc, top, _ = _git(p, "rev-parse", "--show-toplevel")
    if rc != 0 or not top:
        return {"state": "no_repo", "top": None, "branch": None, "default_branch": None, "has_origin": False, "visibility": "unknown"}
    rc_head, _, _ = _git(top, "rev-parse", "--verify", "-q", "HEAD")
    _, branch, _ = _git(top, "symbolic-ref", "--short", "-q", "HEAD")
    _, remotes, _ = _git(top, "remote")
    has_origin = "origin" in remotes.split()
    default = None
    if has_origin:
        rc_d, d, _ = _git(top, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD")
        if rc_d == 0 and d:
            default = d.split("/", 1)[-1]
    if not default:
        for cand in ("main", "master"):
            if _git(top, "rev-parse", "--verify", "-q", "refs/heads/%s" % cand)[0] == 0:
                default = cand
                break
    if not default:
        _, cfg_def, _ = _git(top, "config", "--get", "init.defaultBranch")
        default = cfg_def or ("main" if rc_head != 0 else None)
    _, porcelain, _ = _git(top, "status", "--porcelain", "-uno")
    return {"state": "unborn" if rc_head != 0 else "normal", "top": top, "branch": branch or None, "default_branch": default,
            "has_origin": has_origin, "visibility": "unknown", "dirty": bool(porcelain)}


def git_plan(gs, target):
    """Человеческий план работы с git по состоянию (строки для сводки и references/orchestration.md)."""
    st = gs.get("state")
    if st == "no_repo":
        return ["git: папка не в git-репозитории — работаем без git (результат не версионируется); нужен git — "
                "`git init` и повторить concept-apply (решение владельца)"]
    origin = "origin есть" if gs.get("has_origin") else "origin нет"
    default = gs.get("default_branch") or "main"
    if st == "unborn":
        return ["git: пустой репозиторий (нет коммитов), %s" % origin,
                "план: первый коммит — в ветку %s; основная ветка %s создаётся слиянием из неё (`git switch -c %s` после первого "
                "коммита задачи или `git branch %s %s`), затем `git push -u origin %s`" % (target, default, default, default, target, default)]
    return ["git: обычный репозиторий, текущая ветка %s, основная %s, %s" % (gs.get("branch") or "—", default, origin)]


def ensure_branch(top, target, mode="auto"):
    """Ветка прогона до первой записи (FB-034). mode: auto | none. → (status, message), status:
    current (уже на ней) | created | switched | skipped | failed."""
    if mode == "none" or not top or not target:
        return "skipped", "создание ветки выключено (--branch none)" if mode == "none" else "вне git-репозитория"
    gs = git_state(top)
    if gs["state"] == "no_repo":
        return "skipped", "вне git-репозитория"
    cur = gs.get("branch")
    if cur == target:
        return "current", "ветка %s уже активна" % target
    exists = _git(gs["top"], "rev-parse", "--verify", "-q", "refs/heads/%s" % target)[0] == 0
    default = gs.get("default_branch")
    if exists:
        if gs.get("dirty"):
            return "skipped", "ветка %s уже есть, а в рабочем дереве незакоммиченные изменения — переключитесь вручную (`git switch %s`)" % (target, target)
        rc, _o, err = _git(gs["top"], "switch", target)
        return ("switched", "переключено на существующую ветку %s" % target) if rc == 0 else ("failed", "не удалось переключиться: %s" % err[:200])
    if gs["state"] == "unborn" or cur in (default, "main", "master") or cur is None:
        rc, _o, err = _git(gs["top"], "switch", "-c", target)
        if rc != 0:
            return "failed", "не удалось создать ветку %s: %s" % (target, err[:200])
        return "created", "создана и активна ветка %s (от %s)" % (target, "пустого репозитория" if gs["state"] == "unborn" else cur)
    return "skipped", "текущая ветка %s — не основная (%s): ветку %s не создаю автоматически; создайте её от основной вручную" % (
        cur, default or "main", target)


# ---------------------------------------------------------------- правила владельца из CLAUDE.md (FB-040)
def _claude_files(top, home=None):
    home = Path(home or os.environ.get("HOME") or Path.home())
    cands = [(home / ".claude" / "CLAUDE.md", "~/.claude/CLAUDE.md")]
    if top:
        cands += [(Path(top) / "CLAUDE.md", "./CLAUDE.md"), (Path(top) / ".claude" / "CLAUDE.md", "./.claude/CLAUDE.md")]
    return [(p, label) for p, label in cands if p.is_file()]


def owner_rules(top, home=None):
    """Правила владельца, влияющие на прогон. → {sources: [...], branch_per_task, merge: self|on_request|unknown,
    push_after_merge, delete_branches: ask|keep|auto|unknown, tasks_file, language, lines: [...]}."""
    text, sources = "", []
    for p, label in _claude_files(top, home):
        try:
            text += "\n" + p.read_text(encoding="utf-8", errors="replace")[:60000]
            sources.append(label)
        except OSError:
            continue
    low = text.lower()
    r = {"sources": sources, "branch_per_task": None, "merge": "unknown", "push_after_merge": None, "delete_branches": "unknown",
         "tasks_file": None, "language": None}
    if not sources:
        r["lines"] = []
        return r
    if re.search(r"отдельн\w*\s+ветк|только\s+в\s+отдельной\s+ветке|branch\s+per|separate\s+branch|ветк\w*\s+для\s+доработ", low):
        r["branch_per_task"] = True
    if re.search(r"прямых\s+коммитов\s+в\s+`?main|no\s+direct\s+commits", low):
        r["branch_per_task"] = True
    if re.search(r"вливать[^.\n]{0,80}самостоятельно|сливать[^.\n]{0,80}самостоятельно|merge[^.\n]{0,40}yourself|"
                 r"влит\w*[^.\n]{0,60}не\s+нужно\s+согласи|согласия\s+на\s+влитие\s+не\s+нужно", low):
        r["merge"] = "self"
    elif re.search(r"(?:вливать|сливать|merge)[^.\n]{0,60}(?:по\s+запросу|только\s+с\s+согласия|after\s+approval|ask)", low):
        r["merge"] = "on_request"
    if re.search(r"push[^.\n]{0,60}(?:автоматич|сразу)|сразу\s+push|после\s+влития\s*[—-]?\s*сразу\s+push", low):
        r["push_after_merge"] = True
    if re.search(r"(?:удалять\s+ли|спроси[^.\n]{0,40}удал|без\s+явного\s+«?да»?\s+не\s+удаляй|ask[^.\n]{0,30}delet)", low):
        r["delete_branches"] = "ask"
    elif re.search(r"ветки[^.\n]{0,40}сохраня|keep\s+branches", low):
        r["delete_branches"] = "keep"
    m = re.search(r"`?(TASKS\.md|TODO\.md|CHECKLIST\.md)`?", text)
    if m and re.search(r"чек-?лист|checklist|todo", low):
        r["tasks_file"] = m.group(1)
    if re.search(r"ответы[^.\n]{0,40}русск|по-русски|russian", low):
        r["language"] = "ru"
    lines = []
    if r["branch_per_task"]:
        lines.append("ветка на каждую доработку (прямых коммитов в основную нет)")
    lines.append("слияние в основную — %s" % {"self": "сам, в конце, без отдельного согласия", "on_request": "по запросу владельца",
                                               "unknown": "не указано — спросить"}[r["merge"]])
    if r["push_after_merge"]:
        lines.append("push основной ветки — сразу после слияния")
    lines.append("удаление веток — %s" % {"ask": "спросить владельца", "keep": "не удалять", "auto": "удалять", "unknown": "не указано"}[r["delete_branches"]])
    if r["tasks_file"]:
        lines.append("чек-лист — %s в корне (STRATEGY_TASKS.md не заводить: блок фаз — в %s, init_run.py --tasks-file %s)" % (
            r["tasks_file"], r["tasks_file"], r["tasks_file"]))
    if r["language"] == "ru":
        lines.append("ответы владельцу — по-русски")
    r["lines"] = lines
    return r


def load_verdict(out):
    try:
        return json.loads((Path(out) / "data" / "typesafe-concept.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
