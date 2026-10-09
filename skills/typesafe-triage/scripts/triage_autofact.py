# -*- coding: utf-8 -*-
"""2.4.0 (#33): автозапись факта после субагента — хук плагина (hooks/hooks.json): PostToolUse на Agent|Task и
SubagentStop. ОПЦИЯ, по умолчанию выключена: TYPESAFE_TRIAGE_AUTO_FACT=on; пишет только в журнал проекта
triage-log.jsonl, то есть вместе с TYPESAFE_TRIAGE_PROJECT_LOG (журнал выключен — не пишет ничего).

Источники — только документированные поля ввода хуков Claude Code (docs: hooks → PostToolUse, SubagentStop):
  * PostToolUse (tool_name Agent): tool_input {description, prompt, model, effort?}, tool_response {status, agentId,
    resolvedModel, totalTokens, totalDurationMs, totalToolUseCount}. status «completed» (агент на переднем плане) — факт
    пишется сразу; «async_launched» (фоновый агент: расхода в ответе нет) — пишется запись «launch» с agentId.
  * SubagentStop: agent_id, agent_transcript_path. По agent_id находится «launch», расход берётся из служебных полей
    стенограммы субагента (usage последнего ответа — та же мера, что totalTokens; message.model; число вызовов
    инструментов; время первой и последней записи). Текст стенограммы и last_assistant_message не читаются.
Привязка к решению — без догадок при параллельных агентах: (1) метка «triage:<id>» в description или prompt Agent
(заметка подсказывает её, когда опция включена); (2) description вида «<id задачи --batch>: …»; (3) иначе — последнее
решение этой сессии за 6 ч, если к нему ещё не привязан другой агент; (4) иначе факт без привязки (ref «agent:<id>»).
Исход (ok/review/…) автоматически не известен — его добавляет `--fact <id> --outcome …`: ручной факт дополняет
автоматический (triage_projectlog.merged_facts), а не дублирует. Текст запросов и ответов не пишется; сеть не нужна.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import triage_projectlog as plog  # noqa: E402
import triage_session as sess_mod  # noqa: E402

ENV = "TYPESAFE_TRIAGE_AUTO_FACT"
ON_WORDS = ("1", "on", "yes", "true", "да")
AGENT_TOOLS = ("Agent", "Task")
MARK_RX = re.compile(r"\btriage[:#=]\s*([\w.-]{1,64})")
BATCH_RX = re.compile(r"^\s*([\w.-]{1,64}):\s")
BIND_WINDOW_S = 6 * 3600
EFFORTS = plog.EFFORTS


def enabled(environ=None):
    env = os.environ if environ is None else environ
    return str(env.get(ENV, "")).strip().lower() in ON_WORDS


def session_tag(session_id):
    """Тот же хеш сессии, что в решениях журнала (triage_effort.session_tag), без импорта тяжёлых модулей."""
    from triage_effort import session_tag as tag
    return tag(session_id) if isinstance(session_id, str) else None


def _int(v):
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None


def bind(records, tool_input, session, now):
    """Решение, к которому относится вызов Agent → (ref, как привязано). Текст description/prompt не сохраняется."""
    desc = str(tool_input.get("description") or "")
    for text in (desc, str(tool_input.get("prompt") or "")[:4000]):
        m = MARK_RX.search(text)
        if m:
            return m.group(1), "mark"
    decisions = [r for r in records if r.get("kind") == "decision"]
    m = BATCH_RX.match(desc)
    if m and any(r.get("task_id") == m.group(1) for r in decisions):
        return m.group(1), "batch"
    if session:
        mine = [r for r in decisions if r.get("session") == session and now - (r.get("ts") or 0) <= BIND_WINDOW_S]
        if mine:
            last = mine[-1]
            taken = any(r.get("kind") in ("launch", "fact") and r.get("auto") and r.get("ref") == last.get("id")
                        for r in records)
            if not taken:
                return last.get("id"), "session"
    return None, None


def agent_usage(path):
    """Служебные поля стенограммы субагента: tokens (usage последнего ответа: input + cache + output — как totalTokens),
    model, tool_uses, minutes (первая → последняя запись). Сбой — {}."""
    try:
        lines, _ = sess_mod._tail_lines(path, 8 * 1024 * 1024)
    except (OSError, ValueError, TypeError):
        return {}
    first = last = None
    usage, model, tools = None, None, 0
    for ln in lines:
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        ts = rec.get("timestamp")
        if isinstance(ts, str):
            first, last = first or ts, ts
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        if rec.get("type") == "assistant":
            if isinstance(msg.get("usage"), dict):
                usage = msg["usage"]
            if msg.get("model"):
                model = str(msg["model"])
            tools += sum(1 for c in msg.get("content") or [] if isinstance(c, dict) and c.get("type") == "tool_use")
    out = {"tool_uses": tools}
    if usage:
        out["tokens"] = sum(_int(usage.get(k)) or 0 for k in ("input_tokens", "cache_creation_input_tokens",
                                                              "cache_read_input_tokens", "output_tokens"))
    if model:
        out["model"] = model
    mins = _minutes(first, last)
    if mins is not None:
        out["minutes"] = mins
    return out


def _minutes(a, b):
    from datetime import datetime
    try:
        f = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731
        return round(max(0.0, (f(b) - f(a)).total_seconds()) / 60, 1)
    except (TypeError, ValueError, AttributeError):
        return None


def _fact(ref, agent_id, model, effort, tokens, minutes, tool_uses, how):
    rec = {"ts": int(time.time()), "kind": "fact", "ref": str(ref or "agent:%s" % agent_id)[:64], "auto": True,
           "agent": str(agent_id)[:40] if agent_id else None, "model": sess_mod.tier_of(model),
           "effort": effort if effort in EFFORTS else None, "tokens": _int(tokens),
           "minutes": round(minutes, 1) if isinstance(minutes, (int, float)) else None, "tool_uses": _int(tool_uses),
           "linked": how}
    return {k: v for k, v in rec.items() if v is not None}


def on_post_tool_use(data, path, now):
    if data.get("tool_name") not in AGENT_TOOLS:
        return None
    ti = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    tr = data.get("tool_response") if isinstance(data.get("tool_response"), dict) else {}
    status, agent_id = tr.get("status"), tr.get("agentId")
    if status not in ("completed", "async_launched") or not agent_id:
        return None
    records = plog.read(path)
    if any(r.get("auto") and r.get("agent") == str(agent_id) for r in records):
        return None                                            # повтор хука на тот же вызов
    ref, how = bind(records, ti, session_tag(data.get("session_id")), now)
    model = tr.get("resolvedModel") or ti.get("model")
    effort = ti.get("effort") if ti.get("effort") in EFFORTS else None
    if status == "completed":
        ms = tr.get("totalDurationMs")
        rec = _fact(ref, agent_id, model, effort, tr.get("totalTokens"),
                    ms / 60000.0 if isinstance(ms, (int, float)) else None, tr.get("totalToolUseCount"), how)
    else:
        rec = {"ts": int(now), "kind": "launch", "auto": True, "agent": str(agent_id)[:40], "ref": ref,
               "linked": how, "model": sess_mod.tier_of(model), "effort": effort,
               "session": session_tag(data.get("session_id"))}
        rec = {k: v for k, v in rec.items() if v is not None}
    return rec if plog.append(path, rec) else None


def on_subagent_stop(data, path, now):
    agent_id = data.get("agent_id")
    tp = data.get("agent_transcript_path")
    if not agent_id and isinstance(tp, str):
        agent_id = Path(tp).stem.replace("agent-", "", 1)
    if not agent_id:
        return None
    records = plog.read(path)
    launch = next((r for r in reversed(records) if r.get("kind") == "launch" and r.get("agent") == str(agent_id)), None)
    if launch is None:                                         # не наш (или передний план — факт уже записан)
        return None
    if any(r.get("kind") == "fact" and r.get("auto") and r.get("agent") == str(agent_id) for r in records):
        return None                                            # уже записан (повторная остановка того же агента)
    u = agent_usage(os.path.expanduser(tp)) if isinstance(tp, str) else {}
    minutes = u.get("minutes")
    if minutes is None and launch.get("ts"):
        minutes = (now - launch["ts"]) / 60.0
    rec = _fact(launch.get("ref"), agent_id, u.get("model") or launch.get("model"), launch.get("effort"),
                u.get("tokens"), minutes, u.get("tool_uses"), launch.get("linked"))
    return rec if plog.append(path, rec) else None


def handle(data, environ=None, now=None):
    """Ввод хука → записанная запись или None. Выключено, журнал проекта выключен, не тот инструмент — None."""
    if not isinstance(data, dict) or not enabled(environ):
        return None
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    path = plog.log_path(cwd, environ=environ)
    if path is None:
        return None
    now = time.time() if now is None else now
    event = data.get("hook_event_name")
    if event == "PostToolUse":
        return on_post_tool_use(data, path, now)
    if event == "SubagentStop":
        return on_subagent_stop(data, path, now)
    return None


def main():
    """Хук: ничего не печатает и всегда завершается с кодом 0 — журнал вспомогательный, работу не прерывает."""
    try:
        raw = sys.stdin.read()          # ввод дочитывается всегда (Claude Code пишет его целиком); не хранится
        if enabled():
            handle(json.loads(raw))
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    try:                                # Windows: ввод хука — UTF-8 JSON, а консоль по умолчанию не UTF-8
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
