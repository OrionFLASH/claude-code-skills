#!/usr/bin/env python3
"""Re-check of claimed fixes: extract owner claims from issue comments and build a check plan.

  claims.py extract REGISTRY.json [--repo owner/repo] [--owners a,b] [--all] [--out claims.json]
      REGISTRY — registry.json (fetch_issues.py registry) or an issues cache file (fetch_issues.py sync).
      For every issue with fix_claimed: owner comments with claim markers ("Исправили", "Сделали",
      "Доделали", "Частично", "Fixed", version vX.Y.Z), bullet items, remaining part ("Осталось: …"),
      URLs and paths, quoted texts («…», "…"), area/steps/expected from the issue body, hints for
      NOT-CHECKED (logout needed, other account type, side effects).
      Owners: --owners, else comment author_association OWNER/MEMBER/COLLABORATOR, else the repo owner login.
  claims.py plan CLAIMS.json|REGISTRY.json [--repo R] [--site URL] [--since-days N] [--include-unquoted]
                 [--out plan.md] [--json rechecks.json]
      Checklist (Markdown) and a rechecks skeleton (JSON) for report.md: one item per claimed issue with a quote.
  claims.py set rechecks.json --number N [--repo R] --status FIXED-OK|FIXED-INSUFFICIENT|REGRESSION|NOT-CHECKED
                 [--by "how it was checked"] [--reason logout-required|other-account-type|forbidden|steps-unclear|
                 environment|other] [--reason-text "…"] [--finding F-012]
      Record the result of one re-check.

Exit codes: 0 ok, 1 nothing found (plan is empty), 2 bad input.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

CLAIM_RX = re.compile(
    r"(исправил[иа]?|исправлено|сделали|доделали|поправил[иа]?|починил[иа]?|частично|что сделали|"
    r"убрали|добавили|теперь\b|\bfixed\b|\bdone\b|\bimplemented\b|\bresolved\b|\bpartially\b|"
    r"\bv\d+\.\d+\.\d+)", re.I)
PARTIAL_RX = re.compile(r"(частично|(?:^|\n|[.!]\s)\s*осталось\b|\bосталось:|не успели|пока не (сделали|делали)|ещё не (сделали|делали)|"
                        r"partially|remaining:|not yet)", re.I)
DONE_RX = re.compile(r"(доделали|закрываю|completed|fully)", re.I)
VERSION_RX = re.compile(r"\bv(\d+(?:\.\d+){1,3})\b|\b(?:версии|version)\s+(\d+(?:\.\d+){1,3})\b", re.I)
URL_RX = re.compile(r"https?://[^\s)\]>\"'«»]+")
PATH_RX = re.compile(r"(?<![\w/.:])(/[a-z0-9][a-z0-9_\-]*(?:/[a-z0-9_\-.]+)*/?)(?![\w/])", re.I)
QUOTE_RX = re.compile(r"«([^«»\n]{1,100})»|“([^”\n]{1,100})”|\"([^\"\n]{1,100})\"")
BULLET_RX = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+)$", re.M)
REMAIN_RX = re.compile(r"(?:^|\n)\s*(?:осталось|не сделано|remaining|still)[^:\n]*:\s*(.+?)(?:\n\s*\n|\Z)", re.I | re.S)
ATTACH_RX = re.compile(r"github\.com/user-attachments/|githubusercontent\.com/")
# Issue body sections (issue forms render as "### Label").
SECTIONS = {
    "area": r"где|area|раздел|component",
    "url": r"адрес страницы|url|ссылка|page",
    "steps": r"шаги( воспроизведения)?|steps( to reproduce)?|how to reproduce|как воспроизвести",
    "expected": r"что ожидали|ожидаемо(е|ый результат)?|expected( behavio(u)?r| result)?",
    "actual": r"что получилось|фактически|фактический результат|actual( behavio(u)?r| result)?|что мешает сейчас",
    "proposal": r"что предлагаете|предложение|proposal|suggested solution",
    "account": r"аккаунт|account|вход",
    "frequency": r"как часто|frequency|повторяемость",
}
HINTS = [
    ("logout-required", re.compile(r"(без входа|не вошед|гост|выйти из аккаунта|разлогин|logged[- ]out|"
                                   r"signed[- ]out|без аккаунта|незарегистрирован)", re.I)),
    ("other-account-type", re.compile(r"(\bpro\b|премиум|premium|подписк|subscription|администратор|"
                                      r"модератор|admin\b|другой аккаунт|второй аккаунт)", re.I)),
    ("side-effect", re.compile(r"(загрузи(ть|те) (сохранение|сейв|файл)|загрузка (сохранения|сейва|файла)|"
                               r"рейтинг|публичн|опубликова|рассылк|upload|leaderboard)", re.I)),
    ("device", re.compile(r"(телефон|мобильн|iphone|android|ipad|планшет|альбомн|landscape|safari|webkit)", re.I)),
]
NOT_CHECKED_REASONS = ["logout-required", "other-account-type", "forbidden", "steps-unclear", "environment", "other"]
STATUSES = ["FIXED-OK", "FIXED-INSUFFICIENT", "REGRESSION", "NOT-CHECKED"]
OWNER_ASSOC = {"OWNER", "MEMBER", "COLLABORATOR"}


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        sys.stderr.write(f"claims: не удалось прочитать {path}: {ex}\n")
        sys.exit(2)


def default_fix_claimed(iss):
    if iss.get("state") == "closed" and iss.get("state_reason") in (None, "completed"):
        return True
    return any(CLAIM_RX.search(c.get("body") or "") for c in iss.get("comments") or [])


def load_issues(data, repo_filter=None):
    """Accept registry.json ({"issues": [...]}) or a cache file ({"repo", "issues": {num: issue}})."""
    if isinstance(data, dict) and isinstance(data.get("issues"), dict):
        repo = data.get("repo", "")
        issues = [dict(i, repo=i.get("repo") or repo) for i in data["issues"].values()]
    elif isinstance(data, dict) and isinstance(data.get("issues"), list):
        issues = data["issues"]
    elif isinstance(data, list):
        issues = data
    else:
        sys.stderr.write("claims: неизвестный формат реестра (ожидается registry.json или кэш fetch_issues)\n")
        sys.exit(2)
    if repo_filter:
        issues = [i for i in issues if i.get("repo") == repo_filter]
    for i in issues:
        if "fix_claimed" not in i:
            i["fix_claimed"] = default_fix_claimed(i)
    return sorted(issues, key=lambda i: (i.get("repo") or "", i.get("number") or 0))


def body_sections(body):
    """'### Label\\n\\ntext' sections -> {key: text}; _No response_ is dropped."""
    out = {}
    parts = re.split(r"^#{2,4}\s+(.+?)\s*$", body or "", flags=re.M)
    for label, text in zip(parts[1::2], parts[2::2]):
        text = re.sub(r"<img[^>]*>", "", text).strip()
        if not text or text in ("_No response_", "None"):
            continue
        for key, rx in SECTIONS.items():
            if key not in out and re.fullmatch(rf"\s*({rx})\s*[:?]?\s*", label, re.I):
                out[key] = text
                break
    return out


def steps_from_body(body, sections):
    text = sections.get("steps")
    if text:
        items = [m.group(1).strip() for m in BULLET_RX.finditer(text)]
        return items or [ln.strip() for ln in text.splitlines() if ln.strip()][:12]
    items = [m.group(1).strip() for m in re.finditer(r"^\s*\d+[.)]\s+(.+)$", body or "", re.M)]
    return items[:12]


def urls_in(text):
    urls, attachments = [], []
    for u in URL_RX.findall(text or ""):
        u = u.rstrip(".,;:")
        (attachments if ATTACH_RX.search(u) else urls).append(u)
    return list(dict.fromkeys(urls)), list(dict.fromkeys(attachments))


def paths_in(text):
    text = URL_RX.sub(" ", text or "")
    return list(dict.fromkeys(p for p in PATH_RX.findall(text) if len(p) > 1 and not re.fullmatch(r"/\d+", p)))


def quotes_in(text):
    res = []
    for m in QUOTE_RX.finditer(URL_RX.sub(" ", text or "")):
        q = next(g for g in m.groups() if g is not None).strip()
        if q and q not in res:
            res.append(q)
    return res


def first_paragraph(text, limit=400):
    paras = re.split(r"\n\s*\n", (text or "").strip())
    para = paras[0].strip()
    if para.endswith(":") and len(paras) > 1:  # "Доделали:" followed by the list
        para += " " + paras[1].strip()
    para = re.sub(r"\s+", " ", para)
    return para if len(para) <= limit else para[:limit - 1].rstrip() + "…"


def is_owner(comment, owners, repo):
    author = (comment.get("author") or "").lower()
    if owners:
        return author in owners
    if comment.get("author_association") in OWNER_ASSOC:
        return True
    return bool(repo) and author == repo.split("/")[0].lower()


def claim_kind(text):
    text = QUOTE_RX.sub("«»", text)  # UI names in quotes («Осталось найти») are not claim words
    if PARTIAL_RX.search(text) and not DONE_RX.search(text.split("\n", 1)[0]):
        return "partial"
    if CLAIM_RX.search(text):
        return "fixed"
    return "reply"


def extract_issue(iss, owners):
    repo = iss.get("repo") or ""
    body = iss.get("body") or ""
    sections = body_sections(body)
    claims = []
    for c in iss.get("comments") or []:
        if not is_owner(c, owners, repo):
            continue
        text = c.get("body") or ""
        kind = claim_kind(text)
        vm = VERSION_RX.search(text)
        rem = REMAIN_RX.search(text)
        claims.append({
            "kind": kind, "version": (vm.group(1) or vm.group(2)) if vm else None,
            "quote": first_paragraph(text), "items": [m.group(1).strip() for m in BULLET_RX.finditer(text)][:15],
            "remaining": first_paragraph(rem.group(1), 300) if rem else None,
            "date": (c.get("created_at") or "")[:10], "author": c.get("author"), "url": c.get("url"),
        })
    explicit = [c for c in claims if c["kind"] != "reply"]
    last = (explicit or claims or [None])[-1]
    all_text = body + "\n" + "\n".join(c.get("body") or "" for c in iss.get("comments") or [])
    owner_text = "\n".join(c["quote"] + "\n" + "\n".join(c["items"]) for c in claims)
    urls, attachments = urls_in(all_text)
    if sections.get("url"):
        urls = list(dict.fromkeys(urls_in(sections["url"])[0] + urls))
    hints = [name for name, rx in HINTS if rx.search(body + "\n" + owner_text)]
    return {
        "repo": repo, "number": iss.get("number"), "title": iss.get("title"), "url": iss.get("url"),
        "state": iss.get("state"), "state_reason": iss.get("state_reason"), "closed_at": iss.get("closed_at"),
        "fix_claimed": bool(iss.get("fix_claimed")),
        "version": last["version"] if last else None,
        "claim_kind": last["kind"] if last else None,
        "quote": last["quote"] if last else None,
        "claims": claims,
        "area": first_paragraph(sections.get("area", ""), 120) or None,
        "urls": urls, "paths": paths_in(owner_text + "\n" + body), "attachments": attachments,
        "quoted_texts": quotes_in(owner_text + "\n" + iss.get("title", ""))[:20],
        "steps": steps_from_body(body, sections),
        "expected": first_paragraph(sections.get("expected", ""), 400) or None,
        "actual": first_paragraph(sections.get("actual", ""), 400) or None,
        "hints": hints,
    }


def cmd_extract(a):
    issues = load_issues(load_json(a.registry), a.repo)
    owners = {o.strip().lower() for o in (a.owners or "").split(",") if o.strip()}
    res = [extract_issue(i, owners) for i in issues if a.all or i.get("fix_claimed")]
    out = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source": str(a.registry), "repo": a.repo, "claims": res}
    with_quote = sum(1 for c in res if c["quote"])
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"claims: issues с заявленным исправлением {len(res)}, с цитатой владельца {with_quote} -> {a.out}")
    else:
        print(text)
    return 0 if res else 1


def strip_www(host):
    host = (host or "").lower()
    return host[4:] if host.startswith("www.") else host


def site_matches(c, host):
    if not host:
        return True
    hosts = {strip_www(urlsplit(u).hostname) for u in c["urls"]}
    return not hosts or host in hosts or any(h.endswith("." + host) for h in hosts)


def cmd_plan(a):
    data = load_json(a.source)
    if isinstance(data, dict) and "claims" in data:
        items = data["claims"]
        if a.repo:
            items = [c for c in items if c["repo"] == a.repo]
    else:
        items = [extract_issue(i, set()) for i in load_issues(data, a.repo) if i.get("fix_claimed")]
    host = strip_www(urlsplit(a.site).hostname) if a.site else None
    since = None
    if a.since_days:
        since = (datetime.now(timezone.utc) - timedelta(days=a.since_days)).strftime("%Y-%m-%d")
    plan, skipped = [], []
    for c in items:
        if not site_matches(c, host):
            skipped.append((c, "другой сайт"))
        elif since and c.get("closed_at") and c["closed_at"][:10] < since:
            skipped.append((c, f"закрыт раньше {since}"))
        elif not c.get("quote") and not a.include_unquoted:
            skipped.append((c, "нет комментария владельца с заявлением"))
        else:
            plan.append(c)
    lines = [f"# План перепроверки заявленных исправлений", "",
             f"Пунктов: {len(plan)} (пропущено: {len(skipped)}). Статус каждого: FIXED-OK / FIXED-INSUFFICIENT / "
             "REGRESSION / NOT-CHECKED (причина). Результат записывать: `claims.py set <rechecks.json> --number N …`.", ""]
    for n, c in enumerate(plan, 1):
        ver = f" (v{c['version']})" if c.get("version") else ""
        kind = {"partial": "частично", "fixed": "исправлено", "reply": "ответ без явного заявления"}.get(c.get("claim_kind"), "—")
        lines += [f"## {n}. {c['repo']}#{c['number']} — {c['title']}", "",
                  f"- [ ] Заявлено{ver}: {kind}" + (f", {c['claims'][-1]['date']}" if c.get("claims") else "")]
        if c.get("quote"):
            lines.append(f"  > {c['quote']}")
        for it in (c["claims"][-1]["items"] if c.get("claims") else [])[:8]:
            lines.append(f"  - [ ] проверить: {it}")
        rem = next((x["remaining"] for x in reversed(c.get("claims") or []) if x.get("remaining")), None)
        if rem and c.get("claim_kind") == "partial":
            lines.append(f"  - Владелец пишет, что осталось: {rem}")
        if c.get("area"):
            lines.append(f"- Раздел: {c['area']}")
        if c.get("urls") or c.get("paths"):
            lines.append("- Где: " + ", ".join(c.get("urls", [])[:5] + c.get("paths", [])[:5]))
        if c.get("quoted_texts"):
            lines.append("- Элементы и тексты: " + ", ".join(f"«{q}»" for q in c["quoted_texts"][:10]))
        if c.get("steps"):
            lines.append("- Шаги из issue:")
            lines += [f"  {i}. {s}" for i, s in enumerate(c["steps"][:10], 1)]
        if c.get("expected"):
            lines.append(f"- Ожидалось (из issue): {c['expected']}")
        hints = c.get("hints") or []
        if hints:
            names = {"logout-required": "может понадобиться выход из аккаунта (NOT-CHECKED: logout-required)",
                     "other-account-type": "может понадобиться другой тип аккаунта (NOT-CHECKED: other-account-type)",
                     "side-effect": "ВНИМАНИЕ: шаги с побочным эффектом (загрузка/публикация) — сверить с side_effects и запретами",
                     "device": "проверять на устройстве/браузере из issue"}
            lines += [f"- Условие: {names[h]}" for h in hints]
        lines.append("")
    if skipped:
        lines += ["## Пропущено", ""] + [f"- {c['repo']}#{c['number']} — {c['title']}: {why}" for c, why in skipped]
    text = "\n".join(lines).rstrip() + "\n"
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"plan: пунктов {len(plan)}, с цитатой {sum(1 for c in plan if c.get('quote'))}, пропущено {len(skipped)} -> {a.out}")
    else:
        print(text)
    if a.json:
        rechecks = [{"repo": c["repo"], "number": c["number"], "title": c["title"], "quote": c.get("quote") or "",
                     "version": c.get("version"), "urls": c.get("urls", [])[:5], "status": None, "reason": None,
                     "reason_text": "", "checked_by": "", "finding_id": None} for c in plan]
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps({"rechecks": rechecks}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"rechecks: {len(rechecks)} -> {a.json}")
    return 0 if plan else 1


def cmd_set(a):
    data = load_json(a.rechecks)
    rows = data.get("rechecks", []) if isinstance(data, dict) else data
    hit = [r for r in rows if r.get("number") == a.number and (not a.repo or r.get("repo") == a.repo)]
    if len(hit) != 1:
        sys.stderr.write(f"claims set: найдено записей {len(hit)} для #{a.number} — уточните --repo\n")
        return 2
    if a.status == "NOT-CHECKED" and not a.reason:
        sys.stderr.write("claims set: для NOT-CHECKED нужна --reason\n")
        return 2
    r = hit[0]
    r.update({"status": a.status, "reason": a.reason if a.status == "NOT-CHECKED" else None})
    if a.by is not None:
        r["checked_by"] = a.by
    if a.reason_text is not None:
        r["reason_text"] = a.reason_text
    if a.finding:
        r["finding_id"] = a.finding
    Path(a.rechecks).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{r['repo']}#{r['number']}: {a.status}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("registry")
    e.add_argument("--repo")
    e.add_argument("--owners", help="логины владельцев через запятую")
    e.add_argument("--all", action="store_true", help="все issues, не только с fix_claimed")
    e.add_argument("--out")
    p = sub.add_parser("plan")
    p.add_argument("source", help="claims.json или registry.json")
    p.add_argument("--repo")
    p.add_argument("--site", help="URL проверяемого сайта: issues с URL других хостов пропускаются")
    p.add_argument("--since-days", type=int)
    p.add_argument("--include-unquoted", action="store_true")
    p.add_argument("--out")
    p.add_argument("--json")
    s = sub.add_parser("set")
    s.add_argument("rechecks")
    s.add_argument("--number", type=int, required=True)
    s.add_argument("--repo")
    s.add_argument("--status", choices=STATUSES, required=True)
    s.add_argument("--reason", choices=NOT_CHECKED_REASONS)
    s.add_argument("--reason-text")
    s.add_argument("--by")
    s.add_argument("--finding")
    a = ap.parse_args()
    sys.exit({"extract": cmd_extract, "plan": cmd_plan, "set": cmd_set}[a.cmd](a))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
