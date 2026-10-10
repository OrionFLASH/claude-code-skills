"""Регрессия 1.1: слияние дублей, проверка реестра, зависимости и критический путь, аудит пробелов, новые графики,
валюты и профиль zero-budget-solo (pytest, без сети).

Запуск: python3 -m pytest skills/product-strategy/tests/test_registry2.py -q
Проверка на реальных черновиках (не входят в репозиторий — личные данные прогона): переменная PS_REAL_DRAFTS —
папка с proposals-draft-G1…G6.json (139 кандидатов); без неё тест пропускается.
"""
import copy
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pipeline import jdump, jload, make_out, proposal, run, svg_ok  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import merge_proposals as mp  # noqa: E402

CATS100 = (["product"] * 30 + ["acquisition"] * 20 + ["conversion"] * 8 + ["retention"] * 8 + ["monetization"] * 8 +
           ["analytics"] * 6 + ["partnerships"] * 6 + ["localization"] * 5 + ["new_lines"] * 3 + ["platform"] * 6)
# известные слияния реального прогона (feedback §4.1): 12 групп, 14 связей
REAL_GROUPS = [["G1-01", "G3-06", "G4-13"], ["G2-23", "G6-17"], ["G1-32", "G6-09"], ["G1-04", "G4-11", "G4-20"],
               ["G1-29", "G4-04"], ["G1-31", "G4-08"], ["G4-02", "G5-01"], ["G3-10", "G4-06"], ["G1-30", "G3-17"],
               ["G2-04", "G4-09"], ["G1-03", "G4-12"], ["G1-12", "G6-19"]]
TOPICS = ["экспорт отчётов в табличный формат", "тёмная тема интерфейса", "голосовой ввод заметок", "календарь публикаций",
          "импорт контактов из файла", "офлайн-режим просмотра", "горячие клавиши редактора", "шифрование резервных копий",
          "массовое переименование файлов", "интеграция с почтовым клиентом", "шаблоны документов юристов",
          "карта посещаемости страниц", "напоминания о дедлайнах", "статистика скорости печати", "редактор формул",
          "проверка орфографии", "виджет погоды", "трекер привычек", "конвертер единиц измерения", "генератор паролей",
          "сканер штрихкодов", "учёт расходов семьи", "планировщик поездок", "словарь синонимов", "таймер помидоро",
          "менеджер закладок", "сравнение версий текста", "журнал тренировок", "каталог рецептов", "подбор цветовой палитры",
          "распознавание чеков", "чат поддержки", "опросы для команды", "доска задач", "архив переписки", "экспорт в PDF",
          "облачная синхронизация", "мобильный клиент", "публичный API", "система плагинов"]


SYL = ["ка", "ло", "ми", "ну", "ре", "со", "ти", "фа", "хе", "цу", "бо", "да"]


def word(i, salt):
    """Уникальное «слово» из слогов: у разных i нет общих основ (дубли не находятся)."""
    k = i * 7 + salt * 131
    return "".join(SYL[(k // 12 ** j) % 12] for j in range(4)) + "р"


def regs(n, cats, **over):
    """n корректных предложений с попарно несвязанными названиями и описаниями."""
    out = []
    for i in range(1, n + 1):
        t = TOPICS[i - 1] if i <= len(TOPICS) else "%s %s" % (word(i, 1), word(i, 2))
        out.append(proposal(i, category=cats[(i - 1) % len(cats)], title="Добавить %s" % t,
                            description="%s %s %s." % (t, word(i, 3), word(i, 4)), **over))
    return out


# ---------------------------------------------------------------- сходство
def test_stem_and_similarity_basics():
    assert mp.stem("шаблонов") == mp.stem("шаблоны") == mp.stem("шаблон")
    assert mp.stem("installers") == mp.stem("installer")
    assert "сделать" not in mp.stems("Сделать английский интерфейс")
    props = [{"id": "a", "title": "Английский интерфейс с переключателем языка", "description": "Словари ru/en и переключатель"},
             {"id": "b", "title": "Выпустить английский язык интерфейса и переключатель", "description": "Вынести тексты в словари ru и en"},
             {"id": "c", "title": "Партнёрская программа для блогеров", "description": "Процент с продаж за приглашённых"}]
    sim = mp.Similarity(props)
    assert sim.score("a", "b") > 0.3 > sim.score("a", "c")
    parts = sim.parts(0, 1)
    assert set(mp.SIM_WEIGHTS) <= set(parts) and 0 <= parts["score"] <= 1


def drafts(tmp, groups, cfg=None):
    for g, items in groups.items():
        jdump(tmp / "data" / ("proposals-draft-%s.json" % g), items)
    if cfg:
        jdump(tmp / "build" / "run-config.json", cfg)
    return tmp


def test_merge_semantic_duplicates_and_report(tmp_path):
    a = proposal(0, id="G1-01", title="Английский интерфейс: словари и переключатель языка",
                 description="Вынести строки интерфейса в словари ru/en, функция t() и переключатель языка в шапке.", category="product")
    b = proposal(0, id="G2-01", title="Вынести тексты в словари и выпустить английский язык с переключателем",
                 description="Простой i18n: ru.json и en.json, функция t(), переключатель языка в настройках.", category="localization",
                 evidence=[{"kind": "docs", "url": "https://docs.python.org/3/library/json.html", "file": None, "title": "та же", "note": "дубль", "checked": "2026-10-10"},
                           {"kind": "competitor", "url": "https://www.mozilla.org/", "file": None, "title": "конкурент", "note": "у них есть", "checked": "2026-10-10"}])
    c = proposal(0, id="G2-02", title="Партнёрская программа для авторов обзоров", description="Процент с оплат за приглашённых.",
                 category="partnerships")
    out = drafts(tmp_path, {"G1": [a], "G2": [b, c]})
    r = run("merge_proposals.py", out)        # минимум 100: обе категории уже ниже минимума — слияние разрешено
    assert r.returncode == 0, r.stdout + r.stderr
    P = jload(out / "data" / "proposals.json")
    assert len(P) == 2
    merged = next(p for p in P if p["merged_from"])
    assert sorted(merged["merged_from"]) == ["G1-01", "G2-01"]
    urls = [e["url"] for e in merged["evidence"]]
    assert len(urls) == len(set(urls)) == 2           # объединение без дублей по url
    loser = [x for x in merged["merged_from"] if x != merged["merged_from"][0]][0]
    assert "merged:%s" % loser in merged["tags"]
    rep = jload(out / "build" / "merge-report.json")
    m = rep["merges"][0]
    assert m["score"] >= rep["threshold"] and m["reason"] and m["pairs"][0]["parts"]["title_cos"] > 0
    assert rep["category_counts"]["after"] and rep["dropped"][0]["reason"] == "similarity"
    # --suggest: только печать, файлы не меняются
    before = (out / "data" / "proposals.json").read_text(encoding="utf-8")
    s = run("merge_proposals.py", out, "--suggest", "--top", "3")
    assert s.returncode == 0 and "G1-01" in s.stdout and "Шаблон ручных пар" in s.stdout
    assert (out / "data" / "proposals.json").read_text(encoding="utf-8") == before
    # --dry-run: отчёт пишется, реестр нет
    (out / "data" / "proposals.json").unlink()
    assert run("merge_proposals.py", out, "--dry-run").returncode == 0
    assert not (out / "data" / "proposals.json").exists() and (out / "build" / "merge-report.json").exists()


def test_merge_keeps_category_minimum(tmp_path):
    """Дубль между product (ровно минимум) и retention (с запасом): победитель — product, минимум не падает."""
    base = regs(100, CATS100)
    for p in base:
        p["id"] = "G1-%03d" % int(p["id"][1:])
    dup_prod = base[0]                                   # product, ровно 30 из 30
    dup_ret = proposal(0, id="G2-001", category="retention", title=dup_prod["title"] + " и фильтры",
                       description=dup_prod["description"] + " С фильтрами.", evidence_class="A")
    dup_prod["evidence_class"] = "C"                     # у retention класс лучше, но категория product на минимуме
    out = drafts(tmp_path, {"G1": base, "G2": [dup_ret]}, {"strategy": {"proposals_min": 100}})
    r = run("merge_proposals.py", out)
    assert r.returncode == 0, r.stdout
    rep = jload(out / "build" / "merge-report.json")
    assert rep["merges"][0]["winner"] == "G1-001", rep["merges"]
    assert "минимум" in rep["merges"][0]["reason"]
    assert run("check_registry.py", out).returncode == 0
    # обе категории ровно на минимуме → не сливать, пометка в отчёте
    base2 = [p for p in copy.deepcopy(base)]
    ret = next(p for p in base2 if p["category"] == "retention")
    ret.update(title=dup_prod["title"] + " и фильтры", description=dup_prod["description"] + " С фильтрами.")
    out2 = drafts(tmp_path / "b", {"G1": base2}, {"strategy": {"proposals_min": 100}})
    r = run("merge_proposals.py", out2)
    rep = jload(out2 / "build" / "merge-report.json")
    assert not rep["merges"] and rep["not_merged"] and "минимум" in rep["not_merged"][0]["reason"]
    assert len(jload(out2 / "data" / "proposals.json")) == 100
    assert run("check_registry.py", out2).returncode == 0


def test_merge_manual_pairs(tmp_path):
    base = regs(100, CATS100)
    for p in base:
        p["id"] = "G1-%03d" % int(p["id"][1:])
    conv = [p for p in base if p["category"] == "conversion"]        # ровно 8 из 8
    prod = [p for p in base if p["category"] == "product"]
    conv[0]["evidence"].append({"kind": "competitor", "url": "https://www.mozilla.org/x", "file": None, "title": "к", "note": "н", "checked": "2026-10-10"})
    out = drafts(tmp_path, {"G1": base}, {"strategy": {"proposals_min": 100}})
    jdump(out / "build" / "pairs.json", {prod[0]["id"]: [conv[0]["id"]]})
    r = run("merge_proposals.py", out, "--pairs", out / "build" / "pairs.json")
    assert r.returncode == 0, r.stdout
    assert "роняет минимум conversion" in r.stdout
    rep = jload(out / "build" / "merge-report.json")
    assert rep["auto"] is False and rep["min_violations"][0]["category"] == "conversion"
    assert conv[0]["id"] in rep["min_violations"][0]["hint"]
    P = jload(out / "data" / "proposals.json")
    w = next(p for p in P if p["merged_from"])
    assert w["merged_from"] == [prod[0]["id"], conv[0]["id"]] and "merged:%s" % conv[0]["id"] in w["tags"]
    assert any(e["url"] == "https://www.mozilla.org/x" for e in w["evidence"])
    assert len(w["evidence"]) == 2                     # docs-ссылка совпала по url → не продублирована
    assert run("check_registry.py", out).returncode == 1   # ручное решение выполнено и честно роняет минимум
    # --pairs-winner auto: победитель — из категории на минимуме, check_registry зелёный
    out2 = drafts(tmp_path / "auto", {"G1": copy.deepcopy(base)}, {"strategy": {"proposals_min": 100}})
    jdump(out2 / "build" / "pairs.json", {prod[0]["id"]: [conv[0]["id"]]})
    r = run("merge_proposals.py", out2, "--pairs", out2 / "build" / "pairs.json", "--pairs-winner", "auto")
    rep = jload(out2 / "build" / "merge-report.json")
    assert rep["merges"][0]["winner"] == conv[0]["id"] and not rep["min_violations"]
    assert run("check_registry.py", out2).returncode == 0


def test_merge_append(tmp_path):
    base = regs(5, ["product"])
    out = make_out(tmp_path, base)
    g7 = [proposal(0, id="G7-01", title=base[1]["title"], description=base[1]["description"] + " Дополнение.",
                   evidence=[{"kind": "community", "url": "https://www.python.org/community/", "file": None, "title": "c", "note": "n", "checked": "2026-10-10"}]),
          proposal(0, id="G7-02", title="Захостить публичное демо на статическом хостинге", description="Статическая сборка демо.",
                   dependencies=["P001"]),
          proposal(0, id="G7-03", title="Лицензия и открытие репозитория кода", description="Выбрать лицензию, открыть код.",
                   dependencies=["G7-02"])]
    jdump(out / "data" / "proposals-draft-G7.json", g7)
    r = run("merge_proposals.py", out, "--append", "G7")
    assert r.returncode == 0, r.stdout + r.stderr
    P = {p["id"]: p for p in jload(out / "data" / "proposals.json")}
    assert sorted(P) == ["P001", "P002", "P003", "P004", "P005", "P006", "P007"]
    assert P["P002"]["merged_from"] == ["P002", "G7-01"] and len(P["P002"]["evidence"]) == 2
    assert P["P006"]["merged_from"] == [] and P["P006"]["dependencies"] == ["P001"]
    assert P["P007"]["dependencies"] == ["P006"]       # ссылка G7-02 → новый id
    assert run("check_registry.py", out, "--min", "1", "--demo").returncode == 0


@pytest.mark.skipif(not os.environ.get("PS_REAL_DRAFTS"), reason="нет PS_REAL_DRAFTS (реальные черновики не в репозитории)")
def test_merge_real_139(tmp_path):
    src = Path(os.environ["PS_REAL_DRAFTS"])
    for f in sorted(src.glob("proposals-draft-G*.json")):
        (tmp_path / "data").mkdir(exist_ok=True)
        shutil.copy(f, tmp_path / "data" / f.name)
    jdump(tmp_path / "build" / "run-config.json", {"strategy": {"proposals_min": 100}})
    r = run("merge_proposals.py", tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    rep = jload(tmp_path / "build" / "merge-report.json")
    assert rep["loaded"] == 139
    cl = {}
    for m in rep["merges"]:
        g = frozenset([m["winner"]] + m["losers"])
        for x in g:
            cl[x] = g
    found = sum(max(len(set(g) & cl.get(x, {x})) for x in g) - 1 for g in REAL_GROUPS)
    gt = {frozenset(p) for g in REAL_GROUPS for p in itertools.combinations(g, 2)}
    pred = {frozenset(p) for g in set(cl.values()) for p in itertools.combinations(sorted(g), 2)}
    false = pred - gt
    print("связей найдено %d из 14; пар предсказано %d, ложных %d" % (found, len(pred), len(false)))
    assert found >= 10 and len(false) <= 1
    assert run("check_registry.py", tmp_path).returncode == 0


# ---------------------------------------------------------------- check_registry
def test_check_registry_d_class_and_evidence_split(tmp_path):
    ext = proposal(1, evidence=[{"kind": "competitor", "url": "https://www.mozilla.org/", "file": None, "title": "к", "note": "н", "checked": "2026-10-10"}])
    own = proposal(2, evidence=[{"kind": "docs", "url": "https://github.com/owner/repo/blob/main/README.md", "file": None, "title": "README", "note": "н", "checked": "2026-10-10"}])
    code = proposal(3, evidence=[{"kind": "repo", "url": None, "file": "src/app.py:10", "title": "код", "note": "н", "checked": "2026-10-10"}])
    shot = proposal(4, evidence=[{"kind": "own_app", "url": None, "file": "mockups/current/home.png", "title": "скрин", "note": "н", "checked": "2026-10-10"}])
    d_ok = proposal(5, evidence_class="D", evidence=[{"kind": "research", "url": None, "file": None, "title": "вывод", "note": "из воронки следует", "checked": "2026-10-10"}])
    d_bad = proposal(6, evidence_class="D", evidence=[{"kind": "research", "url": None, "file": None, "title": "вывод", "note": "", "checked": "2026-10-10"}])
    out = make_out(tmp_path, [ext, own, code, shot, d_ok, d_bad],
                   {"strategy": {"proposals_min": 1}, "repo": {"remote": "owner/repo"}})
    r = run("check_registry.py", out, "--demo")
    rep = jload(out / "data" / "registry-check.json")
    assert not any("P005" in w for w in rep["warnings"])                  # D без url с рассуждением — норма
    assert any("P006" in w and "note" in w for w in rep["warnings"])      # D без рассуждения — предупреждение
    assert rep["ab_external_share"] == round(1 / 6, 4) and rep["ab_internal_share"] == round(3 / 6, 4)
    assert abs(rep["ab_share"] - (rep["ab_external_share"] + rep["ab_internal_share"])) < 1e-3
    assert any("внешних A+B" in w for w in rep["warnings"])               # 17 % < 40 %
    assert "внешние 17 %" in r.stdout


def test_check_registry_zero_budget_profile(tmp_path):
    cats = ["product"] * 30 + ["acquisition"] * 20 + ["conversion"] * 8 + ["retention"] * 8 + ["analytics"] * 6 + ["platform"] * 28
    props = [proposal(i, category=c) for i, c in enumerate(cats, 1)]
    cfg = {"strategy": {"proposals_min": 100, "profile": "zero-budget-solo", "markets": ["ru"]}}
    out = make_out(tmp_path, props, cfg)
    r = run("check_registry.py", out)
    assert r.returncode == 0, r.stdout
    cm = jload(out / "data" / "registry-check.json")["category_minimums"]
    for c in ("monetization", "partnerships", "localization", "new_lines"):
        assert cm[c]["optional"] is True and cm[c]["required"] == 0
    assert "по запросу" in r.stdout
    # запрошенная категория и неявные условия (платный тариф, несколько рынков) возвращают минимумы
    cfg["strategy"].update(categories_required=["partnerships"], paid_tier="yes", markets=["ru", "en"])
    make_out(out, props, cfg)
    r = run("check_registry.py", out)
    assert r.returncode == 1
    for frag in ("категория partnerships", "категория monetization", "категория localization"):
        assert frag in r.stdout
    assert "категория new_lines" not in r.stdout
    cfg["strategy"]["categories_na"] = ["partnerships", "monetization", "localization"]
    make_out(out, props, cfg)
    assert run("check_registry.py", out).returncode == 0


# ---------------------------------------------------------------- зависимости
def scored(out):
    r = run("score.py", out)
    assert r.returncode == 0, r.stderr
    return {s["id"]: s for s in jload(out / "data" / "scores.json")}, r


def test_dependencies_chain_bonus_and_validate(tmp_path):
    p = [proposal(1, scores={"value": 5, "cost": 1, "risk": 1, "confidence": 5}, dependencies=["P003"]),
         proposal(2, scores={"value": 4, "cost": 2, "risk": 2, "confidence": 4}),
         proposal(3, scores={"value": 2, "cost": 4, "risk": 3, "confidence": 2}, dependencies=["P004"]),
         proposal(4, scores={"value": 1, "cost": 5, "risk": 4, "confidence": 1}),
         proposal(5, scores={"value": 3, "cost": 3, "risk": 2, "confidence": 3})]
    out = make_out(tmp_path, p)
    S, r = scored(out)
    assert S["P001"]["blocked_by"] == ["P003", "P004"] or set(S["P001"]["blocked_by"]) == {"P003", "P004"}
    assert set(S["P004"]["unlocks"]) == {"P003", "P001"} and S["P002"]["blocked_by"] == [] and S["P002"]["unlocks"] == []
    assert S["P004"]["dep_rank"] < S["P003"]["dep_rank"] < S["P001"]["dep_rank"]      # не выше своей предпосылки
    assert S["P004"]["dep_bonus"] > 0 and S["P002"]["dep_bonus"] == 0
    assert S["P001"]["rank"] == 1                                                      # обычный ранг не меняется
    assert sorted(s["dep_rank"] for s in S.values()) == [1, 2, 3, 4, 5]
    cp = jload(out / "data" / "critical-path.json")
    assert cp["order"] == ["P004", "P003", "P001"] and ["P003", "P001"] in cp["edges"]
    assert all(S[i]["critical_path"] for i in cp["order"]) and not S["P002"]["critical_path"]
    assert "Критический путь" in r.stdout
    v = run("validate_scores.py", out)
    assert v.returncode == 0 and "зависимости: пересчитаны" in v.stdout, v.stdout
    bad = jload(out / "data" / "scores.json")
    bad[0]["dep_rank"], bad[1]["dep_rank"] = bad[1]["dep_rank"], bad[0]["dep_rank"]
    bad[2]["blocked_by"] = []
    jdump(out / "data" / "scores.json", bad)
    v = run("validate_scores.py", out)
    assert v.returncode == 1 and "dep_rank" in v.stdout and "blocked_by" in v.stdout
    # старые scores.json без полей зависимостей — валидатор не падает
    old = [{k: x for k, x in s.items() if k not in ("blocked_by", "unlocks", "dep_rank", "dep_bonus", "critical_path")}
           for s in jload(out / "data" / "scores.json")]
    run("score.py", out)
    old = [{k: x for k, x in s.items() if k not in ("blocked_by", "unlocks", "dep_rank", "dep_bonus", "critical_path")}
           for s in jload(out / "data" / "scores.json")]
    jdump(out / "data" / "scores.json", old)
    v = run("validate_scores.py", out)
    assert v.returncode == 0 and "до версии 1.1" in v.stdout


def test_dependency_cycle_is_broken_deterministically(tmp_path):
    p = [proposal(1, scores={"value": 5, "cost": 1, "risk": 1, "confidence": 5}, dependencies=["P002"]),
         proposal(2, scores={"value": 3, "cost": 3, "risk": 2, "confidence": 3}, dependencies=["P003"]),
         proposal(3, scores={"value": 2, "cost": 4, "risk": 2, "confidence": 2}, dependencies=["P001"]),
         proposal(4, dependencies=["P004"])]                          # самоссылка игнорируется
    out = make_out(tmp_path, p)
    run("check_registry.py", out, "--min", "1", "--demo")
    S, r = scored(out)
    assert "цикл зависимостей" in r.stdout
    cp = jload(out / "data" / "critical-path.json")
    assert cp["cycles"] == [["P001", "P002", "P003"]]
    # внутри цикла остаются связи «предпосылка выше по рангу»: снимаются P002→P001 и P003→P002
    assert sorted(map(tuple, cp["dropped_edges"])) == [("P002", "P001"), ("P003", "P002")]
    assert S["P003"]["blocked_by"] == ["P001"] and S["P001"]["blocked_by"] == []
    first = {k: v["dep_rank"] for k, v in S.items()}
    S2, _ = scored(out)
    assert {k: v["dep_rank"] for k, v in S2.items()} == first      # детерминированно
    assert run("validate_scores.py", out).returncode == 0
    assert jload(out / "data" / "registry-check.json")["dependency_cycles"] == [["P001", "P002", "P003"]]


def test_dependency_warning_top20_and_gap_deps(tmp_path):
    props = []
    for i in range(1, 71):
        v = 5 if i <= 20 else (3 if i <= 60 else 1)
        props.append(proposal(i, scores={"value": v, "cost": 6 - v, "risk": 2, "confidence": v}))
    props[0]["dependencies"] = ["P070"]                               # топ-1 зависит от последнего
    out = make_out(tmp_path, props)
    jdump(out / "data" / "gap-audit-deps.json", {"P002": ["P069", "P999"]})
    run("check_registry.py", out, "--min", "1")
    S, r = scored(out)
    assert S["P001"]["rank"] <= 20 and S["P070"]["rank"] > 60
    assert "ниже топ-60" in r.stdout and "P999" in r.stdout
    assert "P069" in S["P002"]["blocked_by"]                          # предпосылка из аудита
    cp = jload(out / "data" / "critical-path.json")
    assert {w["id"] for w in cp["warnings"]} == {"P001", "P002"}
    rc = jload(out / "data" / "registry-check.json")
    assert any("P001" in w for w in rc["dependency_warnings"])
    assert S["P070"]["dep_rank"] < S["P001"]["dep_rank"]
    assert run("validate_scores.py", out).returncode == 0
    assert "Зависимости:" in r.stdout.strip().splitlines()[-1]       # build_all видит последнюю строку


def test_no_dependencies_and_single(tmp_path):
    out = make_out(tmp_path, [proposal(1)])
    S, _ = scored(out)
    assert S["P001"]["dep_rank"] == 1 and S["P001"]["critical_path"] is False
    assert jload(out / "data" / "critical-path.json")["order"] == []
    assert run("validate_scores.py", out).returncode == 0
    keys = json.loads(run("charts.py", out, "--list-keys").stdout)
    assert keys["skipped"]["critical-path"].startswith("нет зависимостей")


# ---------------------------------------------------------------- аудит пробелов
def test_gap_audit_facts_and_check(tmp_path):
    p = [proposal(1, title="Страница-ответ про экспорт в PDF", description="Опубликовать страницу на сайте, ссылка на демо и репозиторий.",
                  dependencies=["P003"]),
         proposal(2, title="Бесплатный Wrapped", description="Перевести итоги года из Pro в бесплатный уровень."),
         proposal(3, title="Статический лендинг", description="Собрать лендинг.", horizon="next"),
         proposal(4, title="Захостить публичное демо", description="Статическая сборка демо на бесплатном хостинге.")]
    out = make_out(tmp_path, p, {"strategy": {"proposals_min": 1, "constraints": "один разработчик"}})
    scored(out)
    r = run("gap_audit.py", out, "--top", "4")
    assert r.returncode == 0, r.stderr
    F = jload(out / "data" / "gap-audit-facts.json")
    assert F["top_n"] == 4 and len(F["bets"]["items"]) == 3 and F["bets"]["rule"]
    top1 = next(t for t in F["top"] if t["id"] == "P001")
    assert top1["dependencies"] == ["P003"] and top1["blocked_by"] == ["P003"]
    assert any(x["id"] == "P002" and "бесплатн" in x["free_words"] for x in F["free_vs_paid"])
    assert {"categories", "evidence_classes", "ab_external_share"} <= set(F["coverage"])
    md = (out / "build" / "gap-audit-facts.md").read_text(encoding="utf-8")
    for h in ("## 1. Три главные ставки", "## 2. Топ-4", "## 4.", "## 7. Покрытие", "## 8. Вопросы аудитору"):
        assert h in md
    # --check: нет файла → ошибка; полный → ок; битый G7 и неизвестный P-id → ошибки
    assert run("gap_audit.py", out, "--check").returncode == 1
    (out / "research").mkdir()
    (out / "research" / "gap-audit.md").write_text("# Аудит\n## Предпосылки\nP001 нужен P003.\n## Пробелы\nнет хостинга\n## Конфликты\nнет\n",
                                                  encoding="utf-8")
    good = proposal(0, id="G7-01", title="Хостинг демо", dependencies=["P001"])
    jdump(out / "data" / "proposals-draft-G7.json", [good])
    jdump(out / "data" / "gap-audit-deps.json", {"P001": ["P004"]})
    c = run("gap_audit.py", out, "--check")
    assert c.returncode == 0, c.stdout
    bad = dict(good, id="X-1", evidence_class="Z")
    jdump(out / "data" / "proposals-draft-G7.json", [bad])
    (out / "research" / "gap-audit.md").write_text("# Аудит\n## Предпосылки\nP777\n## Пробелы\n", encoding="utf-8")
    c = run("gap_audit.py", out, "--check")
    assert c.returncode == 1
    for frag in ("Конфликты", "P777", "G7-NN", "класс доказательства"):
        assert frag in c.stdout, frag
    # фактура работает и без scores.json
    (out / "data" / "scores.json").unlink()
    r = run("gap_audit.py", out)
    assert r.returncode == 0 and "нет data/scores.json" in r.stdout


# ---------------------------------------------------------------- графики
def test_charts_list_keys_and_new_charts(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    r = run("charts.py", empty, "--list-keys")
    K = json.loads(r.stdout)
    assert r.returncode == 0 and K["available"] == [] and "gantt" in K["skipped"] and "фаза 7" in K["skipped"]["gantt"]
    assert not (empty / "charts").exists()                          # --list-keys ничего не строит
    out = tmp_path / "demo"
    assert run("make_demo.py", out).returncode == 0
    acq = next(p for p in jload(out / "data" / "proposals.json") if p["category"] == "acquisition")
    P = jload(out / "data" / "proposals.json")
    for p in P:
        if p["id"] == acq["id"]:
            p["tags"] = ["seo"]
    jdump(out / "data" / "proposals.json", P)
    keys0 = json.loads(run("charts.py", out, "--list-keys").stdout)
    assert "critical-path" in keys0["skipped"] and "gantt" in keys0["available"]
    run("score.py", out)
    run("model.py", out)
    K = jload(out / "data" / "keywords.json")
    for k in K:
        k["volume"] = None
    jdump(out / "data" / "keywords.json", K)
    C = jload(out / "data" / "competitors.json")
    first = list(C[0]["features"])[0]
    for x in C:
        x["features"]["own_channel_analytics"] = True                  # ключ без подписи → человекочитаемо
        if isinstance(x.get("features_labels"), dict):
            x["features_labels"].pop("own_channel_analytics", None)
    C[0].setdefault("features_labels", {})[first] = "Готовые шаблоны"   # подпись из features_labels
    jdump(out / "data" / "competitors.json", C)
    keys = json.loads(run("charts.py", out, "--list-keys").stdout)
    assert {"critical-path", "channel-mix", "kpi-tree", "keywords-clusters", "gantt"} <= set(keys["available"])
    assert "keywords-volume" in keys["skipped"]
    r = run("charts.py", out)
    assert r.returncode == 0, r.stderr
    idx = {e["key"]: e for e in jload(out / "charts" / "charts-index.json")}
    assert set(idx) == set(keys["available"])
    for k in ("critical-path", "channel-mix", "kpi-tree", "keywords-clusters"):
        txt = svg_ok(out / idx[k]["svg"])
        assert "…" not in txt and idx[k]["caption"]
    assert idx["critical-path"]["section"] == "plan" and idx["keywords-clusters"]["section"] == "market"
    assert idx["channel-mix"]["section"] == "registry" and idx["kpi-tree"]["section"] == "plan"
    heat = (out / "charts" / "competitors-heatmap.svg").read_text(encoding="utf-8")
    texts = re.findall(r">([^<]+)</text>", heat)                       # подписи переносятся по словам
    assert "own_channel_analytics" not in " ".join(texts) and "Own channel" in texts and "Готовые" in texts
    assert "SEO и поисковые страницы" in (out / "charts" / "channel-mix.svg").read_text(encoding="utf-8")
    jdump(out / "data" / "north-star.json", {"metric": "Еженедельно активные авторы"})
    run("charts.py", out, "--only", "kpi-tree")
    assert "Еженедельно активные авторы" in (out / "charts" / "kpi-tree.svg").read_text(encoding="utf-8")
    assert len(jload(out / "charts" / "charts-index.json")) == len(idx)      # --only сохраняет остальные
    (out / "data" / "gantt.json").unlink()
    assert "gantt" in json.loads(run("charts.py", out, "--list-keys").stdout)["skipped"]


# ---------------------------------------------------------------- модель: валюта и нулевой бюджет
def test_model_currency_and_hints(tmp_path):
    out = make_out(tmp_path, [proposal(1)], {"strategy": {"horizon_months": 12},
                                              "project": {"currency": "RUB", "price_hint": 390, "traffic_hint": 1000}})
    assert run("model.py", out).returncode == 0
    prm = jload(out / "build" / "model-params.json")
    assert prm["currency"] == "RUB" and prm["common"]["price_month"]["value"] == 390.0
    assert prm["common"]["price_month"]["label"] == "оценка"
    assert prm["scenarios"]["base"]["visitors_month"]["value"] == 1000 and prm["scenarios"]["optimistic"]["visitors_month"]["value"] == 3000
    assert prm["scenarios"]["base"]["fixed_cost_month"]["value"] == 13000.0          # 400 $ × 32 ≈ 13 000 ₽ (пресет)
    M = jload(out / "data" / "model.json")
    assert M["currency_symbol"] == "₽" and M["profile"] == "standard" and isinstance(M["scenarios"]["base"]["roi"], float)
    other = make_out(tmp_path / "x", [proposal(1)], {"project": {"currency": "XYZ"}})
    assert run("model.py", other).returncode == 0
    M = jload(other / "data" / "model.json")
    assert M["currency"] == "XYZ" and any("XYZ" in n for n in M["notes"])
    usd = make_out(tmp_path / "u", [proposal(1)])
    run("model.py", usd)
    sys.path.insert(0, str(SCRIPTS))
    import model
    assert jload(usd / "build" / "model-params.json")["common"] == model.DEFAULT_PARAMS["common"]   # standard/USD без изменений


def test_model_zero_budget_solo(tmp_path):
    props = [proposal(i, effort_days=[2, 6]) for i in range(1, 21)]
    out = make_out(tmp_path, props, {"strategy": {"horizon_months": 12, "profile": "zero-budget-solo", "proposals_min": 1},
                                     "project": {"currency": "RUB", "team_size": 1}})
    run("score.py", out)
    r = run("model.py", out)
    assert r.returncode == 0, r.stderr
    M = jload(out / "data" / "model.json")
    assert M["profile"] == "zero-budget-solo" and "solo" in M and M["capacity"] == M["solo"]["capacity"]
    for sc in M["scenarios"].values():
        assert sc["roi"] == "неприменимо (нулевой бюджет)" and sc["cac"] is None and sc["roi_note"]
        assert sc["assumptions"]["paid_share"]["value"] == 0.0
    b = M["solo"]["scenarios"]["base"]
    assert b["hours_per_activated"] > 0 and b["dev_hours"] == 12 * 12 * 6 and "time_breakeven_month" in b
    cap = M["capacity"]
    assert cap["dev_days_total"] == 144 and cap["p0_p1"]["count"] >= 1
    assert cap["p0_p1"]["fits_count"] + len(cap["p0_p1"]["not_fit_ids"]) == cap["p0_p1"]["count"]
    assert cap["p0_p1"]["order_by"] == "dep_rank"
    assert {"support_eats_revenue", "margin_after_support"} <= set(M["solo"]["support"])
    run("check_registry.py", out, "--demo")
    c = run("charts.py", out, "--only", "cac-ltv,payback")
    assert c.returncode == 0, c.stderr
    idx = {e["key"]: e for e in jload(out / "charts" / "charts-index.json")}
    assert "ч разработчика" in idx["cac-ltv"]["title"] and "CAC неприменим" in idx["cac-ltv"]["caption"]
    assert "по времени" in idx["payback"]["title"] and "₽" in idx["payback"]["title"]
    for k in ("cac-ltv", "payback"):
        svg_ok(out / idx[k]["svg"])
    # нет scores.json — capacity без списка, но модель строится
    (out / "data" / "scores.json").unlink()
    run("model.py", out)
    assert "skipped" in jload(out / "data" / "model.json")["capacity"]["p0_p1"]


def test_payback_caveat_small_numbers(tmp_path):
    out = make_out(tmp_path, [proposal(1)])
    run("model.py", out)
    prm = jload(out / "build" / "model-params.json")
    for sc in prm["scenarios"].values():
        sc["visitors_month"]["value"] = 300
        sc["fixed_cost_month"]["value"] = 5
    jdump(out / "build" / "model-params.json", prm)
    run("model.py", out)
    run("charts.py", out, "--only", "payback,cac-ltv")
    idx = {e["key"]: e for e in jload(out / "charts" / "charts-index.json")}
    assert "новых платящих" in idx["payback"]["title"] and "$" in idx["payback"]["title"]
