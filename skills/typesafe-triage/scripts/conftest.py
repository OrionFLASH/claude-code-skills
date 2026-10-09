# -*- coding: utf-8 -*-
"""Общая изоляция офлайн-тестов (2.3): модель и effort сессии, параметр effort у Agent и журнал проекта не берутся из
окружения запуска (переменные Claude Code, ~/.claude/settings.json), иначе заметка зависела бы от машины.
Переменные ставятся в os.environ — их наследуют и подпроцессы-хуки сквозных тестов. Тесты, которым нужна модель
сессии, задают TYPESAFE_TRIAGE_SESSION_MODEL сами."""
import pytest


@pytest.fixture(autouse=True)
def _isolated_session(monkeypatch):
    monkeypatch.setenv("TYPESAFE_TRIAGE_SESSION_MODEL", "unknown")
    for k in ("TYPESAFE_TRIAGE_AGENT_EFFORT", "TYPESAFE_TRIAGE_PROJECT_LOG", "CLAUDE_EFFORT", "ANTHROPIC_MODEL",
              "CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_SESSION_ID"):
        monkeypatch.delenv(k, raising=False)
