# -*- coding: utf-8 -*-
"""Офлайн-тесты второй оси (reasoning effort) и идемпотентности хука: pytest test_typesafe_effort.py"""
import io
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import triage_effort as eff
import triage_heuristics as heur
import typesafe_triage as t


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(t.guard, "HOME", tmp_path / "guard")
    monkeypatch.delenv("TYPESAFE_TRIAGE", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv(t.CHILD_ENV, raising=False)
    monkeypatch.setattr(eff, "session_effort", lambda cwd=None: None)   # не читать настройки пользователя


TIER_FLAGS = ("read_only", "mechanical", "needs_investigation", "silent_errors", "irreversible", "novel_design", "conversational")
EFF_FLAGS = ("verification", "exploration", "constraints", "coordination")


def m(level=0.0, conf=0.9, **over):
    """Метрики как из metrics_from: все шкалы (в т. ч. effort) = level, флаги = 0, переопределения поштучно."""
    out = {}
    for k in list(t.SCORES) + list(t.EFFORT_SCORES):
        v = over.get(k, level)
        out[k] = (v, conf, 0.0 if v <= 0.5 else 1.0)
    for k in TIER_FLAGS + EFF_FLAGS:
        p = over.get(k, 0.0)
        out[k] = (p, abs(2 * p - 1), p)
    return out


def H(text="Сделай отчёт по продажам"):
    return heur.signals(text)


def fake_resp(level=1.0, **flags):
    a = {k: {"score": level * (len(t.SCORES[k]["criteria"]) - 1), "confidence": 0.9} for k in t.SCORES}
    for k, spec in t.EFFORT_SCORES.items():
        a[k] = {"score": level * (len(spec["criteria"]) - 1), "confidence": 0.9}
    for k in list(t.FLAGS) + list(t.EFFORT_FLAGS):
        a[k] = {"noul": flags.get(k, 0.05)}
    a["domain"] = {"choice": "software", "confidence": 0.9}
    return {"answers": a, "usage": {"input_tokens": 100}}


# ---------- константы и шкала ----------
def test_effort_scale_and_confirm_constants():
    assert eff.EFFORTS == ["low", "medium", "high", "xhigh", "max"]
    assert eff.CONFIRM_EFFORTS == {"low": "medium", "max": "xhigh"}
    assert "xhigh" not in eff.CONFIRM_EFFORTS and eff.OPTIONAL_CONFIRM_EFFORTS == {"xhigh": "high"}
    assert eff.safe_effort("max") == "xhigh" and eff.safe_effort("low") == "medium" and eff.safe_effort("high") == "high"
    # пользователь добавил xhigh в подтверждаемые — цепочка max → xhigh → high
    assert eff.safe_effort("max", dict(eff.CONFIRM_EFFORTS, **eff.OPTIONAL_CONFIRM_EFFORTS)) == "high"
    assert set(eff.MODEL_EFFORTS) == set(t.TIERS) and all(set(v) == set(eff.EFFORTS) for v in eff.MODEL_EFFORTS.values())
    assert abs(sum(eff.EFFORT_WEIGHTS.values()) - 1) < 1e-9


def test_questions_include_effort_axis_in_same_request():
    q = t.build_questions()
    for k in list(t.EFFORT_SCORES) + list(t.EFFORT_FLAGS):
        assert k in q
    assert q["planning"]["type"] == "score" and q["verification"]["type"] == "noul"
    assert all(k in eff.EFFORT_WEIGHTS for k in list(t.EFFORT_SCORES) + list(t.EFFORT_FLAGS))


# ---------- независимость осей ----------
def test_axes_are_independent():
    mm = m(0.5)
    a = eff.decide_effort(mm, H(), "sonnet", env={})
    b = eff.decide_effort(mm, H(), "opus", env={})
    assert a["effort"] == b["effort"]                                     # модель не задаёт effort
    # выбор модели не зависит от вопросов effort
    base = {k: v for k, v in mm.items() if k not in t.EFFORT_SCORES and k not in t.EFFORT_FLAGS}
    assert t.decide(mm)[0] == t.decide(base)[0]
    deep = dict(mm, shallow_cost=(1.0, 0.9, 1.0), planning=(1.0, 0.9, 1.0), verification=(0.95, 0.9, 0.95))
    assert t.decide(deep)[0] == t.decide(mm)[0]                           # глубина выросла — модель та же
    assert eff.idx(eff.decide_effort(deep, H(), "sonnet", env={})["effort"]) > eff.idx(a["effort"])


def test_metrics_tolerate_missing_effort_answers():
    resp = fake_resp(0.5)
    for k in list(t.EFFORT_SCORES) + list(t.EFFORT_FLAGS):
        del resp["answers"][k]
    mm = t.metrics_from(resp["answers"])
    assert "planning" not in mm and "complexity" in mm
    d, parts = eff.ts_depth(mm)
    assert 0 <= d <= 1 and "planning" not in parts


# ---------- крайние уровни: только с подтверждения ----------
def test_max_needs_confirmation_and_falls_back_to_xhigh():
    crit = m(1.0, irreversible=0.95, verification=0.95, coordination=0.9, constraints=0.9)
    r = eff.decide_effort(crit, H("Мигрируй боевую базу платежей без простоя, откатить нельзя"), "fable", env={}, min_conf=0.9)
    assert r["effort"] == "max" and r["effort_confirm"] and r["effort_fallback"] == "xhigh"
    # без признака критичности max не выдаётся
    r = eff.decide_effort(m(1.0, risk=0.67, verification=0.95, coordination=0.9, constraints=0.9), H("Мигрируй боевую базу платежей"),
                          "opus", env={}, min_conf=0.9)
    assert r["effort"] == "xhigh" and not r["effort_confirm"]
    # низкая уверенность — тоже не max
    r = eff.decide_effort(crit, H("Мигрируй боевую базу платежей, откатить нельзя"), "opus", env={}, min_conf=0.5)
    assert r["effort"] == "xhigh"


def test_low_needs_confirmation_and_only_for_confident_light_work():
    light = m(0.0, read_only=0.95)
    r = eff.decide_effort(light, H("Отсортируй список: б, а, в"), "haiku", env={}, min_conf=0.9)
    assert r["effort"] == "low" and r["effort_confirm"] and r["effort_fallback"] == "medium"
    r = eff.decide_effort(light, H("Почему падает сборка? Разберись в причине"), "haiku", env={}, min_conf=0.9)
    assert r["effort"] != "low"                                           # текст говорит о диагностике
    r = eff.decide_effort(light, H("Отсортируй список: б, а, в"), "haiku", env={}, min_conf=0.4)
    assert r["effort"] == "medium"                                        # неуверенно — не low


def test_run_compresses_unconfirmed_extremes(monkeypatch, capsys):
    for rec, plain in (("max", "xhigh"), ("low", "medium"), ("high", "high")):
        monkeypatch.setattr(t, "triage", lambda *a, **k: {"model": "opus", "source": "typesafe", "reason": "r", "effort": rec,
                                                         "effort_source": "typesafe", "effort_reasons": ["x"]})
        monkeypatch.setattr(t, "log", lambda *a, **k: None)
        assert t.run_agent(["x", "--dry-run", "большая задача"]) == 0
        out = capsys.readouterr()
        assert out.out.startswith("claude -p --model opus --effort %s " % plain)
        if rec != plain:
            assert "без --confirmed-effort" in out.err
            assert t.run_agent(["x", "--dry-run", "--confirmed-effort", "большая задача"]) == 0
            assert capsys.readouterr().out.startswith("claude -p --model opus --effort %s " % rec)


def test_run_explicit_effort_options(capsys):
    assert t.run_agent(["x", "--tier", "sonnet", "--effort", "max", "--dry-run", "задача"]) == 2
    assert "--confirmed-effort" in capsys.readouterr().out
    assert t.run_agent(["x", "--tier", "sonnet", "--effort", "low", "--dry-run", "задача"]) == 2
    assert "medium" in capsys.readouterr().out
    assert t.run_agent(["x", "--tier", "sonnet", "--effort", "ultra", "--dry-run", "задача"]) == 2
    capsys.readouterr()
    assert t.run_agent(["x", "--tier", "sonnet", "--effort", "max", "--confirmed-effort", "--dry-run", "моя", "задача"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("claude -p --model sonnet --effort max ") and out.rstrip().endswith("моя задача")
    assert t.run_agent(["x", "--tier", "opus", "--effort", "xhigh", "--dry-run", "задача"]) == 0   # xhigh — без вопроса
    assert "--effort xhigh" in capsys.readouterr().out


def test_build_agent_cmd_validates_effort():
    cmd = t.build_agent_cmd("opus", effort="high")
    assert cmd[:6] == ["claude", "-p", "--model", "opus", "--effort", "high"]
    assert "--effort" not in t.build_agent_cmd("opus")                    # совместимость: без effort — как раньше
    for bad in ("ultra", "", "MAX"):
        with pytest.raises(ValueError):
            t.build_agent_cmd("opus", effort=bad)
    for e in ("low", "max"):
        with pytest.raises(ValueError):
            t.build_agent_cmd("opus", effort=e)
        assert t.build_agent_cmd("opus", effort=e, confirmed_effort=True)[5] == e


def test_run_passes_effort_to_child(monkeypatch):
    seen = {}
    monkeypatch.setattr(t.subprocess, "run", lambda cmd, **kw: seen.update(cmd=cmd, **kw) or type("R", (), {"returncode": 0})())
    assert t.run_agent(["x", "--tier", "opus", "--effort", "high", "задача для агента"]) == 0
    assert seen["cmd"][seen["cmd"].index("--effort") + 1] == "high" and seen["env"][t.CHILD_ENV] == "1"


# ---------- явные указания пользователя и отрицания ----------
@pytest.mark.parametrize("text,key,val", [
    ("Сделай на opus с effort max: проверь расчёт", "effort", "max"),
    ("Use haiku for this: convert the list", "tier", "haiku"),
    ("ultrathink: design the sharding strategy", "effort", "max"),
    ("max effort please, review the contract", "effort", "max"),
    ("Усилия: высокие. Проверь договор", "effort", "high"),
    ("Без размышлений, просто перечисли файлы", "effort", "low"),
    ("Подумай как следует и сравни варианты", "effort_min", "high"),
    ("Очень тщательно проверь формулы", "effort_min", "xhigh"),
    ("Think really hard about the race condition", "effort_min", "xhigh"),
    ("Ответь кратко: что такое SLA", "effort_max", "low"),
    ("Quick answer: is sort stable?", "effort_max", "low"),
    ("Не нужно глубоко разбираться, поправь отступы", "effort_max", "medium"),
    ("Не торопись, проверь отчёт", "effort_min", "high"),
    ("Не надо кратко, распиши подробно", "effort_min", "high"),
    ("Не нужен effort max, хватит обычного", "effort_max", "xhigh"),
])
def test_directives(text, key, val):
    assert heur.directives(text)[key] == val


def test_directive_negated_tier_and_conflicts():
    d = heur.directives("Don't use opus for this, sonnet is enough")
    assert d["tier"] is None and d["tier_not"] == ["opus"]
    assert eff.apply_tier_directive("opus", d)[0] == "sonnet"
    d = heur.directives("Сделай быстро и кратко, но очень тщательно")
    assert d["effort_min"] is None and d["effort_max"] is None and any("противоречив" in p for p in d["phrases"])
    assert heur.directives("Напиши оду в стиле opus magnum")["tier"] is None   # слово без маркера — не указание
    assert heur.directives("Сервис быстро падает после деплоя")["effort_max"] is None


def test_explicit_extremes_are_consent_without_second_question():
    r = t.triage("Сделай на fable с effort max: перепиши модуль биллинга целиком", env={}, history=[])
    assert r["model"] == "fable" and r["model_source"] == "user" and not r["confirm"]
    assert r["effort"] == "max" and r["effort_source"] == "user" and not r["effort_confirm"]
    txt = t.hook_context(r)
    assert "AskUserQuestion" not in txt and "Задано пользователем" in txt and "Agent(model=fable, effort=max)" in txt
    r = t.triage("Ответь кратко, без размышлений: сколько дней в високосном году?", env={}, history=[])
    assert r["effort"] == "low" and not r["effort_confirm"]


def test_quick_request_does_not_drop_safety_on_risky_work():
    r = eff.decide_effort(m(0.6, risk=1.0), H("Быстро ответь: можно удалить все бэкапы на проде?"), "opus",
                          env={}, d={"effort_max": "low"}, min_conf=0.9)
    assert r["effort"] == "high"                                          # риск держит пол high, просьба «быстро» не опускает до low


# ---------- запасной вариант без TypeSafe ----------
@pytest.mark.parametrize("text", [
    "Покажи список файлов в папке docs и их размеры, больше ничего",
    "Напиши короткое письмо коллеге о переносе встречи на четверг",
    "Сайт периодически отдаёт 502, разберись, в чём дело",
    "Мигрируй боевую базу платежей без простоя, откатить нельзя, ошибка — потеря денег",
    "Prove that the merge operation is commutative and idempotent",
])
def test_fallback_effort_stays_in_band(text):
    r = t.triage(text, env={}, history=[])
    assert r["source"] == "heuristic" and r["effort_source"] == "heuristic" and r["effort_confidence"] == "низкая"
    assert r["effort"] in ("medium", "high", "xhigh") and not r["effort_confirm"]


def test_fallback_order_routine_medium_doubt_high_risk_xhigh():
    assert t.triage("Напиши короткое письмо коллеге о переносе встречи на четверг", env={}, history=[])["effort"] == "medium"
    assert t.triage("Сайт периодически отдаёт 502, разберись, в чём дело", env={}, history=[])["effort"] == "high"
    big = "Спроектируй и проведи миграцию боевой базы платежей без простоя: двойная запись, сверка, откат; откатить после переключения нельзя"
    assert t.triage(big, env={}, history=[])["effort"] == "xhigh"


# ---------- согласованность модель × effort ----------
def test_consistency_rules():
    deep = m(1.0)
    assert eff.decide_effort(deep, H(), "haiku", env={}, min_conf=0.9)["effort"] == eff.HAIKU_EFFORT_MAX
    assert eff.decide_effort(m(0.2), H("Составь письмо"), "fable", env={}, min_conf=0.9)["effort"] == "high"
    assert eff.idx(eff.decide_effort(m(0.1, risk=0.9), H(), "sonnet", env={}, min_conf=0.9)["effort"]) >= eff.idx("high")
    mech = m(0.9, mechanical=0.95, risk=0.1)
    assert eff.decide_effort(mech, H("Переименуй переменные"), "opus", env={}, min_conf=0.9)["effort"] == "medium"
    # opus + low только для объёмной механики
    bulk = m(0.0, mechanical=0.95, breadth=1.0)
    assert eff.decide_effort(bulk, H("Отсортируй"), "opus", env={}, min_conf=0.9)["effort"] == "low"
    notbulk = m(0.0, read_only=0.95)
    assert eff.decide_effort(notbulk, H("Отсортируй"), "opus", env={}, min_conf=0.9)["effort"] == "medium"


# ---------- окружение ----------
def test_env_context_is_local_and_bounded(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    (tmp_path / "tests").mkdir()
    for i in range(5):
        (tmp_path / ("f%d.py" % i)).write_text("x")
    sub = tmp_path / "src"
    sub.mkdir()
    e = eff.env_context(str(sub))
    assert e["repo"] and e["tests"] and not e["ci"] and e["files"] >= 5 and e["marker"] is None
    monkeypatch.setattr(eff, "ENV_LARGE_FILES", 3)
    bump, why = eff.env_adjust(e, True)
    assert 0 < bump <= eff.ENV_MAX_BUMP and any("большой" in w for w in why)
    assert eff.env_adjust(e, False) == (0.0, [])                          # не работа над проектом — окружение не влияет
    assert eff.env_context(str(tmp_path.parent / "nonexistent-dir"))["repo"] is False


def test_project_marker_sets_floor(tmp_path):
    (tmp_path / eff.ENV_MARKER).write_text("xhigh\n")
    e = eff.env_context(str(tmp_path))
    assert e["marker"] == "xhigh"
    r = eff.decide_effort(m(0.2), H("Напиши письмо"), "sonnet", env=e, min_conf=0.9)
    assert r["effort"] == "xhigh" and r["effort_source"] == "project" and not r["effort_confirm"]


# ---------- история сессии ----------
def rec(task, retry, session="s", ts=None):
    return {"ts": ts or time.time(), "session": session, "id": t.prompt_id(task), "retry": retry}


def test_history_escalation_has_a_ceiling():
    assert eff.history_escalation([], False) == (0, 0, [])
    assert eff.history_escalation([rec("a", False)], True)[:2] == (1, 0)
    assert eff.history_escalation([rec("a", False), rec("b", True)], True)[:2] == (2, 1)
    many = [rec("x%d" % i, True) for i in range(10)]
    steps, mstep, why = eff.history_escalation(many, True)
    assert steps == eff.HISTORY_MAX_STEPS and mstep == 1 and any("потолок" in w for w in why)
    assert eff.history_escalation([rec("same", False)], False, t.prompt_id("same"))[0] == 1   # тот же запрос — повтор


def test_history_raises_effort_and_model_but_not_into_max():
    hist = [rec("Почини импорт CSV", False), rec("Опять не работает импорт CSV", True)]
    task = "Всё ещё не работает импорт CSV, ошибка та же, разберись"
    r = t.triage(task, env={}, history=hist)
    base = t.triage("Почини импорт CSV, разберись с ошибкой", env={}, history=[])
    assert r["retry"] and eff.idx(r["effort"]) > eff.idx(base["effort"]) and r["effort"] != "max"
    assert t.TIERS.index(r["model"]) >= t.TIERS.index(base["model"]) and r["model"] in ("sonnet", "opus")
    assert any("история" in x for x in r["effort_reasons"])


def test_history_read_from_log_by_session(tmp_path):
    t.log("Почини импорт", dict(t.triage("Почини импорт CSV с BOM", env={}, history=[]), session="aaa", retry=False))
    t.log("Опять не работает импорт", dict(t.triage("Опять не работает импорт CSV", env={}, history=[]), session="aaa", retry=True))
    t.log("чужая сессия", dict(t.triage("Опять не работает импорт CSV", env={}, history=[]), session="bbb", retry=True))
    recs = eff.read_history(t.LOG_PATH, "aaa")
    assert len(recs) == 2 and recs[-1]["retry"] is True
    old = {"ts": time.time(), "id": "x", "task": "старая запись 2.0", "model": "opus"}         # записи без новых полей
    with t.LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(old) + "\n" + "мусор\n")
    assert len(eff.read_history(t.LOG_PATH, "aaa")) == 2
    assert eff.read_history(t.LOG_PATH, None) == []
    stale = [dict(r, ts=time.time() - eff.HISTORY_WINDOW_S - 10) for r in recs]
    assert [r for r in stale if time.time() - r["ts"] <= eff.HISTORY_WINDOW_S] == []


def test_retry_detection_is_not_triggered_by_plain_again():
    assert heur.is_retry("Опять не работает импорт") and heur.is_retry("Still broken after your fix")
    assert not heur.is_retry("Поправь отступы, чтобы файл снова читался")
    assert not heur.is_retry("Send the report again to the new address")


# ---------- совместимость формата и заметка ----------
OLD_KEYS = ("model", "source", "confidence", "confirm", "fallback", "skip", "reason", "signals")
NEW_KEYS = ("effort", "effort_confidence", "effort_confirm", "effort_fallback", "effort_source", "effort_reasons", "clarify")


def test_result_format_is_additive(monkeypatch):
    r = t.triage("Составь план переезда офиса: сроки, ответственные, бюджет", env={}, history=[])
    assert all(k in r for k in OLD_KEYS + NEW_KEYS)
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: fake_resp(0.5))
    r = t.triage("Составь план переезда офиса: сроки, ответственные, бюджет", key="k", env={}, history=[])
    assert r["source"] == "typesafe" and all(k in r for k in OLD_KEYS + NEW_KEYS) and isinstance(r["effort_reasons"], list)
    assert any(x.startswith("a) TypeSafe") for x in r["effort_reasons"])


def test_old_server_without_effort_answers_still_works(monkeypatch):
    resp = fake_resp(0.5)
    for k in list(t.EFFORT_SCORES) + list(t.EFFORT_FLAGS):
        del resp["answers"][k]
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp)
    r = t.triage("Сравни три тарифа связи и посоветуй лучший для семьи", key="k", env={}, history=[])
    assert r["source"] == "typesafe" and r["effort"] in eff.EFFORTS


def base_result(tier="opus", effort="high", **kw):
    r = t.finish(tier, ["причина"], "typesafe", H(), metrics={k: {"value": 0.5, "confidence": 0.9} for k in t.SCORES})
    r.update(effort=effort, effort_confirm=False, effort_fallback=effort, effort_confidence="средняя",
             effort_reasons=["a) TypeSafe 0.50"], effort_source="typesafe")
    r.update(kw)
    return r


def test_note_single_dialog_for_both_confirmations():
    r = base_result("fable", "max", effort_confirm=True)
    r["effort_fallback"] = "xhigh"
    txt = t.hook_context(r)
    assert txt.count("AskUserQuestion") == 1 and "ОДИН вызов AskUserQuestion с двумя вопросами" in txt
    for s in ("«Да, fable»", "«Нет, opus»", "«Да, max»", "«Нет, xhigh»", "Agent(model=fable, effort=max)",
              "Agent(model=opus, effort=xhigh)", "больше токенов"):
        assert s in txt
    only_e = base_result("opus", "low", effort_confirm=True)
    only_e["effort_fallback"] = "medium"
    txt = t.hook_context(only_e)
    assert txt.count("AskUserQuestion") == 1 and "«Да, low»" in txt and "«Нет, medium»" in txt and "Запустить агента" not in txt


def test_note_session_effort_hint_and_clarify():
    txt = t.hook_context(base_result("opus", "xhigh"), cur_effort="low")
    assert "/effort xhigh" in txt
    assert "/effort" not in t.hook_context(base_result("opus", "high"), cur_effort="medium")   # отличие в 1 ступень — молчим
    assert "/effort" not in t.hook_context(base_result("opus", "xhigh"), cur_effort=None)
    txt = t.hook_context(base_result("opus", "high", clarify=True))
    assert "ОДИН короткий уточняющий вопрос" in txt


def test_clarify_only_for_low_confidence_high_stakes(monkeypatch):
    unsure = fake_resp(0.9, irreversible=0.9)
    for k in unsure["answers"]:
        if "confidence" in unsure["answers"][k]:
            unsure["answers"][k]["confidence"] = 0.3
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: unsure)
    r = t.triage("Удали старые данные клиентов из боевой базы, не знаю точно какие, может быть за прошлый год или раньше",
                 key="k", env={}, history=[])
    assert r["clarify"]
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: fake_resp(0.2))
    assert not t.triage("Напиши письмо коллеге о переносе встречи", key="k", env={}, history=[])["clarify"]


# ---------- идемпотентность хука ----------
def hook_raw(monkeypatch, capsys, payload):
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps(payload)))
    assert t.run_hook() == 0
    out = capsys.readouterr().out
    return json.loads(out) if out.strip() else {}


def test_second_hook_call_for_same_prompt_is_silent(monkeypatch, capsys):
    p = {"prompt": "Составь план подготовки к квартальной встрече с руководством: темы, слайды, сроки", "session_id": "sess-1"}
    first = hook_raw(monkeypatch, capsys, p)
    assert first["hookSpecificOutput"]["additionalContext"].startswith("TypeSafe-триаж: уровень ")
    assert hook_raw(monkeypatch, capsys, p) == {}                         # второй хук на тот же запрос — молчит
    assert hook_raw(monkeypatch, capsys, dict(p, session_id="sess-2"))    # другая сессия — говорит
    d = t.guard.HOME / t.DEDUP_NAME
    files = list(d.iterdir())
    assert files and all(oct(f.stat().st_mode & 0o777) == "0o600" and f.stat().st_size == 0 for f in files)
    assert all("квартал" not in f.name and len(f.name) == 32 for f in files)   # только хеш, без текста
    old = time.time() - t.DEDUP_S - 1
    for f in files:
        os.utime(f, (old, old))
    assert hook_raw(monkeypatch, capsys, p)                               # прошло больше DEDUP_S — это новый запрос


def test_dedup_needs_session_and_survives_fs_errors(monkeypatch):
    assert t.already_handled(None, "текст") is False and t.already_handled(None, "текст") is False
    monkeypatch.setattr(t.guard, "HOME", Path("/dev/null/not-a-dir"))
    assert t.already_handled("s", "текст") is False


def test_hook_still_silent_for_chatter_commands_and_child(monkeypatch, capsys):
    for p in ("ок, продолжай", "/review посмотри последние изменения в ветке, пожалуйста", "<task-notification>x</task-notification>"):
        assert hook_raw(monkeypatch, capsys, {"prompt": p, "session_id": "s"}) == {}
    monkeypatch.setenv(t.CHILD_ENV, "1")
    assert hook_raw(monkeypatch, capsys, {"prompt": "Составь план подготовки к квартальной встрече", "session_id": "s"}) == {}


def test_hook_log_has_effort_and_session_hash_only(monkeypatch, capsys):
    hook_raw(monkeypatch, capsys, {"prompt": "Составь план подготовки к квартальной встрече с руководством", "session_id": "secret-session-id"})
    line = json.loads(t.LOG_PATH.read_text(encoding="utf-8").splitlines()[-1])
    assert line["effort"] in eff.EFFORTS and line["session"] == eff.session_tag("secret-session-id")
    assert "secret-session-id" not in t.LOG_PATH.read_text(encoding="utf-8")


# ---------- калибровка ----------
def test_calibrate_offline_reports_both_splits(capsys):
    assert t.run_selftest(heuristic_only=True, calibrate=True) == 0
    out = capsys.readouterr().out
    assert "[train]" in out and "[holdout]" in out and "Распределение effort" in out
    assert "effort: совпало" in out and "ниже ожидаемого (опасно) 0, выше" in out


def test_cases_cover_efforts_domains_languages_and_history():
    cases = json.loads(Path(t.__file__).with_name("triage_cases.json").read_text(encoding="utf-8"))
    work = [c for c in cases if c["expect"] != "skip"]
    assert len(cases) >= 60
    assert {c["effort"] for c in work} == set(eff.EFFORTS)
    assert all(c.get("effort") in eff.EFFORTS for c in work)
    assert len({c.get("domain") for c in work}) >= 12
    assert sum(1 for c in work if c.get("lang") == "en") >= 15
    assert any(c.get("history") for c in work) and sum(1 for c in work if c.get("explicit")) >= 6
    holdout = [c for c in cases if t.is_holdout(c["task"])]
    assert 0.1 <= len(holdout) / float(len(cases)) <= 0.35


# ---------- 2.1.1: повтор при временной ошибке сервиса ----------
def _http(code):
    import urllib.error
    return urllib.error.HTTPError("http://x", code, "err", {}, None)


def test_retry_once_on_transient_5xx(monkeypatch):
    calls = []

    def flaky(task, key, timeout=0):
        calls.append(timeout)
        if len(calls) == 1:
            raise _http(529)
        return {"ok": True}

    monkeypatch.setattr(t, "ask_typesafe", flaky)
    monkeypatch.setattr(t.time, "sleep", lambda s: None)
    assert t.ask_with_retry("x", "k", 5) == {"ok": True}
    assert len(calls) == 2 and calls[1] < 5


def test_no_retry_when_budget_small_or_not_transient(monkeypatch):
    calls = []

    def boom(code):
        def f(task, key, timeout=0):
            calls.append(1)
            raise _http(code)
        return f

    monkeypatch.setattr(t.time, "sleep", lambda s: None)
    monkeypatch.setattr(t, "ask_typesafe", boom(402))
    with pytest.raises(Exception):
        t.ask_with_retry("x", "k", 5)
    assert len(calls) == 1                       # 402 - не временная ошибка
    calls.clear()
    monkeypatch.setattr(t, "ask_typesafe", boom(503))
    with pytest.raises(Exception):
        t.ask_with_retry("x", "k", 1.0)          # бюджета на повтор не осталось
    assert len(calls) == 1


def test_retry_gives_up_after_second_failure(monkeypatch):
    calls = []

    def always(task, key, timeout=0):
        calls.append(1)
        raise _http(529)

    monkeypatch.setattr(t, "ask_typesafe", always)
    monkeypatch.setattr(t.time, "sleep", lambda s: None)
    with pytest.raises(Exception):
        t.ask_with_retry("x", "k", 5)
    assert len(calls) == 2


# ---------- 2.1.2: у Agent может не быть параметра effort ----------
TYPICAL_CMD = "python3 $HOME/.claude/skills/typesafe-triage/scripts/typesafe_triage.py"


def risky_result(tier="opus", effort="high", **kw):
    r = base_result(tier, effort, **kw)
    r["metrics"]["risk"] = {"value": 1.0, "confidence": 0.9}
    return r


def test_note_effort_is_conditional_never_unconditional():
    for r in (base_result("opus", "medium"), base_result("opus", "high"), base_result("opus", "xhigh"), risky_result("opus", "high"),
              base_result("opus", "max", effort_confirm=True, effort_fallback="xhigh"), base_result("sonnet", "low")):
        txt = t.hook_context(r)
        assert "effort указывай явно" not in txt and "этого требует пользователь" not in txt
        assert "если параметр есть у Agent" in txt and "не пытайся и не ссылайся на него (не ошибка)" in txt
        assert "Agent(model=%s, effort=%s)" % (r["model"], r["effort"]) in txt


def test_note_default_effort_has_no_fallback_extras():
    for e in ("medium", "high"):
        r = base_result("opus", e)
        assert t.effort_delivery(r) == "agent_param"
        txt = t.hook_context(r)
        assert "глубину задай в промпте" in txt and "в промпт агента «" not in txt and "--run" not in txt


def test_note_unusual_effort_gives_prompt_phrase_only():
    txt = t.hook_context(base_result("opus", "xhigh"))
    assert t.effort_delivery(base_result("opus", "xhigh")) == "prompt"
    assert "в промпт агента «%s»" % t.EFFORT_PROMPT["xhigh"][0] in txt and "--run" not in txt
    low = t.hook_context(base_result("sonnet", "low", effort_confirm=True, effort_fallback="medium"))
    assert "кратко" in low and "--run" not in low
    en = base_result("opus", "xhigh")
    en["signals"]["effort"]["lang"] = "en"
    assert t.EFFORT_PROMPT["xhigh"][1] in t.hook_context(en)


@pytest.mark.parametrize("r,flags,after_yes", [
    (risky_result("opus", "high"), "--tier opus --effort high", False),
    (risky_result("opus", "xhigh"), "--tier opus --effort xhigh", False),
    (base_result("opus", "max", effort_confirm=True, effort_fallback="xhigh"), "--tier opus --effort max --confirmed-effort", True),
    (base_result("fable", "max", confirm=True, effort_confirm=True, effort_fallback="xhigh"),
     "--tier fable --confirmed --effort max --confirmed-effort", True),
    (base_result("opus", "max", effort_source="user", explicit=["effort max"]), "--tier opus --effort max --confirmed-effort", False),
])
def test_note_critical_effort_offers_run_with_full_path(monkeypatch, r, flags, after_yes):
    assert t.effort_delivery(r) == "run"
    txt = t.hook_context(r)
    line = next(ln for ln in txt.split("\n") if "--run" in ln)
    assert line.startswith("• Без параметра effort: в промпт агента «%s»" % t.EFFORT_PROMPT[r["effort"]][0])
    assert t.self_command() + " --run " + flags + " [--edit|--readonly]" in line
    assert t.self_command().split()[1].replace("$HOME", os.path.expanduser("~")).endswith("scripts/typesafe_triage.py")
    assert ("после «да»" in line) == after_yes
    plain = t.hook_context(base_result("opus", "medium"))
    assert txt.count("\n• ") <= plain.count("\n• ") + 1 + (1 if "AskUserQuestion" in txt else 0) + (1 if r.get("explicit") else 0)


def test_note_run_command_is_accepted_by_run(monkeypatch, capsys):
    txt = t.hook_context(base_result("opus", "max", effort_confirm=True, effort_fallback="xhigh"))
    args = txt.split("--run ", 1)[1].split(" [--edit|--readonly]")[0].split()
    assert t.run_agent(["x"] + args + ["--edit", "--dry-run", "проверь расчёт налога за год"]) == 0
    assert "claude -p --model opus --effort max" in capsys.readouterr().out


def test_self_command_uses_python_and_this_script():
    cmd = t.self_command()
    assert cmd.split()[0] == ("python" if os.name == "nt" else "python3")
    assert cmd.rstrip('"').endswith("/scripts/typesafe_triage.py") and "\\" not in cmd


def test_result_has_effort_delivery(monkeypatch):
    r = t.triage("Мигрируй боевую базу платежей без простоя, откатить нельзя, ошибка — потеря денег", env={}, history=[])
    assert r["effort_delivery"] in t.EFFORT_DELIVERY and r["effort_delivery"] == "run"
    assert t.triage("Напиши короткое письмо коллеге о переносе встречи на четверг", env={}, history=[])["effort_delivery"] \
        == "agent_param"


# Длина заметки 2.1.1 на тех же входах (замер до правки): рост не больше ~25 %.
OLD_NOTE_LEN = [
    (dict(level=0.6), "Найди причину, почему тест test_login иногда падает по таймауту в CI, и исправь", 1061),
    (dict(level=0.9, irreversible=0.9), "Мигрируй боевую базу платежей на новый кластер без простоя: двойная запись, сверка, откат", 1409),
    (dict(level=0.5), "Сделай на opus с effort max: проверь расчёт налога на имущество организации за год", 1260),
    (dict(level=0.85, risk=1.0), "Rotate all production database credentials for the payment service with a rollback path", 1075),
]


@pytest.mark.parametrize("resp,task,old", OLD_NOTE_LEN)
def test_note_size_grows_at_most_a_quarter(monkeypatch, resp, task, old):
    monkeypatch.setattr(t, "self_command", lambda: TYPICAL_CMD)
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: fake_resp(**resp))
    txt = t.hook_context(t.triage(task, key="k", env={}, history=[]))
    assert len(txt) <= old * 1.26, (len(txt), old)


# ---------- 2.1.2: упоминание (mention) против использования (use) ----------
REPORT_PARA = (
    "Кроме модели, заметка советует effort (насколько глубоко модели думать): от low до max. Effort для субагента я передать "
    "не могу, у инструмента Agent здесь нет такого параметра. Поэтому из заметки в работе используется только выбор модели.\n"
    "Глубину можно задать словами в запросе: «тщательно» поднимает её, «кратко» и «навскидку» снижают, «effort max» и "
    "«ultrathink» ставят максимум. Модель тоже можно назвать прямо: «на opus».")
NONE = {"tier": None, "tier_not": [], "effort": None, "effort_min": None, "effort_max": None, "phrases": []}


@pytest.mark.parametrize("text", [REPORT_PARA + "\n" + REPORT_PARA, REPORT_PARA + "\n\n" + REPORT_PARA,
                                  REPORT_PARA + " " + REPORT_PARA, REPORT_PARA])
def test_pasted_report_with_quoted_examples_is_not_a_directive(text):
    d = heur.directives(text)
    assert {k: d[k] for k in NONE} == NONE and d["report"] and d["mentions"] >= 5


def test_pasted_report_gives_no_explicit_in_result_and_note():
    r = t.triage(REPORT_PARA + "\n" + REPORT_PARA, env={}, history=[])
    assert r["model_source"] == "auto" and r["effort_source"] != "user" and "explicit" not in r and r["mentions"] >= 5
    assert "Задано пользователем" not in t.hook_context(r)


@pytest.mark.parametrize("text,key,val", [
    ("ultrathink: разбери архитектуру шардирования событий", "effort", "max"),
    ("на opus сделай ревью модуля оплаты", "tier", "opus"),
    ("effort max, пожалуйста: проверь миграцию базы", "effort", "max"),
    ("Сделай это «на opus»: перепиши модуль импорта", "tier", "opus"),
    ('Run it "on opus" please and review the PR', "tier", "opus"),
    ("Ответь кратко: что такое SLA", "effort_max", "low"),
])
def test_direct_use_still_works(text, key, val):
    assert heur.directives(text)[key] == val


@pytest.mark.parametrize("text", [
    "Слово «ultrathink» ставит максимум, а «кратко» снижает — объясни, как это работает",
    "Ассистент ответил: effort max я передать не могу. Почему так?",
    "Use `effort max` in the docs? Explain what it does",
    "Заметка советует на opus, а я не уверен. Сравни варианты",
    "Модель можно назвать прямо: «на opus».",
    "Он сказал: ultrathink ставит максимум. Это правда?",
    'The note says "effort max" — what does it change?',
    "В отчёте написано effort max и на opus, проверь отчёт",
])
def test_mentions_are_not_directives(text):
    d = heur.directives(text)
    assert d["tier"] is None and d["effort"] is None and d["mentions"] >= 1, d


def test_label_marks_only_the_next_quote_as_mention():
    d = heur.directives("Фраза «на opus» не сработала, сделай на opus и проверь отчёт")
    assert d["tier"] == "opus" and d["phrases"] == ["на opus"] and d["mentions"] == 1
    assert heur.directives("Как написано в ТЗ, сделай на opus миграцию")["tier"] == "opus"   # «написано» без двоеточия — не цитата


def test_directive_phrases_are_deduplicated():
    d = heur.directives("Сделай на opus с effort max: проверь расчёт, на opus, effort max, Effort max")
    assert d["tier"] == "opus" and d["effort"] == "max" and d["phrases"] == ["на opus", "effort max"]
    r = t.triage("Сделай на opus с effort max: проверь расчёт налога, на opus, effort max", env={}, history=[])
    assert r["explicit"] == ["на opus", "effort max"]
    assert "(на opus, effort max)" in t.hook_context(r)


def test_negations_still_work_with_mentions():
    assert heur.directives("Не нужен effort max, хватит обычного")["effort_max"] == "xhigh"
    d = heur.directives("Don't use opus for this, sonnet is enough")
    assert d["tier"] is None and d["tier_not"] == ["opus"]
    assert heur.directives("Не нужно глубоко разбираться, поправь отступы")["effort_max"] == "medium"


def test_repeated_log_lines_do_not_hide_own_request():
    text = "Разберись тщательно, почему падает сервис.\n" + "ERROR connection timeout to auth service after 30 seconds\n" * 6
    d = heur.directives(text)
    assert d["effort_min"] == "high" and not d["report"]


def test_mentions_masking_is_fast_on_long_input():
    t0 = time.time()
    heur.directives("Слово «ultrathink» и «effort max» в кавычках. " * 2500)
    heur.directives("Обычный текст без маркеров, просто описание задачи. " * 2000)
    assert time.time() - t0 < 2.0
