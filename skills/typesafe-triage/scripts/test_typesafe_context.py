# -*- coding: utf-8 -*-
"""2.2.0: путь скрипта и проверка хуков (T-5), контекст активной задачи и наследование оценки (T-1), тип qa (T-2),
общее интерактивное состояние (T-3), правило effort в SKILL.md (T-6). Офлайн. pytest test_typesafe_context.py"""
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import triage_effort as eff
import triage_heuristics as heur
import typesafe_triage as t

SKILL = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(t.guard, "HOME", tmp_path / "guard")
    for k in ("TYPESAFE_TRIAGE", "TYPESAFE_API_KEY", t.CHILD_ENV, t.CONTEXT_ENV):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(eff, "session_effort", lambda cwd=None: None)


def resp(level=0.2, choice="software", **flags):
    a = {k: {"score": level * (len(t.SCORES[k]["criteria"]) - 1), "confidence": 0.9} for k in t.SCORES}
    for k, spec in t.EFFORT_SCORES.items():
        a[k] = {"score": level * (len(spec["criteria"]) - 1), "confidence": 0.9}
    for k in list(t.FLAGS) + list(t.EFFORT_FLAGS):
        a[k] = {"noul": flags.get(k, 0.05)}
    a["domain"] = {"choice": choice, "confidence": 0.8}
    return {"answers": a, "usage": {"input_tokens": 50}}


def hook(monkeypatch, capsys, payload):
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps(payload)))
    assert t.run_hook() == 0
    out = capsys.readouterr().out
    return json.loads(out) if out.strip() else {}


def ctx(out):
    return out.get("hookSpecificOutput", {}).get("additionalContext", "")


def project(tmp_path, tasks=None, profile=False, cdp=False):
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    if tasks is not None:
        (root / "TASKS.md").write_text(tasks, encoding="utf-8")
    if profile:
        (root / ".profile" / "Default").mkdir(parents=True)
        if cdp:
            (root / ".profile" / "DevToolsActivePort").write_text("9222\n/devtools/browser/x")
    return root


# ---------- T-5: --where и фактический путь ----------
def test_where_prints_real_script_path_first(tmp_path):
    r = subprocess.run([sys.executable, "-B", str(SKILL / "scripts" / "typesafe_triage.py"), "--where"], capture_output=True,
                       text=True, env=dict(os.environ, HOME=str(tmp_path), TYPESAFE_TRIAGE_HOME=str(tmp_path / "st")), timeout=30)
    first = r.stdout.splitlines()[0]
    assert r.returncode == 0 and os.path.isfile(first) and first.endswith("typesafe_triage.py")
    assert "# каталог скриптов: " + os.path.dirname(first) in r.stdout
    assert "хук не найден" in r.stdout                                   # пустой домашний каталог — честное предупреждение


def test_where_detects_stale_manual_hook_and_duplicate(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    settings = {"env": {"TYPESAFE_API_KEY": "sk-" "secretsecretsecret"},
                "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "timeout": 10,
                          "command": "python3 \"$HOME/.claude/skills/typesafe-triage/scripts/typesafe_triage.py\" --hook"}]}]},
                "enabledPlugins": {"typesafe-triage@claude-code-skills": True}}
    (home / ".claude" / "settings.json").write_text(json.dumps(settings))
    (home / ".claude" / "plugins" / "cache" / "claude-code-skills" / "typesafe-triage" / "2.2.0").mkdir(parents=True)
    rep = t.where_report(home=str(home), cwd=str(tmp_path))
    assert "ФАЙЛА НЕТ" in rep and "несуществующий файл" in rep and "код 2" in rep
    assert "включён (typesafe-triage@claude-code-skills)" in rep and "версии в кэше плагинов: 2.2.0" in rep
    assert "и в settings.json, и в плагине" in rep and "/reload-plugins" in rep
    assert "secretsecret" not in rep                                      # из настроек выводятся только хуки


def test_where_accepts_existing_manual_hook(tmp_path):
    home = tmp_path / "home"
    script = home / ".claude" / "skills" / "typesafe-triage" / "scripts" / "typesafe_triage.py"
    script.parent.mkdir(parents=True)
    script.write_text("")
    hooks = {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": 'python3 "%s" --hook' % script}]}]}}
    (home / ".claude" / "settings.json").write_text(json.dumps(hooks))
    rep = t.where_report(home=str(home), cwd=str(tmp_path))
    assert "файл есть" in rep and "ВНИМАНИЕ" not in rep


def test_where_understands_guarded_manual_hook_from_install_md(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    cmd = ('f="$HOME/.claude/skills/typesafe-triage/scripts/typesafe_triage.py"; if [ -f "$f" ]; then python3 "$f" --hook; '
           'else echo \'{"systemMessage":"TypeSafe-триаж пропущен: скрипт хука не найден, проверьте установку (--where)"}\'; fi')
    (home / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [{"command": cmd}]}]}}))
    entries = t.hook_entries([home / ".claude" / "settings.json"], str(home))
    assert entries and Path(entries[0][2]) == home / ".claude" / "skills" / "typesafe-triage" / "scripts" / "typesafe_triage.py"
    assert entries[0][3] is False


def test_guard_hints_use_real_path_not_fixed_skills_dir():
    p = t.guard.SCRIPT.strip('"').replace("$HOME", os.path.expanduser("~"))
    assert os.path.isfile(p) and Path(p).resolve() == (SKILL / "scripts" / "typesafe_triage.py").resolve()


# ---------- T-1: активная задача и наследование ----------
@pytest.mark.parametrize("text,yes", [
    ("про доступ выдан, продолжай тесты, в т. ч. по Pro", True),
    ("и ещё добавь в отчёт раздел про иконки и подписи кнопок", True),
    ("continue with the remaining checks on the pricing page", True),
    ("Не забудь разместить скрины в issues, если для этого потребуется", False),
    ("Напиши письмо партнёрам о переносе сроков поставки на две недели", False),
    ("продолжай " + "очень длинное описание новой задачи " * 20, False),
])
def test_continuation_detection(text, yes):
    assert heur.is_continuation(text) is yes


def test_active_task_line_from_tasks_md(tmp_path):
    root = project(tmp_path, "# План\n- [x] сделано\n- [ ] Прогон site-qa-audit по разделу Pro: вход, оплата, скриншоты\n")
    sub = root / "a" / "b"
    sub.mkdir(parents=True)
    assert eff.active_task(str(sub)).startswith("Прогон site-qa-audit по разделу Pro")
    stopped = project(tmp_path / "2", "## Где остановился\nДописать тесты хука\n")
    assert eff.active_task(str(stopped)) == "Дописать тесты хука"
    assert eff.active_task(str(project(tmp_path / "3"))) is None


def test_digest_adds_active_task_only_for_continuation(tmp_path, monkeypatch):
    root = project(tmp_path, "- [ ] Проверка формы оплаты, token=" "abcdef1234567890abcdef\n")
    cont = "продолжай проверку по второму сценарию, пожалуйста"
    sent, used = t.request_digest(cont, str(root))
    assert used and sent.startswith(cont) and t.CONTEXT_HEAD in sent and "Проверка формы оплаты" in sent
    assert "abcdef1234567890abcdef" not in sent                           # секреты скрыты и в строке контекста
    assert t.request_digest("Напиши письмо партнёрам о переносе сроков поставки", str(root)) == (
        "Напиши письмо партнёрам о переносе сроков поставки", False)
    assert t.request_digest(cont, None)[1] is False                       # без каталога — без контекста
    monkeypatch.setenv(t.CONTEXT_ENV, "off")
    assert t.request_digest(cont, str(root))[1] is False


def test_typesafe_receives_active_task_and_log_marks_it(tmp_path, monkeypatch):
    root = project(tmp_path, "- [ ] Прогон тестов раздела Pro\n")
    seen = []
    monkeypatch.setattr(t, "ask_typesafe", lambda task, key, timeout=0: seen.append(task) or resp(0.5))
    r = t.triage("продолжай тесты по разделу Pro, доступ выдан", key="k", cwd=str(root), history=[])
    assert r["active_task"] and "Прогон тестов раздела Pro" in seen[0]
    t.log("продолжай тесты по разделу Pro, доступ выдан", r)
    rec = json.loads(t.LOG_PATH.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["active_task"] is True and "Прогон тестов" not in json.dumps(rec, ensure_ascii=False)


def prev_rec(model="opus", effort="high"):
    return [{"ts": int(time.time()) - 60, "session": "s", "id": "x", "model": model, "effort": effort, "retry": False}]


def test_short_continuation_inherits_previous_assessment(monkeypatch):
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp(0.15))
    task = "про доступ выдан, продолжай тесты, в т. ч. по Pro"
    r = t.triage(task, key="k", env={}, history=prev_rec())
    assert r["model"] == "opus" and r["effort"] == "high" and r["inherited"] == {"model": "opus", "effort": "high"}
    assert "продолжение предыдущей задачи" in r["reason"] and r["effort_confidence"] == "унаследована"
    assert not r["clarify"]
    plain = t.triage("Напиши письмо партнёрам о переносе сроков поставки", key="k", env={}, history=prev_rec())
    assert "inherited" not in plain and "продолжение" not in plain["reason"]


def test_inheritance_is_capped_and_respects_user(monkeypatch):
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp(0.15))
    r = t.triage("продолжай тесты по второму сценарию", key="k", env={}, history=prev_rec("fable", "max"))
    assert r["model"] == "opus" and r["effort"] == "xhigh" and not r["confirm"] and not r["effort_confirm"]
    u = t.triage("продолжай тесты по второму сценарию на sonnet, кратко", key="k", env={}, history=prev_rec())
    assert u["model"] == "sonnet" and u["model_source"] == "user"


def test_hook_continuation_inherits_from_session_log(monkeypatch, capsys):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp(0.8, irreversible=0.9))
    big = {"prompt": "Проведи полный прогон QA сайта: все разделы, вход, оплата, мобильная версия, отчёт и issues", "session_id": "S"}
    first = ctx(hook(monkeypatch, capsys, big))
    assert "[TypeSafe-триаж: opus/" in first
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp(0.1))
    # 2.3 (#27, «реже»): продолжение наследует оценку и действие — решение прежнее, заметку не повторяем
    second = hook(monkeypatch, capsys, {"prompt": "про доступ выдан, продолжай тесты, в т. ч. по Pro", "session_id": "S"})
    assert second == {}
    rec = json.loads(t.LOG_PATH.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["quiet"] == t.QUIET_REASON and rec["model"] == "opus" and rec["inherited"]["model"] == "opus"
    assert "task" not in rec and "Pro" not in json.dumps(rec, ensure_ascii=False)


# ---------- T-2: тип qa ----------
def test_domain_has_qa_type_and_note_shows_it(monkeypatch, capsys):
    assert "qa" in t.CHOICES["domain"]["criteria"] and "testing" not in t.CHOICES["domain"]["criteria"]["software"].split(",")[0]
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp(0.5, choice="qa"))
    c = ctx(hook(monkeypatch, capsys, {"prompt": "Проверь сайт на ошибки в мобильной версии и заведи issues со скриншотами"}))
    assert "; тип qa" in c.split("\n")[0]


# ---------- T-3: общее интерактивное состояние ----------
def test_shared_state_env_signals(tmp_path):
    assert eff.shared_state_env(str(project(tmp_path / "plain", "- [ ] написать README\n"))) == []
    assert eff.shared_state_env(str(project(tmp_path / "p", profile=True))) == ["профиль браузера .profile/"]
    assert eff.shared_state_env(str(project(tmp_path / "c", profile=True, cdp=True))) == ["браузер с отладкой (CDP) в .profile/"]
    run = project(tmp_path / "r", "- [x] старт\n- [ ] Прогон раздела Pro в браузере пользователя\n")
    assert eff.shared_state_env(str(run)) == ["активный прогон в TASKS.md"]


def test_shared_state_text_signals():
    assert heur.shared_state_text("Проверь это в моём браузере, я уже вошёл под своим аккаунтом")
    assert heur.shared_state_text("connect to my browser via CDP on port 9222")
    assert heur.shared_state_text("Напиши письмо партнёрам о переносе сроков поставки") == []


def test_note_says_delegate_only_independent_parts(tmp_path, monkeypatch, capsys):
    root = project(tmp_path, "- [ ] Прогон раздела Pro в браузере пользователя\n", profile=True, cdp=True)
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(t, "ask_typesafe", lambda *a, **k: resp(0.8, irreversible=0.9))
    out = hook(monkeypatch, capsys, {"prompt": "Найди мелкие недочёты на всех страницах и доведи список до 100 issues",
                                     "cwd": str(root), "session_id": "S3"})
    c = ctx(out)
    assert "Общее интерактивное состояние (браузер с отладкой (CDP) в .profile/; активный прогон в TASKS.md)" in c
    assert "делегируй только независимые части" in c and c.startswith("ДЕЙСТВИЕ: сам — общее устройство или сессия")
    rec = json.loads(t.LOG_PATH.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["shared_state"]
    plain = ctx(hook(monkeypatch, capsys, {"prompt": "Найди мелкие недочёты на всех страницах и доведи список до 100 issues",
                                           "cwd": str(project(tmp_path / "x")), "session_id": "S4"}))
    assert "Общее интерактивное состояние" not in plain
