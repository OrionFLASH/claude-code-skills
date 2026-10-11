"""Ссылки, выгрузки, скан, перенос, фазы, пути (эпик E-LINKS-DATA, pytest, без внешней сети).

check_links (повтор GET после 404 на HEAD, «не проверено» при таймауте, проход браузером, раздельные файлы — локальный
HTTP-сервер на 127.0.0.1), issues_export (owner/repo, органика, запасной путь — подменённый gh), repo_scan (исключения,
--strict-limit), relocate_run (маски, формы пути, --scan-leftovers), init_run (фазы по артефактам, относительные пути),
check_gitignore (--fix → node_modules/), check_paths (снимок волны и «Выдача» брифа), build_appendix (заготовки).
Запуск: python3 -m pytest skills/product-strategy/tests/test_links_data.py -q
"""
import csv
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
sys.path.insert(0, str(SCRIPTS))
import check_links  # noqa: E402
import check_paths  # noqa: E402
import issues_export  # noqa: E402


def run(script, *args, env=None, cwd=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    e.update(env or {})
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True,
                          env=e, timeout=180, cwd=cwd)


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write(p, text):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(text, encoding="utf-8")


def git(repo, *args):
    e = dict(os.environ, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="T", GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args], cwd=repo, env=e,
                          check=True, capture_output=True, text=True).stdout


needs_git = pytest.mark.skipif(not shutil.which("git"), reason="нет git")


# ---------------------------------------------------------------- локальный HTTP-сервер

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self):
        p = self.path
        if p.startswith("/ok"):
            code = 200
        elif p.startswith("/headonly404"):
            code = 404 if self.command == "HEAD" else 200
        elif p.startswith("/dead"):
            code = 404
        elif p.startswith("/browser"):
            code = 200 if self.headers.get("Sec-Fetch-Mode") else 404      # Chromium шлёт Sec-Fetch-*, urllib — нет
        elif p.startswith("/slow"):
            time.sleep(1.5)
            code = 200
        else:
            code = 500
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(b"<title>page</title>ok")
            except OSError:
                pass

    do_HEAD = do_GET = _reply


@pytest.fixture(scope="module")
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


def links_out(tmp_path, base, paths):
    out = tmp_path / "out"
    write(out / "data" / "sources.json", json.dumps([{"id": "S%03d" % i, "url": base + p, "title": "t%d" % i, "date_checked": None,
                                                      "status": None, "note": ""} for i, p in enumerate(paths, 1)]))
    return out


def rows_of(path):
    return {r["url"]: r for r in csv.DictReader(open(path, encoding="utf-8"))}


# ---------------------------------------------------------------- check_links

def test_head_404_retried_with_get_and_timeout_not_dead(server, tmp_path):
    out = links_out(tmp_path, server, ["/ok", "/headonly404", "/dead", "/slow1", "/slow2", "/slow3"])
    r = run("check_links.py", out, "--per-host-delay", "0", "--timeout", "0.5", "--backoff", "0.05", "--workers", "1", "--browser", "off")
    assert r.returncode == 0, r.stderr
    rows = rows_of(out / "data" / "links-check.net.csv")
    assert rows[server + "/ok"]["verdict"] == "ok"
    assert rows[server + "/headonly404"]["verdict"] == "ok"                     # HEAD 404, GET 200 → живая
    assert rows[server + "/dead"]["verdict"] == "мёртвая"                       # и GET 404 → мёртвая
    slow = [rows[server + "/slow%d" % i]["verdict"] for i in (1, 2, 3)]
    assert all(v.startswith("не проверено") for v in slow), slow                # таймаут — не «мёртвая»
    assert "попыток: 2" in slow[0] and "хост не отвечает" in slow[2]            # повтор и отказ ждать хост дальше
    assert (out / "data" / "links-check.csv").read_text(encoding="utf-8") == (out / "data" / "links-check.net.csv").read_text(encoding="utf-8")
    src = {s["url"]: s for s in jload(out / "data" / "sources.json")}
    assert src[server + "/dead"]["status"] == 404 and src[server + "/slow1"]["date_checked"] is None   # «не проверено» — дату не ставим
    assert "не проверено 3" in r.stdout


def test_offline_does_not_overwrite_network_result(server, tmp_path):
    out = links_out(tmp_path, server, ["/ok", "/dead"])
    assert run("check_links.py", out, "--per-host-delay", "0", "--browser", "off").returncode == 0
    net = (out / "data" / "links-check.csv").read_text(encoding="utf-8")
    r = run("check_links.py", out, "--offline")
    assert r.returncode == 0, r.stderr
    assert (out / "data" / "links-check.csv").read_text(encoding="utf-8") == net                    # сетевой результат цел
    assert all(v["verdict"].startswith("не проверялось") for v in rows_of(out / "data" / "links-check.offline.csv").values())
    assert "не тронут" in r.stdout


def test_offline_keeps_legacy_network_csv(tmp_path):
    out = tmp_path / "o"
    write(out / "data" / "sources.json", json.dumps([{"id": "S001", "url": "https://docs.python.org/3/", "title": "Python"}]))
    write(out / "data" / "links-check.csv", "url,status,verdict,final_url,checked,origins,files\nhttps://docs.python.org/3/,200,ok,,2026-10-01,sources:S001,\n")
    assert run("check_links.py", out, "--offline").returncode == 0
    assert "2026-10-01" in (out / "data" / "links-check.net.csv").read_text(encoding="utf-8")         # старый сетевой файл сохранён
    assert "2026-10-01" in (out / "data" / "links-check.csv").read_text(encoding="utf-8")


def test_offline_without_network_file_writes_main_csv(tmp_path):
    out = tmp_path / "o"
    write(out / "data" / "sources.json", json.dumps([{"id": "S001", "url": "https://docs.python.org/3/", "title": "Python"}]))
    assert run("check_links.py", out, "--offline").returncode == 0
    assert set(next(csv.reader(open(out / "data" / "links-check.csv", encoding="utf-8")))) == set(check_links.FIELDS)
    assert (out / "data" / "links-check.offline.csv").exists() and not (out / "data" / "links-check.net.csv").exists()


def test_browser_verdicts_and_refusal_hosts():
    results = {"https://support.google.com/a": (404, "мёртвая", "https://support.google.com/a"),
               "https://x.org/gone": (404, "мёртвая", "https://x.org/gone"),
               "https://x.org/block": (403, check_links.ANTIBOT, "https://x.org/block"),
               "https://x.org/ok": (200, "ok", "https://x.org/ok")}
    cands = check_links.browser_candidates(results, check_links.CLIENT_REFUSAL_HOSTS)
    assert cands == ["https://support.google.com/a", "https://x.org/block", "https://x.org/gone"]
    notes = check_links.apply_browser(dict(results), {})
    assert notes == {}
    res = dict(results)
    check_links.apply_browser(res, {"https://support.google.com/a": {"url": "", "status": 200, "title": "Справка"},
                                    "https://x.org/gone": {"status": 200, "title": "404 Not Found"},
                                    "https://x.org/block": {"status": 403, "title": ""}})
    assert res["https://support.google.com/a"][1] == check_links.CLIENT_REFUSED
    assert res["https://x.org/gone"][1] == check_links.DEAD_BROWSER                   # «мягкий 404» по заголовку
    assert res["https://x.org/block"][1] == check_links.ANTIBOT
    res2 = dict(results)
    assert check_links.unverified_refusals(res2, check_links.CLIENT_REFUSAL_HOSTS, "нет Playwright") == 1
    assert res2["https://support.google.com/a"][1].startswith("не проверено") and res2["https://x.org/gone"][1] == "мёртвая"


def test_probe_retries_transient_then_not_checked(monkeypatch):
    calls = []

    def fake_once(u, timeout, ctx):
        calls.append(u)
        return (None, "таймаут", u), True
    monkeypatch.setattr(check_links, "probe_once", fake_once)
    st, verdict, _ = check_links.probe("https://consultant.ru/x", 1, None, retries=2, backoff=0, sleep=lambda s: None)
    assert st is None and verdict == "не проверено: таймаут (попыток: 3)" and len(calls) == 3


def _playwright():
    try:
        node, mod = check_links.find_playwright(Path("."), os.environ.get("PS_NODE_DIR"))
    except Exception:  # noqa: BLE001
        return None
    return (node, mod) if node else None


@pytest.mark.skipif(_playwright() is None, reason="нет Node + playwright (PS_NODE_DIR)")
def test_browser_pass_real_chromium(server, tmp_path):
    out = links_out(tmp_path, server, ["/browser", "/dead"])
    r = run("check_links.py", out, "--per-host-delay", "0", "--browser", "on", "--timeout", "5")
    if "проход браузером не удался" in r.stderr:
        pytest.skip("Chromium не запустился: " + r.stderr.strip()[-200:])
    assert r.returncode == 0, r.stderr
    rows = rows_of(out / "data" / "links-check.net.csv")
    assert rows[server + "/browser"]["verdict"] == check_links.CLIENT_REFUSED and rows[server + "/browser"]["browser"] == "браузер: 200"
    assert rows[server + "/dead"]["verdict"] == check_links.DEAD_BROWSER
    src = {s["url"]: s for s in jload(out / "data" / "sources.json")}
    assert src[server + "/browser"]["status"] == 200 and "отказ клиента" in src[server + "/browser"]["note"]


# ---------------------------------------------------------------- issues_export

FAKE_GH = r"""#!/bin/sh
case "$*" in
  *"repo view"*) echo "acme/widget";;
  *"issue list"*reactionGroups*) echo "unknown field reactionGroups" >&2; exit 1;;
  *"issue list"*) cat <<'J'
[{"number":1,"title":"App crashes","body":"","state":"OPEN","labels":[],"createdAt":"2026-01-01","author":{"login":"QA1"},"url":"u1"},
 {"number":2,"title":"Add dark theme","body":"","state":"OPEN","labels":[],"createdAt":"2026-01-02","author":{"login":"qa1"},"url":"u2"},
 {"number":3,"title":"Добавить экспорт","body":"","state":"CLOSED","labels":[],"createdAt":"2026-01-03","author":{"login":"stranger"},"url":"u3"},
 {"number":4,"title":"bump deps","body":"","state":"CLOSED","labels":[],"createdAt":"2026-01-03","author":{"login":"app/dependabot","is_bot":true},"url":"u4"},
 {"number":5,"title":"note to self","body":"","state":"OPEN","labels":[],"createdAt":"2026-01-03","author":{"login":"acme"},"url":"u5"},
 {"number":6,"title":"Crash on login","body":"","state":"OPEN","labels":[],"createdAt":"2026-01-04","author":{"login":"qa2"},"url":"u6"}]
J
;;
  *"pr list"*) echo "[]";;
  *) exit 1;;
esac
"""


@pytest.fixture()
def fake_gh(tmp_path):
    p = tmp_path / "bin" / "gh"
    write(p, FAKE_GH)
    p.chmod(0o755)
    return p


def test_issues_export_slug_argument_and_organic(fake_gh, tmp_path):
    out = tmp_path / "o"
    write(out / "build" / "run-config.json", json.dumps({"sources": {"internal_authors": ["qa2"]}}))
    r = run("issues_export.py", "acme/widget", out, "--gh", fake_gh, "--internal-authors", "@qa1")
    assert r.returncode == 0, r.stderr
    d = jload(out / "data" / "issues.json")
    c = d["counts"]
    assert d["repo"] == "acme/widget" and d["slug_source"] == "аргумент owner/repo"
    assert c["issues"] == 6 and c["internal"] == 3 and c["bots"] == 1 and c["by_owner"] == 1 and c["organic"] == 1
    assert c["organic_share"] == round(1 / 6, 3)
    assert any("минимальному набору" in n for n in d["notes"])                   # запасной путь gh issue list
    roles = {i["number"]: i["author_role"] for i in d["issues"]}
    assert roles == {1: "internal", 2: "internal", 3: "external", 4: "bot", 5: "owner", 6: "internal"}
    assert all("_login" not in i for i in d["issues"]) and "qa1" not in json.dumps(d).lower()        # логины не сохраняются
    md = (out / "research" / "issues-demand.md").read_text(encoding="utf-8")
    assert "Органика" in md and "органики меньше 30 %" in md
    s = jload(out / "data" / "issues-summary.json")
    assert s["organic"] == 1 and s["detailed"] is True
    assert "author_role" in (out / "data" / "issues-demand.csv").read_text(encoding="utf-8").splitlines()[0]


def test_issues_export_url_and_repo_path(fake_gh, tmp_path):
    assert issues_export.slug_from_text("https://github.com/acme/widget.git") == "acme/widget"
    assert issues_export.slug_from_text("git" + "@" + "github.com:acme/widget") == "acme/widget"      # SSH-адрес remote
    assert issues_export.slug_from_text("acme/widget") == "acme/widget"
    assert issues_export.slug_from_text("./src") is None and issues_export.slug_from_text("just-a-dir") is None
    repo = tmp_path / "repo"
    repo.mkdir()
    out = tmp_path / "o"
    # путь без git remote → slug через `gh repo view` (подменённый gh)
    path, slug, how = issues_export.resolve_target(str(repo), None, out, str(fake_gh))
    assert path == repo.resolve() and slug == "acme/widget" and how == "gh repo view"
    # явный --repo-path + owner/repo первым аргументом: аргумент главнее
    path, slug, how = issues_export.resolve_target("other/thing", str(repo), out, None)
    assert path == repo.resolve() and slug == "other/thing"
    # нет ни папки, ни slug → причина; внешний трекер из run-config — запасной
    assert issues_export.resolve_target("no-such-dir-xyz", None, out, None)[1] is None
    write(out / "build" / "run-config.json", json.dumps({"sources": {"external": {"tracker": "https://github.com/client/qa-tracker"}}}))
    assert issues_export.resolve_target("no-such-dir-xyz", None, out, None)[1:] == ("client/qa-tracker", "run-config sources.external.tracker")


def test_issues_export_dominant_external_author_warning():
    raw = [{"number": i, "title": "Bug %d" % i, "state": "OPEN", "author": {"login": "client"}, "url": "u"} for i in range(9)] + \
          [{"number": 99, "title": "Idea", "state": "OPEN", "author": {"login": "someone"}, "url": "u"}]
    issues = [issues_export.normalize_issue(r, "acme") for r in raw]
    org = issues_export.organic_stats(issues)
    assert org["top_author_share"] == 0.9 and org["top_author_role"] == "external"
    for i in issues:
        i.pop("_login", None)
    d = {"date": "2026-10-11", "repo": "acme/w", "limit": 500, "skipped": None, "clusters": [], "prs": [], "suspicious": [], "issues": [],
         "counts": {"issues": 10, "open": 10, "closed": 0, "prs": 0, "prs_merged": 0, "by_type": {}, "by_owner": 0, "external_authors": 2, **org}}
    md = issues_export.render_md(d)
    assert "один автор завёл 90 %" in md and "sources.internal_authors" in md


# ---------------------------------------------------------------- repo_scan

@needs_git
def test_repo_scan_skips_worktrees_cxx_and_strict_limit(tmp_path):
    repo = tmp_path / "r"
    for rel in ("src/app.py", "src/util.py", "README.md", ".worktrees/feat/src/app.py", "android/app/.cxx/llama/ggml.cpp",
                "third_party/lib/x.c", "external/sdk/y.c", "android/app/.externalNativeBuild/z.cpp"):
        write(repo / rel, "print('x')\n" if rel.endswith(".py") else "int x;\n")
    git(repo, "init", "-q")
    git(repo, "add", "-A", "-f")
    git(repo, "commit", "-q", "-m", "init")
    out = tmp_path / "o"
    r = run("repo_scan.py", repo, out)
    assert r.returncode == 0, r.stderr
    d = jload(out / "data" / "repo-scan.json")
    langs = json.dumps(d["stack"]["languages"])
    assert "C++" not in langs and '"C"' not in langs, langs
    assert d["scan"]["files_seen"] == 3
    r = run("repo_scan.py", repo, tmp_path / "o2", "--max-files", "1")
    assert r.returncode == 0 and "СКАН НЕПОЛНЫЙ" in r.stdout                    # без флага — код 0, но строка в выводе
    r = run("repo_scan.py", repo, tmp_path / "o3", "--max-files", "1", "--strict-limit")
    assert r.returncode == 3 and jload(tmp_path / "o3" / "data" / "repo-scan.json")["scan"]["truncated"] is True


# ---------------------------------------------------------------- relocate_run

def test_relocate_masks_forms_and_leftovers(tmp_path):
    home = Path.home()
    old = tmp_path / "old" / "run"
    write(old / "build" / "run-config.json", json.dumps({"output": {"dir": str(old), "inside_repo": False, "git_branch": ""}}))
    write(old / "build" / "agent.log", "wrote %s/data/x.json\n" % old)                                # .log теперь в масках
    write(old / "build" / "env.json", json.dumps({"node": str(home / ".nvm" / "bin" / "node")}))     # другой абсолютный путь
    write(old / "build" / "STATUS.md", "# S\n- запись: %s/research\n" % str(old).replace(str(home), "~", 1)
          if str(old).startswith(str(home)) else "# S\n- запись: %s/research\n" % old)
    new = tmp_path / "new" / "run"
    r = run("relocate_run.py", old, new, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    rep = json.loads(r.stdout)
    assert rep["remaining_total"] == 0
    assert str(new.resolve()) in (new / "build" / "agent.log").read_text(encoding="utf-8")
    lo = rep["leftovers"]
    assert any(h["file"] == "build/env.json" for h in lo["files"]), lo                      # остаток другой формы найден
    assert any(h["file"] == "build/run-config.json" for h in lo["contract"])
    st = (new / "build" / "STATUS.md").read_text(encoding="utf-8")
    assert "<SKILL_DIR>/scripts/build_all.py" in st and str(home) + "/" not in st.split("## Перенос")[1]
    saved = (new / "build" / "relocate-report.json").read_text(encoding="utf-8")
    assert str(SCRIPTS) not in saved and str(home) + "/" not in saved
    # отдельный режим: только поиск и замена домашней папки на ~
    r = run("relocate_run.py", new, "--scan-leftovers", "--fix-leftovers", "--json")
    assert r.returncode == 0, r.stderr
    env_text = (new / "build" / "env.json").read_text(encoding="utf-8")
    assert str(home) not in env_text and "~/.nvm" in env_text
    assert str(new.resolve()) in (new / "build" / "run-config.json").read_text(encoding="utf-8")     # run-config не трогаем
    assert run("relocate_run.py", tmp_path / "missing", "--scan-leftovers").returncode == 2


def test_relocate_path_forms():
    import relocate_run
    forms = relocate_run.path_forms("/var/folders/ab/run", Path("/private/var/folders/ab/run"))
    assert {"/var/folders/ab/run", "/private/var/folders/ab/run"} <= forms
    home = str(Path.home())
    assert "~/x/run" in relocate_run.path_forms(home + "/x/run", Path(home + "/x/run"))
    assert relocate_run.path_forms("rel/run", Path("/abs/rel/run")) == {"/abs/rel/run"}             # относительная форма не заменяется


@needs_git
def test_relocate_detects_repo_and_sets_branch(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    old = tmp_path / "sib" / "run"
    write(old / "build" / "run-config.json", json.dumps({"output": {"dir": str(old), "inside_repo": False, "git_branch": ""}}))
    write(old / "build" / "briefs" / "a.md", "Выдача: %s/data/x.json\n" % old)
    new = repo / "strategy" / "2026-10-11"
    r = run("relocate_run.py", old, new, "--json")                       # без --repo: репозиторий найден по git
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(r.stdout)["replacement"] == "strategy/2026-10-11"
    cfg = jload(new / "build" / "run-config.json")
    assert cfg["output"]["inside_repo"] is True and cfg["output"]["git_branch"].startswith("docs/strategy-")
    assert cfg["repo"]["path"] == str(repo.resolve())
    assert "strategy/2026-10-11/data/x.json" in (new / "build" / "briefs" / "a.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------- init_run

def test_init_run_artifacts_sync_and_next_phase(tmp_path):
    out = tmp_path / "o"
    assert run("init_run.py", out).returncode == 0
    assert "node_modules/" in (out / ".gitignore").read_text(encoding="utf-8")
    # фазы 4 и 5 выполнены, но не отмечены → --show отмечает их и называет следующую по факту
    write(out / "research" / "market.md", "# Рынок\n")
    write(out / "data" / "competitors.json", json.dumps([{"slug": "a"}]))
    write(out / "data" / "sources-competitors.json", json.dumps([{"id": "SC001"}]))
    write(out / "data" / "proposals.json", json.dumps([{"id": "P001"}]))
    r = run("init_run.py", out, "--show")
    assert r.returncode == 0, r.stderr
    assert "по артефактам отмечены фазы: 4, 5" in r.stdout
    assert "Следующая фаза: 5.5." in r.stdout and "Пропущены раньше" in r.stdout and "3 (build/seeds.md)" in r.stdout
    st = (out / "build" / "STATUS.md").read_text(encoding="utf-8")
    assert "- [x] 4. " in st and "- [x] 5. " in st and "- [ ] 3. " in st
    # --done без артефактов: по умолчанию — предупреждение и пометка; со строгим режимом — отказ
    r = run("init_run.py", out, "--done", "6", "--require-artifacts")
    assert r.returncode == 2 and "data/scores.json" in r.stderr
    assert "- [ ] 6. " in (out / "build" / "STATUS.md").read_text(encoding="utf-8")
    r = run("init_run.py", out, "--done", "6", "--require-artifacts", "--force")
    assert r.returncode == 0 and "без артефактов" in r.stderr
    assert "фаза 6 отмечена с --force без артефактов" in (out / "build" / "STATUS.md").read_text(encoding="utf-8")
    # пустой JSON — не артефакт
    write(out / "data" / "scores.json", "[]")
    assert "data/scores.json" in run("init_run.py", out, "--show", "--no-sync").stdout


def test_init_run_strict_from_config_and_disabled_phase(tmp_path):
    out = tmp_path / "o"
    write(out / "build" / "run-config.json", json.dumps({"tools": {"strict_phases": True}, "phases": {"gap_audit": False},
                                                         "scope": {"repo_analysis": False}}))
    assert run("init_run.py", out).returncode == 0
    assert run("init_run.py", out, "--done", "1").returncode == 2                       # строгий режим из run-config
    write(out / "research" / "product-understanding.md", "# Продукт\n")
    assert run("init_run.py", out, "--done", "1").returncode == 0                       # repo-scan не нужен: repo_analysis=false
    r = run("init_run.py", out, "--show", "--no-sync")
    assert "5.5   выключена выбором" in r.stdout


def test_init_run_status_without_absolute_paths(tmp_path):
    out = tmp_path / "o"
    assert run("init_run.py", out).returncode == 0
    home = str(Path.home())
    assert run("init_run.py", out, "--status", "готово: %s/build/briefs/a.md и %s/dev/x" % (out.resolve(), home)).returncode == 0
    st = (out / "build" / "STATUS.md").read_text(encoding="utf-8")
    line = [ln for ln in st.splitlines() if "готово:" in ln][0]
    assert str(out.resolve()) not in line and home + "/" not in line
    assert "<OUT>/build/briefs/a.md" in line and "~/dev/x" in line


# ---------------------------------------------------------------- check_gitignore

@needs_git
def test_check_gitignore_fix_always_adds_node_modules(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    out = repo / "strategy" / "run"
    write(out / "data" / "x.json", "[]")
    write(out / ".gitignore", "*.tmp\n")
    r = run("check_gitignore.py", out, "--repo", repo, "--fix")
    assert r.returncode == 0, r.stdout + r.stderr
    gi = (out / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "node_modules/" in gi and "*.tmp" in gi


# ---------------------------------------------------------------- check_paths

BRIEF = """# Бриф
## Цель
Сделать макеты.

## Выдача (только эти пути)
- `{OUT}/mockups/concepts/<key>.html` для каждого ключа (+ ассеты в `{OUT}/mockups/concepts/assets/<key>/`).
- PNG и `data/mockups-check.<key>.json` создаёт `shoot_mockups.mjs`. Общие `data/mockups-index.json` и `data/mockups-check.json` — **не трогать**.
- `{OUT}/data/competitors-cards-{PART}.json` — список полей как в `data/competitors.json`.

## Правила
- `data/forbidden.json` здесь не выдача.
"""


def test_check_paths_brief_parsing():
    allow, deny = check_paths.brief_patterns(BRIEF, "strategy/2026-10-11")
    assert "mockups/concepts/*.html" in allow and "mockups/concepts/assets/*/*" in allow and "data/mockups-check.*.json" in allow
    assert "data/competitors-cards-*.json" in allow and "mockups/concepts/*.png" in allow
    assert "data/competitors.json" not in allow and "data/forbidden.json" not in allow and "shoot_mockups.mjs" not in " ".join(allow)
    assert deny == ["data/mockups-index.json", "data/mockups-check.json"]
    rendered = BRIEF.replace("{OUT}", "strategy/2026-10-11")
    assert check_paths.brief_patterns(rendered, "strategy/2026-10-11")[0][0] == "mockups/concepts/*.html"


def test_check_paths_wave_snapshot(tmp_path):
    out = tmp_path / "o"
    write(out / "build" / "briefs" / "mockups-1.md", BRIEF)
    write(out / "data" / "mockups-index.json", "[]")
    write(out / "data" / "proposals.json", "[]")
    assert run("check_paths.py", out, "--start", "8a").returncode == 0
    assert (out / "build" / "waves" / "8a.json").is_file()
    time.sleep(0.01)
    write(out / "mockups" / "concepts" / "M01-home.html", "<html></html>")
    write(out / "mockups" / "concepts" / "M01-home.png", "png")
    write(out / "data" / "mockups-check.M01-home.json", "{}")
    write(out / "build" / "STATUS.md", "# S\n")                                   # служебный файл оркестратора
    r = run("check_paths.py", out, "--wave", "8a", "--briefs", "build/briefs/mockups-1.md")
    assert r.returncode == 0, r.stdout
    write(out / "data" / "mockups-index.json", "[1]")                             # запрещённый общий файл
    write(out / "data" / "proposals.json", "[1]")                                 # чужой файл
    (out / "build" / "briefs" / "mockups-1.md").touch()
    r = run("check_paths.py", out, "--wave", "8a", "--briefs", "build/briefs/mockups-1.md", "--json")
    assert r.returncode == 1
    v = {x["file"]: x["why"] for x in json.loads(r.stdout)["violations"]}
    assert set(v) == {"data/mockups-index.json", "data/proposals.json"} and "не трогать" in v["data/mockups-index.json"]
    r = run("check_paths.py", out, "--wave", "8a", "--briefs", "build/briefs/mockups-1.md", "--allow", "data/proposals.json", "data/mockups-index.json")
    assert r.returncode == 0, r.stdout
    assert run("check_paths.py", out, "--wave", "nope", "--briefs", "build/briefs/mockups-1.md").returncode == 2


@needs_git
def test_check_paths_detects_changes_outside_out(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "src" / "app.py", "x = 1\n")
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "i")
    out = repo / "strategy" / "run"
    write(out / "build" / "briefs" / "b.md", BRIEF)
    assert run("check_paths.py", out, "--start", "w1").returncode == 0
    write(repo / "src" / "app.py", "x = 2\n")
    r = run("check_paths.py", out, "--wave", "w1", "--briefs", "build/briefs/b.md", "--json")
    assert r.returncode == 1
    rep = json.loads(r.stdout)
    assert rep["outside_repo"] == ["src/app.py"] and any(x["change"] == "вне <OUT>" for x in rep["violations"])


def test_check_paths_since(tmp_path):
    out = tmp_path / "o"
    write(out / "build" / "briefs" / "b.md", BRIEF)
    stamp = out / "build" / "stamp"
    write(stamp, "")
    old = time.time() - 100
    os.utime(out / "build" / "briefs" / "b.md", (old, old))
    os.utime(stamp, (old + 50, old + 50))
    write(out / "data" / "stray.txt", "x")
    r = run("check_paths.py", out, "--since", stamp, "--briefs", "build/briefs/b.md", "--json")
    assert r.returncode == 1 and [x["file"] for x in json.loads(r.stdout)["violations"]] == ["data/stray.txt"]


# ---------------------------------------------------------------- build_appendix

def test_build_appendix_documents(tmp_path):
    out = tmp_path / "o"
    write(out / "build" / "run-config.json", json.dumps({"created": "2026-10-11", "product": {"name": "Тест"}, "strategy": {"depth": "standard"},
                                                         "assumptions": ["Валюта — RUB", "Команда: 1 человек"]}))
    write(out / "data" / "fact-check.json", json.dumps([
        {"fact": "цена тарифа", "phase1_value": "нет", "agent_value": "199 ₽", "source": "G5", "resolved_value": None},
        {"claim": "число тестов", "was": "10", "now": "12", "status": "resolved"}]))
    write(out / "data" / "scores.json", json.dumps([{"id": "P002", "rank": 1, "dep_rank": 2, "title": "Б", "category": "product"},
                                                    {"id": "P001", "rank": 2, "dep_rank": 1, "title": "А", "category": "platform", "blocked_by": []}]))
    write(out / "research" / "strategy.md", "## 1. Резюме\nNorth Star — недельные активные. Оценка по RICE. Конверсия 3 % [ДОПУЩЕНИЕ].\n")
    write(out / "build" / "parts" / "strategy-06.md", "## 6. Привлечение\nCAC не считаем [допущение: бюджета нет].\n")
    write(out / "data" / "sources.json", json.dumps([{"id": "S001", "date_checked": "2026-10-01"}, {"id": "S002", "date_checked": "2026-10-05"}]))
    r = run("build_appendix.py", out, "--json")
    assert r.returncode == 0, r.stderr
    rep = json.loads(r.stdout)
    assert rep["open_facts"] == 1 and rep["assumptions"] == 2 and rep["markers"] == 2
    db = (out / "research" / "decision-brief.md").read_text(encoding="utf-8")
    assert "# Решения для владельца: Тест" in db and db.index("| 1 | P001 |") < db.index("| 2 | P002 |")
    assert "| цена тарифа | нет | 199 ₽ | G5 |" in db and "число тестов" not in db and "{" not in db.replace("{rank", "")
    q = (out / "research" / "questions-owner.md").read_text(encoding="utf-8")
    assert q.index("[факт] цена тарифа") < q.index("[допущение] Валюта") < q.index("[в тексте] research/strategy.md:2")
    g = (out / "research" / "glossary.md").read_text(encoding="utf-8")
    assert "| RICE |" in g and "| North Star |" in g and "| CAC |" in g and "| WSJF |" not in g and "## Словарь" not in g
    ap = (out / "build" / "appendix-17.md").read_text(encoding="utf-8")
    assert ap.startswith("## 17. Приложение") and "2 записей, проверены 2026-10-01…2026-10-05" in ap and "1. Валюта — RUB" in ap
    # повтор — детерминированно и без затирания ручной правки
    snap = {f: (out / f).read_text(encoding="utf-8") for f in ("research/decision-brief.md", "research/glossary.md")}
    assert run("build_appendix.py", out).returncode == 0
    assert {f: (out / f).read_text(encoding="utf-8") for f in snap} == snap
    write(out / "research" / "questions-owner.md", "# Мои вопросы\n1. Ручной вопрос?\n")
    assert run("build_appendix.py", out, "--only", "questions").returncode == 0
    assert "Ручной вопрос" in (out / "research" / "questions-owner.md").read_text(encoding="utf-8")
    assert (out / "research" / "questions-owner.generated.md").is_file()
    assert run("build_appendix.py", out, "--only", "nope").returncode == 2
    assert run("build_appendix.py", tmp_path / "missing").returncode == 2


def test_templates_have_placeholders():
    db = (TEMPLATES / "decision-brief.md").read_text(encoding="utf-8")
    for ph in ("{PRODUCT}", "{BETS}", "{FORKS}", "{ASSUMPTIONS}", "{OPEN_FACTS}"):
        assert ph in db
    g = (TEMPLATES / "glossary.md").read_text(encoding="utf-8")
    assert "{TERMS}" in g and "## Словарь" in g


@pytest.mark.parametrize("script", ["check_links.py", "issues_export.py", "repo_scan.py", "relocate_run.py", "init_run.py",
                                    "check_gitignore.py", "check_paths.py", "build_appendix.py", "dispatch.py"])
def test_help(script):
    r = run(script, "--help")
    assert r.returncode == 0 and "usage" in r.stdout.lower()
