"""WP-G (1.5.0): новые брифы режима идеи, личный режим в outline и брифах, модули ИИ и администрирования,
входы брифов без ссылок на несуществующее, временные файлы агентов, значения brief_facets.py (pytest, без сети).

Критерии приёмки из фидбэков:
  - FB-045: бриф research-integration рендерится без --set на эталоне ARC Raiders; выдача integration-options.json;
  - FB-010: specs — архитектура {ARCH} из plan-baseline.json, без «будет в фазе 8»; experiments — data/experiments.json
    через sample_size.py --add; FB-011: авторы разделов добавляют источники в data/sources-s<часть>.json;
  - FB-047: бриф strategy-summary (раздел 1 из baseline и плейсхолдеров); FB-006: ключи схем из flows-plan.json,
    временные файлы — build/tmp/<имя брифа>/ (совпадает с check_paths.py);
  - SM 4/5/7/6.2/11: личный режим (разделы 4/6/8/9/12/13), модули ИИ/админки, брифы прототипа, research-datasources и
    research-owner-refs, «явно пропущено, потому что…», правила содержимого.
Запуск: python3 -m pytest skills/product-strategy/tests/test_briefs_concept.py -q -p no:cacheprovider
"""
import contextlib
import io
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SKILL / "scripts"))
from test_pipeline import jdump, jload, run  # noqa: E402

import brief_facets  # noqa: E402
import render_brief  # noqa: E402

brief_facets.install(render_brief.RESOLVERS)        # без интеграции в render_brief — тоже работает (идемпотентно)

TEMPLATES = SKILL / "templates" / "briefs"
PH = re.compile(r"\{[A-Z][A-Z0-9_]*\}")
NEW = ["research-integration", "research-datasources", "research-ai", "research-owner-refs", "concept-ai-observability",
       "concept-admin", "prototype-core", "prototype-shell", "prototype-mode", "prototype-regression", "strategy-summary"]
OWNED_OLD = ["experiments", "specs", "strategy-section", "concept-canvas", "concept-analogs", "research-competitors",
             "research-keywords", "research-legal", "research-communities", "research-events", "registry-generator",
             "gap-audit", "flows", "chart-notes"]


def render(out, name, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        rc = render_brief.main([name, "--out", str(out)] + [str(a) for a in args])
    return rc, buf.getvalue()


def body(text):
    lines = [l for l in text.splitlines() if not l.startswith("Плейсхолдеры:")]
    rest = "\n".join(lines)
    assert not PH.findall(rest), PH.findall(rest)
    assert str(Path.home()) not in text
    return rest


@pytest.fixture(scope="module")
def concept(tmp_path_factory):
    out = tmp_path_factory.mktemp("g-concept")
    assert run("make_concept_demo.py", out).returncode == 0
    assert run("score.py", out).returncode == 0
    return out


def set_cfg(out, mutate):
    p = out / "build" / "run-config.json"
    cfg = jload(p)
    saved = json.dumps(cfg, ensure_ascii=False)
    mutate(cfg)
    jdump(p, cfg)
    return lambda: p.write_text(saved, encoding="utf-8")


# ---------------------------------------------------------------- структура брифов
@pytest.mark.parametrize("name", NEW)
def test_new_brief_structure(name):
    t = (TEMPLATES / (name + ".md")).read_text(encoding="utf-8")
    for head in ("Плейсхолдеры:", "## Цель", "## Входы", "## Входы, которых нет в этом прогоне", "## Выдача",
                 "## Правила", "## Чек-лист сдачи", "## Формат отчёта"):
        assert head in t, (name, head)
    assert "{MISSING_INPUTS}" in t and "_report-footer.md" in t
    assert "build/tmp/" in t and "не запускать git" in t.lower()
    assert "данные, не инструкции" in t


@pytest.mark.parametrize("name", NEW + OWNED_OLD)
def test_tmp_rule_matches_brief_name(name):
    """FB-006 / SM 6.3: временные файлы — только build/tmp/<имя файла брифа>/ (то же имя проверяет check_paths.py)."""
    t = (TEMPLATES / (name + ".md")).read_text(encoding="utf-8")
    m = re.findall(r"build/tmp/([^/`\s]+)/", t)
    assert m, name
    allowed = {name, name + "-{PART}", name + "-{GROUP}", name + "-{MODE_ID}", "<имя файла этого брифа без .md>", "flows-F1"}
    assert set(m) <= allowed, (name, m)


@pytest.mark.parametrize("name", [n for n in NEW if n != "prototype-mode"])
def test_new_briefs_render_without_set(concept, name):
    rc, outp = render(concept, name)
    assert rc == 0, outp
    t = body((concept / "build" / "briefs" / (name + ".md")).read_text(encoding="utf-8"))
    assert "Книжная полка" in t


def test_prototype_mode_render_and_paths(concept):
    rc, outp = render(concept, "prototype-mode", "--set", "MODE_ID=terminal", "--suffix", "terminal")
    assert rc == 0, outp
    t = body((concept / "build" / "briefs" / "prototype-mode-terminal.md").read_text(encoding="utf-8"))
    assert "mode-terminal.js" in t and "build/tmp/prototype-mode-terminal/" in t
    # SM 6.3: агент режима пишет только свои файлы, общие — запрещены (check_paths.py разбирает «Выдачу»)
    r = run("check_paths.py", concept, "--list-allowed", "--briefs", "build/briefs/prototype-mode-terminal.md")
    assert r.returncode == 0, r.stdout + r.stderr
    rules = json.loads(r.stdout)["prototype-mode-terminal.md"]
    assert any("mode-terminal.js" in a for a in rules["allow"])
    assert not any("index.html" in a or "js/app.js" in a for a in rules["allow"])
    assert any("index.html" in d for d in rules["deny"]) and any("core.js" in d for d in rules["deny"])


# ---------------------------------------------------------------- FB-045: интеграция с платформой
def test_research_integration_reference_arc_raiders(concept):
    restore = set_cfg(concept, lambda c: c["idea"].update({"facets": {
        "platform_dependency": True, "platform_name": "ARC Raiders (Steam, Embark Studios)",
        "platform_urls": ["https://arcraiders.com", "https://partner.steamgames.com/doc/webapi_overview"],
        "platform_data_needs": ["данные о мире: предметы, карты, события", "данные игрока: прогресс, инвентарь", "вход через Steam OpenID"],
        "platform_access": "official"}, "request_questions": [
        {"id": "RQ01", "text": "Можно ли получить прогресс игрока законно?", "kind": "research"},
        {"id": "RQ02", "text": "Нужен PDF", "kind": "format"}]}))
    try:
        rc, outp = render(concept, "research-integration")                 # без --set
        assert rc == 0, outp
        t = body((concept / "build" / "briefs" / "research-integration.md").read_text(encoding="utf-8"))
    finally:
        restore()
    assert "интеграции с платформой ARC Raiders (Steam, Embark Studios)" in t
    assert "https://partner.steamgames.com/doc/webapi_overview" in t and "вход через Steam OpenID" in t
    assert "только официальный API" in t
    assert "RQ01 — Можно ли получить прогресс игрока законно?" in t and "Нужен PDF" not in t   # только kind=research
    for k in range(1, 9):
        assert re.search(r"(?m)^%d\. \*\*" % k, t), k                         # восемь пунктов исследования
    assert "data/integration-options.json" in t and "data/sources-tech.json" in t and "research/integration.md" in t
    assert "plan_baseline.py" in t                                           # варианты идут в baseline и раздел 11


def test_integration_options_schema_in_brief_is_checkable():
    """Однострочник чек-листа брифа проверяет integration-options.json по схеме из «Выдачи»."""
    t = (TEMPLATES / "research-integration.md").read_text(encoding="utf-8")
    for field in ('"recommended"', '"options"', '"effort_days"', '"risks"', '"value"', '"platform_risks"', '"queue"'):
        assert field in t


# ---------------------------------------------------------------- FB-010: спецификации и эксперименты
def test_specs_arch_from_plan_baseline(concept):
    rc, _ = render(concept, "specs")
    assert rc == 0
    t = body((concept / "build" / "briefs" / "specs.md").read_text(encoding="utf-8"))
    assert "архитектуры ещё нет" in t                                        # режим идеи без baseline
    assert "иначе «будет в фазе 8»" not in t and "будет в фазе|появится позже" in t
    jdump(concept / "data" / "plan-baseline.json", {"architecture": {"frontend": "PWA", "backend": "нет (статический сайт)",
                                                                     "data": "IndexedDB"}})
    try:
        rc, _ = render(concept, "specs")
        t = body((concept / "build" / "briefs" / "specs.md").read_text(encoding="utf-8"))
    finally:
        (concept / "data" / "plan-baseline.json").unlink()
    assert rc == 0 and "frontend: PWA" in t and "plan-baseline.json" in t


def test_arch_fallbacks(concept, tmp_path):
    class C:                                                                 # минимальный контекст render_brief.Ctx
        def __init__(self, out, concept_mode=True):
            self.out, self.cfg, self.idea, self.concept, self.name = out, {}, {}, concept_mode, "specs"
    out = tmp_path / "o"
    (out / "build" / "parts").mkdir(parents=True)
    (out / "data").mkdir()
    assert "код" in brief_facets.r_arch(C(out, concept_mode=False))
    jdump(out / "data" / "integration-options.json", {"recommended": "B", "options": [{"id": "B", "title": "Вход через платформу"}]})
    (out / "build" / "parts" / "strategy-11.md").write_text("## 11. Технологическое решение\nСтек: PWA.\n", encoding="utf-8")
    v = brief_facets.r_arch(C(out))
    assert "B «Вход через платформу»" in v and "build/parts/strategy-11.md" in v


def test_experiments_brief_writes_experiments_json(concept):
    t = (TEMPLATES / "experiments.md").read_text(encoding="utf-8")
    assert "sample_size.py {OUT} --add E01" in t and "`{OUT}/data/experiments.json`" in t.split("## Выдача")[1]
    assert "{exp:E01.n}" in t and "N = 1" in t                                # личный режим: эксперименты на себе
    rc, _ = render(concept, "experiments")
    assert rc == 0
    body((concept / "build" / "briefs" / "experiments.md").read_text(encoding="utf-8"))
    # сама команда из брифа пишет data/experiments.json со значением для {exp:E01.n}
    r = run("sample_size.py", concept, "--add", "E01", "--baseline", "0.1", "--mde", "0.05", "--title", "Лист ожидания",
            "--proposal", "P001", "--traffic", "500")
    assert r.returncode == 0, r.stdout + r.stderr
    e = jload(concept / "data" / "experiments.json")
    assert e["experiments"][0]["id"] == "E01" and e["experiments"][0].get("n_per_arm")
    r = run("assemble_strategy.py", concept, "--list-placeholders")          # критерий FB-010: значение {exp:E01.n}
    assert re.search(r"(?m)^\{exp:E01\.n\}\s+\d", r.stdout), r.stdout[-800:]


# ---------------------------------------------------------------- FB-011, FB-006, SM 6.2: текст стратегии и схемы
def test_strategy_section_sources_flows_and_outputs(concept):
    rc, _ = render(concept, "strategy-section", "--set", "SECTIONS=2. Идея; 3. Рынок", "--set", "OTHER_PARTS=остальные")
    assert rc == 0
    t = body((concept / "build" / "briefs" / "strategy-section-02.md").read_text(encoding="utf-8"))
    assert "data/sources-s02.json" in t and "merge_sources.py" in t           # FB-011
    assert "data/flows-plan.json" in t                                       # FB-006
    assert "Если в 2. Идея" not in t                                         # SM 6.2: без условий по подстроке
    assert "| 14 |" in t and "без пропусков" in t                            # Гант на весь горизонт
    assert "явно пропущено, потому что" in t
    assert "гипотеза новизны" in t and "эталонного эксперимента" in t        # SM 11
    assert "Для кого: `public`" in t


def test_flows_plan_keys(concept):
    jdump(concept / "data" / "flows-plan.json", [{"key": "user-journey", "title": "Путь пользователя", "agent": "F1"},
                                                 {"key": "architecture", "title": "Архитектура", "agent": "F2"}])
    try:
        rc, outp = render(concept, "flows", "--set", "MODE=draw", "--suffix", "F1")     # FLOWS — из плана, без --set
        t = body((concept / "build" / "briefs" / "flows-F1.md").read_text(encoding="utf-8"))
    finally:
        (concept / "data" / "flows-plan.json").unlink()
    assert rc == 0, outp
    assert "user-journey — Путь пользователя; architecture — Архитектура" in t
    assert "build/tmp/<имя файла этого брифа без .md>/" in t and "сливается в `data/flows.json` скриптом" in t
    jdump(concept / "data" / "flows-plan.json", {"flows": [{"key": "k1", "title": "Т1"}]})       # форма-объект
    try:
        class C:
            out, cfg, idea = concept, {}, {}
        assert brief_facets.r_flows(C()) == "k1 — Т1"
    finally:
        (concept / "data" / "flows-plan.json").unlink()


# ---------------------------------------------------------------- SM 4: личный режим
def test_personal_mode_values_and_briefs(concept):
    restore = set_cfg(concept, lambda c: c["project"].update({"audience": "personal_then_public"}))
    try:
        for name in ("strategy-section", "experiments", "concept-canvas", "concept-analogs", "registry-generator"):
            extra = {"strategy-section": ["--set", "SECTIONS=8. Модель", "--set", "OTHER_PARTS=остальные"],
                     "registry-generator": ["--group", "G1", "--pass", "titles", "--set", "QUOTAS=core — 10"]}.get(name, [])
            rc, outp = render(concept, name, *extra)
            assert rc == 0, (name, outp)
        t = (concept / "build" / "briefs" / "strategy-section-08.md").read_text(encoding="utf-8")
        assert "`personal_then_public`" in t and "Если захочется выпустить наружу" in t
        canvas = (concept / "build" / "briefs" / "concept-canvas.md").read_text(encoding="utf-8")
        assert "JTBD владельца" in canvas and "personal_then_public" in canvas
        analogs = (concept / "build" / "briefs" / "concept-analogs.md").read_text(encoding="utf-8")
        assert "## Build vs buy" in analogs
        reg = (concept / "build" / "briefs" / "registry-generator-G1.md").read_text(encoding="utf-8")
        for cat in ("core", "data-sources", "reliability", "privacy-security", "ux", "ai-quality", "maintenance", "personal-analytics"):
            assert "`%s`" % cat in reg
        assert "**без** `acquisition`, `conversion`, `retention`, `monetization`, `partnerships`, `localization`" in reg
    finally:
        restore()


def test_audience_rules_resolver():
    class C:
        def __init__(self, aud):
            self.cfg, self.idea = {"project": {"audience": aud}} if aud else {}, {}
    assert "публичный продукт" in brief_facets.r_audience_rules(C(None))
    rules = brief_facets.r_audience_rules(C("personal"))
    assert "build vs buy" in rules and "concept-outline.md" in rules and "{SKILL_DIR}" not in rules
    assert "выпуске наружу" in brief_facets.r_audience_rules(C("personal_then_public"))
    assert brief_facets.audience(C("weird")) == "public"


def test_outline_personal_mode_and_modules():
    t = (SKILL / "references" / "concept-outline.md").read_text(encoding="utf-8")
    sec = t.split("## Личный режим")[1].split("## Модули концепции")[0]
    for n, title in ((4, "Источники знаний и компоненты"), (6, "План внедрения и привычка использования"),
                     (8, "Стоимость владения и окупаемость личных усилий"), (9, "Поддержка, обновления, резервные копии"),
                     (12, "Личные KPI и проверка на себе"), (13, "Риски: данные, зависимости, поддержка, право")):
        assert re.search(r"\| Раздел %d \|[^|]+\| %s \|" % (n, re.escape(title)), sec), n
    assert "Если захочется выпустить наружу" in sec and "build vs buy" in sec.lower()
    for mod in ("research-integration.md", "research-datasources.md", "research-ai.md", "research-owner-refs.md",
                "concept-ai-observability.md", "concept-admin.md", "prototype-*.md"):
        assert mod in t
    rules = t.split("## Правила содержимого (1.5.0)")[1]
    assert "гипотеза новизны" in rules and "demo-canon.json" in rules and "эталонного эксперимента" in rules
    assert "Что пропущено и почему" in t
    # таблица объёма не испорчена новыми таблицами (render_brief.r_words читает строки «| N | Раздел | standard |»)
    head, rows = None, {}
    for line in t.splitlines():
        cells = [x.strip() for x in line.strip().strip("|").split("|")]
        if line.startswith("| №"):
            head = cells
            continue
        if head and len(cells) == len(head) and cells[0].isdigit():
            rows[int(cells[0])] = dict(zip(head, cells))
    assert sorted(rows) == list(range(1, 18))
    assert rows[10]["standard"] == "1 400 / 2 100" and rows[4]["standard"] == "700 / 1 050"


# ---------------------------------------------------------------- SM 5, 6.2: модули и новые исследования
def test_module_briefs_outputs_and_groups():
    def t(n):
        return (TEMPLATES / (n + ".md")).read_text(encoding="utf-8")
    assert "research/data-sources.md" in t("research-datasources") and "auth_howto" in t("research-datasources")
    assert "research/owner-references.md" in t("research-owner-refs") and "owner_prior_work" in t("research-owner-refs")
    assert "proposals-draft-G11.json" in t("research-owner-refs")
    ai = t("research-ai")
    assert "## Эталонный эксперимент выбора модели" in ai and '"status": "candidate"' in ai
    obs = t("concept-ai-observability")
    assert "proposals-draft-G9.json" in obs and "min_sample" in obs and "never_store" in obs
    adm = t("concept-admin")
    assert "proposals-draft-G10.json" in adm and "## Резервные копии и восстановление" in adm and "data-hs-*" in adm
    summ = t("strategy-summary")
    assert "{plan:kill.N.date}" in summ and "build/parts/strategy-01.md" in summ and "summary_scaffold.py" in summ
    assert "build/parts/strategy-01-draft" not in summ                       # черновик не попадёт в сборку как часть


def test_personal_skip_and_request_questions_in_research(concept):
    for name in ("research-keywords", "research-events", "research-communities"):
        t = (TEMPLATES / (name + ".md")).read_text(encoding="utf-8")
        assert "## Личный режим" in t and "явно пропущено, потому что личный режим" in t
        assert "{REQUEST_QUESTIONS}" in t
    restore = set_cfg(concept, lambda c: c["idea"].update({"request_questions": [{"id": "RQ01", "text": "Сколько стоит доставка?", "kind": "research"}]}))
    try:
        rc, outp = render(concept, "concept-analogs")
        t = body((concept / "build" / "briefs" / "concept-analogs.md").read_text(encoding="utf-8"))
    finally:
        restore()
    assert rc == 0, outp
    assert "- RQ01 — Сколько стоит доставка?" in t
    legal = (TEMPLATES / "research-legal.md").read_text(encoding="utf-8")
    assert "## Запреты для реестра" in legal
    gap = (TEMPLATES / "gap-audit.md").read_text(encoding="utf-8")
    assert "G7-02" in gap and "сам переводит" in gap and "score.py <OUT>" in gap   # SM 6.1/6.2: зависимости G7, порядок C5.5


def test_resolvers_safe_without_data(tmp_path):
    """Каждый резолвер brief_facets даёт строку (или None только для FLOWS) на пустом прогоне — бриф не падает."""
    out = tmp_path / "empty"
    (out / "data").mkdir(parents=True)

    class C:
        cfg, idea, concept, name = {}, {}, True, "x"
    C.out = out
    for k, (src, fn) in brief_facets.RESOLVERS.items():
        v = fn(C())
        assert (v is None) == (k == "FLOWS"), k
        assert src
