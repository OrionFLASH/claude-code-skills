# -*- coding: utf-8 -*-
"""Дешёвые локальные сигналы о задаче по самому тексту: без сети, без зависимостей, детерминированно, ~1 мс.

Зачем. TypeSafe отвечает на узкие вопросы, но (а) бывает недоступен (нет ключа, сеть, пауза защиты) и (б) не видит
того, что легко посчитать кодом: длину, число пунктов и файлов, наличие кода и логов, слова про продакшн, деньги,
безопасность, необратимость. Эти сигналы:
  * при ответе TypeSafe — только ПОДНИМАЮТ нагрузку (вверх легко) и могут запретить haiku / разрешить fable;
  * без TypeSafe — единственный источник уровня (запасной вариант: только sonnet или opus, уверенность низкая).

Все словари и пороги — константы ниже; меняются вместе с `--selftest --heuristic` (triage_cases.json).
Публичное API: signals(text) -> dict, is_chatter(text) -> bool.
"""
import re

FLAGS_RE = re.I | re.U

# Слова: русские основы + английские. Совпадение по началу слова, чтобы «удалить» и «удали» попадали одинаково.
CRITICAL_GROUPS = {
    "production": r"\bпрод\b|\bпродакшн|\bпродуктив|\bбоев|\bproduction\b|\bprod\b|\blive (?:site|system|data|database)",
    "irreversible": (r"необратим|безвозврат|irreversib|cannot be undone|force.?push|drop (?:table|database)|rm -rf|truncate"
                     r"|удал\w* (?:вс\w*|баз\w*|ветк\w*|репозитор\w*|аккаунт\w*|данн\w*|таблиц\w*|истори\w*|бэкап\w*)"
                     r"|delete (?:all|the database|the branch|the repo|account|data|history)|\bмиграц|\bmigrat|переезд"),
    "security": (r"безопасн|уязвим|\bsecurity\b|vulnerab|\bauth\b|аутентифик|авторизац|прав\w* доступа|\bpermission|\bсекрет"
                 r"|шифров|encrypt|\bcrypto|\bпарол|\bpassword|\boauth|\bsso\b|\bcve-"),
    "money": (r"\bденьг|\bденеж|платеж|платёж|\bоплат|\bpayment|\bbilling|\binvoice|\bсчёт|\bсчет\w* на оплат|бюджет"
              r"|\bbudget|финанс|financ|\bналог|\btax\b|бухгалт|accounting|зарплат|payroll|\bбанк|\bbank|\bтранзакц|transaction"),
    "legal_medical": (r"юридич|\blegal\b|\bдоговор(?:а|у|ом|е|ы|ов|ами|ах)?\b|\bcontract\b|лицензи|licens|медицин|medical|\bдиагноз|\bgdpr|персональн\w* данн"
                      r"|\bpii\b|compliance|регулятор|152-фз|\bсуд\b|\bиск\b"),
    "data_loss": (r"данн\w* (?:клиент|пользовател|заказчик)|customer data|user data|\bбэкап|\bbackup|резервн\w* коп"
                  r"|потер\w* данн|data loss|без простоя|zero.?downtime"),
}
DEEP_RE = re.compile(
    r"\bпочему|\bзачем|\bwhy\b|как (?:устроен|работает|это работает)|how (?:does|do) .{0,40}work|\bпричин|root cause|разбер\w*ся"
    r"|\binvestigat|исследу|исследован|\bresearch|спроектир|проектирован|\bdesign\b|архитектур|architect|стратеги|strateg|гипотез|hypothes"
    r"|\bсравни|\bcompare|trade.?off|компромисс|\bоцени\b|\bevaluat|\bassess|доказ|\bprove\b|оптимиз|optimi[sz]"
    r"|рефактор|refactor|переделай|перестр|redesign|rewrite|перепиш|продума|think through|анализ|analy[sz]|диагност|\bdebug|прогноз|forecast"
    r"|отлад|утечк|\bleak|race condition|гонк\w* данн|deadlock|взаимоблок|производительн|performance|узк\w* мест|bottleneck"
    r"|модель данных|модель правил|data model|финансов\w* модел|спецификац|specification|\bплан\w* (?:миграц|переход|внедрен|проект)|\bаудит|\baudit"
    r"|обоснова|justif|\bреализуй|\bimplement|обратн\w* совместим|backward.?compat|\bриск|\brisk",
    FLAGS_RE)
LIGHT_RE = re.compile(
    r"переименуй|\brename|\bвыведи|\bпокажи|\bshow\b|\blist\b|перечисли|\bсписок|найди,? где|where is|\bгде (?:лежит|находится|задаётся|задается)"
    r"|\bпосчитай|\bcount\b|отформатируй|\bformat\b|опечатк|\btypo|замени .{1,60} на|\breplace\b|переведи|\btranslate|сократи"
    r"|орфограф|\bspell|скопируй|\bcopy\b|\bпросто\b|\bjust\b|\bonly\b|\bтолько\b|одн\w* строк|one line|без изменений|ничего не меняй"
    r"|больше ничего|\bнапомни|\bremind|\bчто такое|what is\b|как называется|\bопредели (?:тип|формат)",
    FLAGS_RE)
STEP_RE = re.compile(
    r"\bзатем\b|\bпотом\b|после этого|\bдалее\b|\bшаг\w*\b|\bэтап\w*\b|\bthen\b|after that|\bstep\b|\bsteps\b|\bphase|во-первых|во-вторых"
    r"|\bfirst,|\bsecond,|\bfinally\b|в конце|\bи ещё\b|\bа также\b|\bas well as\b|\balso\b|\bтакже\b",
    FLAGS_RE)
ITEM_RE = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+\S", re.M)
PATH_RE = re.compile(
    r"(?:[\w.-]+/)+[\w.-]+|\b[\w-]+\.(?:py|js|ts|tsx|jsx|mjs|md|json|ya?ml|sql|csv|xlsx?|docx?|pdf|pptx?|html?|css|scss|go|rs|java"
    r"|kt|swift|rb|php|sh|ps1|toml|ini|cfg|txt|ipynb|c|h|cpp|hpp|cs|vue|svelte|tf|lock)\b", FLAGS_RE)
LOG_RE = re.compile(r"traceback|exception|\berror\b|\bfatal\b|\bpanic\b|stack ?trace|\bat [\w.$]+\(|\bошибк|\bпадает|\bупал", FLAGS_RE)
CODE_LINE_RE = re.compile(r"^\s*(?:def |class |function |const |let |var |import |from \S+ import|return\b|if \(|for \(|\}|\{|<\w+[ >]|SELECT\b|#include)",
                          re.M)
FENCE_RE = re.compile(r"```.*?```", re.S)
CHATTER_RE = re.compile(
    r"^\s*(?:спасибо|благодарю|отлично|супер|класс|круто|ок(?:ей)?|окей|хорошо|понял[аи]?|ясно|принято|согласен|согласна|да|нет|ага"
    r"|давай(?:те)?|продолжай(?:те)?|продолжим|дальше|go on|go ahead|continue|thanks|thank you|great|ok(?:ay)?|yes|no|sure|cool|nice"
    r"|perfect|got it|sounds good)\b", FLAGS_RE)
WORK_RE = re.compile(  # глаголы-поручения: если они есть, реплика уже не «болтовня»
    r"\b(?:сделай|напиши|исправь|почини|добавь|удали|перепиши|переделай|проверь|найди|создай|настрой|запусти|разбер|объясни|опиши"
    r"|составь|подготовь|посчитай|сравни|спроектир|реализуй|обнови|write|fix|add|remove|delete|create|check|find|build|implement"
    r"|update|explain|prepare|compare|design|refactor|review|run)\w*", FLAGS_RE)

CRITICAL_RES = {k: re.compile(v, FLAGS_RE) for k, v in CRITICAL_GROUPS.items()}

# Нормировки «сырых» счётчиков в 0..1
SIZE_FROM, SIZE_TO = 150, 1500     # знаков прозы: короче — 0, длиннее — 1
ITEMS_FULL = 8                     # столько пунктов списка = максимум структуры
PATHS_FULL = 5                     # столько разных файлов/путей = максимум ширины
STEPS_FULL = 4                     # столько слов-связок шагов = максимум многошаговости
CLAUSES_FULL = 6                   # столько запятых/двоеточий сверх одной = максимум перечисленных требований
CHATTER_MAX_CHARS = 160            # длиннее — уже не реплика, даже если начинается со «спасибо»
MAX_CHARS = 100000                 # сверхдлинный ввод: считаем по началу и концу (скорость регулярных выражений)


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def is_chatter(text):
    """Короткая реплика/подтверждение без поручения («спасибо, давай дальше», «ок, продолжай») — не задача."""
    t = (text or "").strip()
    return len(t) <= CHATTER_MAX_CHARS and bool(CHATTER_RE.match(t)) and not WORK_RE.search(t)


def signals(text):
    """Текст задачи → сырые счётчики + оценки по осям (0..1) + собственная «нагрузка» эвристики.
    Оси совпадают с вопросами TypeSafe: complexity, reasoning, ambiguity, risk, breadth."""
    text = text or ""
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS * 6 // 10] + "\n" + text[-MAX_CHARS * 4 // 10:]
    fences = FENCE_RE.findall(text)
    prose = FENCE_RE.sub(" ", text)
    lines = [ln for ln in prose.split("\n") if ln.strip()]
    code_lines = len(CODE_LINE_RE.findall(prose)) + sum(f.count("\n") for f in fences)
    log_hits = len(LOG_RE.findall(text))
    # длинные серии строк (вставленный лог/вывод) не считаем «прозой» задачи
    prose_chars = sum(len(ln) for ln in lines if len(ln) < 400) if len(lines) < 40 else sum(len(ln) for ln in lines[:20] + lines[-5:])
    items = len(ITEM_RE.findall(prose))
    paths = len({p.lower() for p in PATH_RE.findall(text) if not p.lower().startswith(("http", "www."))})
    steps = len(STEP_RE.findall(prose))
    deep = len(DEEP_RE.findall(prose))
    light = len(LIGHT_RE.findall(prose))
    critical = sorted(k for k, rx in CRITICAL_RES.items() if rx.search(prose))
    question = prose.rstrip().endswith("?")
    has_code = bool(fences) or code_lines >= 3
    has_logs = log_hits >= 3 or "traceback" in text.lower()

    size = clamp((prose_chars - SIZE_FROM) / float(SIZE_TO - SIZE_FROM))
    clauses = prose.count(",") + prose.count(";") + prose.count(":")
    structure = max(clamp(items / float(ITEMS_FULL)), clamp(steps / float(STEPS_FULL)), clamp((clauses - 1) / float(CLAUSES_FULL)))
    width = clamp(paths / float(PATHS_FULL))
    deep_s = clamp(deep / 2.0)
    light_s = 1.0 if light and not deep else 0.0
    crit_s = clamp(len(critical) / 2.0)

    axes = {
        "complexity": clamp(0.10 + 0.30 * size + 0.35 * structure + 0.10 * width + 0.25 * deep_s - 0.15 * light_s),
        "reasoning": clamp(0.20 + 0.55 * deep_s + 0.15 * has_logs + 0.15 * structure - 0.20 * light_s),
        "ambiguity": clamp(0.30 + (0.20 if deep and prose_chars < 200 else 0.0) - 0.15 * light_s),
        "risk": clamp(0.10 + 0.60 * crit_s + (0.10 if "irreversible" in critical else 0.0) - 0.05 * light_s),
        "breadth": clamp(0.10 + 0.50 * width + 0.25 * size + 0.15 * (has_code or has_logs)),
    }
    return {
        "chars": len(text), "prose_chars": prose_chars, "items": items, "paths": paths, "steps": steps,
        "clauses": clauses, "deep": deep, "light": light, "critical": critical, "question": question,
        "has_code": has_code, "has_logs": has_logs, "chatter": is_chatter(text), "axes": axes,
    }
