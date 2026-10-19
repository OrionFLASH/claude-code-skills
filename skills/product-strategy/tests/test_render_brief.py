"""render_brief.py: подстановка плейсхолдеров брифов из run-config и данных прогона (pytest, без сети).

Проверяется на демо-прогонах make_demo.py (продукт) и make_concept_demo.py (идея): registry-generator (оба прохода),
research-competitors, strategy-section, specs, experiments, concept-*; непарные плейсхолдеры → код 1; --list;
справочная строка «Плейсхолдеры: …» не раскрывается; пути относительные, без домашней папки.
Запуск: python3 -m pytest skills/product-strategy/tests/test_render_brief.py -q
"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pipeline import jdump, jload, proposal, run  # noqa: E402

SKILL = Path(__file__).resolve().parent.parent
TEMPLATES = SKILL / "templates" / "briefs"
PH = re.compile(r"\{[A-Z][A-Z0-9_]*\}")


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("rb-demo")
    assert run("make_demo.py", out).returncode == 0
    assert run("score.py", out).returncode == 0
    return out


@pytest.fixture(scope="module")
def concept(tmp_path_factory):
    out = tmp_path_factory.mktemp("rb-concept")
    assert run("make_concept_demo.py", out).returncode == 0
    assert run("score.py", out).returncode == 0
    return out


def brief(out, name):
    return (out / "build" / "briefs" / name).read_text(encoding="utf-8")


def ref_line(name):
    return next(l for l in (TEMPLATES / (name + ".md")).read_text(encoding="utf-8").splitlines() if l.startswith("Плейсхолдеры:"))


def body_ok(text, name):
    """Справочная строка как в шаблоне; в остальном теле не осталось {ЗАГЛАВНЫХ}; нет домашней папки."""
    lines = text.splitlines()
    ref = [l for l in lines if l.startswith("Плейсхолдеры:")]
    assert ref == [ref_line(name)]
    rest = "\n".join(l for l in lines if not l.startswith("Плейсхолдеры:"))
    assert not PH.findall(rest), PH.findall(rest)
    assert str(Path.home()) not in text
    return rest


def test_registry_generator_titles_and_details(demo):
    q = "acquisition — 22; localization — 6"
    r = run("render_brief.py", "registry-generator", "--out", demo, "--group", "G1", "--pass", "titles",
            "--set", "QUOTAS=" + q, "--set", "EXISTING=шаблоны проектов, команды")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "build/briefs/registry-generator-G1.md" in r.stdout and "Промпт агенту" in r.stdout
    t = body_ok(brief(demo, "registry-generator-G1.md"), "registry-generator")
    assert "группа G1, проход titles — Demo App" in t
    assert "по acquisition, localization (на 20–30 %" in t                    # CATEGORIES из QUOTAS
    assert "## Контекст продукта\n- Продукт: Demo App" in t
    assert len(re.findall(r"(?m)^- ", t.split("## Контекст продукта")[1].split("\n\n")[0])) >= 5
    assert "не больше 2 поисков" in t and "data/issues.json, research/issues-demand.md — анализ Issues выключен" in t
    assert "(scope.app_run=false)" in t and "~/" in t                          # SKILL_DIR через ~
    # проход details: свои и чужие заголовки из черновиков
    jdump(demo / "data" / "proposals-draft-G1.json", [proposal(0, id="G1-01", title="Страницы сравнения")])
    jdump(demo / "data" / "proposals-draft-G2.json", [proposal(0, id="G2-01", title="Дайджест недели")])
    r = run("render_brief.py", "registry-generator", "--out", demo, "--group", "G1", "--pass", "details",
            "--set", "QUOTAS=" + q, "--set", "EXISTING=шаблоны")
    assert r.returncode == 0, r.stdout
    t = body_ok(brief(demo, "registry-generator-G1.md"), "registry-generator")
    assert "- G1-01 — Страницы сравнения" in t and "- G2-01 — Дайджест недели (у G2)" in t
    assert "не больше 0 (веб-поиск выключен в run-config) поисков" in t        # sources.web_search=false в демо
    assert "пересекается с «чужие заголовки» (список" in t or "«чужие заголовки» (см. список выше)" in t
    for f in ("proposals-draft-G1.json", "proposals-draft-G2.json"):
        (demo / "data" / f).unlink()


def test_missing_placeholders_error_and_allow(demo):
    dest = demo / "build" / "briefs" / "registry-generator-G9.md"
    r = run("render_brief.py", "registry-generator", "--out", demo, "--group", "G9", "--pass", "titles")
    assert r.returncode == 1 and "{QUOTAS}" in r.stdout and "{EXISTING}" in r.stdout and "rank:P" in r.stdout
    assert not dest.exists()
    r = run("render_brief.py", "registry-generator", "--out", demo, "--group", "G9", "--pass", "titles", "--allow-missing")
    assert r.returncode == 1 and dest.exists() and "{QUOTAS}" in dest.read_text(encoding="utf-8")
    dest.unlink()


def test_research_competitors_and_set_from_file(demo, tmp_path):
    (tmp_path / "kw.txt").write_text("демо, шаблоны проектов\n", encoding="utf-8")
    r = run("render_brief.py", "research-competitors", "--out", demo, "--set", "KEYWORDS=@%s" % (tmp_path / "kw.txt"))
    assert r.returncode == 0, r.stdout
    t = body_ok(brief(demo, "research-competitors.md"), "research-competitors")
    assert "не меньше 10" in t and "демо, шаблоны проектов" in t and "references/locales/ru.md" in t
    assert "0 (веб-поиск выключен в run-config)" in t                           # sources.web_search=false в демо


def test_strategy_section_words_charts_context(demo):
    r = run("render_brief.py", "strategy-section", "--out", demo, "--set", "SECTIONS=6. Привлечение; 7. Конверсия и онбординг",
            "--set", "OTHER_PARTS=разделы 2–5 и 8–17 — другие агенты")
    assert r.returncode == 0, r.stdout
    t = body_ok(brief(demo, "strategy-section-06.md"), "strategy-section")       # PART из SECTIONS → суффикс 06
    assert "6. Привлечение — 1 200 / 1 800 слов; 7. Конверсия и онбординг — 1 000 / 1 500 слов" in t
    assert "effort-impact" in t and "M01-demo" in t and "zero, small, medium" in t
    assert t.index("## Контекст продукта") < t.index("## Входы")                # вставлен: в шаблоне его нет
    assert "./build/parts/strategy-06.md" in t


def test_specs_and_experiments(demo):
    r = run("render_brief.py", "specs", "--out", demo)
    assert r.returncode == 0, r.stdout
    top = [s["id"] for s in jload(demo / "data" / "scores.json")][:5]
    t = body_ok(brief(demo, "specs.md"), "specs")
    assert "из %s написать" % ", ".join(top) in t
    r = run("render_brief.py", "experiments", "--out", demo)
    assert r.returncode == 0, r.stdout
    t = body_ok(brief(demo, "experiments.md"), "experiments")
    assert "Подготовить 4 планов" in t and "Трафик: неизвестно" in t and "## Контекст продукта" in t


def test_list_mode(demo):
    r = run("render_brief.py", "specs", "--list", "--out", demo)
    assert r.returncode == 0
    assert "{IDS}" in r.stdout and "откуда: specs: топ-scope.specs_top" in r.stdout
    assert "Только в справочной строке" in r.stdout and "{DEPTH}" in r.stdout
    r = run("render_brief.py", "flows", "--list")
    assert r.returncode == 0 and "нужно --set FLOWS=" in r.stdout


def test_out_outside_repo_and_disabled_direction(demo, tmp_path):
    cfg = jload(demo / "build" / "run-config.json")
    saved = json.dumps(cfg, ensure_ascii=False)
    try:
        cfg["repo"]["path"] = str(demo.parent / "some-repo")
        cfg["scope"]["communities"] = False
        jdump(demo / "build" / "run-config.json", cfg)
        r = run("render_brief.py", "registry-generator", "--out", demo, "--group", "G4", "--pass", "titles",
                "--set", "QUOTAS=product — 5", "--set", "EXISTING=нет")
        assert r.returncode == 0, r.stdout
        t = brief(demo, "registry-generator-G4.md")
        assert "> Пути `{OUT}/…` в этом брифе — от папки" in t
        assert "`%s/data/competitors.json`" % demo.name in t
        assert "- data/communities.json — направление «сообщества» выключено" in t
    finally:
        (demo / "build" / "run-config.json").write_text(saved, encoding="utf-8")


@pytest.mark.parametrize("name,extra", [
    ("concept-analogs", []), ("concept-canvas", []),
    ("concept-design", ["--set", "KEYS=M01-catalog → P001", "--set", "VIEWPORTS=M01-catalog — 390x844"]),
])
def test_concept_briefs(concept, name, extra):
    r = run("render_brief.py", name, "--out", concept, *extra)
    assert r.returncode == 0, r.stdout + r.stderr
    t = body_ok(brief(concept, name + ".md"), name)
    assert "Книжная полка" in t
    assert "- Идея (дословно): Демо: приложение для обмена книгами" in t
    assert "Модель денег: бесплатно" in t and "профиль zero-budget-solo" in t
    if name == "concept-design":
        assert "1-3" in t and "Стиль: Тёплый и дружелюбный" in t                # STEPS по автопилоту, ответы «дизайн»
    if name == "concept-analogs":
        # 1.5 (FB-022): ключевые слова — без ярлыка «Демо:» перед двоеточием и без слов формы
        assert "Демо-аналог А, Демо-аналог Б" in t and "обмена, книгами, соседями" in t


def test_concept_registry_generator(concept):
    r = run("render_brief.py", "registry-generator", "--out", concept, "--group", "G1", "--pass", "titles",
            "--set", "QUOTAS=product — 12; acquisition — 8")
    assert r.returncode == 0, r.stdout
    t = body_ok(brief(concept, "registry-generator-G1.md"), "registry-generator")
    assert "Действует, когда `concept` = `concept`" in t                       # MODE из run-config
    assert "нет (продукта ещё нет)" in t
    assert "режим идеи: продукта и репозитория ещё нет" in t
    assert "(они в списке «Входы, которых нет в этом прогоне»)" in t           # многострочное в середине фразы — ссылкой
    assert "не больше 2 поисков" in t
    r = run("render_brief.py", "strategy-section", "--out", concept, "--set", "SECTIONS=10. Дорожная карта: MVP → v1 → v2",
            "--set", "OTHER_PARTS=остальные")
    assert r.returncode == 0, r.stdout
    assert "10. Дорожная карта: MVP → v1 → v2 — 1 400 / 2 100 слов" in brief(concept, "strategy-section-10.md")
