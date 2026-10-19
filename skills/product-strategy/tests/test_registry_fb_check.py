"""1.5, WP-C: проверка реестра — подсказка про overrides при длинной цитате (FB-029), личный режим (категории, квоты,
порог A+B; SM разд. 4), evidence.kind owner_prior_work (класс ≤ C, свой порог A+B; SM 6.1), тег релиза ↔ horizon.

Запуск: python3 -m pytest skills/product-strategy/tests/test_registry_fb_check.py -q
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pipeline import jdump, jload, make_out, proposal, run  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check_registry as cr  # noqa: E402

LONG = "«" + " ".join("слово%d" % i for i in range(17)) + "»"
OWNER_EV = [{"kind": "owner_prior_work", "url": "https://github.com/owner/ref-repo", "file": None, "title": "референс владельца",
             "note": "замеры владельца", "checked": "2026-10-19"}]


# ---------------------------------------------------------------- FB-029
def test_long_quote_error_points_to_overrides_and_suggests(tmp_path):
    p = proposal(64, description="Пользователь пишет: %s — это главная боль." % LONG)
    q = proposal(65, evidence=[dict(proposal(0)["evidence"][0], note="цитата " + LONG)])
    out = make_out(tmp_path, [p, q])
    r = run("check_registry.py", out, "--suggest-overrides")
    assert r.returncode == 1
    assert "build/overrides.json" in r.stdout and '{"P064": {"description": "…"}}' in r.stdout
    assert "--suggest-overrides" in r.stdout
    sug = jload(out / "build" / "overrides.suggested.json")
    assert "слово9 …»" in sug["P064"]["description"] and "слово16" not in sug["P064"]["description"]
    assert "слово16" not in sug["P065"]["evidence"][0]["note"]
    # перенос заготовки в overrides.json и слияние (--apply-overrides) снимают ошибку
    ov = {k: v for k, v in sug.items() if not k.startswith("_")}
    jdump(out / "build" / "overrides.json", ov)
    assert run("merge_proposals.py", out, "--apply-overrides").returncode == 0
    c = run("check_registry.py", out, "--demo")
    assert c.returncode == 0 and "цитата" not in c.stdout


# ---------------------------------------------------------------- личный режим
PERSONAL = {"strategy": {"proposals_min": 20}, "project": {"audience": "personal"},
            "idea": {"facets": {"ai_role": "Без ИИ"}}}


def personal_props(cats):
    return [proposal(i, category=c) for i, c in enumerate(cats, 1)]


def test_personal_mode_categories_minimums_and_quotas(tmp_path):
    req = cr.category_requirements(PERSONAL, 20)
    assert set(req) == set(cr.PERSONAL_CATEGORIES)
    assert req["ai-quality"]["optional"] and req["core"]["required"] == 1 and req["core"]["nominal"] == 6
    assert "acquisition" not in req and "monetization" not in req
    cats = ["core"] * 8 + ["data-sources", "reliability", "privacy-security", "ux", "maintenance", "personal-analytics"] * 2
    out = make_out(tmp_path, personal_props(cats), PERSONAL)
    r = run("check_registry.py", out)
    assert r.returncode == 0, r.stdout
    rep = jload(out / "data" / "registry-check.json")
    assert rep["audience"] == "personal" and rep["category_mode"] == "priority" and rep["now_capacity"] is not None
    # категория не представлена — ошибка «по приоритету»; категории аудитории — предупреждение
    cats2 = ["core"] * 14 + ["acquisition", "monetization"] + ["ux", "maintenance", "personal-analytics", "privacy-security"]
    make_out(out, personal_props(cats2), PERSONAL)
    r = run("check_registry.py", out)
    assert r.returncode == 1 and "категория data-sources: 0 < 1 (минимум по приоритету" in r.stdout
    assert "категории аудитории acquisition 1, monetization 1 не нужны" in r.stdout
    # квоты для брифа генераторов ({QUOTAS})
    q = run("check_registry.py", out, "--quotas", "--json")
    quotas = json.loads(q.stdout)
    assert quotas["core"] == 6 and "acquisition" not in quotas and "ai-quality" not in quotas
    # ИИ в продукте — ai-quality обязательна
    cfg = json.loads(json.dumps(PERSONAL))
    cfg["idea"]["facets"]["ai_role"] = "ядро продукта"
    assert cr.category_requirements(cfg, 20)["ai-quality"]["required"] == 1


def test_personal_then_public_and_public_compat(tmp_path):
    cfg = {"strategy": {"proposals_min": 1}, "project": {"audience": "personal_then_public"}}
    assert "acquisition" in cr.active_categories(cfg) and "core" in cr.active_categories(cfg)
    props = [proposal(1, category="core"), proposal(2, category="acquisition", horizon="now"),
             proposal(3, category="monetization", horizon="later")]
    out = make_out(tmp_path, props, cfg)
    r = run("check_registry.py", out, "--demo")
    assert "в horizon now у P002" in r.stdout and "P003" not in r.stdout.split("в horizon now у", 1)[1].split("\n")[0]
    # публичный продукт без audience — как в 1.4 (count, прежние категории), личная категория — предупреждение
    pub = {"strategy": {"proposals_min": 10}}
    assert cr.category_mode(pub) == "count" and cr.category_requirements(pub, 10)["product"]["required"] == 3
    out2 = make_out(tmp_path / "pub", [proposal(1, category="core")], {"strategy": {"proposals_min": 1}})
    r = run("check_registry.py", out2, "--demo")
    assert "категории личного режима (core)" in r.stdout


# ---------------------------------------------------------------- owner_prior_work
def test_owner_prior_work_class_cap_and_ab_threshold(tmp_path):
    good = [proposal(i, evidence_class="B") for i in range(1, 4)]
    owner_c = [proposal(i, evidence_class="C", evidence=OWNER_EV) for i in range(4, 10)]
    out = make_out(tmp_path, good + owner_c, {"strategy": {"proposals_min": 1}, "mode": "concept"})
    r = run("check_registry.py", out, "--demo")
    rep = jload(out / "data" / "registry-check.json")
    # 3 из 9 = 33 % всего, но предложения только на owner_prior_work не в знаменателе → 100 %
    assert rep["ab_share"] == round(3 / 9, 4) and rep["ab_share_checked"] == 1.0
    assert sorted(rep["owner_only"]) == ["P%03d" % i for i in range(4, 10)]
    assert "доля классов A+B" not in r.stdout
    assert "repo/own_app" not in r.stdout                                    # owner_prior_work в режиме идеи допустим
    assert rep["evidence_sides"].get("internal") == 6
    # класс A при одних owner_prior_work — ошибка
    bad = proposal(10, evidence_class="A", evidence=OWNER_EV)
    make_out(out, good + owner_c + [bad], {"strategy": {"proposals_min": 1}})
    r = run("check_registry.py", out)
    assert r.returncode == 1 and "P010: класс A при доказательствах только owner_prior_work" in r.stdout


def test_personal_ab_threshold_40(tmp_path):
    cats = ["core"] * 10
    props = [proposal(i, category=c, evidence_class="B" if i <= 4 else "C") for i, c in enumerate(cats, 1)]
    cfg = {"strategy": {"proposals_min": 1}, "project": {"audience": "circle"}, "registry": {"category_minimums": "count"}}
    out = make_out(tmp_path, props, cfg)
    r = run("check_registry.py", out, "--demo")
    assert "доля классов A+B" not in r.stdout and "внешних A+B" not in r.stdout      # 40 % ≥ 40 %
    assert jload(out / "data" / "registry-check.json")["ab_min_share"] == 0.4


def test_concept_tag_horizon_mismatch_warning(tmp_path):
    props = [proposal(1, tags=["mvp"], horizon="now"), proposal(2, tags=["mvp"], horizon="later"), proposal(3, tags=["v1"], horizon="next")]
    out = make_out(tmp_path, props, {"strategy": {"proposals_min": 1}, "mode": "concept"})
    r = run("check_registry.py", out, "--demo")
    assert "тег релиза расходится с horizon" in r.stdout and "P002 (mvp/later)" in r.stdout and "P003" not in r.stdout.split("тег релиза")[1].split("\n")[0]
