# -*- coding: utf-8 -*-
"""2.4.0 (#33): автозапись факта хуком плагина (PostToolUse Agent, SubagentStop) — опция, выкл. по умолчанию; привязка
к решению без догадок (метка triage:<id>, id задачи --batch, единственный агент после решения сессии); ручной --fact
дополняет автоматический; признаки сессии из служебных полей стенограммы (доля чтения/записи, накопленные факты,
профиль, контекст в токенах) и их влияние на стоимость передачи контекста. Офлайн. pytest test_typesafe_autofact.py"""
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import triage_action as act
import triage_autofact as af
import triage_effort as eff
import triage_projectlog as plog
import triage_session as sess
import typesafe_triage as t

HERE = Path(__file__).parent
SECRET = "Секретное поручение про клиента Ромашка, пароль hunter2"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(t.guard, "HOME", tmp_path / "guard")
    for k in ("TYPESAFE_API_KEY", "TYPESAFE_TRIAGE", af.ENV, plog.ENV):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(eff, "session_effort", lambda cwd=None: None)


def repo(tmp_path):
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    return root


ON = {af.ENV: "on", plog.ENV: "on"}


def post(root, agent_id, status="completed", desc="Разбор логов", prompt=SECRET, session="sess-1", **resp):
    tr = {"status": status, "agentId": agent_id, "resolvedModel": "claude-opus-5-5"}
    if status == "completed":
        tr.update(totalTokens=48211, totalDurationMs=150000, totalToolUseCount=7, content=[{"type": "text", "text": SECRET}])
    else:
        tr.update(description=desc, prompt=prompt, outputFile="/tmp/x.output")
    tr.update(resp)
    return {"hook_event_name": "PostToolUse", "session_id": session, "cwd": str(root), "tool_name": "Agent",
            "tool_input": {"description": desc, "prompt": prompt, "model": "opus", "effort": "high"}, "tool_response": tr}


def agent_transcript(path, model="claude-sonnet-5-5"):
    recs = [{"type": "user", "isSidechain": True, "agentId": "x", "timestamp": "2026-10-09T10:00:00.000Z",
             "message": {"role": "user", "content": SECRET}},
            {"type": "assistant", "isSidechain": True, "timestamp": "2026-10-09T10:03:00.000Z", "message": {
                "model": model, "content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/s"}}],
                "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000,
                          "output_tokens": 5}}},
            {"type": "assistant", "isSidechain": True, "timestamp": "2026-10-09T10:12:30.000Z", "message": {
                "model": model, "content": [{"type": "text", "text": SECRET}],
                "usage": {"input_tokens": 2, "cache_creation_input_tokens": 3196, "cache_read_input_tokens": 143889,
                          "output_tokens": 8}}}]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n", encoding="utf-8")
    return str(path)


def stop(root, agent_id, tp, session="sess-1"):
    return {"hook_event_name": "SubagentStop", "session_id": session, "cwd": str(root), "agent_id": agent_id,
            "agent_type": "general-purpose", "agent_transcript_path": tp, "last_assistant_message": SECRET,
            "stop_hook_active": False}


def log_text(root):
    p = root / plog.FILE_NAME
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ---------- опция ----------
def test_off_by_default_and_needs_project_log(tmp_path):
    root = repo(tmp_path)
    assert af.handle(post(root, "a1"), environ={}) is None
    assert af.handle(post(root, "a1"), environ={af.ENV: "on"}) is None          # журнал проекта выключен — не пишем
    assert not (root / plog.FILE_NAME).exists()
    assert af.handle({"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": str(root)}, environ=ON) is None


# ---------- передний план: факт сразу ----------
def test_foreground_agent_writes_fact_with_mark_and_no_text(tmp_path):
    root = repo(tmp_path)
    rec = af.handle(post(root, "a1", desc="triage:P7 проверка расчёта"), environ=ON)
    assert rec == dict(rec, kind="fact", ref="P7", auto=True, agent="a1", model="opus", effort="high", tokens=48211,
                       minutes=2.5, tool_uses=7, linked="mark")
    assert af.handle(post(root, "a1", desc="triage:P7 проверка расчёта"), environ=ON) is None    # повтор того же вызова
    raw = log_text(root)
    for word in ("Ромашка", "hunter2", "Секретное", "проверка расчёта"):
        assert word not in raw


# ---------- фон: launch → SubagentStop ----------
def test_background_agent_launch_then_stop_uses_service_fields(tmp_path):
    root = repo(tmp_path)
    launch = af.handle(post(root, "a9bf37af36ebc0f68", status="async_launched", desc="triage:1a2b3c4d5e x"), environ=ON)
    assert launch["kind"] == "launch" and launch["ref"] == "1a2b3c4d5e" and launch["model"] == "opus"
    tp = agent_transcript(tmp_path / "s" / "subagents" / "agent-a9bf37af36ebc0f68.jsonl")
    fact = af.handle(stop(root, "a9bf37af36ebc0f68", tp), environ=ON)
    assert fact == dict(fact, kind="fact", ref="1a2b3c4d5e", agent="a9bf37af36ebc0f68", model="sonnet", effort="high",
                        tokens=147095, minutes=12.5, tool_uses=1, auto=True, linked="mark")
    assert af.handle(stop(root, "a9bf37af36ebc0f68", tp), environ=ON) is None                  # повторная остановка
    assert af.handle(stop(root, "чужой", tp), environ=ON) is None                              # не наш агент
    no_id = stop(root, None, tp)                                                               # id из имени файла
    assert af.handle(no_id, environ=ON) is None                                                # (уже записан)
    raw = log_text(root)
    assert "Ромашка" not in raw and "hunter2" not in raw


def test_stop_without_readable_transcript_uses_launch_time(tmp_path):
    root = repo(tmp_path)
    af.handle(post(root, "b1", status="async_launched"), environ=ON, now=1000.0)
    f = af.handle(stop(root, "b1", str(tmp_path / "нет.jsonl")), environ=ON, now=1000.0 + 600)
    assert f["minutes"] == 10.0 and "tokens" not in f and f["ref"] == "agent:b1" and "linked" not in f


# ---------- привязка к решению ----------
def test_binding_session_decision_once_batch_prefix_and_unlinked(tmp_path):
    root = repo(tmp_path)
    p = root / plog.FILE_NAME
    r = {"model": "opus", "effort": "high", "source": "typesafe", "confidence": "высокая", "action": {"kind": "agent"}}
    plog.append(p, plog.decision_record("d1", r, "hook", session=eff.session_tag("sess-1")))
    first = af.handle(post(root, "c1", status="async_launched"), environ=ON)
    second = af.handle(post(root, "c2", status="async_launched"), environ=ON)          # параллельный, без метки
    assert (first["ref"], first["linked"]) == ("d1", "session")
    assert "ref" not in second and "linked" not in second                               # не угадываем чужое решение
    other = af.handle(post(root, "c3", status="async_launched", session="другая"), environ=ON)
    assert "ref" not in other
    plog.append(p, plog.decision_record("P4", r, "batch", task_id="P4"))
    b = af.handle(post(root, "c4", status="async_launched", desc="P4: Спроектируй и проведи миграцию"), environ=ON)
    assert (b["ref"], b["linked"]) == ("P4", "batch")
    tp = agent_transcript(tmp_path / "agent-c2.jsonl")
    assert af.handle(stop(root, "c2", tp), environ=ON)["ref"] == "agent:c2"


def test_old_session_decision_is_not_bound(tmp_path):
    root = repo(tmp_path)
    r = {"model": "opus", "effort": "high", "action": {"kind": "agent"}}
    rec = plog.decision_record("old", r, "hook", session=eff.session_tag("sess-1"))
    rec["ts"] -= af.BIND_WINDOW_S + 10
    plog.append(root / plog.FILE_NAME, rec)
    assert "ref" not in af.handle(post(root, "d1", status="async_launched"), environ=ON)


# ---------- ручной факт дополняет автоматический ----------
def test_manual_fact_completes_auto_fact_in_summaries(tmp_path, monkeypatch, capsys):
    root = repo(tmp_path)
    p = root / plog.FILE_NAME
    r = {"model": "opus", "effort": "high", "source": "typesafe", "confidence": "высокая", "action": {"kind": "agent"}}
    plog.append(p, plog.decision_record("P1", r, "batch", task_id="P1"))
    af.handle(post(root, "e1", desc="triage:P1 x"), environ=ON)
    monkeypatch.chdir(root)
    assert t.main(["x", "--fact", "P1", "--outcome", "review", "--review-issues", "2"]) == 0
    facts = plog.merged_facts(plog.read(p))
    assert len(facts) == 1 and facts[0]["outcome"] == "review" and facts[0]["tokens"] == 48211 and facts[0]["review_issues"] == 2
    lines = "\n".join(plog.summary(p))
    assert "фактов 1 (автоматических 1, из них с исходом 1)" in lines and "opus/high: фактов 1" in lines
    assert "сопоставлено с решениями: 1 из 1" in lines
    af.handle(post(root, "e2", desc="triage:P1 y"), environ=ON)              # второй агент того же решения — свой факт
    assert len(plog.merged_facts(plog.read(p))) == 2


# ---------- скрипт хука ----------
def test_hook_script_is_silent_and_always_zero(tmp_path):
    root = repo(tmp_path)
    env = dict(os.environ, **ON)
    payload = json.dumps(post(root, "f1", desc="triage:Q1 z"), ensure_ascii=False)
    r = subprocess.run([sys.executable, "-B", str(HERE / "triage_autofact.py")], input=payload, capture_output=True,
                       text=True, encoding="utf-8", env=env, timeout=60, cwd=str(tmp_path))
    assert r.returncode == 0 and r.stdout == "" and json.loads(log_text(root).splitlines()[-1])["ref"] == "Q1"
    bad = subprocess.run([sys.executable, "-B", str(HERE / "triage_autofact.py")], input="{не json", capture_output=True,
                         text=True, env=env, timeout=60)
    assert bad.returncode == 0 and bad.stdout == ""
    off = dict(os.environ)
    off.pop(af.ENV, None)
    o = subprocess.run([sys.executable, "-B", str(HERE / "triage_autofact.py")], input=payload, capture_output=True,
                       text=True, encoding="utf-8", env=off, timeout=60)
    assert o.returncode == 0 and len(log_text(root).splitlines()) == 1


def test_plugin_hooks_json_registers_autofact():
    data = json.loads((HERE.parent / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    assert "typesafe_triage.py" in data["UserPromptSubmit"][0]["hooks"][0]["command"]
    post_hooks = data["PostToolUse"][0]
    assert post_hooks["matcher"] == "Agent|Task" and "triage_autofact.py" in post_hooks["hooks"][0]["command"]
    assert "triage_autofact.py" in data["SubagentStop"][0]["hooks"][0]["command"]
    for groups in data.values():
        for g in groups:
            for h in g["hooks"]:
                assert h["type"] == "command" and h["timeout"] <= 10 and "${CLAUDE_PLUGIN_ROOT}" in h["command"]


def test_note_asks_for_mark_only_when_autofact_on(monkeypatch):
    r = {"model": "opus", "effort": "high", "source": "typesafe", "confidence": "высокая", "decision_id": "1a2b3c4d5e",
         "action": {"kind": "agent", "why": "higher", "reason": "нужен opus", "agent": {"model": "opus", "effort": "high"},
                    "hints": []}}
    assert "triage:" not in t.hook_context(r)
    monkeypatch.setenv(af.ENV, "on")
    assert "метку «triage:1a2b3c4d5e»" in t.hook_context(r)
    s = dict(r, action=dict(r["action"], kind="self"))
    assert "triage:" not in t.hook_context(s)


# ---------- признаки сессии из служебных полей ----------
def session_transcript(path, reads=6, writes=1, shells=2, turns=2, compact_first=False, usage=None):
    recs = []
    if compact_first:
        recs += [{"type": "assistant", "message": {"model": "claude-opus-5-5", "content": [
            {"type": "tool_use", "id": "old%d" % i, "name": "Read", "input": {}} for i in range(50)]}},
            {"type": "system", "subtype": "compact_boundary", "content": "Conversation compacted"}]
    recs.append({"type": "user", "message": {"role": "user", "content": SECRET}})
    for i in range(turns - 1):
        recs.append({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": SECRET}]}})
    recs.append({"type": "user", "isMeta": True, "message": {"role": "user", "content": [{"type": "text", "text": "мета"}]}})
    n = 0
    for name, count in (("Read", reads), ("Edit", writes), ("Bash", shells)):
        for _ in range(count):
            n += 1
            recs.append({"type": "assistant", "message": {"model": "claude-opus-5-5", "content": [
                {"type": "tool_use", "id": "u%d" % n, "name": name, "input": {"file_path": "/secret/path"}}],
                "usage": usage or {"input_tokens": 5, "cache_read_input_tokens": 1000}}})
            recs.append({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "u%d" % n, "is_error": n == 1, "content": SECRET}]}})
    recs.append({"type": "assistant", "isSidechain": True, "message": {"model": "claude-haiku-4", "content": [
        {"type": "tool_use", "id": "side", "name": "Write", "input": {}}]}})
    Path(path).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n", encoding="utf-8")
    return str(path)


def test_session_work_counts_without_text(tmp_path):
    p = session_transcript(tmp_path / "s.jsonl", compact_first=True)
    info = sess.session_info(p, None, environ={}, home=str(tmp_path))
    w = info["work"]
    assert (w["read"], w["write"], w["shell"], w["agent"]) == (6, 1, 2, 0) and w["compacted"]     # до сжатия — не считаем
    assert w["facts"] == 7 and w["user_turns"] == 2 and w["context_tokens"] == 1005           # ошибка и запись — не факты
    assert w["write_share"] == 0.14 and w["tool_share"] == 0.82 and w["profile"] == "reading"
    dump = json.dumps(info, ensure_ascii=False)
    for word in ("Ромашка", "hunter2", "/secret/path", "мета"):
        assert word not in dump


@pytest.mark.parametrize("kw,profile", [
    ({"reads": 1, "writes": 0, "shells": 0, "turns": 6}, "dialog"),
    ({"reads": 4, "writes": 4, "shells": 0, "turns": 1}, "writing"),
    ({"reads": 2, "writes": 1, "shells": 5, "turns": 3}, "mixed"),
    ({"reads": 1, "writes": 0, "shells": 0, "turns": 1}, None),
])
def test_session_profiles(tmp_path, kw, profile):
    w = sess.session_info(session_transcript(tmp_path / "p.jsonl", **kw), None, environ={}, home=str(tmp_path))["work"]
    assert w["profile"] == profile, w


def test_context_tokens_make_session_long(tmp_path):
    p = session_transcript(tmp_path / "l.jsonl", reads=1, writes=0, shells=0, turns=1,
                           usage={"input_tokens": 10, "cache_creation_input_tokens": 50000, "cache_read_input_tokens": 120000})
    i = sess.session_info(p, None, environ={}, home=str(tmp_path))
    assert i["long"] and i["work"]["context_tokens"] == 170010


def base_r(**kw):
    r = {"model": "sonnet", "effort": "high", "source": "typesafe", "confidence": "высокая", "history_n": 0,
         "metrics": {k: {"value": 0.5, "confidence": 0.9} for k in ("complexity", "reasoning", "breadth", "risk")},
         "signals": {"axes": {}, "paths": 0, "items": 0, "critical": [], "effort": {}}}
    r.update(kw)
    return r


def test_facts_and_dialog_raise_context_cost():
    many = {"tier": "opus", "work": {"facts": 42, "profile": "reading", "user_turns": 2}}
    d = act.decide(base_r(), {"refs": True}, many)
    assert (d["kind"], d["why"], d["context_cost"], d["facts"]) == ("self", "context", "high", 42)
    assert "42 фактов" in d["reason"] and act.words(d["reason"]) <= act.REASON_MAX_WORDS
    talk = {"tier": "opus", "work": {"facts": 3, "profile": "dialog", "user_turns": 5}}
    d = act.decide(base_r(), {"refs": True}, talk)
    assert d["why"] == "context" and "диалога" in d["reason"] and act.words(d["reason"]) <= act.REASON_MAX_WORDS
    few = {"tier": "opus", "work": {"facts": 3, "profile": "reading", "user_turns": 2}}
    assert act.decide(base_r(), {"refs": True}, few)["context_cost"] == "medium"          # файлы субагент перечитает
    assert act.decide(base_r(), {}, many)["context_cost"] == "low"                       # задача самодостаточна


def test_hook_logs_session_profile_and_facts(tmp_path, monkeypatch, capsys):
    p = session_transcript(tmp_path / "h.jsonl", reads=35, writes=0, shells=0, turns=2)
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps(
        {"prompt": "Исправь падение теста test_login: таймаут при вызове сервиса авторизации, добавь повтор запроса",
         "session_id": "h1", "transcript_path": p, "cwd": str(tmp_path)})))
    assert t.run_hook() == 0
    capsys.readouterr()
    rec = [json.loads(x) for x in t.LOG_PATH.read_text(encoding="utf-8").splitlines()][-1]
    assert rec.get("session_facts") == 34 and rec.get("session_profile") == "reading"
