#!/usr/bin/env python3
"""Черновики issues/комментариев из findings.json по шаблонам templates/.

  render_draft.py detailed findings.json --id F-001 [--run-dir DIR] [--related "owner/repo#12"] [--out FILE]
  render_draft.py comment  findings.json --id F-001 --kind FIXED-INSUFFICIENT|REGRESSION
                  --what-fixed "…" --what-remains "…" --why "…" [--fixed-ref "#12 закрыт 2026-09-01"] [--out FILE]
  render_draft.py all findings.json --run-dir DIR       # подробные черновики всех находок в DIR/drafts/copies/

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


def mask(text):
    text = EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}***.{m.group(3)}", text)
    return TOKEN.sub(lambda m: f"{m.group(0)[:4]}…({len(m.group(0))})", text)


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


def common_values(f, run):
    env = f.get("environment") or {}
    shots = f.get("screenshots") or []
    return {
        "title": f.get("title"), "severity": f.get("severity"), "severity_upper": (f.get("severity") or "").upper(),
        "direction": f.get("direction"), "check_id": f.get("check_id"), "type": f.get("type"),
        "status": f.get("status") or "NEW", "url": f.get("url"), "element": f.get("element") or "",
        "sources": ", ".join(f.get("sources") or []), "run_id": run.get("id", ""), "depth": run.get("depth", ""),
        "steps_numbered": "\n".join(f"{i}. {s}" for i, s in enumerate(f.get("steps") or [], 1)),
        "expected": f.get("expected"), "actual": f.get("actual"),
        "actual_one_line": (f.get("actual") or "").split("\n")[0][:300],
        "browser": env.get("browser"), "browser_version": env.get("browser_version"), "viewport": env.get("viewport"),
        "os": env.get("os"), "auth": env.get("auth"), "date": env.get("date") or run.get("started_at", "")[:10],
        "environment_list": ", ".join(f.get("environment_list") or []),
        "screenshots_md": "\n".join(f"![{Path(s).stem}]({s})" for s in shots),
        "console": "\n".join(f.get("console") or []),
        "network_rows": "\n".join(f"| {n.get('method', 'GET')} | {n.get('url')} | {n.get('status')} |" for n in f.get("network") or []),
        "evidence_json": json.dumps(f.get("evidence"), ensure_ascii=False, indent=2) if f.get("evidence") else "",
        "hypothesis": f.get("hypothesis"), "suggestion": f.get("suggestion"), "fingerprint": f.get("fingerprint", ""),
        "status_links": "".join(f" — {m.get('repo')}#{m.get('number')}" for m in f.get("matches") or []),
    }


def render_detailed(f, run, related=None, screenshot_base=None, rel_prefix=""):
    """rel_prefix — путь от файла черновика до папки прогона (для локальных ссылок на скриншоты)."""
    v = common_values(f, run)
    if rel_prefix and not screenshot_base:
        v["screenshots_md"] = "\n".join(f"![{Path(s).stem}]({rel_prefix}{s})" for s in f.get("screenshots") or [])
    if screenshot_base:
        v["screenshots_md"] = "\n".join(f"![{Path(s).stem}]({screenshot_base.rstrip('/')}/{Path(s).name}?raw=true)"
                                        for s in f.get("screenshots") or [])
    v["related_links"] = "\n".join(f"- {r}" for r in (related or []) +
                                   [f"{m.get('repo')}#{m.get('number')}" for m in f.get("matches") or []])
    body = drop_empty(fill(strip_comments((TPL / "issue-detailed.md").read_text(encoding="utf-8")), v))
    return f"[{v['severity_upper']}] {v['title']}", mask(body)


def render_comment(f, run, kind, what_fixed, what_remains, why, fixed_ref=None, copy_link=None):
    v = common_values(f, run)
    v.update({
        "status_title": "Проверка исправления: проблема воспроизводится частично" if kind == "FIXED-INSUFFICIENT"
        else "Регрессия: проблема снова воспроизводится",
        "what_fixed": what_fixed, "what_remains": what_remains,
        "why_insufficient": why if kind == "FIXED-INSUFFICIENT" else f"Было исправлено: {fixed_ref}. Сейчас воспроизводится полностью. Предлагаю переоткрыть issue.",
        "copy_link": f"Подробная копия: {copy_link}" if copy_link else "",
    })
    return None, mask(drop_empty(fill(strip_comments((TPL / "issue-comment.md").read_text(encoding="utf-8")), v)))


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
    ap.add_argument("cmd", choices=["detailed", "comment", "all"])
    ap.add_argument("findings")
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
    data, findings = load_findings(a.findings)
    run = data.get("run", {}) if isinstance(data, dict) else {}
    if a.cmd == "all":
        if not a.run_dir:
            ap.error("нужен --run-dir")
        for i, f in enumerate(findings, 1):
            title, body = render_detailed(f, run, screenshot_base=a.screenshot_base, rel_prefix="../../")
            write(Path(a.run_dir) / "drafts" / "copies" / f"{i:02d}-{f.get('status') or 'NEW'}-{f.get('fingerprint', f['id'])}.md",
                  title, body)
        return
    f = next((x for x in findings if x.get("id") == a.id), None)
    if f is None:
        sys.exit(f"находка {a.id} не найдена")
    if a.cmd == "detailed":
        write(a.out, *render_detailed(f, run, a.related, a.screenshot_base))
    else:
        if not a.kind:
            ap.error("нужен --kind")
        write(a.out, *render_comment(f, run, a.kind, a.what_fixed, a.what_remains, a.why, a.fixed_ref, a.copy_link))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
