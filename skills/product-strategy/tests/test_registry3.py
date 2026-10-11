"""Регрессия 1.4 (обратная связь прогонов QA Helper и «Слышно»): карта id и перевод ссылок G-NN, --append без
автослияния и решения из --dry-run, build/overrides.json, смысловые подсказки, неприменимые подшкалы, ничья на
медиане, защита typesafe_eval.py, gap_audit.py --remap (pytest, без сети).

Запуск: python3 -m pytest skills/product-strategy/tests/test_registry3.py -q
"""
import json
import shutil
import subprocess
import sys
import threading
from http.server import HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pipeline import FakeTypeSafe, jdump, jload, make_out, proposal, run  # noqa: E402
from test_registry2 import drafts, regs  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import merge_proposals as mp  # noqa: E402
import score  # noqa: E402
import typesafe_eval  # noqa: E402
import validate_scores  # noqa: E402

EV = [{"kind": "community", "url": "https://www.python.org/community/", "file": None, "title": "c", "note": "n", "checked": "2026-10-10"}]


def g7_drafts(base):
    return [proposal(0, id="G7-01", title=base[1]["title"], description=base[1]["description"] + " Дополнение.", evidence=EV),
            proposal(0, id="G7-02", title="Захостить публичное демо на статическом хостинге", description="Статическая сборка демо.",
                     dependencies=["P001"]),
            proposal(0, id="G7-03", title="Лицензия и открытие репозитория кода", description="Выбрать лицензию, открыть код.",
                     dependencies=["G7-02"]),
            proposal(0, id="G7-04", title="Песочница для отзывов о демо", description="Собрать отзывы после G7-02; связано с G7-99.",
                     steps=[{"what": "после G7-03 открыть форму", "where": "сайт", "how": "форма", "doc_url": None}])]


def appended(tmp_path, *extra):
    base = regs(5, ["product"])
    out = make_out(tmp_path, base)
    jdump(out / "data" / "proposals-draft-G7.json", g7_drafts(base))
    r = run("merge_proposals.py", out, "--append", "G7", *extra)
    return out, r


# ---------------------------------------------------------------- --append, карта id, ссылки
def test_append_default_no_merge_idmap_and_refs(tmp_path):
    out, r = appended(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    P = {p["id"]: p for p in jload(out / "data" / "proposals.json")}
    assert sorted(P) == ["P%03d" % i for i in range(1, 10)]                 # 5 + 4, ничего не влито
    assert "автослияние выключено" in r.stdout and "[ ] G7-01" in r.stdout
    rep = jload(out / "build" / "merge-report.json")
    assert rep["candidates"][0]["drop"] == "G7-01" and rep["candidates"][0]["keep"] == "P002"
    idm = jload(out / "build" / "id-map.json")
    assert idm == {"G7-01": "P006", "G7-02": "P007", "G7-03": "P008", "G7-04": "P009"}
    assert P["P008"]["dependencies"] == ["P007"]
    assert "после P007" in P["P009"]["description"] and "G7-99" in P["P009"]["description"]
    assert P["P009"]["steps"][0]["what"].startswith("после P008")
    assert any(u["ref"] == "G7-99" for u in rep["unresolved_refs"]) and "G7-99" in r.stdout
    c = run("check_registry.py", out, "--min", "1", "--demo")
    assert c.returncode == 1 and "ссылки на черновики G7-99" in c.stdout
    # повторный --append тех же черновиков ничего не дублирует, прежняя карта сохраняется
    r2 = run("merge_proposals.py", out, "--append", "G7")
    assert r2.returncode == 0 and r2.stdout.count("уже в реестре") == 4
    assert len(jload(out / "data" / "proposals.json")) == 9
    assert jload(out / "build" / "merge-report.json")["id_map"]["G7-03"] == "P008"


def test_append_dry_run_decisions_json_and_text(tmp_path):
    base = regs(5, ["product"])
    out = make_out(tmp_path / "a", base)
    jdump(out / "data" / "proposals-draft-G7.json", g7_drafts(base))
    shutil.copytree(out, tmp_path / "b")
    before = (out / "data" / "proposals.json").read_text(encoding="utf-8")
    d = run("merge_proposals.py", out, "--append", "G7", "--dry-run")
    assert d.returncode == 0 and (out / "data" / "proposals.json").read_text(encoding="utf-8") == before
    assert not (out / "build" / "id-map.json").exists()
    cand = jload(out / "build" / "merge-candidates.json")
    dec = next(x for x in cand["decisions"] if x["drop"] == "G7-01")
    assert dec["keep"] == "P002" and dec["merge"] is False
    dec["merge"] = True
    jdump(out / "build" / "merge-candidates.json", cand)
    r = run("merge_proposals.py", out, "--append", "G7", "--pairs-from-dry-run")
    assert r.returncode == 0, r.stdout + r.stderr
    P = {p["id"]: p for p in jload(out / "data" / "proposals.json")}
    assert len(P) == 8 and P["P002"]["merged_from"] == ["P002", "G7-01"]
    assert jload(out / "build" / "id-map.json")["G7-01"] == "P002"
    # текстовый вариант: сохранённый вывод --dry-run, отмечено [x]
    out2 = tmp_path / "b"
    d2 = run("merge_proposals.py", out2, "--append", "G7", "--dry-run")
    txt = d2.stdout.replace("[ ] G7-01", "[x] G7-01")
    (out2 / "build" / "decisions.txt").write_text(txt, encoding="utf-8")
    r2 = run("merge_proposals.py", out2, "--append", "G7", "--pairs-from-dry-run", out2 / "build" / "decisions.txt")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert {p["id"]: p for p in jload(out2 / "data" / "proposals.json")}["P002"]["merged_from"] == ["P002", "G7-01"]
    assert mp.load_decisions(out2 / "build" / "decisions.txt") == [("G7-01", "P002")]


def test_append_allow_merge_raised_threshold_and_category_guard(tmp_path):
    review = proposal(1, title="Просьба об оценке в приложении (In-App Review)", category="retention",
                      description="Показывать системный диалог оценки In-App Review после успешной расшифровки в приложении.")
    upd = proposal(0, id="G7-01", title="Обновление внутри приложения (in-app updates)", category="retention",
                   description="Показывать системный диалог обновления In-App Updates после запуска приложения.")
    out = make_out(tmp_path, [review])
    jdump(out / "data" / "proposals-draft-G7.json", [upd])
    sim = mp.Similarity([review, upd])
    assert mp.DEFAULT_THRESHOLD <= sim.score("P001", "G7-01") < mp.APPEND_THRESHOLD     # 1.2 слило бы (0,275)
    r = run("merge_proposals.py", out, "--append", "G7", "--allow-merge")
    assert r.returncode == 0 and len(jload(out / "data" / "proposals.json")) == 2
    # дубль из категории ниже минимума в другую категорию не вливается (минимумы — check_registry)
    base = regs(3, ["product"])
    out2 = make_out(tmp_path / "g", base, {"strategy": {"proposals_min": 100}})
    dup = proposal(0, id="G7-01", category="conversion", title=base[0]["title"], description=base[0]["description"])
    jdump(out2 / "data" / "proposals-draft-G7.json", [dup])
    r = run("merge_proposals.py", out2, "--append", "G7", "--allow-merge")
    rep = jload(out2 / "build" / "merge-report.json")
    assert not rep["merges"] and "ниже минимума" in rep["not_merged"][0]["reason"]
    assert len(jload(out2 / "data" / "proposals.json")) == 4


def test_full_merge_stable_ids_overrides_and_text_refs(tmp_path):
    g1 = [proposal(0, id="G1-01", title="Экспорт отчётов в табличный формат", description="Выгрузка; зависит от G2-01, см. G1-03.",
                   dependencies=["G2-01"], tags=["after:G2-01"],
                   evidence=[{"kind": "docs", "url": "https://docs.python.org/3/library/csv.html", "file": None, "title": "csv",
                              "note": "как в G1-02", "checked": "2026-10-10"}]),
          proposal(0, id="G1-02", title="Тёмная тема интерфейса", description="Переключатель темы."),
          proposal(0, id="G1-03", title="Голосовой ввод заметок в редакторе", description="Диктовка заметок.")]
    g2 = [proposal(0, id="G2-01", title="Календарь публикаций команды", description="Планирование выпусков."),
          proposal(0, id="G2-02", title="Голосовой ввод заметок в редакторе", description="Диктовка заметок голосом.")]
    out = drafts(tmp_path, {"G1": g1, "G2": g2}, {"strategy": {"proposals_min": 1}})
    r = run("merge_proposals.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    idm = jload(out / "build" / "id-map.json")
    assert set(idm) == {"G1-01", "G1-02", "G1-03", "G2-01", "G2-02"}
    assert idm["G1-03"] == idm["G2-02"]                                           # слитый → победитель
    P = {p["id"]: p for p in jload(out / "data" / "proposals.json")}
    a = P[idm["G1-01"]]
    assert a["dependencies"] == [idm["G2-01"]] and "зависит от %s, см. %s" % (idm["G2-01"], idm["G1-03"]) in a["description"]
    assert a["evidence"][0]["note"] == "как в %s" % idm["G1-02"] and a["tags"] == ["after:%s" % idm["G2-01"]]
    w = P[idm["G1-03"]]
    assert any(t.startswith("merged:G") for t in w["tags"])                      # провенанс не переводится
    assert run("check_registry.py", out, "--min", "1", "--demo").returncode == 0
    # ручные правки по P-id и по id черновика, удаление ключа; сохраняются при перезапуске слияния
    p2 = idm["G1-02"]
    P[p2]["scores"]["seo"] = 3
    jdump(out / "data" / "proposals.json", list(P.values()))
    jdump(out / "build" / "overrides.json", {
        "_comment": "ручные правки",
        p2: {"scores": {"value": 5, "_delete": ["seo"]}, "horizon": "later", "tags": ["ручная"]},
        "G2-01": {"cheap_test": "фейковая дверь", "_delete": ["segment"]}})
    jdump(out / "data" / "proposals-draft-G3.json", [proposal(0, id="G3-01", title="Публичный API для интеграций",
                                                              description="REST API.")])
    r = run("merge_proposals.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    P2 = {p["id"]: p for p in jload(out / "data" / "proposals.json")}
    idm2 = jload(out / "build" / "id-map.json")
    assert {k: idm2[k] for k in idm} == idm                                      # прежние номера сохранены
    assert idm2["G3-01"] == "P%03d" % (max(int(v[1:]) for v in idm.values()) + 1)
    assert P2[p2]["scores"]["value"] == 5 and "seo" not in P2[p2]["scores"] and P2[p2]["horizon"] == "later"
    assert P2[p2]["tags"] == ["ручная"]
    c = P2[idm["G2-01"]]
    assert c["cheap_test"] == "фейковая дверь" and "segment" not in c
    rep = jload(out / "build" / "merge-report.json")
    assert sorted(rep["overrides"]["applied"]) == sorted([p2, idm["G2-01"]])
    # --apply-overrides: патч калибровщика с _delete — к готовому реестру без слияния
    jdump(out / "build" / "calibration-patch.json", {idm["G1-01"]: {"scores": {"_delete": ["confidence"], "risk": 4}}})
    r = run("merge_proposals.py", out, "--apply-overrides", out / "build" / "calibration-patch.json")
    assert r.returncode == 0, r.stdout
    s = {p["id"]: p for p in jload(out / "data" / "proposals.json")}[idm["G1-01"]]["scores"]
    assert "confidence" not in s and s["risk"] == 4
    # --renumber: заново, прежняя карта — в id-map.prev.json
    r = run("merge_proposals.py", out, "--renumber")
    assert r.returncode == 0 and (out / "build" / "id-map.prev.json").exists()


def test_gap_deps_remap_on_append_and_gap_audit(tmp_path):
    base = regs(5, ["product"])
    out = make_out(tmp_path, base, {"strategy": {"proposals_min": 1}})
    jdump(out / "data" / "proposals-draft-G7.json", g7_drafts(base)[:3])
    # до слияния --check принимает ссылки на черновики G7 (предупреждение), неизвестные — ошибка
    (out / "research").mkdir()
    (out / "research" / "gap-audit.md").write_text("# А\n## Предпосылки\nP001\n## Пробелы\nнет\n## Конфликты\nнет\n", encoding="utf-8")
    jdump(out / "data" / "gap-audit-deps.json", {"P001": ["G7-02"], "G7-03": ["P002"]})
    c = run("gap_audit.py", out, "--check")
    assert c.returncode == 0 and "G7-02" in c.stdout and "--remap" in c.stdout, c.stdout
    jdump(out / "data" / "gap-audit-deps.json", {"P001": ["G7-02", "G7-55"]})
    assert run("gap_audit.py", out, "--check").returncode == 1
    jdump(out / "data" / "gap-audit-deps.json", {"P001": ["G7-02", "P003"], "G7-03": ["P002"]})
    r = run("merge_proposals.py", out, "--append", "G7")
    assert r.returncode == 0, r.stdout + r.stderr
    assert jload(out / "data" / "gap-audit-deps.json") == {"P001": ["P007", "P003"], "P008": ["P002"]}
    # gap_audit.py --remap: тот же перевод по карте; старые P-id не меняются; непереведённое — код 1
    jdump(out / "data" / "gap-audit-deps.json", {"P004": ["G7-01", "P005"], "G7-02": ["G7-77"]})
    g = run("gap_audit.py", out, "--remap")
    assert g.returncode == 1 and "G7-77" in g.stdout
    assert jload(out / "data" / "gap-audit-deps.json") == {"P004": ["P006", "P005"], "P007": ["G7-77"]}
    jdump(out / "data" / "gap-audit-deps.json", {"P004": ["G7-01"]})
    assert run("gap_audit.py", out, "--remap").returncode == 0
    assert jload(out / "data" / "gap-audit-deps.json") == {"P004": ["P006"]}


# ---------------------------------------------------------------- смысловые подсказки
SEM = [proposal(0, id="G1-01", title="Ярлыки PWA для быстрых действий", category="product", tags=["pwa"],
                description="Пункты быстрого запуска в иконке приложения: новая заметка, поиск."),
       proposal(0, id="G2-01", title="Добавить shortcuts в манифест веб-приложения", category="platform", tags=["pwa"],
                description="В manifest.json прописать shortcuts для частых сценариев."),
       proposal(0, id="G2-02", title="Просьба об оценке в приложении (In-App Review)", category="retention",
                description="Показывать системный диалог оценки In-App Review после успешной расшифровки в приложении."),
       proposal(0, id="G3-01", title="Обновление внутри приложения (in-app updates)", category="retention",
                description="Показывать системный диалог обновления In-App Updates после запуска приложения.")]


def test_semantic_hints_rank_above_lexical_without_merges(tmp_path):
    sim = mp.Similarity(SEM)
    assert sim.score("G1-01", "G2-01") < 0.1                                  # лексически не видно
    out = drafts(tmp_path, {"G1": SEM[:1], "G2": SEM[1:3], "G3": SEM[3:]})
    s = run("merge_proposals.py", out, "--suggest")
    assert s.returncode == 0
    sem_part, lex_part = s.stdout.split("Лексические пары", 1)
    assert "Смысловые кандидаты" in sem_part and "G1-01" in sem_part and "G2-01" in sem_part
    assert "G3-01" not in sem_part                                             # «оценка» ≠ «обновление»
    r = run("merge_proposals.py", out, "--dry-run")
    rep = jload(out / "build" / "merge-report.json")
    assert {(c["a"], c["b"]) for c in rep["semantic_candidates"]} == {("G1-01", "G2-01")}
    assert all(m["manual"] or {"G1-01", "G2-01"} != set([m["winner"]] + m["losers"]) for m in rep["merges"])
    assert any(d["source"].startswith("semantic") and d["merge"] is False
               for d in jload(out / "build" / "merge-candidates.json")["decisions"])
    # лексическое автослияние «оценка ↔ обновление» (0,29 ≥ 0,275) помечается как подозрительное
    assert any({w["a"], w["b"]} == {"G2-02", "G3-01"} for w in rep["semantic_warnings"]), rep["merges"]
    assert "разные объекты" in r.stdout


def test_semantic_no_new_automerges_on_reference_sets(tmp_path):
    """Те же наборы, что в test_registry2: число автослияний не изменилось (смысловой проход только подсказывает)."""
    base = regs(40, ["product"])
    out = drafts(tmp_path, {"G1": [dict(p, id="G1-%02d" % k) for k, p in enumerate(base, 1)]})
    run("merge_proposals.py", out)
    rep = jload(out / "build" / "merge-report.json")
    assert rep["merges"] == [] and len(jload(out / "data" / "proposals.json")) == 40


# ---------------------------------------------------------------- check_registry
def test_check_registry_draft_refs_and_na_subscales(tmp_path):
    p = [proposal(1, rationale="Как в G5-19", tags=["merged:G1-02"], merged_from=["G1-01", "G1-02"]),
         proposal(2, scores={"value": 4, "cost": 2, "risk": 2, "confidence": 4, "seo": None}, scores_na=["revenue"]),
         proposal(3, scores_na=["value", "foo"])]
    out = make_out(tmp_path, p)
    r = run("check_registry.py", out, "--min", "1", "--demo")
    assert r.returncode == 1
    assert "P001: ссылки на черновики G5-19 в rationale" in r.stdout
    assert "P002" not in r.stdout.split("Ошибки")[1]
    assert "'value' обязательна" in r.stdout and "'foo' не подшкала" in r.stdout


# ---------------------------------------------------------------- оценки: неприменимые подшкалы, медиана
def test_scores_na_excluded_from_value_index(tmp_path):
    a = proposal(1, scores={"value": 4, "cost": 2, "risk": 2, "confidence": 4, "revenue": 1, "seo": None}, scores_na=["revenue"])
    b = proposal(2, scores={"value": 4, "cost": 2, "risk": 2, "confidence": 4, "revenue": 1, "seo": 1})
    c = proposal(3, scores={"value": 4, "cost": 2, "risk": 2, "confidence": 4, "moat": 5}, scores_na=["moat"], horizon="later")
    out = make_out(tmp_path, [a, b, c])
    r = run("score.py", out)
    assert r.returncode == 0, r.stderr
    S = {s["id"]: s for s in jload(out / "data" / "scores.json")}
    assert S["P001"]["value_index"] == 4.0 and S["P002"]["value_index"] < 4.0     # исключены, а не подменены
    assert "strategic" not in S["P003"]["labels"]                                  # moat неприменима
    v = run("validate_scores.py", out)
    assert v.returncode == 0, v.stdout


def _rows_score(vals):
    rows = []
    for k, (vi, ci) in enumerate(vals, 1):
        rows.append({"id": "P%03d" % k, "rank": k, "value_index": vi, "cost_index": ci, "risk_index": 2.0, "value_per_effort": vi / ci,
                     "confidence_calc": 0.8, "_sub": {"moat": 3}, "_time_days": 10, "_money": 0, "_na": set()})
    return rows


def test_median_compare_rounded_in_both_scripts():
    W = score.DEFAULT_WEIGHTS
    m = 2.9265
    vals = [(m + 4e-16, 3.0), (m, 3.0), (m - 4e-16, 3.0), (1.0, 3.0), (4.0, 3.0)]   # медиана = 2.9265
    rows = score.classify(_rows_score(vals), {}, W)
    assert [r["quadrant"] for r in rows[:3]] == ["quick_win"] * 3                     # без round(x, 9) третье — filler
    vrows = {"P%03d" % k: {"value_index": vi, "cost_index": ci, "rank": k, "value_per_effort": vi / ci, "risk_index": 2.0,
                           "money": 0, "days": 10, "cost_raw": 2, "moat": 3, "confidence_calc": 0.8}
             for k, (vi, ci) in enumerate(vals, 1)}
    order = sorted(vrows)
    validate_scores.classify(vrows, order, {i: {} for i in order}, W)
    assert [vrows[i]["quadrant"] for i in order[:3]] == ["quick_win"] * 3
    assert "quadrant" in vrows["P003"]["near"]


def test_validate_tie_is_not_error(tmp_path):
    props = [proposal(i, scores={"value": v, "cost": 3, "risk": 2, "confidence": 3}) for i, v in enumerate([1, 2, 3, 4, 5], 1)]
    out = make_out(tmp_path, props)
    assert run("score.py", out).returncode == 0
    S = jload(out / "data" / "scores.json")
    med = next(s for s in S if s["id"] == "P003")                   # value_index на медиане
    med["quadrant"] = {"quick_win": "filler", "big_bet": "money_pit", "filler": "quick_win", "money_pit": "big_bet"}[med["quadrant"]]
    jdump(out / "data" / "scores.json", S)
    v = run("validate_scores.py", out)
    last = v.stdout.strip().splitlines()[-1]
    assert v.returncode == 0 and last.startswith("OK") and "ничьих 1 — не ошибка" in last, v.stdout
    far = next(s for s in S if s["id"] == "P005")
    far["quadrant"] = "money_pit"
    jdump(out / "data" / "scores.json", S)
    v = run("validate_scores.py", out)
    assert v.returncode == 1 and v.stdout.strip().splitlines()[-1].startswith("FAIL")


# ---------------------------------------------------------------- typesafe_eval.py
def ts_run(out, *args, env=None):
    e = {k: v for k, v in __import__("os").environ.items() if not k.startswith("TYPESAFE_")}
    e.update(env or {})
    return subprocess.run([sys.executable, str(SCRIPTS / "typesafe_eval.py"), str(out)] + [str(a) for a in args],
                          capture_output=True, text=True, env=e, stdin=subprocess.DEVNULL, timeout=120)


def test_typesafe_limit_zero_and_redo_confirmation(tmp_path):
    out = make_out(tmp_path, [proposal(i) for i in range(1, 5)])
    r = ts_run(out, "--limit", "0", "--dry-run")
    assert r.returncode == 2 and "--limit 0" in r.stderr and "не указывайте --limit" in r.stderr
    srv = HTTPServer(("127.0.0.1", 0), FakeTypeSafe)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    env = {"TYPESAFE_API_KEY": "k-test", "TYPESAFE_API_URL": "http://127.0.0.1:%d/v1" % srv.server_port}
    try:
        n0 = len(FakeTypeSafe.seen_auth)
        r = ts_run(out, "--limit", "2", env=env)
        assert r.returncode == 0 and "Будет запросов: 2" in r.stdout, r.stdout + r.stderr
        assert len(FakeTypeSafe.seen_auth) - n0 == 2
        r = ts_run(out, "--limit", "2", env=env)
        assert "Будет запросов: 0" in r.stdout and len(FakeTypeSafe.seen_auth) - n0 == 2
        r = ts_run(out, "--redo", env=env)                                     # без терминала и без --yes — стоп
        assert r.returncode == 2 and "--yes" in r.stderr and len(FakeTypeSafe.seen_auth) - n0 == 2
        d = ts_run(out, "--redo", "--dry-run", env=env)
        assert "Запросов было бы: 4" in d.stdout
        r = ts_run(out, "--redo", "--yes", "--limit", "1", env=env)
        assert r.returncode == 0 and "Будет запросов: 1" in r.stdout and len(FakeTypeSafe.seen_auth) - n0 == 3
    finally:
        srv.shutdown()

    class Tty:
        def __init__(self, ans):
            self.ans = ans

        def isatty(self):
            return True

        def readline(self):
            return self.ans

    assert typesafe_eval.confirm_redo(3, False, Tty("y\n")) is True
    assert typesafe_eval.confirm_redo(3, False, Tty("\n")) is False
    assert typesafe_eval.confirm_redo(3, True, None) is True
