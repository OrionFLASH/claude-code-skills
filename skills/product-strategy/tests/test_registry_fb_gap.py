"""1.5, WP-C: аудит пробелов — SyntaxWarning (FB-019), черновики G7 без ложных «нет merged_from» (FB-020), понятный
--remap (FB-021), автоперенос зависимостей от G7 из текста аудита и unlocks (SM 6.1), ёмкость в фактуре.

Запуск: python3 -m pytest skills/product-strategy/tests/test_registry_fb_gap.py -q
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pipeline import jdump, jload, make_out, proposal, run  # noqa: E402
from test_registry2 import regs  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
AUDIT_MD = "# Аудит\n## Предпосылки\nP001 нужен P003.\n## Пробелы\nнет\n## Конфликты\nнет\n"


def test_all_scripts_compile_without_syntax_warning():
    """FB-019: python3 -W error::SyntaxWarning -m py_compile scripts/*.py проходит."""
    files = sorted(str(p) for p in SCRIPTS.glob("*.py"))
    r = subprocess.run([sys.executable, "-W", "error::SyntaxWarning", "-c",
                        "import sys\nfor f in sys.argv[1:]:\n    compile(open(f, encoding='utf-8').read(), f, 'exec')"] + files,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    g = run("gap_audit.py", "--help")
    assert g.returncode == 0 and "SyntaxWarning" not in g.stderr


def test_g7_drafts_have_no_merged_from_warnings(tmp_path):
    """FB-020: черновики G7 без merged_from/source_group (как велит бриф) — без предупреждений; заполненный — предупреждение."""
    out = make_out(tmp_path, regs(4, ["product"]), {"strategy": {"proposals_min": 1}})
    (out / "research").mkdir()
    (out / "research" / "gap-audit.md").write_text(AUDIT_MD, encoding="utf-8")
    drafts = []
    for i in range(1, 5):
        p = proposal(0, id="G7-0%d" % i, title="Пробел номер %d" % i)
        p.pop("merged_from")
        p.pop("source_group")
        drafts.append(p)
    jdump(out / "data" / "proposals-draft-G7.json", drafts)
    c = run("gap_audit.py", out, "--check")
    assert c.returncode == 0, c.stdout
    assert "merged_from" not in c.stdout and "source_group" not in c.stdout
    drafts[0]["merged_from"] = ["G7-01", "G1-02"]
    jdump(out / "data" / "proposals-draft-G7.json", drafts)
    c = run("gap_audit.py", out, "--check")
    assert c.returncode == 0 and "заполнен merged_from" in c.stdout


def test_remap_message_distinguishes_nothing_to_do(tmp_path):
    """FB-021: после --append ссылок на черновики нет — «уже переведены», а не «переведено 0»."""
    base = regs(4, ["product"])
    out = make_out(tmp_path, base, {"strategy": {"proposals_min": 1}})
    jdump(out / "data" / "proposals-draft-G7.json", [proposal(0, id="G7-01", title="Захостить публичное демо", description="Хостинг.")])
    jdump(out / "data" / "gap-audit-deps.json", {"P001": ["G7-01"]})
    assert run("merge_proposals.py", out, "--append", "G7").returncode == 0
    assert jload(out / "data" / "gap-audit-deps.json") == {"P001": ["P005"]}
    r = run("gap_audit.py", out, "--remap")
    assert r.returncode == 0
    assert "уже переведены merge_proposals.py" in r.stdout and "переведено ссылок 0" not in r.stdout
    jdump(out / "data" / "gap-audit-deps.json", {"P002": ["G7-01"], "P003": ["P001"]})
    r = run("gap_audit.py", out, "--remap")
    assert r.returncode == 0 and "переведено ссылок 1 из 1" in r.stdout
    assert jload(out / "data" / "gap-audit-deps.json") == {"P002": ["P005"], "P003": ["P001"]}


def test_g7_dependencies_from_audit_text_and_unlocks_are_transferred(tmp_path):
    """SM 6.1: «P013 ← G7-02» в research/gap-audit.md и unlocks черновика попадают в gap-audit-deps.json и blocked_by."""
    base = regs(5, ["product"])
    out = make_out(tmp_path, base, {"strategy": {"proposals_min": 1}})
    (out / "research").mkdir()
    (out / "research" / "gap-audit.md").write_text(
        "# Аудит\n## Предпосылки\n| предложение | предпосылка | почему |\n|---|---|---|\n| P004 | G7-01 | без демо нет витрины |\n"
        "| Ставка 1 (P002, P003) | G7-01 | неоднозначно — пропускается |\n\nP001 ← G7-02, P005\n"
        "## Пробелы\nG7-01, G7-02\n## Конфликты\nнет\n", encoding="utf-8")
    g7 = [proposal(0, id="G7-01", title="Захостить публичное демо", description="Статическое демо."),
          proposal(0, id="G7-02", title="Лицензия и открытие кода", description="Выбрать лицензию.", unlocks=["P003"])]
    jdump(out / "data" / "proposals-draft-G7.json", g7)
    r = run("merge_proposals.py", out, "--append", "G7")
    assert r.returncode == 0, r.stdout + r.stderr
    deps = jload(out / "data" / "gap-audit-deps.json")
    assert deps == {"P004": ["P006"], "P001": ["P007", "P005"], "P003": ["P007"]}, deps
    assert "дописано из текста аудита" in r.stdout
    rep = jload(out / "build" / "merge-report.json")
    assert len(rep["gap_audit_deps"]["added_from_text"]) == 4
    # повторный --append/--remap не дублирует
    assert run("gap_audit.py", out, "--remap").returncode == 0
    assert jload(out / "data" / "gap-audit-deps.json") == deps
    # score.py видит предпосылки (blocked_by), --check доволен
    assert run("score.py", out).returncode == 0
    S = {s["id"]: s for s in jload(out / "data" / "scores.json")}
    assert "P007" in S["P001"]["blocked_by"] and "P006" in S["P004"]["blocked_by"]
    assert run("gap_audit.py", out, "--check").returncode == 0


def test_facts_include_unified_capacity(tmp_path):
    """Фактура аудита показывает одну ёмкость (capacity.py) и сумму now — аудитор не пересчитывает в своих часах."""
    props = [proposal(i, effort_days=[10, 20]) for i in range(1, 5)]
    cfg = {"strategy": {"proposals_min": 1}, "project": {"capacity": {"hours_per_week": 12, "dev_share": 0.5, "day_hours": 6}}}
    out = make_out(tmp_path, props, cfg)
    assert run("gap_audit.py", out, "--top", "4").returncode == 0
    F = jload(out / "data" / "gap-audit-facts.json")
    cap = F["now_capacity"]
    assert cap["day_hours"] == 6 and cap["now_days"] == 60.0 and cap["ok"] is False
    md = (out / "build" / "gap-audit-facts.md").read_text(encoding="utf-8")
    assert "день = 6 ч" in md and "ПРЕВЫШЕНИЕ" in md
    # старые прогоны без ёмкости — без строки
    out2 = make_out(tmp_path / "old", props)
    assert run("gap_audit.py", out2, "--top", "4").returncode == 0
    assert jload(out2 / "data" / "gap-audit-facts.json")["now_capacity"] is None
