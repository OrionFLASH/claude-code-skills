#!/usr/bin/env python3
"""report_destinations: folder — copy only the final results of a run (summary.md, report.md, findings.json and
the screenshots referenced by findings) to <PATH>/<YYYY-MM-DD>-<name>/; raw/, logs/, apk/, recordings/, drafts/ are
never copied (references/run-files.md → «Куда записаны итоги»).

Thin wrapper over scripts/shared/qa_export.py:
  export_results.py <RUN_DIR> --to <PATH> [--name NAME] [--screenshots referenced|all|none] [--clips referenced|all|none]
                    [--overwrite] [--dry-run] [--json]
  --clips (1.7.0, references/clips.md): referenced (default) — the clip files of findings[].clips[] (mp4/webm, GIF,
  poster) that lie in <RUN_DIR>/clips/; all — every clip file of <RUN_DIR>/clips/; none — no clips. Copied to
  <dest>/clips/ with the same relative paths, so the links of report.md keep working.
  exit 0 copied, 1 conflicts (same name, different content — ask the user), 2 error
"""
import filecmp
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
sys.path.insert(0, str(HERE))
import clips as clipmod  # noqa: E402
import qa_export  # noqa: E402

CLIPS = "clips"
CLIP_FILES = {".mp4", ".webm", ".mov", ".gif", ".png"}


def clip_sources(run, mode):
    """(list of Path inside RUN_DIR/clips, skipped [(ref, reason)])."""
    cdir = run / CLIPS
    if mode == "none" or not cdir.is_dir():
        return [], []
    if mode == "all":
        return sorted(p for p in cdir.rglob("*") if p.is_file() and p.suffix.lower() in CLIP_FILES), []
    try:
        data = json.loads((run / "findings.json").read_text(encoding="utf-8")) if (run / "findings.json").is_file() else {}
    except ValueError:
        data = {}
    items = data.get("findings", []) if isinstance(data, dict) else (data or [])
    out, skipped = [], []
    for f in items if isinstance(items, list) else []:
        for c in clipmod.clips_of(f) if isinstance(f, dict) else []:
            for key in ("file", "gif", "poster"):
                ref = c.get(key)
                if not ref:
                    continue
                p = run / ref
                if not p.is_file():
                    skipped.append((ref, "файла нет"))
                elif not qa_export.inside(p, cdir):
                    skipped.append((ref, f"не в {CLIPS}/ папки прогона"))
                elif p.resolve() not in [x.resolve() for x in out]:
                    out.append(p)
    return out, skipped


def main(argv):
    mode = "referenced"
    rest = []
    i = 0
    while i < len(argv):
        x = argv[i]
        if x == "--clips" or x.startswith("--clips="):
            val = x.split("=", 1)[1] if "=" in x else (argv[i + 1] if i + 1 < len(argv) else "")
            i += 1 if "=" in x else 2
            if val not in ("referenced", "all", "none"):
                sys.stderr.write("export_results: --clips referenced|all|none\n")
                sys.exit(2)
            mode = val
            continue
        rest.append(x)
        i += 1
    if "-h" in rest or "--help" in rest:
        print(__doc__)
    orig = qa_export.plan
    counted = {"clips": 0}

    def plan(run, dest, shots_mode):
        rows, skipped = orig(run, dest, shots_mode)
        files, cskip = clip_sources(run, mode)
        for src in files:
            rel = src.resolve().relative_to(run.resolve())
            dst = dest / rel
            state = "new" if not dst.exists() else ("same" if dst.is_file() and filecmp.cmp(src, dst, shallow=False) else "conflict")
            rows.append({"file": rel.as_posix(), "src": str(src), "dst": str(dst), "state": state})
        counted["clips"] = len(files)
        return rows, skipped + cskip

    qa_export.plan = plan  # the shared main() copies, reports conflicts and prints the rows — clips included
    try:
        qa_export.main(rest)
    except SystemExit as ex:
        if counted["clips"] and "--json" not in rest:
            sys.stdout.flush()
            sys.stderr.write(f"роликов в наборе: {counted['clips']} (--clips {mode})\n")
        raise ex


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
