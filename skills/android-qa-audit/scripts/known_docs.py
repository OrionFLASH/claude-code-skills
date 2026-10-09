#!/usr/bin/env python3
"""Documents of the project «what is known / intended / approximate» (references/repo-sync.md → «Уже известно»).

Thin wrapper over scripts/shared/qa_known.py:
  known_docs.py fetch --repo owner/repo --path docs/KNOWN.md [--path docs/] --out <RUN_DIR>/raw/known   (read-only)
  known_docs.py check <RUN_DIR>/findings.json --doc <file or folder> [--doc …] [--json]   candidates with quotes
  known_docs.py set <RUN_DIR>/findings.json --id F-006 --doc <file> --quote "…"          status KNOWN — not published
Nothing is excluded automatically: read the quote first. Exit: 0 no candidates, 1 candidates found, 2 error.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import qa_known  # noqa: E402

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(qa_known.cli(sys.argv[1:], "android-qa-audit"))
