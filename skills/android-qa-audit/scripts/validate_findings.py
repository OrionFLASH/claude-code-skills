#!/usr/bin/env python3
"""Check findings.json against templates/finding.schema.json (a JSON Schema subset, stdlib only).

  validate_findings.py findings.json [--schema PATH] [--run-dir DIR]
Errors: required fields, enum, pattern, types, if/else, duplicate id and fingerprint, unfilled {{…}} placeholders.
Warnings: unmasked e-mail / tokens / JWT / auth values (masking.py), crash/anr without a `crash` object,
missing steps for critical/high, screenshot or recording files that do not exist in the run folder.
Exit code: 0 — ok, 1 — errors.
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from masking import find_unmasked  # noqa: E402

SCHEMA = HERE.parent / "templates" / "finding.schema.json"
TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict,
         "null": type(None)}


def check(value, schema, root, path, errors):
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            target = target[part]
        return check(value, target, root, path, errors)
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: значение {value!r} не из {schema['enum']}")
        return
    t = schema.get("type")
    if t:
        allowed = t if isinstance(t, list) else [t]
        if not any(isinstance(value, TYPES[x]) and not (x in ("integer", "number") and isinstance(value, bool)) for x in allowed):
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
    if "if" in schema:
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
    ap.add_argument("--run-dir", help="папка прогона (по умолчанию — папка findings.json): проверка файлов скриншотов")
    a = ap.parse_args()
    schema = json.loads(Path(a.schema).read_text(encoding="utf-8"))
    text = Path(a.findings).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except ValueError as ex:
        print(f"ERROR findings.json не JSON: {ex}")
        sys.exit(1)
    run_dir = Path(a.run_dir) if a.run_dir else Path(a.findings).resolve().parent
    errors, warnings = [], []
    check(data, schema, schema, "$", errors)
    fs = data.get("findings", []) if isinstance(data, dict) else []
    for key in ("id", "fingerprint"):
        vals = [f.get(key) for f in fs if isinstance(f, dict) and f.get(key)]
        dups = sorted({v for v in vals if vals.count(v) > 1})
        if dups:
            errors.append(f"повторяющиеся {key}: {dups}")
    if "{{" in text:
        errors.append("остались плейсхолдеры {{…}}")
    warnings += find_unmasked(text)
    for f in fs:
        if not isinstance(f, dict):
            continue
        fid = f.get("id", "?")
        if f.get("type") in ("crash", "anr") and not f.get("crash"):
            warnings.append(f"{fid}: тип {f['type']} без объекта crash (summary, process, time)")
        if f.get("severity") in ("critical", "high") and not f.get("steps"):
            warnings.append(f"{fid}: {f['severity']} без шагов воспроизведения")
        for key in ("screenshots", "recordings"):
            for p in f.get(key) or []:
                if not (run_dir / p).exists() and not Path(p).is_absolute():
                    warnings.append(f"{fid}: нет файла {p}")
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
