# -*- coding: utf-8 -*-
"""Сквозные тесты: настоящий подпроцесс-хук против локального поддельного сервера TypeSafe (без интернета и без расходов).
Проверяют, что при нехватке средств / неверном ключе / квоте / лимите / перегрузке / зависании / недоступности хук
показывает предупреждение пользователю, прекращает запросы (уровень дальше — по локальной эвристике) и снова работает
с TypeSafe после исправления; что реплики и команды не уходят на сервер; что fable требует подтверждения. pytest test_typesafe_e2e.py"""
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "typesafe_triage.py"
PROMPT = {"prompt": "Исправь падение теста test_login в сервисе авторизации: таймаут при вызове", "cwd": "/tmp"}


FLAGS = ("read_only", "mechanical", "needs_investigation", "silent_errors", "irreversible", "novel_design", "conversational")


def ok_body(extreme=False):
    lvl = 3.0 if extreme else 1.0
    a = {"complexity": {"score": lvl, "confidence": 0.9}, "reasoning": {"score": lvl, "confidence": 0.9},
         "ambiguity": {"score": 1.0, "confidence": 0.9}, "risk": {"score": lvl, "confidence": 0.9},
         "breadth": {"score": lvl, "confidence": 0.9}}
    for k in FLAGS:
        a[k] = {"noul": 0.95 if extreme and k == "irreversible" else 0.05}
    a["domain"] = {"choice": "software", "confidence": 0.9}
    return {"answers": a, "usage": {"input_tokens": 1000}}


def ctx(out):
    return out.get("hookSpecificOutput", {}).get("additionalContext", "")


def ts_note(out):
    return ctx(out).startswith("TypeSafe-триаж: уровень") and "(TypeSafe, уверенность" in ctx(out)


def heuristic_only(out):
    """Во время паузы: без предупреждения пользователю, но с уровнем по эвристике."""
    return "systemMessage" not in out and "ВАЖНО" not in ctx(out) and "только эвристика, уверенность низкая" in ctx(out)


class Fake(BaseHTTPRequestHandler):
    mode = ("ok",)
    hits = 0

    def log_message(self, *a):
        pass

    def do_POST(self):
        Fake.hits += 1
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        mode, *arg = Fake.mode
        if mode == "hang":
            time.sleep(6)
        code, body, headers = {
            "ok": (200, ok_body(), {}),
            "extreme": (200, ok_body(extreme=True), {}),
            "402": (402, {"detail": {"error_type": "payment_required", "message": "Insufficient credits"}}, {}),
            "401": (401, {"detail": {"error_type": "authentication_error"}}, {}),
            "403": (403, {"detail": "Forbidden"}, {}),
            "quota": (429, {"detail": {"error_type": "quota_exceeded"}}, {}),
            "rate": (429, {"detail": {"error_type": "rate_limit_exceeded"}}, {"Retry-After": "120"}),
            "503": (503, {"detail": "overloaded"}, {}),
            "hang": (200, ok_body(), {}),
        }[mode]
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(raw)
        except OSError:
            pass


@pytest.fixture()
def server():
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    Fake.hits, Fake.mode = 0, ("ok",)
    yield srv
    srv.shutdown()


def hook(srv, home, key="fake-key", prompt=PROMPT, url=None):
    env = dict(os.environ, TYPESAFE_API_URL=url or "http://127.0.0.1:%d/v1/systemone" % srv.server_port,
               TYPESAFE_API_KEY=key, TYPESAFE_TRIAGE_HOME=str(home))
    t0 = time.time()
    r = subprocess.run([sys.executable, "-B", str(SCRIPT), "--hook"], input=json.dumps(prompt), capture_output=True, text=True, env=env, timeout=30)
    out = json.loads(r.stdout) if r.stdout.strip() else {}
    return r.returncode, out, time.time() - t0


def cli(srv, home, *args, key="fake-key"):
    env = dict(os.environ, TYPESAFE_API_URL="http://127.0.0.1:%d/v1/systemone" % srv.server_port, TYPESAFE_API_KEY=key, TYPESAFE_TRIAGE_HOME=str(home))
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=30)


def test_normal_flow_gives_recommendation_and_counts_usage(server, tmp_path):
    rc, out, _ = hook(server, tmp_path)
    assert rc == 0 and "systemMessage" not in out and ts_note(out)
    assert json.loads((tmp_path / "state.json").read_text())["usage"]
    assert "запросов 1" in cli(server, tmp_path, "--status").stdout


@pytest.mark.parametrize("mode,kind", [("402", "billing"), ("quota", "billing"), ("403", "forbidden"), ("401", "auth")])
def test_hard_failures_warn_user_stop_requests_and_resume(server, tmp_path, mode, kind):
    Fake.mode = (mode,)
    rc, out, _ = hook(server, tmp_path)
    assert rc == 0 and "приостанов" in out["systemMessage"].lower() and "сообщи пользователю" in out["hookSpecificOutput"]["additionalContext"]
    assert json.loads((tmp_path / "state.json").read_text())["pause"]["kind"] == kind
    hits = Fake.hits
    assert "только эвристика" in ctx(out)                      # уровень есть и без TypeSafe
    for _ in range(3):                                          # дальше ни одного запроса к сервису, предупреждение не повторяется
        rc, out, _ = hook(server, tmp_path)
        assert rc == 0 and heuristic_only(out)
    assert Fake.hits == hits
    Fake.mode = ("ok",)
    assert heuristic_only(hook(server, tmp_path)[1])            # пока не --resume — сервис не трогаем, даже если он «ожил»
    assert Fake.hits == hits
    assert "Пауза снята" in cli(server, tmp_path, "--resume").stdout
    rc, out, _ = hook(server, tmp_path)
    assert ts_note(out) and Fake.hits == hits + 1


def test_auth_pause_lifts_itself_when_key_is_changed(server, tmp_path):
    Fake.mode = ("401",)
    hook(server, tmp_path, key="old-key")
    hits = Fake.hits
    assert heuristic_only(hook(server, tmp_path, key="old-key")[1]) and Fake.hits == hits
    Fake.mode = ("ok",)
    rc, out, _ = hook(server, tmp_path, key="new-key")
    assert ts_note(out)


def test_rate_limit_pauses_temporarily(server, tmp_path):
    Fake.mode = ("rate",)
    assert heuristic_only(hook(server, tmp_path)[1])            # единичный сбой: без шума, уровень по эвристике
    st = json.loads((tmp_path / "state.json").read_text())
    assert st["pause"]["kind"] == "rate" and st["pause"]["until"] - time.time() > 40   # ≥ базовых 60 с
    hits = Fake.hits
    assert heuristic_only(hook(server, tmp_path)[1]) and Fake.hits == hits


def test_outage_warns_after_three_failures_and_recovers(server, tmp_path):
    Fake.mode = ("503",)
    for i in range(3):
        st_path = tmp_path / "state.json"
        if st_path.exists():                                   # имитируем истечение паузы
            st = json.loads(st_path.read_text())
            st["pause"]["until"] = time.time() - 1
            st_path.write_text(json.dumps(st))
        rc, out, _ = hook(server, tmp_path)
    assert "не отвечает" in out["systemMessage"] and Fake.hits == 6   # по два обращения на вызов: быстрый повтор при 503
    st = json.loads(st_path.read_text())
    st["pause"]["until"] = time.time() - 1
    st_path.write_text(json.dumps(st))
    Fake.mode = ("ok",)
    rc, out, _ = hook(server, tmp_path)
    assert "снова отвечает" in out["systemMessage"] and ts_note(out)


def test_hang_does_not_stall_the_prompt(server, tmp_path):
    Fake.mode = ("hang",)
    rc, out, dt = hook(server, tmp_path)
    assert rc == 0 and dt < 5.9, dt                             # тайм-аут хука 5 с, а не полное зависание сервера
    assert json.loads((tmp_path / "state.json").read_text())["failures"] == 1


def test_connection_refused_is_quiet_outage(server, tmp_path):
    rc, out, dt = hook(server, tmp_path, url="http://127.0.0.1:9/v1/systemone")
    assert rc == 0 and heuristic_only(out) and dt < 5
    assert json.loads((tmp_path / "state.json").read_text())["pause"]["kind"] == "outage"


def test_budget_ceiling_stops_before_overspend(server, tmp_path):
    (tmp_path).mkdir(exist_ok=True)
    (tmp_path / "config.json").write_text(json.dumps({"monthly_budget_usd": 0.00002}))   # ≈ 476 токенов: хватит на 0 запросов по 1000
    rc, out, _ = hook(server, tmp_path)                         # первый запрос выполняется, превышает потолок
    assert "потолок" in out["systemMessage"].lower()
    hits = Fake.hits
    assert heuristic_only(hook(server, tmp_path)[1]) and Fake.hits == hits   # дальше — ни одного запроса


@pytest.mark.parametrize("text", ["Спасибо, отлично получилось! Давай дальше по плану, как договорились.",
                                  "/commit с сообщением про исправление валидации формы входа", "ок"])
def test_chatter_and_commands_never_reach_the_server(server, tmp_path, text):
    rc, out, _ = hook(server, tmp_path, prompt={"prompt": text, "cwd": "/tmp"})
    assert rc == 0 and Fake.hits == 0 and "systemMessage" not in out          # 2.2: вместо молчания — строка о пропуске
    assert ctx(out).startswith("TypeSafe-триаж пропущен: ") and "\n" not in ctx(out)


def test_universal_task_and_fable_needs_confirmation(server, tmp_path):
    rc, out, _ = hook(server, tmp_path, prompt={"prompt": "Напиши письмо партнёрам о переносе сроков поставки на две недели", "cwd": "/tmp"})
    assert ts_note(out) and "AskUserQuestion" not in ctx(out)
    Fake.mode = ("extreme",)
    big = ("Спроектируй и проведи миграцию боевой базы платежей без простоя: двойная запись, сверка, переключение, откат; "
           "ошибка означает потерю денег клиентов, откатиться после переключения нельзя.")
    rc, out, _ = hook(server, tmp_path, prompt={"prompt": big, "cwd": "/tmp"})
    assert ctx(out).startswith("TypeSafe-триаж: уровень fable") and "AskUserQuestion" in ctx(out) and "«Нет, opus»" in ctx(out)


def test_duplicate_hook_calls_for_same_prompt_speak_once(server, tmp_path):
    """Ручной хук в settings.json + хук плагина: два процесса одновременно на один запрос — заметка ровно одна."""
    env = dict(os.environ, TYPESAFE_API_URL="http://127.0.0.1:%d/v1/systemone" % server.server_port,
               TYPESAFE_API_KEY="fake-key", TYPESAFE_TRIAGE_HOME=str(tmp_path))
    payload = json.dumps(dict(PROMPT, session_id="e2e-session"))
    procs = [subprocess.Popen([sys.executable, "-B", str(SCRIPT), "--hook"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, env=env) for _ in range(2)]
    outs = [p.communicate(payload, timeout=30)[0] for p in procs]
    assert all(p.returncode == 0 for p in procs)
    spoken = [o for o in outs if o.strip()]
    assert len(spoken) == 1 and ts_note(json.loads(spoken[0])) and Fake.hits == 1
    rc, out, _ = hook(server, tmp_path, prompt=dict(PROMPT, session_id="other-session"))
    assert ts_note(out)                                              # другая сессия — не дубль


def test_note_has_model_and_effort_pair(server, tmp_path):
    rc, out, _ = hook(server, tmp_path)
    c = ctx(out)
    assert rc == 0 and ", effort " in c.split("\n")[0] and "Agent(model=" in c and "effort=" in c
