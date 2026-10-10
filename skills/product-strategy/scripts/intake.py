#!/usr/bin/env python3
"""Опрос владельца перед стратегией → build/run-config.json (references/intake.md, references/data-contract.md).

  intake.py questions [--round N] [--repo .]         вопросы раунда N (1–5) в формате AskUserQuestion (JSON); без --round — все
  intake.py open [--json]                             открытые вопросы: карточки AskUserQuestion (--json) или текстом
  intake.py apply --repo . (--answers answers.json | --from-askuser '<json>') [--open open.json] [--set key=value …]
                  [--out-dir DIR]                     ответы → run-config.json; печатает путь <OUT> и сводку.
                                                      --from-askuser принимает ответ AskUserQuestion как есть (ключи — текст
                                                      вопроса или header; значение — label, список label или свой текст), в том
                                                      числе и для открытых вопросов: отдельный open.json не нужен
  intake.py defaults --repo . [--set …] [--out-dir DIR]   конфиг по умолчанию (автопилот, без вопросов)
  intake.py from-text "<текст запроса>" [--repo .]   явные параметры из текста запроса (число предложений, глубина,
                                                      горизонт, рынки, форматы) → JSON overrides для --set; что найдено,
                                                      не переспрашивать
  intake.py show <run-config.json>                    сводка для подтверждения «старт»
  intake.py detect --repo . [--json]                  есть ли прошлые стратегии репозитория (strategy/*/, ../<repo>-strategy/*/,
                                                      PS_STRATEGY_DIR): кандидаты, выбор по умолчанию (самая свежая полная) и
                                                      карточки AskUserQuestion («Режим», «Стратегия») для режима «Отслеживание»
  intake.py track --repo . [--baseline OUT] [--mode track|update] [--set …]
                                                      режим «Отслеживание»: проверить стратегию, дописать tracking в её run-config
                                                      (mode, baseline), напечатать OUT=… и дальнейшие команды; без --baseline берётся
                                                      выбор по умолчанию (автоопределение)

answers.json — {"<header вопроса>": "<label выбранного варианта>" | ["label", …] | "свой текст"} (как вернул
AskUserQuestion; «Other» — свой текст). --set — точечные пути: strategy.proposals_min=150, scope.competitors=false.
Только стандартная библиотека.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

DEPTH = {  # глубина → значения по умолчанию объёма (references/phases.md, таблица масштабирования)
    "quick": {"proposals_min": 50, "competitors_min": 6, "mockups_min": 6, "experiments": 3, "specs_top": 5, "kanban_cards": 20},
    "standard": {"proposals_min": 100, "competitors_min": 10, "mockups_min": 12, "experiments": 8, "specs_top": 10, "kanban_cards": 40},
    "deep": {"proposals_min": 120, "competitors_min": 15, "mockups_min": 15, "experiments": 10, "specs_top": 15, "kanban_cards": 60},
    "exhaustive": {"proposals_min": 150, "competitors_min": 25, "mockups_min": 20, "experiments": 12, "specs_top": 20, "kanban_cards": 80},
}

# Раунды AskUserQuestion: не больше 4 вопросов, у вопроса 2–4 варианта (Other добавляет сам инструмент).
# Каждый вариант: (label, description, {путь: значение}). Рекомендуемый — первый, с «(Recommended)».
ROUNDS = [
    ("Проект", [
        ("Цель", "Какова цель проекта и его модель?", False, [
            ("Определить по репозиторию (Recommended)", "Определю по лицензии, видимости, монетизации в коде и README; решение запишу в допущения",
             {"project.goal": "auto"}),
            ("Личный инструмент", "Делаю для себя; главный вопрос — нужен ли он другим и открывать ли код", {"project.goal": "personal"}),
            ("Open-source", "Открытый проект: сообщество, вклад, спонсорство, релизный ритм", {"project.goal": "oss"}),
            ("Коммерческий продукт", "Выручка и рост аудитории: воронка, тарифы, каналы", {"project.goal": "commercial"}),
        ]),
        ("Видимость", "Репозиторий публичный или приватный?", False, [
            ("Определить через gh (Recommended)", "gh repo view, только чтение; нет gh — отмечу как неизвестно", {"project.repo_visibility": "unknown"}),
            ("Публичный", "Код открыт всем", {"project.repo_visibility": "public"}),
            ("Приватный", "Код закрыт; открытие — отдельное решение стратегии", {"project.repo_visibility": "private"}),
        ]),
        ("Команда", "Сколько человек работает над проектом?", False, [
            ("Один разработчик (Recommended)", "Ёмкость плана — дни одного человека; включаю профиль «нулевой бюджет, один разработчик», если бюджет нулевой",
             {"project.team_size": 1}),
            ("2–5 человек", "Небольшая команда", {"project.team_size": 3}),
            ("Больше пяти", "Команда с ролями", {"project.team_size": 8}),
        ]),
        ("Валюта", "В какой валюте считать деньги?", False, [
            ("По рынкам (Recommended)", "RU → RUB, остальное → USD; решение запишу в допущения", {"project.currency": "auto"}),
            ("RUB", "Рубли", {"project.currency": "RUB"}),
            ("USD", "Доллары США", {"project.currency": "USD"}),
            ("EUR", "Евро", {"project.currency": "EUR"}),
        ]),
    ]),
    ("Цель и объём", [
        ("Стратегия", "Какую стратегию готовим?", False, [
            ("Рост продукта (Recommended)", "Аудитория, активация, удержание, монетизация, каналы — полная продуктовая и маркетинговая стратегия роста",
             {"strategy.kind": "growth"}),
            ("Полная: рост + технологии", "Рост плюс технологическая дорожная карта, платформа, долг, архитектура на годы",
             {"strategy.kind": "full"}),
            ("Монетизация", "Модель дохода, тарифы, платный уровень, юнит-экономика, платёжные пути", {"strategy.kind": "monetization"}),
            ("Выход на рынок (GTM)", "Запуск или выход на новые рынки: позиционирование, каналы, запуск", {"strategy.kind": "gtm"}),
        ]),
        ("Глубина", "Насколько глубоко прорабатываем?", False, [
            ("Стандарт (Recommended)", "≈100 предложений, 10+ конкурентов, 12+ макетов, 8 экспериментов, спеки топ-10", {"strategy.depth": "standard"}),
            ("Глубоко", "≈120 предложений, 15+ конкурентов, 15+ макетов, спеки топ-15", {"strategy.depth": "deep"}),
            ("Максимально", "≈150 предложений, 25+ конкурентов, 20+ макетов, спеки топ-20 — долго и дорого", {"strategy.depth": "exhaustive"}),
            ("Быстро", "≈50 предложений, 6 конкурентов, 6 макетов — черновик за короткий прогон", {"strategy.depth": "quick"}),
        ]),
        ("Предложения", "Сколько предложений проработать в реестре (минимум после дедупликации)?", False, [
            ("100 (Recommended)", "Каждое с доказательством, шагами, оценками и KPI", {"strategy.proposals_min": 100}),
            ("50", "Минимум: только сильные идеи", {"strategy.proposals_min": 50}),
            ("150", "Широкий охват, включая многолетние ставки", {"strategy.proposals_min": 150}),
            ("200", "Максимальный охват; дольше генерация и оценка", {"strategy.proposals_min": 200}),
        ]),
        ("Горизонт", "На какой срок план и видение?", False, [
            ("12 мес + видение 3 года (Recommended)", "План 30/60/90 дней, 6 и 12 месяцев + ставки на 2–3 года",
             {"strategy.horizon_months": 12, "strategy.vision_years": 3}),
            ("6 мес + видение 2 года", "Короткий план и ориентиры", {"strategy.horizon_months": 6, "strategy.vision_years": 2}),
            ("18 мес + видение 5 лет", "Длинный план для инвесторов и платформенных ставок", {"strategy.horizon_months": 18, "strategy.vision_years": 5}),
            ("3 мес тактика", "Только ближайшие шаги, без видения", {"strategy.horizon_months": 3, "strategy.vision_years": 0}),
        ]),
    ]),
    ("Что анализируем", [
        ("Источники", "Что анализировать о самом продукте? (можно несколько)", True, [
            ("Текущий репозиторий (Recommended)", "Код, манифесты, маршруты, функции, i18n, интеграции, git-история — только чтение",
             {"scope.repo_analysis": True, "sources.repo": True}),
            ("Запуск приложения", "Запустить локально по README и пройти пути пользователя в браузере (тестовые данные)",
             {"scope.app_run": True}),
            ("Публичный сайт/URL", "Открыть продукт по адресу: скриншоты, дизайн-токены, SEO-теги (адрес спрошу отдельно)",
             {"product.local_run": "none", "scope.app_run": True}),
            ("Issues и PR GitHub", "Карта спроса из Issues/PR (gh, только чтение)", {"scope.issues": True, "sources.issues": True}),
        ]),
        ("Исследования", "Какие внешние исследования нужны? (можно несколько)", True, [
            ("Конкуренты (Recommended)", "Альтернативы и косвенные конкуренты: функции, цены, где лучше они/мы, их лучшие решения и дизайн, скриншоты",
             {"scope.competitors": True}),
            ("Сообщества и каналы", "Площадки аудитории, правила самопродвижения, риск бана", {"scope.communities": True}),
            ("Спрос и события", "Запросы и кластеры, календарь отраслевых событий", {"scope.keywords": True, "scope.events": True}),
            ("Право, IP, платежи", "Лицензии, приватность (GDPR, 152-ФЗ), правила платформ, платёжные ограничения", {"scope.legal": True}),
        ]),
        ("Дизайн", "Нужны ли макеты и референсы дизайна?", False, [
            ("Макеты + референсы (Recommended)", "Детальные HTML-макеты в стиле продукта, карточки референсов с кликабельными зонами, дизайн конкурентов",
             {"scope.design_mockups": True, "scope.design_refs": True}),
            ("Только макеты", "Макеты предложений без карточек для постановки задач", {"scope.design_mockups": True, "scope.design_refs": False}),
            ("Без дизайна", "Только текст, реестр и графики", {"scope.design_mockups": False, "scope.design_refs": False, "scope.mockups_min": 0}),
        ]),
        ("Экономика", "Нужна ли финансовая модель?", False, [
            ("Да, 3 сценария (Recommended)", "Воронка AARRR, CAC, LTV, окупаемость, ARPU, отток, ROI — параметры редактируемы",
             {"scope.unit_economics": True}),
            ("Только качественно", "Без расчётов, оценки диапазонами", {"scope.unit_economics": False}),
        ]),
    ]),
    ("Рынки и деньги", [
        ("Рынки", "На какие рынки и языки ориентируемся?", False, [
            ("Определи сам (Recommended)", "По продукту, локалям в коде и аудитории; решение запишу в допущения", {"strategy.markets": ["auto"]}),
            ("RU + EN", "Русскоязычный и англоязычный рынки", {"strategy.markets": ["ru", "en"]}),
            ("Только RU", "Россия и СНГ", {"strategy.markets": ["ru"]}),
            ("Глобально", "EN + крупные локали (es, pt, de, fr, ja…)", {"strategy.markets": ["en", "es", "pt", "de", "fr", "ja"]}),
        ]),
        ("Бюджет", "Какой бюджет закладывать?", False, [
            ("Три варианта (Recommended)", "Нулевой, малый и средний — для каждого свой набор действий", {"strategy.budget.variants": ["zero", "small", "medium"]}),
            ("Нулевой", "Только своими силами, без затрат", {"strategy.budget.variants": ["zero"]}),
            ("Малый", "Небольшие траты на инструменты и продвижение", {"strategy.budget.variants": ["small"]}),
            ("Средний", "Платные каналы, подрядчики, инструменты", {"strategy.budget.variants": ["medium"]}),
        ]),
        ("Монетизация", "Что с монетизацией?", False, [
            ("Оценить (Recommended)", "Определю, нужен ли платный уровень, и предложу границы и цены", {"strategy.paid_tier": "auto"}),
            ("Уже есть", "Оптимизировать существующую монетизацию", {"strategy.paid_tier": "yes"}),
            ("Не нужен", "Модель устойчивости: спонсорство, гранты, услуги", {"strategy.paid_tier": "no"}),
        ]),
        ("Форматы", "В каких форматах нужен результат? (можно несколько)", True, [
            ("Веб-страница (Recommended)", "Интерактивная офлайн-страница: реестр с фильтрами, Гант, Kanban, макеты, конкуренты", {"formats.html": True}),
            ("XLSX", "Реестр, оценки с формулами и весами, модель, источники, KPI, Kanban", {"formats.xlsx": True}),
            ("PPTX", "Презентация 40–60 слайдов + приложение", {"formats.pptx": True}),
            ("PDF", "PDF-версия презентации", {"formats.pdf": True}),
        ]),
    ]),
    ("Место и инструменты", [
        ("Папка", "Где сохранить результат?", False, [
            ("В репозитории strategy/ (Recommended)", "<repo>/strategy/<дата>/ в отдельной ветке docs/strategy-<дата>", {"output.inside_repo": True}),
            ("Рядом с репозиторием", "../<repo>-strategy/<дата>/ — репозиторий не меняется вовсе", {"output.inside_repo": False}),
        ]),
        ("TypeSafe", "Оценивать предложения TypeSafe (Jev) отдельной колонкой?", False, [
            ("Да, если есть ключ (Recommended)", "Узкие вероятностные вопросы к каждому предложению; ключ из TYPESAFE_API_KEY", {"tools.typesafe": "auto"}),
            ("Нет", "Только экспертные шкалы и формулы", {"tools.typesafe": "off"}),
        ]),
        ("Субагенты", "Распараллеливать работу субагентами?", False, [
            ("Да, до 5 (Recommended)", "Исследования, генерация предложений, тексты разделов, макеты — параллельно", {"tools.subagents": True, "tools.max_parallel_agents": 5}),
            ("Да, до 3", "Экономнее по токенам", {"tools.subagents": True, "tools.max_parallel_agents": 3}),
            ("Без субагентов", "Всё в одной сессии: дольше, дешевле", {"tools.subagents": False, "tools.max_parallel_agents": 1}),
        ]),
        ("Установка", "Если не хватает инструментов?", False, [
            ("Локально сам, остальное спросить (Recommended)", "Node-модули и Chromium — в папку прогона без вопроса; pip, brew, плагины — после вашего «да»",
             {"tools.install": "local-auto"}),
            ("Всегда спрашивать", "Ничего не ставить без подтверждения", {"tools.install": "ask"}),
            ("Не ставить", "Работать с тем, что есть; недоступное — заменить и отметить в отчёте", {"tools.install": "never"}),
        ]),
    ]),
]

OPEN_QUESTIONS = [   # (путь, текст для текстового режима)
    ("product.name", "Название продукта и одна фраза — что он делает (если не очевидно из репозитория)."),
    ("product.url", "Публичный адрес продукта или команда локального запуска (если есть)."),
    ("product.known_facts", "Что известно: аудитория, трафик, конверсии, доход, цены, каналы — любые цифры (можно «нет данных»)."),
    ("sources.competitor_list", "Известные вам конкуренты и продукты-образцы (названия или ссылки)."),
    ("strategy.constraints", "Ограничения и что вне задачи (бюджет, сроки, запретные каналы, юрисдикции, команда)."),
    ("sources.owner_docs", "Дополнительные материалы: пути к документам, выгрузкам аналитики, исследованиям."),
    ("author", "Автор стратегии для титула и подвалов: ФИО и ник (или «не указывать»)."),
    ("project.publish_code", "Готовы ли открыть код (если репозиторий закрыт)?"),
]
# Открытые вопросы как карточки AskUserQuestion: у каждого есть вариант-по-умолчанию и «Other» (свой текст идёт в поле).
# (путь, header, вопрос, [(label, description, значение|None)]); None — пропустить, значение по умолчанию остаётся.
OPEN_CARDS = [
    ("product.name", "Продукт", "Название продукта и суть в одной фразе?", [
        ("Определи по репозиторию (Recommended)", "README, манифесты, заголовки экранов", None),
        ("Уточню сам", "Впишу название и фразу в «Other»", "__text__")]),
    ("product.url", "Адрес", "Публичный адрес продукта или команда локального запуска?", [
        ("Найди в README и конфигах (Recommended)", "Если не найдётся — оценка по коду, уверенность ниже", None),
        ("Нет, только код", "Приложение не запускать и не открывать", ""),
        ("Укажу сам", "Адрес или команда в «Other»", "__text__")]),
    ("product.known_facts", "Цифры", "Известны ли аудитория, трафик, конверсии, доход, цены?", [
        ("Нет данных (Recommended)", "Недостающее — допущения с метками и запрос данных владельцу", None),
        ("Есть, напишу", "Любые цифры в «Other»", "__text__"),
        ("Есть выгрузка", "Путь к файлу в «Other» (Search Console, аналитика, платежи)", "__owner_doc__")]),
    ("sources.competitor_list", "Конкуренты", "Есть ли известные конкуренты и образцы?", [
        ("Найди сам (Recommended)", "Поиск по задачам и функциям из репозитория", None),
        ("Есть список", "Названия или ссылки в «Other»", "__text__")]),
    ("strategy.constraints", "Ограничения", "Есть ли ограничения и что вне задачи?", [
        ("Нет ограничений (Recommended)", "Бюджет — по ответу выше, остальное свободно", None),
        ("Без платной рекламы", "Только органические и бесплатные каналы", "Без платной рекламы"),
        ("Есть другие", "Опишу в «Other»: сроки, юрисдикции, запретные каналы", "__text__")]),
    ("sources.owner_docs", "Материалы", "Есть ли документы, выгрузки или исследования для анализа?", [
        ("Нет (Recommended)", "Только репозиторий и публичные источники", None),
        ("Есть, укажу пути", "Пути в «Other»", "__text__")]),
    ("author", "Автор", "Кого указать автором стратегии в титуле и подвалах?", [
        ("Не указывать (Recommended)", "Без имени", None),
        ("Взять из git", "Имя из git config user.name", "__git__"),
        ("Укажу сам", "ФИО и ник в «Other», например: Иванов Иван (ivanov)", "__text__")]),
    ("project.publish_code", "Код", "Готовы ли открыть код проекта, если он закрыт?", [
        ("Решить по итогам стратегии (Recommended)", "Рассмотрю плюсы и минусы открытия как отдельное предложение", "undecided"),
        ("Да, готов открыть", "Предложения по публикации учитывают открытый код", "yes"),
        ("Нет, остаётся закрытым", "Предложения, требующие открытого кода, не рассматриваются", "no")]),
]


def set_path(cfg, path, value):
    node = cfg
    parts = path.split(".")
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def parse_value(s):
    low = s.strip().lower()
    if low in ("true", "yes", "да", "on"):
        return True
    if low in ("false", "no", "нет", "off"):
        return False
    if re.fullmatch(r"-?\d+", low):
        return int(low)
    if low.startswith("[") or low.startswith("{"):
        try:
            return json.loads(s)
        except ValueError:
            pass
    return s


def git_info(repo):
    def g(*args):
        try:
            r = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True, timeout=10)
            return r.stdout.strip() if r.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""
    top = g("rev-parse", "--show-toplevel")
    url = g("remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", url)
    return (Path(top) if top else Path(repo).resolve()), (m.group(1) if m else None)


def base_config(repo, out_dir=None):
    top, remote = git_info(repo)
    today = date.today().isoformat()
    cfg = {
        "version": 1, "created": today, "author": {"name": "", "nick": "", "copyright": ""},
        "repo": {"path": str(top), "name": top.name, "remote": remote, "analyze": True},
        "product": {"name": top.name, "url": "", "local_run": "auto", "run_command": "", "type": "auto", "known_facts": ""},
        "strategy": {"kind": "growth", "goal": "рост и развитие продукта: аудитория, активация, удержание, монетизация",
                     "depth": "standard", "proposals_min": 100, "horizon_months": 12, "vision_years": 3, "markets": ["auto"],
                     "budget": {"variants": ["zero", "small", "medium"], "note": ""}, "paid_tier": "auto", "constraints": "",
                     "categories_na": [], "profile": "auto"},
        "project": {"goal": "auto", "repo_visibility": "unknown", "publish_code": "undecided", "currency": "auto", "price_hint": None,
                    "traffic_hint": None, "team_size": None},
        "scope": {"repo_analysis": True, "app_run": True, "competitors": True, "competitors_min": 10, "communities": True,
                  "keywords": True, "events": True, "legal": True, "issues": bool(remote), "design_mockups": True, "mockups_min": 12,
                  "design_refs": True, "unit_economics": True, "experiments": 8, "specs_top": 10, "kanban_cards": 40},
        "sources": {"repo": True, "issues": bool(remote), "web_search": True, "web_search_budget_per_hour": 100,
                    "analytics_exports": [], "owner_docs": [], "competitor_list": [], "other": ""},
        "formats": {"html": True, "xlsx": True, "pptx": True, "pdf": True, "md": True},
        "tools": {"typesafe": "auto", "browser": "auto", "subagents": True, "max_parallel_agents": 5, "install": "local-auto", "node_dir": None},
        "phases": {"gap_audit": True},
        "output": {"dir": "", "inside_repo": True, "git_branch": "docs/strategy-%s" % today},
        "language": "ru", "autopilot": False, "assumptions": [],
    }
    if out_dir:
        cfg["output"]["dir"] = str(Path(out_dir).resolve())
    return cfg


def _read_readme(repo):
    for n in ("README.md", "README.rst", "README.txt", "README"):
        p = Path(repo) / n
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8", errors="replace")[:20000]
            except OSError:
                return ""
    return ""


def _detect_markets(repo):
    """Рынки по репозиторию: кириллица в README и языки локалей (locales/ru.json, i18n/…). → (список языков, причина)."""
    text = _read_readme(repo)
    cyr = len(re.findall(r"[А-Яа-яЁё]", text))
    lat = len(re.findall(r"[A-Za-z]", text))
    langs = []
    if cyr > max(40, lat * 0.2):
        langs.append("ru")
    skip = {"node_modules", "venv", ".venv", "site-packages", "build", "dist", ".git"}
    for loc in ("locales", "i18n", "lang", "translations", "locale"):
        for d in Path(repo).rglob(loc):
            if d.is_dir() and not (skip & set(d.parts)):
                for f in list(d.iterdir())[:40]:
                    m = re.match(r"^([a-z]{2})(?:[-_][A-Za-z]{2})?$", f.stem if f.is_file() else f.name)
                    if m and m.group(1) not in langs:
                        langs.append(m.group(1))
        if len(langs) > 6:
            break
    if "en" not in langs:
        langs.append("en")
    return langs[:6], ("кириллица в README: %d знаков" % cyr) if cyr else "README без кириллицы"


def _detect_type(repo):
    root = Path(repo)
    names = {p.name for p in root.iterdir()} if root.is_dir() else set()
    blob = ""
    for n in ("package.json", "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg"):
        if n in names:
            try:
                blob += (root / n).read_text(encoding="utf-8", errors="replace")[:20000].lower()
            except OSError:
                pass
    has_manifest = any(root.glob("android/app/src/main/AndroidManifest.xml")) or any(root.glob("ios/*.xcodeproj")) or "AndroidManifest.xml" in names
    if has_manifest or re.search(r"react-native|flutter|expo", blob):
        return "mobile", "манифест Android/Xcode или react-native/flutter"
    if re.search(r'"bin"\s*:|console_scripts|\[project\.scripts\]|entry_points', blob):
        return "devtool", "CLI-точка входа в манифесте"
    if re.search(r"fastapi|flask|django|express|next|react|vue|svelte|aiohttp|starlette", blob):
        return "saas", "веб-фреймворк в зависимостях"
    if re.search(r"discord|telegram|aiogram|telebot|vk_api|slack", blob):
        return "bot", "библиотека бота в зависимостях"
    return "other", "тип не определён по манифестам"


def resolve_auto(cfg):
    """Значения auto → конкретные (markets, product.type, project.currency, strategy.profile); решения — в assumptions."""
    repo = cfg["repo"]["path"]
    s, pr, prj = cfg["strategy"], cfg["product"], cfg["project"]
    if s["markets"] in (["auto"], [], "auto"):
        langs, why = _detect_markets(repo)
        s["markets"] = langs
        cfg["assumptions"].append("Рынки определены по репозиторию: %s (%s)" % (", ".join(langs), why))
    if pr["type"] == "auto":
        t, why = _detect_type(repo)
        pr["type"] = t
        cfg["assumptions"].append("Тип продукта определён по репозиторию: %s (%s)" % (t, why))
    if prj["currency"] == "auto":
        prj["currency"] = "RUB" if s["markets"] and s["markets"][0] == "ru" else "USD"
        cfg["assumptions"].append("Валюта определена по первому рынку: %s" % prj["currency"])
    if prj["team_size"] is None:
        prj["team_size"] = 1
        cfg["assumptions"].append("Команда: 1 человек (по умолчанию; уточните, если иначе)")
    if s["profile"] == "auto":
        zero = s["budget"]["variants"] == ["zero"]
        solo = prj["team_size"] == 1 and (zero or prj["goal"] in ("personal", "oss"))
        s["profile"] = "zero-budget-solo" if solo else "standard"
        cfg["assumptions"].append("Профиль стратегии: %s" % s["profile"])
    return cfg


def finalize(cfg):
    """Глубина → объёмы (если пользователь не задал их явно), папка результата, мультивыбор → флаги, auto → решения."""
    resolve_auto(cfg)
    depth = DEPTH.get(cfg["strategy"]["depth"], DEPTH["standard"])
    explicit = set(cfg.pop("_explicit", []))
    if "strategy.proposals_min" not in explicit:     # явный ответ «Предложения» главнее глубины
        cfg["strategy"]["proposals_min"] = depth["proposals_min"]
    for k in ("competitors_min", "mockups_min", "experiments", "specs_top", "kanban_cards"):
        if "scope." + k not in explicit and not (k == "mockups_min" and not cfg["scope"]["design_mockups"]):
            cfg["scope"][k] = depth[k]
    cfg["strategy"]["proposals_min"] = max(50, int(cfg["strategy"]["proposals_min"]))
    if not cfg["output"]["dir"]:
        top = Path(cfg["repo"]["path"])
        today = cfg["created"]
        cfg["output"]["dir"] = str(top / "strategy" / today) if cfg["output"]["inside_repo"] \
            else str(top.parent / ("%s-strategy" % top.name) / today)
    if not cfg["author"].get("copyright") and (cfg["author"].get("name") or cfg["author"].get("nick")):
        who = " ".join(x for x in (cfg["author"].get("name"), "(%s)" % cfg["author"]["nick"] if cfg["author"].get("nick") else "") if x)
        cfg["author"]["copyright"] = "© %s %s" % (cfg["created"][:4], who)
    return cfg


def questions_json(round_no=None):
    out = []
    for i, (title, qs) in enumerate(ROUNDS, 1):
        if round_no and i != round_no:
            continue
        out.append({"round": i, "title": title, "questions": [
            {"header": h, "question": q, "multiSelect": multi, "options": [{"label": l, "description": d} for l, d, _ in opts]}
            for h, q, multi, opts in qs]})
    return out


def _find_option(header, label):
    for _, qs in ROUNDS:
        for h, _q, multi, opts in qs:
            if h == header:
                for l, _d, mapping in opts:
                    if l == label or l.replace(" (Recommended)", "") == label.replace(" (Recommended)", ""):
                        return multi, mapping
                return multi, None
    return False, None


CUSTOM_PATH = {  # свой ответ («Other») на вопрос → куда записать текст
    "Стратегия": "strategy.goal", "Бюджет": "strategy.budget.note", "Монетизация": "strategy.constraints",
    "Горизонт": "strategy.constraints", "Глубина": "strategy.constraints",
}

MULTI_OFF = {  # для мультивыбора: что выключается, если вариант НЕ выбран
    "Источники": {"Запуск приложения": {"scope.app_run": False}, "Issues и PR GitHub": {"scope.issues": False, "sources.issues": False},
                  "Текущий репозиторий (Recommended)": {"scope.repo_analysis": False, "sources.repo": False}},
    "Исследования": {"Конкуренты (Recommended)": {"scope.competitors": False}, "Сообщества и каналы": {"scope.communities": False},
                     "Спрос и события": {"scope.keywords": False, "scope.events": False}, "Право, IP, платежи": {"scope.legal": False}},
    "Форматы": {"Веб-страница (Recommended)": {"formats.html": False}, "XLSX": {"formats.xlsx": False},
                "PPTX": {"formats.pptx": False}, "PDF": {"formats.pdf": False}},
}


def apply_answers(cfg, answers):
    explicit = cfg.setdefault("_explicit", [])
    notes = []
    for header, ans in answers.items():
        labels = ans if isinstance(ans, list) else [x.strip() for x in str(ans).split(",")] if header in MULTI_OFF else [ans]
        if header in MULTI_OFF:
            chosen = set()
            for lab in labels:
                multi, mapping = _find_option(header, lab)
                if mapping is None:
                    notes.append("%s: свой ответ «%s» — учесть вручную" % (header, lab))
                    cfg["assumptions"].append("%s: %s" % (header, lab))
                    continue
                chosen.add(lab)
                for k, v in mapping.items():
                    set_path(cfg, k, v)
                    explicit.append(k)
            for lab, off in MULTI_OFF[header].items():
                if lab not in chosen and not any(lab.replace(" (Recommended)", "") == c.replace(" (Recommended)", "") for c in chosen):
                    for k, v in off.items():
                        set_path(cfg, k, v)
            continue
        lab = labels[0] if labels else ""
        multi, mapping = _find_option(header, lab)
        if mapping is None:
            m = re.search(r"\d+", str(lab))
            if header == "Предложения" and m:
                set_path(cfg, "strategy.proposals_min", int(m.group(0)))
                explicit.append("strategy.proposals_min")
            elif header == "Рынки":
                set_path(cfg, "strategy.markets", [x.strip() for x in re.split(r"[,;/ ]+", str(lab)) if x.strip()])
            elif header in CUSTOM_PATH:
                path = CUSTOM_PATH[header]
                node = cfg
                for part in path.split(".")[:-1]:
                    node = node[part]
                prev = node.get(path.split(".")[-1]) or ""
                set_path(cfg, path, (prev + "; " if prev and header != "Стратегия" else "") + str(lab))
            else:
                notes.append("%s: свой ответ «%s» — учесть вручную" % (header, lab))
                cfg["assumptions"].append("%s: %s" % (header, lab))
            continue
        for k, v in mapping.items():
            set_path(cfg, k, v)
            explicit.append(k)
    return notes


def open_cards_json():
    """Открытые вопросы как карточки AskUserQuestion: две пачки (до 4 вопросов в вызове); «Other» добавляет сам инструмент."""
    cards = [{"header": h, "question": q, "multiSelect": False, "options": [{"label": l, "description": d} for l, d, _ in opts]}
             for _k, h, q, opts in OPEN_CARDS]
    return [{"batch": 1, "questions": cards[:4]}, {"batch": 2, "questions": cards[4:]}]


def _git_user(repo):
    try:
        r = subprocess.run(["git", "-C", str(repo), "config", "user.name"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def apply_from_askuser(cfg, answers):
    """Ответ AskUserQuestion как есть: ключи — текст вопроса или header, значения — label, список label или свой текст.
    Вопросы раундов (ROUNDS) и открытые карточки (OPEN_CARDS) различаются автоматически. Возвращает заметки."""
    by_q, by_h = {}, {}
    for _t, qs in ROUNDS:
        for h, q, _m, _o in qs:
            by_q[q], by_h[h] = h, h
    open_by = {}
    for path, h, q, opts in OPEN_CARDS:
        open_by[q] = open_by[h] = (path, opts)
    rounds, notes = {}, []
    for k, v in (answers or {}).items():
        if k in open_by:
            path, opts = open_by[k]
            val = v[0] if isinstance(v, list) and v else v
            hit = next((o for o in opts if o[0] == val or o[0].replace(" (Recommended)", "") == str(val).replace(" (Recommended)", "")), None)
            if hit is not None:
                kind = hit[2]
                if kind is None:
                    continue
                if kind == "__text__":
                    notes.append("%s: выбран «%s», но текста нет — уточнить у владельца" % (path, hit[0]))
                    cfg["assumptions"].append("%s: владелец собирался уточнить, текста нет" % path)
                    continue
                if kind == "__owner_doc__":
                    notes.append("%s: нужен путь к файлу выгрузки — уточнить" % path)
                    continue
                if kind == "__git__":
                    name = _git_user(cfg["repo"]["path"])
                    if name:
                        cfg["author"]["name"] = name
                    continue
                set_path(cfg, path, kind)
            else:
                apply_open(cfg, {path: str(val)})
            continue
        rounds[by_q.get(k) or by_h.get(k) or k] = v
    notes += apply_answers(cfg, rounds)
    return notes


def apply_open(cfg, opened):
    for key, val in (opened or {}).items():
        if not val or str(val).strip().lower() in ("нет", "-", "пропустить", "не указывать"):
            continue
        if key == "author":
            m = re.match(r"\s*(.+?)\s*[\(\[,/]\s*@?([\w.-]+)\s*[\)\]]?\s*$", str(val))
            cfg["author"].update({"name": m.group(1), "nick": m.group(2)} if m else {"name": str(val).strip()})
        elif key in ("sources.competitor_list", "sources.owner_docs"):
            set_path(cfg, key, [x.strip() for x in re.split(r"[,;\n]", str(val)) if x.strip()])
        else:
            set_path(cfg, key, str(val).strip())


FROM_TEXT = [  # (регэксп, путь, функция значения)
    (r"(\d{2,3})\s*(?:предложени|идей|инициатив|proposals|ideas)", "strategy.proposals_min", lambda m: int(m.group(1))),
    (r"не\s+менее\s+(\d{2,3})", "strategy.proposals_min", lambda m: int(m.group(1))),
    (r"\b(быстр\w*|черновик|quick)\b", "strategy.depth", lambda m: "quick"),
    (r"\b(максимально подробн\w*|подробнейш\w*|exhaustive|исчерпывающ\w*)\b", "strategy.depth", lambda m: "exhaustive"),
    (r"\b(глубок\w*|детальн\w*|deep)\b", "strategy.depth", lambda m: "deep"),
    (r"(\d{1,2})\s*(?:мес|months?)", "strategy.horizon_months", lambda m: int(m.group(1))),
    (r"(\d)\s*(?:год|года|лет|years?)", "strategy.vision_years", lambda m: int(m.group(1))),
    (r"\bбез\s+(?:макетов|дизайна)\b", "scope.design_mockups", lambda m: False),
    (r"\bбез\s+конкурентов\b", "scope.competitors", lambda m: False),
    (r"\bбез\s+субагентов\b", "tools.subagents", lambda m: False),
    (r"\b(?:автопилот|без вопросов|autopilot)\b", "autopilot", lambda m: True),
]


def from_text(text):
    found = {}
    for rx, path, fn in FROM_TEXT:
        m = re.search(rx, text or "", re.I | re.U)
        if m and path not in found:
            found[path] = fn(m)
    return found


def show(cfg):
    s, sc, f = cfg["strategy"], cfg["scope"], cfg["formats"]
    lines = [
        "Продукт: %s (репозиторий %s%s)" % (cfg["product"]["name"], cfg["repo"]["path"], ", " + cfg["repo"]["remote"] if cfg["repo"]["remote"] else ""),
        "Стратегия: %s, глубина %s, предложений ≥ %d, горизонт %d мес + видение %d г." % (s["kind"], s["depth"], s["proposals_min"], s["horizon_months"], s["vision_years"]),
        "Анализ: репозиторий %s, запуск приложения %s, Issues %s" % (_yn(sc["repo_analysis"]), _yn(sc["app_run"]), _yn(sc["issues"])),
        "Исследования: конкуренты %s (≥%d), сообщества %s, спрос %s, события %s, право %s" % (
            _yn(sc["competitors"]), sc["competitors_min"], _yn(sc["communities"]), _yn(sc["keywords"]), _yn(sc["events"]), _yn(sc["legal"])),
        "Дизайн: макеты %s (≥%d), референсы %s; экономика %s; эксперименты %d; спеки топ-%d; Kanban %d карточек" % (
            _yn(sc["design_mockups"]), sc["mockups_min"], _yn(sc["design_refs"]), _yn(sc["unit_economics"]), sc["experiments"], sc["specs_top"], sc["kanban_cards"]),
        "Рынки: %s; бюджет: %s; платный уровень: %s" % (", ".join(s["markets"]), ", ".join(s["budget"]["variants"]), s["paid_tier"]),
        "Форматы: %s" % ", ".join(k for k, v in f.items() if v),
        "Инструменты: TypeSafe %s, субагенты %s (до %d), установка %s" % (
            cfg["tools"]["typesafe"], _yn(cfg["tools"]["subagents"]), cfg["tools"]["max_parallel_agents"], cfg["tools"].get("install", "local-auto")),
        "Проект: цель %s, репозиторий %s, команда %s, валюта %s, профиль %s" % (
            cfg["project"]["goal"], cfg["project"]["repo_visibility"], cfg["project"]["team_size"], cfg["project"]["currency"], s["profile"]),
        "Папка: %s%s" % (cfg["output"]["dir"], " (ветка %s)" % cfg["output"]["git_branch"] if cfg["output"]["inside_repo"] else ""),
    ]
    if cfg["author"].get("copyright"):
        lines.append("Авторство: %s" % cfg["author"]["copyright"])
    if cfg["assumptions"]:
        lines.append("Допущения: " + "; ".join(cfg["assumptions"]))
    return "\n".join(lines)


def _yn(v):
    return "да" if v else "нет"


def write_config(cfg):
    out = Path(cfg["output"]["dir"])
    (out / "build").mkdir(parents=True, exist_ok=True)
    p = out / "build" / "run-config.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _apply_sets(cfg, sets):
    for s in sets or []:
        k, _, v = s.partition("=")
        set_path(cfg, k.strip(), parse_value(v))
        cfg.setdefault("_explicit", []).append(k.strip())


# ---------- режим «Отслеживание»: поиск прошлых стратегий ----------
SKIP_DIRS = {"node_modules", "venv", ".venv", ".git", "site-packages", "__pycache__", "dist", "target", "vendor"}


def _strategy_info(out):
    """Сведения о папке стратегии по её run-config и данным; None, если это не стратегия."""
    cfgp = Path(out) / "build" / "run-config.json"
    if not cfgp.is_file():
        return None
    try:
        cfg = json.loads(cfgp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    data = Path(out) / "data"
    n = None
    try:
        n = len(json.loads((data / "proposals.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    checked = None
    try:
        checked = json.loads((data / "progress.json").read_text(encoding="utf-8")).get("checked")
    except (OSError, ValueError):
        pass
    return {"path": str(Path(out).resolve()), "created": cfg.get("created", ""), "product": (cfg.get("product") or {}).get("name", ""),
            "proposals": n, "has_scores": (data / "scores.json").is_file(), "has_page": (Path(out) / "deliverables" / "index.html").is_file(),
            "last_checked": checked, "inside_repo": bool((cfg.get("output") or {}).get("inside_repo")),
            "complete": bool(n) and (data / "scores.json").is_file()}


def find_strategies(repo):
    """Прошлые стратегии: <repo>/strategy/*/, любые <repo>/**/build/run-config.json до глубины 3, <repo>/../<имя>-strategy/*/ и
    PS_STRATEGY_DIR (папка стратегии или папка с ними). Самая свежая полная — recommended."""
    repo = Path(repo).resolve()
    roots, seen, found = [], set(), []
    roots.append(repo / "strategy")
    roots.append(repo.parent / ("%s-strategy" % repo.name))
    env = os.environ.get("PS_STRATEGY_DIR")
    if env:
        roots.append(Path(env).expanduser())
    cands = []
    for r in roots:
        if r.is_dir():
            cands += [r] + [d for d in sorted(r.iterdir()) if d.is_dir()]
    for base, dirs, _files in os.walk(repo):
        depth = len(Path(base).relative_to(repo).parts)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")] if depth < 4 else []
        if (Path(base) / "build" / "run-config.json").is_file():
            cands.append(Path(base))
    for c in cands:
        key = str(c.resolve())
        if key in seen:
            continue
        seen.add(key)
        info = _strategy_info(c)
        if info:
            found.append(info)
    found.sort(key=lambda x: (x["complete"], x["created"], x["path"]), reverse=True)
    for i, f in enumerate(found):
        f["recommended"] = i == 0 and f["complete"]
    return found


def mode_cards(found, repo):
    """Карточки AskUserQuestion: режим (если прошлые стратегии есть) и, если их несколько, какую контролировать."""
    if not found:
        return []
    top = found[0]
    label = "%s · %s · %s предложений" % (top["created"] or "без даты", top["product"] or "продукт", top["proposals"] if top["proposals"] is not None else "?")
    cards = [{"header": "Режим", "question": "Найдена прошлая стратегия (%s). Что делаем?" % label, "multiSelect": False, "options": [
        {"label": "Отследить выполнение (Recommended)", "description": "Сверить план с кодом, коммитами, issues и PR репозитория; статусы на таймлайне; корректировки"},
        {"label": "Отследить и пересмотреть", "description": "То же и обновить текст стратегии: сделанное отметить, зависимости и приоритеты пересчитать"},
        {"label": "Новая стратегия", "description": "Прошлая остаётся как есть; новый прогон с опросом"}]}]
    if len(found) > 1:
        opts = [{"label": ("%s · %s%s" % (f["created"] or "без даты", f["product"] or "продукт", " (Recommended)" if f["recommended"] else ""))[:60],
                 "description": "%s предложений%s%s; %s" % (f["proposals"] if f["proposals"] is not None else "?", ", оценки есть" if f["has_scores"] else "",
                                                          ", проверялась %s" % f["last_checked"] if f["last_checked"] else "", f["path"])}
                for f in found[:4]]
        cards.append({"header": "Стратегия", "question": "Какую стратегию использовать для контроля выполнения?", "multiSelect": False, "options": opts})
    return cards


def cmd_track(repo, baseline, mode, sets):
    found = find_strategies(repo)
    pick = None
    if baseline:
        info = _strategy_info(baseline)
        if not info:
            sys.exit("track: в %s нет build/run-config.json — это не папка стратегии" % baseline)
        pick = info
    else:
        pick = next((f for f in found if f.get("recommended")), found[0] if found else None)
    if not pick:
        sys.exit("track: прошлых стратегий не найдено (strategy/*/, ../<repo>-strategy/*/, PS_STRATEGY_DIR). Нужна новая: intake.py questions")
    if not pick["complete"]:
        print("Предупреждение: в стратегии нет data/proposals.json или scores.json — сверка будет неполной", file=sys.stderr)
    cfgp = Path(pick["path"]) / "build" / "run-config.json"
    cfg = json.loads(cfgp.read_text(encoding="utf-8"))
    cfg["tracking"] = {**(cfg.get("tracking") or {}), "mode": mode, "baseline": pick["path"], "last_checked": (cfg.get("tracking") or {}).get("last_checked")}
    cfg["tracking"]["repo"] = str(Path(repo).resolve())
    for s_ in sets or []:
        k, _, v = s_.partition("=")
        set_path(cfg, k.strip(), parse_value(v))
    cfgp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return pick, cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("questions")
    q.add_argument("--round", type=int)
    o = sub.add_parser("open")
    o.add_argument("--json", action="store_true")
    for name in ("apply", "defaults"):
        p = sub.add_parser(name)
        p.add_argument("--repo", default=".")
        p.add_argument("--set", action="append", default=[])
        p.add_argument("--out-dir")
        if name == "apply":
            p.add_argument("--answers")
            p.add_argument("--from-askuser", help="ответ AskUserQuestion (JSON-строка, @файл или - для stdin)")
            p.add_argument("--open")
    d = sub.add_parser("detect")
    d.add_argument("--repo", default=".")
    d.add_argument("--json", action="store_true")
    tr = sub.add_parser("track")
    tr.add_argument("--repo", default=".")
    tr.add_argument("--baseline")
    tr.add_argument("--mode", choices=["track", "update"], default="track")
    tr.add_argument("--set", action="append", default=[])
    t = sub.add_parser("from-text")
    t.add_argument("text")
    s = sub.add_parser("show")
    s.add_argument("config")
    a = ap.parse_args(argv)

    if a.cmd == "questions":
        print(json.dumps(questions_json(a.round), ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "open" and a.json:
        print(json.dumps(open_cards_json(), ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "open":
        print("Несколько открытых вопросов (ответьте на любые, остальное — «пропустить»):")
        for i, (_k, text) in enumerate(OPEN_QUESTIONS, 1):
            print("%d. %s" % (i, text))
        return 0
    if a.cmd == "detect":
        top, _ = git_info(a.repo)
        found = find_strategies(top)
        cards = mode_cards(found, top)
        if a.json:
            print(json.dumps({"repo": str(top), "found": found, "auto": next((f for f in found if f.get("recommended")), None), "cards": cards},
                             ensure_ascii=False, indent=2))
        elif not found:
            print("Прошлых стратегий не найдено — режим «Новая стратегия» (intake.py questions).")
        else:
            print("Найдено стратегий: %d" % len(found))
            for f in found:
                print("  %s %s · %s · %s предложений%s · %s" % ("★" if f["recommended"] else " ", f["created"] or "без даты", f["product"] or "продукт",
                                                              f["proposals"] if f["proposals"] is not None else "?", ", проверялась " + f["last_checked"] if f["last_checked"] else "", f["path"]))
        return 0
    if a.cmd == "track":
        top, _ = git_info(a.repo)
        pick, cfg = cmd_track(top, a.baseline, a.mode, a.set)
        print("Режим: %s; стратегия: %s (%s, %s предложений)" % ("отследить и пересмотреть" if a.mode == "update" else "отследить выполнение", pick["path"], pick["created"], pick["proposals"]))
        print("OUT=%s" % pick["path"])
        print("Дальше: strategy_track.py check %s --repo %s" % (pick["path"], top))
        return 0
    if a.cmd == "from-text":
        print(json.dumps(from_text(a.text), ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "show":
        print(show(json.loads(Path(a.config).read_text(encoding="utf-8"))))
        return 0
    cfg = base_config(a.repo, a.out_dir)
    notes = []
    if a.cmd == "apply":
        if not a.answers and not a.from_askuser:
            ap.error("apply: нужен --answers или --from-askuser")
        if a.answers:
            notes += apply_answers(cfg, json.loads(Path(a.answers).read_text(encoding="utf-8")))
        if a.from_askuser:
            raw = a.from_askuser
            raw = sys.stdin.read() if raw == "-" else Path(raw[1:]).read_text(encoding="utf-8") if raw.startswith("@") else raw
            notes += apply_from_askuser(cfg, json.loads(raw))
        if a.open:
            apply_open(cfg, json.loads(Path(a.open).read_text(encoding="utf-8")))
    else:
        cfg["autopilot"] = True
        cfg["assumptions"].append("Автопилот: параметры по умолчанию, опрос пропущен")
    _apply_sets(cfg, a.set)
    cfg = finalize(cfg)
    path = write_config(cfg)
    print(show(cfg))
    for n in notes:
        print("Заметка: " + n)
    print("\nrun-config: %s" % path)
    print("OUT=%s" % cfg["output"]["dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
