# -*- coding: utf-8 -*-
"""2.6.0: обращения пользователя (issues #36–#49): делегирование вниз, подсказки в заметке, экономный режим, отчёт, HTTP 451,
дубль хука в --where, команды в подсказках, пропущенные формы секретов, путь в начале запроса, SHA256SUMS. pytest test_typesafe_feedback.py"""
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import triage_action as act
import triage_effort as eff
import triage_install as inst
import triage_report as rep
import triage_secrets as sec
import typesafe_guard as g
import typesafe_triage as t

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = Path(__file__).parent / "typesafe_triage.py"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(t.guard, "HOME", tmp_path / "guard")
    monkeypatch.setattr(g, "HOME", tmp_path / "guard")
    monkeypatch.delenv("TYPESAFE_TRIAGE", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(eff, "session_effort", lambda cwd=None: None)


def M(**kw):
    return {k: {"value": v, "confidence": 0.9} for k, v in kw.items()}


def result(model="sonnet", **kw):
    r = {"model": model, "effort": "high", "confirm": False, "fallback": model, "effort_confirm": False, "effort_fallback": "high",
         "source": "typesafe", "metrics": M(complexity=0.5, reasoning=0.5, mechanical=0.9, risk=0.1, irreversible=0.0), "signals": {}}
    r.update(kw)
    return r


# ---------- #49: путь в начале запроса ----------
@pytest.mark.parametrize("text,cmd", [
    ("/commit fix login", True), ("/typesafe-triage:typesafe-triage задача", True), ("/review", True), ("  /plan\nтекст", True),
    ("/Users/orionflash/Downloads/файл.md Просмотри пожелания и реализуй их, пожалуйста", False),
    ("/etc/nginx/nginx.conf не применяется после reload, разберись", False),
    ("/var/log/syslog полон ошибок диска, что делать", False),
    ("обычный текст", False),
])
def test_slash_command_vs_path(text, cmd):
    assert t.is_slash_command(text) is cmd
    if not cmd and len(text) >= 40:
        assert t.skip_reason(text) is None


# ---------- #42: HTTP 451 ----------
def test_451_is_region_with_fixed_hourly_pause():
    body = '{"title":"Typesafe is not available in your region.","status":451}'
    assert g.classify_http(451, body)[0] == "region"
    assert g.classify_http(503, "x")[0] == "outage" and g.classify_http(429, "x")[0] == "rate"
    now = 1_800_000_000
    first = g.record_failure("region", "HTTP 451", None, "k", now=now)
    assert first and "HTTP 451" in first and "регион" in first
    st = g.status("k", now=now + 10)
    assert not st["allowed"] and st["kind"] == "region"
    p = g.load_state()["pause"]
    assert p["until"] - now == 3600 and not g.load_state().get("failures")       # без счётчика сбоев и удвоения
    again = g.record_failure("region", "HTTP 451", None, "k", now=now + 3700)
    assert again is None                                                        # напоминание один раз за паузу
    assert g.load_state()["pause"]["until"] == now + 3700 + 3600
    assert g.status("k", now=now + 3700 + 3601)["allowed"]                       # пауза вышла: следующий запрос — проверка
    g.resume()
    assert g.status("k", now=now)["allowed"]


def test_451_in_triage_falls_back_without_retries(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise t.urllib.error.HTTPError("u", 451, "x", {}, io.BytesIO(b'{"status":451}'))
    monkeypatch.setattr(t, "ask_typesafe", boom)
    r = t.triage("Почини деплой сервиса авторизации, тесты падают на таймауте соединения с базой", key="k", session="s")
    assert r["source"] == "heuristic" and r["paused"] == "region" and "451" in (r["notice"] or "")
    r2 = t.triage("Почини деплой сервиса авторизации, тесты падают на таймауте соединения с базой", key="k", session="s")
    assert len(calls) == 1 and r2["paused"] == "region"


# ---------- #45: команды в подсказках ----------
def test_guard_messages_use_platform_python_and_real_script():
    for kind in ("billing", "auth", "forbidden", "manual", "region"):
        m = g.message(kind, "x", 1_800_000_000)
        if "--resume" in m:
            assert ("%s %s --resume" % (g.PY, g.SCRIPT)) in m
    assert g.message("budget", cost=3.0, cap=2.0).count("%s %s --set-budget" % (g.PY, g.SCRIPT)) == 1
    assert g.PY == ("python" if os.name == "nt" else "python3")


def test_guard_messages_follow_the_py_command(monkeypatch):
    monkeypatch.setattr(g, "PY", "python")
    assert "python " in g.message("billing") and "python3" not in g.message("billing")


# ---------- #44: один хук — одна строка, если cwd = домашняя папка ----------
def test_where_does_not_duplicate_hook_when_cwd_is_home(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    cmd = 'python3 "%s" --hook' % (SKILL / "scripts" / "typesafe_triage.py")
    (home / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": cmd}]}]}}))
    sf = [home / ".claude" / "settings.json", home / ".claude" / "settings.local.json", home / ".claude" / "settings.json", home / ".claude" / "settings.local.json"]
    assert len(t.hook_entries(sf, str(home))) == 1
    files = inst.settings_files(str(home), str(home))
    assert len(files) == 2 and len({str(p.resolve()) for _l, p in files}) == 2
    assert len(inst.settings_files(str(home), str(tmp_path / "project"))) == 4


# ---------- #46: пропущенные формы секретов ----------
@pytest.mark.parametrize("text,secret", [
    ("sudo-пароль 1, зайди на сервер и обнови", "1"),
    ("root-пароль Xk9, потом перезагрузи", "Xk9"),
    ("wifi-password qwerty и ещё что-то", "qwerty"),
    ("пароль 12 для тестового стенда", "12"),
    ("ключ от стенда " + "ts_" + "live_AbCdEf123456 вставь в конфиг", "AbCdEf123456"),
    ("API key for prod: Zk93JdUe8sLpQw21xYz in config", "Zk93JdUe8sLpQw21xYz"),
    ("токен GhIjKl12MnOpQr34St бота", "GhIjKl12MnOpQr34St"),
])
def test_missed_secret_forms_are_masked(text, secret):
    r = sec.inspect(text)
    assert r["count"] >= 1 and secret not in r["text"], r


@pytest.mark.parametrize("text", [
    "пароль не сохраняется после перезапуска", "пароль в базе хранится в виде хеша", "sudo-пароль нужен для установки", "root-пароль в вики",
    "пароль в 2 раза длиннее чем нужно", "ключ GetUserNameFromDatabase используется в коде", "вызов getUserSettingsForCurrentUser вернёт ключ",
])
def test_new_secret_forms_keep_prose_intact(text):
    assert sec.inspect(text)["count"] == 0


# ---------- #36: делегирование вниз ----------
def decide(r, down=True, tier="opus", a=None, **sess):
    return act.decide(r, a or {}, dict({"tier": tier}, **sess), False, opts={"delegate_down": down})


def test_delegate_down_catches_translation_by_units_and_moderate_risk():
    """Пример из обращения: «добавь 19 языков» — TypeSafe даёт риск ≈ 0,57 и механику ≈ 0,48; единиц работы 19."""
    r = result("sonnet", metrics=M(complexity=0.58, reasoning=0.1, risk=0.57, breadth=0.4, read_only=0.05, mechanical=0.48, irreversible=0.11))
    a = {"units": 19}
    d = act.decide(r, a, {"tier": "opus"}, False, opts={"delegate_down": True})
    assert d["kind"] == "agent" and d["why"] == "cheaper"
    assert act.decide(r, {}, {"tier": "opus"}, False, opts={"delegate_down": True})["why"] == "cheaper"        # механика 0,48 ≥ 0,45
    assert act.decide(result("sonnet", metrics=M(complexity=0.58, reasoning=0.1, risk=0.65, mechanical=0.9)), a, {"tier": "opus"}, False,
                      opts={"delegate_down": True})["why"] != "cheaper"                                         # риск выше 0,6 — нет


@pytest.mark.parametrize("text,units", [("Добавь 19 языков интерфейса", 19), ("Проверь 12 файлов в docs", 12), ("fix 5 tests", 5), ("версия 2026 года", 0)])
def test_units_signal(text, units):
    assert heur_units(text) == units


def heur_units(text):
    import triage_heuristics as heur
    return heur.action_signals(text)["units"]


def test_delegate_down_is_off_by_default():
    d = decide(result("sonnet"), down=False)
    assert d["kind"] == "self" and d["why"] == "not_higher"


def test_delegate_down_when_routine_and_isolated():
    d = decide(result("sonnet"))
    assert d["kind"] == "agent" and d["why"] == "cheaper" and d["agent"]["model"] == "sonnet"
    assert "дешевле" in d["reason"] and len(d["reason"].split()) <= act.REASON_MAX_WORDS


@pytest.mark.parametrize("name,r,a,sess,tier", [
    ("уровень не ниже сессии", result("opus"), {}, {}, "opus"),
    ("выше сессии", result("opus"), {}, {}, "sonnet"),
    ("высокий риск", result("sonnet", metrics=M(complexity=0.5, reasoning=0.5, mechanical=0.9, risk=0.7)), {}, {}, "opus"),
    ("необратимость", result("sonnet", metrics=M(complexity=0.5, reasoning=0.5, mechanical=0.9, irreversible=0.8)), {}, {}, "opus"),
    ("критичный признак", result("sonnet", signals={"critical": True}), {}, {}, "opus"),
    ("не рутина и не изолируемая", result("sonnet", metrics=M(complexity=0.5, reasoning=0.6, mechanical=0.1, read_only=0.1)), {}, {}, "opus"),
    ("общее состояние", result("sonnet", shared_state=["браузер"]), {}, {}, "opus"),
    ("долгое ожидание", result("sonnet"), {"wait": "всю ночь"}, {}, "opus"),
    ("просит сделать самому", result("sonnet"), {"agent_req": "self"}, {}, "opus"),
    ("мелочь", result("sonnet", metrics=M(complexity=0.2, reasoning=0.2, mechanical=0.9)), {}, {}, "opus"),
    ("модель сессии неизвестна", result("sonnet"), {}, {}, None),
])
def test_delegate_down_guards(name, r, a, sess, tier):
    d = decide(r, tier=tier, a=a, **sess)
    assert d["why"] != "cheaper", name


def test_delegate_down_blocked_by_expensive_context():
    r = result("sonnet", inherited={"model": "sonnet", "effort": "high"}, history_n=5)
    assert decide(r)["why"] != "cheaper"
    assert decide(result("sonnet"), a={"refs": True}, long=True)["why"] != "cheaper"


def test_delegate_down_haiku_needs_consent_and_no_means_self():
    r = result("haiku", confirm=True, fallback="sonnet")
    d = decide(r)
    assert d["kind"] == "ask" and d["then"] == "cheaper" and d["fallback"] == {"kind": "self"}


def test_delegate_down_effort_only_confirm_keeps_agent():
    r = result("sonnet", effort="max", effort_confirm=True, effort_fallback="xhigh")
    d = decide(r)
    assert d["kind"] == "ask" and d["fallback"] == {"kind": "agent", "model": "sonnet", "effort": "xhigh"}


def test_delegate_down_options_from_env_and_config(monkeypatch, tmp_path):
    assert t.delegate_down_on() is False
    monkeypatch.setenv("TYPESAFE_TRIAGE_DELEGATE_DOWN", "on")
    assert t.delegate_down_on() is True
    monkeypatch.setenv("TYPESAFE_TRIAGE_DELEGATE_DOWN", "off")
    assert t.delegate_down_on() is False
    monkeypatch.delenv("TYPESAFE_TRIAGE_DELEGATE_DOWN")
    g._write(g.config_path(), {"delegate_down": True, "economy": True})
    assert t.delegate_down_on() is True and t.economy_on() is True
    monkeypatch.setenv("TYPESAFE_TRIAGE_ECONOMY", "off")
    assert t.economy_on() is False


# ---------- #37 #38 #39: заметка ----------
def note_for(agent_effort=None, big=False, kind="agent", **sig):
    a = {"kind": kind, "why": "higher", "reason": "нужен opus, а модель сессии sonnet ниже", "agent": {"model": "opus", "effort": "high"},
         "hints": [], "big": big, "parallel": 0}
    r = result("opus", action=a, signals=dict({"effort": {"lang": "ru"}}, **sig), confidence="высокая", effort_confidence="высокая")
    if agent_effort is not None:
        r["agent_effort"] = agent_effort
    return t.hook_context(r)


def test_note_puts_depth_phrase_inside_agent_call_when_param_missing():
    n = note_for(agent_effort=False)
    first = n.split("\n")[0]
    assert first.startswith("ДЕЙСТВИЕ: Agent(model=opus; в промпт: «") and "effort=" not in first
    assert "Думай тщательно" in first
    assert note_for(agent_effort=True).split("\n")[0].startswith("ДЕЙСТВИЕ: Agent(model=opus, effort=high)")
    assert note_for(agent_effort=None).split("\n")[0].startswith("ДЕЙСТВИЕ: Agent(model=opus, effort=high)")


def test_note_hints_about_homogeneous_subtasks_and_explicit_model():
    for kw in ({"big": True}, {"items": 6}, {"paths": 4}):
        n = note_for(**kw)
        assert "Однотипные подзадачи" in n and "model у Agent явно" in n and "--batch" in n
    assert "Однотипные подзадачи" not in note_for()
    assert "Однотипные подзадачи" in note_for(kind="self", big=True)


# ---------- #41: экономный режим ----------
CALM = "Поправь опечатку в названии кнопки в файле README, пожалуйста, это мелкая правка текста"
RISKY = "Спроектируй и проведи необратимую миграцию боевой базы платежей без простоя, откат обязателен, аудит регулятора завтра"


def hook(monkeypatch, capsys, prompt, sid="eco"):
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps({"prompt": prompt, "session_id": sid})))
    assert t.run_hook() == 0
    out = capsys.readouterr().out
    return json.loads(out) if out.strip() else {}


def fake_session(monkeypatch, tier):
    monkeypatch.setattr(t.sess_mod, "session_info", lambda *a, **k: {"tier": tier, "model_source": "стенограмма"})


def test_economy_is_off_by_default(monkeypatch, capsys):
    fake_session(monkeypatch, "opus")
    monkeypatch.setattr(t, "triage", lambda *a, **k: result("sonnet", action=act.decide(result("sonnet"), {}, {"tier": "opus"}, False)))
    out = hook(monkeypatch, capsys, CALM)
    assert "ДЕЙСТВИЕ" in out["hookSpecificOutput"]["additionalContext"]


def test_economy_skips_calm_requests_on_opus_without_calling_typesafe(monkeypatch, capsys):
    monkeypatch.setenv("TYPESAFE_TRIAGE_ECONOMY", "on")
    fake_session(monkeypatch, "opus")
    called = []
    monkeypatch.setattr(t, "triage", lambda *a, **k: called.append(1))
    out = hook(monkeypatch, capsys, CALM)
    assert not called and "экономный режим: сессия на opus" in out["hookSpecificOutput"]["additionalContext"]
    rec = json.loads(t.LOG_PATH.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["skipped"].startswith("экономный режим") and isinstance(rec["ms"], int) and "model" not in rec


@pytest.mark.parametrize("name,prompt,tier,extra", [
    ("рискованный запрос", RISKY, "opus", {}),
    ("сессия на sonnet", CALM, "sonnet", {}),
    ("модель сессии неизвестна", CALM, None, {}),
    ("явное указание", "Сделай на opus: " + CALM, "opus", {}),
    ("просит субагента", "Запусти субагента: " + CALM, "opus", {}),
    ("делегирование вниз включено", CALM, "opus", {"TYPESAFE_TRIAGE_DELEGATE_DOWN": "on"}),
])
def test_economy_does_not_skip(monkeypatch, capsys, name, prompt, tier, extra):
    monkeypatch.setenv("TYPESAFE_TRIAGE_ECONOMY", "on")
    for k, v in extra.items():
        monkeypatch.setenv(k, v)
    fake_session(monkeypatch, tier)
    called = []
    monkeypatch.setattr(t, "triage", lambda *a, **k: called.append(1) or result("opus", action=act.decide(result("opus"), {}, {"tier": tier}, False)))
    hook(monkeypatch, capsys, prompt)
    assert called, name


def test_hook_logs_latency(monkeypatch, capsys):
    monkeypatch.setattr(t, "triage", lambda *a, **k: result("sonnet", action=act.decide(result("sonnet"), {}, {"tier": "sonnet"}, False)))
    hook(monkeypatch, capsys, CALM)
    rec = json.loads(t.LOG_PATH.read_text(encoding="utf-8").splitlines()[-1])
    assert isinstance(rec["ms"], int) and 0 <= rec["ms"] < 5000


# ---------- #40: отчёт ----------
def write_log(path, recs):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")


def make_report_fixture(tmp_path, n=24, with_agents=True):
    now = int(time.time())
    tag = eff.session_tag("sess-1")
    recs = []
    for i in range(n):
        recs.append({"ts": now - 3600 + i * 60, "model": "sonnet" if i % 4 else "opus", "effort": "high", "source": "typesafe", "tokens": 2500,
                     "session": tag, "action": "self", "action_why": "not_higher", "ms": 900 + i})
    recs += [{"ts": now - 100, "skipped": "короткая реплика (< 40 знаков)", "ms": 250}, {"ts": now - 90, "skipped": "команда /…"},
             {"ts": now - 80, "quiet": "решение прежнее (продолжение)", "ms": 200}]
    log = tmp_path / "log.jsonl"
    write_log(log, recs)
    proj = tmp_path / "projects" / "p1"
    proj.mkdir(parents=True)
    lines = []
    if with_agents:
        phrase = t.EFFORT_PROMPT["high"][0]
        for i, (model, prompt) in enumerate([("sonnet", "задача " + phrase), (None, "задача без фразы"), ("opus", "ещё задача"), (None, "ещё")]):
            inp = {"description": "x", "prompt": prompt}
            if model:
                inp["model"] = model
            lines.append({"type": "assistant", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - 1800 + i * 10)),
                          "message": {"content": [{"type": "tool_use", "name": "Agent", "input": inp}]}})
        lines.append({"type": "assistant", "isSidechain": True, "timestamp": "2027-01-15T10:00:00+00:00",
                      "message": {"content": [{"type": "tool_use", "name": "Agent", "input": {"prompt": "внутри агента"}}]}})
        (proj / "sess-1.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines), encoding="utf-8")
    return log, tmp_path / "projects", now


def test_report_counts_and_advice(tmp_path):
    log, projects, now = make_report_fixture(tmp_path)
    phrases = [p for pair in t.EFFORT_PROMPT.values() for p in pair]
    r = rep.build(7, log, projects, now=now, phrases=phrases, session_tag=eff.session_tag)
    assert r["decisions"] == 24 and r["quiet"] == 1 and r["skips"] == 2
    assert r["models"] == {"sonnet": 18, "opus": 6} and r["not_higher_share"] == 100.0
    assert r["tokens"] == 60000 and abs(r["usd"] - 60000 * 0.042 / 1e6) < 1e-9 and r["avg_tokens"] == 2500
    assert r["latency_ms"]["decision_median"] and r["latency_ms"]["skip_median"] in (200, 250)
    ag = r["agents"]
    assert ag["calls"] == 4 and ag["with_model"] == 2 and ag["no_model"] == 2 and ag["with_phrase"] == 1 and ag["files"] == 1   # вложенный агент не считается
    assert ag["same"] + ag["lower"] + ag["higher"] == 2
    text = "\n".join(r["advice"])
    assert "почти не влияет" in text and "DELEGATE_DOWN" in text and "ECONOMY" in text        # ≥ 90 % «сам: не выше»
    assert "без model" in text and "указывай model явно" in text                              # 50 % агентов без model
    out = rep.render(r)
    assert "Отчёт typesafe-triage" in out and "$0.0025" in out and "Выводы:" in out


def test_report_is_cautious_with_little_data(tmp_path):
    log, projects, now = make_report_fixture(tmp_path, n=5, with_agents=False)
    r = rep.build(7, log, projects, now=now, phrases=[], session_tag=eff.session_tag)
    assert r["advice"] and "Мало данных" in r["advice"][0]
    assert "Вызовы Agent: в стенограммах" in rep.render(r)


def test_report_reads_no_texts_into_output(tmp_path):
    log, projects, now = make_report_fixture(tmp_path)
    r = rep.build(7, log, projects, now=now, phrases=[t.EFFORT_PROMPT["high"][0]], session_tag=eff.session_tag)
    blob = json.dumps(r, ensure_ascii=False) + rep.render(r)
    assert "задача без фразы" not in blob and "ещё задача" not in blob


def test_report_cli(tmp_path):
    log, projects, now = make_report_fixture(tmp_path, n=3, with_agents=False)
    env = dict(os.environ, TYPESAFE_TRIAGE_HOME=str(tmp_path / "st"), TYPESAFE_TRIAGE_PROJECTS=str(projects))
    r = subprocess.run([sys.executable, "-B", str(SCRIPT), "--report", "--days", "5000", "--json"], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0 and "decisions" in json.loads(r.stdout)
    bad = subprocess.run([sys.executable, "-B", str(SCRIPT), "--report", "--days", "x"], capture_output=True, text=True, env=env, timeout=60)
    assert bad.returncode == 2


# ---------- #48: SHA256SUMS и --verify ----------
sys.path.insert(0, str(Path(__file__).parent / "shared"))
import skill_sums  # noqa: E402


def make_skill(tmp_path):
    d = tmp_path / "skill"
    (d / "scripts").mkdir(parents=True)
    (d / "SKILL.md").write_text("a\r\nb\r\n", encoding="utf-8", newline="")
    (d / "scripts" / "x.py").write_text("print(1)\n", encoding="utf-8")
    (d / "scripts" / "__pycache__").mkdir()
    (d / "scripts" / "__pycache__" / "x.pyc").write_bytes(b"\0\1")
    (d / "node_modules").mkdir()
    (d / "node_modules" / "m.js").write_text("x", encoding="utf-8")
    (d / "bin.dat").write_bytes(b"\0\r\n\0")
    return d


def test_sums_generate_verify_and_tamper(tmp_path):
    d = make_skill(tmp_path)
    assert skill_sums.collect(d) == ["SKILL.md", "bin.dat", "scripts/x.py"]            # кэш и node_modules исключены
    (d / "SHA256SUMS").write_text(skill_sums.generate(d), encoding="utf-8", newline="\n")
    assert skill_sums.verify(d)["ok"] and skill_sums.verify(d)["count"] == 3
    (d / "SKILL.md").write_text("a\nb\n", encoding="utf-8", newline="")                  # CRLF → LF (git на Windows): суммы те же
    assert skill_sums.verify(d)["ok"]
    (d / "bin.dat").write_bytes(b"\0\n\0")                                                # бинарный файл: перевод строк значим
    assert skill_sums.verify(d)["changed"] == ["bin.dat"]
    (d / "bin.dat").write_bytes(b"\0\r\n\0")
    (d / "scripts" / "x.py").write_text("print(2)\n", encoding="utf-8")
    (d / "new.py").write_text("x", encoding="utf-8")
    (d / "SKILL.md").unlink()
    r = skill_sums.verify(d)
    assert not r["ok"] and r["changed"] == ["scripts/x.py"] and r["missing"] == ["SKILL.md"] and r["extra"] == ["new.py"]
    assert skill_sums.main(["verify", str(d)]) == 1 and skill_sums.main(["verify", str(tmp_path)]) == 2


def test_installed_skill_matches_its_sums():
    """Файл SHA256SUMS в репозитории актуален (его пересчитывает tools/validate.sh --fix) и --verify это подтверждает."""
    if not (SKILL / "SHA256SUMS").exists():
        pytest.skip("SHA256SUMS создаётся при релизе")
    r = subprocess.run([sys.executable, "-B", str(SCRIPT), "--verify"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout
    assert "curl -fsSL https://raw.githubusercontent.com/OrionFLASH/claude-code-skills/typesafe-triage/v" in r.stdout


# ---------- изоляция тестов от настоящей среды (#43) ----------
def test_tests_do_not_see_real_home_or_api_key():
    assert "typesafe-tests-home-" in str(Path.home()) and os.environ.get("USERPROFILE") == os.environ.get("HOME")
    assert not os.environ.get("TYPESAFE_API_KEY")
    assert os.environ.get("PYTHONUTF8") == "1"


def test_subprocess_text_mode_decodes_utf8():
    r = subprocess.run([sys.executable, "-c", "print('пароль ✓')"], capture_output=True, text=True)
    assert r.stdout.strip() == "пароль ✓"
