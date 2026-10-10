#!/usr/bin/env python3
"""Keep <OUTPUT_ROOT>/qa-runs/ out of git (references/run-files.md → «qa-runs/ и git»).

Thin wrapper over scripts/shared/qa_gitignore.py (default pattern qa-runs/, anchored to OUTPUT_ROOT):
  ensure  <OUTPUT_ROOT> [--allow-commit-results] [--config …] [--text "…"]
          right after OUTPUT_ROOT is known, before the run folder is created: qa-runs/ goes to .gitignore of the
          repository unless the user explicitly allowed committing the results (git.allow_commit_results);
          exit 0 done, 1 ask about already tracked qa-runs/ files (untrack), 2 error, 3 overridden by a "!" rule
  untrack <OUTPUT_ROOT> [--yes]             git rm -r --cached for qa-runs/ — only after the user's "yes"
  check / apply …                           state and the low-level writer (see the shared module)
  clips   <RUN_DIR>                         clips/ and recordings/ into <RUN_DIR>/.gitignore: clips of findings are never
                                            committed, even with git.allow_commit_results (clips.py finalize does it
                                            itself; references/clips.md); exit 0 done, 2 no run folder
Never touches files already tracked by git on its own.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_gitignore  # noqa: E402

DEFAULT_PATTERNS = ["qa-runs/"]


def clips_cmd(argv):
    ap = argparse.ArgumentParser(prog="gitignore_helper.py clips",
                                 description="clips/ и recordings/ в <RUN_DIR>/.gitignore (ролики находок не коммитятся)")
    ap.add_argument("run_dir")
    a = ap.parse_args(argv)
    if not Path(a.run_dir).is_dir():
        sys.stderr.write(f"gitignore_helper: нет папки прогона {a.run_dir}\n")
        return 2
    import clips  # noqa: E402
    print(json.dumps(clips.ensure_ignored(a.run_dir), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] == "clips":
        sys.exit(clips_cmd(sys.argv[2:]))
    qa_gitignore.main(DEFAULT_PATTERNS, label="site-qa-audit")
