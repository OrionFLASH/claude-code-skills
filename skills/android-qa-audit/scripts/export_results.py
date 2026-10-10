#!/usr/bin/env python3
"""report_destinations: folder — copy only the final results of a run (summary.md, report.md, findings.json, the
screenshots referenced by findings and — 1.5.0 — their clips) to <PATH>/<YYYY-MM-DD>-<name>/; raw/, logs/, apk/,
recordings/, drafts/ are never copied (references/run-files.md → «Куда записаны итоги»).

Thin wrapper over scripts/shared/qa_export.py:
  export_results.py <RUN_DIR> --to <PATH> [--name NAME] [--screenshots referenced|all|none]
                    [--clips referenced|all|none] [--overwrite] [--dry-run] [--json]
  --clips referenced (default) — clips of findings (findings[].clips: mp4/webm, GIF, poster) into <dest>/clips/;
          all — everything in <RUN_DIR>/clips/ (also not yet attached); none — no clips.
  exit 0 copied, 1 conflicts (same name, different content — ask the user), 2 error
"""
import argparse
import filecmp
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import qa_export  # noqa: E402

CLIPS = "clips"
CLIP_EXT = {".mp4", ".webm", ".mov", ".gif", ".png"}
_plan = qa_export.plan


def clip_files(run, mode):
    d = run / CLIPS
    if mode == "none" or not d.is_dir():
        return []
    if mode == "all":
        return sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in CLIP_EXT)
    try:
        data = json.loads((run / "findings.json").read_text(encoding="utf-8")) if (run / "findings.json").is_file() else {}
    except ValueError:
        data = {}
    out = []
    for f in data.get("findings", []) if isinstance(data, dict) else []:
        for c in f.get("clips") or [] if isinstance(f, dict) else []:
            for key in ("file", "gif", "poster"):
                ref = c.get(key) if isinstance(c, dict) else None
                p = (run / ref) if ref else None
                if p and p.is_file() and qa_export.inside(p, d) and p.resolve() not in [x.resolve() for x in out]:
                    out.append(p)
    return out


def with_clips(mode):
    def plan(run, dest, shots_mode):
        rows, skipped = _plan(run, dest, shots_mode)
        have = {r["file"] for r in rows}
        for src in clip_files(run, mode):
            rel = src.resolve().relative_to(run.resolve()).as_posix()
            if rel in have:
                continue
            dst = dest / rel
            state = "new" if not dst.exists() else ("same" if dst.is_file() and filecmp.cmp(src, dst, shallow=False) else "conflict")
            rows.append({"file": rel, "src": str(src), "dst": str(dst), "state": state})
        return rows, skipped
    return plan


def main(argv):
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--clips", default="referenced", choices=["referenced", "all", "none"])
    ns, rest = pre.parse_known_args(argv)
    if "-h" in rest or "--help" in rest:
        try:
            qa_export.main(rest)
        finally:
            print("\nandroid-qa-audit: --clips referenced|all|none — ролики находок в <dest>/clips/ (по умолчанию "
                  "referenced: только те, на которые ссылаются находки; mp4/webm, GIF, постер).")
    qa_export.plan = with_clips(ns.clips)
    qa_export.main(rest)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
