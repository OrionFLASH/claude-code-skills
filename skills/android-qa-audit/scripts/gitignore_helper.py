#!/usr/bin/env python3
"""Keep <OUTPUT_ROOT>/qa-runs/ and Android build artifacts out of git (references/run-files.md).

Thin wrapper over scripts/shared/qa_gitignore.py with Android defaults:
  patterns: qa-runs/ (anchored to OUTPUT_ROOT), *.apk, *.aab, *.apks, *.keystore (anywhere in the repository)
  check <OUTPUT_ROOT>                       exit 0 — nothing to ask, 1 — ask the user, 2 — error
  apply <OUTPUT_ROOT> --mode gitignore|exclude|keep [--pattern qa-runs/ ...]   only after the user's answer
`--pattern` (repeatable) replaces the defaults, e.g. only qa-runs/: --pattern qa-runs/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import qa_gitignore  # noqa: E402

DEFAULT_PATTERNS = ["qa-runs/", "*.apk", "*.aab", "*.apks", "*.keystore"]

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    qa_gitignore.main(DEFAULT_PATTERNS, label="android-qa-audit")
