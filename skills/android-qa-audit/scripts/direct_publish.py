#!/usr/bin/env python3
"""Direct publication mode (references/repo-sync.md → «Прямая публикация») — android-qa-audit.

  direct_publish.py check  <RUN_DIR> --id F-001 --repo owner/repo [--registry <RUN_DIR>/raw/issues-owner__repo.json]
                           [--ack-candidates]
  direct_publish.py record <RUN_DIR> --id F-001 --repo owner/repo --number 12 --url https://github.com/owner/repo/issues/12
  direct_publish.py next   <RUN_DIR> --repo owner/repo
  direct_publish.py status <RUN_DIR>

For every finding: recheck.py run (reproduced twice) -> check (gate + duplicate search in the gh issue export) ->
the printed commands (render body, gh issue create) -> record. Nothing is published by the script itself; with
repos[].confirm_before_publish the orchestrator asks «да» per finding. Exit codes of check: 0 publish now,
1 gate closed, 2 fuzzy candidates to read, 3 already published / exact duplicate. Logic — shared/scripts/qa_direct.py.
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
]


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    # default issue exports: every <RUN_DIR>/raw/issues-*.json (gh issue list … --json …)
    defaults = []
    if len(argv) > 1 and "--registry" not in argv:
        defaults = [str(p.relative_to(argv[1])) for p in sorted(Path(argv[1]).glob("raw/issues-*.json"))] if Path(argv[1]).is_dir() else []
    sys.exit(qa_direct.cli(argv, "android-qa-audit", HERE / "fingerprint.py", COMMANDS, defaults or ["raw/issues.json"],
                           miniyaml.load_file))
