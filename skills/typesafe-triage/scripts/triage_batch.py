# -*- coding: utf-8 -*-
"""2.3.0 (#29): пакетный триаж `--batch tasks.json` — для оркестратора, который раздаёт несколько подзадач исполнителям.

Вход — JSON: список задач или {"tasks": [...]}. Поля задачи: id (иначе T1, T2 …), task (текст, обязательно), paths
(файлы и папки, которые задача меняет; можно маски), необязательные goal, context, criteria, constraints, report — для
промпта исполнителя по шаблону references/executor-prompt.md.
Выход: таблица {id, model, effort, confidence, reasons}; порядок запуска (задачи с пересекающимися paths — «выполнять
последовательно», без пересечений — параллельно); текст ОДНОГО AskUserQuestion на все подтверждения пакета
(haiku/fable, effort low/max — не больше четырёх вопросов, по одному на вид); готовые аргументы Agent(...) для «да»
и для «нет»; промпты исполнителей. Каждая задача оценивается как обычный запрос (TypeSafe или эвристика).
Только стандартная библиотека.
"""
import json
import re
from pathlib import Path

TIERS = ("haiku", "sonnet", "opus", "fable")
CONFIRM_KINDS = (("model", "haiku"), ("model", "fable"), ("effort", "low"), ("effort", "max"))
MAX_TASKS = 50
MAX_TASK_CHARS = 20000
TEMPLATE_FILE = Path(__file__).resolve().parent.parent / "references" / "executor-prompt.md"
TEMPLATE_START, TEMPLATE_END = "<!-- template -->", "<!-- /template -->"
DEFAULTS = {
    "goal": "выполнить задачу ниже; готово — когда выполнены критерии готовности",
    "context": "—",
    "paths": "пути не заданы: сначала найди нужные файлы, правь минимально необходимое",
    "constraints": "—",
    "criteria": "тесты зелёные (новые — на каждый пункт), поведение вне задачи не изменилось",
    "report": "ветка и список коммитов; что сделано; чем проверено (команды и итог); что не сделано и почему; найденное по дороге",
}
FALLBACK_TEMPLATE = (
    "Ты исполнитель {id}. Истории нашего диалога у тебя нет — всё нужное в этом промпте.\n"
    "ЦЕЛЬ: {goal}\nЗАДАЧА: {task}\nКОНТЕКСТ: {context}\nФАЙЛЫ: {paths}\nОГРАНИЧЕНИЯ: {constraints}\n"
    "- отдельная ветка; без merge и push; скилл typesafe-triage не применять.\nКРИТЕРИИ ГОТОВНОСТИ: {criteria}\n"
    "КОММИТЫ: в конце сообщения — строка Co-Authored-By из твоей системной инструкции атрибуции (твоя модель).\n"
    "ОТЧЁТ: {report}\n")


class BatchError(ValueError):
    pass


def load_tasks(path):
    """Файл → список задач [{id, task, paths, …}]. Ошибки формата — BatchError с понятным текстом."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as e:
        raise BatchError("не удалось прочитать %s: %s" % (path, e.strerror or e))
    except ValueError as e:
        raise BatchError("%s: не JSON (%s)" % (path, e))
    items = data.get("tasks") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise BatchError("ожидается список задач или {\"tasks\": [...]}")
    if len(items) > MAX_TASKS:
        raise BatchError("задач %d — больше %d; разбейте пакет" % (len(items), MAX_TASKS))
    out, seen = [], set()
    for i, it in enumerate(items, 1):
        if isinstance(it, str):
            it = {"task": it}
        if not isinstance(it, dict) or not isinstance(it.get("task"), str) or not it["task"].strip():
            raise BatchError("задача №%d: нужно поле task (текст)" % i)
        tid = str(it.get("id") or "T%d" % i).strip()[:40]
        if tid in seen:
            raise BatchError("повтор id %r" % tid)
        seen.add(tid)
        paths = it.get("paths") or []
        if isinstance(paths, str):
            paths = [paths]
        if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
            raise BatchError("задача %s: paths — список строк" % tid)
        task = dict(it, id=tid, task=it["task"].strip()[:MAX_TASK_CHARS], paths=[p for p in paths if p.strip()])
        out.append(task)
    return out


def norm_path(p):
    """Путь для сравнения: прямые слеши, без ./ и хвостового /; маска — до первого символа маски (папка-префикс)."""
    s = p.strip().replace("\\", "/")
    s = re.sub(r"/+", "/", s)
    while s.startswith("./"):
        s = s[2:]
    cut = re.search(r"[*?\[]", s)
    if cut:
        s = s[:cut.start()]
        s = s[:s.rfind("/")] if "/" in s else ""
    return s.rstrip("/").lower()


def overlap(a, b):
    """Пересекаются ли два пути: совпадают, один — папка другого, или маска на весь проект ("" — корень)."""
    if a == "" or b == "":
        return True
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def plan_order(tasks):
    """→ {"parallel": [id], "sequential": [{"ids": [...], "shared": [пути]}], "unchecked": [id]} — задачи с общими
    путями выстраиваются в очередь (в порядке файла), остальные можно запускать параллельно."""
    with_paths = [t for t in tasks if t.get("paths")]
    parent = {t["id"]: t["id"] for t in with_paths}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    shared = {}
    for i, a in enumerate(with_paths):
        na = [norm_path(p) for p in a["paths"]]
        for b in with_paths[i + 1:]:
            nb = [norm_path(p) for p in b["paths"]]
            common = sorted({min(x, y, key=len) or "<весь проект>" for x in na for y in nb if overlap(x, y)})
            if common:
                parent[find(a["id"])] = find(b["id"])
                shared.setdefault(frozenset((a["id"], b["id"])), common)
    groups = {}
    for t in with_paths:
        groups.setdefault(find(t["id"]), []).append(t["id"])
    order = {"parallel": [], "sequential": [], "unchecked": [t["id"] for t in tasks if not t.get("paths")]}
    for ids in groups.values():
        if len(ids) == 1:
            order["parallel"].append(ids[0])
        else:
            paths = sorted({p for k, v in shared.items() if k <= set(ids) for p in v})
            order["sequential"].append({"ids": ids, "shared": paths[:6]})
    return order


SKIP_REASONS = ("нагрузка", "только эвристика: нагрузка", "нет TYPESAFE_API_KEY", "TypeSafe", "вход слишком", "офлайн", "≥ ")


def short_reasons(r, limit=3):
    """Причины для таблицы: правила модели и effort без чисел слоёв и без причины отказа TypeSafe (она — в confidence;
    полный разбор — в --json)."""
    out = []
    for x in (r.get("reason") or "").split("; "):
        x = x.strip()
        if x and not x.startswith(SKIP_REASONS):
            out.append(x)
    for x in r.get("effort_reasons") or []:
        if x.startswith(("a) ", "b) ", "c) ", "f) ")):
            continue
        out.append(x[3:] if x[1:3] == ") " else x)
    if not out:
        out.append("нагрузка/глубина в середине шкалы")
    if r.get("domain"):
        out.append("тип %s" % r["domain"]["kind"])
    return out[:limit]


def row_of(task, r):
    return {"id": task["id"], "model": r.get("model"), "effort": r.get("effort"),
            "confidence": r.get("confidence") if r.get("source") == "typesafe" else "низкая (эвристика)",
            "reasons": short_reasons(r), "confirm": bool(r.get("confirm")), "effort_confirm": bool(r.get("effort_confirm")),
            "fallback": r.get("fallback") if r.get("confirm") else r.get("model"),
            "effort_fallback": r.get("effort_fallback") if r.get("effort_confirm") else r.get("effort"),
            "source": r.get("source"), "paths": task.get("paths") or [], "read_only": _read_only(r)}


def _read_only(r):
    v = ((r.get("metrics") or {}).get("read_only") or {}).get("value")
    return bool(v is not None and v >= 0.8)


def ask_questions(rows):
    """Подтверждения пакета → вопросы ОДНОГО AskUserQuestion (по одному на вид: haiku, fable, effort low, effort max)."""
    qs = []
    for axis, val in CONFIRM_KINDS:
        if axis == "model":
            ids = [r["id"] for r in rows if r["confirm"] and r["model"] == val]
        else:
            ids = [r["id"] for r in rows if r["effort_confirm"] and r["effort"] == val]
        if not ids:
            continue
        safe = {"haiku": "sonnet", "fable": "opus", "low": "medium", "max": "xhigh"}[val]
        if axis == "model":
            q = "Запустить на %s задачи %s?" % (val, ", ".join(ids))
            yes_d = "исполнители %s на %s" % (", ".join(ids), val)
        else:
            q = "Effort %s для задач %s — %s?" % (val, ", ".join(ids), "дольше и дороже" if val == "max" else "минимум размышлений")
            yes_d = "effort %s у %s" % (val, ", ".join(ids))
        qs.append({"question": q, "header": ("%s %s" % ("effort" if axis == "effort" else "модель", val))[:12],
                   "multiSelect": False,
                   "options": [{"label": "Да, %s" % val, "description": yes_d},
                               {"label": "Нет, %s" % safe, "description": "безопасная замена: %s" % safe}]})
    return qs


def agent_args(row, task, yes=True):
    """Аргументы инструмента Agent для задачи: при yes=False — безопасные замены (ответ «нет» на вопрос)."""
    model = row["model"] if yes or not row["confirm"] else row["fallback"]
    effort = row["effort"] if yes or not row["effort_confirm"] else row["effort_fallback"]
    words = re.sub(r"\s+", " ", task.get("goal") or task["task"]).split(" ")
    args = {"description": ("%s: %s" % (row["id"], " ".join(words[:4])))[:60], "model": model, "effort": effort,
            "run_in_background": True}
    if task.get("paths") or not row["read_only"]:
        args["isolation"] = "worktree"
    return args


def agent_call_text(args, prompt_ref):
    parts = ['description="%s"' % args["description"].replace('"', "'"), 'model="%s"' % args["model"],
             'effort="%s"' % args["effort"]]
    if args.get("isolation"):
        parts.append('isolation="%s"' % args["isolation"])
    parts.append("run_in_background=true")
    parts.append("prompt=<%s>" % prompt_ref)
    return "Agent(%s)" % ", ".join(parts)


def load_template():
    try:
        text = TEMPLATE_FILE.read_text(encoding="utf-8")
        a, b = text.index(TEMPLATE_START) + len(TEMPLATE_START), text.index(TEMPLATE_END)
        body = text[a:b].strip("\n")
        body = re.sub(r"^```\w*\n|\n```$", "", body.strip())
        return body + "\n"
    except (OSError, ValueError):
        return FALLBACK_TEMPLATE


def _fmt(val, bullet=True):
    if isinstance(val, (list, tuple)):
        items = [str(x).strip() for x in val if str(x).strip()]
        if not items:
            return None
        return ("\n- " + "\n- ".join(items)) if bullet and len(items) > 1 else ", ".join(items)
    s = str(val or "").strip()
    return s or None


def render_prompt(task, row, template=None):
    """Самодостаточный промпт исполнителя по шаблону: подстановка {id}, {goal}, {task}, {context}, {paths},
    {constraints}, {criteria}, {report}, {model}, {effort}; пустые поля — значения по умолчанию."""
    tpl = template or load_template()
    vals = {"id": task["id"], "task": task["task"], "model": row["model"], "effort": row["effort"]}
    for k in ("goal", "context", "paths", "constraints", "criteria", "report"):
        vals[k] = _fmt(task.get(k), bullet=k != "paths") or DEFAULTS[k]
    out = tpl
    for k, v in vals.items():
        out = out.replace("{%s}" % k, str(v))
    return out


def run(tasks, triage_fn, template=None):
    """Оценить пакет. triage_fn(task_dict) → результат триажа. → отчёт (dict) для format_text / JSON."""
    rows, results = [], {}
    for t in tasks:
        r = triage_fn(t)
        results[t["id"]] = r
        rows.append(row_of(t, r))
    tpl = template or load_template()
    by_id = {t["id"]: t for t in tasks}
    for row in rows:
        t = by_id[row["id"]]
        row["agent"] = agent_args(row, t, yes=True)
        if row["confirm"] or row["effort_confirm"]:
            row["agent_if_no"] = agent_args(row, t, yes=False)
        row["prompt"] = render_prompt(t, row, tpl)
    order = plan_order(tasks)
    qs = ask_questions(rows)
    return {"tasks": rows, "order": order, "ask": {"questions": qs} if qs else None,
            "sources": {"typesafe": sum(1 for r in results.values() if r.get("source") == "typesafe"),
                        "heuristic": sum(1 for r in results.values() if r.get("source") != "typesafe")}}


def _cell(s):
    return str(s).replace("|", "/").replace("\n", " ")


def format_text(rep, prompts=False):
    rows = rep["tasks"]
    out = ["TypeSafe-триаж --batch: задач %d (TypeSafe %d, эвристика %d)" % (
        len(rows), rep["sources"]["typesafe"], rep["sources"]["heuristic"]), "",
        "| id | model | effort | confidence | reasons |", "|----|-------|--------|------------|---------|"]
    for r in rows:
        mark_m = r["model"] + (" (вопрос)" if r["confirm"] else "")
        mark_e = r["effort"] + (" (вопрос)" if r["effort_confirm"] else "")
        out.append("| %s | %s | %s | %s | %s |" % (_cell(r["id"]), mark_m, mark_e, _cell(r["confidence"]), _cell("; ".join(r["reasons"]))))
    o = rep["order"]
    out += ["", "Порядок запуска:"]
    if o["parallel"]:
        out.append("- параллельно (пути не пересекаются): %s" % ", ".join(o["parallel"]))
    for g in o["sequential"]:
        out.append("- выполнять последовательно: %s (общие пути: %s)" % (" → ".join(g["ids"]), ", ".join(g["shared"])))
    if o["unchecked"]:
        out.append("- без paths, пересечения не проверены: %s — задайте paths или запускайте после остальных" % ", ".join(o["unchecked"]))
    if rep.get("ask"):
        qs = rep["ask"]["questions"]
        out += ["", "Подтверждение — ОДИН вызов AskUserQuestion, вопросов: %d (JSON — в --json, поле ask):" % len(qs)]
        for i, q in enumerate(qs, 1):
            out.append("  %d. «%s» — «%s» / «%s»" % (i, q["question"], q["options"][0]["label"], q["options"][1]["label"]))
        out.append("Нет явного «да» → безопасные замены (вызовы «нет» ниже).")
    out += ["", "Готовые вызовы Agent (промпт — шаблон references/executor-prompt.md%s):" % (", ниже" if prompts else "; полностью — с --prompts или в --json")]
    for r in rows:
        out.append("- %s" % agent_call_text(r["agent"], "промпт %s" % r["id"]))
        if r.get("agent_if_no"):
            out.append("  нет «да» → %s" % agent_call_text(r["agent_if_no"], "промпт %s" % r["id"]))
    out += ["", "Исполнителям: скилл typesafe-triage не применять; строка Co-Authored-By — из системной инструкции атрибуции "
                "исполнителя (его фактическая модель), не модель оркестратора."]
    if prompts:
        for r in rows:
            out += ["", "----- промпт %s -----" % r["id"], r["prompt"].rstrip()]
    return "\n".join(out)
