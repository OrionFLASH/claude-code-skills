#!/usr/bin/env python3
"""report.md, summary.md and the pre-publication table from the run folder (references/run-files.md).

  build_report.py report RUN_DIR [--out RUN_DIR/report.md]
  build_report.py summary RUN_DIR [--out RUN_DIR/summary.md]
  build_report.py publish-table RUN_DIR [--out FILE]

Sources in RUN_DIR (missing optional files are skipped): findings.json (required), run-config.yaml, apk-info.json,
device-matrix.json, stands.json, raw/metrics.jsonl, raw/crashes-*.json, logs/blocked.jsonl.
Exit codes: 0 ok, 2 no findings.json.
"""
import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
import miniyaml  # noqa: E402
import qa_recheck  # noqa: E402 — publication gate: independent re-check, legal second check

SEVERITIES = ["critical", "high", "medium", "low", "info"]
STATUSES = ["NEW", "DUPLICATE-OPEN", "FIXED-INSUFFICIENT", "REGRESSION", "ALREADY-COPIED", "UNSURE-MATCH", "FIXED-OK",
            "NOT-CHECKED"]


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def jsonl(path):
    out = []
    p = Path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def cell(text, limit=160):
    text = re.sub(r"\s+", " ", str(text if text is not None else "")).strip().replace("|", "\\|")
    return text if len(text) <= limit else text[:limit - 1] + "…"


def norm_repo(r):
    return re.sub(r"^https?://github\.com/|\.git$|/$", "", r or "")


class Run:
    def __init__(self, run_dir):
        d = Path(run_dir)
        self.dir = d
        self.data = load_json(d / "findings.json")
        if self.data is None:
            sys.stderr.write("build_report: нет findings.json\n")
            sys.exit(2)
        self.findings = self.data.get("findings", []) if isinstance(self.data, dict) else self.data
        self.run = self.data.get("run", {}) if isinstance(self.data, dict) else {}
        self.config = miniyaml.load_file(d / "run-config.yaml") if (d / "run-config.yaml").exists() else {}
        self.apk = load_json(d / "apk-info.json", {}) or {}
        self.matrix = load_json(d / "device-matrix.json", {}) or {}
        self.stands = load_json(d / "stands.json", {}) or {}
        self.metrics = jsonl(d / "raw" / "metrics.jsonl")
        self.crashes, self.other_crashes = [], []
        for p in sorted((d / "raw").glob("crashes-*.json")) if (d / "raw").is_dir() else []:
            data = load_json(p, []) or []
            # 1.0.1: {"package", "items", "other_processes"}; 1.0.0: a list of items
            items, others = (data.get("items") or [], data.get("other_processes") or []) if isinstance(data, dict) else (data, [])
            for lst, target in ((items, self.crashes), (others, self.other_crashes)):
                for x in lst:
                    if isinstance(x, dict):
                        x["serial"] = p.stem.replace("crashes-", "")
                        target.append(x)
        self.blocked = jsonl(d / "logs" / "blocked.jsonl")

    def repos(self):
        return [r for r in self.config.get("repos") or [] if isinstance(r, dict)]


def header(run):
    r, cfg, apk = run.run, run.config, run.apk
    pkg = r.get("app") or apk.get("package") or (cfg.get("app") or {}).get("package") or "?"
    label = apk.get("label") or pkg
    ver = r.get("app_version") or (f"{apk.get('version_name')} ({apk.get('version_code')})" if apk.get("version_name") else "")
    date = (r.get("id") or "")[:10] or (r.get("started_at") or "")[:10]
    m = run.matrix
    apis = ", ".join(str(x) for x in m.get("apis") or [])
    src = apk.get("source") or {}
    files = src.get("copies") or src.get("files") or []
    L = [f"# QA Android: {label} (`{pkg}`) {ver} — {date}".rstrip(), "",
         f"**Режим:** {r.get('mode') or cfg.get('mode', '—')} · **Глубина:** {r.get('depth') or cfg.get('depth', '—')} · "
         f"**Находок:** {len(run.findings)} · **minSdk/targetSdk:** {apk.get('min_sdk', '—')}/{apk.get('target_sdk', '—')}",
         f"**Стенды:** {len(m.get('cells') or [])} ячеек матрицы, API {apis or '—'}, потоков {len(m.get('threads') or []) or '—'} · "
         f"**Эмуляторов запущено:** {len(run.stands.get('emulators') or [])}, AVD создано: {len(run.stands.get('avds_created') or [])}",
         f"**APK:** " + (", ".join(f"{x.get('file', '').split('/')[-1]} sha256 {str(x.get('sha256', ''))[:12]}…" for x in files[:3]) or "—")
         + f" · **Начало:** {r.get('started_at', '—')} · **Конец:** {r.get('finished_at', '—')} · **Папка прогона:** `{run.dir}`"]
    return L


def summary_block(run):
    fs = run.findings
    sev = Counter(f.get("severity") for f in fs)
    st = Counter(f.get("status") or "NEW" for f in fs)
    crashes = [f for f in fs if f.get("type") in ("crash", "anr") or f.get("crash")]
    nc = (run.data.get("not_checked") or []) if isinstance(run.data, dict) else []
    L = ["## Итог", "",
         "- Находки по severity: " + (", ".join(f"{s} {sev[s]}" for s in SEVERITIES if sev[s]) or "нет") + ".",
         "- По статусам: " + (", ".join(f"{s} {st[s]}" for s in STATUSES if st[s]) or "нет") + ".",
         f"- Падения и ANR в находках: {len(crashes)}; в журналах устройств: {len(run.crashes)}.",
         f"- Не проверено пунктов: {len(nc)}; сработавших запретов: {len(run.blocked)}."]
    goal = (run.config.get("goal") or {}).get("success")
    if goal == "release-gate":
        blockers = [f for f in fs if f.get("severity") in ("critical", "high") and (f.get("status") or "NEW") in ("NEW", "REGRESSION")]
        L.append(f"- Готовность к релизу: {'блокеры есть — ' + str(len(blockers)) if blockers else 'блокеров (critical/high NEW, REGRESSION) нет'}.")
    L += ["", "## Статистика", "", "| Severity | Всего | " + " | ".join(STATUSES) + " |", "|---|---|" + "---|" * len(STATUSES)]
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
    if not byd:
        L.append("| — | 0 | — |")
    return L


def matrix_block(run):
    cells = run.matrix.get("cells") or []
    if not cells:
        return []
    by_cell = Counter((f.get("environment") or {}).get("cell") for f in run.findings)
    L = ["", "## Матрица стендов", "", "| Ячейка | API | Железо | Вариации | Стенд | Находок |", "|---|---|---|---|---|---|"]
    for c in cells:
        st = c.get("stand") or {}
        L.append(f"| {c['id']} | {cell(c.get('label'), 30)} | {cell(c.get('hardware_label'), 50)} | {cell(', '.join(c.get('variants') or []), 80)} | "
                 f"`{st.get('name') or st.get('serial') or '—'}` | {by_cell.get(c['id'], 0)} |")
    return L


def metrics_block(run):
    if not run.metrics:
        return []
    L = ["", "## Метрики", "", "| Метрика | Устройство | Значение |", "|---|---|---|"]
    for m in run.metrics:
        name, serial = m.get("metric"), m.get("serial", "")
        if name and name.startswith("start-"):
            val = f"медиана {m.get('median_ms')} мс (мин {m.get('min_ms')}, макс {m.get('max_ms')}, {m.get('runs')} запусков)"
        elif name == "meminfo":
            val = f"PSS {round((m.get('total_pss_kb') or 0) / 1024)} МБ, Java {round((m.get('java_heap_kb') or 0) / 1024)} МБ, " \
                  f"Native {round((m.get('native_heap_kb') or 0) / 1024)} МБ, Activities {m.get('activities', '—')}"
        elif name == "gfxinfo":
            val = f"кадров {m.get('frames', '—')}, jank {m.get('janky_percent', '—')} %, p90 {m.get('p90_ms', '—')} мс, p99 {m.get('p99_ms', '—')} мс"
        elif name == "size":
            val = f"APK на устройстве {round((m.get('apk_bytes_on_device') or 0) / 2 ** 20, 1)} МБ" + \
                  (f", данные {round(m['data_bytes'] / 2 ** 20, 1)} МБ" if m.get("data_bytes") else "")
        else:
            val = cell(json.dumps({k: v for k, v in m.items() if k not in ("metric", "serial", "time")}, ensure_ascii=False), 120)
        L.append(f"| {name} | {serial} | {val} |")
    starts = [m["median_ms"] for m in run.metrics if m.get("metric") == "start-cold" and m.get("median_ms")]
    if starts:
        L.append(f"\nХолодный запуск, медиана по стендам: {int(statistics.median(starts))} мс "
                 "(ориентир Android vitals: > 5 с — чрезмерно).")
    return L


def crashes_block(run):
    rows = [f for f in run.findings if f.get("type") in ("crash", "anr") or f.get("crash")]
    if not rows and not run.crashes and not run.other_crashes:
        return []
    L = ["", "## Падения и ANR", "", "| Тип | Где | Сводка | Находка |", "|---|---|---|---|"]
    for f in rows:
        c = f.get("crash") or {}
        L.append(f"| {c.get('type') or f.get('type')} | {cell(f.get('screen'), 50)} | {cell(c.get('summary') or f.get('title'), 100)} | {f['id']} |")
    seen = {(f.get("crash") or {}).get("summary") for f in rows}
    for x in run.crashes:
        if x.get("summary") in seen:
            continue
        L.append(f"| {x.get('type')} | {x.get('serial')} {x.get('time', '')} | {cell(x.get('summary'), 100)} | — (не оформлено) |")
    if run.other_crashes:
        L += ["", f"Падения других процессов — не приложения, в итог не входят ({len(run.other_crashes)}):", "",
              "| Тип | Процесс | Чей | Сводка |", "|---|---|---|---|"]
        for x in run.other_crashes[:20]:
            who = (x.get("note") or x.get("owner") or "") + ("; запущен для приложения — проверить" if x.get("related_to_app") else "")
            proc = x.get("process") or f"pid {x.get('pid') or '?'}"
            if x.get("thread"):
                proc += f" / поток {x['thread']}"
            L.append(f"| {x.get('type')} | {cell(proc, 60)} | {cell(who, 80)} | {cell(x.get('summary'), 80)} |")
    return L


def apk_block(run):
    risks = run.apk.get("risks") or []
    if not risks:
        return []
    L = ["", "## Пассивная проверка APK (кандидаты)", "", "| Проверка | Severity | Что |", "|---|---|---|"]
    L += [f"| `{r['check_id']}` | {r['severity']} | {cell(r['title'], 120)} |" for r in risks]
    return L


def build_report(run):
    fs = run.findings
    L = header(run) + [""] + summary_block(run) + matrix_block(run) + crashes_block(run) + metrics_block(run)
    L += ["", "## Находки", "", "| ID | Severity | Статус | Заголовок | Экран | Окружение | Куда опубликовано |", "|---|---|---|---|---|---|---|"]
    for f in fs:
        env = f.get("environment") or {}
        where = ", ".join(x for x in [f"API {env['api']}" if env.get("api") else "", env.get("device_profile") or "",
                                      env.get("cell") or ""] if x)
        pub = ", ".join(f"{p.get('repo')}#{p.get('number')}" if p.get("number") else str(p.get("kind")) for p in f.get("published") or [])
        L.append(f"| {f['id']} | {f.get('severity')} | {f.get('status') or 'NEW'} | {cell(f.get('title'), 100)} | "
                 f"{cell((f.get('screen') or '').split('.')[-1], 40)} | {cell(where, 60)} | {pub or '—'} |")
    if not fs:
        L.append("| — | — | — | находок нет | — | — | — |")
    L += apk_block(run)
    nc = (run.data.get("not_checked") or []) if isinstance(run.data, dict) else []
    L += ["", "## Что не проверено и почему", "", "| Что | Причина |", "|---|---|"]
    L += [f"| {cell(x.get('what'))} | {cell(x.get('reason'))}{' (' + x['rule'] + ')' if x.get('rule') else ''} |" for x in nc] or ["| — | — |"]
    if run.blocked:
        L += ["", "## Сработавшие запреты", "", "| Правило | Сколько раз | Пример |", "|---|---|---|"]
        g = defaultdict(list)
        for b in run.blocked:
            g[b.get("rule") or "?"].append(b)
        for rule, items in sorted(g.items(), key=lambda x: -len(x[1])):
            t = items[0].get("target") or {}
            ex = t.get("text") or t.get("adb") or t.get("package") or items[0].get("reason") if isinstance(t, dict) else str(t)
            L.append(f"| {cell(rule, 60)} | {len(items)} | {cell(ex, 100)} |")
    if run.repos():
        L += ["", "## Публикация", ""] + publish_table(run)
    L += ["", f"<!-- android-qa-audit:run={run.run.get('id', '')} -->"]
    return "\n".join(L).rstrip() + "\n"


def build_summary(run):
    L = header(run) + [""] + summary_block(run)
    return "\n".join(L).rstrip() + "\n\nПолный отчёт — `report.md` рядом с этим файлом.\n"


def plan_actions(run):
    rows = []
    for f in run.findings:
        st = f.get("status") or "NEW"
        for r in run.repos():
            repo = norm_repo(r.get("url") or r.get("repo"))
            roles = r.get("roles") or []
            roles = [roles] if isinstance(roles, str) else roles
            label = (r.get("severity_map") or {}).get(f.get("severity")) or f.get("severity")
            refs = [m for m in f.get("matches") or [] if norm_repo(m.get("repo")) == repo]
            if (f.get("evidence") or {}).get("sensitive"):
                action = "не публиковать без решения: чувствительная находка"
            elif st in ("FIXED-INSUFFICIENT", "REGRESSION") and refs:
                action = f"комментарий в #{refs[0].get('number')}" if "comment" in roles else f"нет роли comment (#{refs[0].get('number')})"
            elif st in ("FIXED-OK", "NOT-CHECKED"):
                action = "только отчёт"
            elif st == "UNSURE-MATCH":
                action = "вопрос пользователю"
            elif st == "DUPLICATE-OPEN" and refs:
                action = f"пропуск: дубль #{refs[0].get('number')}" + ("; копия со ссылкой" if "copies" in roles else "")
            elif st == "ALREADY-COPIED":
                action = "пропуск: уже есть"
            elif "copies" in roles:
                action = "копия (templates/issue-detailed.md)"
            elif "write-new" in roles and st == "NEW":
                action = "issue (их шаблон или issue-detailed.md)"
            else:
                continue
            rows.append((f, repo, label, action))
    return rows


def publish_table(run):
    rows = plan_actions(run)
    mode = run.run.get("mode") or run.config.get("mode") or "dry-run"
    out = [f"Режим: **{mode}** — " + ("только черновики в drafts/" if mode != "live" else "публикация после «да» по этой таблице"), "",
           "| № | ID | Статус | Severity | Заголовок | Куда | Действие | Перепроверка |", "|---|---|---|---|---|---|---|---|"]
    blocked = 0
    for n, (f, repo, label, action) in enumerate(rows, 1):
        problems = qa_recheck.gate_problems(f)
        if problems and not re.match(r"^(пропуск|только отчёт|вопрос|нет роли|не публиковать)", action):
            action += " — НЕ публиковать до перепроверки"
            blocked += 1
        rc = f.get("recheck") or {}
        recheck = ("да" + (f" ({rc.get('by')})" if rc.get("by") else "")) if not problems else "нет: " + "; ".join(problems)
        out.append(f"| {n} | {f['id']} | {f.get('status') or 'NEW'} | {cell(label, 30)} | {cell(f.get('title'), 90)} | {repo} | "
                   f"{cell(action, 110)} | {cell(recheck, 120)} |")
    if not rows:
        out.append("| — | — | — | — | нет действий (нет репозиториев с ролями записи) | — | — | — |")
    if blocked:
        out += ["", f"Без независимой перепроверки (или второй проверки правовых норм): {blocked}. Сначала "
                "`recheck.py run <RUN_DIR> --subst SERIAL=…` / `recheck.py set …` / `recheck.py legal …`, затем `recheck.py gate <RUN_DIR>`."]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["report", "summary", "publish-table"])
    ap.add_argument("run_dir")
    ap.add_argument("--out")
    a = ap.parse_args()
    run = Run(a.run_dir)
    text = build_report(run) if a.cmd == "report" else build_summary(run) if a.cmd == "summary" else "\n".join(publish_table(run)) + "\n"
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
