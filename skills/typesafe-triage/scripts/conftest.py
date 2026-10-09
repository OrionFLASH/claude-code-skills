# -*- coding: utf-8 -*-
"""Общая изоляция офлайн-тестов (2.3): модель и effort сессии, параметр effort у Agent и журнал проекта не берутся из
окружения запуска (переменные Claude Code, ~/.claude/settings.json), иначе заметка зависела бы от машины.
Переменные ставятся в os.environ — их наследуют и подпроцессы-хуки сквозных тестов. Тесты, которым нужна модель
сессии, задают TYPESAFE_TRIAGE_SESSION_MODEL сами."""
import atexit
import os
import shutil
import subprocess
import tempfile

import pytest

# 2.6.0 (#43): тесты не должны видеть настоящую среду пользователя (его ~/.claude/settings.json, где лежит TYPESAFE_API_KEY, журнал,
# состояние) и не должны ходить в настоящий TypeSafe. До импорта тестовых модулей (их константы считают пути при импорте):
# HOME и USERPROFILE (на Windows Path.home() берёт USERPROFILE) — во временную папку, ключ и пути скилла — убрать из окружения.
_TEST_HOME = tempfile.mkdtemp(prefix="typesafe-tests-home-")
atexit.register(shutil.rmtree, _TEST_HOME, ignore_errors=True)
for _k in ("HOME", "USERPROFILE"):
    os.environ[_k] = _TEST_HOME
for _k in ("TYPESAFE_API_KEY", "TYPESAFE_API_URL", "TYPESAFE_TRIAGE_HOME", "TYPESAFE_TRIAGE_PROJECTS", "TYPESAFE_TRIAGE_SECRETS",
           "TYPESAFE_TRIAGE_DELEGATE_DOWN", "TYPESAFE_TRIAGE_ECONOMY", "TYPESAFE_TRIAGE", "TYPESAFE_TRIAGE_CHILD", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(_k, None)
os.environ["PYTHONUTF8"] = "1"          # подпроцессы пишут и читают UTF-8 независимо от кодовой страницы (Windows: cp1251)
os.environ["PYTHONIOENCODING"] = "utf-8"

_real_popen_init = subprocess.Popen.__init__


def _utf8_popen_init(self, *args, **kwargs):
    """Тексты тестов на русском: text=True без encoding читает вывод в кодовой странице системы (cp1251 на Windows)."""
    if (kwargs.get("text") or kwargs.get("universal_newlines")) and not kwargs.get("encoding"):
        kwargs["encoding"] = "utf-8"
    env = kwargs.get("env")
    if isinstance(env, dict):
        env = dict(env)
        env.setdefault("PYTHONUTF8", "1")
        if "HOME" in env and "USERPROFILE" not in env:
            env["USERPROFILE"] = env["HOME"]       # подмена домашней папки через HOME на Windows не действует без USERPROFILE
        kwargs["env"] = env
    _real_popen_init(self, *args, **kwargs)


subprocess.Popen.__init__ = _utf8_popen_init


@pytest.fixture(autouse=True)
def _isolated_session(monkeypatch):
    monkeypatch.setenv("TYPESAFE_TRIAGE_SESSION_MODEL", "unknown")
    for k in ("TYPESAFE_TRIAGE_AGENT_EFFORT", "TYPESAFE_TRIAGE_PROJECT_LOG", "CLAUDE_EFFORT", "ANTHROPIC_MODEL",
              "CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_SESSION_ID"):
        monkeypatch.delenv(k, raising=False)
