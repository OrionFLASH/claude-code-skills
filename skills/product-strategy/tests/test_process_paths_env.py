# -*- coding: utf-8 -*-
"""WP-D 1.5.0: пути, git и среда — временные файлы агентов только в build/tmp/<бриф>/ и общие пути (FB-006, SM 6.3),
.gitignore без ложных провалов на .DS_Store и с точной формулировкой (SM 6.4), скриншоты «только локально» (FB-042),
.playwright-mcp и абсолютные пути (FB-017), состояние git и unborn main (FB-041, SM 6.5), запасной timeout для macOS (SM 6.4).
Запуск: python3 -m pytest tests/test_process_paths_env.py -q -p no:cacheprovider
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check_paths  # noqa: E402

needs_git = pytest.mark.skipif(not shutil.which("git"), reason="нет git")


def run(script, *args):
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True, env=e, timeout=120)


def write(p, text):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(text, encoding="utf-8")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True)


BRIEF = "# Бриф {name}\n## Цель\nСхемы.\n## Выдача\n- `{{OUT}}/build/parts/flows-{n}.json` — часть схем.\n- `{{OUT}}/charts/flows/*.svg` — рисунки.\n## Правила\n- …\n"


# ---------------------------------------------------------------- FB-006: временные файлы и общие пути
def test_tmp_dirs_per_brief_foreign_tmp_and_temp_files(tmp_path):
    out = tmp_path / "o"
    write(out / "build" / "briefs" / "flows-F1.md", BRIEF.format(name="F1", n=1))
    write(out / "build" / "briefs" / "flows-F2.md", BRIEF.format(name="F2", n=2))
    check_paths.start(out, "C7")
    write(out / "build" / "tmp" / "flows-F1" / "gen.py", "print(1)")                         # своя папка F1 — можно
    write(out / "build" / "parts" / "flows-1.json", "[]")
    write(out / "build" / "tmp" / "other-agent" / "x.json", "{}")                           # чужая/ничья временная папка
    write(out / "gen.py", "print(2)")                                                       # временный скрипт вне build/tmp
    rep = check_paths.check(out, ["build/briefs/flows-F1.md", "build/briefs/flows-F2.md"], wave="C7")
    why = {v["file"]: v["why"] for v in rep["violations"]}
    assert "build/tmp/flows-F1/gen.py" not in why and "build/parts/flows-1.json" not in why
    assert why["build/tmp/other-agent/x.json"].startswith("чужая временная папка")
    assert why["gen.py"] == "временный файл вне build/tmp/<агент>/"
    shared = rep["shared_outputs"]
    assert shared and shared[0]["pattern"] == "charts/flows/*.svg" and shared[0]["briefs"] == ["flows-F1.md", "flows-F2.md"]
    r = run("check_paths.py", out, "--wave", "C7", "--briefs", "build/briefs/flows-F1.md", "build/briefs/flows-F2.md")
    assert r.returncode == 1 and "общий путь charts/flows/*.svg у flows-F1.md и flows-F2.md" in r.stdout


# ---------------------------------------------------------------- SM 6.4, FB-042, FB-017: .gitignore
@needs_git
def test_gitignore_ds_store_is_not_a_loss_and_rule_is_per_rule(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    write(repo / ".gitignore", ".DS_Store\nbuild/\n")
    out = repo / "concept" / "x"
    write(out / "competitors" / ".DS_Store", "x")
    write(out / "data" / ".DS_Store", "x")
    write(out / "data" / "a.json", "[]")
    r = run("check_gitignore.py", out)
    assert r.returncode == 0 and "системные файлы (.DS_Store и т. п.) игнорируются как положено: 2" in r.stdout
    write(out / "build" / "run-config.json", "{}")
    r = run("check_gitignore.py", out)
    assert r.returncode == 1 and "правило .gitignore:2:build/ скрывает: build/run-config.json" in r.stdout
    assert ".DS_Store" not in r.stdout.split("ВНИМАНИЕ")[1].split("Исправить")[0]          # .DS_Store не в списке потерь
    r = run("check_gitignore.py", out, "--fix")
    gi = (out / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert r.returncode == 0 and "!build/" in gi and "build/tmp/" in gi and ".DS_Store" in gi


@needs_git
def test_gitignore_shots_local_and_playwright_mcp(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / ".playwright-mcp").mkdir()
    out = repo / "concept" / "x"
    write(out / "build" / "run-config.json", json.dumps({"project": {"repo_visibility": "public"}}))
    write(out / "competitors" / "shots" / "a.png", "png")
    r = run("check_gitignore.py", out)
    assert "ВОПРОС ВЛАДЕЛЬЦУ: видимость репозитория public" in r.stdout and "Посторонние служебные папки" in r.stdout
    r = run("check_gitignore.py", out, "--shots", "local", "--fix")
    assert r.returncode == 0 and "только локально" in r.stdout
    assert "competitors/shots/" in (out / ".gitignore").read_text(encoding="utf-8")
    assert ".playwright-mcp/" in (repo / ".gitignore").read_text(encoding="utf-8")
    ls = git(repo, "status", "--porcelain", "--untracked-files=all").stdout
    assert "shots/a.png" not in ls and ".playwright-mcp" not in ls                          # снимки и папка инструмента — не в коммит


def test_relocate_portable_config_and_tool_dirs(tmp_path):
    home = tmp_path / "home"
    out = home / "dev" / "proj" / "concept" / "x"
    write(out / "build" / "run-config.json", json.dumps({"output": {"dir": str(out)}, "repo": {"path": str(home / "dev" / "proj")}}))
    (out / ".playwright-mcp").mkdir(parents=True, exist_ok=True)
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    e["HOME"] = str(home)                                                                   # домашняя папка — во временной
    rr = lambda *a: subprocess.run([sys.executable, "-B", str(SCRIPTS / "relocate_run.py")] + [str(x) for x in a], capture_output=True,
                                   text=True, env=e, timeout=120)
    r = rr(out, "--scan-leftovers", "--portable-config")
    assert r.returncode == 0 and "без домашней папки" in r.stdout and "посторонние папки инструментов: .playwright-mcp" in r.stdout
    cfg = json.loads((out / "build" / "run-config.json").read_text(encoding="utf-8"))
    assert cfg["output"]["dir"] == "~/dev/proj/concept/x" and cfg["repo"]["path"] == "~/dev/proj" and cfg["output"]["dir_rel"] == "concept/x"
    lo = json.loads(rr(out, "--scan-leftovers", "--json").stdout)
    assert lo["files"] == [] and lo["contract"] == []                                        # 0 находок


# ---------------------------------------------------------------- FB-041, SM 6.5: состояние git
@needs_git
def test_git_state_no_repo_unborn_normal(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    r = run("check_env.py", "--git-state", "--repo", plain, "--json", "-")
    assert json.loads(r.stdout)["state"] == "no_repo" and "git init" in json.loads(r.stdout)["plan"]
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "remote", "add", "origin", "git@example.com:o/r.git")
    d = json.loads(run("check_env.py", "--git-state", "--repo", repo, "--json", "-").stdout)
    assert d["state"] == "unborn" and d["has_origin"] and "git push -u origin main" in d["plan"] and "git switch -c" in d["plan"]
    r = run("check_env.py", "--git-state", "--repo", repo)
    assert "git: пустой репозиторий (нет коммитов); origin есть" in r.stdout
    write(repo / "a.txt", "x")
    git(repo, "add", "a.txt")
    git(repo, "-c", "user.email=t@e.st", "-c", "user.name=t", "commit", "-q", "-m", "init")
    d = json.loads(run("check_env.py", "--git-state", "--repo", repo, "--json", "-").stdout)
    assert d["state"] == "normal" and d["commits"] == 1
    r = run("check_env.py", "--out", repo, "--json", tmp_path / "env.json", "--quiet")
    env = json.loads((tmp_path / "env.json").read_text(encoding="utf-8"))
    assert env["git"]["state"] == "normal" and any(x["name"] == "timeout" for x in env["rows"])


# ---------------------------------------------------------------- SM 6.4: timeout на macOS
def test_run_timeout_fallback():
    r = run("check_env.py", "--run-timeout", "1", "--", sys.executable, "-c", "import time; time.sleep(5)")
    assert r.returncode == 124 and "время вышло" in r.stderr
    r = run("check_env.py", "--run-timeout", "10", "--", sys.executable, "-c", "raise SystemExit(3)")
    assert r.returncode == 3
