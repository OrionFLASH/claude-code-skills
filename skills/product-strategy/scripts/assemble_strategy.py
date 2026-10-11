#!/usr/bin/env python3
"""Склейка и проверка research/strategy.md: части разделов → один файл, плейсхолдеры, маркеры, ссылки.

  assemble_strategy.py <OUT> [--insert-mockups] [--lenient] [--strict] [--check] [--no-parts] [--require-all] [--json]
                       [--label-unlabeled] [--show N]
  assemble_strategy.py <OUT> --list-placeholders [--json]     все ключи {bet:…}, {north_star}, {model:…}, {exp:…} со значениями

Источник текста (по приоритету):
  1. части `build/parts/strategy-*.md` и `research/strategy-part*.md` — разделы режутся по заголовкам `## N. …`
     (в одном файле может быть несколько разделов); порядок разделов — 1…17 по references/strategy-outline.md
     (в режиме идеи, run-config mode: concept, — по references/concept-outline.md, минимумы слов оттуда же);
  2. если частей нет, но есть `research/strategy.md` — проверка и подстановка «на месте»
     (в этом режиме подставленные ранги «замораживаются»: чтобы обновлять их, держите части как источник правды).

Что делает:
  - `{rank:P032}` → номер `rank` из data/scores.json, `{deprank:P032}` → `dep_rank` (нет dep_rank → rank и предупреждение);
  - `![[mockup:?P058]]` → `![[mockup:<ключ>]]` по `proposals[].mockup` (`mockups[0]`); нет макета → маркер удаляется,
    в отчёт идёт заметка «макета для P058 нет» (не ошибка);
  - `--insert-mockups` — в конец разделов 6 (привлечение), 7 (конверсия), 8 (монетизация), 9 (удержание), 10 (остальное)
    добавляет подраздел «Макеты концептов» с `![[mockup:ключ]]` и списком P-id по предложениям, у которых есть макет;
    ключи, уже вставленные в текст, не дублируются (повторный запуск ничего не добавляет);
  - проверки: каждый `P\\d{3}` есть в data/proposals.json; `![[chart:k]]` — в charts/charts-index.json (нет индекса или ключа —
    `charts.py <OUT> --list-keys`, поле available); `![[mockup:k]]` — в data/mockups-index.json; `![[ref:NN-slug]]` — в
    design-refs/; `![[flow:k]]` — в data/flows.json; битый маркер/ключ/несуществующий P-id = ОШИБКА;
  - предупреждения: URL неверного формата (плейсхолдеры «…», <…>, {…}, example.*), URL нет в data/sources.json, число с %/деньгами
    без метки [факт|оценка|допущение] и без ссылки на источник (эвристика), раздел короче минимума для глубины, нет раздела;
  - решения, модель, эксперименты (decisions.py): `{bet:1.kill}`, `{bet:1.name}`, `{north_star}`, `{anti_goals}`, `{fork:F1}`,
    `{capacity}` — из data/decisions.json; `{model:base.ltv}`, `{model:pess.cac}`, `{model:base.users_last}` — из data/model.json;
    `{exp:E01.n}`, `{exp:E01.weeks}`, `{bet:1.kill.weeks}` — из data/experiments.json и расчёта измеримости (sample_size.py);
    формат `{model:base.ltv|money}`, `{model:base.churn|%}`, `{…|0}`; неизвестный ключ или нет файла — ОШИБКА; список ключей —
    `--list-placeholders`. Подставляются после `{rank:…}`, в коде не трогаются;
  - сверка с decisions.json: абзац, где упомянута ставка (`Ставка 1` или её название) и критерий отказа, с буквальным порогом
    (число с %, п. п. или рядом с «ниже/выше/порог/не менее…») или датой, которые не совпадают с `bets[].kill` → предупреждение
    `decision_mismatch` (с `--strict` — ошибка); то же для цели и названия North Star. Значения из плейсхолдеров не сверяются;
  - измеримость критериев отказа (sample_size.evaluate_criteria): нужный срок больше времени до kill.date или горизонта,
    нет трафика → `kill_unobservable` (с `--strict` — ошибка); результат — в отчёте `kill_criteria`;
  - числа без метки: печатаются первые `--show` (10) мест «файл части:строка (раздел N): фрагмент»; `--label-unlabeled`
    дописывает « [допущение]» в конец таких фрагментов в исходных частях (или в strategy.md в режиме «на месте») и печатает
    правки; значения плейсхолдеров при этом не считаются числами без метки;
  - повторы между разделами: почти одинаковые абзацы (шинглы по 5 слов, сходство ≥ 0,6, абзацы ≥ 20 слов) → предупреждения
    `repeated_text` «раздел A ↔ раздел B»; общие числа с %/деньгами в разделах 2/3/6/7 — список в отчёте `repeats.numbers`.

Результат: research/strategy.md (без --check), отчёт build/assemble-report.json. Если существующий strategy.md отличается от
собранного из частей, прежний сохраняется в build/strategy.prev.md.
Код выхода: 0 — ошибок нет (предупреждения допустимы); 1 — есть ошибки (с --lenient ошибки становятся предупреждениями;
--strict делает ошибками расхождения с decisions.json и ненаблюдаемые критерии отказа);
2 — нет папки <OUT>/data или нет ни частей, ни strategy.md.
Только стандартная библиотека.
"""
import argparse
import bisect
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import decisions as dec_mod  # noqa: E402

SECTIONS = list(range(1, 18))
# минимум слов на раздел по глубине (references/strategy-outline.md)
MIN_WORDS = {
    "quick": [300, 400, 300, 200, 200, 400, 300, 300, 300, 400, 200, 200, 200, 400, 200, 100, 0],
    "standard": [500, 1000, 1000, 700, 600, 1200, 1000, 1000, 800, 1200, 600, 700, 700, 1200, 700, 300, 400],
    "deep": [600, 1500, 1500, 1000, 900, 1800, 1400, 1500, 1200, 1800, 900, 1000, 1000, 1800, 1000, 400, 600],
    "exhaustive": [700, 2000, 2500, 1500, 1200, 2500, 2000, 2000, 1600, 2500, 1200, 1400, 1500, 2500, 1500, 500, 800],
}
# режим идеи (mode: concept): минимумы для standard из references/concept-outline.md, другие глубины — множителем
CONCEPT_MIN_WORDS_STANDARD = [600, 1100, 1200, 700, 900, 900, 800, 1100, 500, 1400, 900, 1000, 1100, 1200, 600, 300, 400]
CONCEPT_DEPTH_FACTOR = {"quick": 0.3, "standard": 1.0, "deep": 1.5, "exhaustive": 2.0}
# куда вставлять блок макетов: категория предложения → номер раздела (в режиме идеи разделы 6–10 те же по смыслу)
MOCKUP_SECTION = {"acquisition": 6, "conversion": 7, "monetization": 8, "retention": 9}
MOCKUP_DEFAULT_SECTION = 10
MOCKUP_HEADING = "### Макеты концептов"

HEAD_RE = re.compile(r"^##[ \t]+(\d+)\.[ \t]*(.*?)[ \t]*$")
PID_RE = re.compile(r"(?<![A-Za-z0-9])P\d{3}(?!\d)")
MARKER_START = "![["
MARKER_RE = re.compile(r"!\[\[[ \t]*([A-Za-z_]+)[ \t]*:[ \t]*([^\]\n]*?)[ \t]*\]\]")
PLACEHOLDER_RE = re.compile(r"\{(rank|deprank)[ \t]*:[ \t]*([^}\n]*?)[ \t]*\}")
URL_RE = re.compile(r"https?://[^\s<>\]\"'`]+", re.I)
LABEL_RE = re.compile(r"\[\s*(?:факт|оценка|допущение|не подтверждено)\b|\]\(https?://", re.I)  # метка либо ссылка на источник
NUMBER_RE = re.compile(r"\d[\d \u00a0\u202f.,]*[ \u00a0]?(?:%|п\.[ ]?п\.|₽|руб|\$|€|USD|EUR|RUB)|[$€][ \u00a0]?\d", re.I)
TRACKING = {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid"}


# ---------------------------------------------------------------- ввод-вывод
def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as e:
        print("предупреждение: не удалось прочитать %s: %s" % (path, e), file=sys.stderr)
        return default


def dump_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- URL
def clean_url(raw):
    u = raw
    while u and u[-1] in ".,;:!?»”*":
        u = u[:-1]
    while u.endswith(")") and u.count(")") > u.count("("):
        u = u[:-1]
    return u


def url_problem(u):
    """Причина, по которой строка не годится как URL источника, или None."""
    if "…" in u or "..." in u:
        return "плейсхолдер «…»"
    if re.search(r"[<>{}]", u):
        return "плейсхолдер <…> или {…}"
    if u.count("(") > u.count(")"):
        return "незакрытая скобка"
    try:
        host = (urlsplit(u).hostname or "").lower()
    except ValueError as e:
        return "неверный формат: %s" % e
    if not host or ("." not in host and host != "localhost"):
        return "нет домена"
    if re.fullmatch(r"(?:www\.)?example\.[a-z.]+", host):
        return "плейсхолдер example.*"
    return None


def norm_url(u):
    """Ключ сравнения: схема и хост в нижнем регистре, без якоря, utm_* и трекинговых параметров, без хвостового «/»."""
    try:
        p = urlsplit(u.strip())
        port = p.port
    except ValueError:
        return u.strip()
    host = (p.hostname or "").lower()
    if port and not ((p.scheme.lower() == "http" and port == 80) or (p.scheme.lower() == "https" and port == 443)):
        host += ":%d" % port
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in TRACKING]
    return "%s://%s%s%s" % (p.scheme.lower(), host, p.path.rstrip("/"), ("?" + urlencode(q)) if q else "")


# ---------------------------------------------------------------- разбор текста
def code_spans(text, inline=True):
    """Диапазоны (start, end) ограждённых блоков кода и (inline=True) инлайн-кода — внутри них маркеры и плейсхолдеры не трогаем."""
    spans, pos, in_fence, fence_start, fence_ch = [], 0, False, 0, ""
    for line in text.splitlines(keepends=True):
        s = line.lstrip()
        if s.startswith("```") or s.startswith("~~~"):
            if not in_fence:
                in_fence, fence_start, fence_ch = True, pos, s[:3]
            elif s.startswith(fence_ch):
                in_fence = False
                spans.append((fence_start, pos + len(line)))
        elif not in_fence and inline:
            for m in re.finditer(r"`[^`\n]*`", line):
                spans.append((pos + m.start(), pos + m.end()))
        pos += len(line)
    if in_fence:
        spans.append((fence_start, len(text)))
    return sorted(spans)


class Code:
    def __init__(self, text, inline=True):
        self.spans = code_spans(text, inline)
        self.starts = [s for s, _ in self.spans]

    def inside(self, pos):
        i = bisect.bisect_right(self.starts, pos) - 1
        return i >= 0 and self.spans[i][0] <= pos < self.spans[i][1]


def split_sections_lines(text):
    """→ (преамбула, строка начала преамбулы, [(N, заголовок, текст раздела с заголовком, строка заголовка в файле)])."""
    code = Code(text)
    marks, pos = [], 0
    for ln, line in enumerate(text.splitlines(keepends=True), 1):
        m = HEAD_RE.match(line.rstrip("\n"))
        if m and not code.inside(pos):
            marks.append((pos, int(m.group(1)), m.group(2), ln))
        pos += len(line)
    lead = len(text) - len(text.lstrip())
    pre_line = text.count("\n", 0, lead) + 1
    if not marks:
        return text.strip(), pre_line, []
    pre = text[:marks[0][0]].strip()
    out = []
    for i, (st, n, title, ln) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out.append((n, title, text[st:end].strip(), ln))
    return pre, pre_line, out


def split_sections(text):
    """→ (преамбула, [(N, заголовок, текст раздела с заголовком)])."""
    pre, _pl, secs = split_sections_lines(text)
    return pre, [(n, t, b) for n, t, b, _ln in secs]


def find_parts(out):
    files = sorted((out / "build" / "parts").glob("strategy-*.md")) + sorted((out / "research").glob("strategy-part*.md"))
    return [f for f in files if f.is_file()]


def depth_min_words(depth, n, concept=False):
    if concept:
        f = CONCEPT_DEPTH_FACTOR.get(depth)
        return int(round(CONCEPT_MIN_WORDS_STANDARD[n - 1] * f)) if f and 1 <= n <= 17 else 0
    row = MIN_WORDS.get(depth)
    return row[n - 1] if row and 1 <= n <= 17 else 0


def words(text):
    return len(re.findall(r"\w+", text))


# ---------------------------------------------------------------- отчёт об ошибках
class Report:
    def __init__(self, lenient):
        self.lenient = lenient
        self.errors, self.warnings, self.notes = [], [], []

    def error(self, code, message, line=None, section=None):
        item = {"code": code, "message": message}
        if line:
            item["line"] = line
        if section:
            item["section"] = section
        (self.warnings if self.lenient else self.errors).append(dict(item, severity="error→warning" if self.lenient else "error"))

    def warn(self, code, message, line=None, section=None):
        item = {"code": code, "message": message, "severity": "warning"}
        if line:
            item["line"] = line
        if section:
            item["section"] = section
        self.warnings.append(item)

    def note(self, code, message, **extra):
        self.notes.append(dict({"code": code, "message": message}, **extra))


# ---------------------------------------------------------------- данные прогона
class Data:
    def __init__(self, out):
        self.out = out
        self.proposals = {p["id"]: p for p in (load_json(out / "data" / "proposals.json", []) or []) if isinstance(p, dict) and p.get("id")}
        scores = load_json(out / "data" / "scores.json", None)
        self.scores = {s["id"]: s for s in scores if isinstance(s, dict) and s.get("id")} if isinstance(scores, list) else None
        idx = load_json(out / "data" / "mockups-index.json", None)
        self.mockups = {m["key"]: m for m in idx if isinstance(m, dict) and m.get("key")} if isinstance(idx, list) else None
        flows = load_json(out / "data" / "flows.json", None)
        self.flows = {f["key"] for f in flows if isinstance(f, dict) and f.get("key")} if isinstance(flows, list) else None
        src = load_json(out / "data" / "sources.json", None)
        self.source_urls = {norm_url(s["url"]) for s in src if isinstance(s, dict) and s.get("url")} if isinstance(src, list) else None
        cfg = load_json(out / "build" / "run-config.json", {}) or {}
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self._charts = None
        self._list_keys = None

    # ключи графиков
    def chart_keys(self):
        """Множество допустимых ключей: charts-index.json; нет индекса → charts.py --list-keys (available)."""
        if self._charts is None:
            idx = load_json(self.out / "charts" / "charts-index.json", None)
            if isinstance(idx, list):
                self._charts = {c["key"] for c in idx if isinstance(c, dict) and c.get("key")}
            else:
                self._charts = set(self.list_keys().get("available") or [])
        return self._charts

    def list_keys(self):
        """Вывод `charts.py <OUT> --list-keys` как {available, skipped}; нет флага/ошибка → пусто."""
        if self._list_keys is None:
            self._list_keys = {"available": [], "skipped": {}}
            script = HERE / "charts.py"
            if script.exists():
                try:
                    r = subprocess.run([sys.executable, "-B", str(script), str(self.out), "--list-keys"], capture_output=True, text=True, timeout=120)
                    if r.returncode == 0:
                        d = json.loads(r.stdout)
                        if isinstance(d, dict):
                            self._list_keys = {"available": list(d.get("available") or []), "skipped": dict(d.get("skipped") or {})}
                except (OSError, subprocess.SubprocessError, ValueError):
                    pass
        return self._list_keys

    def chart_problem(self, key):
        if key in self.chart_keys():
            return None
        lk = self.list_keys()
        if key in (lk.get("available") or []):
            return None
        why = (lk.get("skipped") or {}).get(key)
        if why:
            return "график «%s» не построен: %s" % (key, why)
        if key == "gantt":
            return "график «gantt» появляется после записи data/gantt.json и запуска charts.py"
        return "нет графика «%s» в charts/charts-index.json" % key


def mockup_key(value):
    """'concepts/M01-landing.html' → 'M01-landing'; ключ остаётся ключом."""
    return Path(str(value)).stem if value else None


def proposal_mockup_keys(p):
    keys = []
    for v in ([p.get("mockup")] if p.get("mockup") else []) + list(p.get("mockups") or []):
        k = mockup_key(v)
        if k and k not in keys:
            keys.append(k)
    return keys


# ---------------------------------------------------------------- шаги преобразования
def substitute_ranks(sections, data, rep):
    """{rank:P…} / {deprank:P…} внутри каждого раздела."""
    counts = {"rank": 0, "deprank": 0}
    warned_dep = [False]

    def one(n, text):
        code = Code(text)

        def repl(m):
            kind, pid = m.group(1), m.group(2).strip()
            if code.inside(m.start()):
                return m.group(0)
            if not re.fullmatch(r"P\d{3}", pid):
                rep.error("bad_placeholder", "плейсхолдер %s не содержит P-id" % m.group(0), section=n)
                return m.group(0)
            if data.scores is None:
                rep.error("no_scores", "нет data/scores.json: %s не подставить (запустите score.py)" % m.group(0), section=n)
                return m.group(0)
            s = data.scores.get(pid)
            if s is None:
                rep.error("missing_rank", "%s: нет записи в data/scores.json (%s)" % (pid, m.group(0)), section=n)
                return m.group(0)
            if kind == "deprank":
                if s.get("dep_rank") is None:
                    if not warned_dep[0]:
                        rep.warn("no_dep_rank", "в data/scores.json нет dep_rank: {deprank:…} заменён на rank (обновите score.py)")
                        warned_dep[0] = True
                    val = s.get("rank")
                else:
                    val = s["dep_rank"]
            else:
                val = s.get("rank")
            if val is None:
                rep.error("missing_rank", "%s: в scores.json нет ранга" % pid, section=n)
                return m.group(0)
            counts[kind] += 1
            return str(val)
        return PLACEHOLDER_RE.sub(repl, text)
    return {n: one(n, t) for n, t in sections.items()}, counts


def resolve_mockup_queries(sections, data, rep):
    """![[mockup:?P058]] → ![[mockup:<ключ>]] либо удаление маркера, если макета нет."""
    resolved, removed = [], []

    def one(n, text):
        code = Code(text)
        changed = [False]

        def repl(m):
            kind, key = m.group(1).lower(), m.group(2)
            if kind != "mockup" or not key.startswith("?") or code.inside(m.start()):
                return m.group(0)
            pid = key[1:].strip()
            if pid not in data.proposals:
                rep.error("bad_pid", "%s: предложения нет в data/proposals.json (маркер %s)" % (pid or "?", m.group(0)), section=n)
                return m.group(0)
            keys = proposal_mockup_keys(data.proposals[pid])
            if not keys:
                removed.append(pid)
                rep.note("mockup_absent", "макета для %s нет" % pid, proposal=pid, section=n)
                changed[0] = True
                return "\x00REMOVED\x00"
            resolved.append({"proposal": pid, "key": keys[0], "section": n})
            return "![[mockup:%s]]" % keys[0]
        new = MARKER_RE.sub(repl, text)
        if changed[0]:
            # строка, состоявшая только из удалённого маркера, исчезает целиком
            new = re.sub(r"^[ \t]*\x00REMOVED\x00[ \t]*\n?", "", new, flags=re.M).replace("\x00REMOVED\x00", "")
            new = re.sub(r"\n{3,}", "\n\n", new)
        return new
    return {n: one(n, t) for n, t in sections.items()}, resolved, removed


def present_mockup_keys(sections):
    keys = set()
    for text in sections.values():
        code = Code(text)
        for m in MARKER_RE.finditer(text):
            if m.group(1).lower() == "mockup" and not code.inside(m.start()) and not m.group(2).startswith("?"):
                keys.add(m.group(2))
    return keys


def insert_mockup_blocks(sections, data, rep):
    """Подраздел «Макеты концептов» в конец разделов 6–10; уже вставленные ключи пропускаются."""
    if data.mockups is None:
        rep.error("no_mockups_index", "--insert-mockups: нет data/mockups-index.json")
        return sections, []
    present = present_mockup_keys(sections)
    by_key = {}
    for pid in sorted(data.proposals):
        p = data.proposals[pid]
        for k in proposal_mockup_keys(p):
            if k not in data.mockups:
                rep.error("bad_mockup", "%s: макет «%s» (proposals[].mockup) отсутствует в data/mockups-index.json" % (pid, k))
                continue
            e = by_key.setdefault(k, {"pids": [], "section": MOCKUP_SECTION.get(p.get("category"), MOCKUP_DEFAULT_SECTION)})
            e["pids"].append(pid)
    per_section, inserted = {}, []
    for k in sorted(by_key):
        if k in present:
            continue
        per_section.setdefault(by_key[k]["section"], []).append(k)
    out = dict(sections)
    for n in sorted(per_section):
        if n not in out:
            rep.warn("mockups_no_section", "макеты %s некуда вставить: нет раздела %d" % (", ".join(per_section[n]), n))
            continue
        lines = [MOCKUP_HEADING, "", "Макеты ниже показывают предложения как концепты, а не существующие функции.", ""]
        for k in per_section[n]:
            title = (data.mockups[k].get("title") or k)
            lines += ["![[mockup:%s]]" % k, "", "*Концепт «%s»: %s.*" % (title, ", ".join(by_key[k]["pids"])), ""]
        out[n] = out[n].rstrip() + "\n\n" + "\n".join(lines).rstrip() + "\n"
        inserted.append({"section": n, "keys": per_section[n]})
    return out, inserted


# ---------------------------------------------------------------- проверки итогового текста
def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def check_text(text, data, rep, section_of):
    code = Code(text)
    # P-id
    seen_missing = set()
    fenced = Code(text, inline=False)                    # P-id в ограждённых блоках кода (примеры) не проверяем
    for m in PID_RE.finditer(text):
        pid = m.group(0)
        if pid not in data.proposals and pid not in seen_missing and not fenced.inside(m.start()):
            seen_missing.add(pid)
            ln = line_of(text, m.start())
            rep.error("bad_pid", "%s: предложения нет в data/proposals.json" % pid, line=ln, section=section_of(ln))
    # маркеры
    stats = {"chart": 0, "mockup": 0, "ref": 0, "flow": 0}
    pos = 0
    while True:
        i = text.find(MARKER_START, pos)
        if i < 0:
            break
        pos = i + 3
        if code.inside(i):
            continue
        ln = line_of(text, i)
        sec = section_of(ln)
        m = MARKER_RE.match(text, i)
        if not m:
            snippet = text[i:text.find("\n", i) if text.find("\n", i) > 0 else len(text)][:60]
            rep.error("bad_marker", "битый маркер «%s»" % snippet, line=ln, section=sec)
            continue
        kind, key = m.group(1).lower(), m.group(2)
        if not key:
            rep.error("bad_marker", "пустой ключ в маркере «%s»" % m.group(0), line=ln, section=sec)
        elif kind == "chart":
            stats["chart"] += 1
            why = data.chart_problem(key)
            if why:
                rep.error("bad_chart", why, line=ln, section=sec)
        elif kind == "mockup":
            stats["mockup"] += 1
            if key.startswith("?"):
                rep.error("bad_marker", "неразрешённый маркер «%s»" % m.group(0), line=ln, section=sec)
            elif data.mockups is None:
                rep.error("bad_mockup", "![[mockup:%s]]: нет data/mockups-index.json" % key, line=ln, section=sec)
            elif key not in data.mockups:
                rep.error("bad_mockup", "нет макета «%s» в data/mockups-index.json" % key, line=ln, section=sec)
        elif kind == "ref":
            stats["ref"] += 1
            if not ((data.out / "design-refs" / (key + ".json")).exists() or (data.out / "design-refs" / (key + ".md")).exists()):
                rep.error("bad_ref", "нет карточки design-refs/%s.json" % key, line=ln, section=sec)
        elif kind == "flow":
            stats["flow"] += 1
            if data.flows is None or key not in data.flows:
                rep.error("bad_flow", "нет схемы «%s» в data/flows.json" % key, line=ln, section=sec)
        else:
            rep.error("bad_marker", "неизвестный вид маркера «%s» (допустимы chart, mockup, ref, flow)" % m.group(0), line=ln, section=sec)
    # URL
    seen = set()
    for m in URL_RE.finditer(text):
        if code.inside(m.start()):
            continue
        u = clean_url(m.group(0))
        if u in seen:
            continue
        seen.add(u)
        ln = line_of(text, m.start())
        why = url_problem(u)
        if why:
            rep.warn("bad_url", "URL «%s»: %s" % (u[:80], why), line=ln, section=section_of(ln))
        elif data.source_urls is not None and norm_url(u) not in data.source_urls:
            rep.warn("url_not_in_sources", "URL нет в data/sources.json: %s (merge_sources.py добавит)" % u[:100], line=ln, section=section_of(ln))
    return stats, len(seen)


def text_units(text, code=None):
    """Единицы текста (абзац / пункт списка / строка таблицы) вне кода → [(строка начала, строка конца, текст)]."""
    code = code or Code(text)
    res, unit, rng = [], [], [0, 0]
    pos = 0

    def flush():
        if unit:
            res.append((rng[0], rng[1], " ".join(unit).strip()))
        unit.clear()
    for i, line in enumerate(text.splitlines(keepends=True), 1):
        s = line.rstrip("\n").strip()
        if code.inside(pos) or not s:
            flush()
        elif s.startswith("#") or s.startswith("![[") or re.fullmatch(r"\|?[\s:|-]+\|?", s):
            flush()
        elif s.startswith("|") or re.match(r"([-*+]|\d+[.)])\s", s):
            flush()
            rng[:] = [i, i]
            unit.append(s)
        else:
            if not unit:
                rng[0] = i
            rng[1] = i
            unit.append(s)
        pos += len(line)
    flush()
    return res


def unlabeled_numbers(text, code=None):
    """Эвристика: единицы текста с числом при %, п.п. или деньгах, но без метки → [(начало, конец, текст)]."""
    res = []
    for start, end, body in text_units(text, code):
        body_clean = URL_RE.sub(" ", re.sub(r"`[^`\n]*`", " ", body))
        if NUMBER_RE.search(body_clean) and not LABEL_RE.search(body):
            res.append((start, end, body))
    return res


# ---------------------------------------------------------------- решения, модель, эксперименты
NEUTRAL = "⟨значение⟩"


def substitute_decisions(sections, reg, rep, neutral=False):
    """{bet:…}, {north_star}, {model:…}, {exp:…} → значения (neutral=True — нейтральная метка без цифр, для проверок)."""
    counts = {}
    warned = [False]
    sens_only = (reg.model or {}).get("mode") == "sensitivity-only"

    def one(n, text):
        code = Code(text)

        def repl(m):
            if code.inside(m.start()):
                return m.group(0)
            kind, key, bare, tail, spec = m.groups()
            full = reg.key_of(kind, key, bare, tail)
            if neutral:
                return NEUTRAL
            val, why = reg.render(full, spec)
            if val is None:
                rep.error("unknown_placeholder", "%s: %s (список ключей — assemble_strategy.py <OUT> --list-placeholders)" % (m.group(0), why),
                          section=n)
                return m.group(0)
            k = kind or bare
            counts[k] = counts.get(k, 0) + 1
            if kind == "model" and sens_only and not warned[0]:
                metric = full.split(".")[-1]
                if metric in dec_mod.FORECAST_KEYS or metric.endswith("_last"):
                    warned[0] = True
                    rep.warn("model_sensitivity_only", "модель в режиме sensitivity-only (нет данных об аудитории): %s и другие прогнозные "
                             "числа — иллюстрация, а не прогноз; оговорите это в тексте" % m.group(0), section=n)
            return val
        return dec_mod.PH_RE.sub(repl, text)
    return {n: one(n, t) for n, t in sections.items()}, counts


KILL_CTX = re.compile(r"критери\w*\s+(?:отказа|остановки)|kill|стоп-критери\w*|останов\w*|прекрат\w*|прекращ\w*|закро\w*\s+ставк|закрыва\w*\s+ставк", re.I)
NS_CTX = re.compile(r"north[\s-]*star|полярн\w*\s+звезд\w*", re.I)
CMP_NUM = re.compile(r"(?:<|>|≤|≥|=|ниже|выше|меньше|больше|не\s+менее|не\s+более|менее|более|порог\w*|уровн\w*|опустится\s+до|упад\w*\s+до|"
                     r"цел\w*|target)[\s:—-]*(?:чем\s+)?(\d+(?:[.,]\d+)?)", re.I)
PCT_NUM = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)[   ]?(?:%|п\.[  ]?п\.)")
NS_TARGET_NUM = re.compile(r"(?:цел\w*|target)[\s:—–-]*(?:[а-яё]+\s+){0,2}?(\d{1,3}(?:[  ]\d{3})+|\d+(?:[.,]\d+)?)", re.I)
DATE_TOKEN = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")


def _f(s):
    try:
        return float(str(s).replace(",", "."))
    except ValueError:
        return None


def _dates(text):
    out = set()
    for m in DATE_TOKEN.finditer(text):
        if m.group(1):
            out.add("%s-%s-%s" % (m.group(1), m.group(2), m.group(3)))
        else:
            out.add("%s-%02d-%02d" % (m.group(6), int(m.group(5)), int(m.group(4))))
    return out


def _threshold_numbers(text):
    """Числа-пороги: с %/п. п. или после «ниже/выше/порог/цель…» (даты и «Ставка N» вырезаны заранее)."""
    vals = set()
    for m in PCT_NUM.finditer(text):
        v = _f(m.group(1))
        if v is not None:
            vals.add(("pct", v))
    for m in CMP_NUM.finditer(text):
        v = _f(m.group(1))
        if v is not None:
            tail = text[m.end():m.end() + 3]
            vals.add(("pct" if "%" in tail or "п." in tail else "num", v))
    return vals


def _same(found, expected_vals):
    return any(abs(v - e) <= max(1e-9, abs(e) * 0.005) for _k, v in found for e in expected_vals)


def check_decisions(raw_neutral, owner, starts, reg, rep, strict):
    """Буквальные пороги, даты и название North Star в тексте против data/decisions.json → список расхождений."""
    d = reg.decisions
    if not isinstance(d, dict):
        return []
    found = []
    emit = rep.error if strict else rep.warn
    bets = [b for b in dec_mod.bets(d) if isinstance(b.get("kill"), dict)]
    ns = d.get("north_star") if isinstance(d.get("north_star"), dict) else {}
    ns_target = _f(re.search(r"\d[\d  ]*(?:[.,]\d+)?", str(ns.get("target") or "")).group(0).replace(" ", "").replace(" ", "")) \
        if re.search(r"\d", str(ns.get("target") or "")) else None
    ns_metric = str(ns.get("metric") or "").strip().lower()
    for n, text in raw_neutral.items():
        for start, _end, body in text_units(text):
            low = body.lower()
            line = starts.get(n, 1) + start - 1
            where = "%s:%s" % (owner.get(n, "?"), line)
            for b in bets:
                bid = str(b["id"])
                ref = re.search(r"ставк\w*\s*(?:№\s*)?%s(?!\d)" % re.escape(bid), low)
                name = str(b.get("name") or "").strip().lower()
                if not ref and not (len(name) >= 4 and name in low):
                    continue
                k = b["kill"]
                metric = str(k.get("metric") or "").strip().lower()
                if not (KILL_CTX.search(body) or (len(metric) >= 4 and metric in low)):
                    continue
                cleaned = DATE_TOKEN.sub(" ", re.sub(r"ставк\w*\s*(?:№\s*)?\d+", " ", body, flags=re.I))
                cleaned = re.sub(r"(?<![\w.,])P\d{3}\b|\bE\d{2}\b|\bK\d\b|\bF\d+\b", " ", cleaned)
                nums = _threshold_numbers(cleaned)
                t = k.get("threshold")
                if dec_mod.is_num(t) and nums:
                    exp = {float(t)} | ({float(t) * 100} if k.get("kind", "share") == "share" and 0 < abs(t) <= 1 else set())
                    if not _same(nums, exp):
                        shown = ", ".join(sorted({dec_mod.fmt_num(v) + (" %" if kd == "pct" else "") for kd, v in nums}))
                        msg = "ставка %s «%s»: в тексте порог %s, в data/decisions.json — %s (%s); используйте {bet:%s.kill}" % (
                            bid, b.get("name"), shown, dec_mod.kill_threshold_text(k), where, bid)
                        emit("decision_mismatch", msg, line=line, section=n)
                        found.append({"bet": b["id"], "what": "threshold", "where": where, "text": body[:160]})
                dates = _dates(body)
                if k.get("date") and dates and k["date"] not in dates:
                    msg = "ставка %s «%s»: в тексте дата %s, в data/decisions.json — %s (%s); используйте {bet:%s.kill.date}" % (
                        bid, b.get("name"), ", ".join(dec_mod.fmt_date(x) for x in sorted(dates)), dec_mod.fmt_date(k["date"]), where, bid)
                    emit("decision_mismatch", msg, line=line, section=n)
                    found.append({"bet": b["id"], "what": "date", "where": where, "text": body[:160]})
            if ns and NS_CTX.search(body):
                q = re.search(r"(?:north[\s-]*star|полярн\w*\s+звезд\w*)[^«\n]{0,40}«([^»]{3,80})»", body, re.I)
                if q and ns_metric and q.group(1).strip().lower() != ns_metric and ns_metric not in low:
                    msg = "North Star: в тексте «%s», в data/decisions.json — «%s» (%s); используйте {north_star}" % (q.group(1), ns.get("metric"), where)
                    emit("decision_mismatch", msg, line=line, section=n)
                    found.append({"bet": None, "what": "north_star.metric", "where": where, "text": body[:160]})
                if ns_target is not None:
                    tn = {("num", _f(re.sub(r"[  ]", "", m.group(1)))) for m in NS_TARGET_NUM.finditer(DATE_TOKEN.sub(" ", body))}
                    tn = {x for x in tn if x[1] is not None}
                    if tn and not _same(tn, {ns_target}):
                        msg = "North Star: в тексте цель %s, в data/decisions.json — %s (%s); используйте {north_star.target}" % (
                            ", ".join(sorted({dec_mod.fmt_num(v) for _k, v in tn})), ns.get("target"), where)
                        emit("decision_mismatch", msg, line=line, section=n)
                        found.append({"bet": None, "what": "north_star.target", "where": where, "text": body[:160]})
    return found


def kill_measurability(out, reg, rep, strict, cfg):
    """Измеримость критериев отказа через sample_size.evaluate_criteria → строки отчёта."""
    if not isinstance(reg.decisions, dict) or not dec_mod.bets(reg.decisions):
        return []
    try:
        import sample_size
    except ImportError:
        return []
    rows = sample_size.evaluate_criteria(out, reg.decisions, reg.model, cfg, reg.experiments)
    emit = rep.error if strict else rep.warn
    for r in rows:
        if r["status"] == "unobservable":
            emit("kill_unobservable", "ставка %s: критерий «%s» ненаблюдаем — %s; поменяйте порог/дату/метрику или пометьте «ненаблюдаем» "
                 "(sample_size.py <OUT> --criteria)" % (r["bet"], r.get("metric"), r.get("reason")))
        elif r["status"] == "unknown":
            rep.note("kill_not_computed", "ставка %s: измеримость критерия «%s» не рассчитана — %s" % (r["bet"], r.get("metric"), r.get("reason")))
    return rows


# ---------------------------------------------------------------- повторы между разделами
SHINGLE = 5
REPEAT_MIN_WORDS = 20
REPEAT_SIM = 0.6
REPEAT_NUM_SECTIONS = (2, 3, 6, 7)


def _paragraphs(text):
    """Абзацы раздела (таблица — одним абзацем) → [(строка начала, текст)]."""
    code = Code(text)
    out, cur, start, pos = [], [], 0, 0
    for i, line in enumerate(text.splitlines(keepends=True), 1):
        s = line.strip()
        skip = code.inside(pos) or s.startswith("#") or s.startswith("![[")
        if not s or skip:
            if cur:
                out.append((start, " ".join(cur)))
                cur = []
        else:
            if not cur:
                start = i
            cur.append(s)
        pos += len(line)
    if cur:
        out.append((start, " ".join(cur)))
    return out


def find_repeats(raw_neutral, owner, starts, rep, limit=50):
    """Почти одинаковые абзацы в разных разделах (шинглы) и общие числа разделов 2/3/6/7."""
    paras = []
    for n, text in raw_neutral.items():
        for ln, body in _paragraphs(text):
            w = re.findall(r"\w+", re.sub(r"[|*_`>]", " ", body.lower()))
            if len(w) < REPEAT_MIN_WORDS:
                continue
            sh = {" ".join(w[i:i + SHINGLE]) for i in range(len(w) - SHINGLE + 1)}
            paras.append((n, starts.get(n, 1) + ln - 1, body, sh))
    index = {}
    for i, p in enumerate(paras):
        for s in p[3]:
            index.setdefault(s, []).append(i)
    shared = {}
    for ids in index.values():
        if len(ids) > 30:                       # служебные обороты, встречающиеся везде
            continue
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                a, b = ids[x], ids[y]
                if paras[a][0] != paras[b][0]:
                    shared[(a, b)] = shared.get((a, b), 0) + 1
    pairs = []
    for (a, b), c in shared.items():
        A, B = paras[a][3], paras[b][3]
        sim = c / float(min(len(A), len(B)))
        if sim >= REPEAT_SIM:
            pairs.append({"similarity": round(sim, 2),
                          "a": {"section": paras[a][0], "file": owner.get(paras[a][0]), "line": paras[a][1]},
                          "b": {"section": paras[b][0], "file": owner.get(paras[b][0]), "line": paras[b][1]},
                          "text": paras[a][2][:160]})
    pairs.sort(key=lambda p: (-p["similarity"], p["a"]["section"], p["b"]["section"]))
    for p in pairs[:limit]:
        rep.warn("repeated_text", "раздел %s ↔ раздел %s: похожие абзацы (%d %%) — %s:%s и %s:%s; оставьте в одном, в другом — ссылка" % (
            p["a"]["section"], p["b"]["section"], int(p["similarity"] * 100), p["a"]["file"], p["a"]["line"], p["b"]["file"], p["b"]["line"]),
            line=p["a"]["line"], section=p["a"]["section"])
    nums = {}
    for n in REPEAT_NUM_SECTIONS:
        text = raw_neutral.get(n)
        if not text:
            continue
        for m in NUMBER_RE.finditer(URL_RE.sub(" ", text)):
            key = re.sub(r"[   ]", "", m.group(0)).lower()
            nums.setdefault(key, set()).add(n)
    common = [{"value": k, "sections": sorted(v)} for k, v in sorted(nums.items()) if len(v) >= 2]
    return {"paragraphs": pairs[:limit], "paragraphs_total": len(pairs), "numbers": common}


def label_unlabeled(out, items):
    """Дописать « [допущение]» в конец фрагментов (файл, end_line) → [(файл, строка, было, стало)]."""
    changes = []
    by_file = {}
    for it in items:
        if it.get("file") and it.get("end_line"):
            by_file.setdefault(it["file"], set()).add(it["end_line"])
    for rel, lines in by_file.items():
        p = out / rel
        try:
            src = p.read_text(encoding="utf-8").split("\n")
        except OSError:
            continue
        for ln in sorted(lines, reverse=True):
            if not 1 <= ln <= len(src):
                continue
            old = src[ln - 1]
            if "[допущение]" in old:
                continue
            if old.strip().startswith("|") and old.rstrip().endswith("|"):
                new = re.sub(r"[ \t]*\|[ \t]*$", " [допущение] |", old.rstrip())
            else:
                new = old.rstrip() + " [допущение]"
            src[ln - 1] = new
            changes.append((rel, ln, old.strip()[:100], new.strip()[-60:]))
        p.write_text("\n".join(src), encoding="utf-8")
    return sorted(changes)


# ---------------------------------------------------------------- основной ход
def build_from_parts(out, parts, rep, existing_pre, starts=None, pre_src=None):
    """starts — {N: строка заголовка в файле части}; pre_src — [файл, строка] источника преамбулы."""
    pre_part, owner, sections = "", {}, {}
    starts = {} if starts is None else starts
    for f in parts:
        pre, pre_line, secs = split_sections_lines(f.read_text(encoding="utf-8"))
        rel = f.relative_to(out).as_posix()
        if not secs:
            rep.warn("part_no_sections", "%s: нет заголовков «## N. …», файл пропущен" % rel)
            continue
        if pre and not pre_part:
            pre_part = pre
            if pre_src is not None:
                pre_src[:] = [rel, pre_line]
        for n, _title, body, ln in secs:
            if n in sections:
                rep.error("dup_section", "раздел %d есть в двух частях: %s и %s" % (n, owner[n], rel), section=n)
                continue
            sections[n], owner[n], starts[n] = body, rel, ln
    if not pre_part and pre_src is not None:
        pre_src[:] = ["research/strategy.md", 1]
    return (pre_part or existing_pre), sections, owner


def load_sources(out, a, rep, existing):
    """→ (mode, pre, sections, owner, starts, pre_src)."""
    starts, pre_src = {}, []
    parts = [] if a.no_parts else find_parts(out)
    existing_pre = split_sections(existing)[0] if existing else ""
    if parts:
        pre, sections, owner = build_from_parts(out, parts, rep, existing_pre, starts, pre_src)
        return "parts", pre, sections, owner, starts, pre_src
    pre, pre_line, secs = split_sections_lines(existing)
    sections, owner = {}, {}
    for n, _t, body, ln in secs:
        if n in sections:
            rep.error("dup_section", "раздел %d встречается в strategy.md дважды" % n, section=n)
            continue
        sections[n], owner[n], starts[n] = body, "research/strategy.md", ln
    return "in-place", pre, sections, owner, starts, ["research/strategy.md", pre_line]


def unlabeled_items(raw_neutral, pre_neutral, owner, starts, pre_src):
    items = []
    if pre_neutral and pre_src:
        for st, en, body in unlabeled_numbers(pre_neutral):
            items.append({"section": None, "file": pre_src[0], "line": pre_src[1] + st - 1, "end_line": pre_src[1] + en - 1, "text": body})
    for n in sorted(raw_neutral):
        for st, en, body in unlabeled_numbers(raw_neutral[n]):
            items.append({"section": n, "file": owner.get(n), "line": starts.get(n, 1) + st - 1, "end_line": starts.get(n, 1) + en - 1,
                          "text": body})
    return items


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="Подробности — в docstring скрипта, references/data-contract.md и references/decisions.md.")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--insert-mockups", action="store_true", help="добавить блоки «Макеты концептов» в разделы 6–10")
    ap.add_argument("--lenient", action="store_true", help="ошибки проверок считать предупреждениями (код выхода 0)")
    ap.add_argument("--strict", action="store_true", help="расхождения с decisions.json и ненаблюдаемые критерии отказа — ошибки")
    ap.add_argument("--check", action="store_true", help="только проверить и показать результат, файл strategy.md не писать")
    ap.add_argument("--no-parts", action="store_true", help="не использовать части, работать с готовым research/strategy.md")
    ap.add_argument("--require-all", action="store_true", help="отсутствие любого из разделов 1…17 — ошибка (иначе предупреждение)")
    ap.add_argument("--json", action="store_true", help="печатать отчёт JSON в stdout вместо текста")
    ap.add_argument("--list-placeholders", action="store_true", help="все ключи плейсхолдеров решений, модели и экспериментов со значениями")
    ap.add_argument("--label-unlabeled", action="store_true", help="дописать [допущение] к фрагментам с числами без метки (в исходных частях)")
    ap.add_argument("--show", type=int, default=10, help="сколько мест с числами без метки печатать (по умолчанию 10)")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if not (out / "data").is_dir():
        print("ошибка: нет папки %s/data" % out, file=sys.stderr)
        return 2
    data = Data(out)
    if a.list_placeholders:
        crit = kill_measurability(out, dec_mod.Registry(out), Report(True), False, data.cfg)
        rows = dec_mod.Registry(out, criteria=crit or None).listing()
        if a.json:
            print(json.dumps([{"placeholder": p, "value": v, "source": s} for p, v, s in rows], ensure_ascii=False, indent=2))
        else:
            for p, v, s in rows:
                print("%-36s %s" % (p, v))
            print("всего %d ключей (decisions.json, model.json, experiments.json); {rank:P…}/{deprank:P…} — из data/scores.json; "
                  "формат: {…|money}, {…|%%}, {…|0}" % len(rows))
        return 0
    strat = out / "research" / "strategy.md"
    parts = [] if a.no_parts else find_parts(out)
    if not parts and not strat.exists():
        print("ошибка: нет частей (build/parts/strategy-*.md, research/strategy-part*.md) и нет research/strategy.md", file=sys.stderr)
        return 2
    rep = Report(a.lenient)
    existing = strat.read_text(encoding="utf-8") if strat.exists() else ""
    reg = dec_mod.Registry(out)
    labeled = []
    if a.label_unlabeled and not a.check:
        _m, pre0, secs0, own0, st0, ps0 = load_sources(out, a, Report(True), existing)
        neu0, _c = substitute_decisions(secs0, reg, Report(True), neutral=True)
        pneu0 = substitute_decisions({0: pre0}, reg, Report(True), neutral=True)[0][0] if pre0 else ""
        labeled = label_unlabeled(out, unlabeled_items(neu0, pneu0, own0, st0, ps0))
        existing = strat.read_text(encoding="utf-8") if strat.exists() else ""
    mode, pre, sections, owner, starts, pre_src = load_sources(out, a, rep, existing)
    # исходный текст разделов с нейтральными значениями плейсхолдеров — для проверок с адресами в частях
    raw_neutral, _ = substitute_decisions(sections, reg, Report(True), neutral=True)
    pre_neutral = substitute_decisions({0: pre}, reg, Report(True), neutral=True)[0][0] if pre else ""
    criteria = kill_measurability(out, reg, rep, a.strict, data.cfg)
    if criteria:
        reg = dec_mod.Registry(out, criteria=criteria)
    mismatches = check_decisions(raw_neutral, owner, starts, reg, rep, a.strict)
    # плейсхолдеры, запросы макетов, блоки макетов
    sections, rank_counts = substitute_ranks(sections, data, rep)
    sections, dec_counts = substitute_decisions(sections, reg, rep)
    if pre:
        pre = substitute_decisions({0: pre}, reg, rep)[0][0]
    sections, resolved, removed = resolve_mockup_queries(sections, data, rep)
    inserted = []
    if a.insert_mockups:
        sections, inserted = insert_mockup_blocks(sections, data, rep)
    # порядок разделов
    order = [n for n in SECTIONS if n in sections] + sorted(n for n in sections if n not in SECTIONS)
    for n in sections:
        if n not in SECTIONS:
            rep.warn("unknown_section", "раздел %d вне схемы 1…17 (references/strategy-outline.md): добавлен в конец" % n, section=n)
    missing = [n for n in SECTIONS if n not in sections]
    for n in missing:
        (rep.error if a.require_all else rep.warn)("missing_section", "нет раздела %d" % n, section=n)
    chunks = ([pre] if pre else []) + [sections[n].strip() for n in order]
    text = "\n\n".join(chunks) + "\n"
    # номера строк разделов в итоговом тексте
    heads = []
    for ln, line in enumerate(text.splitlines(), 1):
        m = HEAD_RE.match(line)
        if m:
            heads.append((ln, int(m.group(1))))

    def section_of(line):
        cur = None
        for ln, n in heads:
            if ln <= line:
                cur = n
        return cur
    stats, n_urls = check_text(text, data, rep, section_of)
    depth = (data.cfg.get("strategy") or {}).get("depth")
    wc = {n: words(sections[n]) for n in order}
    for n in order:
        need = depth_min_words(depth, n, data.cfg.get("mode") == "concept")
        if need and wc[n] < need:
            rep.warn("short_section", "раздел %d: %d слов < минимума %d для глубины %s" % (n, wc[n], need, depth), section=n)
    unl = unlabeled_items(raw_neutral, pre_neutral, owner, starts, pre_src)
    if unl:
        rep.warn("unlabeled_numbers", "%d фрагментов с числами (%%, деньги) без метки [факт|оценка|допущение]: места — ниже и в "
                 "build/assemble-report.json; --label-unlabeled допишет [допущение]" % len(unl))
    repeats = find_repeats(raw_neutral, owner, starts, rep)
    written, prev_saved = False, False
    if not a.check:
        if existing and existing != text and mode == "parts":
            (out / "build").mkdir(parents=True, exist_ok=True)
            (out / "build" / "strategy.prev.md").write_text(existing, encoding="utf-8")
            prev_saved = True
        if existing != text:
            strat.parent.mkdir(parents=True, exist_ok=True)
            strat.write_text(text, encoding="utf-8")
            written = True
    substituted = dict({"rank": rank_counts["rank"], "deprank": rank_counts["deprank"]}, **dec_counts)
    report = {
        "ok": not rep.errors, "date": date.today().isoformat(), "mode": mode, "written": written, "checked_only": a.check,
        "strategy": strat.relative_to(out).as_posix(), "previous_saved": "build/strategy.prev.md" if prev_saved else None,
        "parts": sorted(set(owner.values())) if mode == "parts" else [], "section_source": {str(n): owner[n] for n in order if n in owner},
        "sections_present": order, "sections_missing": missing, "words": {str(n): wc[n] for n in order}, "words_total": sum(wc.values()),
        "substituted": substituted, "mockups_resolved": resolved, "mockups_removed": [{"proposal": p, "note": "макета для %s нет" % p} for p in removed],
        "mockups_inserted": inserted, "markers": stats, "urls_checked": n_urls,
        "unlabeled_numbers": {"count": len(unl), "examples": [dict(u, text=u["text"][:140]) for u in unl[:100]]},
        "labeled": [{"file": f, "line": ln, "was": was} for f, ln, was, _new in labeled],
        "decisions": {"present": reg.decisions is not None, "mismatches": mismatches},
        "kill_criteria": criteria,
        "repeats": repeats,
        "errors": rep.errors, "warnings": rep.warnings, "notes": rep.notes,
        "counts": {"errors": len(rep.errors), "warnings": len(rep.warnings), "notes": len(rep.notes)},
    }
    if not a.check:
        dump_json(out / "build" / "assemble-report.json", report)
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(report, strat, a)
    return 1 if rep.errors else 0


def print_text(rp, strat, a):
    print("%s: %s; разделов %d из 17, слов %d" % (("проверено (файл не записан)" if a.check else ("записано " + str(strat)) if rp["written"] else "без изменений " + str(strat)),
                                                  "режим «%s»" % rp["mode"], len(rp["sections_present"]), rp["words_total"]))
    subs = ", ".join(("{%s:…} × %d" if k in ("rank", "deprank", "bet", "fork", "model", "exp") else "{%s} × %d") % (k, v)
                     for k, v in rp["substituted"].items() if v)
    if subs:
        print("подставлено: %s" % subs)
    for f, ln, was in ((x["file"], x["line"], x["was"]) for x in rp.get("labeled") or []):
        print("метка [допущение] добавлена: %s:%s — %s" % (f, ln, was))
    for m in rp["mockups_resolved"]:
        print("макет разрешён: ?%s → %s (раздел %s)" % (m["proposal"], m["key"], m["section"]))
    for n in rp["notes"]:
        print("заметка: %s" % n["message"])
    for i in rp["mockups_inserted"]:
        print("вставлен блок макетов в раздел %d: %s" % (i["section"], ", ".join(i["keys"])))
    for c in rp.get("kill_criteria") or []:
        print("критерий отказа ставки %s «%s»: %s — n %s, срок %s нед.; %s" % (c["bet"], c.get("metric"), c.get("status_text"),
                                                                           c.get("n", "—"), c.get("weeks", "—"), c.get("reason", "")))
    for e in rp["errors"]:
        print("ОШИБКА [%s]%s%s: %s" % (e["code"], " раздел %s" % e["section"] if e.get("section") else "", " стр. %s" % e["line"] if e.get("line") else "", e["message"]))
    groups = {}
    for w in rp["warnings"]:
        groups.setdefault(w["code"], []).append(w)
    for code, items in groups.items():
        print("предупреждение [%s] × %d" % (code, len(items)))
        if code == "unlabeled_numbers":
            ex = rp["unlabeled_numbers"]["examples"]
            for u in ex[:max(0, a.show)]:
                print("    %s:%s%s: %s" % (u["file"], u["line"], " (раздел %s)" % u["section"] if u.get("section") else "", u["text"][:110]))
            if rp["unlabeled_numbers"]["count"] > a.show:
                print("    … и ещё %d (полный список — build/assemble-report.json, --show N)" % (rp["unlabeled_numbers"]["count"] - a.show))
            continue
        for w in items[:5]:
            print("    %s%s" % ("стр. %s: " % w["line"] if w.get("line") else "", w["message"]))
        if len(items) > 5:
            print("    … и ещё %d (полный список — build/assemble-report.json)" % (len(items) - 5))
    rn = (rp.get("repeats") or {}).get("numbers") or []
    if rn:
        print("общие числа в разделах 2/3/6/7: %s" % "; ".join("%s (%s)" % (x["value"], "↔".join(str(s) for s in x["sections"])) for x in rn[:10]))
    print("итог: ошибок %d, предупреждений %d%s" % (rp["counts"]["errors"], rp["counts"]["warnings"], "" if a.check else "; отчёт build/assemble-report.json"))


if __name__ == "__main__":
    sys.exit(main())
