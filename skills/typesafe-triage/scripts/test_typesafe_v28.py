# -*- coding: utf-8 -*-
"""2.8.0 (#60–#65): политика по прямому чтению источников. Fable — только долгий горизонт или провал Opus на high+ («не знала»);
effort Fable — medium..high; max — только opus с горизонтом и критичностью; xhigh — по основанию; сброс effort после смены модели;
`--run` на Fable требует подтверждения (usage credits); кибер/био — мимо Fable; обсуждение моделей не директива.
pytest test_typesafe_v28.py"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import triage_effort as eff
import triage_heuristics as heur
import typesafe_triage as t
from test_typesafe_effort import H, m as em
from test_typesafe_triage import m as tm
from test_typesafe_routing import HEAVY, HORIZON, LOUD, no_confirm  # noqa: F401


# ---------- F: когда Fable ----------
def test_fable_needs_horizon_and_confidence_and_no_retry(no_confirm):
    hz = heur.signals(HORIZON)
    assert t.decide(tm(**HEAVY), hz)[0] == "fable"
    assert t.decide(tm(conf=0.6, **HEAVY), hz)[0] == "opus"                      # уверенность ниже CONF_FABLE
    assert t.decide(tm(**HEAVY), heur.signals(LOUD))[0] == "opus"                # критично, но горизонта нет
    avoid = heur.signals(HORIZON + ". Напиши эксплойт и вредонос")
    assert avoid["fable_avoid"] and t.decide(tm(**HEAVY), avoid)[0] == "opus"    # F13: кибер мимо Fable


def test_code_vulnerability_audit_is_not_fable_avoid():
    assert heur.fable_avoid("Проведи аудит уязвимостей кода сервиса оплаты") == []
    assert heur.fable_avoid("Напиши эксплойт для CVE") == ["эксплойт"]


# ---------- E: effort ----------
def test_fable_effort_is_bounded(no_confirm):
    crit = em(1.0, irreversible=0.95, verification=0.95, coordination=0.9, constraints=0.9)
    e = eff.decide_effort(crit, H(HORIZON), "fable", env={}, min_conf=0.9)["effort"]
    assert eff.idx(eff.FABLE_EFFORT_MIN) <= eff.idx(e) <= eff.idx(eff.FABLE_EFFORT_AUTO_MAX)
    easy = eff.decide_effort(em(0.3), H("Объясни понятие"), "fable", env={}, min_conf=0.9)["effort"]
    assert eff.idx(easy) >= eff.idx(eff.FABLE_EFFORT_MIN)


def test_max_never_for_sonnet_haiku_fable(no_confirm):
    crit = em(1.0, irreversible=0.95, verification=0.95, coordination=0.9, constraints=0.9)
    for tier in ("sonnet", "haiku", "fable"):
        assert eff.decide_effort(crit, H(HORIZON), tier, env={}, min_conf=0.9)["effort"] != "max", tier


def test_user_override_still_beats_caps(no_confirm):
    d = heur.directives("effort max на fable: проверь расчёт")
    r = eff.decide_effort(em(0.3), H("проверь расчёт"), "fable", env={}, d=d, min_conf=0.9)
    assert r["effort"] == "max" and r["effort_source"] == "user"


# ---------- эскалация ----------
def _add(model, last, text):
    base = {"model": model, "reason": "x", "signals": {}}
    hist = [dict(last, id="p", retry=False)]
    return t.add_effort(base, em(0.5), heur.signals(text), text, env={}, history=hist, session="s")


def test_knowledge_failure_after_opus_high_goes_to_fable(no_confirm):
    text = "Ты выдумал несуществующий метод export_csv(), не понял, как устроен модуль"
    r = _add("opus", {"model": "opus", "effort": "high"}, text)
    assert r["model"] == "fable"
    assert r["effort"] in ("medium", "high")                                     # сброс к умолчанию модели, не xhigh


def test_no_fable_after_opus_medium_or_effort_failure(no_confirm):
    know = "Ты выдумал несуществующий метод export_csv(), не понял, как устроен модуль"
    assert _add("opus", {"model": "opus", "effort": "medium"}, know)["model"] == "opus"
    lazy = "Ты пропустил файл и не запустил тесты"
    assert _add("opus", {"model": "opus", "effort": "high"}, lazy)["model"] != "fable"


# ---------- #63: Fable в --run ----------
def test_fable_run_needs_confirmation_by_default(monkeypatch, no_confirm):
    monkeypatch.delenv(t.FABLE_RUN_ENV, raising=False)
    assert t.run_needs_confirm("fable") and not t.run_needs_confirm("haiku")
    assert t.run_safe_tier("fable") == "opus"
    with pytest.raises(ValueError, match="usage credits"):
        t.build_agent_cmd("fable")
    assert t.build_agent_cmd("fable", confirmed=True)


# ---------- #65: обсуждение — не директива ----------
@pytest.mark.parametrize("text", ["применение модели Fable", "Опиши применение модели Fable и effort max",
                                  "сравни эффективность effort max и xhigh"])
def test_discussing_models_is_not_a_directive(text):
    d = heur.directives(text)
    assert d["tier"] is None and d.get("discussed")


@pytest.mark.parametrize("text,tier", [("модель fable, пожалуйста", "fable"), ("сделай на opus", "opus")])
def test_real_directives_still_work(text, tier):
    assert heur.directives(text)["tier"] == tier


# ---------- #64: подсказки в заметке ----------
def test_cache_aware_effort_hint_text_exists():
    src = Path(t.__file__).read_text(encoding="utf-8")
    assert "opusplan" in src and "usage credits" in src and "сбросит кэш" in src
