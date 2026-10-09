# -*- coding: utf-8 -*-
"""Офлайн-тесты политики выбора модели (без сети и без записи в настоящий журнал): pytest test_typesafe_triage.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import json
import os
import re

import pytest
import triage_heuristics as heur
import typesafe_triage as t


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(t.guard, "HOME", tmp_path / "guard")     # состояние защиты — во временный каталог
    monkeypatch.delenv("TYPESAFE_TRIAGE", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)        # офлайн: никаких живых запросов из тестов
    monkeypatch.delenv("CLAUDE_CODE_EFFORT_LEVEL", raising=False)


FLAG_NAMES = ("read_only", "mechanical", "needs_investigation", "silent_errors", "irreversible", "novel_design", "conversational")


def m(complexity=0.0, reasoning=0.0, ambiguity=0.0, risk=0.0, breadth=0.0, conf=1.0, upper=None, **flags):
    """Метрики как из metrics_from: шкалы (значение, уверенность, вероятность верхней половины), флаги (p, |2p-1|, p)."""
    out = {}
    for k in FLAG_NAMES:
        p = flags.get(k, 0.0)
        out[k] = (p, abs(2 * p - 1), p)
    for k, v in (("complexity", complexity), ("reasoning", reasoning), ("ambiguity", ambiguity), ("risk", risk), ("breadth", breadth)):
        out[k] = (v, conf, upper if upper is not None else (0.0 if v <= 0.5 else 1.0))
    return out


def test_four_tiers_and_confirmation_rules():
    assert t.TIERS == ["haiku", "sonnet", "opus", "fable"]
    assert t.CONFIRM_TIERS == {"haiku": "sonnet", "fable": "opus"} and set(t.AUTO_TIERS) == {"sonnet", "opus"}
    assert set(t.WEIGHTS) == set(t.SCORES) and abs(sum(t.WEIGHTS.values()) - 1) < 1e-9


def test_haiku_only_for_safe_confident_light_tasks():
    assert t.decide(m(read_only=0.95))[0] == "haiku"
    assert t.decide(m(mechanical=0.9))[0] == "haiku"
    assert t.decide(m())[0] == "sonnet"                                   # не только чтение/механика
    assert t.decide(m(read_only=0.95, conf=0.6, upper=0.3))[0] == "sonnet"  # неуверенно — не haiku
    assert t.decide(m(read_only=0.95, risk=0.9))[0] == "sonnet"           # рискованно — не haiku
    assert t.decide(m(read_only=0.95, novel_design=0.7))[0] == "sonnet"   # нужна новизна — не haiku


def test_haiku_by_confident_lower_half_even_with_split_levels():
    # уверенность шкал низкая (модель колеблется между «механикой» и «рутиной»), но верхняя половина почти пуста
    assert t.decide(m(reasoning=0.2, read_only=0.95, conf=0.55, upper=0.05))[0] == "haiku"
    assert t.decide(m(reasoning=0.2, read_only=0.95, conf=0.55, upper=0.3))[0] == "sonnet"


def test_heuristic_text_vetoes_haiku():
    h = heur.signals("Удали все данные клиентов из боевой базы и перезапусти прод")
    assert h["critical"]
    assert t.decide(m(mechanical=0.95), h)[0] == "sonnet"
    light = heur.signals("Покажи, где лежит файл настроек")
    assert t.decide(m(read_only=0.95), light)[0] == "haiku"


def test_data_rules_floor_and_opus():
    assert t.decide(m(silent_errors=0.9))[0] == "sonnet"
    assert t.decide(m(complexity=0.6, silent_errors=0.9))[0] == "opus"
    assert t.decide(m(complexity=0.6, irreversible=0.9))[0] == "opus"


def test_low_confidence_escalates_once_only_near_boundary():
    assert t.decide(m(complexity=0.7, reasoning=0.7, risk=0.5, conf=0.3))[0] == "opus"   # нагрузка 0.485 — у границы opus
    assert t.decide(m(complexity=0.5, reasoning=0.5, conf=0.3))[0] == "sonnet"           # 0.275 — далеко от границы
    assert t.decide(m(read_only=0.95, conf=0.3, upper=0.5))[0] == "sonnet"               # haiku→sonnet, второй шаг не делаем


def test_heavy_task_gets_opus():
    assert t.decide(m(1.0, 1.0, 0.5, 0.6, 0.5))[0] == "opus"


def test_fable_only_for_extreme_confident_critical_tasks():
    heavy = dict(complexity=1.0, reasoning=1.0, ambiguity=0.5, risk=1.0, breadth=1.0, irreversible=0.95)
    assert t.decide(m(**heavy))[0] == "fable"
    assert t.decide(m(conf=0.6, **heavy))[0] == "opus"                       # уверенность ниже CONF_FABLE
    assert t.decide(m(**dict(heavy, risk=0.67, irreversible=0.1, reasoning=0.8)))[0] == "opus"   # нет признака критичности
    calm = heur.signals("Сделай это")                                         # текст не подтверждает предельную нагрузку
    assert t.decide(m(**heavy), calm)[0] == "opus"
    loud = heur.signals("Мигрируй боевую базу платежей без простоя, откатить нельзя")
    assert t.decide(m(**heavy), loud)[0] == "fable"


def test_low_confidence_never_escalates_to_fable():
    for c in (0.0, 0.3, 0.49):
        assert t.decide(m(0.9, 0.9, 1.0, 0.9, 1.0, conf=c, irreversible=0.9))[0] == "opus"


def test_heuristic_fallback_is_only_sonnet_or_opus():
    for text in ("Покажи список файлов в папке", "Переименуй переменную x в y", "Привет, как дела у проекта сегодня?",
                 "Спроектируй архитектуру платёжной системы, миграцию боевой базы без простоя, план отката, аудит безопасности"):
        tier, _ = t.decide_heuristic(heur.signals(text))
        assert tier in t.AUTO_TIERS
    assert t.decide_heuristic(heur.signals("Напиши короткое письмо коллеге о переносе встречи на четверг"))[0] == "sonnet"
    assert t.decide_heuristic(heur.signals(
        "Разработай стратегию выхода на новый рынок: сегменты, цены, каналы, риски, план на год, и обоснуй выбор"))[0] == "opus"


def test_no_key_or_no_network_gives_heuristic_recommendation(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    r = t.triage("Составь план переезда офиса: сроки, ответственные, бюджет")
    assert r["model"] in t.AUTO_TIERS and r["source"] == "heuristic" and r["confidence"] == "низкая" and not r["confirm"]
    def boom(*a, **k):
        raise t.urllib.error.URLError("offline")
    monkeypatch.setattr(t, "ask_typesafe", boom)
    r = t.triage("любая задача про отчёт для руководства", key="x")
    assert r["model"] in t.AUTO_TIERS and r["paused"] == "outage" and r["source"] == "heuristic"


def test_offline_selftest_has_no_underestimates(capsys):
    assert t.run_selftest(heuristic_only=True) == 0
    assert "ниже ожидаемого (опасно) 0" in capsys.readouterr().out


def test_cases_cover_all_tiers_and_domains():
    cases = json.loads(Path(t.__file__).with_name("triage_cases.json").read_text(encoding="utf-8"))
    kinds = {c["expect"] for c in cases}
    assert {"haiku", "sonnet", "opus", "fable", "skip"} <= kinds
    assert sum(1 for c in cases if not re.search(r"код|файл|тест|функци|проект|README|\\.js|CSV|баз", c["task"])) >= 8


def test_agent_cmd_uses_allowed_tier_only():
    cmd = t.build_agent_cmd("opus", readonly=True, budget=2)
    assert cmd[:4] == ["claude", "-p", "--model", "opus"]
    assert "plan" in cmd and "--max-budget-usd" in cmd
    assert "--permission-mode" not in t.build_agent_cmd("sonnet")
    for bad in ("claude-fable-5-1", "", None, "gpt"):
        with pytest.raises(ValueError):
            t.build_agent_cmd(bad)
    for tier in ("haiku", "fable"):                                       # только с подтверждением пользователя
        with pytest.raises(ValueError):
            t.build_agent_cmd(tier)
        assert t.build_agent_cmd(tier, confirmed=True)[3] == tier


def test_run_without_signal_uses_default_tier(monkeypatch, capsys):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert t.run_agent(["x", "--dry-run", "--readonly", "Объясни структуру папки"]) == 0
    assert "sonnet" in capsys.readouterr().err


def test_run_requires_confirmation_for_haiku_and_fable(capsys):
    assert t.run_agent(["x", "--tier", "fable", "--dry-run", "задача"]) == 2
    assert "--confirmed" in capsys.readouterr().out
    assert t.run_agent(["x", "--tier", "haiku", "--dry-run", "задача"]) == 2
    assert "sonnet" in capsys.readouterr().out
    assert t.run_agent(["x", "--tier", "fable", "--confirmed", "--dry-run", "задача"]) == 0
    assert capsys.readouterr().out.startswith("claude -p --model fable")
    assert t.run_agent(["x", "--dry-run"]) == 2


@pytest.mark.parametrize("rec,expected_plain", [("fable", "opus"), ("haiku", "sonnet"), ("opus", "opus"), ("sonnet", "sonnet")])
def test_run_downgrades_unconfirmed_recommendation(monkeypatch, capsys, rec, expected_plain):
    monkeypatch.setattr(t, "triage", lambda *a, **k: {"model": rec, "source": "typesafe", "reason": "r"})
    monkeypatch.setattr(t, "log", lambda *a, **k: None)
    assert t.run_agent(["x", "--dry-run", "большая задача"]) == 0
    out = capsys.readouterr()
    assert out.out.startswith("claude -p --model %s " % expected_plain)
    if rec != expected_plain:
        assert "без --confirmed" in out.err
    assert t.run_agent(["x", "--confirmed", "--dry-run", "большая задача"]) == 0
    assert capsys.readouterr().out.startswith("claude -p --model %s " % rec)


def test_kill_switch_env_and_marker(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_TRIAGE", raising=False)
    assert not t.switched_off(str(tmp_path))
    (tmp_path / t.OFF_MARKER).write_text("")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    assert t.switched_off(str(sub))                      # маркер выше по дереву
    (tmp_path / t.OFF_MARKER).unlink()
    monkeypatch.setenv("TYPESAFE_TRIAGE", "off")
    assert t.switched_off(str(tmp_path))


def hook_out(monkeypatch, capsys, prompt, cwd=None):
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps({"prompt": prompt, "cwd": cwd})))
    assert t.run_hook() == 0
    out = capsys.readouterr().out
    return json.loads(out) if out.strip() else {}


@pytest.mark.parametrize("prompt", [
    "Спасибо, отлично получилось! Давай дальше по плану, как договорились.",
    "ок, продолжай",
    "да",
    "/review проверь последние изменения в ветке и скажи, что не так",
    "<task-notification>фоновая задача завершена, результат записан в файл</task-notification>",
])
def test_hook_skips_chatter_commands_and_harness_without_network(monkeypatch, capsys, prompt):
    calls = []
    monkeypatch.setattr(t, "triage", lambda *a, **k: calls.append(1) or {"model": "opus", "source": "typesafe", "reason": "x"})
    out = hook_out(monkeypatch, capsys, prompt)                          # 2.2: строка о пропуске вместо молчания
    assert calls == [] and set(out) == {"hookSpecificOutput"}
    assert out["hookSpecificOutput"]["additionalContext"].startswith("TypeSafe-триаж пропущен: ")


@pytest.mark.parametrize("prompt", [
    "Напиши вежливое письмо арендодателю с просьбой снизить плату за квартиру из-за ремонта",
    "Сравни три тарифа мобильной связи по цене и покрытию и посоветуй лучший для семьи",
    "Составь план подготовки к квартальной отчётной встрече с руководством: темы, слайды, сроки",
])
def test_hook_gives_note_for_non_code_tasks(monkeypatch, capsys, prompt):
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: fake_answers())
    monkeypatch.setenv("TYPESAFE_API_KEY", "k-test")
    out = hook_out(monkeypatch, capsys, prompt)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    # 2.3: заметка начинается строкой «ДЕЙСТВИЕ: …», модель/effort — в хвосте [TypeSafe-триаж: …]
    assert ctx.startswith("ДЕЙСТВИЕ: ") and "[TypeSafe-триаж: " in ctx and "systemMessage" not in out


def test_hook_note_without_key_uses_heuristic(monkeypatch, capsys):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    ctx = hook_out(monkeypatch, capsys, "Подготовь сводку продаж по регионам за квартал и объясни причины падения")[
        "hookSpecificOutput"]["additionalContext"]
    assert "только эвристика" in ctx and "Уверенность: низкая" in ctx and "AskUserQuestion" not in ctx


def test_hook_silent_when_typesafe_says_it_is_just_conversation(monkeypatch, capsys):
    a = fake_answers()
    a["answers"]["conversational"] = {"noul": 0.95}
    a["answers"]["complexity"] = {"score": 0.0, "confidence": 1.0}
    monkeypatch.setattr(t, "ask_typesafe", lambda *a_, **k: a)
    monkeypatch.setenv("TYPESAFE_API_KEY", "k-test")
    assert not t.should_skip("Я посмотрю это вечером, а пока просто держу в курсе команды проекта")
    out = hook_out(monkeypatch, capsys, "Я посмотрю это вечером, а пока просто держу в курсе команды проекта")
    assert out["hookSpecificOutput"]["additionalContext"].startswith("TypeSafe-триаж пропущен: реплика (по оценке TypeSafe)")


def test_hook_silent_when_switched_off(monkeypatch, capsys, tmp_path):
    called = []
    monkeypatch.setattr(t, "triage", lambda *a, **k: called.append(1))
    (tmp_path / t.OFF_MARKER).write_text("")
    assert hook_out(monkeypatch, capsys, "Напиши подробный отчёт о продажах за квартал для руководства", str(tmp_path)) == {}
    (tmp_path / t.OFF_MARKER).unlink()
    monkeypatch.setenv("TYPESAFE_TRIAGE", "off")
    assert hook_out(monkeypatch, capsys, "Напиши подробный отчёт о продажах за квартал для руководства", str(tmp_path)) == {}
    assert called == []


def test_flag_thresholds_haiku_strict_protection_loose():
    assert t.decide(m(read_only=0.7))[0] == "sonnet"                     # 0.7 < 0.8 — haiku не открывается
    assert t.decide(m(read_only=0.9))[0] == "haiku"
    assert t.decide(m(read_only=0.9, silent_errors=0.55))[0] == "sonnet"  # слабое «да» уже защищает
    assert t.decide(m(read_only=0.9, needs_investigation=0.55))[0] == "sonnet"
    assert t.decide(m(complexity=0.6, silent_errors=0.65))[0] == "opus"
    assert t.decide(m(complexity=0.6, novel_design=0.7))[0] == "opus"


def test_redact_hides_secrets():
    text = "ключ sk-" "abcdefghijklmnop1234 и password=hunter2 и Bearer abcdefghijklmnopqrstu плюс обычный текст"
    out = t.redact(text)
    assert "sk-abc" not in out and "hunter2" not in out and "abcdefghijklmnopqrstu" not in out and "обычный текст" in out


def test_hook_survives_garbage_and_pauses_after_failure(monkeypatch, capsys):
    import io, json
    for raw in ("[]", "null", "не json", json.dumps({"prompt": 123})):
        monkeypatch.setattr(t.sys, "stdin", io.StringIO(raw))
        assert t.run_hook() == 0
        out = json.loads(capsys.readouterr().out)                        # 2.2: отказ виден пользователю
        assert out["systemMessage"].startswith("TypeSafe-триаж пропущен: некорректный ввод хука")
    calls = []
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(t.urllib.error.URLError("down")))
    monkeypatch.setenv("TYPESAFE_API_KEY", "k-test")
    prompt = json.dumps({"prompt": "Исправь падение теста test_login в сервисе авторизации, пожалуйста"})
    for _ in range(3):
        monkeypatch.setattr(t.sys, "stdin", io.StringIO(prompt))
        assert t.run_hook() == 0
    assert len(calls) == 1                                               # после первого сбоя — пауза, сеть не трогаем


def test_log_skips_chatter_and_is_private(tmp_path):
    t.log("реплика", {"skip": True, "model": "sonnet"})
    t.log("нет уровня", {"model": None})
    assert not t.LOG_PATH.exists()
    t.log("правка кода password=" + "hunter2", {"model": "sonnet", "source": "heuristic", "reason": "r"})
    assert "hunter2" not in t.LOG_PATH.read_text(encoding="utf-8")
    assert os.name == "nt" or oct(t.LOG_PATH.stat().st_mode & 0o777) == "0o600"


def test_harness_messages_are_not_sent(monkeypatch, capsys):
    import io, json
    calls = []
    monkeypatch.setattr(t, "triage", lambda *a, **k: calls.append(1) or {"model": "opus", "source": "typesafe", "reason": "x"})
    for p in ('<task-notification>\n<task-id>1</task-id> завершена, это длинное служебное сообщение среды</task-notification>',
              '[SYSTEM NOTIFICATION - NOT USER INPUT] фоновая задача завершена и вернула результат работы',
              '<agent-message from="abc">[Subagent hand-back] отчёт субагента о проделанной работе по ревью</agent-message>'):
        assert t.is_harness_message(p)
        monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps({"prompt": p})))
        assert t.run_hook() == 0
        assert "служебное сообщение среды" in json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert calls == []
    assert not t.is_harness_message("Исправь падение теста test_login в сервисе авторизации")


def test_service_blocks_are_stripped_not_skipped(monkeypatch, capsys):
    """2.4.1: служебные теги среды перед текстом задачи не делают запрос служебным; в TypeSafe уходит только текст пользователя."""
    import io, json
    task = "Спроектируй миграцию базы с одной схемы на другую без простоя: план шагов и откат"
    seen = []
    monkeypatch.setattr(t, "triage", lambda text, *a, **k: seen.append(text) or {"model": "opus", "source": "typesafe", "reason": "x"})
    for p in ("<system-reminder>секрет-контекст</system-reminder>\n<ide_selection>token=abc</ide_selection> " + task,
              "<IDE_OPENED_FILE>a.py</IDE_OPENED_FILE>" + task):
        assert not t.is_harness_message(p) and t.skip_reason(p) is None
        assert t.strip_service_blocks(p) == task
    for p in ("<div class='a'>…</div> Перепиши этот блок на семантическую вёрстку и добавь aria-атрибуты", "<task>" + task + "</task>"):
        assert t.skip_reason(p) is None and t.strip_service_blocks(p) == p      # чужие теги — часть запроса
    for p in ("<system-reminder>только служебное</system-reminder>", "<task-notification>x</task-notification>",
              "<system-reminder>обрезано без закрывающего тега " + task):
        assert t.skip_reason(p) == "служебное сообщение среды"
    assert t.skip_reason("<system-reminder>x</system-reminder> /commit fix") == "команда /…"
    assert t.skip_reason("<system-reminder>x</system-reminder> ок") .startswith("короткая реплика")
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps({"prompt": "<system-reminder>секрет-контекст</system-reminder> " + task})))
    assert t.run_hook() == 0
    assert "ДЕЙСТВИЕ" in capsys.readouterr().out or seen
    assert seen and all("секрет-контекст" not in x and "system-reminder" not in x for x in seen)


@pytest.mark.parametrize("text,kind,rest", [
    ("/typesafe-triage:typesafe-triage проверь орфографию в docs", "slash", "проверь орфографию в docs"),
    ("/typesafe-triage проверь орфографию в docs", "slash", "проверь орфографию в docs"),
    ("/typesafe-triage:typesafe-triage", "slash", ""),
    ("triage: проверь орфографию в docs", "label", "проверь орфографию в docs"),
    ("Триаж: проверь орфографию в docs", "label", "проверь орфографию в docs"),
    ("!triage проверь орфографию в docs", "label", "проверь орфографию в docs"),
    ("triage: high quality docs", "label", "high quality docs"),                          # уровень — только вплотную к двоеточию
    ("triage:opus/high проверь договор", "label", "use opus, effort high: проверь договор"),
    ("!triage haiku проверь орфографию", "label", "use haiku: проверь орфографию"),
    ("!триаж opus high сделай", "label", "use opus, effort high: сделай"),
    ("!triage max", "label", ""),
    ("сделай триаж и проверь орфографию", "phrase", "сделай триаж и проверь орфографию"),
    ("проверь орфографию через typesafe-triage", "phrase", "проверь орфографию через typesafe-triage"),
    ("Please run triage on this and check the docs", "phrase", "Please run triage on this and check the docs"),
    ("почини баг в typesafe-triage", None, None),                  # название как объект задачи — не просьба
    ("/typesafe:typesafe-ai что-то", None, None),                  # чужой скилл
    ('в отчёте написано "сделай триаж", это цитата', None, None),
    ("`run triage` — пример из кода", None, None),
    ("triagex: не метка", None, None),
])
def test_force_trigger(text, kind, rest):
    k, r = heur.force_trigger(text)
    assert k == kind and (rest is None or r == rest)


def test_force_level_label_gives_explicit_directives():
    """Метка с уровнем = явное указание (согласие на haiku/fable/low/max), как «на opus» в тексте."""
    k, r = heur.force_trigger("!triage haiku max проверь орфографию")
    d = heur.directives(r)
    assert k == "label" and d["tier"] == "haiku" and d["effort"] == "max"


def test_forced_run_lifts_skips(monkeypatch, capsys):
    """2.4.2: слэш-вызов скилла, метка и фраза снимают пропуски (команда /…, короткая реплика, «болтовня», режим «реже»)."""
    import io, json
    seen = []
    monkeypatch.setattr(t, "triage", lambda text, *a, **k: seen.append(text) or {"model": "opus", "source": "typesafe", "reason": "x"})
    cases = [("/typesafe-triage:typesafe-triage проверь орфографию во всей документации", "проверь орфографию во всей документации"),
             ("триаж: поправь опечатку", "поправь опечатку"),
             ("сделай триаж, спасибо", "сделай триаж, спасибо")]
    for p, expect in cases:
        assert t.skip_reason(p) is not None or p.startswith("сделай")          # без метки такие запросы пропускались
        monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps({"prompt": p, "session_id": "f-" + expect[:5]})))
        assert t.run_hook() == 0
        out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
        assert "пропущен" not in out, p
        assert seen[-1] == expect                                                # метка вырезана, в оценку идёт только задача
    for p, why in (("/typesafe-triage:typesafe-triage", "нет текста задачи"), ("!triage max", "нет текста задачи"),
                   ("<task-notification>x</task-notification>", "служебное")):
        monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps({"prompt": p, "session_id": "f2"})))
        assert t.run_hook() == 0
        assert why in json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"], p
    assert t.skip_reason("/commit fix") == "команда /…"                          # чужие команды по-прежнему пропускаются


def test_agent_cmd_edit_and_allow():
    cmd = t.build_agent_cmd("sonnet", edit=True, allow=("Bash(git status)", "Bash(python3 -m pytest:*)"))
    assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"
    assert cmd.count("--allowedTools") == 2 and "Bash(git status)" in cmd
    with pytest.raises(ValueError):
        t.build_agent_cmd("sonnet", readonly=True, edit=True)
    assert t.run_agent(["x", "--edit", "--readonly", "--dry-run", "задача"]) == 2


def test_run_parses_allow_values_not_as_task(capsys):
    assert t.run_agent(["x", "--tier", "haiku", "--confirmed", "--allow", "Bash(ls)", "--dry-run", "моя", "задача"]) == 0
    out = capsys.readouterr().out
    assert out.rstrip().endswith("моя задача") and "Bash(ls)" not in out.split("\n", 1)[1]


# ---- ограничение размера отправляемого текста ----
import io
import time
import urllib.error


def fake_answers():
    a = {k: {"score": 1.0, "confidence": 0.9} for k in t.SCORES}
    for k in t.FLAGS:
        a[k] = {"noul": 0.1}
    a["domain"] = {"choice": "writing", "confidence": 0.8}
    return {"answers": a, "usage": {"input_tokens": 123}}


def http400():
    return urllib.error.HTTPError("u", 400, "Bad Request", {}, io.BytesIO(b'{"detail":{"error_type":"max_tokens_exceeded"}}'))


def test_digest_short_text_unchanged():
    s = "Исправь падение теста test_login: таймаут при вызове сервиса авторизации"
    assert t.make_digest(s) == s


def test_digest_squeezes_code_fence_and_keeps_the_request():
    code = "```python\n" + "\n".join("line_%d = %d" % (i, i) for i in range(300)) + "\n```"
    text = "Вот код, который падает:\n" + code + "\nИсправь ошибку в функции авторизации."
    d = t.make_digest(text)
    assert len(d) <= t.HARD_CHARS and "Вот код, который падает" in d and "Исправь ошибку в функции авторизации." in d
    assert "line_0 = 0" in d and "line_299 = 299" in d and "line_150 = 150" not in d and "пропущено" in d


def test_digest_squeezes_unfenced_log_and_clips_long_lines():
    log = "\n".join("2026-10-03 12:00:%02d ERROR worker-%d failed to connect to db" % (i % 60, i) for i in range(500))
    d = t.make_digest("Сервис падает, вот лог:\n\n" + log + "\n\nНайди причину.")
    assert len(d) <= t.HARD_CHARS and "Найди причину." in d and "Сервис падает" in d and "worker-250 " not in d
    one = t.make_digest("x" * 50 + " " + "y" * 20000 + " конец запроса: исправь")
    assert len(one) <= t.HARD_CHARS and "исправь" in one


def test_digest_head_tail_when_still_too_long():
    paras = "\n\n".join("Абзац номер %d описывает требование к системе и ограничения по срокам." % i for i in range(400))
    d = t.make_digest("НАЧАЛО просьбы.\n\n" + paras + "\n\nКОНЕЦ просьбы: сделай.")
    assert len(d) <= t.HARD_CHARS and d.startswith("НАЧАЛО") and d.rstrip().endswith("сделай.") and "середина пропущена" in d


def test_digest_huge_input_is_fast_and_bounded():
    big = ("шум шум шум 12345 abcdef\n" * 100000) + "ПРОСЬБА: почини сборку"
    t0 = time.time()
    d = t.make_digest(big)
    assert time.time() - t0 < 3 and len(d) <= t.HARD_CHARS and d.rstrip().endswith("почини сборку")
    t0 = time.time()
    h = heur.signals(big)                                                # эвристика тоже ограничена по размеру
    assert time.time() - t0 < 3 and h["chars"] <= heur.MAX_CHARS + 1


def test_digest_hides_secrets_in_kept_part():
    d = t.make_digest("Почини вход. password=hunter2 " + "слово " * 2000 + " токен ghp_abcdefghijklmnop1234567890")
    assert "hunter2" not in d and "ghp_abcdefghijklmnop" not in d


def test_retry_with_shorter_digest_after_max_tokens(monkeypatch):
    sizes = []

    def ask(sent, key, timeout=0):
        sizes.append(len(sent))
        if len(sizes) == 1:
            raise http400()
        return fake_answers()
    monkeypatch.setattr(t, "ask_typesafe", ask)
    r = t.triage("слово " * 3000, key="k")
    assert r["model"] and len(sizes) == 2 and sizes[1] <= t.RETRY_CHARS < sizes[0]
    assert r["input"]["chars"] == 18000 and r["input"]["sent"] == sizes[1] and r["tokens"] == 123


def test_too_big_even_after_retry_is_not_an_outage(monkeypatch):
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: (_ for _ in ()).throw(http400()))
    r = t.triage("слово " * 3000, key="k")
    assert r["source"] == "heuristic" and r["model"] in t.AUTO_TIERS and "paused" not in r and "слишком велик" in r["reason"]
    assert t.guard.status("k")["allowed"] and t.guard.load_state().get("pause") is None   # пауза не включилась
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: (_ for _ in ()).throw(urllib.error.HTTPError("u", 503, "x", {}, io.BytesIO(b""))))
    assert t.triage("слово " * 30, key="k")["paused"] == "outage"


def test_run_refuses_gigantic_task(capsys):
    assert t.run_agent(["x", "--dry-run", "я" * (t.AGENT_MAX_CHARS + 1)]) == 2


def test_long_prose_line_is_not_clipped():
    para = "Нужно переработать экран выгрузки так, чтобы пользователь видел ошибки по каждому файлу. " * 15   # ~1300 знаков, одна строка
    d = t.make_digest("Задача: " + para + "Сделай это аккуратно.")
    assert para in d and d.rstrip().endswith("Сделай это аккуратно.")


def test_child_agent_env_silences_hook_and_blocks_nested_run(monkeypatch, capsys):
    import io, json
    monkeypatch.setenv(t.CHILD_ENV, "1")
    called = []
    monkeypatch.setattr(t, "triage", lambda *a, **k: called.append(1) or {"model": "opus", "source": "typesafe", "reason": "x"})
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps({"prompt": "Исправь падение теста test_login в сервисе авторизации сегодня"})))
    assert t.run_hook() == 0 and called == [] and capsys.readouterr().out == ""
    assert t.run_agent(["x", "--dry-run", "любая задача"]) == 2
    assert "Вложенный" in capsys.readouterr().out


def test_run_passes_child_marker_to_agent(monkeypatch):
    seen = {}
    monkeypatch.delenv(t.CHILD_ENV, raising=False)
    monkeypatch.setattr(t.subprocess, "run", lambda cmd, **kw: seen.update(kw) or type("R", (), {"returncode": 0})())
    assert t.run_agent(["x", "--tier", "haiku", "--confirmed", "задача для агента"]) == 0
    assert seen["env"][t.CHILD_ENV] == "1" and seen["input"] == "задача для агента"


def note(tier, source="typesafe"):
    r = t.finish(tier, ["причина"], source, heur.signals("Сделай отчёт"),
                 metrics={k: {"value": 0.5, "confidence": 0.9} for k in t.SCORES} if source == "typesafe" else None)
    return t.hook_context(r)


def test_note_is_short_imperative_and_keeps_rules():
    txt = note("opus")      # 2.3: модель сессии неизвестна → Agent с оговоркой «если ты уже opus — сам»
    assert txt.startswith("ДЕЙСТВИЕ: Agent(model=opus, effort=") and "[TypeSafe-триаж: opus/" in txt
    assert "AskUserQuestion" not in txt and "делай сам" in txt and "не применять" in txt and "Model Selection" in txt
    assert "effort указывай явно" not in txt                         # 2.1.2: у Agent параметра effort может не быть
    assert "если он есть в схеме" in txt and "не ссылайся на него" in txt
    assert len(txt) < 2000 and txt.count("\n") <= 8


@pytest.mark.parametrize("tier,safe", [("fable", "opus")])
def test_note_for_confirm_tiers_demands_question_and_fallback(tier, safe):
    txt = note(tier)
    assert txt.startswith("ДЕЙСТВИЕ: спросить — %s: только с согласия" % tier)
    assert "AskUserQuestion" in txt and "«Да, %s»" % tier in txt and "«Нет, %s»" % safe in txt
    assert "нет явного «да» → Agent(model=%s" % safe in txt


def test_note_haiku_is_done_by_yourself_without_question():
    """2.3: haiku-задачу проще сделать самому — не делегируют и не спрашивают (подтверждение — только для агента haiku)."""
    txt = note("haiku")
    assert txt.startswith("ДЕЙСТВИЕ: сам — ") and "AskUserQuestion" not in txt


def test_note_marks_heuristic_source():
    txt = note("sonnet", "heuristic")
    assert "только эвристика" in txt and "Уверенность: низкая" in txt


def test_metrics_upper_mass_from_probabilities():
    ans = {k: {"score": 0.3, "confidence": 0.5, "probabilities": {"0": 0.6, "1": 0.3, "2": 0.1, "3": 0.0}} for k in t.SCORES}
    ans["ambiguity"] = {"score": 0.5, "confidence": 0.5, "probabilities": {"0": 0.5, "1": 0.4, "2": 0.1}}
    for k in t.FLAGS:
        ans[k] = {"noul": 0.8}
    mm = t.metrics_from(ans)
    assert abs(mm["complexity"][2] - 0.1) < 1e-9 and abs(mm["ambiguity"][2] - 0.1) < 1e-9
    assert abs(mm["read_only"][1] - 0.6) < 1e-9
    del ans["complexity"]["probabilities"]
    assert t.metrics_from(ans)["complexity"][2] == 1.0                     # нет распределения — считаем, что не уверены


def test_heuristic_signals_examples():
    s = heur.signals("Перенеси боевую базу платежей на новый сервер без простоя; удали все бэкапы")
    assert {"production", "money", "irreversible"} <= set(s["critical"])
    assert heur.signals("Спасибо, как договорились")["critical"] == []          # «договорились» — не юридический договор
    assert heur.signals("Почему падает сборка? Разберись в причине")["deep"] >= 2
    assert heur.signals("Переименуй кнопку «Ок» в «Готово»")["light"] >= 1
    many = heur.signals("Сделай:\n- пункт 1\n- пункт 2\n- пункт 3\n- пункт 4\nв файлах a/b.py, c/d.py, e.md")
    assert many["items"] == 4 and many["paths"] >= 3
    assert heur.is_chatter("Отлично, спасибо!") and not heur.is_chatter("Спасибо, а теперь напиши тесты для модуля")
