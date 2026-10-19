# -*- coding: utf-8 -*-
"""WP-A 1.5: проверки до «Начинаю?» — противоречия ответов (FB-053, SM 3.2, 3.4), ёмкость MVP против срока (FB-054),
нарезка на очереди после светофора (SM 3.3); вход прогона — состояние git и пустой репозиторий (FB-041, SM 6.5), ветка до
первой записи (FB-034), правила владельца из CLAUDE.md (FB-040), единая ёмкость project.capacity (FB-028, SM 6.1), поля
registry для реестра. pytest tests/test_concept_intake_checks.py"""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import concept_checks as cc  # noqa: E402
import intake  # noqa: E402

PY = [sys.executable, "-B"]
AR_PITCH = ("Платный сайт/приложение-трекер для игры ARC Raiders: предметы, спауны ARC-роботов, карты, статистика и прогресс "
            "игрока, синхронизация со Steam/сохранениями; ориентир — metaforge.app")
# ответы владельца в прогоне ARC Raiders (run-config.idea.answers эталона, 40 вопросов)
AR_ANSWERS = {
    "Вопросов": "40 — все", "Глубина": "Глубоко", "Боль": "Заметная, но терпимая", "Сейчас": "Бесплатными аналогами", "Частота": "Каждый день",
    "Триггер": "Требование извне", "Цена боли": "Только неудобство", "Аудитория": "Частные лица (B2C)",
    "Рынки": "Основной русский и английский, плюс языки локализации игры", "Сегмент": "Сообщество, где я свой",
    "Где они": ["Найти в исследовании", "Соцсети и видео"], "Доступ": "Нет, начинаю с нуля", "Ценность": "Экономит время",
    "Отличие": "Новая возможность", "Ага-момент": "В первые 5 минут", "Замена": "От таблиц и заметок", "Сеть": "Полезен и одному",
    "Форма": "Веб-приложение и мобильное приложение или удобная мобильная версия веба", "MVP": "Полноценная первая версия",
    "Срок MVP": "Через 1–2 месяца", "Устройства": "Оба одинаково", "Данные": "Минимум: почта и настройки", "ИИ": "Только если упростит",
    "Аналоги": "Найди сам", "Образцы": "Подбери по идее", "Рынок": "Зрелый, есть лидеры", "Тайминг": "Найти в исследовании",
    "Модель": "Freemium + подписка", "Цена": "Определи по аналогам", "Кто платит": "Сам пользователь", "Доход": "Окупить расходы",
    "Команда": "Я один", "Бюджет": "Нулевой", "Время": "10–20 часов", "Навыки": ["Разработка", "Дизайн", "Знание предметной области"],
    "Стиль": "Тёплый и дружелюбный", "Название": "Придумай варианты", "Тема": "Обе, по системе", "Бренд": "Нет, создать с нуля",
    "Область": ["Нет, обычные данные, Деньги и платежи"], "Успех": "100 активных пользователей", "Риск": "Никому не нужно"}
CLAUDE_MD = """# Правила
- **Любая доработка** — **только в отдельной ветке под неё**, созданной от основной. Прямых коммитов в `main` нет.
- **Вливать в основную ветку — самостоятельно в конце**. Отдельного согласия на влитие не нужно. После влития — сразу push основной ветки.
- После влития спроси, удалять ли их; без явного «да» не удаляй.
- Для задачи длиннее нескольких шагов веди чек-лист в `TASKS.md` в корне проекта.
- **Ответы мне:** русский
"""


def env_home(tmp_path, claude_md=None):
    e = {k: v for k, v in os.environ.items() if k not in ("TYPESAFE_API_KEY", "TYPESAFE_API_URL")}
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    if claude_md:
        (home / ".claude" / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    e["HOME"] = str(home)
    return e


def run(tmp_path, *args, claude_md=None):
    return subprocess.run(PY + [str(SCRIPTS / "intake.py")] + [str(a) for a in args], capture_output=True, text=True, timeout=120,
                          env=env_home(tmp_path, claude_md))


def apply(tmp_path, answers, *extra, cwd=None, claude_md=None, idea=AR_PITCH):
    r = run(tmp_path, "concept-apply", "--repo", cwd or tmp_path, "--idea", idea, "--from-askuser", json.dumps(answers, ensure_ascii=False),
            *extra, claude_md=claude_md)
    assert r.returncode == 0, r.stdout + r.stderr
    out = next(line[4:] for line in r.stdout.splitlines() if line.startswith("OUT="))
    return r, Path(out), json.loads((Path(out) / "build" / "run-config.json").read_text(encoding="utf-8"))


def cfg_with(facets=None, answered=(), **over):
    cfg = intake.concept_base_config(".", "идея", None)
    cfg["idea"]["facets"] = dict(facets or {})
    cfg["idea"]["answers"] = {q: {"answer": "x"} for q in answered}
    for k, v in over.items():
        intake.set_path(cfg, k.replace("__", "."), v)
    return cfg


def ids(cfg):
    return {x["id"] for x in cc.run_checks(cfg) if x.get("options")}


# ---------- FB-053: правила противоречий (юнит) ----------
def test_conflict_rules_unit():
    c = cfg_with({"niche": "own_community", "access": "none"}, ["c08", "c10"])
    assert "own_community_no_access" in ids(c)
    assert "own_community_no_access" not in ids(cfg_with({"niche": "own_community", "access": "none"}, ["c08"]))   # c10 по умолчанию
    c = cfg_with({"revenue_goal": "main_income", "hours_week": 15}, ["c29"])
    assert "revenue_vs_resources" in ids(c)
    c = cfg_with({"segment": "b2b", "channels": ["social"]}, ["c06", "c09"])
    assert "b2b_social" in ids(c)
    c = cfg_with({"skills": ["design"]}, ["c33"])
    assert "no_dev_skills" in ids(c)
    c = cfg_with({}, ["c26"], project__audience="personal", strategy__paid_tier="yes")
    assert "personal_money" in ids(c)
    c = cfg_with({"ai": "core", "ai_where": "local", "ai_hardware": "browser_only"})
    assert "ai_local_browser" in ids(c)
    c = cfg_with({"competitors_known": "none_claimed"}, ["c22"], sources__competitor_list=["metaforge.app"])
    assert "competitors_claimed_none" in ids(c)
    c = cfg_with({"ai": "core", "data": "personal"})
    assert any(x["id"] == "ai_core_sensitive" for x in cc.run_checks(c))       # связка ИИ + личные данные — пометка и блок права
    assert ids(cfg_with({"mvp": "single_feature", "hours_week": 40, "mvp_weeks": 6})) == set()


# ---------- FB-054: ёмкость MVP против срока ----------
def test_mvp_capacity_numbers():
    c = cfg_with({"mvp": "full", "hours_week": 15, "mvp_weeks": 6})
    mc = cc.mvp_capacity(c)
    assert mc["fits"] == "no" and mc["need"] == [60, 120] and 7 < mc["have"] < 9 and mc["need_weeks"] > 6
    assert "не помещается" in mc["line"] and "день 8 ч" in mc["line"]
    c2 = cfg_with({"mvp": "full", "hours_week": 15, "mvp_weeks": 6}, project__team_size=2)
    assert cc.mvp_capacity(c2)["have"] > mc["have"] * 1.9                       # команда умножает ёмкость (capacity.py)
    assert cc.mvp_capacity(cfg_with({"mvp": "landing", "hours_week": 15, "mvp_weeks": 6}))["fits"] in ("yes", "tight")


# ---------- эталонные ответы: вопросы до «Начинаю?», решения через update ----------
def test_reference_answers_ask_before_start_and_record_decisions(tmp_path):
    r, out, cfg = apply(tmp_path, AR_ANSWERS)
    paths = {x["path"] for x in cfg["follow_up"]}
    assert {"idea.decisions.own_community_no_access", "idea.decisions.mvp_capacity", "idea.decisions.sensitive_exclusive"} <= paths
    assert "Уточнить ДО «Начинаю?»" in r.stdout and "Проверка ответов до «Начинаю?»" in r.stdout and "не помещается" in r.stdout
    assert cfg["product"]["type"] == "saas" and cfg["product"]["forms"] == ["web", "mobile_web"]      # FB-024 на эталоне
    assert cfg["registry"]["capacity_cap"] is True and cfg["registry"]["passes"] == 1                  # deep — один проход (FB-005)
    u = run(tmp_path, "update", out, "--from-askuser", json.dumps({"Сообщество": "Есть знакомые в сообществе (Recommended)",
                                                                  "Ёмкость MVP": "Одна ключевая функция (Recommended)",
                                                                  "Чувств. обл.": "Есть чувствительная область (Recommended)"},
                                                                 ensure_ascii=False))
    assert u.returncode == 0, u.stderr
    cfg = json.loads((out / "build" / "run-config.json").read_text(encoding="utf-8"))
    f = cfg["idea"]["facets"]
    assert f["access"] == "acquaintances" and f["mvp"] == "single_feature" and f["sensitive"] == ["finance"]
    assert cfg["idea"]["decisions"]["mvp_capacity"] == "single_feature"                                # выбор записан (FB-054)
    assert not any(x["path"].startswith("idea.decisions.") and x["path"] != "idea.decisions.name" for x in cfg["follow_up"])
    assert any("Решение владельца до старта" in a for a in cfg["assumptions"])


def test_decisions_in_concept_apply_answers(tmp_path):
    ans = dict(AR_ANSWERS, **{"Ёмкость MVP": "Продлить срок до 46 нед.", "Сообщество": "Доступа нет: сегмент — узкая ниша",
                              "Чувств. обл.": "Нет, обычные данные", "Имя и папка": "Рейд-планер"})
    _r, out, cfg = apply(tmp_path, ans)
    f = cfg["idea"]["facets"]
    assert f["niche"] == "narrow" and f["mvp_weeks"] > 6 and f["sensitive"] == [] and cfg["scope"]["legal"] is False
    assert cfg["product"]["name"] == "Рейд-планер" and cfg["idea"]["slug"] == "reyd-planer" and out.parent.name == "reyd-planer"
    assert not any(x["path"].startswith("idea.decisions.") for x in cfg["follow_up"])


# ---------- SM 3.3: светофор → нарезка на очереди ----------
def test_verdict_card_and_slicing(tmp_path):
    _r, out, _cfg = apply(tmp_path, {"Время": "10–20 часов"})
    (out / "data").mkdir(exist_ok=True)
    (out / "data" / "typesafe-concept.json").write_text(json.dumps({"verdict": "red", "viability": 0.41, "weak": ["revenue", "feasible"]}),
                                                       encoding="utf-8")
    v = run(tmp_path, "concept-verdict", out, "--json")
    d = json.loads(v.stdout)
    assert d["verdict_card"]["header"] == "Светофор" and d["verdict_card"]["options"][0]["label"].startswith("Продолжить с нарезкой")
    u = run(tmp_path, "update", out, "--from-askuser", json.dumps({"Светофор": "Продолжить с нарезкой на очереди (Recommended)"},
                                                                  ensure_ascii=False))
    assert u.returncode == 0, u.stderr
    cfg = json.loads((out / "build" / "run-config.json").read_text(encoding="utf-8"))
    sl = cfg["slicing"]
    assert sl["enabled"] is True and [q["id"] for q in sl["queues"]] == ["alpha", "beta", "v1", "v2"]
    assert all(q["name"] and q["goal"] and q["enter_when"] and q["capacity_days"] > 0 for q in sl["queues"])
    assert {p["weak"] for p in sl["priorities"]} == {"revenue", "feasible"} and cfg["idea"]["facets"]["mvp"] == "single_feature"
    assert cfg["registry"]["capacity_cap"] is True and "Нарезка на очереди" in u.stdout
    (out / "data" / "typesafe-concept.json").write_text(json.dumps({"verdict": "green"}), encoding="utf-8")
    assert "не нужна" in run(tmp_path, "concept-verdict", out).stdout


# ---------- FB-041, SM 6.5: состояние git; FB-034: ветка до первой записи ----------
def test_git_states(tmp_path):
    assert cc.git_state(tmp_path)["state"] == "no_repo"
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    gs = cc.git_state(repo)
    assert gs["state"] == "unborn" and gs["branch"] == "main" and gs["has_origin"] is False
    plan = " ".join(cc.git_plan(gs, "docs/concept-x"))
    assert "пустой репозиторий (нет коммитов)" in plan and "push -u origin main" in plan
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "https://example.com/x.git"], check=True)
    gs = cc.git_state(repo)
    assert gs["state"] == "normal" and gs["has_origin"] is True and gs["default_branch"] == "main"


def test_branch_created_before_first_write_in_unborn_repo(tmp_path):
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    r, out, cfg = apply(tmp_path, {"Название": "Книгообмен"}, cwd=repo)
    head = subprocess.run(["git", "-C", str(repo), "symbolic-ref", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert head == cfg["output"]["git_branch"] == "docs/concept-knigoobmen" and cfg["output"]["branch_status"] == "created"
    assert cfg["git"]["state"] == "unborn" and "git: пустой репозиторий (нет коммитов)" in r.stdout and "Ветка: создана" in r.stdout
    r2, _out, cfg2 = apply(tmp_path, {"Название": "Книгообмен"}, cwd=repo)                      # повтор — уже на ветке
    assert cfg2["output"]["branch_status"] == "current"


def test_branch_not_switched_from_feature_branch_and_branch_none(tmp_path):
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    subprocess.run(["git", "-C", str(repo), "switch", "-q", "-c", "feature/other"], check=True)
    r, _out, cfg = apply(tmp_path, {"Название": "Полка"}, cwd=repo)
    head = subprocess.run(["git", "-C", str(repo), "symbolic-ref", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert head == "feature/other" and cfg["output"]["branch_status"] == "skipped" and "ВНИМАНИЕ, ветка" in r.stdout
    subprocess.run(["git", "-C", str(repo), "switch", "-q", "main"], check=True)
    _r, _out, cfg = apply(tmp_path, {"Название": "Полка"}, "--branch", "none", cwd=repo)
    head = subprocess.run(["git", "-C", str(repo), "symbolic-ref", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert head == "main" and cfg["output"]["branch_status"] == "skipped"


def test_dry_run_writes_nothing(tmp_path):
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    r = run(tmp_path, "concept-apply", "--repo", repo, "--idea", AR_PITCH, "--from-askuser", json.dumps(AR_ANSWERS, ensure_ascii=False),
            "--dry-run", "--json")
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["dry_run"] is True and d["run_config"] is None and d["follow_up"] and not (repo / "concept").exists()
    head = subprocess.run(["git", "-C", str(repo), "symbolic-ref", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert head == "main"


# ---------- FB-040: правила владельца из CLAUDE.md ----------
def test_owner_rules_from_claude_md(tmp_path):
    rules = cc.owner_rules(None, home=env_home(tmp_path, CLAUDE_MD)["HOME"])
    assert rules["sources"] == ["~/.claude/CLAUDE.md"] and rules["branch_per_task"] is True and rules["merge"] == "self"
    assert rules["push_after_merge"] is True and rules["delete_branches"] == "ask" and rules["tasks_file"] == "TASKS.md"
    r, _out, cfg = apply(tmp_path, {"Название": "Полка"}, claude_md=CLAUDE_MD)
    assert "Правила владельца (~/.claude/CLAUDE.md)" in r.stdout and "слияние в основную — сам" in r.stdout and "TASKS.md" in r.stdout
    assert cfg["owner_rules"]["tasks_file"] == "TASKS.md" and "/Users/" not in json.dumps(cfg["owner_rules"])
    assert cc.owner_rules(None, home=tmp_path / "nohome")["sources"] == []


# ---------- FB-028, SM 6.1: одна ёмкость; registry ----------
def test_project_capacity_single_day_hours(tmp_path):
    _r, _out, cfg = apply(tmp_path, {"Время": "10–20 часов", "Глубина": "Стандарт (Recommended)"})
    cap = cfg["project"]["capacity"]
    assert cap["hours_per_week"] == 15 and cap["dev_share"] == 0.7 and cap["day_hours"] == 8 and cap["source"].startswith("ответ c32")
    assert "hours_in_day" not in cfg["project"] and cfg["registry"]["passes"] == 2
    _r, _out, cfg = apply(tmp_path / "b", {"Команда": "2–3 человека"}, "--set", "project.capacity.day_hours=6")
    cap = cfg["project"]["capacity"]
    assert cap["day_hours"] == 6 and cap["hours_per_week"] == 8 and cap["source"].startswith("задано владельцем")
    import capacity
    assert capacity.capacity(cfg, 6)["team_size"] == 2                                           # команду умножает capacity.py
