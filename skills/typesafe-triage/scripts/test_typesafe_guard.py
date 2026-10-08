# -*- coding: utf-8 -*-
"""Офлайн-тесты защиты (паузы, нехватка средств, сбои сервиса, потолок расходов): pytest test_typesafe_guard.py"""
import io
import json
import sys
import threading
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import typesafe_guard as g
import typesafe_triage as t

NOW = 1_800_000_000.0  # фиксированный «сейчас» для расчётов времени
H = 3600


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "HOME", tmp_path / "guard")
    monkeypatch.setattr(t.guard, "HOME", tmp_path / "guard")
    monkeypatch.setattr(t, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.delenv("TYPESAFE_TRIAGE", raising=False)


# ---------- классификация ответов ----------
@pytest.mark.parametrize("code,body,kind", [
    (402, "", "billing"),
    (401, '{"detail":{"error_type":"authentication_error"}}', "auth"),
    (403, "forbidden", "forbidden"),
    (403, '{"detail":{"error_type":"insufficient_credits"}}', "billing"),
    (400, '{"detail":{"error_type":"insufficient_balance"}}', "billing"),
    (429, '{"detail":{"error_type":"quota_exceeded"}}', "billing"),
    (429, '{"detail":{"error_type":"rate_limit_exceeded"}}', "rate"),
    (400, '{"detail":{"error_type":"max_tokens_exceeded"}}', "size"),
    (503, "overloaded", "outage"),
    (529, "overloaded", "outage"),
    (500, "payment gateway down", "outage"),      # 5xx со словом payment — это сбой сервиса, не оплата
    (422, '[{"type":"missing"}]', "outage"),
])
def test_classify_http(code, body, kind):
    assert g.classify_http(code, body, {})[0] == kind


def test_retry_after_sources():
    assert g.classify_http(429, "", {"Retry-After": "42"})[2] == 42
    assert g.classify_http(429, "", {"retry-after-ms": "1500"})[2] == 1.5
    assert g.classify_http(429, '{"detail":{"retry_after_ms":2000}}', {})[2] == 2
    assert g.classify_http(429, "", {})[2] is None


# ---------- жёсткие паузы: нет средств / ключ / доступ ----------
def test_billing_pause_is_hard_and_never_auto_retries():
    msg = g.record_failure("billing", "payment_required", key="k", now=NOW)
    assert "ПРИОСТАНОВЛЕНО" in msg and "--resume" in msg and "console.typesafe.ai" in msg
    for dt in (1, 3600, 86400 * 30):                        # хоть через месяц — без авто-пробы
        assert g.status("k", now=NOW + dt)["allowed"] is False
    assert g.resume()["kind"] == "billing"
    assert g.status("k", now=NOW + 5)["allowed"] is True


def test_hard_pause_reminders_are_throttled():
    g.record_failure("billing", "x", key="k", now=NOW)      # пользователь уведомлён сразу при сбое
    assert g.status("k", now=NOW + 60)["notice"] is None
    assert g.status("k", now=NOW + 7 * H)["notice"] and g.status("k", now=NOW + 7 * H + 5)["notice"] is None
    assert g.status("k", now=NOW + 14 * H)["notice"]         # раз в remind_hours


def test_auth_pause_clears_when_key_changes():
    g.record_failure("auth", "bad key", key="old-key", now=NOW)
    assert g.status("old-key", now=NOW + 10)["allowed"] is False
    s = g.status("new-key", now=NOW + 10)
    assert s["allowed"] is True and g.load_state().get("pause") is None


def test_forbidden_and_manual_pause():
    assert "403" in g.record_failure("forbidden", "", key="k", now=NOW)
    assert g.status("k", now=NOW + 1)["kind"] == "forbidden"
    g.resume()
    g.pause_manual("пока не нужен")
    assert g.status("k")["kind"] == "manual" and not g.status("k")["allowed"]


# ---------- временные сбои ----------
def test_transient_backoff_grows_and_caps():
    untils = []
    for i in range(7):
        g.record_failure("outage", "x", key="k", now=NOW)
        untils.append(g.load_state()["pause"]["until"] - NOW)
    assert untils[:5] == [300, 600, 1200, 2400, 3600] and untils[5:] == [3600, 3600]


def test_retry_after_wins_when_longer_and_pause_expires():
    g.record_failure("rate", "429", retry_after=900, key="k", now=NOW)
    assert g.load_state()["pause"]["until"] == NOW + 900
    assert g.status("k", now=NOW + 899)["allowed"] is False
    assert g.status("k", now=NOW + 901)["allowed"] is True   # время вышло: следующий запрос — проверка


def test_transient_notice_only_for_persistent_failures_and_recovery_message():
    notices = [g.record_failure("outage", "x", key="k", now=NOW) for _ in range(10)]
    assert [i + 1 for i, n in enumerate(notices) if n] == [3, 10]
    assert "не отвечает" in notices[2]
    assert g.record_success(100, now=NOW + 5000) == "TypeSafe снова отвечает — совет по модели возобновлён."
    assert g.record_success(100, now=NOW + 5001) is None      # повторно — тихо
    assert g.load_state().get("pause") is None and g.load_state().get("failures") is None


def test_single_failure_is_silent_and_recovers_silently():
    assert g.record_failure("outage", "x", key="k", now=NOW) is None
    assert g.record_success(10, now=NOW + 400) is None


# ---------- локальный потолок расходов ----------
def test_budget_warning_then_pause_then_new_month():
    g.set_budget(0.001)                                        # ≈ 23 810 токенов
    assert g.record_success(10000, now=NOW) is None
    n = g.record_success(10000, now=NOW)                       # ≈ 84 % — предупреждение один раз
    assert n and "потолка" in n and g.record_success(10, now=NOW) is None
    n = g.record_success(10000, now=NOW)                       # превысили — пауза
    assert n and "приостановлено" in n and g.status("k", now=NOW)["kind"] == "budget"
    assert g.status("k", now=NOW + 40 * 86400)["allowed"] is True   # другой месяц — потолок обнулён


def test_budget_zero_means_unlimited_and_raise_then_resume():
    g.set_budget(0)
    g.record_success(10**9, now=NOW)
    assert g.status("k", now=NOW)["allowed"] is True
    g.set_budget(0.001)
    assert g.status("k", now=NOW)["kind"] == "budget"          # уже превышено
    g.set_budget(1000)
    g.resume()
    assert g.status("k", now=NOW)["allowed"] is True


def test_cost_estimate_uses_public_price():
    g.record_success(1_000_000, now=NOW)
    assert abs(g.summary(NOW)["usage"]["cost_usd"] - 0.042) < 1e-9


# ---------- устойчивость состояния ----------
def test_corrupt_state_and_config_do_not_crash():
    g.HOME.mkdir(parents=True)
    (g.HOME / "state.json").write_text("{не json", encoding="utf-8")
    (g.HOME / "config.json").write_text("[1,2]", encoding="utf-8")
    assert g.status("k", now=NOW)["allowed"] is True and g.config()["monthly_budget_usd"] == 2.0
    g.record_success(5, now=NOW)
    assert (g.HOME / "state.json").stat().st_mode & 0o777 == 0o600


def test_threads_do_not_lose_updates():
    def work():
        for _ in range(50):
            g.record_success(10, now=NOW)
    th = [threading.Thread(target=work) for _ in range(8)]
    [x.start() for x in th]
    [x.join() for x in th]
    assert g.summary(NOW)["usage"]["requests"] == 400


# ---------- интеграция с triage и хуком ----------
def answers():
    a = {k: {"score": 1.0, "confidence": 0.9} for k in t.SCORES}
    for k in t.FLAGS:
        a[k] = {"noul": 0.9 if k == "software_dev" else 0.1}
    return {"answers": a, "usage": {"input_tokens": 1000}}


def http(code, body="", headers=None):
    return urllib.error.HTTPError("u", code, "x", headers or {}, io.BytesIO(body.encode()))


def test_triage_402_pauses_and_second_call_makes_no_network(monkeypatch):
    calls = []
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(http(402, '{"detail":"payment required"}')))
    r = t.triage("Исправь тест test_login", key="k")
    assert r["source"] == "heuristic" and r["paused"] == "billing" and "--resume" in r["notice"] and len(calls) == 1
    r2 = t.triage("Исправь тест test_login", key="k")
    assert r2["source"] == "heuristic" and r2["paused"] == "billing" and len(calls) == 1   # сеть не тронута, уровень — по эвристике
    assert t.triage("Исправь тест test_login", key="k")["notice"] is None            # напоминание не чаще раза в 6 ч


def test_triage_429_quota_vs_rate(monkeypatch):
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: (_ for _ in ()).throw(http(429, '{"detail":{"error_type":"quota_exceeded"}}')))
    assert t.triage("задача", key="k")["paused"] == "billing"
    g.resume()
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: (_ for _ in ()).throw(http(429, "slow down", {"Retry-After": "120"})))
    assert t.triage("задача", key="k")["paused"] == "rate"
    assert g.load_state()["pause"]["until"] - __import__("time").time() <= 301   # base 300 > retry-after 120


def test_triage_success_records_tokens_and_budget_warning(monkeypatch):
    g.set_budget(0.001)
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: dict(answers(), usage={"input_tokens": 20000}))
    r = t.triage("Исправь тест", key="k")
    assert r["source"] == "typesafe" and r["notice"] and "потолка" in r["notice"] and r["tokens"] == 20000
    assert g.summary()["usage"]["tokens"] == 20000


def test_hook_shows_system_message_once_then_stays_quiet(monkeypatch, capsys):
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: (_ for _ in ()).throw(http(402)))
    monkeypatch.setenv("TYPESAFE_API_KEY", "k-test")
    prompt = json.dumps({"prompt": "Исправь падение теста test_login в сервисе авторизации, пожалуйста", "cwd": "/tmp"})
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(prompt))
    assert t.run_hook() == 0
    out = json.loads(capsys.readouterr().out)
    assert "ПРИОСТАНОВЛЕНО" in out["systemMessage"] and "сообщи пользователю" in out["hookSpecificOutput"]["additionalContext"]
    assert "только эвристика" in out["hookSpecificOutput"]["additionalContext"]          # уровень всё равно есть
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(prompt))
    assert t.run_hook() == 0
    out = json.loads(capsys.readouterr().out)                               # второй запрос — без сети и без предупреждения,
    ctx = out["hookSpecificOutput"]["additionalContext"]                    # но с уровнем по эвристике
    assert "systemMessage" not in out and "ВАЖНО" not in ctx and "только эвристика" in ctx


def test_hook_never_blocks_prompt(monkeypatch, capsys):
    """Хук не должен ни блокировать запрос (exit 2 / decision block), ни падать, даже если защита сломана."""
    monkeypatch.setattr(t.guard, "status", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("сломано")))
    monkeypatch.setenv("TYPESAFE_API_KEY", "k-test")
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps({"prompt": "Исправь падение теста test_login в сервисе авторизации"})))
    assert t.run_hook() == 0 and "block" not in capsys.readouterr().out


def test_cli_status_resume_setbudget(capsys):
    g.record_failure("billing", "payment_required", key="k", now=NOW)
    assert t.main(["x", "--status"]) == 0
    out = capsys.readouterr().out
    assert "ПАУЗА: billing" in out and "НЕ баланс" in out
    assert t.main(["x", "--set-budget", "5"]) == 0 and g.config()["monthly_budget_usd"] == 5.0
    assert t.main(["x", "--set-budget", "abc"]) == 2
    assert t.main(["x", "--resume"]) == 0 and g.load_state().get("pause") is None
    assert t.main(["x", "--pause", "тест"]) == 0 and g.status("k")["kind"] == "manual"
