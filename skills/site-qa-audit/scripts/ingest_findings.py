#!/usr/bin/env python3
"""Findings of executors from a ```qa-findings``` JSON block of their final message -> the files of the run.

  ingest_findings.py <RUN_DIR> --from message.txt [--thread qa-ux] [--dry-run] [--partial] [--force]
  ingest_findings.py <RUN_DIR> --stdin | --text "…"
  ingest_findings.py example          block format to paste into executor instructions (brief.py does it itself)

Executors (subagents) do not write findings.json or reports: they return the block in their last message, the
orchestrator saves the message and runs this script. ONE PLACE OF TRUTH after that (the message is not retold):
  findings.json                — merged findings of the run (ids F-NNN, `not_checked`), the working file
  findings/<thread>.json       — ARRAY of the thread's findings;  coverage/<thread>.json + .md — checked / not checked,
                                 questions, metrics (coverage.py);  run.json — the run;  raw/messages/ — the messages
A repeated notification with the same message changes nothing («уже принято», exit 0; --force — ingest again).
Validation — templates/finding.schema.json (id and fingerprint are assigned here and by fingerprint.py compute); a
finding without dup_check gets "skipped" (with a warning: the orchestrator checks it with fingerprint.py match).
Logic — shared/scripts/qa_ingest.py + shared/scripts/qa_threads.py.
Exit codes: 0 ok (or duplicate), 1 invalid findings (nothing written without --partial), 2 no block / bad input.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
sys.path.insert(0, str(HERE))
import miniyaml  # noqa: E402
import qa_ingest  # noqa: E402
import qa_threads  # noqa: E402

SCHEMA = HERE.parent / "templates" / "finding.schema.json"

EXAMPLE = """```qa-findings
{"thread": "<qa-id>",
 "findings": [
  {"direction": "<направление>", "check_id": "<id пункта чек-листа>", "type": "bug", "severity": "medium",
   "title": "Что не так и где", "url": "<URL>", "steps": ["1. …"], "expected": "…", "actual": "…",
   "screenshots": ["screenshots/<qa-id>-01-annotated.png"],
   "repro": {"url": "<URL>", "js": "<выражение: true, если дефект есть>"},
   "dup_check": "done", "dup_of": null, "dup_candidates": [],
   "variant": null, "verify": "<как проверить исправление: до — да, после — нет>",
   "sources": ["own:checklist"]}
 ],
 "checked": [{"what": "…", "direction": "<направление>"}],
 "not_checked": [{"what": "…", "reason": "…", "category": "time", "rule": null}],
 "metrics": {"minutes": 0},
 "questions": ["…"]}
```
findings — МАССИВ (может быть пустым). dup_check: done — сверено со срезом реестра из задания, skipped — не сверялось.
category у not_checked: time | forbidden | auth | environment | data | other (вторая волна — coverage.py again).
Проверить блок до отправки: python3 <SKILL_DIR>/scripts/validate_findings.py --array - (JSON блока на stdin)."""


def run_skeleton(run_dir):
    cfg = {}
    p = Path(run_dir) / "run-config.yaml"
    if p.exists():
        cfg = miniyaml.load_file(str(p)) or {}
    urls = (cfg.get("site") or {}).get("start_urls") or [""]
    return {"id": Path(run_dir).name, "site": urls[0], "depth": cfg.get("depth") or "smoke",
            "mode": "live" if cfg.get("mode") == "live" else "dry-run",
            "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def main(argv):
    ap = argparse.ArgumentParser(prog="ingest_findings.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--from", dest="src")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--text")
    ap.add_argument("--thread")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--partial", action="store_true", help="добавить валидные находки, даже если есть ошибки")
    ap.add_argument("--force", action="store_true", help="принять сообщение, даже если оно уже принималось")
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
    run_dir = Path(a.run_dir)
    seen = qa_threads.seen_message(run_dir, text)
    if seen and not a.force and not a.dry_run:
        rep = qa_ingest.ingest(run_dir, text, SCHEMA, run_skeleton, a.thread, dry_run=True)  # what it would do: nothing
        rep.update({"duplicate": True, "written": False, "thread": seen.get("thread"), "at": seen.get("at"),
                    "note": "это сообщение уже принято — повторное уведомление, ничего не изменено "
                            "(место правды: findings/<поток>.json, coverage/<поток>.md)"})
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 0
    rep = qa_ingest.ingest(run_dir, text, SCHEMA, run_skeleton, a.thread, a.dry_run, a.partial)
    if not rep["blocks"]:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 2
    if not a.dry_run and (rep["written"] or not rep["errors"]):
        fpath = run_dir / "findings.json"
        filled = qa_threads.fill_dup_check(fpath, set(rep["added"]))
        if filled:
            rep["warnings"].append(f"dup_check не указан у {', '.join(filled)} — записано skipped: сверить с реестром "
                                   "(fingerprint.py match)")
        qa_threads.dedupe_not_checked(fpath)
        payloads, _ = qa_ingest.extract_blocks(text)
        by_thread = {}
        for p in payloads:
            by_thread.setdefault(a.thread or p.get("thread") or "agent", []).append(p)
        rep["threads"] = {}
        import coverage  # noqa: E402 — coverage/<thread>.md with the automatic metrics
        for th, ps in by_thread.items():
            files = qa_threads.write_thread_files(run_dir, th, ps)
            md, m = coverage.build(run_dir, th)
            rep["threads"][th] = dict(files, coverage_md=str(md), minutes=m["minutes"], actions=m["action_checks"])
        rep["run_json"] = str(qa_threads.ensure_run_json(run_dir, run_skeleton(run_dir)))
        qa_threads.remember_message(run_dir, text, ",".join(by_thread))
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 1 if rep["errors"] else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
