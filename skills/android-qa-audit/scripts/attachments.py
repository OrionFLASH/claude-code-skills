#!/usr/bin/env python3
"""Screenshots of findings in a branch of a repository before creating issues (repos[].attachments: branch,
references/repo-sync.md → «Вложения веткой»). Order: plan → «да» → push → verify → issues.

Thin wrapper over scripts/shared/qa_attachments.py:
  attachments.py plan <RUN_DIR> --repo owner/repo --branch qa-screens --dir qa/<run id>          (no network)
  attachments.py push <RUN_DIR> --repo owner/repo --branch qa-screens --dir qa/<run id> --yes [--message M]
  attachments.py verify <RUN_DIR> --repo owner/repo --branch qa-screens --dir qa/<run id>
Links: https://github.com/<repo>/blob/<branch>/<dir>/<file>?raw=true → render_draft.py --attachments-base <base>.
Exit: 0 ok, 1 a file is missing or not in the branch, 2 error.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import qa_attachments  # noqa: E402

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(qa_attachments.cli(sys.argv[1:], "android-qa-audit"))
