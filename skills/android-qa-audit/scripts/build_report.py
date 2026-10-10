#!/usr/bin/env python3
"""report.md, summary.md and the pre-publication table from the run folder (references/run-files.md).

  build_report.py report RUN_DIR [--out RUN_DIR/report.md]
  build_report.py summary RUN_DIR [--out RUN_DIR/summary.md]
  build_report.py publish-table RUN_DIR [--out FILE]

Sources in RUN_DIR (missing optional files are skipped): findings.json (required), run-config.yaml, apk-info.json,
device-matrix.json, stands.json, raw/metrics.jsonl, raw/crashes-*.json, raw/soak-*.json (long scenarios: status,
duration, PSS, events, host load), logs/blocked.jsonl. Metrics taken while other emulators were running are marked.
«Ролики находок» (1.5.0): findings[].clips and soak clips (--clips-on-crash) — finding, kind, duration, size, viewed, link.
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
            "NOT-CHECKED", "KNOWN"]
SOAK_STATUS = {"ok": "прошёл", "interrupted": "прервался (находка)", "result-mismatch": "итог не совпал (находка)",
               "invalid": "НЕДЕЙСТВИТЕЛЕН — предусловие не выполнено", "stopped": "остановлен", "failed": "ошибка скрипта"}


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
        self.soaks = [x for x in (load_json(p, None) for p in sorted((d / "raw").glob("soak-*.json"))) if isinstance(x, dict)] \
            if (d / "raw").is_dir() else []

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
    busy = 0
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
            val = cell(json.dumps({k: v for k, v in m.items() if k not in ("metric", "serial", "time", "host")},
                                  ensure_ascii=False), 120)
        emus = (m.get("host") or {}).get("emulators_running")
        if emus and emus > 1:
            val += f" ⚠ рядом работало эмуляторов: {emus}"
            busy += 1
        L.append(f"| {name} | {serial} | {val} |")
    starts = [m["median_ms"] for m in run.metrics if m.get("metric") == "start-cold" and m.get("median_ms")]
    if starts:
        L.append(f"\nХолодный запуск, медиана по стендам: {int(statistics.median(starts))} мс "
                 "(ориентир Android vitals: > 5 с — чрезмерно).")
    if busy:
        L.append(f"\n⚠ {busy} замер(ов) сделано при нескольких работающих эмуляторах: время и плавность искажены "
                 "нагрузкой хоста — для выводов о скорости повторить на свободном хосте (parallelism.md).")
    return L


SPARK = "▁▂▃▄▅▆▇█"
LOSS_EVENTS = ("process-died", "service-lost", "process-restarted")


def soak_samples(run, s):
    """Points (minutes, PSS MB) of a soak run from its raw/soak-*.jsonl (the path in the summary, or the same name in
    this run's raw/ when the run folder was moved)."""
    cands = [Path(s["file"])] if s.get("file") else []
    if s.get("file"):
        cands.append(run.dir / "raw" / Path(s["file"]).name)
    for p in cands:
        if p.is_file():
            return [(round(x["t_s"] / 60, 2), round(x["pss_kb"] / 1024, 1)) for x in jsonl(p)
                    if isinstance(x.get("t_s"), (int, float)) and x.get("pss_kb")]
    return []


def sparkline(values, width=12):
    """Text chart for a table cell: `width` bars (means of equal chunks), ▁ — minimum, █ — maximum."""
    if len(values) < 2:
        return ""
    n = min(width, len(values))
    chunks = [values[i * len(values) // n:(i + 1) * len(values) // n] for i in range(n)]
    means = [sum(c) / len(c) for c in chunks if c]
    lo, hi = min(means), max(means)
    return "".join(SPARK[0] if hi == lo else SPARK[min(7, int((v - lo) / (hi - lo) * 8))] for v in means)


def nice_ticks(lo, hi, count=5):
    """Round axis ticks covering [lo, hi]: (start, stop, step)."""
    import math
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / count
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    return math.floor(lo / step) * step, math.ceil(hi / step) * step, step


def _fmt(v):
    return f"{v:g}" if abs(v) >= 10 or v == int(v) else f"{v:.1f}"


def pss_svg(points, events=(), title=""):
    """PSS over time as a standalone SVG (stdlib only): one line, recessive grid, loss events as labelled vertical
    lines, screen-off periods as a grey band, a hover title on each point (≤ 200). Light and dark themes (CSS
    variables; plain colours in the attributes are the fallback for viewers without CSS)."""
    from xml.sax.saxutils import escape, quoteattr
    W, H, L, R, T, B = 720, 290, 56, 16, 44, 40
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    x0, x1, xstep = nice_ticks(0, max(xs) or 1, 6)
    pad = max(1.0, (max(ys) - min(ys)) * 0.1)
    y0, y1, ystep = nice_ticks(max(0.0, min(ys) - pad), max(ys) + pad, 4)
    sx = lambda v: L + (v - x0) / ((x1 - x0) or 1) * (W - L - R)  # noqa: E731
    sy = lambda v: H - B - (v - y0) / ((y1 - y0) or 1) * (H - T - B)  # noqa: E731
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
         f'aria-label={quoteattr(title)}>',
         "<style>svg{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;"
         "--line:#2a78d6;--crit:#d03b3b}"
         "@media (prefers-color-scheme: dark){svg{--bg:#1a1a19;--ink:#ffffff;--ink2:#c3c2b7;--grid:#2c2c2a;"
         "--axis:#383835;--line:#3987e5}}"
         "text{font:12px system-ui,-apple-system,'Segoe UI',Arial,sans-serif;fill:var(--ink2)}"
         ".t{font-size:13px;font-weight:600;fill:var(--ink)}.m{fill:var(--muted)}.e{fill:var(--ink)}"
         ".bg{fill:var(--bg)}.band{fill:var(--grid)}.grid{stroke:var(--grid)}.axis{stroke:var(--axis)}"
         ".ln{stroke:var(--line)}.dot{fill:var(--line);stroke:var(--bg)}.crit{stroke:var(--crit)}</style>",
         f'<rect class="bg" fill="#fcfcfb" width="{W}" height="{H}"/>',
         f'<text class="t" fill="#0b0b0b" x="{L}" y="20">{escape(title)}</text>']

    def band(a, b, label):
        o.append(f'<rect class="band" fill="#e1e0d9" opacity="0.6" x="{sx(a):.1f}" y="{T}" '
                 f'width="{max(1.0, sx(b) - sx(a)):.1f}" height="{H - T - B}"><title>{escape(label)}</title></rect>')
        if sx(b) - sx(a) >= 70:
            o.append(f'<text class="m" fill="#898781" x="{sx(a) + 4:.1f}" y="{H - B - 6}">экран выкл.</text>')
    off = None
    for ev in sorted(events, key=lambda ev: ev.get("t_s", 0)):     # screen-off periods — background band
        m = ev.get("t_s", 0) / 60
        if ev.get("event") == "screen-off":
            off = m
        elif ev.get("event") == "screen-on" and off is not None:
            band(off, m, f"экран выключен {off:.1f}–{m:.1f} мин")
            off = None
    if off is not None:
        band(off, max(xs[-1], off), f"экран выключен с {off:.1f} мин")
    v = y0
    while v <= y1 + ystep / 2:
        o.append(f'<line class="grid" stroke="#e1e0d9" stroke-width="1" x1="{L}" x2="{W - R}" y1="{sy(v):.1f}" '
                 f'y2="{sy(v):.1f}"/>')
        o.append(f'<text fill="#52514e" x="{L - 6}" y="{sy(v) + 4:.1f}" text-anchor="end">{_fmt(v)}</text>')
        v += ystep
    v = x0
    while v <= x1 + xstep / 2:
        o.append(f'<text fill="#52514e" x="{sx(v):.1f}" y="{H - B + 16}" text-anchor="middle">{_fmt(v)}</text>')
        v += xstep
    o.append(f'<line class="axis" stroke="#c3c2b7" stroke-width="1" x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}"/>')
    o.append(f'<text class="m" fill="#898781" x="{W - R}" y="{H - 6}" text-anchor="end">минуты</text>')
    o.append(f'<text class="m" fill="#898781" x="{L - 6}" y="{T - 14}" text-anchor="end">PSS, МБ</text>')
    losses = [ev for ev in events if ev.get("event") in LOSS_EVENTS]
    for i, ev in enumerate(losses[:6]):
        m = ev.get("t_s", 0) / 60
        x = sx(m)
        o.append(f'<line class="crit" stroke="#d03b3b" stroke-width="1.5" stroke-dasharray="4 3" x1="{x:.1f}" '
                 f'x2="{x:.1f}" y1="{T}" y2="{H - B}"/>')
        anchor, dx = ("end", -4) if x > W - R - 160 else ("start", 4)
        o.append(f'<text class="e" fill="#0b0b0b" x="{x + dx:.1f}" y="{T + 12 + 14 * i}" text-anchor="{anchor}">'
                 f'✕ {escape(ev["event"])} {m:.1f} мин</text>')
    path = " ".join(f"{'M' if i == 0 else 'L'}{sx(x):.1f},{sy(y):.1f}" for i, (x, y) in enumerate(points))
    o.append(f'<path class="ln" stroke="#2a78d6" d="{path}" fill="none" stroke-width="2" stroke-linejoin="round" '
             f'stroke-linecap="round"/>')
    step = max(1, len(points) // 200)
    for x, y in points[::step]:
        o.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="5" fill="transparent"><title>{x:g} мин — {y:g} МБ'
                 f'</title></circle>')
    lx, ly = points[-1]
    o.append(f'<circle class="dot" fill="#2a78d6" stroke="#fcfcfb" stroke-width="2" r="4" cx="{sx(lx):.1f}" '
             f'cy="{sy(ly):.1f}"/>')
    o.append(f'<text class="e" fill="#0b0b0b" x="{min(sx(lx), W - R - 4):.1f}" y="{sy(ly) - 9:.1f}" '
             f'text-anchor="end">{_fmt(ly)} МБ</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


def long_runs_block(run, charts_dir=None, rel_base=None):
    """«Длинные сценарии»: soak runs (adb_helpers.py soak) — status, duration, result, PSS (with a text sparkline and
    an SVG chart per run in charts_dir, linked relative to rel_base), events, host load."""
    if not run.soaks:
        return []
    L = ["", "## Длинные сценарии", "", "| Сценарий | Стенд | Статус | Длительность | Итог | PSS, МБ (мин–макс, рост/ч) | "
         "События | Хост |", "|---|---|---|---|---|---|---|---|"]
    invalid = 0
    charts = []
    for s in run.soaks:
        pts = soak_samples(run, s)
        spark = sparkline([p[1] for p in pts])
        if charts_dir is not None and len(pts) >= 2:
            name = Path(s.get("file") or f"soak-{s.get('tag')}-{s.get('serial')}.jsonl").stem + "-pss.svg"
            Path(charts_dir).mkdir(parents=True, exist_ok=True)
            title = f"PSS: {s.get('tag')} · {s.get('serial')} · {SOAK_STATUS.get(s.get('status'), s.get('status'))}"
            (Path(charts_dir) / name).write_text(pss_svg(pts, s.get("events") or [], title), encoding="utf-8")
            link = Path(charts_dir, name)
            try:
                link = link.relative_to(rel_base) if rel_base else link
            except ValueError:
                pass
            charts.append(f"![{cell(title, 100)}]({link.as_posix()})")
        res = s.get("result") or {}
        sd, fd = res.get("screen_duration") or {}, res.get("file") or {}
        itog = "; ".join(x for x in [
            f"на экране {sd['text']}" + (" ✓" if sd.get("ok") else " ✗") if sd.get("text") else "",
            f"файл {fd['seconds']} с" + (" ✓" if fd.get("ok") else " ✗") if fd.get("seconds") is not None else "",
            fd.get("reason") or "", sd.get("reason") or ""] if x) or "—"
        pss = (f"{s.get('pss_min_mb', '—')}–{s.get('pss_max_mb', '—')}"
               + (f", {s['pss_growth_mb_per_hour']:+}" if s.get("pss_growth_mb_per_hour") is not None else "")) \
            if s.get("pss_max_mb") is not None else "—"
        pss += f" {spark}" if spark else ""
        ev = ", ".join(f"{e['event']} {round(e['t_s'] / 60, 1)} мин" for e in s.get("events") or []
                       if e.get("event") not in ("screen-off", "screen-on")) or "—"
        scr = [e for e in s.get("events") or [] if e.get("event") in ("screen-off", "screen-on")]
        if scr:
            ev += " (экран: " + ", ".join(f"{e['event'].split('-')[1]} {round(e['t_s'] / 60, 1)}" for e in scr) + ")"
        host = s.get("host") or {}
        hst = f"эмуляторов {host.get('emulators_max') or '?'}, load {host.get('load1_max') or '?'}/{host.get('cpus') or '?'}"
        st = SOAK_STATUS.get(s.get("status"), s.get("status"))
        if s.get("status") == "invalid":
            invalid += 1
        L.append(f"| {cell(s.get('tag'), 30)} | {s.get('serial')} | {st} | {s.get('minutes_actual')} из {s.get('minutes_planned')} мин | "
                 f"{cell(itog, 80)} | {pss} | {cell(ev, 90)} | {hst} |")
    if invalid:
        L.append(f"\nНедействительных прогонов: {invalid} — о приложении ничего не говорят (не выполнено предусловие после "
                 "старта), в выводы не входят; причина — raw/soak-*.json → reason.")
    if any((s.get("host") or {}).get("emulators_max") and s["host"]["emulators_max"] > 1 for s in run.soaks):
        L.append("\nПри нескольких эмуляторах на хосте время обработки (расшифровка, экспорт) искажено; память и "
                 "стабильность — достоверны.")
    if charts:
        L += ["", "PSS по времени (красный пунктир — смерть процесса / потеря сервиса, серая полоса — экран выключен; "
                  "точки — `raw/soak-*.jsonl`):", ""] + [x + "\n" for x in charts]
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


CLIP_KIND = {"error": "ошибка", "ok": "работает", "note": "пояснение", "after": "после исправления"}


def clips_block(run, base):
    """«Ролики находок»: findings[].clips (+ clips saved by soak --clips-on-crash), links relative to report.md."""
    import os
    rows = []
    for f in run.findings:
        for c in f.get("clips") or []:
            if isinstance(c, dict) and c.get("file"):
                rows.append((f["id"], c))
    linked = {c.get("file") for _, c in rows}
    for s in run.soaks:
        for e in s.get("clips") or []:
            if isinstance(e, dict) and e.get("file") and e["file"] not in linked:
                rows.append((f"soak {s.get('tag')} ({e.get('event') or 'падение'})", e))
    if not rows:
        return []
    L = ["", "## Ролики находок", "", "| Находка | Вид | Длительность | Размер | Просмотрен | Подпись | Ролик |", "|---|---|---|---|---|---|---|"]
    for fid, c in rows:
        try:
            rel = os.path.relpath(str((run.dir / c["file"]).resolve()), str(base)).replace(os.sep, "/")
        except ValueError:                       # another drive (Windows)
            rel = str((run.dir / c["file"]).resolve())
        secs = f"{c['seconds']:.1f} с".replace(".", ",") if isinstance(c.get("seconds"), (int, float)) else "—"
        size = f"{c['bytes'] / 1048576:.2f} МБ".replace(".", ",") if isinstance(c.get("bytes"), (int, float)) else "—"
        warn = " ⚠ " + cell(c["warning"], 60) if c.get("warning") else ""
        L.append(f"| {fid} | {CLIP_KIND.get(c.get('kind'), c.get('kind') or '—')} | {secs} | {size} | "
                 f"{'да' if c.get('viewed') else 'нет — не публикуется'} | {cell(c.get('caption'), 70)}{warn} | [{Path(c['file']).name}]({rel}) |")
    L += ["", "Звук в роликах не пишется; в черновики issues попадают только просмотренные (лента кадров, `finding.py clip-viewed`)."]
    return L


def apk_block(run):
    risks = run.apk.get("risks") or []
    if not risks:
        return []
    L = ["", "## Пассивная проверка APK (кандидаты)", "", "| Проверка | Severity | Что |", "|---|---|---|"]
    L += [f"| `{r['check_id']}` | {r['severity']} | {cell(r['title'], 120)} |" for r in risks]
    return L


def build_report(run, out=None):
    """out — where report.md goes: PSS charts are written to <its folder>/charts/ and linked relatively."""
    fs = run.findings
    base = Path(out).resolve().parent if out else run.dir.resolve()
    L = header(run) + [""] + summary_block(run) + matrix_block(run) + crashes_block(run) + metrics_block(run) + \
        long_runs_block(run, base / "charts", base)
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
    L += clips_block(run, base)
    L += apk_block(run)
    nc = (run.data.get("not_checked") or []) if isinstance(run.data, dict) else []
    L += ["", "## Что не проверено и почему", "", "| Что | Причина |", "|---|---|"]
    L += [f"| {cell(x.get('what'))} | {cell(x.get('reason'))}{' (' + x['rule'] + ')' if x.get('rule') else ''} |" for x in nc] or ["| — | — |"]
    known = [f for f in fs if f.get("status") == "KNOWN"]
    if known:
        L += ["", "## Уже известно (документы проекта)", "", "| ID | Заголовок | Документ | Цитата |", "|---|---|---|---|"]
        L += [f"| {f['id']} | {cell(f.get('title'), 80)} | {cell(Path((f.get('known') or {}).get('doc', '')).name, 40)} | "
              f"{cell((f.get('known') or {}).get('quote'), 120)} |" for f in known]
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
            elif st == "KNOWN":
                action = "только отчёт: описано в документах проекта как известное"
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
    out = a.out or (str(Path(a.run_dir) / f"{a.cmd}.md") if a.cmd in ("report", "summary") else None)
    text = build_report(run, out) if a.cmd == "report" else build_summary(run) if a.cmd == "summary" else "\n".join(publish_table(run)) + "\n"
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
