# -*- coding: utf-8 -*-
"""2.9.0: квоты на автоматические fable и effort max, потолок расхода --run, «уйдут на Fable» — не указание.
pytest test_typesafe_extremes.py"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import triage_extremes as xt
import triage_heuristics as heur
import typesafe_guard as guard
import typesafe_triage as t


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "HOME", tmp_path)
    for k in (*xt.ENV.values(), xt.BUDGET_ENV):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(t, "skill_config", lambda: {})
    return tmp_path


def res(model="fable", effort="high", msrc="auto", esrc="typesafe"):
    return {"model": model, "effort": effort, "model_source": msrc, "effort_source": esrc, "reason": "r",
            "confirm": False, "fallback": model, "effort_confirm": False, "effort_fallback": effort, "effort_reasons": []}


def test_parse_limit():
    assert xt.parse_limit("1/3", None) == (1, 3)
    assert xt.parse_limit("2", None) == (2, 14)
    assert xt.parse_limit("0", None) == (0, 0)
    assert xt.parse_limit("off", (1, 3)) is None
    assert xt.parse_limit("мусор", (1, 3)) == (1, 3)
    assert xt.parse_limit("5/2", None) == (5, 5)        # неделя не меньше суток


def test_defaults_are_tight():
    assert xt.DEFAULTS == {"fable": (1, 3), "max": (2, 6)}


def test_first_auto_fable_allowed_second_downgraded(home):
    r1 = res()
    t.apply_extremes(r1, "задача один", "s", "commit")
    assert r1["model"] == "fable" and r1["extremes_used"] == ["fable"]
    r2 = res()
    t.apply_extremes(r2, "задача два", "s", "commit")
    assert r2["model"] == "opus" and "fable" in r2["extremes"] and not r2["confirm"] and r2["fallback"] == "opus"
    assert "квота fable за сутки исчерпана" in r2["reason"]


def test_same_prompt_twice_spends_once(home):
    for _ in range(3):
        r = res()
        t.apply_extremes(r, "тот же запрос", "s", "commit")
        assert r["model"] == "fable"
    assert len(xt.load(home)) == 1


def test_check_mode_does_not_spend(home):
    for i in range(3):
        r = res()
        t.apply_extremes(r, "запрос %d" % i, "s", "check")
        assert r["model"] == "fable"
    assert xt.load(home) == []


def test_off_mode_untouched(home):
    r = res()
    t.apply_extremes(r, "x", "s", None)
    assert r["model"] == "fable" and "extremes_used" not in r


def test_explicit_user_choice_never_blocked_and_not_counted(home, monkeypatch):
    monkeypatch.setenv(xt.ENV["fable"], "0")
    r = res(msrc="user")
    t.apply_extremes(r, "на fable сделай", "s", "commit")
    assert r["model"] == "fable" and "extremes" not in r
    assert xt.usage(xt.load(home), "fable", time.time()) == (0, 0)            # в квоту не входит
    assert xt.usage(xt.load(home), "fable", time.time(), auto_only=False) == (1, 1)   # но в журнале есть


def test_zero_quota_means_never_auto(home, monkeypatch):
    monkeypatch.setenv(xt.ENV["fable"], "0")
    r = res()
    t.apply_extremes(r, "x", "s", "commit")
    assert r["model"] == "opus" and "квота 0" in r["reason"]


def test_off_means_unlimited(home, monkeypatch):
    monkeypatch.setenv(xt.ENV["fable"], "off")
    for i in range(5):
        r = res()
        t.apply_extremes(r, "q%d" % i, "s", "commit")
        assert r["model"] == "fable"


def test_max_effort_downgrades_to_xhigh_after_quota(home):
    outs = []
    for i in range(3):
        r = res(model="opus", effort="max")
        t.apply_extremes(r, "задача %d" % i, "s", "commit")
        outs.append(r["effort"])
    assert outs == ["max", "max", "xhigh"]


def test_explicit_effort_max_not_blocked(home, monkeypatch):
    monkeypatch.setenv(xt.ENV["max"], "0")
    r = res(model="sonnet", effort="max", esrc="user")
    t.apply_extremes(r, "effort max: опечатка", "s", "commit")
    assert r["effort"] == "max" and "extremes" not in r


def test_window_expires(home):
    old = time.time() - 2 * xt.DAY_S
    xt.save(home, [{"ts": int(old), "kind": "fable", "src": "auto", "id": "a", "session": "s"}])
    ok, why, _ = xt.decide(xt.load(home), "fable", time.time())
    assert ok and why is None                          # сутки прошли; неделя 1 из 3


def test_week_quota(home):
    now = time.time()
    xt.save(home, [{"ts": int(now - (i + 1.5) * xt.DAY_S), "kind": "fable", "src": "auto", "id": str(i), "session": "s"} for i in range(3)])
    ok, why, _ = xt.decide(xt.load(home), "fable", now)
    assert not ok and "за неделю" in why


def test_broken_state_file_is_ignored(home):
    (home / "extremes.json").write_text("{не json", encoding="utf-8")
    assert xt.load(home) == []
    r = res()
    t.apply_extremes(r, "x", "s", "commit")
    assert r["model"] == "fable"


def test_run_gets_default_budget_for_extremes(home):
    cmd = t.build_agent_cmd("fable", confirmed=True)
    assert cmd[cmd.index("--max-budget-usd") + 1] == "10.0"
    cmd = t.build_agent_cmd("opus", effort="max", confirmed_effort=True)
    assert "--max-budget-usd" in cmd
    assert "--max-budget-usd" not in t.build_agent_cmd("opus", effort="high")
    cmd = t.build_agent_cmd("fable", budget="3", confirmed=True)
    assert cmd[cmd.index("--max-budget-usd") + 1] == "3"


def test_note_has_stage_limiter_and_quota_line(home):
    r = res()
    r.update(model="fable", effort="high")
    t.apply_extremes(r, "q1", "s", "commit")
    r2 = res()
    t.apply_extremes(r2, "q2", "s", "commit")
    for result, expect in ((r, "Крайний случай — расход не безграничен"), (r2, "Квота крайних случаев исчерпана")):
        result.setdefault("action", {"kind": "self", "reason": "x", "hints": []})
        assert expect in t.hook_context(result)


def test_concern_about_fable_is_not_a_directive():
    text = "Есть опасения, что очень долгие задачи уйдут на Fable и сожгут токены; продумай, как выбирать Fable только в крайних случаях"
    assert heur.directives(text)["tier"] is None
    assert heur.directives("Сделай на Fable рефакторинг модуля")["tier"] == "fable"
    assert heur.directives("use fable for this")["tier"] == "fable"


def test_extremes_command_prints_quotas(home, capsys):
    xt_lines = xt.summary(home, {})
    assert any("fable" in l and "1/сутки, 3/неделя" in l for l in xt_lines) and any("$10.00" in l for l in xt_lines)
