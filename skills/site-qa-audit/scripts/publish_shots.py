#!/usr/bin/env python3
"""Screenshots of findings into a (private) GitHub repository WITHOUT the browser: gh api contents, own branch.

  publish_shots.py plan <RUN_DIR> --repo owner/repo [--ids F-001,F-002]
      which way works for this repository, checked IN ADVANCE and without writing anything: gh installed → gh logged
      in (`gh auth status`, token scopes when gh shows them) → the repository is visible to this login → push right.
      Modes: api-commit (push: private repository or own one — no manual steps), web-upload (no push: the GitHub web
      form in the user's browser where the USER logged in, node/publish_web.mjs) or local (gh missing / not logged in /
      no access: the screenshots stay with the report — `local`). JSON: mode, reason, checks[], fallback, files.
  publish_shots.py push <RUN_DIR> --repo owner/repo [--branch qa-screenshots] [--path qa-screenshots/<run-id>]
                    [--ids F-001,F-002] [--confirm-push] [--fallback-local]
      DRY-RUN by default (prints what would be uploaded). With --confirm-push (after the user's «да»): the branch is
      created from the default branch if missing (never the default branch itself), every screenshot of the chosen
      findings (annotated if present) is uploaded with `gh api -X PUT repos/<repo>/contents/<path>/<file>` (an
      unchanged file is skipped by its git blob sha), <RUN_DIR>/shots-published.json maps local files to URLs, and the
      value for `render_draft.py --screenshot-base` is printed. In the issue, images are
      https://github.com/<repo>/blob/<branch>/<path>/<file>?raw=true — visible to everyone with access to the repo.
      A write refused on the way (403: token without Contents: write, SSO not authorised, branch rules) stops the
      upload: what was uploaded is kept in shots-published.json, the reason and the fallback are printed (exit 3).
      --fallback-local: when api-commit is not possible, do `local` instead (exit 0, mode local).
  publish_shots.py local <RUN_DIR> [--ids F-001,F-002] [--to <RUN_DIR>/results/screenshots]
      the fallback without GitHub: the same screenshots are copied to <RUN_DIR>/results/screenshots/ with index.md
      (finding → file) and packed to <RUN_DIR>/results/screenshots.zip; build_report.py links them in «Скриншоты
      находок»; the printed line goes into the issue («screenshots are attached to the run report»). The user can drag
      the files into an issue comment himself.

Not automated, on purpose: logging in to GitHub (gh auth login, the web login, 2FA, SSO) — only the user does it; the
skill never types credentials, never reads github.com cookies and never drives the login page (safety-rules.md).
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
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

GH = os.environ.get("QA_GH_BIN") or "gh"


class GhError(Exception):
    pass


def gh_run(args, body=None):
    try:
        return subprocess.run([GH] + args, input=body, capture_output=True, text=True, encoding="utf-8")
    except OSError as ex:  # gh is not installed (or QA_GH_BIN points nowhere)
        raise GhError(f"gh не запускается ({GH}): {ex.strerror or ex}")


def gh_api(path, method="GET", body=None, ok404=False):
    cmd = ["api", "-H", "Accept: application/vnd.github+json", path]
    if method != "GET":
        cmd[1:1] = ["-X", method]
    if body is not None:
        cmd += ["--input", "-"]
    p = gh_run(cmd, json.dumps(body) if body is not None else None)
    if p.returncode != 0:
        if ok404 and re.search(r"404|Not Found", p.stderr + p.stdout):
            return None
        raise GhError(f"gh api {method} {path}: {(p.stderr or p.stdout).strip()[:300]}")
    try:
        return json.loads(p.stdout or "null")
    except ValueError:
        raise GhError(f"gh api {path}: ответ не JSON")


def why_refused(msg):
    """A readable reason for a refused write (gh api error text)."""
    if re.search(r"\b403\b|Resource not accessible|forbidden", msg, re.I):
        return ("GitHub отказал в записи (403): у входа gh нет права записи в этот репозиторий — fine-grained токен без "
                "Contents: write, организация требует SSO-авторизации токена или правила ветки запрещают её создание")
    if re.search(r"\b404\b|Not Found", msg):
        return "репозиторий или ветка не видны входу gh (404): нет доступа или неверное имя"
    if re.search(r"\b409\b|\b422\b", msg):
        return "GitHub отклонил файл (409/422): ветка или файл изменились одновременно — повторить push"
    return "ошибка gh: " + msg[:200]


def fallback_hint(run_dir, ids=None):
    return {"mode": "local", "command": f"publish_shots.py local {run_dir}" + (f" --ids {','.join(sorted(ids))}" if ids else ""),
            "what": "скриншоты остаются при отчёте: results/screenshots/ + results/screenshots.zip, ссылка в сводке; "
                    "в issue — строка «скриншоты приложены к отчёту прогона»"}


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


def preflight(repo):
    """Checks in advance, nothing is written: gh → login (scopes) → repository visible → push. -> (checks, info|None, stop)"""
    checks = []
    try:
        p = gh_run(["auth", "status"])
    except GhError as ex:
        checks.append({"check": "gh", "ok": False, "detail": str(ex) + " — установить GitHub CLI (cli.github.com)"})
        return checks, None, "gh не найден — загрузка через API невозможна"
    checks.append({"check": "gh", "ok": True})
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        checks.append({"check": "login", "ok": False, "detail": "gh не авторизован: войти может только пользователь сам "
                       "(`gh auth login` в своём терминале); скил вход не выполняет"})
        return checks, None, "gh не авторизован"
    m = re.search(r"Token scopes:\s*(.+)", out)
    scopes = [s.strip(" '\"") for s in m.group(1).split(",")] if m else None
    checks.append({"check": "login", "ok": True, **({"scopes": scopes} if scopes is not None else {})})
    try:
        info = gh_api(f"repos/{repo}")
    except GhError as ex:
        checks.append({"check": "repo", "ok": False, "detail": why_refused(str(ex))})
        return checks, None, "репозиторий не виден текущему входу gh"
    checks.append({"check": "repo", "ok": True, "private": bool(info.get("private"))})
    perms = info.get("permissions") or {}
    push = bool(perms.get("push") or perms.get("admin") or perms.get("maintain"))
    detail = None
    if push and scopes is not None and not ({"repo"} & set(scopes) or (not info.get("private") and "public_repo" in scopes)):
        push, detail = False, f"у токена gh нет scope repo (есть: {', '.join(scopes) or '—'}) — запись через API не пройдёт"
    checks.append({"check": "push", "ok": push, **({"detail": detail} if detail else {})})
    return checks, info, None


def plan(run_dir, repo, ids=None):
    files, skipped = files_of(run_dir, ids)
    checks, info, stop = preflight(repo)
    base = {"repo": repo, "checks": checks, "files": [{"id": i, "file": s} for i, s, _ in files], "skipped": skipped,
            "fallback": fallback_hint(run_dir, ids)}
    if stop:
        return dict(base, private=None, push=False, default_branch=None, mode="local",
                    reason=stop + ": " + next((c.get("detail") or "") for c in checks if not c["ok"]))
    private = bool(info.get("private"))
    push = next(c["ok"] for c in checks if c["check"] == "push")
    if push:
        mode = "api-commit"
        reason = ("приватный репозиторий с правом push: загрузка через API без входа в браузере; картинки видны "
                  "только тем, у кого есть доступ") if private else \
            "есть push, но репозиторий ПУБЛИЧНЫЙ: скриншоты станут публичными — только с согласия пользователя"
    else:
        mode = "web-upload"
        reason = ((next((c.get("detail") for c in checks if c["check"] == "push" and c.get("detail")), None) or "нет права push")
                  + ": только веб-форма GitHub в браузере, где пользователь САМ вошёл (node/publish_web.mjs, web-upload.md); "
                  "без этого — local (скриншоты при отчёте)")
    return dict(base, private=private, push=push, default_branch=info.get("default_branch") or "main", mode=mode, reason=reason)


def save_published(run_dir, rows):
    out = Path(run_dir) / "shots-published.json"
    old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    old.update({r["file"]: r["url"] for r in rows if r.get("status") in ("created", "updated", "unchanged")})
    out.write_text(json.dumps(old, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return str(out)


def push(run_dir, repo, branch, path, ids=None, confirm=False, fallback_local=False):
    p = plan(run_dir, repo, ids)
    if p["mode"] != "api-commit":
        if fallback_local:
            code, loc = local(run_dir, ids)
            return code, dict(p, local=loc, error=None, note="api-commit невозможен — выполнен запасной путь local")
        return 1, dict(p, error="загрузка через API невозможна: " + p["reason"])
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
    done = []
    try:
        if gh_api(f"repos/{repo}/git/ref/heads/{branch}", ok404=True) is None:
            head = gh_api(f"repos/{repo}/git/ref/heads/{p['default_branch']}")
            gh_api(f"repos/{repo}/git/refs", "POST", {"ref": f"refs/heads/{branch}", "sha": head["object"]["sha"]})
            res["branch_created"] = True
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
    except GhError as ex:
        left = [dict(r, status="not uploaded") for r in rows[len(done):]]
        res.update(uploads=done + left, error=why_refused(str(ex)), gh_error=str(ex)[:300],
                   published_file=save_published(run_dir, done) if done else None)
        return 3, res
    res["uploads"] = done
    res["published_file"] = save_published(run_dir, done)
    return 0, res


def local(run_dir, ids=None, to=None):
    """Fallback without GitHub: copies + index.md + zip under <RUN_DIR>/results/."""
    run = Path(run_dir)
    files, skipped = files_of(run_dir, ids)
    dest = Path(to) if to else run / "results" / "screenshots"
    dest.mkdir(parents=True, exist_ok=True)
    data = json.loads((run / "findings.json").read_text(encoding="utf-8"))
    titles = {f.get("id"): f.get("title") or "" for f in data.get("findings") or []}
    rows = []
    for fid, rel, src in files:
        name = Path(rel).name
        shutil.copy2(src, dest / name)
        rows.append({"id": fid, "file": rel, "copy": str(dest / name)})
    lines = ["# Скриншоты находок", "",
             "Скриншоты не загружены в репозиторий (нет права push / нет входа gh / нет доступа) — они приложены к отчёту "
             "прогона. Чтобы показать их в issue, перетащите файл в поле комментария на GitHub (вход выполняете вы).", "",
             "| Находка | Заголовок | Файл |", "|---|---|---|"]
    lines += [f"| {r['id']} | {str(titles.get(r['id'], '')).replace('|', '/')[:100]} | [{Path(r['copy']).name}]({quote(Path(r['copy']).name)}) |"
              for r in rows] or ["| — | — | — |"]
    (dest / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    archive = dest.parent / (dest.name + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for r in rows:
            z.write(r["copy"], Path(r["copy"]).name)
        z.write(dest / "index.md", "index.md")
    try:
        rel_dir = dest.resolve().relative_to(run.resolve()).as_posix()
    except ValueError:
        rel_dir = str(dest)
    issue_line = (f"Скриншоты: приложены к отчёту прогона ({rel_dir}/, архив {archive.name}) — "
                  + ", ".join(Path(r['file']).name for r in rows) + "." if rows else "Скриншотов для приложения нет.")
    return 0, {"mode": "local", "dir": str(dest), "archive": str(archive), "index": str(dest / "index.md"), "files": rows,
               "skipped": skipped, "issue_line": issue_line}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "push", "local"):
        c = sub.add_parser(name)
        c.add_argument("run_dir")
        if name != "local":
            c.add_argument("--repo", required=True)
        c.add_argument("--ids", help="только эти находки: F-001,F-002")
        if name == "push":
            c.add_argument("--branch", default="qa-screenshots")
            c.add_argument("--path", help="папка в репозитории (по умолчанию qa-screenshots/<имя папки прогона>)")
            c.add_argument("--confirm-push", action="store_true", help="реально загрузить (после «да» пользователя)")
            c.add_argument("--fallback-local", action="store_true", help="если API невозможен — сразу запасной путь local")
        if name == "local":
            c.add_argument("--to", help="папка (по умолчанию <RUN_DIR>/results/screenshots)")
    a = ap.parse_args()
    repo = None
    if a.cmd != "local":
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
        elif a.cmd == "local":
            code, res = local(a.run_dir, ids, a.to)
        else:
            path = a.path or f"qa-screenshots/{Path(a.run_dir).resolve().name}"
            code, res = push(a.run_dir, repo, a.branch, path, ids, a.confirm_push, a.fallback_local)
    except GhError as ex:
        print(json.dumps({"error": why_refused(str(ex)), "gh_error": str(ex)[:300], "fallback": fallback_hint(a.run_dir, ids)},
                         ensure_ascii=False))
        sys.exit(3)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if a.cmd == "plan":
        sys.stderr.write(f"режим: {res['mode']} — {res['reason']}\n" +
                         ("" if res["mode"] == "api-commit" else f"запасной путь: {res['fallback']['command']}\n"))
    elif a.cmd == "local":
        sys.stderr.write(f"скриншоты при отчёте: {res['dir']} ({len(res['files'])}), архив {res['archive']}\nв issue: {res['issue_line']}\n")
    elif res.get("mode") == "local" and res.get("local"):
        sys.stderr.write(f"API невозможен ({res['reason']}) — скриншоты при отчёте: {res['local']['archive']}\n"
                         f"в issue: {res['local']['issue_line']}\n")
    elif code == 0:
        sys.stderr.write(("ПРОБНЫЙ ЗАПУСК (ничего не загружено): после «да» — тот же вызов с --confirm-push\n" if res["dry_run"]
                          else f"загружено: {sum(1 for u in res['uploads'] if u['status'] in ('created', 'updated'))}, без изменений: "
                               f"{sum(1 for u in res['uploads'] if u['status'] == 'unchanged')}\n") +
                         f"render_draft.py … --screenshot-base {res['screenshot_base']}\n")
    else:
        sys.stderr.write(f"НЕ ЗАГРУЖЕНО: {res.get('error')}\nзапасной путь: {res['fallback']['command']}\n")
    sys.exit(code)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
