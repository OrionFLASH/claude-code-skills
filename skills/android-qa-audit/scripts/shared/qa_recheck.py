"""Independent re-check of findings before publication (S-9) and the legal second check (shared by QA skills).

Every finding carries `repro` — how to re-run the measurement with one command:
    "repro": {"argv": ["node", "<SKILL_DIR>/scripts/node/repro.js", "--url", "…", "--js", "…"], "expect": "regex"}
    "repro": {"cmd": "python3 <SKILL_DIR>/scripts/adb_helpers.py dump-ui --serial <SERIAL> --find 'Купить'"}
A skill wrapper may translate its own short forms (site: {"url", "js" | "selector", "device"}) into argv.
Only the skill's own scripts may be run: argv[0] is node/python and argv[1] lies inside <SKILL_DIR>/scripts/ —
anything else is refused (re-check by hand and record it with `set`). <SKILL_DIR>, <RUN_DIR> and other
placeholders from `subst` are replaced. No shell is used.

Reproduced?  1) JSON in stdout with "reproduced": true/false; 2) repro.expect — regex over stdout;
             3) repro.expect_exit — exit code; 4) otherwise exit code 0. Exit code 4 (guard unavailable),
             a timeout or a start failure is an error, never «reproduced».
Status: confirmed (all N runs reproduced), flaky (some), not-reproduced (none), error, refused, no-repro.
Written to finding.recheck = {status, runs, by, at, independent}. Manual results (another executor) — `set`.

Gate (before any publication): a finding to publish needs recheck.status == confirmed with at least 2 reproduced
runs (or a manual confirmation by another executor); a finding with legal.norms needs legal.second_check
(another executor) and legal.lawyer_review = true («проверить юристом» in the text). Stdlib only, Python 3.8+.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PUBLISH_STATUSES = {"NEW", "FIXED-INSUFFICIENT", "REGRESSION", None}
RUNNERS = {"node", "node.exe", "python", "python3", "python.exe", "py", "py.exe"}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, data):
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def findings_of(data):
    return data["findings"] if isinstance(data, dict) else data


def substitute(s, subst):
    for k, v in subst.items():
        s = s.replace(f"<{k}>", str(v))
    return s


def build_argv(repro, subst, translate=None):
    """-> (argv, None) or (None, reason)."""
    if not isinstance(repro, dict) or not repro:
        return None, "нет repro"
    if translate:
        tr = translate(repro, subst)
        if tr:
            repro = dict(repro, argv=tr)
    if repro.get("argv"):
        argv = [substitute(str(x), subst) for x in repro["argv"]]
    elif repro.get("cmd"):
        try:
            argv = [substitute(x, subst) for x in shlex.split(str(repro["cmd"]))]
        except ValueError as ex:
            return None, f"cmd не разобран: {ex}"
    else:
        return None, "в repro нет argv/cmd (и короткая форма скила не подходит)"
    return argv, None


def allowed(argv, skill_dir):
    if len(argv) < 2:
        return "команда без скрипта"
    if os.path.basename(argv[0]).lower() not in RUNNERS and Path(argv[0]).resolve() != Path(sys.executable).resolve():
        return f"запуск только node/python, получено {argv[0]}"
    scripts = (Path(skill_dir) / "scripts").resolve()
    target = Path(argv[1]).resolve()
    try:
        target.relative_to(scripts)
    except ValueError:
        return f"скрипт вне {scripts}: {argv[1]}"
    if not target.is_file():
        return f"скрипта нет: {argv[1]}"
    return None


def json_reproduced(out):
    """"reproduced": bool from the whole stdout or its last JSON line; None if absent."""
    cands = [out or ""] + list(reversed([ln for ln in (out or "").strip().splitlines() if ln.strip()]))
    for c in cands:
        try:
            j = json.loads(c)
        except ValueError:
            continue
        if isinstance(j, dict) and isinstance(j.get("reproduced"), bool):
            return j["reproduced"]
    return None


def run_once(argv, repro, timeout, env=None, error_codes=(4,)):
    t0 = time.time()
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"at": now(), "code": None, "error": f"таймаут {timeout} с"}
    except OSError as ex:
        return {"at": now(), "code": None, "error": f"не запустилось: {ex}"}
    out = r.stdout or ""
    res = {"at": now(), "code": r.returncode, "seconds": round(time.time() - t0, 1), "out": out[-400:]}
    if r.returncode in error_codes:
        res["error"] = f"guard недоступен (код {r.returncode})"
        return res
    jr = json_reproduced(out)
    if jr is not None:
        res["reproduced"] = jr
    elif repro.get("expect"):
        res["reproduced"] = bool(re.search(repro["expect"], out, re.S))
    elif repro.get("expect_exit") is not None:
        res["reproduced"] = r.returncode == int(repro["expect_exit"])
    elif r.returncode == 0:
        res["reproduced"] = True
    else:  # no verdict and a failure code: an error, never «not reproduced»
        res["error"] = f"код {r.returncode} без ответа reproduced: {(r.stderr or '').strip()[-200:]}"
    return res


def status_of(runs):
    if any("error" in r for r in runs):
        return "error"
    hits = sum(1 for r in runs if r.get("reproduced"))
    return "confirmed" if hits == len(runs) and runs else "flaky" if hits else "not-reproduced"


def recheck(run_dir, skill_dir, ids=None, times=2, pause=1.0, timeout=180, translate=None, extra_subst=None,
            env=None, dry_run=False, error_codes=(4,)):
    run_dir = Path(run_dir)
    data = load(run_dir / "findings.json")
    subst = {"SKILL_DIR": skill_dir, "RUN_DIR": str(run_dir), **(extra_subst or {})}
    report = []
    for f in findings_of(data):
        if ids and f.get("id") not in ids:
            continue
        if not ids and f.get("status") not in PUBLISH_STATUSES:
            continue
        argv, why = build_argv(f.get("repro"), subst, translate)
        if not argv:
            rec = {"status": "no-repro", "reason": why, "by": "recheck.py", "at": now()}
        else:
            bad = allowed(argv, skill_dir)
            if bad:
                rec = {"status": "refused", "reason": bad + " — перепроверить вручную (recheck.py set)", "by": "recheck.py", "at": now()}
            elif dry_run:
                rec = {"status": "planned", "argv": argv}
            else:
                runs = []
                for i in range(max(1, times)):
                    if i:
                        time.sleep(pause)
                    runs.append(run_once(argv, f["repro"], timeout, env, error_codes))
                    if "error" in runs[-1]:
                        break
                rec = {"status": status_of(runs), "runs": runs, "by": "recheck.py", "independent": True, "at": now(),
                       "argv": argv}
        if not dry_run:
            f["recheck"] = rec
        report.append({"id": f.get("id"), "title": f.get("title"), **{k: v for k, v in rec.items() if k != "runs"},
                       "reproduced_runs": sum(1 for r in rec.get("runs", []) if r.get("reproduced"))})
    if not dry_run:
        save(run_dir / "findings.json", data)
    return report


def set_manual(run_dir, fid, status, by, independent=True, note=None):
    run_dir = Path(run_dir)
    data = load(run_dir / "findings.json")
    hit = [f for f in findings_of(data) if f.get("id") == fid]
    if not hit:
        raise SystemExit(f"recheck set: находка {fid} не найдена")
    if not by:
        raise SystemExit("recheck set: нужен --by (кто и чем перепроверил: исполнитель, браузер, шаги)")
    hit[0]["recheck"] = {"status": status, "by": by, "independent": bool(independent), "manual": True, "at": now(),
                         **({"note": note} if note else {})}
    save(run_dir / "findings.json", data)
    return hit[0]["recheck"]


def set_legal(run_dir, fid, by, result, lawyer=True, note=None, norms=None):
    run_dir = Path(run_dir)
    data = load(run_dir / "findings.json")
    hit = [f for f in findings_of(data) if f.get("id") == fid]
    if not hit:
        raise SystemExit(f"recheck legal: находка {fid} не найдена")
    legal = hit[0].setdefault("legal", {})
    if norms:
        legal["norms"] = norms
    legal["second_check"] = {"by": by, "result": result, "at": now(), **({"note": note} if note else {})}
    legal["lawyer_review"] = bool(lawyer)
    save(run_dir / "findings.json", data)
    return legal


def gate_problems(f):
    """Reasons why a finding may not be published yet (empty list = may be published)."""
    out = []
    rc = f.get("recheck") or {}
    st = rc.get("status")
    if st != "confirmed":
        out.append(f"перепроверка: {st or 'не выполнялась'}" + (f" ({rc.get('reason')})" if rc.get("reason") else ""))
    elif not rc.get("manual") and sum(1 for r in rc.get("runs", []) if r.get("reproduced")) < 2:
        out.append("перепроверка: воспроизведено меньше 2 раз")
    elif rc.get("manual") and not rc.get("independent"):
        out.append("перепроверка выполнена тем же исполнителем — нужна независимая")
    legal = f.get("legal") or {}
    if legal.get("norms") or f.get("direction") == "legal-ui" and legal.get("claims_law"):
        sc = legal.get("second_check") or {}
        if not sc.get("by"):
            out.append("правовые нормы без второй проверки другим исполнителем")
        elif sc.get("result") == "rejected":
            out.append("вторая проверка не подтвердила правовые нормы")
        if not legal.get("lawyer_review"):
            out.append("нет пометки «проверить юристом»")
    if (f.get("evidence") or {}).get("sensitive"):
        out.append("чувствительная находка (evidence.sensitive) — только по решению пользователя")
    return out


def gate(run_dir, ids=None, all_findings=False):
    data = load(Path(run_dir) / "findings.json")
    rows = []
    for f in findings_of(data):
        if ids and f.get("id") not in ids:
            continue
        if not ids and not all_findings and f.get("status") not in PUBLISH_STATUSES:
            continue
        rows.append({"id": f.get("id"), "title": f.get("title"), "problems": gate_problems(f)})
    return rows


def cli(argv, skill_name, skill_dir, translate=None, extra_subst=None, error_codes=(4,)):
    import argparse
    ap = argparse.ArgumentParser(prog="recheck.py", description=f"""Independent re-check of {skill_name} findings (repro)
and the publication gate.

  recheck.py run  <RUN_DIR> [--id F-001 --id F-002] [--times 2] [--pause 1] [--timeout 180] [--dry-run]
                  [--subst SERIAL=emulator-5554]   extra <PLACEHOLDER> values for repro commands
  recheck.py set  <RUN_DIR> --id F-001 --status confirmed|flaky|not-reproduced --by "кто, чем, шаги" [--same-executor]
  recheck.py legal <RUN_DIR> --id F-001 --by "второй исполнитель …" --result confirmed|corrected|rejected
                  [--norm "152-ФЗ ст. 9"] [--note "…"] [--no-lawyer]
  recheck.py gate <RUN_DIR> [--id …] [--all]      exit 1 if anything may not be published yet
Exit codes: 0 ok, 1 not confirmed / gate closed, 2 bad input.""", formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "set", "legal", "gate"])
    ap.add_argument("run_dir")
    ap.add_argument("--id", action="append")
    ap.add_argument("--times", type=int, default=2)
    ap.add_argument("--pause", type=float, default=1.0)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--status", choices=["confirmed", "flaky", "not-reproduced"])
    ap.add_argument("--by")
    ap.add_argument("--same-executor", action="store_true")
    ap.add_argument("--note")
    ap.add_argument("--result", choices=["confirmed", "corrected", "rejected"])
    ap.add_argument("--norm", action="append")
    ap.add_argument("--no-lawyer", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--subst", action="append", default=[], help="KEY=VALUE: значение плейсхолдера <KEY> в repro")
    a = ap.parse_args(argv)
    if not (Path(a.run_dir) / "findings.json").is_file():
        print(f"recheck: нет {Path(a.run_dir) / 'findings.json'}")
        return 2
    subst = dict(extra_subst or {})
    for kv in a.subst:
        if "=" not in kv:
            ap.error(f"--subst KEY=VALUE, получено {kv!r}")
        k, v = kv.split("=", 1)
        subst[k.strip()] = v
    if a.cmd == "run":
        rep = recheck(a.run_dir, skill_dir, a.id, a.times, a.pause, a.timeout, translate, subst, dry_run=a.dry_run, error_codes=error_codes)
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 0 if all(r["status"] in ("confirmed", "planned") for r in rep) else 1
    if a.cmd == "set":
        if not (a.id and a.status):
            ap.error("нужны --id и --status")
        print(json.dumps(set_manual(a.run_dir, a.id[0], a.status, a.by, not a.same_executor, a.note), ensure_ascii=False))
        return 0
    if a.cmd == "legal":
        if not (a.id and a.by and a.result):
            ap.error("нужны --id, --by и --result")
        print(json.dumps(set_legal(a.run_dir, a.id[0], a.by, a.result, not a.no_lawyer, a.note, a.norm), ensure_ascii=False))
        return 0
    rows = gate(a.run_dir, a.id, a.all)
    closed = [r for r in rows if r["problems"]]
    for r in rows:
        print(f"{r['id']}: " + ("можно публиковать" if not r["problems"] else "НЕЛЬЗЯ: " + "; ".join(r["problems"])))
    print(f"gate: находок {len(rows)}, к публикации готово {len(rows) - len(closed)}, закрыто {len(closed)}")
    return 1 if closed else 0
