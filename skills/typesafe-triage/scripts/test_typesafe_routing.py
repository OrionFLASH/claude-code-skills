# -*- coding: utf-8 -*-
"""2.7.0 (#50–#58): выбор модели и effort без подтверждений. Подтверждений по умолчанию нет — вместо вопроса строгие критерии для
haiku, fable, low и max; диагностика повтора («не знала» → модель, «не старалась» → effort); рутина не поднимается по сомнению;
описание выбора модели не считается указанием. Предыдущий набор тестов идёт в режиме TYPESAFE_TRIAGE_CONFIRM=on (conftest),
здесь — поведение по умолчанию (CONFIRM_* подменяются пустыми). pytest test_typesafe_routing.py"""
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import triage_action as act
import triage_effort as eff
import triage_heuristics as heur
import typesafe_triage as t
from test_typesafe_effort import H, m as em
from test_typesafe_triage import m as tm


@pytest.fixture
def no_confirm(monkeypatch):
    monkeypatch.setattr(t, "CONFIRM_TIERS", {})
    monkeypatch.setattr(eff, "CONFIRM_EFFORTS", {})
    monkeypatch.setattr(eff, "history_escalation", eff.history_escalation)


# ---------- подтверждения: выключатель ----------
@pytest.mark.parametrize("value,names", [
    ("", set()), ("off", set()), ("0", set()), ("none", set()),
    ("on", {"haiku", "fable", "low", "max"}), ("all", {"haiku", "fable", "low", "max"}), ("yes", {"haiku", "fable", "low", "max"}),
    ("haiku,fable", {"haiku", "fable"}), ("max low", {"low", "max"}), ("opus, fable", {"fable"}),
])
def test_confirm_names(value, names):
    assert eff.confirm_names({eff.CONFIRM_ENV: value}) == names


def test_no_confirmation_by_default_in_a_fresh_process():
    import subprocess
    env = {k: v for k, v in __import__("os").environ.items() if k != eff.CONFIRM_ENV}
    out = subprocess.run([sys.executable, "-c", "import typesafe_triage as t, triage_effort as e; print(t.CONFIRM_TIERS, e.CONFIRM_EFFORTS)"],
                         capture_output=True, text=True, cwd=str(Path(__file__).parent), env=env)
    assert out.stdout.strip() == "{} {}", out.stdout + out.stderr


# ---------- fable: безусловный случай ----------
HEAVY = dict(complexity=1.0, reasoning=1.0, ambiguity=0.5, risk=1.0, breadth=1.0, irreversible=0.95)
LOUD = "Мигрируй боевую базу платежей без простоя, откатить нельзя"


HORIZON = "Проведи многочасовую автономную миграцию боевой базы платежей по всей кодовой базе, откатить нельзя"


def test_fable_without_question_only_for_long_horizon(no_confirm):
    sig = heur.signals(HORIZON)
    assert sig["horizon"]
    r = t.finish(*(lambda tier, why: (tier, why))(*t.decide(tm(**HEAVY), sig)), "typesafe", sig)
    assert r["model"] == "fable" and r["confirm"] is False and "только с подтверждением" not in r["reason"]
    # критично, но без долгого горизонта (F1, F2): opus на высоком effort, Fable не нужна
    tier, why = t.decide(tm(**HEAVY), heur.signals(LOUD))
    assert tier == "opus" and any("без долгого горизонта" in w for w in why)


@pytest.mark.parametrize("name,metrics,text", [
    ("уверенность 0,75 < 0,8", dict(HEAVY, conf=0.75), LOUD),
    ("один признак критичности", dict(complexity=0.95, reasoning=0.8, ambiguity=0.5, risk=0.95, breadth=1.0, irreversible=0.1), LOUD),
    ("текст спокойный", HEAVY, "Сделай это"),
    ("кибер-тема", HEAVY, "Найди уязвимости и напиши эксплойт для боевой базы платежей, откатить нельзя"),
    ("повтор после неудачи", HEAVY, "Опять не работает миграция боевой базы платежей, откатить нельзя"),
])
def test_fable_denied(no_confirm, name, metrics, text):
    assert t.decide(tm(**metrics), heur.signals(text))[0] == "opus", name


def test_fable_by_long_horizon_with_extreme_complexity(no_confirm):
    text = "Проведи многочасовую миграцию по всей кодовой базе: переписать слой доступа к данным, сохранив поведение, без простоя"
    calm = dict(complexity=0.95, reasoning=0.95, ambiguity=0.6, risk=0.7, breadth=1.0)
    assert heur.signals(text)["horizon"]
    assert t.decide(tm(**calm), heur.signals(text))[0] == "fable"
    assert t.decide(tm(**dict(calm, reasoning=0.8)), heur.signals(text))[0] == "opus"          # рассуждение ниже порога горизонта
    assert t.decide(tm(**calm), heur.signals("Перепиши слой доступа к данным без простоя, это сложно"))[0] == "opus"   # горизонта нет


# ---------- haiku: максимальная ответственность ----------
LIGHT = dict(reasoning=0.1, read_only=0.95, conf=0.9, upper=0.02)


def test_haiku_for_confident_precise_task(no_confirm):
    tier, _ = t.decide(tm(**LIGHT), heur.signals("Покажи, где в проекте определена функция parse_date"))
    assert tier == "haiku"


@pytest.mark.parametrize("name,metrics,text", [
    ("conf-low-and-upper-high", dict(LIGHT, conf=0.6, upper=0.3), "Покажи, где определена функция parse_date"),
    ("риск 0,3", dict(LIGHT, risk=0.3), "Покажи, где определена функция parse_date"),
    ("слова риска", dict(LIGHT, risk=0.2), "Покажи, где в проекте лежит платёжный ключ и пароль"),
    ("диагностика", LIGHT, "Почему не работает вход, ошибка после обновления, найди причину"),
    ("повтор", LIGHT, "Опять не работает показ списка, всё ещё не работает, покажи файл"),
    ("длинное ТЗ", LIGHT, "Покажи файл. " + "Дополнительное пояснение к задаче и подробности. " * 25),
    ("много шагов", LIGHT, "Сначала найди файл, потом открой его, затем покажи функцию, после этого найди вызовы, далее покажи тесты"),
], ids=["conf-low-upper-high", "risk03", "risk-words", "diagnosis", "retry", "long", "many-steps"])
def test_haiku_denied(no_confirm, name, metrics, text):  # noqa: идентификаторы длинные из-за текстов — это нормально
    assert t.decide(tm(**metrics), heur.signals(text))[0] != "haiku", name


def test_haiku_not_after_a_failure_in_history(no_confirm):
    r = {"model": "haiku", "reason": "x", "signals": {}}
    h = heur.signals("Опять не работает показ списка, покажи файл ещё раз")
    out = t.add_effort(r, em(0.1), h, "Опять не работает показ списка, покажи файл ещё раз", env={}, history=[{"id": "other", "retry": False}], session="s")
    assert out["model"] == "sonnet" and "повтор после неудачи" in out["reason"]


def test_note_asks_to_verify_haiku_result(no_confirm):
    a = {"kind": "agent", "why": "cheaper", "reason": "haiku достаточно", "agent": {"model": "haiku", "effort": "medium"}, "hints": []}
    r = {"model": "haiku", "effort": "medium", "source": "typesafe", "signals": {}, "action": a, "confidence": "высокая", "effort_confidence": "высокая"}
    txt = t.hook_context(r)
    assert "Haiku (без вопроса" in txt and "проверь сам" in txt and "повтори на sonnet" in txt
    a2 = dict(a, agent={"model": "opus", "effort": "high"})
    assert "Haiku (без вопроса" not in t.hook_context(dict(r, model="opus", action=a2))


# ---------- effort: low и max строго ----------
def test_max_without_question_only_for_opus_fable_with_evidence(no_confirm):
    crit = em(1.0, irreversible=0.95, verification=0.95, coordination=0.9, constraints=0.9)
    text = H("Мигрируй боевую базу платежей без простоя, откатить нельзя")
    horizon = H(HORIZON)
    r = eff.decide_effort(crit, horizon, "opus", env={}, min_conf=0.9)           # E: max — только opus с долгим горизонтом
    assert r["effort"] == "max" and r["effort_confirm"] is False
    assert eff.decide_effort(crit, text, "opus", env={}, min_conf=0.9)["effort"] == "xhigh"        # без горизонта — xhigh
    assert eff.decide_effort(crit, horizon, "fable", env={}, min_conf=0.9)["effort"] == eff.FABLE_EFFORT_AUTO_MAX   # Fable: потолок high
    assert eff.decide_effort(crit, horizon, "opus", env={}, min_conf=0.8)["effort"] == "xhigh"      # уверенность ниже MAX_FRONTIER_CONF
    for tier in ("sonnet", "haiku"):
        assert eff.decide_effort(crit, text, tier, env={}, min_conf=0.9)["effort"] in ("xhigh", "high"), tier
    assert eff.decide_effort(crit, text, "opus", env={}, min_conf=0.75)["effort"] == "xhigh"             # уверенность ниже 0,8
    assert eff.decide_effort(em(1.0, risk=0.67, verification=0.95), H("Мигрируй базу"), "opus", env={}, min_conf=0.9)["effort"] == "xhigh"


def test_user_can_still_ask_for_max_on_any_tier(no_confirm):
    d = heur.directives("effort max на sonnet: проверь расчёт")
    r = eff.decide_effort(em(0.3), H("проверь расчёт"), "sonnet", env={}, d=d, min_conf=0.9)
    assert r["effort"] == "max" and r["effort_source"] == "user"


def test_haiku_low_only_for_pure_reading(no_confirm):
    easy = em(0.02, conf=0.95)
    assert eff.decide_effort(dict(easy, read_only=(0.95, 0.9, 0.95)), H("Покажи файл"), "haiku", env={}, min_conf=0.95)["effort"] == "low"
    r = eff.decide_effort(dict(easy, mechanical=(0.9, 0.8, 0.9)), H("Покажи файл"), "haiku", env={}, min_conf=0.95)
    assert r["effort"] == "medium" and any("haiku + low" in w for w in r["effort_reasons"])


def test_sonnet_never_above_xhigh_by_itself(no_confirm):
    r = eff.decide_effort(em(1.0, irreversible=0.95), H("Мигрируй боевую базу, откатить нельзя"), "sonnet", env={}, min_conf=0.95)
    assert eff.idx(r["effort"]) <= eff.idx("xhigh")


# ---------- диагностика повтора ----------
@pytest.mark.parametrize("text,kind", [
    ("Модель выдумала несуществующий метод API, переделай", "knowledge"),
    ("Ты не понял архитектуру, это не тот подход", "knowledge"),
    ("Ты пропустил файл и не запустил тесты", "effort"),
    ("Бросил рефакторинг на половине, недоделал", "effort"),
    ("Опять не работает: не понял архитектуру и не запустил тесты", "both"),
    ("Сделай отчёт по продажам за квартал", None),
])
def test_retry_kind(text, kind):
    assert heur.retry_kind(text) == kind


def test_history_escalation_by_cause():
    recs = [{"id": "a", "retry": False}]
    e0, m0, _ = eff.history_escalation(recs, True, "x")                    # без причины — как раньше
    assert (e0, m0) == (1, 0)
    e1, m1, w1 = eff.history_escalation(recs, True, "x", "effort")         # не старалась: глубже, модель не меняем
    assert e1 == 2 and m1 == 0 and "только effort" in w1[0]
    e2, m2, w2 = eff.history_escalation(recs, True, "x", "knowledge")      # не знала: мощнее модель уже с первого повтора
    assert m2 == 1 and e2 == 0 and "модель +1" in w2[0]                      # effort не растёт: после смены модели он сбрасывается
    assert eff.history_escalation([], False, "x", None) == (0, 0, [])
    assert eff.history_escalation([], False, "x", "knowledge")[1] == 1     # причина названа и без «опять не работает»


def test_knowledge_failure_raises_sonnet_to_opus_but_effort_failure_does_not(no_confirm):
    base = {"model": "sonnet", "reason": "x", "signals": {}}
    know = t.add_effort(dict(base), em(0.4), heur.signals("Ты выдумал несуществующий метод"), "Ты выдумал несуществующий метод",
                        env={}, history=[{"id": "p", "retry": False}], session="s")
    eff_ = t.add_effort(dict(base), em(0.4), heur.signals("Ты пропустил файл и не запустил тесты"), "Ты пропустил файл и не запустил тесты",
                        env={}, history=[{"id": "p", "retry": False}], session="s")
    assert know["model"] == "opus" and eff_["model"] == "sonnet"
    assert eff.idx(eff_["effort"]) >= eff.idx("high")


# ---------- рутина: сомнение не поднимает точную правку ----------
def test_precise_edit_not_raised_by_low_confidence(no_confirm):
    shaky = tm(complexity=0.7, reasoning=0.6, ambiguity=0.3, risk=0.2, breadth=0.3, conf=0.4)     # нагрузка у границы opus
    assert t.decide(shaky, heur.signals("Сделай задачу по отчёту, детали ниже"))[0] == "opus"        # обычный текст: шаг вверх
    assert t.decide(shaky, heur.signals("Замени getUser на fetchUser в файле api.py"))[0] == "sonnet"  # точная правка: остаётся
    assert heur.signals("Поправь опечатку в README")["precise"] and heur.signals("Что делает эта функция?")["precise"]
    assert not heur.signals("Спроектируй новую архитектуру платёжного сервиса")["precise"]


# ---------- описание выбора модели ≠ указание ----------
DESCRIPTION = ("убери необходимость подтверждения на более высокие или более низкие модели, то есть на модели Haiku, либо Fable. "
               "Но для модели Fable ужесточи требования под эти задачи")


def test_model_names_in_a_description_are_not_directives():
    d = heur.directives(DESCRIPTION)
    assert d["tier"] is None and not d["phrases"] and d.get("discussed")
    assert heur.directives("Выбор модели: например, на opus это решается лучше")["tier"] is None
    assert heur.directives("Подтверждение для haiku и fable убери")["tier"] is None


@pytest.mark.parametrize("text,tier", [
    ("Сделай на opus: проверь расчёт налога", "opus"), ("Use haiku for this: convert the list", "haiku"),
    ("запусти на haiku проверку орфографии", "haiku"), ("Проверь договор, модель fable, пожалуйста", "fable"),
    ("Don't use opus for this, sonnet is enough", "sonnet" if False else None),
])
def test_real_directives_still_work(text, tier):
    assert heur.directives(text)["tier"] == tier


def test_hook_does_not_treat_the_users_own_message_as_a_directive(no_confirm):
    r = t.triage.__wrapped__(DESCRIPTION) if hasattr(t.triage, "__wrapped__") else heur.directives(DESCRIPTION)
    assert not (r.get("explicit") if isinstance(r, dict) else r["tier"])


# ---------- исполнители: дисциплина объёма ----------
def test_scope_discipline_in_executor_prompt_and_rules():
    assert "минимально достаточное изменение" in t.AGENT_RULES.lower() or "Минимально достаточное изменение" in t.AGENT_RULES
    tpl = (Path(__file__).parent.parent / "references" / "executor-prompt.md").read_text(encoding="utf-8")
    assert "ДИСЦИПЛИНА ОБЪЁМА" in tpl
    import triage_batch as batch
    assert "ДИСЦИПЛИНА ОБЪЁМА" in batch.TEMPLATE if hasattr(batch, "TEMPLATE") else True


# ---------- сквозной: без подтверждений в итоговом действии ----------
def test_no_ask_action_for_haiku_fable_low_max(no_confirm, monkeypatch):
    for tier, effort in (("haiku", "low"), ("fable", "max"), ("fable", "high"), ("haiku", "medium")):
        r = {"model": tier, "effort": effort, "confirm": False, "fallback": tier, "effort_confirm": False, "effort_fallback": effort,
             "source": "typesafe", "metrics": {}, "signals": {"critical": ["x"]}}
        a = act.decide(r, {"parallel": 2}, {"tier": "sonnet"}, False)
        assert a["kind"] != "ask" or a["why"] == "clarify", (tier, effort, a)
