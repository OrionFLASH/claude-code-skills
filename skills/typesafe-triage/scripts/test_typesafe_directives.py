# -*- coding: utf-8 -*-
"""2.9.1 (#68–#74): формы явных указаний пользователя — глаголы выбора («используй», «задействуй», «пусть сделает»), творительный
падеж, обращение, отрицание и исключение, вопросы как обсуждение, глагольные формы effort и субагента, подсказка «модель названа,
но не распознана». pytest test_typesafe_directives.py"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import triage_heuristics as heur

SCRIPT = Path(__file__).parent / "typesafe_triage.py"


def tier(text):
    return heur.directives(text)["tier"]


# ---------- #68: глаголы выбора ----------
@pytest.mark.parametrize("text,want", [
    ("Возьми Fable для миграции", "fable"), ("Сделай это на Fable", "fable"), ("Запусти агента на fable", "fable"),
    ("Через Fable перепиши модуль", "fable"), ("Use Fable for this task", "fable"), ("Используй модель Fable для миграции", "fable"),
    ("Выполни на опусе", "opus"),                                           # уже работало
    ("Используй Fable: перепиши модуль биллинга", "fable"), ("Используйте Fable", "fable"),
    ("Используй опус для этой задачи", "opus"), ("Используй Sonnet, задача простая", "sonnet"), ("Используй haiku для переименования", "haiku"),
    ("Задействуй Fable для миграции", "fable"), ("Примени Opus к этому модулю", "opus"), ("Привлеки Fable, задача большая", "fable"),
    ("Выбери opus", "opus"), ("Нужно использовать Fable для этой миграции", "fable"),
    ("Try Sonnet first", "sonnet"), ("Switch to opus", "opus"), ("Go with haiku", "haiku"), ("Pick Fable for the migration", "fable"),
])
def test_verbs_of_choice_are_directives(text, want):
    assert tier(text) == want


# ---------- #69: «пусть сделает», творительный, обращение ----------
@pytest.mark.parametrize("text,want", [
    ("Пусть это сделает Fable", "fable"), ("Пусть Opus проверит", "opus"), ("Попроси Opus проверить результат", "opus"),
    ("Let opus do it", "opus"), ("Делай фейблом", "fable"), ("Реши сонетом", "sonnet"), ("Сделай это опусом", "opus"),
    ("Fable, перепиши модуль биллинга", "fable"), ("Opus: проверь миграцию", "opus"), ("Haiku, please rename the files", "haiku"),
    ("Fable нужен для миграции, перепиши биллинг", "fable"), ("Opus подойдёт", "opus"), ("Хватит haiku", "haiku"),
])
def test_after_verb_instrumental_address(text, want):
    assert tier(text) == want


def test_address_is_not_a_directive_without_imperative_or_in_enumeration():
    assert tier("Opus, Sonnet и Haiku, сравни цены") is None
    assert tier("Fable, как известно, дорогая модель") is None


def test_address_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("TYPESAFE_TRIAGE_ADDRESS", "off")
    assert tier("Fable, перепиши модуль биллинга") is None
    assert tier("Используй Fable") == "fable"          # обычные глаголы выбора остаются


# ---------- #70: отрицание и исключение ----------
def test_negation_and_exclusion():
    d = heur.directives("Не используй Fable, хватит opus")
    assert d["tier"] == "opus" and d["tier_not"] == ["fable"]
    for text, no in [("Без Fable обойдёмся", "fable"), ("Fable не нужен, возьми sonnet", "fable"), ("Не надо использовать Fable", "fable"),
                     ("Кроме opus — любая", "opus"), ("Don't use Fable here", "fable"), ("Fable is overkill, use sonnet", "fable")]:
        assert no in heur.directives(text)["tier_not"], text
    assert tier("Fable не нужен, возьми sonnet") == "sonnet"
    assert tier("Не используй Fable. Используй Fable.") is None          # прямое противоречие — не угадываем
    assert heur.directives("Не используй Fable. Используй Fable.")["tier_not"] == ["fable"]


def test_negation_does_not_span_a_comma_clause():
    # раньше «не …, возьми opus» читалось как отрицание opus
    d = heur.directives("Не нужен fable, возьми opus")
    assert d["tier"] == "opus" and d["tier_not"] == ["fable"]


# ---------- #71: вопросы и обсуждение ----------
@pytest.mark.parametrize("text", [
    "Стоит ли использовать Fable для миграции?", "Можно ли взять Opus?", "Should I use Fable?", "Нужен ли Fable для миграции?",
    "Как использовать Fable в проекте?", "Используй Fable или Opus", "Is it worth using Fable for this?",
])
def test_questions_and_enumerations_are_discussion(text):
    assert tier(text) is None


def test_quoted_reported_and_noun_forms_are_not_directives():
    assert tier("Ассистент ответил: используй Fable") is None
    assert tier("В отчёте написано: используй Fable для задач") is None
    assert tier("Слово «используй Fable» не сработало") is None
    assert tier("Использование Fable в задачах — расскажи") is None
    assert tier("Покажи `используй Fable` в логе") is None


def test_directive_after_analysis_sentence_is_not_swallowed():
    # 2.8: «проанализируй» в окне 70 знаков гасило указание; глагол выбора теперь устойчив
    assert tier("Проанализируй логи сборки. Используй Fable") == "fable"
    assert tier("Проанализируй логи и используй Fable") == "fable"


# ---------- #72: effort ----------
@pytest.mark.parametrize("text,want", [
    ("Поставь effort max", "max"), ("Установи effort=high", "high"), ("Включи рассуждения на максимум", "max"), ("Думай на максимуме", "max"),
    ("Set reasoning to high", "high"), ("Use max effort", "max"), ("Switch to effort low", "low"), ("Используй effort xhigh", "xhigh"),
])
def test_effort_verb_forms(text, want):
    assert heur.directives(text)["effort"] == want


def test_effort_negation_and_discussion():
    d = heur.directives("Не ставь effort max")
    assert d["effort"] is None and d["effort_max"] == "xhigh"
    assert heur.directives("Расскажи, когда ставить effort max")["effort"] is None
    assert heur.directives("Объясни рассуждения высокого качества")["effort"] is None        # не уровень
    assert heur.directives("Сравни effort max и xhigh")["effort"] is None


# ---------- #73: субагент ----------
@pytest.mark.parametrize("text,want", [
    ("Привлеки агента для проверки", "agent"), ("Запусти трёх сабагентов", "agent"), ("Спавни агентов параллельно", "agent"),
    ("Создай агента для каждого файла", "agent"), ("Use an agent for each file", "agent"),
    ("Не привлекай агентов, сделай сам", "self"), ("Сделай самостоятельно", "self"), ("Агенты не нужны", "self"),
    ("Обойдись без помощи субагентов", "self"), ("Don't launch agents", "self"), ("Do it on your own", "self"),
    ("Самостоятельно, без помощников разберись", "self"), ("Не используй сабагентов", "self"),
    ("Это агент поддержки клиентов", None), ("Запусти агента поддержки", None),
    ("Запусти скрипт, который самостоятельно качает файлы", None),
])
def test_agent_requests(text, want):
    assert heur.action_signals(text)["agent_req"] == want


def test_agent_request_in_quotes_is_not_a_request():
    assert heur.action_signals("Фраза «привлеки агента» не сработала")["agent_req"] is None


# ---------- подсказка «модель названа, но не распознана» ----------
def test_bare_tier_hint_only_for_unrecognised_single_tier_with_request():
    assert heur.directives("Перепиши биллинг, Fable тут красиво зайдёт")["tier_bare"] == ["fable"]
    assert "tier_bare" not in heur.directives("Расскажи про Fable")                       # нет просьбы
    assert "tier_bare" not in heur.directives("Сравни opus, sonnet и haiku по цене")       # несколько уровней
    assert "tier_bare" not in heur.directives("Используй Fable")                           # распознано


def _hook(prompt):
    r = subprocess.run([sys.executable, "-B", str(SCRIPT), "--hook"], input=json.dumps({"prompt": prompt, "cwd": ".", "session_id": "d291"}),
                       capture_output=True, text=True, timeout=60,
                       env={**__import__("os").environ, "TYPESAFE_TRIAGE_LOG": "off", "TYPESAFE_API_KEY": ""})
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


def test_hook_note_for_verb_directive_and_for_bare_hint():
    note = _hook("Используй Fable, effort max: перепиши всю архитектуру биллинга с миграцией боевой базы без простоя")
    assert "fable" in note.split("\n")[0].lower() and "Задано пользователем" in note
    note = _hook("Перепиши архитектуру биллинга с миграцией боевой базы, Fable тут красиво зайдёт, это очень важно")
    assert "формулировка не распознана" in note


# ---------- #72: самооценка сложности ----------
def test_self_assessed_difficulty_bounds_effort():
    d = heur.directives("Используй Sonnet, задача простая: переименуй переменную")
    assert d["tier"] == "sonnet" and d["effort_max"] == "medium" and d["effort_min"] is None
    assert heur.directives("Задача сложная, разберись")["effort_min"] == "high"
    assert heur.directives("This is a simple task, rename it")["effort_max"] == "medium"
    assert heur.directives("Что значит «задача простая»?")["effort_max"] is None      # в кавычках — упоминание
    assert heur.directives("Задача простая, но проверь тщательно")["effort_max"] is None      # противоречие — не применяем
