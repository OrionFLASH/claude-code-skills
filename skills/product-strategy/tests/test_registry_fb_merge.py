"""1.5, WP-C: слияние реестра — однопроходный режим без ручной правки merge-map.json (FB-005), потолок now по ёмкости
(SM 6.1, п. 6 списка изменений), очереди нарезки (slicing), горизонты по решениям владельца (decisions.json), патч
«_add», перевод G8-NN в файлах прогона после --append G8 (FB-009, SM А15).

Запуск: python3 -m pytest skills/product-strategy/tests/test_registry_fb_merge.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pipeline import jdump, jload, make_out, proposal, run  # noqa: E402
from test_registry2 import drafts, regs  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import merge_proposals as mp  # noqa: E402

DUP = [proposal(0, id="G1-01", title="Английский интерфейс: словари и переключатель языка",
                description="Вынести строки интерфейса в словари ru/en, функция t() и переключатель языка в шапке."),
       proposal(0, id="G2-01", title="Вынести тексты в словари и выпустить английский язык с переключателем",
                description="Простой i18n: ru.json и en.json, функция t(), переключатель языка в настройках.")]


# ---------------------------------------------------------------- FB-005: решения → merge-map.json
def test_write_distinct_from_dry_run_text_and_json(tmp_path):
    out = drafts(tmp_path, {"G1": DUP[:1], "G2": DUP[1:]},
                 {"strategy": {"proposals_min": 1}, "registry": {"passes": 1}})
    # решение [ ] (похожи, но разные) из сохранённого вывода --dry-run
    (out / "build").mkdir(exist_ok=True)
    (out / "build" / "decisions.txt").write_text("  [ ] G2-01 «…» → G1-01 «…» (сходство 0.40; auto)\n", encoding="utf-8")
    r = run("merge_proposals.py", out, "--write-distinct", out / "build" / "decisions.txt")
    assert r.returncode == 0, r.stdout + r.stderr
    m = jload(out / "build" / "merge-map.json")
    assert m["distinct"] == [["G1-01", "G2-01"]] and m["merge"] == []
    # повторный запуск не дублирует; слияние уважает distinct без ручной правки файла
    assert run("merge_proposals.py", out, "--write-distinct", out / "build" / "decisions.txt").returncode == 0
    assert len(jload(out / "build" / "merge-map.json")["distinct"]) == 1
    r = run("merge_proposals.py", out)
    assert r.returncode == 0
    assert len(jload(out / "data" / "proposals.json")) == 2
    rep = jload(out / "build" / "merge-report.json")
    assert rep["registry_passes"] == 1
    # решение [x] в JSON → merge; пара уходит из distinct
    jdump(out / "build" / "merge-candidates.json", {"decisions": [{"drop": "G2-01", "keep": "G1-01", "merge": True}]})
    assert run("merge_proposals.py", out, "--write-distinct").returncode == 0
    m = jload(out / "build" / "merge-map.json")
    assert m["distinct"] == [] and m["merge"][0]["drop"] == "G2-01" and m["merge"][0]["into"] == "G1-01"
    assert run("merge_proposals.py", out).returncode == 0
    assert len(jload(out / "data" / "proposals.json")) == 1


def test_suggest_prints_decision_lines_readable_by_write_distinct(tmp_path):
    out = drafts(tmp_path, {"G1": DUP[:1], "G2": DUP[1:]}, {"strategy": {"proposals_min": 1}})
    s = run("merge_proposals.py", out, "--suggest")
    assert s.returncode == 0 and "Решения (отметьте [x]" in s.stdout
    (out / "build").mkdir(exist_ok=True)
    (out / "build" / "s.txt").write_text(s.stdout.replace("[x]", "[ ]"), encoding="utf-8")
    assert run("merge_proposals.py", out, "--write-distinct", out / "build" / "s.txt").returncode == 0
    assert jload(out / "build" / "merge-map.json")["distinct"] == [["G1-01", "G2-01"]]


# ---------------------------------------------------------------- потолок now по ёмкости
CAP_CFG = {"strategy": {"proposals_min": 1}, "registry": {"now_months": 3},
           "project": {"capacity": {"hours_per_week": 10, "dev_share": 0.7, "day_hours": 8}}}


def big_now(n=12):
    """n предложений now по ~12 дн.: сумма ≈ 144 дн. против ≈ 11,4 дн. ёмкости за 3 мес."""
    out = []
    for i, p in enumerate(regs(n, ["product", "analytics"]), 1):
        p.update(id="G1-%02d" % i, effort_days=[8, 16], scores={"value": 5 - (i % 4), "cost": 2, "risk": 2, "confidence": 3},
                 tags=["mvp"])
        out.append(p)
    out[3]["dependencies"] = ["G1-05"]
    return out


def test_cap_now_respects_capacity_and_prerequisites(tmp_path):
    out = drafts(tmp_path, {"G1": big_now()}, dict(CAP_CFG, mode="concept"))
    r = run("merge_proposals.py", out, "--cap-now")
    assert r.returncode == 0, r.stdout + r.stderr
    P = jload(out / "data" / "proposals.json")
    from capacity import capacity
    dev = capacity(CAP_CFG, 3)["dev_days"]
    now = [p for p in P if p["horizon"] == "now"]
    total = sum(sum(p["effort_days"]) / 2.0 for p in now)
    assert 0 < total <= dev * 1.3 + 1e-9                                      # критерий SM: «now» ≤ ёмкость × 1,3
    moved = [p for p in P if p["horizon"] == "next"]
    assert moved and all("ёмкость" in p["horizon_reason"] and "v1" in p["tags"] and "mvp" not in p["tags"] for p in moved)
    ids = {p["id"]: p for p in P}
    for p in now:                                                            # предпосылки остающихся тоже в now
        assert all(ids[d]["horizon"] == "now" for d in p["dependencies"])
    rep = jload(out / "build" / "merge-report.json")["cap_now"]
    assert rep["after_days"] == round(total, 1) and len(rep["demoted"]) == len(moved)
    assert "Ёмкость now (--cap-now)" in r.stdout
    c = run("check_registry.py", out)
    assert "ПРЕВЫШЕНИЕ" not in c.stdout and "Ёмкость now" in c.stdout


def test_cap_now_from_config_pins_owner_decisions_and_priority_categories(tmp_path):
    def setup(path, reg):
        cfg = dict(CAP_CFG, registry=dict(reg, now_months=6))               # ёмкость ≈ 22,8 дн., потолок ≈ 29,6 дн.
        props = big_now()
        props[11]["category"] = "retention"                                  # единственная retention — худшая по ценности
        props[11]["scores"] = {"value": 1, "cost": 5, "risk": 2, "confidence": 3}
        return drafts(path, {"G1": props}, cfg)

    # registry.capacity_cap → потолок без флага и минимумы «по приоритету»: редкая категория получает место в now
    out = setup(tmp_path / "prio", {"capacity_cap": True})
    assert run("merge_proposals.py", out).returncode == 0
    P = {p["id"]: p for p in jload(out / "data" / "proposals.json")}
    assert sum(sum(p["effort_days"]) / 2 for p in P.values() if p["horizon"] == "now") <= 22.8 * 1.3 + 0.1
    assert [p["horizon"] for p in P.values() if p["category"] == "retention"] == ["now"]
    # режим count (--cap-now без capacity_cap): только по ценности — retention не помещается
    out_c = setup(tmp_path / "count", {})
    assert run("merge_proposals.py", out_c, "--cap-now").returncode == 0
    Pc = {p["id"]: p for p in jload(out_c / "data" / "proposals.json")}
    assert [p["horizon"] for p in Pc.values() if p["category"] == "retention"] == ["next"]
    # решение владельца закрепляет предложение в now — --cap-now его не переносит
    moved = next(pid for pid, p in P.items() if p["horizon"] == "next")
    jdump(out / "data" / "decisions.json", {"bets": [], "horizons": [{"proposals": [moved], "horizon": "now", "tag": "mvp",
                                                                       "why": "владелец: обязательно в MVP"}]})
    r = run("merge_proposals.py", out)
    assert r.returncode == 0
    P2 = {p["id"]: p for p in jload(out / "data" / "proposals.json")}
    assert P2[moved]["horizon"] == "now" and "mvp" in P2[moved]["tags"]
    assert moved in jload(out / "build" / "merge-report.json")["cap_now"]["pinned"]


def test_no_cap_without_flag_or_config_is_unchanged(tmp_path):
    out = drafts(tmp_path, {"G1": big_now()}, CAP_CFG)
    assert run("merge_proposals.py", out).returncode == 0
    assert all(p["horizon"] == "now" for p in jload(out / "data" / "proposals.json"))
    assert jload(out / "build" / "merge-report.json")["cap_now"] is None
    c = run("check_registry.py", out)
    assert "ПРЕВЫШЕНИЕ" in c.stdout and "--cap-now" in c.stdout              # предупреждение с подсказкой


def test_slicing_queues_become_registry_entity(tmp_path):
    cfg = dict(CAP_CFG, slicing={"enabled": True, "queues": [{"id": "Q1", "name": "Ядро", "goal": "первая польза"},
                                                             {"id": "Q2", "name": "Удобство", "enter_when": "Q1 работает неделю"},
                                                             {"id": "Q3", "name": "Остальное"}]})
    out = drafts(tmp_path, {"G1": big_now()}, cfg)
    r = run("merge_proposals.py", out, "--cap-now")
    assert r.returncode == 0, r.stdout + r.stderr
    P = jload(out / "data" / "proposals.json")
    assert all(p.get("queue") in ("Q1", "Q2", "Q3") for p in P)
    assert all(p["horizon"] == "now" for p in P if p["queue"] == "Q1")
    assert all(p["horizon"] == "next" for p in P if p["queue"] != "Q1")
    q = jload(out / "build" / "merge-report.json")["cap_now"]["queues"]
    assert q["Q1"]["effort_days"] <= 11.4 * 1.3 and q["Q2"]["count"] >= 1 and q["Q3"]["count"] >= 1
    c = run("check_registry.py", out)
    rep = jload(out / "data" / "registry-check.json")
    assert set(rep["by_queue"]) == {"Q1", "Q2", "Q3"} and "Очереди:" in c.stdout
    assert run("score.py", out).returncode == 0
    assert all("queue" in s for s in jload(out / "data" / "scores.json"))
    # неизвестная очередь — ошибка проверки
    P[0]["queue"] = "Q9"
    jdump(out / "data" / "proposals.json", P)
    c = run("check_registry.py", out)
    assert c.returncode == 1 and "Q9" in c.stdout


# ---------------------------------------------------------------- решения владельца → горизонты
def test_decisions_sync_horizon_and_check(tmp_path):
    props = regs(4, ["product"])
    for p in props:
        p["tags"] = ["v1"]
        p["horizon"] = "next"
    out = make_out(tmp_path, props, {"strategy": {"proposals_min": 1}, "mode": "concept"})
    jdump(out / "data" / "decisions.json", {"bets": [], "forks": [
        {"id": "F1", "question": "3D сейчас?", "default": "v1", "decision": "v2", "apply": {"proposals": ["P002"], "horizon": "later", "tag": "later"}},
        {"id": "F2", "question": "без решения", "default": "x", "apply": {"proposals": ["P003"], "horizon": "now"}}]})
    c = run("check_registry.py", out)
    assert c.returncode == 1 and "P002: реестр расходится с решением владельца" in c.stdout and "--sync-decisions" in c.stdout
    assert "P003" not in c.stdout                                            # развилка без decision не применяется
    r = run("merge_proposals.py", out, "--sync-decisions")
    assert r.returncode == 0, r.stdout + r.stderr
    P = {p["id"]: p for p in jload(out / "data" / "proposals.json")}
    assert P["P002"]["horizon"] == "later" and P["P002"]["tags"] == ["later"] and "F1" in P["P002"]["horizon_reason"]
    assert P["P003"]["horizon"] == "next"
    assert run("check_registry.py", out, "--demo").returncode == 0           # --demo: минимумы категорий — предупреждения


# ---------------------------------------------------------------- патч _add
def test_overrides_add_appends_without_duplicates():
    t = {"id": "P038", "dependencies": ["P032"], "tags": ["a"]}
    mp.apply_patch(t, {"_add": {"dependencies": ["P033", "P032", "P038"], "tags": "b"}})
    assert t["dependencies"] == ["P032", "P033"] and t["tags"] == ["a", "b"]
    u = {"id": "P001"}
    mp.apply_patch(u, {"_add": {"dependencies": ["P002"]}, "horizon": "next"})
    assert u == {"id": "P001", "dependencies": ["P002"], "horizon": "next"}


# ---------------------------------------------------------------- FB-009 / SM А15: G8 из макетов
def test_append_g8_translates_refs_in_run_files(tmp_path):
    out = make_out(tmp_path, regs(3, ["product"]), {"strategy": {"proposals_min": 1}})
    jdump(out / "data" / "proposals-draft-G8.json", [proposal(0, id="G8-01", title="Свежесть данных на графике", description="Метка времени.",
                                                              evidence_class="D", evidence=[{"kind": "research", "url": None, "file": None,
                                                                                             "title": "макет", "note": "из макета M08", "checked": "2026-10-19"}])])
    (out / "mockups" / "concepts").mkdir(parents=True)
    (out / "mockups" / "concepts" / "M08-chart.html").write_text('<main data-proposals="P001 G8-01">G8-01, G8-019</main>', encoding="utf-8")
    (out / "design-refs").mkdir()
    jdump(out / "design-refs" / "08-chart.json", {"proposals": ["G8-01"], "hotspots": [{"proposal": "G8-01"}]})
    jdump(out / "data" / "fact-check.json", [{"fact": "РАСХОЖДЕНИЕ: P001 | M08", "note": "нужно G8-01"}])
    r = run("merge_proposals.py", out, "--append", "G8")
    assert r.returncode == 0, r.stdout + r.stderr
    html = (out / "mockups" / "concepts" / "M08-chart.html").read_text(encoding="utf-8")
    assert 'data-proposals="P001 P004"' in html and "G8-019" in html     # целый токен, неизвестный — без изменений
    assert jload(out / "design-refs" / "08-chart.json")["hotspots"][0]["proposal"] == "P004"
    assert "P004" in jload(out / "data" / "fact-check.json")[0]["note"]
    assert set(jload(out / "build" / "merge-report.json")["remapped_files"]) == {
        "mockups/concepts/M08-chart.html", "design-refs/08-chart.json", "data/fact-check.json"}
    assert run("check_registry.py", out, "--demo").returncode == 0
