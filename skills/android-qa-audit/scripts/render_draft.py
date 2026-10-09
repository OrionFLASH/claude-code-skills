#!/usr/bin/env python3
"""Issue drafts from findings.json by templates/issue-detailed.md (references/repo-sync.md). Never publishes.

  render_draft.py detailed findings.json --id F-001 [--repo owner/repo] [--config run-config.yaml] [--out FILE]
  render_draft.py all findings.json --run-dir R [--repo owner/repo] [--config …] [--status NEW,REGRESSION]
                  [--min-severity low]   → R/drafts/<owner__repo|local>/NN-STATUS-fp.md (+ .body.md) and index.md
  render_draft.py summary --run-dir R [--repo owner/repo]   → drafts/<repo>/summary.md (summary.md without local paths)

Publication settings (flags override run-config repos[] entry chosen by --repo, then publish.* of run-config):
  --disclosure tool|none   tool (default; «full» is the same): the skill's footer and hidden marker are kept;
                           none: no footer, no sources / run id, no hidden marker, no tool labels — for a foreign
                           tracker a warning is printed and written to index.md (repos[].ours: true silences it)
  --no-links               no links to issues of other repositories
  --marker skill|neutral|none   skill: <!-- android-qa-audit:fp=… -->, neutral: <!-- qa-fp:… --> (disclosure tool only)
  --attachments-base URL   screenshots/recordings as links under this URL (attachments.py push to a branch);
                           repos[].attachments: branch with attachments_repo/branch/dir builds it automatically;
                           without it they are referenced as local files of the run folder
  --human-steps            steps written as user actions instead of adb / adb_helpers commands (repos[].steps: human)
  --form PATH|auto         body by the repository's GitHub issue form (issue_forms.py fetch): fields «### label»,
                           `_No response_`, exact dropdown options; auto — a bug or feature form from --forms-dir
                           (default <RUN_DIR>/raw/forms/<owner__repo>); --form-map map.json — values for fields
Screenshots: the annotated copy (shots[].annotated or <name>-annotated.png next to the original) replaces the original.
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
FOREIGN_WARNING = ("ВНИМАНИЕ: disclosure: none — в тексте нет пометки, что находки собраны инструментом. В чужом трекере "
                   "это может ввести мейнтейнеров в заблуждение (они сочтут текст ручным отчётом); предпочтительно "
                   "disclosure: tool. Свой репозиторий — repos[].ours: true.")
TOOL_LABEL = re.compile(r"android-qa-audit|qa-audit|claude", re.I)
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


def publish_settings(config):
    if not config or not Path(config).exists():
        return {}
    cfg = miniyaml.load_file(config) or {}
    return cfg.get("publish") or {}


class Opts:
    def __init__(self, a):
        rs = repo_settings(getattr(a, "config", None), getattr(a, "repo", None))
        ps = publish_settings(getattr(a, "config", None))
        self.repo = norm_repo(a.repo) if getattr(a, "repo", None) else None
        disc = getattr(a, "disclosure", None) or rs.get("disclosure") or ps.get("disclosure") or "tool"
        self.disclosure = "none" if disc == "none" else "tool"
        self.cross_links = not getattr(a, "no_links", False) and rs.get("cross_links", True) is not False
        self.marker = "none" if self.disclosure == "none" else (getattr(a, "marker", None) or rs.get("marker") or "skill")
        self.severity_map = rs.get("severity_map") or {}
        self.labels_policy = rs.get("labels") or "existing"
        self.extra_labels = [x for x in (rs.get("extra_labels") or [])
                             if not (self.disclosure == "none" and TOOL_LABEL.search(str(x)))]
        self.base = getattr(a, "attachments_base", None) or rs.get("attachments_base")
        if not self.base and rs.get("attachments") == "branch" and rs.get("attachments_branch"):
            repo = norm_repo(rs.get("attachments_repo") or rs.get("url") or rs.get("repo"))
            self.base = f"https://github.com/{repo}/blob/{rs['attachments_branch']}/{(rs.get('attachments_dir') or 'qa-screenshots').strip('/')}"
        self.human = bool(getattr(a, "human_steps", False) or rs.get("steps") == "human" or ps.get("steps") == "human")
        self.ours = rs.get("ours")
        self.warning = FOREIGN_WARNING if (self.disclosure == "none" and self.repo and self.ours is not True) else None
        self.run_dir = Path(a.run_dir) if getattr(a, "run_dir", None) else None
        self.form = getattr(a, "form", None) or rs.get("form")
        self.forms_dir = getattr(a, "forms_dir", None)
        if self.form == "auto" and not self.forms_dir and self.run_dir and self.repo:
            self.forms_dir = str(self.run_dir / "raw" / "forms" / self.repo.replace("/", "__"))
        fm = getattr(a, "form_map", None)
        self.form_map = json.loads(Path(fm).read_text(encoding="utf-8")) if fm else {}

    def finish(self, body):
        if self.marker == "neutral":
            body = SKILL_MARKER.sub(lambda m: f"<!-- qa-fp:{m.group(1)} -->\n", body)
        elif self.marker == "none":
            body = SKILL_MARKER.sub("", body)
        if self.disclosure == "none":
            body = re.sub(r"\n---\n_Создано android-qa-audit[^\n]*\n?", "\n", body)
            body = re.sub(r"^\|\s*\*\*(Источник|Прогон)\*\*\s*\|[^\n]*\n?", "", body, flags=re.M)
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


def shots_of(f, run_dir=None):
    """Screenshots to show: shots[].annotated (or original) first, then screenshots[] with an annotated sibling
    (<name>-annotated.png) instead of the original; duplicates removed."""
    refs = [s.get("annotated") or s.get("original") for s in f.get("shots") or [] if isinstance(s, dict)]
    originals = {s.get("original") for s in f.get("shots") or [] if isinstance(s, dict) and s.get("annotated")}
    for x in f.get("screenshots") or []:
        if not isinstance(x, str) or x in originals:
            continue
        stem = Path(x).stem
        if not stem.endswith("-annotated"):
            sib = str(Path(x).with_name(stem + "-annotated" + Path(x).suffix))
            if sib in refs or sib in (f.get("screenshots") or []) or (run_dir and (Path(run_dir) / sib).exists()):
                x = sib
        refs.append(x)
    return list(dict.fromkeys(r for r in refs if r))


HUMAN_STEPS = [
    (r"font-scale\s+([\d.]+)", lambda m: f"Настройки Android → Экран → Размер шрифта: {'максимальный' if float(m.group(1)) >= 2 else 'крупный'} (×{m.group(1)})"),
    (r"dark-mode\s+on", lambda m: "Настройки Android → Экран → Тёмная тема: включить"),
    (r"dark-mode\s+off", lambda m: "Настройки Android → Экран → Тёмная тема: выключить"),
    (r"rotate\s+(landscape|reverse-landscape)", lambda m: "Повернуть телефон горизонтально (автоповорот включён)"),
    (r"rotate\s+portrait", lambda m: "Вернуть телефон в вертикальное положение"),
    (r"kill-bg", lambda m: "Свернуть приложение кнопкой «Домой» и дождаться, пока система выгрузит его из памяти "
                           "(или «Параметры разработчика → Лимит фоновых процессов: без фоновых процессов»), затем открыть из «Недавних»"),
    (r"launch\s+--cold|am force-stop", lambda m: "Полностью закрыть приложение (смахнуть из «Недавних») и открыть заново"),
    (r"\blaunch\b", lambda m: "Открыть приложение"),
    (r"network\s+offline", lambda m: "Включить режим полёта (без сети)"),
    (r"network\s+online", lambda m: "Выключить режим полёта"),
    (r"network\s+(3g|edge|gprs|4g)", lambda m: f"Медленный мобильный интернет ({m.group(1).upper()})"),
    (r"network\s+switch", lambda m: "Выключить Wi-Fi на несколько секунд и включить снова"),
    (r"battery\s+saver-on", lambda m: "Включить режим энергосбережения"),
    (r"battery\s+level\s+(\d+)", lambda m: f"Заряд батареи {m.group(1)} % (без зарядки)"),
    (r"doze\s+enter", lambda m: "Оставить телефон без зарядки с выключенным экраном (режим сна Doze)"),
    (r"locale\s+([\w-]+)", lambda m: f"Язык приложения: {m.group(1)} (Настройки → Система → Языки → Языки приложений)"),
    (r"shade\s+open", lambda m: "Открыть шторку уведомлений (смахнуть сверху вниз)"),
    (r"key\s+BACK", lambda m: "Нажать «Назад»"),
    (r"key\s+HOME", lambda m: "Нажать «Домой»"),
    (r"key\s+APP_SWITCH", lambda m: "Открыть «Недавние»"),
    (r"(grant|revoke)\s+([\w.]+)", lambda m: f"Настройки → Приложения → (приложение) → Разрешения → {m.group(2).split('.')[-1]}: "
                                               f"{'разрешить' if m.group(1) == 'grant' else 'запретить'}"),
    (r"tap\s+--(?:text|desc)\s+[\"«]?([^\"»]+)[\"»]?", lambda m: f"Нажать «{m.group(1).strip()}»"),
    (r"long-press\s+--(?:text|desc)\s+[\"«]?([^\"»]+)[\"»]?", lambda m: f"Нажать и удерживать «{m.group(1).strip()}»"),
    (r"text\s+[\"«]([^\"»]*)[\"»]", lambda m: f"Ввести «{m.group(1)}»"),
    (r"scroll\s+(down|up)", lambda m: "Прокрутить вниз" if m.group(1) == "down" else "Прокрутить вверх"),
    (r"(?:input\s+tap|tap)\s+(\d+)\s+(\d+)", lambda m: f"Нажать на экран в точке ({m.group(1)}, {m.group(2)})"),
    (r"monkey\b.*?-s(?:eed)?\s+(\d+)", lambda m: f"Случайные нажатия (monkey, seed {m.group(1)}) — воспроизводится командой из раздела логов"),
]
TECH = re.compile(r"\badb\b|adb_helpers|\.py\b|settings put|dumpsys|am start|pm (grant|clear)|--serial", re.I)


def humanize(step):
    """One step as a user action. Returns (text, converted?) — unknown technical steps are kept and reported."""
    if not TECH.search(step) and not re.match(r"^\s*(adb_helpers|font-scale|dark-mode|rotate|kill-bg|launch|network|"
                                              r"battery|doze|locale|shade|key|grant|revoke|tap|long-press|scroll)\b", step):
        return step, False
    for rx, fn in HUMAN_STEPS:
        m = re.search(rx, step, re.I)
        if m:
            return fn(m), True
    return step, None


def human_steps(steps):
    out, left = [], []
    for s in steps or []:
        text, conv = humanize(s)
        out.append(text)
        if conv is None:
            left.append(s)
    return out, left


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
        "steps_numbered": "\n".join(f"{i}. {s}" for i, s in enumerate(
            human_steps(f.get("steps"))[0] if opts.human else (f.get("steps") or []), 1)),
        "expected": f.get("expected"), "actual": f.get("actual"),
        "actual_one_line": (f.get("actual") or f.get("suggestion") or f.get("title") or "").split("\n")[0][:300],
        "android": (f"API {env['api']}" + (f" (Android {env['android_version']})" if env.get("android_version") else "")) if env.get("api") else "",
        "device": device, "screen_cfg": env.get("screen") or "", "settings": settings,
        "stand": {"own-emulator": "эмулятор", "foreign-emulator": "эмулятор пользователя (read-only)", "real": "реальное устройство"}.get(env.get("stand"), env.get("stand") or ""),
        "date": env.get("date") or (run.get("started_at") or "")[:10],
        "environment_list": ", ".join(f.get("environment_list") or []),
        "crash_md": (f"**{crash.get('type', '').upper()}** {crash.get('summary', '')}" + (f" (процесс `{crash['process']}`)" if crash.get("process") else "")) if crash else "",
        "screenshots_md": media_md(shots_of(f, opts.run_dir), opts, rel_prefix),
        "recordings_md": media_md(f.get("recordings"), opts, rel_prefix, video=True),
        "logcat_excerpt": "\n".join((f.get("logcat_excerpt") or "").splitlines()[:40]),
        "metrics_json": json.dumps(f.get("metrics"), ensure_ascii=False, indent=2) if f.get("metrics") else "",
        "hypothesis": f.get("hypothesis"), "suggestion": f.get("suggestion"), "fingerprint": f.get("fingerprint", ""),
        "related_links": "\n".join(f"- {m.get('repo')}#{m.get('number')}" for m in f.get("matches") or []
                                   if opts.cross_links or norm_repo(m.get("repo")) == opts.repo),
        "legal_md": legal_md(f),
    }


def legal_md(f):
    """Legal norms are never stated as fact: «возможно применимо», second check, «проверить юристом»."""
    lg = f.get("legal") or {}
    norms = lg.get("norms") or []
    if not norms:
        return ""
    sc = lg.get("second_check") or {}
    lines = ["Возможно применимые нормы (наблюдение тестировщика, **не юридическое заключение; требуется проверка юристом**):"]
    lines += [f"- {n}" for n in norms]
    if sc.get("by"):
        lines.append(f"\nВторая проверка: {sc.get('by')} — {sc.get('result')}" + (f" ({sc.get('note')})" if sc.get("note") else ""))
    return "\n".join(lines)


PROPOSAL_TYPES = ("proposal", "suggestion", "user-story")


def form_for(f, opts):
    """Path of the repository's form for this finding (--form PATH | auto by kind) or None."""
    if not opts.form:
        return None
    if opts.form != "auto":
        return opts.form
    d = Path(opts.forms_dir) if opts.forms_dir else None
    if not d or not d.is_dir():
        return None
    import qa_issueforms
    forms = []
    for p in sorted(d.iterdir()):
        if p.suffix.lower() in (".yml", ".yaml", ".md") and p.name.lower() not in ("config.yml", "config.yaml"):
            try:
                forms.append(dict(qa_issueforms.load_form(p), path=str(p)))
            except qa_issueforms.FormError:
                continue
    hit = qa_issueforms.choose_form(forms, "proposal" if f.get("type") in PROPOSAL_TYPES else "bug")
    return hit["path"] if hit else None


def form_values(f, run, opts, rel_prefix):
    v = values(f, run, opts, rel_prefix)
    env = f.get("environment") or {}
    lines = [f"- Android: {v['android']}" if v["android"] else "", f"- Устройство: {v['device']}" if v["device"] else "",
             f"- Экран: {v['screen_cfg']}" if v["screen_cfg"] else "", f"- Настройки: {v['settings']}" if v["settings"] else "",
             f"- Стенд: {v['stand']}" if v["stand"] else "", f"- Дата: {v['date']}" if v["date"] else "",
             f"- Воспроизводится также: {v['environment_list']}" if v["environment_list"] else ""]
    extra = [x for x in [v["hypothesis"] and f"Гипотеза: {v['hypothesis']}", v["legal_md"], v["crash_md"],
                         v["recordings_md"]] if x]
    if opts.disclosure != "none":
        extra.append(f"Направление: {v['direction']} (`{v['check_id']}`), источник: {v['sources']}")
    return {"title": v["title"], "summary": v["actual_one_line"], "steps": v["steps_numbered"], "expected": v["expected"],
            "actual": v["actual"], "environment": "\n".join(x for x in lines if x), "android": v["android"],
            "device": v["device"], "app_version": f.get("app_version") or run.get("app_version") or "",
            "severity": f.get("severity"), "screenshots": v["screenshots_md"], "logs": v["logcat_excerpt"],
            "screen": " · ".join(x for x in [(f.get("screen") or "").split(".")[-1], f.get("element") or ""] if x),
            "suggestion": v["suggestion"], "frequency": f.get("frequency") or "", "platform": "Android",
            "extra": "\n\n".join(extra) or None, "api": env.get("api")}


def render(f, run, opts, rel_prefix=""):
    """(title, body, problems). problems — what the user must decide (issue form: dropdown, required fields)."""
    v = values(f, run, opts, rel_prefix)
    problems = []
    if opts.human:
        problems += [f"шаг с командой — переписать для человека: «{s}»" for s in human_steps(f.get("steps"))[1]]
    form = form_for(f, opts)
    if form:
        import qa_issueforms
        title, body, _labels, probs = qa_issueforms.render(form, form_values(f, run, opts, rel_prefix), opts.form_map,
                                                           v["title"])
        problems += probs
        if body is not None:
            if opts.disclosure != "none":
                body += "\n---\n_Создано android-qa-audit. Проверка через интерфейс приложения и adb без доступа к исходному коду._\n"
                if opts.marker == "skill" and f.get("fingerprint"):
                    body += f"<!-- android-qa-audit:fp={f['fingerprint']} -->\n"
                elif opts.marker == "neutral" and f.get("fingerprint"):
                    body += f"<!-- qa-fp:{f['fingerprint']} -->\n"
            return title, mask(opts.finish(body)), problems
    body = drop_empty(fill(strip_comments((TPL / "issue-detailed.md").read_text(encoding="utf-8")), v))
    body = re.sub(r"^\|\s*\*\*Прогон\*\*\s*\|\s*\(\)\s*\|\n?", "", body, flags=re.M)
    return f"[{v['severity_upper']}] {v['title']}", mask(opts.finish(body)), problems


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
        title, body, problems = render(f, run, opts, rel_prefix="../../")
        name = f"{n:02d}-{st}-{f.get('fingerprint') or f['id']}"
        write(folder / f"{name}.md", title, body)
        write(folder / f"{name}.body.md", None, body)
        labels = labels_for(f, opts)
        form = form_for(f, opts)
        if form:
            import qa_issueforms
            try:
                labels = list(dict.fromkeys(qa_issueforms.load_form(form)["labels"] + labels))
            except qa_issueforms.FormError:
                pass
        cmd = (f"gh issue create -R {opts.repo} --title \"{title.replace(chr(34), chr(39))}\" --body-file \"{folder / (name + '.body.md')}\""
               + "".join(f" --label \"{x}\"" for x in labels)) if opts.repo else "—"
        check = "; ".join(problems) if problems else "—"
        rows.append(f"| {n} | {f['id']} | {title} | {', '.join(labels) or '—'} | {Path(form).name if form else 'шаблон скила'} | "
                    f"{check} | `{cmd}` |")
        if problems:
            sys.stderr.write(f"render_draft: {f['id']}: решить до публикации — {check}\n")
    head = [f"# Черновики issues — {opts.repo or 'без репозитория'}", "",
            "Ничего не опубликовано. Команды ниже выполняются только после явного «да» пользователя "
            "(сводная таблица build_report.py publish-table). Скриншоты gh не прикладывает — вложения веткой "
            "(attachments.py push) до создания issues, см. repo-sync.md.", ""]
    if opts.warning:
        head += [f"> {opts.warning}", ""]
        sys.stderr.write("render_draft: " + opts.warning + "\n")
    index = head + ["| № | Находка | Заголовок | Метки | Форма | Проверить | Команда |", "|---|---|---|---|---|---|---|"] + \
        (rows or ["| — | — | нет находок по фильтру | — | — | — | — |"])
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
    ap.add_argument("--disclosure", choices=["tool", "full", "none"])
    ap.add_argument("--human-steps", action="store_true", help="шаги действиями пользователя, а не командами adb")
    ap.add_argument("--form", help="форма issue репозитория (.yml) или auto")
    ap.add_argument("--forms-dir", help="папка с формами (issue_forms.py fetch); по умолчанию <RUN_DIR>/raw/forms/<owner__repo>")
    ap.add_argument("--form-map", help="map.json: значения полей формы {id или label: значение / точный вариант}")
    ap.add_argument("--no-links", action="store_true")
    ap.add_argument("--marker", choices=["skill", "neutral", "none"])
    ap.add_argument("--attachments-base")
    ap.add_argument("--status")
    ap.add_argument("--min-severity", default="info")
    ap.add_argument("--out")
    ap.add_argument("--body-only", action="store_true", help="detailed: в --out только тело (gh --body-file), заголовок — в stdout")
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
    title, body, problems = render(f, run, opts)
    if opts.warning:
        sys.stderr.write("render_draft: " + opts.warning + "\n")
    for pr in problems:
        sys.stderr.write(f"render_draft: решить до публикации — {pr}\n")
    if a.out and getattr(a, "body_only", False):
        # body only for gh issue create --body-file (direct publication); the title is printed
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(body, encoding="utf-8")
        print(f"TITLE: {title}")
        print(a.out)
    elif a.out:
        write(a.out, title, body)
        print(a.out)
    else:
        print(f"TITLE: {title}\n\n{body}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
