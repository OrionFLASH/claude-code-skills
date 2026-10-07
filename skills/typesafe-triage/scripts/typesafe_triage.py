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

Запуск (только стандартная библиотека; ключ — переменная окружения TYPESAFE_API_KEY):
    python3 typesafe_triage.py "текст задачи"        # JSON с метриками, сигналами и рекомендацией
    python3 typesafe_triage.py --hook                # режим хука UserPromptSubmit (stdin = JSON хука)
    python3 typesafe_triage.py --digest "текст"       # показать, что именно уйдёт в TypeSafe (или текст из stdin)
    python3 typesafe_triage.py --signals "текст"      # показать локальные сигналы эвристики (без сети)
    python3 typesafe_triage.py --status               # пауза, расходы за месяц, потолок
    python3 typesafe_triage.py --resume               # снять паузу после пополнения баланса / исправления ключа
    python3 typesafe_triage.py --pause "причина"      # отключить TypeSafe вручную;  --set-budget USD  месячный потолок расходов
    python3 typesafe_triage.py --check                # диагностика: ключ, сеть, сертификаты
    python3 typesafe_triage.py --selftest            # эталонные задачи (triage_cases.json) через TypeSafe; нужна сеть
    python3 typesafe_triage.py --selftest --heuristic   # те же задачи только по эвристике (офлайн)
    python3 typesafe_triage.py --run "текст задачи"  # триаж + запуск отдельного агента `claude -p` на нужной модели
        --readonly          агент только читает и планирует (--permission-mode plan), файлы не правит
        --edit              агент может править файлы в текущем каталоге (--permission-mode acceptEdits); без --edit и --readonly
                            в режиме -p агент не получает права на запись и остановится с просьбой о разрешении (проверено)
        --allow "Bash(git status)"   доп. разрешённый инструмент (--allowedTools); можно несколько раз, например для запуска тестов
        --tier haiku|sonnet|opus|fable   вместо рекомендации; haiku и fable — только вместе с --confirmed, иначе отказ (код 2)
        --confirmed         пользователь явно подтвердил haiku/fable; без него рекомендация haiku/fable понижается
                            до sonnet/opus соответственно
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
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import typesafe_guard as guard  # паузы, учёт расходов, предупреждения (см. его докстринг)
import triage_heuristics as heur  # локальные сигналы по тексту (без сети)

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
H_CRITICAL_OPUS = 2         # без TypeSafe: столько разных групп слов критичности при заметном объёме — opus
AGENT_TIMEOUT_S = 1800
HOOK_TIMEOUT_S = 3
# Уверенность считаем по осям, несущим выбор уровня: «неясность» и «объём» — вспомогательные (их уверенность системно ниже).
CONF_AXES = ("complexity", "reasoning", "risk")

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
            "software": "Writing, changing, debugging, testing or reviewing code, scripts, builds or repositories",
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
AXIS_RU = {"complexity": "сложность", "reasoning": "рассуждение", "ambiguity": "неясность", "risk": "риск", "breadth": "объём"}


SECRET_RE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._\-]{12,}|\b(?:sk|pk|ghp|gho|ghs|github_pat|xox[abp]|AKIA)[a-z0-9_\-]{10,}"
    r"|(?:password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*\S+|\b[a-f0-9]{32,}\b|\b[A-Za-z0-9+/_\-]{40,}={0,2}(?=\s|$))")


def redact(text):
    """Строки, похожие на ключи и пароли, не уходят в TypeSafe и не попадают в журнал."""
    return SECRET_RE.sub("[скрыто]", text)


def build_questions():
    q = {name: {"type": "score", **spec} for name, spec in SCORES.items()}
    for name, text in FLAGS.items():
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
    if len(text) > PRETRIM_CHARS:
        text = text[:PRETRIM_CHARS * 6 // 10] + "\n[… середина очень длинного ввода пропущена …]\n" + text[-PRETRIM_CHARS * 4 // 10:]
    text = redact(text)
    if len(text) <= min(SOFT_CHARS, hard):
        return text
    text = FENCE_RE.sub(lambda m: squeeze_lines(m.group(0), 4, 2, "код"), text)
    text = squeeze_runs(text)
    if len(text) <= hard:
        return text
    mark = "\n[… середина пропущена, всего %d знаков …]\n" % len(text)
    head = (hard - len(mark)) * 55 // 100
    return text[:head] + mark + text[len(text) - (hard - len(mark) - head):]


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
    return sum(WEIGHTS[k] * h["axes"][k] for k in WEIGHTS)


def decide(m, h=None):
    """Чистая политика: метрики TypeSafe (+ сигналы эвристики) → (уровень, причины). Без сети и побочных эффектов.
    Эвристика только поднимает нагрузку, может запретить haiku и обязана подтвердить fable."""
    why = []
    v = {k: x[0] for k, x in m.items()}
    min_conf = min(m[k][1] for k in CONF_AXES)
    load_ts = sum(WEIGHTS[k] * v[k] for k in WEIGHTS)
    load_h = heur_load(h) if h else None
    load = load_ts + HEUR_RAISE * max(0.0, load_h - load_ts) if h else load_ts
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
    elif len(h["critical"]) >= H_CRITICAL_OPUS and h["axes"]["complexity"] >= 0.5:
        tier = "opus"
        why.append("слова риска (%s) и заметный объём → opus" % ", ".join(h["critical"]))
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
    return out


def finish(tier, why, source, h, **extra):
    """Общий вид результата: уровень, нужен ли вопрос пользователю, безопасная замена."""
    assert tier in TIERS
    r = {"model": tier, "source": source, "confidence": "низкая" if source == "heuristic" else extra.pop("conf_label", "обычная"),
         "confirm": tier in CONFIRM_TIERS, "fallback": CONFIRM_TIERS.get(tier, tier), "skip": False,
         "reason": "; ".join(why), "signals": compact_signals(h)}
    r.update(extra)
    return r


def fallback(task, h, reason, **extra):
    tier, why = decide_heuristic(h)
    return finish(tier, [reason] + why, "heuristic", h, **extra)


def triage(task, key=None, timeout=TIMEOUT_S):
    """Оценка задачи. TypeSafe недоступен (оплата, ключ, сеть, лимиты, пауза) → уровень по эвристике + notice при необходимости;
    при жёсткой паузе (нет средств, ключ, доступ, потолок расходов) сеть не используется вовсе."""
    h = heur.signals(task)
    key = key or os.environ.get("TYPESAFE_API_KEY")
    if not key:
        return fallback(task, h, "нет TYPESAFE_API_KEY")
    g = guard.status(key)
    if not g["allowed"]:
        return fallback(task, h, "TypeSafe приостановлен (%s)" % g["kind"], paused=g["kind"], notice=g["notice"])
    sent = make_digest(task)
    info = lambda: {"chars": len(task), "sent": len(sent)}
    try:
        try:
            resp = ask_typesafe(sent, key, timeout)
        except urllib.error.HTTPError as e:
            # слишком большой вход (400 max_tokens_exceeded): один повтор с более коротким дайджестом
            if e.code == 400 and "max_tokens" in http_detail(e):
                sent = make_digest(task, RETRY_CHARS)
                resp = ask_typesafe(sent, key, timeout)
            else:
                raise
        m = metrics_from(resp["answers"])
    except urllib.error.HTTPError as e:
        kind, detail, wait = guard.classify_http(e.code, http_detail(e), e.headers)
        if kind == "size":  # не авария и не повод для паузы
            return fallback(task, h, "вход слишком велик для TypeSafe даже после сжатия", input=info())
        notice = guard.record_failure(kind, detail, wait, key)
        return fallback(task, h, "TypeSafe: %s (HTTP %d)" % (kind, e.code), paused=kind, notice=notice, input=info())
    except Exception as e:  # сеть, тайм-аут, разбор ответа: эвристика, а не понижение и не падение
        notice = guard.record_failure("outage", type(e).__name__, None, key)
        return fallback(task, h, "TypeSafe недоступен (%s)" % type(e).__name__, paused="outage", notice=notice)
    tier, why = decide(m, h)
    tokens = resp.get("usage", {}).get("input_tokens")
    min_conf = min(m[k][1] for k in CONF_AXES)
    r = finish(tier, why, "typesafe", h, notice=guard.record_success(tokens),
               conf_label="высокая" if min_conf >= CONF_DOWNGRADE else "средняя" if min_conf >= CONF_ESCALATE else "низкая",
               metrics={k: {"value": round(x[0], 2), "confidence": round(x[1], 2)} for k, x in m.items()},
               domain=domain_from(resp["answers"]), input=info(), tokens=tokens)
    if m["conversational"][0] >= CHAT_SKIP and m["complexity"][0] <= 0.2 and tier in ("haiku", "sonnet"):
        r["skip"] = True  # реплика, а не задача: заметку не добавляем
    return r


def log(task, result):
    """Журнал решений (первые 200 символов, секреты скрыты, права 0600). Пропущенные реплики не пишутся."""
    if not result or result.get("skip") or not result.get("model"):
        return
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": int(time.time()), "id": hashlib.sha1(task.encode("utf-8")).hexdigest()[:10],
               "task": redact(task)[:200], "model": result.get("model"), "source": result.get("source"),
               "reason": result.get("reason"), "metrics": result.get("metrics"), "signals": result.get("signals"),
               "domain": result.get("domain"), "input": result.get("input"), "tokens": result.get("tokens")}
        new = not LOG_PATH.exists()
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if new:
            os.chmod(LOG_PATH, 0o600)
    except OSError:
        pass


def axes_line(result):
    if result.get("metrics"):
        vals = {k: result["metrics"][k]["value"] for k in WEIGHTS}
    else:
        vals = result["signals"]["axes"]
    return ", ".join("%s %.1f" % (AXIS_RU[k], vals[k]) for k in WEIGHTS)


def hook_context(result):
    """Короткая императивная заметка для основной модели: что делать с этим уровнем."""
    tier = result["model"]
    src = ("TypeSafe, уверенность %s" % result.get("confidence", "обычная")) if result.get("source") == "typesafe" \
        else "только эвристика, уверенность низкая"
    kind = (result.get("domain") or {}).get("kind")
    head = "TypeSafe-триаж: уровень %s (%s%s; %s). Причины: %s." % (
        tier, src, ("; тип: %s" % kind) if kind else "", axes_line(result), result.get("reason", ""))
    run = tier
    lines = [head]
    if tier in CONFIRM_TIERS:
        fb = CONFIRM_TIERS[tier]
        lines.append(
            "• %s не запускать без подтверждения. Прежде чем делегировать — AskUserQuestion «Запустить агента на %s?» "
            "с вариантами «Да, %s» / «Нет, %s». Нет явного «да» → работай на %s." % (tier, tier, tier, fb, fb))
        run = "%s (или %s без подтверждения)" % (tier, fb)
    lines += [
        "• Делегируй, если работа содержательная (анализ, проектирование, нетривиальная правка, поиск причины, большой текст) "
        "и уровень выше твоей модели, или задача большая и изолируемая: Agent(model=%s) с самодостаточным промптом "
        "(цель, пути, ограничения, критерии готовности, что вернуть); результат проверь сам." % run,
        "• Иначе (диалог, мелочь, уровень не выше твоего) — делай сам, триаж не упоминай.",
        "• Субагентам скилл typesafe-triage не применять. План SuperPowers: модели ролей — из его Model Selection (model явно), "
        "«most capable» = opus, «cheapest» = sonnet (haiku/fable — только с подтверждения). Проверки (тесты, чтение результата, данные) обязательны; при сомнении — уровень выше.",
    ]
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


HARNESS_PREFIXES = ("<", "[SYSTEM", "[Subagent", "[Request interrupted", "[Image", "Caveat:")


def is_harness_message(prompt):
    """Служебные сообщения среды (уведомления задач, отчёты субагентов, теги) — не запрос пользователя: не отправляем наружу."""
    head = prompt.lstrip()[:200]
    return head.startswith(HARNESS_PREFIXES) or "[Subagent hand-back]" in head or "<task-notification>" in head


def should_skip(prompt):
    """Что вообще не оцениваем (и не отправляем в TypeSafe): короткие реплики, команды, служебные сообщения, болтовня."""
    return (not isinstance(prompt, str) or len(prompt.strip()) < MIN_HOOK_CHARS or prompt.lstrip().startswith("/")
            or is_harness_message(prompt) or heur.is_chatter(prompt))


def run_hook():
    """Хук не должен ни ломать, ни тормозить работу: любая неожиданность = молчание и код 0."""
    try:
        if os.environ.get(CHILD_ENV):
            return 0  # мы внутри агента, запущенного --run: уровень модели уже выбран, советов и второго обращения в TypeSafe не нужно
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            return 0
        prompt = data.get("prompt", "") or ""
        if should_skip(prompt) or switched_off(data.get("cwd")):
            return 0
        result = triage(prompt, timeout=HOOK_TIMEOUT_S)
        log(prompt, result)
        parts, out = [], {}
        if result.get("model") and not result.get("skip"):
            parts.append(hook_context(result))
        if result.get("notice"):  # проблема с TypeSafe: показать пользователю прямо (systemMessage) и поручить сообщить в ответе
            out["systemMessage"] = result["notice"]
            parts.append("ВАЖНО (TypeSafe): в начале ответа одной-двумя строками сообщи пользователю: " + result["notice"])
        if parts:
            out["hookSpecificOutput"] = {"hookEventName": "UserPromptSubmit", "additionalContext": "\n\n".join(parts)}
            print(json.dumps(out))
    except Exception:
        pass
    return 0


def run_selftest(heuristic_only=False):
    """Эталонные задачи. expect: уровень или "skip" (реплика: заметки быть не должно).
    С --heuristic ожидания сводятся к sonnet/opus (запасной вариант других уровней не даёт)."""
    cases = json.loads((Path(__file__).with_name("triage_cases.json")).read_text(encoding="utf-8"))
    ok = under = over = fail = 0
    for c in cases:
        exp, task = c["expect"], c["task"]
        if exp == "skip":
            got_skip = should_skip(task) or (not heuristic_only and triage(task).get("skip"))
            ok, over = ok + bool(got_skip), over + (not got_skip)
            print("%-6s ожид skip   %s | %s" % ("ok" if got_skip else "over", "пропуск" if got_skip else "заметка", task[:60]))
            continue
        if heuristic_only:
            r = fallback(task, heur.signals(task), "офлайн-проверка")
            exp = CONFIRM_TIERS.get(exp, exp)
        else:
            r = triage(task)
            if r.get("source") != "typesafe":
                fail += 1
                print("NOSIG  %-9s %s | %s" % (exp, r.get("reason"), task[:60]))
                continue
        got = r["model"]
        d = TIERS.index(got) - TIERS.index(exp)
        tag = "ok" if d == 0 else "UNDER" if d < 0 else "over"
        ok, under, over = ok + (d == 0), under + (d < 0), over + (d > 0)
        print("%-6s ожид %-6s дано %-6s | %s | %s" % (tag, exp, got, r["reason"], task[:60]))
    print("\nсовпало %d, ниже ожидаемого (опасно) %d, выше (дорого) %d, без сигнала %d, всего %d" % (
        ok, under, over, fail, len(cases)))
    return 1 if under else 0


def build_agent_cmd(tier, readonly=False, budget=None, edit=False, allow=(), confirmed=False):
    """Команда запуска отдельного агента Claude Code на заданном уровне. haiku/fable — только с confirmed=True."""
    if tier not in TIERS:
        raise ValueError("недопустимый уровень модели %r: разрешены %s" % (tier, ", ".join(TIERS)))
    if tier in CONFIRM_TIERS and not confirmed:
        raise ValueError("уровень %s запускается только с явным подтверждением пользователя (--confirmed); без него — %s"
                         % (tier, CONFIRM_TIERS[tier]))
    if readonly and edit:
        raise ValueError("--readonly и --edit несовместимы")
    cmd = ["claude", "-p", "--model", tier, "--append-system-prompt", AGENT_RULES]
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
        elif a in ("--tier", "--budget", "--allow"):
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
    confirmed = "--confirmed" in argv
    forced = opt(argv, "--tier")
    if forced:
        if forced in CONFIRM_TIERS and not confirmed:
            print("Уровень %s запускается только после явного подтверждения пользователя: добавьте --confirmed или выберите %s."
                  % (forced, CONFIRM_TIERS[forced]))
            return 2
        tier, why = forced, "уровень задан вручную"
    else:
        result = triage(task)
        log(task, result)
        if result.get("notice"):
            print(result["notice"], file=sys.stderr)
        tier = result.get("model") or DEFAULT_TIER
        why = result.get("reason") or "рекомендации нет; беру %s по умолчанию" % DEFAULT_TIER
        if result.get("source") == "heuristic":
            why += " (уверенность низкая)"
        if tier in CONFIRM_TIERS and not confirmed:
            why += "; рекомендован %s, но без --confirmed запускаю %s" % (tier, CONFIRM_TIERS[tier])
            tier = CONFIRM_TIERS[tier]
    try:
        cmd = build_agent_cmd(tier, "--readonly" in argv, opt(argv, "--budget"), "--edit" in argv, opts(argv, "--allow"), confirmed)
    except ValueError as e:
        print(e)
        return 2
    print("Агент: %s | %s" % (tier, why), file=sys.stderr)
    if "--dry-run" in argv:
        print(" ".join(cmd[:4]) + " … (задача — через stdin)\n" + task)
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


def main(argv):
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
        d = make_digest(text)
        print("знаков: было %d, уйдёт %d\n---\n%s" % (len(text), len(d), d))
        return 0
    if "--signals" in argv:  # локальные сигналы, без сети
        text = " ".join(a for a in argv[1:] if not a.startswith("--")) or sys.stdin.read()
        h = heur.signals(text)
        tier, why = decide_heuristic(h)
        print(json.dumps({"skip": should_skip(text), "heuristic_tier": tier, "reason": "; ".join(why),
                          "load": round(heur_load(h), 2), "signals": compact_signals(h)}, ensure_ascii=False, indent=2))
        return 0
    if "--check" in argv:
        r = triage("Исправь падение теста test_login: таймаут при вызове сервиса авторизации", timeout=10)
        print(json.dumps({k: r.get(k) for k in ("model", "source", "reason")}, ensure_ascii=False))
        print("python:", sys.version.split()[0], "| ключ:", "есть" if os.environ.get("TYPESAFE_API_KEY") else "НЕТ")
        if r.get("notice"):
            print(r["notice"])
        print(format_status())
        return 0 if r.get("source") == "typesafe" else 1
    if "--hook" in argv:
        return run_hook()
    if "--selftest" in argv:
        return run_selftest("--heuristic" in argv)
    if len(argv) < 2:
        print(__doc__)
        return 2
    task = " ".join(a for a in argv[1:] if not a.startswith("--"))
    result = triage(task)
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
