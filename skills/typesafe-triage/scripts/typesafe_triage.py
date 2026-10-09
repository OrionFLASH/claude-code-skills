# -*- coding: utf-8 -*-
"""Универсальный триаж задачи через TypeSafe (Jev) + локальные эвристики: какой уровень модели Claude нужен.
Глобальный инструмент Claude Code, не часть чьего-либо проекта.

Подходит для ЛЮБЫХ задач: код, документы, письма, анализ, данные, исследование, планирование, ревью, ops.
Пропускаются только короткие реплики/подтверждения, команды `/…` и служебные сообщения среды.

Как определяется уровень (haiku < sonnet < opus < fable):
  1. TypeSafe отвечает одним запросом на узкие вопросы (шкалы Score, флаги Noul, тип задачи Choice): сложность, глубина
     рассуждения, неясность, цена ошибки, объём контекста; только чтение? механика? нужна диагностика? ошибка может пройти
     незаметно? необратимо? нужна новая разработка/творчество? это просто реплика?
  2. Локальные эвристики (triage_heuristics.py) считают по тексту: длину, пункты, файлы, шаги, код/логи, слова про
     продакшн/деньги/безопасность/необратимость, «почему/спроектируй» против «переименуй/покажи».
  3. Код (не модель) детерминированно объединяет: нагрузка = взвешенная сумма осей TypeSafe; эвристика только ПОДНИМАЕТ её
     (доля HEUR_RAISE разрыва) и может запретить haiku. Пороги — константы ниже.
  4. Нет ответа TypeSafe (нет ключа, сеть, пауза защиты, ошибка) → уровень по одной эвристике: только sonnet или opus,
     пометка «уверенность низкая». Никогда не «рекомендации нет».

Правила уровней (не ослаблять):
  * haiku и fable НИКОГДА не запускаются автоматически (CONFIRM_TIERS): основная модель сначала спрашивает пользователя
    (AskUserQuestion), без явного «да» работает на ближайшем безопасном: haiku → sonnet, fable → opus.
  * fable — только при очень высокой нагрузке (≥ LOAD_FABLE), высокой уверенности (≥ CONF_FABLE) и признаке критичности
    (цена ошибки на верхнем уровне / необратимость / предельная сложность), подтверждённом текстом.
  * haiku — только уверенно простое чтение/механика с низким риском, без признаков риска и объёма в тексте.
  * Вверх — легко, вниз — только при уверенных ответах; низкая уверенность = шаг вверх (не выше opus).
  * Основную модель сессии переключить нельзя (механизма нет): «переключение» = делегирование субагенту с model=.
  * Защита от потери доступа и ухода баланса в минус — typesafe_guard.py (паузы, потолок расходов, предупреждения).
  * В TypeSafe уходит только дайджест текста (до HARD_CHARS знаков), секреты маскируются; см. make_digest и --digest.
  * Выключатели: TYPESAFE_TRIAGE=off или файл .typesafe-triage-off в каталоге проекта (или выше).

Вторая ось (2.1) — reasoning effort low < medium < high < xhigh < max, независимо от модели (triage_effort.py): те же
ответы TypeSafe + узкие вопросы effort в том же запросе, сигналы текста, окружение, история сессии, правила
согласованности. low и max — только с подтверждения (CONFIRM_EFFORTS), без него low → medium, max → xhigh. Явные
указания пользователя в тексте («на opus», «effort max», «ultrathink», «тщательно», «кратко») — согласие и приоритет.
Повторный вызов хука на тот же запрос (session_id + хеш) молчит, только если первый уже выдал заметку (метка «готово»);
первый упал или оборван — заметку даёт второй (2.2.0). Хук не молчит без причины: «TypeSafe-триаж пропущен: <причина>».
2.2.0: короткие продолжения наследуют оценку сессии и получают строку «активная задача» из TASKS.md; тип задачи qa;
признаки общего интерактивного состояния (профиль браузера/CDP, активный прогон) — «делегируй только независимые части».
2.3.0: заметка начинается строкой «ДЕЙСТВИЕ: сам | Agent(model=…, effort=…) | спросить — причина (≤ 15 слов). Уверенность: …»
(triage_action: явная просьба пользователя, общее устройство, долгое ожидание, накопленный контекст, параллельность, модель
сессии — triage_session, локально из стенограммы); короткое продолжение с прежним решением — без заметки (журнал: quiet);
--check проверяет регистрацию хука и имя скилла для Skill (triage_install); --batch (triage_batch); журнал решений и
фактов в корне проекта и --fact (triage_projectlog, опция).
2.5.0: маскировка секретов и персональных данных (triage_secrets): пароли RU/EN, seed-фразы, ключи, токены, карты, e-mail; critical не отправляется; TYPESAFE_TRIAGE_SECRETS=block|strict|mask, --scan.
2.4.2: принудительный запуск триажа из запроса — /typesafe-triage <задача>, метка «triage:» / «!триаж opus/high», фраза «сделай триаж» (снимает пропуски хука; выбор модели не меняет).
2.4.1: запрос со служебными тегами среды (<system-reminder>, <ide_selection>) в начале больше не пропускается как служебный; «Don't use opus» — не «без субагента».
2.4.0: автозапись факта после субагента хуком плагина PostToolUse/SubagentStop (triage_autofact, опция, выкл.);
«чем занята сессия» — счётчики инструментов, фактов, реплик и токенов из служебных полей стенограммы (triage_session.work).

Запуск (только стандартная библиотека; ключ — переменная окружения TYPESAFE_API_KEY):
    python3 typesafe_triage.py "текст задачи"        # JSON с метриками, сигналами и рекомендацией
    python3 typesafe_triage.py --hook                # режим хука UserPromptSubmit (stdin = JSON хука)
    python3 typesafe_triage.py --where               # фактический путь скрипта (1-я строка), установка, хуки и их проблемы
    python3 typesafe_triage.py --digest "текст"       # показать, что именно уйдёт в TypeSafe (или текст из stdin)
    python3 typesafe_triage.py --signals "текст"      # показать локальные сигналы эвристики (без сети)
    python3 typesafe_triage.py --status               # пауза, расходы за месяц, потолок
    python3 typesafe_triage.py --resume               # снять паузу после пополнения баланса / исправления ключа
    python3 typesafe_triage.py --pause "причина"      # отключить TypeSafe вручную;  --set-budget USD  месячный потолок расходов
    python3 typesafe_triage.py --check                # диагностика: ключ, сеть, сертификаты; хук зарегистрирован? имя для Skill;
                                                     # команды починки (код 0 — всё в порядке, 1 — нет ответа TypeSafe, 3 — хук)
    python3 typesafe_triage.py --set-agent-effort yes|no|auto   # есть ли у инструмента Agent параметр effort
    python3 typesafe_triage.py --batch tasks.json [--json] [--prompts]   # пакет подзадач: таблица, порядок по paths,
                                                     # одно AskUserQuestion, готовые Agent(...) и промпты исполнителей
    python3 typesafe_triage.py --fact <id> --model M --effort E --tokens N [--minutes N] --outcome ok|review|rework|escalated|fail
                                                     # факт после подзадачи — в triage-log.jsonl проекта (калибровка)
    python3 typesafe_triage.py "текст" --project-log[=ПУТЬ]   # решение — ещё и в журнал проекта (или TYPESAFE_TRIAGE_PROJECT_LOG=on)
    python3 typesafe_triage.py --selftest            # эталонные задачи (triage_cases.json) через TypeSafe; нужна сеть
    python3 typesafe_triage.py --selftest --heuristic   # те же задачи только по эвристике (офлайн)
    python3 typesafe_triage.py --calibrate [--heuristic] [--split train|holdout|all] [--cache F] [--facts F]
                                                     # распределение effort/моделей, «ниже/выше ожидаемого», журнал;
                                                     # 2.3: факты из triage-log.jsonl проекта (на код возврата не влияют)
    python3 typesafe_triage.py --run "текст задачи"  # триаж + запуск отдельного агента `claude -p` на нужной модели
        --readonly          агент только читает и планирует (--permission-mode plan), файлы не правит
        --edit              агент может править файлы в текущем каталоге (--permission-mode acceptEdits); без --edit и --readonly
                            в режиме -p агент не получает права на запись и остановится с просьбой о разрешении (проверено)
        --allow "Bash(git status)"   доп. разрешённый инструмент (--allowedTools); можно несколько раз, например для запуска тестов
        --tier haiku|sonnet|opus|fable   вместо рекомендации; haiku и fable — только вместе с --confirmed, иначе отказ (код 2)
        --confirmed         пользователь явно подтвердил haiku/fable; без него рекомендация haiku/fable понижается
                            до sonnet/opus соответственно
        --effort low|medium|high|xhigh|max   вместо рекомендации; low и max — только вместе с --confirmed-effort
        --confirmed-effort  пользователь явно подтвердил low/max; без него рекомендация low → medium, max → xhigh
        --budget USD        потолок расходов агента (--max-budget-usd)
        --dry-run           только показать рекомендацию и команду, ничего не запускать
"""
import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import typesafe_guard as guard  # паузы, учёт расходов, предупреждения (см. его докстринг)
import triage_heuristics as heur  # локальные сигналы по тексту (без сети)
import triage_effort as eff       # вторая ось: reasoning effort (политика, окружение, история)
import triage_session as sess_mod  # 2.3: модель и effort сессии, параметр effort у Agent (локально, без сети)
import triage_action as act       # 2.3: строка «ДЕЙСТВИЕ: сам | Agent(…) | спросить» и одна причина
import triage_batch as batch      # 2.3: --batch tasks.json (таблица, порядок по paths, одно подтверждение, Agent(...))
import triage_install as inst     # 2.3: --check — зарегистрирован ли хук, имя скилла для Skill, «призраки»
import triage_projectlog as plog  # 2.3: журнал решений и фактов в корне проекта (опция) и --fact
import triage_secrets as sec    # 2.5: поиск, маскировка и политика «что не отправлять» для секретов и персональных данных
import triage_autofact as autofact  # 2.4: автозапись факта хуком плагина PostToolUse/SubagentStop (опция)

API_URL = os.environ.get("TYPESAFE_API_URL") or "https://api.typesafe.ai/v1/systemone"  # переопределение — только для тестов
MODEL = "jev-latest"
TIMEOUT_S = 8
# Размер отправляемого текста. Предел API — 64k токенов на запрос (ответ 400 max_tokens_exceeded, проверено: ~20 тыс. знаков
# логов уже ~14 тыс. токенов), но точность падает раньше (лишний шум мешает), а лишний объём — это ещё и приватность.
SOFT_CHARS = 3000          # короче — уходит как есть
HARD_CHARS = 4500          # потолок отправки (порядка 2–3 тыс. токенов)
RETRY_CHARS = 1500         # потолок повтора после max_tokens_exceeded
PRETRIM_CHARS = 100000     # сверхдлинный ввод режется ДО обработки (скорость, регулярные выражения)
RUN_LINES = 20             # столько подряд идущих строк считаем вставкой (лог, вывод, код без ```)
LINE_CLIP = 400            # строка длиннее и почти без пробелов — обрезается
SPACE_MIN = 0.08           # доля пробелов в обычной прозе ~0.15; меньше — похоже на сплошной блоб
AGENT_MAX_CHARS = 400000   # для --run: задача длиннее этого — ошибка (положить в файл и дать агенту путь)
MIN_HOOK_CHARS = 40        # короче — реплика, в TypeSafe не уходит
LOG_PATH = guard.HOME / "log.jsonl"
OFF_MARKER = ".typesafe-triage-off"
CHILD_ENV = "TYPESAFE_TRIAGE_CHILD"   # ставится в окружение агента, запущенного через --run: в нём хук молчит, вложенный --run запрещён
DEDUP_S = 8                # второй вызов хука на тот же запрос (session_id + хеш промпта) за это время — молчит
DEDUP_NAME = "dedup"       # каталог в guard.HOME: файлы-метки, имя = хеш (без содержимого промпта), права 0600
# 2.2.0 (T-4): хук никогда не молчит без причины. Метка «в работе» (pending) ставится до триажа, «готово» (done) — после
# вывода заметки; второй вызов ждёт первого и подхватывает работу, если тот оборвался. Весь хук укладывается в бюджет.
HOOK_BUDGET_S = 8.0        # весь хук (бюджет Claude Code — 10 с): не успели — заметка по эвристике и «триаж пропущен: …»
PENDING_STALE_S = HOOK_BUDGET_S + 1.5   # метка «в работе» старше — её хозяина оборвали (тайм-аут Claude Code, kill)
TAKEOVER_RESERVE_S = 0.5   # второй вызов ждёт первого не дольше HOOK_BUDGET_S минус этот запас (нужен на свою заметку)
NET_MIN_S = 1.5            # меньше времени осталось — в TypeSafe не идём, сразу эвристика
DEDUP_POLL_S = 0.1
SKIP_PREFIX = "TypeSafe-триаж пропущен: "
CLARIFY_RISK = 0.67        # уточняющий вопрос: риск не ниже этого (или необратимость / слова критичности) …
CLARIFY_CONF = 0.5         # … и уверенность ниже этого (или нет ответа TypeSafe)
CLARIFY_AMBIG = 0.6        # … и задача открытая (неясность TypeSafe) / есть слова неопределённости
SESSION_EFFORT_GAP = 2     # строка «/effort …» для основной сессии — если её effort известен и отличается на столько ступеней

# ---------- уровни ----------
TIERS = ["haiku", "sonnet", "opus", "fable"]
AUTO_TIERS = ("sonnet", "opus")                     # запускаются без вопросов
CONFIRM_TIERS = {"haiku": "sonnet", "fable": "opus"}  # только с подтверждения пользователя; значение — ближайший безопасный
DEFAULT_TIER = "sonnet"     # если рекомендации нет совсем (пустой текст): модель по умолчанию

# ---------- пороги (подбираются по triage_cases.json через --selftest, не «из головы» навсегда) ----------
WEIGHTS = {"complexity": 0.30, "reasoning": 0.25, "ambiguity": 0.15, "risk": 0.20, "breadth": 0.10}
LOAD_SONNET = 0.25          # нагрузка ниже — кандидат на haiku
LOAD_OPUS = 0.60            # нагрузка от — opus
LOAD_FABLE = 0.84           # нагрузка от — кандидат на fable (плюс уверенность и критичность)
HEUR_RAISE = 0.4            # какая доля превышения «эвристика над TypeSafe» добавляется к нагрузке (вниз эвристика не тянет)
CONF_ESCALATE = 0.5         # минимальная уверенность шкал ниже — шаг вверх (один, не выше opus)…
ESC_MARGIN = 0.15           # …если нагрузка не дальше ESC_MARGIN от следующего порога (сомнение далеко от границы уровень не меняет)
CONF_DOWNGRADE = 0.7        # для haiku уверенность должна быть не ниже, ЛИБО…
HAIKU_UPPER_MAX = 0.15      # …вероятность верхней половины шкал (сложность, рассуждение, риск) не выше этого: «уверенно просто»
HAIKU_AMBIG_UPPER = 0.3     # для haiku вероятность «открытая, неясная задача» не выше
CONF_FABLE = 0.7            # для fable уверенность должна быть не ниже
FLAG_ON = 0.6               # порог «да» для флагов Noul
HAIKU_FLAG_MIN = 0.8        # read_only/mechanical открывают haiku только при уверенном «да»
HAIKU_RISK_MAX = 0.34       # риск для haiku — не выше «легко проверить и откатить»
HAIKU_HEUR_MAX = 0.40       # эвристическая нагрузка выше — haiku запрещён
PROTECT_FLAG = 0.5          # диагностика/незаметные ошибки/необратимость/новизна поднимают до sonnet уже при слабом «да»
RISK_TOP = 0.9              # риск на верхнем уровне шкалы («критично/необратимо»)
FABLE_FLAG_MIN = 0.8        # необратимость для fable — уверенное «да»
FABLE_HEUR_MIN = 0.45       # fable — только если и текст говорит о тяжёлой задаче (или есть слова критичности)
CHAT_SKIP = 0.8             # «это просто реплика» уверенно и работы почти нет — заметку не добавляем
H_LOAD_OPUS = 0.36          # без TypeSafe: эвристическая нагрузка от — opus, ниже — sonnet
H_CRITICAL_OPUS = 2         # без TypeSafe: столько разных групп слов критичности — opus
H_INTENT_OPUS = 0.6         # без TypeSafe: одна группа риска + намерение не легче «проверить/сравнить» — opus
H_INTENT_ALONE_OPUS = 0.8   # без TypeSafe: намерение «доказать» само по себе — opus
AGENT_TIMEOUT_S = 1800
HOOK_TIMEOUT_S = 5            # замеры: медиана ответа ~0.7 с, редкие всплески 5-20 с; бюджет хука в settings.json - 10 с
TRANSIENT_HTTP = (500, 502, 503, 504, 529)   # один быстрый повтор, если остаётся бюджет времени
RETRY_MIN_LEFT_S = 1.5
RETRY_PAUSE_S = 0.4
# Уверенность считаем по осям, несущим выбор уровня: «неясность» и «объём» — вспомогательные (их уверенность системно ниже).
CONF_AXES = ("complexity", "reasoning", "risk")
EFFORT_CONF_AXES = ("reasoning", "shallow_cost", "planning")   # уверенность второй оси

AGENT_RULES = (
    "Работай по правилам CLAUDE.md репозитория: доработка только в отдельной ветке, в main не коммитить и не вливать "
    "без явного акцепта пользователя. Проверки (тесты, чтение результата, проверка на данных) обязательны. "
    "Скилл typesafe-triage не применяй, других агентов на моделях haiku или fable не запускай. "
    "В конце кратко и по-русски доложи, что сделано и что проверено.")

# ---------- вопросы к TypeSafe (английский — основной язык Jev; одна мысль на вопрос; уровни — ситуации с примерами) ----------
ANY_FIELD = " The request can be from any field: software, writing, analysis, data, research, planning, operations."
SCORES = {
    "complexity": {
        "instructions": "How much work does this request ask for?" + ANY_FIELD,
        "criteria": [
            {"what": "A quick answer or one tiny edit",
             "examples": ["define a term", "say where a setting is", "fix a typo", "rename one label"]},
            {"what": "A small self-contained piece of work with an obvious approach",
             "examples": ["a short email", "add one field like an existing one", "summarize one document", "one spreadsheet formula"]},
            {"what": "A substantial piece of work with several parts that must fit together",
             "examples": ["a consistent change across several files", "a multi-section report", "analyze a dataset and explain it",
                          "a project plan with milestones", "find and fix a bug of unknown cause"]},
            {"what": "A large or open-ended project that needs design decisions across many interacting parts",
             "examples": ["design and build a feature end to end", "migrate a system without downtime", "a full strategy or research study",
                          "redesign an architecture"]},
        ],
    },
    "reasoning": {
        "instructions": "How much careful thinking does doing this request well need?",
        "criteria": [
            {"what": "Mechanical: copy, list, look up, count, reformat or rename", "examples": ["list the files", "convert a table to CSV"]},
            {"what": "Routine: follow a known pattern, template or clear instruction",
             "examples": ["write a standard letter", "add a test like the existing ones", "fill in a report template"]},
            {"what": "Careful: weigh options, find a root cause, handle edge cases or check consistency",
             "examples": ["debug an intermittent failure", "compare three vendors", "review a contract clause"]},
            {"what": "Deep: a novel or subtle problem where wrong reasoning looks right",
             "examples": ["design a concurrency scheme", "prove a property", "build a pricing model", "resolve conflicting requirements"]},
        ],
    },
    "ambiguity": {
        "instructions": "How unclear is what exactly has to be produced?",
        "criteria": [
            "Precise: what to produce and where is stated",
            "Some gaps that a sensible default would fill",
            "Open-ended: goals unclear, needs exploration, diagnosis or clarifying questions first",
        ],
    },
    "risk": {
        "instructions": "How costly is a silent mistake in doing this request?",
        "criteria": [
            {"what": "Nothing is changed: a question, an explanation, a draft or a private note"},
            {"what": "A change that is easy to check and undo", "examples": ["code covered by tests", "a document draft", "a local file"]},
            {"what": "A mistake could go unnoticed or be costly to undo",
             "examples": ["data validation or merge rules", "deleting files", "rewriting git history", "figures others will rely on",
                          "a message sent to other people"]},
            {"what": "Critical or irreversible harm is possible",
             "examples": ["production systems or live data", "security or access control", "payments or money transfers",
                          "legal or medical consequences", "a migration that cannot be rolled back"]},
        ],
    },
    "breadth": {
        "instructions": "How much material must be read and kept in mind to do this request?",
        "criteria": [
            "Only the message itself",
            "One file, document or short source",
            "Several files, documents or sources that must be read together",
            "A whole codebase, a large dataset, a long document set or many sources",
        ],
    },
}
FLAGS = {
    "read_only": "Does the request only ask to explain, find, summarize, list or answer, without creating or changing any files, data, documents or systems?",
    "mechanical": "Is the request a purely mechanical edit or transformation such as renaming, reformatting, reordering or converting, with no decisions to make?",
    "needs_investigation": "Is the cause of a problem unknown, so it must be diagnosed or researched before anything can be done?",
    "silent_errors": "Does the request create or change rules, formulas or calculations that process data, such as validation, merging, conversion, financial or statistical figures, where a wrong rule would silently produce wrong results?",
    "irreversible": "Does the request involve an action that is hard or impossible to undo, such as deleting data, deploying to production, migrating a database, sending messages or money to other people, or rewriting history?",
    "novel_design": "Does the request require inventing something new, such as an original design, architecture, strategy, argument or creative piece, rather than following an existing pattern?",
    "conversational": "Is this message just conversation, such as thanks, a greeting, an acknowledgement or a short reaction, rather than a request for work or for an answer?",
}
CHOICES = {
    "domain": {
        "instructions": "What kind of work does this request ask for?",
        "criteria": {
            "software": "Writing, changing, debugging or reviewing code, scripts, builds or repositories, including automated tests",
            "qa": "Testing or quality assurance of a product: running test scenarios, checking a site or app for bugs, "
                  "reproducing, measuring and reporting defects with evidence such as screenshots",
            "writing": "Writing or editing prose: letters, articles, documentation, posts, translations",
            "analysis": "Analysis, comparison, evaluation or review of information, documents or options",
            "data": "Working with data: tables, spreadsheets, queries, calculations, reports",
            "research": "Finding and synthesizing information from sources",
            "planning": "Plans, schedules, strategies, decisions or organizing work",
            "operations": "Operating systems and infrastructure: servers, deployments, accounts, settings, files",
            "conversation": "Small talk, thanks, acknowledgement or a reaction, not a task",
            "other": "None of the above",
        },
    },
}
# Вопросы второй оси (effort: сколько думать) — тем же запросом, отдельно от SCORES/FLAGS (их веса — в triage_effort).
# Доменно-нейтрально: код, документы, данные, письма, анализ, планирование, ops, исследование, дизайн, право, финансы, учёба.
# «Творчество/новизна» — уже есть флаг novel_design (используется и для effort).
EFFORT_SCORES = {
    "planning": {
        "instructions": "How many dependent steps must be planned and kept in order to do this request well?" + ANY_FIELD,
        "criteria": [
            {"what": "One step or a direct answer", "examples": ["answer a question", "rename a label", "sort a list"]},
            {"what": "A few steps in an obvious order",
             "examples": ["edit a document and re-read it", "add a field and a test", "write and format an email"]},
            {"what": "Many steps where later steps depend on earlier findings or decisions",
             "examples": ["reproduce a bug, find the cause, fix it and add a test", "collect data, clean it, analyse it and report",
                          "plan a trip with bookings and a budget"]},
            {"what": "A long chain of dependent stages with checkpoints or a rollback plan",
             "examples": ["a staged migration with verification and rollback", "a multi-month project plan with dependencies",
                          "a research study from hypotheses to conclusions"]},
        ],
    },
    "shallow_cost": {
        "instructions": "What happens if this request gets a quick first-impression answer without careful thought?",
        "criteria": [
            {"what": "A quick answer is exactly what is wanted", "examples": ["a definition", "a fact", "a list", "a simple reformat"]},
            {"what": "A quick answer is fine if done with ordinary care",
             "examples": ["a routine email", "a small edit following a pattern", "a short summary"]},
            {"what": "A quick answer would probably miss important points or edge cases",
             "examples": ["comparing options", "debugging", "reviewing a contract", "planning a budget"]},
            {"what": "A quick answer would likely be wrong in a way that looks right and causes real harm",
             "examples": ["a proof", "a financial model others rely on", "a security fix", "a data migration",
                          "a medical or legal judgment"]},
        ],
    },
}
EFFORT_FLAGS = {
    "verification": "Does doing this well require checking the result before it can be trusted, such as running tests, re-checking calculations, proofreading against sources or validating edge cases?",
    "exploration": "Does this request require searching for or exploring unknown information first, such as where something is, what causes a problem, or what options exist?",
    "constraints": "Does the request state strict constraints or acceptance criteria that the result must satisfy all at once, such as must or must not, an exact format, limits, deadlines or tests that must pass?",
    "coordination": "Must several separate parts, such as files, documents, data sources, systems or people, be kept consistent with each other?",
}


SECRET_RE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._\-]{12,}|\b(?:sk|pk|ghp|gho|ghs|github_pat|xox[abp]|AKIA)[a-z0-9_\-]{10,}"
    r"|(?:password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*\S+|\b[a-f0-9]{32,}\b|\b[A-Za-z0-9+/_\-]{40,}={0,2}(?=\s|$))")


def redact(text):
    """Секреты и персональные данные (triage_secrets: пароли на русском и английском, seed-фразы, ключи, карты, токены, e-mail …)
    не уходят в TypeSafe и не попадают в журнал; прежний шаблон остаётся вторым слоем защиты."""
    return SECRET_RE.sub("[скрыто]", sec.scrub(text))


def pretrim(text):
    """Сверхдлинный ввод режется до обработки: то, что отброшено, не отправляется и не проверяется."""
    if len(text) > PRETRIM_CHARS:
        return text[:PRETRIM_CHARS * 6 // 10] + "\n[… середина очень длинного ввода пропущена …]\n" + text[-PRETRIM_CHARS * 4 // 10:]
    return text


def secrets_info(scan):
    """Результат sec.inspect → сведения для результата и журнала: виды и числа, без значений. None — находок нет."""
    if not scan["count"]:
        return None
    return {"kinds": scan["kinds"], "level": scan["level"], "count": scan["count"]}


def secrets_notice(scan):
    return ("в запросе найдены секреты (%s): в TypeSafe он не отправлен, уровень и effort — по локальной эвристике. "
            "Не повторяй их в ответах и не записывай в файлы, журналы, коммиты и issues; если это настоящие данные, посоветуй их сменить. "
            "Политика — TYPESAFE_TRIAGE_SECRETS (block | strict | mask)." % sec.describe(scan["kinds"]))


def build_questions():
    q = {name: {"type": "score", **spec} for name, spec in list(SCORES.items()) + list(EFFORT_SCORES.items())}
    for name, text in list(FLAGS.items()) + list(EFFORT_FLAGS.items()):
        q[name] = {"type": "noul", "instructions": text,
                   "criteria": {"true": "Yes, clearly", "false": "No"}}
    for name, spec in CHOICES.items():
        q[name] = {"type": "choice", **spec}
    return q


CA_FALLBACKS = ["/etc/ssl/cert.pem", "/opt/homebrew/etc/ca-certificates/cert.pem", "/etc/ssl/certs/ca-certificates.crt"]


def ssl_context():
    """Стандартный контекст; если у сборки Python нет корневых сертификатов (python.org на macOS) — системный пакет CA.
    Проверка сертификата НЕ отключается никогда."""
    ctx = ssl.create_default_context()
    if ctx.cert_store_stats().get("x509_ca", 0) == 0:
        for f in CA_FALLBACKS:
            if os.path.exists(f):
                return ssl.create_default_context(cafile=f)
    return ctx


FENCE_RE = re.compile(r"```.*?```", re.S)


def squeeze_lines(block, head, tail, what):
    """Сжать блок строк до начала и конца с пометкой, сколько пропущено."""
    lines = block.split("\n")
    if len(lines) <= head + tail + 3:
        return block
    return "\n".join(lines[:head] + ["[… %s: пропущено %d строк …]" % (what, len(lines) - head - tail)] + lines[-tail:])


def squeeze_runs(text):
    """Длинные серии подряд идущих непустых строк (вставки без ```) и сверхдлинные строки."""
    out, run = [], []

    def flush():
        if len(run) >= RUN_LINES:
            out.extend(squeeze_lines("\n".join(run), 5, 3, "вставка").split("\n"))
        else:
            out.extend(run)
        run.clear()

    for ln in text.split("\n"):
        if len(ln) > LINE_CLIP and ln.count(" ") < len(ln) * SPACE_MIN:  # сплошной «мусор» (минифицированный JSON, base64); абзац прозы не трогаем
            ln = ln[:LINE_CLIP * 3 // 5] + " […+%d симв.]" % (len(ln) - LINE_CLIP * 3 // 5)
        if ln.strip():
            run.append(ln)
        else:
            flush()
            out.append(ln)
    flush()
    return "\n".join(out)


def make_digest(text, hard=HARD_CHARS):
    """Текст для отправки в TypeSafe: секреты скрыты, большие вставки сжаты, размер ≤ hard.
    Сначала сжимаем вставки (код в ```, длинные серии строк, длинные строки) — просьба пользователя остаётся целиком;
    если всё ещё длинно — начало и конец (просьба обычно в начале или в конце), середина заменяется пометкой."""
    text = redact(pretrim(text))
    if len(text) <= min(SOFT_CHARS, hard):
        return text
    text = FENCE_RE.sub(lambda m: squeeze_lines(m.group(0), 4, 2, "код"), text)
    text = squeeze_runs(text)
    if len(text) <= hard:
        return text
    mark = "\n[… середина пропущена, всего %d знаков …]\n" % len(text)
    head = (hard - len(mark)) * 55 // 100
    return text[:head] + mark + text[len(text) - (hard - len(mark) - head):]


CONTEXT_ENV = "TYPESAFE_TRIAGE_CONTEXT"   # off — не добавлять к дайджесту строку «активная задача» (2.2.0, T-1)
CONTEXT_HEAD = "[Context, not part of the request] The user is continuing this active task: "


def context_enabled():
    return os.environ.get(CONTEXT_ENV, "").lower() not in ("off", "0", "false", "no")


def request_digest(task, cwd=None, hard=HARD_CHARS):
    """Дайджест для TypeSafe + (для короткого продолжения «продолжай …», если задан каталог) одна строка «активная задача»
    из TASKS.md проекта: первый открытый пункт, до 200 знаков, секреты скрыты. → (текст, добавлен ли контекст)."""
    sent = make_digest(task, hard)
    if not (cwd and context_enabled() and heur.is_continuation(task)):
        return sent, False
    line = eff.active_task(cwd)
    if not line:
        return sent, False
    return sent + "\n\n" + CONTEXT_HEAD + redact(line), True


def ask_with_retry(task, key, timeout=TIMEOUT_S):
    """ask_typesafe + один быстрый повтор при временной ошибке сервиса (5xx/529), если в бюджете timeout остаётся время."""
    started = time.monotonic()
    try:
        return ask_typesafe(task, key, timeout)
    except urllib.error.HTTPError as e:
        left = timeout - (time.monotonic() - started) - RETRY_PAUSE_S
        if e.code not in TRANSIENT_HTTP or left < RETRY_MIN_LEFT_S:
            raise
        time.sleep(RETRY_PAUSE_S)
        return ask_typesafe(task, key, left)


def ask_typesafe(task, key, timeout=TIMEOUT_S):
    body = json.dumps({"state": {"task": task}, "model": MODEL,
                       "questions": build_questions()}).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def upper_mass(answer, top):
    """Вероятность верхней половины шкалы (нормированный уровень > 0.5) из probabilities ответа; нет данных — 1.0 (не уверены)."""
    try:
        return sum(float(p) for lvl, p in answer["probabilities"].items() if int(lvl) / float(top) > 0.5)
    except (KeyError, TypeError, ValueError, AttributeError):
        return 1.0


def metrics_from(answers):
    """Ответы API → {имя: (значение 0..1, уверенность 0..1, вероятность верхней половины)}.
    Шкалы нормируются на верхний уровень; у флагов уверенность |2p-1| (так советует документация TypeSafe), третье — p."""
    out = {}
    for name in SCORES:
        a = answers[name]
        top = len(SCORES[name]["criteria"]) - 1
        out[name] = (float(a["score"]) / top, float(a["confidence"]), upper_mass(a, top))
    for name in FLAGS:
        p = float(answers[name]["noul"])
        out[name] = (p, abs(2 * p - 1), p)
    # вопросы effort: отсутствие ответа не ошибка (старый/поддельный сервер) — веса перенормируются в triage_effort
    for name, spec in EFFORT_SCORES.items():
        try:
            a = answers[name]
            top = len(spec["criteria"]) - 1
            out[name] = (float(a["score"]) / top, float(a["confidence"]), upper_mass(a, top))
        except (KeyError, TypeError, ValueError):
            pass
    for name in EFFORT_FLAGS:
        try:
            p = float(answers[name]["noul"])
            out[name] = (p, abs(2 * p - 1), p)
        except (KeyError, TypeError, ValueError):
            pass
    return out


def domain_from(answers):
    """Тип задачи (Choice) — только для заметки и журнала; на уровень не влияет. Нет ответа — None."""
    try:
        a = answers["domain"]
        return {"kind": a["choice"], "confidence": round(float(a.get("confidence", 0)), 2)}
    except (KeyError, TypeError, ValueError):
        return None


def mass(x):
    """Вероятность верхней половины шкалы из кортежа метрики; если её нет — 1.0 (считаем, что не уверены)."""
    return x[2] if len(x) > 2 else 1.0


def heur_load(h):
    return round(sum(WEIGHTS[k] * h["axes"][k] for k in WEIGHTS), 9)   # округление — см. decide


def decide(m, h=None):
    """Чистая политика: метрики TypeSafe (+ сигналы эвристики) → (уровень, причины). Без сети и побочных эффектов.
    Эвристика только поднимает нагрузку, может запретить haiku и обязана подтвердить fable."""
    why = []
    v = {k: x[0] for k, x in m.items()}
    min_conf = min(m[k][1] for k in CONF_AXES)
    load_ts = sum(WEIGHTS[k] * v[k] for k in WEIGHTS)
    load_h = heur_load(h) if h else None
    load = load_ts + HEUR_RAISE * max(0.0, load_h - load_ts) if h else load_ts
    # 2.3: округление до 9 знаков — sum() в Python 3.12+ складывает float точнее, чем в 3.9, и на самой границе порога
    # (например, все оси 0.6 → нагрузка ровно LOAD_OPUS) уровень иначе зависел бы от версии Python
    load_ts, load = round(load_ts, 9), round(load, 9)
    why.append("нагрузка %.2f" % load + (" (TypeSafe %.2f, текст %.2f)" % (load_ts, load_h) if h else ""))
    tier = 0 if load < LOAD_SONNET else 1 if load < LOAD_OPUS else 2

    upper = max(mass(m[k]) for k in CONF_AXES)
    reads = v["read_only"] >= HAIKU_FLAG_MIN
    safe_light = ((reads or v["mechanical"] >= HAIKU_FLAG_MIN)
                  and v["risk"] <= HAIKU_RISK_MAX and mass(m["ambiguity"]) <= HAIKU_AMBIG_UPPER)
    raised = False  # один шаг вверх за низкую уверенность максимум, не два подряд
    if tier == 0 and not safe_light:
        tier, raised = 1, True
        why.append("haiku только для уверенного чтения/механики с низким риском → sonnet")
    if tier == 0 and min_conf < CONF_DOWNGRADE and upper > HAIKU_UPPER_MAX:
        tier, raised = 1, True
        why.append("для haiku нужна уверенность ≥ %.1f (есть %.2f) или «верх шкал» ≤ %.2f (есть %.2f) → sonnet"
                   % (CONF_DOWNGRADE, min_conf, HAIKU_UPPER_MAX, upper))
    if tier == 0 and h and ((h["critical"] and not reads) or load_h >= HAIKU_HEUR_MAX):
        tier, raised = 1, True
        why.append("текст: %s → не haiku" % ("слова риска: " + ", ".join(h["critical"]) if h["critical"] and not reads
                                              else "заметный объём/шаги"))
    protect = [k for k in ("silent_errors", "needs_investigation", "irreversible", "novel_design") if v[k] >= PROTECT_FLAG]
    if tier < 1 and protect:
        tier = 1
        why.append("%s → не ниже sonnet" % "/".join(protect))
    heavy_risk = (v["silent_errors"] >= FLAG_ON or v["irreversible"] >= FLAG_ON or v["risk"] >= RISK_TOP)
    if heavy_risk and v["complexity"] >= 0.5 and v["read_only"] < FLAG_ON:
        if tier < 2:
            why.append("цена ошибки высокая и работа нетривиальная → opus")
        tier = max(tier, 2)
    if v["novel_design"] >= FLAG_ON and v["complexity"] >= 0.6 and tier < 2:
        tier = 2
        why.append("нужна новая разработка/творчество в большой задаче → opus")
    next_cut = LOAD_SONNET if tier == 0 else LOAD_OPUS
    if min_conf < CONF_ESCALATE and tier < 2 and not raised and load >= next_cut - ESC_MARGIN:
        tier += 1
        why.append("низкая уверенность %.2f у границы уровня → шаг вверх" % min_conf)

    critical = v["risk"] >= RISK_TOP or v["irreversible"] >= FABLE_FLAG_MIN or (v["complexity"] >= 0.9 and v["reasoning"] >= 0.9)
    text_agrees = h is None or bool(h["critical"]) or load_h >= FABLE_HEUR_MIN
    if tier == 2 and load >= LOAD_FABLE and critical:
        if min_conf < CONF_FABLE:
            why.append("для fable нужна уверенность ≥ %.1f (есть %.2f) → opus" % (CONF_FABLE, min_conf))
        elif not text_agrees:
            why.append("текст не подтверждает предельную нагрузку → opus")
        else:
            tier = 3
            why.append("критично/необратимо/предельно сложно при уверенности %.2f → fable (только с подтверждением)" % min_conf)
    return TIERS[tier], why


def decide_heuristic(h):
    """Запасной вариант без TypeSafe: только sonnet или opus (ни haiku, ни fable без ответа TypeSafe)."""
    load = heur_load(h)
    tier, why = "sonnet", ["только эвристика: нагрузка по тексту %.2f" % load]
    if load >= H_LOAD_OPUS:
        tier = "opus"
        why.append("≥ %.2f → opus" % H_LOAD_OPUS)
    elif len(h["critical"]) >= H_CRITICAL_OPUS:
        tier = "opus"
        why.append("слова риска (%s) → opus" % ", ".join(h["critical"]))
    elif h.get("effort", {}).get("parts", {}).get("intent", 0) >= H_INTENT_ALONE_OPUS:
        tier = "opus"
        why.append("доказательство/формальная проверка → opus")
    elif h["critical"] and h.get("effort", {}).get("parts", {}).get("intent", 0) >= H_INTENT_OPUS:
        tier = "opus"
        why.append("риск (%s) и тяжёлое намерение (%s) → opus" % (", ".join(h["critical"]), "/".join(h["effort"]["intents"])))
    return tier, why


def http_detail(e):
    """Тело HTTP-ошибки; читается один раз и кэшируется (поток читается единожды)."""
    if not hasattr(e, "_body_text"):
        try:
            e._body_text = e.read().decode("utf-8", "replace")
        except Exception:
            e._body_text = ""
    return e._body_text


def compact_signals(h):
    keep = ("prose_chars", "items", "paths", "steps", "deep", "light", "critical", "has_code", "has_logs")
    out = {k: h[k] for k in keep}
    out["axes"] = {k: round(x, 2) for k, x in h["axes"].items()}
    e = h.get("effort")
    if e:
        out["effort"] = {k: e[k] for k in ("depth", "intents", "diag", "constraints", "accept", "uncertain", "scope", "math",
                                           "retry", "lang")}
    return out


def prompt_id(task):
    return hashlib.sha1(task.encode("utf-8")).hexdigest()[:10]


INHERIT_MAX_TIER = "opus"     # продолжение наследует оценку предыдущего запроса сессии, но не выше этого …
INHERIT_MAX_EFFORT = "xhigh"  # … и не выше этого effort (haiku/fable, low/max — только с подтверждения, не по наследству)


def inherit_from(task, records):
    """Короткое продолжение («продолжай тесты», «и ещё добавь…») наследует оценку последнего оценённого запроса этой
    сессии (журнал, окно истории): → (модель, effort) с потолком opus/xhigh, или None."""
    if not records or not heur.is_continuation(task):
        return None
    last = records[-1]
    tier, effort = last.get("model"), last.get("effort") or eff.DEFAULT_EFFORT
    if tier not in TIERS or effort not in eff.EFFORTS:
        return None
    tier = TIERS[min(TIERS.index(tier), TIERS.index(INHERIT_MAX_TIER))]
    tier = CONFIRM_TIERS.get(tier, tier) if tier == "haiku" else tier
    return tier, eff.at_most(eff.at_least(effort, "medium"), INHERIT_MAX_EFFORT)


def skill_config():
    """config.json скилла (тот же файл, что у typesafe_guard: потолок расходов и т. п.) целиком; нет — {}."""
    try:
        d = json.loads(guard.config_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def set_agent_effort(value):
    """2.3: записать, есть ли у инструмента Agent параметр effort (True/False; None — снова определять автоматически)."""
    c = skill_config()
    if value is None:
        c.pop("agent_effort", None)
    else:
        c["agent_effort"] = bool(value)
    guard._write(guard.config_path(), c)


def add_effort(r, m, h, task, env="auto", history=None, session=None, cwd=None, min_conf=None, transcript=None,
               session_info=None):
    """Вторая ось + явные указания + история: дописывает в результат поля effort_* и при необходимости меняет модель
    (явный выбор пользователя / эскалация по истории), а с 2.3 — действие (поле action: сам / Agent / спросить).
    Старые поля сохраняются (формат аддитивный). session_info — готовые сведения о сессии; без них при env="auto" они
    читаются локально (стенограмма transcript, переменные, настройки), при env={} — не учитываются (офлайн-проверки)."""
    d = heur.directives(task)
    if session_info is None:   # без стенограммы (ручной запуск из Claude Code) — найти её по CLAUDE_CODE_SESSION_ID
        session_info = {} if env == {} else sess_mod.session_info(transcript, cwd, config=skill_config(),
                                                                  discover=transcript is None)
    if env == "auto":
        env = eff.env_context(cwd)
    records = eff.read_history(LOG_PATH, session) if history is None else history
    pid = prompt_id(task)
    retry_now = h["effort"]["retry"]
    hist = eff.history_escalation(records, retry_now, pid)
    r["retry"] = bool(hist[0])
    tier, why = r["model"], [r["reason"]] if r.get("reason") else []
    if hist[1] and tier in ("haiku", "sonnet"):
        tier = TIERS[TIERS.index(tier) + 1]
        why.append("история: повторы подряд → модель %s" % tier)
    tier, user_tier, note = eff.apply_tier_directive(tier, d)
    if note:
        why.append(note)
    prev = inherit_from(task, records)
    if prev and not user_tier and TIERS.index(tier) < TIERS.index(prev[0]):
        tier = prev[0]
        why.append("продолжение предыдущей задачи → модель не ниже %s" % tier)
    e = eff.decide_effort(m, h, tier, env=env, hist=hist, d=d, min_conf=min_conf)
    if prev:
        r["inherited"] = {"model": prev[0], "effort": prev[1]}
        if e["effort_source"] != "user" and eff.idx(e["effort"]) < eff.idx(prev[1]):
            e.update(effort=prev[1], effort_confirm=False, effort_fallback=prev[1], effort_source="history")
            e["effort_reasons"] = list(e.get("effort_reasons") or []) + ["продолжение предыдущей задачи → effort не ниже %s" % prev[1]]
        e["effort_confidence"] = "унаследована"
        if r.get("confidence") == "низкая":
            r["confidence"] = "унаследована от предыдущего запроса"
    r.update(model=tier, confirm=tier in CONFIRM_TIERS and not user_tier, fallback=tier if user_tier else CONFIRM_TIERS.get(tier, tier),
             model_source="user" if user_tier else "auto", reason="; ".join(why), **e)
    if d["phrases"]:
        r["explicit"] = d["phrases"][:4]
    if d.get("mentions"):
        r["mentions"] = d["mentions"]     # маркеры-упоминания (в кавычках, коде, пересказе) — не учтены как указания
    r["effort_delivery"] = effort_delivery(r)
    v = {k: x[0] for k, x in (m or {}).items()}
    stakes = v.get("risk", 0) >= CLARIFY_RISK or v.get("irreversible", 0) >= eff.FLAG_ON or bool(h["critical"])
    unsure = m is None or (min_conf is not None and min_conf < CLARIFY_CONF)
    open_ = v.get("ambiguity", 0) >= CLARIFY_AMBIG or h["effort"]["uncertain"] >= 1
    r["clarify"] = bool(stakes and unsure and open_ and not (user_tier or e["effort_source"] == "user" or prev))
    shared = heur.shared_state_text(task) + heur.device_text(task) + (eff.shared_state_env(cwd) if cwd and env != {} else [])
    if shared:
        r["shared_state"] = shared[:4]
    if env:
        r["env"] = {k: env[k] for k in ("repo", "tests", "ci", "lock", "files", "marker") if k in env}
    if session:
        r["session"] = session
    # 2.3 (#27): действие и сведения о сессии (только служебные: уровень модели, effort, параметр effort у Agent)
    r["history_n"] = len(records)
    if records:
        last = records[-1]
        r["prev"] = {"model": last.get("model"), "effort": last.get("effort"), "action": last.get("action"),
                     "why": last.get("action_why"), "hints": last.get("action_hints") or []}
    if session_info:
        r["session_model"] = {k: session_info.get(k) for k in ("tier", "model", "model_source") if session_info.get(k)}
        if session_info.get("agent_effort") is not None:
            r["agent_effort"] = session_info["agent_effort"]
        if session_info.get("effort"):
            r["session_effort"] = session_info["effort"]
        if session_info.get("work"):   # 2.4.0 (#33): счётчики и профиль сессии — без текста стенограммы
            r["session_work"] = session_info["work"]
    r["continuation"] = heur.is_continuation(task)
    r["action"] = act.decide(r, heur.action_signals(task), session_info, r["continuation"])
    return r


def finish(tier, why, source, h, **extra):
    """Общий вид результата: уровень, нужен ли вопрос пользователю, безопасная замена."""
    assert tier in TIERS
    r = {"model": tier, "source": source, "confidence": "низкая" if source == "heuristic" else extra.pop("conf_label", "обычная"),
         "confirm": tier in CONFIRM_TIERS, "fallback": CONFIRM_TIERS.get(tier, tier), "skip": False,
         "reason": "; ".join(why), "signals": compact_signals(h)}
    r.update(extra)
    return r


def fallback(task, h, reason, ctx=None, **extra):
    tier, why = decide_heuristic(h)
    return add_effort(finish(tier, [reason] + why, "heuristic", h, **extra), None, h, task, **(ctx or {}))


def triage(task, key=None, timeout=TIMEOUT_S, **ctx):
    """Оценка задачи с проверкой на секреты (2.5): критичные находки (приватные ключи, seed-фразы, номера карт) по политике
    TYPESAFE_TRIAGE_SECRETS=block (по умолчанию) в TypeSafe не отправляются вовсе — уровень по эвристике; остальные находки
    маскируются в дайджесте (_triage_net → make_digest). Виды и числа находок — в result["secrets"], значения — нигде."""
    scan = sec.inspect(pretrim(task))
    if sec.withhold(scan):
        if ctx.get("session"):
            ctx["session"] = eff.session_tag(ctx["session"])
        r = fallback(task, heur.signals(task), "запрос с секретами (%s) не отправлен в TypeSafe" % sec.describe(scan["kinds"]), ctx,
                     notice=secrets_notice(scan))
    else:
        r = _triage_net(task, key, timeout, **ctx)
    info = secrets_info(scan)
    if info:
        r["secrets"] = dict(info, withheld=sec.withhold(scan))
    return r


def _triage_net(task, key=None, timeout=TIMEOUT_S, **ctx):
    """Оценка задачи. TypeSafe недоступен (оплата, ключ, сеть, лимиты, пауза) → уровень по эвристике + notice при необходимости;
    при жёсткой паузе (нет средств, ключ, доступ, потолок расходов) сеть не используется вовсе.
    ctx (необязательно): session — session_id хука (история), cwd — каталог (окружение), env — готовый env_context
    ({} — не учитывать окружение), history — готовые записи журнала (для --calibrate)."""
    if ctx.get("session"):
        ctx["session"] = eff.session_tag(ctx["session"])
    h = heur.signals(task)
    key = key or os.environ.get("TYPESAFE_API_KEY")
    if not key:
        return fallback(task, h, "нет TYPESAFE_API_KEY", ctx)
    g = guard.status(key)
    if not g["allowed"]:
        return fallback(task, h, "TypeSafe приостановлен (%s)" % g["kind"], ctx, paused=g["kind"], notice=g["notice"])
    sent, with_ctx = request_digest(task, ctx.get("cwd"))
    info = lambda: {"chars": len(task), "sent": len(sent)}
    try:
        try:
            resp = ask_with_retry(sent, key, timeout)
        except urllib.error.HTTPError as e:
            # слишком большой вход (400 max_tokens_exceeded): один повтор с более коротким дайджестом
            if e.code == 400 and "max_tokens" in http_detail(e):
                sent, with_ctx = request_digest(task, ctx.get("cwd"), RETRY_CHARS)
                resp = ask_typesafe(sent, key, timeout)
            else:
                raise
        m = metrics_from(resp["answers"])
    except urllib.error.HTTPError as e:
        kind, detail, wait = guard.classify_http(e.code, http_detail(e), e.headers)
        if kind == "size":  # не авария и не повод для паузы
            return fallback(task, h, "вход слишком велик для TypeSafe даже после сжатия", ctx, input=info())
        notice = guard.record_failure(kind, detail, wait, key)
        return fallback(task, h, "TypeSafe: %s (HTTP %d)" % (kind, e.code), ctx, paused=kind, notice=notice, input=info())
    except Exception as e:  # сеть, тайм-аут, разбор ответа: эвристика, а не понижение и не падение
        notice = guard.record_failure("outage", type(e).__name__, None, key)
        return fallback(task, h, "TypeSafe недоступен (%s)" % type(e).__name__, ctx, paused="outage", notice=notice)
    tier, why = decide(m, h)
    tokens = resp.get("usage", {}).get("input_tokens")
    min_conf = min(m[k][1] for k in CONF_AXES)
    r = finish(tier, why, "typesafe", h, notice=guard.record_success(tokens),
               conf_label="высокая" if min_conf >= CONF_DOWNGRADE else "средняя" if min_conf >= CONF_ESCALATE else "низкая",
               metrics={k: {"value": round(x[0], 2), "confidence": round(x[1], 2)} for k, x in m.items()},
               domain=domain_from(resp["answers"]), input=info(), tokens=tokens, active_task=with_ctx)
    if m["conversational"][0] >= CHAT_SKIP and m["complexity"][0] <= 0.2 and tier in ("haiku", "sonnet"):
        r["skip"] = True  # реплика, а не задача: заметку не добавляем
    eff_conf = min(m[k][1] for k in EFFORT_CONF_AXES if k in m)
    return add_effort(r, m, h, task, min_conf=eff_conf, **ctx)


def _append_log(rec):
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        new = not LOG_PATH.exists()
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if new:
            os.chmod(LOG_PATH, 0o600)
    except OSError:
        pass


def log_text(task):
    """Начало запроса для журнала: секреты скрыты; запрос с критичными находками (ключ, seed-фраза, карта) не пишется вовсе."""
    found = sec.inspect(pretrim(task))
    if found["level"] == sec.CRITICAL:
        return "[скрыто: запрос содержит критичные секреты — текст не записан]"
    return redact(task)[:200]


def log(task, result, **extra):
    """Журнал решений (первые 200 символов, секреты скрыты, права 0600). Пропущенные реплики сюда не пишутся (см. log_skip).
    extra — дополнительные поля хука (takeover, late …); пустые не пишутся."""
    if not result or result.get("skip") or not result.get("model"):
        return
    rec = {"ts": int(time.time()), "id": prompt_id(task),
           "task": log_text(task), "model": result.get("model"), "source": result.get("source"),
           "reason": result.get("reason"), "metrics": result.get("metrics"), "signals": result.get("signals"),
           "domain": result.get("domain"), "input": result.get("input"), "tokens": result.get("tokens"),
           # 2.1: вторая ось и история (session — хеш session_id, не сам идентификатор)
           "effort": result.get("effort"), "effort_source": result.get("effort_source"),
           "effort_depth": result.get("effort_depth"), "model_source": result.get("model_source"),
           "session": result.get("session"), "retry": result.get("retry")}
    if result.get("secrets"):   # 2.5: только виды и числа находок, без значений
        rec["secrets"] = result["secrets"]
    for k in ("inherited", "shared_state", "active_task"):   # 2.2: контекст задачи и общее состояние (без текста)
        if result.get(k):
            rec[k] = result[k] if k != "active_task" else True
    a = result.get("action") or {}
    if a.get("kind"):   # 2.3: действие и уровень модели сессии (без текста)
        rec["action"] = a["kind"]
        rec["action_why"] = a.get("why")
        if a.get("hints"):
            rec["action_hints"] = a["hints"]
        for k in ("facts", "profile"):   # 2.4.0 (#33): для калибровки (числа и профиль, без текста)
            if a.get(k) is not None:
                rec["session_" + k] = a[k]
    if (result.get("session_model") or {}).get("tier"):
        rec["session_tier"] = result["session_model"]["tier"]
    rec.update({k: v for k, v in extra.items() if v})
    _append_log(rec)


def log_skip(task, session_id, reason):
    """2.2.0: пропуск или отказ хука — тоже в журнал, но без текста запроса: время, хеш, длина, хеш сессии, причина.
    Такие записи (поле skipped, без model) не участвуют в истории сессии и в сводке моделей."""
    rec = {"ts": int(time.time()), "skipped": reason}
    if isinstance(task, str):
        rec.update(id=prompt_id(task), chars=len(task))
    if session_id:
        rec["session"] = eff.session_tag(session_id)
    _append_log(rec)


# У инструмента Agent параметра effort может не быть (зависит от версии и окружения Claude Code), а хук схему инструментов
# не видит. Поэтому заметка условная, а для случая «параметра нет» — готовая фраза глубины для промпта агента (ru, en)
# и, когда effort критичен, запуск отдельным процессом `--run` (`claude -p --model … --effort …`).
EFFORT_PROMPT = {
    "low": ("Ответь кратко, без лишних шагов и рассуждений.", "Answer briefly, without extra steps or deliberation."),
    "medium": ("Обычная аккуратность, без лишней глубины.", "Ordinary care, no extra depth."),
    "high": ("Думай тщательно: проверь крайние случаи и результат.", "Think carefully: check edge cases and the result."),
    "xhigh": ("Думай очень тщательно: сравни альтернативы, проверь крайние случаи, перепроверь результат.",
              "Think very carefully: compare alternatives, check edge cases, re-verify the result."),
    "max": ("Думай максимально глубоко: разбери альтернативы и риски, проверь каждый шаг, в конце — самопроверка.",
            "Think as deeply as possible: weigh alternatives and risks, verify every step, self-check before answering."),
}
EFFORT_DELIVERY = ("agent_param", "prompt", "run")


def effort_delivery(result):
    """Как донести effort, если у Agent нет параметра effort (параметр, если есть, передаётся всегда):
    agent_param — effort обычный (medium/high без высокой цены ошибки): хватит общей фразы о глубине в промпте;
    prompt — effort необычный (low/xhigh/max или задан пользователем/проектом): готовая фраза глубины в промпт;
    run — effort критичен (high и выше при высокой цене ошибки, max или задан явно): ещё и запуск через --run."""
    e = result.get("effort") or eff.DEFAULT_EFFORT
    mt = result.get("metrics") or {}
    val = lambda k: (mt.get(k) or {}).get("value", 0)
    risky = val("risk") >= eff.RISK_EFFORT_AT or val("irreversible") >= eff.FLAG_ON \
        or (not mt and len((result.get("signals") or {}).get("critical") or []) >= 2)
    explicit = result.get("effort_source") in ("user", "project")
    if eff.idx(e) >= eff.idx("high") and (risky or explicit or e == "max"):
        return "run"
    if e in ("low", "xhigh", "max") or explicit:
        return "prompt"
    return "agent_param"


def effort_phrase(effort, lang="ru"):
    ru, en = EFFORT_PROMPT.get(effort, EFFORT_PROMPT[eff.DEFAULT_EFFORT])
    return en if lang == "en" else ru


def self_command():
    """Команда запуска этого скрипта для заметки: python3 (Windows — python) и полный путь (домашний каталог — $HOME:
    так короче и работает и в bash, и в PowerShell)."""
    p = os.path.abspath(__file__)
    home = os.path.expanduser("~")
    if home and p.startswith(home + os.sep):
        p = "$HOME" + p[len(home):]
    p = p.replace("\\", "/")
    return "%s %s" % ("python" if os.name == "nt" else "python3", ('"%s"' % p) if " " in p else p)


CONF_RANK = {"низкая": 0, "средняя": 1, "высокая": 2}


def overall_confidence(result):
    """Одна уверенность на всю оценку (2.3, #27: без «effort high … Effort (низкая)» рядом): эвристика — низкая,
    наследование — унаследована, иначе меньшая из уверенностей модели и effort (заданное пользователем не снижает)."""
    if result.get("source") != "typesafe":
        return "низкая"
    if result.get("inherited"):
        return "унаследована"
    ranked = [x for x in (result.get("confidence"), result.get("effort_confidence")) if x in CONF_RANK]
    if not ranked:
        return "задано пользователем" if result.get("effort_source") == "user" or result.get("model_source") == "user" else "средняя"
    return min(ranked, key=CONF_RANK.get)


def agent_call(model, effort):
    return "Agent(model=%s, effort=%s)" % (model, effort)


def _fallback_text(fb):
    if not fb or fb.get("kind") == "self":
        return "сам"
    return agent_call(fb["model"], fb["effort"])


def note_tag(result):
    """Хвост первой строки: что нужно задаче и откуда оценка (модель/effort; TypeSafe или эвристика; тип; id решения)."""
    parts = ["%s/%s" % (result["model"], result.get("effort") or eff.DEFAULT_EFFORT),
             "TypeSafe" if result.get("source") == "typesafe" else "только эвристика"]
    kind = (result.get("domain") or {}).get("kind")
    if kind:
        parts.append("тип %s" % kind)
    if result.get("decision_id"):
        parts.append("id %s" % result["decision_id"])
    return "[TypeSafe-триаж: %s]" % "; ".join(parts)


def _confirm_line(result, a):
    tier, e = result["model"], result.get("effort") or eff.DEFAULT_EFFORT
    m_conf, e_conf = bool(result.get("confirm")), bool(result.get("effort_confirm"))
    mfb = result.get("fallback") if m_conf else tier
    efb = result.get("effort_fallback") if e_conf else e
    qm = "«Запустить агента на %s?» («Да, %s» / «Нет, %s»)" % (tier, tier, mfb)
    qe = "«Effort %s — %s?» («Да, %s» / «Нет, %s»)" % (e, "дольше и дороже" if e in eff.COSTLY_EFFORTS else "минимум размышлений",
                                                     e, efb)
    yes = agent_call(*(((a.get("agent") or {}).get("model", tier), (a.get("agent") or {}).get("effort", e))))
    if m_conf and e_conf:
        ask = "ОДИН вызов AskUserQuestion с двумя вопросами: %s и %s" % (qm, qe)
    else:
        ask = "AskUserQuestion %s" % (qm if m_conf else qe)
    cost = " (xhigh/max — больше токенов)" if e in eff.COSTLY_EFFORTS or efb in eff.COSTLY_EFFORTS else ""
    return "• %s. «Да» → %s; нет явного «да» → %s%s." % (ask, yes, _fallback_text(a.get("fallback")), cost)


def _effort_line(result, a):
    """Как передать effort исполнителю: параметром Agent (если он есть), фразой в промпте, для критичного — --run."""
    tier, e = (a.get("agent") or {}).get("model", result["model"]), (a.get("agent") or {}).get("effort", result.get("effort") or "high")
    has = result.get("agent_effort")
    how = result.get("effort_delivery") or effort_delivery(result)
    lang = ((result.get("signals") or {}).get("effort") or {}).get("lang")
    phrase = effort_phrase(e, lang)
    tail = ""
    if how == "run" and has is not True:
        flags = "--tier %s%s --effort %s%s" % (tier, " --confirmed" if tier in CONFIRM_TIERS else "", e,
                                                " --confirmed-effort" if e in eff.CONFIRM_EFFORTS else "")
        tail = "; effort критичен, работа изолируемая — можно отдельно: %s --run %s [--edit|--readonly] \"<задача>\"%s" % (
            self_command(), flags, " (--confirmed* — после «да»)" if a.get("kind") == "ask" else "")
    if has is True:
        return "• effort=%s — параметром Agent: он есть, а правило CLAUDE.md/скилла — явное требование его передать." % e
    if has is False:
        return "• У Agent нет параметра effort (не ошибка): в промпт агента «%s»%s." % (phrase, tail)
    return ("• effort — параметром Agent, если он есть в схеме (правило CLAUDE.md/скилла — явное требование); нет — не ссылайся "
            "на него (не ошибка), в промпт агента «%s»%s. Есть ли параметр — запиши один раз: --set-agent-effort yes|no."
            % (phrase, tail))


def hook_context(result, cur_effort=None):
    """2.3 (#27): заметка начинается строкой «ДЕЙСТВИЕ: сам | Agent(model=…, effort=…) | спросить — причина. Уверенность: …»;
    дальше — только нужные пункты (подтверждение, способ передать effort, общее состояние, долгое ожидание …).
    Числа осей и причины слоёв — в JSON и журнале, не в заметке."""
    a = result.get("action") or act.decide(result)
    kind = a.get("kind")
    head_act = agent_call(a["agent"]["model"], a["agent"]["effort"]) if kind == "agent" else "спросить" if kind == "ask" else "сам"
    lines = ["ДЕЙСТВИЕ: %s — %s. Уверенность: %s. %s" % (head_act, a.get("reason", ""), overall_confidence(result),
                                                         note_tag(result))]
    hints = a.get("hints") or []
    delegating = kind == "agent" or (kind == "ask" and a.get("why") == "confirm")
    if kind == "ask" and (result.get("confirm") or result.get("effort_confirm")):
        lines.append(_confirm_line(result, a))
    if result.get("explicit"):
        lines.append("• Задано пользователем в запросе (%s) — это согласие, повторно не спрашивай." % ", ".join(result["explicit"]))
    if delegating:
        lines.append(_effort_line(result, a))
    if "shared" in hints:   # 2.2.0 (T-3): исполнитель не увидит окна браузера, входа пользователя, устройства
        lines.append("• Общее интерактивное состояние (%s): исполнитель не увидит твой браузер, вход и устройство — делегируй только "
                     "независимые части, шаги в общем окне делай сам." % "; ".join(result.get("shared_state") or []))
    if "wait" in hints:
        lines.append("• Долгое ожидание («%s»): запусти фоновый скрипт (Bash в фоне, Monitor) и проверяй его состояние, "
                     "а не держи субагента." % (a.get("wait") or "минуты и часы"))
    if "parallel" in hints and delegating:
        lines.append("• Части независимы: можно несколько Agent параллельно — только с непересекающимися путями "
                     "(порядок и одно подтверждение на всё — --batch).")
    efb = result.get("effort_fallback") if result.get("effort_confirm") else result.get("effort") or eff.DEFAULT_EFFORT
    if kind == "self" and cur_effort and cur_effort in eff.EFFORTS and abs(eff.idx(cur_effort) - eff.idx(efb)) >= SESSION_EFFORT_GAP:
        lines.append("• Делаешь сам (effort сессии %s): одной строкой предложи пользователю «/effort %s»." % (cur_effort, efb))
    if delegating:
        lines.append("• Исполнителю: самодостаточный промпт (шаблон references/executor-prompt.md), скилл typesafe-triage ему не "
                     "применять; план SuperPowers — модели ролей из его Model Selection («most capable» = opus, «cheapest» = sonnet).")
    if delegating and result.get("decision_id") and autofact.enabled():   # 2.4.0 (#33): привязка факта к решению
        lines.append("• Автозапись факта: добавь в description Agent метку «triage:%s»." % result["decision_id"])
    return "\n".join(lines)


def switched_off(cwd):
    """Выключатель: TYPESAFE_TRIAGE=off или файл .typesafe-triage-off в каталоге проекта либо выше."""
    if os.environ.get("TYPESAFE_TRIAGE", "").lower() in ("off", "0", "false", "no"):
        return True
    try:
        d = Path(cwd or os.getcwd()).resolve()
        return any((p / OFF_MARKER).exists() for p in [d, *d.parents])
    except OSError:
        return False


HARNESS_PREFIXES = ("[SYSTEM", "[Subagent", "[Request interrupted", "[Image", "Caveat:")
# Теги, которые добавляет среда (Claude Code, IDE): блок вырезается целиком; любой другой «<…>» — часть запроса (HTML, XML, свои теги)
SERVICE_TAGS = ("system-reminder", "ide_selection", "ide_opened_file", "task-notification", "agent-message", "user-prompt-submit-hook",
                "command-name", "command-message", "command-args", "local-command-stdout", "local-command-stderr", "local-command-caveat")
SERVICE_BLOCK_RE = re.compile(r"<(%s)\b[^>]*>.*?</\1\s*>" % "|".join(SERVICE_TAGS), re.S | re.I)


UNCLOSED_SERVICE_RE = re.compile(r"<(?:%s)\b" % "|".join(SERVICE_TAGS), re.I)


def strip_service_blocks(prompt):
    """Запрос без служебных блоков среды (<system-reminder>, <ide_selection>, …): их не оцениваем и не отправляем наружу."""
    return SERVICE_BLOCK_RE.sub(" ", prompt).strip() if isinstance(prompt, str) else prompt


def is_harness_message(prompt):
    """Служебные сообщения среды (уведомления задач, отчёты субагентов, теги) — не запрос пользователя: не отправляем наружу.
    Запрос, у которого после вырезания служебных блоков остался текст, — обычный (блоки в начале его не делают служебным)."""
    cleaned = strip_service_blocks(prompt)
    if prompt.strip() and not cleaned:
        return True
    head = cleaned.lstrip()[:200]
    return (head.startswith(HARNESS_PREFIXES) or "[Subagent hand-back]" in head or "<task-notification>" in head
            or bool(UNCLOSED_SERVICE_RE.match(head)))     # служебный тег без закрывающего (обрезанное сообщение)


def skip_reason(prompt):
    """Почему запрос не оцениваем (и не отправляем в TypeSafe); None — оцениваем."""
    if not isinstance(prompt, str):
        return "некорректный ввод хука"
    if is_harness_message(prompt):
        return "служебное сообщение среды"
    prompt = strip_service_blocks(prompt)
    if prompt.lstrip().startswith("/"):
        return "команда /…"
    if len(prompt.strip()) < MIN_HOOK_CHARS:
        return "короткая реплика (< %d знаков)" % MIN_HOOK_CHARS
    if heur.is_chatter(prompt):
        return "реплика без поручения"
    return None


def forced_skip_reason(raw, text):
    """2.4.2: принудительный запуск снимает пропуски (короткая реплика, «болтовня», команда /… этого скилла); остаются
    только чисто служебное сообщение среды и пустая задача после метки."""
    if is_harness_message(raw):
        return "служебное сообщение среды"
    if not (text or "").strip():
        return "после метки нет текста задачи"
    return None


def should_skip(prompt):
    """Что вообще не оцениваем (и не отправляем в TypeSafe): короткие реплики, команды, служебные сообщения, болтовня."""
    return skip_reason(prompt) is not None


# ---------- идемпотентность хука: метки «в работе» / «готово» (2.2.0, T-4) ----------
def dedup_key(session_id, prompt):
    return hashlib.sha256((session_id + "\0" + prompt).encode("utf-8")).hexdigest()[:32]


def _marker_write(f, state, create=False):
    """Метка: {"state", "pid", "ts"} — без текста запроса, права 0600. Пишется во временный файл и появляется атомарно уже
    с содержимым: create=True — os.link (FileExistsError — метка уже есть), иначе os.replace."""
    data = json.dumps({"state": state, "pid": os.getpid(), "ts": time.time()})
    tmp = f.with_name("%s.%d.tmp" % (f.name, os.getpid()))
    fd = os.open(str(tmp), os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as h:
        h.write(data)
    try:
        if not create:
            os.replace(str(tmp), str(f))
            return
        try:
            os.link(str(tmp), str(f))
        except FileExistsError:
            raise
        except (OSError, AttributeError, NotImplementedError):   # ФС без жёстких ссылок: создание O_EXCL + запись
            fd = os.open(str(f), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w") as h:
                h.write(data)
    finally:
        try:
            os.unlink(str(tmp))
        except OSError:
            pass


LEGACY = "legacy"   # пустая метка хука до 2.2: тот вызов после метки всегда выдаёт заметку


def _marker_read(f):
    """→ (state, pid, ts). Пустая метка — формат до 2.2 (state=legacy, время файла); нечитаемая — «в работе»."""
    mtime = f.stat().st_mtime                 # FileNotFoundError — метки уже нет
    try:
        raw = f.read_text(encoding="utf-8")
    except OSError:
        return "pending", None, mtime
    if not raw.strip():
        return LEGACY, None, mtime
    try:
        st = json.loads(raw)
        return st.get("state", "pending"), st.get("pid"), float(st.get("ts", mtime))
    except (ValueError, TypeError, AttributeError):
        return "pending", None, mtime


def _pid_alive(pid):
    """Жив ли процесс (только POSIX; на Windows os.kill(pid, 0) завершил бы процесс — там считаем живым и ждём по времени)."""
    if not isinstance(pid, int) or pid <= 0 or os.name == "nt":
        return True
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _dedup_cleanup(d, now):
    for x in d.iterdir():
        try:
            if now - x.stat().st_mtime > 60 * DEDUP_S:
                x.unlink()
        except OSError:
            pass


def dedup_claim(session_id, prompt, started=None):
    """Кто из вызовов хука на этот запрос (session_id + хеш промпта) даёт заметку.
    → ("own", метка | None) — мы; ("dup", None) — другой вызов уже дал заметку (молчим);
      ("takeover", метка, причина) — другой вызов начал, но оборвался или не уложился: заметку даём мы.
    Второй вызов ждёт первого (метка «в работе») не дольше HOOK_BUDGET_S − TAKEOVER_RESERVE_S. Без session_id и при ошибке
    файловой системы — «own» без метки (лучше лишняя заметка, чем потерянная)."""
    if not session_id:
        return ("own", None)
    started = time.monotonic() if started is None else started
    d = guard.HOME / DEDUP_NAME
    try:
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
        f = d / dedup_key(session_id, prompt)
        while True:
            try:
                _marker_write(f, "pending", create=True)
                _dedup_cleanup(d, time.time())
                return ("own", f)
            except FileExistsError:
                pass
            try:
                state, pid, ts = _marker_read(f)
            except FileNotFoundError:
                continue                      # метку только что убрали — пробуем занять снова
            age = time.time() - ts
            if state in ("done", LEGACY):
                if age < DEDUP_S:
                    return ("dup", None)
                _marker_write(f, "pending")   # тот же текст, но позже — это новый запрос пользователя
                return ("own", f)
            if age > PENDING_STALE_S:
                reason = "первый вызов хука оборвался (метка «в работе» %.0f с)" % age
            elif not _pid_alive(pid):
                reason = "первый вызов хука завершился, не дав заметки"
            elif time.monotonic() - started >= HOOK_BUDGET_S - TAKEOVER_RESERVE_S:
                reason = "первый вызов хука не ответил за %.0f с" % (time.monotonic() - started)
            else:
                time.sleep(DEDUP_POLL_S)
                continue
            _marker_write(f, "pending")
            return ("takeover", f, reason)
    except OSError:
        return ("own", None)


def already_handled(session_id, prompt, now=None):
    """Совместимость (до 2.2): True — этот запрос уже обработан другим вызовом. Ставит метку «готово» сразу."""
    claim = dedup_claim(session_id, prompt)
    if claim[0] == "dup":
        return True
    mark_done(claim[1])
    return False


def mark_done(f):
    if f is None:
        return
    try:
        _marker_write(f, "done")
    except OSError:
        pass


# ---------- бюджет времени хука ----------
class HookTimeout(Exception):
    pass


_ABANDONED = []   # потоки, брошенные по тайм-ауту: процесс хука завершается os._exit, не дожидаясь их


def call_with_deadline(fn, seconds):
    """fn() в отдельном потоке; не успела за seconds — HookTimeout (поток бросаем, он демон)."""
    box = {}

    def target():
        try:
            box["r"] = fn()
        except BaseException as e:  # noqa: B902 — передаём в основной поток как есть
            box["e"] = e
    th = threading.Thread(target=target, daemon=True)
    th.start()
    th.join(max(0.0, seconds))
    if th.is_alive():
        _ABANDONED.append(th)
        raise HookTimeout()
    if "e" in box:
        raise box["e"]
    return box["r"]


def offline_triage(task, reason, **ctx):
    """Оценка без сети (только эвристика) — когда на TypeSafe не осталось времени."""
    if ctx.get("session"):
        ctx["session"] = eff.session_tag(ctx["session"])
    return fallback(task, heur.signals(task), reason, ctx)


def hook_triage(prompt, sid, cwd, started, late=None, transcript=None):
    """Триаж в рамках HOOK_BUDGET_S от начала хука. → (результат, причина деградации или None)."""
    left = HOOK_BUDGET_S - (time.monotonic() - started)
    if late or left < NET_MIN_S + 0.3:
        why = late or "не осталось времени на TypeSafe"
        return offline_triage(prompt, why, session=sid, cwd=cwd, transcript=transcript), why
    try:
        r = call_with_deadline(lambda: triage(prompt, timeout=min(HOOK_TIMEOUT_S, left - 1.0), session=sid, cwd=cwd,
                                              transcript=transcript), left - 0.3)
        return r, None
    except HookTimeout:
        why = "TypeSafe-оценка не уложилась в %.0f с" % HOOK_BUDGET_S
        return offline_triage(prompt, why, session=sid, cwd=cwd, transcript=transcript), why


QUIET_REASON = "решение прежнее (продолжение)"


def quiet_reason(prompt, result, late=None):
    """2.3 (#27, «реже»): короткое продолжение с тем же решением, что и в прошлый раз, — заметку не повторяем.
    Молчим только если: это продолжение («продолжай …», «и ещё …»), в сессии есть прошлое решение, совпадают действие,
    модель и effort, нет подтверждений, уточняющего вопроса, предупреждения TypeSafe и сбоя. Иначе — None (заметка)."""
    prev = result.get("prev") or {}
    a = result.get("action") or {}
    if late or result.get("notice") or not result.get("continuation") or not prev:
        return None
    if result.get("confirm") or result.get("effort_confirm") or result.get("clarify") or a.get("kind") == "ask":
        return None
    if (prev.get("model"), prev.get("effort"), prev.get("action")) != (result.get("model"), result.get("effort"), a.get("kind")):
        return None
    if set(a.get("hints") or []) - set(prev.get("hints") or []):   # новое указание (долгое ожидание, общее устройство …)
        return None
    return QUIET_REASON


def log_quiet(task, session_id, reason, result):
    """Намеренное молчание (2.3): запись в журнал без текста запроса — время, хеш, длина, хеш сессии, причина и само
    решение (оно продолжает историю сессии: наследование, повторы)."""
    a = result.get("action") or {}
    rec = {"ts": int(time.time()), "id": prompt_id(task), "chars": len(task), "quiet": reason,
           "model": result.get("model"), "effort": result.get("effort"), "action": a.get("kind"), "action_why": a.get("why"),
           "source": result.get("source"), "retry": result.get("retry")}
    if a.get("hints"):
        rec["action_hints"] = a["hints"]
    if result.get("inherited"):
        rec["inherited"] = result["inherited"]
    if session_id:
        rec["session"] = eff.session_tag(session_id)
    _append_log(rec)


def skip_output(reason, failure=False):
    """Одна строка вместо заметки. failure — сбой (видит и пользователь), иначе намеренный пропуск (только модель)."""
    line = SKIP_PREFIX + reason
    if failure:
        ctx = line + ". Заметки нет: уровень и effort выбирай сам; пользователь видит это сообщение."
    else:
        ctx = line + ". Заметки нет — работай как обычно, триаж не упоминай."
    out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}
    if failure:
        out["systemMessage"] = line
    return out


def hook_output(result, cwd, late=None):
    parts, out = [], {}
    if result.get("model") and not result.get("skip"):
        parts.append(hook_context(result, result.get("session_effort") or eff.session_effort(cwd)))
    msgs = []
    if late:
        msgs.append(SKIP_PREFIX + late + "; уровень и effort — по локальной эвристике")
    if result.get("notice"):  # проблема с TypeSafe: показать пользователю прямо (systemMessage) и поручить сообщить в ответе
        msgs.append(result["notice"])
        parts.append("ВАЖНО (TypeSafe): в начале ответа одной-двумя строками сообщи пользователю: " + result["notice"])
    found = result.get("secrets") or {}
    if found.get("level") in (sec.CRITICAL, sec.SECRET) and not result.get("notice"):   # замаскировано и отправлено: сказать об этом
        names = sec.describe(found.get("kinds") or {})
        msgs.append("TypeSafe-триаж: в запросе замаскированы перед отправкой: %s." % names)
        parts.append("Безопасность: в запросе пользователя есть секреты (%s). Не повторяй их в ответах и не записывай в файлы, журналы, "
                     "коммиты и issues; если это настоящие данные, посоветуй пользователю их сменить." % names)
    if msgs:
        out["systemMessage"] = "\n".join(msgs)
    if parts:
        out["hookSpecificOutput"] = {"hookEventName": "UserPromptSubmit", "additionalContext": "\n\n".join(parts)}
    return out


def run_hook():
    """Хук не ломает и не тормозит работу (код всегда 0, укладывается в HOOK_BUDGET_S) и не молчит без причины:
    вместо заметки — строка «TypeSafe-триаж пропущен: <причина>» и запись в журнал. Молчит только при выключателе,
    внутри агента --run, когда заметку уже дал другой вызов хука на тот же запрос и (2.3, «реже») на короткое
    продолжение с прежним решением — последнее пишется в журнал (поле quiet, без текста запроса)."""
    started = time.monotonic()
    if os.environ.get(CHILD_ENV):
        return 0  # мы внутри агента, запущенного --run: уровень модели уже выбран, советов и второго обращения в TypeSafe не нужно
    prompt, sid, f, sent = None, None, None, []

    def emit(out):
        if out and not sent:
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()
            sent.append(1)
    try:
        try:
            data = json.load(sys.stdin)
        except Exception as e:
            data = e
        if not isinstance(data, dict) or not isinstance(data.get("prompt", ""), str):
            why = "некорректный ввод хука (%s)" % (type(data).__name__)
            emit(skip_output(why, failure=True))
            log_skip(None, None, why)
            return 0
        cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
        transcript = data.get("transcript_path") if isinstance(data.get("transcript_path"), str) else None
        if switched_off(cwd):
            return 0
        prompt = data.get("prompt") or ""
        sid = data.get("session_id") if isinstance(data.get("session_id"), str) else None
        why = skip_reason(prompt)
        raw_prompt, prompt = prompt, strip_service_blocks(prompt)   # дальше (дайджест, журнал, дедуп) — только то, что написал пользователь
        force, forced_text = heur.force_trigger(prompt)             # 2.4.2: пользователь сам просит триаж
        if force:
            why = forced_skip_reason(raw_prompt, forced_text)
            prompt = forced_text
        if why:
            emit(skip_output(why))
            log_skip(raw_prompt, sid, why)
            return 0
        claim = dedup_claim(sid, prompt, started)
        if claim[0] == "dup":
            log_skip(prompt, sid, "дубль: заметку дал другой вызов хука")
            return 0
        f = claim[1]
        takeover = claim[2] if claim[0] == "takeover" else None
        late_in = takeover if takeover and HOOK_BUDGET_S - (time.monotonic() - started) < NET_MIN_S + 0.3 else None
        result, late = hook_triage(prompt, sid, cwd, started, late_in, transcript)
        if result.get("skip"):
            why = "реплика (по оценке TypeSafe)"
            emit(skip_output(why))
            log_skip(prompt, sid, why)
        else:
            quiet = None if force else quiet_reason(prompt, result, late)   # просили триаж — заметка всегда
            if quiet:
                log_quiet(prompt, sid, quiet, result)
            else:
                project_decision(prompt, result, cwd, via="hook")
                emit(hook_output(result, cwd, late))
                log(prompt, result, takeover=takeover, late=late, forced=force)
    except Exception as e:
        why = "ошибка %s" % type(e).__name__
        try:
            emit(skip_output(why, failure=True))
            log_skip(prompt, sid, why)
        except Exception:
            pass
    finally:
        mark_done(f)
    return 0


CASES_FILE = "triage_cases.json"
HOLDOUT_MOD = 5            # отложенная часть кейсов (~20 %): sha1(task) % HOLDOUT_MOD == 0 — не используется при подстройке


def is_holdout(task):
    return int(hashlib.sha1(task.encode("utf-8")).hexdigest(), 16) % HOLDOUT_MOD == 0


def history_records(prev):
    """Предыдущие запросы кейса → записи журнала одной сессии (как их пишет log)."""
    recs, seen = [], set()
    for i, p in enumerate(prev or []):
        pid = prompt_id(p)
        recs.append({"ts": int(time.time()) - 60 * (len(prev) - i), "session": "selftest", "id": pid,
                     "retry": heur.is_retry(p) or pid in seen})
        seen.add(pid)
    return recs


def _range(c, key, single, order):
    vals = c.get(key) or ([c[single]] if c.get(single) else [])
    vals = [x for x in vals if x in order]
    return (min(vals, key=order.index), max(vals, key=order.index)) if vals else None


def _cmp(got, rng, order):
    """-1 ниже допустимого, 0 в диапазоне, +1 выше."""
    if rng is None or got not in order:
        return 0
    return -1 if order.index(got) < order.index(rng[0]) else 1 if order.index(got) > order.index(rng[1]) else 0


class Replay:
    """Кэш ответов TypeSafe для --calibrate: ключ = (набор вопросов, дайджест). Нет ответа в кэше — живой запрос и запись."""

    def __init__(self, path):
        self.path = Path(path)
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}
        self.qhash = hashlib.sha1(json.dumps(build_questions(), sort_keys=True).encode("utf-8")).hexdigest()[:10]
        self.live = ask_typesafe

    def __call__(self, task, key, timeout=TIMEOUT_S):
        k = self.qhash + ":" + hashlib.sha1(task.encode("utf-8")).hexdigest()
        if k not in self.data:
            self.data[k] = self.live(task, key, timeout)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        return self.data[k]


def run_cases(heuristic_only=False, split="all", calibrate=False):
    """Эталонные задачи (triage_cases.json): модель и effort против ожидаемого диапазона.
    expect — уровень модели или "skip"; effort / effort_ok — ожидаемый effort и допустимый диапазон; tier_ok — диапазон модели;
    history — предыдущие запросы той же сессии. С --heuristic ожидания сводятся к запасной полосе (sonnet/opus, medium..xhigh),
    кроме явных указаний пользователя. Возврат: словарь счётчиков по частям train/holdout."""
    cases = json.loads(Path(__file__).with_name(CASES_FILE).read_text(encoding="utf-8"))
    stats = {part: {"n": 0, "m_ok": 0, "m_under": 0, "m_over": 0, "e_ok": 0, "e_under": 0, "e_over": 0, "nosig": 0}
             for part in ("train", "holdout")}
    dist, confusion = {}, {}
    for c in cases:
        task = c["task"]
        part = "holdout" if is_holdout(task) else "train"
        if split != "all" and part != split:
            continue
        st = stats[part]
        if c["expect"] == "skip":
            got_skip = should_skip(task) or (not heuristic_only and triage(task, env={}, history=[]).get("skip"))
            st["n"] += 1
            st["m_ok"] += bool(got_skip)
            st["m_over"] += not got_skip
            print("%-6s %-7s ожид skip   %s | %s" % ("ok" if got_skip else "over", part, "пропуск" if got_skip else "заметка", task[:60]))
            continue
        hist = history_records(c.get("history"))
        if heuristic_only:
            r = fallback(task, heur.signals(task), "офлайн-проверка", {"env": {}, "history": hist})
        else:
            r = triage(task, env={}, history=hist)
            if r.get("source") != "typesafe":
                st["nosig"] += 1
                print("NOSIG  %-7s %s | %s" % (part, r.get("reason"), task[:60]))
                continue
        st["n"] += 1
        mr = _range(c, "tier_ok", "expect", TIERS)
        er = _range(c, "effort_ok", "effort", eff.EFFORTS)
        if heuristic_only:
            mr = tuple(CONFIRM_TIERS.get(x, x) for x in mr) if r.get("model_source") != "user" else mr
            if er and r.get("effort_source") != "user":
                lo, hi = eff.H_EFFORT_BAND
                er = (eff.at_most(eff.at_least(er[0], lo), hi), eff.at_most(eff.at_least(er[1], lo), hi))
        dm, de = _cmp(r["model"], mr, TIERS), _cmp(r["effort"], er, eff.EFFORTS)
        for ax, dv in (("m", dm), ("e", de)):
            st[ax + ("_ok" if dv == 0 else "_under" if dv < 0 else "_over")] += 1
        dist[r["effort"]] = dist.get(r["effort"], 0) + 1
        if c.get("effort"):
            confusion.setdefault(c["effort"], {}).setdefault(r["effort"], 0)
            confusion[c["effort"]][r["effort"]] += 1
        tag = "UNDER" if dm < 0 or de < 0 else "over" if dm > 0 or de > 0 else "ok"
        print("%-6s %-7s модель %-6s (ожид %s) effort %-6s (ожид %s) глубина %.2f | %s" % (
            tag, part, r["model"], "-".join(mr) if mr else "?", r["effort"], "-".join(er) if er else "?",
            r.get("effort_depth", 0), task[:70]))
        if calibrate or tag != "ok":
            print("        модель: %s\n        effort: %s" % (r.get("reason", ""), "; ".join(r.get("effort_reasons", []))))
    for part, st in stats.items():
        if st["n"] or st["nosig"]:
            print("\n[%s] кейсов %d | модель: совпало %d, ниже ожидаемого (опасно) %d, выше (дорого) %d | effort: совпало %d, "
                  "ниже ожидаемого (опасно) %d, выше (дорого) %d | без сигнала %d" % (
                      part, st["n"], st["m_ok"], st["m_under"], st["m_over"], st["e_ok"], st["e_under"], st["e_over"], st["nosig"]))
    if calibrate:
        print("\nРаспределение effort: " + ", ".join("%s %d" % (e, dist.get(e, 0)) for e in eff.EFFORTS))
        print("Ожидаемый → выданный effort:")
        for e in eff.EFFORTS:
            if e in confusion:
                print("  %-6s → %s" % (e, ", ".join("%s %d" % (g, confusion[e].get(g, 0)) for g in eff.EFFORTS if confusion[e].get(g))))
    return stats


def log_summary():
    """Сводка журнала: распределение моделей и effort, источники effort, доля повторов."""
    try:
        allrecs = [json.loads(x) for x in LOG_PATH.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        allrecs = []
    recs = [r for r in allrecs if isinstance(r, dict) and r.get("model")]
    skipped = [r for r in allrecs if isinstance(r, dict) and r.get("skipped")]
    if not recs:
        print("\nЖурнал %s пуст или недоступен." % LOG_PATH)
        return
    def count(key):
        out = {}
        for r in recs:
            out[r.get(key)] = out.get(r.get(key), 0) + 1
        return ", ".join("%s %d" % (k, v) for k, v in sorted(out.items(), key=lambda kv: -kv[1]))
    print("\nЖурнал %s: записей %d" % (LOG_PATH, len(recs)))
    print("  модели: " + count("model"))
    print("  effort: " + count("effort") + "  (None — записи до 2.1)")
    print("  источник effort: " + count("effort_source"))
    print("  повторы (эскалация по истории): %d" % sum(1 for r in recs if r.get("retry")))
    quiet = sum(1 for r in recs if r.get("quiet"))
    acts = {}
    for r in recs:
        if r.get("action"):
            acts[r["action"]] = acts.get(r["action"], 0) + 1
    if quiet or acts:
        print("  2.3: действие — %s; без заметки (решение прежнее): %d" % (
            ", ".join("%s %d" % kv for kv in sorted(acts.items(), key=lambda kv: -kv[1])) or "—", quiet))
    if skipped:
        kinds = {}
        for r in skipped:
            k = r["skipped"].split(" (")[0]
            kinds[k] = kinds.get(k, 0) + 1
        print("  пропуски и отказы хука (2.2+): %d — %s" % (len(skipped), ", ".join(
            "%s %d" % kv for kv in sorted(kinds.items(), key=lambda kv: -kv[1]))))


def run_selftest(heuristic_only=False, split="all", calibrate=False):
    stats = run_cases(heuristic_only, split, calibrate)
    if calibrate:
        log_summary()
    under = sum(st["m_under"] + st["e_under"] for st in stats.values())
    return 1 if under else 0


def build_agent_cmd(tier, readonly=False, budget=None, edit=False, allow=(), confirmed=False, effort=None, confirmed_effort=False):
    """Команда запуска отдельного агента Claude Code на заданном уровне. haiku/fable — только с confirmed=True;
    effort low/max — только с confirmed_effort=True (неизвестный уровень CLI молча игнорирует, поэтому проверяем здесь)."""
    if tier not in TIERS:
        raise ValueError("недопустимый уровень модели %r: разрешены %s" % (tier, ", ".join(TIERS)))
    if tier in CONFIRM_TIERS and not confirmed:
        raise ValueError("уровень %s запускается только с явным подтверждением пользователя (--confirmed); без него — %s"
                         % (tier, CONFIRM_TIERS[tier]))
    if effort is not None and effort not in eff.EFFORTS:
        raise ValueError("недопустимый effort %r: разрешены %s" % (effort, ", ".join(eff.EFFORTS)))
    if effort in eff.CONFIRM_EFFORTS and not confirmed_effort:
        raise ValueError("effort %s ставится только с явным подтверждением пользователя (--confirmed-effort); без него — %s"
                         % (effort, eff.safe_effort(effort)))
    if effort is not None and effort not in eff.MODEL_EFFORTS.get(tier, eff.EFFORTS):
        raise ValueError("сочетание %s + effort %s не поддерживается" % (tier, effort))
    if readonly and edit:
        raise ValueError("--readonly и --edit несовместимы")
    cmd = ["claude", "-p", "--model", tier] + (["--effort", effort] if effort else []) + ["--append-system-prompt", AGENT_RULES]
    if readonly:
        cmd += ["--permission-mode", "plan"]
    elif edit:
        cmd += ["--permission-mode", "acceptEdits"]
    for rule in allow:
        cmd += ["--allowedTools", rule]
    if budget is not None:
        cmd += ["--max-budget-usd", str(budget)]
    return cmd


def opts(argv, name):
    """Все значения повторяющейся опции `--name значение`."""
    return [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == name]


def opt(argv, name):
    """Значение опции вида `--name значение`; None, если опции нет."""
    i = argv.index(name) + 1 if name in argv else 0
    return argv[i] if 0 < i < len(argv) else None


def run_agent(argv):
    """argv: как sys.argv, но без `--run`. Задача — позиционные слова; она уходит агенту через stdin."""
    words, skip = [], False
    for a in argv[1:]:
        if skip:
            skip = False
        elif a in ("--tier", "--budget", "--allow", "--effort"):
            skip = True
        elif not a.startswith("--"):
            words.append(a)
    if os.environ.get(CHILD_ENV):
        print("Вложенный запуск --run запрещён: вы уже внутри агента, запущенного через --run (уровень модели выбран, дальше не делегируем).")
        return 2
    task = " ".join(words).strip()
    if not task:
        print('Нужен текст задачи: --run "текст задачи"')
        return 2
    if len(task) > AGENT_MAX_CHARS:
        print("Задача длиннее %d знаков: сохраните её в файл и поставьте агенту задачу «прочитай файл …»." % AGENT_MAX_CHARS)
        return 2
    confirmed, confirmed_effort = "--confirmed" in argv, "--confirmed-effort" in argv
    forced, forced_effort = opt(argv, "--tier"), opt(argv, "--effort")
    if forced and forced in CONFIRM_TIERS and not confirmed:
        print("Уровень %s запускается только после явного подтверждения пользователя: добавьте --confirmed или выберите %s."
              % (forced, CONFIRM_TIERS[forced]))
        return 2
    if forced_effort is not None:
        if forced_effort not in eff.EFFORTS:
            print("Недопустимый effort %r: разрешены %s." % (forced_effort, ", ".join(eff.EFFORTS)))
            return 2
        if forced_effort in eff.CONFIRM_EFFORTS and not confirmed_effort:
            print("Effort %s ставится только после явного подтверждения пользователя: добавьте --confirmed-effort или выберите %s."
                  % (forced_effort, eff.safe_effort(forced_effort)))
            return 2
    result = {}
    if not (forced and forced_effort):
        result = triage(task, cwd=os.getcwd())
        log(task, result)
        if result.get("notice"):
            print(result["notice"], file=sys.stderr)
    why = []
    if forced:
        tier = forced
        why.append("уровень задан вручную")
    else:
        tier = result.get("model") or DEFAULT_TIER
        why.append(result.get("reason") or "рекомендации нет; беру %s по умолчанию" % DEFAULT_TIER)
        if result.get("source") == "heuristic":
            why[-1] += " (уверенность низкая)"
        # явный выбор модели в тексте задачи — согласие пользователя
        if tier in CONFIRM_TIERS and not confirmed and result.get("model_source") != "user":
            why.append("рекомендован %s, но без --confirmed запускаю %s" % (tier, CONFIRM_TIERS[tier]))
            tier = CONFIRM_TIERS[tier]
        confirmed = confirmed or result.get("model_source") == "user"
    if forced_effort:
        effort = forced_effort
        why.append("effort задан вручную")
    else:
        effort = result.get("effort") or eff.DEFAULT_EFFORT
        why.append("effort %s: %s" % (effort, "; ".join(result.get("effort_reasons") or ["по умолчанию"])))
        if effort in eff.CONFIRM_EFFORTS and not confirmed_effort and result.get("effort_source") not in ("user", "project"):
            why.append("рекомендован effort %s, но без --confirmed-effort ставлю %s" % (effort, eff.safe_effort(effort)))
            effort = eff.safe_effort(effort)
        confirmed_effort = confirmed_effort or result.get("effort_source") in ("user", "project")
    try:
        cmd = build_agent_cmd(tier, "--readonly" in argv, opt(argv, "--budget"), "--edit" in argv, opts(argv, "--allow"), confirmed,
                              effort, confirmed_effort)
    except ValueError as e:
        print(e)
        return 2
    print("Агент: %s, effort %s | %s" % (tier, effort, " | ".join(why)), file=sys.stderr)
    if "--dry-run" in argv:
        print(" ".join(cmd[:6]) + " … (задача — через stdin)\n" + task)
        return 0
    cmd = [shutil.which(cmd[0]) or cmd[0]] + cmd[1:]   # Windows: claude может быть claude.cmd/.exe — ищем по PATH
    try:
        r = subprocess.run(cmd, input=task, text=True, cwd=os.getcwd(), timeout=AGENT_TIMEOUT_S, env=dict(os.environ, **{CHILD_ENV: "1"}))
    except FileNotFoundError:
        print("Команда claude не найдена в PATH")
        return 127
    except subprocess.TimeoutExpired:
        print("Агент не уложился в %d с и остановлен" % AGENT_TIMEOUT_S)
        return 124
    return r.returncode


# ---------- --where: где скрипт и какие хуки на него смотрят (2.2.0, T-5) ----------
HOOK_PATH_RE = re.compile(r"\"([^\"]*typesafe_triage\.py)\"|([^\s\"'=]*typesafe_triage\.py)")


def _expand(path, home):
    path = path.replace("${HOME}", home).replace("$HOME", home).replace("%USERPROFILE%", home)
    if path.startswith("~"):
        path = home + path[1:]
    return path


def hook_entries(settings_files, home):
    """Хуки UserPromptSubmit с typesafe_triage.py в файлах настроек → [(файл, команда, путь, существует|None)].
    Читается только блок hooks (ключи и прочие настройки не выводятся)."""
    out = []
    for sf in settings_files:
        try:
            data = json.loads(Path(sf).read_text(encoding="utf-8"))
            groups = (data.get("hooks") or {}).get("UserPromptSubmit") or []
        except (OSError, ValueError, AttributeError):
            continue
        for g in groups if isinstance(groups, list) else []:
            for hk in (g.get("hooks") or []) if isinstance(g, dict) else []:
                cmd = hk.get("command") if isinstance(hk, dict) else None
                if not isinstance(cmd, str) or "typesafe_triage" not in cmd:
                    continue
                m = HOOK_PATH_RE.search(cmd)
                raw = (m.group(1) or m.group(2)) if m else None
                if raw and "CLAUDE_PLUGIN_ROOT" in raw:
                    out.append((str(sf), cmd, raw, None))
                elif raw:
                    p = _expand(raw, home)
                    out.append((str(sf), cmd, p, os.path.isfile(p)))
                else:
                    out.append((str(sf), cmd, None, None))
    return out


def plugin_installs(home, settings_files):
    """Включён ли плагин typesafe-triage@… и какие версии лежат в кэше плагинов."""
    enabled = []
    for sf in settings_files:
        try:
            ep = json.loads(Path(sf).read_text(encoding="utf-8")).get("enabledPlugins") or {}
        except (OSError, ValueError, AttributeError):
            continue
        enabled += [k for k, v in ep.items() if k.startswith("typesafe-triage@") and v]
    cache = sorted(str(p) for p in Path(home, ".claude", "plugins", "cache").glob("*/typesafe-triage/*") if p.is_dir())
    return sorted(set(enabled)), cache


def install_kind(path):
    s = path.replace("\\", "/")
    if "/plugins/cache/" in s:
        return "плагин из маркетплейса (папка версии меняется при обновлении — путь не прописывайте вручную)"
    if "/.claude/skills/" in s:
        return "копия в каталоге скиллов"
    return "рабочая копия или клон репозитория"


def where_report(home=None, cwd=None):
    """Текст для --where: первая строка — фактический путь скрипта (её можно брать в переменную), дальше — диагностика."""
    home = home or os.path.expanduser("~")
    cwd = cwd or os.getcwd()
    me = os.path.abspath(__file__)
    real = os.path.realpath(me)
    sf = [Path(home, ".claude", "settings.json"), Path(home, ".claude", "settings.local.json"),
          Path(cwd, ".claude", "settings.json"), Path(cwd, ".claude", "settings.local.json")]
    lines = [me,
             "# каталог скриптов: %s" % os.path.dirname(me),
             "# установка: %s" % install_kind(real)]
    if real != me:
        lines.append("# ссылка ведёт в: %s" % real)
    if os.environ.get("CLAUDE_PLUGIN_ROOT"):
        lines.append("# CLAUDE_PLUGIN_ROOT: %s" % os.environ["CLAUDE_PLUGIN_ROOT"])
    lines.append("# python: %s (%s)" % (sys.version.split()[0], sys.executable))
    lines.append("# состояние и журнал: %s" % guard.HOME)
    lines.append("# запуск: %s <команда>" % self_command())
    hooks = hook_entries(sf, home)
    enabled, cache = plugin_installs(home, sf[:2])
    warn = []
    lines.append("# хуки UserPromptSubmit на typesafe_triage.py в settings.json:" + ("" if hooks else " нет"))
    for f, cmd, p, ok in hooks:
        state = "через ${CLAUDE_PLUGIN_ROOT}" if p and ok is None else "файл есть" if ok else "ФАЙЛА НЕТ" if p else "путь не распознан"
        lines.append("#   %s: %s — %s" % (f, cmd, state))
        if p and ok is False:
            warn.append("хук в %s ведёт в несуществующий файл %s: Claude Code не сможет запустить скрипт — заметок не будет, "
                        "а python3 вернёт код 2 (такой код блокирует запрос). Уберите этот хук или поправьте путь" % (f, p))
    lines.append("# плагин typesafe-triage: %s" % (("включён (%s)" % ", ".join(enabled)) if enabled else "не включён"))
    if cache:
        lines.append("# версии в кэше плагинов: %s" % ", ".join(os.path.basename(c) for c in cache))
    if enabled and hooks:
        warn.append("хук прописан и в settings.json, и в плагине: заметка будет одна, но оставьте один хук")
    if not enabled and not hooks:
        warn.append("хук не найден ни в settings.json, ни среди включённых плагинов — заметок «TypeSafe-триаж» не будет")
    _name, note, sp, _sf = inst.skill_status(home, cwd, bool(enabled))   # 2.3 (#28): имя для Skill и «призраки»
    lines.append("# вызов через Skill: %s" % note)
    warn += sp
    for w in warn:
        lines.append("# ВНИМАНИЕ: " + w)
    lines.append("# открытые сессии: правки хуков в settings.json подхватываются на лету, а хук только что установленного "
                 "или включённого плагина — после /reload-plugins или перезапуска Claude Code")
    return "\n".join(lines)


def format_status():
    """Человекочитаемое состояние защиты: пауза, расходы за месяц, потолок."""
    sm = guard.summary()
    p, u = sm["pause"], sm["usage"]
    lines = ["Состояние TypeSafe-триажа (%s)" % sm["state_file"]]
    if p:
        since = time.strftime("%Y-%m-%d %H:%M", time.localtime(p.get("since", 0)))
        until = (", авто-проверка после %s" % time.strftime("%H:%M", time.localtime(p["until"]))) if p.get("until") else ""
        lines.append("ПАУЗА: %s с %s%s. %s" % (p["kind"], since, until, (p.get("detail") or "")[:200]))
        lines.append("  Что делать: " + guard.message(p["kind"], p.get("detail", ""), p.get("until"), sm["failures"], p.get("cost"), sm["budget_usd"]))
        lines.append("  Пока пауза, уровень выбирается только локальной эвристикой (sonnet/opus, уверенность низкая).")
    else:
        lines.append("Пауза: нет (TypeSafe используется)")
    cap = sm["budget_usd"]
    lines.append("Месяц %s: запросов %d, входных токенов %d, оценка расходов $%.4f из потолка %s" % (
        sm["month"], u["requests"], u["tokens"], u["cost_usd"], ("$%.2f" % cap) if cap > 0 else "без потолка"))
    lines.append("Оценка считается по токенам из ответов API и цене $%.3f за млн; это НЕ баланс аккаунта (баланс через API недоступен): "
                 "остаток смотрите в %s" % (guard.PRICE_PER_MTOK_USD, guard.CONSOLE_URL))
    return "\n".join(lines)


def flag_value(argv, name):
    """Флаг `--name` (→ True) или `--name=ЗНАЧЕНИЕ` (→ строка); нет флага — None."""
    for a in argv:
        if a == name:
            return True
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def project_decision(task, result, cwd, via="cli", task_id=None, flag=None):
    """2.3 (#30): решение — в журнал проекта triage-log.jsonl, если он включён (переменная или флаг); без текста запроса.
    Ставит в результат decision_id (виден в заметке — для --fact) и expected (медиана прошлых фактов). Сбой — молча."""
    try:
        path = plog.log_path(cwd, flag)
        if path is None:
            return None
        did = str(task_id) if task_id else prompt_id(task)
        rec = plog.decision_record(did, result, via, task_id=task_id, session=result.get("session"), records=plog.read(path))
        result["decision_id"] = did
        if rec.get("expected"):
            result["expected"] = rec["expected"]
        return path if plog.append(path, rec) else None
    except Exception:  # журнал проекта вспомогательный: не ломает ни хук, ни команду
        return None


def run_check():
    """--check: TypeSafe (ключ, сеть, сертификаты) + 2.3 (#28): зарегистрирован ли хук, как вызывать скилл через Skill.
    Код: 0 — всё в порядке; 1 — TypeSafe не ответил; 3 — TypeSafe ответил, но хук не зарегистрирован или сломан."""
    r = triage("Исправь падение теста test_login: таймаут при вызове сервиса авторизации", timeout=10)
    print(json.dumps({k: r.get(k) for k in ("model", "source", "reason")}, ensure_ascii=False))
    print("python:", sys.version.split()[0], "| ключ:", "есть" if os.environ.get("TYPESAFE_API_KEY") else "НЕТ")
    if r.get("notice"):
        print(r["notice"])
    print(format_status())
    res = inst.check(cwd=os.getcwd(), script=os.path.abspath(__file__))
    print("\n".join(inst.report_lines(res)))
    s = sess_mod.session_info(None, os.getcwd(), config=skill_config(), discover=True)
    print("Сессия: модель %s, effort %s%s" % (
        ("%s (%s)" % (s["tier"], s["model_source"])) if s.get("tier") else "неизвестна" + (
            " (%s)" % s["model_source"] if s.get("model_source") else ""),
        s.get("effort") or "неизвестен", (", Claude Code %s" % s["version"]) if s.get("version") else ""))
    print("Agent и effort: параметр effort у Agent — %s" % (
        {True: "есть", False: "нет"}.get(s.get("agent_effort"), "неизвестно (запишите после проверки схемы: --set-agent-effort yes|no)")
        + ((" (%s)" % s["agent_effort_source"]) if s.get("agent_effort_source") else "")))
    w = s.get("work") or {}
    if w:   # 2.4.0 (#33): только счётчики служебных полей, без текста
        print("Сессия (служебные поля%s): чтение %d, запись %d, команды %d, агенты %d; фактов %d, реплик %d; контекст %s; "
              "профиль %s" % (", после сжатия" if w.get("compacted") else "", w.get("read", 0), w.get("write", 0),
                              w.get("shell", 0), w.get("agent", 0), w.get("facts", 0), w.get("user_turns", 0),
                              ("%d ток." % w["context_tokens"]) if w.get("context_tokens") is not None else "неизвестен",
                              w.get("profile") or "не определён (мало данных)"))
    plp = plog.log_path(os.getcwd())
    print("Автозапись фактов (%s): %s" % (autofact.ENV, "выкл (по умолчанию)" if not autofact.enabled() else (
        "вкл → %s" % plp if plp else "вкл, но журнал проекта выключен (%s) — факты не пишутся" % plog.ENV)))
    if r.get("source") != "typesafe":
        return 1
    return 0 if res["registered"] else 3


def run_batch_cli(argv):
    """--batch tasks.json [--json] [--prompts] [--project-log[=ПУТЬ]] (2.3, #29)."""
    path = opt(argv, "--batch")
    if not path or path.startswith("--"):
        print("Использование: --batch tasks.json [--json] [--prompts] — файл: [{\"id\", \"task\", \"paths\": [...]}, …]")
        return 2
    try:
        tasks = batch.load_tasks(path)
    except batch.BatchError as e:
        print("--batch: %s" % e)
        return 2
    cwd, flag = os.getcwd(), flag_value(argv, "--project-log")

    def one(task):
        r = triage(task["task"], cwd=cwd)
        log(task["task"], r)
        project_decision(task["task"], r, cwd, via="batch", task_id=task["id"], flag=flag)
        if r.get("notice"):
            print(r["notice"], file=sys.stderr)
        return r
    rep = batch.run(tasks, one)
    if "--json" in argv:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(batch.format_text(rep, prompts="--prompts" in argv))
    return 0


def run_fact_cli(argv):
    """--fact <id> --model M --effort E --tokens N [--minutes N] --outcome X [--review-issues N] [--project-log=ПУТЬ]
    (2.3, #30): факт после подзадачи — в журнал проекта (явная команда — пишет и без включённой опции)."""
    try:
        rec = plog.fact_record(opt(argv, "--fact"), opt(argv, "--model"), opt(argv, "--effort"), opt(argv, "--tokens"),
                               opt(argv, "--minutes"), opt(argv, "--outcome"), opt(argv, "--review-issues"))
    except ValueError as e:
        print("--fact: %s" % e)
        return 2
    if str(rec.get("ref", "")).startswith("--"):
        print("--fact: нужен id решения сразу после --fact")
        return 2
    path = plog.log_path(os.getcwd(), flag_value(argv, "--project-log") or True)
    if path is None or not plog.append(path, rec):
        print("--fact: не удалось записать журнал проекта (%s)" % path)
        return 1
    print("Факт записан в %s: %s" % (path, json.dumps(rec, ensure_ascii=False)))
    return 0


def main(argv):
    if "--where" in argv:
        print(where_report())
        return 0
    if "--status" in argv:
        print(format_status())
        return 0
    if "--resume" in argv:
        p = guard.resume()
        print("Пауза снята (%s). TypeSafe снова используется." % p["kind"] if p else "Паузы не было.")
        return 0
    if "--pause" in argv:
        guard.pause_manual(" ".join(a for a in argv[1:] if not a.startswith("--")))
        print("TypeSafe отключён вручную (уровень — только по локальной эвристике). Включить: --resume")
        return 0
    if "--set-budget" in argv:
        try:
            guard.set_budget(float(opt(argv, "--set-budget")))
        except (TypeError, ValueError):
            print("Использование: --set-budget <USD>, например 5 (0 — без потолка)")
            return 2
        print("Месячный потолок расходов: $%s. Если TypeSafe на паузе из-за потолка — выполните --resume." % opt(argv, "--set-budget"))
        return 0
    if "--run" in argv:
        return run_agent([a for a in argv if a != "--run"])
    if "--digest" in argv:  # показать, что именно уйдёт в TypeSafe
        text = " ".join(a for a in argv[1:] if not a.startswith("--")) or sys.stdin.read()
        d, with_ctx = request_digest(text, os.getcwd())
        scan = sec.inspect(pretrim(text))
        print("знаков: было %d, уйдёт %d%s" % (len(text), len(d), " (с строкой «активная задача» из TASKS.md)" if with_ctx else ""))
        if scan["count"]:
            print("секреты: %s (уровень %s, политика %s)%s" % (sec.describe(scan["kinds"]), scan["level"], sec.policy(),
                                                              " — в TypeSafe НЕ отправляется" if sec.withhold(scan) else " — маскируются"))
        print("---\n" + d)
        return 0
    if "--scan" in argv:  # что найдёт проверка секретов (только виды и числа, значения не печатаются); код 3 — отправка заблокирована
        text = " ".join(a for a in argv[1:] if not a.startswith("--")) or sys.stdin.read()
        scan = sec.inspect(pretrim(text))
        print(json.dumps({"level": scan["level"], "kinds": scan["kinds"], "count": scan["count"], "policy": sec.policy(),
                          "withheld": sec.withhold(scan)}, ensure_ascii=False))
        return 3 if sec.withhold(scan) else 0
    if "--signals" in argv:  # локальные сигналы, без сети
        text = " ".join(a for a in argv[1:] if not a.startswith("--")) or sys.stdin.read()
        h = heur.signals(text)
        tier, why = decide_heuristic(h)
        e = eff.decide_effort(None, h, tier, env={}, d=heur.directives(text))
        print(json.dumps({"skip": should_skip(text), "heuristic_tier": tier, "reason": "; ".join(why),
                          "load": round(heur_load(h), 2), "heuristic_effort": e["effort"], "effort_reasons": e["effort_reasons"],
                          "directives": heur.directives(text), "signals": compact_signals(h)}, ensure_ascii=False, indent=2))
        return 0
    if "--check" in argv:
        return run_check()
    if "--set-agent-effort" in argv:
        val = (opt(argv, "--set-agent-effort") or "").lower()
        if val not in ("yes", "no", "auto"):
            print("Использование: --set-agent-effort yes|no|auto — есть ли у инструмента Agent параметр effort (auto — "
                  "определять по стенограмме)")
            return 2
        set_agent_effort(None if val == "auto" else val == "yes")
        print("Записано в %s: у Agent параметр effort — %s." % (guard.config_path(), {"yes": "есть", "no": "нет",
                                                                                      "auto": "определять автоматически"}[val]))
        return 0
    if "--batch" in argv:
        return run_batch_cli(argv)
    if "--fact" in argv:
        return run_fact_cli(argv)
    if "--hook" in argv:
        rc = run_hook()
        if _ABANDONED:                     # поток с зависшим запросом брошен по тайм-ауту: выходим, не дожидаясь его
            sys.stdout.flush()
            os._exit(rc)
        return rc
    if "--selftest" in argv or "--calibrate" in argv:
        if opt(argv, "--cache"):
            globals()["ask_typesafe"] = Replay(opt(argv, "--cache"))
        split = opt(argv, "--split") or "all"
        if split not in ("all", "train", "holdout"):
            print("--split: all | train | holdout")
            return 2
        rc = run_selftest("--heuristic" in argv, split, "--calibrate" in argv)
        if "--calibrate" in argv:   # 2.3 (#30): факты из журнала проекта — для сведения, на код возврата не влияют
            facts = opt(argv, "--facts")
            path = Path(facts) if facts else plog.log_path(os.getcwd(), True)
            if facts or (path and path.exists()):
                print("\n".join(plog.summary(path)))
        return rc
    if len(argv) < 2:
        print(__doc__)
        return 2
    task = " ".join(a for a in argv[1:] if not a.startswith("--"))
    result = triage(task, cwd=os.getcwd())
    project_decision(task, result, os.getcwd(), via="cli", flag=flag_value(argv, "--project-log"))
    log(task, result)
    if result.get("notice"):
        print(result["notice"], file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    # Windows: консоль/пайпы по умолчанию не UTF-8; хук получает UTF-8 JSON от Claude Code
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv))
