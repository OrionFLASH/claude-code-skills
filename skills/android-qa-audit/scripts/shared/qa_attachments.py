#!/usr/bin/env python3
"""Screenshots for issues in a branch of a repository (`attachments: branch`) for the QA skills.

`gh issue create` cannot attach images, so the pictures must already be in the repository when the issues are
created. Order: plan → (user's «да») push → verify → then create issues with links
https://github.com/<repo>/blob/<branch>/<dir>/<file>?raw=true (they work in private repositories for everyone who has
access; raw.githubusercontent.com links do not). Uploads go through the GitHub contents API (`gh api`): no local
clone, the user's working copy and branches are not touched; a missing branch is created from the head of the
default branch. Identical files are skipped (git blob sha). Commit messages are given by the caller (with
disclosure: none — without the tool's name); Claude Code's own commit trailers are not added or removed here.
Standard library only.

  qa_attachments.cli(argv, skill)
    plan   RUN_DIR --repo owner/repo --branch B --dir D [--file F …] [--json]    what goes where, links (no network)
    push   RUN_DIR --repo … --branch … --dir … [--file F …] --yes [--message M]  upload (only after «да»)
    verify RUN_DIR --repo … --branch … --dir … [--file F …]                     every file is in the branch
Without --file: the screenshots of findings to publish (findings.json: shots[].annotated first, then screenshots[]),
skipping KNOWN / DUPLICATE / FIXED-OK statuses and evidence.sensitive. Result: RUN_DIR/attachments.json
{base, files: [{local, path, url, sha, status}]}; render_draft.py --attachments-base <base>.
Environment: QA_GH_BIN — path to gh. Exit codes: 0 ok, 1 something missing or failed, 2 bad input.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKIP_STATUSES = {"KNOWN", "DUPLICATE-OPEN", "FIXED-OK", "ALREADY-COPIED", "NOT-CHECKED"}
IMAGES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm")


class AttachError(Exception):
    pass


def norm_repo(r):
    return re.sub(r"^https?://github\.com/|\.git$|/$", "", r or "")


def gh(args, body=None, timeout=120):
    exe = os.environ.get("QA_GH_BIN") or shutil.which("gh")
    if not exe:
        raise AttachError("gh не найден (https://cli.github.com)")
    tmp = None
    try:
        if body is not None:
            fd, tmp = tempfile.mkstemp(suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(body, f)
            args = args + ["--input", tmp]
        p = subprocess.run([exe, "api"] + args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise AttachError(f"gh api {' '.join(args[:3])}: {ex}")
    finally:
        if tmp:
            os.unlink(tmp)
    if p.returncode != 0:
        msg = (p.stderr or p.stdout).strip()
        if "404" in msg or "Not Found" in msg:
            return None
        raise AttachError(f"gh api {' '.join(args[:3])}: {msg[:200]}")
    try:
        return json.loads(p.stdout) if p.stdout.strip() else {}
    except ValueError:
        return {}


def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def findings_files(run_dir):
    p = Path(run_dir) / "findings.json"
    if not p.exists():
        raise AttachError(f"нет {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for f in data.get("findings", []) if isinstance(data, dict) else data:
        if (f.get("status") or "NEW") in SKIP_STATUSES or (f.get("evidence") or {}).get("sensitive"):
            continue
        refs = [s.get("annotated") or s.get("original") for s in f.get("shots") or [] if isinstance(s, dict)]
        refs += [x for x in f.get("screenshots") or [] if isinstance(x, str)]
        for r in refs:
            if not r:
                continue
            stem = Path(r).stem
            if not stem.endswith("-annotated") and any(Path(x).stem == stem + "-annotated" for x in refs if x):
                continue  # the original is not published when its annotated copy exists
            if r not in out:
                out.append(r)
    return out


def plan(run_dir, repo, branch, folder, files=None):
    run = Path(run_dir)
    repo = norm_repo(repo)
    if not re.match(r"^[\w.-]+/[\w.-]+$", repo):
        raise AttachError(f"репозиторий owner/repo, получено {repo!r}")
    if not re.match(r"^[\w./-]+$", branch) or ".." in branch:
        raise AttachError(f"имя ветки {branch!r}")
    folder = folder.strip("/")
    if ".." in folder or not re.match(r"^[\w./-]*$", folder):
        raise AttachError(f"папка {folder!r}")
    refs = files or findings_files(run)
    base = f"https://github.com/{repo}/blob/{branch}/{folder}".rstrip("/")
    rows = []
    for r in refs:
        local = Path(r) if Path(r).is_absolute() else run / r
        if local.suffix.lower() not in IMAGES:
            continue
        name = local.name
        rows.append({"local": str(local), "exists": local.is_file(), "path": f"{folder}/{name}".lstrip("/"),
                     "url": f"{base}/{name}?raw=true"})
    return {"repo": repo, "branch": branch, "dir": folder, "base": base, "files": rows}


def ensure_branch(repo, branch):
    ref = gh([f"repos/{repo}/git/ref/heads/{branch}"])
    if ref:
        return False
    info = gh([f"repos/{repo}"]) or {}
    default = info.get("default_branch") or "main"
    head = gh([f"repos/{repo}/git/ref/heads/{default}"])
    if not head:
        raise AttachError(f"нет ветки по умолчанию {default} в {repo}")
    gh(["-X", "POST", f"repos/{repo}/git/refs"], {"ref": f"refs/heads/{branch}", "sha": head["object"]["sha"]})
    return True


def push(p, message):
    created = ensure_branch(p["repo"], p["branch"])
    for row in p["files"]:
        if not row["exists"]:
            row["status"] = "нет файла"
            continue
        data = Path(row["local"]).read_bytes()
        sha = blob_sha(data)
        cur = gh([f"repos/{p['repo']}/contents/{row['path']}?ref={p['branch']}"])
        if cur and cur.get("sha") == sha:
            row.update(status="уже есть", sha=sha)
            continue
        body = {"message": message, "content": base64.b64encode(data).decode("ascii"), "branch": p["branch"]}
        if cur and cur.get("sha"):
            body["sha"] = cur["sha"]
        gh(["-X", "PUT", f"repos/{p['repo']}/contents/{row['path']}"], body)
        row.update(status="загружен", sha=sha)
    p["branch_created"] = created
    return p


def verify(p):
    ok = True
    for row in p["files"]:
        cur = gh([f"repos/{p['repo']}/contents/{row['path']}?ref={p['branch']}"])
        row["verified"] = bool(cur and cur.get("sha"))
        if row["exists"] and row["verified"]:
            row["same"] = cur.get("sha") == blob_sha(Path(row["local"]).read_bytes())
        ok = ok and row["verified"]
    p["ok"] = ok
    return p


def cli(argv, skill="qa"):
    ap = argparse.ArgumentParser(prog="attachments.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "push", "verify"):
        p = sub.add_parser(name)
        p.add_argument("run_dir")
        p.add_argument("--repo", required=True)
        p.add_argument("--branch", required=True)
        p.add_argument("--dir", default="qa-screenshots")
        p.add_argument("--file", action="append")
        p.add_argument("--json", action="store_true")
        if name == "push":
            p.add_argument("--yes", action="store_true", help="загрузить (только после «да» пользователя)")
            p.add_argument("--message", default="Add screenshots for issues")
    a = ap.parse_args(argv)
    try:
        p = plan(a.run_dir, a.repo, a.branch, a.dir, a.file)
        if a.cmd == "push":
            if not a.yes:
                p["note"] = "План без изменений: загрузка — тот же вызов с --yes после «да» пользователя"
            else:
                p = push(p, a.message)
                verify(p)
        elif a.cmd == "verify":
            verify(p)
        out = Path(a.run_dir) / "attachments.json"
        if a.cmd != "plan":
            out.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
        if a.json or a.cmd != "plan":
            print(json.dumps(p, ensure_ascii=False, indent=1))
        else:
            print(f"{p['repo']} ветка {p['branch']}, папка {p['dir']}: файлов {len(p['files'])}")
            for r in p["files"]:
                print(f"  {r['local']} → {r['path']}" + ("" if r["exists"] else "  (НЕТ ФАЙЛА)"))
            print(f"render_draft.py … --attachments-base {p['base']}")
        missing = [r for r in p["files"] if not r["exists"]]
        failed = a.cmd != "plan" and a.cmd == "verify" and not p.get("ok")
        failed = failed or (a.cmd == "push" and a.yes and not p.get("ok"))
        return 1 if missing or failed else 0
    except AttachError as ex:
        print(f"{skill}: {ex}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(cli(sys.argv[1:]))
