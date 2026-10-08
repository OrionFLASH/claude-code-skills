#!/usr/bin/env python3
"""Keep local QA results (<OUTPUT_ROOT>/qa-runs/) and build artifacts out of git.

Shared module (shared/scripts/qa_gitignore.py, vendored into <skill>/scripts/shared/ via .shared);
a skill exposes it as scripts/gitignore_helper.py with its own default patterns and label.

Rule: unless the user explicitly allowed committing the results in the request, the results folder MUST be
ignored by git. The skill calls `ensure` right after <OUTPUT_ROOT> is known and BEFORE the run folder is created.

  gitignore_helper.py ensure <OUTPUT_ROOT> [--allow-commit-results] [--allow-commit-apk] [--config run-config.yaml]
                      [--text "request"] [--mode gitignore|exclude] [--pattern P ...] [--json]
      Apply the policy: results patterns (with "/", e.g. qa-runs/) are ignored unless committing results is allowed
      (git.allow_commit_results), artifact patterns (no "/", e.g. *.apk, *.keystore) are ignored unless
      git.allow_commit_apk. Allowed patterns are never touched. <OUTPUT_ROOT> may not exist yet.
      Files of qa-runs/ already tracked by git are NOT removed: the command is printed (see `untrack`).
      Exit: 0 done (not in a repo, or everything required is ignored now), 1 ask the user: files under qa-runs/
            are already tracked (one question: run `untrack --yes`?), 2 error, 3 lines written but still not
            ignored (overridden by a "!" rule — show `git check-ignore -v`).
  gitignore_helper.py untrack <OUTPUT_ROOT> [--yes] [--json]
      Plan (without --yes) or run (with --yes, only after the user's "yes") `git rm -r --cached` for the
      results patterns: the files stay on disk, only the index changes; the commit is up to the user.
  gitignore_helper.py check <OUTPUT_ROOT> [--pattern P ...] [--label NAME] [--json]
      State only. Exit: 0 nothing to do (not in a repo, everything ignored, or the old "keep" decision),
            1 inside a repo and at least one pattern is not ignored, 2 error.
  gitignore_helper.py apply <OUTPUT_ROOT> --mode gitignore|exclude|keep [--pattern P ...] [--label NAME] [--json]
      Low level: append the missing lines to .gitignore of the repository root (gitignore) or to
      .git/info/exclude (exclude, local only); keep — write qa-runs/.gitignore-decision (legacy, `ensure`
      does not honour it). Idempotent. Exit: 0 done, 1 lines written but something is still not ignored, 2 error.

Patterns (default: qa-runs/):
  with "/" (qa-runs/, qa-runs/**/*.mp4) — results: a path relative to <OUTPUT_ROOT>, written anchored: /<prefix>qa-runs/
  without "/" (*.apk, *.keystore)       — artifacts: a name glob, written as is: matches anywhere in the repository

commit_permission(text) — explicit permission to commit results / APK in a free-form request (RU/EN), used by
intake.py from-text and `ensure --text`: true only for an explicit, non-negated phrase («коммить результаты»,
«положи результаты в репозиторий», "commit the results", «не добавляй qa-runs в .gitignore»…).
Python 3.8+, standard library only.
"""
import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

RUNS = "qa-runs"
DECISION = ".gitignore-decision"
DEFAULT_PATTERNS = ["qa-runs/"]


# ---------- explicit permission in the request ----------

_NEG = re.compile(r"(?:\bне\b|\bнельзя\b|\bникогда\b|\bбез\b|\bdon'?t\b|\bdo\s+not\b|\bnever\b|\bnot\b|\bno\b)"
                  r"[\s\w-]{0,16}$")
_RESULTS = r"(?:результат\w*|итог\w*|отч[её]т\w*|qa-runs|находк\w*|папк\w*\s+(?:тестирования|результатов|прогона)|" \
           r"results?|reports?|findings|qa\s+runs)"
_APK = r"(?:apks?|aab|xapk|сборк\w*|keystore|jks|ключ\w*\s+подпис\w*|builds?|signing\s+keys?)"
_COMMIT = r"(?:(?:за)?ком+ит(?:ь|ьте|ить|им|ите|ишь|ил|ила|или|ят)|commit(?:ting|ted)?|check\s+in)"
_PUT = r"(?:полож\w*|клад\w*|клади\w*|добав\w*|сохран\w*|хран\w*|остав\w*|включ\w*|запуш\w*|" \
       r"put|add|keep|store|save|include|leave|push)"
_TARGET = re.compile(r"(?:\b(?:в|во|in|into|to)\s+(?:the\s+|наш\w*\s+|этот\s+|мой\s+|my\s+|our\s+)?"
                     r"(?:git\b|гит\w*|репозитори\w*|репо\b|repo\w*|version\s+control))")
_PARTICLES = r"(?:тоже|также|можно|нужно|надо|обязательно|смело|сразу|can|should|may|also|too|be|will|must)"
_STOP = {"и", "или", "а", "но", "затем", "потом", "and", "or", "then", "but"}
_FILLER = {"the", "a", "an", "all", "my", "our", "these", "this", "test", "qa", "too", "also", "все", "всё", "мои", "наши",
           "эти", "этот", "тестов", "тестирования", "итоговые", "тоже", "также"}
_IGNORE_NEG = re.compile(r"(?:не\s+(?:добавля\w*|клади\w*|клад\w*|внос\w*|пиши\w*|пиш\w*)\s+(?:\S+\s+){0,3}?(?:в\s+)?\.?gitignore|"
                         r"не\s+игнорир\w*|don'?t\s+(?:add|put)\s+(?:\S+\s+){0,3}?(?:to|in|into)\s+(?:the\s+)?\.?gitignore|"
                         r"(?:don'?t|do\s+not)\s+(?:git)?ignore)")
_CONFIG = {"results": re.compile(r"allow_commit_results\s*[:=]\s*true", re.I),
           "apk": re.compile(r"allow_commit_apk\s*[:=]\s*true", re.I)}


def _clauses(text):
    # a dot splits only before a space or the end: «в .gitignore», «*.apk» stay in one clause
    return [c.strip() for c in re.split(r"[.!?;]+(?=\s|$)|\n+", text or "") if c and c.strip()]


def _negated(low, pos):
    return bool(_NEG.search(low[max(0, pos - 24):pos]))


def _gap_ok(words):
    """Words between the verb and the object: up to 2 arbitrary ones without conjunctions («закоммить все
    результаты»), or up to 5 fillers / other objects joined by conjunctions («commit the results and the APK»)."""
    if not words:
        return True
    if len(words) <= 2 and not set(words) & _STOP:
        return True
    objects = [w for w in words if re.fullmatch(f"{_RESULTS}|{_APK}", w)]
    return len(words) <= 5 and bool(objects) and all(w in _FILLER or w in _STOP or w in objects for w in words)


def _near(low, verb, obj):
    """verb … obj (see _gap_ok) or obj [particles] verb; the verb is not negated."""
    rx_fwd = re.compile(rf"({verb})((?:\W+[\w-]+){{0,5}}?)\W+{obj}\b")
    for m in rx_fwd.finditer(low):
        if _gap_ok(re.findall(r"[\w-]+", m.group(2))) and not _negated(low, m.start(1)):
            return m.group(0)
    rx_back = re.compile(rf"{obj}\s+(?:{_PARTICLES}\s+){{0,2}}({verb})")
    for m in rx_back.finditer(low):
        if not _negated(low, m.start(1)):
            return m.group(0)
    return None


def _explicit(clause, obj):
    low = clause.lower()
    if not re.search(obj, low):
        return None
    if _IGNORE_NEG.search(low):
        m = _IGNORE_NEG.search(low)
        return m.group(0)
    if "gitignore" in low or "игнор" in low or "ignore" in low:
        return None  # «добавь qa-runs в .gitignore» — the opposite of a permission
    hit = _near(low, _COMMIT, obj)
    if hit:
        return hit
    if _TARGET.search(low):
        return _near(low, _PUT, obj)
    return None


def commit_permission(text):
    """{"allow_commit_results": bool, "allow_commit_apk": bool, "evidence": {...}} — explicit permission only."""
    res = {"allow_commit_results": False, "allow_commit_apk": False, "evidence": {}}
    for key, obj in (("results", _RESULTS), ("apk", _APK)):
        if _CONFIG[key].search(text or ""):
            res[f"allow_commit_{key}"] = True
            res["evidence"][key] = _CONFIG[key].search(text).group(0)
            continue
        for cl in _clauses(text):
            hit = _explicit(cl, obj)
            if hit:
                res[f"allow_commit_{key}"] = True
                res["evidence"][key] = cl[:160]
                break
    return res


# ---------- git ----------

def git(cwd, *args):
    try:
        p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired) as ex:
        return 1, "", str(ex)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def escape(path):
    """gitignore pattern for a literal path: escape glob characters."""
    return "".join("\\" + ch if ch in "*?[\\" else ch for ch in path)


def fail(msg):
    sys.stderr.write(f"gitignore_helper: {msg}\n")
    sys.exit(2)


def norm_pattern(p):
    p = (p or "").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if not p or p.startswith("/") or p.startswith("!") or ".." in p.split("/"):
        fail(f"недопустимый шаблон «{p}»: нужен путь относительно OUTPUT_ROOT (qa-runs/) или маска имени (*.apk)")
    return p


def is_results(pattern):
    return "/" in pattern


def describe(prefix, pattern):
    """(line for the ignore file, probe path relative to the repo root, pathspec for ls-files)."""
    if is_results(pattern):  # a path next to OUTPUT_ROOT: qa-runs/, qa-runs/**/*.mp4
        rel = prefix + pattern
        probe = rel.replace("**/", "").replace("*", "qa-probe").replace("?", "q")
        return "/" + escape(prefix) + pattern, probe, rel.rstrip("/")
    probe = prefix + pattern.replace("*", "qa-probe").replace("?", "q")
    return pattern, probe, pattern


def locate(root, allow_missing=False):
    """(resolved OUTPUT_ROOT, existing folder to ask git from, path of OUTPUT_ROOT relative to it)."""
    root = Path(root).expanduser()
    if root.is_dir():
        return root.resolve(), root.resolve(), ""
    if not allow_missing or root.exists():
        fail(f"нет папки {root}")
    root = root.resolve()
    base = root
    while not base.is_dir():
        if base.parent == base:
            fail(f"нет ни одной существующей папки на пути {root}")
        base = base.parent
    return root, base, root.relative_to(base).as_posix().strip("/") + "/"


def inspect(root, patterns, allow_missing=False):
    """State of the patterns with respect to git. Exits with 2 on errors."""
    if not shutil.which("git"):
        fail("git не найден")
    root, base, tail = locate(root, allow_missing)
    code, top, _ = git(base, "rev-parse", "--show-toplevel")
    state = {"output_root": str(root), "exists": root.is_dir(), "in_repo": code == 0, "repo": top if code == 0 else None,
             "prefix": None, "patterns": [], "path": None, "pattern": None, "ignored": False, "tracked_files": 0,
             "decision": None}
    marker = root / RUNS / DECISION
    if marker.is_file():
        state["decision"] = (marker.read_text(encoding="utf-8").split() or [""])[0] or None
    if code != 0:
        return state
    _, prefix, _ = git(base, "rev-parse", "--show-prefix")  # "" at the top, "sub/dir/" below
    prefix = (prefix or "") + tail
    state["prefix"] = prefix
    for pat in patterns:
        line, probe, spec = describe(prefix, pat)
        # --no-index: judge by ignore rules only; a folder with tracked files is otherwise never "ignored"
        ignored = git(top, "check-ignore", "-q", "--no-index", "--", probe)[0] == 0
        _, tracked, _ = git(top, "ls-files", "--", spec)
        files = [x for x in tracked.splitlines() if x]
        state["patterns"].append({"pattern": pat, "kind": "results" if is_results(pat) else "artifacts", "line": line,
                                  "probe": probe, "pathspec": spec, "ignored": ignored, "tracked_files": len(files),
                                  "tracked_sample": files[:5]})
    first = state["patterns"][0] if state["patterns"] else {}
    state["path"] = (prefix + first["pattern"]) if first else None
    state["pattern"] = first.get("line")
    state["ignored"] = all(p["ignored"] for p in state["patterns"])
    state["tracked_files"] = sum(p["tracked_files"] for p in state["patterns"])
    return state


def append_lines(path, lines, label):
    """Append missing lines (with one comment). Returns the list of lines actually added."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    have = {x.strip() for x in text.splitlines()}
    add = [ln for ln in lines if ln not in have]
    if not add:
        return []
    if text and not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text + f"# {label}: local QA results and build artifacts (not for git)\n" + "\n".join(add) + "\n")
    return add


def ignore_file(top, mode):
    if mode == "gitignore":
        return top / ".gitignore"
    _, gp, _ = git(top, "rev-parse", "--git-path", "info/exclude")
    return Path(gp) if Path(gp).is_absolute() else top / gp


def untrack_command(state, pat):
    return f"git -C \"{state['repo']}\" rm -r --cached -- \"{pat['pathspec']}\""


def report(state, as_json, extra=""):
    if as_json:
        out = dict(state)
        if extra:
            out["message"] = extra
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    if not state["in_repo"]:
        print(f"{state['output_root']}: не в git-репозитории — ничего делать не нужно")
        if extra:
            print(extra)
        return
    print(f"репозиторий: {state['repo']} (OUTPUT_ROOT: {state['prefix'] or '.'})")
    for p in state["patterns"]:
        if p.get("allowed"):
            mark = "разрешено коммитить — не трогаю" + (" (но уже игнорируется)" if p["ignored"] else "")
        elif p["ignored"]:
            mark = "игнорируется"
        elif state["decision"] == "keep" and "required" not in p:
            mark = "не игнорируется, пользователь решил коммитить"
        else:
            mark = "НЕ игнорируется"
        print(f"  {p['pattern']:<16} → строка {p['line']:<24} {mark}")
        if p["tracked_files"] and state.get("cmd") == "ensure" and p["kind"] == "artifacts":
            print(f"    уже в индексе git файлов: {p['tracked_files']} (например, {', '.join(p['tracked_sample'][:2])}) — "
                  "файлы проекта, скил их не трогает")
        elif p["tracked_files"]:
            print(f"    уже в индексе git файлов: {p['tracked_files']} — .gitignore их не уберёт; команда "
                  f"(выполняется только после «да» пользователя): {untrack_command(state, p)}")
    if extra:
        print(extra)


# ---------- commands ----------

def cmd_check(a, patterns):
    st = inspect(a.dir, patterns)
    report(st, a.json)
    need = st["in_repo"] and not st["ignored"] and st["decision"] != "keep"
    sys.exit(1 if need else 0)


def cmd_apply(a, patterns):
    st = inspect(a.dir, patterns)
    if not st["in_repo"]:
        fail(f"{st['output_root']} не в git-репозитории — нечего добавлять")
    root, top = Path(st["output_root"]), Path(st["repo"])
    if a.mode == "keep":
        marker = root / RUNS / DECISION
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"keep {datetime.date.today().isoformat()} {' '.join(patterns)}\n", encoding="utf-8")
        st["decision"] = "keep"
        report(st, a.json, f"записано: {marker}")
        sys.exit(0)
    todo = [p["line"] for p in st["patterns"] if not p["ignored"]]
    if not todo:
        report(st, a.json, "всё уже игнорируется — файлы не менялись")
        sys.exit(0)
    target = ignore_file(top, a.mode)
    added = append_lines(target, todo, a.label)
    st = inspect(a.dir, patterns)
    st["file"], st["added"] = str(target), added
    report(st, a.json, (f"добавлено в {target}: {', '.join(added)}" if added else f"строки уже были: {target}"))
    if not st["ignored"]:
        sys.stderr.write("gitignore_helper: строки есть, но не всё игнорируется — проверьте правила с «!» "
                         "(git check-ignore -v)\n")
        sys.exit(1)
    sys.exit(0)


def policy(a):
    """allow_commit_results / allow_commit_apk from flags, run-config (git.*) and the request text."""
    allow = {"results": bool(a.allow_commit_results), "apk": bool(a.allow_commit_apk)}
    why = {k: ("флаг --allow-commit-" + k) for k, v in allow.items() if v}
    if a.config:
        try:
            import miniyaml  # vendored next to this module
            g = (miniyaml.load_file(a.config) or {}).get("git") or {}
        except (OSError, ValueError, ImportError) as ex:
            fail(f"не прочитать {a.config}: {ex}")
        for k in ("results", "apk"):
            if g.get(f"allow_commit_{k}") is True and not allow[k]:
                allow[k], why[k] = True, f"{a.config}: git.allow_commit_{k}: true"
    if a.text:
        perm = commit_permission(a.text)
        for k in ("results", "apk"):
            if perm[f"allow_commit_{k}"] and not allow[k]:
                allow[k], why[k] = True, f"в запросе: «{perm['evidence'][k]}»"
    return allow, why


def cmd_ensure(a, patterns):
    allow, why = policy(a)
    st = inspect(a.dir, patterns, allow_missing=True)
    st["cmd"] = "ensure"
    st["allow_commit_results"], st["allow_commit_apk"] = allow["results"], allow["apk"]
    st["why"] = why
    if not st["in_repo"]:
        report(st, a.json, "→ .gitignore не нужен")
        sys.exit(0)
    for p in st["patterns"]:
        p["allowed"] = allow[p["kind"] if p["kind"] == "results" else "apk"]
        p["required"] = not p["allowed"]
    todo = [p["line"] for p in st["patterns"] if p["required"] and not p["ignored"]]
    added, target = [], None
    if todo:
        target = ignore_file(Path(st["repo"]), a.mode)
        added = append_lines(target, todo, a.label)
        allowed = {p["pattern"] for p in st["patterns"] if p["allowed"]}
        st2 = inspect(a.dir, patterns, allow_missing=True)
        for p in st2["patterns"]:
            p["allowed"] = p["pattern"] in allowed
            p["required"] = not p["allowed"]
        st2.update({k: st[k] for k in ("cmd", "allow_commit_results", "allow_commit_apk", "why")})
        st = st2
    st["file"], st["added"] = (str(target) if target else None), added
    tracked = [p for p in st["patterns"] if p["required"] and p["kind"] == "results" and p["tracked_files"]]
    still = [p["pattern"] for p in st["patterns"] if p["required"] and not p["ignored"]]
    st["tracked_results"] = [{"pattern": p["pattern"], "files": p["tracked_files"], "sample": p["tracked_sample"],
                              "command": untrack_command(st, p)} for p in tracked]
    st["still_not_ignored"] = still
    msgs = []
    if added:
        msgs.append(f"добавлено в {target}: {', '.join(added)}")
    elif any(p["required"] for p in st["patterns"]):
        msgs.append("всё нужное уже игнорируется — файлы не менялись")
    for k, label in (("results", "qa-runs/"), ("apk", "сборки и ключи (*.apk, *.keystore …)")):
        if allow[k]:
            msgs.append(f"разрешено коммитить {label} ({why.get(k)}) — эти строки не добавлялись")
    if st["decision"] == "keep" and not allow["results"]:
        msgs.append(f"старое решение «буду коммитить» ({RUNS}/{DECISION}) больше не действует само: без явного "
                    "разрешения в запросе qa-runs/ игнорируется (разрешить — git.allow_commit_results: true)")
    if allow["results"] and any(p["kind"] == "results" and p["ignored"] for p in st["patterns"]):
        msgs.append("qa-runs/ всё ещё игнорируется правилом в .gitignore — чтобы коммитить, уберите его вручную")
    if tracked:
        msgs.append("ВОПРОС пользователю (один): файлы qa-runs/ уже в индексе git и .gitignore их не уберёт — выполнить "
                    "`gitignore_helper.py untrack <OUTPUT_ROOT> --yes` (git rm -r --cached, файлы останутся на диске)?")
    if still:
        msgs.append(f"строки есть, но не игнорируется: {', '.join(still)} — правило с «!» (git check-ignore -v)")
    report(st, a.json, "\n".join(msgs))
    sys.exit(3 if still else 1 if tracked else 0)


def cmd_untrack(a, patterns):
    st = inspect(a.dir, patterns, allow_missing=True)
    if not st["in_repo"]:
        report(st, a.json, "→ нечего убирать из индекса")
        sys.exit(0)
    todo = [p for p in st["patterns"] if p["kind"] == "results" and p["tracked_files"]]
    cmds = [untrack_command(st, p) for p in todo]
    if not todo:
        report(st, a.json, "файлов qa-runs/ в индексе git нет")
        sys.exit(0)
    if not a.yes:
        report(st, a.json, "План (ничего не выполнено; --yes — только после «да» пользователя):\n  " + "\n  ".join(cmds))
        sys.exit(0)
    done = []
    for p in todo:
        code, _, err = git(st["repo"], "rm", "-r", "--cached", "--quiet", "--", p["pathspec"])
        if code != 0:
            fail(f"git rm --cached {p['pathspec']}: {err[:300]}")
        done.append(p["pathspec"])
    st = inspect(a.dir, patterns, allow_missing=True)
    st["untracked"] = done
    report(st, a.json, f"убрано из индекса git (файлы на диске остались): {', '.join(done)}; "
                       "изменение нужно закоммитить — это решает пользователь")
    sys.exit(0)


def main(default_patterns=None, label="qa-runs", argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("ensure", "untrack", "check", "apply"):
        p = sub.add_parser(name)
        p.add_argument("dir", help="OUTPUT_ROOT — папка, в которой лежит (или будет лежать) qa-runs/")
        p.add_argument("--pattern", action="append", default=None,
                       help=f"шаблон (можно несколько); по умолчанию: {' '.join(default_patterns or DEFAULT_PATTERNS)}")
        p.add_argument("--label", default=label, help="подпись в комментарии над строками")
        p.add_argument("--json", action="store_true")
        if name == "apply":
            p.add_argument("--mode", required=True, choices=["gitignore", "exclude", "keep"])
        if name == "ensure":
            p.add_argument("--mode", default="gitignore", choices=["gitignore", "exclude"],
                           help="gitignore (по умолчанию) — .gitignore корня репозитория; exclude — .git/info/exclude")
            p.add_argument("--allow-commit-results", action="store_true",
                           help="пользователь явно разрешил коммитить результаты (git.allow_commit_results)")
            p.add_argument("--allow-commit-apk", action="store_true",
                           help="пользователь явно разрешил коммитить сборки и ключи (git.allow_commit_apk)")
            p.add_argument("--config", help="run-config.yaml: взять git.allow_commit_results / allow_commit_apk")
            p.add_argument("--text", help="текст запроса: явное разрешение коммитить (commit_permission)")
        if name == "untrack":
            p.add_argument("--yes", action="store_true", help="выполнить (только после «да» пользователя)")
    a = ap.parse_args(argv)
    patterns = [norm_pattern(p) for p in (a.pattern or default_patterns or DEFAULT_PATTERNS)]
    patterns = list(dict.fromkeys(patterns))
    {"check": cmd_check, "apply": cmd_apply, "ensure": cmd_ensure, "untrack": cmd_untrack}[a.cmd](a, patterns)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
