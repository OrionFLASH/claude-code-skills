#!/usr/bin/env python3
"""Keep local QA results (<OUTPUT_ROOT>/qa-runs/) and build artifacts out of git.

Shared module (shared/scripts/qa_gitignore.py, vendored into <skill>/scripts/shared/ via .shared);
a skill exposes it as scripts/gitignore_helper.py with its own default patterns and label.

  gitignore_helper.py check <OUTPUT_ROOT> [--pattern P ...] [--label NAME] [--json]
      Is <OUTPUT_ROOT> inside a git work tree, and is every pattern ignored there?
      Exit: 0 nothing to ask (not in a repo, everything ignored, or the user chose to keep results in git),
            1 ask the user (inside a repo and at least one pattern is not ignored), 2 error.
  gitignore_helper.py apply <OUTPUT_ROOT> --mode gitignore|exclude|keep [--pattern P ...] [--label NAME] [--json]
      gitignore — append the missing lines to .gitignore in the repository root;
      exclude   — the same lines in .git/info/exclude (local only, the repository is not changed);
      keep      — remember "keep results in git" in qa-runs/.gitignore-decision, so check stops asking.
      Idempotent: an existing line is not added twice. Exit: 0 done (ignored now, or keep recorded),
      1 lines were written but something is still not ignored (a "!" rule overrides it), 2 error.

Patterns (default: qa-runs/):
  with "/" (qa-runs/, qa-runs/**/*.mp4) — a path relative to <OUTPUT_ROOT>, written anchored: /<prefix>qa-runs/
  without "/" (*.apk, *.keystore)       — a name glob, written as is: matches anywhere in the repository
Only runs after an explicit answer of the user; never touches files already tracked by git
(prints the `git rm -r --cached` command instead). Python 3.8+, standard library only.
"""
import argparse
import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

RUNS = "qa-runs"
DECISION = ".gitignore-decision"
DEFAULT_PATTERNS = ["qa-runs/"]


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


def describe(prefix, pattern):
    """(line for the ignore file, probe path relative to the repo root, pathspec for ls-files)."""
    if "/" in pattern:  # a path next to OUTPUT_ROOT: qa-runs/, qa-runs/**/*.mp4
        rel = prefix + pattern
        probe = rel.replace("**/", "").replace("*", "qa-probe").replace("?", "q")
        return "/" + escape(prefix) + pattern, probe, rel.rstrip("/")
    probe = prefix + pattern.replace("*", "qa-probe").replace("?", "q")
    return pattern, probe, pattern


def inspect(root, patterns):
    """State of the patterns with respect to git. Exits with 2 on errors."""
    if not shutil.which("git"):
        fail("git не найден")
    root = Path(root).expanduser()
    if not root.is_dir():
        fail(f"нет папки {root}")
    root = root.resolve()
    code, top, _ = git(root, "rev-parse", "--show-toplevel")
    state = {"output_root": str(root), "in_repo": code == 0, "repo": top if code == 0 else None, "prefix": None,
             "patterns": [], "path": None, "pattern": None, "ignored": False, "tracked_files": 0, "decision": None}
    marker = root / RUNS / DECISION
    if marker.is_file():
        state["decision"] = (marker.read_text(encoding="utf-8").split() or [""])[0] or None
    if code != 0:
        return state
    _, prefix, _ = git(root, "rev-parse", "--show-prefix")  # "" at the top, "sub/dir/" below
    state["prefix"] = prefix
    for pat in patterns:
        line, probe, spec = describe(prefix, pat)
        # --no-index: judge by ignore rules only; a folder with tracked files is otherwise never "ignored"
        ignored = git(top, "check-ignore", "-q", "--no-index", "--", probe)[0] == 0
        _, tracked, _ = git(top, "ls-files", "--", spec)
        files = [x for x in tracked.splitlines() if x]
        state["patterns"].append({"pattern": pat, "line": line, "probe": probe, "pathspec": spec,
                                  "ignored": ignored, "tracked_files": len(files), "tracked_sample": files[:5]})
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


def report(state, as_json, extra=""):
    if as_json:
        out = dict(state)
        if extra:
            out["message"] = extra
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    if not state["in_repo"]:
        print(f"{state['output_root']}: не в git-репозитории — ничего делать не нужно")
        return
    print(f"репозиторий: {state['repo']} (OUTPUT_ROOT: {state['prefix'] or '.'})")
    for p in state["patterns"]:
        mark = "игнорируется" if p["ignored"] else (
            "не игнорируется, пользователь решил коммитить" if state["decision"] == "keep" else "НЕ игнорируется")
        print(f"  {p['pattern']:<16} → строка {p['line']:<24} {mark}")
        if p["tracked_files"]:
            print(f"    уже в индексе git файлов: {p['tracked_files']} — .gitignore их не уберёт; команда "
                  f"(выполняет пользователь): git -C \"{state['repo']}\" rm -r --cached -- \"{p['pathspec']}\"")
    if not state["ignored"] and state["decision"] != "keep":
        print("  → спросить пользователя")
    if extra:
        print(extra)


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
    if a.mode == "gitignore":
        target = top / ".gitignore"
    else:
        _, gp, _ = git(top, "rev-parse", "--git-path", "info/exclude")
        target = Path(gp) if Path(gp).is_absolute() else top / gp
    added = append_lines(target, todo, a.label)
    st = inspect(a.dir, patterns)
    st["file"], st["added"] = str(target), added
    report(st, a.json, (f"добавлено в {target}: {', '.join(added)}" if added else f"строки уже были: {target}"))
    if not st["ignored"]:
        sys.stderr.write("gitignore_helper: строки есть, но не всё игнорируется — проверьте правила с «!» "
                         "(git check-ignore -v)\n")
        sys.exit(1)
    sys.exit(0)


def main(default_patterns=None, label="qa-runs", argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "apply"):
        p = sub.add_parser(name)
        p.add_argument("dir", help="OUTPUT_ROOT — папка, в которой лежит qa-runs/")
        p.add_argument("--pattern", action="append", default=None,
                       help=f"шаблон (можно несколько); по умолчанию: {' '.join(default_patterns or DEFAULT_PATTERNS)}")
        p.add_argument("--label", default=label, help="подпись в комментарии над строками")
        p.add_argument("--json", action="store_true")
        if name == "apply":
            p.add_argument("--mode", required=True, choices=["gitignore", "exclude", "keep"])
    a = ap.parse_args(argv)
    patterns = [norm_pattern(p) for p in (a.pattern or default_patterns or DEFAULT_PATTERNS)]
    patterns = list(dict.fromkeys(patterns))
    cmd_check(a, patterns) if a.cmd == "check" else cmd_apply(a, patterns)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
