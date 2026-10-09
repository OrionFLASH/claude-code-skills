# -*- coding: utf-8 -*-
"""2.6.0 (#40): отчёт «меняет ли триаж что-то на практике» — локально, без сети.

Берёт журнал решений (~/.claude/typesafe-triage/log.jsonl) и, для сессий из журнала, стенограммы Claude Code
(~/.claude/projects/*/<session_id>.jsonl) и считает:
  * решения: модели, действия, причины («сам: не выше модели сессии»), пропуски и молчание «реже», токены и цену, задержку хука;
  * вызовы Agent из стенограмм после заметок: с model и без, совпадение с рекомендацией, доля промптов с фразой глубины.
Приватность: журнал уже не содержит текста запросов. Стенограммы читает только эта явная команда (хук их так не читает) и берёт
из них имена инструментов, поля model/effort входа Agent и один булев признак «в промпте агента есть фраза глубины» — тексты
не сохраняются и не печатаются. Только стандартная библиотека."""
import json
import os
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

PRICE_PER_MTOK_USD = 0.042
TIERS = ("haiku", "sonnet", "opus", "fable")
NOT_HIGHER_SHARE = 0.9       # от этой доли «сам: не выше модели сессии» отчёт говорит прямо: триаж почти не влияет
NO_MODEL_SHARE = 0.3         # от этой доли вызовов Agent без model — совет указывать model явно
MIN_DECISIONS = 20           # меньше — выводы не делаем


def _read_log(path, since):
    recs = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and (r.get("ts") or 0) >= since:
                    recs.append(r)
    except OSError:
        pass
    return recs


def _pct(n, total):
    return 0.0 if not total else round(100.0 * n / total, 1)


def _median(xs):
    xs = sorted(xs)
    return None if not xs else xs[len(xs) // 2]


def _p90(xs):
    xs = sorted(xs)
    return None if not xs else xs[min(len(xs) - 1, int(len(xs) * 0.9))]


def _iso_ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def scan_transcript(path, since):
    """Вызовы Agent основной сессии из стенограммы → [{ts, model, effort, phrase}] (только служебные поля и булев признак)."""
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"tool_use"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(r, dict) or r.get("isSidechain") or r.get("type") != "assistant":
                    continue
                msg = r.get("message") or {}
                for b in msg.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in ("Agent", "Task"):
                        ts = _iso_ts(r.get("timestamp"))
                        if ts is None or ts < since:
                            continue
                        inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                        out.append({"ts": ts, "model": inp.get("model") if inp.get("model") in TIERS else None,
                                    "effort": inp.get("effort"), "prompt": inp.get("prompt") if isinstance(inp.get("prompt"), str) else ""})
    except OSError:
        pass
    return out


def build(days=7, log_path=None, projects_dir=None, now=None, phrases=(), session_tag=None):
    """→ словарь отчёта. phrases — фразы глубины из заметок (для признака «есть фраза в промпте агента»),
    session_tag — функция session_id → хеш, как в журнале."""
    now = now or time.time()
    since = now - days * 86400
    recs = _read_log(log_path, since)
    decisions = [r for r in recs if r.get("model") and not r.get("skipped") and not r.get("quiet")]
    quiet = [r for r in recs if r.get("quiet")]
    skips = [r for r in recs if r.get("skipped")]
    tokens = sum(int(r.get("tokens") or 0) for r in decisions)
    why = Counter(r.get("action_why") for r in decisions if r.get("action_why"))
    n = len(decisions)
    rep = {
        "days": days, "decisions": n, "quiet": len(quiet), "skips": len(skips),
        "models": dict(Counter(r["model"] for r in decisions)),
        "efforts": dict(Counter(r.get("effort") for r in decisions if r.get("effort"))),
        "actions": dict(Counter(r.get("action") for r in decisions if r.get("action"))),
        "why": dict(why),
        "not_higher_share": _pct(why.get("not_higher", 0), n),
        "skip_reasons": dict(Counter(str(r["skipped"]).split(":")[0][:40] for r in skips)),
        "heuristic": sum(1 for r in decisions if r.get("source") == "heuristic"),
        "secrets": sum(1 for r in recs if r.get("secrets")),
        "tokens": tokens, "usd": round(tokens * PRICE_PER_MTOK_USD / 1e6, 5),
        "avg_tokens": int(tokens / n) if n else 0,
    }
    dec_ms = [r["ms"] for r in decisions if isinstance(r.get("ms"), (int, float))]
    skip_ms = [r["ms"] for r in skips + quiet if isinstance(r.get("ms"), (int, float))]
    rep["latency_ms"] = {"decision_median": _median(dec_ms), "decision_p90": _p90(dec_ms), "skip_median": _median(skip_ms), "measured": len(dec_ms)}

    # --- вызовы Agent из стенограмм ---
    by_session = {}
    for r in decisions:
        if r.get("session"):
            by_session.setdefault(r["session"], []).append(r)
    for lst in by_session.values():
        lst.sort(key=lambda x: x.get("ts") or 0)
    agents = {"calls": 0, "with_model": 0, "no_model": 0, "same": 0, "lower": 0, "higher": 0, "with_phrase": 0, "with_effort": 0, "files": 0}
    pdir = Path(projects_dir) if projects_dir else None
    if pdir and pdir.is_dir() and session_tag and by_session:
        for f in pdir.glob("*/*.jsonl"):
            try:
                if f.stat().st_mtime < since:
                    continue
            except OSError:
                continue
            tag = session_tag(f.stem)
            if tag not in by_session:
                continue
            calls = scan_transcript(f, since)
            if not calls:
                continue
            agents["files"] += 1
            for c in calls:
                prev = [d for d in by_session[tag] if (d.get("ts") or 0) <= c["ts"]]
                if not prev:
                    continue
                rec = prev[-1]
                agents["calls"] += 1
                agents["with_effort"] += 1 if c["effort"] else 0
                agents["with_phrase"] += 1 if any(p and p in c["prompt"] for p in phrases) else 0
                if c["model"] is None:
                    agents["no_model"] += 1
                    continue
                agents["with_model"] += 1
                if rec.get("model") in TIERS:
                    d = TIERS.index(c["model"]) - TIERS.index(rec["model"])
                    agents["same" if d == 0 else "lower" if d < 0 else "higher"] += 1
    rep["agents"] = agents
    rep["advice"] = advice(rep)
    return rep


def advice(rep):
    out = []
    n, ag = rep["decisions"], rep["agents"]
    if n < MIN_DECISIONS:
        return ["Мало данных (решений: %d, нужно от %d): выводы делать рано — увеличьте --days." % (n, MIN_DECISIONS)]
    if rep["not_higher_share"] >= 100 * NOT_HIGHER_SHARE:
        out.append("%.0f %% решений заканчиваются «сам: уровень не выше модели сессии»: при текущей модели сессии триаж почти не влияет на работу. "
                   "Включите делегирование вниз (TYPESAFE_TRIAGE_DELEGATE_DOWN=on), экономный режим (TYPESAFE_TRIAGE_ECONOMY=on — не платить "
                   "задержкой за бесполезные заметки) или выключите хук (TYPESAFE_TRIAGE=off)." % rep["not_higher_share"])
    if ag["calls"] and ag["no_model"] >= NO_MODEL_SHARE * ag["calls"]:
        out.append("%d из %d вызовов Agent после заметок без model — они молча наследуют модель сессии. Добавьте в CLAUDE.md правило "
                   "«при любом вызове Agent указывай model явно» (шаблон — INSTALL.md, шаг 5)." % (ag["no_model"], ag["calls"]))
    if ag["calls"] and not ag["with_effort"] and ag["with_phrase"] < ag["calls"] * 0.5:
        out.append("Фраза глубины есть в промптах %d из %d агентов, а параметра effort у Agent нет: см. строку вызова в заметке "
                   "(с 2.6.0 фраза стоит внутри Agent(...))." % (ag["with_phrase"], ag["calls"]))
    if rep["latency_ms"]["decision_median"] and rep["latency_ms"]["decision_median"] > 1500:
        out.append("Медианная задержка хука на решение %d мс — заметно; экономный режим уберёт её для запросов без риска." % rep["latency_ms"]["decision_median"])
    if not out:
        out.append("Триаж меняет работу: рекомендации расходятся с моделью сессии, предупреждений нет.")
    return out


def render(rep):
    n, ag, lat = rep["decisions"], rep["agents"], rep["latency_ms"]
    L = ["Отчёт typesafe-triage за %d дн.: решений %d, молчание «реже» %d, пропусков %d (локальная эвристика без TypeSafe: %d)"
         % (rep["days"], n, rep["quiet"], rep["skips"], rep["heuristic"])]
    if n:
        L.append("Модели: " + ", ".join("%s %d (%.0f %%)" % (k, v, _pct(v, n)) for k, v in sorted(rep["models"].items(), key=lambda kv: -kv[1])))
        L.append("Действия: " + ", ".join("%s %d" % (k, v) for k, v in sorted(rep["actions"].items(), key=lambda kv: -kv[1])))
        L.append("Причины: " + ", ".join("%s %d" % (k, v) for k, v in sorted(rep["why"].items(), key=lambda kv: -kv[1])[:6]))
        L.append("«сам: не выше модели сессии» — %.1f %% решений" % rep["not_higher_share"])
    if rep["skip_reasons"]:
        L.append("Пропуски: " + ", ".join("%s %d" % (k, v) for k, v in sorted(rep["skip_reasons"].items(), key=lambda kv: -kv[1])[:6]))
    L.append("Секреты: запросов с находками %d (значения не хранятся)" % rep["secrets"])
    L.append("TypeSafe: %d токенов на входе (в среднем %d на решение), ≈ $%.4f по цене $%.3f за млн" % (rep["tokens"], rep["avg_tokens"], rep["usd"], PRICE_PER_MTOK_USD))
    if lat["measured"]:
        L.append("Задержка хука на решение: медиана %d мс, 90-й процентиль %d мс; на пропуск — медиана %s мс (замерено %d; поле ms пишется с 2.6.0)"
                 % (lat["decision_median"], lat["decision_p90"], lat["skip_median"] if lat["skip_median"] is not None else "—", lat["measured"]))
    else:
        L.append("Задержка хука: данных нет (поле ms пишется с 2.6.0).")
    if ag["calls"]:
        L.append("Вызовы Agent после заметок (стенограммы, %d файл.): %d; с model %d, без model %d (наследуют модель сессии); с рекомендацией: "
                 "совпали %d, ниже %d, выше %d; с параметром effort %d; с фразой глубины в промпте %d"
                 % (ag["files"], ag["calls"], ag["with_model"], ag["no_model"], ag["same"], ag["lower"], ag["higher"], ag["with_effort"], ag["with_phrase"]))
    else:
        L.append("Вызовы Agent: в стенограммах сессий из журнала не найдены (или стенограммы недоступны).")
    L.append("Выводы:")
    L += ["  - " + a for a in rep["advice"]]
    return "\n".join(L)
