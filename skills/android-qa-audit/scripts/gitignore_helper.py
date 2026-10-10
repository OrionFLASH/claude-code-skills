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
  ensure_run_ignore(run_dir) (module function, 1.5.0) — <RUN_DIR>/.gitignore with clips/, recordings/, raw/rolling-*/:
             screen recordings are never committed, not even with git.allow_commit_results (clip_android.py, finding.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import qa_gitignore  # noqa: E402

DEFAULT_PATTERNS = ["qa-runs/", "*.apk", "*.aab", "*.apks", "*.xapk", "*.keystore", "*.jks"]
# 1.5.0: screen recordings of a run are never committed — not even with git.allow_commit_results (they show the screen
# over time and may contain personal data): <RUN_DIR>/.gitignore, written by clip_android.py and finding.py clip.
RUN_IGNORE = ["clips/", "recordings/", "raw/rolling-*/"]


def ensure_run_ignore(run_dir):
    """<RUN_DIR>/.gitignore with clips/, recordings/, raw/rolling-*/ (missing lines appended). Returns the path."""
    p = Path(run_dir) / ".gitignore"
    have = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    add = [x for x in RUN_IGNORE if x not in have]
    if add:
        p.parent.mkdir(parents=True, exist_ok=True)
        head = [] if have else ["# android-qa-audit: записи экрана прогона не коммитятся (references/clips.md)"]
        p.write_text("\n".join(have + head + add) + "\n", encoding="utf-8")
    return p

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    qa_gitignore.main(DEFAULT_PATTERNS, label="android-qa-audit")
