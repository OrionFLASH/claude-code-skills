"""Единый источник решений и сборка: decisions.py, плейсхолдеры {bet:…}/{model:…}/{exp:…} в assemble_strategy.py,
сверка буквальных порогов, числа без метки с адресами и --label-unlabeled, повторы между разделами, facts_scaffold из
decisions.json, collect_reports.py (pytest, без сети).

Запуск: python3 -m pytest skills/product-strategy/tests/test_decisions.py -q
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SKILL = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import decisions as dm  # noqa: E402

NB = " "


def run(script, *args):
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True, env=e, timeout=300)


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def jdump(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def write(p, text):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(text, encoding="utf-8")


KILL_DATE = (date.today() + timedelta(weeks=30)).isoformat()


def decisions_doc():
    d = jload(SKILL / "templates" / "decisions.example.json")
    d.pop("_comment")
    d["bets"][0]["kill"]["date"] = KILL_DATE
    d["bets"][0]["proposals"] = ["P001", "P002"]
    d["bets"][1]["proposals"] = ["P003"]
    d["bets"][2]["proposals"] = ["P004"]
    return d


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    out = tmp_path_factory.mktemp("dec") / "demo"
    for cmd in (("make_demo.py", out), ("score.py", out), ("charts.py", out), ("model.py", out)):
        r = run(*cmd)
        assert r.returncode == 0, "%s: %s" % (cmd[0], r.stdout + r.stderr)
    (out / "research" / "strategy.md").unlink()
    jdump(out / "data" / "decisions.json", decisions_doc())
    assert run("sample_size.py", out, "--add", "E01", "--baseline", "0.05", "--mde", "0.01", "--traffic", "2000").returncode == 0
    return out


@pytest.fixture
def out(base, tmp_path):
    dst = tmp_path / "out"
    shutil.copytree(base, dst)
    return dst


def parts(out, *sections):
    """Разделы 1…17: переданные тексты {N: body}, остальные — заготовки."""
    given = dict(sections)
    secs = ["## %d. Раздел %d\n%s" % (n, n, given.get(n, "Текст раздела.")) for n in range(1, 18)]
    write(out / "build" / "parts" / "strategy-A.md", "# Стратегия\n\n" + "\n\n".join(secs[:9]) + "\n")
    write(out / "build" / "parts" / "strategy-B.md", "\n\n".join(secs[9:]) + "\n")


def codes(rep, key="errors"):
    return {x["code"] for x in rep[key]}


# ---------------------------------------------------------------- decisions.py
def test_example_is_valid_and_formatting():
    d = decisions_doc()
    errs, warns = dm.validate(d, {"P001", "P002", "P003", "P004"})
    assert not errs, errs
    v = dm.decision_values(d)
    assert v["bet:1.kill"] == "доля активации ниже 33%s%% к %s" % (NB, dm.fmt_date(KILL_DATE))
    assert v["bet:1.kill.threshold"] == "33" + NB + "%" and v["bet:3.kill.threshold"] == "3" + NB + "оплат/нед."
    assert v["north_star"] == "еженедельно активные команды" and v["fork:F1.default"].startswith("нет до")
    assert v["anti_goals"].count(";") == 2 and v["bet:1.premortem.2"]
    assert dm.fmt_num(12345.6) == "12" + NB + "346" and dm.fmt_num(3.456) == "3,46" and dm.fmt_num(0.0612) == "0,061"
    assert dm.apply_format(0.065, "%1") == "6,5" + NB + "%" and dm.apply_format(1234.5, "money", "₽") == "1" + NB + "234" + NB + "₽"
    bad = dict(d, bets=[{"id": 1, "name": "", "kill": {"metric": "x", "threshold": 1.5, "date": "31.12.2026"}}], north_star={})
    errs, _ = dm.validate(bad)
    assert any("name" in e for e in errs) and any("YYYY-MM-DD" in e for e in errs) and any("доля" in e for e in errs)
    assert any("north_star" in e for e in errs)


def test_decisions_cli(out):
    (out / "data" / "decisions.json").unlink()
    assert run("decisions.py", out, "--check").returncode == 1
    r = run("decisions.py", out, "--init")
    assert r.returncode == 0, r.stderr
    d = jload(out / "data" / "decisions.json")
    p0 = [s["id"] for s in jload(out / "data" / "scores.json") if s.get("priority") == "P0"]
    assert d["bets"][0]["proposals"] and set(d["bets"][0]["proposals"]) <= set(p0) and d["capacity"]["team_size"] == 3
    assert run("decisions.py", out, "--init").returncode == 1                       # не перезаписывает
    assert run("decisions.py", out, "--check").returncode == 0
    lp = run("decisions.py", out, "--list-placeholders", "--json")
    keys = {x["placeholder"] for x in json.loads(lp.stdout)}
    assert {"{bet:1.kill}", "{north_star}", "{model:base.ltv}", "{exp:E01.n}"} <= keys
    assert run("decisions.py", out.parent / "nope", "--check").returncode == 2


# ---------------------------------------------------------------- assemble: подстановка
def test_assemble_substitutes_decisions_model_exp(out):
    parts(out, (1, "Ставка 1 «{bet:1.name}»: {bet:1.what}. Критерий отказа: {bet:1.kill}. North Star: {north_star}. [допущение]\n\n"
                   "LTV {model:base.ltv|money}, CAC {model:pess.cac}, платный CAC {model:base.cac_paid|money} [оценка: model.py].\n\n"
                   "Выборка {exp:E01.n} на группу, {exp:E01.weeks} нед.; критерий: {bet:1.kill.n} регистраций, "
                   "{bet:1.kill.weeks} нед., {bet:1.kill.status}.\n\nАнти-цели: {anti_goals}. Код `{bet:1.kill}` не трогаем."))
    r = run("assemble_strategy.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    text = (out / "research" / "strategy.md").read_text(encoding="utf-8")
    M = jload(out / "data" / "model.json")
    E = jload(out / "data" / "experiments.json")["experiments"][0]
    assert "«Активация за первую сессию»" in text and "доля активации ниже 33" + NB + "%" in text
    assert "North Star: еженедельно активные команды" in text
    assert "LTV %s" % dm.apply_format(M["scenarios"]["base"]["ltv"], "money", "$") in text
    assert "Выборка %s на группу, %s нед." % (dm.fmt_num(E["n_per_arm"]), E["weeks"]) in text
    assert "наблюдаем" in text and "`{bet:1.kill}`" in text and "{model:" not in text and "{exp:" not in text
    rep = jload(out / "build" / "assemble-report.json")
    assert rep["substituted"]["bet"] >= 6 and rep["substituted"]["model"] == 3 and rep["substituted"]["exp"] == 2
    assert rep["substituted"]["north_star"] == 1 and rep["substituted"]["anti_goals"] == 1
    assert {c["id"] for c in rep["kill_criteria"]} == {"K1", "K2", "K3"}
    assert "model_sensitivity_only" not in codes(rep, "warnings")                    # LTV/CAC — не прогноз выручки


def test_model_change_updates_all_mentions(out):
    parts(out, (1, "LTV {model:base.ltv|0} [оценка]."), (8, "Снова LTV {model:base.ltv|0} [оценка], выручка {model:base.net_revenue|0}."))
    assert run("assemble_strategy.py", out).returncode == 0
    text = (out / "research" / "strategy.md").read_text(encoding="utf-8")
    ltv0 = jload(out / "data" / "model.json")["scenarios"]["base"]["ltv"]
    assert text.count("LTV %s" % dm.fmt_num(ltv0, 0)) == 2
    rep = jload(out / "build" / "assemble-report.json")
    assert "model_sensitivity_only" in codes(rep, "warnings")                         # демо: данных об аудитории нет
    p = jload(out / "build" / "model-params.json")
    p["common"]["price_month"]["value"] = 30.0
    jdump(out / "build" / "model-params.json", p)
    assert run("model.py", out).returncode == 0
    ltv1 = jload(out / "data" / "model.json")["scenarios"]["base"]["ltv"]
    assert ltv1 != ltv0
    assert run("assemble_strategy.py", out).returncode == 0
    text = (out / "research" / "strategy.md").read_text(encoding="utf-8")
    assert text.count("LTV %s" % dm.fmt_num(ltv1, 0)) == 2 and "LTV %s " % dm.fmt_num(ltv0, 0) not in text


def test_unknown_placeholders_are_errors(out):
    parts(out, (2, "Плохо: {model:base.nope}, {bet:7.kill}, {exp:E99.n}, {model:base.ltv|xx}."))
    r = run("assemble_strategy.py", out)
    assert r.returncode == 1
    rep = jload(out / "build" / "assemble-report.json")
    errs = [e for e in rep["errors"] if e["code"] == "unknown_placeholder"]
    assert len(errs) == 4 and all(e["section"] == 2 for e in errs) and "--list-placeholders" in errs[0]["message"]
    (out / "data" / "decisions.json").unlink()
    parts(out, (1, "Ставка: {bet:1.name}."))
    r = run("assemble_strategy.py", out)
    assert r.returncode == 1 and "decisions.py <OUT> --init" in r.stdout
    assert run("assemble_strategy.py", out, "--lenient").returncode == 0


def test_list_placeholders(out):
    r = run("assemble_strategy.py", out, "--list-placeholders")
    assert r.returncode == 0 and "{bet:1.kill.weeks}" in r.stdout and "{model:base.users_last}" in r.stdout
    assert "{exp:E01.weeks}" in r.stdout and "{north_star.target}" in r.stdout
    rows = json.loads(run("assemble_strategy.py", out, "--list-placeholders", "--json").stdout)
    assert any(x["placeholder"] == "{model:optimistic.cac}" and x["source"] == "data/model.json" for x in rows)


# ---------------------------------------------------------------- assemble: сверка с decisions.json
def test_literal_mismatch_warns_and_strict_fails(out):
    parts(out, (1, "Критерий отказа ставки 1: активация ниже 30 %% к %s — останавливаем. [допущение]\n\n"
                   "Ставка 2 «Органическое привлечение»: критерий отказа — доля из поиска ниже 8 %% к 01.01.2030. [допущение]\n\n"
                   "Ставка 3: если оплат командного тарифа меньше 3 в неделю — закрываем ставку. [допущение]\n\n"
                   "North Star — «еженедельно активные пользователи», цель 5 000. [допущение]" % dm.fmt_date(KILL_DATE)))
    r = run("assemble_strategy.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    rep = jload(out / "build" / "assemble-report.json")
    mm = [w for w in rep["warnings"] if w["code"] == "decision_mismatch"]
    whats = {(m["bet"], m["what"]) for m in rep["decisions"]["mismatches"]}
    assert (1, "threshold") in whats and (2, "date") in whats and (None, "north_star.metric") in whats and (None, "north_star.target") in whats
    assert (2, "threshold") not in whats and (3, "threshold") not in whats and (1, "date") not in whats   # совпадающие значения — не ошибка
    assert all("build/parts/strategy-A.md:" in m["message"] for m in mm) and "{bet:1.kill}" in mm[0]["message"]
    assert run("assemble_strategy.py", out, "--strict").returncode == 1
    rep = jload(out / "build" / "assemble-report.json")
    assert "decision_mismatch" in codes(rep)


def test_unobservable_kill_criterion(out):
    d = jload(out / "data" / "decisions.json")
    d["bets"][2]["kill"]["date"] = (date.today() + timedelta(weeks=8)).isoformat()   # −25 % оплат за 8 недель не различить
    jdump(out / "data" / "decisions.json", d)
    parts(out)
    r = run("assemble_strategy.py", out)
    assert r.returncode == 0 and "kill_unobservable" in r.stdout
    rep = jload(out / "build" / "assemble-report.json")
    k3 = next(c for c in rep["kill_criteria"] if c["id"] == "K3")
    assert k3["status"] == "unobservable"
    assert run("assemble_strategy.py", out, "--strict").returncode == 1


# ---------------------------------------------------------------- числа без метки, повторы
def test_unlabeled_addresses_and_autolabel(out):
    parts(out, (5, "Конверсия вырастет на 15 % за квартал.\n\n| Метрика | Значение |\n|---|---|\n| Выручка | 500 $ |\n\n"
                   "Порог {bet:1.kill.threshold} задан в решениях.\n\nРост на 20 % [оценка: эксперимент]."))
    r = run("assemble_strategy.py", out)
    assert r.returncode == 0
    rep = jload(out / "build" / "assemble-report.json")
    ex = rep["unlabeled_numbers"]["examples"]
    assert rep["unlabeled_numbers"]["count"] == 2 and {e["section"] for e in ex} == {5}
    src = (out / "build" / "parts" / "strategy-A.md").read_text(encoding="utf-8").split("\n")
    for e in ex:
        assert e["file"] == "build/parts/strategy-A.md" and e["text"].split()[0] in src[e["line"] - 1]
    assert "build/parts/strategy-A.md:%d (раздел 5)" % ex[0]["line"] in r.stdout
    r = run("assemble_strategy.py", out, "--label-unlabeled")
    assert r.returncode == 0 and r.stdout.count("метка [допущение] добавлена") == 2
    src = (out / "build" / "parts" / "strategy-A.md").read_text(encoding="utf-8")
    assert "за квартал. [допущение]" in src and "| 500 $ [допущение] |" in src
    rep = jload(out / "build" / "assemble-report.json")
    assert rep["unlabeled_numbers"]["count"] == 0
    assert "[допущение]" in (out / "research" / "strategy.md").read_text(encoding="utf-8").split("## 5.")[1]
    r = run("assemble_strategy.py", out, "--label-unlabeled")
    assert "метка [допущение] добавлена" not in r.stdout                             # повторный запуск ничего не меняет


def test_repeats_between_sections(out):
    para = ("Активация новых пользователей в первую неделю определяет весь дальнейший рост продукта, поэтому мастер первого запуска "
            "и пример на готовых данных идут первыми в плане работ команды на ближайший квартал без исключений и отсрочек.")
    parts(out, (2, para + " Рост 12 % [оценка]."), (6, "Повторим: " + para), (3, "Доля 12 % [оценка]."), (9, "Совсем другой текст про удержание."))
    r = run("assemble_strategy.py", out)
    assert r.returncode == 0
    rep = jload(out / "build" / "assemble-report.json")
    pairs = rep["repeats"]["paragraphs"]
    assert len(pairs) == 1 and {pairs[0]["a"]["section"], pairs[0]["b"]["section"]} == {2, 6} and pairs[0]["similarity"] >= 0.9
    assert "repeated_text" in codes(rep, "warnings") and "раздел 2 ↔ раздел 6" in r.stdout
    # 1.5 (FB-030): общее число без общего контекста («Рост 12 %» и «Доля 12 %») — не повтор; прежний список — numbers_value_only
    assert {"value": "12%", "sections": [2, 3]} in rep["repeats"]["numbers_value_only"]
    assert not any(x["value"] == "12%" for x in rep["repeats"]["numbers"])


# ---------------------------------------------------------------- facts_scaffold и collect_reports
def test_facts_scaffold_uses_decisions(out):
    r = run("facts_scaffold.py", out, "--stdout")
    assert r.returncode == 0, r.stderr
    t = r.stdout
    assert "## Три главные ставки (из data/decisions.json)" in t and "«Активация за первую сессию»" in t
    assert "`{bet:1.kill}`: доля активации ниже 33" in t and "измеримость: наблюдаем" in t
    assert "**North Star Metric** `{north_star}`: еженедельно активные команды" in t and "| F1 |" in t
    assert "{model:base.ltv|money}" in t
    (out / "data" / "decisions.json").unlink()
    t = run("facts_scaffold.py", out, "--stdout").stdout
    assert "## Три главные ставки (заготовка)" in t and "decisions.py <OUT> --init" in t


REPORT_ITEM = """1. Файл, 12 предложений.
6. Расхождения с фактами входов: пробный период — 7 дней (strategy-facts.md) — 3 дня — https://example.com/pricing; тариф Pro — 9 $ — 12 $ — https://example.com/pro
7. Допущения: нет.
"""
REPORT_BLOCK = """# Отчёт
## Расхождения с фактами
- **Пробный период** — 7 дней — 5 дней — https://example.com/trial
- Офлайн у Rival 1 — нет (product-understanding.md:40) — есть — https://example.com/rival-1

## Допущения
- что-то 10 — 20 — 30 — 40
"""
REPORT_NONE = "Итог.\n\n## Расхождения с фактами\nнет\n"
REPORT_JSON = 'Без блока.\n\n```json\n{"discrepancies": [{"fact": "число тестов", "input_value": "120", "found_value": "96", "source": "tests/:1"}]}\n```\n'
REPORT_TABLE = "## 5. Расхождения с фактами\n| факт | во входах | нашёл | источник |\n|---|---|---|---|\n| Спикер | Спикер | Говорящий | ui.md:12 |\n"


def test_collect_reports(out):
    rd = out / "build" / "agent-reports"
    for name, text in (("registry-G1", REPORT_ITEM), ("competitors", REPORT_BLOCK), ("legal", REPORT_NONE), ("specs", REPORT_JSON),
                       ("table", REPORT_TABLE), ("silent", "Отчёт без расхождений вовсе.\n")):
        write(rd / (name + ".md"), text)
    jdump(out / "data" / "fact-check.json", [{"fact": "число тестов", "phase1_value": "120", "agent_value": "96", "source": "x",
                                              "resolved_value": "96", "note": ""}])
    r = run("collect_reports.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    doc = jload(out / "data" / "fact-check.candidates.json")
    reps = {x["agent"]: x for x in doc["reports"]}
    assert reps["registry-G1"]["format"] == "item" and reps["registry-G1"]["count"] == 2
    assert reps["competitors"]["count"] == 2 and reps["legal"]["found"] and reps["legal"]["count"] == 0
    assert reps["specs"]["format"] == "json" and reps["table"]["count"] == 1 and not reps["silent"]["found"]
    c = {x["fact"].lower(): x for x in doc["candidates"]}
    trial = c["пробный период"]
    assert trial["conflict"] and {v["value"] for v in trial["variants"]} == {"3 дня", "5 дней"} and trial["agents"] == ["competitors", "registry-G1"]
    assert trial["resolved_value"] is None and trial["status"] == "candidate" and trial["id"] == "FC001"
    assert c["тариф pro"]["agent_value"] == "12 $" and c["тариф pro"]["source"] == "https://example.com/pro"
    assert c["число тестов"]["known"] and c["число тестов"]["resolved_value"] == "96"
    assert c["спикер"]["agent_value"] == "Говорящий" and "что-то 10" not in c                # другой раздел отчёта не читается
    r = run("collect_reports.py", out, "--merge")
    fc = jload(out / "data" / "fact-check.json")
    assert len(fc) == 1 + 4 and all(x["resolved_value"] is None for x in fc[1:]) and "конфликт" in fc[1]["note"]
    r = run("collect_reports.py", out, rd / "legal.md", "--json")
    assert json.loads(r.stdout)["candidates"] == []
    assert run("collect_reports.py", out.parent / "nope").returncode == 2


def test_report_footer_referenced_by_briefs():
    footer = (SKILL / "templates" / "briefs" / "_report-footer.md").read_text(encoding="utf-8")
    assert "## Расхождения с фактами" in footer and "collect_reports.py" in footer
    import re
    assert not re.search(r"\{[A-Z][A-Z0-9_]*\}", footer)                              # без плейсхолдеров render_brief
    refs = [p.stem for p in (SKILL / "templates" / "briefs").glob("*.md") if "_report-footer.md" in p.read_text(encoding="utf-8") and p.stem != "_report-footer"]
    assert {"registry-generator", "research-competitors", "gap-audit"} <= set(refs)
