#!/usr/bin/env python3
"""report_destinations: folder — copy only the final results of a run (summary.md, report.md, findings.json and
the screenshots referenced by findings) to <PATH>/<YYYY-MM-DD>-<name>/; raw/, logs/, apk/, recordings/, drafts/ are
never copied (references/run-files.md → «Куда записаны итоги»).

Thin wrapper over scripts/shared/qa_export.py:
  export_results.py <RUN_DIR> --to <PATH> [--name NAME] [--screenshots referenced|all|none] [--overwrite] [--dry-run] [--json]
  exit 0 copied, 1 conflicts (same name, different content — ask the user), 2 error
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import qa_export  # noqa: E402

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    qa_export.main()
