"""Волна 2 (1.5.0): запросы пакетов A–G к шаблонам брифов, набору макетов и прототипа (pytest, без сети).

Критерии приёмки (docs/plans/wp-*-requests.md):
  - FB-051, FB-004 (wp-c): хвост _report-footer.md — строки «ПРЕДПОСЫЛКА:» (их понимает collect_reports.py --deps) и блок
    «Отступления от брифа» (--retro); авторы разделов, спецификаций, экспериментов, схем, макетов ссылаются на них;
  - SM 6.1 (wp-c): gap-audit — зависимости от G7-NN текстом, unlocks или в gap-audit-deps.json; registry-generator —
    личные категории, {QUOTAS}, запреты для реестра;
  - FB-028, FB-046, FB-027 (wp-b): {CAPACITY} в брифах авторов, сроки — {plan:…}, sensitivity-only — метка иллюстрации,
    личный профиль модели; FB-047: порядок summary_scaffold → бриф резюме (черновик build/summary-draft.md);
  - FB-022, FB-002 (wp-a): имя карточки self из {PRODUCT} и «рабочее имя»; входы research-owner-refs; поля design.*;
  - SM 11 (wp-b, wp-g): канон демо-данных и data-canon в брифах макетов и README набора; FB-038 (wp-e): <title> узлов
    схем; wp-d №18: временные файлы брифов набора — build/tmp/<имя брифа>/.
Запуск: python3 -m pytest skills/product-strategy/tests/test_briefs_wave2.py -q -p no:cacheprovider
"""
import contextlib
import io
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SKILL / "scripts"))
from test_pipeline import run  # noqa: E402

import collect_reports  # noqa: E402
import render_brief  # noqa: E402

BRIEFS = SKILL / "templates" / "briefs"
PH = re.compile(r"\{[A-Z][A-Z0-9_]*\}")
AUTHORS = ["strategy-section", "specs", "experiments", "flows", "mockups", "concept-design"]


def brief(name):
    return (BRIEFS / (name + ".md")).read_text(encoding="utf-8")


def render(out, name, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        rc = render_brief.main([name, "--out", str(out)] + [str(a) for a in args])
    return rc, buf.getvalue()


@pytest.fixture(scope="module")
def concept(tmp_path_factory):
    out = tmp_path_factory.mktemp("w2-concept")
    assert run("make_concept_demo.py", out).returncode == 0
    assert run("score.py", out).returncode == 0
    return out


# ---------------------------------------------------------------- FB-051 / FB-004: хвост отчёта

def test_footer_prereq_and_deviation_blocks():
    t = brief("_report-footer")
    assert not PH.findall(t)
    for s in ("## Расхождения с фактами", "## Предпосылки, которых нет в реестре", "## Отступления от брифа",
              "collect_reports.py --deps", "build/deps-patch.json", "collect_reports.py --retro", "build/retro.md"):
        assert s in t, s
    pre = collect_reports.parse_prereqs(t)
    assert pre and pre[0]["id"] == "P038" and pre[0]["prereqs"] == ["P033", "P111"]
    # порядок блоков: расхождения → предпосылки → отступления
    assert t.index("## Расхождения с фактами") < t.index("## Предпосылки") < t.rindex("## Отступления от брифа")


@pytest.mark.parametrize("name", AUTHORS)
def test_author_briefs_ask_for_prereq_lines(name):
    t = brief(name)
    assert "ПРЕДПОСЫЛКА: P038 ← P033 | почему" in t and "_report-footer.md" in t and "Отступления от брифа" in t
    assert collect_reports.parse_prereqs("ПРЕДПОСЫЛКА: P038 ← P033 | почему")[0]["prereqs"] == ["P033"]


def test_every_footer_reference_mentions_deviations():
    for p in BRIEFS.glob("*.md"):
        t = p.read_text(encoding="utf-8")
        if p.stem != "_report-footer" and "_report-footer.md" in t:
            assert "Отступления от брифа" in t, p.name


# ---------------------------------------------------------------- SM 6.1: аудит пробелов и генератор реестра

def test_gap_audit_g7_dependencies_any_way():
    t = brief("gap-audit")
    assert "сюда не писать" not in t
    for s in ("P035 ← G7-02", "`\"unlocks\": [\"P035\"]`", "data/gap-audit-deps.json", "merge_proposals.py --append G7",
              "`gap_audit.py --remap` после `--append` не нужны", "{CAPACITY}", "owner_prior_work"):
        assert s in t, s
    assert "4. Зависимости от G7 сводкой" in t


def test_registry_generator_personal_mode_categories_quotas_bans():
    t = brief("registry-generator")
    personal = t[t.index("## Личный режим"):]
    for s in ("core", "personal-analytics", "{QUOTAS}", "check_registry.py <OUT> --quotas", "Запреты для реестра",
              "`later`/`vision`", "owner_prior_work", "release_outward"):
        assert s in personal, s
    assert "G9" in t and "G10" in t and "G11" in t and "{CAPACITY}" in t


# ---------------------------------------------------------------- FB-028 / FB-046 / FB-027 / FB-047: ёмкость, план, модель

@pytest.mark.parametrize("name", ["strategy-section", "specs", "experiments", "gap-audit", "registry-generator"])
def test_capacity_placeholder_in_author_briefs(name):
    t = brief(name)
    assert "{CAPACITY}" in t and "`{CAPACITY}`" in t.splitlines()[2]           # в теле и в справочной строке
    assert render_brief.RESOLVERS["CAPACITY"][1] is not None


def test_strategy_section_plan_placeholders_and_model_labels():
    t = brief("strategy-section")
    for s in ("{plan:beta}", "{plan:launch}", "{plan:mvp_ids}", "{plan:kill.N.date}", "{plan:capacity}", "workday_mismatch",
              "--list-placeholders", "sensitivity-only", "[иллюстрация при допущениях]", "{model:base.value|money}",
              "{model:base.hours_saved_per_week_to_break_even|1}"):
        assert s in t, s


def test_specs_and_experiments_no_raw_plan_placeholders_in_research_files():
    s, e = brief("specs"), brief("experiments")
    assert "link_mockups.py {OUT} --index-only" in s
    for t in (s, e):
        assert "не раскрываются" in t and "(data/plan-baseline.json)" in t
    assert "hours_saved_per_week_to_break_even" in e and "model.py --profile personal" in e


@pytest.mark.parametrize("name", ["strategy-section", "specs", "experiments", "strategy-summary"])
def test_plan_baseline_placeholder(name):
    t = brief(name)
    assert "{PLAN_BASELINE}" in t and "`{PLAN_BASELINE}`" in t.splitlines()[2]


def test_strategy_summary_order_with_scaffold():
    t = brief("strategy-summary")
    assert "{OUT}/build/summary-draft.md" in t and "**без** `--to-part`" in t and "--to-part` (тогда этот бриф не запускать)" in t
    assert "{plan:capacity}" in t and "build/parts/strategy-01.md" in t


def test_author_briefs_render_with_capacity(concept):
    for name in ("strategy-section", "specs", "experiments", "gap-audit", "registry-generator"):
        extra = ["--auto"] + (["--set", "SECTIONS=8. Стоимость владения"] if name == "strategy-section" else []) + \
            (["--group", "G1", "--pass", "titles"] if name == "registry-generator" else [])
        rc, outp = render(concept, name, *extra)
        assert rc == 0, (name, outp)
        t = max((concept / "build" / "briefs").glob(name + "*.md"), key=lambda f: f.stat().st_mtime).read_text(encoding="utf-8")
        rest = "\n".join(l for l in t.splitlines() if not l.startswith("Плейсхолдеры:"))
        assert "{CAPACITY}" not in rest and "ч/нед" in rest, name                  # строка capacity.py, а не «нет данных»
        assert "CAPACITY (нет данных)" not in t, name
        if name in ("strategy-section", "specs", "experiments"):
            assert "{PLAN_BASELINE}" not in rest and "PLAN_BASELINE (нет данных)" not in t, name


# ---------------------------------------------------------------- FB-022 / FB-002 / поля design.*

def test_concept_analogs_self_name_and_working_name():
    t = brief("concept-analogs")
    assert "`name` — ровно {PRODUCT}" in t and "run-config.product.name" in t
    assert "idea.name_source = auto" in t and "рабочее имя" in t and "\"name_note\": \"рабочее имя\"" in t


def test_owner_refs_inputs_roles_and_statuses():
    t = brief("research-owner-refs")
    inputs = t[t.index("## Входы (только чтение)"):t.index("## Входы, которых нет")]
    for s in ("{OUT}/build/owner-materials.md", "sources.owner_docs[]", "base", "follow", "ref", "blocked", "not_attempted",
              "только как основа вопросов"):
        assert s in inputs, s


def test_concept_design_reads_intake_design_fields():
    t = brief("concept-design")
    for s in ("`directions_count` — сколько направлений предложить (1–7", "modes_decide_later", "product.future_forms",
              "idea.facets.doc_features[]", "M2x-ai-", "M3x-admin-", "research/ai-observability.md"):
        assert s in t, s


# ---------------------------------------------------------------- SM 11: канон демо-данных

@pytest.mark.parametrize("name", ["concept-design", "mockups"])
def test_mockup_briefs_demo_canon_attributes(name):
    t = brief(name)
    for s in ("demo-canon.json", 'data-canon="<ключ>"', "data-canon-item", "model.price_month", "C01.paybackWeeks",
              "entities", "templates/prototype-kit/tools/check_canon.py {OUT}"):
        assert s in t, (name, s)


def test_kit_readme_and_prototype_docs_canon():
    kit = (SKILL / "templates" / "mockup-kit" / "README.md").read_text(encoding="utf-8")
    assert "## Канон демо-данных (`data-canon`)" in kit and "data-canon-item" in kit and "check_canon.py <OUT>" in kit
    proto = (SKILL / "templates" / "prototype-kit" / "README.md").read_text(encoding="utf-8")
    assert "model.price_month" in proto and "values" in proto and "cases" in proto
    core = brief("prototype-core")
    assert "только значения показа (`values`" in core


# ---------------------------------------------------------------- FB-038 / wp-d №18

def test_flows_requires_title_in_nodes():
    t = brief("flows")
    assert "первым дочерним элементом каждого `<g data-node>` — `<title>` с текстом из `nodes[].what`" in t
    assert "check_flow.mjs" in t and "<title>" in t[t.index("## Чек-лист сдачи"):]


@pytest.mark.parametrize("name", ["concept-design", "mockups", "design-refs", "competitor-cards"])
def test_kit_briefs_tmp_folder_by_brief_name(name):
    t = brief(name)
    assert "build/tmp/<имя файла этого брифа без .md>/" in t and "<ключ агента>" not in t
