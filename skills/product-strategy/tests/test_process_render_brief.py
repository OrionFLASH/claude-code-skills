# -*- coding: utf-8 -*-
"""WP-D 1.5.0: render_brief.py — --auto для всех брифов (FB-050), условные строки по номеру раздела и входы без «файла нет»
(SM 6.2), ворота `<EN: …>` (FB-023) и выбора дизайна (FB-007), {CAPACITY} (FB-028), выводы пересмотра идеи в контексте
(FB-044), блок общих правил: build/tmp/<бриф>/, браузер владельца, «Отступления от брифа» (FB-004, FB-006, FB-043), проверка
decisions.json для авторов (FB-049), список владельца из owner_docs (FB-002). Без сети.
Запуск: python3 -m pytest tests/test_process_render_brief.py -q -p no:cacheprovider
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
TEMPLATES = SKILL / "templates" / "briefs"
PH = re.compile(r"\{[A-Z][A-Z0-9_]*\}")


def run(script, *args):
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True, env=e, timeout=300)


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def jdump(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def brief(out, name):
    return (out / "build" / "briefs" / name).read_text(encoding="utf-8")


def body(text):
    return "\n".join(line for line in text.splitlines() if not line.startswith("Плейсхолдеры:"))


@pytest.fixture(scope="module")
def concept(tmp_path_factory):
    out = tmp_path_factory.mktemp("rbp") / "c"
    assert run("make_concept_demo.py", out, "--proposals", "60").returncode == 0
    assert run("score.py", out).returncode == 0
    return out


def real(out):
    """Не демо: без пометки «Демо» в допущениях и без автопилота."""
    cfg = jload(out / "build" / "run-config.json")
    cfg["assumptions"] = [a for a in cfg.get("assumptions") or [] if "Демо" not in a]
    cfg["autopilot"] = False
    jdump(out / "build" / "run-config.json", cfg)
    return cfg


# ---------------------------------------------------------------- FB-050: все брифы с --auto, не больше одного --set
def test_all_briefs_render_with_auto(concept):
    names = sorted(f.stem for f in TEMPLATES.glob("*.md") if not f.stem.startswith("_"))
    assert len(names) >= 19
    failed = {}
    for n in names:
        r = run("render_brief.py", n, "--out", concept, "--auto", "--allow-untranslated")
        if r.returncode != 0:
            failed[n] = r.stdout[-300:]
            continue
        dest = next((concept / "build" / "briefs").glob(n + "*.md"))
        rest = body(dest.read_text(encoding="utf-8"))
        assert not PH.findall(rest), (n, PH.findall(rest))
        assert str(Path.home()) not in rest
    assert not failed, failed


def test_auto_strategy_parts_registry_and_mockups(concept):
    r = run("render_brief.py", "strategy-section", "--out", concept, "--auto", "--parts", "4", "--group", "S2")
    assert r.returncode == 0 and "Подставлено автоматически: SECTIONS, OTHER_PARTS" in r.stdout
    t = brief(concept, "strategy-section-S2.md")
    assert "> Подставлено автоматически (render_brief --auto): SECTIONS, OTHER_PARTS." in t
    assert "раздел 1 (резюме) — оркестратор" in t and "— часть S1" in t and "— часть S2" not in t
    r = run("render_brief.py", "registry-generator", "--out", concept, "--auto", "--group", "G2")
    assert r.returncode == 0
    t = brief(concept, "registry-generator-G2.md")
    assert re.search(r"[a-z_]+ — \d+", t) and "проход titles" in t                             # standard, черновиков ещё нет
    cfg = jload(concept / "build" / "run-config.json")
    cfg["registry"] = {"passes": 1}
    jdump(concept / "build" / "run-config.json", cfg)
    try:
        r = run("render_brief.py", "registry-generator", "--out", concept, "--auto", "--group", "G2")
        t = brief(concept, "registry-generator-G2.md")
        assert r.returncode == 0 and "проход details" in t and "темы группы G1:" in t       # FB-005: один проход, темы других групп
    finally:
        cfg.pop("registry")
        jdump(concept / "build" / "run-config.json", cfg)
    r = run("render_brief.py", "concept-design", "--out", concept, "--auto")
    t = brief(concept, "concept-design.md")
    assert r.returncode == 0 and re.search(r"M0\d", t) and "1440x900" in t or "390x844" in t


# ---------------------------------------------------------------- SM 6.2: условные строки и входы, которых нет
def test_conditions_by_exact_section_number(concept):
    r = run("render_brief.py", "strategy-section", "--out", concept, "--set", "SECTIONS=2. Идея; 3. Рынок; 4. Сообщества; 5. Ценность",
            "--set", "OTHER_PARTS=остальные", "--suffix", "p1")
    t = body(brief(concept, "strategy-section-p1.md"))
    assert r.returncode == 0 and "Если писал" not in t and "Если в {SECTIONS}" not in t and "Если в 2." not in t
    r = run("render_brief.py", "strategy-section", "--out", concept, "--set", "SECTIONS=13. Риски; 14. План действий", "--set", "OTHER_PARTS=остальные",
            "--suffix", "p2")
    t = body(brief(concept, "strategy-section-p2.md"))
    assert "Если писал" in t and "Если в 13." not in t                                       # раздел 14 есть — пункт проверки JSON остаётся
    r = run("render_brief.py", "strategy-section", "--out", concept, "--set", "SECTIONS=14. План действий", "--set", "OTHER_PARTS=—",
            "--set", "CHART_KEYS=funnel, matrix", "--suffix", "p4")
    assert "gantt (после записи data/gantt.json" in brief(concept, "strategy-section-p4.md")    # ключ плана — в списке графиков


def test_missing_inputs_marked_and_listed(concept):
    r = run("render_brief.py", "strategy-section", "--out", concept, "--set", "SECTIONS=6. Запуск", "--set", "OTHER_PARTS=—", "--suffix", "p3")
    t = brief(concept, "strategy-section-p3.md")
    assert r.returncode == 0
    assert "не искать и не писать в отчёте «файла нет»" in t
    assert "*(нет в этом прогоне — не искать)*" in t
    assert "data/decisions.json — решений ещё нет" in t                                       # FB-049


# ---------------------------------------------------------------- FB-023 и FB-007: ворота
def test_en_gate_and_design_gate(tmp_path):
    out = tmp_path / "c"
    assert run("make_concept_demo.py", out, "--proposals", "50").returncode == 0
    real(out)
    r = run("render_brief.py", "concept-analogs", "--out", out)
    assert r.returncode == 1 and "непереведённых английских запросов" in r.stdout and not (out / "build" / "briefs" / "concept-analogs.md").exists()
    assert run("render_brief.py", "concept-analogs", "--out", out, "--allow-untranslated").returncode == 0
    sp = out / "build" / "search-plan.md"
    sp.write_text(re.sub(r"<EN: [^>]*>", "book swap", sp.read_text(encoding="utf-8")), encoding="utf-8")
    assert run("render_brief.py", "research-communities", "--out", out).returncode == 0       # переведено — бриф пишется
    r = run("render_brief.py", "concept-design", "--out", out, "--set", "STEPS=2-3", "--set", "KEYS=M01", "--set", "VIEWPORTS=все")
    assert r.returncode == 1 and "без выбора владельца" in r.stdout
    r = run("render_brief.py", "concept-design", "--out", out, "--auto")
    assert r.returncode == 0 and "**Какие шаги выполнять:** 1; выбранное направление: нет" in brief(out, "concept-design.md")
    cfg = jload(out / "build" / "run-config.json")
    cfg["design"] = {"chosen": "B «Глина и бумага»", "chosen_by": "owner"}
    jdump(out / "build" / "run-config.json", cfg)
    r = run("render_brief.py", "concept-design", "--out", out, "--auto")
    t = brief(out, "concept-design.md")
    assert r.returncode == 0 and "**Какие шаги выполнять:** 2-3; выбранное направление: B «Глина и бумага» (выбрал владелец)" in t


# ---------------------------------------------------------------- FB-028, FB-044, FB-002: контекст
def test_capacity_premises_and_owner_list_in_context(tmp_path):
    out = tmp_path / "c"
    assert run("make_concept_demo.py", out, "--proposals", "50").returncode == 0
    cfg = jload(out / "build" / "run-config.json")
    cfg["project"]["capacity"] = {"hours_per_week": 15, "dev_share": 0.7, "day_hours": 8, "source": "ответ c32"}
    cfg["sources"]["owner_docs"] = [{"url": "https://metaforge.app", "role": "competitor"}]
    jdump(out / "build" / "run-config.json", cfg)
    jdump(out / "data" / "premises.json", {"premises": [{"id": "PR1", "text": "синк со Steam — новая возможность", "status": "refuted",
                                                         "source": "research/integration.md:40"}], "decision": "narrow", "pitch_v2": "личный план фарма"})
    tpl = tmp_path / "cap.md"
    tpl.write_text("# Бриф {PRODUCT}\n\n## Цель\nЁмкость: {CAPACITY}\n\n## Входы\n- {OUT}/data/idea.json\n\n## Выдача\n- `{OUT}/research/x.md`\n",
                   encoding="utf-8")
    r = run("render_brief.py", str(tpl), "--out", out)
    t = brief(out, "cap.md")
    assert r.returncode == 0 and re.search(r"15 ч/нед × 70 % на разработку = 10[.,]5 ч/нед", t)
    assert "Выводы исследования (C4.5" in t and "опровергнуто" in t and "идея v2: личный план фарма" in t
    assert "Ёмкость: 15 ч/нед" in t                                                           # и в контексте идеи
    r = run("render_brief.py", "concept-analogs", "--out", out, "--allow-untranslated")
    assert "https://metaforge.app" in brief(out, "concept-analogs.md")


# ---------------------------------------------------------------- FB-004/006/043: общие правила
def test_rules_block_tmp_dir_browser_and_deviations(concept):
    r = run("render_brief.py", "flows", "--out", concept, "--auto", "--group", "F1")
    t = brief(concept, "flows-F1.md")
    assert r.returncode == 0 and "## Общие правила прогона (render_brief.py)" in t
    assert "build/tmp/flows-F1/" in t and "Отступления от брифа" in t and "владелец общих файлов" in t
    assert t.index("## Общие правила прогона") < t.index("## Формат отчёта") if "## Формат отчёта" in t else True
    r = run("render_brief.py", "mockups", "--out", concept, "--auto", "--suffix", "A")
    t = brief(concept, "mockups-A.md")
    assert "браузер владельца" in t and "build/tmp/mockups-A/" in t
    r = run("render_brief.py", "flows", "--out", concept, "--auto", "--group", "F2", "--no-rules")
    assert "Общие правила прогона" not in brief(concept, "flows-F2.md")
    # check_paths разрешает агенту ровно его временную папку
    sys.path.insert(0, str(SCRIPTS))
    import check_paths
    allow, _deny = check_paths.brief_patterns(brief(concept, "flows-F1.md"), None)
    assert not any(p.startswith("build/tmp/flows-F2") for p in allow)


def test_legacy_conditional_lines_exact_number(concept, tmp_path):
    """Шаблон в стиле 1.4: «- Если в {SECTIONS} есть раздел 14 …» — по точному номеру, а не по подстроке («1.» и «4.» ≠ 14)."""
    tpl = tmp_path / "legacy.md"
    tpl.write_text("# Бриф {SECTIONS}\n\n## Выдача\n- `{OUT}/build/parts/x.md`\n"
                   "- Если в {SECTIONS} есть раздел 14 «План действий»: `{OUT}/data/gantt.json` по схеме контракта.\n"
                   "- Если в {SECTIONS} есть раздел 4 «Сообщества»: список площадок.\n\n## Чек-лист сдачи\n"
                   "- [ ] Если писал `gantt.json`/`kanban.json` — JSON валиден.\n", encoding="utf-8")
    r = run("render_brief.py", str(tpl), "--out", concept, "--set", "SECTIONS=1. Резюме; 4. Сообщества", "--no-rules")
    t = brief(concept, "legacy.md")
    assert r.returncode == 0 and "Если в" not in t and "gantt.json" not in t
    assert "- Список площадок." in t                                                          # своё условие — без «Если»
