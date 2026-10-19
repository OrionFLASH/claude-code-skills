# -*- coding: utf-8 -*-
"""Волна 2 (1.5.0): запросы пакетов к render_brief.py, check_paths.py, build_all.py, plan_baseline.py, summary_scaffold.py —
ворота FB-023 (<EN: …>), входы личного режима (SM 6.2), личные заголовки разделов, {PLAN_BASELINE}, подсказка
facts_scaffold --draft (FB-049), ворота выбора дизайна с командами mockup_kit (FB-007), пути брифа при {OUT} = «.»,
ворота полноты (owner_docs, idea.checks), шаги baseline/factcheck/kitverify/prototype, коды plan_baseline --check (D7),
архитектура из integration-options.json (G9), черновик резюме в build/summary-draft.md (G10).
Запуск: python3 -m pytest tests/test_wave2_gates.py -q -p no:cacheprovider
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import build_all  # noqa: E402
import render_brief  # noqa: E402

PY = [sys.executable, "-B"]


def env():
    return {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}


def run(script, *args):
    return subprocess.run(PY + [str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True, env=env(), timeout=600)


def write(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def demo_src(tmp_path_factory):
    out = tmp_path_factory.mktemp("w2") / "cdemo"
    r = run("make_concept_demo.py", out, "--proposals", "60")
    assert r.returncode == 0, r.stderr
    return out


@pytest.fixture()
def demo(demo_src, tmp_path):
    out = tmp_path / "cdemo"
    shutil.copytree(demo_src, out)
    cfg = jload(out / "build" / "run-config.json")
    cfg["repo"] = dict(cfg.get("repo") or {}, path=str(out))
    write(out / "build" / "run-config.json", cfg)
    return out


def set_cfg(out, **upd):
    cfg = jload(out / "build" / "run-config.json")
    for dotted, v in upd.items():
        cur = cfg
        keys = dotted.split("__")
        for k in keys[:-1]:
            cur = cur.setdefault(k, {})
        cur[keys[-1]] = v
    write(out / "build" / "run-config.json", cfg)
    return cfg


def not_demo(out):
    cfg = jload(out / "build" / "run-config.json")
    cfg["assumptions"] = [x for x in cfg.get("assumptions") or [] if "Демо" not in str(x)]
    write(out / "build" / "run-config.json", cfg)


# ---------------------------------------------------------------- render_brief
def test_fb023_gate_names_concept_dossier_topic_en(demo):
    """FB-023 (wp-a №1): брифы C4 не рендерятся, пока в плане поиска есть <EN: …>; сообщение называет concept_dossier --topic-en."""
    not_demo(demo)
    assert "<EN:" in (demo / "build" / "search-plan.md").read_text(encoding="utf-8")
    r = run("render_brief.py", "concept-analogs", "--out", demo, "--auto")
    assert r.returncode == 1 and not (demo / "build" / "briefs" / "concept-analogs.md").exists()
    assert "concept_dossier.py <OUT> --topic-en" in r.stdout and "<EN:" in r.stdout
    assert run("concept_dossier.py", demo, "--topic-en", "book swap between neighbours").returncode == 0
    assert "<EN:" not in (demo / "build" / "search-plan.md").read_text(encoding="utf-8")
    r = run("render_brief.py", "concept-analogs", "--out", demo, "--auto")
    assert r.returncode == 0, r.stdout + r.stderr


def test_keywords_from_confirmed_idea_keywords(demo):
    """FB-023 (wp-a №1, wp-d №5): {KEYWORDS} — из run-config idea.keywords в первую очередь."""
    set_cfg(demo, idea__keywords=["книгообмен", "соседи"], idea__keywords_source="owner")
    ctx = render_brief.Ctx(render_brief.template_path("concept-analogs"), demo, {})
    assert ctx.get("KEYWORDS") == "книгообмен, соседи"


def test_personal_mode_missing_inputs_and_titles(demo):
    """SM 6.2 / SM разд. 4 (wp-g №2, №3): в личном режиме запросы и события — «явно пропущено», заголовки разделов личные."""
    set_cfg(demo, project__audience="personal")
    tpl = demo / "build" / "tpl.md"
    write(tpl, "# Бриф\n\n## Входы\n- `{OUT}/data/keywords.json`, `{OUT}/research/events.md`\n- {MISSING_INPUTS}\n\nРазделы {SECTIONS}: {WORDS_MAX}\n")
    ctx = render_brief.Ctx(tpl, demo, {"SECTIONS": "8. Модель; 12. Метрики"})
    miss = ctx.get("MISSING_INPUTS")
    assert "явно пропущено: личный режим" in miss and "keywords.json" in miss and "events.md" in miss
    words = ctx.get("WORDS_MAX")
    assert "Стоимость владения и окупаемость личных усилий" in words and "Личные KPI и проверка на себе" in words
    set_cfg(demo, project__audience="public")
    ctx = render_brief.Ctx(tpl, demo, {"SECTIONS": "8. Модель"})
    assert "Модель дохода и экономика" in ctx.get("WORDS_MAX") and "личный режим" not in (ctx.get("MISSING_INPUTS") or "")


def test_plan_baseline_placeholder(demo):
    """FB-046 (wp-b №6): {PLAN_BASELINE} — сводка базовой линии или подсказка."""
    tpl = demo / "build" / "tpl.md"
    write(tpl, "# Бриф\n\nПлан: {PLAN_BASELINE}\n")
    assert "plan_baseline.py" in render_brief.Ctx(tpl, demo, {}).get("PLAN_BASELINE")
    assert run("plan_baseline.py", demo).returncode == 0
    v = render_brief.Ctx(tpl, demo, {}).get("PLAN_BASELINE")
    assert v and "нет data/plan-baseline.json" not in v


def test_strategy_section_without_decisions_hints_draft(demo):
    """FB-049 (wp-b №6): нет data/decisions.json — подсказка facts_scaffold.py --draft (предупреждение, бриф пишется)."""
    (demo / "data" / "decisions.json").unlink(missing_ok=True)
    r = run("render_brief.py", "strategy-section", "--out", demo, "--auto", "--group", "S1")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "facts_scaffold.py <OUT> --draft" in r.stderr
    assert "facts_scaffold.py <OUT> --draft" in (demo / "build" / "briefs" / "strategy-section-S1.md").read_text(encoding="utf-8")


def test_design_gate_message_names_mockup_kit(demo):
    """FB-007 (wp-f №4а): отказ шагов 2–3 называет mockup_kit.py directions / choose."""
    not_demo(demo)
    set_cfg(demo, autopilot=False, design={})
    r = run("render_brief.py", "concept-design", "--out", demo, "--auto", "--set", "STEPS=2-3", "--allow-untranslated")
    assert r.returncode == 1
    assert "mockup_kit.py directions <OUT>" in r.stdout and "mockup_kit.py choose <OUT> --direction <id> --by owner" in r.stdout


def test_kit_classes_not_truncated_at_60(demo):
    """wp-f №4б: {KIT_CLASSES} — все классы набора (ps-* и pm-*), включая компоненты 1.3."""
    ctx = render_brief.Ctx(render_brief.template_path("concept-design"), demo, {}, auto=True)
    v = render_brief.a_kit_classes(ctx) or ""
    assert "ps-concept-badge" in v and not v.endswith("…")
    kit = (Path(render_brief.SKILL) / "templates" / "mockup-kit" / "_kit.css").read_text(encoding="utf-8")
    for cls in ("ps-kbd", "ps-slider", "ps-stepper", "pm-actionbar"):
        if "." + cls in kit:
            assert cls in v, cls


# ---------------------------------------------------------------- check_paths
def test_check_paths_out_is_repo_root(demo):
    """wp-g №4: {OUT} = «.» (папка прогона — корень репозитория) → шаблоны без ведущего «/»."""
    not_demo(demo)
    r = run("render_brief.py", "research-ai", "--out", demo, "--auto", "--allow-untranslated")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "`./research/ai.md`" in (demo / "build" / "briefs" / "research-ai.md").read_text(encoding="utf-8")
    r = run("check_paths.py", demo, "--list-allowed", "--briefs", demo / "build" / "briefs" / "research-ai.md")
    allow = json.loads(r.stdout)["research-ai.md"]["allow"]
    assert "research/ai.md" in allow and not any(a.startswith("/") for a in allow), allow
    import check_paths
    assert check_paths.to_glob("./.gitignore", ".") == ".gitignore"
    assert check_paths.to_glob("{OUT}/data/x.json.", None) == "data/x.json"


# ---------------------------------------------------------------- build_all: ворота полноты и шаги
def ns(**kw):
    base = dict(accept_known=[], single=False, lite=False, zip=False, engines=None, strict=False, typesafe=False, track=False,
                shoot=False, links=False)
    base.update(kw)
    return argparse.Namespace(**base)


def test_completeness_owner_docs_and_start_decisions(tmp_path):
    """FB-002/FB-058 (wp-a №2): owner_docs со status not_attempted — «нет»; строки 1.4 — пропуск; idea.checks без решения —
    предупреждение start_decisions (не провал строгих ворот)."""
    out = tmp_path / "o"
    cfg = {"mode": "concept", "sources": {"owner_docs": ["https://old.example/doc"]},
           "idea": {"checks": [{"id": "mvp_capacity", "header": "Ёмкость MVP", "message": "не помещается", "options": [{"label": "a", "key": "single_feature"}]}]}}
    write(out / "build" / "run-config.json", cfg)
    rows = {r["code"]: r for r in build_all.completeness(out, cfg, [], ns())}
    assert rows["owner_materials"]["status"] == "н/п"                    # формат 1.4 (строки) — пропускается
    assert rows["start_decisions"]["status"] == "нет" and rows["start_decisions"]["warn_only"]
    assert "решение владельца до старта не получено" in rows["start_decisions"]["detail"]
    cfg["sources"]["owner_docs"] = [{"url": "https://claude.ai/a/1", "role": "base", "status": "not_attempted"},
                                    {"url": "https://x.example", "role": "ref", "status": "read"}]
    cfg["idea"]["decisions"] = {"mvp_capacity": "single_feature"}
    rows = {r["code"]: r for r in build_all.completeness(out, cfg, [], ns())}
    assert rows["owner_materials"]["status"] == "нет" and "claude.ai/a/1" in rows["owner_materials"]["detail"]
    assert "C0.6" in rows["owner_materials"]["todo"]
    assert rows["start_decisions"]["status"] == "да"


def test_build_all_plan_has_new_steps(demo):
    """wp-b №7, wp-c №4, wp-f №2, wp-g №5: шаги baseline (Гант без базовой линии), consistency с --strict, factcheck,
    kitverify (есть kit.lock), prototype (есть core.test.js)."""
    cfg = jload(demo / "build" / "run-config.json")
    steps = {s[0]: s for s in build_all.plan(demo, cfg, ns(strict=True))}
    assert steps["baseline"][1] is True                                  # gantt.json есть, plan-baseline.json нет
    assert "--strict" in steps["consistency"][3] and steps["consistency"][1]
    assert steps["factcheck"][1] is False and steps["kitverify"][1] is False and steps["prototype"][1] is False
    write(demo / "data" / "fact-check.json", [])
    write(demo / "build" / "kit.lock", {})
    write(demo / "prototype" / "js" / "core.test.js", "")
    steps = {s[0]: s for s in build_all.plan(demo, cfg, ns())}
    assert steps["factcheck"][1] and steps["factcheck"][3][-1] == "--check"
    assert steps["kitverify"][1] and steps["kitverify"][3][-2:] == ["verify", str(demo)]
    assert "--strict" not in steps["consistency"][3]
    order = [s[0] for s in build_all.plan(demo, cfg, ns())]
    assert order.index("baseline") < order.index("assemble") < order.index("consistency") < order.index("factcheck")
    assert order.index("mockups") < order.index("kitverify")
    assert {"factcheck", "kitverify", "prototype"} <= build_all.WARN_STEPS


def test_baseline_stale(tmp_path):
    out = tmp_path / "o"
    assert not build_all.baseline_stale(out)
    write(out / "data" / "gantt.json", [])
    assert build_all.baseline_stale(out)
    write(out / "data" / "plan-baseline.json", {})
    os.utime(out / "data" / "gantt.json", (1, 1))
    assert not build_all.baseline_stale(out)
    os.utime(out / "data" / "plan-baseline.json", (0, 0))
    assert build_all.baseline_stale(out)


@pytest.mark.skipif(not shutil.which("node"), reason="нет node")
def test_check_prototype(tmp_path):
    """SM 7 (wp-g №5): тесты ядра, оболочки и канона; провал — код 1 со строкой «не прошло»."""
    out = tmp_path / "o"
    write(out / "prototype" / "js" / "core.test.js", "console.log('ok')\n")
    write(out / "prototype" / "js" / "kit.test.js", "process.exit(3)\n")
    code, line = build_all.check_prototype(out)
    assert code == 1 and "оболочка (код 3" in line and "прошло — ядро" in line
    write(out / "prototype" / "js" / "kit.test.js", "console.log('ok')\n")
    write(out / "prototype" / "tools" / "check_canon.py", "import sys; sys.exit(0)\n")
    code, line = build_all.check_prototype(out)
    assert code == 0 and "ядро, оболочка, канон" in line


def test_factcheck_step_warns_and_fails_strict(demo):
    """FB-052 (wp-c №4): неприменённая подтверждённая запись fact-check — WARN, в --strict (не демо) — FAIL."""
    not_demo(demo)
    write(demo / "data" / "fact-check.json", [{"fact": "цена", "resolved_value": "990", "fix": None}])
    r = run("build_all.py", demo, "--only", "factcheck")
    assert "factcheck" in r.stdout and "WARN" in r.stdout
    r = run("build_all.py", demo, "--only", "factcheck", "--strict")
    assert r.returncode == 1 and "FAIL" in r.stdout


# ---------------------------------------------------------------- plan_baseline, summary_scaffold
def test_plan_baseline_check_codes_and_integration_options(demo):
    """D7: --check — код 0 без расхождений; G9: architecture — рекомендованный вариант integration-options.json и сроки MVP."""
    write(demo / "data" / "integration-options.json", {
        "recommended": "B", "platform_risks": ["смена условий API"],
        "options": [{"id": "A", "title": "Скрапинг", "effort_days": [2, 4], "value": 5, "risks": ["запрет"]},
                    {"id": "B", "title": "Официальный API", "effort_days": [5, 9], "value": 3, "risks": [], "mvp": True},
                    {"id": "C", "title": "Экспорт вручную", "effort_days": [1, 2], "value": 2, "mvp": True, "queue": "alpha"}]})
    assert run("plan_baseline.py", demo).returncode == 0
    arch = jload(demo / "data" / "plan-baseline.json")["architecture"]
    assert arch["id"] == "B" and arch["name"] == "Официальный API" and arch["why"].startswith("chosen/recommended")
    assert arch["mvp_options"] == ["B", "C"] and arch["mvp_days"] == [6.0, 11.0] and arch["platform_risks"] == ["смена условий API"]
    for f in (demo / "build" / "parts").glob("strategy-*.md") if (demo / "build" / "parts").is_dir() else []:
        f.unlink()
    r = run("plan_baseline.py", demo, "--check")
    rep = jload(demo / "build" / "consistency-report.json")
    assert r.returncode == (1 if rep["issues"] else 0)
    assert r.stdout.strip().splitlines()[-1].startswith("итог: расхождений с plan-baseline")


def test_summary_scaffold_default_draft_path(demo):
    """G10: черновик резюме — build/summary-draft.md (не в build/parts/)."""
    r = run("summary_scaffold.py", demo)
    assert r.returncode == 0, r.stderr
    assert (demo / "build" / "summary-draft.md").exists()
    assert not (demo / "build" / "strategy-summary.md").exists()
    assert not (demo / "build" / "parts" / "strategy-01.md").exists() or "summary_scaffold" not in (
        demo / "build" / "parts" / "strategy-01.md").read_text(encoding="utf-8")
