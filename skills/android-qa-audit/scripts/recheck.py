#!/usr/bin/env python3
"""Independent re-check of findings (repro) and the publication gate — android-qa-audit.

  recheck.py run   <RUN_DIR> --subst SERIAL=emulator-5554 [--id F-001] [--times 2] [--dry-run]
  recheck.py set   <RUN_DIR> --id F-001 --status confirmed --by "w-verify: emulator-5556, API 34, шаги 1–3"
  recheck.py legal <RUN_DIR> --id F-007 --by "второй исполнитель" --result confirmed --norm "…"
  recheck.py gate  <RUN_DIR>                                          exit 1 if something may not be published

finding.repro — how to re-run the check with one command (only the skill's scripts):
  {"adb": ["find", "--text", "Купить"], "expect_exit": 0}           adb_helpers.py find — the defect element is there
  {"adb": "crashes", "expect": "\\"crashes\\": \\\\[\\\\{"}                    a crash is in the log again
  {"argv": ["python3", "<SKILL_DIR>/scripts/adb_helpers.py", "start-time", "--mode", "cold"], "expect": "…"}
The short form {"adb": …} runs `adb_helpers.py <args> --serial <SERIAL> --run-dir <RUN_DIR>` (SERIAL — from
repro.serial or --subst SERIAL=…); every action inside goes through guard.py as usual. Exit codes: 0 ok,
1 not confirmed / gate closed, 2 bad input. Logic — shared/scripts/qa_recheck.py.
"""
import shlex
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
import qa_recheck  # noqa: E402

SKILL_DIR = str(HERE.parent)


def translate(repro, subst):
    """{"adb": [...] | "..."} -> argv of adb_helpers.py with --serial and --run-dir."""
    if repro.get("argv") or repro.get("cmd") or not repro.get("adb"):
        return None
    args = repro["adb"] if isinstance(repro["adb"], list) else shlex.split(str(repro["adb"]))
    args = [qa_recheck.substitute(str(x), subst) for x in args]
    if "--serial" not in args:
        serial = repro.get("serial") or subst.get("SERIAL")
        if serial:
            args += ["--serial", qa_recheck.substitute(str(serial), subst)]
    if "--run-dir" not in args:
        args += ["--run-dir", subst["RUN_DIR"]]
    return [sys.executable, str(HERE / "adb_helpers.py"), *args]


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # guard unavailable in adb_helpers.py is exit 6 (4 there means «element not found / not supported»)
    sys.exit(qa_recheck.cli(sys.argv[1:], "android-qa-audit", SKILL_DIR, translate, error_codes=(6,)))
