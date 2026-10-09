#!/usr/bin/env python3
"""GitHub issue forms of the target repository (references/repo-sync.md → «Их формы issue»): read-only towards GitHub.

Thin wrapper over scripts/shared/qa_issueforms.py:
  issue_forms.py fetch --repo owner/repo --out <RUN_DIR>/raw/forms/owner__repo        their .github/ISSUE_TEMPLATE
  issue_forms.py show <form.yml> [--json]                                              fields, required, options
  issue_forms.py map <form.yml> --values values.json [--overrides map.json] [--json]   «поле формы ← поле находки»
  issue_forms.py render <form.yml> --values values.json [--overrides map.json] [--title T] [--out body.md]
Usually not called by hand: render_draft.py … --form auto --forms-dir <dir> builds values from findings.json.
Exit: 0 ok, 1 problems (ask the user: dropdown value, required field, required checkbox), 2 error.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import qa_issueforms  # noqa: E402

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(qa_issueforms.cli(sys.argv[1:], "android-qa-audit"))
