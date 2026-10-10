#!/usr/bin/env python3
"""Screenshots and clips of findings in a branch of a repository before creating issues (repos[].attachments: branch,
references/repo-sync.md → «Вложения веткой»). Order: plan → «да» → push → verify → issues.

Thin wrapper over scripts/shared/qa_attachments.py:
  attachments.py plan <RUN_DIR> --repo owner/repo --branch qa-screens --dir qa/<run id>          (no network)
  attachments.py push <RUN_DIR> --repo owner/repo --branch qa-screens --dir qa/<run id> --yes [--message M]
  attachments.py verify <RUN_DIR> --repo owner/repo --branch qa-screens --dir qa/<run id>
Links: https://github.com/<repo>/blob/<branch>/<dir>/<file>?raw=true → render_draft.py --attachments-base <base>.
1.5.0: without --file the set also includes the clips of findings (findings[].clips: the mp4 and its GIF) — only
viewed ones (finding.py clip-viewed), with the same status filter as screenshots; --no-clips — screenshots only.
Clips are public once pushed: only with the same consent as the screenshots (references/safety-rules.md).
Exit: 0 ok, 1 a file is missing or not in the branch, 2 error.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import qa_attachments  # noqa: E402

_screens_only = qa_attachments.findings_files


def clip_files(run_dir):
    """mp4 + GIF of viewed clips of the findings to publish (the shared module collects only screenshots)."""
    data = json.loads((Path(run_dir) / "findings.json").read_text(encoding="utf-8"))
    out = []
    for f in data.get("findings", []) if isinstance(data, dict) else data:
        if (f.get("status") or "NEW") in qa_attachments.SKIP_STATUSES or (f.get("evidence") or {}).get("sensitive"):
            continue
        for c in f.get("clips") or []:
            if isinstance(c, dict) and c.get("viewed"):
                out += [x for x in (c.get("file"), c.get("gif")) if x and x not in out]
    return out


def findings_files(run_dir):
    files = _screens_only(run_dir)
    return files + [x for x in clip_files(run_dir) if x not in files]


def main(argv):
    if "--no-clips" in argv:
        argv = [x for x in argv if x != "--no-clips"]
    else:
        qa_attachments.findings_files = findings_files    # plan() looks the collector up at call time
    if "-h" in argv or "--help" in argv:
        try:
            return qa_attachments.cli(argv, "android-qa-audit")
        finally:
            print("\nandroid-qa-audit: без --file в набор входят и ролики находок (mp4 и GIF, только просмотренные); "
                  "--no-clips — только скриншоты.")
    return qa_attachments.cli(argv, "android-qa-audit")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
