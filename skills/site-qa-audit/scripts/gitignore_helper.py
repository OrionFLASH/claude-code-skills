#!/usr/bin/env python3
"""Keep <OUTPUT_ROOT>/qa-runs/ out of git (references/intake.md -> «В конце прогона: qa-runs/ и git»).

  gitignore_helper.py check <OUTPUT_ROOT> [--json]
      Is <OUTPUT_ROOT> inside a git work tree, and is <OUTPUT_ROOT>/qa-runs/ ignored?
      Exit: 0 nothing to ask (not in a repo, already ignored, or the user chose to keep it in git),
            1 ask the user (inside a repo and not ignored), 2 error (no git, no such folder).
  gitignore_helper.py apply <OUTPUT_ROOT> --mode gitignore|exclude|keep [--json]
      gitignore — append "/<prefix>qa-runs/" to .gitignore in the repository root;
      exclude   — the same line in .git/info/exclude (local only, the repository is not changed);
      keep      — remember "commit qa-runs" in qa-runs/.gitignore-decision, so check stops asking.
      Idempotent: an existing line is not added twice. Exit: 0 done (ignored now, or keep recorded),
      1 the line was written but qa-runs/ is still not ignored (a "!" rule overrides it), 2 error.
Only runs after an explicit answer of the user; never touches files already tracked by git
(prints the `git rm -r --cached` command instead).
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
COMMENT = "# site-qa-audit: local QA run results"


def git(cwd, *args):
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def escape(path):
    """gitignore pattern for a literal path: escape glob characters."""
    return "".join("\\" + ch if ch in "*?[\\" else ch for ch in path)


def inspect(root):
    """State of <root>/qa-runs/ with respect to git. Raises SystemExit(2) on errors."""
    if not shutil.which("git"):
        fail("git не найден")
    root = Path(root).expanduser()
    if not root.is_dir():
        fail(f"нет папки {root}")
    root = root.resolve()
    code, top, _ = git(root, "rev-parse", "--show-toplevel")
    state = {"output_root": str(root), "in_repo": code == 0, "repo": top if code == 0 else None,
             "path": None, "pattern": None, "ignored": False, "tracked_files": 0, "decision": None}
    if code != 0:
        return state
    _, prefix, _ = git(root, "rev-parse", "--show-prefix")  # "" at the top, "sub/dir/" below
    rel = f"{prefix}{RUNS}/"
    state["path"] = rel
    state["pattern"] = "/" + escape(rel)
    # --no-index: judge by ignore rules only; a folder with tracked files is otherwise never "ignored"
    state["ignored"] = git(top, "check-ignore", "-q", "--no-index", "--", rel)[0] == 0
    _, tracked, _ = git(top, "ls-files", "--", rel)
    state["tracked_files"] = len([x for x in tracked.splitlines() if x])
    marker = root / RUNS / DECISION
    if marker.is_file():
        state["decision"] = (marker.read_text(encoding="utf-8").split() or [""])[0] or None
    return state


def fail(msg):
    sys.stderr.write(f"gitignore_helper: {msg}\n")
    sys.exit(2)


def append_line(path, line):
    """Append line (with the comment) unless it is already there. Returns True if the file changed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if line in (x.strip() for x in text.splitlines()):
        return False
    if text and not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text + f"{COMMENT}\n{line}\n")
    return True


def report(state, as_json, extra=""):
    if as_json:
        print(json.dumps(state, ensure_ascii=False, indent=1))
        return
    if not state["in_repo"]:
        print(f"{state['output_root']}: не в git-репозитории — ничего делать не нужно")
        return
    where = f"{state['repo']} → {state['path']}"
    if state["ignored"]:
        print(f"{where}: игнорируется git")
    elif state["decision"] == "keep":
        print(f"{where}: не игнорируется, пользователь решил коммитить ({DECISION})")
    else:
        print(f"{where}: НЕ игнорируется — спросить пользователя")
    if state["tracked_files"]:
        print(f"  уже в индексе git файлов: {state['tracked_files']} — .gitignore их не уберёт; "
              f"команда (выполняет пользователь): git -C \"{state['repo']}\" rm -r --cached \"{state['path']}\"")
    if extra:
        print(extra)


def cmd_check(a):
    st = inspect(a.dir)
    report(st, a.json)
    need = st["in_repo"] and not st["ignored"] and st["decision"] != "keep"
    sys.exit(1 if need else 0)


def cmd_apply(a):
    st = inspect(a.dir)
    if not st["in_repo"]:
        fail(f"{st['output_root']} не в git-репозитории — нечего добавлять")
    root, top = Path(st["output_root"]), Path(st["repo"])
    if a.mode == "keep":
        marker = root / RUNS / DECISION
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"keep {datetime.date.today().isoformat()}\n", encoding="utf-8")
        st["decision"] = "keep"
        report(st, a.json, f"записано: {marker}")
        sys.exit(0)
    if st["ignored"]:
        report(st, a.json, "уже игнорируется — файлы не менялись")
        sys.exit(0)
    if a.mode == "gitignore":
        target = top / ".gitignore"
    else:
        _, gp, _ = git(top, "rev-parse", "--git-path", "info/exclude")
        target = Path(gp) if Path(gp).is_absolute() else top / gp
    changed = append_line(target, st["pattern"])
    st = inspect(a.dir)
    st["file"] = str(target)
    st["changed"] = changed
    report(st, a.json, f"{'добавлено' if changed else 'строка уже была'}: {st['pattern']} → {target}")
    if not st["ignored"]:
        sys.stderr.write("gitignore_helper: строка есть, но qa-runs/ всё ещё не игнорируется — "
                         "проверьте правила с «!» (git check-ignore -v)\n")
        sys.exit(1)
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("dir", help="OUTPUT_ROOT — папка, в которой лежит qa-runs/")
    c.add_argument("--json", action="store_true")
    p = sub.add_parser("apply")
    p.add_argument("dir", help="OUTPUT_ROOT — папка, в которой лежит qa-runs/")
    p.add_argument("--mode", required=True, choices=["gitignore", "exclude", "keep"])
    p.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cmd_check(a) if a.cmd == "check" else cmd_apply(a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
