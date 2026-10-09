# -*- coding: utf-8 -*-
"""Квоты на «крайние случаи» (2.9.0): автоматический выбор Fable и effort max.

Зачем. Правила выбора (LOAD_FABLE_HORIZON, MAX_FRONTIER_CONF …) говорят, КОГДА задача подходит под Fable или max, но не
ограничивают, СКОЛЬКО раз это случится. Долгий горизонт — самый дорогой вид работы; если каждая такая задача уходит на Fable
(или на max), расход токенов не ограничен ничем, кроме терпения пользователя. Здесь — счётчик по окнам «сутки» и «неделя»:
исчерпана квота — выбор понижается (fable → opus, max → xhigh) с понятной причиной, а не молча.

Что считается. Только АВТОМАТИЧЕСКИЕ выборы (model_source/effort_source не «user»). Явная просьба пользователя («на fable»,
«effort max») не блокируется и в квоту не входит — это его решение и его расход; в журнале остаётся отметка.
Повторный вызов хука на тот же запрос (ручной хук + хук плагина) квоту не тратит второй раз (ключ — id запроса).
Квоты: TYPESAFE_TRIAGE_FABLE_LIMIT=«сутки/неделя» (по умолчанию 1/3), TYPESAFE_TRIAGE_MAX_LIMIT (2/6); «0» — никогда
автоматически; «off» — без ограничения. Те же ключи fable_limit / max_limit в config.json. Состояние — extremes.json рядом
с state.json (без текста запросов: время, вид, id, источник). Только стандартная библиотека.
"""
import json
import os
import time

DAY_S, WEEK_S = 86400, 7 * 86400
DEFAULTS = {"fable": (1, 3), "max": (2, 6)}      # (сутки, неделя)
ENV = {"fable": "TYPESAFE_TRIAGE_FABLE_LIMIT", "max": "TYPESAFE_TRIAGE_MAX_LIMIT"}
CFG = {"fable": "fable_limit", "max": "max_limit"}
KEEP_S = WEEK_S + DAY_S
DEDUP_S = 600                                      # тот же запрос в пределах 10 мин — тот же выбор, не вторая трата
BUDGET_ENV = "TYPESAFE_TRIAGE_EXTREME_BUDGET_USD"  # потолок --run для fable/max, если не задан --budget
DEFAULT_BUDGET_USD = 10.0


def parse_limit(value, default):
    """«1/3» → (1, 3); «2» → (2, 2·7); «0» → (0, 0); «off» → None (без ограничения); непонятное → default."""
    if value is None:
        return default
    s = str(value).strip().lower()
    if s in ("off", "none", "unlimited", "-", ""):
        return None if s != "" else default
    try:
        if "/" in s:
            d, w = s.split("/", 1)
            d, w = int(d), int(w)
        else:
            d = int(s)
            w = d * 7
    except ValueError:
        return default
    d, w = max(d, 0), max(w, 0)
    return (d, max(w, d))


def limits(kind, config=None):
    """Квота вида ('fable'|'max') → (сутки, неделя) или None (без ограничения). Среда главнее config.json."""
    v = os.environ.get(ENV[kind])
    if v is None and config:
        v = config.get(CFG[kind])
    return parse_limit(v, DEFAULTS[kind])


def budget_usd():
    """Потолок расхода агента (--max-budget-usd) для fable/max в --run, если пользователь не задал --budget."""
    try:
        return float(os.environ.get(BUDGET_ENV, "")) if os.environ.get(BUDGET_ENV, "").strip() else DEFAULT_BUDGET_USD
    except ValueError:
        return DEFAULT_BUDGET_USD


def _path(home):
    return home / "extremes.json"


def load(home):
    try:
        data = json.loads(_path(home).read_text(encoding="utf-8"))
        return [e for e in data.get("events", []) if isinstance(e, dict) and isinstance(e.get("ts"), (int, float))]
    except (OSError, ValueError, AttributeError):
        return []


def save(home, events):
    try:
        home.mkdir(parents=True, exist_ok=True)
        p = _path(home)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"events": events}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
        return True
    except OSError:
        return False


def usage(events, kind, now, auto_only=True):
    """Сколько раз за сутки и за неделю выбран вид. auto_only — только автоматические выборы (они и считаются в квоту)."""
    mine = [e for e in events if e.get("kind") == kind and (not auto_only or e.get("src") == "auto")]
    return (sum(1 for e in mine if now - e["ts"] < DAY_S), sum(1 for e in mine if now - e["ts"] < WEEK_S))


def decide(events, kind, now, pid=None, config=None):
    """→ (разрешено, причина|None, уже учтён). Тот же запрос (pid) в окне DEDUP_S — разрешён без новой траты."""
    lim = limits(kind, config)
    if lim is None:
        return True, None, False
    if pid and any(e.get("id") == pid and e.get("kind") == kind and e.get("src") == "auto" and now - e["ts"] < DEDUP_S for e in events):
        return True, None, True
    day, week = usage(events, kind, now)
    if lim[0] == 0 or lim[1] == 0:
        return False, "автоматический %s отключён (квота 0)" % kind, False
    if day >= lim[0]:
        return False, "квота %s за сутки исчерпана (%d из %d)" % (kind, day, lim[0]), False
    if week >= lim[1]:
        return False, "квота %s за неделю исчерпана (%d из %d)" % (kind, week, lim[1]), False
    return True, None, False


def record(home, events, kind, src, pid, session, now):
    events = [e for e in events if now - e["ts"] < KEEP_S]
    events.append({"ts": int(now), "kind": kind, "src": src, "id": pid, "session": session})
    return save(home, events)


def summary(home, config=None, now=None):
    """Строки для --extremes: квоты, расход за окна, последние события."""
    now = now or time.time()
    ev = load(home)
    out = []
    for kind in ("fable", "max"):
        lim = limits(kind, config)
        d, w = usage(ev, kind, now)
        ud, uw = usage(ev, kind, now, auto_only=False)
        q = "без ограничения" if lim is None else "%d/сутки, %d/неделя" % lim
        out.append("%-5s автоматически: %d за сутки, %d за неделю (квота %s); всего с явными просьбами: %d / %d" % (kind, d, w, q, ud, uw))
    out.append("Потолок --run для fable/max: $%.2f (%s, или --budget)" % (budget_usd(), BUDGET_ENV))
    return out
