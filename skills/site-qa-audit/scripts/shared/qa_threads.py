"""One place of truth for the results of executor threads (works together with qa_ingest.py).

The orchestrator does not rely on the hand-back message after the result is ingested: the thread result lives in files
  <RUN_DIR>/findings/<thread>.json   — ARRAY of the thread's findings (with the ids F-NNN assigned by ingest)
  <RUN_DIR>/coverage/<thread>.json   — what was checked / not checked, questions, self-reported metrics, messages
  <RUN_DIR>/run.json                 — the run (id, site, depth, mode, started_at): the «run» part of findings.json
and <RUN_DIR>/findings.json stays the merged working file of the run. A repeated notification with the same message
is recognised by its hash (raw/messages/index.json) and changes nothing.

  message_key(text) -> sha256 of the normalised message
  seen_message(run_dir, text) -> index entry or None
  remember_message(run_dir, text, thread, path)
  ensure_run_json(run_dir, run) -> path (written once; findings.json["run"] is the source when present)
  fill_dup_check(findings_json_path, ids) -> [ids that got dup_check "skipped"]
  dedupe_not_checked(findings_json_path) -> number of removed repeats
  write_thread_files(run_dir, thread, payloads) -> {"findings": path, "coverage": path, "count": n}

Stdlib only, Python 3.8+. Used by skills/*/scripts/ingest_findings.py.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def safe_name(thread):
    return re.sub(r"[^\w.-]+", "-", str(thread or "agent")).strip("-") or "agent"


def message_key(text):
    norm = re.sub(r"\s+", " ", (text or "").strip())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def seen_message(run_dir, text):
    return _load(Path(run_dir) / "raw" / "messages" / "index.json", {}).get(message_key(text))


def remember_message(run_dir, text, thread, path=None):
    idx_path = Path(run_dir) / "raw" / "messages" / "index.json"
    idx = _load(idx_path, {})
    idx[message_key(text)] = {"thread": thread, "at": now(), "file": str(path) if path else None}
    _save(idx_path, idx)


def ensure_run_json(run_dir, run):
    p = Path(run_dir) / "run.json"
    if not p.exists():
        data = _load(Path(run_dir) / "findings.json", {})
        _save(p, (data.get("run") if isinstance(data, dict) and data.get("run") else None) or run or {})
    return p


def fill_dup_check(findings_path, ids):
    data = _load(findings_path, None)
    if not isinstance(data, dict):
        return []
    filled = []
    for f in data.get("findings") or []:
        if f.get("id") in ids and not f.get("dup_check"):
            f["dup_check"] = "skipped"
            filled.append(f["id"])
    if filled:
        _save(findings_path, data)
    return filled


def dedupe_not_checked(findings_path):
    data = _load(findings_path, None)
    if not isinstance(data, dict) or not data.get("not_checked"):
        return 0
    seen, out = set(), []
    for x in data["not_checked"]:
        key = (x.get("thread"), x.get("what"), x.get("reason"))
        if key not in seen:
            seen.add(key)
            out.append(x)
    removed = len(data["not_checked"]) - len(out)
    if removed:
        data["not_checked"] = out
        _save(findings_path, data)
    return removed


def _merge_unique(old, new, key):
    seen = {key(x) for x in old}
    return old + [x for x in new if key(x) not in seen and not seen.add(key(x))]


def write_thread_files(run_dir, thread, payloads):
    """findings/<thread>.json (array from findings.json, ids assigned) + coverage/<thread>.json (merged)."""
    run_dir = Path(run_dir)
    name = safe_name(thread)
    data = _load(run_dir / "findings.json", {"findings": []})
    mine = [f for f in data.get("findings") or [] if (f.get("ingested") or {}).get("thread") == thread]
    fpath = run_dir / "findings" / f"{name}.json"
    _save(fpath, mine)
    cpath = run_dir / "coverage" / f"{name}.json"
    cov = _load(cpath, {})
    if not isinstance(cov, dict):
        cov = {}
    # the file may already exist with only progress metrics (coverage.py build before the result came)
    for key, empty in (("thread", thread), ("checked", []), ("not_checked", []), ("questions", []), ("metrics", {}),
                       ("messages", 0)):
        cov.setdefault(key, empty)
    for p in payloads:
        checked = [x if isinstance(x, dict) else {"what": str(x)} for x in p.get("checked") or []]
        cov["checked"] = _merge_unique(cov["checked"], checked, lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))
        nc = [x for x in p.get("not_checked") or [] if isinstance(x, dict) and x.get("what")]
        cov["not_checked"] = _merge_unique(cov["not_checked"], nc, lambda x: (x.get("what"), x.get("reason")))
        qs = [q if isinstance(q, str) else json.dumps(q, ensure_ascii=False) for q in p.get("questions") or []]
        cov["questions"] = _merge_unique(cov["questions"], qs, lambda x: x)
        if isinstance(p.get("metrics"), dict):
            cov["metrics"].update(p["metrics"])
    cov["messages"] = int(cov.get("messages") or 0) + 1
    cov["findings"] = len(mine)
    cov["updated_at"] = now()
    _save(cpath, cov)
    return {"findings": str(fpath), "coverage": str(cpath), "count": len(mine)}
