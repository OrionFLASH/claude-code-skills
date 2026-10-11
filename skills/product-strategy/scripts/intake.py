#!/usr/bin/env python3
"""Опрос владельца перед стратегией → build/run-config.json (references/intake.md, references/data-contract.md).

  intake.py questions [--round N] [--json]            вопросы раунда N в формате AskUserQuestion (JSON всегда; --json принимается
                                                      для единообразия); раунд 0 «Заказчик и продукт» (роль, чей продукт и где
                                                      код, ёмкость в днях, раскрытие автоматизации) задаётся ПЕРВЫМ; без
                                                      --round — раунды 0–6
  intake.py open [--json]                             открытые вопросы: карточки AskUserQuestion (--json) или текстом
  intake.py apply --repo . (--answers answers.json | --from-askuser '<json>') [--open open.json] [--set key=value …]
                  [--out-dir DIR] [--json] [--lenient]
                                                      ответы → run-config.json; печатает путь <OUT> и сводку.
                                                      --from-askuser принимает ответ AskUserQuestion как есть (ключи — текст
                                                      вопроса или header; значение — label, список label или свой текст), в том
                                                      числе и для открытых вопросов: отдельный open.json не нужен. Обёртка
                                                      {"answers": {...}} (как отдаёт AskUserQuestion) разворачивается сама;
                                                      неизвестный ключ — ошибка (код 2) со списком допустимых заголовков
                                                      (--lenient — только предупреждение). --json — сводка, заметки и список
                                                      follow_up (уточняющие вопросы: задать ДО «Начинаю?») одним JSON
  intake.py update <OUT|run-config.json> [--set k=v …] [--from-askuser '<json>'] [--json]
                                                      ответы на уточняющие вопросы (follow_up) → тот же run-config; закрытые
                                                      вопросы убираются из списка, сводка печатается заново
  intake.py disclosure-check <OUT>                    при disclosure=none|summary — нет ли в deliverables/ упоминаний автоматизации
                                                      (Claude, субагент, LLM, число токенов …); код 1 и адреса строк, если есть
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

Режим «Идея → концепция продукта» (references/concept-mode.md; run-config → mode: "concept"):
  intake.py concept-setup [--json]                    карточка настройки: число вопросов (15/25/40/своё ≥ 15), глубина,
                                                      форматы, папка результата (спрашивается каждый раз)
  intake.py concept-questions --count N [--batch 4] [--json]
                                                      первые N вопросов банка (40 вопросов, 9 тем) по приоритету пачками
                                                      по ≤ 4 для AskUserQuestion; N < 15 — ошибка; покрытие тем в начале
  intake.py concept-apply --repo <cwd> --idea "<идея>" --from-askuser '<JSON|@файл|->' [--out-dir D] [--set k=v]
                          [--request "<запрос>"] [--count N]
                                                      ответы карточек (ключ — header, текст вопроса или id c01…c40) →
                                                      <OUT>/build/run-config.json с mode: concept и блоком idea; OUT=…
  intake.py concept-defaults --idea "<идея>" [--repo <cwd>] [--out-dir D] [--set k=v]
                                                      автопилот: 15 вопросов отвечены значениями по умолчанию (допущения)

answers.json — {"<header вопроса>": "<label выбранного варианта>" | ["label", …] | "свой текст"} (как вернул
AskUserQuestion; «Other» — свой текст). --set — точечные пути: strategy.proposals_min=150, scope.competitors=false.

Режим «внешний продукт» (references/external-product.md): product.mode = repo | external | auto (карточка «Чей продукт»).
external — кода продукта в папке нет: scope.repo_analysis=false (repo_scan/repo_facts пропускаются, render_brief сам
перечисляет repo-scan/repo-facts в {MISSING_INPUTS}), источники фазы 1 — сайт, карточки магазинов (store_stats.py),
APK (app_scan.py), трекер → sources.external. auto — определить по папке (нет кода/есть только APK → external).
Только стандартная библиотека.
"""
import argparse
import difflib
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
            ("Три варианта (Recommended)", "Нулевой; малый — до 50 тыс. ₽ / $500 в месяц; средний — до 300 тыс. ₽ / $3000 в месяц. "
             "Свои суммы — в «Other»", {"strategy.budget.variants": ["zero", "small", "medium"]}),
            ("Нулевой", "Только своими силами, без затрат", {"strategy.budget.variants": ["zero"]}),
            ("Малый", "До 50 тыс. ₽ / $500 в месяц: инструменты, немного продвижения (своя сумма — в «Other»)",
             {"strategy.budget.variants": ["small"]}),
            ("Средний", "До 300 тыс. ₽ / $3000 в месяц: платные каналы, подрядчики (своя сумма — в «Other»)",
             {"strategy.budget.variants": ["medium"]}),
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
            ("ВНУТРИ репозитория: strategy/ (Recommended)", "<repo>/strategy/<дата>/ в отдельной ветке docs/strategy-<дата>; файлы попадают в git вместе с проектом", {"output.inside_repo": True}),
            ("ВНЕ репозитория (рядом)", "../<repo>-strategy/<дата>/ — в git репозитория не попадёт; перенести внутрь позже: init_run.py --relocate", {"output.inside_repo": False}),
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
    ("Передача в разработку", [
        ("Задачи", "Сформировать MD-файл с эпиками и задачами для Claude Code (по результатам стратегии: ссылки на макеты, спеки, эксперименты)?", False, [
            ("Да, состав выберу в конце (Recommended)", "В конце прогона покажу разделы стратегии с числом задач, вы отметите, что включить в файл",
             {"handoff.enabled": True, "handoff.ask_at_end": True, "handoff.scope": ["all"]}),
            ("Да, всё без вопросов", "Все разделы стратегии попадают в файл сразу", {"handoff.enabled": True, "handoff.ask_at_end": False, "handoff.scope": ["all"]}),
            ("Только интерфейс и дизайн", "Эпик доработки интерфейса: макеты, референсы, язык дизайна и связанные предложения",
             {"handoff.enabled": True, "handoff.ask_at_end": False, "handoff.scope": ["ui"]}),
            ("Нет", "Файл задач не нужен", {"handoff.enabled": False, "handoff.ask_at_end": False}),
        ]),
        ("Детальность", "Насколько подробно описывать задачи в файле?", False, [
            ("Суть, шаги и ссылки (Recommended)", "У каждой задачи: суть, чек-лист шагов, KPI, ссылки на спеки и макеты", {"handoff.detail": "brief"}),
            ("Только ссылки на материалы", "Короткие строки: P-id, название, приоритет и где лежат описание, спека, макет", {"handoff.detail": "links"}),
            ("Полные описания", "+ критерии приёмки, риски, дешёвый тест, доказательства — Claude Code почти не придётся читать другие файлы", {"handoff.detail": "full"}),
        ]),
        ("Срок задач", "Какие задачи по срокам включать в файл?", False, [
            ("Сейчас и следом (Recommended)", "Горизонты now и next (до ~12 месяцев)", {"handoff.horizon": "next"}),
            ("Только ближайшие", "Горизонт now (0–3 месяца)", {"handoff.horizon": "now"}),
            ("Все, включая многолетние", "Также later и vision", {"handoff.horizon": "all"}),
        ]),
    ]),
]

# Раунд 0 — задаётся ПЕРВЫМ (intake.py questions --round 0): от роли заказчика и того, есть ли код продукта, зависят
# формулировки, «вопросы владельцу», доступные источники фазы 1 и этика публикаций (references/external-product.md).
CONTEXT_ROUND = ("Заказчик и продукт", [
    ("Роль", "Кто вы относительно продукта?", False, [
        ("Владелец или команда (Recommended)", "Продукт ваш: «вопросы владельцу» — вам, доступ к консолям и аналитике есть",
         {"project.requester_role": "owner"}),
        ("Сторонний аналитик", "Аналитик, подрядчик или QA: продукт чужой, консолей нет, вопросы — владельцу через вас",
         {"project.requester_role": "analyst"}),
        ("Партнёр", "Партнёр или интегратор: интерес — совместный рост, данные владельца частично", {"project.requester_role": "partner"}),
        ("Инвестор", "Оценка перспектив: акцент на рынок, риски и экономику", {"project.requester_role": "investor"}),
    ]),
    ("Чей продукт", "Где код продукта, по которому готовим стратегию?", False, [
        ("Определи по папке (Recommended)", "Есть код продукта в текущей папке — анализ репозитория; нет кода (только APK, "
         "материалы QA) — режим «внешний продукт»", {"product.mode": "auto"}),
        ("Код в этой папке", "Текущий репозиторий — код продукта: repo_scan, repo_facts, Issues", {"product.mode": "repo"}),
        ("Кода нет, продукт внешний", "Чужой или закрытый продукт: вместо кода — сайт, магазины, APK, трекер", {"product.mode": "external"}),
    ]),
    ("Ёмкость", "Сколько человеко-дней в месяц команда тратит на развитие продукта?", False, [
        ("Определи по команде (Recommended)", "Один человек — 12 дней, команда — 15 дней на человека; запишу в допущения",
         {"project.capacity_days_month": "auto"}),
        ("До 5 дней", "Урывками: план будет очень узким", {"project.capacity_days_month": 4}),
        ("5–15 дней", "Регулярно, но не полный рабочий месяц", {"project.capacity_days_month": 10}),
        ("Полный месяц на человека", "≈ 20 дней на каждого в команде", {"project.capacity_days_month": "full"}),
    ]),
    ("Раскрытие", "Можно ли в отчёте и на странице упоминать, что стратегию готовил ИИ-ассистент?", False, [
        ("Да, полностью (Recommended)", "Раздел «Инструменты и токены» в отчёте: модели, агенты, токены", {"disclosure": "full"}),
        ("Кратко, без деталей", "Одна строка «подготовлено с помощью ИИ-инструментов», без моделей и токенов", {"disclosure": "summary"}),
        ("Нет, без упоминаний", "Публичные тексты без упоминаний автоматизации; служебный отчёт об инструментах — в build/",
         {"disclosure": "none"}),
    ]),
])
ALL_ROUNDS = [CONTEXT_ROUND] + ROUNDS

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
        "product": {"name": top.name, "url": "", "local_run": "auto", "run_command": "", "type": "auto", "known_facts": "",
                    "mode": "repo"},
        "strategy": {"kind": "growth", "goal": "рост и развитие продукта: аудитория, активация, удержание, монетизация",
                     "depth": "standard", "proposals_min": 100, "horizon_months": 12, "vision_years": 3, "markets": ["auto"],
                     "budget": {"variants": ["zero", "small", "medium"], "note": "", "small": None, "medium": None, "period": "month"},
                     "paid_tier": "auto", "constraints": "", "categories_na": [], "profile": "auto"},
        "project": {"goal": "auto", "repo_visibility": "unknown", "publish_code": "undecided", "currency": "auto", "price_hint": None,
                    "traffic_hint": None, "team_size": None, "requester_role": "owner", "product_owner": "",
                    "capacity_days_month": "auto"},
        "scope": {"repo_analysis": True, "app_run": True, "competitors": True, "competitors_min": 10, "communities": True,
                  "keywords": True, "events": True, "legal": True, "issues": bool(remote), "design_mockups": True, "mockups_min": 12,
                  "design_refs": True, "unit_economics": True, "experiments": 8, "specs_top": 10, "kanban_cards": 40},
        "sources": {"repo": True, "issues": bool(remote), "web_search": True, "web_search_budget_per_hour": 100,
                    "analytics_exports": [], "owner_docs": [], "competitor_list": [], "other": "", "stores": [],
                    "internal_authors": [],
                    "external": {"site": "", "stores": [], "apk": [], "tracker": "", "other_urls": []}},
        "formats": {"html": True, "xlsx": True, "pptx": True, "pdf": True, "md": True},
        "tools": {"typesafe": "auto", "browser": "auto", "subagents": True, "max_parallel_agents": 5, "install": "local-auto", "node_dir": None},
        "handoff": {"enabled": True, "ask_at_end": True, "scope": ["all"], "detail": "brief", "horizon": "next"},
        "phases": {"gap_audit": True},
        "output": {"dir": "", "inside_repo": True, "git_branch": "docs/strategy-%s" % today},
        "language": "ru", "disclosure": "full", "autopilot": False, "assumptions": [], "follow_up": [],
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


URL_RE = re.compile(r"https?://[^\s,;«»<>\"']+", re.I)
# домены и параметры → язык рынка (сигналы для _detect_markets)
TLD_LANG = {"ru": "ru", "рф": "ru", "su": "ru", "by": "ru", "kz": "ru", "uz": "ru", "kg": "ru", "ua": "uk", "de": "de", "fr": "fr",
            "es": "es", "it": "it", "br": "pt", "pt": "pt", "jp": "ja", "cn": "zh", "tr": "tr", "pl": "pl"}
STORE_LANG = {"rustore": "ru", "huawei": None, "gplay": None, "appstore": None}


def _store_parse(url):
    """URL карточки магазина → (store, id, lang|None) или None (store_stats.parse_store_url; без него — разбор здесь)."""
    try:
        import store_stats                                   # noqa: WPS433 — тот же каталог scripts/
        return store_stats.parse_store_url(url)
    except Exception:                                        # noqa: BLE001 — модуль недоступен: простой разбор
        low = url.lower()
        m = re.search(r"rustore\.ru/(?:catalog/)?app/([\w.]+)", low)
        if m:
            return ("rustore", m.group(1), "ru")
        m = re.search(r"play\.google\.com/store/apps/details\?(?:.*&)?id=([\w.]+)", low)
        if m:
            return ("gplay", m.group(1), None)
        m = re.search(r"apps\.apple\.com/(?:([a-z]{2})/)?app/(?:[^/]+/)?id(\d+)", low)
        if m:
            return ("appstore", m.group(2), None)
        return None


def _url_lang(url):
    """Язык по адресу: домен верхнего уровня, сегмент /ru/, параметры hl=, gl=, lang=. → код языка или None."""
    low = url.lower()
    m = re.search(r"[?&](?:hl|lang|locale)=([a-z]{2})", low)
    if m:
        return m.group(1)
    m = re.search(r"apps\.apple\.com/([a-z]{2})/", low)
    if m:
        return TLD_LANG.get(m.group(1), "en" if m.group(1) in ("us", "gb", "au", "ca") else None)
    m = re.match(r"https?://([^/:?#]+)", low)
    host = m.group(1) if m else ""
    if "rustore.ru" in host:
        return "ru"
    tld = host.rsplit(".", 1)[-1] if "." in host else ""
    if tld.startswith("xn--p1ai"):
        return "ru"
    if tld in TLD_LANG and not host.endswith(("google.com", "apple.com")):
        return TLD_LANG[tld]
    m = re.search(r"https?://[^/]+/(ru|en|de|fr|es|pt|ja|zh|uk|kk)(?:[/?#-]|$)", low)
    return m.group(1) if m else None


def _external_urls(cfg):
    """Все известные адреса продукта: product.url (может содержать несколько ссылок) и sources.external/stores."""
    ext = (cfg.get("sources") or {}).get("external") or {}
    urls = URL_RE.findall(str((cfg.get("product") or {}).get("url") or ""))
    urls += [ext.get("site")] if ext.get("site") else []
    urls += [s.get("url") for s in (ext.get("stores") or []) + ((cfg.get("sources") or {}).get("stores") or []) if isinstance(s, dict) and s.get("url")]
    out = []
    for u in urls:
        if u and u not in out:
            out.append(u.rstrip(".)"))
    return out


def split_product_urls(cfg):
    """product.url с несколькими ссылками → сайт (product.url), карточки магазинов (sources.stores и sources.external.stores),
    прочие ссылки (sources.external.other_urls). Команда локального запуска (не URL) не трогается."""
    pr, src = cfg["product"], cfg["sources"]
    ext = src.setdefault("external", {"site": "", "stores": [], "apk": [], "tracker": "", "other_urls": []})
    raw = str(pr.get("url") or "")
    urls = URL_RE.findall(raw)
    if not urls:
        return
    site, others = None, []
    stores = src.setdefault("stores", [])
    for u in urls:
        u = u.rstrip(".)")
        hit = _store_parse(u)
        if hit:
            if not any(s.get("url") == u for s in stores):
                stores.append({"store": hit[0], "id": hit[1], "url": u})
        elif site is None:
            site = u
        elif u not in others:
            others.append(u)
    ext["stores"] = [dict(s) for s in stores]
    ext["other_urls"] = sorted(set((ext.get("other_urls") or []) + others))
    if site:
        ext["site"] = site
    rest = URL_RE.sub("", raw).strip(" ,;")
    pr["url"] = site or ""
    if rest and not pr.get("run_command") and not site:
        pr["run_command"] = rest


def _detect_markets(repo, cfg=None):
    """Рынки по сигналам. → (список языков, причина, конфликт|None).
    Сигналы: адрес продукта (домен, /ru/, hl=), карточки магазинов (RuStore → ru, hl=/gl=, apps.apple.com/<страна>/),
    кириллица в названии продукта, README и локали в коде (README и локали — только если код продукта в этой папке)."""
    cfg = cfg or {}
    external = ((cfg.get("product") or {}).get("mode") == "external")
    ext_langs, ext_why = [], []
    for u in _external_urls(cfg):
        lang = _url_lang(u)
        if lang and lang not in ext_langs:
            ext_langs.append(lang)
            ext_why.append("%s → %s" % (re.sub(r"^https?://", "", u)[:40], lang))
    name = str((cfg.get("product") or {}).get("name") or "")
    if re.search(r"[А-Яа-яЁё]", name) and "ru" not in ext_langs:
        ext_langs.append("ru")
        ext_why.append("кириллица в названии «%s»" % name[:30])
    repo_langs, why_repo = [], ""
    if not external:
        text = _read_readme(repo)
        cyr = len(re.findall(r"[А-Яа-яЁё]", text))
        lat = len(re.findall(r"[A-Za-z]", text))
        if cyr > max(40, lat * 0.2):
            repo_langs.append("ru")
        skip = {"node_modules", "venv", ".venv", "site-packages", "build", "dist", ".git"}
        for loc in ("locales", "i18n", "lang", "translations", "locale"):
            for d in Path(repo).rglob(loc):
                if d.is_dir() and not (skip & set(d.parts)):
                    for f in list(d.iterdir())[:40]:
                        m = re.match(r"^([a-z]{2})(?:[-_][A-Za-z]{2})?$", f.stem if f.is_file() else f.name)
                        if m and m.group(1) not in repo_langs:
                            repo_langs.append(m.group(1))
            if len(repo_langs) > 6:
                break
        why_repo = ("кириллица в README: %d знаков" % cyr) if cyr else ("README без кириллицы" if text else "README нет")
        readme_en_only = bool(text) and not repo_langs and lat > 60
    else:
        readme_en_only = False
    conflict = None
    if ext_langs and readme_en_only and "ru" in ext_langs:
        conflict = "README без кириллицы (рынок en), а %s" % "; ".join(ext_why)
    langs = []
    for x in ext_langs + repo_langs:
        if x not in langs:
            langs.append(x)
    if "en" not in langs:
        langs.append("en")
    parts = []
    if ext_why:
        parts.append("адрес/магазины/название: " + "; ".join(ext_why))
    if why_repo:
        parts.append(why_repo)
    if external and not ext_why:
        parts.append("внешний продукт: адреса и названия на кириллице нет, README папки не учитывается")
    return langs[:6], "; ".join(parts) or "сигналов нет", conflict


CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".kt", ".kts", ".java", ".swift", ".m", ".mm", ".go", ".rs", ".rb", ".php",
            ".cs", ".dart", ".vue", ".svelte", ".c", ".cc", ".cpp", ".h", ".scala", ".ex", ".exs", ".clj", ".lua", ".fs", ".elm"}
APP_MANIFESTS = {"package.json", "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "build.gradle", "build.gradle.kts",
                 "settings.gradle", "settings.gradle.kts", "pom.xml", "Cargo.toml", "go.mod", "Gemfile", "composer.json", "pubspec.yaml",
                 "Package.swift", "AndroidManifest.xml", "Podfile", "mix.exs", "deno.json"}
NON_PRODUCT_DIRS = {"test", "tests", "e2e", "qa", "docs", "doc", "strategy", "scripts", "tools", "examples", "fixtures", "reports",
                    "screenshots", "apk", "builds"}


def scan_folder(repo, max_entries=6000):
    """Есть ли в папке код продукта и бинарные сборки. → {code_files, product_code_files, manifests, apk, aab, ipa}."""
    root = Path(repo)
    res = {"code_files": 0, "product_code_files": 0, "manifests": [], "apk": [], "aab": [], "ipa": []}
    if not root.is_dir():
        return res
    seen = 0
    for base, dirs, files in os.walk(root):
        rel = Path(base).relative_to(root).parts
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")] if len(rel) < 5 else []
        in_non_product = any(p.lower() in NON_PRODUCT_DIRS for p in rel)
        for f in files:
            seen += 1
            if seen > max_entries:
                return res
            p = Path(base) / f
            suf = p.suffix.lower()
            if suf in (".apk", ".aab", ".ipa"):
                res[suf[1:]].append(str(p.relative_to(root)))
            elif suf in CODE_EXT:
                res["code_files"] += 1
                if not in_non_product:
                    res["product_code_files"] += 1
            if f in APP_MANIFESTS and not in_non_product:
                res["manifests"].append(str(p.relative_to(root)))
    return res


def detect_product_mode(repo):
    """repo | external по содержимому папки. → (режим, причина)."""
    s = scan_folder(repo)
    builds = s["apk"] + s["aab"] + s["ipa"]
    if builds and s["product_code_files"] < 20 and not any(m.endswith(("AndroidManifest.xml", "build.gradle", "build.gradle.kts",
                                                                        "pubspec.yaml", "Podfile", "Package.swift")) for m in s["manifests"]):
        return "external", "в папке сборки (%s) без исходников приложения (файлов кода вне тестов/скриптов: %d)" % (
            ", ".join(builds[:3]), s["product_code_files"])
    if s["product_code_files"] >= 5 or (s["manifests"] and s["product_code_files"] >= 1):
        return "repo", "код продукта: %d файлов, манифесты: %s" % (s["product_code_files"], ", ".join(s["manifests"][:3]) or "нет")
    return "external", "кода продукта нет (файлов кода вне тестов/скриптов: %d, манифестов: %d)" % (
        s["product_code_files"], len(s["manifests"]))


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


def _follow(cfg, path, header, question, kind="text", options=None, why=""):
    """Уточняющий вопрос: задать владельцу ДО «Начинаю?» (ответ — intake.py update <OUT> --set path=… или --from-askuser)."""
    fu = cfg.setdefault("follow_up", [])
    if any(x.get("path") == path for x in fu) or path in (cfg.get("follow_up_done") or []):
        return
    item = {"path": path, "header": header, "question": question, "kind": kind}
    if options:
        item["card"] = {"header": header, "question": question, "multiSelect": False,
                        "options": [{"label": l, "description": d} for l, d, _ in options]}
        item["options"] = {l: v for l, _d, v in options}
    if why:
        item["why"] = why
    fu.append(item)


def apply_product_mode(cfg):
    """product.mode auto → repo|external; для external — источники фазы 1 вместо кода, scope.repo_analysis=false (repo_scan и
    repo_facts пропускаются; render_brief перечисляет их в {MISSING_INPUTS}). Идемпотентно (повтор в update)."""
    if cfg.get("mode") == "concept":
        return cfg
    pr, sc, src = cfg["product"], cfg["scope"], cfg["sources"]
    repo = cfg["repo"]["path"]
    mode = pr.get("mode") or "repo"
    if mode == "auto":
        mode, why = detect_product_mode(repo)
        pr["mode"] = mode
        cfg["assumptions"].append("Режим продукта определён по папке: %s (%s)" % (mode, why))
    elif mode == "repo" and "product.mode" not in (cfg.get("_explicit") or []) and not pr.get("mode_confirmed"):
        m2, why = detect_product_mode(repo)
        if m2 == "external" and scan_folder(repo)["apk"]:
            _follow(cfg, "product.mode", "Чей продукт", "В папке есть APK, но нет исходников приложения. Продукт внешний (кода нет)?",
                    "choice", [("Да, кода нет (Recommended)", "Режим «внешний продукт»: сайт, магазины, APK вместо кода", "external"),
                               ("Нет, код здесь", "Анализировать текущий репозиторий", "repo")], why)
    split_product_urls(cfg)
    if mode != "external":
        return cfg
    ext = src.setdefault("external", {"site": "", "stores": [], "apk": [], "tracker": "", "other_urls": []})
    sc["repo_analysis"] = False
    src["repo"] = False
    cfg["repo"]["analyze"] = False
    if pr.get("local_run") in (None, "", "auto"):
        pr["local_run"] = "none"
    folder = scan_folder(repo)
    ext["apk"] = sorted(set((ext.get("apk") or []) + folder["apk"] + folder["aab"]))
    if pr.get("name") == cfg["repo"].get("name") and "product.name" not in (cfg.get("_explicit") or []):
        pr["name"] = ""                                       # имя рабочей папки — не название чужого продукта
        _follow(cfg, "product.name", "Продукт", FOLLOW_UP_TEXT["product.name"], why="режим external: имя папки — не название продукта")
    if cfg["repo"].get("remote") and sc.get("issues"):
        ext["tracker"] = ext.get("tracker") or "github:%s" % cfg["repo"]["remote"]
    has_site = bool(ext.get("site") or URL_RE.search(str(pr.get("url") or "")))
    if not has_site and "scope.app_run" not in (cfg.get("_explicit") or []):
        sc["app_run"] = False                                 # сайта нет — браузерного аудита тоже
    if not (ext.get("site") or ext.get("stores") or ext.get("apk")):
        _follow(cfg, "product.url", "Адрес", "Продукт внешний, кода нет. Дайте адрес сайта и/или ссылки на карточки в магазинах "
                "(RuStore, Google Play, App Store) одной строкой через пробел — это источники фазы 1.", why="режим external без источников")
    if ext.get("tracker"):
        _follow(cfg, "sources.internal_authors", "Авторы",
                "Трекер %s — чей он? Перечислите логины внутренних авторов (заказчик, тестировщики) через запятую: их обращения "
                "не считаются спросом пользователей (или «нет»)." % ext["tracker"], why="в режиме external трекер часто принадлежит QA")
    return cfg


BUDGET_DEFAULT = {"RUB": (50000, 300000), "USD": (500, 3000), "EUR": (500, 3000)}  # малый / средний в месяц


def parse_money(text):
    """«до 30 тыс. ₽», «$300», «1,5 млн руб» → (сумма, валюта|None) или (None, None)."""
    low = str(text or "").lower().replace(" ", " ")
    m = re.search(r"(\d[\d\s]*(?:[.,]\d+)?)\s*(тыс\.?|т\.?\s?р\.?|k\b|к\b|млн|mln|m\b)?", low)
    if not m:
        return None, None
    num = float(re.sub(r"\s", "", m.group(1)).replace(",", "."))
    mult = m.group(2) or ""
    if mult.startswith(("тыс", "т", "k", "к")):
        num *= 1000
    elif mult.startswith(("млн", "mln", "m")):
        num *= 1_000_000
    cur = "RUB" if re.search(r"₽|руб|\bр\b|rub", low) else "USD" if re.search(r"\$|usd|долл", low) else "EUR" if re.search(r"€|eur|евро", low) else None
    return int(num) if num == int(num) else num, cur


def resolve_budget(cfg):
    """Суммы малого и среднего бюджета в валюте проекта (strategy.budget.small/medium, в месяц); по умолчанию — из карточки."""
    if cfg.get("mode") == "concept":
        return
    b = cfg["strategy"].setdefault("budget", {"variants": ["zero"], "note": ""})
    cur = cfg["project"].get("currency") or "USD"
    lo, hi = BUDGET_DEFAULT.get(cur, BUDGET_DEFAULT["USD"])
    b.setdefault("period", "month")
    filled = []
    for k, v in (("small", lo), ("medium", hi)):
        if k in (b.get("variants") or []) and (b.get(k) in (None, "", "auto") or (k in (b.get("defaulted") or []) and b.get("currency") != cur)):
            b[k] = v
            b["defaulted"] = sorted(set((b.get("defaulted") or []) + [k]))
            filled.append("%s ≤ %s %s/мес" % ("малый" if k == "small" else "средний", "{:,}".format(v).replace(",", " "), cur))
    if filled:
        cfg["assumptions"].append("Бюджет по умолчанию: %s — уточните, если иначе (--set strategy.budget.small=…)" % ", ".join(filled))
    b["currency"] = cur


def resolve_capacity(cfg):
    """project.capacity_days_month: auto → 12 дней (один человек) или 15 × команда; full → 20 × команда (человеко-дни в месяц)."""
    prj = cfg["project"]
    team = prj.get("team_size") or 1
    v = prj.get("capacity_days_month")
    if v in (None, "", "auto"):
        prj["capacity_days_month"] = 12 if team == 1 else 15 * team
        cfg["assumptions"].append("Ёмкость: %d человеко-дней в месяц на развитие (по команде %s; уточните, если иначе)" % (
            prj["capacity_days_month"], team))
    elif v == "full":
        prj["capacity_days_month"] = 20 * team
    elif isinstance(v, str):
        m = re.search(r"\d+", v)
        prj["capacity_days_month"] = int(m.group(0)) if m else 12


def resolve_auto(cfg):
    """Значения auto → конкретные (product.mode, markets, product.type, project.currency, strategy.profile); решения — в assumptions."""
    repo = cfg["repo"]["path"]
    apply_product_mode(cfg)
    s, pr, prj = cfg["strategy"], cfg["product"], cfg["project"]
    external = pr.get("mode") == "external"
    if s["markets"] in (["auto"], [], "auto"):
        langs, why, conflict = _detect_markets(repo, cfg)
        s["markets"] = langs
        cfg["assumptions"].append("Рынки определены по %s: %s (%s)" % ("адресам и названию" if external else "репозиторию и адресам",
                                                                       ", ".join(langs), why))
        if conflict:
            _follow(cfg, "strategy.markets", "Рынки", "Сигналы рынка противоречат: %s. На какие рынки ориентируемся?" % conflict, "choice",
                    [("Только RU (Recommended)", "Россия и СНГ: язык, валюта RUB, площадки RU", ["ru"]),
                     ("RU + EN", "Русскоязычный и англоязычный рынки", ["ru", "en"]),
                     ("Только EN", "Англоязычный рынок, валюта USD", ["en"])], conflict)
    if pr["type"] == "auto":
        ext = (cfg["sources"].get("external") or {})
        if external or cfg["sources"].get("stores"):
            if ext.get("stores") or ext.get("apk") or cfg["sources"].get("stores"):
                t, why = "mobile", "карточки магазинов или APK"
            elif external:
                t, why = "other", "внешний продукт: только сайт, тип не ясен"
                _follow(cfg, "product.type", "Тип", "Какой это продукт: веб-сервис (saas), контент-сайт (content), бот (bot), "
                        "мобильное приложение (mobile) или другое?", why="режим external без магазинов и APK")
            else:
                t, why = _detect_type(repo)
        else:
            t, why = _detect_type(repo)
        pr["type"] = t
        cfg["assumptions"].append("Тип продукта определён %s: %s (%s)" % ("по источникам" if external else "по репозиторию", t, why))
    if prj["currency"] == "auto":
        prj["currency"] = "RUB" if s["markets"] and s["markets"][0] == "ru" else "USD"
        prj["currency_source"] = "auto"
        cfg["assumptions"].append("Валюта определена по первому рынку: %s" % prj["currency"])
    if prj["team_size"] is None:
        prj["team_size"] = 1
        cfg["assumptions"].append("Команда: 1 человек (по умолчанию; уточните, если иначе)")
    if s["profile"] == "auto":
        zero = s["budget"]["variants"] == ["zero"]
        solo = prj["team_size"] == 1 and (zero or prj["goal"] in ("personal", "oss"))
        s["profile"] = "zero-budget-solo" if solo else "standard"
        cfg["assumptions"].append("Профиль стратегии: %s" % s["profile"])
    if cfg.get("mode") != "concept":
        resolve_budget(cfg)
        resolve_capacity(cfg)
        role = prj.get("requester_role") or "owner"
        if role != "owner" and not prj.get("product_owner"):
            _follow(cfg, "project.product_owner", "Владелец", "Кто владелец продукта (компания или человек)? Нужен для «вопросов "
                    "владельцу», доступа к данным и этики публикаций.", why="заказчик — не владелец (роль %s)" % role)
        elif role == "owner" and not prj.get("product_owner"):
            prj["product_owner"] = "заказчик (владелец продукта)"
    return cfg


# Прогноз размера прогона перед «Начинаю?» (оценка, ±50 %). Основа — два прогона глубины deep (2026-10): 27 агентов,
# ≈ 6,3 млн токенов, ≈ 6 ч и ≈ 50 агентов, ≈ 11 млн токенов, ≈ 4–5 ч (параллельно до 5); остальные глубины — экстраполяция.
FORECAST = {   # глубина → ((агенты), (млн токенов субагентов), (часы по часам))
    "quick": ((8, 15), (1.5, 3.0), (1.0, 2.0)),
    "standard": ((18, 32), (3.5, 7.0), (2.5, 4.0)),
    "deep": ((27, 50), (6.0, 11.0), (4.0, 6.0)),
    "exhaustive": ((45, 75), (10.0, 18.0), (6.0, 10.0)),
}
PARALLEL_HOURS = {5: 1.0, 4: 1.1, 3: 1.3, 2: 1.7, 1: 2.5}
FORECAST_BASIS = ("оценка по двум прогонам глубины deep (2026-10: 27 агентов / 6,3 млн токенов / ≈ 6 ч и ≈ 50 агентов / ≈ 11 млн / "
                  "4–5 ч, параллельно до 5); другие глубины — экстраполяция [допущение]")


def forecast(cfg):
    """Агенты, токены субагентов, часы по часам — диапазоны с поправкой на выключенные направления, число предложений и
    параллельность. → dict (пишется в run-config forecast; сверяется с фактом в разделе 11 отчёта)."""
    s, sc, t = cfg["strategy"], cfg["scope"], cfg["tools"]
    depth = s.get("depth") if s.get("depth") in FORECAST else "standard"
    (a0, a1), (t0, t1), (h0, h1) = FORECAST[depth]
    k = 1.0 - 0.04 * sum(1 for x in ("competitors", "communities", "keywords", "events", "legal") if sc.get(x) is False)
    k -= 0.15 if sc.get("design_mockups") is False else 0
    k -= 0.05 if sc.get("design_refs") is False else 0
    base = DEPTH[depth]["proposals_min"]
    k *= max(0.5, (float(s.get("proposals_min") or base) / base)) ** 0.5
    hk = k
    par = int(t.get("max_parallel_agents") or 5)
    if t.get("subagents") is False:
        agents, hk = (0, 0), k * 2.6
    else:
        agents = (max(1, int(round(a0 * k))), max(1, int(round(a1 * k))))
        hk = k * PARALLEL_HOURS.get(min(5, max(1, par)), 1.0)
    r1 = lambda x: round(x, 1)                                  # noqa: E731
    return {"label": "оценка", "depth": depth, "agents": list(agents), "tokens_m": [r1(t0 * k), r1(t1 * k)],
            "hours": [r1(h0 * hk), r1(h1 * hk)], "parallel": 1 if t.get("subagents") is False else par, "basis": FORECAST_BASIS}


def finalize(cfg):
    """Глубина → объёмы (если пользователь не задал их явно), папка результата, мультивыбор → флаги, auto → решения."""
    resolve_auto(cfg)
    table = CONCEPT_DEPTH if cfg.get("mode") == "concept" else DEPTH
    depth = table.get(cfg["strategy"]["depth"], table["standard"])
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
    if cfg.get("mode") != "concept":
        cfg["forecast"] = forecast(cfg)
    return cfg


def questions_json(round_no=None, context=False):
    """Раунды AskUserQuestion. round_no=0 — раунд «Заказчик и продукт» (задаётся первым); context=True — раунды 0–6;
    по умолчанию — раунды 1–6 (как до 1.4)."""
    out = []
    numbered = ([(0, CONTEXT_ROUND)] if (context or round_no == 0) else []) + list(enumerate(ROUNDS, 1))
    for i, (title, qs) in numbered:
        if round_no is not None and i != round_no:
            continue
        out.append({"round": i, "title": title, "questions": [
            {"header": h, "question": q, "multiSelect": multi, "options": [{"label": l, "description": d} for l, d, _ in opts]}
            for h, q, multi, opts in qs]})
    return out


LEGACY_LABELS = {  # старые подписи карточек (до 1.2.1) → новые; ответы прежних сессий принимаются
    "В репозитории strategy/ (Recommended)": "ВНУТРИ репозитория: strategy/ (Recommended)",
    "Рядом с репозиторием": "ВНЕ репозитория (рядом)",
}


def _folder_alias(label):
    """Свободная формулировка ответа «Папка» → True (внутри) / False (вне) / None (не понял)."""
    low = str(label).lower()
    if re.search(r"\b(вне|рядом|outside|снаружи)\b", low):
        return False
    if re.search(r"\b(внутри|inside)\b|в\s+репозитори|в\s+папке\s+репозитори|strategy/", low):
        return True
    return None


def _find_option(header, label):
    label = LEGACY_LABELS.get(str(label).strip(), label)
    for _, qs in ALL_ROUNDS:
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


def _role_custom(cfg, text, explicit):
    low = text.lower()
    role = "analyst" if re.search(r"аналит|подряд|qa|тестир|агентств|консульт|analyst|contractor", low) else \
        "partner" if re.search(r"партн|интегр|partner", low) else "investor" if re.search(r"инвест|investor|фонд", low) else \
        "owner" if re.search(r"владел|мой продукт|наш продукт|owner|основат|founder|cto|ceo", low) else "other"
    set_path(cfg, "project.requester_role", role)
    set_path(cfg, "project.requester_note", text.strip())
    explicit.append("project.requester_role")


def _mode_custom(cfg, text, explicit):
    low = text.lower()
    if re.search(r"чуж|внеш|нет кода|без кода|кода нет|закрыт|только apk|external", low):
        mode = "external"
    elif re.search(r"здесь|в этой папке|этот репозитор|текущ|repo", low):
        mode = "repo"
    else:
        mode = "auto"
    set_path(cfg, "product.mode", mode)
    m = re.search(r"(?:продукт|владелец|принадлежит|компани[ия])\s*[:—-]?\s*(.+)$", text.strip(), re.I)
    if m and mode == "external" and len(m.group(1)) <= 80 and not re.search(r"кода|код\b", m.group(1), re.I):
        set_path(cfg, "project.product_owner", m.group(1).strip(" .«»\""))
    explicit.append("product.mode")


def _capacity_custom(cfg, text, explicit):
    m = re.search(r"\d+(?:[.,]\d+)?", text)
    if m:
        v = float(m.group(0).replace(",", "."))
        if re.search(r"час|hour", text.lower()) and not re.search(r"д(ен|н)", text.lower()):
            v = v / 8.0 * (4.3 if re.search(r"недел|week", text.lower()) else 1)   # часы (в неделю) → дни в месяц
        set_path(cfg, "project.capacity_days_month", max(1, int(round(v))))
        explicit.append("project.capacity_days_month")
    else:
        cfg["assumptions"].append("Ёмкость: свой ответ «%s» без числа — по команде" % text)


def _disclosure_custom(cfg, text, explicit):
    low = text.lower()
    val = "none" if re.search(r"\bнет\b|без упомин|не упомин|нельзя|запрещ|\bnone\b|\bno\b", low) else \
        "summary" if re.search(r"кратк|одн\w+ строк|summary|без детал", low) else "full"
    set_path(cfg, "disclosure", val)
    set_path(cfg, "disclosure_note", text.strip())
    explicit.append("disclosure")


def _budget_custom(cfg, text, explicit):
    """Свой ответ «Бюджет» с суммой → strategy.budget.small (или medium, если сказано «средний»); валюта — в заметку."""
    amount, cur = parse_money(text)
    if amount is None:
        return
    key = "medium" if re.search(r"средн|medium", text.lower()) else "small"
    b = cfg["strategy"]["budget"]
    b[key] = amount
    if cur:
        b["amount_currency"] = cur
    if key not in (b.get("variants") or []):
        b["variants"] = sorted(set((b.get("variants") or []) + [key]), key=["zero", "small", "medium"].index)
    explicit.append("strategy.budget." + key)


CONTEXT_CUSTOM = {"Роль": _role_custom, "Чей продукт": _mode_custom, "Ёмкость": _capacity_custom, "Раскрытие": _disclosure_custom}


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
            elif header == "Папка" and _folder_alias(lab) is not None:
                set_path(cfg, "output.inside_repo", _folder_alias(lab))
                explicit.append("output.inside_repo")
            elif header in CONTEXT_CUSTOM:
                CONTEXT_CUSTOM[header](cfg, str(lab), explicit)
            elif header in CUSTOM_PATH:
                path = CUSTOM_PATH[header]
                node = cfg
                for part in path.split(".")[:-1]:
                    node = node[part]
                prev = node.get(path.split(".")[-1]) or ""
                set_path(cfg, path, (prev + "; " if prev and header != "Стратегия" else "") + str(lab))
                if header == "Бюджет":
                    _budget_custom(cfg, str(lab), explicit)
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


FOLLOW_UP_TEXT = {   # «Уточню сам» / «Есть, напишу» без текста → готовый текстовый вопрос (задать до «Начинаю?»)
    "product.name": "Как называется продукт и что он делает — одной фразой?",
    "product.url": "Какой публичный адрес продукта (сайт, карточки в магазинах) или команда локального запуска? Несколько ссылок — через пробел.",
    "product.known_facts": "Какие цифры известны: аудитория, трафик, конверсии, доход, цены (любые, с периодом)?",
    "sources.competitor_list": "Какие конкуренты и образцы вы знаете? Названия или ссылки через запятую.",
    "strategy.constraints": "Какие ограничения и что вне задачи: сроки, юрисдикции, запретные каналы?",
    "sources.owner_docs": "Пути к документам, выгрузкам аналитики или исследованиям — через запятую?",
    "author": "Кого указать автором: ФИО и ник, например «Иванов Иван (ivanov)»?",
}


class AnswerError(ValueError):
    """Ответ AskUserQuestion не разобран: неизвестные ключи или значения не того вида."""


def unwrap_answers(answers):
    """Обёртки ответа AskUserQuestion → плоский {вопрос|header: значение}: {"answers": {...}} (с questions/annotations рядом
    или без), список [{"question"|"header": …, "answer"|"answers"|"selected": …}]. Плоский словарь возвращается как есть."""
    if isinstance(answers, dict) and isinstance(answers.get("answers"), (dict, list)) and \
            set(answers) <= {"answers", "questions", "annotations", "metadata", "result"}:
        answers = answers["answers"]
    if isinstance(answers, list):
        flat = {}
        for it in answers:
            if not isinstance(it, dict):
                raise AnswerError("элемент списка ответов — не объект: %r" % (it,))
            k = it.get("header") or it.get("question")
            v = next((it[x] for x in ("answer", "answers", "selected", "value") if x in it), None)
            if not k:
                raise AnswerError("в элементе списка нет question/header: %r" % (it,))
            flat[k] = v
        answers = flat
    if answers is None:
        return {}
    if not isinstance(answers, dict):
        raise AnswerError("ответ должен быть объектом {вопрос: ответ}, получено: %s" % type(answers).__name__)
    return answers


def known_keys():
    """Все допустимые ключи ответа: header и текст вопроса раундов 0–6 и открытых карточек. → (множество, список header)."""
    keys, headers = set(), []
    for _t, qs in ALL_ROUNDS:
        for h, q, _m, _o in qs:
            keys.update((h, q))
            headers.append(h)
    for _p, h, q, _o in OPEN_CARDS:
        keys.update((h, q))
        headers.append(h)
    return keys, headers


def validate_answers(answers):
    """Неизвестные ключи и значения-объекты. → список ошибок (пустой — всё в порядке)."""
    keys, headers = known_keys()
    errs = []
    for k, v in answers.items():
        if k not in keys:
            close = difflib.get_close_matches(str(k), sorted(keys), n=2, cutoff=0.6)
            errs.append("неизвестный ключ «%s»%s" % (k, " — может быть: %s" % " / ".join("«%s»" % c for c in close) if close else ""))
        if isinstance(v, dict) or (isinstance(v, list) and any(isinstance(x, (dict, list)) for x in v)):
            errs.append("ключ «%s»: значение — label, список label или свой текст, а не объект" % k)
    if errs:
        errs.append("допустимые заголовки (header): %s; ключом может быть и полный текст вопроса" % ", ".join(headers))
    return errs


def apply_from_askuser(cfg, answers, strict=True):
    """Ответ AskUserQuestion как есть: ключи — текст вопроса или header, значения — label, список label или свой текст.
    Обёртка {"answers": {...}} разворачивается. Вопросы раундов (0–6) и открытые карточки (OPEN_CARDS) различаются
    автоматически. Неизвестный ключ: strict — AnswerError, иначе заметка (в assumptions сырые словари не попадают).
    «Уточню сам» без текста → cfg["follow_up"] (готовый вопрос). Возвращает заметки."""
    answers = unwrap_answers(answers)
    errs = validate_answers(answers)
    notes = []
    if errs and strict:
        raise AnswerError("; ".join(errs))
    by_q, by_h = {}, {}
    for _t, qs in ALL_ROUNDS:
        for h, q, _m, _o in qs:
            by_q[q], by_h[h] = h, h
    open_by = {}
    for path, h, q, opts in OPEN_CARDS:
        open_by[q] = open_by[h] = (path, h, opts)
    keys, _hs = known_keys()
    rounds = {}
    for k, v in answers.items():
        if k not in keys:
            notes.append("пропущен неизвестный ключ «%s» (--lenient)" % k)
            continue
        if isinstance(v, dict):
            notes.append("ключ «%s»: значение-объект пропущено" % k)
            continue
        if k in open_by:
            path, h, opts = open_by[k]
            val = v[0] if isinstance(v, list) and v else v
            hit = next((o for o in opts if o[0] == val or o[0].replace(" (Recommended)", "") == str(val).replace(" (Recommended)", "")), None)
            if hit is not None:
                kind = hit[2]
                if kind is None:
                    continue
                if kind == "__text__":
                    notes.append("%s: выбран «%s», но текста нет — уточнить у владельца (вопрос в follow_up)" % (path, hit[0]))
                    _follow(cfg, path, h, FOLLOW_UP_TEXT.get(path, "Уточните: %s" % h), why="выбран «%s» без текста" % hit[0])
                    continue
                if kind == "__owner_doc__":
                    notes.append("%s: нужен путь к файлу выгрузки — уточнить (вопрос в follow_up)" % path)
                    _follow(cfg, "sources.owner_docs", h, "Путь к файлу выгрузки (Search Console, аналитика, платежи)?",
                            why="выбрано «Есть выгрузка» без пути")
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
        elif key in ("sources.competitor_list", "sources.owner_docs", "sources.internal_authors"):
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
    (r"\b(?:вне|рядом\s+с|outside)\s+(?:текущего\s+|the\s+)?(?:репозитори\w*|repo\w*)", "output.inside_repo", lambda m: False),
    (r"(?:\bвнутри\s+(?:текущего\s+)?репозитори\w*|\bв\s+(?:папк\w+\s+)?(?:текущ\w+\s+)?репозитори\w*|\binside\s+(?:the\s+)?repo\w*)", "output.inside_repo", lambda m: True),
]


# режим «Идея → концепция»: метка в начале запроса (идея — текст после неё) или фраза по смыслу
CONCEPT_MARK_RE = re.compile(r"^\s*(?:!concept\b|concept\s*:|!идея\b|идея\s*:)\s*[:—-]?\s*", re.I | re.U)
CONCEPT_PHRASE_RE = re.compile(r"(?:иде[яюие]\s+(?:нового\s+)?продукт|концепци\w*\s+(?:нового\s+)?продукт|product\s+concept|product\s+idea)", re.I | re.U)


def from_text(text):
    found = {}
    for rx, path, fn in FROM_TEXT:
        m = re.search(rx, text or "", re.I | re.U)
        if m and path not in found:
            found[path] = fn(m)
    m = CONCEPT_MARK_RE.match(text or "")
    if m:
        found["mode"] = "concept"
        rest = (text or "")[m.end():].strip()
        if rest:
            found["idea.pitch"] = rest
    elif CONCEPT_PHRASE_RE.search(text or ""):
        found["mode"] = "concept"
        found["mode_confirm"] = True          # подхвачено по смыслу — сначала спросить, запускать ли режим
    return found


def check_folder_request(cfg, request):
    """Сверка слов запроса («в репозитории» / «вне репозитория») с выбранной папкой. Возвращает заметки."""
    asked = from_text(request).get("output.inside_repo")
    if asked is None:
        return []
    chosen = cfg["output"]["inside_repo"]
    explicit = "output.inside_repo" in (cfg.get("_explicit") or [])
    if not explicit:                       # карточку не задавали или не ответили — слова запроса главнее значения по умолчанию
        cfg["output"]["inside_repo"] = asked
        return ["Папка взята из запроса: %s репозитория" % ("внутри" if asked else "вне")]
    if asked != chosen:
        cfg["output"]["folder_conflict"] = True
        return ["ВНИМАНИЕ: в запросе сказано «%s репозитория», а в карточке выбрано «%s». Переспросить одной строкой и при необходимости повторить apply с --set output.inside_repo=%s" % (
            "внутри" if asked else "вне", "внутри" if chosen else "вне", "true" if asked else "false")]
    return []


def show(cfg):
    if cfg.get("mode") == "concept":
        return show_concept(cfg)
    s, sc, f = cfg["strategy"], cfg["scope"], cfg["formats"]
    lines = [
        ("Продукт: %s (репозиторий %s%s)" % (cfg["product"]["name"], cfg["repo"]["path"], ", " + cfg["repo"]["remote"] if cfg["repo"]["remote"] else ""))
        if cfg["product"].get("mode") != "external" else
        "Продукт: %s (внешний; рабочая папка %s — не код продукта)" % (cfg["product"]["name"] or "название уточнить", cfg["repo"]["path"]),
        "Стратегия: %s, глубина %s, предложений ≥ %d, горизонт %d мес + видение %d г." % (s["kind"], s["depth"], s["proposals_min"], s["horizon_months"], s["vision_years"]),
        "Анализ: репозиторий %s, запуск приложения %s, Issues %s" % (_yn(sc["repo_analysis"]), _yn(sc["app_run"]), _yn(sc["issues"])),
        "Исследования: конкуренты %s (≥%d), сообщества %s, спрос %s, события %s, право %s" % (
            _yn(sc["competitors"]), sc["competitors_min"], _yn(sc["communities"]), _yn(sc["keywords"]), _yn(sc["events"]), _yn(sc["legal"])),
        "Дизайн: макеты %s (≥%d), референсы %s; экономика %s; эксперименты %d; спеки топ-%d; Kanban %d карточек" % (
            _yn(sc["design_mockups"]), sc["mockups_min"], _yn(sc["design_refs"]), _yn(sc["unit_economics"]), sc["experiments"], sc["specs_top"], sc["kanban_cards"]),
        "Рынки: %s; бюджет: %s; платный уровень: %s" % (", ".join(s["markets"]), _budget_text(cfg), s["paid_tier"]),
        _formats_line(f),
        "Инструменты: TypeSafe %s, субагенты %s (до %d), установка %s" % (
            cfg["tools"]["typesafe"], _yn(cfg["tools"]["subagents"]), cfg["tools"]["max_parallel_agents"], cfg["tools"].get("install", "local-auto")),
        "Проект: цель %s, репозиторий %s, команда %s, ёмкость %s чел.-дн./мес, валюта %s, профиль %s" % (
            cfg["project"]["goal"], cfg["project"]["repo_visibility"], cfg["project"]["team_size"],
            cfg["project"].get("capacity_days_month") or "—", cfg["project"]["currency"], s["profile"]),
        _requester_line(cfg),
        _disclosure_line(cfg),
        _handoff_line(cfg),
        ("Папка: %s — ВНУТРИ репозитория (ветка %s)" % (cfg["output"]["dir"], cfg["output"]["git_branch"])) if cfg["output"]["inside_repo"]
        else ("Папка: %s — ВНЕ РЕПОЗИТОРИЯ: в git проекта не попадёт. Нужна внутри репозитория — повторить apply с --set output.inside_repo=true "
              "или позже init_run.py <OUT> --relocate <repo>/strategy/<дата> --repo <repo> --inside-repo" % cfg["output"]["dir"]),
    ]
    if (cfg["product"].get("mode") == "external"):
        lines.insert(1, _external_line(cfg))
    if cfg["author"].get("copyright"):
        lines.append("Авторство: %s" % cfg["author"]["copyright"])
    lines += _warnings(cfg)
    if cfg.get("forecast"):
        lines.append(_forecast_line(cfg["forecast"]))
    if cfg["assumptions"]:
        lines.append("Допущения: " + "; ".join(cfg["assumptions"]))
    fu = cfg.get("follow_up") or []
    if fu:
        lines.append("Уточнить ДО «Начинаю?» (%d): %s" % (len(fu), " | ".join("[%s] %s" % (x.get("header"), x.get("question")) for x in fu)))
    return "\n".join(lines)


FORMAT_NAMES = {"html": "веб-страница", "xlsx": "XLSX", "pptx": "PPTX", "pdf": "PDF"}
ROLE_NAMES = {"owner": "владелец или команда продукта", "analyst": "сторонний аналитик / подрядчик", "partner": "партнёр",
              "investor": "инвестор", "other": "другое"}
DISCLOSURE_NAMES = {"full": "полностью (раздел «Инструменты и токены» в отчёте)",
                    "summary": "кратко: одна строка без моделей и токенов",
                    "none": "без упоминаний автоматизации в публичных текстах; отчёт об инструментах — в build/"}


def _formats_line(f):
    on = [k for k in ("html", "xlsx", "pptx", "pdf") if f.get(k)]
    line = "Форматы: %s" % ", ".join(k for k, v in f.items() if v)
    if len(on) == 1:
        other = [FORMAT_NAMES[k] for k in ("html", "xlsx", "pptx", "pdf") if k not in on]
        line += " — получится только %s, верно? (%s собираться не будут; добавить — --set formats.<xlsx|pptx|pdf>=true)" % (
            FORMAT_NAMES[on[0]], ", ".join(other))
    elif not on:
        line += " — ВНИМАНИЕ: ни одного формата результата, кроме Markdown; верно?"
    return line


def _budget_text(cfg):
    b = cfg["strategy"].get("budget") or {}
    cur = b.get("amount_currency") or b.get("currency") or cfg["project"].get("currency") or ""
    out = []
    for v in b.get("variants") or []:
        amt = b.get(v) if v in ("small", "medium") else None
        out.append("%s (≤ %s %s/мес)" % (v, "{:,}".format(amt).replace(",", " ") if isinstance(amt, (int, float)) else amt, cur) if amt else v)
    return ", ".join(out) + ("; заметка: %s" % b["note"] if b.get("note") else "")


def _requester_line(cfg):
    prj, pr = cfg["project"], cfg["product"]
    role = prj.get("requester_role") or "owner"
    return "Заказчик: %s; владелец продукта: %s; режим продукта: %s" % (
        ROLE_NAMES.get(role, role) + (" (%s)" % prj["requester_note"] if prj.get("requester_note") else ""),
        prj.get("product_owner") or "не указан — уточнить", {"repo": "код в репозитории", "external": "внешний, без кода",
                                                             "auto": "определить по папке"}.get(pr.get("mode") or "repo", pr.get("mode")))


def _disclosure_line(cfg):
    d = cfg.get("disclosure") or "full"
    return "Публичные тексты: disclosure=%s — %s" % (d, DISCLOSURE_NAMES.get(d, d))


def _external_line(cfg):
    ext = (cfg.get("sources") or {}).get("external") or {}
    stores = ", ".join("%s:%s" % (x.get("store"), x.get("id")) for x in ext.get("stores") or []) or "нет"
    return ("Внешний продукт (кода нет): repo_scan/repo_facts пропускаются (scope.repo_analysis=false); фаза 1 — сайт %s, магазины %s "
            "(store_stats.py), APK %s (app_scan.py), трекер %s" % (ext.get("site") or "нет", stores, ", ".join(ext.get("apk") or []) or "нет",
                                                               ext.get("tracker") or "нет"))


def _warnings(cfg):
    sc = cfg["scope"]
    out = []
    off = [n for k, n in (("keywords", "поисковые запросы"), ("events", "календарь событий")) if sc.get(k) is False]
    if off:
        charts = [c for k, c in (("keywords", "keywords-volume, keywords-clusters"), ("events", "events-calendar")) if sc.get(k) is False]
        out.append("Внимание: выключено «%s» — графики %s и раздел «Спрос» будут пустыми или короткими. Для стратегии с SEO и "
                   "контентом включите хотя бы запросы: --set scope.keywords=true" % (", ".join(off), ", ".join(charts)))
    if cfg["product"].get("mode") == "external" and sc.get("issues"):
        out.append("Внимание: внешний продукт и анализ Issues — проверьте, что трекер отражает пользователей, а не QA заказчика "
                   "(sources.internal_authors)")
    return out


def _forecast_line(fc):
    a = fc.get("agents") or [0, 0]
    return "Прогноз (оценка ±50 %%): агентов ≈ %s, токенов субагентов ≈ %s–%s млн, ≈ %s–%s ч по часам (параллельно до %s); основа — %s" % (
        "%d–%d" % tuple(a) if a[1] else "0 (одна сессия)", *[str(x).replace(".", ",") for x in fc["tokens_m"] + fc["hours"]],
        fc.get("parallel"), fc.get("basis", ""))


HANDOFF_HEADERS = {"Задачи", "Детальность", "Срок задач"}


def _handoff_line(cfg):
    h = cfg.get("handoff") or {}
    if not h.get("enabled"):
        return "Файл задач для Claude Code: нет"
    sc = h.get("scope") or ["all"]
    return "Файл задач для Claude Code: да (состав: %s; детальность: %s; горизонт: %s)" % (
        "выберете в конце" if h.get("ask_at_end") else ("все разделы" if "all" in sc else ", ".join(sc)),
        {"links": "ссылки", "brief": "суть и шаги", "full": "полные описания"}.get(h.get("detail"), h.get("detail")),
        {"now": "ближайшие", "next": "сейчас и следом", "all": "все"}.get(h.get("horizon"), h.get("horizon")))


def _yn(v):
    return "да" if v else "нет"


def write_config(cfg):
    out = Path(cfg["output"]["dir"])
    (out / "build").mkdir(parents=True, exist_ok=True)
    p = out / "build" / "run-config.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


DISCLOSURE_TERMS = [   # (регэксп, уровень): model — запрещено при summary и none; auto — только при none
    (r"\bClaude\b", "model"), (r"\bAnthropic\b", "model"), (r"\b(?:Opus|Sonnet|Haiku|Fable)\b", "model"), (r"\bGPT-?\d", "model"),
    (r"\d[\d\s.,]*\s*(?:млн|тыс\.?|k|K|M)?\s*токен\w*", "model"), (r"инструменты и токены", "model"),
    (r"суб-?агент\w*", "auto"), (r"\bsub-?agents?\b", "auto"), (r"\bLLM\b", "auto"), (r"нейросет\w*", "auto"),
    (r"ИИ-ассистент\w*", "auto"), (r"\bAI[- ]assistant", "auto"), (r"языков\w+ модел\w*", "auto"), (r"\bTypeSafe\b|\bJev\b", "auto"),
    (r"(?:сгенерирован|подготовлен|написан)\w*\s+(?:с помощью\s+)?(?:ИИ|AI|нейросет)", "auto"),
]
DISCLOSURE_SKIP_CTX = re.compile(r"дизайн|design|css|цвет|colou?r|шрифт|font|--c-", re.I)


def disclosure_check(out):
    """Упоминания автоматизации в deliverables/ при disclosure=none|summary. → (уровень, список находок)."""
    out = Path(out)
    cfg = {}
    try:
        cfg = json.loads((out / "build" / "run-config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    level = cfg.get("disclosure") or "full"
    if level == "full":
        return level, []
    rx = [(re.compile(r, re.I if not r.startswith("\\b(?:Opus") else 0), lv) for r, lv in DISCLOSURE_TERMS if level == "none" or lv == "model"]
    found = []
    for f in sorted((out / "deliverables").rglob("*")):
        if not f.is_file() or f.suffix.lower() not in (".md", ".html", ".htm", ".txt", ".csv", ".json", ".xml", ".svg") or f.stat().st_size > 30_000_000:
            continue
        if "node_modules" in f.parts:
            continue
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for r, _lv in rx:
                for m in r.finditer(line):
                    if "токен" in m.group(0).lower() and DISCLOSURE_SKIP_CTX.search(line[max(0, m.start() - 40):m.start()]):
                        continue
                    found.append({"file": str(f.relative_to(out)), "line": i, "term": m.group(0).strip(),
                                  "text": line[max(0, m.start() - 60):m.end() + 60].strip()})
    return level, found


def _set_followup_value(cfg, path, val):
    """Ответ на уточняющий вопрос → поле run-config (списки, автор, адреса, рынки — с разбором)."""
    if isinstance(val, list):
        val = ", ".join(str(x) for x in val)
    sval = str(val).strip()
    if path in ("author", "sources.competitor_list", "sources.owner_docs", "sources.internal_authors"):
        apply_open(cfg, {path: sval})
    elif path == "strategy.markets":
        set_path(cfg, path, [x.strip().lower() for x in re.split(r"[,;/ +]+", sval) if re.fullmatch(r"[a-zA-Z]{2}", x.strip())] or ["ru"])
    elif path == "product.mode":
        set_path(cfg, path, "external" if re.search(r"extern|внеш|кода нет|да", sval.lower()) else "repo")
        cfg["product"]["mode_confirmed"] = True
    else:
        set_path(cfg, path, parse_value(sval) if path.startswith(("project.capacity", "strategy.budget.")) else sval)


def refresh(cfg):
    """Пересчёт после update: режим продукта (external — источники фазы 1), адреса, тип по магазинам, бюджеты, ёмкость,
    владелец, прогноз. Повторный вызов безопасен."""
    apply_product_mode(cfg)
    pr, ext = cfg["product"], (cfg["sources"].get("external") or {})
    if pr.get("type") in ("other", "auto") and (ext.get("stores") or ext.get("apk") or cfg["sources"].get("stores")):
        pr["type"] = "mobile"
        cfg["assumptions"].append("Тип продукта уточнён по магазинам/APK: mobile")
        cfg["follow_up"] = [x for x in cfg.get("follow_up") or [] if x.get("path") != "product.type"]
    if cfg["project"].get("currency") == "auto" or cfg["project"].get("currency_source") == "auto":
        cur = "RUB" if (cfg["strategy"].get("markets") or ["en"])[0] == "ru" else "USD"
        if cur != cfg["project"].get("currency"):
            cfg["assumptions"].append("Валюта пересчитана по первому рынку: %s" % cur)
        cfg["project"]["currency"], cfg["project"]["currency_source"] = cur, "auto"
    resolve_budget(cfg)
    resolve_capacity(cfg)
    if cfg["project"].get("product_owner"):
        cfg["follow_up"] = [x for x in cfg.get("follow_up") or [] if x.get("path") != "project.product_owner"]
    if cfg.get("mode") != "concept":
        cfg["forecast"] = forecast(cfg)
    cfg.pop("_explicit", None)
    return cfg


def cmd_update(target, sets=None, from_askuser=None, strict=True):
    """intake.py update: ответы на follow_up (и любые --set) → тот же run-config. → (cfg, путь, заметки)."""
    p = Path(target)
    cfgp = p if p.suffix == ".json" else p / "build" / "run-config.json"
    cfg = json.loads(cfgp.read_text(encoding="utf-8"))
    cfg["_explicit"] = []
    fu = cfg.get("follow_up") or []
    resolved, notes, rest = set(), [], {}
    if from_askuser:
        ans = unwrap_answers(_read_answers_arg(from_askuser) if isinstance(from_askuser, str) else from_askuser)
        for k, v in ans.items():
            item = next((x for x in fu if k in (x.get("question"), x.get("header"), x.get("path"))), None)
            if not item:
                rest[k] = v
                continue
            val = v[0] if isinstance(v, list) and len(v) == 1 else v
            opts = item.get("options") or {}
            hit = next((ov for ol, ov in opts.items() if ol == val or ol.replace(" (Recommended)", "") == str(val).replace(" (Recommended)", "")), None)
            if hit is not None:
                set_path(cfg, item["path"], hit)
                if item["path"] == "product.mode":
                    cfg["product"]["mode_confirmed"] = True
            else:
                _set_followup_value(cfg, item["path"], val)
            resolved.add(item["path"])
        if rest:
            notes += apply_from_askuser(cfg, rest, strict=strict)
    for s_ in sets or []:
        k, _, v = s_.partition("=")
        k = k.strip()
        if any(x.get("path") == k for x in fu):
            _set_followup_value(cfg, k, v)
        else:
            _apply_sets(cfg, [s_])
        resolved.add(k)
    if "project.currency" in resolved:
        cfg["project"]["currency_source"] = "explicit"
    for bk in ("small", "medium"):
        if "strategy.budget." + bk in resolved:
            cfg["strategy"]["budget"]["defaulted"] = [x for x in cfg["strategy"]["budget"].get("defaulted") or [] if x != bk]
    cfg["follow_up"] = [x for x in fu if x.get("path") not in resolved]
    cfg["follow_up_done"] = sorted(set((cfg.get("follow_up_done") or []) + [x.get("path") for x in fu if x.get("path") in resolved]))
    refresh(cfg)
    cfgp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg, cfgp, notes


def _apply_sets(cfg, sets):
    for s in sets or []:
        k, _, v = s.partition("=")
        val = parse_value(v)
        if k.strip().startswith("tools.") and v.strip().lower() in ("off", "on", "auto"):
            val = v.strip().lower()                      # «off» для tools.* — строка режима, а не булево (иначе проверки mode == "off" его не видят)
        set_path(cfg, k.strip(), val)
        cfg.setdefault("_explicit", []).append(k.strip())


# ---------- режим «Идея → концепция продукта» (references/concept-mode.md) ----------
CONCEPT_MIN_QUESTIONS = 15
CONCEPT_DEFAULT_QUESTIONS = 25
CONCEPT_DEPTH = {  # глубина → объём в режиме идеи (≥ 60 предложений, 10+ аналогов, 8+ макетов, 8 экспериментов для стандарта)
    "quick": {"proposals_min": 50, "competitors_min": 8, "mockups_min": 6, "experiments": 5, "specs_top": 5, "kanban_cards": 20},
    "standard": {"proposals_min": 60, "competitors_min": 10, "mockups_min": 8, "experiments": 8, "specs_top": 8, "kanban_cards": 30},
    "deep": {"proposals_min": 80, "competitors_min": 15, "mockups_min": 12, "experiments": 10, "specs_top": 12, "kanban_cards": 40},
    "exhaustive": {"proposals_min": 100, "competitors_min": 20, "mockups_min": 15, "experiments": 12, "specs_top": 15, "kanban_cards": 60},
}
CONCEPT_THEMES = [  # (ключ, название) — порядок тем в опросе и в досье
    ("problem", "Проблема и боль"), ("audience", "Аудитория"), ("value", "Ценность и отличие"),
    ("product", "Продукт и объём MVP"), ("market", "Рынок, аналоги, вдохновение"), ("money", "Модель и деньги"),
    ("team", "Команда и ресурсы"), ("design", "Дизайн и бренд"), ("risks", "Риски, право, критерии успеха"),
]
CONCEPT_THEME_TITLE = dict(CONCEPT_THEMES)
# Банк вопросов об идее: (id, тема, приоритет, header ≤ 12, вопрос, мультивыбор, [(label, description, {путь: значение})]).
# Первый вариант — значение по умолчанию «(Recommended)»; «Other» (свой текст) добавляет AskUserQuestion.
# Приоритет: 1–9 — по одному вопросу каждой темы, 10–15 — вторые вопросы шести тем (в 15 есть все темы),
# 16–25 — до 2–3 вопросов на тему, 26–40 — остальное. Пути idea.facets.* — признаки идеи для досье и эвристик.
CONCEPT_BANK = [
    # 1. Проблема и боль
    ("c01", "problem", 1, "Боль", "Насколько острая проблема, которую решает идея?", False, [
        ("Заметная, но терпимая (Recommended)", "Раздражает регулярно, но люди обходятся; остроту проверю в исследовании", {"idea.facets.pain": "moderate"}),
        ("Острая, ищут решение", "Уже тратят деньги или часы на обходные пути", {"idea.facets.pain": "acute"}),
        ("Моя личная боль", "Проверено на себе, на других пока нет", {"idea.facets.pain": "personal"}),
        ("Скрытая, не осознают", "Сначала придётся объяснять, что проблема вообще есть", {"idea.facets.pain": "latent"})]),
    ("c02", "problem", 16, "Сейчас", "Как люди решают проблему сейчас?", False, [
        ("Вручную, подручными средствами (Recommended)", "Таблицы, заметки, чаты, звонки — неудобно, но бесплатно", {"idea.facets.current": "manual"}),
        ("Платят за другой сервис", "Есть платные решения, но они чем-то не устраивают", {"idea.facets.current": "paid_competitor"}),
        ("Бесплатными аналогами", "Есть бесплатные инструменты общего назначения", {"idea.facets.current": "free_tools"}),
        ("Никак не решают", "Мирятся с проблемой или не знают, что можно иначе", {"idea.facets.current": "nothing"})]),
    ("c03", "problem", 26, "Частота", "Как часто человек сталкивается с проблемой?", False, [
        ("Несколько раз в месяц (Recommended)", "Регулярно, но не каждый день", {"idea.facets.frequency": "monthly"}),
        ("Каждый день", "Повседневная задача — шанс на привычку", {"idea.facets.frequency": "daily"}),
        ("Редко, но дорого", "Раз в год или реже, зато ставка высокая (переезд, ремонт, свадьба)", {"idea.facets.frequency": "rare"})]),
    ("c04", "problem", 27, "Триггер", "Что заставляет начать искать решение?", False, [
        ("Потеря денег или времени (Recommended)", "Человек замечает, что теряет, и ищет способ перестать", {"idea.facets.trigger": "loss"}),
        ("Событие в жизни", "Переезд, ребёнок, новая работа, начало проекта", {"idea.facets.trigger": "life_event"}),
        ("Требование извне", "Закон, работодатель, клиент или платформа требуют", {"idea.facets.trigger": "external"}),
        ("Любопытство и мода", "Увидел у других, захотел попробовать", {"idea.facets.trigger": "curiosity"})]),
    ("c05", "problem", 28, "Цена боли", "Во что проблема обходится человеку?", False, [
        ("Пара часов в месяц (Recommended)", "Потеря времени и нервов, деньги не главное", {"idea.facets.cost_of_pain": "time"}),
        ("Заметные деньги", "Прямые траты или упущенный доход каждый месяц", {"idea.facets.cost_of_pain": "money"}),
        ("Риск крупной потери", "Штраф, здоровье, сорванная сделка, утрата данных", {"idea.facets.cost_of_pain": "big_risk"}),
        ("Только неудобство", "Неприятно, но без ощутимых потерь", {"idea.facets.cost_of_pain": "annoyance"})]),
    # 2. Аудитория
    ("c06", "audience", 2, "Аудитория", "Кто главный пользователь продукта?", False, [
        ("Частные лица (B2C) (Recommended)", "Люди решают личную задачу и сами выбирают продукт", {"idea.facets.segment": "b2c"}),
        ("Малый бизнес и фрилансеры", "Самозанятые, мастера, небольшие команды", {"idea.facets.segment": "smb"}),
        ("Компании и команды (B2B)", "Решение принимает компания, пользователей несколько", {"idea.facets.segment": "b2b"}),
        ("Разработчики", "Инструмент для программистов и технических специалистов", {"idea.facets.segment": "dev"})]),
    ("c07", "audience", 10, "Рынки", "На каких языках и рынках запускаемся?", False, [
        ("Русскоязычный рынок (Recommended)", "Россия и СНГ, интерфейс на русском, цены в рублях", {"strategy.markets": ["ru"]}),
        ("RU + EN", "Русский и английский с первого выпуска", {"strategy.markets": ["ru", "en"]}),
        ("Англоязычный, глобально", "Интерфейс на английском, цены в долларах", {"strategy.markets": ["en"]}),
        ("Глобально, много языков", "EN + крупные локали (es, pt, de, fr)", {"strategy.markets": ["en", "es", "pt", "de", "fr"]})]),
    ("c08", "audience", 20, "Сегмент", "Насколько узкий первый сегмент?", False, [
        ("Узкая ниша для старта (Recommended)", "Одна профессия, город или сообщество — проще найти первых 100", {"idea.facets.niche": "narrow"}),
        ("Широкая массовая аудитория", "Сразу для всех, кому знакома проблема", {"idea.facets.niche": "broad"}),
        ("Сообщество, где я свой", "Аудитория, в которой у меня есть репутация и связи", {"idea.facets.niche": "own_community"})]),
    ("c09", "audience", 29, "Где они", "Где первые пользователи проводят время онлайн? (можно несколько)", True, [
        ("Найти в исследовании (Recommended)", "Площадки и сообщества аудитории определю в фазе рынка", {"idea.facets.channels": ["research"]}),
        ("Мессенджеры и чаты", "Каналы и группы в мессенджерах", {"idea.facets.channels": ["messengers"]}),
        ("Профильные форумы", "Тематические форумы, Q&A-сайты, сообщества по интересам", {"idea.facets.channels": ["forums"]}),
        ("Соцсети и видео", "Короткие видео, блоги, соцсети", {"idea.facets.channels": ["social"]})]),
    ("c10", "audience", 30, "Доступ", "Есть ли у вас прямой доступ к аудитории?", False, [
        ("Нет, начинаю с нуля (Recommended)", "Первых пользователей придётся искать", {"idea.facets.access": "none"}),
        ("Есть знакомые из аудитории", "5–20 человек, с которыми можно провести интервью", {"idea.facets.access": "acquaintances"}),
        ("Своя аудитория", "Канал, блог, рассылка или сообщество, где меня читают", {"idea.facets.access": "own_audience"})]),
    # 3. Ценность и отличие
    ("c11", "value", 3, "Ценность", "Какую главную пользу получит пользователь?", False, [
        ("Экономит время (Recommended)", "Делает привычную задачу быстрее и проще", {"idea.facets.value": "time"}),
        ("Экономит или приносит деньги", "Прямая выгода, которую можно посчитать", {"idea.facets.value": "money"}),
        ("Снижает риск и тревогу", "Контроль, напоминания, уверенность, безопасность", {"idea.facets.value": "safety"}),
        ("Радость и общение", "Развлечение, самовыражение, люди рядом", {"idea.facets.value": "joy"})]),
    ("c12", "value", 11, "Отличие", "Чем идея отличается от того, что уже есть?", False, [
        ("Проще и быстрее (Recommended)", "То же самое, но без лишнего и за меньшее число шагов", {"idea.facets.differentiator": "simpler"}),
        ("Дешевле или бесплатно", "Доступная альтернатива дорогим решениям", {"idea.facets.differentiator": "cheaper"}),
        ("Новая возможность", "Делает то, чего аналоги не умеют", {"idea.facets.differentiator": "new_capability"}),
        ("Под узкую нишу", "Сделано под конкретную аудиторию и её словарь", {"idea.facets.differentiator": "niche_fit"})]),
    ("c13", "value", 21, "Ага-момент", "Когда пользователь впервые почувствует пользу?", False, [
        ("В первые 5 минут (Recommended)", "Результат сразу, без долгой настройки", {"idea.facets.time_to_value": "minutes"}),
        ("После первой недели", "Польза копится от регулярного использования", {"idea.facets.time_to_value": "week"}),
        ("Когда накопятся люди", "Нужны данные или другие участники (сетевой эффект)", {"idea.facets.time_to_value": "network"})]),
    ("c14", "value", 31, "Замена", "От чего пользователь откажется ради продукта?", False, [
        ("От таблиц и заметок (Recommended)", "Заменяет самодельные способы", {"idea.facets.replaces": "diy"}),
        ("От платного сервиса", "Переход от конкурента — нужен импорт и повод", {"idea.facets.replaces": "competitor"}),
        ("От посредника", "Агентство, специалист, перекупщик", {"idea.facets.replaces": "intermediary"}),
        ("Ни от чего, это новое", "Новая привычка — сложнее объяснить ценность", {"idea.facets.replaces": "nothing"})]),
    ("c15", "value", 32, "Сеть", "Растёт ли ценность с числом пользователей?", False, [
        ("Полезен и одному (Recommended)", "Ценность есть с первого пользователя", {"idea.facets.network": "single"}),
        ("Нужны обе стороны", "Площадка или маркетплейс: продавцы и покупатели, авторы и читатели", {"idea.facets.network": "two_sided"}),
        ("Нужна группа", "Семья, команда, соседи — пользуются вместе", {"idea.facets.network": "group"})]),
    # 4. Продукт и объём MVP
    ("c16", "product", 4, "Форма", "В какой форме будет продукт?", False, [
        ("Веб-приложение (Recommended)", "Сайт-сервис в браузере, работает и на телефоне", {"product.type": "saas"}),
        ("Мобильное приложение", "iOS и/или Android, магазины приложений", {"product.type": "mobile"}),
        ("Бот в мессенджере", "Бот или мини-приложение в мессенджере", {"product.type": "bot"}),
        ("Расширение или десктоп", "Расширение браузера или программа для компьютера", {"product.type": "desktop"})]),
    ("c17", "product", 12, "MVP", "Каким должен быть первый выпуск (MVP)?", False, [
        ("Одна ключевая функция (Recommended)", "Самый узкий сценарий, который решает боль целиком", {"idea.facets.mvp": "single_feature"}),
        ("Лендинг и лист ожидания", "Проверка спроса до разработки", {"idea.facets.mvp": "landing"}),
        ("Ручной сервис за интерфейсом", "Снаружи продукт, внутри работаю руками (concierge)", {"idea.facets.mvp": "concierge"}),
        ("Полноценная первая версия", "Сразу несколько сценариев — дольше и рискованнее", {"idea.facets.mvp": "full"})]),
    ("c18", "product", 22, "Срок MVP", "Когда нужен первый выпуск?", False, [
        ("Через 1–2 месяца (Recommended)", "План на 6 месяцев + видение на 2 года", {"idea.facets.mvp_weeks": 6}),
        ("Через 2 недели", "Самый быстрый запуск, минимум функций", {"idea.facets.mvp_weeks": 2}),
        ("Через 3–6 месяцев", "План на 12 месяцев + видение на 2 года", {"idea.facets.mvp_weeks": 18, "strategy.horizon_months": 12})]),
    ("c19", "product", 33, "Устройства", "Какие устройства важнее для пользователя?", False, [
        ("Телефон в первую очередь (Recommended)", "Макеты — сначала мобильные экраны", {"idea.facets.device": "phone"}),
        ("Компьютер", "Работа за столом, большие экраны", {"idea.facets.device": "desktop"}),
        ("Оба одинаково", "Адаптивный интерфейс для обоих", {"idea.facets.device": "both"})]),
    ("c20", "product", 34, "Данные", "Что продукт будет хранить о пользователе?", False, [
        ("Минимум: почта и настройки (Recommended)", "Без чувствительных данных", {"idea.facets.data": "minimal"}),
        ("Личные данные и файлы", "Профили, фото, документы, переписка", {"idea.facets.data": "personal", "scope.legal": True}),
        ("Здоровье, деньги или дети", "Особые категории данных — право обязательно", {"idea.facets.data": "sensitive", "scope.legal": True})]),
    ("c21", "product", 35, "ИИ", "Нужен ли ИИ в продукте?", False, [
        ("Только если упростит (Recommended)", "ИИ как помощник там, где он убирает рутину", {"idea.facets.ai": "helper"}),
        ("ИИ — ядро продукта", "Без модели продукт не работает — расходы на запросы и риски качества", {"idea.facets.ai": "core"}),
        ("Без ИИ", "Классический продукт без моделей", {"idea.facets.ai": "none"})]),
    # 5. Рынок, аналоги, вдохновение
    ("c22", "market", 5, "Аналоги", "Знаете ли вы конкурентов или аналоги?", False, [
        ("Найди сам (Recommended)", "Прямые, косвенные, заменители и аналоги из соседних сфер — поиском", {"idea.facets.competitors_known": "search"}),
        ("Знаю несколько, впишу", "Названия или ссылки — в «Other»", {"idea.facets.competitors_known": "listed"}),
        ("Уверен, что аналогов нет", "Проверю: обычно они есть, хотя бы как заменители", {"idea.facets.competitors_known": "none_claimed"})]),
    ("c23", "market", 18, "Образцы", "Какие продукты вдохновляют (из любых сфер)?", False, [
        ("Подбери по идее (Recommended)", "Образцы механик и дизайна найду в исследовании", {"idea.facets.inspiration": "search"}),
        ("Есть образцы, впишу", "Названия или ссылки — в «Other»", {"idea.facets.inspiration": "listed"}),
        ("Не нужно", "Без раздела вдохновения", {"idea.facets.inspiration": "skip"})]),
    ("c24", "market", 24, "Рынок", "Каким вы видите рынок сейчас?", False, [
        ("Оценить в исследовании (Recommended)", "Размер и динамику оценю по открытым данным", {"idea.facets.market": "research"}),
        ("Растёт, приходят новые", "Спрос увеличивается, игроков становится больше", {"idea.facets.market": "growing"}),
        ("Зрелый, есть лидеры", "Устоявшиеся игроки, нужно отличие", {"idea.facets.market": "mature"}),
        ("Новый, рынка ещё нет", "Категорию придётся создавать", {"idea.facets.market": "new"})]),
    ("c25", "market", 36, "Тайминг", "Почему сейчас — подходящее время?", False, [
        ("Найти в исследовании (Recommended)", "Тренды и события проверю по источникам", {"idea.facets.why_now": "research"}),
        ("Новая технология", "Стало возможно или дёшево то, что раньше было недоступно", {"idea.facets.why_now": "technology"}),
        ("Изменились правила", "Закон, политика платформ или уход игроков с рынка", {"idea.facets.why_now": "regulation"}),
        ("Изменились привычки", "Люди стали делать это иначе", {"idea.facets.why_now": "habits"})]),
    # 6. Модель и деньги
    ("c26", "money", 6, "Модель", "Как продукт будет зарабатывать?", False, [
        ("Freemium + подписка (Recommended)", "Бесплатная основа, платные функции по подписке", {"strategy.paid_tier": "yes", "strategy.monetization": "freemium"}),
        ("Разовая покупка", "Платная версия или покупка внутри продукта", {"strategy.paid_tier": "yes", "strategy.monetization": "one_time"}),
        ("Комиссия со сделок", "Процент с транзакций между пользователями", {"strategy.paid_tier": "yes", "strategy.monetization": "commission"}),
        ("Бесплатно: донаты, гранты", "Без платного уровня; устойчивость — поддержка и гранты", {"strategy.paid_tier": "no", "strategy.monetization": "donations"})]),
    ("c27", "money", 17, "Цена", "Какую цену в месяц вы допускаете?", False, [
        ("Определи по аналогам (Recommended)", "Цену предложу по ценам аналогов", {"idea.facets.price_band": "auto"}),
        ("Низкая: до 300 ₽ / $5", "Массовый потребительский продукт", {"idea.facets.price_band": "low"}),
        ("Средняя: до 1500 ₽ / $20", "Профессиональный инструмент для частного лица", {"idea.facets.price_band": "mid"}),
        ("Высокая: B2B-цена", "Для компаний, от 5000 ₽ / $50 в месяц", {"idea.facets.price_band": "high"})]),
    ("c28", "money", 25, "Кто платит", "Кто платит за продукт?", False, [
        ("Сам пользователь (Recommended)", "Платит тот, кто пользуется", {"idea.facets.payer": "user"}),
        ("Компания пользователя", "Платит работодатель или клиент", {"idea.facets.payer": "company"}),
        ("Третья сторона", "Рекламодатель, партнёр, спонсор", {"idea.facets.payer": "third_party"}),
        ("Пока никто", "Деньги — после набора аудитории", {"idea.facets.payer": "nobody"})]),
    ("c29", "money", 37, "Доход", "Чего вы ждёте от продукта в деньгах за первый год?", False, [
        ("Окупить расходы (Recommended)", "Продукт должен хотя бы покрывать свои траты", {"idea.facets.revenue_goal": "break_even", "project.goal": "commercial"}),
        ("Подработка", "Дополнительный доход к основной работе", {"idea.facets.revenue_goal": "side_income", "project.goal": "commercial"}),
        ("Основной доход", "Цель — жить на доход от продукта", {"idea.facets.revenue_goal": "main_income", "project.goal": "commercial"}),
        ("Деньги не важны", "Делаю для себя и сообщества", {"idea.facets.revenue_goal": "none", "project.goal": "personal"})]),
    # 7. Команда и ресурсы
    ("c30", "team", 7, "Команда", "Кто будет делать продукт?", False, [
        ("Я один (Recommended)", "Ёмкость плана — часы одного человека", {"project.team_size": 1}),
        ("2–3 человека", "Небольшая команда единомышленников", {"project.team_size": 2}),
        ("Команда 4+", "Команда с ролями", {"project.team_size": 5}),
        ("Я и подрядчики", "Делаю сам, часть работы заказываю", {"project.team_size": 1, "idea.facets.contractors": True})]),
    ("c31", "team", 13, "Бюджет", "Какой бюджет на первые 6 месяцев?", False, [
        ("Нулевой (Recommended)", "Только своё время; платные каналы и подрядчики не рассматриваются", {"strategy.budget.variants": ["zero"]}),
        ("Малый", "До 50 тыс. ₽ / $500: домен, хостинг, немного продвижения", {"strategy.budget.variants": ["small"]}),
        ("Средний", "До 500 тыс. ₽ / $5000: подрядчики, платные каналы", {"strategy.budget.variants": ["medium"]}),
        ("Посчитай три варианта", "Нулевой, малый и средний — для каждого свой план", {"strategy.budget.variants": ["zero", "small", "medium"]})]),
    ("c32", "team", 23, "Время", "Сколько часов в неделю вы готовы вкладывать?", False, [
        ("5–10 часов (Recommended)", "Вечера и выходные", {"idea.facets.hours_week": 8}),
        ("10–20 часов", "Серьёзный побочный проект", {"idea.facets.hours_week": 15}),
        ("Полный рабочий день", "Продукт — основное занятие", {"idea.facets.hours_week": 40}),
        ("Меньше 5 часов", "Урывками — план будет очень узким", {"idea.facets.hours_week": 4})]),
    ("c33", "team", 38, "Навыки", "Какие навыки есть в команде? (можно несколько)", True, [
        ("Разработка (Recommended)", "Можем сами сделать продукт", {"idea.facets.skills": ["dev"]}),
        ("Дизайн", "Интерфейсы и визуальный язык", {"idea.facets.skills": ["design"]}),
        ("Маркетинг и продажи", "Привлечение и общение с клиентами", {"idea.facets.skills": ["marketing"]}),
        ("Знание предметной области", "Опыт в сфере, которой касается продукт", {"idea.facets.skills": ["domain"]})]),
    # 8. Дизайн и бренд
    ("c34", "design", 8, "Стиль", "Какой характер у визуального языка?", False, [
        ("Спокойный и чистый (Recommended)", "Много воздуха, нейтральная палитра, один акцентный цвет", {"idea.facets.style": "calm"}),
        ("Яркий и игровой", "Смелые цвета, иллюстрации, анимация", {"idea.facets.style": "playful"}),
        ("Строгий деловой", "Плотные данные, таблицы, сдержанные цвета", {"idea.facets.style": "business"}),
        ("Тёплый и дружелюбный", "Мягкие формы, тёплые цвета, живые тексты", {"idea.facets.style": "warm"})]),
    ("c35", "design", 15, "Название", "Есть ли у продукта название?", False, [
        ("Придумай варианты (Recommended)", "Предложу 5–10 вариантов с проверкой занятости в исследовании", {"idea.facets.naming": "generate"}),
        ("Есть, впишу", "Название — в «Other»", {"idea.facets.naming": "given"}),
        ("Рабочее по идее", "Пока назову по сути идеи", {"idea.facets.naming": "working"})]),
    ("c36", "design", 39, "Тема", "Светлая или тёмная тема интерфейса?", False, [
        ("Обе, по системе (Recommended)", "Макеты в двух темах, переключение по настройке устройства", {"idea.facets.theme": "both"}),
        ("Светлая", "Только светлая тема", {"idea.facets.theme": "light"}),
        ("Тёмная", "Только тёмная тема", {"idea.facets.theme": "dark"})]),
    ("c37", "design", 40, "Бренд", "Есть ли элементы бренда?", False, [
        ("Нет, создать с нуля (Recommended)", "Палитру, шрифты и тон предложу в трёх направлениях", {"idea.facets.brand": "new"}),
        ("Есть цвет или логотип", "Опишу или дам путь в «Other»", {"idea.facets.brand": "partial"}),
        ("Бренд компании", "Нужно соответствовать существующему фирменному стилю", {"idea.facets.brand": "company"})]),
    # 9. Риски, право, критерии успеха
    ("c38", "risks", 9, "Область", "Касается ли продукт чувствительной области? (можно несколько)", True, [
        ("Нет, обычные данные (Recommended)", "Правовой разбор — только базовый (персональные данные, правила платформ)", {"idea.facets.sensitive": []}),
        ("Здоровье или психика", "Медицинские данные, советы о здоровье", {"idea.facets.sensitive": ["health"], "scope.legal": True}),
        ("Деньги и платежи", "Финансы, инвестиции, приём платежей между людьми", {"idea.facets.sensitive": ["finance"], "scope.legal": True}),
        ("Дети или персональные данные", "Пользователи младше 18 лет, документы, геолокация", {"idea.facets.sensitive": ["children_pd"], "scope.legal": True})]),
    ("c39", "risks", 14, "Успех", "Что будет успехом через 6 месяцев?", False, [
        ("100 активных пользователей (Recommended)", "Люди возвращаются к продукту каждую неделю", {"strategy.success_criteria": "100 активных пользователей в неделю через 6 месяцев"}),
        ("Первые платящие", "Хотя бы 10 человек заплатили", {"strategy.success_criteria": "первые 10 платящих клиентов через 6 месяцев"}),
        ("Подтверждённый спрос", "Лист ожидания, интервью, предзаказы до разработки", {"strategy.success_criteria": "подтверждённый спрос: лист ожидания и интервью до разработки"}),
        ("Окупаемость", "Доход покрывает расходы", {"strategy.success_criteria": "доход покрывает расходы через 6 месяцев"})]),
    ("c40", "risks", 19, "Риск", "Что беспокоит в идее больше всего?", False, [
        ("Никому не нужно (Recommended)", "Главный риск — спрос; начну с дешёвых проверок", {"idea.facets.main_risk": "demand"}),
        ("Не успею сделать", "Риск выполнения: время и навыки", {"idea.facets.main_risk": "execution"}),
        ("Скопируют крупные игроки", "Риск конкуренции", {"idea.facets.main_risk": "competition"}),
        ("Запреты и правила", "Закон, правила магазинов и платформ", {"idea.facets.main_risk": "regulation", "scope.legal": True})]),
]
CONCEPT_BY_ID = {q[0]: q for q in CONCEPT_BANK}
CONCEPT_SENSITIVE_RE = re.compile(r"здоров|медиц|психи|диагноз|лекарств|финанс|деньг|платеж|платёж|инвест|кредит|банк|дет[иейя]|ребён|ребен|"
                                  r"школьн|несовершеннолет|персональн|паспорт|документ|геолокац|health|medical|finance|payment|child|kids|personal data",
                                  re.I | re.U)

# карточка настройки режима (header, вопрос, мультивыбор, [(label, description, значение)])
CONCEPT_SETUP = [
    ("Вопросов", "Сколько вопросов об идее задать (минимум 15)?", False, [
        ("25 (Recommended)", "Все 9 тем по 2–3 вопроса — баланс точности и времени", 25),
        ("15 — минимум", "По 1–2 вопроса на тему, остальное — допущения", 15),
        ("40 — все", "Полный банк вопросов: самая точная концепция", 40)]),
    ("Глубина", "Насколько глубоко прорабатываем концепцию?", False, [
        ("Стандарт (Recommended)", "≈60 предложений, 10+ аналогов, 8+ макетов, 8 экспериментов", "standard"),
        ("Быстро", "≈50 предложений, 8 аналогов, 6 макетов — черновик концепции", "quick"),
        ("Глубоко", "≈80 предложений, 15+ аналогов, 12+ макетов", "deep")]),
    ("Форматы", "В каких форматах нужен результат? (можно несколько)", True, [
        ("Веб-страница (Recommended)", "Интерактивная офлайн-страница концепции", "html"),
        ("XLSX", "Реестр решений, оценки, модель", "xlsx"),
        ("PPTX", "Презентация концепции", "pptx"),
        ("PDF", "PDF-версия презентации", "pdf")]),
    ("Папка", "Где сохранить концепцию?", False, [
        ("Текущая папка: concept/ (Recommended)", "./concept/<имя>/<дата>/; внутри git-репозитория — отдельная ветка docs/concept-<имя>", "here"),
        ("Рядом: ../concept-<имя>/", "Соседняя папка ../concept-<имя>/<дата>/ — вне текущего проекта", "sibling"),
        ("Домашняя: ~/concepts/", "~/concepts/<имя>/<дата>/ — общая папка всех концепций", "home")]),
]
CONCEPT_SETUP_BY = {h: (h, q, m, o) for h, q, m, o in CONCEPT_SETUP}
for _h, _q, _m, _o in CONCEPT_SETUP:
    CONCEPT_SETUP_BY[_q] = (_h, _q, _m, _o)

TRANSLIT = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
            "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
            "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya", "і": "i", "ї": "yi", "є": "ye"}
# слова-обёртки в начале идеи, которые не несут смысла для имени папки
SLUG_FILLER = {"приложение", "приложения", "сервис", "сервиса", "платформа", "платформу", "бот", "бота", "сайт", "сайта", "мобильное",
               "веб", "веб-приложение", "онлайн", "для", "которое", "который", "которая", "чтобы", "это", "мое", "моё", "моя", "мой",
               "идея", "продукт", "продукта", "app", "an", "a", "the", "for", "to", "service", "platform", "bot", "website", "tool",
               "инструмент", "простое", "простой", "простая", "новый", "новое", "новая", "у", "меня"}


def slugify(text, max_len=40):
    """Текст → латинский slug (транслитерация кириллицы), слова через «-», не длиннее max_len."""
    low = str(text or "").lower()
    s = "".join(TRANSLIT.get(ch, ch) for ch in low)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > max_len:
        s = s[:max_len].rsplit("-", 1)[0] or s[:max_len]
    return s or "idea"


def idea_first_phrase(pitch):
    """Первая фраза идеи (до точки, «!», «?», «;», переноса строки или тире)."""
    t = re.sub(r"^\s*(?:!concept\b|concept\s*:|!идея\b|идея\s*:)\s*", "", str(pitch or ""), flags=re.I)
    m = re.split(r"(?<=[^\d])[.!?;\n]|\s[—–]\s", t.strip(), maxsplit=1)
    return (m[0] if m else t).strip(" «»\"'")


def idea_name_slug(pitch, given=None):
    """Имя и slug идеи: из ответа «Название», иначе — из первой фразы (без слов-обёрток, до 4 значимых слов)."""
    if given and str(given).strip():
        name = str(given).strip().strip("«»\"'")[:60]
        return name, slugify(name)
    phrase = idea_first_phrase(pitch)
    words = [w for w in re.findall(r"[\w-]+", phrase, re.U)]
    core = [w for w in words if w.lower() not in SLUG_FILLER]
    name = " ".join(words[:8]) if words else "Новая идея"
    name = (name[:1].upper() + name[1:])[:60]
    return name, slugify(" ".join((core or words)[:4]))


def concept_setup_json():
    return {"title": "Настройка концепции", "questions": [
        {"header": h, "question": q, "multiSelect": m, "options": [{"label": l, "description": d} for l, d, _ in opts]}
        for h, q, m, opts in CONCEPT_SETUP]}


def concept_select(count):
    """Первые count вопросов банка по приоритету (count ≥ 15, не больше 40). Ошибка ValueError при count < 15."""
    count = int(count)
    if count < CONCEPT_MIN_QUESTIONS:
        raise ValueError("минимум 15 вопросов об идее (запрошено %d): меньше — темы не покрываются; автопилот — concept-defaults" % count)
    return sorted(CONCEPT_BANK, key=lambda q: q[2])[:min(count, len(CONCEPT_BANK))]


def concept_coverage(selected):
    cov = {k: 0 for k, _ in CONCEPT_THEMES}
    for q in selected:
        cov[q[1]] += 1
    return cov


def _card(q):
    _id, _t, _p, h, text, multi, opts = q
    return {"header": h, "question": text, "multiSelect": multi, "options": [{"label": l, "description": d} for l, d, _ in opts]}


def concept_questions_json(count, batch=4):
    """Вопросы об идее пачками по ≤ batch (≤ 4 — ограничение AskUserQuestion) в порядке тем; заголовок пачки — темы в ней."""
    batch = max(1, min(4, int(batch)))
    sel = concept_select(count)
    theme_order = {k: i for i, (k, _) in enumerate(CONCEPT_THEMES)}
    ordered = sorted(sel, key=lambda q: (theme_order[q[1]], q[2]))
    batches = []
    nb = -(-len(ordered) // batch)                      # пачки ровные по размеру: 25 вопросов → 4+4+4+4+3+3+3, а не 6×4 и одиночный хвост
    base, extra = divmod(len(ordered), nb) if nb else (0, 0)
    pos = 0
    for k in range(nb):
        size = base + (1 if k < extra else 0)
        chunk = ordered[pos:pos + size]
        pos += size
        titles = []
        for q in chunk:
            if CONCEPT_THEME_TITLE[q[1]] not in titles:
                titles.append(CONCEPT_THEME_TITLE[q[1]])
        batches.append({"batch": len(batches) + 1, "title": " · ".join(titles), "questions": [_card(q) for q in chunk],
                        "ids": [{"id": q[0], "header": q[3], "theme": q[1], "priority": q[2]} for q in chunk]})
    cov = concept_coverage(sel)
    return {"count": len(sel), "total_bank": len(CONCEPT_BANK), "min": CONCEPT_MIN_QUESTIONS,
            "coverage": [{"theme": k, "title": t, "questions": cov[k]} for k, t in CONCEPT_THEMES],
            "all_themes_covered": all(cov.values()), "batches": batches}


def _match_label(opts, val):
    v = str(val).strip()
    for o in opts:
        if o[0] == v or o[0].replace(" (Recommended)", "") == v.replace(" (Recommended)", ""):
            return o
    return None


MARKET_WORDS = [(r"рус|\bru\b|росси|снг", "ru"), (r"англ|\ben\b|english|сша|usa|uk\b|глобал", "en"), (r"каз|\bkk\b|\bkz\b", "kk"),
                (r"укра|\buk\b|\bua\b", "uk"), (r"бел|\bbe\b|\bby\b", "be"), (r"узб|\buz\b", "uz"), (r"испан|\bes\b", "es"),
                (r"португ|бразил|\bpt\b", "pt"), (r"немец|герман|\bde\b", "de"), (r"франц|\bfr\b", "fr"), (r"япон|\bja\b", "ja"),
                (r"кита|\bzh\b", "zh"), (r"турец|турци|\btr\b", "tr")]
FORM_WORDS = [(r"моб|ios|android|айфон|андроид", "mobile"), (r"бот|telegram|телеграм|мессенджер|vk|whatsapp|mini ?app|мини-приложен", "bot"),
              (r"расширени|десктоп|desktop|windows|macos|linux|программ\w* для компьютер", "desktop"),
              (r"\bapi\b|\bcli\b|sdk|библиотек|плагин для (?:ide|разработ)", "devtool"), (r"игр|game", "game"),
              (r"блог|медиа|контент|журнал|подкаст|рассылк", "content"), (r"сайт|веб|web|браузер|saas|сервис", "saas")]


def _custom_answer(cfg, qid, text, notes):
    """Свой ответ («Other») на вопрос банка → поля run-config, где это можно сделать надёжно."""
    t = str(text).strip()
    low = t.lower()
    if qid == "c16":
        hit = next((v for rx, v in FORM_WORDS if re.search(rx, low)), None)
        set_path(cfg, "product.type", hit or "other")
        if not hit:
            cfg["assumptions"].append("Форма продукта «%s» не распознана — тип other; уточнить в фазе C3" % t)
    elif qid == "c07":
        langs = []
        for rx, code in MARKET_WORDS:
            if re.search(rx, low) and code not in langs:
                langs.append(code)
        if not langs:
            langs = [x for x in re.split(r"[,;/ ]+", low) if re.fullmatch(r"[a-z]{2}", x)]
        if langs:
            set_path(cfg, "strategy.markets", langs[:6])
        else:
            notes.append("Рынки: свой ответ «%s» не распознан — рынки определю по идее" % t)
    elif qid == "c31":
        if re.search(r"\b0\b|нол|нул|без бюджет|нет денег|бесплат", low):
            set_path(cfg, "strategy.budget.variants", ["zero"])
        else:
            set_path(cfg, "strategy.budget.variants", ["small"])
        set_path(cfg, "strategy.budget.note", t)
    elif qid == "c30":
        m = re.search(r"\d+", low)
        words = [(r"\bпят\w*|\bfive\b", 5), (r"\bчетыр\w*|\bчетвер\w*|\bfour\b", 4), (r"\bтр(?:ое|и)\b|\bthree\b", 3),
                 (r"\bдво(?:е|их)\b|\bдва\b|\bвдво[её]м\b|\btwo\b", 2)]
        n = int(m.group(0)) if m else next((v for rx, v in words if re.search(rx, low)), 1)
        set_path(cfg, "project.team_size", max(1, n))
    elif qid == "c35":
        cfg["idea"]["name_given"] = t
        cfg["idea"].setdefault("facets", {})["naming"] = "given"
    elif qid == "c22":
        set_path(cfg, "sources.competitor_list", [x.strip() for x in re.split(r"[,;\n]", t) if x.strip()])
        cfg["idea"].setdefault("facets", {})["competitors_known"] = "listed"
    elif qid == "c23":
        cfg["idea"]["inspiration"] = [x.strip() for x in re.split(r"[,;\n]", t) if x.strip()]
        cfg["idea"].setdefault("facets", {})["inspiration"] = "listed"
    elif qid == "c26":
        set_path(cfg, "strategy.monetization", t)
        set_path(cfg, "strategy.paid_tier", "no" if re.search(r"бесплатн|донат|грант|free", low) and not re.search(r"подписк|плат[ан]", low) else "auto")
    elif qid == "c27":
        m = re.search(r"\d+(?:[.,]\d+)?", low)
        if m:
            set_path(cfg, "project.price_hint", float(m.group(0).replace(",", ".")))
    elif qid == "c38" or qid == "c20":
        if CONCEPT_SENSITIVE_RE.search(low):
            set_path(cfg, "scope.legal", True)
            cfg["idea"].setdefault("facets", {}).setdefault("sensitive", []).append("custom")
    elif qid == "c39":
        set_path(cfg, "strategy.success_criteria", t)
    elif qid == "c18":
        m = re.search(r"(\d+)\s*(нед|week|мес|month)", low)
        if m and m.group(2).startswith(("мес", "month")) and int(m.group(1)) > 2:
            set_path(cfg, "strategy.horizon_months", 12)
    elif qid == "c32":
        m = re.search(r"\d+", low)
        if m:
            cfg["idea"].setdefault("facets", {})["hours_week"] = int(m.group(0))


def _apply_mapping(cfg, mapping, explicit):
    for k, v in mapping.items():
        node = cfg
        parts = k.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        if isinstance(v, list) and k.startswith("idea.facets.") and isinstance(node.get(parts[-1]), list):
            node[parts[-1]] = node[parts[-1]] + [x for x in v if x not in node[parts[-1]]]
        else:
            node[parts[-1]] = list(v) if isinstance(v, list) else v
        explicit.append(k)


def concept_base_config(repo, pitch, out_dir=None):
    """Каркас run-config режима идеи: репозиторий не анализируется, продукт — на стадии идеи."""
    cfg = base_config(repo, out_dir)
    today = cfg["created"]
    cfg["mode"] = "concept"
    cfg["repo"]["analyze"] = False
    cfg["product"].update({"name": "", "stage": "idea", "type": "saas", "local_run": "none", "url": ""})
    cfg["strategy"].update({"kind": "full", "goal": "", "depth": "standard", "proposals_min": CONCEPT_DEPTH["standard"]["proposals_min"],
                            "horizon_months": 6, "vision_years": 2, "markets": ["ru"], "budget": {"variants": ["zero"], "note": ""},
                            "paid_tier": "yes", "monetization": "freemium", "success_criteria": ""})
    cfg["project"].update({"goal": "commercial", "repo_visibility": "unknown", "publish_code": "undecided", "team_size": 1})
    cfg["scope"].update({"repo_analysis": False, "app_run": False, "issues": False, "legal": False, "design_mockups": True,
                         "design_refs": True, "competitors": True, "communities": True, "keywords": True, "events": True,
                         "unit_economics": True})
    cfg["sources"].update({"repo": False, "issues": False})
    cfg["formats"].update({"html": True, "xlsx": False, "pptx": False, "pdf": False, "md": True})
    cfg["output"].update({"dir": str(Path(out_dir).resolve()) if out_dir else "", "inside_repo": False, "git_branch": ""})
    cfg["idea"] = {"pitch": str(pitch or "").strip(), "name": "", "slug": "", "questions_count": CONCEPT_DEFAULT_QUESTIONS,
                   "answers": {}, "unanswered": [], "not_asked": [], "facets": {}, "folder_choice": "here", "created": today}
    return cfg


def _git_top_of(path):
    """Корень git-репозитория, в котором лежит путь (ближайший существующий предок), или None."""
    p = Path(path).expanduser()
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        r = subprocess.run(["git", "-C", str(p), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10)
        return Path(r.stdout.strip()).resolve() if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def concept_folder(cwd, choice, slug, today, custom=None):
    """Папка результата по ответу карточки «Папка»: here | sibling | home | свой путь."""
    cwd = Path(cwd).expanduser().resolve()
    if custom:
        p = Path(str(custom).strip()).expanduser()
        return (p if p.is_absolute() else cwd / p).resolve()
    if choice == "sibling":
        return cwd.parent / ("concept-%s" % slug) / today
    if choice == "home":
        return Path.home() / "concepts" / slug / today
    return cwd / "concept" / slug / today


def concept_set_output(cfg, cwd):
    """output.dir, inside_repo и ветка по выбору папки; внутри git-репозитория — ветка docs/concept-<slug>."""
    idea = cfg["idea"]
    if not cfg["output"].get("dir"):
        cfg["output"]["dir"] = str(concept_folder(cwd, idea.get("folder_choice"), idea["slug"], cfg["created"], idea.get("folder_custom")))
    top = _git_top_of(cfg["output"]["dir"])
    cfg["output"]["inside_repo"] = bool(top)
    cfg["output"]["git_branch"] = ("docs/concept-%s" % idea["slug"]) if top else ""
    if top:
        cfg["repo"].update({"path": str(top), "name": top.name})
    return cfg


def apply_concept_answers(cfg, answers, count=None):
    """Ответы карточек режима идеи (настройка + вопросы банка). Ключ — header, текст вопроса или id; значение — label,
    список label (мультивыбор) или свой текст. Вопросы без ответа из первых N — допущения со значением по умолчанию."""
    by_key = {}
    for q in CONCEPT_BANK:
        by_key[q[0]] = by_key[q[3]] = by_key[q[4]] = q
    explicit = cfg.setdefault("_explicit", [])
    idea, notes = cfg["idea"], []
    answered = {}
    for k, v in (answers or {}).items():
        key = str(k).strip()
        if key in CONCEPT_SETUP_BY:
            h, _q, multi, opts = CONCEPT_SETUP_BY[key]
            vals = v if isinstance(v, list) else ([x.strip() for x in str(v).split(",")] if multi else [v])
            if h == "Вопросов":
                hit = _match_label(opts, vals[0]) if vals else None
                n = hit[2] if hit else (int(re.search(r"\d+", str(vals[0])).group(0)) if vals and re.search(r"\d+", str(vals[0])) else CONCEPT_DEFAULT_QUESTIONS)
                if n < CONCEPT_MIN_QUESTIONS:
                    notes.append("Вопросов: %d меньше минимума — задаю 15" % n)
                    n = CONCEPT_MIN_QUESTIONS
                idea["questions_count"] = min(n, len(CONCEPT_BANK))
            elif h == "Глубина":
                hit = _match_label(opts, vals[0]) if vals else None
                if hit:
                    cfg["strategy"]["depth"] = hit[2]
                else:
                    set_path(cfg, "strategy.constraints", ((cfg["strategy"].get("constraints") or "") + "; " if cfg["strategy"].get("constraints") else "") + str(vals[0]))
            elif h == "Форматы":
                chosen = {(_match_label(opts, x) or (None, None, None))[2] for x in vals}
                for _l, _d, fmt in opts:
                    cfg["formats"][fmt] = fmt in chosen
                for x in vals:
                    if not _match_label(opts, x):
                        notes.append("Форматы: свой ответ «%s» — учесть вручную" % x)
            elif h == "Папка":
                hit = _match_label(opts, vals[0]) if vals else None
                if hit:
                    idea["folder_choice"] = hit[2]
                elif vals and str(vals[0]).strip():
                    idea["folder_choice"], idea["folder_custom"] = "custom", str(vals[0]).strip()
                explicit.append("output.dir")
            continue
        q = by_key.get(key)
        if not q and key in HANDOFF_HEADERS:                         # раунд 6 «Передача в разработку» общий с обычным режимом
            for lab in (v if isinstance(v, list) else [v])[:1]:
                _m, mapping = _find_option(key, lab)
                if mapping:
                    for pk, pv in mapping.items():
                        set_path(cfg, pk, pv)
                else:
                    notes.append("%s: свой ответ «%s» — учесть вручную" % (key, lab))
            continue
        if not q:
            notes.append("Неизвестный вопрос «%s» — ответ сохранён в допущения" % key)
            cfg["assumptions"].append("%s: %s" % (key, v))
            continue
        qid, theme, _p, h, text, multi, opts = q
        vals = v if isinstance(v, list) else ([x.strip() for x in str(v).split(",")] if multi and _match_label(opts, str(v).split(",")[0].strip()) else [v])
        vals = [x for x in vals if str(x).strip()]
        if not vals:
            continue
        custom = False
        if multi:                               # «Нет, обычные данные» вместе с другими вариантами теряет смысл
            hits = [_match_label(opts, x) for x in vals]
            if any(hits) and len(vals) > 1:
                vals = [x for x, hh in zip(vals, hits) if not (hh is opts[0] and qid == "c38")] or vals
        for x in vals:
            hit = _match_label(opts, x)
            if hit:
                _apply_mapping(cfg, hit[2], explicit)
            else:
                custom = True
                _custom_answer(cfg, qid, x, notes)
        answered[qid] = {"theme": theme, "header": h, "question": text, "answer": vals if multi else vals[0], "custom": custom}
    n = int(count or idea.get("questions_count") or CONCEPT_DEFAULT_QUESTIONS)
    n = max(CONCEPT_MIN_QUESTIONS, min(n, len(CONCEPT_BANK)))
    idea["questions_count"] = n
    asked = [q[0] for q in concept_select(n)]
    # значения по умолчанию — для всех вопросов без ответа (заданные, но пропущенные, — в допущения поимённо)
    for q in sorted(CONCEPT_BANK, key=lambda x: x[2]):
        qid = q[0]
        if qid in answered:
            continue
        default = q[6][0]
        for k, v in default[2].items():
            if k not in explicit:
                _apply_mapping(cfg, {k: v}, [])
        if qid in asked:
            idea["unanswered"].append(qid)
            cfg["assumptions"].append("%s «%s»: не отвечено → допущение «%s»" % (qid, q[4], default[0].replace(" (Recommended)", "")))
        else:
            idea["not_asked"].append(qid)
    if idea["not_asked"]:
        cfg["assumptions"].append("Вопросы вне выбранных %d не задавались (%d шт.) — для них значения по умолчанию" % (n, len(idea["not_asked"])))
    idea["answers"] = {k: answered[k] for k in sorted(answered)}
    return notes


def concept_finish(cfg, cwd, request=""):
    """Имя и slug, цель, цена по диапазону, папка, проверка запроса «в/вне репозитория», finalize."""
    idea = cfg["idea"]
    given = idea.pop("name_given", None)
    notes = []
    facets = idea.get("facets") or {}
    if facets.get("naming") == "given" and not given:
        notes.append("Название: выбрано «Есть, впишу», но текста нет — рабочее имя по идее; уточнить у владельца")
    name, slug = idea_name_slug(idea["pitch"], given)
    idea["name"], idea["slug"] = name, slug
    cfg["product"]["name"] = name
    cfg["strategy"]["goal"] = "концепция нового продукта: %s" % (idea_first_phrase(idea["pitch"]) or name)
    if not idea["pitch"]:
        notes.append("Идея не передана (--idea) — досье будет пустым; повторить concept-apply с --idea \"<текст>\"")
    if facets.get("sensitive"):
        cfg["scope"]["legal"] = True
    concept_set_output(cfg, cwd)
    notes += check_concept_folder(cfg, cwd, request)
    finalize(cfg)
    band = facets.get("price_band")
    if cfg["project"].get("price_hint") is None and band in ("low", "mid", "high"):
        rub = cfg["project"]["currency"] == "RUB"
        cfg["project"]["price_hint"] = {"low": 299 if rub else 5, "mid": 990 if rub else 15, "high": 4990 if rub else 49}[band]
        cfg["assumptions"].append("Ориентир цены %s %s/мес — по ответу «Цена» (диапазон %s)" % (cfg["project"]["price_hint"], cfg["project"]["currency"], band))
    return notes


def check_concept_folder(cfg, cwd, request):
    """Та же защита «ВНУТРИ/ВНЕ», что у обычной папки: слова запроса против фактического положения папки концепции."""
    asked = from_text(request).get("output.inside_repo")
    if asked is None:
        return []
    explicit = "output.dir" in (cfg.get("_explicit") or [])
    inside = cfg["output"]["inside_repo"]
    if asked == inside:
        return []
    if not explicit and asked is False and inside:      # карточку не отвечали: «вне репозитория» → соседняя папка
        cfg["idea"]["folder_choice"] = "sibling"
        cfg["output"]["dir"] = ""
        concept_set_output(cfg, cwd)
        if not cfg["output"]["inside_repo"]:
            return ["Папка взята из запроса: вне репозитория (%s)" % cfg["output"]["dir"]]
    cfg["output"]["folder_conflict"] = True
    return ["ВНИМАНИЕ: в запросе сказано «%s репозитория», а папка концепции %s git-репозитория. Переспросить одной строкой и при "
            "необходимости повторить concept-apply с --out-dir <папка>" % ("внутри" if asked else "вне", "ВНУТРИ" if cfg["output"]["inside_repo"] else "ВНЕ")]


def concept_defaults(cfg, cwd, request=""):
    """Автопилот режима идеи: первые 15 вопросов считаются отвеченными значениями по умолчанию."""
    cfg["autopilot"] = True
    explicit = cfg.setdefault("_explicit", [])
    sel = concept_select(CONCEPT_MIN_QUESTIONS)
    for q in sel:
        qid, theme, _p, h, text, multi, opts = q
        _apply_mapping(cfg, opts[0][2], explicit)
        lab = opts[0][0]
        cfg["idea"]["answers"][qid] = {"theme": theme, "header": h, "question": text, "answer": [lab] if multi else lab,
                                       "custom": False, "default": True}
    cfg["idea"]["questions_count"] = CONCEPT_MIN_QUESTIONS
    cfg["idea"]["not_asked"] = [q[0] for q in sorted(CONCEPT_BANK, key=lambda x: x[2]) if q[0] not in cfg["idea"]["answers"]]
    for qid in cfg["idea"]["not_asked"]:
        for k, v in CONCEPT_BY_ID[qid][6][0][2].items():
            if k not in explicit:
                _apply_mapping(cfg, {k: v}, [])
    cfg["assumptions"].append("Автопилот: 15 вопросов об идее отвечены значениями по умолчанию — на вашу проверку")
    return []


def show_concept(cfg):
    s, sc, f, idea = cfg["strategy"], cfg["scope"], cfg["formats"], cfg.get("idea") or {}
    n = idea.get("questions_count") or CONCEPT_MIN_QUESTIONS
    answered = len(idea.get("answers") or {})
    pitch = idea.get("pitch") or ""
    lines = [
        "Режим: концепция нового продукта (идея: %s), вопросов отвечено %d из %d" % ((pitch[:120] + "…") if len(pitch) > 120 else pitch, answered, n),
        "Продукт: %s (стадия: идея, продукта ещё нет); имя папки: %s; тип: %s" % (cfg["product"]["name"], idea.get("slug", ""), cfg["product"]["type"]),
        "Концепция: %s, глубина %s, предложений ≥ %d, горизонт %d мес + видение %d г." % (s["kind"], s["depth"], s["proposals_min"], s["horizon_months"], s["vision_years"]),
        "Исследования: конкуренты и аналоги %s (≥%d), сообщества %s, спрос %s, события %s, право %s" % (
            _yn(sc["competitors"]), sc["competitors_min"], _yn(sc["communities"]), _yn(sc["keywords"]), _yn(sc["events"]), _yn(sc["legal"])),
        "Дизайн: макеты %s (≥%d), референсы %s; экономика %s; эксперименты %d; спеки топ-%d; Kanban %d карточек" % (
            _yn(sc["design_mockups"]), sc["mockups_min"], _yn(sc["design_refs"]), _yn(sc["unit_economics"]), sc["experiments"], sc["specs_top"], sc["kanban_cards"]),
        "Рынки: %s; бюджет: %s; модель дохода: %s (платный уровень: %s)" % (", ".join(s["markets"]), ", ".join(s["budget"]["variants"]), s.get("monetization") or "—", s["paid_tier"]),
        "Команда: %s, валюта %s, профиль %s" % (cfg["project"]["team_size"], cfg["project"]["currency"], s["profile"]),
        "Форматы: %s" % ", ".join(k for k, v in f.items() if v),
        "Инструменты: TypeSafe %s, субагенты %s (до %d), установка %s" % (
            cfg["tools"]["typesafe"], _yn(cfg["tools"]["subagents"]), cfg["tools"]["max_parallel_agents"], cfg["tools"].get("install", "local-auto")),
        _handoff_line(cfg),
        ("Папка: %s — ВНУТРИ git-репозитория %s (ветка %s)" % (cfg["output"]["dir"], cfg["repo"]["path"], cfg["output"]["git_branch"])) if cfg["output"]["inside_repo"]
        else ("Папка: %s — ВНЕ РЕПОЗИТОРИЯ: в git не попадёт. Нужна внутри git-репозитория — повторить concept-apply с --out-dir <repo>/concept/<имя>/<дата> "
              "или позже init_run.py <OUT> --relocate <repo>/concept/<имя>/<дата> --repo <repo> --inside-repo" % cfg["output"]["dir"]),
    ]
    if s.get("success_criteria"):
        lines.insert(3, "Критерий успеха: %s" % s["success_criteria"])
    if idea.get("unanswered"):
        lines.append("Не отвечено (допущения): %s" % ", ".join(idea["unanswered"]))
    if cfg["author"].get("copyright"):
        lines.append("Авторство: %s" % cfg["author"]["copyright"])
    if cfg["assumptions"]:
        lines.append("Допущения: " + "; ".join(cfg["assumptions"]))
    return "\n".join(lines)


def _read_answers_arg(raw):
    raw = sys.stdin.read() if raw == "-" else Path(raw[1:]).read_text(encoding="utf-8") if raw.startswith("@") else raw
    return json.loads(raw)


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
    q.add_argument("--round", type=int, help="0 — «Заказчик и продукт» (первым), 1–6 — основные раунды; без него — 0–6")
    q.add_argument("--json", action="store_true", help="вывод и так JSON; флаг принимается для единообразия с open/detect")
    up = sub.add_parser("update", help="ответы на уточняющие вопросы (follow_up) → тот же run-config")
    up.add_argument("target", help="<OUT> или путь к run-config.json")
    up.add_argument("--set", action="append", default=[])
    up.add_argument("--from-askuser", help="ответы на follow_up-карточки (JSON, @файл или -)")
    up.add_argument("--json", action="store_true")
    up.add_argument("--lenient", action="store_true")
    dc = sub.add_parser("disclosure-check", help="упоминания автоматизации в deliverables/ при disclosure=none|summary")
    dc.add_argument("out")
    dc.add_argument("--json", action="store_true")
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
            p.add_argument("--request", default="", help="исходный текст запроса пользователя: слова «в/вне репозитория» сверяются с ответом карточки «Папка»")
            p.add_argument("--json", action="store_true", help="сводка, заметки, follow_up и прогноз одним JSON")
            p.add_argument("--lenient", action="store_true", help="неизвестные ключи ответа — предупреждение, а не ошибка")
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
    cs = sub.add_parser("concept-setup", help="режим идеи: карточка настройки (4 вопроса)")
    cs.add_argument("--json", action="store_true")
    cq = sub.add_parser("concept-questions", help="режим идеи: первые N вопросов банка пачками по ≤ 4")
    cq.add_argument("--count", type=int, default=CONCEPT_DEFAULT_QUESTIONS)
    cq.add_argument("--batch", type=int, default=4)
    cq.add_argument("--json", action="store_true")
    for name in ("concept-apply", "concept-defaults"):
        p = sub.add_parser(name)
        p.add_argument("--repo", default=".", help="текущая папка пользователя (от неё считается папка результата)")
        p.add_argument("--idea", default="", help="идея дословно")
        p.add_argument("--out-dir")
        p.add_argument("--set", action="append", default=[])
        p.add_argument("--request", default="", help="исходный запрос: слова «в/вне репозитория» сверяются с папкой")
        if name == "concept-apply":
            p.add_argument("--from-askuser", required=True, help="ответы карточек (JSON-строка, @файл или - для stdin)")
            p.add_argument("--count", type=int, help="сколько вопросов задавали (иначе — ответ карточки «Вопросов», по умолчанию 25)")
    a = ap.parse_args(argv)

    if a.cmd == "concept-setup":
        d = concept_setup_json()
        if a.json:
            print(json.dumps(d, ensure_ascii=False, indent=2))
        else:
            print(d["title"] + ":")
            for i, q in enumerate(d["questions"], 1):
                print("%d. [%s] %s" % (i, q["header"], q["question"]))
                for o in q["options"]:
                    print("   - %s — %s" % (o["label"], o["description"]))
            print("   (в «Папка» свой путь — через «Other»; в «Вопросов» — своё число ≥ 15)")
        return 0
    if a.cmd == "concept-questions":
        try:
            d = concept_questions_json(a.count, a.batch)
        except ValueError as e:
            print("ошибка: %s" % e, file=sys.stderr)
            return 2
        if a.json:
            print(json.dumps(d, ensure_ascii=False, indent=2))
            return 0
        print("Вопросов об идее: %d из %d (минимум %d); пачек: %d" % (d["count"], d["total_bank"], d["min"], len(d["batches"])))
        print("Покрытие тем:")
        for c in d["coverage"]:
            print("  %-32s %d" % (c["title"], c["questions"]))
        for b in d["batches"]:
            print("\nПачка %d — %s" % (b["batch"], b["title"]))
            for q, meta in zip(b["questions"], b["ids"]):
                print("  %s [%s] %s" % (meta["id"], q["header"], q["question"]))
                for o in q["options"]:
                    print("     - %s — %s" % (o["label"], o["description"]))
        return 0
    if a.cmd in ("concept-apply", "concept-defaults"):
        cfg = concept_base_config(a.repo, a.idea, a.out_dir)
        if a.out_dir:
            cfg.setdefault("_explicit", []).append("output.dir")
        notes = []
        if a.cmd == "concept-apply":
            try:
                answers = unwrap_answers(_read_answers_arg(a.from_askuser))
            except (ValueError, OSError) as e:
                print("ошибка: --from-askuser не читается как JSON (%s)" % e, file=sys.stderr)
                return 2
            if a.count is not None and a.count < CONCEPT_MIN_QUESTIONS:
                print("ошибка: минимум 15 вопросов об идее (--count %d); автопилот — concept-defaults" % a.count, file=sys.stderr)
                return 2
            notes += apply_concept_answers(cfg, answers, a.count)
        else:
            notes += concept_defaults(cfg, a.repo, a.request)
        _apply_sets(cfg, a.set)
        notes += concept_finish(cfg, a.repo, a.request)
        path = write_config(cfg)
        print(show(cfg))
        for n in notes:
            print("Заметка: " + n)
        print("\nrun-config: %s" % path)
        print("OUT=%s" % cfg["output"]["dir"])
        return 0

    if a.cmd == "questions":
        print(json.dumps(questions_json(a.round, context=True), ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "update":
        try:
            cfg, path, notes = cmd_update(a.target, a.set, a.from_askuser, strict=not a.lenient)
        except AnswerError as e:
            print("ошибка: %s" % e, file=sys.stderr)
            return 2
        except (OSError, ValueError) as e:
            print("ошибка: run-config или ответ не читается (%s)" % e, file=sys.stderr)
            return 2
        return _print_result(cfg, path, notes, a.json)
    if a.cmd == "disclosure-check":
        level, found = disclosure_check(a.out)
        if a.json:
            print(json.dumps({"disclosure": level, "found": found}, ensure_ascii=False, indent=2))
        elif level == "full":
            print("disclosure=full — проверка не нужна")
        elif not found:
            print("disclosure=%s: упоминаний автоматизации в deliverables/ нет" % level)
        else:
            print("disclosure=%s: найдено %d упоминаний автоматизации в deliverables/ — убрать или перенести в build/:" % (level, len(found)))
            for x in found[:50]:
                print("  %s:%d «%s» — %s" % (x["file"], x["line"], x["term"], x["text"][:140]))
        return 1 if found else 0
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
        try:
            if a.answers:
                notes += apply_answers(cfg, unwrap_answers(json.loads(Path(a.answers).read_text(encoding="utf-8"))))
            if a.from_askuser:
                notes += apply_from_askuser(cfg, _read_answers_arg(a.from_askuser), strict=not a.lenient)
        except AnswerError as e:
            print("ошибка: --from-askuser: %s. Ничего не записано; исправьте ключи или повторите с --lenient" % e, file=sys.stderr)
            return 2
        except (ValueError, OSError) as e:
            print("ошибка: ответ не читается как JSON (%s)" % e, file=sys.stderr)
            return 2
        if a.open:
            apply_open(cfg, json.loads(Path(a.open).read_text(encoding="utf-8")))
    else:
        cfg["autopilot"] = True
        cfg["assumptions"].append("Автопилот: параметры по умолчанию, опрос пропущен")
    _apply_sets(cfg, a.set)
    notes += check_folder_request(cfg, getattr(a, "request", ""))
    cfg = finalize(cfg)
    path = write_config(cfg)
    return _print_result(cfg, path, notes, getattr(a, "json", False))


def _print_result(cfg, path, notes, as_json=False):
    if as_json:
        print(json.dumps({"out": cfg["output"]["dir"], "run_config": str(path), "summary": show(cfg), "notes": notes,
                          "follow_up": cfg.get("follow_up") or [], "forecast": cfg.get("forecast")}, ensure_ascii=False, indent=2))
        return 0
    print(show(cfg))
    for n in notes:
        print("Заметка: " + n)
    for x in cfg.get("follow_up") or []:
        print("Уточнить: [%s] %s → intake.py update %s --set %s=…" % (x.get("header"), x.get("question"), cfg["output"]["dir"], x.get("path")))
    print("\nrun-config: %s" % path)
    print("OUT=%s" % cfg["output"]["dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
