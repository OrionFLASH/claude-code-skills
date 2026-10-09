# -*- coding: utf-8 -*-
"""2.3.0 (#27): одно действие для основной модели — «сам», Agent(model=…, effort=…) или «спросить» — и одна причина.

Модель и effort (что нужно задаче) считает typesafe_triage + triage_effort. Здесь решается другое: кому выгоднее делать
работу. Детерминированно, без сети, по полям результата триажа, признакам текста (triage_heuristics.action_signals) и
сведениям о сессии (triage_session.session_info). Порядок правил — сверху вниз, первое сработавшее решает:

  1. пользователь просит сделать самому / без субагента                 → сам
  2. неуверенная оценка при высокой цене ошибки (clarify)               → спросить (один уточняющий вопрос)
  3. долгое ожидание (минуты-часы)                                      → сам: фоновый скрипт и проверка, а не субагент
  4. пользователь просит субагента                                     → Agent (триаж подтверждает, а не спорит)
  ·  короткое продолжение с унаследованной оценкой                        → то же действие, что в прошлый раз
  5. общее устройство или сессия (браузер пользователя, CDP, эмулятор)  → сам; делегировать только независимые части
  6. небольшая задача или диалог                                        → сам
  7. нужный уровень выше модели сессии (модель известна)                → Agent
  8. модель сессии неизвестна, нужен opus или выше                      → Agent, с оговоркой «если ты уже X — сам»
  9. большая изолируемая задача, контекст передаётся недорого           → Agent (несколько — если части независимы)
 9б. опция «делегирование вниз» (2.6.0, #36): рекомендован уровень НИЖЕ модели
     сессии, задача рутинная/изолируемая, контекст дешёвый, риска нет         → Agent на рекомендованном уровне («дешевле»)
 10. продолжение с накопленным контекстом (передавать дорого)           → сам
 11. иначе                                                              → сам
Для Agent с haiku/fable или effort low/max без согласия пользователя действие — «спросить» (один AskUserQuestion),
а ответ «нет» ведёт к безопасной замене (haiku → sonnet, fable → opus, low → medium, max → xhigh) или к «сам».
"""
import re

TIERS = ("haiku", "sonnet", "opus", "fable")
REASON_MAX_WORDS = 15
SMALL_TS = 0.34          # сложность и рассуждение TypeSafe не выше — мелочь
SMALL_FLAG = 0.6         # … или уверенное «только чтение» / «механика»
SMALL_TEXT = 0.30        # без TypeSafe: оси текста не выше
BIG_TS = 0.85            # сложность или объём TypeSafe от — большая задача
BIG_PATHS = 5            # … или столько файлов в тексте
BIG_ITEMS = 6            # … или столько пунктов
HISTORY_CONTEXT = 3      # столько оценённых запросов сессии — контекст уже накоплен
FACTS_HIGH = 30          # 2.4.0: столько фактов (успешных результатов инструментов, кроме записи) после сжатия — тоже
DIALOG_TURNS = 4         # 2.4.0: сессия-диалог (мало работы с файлами) с таким числом реплик — тоже
DOWN_RISK_MAX = 0.6      # 2.6.0 (#36): делегирование вниз — только при риске и необратимости TypeSafe не выше (2.6.1: 0,6 — перевод строк оценивается ≈ 0,57)
DOWN_MECH = 0.45         # 2.6.1: рутина для делегирования вниз — «механика»/«только чтение» не ниже (общий порог мелочи SMALL_FLAG строже)
DOWN_ITEMS = 3           # … изолируемая работа: столько пунктов/файлов в тексте, либо рутина (механика/чтение), либо части независимы
DOWN_PATHS = 2
KINDS = ("self", "agent", "ask")


def words(text):
    """Число слов (тире и знаки препинания не считаются)."""
    return len([w for w in re.split(r"\s+", text or "") if re.search(r"\w", w)])


def _val(r, k):
    x = (r.get("metrics") or {}).get(k)
    return x.get("value") if isinstance(x, dict) else None


def is_small(r, a):
    """Мелочь или диалог: короткий вопрос-реплика, либо по TypeSafe лёгкая работа без признаков риска."""
    if a.get("dialog"):
        return True
    sig = r.get("signals") or {}
    if sig.get("critical"):
        return False
    c, rs = _val(r, "complexity"), _val(r, "reasoning")
    if c is not None:
        light = (rs is not None and rs <= SMALL_TS) or (_val(r, "mechanical") or 0) >= SMALL_FLAG \
            or (_val(r, "read_only") or 0) >= SMALL_FLAG
        return c <= SMALL_TS and light
    ax = sig.get("axes") or {}
    return ax.get("complexity", 1.0) < SMALL_TEXT and ax.get("reasoning", 1.0) < SMALL_TEXT


def is_big(r, a):
    sig = r.get("signals") or {}
    c, b = _val(r, "complexity"), _val(r, "breadth")
    if (c or 0) >= BIG_TS or (b or 0) >= BIG_TS:
        return True
    return sig.get("paths", 0) >= BIG_PATHS or sig.get("items", 0) >= BIG_ITEMS or bool((sig.get("effort") or {}).get("scope"))


def is_isolated(r, a):
    """2.6.0 (#36): рутинная изолируемая работа, которую можно отдать субагенту дешевле: механика или чтение по TypeSafe,
    несколько однотипных пунктов или файлов, либо независимые части (переводы, проверки по списку, правки в нескольких файлах)."""
    sig = r.get("signals") or {}
    return ((_val(r, "mechanical") or 0) >= DOWN_MECH or (_val(r, "read_only") or 0) >= DOWN_MECH
            or sig.get("items", 0) >= DOWN_ITEMS or sig.get("paths", 0) >= DOWN_PATHS or a.get("parallel", 0) >= 2
            or a.get("units", 0) >= DOWN_ITEMS)


def is_risky(r):
    sig = r.get("signals") or {}
    return bool(sig.get("critical")) or (_val(r, "risk") or 0) > DOWN_RISK_MAX or (_val(r, "irreversible") or 0) > DOWN_RISK_MAX


def context_cost(r, a, sess, continuation):
    """Стоимость передачи контекста субагенту: high — запрос опирается на накопленное (продолжение, «как обсуждали»)
    в длинной сессии, при многих накопленных фактах или в сессии-диалоге; medium — опирается, накоплено немного;
    low — задача самодостаточна. 2.4.0 (#33): факты и профиль — из служебных полей стенограммы (triage_session.work):
    договорённости диалога субагент сам не перечитает, а файлы перечитает — поэтому «чтение» цену не поднимает."""
    refs = bool(a.get("refs") or continuation or r.get("inherited"))
    if not refs:
        return "low"
    w = (sess or {}).get("work") or {}
    if (sess or {}).get("long") or (r.get("history_n") or 0) >= HISTORY_CONTEXT or (w.get("facts") or 0) >= FACTS_HIGH:
        return "high"
    if w.get("profile") == "dialog" and (w.get("user_turns") or 0) >= DIALOG_TURNS:
        return "high"
    return "medium"


def context_reason(sess):
    """Причина «сам: контекст дорого передавать» (≤ 15 слов) с числом фактов или пометкой диалога, если они известны."""
    w = (sess or {}).get("work") or {}
    if (w.get("facts") or 0) >= FACTS_HIGH:
        return "продолжение: в контексте %d фактов — передавать их субагенту дорого" % w["facts"]
    if w.get("profile") == "dialog":
        return "продолжение диалога: договорённости из разговора субагенту не передать дёшево"
    return "продолжение: контекст накоплен, передавать его дорого"


def _confirm_what(r):
    parts = []
    if r.get("confirm"):
        parts.append(r["model"])
    if r.get("effort_confirm"):
        parts.append("effort %s" % r.get("effort"))
    return " и ".join(parts)


def decide(r, a=None, sess=None, continuation=False, opts=None):
    """Результат триажа + признаки текста + сессия → действие (dict). Чистая функция, без побочных эффектов.
    opts (2.6.0): {"delegate_down": bool} — опция делегирования вниз (по умолчанию выключена)."""
    a, sess, opts = a or {}, sess or {}, opts or {}
    tier, e = r.get("model") or "sonnet", r.get("effort") or "high"
    m_conf, e_conf = bool(r.get("confirm")), bool(r.get("effort_confirm"))
    mfb = r.get("fallback") if m_conf else tier
    efb = r.get("effort_fallback") if e_conf else e
    st = sess.get("tier") if sess.get("tier") in TIERS else None
    shared = list(r.get("shared_state") or [])
    small, big = is_small(r, a), is_big(r, a)
    cost = context_cost(r, a, sess, continuation)
    higher = st is not None and tier in TIERS and TIERS.index(tier) > TIERS.index(st)
    lower = st is not None and tier in TIERS and TIERS.index(tier) < TIERS.index(st)
    src = sess.get("model_source") or ""
    hints = []
    if a.get("wait"):
        hints.append("wait")
    if shared:
        hints.append("shared")
    w = sess.get("work") or {}
    base = {"session_tier": st, "session_source": src or None, "context_cost": cost, "small": small, "big": big,
            "wait": a.get("wait"), "parallel": a.get("parallel", 0), "user": a.get("agent_req"),
            "facts": w.get("facts"), "profile": w.get("profile")}

    def out(kind, why, reason, **kw):
        d = dict(base, kind=kind, why=why, reason=reason, hints=hints + kw.pop("extra", []), agent=None, fallback=None,
                 conditional=False)
        d.update(kw)
        return d

    def delegate(why, reason, conditional=False):
        extra = ["parallel"] if a.get("parallel", 0) >= 2 else []
        run = {"model": tier, "effort": e}
        if m_conf or e_conf:
            keep_self = st is not None and mfb in TIERS and TIERS.index(mfb) <= TIERS.index(st) and why not in ("user_agent", "big")
            if why == "cheaper":   # отказ от haiku → сам; отказ только от effort low/max → агент с безопасным effort
                keep_self = bool(m_conf)
            fb = {"kind": "self"} if keep_self else {"kind": "agent", "model": mfb, "effort": efb}
            return out("ask", "confirm", "%s: только с согласия пользователя" % _confirm_what(r), agent=run, fallback=fb,
                       then=why, conditional=conditional, extra=extra)
        return out("agent", why, reason, agent=run, conditional=conditional, extra=extra)

    if a.get("agent_req") == "self":
        return out("self", "user_self", "пользователь просит сделать самому, без субагента")
    if r.get("clarify"):
        return out("ask", "clarify", "неуверенная оценка при высокой цене ошибки: ОДИН короткий уточняющий вопрос")
    if a.get("wait"):
        return out("self", "wait", "долгое ожидание — фоновый скрипт и проверка, а не субагент")
    if a.get("agent_req") == "agent":
        return delegate("user_agent", "пользователь просит субагента — делегируй")
    prev = (r.get("prev") or {}).get("action")
    if prev == "ask" and (r.get("prev") or {}).get("why") == "confirm":   # спрашивали о согласии на агента — работа у агента
        prev = "agent"
    if continuation and r.get("inherited") and prev in ("self", "agent"):   # «продолжай …»: кто делал, тот и продолжает
        if prev == "agent" and not shared:
            return delegate("continuation", "продолжение предыдущей задачи — решение прежнее")
        return out("self", "continuation", "продолжение предыдущей задачи — решение прежнее")
    if shared:
        return out("self", "shared", "общее устройство или сессия — одно взаимодействие за раз")
    if small:
        return out("self", "small", "небольшая задача или диалог — быстрее самому")
    if higher:
        how = " (по настройкам)" if src.startswith("настройки") else ""   # settings.json не знает про --model и /model
        return delegate("higher", "нужен %s, а модель сессии %s%s ниже" % (tier, st, how))
    if st is None and tier in TIERS and TIERS.index(tier) >= TIERS.index("opus"):
        return delegate("unknown_session", "нужен %s; модель сессии хуку неизвестна — если ты уже %s или выше, делай сам"
                        % (tier, tier), conditional=True)
    if big and cost != "high":
        return delegate("big", "большая изолируемая задача — субагент сбережёт контекст сессии")
    if opts.get("delegate_down") and lower and cost != "high" and is_isolated(r, a) and not is_risky(r):
        return delegate("cheaper", "%s достаточно, задача изолируемая — субагент дешевле" % tier)
    if cost == "high":
        return out("self", "context", context_reason(sess))
    if st is not None:
        return out("self", "not_higher", "уровень %s не выше модели сессии (%s)" % (tier, st))
    return out("self", "default", "хватит %s; модель сессии хуку неизвестна" % tier)
