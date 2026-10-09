# -*- coding: utf-8 -*-
"""2.3.0 (#30): журнал решений и фактов в корне проекта — triage-log.jsonl. ОПЦИЯ, по умолчанию выключена.

Зачем. Триаж предсказывает модель и effort, но не узнаёт, чем кончилось: сколько токенов и минут ушло, приняли ли
результат без замечаний. Этот журнал хранит пары «решение → факт», а `--calibrate` сводит их по (модель, effort):
медиана расхода, исходы, «недооценка по факту». Отсюда же — «ожидаемый расход» в новых решениях (медиана прошлых фактов).

Включение: переменная TYPESAFE_TRIAGE_PROJECT_LOG=on (или путь к файлу), флаг --project-log [ПУТЬ] у ручных команд;
`--fact` пишет всегда (это явная команда). Корень проекта — корень git-репозитория каталога запуска (иначе сам каталог).
ТЕКСТ ЗАПРОСА НЕ ПИШЕТСЯ НИКОГДА: только время, id решения (хеш запроса или id задачи --batch), хеш сессии, тип задачи,
модель, effort, уверенность, действие, источник оценки; в факте — модель, effort, токены, минуты, исход, число замечаний.
Только стандартная библиотека, без сети.
"""
import json
import os
import statistics
import time
from pathlib import Path

ENV = "TYPESAFE_TRIAGE_PROJECT_LOG"
FILE_NAME = "triage-log.jsonl"
ON_WORDS = ("1", "on", "yes", "true", "да")
OFF_WORDS = ("", "0", "off", "no", "false", "нет")
TIERS = ("haiku", "sonnet", "opus", "fable")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# исход подзадачи: ok — принято без замечаний; review — принято после замечаний ревью; rework — переделка той же
# моделью; escalated — понадобилась модель/effort выше; fail — не справился
OUTCOMES = ("ok", "review", "rework", "escalated", "fail")
UNDER_OUTCOMES = ("escalated", "fail")
EXPECT_MIN_FACTS = 2
MAX_READ_BYTES = 4 * 1024 * 1024


def project_root(cwd=None):
    try:
        start = Path(cwd or os.getcwd()).resolve()
    except (OSError, ValueError):
        return None
    for p in [start, *start.parents][:25]:
        if (p / ".git").exists():
            return p
    return start


def log_path(cwd=None, value=None, environ=None):
    """Путь журнала или None (выключен). value — значение флага --project-log (True — путь по умолчанию, строка — путь);
    без флага — переменная ENV: on → <корень проекта>/triage-log.jsonl, путь → этот файл (относительный — от корня)."""
    env = os.environ if environ is None else environ
    raw = value if value is not None else env.get(ENV, "")
    if raw is True:
        raw = "on"
    s = str(raw or "").strip()
    if s.lower() in OFF_WORDS:
        return None
    root = project_root(cwd)
    if root is None:
        return None
    if s.lower() in ON_WORDS:
        return root / FILE_NAME
    p = Path(os.path.expanduser(s))
    return p if p.is_absolute() else root / p


def append(path, rec):
    """Дописать запись; сбой записи не ломает работу (журнал вспомогательный). → True, если записано."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def read(path):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - MAX_READ_BYTES))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError):
        return []
    out = []
    for ln in lines:
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("kind") in ("decision", "fact"):
            out.append(rec)
    return out


def _median(xs):
    xs = [x for x in xs if isinstance(x, (int, float)) and not isinstance(x, bool)]
    return int(statistics.median(xs)) if xs else None


def expected(records, model, effort):
    """Ожидаемый расход для (модель, effort): медиана токенов и минут прошлых фактов (не меньше EXPECT_MIN_FACTS),
    иначе None — без фактов оценки нет (не придумываем)."""
    facts = [r for r in records if r.get("kind") == "fact" and r.get("model") == model and r.get("effort") == effort]
    toks = [r.get("tokens") for r in facts if r.get("tokens")]
    if len(toks) < EXPECT_MIN_FACTS:
        return None
    return {"tokens": _median(toks), "minutes": _median([r.get("minutes") for r in facts if r.get("minutes")]),
            "facts": len(facts)}


def decision_record(decision_id, result, via, task_id=None, session=None, records=None):
    """Запись решения без текста запроса."""
    a = result.get("action") or {}
    rec = {"ts": int(time.time()), "kind": "decision", "id": decision_id, "via": via,
           "model": result.get("model"), "effort": result.get("effort"), "source": result.get("source"),
           "confidence": result.get("confidence"), "action": a.get("kind"),
           "domain": (result.get("domain") or {}).get("kind")}
    if task_id:
        rec["task_id"] = str(task_id)[:64]
    if session:
        rec["session"] = session
    exp = expected(records or [], rec["model"], rec["effort"])
    if exp:
        rec["expected"] = exp
    return {k: v for k, v in rec.items() if v is not None}


def fact_record(ref, model=None, effort=None, tokens=None, minutes=None, outcome=None, review_issues=None):
    """Запись факта после подзадачи. Проверяет значения; ошибка — ValueError с понятным текстом."""
    if not ref:
        raise ValueError("нужен id решения: --fact <id> (id из заметки, журнала или id задачи --batch)")
    if model is not None and model not in TIERS:
        raise ValueError("--model: %s" % " | ".join(TIERS))
    if effort is not None and effort not in EFFORTS:
        raise ValueError("--effort: %s" % " | ".join(EFFORTS))
    if outcome is not None and outcome not in OUTCOMES:
        raise ValueError("--outcome: %s" % " | ".join(OUTCOMES))
    rec = {"ts": int(time.time()), "kind": "fact", "ref": str(ref)[:64], "model": model, "effort": effort,
           "outcome": outcome}
    for name, val in (("tokens", tokens), ("minutes", minutes), ("review_issues", review_issues)):
        if val is None:
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            raise ValueError("--%s: число" % name.replace("_", "-"))
        if num < 0:
            raise ValueError("--%s: не меньше 0" % name.replace("_", "-"))
        rec[name] = int(num) if name != "minutes" else round(num, 1)
    return {k: v for k, v in rec.items() if v is not None}


def link(records):
    """Факты, сопоставленные с решениями (по id решения или id задачи --batch). → [(решение|None, факт)]."""
    by_id = {}
    for r in records:
        if r.get("kind") == "decision":
            by_id[r.get("id")] = r
            if r.get("task_id"):
                by_id[r["task_id"]] = r
    return [(by_id.get(f.get("ref")), f) for f in records if f.get("kind") == "fact"]


def under_by_fact(decision, fact):
    """Недооценка по факту: исход escalated/fail, либо по факту понадобились модель или effort выше предсказанных."""
    if fact.get("outcome") in UNDER_OUTCOMES:
        return True
    if not decision:
        return False
    dm, fm = decision.get("model"), fact.get("model")
    de, fe = decision.get("effort"), fact.get("effort")
    if dm in TIERS and fm in TIERS and TIERS.index(fm) > TIERS.index(dm):
        return True
    return de in EFFORTS and fe in EFFORTS and EFFORTS.index(fe) > EFFORTS.index(de)


def summary(path):
    """Строки сводки для --calibrate: по (модель, effort) — число фактов, медианы токенов и минут, исходы;
    сколько фактов сопоставлено с решениями и сколько из них — недооценка по факту."""
    recs = read(path)
    facts = [r for r in recs if r.get("kind") == "fact"]
    decisions = [r for r in recs if r.get("kind") == "decision"]
    lines = ["\nЖурнал проекта %s: решений %d, фактов %d" % (path, len(decisions), len(facts))]
    if not facts:
        lines.append("  фактов нет: после подзадачи — --fact <id> --model … --effort … --tokens … --outcome ok|review|rework|escalated|fail")
        return lines
    groups = {}
    for f in facts:
        groups.setdefault((f.get("model") or "?", f.get("effort") or "?"), []).append(f)
    for (m, e), fs in sorted(groups.items(), key=lambda kv: (TIERS.index(kv[0][0]) if kv[0][0] in TIERS else 9,
                                                              EFFORTS.index(kv[0][1]) if kv[0][1] in EFFORTS else 9)):
        outs = {}
        for f in fs:
            outs[f.get("outcome") or "?"] = outs.get(f.get("outcome") or "?", 0) + 1
        tok, mins = _median([f.get("tokens") for f in fs]), _median([f.get("minutes") for f in fs])
        lines.append("  %s/%s: фактов %d, медиана токенов %s, минут %s, исходы: %s" % (
            m, e, len(fs), tok if tok is not None else "—", mins if mins is not None else "—",
            ", ".join("%s %d" % kv for kv in sorted(outs.items(), key=lambda kv: -kv[1]))))
    pairs = link(recs)
    linked = [(d, f) for d, f in pairs if d]
    under = [(d, f) for d, f in pairs if under_by_fact(d, f)]
    lines.append("  сопоставлено с решениями: %d из %d; недооценка по факту (escalated/fail или понадобилось выше): %d"
                 % (len(linked), len(pairs), len(under)))
    for d, f in under[:10]:
        lines.append("    %s: предсказано %s/%s → факт %s/%s, исход %s" % (
            f.get("ref"), (d or {}).get("model", "?"), (d or {}).get("effort", "?"), f.get("model", "?"), f.get("effort", "?"),
            f.get("outcome", "?")))
    return lines
