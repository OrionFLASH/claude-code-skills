#!/usr/bin/env python3
"""Direct publication mode (G-6, references/repo-sync.md §4a) — site-qa-audit.

  direct_publish.py check  <RUN_DIR> --id F-001 --repo owner/repo [--registry <RUN_DIR>/registry.json] [--ack-candidates]
  direct_publish.py record <RUN_DIR> --id F-001 --repo owner/repo --number 12 --url https://github.com/owner/repo/issues/12
  direct_publish.py next   <RUN_DIR> --repo owner/repo
  direct_publish.py status <RUN_DIR>

For every finding: recheck.py run (reproduced twice) -> check (gate + duplicate search in registry.json) -> the printed
commands (render body, gh issue create, screenshots with publish_web.mjs --attach-to) -> record. Exit codes of
check: 0 publish now, 1 gate closed, 2 fuzzy candidates to read, 3 already published / exact duplicate.
Logic — shared/scripts/qa_direct.py.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
import miniyaml  # noqa: E402
import qa_direct  # noqa: E402

S = str(HERE)
COMMANDS = [
    f"python3 {S}/render_draft.py detailed {{run_dir}}/findings.json --id {{id}} --config {{run_dir}}/run-config.yaml "
    f"--repo {{repo}} --body-only --out {{run_dir}}/published/{{slug}}/{{id}}.md   # печатает TITLE: …",
    "gh issue create -R {repo} --title \"<TITLE>\" --body-file {run_dir}/published/{slug}/{id}.md   # после «да», если confirm_before_publish",
    f"node {S}/node/publish_web.mjs --attach-to <N> --repo {{repo}} --shots-dir {{run_dir}}/screenshots "
    "--cdp http://127.0.0.1:9222 --confirm-publish   # screenshots: web-upload (references/web-upload.md)",
]

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(qa_direct.cli(sys.argv[1:], "site-qa-audit", HERE / "fingerprint.py", COMMANDS, ["registry.json"],
                           miniyaml.load_file))
