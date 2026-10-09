#!/usr/bin/env python3
"""Fake `gh api` for offline tests (issue forms, known docs, attachments by branch). No network.

  FAKE_GH_REPO   folder with the files of the repository (owner/repo — any): <path> → contents API
  FAKE_GH_STATE  folder: branches.json and uploads/<branch>/<path> (written by PUT contents / POST git/refs)
  FAKE_GH_LOG    every call as a JSON line
Supported: GET repos/O/R, repos/O/R/contents/<path>[?ref=B], repos/O/R/git/ref/heads/<B>;
PUT repos/O/R/contents/<path> --input body.json; POST repos/O/R/git/refs --input body.json. Unknown — 404.
"""
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("FAKE_GH_REPO", "/nonexistent"))
STATE = Path(os.environ.get("FAKE_GH_STATE", "/tmp/fake-gh-state"))


def out(obj, code=0):
    if code:
        sys.stderr.write(json.dumps(obj) + "\n")
    else:
        sys.stdout.write(json.dumps(obj))
    sys.exit(code)


def sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def branches():
    p = STATE / "branches.json"
    return json.loads(p.read_text()) if p.exists() else {"main": "a" * 40}


def main():
    args = sys.argv[1:]
    if os.environ.get("FAKE_GH_LOG"):
        with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as f:
            f.write(json.dumps(args, ensure_ascii=False) + "\n")
    if not args or args[0] != "api":
        out({"message": "fake gh: only api"}, 1)
    args = args[1:]
    method, body = "GET", None
    if "-X" in args:
        method = args[args.index("-X") + 1]
    if "--input" in args:
        body = json.loads(Path(args[args.index("--input") + 1]).read_text(encoding="utf-8"))
    path = next(a for a in args if a.startswith("repos/"))
    path, _, query = path.partition("?")
    ref = dict(x.split("=", 1) for x in query.split("&") if "=" in x).get("ref")
    parts = path.split("/")
    rest = "/".join(parts[3:])
    STATE.mkdir(parents=True, exist_ok=True)
    if len(parts) == 3:
        out({"default_branch": "main", "private": True})
    if rest.startswith("git/ref/heads/"):
        b = rest[len("git/ref/heads/"):]
        br = branches()
        if b in br:
            out({"ref": f"refs/heads/{b}", "object": {"sha": br[b]}})
        out({"message": "Not Found", "status": "404"}, 1)
    if rest == "git/refs" and method == "POST":
        br = branches()
        br[body["ref"].split("/")[-1]] = body["sha"]
        (STATE / "branches.json").write_text(json.dumps(br))
        out({"ref": body["ref"]})
    if rest.startswith("contents/"):
        p = rest[len("contents/"):]
        if method == "PUT":
            b = body["branch"]
            if b not in branches():
                out({"message": "Branch not found", "status": "404"}, 1)
            dest = STATE / "uploads" / b / p
            dest.parent.mkdir(parents=True, exist_ok=True)
            data = base64.b64decode(body["content"])
            dest.write_bytes(data)
            out({"content": {"path": p, "sha": sha(data)}, "commit": {"message": body["message"]}})
        if ref:
            up = STATE / "uploads" / ref / p
            if up.is_file():
                data = up.read_bytes()
                out({"type": "file", "path": p, "sha": sha(data), "size": len(data)})
            out({"message": "Not Found", "status": "404"}, 1)
        src = REPO / p
        if src.is_dir():
            out([{"name": x.name, "path": f"{p}/{x.name}".strip("/"), "type": "file" if x.is_file() else "dir"}
                 for x in sorted(src.iterdir())])
        if src.is_file():
            data = src.read_bytes()
            out({"type": "file", "name": src.name, "path": p, "sha": sha(data),
                 "content": base64.b64encode(data).decode("ascii"), "encoding": "base64"})
        out({"message": "Not Found", "status": "404"}, 1)
    out({"message": "Not Found", "status": "404"}, 1)


if __name__ == "__main__":
    main()
