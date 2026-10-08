#!/usr/bin/env python3
"""Keep <OUTPUT_ROOT>/qa-runs/ out of git (references/run-files.md → «qa-runs/ и git»).

Thin wrapper over scripts/shared/qa_gitignore.py (default pattern qa-runs/, anchored to OUTPUT_ROOT):
  ensure  <OUTPUT_ROOT> [--allow-commit-results] [--config …] [--text "…"]
          right after OUTPUT_ROOT is known, before the run folder is created: qa-runs/ goes to .gitignore of the
          repository unless the user explicitly allowed committing the results (git.allow_commit_results);
          exit 0 done, 1 ask about already tracked qa-runs/ files (untrack), 2 error, 3 overridden by a "!" rule
  untrack <OUTPUT_ROOT> [--yes]             git rm -r --cached for qa-runs/ — only after the user's "yes"
  check / apply …                           state and the low-level writer (see the shared module)
Never touches files already tracked by git on its own.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import qa_gitignore  # noqa: E402

DEFAULT_PATTERNS = ["qa-runs/"]

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    qa_gitignore.main(DEFAULT_PATTERNS, label="site-qa-audit")
