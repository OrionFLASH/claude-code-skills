#!/usr/bin/env python3
"""Issue drafts from findings.json by templates/issue-detailed.md (references/repo-sync.md). Never publishes.

  render_draft.py detailed findings.json --id F-001 [--repo owner/repo] [--config run-config.yaml] [--out FILE]
  render_draft.py all findings.json --run-dir R [--repo owner/repo] [--config …] [--status NEW,REGRESSION]
                  [--min-severity low]   → R/drafts/<owner__repo|local>/NN-STATUS-fp.md (+ .body.md) and index.md
  render_draft.py summary --run-dir R [--repo owner/repo]   → drafts/<repo>/summary.md (summary.md without local paths)

Publication settings (flags override run-config repos[] entry chosen by --repo):
  --disclosure full|none   none: no «Создано android-qa-audit» footer, no sources/run id, no skill marker
  --no-links               no links to issues of other repositories
  --marker skill|neutral|none   skill: <!-- android-qa-audit:fp=… -->, neutral: <!-- qa-fp:… -->
  --attachments-base URL   screenshots/recordings as links under this URL (files committed by the agent);
                           without it they are referenced as local files of the run folder
Draft file: first line "TITLE: <title>", then the body; *.body.md — body only (for gh issue create --body-file).
index.md lists title, labels and the gh command that WOULD publish the draft (run only after the user's «да»).
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
sys.path.insert(0, str(HERE))
import miniyaml  # noqa: E402
from masking import mask  # noqa: E402

TPL = HERE.parent / "templates"
SKILL_MARKER = re.compile(r"<!--\s*android-qa-audit:fp=([0-9a-f]*)\s*-->\n?")
ISSUE_REF = re.compile(r"(?<![\w/])([\w.-]+/[\w.-]+)#(\d+)")
FREQ = {"always": "всегда", "sometimes": "иногда", "once": "один раз"}
SEV = ["critical", "high", "medium", "low", "info"]
TYPE_LABELS = {"bug": "bug", "crash": "bug", "anr": "bug", "a11y": "accessibility", "performance": "performance",
               "security": "security", "ux-issue": "ux", "visual": "ui", "content": "content", "compat": "compatibility",
               "proposal": "enhancement", "suggestion": "enhancement", "user-story": "enhancement"}


def norm_repo(r):
    return re.sub(r"^https?://github\.com/|\.git$|/$", "", r or "")


def repo_settings(config, repo):
    if not config or not repo or not Path(config).exists():
        return {}
    cfg = miniyaml.load_file(config) or {}
    for r in cfg.get("repos") or []:
        if isinstance(r, dict) and norm_repo(r.get("url") or r.get("repo")) == norm_repo(repo):
            return r
    return {}


class Opts:
    def __init__(self, a):
        rs = repo_settings(getattr(a, "config", None), getattr(a, "repo", None))
        self.repo = norm_repo(a.repo) if getattr(a, "repo", None) else None
        self.disclosure = getattr(a, "disclosure", None) or rs.get("disclosure") or "full"
        self.cross_links = not getattr(a, "no_links", False) and rs.get("cross_links", True) is not False
        self.marker = getattr(a, "marker", None) or rs.get("marker") or ("skill" if self.disclosure == "full" else "none")
        if self.disclosure == "none" and self.marker == "skill":
            self.marker = "neutral"
        self.severity_map = rs.get("severity_map") or {}
        self.labels_policy = rs.get("labels") or "existing"
        self.extra_labels = rs.get("extra_labels") or []
        self.base = getattr(a, "attachments_base", None) or rs.get("attachments_base")

    def finish(self, body):
        if self.marker == "neutral":
            body = SKILL_MARKER.sub(lambda m: f"<!-- qa-fp:{m.group(1)} -->\n", body)
        elif self.marker == "none":
            body = SKILL_MARKER.sub("", body)
        if self.disclosure == "none":
            body = re.sub(r"\n---\n_Создано android-qa-audit[^\n]*\n?", "\n", body)
        if not self.cross_links:
            body = ISSUE_REF.sub(lambda m: m.group(0) if self.repo and m.group(1) == self.repo else "", body)
        body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"
        if self.disclosure == "none":
            for w in ("android-qa-audit", "claude"):
                if w in body.lower():
                    sys.stderr.write(f"render_draft: ВНИМАНИЕ — в тексте осталось «{w}» (из данных находки)\n")
        return body


def strip_comments(text):
    return re.sub(r"<!--(?!\s*android-qa-audit:).*?-->\n?", "", text, flags=re.S)


def drop_empty(text):
    lines = [ln for ln in text.split("\n") if not re.match(r"^\|\s*\*\*[^|]+\*\*\s*\|\s*(`\s*`)?\s*\|$", ln)]
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith("## "):
            j = i + 1
            while j < len(lines) and not lines[j].startswith(("## ", "---")):
                j += 1
            body = "\n".join(lines[i + 1:j])
            meaningful = re.sub(r"<details>.*?</details>|[\s|:-]|^- [^:]+:\s*$", "", body, flags=re.S | re.M)
            if meaningful:
                out.extend(lines[i:j])
            i = j
        else:
            out.append(lines[i])
            i += 1
    text = "\n".join(out)
    text = re.sub(r"<details><summary>[^<]+</summary>\s*```(text|json)\s*```\s*</details>\n?", "", text)
    text = re.sub(r"^- [^:\n]+:\s*$\n?", "", text, flags=re.M)
    text = re.sub(r"([^\n])\n(#{2,} )", r"\1\n\n\2", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def fill(template, values):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(values.get(m.group(1), "") or ""), template)


def media_md(paths, opts, rel_prefix, video=False):
    """With --attachments-base: links to committed files; draft for a repository without it: plain text
    (local images would be broken on GitHub); local draft: relative Markdown links for preview."""
    out = []
    for p in paths or []:
        name = Path(p).name
        if opts.base:
            url = f"{opts.base.rstrip('/')}/{name}"
            out.append(f"[{name}]({url})" if video else f"![{Path(p).stem}]({url}?raw=true)")
        elif opts.repo or not rel_prefix:
            out.append(f"- {'видео' if video else 'скриншот'}: `{p}` (файл в папке прогона, приложу по запросу)")
        else:
            out.append(f"[{name}]({rel_prefix}{p})" if video else f"![{Path(p).stem}]({rel_prefix}{p})")
    return "\n".join(out)


def values(f, run, opts, rel_prefix=""):
    env = f.get("environment") or {}
    label = opts.severity_map.get(f.get("severity")) if opts.severity_map else None
    crash = f.get("crash") or {}
    rate = f.get("repro_rate") or ""
    freq = FREQ.get(f.get("frequency"), f.get("frequency") or "")
    settings = ", ".join(x for x in [
        f"язык {env['locale']}" if env.get("locale") else "", "тёмная тема" if env.get("dark_mode") else "",
        f"шрифт {env['font_scale']}" if env.get("font_scale") not in (None, 1, 1.0) else "",
        env.get("orientation") or "", f"сеть {env['network']}" if env.get("network") else "",
        f"батарея {env['battery']}" if env.get("battery") else ""] if x)
    device = ", ".join(x for x in [env.get("device_profile") or "", f"{env['ram_mb']} МБ ОЗУ" if env.get("ram_mb") else "",
                                   f"{env['cores']} ядра" if env.get("cores") else "", env.get("abi") or ""] if x)
    return {
        "title": f.get("title"), "direction": f.get("direction"), "check_id": f.get("check_id"), "type": f.get("type"),
        "severity": (label if opts.disclosure == "none" else f"{label} ({f.get('severity')})") if label else f.get("severity"),
        "severity_upper": label or (f.get("severity") or "").upper(),
        "status": f.get("status") or "NEW",
        "status_links": "".join(f" — {m.get('repo')}#{m.get('number')}" for m in f.get("matches") or []
                                if opts.cross_links or norm_repo(m.get("repo")) == opts.repo),
        "app": " ".join(x for x in [f.get("package") or run.get("app") or "", f.get("app_version") or run.get("app_version") or ""] if x),
        "screen": f.get("screen") or "", "element": f.get("element") or "",
        "repro_text": " · ".join(x for x in [rate, freq] if x),
        "sources": "" if opts.disclosure == "none" else ", ".join(f.get("sources") or []),
        "run_id": "" if opts.disclosure == "none" else run.get("id", ""),
        "depth": "" if opts.disclosure == "none" else run.get("depth", ""),
        "steps_numbered": "\n".join(f"{i}. {s}" for i, s in enumerate(f.get("steps") or [], 1)),
        "expected": f.get("expected"), "actual": f.get("actual"),
        "actual_one_line": (f.get("actual") or f.get("suggestion") or f.get("title") or "").split("\n")[0][:300],
        "android": (f"API {env['api']}" + (f" (Android {env['android_version']})" if env.get("android_version") else "")) if env.get("api") else "",
        "device": device, "screen_cfg": env.get("screen") or "", "settings": settings,
        "stand": {"own-emulator": "эмулятор", "foreign-emulator": "эмулятор пользователя (read-only)", "real": "реальное устройство"}.get(env.get("stand"), env.get("stand") or ""),
        "date": env.get("date") or (run.get("started_at") or "")[:10],
        "environment_list": ", ".join(f.get("environment_list") or []),
        "crash_md": (f"**{crash.get('type', '').upper()}** {crash.get('summary', '')}" + (f" (процесс `{crash['process']}`)" if crash.get("process") else "")) if crash else "",
        "screenshots_md": media_md(f.get("screenshots"), opts, rel_prefix),
        "recordings_md": media_md(f.get("recordings"), opts, rel_prefix, video=True),
        "logcat_excerpt": "\n".join((f.get("logcat_excerpt") or "").splitlines()[:40]),
        "metrics_json": json.dumps(f.get("metrics"), ensure_ascii=False, indent=2) if f.get("metrics") else "",
        "hypothesis": f.get("hypothesis"), "suggestion": f.get("suggestion"), "fingerprint": f.get("fingerprint", ""),
        "related_links": "\n".join(f"- {m.get('repo')}#{m.get('number')}" for m in f.get("matches") or []
                                   if opts.cross_links or norm_repo(m.get("repo")) == opts.repo),
    }


def render(f, run, opts, rel_prefix=""):
    v = values(f, run, opts, rel_prefix)
    body = drop_empty(fill(strip_comments((TPL / "issue-detailed.md").read_text(encoding="utf-8")), v))
    body = re.sub(r"^\|\s*\*\*Прогон\*\*\s*\|\s*\(\)\s*\|\n?", "", body, flags=re.M)
    return f"[{v['severity_upper']}] {v['title']}", mask(opts.finish(body))


def labels_for(f, opts):
    if opts.labels_policy == "none":
        return []
    labels = [TYPE_LABELS.get(f.get("type"), "bug")] + list(opts.extra_labels)
    if opts.severity_map.get(f.get("severity")) and opts.labels_policy in ("existing", "create"):
        labels.append(str(opts.severity_map[f["severity"]]))
    return list(dict.fromkeys(labels))


def load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data, (data["findings"] if isinstance(data, dict) else data)


def write(out, title, body):
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text((f"TITLE: {title}\n\n" if title else "") + body, encoding="utf-8")


def cmd_all(a, opts):
    data, findings = load(a.findings)
    run = data.get("run", {}) if isinstance(data, dict) else {}
    statuses = set(a.status.split(",")) if a.status else None
    limit = SEV.index(a.min_severity) if a.min_severity in SEV else len(SEV) - 1
    folder = Path(a.run_dir) / "drafts" / (opts.repo.replace("/", "__") if opts.repo else "local")
    rows = []
    n = 0
    for f in findings:
        st = f.get("status") or "NEW"
        if statuses and st not in statuses:
            continue
        if SEV.index(f.get("severity", "info")) > limit:
            continue
        if (f.get("evidence") or {}).get("sensitive"):
            rows.append(f"| — | {f['id']} | не черновик: чувствительная находка (evidence.sensitive) — решение пользователя | — | — |")
            continue
        n += 1
        title, body = render(f, run, opts, rel_prefix="../../")
        name = f"{n:02d}-{st}-{f.get('fingerprint') or f['id']}"
        write(folder / f"{name}.md", title, body)
        write(folder / f"{name}.body.md", None, body)
        labels = labels_for(f, opts)
        cmd = (f"gh issue create -R {opts.repo} --title \"{title.replace(chr(34), chr(39))}\" --body-file \"{folder / (name + '.body.md')}\""
               + "".join(f" --label \"{x}\"" for x in labels)) if opts.repo else "—"
        rows.append(f"| {n} | {f['id']} | {title} | {', '.join(labels) or '—'} | `{cmd}` |")
    index = [f"# Черновики issues — {opts.repo or 'без репозитория'}", "",
             "Ничего не опубликовано. Команды ниже выполняются только после явного «да» пользователя "
             "(сводная таблица build_report.py publish-table). Скриншоты gh не прикладывает — см. repo-sync.md.", "",
             "| № | Находка | Заголовок | Метки | Команда |", "|---|---|---|---|---|"] + (rows or ["| — | — | нет находок по фильтру | — | — |"])
    (folder).mkdir(parents=True, exist_ok=True)
    (folder / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"render_draft: черновиков {n} -> {folder}")


def cmd_summary(a, opts):
    run_dir = Path(a.run_dir)
    src = run_dir / "summary.md"
    if not src.exists():
        sys.exit("render_draft: нет summary.md — сначала build_report.py summary")
    text = src.read_text(encoding="utf-8")
    text = re.sub(r" · \*\*Папка прогона:\*\* `[^`]*`", "", text)
    text = re.sub(r"^\*\*Папка прогона:\*\*.*$\n?", "", text, flags=re.M)
    title = (re.search(r"^# (.+)$", text, re.M) or [None, "QA Android"])[1]
    body = re.sub(r"^# .+\n+", "", text, count=1)
    fj = run_dir / "findings.json"
    run_id = (json.loads(fj.read_text(encoding="utf-8")).get("run") or {}).get("id", "") if fj.exists() else ""
    if opts.marker == "skill" and run_id:
        body += f"\n<!-- android-qa-audit:run={run_id} -->\n"
    body = mask(opts.finish(body))
    folder = run_dir / "drafts" / (opts.repo.replace("/", "__") if opts.repo else "local")
    write(folder / "summary.md", title, body)
    write(folder / "summary.body.md", None, body)
    print(f"render_draft: итоговый черновик -> {folder / 'summary.md'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["detailed", "all", "summary"])
    ap.add_argument("findings", nargs="?")
    ap.add_argument("--id")
    ap.add_argument("--run-dir")
    ap.add_argument("--repo")
    ap.add_argument("--config")
    ap.add_argument("--disclosure", choices=["full", "none"])
    ap.add_argument("--no-links", action="store_true")
    ap.add_argument("--marker", choices=["skill", "neutral", "none"])
    ap.add_argument("--attachments-base")
    ap.add_argument("--status")
    ap.add_argument("--min-severity", default="info")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.run_dir and not a.config and (Path(a.run_dir) / "run-config.yaml").exists():
        a.config = str(Path(a.run_dir) / "run-config.yaml")
    opts = Opts(a)
    if a.cmd == "summary":
        if not a.run_dir:
            ap.error("нужен --run-dir")
        cmd_summary(a, opts)
        return
    if not a.findings:
        ap.error("нужен путь к findings.json")
    if a.cmd == "all":
        if not a.run_dir:
            ap.error("нужен --run-dir")
        cmd_all(a, opts)
        return
    data, findings = load(a.findings)
    run = data.get("run", {}) if isinstance(data, dict) else {}
    f = next((x for x in findings if x.get("id") == a.id), None)
    if f is None:
        sys.exit(f"render_draft: находка {a.id} не найдена")
    title, body = render(f, run, opts)
    if a.out:
        write(a.out, title, body)
        print(a.out)
    else:
        print(f"TITLE: {title}\n\n{body}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
