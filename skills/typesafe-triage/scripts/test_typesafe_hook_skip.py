# -*- coding: utf-8 -*-
"""2.2.0, T-4: хук не молчит. Метка-дубль ставится до триажа, поэтому сбой или «убийство» первого вызова раньше
оставляли второй вызов (ручной хук + хук плагина) молчащим; любые исключения тоже глушились без следа.
Здесь — воспроизведение (настоящие процессы, поддельный сервер) и проверка исправления. pytest test_typesafe_hook_skip.py"""
import io
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import triage_effort as eff
import typesafe_triage as t

SCRIPT = Path(__file__).parent / "typesafe_triage.py"
TASK = "Исправь падение теста test_login в сервисе авторизации: таймаут при вызове"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(t.guard, "HOME", tmp_path / "guard")
    monkeypatch.delenv("TYPESAFE_TRIAGE", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv(t.CHILD_ENV, raising=False)
    monkeypatch.setattr(eff, "session_effort", lambda cwd=None: None)


def hook_raw(monkeypatch, capsys, payload):
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(payload if isinstance(payload, str) else json.dumps(payload)))
    assert t.run_hook() == 0
    out = capsys.readouterr().out
    return json.loads(out) if out.strip() else {}


def ctx(out):
    return out.get("hookSpecificOutput", {}).get("additionalContext", "")


def log_lines():
    return [json.loads(x) for x in t.LOG_PATH.read_text(encoding="utf-8").splitlines()] if t.LOG_PATH.exists() else []


# ---------- исключение внутри триажа ----------
def test_internal_error_is_reported_not_silent(monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("сломалось")
    monkeypatch.setattr(t, "triage", boom)
    out = hook_raw(monkeypatch, capsys, {"prompt": TASK, "session_id": "s1"})
    assert "триаж пропущен" in out["systemMessage"] and "RuntimeError" in out["systemMessage"]
    assert "триаж пропущен" in ctx(out)
    rec = log_lines()[-1]
    assert rec["skipped"].startswith("ошибка") and rec["session"] == eff.session_tag("s1") and "model" not in rec


def test_error_while_building_note_is_reported(monkeypatch, capsys):
    monkeypatch.setattr(t, "hook_context", lambda *a, **k: 1 / 0)
    out = hook_raw(monkeypatch, capsys, {"prompt": TASK, "session_id": "s1"})
    assert "ZeroDivisionError" in out["systemMessage"]


# ---------- зависание дольше бюджета хука ----------
def test_hang_beyond_budget_gives_heuristic_note_in_time(monkeypatch, capsys):
    monkeypatch.setattr(t, "HOOK_BUDGET_S", 2.2)
    real = t.triage

    def slow(task, **kw):
        time.sleep(5)
        return real(task, **kw)
    monkeypatch.setattr(t, "triage", slow)
    t0 = time.monotonic()
    out = hook_raw(monkeypatch, capsys, {"prompt": TASK, "session_id": "s1"})
    assert time.monotonic() - t0 < 3.5
    c = ctx(out)
    assert c.startswith("ДЕЙСТВИЕ: ") and "только эвристика" in c
    assert "триаж пропущен" in out["systemMessage"] and "не уложилась" in out["systemMessage"]
    assert log_lines()[-1]["source"] == "heuristic"


# ---------- дубль-метка: второй вызов не молчит, если первый не договорил ----------
def marker(sid, prompt):
    return t.guard.HOME / t.DEDUP_NAME / t.dedup_key(sid, prompt)


def dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


@pytest.mark.skipif(os.name == "nt", reason="проверка живости процесса — только POSIX")
def test_pending_marker_of_dead_process_is_taken_over(monkeypatch, capsys):
    p = {"prompt": TASK, "session_id": "s1"}
    f = marker("s1", TASK)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"state": "pending", "pid": dead_pid(), "ts": time.time()}))
    out = hook_raw(monkeypatch, capsys, p)
    assert ctx(out).startswith("ДЕЙСТВИЕ: ")
    assert json.loads(f.read_text())["state"] == "done"


def test_stale_pending_marker_is_taken_over(monkeypatch, capsys):
    f = marker("s1", TASK)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"state": "pending", "pid": os.getpid(), "ts": time.time() - t.PENDING_STALE_S - 1}))
    assert ctx(hook_raw(monkeypatch, capsys, {"prompt": TASK, "session_id": "s1"})).startswith("ДЕЙСТВИЕ: ")


def test_loser_waits_for_live_winner_then_stays_silent(monkeypatch, capsys):
    f = marker("s1", TASK)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"state": "pending", "pid": os.getpid(), "ts": time.time()}))

    def finish_later():
        time.sleep(0.4)
        f.write_text(json.dumps({"state": "done", "pid": os.getpid(), "ts": time.time()}))
    threading.Thread(target=finish_later, daemon=True).start()
    t0 = time.monotonic()
    assert hook_raw(monkeypatch, capsys, {"prompt": TASK, "session_id": "s1"}) == {}
    assert 0.3 < time.monotonic() - t0 < 3
    assert log_lines()[-1]["skipped"] == "дубль: заметку дал другой вызов хука"


def test_loser_takes_over_when_winner_never_finishes(monkeypatch, capsys):
    monkeypatch.setattr(t, "HOOK_BUDGET_S", 0.8)
    f = marker("s1", TASK)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"state": "pending", "pid": os.getpid(), "ts": time.time()}))   # «живой», но не отвечает
    t0 = time.monotonic()
    out = hook_raw(monkeypatch, capsys, {"prompt": TASK, "session_id": "s1"})
    assert time.monotonic() - t0 < 3
    assert ctx(out).startswith("ДЕЙСТВИЕ: ") and "первый вызов хука" in out["systemMessage"]


def test_done_marker_still_silences_true_duplicate(monkeypatch, capsys):
    p = {"prompt": TASK, "session_id": "s1"}
    assert ctx(hook_raw(monkeypatch, capsys, p))
    assert hook_raw(monkeypatch, capsys, p) == {}
    f = marker("s1", TASK)
    st = json.loads(f.read_text())
    assert st["state"] == "done" and set(st) == {"state", "pid", "ts"}         # в метке нет текста запроса
    assert os.name == "nt" or oct(f.stat().st_mode & 0o777) == "0o600"


# ---------- пропуски: короткая причина вместо молчания, запись в журнал ----------
@pytest.mark.parametrize("prompt,reason", [
    ("ок, продолжай", "короткая реплика"),
    ("Спасибо, отлично получилось! Давай дальше по плану, как договорились.", "реплика"),
    ("/review посмотри последние изменения в ветке, пожалуйста", "команда"),
    ("<task-notification>фоновая задача завершена, результат записан в файл</task-notification>", "служебное"),
])
def test_content_skip_gives_one_line_and_log(monkeypatch, capsys, prompt, reason):
    called = []
    monkeypatch.setattr(t, "triage", lambda *a, **k: called.append(1))
    out = hook_raw(monkeypatch, capsys, {"prompt": prompt, "session_id": "s1"})
    c = ctx(out)
    assert c.startswith("TypeSafe-триаж пропущен: ") and reason in c and "\n" not in c
    assert "systemMessage" not in out and called == []
    rec = log_lines()[-1]
    assert reason in rec["skipped"] and "task" not in rec and rec["chars"] == len(prompt)


def test_garbage_input_is_reported(monkeypatch, capsys):
    out = hook_raw(monkeypatch, capsys, "не json")
    assert "триаж пропущен" in out["systemMessage"]


def test_skip_records_do_not_count_as_history(monkeypatch, capsys):
    p = {"prompt": TASK, "session_id": "s1"}
    hook_raw(monkeypatch, capsys, p)
    hook_raw(monkeypatch, capsys, p)                       # дубль → запись «skipped»
    recs = eff.read_history(t.LOG_PATH, eff.session_tag("s1"))
    assert len(recs) == 1 and recs[0].get("model")


def test_switched_off_and_child_stay_silent(monkeypatch, capsys, tmp_path):
    (tmp_path / t.OFF_MARKER).write_text("")
    assert hook_raw(monkeypatch, capsys, {"prompt": TASK, "cwd": str(tmp_path)}) == {}
    (tmp_path / t.OFF_MARKER).unlink()
    monkeypatch.setenv(t.CHILD_ENV, "1")
    assert hook_raw(monkeypatch, capsys, {"prompt": TASK}) == {}
    assert not t.LOG_PATH.exists()


# ---------- настоящие процессы: первый вызов «убит» Claude Code по тайм-ауту ----------
class Hang(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        time.sleep(8)


@pytest.mark.skipif(os.name == "nt", reason="SIGKILL — только POSIX")
def test_e2e_killed_first_call_does_not_silence_second(tmp_path):
    srv = HTTPServer(("127.0.0.1", 0), Hang)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    env = dict(os.environ, TYPESAFE_API_URL="http://127.0.0.1:%d/v1/systemone" % srv.server_port,
               TYPESAFE_API_KEY="fake-key", TYPESAFE_TRIAGE_HOME=str(tmp_path))
    env.pop(t.CHILD_ENV, None)
    payload = json.dumps({"prompt": TASK, "session_id": "e2e-kill", "cwd": str(tmp_path)})
    try:
        a = subprocess.Popen([sys.executable, "-B", str(SCRIPT), "--hook"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=env)
        a.stdin.write(payload)
        a.stdin.close()
        dd = tmp_path / "dedup"
        for _ in range(100):                                   # ждём, пока первый вызов поставит метку
            if dd.exists() and any(dd.iterdir()):
                break
            time.sleep(0.05)
        assert dd.exists() and any(dd.iterdir())
        os.kill(a.pid, signal.SIGKILL)                         # так Claude Code обрывает хук по тайм-ауту
        a.wait()
        b = subprocess.run([sys.executable, "-B", str(SCRIPT), "--hook"], input=payload, capture_output=True, text=True,
                           env=dict(env, TYPESAFE_API_URL="http://127.0.0.1:9/v1/systemone"), timeout=30)
        out = json.loads(b.stdout) if b.stdout.strip() else {}
        assert b.returncode == 0 and ctx(out).startswith("ДЕЙСТВИЕ: "), b.stdout + b.stderr
    finally:
        srv.shutdown()


def test_legacy_empty_marker_from_old_version_counts_as_done(monkeypatch, capsys):
    """Во время обновления может работать старый хук (2.1, пустая метка): новый не ждёт его 8 с и не дублирует заметку."""
    f = marker("s1", TASK)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("")
    t0 = time.monotonic()
    assert hook_raw(monkeypatch, capsys, {"prompt": TASK, "session_id": "s1"}) == {}
    assert time.monotonic() - t0 < 1
    old = time.time() - t.DEDUP_S - 1
    os.utime(f, (old, old))
    assert ctx(hook_raw(monkeypatch, capsys, {"prompt": TASK, "session_id": "s1"})).startswith("ДЕЙСТВИЕ: ")


def test_marker_has_content_as_soon_as_it_exists(tmp_path):
    f = tmp_path / "m"
    t._marker_write(f, "pending", create=True)
    assert json.loads(f.read_text())["state"] == "pending" and not list(tmp_path.glob("*.tmp"))
    with pytest.raises(FileExistsError):
        t._marker_write(f, "pending", create=True)
    t._marker_write(f, "done")
    assert t._marker_read(f)[0] == "done" and (os.name == "nt" or oct(f.stat().st_mode & 0o777) == "0o600")
