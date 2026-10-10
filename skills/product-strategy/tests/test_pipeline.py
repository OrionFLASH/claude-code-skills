"""Сквозная проверка конвейера оценки product-strategy (pytest, без сети).

make_demo → check_registry (--demo) → score → validate_scores → model → charts → merge_proposals → typesafe_eval,
плюс крайние случаи: пустой реестр, одно предложение, ничьи, нет подшкал, неизвестная категория.
Запуск: python3 -m pytest skills/product-strategy/tests/test_pipeline.py -q
"""
import copy
import json
import os
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
QUADRANTS = {"quick_win", "big_bet", "filler", "money_pit"}
LABELS = {"important", "effective", "expensive", "risky", "fast", "slow", "strategic", "tempting_weak"}


def run(script, *args, env=None):
    """Запуск скрипта отдельным процессом; ключ TypeSafe из окружения тестов не наследуется."""
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    e.update(env or {})
    return subprocess.run([sys.executable, str(SCRIPTS / script)] + [str(a) for a in args],
                          capture_output=True, text=True, env=e, timeout=180)


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def jdump(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def proposal(i, **over):
    """Корректное по контракту предложение с реальными (не заглушечными) URL."""
    p = {
        "id": "P%03d" % i, "title": "Предложение номер %d" % i, "category": "product", "segment": "новые пользователи",
        "description": "Сделать функцию %d для пользователей." % i, "rationale": "Есть спрос.",
        "evidence": [{"kind": "docs", "url": "https://docs.python.org/3/library/json.html", "file": None,
                      "title": "Документация", "note": "пересказ", "checked": "2026-10-10"}],
        "evidence_class": "A", "current_feature": "нет",
        "effect_kpi": [{"kpi": "активация", "direction": "up", "range": "+1..3 %", "label": "оценка"}],
        "steps": [{"what": "шаг", "where": "репозиторий", "how": "так", "doc_url": None}],
        "dependencies": [], "effort_days": [2, 6], "cost_money": {"min": 0, "max": 100, "currency": "USD", "note": ""},
        "risks": {"legal": 1, "ip": 1, "platform": 1, "privacy": 1, "tech": 2, "reputation": 1, "note": ""},
        "time_to_first_result_days": 14, "cheap_test": "опрос", "scores": {"value": 4, "cost": 2, "risk": 2, "confidence": 4},
        "kano": "linear", "horizon": "now", "horizon_years": 0, "tags": [], "mockup": None, "source_group": "G1", "merged_from": [],
    }
    p.update(over)
    return p


def make_out(tmp, props, cfg=None):
    jdump(tmp / "data" / "proposals.json", props)
    jdump(tmp / "build" / "run-config.json", cfg or {"strategy": {"proposals_min": 1, "horizon_months": 12}, "tools": {"typesafe": "auto"}})
    return tmp


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    r = run("make_demo.py", out)
    assert r.returncode == 0, r.stderr
    return out


# ---------------------------------------------------------------- основной конвейер на демо
def test_check_registry_demo(demo):
    r = run("check_registry.py", demo, "--demo")
    assert r.returncode == 0, r.stdout + r.stderr
    rep = jload(demo / "data" / "registry-check.json")
    assert rep["ok"] and rep["total"] == 60 and rep["demo"] is True
    assert set(rep["evidence_classes"]) == set("ABCD")


def test_check_registry_rejects_placeholders(demo, tmp_path):
    out = make_out(tmp_path, jload(demo / "data" / "proposals.json"), jload(demo / "build" / "run-config.json"))
    r = run("check_registry.py", out)
    assert r.returncode == 1
    assert "example.com" in r.stdout


def test_score_validate(demo):
    r = run("score.py", demo)
    assert r.returncode == 0, r.stderr
    S = jload(demo / "data" / "scores.json")
    assert len(S) == 60 and [s["rank"] for s in S] == list(range(1, 61))
    for s in S:
        for k in ("id", "rank", "rice", "ice", "wsjf", "value_per_effort", "risk_adjusted", "confidence_calc", "composite",
                  "quadrant", "priority", "moscow", "labels", "typesafe"):
            assert k in s, k
        assert s["quadrant"] in QUADRANTS and s["priority"] in {"P0", "P1", "P2", "P3"}
        assert s["moscow"] in {"must", "should", "could", "wont"} and set(s["labels"]) <= LABELS
        assert 0 <= s["confidence_calc"] <= 1 and 0 <= s["composite"] <= 1
        if s["priority"] == "P0":
            assert s["quadrant"] in {"quick_win", "big_bet"}
        assert s["typesafe"] is None
    assert 1 <= sum(s["priority"] == "P0" for s in S) <= 9
    sens = jload(demo / "data" / "sensitivity.json")
    assert {"tornado", "top20_stability", "runs"} <= set(sens) and 0 <= sens["top20_stability"] <= 1
    assert {"param", "low_rank_shift", "high_rank_shift"} <= set(sens["tornado"][0])
    assert (demo / "data" / "scores.csv").read_text(encoding="utf-8").startswith("id,rank,")
    W = jload(demo / "data" / "weights.json")
    assert W["composite"] == {"rice": 0.30, "ice": 0.20, "wsjf": 0.25, "risk_adjusted": 0.25}
    v = run("validate_scores.py", demo)
    assert v.returncode == 0, v.stdout
    assert "OK" in v.stdout


def test_validate_detects_tampering(demo, tmp_path):
    for rel in ("data/proposals.json", "data/scores.json", "data/weights.json"):
        jdump(tmp_path / rel, jload(demo / rel))
    S = jload(tmp_path / "data/scores.json")
    S[5]["composite"] += 0.05
    S[7]["quadrant"] = "money_pit" if S[7]["quadrant"] != "money_pit" else "quick_win"
    jdump(tmp_path / "data/scores.json", S)
    r = run("validate_scores.py", tmp_path)
    assert r.returncode == 1 and "FAIL" in r.stdout


def test_weights_override(demo, tmp_path):
    out = make_out(tmp_path, jload(demo / "data" / "proposals.json"))
    wf = tmp_path / "w.json"
    jdump(wf, {"composite": {"rice": 1.0, "ice": 0.0, "wsjf": 0.0, "risk_adjusted": 0.0}})
    assert run("score.py", out, "--weights", wf).returncode == 0
    W = jload(out / "data" / "weights.json")
    assert W["composite"]["rice"] == 1.0 and W["composite"]["ice"] == 0.0
    S = jload(out / "data" / "scores.json")
    assert S[0]["n_rice"] == 1.0 and all(abs(s["composite"] - s["n_rice"]) < 1e-4 for s in S)  # composite = n(RICE)
    assert run("validate_scores.py", out).returncode == 0
    # повторный запуск без --weights берёт сохранённые веса, --reset-weights — встроенные
    run("score.py", out)
    assert jload(out / "data" / "weights.json")["composite"]["rice"] == 1.0
    run("score.py", out, "--reset-weights")
    assert jload(out / "data" / "weights.json")["composite"]["rice"] == 0.30


def test_model(demo):
    r = run("model.py", demo)
    assert r.returncode == 0, r.stderr
    params = demo / "build" / "model-params.json"
    assert params.exists()
    M = jload(demo / "data" / "model.json")
    assert set(M["scenarios"]) == {"pessimistic", "base", "optimistic"}
    for sc in M["scenarios"].values():
        assert {"assumptions", "funnel", "monthly", "cac", "ltv", "payback_months", "arpu", "churn", "roi"} <= set(sc)
        assert len(sc["monthly"]) == 12
        assert {"month", "users", "paying", "revenue", "cost"} <= set(sc["monthly"][0])
        assert all(a["label"] in ("факт", "оценка", "допущение") for a in sc["assumptions"].values())
        assert [f["stage"] for f in sc["funnel"]] == ["acquisition", "activation", "retention", "revenue", "referral"]
    base_users = M["scenarios"]["base"]["monthly"][-1]["users"]
    assert M["scenarios"]["pessimistic"]["monthly"][-1]["users"] < base_users < M["scenarios"]["optimistic"]["monthly"][-1]["users"]
    p = jload(params)
    p["scenarios"]["base"]["visitors_month"]["value"] *= 2
    jdump(params, p)
    assert run("model.py", demo).returncode == 0
    assert jload(demo / "data" / "model.json")["scenarios"]["base"]["monthly"][-1]["users"] > base_users
    p["revenue_model"] = {"value": "one_time", "label": "допущение", "note": ""}
    jdump(params, p)
    assert run("model.py", demo, "--months", 6).returncode == 0
    M2 = jload(demo / "data" / "model.json")
    assert M2["revenue_model"] == "one_time" and len(M2["scenarios"]["base"]["monthly"]) == 6


def svg_ok(path):
    root = ET.parse(path).getroot()
    assert root.tag.endswith("svg")
    for el in root.iter():
        for k, v in el.attrib.items():
            if k.endswith("href") or k == "src":
                assert "http" not in v, (path, k, v)
    txt = Path(path).read_text(encoding="utf-8")
    assert "@import" not in txt and "url(" not in txt
    return txt


def test_charts(demo):
    run("score.py", demo)
    run("model.py", demo)
    run("check_registry.py", demo, "--demo")
    r = run("charts.py", demo)
    assert r.returncode == 0, r.stderr
    idx = jload(demo / "charts" / "charts-index.json")
    keys = {e["key"] for e in idx}
    expected = {"effort-impact", "bubble", "metrics-heatmap", "radar-top10", "pareto", "tornado", "dist-category", "dist-evidence",
                "dist-horizon", "gantt", "funnel", "forecast-fan", "cac-ltv", "payback", "keywords-volume", "events-calendar",
                "competitors-heatmap"}
    assert expected <= keys
    svgs = list((demo / "charts").glob("*.svg"))
    assert len(svgs) >= len(expected)
    titles = {p["id"]: p["title"] for p in jload(demo / "data" / "proposals.json")}
    for e in idx:
        assert e["title"] and e["caption"] and e["section"] in {"scores", "registry", "plan", "model", "market"}
        assert e["svg"] == "charts/%s.svg" % e["key"]
        txt = svg_ok(demo / e["svg"])
        assert "…" not in txt, e["key"]
    # полные названия топа на матрице — без обрезки (переносы допустимы, поэтому сверяем по словам)
    S = jload(demo / "data" / "scores.json")
    mat = (demo / "charts" / "effort-impact.svg").read_text(encoding="utf-8")
    for s in S[:15]:
        for word in titles[s["id"]].split():
            assert word.replace("«", "").replace("»", "") in mat.replace("&#39;", "'")


def test_charts_tokens_palette(demo, tmp_path):
    for rel in ("data/scores.json", "data/proposals.json"):
        jdump(tmp_path / rel, jload(demo / rel))
    (tmp_path / "mockups").mkdir()
    (tmp_path / "mockups" / "tokens.css").write_text(":root{--color-primary:#5B21B6;--text:#111111;--bg:#ffffff}", encoding="utf-8")
    r = run("charts.py", tmp_path, "--only", "effort-impact")
    assert r.returncode == 0 and "tokens.css" in r.stdout
    assert "#5B21B6" in (tmp_path / "charts" / "effort-impact.svg").read_text(encoding="utf-8")


# ---------------------------------------------------------------- merge
def test_merge(tmp_path):
    g1 = [proposal(0, id="G1-01", title="Добавить шаблоны проектов на старте", description="Галерея шаблонов проектов для новых пользователей на первом экране", evidence_class="C"),
          proposal(0, id="G1-02", title="Еженедельный дайджест по почте", description="Письмо раз в неделю с итогами"),
          proposal(0, id="G1-03", title="Интеграция с мессенджером", description="Бот уведомлений", dependencies=["G1-01"], category="partnerships"),
          proposal(0, id="G1-04", title="Тариф для команд", description="Отдельный тариф с общими пространствами", category="monetization")]
    g2 = [proposal(0, id="G2-01", title="Добавить шаблоны проектов на старте", description="Галерея шаблонов проектов для новых пользователей на первом экране и в пустых состояниях",
                   evidence=[{"kind": "competitor", "url": "https://github.com/topics/templates", "file": None, "title": "Конкурент", "note": "пересказ", "checked": "2026-10-10"}],
                   evidence_class="A"),
          proposal(0, id="G2-02", title="Сводка недели в мессенджере", description="Итоги недели отправлять в мессенджер", category="retention"),
          proposal(0, id="G2-03", title="Тариф для команд", description="Отдельный тариф с общими пространствами", category="monetization")]
    jdump(tmp_path / "data" / "proposals-draft-G1.json", g1)
    jdump(tmp_path / "data" / "proposals-draft-G2.json", g2)
    jdump(tmp_path / "build" / "merge-map.json", {"merge": [{"drop": "G1-02", "into": "G2-02", "reason": "одна идея"}],
                                                   "distinct": [["G1-04", "G2-03"]]})
    r = run("merge_proposals.py", tmp_path)
    assert r.returncode == 0, r.stderr
    P = jload(tmp_path / "data" / "proposals.json")
    assert [p["id"] for p in P] == ["P%03d" % i for i in range(1, len(P) + 1)]
    assert len(P) == 5  # 7 черновиков − авто-дубль G1-01 − ручной G1-02; distinct сохранил оба тарифа
    by_orig = {(p["merged_from"] or [None])[0]: p for p in P}
    tpl = by_orig["G2-01"]
    assert tpl["merged_from"] == ["G2-01", "G1-01"] and tpl["evidence_class"] == "A"
    assert len(tpl["evidence"]) == 2  # доказательство дубля перенесено
    assert by_orig["G2-02"]["merged_from"] == ["G2-02", "G1-02"]
    integ = next(p for p in P if p["title"] == "Интеграция с мессенджером")
    assert integ["dependencies"] == [tpl["id"]]  # зависимость на слитый дубль → на держателя
    assert sum(1 for p in P if p["title"] == "Тариф для команд") == 2
    rep = jload(tmp_path / "build" / "merge-report.json")
    assert rep["loaded"] == 7 and rep["kept"] == 5 and len(rep["dropped"]) == 2
    assert rep["id_map"]["G1-01"] == tpl["id"]
    assert run("check_registry.py", tmp_path, "--min", "1", "--demo").returncode == 0
    dry = tmp_path / "dry"
    jdump(dry / "data" / "proposals-draft-G1.json", g1)
    assert run("merge_proposals.py", dry, "--dry-run").returncode == 0
    assert not (dry / "data" / "proposals.json").exists()


def test_merge_threshold(tmp_path):
    a = proposal(0, id="G1-01", title="Страницы сравнения с альтернативами", description="Лендинги X против Y для поиска")
    b = proposal(0, id="G2-01", title="Страницы сравнения с конкурентами", description="Лендинги X против Y для поисковых запросов")
    jdump(tmp_path / "data" / "proposals-draft-G1.json", [a])
    jdump(tmp_path / "data" / "proposals-draft-G2.json", [b])
    run("merge_proposals.py", tmp_path, "--threshold", "0.99", "--title-threshold", "0.99")
    assert len(jload(tmp_path / "data" / "proposals.json")) == 2
    run("merge_proposals.py", tmp_path, "--threshold", "0.3")
    assert len(jload(tmp_path / "data" / "proposals.json")) == 1


# ---------------------------------------------------------------- TypeSafe
def test_typesafe_skipped_without_key(demo):
    r = run("typesafe_eval.py", demo, "--force")
    assert r.returncode == 0
    J = jload(demo / "data" / "typesafe-jev.json")
    assert J["skipped"] and "TYPESAFE_API_KEY" in J["skipped"] and J["items"] == {}
    assert len(J["questions"]) >= 5
    r = run("typesafe_eval.py", demo, env={"TYPESAFE_API_KEY": "dummy-not-used"})
    assert r.returncode == 0 and "run-config" in jload(demo / "data" / "typesafe-jev.json")["skipped"]
    assert "dummy-not-used" not in r.stdout + r.stderr
    d = run("typesafe_eval.py", demo, "--dry-run", "--limit", "1")
    assert d.returncode == 0 and "P001" in d.stdout
    run("score.py", demo)
    assert all(s["typesafe"] is None for s in jload(demo / "data" / "scores.json"))


class FakeTypeSafe(BaseHTTPRequestHandler):
    """Локальная подмена API TypeSafe (127.0.0.1) — проверка разбора ответа без сети."""
    seen_auth = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeTypeSafe.seen_auth.append(self.headers.get("Authorization"))
        ans = {}
        for k, q in body["questions"].items():
            if q["type"] == "noul":
                ans[k] = {"noul": 0.7}
            elif q["type"] == "score":
                ans[k] = {"score": 2.5, "confidence": 0.8}
            else:
                ans[k] = {"choice": "linear", "probabilities": {"linear": 0.6, "must": 0.4}}
        data = json.dumps({"model": "jev-test", "answers": ans}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def test_typesafe_fake_server_not_mixed_into_composite(demo, tmp_path):
    out = make_out(tmp_path, jload(demo / "data" / "proposals.json"))
    run("score.py", out)
    before = {s["id"]: (s["composite"], s["rank"]) for s in jload(out / "data" / "scores.json")}
    srv = HTTPServer(("127.0.0.1", 0), FakeTypeSafe)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        r = run("typesafe_eval.py", out, "--limit", "3", env={"TYPESAFE_API_KEY": "secret-test-key",
                                                               "TYPESAFE_API_URL": "http://127.0.0.1:%d/v1/systemone" % srv.server_port})
    finally:
        srv.shutdown()
    assert r.returncode == 0, r.stderr
    assert "secret-test-key" not in r.stdout + r.stderr
    assert FakeTypeSafe.seen_auth and FakeTypeSafe.seen_auth[-1] == "Bearer secret-test-key"
    J = jload(out / "data" / "typesafe-jev.json")
    assert "secret-test-key" not in json.dumps(J)
    assert J["skipped"] is None and len(J["items"]) == 3 and J["model"] == "jev-test"
    it = J["items"]["P001"]
    assert it["p_success"] == 0.7 and it["impact"] == 3.5 and it["kano"] == "linear"
    run("score.py", out)
    S = jload(out / "data" / "scores.json")
    assert sum(1 for s in S if s["typesafe"]) == 3
    assert {s["id"]: (s["composite"], s["rank"]) for s in S} == before
    assert "ts_p_success" in (out / "data" / "scores.csv").read_text(encoding="utf-8").splitlines()[0]


# ---------------------------------------------------------------- крайние случаи
def full_chain(out, check_args=("--min", "1", "--demo")):
    res = {"check": run("check_registry.py", out, *check_args), "score": run("score.py", out)}
    res["validate"] = run("validate_scores.py", out)
    res["charts"] = run("charts.py", out)
    return res


def test_empty_registry(tmp_path):
    out = make_out(tmp_path, [], {"strategy": {"proposals_min": 100}})
    res = full_chain(out, ())
    assert res["check"].returncode == 1 and "0 < минимума 100" in res["check"].stdout
    assert res["score"].returncode == 0 and jload(out / "data" / "scores.json") == []
    assert res["validate"].returncode == 0
    assert res["charts"].returncode == 0
    assert jload(out / "charts" / "charts-index.json") == []


def test_single_proposal(tmp_path):
    out = make_out(tmp_path, [proposal(1)])
    res = full_chain(out)
    for k, r in res.items():
        assert r.returncode == 0, (k, r.stdout, r.stderr)
    S = jload(out / "data" / "scores.json")
    assert len(S) == 1 and S[0]["rank"] == 1 and S[0]["priority"] == "P0" and S[0]["quadrant"] == "quick_win"
    for e in jload(out / "charts" / "charts-index.json"):
        svg_ok(out / e["svg"])


def test_all_ties(tmp_path):
    out = make_out(tmp_path, [proposal(i) for i in (3, 1, 2, 5, 4, 7, 6, 10, 9, 8)])
    res = full_chain(out)
    for k, r in res.items():
        assert r.returncode == 0, (k, r.stdout, r.stderr)
    S = jload(out / "data" / "scores.json")
    assert [s["id"] for s in S] == ["P%03d" % i for i in range(1, 11)]  # ничья → по id
    assert len({s["composite"] for s in S}) == 1
    assert sum(s["priority"] == "P0" for s in S) == 2  # half_up(0,15·10) = 2
    sens = jload(out / "data" / "sensitivity.json")
    assert sens["top20_stability"] == 1.0


def test_missing_subscales_and_optional(tmp_path):
    a = proposal(1, scores={"value": 5, "cost": 1, "risk": 1, "confidence": 5})
    b = proposal(2, scores={"value": 2, "cost": 4, "risk": 3, "confidence": 2, "reach": 5, "moat": 5}, horizon="later")
    c = proposal(3, scores={"value": 3, "cost": 3, "risk": 2, "confidence": 3})
    for k in ("cost_money", "time_to_first_result_days"):
        c.pop(k)
    out = make_out(tmp_path, [a, b, c])
    r = run("check_registry.py", out, "--min", "1")
    assert r.returncode == 1 and "P003: нет поля cost_money" in r.stdout  # обязательные поля контракта
    for k, rr in (("score", run("score.py", out)), ("validate", run("validate_scores.py", out)), ("charts", run("charts.py", out))):
        assert rr.returncode == 0, (k, rr.stdout, rr.stderr)
    S = {s["id"]: s for s in jload(out / "data" / "scores.json")}
    assert S["P001"]["value_index"] == 5.0  # нет подшкал → индекс ценности = value
    assert "strategic" in S["P002"]["labels"]


def test_unknown_category(tmp_path):
    out = make_out(tmp_path, [proposal(1), proposal(2, category="space_travel")])
    r = run("check_registry.py", out, "--min", "1")
    assert r.returncode == 1 and "неизвестная категория 'space_travel'" in r.stdout
    for k, rr in (("score", run("score.py", out)), ("validate", run("validate_scores.py", out)), ("charts", run("charts.py", out))):
        assert rr.returncode == 0, (k, rr.stdout, rr.stderr)
    assert "space_travel" in (out / "charts" / "dist-category.svg").read_text(encoding="utf-8")


def test_registry_rules(tmp_path):
    good = [proposal(i, category=c) for i, c in enumerate(
        ["product"] * 30 + ["acquisition"] * 20 + ["conversion"] * 8 + ["retention"] * 8 + ["monetization"] * 8 +
        ["analytics"] * 6 + ["partnerships"] * 6 + ["localization"] * 5 + ["new_lines"] * 3 + ["platform"] * 6, 1)]
    out = make_out(tmp_path, good, {"strategy": {"proposals_min": 100}})
    r = run("check_registry.py", out)
    assert r.returncode == 0, r.stdout
    bad = copy.deepcopy(good)
    bad[0]["dependencies"] = ["P999"]
    bad[1]["evidence"][0]["note"] = "«" + " ".join(["слово"] * 16) + "»"
    bad[2]["horizon"] = "someday"
    bad[3]["id"] = bad[4]["id"]
    bad[5]["evidence"][0]["url"] = "ftp://example.org/x"
    bad[6]["category"] = "platform"   # product: 29 < 30
    for p in bad[10:51]:
        p["evidence_class"] = "D"     # A+B = 59 %
    jdump(out / "data" / "proposals.json", bad)
    r = run("check_registry.py", out)
    assert r.returncode == 1
    for frag in ("P999", "цитата 16 слов", "someday", "повторяющиеся id", "ftp://", "A+B", "категория product"):
        assert frag in r.stdout, frag
    # неприменимая категория пропускается
    cfg = {"strategy": {"proposals_min": 100, "categories_na": ["monetization"]}}
    no_money = [p for p in good if p["category"] != "monetization"] + [proposal(200 + i) for i in range(8)]
    make_out(out, no_money, cfg)
    r = run("check_registry.py", out)
    assert r.returncode == 0, r.stdout
    assert jload(out / "data" / "registry-check.json")["category_minimums"]["monetization"]["na"] is True
