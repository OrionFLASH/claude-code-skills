#!/usr/bin/env python3
"""Copy of a local web app (opened as file://) inside the run folder: tests may break its files and data, the
original stays untouched (references/local-files.md).

  local_app.py copy <APP_DIR> <RUN_DIR> [--name app] [--start index.html] [--exclude PATTERN ...] [--update-config]
                    [--force] [--json]
  local_app.py url <PATH>                      file:// URL of a local file or folder (absolute, percent-encoded)

copy: <APP_DIR> -> <RUN_DIR>/<name>/ — an independent copy (never hard links: the run may write to it). Not copied:
.git, caches, qa-runs/ (and the run folder itself, if it is inside the app), --exclude patterns; symlinks are never
followed (listed in the output — the guard would refuse them anyway). Prints the start URL of the copy.
--update-config: <RUN_DIR>/run-config.yaml → site.start_urls (file:// inside the original app -> the same path inside
the copy; --start, if given, first), site.local_roots: [copy] (the original folder is NOT allowed any more),
rules.json is re-exported when it exists and <RUN_DIR>/playwright-cli.json allows file:// for playwright-cli.
An existing copy is kept (exit 3) unless --force. Exit codes: 0 ok, 1 bad input, 3 copy exists.
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
sys.path.insert(0, str(HERE))
import qa_snapshot  # noqa: E402
import runcfg  # noqa: E402

EXCLUDE = qa_snapshot.DEFAULT_EXCLUDE + ("qa-runs", ".cache", ".idea", ".vscode")


def file_url(p):
    return Path(os.path.abspath(os.path.expanduser(str(p)))).as_uri()


def remap(urls, src, dst):
    """file:// URLs inside src -> the same relative path inside dst (others unchanged)."""
    out = []
    for u in urls or []:
        parts = urlsplit(str(u))
        if parts.scheme.lower() == "file":
            p = os.path.normpath(url2pathname(parts.path))
            for base in (os.path.normpath(str(src)), os.path.realpath(str(src))):
                if p == base or p.startswith(base.rstrip(os.sep) + os.sep):
                    rel = os.path.relpath(p, base)
                    newp = Path(dst) if rel == "." else Path(dst) / rel
                    u = newp.as_uri() + (("?" + parts.query) if parts.query else "") + (("#" + parts.fragment) if parts.fragment else "")
                    break
        out.append(u)
    return out


def copy(app, run_dir, name="app", start=None, exclude=(), update_config=False, force=False):
    app, run_dir = Path(os.path.expanduser(app)), Path(run_dir)
    if not app.is_dir():
        return 1, {"ok": False, "error": f"нет папки приложения: {app}"}
    dst = run_dir / name
    if dst.exists() and any(dst.iterdir()) and not force:
        meta = qa_snapshot.read_meta(dst) or {}
        return 3, {"ok": False, "app_dir": str(dst), "from": meta.get("from"),
                   "error": f"копия уже есть: {dst} — работать в ней или --force, чтобы скопировать заново"}
    if dst.exists() and force:
        shutil.rmtree(dst)
    rep = qa_snapshot.copy_tree(app, dst, exclude=EXCLUDE + tuple(exclude), mode="copy")
    qa_snapshot.write_meta(dst, {"from": str(app), "kind": "app", **{k: rep[k] for k in ("files", "bytes", "copied")}})
    start_path = dst / start if start else next((dst / n for n in ("index.html", "index.htm") if (dst / n).is_file()), dst)
    res = {"ok": True, "app_dir": str(dst), "from": str(app), "files": rep["files"], "size": qa_snapshot.human_size(rep["bytes"]),
           "skipped_symlinks": rep["skipped_symlinks"], "start_url": start_path.as_uri(), "local_root": str(dst)}
    if update_config:
        cfg_path = run_dir / "run-config.yaml"
        cfg = runcfg.load(cfg_path)
        site = dict(cfg.get("site") or {})
        urls = remap(site.get("start_urls") or [], app, dst)
        if start or not any(str(u).startswith(dst.as_uri()) for u in urls):
            urls = [res["start_url"]] + [u for u in urls if u != res["start_url"]]
        site["start_urls"] = urls
        site["local_roots"] = [str(dst)]
        site["allowed_domains"] = [a for a in site.get("allowed_domains") or []
                                   if not str(a).strip().lower().startswith("file")]
        runcfg.set_top(cfg_path, "site", site)
        res["config_updated"] = str(cfg_path)
        res["rules"] = runcfg.reexport_rules(run_dir)
        import browser_mode  # noqa: E402 — playwright-cli needs file:// access for a local app
        res["playwright_cli_config"] = str(browser_mode.write_cli_config(run_dir))
    return 0, res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("copy", help="копия приложения в <RUN_DIR>/<name>")
    c.add_argument("app_dir")
    c.add_argument("run_dir")
    c.add_argument("--name", default="app")
    c.add_argument("--start", help="стартовый файл относительно папки приложения (по умолчанию index.html)")
    c.add_argument("--exclude", action="append", default=[], help="маска пути, которую не копировать (можно несколько)")
    c.add_argument("--update-config", action="store_true")
    c.add_argument("--force", action="store_true")
    c.add_argument("--json", action="store_true")
    u = sub.add_parser("url", help="file:// URL пути")
    u.add_argument("path")
    a = ap.parse_args()
    if a.cmd == "url":
        print(file_url(a.path))
        return
    code, res = copy(a.app_dir, a.run_dir, a.name, a.start, a.exclude, a.update_config, a.force)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    elif code == 0:
        print(f"копия приложения: {res['app_dir']} ({res['files']} файлов, {res['size']}) из {res['from']}")
        print(f"  стартовый URL: {res['start_url']}")
        if res["skipped_symlinks"]:
            print(f"  симлинки не скопированы ({len(res['skipped_symlinks'])}): {', '.join(res['skipped_symlinks'][:5])}")
        if res.get("config_updated"):
            print(f"  run-config.yaml: start_urls и local_roots → копия" +
                  (f"; rules.json пересобран" if res.get("rules") and res["rules"]["code"] == 0 else ""))
    else:
        print(f"local_app: {res['error']}", file=sys.stderr)
    sys.exit(code)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
