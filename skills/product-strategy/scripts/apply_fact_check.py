#!/usr/bin/env python3
"""Исправление JSON-источников по data/fact-check.json (шаг «обновить исходники по fact-check», FB-052).

  apply_fact_check.py <OUT> [--dry-run] [--json]   применить fix у подтверждённых записей, поставить applied: true
  apply_fact_check.py <OUT> --check [--json]       только проверка (для build_all --strict): код 1 — есть
                                                   неприменённые подтверждённые записи

data/fact-check.json — список записей или объект с items|discrepancies|checks (как читает collect_reports.py).
Запись (поля, кроме fact|claim, необязательны):
  {"fact": "MetaForge: премиум", "phase1_value": "нет", "resolved_value": "Premium $2,99/4,99/9,99", "source": "…",
   "fix": {"file": "data/competitors.json", "path": "[slug=metaforge].price", "value": "Premium $2,99/4,99/9,99",
           "op": "set|append|merge|delete"},              ← или список таких объектов
   "text_only": true,                                     ← расхождение только в тексте, JSON не трогаем
   "applied": true, "applied_at": "2026-10-19", "previous": [<прежние значения>]}   ← пишет этот скрипт
Путь fix.path — шаги через точку: ключ словаря (`price`, `features.premium`), номер элемента списка (`0`, `[0]`),
выбор элемента списка по полю (`[slug=metaforge]`, `[id=P012]`); шаг можно склеивать: `items[slug=a].price`.
op: set (по умолчанию; создаёт недостающий последний ключ), append (добавить в список, если значения ещё нет),
merge (слить словарь), delete (удалить ключ или элемент). fix.file — относительный путь внутри <OUT>, только *.json
(не сам data/fact-check.json); выход за пределы <OUT> — ошибка.

Подтверждённая запись — есть resolved_value (не null) или fix. Неприменённая — подтверждённая без applied: true и
без text_only: true (или «только текст» в note). Такие записи и ошибки путей — код 1 в --check; без --check
скрипт применяет fix и пишет applied. Записи без resolved_value и без fix — «не подтверждены» (предупреждение).
Отчёт — stdout и build/fact-check-apply.json. Только стандартная библиотека.
"""
import argparse
import copy
import json
import re
import sys
from datetime import date
from pathlib import Path

TOKEN = re.compile(r"\[([^\]]*)\]|([^.\[\]]+)")
MISSING = object()


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def items_of(fc):
    """(список записей, контейнер для записи обратно)."""
    if isinstance(fc, list):
        return fc
    if isinstance(fc, dict):
        for k in ("items", "discrepancies", "checks"):
            if isinstance(fc.get(k), list):
                return fc[k]
    return []


def parse_path(path):
    """'items[slug=a].price' → [('key', 'items'), ('sel', ('slug', 'a')), ('key', 'price')]."""
    steps = []
    for part in str(path).split("."):
        if part == "":
            continue
        for m in TOKEN.finditer(part):
            br, name = m.group(1), m.group(2)
            if br is not None:
                if "=" in br:
                    k, v = br.split("=", 1)
                    steps.append(("sel", (k.strip(), v.strip().strip("\"'"))))
                elif re.fullmatch(r"-?\d+", br.strip()):
                    steps.append(("idx", int(br)))
                else:
                    raise ValueError("непонятный шаг [%s]" % br)
            elif re.fullmatch(r"-?\d+", name):
                steps.append(("idx", int(name)))
            else:
                steps.append(("key", name))
    if not steps:
        raise ValueError("пустой путь")
    return steps


def step_get(obj, st):
    kind, arg = st
    if kind == "key":
        if isinstance(obj, dict) and arg in obj:
            return obj[arg]
        return MISSING
    if kind == "idx":
        if isinstance(obj, list) and -len(obj) <= arg < len(obj):
            return obj[arg]
        return MISSING
    if isinstance(obj, list):
        k, v = arg
        hits = [x for x in obj if isinstance(x, dict) and str(x.get(k)) == v]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise ValueError("выбор [%s=%s] неоднозначен (%d элементов)" % (k, v, len(hits)))
    return MISSING


def apply_fix(doc, fix):
    """Применить один fix к загруженному JSON на месте. → прежнее значение (None, если не было)."""
    steps = parse_path(fix.get("path"))
    op = fix.get("op") or "set"
    if op not in ("set", "append", "merge", "delete"):
        raise ValueError("op %r не из set|append|merge|delete" % op)
    cur = doc
    for st in steps[:-1]:
        nxt = step_get(cur, st)
        if nxt is MISSING:
            raise ValueError("путь %s: шаг %s не найден" % (fix.get("path"), st[1]))
        cur = nxt
    last = steps[-1]
    old = step_get(cur, last)
    if op == "delete":
        if old is MISSING:
            raise ValueError("путь %s: удалять нечего" % fix.get("path"))
        if isinstance(cur, dict):
            del cur[last[1]]
        else:
            cur.remove(old)
        return old
    if "value" not in fix:
        raise ValueError("нет fix.value")
    val = copy.deepcopy(fix["value"])
    if op == "append":
        target = old
        if target is MISSING:
            if last[0] != "key" or not isinstance(cur, dict):
                raise ValueError("путь %s: списка нет" % fix.get("path"))
            target = cur[last[1]] = []
        if not isinstance(target, list):
            raise ValueError("путь %s: не список" % fix.get("path"))
        if val not in target:
            target.append(val)
        return None if old is MISSING else old
    if op == "merge":
        if old is MISSING:
            if last[0] != "key" or not isinstance(cur, dict):
                raise ValueError("путь %s: словаря нет" % fix.get("path"))
            cur[last[1]] = {}
            old = None
            target = cur[last[1]]
        else:
            target = old
            old = copy.deepcopy(old)
        if not isinstance(target, dict) or not isinstance(val, dict):
            raise ValueError("путь %s: merge — только словарь со словарём" % fix.get("path"))
        target.update(val)
        return old
    # set
    if last[0] == "key":
        if not isinstance(cur, dict):
            raise ValueError("путь %s: родитель не словарь" % fix.get("path"))
        cur[last[1]] = val
    elif last[0] == "idx":
        if old is MISSING:
            raise ValueError("путь %s: нет элемента %d" % (fix.get("path"), last[1]))
        cur[last[1]] = val
    else:
        if old is MISSING:
            raise ValueError("путь %s: элемент [%s=%s] не найден" % (fix.get("path"), last[1][0], last[1][1]))
        cur[cur.index(old)] = val
    return None if old is MISSING else old


def is_text_only(rec):
    return rec.get("text_only") is True or "только текст" in str(rec.get("note") or "").lower()


def confirmed(rec):
    return rec.get("resolved_value") not in (None, "") or bool(rec.get("fix"))


def label(rec, n):
    return "#%d «%s»" % (n, rec.get("fact") or rec.get("claim") or rec.get("topic") or "?")


def safe_target(out, rel):
    if not rel or not str(rel).endswith(".json"):
        raise ValueError("fix.file %r — нужен путь к *.json внутри <OUT>" % rel)
    p = (out / str(rel)).resolve()
    try:
        p.relative_to(out)
    except ValueError:
        raise ValueError("fix.file %r вне папки прогона" % rel)
    if p == (out / "data" / "fact-check.json").resolve():
        raise ValueError("fix.file не может быть data/fact-check.json")
    return p


def run(out, check=False, dry_run=False):
    out = Path(out).resolve()
    path = out / "data" / "fact-check.json"
    fc = load_json(path, None)
    rep = {"date": date.today().isoformat(), "applied": [], "pending": [], "errors": [], "unconfirmed": [], "text_only": [],
           "already": [], "files": []}
    if fc is None:
        rep["note"] = "нет data/fact-check.json — проверять нечего"
        return rep, 0
    recs = items_of(fc)
    cache = {}
    for n, rec in enumerate(recs, 1):
        if not isinstance(rec, dict):
            continue
        name = label(rec, n)
        if rec.get("applied") is True:
            rep["already"].append(name)
            continue
        if is_text_only(rec):
            rep["text_only"].append(name)
            continue
        if not confirmed(rec):
            rep["unconfirmed"].append(name)
            continue
        fixes = rec.get("fix")
        fixes = fixes if isinstance(fixes, list) else ([fixes] if isinstance(fixes, dict) else [])
        if not fixes:
            rep["pending"].append("%s: resolved_value есть, но нет fix {file, path, value} и нет text_only: true" % name)
            continue
        if check:
            rep["pending"].append("%s: fix не применён — apply_fact_check.py <OUT>" % name)
            continue
        prev, ok = [], True
        for fx in fixes:
            try:
                tgt = safe_target(out, fx.get("file"))
                if tgt not in cache:
                    if not tgt.exists():
                        raise ValueError("нет файла %s" % fx.get("file"))
                    cache[tgt] = json.loads(tgt.read_text(encoding="utf-8"))
                prev.append(apply_fix(cache[tgt], fx))
                if str(tgt.relative_to(out)) not in rep["files"]:
                    rep["files"].append(str(tgt.relative_to(out)))
            except (ValueError, json.JSONDecodeError) as e:
                rep["errors"].append("%s: %s" % (name, e))
                ok = False
                break
        if ok:
            rec["applied"] = True
            rec["applied_at"] = date.today().isoformat()
            rec["previous"] = prev
            rep["applied"].append(name)
    if not check and not dry_run and (rep["applied"]):
        for tgt, doc in cache.items():
            tgt.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        path.write_text(json.dumps(fc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    code = 1 if (rep["errors"] or rep["pending"]) else 0
    return rep, code


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--check", action="store_true", help="только проверка: код 1 — есть неприменённые подтверждённые записи")
    ap.add_argument("--dry-run", action="store_true", help="показать, что будет применено, без записи")
    ap.add_argument("--json", action="store_true", help="печатать отчёт JSON")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if not (out / "data").is_dir():
        print("ошибка: нет папки %s/data" % out, file=sys.stderr)
        return 2
    rep, code = run(out, a.check, a.dry_run)
    if not a.check and not a.dry_run:
        (out / "build").mkdir(parents=True, exist_ok=True)
        (out / "build" / "fact-check-apply.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if a.json:
        print(json.dumps(dict(rep, code=code), ensure_ascii=False, indent=2))
        return code
    if rep.get("note"):
        print(rep["note"])
        return 0
    print("fact-check: применено %d%s, уже применено %d, только текст %d, не подтверждено %d, неприменённых %d, ошибок %d"
          % (len(rep["applied"]), " (--dry-run, файлы не менялись)" if a.dry_run else "", len(rep["already"]),
             len(rep["text_only"]), len(rep["unconfirmed"]), len(rep["pending"]), len(rep["errors"])))
    if rep["files"]:
        print("Исправлены источники: %s — пересоберите графики и страницу (build_all.py)" % ", ".join(rep["files"]))
    for x in rep["pending"]:
        print("  ! " + x)
    for x in rep["errors"]:
        print("  ! " + x)
    for x in rep["unconfirmed"][:20]:
        print("  - не подтверждено: " + x)
    print("FAIL" if code else "OK")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
