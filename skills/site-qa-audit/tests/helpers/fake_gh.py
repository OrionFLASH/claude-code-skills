#!/usr/bin/env python3
"""Offline stand-in for the `gh` CLI used by tests of publish_web.mjs / comment_web.mjs.

State lives in $FAKE_GH_STATE (JSON). Comments and button clicks made in the local fixtures are
read from the python http.server log ($FAKE_GH_SERVER_LOG): lines with GET /__event?... .
Every call is appended to state["calls"] so tests can assert what was (not) done.
Never talks to the network.
"""
import json
import os
import re
import sys
from urllib.parse import parse_qs, urlsplit

STATE = os.environ["FAKE_GH_STATE"]
LOG = os.environ.get("FAKE_GH_SERVER_LOG")


def load():
    with open(STATE, encoding="utf-8") as fh:
        return json.load(fh)


def save(s):
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump(s, fh, ensure_ascii=False, indent=1)


def events():
    out = []
    if LOG and os.path.exists(LOG):
        for line in open(LOG, encoding="utf-8", errors="replace"):
            m = re.search(r'"GET (/__event\?[^ ]+) HTTP', line)
            if m:
                q = parse_qs(urlsplit(m.group(1)).query)
                out.append({k: v[0] for k, v in q.items()})
    return out


def opt(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def main(argv):
    s = load()
    s.setdefault("calls", []).append(argv)
    s.setdefault("issues", {})
    repo = opt(argv, "-R")
    if argv[:2] == ["issue", "create"]:
        n = max([int(k) for k in s["issues"]] + [0]) + 1
        s["issues"][str(n)] = {"number": n, "state": "open", "title": opt(argv, "--title"),
                               "body": open(opt(argv, "--body-file"), encoding="utf-8").read(), "comments": []}
        save(s)
        print(f"https://github.example/{repo}/issues/{n}")
        return 0
    if argv[:2] == ["issue", "edit"]:
        s["issues"][argv[2]]["body"] = open(opt(argv, "--body-file"), encoding="utf-8").read()
        save(s)
        return 0
    if argv[0] == "api":
        path = [a for a in argv[1:] if not a.startswith("-")][0]
        m = re.fullmatch(r"repos/[^/]+/[^/]+/issues/(\d+)(/comments)?", path)
        if not m:
            print(f"fake gh: unsupported api path {path}", file=sys.stderr)
            return 1
        issue = s["issues"].get(m.group(1))
        if issue is None:
            print("HTTP 404", file=sys.stderr)
            return 1
        ev = [e for e in events() if e.get("issue") == m.group(1)]
        state = issue["state"]
        for e in ev:  # clicks in the fixture change the state like GitHub would
            if e.get("type") == "click" and e.get("button") in ("reopen",):
                state = "open"
            if e.get("type") == "click" and e.get("button") in ("close", "decoy-close"):
                state = "closed"
        save(s)
        if m.group(2):
            comments = list(issue["comments"]) + [
                {"id": 1000 + i, "body": e.get("body", ""), "html_url": f"#c{i}"}
                for i, e in enumerate(ev) if e.get("type") == "comment"]
            print(json.dumps(comments, ensure_ascii=False))
        else:
            print(json.dumps({"number": issue["number"], "state": state, "body": issue["body"]}, ensure_ascii=False))
        return 0
    print(f"fake gh: unsupported command {argv[:2]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
