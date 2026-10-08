#!/usr/bin/env python3
"""Keep <OUTPUT_ROOT>/qa-runs/ and Android builds and signing keys out of git (references/run-files.md).

Thin wrapper over scripts/shared/qa_gitignore.py with Android defaults:
  results:   qa-runs/ (anchored to OUTPUT_ROOT) — ignored unless git.allow_commit_results (explicit permission)
  artifacts: *.apk, *.aab, *.apks, *.xapk, *.keystore, *.jks (anywhere in the repository) — ignored unless
             git.allow_commit_apk (a separate explicit permission)
  ensure  <OUTPUT_ROOT> [--allow-commit-results] [--allow-commit-apk] [--config …] [--text "…"]
          right after OUTPUT_ROOT is known, before the run folder is created; exit 0 done, 1 ask about
          already tracked qa-runs/ files (untrack), 2 error, 3 overridden by a "!" rule
  untrack <OUTPUT_ROOT> [--yes]             git rm -r --cached for qa-runs/ — only after the user's "yes"
  check / apply …                           state and the low-level writer (see the shared module)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import qa_gitignore  # noqa: E402

DEFAULT_PATTERNS = ["qa-runs/", "*.apk", "*.aab", "*.apks", "*.xapk", "*.keystore", "*.jks"]

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    qa_gitignore.main(DEFAULT_PATTERNS, label="android-qa-audit")
