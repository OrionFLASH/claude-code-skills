#!/usr/bin/env python3
"""Findings of executors (stand threads) from a ```qa-findings``` JSON block of their final message ->
<RUN_DIR>/findings.json.

  ingest_findings.py <RUN_DIR> --from message.txt [--thread w2] [--dry-run] [--partial]
  ingest_findings.py <RUN_DIR> --stdin
  ingest_findings.py example          block format to paste into executor instructions (references/parallelism.md)

Executors (subagents) do not write findings.json or reports: they return the block in their last message, the
orchestrator saves the message and runs this script. Validation — templates/finding.schema.json (id and fingerprint
are assigned here and by fingerprint.py compute). Logic — shared/scripts/qa_ingest.py. Python 3.9+, stdlib only.
Exit codes: 0 ok, 1 invalid findings (nothing written without --partial), 2 no block.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
import miniyaml  # noqa: E402
import qa_ingest  # noqa: E402

SCHEMA = HERE.parent / "templates" / "finding.schema.json"


def run_skeleton(run_dir):
    cfg = {}
    p = Path(run_dir) / "run-config.yaml"
    if p.exists():
        cfg = miniyaml.load_file(str(p)) or {}
    return {"id": Path(run_dir).name, "app": (cfg.get("app") or {}).get("package") or "",
            "depth": cfg.get("depth") or "smoke", "mode": "live" if cfg.get("mode") == "live" else "dry-run",
            "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(qa_ingest.cli(sys.argv[1:], SCHEMA, run_skeleton, "android-qa-audit"))
