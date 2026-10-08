"""Direct publication mode (G-6): each finding goes «reproduced twice -> duplicate search -> issue -> screenshots»
straight to the target repository, without piling up drafts. Shared by QA skills (thin wrapper direct_publish.py).

  check  <RUN_DIR> --id F-001 --repo owner/repo [--registry <RUN_DIR>/registry.json …] [--ack-candidates]
         gate (qa_recheck.gate_problems: confirmed twice, legal second check, not sensitive) + not yet published +
         duplicate search with the skill's fingerprint.py match. Exit 0 — publish now (prints the commands),
         1 — gate closed, 2 — fuzzy candidates: read them and decide (then --ack-candidates), 3 — already published or
         an exact duplicate (marker) exists.
  record <RUN_DIR> --id F-001 --repo owner/repo --number 12 --url URL [--kind issue|comment]
         -> <RUN_DIR>/published.json + finding.published (protects against double publication after a crash)
  next   <RUN_DIR> --repo owner/repo     the next finding (by severity) that is not published yet
  status <RUN_DIR>                        what was published

The script never publishes by itself: the orchestrator runs the printed commands (gh issue create … --body-file …,
screenshots — the skill's attach command) after the user's «да» when repos[].confirm_before_publish is true.
Stdlib only, Python 3.8+.
"""
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_recheck  # noqa: E402

SEV = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_repo(r):
    import re
    return re.sub(r"^https?://github\.com/|\.git$|/$", "", r or "")


def load_published(run_dir):
    p = Path(run_dir) / "published.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def already(run_dir, f, repo):
    for p in load_published(run_dir):
        if p.get("id") == f.get("id") and norm_repo(p.get("repo")) == repo:
            return p
    for p in f.get("published") or []:
        if norm_repo(p.get("repo")) == repo and p.get("kind") != "draft":
            return p
    return None


def repo_cfg(run_dir, repo, load_yaml):
    cfg_path = Path(run_dir) / "run-config.yaml"
    if not cfg_path.exists() or not load_yaml:
        return {}
    cfg = load_yaml(str(cfg_path)) or {}
    for r in cfg.get("repos") or []:
        if isinstance(r, dict) and norm_repo(r.get("url") or r.get("repo")) == repo:
            return r
    return {}


def duplicates(f, registries, fingerprint_py):
    with tempfile.TemporaryDirectory() as tmp:
        one = Path(tmp) / "one.json"
        out = Path(tmp) / "m.json"
        one.write_text(json.dumps({"run": {}, "findings": [f]}, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(fingerprint_py), "match", str(one), *map(str, registries), "--out", str(out)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0 or not out.exists():
            raise SystemExit(f"direct: fingerprint.py match завершился с кодом {r.returncode}: {r.stderr.strip()[-300:]}")
        rows = json.loads(out.read_text(encoding="utf-8"))
    row = rows[0] if rows else {"exact": [], "candidates": []}
    return row.get("exact") or [], row.get("candidates") or []


def check(run_dir, fid, repo, registries, fingerprint_py, commands, ack=False, load_yaml=None):
    repo = norm_repo(repo)
    data = qa_recheck.load(Path(run_dir) / "findings.json")
    f = next((x for x in qa_recheck.findings_of(data) if x.get("id") == fid), None)
    if not f:
        return 1, {"id": fid, "problems": ["находка не найдена"]}
    done = already(run_dir, f, repo)
    if done:
        return 3, {"id": fid, "problems": [f"уже опубликовано: {done.get('url') or done.get('number')}"]}
    problems = qa_recheck.gate_problems(f)
    if problems:
        return 1, {"id": fid, "problems": problems,
                   "hint": "воспроизвести дважды: recheck.py run <RUN_DIR> --id " + fid + " (или recheck.py set от другого исполнителя)"}
    regs = [Path(r) for r in registries if r and Path(r).exists()]
    if not regs:
        return 1, {"id": fid, "problems": ["нет выгрузки issues для поиска дублей (registry.json / выгрузка gh) — сначала выгрузить"]}
    exact, cands = duplicates(f, regs, fingerprint_py)
    if exact:
        return 3, {"id": fid, "problems": ["точный дубль по маркеру: " + ", ".join(f"{e.get('repo')}#{e.get('number')}" for e in exact)]}
    if cands and not ack:
        return 2, {"id": fid, "candidates": cands, "problems": ["похожие issues — прочитать и решить: дубль или новое (затем --ack-candidates)"]}
    rc = repo_cfg(run_dir, repo, load_yaml)
    plan = {"id": fid, "title": f.get("title"), "repo": repo, "confirm_before_publish": rc.get("confirm_before_publish", True),
            "commands": [c.format(run_dir=run_dir, id=fid, repo=repo, slug=repo.replace("/", "__")) for c in commands],
            "then": f"direct_publish.py record {run_dir} --id {fid} --repo {repo} --number <N> --url <URL>"}
    if plan["confirm_before_publish"]:
        plan["ask"] = f"Опубликовать {fid} «{f.get('title')}» в {repo}? (confirm_before_publish: true — ждать «да»)"
    return 0, plan


def record(run_dir, fid, repo, number, url, kind="issue"):
    repo = norm_repo(repo)
    path = Path(run_dir) / "findings.json"
    data = qa_recheck.load(path)
    f = next((x for x in qa_recheck.findings_of(data) if x.get("id") == fid), None)
    if not f:
        raise SystemExit(f"direct record: находка {fid} не найдена")
    entry = {"repo": repo, "number": number, "url": url, "kind": kind}
    f.setdefault("published", []).append(entry)
    qa_recheck.save(path, data)
    pub = load_published(run_dir) + [dict(entry, id=fid, title=f.get("title"), at=now())]
    (Path(run_dir) / "published.json").write_text(json.dumps(pub, ensure_ascii=False, indent=1), encoding="utf-8")
    return entry


def next_finding(run_dir, repo):
    repo = norm_repo(repo)
    data = qa_recheck.load(Path(run_dir) / "findings.json")
    pending = [f for f in qa_recheck.findings_of(data)
               if f.get("status") in qa_recheck.PUBLISH_STATUSES and not already(run_dir, f, repo)]
    pending.sort(key=lambda f: (SEV.get(f.get("severity"), 9), f.get("id") or ""))
    return pending[0] if pending else None


def cli(argv, skill_name, fingerprint_py, commands, default_registries, load_yaml=None):
    import argparse
    ap = argparse.ArgumentParser(prog="direct_publish.py", description=__doc__.split("\n\n")[0] + f" ({skill_name})",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("cmd", choices=["check", "record", "next", "status"])
    ap.add_argument("run_dir")
    ap.add_argument("--id")
    ap.add_argument("--repo")
    ap.add_argument("--registry", action="append")
    ap.add_argument("--ack-candidates", action="store_true")
    ap.add_argument("--number", type=int)
    ap.add_argument("--url")
    ap.add_argument("--kind", default="issue", choices=["issue", "comment"])
    a = ap.parse_args(argv)
    if a.cmd == "status":
        pub = load_published(a.run_dir)
        for p in pub:
            print(f"{p.get('id')} -> {p.get('repo')}#{p.get('number')} {p.get('url') or ''}")
        print(f"published: {len(pub)}")
        return 0
    if not a.repo:
        ap.error("нужен --repo owner/repo")
    if a.cmd == "next":
        f = next_finding(a.run_dir, a.repo)
        print(json.dumps({"id": f.get("id"), "title": f.get("title"), "severity": f.get("severity")} if f else {"id": None},
                         ensure_ascii=False))
        return 0 if f else 1
    if not a.id:
        ap.error("нужен --id")
    if a.cmd == "record":
        if not a.number:
            ap.error("нужен --number")
        print(json.dumps(record(a.run_dir, a.id, a.repo, a.number, a.url, a.kind), ensure_ascii=False))
        return 0
    regs = a.registry or [str(Path(a.run_dir) / r) for r in default_registries]
    code, res = check(a.run_dir, a.id, a.repo, regs, fingerprint_py, commands, a.ack_candidates, load_yaml)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return code
