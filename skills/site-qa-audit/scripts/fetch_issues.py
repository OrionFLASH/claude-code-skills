#!/usr/bin/env python3
"""Выгрузка issues (open + closed) с комментариями через gh CLI в JSON-кэш, инкрементально.

  fetch_issues.py sync owner/repo [owner/repo ...] [--cache DIR] [--full]
      Обновляет кэш DIR/<owner>__<repo>.json (по умолчанию ./qa-runs/.cache/issues).
      Повторный запуск догружает только изменённое с прошлого раза (параметр since).
  fetch_issues.py meta owner/repo
      Права текущего пользователя, метки, наличие issues — JSON.
  fetch_issues.py registry --cache DIR [--out registry.json] owner/repo ...
      Сводный реестр известных проблем (для fingerprint.py match).

Требуется авторизованный gh (`gh auth status`). Пауза и повторы при лимитах API.
Pull requests из выдачи issues исключаются.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FIX_RX = re.compile(
    r"\b(fixed|fix(ed)? in|resolved|done|deployed|исправлен[оа]?|исправили|починил[иа]?|поправил[иа]?|"
    r"решено|готово|сделано|закрыто как исправленное)\b", re.I)
MARKER_RX = re.compile(r"<!--\s*site-qa-audit:fp=([0-9a-f]{12,40})\s*-->")


def gh_api(path, paginate=False, retries=4):
    cmd = ["gh", "api", "-H", "Accept: application/vnd.github+json", path]
    if paginate:
        cmd.insert(2, "--paginate")
    delay = 5
    for attempt in range(retries + 1):
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if proc.returncode == 0:
            out = proc.stdout.strip()
            if not out:
                return []
            if paginate:  # --paginate склеивает массивы как "][" — разбираем поток JSON
                dec, pos, items = json.JSONDecoder(), 0, []
                while pos < len(out):
                    obj, pos = dec.raw_decode(out, pos)
                    items.extend(obj if isinstance(obj, list) else [obj])
                    while pos < len(out) and out[pos] in " \n\r\t":
                        pos += 1
                return items
            return json.loads(out)
        err = proc.stderr
        if attempt < retries and re.search(r"rate limit|secondary|HTTP 5\d\d|timeout|EOF", err, re.I):
            print(f"gh api {path}: {err.strip()[:120]} — повтор через {delay}s", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
            continue
        raise RuntimeError(f"gh api {path} завершился с ошибкой: {err.strip()}")
    return None


def cache_path(cache, repo):
    return Path(cache) / (repo.replace("/", "__") + ".json")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sync_repo(repo, cache, full=False):
    path = cache_path(cache, repo)
    data = {"repo": repo, "fetched_at": None, "issues": {}}
    if path.exists() and not full:
        data = json.loads(path.read_text(encoding="utf-8"))
    since = data.get("fetched_at")
    started = now_iso()
    q = f"repos/{repo}/issues?state=all&per_page=100" + (f"&since={since}" if since else "")
    changed = 0
    for it in gh_api(q, paginate=True):
        if "pull_request" in it:
            continue
        key = str(it["number"])
        old = data["issues"].get(key, {})
        data["issues"][key] = {
            "number": it["number"], "title": it["title"], "state": it["state"],
            "state_reason": it.get("state_reason"), "url": it["html_url"],
            "labels": [lb["name"] for lb in it.get("labels", [])],
            "body": it.get("body") or "", "created_at": it["created_at"], "updated_at": it["updated_at"],
            "closed_at": it.get("closed_at"), "comments": old.get("comments", []),
        }
        changed += 1
    cq = f"repos/{repo}/issues/comments?per_page=100" + (f"&since={since}" if since else "")
    ncom = 0
    for c in gh_api(cq, paginate=True):
        num = c["issue_url"].rsplit("/", 1)[-1]
        iss = data["issues"].get(num)
        if iss is None:
            continue  # комментарий к PR
        rec = {"id": c["id"], "author": (c.get("user") or {}).get("login"), "body": c.get("body") or "",
               "created_at": c["created_at"], "updated_at": c["updated_at"], "url": c["html_url"]}
        iss["comments"] = [x for x in iss["comments"] if x["id"] != c["id"]] + [rec]
        iss["comments"].sort(key=lambda x: x["created_at"])
        ncom += 1
    data["fetched_at"] = started
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{repo}: issues обновлено {changed}, комментариев {ncom}, всего issues {len(data['issues'])} -> {path}")


def meta(repo):
    info = gh_api(f"repos/{repo}")
    labels = gh_api(f"repos/{repo}/labels?per_page=100", paginate=True)
    return {
        "repo": repo, "private": info.get("private"), "has_issues": info.get("has_issues"),
        "default_branch": info.get("default_branch"), "permissions": info.get("permissions", {}),
        "labels": [{"name": lb["name"], "description": lb.get("description")} for lb in labels],
    }


def fix_claimed(iss):
    if iss["state"] == "closed" and iss.get("state_reason") in (None, "completed"):
        return True
    return any(FIX_RX.search(c["body"]) for c in iss.get("comments", []))


def registry(repos, cache):
    out = []
    for repo in repos:
        data = json.loads(cache_path(cache, repo).read_text(encoding="utf-8"))
        for iss in data["issues"].values():
            out.append({
                "repo": repo, "number": iss["number"], "title": iss["title"], "state": iss["state"],
                "state_reason": iss.get("state_reason"), "url": iss["url"], "labels": iss["labels"],
                "body": iss["body"], "comments": iss["comments"], "fix_claimed": fix_claimed(iss),
                "fingerprints": sorted(set(MARKER_RX.findall(iss["body"] + "".join(c["body"] for c in iss["comments"])))),
            })
    return {"generated_at": now_iso(), "repos": repos, "issues": out}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["sync", "meta", "registry"])
    ap.add_argument("repos", nargs="+", help="owner/repo или URL github.com/owner/repo")
    ap.add_argument("--cache", default="qa-runs/.cache/issues")
    ap.add_argument("--full", action="store_true", help="перекачать всё, игнорируя кэш")
    ap.add_argument("--out")
    a = ap.parse_args()
    repos = [re.sub(r"^https?://github\.com/|\.git$|/$", "", r) for r in a.repos]
    if a.cmd == "sync":
        for r in repos:
            sync_repo(r, a.cache, a.full)
            time.sleep(1)
    elif a.cmd == "meta":
        print(json.dumps([meta(r) for r in repos], ensure_ascii=False, indent=2))
    else:
        reg = registry(repos, a.cache)
        text = json.dumps(reg, ensure_ascii=False, indent=1)
        if a.out:
            Path(a.out).write_text(text, encoding="utf-8")
            print(f"registry: {len(reg['issues'])} issues -> {a.out}")
        else:
            print(text)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
