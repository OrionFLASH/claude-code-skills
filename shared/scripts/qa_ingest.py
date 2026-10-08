"""Findings returned by executors as a JSON block in their final message -> <RUN_DIR>/findings.json (S-5).

Subagents often may not write files (the tool rejects «subagents should return findings as text»), so an executor
returns its findings in the LAST message as a fenced block and the orchestrator ingests it:

    ```qa-findings
    {"thread": "qa-ux",
     "findings": [{"direction": "ux", "check_id": "ux.feedback", "type": "bug", "severity": "medium",
                   "title": "…", "url": "https://example.com/", "steps": ["…"], "expected": "…", "actual": "…",
                   "repro": {"url": "https://example.com/", "js": "…"}, "sources": ["own:checklist"]}],
     "not_checked": [{"what": "…", "reason": "…"}],
     "questions": ["…"]}
    ```

The block may also be a bare JSON array of findings, and «```json qa-findings» is accepted. Several blocks in one
message are merged. Each finding is validated against the skill's $defs.finding (id and fingerprint are not required:
the orchestrator assigns ids F-NNN; fingerprint.py compute adds fingerprints). Nothing is written if any finding is
invalid (unless partial=True: valid ones are added, invalid ones reported). The raw message is kept in
<RUN_DIR>/raw/messages/ for the audit trail; questions go to <RUN_DIR>/questions.json.

Used by skills/<skill>/scripts/ingest_findings.py (thin wrapper: schema path + run skeleton). Stdlib only, Python 3.8+.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

BLOCK_RX = re.compile(r"```[ \t]*(?:json[ \t]+)?qa-findings[^\n]*\n(.*?)\n[ \t]*```", re.S)
TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict,
         "null": type(None)}

EXAMPLE = """```qa-findings
{"thread": "<qa-id>",
 "findings": [
  {"direction": "<направление>", "check_id": "<id пункта чек-листа>", "type": "bug", "severity": "medium",
   "title": "Что не так и где", "url": "<URL>", "steps": ["1. …"], "expected": "…", "actual": "…",
   "screenshots": ["screenshots/<qa-id>-01-annotated.png"],
   "repro": {"url": "<URL>", "js": "<выражение: true, если дефект есть>"},
   "sources": ["own:checklist"]}
 ],
 "not_checked": [{"what": "…", "reason": "…", "rule": null}],
 "questions": ["…"]}
```"""


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def schema_check(value, schema, root, path, errors):
    """JSON Schema subset (same as validate_findings.py): $ref, enum, type, pattern, maxLength, required,
    properties, additionalProperties, if/then/else, items."""
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            target = target[part]
        return schema_check(value, target, root, path, errors)
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
                schema_check(value[k], sub, root, f"{path}.{k}", errors)
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            for k, v in value.items():
                if k not in schema.get("properties", {}) and v is not None:
                    schema_check(v, extra, root, f"{path}.{k}", errors)
    if "if" in schema:
        probe = []
        schema_check(value, schema["if"], root, path, probe)
        branch = schema.get("then") if not probe else schema.get("else")
        if branch:
            schema_check(value, branch, root, path, errors)
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            schema_check(item, schema["items"], root, f"{path}[{i}]", errors)


def extract_blocks(text):
    """-> (payloads, errors): every ```qa-findings block parsed as JSON."""
    payloads, errors = [], []
    for n, m in enumerate(BLOCK_RX.finditer(text or ""), 1):
        try:
            data = json.loads(m.group(1))
        except ValueError as ex:
            errors.append(f"блок {n}: не JSON ({ex})")
            continue
        if isinstance(data, list):
            data = {"findings": data}
        if not isinstance(data, dict):
            errors.append(f"блок {n}: ожидается объект или массив находок")
            continue
        payloads.append(data)
    return payloads, errors


def finding_schema(schema_path):
    root = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    fdef = json.loads(json.dumps(root["$defs"]["finding"]))
    fdef["required"] = [r for r in fdef.get("required", []) if r not in ("id", "fingerprint")]
    return root, fdef


def next_id_factory(existing, prefix="F-"):
    nums = [int(m.group(1)) for f in existing for m in [re.match(rf"^{re.escape(prefix)}(\d+)$", str(f.get("id") or ""))] if m]
    counter = [max(nums) if nums else 0]

    def nxt():
        counter[0] += 1
        return f"{prefix}{counter[0]:03d}"
    return nxt


def ingest(run_dir, text, schema_path, run_skeleton=None, thread=None, dry_run=False, partial=False,
           require_repro=True, prefix="F-"):
    """Merge executor blocks into <run_dir>/findings.json. Returns a report dict (also on errors)."""
    run_dir = Path(run_dir)
    payloads, errors = extract_blocks(text)
    report = {"blocks": len(payloads), "added": [], "skipped": [], "errors": list(errors), "warnings": [],
              "not_checked": 0, "questions": 0, "written": False}
    if not payloads and not errors:
        report["errors"].append("в тексте нет блока ```qa-findings``` — исполнитель должен вернуть находки JSON-блоком")
    root, fdef = finding_schema(schema_path)
    fpath = run_dir / "findings.json"
    if fpath.exists():
        data = json.loads(fpath.read_text(encoding="utf-8"))
    else:
        data = {"run": run_skeleton(run_dir) if run_skeleton else {}, "findings": []}
    findings = data.setdefault("findings", [])
    nxt = next_id_factory(findings, prefix)
    seen = {(f.get("title"), f.get("url") or f.get("screen")) for f in findings}
    new, not_checked, questions = [], [], []
    for b, payload in enumerate(payloads, 1):
        th = thread or payload.get("thread") or "agent"
        for i, f in enumerate(payload.get("findings") or []):
            where = f"блок {b}, находка {i + 1}"
            if not isinstance(f, dict):
                report["errors"].append(f"{where}: не объект")
                continue
            f = dict(f)
            if f.get("id"):
                f["source_id"] = f.pop("id")
            f.pop("fingerprint", None)
            f.setdefault("sources", [f"agent:{th}"])
            if not any(str(s).startswith("agent:") for s in f["sources"]):
                f["sources"] = list(f["sources"]) + [f"agent:{th}"]
            errs = []
            schema_check(f, fdef, root, where, errs)
            if errs:
                report["errors"].extend(errs)
                continue
            key = (f.get("title"), f.get("url") or f.get("screen"))
            if key in seen:
                report["skipped"].append({"where": where, "title": f.get("title"), "reason": "уже есть с тем же заголовком и адресом"})
                continue
            seen.add(key)
            if require_repro and not f.get("repro"):
                report["warnings"].append(f"{where} «{f.get('title')}»: нет repro — перед публикацией нужна ручная "
                                          "перепроверка (recheck.py set)")
            f["ingested"] = {"thread": th, "at": now()}
            new.append(f)
        for nc in payload.get("not_checked") or []:
            if isinstance(nc, dict) and nc.get("what"):
                not_checked.append(dict(nc, thread=th))
        for q in payload.get("questions") or []:
            questions.append({"thread": th, "question": q if isinstance(q, str) else json.dumps(q, ensure_ascii=False), "at": now()})
    if report["errors"] and not partial:
        return report
    for f in new:
        f["id"] = nxt()
        report["added"].append(f["id"])
    report["not_checked"], report["questions"] = len(not_checked), len(questions)
    if dry_run:
        return report
    if new or not_checked:
        findings.extend(new)
        if not_checked:
            data.setdefault("not_checked", []).extend(not_checked)
        fpath.parent.mkdir(parents=True, exist_ok=True)
        tmp = fpath.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(fpath)
        report["written"] = True
    if questions:
        qpath = run_dir / "questions.json"
        old = json.loads(qpath.read_text(encoding="utf-8")) if qpath.exists() else []
        qpath.write_text(json.dumps(old + questions, ensure_ascii=False, indent=1), encoding="utf-8")
    if text:
        raw = run_dir / "raw" / "messages"
        raw.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        name = re.sub(r"[^\w.-]+", "-", thread or (payloads[0].get("thread") if payloads else None) or "agent")
        (raw / f"{stamp}-{name}.md").write_text(text, encoding="utf-8")
    return report


def cli(argv, schema_path, run_skeleton, skill_name):
    import argparse
    import sys
    ap = argparse.ArgumentParser(prog="ingest_findings.py", description=f"""Findings of executors ({skill_name}) from a
```qa-findings``` JSON block of their final message -> <RUN_DIR>/findings.json.

  ingest_findings.py <RUN_DIR> --from message.txt [--thread qa-ux] [--dry-run] [--partial]
  ingest_findings.py <RUN_DIR> --stdin            (message text on stdin)
  ingest_findings.py example                      block format for executor instructions
Exit codes: 0 ok, 1 invalid findings (nothing written without --partial), 2 no block / bad input.""",
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--from", dest="src")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--text")
    ap.add_argument("--thread")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--partial", action="store_true", help="добавить валидные находки, даже если есть ошибки")
    a = ap.parse_args(argv)
    if a.run_dir == "example":
        print(EXAMPLE)
        return 0
    if a.text is not None:
        text = a.text
    elif a.stdin:
        text = sys.stdin.read()
    elif a.src:
        text = Path(a.src).read_text(encoding="utf-8")
    else:
        ap.error("нужен --from FILE, --stdin или --text")
    rep = ingest(a.run_dir, text, schema_path, run_skeleton, a.thread, a.dry_run, a.partial)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    if not rep["blocks"]:
        return 2
    return 1 if rep["errors"] else 0
