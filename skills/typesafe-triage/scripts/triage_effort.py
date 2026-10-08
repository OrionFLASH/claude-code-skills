# -*- coding: utf-8 -*-
"""Вторая ось триажа — reasoning effort (глубина размышления): low < medium < high < xhigh < max.

Модель (haiku/sonnet/opus/fable) — это СПОСОБНОСТЬ исполнителя, effort — сколько ему ДУМАТЬ над этой задачей.
Оси независимы: effort не выводится из модели и наоборот; связаны только правилами согласованности (слой e).

Слои оценки (каждый пишет свой вклад в reasons — прозрачно):
  a) TypeSafe: шкалы рассуждения/неясности/риска/сложности + узкие вопросы effort (проверка результата, план из зависимых
     шагов, поиск неизвестного, цена поверхностного ответа, жёсткие ограничения, согласование частей) — тот же запрос;
  b) текст (triage_heuristics): намерение, требования, критерии приёмки, ограничения, неопределённость, диагностика,
     критичность, объём, математика, логи — только ПОДНИМАЕТ оценку TypeSafe (доля EFF_HEUR_RAISE);
  c) окружение (env_context): git-репозиторий, тесты/CI/lock-файлы, порядок числа файлов, маркер .typesafe-triage-effort —
     локально, без чтения содержимого файлов проекта, в TypeSafe не уходит; вклад ≤ ENV_MAX_BUMP;
  d) история сессии (журнал log.jsonl по session): подряд идущие повторы/неудачи → +1 ступень за повтор, потолок
     HISTORY_MAX_STEPS (модель — +1 только после HISTORY_MODEL_AFTER повторов и не выше opus);
  e) согласованность модель × effort (haiku ≤ high, fable ≥ high, риск → ≥ high, механика → ≤ medium, opus+low только
     для объёмной механики);
  f) без TypeSafe — только b→c→d, уверенность низкая, полоса medium..xhigh (ни low, ни max);
  g) калибровка — typesafe_triage.py --calibrate (triage_cases.json + журнал).
Явные указания пользователя (directives в triage_heuristics) — согласие и приоритет над автооценкой.

Полоса без вопросов: medium..xhigh. low и max — только с подтверждения (CONFIRM_EFFORTS); без него low→medium, max→xhigh.
Только стандартная библиотека, без сети.
"""
import hashlib
import json
import os
import time
from pathlib import Path

EFFORTS = ["low", "medium", "high", "xhigh", "max"]
DEFAULT_EFFORT = "high"            # если оценки нет совсем
# Крайние уровни — только с подтверждения пользователя (AskUserQuestion); значение — ближайший безопасный.
CONFIRM_EFFORTS = {"low": "medium", "max": "xhigh"}
# xhigh по умолчанию без вопроса (только предупреждение о расходе). Чтобы спрашивать и его — добавьте эту пару в
# CONFIRM_EFFORTS (safe_effort пройдёт цепочку max → xhigh → high).
OPTIONAL_CONFIRM_EFFORTS = {"xhigh": "high"}
COSTLY_EFFORTS = ("xhigh", "max")  # в заметке — предупреждение о расходе токенов и времени
# Проверено живьём (claude 2.1.292, `claude -p --model <m> --effort <e>`, промпт «ответь ok»): CLI принимает все пять уровней
# на haiku, sonnet и opus (рост thinking-токенов на sonnet/opus заметен на xhigh/max; на haiku различие не выражено).
# fable живьём не проверялся (дорого) — считаем, что поддерживает всё. Неизвестный уровень CLI молча игнорирует
# (предупреждение и effort по умолчанию), поэтому значения проверяем сами (build_agent_cmd).
MODEL_EFFORTS = {"haiku": EFFORTS, "sonnet": EFFORTS, "opus": EFFORTS, "fable": EFFORTS}

# ---------- a) веса вопросов TypeSafe в «глубине» (0..1); отсутствующие ответы — веса перенормируются ----------
EFFORT_WEIGHTS = {
    "reasoning": 0.26, "shallow_cost": 0.16, "planning": 0.10, "ambiguity": 0.08, "risk": 0.08, "complexity": 0.04,
    "verification": 0.08, "exploration": 0.05, "constraints": 0.04, "coordination": 0.04, "needs_investigation": 0.03,
    "novel_design": 0.04,
}
# Пороги «глубина → уровень» (нижняя граница уровня). Подобраны --calibrate на обучающей части кейсов.
EFFORT_CUTS = {"medium": 0.22, "high": 0.45, "xhigh": 0.70, "max": 0.84}
EFF_HEUR_RAISE = 0.5               # доля превышения «текст над TypeSafe», добавляемая к глубине (вниз текст не тянет)
LOW_TS_MAX = 0.18                  # low: глубина TypeSafe не выше …
LOW_TEXT_MAX = 0.30                # … и глубина текста не выше, нет диагностики/критичности/«глубоких» слов
CONF_LOW = 0.6                     # для low уверенность осей не ниже
MAX_CONF = 0.7                     # для max уверенность не ниже, плюс признак критичности (риск наверху / необратимость)
MAX_TEXT_MIN = 0.45                # … и текст согласен (слова критичности или глубина текста не ниже)
EFF_CONF_ESCALATE = 0.5            # низкая уверенность у границы (≤ EFF_ESC_MARGIN) → +1 ступень (не в max)
EFF_ESC_MARGIN = 0.06
# ---------- e) согласованность модель × effort ----------
HAIKU_EFFORT_MAX = "high"          # haiku не получает xhigh/max (кроме явного указания пользователя)
FABLE_EFFORT_MIN = "high"          # fable по умолчанию не ниже high
RISK_EFFORT_MIN = "high"           # при риске ≥ RISK_EFFORT_AT (или необратимости ≥ FLAG_ON) — не ниже high при любой модели
RISK_EFFORT_AT = 0.67
MECHANICAL_EFFORT_MAX = "medium"   # чисто механическая работа — не выше medium даже на opus (если риск невысок)
MECH_FLAG = 0.8
FLAG_ON = 0.6
HEAVY_LOW_BREADTH = 0.67           # opus/fable + low — только для объёмной (breadth ≥ …) механики
# ---------- f) без TypeSafe ----------
H_EFFORT_BAND = ("medium", "xhigh")
ROUTINE_INTENTS = {"lookup", "transform", "explain", "write"}   # без TypeSafe: рутина → medium, иначе по умолчанию high
H_MEDIUM_MAX = 0.35                # … если глубина текста ниже и нет диагностики/слов риска
H_XHIGH = 0.45                     # xhigh: глубина текста от этого И (≥ 2 групп риска ИЛИ риск + тяжёлое намерение)
H_XHIGH_INTENT = 0.65
UNCERTAIN_OPEN = 2                 # столько слов неопределённости («не уверен», «или») — задача открытая, не рутина
# ---------- c) окружение ----------
ENV_MARKER = ".typesafe-triage-effort"   # файл в каталоге проекта (или выше): первое слово — пол effort для проекта
ENV_MAX_FILES = 3000               # считаем файлы не дальше этого (порядок величины), не дольше ENV_MAX_S
ENV_MAX_S = 0.15
ENV_LARGE_FILES = 1000             # от стольких файлов проект «большой»
ENV_LARGE_BUMP = 0.04              # большой проект + работа над ним → глубже
ENV_NOTESTS_BUMP = 0.03            # репозиторий без тестов/CI + правка → проверить нечем, думать аккуратнее
ENV_MAX_BUMP = 0.06
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".tox", ".mypy_cache", ".idea", "target"}
TEST_MARKS = ("tests", "test", "__tests__", "spec", "pytest.ini", "tox.ini", "conftest.py", "jest.config.js", "vitest.config.ts")
CI_MARKS = (".github/workflows", ".gitlab-ci.yml", ".circleci", "Jenkinsfile", "azure-pipelines.yml", ".travis.yml")
LOCK_MARKS = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "go.sum", "Pipfile.lock", "uv.lock",
              "Gemfile.lock", "composer.lock")
# ---------- d) история ----------
HISTORY_WINDOW_S = 2 * 3600        # учитываем записи сессии за это время
HISTORY_TAIL_BYTES = 256 * 1024    # читаем только хвост журнала
HISTORY_MAX_STEPS = 2              # потолок эскалации effort за счёт истории (ступеней) — защита от бесконечного роста
HISTORY_AUTO_CEIL = "xhigh"        # история сама не поднимает до max (max — только с подтверждения)
HISTORY_MODEL_AFTER = 2            # модель +1 ступень только со второго подряд повтора, не выше opus
SAME_PROMPT_IS_RETRY = True        # тот же запрос (тот же хеш) в сессии — повтор


def idx(e):
    return EFFORTS.index(e)


def step(e, d):
    return EFFORTS[max(0, min(len(EFFORTS) - 1, idx(e) + d))]


def at_least(e, floor):
    return e if idx(e) >= idx(floor) else floor


def at_most(e, ceil):
    return e if idx(e) <= idx(ceil) else ceil


def safe_effort(e, confirm=None):
    """Ближайший уровень, не требующий подтверждения (цепочка, если пользователь добавил xhigh в CONFIRM_EFFORTS)."""
    confirm = CONFIRM_EFFORTS if confirm is None else confirm
    seen = set()
    while e in confirm and e not in seen:
        seen.add(e)
        e = confirm[e]
    return e


def level_from_depth(d, cuts=None):
    cuts = cuts or EFFORT_CUTS
    lvl = "low"
    for name in ("medium", "high", "xhigh", "max"):
        if name in cuts and d >= cuts[name]:
            lvl = name
    return lvl


def ts_depth(m):
    """Глубина по ответам TypeSafe: взвешенная сумма доступных метрик (вес отсутствующих перенормируется)."""
    have = {k: w for k, w in EFFORT_WEIGHTS.items() if k in m}
    total = sum(have.values())
    if not total:
        return None, {}
    parts = {k: m[k][0] * w / total for k, w in have.items()}
    return sum(parts.values()), parts


# ---------- c) окружение ----------
def _find_root(start):
    d = start
    for _ in range(25):
        if (d / ".git").exists():
            return d
        if d.parent == d:
            return None
        d = d.parent
    return None


def env_context(cwd=None):
    """Дёшево и локально: репозиторий, тесты, CI, lock-файлы, порядок числа файлов, маркер effort. Содержимое файлов
    проекта не читается (кроме первого слова нашего маркера). Ничего из этого не уходит в TypeSafe."""
    out = {"repo": False, "tests": False, "ci": False, "lock": False, "files": None, "marker": None}
    try:
        start = Path(cwd or os.getcwd()).resolve()
        for p in [start, *start.parents]:
            mk = p / ENV_MARKER
            if mk.is_file():
                word = (mk.read_text(encoding="utf-8", errors="replace")[:40].split() or [""])[0].lower()
                out["marker"] = word if word in EFFORTS else None
                break
        root = _find_root(start)
        if root is None or root == Path.home():
            return out
        out["repo"] = True
        out["tests"] = any((root / x).exists() for x in TEST_MARKS)
        out["ci"] = any((root / x).exists() for x in CI_MARKS)
        out["lock"] = any((root / x).exists() for x in LOCK_MARKS)
        n, t0 = 0, time.time()
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS]
            n += len(filenames)
            if n >= ENV_MAX_FILES or time.time() - t0 > ENV_MAX_S:
                break
        out["files"] = n
    except (OSError, ValueError):
        pass
    return out


def env_adjust(env, works_on_project):
    """→ (прибавка к глубине, причины). Окружение само effort не задаёт, только слегка уточняет работу над проектом."""
    bump, why = 0.0, []
    if env and env.get("repo") and works_on_project:
        if (env.get("files") or 0) >= ENV_LARGE_FILES:
            bump += ENV_LARGE_BUMP
            why.append("большой проект (≥%d файлов) +%.2f" % (ENV_LARGE_FILES, ENV_LARGE_BUMP))
        if not env.get("tests") and not env.get("ci"):
            bump += ENV_NOTESTS_BUMP
            why.append("нет тестов/CI — проверить нечем +%.2f" % ENV_NOTESTS_BUMP)
        elif env.get("tests"):
            why.append("есть тесты — проверь ими")
    return min(bump, ENV_MAX_BUMP), why


# ---------- d) история ----------
def session_tag(session_id):
    return hashlib.sha1(session_id.encode("utf-8")).hexdigest()[:12] if session_id else None


def read_history(log_path, session, now=None):
    """Записи журнала этой сессии за HISTORY_WINDOW_S (только хвост файла). Нет сессии/файла — []."""
    if not session:
        return []
    now = time.time() if now is None else now
    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - HISTORY_TAIL_BYTES))
            raw = f.read().decode("utf-8", "replace").split("\n")
    except OSError:
        return []
    out = []
    for ln in raw:
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if (isinstance(rec, dict) and rec.get("session") == session and rec.get("model")   # 2.2: пропуски (skipped) — не история
                and now - rec.get("ts", 0) <= HISTORY_WINDOW_S):
            out.append(rec)
    return out


def history_escalation(records, retry_now, prompt_id=None):
    """→ (ступени effort, ступени модели, причины). Считаются подряд идущие повторы, заканчивающиеся текущим запросом.
    Потолок HISTORY_MAX_STEPS — сколько бы раз подряд ни было «опять не работает»."""
    same = SAME_PROMPT_IS_RETRY and prompt_id and any(r.get("id") == prompt_id for r in records)
    if not (retry_now or same):
        return 0, 0, []
    streak = 1
    for r in reversed(records):
        if r.get("retry"):
            streak += 1
        else:
            break
    e_steps = min(streak, HISTORY_MAX_STEPS)
    m_steps = 1 if streak >= HISTORY_MODEL_AFTER else 0
    why = ["история: %s, повтор №%d подряд → effort +%d%s" % (
        "тот же запрос" if same and not retry_now else "признаки неудачи/повтора", streak, e_steps,
        ", модель +1" if m_steps else "")]
    if streak > HISTORY_MAX_STEPS:
        why.append("потолок эскалации за сессию %d ступени" % HISTORY_MAX_STEPS)
    return e_steps, m_steps, why


# ---------- основная политика ----------
def _conf_label(c):
    return "высокая" if c >= 0.7 else "средняя" if c >= 0.5 else "низкая"


def decide_effort(m, h, tier, env=None, hist=(0, 0, []), d=None, min_conf=None):
    """Чистая политика effort. m — метрики TypeSafe (или None = запасной вариант), h — сигналы текста, tier — уже выбранная
    модель (только для правил согласованности), env — env_context, hist — history_escalation, d — directives.
    → dict: effort, effort_confidence, effort_confirm, effort_fallback, effort_source, effort_reasons, effort_depth, layers."""
    why, layers = [], {}
    he = h["effort"]
    depth_h = he["depth"]
    v = {k: x[0] for k, x in (m or {}).items()}
    if m:
        depth_ts, parts = ts_depth(m)
        top = sorted(parts.items(), key=lambda kv: -kv[1])[:3]
        why.append("a) TypeSafe %.2f (%s)" % (depth_ts, ", ".join("%s %.2f" % kv for kv in top)))
        raise_h = EFF_HEUR_RAISE * max(0.0, depth_h - depth_ts)
        depth = depth_ts + raise_h
        why.append("b) текст %.2f%s" % (depth_h, (" → +%.2f" % raise_h) if raise_h >= 0.005 else " (не выше — не влияет)"))
        layers.update(typesafe=round(depth_ts, 3), text=round(raise_h, 3))
        source, conf = "typesafe", (min_conf if min_conf is not None else 1.0)
    else:
        depth, depth_ts, source, conf = depth_h, None, "heuristic", 0.0
        why.append("f) без TypeSafe: глубина по тексту %.2f" % depth_h)
        layers.update(text=round(depth_h, 3))
    works = bool(he["intents"] and set(he["intents"]) & {"fix", "migrate", "optimize", "design", "write", "diagnose"}) \
        or h["paths"] or h["has_code"]
    bump, ewhy = env_adjust(env, works and v.get("read_only", 0) < FLAG_ON)
    if bump or ewhy:
        depth += bump
        why.append("c) окружение: " + ", ".join(ewhy))
        layers["env"] = round(bump, 3)
    if m:
        e = level_from_depth(depth)
        # low — только уверенно лёгкое: и TypeSafe, и текст
        if e == "low" and not (depth_ts <= LOW_TS_MAX and depth_h <= LOW_TEXT_MAX and conf >= CONF_LOW and not he["diag"]
                               and not h["critical"] and not h["deep"]):
            e = "medium"
            why.append("low только для уверенно лёгкого → medium")
        crit = v.get("risk", 0) >= 0.9 or v.get("irreversible", 0) >= 0.8
        if e == "max" and not (crit and conf >= MAX_CONF and (h["critical"] or depth_h >= MAX_TEXT_MIN)):
            e = "xhigh"
            why.append("max только при критичности, уверенности ≥ %.1f и согласии текста → xhigh" % MAX_CONF)
        nxt = next((c for n, c in sorted(EFFORT_CUTS.items(), key=lambda kv: kv[1]) if c > depth), None)
        if conf < EFF_CONF_ESCALATE and nxt is not None and nxt - depth <= EFF_ESC_MARGIN and e not in ("xhigh", "max"):
            e = step(e, 1)
            why.append("низкая уверенность у границы → +1")
    else:
        # при сомнении — high (середина полосы), medium — только явная рутина, xhigh — только явный риск + глубина
        routine = set(he["intents"]) <= ROUTINE_INTENTS and not he["diag"] and not h["critical"] and he["uncertain"] < UNCERTAIN_OPEN
        top_intent = he["parts"]["intent"]
        if routine and depth < H_MEDIUM_MAX:
            e = "medium"
            why.append("рутина (%s) → medium" % ("/".join(he["intents"]) or "без сложных намерений"))
        elif depth >= H_XHIGH and (len(h["critical"]) >= 2 or (h["critical"] and top_intent >= H_XHIGH_INTENT)):
            e = "xhigh"
            why.append("риск (%s) и глубина → xhigh" % ", ".join(h["critical"]))
        else:
            e = "high"
            why.append("не рутина%s → high" % ((": риск " + ", ".join(h["critical"])) if h["critical"] else ""))
        e = at_most(at_least(e, H_EFFORT_BAND[0]), H_EFFORT_BAND[1])
    # e) согласованность модель × effort
    risky = v.get("risk", 0) >= RISK_EFFORT_AT or v.get("irreversible", 0) >= FLAG_ON or (not m and len(h["critical"]) >= 2)
    routine_text = set(he["intents"]) <= ROUTINE_INTENTS and not he["diag"] and not h["critical"] and he["uncertain"] < UNCERTAIN_OPEN
    mech = (v.get("mechanical", 0) >= MECH_FLAG or (not m and h["light"] and not h["deep"] and routine_text)) and not he["diag"]
    if mech and not risky and idx(e) > idx(MECHANICAL_EFFORT_MAX):
        e = MECHANICAL_EFFORT_MAX
        why.append("e) механическая работа → не выше %s" % MECHANICAL_EFFORT_MAX)
    if risky and idx(e) < idx(RISK_EFFORT_MIN):
        e = RISK_EFFORT_MIN
        why.append("e) высокая цена ошибки → не ниже %s" % RISK_EFFORT_MIN)
    if tier == "haiku" and idx(e) > idx(HAIKU_EFFORT_MAX):
        e = HAIKU_EFFORT_MAX
        why.append("e) haiku → не выше %s" % HAIKU_EFFORT_MAX)
    if tier == "fable" and idx(e) < idx(FABLE_EFFORT_MIN):
        e = FABLE_EFFORT_MIN
        why.append("e) fable → не ниже %s" % FABLE_EFFORT_MIN)
    if tier in ("opus", "fable") and e == "low" and not (mech and v.get("breadth", 0) >= HEAVY_LOW_BREADTH):
        e = "medium"
        why.append("e) %s + low только для объёмной механики → medium" % tier)
    # d) история
    e_steps, _, hwhy = hist
    if e_steps:
        before = e
        e = step(e, e_steps)
        if idx(e) > idx(HISTORY_AUTO_CEIL) and idx(before) <= idx(HISTORY_AUTO_CEIL):
            e = HISTORY_AUTO_CEIL
        why.append("d) " + "; ".join(hwhy) + " (%s → %s)" % (before, e))
        layers["history"] = e_steps
    # явные указания: проект (маркер) и пользователь — согласие, приоритет над автооценкой
    user = False
    if env and env.get("marker") and idx(e) < idx(env["marker"]):
        e, source = env["marker"], "project"
        user = True
        why.append("маркер %s в проекте: не ниже %s" % (ENV_MARKER, env["marker"]))
    d = d or {}
    if d.get("effort"):
        e, source, user = d["effort"], "user", True
        why.append("задано пользователем: %s" % d["effort"])
    else:
        if d.get("effort_min") and idx(e) < idx(d["effort_min"]):
            e, source, user = d["effort_min"], "user", True
            why.append("пользователь просит глубже → не ниже %s" % d["effort_min"])
        if d.get("effort_max") and idx(e) > idx(d["effort_max"]):
            want = d["effort_max"]
            if risky and idx(want) < idx(RISK_EFFORT_MIN):   # мягкая просьба «быстро/кратко» не снимает пол риска
                want = RISK_EFFORT_MIN
                why.append("просьба о быстром ответе, но цена ошибки высокая → не ниже %s" % RISK_EFFORT_MIN)
            if idx(e) > idx(want):
                e, source, user = want, "user", True
                why.append("пользователь просит быстрее → %s" % want)
    if e not in MODEL_EFFORTS.get(tier, EFFORTS):
        e = safe_effort(e)
    confirm = e in CONFIRM_EFFORTS and not user
    label = "низкая" if source == "heuristic" else ("задано" if user else _conf_label(conf))
    return {"effort": e, "effort_confidence": label, "effort_confirm": confirm,
            "effort_fallback": safe_effort(e) if confirm else e, "effort_source": source,
            "effort_reasons": why, "effort_depth": round(depth, 3), "effort_layers": layers}


def session_effort(cwd=None):
    """Текущий effort основной сессии, если он где-то явно задан (только чтение): CLAUDE_CODE_EFFORT_LEVEL,
    .claude/settings.local.json и .claude/settings.json проекта, ~/.claude/settings.json → effortLevel. Иначе None."""
    env = (os.environ.get("CLAUDE_CODE_EFFORT_LEVEL") or "").lower()
    if env in EFFORTS:
        return env
    paths = []
    try:
        base = Path(cwd or os.getcwd()).resolve()
        paths += [base / ".claude" / "settings.local.json", base / ".claude" / "settings.json"]
    except OSError:
        pass
    paths.append(Path.home() / ".claude" / "settings.json")
    for p in paths:
        try:
            val = str(json.loads(p.read_text(encoding="utf-8")).get("effortLevel", "")).lower()
        except (OSError, ValueError, AttributeError):
            continue
        if val in EFFORTS:
            return val
    return None


TIER_ORDER = ["haiku", "sonnet", "opus", "fable"]


def apply_tier_directive(tier, d):
    """Явный выбор модели в тексте → (уровень, согласие_пользователя, причина|None). «не на opus» исключает уровень."""
    if d.get("tier"):
        return d["tier"], True, "модель задана пользователем: %s" % d["tier"]
    if tier in d.get("tier_not", []):
        i = TIER_ORDER.index(tier)
        for j in [i - 1, i + 1, i - 2, i + 2]:
            if 0 <= j < len(TIER_ORDER) and TIER_ORDER[j] not in d["tier_not"]:
                return TIER_ORDER[j], False, "пользователь не хочет %s → %s" % (tier, TIER_ORDER[j])
    return tier, False, None
