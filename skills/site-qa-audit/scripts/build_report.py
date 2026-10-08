#!/usr/bin/env python3
"""Build report.md and the pre-publication summary table from the run folder.

  build_report.py report RUN_DIR [--findings F] [--config run-config.yaml] [--rechecks rechecks.json]
                  [--registry registry.json] [--side-effects side_effects.md] [--out RUN_DIR/report.md]
      report.md from findings.json, the re-check table (claims.py plan/set → rechecks.json or
      findings.json → rechecks), side_effects.md and logs/blocked.jsonl, if present.
  build_report.py summary RUN_DIR [same options] [--out RUN_DIR/summary.md]
      Short summary for report destinations: header, «Итог», statistics and directions of report.md.
  build_report.py publish-table RUN_DIR [same options] [--out FILE]
      Summary table before publication: status, severity on the repo scale, target, action.
      For FIXED-INSUFFICIENT / REGRESSION of a closed issue the action follows repos[].closed_claims
      (comment | new | skip; default comment).

Default paths are inside RUN_DIR: findings.json, run-config.yaml, rechecks.json, registry.json,
side_effects.md, logs/blocked.jsonl. Missing optional files are skipped.
Exit codes: 0 ok, 2 no findings.json.
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
import miniyaml  # noqa: E402
import qa_recheck  # noqa: E402 — publication gate: independent re-check, legal second check (S-9)

SEVERITIES = ["critical", "high", "medium", "low", "info"]
STATUSES = ["NEW", "DUPLICATE-OPEN", "FIXED-INSUFFICIENT", "REGRESSION", "ALREADY-COPIED", "UNSURE-MATCH",
            "FIXED-OK", "NOT-CHECKED"]
REASONS = {"logout-required": "нужен выход из аккаунта", "other-account-type": "нужен другой тип аккаунта",
           "forbidden": "запрет", "steps-unclear": "шаги неясны", "environment": "окружение",
           "other": "другое"}
CLOSED_POLICY = {"comment": "комментарий", "new": "новый issue", "skip": "пропуск"}


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def norm_repo(r):
    return re.sub(r"^https?://github\.com/|\.git$|/$", "", r or "")


def cell(text, limit=160):
    text = re.sub(r"\s+", " ", str(text or "")).strip().replace("|", "\\|")
    return text if len(text) <= limit else text[:limit - 1] + "…"


class Run:
    def __init__(self, a):
        d = Path(a.run_dir)
        self.dir = d
        self.data = load_json(a.findings or d / "findings.json")
        if self.data is None:
            sys.stderr.write("build_report: нет findings.json\n")
            sys.exit(2)
        self.findings = self.data.get("findings", []) if isinstance(self.data, dict) else self.data
        cfg = Path(a.config) if a.config else d / "run-config.yaml"
        self.config = miniyaml.load_file(cfg) if cfg.exists() else {}
        rc = load_json(a.rechecks or d / "rechecks.json", {})
        rows = (rc.get("rechecks") if isinstance(rc, dict) else rc) or []
        rows += (self.data.get("rechecks") or []) if isinstance(self.data, dict) else []
        merged = {}
        for r in rows:  # later entries (findings.json) refine earlier ones
            key = (norm_repo(r.get("repo")), r.get("number"))
            merged[key] = {**merged.get(key, {}), **{k: v for k, v in r.items() if v not in (None, "")}}
        for f in self.findings:  # findings with claim_ref complete the table
            c = f.get("claim_ref")
            if not c:
                continue
            key = (norm_repo(c.get("repo")), c.get("number"))
            row = merged.setdefault(key, {"repo": c.get("repo"), "number": c.get("number"), "quote": c.get("quote", "")})
            row.setdefault("finding_id", f["id"])
            if not row.get("status") and f.get("status") in ("FIXED-OK", "FIXED-INSUFFICIENT", "REGRESSION", "NOT-CHECKED"):
                row["status"] = f["status"]
                row.setdefault("reason", f.get("not_checked_reason"))
                row.setdefault("reason_text", f.get("status_reason", ""))
            row.setdefault("title", f.get("title"))
        self.rechecks = list(merged.values())
        reg = load_json(a.registry or d / "registry.json", {}) or {}
        self.issues = {(norm_repo(i.get("repo")), i.get("number")): i for i in reg.get("issues", [])}
        se = Path(a.side_effects) if a.side_effects else d / "side_effects.md"
        self.side_effects = se.read_text(encoding="utf-8") if se.exists() else None
        self.blocked = []
        bl = d / "logs" / "blocked.jsonl"
        if bl.exists():
            for line in bl.read_text(encoding="utf-8").splitlines():
                try:
                    self.blocked.append(json.loads(line))
                except ValueError:
                    continue

    @property
    def run(self):
        return self.data.get("run", {}) if isinstance(self.data, dict) else {}

    def repos(self):
        return [r for r in self.config.get("repos") or [] if isinstance(r, dict)]


def recheck_table(run):
    if not run.rechecks:
        return []
    out = ["| № | Issue | Заявлено | Статус | Что проверено | Чем |", "|---|---|---|---|---|---|"]
    for n, r in enumerate(sorted(run.rechecks, key=lambda x: (x.get("repo") or "", x.get("number") or 0)), 1):
        status = r.get("status") or "не проверено (нет результата)"
        if status == "NOT-CHECKED":
            reason = REASONS.get(r.get("reason"), r.get("reason") or "причина не указана")
            status = f"NOT-CHECKED: {reason}" + (f" ({r['reason_text']})" if r.get("reason_text") else "")
        what = r.get("title") or ""
        if r.get("finding_id"):
            what += f" → {r['finding_id']}"
        out.append(f"| {n} | {r.get('repo')}#{r.get('number')} | {cell(r.get('quote'), 140)} | {cell(status, 120)} | "
                   f"{cell(what, 120)} | {cell(r.get('checked_by') or '—', 120)} |")
    return out


def issue_state(run, repo, number):
    iss = run.issues.get((norm_repo(repo), number))
    return iss.get("state") if iss else None


def plan_actions(run):
    """[(finding, repo, severity_label, action)] for the pre-publication table."""
    rows = []
    for f in run.findings:
        st = f.get("status") or "NEW"
        for r in run.repos():
            repo = norm_repo(r.get("url") or r.get("repo"))
            roles = r.get("roles") or []
            if isinstance(roles, str):
                roles = [roles]
            smap = r.get("severity_map") or {}
            label = ((f.get("target_forms") or {}).get(repo) or {}).get("severity_label") or smap.get(f.get("severity")) \
                or f.get("severity")
            refs = [m for m in f.get("matches") or [] if norm_repo(m.get("repo")) == repo]
            c = f.get("claim_ref")
            if c and norm_repo(c.get("repo")) == repo and not any(m.get("number") == c.get("number") for m in refs):
                refs.insert(0, {"repo": repo, "number": c.get("number")})
            action = None
            if st in ("FIXED-INSUFFICIENT", "REGRESSION") and refs:
                num = refs[0].get("number")
                state = issue_state(run, repo, num)
                if state == "open":
                    action = (f"комментарий в #{num}" if ("comment" in roles or "copies" in roles)
                              else f"нет роли comment (#{num} открыт)")
                else:
                    pol = r.get("closed_claims") or "comment"
                    where = f"#{num} закрыт" if state == "closed" else f"#{num} (состояние неизвестно)"
                    if pol == "skip":
                        action = f"пропуск: {where}, closed_claims: skip"
                    elif pol == "new":
                        action = (f"новый issue: {where}, closed_claims: new" if ("write-new" in roles or "copies" in roles)
                                  else f"нет роли write-new: {where}, closed_claims: new")
                    else:
                        action = (f"комментарий: {where}, closed_claims: comment" if "comment" in roles
                                  else f"нет роли comment: {where}, closed_claims: comment")
            elif st in ("FIXED-OK", "NOT-CHECKED"):
                if any(x[0] is f for x in rows):
                    continue  # one report-only row per finding
                action = "только отчёт"
            elif st == "UNSURE-MATCH":
                action = "вопрос пользователю"
            elif st == "DUPLICATE-OPEN" and refs:
                action = f"пропуск: дубль #{refs[0].get('number')}"
            elif st == "ALREADY-COPIED" and "copies" in roles:
                action = "пропуск: уже скопировано"
            if action is None:
                if "copies" in roles:
                    action = "копия (свой шаблон)"
                elif "write-new" in roles and st == "NEW":
                    action = "issue (их шаблон)"
                else:
                    continue
            if (f.get("evidence") or {}).get("sensitive"):
                action = "не публиковать без решения: чувствительная находка"
            rows.append((f, repo, label, action))
    return rows


def publish_table(run):
    rows = plan_actions(run)
    out = []
    pol = [f"{norm_repo(r.get('url') or r.get('repo'))} — closed_claims: {r.get('closed_claims') or 'comment'}"
           f", раскрытие: {r.get('disclosure') or 'full'}, ссылки: {'да' if r.get('cross_links', True) is not False else 'нет'}"
           for r in run.repos()]
    if pol:
        out += ["Политика по репозиториям:", ""] + [f"- {p}" for p in pol] + [""]
    out += ["| № | ID | Статус | Severity | Заголовок | Куда | Действие | Перепроверка |", "|---|---|---|---|---|---|---|---|"]
    blocked = 0
    for n, (f, repo, label, action) in enumerate(rows, 1):
        problems = qa_recheck.gate_problems(f)
        publishes = not re.match(r"^(пропуск|только отчёт|вопрос|нет роли|не публиковать)", action)
        if problems and publishes:
            action += " — НЕ публиковать до перепроверки"
            blocked += 1
        rc = f.get("recheck") or {}
        recheck = "да" + (f" ({rc.get('by')})" if rc.get("by") else "") if not problems else "нет: " + "; ".join(problems)
        out.append(f"| {n} | {f['id']} | {f.get('status') or 'NEW'} | {cell(label, 30)} | {cell(f.get('title'), 90)} | "
                   f"{repo} | {cell(action, 110)} | {cell(recheck, 120)} |")
    if not rows:
        out.append("| — | — | — | — | нет действий (нет репозиториев с ролями записи) | — | — | — |")
    if blocked:
        out += ["", f"Без независимой перепроверки (или второй проверки правовых норм): {blocked}. Сначала "
                "`recheck.py run <RUN_DIR>` / `recheck.py set …` / `recheck.py legal …`, затем `recheck.py gate <RUN_DIR>`."]
    return out


def build_report(run):
    r, cfg = run.run, run.config
    fs = run.findings
    host = re.sub(r"^https?://|/.*$", "", r.get("site") or (cfg.get("site") or {}).get("start_urls", [""])[0])
    date = (r.get("id") or "")[:10] or (r.get("started_at") or "")[:10]
    dev = cfg.get("devices") or {}
    vps = ", ".join(f"{v.get('name')} {v.get('width')}×{v.get('height')}" for v in dev.get("viewports") or [] if isinstance(v, dict))
    sev = Counter(f.get("severity") for f in fs)
    st = Counter(f.get("status") or "NEW" for f in fs)
    L = [f"# QA-аудит {host} — {date}", "",
         f"**Режим:** {r.get('mode') or cfg.get('mode', '—')} · **Глубина:** {r.get('depth') or cfg.get('depth', '—')} · "
         f"**Охват:** {(cfg.get('scope') or {}).get('type', '—')} · **Находок:** {len(fs)}",
         f"**Устройства:** {vps or '—'} · **Браузеры:** {', '.join(dev.get('browsers') or []) or '—'} · "
         f"**Авторизация:** {(cfg.get('auth') or {}).get('mode', '—')}",
         f"**Начало:** {r.get('started_at', '—')} · **Конец:** {r.get('finished_at', '—')} · **Папка прогона:** `{run.dir}`", "",
         "## Итог", ""]
    L.append("- Находки по severity: " + (", ".join(f"{s} {sev[s]}" for s in SEVERITIES if sev[s]) or "нет") + ".")
    L.append("- По статусам: " + (", ".join(f"{s} {st[s]}" for s in STATUSES if st[s]) or "нет") + ".")
    if run.rechecks:
        rs = Counter(x.get("status") or "без результата" for x in run.rechecks)
        L.append(f"- Перепроверено заявленных исправлений: {len(run.rechecks)} (" +
                 ", ".join(f"{k} {v}" for k, v in sorted(rs.items())) + ").")
    nc = (run.data.get("not_checked") or []) if isinstance(run.data, dict) else []
    L.append(f"- Не проверено пунктов: {len(nc)}." + (" Есть побочные эффекты — см. раздел ниже." if run.side_effects else ""))
    L += ["", "## Статистика", "", "| Severity | Всего | " + " | ".join(STATUSES) + " |",
          "|---|---|" + "---|" * len(STATUSES)]
    for s in SEVERITIES:
        row = [f for f in fs if f.get("severity") == s]
        c = Counter(f.get("status") or "NEW" for f in row)
        L.append(f"| {s.capitalize()} | {len(row)} | " + " | ".join(str(c[x] or "") for x in STATUSES) + " |")
    L += ["", "## По направлениям", "", "| Направление | Находок | Главное |", "|---|---|---|"]
    byd = defaultdict(list)
    for f in fs:
        byd[f.get("direction")].append(f)
    for d, items in sorted(byd.items(), key=lambda x: -len(x[1])):
        top = min(items, key=lambda f: SEVERITIES.index(f.get("severity")) if f.get("severity") in SEVERITIES else 9)
        L.append(f"| {d} | {len(items)} | {cell(top.get('title'), 100)} |")
    L += ["", "## Находки", "", "| ID | Severity | Статус | Заголовок | URL | Куда опубликовано |", "|---|---|---|---|---|---|"]
    for f in fs:
        pub = ", ".join(f"{p.get('repo')}#{p.get('number')}" if p.get("number") else f"{p.get('kind')}" for p in f.get("published") or [])
        L.append(f"| {f['id']} | {f.get('severity')} | {f.get('status') or 'NEW'} | {cell(f.get('title'), 100)} | "
                 f"{cell(f.get('url'), 80)} | {pub or '—'} |")
    if run.rechecks:
        L += ["", "## Перепроверка заявленных исправлений", ""] + recheck_table(run)
    L += ["", "## Что не проверено и почему", "", "| Что | Причина |", "|---|---|"]
    L += [f"| {cell(x.get('what'))} | {cell(x.get('reason'))}{' (' + x['rule'] + ')' if x.get('rule') else ''} |" for x in nc] \
        or ["| — | — |"]
    if run.blocked:
        L += ["", "## Сработавшие запреты", "", "| Правило | Сколько раз | Пример |", "|---|---|---|"]
        g = defaultdict(list)
        for b in run.blocked:
            g[b.get("rule") or b.get("reason") or "?"].append(b)
        for rule, items in sorted(g.items(), key=lambda x: -len(x[1])):
            ex = items[0]
            L.append(f"| {cell(rule, 60)} | {len(items)} | {cell(ex.get('url') or ex.get('name') or ex.get('text') or '', 100)} |")
    if run.side_effects:
        body = re.sub(r"^(#+) ", lambda m: "#" * min(len(m.group(1)) + 2, 6) + " ", run.side_effects.strip(), flags=re.M)
        L += ["", "## Побочные эффекты (side_effects.md)", "", body]
    if run.repos():
        L += ["", "## Публикация", ""] + publish_table(run)
    L += ["", f"<!-- site-qa-audit:run={r.get('id', '')} -->"]
    return "\n".join(L).rstrip() + "\n"


def build_summary(run):
    head = build_report(run).split("\n## Находки", 1)[0].rstrip()
    return head + "\n\nПолный отчёт — `report.md` рядом с этим файлом.\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["report", "summary", "publish-table"])
    ap.add_argument("run_dir")
    ap.add_argument("--findings")
    ap.add_argument("--config")
    ap.add_argument("--rechecks")
    ap.add_argument("--registry")
    ap.add_argument("--side-effects")
    ap.add_argument("--out")
    a = ap.parse_args()
    run = Run(a)
    if a.cmd == "report":
        text = build_report(run)
    elif a.cmd == "summary":
        text = build_summary(run)
    else:
        text = "\n".join(publish_table(run)) + "\n"
    out = a.out or (str(Path(a.run_dir) / f"{a.cmd}.md") if a.cmd in ("report", "summary") else None)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
        print(f"{a.cmd}: -> {out}")
    else:
        print(text, end="")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
