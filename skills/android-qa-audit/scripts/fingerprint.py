#!/usr/bin/env python3
"""Fingerprints of findings and matching with GitHub issues (references/repo-sync.md).

  fingerprint.py compute findings.json           set fingerprint for every finding (in place)
  fingerprint.py dedupe findings.json            merge duplicates (same fingerprint) in place: environments,
                                                 screenshots and sources are combined, the higher severity wins
  fingerprint.py match findings.json issues.json [issues2.json …] [--out matches.json] [--threshold 0.35]
                                                 candidates among issues: exact by marker, fuzzy by words
  fingerprint.py one --direction D --check C --screen S [--element E] [--package P]

The fingerprint does not depend on the wording: direction + check_id + package + screen + element.
issues.json — output of `gh issue list -R owner/repo --state all --limit 1000 --json number,title,body,state,url`
(one file per repository; the repository is taken from "repo" or from the issue url). Marker: <!-- android-qa-audit:fp=<fp> -->
(or the neutral <!-- qa-fp:<fp> -->).
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

MARKER_RX = re.compile(r"<!--\s*(?:android-qa-audit:fp=|qa-fp:)([0-9a-f]{12,40})\s*-->")
STOP = set("the a an of to in on for and or is are not with без и в на не по для из к от что как при экран кнопка".split())
SEV = ["critical", "high", "medium", "low", "info"]


def norm_screen(screen, package=""):
    s = (screen or "").strip()
    if package and s.startswith(package + "."):
        s = s[len(package):]
    s = re.sub(r"\$\d+", "", s)  # anonymous inner classes
    return s.lower()


def norm_element(el):
    el = str(el or "")
    m = re.search(r"id=([\w.:/-]+)", el)
    if m:
        return "id=" + m.group(1).split(":id/")[-1].lower()
    el = re.sub(r"\[\d+\]|#\d+|\d+", "", el)
    return re.sub(r"\s+", " ", el).strip().lower()


def compute(direction, check_id, screen, element="", package=""):
    key = "|".join([direction or "", (check_id or "").lower(), package or "", norm_screen(screen, package), norm_element(element)])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def finding_fp(f, run=None):
    pkg = f.get("package") or (run or {}).get("app") or ""
    return compute(f.get("direction"), f.get("check_id"), f.get("screen"), f.get("element"), pkg)


def tokens(text):
    return {w for w in re.findall(r"[\w-]{3,}", (text or "").lower()) if w not in STOP}


def similarity(a, b):
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def flist(data):
    return data["findings"] if isinstance(data, dict) else data


def cmd_compute(path):
    data = load(path)
    run = data.get("run") if isinstance(data, dict) else {}
    for f in flist(data):
        f["fingerprint"] = finding_fp(f, run)
    save(path, data)
    print(f"compute: {len(flist(data))} находок")


def cmd_dedupe(path):
    data = load(path)
    run = data.get("run") if isinstance(data, dict) else {}
    merged, order = {}, []
    for f in flist(data):
        fp = f.get("fingerprint") or finding_fp(f, run)
        f["fingerprint"] = fp
        if fp not in merged:
            merged[fp] = f
            order.append(fp)
            continue
        keep = merged[fp]
        if SEV.index(f.get("severity", "info")) < SEV.index(keep.get("severity", "info")):
            keep["severity"] = f["severity"]
        for k in ("sources", "screenshots", "recordings", "environment_list"):
            keep[k] = list(dict.fromkeys((keep.get(k) or []) + (f.get(k) or [])))
        if f.get("crash") and not keep.get("crash"):
            keep["crash"] = f["crash"]
        keep.setdefault("merged_ids", []).append(f.get("id"))
    result = [merged[k] for k in order]
    removed = len(flist(data)) - len(result)
    if isinstance(data, dict):
        data["findings"] = result
    else:
        data = result
    save(path, data)
    print(f"dedupe: слито дублей {removed}, осталось {len(result)}")


def load_issues(paths):
    issues = []
    for p in paths:
        data = load(p)
        for i in (data.get("issues", []) if isinstance(data, dict) else data):
            if not i.get("repo"):
                m = re.search(r"github\.com/([\w.-]+/[\w.-]+)/(?:issues|pull)/", i.get("url") or "")
                i["repo"] = m.group(1) if m else None
            issues.append(i)
    return issues


def cmd_match(findings_path, issues_paths, out=None, threshold=0.35):
    data = load(findings_path)
    run = data.get("run") if isinstance(data, dict) else {}
    issues = load_issues(issues_paths)
    by_fp = {}
    for iss in issues:
        texts = [iss.get("body") or ""] + [c.get("body") or "" for c in iss.get("comments") or [] if isinstance(c, dict)]
        for t in texts:
            for fp in MARKER_RX.findall(t):
                by_fp.setdefault(fp, []).append(iss)
    rows = []
    for f in flist(data):
        fp = f.get("fingerprint") or finding_fp(f, run)
        exact = [{"repo": i.get("repo"), "number": i.get("number"), "state": (i.get("state") or "").lower(),
                  "url": i.get("url"), "how": "marker"} for i in by_fp.get(fp, [])]
        fuzzy = []
        screen = norm_screen(f.get("screen"), f.get("package") or run.get("app") or "").split(".")[-1]
        for i in issues:
            if any(e["number"] == i.get("number") and e["repo"] == i.get("repo") for e in exact):
                continue
            text = (i.get("title") or "") + " " + (i.get("body") or "")[:1500]
            score = similarity(f"{f.get('title', '')} {f.get('actual', '')} {(f.get('crash') or {}).get('summary', '')}", text)
            if screen and len(screen) > 3 and screen in text.lower():
                score += 0.15
            if score >= threshold:
                fuzzy.append({"repo": i.get("repo"), "number": i.get("number"), "title": i.get("title"),
                              "state": (i.get("state") or "").lower(), "url": i.get("url"), "score": round(score, 2), "how": "fuzzy"})
        fuzzy.sort(key=lambda x: -x["score"])
        rows.append({"id": f.get("id"), "fingerprint": fp, "title": f.get("title"), "exact": exact, "candidates": fuzzy[:5]})
    if out:
        save(out, rows)
        print(f"match: {sum(1 for r in rows if r['exact'])} точных, "
              f"{sum(1 for r in rows if not r['exact'] and r['candidates'])} с кандидатами -> {out}")
    else:
        print(json.dumps(rows, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("compute").add_argument("findings")
    sub.add_parser("dedupe").add_argument("findings")
    m = sub.add_parser("match")
    m.add_argument("findings")
    m.add_argument("issues", nargs="+")
    m.add_argument("--out")
    m.add_argument("--threshold", type=float, default=0.35)
    o = sub.add_parser("one")
    o.add_argument("--direction", required=True)
    o.add_argument("--check", required=True)
    o.add_argument("--screen", required=True)
    o.add_argument("--element", default="")
    o.add_argument("--package", default="")
    a = ap.parse_args()
    if a.cmd == "compute":
        cmd_compute(a.findings)
    elif a.cmd == "dedupe":
        cmd_dedupe(a.findings)
    elif a.cmd == "match":
        cmd_match(a.findings, a.issues, a.out, a.threshold)
    else:
        print(compute(a.direction, a.check, a.screen, a.element, a.package))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
