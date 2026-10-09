#!/usr/bin/env python3
"""Screenshots of findings into a (private) GitHub repository WITHOUT the browser: gh api contents, own branch.

  publish_shots.py plan <RUN_DIR> --repo owner/repo [--ids F-001,F-002]
      which way works for this repository: api-commit (push right: private repository or own one — no manual steps),
      web-upload (no push: the GitHub web form in the user's browser, node/publish_web.mjs) or sheet (nothing works:
      screenshots stay local, the contact sheet is attached to the summary). JSON with the reason and the files.
  publish_shots.py push <RUN_DIR> --repo owner/repo [--branch qa-screenshots] [--path qa-screenshots/<run-id>]
                    [--ids F-001,F-002] [--confirm-push]
      DRY-RUN by default (prints what would be uploaded). With --confirm-push (after the user's «да»): the branch is
      created from the default branch if missing (never the default branch itself), every screenshot of the chosen
      findings (annotated if present) is uploaded with `gh api -X PUT repos/<repo>/contents/<path>/<file>` (an
      unchanged file is skipped by its git blob sha), <RUN_DIR>/shots-published.json maps local files to URLs, and the
      value for `render_draft.py --screenshot-base` is printed. In the issue, images are
      https://github.com/<repo>/blob/<branch>/<path>/<file>?raw=true — visible to everyone with access to the repo.

Not uploaded: findings with evidence.sensitive (personal data, secrets), missing files. Public repository: the
screenshots become public — the plan says so; publish only what the user agreed to (safety-rules.md §5–6).
gh: authorised `gh` (QA_GH_BIN — another binary, for tests). Exit codes: 0 ok, 1 not possible, 2 bad input, 3 gh error.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

GH = os.environ.get("QA_GH_BIN") or "gh"


class GhError(Exception):
    pass


def gh_api(path, method="GET", body=None, ok404=False):
    cmd = [GH, "api", "-H", "Accept: application/vnd.github+json", path]
    if method != "GET":
        cmd[2:2] = ["-X", method]
    if body is not None:
        cmd += ["--input", "-"]
    p = subprocess.run(cmd, input=json.dumps(body) if body is not None else None, capture_output=True, text=True)
    if p.returncode != 0:
        if ok404 and re.search(r"404|Not Found", p.stderr + p.stdout):
            return None
        raise GhError(f"gh api {method} {path}: {(p.stderr or p.stdout).strip()[:300]}")
    try:
        return json.loads(p.stdout or "null")
    except ValueError:
        raise GhError(f"gh api {path}: ответ не JSON")


def blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def visible_shots(shots):
    ann = {s.replace("-annotated.png", ".png") for s in shots if s.endswith("-annotated.png")}
    return [s for s in shots if s not in ann]


def files_of(run_dir, ids=None):
    """[(finding id, relative path, absolute path)] of screenshots to publish; skipped — with reasons."""
    data = json.loads((Path(run_dir) / "findings.json").read_text(encoding="utf-8"))
    out, skipped = [], []
    for f in data.get("findings") or []:
        if ids and f.get("id") not in ids:
            continue
        shots = visible_shots(f.get("screenshots") or [])
        if not shots:
            continue
        if (f.get("evidence") or {}).get("sensitive"):
            skipped += [{"id": f["id"], "file": s, "reason": "evidence.sensitive — не публикуется"} for s in shots]
            continue
        for s in shots:
            p = Path(run_dir) / s
            if p.is_file():
                out.append((f["id"], s, p))
            else:
                skipped.append({"id": f["id"], "file": s, "reason": "файла нет"})
    return out, skipped


def plan(run_dir, repo, ids=None):
    info = gh_api(f"repos/{repo}")
    perms = info.get("permissions") or {}
    private = bool(info.get("private"))
    push = bool(perms.get("push") or perms.get("admin") or perms.get("maintain"))
    files, skipped = files_of(run_dir, ids)
    if push:
        mode = "api-commit"
        reason = ("приватный репозиторий с правом push: загрузка через API без входа в браузере; картинки видны "
                  "только тем, у кого есть доступ") if private else \
            "есть push, но репозиторий ПУБЛИЧНЫЙ: скриншоты станут публичными — только с согласия пользователя"
    else:
        mode = "web-upload"
        reason = ("нет права push: только веб-форма GitHub в браузере пользователя (node/publish_web.mjs, "
                  "web-upload.md); если и это недоступно — контактный лист в сводке (sheet)")
    return {"repo": repo, "private": private, "push": push, "default_branch": info.get("default_branch") or "main",
            "mode": mode, "reason": reason, "files": [{"id": i, "file": s} for i, s, _ in files], "skipped": skipped}


def push(run_dir, repo, branch, path, ids=None, confirm=False):
    p = plan(run_dir, repo, ids)
    if p["mode"] != "api-commit":
        return 1, dict(p, error="нет права push — загрузка через API невозможна; " + p["reason"])
    if branch == p["default_branch"]:
        return 2, dict(p, error=f"ветка {branch} — основная ветка репозитория: скриншоты только в отдельную ветку")
    files, _ = files_of(run_dir, ids)
    path = path.strip("/")
    base = f"https://github.com/{repo}/blob/{branch}/{path}"
    rows = [{"id": i, "file": s, "target": f"{path}/{Path(s).name}", "url": f"{base}/{quote(Path(s).name)}?raw=true"}
            for i, s, _ in files]
    res = dict(p, branch=branch, path=path, screenshot_base=base, uploads=rows, dry_run=not confirm)
    if not confirm:
        return 0, res
    if gh_api(f"repos/{repo}/git/ref/heads/{branch}", ok404=True) is None:
        head = gh_api(f"repos/{repo}/git/ref/heads/{p['default_branch']}")
        gh_api(f"repos/{repo}/git/refs", "POST", {"ref": f"refs/heads/{branch}", "sha": head["object"]["sha"]})
        res["branch_created"] = True
    done = []
    for (fid, rel, abs_path), row in zip(files, rows):
        data = abs_path.read_bytes()
        api_path = f"repos/{repo}/contents/{quote(row['target'], safe='/')}"
        cur = gh_api(f"{api_path}?ref={quote(branch, safe='')}", ok404=True)
        if cur and cur.get("sha") == blob_sha(data):
            done.append(dict(row, status="unchanged"))
            continue
        body = {"message": f"qa screenshots: {fid} {Path(rel).name}", "branch": branch,
                "content": base64.b64encode(data).decode("ascii")}
        if cur and cur.get("sha"):
            body["sha"] = cur["sha"]
        gh_api(api_path, "PUT", body)
        done.append(dict(row, status="updated" if cur else "created"))
        time.sleep(float(os.environ.get("QA_GH_PAUSE", "0.5")))
    res["uploads"] = done
    out = Path(run_dir) / "shots-published.json"
    old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    old.update({r["file"]: r["url"] for r in done})
    out.write_text(json.dumps(old, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    res["published_file"] = str(out)
    return 0, res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "push"):
        c = sub.add_parser(name)
        c.add_argument("run_dir")
        c.add_argument("--repo", required=True)
        c.add_argument("--ids", help="только эти находки: F-001,F-002")
        if name == "push":
            c.add_argument("--branch", default="qa-screenshots")
            c.add_argument("--path", help="папка в репозитории (по умолчанию qa-screenshots/<имя папки прогона>)")
            c.add_argument("--confirm-push", action="store_true", help="реально загрузить (после «да» пользователя)")
    a = ap.parse_args()
    repo = re.sub(r"^https?://github\.com/|\.git$|/$", "", a.repo)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        print("publish_shots: --repo owner/repo", file=sys.stderr)
        sys.exit(2)
    if not (Path(a.run_dir) / "findings.json").is_file():
        print(f"publish_shots: нет {a.run_dir}/findings.json", file=sys.stderr)
        sys.exit(2)
    ids = {x.strip() for x in a.ids.split(",")} if a.ids else None
    try:
        if a.cmd == "plan":
            code, res = 0, plan(a.run_dir, repo, ids)
        else:
            path = a.path or f"qa-screenshots/{Path(a.run_dir).resolve().name}"
            code, res = push(a.run_dir, repo, a.branch, path, ids, a.confirm_push)
    except GhError as ex:
        print(json.dumps({"error": str(ex)}, ensure_ascii=False))
        sys.exit(3)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if a.cmd == "push" and code == 0:
        sys.stderr.write(("ПРОБНЫЙ ЗАПУСК (ничего не загружено): после «да» — тот же вызов с --confirm-push\n" if res["dry_run"]
                          else f"загружено: {sum(1 for u in res['uploads'] if u['status'] != 'unchanged')}, без изменений: "
                               f"{sum(1 for u in res['uploads'] if u['status'] == 'unchanged')}\n") +
                         f"render_draft.py … --screenshot-base {res['screenshot_base']}\n")
    sys.exit(code)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
