#!/usr/bin/env python3
"""Проверка находок по templates/finding.schema.json (подмножество JSON Schema, только stdlib).

  validate_findings.py findings.json [--schema PATH]
      файл прогона {run, findings}: обязательные поля, enum, pattern, типы; уникальность id и fingerprint;
      находки исполнителей (с ingested) — с dup_check
  validate_findings.py --array FILE|- [--run run.json]
      результат исполнителя — МАССИВ находок без id и fingerprint (<RUN_DIR>/findings/<поток>.json), объект блока
      {"thread", "findings": [...], "not_checked", "checked", "questions"} или сообщение с блоком ```qa-findings```;
      «-» — читать stdin (исполнитель проверяет свой блок до отправки). Обязательно у каждой находки: dup_check
      (done | skipped); без repro — предупреждение. --run — <RUN_DIR>/run.json по схеме run.
  Файл-массив распознаётся и без --array.

Также: нет незаполненных плейсхолдеров {{…}}; e-mail и длинные токены без маскирования — предупреждение.
Код выхода: 0 — ок, 1 — ошибки, 2 — вход не прочитан (не JSON и нет блока qa-findings).
"""
import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent.parent / "templates" / "finding.schema.json"
TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict, "null": type(None)}
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]{2,}@[A-Za-z0-9-]{2,}\.[A-Za-z]{2,}\b")
TOKEN = re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[a-z])(?=[A-Za-z0-9_\-]*[A-Z])[A-Za-z0-9_\-]{32,}\b")
BLOCK_RX = re.compile(r"```[ \t]*(?:json[ \t]+)?qa-findings[^\n]*\n(.*?)\n[ \t]*```", re.S)


def is_slug(s):
    """Hyphenated human-readable names are not secrets: 3+ parts, each short."""
    parts = s.split("-")
    return len(parts) >= 3 and all(len(x) <= 16 for x in parts)


def check(value, schema, root, path, errors):
    if "$ref" in schema:
        ref = schema["$ref"].lstrip("#/").split("/")
        target = root
        for part in ref:
            target = target[part]
        return check(value, target, root, path, errors)
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: значение {value!r} не из {schema['enum']}")
        return
    t = schema.get("type")
    if t:
        allowed = t if isinstance(t, list) else [t]
        if not any(isinstance(value, TYPES[x]) and not (x in ("integer", "number") and isinstance(value, bool))
                   for x in allowed):
            errors.append(f"{path}: тип {type(value).__name__}, ожидается {t}")
            return
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} не соответствует {schema['pattern']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: длиннее {schema['maxLength']} символов")
    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value or value[req] in (None, "", []):
                errors.append(f"{path}: нет обязательного поля {req}")
        for k, sub in schema.get("properties", {}).items():
            if k in value and value[k] is not None:
                check(value[k], sub, root, f"{path}.{k}", errors)
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            for k, v in value.items():
                if k not in schema.get("properties", {}) and v is not None:
                    check(v, extra, root, f"{path}.{k}", errors)
    if "if" in schema:
        # JSON Schema if/then/else: the "if" branch is evaluated silently
        probe = []
        check(value, schema["if"], root, path, probe)
        branch = schema.get("then") if not probe else schema.get("else")
        if branch:
            check(value, branch, root, path, errors)
    for sub in schema.get("allOf", []):
        check(value, sub, root, path, errors)
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            check(item, schema["items"], root, f"{path}[{i}]", errors)


def leaks(text):
    warnings = []
    for m in EMAIL.finditer(text):
        if "***" not in m.group(0):
            warnings.append(f"e-mail без маскирования: {m.group(0)[:3]}…")
    for m in TOKEN.finditer(text):
        if is_slug(m.group(0)):
            continue  # file names / ids like F-012-bell-over-legend-annotated
        warnings.append(f"похоже на немаскированный токен: {m.group(0)[:4]}…({len(m.group(0))})")
    return warnings


def executor_schema(root):
    """Finding of an executor: no id / fingerprint yet, dup_check is required (the contract of the brief)."""
    fdef = json.loads(json.dumps(root["$defs"]["finding"]))
    fdef["required"] = [r for r in fdef.get("required", []) if r not in ("id", "fingerprint")] + ["dup_check"]
    fdef.pop("allOf", None)
    return fdef


def parse_executor(text):
    """-> (findings, not_checked, error): a JSON array, a block object or a message with ```qa-findings``` blocks."""
    try:
        data = json.loads(text)
        payloads = [data]
    except ValueError:
        payloads = []
        for n, m in enumerate(BLOCK_RX.finditer(text or ""), 1):
            try:
                payloads.append(json.loads(m.group(1)))
            except ValueError as ex:
                return None, None, f"блок {n}: не JSON ({ex})"
        if not payloads:
            return None, None, "не JSON и нет блока ```qa-findings```"
    findings, not_checked = [], []
    for p in payloads:
        if isinstance(p, list):
            findings += p
        elif isinstance(p, dict) and isinstance(p.get("findings"), list):
            findings += p["findings"]
            not_checked += p.get("not_checked") or []
        else:
            return None, None, "ожидается массив находок или объект {\"findings\": [...]}"
    return findings, not_checked, None


def validate_array(text, schema):
    errors, warnings = [], []
    findings, not_checked, err = parse_executor(text)
    if err:
        return None, [err], []
    fdef = executor_schema(schema)
    seen = set()
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            errors.append(f"$[{i}]: не объект")
            continue
        f = dict(f)
        if f.get("id") and not re.match(r"^F-\d{3,}$", str(f["id"])):
            f["source_id"] = str(f.pop("id"))  # an executor's own id: ingest keeps it as source_id
        f.pop("fingerprint", None)
        check(f, fdef, schema, f"$[{i}]", errors)
        key = (f.get("title"), f.get("url"))
        if key in seen:
            warnings.append(f"$[{i}]: повтор заголовка и адреса «{f.get('title')}»")
        seen.add(key)
        if not f.get("repro"):
            warnings.append(f"$[{i}] «{f.get('title')}»: нет repro — перед публикацией нужна ручная перепроверка")
    nc_def = schema["properties"]["not_checked"]
    check(not_checked, nc_def, schema, "not_checked", errors)
    return findings, errors, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("findings", help="findings.json, файл-массив исполнителя или «-» (stdin)")
    ap.add_argument("--array", action="store_true", help="результат исполнителя: массив / блок qa-findings")
    ap.add_argument("--run", help="run.json — сведения о прогоне по схеме run")
    ap.add_argument("--schema", default=str(SCHEMA))
    a = ap.parse_args()
    schema = json.loads(Path(a.schema).read_text(encoding="utf-8"))
    text = sys.stdin.read() if a.findings == "-" else Path(a.findings).read_text(encoding="utf-8")
    errors, warnings = [], []
    mode = "array" if a.array else None
    if mode is None:
        try:
            mode = "array" if isinstance(json.loads(text), list) else "file"
        except ValueError:
            mode = "array"  # a message with a ```qa-findings``` block
    if mode == "array":
        fs, errors, warnings = validate_array(text, schema)
        if fs is None:
            for e in errors:
                print("ERROR", e)
            sys.exit(2)
    else:
        data = json.loads(text)
        check(data, schema, schema, "$", errors)
        fs = data.get("findings", [])
        for key in ("id", "fingerprint"):
            vals = [f.get(key) for f in fs if f.get(key)]
            dups = {v for v in vals if vals.count(v) > 1}
            if dups:
                errors.append(f"повторяющиеся {key}: {sorted(dups)}")
    if a.run:
        try:
            run = json.loads(Path(a.run).read_text(encoding="utf-8"))
            check(run, schema["properties"]["run"], schema, "run", errors)
        except (OSError, ValueError) as ex:
            errors.append(f"run.json не прочитан: {ex}")
    if "{{" in text:
        errors.append("остались плейсхолдеры {{…}}")
    warnings += leaks(text)
    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    what = "результат исполнителя (массив)" if mode == "array" else "находок"
    print(f"validate_findings: {what}: {len(fs)}, ошибок {len(errors)}, предупреждений {len(warnings)}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
