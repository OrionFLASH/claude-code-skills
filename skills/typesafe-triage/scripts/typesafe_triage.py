# -*- coding: utf-8 -*-
"""Триаж задачи разработки через TypeSafe (Jev): глобальный инструмент Claude Code, не часть чьего-либо проекта.

Описание задачи уходит в TypeSafe одним запросом с несколькими узкими вопросами (шкалы и да/нет).
Из ответов код (не модель) выводит рекомендованный уровень модели Claude Code: haiku / sonnet / opus.

Принципы, чтобы качество разработки не страдало:
  * Fable не рекомендуется никогда (константа TIERS; переключение на него — только вручную).
  * Рекомендация советует; основную модель сессии переключить нельзя (нет механизма), «переключение» = делегирование субагенту с model=: проверки, тесты и ревью от выбора модели не зависят.
  * Вверх — легко, вниз — только при уверенных ответах и низком риске; низкая уверенность = шаг вверх.
  * Нет ключа / сеть / ошибка / таймаут → рекомендации нет (model = null), текущая модель не меняется.
  * Защита от потери доступа и ухода баланса в минус — typesafe_guard.py: нет средств / ключ / доступ → ЖЁСТКАЯ пауза до --resume
    (никаких авто-проб), сбои сервиса → пауза с нарастанием, локальный потолок расходов в месяц, предупреждение пользователю.
  * В TypeSafe уходит только дайджест текста задачи (до HARD_CHARS знаков), без файлов проекта и данных: большие вставки
    (код, логи) сжимаются до начала и конца, сама просьба сохраняется; см. make_digest и команду --digest.
  * Только про разработку ПО: общие вопросы вне кода хук молча пропускает (вопрос `software_dev`).
  * Выключатели: переменная окружения TYPESAFE_TRIAGE=off или файл .typesafe-triage-off в каталоге проекта (или выше).

Запуск (только стандартная библиотека; ключ — переменная окружения TYPESAFE_API_KEY):
    python3 typesafe_triage.py "текст задачи"        # JSON с метриками и рекомендацией
    python3 typesafe_triage.py --hook                # режим хука UserPromptSubmit (stdin = JSON хука)
    python3 typesafe_triage.py --digest "текст"       # показать, что именно уйдёт в TypeSafe (или текст из stdin)
    python3 typesafe_triage.py --status               # пауза, расходы за месяц, потолок
    python3 typesafe_triage.py --resume               # снять паузу после пополнения баланса / исправления ключа
    python3 typesafe_triage.py --pause "причина"      # отключить TypeSafe вручную;  --set-budget USD  месячный потолок расходов
    python3 typesafe_triage.py --check                # диагностика: ключ, сеть, сертификаты
    python3 typesafe_triage.py --selftest            # прогон набора эталонных задач (triage_cases.json)
    python3 typesafe_triage.py --run "текст задачи"  # триаж + запуск отдельного агента `claude -p` на нужной модели
        --readonly          агент только читает и планирует (--permission-mode plan), файлы не правит
        --edit              агент может править файлы в текущем каталоге (--permission-mode acceptEdits); без --edit и --readonly
                            в режиме -p агент не получает права на запись и остановится с просьбой о разрешении (проверено)
        --allow "Bash(git status)"   доп. разрешённый инструмент (--allowedTools); можно несколько раз, например для запуска тестов
        --tier haiku|sonnet|opus   вместо рекомендации TypeSafe (fable отклоняется)
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
MIN_HOOK_CHARS = 40
LOG_PATH = guard.HOME / "log.jsonl"
OFF_MARKER = ".typesafe-triage-off"
CHILD_ENV = "TYPESAFE_TRIAGE_CHILD"   # ставится в окружение агента, запущенного через --run: в нём хук молчит, вложенный --run запрещён

# Fable сюда не входит намеренно: его включает только пользователь вручную.
TIERS = ["haiku", "sonnet", "opus"]

# Пороги. Подбираются по triage_cases.json (--selftest), не «из головы» навсегда.
LOAD_SONNET = 0.25          # нагрузка ниже — кандидат на haiku
LOAD_OPUS = 0.70            # нагрузка от — opus
WEIGHTS = {"complexity": 0.35, "reasoning": 0.25, "ambiguity": 0.20, "risk": 0.20}
CONF_ESCALATE = 0.5         # минимальная уверенность шкал ниже — шаг вверх
CONF_DOWNGRADE = 0.7        # для haiku уверенность должна быть не ниже
AGENT_TIMEOUT_S = 1800
DEFAULT_TIER = "sonnet"     # если рекомендации нет (нет ключа/сети): модель по умолчанию проекта
AGENT_RULES = (
    "Работай по правилам CLAUDE.md репозитория: доработка только в отдельной ветке, в main не коммитить и не вливать "
    "без явного акцепта пользователя. Проверки (тесты, чтение результата, проверка на данных) обязательны. "
    "Модель Fable не использовать. В конце кратко и по-русски доложи, что сделано и что проверено.")
DEV_MIN = 0.5              # software_dev ниже — не разработка ПО, хук молчит
FLAG_ON = 0.6              # порог «да» для флагов Noul (расчёт нагрузки)
HAIKU_FLAG_MIN = 0.8       # read_only/mechanical открывают haiku только при уверенном «да»
PROTECT_FLAG = 0.4         # touches_data_rules/needs_investigation поднимают уровень уже при слабом «да»
HOOK_TIMEOUT_S = 3
# Уверенность считаем по осям, несущим выбор уровня: «неясность» — средний уровень шкалы, её уверенность
# системно низкая (на ясных задачах тоже), в шлюз не входит; её значение учитывается в нагрузке.
CONF_AXES = ("complexity", "reasoning", "risk")

SCORES = {
    "complexity": {
        "instructions": "How large and intricate is the software change this task asks for?",
        "criteria": [
            "No real change: a question, an explanation, a lookup, or a one-line tweak such as a label or constant",
            "Small local change in one file or one function with an obvious way to do it",
            "Change spanning several files or modules that must stay consistent with each other",
            "New feature, redesign or rewrite that needs design decisions and many interacting parts",
        ],
    },
    "reasoning": {
        "instructions": "How much careful reasoning does solving this task need?",
        "criteria": [
            "Mechanical: lookup, rename, formatting, moving things around",
            "Ordinary implementation following existing patterns in the code",
            "Subtle problem: finding a root cause, edge cases, or weighing design trade-offs",
        ],
    },
    "ambiguity": {
        "instructions": "How unclear is what exactly has to be done?",
        "criteria": [
            "Precise: what to change and where is stated",
            "Some gaps that a sensible default would fill",
            "Open-ended: goals unclear, needs exploration, diagnosis or clarifying questions first",
        ],
    },
    "risk": {
        "instructions": "How costly is a silent mistake in doing this task?",
        "criteria": [
            "Nothing is changed or only documentation text",
            "Code change whose result is easy to check by running it or its tests",
            "Change to data-processing or validation rules, deletion, git history or anything hard to undo, where a wrong result could go unnoticed",
        ],
    },
}
FLAGS = {
    "software_dev": "Is this message part of software development work: writing, changing, debugging, reviewing, testing, explaining or planning code, scripts, repositories, builds, issues or technical project tasks (as opposed to a general question, chat, writing or advice unrelated to code)?",
    "read_only": "Does the task only ask to explain, find, summarize or answer, without changing any files?",
    "mechanical": "Is the task a purely mechanical repetitive edit such as renaming, reformatting or moving text, with no decisions to make?",
    "needs_investigation": "Is the cause of a problem unknown, so it must be diagnosed before anything can be fixed?",
    "touches_data_rules": "Does the task change rules that validate, merge, convert or calculate data, where a wrong rule would silently produce wrong results?",
}


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


def metrics_from(answers):
    """Ответы API → {имя: (значение 0..1, уверенность 0..1)}. Шкалы нормируются на верхний уровень."""
    out = {}
    for name in SCORES:
        a = answers[name]
        top = len(SCORES[name]["criteria"]) - 1
        out[name] = (a["score"] / top, a["confidence"])
    for name in FLAGS:
        p = answers[name]["noul"]
        out[name] = (p, abs(2 * p - 1))
    return out


def decide(m):
    """Чистая политика выбора уровня: метрики → (уровень, причины). Без сети и побочных эффектов."""
    why = []
    v = {k: x[0] for k, x in m.items()}
    min_conf = min(m[k][1] for k in CONF_AXES)
    load = sum(WEIGHTS[k] * v[k] for k in WEIGHTS)
    tier = 0 if load < LOAD_SONNET else 1 if load < LOAD_OPUS else 2
    why.append("нагрузка %.2f" % load)

    safe_light = (v["read_only"] >= HAIKU_FLAG_MIN or v["mechanical"] >= HAIKU_FLAG_MIN) and v["risk"] <= 0.5 and v["ambiguity"] <= 0.5
    raised = False  # один шаг вверх за низкую уверенность максимум, не два подряд
    if tier == 0 and not safe_light:
        tier, raised = 1, True
        why.append("haiku только для чтения/механики с низким риском → sonnet")
    if tier == 0 and min_conf < CONF_DOWNGRADE:
        tier, raised = 1, True
        why.append("для haiku нужна уверенность ≥ %.1f (есть %.2f) → sonnet" % (CONF_DOWNGRADE, min_conf))
    if tier < 1 and (v["touches_data_rules"] >= PROTECT_FLAG or v["needs_investigation"] >= PROTECT_FLAG):
        tier = 1
        why.append("правила данных/диагностика → не ниже sonnet")
    if v["touches_data_rules"] >= PROTECT_FLAG and v["complexity"] >= 0.5:
        if tier < 2:
            why.append("правила данных и нетривиальная правка → opus")
        tier = 2
    if min_conf < CONF_ESCALATE and tier < 2 and not raised:
        tier += 1
        why.append("низкая уверенность %.2f → шаг вверх" % min_conf)
    return TIERS[tier], why


def http_detail(e):
    """Тело HTTP-ошибки; читается один раз и кэшируется (поток читается единожды)."""
    if not hasattr(e, "_body_text"):
        try:
            e._body_text = e.read().decode("utf-8", "replace")
        except Exception:
            e._body_text = ""
    return e._body_text


def triage(task, key=None, timeout=TIMEOUT_S):
    """Оценка задачи. Любая проблема с TypeSafe (оплата, ключ, сеть, лимиты) = model None + при необходимости notice для пользователя;
    при жёсткой паузе (нет средств, ключ, доступ, потолок расходов) сеть не используется вовсе."""
    key = key or os.environ.get("TYPESAFE_API_KEY")
    if not key:
        return {"model": None, "reason": "нет TYPESAFE_API_KEY — рекомендации нет"}
    g = guard.status(key)
    if not g["allowed"]:
        return {"model": None, "paused": g["kind"], "notice": g["notice"], "reason": "TypeSafe приостановлен (%s) — рекомендации нет" % g["kind"]}
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
            return {"model": None, "input": info(), "reason": "вход слишком велик для TypeSafe даже после сжатия — рекомендации нет"}
        notice = guard.record_failure(kind, detail, wait, key)
        return {"model": None, "paused": kind, "notice": notice, "input": info(), "reason": "TypeSafe: %s (HTTP %d) — рекомендации нет" % (kind, e.code)}
    except Exception as e:  # сеть, тайм-аут, разбор ответа: «рекомендации нет», а не понижение и не падение
        notice = guard.record_failure("outage", type(e).__name__, None, key)
        return {"model": None, "paused": "outage", "notice": notice, "reason": "TypeSafe недоступен (%s) — рекомендации нет" % type(e).__name__}
    tier, why = decide(m)
    assert tier in TIERS
    tokens = resp.get("usage", {}).get("input_tokens")
    return {"model": tier, "reason": "; ".join(why), "dev": m["software_dev"][0] >= DEV_MIN, "notice": guard.record_success(tokens),
            "metrics": {k: {"value": round(x[0], 2), "confidence": round(x[1], 2)} for k, x in m.items()},
            "input": info(), "tokens": tokens}


def log(task, result):
    """Журнал решений — только для задач разработки (общие запросы не пишутся), права 0600, секреты скрыты."""
    if not result.get("dev"):
        return
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": int(time.time()), "id": hashlib.sha1(task.encode("utf-8")).hexdigest()[:10],
               "task": redact(task)[:200], "model": result.get("model"), "reason": result.get("reason"),
               "metrics": result.get("metrics"), "input": result.get("input"), "tokens": result.get("tokens")}
        new = not LOG_PATH.exists()
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if new:
            os.chmod(LOG_PATH, 0o600)
    except OSError:
        pass


def hook_context(result):
    m = result["metrics"]
    line = ", ".join("%s %.1f" % (k, m[k]["value"]) for k in ("complexity", "reasoning", "ambiguity", "risk"))
    rec = result["model"]
    return (
        "TypeSafe-триаж задачи (совет, не приказ): рекомендованная модель — %s (%s; %s).\n"
        "Как применять: (1) основную сессию Claude Code переключить нельзя ни хуку, ни тебе (механизма нет, только /model "
        "руками), поэтому «переключение» делается делегированием. (2) Если %s выше твоей модели (свою ты знаешь из "
        "системного промпта) и работа содержательная (анализ, проектирование, нетривиальная правка, поиск причины): "
        "выполни её через Agent с model=%s и самодостаточным промптом (цель, пути, ограничения проекта, что вернуть), "
        "результат прочитай и проверь сам; если нужен диалог с пользователем и делегировать нельзя — одной строкой "
        "спроси через AskUserQuestion: продолжить на текущей модели или переключить /model %s. "
        "(3) Мелкие вопросы, подтверждения и реплики — не делегируй и не напоминай. Рекомендация не выше твоей модели — "
        "ничего не предпринимай. (4) Субагентам: если работа идёт по скиллам SuperPowers (subagent-driven-development, executing-plans, dispatching-parallel-agents), модель каждой роли выбирается по их разделу Model Selection (model указывать всегда явно), а этот совет — вход для решения «делегировать ли всё» и нижний ориентир там, где плана нет; «most capable available» понимать как opus, не Fable. Без плана: уровень не ниже рекомендованного, а для содержательных подзадач — не ниже твоей модели (совет оценивает запрос целиком, а не каждую подзадачу). "
        "(5) Fable не использовать и не предлагать. (6) Выбор модели не отменяет проверки: тесты, чтение результата "
        "субагента, проверка на данных; при сомнении — уровень выше." % (rec, result["reason"], line, rec, rec, rec))


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


def run_hook():
    """Хук не должен ни ломать, ни тормозить работу: любая неожиданность = молчание и код 0."""
    try:
        if os.environ.get(CHILD_ENV):
            return 0  # мы внутри агента, запущенного --run: уровень модели уже выбран, советов и второго обращения в TypeSafe не нужно
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            return 0
        prompt = data.get("prompt", "") or ""
        if (not isinstance(prompt, str) or len(prompt) < MIN_HOOK_CHARS or prompt.lstrip().startswith("/")
                or is_harness_message(prompt) or switched_off(data.get("cwd"))):
            return 0
        result = triage(prompt, timeout=HOOK_TIMEOUT_S)
        log(prompt, result)
        parts, out = [], {}
        if result.get("model") and result.get("dev"):
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


def run_selftest():
    cases = json.loads((Path(__file__).with_name("triage_cases.json")).read_text(encoding="utf-8"))
    ok = under = over = fail = 0
    for c in cases:
        r = triage(c["task"])
        got = r.get("model")
        if c["expect"] == "none":  # не разработка ПО: хук обязан промолчать
            good = got is not None and not r["dev"]
            ok, fail = ok + good, fail + (got is None)
            under += (got is not None and r["dev"])
            print("%-6s ожид none   дано %-6s | dev=%s | %s" % ("ok" if good else "UNDER" if got else "NOSIG", got, r.get("dev"), c["task"][:60]))
            continue
        if got is None:
            fail += 1
            print("NOSIG  %-9s %s" % (c["expect"], c["task"][:70]))
            continue
        if not r["dev"]:  # задача разработки, но хук промолчал бы — это провал классификации
            under += 1
            print("DEVMISS %s" % c["task"][:70])
            continue
        d = TIERS.index(got) - TIERS.index(c["expect"])
        tag = "ok" if d == 0 else "UNDER" if d < 0 else "over"
        ok, under, over = ok + (d == 0), under + (d < 0), over + (d > 0)
        print("%-6s ожид %-6s дано %-6s | %s | %s" % (tag, c["expect"], got, r["reason"], c["task"][:60]))
    print("\nсовпало %d, ниже ожидаемого (опасно) %d, выше (дорого) %d, без сигнала %d, всего %d" % (
        ok, under, over, fail, len(cases)))
    return 1 if under else 0


def build_agent_cmd(tier, readonly=False, budget=None, edit=False, allow=()):
    """Команда запуска отдельного агента Claude Code на заданном уровне. Уровень — только из TIERS (Fable исключён)."""
    if tier not in TIERS:
        raise ValueError("недопустимый уровень модели %r: разрешены %s" % (tier, ", ".join(TIERS)))
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
    forced = opt(argv, "--tier")
    if forced:
        tier, why = forced, "уровень задан вручную"
    else:
        result = triage(task)
        log(task, result)
        if result.get("notice"):
            print(result["notice"], file=sys.stderr)
        tier = result.get("model") or DEFAULT_TIER
        why = result["reason"] if result.get("model") else result["reason"] + "; беру %s по умолчанию" % DEFAULT_TIER
    try:
        cmd = build_agent_cmd(tier, "--readonly" in argv, opt(argv, "--budget"), "--edit" in argv, opts(argv, "--allow"))
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
        print("TypeSafe отключён вручную. Включить: --resume")
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
    if "--check" in argv:
        r = triage("Исправь падение теста test_login: таймаут при вызове сервиса авторизации", timeout=10)
        print(json.dumps({k: r.get(k) for k in ("model", "dev", "reason")}, ensure_ascii=False))
        print("python:", sys.version.split()[0], "| ключ:", "есть" if os.environ.get("TYPESAFE_API_KEY") else "НЕТ")
        if r.get("notice"):
            print(r["notice"])
        print(format_status())
        return 0 if r.get("model") else 1
    if "--hook" in argv:
        return run_hook()
    if "--selftest" in argv:
        return run_selftest()
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
