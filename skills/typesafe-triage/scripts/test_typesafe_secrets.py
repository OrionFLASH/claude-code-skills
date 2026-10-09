# -*- coding: utf-8 -*-
"""2.5.0: маскировка секретов и персональных данных, политика «что не отправлять в TypeSafe». Безопасность: значения секретов
не должны попадать ни в запрос к TypeSafe, ни в журнал, ни в заметку, ни в сообщения пользователю. pytest test_typesafe_secrets.py"""
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import triage_effort as eff
import triage_secrets as sec
import typesafe_triage as t

SCRIPT = Path(__file__).parent / "typesafe_triage.py"

SEED12 = "abandon ability able about above absent absorb abstract absurd abuse access accident"
GHP = "gh" "p_abcdefghijklmnopqrstuvwxyz0123456789"
AKID = "AK" "IAIOSFODNN7EXAMPLE"
JWT = "ey" "JhbGciOiJIUzI1NiJ9." "ey" "JzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
JWT_PART = "ey" "JzdWIiOiIxMjM0NTY3ODkwIn0"
PEM_OPENSSH = "-----BEGIN OPENSSH PRIVATE" " KEY-----\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmU\n-----END OPENSSH PRIVATE" " KEY-----"
PEM_RSA_CUT = "-----BEGIN RSA PRIVATE" " KEY-----\nMIIEowIBAAKCAQEA7bq98ewHdyXHjmoAOeJ"
MAIL = "ivan.petrov@example.com"
DBURL = "postgres://admin:pa55w0rd@example.com:5432/app"

# (описание, текст, секрет, который не должен остаться, ожидаемый вид, ожидаемый уровень)
POSITIVE = [
    ("ru пароль с двоеточием", "мой пароль: Qwerty123! для сервера", "Qwerty123!", "password", sec.SECRET),
    ("ru пароль от X", "пароль от сервера hunter2 не трогай", "hunter2", "password", sec.SECRET),
    ("ru пароль через тире", "логин admin, пароль — Zx9#kLm2", "Zx9#kLm2", "password", sec.SECRET),
    ("ru пароль это", "пароль это qwerty", "qwerty", "password", sec.SECRET),
    ("ru пароль в кавычках", "пароль = 'Tr0ub4dor&3'", "Tr0ub4dor&3", "password", sec.SECRET),
    ("ru пин-код", "пин-код: 4921", "4921", "password", sec.SECRET),
    ("en password=", "login with password=hunter2 please", "hunter2", "password", sec.SECRET),
    ("en passwd", "passwd: abc12345 for root", "abc12345", "password", sec.SECRET),
    ("json password", '{"user": "bob", "password": "s3cr3t!x"}', "s3cr3t!x", "password", sec.SECRET),
    ("env secret", "export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "token", sec.SECRET),
    ("ru токен", "токен: 12345678:AAFabcdefghijklmnopqrstuvwxyz0123456", "AAFabcdefghijklmnopqrstuvwxyz0123456", "token", sec.SECRET),
    ("api_key", "api_key=abcdefghijklmnop", "abcdefghijklmnop", "token", sec.SECRET),
    ("telegram bot", "бот 123456789:AAFabcdefghijklmnopqrstuvwxyz0123456 не отвечает", "AAFabcdefghijklmnopqrstuvwxyz0123456", "token", sec.SECRET),
    ("github token", GHP + " в CI", GHP, "token", sec.SECRET),
    ("aws key id", "ключ " + AKID, AKID, "token", sec.SECRET),
    ("bearer", "curl -H 'Authorization: Bearer abcdefghijklmnopqrstu'", "abcdefghijklmnopqrstu", "token", sec.SECRET),
    ("jwt", "сессия " + JWT, JWT_PART, "jwt", sec.SECRET),
    ("url с паролем", DBURL, "pa55w0rd", "url_cred", sec.SECRET),
    ("cvv", "карта, cvv 123", "123", "cvv", sec.SECRET),
    ("seed с подписью (en)", "my seed phrase: abandon ability able about above absent absorb abstract absurd abuse access accident",
     "abandon ability able about", "seed_phrase", sec.CRITICAL),
    ("seed с подписью (ru)", "сид-фраза: abandon ability able about above absent absorb abstract absurd abuse access accident",
     "absorb abstract", "seed_phrase", sec.CRITICAL),
    ("seed мнемоническая фраза", "мнемоническая фраза - abandon ability able about above absent absorb abstract absurd abuse access accident",
     "absent absorb", "seed_phrase", sec.CRITICAL),
    ("seed без подписи", "abandon ability able about above absent absorb abstract absurd abuse access accident",
     "ability able about", "seed_phrase", sec.CRITICAL),
    ("seed по одному слову в строке", "\n".join("abandon ability able about above absent absorb abstract absurd abuse access accident".split()),
     "absorb", "seed_phrase", sec.CRITICAL),
    ("seed с номерами", "1. abandon 2. ability 3. able 4. about 5. above 6. absent 7. absorb 8. abstract 9. absurd 10. abuse 11. access 12. accident",
     "absurd", "seed_phrase", sec.CRITICAL),
    ("pem", "ключ:\n" + PEM_OPENSSH + "\nгде хранить?",
     "b3BlbnNzaC1rZXktdjEAAAAABG5vbmU", "private_key", sec.CRITICAL),
    ("pem без конца (обрезан)", PEM_RSA_CUT, "MIIEowIBAAKCAQEA7bq98ewHdyXHjmoAOeJ", "private_key", sec.CRITICAL),
    ("карта Visa", "оплата картой 4111 1111 1111 1111 не проходит", "4111 1111 1111 1111", "card", sec.CRITICAL),
    ("карта Mastercard слитно", "карта 5555555555554444", "5555555555554444", "card", sec.CRITICAL),
    ("ethereum private key", "key 0x4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318", "4c0883a69102937d6231471b5dbb6204fe512961", "crypto_key", sec.CRITICAL),
    ("bitcoin wif", "wif 5HueCGU8rMjxEXxiPuD5BDku4MkFqeZyd4dZ1jvhTVqvbTLvyTJ", "5HueCGU8rMjxEXxiPuD5BDku4MkFqeZyd4dZ1jvhTVqvbTLvyTJ", "crypto_key", sec.CRITICAL),
    ("passphrase с пробелами", "passphrase: correct horse battery staple", "horse battery staple", "password", sec.SECRET),
    ("парольная фраза", "парольная фраза — лиса бежит через лес зимой", "бежит через лес", "password", sec.SECRET),
    ("curl -u", "curl -u deploy:S3cretPass! https://api.example.com/v1", "S3cretPass!", "password", sec.SECRET),
    ("sshpass", "sshpass -p 'my pass 42' ssh root@host", "my pass 42", "password", sec.SECRET),
    ("camelCase секрет", "clientSecret = 9f8e7d6c5b4a3f2e1d0c", "9f8e7d6c5b4a3f2e1d0c", "token", sec.SECRET),
    ("snake_case пароль БД", "db_password=Sup3rS3cret", "Sup3rS3cret", "token", sec.SECRET),
    ("приватный ключ словами", "приватный ключ: a1b2c3d4e5f6a7b8", "a1b2c3d4e5f6a7b8", "token", sec.SECRET),
    ("сессия в cookie", "Cookie: sessionid=7d3f9a1c55e84b2f", "7d3f9a1c55e84b2f", "token", sec.SECRET),
    ("код из СМС", "код из СМС: 482913, введи его", "482913", "otp", sec.SECRET),
    ("пароль админа", "пароль админа: Adm1n!2020", "Adm1n!2020", "password", sec.SECRET),
    ("пин без разделителя", "пин 4921 от карты", "4921", "password", sec.SECRET),
    ("url с пустым логином", "redis://:Sup3rS3cret@localhost:6379", "Sup3rS3cret", "url_cred", sec.SECRET),
    ("x-api-key", "x-api-key: 7f3a9c2e1b4d5f60", "7f3a9c2e1b4d5f60", "token", sec.SECRET),
    ("карта в 4 группах, любой префикс", "карта 5200-8282-8282-8210", "5200-8282-8282-8210", "card", sec.CRITICAL),
    ("email", "пишите " + MAIL, MAIL, "email", sec.PII),
    ("телефон", "звонить +7 (916) 123-45-67", "123-45-67", "phone", sec.PII),
    ("iban", "счёт GB82 WEST 1234 5698 7654 32", "1234 5698 7654 32", "iban", sec.PII),
    ("ИНН и паспорт", "ИНН 7707083893, паспорт 45 10 123456", "7707083893", "doc_id", sec.PII),
]

# безобидные тексты: ничего не должно маскироваться и срабатывать как секрет
BENIGN = [
    "Добавь валидацию пароля в форму входа и сброс пароля по email",
    "make the password field required and show a strength meter",
    "password reset flow should send a link to the user",
    "Исправь баг: сумма в отчёте не сходится с итогом за август, 12 регионов",
    "please fix the login bug in the settings page when user is offline today and then check all the pages again",
    "версия 1.2.3.4 релиз 2026-10-09 заказ 1700000000000 таймстамп",
    "token: str  # тип поля",
    "seed the database with test fixtures, then run migrations on all environments please now",
    "сделай ключ: значение в словаре и проверь тесты",
    "Пароль должен содержать минимум 8 символов, проверь это в валидаторе формы регистрации",
    "карта сайта sitemap.xml, номер заказа 4111, id 1234567890123456",
    "def check_password(user, password): return hash(password) == user.hash",
    "добавь поле secret_key в модель настроек и миграцию, а также тест на уникальность ключа",
    "объясни, чем отличается private key от public key в асимметричной криптографии",
    "сделай отправку кода из СМС повторной через 60 секунд, если пользователь не подтвердил",
    "curl https://api.example.com/health --silent и проверь код ответа",
    "узнать pin коды не нужно, а пароль должен быть не менее 8 символов: см. политику",
    "номер заказа 4521 4521 4521 45 и артикул 1234 5678 9012 3456",
]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(t.guard, "HOME", tmp_path / "guard")
    monkeypatch.delenv("TYPESAFE_TRIAGE", raising=False)
    monkeypatch.delenv(sec.ENV, raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr(eff, "session_effort", lambda cwd=None: None)


def fake_answers():
    a = {k: {"score": 1.0, "confidence": 0.9} for k in t.SCORES}
    for k in t.FLAGS:
        a[k] = {"noul": 0.1}
    a["domain"] = {"choice": "writing", "confidence": 0.8}
    return {"answers": a, "usage": {"input_tokens": 123}}


def hook(monkeypatch, capsys, prompt, sid="sec-1"):
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps({"prompt": prompt, "session_id": sid})))
    assert t.run_hook() == 0
    out = capsys.readouterr().out
    return json.loads(out) if out.strip() else {}


# ---------- детекторы ----------
@pytest.mark.parametrize("name,text,secret,kind,level", POSITIVE, ids=[p[0] for p in POSITIVE])
def test_detects_and_masks(name, text, secret, kind, level):
    r = sec.inspect(text)
    assert kind in r["kinds"], r
    assert r["level"] == level or sec.LEVEL_RANK[r["level"]] > sec.LEVEL_RANK[level]
    assert secret not in r["text"] and sec.MASK in r["text"]
    assert secret not in t.redact(text) and secret not in t.make_digest(text)


@pytest.mark.parametrize("text", BENIGN)
def test_benign_text_is_not_touched(text):
    r = sec.inspect(text)
    assert r["count"] == 0 and r["text"] == text and not sec.withhold(r)


def test_original_gaps_are_closed():
    """Замечание ревью: русское «пароль» и seed-фразы не скрывались."""
    assert "hunter2" not in t.redact("пароль: hunter2") and "hunter2" not in t.redact("мой пароль hunter2")
    seed = "abandon ability able about above absent absorb abstract absurd abuse access accident"
    assert "absorb" not in t.redact("seed: " + seed) and "absorb" not in t.redact(seed)


def test_luhn_and_prefix_reduce_false_positives():
    assert not sec.inspect("номер 4111 1111 1111 1112")["count"]              # не проходит Luhn
    assert not sec.inspect("номер 1234 5678 9012 3456")["count"]              # неизвестный префикс
    assert sec.inspect("номер 4111 1111 1111 1111")["kinds"] == {"card": 1}


def test_levels_and_description_have_no_values():
    r = sec.inspect("пароль: hunter2, почта a@example.com, карта 4111 1111 1111 1111")
    assert r["level"] == sec.CRITICAL and set(r["kinds"]) == {"password", "email", "card"}
    d = sec.describe(r["kinds"])
    assert "hunter2" not in d and "a@example.com" not in d and "пароль ×1" in d and d.index("номер банковской карты") < d.index("e-mail")


# ---------- политика ----------
def test_policy_values(monkeypatch):
    crit, secret, pii = sec.inspect("4111 1111 1111 1111"), sec.inspect("password=hunter2"), sec.inspect("a@example.com")
    assert sec.policy() == "block"
    assert sec.withhold(crit) and not sec.withhold(secret) and not sec.withhold(pii)
    monkeypatch.setenv(sec.ENV, "strict")
    assert sec.withhold(crit) and sec.withhold(secret) and sec.withhold(pii)
    monkeypatch.setenv(sec.ENV, "mask")
    assert not sec.withhold(crit) and not sec.withhold(secret)
    monkeypatch.setenv(sec.ENV, "off")          # выключить маскировку нельзя: неизвестное значение = block
    assert sec.policy() == "block" and sec.withhold(crit)
    assert "hunter2" not in t.redact("password=hunter2")


# ---------- что уходит в TypeSafe ----------
def capture(monkeypatch):
    sent = []
    monkeypatch.setattr(t, "ask_typesafe", lambda text, *a, **k: sent.append(text) or fake_answers())
    return sent


def test_critical_request_is_not_sent_at_all(monkeypatch):
    sent = capture(monkeypatch)
    text = "Вот мой seed: abandon ability able about above absent absorb abstract absurd abuse access accident — как лучше хранить? " + "x " * 30
    r = t.triage(text, session="s")
    assert sent == [] and r["source"] == "heuristic" and r["secrets"]["withheld"] and r["secrets"]["level"] == sec.CRITICAL
    assert "не отправлен" in r["notice"] and "seed-фраза" in r["notice"] and "absorb" not in json.dumps(r, ensure_ascii=False)


def test_secret_request_is_sent_masked(monkeypatch):
    sent = capture(monkeypatch)
    r = t.triage("Почини деплой: пароль от сервера hunter2, токен " + GHP + ", почта ivan@example.com", session="s")
    assert len(sent) == 1 and r["source"] == "typesafe" and r["secrets"]["withheld"] is False
    assert "hunter2" not in sent[0] and GHP not in sent[0] and "ivan@example.com" not in sent[0] and "Почини деплой" in sent[0]
    assert set(r["secrets"]["kinds"]) >= {"password", "token", "email"}


def test_strict_policy_withholds_any_finding(monkeypatch):
    sent = capture(monkeypatch)
    monkeypatch.setenv(sec.ENV, "strict")
    r = t.triage("Почини деплой, пароль: hunter2, потом проверь логи сервиса авторизации", session="s")
    assert sent == [] and r["secrets"]["withheld"] and "hunter2" not in json.dumps(r, ensure_ascii=False)


def test_mask_policy_still_masks(monkeypatch):
    sent = capture(monkeypatch)
    monkeypatch.setenv(sec.ENV, "mask")
    t.triage("Вот seed: abandon ability able about above absent absorb abstract absurd abuse access accident — проверь", session="s")
    assert len(sent) == 1 and "absorb" not in sent[0] and sec.MASK in sent[0]


def test_retry_digest_is_masked_too(monkeypatch):
    seen = []

    def ask(text, *a, **k):
        seen.append(text)
        if len(seen) == 1:
            raise t.urllib.error.HTTPError("u", 400, "Bad", {}, io.BytesIO(b'{"detail":{"error_type":"max_tokens_exceeded"}}'))
        return fake_answers()
    monkeypatch.setattr(t, "ask_typesafe", ask)
    t.triage("Разбери логи, пароль: hunter2 " + "строка лога " * 300, session="s")
    assert len(seen) == 2 and all("hunter2" not in x for x in seen)


def test_active_task_line_is_masked(monkeypatch, tmp_path):
    (tmp_path / "TASKS.md").write_text("- [ ] Деплой: пароль: hunter2 и токен " + GHP + "\n", encoding="utf-8")
    sent, _ = t.request_digest("продолжай тесты по плану, пожалуйста", str(tmp_path))
    assert "hunter2" not in sent and GHP not in sent


# ---------- хук: заметка, сообщения, журнал ----------
def test_hook_critical_notifies_and_logs_no_text(monkeypatch, capsys):
    sent = capture(monkeypatch)
    seed = "abandon ability able about above absent absorb abstract absurd abuse access accident"
    out = hook(monkeypatch, capsys, "Мой seed: " + seed + ". Как безопасно хранить такой ключ в приложении?")
    blob = json.dumps(out, ensure_ascii=False)
    assert sent == [] and "absorb" not in blob and "seed-фраза" in out["systemMessage"] and "не отправлен" in out["systemMessage"]
    assert "ВАЖНО (TypeSafe)" in out["hookSpecificOutput"]["additionalContext"]
    log = t.LOG_PATH.read_text(encoding="utf-8")
    assert "absorb" not in log and "критичные секреты" in log and '"seed_phrase"' in log


def test_hook_masked_secret_notifies_without_values(monkeypatch, capsys):
    capture(monkeypatch)
    out = hook(monkeypatch, capsys, "Почини вход на стенд: пароль от стенда hunter2, потом прогони тесты авторизации")
    blob = json.dumps(out, ensure_ascii=False) + t.LOG_PATH.read_text(encoding="utf-8")
    assert "hunter2" not in blob
    assert "замаскированы" in out["systemMessage"] and "пароль ×1" in out["systemMessage"]
    assert "Безопасность" in out["hookSpecificOutput"]["additionalContext"]
    assert '"password": 1' in t.LOG_PATH.read_text(encoding="utf-8")


def test_hook_pii_only_is_quiet(monkeypatch, capsys):
    capture(monkeypatch)
    out = hook(monkeypatch, capsys, "Напиши письмо клиенту ivan@example.com с отказом в скидке и предложи 10% при заказе на год вперёд")
    assert "systemMessage" not in out and "ivan@example.com" not in json.dumps(out, ensure_ascii=False) + t.LOG_PATH.read_text(encoding="utf-8")


def test_hook_plain_request_has_no_secret_notes(monkeypatch, capsys):
    capture(monkeypatch)
    out = hook(monkeypatch, capsys, "Добавь валидацию пароля в форму входа и сброс пароля по email, плюс тесты на оба сценария")
    assert "systemMessage" not in out and "Безопасность" not in json.dumps(out, ensure_ascii=False)
    assert "secrets" not in json.loads(t.LOG_PATH.read_text(encoding="utf-8").splitlines()[-1])


def test_log_text_masks_and_hides_critical():
    assert "hunter2" not in t.log_text("пароль: hunter2 и ещё текст")
    assert t.log_text("карта 4111 1111 1111 1111").startswith("[скрыто: запрос содержит критичные")


# ---------- CLI ----------
def run_cli(*args, stdin=None):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], capture_output=True, text=True, input=stdin, timeout=30)


def test_scan_cli_prints_kinds_only():
    r = run_cli("--scan", "пароль: hunter2 и карта 4111 1111 1111 1111")
    assert r.returncode == 3 and "hunter2" not in r.stdout + r.stderr and "4111" not in r.stdout
    j = json.loads(r.stdout)
    assert j["withheld"] and j["level"] == "critical" and j["kinds"] == {"password": 1, "card": 1}
    r = run_cli("--scan", "пароль: hunter2")
    assert r.returncode == 0 and json.loads(r.stdout)["withheld"] is False
    assert run_cli("--scan", "обычный текст без секретов").returncode == 0


def test_digest_cli_reports_and_masks():
    r = run_cli("--digest", "Почини вход: пароль: hunter2, потом проверь тесты")
    assert r.returncode == 0 and "hunter2" not in r.stdout and "секреты: пароль ×1" in r.stdout and "маскируются" in r.stdout
    r = run_cli("--digest", "seed: abandon ability able about above absent absorb abstract absurd abuse access accident")
    assert "absorb" not in r.stdout and "НЕ отправляется" in r.stdout


# ---------- скорость: враждебные входы не должны вешать хук ----------
@pytest.mark.parametrize("unit", ["пароль ", "password: ", "seed phrase ", "token=", "http://a:b@", "+7 123 ", "4111 1111 ", "SECRET_A_",
                                  "-----BEGIN PRIVATE" " KEY-----", "ey" "Jabcdefgh.", "0x" + "a" * 63 + " ", "ИНН 12 ", "abc def ", "a@", "A1 ", "aaaa-"])
def test_adversarial_inputs_are_fast(unit):
    text = (unit * (100000 // len(unit) + 1))[:100000]
    t0 = time.time()
    sec.inspect(text)
    assert time.time() - t0 < 2.0, unit


# ---------- сквозная проверка: что реально уходит по HTTP ----------
def test_wire_body_never_contains_secret_values(monkeypatch, capsys):
    """Поддельный сервер TypeSafe записывает тело каждого запроса: значения секретов в нём быть не должны, а запрос с critical — не приходить вовсе."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading
    bodies = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace")
            bodies.append(json.dumps(json.loads(raw), ensure_ascii=False))      # без \\u-экранирования: ищем значения как есть
            data = json.dumps(fake_answers()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(t, "API_URL", "http://127.0.0.1:%d/v1/systemone" % srv.server_port)
    try:
        values = ["hunter2", "Qwerty123!", GHP, "ivan@example.com", "+7 (916) 123-45-67", "pa55w0rd",
                  "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"]
        prompt = ("Почини деплой: пароль от сервера hunter2, мой пароль: Qwerty123!, токен " + GHP + ", "
                  "почта ivan@example.com, тел. +7 (916) 123-45-67, БД postgres://admin:pa55w0rd@example.com/app, "
                  "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY. Потом проверь тесты.")
        monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps({"prompt": prompt, "session_id": "wire-1"})))
        assert t.run_hook() == 0
        out = capsys.readouterr().out
        assert bodies, "запрос с замаскированными секретами должен уйти"
        for v in values:
            assert v not in bodies[0] and v not in out and v not in t.LOG_PATH.read_text(encoding="utf-8"), v
        assert "Почини деплой" in bodies[0]
        n = len(bodies)
        critical = ("Мой seed: abandon ability able about above absent absorb abstract absurd abuse access accident, "
                    "и карта 4111 1111 1111 1111 — как это безопасно хранить в приложении для заметок?")
        monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps({"prompt": critical, "session_id": "wire-2"})))
        assert t.run_hook() == 0
        out = capsys.readouterr().out
        assert len(bodies) == n, "запрос с critical не должен уходить в сеть"
        assert "absorb" not in out and "4111" not in out and "absorb" not in t.LOG_PATH.read_text(encoding="utf-8")
    finally:
        srv.shutdown()
