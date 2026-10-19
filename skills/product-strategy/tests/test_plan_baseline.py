"""1.5: базовая линия плана и согласованность (FB-046), контракт Ганта на весь горизонт (SM 6.1), черновик резюме (FB-047),
черновик факт-листа и решений (FB-048, FB-049), одна ёмкость во всех файлах (FB-028), метки иллюстрации (FB-027),
шум чисел без метки и повторов (FB-030), канон демо-данных (SM 11) — pytest, без сети.

Запуск: python3 -m pytest skills/product-strategy/tests/test_plan_baseline.py -q
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import capacity  # noqa: E402
import plan_baseline  # noqa: E402

FILL = "<заполнить>"


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


GANTT = [
    {"id": "G01", "phase": "0. Валидация", "task": "Интервью и лист ожидания", "proposal_ids": ["P001"], "start_month": 1, "end_month": 1, "type": "task"},
    {"id": "G02", "phase": "2. Сборка MVP", "task": "Ядро продукта", "proposal_ids": ["P002", "P003"], "start_month": 2, "end_month": 3, "type": "task"},
    {"id": "G03", "phase": "3. Закрытая бета", "task": "Закрытая бета — 12.01.2027, первые 20 человек", "proposal_ids": ["P004"],
     "start_month": 4, "end_month": 4, "type": "milestone"},
    {"id": "G04", "phase": "4. Публичный запуск", "task": "Публичный запуск MVP", "proposal_ids": ["P005"], "start_month": 5, "end_month": 6,
     "type": "milestone"},
    {"id": "G05", "phase": "vision", "task": "Вторая платформа", "proposal_ids": ["P006"], "start_month": 13, "end_month": 24, "type": "task"},
]


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    out = tmp_path_factory.mktemp("plan") / "demo"
    assert run("make_concept_demo.py", out).returncode == 0
    cfg = jload(out / "build" / "run-config.json")
    cfg["strategy"].update({"horizon_months": 6, "vision_years": 2, "start_date": "2026-10-05"})
    cfg.setdefault("idea", {}).setdefault("facets", {})["hours_week"] = 15
    jdump(out / "build" / "run-config.json", cfg)
    jdump(out / "data" / "gantt.json", GANTT)
    jdump(out / "data" / "events.json", [{"date": "2026-12-10", "title": "Выход крупной игры", "kind": "релиз"},
                                         {"date": "2028-01-01", "title": "Вне горизонта", "kind": "релиз"}])
    jdump(out / "data" / "integration-options.json", {"options": [{"id": "A", "name": "Открытые данные", "days": [3, 5], "value": 4},
                                                                   {"id": "B", "name": "Официальный API", "days": [10, 20], "value": 5,
                                                                    "recommended": True}]})
    for cmd in (("score.py", out), ("model.py", out)):
        r = run(*cmd)
        assert r.returncode == 0, r.stdout + r.stderr
    return out


@pytest.fixture
def out(base, tmp_path):
    dst = tmp_path / "out"
    shutil.copytree(base, dst)
    return dst


def parts(out, body1="", body10="", body14=""):
    secs = []
    for n in range(1, 18):
        b = {1: body1, 10: body10, 14: body14}.get(n) or "Текст раздела %d." % n
        secs.append("## %d. Раздел %d\n%s" % (n, n, b))
    write(out / "build" / "parts" / "strategy-A.md", "\n\n".join(secs) + "\n")


def test_baseline_milestones_mvp_and_gantt_contract(out):
    r = run("plan_baseline.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    b = jload(out / "data" / "plan-baseline.json")
    ms = b["milestones"]
    assert ms["beta"]["month"] == 4 and ms["beta"]["date"] == "2027-01-12" and ms["beta"]["exact"] and ms["beta"]["id"] == "G03"
    assert ms["launch"]["month"] == 6 and ms["launch"]["date"] == "2027-03-01"          # даты в задаче нет — начало месяца
    assert ms["horizon_end"]["date"] == "2027-03-31"
    assert b["mvp"]["ids"] == ["P001", "P002", "P003", "P004", "P005"]
    tagged = {p["id"] for p in jload(out / "data" / "proposals.json") if "mvp" in (p.get("tags") or [])}
    assert set(b["mvp"]["only_in_registry"]) == tagged - set(b["mvp"]["ids"])
    cfg = jload(out / "build" / "run-config.json")
    assert b["capacity"]["dev_days"] == capacity.capacity(cfg, 6)["dev_days"] and b["capacity"]["line"] == capacity.capacity(cfg, 6)["line"]
    assert [e["title"] for e in b["events"]] == ["Выход крупной игры"] and b["events"][0]["month"] == 3
    assert b["architecture"]["id"] == "B"
    # контракт Ганта: все месяцы горизонта и видения (6 + 24), «дыра» 7–12 обнаружена
    gc = b["gantt_contract"]
    assert len(b["months"]) == 30 and [m["period"] for m in b["months"][:7]] == ["plan"] * 6 + ["gap"]
    assert gc["gap_months"][:6] == [7, 8, 9, 10, 11, 12] and not gc["ok"] and any("7–12" in m for m in gc["messages"])
    assert b["months"][3]["milestones"] == ["beta"] and b["months"][0]["capacity_days"] == capacity.capacity(cfg, 6)["dev_days_month"]
    # без «дыры» контракт выполнен
    g = json.loads(json.dumps(GANTT))
    g[-1]["start_month"] = 7
    g[-1]["end_month"] = 30
    jdump(out / "data" / "gantt.json", g)
    run("plan_baseline.py", out)
    assert jload(out / "data" / "plan-baseline.json")["gantt_contract"]["ok"] is True


def test_consistency_check_and_plan_placeholders(out):
    """FB-046: буквальные вехи, состав MVP и ёмкость против базовой линии; плейсхолдеры {plan:…} в сборке."""
    assert run("plan_baseline.py", out).returncode == 0
    parts(out,
          body1="Закрытая бета — {plan:beta}, публичный запуск — {plan:launch} [факт: plan-baseline]. Ёмкость: {plan:capacity}.",
          body10="**В MVP:** P001, P002, P009 [оценка].\n\nСостав по Ганту: {plan:mvp_ids}.",
          body14="Закрытая бета — 15.05.2027 [допущение].\n\nЁмкость — 72 дн. разработки за полгода [оценка].\n\nСчитаем день по 6 ч [допущение].")
    r = run("plan_baseline.py", out, "--check")
    assert r.returncode == 1, r.stdout                                  # D7 (1.5): код 1 — расхождения, последняя строка — сводка
    assert r.stdout.strip().splitlines()[-1].startswith("итог: расхождений с plan-baseline")
    rep = jload(out / "build" / "consistency-report.json")
    codes = {i["code"] for i in rep["issues"]}
    assert {"plan_mismatch", "mvp_mismatch", "capacity_mismatch", "workday_mismatch"} <= codes, rep["issues"]
    mm = next(i for i in rep["issues"] if i["code"] == "mvp_mismatch")
    assert mm["found"] == "P009" and mm["file"] == "build/parts/strategy-A.md"
    assert run("plan_baseline.py", out, "--check", "--strict").returncode == 1
    a = run("assemble_strategy.py", out)
    assert a.returncode == 0, a.stdout + a.stderr
    text = (out / "research" / "strategy.md").read_text(encoding="utf-8")
    assert "Закрытая бета — 12.01.2027, публичный запуск — март 2026" not in text
    assert "Закрытая бета — 12.01.2027" in text and "март 2027" in text and "P001, P002, P003, P004, P005" in text
    assert "{plan:" not in text and capacity.capacity(jload(out / "build" / "run-config.json"), 6)["line"] in text
    arep = jload(out / "build" / "assemble-report.json")
    assert arep["substituted"]["plan"] == 4 and arep["plan_consistency"]["baseline"] is True
    assert {"plan_mismatch", "mvp_mismatch", "workday_mismatch"} <= {w["code"] for w in arep["warnings"]}
    assert run("assemble_strategy.py", out, "--strict").returncode == 1
    lp = run("assemble_strategy.py", out, "--list-placeholders").stdout
    assert "{plan:beta}" in lp and "{plan:kill" not in lp                         # критериев отказа ещё нет (нет decisions.json)


def test_workday_checked_without_baseline(out):
    """FB-028: другое определение рабочего дня ловится и без plan-baseline (по capacity.py)."""
    parts(out, body14="Ёмкость считаем по 6-часовому дню [допущение].")
    write(out / "build" / "parts" / "strategy-A.md", (out / "build" / "parts" / "strategy-A.md").read_text(encoding="utf-8")
          .replace("по 6-часовому дню", "в 6-часовой день"))
    rep = jload(out / "build" / "assemble-report.json") if run("assemble_strategy.py", out).returncode == 0 else {}
    assert "workday_mismatch" in {w["code"] for w in rep["warnings"]}


def test_facts_draft_and_decisions_init(out):
    """FB-048/049: --draft создаёт черновик decisions.json; мест <заполнить> ≤ 5, у предложенных значений — источник."""
    assert run("plan_baseline.py", out).returncode == 0
    before = run("facts_scaffold.py", out, "--stdout").stdout
    assert before.count(FILL) > 10 and not (out / "data" / "decisions.json").exists()
    r = run("facts_scaffold.py", out, "--draft")
    assert r.returncode == 0, r.stderr
    d = jload(out / "data" / "decisions.json")
    assert d["draft"]["sources"] and len(d["bets"]) == 3 and all(b["kill"].get("date") for b in d["bets"])
    assert d["capacity"]["text"] == capacity.capacity(jload(out / "build" / "run-config.json"), 6)["line"]
    facts = (out / "build" / "strategy-facts.md").read_text(encoding="utf-8")
    body = facts.split("\n", 4)[-1]                                                   # без строки-описания каркаса
    assert body.count(FILL) <= 5, [ln for ln in body.splitlines() if FILL in ln]
    assert facts.count("[черновик:") >= 6 and "Черновик решений" in facts
    for b in d["bets"]:
        assert "«%s»" % b["name"] in facts
    assert "## Ёмкость и базовая линия плана" in facts and "`{plan:launch}`" in facts
    chk = run("decisions.py", out, "--check")
    assert chk.returncode == 0 and "черновик" in chk.stdout
    lp = json.loads(run("assemble_strategy.py", out, "--list-placeholders", "--json").stdout)
    v = {x["placeholder"]: x["value"] for x in lp}
    assert v["{bet:1.name}"] == d["bets"][0]["name"] and "{plan:kill.1.date}" not in v   # baseline построен до решений
    run("plan_baseline.py", out)
    lp = {x["placeholder"] for x in json.loads(run("assemble_strategy.py", out, "--list-placeholders", "--json").stdout)}
    assert "{plan:kill.1.date}" in lp
    parts(out)
    arep = json.loads(run("assemble_strategy.py", out, "--json").stdout)
    assert "decisions_draft" in {w["code"] for w in arep["warnings"]}
    # повторный --draft не трогает существующие решения
    d["draft"] = None
    jdump(out / "data" / "decisions.json", d)
    run("facts_scaffold.py", out, "--draft", "--force")
    assert jload(out / "data" / "decisions.json")["draft"] is None
    assert "[черновик:" not in (out / "build" / "strategy-facts.md").read_text(encoding="utf-8").split("## Три главные ставки")[1].split("## North")[0]


def test_summary_scaffold_uses_only_placeholders(out):
    """FB-047: раздел 1 из базовой линии и решений: числа и даты — плейсхолдеры; проверка согласованности без расхождений."""
    run("decisions.py", out, "--init", "--draft")
    run("plan_baseline.py", out)
    parts(out)
    (out / "build" / "parts" / "strategy-A.md").write_text(
        (out / "build" / "parts" / "strategy-A.md").read_text(encoding="utf-8").replace("## 1. Раздел 1\nТекст раздела 1.\n\n", ""), encoding="utf-8")
    r = run("summary_scaffold.py", out, "--to-part")
    assert r.returncode == 0, r.stderr
    part = (out / "build" / "parts" / "strategy-01.md").read_text(encoding="utf-8")
    assert part.startswith("## 1. Резюме") and "{plan:beta}" in part and "{plan:launch}" in part and "{bet:1.kill}" in part
    assert "{plan:mvp_ids}" in part and "{plan:capacity}" in part and FILL not in part
    import re
    literal = re.sub(r"\{[^{}]+\}|\[[^\]]*\]|P\d{3}|<!--.*?-->|\(\{deprank:P\d{3}\}\)", " ", part)
    assert not re.search(r"\d{2}\.\d{2}\.\d{4}|\d+[  ]?(?:₽|\$|%)", literal)     # ни одной буквальной даты, суммы или доли
    a = run("assemble_strategy.py", out)
    assert a.returncode == 0, a.stdout + a.stderr
    assert not [i for i in jload(out / "build" / "assemble-report.json")["plan_consistency"]["issues"] if i["file"].endswith("strategy-01.md")]
    run("summary_scaffold.py", out)                                                   # без --to-part — build/summary-draft.md (G10)
    assert (out / "build" / "summary-draft.md").exists() and not (out / "build" / "parts" / "strategy-summary.md").exists()
    run("plan_baseline.py", out, "--check")
    assert not [i for i in jload(out / "build" / "consistency-report.json")["issues"] if "summary" in i["file"] or "01" in i["file"]]


def test_illustration_labels_in_text(out):
    """FB-027: sensitivity-only — {model:…} итогов получают метку, буквальная выручка без метки — предупреждение (strict — ошибка)."""
    assert jload(out / "data" / "model.json")["mode"] == "sensitivity-only"
    parts(out, body1="Выручка базового сценария {model:base.net_revenue|money}, LTV {model:base.ltv|money}; валюта {model:currency}.",
          body10="Выручка около 23 500 ₽ за 12 мес. по модели.\n\nВыручка {model:opt.net_revenue|0} [иллюстрация при допущениях: model.py].")
    r = run("assemble_strategy.py", out)
    assert r.returncode == 0, r.stdout
    text = (out / "research" / "strategy.md").read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if ln.startswith("Выручка базового сценария"))
    assert line.count("[иллюстрация при допущениях]") == 1                            # одна метка на строку
    assert text.count("[иллюстрация при допущениях: model.py]") == 1 and "[иллюстрация при допущениях] [иллюстрация" not in text
    rep = jload(out / "build" / "assemble-report.json")
    ill = rep["illustration"]["unlabeled"]
    assert len(ill) == 1 and "23 500" in ill[0]["text"] and "illustration_unlabeled" in {w["code"] for w in rep["warnings"]}
    assert run("assemble_strategy.py", out, "--strict").returncode == 1


def test_unlabeled_noise_and_context_repeats(out):
    """FB-030: числа из факт-листа, плейсхолдеров, реестра рядом с P-id и таблиц с колонкой «Источник» — не шум; повтор — по контексту."""
    run("facts_scaffold.py", out)
    facts = (out / "build" / "strategy-facts.md").read_text(encoding="utf-8") + "\nЦена конкурента 777 ₽ [факт: сайт, 2026-10-01]\n"
    write(out / "build" / "strategy-facts.md", facts)
    p = jload(out / "data" / "proposals.json")
    p[0]["effect_kpi"] = [{"kpi": "активация", "direction": "up", "range": "30–45 %", "label": "оценка"}]
    jdump(out / "data" / "proposals.json", p)
    pid = p[0]["id"]
    body2 = ("Как в факт-листе, конкурент берёт 777 ₽.\n\n| Показатель | Значение | Источник |\n|---|---|---|\n| Цена | 990 ₽ | сайт |\n\n"
             "| %s | Мастер | 30–45 %% активации |\n\nМощность 80 %% и α = 5 %%.\n\nРеальный пропуск: рост на 17 %%.\n\n"
             "Средний чек аналогов 450 ₽ в месяц у лидеров рынка." % pid)
    body3 = "Средний чек аналогов 450 ₽ в месяц у лидеров ниши."
    write(out / "build" / "parts" / "strategy-A.md", "\n\n".join(
        "## %d. Раздел\n%s" % (n, {2: body2, 3: body3, 6: "Скидка 10 % на годовой тариф [оценка].", 7: "Отток 10 % в месяц [оценка]."}.get(n, "Текст."))
        for n in range(1, 18)) + "\n")
    r = run("assemble_strategy.py", out)
    assert r.returncode == 0, r.stdout
    rep = jload(out / "build" / "assemble-report.json")
    texts = [e["text"] for e in rep["unlabeled_numbers"]["examples"]]
    assert any("17 %" in t for t in texts) and not any("777" in t or "990" in t or "30–45" in t or "Мощность" in t for t in texts), texts
    nums = {x["value"]: x["sections"] for x in rep["repeats"]["numbers"]}
    assert nums.get("450₽") == [2, 3] and "10%" not in nums                            # «10 %» — разный контекст (скидка / отток)
    assert {"value": "10%", "sections": [6, 7]} in rep["repeats"]["numbers_value_only"]


def test_demo_canon(out):
    """SM 11: канон демо-данных до макетов — один набор чисел для всех агентов."""
    run("decisions.py", out, "--init", "--draft")
    run("plan_baseline.py", out)
    r = run("facts_scaffold.py", out, "--demo-canon", "--stdout")
    assert r.returncode == 0, r.stderr
    c = jload(out / "data" / "demo-canon.json")
    v = c["values"]
    assert v["plan.beta"]["value"] == "12.01.2027" and v["currency"]["value"] == "₽" and "bet.1.name" in v and "data-canon" in c["rule"]
    assert "## Канон демо-данных" in r.stdout
    c["values"]["custom"] = {"value": 1, "source": "владелец"}
    jdump(out / "data" / "demo-canon.json", c)
    run("facts_scaffold.py", out, "--demo-canon", "--stdout")
    assert "custom" in jload(out / "data" / "demo-canon.json")["values"]           # не перезаписывается
