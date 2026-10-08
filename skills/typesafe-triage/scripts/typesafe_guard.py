# -*- coding: utf-8 -*-
"""Защита от потери доступа к TypeSafe и ухода баланса в минус: классификация сбоев, паузы, учёт расходов, предупреждения.

Зачем. Баланс TypeSafe прочитать нельзя (эндпоинта нет, проверено), а документация не описывает ответ при нехватке средств.
Поэтому защита построена на том, что можно сделать надёжно:
  1. Первый же сигнал проблемы с оплатой/доступом (HTTP 402; 401/403; тело ответа со словами credit/balance/billing/payment/
     quota/insufficient…; 429 с признаками квоты) = ЖЁСТКАЯ пауза: запросы прекращаются полностью, пока пользователь сам не
     исправит ситуацию и не выполнит `--resume`. Автоматических «проб» при нехватке средств нет — чтобы не уйти в минус.
  2. Сбои сервиса (5xx, 429 как лимит скорости, тайм-ауты, нет сети) = временная пауза с нарастанием 5 мин → 10 → 20 … до 1 ч;
     дальше первый же запрос сам проверяет, ожил ли сервис.
  3. Локальный предохранитель: учёт входных токенов по ответам API × публичная цена ($0.042 за млн) и потолок расходов в месяц
     (по умолчанию $2). Это оценка только по запросам с этой машины, а не баланс; она защищает от неожиданного расхода.
  4. Пользователь предупреждается: `systemMessage` хука показывается прямо в окне, плюс модель получает указание сообщить.
     Напоминание о жёсткой паузе — не чаще раза в remind_hours; о временной — только когда сбои подряд (3, 10).
Состояние: ~/.claude/typesafe-triage/state.json, настройки: config.json там же (права 0600). Каталог можно сменить
переменной TYPESAFE_TRIAGE_HOME (для тестов). Только стандартная библиотека.
"""
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

HOME = Path(os.environ.get("TYPESAFE_TRIAGE_HOME") or (Path.home() / ".claude" / "typesafe-triage"))
PRICE_PER_MTOK_USD = 0.042          # публичная цена: за входные токены, выходные бесплатны
CONSOLE_URL = "https://console.typesafe.ai"
SCRIPT = "~/.claude/skills/typesafe-triage/scripts/typesafe_triage.py"
HARD_KINDS = ("billing", "auth", "forbidden", "manual")   # без автоповтора: нужно действие пользователя
DEFAULT_CONFIG = {
    "monthly_budget_usd": 2.0,      # локальный потолок расходов в месяц (оценка); 0 или меньше — без потолка
    "warn_fraction": 0.8,           # предупредить на этой доле потолка
    "remind_hours": 6,              # как часто напоминать о жёсткой паузе
    "transient_base_s": 60,         # первая временная пауза (всплески TypeSafe короткие), дальше ×2 до transient_max_s
    "transient_max_s": 3600,
}
BILLING_RE = re.compile(
    r"insufficient|credit|balance|billing|payment|quota|funds|subscription|suspend|top.?up|spend.?limit|plan.?limit|out of tokens|"
    r"paid|invoice|overdue|exhaust", re.I)
_LOCK = threading.RLock()


# ---------- файлы состояния ----------
def _read(path, default):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def _write(path, data):
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp%d" % os.getpid())
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError:
        pass  # состояние — вспомогательное: сбой записи не должен ломать работу


def state_path():
    return HOME / "state.json"


def config_path():
    return HOME / "config.json"


def load_state():
    return _read(state_path(), {})


def config():
    cfg = dict(DEFAULT_CONFIG)
    for k, v in _read(config_path(), {}).items():
        if k in cfg and isinstance(v, (int, float)) and not isinstance(v, bool):
            cfg[k] = v
    return cfg


def set_budget(usd):
    c = _read(config_path(), {})
    c["monthly_budget_usd"] = float(usd)
    _write(config_path(), c)


def fingerprint(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8] if key else ""


def month_key(now):
    return time.strftime("%Y-%m", time.localtime(now))


def month_usage(st, now):
    u = st.get("usage", {}).get(month_key(now), {})
    tokens = int(u.get("tokens", 0))
    return {"tokens": tokens, "requests": int(u.get("requests", 0)), "cost_usd": tokens * PRICE_PER_MTOK_USD / 1e6}


# ---------- классификация ответа ----------
def retry_after_s(headers, body):
    """Секунды ожидания из Retry-After / retry-after-ms / тела ответа; None, если не указано."""
    h = {str(k).lower(): v for k, v in (headers or {}).items()}
    try:
        if "retry-after-ms" in h:
            return max(0.0, float(h["retry-after-ms"]) / 1000)
        if "retry-after" in h:
            return max(0.0, float(h["retry-after"]))
    except (TypeError, ValueError):
        pass
    m = re.search(r'"retry_after_ms"\s*:\s*(\d+)', body or "")
    return int(m.group(1)) / 1000 if m else None


def classify_http(code, body, headers=None):
    """HTTP-ответ с ошибкой → (вид, пояснение, секунды_ожидания|None).
    Виды: size (слишком большой вход — не авария), billing, auth, forbidden, rate, outage."""
    text = (body or "")[:600]
    low = text.lower()
    if code == 400 and "max_tokens" in low:
        return "size", text, None
    if code == 402 or (400 <= code < 500 and BILLING_RE.search(low)):
        return "billing", text, None
    if code == 401:
        return "auth", text, None
    if code == 403:
        return "forbidden", text, None
    if code == 429:
        return "rate", text, retry_after_s(headers, body)
    return "outage", "HTTP %d %s" % (code, text[:200]), retry_after_s(headers, body)


# ---------- сообщения пользователю ----------
def message(kind, detail="", until=None, failures=0, cost=None, cap=None):
    d = (" Ответ сервиса: %s" % detail.strip()[:200]) if detail and detail.strip() else ""
    if kind == "billing":
        return ("TypeSafe: похоже, закончились средства или лимит.%s Использование ПРИОСТАНОВЛЕНО (уровень модели — только по локальной эвристике), "
                "чтобы не уйти в минус. Пополните баланс / проверьте лимиты на %s и выполните: python3 %s --resume" % (d, CONSOLE_URL, SCRIPT))
    if kind == "auth":
        return ("TypeSafe: ключ API не принят (401).%s Использование приостановлено. Проверьте TYPESAFE_API_KEY (%s/keys); "
                "пауза снимется сама, когда ключ изменится, либо: python3 %s --resume" % (d, CONSOLE_URL, SCRIPT))
    if kind == "forbidden":
        return ("TypeSafe: доступ запрещён (403) — аккаунт приостановлен или нет прав.%s Использование приостановлено до исправления "
                "на %s; затем: python3 %s --resume" % (d, CONSOLE_URL, SCRIPT))
    if kind == "budget":
        return ("TypeSafe: достигнут локальный потолок расходов $%.2f в месяц (оценка по токенам: $%.4f). Использование приостановлено "
                "до следующего месяца. Поднять потолок: python3 %s --set-budget <USD> и затем --resume" % (cap or 0, cost or 0, SCRIPT))
    if kind == "manual":
        return "TypeSafe: использование отключено вручную%s. Включить: python3 %s --resume" % (d, SCRIPT)
    when = time.strftime("%H:%M", time.localtime(until)) if until else "позже"
    if kind == "rate":
        return "TypeSafe: превышен лимит скорости (429). Пауза до %s, дальше проверю сама.%s" % (when, d)
    return ("TypeSafe не отвечает (%d сбоев подряд).%s Временно не использую его до %s, дальше проверю сама; "
            "работа Claude Code не затронута." % (failures, d, when))


# ---------- решения ----------
def _set_pause(st, kind, now, **extra):
    st["pause"] = dict({"kind": kind, "since": now}, **extra)


def _notice_due(p, now, cfg):
    last = p.get("notified")
    return last is None or now - last >= cfg["remind_hours"] * 3600


def status(key=None, now=None):
    """Можно ли обращаться к TypeSafe прямо сейчас.
    -> {"allowed": bool, "kind": вид|None, "message": текст|None, "notice": текст для пользователя|None}"""
    now = time.time() if now is None else now
    with _LOCK:
        st, cfg = load_state(), config()
        p = st.get("pause")
        changed = False
        out = {"allowed": True, "kind": None, "message": None, "notice": None}
        if p:
            kind = p.get("kind")
            if kind == "auth" and key and p.get("key_fp") and fingerprint(key) != p["key_fp"]:
                st.pop("pause"), st.pop("failures", None)           # ключ заменён — пауза снята
                p, changed = None, True
            elif kind in ("outage", "rate") and now >= p.get("until", 0):
                pass                                                  # пауза вышла: следующий запрос — проверка
            elif kind == "budget" and p.get("month") != month_key(now):
                st.pop("pause")                                       # новый месяц — потолок обнулён
                p, changed = None, True
            elif kind in HARD_KINDS + ("budget", "outage", "rate"):
                msg = message(kind, p.get("detail", ""), p.get("until"), st.get("failures", 0), p.get("cost"), cfg["monthly_budget_usd"])
                out.update(allowed=False, kind=kind, message=msg)
                if kind in HARD_KINDS + ("budget",) and _notice_due(p, now, cfg):
                    out["notice"], p["notified"], changed = msg, now, True
        cap = cfg["monthly_budget_usd"]
        if out["allowed"] and cap > 0:
            cost = month_usage(st, now)["cost_usd"]
            if cost >= cap:
                _set_pause(st, "budget", now, month=month_key(now), cost=cost, notified=now)
                msg = message("budget", cost=cost, cap=cap)
                out.update(allowed=False, kind="budget", message=msg, notice=msg)
                changed = True
        if changed:
            _write(state_path(), st)
        return out


def record_success(tokens, now=None):
    """Учесть успешный запрос. Возвращает текст-уведомление (80 % потолка, сервис ожил) или None."""
    now = time.time() if now is None else now
    with _LOCK:
        st, cfg = load_state(), config()
        notice = None
        u = st.setdefault("usage", {}).setdefault(month_key(now), {"tokens": 0, "requests": 0})
        u["tokens"] += int(tokens or 0)
        u["requests"] += 1
        p = st.get("pause")
        if p and p.get("kind") in ("outage", "rate"):
            st.pop("pause")
        if st.pop("outage_notified", False):
            notice = "TypeSafe снова отвечает — совет по модели возобновлён."
        st.pop("failures", None)
        cap, cost = cfg["monthly_budget_usd"], month_usage(st, now)["cost_usd"]
        if cap > 0 and cost >= cap:
            _set_pause(st, "budget", now, month=month_key(now), cost=cost, notified=now)
            notice = message("budget", cost=cost, cap=cap)
        elif cap > 0 and cost >= cap * cfg["warn_fraction"] and st.get("warned_month") != month_key(now):
            st["warned_month"] = month_key(now)
            notice = "TypeSafe: израсходовано около $%.4f из локального потолка $%.2f на этот месяц (оценка по токенам)." % (cost, cap)
        _write(state_path(), st)
        return notice


def record_failure(kind, detail="", retry_after=None, key=None, now=None):
    """Зафиксировать сбой. Возвращает текст-уведомление для пользователя или None."""
    now = time.time() if now is None else now
    with _LOCK:
        st, cfg = load_state(), config()
        if kind in HARD_KINDS:
            _set_pause(st, kind, now, detail=detail[:300], notified=now, key_fp=fingerprint(key))
            msg = message(kind, detail)
            _write(state_path(), st)
            return msg
        n = st.get("failures", 0) + 1
        st["failures"] = n
        delay = min(cfg["transient_max_s"], max(retry_after or 0, cfg["transient_base_s"] * 2 ** (n - 1)))
        _set_pause(st, "rate" if kind == "rate" else "outage", now, until=now + delay, detail=detail[:300])
        notice = None
        if n in (3, 10):  # единичные сбои не беспокоят; устойчивые — да
            notice = message(st["pause"]["kind"], detail, now + delay, n)
            st["outage_notified"] = True
        _write(state_path(), st)
        return notice


def pause_manual(reason=""):
    with _LOCK:
        st = load_state()
        _set_pause(st, "manual", time.time(), detail=reason[:200], notified=time.time())
        _write(state_path(), st)


def resume():
    """Снять паузу (после исправления ситуации пользователем). Возвращает снятую паузу или None."""
    with _LOCK:
        st = load_state()
        p = st.pop("pause", None)
        st.pop("failures", None)
        st.pop("outage_notified", None)
        _write(state_path(), st)
        return p


def summary(now=None):
    now = time.time() if now is None else now
    st, cfg = load_state(), config()
    return {"pause": st.get("pause"), "failures": st.get("failures", 0), "month": month_key(now),
            "usage": month_usage(st, now), "budget_usd": cfg["monthly_budget_usd"], "state_file": str(state_path())}
