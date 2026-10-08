#!/usr/bin/env python3
"""Проверка findings.json по templates/finding.schema.json (подмножество JSON Schema, только stdlib).

  validate_findings.py findings.json [--schema PATH]
Проверяет: обязательные поля, enum, pattern, типы; уникальность id и fingerprint; отсутствие
незаполненных плейсхолдеров {{…}}; e-mail и длинные токены без маскирования (предупреждение).
Код выхода: 0 — ок, 1 — ошибки.
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
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            check(item, schema["items"], root, f"{path}[{i}]", errors)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("findings")
    ap.add_argument("--schema", default=str(SCHEMA))
    a = ap.parse_args()
    schema = json.loads(Path(a.schema).read_text(encoding="utf-8"))
    text = Path(a.findings).read_text(encoding="utf-8")
    data = json.loads(text)
    errors, warnings = [], []
    check(data, schema, schema, "$", errors)
    fs = data.get("findings", [])
    for key in ("id", "fingerprint"):
        vals = [f.get(key) for f in fs if f.get(key)]
        dups = {v for v in vals if vals.count(v) > 1}
        if dups:
            errors.append(f"повторяющиеся {key}: {sorted(dups)}")
    if "{{" in text:
        errors.append("остались плейсхолдеры {{…}}")
    for m in EMAIL.finditer(text):
        if "***" not in m.group(0):
            warnings.append(f"e-mail без маскирования: {m.group(0)[:3]}…")
    for m in TOKEN.finditer(text):
        if is_slug(m.group(0)):
            continue  # file names / ids like F-012-bell-over-legend-annotated
        warnings.append(f"похоже на немаскированный токен: {m.group(0)[:4]}…({len(m.group(0))})")
    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    print(f"validate_findings: находок {len(fs)}, ошибок {len(errors)}, предупреждений {len(warnings)}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
