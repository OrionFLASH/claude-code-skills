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
  intake.py concept-intro [--request "<запрос>"] [--json]
                                                      карточка «Начало» (до банка, 1.5): для кого приложение (личный режим
                                                      project.audience), режим опроса (по темам / быстро / глубоко), модели и
                                                      effort субагентов (tools.agents); подсказка из текста запроса
  intake.py concept-questions --count N [--batch 4] [--audience A] [--mode standard|fast|deep] [--request "<запрос>"]
                              [--prefill '<JSON|@файл>'] [--json]
                                                      первые N вопросов банка (40 вопросов, 9 тем) по приоритету пачками
                                                      по ≤ 4 для AskUserQuestion; N < 15 — ошибка; покрытие тем в начале.
                                                      --audience personal|circle|personal_then_public — вопросы о рынке и
                                                      деньгах заменены вопросами о себе; --request/--prefill — уверенные
                                                      ответы из текста идут одной карточкой «Из запроса понял…» (confirm),
                                                      освободившиеся места занимают блоки (платформа, данные, ИИ), «живых»
                                                      вопросов ≥ 15; --mode fast — таблица на тему вместо вопросов
  intake.py concept-blocks --answers '<JSON|@файл>' [--request "<запрос>"] [--prefill …] [--mode …] [--count N] [--json]
                                                      условные блоки по ответам: ИИ, админка, данные, внешняя платформа,
                                                      право по областям, интерфейс, прототип, контекст владельца, оплата
  intake.py concept-apply --repo <cwd> --idea "<идея>" --from-askuser '<JSON|@файл|->' [--out-dir D] [--set k=v]
                          [--request "<запрос>"] [--count N] [--prefill …] [--request-questions '<JSON>']
                          [--topic-en "<перевод темы>"] [--keywords "a, b"] [--name "<имя>"] [--slug <slug>]
                          [--branch auto|none] [--branch-name B] [--dry-run] [--json]
                                                      ответы карточек (ключ — header, текст вопроса или id c01…c40, p01…,
                                                      блоки) → <OUT>/build/run-config.json с mode: concept и блоком idea;
                                                      OUT=…; разбор запроса (вопросы RQ, ссылки владельца), проверки
                                                      противоречий и ёмкости → follow_up до «Начинаю?»; внутри git — ветка
                                                      прогона создаётся ДО первой записи (--branch none — не трогать git);
                                                      --dry-run — только сводка и follow_up, без записи и git
  intake.py concept-defaults --idea "<идея>" [--repo <cwd>] [--out-dir D] [--set k=v] [те же флаги имени/ветки]
                                                      автопилот: 15 вопросов отвечены значениями по умолчанию (допущения)
  intake.py concept-check <OUT> [--json]              пересчитать проверки ответов (противоречия, ёмкость) → follow_up
  intake.py concept-verdict <OUT> [--json]            красный/жёлтый светофор (data/typesafe-concept.json) → карточка «что
                                                      дальше» с вариантом «нарезка на очереди»; ответ — intake.py update
                                                      <OUT> --from-askuser '{"Светофор": "…"}' → блок slicing

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import concept_banks as cb  # noqa: E402 — банки 1.5, разбор текста запроса (не импортирует intake)
import concept_checks as cc  # noqa: E402 — проверки до «Начинаю?», git, правила владельца (не импортирует intake)

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
    else:
        concept_refresh(cfg)
    cfg.pop("_explicit", None)
    return cfg


SLICE_KEYS = {"Продолжить с нарезкой на очереди": "slice", "Продолжить без изменений": "continue", "Уточнить идею": "refine",
              "Остановиться": "stop"}


def concept_refresh(cfg):
    """Режим идеи после update: решения по проверкам и имени, нарезка на очереди после светофора, ёмкость, новые проверки."""
    idea = cfg.setdefault("idea", {})
    dec = idea.get("decisions") or {}
    if dec.get("name") and dec["name"] not in NAME_OK and idea.get("name_applied") != dec["name"]:
        nm = clean_given_name(dec["name"])
        if nm:
            cfg["product"]["name"] = idea["name"] = nm
            idea["name_source"], idea["name_applied"] = "given", dec["name"]
            cfg["assumptions"].append("Имя «%s» — от владельца после записи конфига; папка и ветка остаются %s (переименовать — "
                                      "init_run.py <OUT> --relocate …)" % (nm, idea.get("slug")))
    sl = cfg.get("slicing") or {}
    raw = sl.get("decision") or dec.get("slicing")
    if raw:
        key = SLICE_KEYS.get(str(raw).replace(" (Recommended)", ""), raw)
        if key == "slice" and not sl.get("queues"):
            doc = cc.load_verdict(cfg["output"].get("dir") or ".")
            cfg["slicing"] = dict(cc.build_slicing(cfg, doc), decision="slice")
            f = idea.setdefault("facets", {})
            if f.get("mvp") != "single_feature":
                f["mvp_before_slicing"] = f.get("mvp")
                f["mvp"] = "single_feature"
            cfg["assumptions"].append("Светофор %s → нарезка на очереди: MVP — один сквозной сценарий (α), затем β, v1, v2 с условиями "
                                      "входа; приоритет — дешёвые проверки слабых мест" % ((doc or {}).get("verdict") or "—"))
        elif key in ("continue", "refine", "stop"):
            cfg["slicing"] = dict(sl, decision=key, enabled=False)
    cap = (cfg.get("project") or {}).get("capacity") or {}
    if not isinstance(cap, dict) or str(cap.get("source") or "").startswith(("ответ c32", "значение по умолчанию c32")):
        concept_capacity(cfg)
    concept_run_checks(cfg)
    concept_registry(cfg)
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
        ("Веб-приложение (Recommended)", "Сайт-сервис в браузере, работает и на телефоне", {"product.type": "saas", "product.forms": ["web"]}),
        ("Мобильное приложение", "iOS и/или Android, магазины приложений", {"product.type": "mobile", "product.forms": ["mobile"]}),
        ("Бот в мессенджере", "Бот или мини-приложение в мессенджере", {"product.type": "bot", "product.forms": ["bot"]}),
        ("Расширение или десктоп", "Расширение браузера или программа для компьютера", {"product.type": "desktop", "product.forms": ["desktop"]})]),
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
        ("Домашняя: ~/concepts/", "~/concepts/<имя>/<дата>/ — общая папка всех концепций", "home"),
        ("Плоско: concept/<имя>/", "./concept/<имя>/ без папки даты (дата — в файлах); для небольших репозиториев", "flat")]),
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
    """Первая фраза идеи: до конца предложения («.», «!», «?» с пробелом после), «;», «:», переноса строки или тире;
    скобки выкидываются («Веб-сервис (адаптив, …) для анализа …» → «Веб-сервис для анализа …»)."""
    t = re.sub(r"^\s*(?:!concept\b|concept\s*:|!идея\b|идея\s*:)\s*", "", str(pitch or ""), flags=re.I)
    t = re.sub(r"\([^()]*\)", " ", t)
    m = re.split(r"(?<=[^\d])[.!?](?=\s|$)|[;\n]|:(?!//)|\s[—–]\s", t.strip(), maxsplit=1)
    head = (m[0] if m else t).strip()
    if len(m) > 1 and len(head.split()) <= 2 and re.match(r"^[^:]{1,30}:(?!//)", t.strip()) and m[1].strip():
        rest = re.split(r"(?<=[^\d])[.!?](?=\s|$)|[;\n]|:(?!//)|\s[—–]\s", m[1].strip(), maxsplit=1)
        head = rest[0] if rest and rest[0].strip() else head      # «Демо: приложение для …» — ярлык до двоеточия не идея
    return re.sub(r"\s+", " ", head).strip(" «»\"'")


# имя идеи (FB-022): оценочные слова и формы продукта в начале фразы не дают имени; составные «приложение-трекер» → «трекер»
EVAL_WORDS = {"платный", "платная", "платное", "бесплатный", "бесплатная", "бесплатное", "простой", "простая", "простое",
              "удобный", "удобная", "удобное", "умный", "умная", "умное", "лучший", "лучшая", "крутой", "мощный", "современный",
              "небольшой", "маленький", "личный", "личная", "персональный", "новый", "новая", "новое", "мой", "моя", "моё", "мое"}
FORM_HEADS = {"приложение", "приложения", "сайт", "сайта", "сервис", "сервиса", "веб-сервис", "веб-приложение", "бот", "бота",
              "платформа", "портал", "app", "website", "service", "tool", "инструмент", "программа", "расширение",
              "мини-приложение", "pwa", "веб"}
NAME_FUNCTION = {"для", "и", "в", "во", "с", "со", "на", "по", "о", "об", "от", "до", "из", "через", "под", "при", "а", "или",
                 "чтобы", "который", "которое", "которая", "for", "and", "with", "of", "the", "a", "an", "to"}
WORKING_PREFIX_RE = re.compile(r"^\s*(?:рабоч\w*(?:\s+(?:название|имя))?|временн\w*(?:\s+(?:название|имя))?|пока|кодов\w*\s+имя|"
                               r"working(?:\s+(?:title|name))?|codename|tbd)\s*[:—–-]\s*", re.I | re.U)


def clean_given_name(text):
    """Ответ «Название» без служебных префиксов («Рабочее: Smart Market Lens AI» → «Smart Market Lens AI», SM 3.5)."""
    s = str(text or "").strip().strip("«»\"'")
    s = WORKING_PREFIX_RE.sub("", s).strip().strip("«»\"'")
    return s[:60]


def _degenitive(word):
    """Первое слово после «для» — в именительный падеж (простые окончания): анализа → анализ, учёта → учёт,
    планирования → планирование, аренды → аренда, доставки → доставка, контроля → контроль."""
    w = word
    low = w.lower()
    if low.endswith("ия") and len(low) > 4:
        return w[:-2] + "ие"
    if low.endswith(("ки", "ги", "хи")) and len(low) > 3:
        return w[:-1] + "а"
    if low.endswith("ы") and len(low) > 3:
        return w[:-1] + "а"
    if low.endswith("я") and len(low) > 4 and not low.endswith(("ая", "яя")):
        return w[:-1] + "ь"
    if low.endswith("а") and len(low) > 3 and not low.endswith(("ая", "ья")):
        return w[:-1]
    return w


def _is_entity_token(tok, first=False):
    if "-" in tok and re.search(r"[A-Za-z]", tok) and re.search(r"[А-Яа-яЁё]", tok):
        return False                                            # «ARC-роботов» — производное от сущности, не сущность
    if re.search(r"[A-Za-z]", tok) and not tok.lower() in FORM_HEADS:
        return True
    return (not first) and tok[:1].isupper() and tok.lower() not in FORM_HEADS


def idea_entities(text, limit=4):
    """Сущности (имена собственные) в тексте: подряд идущие слова с заглавной буквы или латиницей («ARC Raiders»,
    «Smart Market Lens AI»); прилагательное с заглавной + существительное («Московской биржи»). Слова через дефис
    с частью сущности («ARC-роботов») — не отдельная сущность."""
    out = []
    text = cb.BARE_DOMAIN_RE.sub(" ", cb.URL_RE.sub(" ", str(text or "")))     # домены и ссылки — не сущности
    for sent in re.split(r"(?<=[.!?])\s+|[;\n]", text):
        toks = re.findall(r"[\w'’-]+", re.sub(r"\([^()]*\)", " ", sent).replace("/", " "), re.U)
        i = 0
        while i < len(toks):
            if _is_entity_token(toks[i], first=(i == 0)) and toks[i].lower() not in NAME_FUNCTION:
                j = i
                run = []
                while j < len(toks) and _is_entity_token(toks[j], first=(j == 0 and not run)) and toks[j].lower() not in NAME_FUNCTION:
                    run.append(toks[j])
                    j += 1
                if len(run) == 1 and re.search(r"(?:ой|ий|ый|ая|ое|ские|ской|ского)$", run[0]) and j < len(toks) and \
                        re.fullmatch(r"[а-яё-]+", toks[j]):
                    run.append(toks[j])
                    j += 1
                ent = " ".join(run)
                if not (i == 0 and len(run) == 1 and not re.search(r"[A-Za-z]", run[0])) and ent not in out:
                    out.append(ent)
                i = j
            else:
                i += 1
            if len(out) >= limit:
                return out
    return out


def auto_name(pitch):
    """Рабочее имя из первой фразы (≤ 4 слов, сущность цела): «Платный сайт/приложение-трекер для игры ARC Raiders: …»
    → «Трекер ARC Raiders»; «Приложение для обмена книгами между соседями» → «Обмен книгами между соседями»."""
    phrase = idea_first_phrase(pitch)
    toks = re.findall(r"[\w'’-]+", phrase.replace("/", " "), re.U)
    while toks and toks[0].lower() in EVAL_WORDS:
        toks.pop(0)
    if not toks:
        return "Новая идея"
    noun = None
    for t in toks:
        parts = t.split("-")
        if len(parts) == 2 and parts[0].lower() in FORM_HEADS and parts[1] and parts[1].lower() not in FORM_HEADS:
            noun = parts[1]
            break
    ents = idea_entities(phrase)
    if noun and ents:
        ent = ents[0].split()[:3]
        return " ".join([noun[:1].upper() + noun[1:]] + ent)
    words = list(toks)
    if len(words) >= 3 and words[0].lower() in FORM_HEADS and words[1].lower() == "для":
        words = [_degenitive(words[2])] + words[3:]
    elif noun and words[0].lower() != noun.lower():
        words = [noun] + [w for w in words[1:] if w.lower() not in FORM_HEADS]
    out = []
    for w in words:
        if len(out) >= 4:
            break
        out.append(w)
    while len(out) > 1 and out[-1].lower() in NAME_FUNCTION:
        out.pop()
    # не резать сущность пополам: если 4-е слово — начало многословной сущности, убрать её целиком
    joined = " ".join(out)
    for e in ents:
        parts = e.split()
        if len(parts) > 1 and parts[0] in out and not all(p in out for p in parts):
            out = out[:out.index(parts[0])] or parts[:4]
            while len(out) > 1 and out[-1].lower() in NAME_FUNCTION:
                out.pop()
            joined = " ".join(out)
            break
    name = joined or "Новая идея"
    return (name[:1].upper() + name[1:])[:60]


def idea_name_slug(pitch, given=None, topic_en=None):
    """Имя и slug идеи: из ответа «Название» (без префиксов «Рабочее:»), иначе — рабочее имя из первой фразы
    (auto_name, ≤ 4 слов). slug — из имени (транслитерация); при переводе темы (--topic-en) и автоимени — из перевода
    («ARC Raiders tracker» → arc-raiders-tracker)."""
    g = clean_given_name(given) if given else ""
    if g:
        return g, slugify(g)
    name = auto_name(pitch)
    if topic_en and str(topic_en).strip():
        return name, slugify(topic_en)
    return name, slugify(name)


KW_STOP = set("""и в во на с со по для из от до за к ко о об обо у а но или же ли не ни что чтобы как это эти этот эта который которая
которые которое мой моя моё мое свой своя своё свои их его её ее при между через без над под про все всех всё весь
можно нужно будет будут есть быть очень также ещё еще где когда кто там тут так даже уже только""".split())
KW_GENERIC = {"игры", "игра", "игр", "игре", "игру", "сайт", "сайта", "версия", "версию", "версии", "мобильную", "мобильная",
              "мобильной", "адаптивная", "адаптивной", "адаптивный", "верстка", "вёрстка", "верстки", "заделом", "задел",
              "также", "помощью", "через", "много", "различных", "вариантов", "выбор", "выбора", "бэкенд", "бэкенда", "бд",
              "ориентир", "ориентиром", "пользователя", "пользователей", "пользователь", "людей", "человек", "нужно",
              "хочу", "сделать", "интерфейса", "интерфейс", "синхронизация", "синхронизации", "анализа", "расчёт", "расчет"}


def idea_keywords(pitch, n=6, extra_stop=()):
    """Ключевые слова идеи (FB-022, SM 6.2): сущности целиком («ARC Raiders»), затем существительное из составной формы
    («приложение-трекер» → «трекер»), затем значимые слова первой фразы и остального текста без служебных, оценочных
    слов и слов формы («платный», «сайт», «игры», «адаптивная»…); слова с частью сущности («ARC-роботов») пропускаются."""
    stop = set(SLUG_FILLER) | EVAL_WORDS | FORM_HEADS | KW_GENERIC | KW_STOP | set(extra_stop) | NAME_FUNCTION
    text = re.sub(r"^\s*(?:!concept\b|concept\s*:|!идея\b|идея\s*:)\s*", "", str(pitch or ""), flags=re.I)
    text = cb.BARE_DOMAIN_RE.sub(" ", cb.URL_RE.sub(" ", text))
    ents = idea_entities(text)
    ent_parts = {p.lower() for e in ents for p in e.split()}
    out = ents[:1]
    first = idea_first_phrase(text)
    for t in re.findall(r"[\w-]+", first.replace("/", " ")):
        parts = t.lower().split("-")
        if len(parts) == 2 and parts[0] in FORM_HEADS and parts[1] not in FORM_HEADS and parts[1] not in out:
            out.append(parts[1])
            break
    for e in ents[1:3]:
        if e.lower() not in [x.lower() for x in out]:
            out.append(e)
    rest = text
    for chunk in (first, rest):
        for w in re.findall(r"[\w-]{3,}", re.sub(r"\([^()]*\)", lambda m: " " + m.group(0)[1:-1] + " ", chunk).replace("/", " "), re.U):
            lw = w.lower()
            parts = lw.split("-")
            if len(parts) == 2 and parts[0] in FORM_HEADS:
                lw = parts[1]
            if lw in stop or lw.isdigit() or lw in ent_parts or (len(parts) == 2 and (parts[0] in ent_parts or parts[1] in ent_parts)):
                continue
            if lw not in [x.lower() for x in out]:
                out.append(lw)
            if len(out) >= n:
                return out
    return out[:n]


def idea_topic_auto(pitch):
    """Тема для поисковых запросов: рабочее имя идеи со строчной первой буквой (сущности сохраняют регистр)."""
    name = auto_name(pitch)
    if name == "Новая идея":
        return ""
    first = name.split()[0]
    if re.match(r"[А-ЯЁ][а-яё-]*$", first):
        name = first[:1].lower() + name[1:]
    return name


def concept_setup_json():
    return {"title": "Настройка концепции", "questions": [
        {"header": h, "question": q, "multiSelect": m, "options": [{"label": l, "description": d} for l, d, _ in opts]}
        for h, q, m, opts in CONCEPT_SETUP]}


def concept_select(count):
    """Первые count вопросов банка по приоритету (count ≥ 15, не больше 40). Ошибка ValueError при count < 15."""
    return concept_select_bank(CONCEPT_BANK, count)


def concept_select_bank(bank, count):
    """То же для банка, адаптированного под аудиторию (личный режим — вопросы p01…p10 вместо части c-вопросов)."""
    count = int(count)
    if count < CONCEPT_MIN_QUESTIONS:
        raise ValueError("минимум 15 вопросов об идее (запрошено %d): меньше — темы не покрываются; автопилот — concept-defaults" % count)
    return sorted(bank, key=lambda q: q[2])[:min(count, len(bank))]


def concept_coverage(selected):
    cov = {k: 0 for k, _ in CONCEPT_THEMES}
    for q in selected:
        if q[1] in cov:
            cov[q[1]] += 1
    return cov


def _card(q):
    _id, _t, _p, h, text, multi, opts = q
    return {"header": h, "question": text, "multiSelect": multi, "options": [{"label": l, "description": d} for l, d, _ in opts]}


def _q_title(q):
    if q[1] in CONCEPT_THEME_TITLE:
        return CONCEPT_THEME_TITLE[q[1]]
    if q[1] == "intro":
        return "Начало"
    key = q[1].split(":")[0]
    return cb.BLOCKS[key][0] if key in cb.BLOCKS else key


def _balanced_batches(ordered, batch=4, card=_card):
    """Пачки ровные по размеру: 25 вопросов → 4+4+4+4+3+3+3, а не 6×4 и одиночный хвост."""
    batches = []
    nb = -(-len(ordered) // batch)
    base, extra = divmod(len(ordered), nb) if nb else (0, 0)
    pos = 0
    for k in range(nb):
        size = base + (1 if k < extra else 0)
        chunk = ordered[pos:pos + size]
        pos += size
        titles = []
        for q in chunk:
            if _q_title(q) not in titles:
                titles.append(_q_title(q))
        batches.append({"batch": len(batches) + 1, "title": " · ".join(titles), "questions": [card(q) for q in chunk],
                        "ids": [{"id": q[0], "header": q[3], "theme": q[1], "priority": q[2]} for q in chunk]})
    return batches


def _answer_text(q, ans):
    if isinstance(ans, list):
        return ", ".join(str(x).replace(" (Recommended)", "") for x in ans)
    return str(ans if ans is not None else "").replace(" (Recommended)", "")


def _confirm_cards(items, look):
    """Уверенные ответы из текста → карточки «Из запроса понял: … Верно?» (до 4 вопросов по ≤ 6 пунктов)."""
    rows = []
    for qid, pv in items:
        q = look[qid][0]
        rows.append((qid, "%s — %s%s" % (q[3], _answer_text(q, pv["answer"]), " («%s»)" % pv["quote"] if pv.get("quote") else "")))
    groups = [rows[i:i + 6] for i in range(0, len(rows), 6)][:4]
    qs, ids = [], []
    for i, g in enumerate(groups):
        header = cb.CONFIRM_HEADER if i == 0 else "%s %d" % (cb.CONFIRM_HEADER, i + 1)
        qs.append({"header": header, "question": "Из запроса понял: %s. Верно? Поправки — в «Other» строками «Заголовок: ответ»."
                   % "; ".join(r for _id, r in g), "multiSelect": False,
                   "options": [{"label": "Да, верно (Recommended)", "description": "Ответы из запроса принимаются, эти вопросы не задаются"},
                               {"label": "Задать эти вопросы", "description": "Вопросы вернутся в опрос с вариантами"}]})
        ids.append([qid for qid, _r in g])
    return qs, ids


def _fast_cards(sel, pre, audience):
    """Быстрый режим (SM 3.6): одна строка-таблица на тему — значения по умолчанию и из запроса; подтвердить или поправить."""
    theme_order = [k for k, _ in CONCEPT_THEMES]
    out, ids = [], []
    for th in theme_order:
        qs = sorted([q for q in sel if q[1] == th], key=lambda q: q[2])
        if not qs:
            continue
        parts = []
        for q in qs:
            pv = pre.get(q[0])
            ans = _answer_text(q, pv["answer"]) + " (из запроса)" if pv else q[6][0][0].replace(" (Recommended)", "")
            parts.append("%s — %s" % (q[3], ans))
        out.append(("fast:" + th, th, 0, cb.THEME_CONFIRM[th],
                    "%s: %s. Верно? Поправки — в «Other» строками «Заголовок: ответ»." % (CONCEPT_THEME_TITLE[th], "; ".join(parts)), False,
                    [("Верно (Recommended)", "Принять значения темы", {}), ("Задать вопросы темы", "Вопросы темы — отдельной пачкой", {})]))
        ids.append([q[0] for q in qs])
    return out, ids


def concept_questions_json(count, batch=4, audience=None, prefill=None, request="", mode=None):
    """Вопросы об идее пачками по ≤ batch (≤ 4 — ограничение AskUserQuestion) в порядке тем; заголовок пачки — темы в ней.

    1.5: audience — личный режим (вопросы о рынке и деньгах заменены вопросами о себе); request/prefill — уверенные
    ответы из текста (≥ 0,8) выносятся в карточки confirm и не задаются, освободившиеся места (из первых N) занимают
    вопросы блоков, видимых по тексту (платформа, данные, ИИ…), «живых» вопросов не меньше 15; mode=fast — вместо
    вопросов таблица на тему. Без этих параметров — поведение 1.4 (первые N по приоритету)."""
    batch = max(1, min(4, int(batch)))
    mode = mode if mode in ("standard", "fast", "deep") else "standard"
    aud = cb.audience_of(audience)
    bank = cb.adapted_bank(CONCEPT_BANK, aud)
    sel = concept_select_bank(bank, count)
    look = cb.lookup(CONCEPT_BANK)
    pre = cb.merged_prefill(CONCEPT_BANK, request, prefill, audience_known=audience is not None) if (request or prefill) else {}
    bank_ids = {q[0] for q in bank}
    confident = {k: v for k, v in pre.items() if v["confidence"] >= cb.CONFIDENT}
    P = [q for q in sorted(bank, key=lambda q: q[2]) if q[0] in confident]
    p_ids = {q[0] for q in P}
    sel_ids = {q[0] for q in sel}
    theme_order = {k: i for i, (k, _) in enumerate(CONCEPT_THEMES)}
    block_taken = []
    if mode == "fast":
        fq, fids = _fast_cards(sel, pre, aud)
        batches = _balanced_batches(fq, batch)
        for b in batches:
            b["theme_ids"] = [fids[[x[0] for x in fq].index(i["id"])] for i in b["ids"]]
        live_ids = [q[0] for q in sel]
        cov = concept_coverage(sel)
        theme_batches = {th: _balanced_batches(sorted([q for q in sel if q[1] == th], key=lambda q: q[2]), batch)
                         for th in cb.THEME_CONFIRM if any(q[1] == th for q in sel)}
        confirm_qs, confirm_ids = [], []
    else:
        n = len(sel)
        p_in = len(p_ids & sel_ids)
        live_target = max(CONCEPT_MIN_QUESTIONS, n - p_in)                # «живых» вопросов ≥ 15
        freed = min(p_in, max(0, live_target + p_in - CONCEPT_MIN_QUESTIONS))  # блоки занимают освободившиеся места, но
                                                                               # вопросов банка (живых + из запроса) ≥ 15
        if freed and request:
            seen = set(confident)
            for _key, qs in cb.text_blocks(request, mode):
                for q in qs:
                    if q[0] not in seen and len(block_taken) < freed:
                        block_taken.append(q)
                        seen.add(q[0])
        bank_live_n = max(1, live_target - len(block_taken))
        ordered_all = sorted(bank, key=lambda q: q[2])
        live = [q for q in ordered_all if q[0] not in p_ids][:bank_live_n]
        if len(live) < bank_live_n:                      # почти всё предзаполнено: «живых» ≥ 15 — менее уверенные вопросы
            back = sorted(P, key=lambda q: (confident[q[0]]["confidence"], q[2]))[:bank_live_n - len(live)]   # возвращаются в опрос
            live += back
            P = [q for q in P if q not in back]
            p_ids = {q[0] for q in P}
        covered = {q[1] for q in live} | {q[1] for q in P}
        for th, _t in CONCEPT_THEMES:                    # покрытие тем: в каждой теме есть живой или подтверждённый вопрос
            if th in covered:
                continue
            top = next((q for q in ordered_all if q[1] == th and q[0] not in p_ids), None)
            if not top:
                continue
            counts = {}
            for q in live:
                counts[q[1]] = counts.get(q[1], 0) + 1
            victim = next((q for q in reversed(live) if counts.get(q[1], 0) > 1), None)
            if victim:
                live.remove(victim)
            live.append(top)
            covered.add(th)
        ordered = sorted(live, key=lambda q: (theme_order[q[1]], q[2])) + block_taken
        batches = _balanced_batches(ordered, batch)
        live_ids = [q[0] for q in live]
        cov = concept_coverage(live + P) if pre else concept_coverage(sel)
        theme_batches = None
        conf_items = [(q[0], confident[q[0]]) for q in P] + [(k, v) for k, v in confident.items() if k not in bank_ids and k in look
                                                            and look[k][1] in ("block", "intro") and k != "i01"]
        confirm_qs, confirm_ids = _confirm_cards(conf_items, look) if conf_items else ([], [])
    hints = [{"id": k, "header": look[k][0][3], "answer": v["answer"], "confidence": v["confidence"], "quote": v.get("quote", "")}
             for k, v in pre.items() if k not in confident and k in look]
    res = {"count": len(sel), "total_bank": len(CONCEPT_BANK), "min": CONCEPT_MIN_QUESTIONS,
           "coverage": [{"theme": k, "title": t, "questions": cov[k]} for k, t in CONCEPT_THEMES],
           "all_themes_covered": all(cov.values()), "batches": batches}
    if audience is not None or pre or mode != "standard":
        res.update({"audience": aud, "mode": mode, "live_ids": live_ids, "prefilled_ids": sorted(p_ids),
                    "blocks_in_batches": [q[0] for q in block_taken],
                    "prefill": [{"id": k, "header": look[k][0][3], "answer": v["answer"], "confidence": v["confidence"],
                                 "quote": v.get("quote", ""), "source": v.get("source")} for k, v in pre.items() if k in look],
                    "confirm": confirm_qs, "confirm_ids": confirm_ids, "hints": hints,
                    "card_count": len(batches) + (1 if confirm_qs else 0)})
        if "i01" in pre:
            res["audience_suggested"] = {"answer": pre["i01"]["answer"], "quote": pre["i01"].get("quote", "")}
        if theme_batches is not None:
            res["theme_batches"] = theme_batches
        res["next"] = ("после ответов: intake.py concept-blocks --answers '<ответы>' — условные блоки (ИИ, админка, данные, "
                       "платформа, право, интерфейс, прототип, контекст владельца)")
    return res


def concept_intro_json(request=""):
    """Карточка «Начало» (до банка): для кого приложение, режим опроса, модели и effort субагентов. По тексту запроса
    подходящий вариант «Для кого» помечается в описании (← из запроса)."""
    hint = cb.prefill_from_text(request).get("i01") if request else None
    qs = []
    for q in cb.INTRO:
        card = _card(q)
        if hint and q[0] == "i01":
            for o in card["options"]:
                if o["label"].replace(" (Recommended)", "") == str(hint["answer"]).replace(" (Recommended)", ""):
                    o["description"] += " ← из запроса: «%s»" % hint.get("quote", "")
        qs.append(card)
    return {"title": "Начало", "questions": qs, "suggested": hint,
            "note": "Задать ПЕРЕД concept-questions: ответ «Для кого» → --audience, «Опрос» → --mode"}


def _provisional_cfg(answers, request="", prefill=None, count=None, audience=None, mode=None):
    cfg = concept_base_config(".", "", None)
    cfg["idea"]["request"] = cb.mask(request)[:4000]
    if prefill is not None:
        cfg["idea"]["prefill_raw"] = prefill
    if audience:
        cfg["project"]["audience"] = cb.audience_of(audience)
    if mode:
        cfg["idea"]["interview_mode"] = mode
    apply_concept_answers(cfg, answers or {}, count)
    return cfg


def concept_blocks_json(answers, request="", prefill=None, mode=None, count=None, batch=4, audience=None):
    """Условные блоки по ответам (после банка): какие блоки и вопросы задать; уже отвеченные и уверенно предзаполненные
    (подтверждённые карточкой «Из запроса») — не задаются. → {blocks: [{key, title, why, ids}], batches, count}."""
    answers = unwrap_answers(answers or {})
    cfg = _provisional_cfg(answers, request, prefill, count, audience, mode)
    mode = mode or cfg["idea"].get("interview_mode") or "standard"
    text = " ".join(x for x in (request, cfg["idea"].get("pitch") or "") if x)
    asked = set()
    for k in answers:
        hit = cb.lookup(CONCEPT_BANK).get(str(k).strip())
        if hit:
            asked.add(hit[0][0])
    pre = cb.merged_prefill(CONCEPT_BANK, request, prefill) if (request or prefill) else {}
    asked |= {k for k, v in pre.items() if v["confidence"] >= cb.CONFIDENT}
    blocks, ordered = [], []
    for key, title, why, qs in cb.blocks_for(cfg, text, mode):
        rest = [q for q in qs if q[0] not in asked]
        if rest:
            blocks.append({"key": key, "title": title, "why": why, "ids": [q[0] for q in rest]})
            ordered += rest
    return {"mode": mode, "blocks": blocks, "batches": _balanced_batches(ordered, max(1, min(4, int(batch)))), "count": len(ordered),
            "note": "ответы блоков добавить в общий JSON ответов concept-apply (ключ — header блока)"}


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


MARKET_FILLER = {"основной", "основные", "основная", "основном", "плюс", "также", "рынок", "рынки", "рынка", "рынках", "язык",
                 "и", "а", "на", "в", "с", "для", "или", "по", "сначала", "потом", "затем", "ещё", "еще"}


def market_remainder(text):
    """Часть ответа «Рынки», где нет распознанного языка или рынка (≥ 3 значимых слова) → текст или ""."""
    clauses = re.split(r"[,;]|\s+(?:плюс|а\s+также|кроме\s+того|и\s+ещё|и\s+еще)\s+", str(text or ""), flags=re.I)
    rest = []
    for c in clauses:
        low = c.lower()
        if any(re.search(rx, low) for rx, _code in MARKET_WORDS):
            continue
        words = [w for w in re.findall(r"[\w-]+", c) if w.lower() not in MARKET_FILLER]
        if words:
            rest.append(" ".join(words))
    joined = " ".join(rest).strip()
    return joined if len([w for w in joined.split() if len(w) >= 3]) >= 3 else ""


def _custom_answer(cfg, qid, text, notes):
    """Свой ответ («Other») на вопрос банка → поля run-config, где это можно сделать надёжно."""
    t = str(text).strip()
    low = t.lower()
    if qid == "c16":
        fp = cb.parse_forms(t)                      # FB-024: все формы, «мобильная версия веба»/адаптив/PWA — это веб
        if fp["main"]:
            set_path(cfg, "product.type", fp["type"])
            set_path(cfg, "product.forms", fp["forms"])
            if fp["future"]:
                set_path(cfg, "product.future_forms", fp["future"])
            cfg["assumptions"].append("Форма продукта «%s» → тип %s; формы: %s%s%s" % (
                t, fp["type"], ", ".join(fp["forms"]), "; позже: %s" % ", ".join(fp["future"]) if fp["future"] else "",
                " («или» — выбран более дешёвый веб-путь, мобильное приложение — на потом)" if fp["alternatives"] else ""))
            if fp["ambiguous"]:
                kinds = []
                for f in fp["forms"]:
                    k = cb.FORM_TYPE.get(f)
                    if k and k not in [x[2] for x in kinds]:
                        kinds.append((cb.FORM_LABELS[f][:1].upper() + cb.FORM_LABELS[f][1:], "Основная форма MVP, остальное — позже", k))
                opts = [(kinds[0][0] + " (Recommended)", kinds[0][1], kinds[0][2])] + kinds[1:4]
                _follow(cfg, "product.type", "Осн. форма", "Форм несколько (%s). Какая основная для MVP?" % ", ".join(
                    cb.FORM_LABELS[f] for f in fp["forms"]), "choice", opts, "свой ответ «Форма»: несколько форм")
        else:
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
        rest = market_remainder(t)                  # FB-025: хвост ответа не теряется
        if rest:
            set_path(cfg, "strategy.markets_note", rest)
            cfg["assumptions"].append("Рынки: %s + уточнение «%s» — определить в исследовании (C4)" % (", ".join(langs[:6]) or "—", rest))
            cfg["idea"].setdefault("_rq_extra", []).append({"text": "Рынки и языки: уточнить «%s» (свой ответ c07)" % rest,
                                                            "kind": "research", "source": "c07"})
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
    if choice == "flat":
        return cwd / "concept" / slug
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


def _split_multi(opts, value):
    """Значение мультивыбора → список ответов. Строка с несколькими вариантами через запятую разбирается по известным
    label (у варианта «Нет, обычные данные» запятая внутри — простое split(",") его ломает); остаток — свой текст."""
    vals = value if isinstance(value, list) else [value]
    out = []
    labels = sorted({o[0] for o in opts} | {o[0].replace(" (Recommended)", "") for o in opts}, key=len, reverse=True)
    for v in vals:
        rest = str(v).strip()
        if not rest:
            continue
        if _match_label(opts, rest):
            out.append(rest)
            continue
        found = []
        for lab in labels:
            i = rest.find(lab)
            if i >= 0 and not any(lab in f for f in found):
                found.append(lab)
                rest = (rest[:i] + "," + rest[i + len(lab):])
        tail = [x.strip(" ,;") for x in re.split(r"[,;]", rest) if x.strip(" ,;")]
        if found:
            out += sorted(found, key=lambda lab: str(v).find(lab)) + tail
        else:
            out += [x.strip() for x in str(v).split(",") if x.strip()] if not tail else tail
    return out


def _fuzzy_label(opts, text):
    """Свой ответ → вариант, если он явно его называет («острая» → «Острая, ищут решение»); иначе None."""
    t = str(text or "").strip().lower().replace("ё", "е")
    if not t:
        return None
    hit = _match_label(opts, text)
    if hit:
        return hit
    for o in opts:
        lab = o[0].replace(" (Recommended)", "").lower().replace("ё", "е")
        if lab.startswith(t) or t.startswith(lab):
            return o
    words = [w for w in re.findall(r"[\w+–-]{3,}", t)]
    best = None
    for o in opts:
        lab = o[0].replace(" (Recommended)", "").lower().replace("ё", "е")
        score = sum(1 for w in words if w[:5] in lab)
        if score and (best is None or score > best[0]):
            best = (score, o)
    if best and best[0] >= max(1, len(words) // 2):
        return best[1]
    m = difflib.get_close_matches(t, [o[0].replace(" (Recommended)", "").lower() for o in opts], n=1, cutoff=0.6)
    if m:
        return next(o for o in opts if o[0].replace(" (Recommended)", "").lower() == m[0])
    return None


def _parse_corrections(text):
    """«Рынки: только RU; Форма: веб» → [(«Рынки», «только RU»), …] (поправки к карточкам подтверждения)."""
    out = []
    for part in re.split(r"[;\n]", str(text or "")):
        m = re.match(r"\s*([^:—]{2,24})\s*[:—-]\s*(.+)$", part)
        if m:
            out.append((m.group(1).strip(), m.group(2).strip()))
    return out


def _block_custom(cfg, q, text, notes):
    """Свой ответ на вопрос блока, карточки «Начало» или личного режима → поле run-config."""
    qid, t = q[0], str(text).strip()
    f = cfg["idea"].setdefault("facets", {})
    if qid == "pl01":
        f["platform_dependency"] = True
        f["platform_name"] = t[:80]
    elif qid in ("ow01", "ow02"):
        items = [x.strip() for x in re.split(r"[,;\n]|\s(?=~/|/Users/|https?://)", t) if x.strip()]
        key = "owner_repos" if qid == "ow01" else "owner_data_paths"
        f[key] = [cb.mask(x) for x in items]
        f["owner_repos_known" if qid == "ow01" else "owner_data"] = True
        docs = cfg["sources"].setdefault("owner_docs", [])
        for x in items:
            x = cb.mask(x)
            entry = {"url": x} if x.startswith("http") else {"path": x}
            entry.update({"kind": "repo" if qid == "ow01" else "data", "role": "ref", "status": "not_attempted",
                          "tool": "web-fetch" if x.startswith("http") else "read", "note": "ответ «%s»" % q[3], "source": qid})
            if not any(d.get("url", d.get("path")) == x for d in docs if isinstance(d, dict)):
                docs.append(entry)
    elif qid == "ui02":
        m = re.search(r"\d+", t)
        if m:
            set_path(cfg, "design.directions_count", max(1, min(7, int(m.group(0)))))
        else:
            notes.append("%s: свой ответ «%s» — учесть вручную" % (q[3], t))
    elif qid == "da01":
        f["data_sources_needed"] = [x.strip() for x in re.split(r"[,;\n]", t) if x.strip()]
    elif qid == "ai06":
        f["ai_hardware"] = t[:120]
    elif qid == "i03":
        set_path(cfg, "tools.agents.model_policy", "custom")
        set_path(cfg, "tools.agents.note", t[:200])
    elif qid == "i01":
        low = t.lower()
        aud = "personal_then_public" if cb.THEN_PUBLIC.search(low) else "personal" if cb.PERSONAL_WORDS.search(low) or "себя" in low \
            else "circle" if cb.CIRCLE_WORDS.search(low) or re.search(r"семь|друз|команд|коллег", low) else "public"
        set_path(cfg, "project.audience", aud)
        set_path(cfg, "project.audience_note", t[:200])
        if aud != "public":
            set_path(cfg, "project.goal", "personal")
    else:
        first = next((k for _l, _d, m in q[6] for k in m if k.startswith("idea.facets.")), None)
        if first:
            node = cfg
            parts = first.split(".")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1] + "_note"] = t[:200]
        cfg["assumptions"].append("%s: свой ответ «%s»" % (q[3], t[:160]))


def apply_concept_answers(cfg, answers, count=None):
    """Ответы карточек режима идеи (настройка, «Начало», вопросы банка и личного режима, блоки, подтверждение «Из
    запроса», таблицы быстрого режима, уточнения проверок). Ключ — header, текст вопроса или id; значение — label,
    список label (мультивыбор) или свой текст. Вопросы без ответа из заданных — допущения со значением по умолчанию.
    Контекст из cfg["idea"]: request, prefill_raw (предзаполнение), interview_mode, project.audience."""
    look = cb.lookup(CONCEPT_BANK)
    explicit = cfg.setdefault("_explicit", [])
    idea, notes = cfg["idea"], []
    answered, block_answers = {}, {}
    answers = dict(answers or {})
    rest = {}
    # 1) настройка и «Начало» — от них зависят аудитория и режим опроса
    for k, v in answers.items():
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
        hit = look.get(key)
        if hit and hit[1] == "intro":
            q = hit[0]
            val = v[0] if isinstance(v, list) and v else v
            o = _match_label(q[6], val)
            if o:
                _apply_mapping(cfg, o[2], explicit)
            elif str(val).strip():
                _block_custom(cfg, q, val, notes)
            block_answers[q[0]] = {"block": "intro", "header": q[3], "question": q[4], "answer": val, "custom": o is None}
            continue
        rest[key] = v
    audience = cb.audience_of(cfg["project"].get("audience"))
    mode = idea.get("interview_mode") or "standard"
    n = int(count or idea.get("questions_count") or CONCEPT_DEFAULT_QUESTIONS)
    n = max(CONCEPT_MIN_QUESTIONS, min(n, len(CONCEPT_BANK)))
    idea["questions_count"] = n
    bank = cb.adapted_bank(CONCEPT_BANK, audience)
    request = idea.get("request") or ""
    prefill_raw = idea.get("prefill_raw")
    aud_arg = audience if (audience != "public" or cfg["project"].get("audience")) else None
    plan = concept_questions_json(n, 4, aud_arg, prefill_raw, request, mode) \
        if (request or prefill_raw or mode != "standard" or audience != "public") else None
    pre = cb.merged_prefill(CONCEPT_BANK, request, prefill_raw, audience_known=True) if (request or prefill_raw) else {}
    confident = {k: v for k, v in pre.items() if v["confidence"] >= cb.CONFIDENT}
    deferred, card_defaults, decisions = [], [], {}
    check_rules = {}
    for it in idea.get("checks") or []:
        if it.get("header"):
            check_rules[it["header"]] = it["id"]
    # 2) остальные ответы
    for key, v in rest.items():
        if key in HANDOFF_HEADERS:                                   # раунд 6 «Передача в разработку» общий с обычным режимом
            for lab in (v if isinstance(v, list) else [v])[:1]:
                _m, mapping = _find_option(key, lab)
                if mapping:
                    for pk, pv in mapping.items():
                        set_path(cfg, pk, pv)
                else:
                    notes.append("%s: свой ответ «%s» — учесть вручную" % (key, lab))
            continue
        if key.startswith(cb.CONFIRM_HEADER) or key in cb.THEME_CONFIRM.values():
            deferred.append((key, v))
            continue
        if key in ("Осн. форма",):
            val = v[0] if isinstance(v, list) and v else v
            low = str(val).lower()
            t = next((cb.FORM_TYPE[f] for f, lab in cb.FORM_LABELS.items() if lab.split()[0] in low), None)
            if t:
                set_path(cfg, "product.type", t)
                explicit.append("product.type")
            continue
        if key == "Имя и папка":
            val = v[0] if isinstance(v, list) and v else v
            decisions["name"] = str(val).strip()
            continue
        if key == "Светофор":
            val = v[0] if isinstance(v, list) and v else v
            decisions["slicing"] = str(val).strip()
            continue
        if key in check_rules or key in cc.CHECK_HEADERS or key in CHECK_HEADER_IDS:
            rid = check_rules.get(key) or cc.CHECK_HEADERS.get(key) or CHECK_HEADER_IDS.get(key)
            val = v[0] if isinstance(v, list) and v else v
            decisions[rid] = str(val).strip()
            continue
        hit = look.get(key)
        if not hit:
            notes.append("Неизвестный вопрос «%s» — ответ сохранён в допущения" % key)
            cfg["assumptions"].append("%s: %s" % (key, v))
            continue
        q, src = hit
        qid, theme, _p, h, text, multi, opts = q
        if isinstance(v, str) and cb.CARD_DEFAULT_RE.search(v):
            card_defaults.append(qid)
            continue
        vals = _split_multi(opts, v) if multi else ([v[0]] if isinstance(v, list) and v else [v])
        vals = [x for x in vals if str(x).strip()]
        if not vals:
            continue
        if len(vals) == 1 and isinstance(vals[0], str) and cb.ONE_DEFAULT_RE.match(vals[0]):
            vals = [opts[0][0]]
        custom = False
        rec = {"theme": theme, "header": h, "question": text, "custom": False}
        if multi and qid in cb.EXCLUSIVE and len(vals) > 1:              # «Нет …» вместе с другими вариантами (SM 3.4)
            ex_lab = opts[cb.EXCLUSIVE[qid]][0]
            hits = [_match_label(opts, x) for x in vals]
            if any(hh is not None and hh[0] == ex_lab for hh in hits):
                vals = [x for x, hh in zip(vals, hits) if not (hh is not None and hh[0] == ex_lab)] or vals
                if qid == "c38":
                    rec["exclusive_conflict"] = True
                    rec["answer_raw"] = _split_multi(opts, v)
        for x in vals:
            o = _match_label(opts, x)
            if o:
                _apply_mapping(cfg, o[2], explicit)
            else:
                custom = True
                if src == "bank":
                    _custom_answer(cfg, qid, x, notes)
                else:
                    _block_custom(cfg, q, x, notes)
        rec.update({"answer": vals if multi else vals[0], "custom": custom})
        if rec.get("answer_raw"):
            rec["answer"] = rec.pop("answer_raw")
        if src in ("bank", "personal"):
            answered[qid] = rec
        else:
            rec["block"] = theme.split(":")[0]
            block_answers[qid] = rec
    # 3) подтверждение предзаполнения («Из запроса понял…») и таблицы быстрого режима
    ask_again = set()
    corrections = []
    confirm_ids = dict(zip([c["header"] for c in (plan or {}).get("confirm") or []], (plan or {}).get("confirm_ids") or []))
    for key, v in deferred:
        val = v[0] if isinstance(v, list) and v else v
        if key.startswith(cb.CONFIRM_HEADER):
            ids = confirm_ids.get(key, [])
            if str(val).startswith("Задать"):
                ask_again |= set(ids)
            elif not str(val).startswith("Да"):
                corrections += _parse_corrections(val)
            continue
        th = next(t for t, hh in cb.THEME_CONFIRM.items() if hh == key)
        ids = [q[0] for q in concept_select_bank(bank, n) if q[1] == th]
        if str(val).startswith("Задать"):
            continue
        for qid in ids:
            if qid in answered:
                continue
            q = look[qid][0]
            pv = pre.get(qid)
            lab = pv["answer"] if pv else q[6][0][0]
            o = _match_label(q[6], lab) if not isinstance(lab, list) else None
            if o:
                _apply_mapping(cfg, o[2], explicit)
            elif pv:
                _custom_answer(cfg, qid, lab, notes) if look[qid][1] == "bank" else _block_custom(cfg, q, lab, notes)
            answered[qid] = {"theme": q[1], "header": q[3], "question": q[4], "answer": lab if not isinstance(lab, list) else lab,
                             "custom": False, "confirmed_default": not bool(pv), "prefilled": bool(pv)}
        if not str(val).startswith("Верно"):
            corrections += _parse_corrections(val)
    for header, value in corrections:
        hit = look.get(header) or next((look[k] for k in look if k.lower() == header.lower()), None)
        if not hit:
            cfg["assumptions"].append("Поправка «%s: %s» — вопрос не найден, учесть вручную" % (header, value))
            continue
        q, src = hit
        o = _fuzzy_label(q[6], value)
        if o:
            _apply_mapping(cfg, o[2], explicit)
            val = o[0]
        else:
            _custom_answer(cfg, q[0], value, notes) if src == "bank" else _block_custom(cfg, q, value, notes)
            val = value
        rec = {"theme": q[1], "header": q[3], "question": q[4], "answer": val, "custom": o is None, "correction": True}
        (answered if src in ("bank", "personal") else block_answers)[q[0]] = rec
    # предзаполненные уверенные ответы, на которые нет ответа владельца
    confirmed = any(k.startswith(cb.CONFIRM_HEADER) for k, _v in deferred)
    for qid, pv in confident.items():
        if qid in answered or qid in block_answers or qid in ask_again or (qid == "i01" and not cfg.get("autopilot")):
            continue                                              # «Для кого» из текста — подсказка карточки «Начало»; в автопилоте — ответ
        q, src = look[qid]
        lab = pv["answer"]
        if q[5] and not isinstance(lab, list):
            lab = _split_multi(q[6], lab)
        labs = lab if isinstance(lab, list) else [lab]
        any_custom = False
        for x in labs:
            o = _match_label(q[6], x)
            if o:
                _apply_mapping(cfg, o[2], explicit)
            else:
                any_custom = True
                _custom_answer(cfg, qid, x, notes) if src == "bank" else _block_custom(cfg, q, x, notes)
        rec = {"theme": q[1], "header": q[3], "question": q[4], "answer": labs if q[5] else labs[0], "custom": any_custom,
               "prefilled": True, "confirmed": confirmed, "quote": pv.get("quote", ""), "source": pv.get("source")}
        (answered if src in ("bank", "personal") else block_answers)[qid] = rec
        if not confirmed:
            cfg["assumptions"].append("%s: «%s» — из текста запроса, не подтверждено владельцем" % (q[3], _answer_text(q, rec["answer"])))
    # «по умолчанию для всей карточки» (SM 3.6)
    if card_defaults:
        batches = (plan or concept_questions_json(n, 4))["batches"]
        for qid in card_defaults:
            sib = next(([i["id"] for i in b["ids"]] for b in batches if qid in [i["id"] for i in b["ids"]]), [qid])
            if look[qid][1] == "block":
                sib = [x[0] for x in cb.BLOCKS[look[qid][0][1].split(":")[0]][2]]
            for sid in sib:
                if sid in answered or sid in block_answers:
                    continue
                q, src = look[sid]
                _apply_mapping(cfg, q[6][0][2], explicit)
                rec = {"theme": q[1], "header": q[3], "question": q[4], "answer": [q[6][0][0]] if q[5] else q[6][0][0], "custom": False,
                       "card_default": True}
                (answered if src in ("bank", "personal") else block_answers)[sid] = rec
    if decisions:
        idea.setdefault("decisions", {}).update(decisions)
    asked = set(plan["live_ids"]) if plan and plan.get("live_ids") else {q[0] for q in concept_select_bank(bank, n)}
    if plan and plan.get("prefilled_ids"):
        asked |= set(plan["prefilled_ids"]) & set(answered)
    asked |= ask_again
    replaced = cb.replaced_ids(audience)
    # значения по умолчанию — для всех вопросов без ответа (заданные, но пропущенные, — в допущения поимённо)
    idea["unanswered"], idea["not_asked"] = [], []
    for q in sorted(bank, key=lambda x: x[2]):
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
    if replaced:
        idea["replaced"] = sorted(replaced)
    idea["answers"] = {k: answered[k] for k in sorted(answered)}
    if block_answers:
        idea["block_answers"] = {k: block_answers[k] for k in sorted(block_answers)}
        blocks = sorted({r.get("block") for r in block_answers.values() if r.get("block") and r.get("block") != "intro"})
        if blocks:
            idea["blocks_answered"] = blocks
        if any(r.get("block") == "admin" for r in block_answers.values()):
            idea.setdefault("facets", {}).setdefault("admin_needed", True)
    return notes


# заголовки карточек проверок (concept_checks) → id правила: ответы через concept-apply принимаются и до первого прогона проверок
CHECK_HEADER_IDS = {"Сообщество": "own_community_no_access", "Ёмкость MVP": "mvp_capacity", "Цель дохода": "revenue_vs_resources",
                    "Каналы B2B": "b2b_social", "Чувств. обл.": "sensitive_exclusive", "Деньги лично": "personal_money",
                    "Кто разраб.": "no_dev_skills", "ИИ и железо": "ai_local_browser", "Аналоги есть": "competitors_claimed_none",
                    "Доход/модель": "revenue_none_paid"}


NAME_OK = ("Подходит (Recommended)", "Подходит", "ok", "Придумать варианты позже", "later")
AUDIENCE_NAMES = {"public": "публичный продукт (аудитория, рынок, модель дохода)",
                  "personal": "только для меня — личный режим: без аудитории, маркетинга и монетизации",
                  "circle": "для меня и узкого круга — личный режим без маркетинга",
                  "personal_then_public": "сначала для себя, потом, возможно, публично — личный режим и раздел «Если захочется выпустить наружу»"}


def concept_request(cfg, request, request_questions=None):
    """Разбор исходного запроса (FB-001, FB-002): вопросы RQ, ссылки и материалы владельца → run-config. Повтор безопасен."""
    idea, src = cfg["idea"], cfg["sources"]
    notes = []
    if request:
        idea["request"] = cb.mask(request)[:4000]
    rq = cb.normalize_request_questions(request_questions) if request_questions else cb.request_questions(request, idea.get("pitch"))
    for x in idea.pop("_rq_extra", []) or []:
        if not any(x["text"] == r["text"] for r in rq):
            rq.append({"id": "RQ%02d" % (len(rq) + 1), "text": cb.mask(x["text"]), "kind": x.get("kind", "research"), "source": x.get("source", "answers")})
    if rq or "request_questions" not in idea:
        idea["request_questions"] = rq
    urls = cb.classify_urls(request) if request else []
    docs = src.setdefault("owner_docs", [])
    ext = src.setdefault("external", {"site": "", "stores": [], "apk": [], "tracker": "", "other_urls": []})
    comps = src.setdefault("competitor_list", [])
    facets = idea.setdefault("facets", {})
    for u in urls:
        key = u.get("url") or u.get("path")
        if not any(isinstance(d, dict) and (d.get("url") or d.get("path")) == key for d in docs):
            docs.append({k: v for k, v in u.items() if k != "domain"})
        if u["kind"] == "platform_site":
            ext["site"] = ext.get("site") or u["url"]
            pu = facets.setdefault("platform_urls", [])
            if u["url"] not in pu:
                pu.append(u["url"])
        elif u["kind"] == "competitor":
            if not any(str(c).lower().rstrip("/") in (u["domain"], u["url"].lower().rstrip("/")) for c in comps):
                comps.append(u["domain"])
    if urls:
        notes.append("Материалы владельца из запроса: %d (%s) — шаг C0.6: прочитать каждую и записать статус в sources.owner_docs[] и build/owner-materials.md"
                     % (len(urls), ", ".join("%s: %s" % (u["kind"], u.get("domain") or u.get("path")) for u in urls)))
    return notes


def concept_capacity(cfg, explicit=()):
    """project.capacity (одна величина «часов в дне» — day_hours; project.hours_in_day не вводится) из ответа «Время» (c32);
    заданное через --set project.capacity.* не перезаписывается, недостающие поля дополняются."""
    prj, f = cfg["project"], (cfg["idea"].get("facets") or {})
    team = int(prj.get("team_size") or 1)
    hw = float(f.get("hours_week") or 8)
    asked = "c32" in (cfg["idea"].get("answers") or {})
    cur = prj.get("capacity") if isinstance(prj.get("capacity"), dict) else {}
    computed = {"hours_per_week": hw, "dev_share": 0.7, "day_hours": 8,      # часы на человека; команду умножает capacity.py
                "source": ("ответ c32 (часов в неделю)" if asked else "значение по умолчанию c32 (5–10 ч/нед) [допущение]") +
                          (" на человека × команда %d [допущение: у каждого столько же]" % team if team > 1 else "")}
    if any(k == "project.capacity" or k.startswith("project.capacity.") for k in explicit):
        prj["capacity"] = dict(computed, **cur)
        prj["capacity"]["source"] = cur.get("source") or "задано владельцем (--set project.capacity…)"
    else:
        prj["capacity"] = computed


def concept_registry(cfg):
    """registry {passes, capacity_cap, category_minimums} для WP-C: один проход генерации на quick и deep (FB-005), два — на
    standard и exhaustive; потолок ёмкости для now — если MVP не помещается в ёмкость, включена нарезка или личный режим;
    минимумы категорий — по приоритету в личном режиме и при потолке. Заданное через --set не трогается."""
    reg = cfg.setdefault("registry", {})
    auto = reg.setdefault("auto_keys", [])
    def put(k, v):
        if k not in reg or k in auto:
            reg[k] = v
            if k not in auto:
                auto.append(k)
    put("passes", 1 if cfg["strategy"].get("depth") in ("quick", "deep") else 2)
    try:
        tight = cc.mvp_capacity(cfg)["fits"] == "no"
    except Exception:                                       # noqa: BLE001
        tight = False
    personal = cb.audience_of(cfg["project"].get("audience")) in cb.PERSONAL_AUDIENCES
    put("capacity_cap", bool(tight or (cfg.get("slicing") or {}).get("enabled") or personal))
    put("category_minimums", "priority" if (personal or reg.get("capacity_cap")) else "count")
    return reg


def _concept_personal(cfg):
    prj, sc, st = cfg["project"], cfg["scope"], cfg["strategy"]
    aud = cb.audience_of(prj.get("audience"))
    prj["audience"] = aud
    if aud == "public":
        prj.setdefault("release_outward", True)
        return []
    explicit = set(cfg.get("_explicit") or [])
    off = []
    for k in cb.PERSONAL_SCOPE_OFF:
        if "scope." + k not in explicit and sc.get(k):
            sc[k] = False
            off.append(k)
    if "strategy.monetization" not in explicit:
        st["monetization"] = "none"
        st["paid_tier"] = "no"
    prj["goal"] = "personal"
    if aud == "personal_then_public":
        prj["release_outward"] = True
    cfg["assumptions"].append("Личный режим (%s): поиск запросов и календарь событий выключены (%s); сообщества — источник идей и "
                              "библиотек, аналоги — «готовое вместо своего» (build vs buy); модель — стоимость владения" % (
                                  aud, ", ".join(off) or "уже выключены"))
    return []


def concept_finish(cfg, cwd, request="", name=None, slug=None, topic_en=None, keywords=None, request_questions=None,
                   home=None):
    """Имя и slug, цель, разбор запроса (RQ, ссылки владельца), ключевые слова и перевод темы, личный режим, папка,
    проверка запроса «в/вне репозитория», finalize, ёмкость, git и правила владельца, проверки до «Начинаю?»."""
    idea = cfg["idea"]
    dec = idea.get("decisions") or {}
    given = name or idea.pop("name_given", None)
    idea.pop("name_given", None)
    if dec.get("name") and dec["name"] not in NAME_OK and not name:
        given = dec["name"]
    notes = []
    facets = idea.get("facets") or {}
    if facets.get("naming") == "given" and not given:
        notes.append("Название: выбрано «Есть, впишу», но текста нет — рабочее имя по идее; уточнить у владельца")
    pitch = idea.get("pitch_v2") or idea["pitch"]
    if topic_en:
        idea["topic_en"] = str(topic_en).strip()
        idea["topic_en_for"] = int(idea.get("version") or 1)
    nm, sl = idea_name_slug(pitch, given, idea.get("topic_en"))
    if slug:
        sl = slugify(slug)
    idea["name"], idea["slug"] = nm, sl
    idea["name_source"] = "given" if given else "auto"
    cfg["product"]["name"] = nm
    cfg["strategy"]["goal"] = "концепция нового продукта: %s" % (idea_first_phrase(pitch) or nm)
    if not idea["pitch"]:
        notes.append("Идея не передана (--idea) — досье будет пустым; повторить concept-apply с --idea \"<текст>\"")
    notes += concept_request(cfg, request, request_questions)
    if keywords:
        idea["keywords"] = [k.strip() for k in (keywords if isinstance(keywords, list) else re.split(r"[,;]", str(keywords))) if k.strip()][:12]
        idea["keywords_source"] = "owner"
    elif idea.get("keywords_source") != "owner":
        idea["keywords"] = idea_keywords(pitch)
        idea["keywords_source"] = "auto"
    if facets.get("sensitive"):
        cfg["scope"]["legal"] = True
    notes += _concept_personal(cfg)
    explicit_all = set(cfg.get("_explicit") or [])
    concept_set_output(cfg, cwd)
    notes += check_concept_folder(cfg, cwd, request)
    finalize(cfg)
    band = facets.get("price_band")
    if cfg["project"].get("price_hint") is None and band in ("low", "mid", "high"):
        rub = cfg["project"]["currency"] == "RUB"
        cfg["project"]["price_hint"] = {"low": 299 if rub else 5, "mid": 990 if rub else 15, "high": 4990 if rub else 49}[band]
        cfg["assumptions"].append("Ориентир цены %s %s/мес — по ответу «Цена» (диапазон %s)" % (cfg["project"]["price_hint"], cfg["project"]["currency"], band))
    concept_capacity(cfg, explicit_all)
    concept_registry(cfg)
    ag = cfg["tools"].setdefault("agents", {})
    ag.setdefault("model_policy", "triage")
    ag.setdefault("effort_policy", "none")
    gs = cc.git_state(cfg["output"]["dir"])
    cfg["git"] = {"state": gs["state"], "has_origin": gs["has_origin"], "branch": gs.get("branch"), "default_branch": gs.get("default_branch"),
                  "visibility": cfg["project"].get("repo_visibility") or "unknown"}
    rules = cc.owner_rules(gs.get("top") or cwd, home)
    if rules.get("sources"):
        cfg["owner_rules"] = rules
    notes += concept_run_checks(cfg)
    if idea["name_source"] == "auto" and "name" not in dec:
        _follow(cfg, "idea.decisions.name", "Имя и папка",
                "Рабочее имя «%s», папка и ветка — %s. Подходит? Своё имя — в «Other»." % (nm, sl), "choice",
                [("Подходит (Recommended)", "Имя временное: варианты названия — в концепции", "ok"),
                 ("Придумать варианты позже", "Оставить рабочее имя до выбора названия", "later")],
                "имя выведено из текста идеи (FB-022); своё — concept-apply --name/--slug")
    return notes


def concept_run_checks(cfg):
    """Проверки до «Начинаю?»: решения (idea.decisions) применяются, нерешённые находки → follow_up (FB-053, FB-054)."""
    idea = cfg["idea"]
    before = cc.run_checks(cfg)
    idea["checks"] = [x for x in before if x.get("options")]
    applied = cc.apply_decisions(cfg, set_path) if idea.get("decisions") else []
    after = cc.run_checks(cfg) if applied else before
    dec = idea.get("decisions") or {}
    keep = {x["id"]: x for x in before if x.get("options") and x["id"] in dec}
    for x in after:
        keep.setdefault(x["id"], x)
    idea["checks"] = list(keep.values())
    for x in after:
        if x.get("options") and x["id"] not in dec:
            _follow(cfg, "idea.decisions.%s" % x["id"], x["header"], x["question"], "choice",
                    [(o["label"], o["description"], o["key"]) for o in x["options"]], x["message"])
    return ["Решение до старта: %s" % a for a in applied]


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
    if cfg["idea"].get("request") or cfg["idea"].get("prefill_raw"):
        apply_concept_answers(cfg, {}, CONCEPT_MIN_QUESTIONS)     # автопилот с текстом запроса: уверенные ответы из текста
        cfg["idea"]["unanswered"] = []                            # (SM 3.1) вместо значений по умолчанию
    sel = concept_select(CONCEPT_MIN_QUESTIONS)
    for q in sel:
        qid, theme, _p, h, text, multi, opts = q
        if qid in cfg["idea"]["answers"]:
            continue
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


def _concept_extra_lines(cfg):
    idea, prj, pr = cfg.get("idea") or {}, cfg["project"], cfg["product"]
    lines = []
    aud = cb.audience_of(prj.get("audience"))
    lines.append("Для кого: %s" % AUDIENCE_NAMES[aud] + ("; выпуск наружу допускается" if aud in ("personal", "circle") and prj.get("release_outward") else ""))
    forms = pr.get("forms") or []
    if forms or pr.get("future_forms"):
        lines.append("Форма: %s (формы: %s%s)" % (cb.FORM_LABELS.get(forms[0], pr["type"]) if forms else pr["type"], ", ".join(forms) or "—",
                                                 "; позже: %s" % ", ".join(pr["future_forms"]) if pr.get("future_forms") else ""))
    if cfg["strategy"].get("markets_note"):
        lines.append("Рынки: %s (+ уточнение: «%s» — в исследовании)" % (", ".join(cfg["strategy"]["markets"]), cfg["strategy"]["markets_note"]))
    try:
        mc = cc.mvp_capacity(cfg)
        c6 = cc.cap_mod.capacity(cfg, cfg["strategy"].get("horizon_months") or 6)
        lines.append("Ёмкость: %s" % c6["line"])
        lines.append("MVP: %s" % mc["line"])
    except Exception:                                             # noqa: BLE001 — сводка не должна падать
        pass
    try:
        import model as _model                                    # WP-B: профиль модели по форме, оплате и аудитории
        prof, why = _model.select_profile(cfg)
        lines.append("Модель: %s (%s)" % (prof, why))
    except Exception:                                             # noqa: BLE001 — нет model.py или старый — без строки
        pass
    kw = idea.get("keywords") or []
    if kw:
        en = idea.get("topic_en")
        lines.append("Ключевые слова: %s (%s); тема EN: %s" % (", ".join(kw), "владелец" if idea.get("keywords_source") == "owner" else "автоматически — поправить: --keywords",
                                                              en or "нет — передайте --topic-en \"<перевод темы>\", иначе в плане поиска останутся <EN: …>"))
    lines.append("Имя: «%s» (%s) · slug/папка/ветка: %s" % (pr.get("name"), "из ответа «Название»" if idea.get("name_source") == "given" else
                                                            "рабочее, из текста идеи — своё: --name/--slug", idea.get("slug")))
    rq = idea.get("request_questions") or []
    if rq:
        lines.append("Вопросы запроса (RQ, %d — проследить ответ на каждый): %s%s" % (
            len(rq), "; ".join("%s [%s] %s" % (r["id"], r["kind"], r["text"][:70]) for r in rq[:6]), " …" if len(rq) > 6 else ""))
    docs = [d for d in (cfg["sources"].get("owner_docs") or []) if isinstance(d, dict)]
    if docs:
        pend = sum(1 for d in docs if d.get("status") == "not_attempted")
        lines.append("Материалы владельца (%d): %s; не прочитано %d — шаг C0.6 (прочитать каждую, статус read|blocked)" % (
            len(docs), "; ".join("%s %s (роль %s)" % (d.get("kind"), d.get("url") or d.get("path"), d.get("role")) for d in docs[:5]), pend))
    ag = cfg["tools"].get("agents") or {}
    if ag:
        lines.append("Агенты: модели — %s; effort — %s" % ({"triage": "триаж TypeSafe (если установлен)", "default": "по умолчанию скилла",
                                                         "custom": "свои правила: %s" % ag.get("note", "—")}.get(ag.get("model_policy"), ag.get("model_policy")),
                                                        "задаётся явно" if ag.get("effort_policy") == "explicit" else "не задаётся"))
    g = cfg.get("git") or {}
    if g:
        lines += cc.git_plan(dict(g, top=None), cfg["output"].get("git_branch") or "docs/concept-%s" % idea.get("slug"))
    bs = cfg["output"].get("branch_status")
    if bs:
        lines.append(("Ветка: %s" if bs in ("created", "current", "switched") else "ВНИМАНИЕ, ветка: %s") % cfg["output"].get("branch_note"))
    rules = cfg.get("owner_rules") or {}
    if rules.get("lines"):
        lines.append("Правила владельца (%s): %s" % (", ".join(rules.get("sources") or []), "; ".join(rules["lines"])))
    reg = cfg.get("registry") or {}
    if reg:
        lines.append("Реестр: проходов %s, потолок ёмкости для now — %s" % (reg.get("passes"), _yn(reg.get("capacity_cap"))))
    if cfg.get("slicing", {}).get("enabled"):
        lines.append("Нарезка на очереди: %s" % ", ".join(q["name"] for q in cfg["slicing"].get("queues") or []))
    blocks = idea.get("blocks_answered") or []
    if blocks:
        lines.append("Блоки опроса: %s" % ", ".join(cb.BLOCKS[b][0] for b in blocks if b in cb.BLOCKS))
    checks = [x for x in idea.get("checks") or [] if x.get("severity") != "info" or x.get("message")]
    if checks:
        lines.append("Проверка ответов до «Начинаю?» (%d): %s" % (len(checks), " | ".join(
            "[%s%s] %s" % (x.get("header") or x["id"], ", решено" if x.get("resolved") or x["id"] in (idea.get("decisions") or {}) else "", x["message"])
            for x in checks)))
    return lines


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
    lines += _concept_extra_lines(cfg)
    if idea.get("unanswered"):
        lines.append("Не отвечено (допущения): %s" % ", ".join(idea["unanswered"]))
    if cfg["author"].get("copyright"):
        lines.append("Авторство: %s" % cfg["author"]["copyright"])
    if cfg["assumptions"]:
        lines.append("Допущения: " + "; ".join(cfg["assumptions"]))
    fu = cfg.get("follow_up") or []
    if fu:
        lines.append("Уточнить ДО «Начинаю?» (%d): %s" % (len(fu), " | ".join("[%s] %s" % (x.get("header"), x.get("question")) for x in fu)))
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
    cq.add_argument("--audience", choices=list(cb.AUDIENCE), help="ответ «Для кого» карточки «Начало» (личный режим — свой банк)")
    cq.add_argument("--mode", choices=["standard", "fast", "deep"], help="ответ «Опрос» карточки «Начало»")
    cq.add_argument("--request", default="", help="исходный запрос: предзаполнение ответов из текста (FB-055, SM 3.1)")
    cq.add_argument("--prefill", help="предзаполнение оркестратора: JSON {id|header: ответ | {answer, confidence, quote}}, @файл или -")
    cq.add_argument("--json", action="store_true")
    ci = sub.add_parser("concept-intro", help="режим идеи: карточка «Начало» (для кого, режим опроса, модели и effort)")
    ci.add_argument("--request", default="")
    ci.add_argument("--json", action="store_true")
    cbl = sub.add_parser("concept-blocks", help="режим идеи: условные блоки вопросов по ответам")
    cbl.add_argument("--answers", required=True, help="ответы карточек (JSON, @файл или -)")
    cbl.add_argument("--request", default="")
    cbl.add_argument("--prefill")
    cbl.add_argument("--mode", choices=["standard", "fast", "deep"])
    cbl.add_argument("--audience", choices=list(cb.AUDIENCE))
    cbl.add_argument("--count", type=int)
    cbl.add_argument("--json", action="store_true")
    for name in ("concept-check", "concept-verdict"):
        p = sub.add_parser(name)
        p.add_argument("out")
        p.add_argument("--json", action="store_true")
    for name in ("concept-apply", "concept-defaults"):
        p = sub.add_parser(name)
        p.add_argument("--repo", default=".", help="текущая папка пользователя (от неё считается папка результата)")
        p.add_argument("--idea", default="", help="идея дословно")
        p.add_argument("--out-dir")
        p.add_argument("--set", action="append", default=[])
        p.add_argument("--request", default="", help="исходный запрос: слова «в/вне репозитория», вопросы RQ, ссылки владельца, предзаполнение")
        p.add_argument("--request-questions", help="вопросы запроса от оркестратора: JSON-список строк или {text, kind} (FB-001)")
        p.add_argument("--topic-en", help="перевод темы идеи на английский — подставляется вместо <EN: …> в плане поиска (FB-023)")
        p.add_argument("--keywords", help="подтверждённые ключевые слова через запятую (FB-023)")
        p.add_argument("--name", help="имя продукта (FB-022); без него — из ответа «Название» или рабочее из идеи")
        p.add_argument("--slug", help="slug папки и ветки (латиница)")
        p.add_argument("--branch", choices=["auto", "none"], default="auto",
                       help="auto — внутри git создать и включить ветку прогона ДО первой записи (FB-034); none — git не трогать")
        p.add_argument("--branch-name", help="имя ветки вместо docs/concept-<slug>")
        p.add_argument("--dry-run", action="store_true", help="только сводка и follow_up: ничего не писать, git не трогать")
        p.add_argument("--json", action="store_true", help="сводка, заметки, follow_up одним JSON")
        if name == "concept-apply":
            p.add_argument("--from-askuser", required=True, help="ответы карточек (JSON-строка, @файл или - для stdin)")
            p.add_argument("--count", type=int, help="сколько вопросов задавали (иначе — ответ карточки «Вопросов», по умолчанию 25)")
            p.add_argument("--prefill", help="предзаполнение оркестратора (тот же JSON, что у concept-questions)")
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
    if a.cmd == "concept-intro":
        d = concept_intro_json(a.request)
        if a.json:
            print(json.dumps(d, ensure_ascii=False, indent=2))
        else:
            print(d["title"] + ":")
            for i, q in enumerate(d["questions"], 1):
                print("%d. [%s] %s" % (i, q["header"], q["question"]))
                for o in q["options"]:
                    print("   - %s — %s" % (o["label"], o["description"]))
            print("   " + d["note"])
        return 0
    if a.cmd == "concept-questions":
        try:
            pre = _read_answers_arg(a.prefill) if a.prefill else None
            d = concept_questions_json(a.count, a.batch, a.audience, pre, a.request, a.mode)
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
        for cq_ in d.get("confirm") or []:
            print("\nПодтвердить [%s]: %s" % (cq_["header"], cq_["question"]))
        for b in d["batches"]:
            print("\nПачка %d — %s" % (b["batch"], b["title"]))
            for q, meta in zip(b["questions"], b["ids"]):
                print("  %s [%s] %s" % (meta["id"], q["header"], q["question"]))
                for o in q["options"]:
                    print("     - %s — %s" % (o["label"], o["description"]))
        if d.get("next"):
            print("\n" + d["next"])
        return 0
    if a.cmd == "concept-blocks":
        try:
            ans = _read_answers_arg(a.answers)
            pre = _read_answers_arg(a.prefill) if a.prefill else None
        except (ValueError, OSError) as e:
            print("ошибка: --answers/--prefill не читается как JSON (%s)" % e, file=sys.stderr)
            return 2
        d = concept_blocks_json(ans, a.request, pre, a.mode, a.count, 4, a.audience)
        if a.json:
            print(json.dumps(d, ensure_ascii=False, indent=2))
            return 0
        print("Условные блоки: %d вопросов в %d пачках" % (d["count"], len(d["batches"])))
        for bl in d["blocks"]:
            print("  %s — %s (%s): %s" % (bl["key"], bl["title"], bl["why"], ", ".join(bl["ids"])))
        for b in d["batches"]:
            print("\nПачка %d — %s" % (b["batch"], b["title"]))
            for q, meta in zip(b["questions"], b["ids"]):
                print("  %s [%s] %s" % (meta["id"], q["header"], q["question"]))
        return 0
    if a.cmd in ("concept-check", "concept-verdict"):
        cfgp = Path(a.out) / "build" / "run-config.json"
        try:
            cfg = json.loads(cfgp.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print("ошибка: нет или не читается %s (%s)" % (cfgp, e), file=sys.stderr)
            return 2
        if cfg.get("mode") != "concept":
            print("ошибка: run-config не в режиме идеи (mode: concept)", file=sys.stderr)
            return 2
        card = None
        if a.cmd == "concept-check":
            notes = concept_run_checks(cfg)
        else:
            notes = []
            doc = cc.load_verdict(a.out)
            card = cc.traffic_card(doc)
            if card:
                _follow(cfg, "slicing.decision", card["header"], card["question"], "choice", card["options"],
                        "светофор %s (data/typesafe-concept.json)" % card["verdict"])
        cfgp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        fu = cfg.get("follow_up") or []
        if a.json:
            print(json.dumps({"checks": (cfg.get("idea") or {}).get("checks") or [], "follow_up": fu, "notes": notes,
                              "verdict_card": ({"header": card["header"], "question": card["question"], "multiSelect": False,
                                                "options": [{"label": l, "description": d} for l, d, _k in card["options"]]} if card else None)},
                             ensure_ascii=False, indent=2))
            return 0
        if a.cmd == "concept-verdict" and not card:
            print("Светофор зелёный или data/typesafe-concept.json нет — карточка «что дальше» не нужна")
        for x in fu:
            print("Уточнить: [%s] %s → intake.py update %s --from-askuser '{\"%s\": \"<вариант>\"}'" % (
                x.get("header"), x.get("question"), a.out, x.get("header")))
        return 0
    if a.cmd in ("concept-apply", "concept-defaults"):
        cfg = concept_base_config(a.repo, a.idea, a.out_dir)
        if a.out_dir:
            cfg.setdefault("_explicit", []).append("output.dir")
        if a.request:
            cfg["idea"]["request"] = cb.mask(a.request)[:4000]
        notes = []
        rq = None
        try:
            if getattr(a, "prefill", None):
                cfg["idea"]["prefill_raw"] = _read_answers_arg(a.prefill)
            if a.request_questions:
                rq = _read_answers_arg(a.request_questions) if a.request_questions.strip()[:1] in "[{@-" else \
                    [x.strip() for x in a.request_questions.split(";") if x.strip()]
        except (ValueError, OSError) as e:
            print("ошибка: --prefill/--request-questions не читается как JSON (%s)" % e, file=sys.stderr)
            return 2
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
        notes += concept_finish(cfg, a.repo, a.request, name=a.name, slug=a.slug, topic_en=a.topic_en, keywords=a.keywords,
                                request_questions=rq)
        if a.branch_name and cfg["output"]["inside_repo"]:
            cfg["output"]["git_branch"] = a.branch_name
        if cfg["output"]["inside_repo"] and not a.dry_run:
            st, msg = cc.ensure_branch(cfg["repo"]["path"], cfg["output"]["git_branch"], a.branch)
            cfg["output"]["branch_status"], cfg["output"]["branch_note"] = st, msg
            if st in ("created", "switched", "current"):
                cfg.setdefault("git", {})["branch"] = cfg["output"]["git_branch"]
        elif cfg["output"]["inside_repo"]:
            cfg["output"]["branch_status"], cfg["output"]["branch_note"] = "planned", "ветка %s будет создана при записи (без --dry-run)" % cfg["output"]["git_branch"]
        path = None if a.dry_run else write_config(cfg)
        if a.json:
            print(json.dumps({"out": cfg["output"]["dir"], "run_config": str(path) if path else None, "dry_run": bool(a.dry_run),
                              "summary": show(cfg), "notes": notes, "follow_up": cfg.get("follow_up") or [],
                              "checks": (cfg.get("idea") or {}).get("checks") or [],
                              "request_questions": (cfg.get("idea") or {}).get("request_questions") or []}, ensure_ascii=False, indent=2))
            return 0
        print(show(cfg))
        for n in notes:
            print("Заметка: " + n)
        for x in cfg.get("follow_up") or []:
            print("Уточнить: [%s] %s → intake.py update <OUT> --from-askuser '{\"%s\": \"<вариант>\"}'" % (x.get("header"), x.get("question"), x.get("header")))
        if a.dry_run:
            print("\n(--dry-run: ничего не записано, git не тронут; после уточнений — тот же concept-apply без --dry-run, ответы "
                  "follow_up — в --from-askuser, имя — --name/--slug)")
            print("OUT_PLANNED=%s" % cfg["output"]["dir"])
            return 0
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
