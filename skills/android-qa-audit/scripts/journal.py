#!/usr/bin/env python3
"""Run journal <RUN_DIR>/journal.md for android-qa-audit (references/run-files.md).

Thin wrapper over the shared module scripts/shared/runjournal.py (source of truth: shared/scripts/ of the
skills repository). Commands: init / todo / done / note / status — see `journal.py -h`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import runjournal  # noqa: E402

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    runjournal.main()
