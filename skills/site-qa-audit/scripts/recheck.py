#!/usr/bin/env python3
"""Independent re-check of findings (repro) and the publication gate — site-qa-audit.

  recheck.py run   <RUN_DIR> [--id F-001] [--times 2] [--dry-run]     re-run finding.repro N times
  recheck.py set   <RUN_DIR> --id F-001 --status confirmed --by "qa-verify: Chrome 1440×900, шаги 1–3"
  recheck.py legal <RUN_DIR> --id F-007 --by "второй исполнитель qa-legal" --result confirmed --norm "…"
  recheck.py gate  <RUN_DIR>                                          exit 1 if something may not be published

finding.repro — how to re-run the measurement with one command:
  {"url": "https://example.com/", "js": "document.querySelectorAll('h1').length !== 1"}       bug present = true
  {"url": "…", "selector": "#bell", "assert": "b.w < 24 || b.h < 24", "device": "pixel7"}      b = box {x, y, w, h}
  {"url": "…", "js": "…", "size": "1440x813", "locale": "de-DE", "setup": "<RUN_DIR>/setup/open-menu.js"}
  {"argv": ["node", "<SKILL_DIR>/scripts/node/occlusion.js", "…"], "expect": "\\"total\\": [1-9]"}
The short forms run scripts/node/repro.js under guard.js (rules.json of the run, if present). Only the skill's own
scripts are run (shared/scripts/qa_recheck.py). Exit codes: 0 ok, 1 not confirmed / gate closed, 2 bad input.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
import qa_recheck  # noqa: E402

SKILL_DIR = str(HERE.parent)
SHORT = ("url", "js", "selector", "assert", "device", "size", "locale", "setup", "wait", "state", "read_only")


def translate(repro, subst):
    """Short site form -> argv of node/repro.js."""
    if repro.get("argv") or repro.get("cmd") or not repro.get("url"):
        return None
    argv = ["node", str(HERE / "node" / "repro.js"), "--url", qa_recheck.substitute(str(repro["url"]), subst)]
    for key in ("js", "selector", "assert", "device", "size", "locale", "setup", "wait", "state"):
        if repro.get(key) not in (None, ""):
            argv += [f"--{key}", qa_recheck.substitute(str(repro[key]), subst)]
    if repro.get("read_only"):
        argv.append("--read-only")
    rules = Path(subst["RUN_DIR"]) / "rules.json"
    if rules.exists():
        argv += ["--rules", str(rules), "--log", str(Path(subst["RUN_DIR"]) / "logs" / "blocked.jsonl")]
    return argv


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(qa_recheck.cli(sys.argv[1:], "site-qa-audit", SKILL_DIR, translate))
