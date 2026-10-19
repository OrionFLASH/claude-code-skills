"""Гант на весь горизонт (SM: «gantt.json допускает месяцы 1–6 и 13–24, месяцев 7–12 нет»): charts.py рисует границу «план | видение»
по горизонту прогона (run-config strategy.horizon_months, а не жёстко 12) и отмечает пробелы плана — месяцы без единой задачи —
элементом gap-<с>-<по> с пояснением; без пробелов график прежний. Страница (build_html.py) — test_site_interactive.py.
  python3 -m pytest skills/product-strategy/tests/test_charts_gantt_horizon.py -q
"""
import json
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))
import charts  # noqa: E402

G = [{"id": "G01", "phase": "MVP", "task": "Прототип", "start_month": 1, "end_month": 3, "type": "task"},
     {"id": "G02", "phase": "MVP", "task": "Запуск", "start_month": 6, "end_month": 6, "type": "milestone"},
     {"id": "G03", "phase": "vision", "task": "Вторая очередь", "start_month": 13, "end_month": 24, "type": "task"}]


def build(cfg):
    charts.REG.reset("gantt")
    res = charts.ch_gantt(G, cfg)
    els = dict(charts.REG.els)
    charts.REG.reset(None)
    return res, els


def test_horizon_from_run_config_and_gaps():
    (svg, title, cap), els = build({"strategy": {"horizon_months": 6}})
    assert charts.gantt_horizon({"strategy": {"horizon_months": 6}}) == 6 and charts.gantt_horizon({}) == 12
    assert charts.gantt_gaps(G, 24) == [(4, 5), (7, 12)]
    assert "после 6-го месяца" in cap and "4–5, 7–12" in cap
    assert "area-vision" in els and "gap-4-5" in els and "gap-7-12" in els
    assert 'data-ps-el="gap-7-12"' in svg and 'data-ps-el="area-vision"' in svg
    label = els["area-vision"]["label"] if isinstance(els["area-vision"], dict) else str(els["area-vision"])
    assert "месяцы 7–24" in json.dumps(els["area-vision"], ensure_ascii=False) or "месяцы 7–24" in label


def test_default_horizon_without_gaps_is_unchanged():
    full = [dict(g) for g in G]
    full[1]["start_month"] = 1                         # задачи на все месяцы 1–6, видение 13–24 → пробел только 7–12
    charts.REG.reset("gantt")
    _, _, cap = charts.ch_gantt(full + [{"id": "G04", "phase": "v1", "task": "v1", "start_month": 7, "end_month": 12}], {})
    els = dict(charts.REG.els)
    charts.REG.reset(None)
    assert not [k for k in els if k.startswith("gap-")] and "после 12-го месяца" in cap and "штриховка" not in cap


def test_concept_demo_meta_explains_gap(tmp_path):
    out = tmp_path / "idea"
    run = lambda *a: subprocess.run([sys.executable, str(SKILL / "scripts" / a[0])] + [str(x) for x in a[1:]], capture_output=True, text=True, timeout=300)
    assert run("make_concept_demo.py", out).returncode == 0
    r = run("charts.py", out, "--only", "gantt")
    assert r.returncode == 0 and "Проверка пояснений графиков: ок" in r.stdout, r.stdout[-1500:]
    meta = json.loads((out / "charts" / "gantt.meta.json").read_text(encoding="utf-8"))
    gap = meta["elements"]["gap-7-12"]
    assert gap["kind"] == "area" and gap["title"] == "Пробел плана: месяцы 7–12"
    assert "горизонт плана — 6 мес." in gap["meaning"] and any("data/gantt.json" in a for a in gap["actions"])
