#!/usr/bin/env python3
"""Фаза C2 режима «Идея → концепция»: предпроверка жизнеспособности идеи → data/typesafe-concept.json.

  typesafe_concept.py <OUT> [--dry-run] [--force]

Восемь узких вопросов о жизнеспособности идеи (вероятность «да», 0..1):
  pain         острота проблемы: люди уже тратят время или деньги на обходные пути
  reach        достижимость аудитории: первых 100 пользователей можно найти без большого бюджета
  switch       готовность переключиться с текущего решения
  distinct     заметное отличие от аналогов и заменителей
  feasible     выполнимость MVP ресурсами владельца (команда, время, бюджет, навыки)
  revenue      потенциал модели дохода или устойчивости (покрыть расходы)
  timing       своевременность: рынок и привычки готовы сейчас
  ban_risk     риск запрета, правовых или платформенных блокировок (высокая вероятность — плохо)

Итоговый светофор (viability — среднее семи «хороших» вероятностей, risk — ban_risk):
  red    viability < 0,40, или risk ≥ 0,70, или pain/reach/feasible < 0,25 — стоп: спросить владельца, продолжать ли
  green  viability ≥ 0,60, risk < 0,40 и ни одна из семи не ниже 0,35 — можно идти дальше
  yellow всё остальное — продолжать с оговорками: проверить слабые места первыми экспериментами

Личный режим (run-config project.audience = personal | circle | personal_then_public, SM 4.3) — свои вопросы без
«достижимости аудитории» и «модели дохода»: pain (острота своей боли), faster (решит быстрее обходного пути), build_vs_buy
(нет готового, которое проще взять), feasible, maintain (реально поддерживать в одиночку), payback (окупаемость личных
усилий), data_risk (риск потери данных или решения; высокая вероятность — плохо), ban_risk; risk = max(ban_risk, data_risk).
Выполнимость (feasible) в эвристике считается по единой ёмкости capacity.py (FB-028): дни разработки к сроку MVP против
типового объёма MVP по ответу о составе (одна функция ≈ 10–20 дн., полная версия ≈ 60–120 дн.).

Источник оценок: TypeSafe Jev (source: jev), если задан TYPESAFE_API_KEY и run-config tools.typesafe ≠ off (или --force);
иначе — ЭВРИСТИКА по ответам владельца (source: heuristic, confidence: low), честно помеченная, поле skipped — причина,
по которой Jev не спрашивали. Ошибка API → эвристика и поле api_error. Ключ — только из переменной окружения
TYPESAFE_API_KEY: никуда не пишется и не печатается. В API уходит обезличенный контекст: идея и ответы без путей,
адресов, почты, телефонов и секретоподобных строк. --dry-run — без сети и без записи: печатает вопросы и контекст.
Адрес API — TYPESAFE_API_URL (только для тестов). Только стандартная библиотека.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import typesafe_eval  # noqa: E402  (тот же вызов API: адрес, модель, повторы, SSL)

POSITIVE = ["pain", "reach", "switch", "distinct", "feasible", "revenue", "timing"]
CRITICAL = ["pain", "reach", "feasible"]
THRESHOLDS = {"red_viability": 0.40, "red_risk": 0.70, "red_critical": 0.25, "green_viability": 0.60, "green_risk": 0.40, "green_min": 0.35}
QUESTIONS = {
    "pain": {"type": "noul", "instructions": "Насколько вероятно, что проблема из идеи острая: люди уже тратят заметное время или деньги на обходные пути?",
             "criteria": {"true": "Проблема острая, обходные пути уже существуют", "false": "Проблема слабая или надуманная"}},
    "reach": {"type": "noul", "instructions": "Можно ли найти первых 100 пользователей из целевой аудитории без большого бюджета (сообщества, знакомые, площадки)?",
              "criteria": {"true": "Аудитория достижима дёшево", "false": "Аудиторию трудно найти без денег"}},
    "switch": {"type": "noul", "instructions": "Готовы ли люди отказаться от текущего способа решения ради нового продукта?",
               "criteria": {"true": "Переключение вероятно: выгода заметна, барьер низкий", "false": "Текущее решение устраивает, переключаться не станут"}},
    "distinct": {"type": "noul", "instructions": "Есть ли у идеи заметное для пользователя отличие от существующих аналогов и заменителей?",
                 "criteria": {"true": "Отличие понятно и важно пользователю", "false": "Похоже на уже существующее"}},
    "feasible": {"type": "noul", "instructions": "Выполним ли первый выпуск (MVP) с указанными ресурсами владельца: команда, часы, бюджет, навыки, срок?",
                 "criteria": {"true": "MVP реалистичен с этими ресурсами", "false": "Ресурсов явно не хватит"}},
    "revenue": {"type": "noul", "instructions": "Может ли выбранная модель дохода или устойчивости покрыть расходы продукта в разумный срок?",
                "criteria": {"true": "Модель жизнеспособна", "false": "Денег или поддержки не хватит даже на расходы"}},
    "timing": {"type": "noul", "instructions": "Подходящее ли сейчас время для такого продукта: рынок, технологии и привычки готовы?",
               "criteria": {"true": "Время подходящее", "false": "Слишком рано или поздно"}},
    "ban_risk": {"type": "noul", "instructions": "Есть ли существенный риск запрета, правовых ограничений или блокировки платформами (магазины, мессенджеры, платёжные системы)?",
                 "criteria": {"true": "Риск реален и может остановить продукт", "false": "Риск низкий или управляемый"}},
}
LABELS = {"pain": "Острота проблемы", "reach": "Достижимость аудитории", "switch": "Готовность переключиться", "distinct": "Отличие от аналогов",
          "feasible": "Выполнимость ресурсами владельца", "revenue": "Потенциал модели дохода", "timing": "Своевременность", "ban_risk": "Риск запрета и права"}
VERDICT_LABELS = {"green": "можно идти дальше (go)", "yellow": "продолжать с оговорками", "red": "стоп: спросить владельца, продолжать ли"}
# личный режим (SM 4.3): без вопросов про аудиторию и доход
PERSONAL_AUDIENCES = ("personal", "circle", "personal_then_public")
POSITIVE_PERSONAL = ["pain", "faster", "build_vs_buy", "feasible", "maintain", "payback"]
CRITICAL_PERSONAL = ["pain", "feasible", "maintain"]
RISKS_PERSONAL = ["ban_risk", "data_risk"]
QUESTIONS_PERSONAL = {
    "pain": QUESTIONS["pain"],
    "faster": {"type": "noul", "instructions": "Решит ли продукт задачу владельца быстрее и надёжнее, чем его нынешний обходной путь (таблица, заметки, ручной труд)?",
               "criteria": {"true": "Заметно быстрее или надёжнее обходного пути", "false": "Обходной путь не хуже"}},
    "build_vs_buy": {"type": "noul", "instructions": "Стоит ли делать своё: нет ли готового продукта или библиотеки, которые решают ту же задачу дешевле по времени?",
                     "criteria": {"true": "Своё оправдано: готовое не подходит или дороже", "false": "Проще взять готовое"}},
    "feasible": QUESTIONS["feasible"],
    "maintain": {"type": "noul", "instructions": "Сможет ли владелец в одиночку поддерживать продукт: обновления, данные, зависимости, внешние API?",
                 "criteria": {"true": "Поддержка посильна одному", "false": "Поддержка съест всё время"}},
    "payback": {"type": "noul", "instructions": "Окупятся ли личные усилия: сэкономленное время, деньги или ошибки владельца больше часов на разработку и поддержку?",
                "criteria": {"true": "Усилия окупятся", "false": "Затраты больше пользы"}},
    "data_risk": {"type": "noul", "instructions": "Есть ли существенный риск потери данных, неверного решения по данным продукта или зависимости от внешнего API, который могут закрыть?",
                  "criteria": {"true": "Риск реален", "false": "Риск низкий или управляемый"}},
    "ban_risk": QUESTIONS["ban_risk"],
}
LABELS.update({"faster": "Быстрее обходного пути", "build_vs_buy": "Своё вместо готового", "maintain": "Поддержка в одиночку",
               "payback": "Окупаемость личных усилий", "data_risk": "Риск потери данных и зависимости от API"})
MVP_DAYS = {"single_feature": (10, 20), "landing": (3, 7), "concierge": (7, 15), "full": (60, 120)}   # типовой объём MVP (FB-054)


def audience(cfg):
    a = str(((cfg or {}).get("project") or {}).get("audience") or "public").lower()
    return a if a in PERSONAL_AUDIENCES + ("public",) else "public"


def is_personal(cfg):
    return audience(cfg) in PERSONAL_AUDIENCES


def questions_for(cfg):
    return QUESTIONS_PERSONAL if is_personal(cfg) else QUESTIONS


def capacity_fit(cfg):
    """FB-028/054: (поправка к feasible | None, пояснение) — дни разработки к сроку MVP (capacity.py) против объёма MVP."""
    try:
        import capacity as cap_mod
    except ImportError:
        return None, ""
    fc = ((cfg.get("idea") or {}).get("facets") or {})
    size = MVP_DAYS.get(fc.get("mvp"))
    if not size:
        return None, ""
    weeks = fc.get("mvp_weeks")
    months = (float(weeks) / (52 / 12.0)) if weeks else float(((cfg.get("strategy") or {}).get("horizon_months")) or 6)
    c = cap_mod.capacity(cfg, months)
    ratio = c["dev_days"] / ((size[0] + size[1]) / 2.0)
    adj = 0.12 if ratio >= 1.5 else 0.05 if ratio >= 1 else -0.08 if ratio >= 0.5 else -0.18
    note = "ёмкость ≈ %.0f дн. разработки к сроку MVP против %d–%d дн. объёма MVP" % (c["dev_days"], size[0], size[1])
    dec = ((cfg.get("idea") or {}).get("decisions") or {}).get("mvp_capacity")   # решение владельца до старта (concept_checks)
    if dec:                                            # single_feature / extend уже применены к facets (mvp, mvp_weeks)
        note += "; решение владельца: %s" % {"single_feature": "одна ключевая функция", "extend": "продлить срок",
                                              "risk": "оставить как есть (риск срыва срока принят)"}.get(dec, dec)
    return adj, note
SECRET_RE = re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|sk_live_[A-Za-z0-9_]{10,}|"
                       r"AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,}|\b\d{8,10}:[A-Za-z0-9_-]{30,}\b|"
                       r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})")
PATH_RE = re.compile(r"(?<![\w.~/])(?:~|/(?:Users|home|private|tmp|var|opt|mnt|Volumes|root|srv|data))/[^\s`'\"()«»,;|<>]*|(?<![\w])[A-Za-z]:\\[^\s`'\"()«»,;|<>]+")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)")
URL_CRED_RE = re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@")


def mask(text):
    """Обезличивание текста перед отправкой: секреты, пути, почта, телефоны, логины в URL."""
    s = str(text or "")
    s = SECRET_RE.sub("[скрыто]", s)
    s = URL_CRED_RE.sub(r"\1[скрыто]@", s)
    s = EMAIL_RE.sub("[почта]", s)
    s = PATH_RE.sub("[путь]", s)
    s = PHONE_RE.sub("[телефон]", s)
    return s


def build_state(cfg):
    """Обезличенный контекст идеи: идея, ответы по темам, ресурсы и модель — без путей, авторов и адресов."""
    idea = cfg.get("idea") or {}
    st, pj, pr = cfg.get("strategy") or {}, cfg.get("project") or {}, cfg.get("product") or {}
    answers = []
    for qid, a in sorted((idea.get("answers") or {}).items()):
        v = a.get("answer")
        v = ", ".join(map(str, v)) if isinstance(v, list) else str(v or "")
        answers.append({"theme": a.get("theme"), "question": mask(a.get("question"))[:200], "answer": mask(v.replace(" (Recommended)", ""))[:300],
                        "default": bool(a.get("default"))})
    state = {"idea": mask(idea.get("pitch_v2") or idea.get("pitch"))[:1500], "product_type": pr.get("type"), "markets": st.get("markets"),
             "monetization": mask(st.get("monetization"))[:200], "budget": (st.get("budget") or {}).get("variants"),
             "team_size": pj.get("team_size"), "horizon_months": st.get("horizon_months"), "answers": answers,
             "unanswered_count": len(idea.get("unanswered") or []), "audience": audience(cfg)}
    try:
        import capacity as cap_mod
        state["capacity"] = cap_mod.capacity(cfg, float(st.get("horizon_months") or 6))["line"]
    except (ImportError, TypeError, ValueError):
        pass
    return state


# ---------------------------------------------------------------- эвристика по ответам
def _option_labels():
    """(путь, значение) → подпись варианта банка вопросов: пояснения эвристики — словами владельца, а не кодами."""
    import intake
    out = {}
    for q in intake.CONCEPT_BANK:
        for label, _d, mapping in q[6]:
            for k, v in mapping.items():
                key = (k.replace("idea.facets.", ""), json.dumps(v, ensure_ascii=False, sort_keys=True))
                out.setdefault(key, label.replace(" (Recommended)", ""))
    return out


OPTION_LABELS = _option_labels()


def said(name, value):
    """Подпись ответа для пояснения; нет ответа — «—»."""
    if value in (None, "", []):
        return "—"
    key = (name, json.dumps(value, ensure_ascii=False, sort_keys=True))
    if key in OPTION_LABELS:
        return OPTION_LABELS[key]
    if isinstance(value, list):
        return ", ".join(OPTION_LABELS.get((name, json.dumps([x], ensure_ascii=False)), str(x)) for x in value)
    return str(value)


def _clip(x):
    return round(max(0.05, min(0.95, x)), 2)


def heuristic(cfg):
    """Оценки по ответам владельца без модели: таблицы поправок к нейтральным 0,5; пояснение — какие ответы учтены."""
    idea = cfg.get("idea") or {}
    fc = idea.get("facets") or {}
    st, pj, pr, sc = cfg.get("strategy") or {}, cfg.get("project") or {}, cfg.get("product") or {}, cfg.get("scope") or {}
    answered = set((idea.get("answers") or {}).keys())
    out = {}

    def put(key, p, why, qids):
        known = [q for q in qids if q in answered]
        note = why + ("" if known else " (ответов нет — значения по умолчанию)")
        out[key] = {"p": _clip(p), "note": note, "based_on": known}

    pain = {"acute": 0.75, "moderate": 0.55, "personal": 0.42, "latent": 0.3}.get(fc.get("pain"), 0.5)
    pain += {"daily": 0.08, "rare": -0.03}.get(fc.get("frequency"), 0) + {"money": 0.07, "big_risk": 0.1, "annoyance": -0.1}.get(fc.get("cost_of_pain"), 0)
    put("pain", pain, "острота «%s», частота «%s», цена боли «%s»" % (said("pain", fc.get("pain")), said("frequency", fc.get("frequency")), said("cost_of_pain", fc.get("cost_of_pain"))),
        ["c01", "c03", "c05"])
    reach = {"own_audience": 0.72, "acquaintances": 0.55, "none": 0.4}.get(fc.get("access"), 0.45)
    reach += {"narrow": 0.06, "own_community": 0.1, "broad": -0.05}.get(fc.get("niche"), 0) + (0.05 if fc.get("segment") == "dev" else 0)
    reach += -0.05 if fc.get("network") == "two_sided" else 0
    put("reach", reach, "доступ «%s», сегмент «%s», сеть «%s»" % (said("access", fc.get("access")), said("niche", fc.get("niche")), said("network", fc.get("network"))), ["c10", "c08", "c15"])
    sw = {"manual": 0.6, "free_tools": 0.45, "paid_competitor": 0.5, "nothing": 0.35}.get(fc.get("current"), 0.5)
    sw += {"minutes": 0.06, "network": -0.08}.get(fc.get("time_to_value"), 0) + {"nothing": -0.08, "competitor": -0.03}.get(fc.get("replaces"), 0)
    put("switch", sw, "сейчас решают «%s», время до пользы «%s», заменяет «%s»" % (said("current", fc.get("current")), said("time_to_value", fc.get("time_to_value")), said("replaces", fc.get("replaces"))),
        ["c02", "c13", "c14"])
    ds = {"new_capability": 0.6, "niche_fit": 0.56, "simpler": 0.5, "cheaper": 0.4}.get(fc.get("differentiator"), 0.48)
    ds += {"none_claimed": -0.08}.get(fc.get("competitors_known"), 0) + {"mature": -0.05, "new": 0.03}.get(fc.get("market"), 0)
    put("distinct", ds, "отличие «%s», аналоги «%s», рынок «%s»" % (said("differentiator", fc.get("differentiator")), said("competitors_known", fc.get("competitors_known")), said("market", fc.get("market"))),
        ["c12", "c22", "c24"])
    team = pj.get("team_size") or 1
    cap_adj, cap_note = capacity_fit(cfg)
    fe = 0.55 + (0.08 if team >= 2 else 0) + (cap_adj if cap_adj is not None else {40: 0.12, 15: 0.05, 4: -0.15}.get(fc.get("hours_week"), 0))
    fe += {"landing": 0.12, "concierge": 0.08, "full": -0.15}.get(fc.get("mvp"), 0) + (-0.06 if pr.get("type") == "mobile" and team == 1 else 0)
    fe += (-0.07 if fc.get("ai") == "core" else 0) + (-0.08 if fc.get("network") == "two_sided" else 0)
    fe += (0.05 if "dev" in (fc.get("skills") or []) else -0.1 if fc.get("skills") else 0) + (-0.08 if fc.get("mvp_weeks") == 2 and fc.get("mvp") == "full" else 0)
    put("feasible", fe, "команда %s, время «%s», MVP «%s», форма «%s», ИИ «%s»%s" % (team, said("hours_week", fc.get("hours_week")), said("mvp", fc.get("mvp")), said("product.type", pr.get("type")), said("ai", fc.get("ai")),
                                                                                 "; " + cap_note if cap_note else ""),
        ["c30", "c32", "c17", "c16", "c21", "c33"])
    mon = str(st.get("monetization") or "")
    rv = {"freemium": 0.5, "one_time": 0.45, "commission": 0.45, "donations": 0.28}.get(mon, 0.42)
    rv += {"company": 0.1, "third_party": -0.03, "nobody": -0.1}.get(fc.get("payer"), 0) + {"high": 0.05, "low": -0.04}.get(fc.get("price_band"), 0)
    rv += {"money": 0.07}.get(fc.get("value"), 0) + (0.05 if fc.get("segment") in ("smb", "b2b") else 0)
    put("revenue", rv, "модель «%s», платит «%s», цена «%s»" % (said("strategy.monetization", mon) if mon in ("freemium", "one_time", "commission", "donations") else (mon or "—"), said("payer", fc.get("payer")), said("price_band", fc.get("price_band"))), ["c26", "c28", "c27"])
    tm = {"technology": 0.6, "regulation": 0.58, "habits": 0.56}.get(fc.get("why_now"), 0.5) + {"growing": 0.08, "mature": -0.03, "new": -0.06}.get(fc.get("market"), 0)
    put("timing", tm, "почему сейчас «%s», рынок «%s»" % (said("why_now", fc.get("why_now")), said("market", fc.get("market"))), ["c25", "c24"])
    sens = [x for x in fc.get("sensitive") or [] if x]
    br = 0.15 + 0.2 * len(sens) + (0.15 if fc.get("data") == "sensitive" else 0.05 if fc.get("data") == "personal" else 0)
    br += (0.08 if fc.get("main_risk") == "regulation" else 0) + (0.05 if pr.get("type") in ("bot", "mobile") else 0) + (0.05 if mon == "commission" else 0)
    put("ban_risk", br, "чувствительные области: %s; данные «%s»; форма «%s»%s" % (said("sensitive", sens) if sens else "нет", said("data", fc.get("data")), said("product.type", pr.get("type")),
        "; право в объёме" if sc.get("legal") else ""), ["c38", "c20", "c40", "c16"])
    if is_personal(cfg):                               # SM 4.3: вопросы личного режима вместо аудитории и дохода
        sw_p = out["switch"]["p"]
        put("faster", sw_p + (0.08 if fc.get("current") == "manual" else 0) + (0.05 if fc.get("frequency") == "daily" else 0),
            "сейчас решает «%s», частота «%s»" % (said("current", fc.get("current")), said("frequency", fc.get("frequency"))), ["c02", "c03"])
        put("build_vs_buy", out["distinct"]["p"] + (0.05 if fc.get("competitors_known") == "none_claimed" else 0) - (0.08 if fc.get("current") == "paid_competitor" else 0),
            "отличие «%s», аналоги «%s» — сравнить с готовым (build vs buy)" % (said("differentiator", fc.get("differentiator")), said("competitors_known", fc.get("competitors_known"))),
            ["c12", "c22"])
        put("maintain", 0.55 + (0.08 if team >= 2 else 0) - (0.1 if fc.get("ai") == "core" else 0) - (0.08 if fc.get("platform_dependency") else 0)
            + (0.05 if "dev" in (fc.get("skills") or []) else 0), "команда %s, ИИ «%s», внешняя платформа: %s" % (
                team, said("ai", fc.get("ai")), "да" if fc.get("platform_dependency") else "нет"), ["c30", "c21", "c33"])
        put("payback", 0.5 + {"daily": 0.12, "monthly": 0.03, "rare": -0.05}.get(fc.get("frequency"), 0)
            + {"money": 0.08, "time": 0.05}.get(fc.get("value"), 0) + (cap_adj or 0) / 2,
            "частота «%s», польза «%s»%s" % (said("frequency", fc.get("frequency")), said("value", fc.get("value")), "; " + cap_note if cap_note else ""),
            ["c03", "c11", "c32"])
        put("data_risk", 0.2 + (0.2 if fc.get("data") in ("personal", "sensitive") else 0) + (0.15 if fc.get("platform_dependency") else 0)
            + (0.1 if fc.get("ai") == "core" else 0), "данные «%s», внешняя платформа: %s, ИИ «%s»" % (
                said("data", fc.get("data")), "да" if fc.get("platform_dependency") else "нет", said("ai", fc.get("ai"))), ["c20", "c21"])
        for k in ("reach", "switch", "distinct", "revenue", "timing"):
            out.pop(k, None)
    return out


def verdict(items):
    """Светофор по порогам THRESHOLDS (см. docstring): green | yellow | red, viability, risk, слабые места.
    Личный режим узнаётся по ключам (faster, maintain …): свои «хорошие» вопросы и риск = max(ban_risk, data_risk)."""
    personal = "maintain" in items or "faster" in items
    positive, critical = (POSITIVE_PERSONAL, CRITICAL_PERSONAL) if personal else (POSITIVE, CRITICAL)
    pos = [items[k]["p"] for k in positive if k in items]
    viability = round(sum(pos) / len(pos), 3) if pos else 0.0
    risk = max([items.get(k, {}).get("p", 0.0) for k in (RISKS_PERSONAL if personal else ["ban_risk"])] or [0.0])
    weak = [k for k in positive if k in items and items[k]["p"] < THRESHOLDS["green_min"]]
    t = THRESHOLDS
    if viability < t["red_viability"] or risk >= t["red_risk"] or any(items.get(k, {}).get("p", 1) < t["red_critical"] for k in critical):
        v = "red"
    elif viability >= t["green_viability"] and risk < t["green_risk"] and not weak:
        v = "green"
    else:
        v = "yellow"
    return v, viability, risk, weak


def doc_for(items, source, cfg, skipped=None, api_error=None, model=None):
    v, viability, risk, weak = verdict(items)
    personal = is_personal(cfg)
    qs = questions_for(cfg)
    first = sorted([k for k in (POSITIVE_PERSONAL if personal else POSITIVE) if k in items], key=lambda k: items[k]["p"])[:3]
    if risk >= THRESHOLDS["green_risk"]:
        worst = max((k for k in (RISKS_PERSONAL if personal else ["ban_risk"]) if k in items), key=lambda k: items[k]["p"], default="ban_risk")
        first = [worst] + first[:2]
    return {"version": 1, "date": date.today().isoformat(), "source": source, "model": model or ("jev" if source == "jev" else "heuristic"),
            "confidence": "medium" if source == "jev" else "low", "skipped": skipped, "api_error": api_error,
            "idea": ((cfg.get("idea") or {}).get("name") or (cfg.get("product") or {}).get("name") or ""),
            "questions": [{"key": k, "label": LABELS[k], "text": q["instructions"], "good": "low" if k in ("ban_risk", "data_risk") else "high"} for k, q in qs.items()],
            "items": {k: dict(items[k], label=LABELS[k]) for k in qs if k in items}, "audience": audience(cfg),
            "viability": viability, "risk": risk, "verdict": v, "verdict_label": VERDICT_LABELS[v], "weak": weak,
            "check_first": [LABELS[k] for k in first], "thresholds": THRESHOLDS,
            "note": ("Оценка Jev по обезличенной идее и ответам владельца" if source == "jev" else
                     "Эвристика по ответам владельца без модели: ориентир, не прогноз (confidence: low)")}


def parse_jev(resp, questions=None):
    a = resp.get("answers") or {}
    out = {}
    for k, q in (questions or QUESTIONS).items():
        ans = a.get(k)
        if isinstance(ans, dict) and "noul" in ans:
            p = round(float(ans["noul"]), 3)
            crit = q["criteria"]["true" if p >= 0.5 else "false"]
            out[k] = {"p": p, "note": "Jev: %s" % crit, "based_on": []}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Предпроверка жизнеспособности идеи (TypeSafe Jev или эвристика).")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--dry-run", action="store_true", help="без сети и без записи: показать вопросы и контекст")
    ap.add_argument("--force", action="store_true", help="игнорировать tools.typesafe = off в run-config")
    a = ap.parse_args(argv)
    out_dir = Path(a.out).resolve()
    cfg_path = out_dir / "build" / "run-config.json"
    if not cfg_path.exists():
        print("нет %s" % cfg_path, file=sys.stderr)
        return 1
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    if cfg.get("mode") != "concept":
        print("run-config не в режиме идеи (mode: concept) — для предложений используйте typesafe_eval.py", file=sys.stderr)
        return 1
    state = build_state(cfg)
    out_path = out_dir / "data" / "typesafe-concept.json"
    qs = questions_for(cfg)
    if a.dry_run:
        print("Вопросы (%d): %s" % (len(qs), ", ".join(qs)))
        print("Контекст (обезличенный):")
        print(json.dumps(state, ensure_ascii=False, indent=2))
        print("Запросов было бы: 1 (файл не записан)")
        return 0
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    mode = str((cfg.get("tools") or {}).get("typesafe", "auto")).lower()
    skipped = None
    if mode == "off" and not a.force:
        skipped = "отключено в run-config (tools.typesafe = off)"
    elif not key:
        skipped = "TYPESAFE_API_KEY не задан"
    doc = None
    if not skipped:
        try:
            resp = ask(state, key, questions=qs)
            items = parse_jev(resp, qs)
            if len(items) == len(qs):
                doc = doc_for(items, "jev", cfg, model=resp.get("model") or "jev")
            else:
                skipped = "ответ Jev неполный (%d из %d вопросов)" % (len(items), len(qs))
        except urllib.error.HTTPError as e:
            skipped = "доступ отклонён (HTTP %d)" % e.code if e.code in (401, 403) else None
            api_error = "HTTP %d" % e.code
            doc = doc_for(heuristic(cfg), "heuristic", cfg, skipped=skipped, api_error=api_error)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
            doc = doc_for(heuristic(cfg), "heuristic", cfg, api_error=type(e).__name__)
    if doc is None:
        doc = doc_for(heuristic(cfg), "heuristic", cfg, skipped=skipped)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Жизнеспособность идеи: %s — %s (viability %.2f, риск %.2f; источник %s%s) → %s" % (
        doc["verdict"], doc["verdict_label"], doc["viability"], doc["risk"], doc["source"],
        ", Jev пропущен: " + doc["skipped"] if doc.get("skipped") else "", out_path))
    if doc["verdict"] == "red":
        print("Красный светофор: спросить владельца, продолжать ли (слабые места: %s)" % ", ".join(doc["check_first"]))
    return 0


def ask(state, key, url=None, timeout=typesafe_eval.TIMEOUT_S, questions=None):
    """Тот же запрос, что typesafe_eval.ask, но со своим набором вопросов; ключ уходит только в заголовок."""
    import time
    import urllib.request
    body = json.dumps({"state": state, "model": typesafe_eval.MODEL, "questions": questions or QUESTIONS}).encode("utf-8")
    last = None
    for attempt in range(typesafe_eval.RETRIES + 1):
        req = urllib.request.Request(url or typesafe_eval.API_URL, data=body, method="POST",
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=typesafe_eval.ssl_context()) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in typesafe_eval.TRANSIENT_HTTP or attempt == typesafe_eval.RETRIES:
                raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            if attempt == typesafe_eval.RETRIES:
                raise
        time.sleep(1.5 * (attempt + 1))
    raise last


if __name__ == "__main__":
    raise SystemExit(main())
