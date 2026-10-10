# -*- coding: utf-8 -*-
"""Ядро product-strategy: опрос (intake.py), проверка инструментов (check_env.py), папка прогона (init_run.py),
путь скилла (skill_dir.py), конвейер (build_all.py), демо (make_demo.py). pytest tests/test_core.py"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import intake  # noqa: E402

PY = [sys.executable, "-B"]


def run(*args, **kw):
    return subprocess.run(PY + [str(SCRIPTS / args[0])] + [str(x) for x in args[1:]], capture_output=True, text=True, timeout=300, **kw)


# ---------- intake: вопросы подходят AskUserQuestion ----------
def test_rounds_fit_ask_user_question_limits():
    rounds = intake.questions_json()
    assert len(rounds) == 5
    headers = []
    for r in rounds:
        assert 1 <= len(r["questions"]) <= 4
        for q in r["questions"]:
            assert len(q["header"]) <= 12, q["header"]
            assert 2 <= len(q["options"]) <= 4, q["header"]
            assert q["question"].endswith("?") or "(можно несколько)" in q["question"]
            labels = [o["label"] for o in q["options"]]
            assert len(set(labels)) == len(labels)
            assert all(1 <= len(l.split()) <= 7 for l in labels), labels
            assert "Other" not in labels and "Другое" not in labels      # «Other» инструмент добавляет сам
            headers.append(q["header"])
    assert len(set(headers)) == len(headers)


def test_open_questions_are_cards_with_defaults():
    batches = intake.open_cards_json()
    assert all(1 <= len(b["questions"]) <= 4 for b in batches)
    for b in batches:
        for q in b["questions"]:
            assert len(q["header"]) <= 12 and 2 <= len(q["options"]) <= 4 and "(Recommended)" in q["options"][0]["label"] or "Решить" in q["options"][0]["label"]
    assert sum(len(b["questions"]) for b in batches) == len(intake.OPEN_CARDS) == 8


def test_from_askuser_rounds_and_open_cards(tmp_path):
    ans = {"Какова цель проекта и его модель?": "Личный инструмент", "Видимость": "Приватный", "Сколько человек работает над проектом?": "Один разработчик",
           "Стратегия": "Рост продукта (Recommended)", "Бюджет": "Нулевой",
           "Название продукта и суть в одной фразе?": "Определи по репозиторию (Recommended)",
           "Известны ли аудитория, трафик, конверсии, доход, цены?": "Мало: 20 пользователей, дохода нет",
           "Есть ли ограничения и что вне задачи?": "Без платной рекламы",
           "Кого указать автором стратегии в титуле и подвалах?": "Иванов Иван (ivanov)",
           "Готовы ли открыть код проекта, если он закрыт?": "Да, готов открыть",
           "Есть ли известные конкуренты и образцы?": "Есть список"}
    r = run("intake.py", "apply", "--repo", tmp_path, "--from-askuser", json.dumps(ans, ensure_ascii=False), "--out-dir", tmp_path / "r")
    assert r.returncode == 0, r.stderr
    cfg = json.loads((tmp_path / "r" / "build" / "run-config.json").read_text(encoding="utf-8"))
    assert cfg["project"]["goal"] == "personal" and cfg["project"]["repo_visibility"] == "private" and cfg["project"]["team_size"] == 1
    assert cfg["project"]["publish_code"] == "yes"
    assert cfg["strategy"]["budget"]["variants"] == ["zero"] and cfg["strategy"]["profile"] == "zero-budget-solo"
    assert cfg["product"]["known_facts"].startswith("Мало") and cfg["strategy"]["constraints"] == "Без платной рекламы"
    assert cfg["author"]["name"] == "Иванов Иван" and cfg["author"]["nick"] == "ivanov"
    assert "Заметка: sources.competitor_list" in r.stdout            # выбран «Есть список», а текста нет


def test_auto_values_are_resolved(tmp_path):
    (tmp_path / "README.md").write_text("# Проект\n\nПриложение для учёта расходов. Работает локально, данные не уходят в облако. " * 6, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\ndependencies=["fastapi"]\n', encoding="utf-8")
    cfg = intake.finalize(intake.base_config(tmp_path))
    assert cfg["strategy"]["markets"][0] == "ru" and cfg["product"]["type"] == "saas" and cfg["project"]["currency"] == "RUB"
    assert cfg["strategy"]["profile"] in ("standard", "zero-budget-solo") and "auto" not in (cfg["strategy"]["markets"] + [cfg["product"]["type"]])


def test_recommended_option_is_first_and_single():
    for r in intake.questions_json():
        for q in r["questions"]:
            rec = [i for i, o in enumerate(q["options"]) if "(Recommended)" in o["label"]]
            if not q["multiSelect"]:
                assert rec == [0], q["header"]


def test_defaults_match_user_request(tmp_path):
    cfg = intake.finalize(intake.base_config(tmp_path))
    assert cfg["strategy"]["proposals_min"] == 100 and cfg["strategy"]["proposals_min"] >= 50
    assert cfg["scope"]["repo_analysis"] is True                     # анализ репозитория — по умолчанию
    assert cfg["strategy"]["horizon_months"] == 12 and cfg["strategy"]["vision_years"] == 3
    assert cfg["output"]["dir"].endswith(str(Path("strategy") / cfg["created"]))


def test_apply_answers_and_open(tmp_path):
    ans = {"Стратегия": "Полная: рост + технологии", "Глубина": "Глубоко", "Предложения": "150",
           "Источники": ["Текущий репозиторий (Recommended)"], "Исследования": ["Конкуренты (Recommended)"],
           "Форматы": ["Веб-страница (Recommended)", "XLSX"], "Папка": "Рядом с репозиторием", "Бюджет": "до $300 в месяц",
           "Рынки": "ru, kz"}
    (tmp_path / "a.json").write_text(json.dumps(ans, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "o.json").write_text(json.dumps({"author": "Иванов Иван (ivan)", "sources.competitor_list": "A, B; C"},
                                                ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "run"
    r = run("intake.py", "apply", "--repo", tmp_path, "--answers", tmp_path / "a.json", "--open", tmp_path / "o.json",
            "--out-dir", out, "--set", "scope.experiments=5")
    assert r.returncode == 0, r.stderr
    cfg = json.loads((out / "build" / "run-config.json").read_text(encoding="utf-8"))
    assert cfg["strategy"]["kind"] == "full" and cfg["strategy"]["depth"] == "deep"
    assert cfg["strategy"]["proposals_min"] == 150                   # явный ответ главнее глубины
    assert cfg["scope"]["competitors_min"] == 15                     # из глубины
    assert cfg["scope"]["experiments"] == 5                          # --set главнее
    assert cfg["scope"]["app_run"] is False and cfg["scope"]["communities"] is False and cfg["scope"]["legal"] is False
    assert cfg["formats"] == {"html": True, "xlsx": True, "pptx": False, "pdf": False, "md": True}
    assert cfg["strategy"]["budget"]["note"] == "до $300 в месяц"
    assert cfg["strategy"]["markets"] == ["ru", "kz"]
    assert cfg["author"] == {"name": "Иванов Иван", "nick": "ivan", "copyright": "© %s Иванов Иван (ivan)" % cfg["created"][:4]}
    assert cfg["sources"]["competitor_list"] == ["A", "B", "C"]
    assert "OUT=" in r.stdout


def test_proposals_floor_is_50(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"Предложения": "20"}), encoding="utf-8")
    r = run("intake.py", "apply", "--repo", tmp_path, "--answers", tmp_path / "a.json", "--out-dir", tmp_path / "r")
    cfg = json.loads((tmp_path / "r" / "build" / "run-config.json").read_text(encoding="utf-8"))
    assert r.returncode == 0 and cfg["strategy"]["proposals_min"] == 50


def test_from_text_extracts_explicit_params():
    f = intake.from_text("Сделай подробнейшую стратегию, не менее 120 предложений, на 18 месяцев и 5 лет, без субагентов")
    assert f == {"strategy.proposals_min": 120, "strategy.depth": "exhaustive", "strategy.horizon_months": 18,
                 "strategy.vision_years": 5, "tools.subagents": False}
    assert intake.from_text("автопилот, 60 идей")["autopilot"] is True


def test_defaults_autopilot(tmp_path):
    r = run("intake.py", "defaults", "--repo", tmp_path, "--out-dir", tmp_path / "r")
    cfg = json.loads((tmp_path / "r" / "build" / "run-config.json").read_text(encoding="utf-8"))
    assert r.returncode == 0 and cfg["autopilot"] is True and cfg["assumptions"]


# ---------- check_gitignore ----------
def test_check_gitignore_finds_and_fixes_hidden_build(tmp_path):
    repo = tmp_path / "repo"
    (repo / "strategy" / "2026-10-10" / "build").mkdir(parents=True)
    (repo / "strategy" / "2026-10-10" / "data").mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / ".gitignore").write_text("build/\n", encoding="utf-8")
    (repo / "strategy" / "2026-10-10" / "build" / "run-config.json").write_text("{}", encoding="utf-8")
    (repo / "strategy" / "2026-10-10" / "data" / "p.json").write_text("[]", encoding="utf-8")
    out = repo / "strategy" / "2026-10-10"
    r = run("check_gitignore.py", out)
    assert r.returncode == 1 and "run-config.json" in r.stdout and "build/" in r.stdout
    r = run("check_gitignore.py", out, "--fix")
    assert r.returncode == 0 and "!build/" in (out / ".gitignore").read_text(encoding="utf-8")
    assert run("check_gitignore.py", tmp_path / "elsewhere").returncode == 0                 # вне репозитория — проверка не нужна


# ---------- init_run ----------
def test_init_run_status_cycle(tmp_path):
    out = tmp_path / "o"
    assert run("init_run.py", out).returncode == 0
    for d in ("research", "data", "charts", "mockups/concepts", "design-refs", "deliverables", "build/briefs"):
        assert (out / d).is_dir()
    assert run("init_run.py", out, "--done", "0", "--status", "опрос и инструменты готовы").returncode == 0
    r = run("init_run.py", out, "--show")
    assert "Следующая фаза: 1." in r.stdout and "опрос и инструменты готовы" in r.stdout
    assert (out / "STRATEGY_TASKS.md").is_file() and not (out / "TASKS.md").exists()
    assert "5.5. Аудит пробелов" in (out / "build" / "STATUS.md").read_text(encoding="utf-8")
    assert run("init_run.py", out, "--done", "5.5").returncode == 0


# ---------- check_env ----------
def test_check_env_runs_and_writes_json(tmp_path):
    r = run("check_env.py", "--json", tmp_path / "env.json", "--session-skills", "superpowers:brainstorming,data:analyze")
    assert r.returncode in (0, 1) and "python3" in r.stdout
    data = json.loads((tmp_path / "env.json").read_text(encoding="utf-8"))
    names = {x["name"] for x in data["rows"]}
    assert {"python3", "git", "node", "node:playwright", "skill:superpowers"} <= names
    sp = next(x for x in data["rows"] if x["name"] == "skill:superpowers")
    assert sp["status"] == "OK"                                      # увиден по списку сессии
    assert "TYPESAFE_API_KEY" in names
    assert all("sk-" not in json.dumps(x) for x in data["rows"])     # значения ключей не печатаются


def test_check_env_plan_uses_session_skills_from_first_call(tmp_path):
    out = tmp_path / "o"
    (out / "build").mkdir(parents=True)
    run("check_env.py", "--out", out, "--session-skills", "zzz-test-skill:one", "--quiet")
    assert "zzz-test-skill:one" in (out / "build" / "session-skills.txt").read_text(encoding="utf-8")
    r = run("check_env.py", "--plan", "--out", out)                      # без флага: берётся сохранённый список
    assert r.returncode == 0 and "Поставлю сам" in r.stdout


def test_node_dir_default_is_user_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("PS_NODE_DIR", raising=False)
    import check_env
    assert str(check_env.node_dir(tmp_path / "o")).endswith(str(Path(".cache") / "product-strategy" / "node"))
    (tmp_path / "o" / "build").mkdir(parents=True)
    (tmp_path / "o" / "build" / "run-config.json").write_text(json.dumps({"tools": {"node_dir": str(tmp_path / "nd")}}), encoding="utf-8")
    assert check_env.node_dir(tmp_path / "o") == tmp_path / "nd"
    monkeypatch.setenv("PS_NODE_DIR", str(tmp_path / "env"))
    assert check_env.node_dir(tmp_path / "o") == tmp_path / "env"


def test_check_env_plan_lists_local_installs(tmp_path):
    r = run("check_env.py", "--plan", "--out", tmp_path / "x")
    assert "Поставлю сам" in r.stdout and "Нужно согласие" in r.stdout


# ---------- skill_dir, demo, build_all ----------
def test_skill_dir_prints_folder_with_skill_md():
    r = run("skill_dir.py")
    assert r.returncode == 0 and (Path(r.stdout.strip()) / "SKILL.md").exists()


def test_demo_and_build_all_html_and_xlsx(tmp_path):
    out = tmp_path / "demo"
    assert run("make_demo.py", out, "--proposals", "60").returncode == 0
    props = json.loads((out / "data" / "proposals.json").read_text(encoding="utf-8"))
    assert len(props) == 60 and len({p["category"] for p in props}) == 10
    r = run("build_all.py", out, "--skip", "links,pptx,pdf,smoke,mockups")
    assert "registry" in r.stdout and "Итог" in r.stdout
    if (SCRIPTS / "build_html.py").exists():
        assert (out / "deliverables" / "index.html").exists(), r.stdout + r.stderr
    if (SCRIPTS / "build_xlsx.py").exists():
        assert (out / "deliverables" / "strategy.xlsx").exists(), r.stdout + r.stderr


def test_build_all_new_steps_and_statuses(tmp_path):
    out = tmp_path / "demo"
    assert run("make_demo.py", out, "--proposals", "60").returncode == 0
    r = run("build_all.py", out, "--skip", "links,pptx,pdf,smoke,mockups,xlsx,deck")
    for step in ("mocklink", "registry", "gapaudit", "assemble", "method", "refsreadme", "gitignore"):
        assert step in r.stdout, step
    assert "выключено выбором" in r.stdout and "всё собрано" in r.stdout
    assert (out / "research" / "methodology.md").is_file() and (out / "design-refs" / "README.generated.md").exists() or (out / "design-refs" / "README.md").exists()


# ---------- режим «Отслеживание»: поиск стратегий, карточки, track ----------
def _repo_with_strategies(tmp_path, n=1):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for i in range(n):
        out = repo / "strategy" / ("2026-10-1%d" % i)
        assert run("make_demo.py", out, "--proposals", "50").returncode == 0
        cfgp = out / "build" / "run-config.json"
        cfg = json.loads(cfgp.read_text(encoding="utf-8"))
        cfg["created"] = "2026-10-1%d" % i
        cfg["output"]["inside_repo"] = True
        cfgp.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        run("score.py", out)
    return repo


def test_detect_no_strategies_means_new(tmp_path):
    r = run("intake.py", "detect", "--repo", tmp_path, "--json")
    d = json.loads(r.stdout)
    assert r.returncode == 0 and d["found"] == [] and d["cards"] == [] and d["auto"] is None


def test_detect_one_strategy_gives_mode_card_and_auto(tmp_path):
    repo = _repo_with_strategies(tmp_path, 1)
    d = json.loads(run("intake.py", "detect", "--repo", repo, "--json").stdout)
    assert len(d["found"]) == 1 and d["auto"]["recommended"] and d["auto"]["complete"] and d["auto"]["proposals"] == 50
    assert [c["header"] for c in d["cards"]] == ["Режим"]
    card = d["cards"][0]
    assert 2 <= len(card["options"]) <= 4 and "(Recommended)" in card["options"][0]["label"] and len(card["header"]) <= 12


def test_detect_several_strategies_asks_which_and_prefers_latest_complete(tmp_path):
    repo = _repo_with_strategies(tmp_path, 3)
    (repo / "strategy" / "2026-10-12" / "data" / "scores.json").unlink()            # самая свежая — неполная
    d = json.loads(run("intake.py", "detect", "--repo", repo, "--json").stdout)
    assert [c["header"] for c in d["cards"]] == ["Режим", "Стратегия"]
    assert d["auto"]["created"] == "2026-10-11"                                       # свежая полная, а не просто свежая
    assert len(d["cards"][1]["options"]) == 3 and "(Recommended)" in d["cards"][1]["options"][0]["label"]


def test_track_writes_tracking_block_and_prints_out(tmp_path):
    repo = _repo_with_strategies(tmp_path, 1)
    r = run("intake.py", "track", "--repo", repo, "--mode", "update")
    out = repo / "strategy" / "2026-10-10"
    assert r.returncode == 0 and "OUT=%s" % out.resolve() in r.stdout
    cfg = json.loads((out / "build" / "run-config.json").read_text(encoding="utf-8"))
    assert cfg["tracking"]["mode"] == "update" and cfg["tracking"]["baseline"] == str(out.resolve())
    assert run("intake.py", "track", "--repo", tmp_path / "none").returncode != 0           # нет стратегий — понятная ошибка


def test_strategy_update_brief_is_self_contained():
    text = (SCRIPTS.parent / "templates" / "briefs" / "strategy-update.md").read_text(encoding="utf-8")
    for ph in ("{OUT}", "{DATE}", "{SKILL_DIR}", "{LANG}", "{MISSING_INPUTS}"):
        assert ph in text
    assert "/Users/" not in text and "assemble_strategy.py" in text and "revision.json" in text


@pytest.mark.parametrize("name", ["SKILL.md", "INSTALL.md", "README.md", "references/data-contract.md", "references/intake.md",
                                  "references/tools.md"])
def test_docs_exist_and_mention_scripts(name):
    p = SCRIPTS.parent / name
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    for script in ("intake.py", "check_env.py") if name == "SKILL.md" else ("intake.py",) if name == "references/intake.md" else ():
        assert script in text


def test_skill_md_references_existing_files():
    import re
    text = (SCRIPTS.parent / "SKILL.md").read_text(encoding="utf-8")
    for ref in set(re.findall(r"`((?:references|templates)/[\w./-]+\.md)`", text)):
        if "{" in ref:
            continue
        assert (SCRIPTS.parent / ref).exists(), ref


# ---------- папка результата: внутри / вне репозитория (1.2.1) ----------
@pytest.mark.parametrize("label,inside", [
    ("ВНУТРИ репозитория: strategy/ (Recommended)", True), ("ВНЕ репозитория (рядом)", False),
    ("В репозитории strategy/ (Recommended)", True), ("Рядом с репозиторием", False),     # подписи до 1.2.1
    ("положи рядом с репозиторием", False), ("внутри репо", True)])
def test_folder_answer_maps_to_inside_repo(label, inside):
    cfg = intake.base_config(".")
    intake.apply_answers(cfg, {"Папка": label})
    assert cfg["output"]["inside_repo"] is inside


def test_folder_card_labels_say_inside_outside():
    q = next(x for r in intake.questions_json() for x in r["questions"] if x["header"] == "Папка")
    assert q["options"][0]["label"].startswith("ВНУТРИ") and "Recommended" in q["options"][0]["label"]
    assert q["options"][1]["label"].startswith("ВНЕ")


def test_request_text_sets_folder_when_card_not_answered_and_warns_on_conflict():
    cfg = intake.base_config(".")
    assert intake.check_folder_request(cfg, "сохрани стратегию вне репозитория") and cfg["output"]["inside_repo"] is False
    cfg = intake.base_config(".")
    intake.apply_answers(cfg, {"Папка": "ВНЕ репозитория (рядом)"})
    notes = intake.check_folder_request(cfg, "стратегию надо положить в репозиторий")
    assert notes and notes[0].startswith("ВНИМАНИЕ") and cfg["output"]["folder_conflict"] is True
    assert cfg["output"]["inside_repo"] is False                       # ответ карточки не меняем молча
    cfg = intake.base_config(".")
    intake.apply_answers(cfg, {"Папка": "ВНУТРИ репозитория: strategy/ (Recommended)"})
    assert intake.check_folder_request(cfg, "положи внутри репозитория") == []


def test_show_marks_outside_repo_loudly():
    cfg = intake.finalize(intake.base_config("."))
    assert "ВНУТРИ репозитория" in intake.show(cfg)
    cfg["output"]["inside_repo"] = False
    assert "ВНЕ РЕПОЗИТОРИЯ" in intake.show(cfg)
