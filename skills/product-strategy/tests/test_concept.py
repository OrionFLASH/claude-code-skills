# -*- coding: utf-8 -*-
"""Режим «Идея → концепция продукта» (references/concept-mode.md): банк вопросов и опрос (intake.py concept-*), досье
(concept_dossier.py), предпроверка жизнеспособности (typesafe_concept.py), фазы C0–C9 (init_run.py), сквозной демо-прогон
(make_concept_demo.py + build_all.py). pytest tests/test_concept.py"""
import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import intake  # noqa: E402
import typesafe_concept  # noqa: E402

PY = [sys.executable, "-B"]
IDEA = "Приложение для обмена книгами между соседями. Без денег и курьеров."


def env_clean(**extra):
    e = {k: v for k, v in os.environ.items() if k not in ("TYPESAFE_API_KEY", "TYPESAFE_API_URL")}
    e.update(extra)
    return e


def run(*args, env=None, **kw):
    return subprocess.run(PY + [str(SCRIPTS / args[0])] + [str(x) for x in args[1:]], capture_output=True, text=True, timeout=300,
                          env=env or env_clean(), **kw)


def apply(cwd, answers, *extra, idea=IDEA, env=None):
    r = run("intake.py", "concept-apply", "--repo", cwd, "--idea", idea, "--from-askuser", json.dumps(answers, ensure_ascii=False), *extra, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = next(line[4:] for line in r.stdout.splitlines() if line.startswith("OUT="))
    return r, Path(out), json.loads((Path(out) / "build" / "run-config.json").read_text(encoding="utf-8"))


# ---------- банк вопросов: 40 вопросов, ограничения AskUserQuestion, приоритеты ----------
def test_bank_has_40_questions_in_9_themes_and_fits_ask_user_question():
    bank = intake.CONCEPT_BANK
    assert len(bank) == 40 and [q[0] for q in bank] == ["c%02d" % i for i in range(1, 41)]
    assert {q[1] for q in bank} == {k for k, _ in intake.CONCEPT_THEMES} and len(intake.CONCEPT_THEMES) == 9
    assert sorted(q[2] for q in bank) == list(range(1, 41))                       # приоритеты уникальны
    headers = [q[3] for q in bank] + [h for h, *_ in intake.CONCEPT_SETUP]
    assert len(set(headers)) == len(headers)                                          # ответы ключуются по header
    for qid, theme, _p, header, text, multi, opts in bank:
        assert 1 <= len(header) <= 12, header
        assert text.endswith("?") or "(можно несколько)" in text, text
        assert 2 <= len(opts) <= 4, qid
        labels = [o[0] for o in opts]
        assert labels[0].endswith("(Recommended)") and sum("(Recommended)" in l for l in labels) == 1, qid
        assert len(set(labels)) == len(labels) and "Other" not in labels and "Другое" not in labels
        assert all(1 <= len(l.split()) <= 7 for l in labels), labels
        assert all(isinstance(m, dict) and m for _l, _d, m in opts), qid              # каждый вариант переводится в поля
    yes_no = sum(1 for q in bank if {o[0].split()[0].strip(",") for o in q[6]} <= {"Да", "Нет"})
    assert yes_no == 0                                                                # варианты содержательные, не «да/нет»


@pytest.mark.parametrize("n,lo,hi", [(15, 1, 2), (25, 2, 3), (40, 3, 6)])
def test_first_n_questions_cover_all_themes(n, lo, hi):
    cov = intake.concept_coverage(intake.concept_select(n))
    assert all(lo <= v <= hi for v in cov.values()), cov
    assert sum(cov.values()) == n


def test_less_than_15_questions_is_rejected():
    with pytest.raises(ValueError, match="минимум 15"):
        intake.concept_select(14)
    r = run("intake.py", "concept-questions", "--count", "10")
    assert r.returncode == 2 and "минимум 15" in r.stderr
    r = run("intake.py", "concept-apply", "--repo", ".", "--idea", "x", "--from-askuser", "{}", "--count", "12")
    assert r.returncode == 2 and "минимум 15" in r.stderr


@pytest.mark.parametrize("n", [15, 25, 40])
def test_concept_questions_batches_of_at_most_4_with_coverage(n):
    r = run("intake.py", "concept-questions", "--count", n, "--batch", "6", "--json")      # больше 4 — урезается до 4
    d = json.loads(r.stdout)
    assert r.returncode == 0 and d["count"] == n and d["all_themes_covered"] is True
    assert [c["theme"] for c in d["coverage"]] == [k for k, _ in intake.CONCEPT_THEMES]
    assert sum(len(b["questions"]) for b in d["batches"]) == n
    for b in d["batches"]:
        assert 1 <= len(b["questions"]) <= 4 and b["title"] and len(b["ids"]) == len(b["questions"])
        for q in b["questions"]:
            assert set(q) == {"header", "question", "multiSelect", "options"}                  # карточка — как есть в AskUserQuestion
    text = run("intake.py", "concept-questions", "--count", "15").stdout
    assert text.startswith("Вопросов об идее: 15 из 40") and "Покрытие тем" in text


def test_concept_setup_card():
    r = run("intake.py", "concept-setup", "--json")
    d = json.loads(r.stdout)
    assert r.returncode == 0 and [q["header"] for q in d["questions"]] == ["Вопросов", "Глубина", "Форматы", "Папка"]
    for q in d["questions"]:
        assert 2 <= len(q["options"]) <= 4 and q["options"][0]["label"].endswith("(Recommended)")
    n = [o["label"] for o in d["questions"][0]["options"]]
    assert n[0].startswith("25") and any(l.startswith("15") for l in n) and any(l.startswith("40") for l in n)
    folder = " ".join(o["label"] + o["description"] for o in d["questions"][3]["options"])
    assert "concept/" in folder and "../concept-" in folder and "~/concepts/" in folder


def test_slug_and_name_from_first_phrase():
    assert intake.idea_name_slug(IDEA) == ("Приложение для обмена книгами между соседями", "obmena-knigami-mezhdu-sosedyami")
    assert intake.idea_name_slug(IDEA, "Книгообмен") == ("Книгообмен", "knigoobmen")
    assert intake.slugify("Щука ёж: test!") == "schuka-ezh-test"


# ---------- concept-apply: ответы → run-config ----------
def test_concept_apply_maps_answers_to_run_config(tmp_path):
    ans = {"Вопросов": "25 (Recommended)", "Глубина": "Глубоко", "Форматы": ["Веб-страница (Recommended)", "XLSX"],
           "Форма": "Бот в мессенджере", "c07": "RU + EN",                                        # ключ — header или id
           "Как продукт будет зарабатывать?": "Разовая покупка",                                    # ключ — текст вопроса
           "Бюджет": "Нулевой (Recommended)", "Команда": "Я один (Recommended)", "Область": ["Здоровье или психика"],
           "Название": "Аптечка", "Аналоги": "Сервис А, Сервис Б", "Цена": "Средняя: до 1500 ₽ / $20"}
    r, out, cfg = apply(tmp_path, ans)
    assert cfg["mode"] == "concept" and cfg["product"]["stage"] == "idea" and cfg["product"]["type"] == "bot"
    assert cfg["product"]["name"] == "Аптечка" and cfg["idea"]["slug"] == "aptechka" and cfg["idea"]["pitch"] == IDEA
    assert cfg["strategy"]["markets"] == ["ru", "en"] and cfg["project"]["currency"] == "RUB"
    assert cfg["strategy"]["paid_tier"] == "yes" and cfg["strategy"]["monetization"] == "one_time" and cfg["project"]["price_hint"] == 990
    assert cfg["strategy"]["budget"]["variants"] == ["zero"] and cfg["project"]["team_size"] == 1
    assert cfg["strategy"]["profile"] == "zero-budget-solo"
    assert cfg["scope"]["legal"] is True and cfg["idea"]["facets"]["sensitive"] == ["health"]
    sc = cfg["scope"]
    assert sc["repo_analysis"] is False and sc["app_run"] is False and sc["issues"] is False and cfg["sources"]["repo"] is False
    assert sc["design_mockups"] is True and sc["design_refs"] is True and sc["mockups_min"] == 12 and sc["competitors_min"] == 15
    assert cfg["strategy"]["kind"] == "full" and cfg["strategy"]["proposals_min"] == 80 and cfg["strategy"]["depth"] == "deep"
    assert cfg["strategy"]["horizon_months"] == 6 and cfg["strategy"]["vision_years"] == 2
    assert cfg["formats"]["html"] and cfg["formats"]["xlsx"] and not cfg["formats"]["pptx"]
    assert cfg["sources"]["competitor_list"] == ["Сервис А", "Сервис Б"]
    a = cfg["idea"]["answers"]
    assert a["c16"] == {"theme": "product", "header": "Форма", "question": "В какой форме будет продукт?", "answer": "Бот в мессенджере", "custom": False}
    assert a["c22"]["custom"] is True and a["c38"]["answer"] == ["Здоровье или психика"]
    assert cfg["idea"]["questions_count"] == 25 and len(cfg["idea"]["unanswered"]) == 25 - len(a)
    assert "Режим: концепция нового продукта (идея: %s), вопросов отвечено %d из 25" % (IDEA, len(a)) in r.stdout


def test_defaults_standard_depth_and_non_sensitive_area(tmp_path):
    _r, _out, cfg = apply(tmp_path, {"Область": ["Нет, обычные данные (Recommended)"], "Форма": "Мобильное приложение"})
    assert cfg["scope"]["legal"] is False and cfg["product"]["type"] == "mobile"
    assert cfg["strategy"]["proposals_min"] == 60 and cfg["scope"]["mockups_min"] == 8 and cfg["scope"]["competitors_min"] == 10
    assert cfg["strategy"]["paid_tier"] == "yes" and cfg["strategy"]["monetization"] == "freemium"   # значения по умолчанию


def test_custom_answers_are_interpreted(tmp_path):
    ans = {"Форма": "мини-приложение в Telegram", "Рынки": "Казахстан и русский", "Бюджет": "тысяч 20 в месяц", "Команда": "нас трое",
           "Область": "детские садики, данные детей", "Успех": "50 семей в пилоте"}
    _r, _out, cfg = apply(tmp_path, ans)
    assert cfg["product"]["type"] == "bot" and cfg["strategy"]["markets"] == ["ru", "kk"]
    assert cfg["strategy"]["budget"] == {"variants": ["small"], "note": "тысяч 20 в месяц"} and cfg["project"]["team_size"] == 3
    assert cfg["scope"]["legal"] is True and cfg["strategy"]["success_criteria"] == "50 семей в пилоте"
    assert cfg["strategy"]["profile"] == "standard"
    assert all(cfg["idea"]["answers"][q]["custom"] for q in ("c16", "c07", "c31", "c30", "c38", "c39"))


def test_unanswered_questions_become_assumptions(tmp_path):
    _r, _out, cfg = apply(tmp_path, {"Вопросов": "15 — минимум", "Боль": "Острая, ищут решение"})
    idea = cfg["idea"]
    assert idea["questions_count"] == 15 and len(idea["unanswered"]) == 14 and "c01" not in idea["unanswered"]
    assert len(idea["not_asked"]) == 25 and set(idea["unanswered"]) | {"c01"} == {q[0] for q in intake.concept_select(15)}
    txt = " ".join(cfg["assumptions"])
    assert "c06 «Кто главный пользователь продукта?»: не отвечено → допущение «Частные лица (B2C)»" in txt
    assert "не задавались (25 шт.)" in txt


# ---------- папка: ВНУТРИ / ВНЕ, git-репозиторий → ветка, свой путь ----------
def test_folder_outside_git_repo_is_marked_loudly(tmp_path):
    r, out, cfg = apply(tmp_path, {"Название": "Книгообмен"})
    assert out == (tmp_path / "concept" / "knigoobmen" / cfg["created"]).resolve()
    assert cfg["output"]["inside_repo"] is False and cfg["output"]["git_branch"] == ""
    assert "ВНЕ РЕПОЗИТОРИЯ" in r.stdout


def test_folder_inside_git_repo_gets_branch(tmp_path):
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    r, out, cfg = apply(repo, {"Папка": "Текущая папка: concept/ (Recommended)", "Название": "Книгообмен"})
    assert cfg["output"]["inside_repo"] is True and cfg["output"]["git_branch"] == "docs/concept-knigoobmen"
    assert Path(cfg["repo"]["path"]) == repo.resolve() and str(out).startswith(str(repo.resolve()))
    assert "ВНУТРИ git-репозитория" in r.stdout and "docs/concept-knigoobmen" in r.stdout


def test_folder_sibling_home_and_custom(tmp_path):
    cwd = tmp_path / "work"
    cwd.mkdir()
    _r, out, cfg = apply(cwd, {"Папка": "Рядом: ../concept-<имя>/", "Название": "Полка"})
    assert out == (tmp_path / "concept-polka" / cfg["created"]).resolve()
    home = tmp_path / "home"
    home.mkdir()
    _r, out, _cfg = apply(cwd, {"Папка": "Домашняя: ~/concepts/", "Название": "Полка"}, env=env_clean(HOME=str(home)))
    assert out == (home / "concepts" / "polka" / cfg["created"]).resolve()
    _r, out, cfg = apply(cwd, {"Папка": "мои/идеи/полка", "Название": "Полка"})                     # свой путь через «Other»
    assert out == (cwd / "мои" / "идеи" / "полка").resolve() and cfg["idea"]["folder_choice"] == "custom"


def test_request_words_move_or_warn_about_folder(tmp_path):
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    r, out, cfg = apply(repo, {"Название": "Полка"}, "--request", "!concept полка, сохрани вне репозитория")
    assert cfg["output"]["inside_repo"] is False and out == (tmp_path / "concept-polka" / cfg["created"]).resolve()
    assert "Папка взята из запроса" in r.stdout
    r, out, cfg = apply(repo, {"Папка": "Текущая папка: concept/ (Recommended)", "Название": "Полка"}, "--request", "положи вне репозитория")
    assert cfg["output"]["inside_repo"] is True and cfg["output"]["folder_conflict"] is True and "ВНИМАНИЕ" in r.stdout


def test_concept_defaults_autopilot(tmp_path):
    r = run("intake.py", "concept-defaults", "--repo", tmp_path, "--idea", IDEA)
    assert r.returncode == 0, r.stderr
    out = Path(next(line[4:] for line in r.stdout.splitlines() if line.startswith("OUT=")))
    cfg = json.loads((out / "build" / "run-config.json").read_text(encoding="utf-8"))
    a = cfg["idea"]["answers"]
    assert cfg["autopilot"] is True and cfg["mode"] == "concept" and len(a) == 15 and all(x["default"] for x in a.values())
    assert any("Автопилот: 15 вопросов" in x for x in cfg["assumptions"]) and cfg["idea"]["unanswered"] == []
    assert "вопросов отвечено 15 из 15" in r.stdout and cfg["product"]["type"] == "saas"


# ---------- from-text: метки и фразы режима идеи ----------
@pytest.mark.parametrize("text,pitch", [
    ("!concept приложение для обмена книгами", "приложение для обмена книгами"),
    ("concept: бот для учёта лекарств", "бот для учёта лекарств"),
    ("!идея сервис аренды инструментов", "сервис аренды инструментов"),
])
def test_from_text_concept_marks(text, pitch):
    f = intake.from_text(text)
    assert f["mode"] == "concept" and f["idea.pitch"] == pitch and "mode_confirm" not in f


@pytest.mark.parametrize("text", ["У меня идея продукта: маркетплейс репетиторов", "Нужна концепция продукта для кофеен",
                                  "сделай концепцию нового продукта"])
def test_from_text_concept_phrases_need_confirmation(text):
    f = intake.from_text(text)
    assert f["mode"] == "concept" and f["mode_confirm"] is True


def test_from_text_normal_request_has_no_mode():
    assert "mode" not in intake.from_text("Сделай стратегию роста на 18 месяцев, 120 предложений")


# ---------- досье ----------
@pytest.fixture
def concept_out(tmp_path):
    _r, out, _cfg = apply(tmp_path, {"Вопросов": "25 (Recommended)", "Форма": "Мобильное приложение", "Аналоги": "Сервис А",
                                    "Область": ["Деньги и платежи"], "Название": "Книгообмен"})
    return out


def test_dossier_creates_files_and_is_idempotent(concept_out):
    out = concept_out
    r = run("concept_dossier.py", out)
    assert r.returncode == 0, r.stderr
    files = ["research/idea-dossier.md", "data/idea.json", "research/product-understanding.md", "build/search-plan.md", "build/seeds.md"]
    snap = {f: (out / f).read_bytes() for f in files}
    assert run("concept_dossier.py", out).returncode == 0
    assert {f: (out / f).read_bytes() for f in files} == snap                                  # идемпотентно
    dossier = (out / "research" / "idea-dossier.md").read_text(encoding="utf-8")
    for theme in ("Проблема и боль", "Аудитория", "Модель и деньги", "Риски, право, критерии успеха"):
        assert "### " + theme in dossier
    assert "не отвечено →" in dossier and "## Выводы" in dossier and "## Открытые вопросы" in dossier and "мобильное приложение" in dossier
    pu = (out / "research" / "product-understanding.md").read_text(encoding="utf-8")
    assert "Продукта ещё нет: концепция по идее и ответам владельца" in pu
    idea = json.loads((out / "data" / "idea.json").read_text(encoding="utf-8"))
    assert idea["product_type"] == "mobile" and idea["legal"] is True and idea["sensitive"] == ["finance"] and idea["open_questions"]
    plan = (out / "build" / "search-plan.md").read_text(encoding="utf-8")
    assert "RU: `" in plan and "EN: `" in plan and "Сервис А" in plan and "**45**" in plan
    seeds = (out / "build" / "seeds.md").read_text(encoding="utf-8")
    assert "SOL-" in seeds and "| PRD-" in seeds                                                 # профиль zero-budget-solo
    assert "/Users/" not in dossier + plan + seeds


def test_dossier_does_not_overwrite_manual_edits(concept_out):
    out = concept_out
    assert run("concept_dossier.py", out).returncode == 0
    (out / "research" / "idea-dossier.md").write_text("# Досье, правленное вручную\n", encoding="utf-8")
    r = run("concept_dossier.py", out)
    assert r.returncode == 0 and "правились вручную" in r.stderr
    assert (out / "research" / "idea-dossier.md").read_text(encoding="utf-8") == "# Досье, правленное вручную\n"
    assert (out / "research" / "idea-dossier.generated.md").is_file()


def test_dossier_refuses_normal_mode(tmp_path):
    (tmp_path / "o" / "build").mkdir(parents=True)
    (tmp_path / "o" / "build" / "run-config.json").write_text(json.dumps(intake.finalize(intake.base_config(tmp_path))), encoding="utf-8")
    assert run("concept_dossier.py", tmp_path / "o").returncode == 2


# ---------- предпроверка жизнеспособности ----------
def test_typesafe_concept_without_key_is_heuristic(concept_out):
    r = run("typesafe_concept.py", concept_out)
    assert r.returncode == 0, r.stderr
    d = json.loads((concept_out / "data" / "typesafe-concept.json").read_text(encoding="utf-8"))
    assert d["source"] == "heuristic" and d["confidence"] == "low" and d["skipped"] == "TYPESAFE_API_KEY не задан"
    assert set(d["items"]) == {"pain", "reach", "switch", "distinct", "feasible", "revenue", "timing", "ban_risk"}
    assert all(0 < v["p"] < 1 and v["note"] for v in d["items"].values())
    assert d["verdict"] in ("green", "yellow", "red") and d["thresholds"]["red_risk"] == 0.7
    assert "TYPESAFE" not in json.dumps(d["items"])


def test_typesafe_concept_off_and_dry_run(concept_out):
    cfgp = concept_out / "build" / "run-config.json"
    cfg = json.loads(cfgp.read_text(encoding="utf-8"))
    cfg["tools"]["typesafe"] = "off"
    cfgp.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    r = run("typesafe_concept.py", concept_out, "--dry-run", env=env_clean(TYPESAFE_API_KEY="sk-test-не-печатать-1234567890abcdef"))
    assert r.returncode == 0 and "Контекст (обезличенный)" in r.stdout and "sk-test" not in r.stdout
    assert not (concept_out / "data" / "typesafe-concept.json").exists()
    r = run("typesafe_concept.py", concept_out, env=env_clean(TYPESAFE_API_KEY="sk-test-не-печатать-1234567890abcdef"))
    d = json.loads((concept_out / "data" / "typesafe-concept.json").read_text(encoding="utf-8"))
    assert d["source"] == "heuristic" and "tools.typesafe = off" in d["skipped"] and "sk-test" not in r.stdout + r.stderr


def test_typesafe_concept_uses_api_when_key_present(concept_out):
    seen = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
            seen["auth"], seen["body"] = self.headers.get("Authorization"), body
            ans = {k: {"noul": 0.8 if k != "ban_risk" else 0.1} for k in body["questions"]}
            data = json.dumps({"model": "jev-test", "answers": ans}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = run("typesafe_concept.py", concept_out, env=env_clean(TYPESAFE_API_KEY="k-123", TYPESAFE_API_URL="http://127.0.0.1:%d/" % srv.server_port))
    finally:
        srv.shutdown()
    assert r.returncode == 0, r.stderr
    d = json.loads((concept_out / "data" / "typesafe-concept.json").read_text(encoding="utf-8"))
    assert d["source"] == "jev" and d["model"] == "jev-test" and d["verdict"] == "green" and d["skipped"] is None
    assert seen["auth"] == "Bearer k-123" and len(seen["body"]["questions"]) == 8
    state = json.dumps(seen["body"]["state"], ensure_ascii=False)
    assert str(concept_out) not in state and "/Users/" not in state and "k-123" not in state


def test_mask_and_verdict_thresholds():
    m = typesafe_concept.mask("пиши на a.b@example.com, ключ " + "sk" + "-" + "abcdefghijklmnopqrstuvwx" + ", файл /Users/x/secret.txt, тел. +7 912 345-67-89")
    assert "@" not in m and "sk-" not in m and "/Users/" not in m and "912" not in m
    it = lambda **kw: {k: {"p": kw.get(k, 0.7)} for k in typesafe_concept.QUESTIONS}
    assert typesafe_concept.verdict(it(ban_risk=0.1))[0] == "green"
    assert typesafe_concept.verdict(it(ban_risk=0.75))[0] == "red"                              # высокий риск запрета
    assert typesafe_concept.verdict(it(ban_risk=0.1, reach=0.2))[0] == "red"                    # критичный вопрос ниже 0,25
    assert typesafe_concept.verdict(it(ban_risk=0.1, revenue=0.3))[0] == "yellow"


# ---------- init_run: фазы C0–C9 ----------
def test_init_run_concept_phases(concept_out):
    r = run("init_run.py", concept_out)
    assert r.returncode == 0 and "ВНЕ git-репозитория" in r.stderr
    st = (concept_out / "build" / "STATUS.md").read_text(encoding="utf-8")
    assert "# STATUS — концепция Книгообмен" in st and "- [ ] C0. " in st and "- [ ] C5.5. " in st and "- [ ] C9. " in st
    assert "фазы C0–C9" in (concept_out / "STRATEGY_TASKS.md").read_text(encoding="utf-8")
    assert run("init_run.py", concept_out, "--done", "0").returncode == 0                        # «0» = «C0»
    assert run("init_run.py", concept_out, "--done", "C1").returncode == 0
    assert "Следующая фаза: C2." in run("init_run.py", concept_out, "--show").stdout


# ---------- сквозной демо-прогон ----------
def _concept_demo(tmp_path):
    out = tmp_path / "cdemo"
    r = run("make_concept_demo.py", out, "--proposals", "60")
    assert r.returncode == 0, r.stderr
    return out


def test_concept_demo_files(tmp_path):
    out = _concept_demo(tmp_path)
    cfg = json.loads((out / "build" / "run-config.json").read_text(encoding="utf-8"))
    assert cfg["mode"] == "concept" and cfg["idea"]["pitch"].startswith("Демо") and "c40" in cfg["idea"]["unanswered"]
    comp = json.loads((out / "data" / "competitors.json").read_text(encoding="utf-8"))
    assert comp[0]["self"] and comp[0]["planned"] and {c["kind"] for c in comp[1:]} == {"direct", "indirect", "substitute", "analog", "inspiration", "anti"}
    props = json.loads((out / "data" / "proposals.json").read_text(encoding="utf-8"))
    assert all(p["current_feature"].startswith("нет") and p["tags"][0] in ("mvp", "v1", "later") for p in props)
    assert all(e["kind"] not in ("repo", "own_app") for p in props for e in p["evidence"])
    ts = json.loads((out / "data" / "typesafe-concept.json").read_text(encoding="utf-8"))
    assert ts["source"] == "heuristic" and ts["skipped"]
    swot = json.loads((out / "data" / "swot.json").read_text(encoding="utf-8"))
    assert all(len(swot[k]) >= 4 for k in ("strengths", "weaknesses", "opportunities", "threats"))
    assert len(json.loads((out / "data" / "personas.json").read_text(encoding="utf-8"))) == 3
    for f in (out / "mockups" / "concepts").glob("M*.html"):
        assert "Концепт продукта, не существующая функция" in f.read_text(encoding="utf-8")
    assert len(list((out / "mockups" / "concepts").glob("M*.html"))) >= cfg["scope"]["mockups_min"] == 8


def test_concept_demo_build_all_strict(tmp_path):
    out = _concept_demo(tmp_path)
    r = run("build_all.py", out, "--strict", "--skip", "pptx,pdf,smoke,mockups")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "всё собрано" in r.stdout and "режим идеи" in r.stdout and "dossier" in r.stdout and "Папка концепции" in r.stdout
    page = (out / "deliverables" / "index.html").read_text(encoding="utf-8")
    assert "<title>Концепция продукта Книжная полка (демо)</title>" in page
    assert 'id="viability"' in page and "Жизнеспособность идеи" in page and "Концепт продукта, не существующая функция" in page
    assert "Концепция нового продукта" in page and 'id="current"' not in page
    import re
    visible = re.sub(r"<script.*?</script>|<style>.*?</style>", "", page, flags=re.S)
    assert not re.search(r"репозитор|скан", visible, re.I)                                     # никаких «репозиторий/скан» в режиме идеи
    facts_r = run("facts_scaffold.py", out, "--stdout")
    assert "Продукта ещё нет (режим идеи)" in facts_r.stdout and "Светофор:" in facts_r.stdout
    assert "видимость репозитория" not in facts_r.stdout
    method = (out / "research" / "methodology.md").read_text(encoding="utf-8")
    assert "режим идеи: продукта ещё нет" in method and "app_run" not in method
    ga = run("gap_audit.py", out)
    assert ga.returncode == 0, ga.stderr
    facts = json.loads((out / "data" / "gap-audit-facts.json").read_text(encoding="utf-8"))
    assert facts["mode"] == "concept" and {"legal_entity", "prototype", "first_users", "platform_accounts"} <= {f["key"] for f in facts["families"]}
    assert "Режим идеи: продукта ещё нет" in (out / "build" / "gap-audit-facts.md").read_text(encoding="utf-8")


def _node_dir_with(mod):
    for d in (os.environ.get("PS_NODE_DIR"), str(SCRIPTS / "node"), str(Path.home() / ".cache" / "product-strategy" / "node")):
        if d and (Path(d) / "node_modules" / mod / "package.json").exists():
            return d
    return None


@pytest.mark.skipif(not shutil.which("node") or not _node_dir_with("playwright"), reason="нет node/playwright (check_env.py --install-node)")
def test_concept_demo_build_all_strict_full(tmp_path):
    out = _concept_demo(tmp_path)
    r = run("build_all.py", out, "--strict", env=env_clean(PS_NODE_DIR=_node_dir_with("playwright")))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "всё собрано" in r.stdout
    for step in ("mockups", "smoke"):
        assert any(line.split()[:2] == [step, "OK"] for line in r.stdout.splitlines()), r.stdout


def test_concept_batches_are_balanced_no_single_question_tail():
    for n in (15, 20, 25, 31, 40):
        sizes = [len(b["questions"]) for b in intake.concept_questions_json(n)["batches"]]
        assert sum(sizes) == n and max(sizes) <= 4 and max(sizes) - min(sizes) <= 1 and min(sizes) >= 2


def test_set_tools_off_stays_string_mode():
    cfg = intake.base_config(".")
    intake._apply_sets(cfg, ["tools.typesafe=off", "scope.experiments=5"])
    assert cfg["tools"]["typesafe"] == "off" and cfg["scope"]["experiments"] == 5
