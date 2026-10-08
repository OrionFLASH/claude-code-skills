#!/usr/bin/env python3
"""Отпечатки находок и сверка с реестром issues.

  fingerprint.py compute findings.json            проставить fingerprint всем находкам (на месте)
  fingerprint.py dedupe findings.json             слить дубли (одинаковый fingerprint) на месте
  fingerprint.py match findings.json registry.json [--out matches.json]
                                                  кандидаты совпадений с issues (точные по маркеру и нечёткие)
  fingerprint.py one --direction D --check C --url U [--element E]   отпечаток одной находки

Отпечаток не зависит от формулировки заголовка: direction + check_id + шаблон URL + элемент.
Маркер в issue: <!-- site-qa-audit:fp=<fingerprint> -->
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

MARKER_RX = re.compile(r"<!--\s*(?:site-qa-audit:fp=|qa-fp:)([0-9a-f]{12,40})\s*-->")  # skill or neutral marker
STOP = set("the a an of to in on for and or is are not with без и в на не по для из к от что как при".split())


def url_template(url):
    """https://Example.com/items/123?id=5#x -> example.com/items/:id  (query/fragment отбрасываются)."""
    if not url:
        return ""
    p = urlsplit(url)
    segs = []
    for seg in (p.path or "/").split("/"):
        if not seg:
            continue
        if re.fullmatch(r"\d+", seg):
            seg = ":id"
        elif re.fullmatch(r"[0-9a-f]{8}-[0-9a-f-]{27,}", seg, re.I) or re.fullmatch(r"[0-9a-f]{16,}", seg, re.I):
            seg = ":hash"
        segs.append(seg.lower())
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    frag = p.fragment if p.fragment.startswith("/") else ""  # SPA-маршруты вида #/active
    return host + "/" + "/".join(segs) + (("#" + frag) if frag else "")


def norm_element(el):
    if not el:
        return ""
    el = re.sub(r":nth-(child|of-type)\(\d+\)", "", str(el))
    el = re.sub(r"\[\d+\]", "", el)
    return re.sub(r"\s+", " ", el).strip().lower()


def compute(direction, check_id, url, element=""):
    key = "|".join([direction or "", (check_id or "").lower(), url_template(url), norm_element(element)])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def finding_fp(f):
    return compute(f.get("direction"), f.get("check_id"), f.get("url"), f.get("element"))


def tokens(text):
    words = re.findall(r"[\w-]{3,}", (text or "").lower())
    return {w for w in words if w not in STOP}


def similarity(a, b):
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def findings_list(data):
    return data["findings"] if isinstance(data, dict) else data


def cmd_compute(path):
    data = load(path)
    for f in findings_list(data):
        f["fingerprint"] = finding_fp(f)
    save(path, data)
    print(f"compute: {len(findings_list(data))} находок")


def cmd_dedupe(path):
    data = load(path)
    merged, order = {}, []
    for f in findings_list(data):
        fp = f.get("fingerprint") or finding_fp(f)
        f["fingerprint"] = fp
        if fp not in merged:
            merged[fp] = f
            order.append(fp)
            continue
        keep = merged[fp]
        sev = ["critical", "high", "medium", "low", "info"]
        if sev.index(f.get("severity", "info")) < sev.index(keep.get("severity", "info")):
            keep["severity"] = f["severity"]
        for k in ("sources", "screenshots", "environment_list"):
            keep[k] = list(dict.fromkeys((keep.get(k) or []) + (f.get(k) or [])))
        keep.setdefault("merged_ids", []).append(f.get("id"))
    result = [merged[k] for k in order]
    removed = len(findings_list(data)) - len(result)
    if isinstance(data, dict):
        data["findings"] = result
    else:
        data = result
    save(path, data)
    print(f"dedupe: слито дублей {removed}, осталось {len(result)}")


def cmd_match(findings_path, registry_path, out=None, threshold=0.35):
    findings = findings_list(load(findings_path))
    registry = load(registry_path)
    issues = registry["issues"] if isinstance(registry, dict) else registry
    by_fp = {}
    for iss in issues:
        texts = [iss.get("body") or ""] + [c.get("body") or "" for c in iss.get("comments", [])]
        for t in texts:
            for fp in MARKER_RX.findall(t):
                by_fp.setdefault(fp, []).append(iss)
    out_rows = []
    for f in findings:
        fp = f.get("fingerprint") or finding_fp(f)
        exact = [{"repo": i.get("repo"), "number": i["number"], "state": i.get("state"),
                  "state_reason": i.get("state_reason"), "fix_claimed": i.get("fix_claimed"), "how": "marker"}
                 for i in by_fp.get(fp, [])]
        fuzzy = []
        tmpl = url_template(f.get("url"))
        path_part = tmpl.split("/", 1)[1] if "/" in tmpl else ""
        for i in issues:
            if any(e["number"] == i["number"] and e["repo"] == i.get("repo") for e in exact):
                continue
            text = (i.get("title") or "") + " " + (i.get("body") or "")[:1500]
            score = similarity(f.get("title", "") + " " + f.get("actual", ""), text)
            if path_part and path_part in text.lower():
                score += 0.15
            if score >= threshold:
                fuzzy.append({"repo": i.get("repo"), "number": i["number"], "title": i.get("title"),
                              "state": i.get("state"), "state_reason": i.get("state_reason"),
                              "fix_claimed": i.get("fix_claimed"), "score": round(score, 2), "how": "fuzzy"})
        fuzzy.sort(key=lambda x: -x["score"])
        out_rows.append({"id": f.get("id"), "fingerprint": fp, "title": f.get("title"),
                         "exact": exact, "candidates": fuzzy[:5]})
    if out:
        save(out, out_rows)
        print(f"match: {sum(1 for r in out_rows if r['exact'])} точных, "
              f"{sum(1 for r in out_rows if not r['exact'] and r['candidates'])} с кандидатами -> {out}")
    else:
        print(json.dumps(out_rows, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("compute").add_argument("findings")
    sub.add_parser("dedupe").add_argument("findings")
    m = sub.add_parser("match")
    m.add_argument("findings")
    m.add_argument("registry")
    m.add_argument("--out")
    m.add_argument("--threshold", type=float, default=0.35)
    o = sub.add_parser("one")
    for k in ("--direction", "--check", "--url"):
        o.add_argument(k, required=True)
    o.add_argument("--element", default="")
    a = ap.parse_args()
    if a.cmd == "compute":
        cmd_compute(a.findings)
    elif a.cmd == "dedupe":
        cmd_dedupe(a.findings)
    elif a.cmd == "match":
        cmd_match(a.findings, a.registry, a.out, a.threshold)
    else:
        print(compute(a.direction, a.check, a.url, a.element))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
