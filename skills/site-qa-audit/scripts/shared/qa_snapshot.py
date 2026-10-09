"""Frozen copy of a folder inside the run folder: the skill (<RUN_DIR>/skill) or the app under test (<RUN_DIR>/app).

A long run must not depend on the installed skill folder (a plugin update or a cleaner can remove it in the middle of
the run) and must not touch the original app (tests may break its files and data). So the run works on a copy.

  copy_tree(src, dst, exclude=(...), link_prefixes=(...), mode="auto") -> report dict

mode:
  copy  — every file is copied (independent copy: use it for an app under test, which the run may modify);
  link  — every file is a hard link (no extra space; survives deletion of the source folder, but a file changed IN
          PLACE changes in both places — never use it for a folder the run writes to);
  auto  — hard links for files under link_prefixes (e.g. "scripts/node/node_modules"), copies for the rest;
          a failed link (other disk, no permission) falls back to a copy.
Symlinks inside src are never followed and never copied: they are listed in report["skipped_symlinks"]
(a copy cannot point outside its folder). Excluded: glob patterns matched against the relative path and each name.

write_meta(dst, meta) / read_meta(dst): <dst>/.snapshot.json with the source, version, time and counters.
Stdlib only, Python 3.8+. Used by skills/*/scripts/skill_snapshot.py and local_app.py.
"""
import fnmatch
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

META = ".snapshot.json"
DEFAULT_EXCLUDE = (".git", "__pycache__", "*.pyc", ".DS_Store", "Thumbs.db", META)


def _excluded(rel_posix, patterns):
    parts = rel_posix.split("/")
    return any(fnmatch.fnmatch(rel_posix, p) or any(fnmatch.fnmatch(x, p) for x in parts) for p in patterns)


def copy_tree(src, dst, exclude=DEFAULT_EXCLUDE, link_prefixes=(), mode="auto"):
    """Copy src -> dst (dst is created; existing files are replaced). Returns a report dict."""
    if mode not in ("auto", "copy", "link"):
        raise ValueError(f"mode: auto | copy | link, получено {mode!r}")
    src, dst = Path(src), Path(dst)
    if not src.is_dir():
        raise FileNotFoundError(f"нет папки {src}")
    if dst.resolve() == src.resolve():
        raise ValueError(f"папка копии совпадает с исходной: {src}")
    # The copy may live inside the source (qa-runs/ inside the project): that subtree is never copied into itself.
    inner = dst.resolve().relative_to(src.resolve()).as_posix() if src.resolve() in dst.resolve().parents else None
    rep = {"src": str(src), "dst": str(dst), "mode": mode, "files": 0, "bytes": 0, "linked": 0, "copied": 0,
           "link_fallbacks": 0, "skipped_symlinks": [], "excluded": 0}
    dst.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(src, followlinks=False):
        rel_root = Path(root).relative_to(src)
        keep = []
        for d in sorted(dirs):
            rel = (rel_root / d).as_posix()
            if inner and rel == inner:
                rep["excluded"] += 1
            elif os.path.islink(os.path.join(root, d)):
                rep["skipped_symlinks"].append(rel)
            elif _excluded(rel, exclude):
                rep["excluded"] += 1
            else:
                keep.append(d)
        dirs[:] = keep
        (dst / rel_root).mkdir(parents=True, exist_ok=True)
        for name in sorted(files):
            s = Path(root) / name
            rel = (rel_root / name).as_posix()
            if s.is_symlink():
                rep["skipped_symlinks"].append(rel)
                continue
            if _excluded(rel, exclude):
                rep["excluded"] += 1
                continue
            t = dst / rel_root / name
            if t.exists() or t.is_symlink():
                t.unlink()
            want_link = mode == "link" or (mode == "auto" and any(rel == p or rel.startswith(p.rstrip("/") + "/")
                                                                  for p in link_prefixes))
            done = False
            if want_link:
                try:
                    os.link(s, t)
                    rep["linked"] += 1
                    done = True
                except OSError:
                    rep["link_fallbacks"] += 1
            if not done:
                shutil.copy2(s, t)
                rep["copied"] += 1
            rep["files"] += 1
            rep["bytes"] += s.stat().st_size
    return rep


def write_meta(dst, meta):
    data = dict(meta, created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    (Path(dst) / META).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def read_meta(dst):
    p = Path(dst) / META
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def human_size(n):
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024 or unit == "ГБ":
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}"
        n /= 1024.0
