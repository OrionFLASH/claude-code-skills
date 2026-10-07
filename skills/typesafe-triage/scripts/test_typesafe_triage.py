# -*- coding: utf-8 -*-
"""Офлайн-тесты политики выбора модели (без сети и без записи в настоящий журнал): pytest test_typesafe_triage.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pytest
import typesafe_triage as t


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(t.guard, "HOME", tmp_path / "guard")     # состояние защиты — во временный каталог
    monkeypatch.delenv("TYPESAFE_TRIAGE", raising=False)


def m(complexity=0.0, reasoning=0.0, ambiguity=0.0, risk=0.0, conf=1.0, **flags):
    base = {"read_only": 0.0, "mechanical": 0.0, "needs_investigation": 0.0, "touches_data_rules": 0.0}
    base.update(flags)
    out = {k: (v, 1.0) for k, v in base.items()}
    for k, v in (("complexity", complexity), ("reasoning", reasoning), ("ambiguity", ambiguity), ("risk", risk)):
        out[k] = (v, conf)
    return out


def test_fable_never_recommended():
    assert "fable" not in t.TIERS
    for c in (0.0, 0.5, 1.0):
        for r in (0.0, 0.5, 1.0):
            assert t.decide(m(c, r, 1.0, 1.0, 0.0))[0] in ("haiku", "sonnet", "opus")


def test_haiku_only_for_safe_confident_light_tasks():
    assert t.decide(m(read_only=0.95))[0] == "haiku"
    assert t.decide(m())[0] == "sonnet"                                   # не только чтение/механика
    assert t.decide(m(read_only=0.95, conf=0.6))[0] == "sonnet"           # неуверенно — не haiku
    assert t.decide(m(read_only=0.95, risk=0.9))[0] == "sonnet"           # рискованно — не haiku


def test_data_rules_floor_and_opus():
    assert t.decide(m(touches_data_rules=0.9))[0] == "sonnet"
    assert t.decide(m(complexity=0.6, touches_data_rules=0.9))[0] == "opus"


def test_low_confidence_escalates_once_only():
    assert t.decide(m(complexity=0.5, reasoning=0.5, conf=0.3))[0] == "opus"
    assert t.decide(m(read_only=0.95, conf=0.3))[0] == "sonnet"           # haiku→sonnet, второй шаг не делаем


def test_heavy_task_gets_opus():
    assert t.decide(m(1.0, 1.0, 0.5, 1.0))[0] == "opus"


def test_no_key_or_no_network_gives_no_recommendation(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert t.triage("любая задача")["model"] is None
    def boom(*a, **k):
        raise t.urllib.error.URLError("offline")
    monkeypatch.setattr(t, "ask_typesafe", boom)
    r = t.triage("любая задача", key="x")
    assert r["model"] is None and r["paused"] == "outage"


def test_agent_cmd_uses_allowed_tier_only():
    cmd = t.build_agent_cmd("opus", readonly=True, budget=2)
    assert cmd[:4] == ["claude", "-p", "--model", "opus"]
    assert "plan" in cmd and "--max-budget-usd" in cmd
    assert "--permission-mode" not in t.build_agent_cmd("sonnet")
    import pytest
    for bad in ("fable", "claude-fable-5-1", "", None):
        with pytest.raises(ValueError):
            t.build_agent_cmd(bad)


def test_run_without_signal_uses_default_tier(monkeypatch, capsys):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert t.run_agent(["x", "--dry-run", "--readonly", "Объясни структуру папки"]) == 0
    assert "sonnet" in capsys.readouterr().err


def test_run_rejects_fable_and_empty_task(capsys):
    assert t.run_agent(["x", "--tier", "fable", "--dry-run", "задача"]) == 2
    assert t.run_agent(["x", "--dry-run"]) == 2


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


def test_hook_silent_for_non_dev_and_when_off(monkeypatch, capsys):
    import io, json
    long_prompt = "Какая сегодня погода в Москве и стоит ли брать зонт на завтра, подскажи"
    monkeypatch.setattr(t, "triage", lambda *a, **k: {"model": "sonnet", "dev": False, "reason": "x", "metrics": {}})
    monkeypatch.setattr(t, "log", lambda *a, **k: None)
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps({"prompt": long_prompt})))
    assert t.run_hook() == 0 and capsys.readouterr().out == ""


def test_flag_thresholds_haiku_strict_protection_loose():
    assert t.decide(m(read_only=0.7))[0] == "sonnet"                     # 0.7 < 0.8 — haiku не открывается
    assert t.decide(m(read_only=0.9))[0] == "haiku"
    assert t.decide(m(touches_data_rules=0.45))[0] == "sonnet"           # слабое «да» уже защищает
    assert t.decide(m(complexity=0.6, touches_data_rules=0.45))[0] == "opus"


def test_redact_hides_secrets():
    text = "ключ sk-" "abcdefghijklmnop1234 и password=hunter2 и Bearer abcdefghijklmnopqrstu плюс обычный текст"
    out = t.redact(text)
    assert "sk-abc" not in out and "hunter2" not in out and "abcdefghijklmnopqrstu" not in out and "обычный текст" in out


def test_hook_survives_garbage_and_pauses_after_failure(monkeypatch, capsys):
    import io, json
    for raw in ("[]", "null", "не json", json.dumps({"prompt": 123})):
        monkeypatch.setattr(t.sys, "stdin", io.StringIO(raw))
        assert t.run_hook() == 0
    assert capsys.readouterr().out == ""
    calls = []
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(t.urllib.error.URLError("down")))
    monkeypatch.setenv("TYPESAFE_API_KEY", "k-test")
    prompt = json.dumps({"prompt": "Исправь падение теста test_login в сервисе авторизации, пожалуйста"})
    for _ in range(3):
        monkeypatch.setattr(t.sys, "stdin", io.StringIO(prompt))
        assert t.run_hook() == 0
    assert len(calls) == 1                                               # после первого сбоя — пауза, сеть не трогаем


def test_log_only_for_dev_and_private(tmp_path):
    t.log("общий вопрос", {"dev": False, "model": "sonnet"})
    assert not t.LOG_PATH.exists()
    t.log("правка кода password=hunter2", {"dev": True, "model": "sonnet", "reason": "r"})
    assert "hunter2" not in t.LOG_PATH.read_text(encoding="utf-8")
    assert oct(t.LOG_PATH.stat().st_mode & 0o777) == "0o600"


def test_harness_messages_are_not_sent(monkeypatch, capsys):
    import io, json
    calls = []
    monkeypatch.setattr(t, "triage", lambda *a, **k: calls.append(1) or {"model": "opus", "dev": True, "reason": "x", "metrics": {}})
    for p in ('<task-notification>\n<task-id>1</task-id> завершена, это длинное служебное сообщение среды</task-notification>',
              '[SYSTEM NOTIFICATION - NOT USER INPUT] фоновая задача завершена и вернула результат работы',
              '<agent-message from="abc">[Subagent hand-back] отчёт субагента о проделанной работе по ревью</agent-message>'):
        assert t.is_harness_message(p)
        monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps({"prompt": p})))
        assert t.run_hook() == 0
    assert calls == [] and capsys.readouterr().out == ""
    assert not t.is_harness_message("Исправь падение теста test_login в сервисе авторизации")


def test_agent_cmd_edit_and_allow():
    cmd = t.build_agent_cmd("sonnet", edit=True, allow=("Bash(git status)", "Bash(python3 -m pytest:*)"))
    assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"
    assert cmd.count("--allowedTools") == 2 and "Bash(git status)" in cmd
    with pytest.raises(ValueError):
        t.build_agent_cmd("sonnet", readonly=True, edit=True)
    assert t.run_agent(["x", "--edit", "--readonly", "--dry-run", "задача"]) == 2


def test_run_parses_allow_values_not_as_task(capsys):
    assert t.run_agent(["x", "--tier", "haiku", "--allow", "Bash(ls)", "--dry-run", "моя", "задача"]) == 0
    out = capsys.readouterr().out
    assert out.rstrip().endswith("моя задача") and "Bash(ls)" not in out.split("\n", 1)[1]


# ---- ограничение размера отправляемого текста ----
import io
import time
import urllib.error


def fake_answers(dev=0.9):
    a = {k: {"score": 1.0, "confidence": 0.9} for k in t.SCORES}
    for k in t.FLAGS:
        a[k] = {"noul": dev if k == "software_dev" else 0.1}
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
    assert r["model"] is None and "paused" not in r and "слишком велик" in r["reason"]
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
    monkeypatch.setattr(t, "triage", lambda *a, **k: called.append(1) or {"model": "opus", "dev": True, "reason": "x", "metrics": {}})
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps({"prompt": "Исправь падение теста test_login в сервисе авторизации сегодня"})))
    assert t.run_hook() == 0 and called == [] and capsys.readouterr().out == ""
    assert t.run_agent(["x", "--dry-run", "любая задача"]) == 2
    assert "Вложенный" in capsys.readouterr().out


def test_run_passes_child_marker_to_agent(monkeypatch):
    seen = {}
    monkeypatch.delenv(t.CHILD_ENV, raising=False)
    monkeypatch.setattr(t.subprocess, "run", lambda cmd, **kw: seen.update(kw) or type("R", (), {"returncode": 0})())
    assert t.run_agent(["x", "--tier", "haiku", "задача для агента"]) == 0
    assert seen["env"][t.CHILD_ENV] == "1" and seen["input"] == "задача для агента"


def test_advice_text_mentions_superpowers_and_forbids_fable():
    txt = t.hook_context({"model": "opus", "reason": "r", "metrics": {k: {"value": 0.5, "confidence": 0.9} for k in ("complexity", "reasoning", "ambiguity", "risk")}})
    assert "SuperPowers" in txt and "Model Selection" in txt and "не Fable" in txt and "Fable не использовать" in txt
