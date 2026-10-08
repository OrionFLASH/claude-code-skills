#!/usr/bin/env python3
"""Черновики issues/комментариев из findings.json по шаблонам templates/.

  render_draft.py detailed findings.json --id F-001 [--run-dir DIR] [--related "owner/repo#12"] [--out FILE]
  render_draft.py comment  findings.json --id F-001 --kind FIXED-INSUFFICIENT|REGRESSION
                  --what-fixed "…" --what-remains "…" --why "…" [--fixed-ref "#12 закрыт 2026-09-01"] [--out FILE]
  render_draft.py all findings.json --run-dir DIR       # подробные черновики всех находок в DIR/drafts/copies/
  render_draft.py severity --config run-config.yaml --repo owner/repo (--severity high | --label P1)

Publication settings (CLI flags override run-config repos[] entry chosen by --repo):
  --config run-config.yaml --repo owner/repo   read disclosure / cross_links / marker / severity_map for that repo
  --disclosure full|none   none: no "created by" footer, no tool names, no skill marker
  --no-links               cross_links: false — no links to other issues/repos (related, matches, copy link)
  --marker skill|neutral|none   skill: <!-- site-qa-audit:fp=… -->, neutral: <!-- qa-fp:… -->, none: no marker
                           default: skill for disclosure full, none for disclosure none

Первая строка файла черновика: "TITLE: <заголовок>", дальше — тело. Пустые секции удаляются.
Маскирование выполняется до записи в findings.json (safety-rules.md §5); здесь — только дополнительная
страховка для e-mail и длинных токенов.
"""
import argparse
import json
import re
import sys
from pathlib import Path

TPL = Path(__file__).resolve().parent.parent / "templates"
EMAIL = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9])[A-Za-z0-9.-]*\.([A-Za-z]{2,})\b")
TOKEN = re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{32,}\b")
SKILL_MARKER = re.compile(r"<!--\s*site-qa-audit:fp=([0-9a-f]*)\s*-->\n?")
ISSUE_REF = re.compile(r"(?<![\w/])([\w.-]+/[\w.-]+)#(\d+)")
FREQ = {"always": "Всегда", "sometimes": "Иногда", "once": "Один раз"}


def is_slug(s):
    """Hyphenated readable names (screenshot files, ids) are not tokens."""
    parts = s.split("-")
    return len(parts) >= 3 and all(len(x) <= 16 for x in parts)


def mask(text):
    text = EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}***.{m.group(3)}", text)
    return TOKEN.sub(lambda m: m.group(0) if is_slug(m.group(0)) else f"{m.group(0)[:4]}…({len(m.group(0))})", text)


def norm_repo(r):
    return re.sub(r"^https?://github\.com/|\.git$|/$", "", r or "")


def repo_settings(config_path, repo):
    """Publication settings for one repo from run-config.yaml (repos[] entry)."""
    if not config_path:
        return {}
    sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
    import miniyaml  # noqa: E402
    cfg = miniyaml.load_file(config_path) or {}
    for r in cfg.get("repos") or []:
        if isinstance(r, dict) and norm_repo(r.get("url") or r.get("repo")) == norm_repo(repo):
            return r
    return {}


class Opts:
    """Disclosure / links / marker / severity scale for the target repository."""

    def __init__(self, repo=None, disclosure="full", cross_links=True, marker=None, severity_map=None):
        self.repo = norm_repo(repo) if repo else None
        self.disclosure = disclosure or "full"
        self.cross_links = cross_links
        default_marker = "skill" if self.disclosure == "full" else "none"
        self.marker = marker or default_marker
        if self.disclosure == "none" and self.marker == "skill":
            sys.stderr.write("render_draft: disclosure none — маркер skill заменён на neutral\n")
            self.marker = "neutral"
        self.severity_map = severity_map or {}

    @classmethod
    def build(cls, a):
        rs = repo_settings(getattr(a, "config", None), getattr(a, "repo", None)) if getattr(a, "repo", None) else {}
        disclosure = a.disclosure or rs.get("disclosure") or "full"
        cross = rs.get("cross_links", True)
        if a.no_links:
            cross = False
        return cls(a.repo, disclosure, cross is not False, a.marker or rs.get("marker"), rs.get("severity_map"))

    def severity_label(self, f):
        forms = (f.get("target_forms") or {}).get(self.repo or "") or {}
        if forms.get("severity_label"):
            return forms["severity_label"]
        return self.severity_map.get(f.get("severity")) if self.severity_map else None

    def finish(self, body):
        """Apply marker policy and disclosure scrubbing to a rendered body."""
        if self.marker == "neutral":
            body = SKILL_MARKER.sub(lambda m: f"<!-- qa-fp:{m.group(1)} -->\n", body)
        elif self.marker == "none":
            body = SKILL_MARKER.sub("", body)
        if self.disclosure == "none":
            body = re.sub(r"\n---\n_Создано site-qa-audit[^\n]*\n?", "\n", body)
        if not self.cross_links:
            body = ISSUE_REF.sub(lambda m: m.group(0) if self.repo and m.group(1) == self.repo else "", body)
        body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"
        leaks = []
        if self.disclosure == "none":
            leaks += [w for w in ("site-qa-audit", "claude") if w in body.lower()]
        for w in leaks:
            sys.stderr.write(f"render_draft: ВНИМАНИЕ — в тексте осталось «{w}» (из данных находки), проверьте вручную\n")
        return body


def strip_comments(text):
    return re.sub(r"<!--(?!\s*site-qa-audit:).*?-->\n?", "", text, flags=re.S)


def drop_empty(text):
    """Удаляет секции '## …', у которых после подстановки не осталось содержимого, и пустые строки таблиц."""
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
    # пустые <details>
    text = re.sub(r"<details><summary>[^<]+</summary>\s*```(text|json)\s*```\s*</details>\n?", "", text)
    text = re.sub(r"<details><summary>Сеть</summary>\s*\|[^\n]*\n\|[^\n]*\n\s*</details>\n?", "", text)
    text = re.sub(r"^- [^:\n]+:\s*$\n?", "", text, flags=re.M)
    text = re.sub(r"([^\n])\n(#{2,} )", r"\1\n\n\2", text)  # пустая строка перед заголовком
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def fill(template, values):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(values.get(m.group(1), "") or ""), template)


def load_findings(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data, (data["findings"] if isinstance(data, dict) else data)


def visible_shots(shots):
    """Если есть X-annotated.png, оригинал X.png в черновик не выводится."""
    ann = {s.replace("-annotated.png", ".png") for s in shots if s.endswith("-annotated.png")}
    return [s for s in shots if s not in ann]


def claim_md(f, opts):
    c = f.get("claim_ref") or {}
    if not c:
        return ""
    ref = f"{c.get('repo')}#{c.get('number')}"
    if not opts.cross_links and norm_repo(c.get("repo")) != opts.repo:
        ref = "исходный issue"
    quote = (c.get("quote") or "").strip()
    return f"{ref}" + (f" — заявлено: «{quote}»" if quote else "")


def common_values(f, run, opts=None):
    opts = opts or Opts()
    env = f.get("environment") or {}
    shots = visible_shots(f.get("screenshots") or [])
    tri = f.get("triage") or {}
    label = opts.severity_label(f)
    return {
        "frequency_text": FREQ.get(f.get("frequency"), f.get("frequency") or ""),
        "account_state": f.get("account_state") or "", "platform": f.get("platform") or "",
        "triage_text": "; ".join(x for x in [tri.get("severity"), tri.get("kind"),
                                             f"уверенность {tri['confidence']}" if tri.get("confidence") not in (None, "") else "",
                                             tri.get("note")] if x) if tri else "",
        "claim_md": claim_md(f, opts),
        "severity_label": label or "",
        "title": f.get("title"),
        "severity": (label if opts.disclosure == "none" else f"{label} ({f.get('severity')})") if label else f.get("severity"),
        "severity_upper": label or (f.get("severity") or "").upper(),
        "direction": f.get("direction"), "check_id": f.get("check_id"), "type": f.get("type"),
        "status": f.get("status") or "NEW", "url": f.get("url"), "element": f.get("element") or "",
        "sources": "" if opts.disclosure == "none" else ", ".join(f.get("sources") or []),
        "run_id": "" if opts.disclosure == "none" else run.get("id", ""),
        "depth": "" if opts.disclosure == "none" else run.get("depth", ""),
        "steps_numbered": "\n".join(f"{i}. {s}" for i, s in enumerate(f.get("steps") or [], 1)),
        "expected": f.get("expected"), "actual": f.get("actual"),
        "actual_one_line": (f.get("actual") or f.get("suggestion") or f.get("title") or "").split("\n")[0][:300],
        "browser": env.get("browser"), "browser_version": env.get("browser_version"), "viewport": env.get("viewport"),
        "os": env.get("os"), "auth": env.get("auth"), "date": env.get("date") or run.get("started_at", "")[:10],
        "environment_list": ", ".join(f.get("environment_list") or []),
        "screenshots_md": "\n".join(f"![{Path(s).stem}]({s})" for s in shots),
        "console": "\n".join(f.get("console") or []),
        "network_rows": "\n".join(f"| {n.get('method', 'GET')} | {n.get('url')} | {n.get('status')} |" for n in f.get("network") or []),
        "evidence_json": json.dumps(f.get("evidence"), ensure_ascii=False, indent=2) if f.get("evidence") else "",
        "hypothesis": f.get("hypothesis"), "suggestion": f.get("suggestion"), "fingerprint": f.get("fingerprint", ""),
        "status_links": "".join(f" — {m.get('repo')}#{m.get('number')}" for m in f.get("matches") or []
                                if opts.cross_links or norm_repo(m.get("repo")) == opts.repo),
    }


def render_detailed(f, run, related=None, screenshot_base=None, rel_prefix="", opts=None):
    """rel_prefix — путь от файла черновика до папки прогона (для локальных ссылок на скриншоты)."""
    opts = opts or Opts()
    v = common_values(f, run, opts)
    if rel_prefix and not screenshot_base:
        v["screenshots_md"] = "\n".join(f"![{Path(s).stem}]({rel_prefix}{s})" for s in visible_shots(f.get("screenshots") or []))
    if screenshot_base:
        v["screenshots_md"] = "\n".join(f"![{Path(s).stem}]({screenshot_base.rstrip('/')}/{Path(s).name}?raw=true)"
                                        for s in visible_shots(f.get("screenshots") or []))
    links = (related or []) + [f"{m.get('repo')}#{m.get('number')}" for m in f.get("matches") or []]
    if not opts.cross_links:
        links = [x for x in links if opts.repo and x.startswith(opts.repo + "#")]
    v["related_links"] = "\n".join(f"- {r}" for r in links)
    body = drop_empty(fill(strip_comments((TPL / "issue-detailed.md").read_text(encoding="utf-8")), v))
    body = re.sub(r"^\|\s*\*\*Прогон\*\*\s*\|\s*\(\)\s*\|\n?", "", body, flags=re.M)
    return f"[{v['severity_upper']}] {v['title']}", mask(opts.finish(body))


def render_comment(f, run, kind, what_fixed, what_remains, why, fixed_ref=None, copy_link=None, opts=None):
    opts = opts or Opts()
    if not opts.cross_links:
        copy_link = None
    v = common_values(f, run, opts)
    v.update({
        "status_title": "Проверка исправления: проблема воспроизводится частично" if kind == "FIXED-INSUFFICIENT"
        else "Регрессия: проблема снова воспроизводится",
        "what_fixed": what_fixed, "what_remains": what_remains,
        "why_insufficient": why if kind == "FIXED-INSUFFICIENT" else f"Было исправлено: {fixed_ref}. Сейчас воспроизводится полностью. Предлагаю переоткрыть issue.",
        "copy_link": f"Подробная копия: {copy_link}" if copy_link else "",
    })
    return None, mask(opts.finish(drop_empty(fill(strip_comments((TPL / "issue-comment.md").read_text(encoding="utf-8")), v))))


def write(out, title, body):
    text = (f"TITLE: {title}\n\n" if title else "") + body
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
        print(out)
    else:
        print(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["detailed", "comment", "all", "severity"])
    ap.add_argument("findings", nargs="?")
    ap.add_argument("--config", help="run-config.yaml: настройки публикации для --repo")
    ap.add_argument("--repo", help="целевой репозиторий owner/repo")
    ap.add_argument("--disclosure", choices=["full", "none"])
    ap.add_argument("--no-links", action="store_true", help="без ссылок на другие issues и репозитории")
    ap.add_argument("--marker", choices=["skill", "neutral", "none"])
    ap.add_argument("--severity")
    ap.add_argument("--label")
    ap.add_argument("--id")
    ap.add_argument("--run-dir")
    ap.add_argument("--related", action="append")
    ap.add_argument("--screenshot-base", help="URL папки скриншотов в репозитории (blob/<branch>/runs/…)")
    ap.add_argument("--kind", choices=["FIXED-INSUFFICIENT", "REGRESSION"])
    ap.add_argument("--what-fixed", default="")
    ap.add_argument("--what-remains", default="")
    ap.add_argument("--why", default="")
    ap.add_argument("--fixed-ref", default="")
    ap.add_argument("--copy-link")
    ap.add_argument("--out")
    a = ap.parse_args()
    opts = Opts.build(a)
    if a.cmd == "severity":
        smap = opts.severity_map
        if not smap:
            sys.exit("severity_map не задан для этого репозитория в run-config")
        if a.severity:
            print(smap.get(a.severity) or sys.exit(f"нет соответствия для {a.severity}"))
        elif a.label:
            back = {}
            for k, v in smap.items():  # first (most severe) skill level wins for shared labels
                back.setdefault(str(v).lower(), k)
            print(back.get(a.label.lower()) or sys.exit(f"нет соответствия для {a.label}"))
        else:
            print(json.dumps(smap, ensure_ascii=False))
        return
    if not a.findings:
        ap.error("нужен путь к findings.json")
    data, findings = load_findings(a.findings)
    run = data.get("run", {}) if isinstance(data, dict) else {}
    if a.cmd == "all":
        if not a.run_dir:
            ap.error("нужен --run-dir")
        for i, f in enumerate(findings, 1):
            title, body = render_detailed(f, run, screenshot_base=a.screenshot_base, rel_prefix="../../", opts=opts)
            write(Path(a.run_dir) / "drafts" / "copies" / f"{i:02d}-{f.get('status') or 'NEW'}-{f.get('fingerprint', f['id'])}.md",
                  title, body)
        return
    f = next((x for x in findings if x.get("id") == a.id), None)
    if f is None:
        sys.exit(f"находка {a.id} не найдена")
    if a.cmd == "detailed":
        write(a.out, *render_detailed(f, run, a.related, a.screenshot_base, opts=opts))
    else:
        if not a.kind:
            ap.error("нужен --kind")
        write(a.out, *render_comment(f, run, a.kind, a.what_fixed, a.what_remains, a.why, a.fixed_ref, a.copy_link,
                                     opts=opts))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
