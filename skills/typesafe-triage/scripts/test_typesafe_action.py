# -*- coding: utf-8 -*-
"""2.3.0 (#27): заметка «ДЕЙСТВИЕ: сам | Agent(…) | спросить» + одна причина ≤ 15 слов + уверенность; реже (продолжение
с прежним решением — без заметки, запись quiet в журнал); признаки (общее устройство, долгое ожидание, явная просьба,
накопленный контекст, параллельность); модель сессии из стенограммы; параметр effort у Agent. Офлайн.
pytest test_typesafe_action.py"""
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import triage_action as act
import triage_effort as eff
import triage_heuristics as heur
import triage_session as sess
import typesafe_triage as t

SCRIPT = Path(__file__).parent / "typesafe_triage.py"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(t.guard, "HOME", tmp_path / "guard")
    for k in ("TYPESAFE_TRIAGE", "TYPESAFE_API_KEY", t.CHILD_ENV, t.CONTEXT_ENV):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(eff, "session_effort", lambda cwd=None: None)


def resp(level=0.2, choice="software", conf=0.9, **flags):
    a = {k: {"score": level * (len(t.SCORES[k]["criteria"]) - 1), "confidence": conf} for k in t.SCORES}
    for k, spec in t.EFFORT_SCORES.items():
        a[k] = {"score": level * (len(spec["criteria"]) - 1), "confidence": conf}
    for k in list(t.FLAGS) + list(t.EFFORT_FLAGS):
        a[k] = {"noul": flags.get(k, 0.05)}
    a["domain"] = {"choice": choice, "confidence": 0.8}
    return {"answers": a, "usage": {"input_tokens": 50}}


def hook(monkeypatch, capsys, payload):
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps(payload)))
    assert t.run_hook() == 0
    out = capsys.readouterr().out
    return json.loads(out) if out.strip() else {}


def ctx(out):
    return out.get("hookSpecificOutput", {}).get("additionalContext", "")


def log_lines():
    return [json.loads(x) for x in t.LOG_PATH.read_text(encoding="utf-8").splitlines()] if t.LOG_PATH.exists() else []


def transcript(path, model="claude-sonnet-5-5", effort="medium", agent_effort=None, sidechain_model=None, garbage=False):
    """Синтетическая стенограмма в формате Claude Code (только служебные поля, которые читает triage_session)."""
    lines = [{"type": "user", "isSidechain": False, "message": {"role": "user", "content": "секретный текст запроса"}},
             {"type": "assistant", "isSidechain": False, "effort": effort, "version": "2.1.294",
              "message": {"model": model, "role": "assistant", "content": [{"type": "text", "text": "ответ"}]}}]
    if agent_effort is not None:
        lines.append({"type": "assistant", "isSidechain": False, "effort": effort, "message": {"model": model, "content": [
            {"type": "tool_use", "id": "tu1", "name": "Agent", "input": {"model": "opus", "effort": "high", "prompt": "x"}}]}})
        lines.append({"type": "user", "isSidechain": False, "message": {"content": [
            {"type": "tool_result", "tool_use_id": "tu1", "is_error": not agent_effort, "content": "done"}]}})
    if sidechain_model:
        lines.append({"type": "assistant", "isSidechain": True, "message": {"model": sidechain_model, "content": []}})
    text = "\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n"
    if garbage:
        text = "{не json\n" + text + "обрывок {"
    Path(path).write_text(text, encoding="utf-8")
    return str(path)


# ---------- формат заметки ----------
FIRST_RE = re.compile(r"^ДЕЙСТВИЕ: (сам|спросить|Agent\(model=(haiku|sonnet|opus|fable), effort=(low|medium|high|xhigh|max)\)) — "
                      r"(?P<reason>.+?)\. Уверенность: (высокая|средняя|низкая|унаследована|задано пользователем)\. "
                      r"\[TypeSafe-триаж: (haiku|sonnet|opus|fable)/(low|medium|high|xhigh|max); (TypeSafe|только эвристика)")


@pytest.mark.parametrize("task,level,flags", [
    ("Напиши короткое письмо коллеге о переносе встречи на четверг", 0.1, {}),
    ("Найди причину, почему тест test_login иногда падает по таймауту в CI, и исправь", 0.5, {}),
    ("Мигрируй боевую базу платежей на новый кластер без простоя: двойная запись, сверка, откат", 0.9, {"irreversible": 0.9}),
    ("Сделай на opus с effort max: проверь расчёт налога на имущество организации за год", 0.5, {}),
])
def test_first_line_is_action_reason_confidence(monkeypatch, task, level, flags):
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp(level, **flags))
    r = t.triage(task, key="k", env={}, history=[])
    txt = t.hook_context(r)
    first = txt.split("\n")[0]
    m = FIRST_RE.match(first)
    assert m, first
    assert act.words(m.group("reason")) <= act.REASON_MAX_WORDS, m.group("reason")
    assert "Effort (" not in txt and "Причины:" not in txt and "рассуждение 0." not in txt   # без блоков a/b/c и чисел осей
    assert txt.count("Уверенность") == 1


def test_boundary_load_gives_the_same_tier_on_every_python():
    """Найдено по дороге: sum() в Python 3.12+ точнее, чем в 3.9; нагрузка ровно на пороге давала sonnet на 3.9 и opus
    на 3.14. Теперь нагрузка и глубина округляются до 9 знаков перед сравнением с порогами."""
    m = {k: (0.6, 0.9, 1.0) for k in t.SCORES}
    m.update({k: (0.05, 0.9, 0.05) for k in t.FLAGS})
    assert t.decide(m)[0] == "opus"
    assert eff.decide_effort({k: (0.45, 0.9, 0.0) for k in eff.EFFORT_WEIGHTS}, heur.signals("Сделай это"), "opus",
                             env={}, min_conf=0.9)["effort_depth"] == 0.45


def test_all_reason_templates_fit_fifteen_words():
    reasons = []
    for tier in t.TIERS:
        for st in (None, "haiku", "sonnet", "opus", "fable"):
            for a in ({}, {"agent_req": "agent"}, {"agent_req": "self"}, {"wait": "на 60 минут"}, {"dialog": True}):
                for extra in ({}, {"clarify": True}, {"shared_state": ["эмулятор"]}, {"confirm": True, "fallback": "opus"},
                              {"effort_confirm": True, "effort_fallback": "xhigh", "effort": "max"}):
                    r = {"model": tier, "effort": "high", "signals": {"axes": {"complexity": 0.5, "reasoning": 0.5}, "paths": 0}}
                    r.update(extra)
                    reasons.append(act.decide(r, a, {"tier": st, "model_source": "настройки (settings.json)"})["reason"])
    assert reasons and max(act.words(x) for x in set(reasons)) <= act.REASON_MAX_WORDS


def test_note_is_short_for_typical_self_action(monkeypatch):
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp(0.1))
    r = t.triage("Напиши короткое письмо коллеге о переносе встречи на четверг", key="k", env={}, history=[])
    txt = t.hook_context(r)
    assert txt.startswith("ДЕЙСТВИЕ: сам — ") and "\n" not in txt and len(txt) < 250


# ---------- правила действия ----------
def base(tier="opus", effort="high", level=0.5, **kw):
    r = {"model": tier, "effort": effort, "source": "typesafe", "confidence": "высокая", "effort_confidence": "высокая",
         "metrics": {k: {"value": level, "confidence": 0.9} for k in ("complexity", "reasoning", "breadth", "risk")},
         "signals": {"axes": {}, "paths": 0, "items": 0, "critical": [], "effort": {}}}
    r.update(kw)
    return r


@pytest.mark.parametrize("r,a,s,kind,why", [
    (base(), {"agent_req": "self"}, {"tier": "sonnet"}, "self", "user_self"),
    (base(clarify=True), {}, {"tier": "sonnet"}, "ask", "clarify"),
    (base(), {"wait": "на 60 минут"}, {"tier": "sonnet"}, "self", "wait"),
    (base("sonnet"), {"agent_req": "agent"}, {"tier": "opus"}, "agent", "user_agent"),
    (base(shared_state=["эмулятор"]), {}, {"tier": "sonnet"}, "self", "shared"),
    (base("sonnet", level=0.2), {}, {"tier": "sonnet"}, "self", "small"),
    (base("opus"), {}, {"tier": "sonnet"}, "agent", "higher"),
    (base("opus"), {}, {}, "agent", "unknown_session"),
    (base("sonnet", level=0.9), {}, {"tier": "opus"}, "agent", "big"),
    (base("sonnet", level=0.5), {"refs": True}, {"tier": "opus", "long": True}, "self", "context"),
    (base("sonnet"), {}, {"tier": "opus"}, "self", "not_higher"),
    (base("sonnet"), {}, {}, "self", "default"),
])
def test_action_rules(r, a, s, kind, why):
    d = act.decide(r, a, s)
    assert (d["kind"], d["why"]) == (kind, why), d


def test_session_tier_is_compared_honestly():
    assert act.decide(base("opus"), {}, {"tier": "opus"})["kind"] == "self"        # уровень не выше модели сессии
    assert act.decide(base("opus"), {}, {"tier": "fable"})["kind"] == "self"
    d = act.decide(base("opus"), {}, {"tier": "sonnet", "model_source": "настройки (settings.json)"})
    assert d["kind"] == "agent" and "(по настройкам)" in d["reason"]                # источник — не стенограмма: честно помечено
    u = act.decide(base("opus"), {}, {})
    assert u["conditional"] and "модель сессии хуку неизвестна" in u["reason"] and "если ты уже opus" in u["reason"]


def test_confirmation_turns_delegation_into_ask_with_safe_fallback():
    d = act.decide(base("fable", confirm=True, fallback="opus"), {}, {"tier": "sonnet"})
    assert d["kind"] == "ask" and d["agent"] == {"model": "fable", "effort": "high"}
    assert d["fallback"] == {"kind": "agent", "model": "opus", "effort": "high"}
    keep = act.decide(base("fable", confirm=True, fallback="opus"), {}, {"tier": "opus"})
    assert keep["kind"] == "ask" and keep["fallback"] == {"kind": "self"}           # «нет» → сам (сессия уже opus)
    h = act.decide(base("haiku", level=0.9, confirm=True, fallback="sonnet"), {"agent_req": "agent"}, {"tier": "opus"})
    assert h["kind"] == "ask" and "haiku" in h["reason"]                            # агент на haiku — только с согласия
    m = act.decide(base("opus", "max", effort_confirm=True, effort_fallback="xhigh"), {}, {"tier": "sonnet"})
    assert m["kind"] == "ask" and m["fallback"]["effort"] == "xhigh"


def test_user_request_beats_indices_and_negation_means_self():
    assert heur.action_signals("Оформи все 22 issues, используй субагента")["agent_req"] == "agent"
    assert heur.action_signals("Не используй субагента, сделай сам: поправь README")["agent_req"] == "self"
    assert heur.action_signals("Do it yourself, without subagents")["agent_req"] == "self"
    assert heur.action_signals("Слово «используй субагента» в отчёте — что значит?")["agent_req"] is None   # цитата
    assert heur.action_signals("Поручи агенту поддержки ответить клиенту")["agent_req"] is None
    d = act.decide(base("sonnet", level=0.1), heur.action_signals("Оформи все issues, используй субагента"), {"tier": "opus"})
    assert d["kind"] == "agent" and d["why"] == "user_agent"


@pytest.mark.parametrize("text,phrase", [
    ("Запусти запись на 60 минут и проверь, что файл растёт", "на 60 минут"),
    ("Подожди, пока сборка закончится, и посмотри логи", "подожди"),
    ("каждые 10 минут проверяй статус", "каждые 10 минут"),
    ("Wait for the deploy to finish and then run smoke tests", "wait for"),
    ("Прогон soak на эмуляторе в течение часа", "soak"),
])
def test_long_wait_detection(text, phrase):
    assert heur.action_signals(text)["wait"] == phrase


def test_short_durations_are_not_long_waits():
    assert heur.action_signals("через 2 минуты повтори запрос")["wait"] is None
    assert heur.action_signals("Напиши письмо на 3 абзаца")["wait"] is None


def test_device_parallel_refs_dialog_signals():
    a = heur.action_signals("Проверь приложение на эмуляторе Pixel 7: вход и запись")
    assert a["device"] == ["эмуляторе"]
    assert heur.action_signals("Почини три модуля параллельно:\n- a.py\n- b.py\n- c.py")["parallel"] == 3
    assert heur.action_signals("Исправь найденные ранее дефекты, как мы обсуждали")["refs"]
    assert heur.action_signals("Что такое SLA?")["dialog"]
    assert not heur.action_signals("Почему падает сборка в CI на шаге тестов? Разберись")["dialog"]


def test_note_hints_wait_shared_parallel(monkeypatch):
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp(0.5))
    w = t.hook_context(t.triage("Запусти запись на 60 минут на втором стенде и собери метрики памяти", key="k", env={}, history=[]))
    assert w.startswith("ДЕЙСТВИЕ: сам — долгое ожидание") and "фоновый скрипт" in w and "«на 60 минут»" in w
    d = t.hook_context(t.triage("Проверь приложение на эмуляторе: вход, запись, расшифровка, экспорт", key="k", env={}, history=[]))
    assert d.startswith("ДЕЙСТВИЕ: сам — общее устройство") and "Общее интерактивное состояние (эмуляторе)" in d
    p = t.hook_context(t.triage("Используй субагентов: почини параллельно три модуля:\n- a.py\n- b.py\n- c.py",
                                key="k", env={}, history=[]))
    assert "Agent(model=" in p.split("\n")[0] and "несколько Agent параллельно" in p


# ---------- параметр effort у Agent ----------
def test_agent_effort_known_yes_or_no_changes_effort_line(monkeypatch):
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp(0.9, irreversible=0.9))
    task = "Мигрируй боевую базу платежей на новый кластер без простоя: двойная запись, сверка, откат"
    yes = t.triage(task, key="k", env={}, history=[], session_info={"tier": "sonnet", "agent_effort": True})
    txt = t.hook_context(yes)
    assert "параметром Agent: он есть" in txt and "--run" not in txt and "если он есть в схеме" not in txt
    no = t.triage(task, key="k", env={}, history=[], session_info={"tier": "sonnet", "agent_effort": False})
    txt = t.hook_context(no)
    assert "У Agent нет параметра effort (не ошибка)" in txt and "Agent(model=opus; в промпт: «" in txt   # 2.6: фраза внутри строки вызова


def test_set_agent_effort_command_and_config(tmp_path, monkeypatch, capsys):
    assert t.main(["x", "--set-agent-effort", "yes"]) == 0
    assert t.skill_config()["agent_effort"] is True
    assert sess.session_info(None, None, environ={}, home=str(tmp_path), config=t.skill_config())["agent_effort"] is True
    assert t.main(["x", "--set-agent-effort", "auto"]) == 0 and "agent_effort" not in t.skill_config()
    assert t.main(["x", "--set-agent-effort", "maybe"]) == 2
    t.guard.set_budget(5)                                              # соседний ключ config.json не теряется
    t.set_agent_effort(False)
    assert t.skill_config()["monthly_budget_usd"] == 5 and t.skill_config()["agent_effort"] is False


# ---------- модель сессии ----------
def test_session_from_transcript(tmp_path):
    p = transcript(tmp_path / "s.jsonl", model="claude-opus-5-5", effort="xhigh", agent_effort=True, sidechain_model="claude-haiku-4")
    i = sess.session_info(p, None, environ={}, home=str(tmp_path))
    assert i["tier"] == "opus" and i["model_source"] == "стенограмма" and i["effort"] == "xhigh" and i["version"] == "2.1.294"
    assert i["agent_effort"] is True and not i["long"]
    bad = transcript(tmp_path / "b.jsonl", agent_effort=False, garbage=True)               # вызов с effort упал — не «есть»
    j = sess.session_info(bad, None, environ={}, home=str(tmp_path))
    assert j["tier"] == "sonnet" and j["agent_effort"] is None
    assert sess.session_info(str(tmp_path / "нет.jsonl"), None, environ={}, home=str(tmp_path))["tier"] is None


def test_session_reads_only_the_tail_and_flags_long_sessions(tmp_path, monkeypatch):
    p = tmp_path / "big.jsonl"
    filler = json.dumps({"type": "assistant", "message": {"model": "claude-haiku-4", "content": []}}) + "\n"
    with open(p, "w", encoding="utf-8") as f:
        f.write(filler * 2000)
    transcript(tmp_path / "tail.jsonl", model="claude-opus-5-5")
    with open(p, "a", encoding="utf-8") as f:
        f.write((tmp_path / "tail.jsonl").read_text(encoding="utf-8"))
    monkeypatch.setattr(sess, "LONG_SESSION_BYTES", 1000)
    i = sess.session_info(str(p), None, environ={}, home=str(tmp_path))
    assert i["tier"] == "opus" and i["long"]


def test_session_sources_order_and_switch(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "settings.json").write_text(json.dumps({"model": "opus", "env": {"TYPESAFE_API_KEY": "sk-secretsecret"}}))
    p = transcript(tmp_path / "s.jsonl", model="claude-sonnet-5-5")
    assert sess.session_info(None, str(proj), environ={}, home=str(tmp_path))["model_source"].startswith("настройки")
    assert sess.session_info(p, str(proj), environ={}, home=str(tmp_path))["tier"] == "sonnet"       # стенограмма главнее
    assert sess.session_info(p, str(proj), environ={"ANTHROPIC_MODEL": "claude-opus-5-5"}, home=str(tmp_path))["tier"] == "sonnet"
    assert sess.session_info(None, None, environ={"ANTHROPIC_MODEL": "claude-opus-5-5"}, home=str(tmp_path))["tier"] == "opus"
    assert sess.session_info(p, str(proj), environ={sess.MODEL_ENV: "fable"}, home=str(tmp_path))["tier"] == "fable"
    off = sess.session_info(p, str(proj), environ={sess.MODEL_ENV: "unknown"}, home=str(tmp_path))
    assert off["tier"] is None and "не определяется" in off["model_source"]
    assert sess.tier_of("opusplan") == "sonnet" and sess.tier_of("default") is None and sess.tier_of("claude-fable-5") == "fable"


def test_manual_commands_find_transcript_by_session_id(tmp_path):
    home = tmp_path / "home"
    d = home / ".claude" / "projects" / "-Users-x-proj"
    d.mkdir(parents=True)
    sid = "a996f529-00e8-491b-a07b-03cd51e31221"
    transcript(d / ("%s.jsonl" % sid), model="claude-opus-5-5", agent_effort=True)
    env = {sess.SESSION_ID_ENV: sid}
    assert sess.session_info(None, None, environ=env, home=str(home))["tier"] is None          # без discover — не ищем
    i = sess.session_info(None, None, environ=env, home=str(home), discover=True)
    assert i["tier"] == "opus" and i["agent_effort"] is True and i["transcript"].endswith(sid + ".jsonl")
    assert sess.find_transcript("../../etc/passwd", str(home)) is None and sess.find_transcript(None, str(home)) is None


def test_hook_uses_transcript_model_for_the_action(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(sess.MODEL_ENV, raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp(0.8, irreversible=0.9))
    task = "Спроектируй миграцию схемы заказов с двойной записью и сверкой, план отката и проверки"
    low = transcript(tmp_path / "sonnet.jsonl", model="claude-sonnet-5-5")
    c = ctx(hook(monkeypatch, capsys, {"prompt": task, "session_id": "A", "transcript_path": low, "cwd": str(tmp_path)}))
    assert c.startswith("ДЕЙСТВИЕ: Agent(model=opus") and "модель сессии sonnet ниже" in c
    high = transcript(tmp_path / "opus.jsonl", model="claude-opus-5-5")
    c = ctx(hook(monkeypatch, capsys, {"prompt": task, "session_id": "B", "transcript_path": high, "cwd": str(tmp_path)}))
    assert c.startswith("ДЕЙСТВИЕ: сам — ") and "секретный" not in json.dumps(log_lines(), ensure_ascii=False)
    assert log_lines()[-1]["session_tier"] == "opus" and log_lines()[-1]["action"] == "self"


# ---------- реже: продолжение с прежним решением ----------
def test_continuation_with_same_decision_is_quiet_and_logged_without_text(monkeypatch, capsys):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp(0.5))
    first = hook(monkeypatch, capsys, {"prompt": "Найди причину, почему тест test_login иногда падает по таймауту в CI", "session_id": "Q"})
    assert ctx(first).startswith("ДЕЙСТВИЕ: ")
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp(0.1))
    assert hook(monkeypatch, capsys, {"prompt": "продолжай, проверь ещё и второй тест в том же модуле", "session_id": "Q"}) == {}
    rec = log_lines()[-1]
    assert rec["quiet"] == t.QUIET_REASON and "task" not in rec and rec["chars"] > 0 and rec["session"] == eff.session_tag("Q")
    assert "второй тест" not in json.dumps(rec, ensure_ascii=False)
    assert len(eff.read_history(t.LOG_PATH, eff.session_tag("Q"))) == 2          # молчаливое решение — тоже история сессии


def test_continuation_with_changed_decision_speaks(monkeypatch, capsys):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp(0.5))
    hook(monkeypatch, capsys, {"prompt": "Найди причину, почему тест test_login иногда падает по таймауту в CI", "session_id": "C"})
    c = ctx(hook(monkeypatch, capsys, {"prompt": "и ещё подожди 30 минут прогона нагрузки и проверь метрики", "session_id": "C"}))
    assert c.startswith("ДЕЙСТВИЕ: сам — долгое ожидание")                         # решение изменилось — заметка есть


def test_new_task_with_same_decision_still_speaks(monkeypatch, capsys):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp(0.5))
    hook(monkeypatch, capsys, {"prompt": "Найди причину, почему тест test_login иногда падает по таймауту в CI", "session_id": "N"})
    c = ctx(hook(monkeypatch, capsys, {"prompt": "Найди причину, почему тест test_logout иногда падает на сборке ночью", "session_id": "N"}))
    assert c.startswith("ДЕЙСТВИЕ: ")                                             # не продолжение — это новая задача


def test_continuation_after_confirmation_keeps_delegation():
    """Найдено живым прогоном: после «спросить (effort max)» продолжение получало «сам — небольшая задача»."""
    r = base("opus", "xhigh", level=0.1, inherited={"model": "opus", "effort": "xhigh"},
             prev={"model": "opus", "effort": "max", "action": "ask", "why": "confirm"})
    d = act.decide(r, {}, {"tier": "sonnet"}, continuation=True)
    assert (d["kind"], d["why"]) == ("agent", "continuation")
    clarify = dict(r, prev={"model": "opus", "effort": "high", "action": "ask", "why": "clarify"})
    assert act.decide(clarify, {}, {"tier": "sonnet"}, continuation=True)["why"] != "continuation"


def test_continuation_with_work_verb_is_not_chatter():
    """Найдено живым прогоном: «продолжай, распиши …» считалось репликой без поручения и не доходило до «реже»."""
    for text in ("продолжай, распиши ещё шаг сверки подробнее", "продолжай, допиши раздел про откат", "дальше — доделай тесты"):
        assert not heur.is_chatter(text) and heur.is_continuation(text)
    assert heur.is_chatter("ок, продолжай") and heur.is_chatter("Спасибо, отлично получилось! Давай дальше по плану.")


def test_quiet_speaks_when_a_new_hint_appears():
    prev = {"model": "sonnet", "effort": "high", "action": "self", "hints": []}
    r = {"model": "sonnet", "effort": "high", "continuation": True, "prev": prev, "action": {"kind": "self", "hints": ["wait"]}}
    assert t.quiet_reason("и ещё подожди 30 минут", r) is None                     # то же «сам», но новое указание
    r["prev"] = dict(prev, hints=["wait"])
    assert t.quiet_reason("и ещё подожди 30 минут", r) == t.QUIET_REASON


def test_quiet_never_hides_failures_confirmations_or_notices():
    prev = {"model": "opus", "effort": "high", "action": "agent"}
    same = {"model": "opus", "effort": "high", "continuation": True, "prev": prev, "action": {"kind": "agent"}}
    assert t.quiet_reason("продолжай", same) == t.QUIET_REASON
    assert t.quiet_reason("продолжай", same, late="не уложилась") is None
    assert t.quiet_reason("продолжай", dict(same, notice="TypeSafe приостановлен")) is None
    assert t.quiet_reason("продолжай", dict(same, effort_confirm=True)) is None
    assert t.quiet_reason("продолжай", dict(same, clarify=True)) is None
    assert t.quiet_reason("продолжай", dict(same, continuation=False)) is None
    assert t.quiet_reason("продолжай", dict(same, prev=None)) is None


def test_failure_contract_is_kept_for_errors(monkeypatch, capsys):
    monkeypatch.setattr(t.act, "decide", lambda *a, **k: 1 / 0)
    out = hook(monkeypatch, capsys, {"prompt": "Найди причину, почему тест test_login иногда падает по таймауту в CI", "session_id": "E"})
    assert out["systemMessage"].startswith(t.SKIP_PREFIX) and "ZeroDivisionError" in out["systemMessage"]


def test_hook_subprocess_with_transcript_gives_action_line(tmp_path):
    p = transcript(tmp_path / "s.jsonl", model="claude-opus-5-5")
    env = dict(os.environ, TYPESAFE_TRIAGE_HOME=str(tmp_path / "st"))
    env.pop("TYPESAFE_API_KEY", None)
    env.pop(sess.MODEL_ENV, None)
    payload = {"prompt": "Напиши короткое письмо коллеге о переносе встречи на четверг", "session_id": "P", "transcript_path": p,
               "cwd": str(tmp_path)}
    r = subprocess.run([sys.executable, "-B", str(SCRIPT), "--hook"], input=json.dumps(payload), capture_output=True, text=True,
                       env=env, timeout=30)
    c = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert r.returncode == 0 and c.startswith("ДЕЙСТВИЕ: сам — ") and "только эвристика" in c
