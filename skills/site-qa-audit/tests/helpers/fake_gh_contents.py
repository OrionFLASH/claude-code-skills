#!/usr/bin/env python3
"""Offline stand-in for `gh api` used by tests of publish_shots.py: repository info, git refs, contents GET/PUT.

State: $FAKE_GH_STATE (JSON) = {"repos": {"owner/repo": {"private": true, "permissions": {"push": true},
"default_branch": "main", "refs": {"main": "<sha>"}, "files": {"<branch>:<path>": {"sha", "content"}},
"deny_put_after": N?}}, "auth": {"logged_in": true, "scopes": ["repo"]}?, "calls": []}.
`gh auth status`: logged in unless auth.logged_in is false; prints «Token scopes» when auth.scopes is given.
deny_put_after: the PUT after N uploaded files answers 403 (a token without Contents: write / SSO).
Every call is appended to state["calls"]. Never talks to the network.
"""
import base64
import hashlib
import json
import os
import re
import sys

STATE = os.environ["FAKE_GH_STATE"]


def load():
    with open(STATE, encoding="utf-8") as fh:
        return json.load(fh)


def save(s):
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump(s, fh, ensure_ascii=False, indent=1)


def fail(msg, code=1):
    print(msg, file=sys.stderr)
    return code


def main(argv):
    s = load()
    s.setdefault("calls", []).append(argv)
    if argv[:2] == ["auth", "status"]:
        # "auth": {"logged_in": false} — not logged in; "scopes": [...] — a classic token shows its scopes
        auth = s.get("auth") or {}
        save(s)
        if auth.get("logged_in") is False:
            return fail("You are not logged into any GitHub hosts. To log in, run: gh auth login")
        print("github.com\n  - Logged in to github.com account qa-user (keyring)")
        if auth.get("scopes") is not None:
            print("  - Token scopes: " + ", ".join(f"'{x}'" for x in auth["scopes"]))
        return 0
    if not argv or argv[0] != "api":
        save(s)
        return fail(f"fake gh: unsupported {argv[:2]}")
    method = argv[argv.index("-X") + 1] if "-X" in argv else "GET"
    skip = {"-X", "-H"}
    rest, i = [], 1
    while i < len(argv):
        if argv[i] in skip:
            i += 2
            continue
        if argv[i] == "--input":
            i += 2
            continue
        rest.append(argv[i])
        i += 1
    path = rest[0]
    body = json.loads(sys.stdin.read() or "null") if "--input" in argv else None
    m = re.match(r"repos/([^/]+/[^/]+)(?:/(.*))?$", path.split("?")[0])
    if not m or m.group(1) not in s.get("repos", {}):
        save(s)
        return fail("HTTP 404: Not Found")
    repo = s["repos"][m.group(1)]
    sub = m.group(2) or ""
    query = dict(x.split("=", 1) for x in path.split("?", 1)[1].split("&")) if "?" in path else {}
    out = None
    if not sub and method == "GET":
        out = {k: repo.get(k) for k in ("private", "permissions", "default_branch")}
    elif sub.startswith("git/ref/heads/") and method == "GET":
        b = sub[len("git/ref/heads/"):]
        if b not in repo["refs"]:
            save(s)
            return fail("HTTP 404: Not Found (gh: Not Found)")
        out = {"ref": f"refs/heads/{b}", "object": {"sha": repo["refs"][b]}}
    elif sub == "git/refs" and method == "POST":
        if not (repo.get("permissions") or {}).get("push"):
            save(s)
            return fail("HTTP 403: Resource not accessible")
        repo["refs"][body["ref"].split("refs/heads/", 1)[1]] = body["sha"]
        out = {"ref": body["ref"]}
    elif sub.startswith("contents/"):
        fpath = sub[len("contents/"):]
        if method == "GET":
            key = f"{query.get('ref', repo['default_branch'])}:{fpath}"
            if key not in repo["files"]:
                save(s)
                return fail("HTTP 404: Not Found")
            out = {"sha": repo["files"][key]["sha"], "path": fpath}
        elif method == "PUT":
            if repo.get("deny_put_after") is not None and sum(1 for k in repo["files"] if not k.startswith("main:")) >= repo["deny_put_after"]:
                save(s)
                return fail("HTTP 403: Resource not accessible by personal access token (gh: Resource not accessible)")
            if body.get("branch") not in repo["refs"]:
                save(s)
                return fail("HTTP 422: branch not found")
            key = f"{body['branch']}:{fpath}"
            if key in repo["files"] and body.get("sha") != repo["files"][key]["sha"]:
                save(s)
                return fail("HTTP 409: sha mismatch")
            data = base64.b64decode(body["content"])
            sha = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
            repo["files"][key] = {"sha": sha, "content": body["content"], "message": body.get("message")}
            out = {"content": {"sha": sha, "path": fpath}}
    if out is None:
        save(s)
        return fail(f"fake gh: unsupported {method} {path}")
    save(s)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
