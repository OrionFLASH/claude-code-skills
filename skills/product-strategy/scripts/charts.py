#!/usr/bin/env python3
"""Графики стратегии в SVG на стандартной библиотеке (без matplotlib) → <OUT>/charts/<key>.svg + charts-index.json.

  charts.py <OUT> [--only key1,key2] [--top N]   строит графики + charts/<ключ>.meta.json и сразу проверяет пояснения
  charts.py <OUT> --list-keys        JSON {"available": [...], "skipped": {"ключ": "причина"}} по данным, без построения
  charts.py <OUT> --check-meta       только проверка разметки и пояснений (код 1 при проблемах)
  charts.py <OUT> --list-generic     JSON элементов с обобщённым пояснением — что дописать в data/chart-notes.json

Интерактивность (1.4, references/interactive-site.md, п. 2.1–2.2): каждый значимый элемент графика — <g data-ps-el="<id>"
tabindex="0" role="button" aria-label="…" class="ps-el ps-<вид>"> с <title>; корень <svg data-ps-chart="<ключ>">;
подписи к элементам — data-ps-ref, группы для подсветки из легенды — data-ps-group / data-ps-highlight. Пояснения
(что это, что значит, что делать, метрики, ссылки) — charts/<ключ>.meta.json (chart_meta.py): data/chart-notes.json →
данные прогона → references/chart-glossary.ru.json; в charts-index.json у записи поле "meta".

Источники: data/scores.json, proposals.json, sensitivity.json, registry-check.json, gantt.json, model.json,
keywords.json, events.json, competitors.json, critical-path.json, north-star.json (необязательно), build/run-config.json.
Каждый график пропускается, если для него нет данных (причина — в выводе и в --list-keys). gantt строится, как только
есть data/gantt.json (можно вызвать отдельно: --only gantt). Ключи и разделы — data-contract.md (charts-index.json).
Новые в 1.1: critical-path (цепочка зависимостей из critical-path.json), channel-mix (каналы привлечения по
предложениям category=acquisition: доля по числу и по composite), kpi-tree (North Star → входные метрики → предложения
по effect_kpi), keywords-clusters (кластеры запросов по числу и конкуренции — работает и без объёмов). Подписи функций
конкурентов — из features_labels (иначе человекочитаемо из snake_case), слова не режутся. Профиль zero-budget-solo:
cac-ltv — часы на активированного и выручка на час, payback — безубыточность по времени; при малом числе платящих
подписи содержат абсолютные суммы.
Палитра: из <OUT>/mockups/tokens.css (CSS-переменные с hex-цветами: accent/primary/brand/… с контрастом ≥ 3:1 к
белому идут первыми, text/ink/fg — цвет текста), иначе встроенная палитра Okabe–Ito, безопасная для дальтоников;
категории дополнительно различаются формой маркера. Фон светлый. Подписи переносятся по словам, ничего не
обрезается многоточием; у матрицы усилие–влияние полные названия топа — в панели справа.
SVG — валидный XML без внешних ссылок (нет href/src, нет @import), шрифты системные.
Только стандартная библиотека.
"""
import argparse
import json
import math
import re
import statistics
import sys
from collections import Counter, OrderedDict
from contextlib import contextmanager
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chart_meta  # noqa: E402

REG = chart_meta.Registry()     # интерактивные элементы текущего графика (сбрасывается build_all перед каждым графиком)
CONCEPT = [False]               # режим идеи (run-config mode: concept) — подписи «продукта ещё нет»
sid = chart_meta.sid

# ---------------------------------------------------------------- палитра и типографика
OKABE_ITO = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#8C6D31", "#882255", "#117733", "#7F7F7F"]
THEME = {"bg": "#FFFFFF", "panel": "#F6F8FA", "ink": "#1F2328", "muted": "#57606A", "grid": "#E4E7EB", "axis": "#9AA1A9",
         "good": "#009E73", "bad": "#D55E00", "neutral": "#9AA1A9", "seq_lo": "#F2F6FB"}
PAL = list(OKABE_ITO)
FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
PAD = 24
TITLE_FS, CAP_FS, SRC_FS = 18, 13, 11

CAT_RU = OrderedDict([("product", "Продукт"), ("acquisition", "Привлечение"), ("conversion", "Конверсия"),
                      ("retention", "Удержание"), ("monetization", "Монетизация"), ("analytics", "Аналитика"),
                      ("partnerships", "Партнёрства"), ("localization", "Локализация"), ("new_lines", "Новые линии"),
                      ("platform", "Платформа")])
HORIZON_RU = OrderedDict([("now", "Сейчас (0–3 мес.)"), ("next", "Дальше (3–12 мес.)"), ("later", "Позже (1–2 года)"),
                          ("vision", "Видение (2+ года)")])
QUAD_RU = {"quick_win": "Быстрые победы", "big_bet": "Крупные ставки", "filler": "Заполнители", "money_pit": "Ловушки стоимости"}
SCEN_RU = OrderedDict([("pessimistic", "Пессимистичный"), ("base", "Базовый"), ("optimistic", "Оптимистичный")])
SCEN_PAL = {"pessimistic": 3, "base": 0, "optimistic": 2}   # индексы в PAL — одинаковые цвета сценариев на всех графиках


def scol(name):
    return PAL[SCEN_PAL.get(name, 0) % len(PAL)]
GROUP_RU = {"composite": "вес", "value": "ценность", "cost": "стоимость", "risk": "риск"}
PARAM_RU = {"rice": "RICE", "ice": "ICE", "wsjf": "WSJF", "risk_adjusted": "с поправкой на риск", "value": "экспертная ценность",
            "cost": "экспертная стоимость", "risk": "экспертный риск", "effort_days": "трудозатраты", "money": "деньги",
            "time_to_result": "срок до результата", "dependencies": "зависимости", "reach": "охват", "impact": "влияние",
            "acquisition": "привлечение", "activation": "активация", "conversion": "конверсия", "retention": "удержание",
            "revenue": "доход", "virality": "вирусность", "seo": "SEO", "trust": "доверие", "moat": "защитимость",
            "fit": "соответствие", "demand": "спрос", "season": "сезон", "legal": "юридический", "ip": "IP и лицензии",
            "platform": "правила площадок", "privacy": "приватность", "tech": "технический", "reputation": "репутация"}
KNOWN_KEYS = ["effort-impact", "bubble", "metrics-heatmap", "radar-top10", "pareto", "tornado", "dist-category",
              "dist-evidence", "dist-horizon", "gantt", "funnel", "forecast-fan", "cac-ltv", "payback",
              "keywords-volume", "events-calendar", "competitors-heatmap", "critical-path", "channel-mix", "kpi-tree",
              "keywords-clusters"]


def hex_rgb(h):
    h = h.lstrip("#")
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h[:3])
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_hex(rgb):
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def lum(h):
    def ch(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = hex_rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a, b, t):
    ra, rb = hex_rgb(a), hex_rgb(b)
    return rgb_hex([x + (y - x) * t for x, y in zip(ra, rb)])


def load_palette(out_dir):
    """Палитра из mockups/tokens.css (если есть) + Okabe–Ito."""
    global PAL, FONT
    path = out_dir / "mockups" / "tokens.css"
    PAL = list(OKABE_ITO)
    if not path.exists():
        return "встроенная (Okabe–Ito)"
    css = path.read_text(encoding="utf-8", errors="replace")
    brand, used = [], []
    for name, val in re.findall(r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\b", css):
        n = name.lower()
        if re.search(r"(accent|primary|brand|secondary|chart|highlight|success|info|warning|danger)", n):
            if contrast(val, THEME["bg"]) >= 3.0:
                brand.append(rgb_hex(hex_rgb(val)))
        elif re.search(r"(^|-)(text|ink|fg|foreground)($|-)", n) and contrast(val, THEME["bg"]) >= 7.0 and "ink" not in used:
            THEME["ink"] = rgb_hex(hex_rgb(val))
            used.append("ink")
    m = re.search(r"--font[\w-]*\s*:\s*([^;]+);", css)
    if m and "url(" not in m.group(1):
        fam = m.group(1).strip().replace('"', "'")
        if fam and "<" not in fam and "&" not in fam:
            FONT = fam + ", " + FONT
    picked = []
    for c in brand:
        if all(sum(abs(x - y) for x, y in zip(hex_rgb(c), hex_rgb(p))) > 90 for p in picked):
            picked.append(c)
    picked = picked[:3]
    rest = [c for c in OKABE_ITO if all(sum(abs(x - y) for x, y in zip(hex_rgb(c), hex_rgb(p))) > 90 for p in picked)]
    PAL = picked + rest
    return "tokens.css (%d цв.) + Okabe–Ito" % len(picked) if picked else "встроенная (Okabe–Ito; в tokens.css нет подходящих цветов)"


# ---------------------------------------------------------------- текст
def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def text_w(s, size, bold=False):
    """Оценка ширины строки в px (с запасом, для системных sans-serif)."""
    w = 0.0
    for ch in str(s):
        if ch == " ":
            w += 0.30
        elif ch in "il.,:;!|'`()[]ІїјI":
            w += 0.32
        elif ch in "mwMWШЩЖФЮмшщжфю%@—":
            w += 0.90
        elif ch.isdigit():
            w += 0.58
        elif ch.isupper():
            w += 0.70
        elif "а" <= ch <= "я" or ch == "ё":
            w += 0.60
        else:
            w += 0.56
    return w * size * (1.08 if bold else 1.0)


def wrap(s, max_px, size, bold=False):
    """Перенос по словам в пределах max_px; слишком длинное слово режется по символам (без «…»)."""
    words = str(s).split()
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if text_w(cand, size, bold) <= max_px:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        while text_w(w, size, bold) > max_px and len(w) > 1:
            k = len(w)
            while k > 1 and text_w(w[:k], size, bold) > max_px:
                k -= 1
            lines.append(w[:k])
            w = w[k:]
        cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def plural(n, forms):
    """Русское склонение: plural(5, ("предложение", "предложения", "предложений"))."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def fmt(x, nd=0):
    """Число по-русски: пробел-разделитель тысяч, десятичная запятая."""
    if x is None:
        return "—"
    if nd == 0:
        s = "{:,.0f}".format(x)
    else:
        s = "{:,.{}f}".format(x, nd)
    return s.replace(",", " ").replace(".", ",")


# ---------------------------------------------------------------- SVG
class Chart:
    """Холст графика: шапка (заголовок + вывод), тело, подвал с источником."""

    def __init__(self, width, title, caption, source=None):
        self.W = width
        self.title, self.caption, self.source = title, caption, source
        self.el = []
        self.tl = wrap(title, width - 2 * PAD, TITLE_FS, True)
        self.cl = wrap(caption, width - 2 * PAD, CAP_FS) if caption else []
        self.top = PAD + len(self.tl) * TITLE_FS * 1.3 + (6 + len(self.cl) * CAP_FS * 1.4 if self.cl else 0) + 18
        self.sl = wrap(source, width - 2 * PAD, SRC_FS) if source else []

    # примитивы
    def add(self, s):
        self.el.append(s)

    # интерактивные элементы (references/interactive-site.md, п. 2.1): <g data-ps-el tabindex role aria-label class>
    def open_el(self, eid, label, kind, info=None, groups=None, highlight=None):
        """Открыть группу-элемент; возвращает уникальный id. Внешний вид не меняется (<g> без стилей)."""
        eid = REG.add(eid, label, kind, info, highlight)
        kind = REG.els[eid]["kind"]
        a = ' data-ps-el="%s" tabindex="0" role="button" aria-label="%s" class="ps-el ps-%s"' % (esc(eid), esc(label), kind)
        if groups:
            a += ' data-ps-group="%s"' % esc(" ".join(sid(g) for g in groups if g))
        if highlight:
            REG.els[eid]["highlight"] = highlight = sid(highlight)
            a += ' data-ps-highlight="%s"' % esc(highlight)
        self.add("<g%s><title>%s</title>" % (a, esc(label)))
        return eid

    def close_el(self):
        self.add("</g>")

    @contextmanager
    def item(self, eid, label, kind, info=None, groups=None, highlight=None):
        eid = self.open_el(eid, label, kind, info, groups, highlight)
        yield eid
        self.close_el()

    @contextmanager
    def ref(self, target):
        """Подпись/строка, относящаяся к элементу target (клик по ней — тот же элемент): data-ps-ref."""
        self.add('<g class="ps-ref" data-ps-ref="%s">' % esc(target))
        yield
        self.add("</g>")

    def hit(self, pts, sw=12):
        """Невидимая широкая линия для попадания мышью по тонкой линии (stroke-opacity 0 — на вид не влияет)."""
        self.add('<polyline points="%s" fill="none" stroke="#000000" stroke-opacity="0" stroke-width="%s"/>'
                 % (" ".join("%.1f,%.1f" % p for p in pts), sw))

    def rect(self, x, y, w, h, fill, stroke=None, rx=0, op=None, sw=1):
        a = ' stroke="%s" stroke-width="%s"' % (stroke, sw) if stroke else ""
        o = ' fill-opacity="%.3f"' % op if op is not None else ""
        self.add('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%s" fill="%s"%s%s/>' % (x, y, max(w, 0), max(h, 0), rx, fill, a, o))

    def line(self, x1, y1, x2, y2, stroke, sw=1, dash=None, op=None):
        d = ' stroke-dasharray="%s"' % dash if dash else ""
        o = ' stroke-opacity="%.3f"' % op if op is not None else ""
        self.add('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%s"%s%s/>' % (x1, y1, x2, y2, stroke, sw, d, o))

    def circle(self, cx, cy, r, fill, stroke=None, op=None, sw=1):
        a = ' stroke="%s" stroke-width="%s"' % (stroke, sw) if stroke else ""
        o = ' fill-opacity="%.3f"' % op if op is not None else ""
        self.add('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s"%s%s/>' % (cx, cy, r, fill, a, o))

    def poly(self, pts, fill, stroke=None, op=None, sw=1, closed=True):
        tag = "polygon" if closed else "polyline"
        a = ' stroke="%s" stroke-width="%s" stroke-linejoin="round"' % (stroke, sw) if stroke else ""
        o = ' fill-opacity="%.3f"' % op if op is not None else ""
        self.add('<%s points="%s" fill="%s"%s%s/>' % (tag, " ".join("%.1f,%.1f" % p for p in pts), fill, a, o))

    def text(self, x, y, s, size=12, fill=None, anchor="start", bold=False, baseline=None):
        b = ' font-weight="600"' if bold else ""
        bl = ' dominant-baseline="%s"' % baseline if baseline else ""
        self.add('<text x="%.1f" y="%.1f" font-size="%s" fill="%s" text-anchor="%s"%s%s>%s</text>'
                 % (x, y, size, fill or THEME["ink"], anchor, b, bl, esc(s)))

    def lines(self, x, y, lines, size=12, fill=None, anchor="start", bold=False, lh=1.25):
        """Многострочный текст; y — базовая линия первой строки."""
        for k, ln in enumerate(lines):
            self.text(x, y + k * size * lh, ln, size, fill, anchor, bold)

    def marker(self, shape, cx, cy, r, fill, stroke="#FFFFFF"):
        if shape == 0:
            self.circle(cx, cy, r, fill, stroke, sw=1)
            return
        k = shape % 7
        if k == 1:
            pts = [(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r)]
        elif k == 2:
            pts = [(cx, cy - r * 1.2), (cx + r * 1.1, cy + r * 0.8), (cx - r * 1.1, cy + r * 0.8)]
        elif k == 3:
            pts = [(cx, cy - r * 1.3), (cx + r * 1.1, cy), (cx, cy + r * 1.3), (cx - r * 1.1, cy)]
        elif k == 4:
            pts = [(cx, cy + r * 1.2), (cx + r * 1.1, cy - r * 0.8), (cx - r * 1.1, cy - r * 0.8)]
        elif k == 5:
            pts = [(cx + r * 1.15 * math.cos(math.pi / 3 * i), cy + r * 1.15 * math.sin(math.pi / 3 * i)) for i in range(6)]
        else:
            pts = [(cx + r * 1.2 * math.cos(-math.pi / 2 + 2 * math.pi / 5 * i), cy + r * 1.2 * math.sin(-math.pi / 2 + 2 * math.pi / 5 * i)) for i in range(5)]
        self.poly(pts, fill, stroke, sw=1)

    def finish(self, body_h):
        H = self.top + body_h + (10 + len(self.sl) * SRC_FS * 1.35 if self.sl else 0) + PAD
        head = []
        y = PAD + TITLE_FS
        for k, ln in enumerate(self.tl):
            head.append('<text x="%d" y="%.1f" font-size="%d" font-weight="700" fill="%s">%s</text>' % (PAD, y + k * TITLE_FS * 1.3, TITLE_FS, THEME["ink"], esc(ln)))
        y += len(self.tl) * TITLE_FS * 1.3 - TITLE_FS * 0.3 + 6 + CAP_FS
        for k, ln in enumerate(self.cl):
            head.append('<text x="%d" y="%.1f" font-size="%d" fill="%s">%s</text>' % (PAD, y + k * CAP_FS * 1.4, CAP_FS, THEME["muted"], esc(ln)))
        foot = []
        fy = self.top + body_h + 10 + SRC_FS
        for k, ln in enumerate(self.sl):
            foot.append('<text x="%d" y="%.1f" font-size="%d" fill="%s">%s</text>' % (PAD, fy + k * SRC_FS * 1.35, SRC_FS, THEME["muted"], esc(ln)))
        body = "\n".join(head + self.el + foot)
        used = {g for v in re.findall(r'data-ps-group="([^"]*)"', body) for g in v.split()}
        for el in REG.els.values():      # подсветка из легенды без единого элемента группы — убрать
            h = el.get("highlight")
            if h and h not in used:
                el["highlight"] = None
                body = body.replace(' data-ps-highlight="%s"' % esc(h), "")
        inter = ' role="group" aria-label="{t}" class="ps-chart"' if REG.els else ' role="img"'
        key = ' data-ps-chart="%s"' % esc(REG.key) if REG.key else ""
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}"' + key + inter + ' '
                'font-family="{f}">\n<title>{t}</title>\n<desc>{d}</desc>\n<rect x="0" y="0" width="{w}" height="{h}" fill="{bg}"/>\n{body}\n</svg>\n'
                ).format(w=self.W, h=int(math.ceil(H)), f=esc(FONT), t=esc(self.title), d=esc(self.caption or ""),
                         bg=THEME["bg"], body=body)


def nice_ticks(lo, hi, n=5, cover=True):
    """«Круглые» деления оси; cover=True — последнее деление не меньше hi (ось покрывает данные)."""
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / max(1, n)
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=10 * mag)
    start = math.floor(lo / step) * step
    ticks, t = [], start
    while t <= hi + step * 1e-9:
        if t >= lo - step * 1e-9:
            ticks.append(round(t, 10))
        t += step
    if cover and ticks and ticks[-1] < hi - step * 1e-9:
        ticks.append(round(ticks[-1] + step, 10))
    return ticks, step


def log_ticks(lo, hi):
    out = []
    e = math.floor(math.log10(max(lo, 1e-9)))
    while 10 ** e <= hi * 1.0001:
        for m in (1, 2, 5):
            v = m * 10 ** e
            if lo * 0.9999 <= v <= hi * 1.0001:
                out.append(v)
        e += 1
    return out


def overlaps(a, b, pad=2):
    return not (a[0] + a[2] + pad <= b[0] or b[0] + b[2] + pad <= a[0] or a[1] + a[3] + pad <= b[1] or b[1] + b[3] + pad <= a[1])


def place_labels(c, pts, labels, box, obstacles, size=11, color=None, bold=True, reserved=None, refs=None):
    """Жадная раскладка подписей точек без наложений: кольца смещений вокруг точки, проверка рамки графика,
    других подписей и маркеров; при отходе от точки — тонкая выноска. Возвращает число вынужденных наложений.
    refs — id элементов, к которым относятся подписи (data-ps-ref: клик по подписи = клик по точке)."""
    placed, forced = list(reserved or []), 0
    refs = list(refs or [])
    x0, y0, x1, y1 = box
    obs = [(ox - orr, oy - orr, 2 * orr, 2 * orr) for ox, oy, orr in obstacles]
    dirs = [(1, -0.2), (1, 0.9), (-1, -0.2), (-1, 0.9), (0, -1.2), (0, 1.6), (1, -1.2), (-1, -1.2), (1, 1.8), (-1, 1.8)]
    h = size * 1.15
    for k, ((px, py), lab) in enumerate(zip(pts, labels)):
        w = text_w(lab, size, bold)
        best = None
        for r in (7, 12, 18, 26, 36, 48, 62, 80):
            for dx, dy in dirs:
                lx, ly = px + dx * r, py + dy * r
                bx = lx if dx > 0 else (lx - w if dx < 0 else lx - w / 2)
                bb = (bx, ly - h / 2, w, h)
                if bb[0] < x0 or bb[0] + w > x1 or bb[1] < y0 or bb[1] + h > y1:
                    continue
                if any(overlaps(bb, o) for o in placed) or any(overlaps(bb, o, 0) for o in obs):
                    continue
                best = (bb, r)
                break
            if best:
                break
        if best is None:
            forced += 1
            bx = min(max(px + 7, x0), x1 - w)
            best = ((bx, py - h / 2 - 9, w, h), 7)
        bb, r = best
        if k < len(refs) and refs[k]:
            c.add('<g class="ps-ref" data-ps-ref="%s">' % esc(refs[k]))
        if r > 7:
            ax = min(max(px, bb[0]), bb[0] + bb[2])
            ay = min(max(py, bb[1]), bb[1] + bb[3])
            c.line(px, py, ax, ay, THEME["axis"], 0.8)
        c.rect(bb[0] - 1, bb[1], bb[2] + 2, bb[3], THEME["bg"], op=0.85)
        c.text(bb[0], bb[1] + h * 0.8, lab, size, color or THEME["ink"], "start", bold)
        if k < len(refs) and refs[k]:
            c.add("</g>")
        placed.append(bb)
    return forced


def legend_row(c, items, x, y, max_w, size=12, els=None):
    """Горизонтальная легенда с переносом; items: (label, color, shape|None). Возвращает занятую высоту.
    els — параллельный список {id, info, highlight, label?} | None: пункт легенды становится интерактивным элементом."""
    cx, cy = x, y
    row_h = size * 1.7
    els = list(els or [])
    for k, (lab, col, shape) in enumerate(items):
        w = 18 + text_w(lab, size) + 18
        if cx + w > x + max_w and cx > x:
            cx, cy = x, cy + row_h
        e = els[k] if k < len(els) else None
        if e:
            c.open_el(e["id"], e.get("label") or "Легенда: " + lab, "legend", e.get("info"), highlight=e.get("highlight"))
        if shape is None:
            c.rect(cx, cy - size * 0.75, 12, 12, col, rx=2)
        else:
            c.marker(shape, cx + 6, cy - size * 0.3, 5.5, col)
        c.text(cx + 18, cy, lab, size, THEME["ink"])
        if e:
            c.close_el()
        cx += w
    return cy - y + row_h


# ---------------------------------------------------------------- данные
def load(out_dir, rel):
    p = out_dir / rel
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def cat_color(cat):
    keys = list(CAT_RU)
    i = keys.index(cat) if cat in keys else len(keys)
    return PAL[i % len(PAL)], i


def cat_name(cat):
    return CAT_RU.get(cat, str(cat or "без категории"))


# ---------------------------------------------------------------- помощники разметки
def gl(*path):
    """Путь в глоссарии references/chart-glossary.ru.json (для info["gloss"])."""
    return [list(path)]


def top_ids(rows, n=3):
    return [r["id"] for r in sorted(rows, key=lambda r: r.get("rank", 10 ** 6))[:n]]


def cat_legend_els(cats, S):
    """Интерактивные пункты легенды категорий: подсвечивают точки группы g-cat-<категория>."""
    out = []
    for k in cats:
        rows = [r for r in S if r.get("category") == k]
        out.append({"id": "legend-cat-%s" % sid(k), "label": "Категория «%s»: %d %s" % (cat_name(k), len(rows), plural(len(rows), ("предложение", "предложения", "предложений"))),
                    "info": {"gloss": gl("categories", k), "cat": k, "related": top_ids(rows),
                             "meaning": "На графике %d %s этой категории; лучшие по рангу: %s." % (
                                 len(rows), plural(len(rows), ("предложение", "предложения", "предложений")), ", ".join(top_ids(rows)) or "—")},
                    "highlight": "g-cat-%s" % sid(k)})
    return out


def pt_label(r, extra=""):
    return "%s — %s%s" % (r["id"], r.get("title", ""), (": " + extra) if extra else "")


# ---------------------------------------------------------------- графики оценок
def ch_effort_impact(S, top_n):
    n = len(S)
    top = S[:min(top_n, n)]
    W = 1160
    mv = statistics.median(r["value_index"] for r in S)
    mc = statistics.median(r["cost_index"] for r in S)
    qc = Counter(r.get("quadrant") for r in S)
    title = "Матрица усилие–влияние: быстрых побед — %d, крупных ставок — %d из %d" % (qc.get("quick_win", 0), qc.get("big_bet", 0), n)
    cap = ("Квадранты по медианам ценности и стоимости; подписаны топ-%d по composite, полные названия — справа. "
           "Лучшие кандидаты — левый верхний угол." % len(top))
    c = Chart(W, title, cap, "Источник: data/scores.json (score.py); индексы 1–5 — оценка по якорям methodology-anchors.md")
    panel_x = 760
    # панель справа: ранг, id, полное название с переносом
    py = c.top + 4
    c.text(panel_x, py + 12, "Топ-%d по composite" % len(top), 13, THEME["ink"], bold=True)
    py += 26
    plines = []
    for r in top:
        tl = wrap(r.get("title", ""), W - PAD - (panel_x + 78), 12)
        plines.append((r, tl, py))
        py += len(tl) * 15 + 6
    panel_h = py - c.top
    ph = max(470, panel_h)
    x0, x1, y0, y1 = PAD + 46, panel_x - 30, c.top + 8, c.top + ph - 62
    for r, tl, yy in plines:
        with c.ref(r["id"]):
            c.text(panel_x, yy + 11, "%d." % r["rank"], 12, THEME["muted"])
            c.text(panel_x + 28, yy + 11, r["id"], 12, PAL[0], bold=True)
            c.lines(panel_x + 78, yy + 11, tl, 12, THEME["ink"], lh=1.25)
    vx = [r["cost_index"] for r in S]
    vy = [r["value_index"] for r in S]
    lo_x, hi_x = max(1.0, math.floor((min(vx) - 0.15) * 2) / 2), min(5.0, math.ceil((max(vx) + 0.15) * 2) / 2)
    lo_y, hi_y = max(1.0, math.floor((min(vy) - 0.15) * 2) / 2), min(5.0, math.ceil((max(vy) + 0.15) * 2) / 2)
    if hi_x - lo_x < 1:
        lo_x, hi_x = max(1.0, lo_x - 0.5), min(5.0, hi_x + 0.5)
    if hi_y - lo_y < 1:
        lo_y, hi_y = max(1.0, lo_y - 0.5), min(5.0, hi_y + 0.5)
    tx, ty = nice_ticks(lo_x, hi_x, 8, False)[0], nice_ticks(lo_y, hi_y, 8, False)[0]
    # поля, чтобы маркеры на краях шкалы и подписи квадрантов не налезали на рамку
    lo_x, hi_x = lo_x - 0.08 * (hi_x - lo_x), hi_x + 0.04 * (hi_x - lo_x)
    lo_y, hi_y = lo_y - 0.12 * (hi_y - lo_y), hi_y + 0.12 * (hi_y - lo_y)
    sx = lambda v: x0 + (v - lo_x) / (hi_x - lo_x) * (x1 - x0)
    sy = lambda v: y1 - (v - lo_y) / (hi_y - lo_y) * (y1 - y0)
    c.rect(x0, y0, sx(mc) - x0, sy(mv) - y0, mix(PAL[2], "#FFFFFF", 0.9))
    for t in tx:
        c.line(sx(t), y0, sx(t), y1, THEME["grid"])
        c.text(sx(t), y1 + 16, fmt(t, 1), 11, THEME["muted"], "middle")
    for t in ty:
        c.line(x0, sy(t), x1, sy(t), THEME["grid"])
        c.text(x0 - 6, sy(t) + 4, fmt(t, 1), 11, THEME["muted"], "end")
    c.line(sx(mc), y0, sx(mc), y1, THEME["axis"], 1.2, "5 4")
    c.line(x0, sy(mv), x1, sy(mv), THEME["axis"], 1.2, "5 4")
    quads = [(x0 + 6, y0 + 4, "start", QUAD_RU["quick_win"], PAL[2]), (x1 - 6, y0 + 4, "end", QUAD_RU["big_bet"], THEME["muted"]),
             (x0 + 6, y1 - 18, "start", QUAD_RU["filler"], THEME["muted"]), (x1 - 6, y1 - 18, "end", QUAD_RU["money_pit"], THEME["muted"])]
    qboxes = [((qx if qa == "start" else qx - text_w(qt, 12, True)) - 3, qy - 1, text_w(qt, 12, True) + 6, 17, 0) for qx, qy, qa, qt, _ in quads]
    with c.item("axis-x", "Ось усилий: индекс стоимости, медиана реестра %s" % fmt(mc, 1), "axis",
                {"gloss": gl("charts", "effort-impact", "elements", "axis-x"),
                 "meaning": "Медиана стоимости по реестру — %s: правее неё предложения дороже половины реестра." % fmt(mc, 1)}):
        c.text((x0 + x1) / 2, y1 + 34, "Усилие — индекс стоимости (1 — дёшево, 5 — дорого)", 12, THEME["ink"], "middle")
    with c.item("axis-y", "Ось эффекта: индекс ценности, медиана реестра %s" % fmt(mv, 1), "axis",
                {"gloss": gl("charts", "effort-impact", "elements", "axis-y"),
                 "meaning": "Медиана ценности по реестру — %s: выше неё предложения ценнее половины реестра." % fmt(mv, 1)}):
        c.add('<text x="%.1f" y="%.1f" font-size="12" fill="%s" text-anchor="middle" transform="rotate(-90 %.1f %.1f)">%s</text>'
              % (PAD + 8, (y0 + y1) / 2, THEME["ink"], PAD + 8, (y0 + y1) / 2, esc("Ценность — индекс от 1 до 5")))
    tids = {r["id"] for r in top}
    for r in sorted(S, key=lambda r: r["id"] in tids):
        col, shp = cat_color(r.get("category"))
        q = r.get("quadrant")
        qn = QUAD_RU.get(q, "вне квадранта")
        info = {"pid": r["id"], "gloss": gl("quadrants", q) if q in QUAD_RU else None,
                "meaning": "Квадрант «%s»: ценность %s из 5 при стоимости %s из 5 (медианы реестра — %s и %s)." % (
                    qn, fmt(r["value_index"], 1), fmt(r["cost_index"], 1), fmt(mv, 1), fmt(mc, 1))}
        with c.item(r["id"], pt_label(r, "%s, ценность %s, стоимость %s" % (qn.lower(), fmt(r["value_index"], 1), fmt(r["cost_index"], 1))),
                    "point", info, groups=["g-cat-%s" % r.get("category"), "g-quad-%s" % q]):
            c.marker(shp, sx(r["cost_index"]), sy(r["value_index"]), 6.5 if r["id"] in tids else 5, col)
    qkeys = ["quick_win", "big_bet", "filler", "money_pit"]
    for (qx, qy, qa, qt, qc), qb, qk in zip(quads, qboxes, qkeys):
        rows = [r for r in S if r.get("quadrant") == qk]
        with c.item("quad-%s" % qk, "Квадрант «%s»: %d %s" % (qt, len(rows), plural(len(rows), ("предложение", "предложения", "предложений"))), "area",
                    {"gloss": gl("quadrants", qk), "related": top_ids(rows), "registry": {"quadrant": qk},
                     "meaning": "В квадранте %d из %d %s; лучшие по рангу: %s." % (
                         len(rows), n, plural(n, ("предложения", "предложений", "предложений")), ", ".join(top_ids(rows)) or "нет")},
                    highlight="g-quad-%s" % qk):
            c.rect(qb[0], qb[1], qb[2], qb[3], THEME["bg"], op=0.85, rx=3)
            c.text(qx, qy + 12, qt, 12, qc, qa, True)
    obstacles = [(sx(r["cost_index"]), sy(r["value_index"]), 7) for r in S]
    place_labels(c, [(sx(r["cost_index"]), sy(r["value_index"])) for r in top], [r["id"] for r in top],
                 (x0, y0, x1, y1), obstacles, 11, reserved=[b[:4] for b in qboxes], refs=[r["id"] for r in top])
    cats = [k for k in CAT_RU if any(r.get("category") == k for r in S)] + sorted({r.get("category") for r in S if r.get("category") not in CAT_RU}, key=str)
    legend_row(c, [(cat_name(k), cat_color(k)[0], cat_color(k)[1]) for k in cats], x0, y1 + 56, x1 - x0, 11, els=cat_legend_els(cats, S))
    return c.finish(ph + 10), title, cap


def ch_bubble(S, top_n):
    n = len(S)
    top = S[:min(10, n)]
    W = 960
    hi_risk = sum(1 for r in S if r["risk_index"] >= 3)
    title = "Пузырьковая диаграмма: влияние, трудозатраты и уверенность"
    qw = [r for r in S if r["value_index"] >= 3.5 and r["confidence_calc"] >= 0.7]
    cap = ("Размер круга — расчётная уверенность, цвет — риск. Высокая ценность (≥ 3,5) при уверенности ≥ 0,7: %d; "
           "высокий риск (≥ 3): %d." % (len(qw), hi_risk))
    c = Chart(W, title, cap, "Источник: data/scores.json; трудозатраты — середина диапазона effort_days, логарифмическая шкала")
    ph = 470
    x0, x1, y0, y1 = PAD + 46, W - PAD - 10, c.top + 8, c.top + ph - 80
    xs = [max(0.5, r["effort_days_mid"]) for r in S]
    lo, hi = min(xs), max(xs)
    lo, hi = 10 ** math.floor(math.log10(lo)), 10 ** math.ceil(math.log10(hi))
    if hi <= lo:
        hi = lo * 10
    sx = lambda v: x0 + (math.log10(max(v, lo)) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * (x1 - x0)
    vy = [r["value_index"] for r in S]
    lo_y, hi_y = max(1.0, math.floor(min(vy) * 2) / 2 - 0.5), min(5.0, math.ceil(max(vy) * 2) / 2 + 0.5)
    yt = nice_ticks(lo_y, hi_y, 8, False)[0]
    lo_y, hi_y = lo_y - 0.1 * (hi_y - lo_y), hi_y + 0.1 * (hi_y - lo_y)
    sy = lambda v: y1 - (v - lo_y) / (hi_y - lo_y) * (y1 - y0)
    for t in log_ticks(lo, hi):
        c.line(sx(t), y0, sx(t), y1, THEME["grid"])
        c.text(sx(t), y1 + 16, fmt(t, 0 if t >= 1 else 1), 11, THEME["muted"], "middle")
    for t in yt:
        c.line(x0, sy(t), x1, sy(t), THEME["grid"])
        c.text(x0 - 6, sy(t) + 4, fmt(t, 1), 11, THEME["muted"], "end")

    def rcol(v):
        return THEME["good"] if v < 2.2 else (THEME["neutral"] if v < 3 else THEME["bad"])

    def rlev(v):
        return "low" if v < 2.2 else ("mid" if v < 3 else "high")

    rname = {"low": "низкий риск", "mid": "средний риск", "high": "высокий риск"}
    order = sorted(S, key=lambda r: -r["confidence_calc"])
    for r in order:
        rad = 4 + 14 * math.sqrt(max(0.0, min(1.0, r["confidence_calc"])))
        lv = rlev(r["risk_index"])
        info = {"pid": r["id"], "meaning": "Трудозатраты ≈ %s чел.-дн., ценность %s из 5, уверенность %s, %s (индекс %s)." % (
            fmt(r["effort_days_mid"], 1 if r["effort_days_mid"] < 10 else 0), fmt(r["value_index"], 1), fmt(r["confidence_calc"], 2),
            rname[lv], fmt(r["risk_index"], 1))}
        with c.item(r["id"], pt_label(r, "%s чел.-дн., уверенность %s, %s" % (fmt(r["effort_days_mid"], 1), fmt(r["confidence_calc"], 2), rname[lv])),
                    "point", info, groups=["g-risk-%s" % lv]):
            c.circle(sx(max(0.5, r["effort_days_mid"])), sy(r["value_index"]), rad, rcol(r["risk_index"]), "#FFFFFF", 0.55, 1)
    obstacles = [(sx(max(0.5, r["effort_days_mid"])), sy(r["value_index"]), 4) for r in S]
    place_labels(c, [(sx(max(0.5, r["effort_days_mid"])), sy(r["value_index"])) for r in top], [r["id"] for r in top],
                 (x0, y0, x1, y1), obstacles, 11, refs=[r["id"] for r in top])
    with c.item("axis-x", "Ось трудозатрат: человеко-дни, логарифмическая шкала", "axis", {"gloss": gl("charts", "bubble", "elements", "axis-x")}):
        c.text((x0 + x1) / 2, y1 + 34, "Трудозатраты, чел.-дни (лог. шкала)", 12, THEME["ink"], "middle")
    with c.item("axis-y", "Ось ценности: индекс от 1 до 5", "axis", {"gloss": gl("charts", "bubble", "elements", "axis-y")}):
        c.add('<text x="%.1f" y="%.1f" font-size="12" fill="%s" text-anchor="middle" transform="rotate(-90 %.1f %.1f)">%s</text>'
              % (PAD + 8, (y0 + y1) / 2, THEME["ink"], PAD + 8, (y0 + y1) / 2, esc("Ценность — индекс от 1 до 5")))
    cnt = Counter(rlev(r["risk_index"]) for r in S)

    def lel(lv, lab):
        rows = [r for r in S if rlev(r["risk_index"]) == lv]
        return {"id": "legend-risk-%s" % lv, "label": "Легенда: %s — %d %s" % (lab, cnt.get(lv, 0), plural(cnt.get(lv, 0), ("предложение", "предложения", "предложений"))),
                "info": {"gloss": gl("charts", "bubble", "elements", "legend-risk-%s" % lv), "related": top_ids(rows),
                         "meaning": "На графике %d %s с таким риском." % (cnt.get(lv, 0), plural(cnt.get(lv, 0), ("предложение", "предложения", "предложений")))},
                "highlight": "g-risk-%s" % lv}
    legend_row(c, [("риск < 2,2", THEME["good"], None), ("риск 2,2–3", THEME["neutral"], None), ("риск ≥ 3", THEME["bad"], None),
                   ("больше круг — выше уверенность; подписаны топ-10", THEME["bg"], None)], x0, y1 + 58, x1 - x0, 11,
               els=[lel("low", "низкий риск"), lel("mid", "средний риск"), lel("high", "высокий риск"),
                    {"id": "legend-size", "label": "Легенда: размер круга — расчётная уверенность",
                     "info": {"gloss": gl("charts", "bubble", "elements", "legend-size")}}])
    return c.finish(ph), title, cap


def ch_heatmap(S, top_n):
    top = S[:min(30, len(S))]
    cols = [("value_index", "Ценность", False, 1, 5), ("cost_index", "Стоимость", True, 1, 5), ("risk_index", "Риск", True, 1, 5),
            ("confidence_calc", "Уверенность", False, 0, 1), ("n_rice", "RICE норм.", False, 0, 1), ("n_ice", "ICE норм.", False, 0, 1),
            ("n_wsjf", "WSJF норм.", False, 0, 1), ("n_risk_adjusted", "С поправкой на риск", False, 0, 1), ("composite", "Composite", False, 0, 1)]
    cols = [c_ for c_ in cols if all(c_[0] in r for r in top)]
    W = 1180
    label_w = 360
    cell_w = (W - 2 * PAD - label_w) / len(cols)
    title = "Тепловая карта метрик топ-%d: насыщеннее — лучше" % len(top)
    cap = "Для стоимости и риска шкала цвета перевёрнута (дешевле и безопаснее — насыщеннее); в ячейках исходные значения."
    c = Chart(W, title, cap, "Источник: data/scores.json")
    hdr = [wrap(lbl, cell_w - 6, 11, True) for _, lbl, *_ in cols]
    hh = max(len(h) for h in hdr) * 14 + 8
    y = c.top + hh

    def good(r, k, inv, lo, hi):
        t = (r[k] - lo) / (hi - lo) if hi > lo else 0
        return max(0.0, min(1.0, 1 - t if inv else t))
    for j, h in enumerate(hdr):
        k, lbl, inv, lo, hi = cols[j]
        best = max(top, key=lambda r: good(r, k, inv, lo, hi))
        worst = min(top, key=lambda r: good(r, k, inv, lo, hi))
        cx = PAD + label_w + j * cell_w + cell_w / 2
        with c.item("col-%s" % k, "Столбец «%s»: лучшее у %s, худшее у %s" % (lbl, best["id"], worst["id"]), "column",
                    {"gloss": gl("metrics", k), "plinks": [best["id"], worst["id"]],
                     "summary": "Столбец метрики «%s» для топ-%d реестра; %s." % (lbl, len(top), "меньше — лучше" if inv else "больше — лучше"),
                     "meaning": "Лучшее значение среди лидеров — у %s (%s), худшее — у %s (%s)." % (best["id"], fmt(best[k], 2), worst["id"], fmt(worst[k], 2))},
                    highlight="g-col-%s" % k):
            c.lines(cx, c.top + 12, h, 11, THEME["ink"], "middle", True, 1.2)
    for r in top:
        tl = wrap("%d. %s %s" % (r["rank"], r["id"], r.get("title", "")), label_w - 10, 11)
        rh = max(24, len(tl) * 13.5 + 8)
        gs = sorted(cols, key=lambda cc: good(r, cc[0], cc[2], cc[3], cc[4]))
        with c.item(r["id"], "%s, ранг %d: сильнее всего «%s», слабее всего «%s»" % (pt_label(r), r["rank"], gs[-1][1], gs[0][1]), "row",
                    {"pid": r["id"], "meaning": "Ранг %d. По относительной шкале сильнее всего метрика «%s», слабее всего — «%s»." % (r["rank"], gs[-1][1], gs[0][1])}):
            c.lines(PAD, y + (rh - len(tl) * 13.5) / 2 + 10.5, tl, 11, THEME["ink"], lh=1.23)
        for j, (k, lbl, inv, lo, hi) in enumerate(cols):
            v = r[k]
            t = good(r, k, inv, lo, hi)
            fill = mix(THEME["seq_lo"], PAL[0], 0.08 + 0.92 * t)
            x = PAD + label_w + j * cell_w
            better = sum(1 for o in top if good(o, k, inv, lo, hi) < t)
            with c.item("cell-%s-%s" % (r["id"], k), "%s, метрика «%s»: %s" % (r["id"], lbl, fmt(v, 2)), "cell",
                        {"title": "%s · %s" % (r["id"], lbl), "gloss": gl("metrics", k), "plinks": [r["id"]], "deep": [("effort-impact", r["id"], "%s на матрице усилие–влияние" % r["id"])],
                         "summary": "Метрика «%s» у %s «%s»: %s." % (lbl, r["id"], r.get("title", ""), fmt(v, 2)),
                         "meaning": "Лучше, чем у %d из %d лидеров реестра%s." % (better, len(top) - 1, " (для этой метрики меньше — лучше)" if inv else ""),
                         "metrics": [{"label": lbl, "value": fmt(v, 2), "tag": "расчёт" if k.startswith("n_") or k in ("composite", "confidence_calc") else "оценка"}]},
                        groups=["g-col-%s" % k]):
                c.rect(x + 1, y + 1, cell_w - 2, rh - 2, fill, rx=2)
                tc = "#FFFFFF" if contrast(fill, "#FFFFFF") >= 4.5 else THEME["ink"]
                c.text(x + cell_w / 2, y + rh / 2 + 4, fmt(v, 2), 11, tc, "middle")
        y += rh
    return c.finish(y - c.top + 4), title, cap


def ch_radar(S, top_n):
    top = S[:min(10, len(S))]
    axes = [("value_index", "Ценность", lambda r: r["value_index"]), ("ease", "Простота", lambda r: 6 - r["cost_index"]),
            ("safety", "Безопасность", lambda r: 6 - r["risk_index"]), ("conf", "Уверенность", lambda r: 1 + 4 * r["confidence_calc"]),
            ("rice", "RICE", lambda r: 1 + 4 * r.get("n_rice", 0)), ("ice", "ICE", lambda r: 1 + 4 * r.get("n_ice", 0)),
            ("wsjf", "WSJF", lambda r: 1 + 4 * r.get("n_wsjf", 0))]
    W = 1060
    ncol = min(3, max(1, len(top)))
    cw = (W - 2 * PAD) / ncol
    title = "Радары топ-%d: профиль каждого лидера по семи осям (1–5)" % len(top)
    weakest = Counter(min(axes, key=lambda a: a[2](r))[1] for r in top).most_common(1)[0][0] if top else "—"
    cap = "Чем больше площадь, тем сильнее предложение по всем осям; самая частая слабая ось у лидеров — «%s»." % weakest
    c = Chart(W, title, cap, "Источник: data/scores.json; простота = 6 − стоимость, безопасность = 6 − риск, нормированные метрики → 1 + 4·n")
    y = c.top
    lab_w = max(text_w(lab, 10) for _, lab, _ in axes)
    R = max(40, min(80, cw / 2 - 12 - lab_w - 8))
    row_h_max = 0
    for i, r in enumerate(top):
        col = i % ncol
        if col == 0 and i:
            y += row_h_max
            row_h_max = 0
        x = PAD + col * cw
        tl = wrap("#%d %s — %s" % (r["rank"], r["id"], r.get("title", "")), cw - 16, 12, True)
        with c.ref(r["id"]):
            c.lines(x + 6, y + 14, tl, 12, THEME["ink"], bold=True, lh=1.25)
        cy = y + 14 + len(tl) * 15 + 22 + R
        cx = x + cw / 2
        for lvl in (1, 2, 3, 4, 5):
            rr = R * lvl / 5
            c.poly([(cx + rr * math.sin(2 * math.pi * k / len(axes)), cy - rr * math.cos(2 * math.pi * k / len(axes))) for k in range(len(axes))],
                   "none", THEME["grid"], sw=1)
        pts = []
        for k, (key, lab, fn) in enumerate(axes):
            a = 2 * math.pi * k / len(axes)
            c.line(cx, cy, cx + R * math.sin(a), cy - R * math.cos(a), THEME["grid"])
            v = max(1.0, min(5.0, fn(r)))
            pts.append((cx + R * v / 5 * math.sin(a), cy - R * v / 5 * math.cos(a)))
            lx, ly = cx + (R + 12) * math.sin(a), cy - (R + 12) * math.cos(a)
            anc = "middle" if abs(math.sin(a)) < 0.3 else ("start" if math.sin(a) > 0 else "end")
            if i == 0:   # подписи осей первого радара — элементы с определением оси (у остальных — data-ps-ref)
                with c.item("axis-%s" % key, "Ось радара «%s»" % lab, "axis",
                            {"title": "Ось «%s»" % lab, "gloss": gl("radar_axes", key),
                             "meaning": "Самое слабое место по этой оси среди лидеров — у %s." % min(top, key=lambda q: fn(q))["id"]}):
                    c.text(lx, ly + 4, lab, 10, THEME["muted"], anc)
            else:
                with c.ref("axis-%s" % key):
                    c.text(lx, ly + 4, lab, 10, THEME["muted"], anc)
        colr = PAL[i % len(PAL)]
        vals = [(lab, max(1.0, min(5.0, fn(r)))) for _, lab, fn in axes]
        lo_ax, hi_ax = min(vals, key=lambda t: t[1]), max(vals, key=lambda t: t[1])
        area = sum(v for _, v in vals) / len(vals)
        with c.item(r["id"], "%s: радар, слабая ось «%s», сильная «%s»" % (pt_label(r), lo_ax[0], hi_ax[0]), "shape",
                    {"pid": r["id"],
                     "meaning": "Ранг %d. Средний уровень по семи осям — %s из 5; сильнее всего «%s» (%s), слабее всего «%s» (%s)." % (
                         r["rank"], fmt(area, 1), hi_ax[0], fmt(hi_ax[1], 1), lo_ax[0], fmt(lo_ax[1], 1)),
                     "metrics": [{"label": lab, "value": fmt(v, 1), "tag": "расчёт"} for lab, v in vals]}):
            c.poly(pts, colr, colr, 0.25, 1.8)
        h = len(tl) * 15 + 22 + 2 * R + 40
        row_h_max = max(row_h_max, h)
    y += row_h_max
    return c.finish(y - c.top), title, cap


def ch_pareto(S, top_n):
    n = len(S)
    vals = [max(0.0, r["risk_adjusted"]) for r in S]
    tot = sum(vals) or 1.0
    cum, acc = [], 0.0
    for v in vals:
        acc += v
        cum.append(acc / tot)
    k50 = next(i for i, x in enumerate(cum, 1) if x >= 0.5 - 1e-12)
    k80 = next(i for i, x in enumerate(cum, 1) if x >= 0.8 - 1e-12)
    W = 960
    title = "Парето: первые %d %s по рангу дают половину ценности, первые %d — 80 %%" % (
        k50, plural(k50, ("предложение", "предложения", "предложений")), k80)
    cap = ("Столбцы — ценность с поправкой на риск в порядке ранга composite, линия — накопленная доля (правая ось). "
           "Чем круче линия в начале, тем сильнее концентрация ценности в лидерах.")
    c = Chart(W, title, cap, "Источник: data/scores.json (risk_adjusted)")
    ph = 380
    x0, x1, y0, y1 = PAD + 40, W - PAD - 44, c.top + 8, c.top + ph - 44
    vmax = max(vals) or 1
    ticks, _ = nice_ticks(0, vmax, 5)
    top_t = ticks[-1] if ticks[-1] > 0 else 1
    bw = (x1 - x0) / n
    for t in ticks:
        yy = y1 - t / top_t * (y1 - y0)
        c.line(x0, yy, x1, yy, THEME["grid"])
        c.text(x0 - 6, yy + 4, fmt(t, 1), 11, THEME["muted"], "end")
    for i, v in enumerate(vals):
        h = v / top_t * (y1 - y0)
        r = S[i]
        head = i < k80
        with c.item(r["id"], "%s: ранг %d, ценность с поправкой на риск %s, накоплено %d %%" % (pt_label(r), r.get("rank", i + 1), fmt(v, 2), round(cum[i] * 100)),
                    "bar", {"pid": r["id"], "meaning": "Ранг %d; ценность с поправкой на риск %s; вместе с предыдущими даёт %d %% суммарной ценности реестра — %s." % (
                        r.get("rank", i + 1), fmt(v, 2), round(cum[i] * 100), "входит в группу, дающую 80 % ценности" if head else "это хвост после отметки 80 %")},
                    groups=["g-head" if head else "g-tail"]):
            c.rect(x0 + i * bw + bw * 0.12, y1 - h, bw * 0.76, h, PAL[0] if head else mix(PAL[0], "#FFFFFF", 0.55))
    pts = [(x0 + (i + 0.5) * bw, y1 - cv * (y1 - y0)) for i, cv in enumerate(cum)]
    with c.item("line-cum", "Накопленная доля ценности: первые %d дают 50 %%, первые %d — 80 %%" % (k50, k80), "line",
                {"gloss": gl("charts", "pareto", "elements", "line-cum"),
                 "meaning": "Первые %d из %d %s дают половину суммарной ценности, первые %d — 80 %%." % (
                     k50, n, plural(n, ("предложения", "предложений", "предложений")), k80),
                 "related": [r["id"] for r in S[:3]]}):
        c.hit(pts)
        c.poly(pts, "none", PAL[1], sw=2.2, closed=False)
    for p in (0, 0.25, 0.5, 0.75, 1.0):
        c.text(x1 + 6, y1 - p * (y1 - y0) + 4, "%d %%" % (p * 100), 11, THEME["muted"])
    for k, lab in ((k50, "50 %"), (k80, "80 %")):
        px = x0 + (k - 0.5) * bw
        py = y1 - cum[k - 1] * (y1 - y0)
        txt = "%s — первые %d" % (lab, k)
        with c.item("mark-%s" % lab.split()[0], "Отметка %s: первые %d %s" % (lab, k, plural(k, ("предложение", "предложения", "предложений"))), "point",
                    {"title": "Отметка %s" % lab, "gloss": gl("terms", "pareto"), "plinks": [S[k - 1]["id"]],
                     "summary": "Отметка %s: столько первых предложений по рангу дают %s суммарной ценности с поправкой на риск." % (lab, lab),
                     "meaning": "Первые %d из %d; граница проходит по %s." % (k, n, S[k - 1]["id"]),
                     "metrics": [{"label": "Предложений до отметки", "value": str(k), "tag": "расчёт"},
                                 {"label": "Доля реестра", "value": "%d %%" % round(100 * k / n), "tag": "расчёт"}]},
                    highlight="g-head" if lab == "80 %" else None):
            c.line(px, py, px, y1, PAL[1], 1, "3 3")
            c.circle(px, py, 4, PAL[1], "#FFFFFF")
            anc = "start" if px + text_w(txt, 11) + 8 < x1 else "end"
            c.rect(px + (6 if anc == "start" else -text_w(txt, 11, True) - 8), py - 22, text_w(txt, 11, True) + 4, 16, THEME["bg"], op=0.9)
            c.text(px + (8 if anc == "start" else -8), py - 10, txt, 11, THEME["ink"], anc, True)
    step = max(1, int(math.ceil(n / 15.0)))
    for i in range(0, n, step):
        c.text(x0 + (i + 0.5) * bw, y1 + 15, str(i + 1), 10, THEME["muted"], "middle")
    with c.item("axis-x", "Ось: ранг по composite", "axis", {"gloss": gl("charts", "pareto", "elements", "axis-x")}):
        c.text((x0 + x1) / 2, y1 + 34, "Ранг по composite", 12, THEME["ink"], "middle")
    return c.finish(ph), title, cap


def ch_tornado(sens):
    t = [e for e in sens.get("tornado", []) if "low_rank_shift" in e and "high_rank_shift" in e]
    if not t or sens.get("top_n", 20) < 2 or max(max(e["low_rank_shift"], e["high_rank_shift"]) for e in t) <= 0:
        return None   # нет данных или ранги вообще не сдвигаются (одно предложение, полные ничьи)
    t = t[:14]
    stab = sens.get("top20_stability", 0)
    topn = sens.get("top_n", 20)

    def pname(p):
        g, _, k = p.partition(".")
        return "%s: %s" % (GROUP_RU.get(g, g), PARAM_RU.get(k, k)) if k else p

    W = 960
    lead = pname(t[0]["param"])
    title = "Торнадо чувствительности: топ-%d сохраняется на %d %% при любом изменении одного веса на ±50 %%" % (topn, round(stab * 100))
    cap = "Сильнее всего ранги зависят от параметра «%s»; длина полосы — средний сдвиг ранга при весе ×0,5 (влево) и ×1,5 (вправо)." % lead
    c = Chart(W, title, cap, "Источник: data/sensitivity.json (score.py, %s прогонов)" % sens.get("runs", "—"))
    label_w = 300
    rows_h = [max(26, len(wrap(pname(e["param"]), label_w - 10, 12)) * 15 + 10) for e in t]
    ph = sum(rows_h) + 50
    x0, x1 = PAD + label_w, W - PAD - 40
    mid = (x0 + x1) / 2
    mx = max(max(e["low_rank_shift"], e["high_rank_shift"]) for e in t) or 1
    half = (x1 - x0) / 2 - 30
    y = c.top + 24
    with c.item("legend-low", "Левые полосы: вес ×0,5", "legend", {"gloss": gl("charts", "tornado", "elements", "legend-low")}, highlight="g-low"):
        c.text(mid - 8, c.top + 12, "вес ×0,5", 11, THEME["muted"], "end")
    with c.item("legend-high", "Правые полосы: вес ×1,5", "legend", {"gloss": gl("charts", "tornado", "elements", "legend-high")}, highlight="g-high"):
        c.text(mid + 8, c.top + 12, "вес ×1,5", 11, THEME["muted"], "start")
    gdesc = {"composite": "вес формулы в итоговом composite", "value": "вес подшкалы в индексе ценности",
             "cost": "вес части в индексе стоимости", "risk": "вес вида риска в индексе риска"}
    for pos, (e, rh) in enumerate(zip(t, rows_h), 1):
        tl = wrap(pname(e["param"]), label_w - 10, 12)
        g_, _, k_ = e["param"].partition(".")
        lo_s, hi_s = e["low_rank_shift"], e["high_rank_shift"]
        ov = [x for x in (e.get("low_top_overlap"), e.get("high_top_overlap")) if isinstance(x, (int, float))]
        mets = [{"label": "Сдвиг ранга при ×0,5", "value": fmt(lo_s, 2), "tag": "расчёт"},
                {"label": "Сдвиг ранга при ×1,5", "value": fmt(hi_s, 2), "tag": "расчёт"}]
        if ov:
            mets.append({"label": "Остаётся в топ-%d (худший случай)" % topn, "value": "%d из %d" % (min(ov), topn), "tag": "расчёт"})
        with c.item("param-%s" % e["param"], "%s: сдвиг ранга %s при ×0,5 и %s при ×1,5" % (pname(e["param"]), fmt(lo_s, 2), fmt(hi_s, 2)), "bar",
                    {"title": "Вес «%s»" % pname(e["param"]), "gloss": gl("terms", "tornado"), "section": 17, "metrics": mets,
                     "summary": "Параметр «%s» — %s (%s). Место по влиянию: %d из %d." % (
                         pname(e["param"]), gdesc.get(g_, "вес формулы"), e["param"], pos, len(t)),
                     "meaning": "Если уменьшить этот вес вдвое, каждое предложение в среднем сдвинется на %s позиции; если увеличить в полтора раза — на %s. %s" % (
                         fmt(lo_s, 2), fmt(hi_s, 2), "Ранжирование заметно зависит от этого веса." if max(lo_s, hi_s) >= 1 else "Влияние меньше одной позиции — вывод устойчив к этому весу.")}):
            c.lines(PAD, y + (rh - len(tl) * 15) / 2 + 12, tl, 12, THEME["ink"])
            lw = lo_s / mx * half
            hw = hi_s / mx * half
            c.add('<g data-ps-group="g-low">')
            c.rect(mid - lw, y + 5, lw, rh - 10, PAL[0], rx=2)
            c.add('</g><g data-ps-group="g-high">')
            c.rect(mid, y + 5, hw, rh - 10, PAL[1], rx=2)
            c.add("</g>")
            c.text(mid - lw - 5, y + rh / 2 + 4, fmt(lo_s, 2), 11, THEME["ink"], "end")
            c.text(mid + hw + 5, y + rh / 2 + 4, fmt(hi_s, 2), 11, THEME["ink"], "start")
        y += rh
    c.line(mid, c.top + 18, mid, y, THEME["ink"], 1.2)
    with c.item("axis-x", "Ось: средний сдвиг ранга, позиций", "axis", {"gloss": gl("charts", "tornado", "elements", "axis-x"),
                                                                       "meaning": "Стабильность топ-%d: %d %% лидеров остаются в топе при любом изменении одного веса." % (topn, round(stab * 100))}):
        c.text(mid, y + 22, "Средний сдвиг ранга, позиций", 12, THEME["ink"], "middle")
    return c.finish(ph), title, cap


def hbar_chart(title, cap, source, items, W=860, color=None, marks=None, value_fmt=None, colors=None, legend=None,
               right_pad=60, int_ticks=False, els=None, legend_els=None, marks_el=None):
    """Горизонтальные столбцы: items — [(label, value)], marks — {label: требуемый минимум} (риска).
    right_pad — место справа под подписи значений; int_ticks — целые деления оси (счётные величины).
    els — параллельно items: {id, label?, info, groups?} — строка (подпись, полоса, значение) становится элементом;
    legend_els — для пунктов legend; marks_el — {id, label, info} для пояснения рисок минимума."""
    c = Chart(W, title, cap, source)
    label_w = 230
    x0, x1 = PAD + label_w, W - PAD - right_pad
    vmax = max([v for _, v in items] + list((marks or {}).values()) + [1])
    if int_ticks:
        step = max(1, int(math.ceil(vmax / 5.0)))
        ticks = list(range(0, int(math.ceil(vmax / float(step))) * step + 1, step))
    else:
        ticks, _ = nice_ticks(0, vmax, 5)
    top = ticks[-1] or 1
    y = c.top + 4
    rows = []
    for lab, v in items:
        tl = wrap(lab, label_w - 12, 12)
        rh = max(28, len(tl) * 15 + 10)
        rows.append((lab, v, tl, rh))
    total_h = sum(r[3] for r in rows)
    for t in ticks:
        xx = x0 + t / top * (x1 - x0)
        c.line(xx, y, xx, y + total_h, THEME["grid"])
        c.text(xx, y + total_h + 16, fmt(t), 11, THEME["muted"], "middle")
    els = list(els or [])
    for k, (lab, v, tl, rh) in enumerate(rows):
        e = els[k] if k < len(els) else None
        if e:
            c.open_el(e["id"], e.get("label") or "%s: %s" % (lab, value_fmt(v) if value_fmt else fmt(v)), e.get("kind", "bar"),
                      e.get("info"), groups=e.get("groups"))
        c.lines(PAD, y + (rh - len(tl) * 15) / 2 + 12, tl, 12, THEME["ink"])
        w = v / top * (x1 - x0)
        col = (colors[k] if colors else None) or color or PAL[0]
        c.rect(x0, y + 5, w, rh - 10, col, rx=2)
        c.text(x0 + w + 6, y + rh / 2 + 4, value_fmt(v) if value_fmt else fmt(v), 12, THEME["ink"])
        if marks and lab in marks:
            mx = x0 + marks[lab] / top * (x1 - x0)
            c.add('<g data-ps-group="g-min">')
            c.line(mx, y + 2, mx, y + rh - 2, THEME["ink"], 2)
            c.add("</g>")
        if e:
            c.close_el()
        y += rh
    extra = 0
    if marks:
        if marks_el:
            c.open_el(marks_el["id"], marks_el["label"], "legend", marks_el.get("info"), highlight="g-min")
        c.line(PAD, y + 34, PAD + 14, y + 34, THEME["ink"], 2)
        c.text(PAD + 20, y + 38, "чёрная риска — требуемый минимум категории", 11, THEME["muted"])
        if marks_el:
            c.close_el()
        extra = 22
    if legend:
        extra += legend_row(c, legend, PAD, y + 38 + extra, W - 2 * PAD, 12, els=legend_els)
    return c.finish(total_h + 30 + extra)


def ch_dist_category(S, check):
    cnt = Counter(r.get("category") for r in S)
    keys = [k for k in CAT_RU if cnt.get(k)] + sorted((k for k in cnt if k not in CAT_RU), key=str)
    keys.sort(key=lambda k: -cnt[k])
    marks = {}
    cm = (check or {}).get("category_minimums") or {}
    for k in keys:
        if k in cm and not cm[k].get("na"):
            marks[cat_name(k)] = cm[k].get("required", 0)
    short = [cat_name(k) for k in keys if cat_name(k) in marks and cnt[k] < marks[cat_name(k)]]
    title = "Реестр по категориям: %d %s, больше всего — «%s»" % (len(S), plural(len(S), ("предложение", "предложения", "предложений")), cat_name(keys[0]))
    cap = ("Ниже минимума: %s." % ", ".join(short)) if short else ("Все категории выше минимумов." if marks else "Минимумы категорий не проверялись (нет data/registry-check.json).")
    items = [(cat_name(k), cnt[k]) for k in keys]
    els = []
    for k in keys:
        rows = [r for r in S if r.get("category") == k]
        req = marks.get(cat_name(k))
        mets = [{"label": "Предложений", "value": str(cnt[k]), "tag": "факт"},
                {"label": "Доля реестра", "value": "%d %%" % round(100 * cnt[k] / len(S)), "tag": "расчёт"}]
        if req is not None:
            mets.append({"label": "Требуемый минимум", "value": str(req), "tag": "правило реестра"})
        qn = Counter(r.get("quadrant") for r in rows)
        els.append({"id": "cat-%s" % k, "label": "Категория «%s»: %d %s%s" % (cat_name(k), cnt[k], plural(cnt[k], ("предложение", "предложения", "предложений")),
                                                                         (", минимум %d" % req) if req is not None else ""),
                    "info": {"gloss": gl("categories", k), "cat": k, "related": top_ids(rows), "metrics": mets,
                             "meaning": "%d %s (%d %% реестра)%s; быстрых побед среди них — %d, крупных ставок — %d." % (
                                 cnt[k], plural(cnt[k], ("предложение", "предложения", "предложений")), round(100 * cnt[k] / len(S)),
                                 ("" if req is None else (", это ниже минимума %d" % req if cnt[k] < req else ", минимум %d выполнен" % req)),
                                 qn.get("quick_win", 0), qn.get("big_bet", 0))}})
    mel = {"id": "legend-min", "label": "Чёрная риска — требуемый минимум категории",
           "info": {"gloss": gl("charts", "dist-category", "elements", "legend-min"),
                    "meaning": ("Ниже минимума: %s." % ", ".join(short)) if short else "Все проверенные категории не ниже минимума."}}
    return hbar_chart(title, cap, "Источник: data/proposals.json, data/registry-check.json", items, marks=marks or None,
                      colors=[cat_color(k)[0] for k in keys], els=els, marks_el=mel), title, cap


def ch_dist_evidence(S):
    cnt = Counter(r.get("evidence_class") for r in S)
    ab = (cnt.get("A", 0) + cnt.get("B", 0)) / len(S)
    title = "Классы доказательств: A+B = %d %% (порог 60 %%)" % round(ab * 100)
    cap = ("Доля сильных доказательств достаточна." if ab >= 0.6 else "Доля сильных доказательств ниже порога — нужно усилить источники.")
    names = {"A": "A — первоисточник / живая функция", "B": "B — несколько независимых упоминаний", "C": "C — одно упоминание", "D": "D — логический вывод"}
    items = [(names[k], cnt.get(k, 0)) for k in "ABCD"]
    cols = [THEME["good"], PAL[5 % len(PAL)], PAL[1], THEME["bad"]]
    els = []
    for k in "ABCD":
        rows = [r for r in S if r.get("evidence_class") == k]
        els.append({"id": "class-%s" % k, "label": "%s: %d %s" % (names[k], len(rows), plural(len(rows), ("предложение", "предложения", "предложений"))),
                    "info": {"gloss": gl("evidence", k), "related": top_ids(rows), "registry": {"class": k}, "section": 17,
                             "metrics": [{"label": "Предложений", "value": str(len(rows)), "tag": "факт"},
                                         {"label": "Доля реестра", "value": "%d %%" % round(100 * len(rows) / len(S)), "tag": "расчёт"}],
                             "meaning": "%d %s (%d %% реестра); доля A+B — %d %% при пороге 60 %%." % (
                                 len(rows), plural(len(rows), ("предложение", "предложения", "предложений")), round(100 * len(rows) / len(S)), round(ab * 100))}})
    return hbar_chart(title, cap, "Источник: data/proposals.json", items, colors=cols, els=els), title, cap


def ch_dist_horizon(S):
    cnt = Counter(r.get("horizon") for r in S)
    keys = [k for k in HORIZON_RU] + sorted((k for k in cnt if k not in HORIZON_RU), key=str)
    shown = [k for k in keys if cnt.get(k, 0) or k in HORIZON_RU]
    items = [(HORIZON_RU.get(k, str(k)), cnt.get(k, 0)) for k in shown]
    near = cnt.get("now", 0) + cnt.get("next", 0)
    title = "Горизонты: %d из %d %s — на ближайший год" % (near, len(S), plural(len(S), ("предложения", "предложений", "предложений")))
    cap = "Сейчас — 0–3 мес., дальше — 3–12 мес., позже — 1–2 года, видение — 2+ года."
    els = []
    for k in shown:
        rows = [r for r in S if r.get("horizon") == k]
        eff = sum(r.get("effort_days_mid") or 0 for r in rows)
        els.append({"id": "horizon-%s" % k, "label": "%s: %d %s" % (HORIZON_RU.get(k, str(k)), len(rows), plural(len(rows), ("предложение", "предложения", "предложений"))),
                    "info": {"gloss": gl("horizons", k), "related": top_ids(rows), "registry": {"horizon": k},
                             "summary": "" if k in HORIZON_RU else "Горизонт «%s» вне контракта (now|next|later|vision)." % k,
                             "metrics": [{"label": "Предложений", "value": str(len(rows)), "tag": "факт"},
                                         {"label": "Сумма середин трудозатрат", "value": "%s чел.-дн." % fmt(eff), "tag": "оценка"}],
                             "meaning": "%d %s, суммарно около %s чел.-дн. по серединам оценок." % (
                                 len(rows), plural(len(rows), ("предложение", "предложения", "предложений")), fmt(eff))},
                    "groups": None})
    return hbar_chart(title, cap, "Источник: data/proposals.json (horizon)", items,
                      colors=[mix(PAL[0], "#FFFFFF", 0.18 * i) for i in range(len(items))], els=els), title, cap


# ---------------------------------------------------------------- план
def ch_gantt(G):
    G = [g for g in G if isinstance(g, dict) and isinstance(g.get("start_month"), (int, float)) and isinstance(g.get("end_month"), (int, float))]
    if not G:
        return None
    maxm = int(max(g["end_month"] for g in G))
    W = 1160
    label_w = 330
    phases = list(OrderedDict.fromkeys(g.get("phase", "") for g in G))
    ms = sum(1 for g in G if g.get("type") == "milestone")
    title = "Диаграмма Ганта: %d %s и %d %s на %d мес." % (
        len(G) - ms, plural(len(G) - ms, ("задача", "задачи", "задач")), ms, plural(ms, ("контрольная точка", "контрольные точки", "контрольных точек")), maxm)
    cap = "Полосы — задачи по фазам, ромбы — контрольные точки; затенённая зона — годы видения (после 12-го месяца)."
    c = Chart(W, title, cap, "Источник: data/gantt.json")
    x0, x1 = PAD + label_w, W - PAD
    mw = (x1 - x0) / maxm
    y = c.top + 26
    step = 1 if maxm <= 18 else (3 if maxm <= 40 else 6)
    rows = []
    for g in G:
        tl = wrap("%s %s" % (g.get("id", ""), g.get("task", "")), label_w - 14, 12)
        rows.append((g, tl, max(26, len(tl) * 15 + 10)))
    body_h = sum(r[2] for r in rows) + len(phases) * 22
    if maxm > 12:
        nv = sum(1 for g in G if g["end_month"] > 12)
        with c.item("area-vision", "Годы видения: месяцы 13–%d, %d %s" % (maxm, nv, plural(nv, ("задача", "задачи", "задач"))), "area",
                    {"gloss": gl("charts", "gantt", "elements", "area-vision"), "section": 15,
                     "meaning": "После 12-го месяца заканчивается %d %s плана." % (nv, plural(nv, ("задача", "задачи", "задач")))}):
            c.rect(x0 + 12 * mw, y, (maxm - 12) * mw, body_h, THEME["panel"])
    for m in range(1, maxm + 1):
        if (m - 1) % step == 0:
            c.text(x0 + (m - 0.5) * mw, c.top + 14, str(m), 11, THEME["muted"], "middle")
        c.line(x0 + (m - 1) * mw, y, x0 + (m - 1) * mw, y + body_h, THEME["grid"], 0.8)
    pcol = {p: PAL[i % len(PAL)] for i, p in enumerate(phases)}
    gids = {str(g.get("id")) for g in G if g.get("id")}
    for pi, ph in enumerate(phases, 1):
        pg = [g for g in G if g.get("phase", "") == ph]
        pm = [g for g in pg if g.get("type") == "milestone"]
        with c.item("phase-%d" % pi, "Фаза «%s»: %d %s, месяцы %d–%d" % (ph or "без фазы", len(pg), plural(len(pg), ("строка", "строки", "строк")),
                                                                      min(g["start_month"] for g in pg), max(g["end_month"] for g in pg)), "row",
                    {"title": "Фаза «%s»" % (ph or "без фазы"), "section": 14,
                     "summary": "Фаза плана «%s»: %d %s и %d %s." % (ph or "без фазы", len(pg) - len(pm), plural(len(pg) - len(pm), ("задача", "задачи", "задач")),
                                                              len(pm), plural(len(pm), ("контрольная точка", "контрольные точки", "контрольных точек"))),
                     "meaning": "Сроки фазы — с %d-го по %d-й месяц от старта; задачи: %s." % (
                         min(g["start_month"] for g in pg), max(g["end_month"] for g in pg), ", ".join(str(g.get("id")) for g in pg[:8])),
                     "links": [{"label": "%s — %s" % (g.get("id"), g.get("task", "")), "href": "#gantt/%s" % g.get("id")} for g in pg[:4] if g.get("id")]},
                    highlight="g-phase-%d" % pi):
            c.text(PAD, y + 15, ph or "без фазы", 12, pcol[ph], bold=True)
        y += 22
        for g, tl, rh in rows:
            if g.get("phase", "") != ph:
                continue
            s, e = g["start_month"], g["end_month"]
            ms_ = g.get("type") == "milestone"
            gid = str(g.get("id") or "task")
            deps = [str(d) for d in g.get("dependencies") or [] if str(d) in gids]
            acts = ["Выполнить: %s" % g.get("task")] if g.get("task") else []
            if g.get("done_criteria"):
                acts.append("Критерий готовности: %s" % g["done_criteria"])
            if g.get("owner"):
                acts.append("Ответственный: %s" % g["owner"])
            if deps:
                acts.append("Сначала завершить: %s" % ", ".join(deps))
            span = ("месяц %d" % e) if ms_ or s == e else ("месяцы %d–%d" % (s, e))
            lk = [{"label": "Строка плана %s" % gid, "href": "#gantt/%s" % gid}] + [
                {"label": "Зависит от %s — %s" % (d, next((x.get("task", "") for x in G if str(x.get("id")) == d), "")), "href": "#gantt/%s" % d} for d in deps]
            with c.item(gid, "%s %s: %s, %s" % (gid, g.get("task", ""), "контрольная точка" if ms_ else "задача", span), "bar",
                        {"title": "%s — %s" % (gid, g.get("task", "")),
                         "summary": "%s «%s» в фазе «%s»." % ("Контрольная точка" if ms_ else "Задача", g.get("task", ""), ph or "без фазы"),
                         "meaning": "%s от старта%s%s." % (span.capitalize(), "; затрагивает годы видения" if e > 12 else "",
                                                           ("; связанные предложения: " + ", ".join(g.get("proposal_ids") or [])) if g.get("proposal_ids") else ""),
                         "actions": acts, "plinks": list(g.get("proposal_ids") or [])[:4], "links": lk, "section": 15 if s > 12 else 14,
                         "metrics": [{"label": "Начало, месяц", "value": str(s), "tag": "план"}, {"label": "Конец, месяц", "value": str(e), "tag": "план"}]},
                        groups=["g-phase-%d" % pi]):
                c.lines(PAD + 10, y + (rh - len(tl) * 15) / 2 + 12, tl, 12, THEME["ink"])
                if ms_:
                    cx, cy = x0 + (e - 0.5) * mw, y + rh / 2
                    c.poly([(cx, cy - 8), (cx + 8, cy), (cx, cy + 8), (cx - 8, cy)], pcol[ph], "#FFFFFF")
                else:
                    c.rect(x0 + (s - 1) * mw + 1, y + 6, (e - s + 1) * mw - 2, rh - 12, pcol[ph], rx=3)
            y += rh
    with c.item("axis-x", "Ось: месяц от старта, всего %d мес." % maxm, "axis", {"gloss": gl("charts", "gantt", "elements", "axis-x")}):
        c.text((x0 + x1) / 2, y + 22, "Месяц от старта", 12, THEME["ink"], "middle")
    return c.finish(body_h + 56), title, cap


# ---------------------------------------------------------------- модель
STAGE_RU = {"acquisition": "Привлечение", "activation": "Активация", "retention": "Удержание", "revenue": "Доход", "referral": "Рекомендации"}
STAGE_CATS = {"acquisition": ("acquisition", "partnerships", "localization"), "activation": ("conversion",), "retention": ("retention",),
              "revenue": ("monetization",), "referral": ()}


def stage_related(stage, S):
    """Лучшие по рангу предложения, относящиеся к ступени воронки (по категории; рекомендации — по словам о шаринге)."""
    if stage == "referral":
        rx = dict((k, r) for k, _, r in CHANNELS)["viral"]
        rows = [r for r in S or [] if re.search(rx, str(r.get("title", "")).lower())]
    else:
        rows = [r for r in S or [] if r.get("category") in STAGE_CATS.get(stage, ())]
    return top_ids(rows), (STAGE_CATS.get(stage) or (None,))[0]


def ch_funnel(M, S=None):
    sc = M.get("scenarios") or {}
    names = [k for k in SCEN_RU if k in sc and sc[k].get("funnel")]
    if not names:
        return None
    stages = [f.get("label") or f.get("stage") for f in sc[names[0]]["funnel"]]
    W = 1000
    base = sc.get("base", sc[names[0]])
    bf = {f.get("stage"): f.get("value", 0) for f in base["funnel"]}
    title = "Воронка AARRR за %s мес.: от %s посетителей до %s новых платящих (базовый сценарий)" % (
        M.get("horizon_months", "—"), fmt(bf.get("acquisition", 0)), fmt(bf.get("revenue", 0)))
    cap = "Логарифмическая шкала: каждая метка — порядок величины; все конверсии — допущения из build/model-params.json."
    c = Chart(W, title, cap, "Источник: data/model.json (model.py) [допущение]")
    label_w = 230
    x0, x1 = PAD + label_w, W - PAD - 90
    allv = [max(1e-3, f.get("value", 0)) for k in names for f in sc[k]["funnel"]]
    lo, hi = 10 ** math.floor(math.log10(max(min(allv), 0.1))), 10 ** math.ceil(math.log10(max(allv)))
    if hi <= lo:
        hi = lo * 10
    sx = lambda v: x0 + (math.log10(max(v, lo)) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * (x1 - x0)
    bh = 16
    gh = bh * len(names) + 16
    y = c.top + 6
    total = gh * len(stages)
    for t in log_ticks(lo, hi):
        if str(t)[0] == "1" or t == lo:
            c.line(sx(t), y, sx(t), y + total, THEME["grid"])
    with c.item("axis-x", "Логарифмическая шкала значений воронки", "axis", {"gloss": gl("charts", "funnel", "elements", "axis-x")}):
        for t in log_ticks(lo, hi):
            if str(t)[0] == "1" or t == lo:
                c.text(sx(t), y + total + 16, fmt(t, 0 if t >= 1 else 1), 11, THEME["muted"], "middle")
    bname = "base" if "base" in sc else names[0]
    for si, st in enumerate(stages):
        tl = wrap(st, label_w - 12, 12)
        f0 = sc[bname]["funnel"][si] if si < len(sc[bname]["funnel"]) else {}
        skey = f0.get("stage") or "stage%d" % si
        vals = {nm: (sc[nm]["funnel"][si].get("value", 0) if si < len(sc[nm]["funnel"]) else 0) for nm in names}
        bv = vals.get(bname, 0)
        prev = sc[bname]["funnel"][si - 1] if si else None
        conv = ("%s %% от ступени «%s»" % (fmt(100.0 * bv / prev["value"], 1), prev.get("label") or prev.get("stage"))) if prev and prev.get("value") else "верх воронки"
        rel, rcat = stage_related(skey, S)
        info = {"title": "%s — «%s»" % ((STAGE_RU.get(skey) or st), st) if STAGE_RU.get(skey) and STAGE_RU.get(skey) != st else st,
                "gloss": gl("stages", skey), "related": rel, "registry": {"category": rcat} if rcat and rel else None,
                "meaning": "%s сценарий: %s за %s мес. (%s). Диапазон по сценариям: %s–%s. Все значения — допущения модели%s." % (
                    SCEN_RU.get(bname, bname), fmt(bv, 0 if bv >= 10 else 1), M.get("horizon_months", "—"), conv,
                    fmt(min(vals.values()), 0 if min(vals.values()) >= 10 else 1), fmt(max(vals.values()), 0 if max(vals.values()) >= 10 else 1),
                    " (продукта ещё нет)" if CONCEPT[0] else ""),
                "metrics": [{"label": "%s сценарий" % SCEN_RU[nm], "value": fmt(vals[nm], 0 if vals[nm] >= 10 else 1), "tag": "допущение"} for nm in names]}
        with c.item("stage-%s" % skey, "Ступень «%s»: %s в базовом сценарии, %s" % (st, fmt(bv, 0 if bv >= 10 else 1), conv), "stage", info):
            c.lines(PAD, y + (gh - len(tl) * 15) / 2 + 12, tl, 12, THEME["ink"], bold=True)
            for k, nm in enumerate(names):
                v = vals[nm]
                yy = y + 8 + k * bh
                c.add('<g data-ps-group="g-scen-%s">' % nm)
                c.rect(x0, yy, sx(max(v, lo)) - x0, bh - 3, scol(nm), rx=2)
                c.text(sx(max(v, lo)) + 5, yy + bh - 6, fmt(v, 0 if v >= 10 else 1), 11, THEME["ink"])
                c.add("</g>")
        y += gh
    lels = [{"id": "legend-scen-%s" % k, "label": "Легенда: %s сценарий" % SCEN_RU[k].lower(),
             "info": {"gloss": gl("scenarios", k), "section": 8}, "highlight": "g-scen-%s" % k} for k in names]
    h = legend_row(c, [(SCEN_RU[k], scol(k), None) for k in names], x0, y + 40, x1 - x0, 12, els=lels)
    return c.finish(total + 30 + h), title, cap


def ch_fan(M):
    sc = M.get("scenarios") or {}
    if not all(k in sc and sc[k].get("monthly") for k in SCEN_RU):
        return None
    mo = {k: [m.get("users", 0) for m in sc[k]["monthly"]] for k in SCEN_RU}
    n = len(mo["base"])
    W = 960
    title = "Веер прогноза: через %d мес. от %s до %s активных пользователей, базовый — %s" % (
        n, fmt(mo["pessimistic"][-1]), fmt(mo["optimistic"][-1]), fmt(mo["base"][-1]))
    cap = "Полоса — диапазон между пессимистичным и оптимистичным сценариями, линия — базовый; допущения в build/model-params.json."
    c = Chart(W, title, cap, "Источник: data/model.json (monthly.users) [допущение]")
    ph = 360
    x0, x1, y0, y1 = PAD + 60, W - PAD - 10, c.top + 8, c.top + ph - 70
    vmax = max(max(v) for v in mo.values()) or 1
    ticks, _ = nice_ticks(0, vmax, 5)
    top = ticks[-1] or 1
    sx = lambda i: x0 + (i / max(1, n - 1)) * (x1 - x0)
    sy = lambda v: y1 - v / top * (y1 - y0)
    for t in ticks:
        c.line(x0, sy(t), x1, sy(t), THEME["grid"])
        c.text(x0 - 6, sy(t) + 4, fmt(t), 11, THEME["muted"], "end")
    step = max(1, int(math.ceil(n / 12.0)))
    for i in range(0, n, step):
        c.text(sx(i), y1 + 16, str(i + 1), 11, THEME["muted"], "middle")
    band = [(sx(i), sy(v)) for i, v in enumerate(mo["optimistic"])] + [(sx(i), sy(v)) for i, v in reversed(list(enumerate(mo["pessimistic"])))]
    spread = (mo["optimistic"][-1] / mo["pessimistic"][-1]) if mo["pessimistic"][-1] else None
    with c.item("band", "Диапазон прогноза через %d мес.: %s–%s" % (n, fmt(mo["pessimistic"][-1]), fmt(mo["optimistic"][-1])), "area",
                {"gloss": gl("charts", "forecast-fan", "elements", "band"),
                 "meaning": "Через %d мес. — от %s до %s активных пользователей%s; все входы — допущения." % (
                     n, fmt(mo["pessimistic"][-1]), fmt(mo["optimistic"][-1]), (", разброс в %s раза" % fmt(spread, 1)) if spread else ""),
                 "metrics": [{"label": "Пессимистичный, мес. %d" % n, "value": fmt(mo["pessimistic"][-1]), "tag": "допущение"},
                             {"label": "Оптимистичный, мес. %d" % n, "value": fmt(mo["optimistic"][-1]), "tag": "допущение"}]}):
        c.poly(band, scol("base"), None, 0.16)

    def scen_line(k, sw):
        vals = mo[k]
        pts = [(sx(i), sy(v)) for i, v in enumerate(vals)]
        a = sc[k].get("assumptions") or {}
        mets = [{"label": "Активные через %d мес." % n, "value": fmt(vals[-1]), "tag": "допущение"},
                {"label": "Активные в 1-й мес.", "value": fmt(vals[0]), "tag": "допущение"}]
        for ak, lab in (("visitors_month", "Посетителей в 1-й мес."), ("traffic_growth", "Рост трафика в месяц"),
                        ("signup_to_active", "Регистрация → активация"), ("retention_monthly", "Удержание в месяц")):
            av = (a.get(ak) or {}).get("value") if isinstance(a.get(ak), dict) else None
            if isinstance(av, (int, float)):
                mets.append({"label": lab, "value": ("%s %%" % fmt(av * 100, 0 if av * 100 >= 10 else 1)) if av < 1 and ak != "visitors_month" else fmt(av),
                             "tag": (a.get(ak) or {}).get("label") or "допущение"})
        with c.item("scen-%s" % k, "%s сценарий: %s активных через %d мес." % (SCEN_RU[k], fmt(vals[-1]), n), "line",
                    {"gloss": gl("scenarios", k), "section": 8, "metrics": mets,
                     "meaning": "Активных пользователей: %s в первый месяц, %s через %d мес." % (fmt(vals[0]), fmt(vals[-1]), n)},
                    groups=["g-scen-%s" % k]):
            c.hit(pts)
            c.poly(pts, "none", scol(k), sw=sw, closed=False)
    scen_line("pessimistic", 1.4)
    scen_line("optimistic", 1.4)
    scen_line("base", 2.6)
    with c.item("axis-x", "Ось: месяц горизонта модели", "axis", {"gloss": gl("charts", "forecast-fan", "elements", "axis-x")}):
        c.text((x0 + x1) / 2, y1 + 34, "Месяц", 12, THEME["ink"], "middle")
    lel = lambda k: {"id": "legend-scen-%s" % k, "label": "Легенда: %s сценарий" % SCEN_RU[k].lower(), "info": {"gloss": gl("scenarios", k)},
                     "highlight": "g-scen-%s" % k}
    legend_row(c, [("оптимистичный", scol("optimistic"), None), ("базовый", scol("base"), None), ("пессимистичный", scol("pessimistic"), None),
                   ("диапазон", mix(scol("base"), "#FFFFFF", 0.8), None)], x0, y1 + 58, x1 - x0, 12,
               els=[lel("optimistic"), lel("base"), lel("pessimistic"),
                    {"id": "legend-band", "label": "Легенда: диапазон между сценариями", "info": {"gloss": gl("charts", "forecast-fan", "elements", "band")}}])
    return c.finish(ph), title, cap


def ch_cac_ltv(M):
    if M.get("solo"):
        return ch_cac_ltv_solo(M)
    sc = M.get("scenarios") or {}
    names = [k for k in SCEN_RU if k in sc]
    if not names or all(sc[k].get("ltv") is None for k in names):
        return None
    cur = M.get("currency", "")
    W = 900
    base = sc.get("base", sc[names[0]])
    ratio = base.get("ltv_cac")
    title = ("LTV/CAC в базовом сценарии — %s, окупаемость привлечения — %s мес." % (fmt(ratio, 1), fmt(base.get("payback_months"), 1))
             if ratio else "LTV и CAC по сценариям: платного привлечения в базовом сценарии нет")
    cap = "Здоровый ориентир — LTV/CAC ≥ 3 и окупаемость до 12 месяцев; CAC — смешанный, на нового платящего, по платным каналам."
    note = small_note(M)
    if note:
        cap += " Оговорка: " + note + "."
    c = Chart(W, title, cap, "Источник: data/model.json (%s) [допущение]" % cur)
    ph = 340
    x0, x1, y0, y1 = PAD + 60, W - PAD - 10, c.top + 30, c.top + ph - 70
    vmax = max([sc[k].get("ltv") or 0 for k in names] + [sc[k].get("cac") or 0 for k in names] + [1])
    ticks, _ = nice_ticks(0, vmax, 5)
    top = ticks[-1] or 1
    sy = lambda v: y1 - v / top * (y1 - y0)
    for t in ticks:
        c.line(x0, sy(t), x1, sy(t), THEME["grid"])
        c.text(x0 - 6, sy(t) + 4, fmt(t), 11, THEME["muted"], "end")
    gw = (x1 - x0) / len(names)
    bw = min(70, gw / 3.2)
    sym = M.get("currency_symbol") or cur
    for i, k in enumerate(names):
        gx = x0 + i * gw + gw / 2
        lt = sc[k].get("ltv_cac")
        pb = sc[k].get("payback_months")
        for j, (key, lab, col) in enumerate((("cac", "CAC", PAL[1 % len(PAL)]), ("ltv", "LTV", PAL[0]))):
            v = sc[k].get(key) or 0
            bx = gx - bw - 4 + j * (bw + 8)
            raw = sc[k].get(key)
            meaning = ("%s сценарий: %s = %s." % (SCEN_RU[k], lab, money(raw, M)) if raw is not None else
                       "%s сценарий: %s не рассчитан — %s." % (SCEN_RU[k], lab, "платного привлечения нет" if key == "cac" else "нет данных модели"))
            if lt:
                meaning += " LTV/CAC = %s (ориентир ≥ 3)%s." % (fmt(lt, 1), "" if lt >= 3 else " — ниже ориентира")
            mets = [{"label": lab, "value": money(raw, M) if raw is not None else "—", "tag": "допущение"}]
            for ak, al in (("arpu", "ARPU"), ("churn", "Отток в месяц")):
                av = sc[k].get(ak)
                if isinstance(av, (int, float)):
                    mets.append({"label": al, "value": ("%s %%" % fmt(av * 100, 1)) if ak == "churn" else money(av, M, 2), "tag": "допущение"})
            with c.item("%s-%s" % (key, k), "%s, %s сценарий: %s" % (lab, SCEN_RU[k].lower(), money(raw, M) if raw is not None else "не рассчитан"), "bar",
                        {"title": "%s — %s сценарий" % (lab, SCEN_RU[k].lower()), "gloss": gl("terms", key), "meaning": meaning, "metrics": mets, "section": 8}, groups=["g-%s" % key, "g-scen-%s" % k]):
                c.rect(bx, sy(v), bw, y1 - sy(v), col, rx=2)
                c.text(bx + bw / 2, sy(v) - 6, fmt(v, 0), 12, THEME["ink"], "middle", True)
        sub = "LTV/CAC %s · окупаемость %s мес." % (fmt(lt, 1), fmt(pb, 1)) if lt else "без платного привлечения"
        with c.item("scen-%s" % k, "%s сценарий: %s" % (SCEN_RU[k], sub), "column",
                    {"gloss": gl("scenarios", k), "section": 8,
                     "meaning": ("LTV/CAC = %s, окупаемость привлечения — %s мес.; ориентир — LTV/CAC ≥ 3 и до 12 мес." % (fmt(lt, 1), fmt(pb, 1))) if lt
                     else "В этом сценарии нет платного привлечения, поэтому CAC и окупаемость не считаются.",
                     "metrics": [{"label": "LTV/CAC", "value": fmt(lt, 1), "tag": "допущение"}, {"label": "Окупаемость, мес.", "value": fmt(pb, 1), "tag": "допущение"}]},
                    highlight="g-scen-%s" % k):
            c.text(gx, y1 + 18, SCEN_RU[k], 12, THEME["ink"], "middle", True)
            for q, ln in enumerate(wrap(sub, gw - 10, 11)):
                c.text(gx, y1 + 34 + q * 14, ln, 11, THEME["muted"], "middle")
    legend_row(c, [("CAC — стоимость привлечения платящего", PAL[1 % len(PAL)], None), ("LTV — валовая ценность клиента", PAL[0], None)],
               x0, c.top + 14, x1 - x0, 12,
               els=[{"id": "legend-cac", "label": "Легенда: CAC — стоимость привлечения платящего (%s)" % sym,
                     "info": {"gloss": gl("charts", "cac-ltv", "elements", "legend-cac")}, "highlight": "g-cac"},
                    {"id": "legend-ltv", "label": "Легенда: LTV — валовая ценность клиента (%s)" % sym,
                     "info": {"gloss": gl("charts", "cac-ltv", "elements", "legend-ltv")}, "highlight": "g-ltv"}])
    return c.finish(ph), title, cap


def ch_payback(M):
    if M.get("solo"):
        return ch_payback_solo(M)
    sc = M.get("scenarios") or {}
    names = [k for k in SCEN_RU if k in sc and sc[k].get("monthly") and "cum_margin" in sc[k]["monthly"][0]]
    if not names:
        return None
    W = 960
    be = {k: sc[k].get("breakeven_month") for k in names}
    ok = [SCEN_RU[k].lower() for k in names if be[k]]
    title = ("Безубыточность за горизонт достигается в сценариях: %s" % ", ".join(ok)) if ok else "Ни один сценарий не выходит на безубыточность за горизонт"
    note = small_note(M)
    if note:
        title += " (%s)" % note
    cap = "Сплошная линия — накопленная валовая выручка, пунктир — накопленные затраты (постоянные + маркетинг); точка — месяц безубыточности."
    if note:
        cap += " При малом числе платящих безубыточность держится на малых постоянных затратах — смотрите абсолютные суммы."
    c = Chart(W, title, cap, "Источник: data/model.json (%s) [допущение]" % M.get("currency", ""))
    ph = 380
    x0, x1, y0, y1 = PAD + 70, W - PAD - 10, c.top + 8, c.top + ph - 70
    n = len(sc[names[0]]["monthly"])
    vmax = max(max(max(m["cum_margin"], m["cum_cost"]) for m in sc[k]["monthly"]) for k in names) or 1
    ticks, _ = nice_ticks(0, vmax, 5)
    top = ticks[-1] or 1
    sx = lambda i: x0 + (i / max(1, n - 1)) * (x1 - x0)
    sy = lambda v: y1 - v / top * (y1 - y0)
    for t in ticks:
        c.line(x0, sy(t), x1, sy(t), THEME["grid"])
        c.text(x0 - 6, sy(t) + 4, fmt(t), 11, THEME["muted"], "end")
    step = max(1, int(math.ceil(n / 12.0)))
    for i in range(0, n, step):
        c.text(sx(i), y1 + 16, str(i + 1), 11, THEME["muted"], "middle")
    for j, k in enumerate(names):
        col = scol(k)
        mo = sc[k]["monthly"]
        last = mo[-1]
        mpts = [(sx(i), sy(m["cum_margin"])) for i, m in enumerate(mo)]
        with c.item("margin-%s" % k, "%s сценарий: накопленная выручка %s за %d мес." % (SCEN_RU[k], money(last["cum_margin"], M), n), "line",
                    {"title": "Выручка накопленная — %s сценарий" % SCEN_RU[k].lower(), "gloss": gl("terms", "payback"), "section": 8,
                     "meaning": "Накопленная валовая выручка к концу горизонта — %s при накопленных затратах %s; %s." % (
                         money(last["cum_margin"], M), money(last["cum_cost"], M),
                         ("безубыточность с %d-го месяца" % be[k]) if be[k] else "за горизонт не окупается"),
                     "metrics": [{"label": "Выручка накопленная", "value": money(last["cum_margin"], M), "tag": "допущение"},
                                 {"label": "Затраты накопленные", "value": money(last["cum_cost"], M), "tag": "допущение"}]},
                    groups=["g-scen-%s" % k]):
            c.hit(mpts)
            c.poly(mpts, "none", col, sw=2.4, closed=False)
        cpts = [(sx(i), sy(m["cum_cost"])) for i, m in enumerate(mo)]
        with c.item("cost-%s" % k, "%s сценарий: накопленные затраты %s за %d мес." % (SCEN_RU[k], money(last["cum_cost"], M), n), "line",
                    {"title": "Затраты накопленные — %s сценарий" % SCEN_RU[k].lower(), "gloss": gl("terms", "payback"), "section": 8,
                     "summary": "Накопленные затраты (постоянные + маркетинг) в сценарии «%s»." % SCEN_RU[k].lower(),
                     "meaning": "К концу горизонта — %s; пересечение с линией выручки — месяц безубыточности." % money(last["cum_cost"], M),
                     "metrics": [{"label": "Затраты накопленные", "value": money(last["cum_cost"], M), "tag": "допущение"}]},
                    groups=["g-scen-%s" % k]):
            c.hit(cpts)
            c.add('<polyline points="%s" fill="none" stroke="%s" stroke-width="1.6" stroke-dasharray="6 4"/>'
                  % (" ".join("%.1f,%.1f" % p for p in cpts), col))
        if be[k]:
            i = be[k] - 1
            with c.item("be-%s" % k, "%s сценарий: безубыточность с %d-го месяца" % (SCEN_RU[k], be[k]), "point",
                        {"title": "Безубыточность — %s сценарий" % SCEN_RU[k].lower(), "gloss": gl("terms", "payback"), "section": 8,
                         "meaning": "В %d-м месяце накопленная выручка (%s) догоняет накопленные затраты (%s)." % (
                             be[k], money(mo[i]["cum_margin"], M), money(mo[i]["cum_cost"], M)),
                         "metrics": [{"label": "Месяц безубыточности", "value": str(be[k]), "tag": "допущение"}]},
                        groups=["g-scen-%s" % k]):
                c.circle(sx(i), sy(mo[i]["cum_margin"]), 5, col, "#FFFFFF", sw=1.5)
    with c.item("axis-x", "Ось: месяц горизонта модели", "axis", {"gloss": gl("charts", "payback", "elements", "axis-x")}):
        c.text((x0 + x1) / 2, y1 + 34, "Месяц", 12, THEME["ink"], "middle")
    legend_row(c, [("%s%s" % (SCEN_RU[k], ": безубыточность с мес. %d" % be[k] if be[k] else ": не окупается"), scol(k), None)
                   for k in names], x0, y1 + 58, x1 - x0, 12,
               els=[{"id": "legend-scen-%s" % k, "label": "Легенда: %s сценарий, %s" % (SCEN_RU[k].lower(), ("безубыточность с мес. %d" % be[k]) if be[k] else "не окупается"),
                     "info": {"gloss": gl("scenarios", k)}, "highlight": "g-scen-%s" % k} for k in names])
    return c.finish(ph), title, cap


# ---------------------------------------------------------------- рынок
def ch_keywords(K):
    rows = [k for k in K if isinstance(k, dict) and isinstance(k.get("volume"), (int, float)) and k.get("volume") > 0]
    if not rows:
        return None
    rows.sort(key=lambda k: -k["volume"])
    top = rows[:20]
    clusters = list(OrderedDict.fromkeys(k.get("cluster") or "без кластера" for k in top))
    ccol = {cl: PAL[i % len(PAL)] for i, cl in enumerate(clusters)}
    tv = Counter()
    for k in rows:
        tv[k.get("cluster") or "без кластера"] += k["volume"]
    lead = tv.most_common(1)[0][0]
    nonull = len(K) - len(rows)
    title = "Спрос по запросам: крупнейший кластер — «%s» (%s в месяц суммарно)" % (lead, fmt(tv[lead]))
    cap = "Топ-%d %s по объёму; без данных об объёме: %d (не показаны — недоступные цифры не придумываются). Цвет — кластер." % (
        len(top), plural(len(top), ("запрос", "запроса", "запросов")), nonull)
    srcs = sorted({str(k.get("volume_source")) for k in top if k.get("volume_source")})
    items = [("%s (%s)" % (k.get("query", ""), k.get("lang", "")) if k.get("lang") else k.get("query", ""), k["volume"]) for k in top]
    cidx = {cl: i + 1 for i, cl in enumerate(clusters)}
    els = []
    for i, k in enumerate(top, 1):
        cl = k.get("cluster") or "без кластера"
        comp = k.get("competition")
        mets = [{"label": "Объём в месяц", "value": fmt(k["volume"]), "tag": "факт: %s" % k["volume_source"] if k.get("volume_source") else "оценка"}]
        if isinstance(comp, (int, float)) and not isinstance(comp, bool):
            mets.append({"label": "Конкуренция (1–5)", "value": fmt(comp, 1), "tag": "оценка"})
        els.append({"id": "kw-%02d" % i, "label": "Запрос «%s»: %s в месяц, кластер «%s»" % (k.get("query", ""), fmt(k["volume"]), cl),
                    "info": {"title": "Запрос «%s»" % k.get("query", ""), "gloss": gl("terms", "keyword_competition") if isinstance(comp, (int, float)) else None,
                             "section": [4, 6], "metrics": mets,
                             "summary": "Поисковый запрос «%s»%s: %s показов в месяц." % (k.get("query", ""), (" (%s)" % k["lang"]) if k.get("lang") else "", fmt(k["volume"])),
                             "meaning": "%d-й по объёму; кластер «%s» (%s в месяц суммарно)%s%s." % (
                                 i, cl, fmt(tv[cl]), ("; намерение: %s" % k["intent"]) if k.get("intent") else "",
                                 ("; конкуренция %s из 5" % fmt(comp, 1)) if isinstance(comp, (int, float)) and not isinstance(comp, bool) else "")},
                    "groups": ["g-cl-%d" % cidx[cl]]})
    lels = [{"id": "cluster-%d" % cidx[cl], "label": "Легенда: кластер «%s», %s в месяц" % (cl, fmt(tv[cl])),
             "info": {"title": "Кластер «%s»" % cl, "section": [4, 6], "summary": "Кластер запросов «%s»: %d %s в топе графика, суммарно %s в месяц по всем запросам с объёмом." % (
                 cl, sum(1 for k in top if (k.get("cluster") or "без кластера") == cl),
                 plural(sum(1 for k in top if (k.get("cluster") or "без кластера") == cl), ("запрос", "запроса", "запросов")), fmt(tv[cl])),
                 "meaning": "Самый крупный кластер прогона." if cl == lead else "Доля кластера в суммарном объёме — %d %%." % round(100 * tv[cl] / max(1, sum(tv.values())))},
             "highlight": "g-cl-%d" % cidx[cl]} for cl in clusters]
    svg = hbar_chart(title, cap, "Источник: data/keywords.json; объёмы: %s" % (", ".join(srcs) or "не указан"), items, W=960,
                     colors=[ccol[k.get("cluster") or "без кластера"] for k in top],
                     legend=[(cl, ccol[cl], None) for cl in clusters], els=els, legend_els=lels)
    return svg, title, cap


def parse_date(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def ch_events(E):
    ev = [e for e in E if isinstance(e, dict) and parse_date(e.get("date"))]
    if not ev:
        return None
    ev.sort(key=lambda e: parse_date(e["date"]))
    d0, d1 = parse_date(ev[0]["date"]), max(parse_date(e.get("date_end")) or parse_date(e["date"]) for e in ev)
    m0 = date(d0.year, d0.month, 1)
    months = (d1.year - m0.year) * 12 + d1.month - m0.month + 1
    W = 1060
    label_w = 380
    unv = sum(1 for e in ev if not e.get("verified", True))
    title = "Календарь внешних событий: %d %s с %s по %s" % (len(ev), plural(len(ev), ("дата", "даты", "дат")), d0.strftime("%m.%Y"), d1.strftime("%m.%Y"))
    cap = ("Только проверенные даты из официальных источников." if not unv else "%d событий не подтверждены — отмечены полым маркером." % unv)
    c = Chart(W, title, cap, "Источник: data/events.json")
    x0, x1 = PAD + label_w, W - PAD - 10
    mw = (x1 - x0) / max(1, months)
    y = c.top + 26
    kinds = list(OrderedDict.fromkeys(e.get("kind") or "событие" for e in ev))
    kcol = {k: PAL[i % len(PAL)] for i, k in enumerate(kinds)}
    rows = []
    for e in ev:
        tl = wrap("%s · %s" % (parse_date(e["date"]).strftime("%d.%m.%Y"), e.get("title", "")), label_w - 12, 12)
        rows.append((e, tl, max(26, len(tl) * 15 + 10)))
    body = sum(r[2] for r in rows)
    mnames = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
    for m in range(months):
        yy, mm = m0.year + (m0.month - 1 + m) // 12, (m0.month - 1 + m) % 12
        c.line(x0 + m * mw, y, x0 + m * mw, y + body, THEME["grid"], 0.8)
        if months <= 24 or m % 3 == 0:
            c.text(x0 + (m + 0.5) * mw, c.top + 14, mnames[mm] + ("" if mm else " %d" % yy), 11, THEME["muted"], "middle")

    def xpos(d):
        idx = (d.year - m0.year) * 12 + d.month - m0.month
        return x0 + (idx + (d.day - 1) / 31.0) * mw

    kidx = {k: i + 1 for i, k in enumerate(kinds)}
    for n_, (e, tl, rh) in enumerate(rows, 1):
        kind = e.get("kind") or "событие"
        col = kcol[kind]
        ds, de = parse_date(e["date"]), parse_date(e.get("date_end"))
        cy = y + rh / 2
        when = ds.strftime("%d.%m.%Y") + ((" – " + de.strftime("%d.%m.%Y")) if de and de > ds else "")
        ver = e.get("verified", True)
        days = (ds - date.today()).days
        acts = ["Подготовьте к этой дате запуск, пост или заявку на участие заранее (за 4–6 недель)." if days > 0 else
                "На дату сборки событие уже прошло: используйте его итоги (записи, обсуждения) как повод для контента."]
        if not ver:
            acts.append("Проверьте дату по официальному источнику, прежде чем планировать под неё.")
        mets = [{"label": "Дата", "value": when, "tag": "факт" if ver else "не подтверждено"}]
        if e.get("relevance"):
            mets.append({"label": "Значимость", "value": str(e["relevance"]), "tag": "оценка"})
        with c.item("ev-%02d" % n_, "Событие «%s», %s, %s%s" % (e.get("title", ""), kind, when, "" if ver else ", дата не подтверждена"), "event",
                    {"title": "%s — %s" % (e.get("title", ""), when), "section": 4, "actions": acts, "metrics": mets,
                     "summary": "Внешнее событие «%s» (%s), %s." % (e.get("title", ""), kind, when),
                     "meaning": "%s%s%s" % ("Дата подтверждена источником." if ver else "Дата не подтверждена официальным источником.",
                                            (" Значимость для продукта: %s." % e["relevance"]) if e.get("relevance") else "",
                                            (" Источник: %s." % e["source"]) if e.get("source") else "")},
                    groups=["g-kind-%d" % kidx[kind]]):
            c.lines(PAD, y + (rh - len(tl) * 15) / 2 + 12, tl, 12, THEME["ink"])
            if de and de > ds:
                c.rect(xpos(ds), cy - 5, max(4, xpos(de) - xpos(ds)), 10, col, rx=3)
            elif ver:
                c.circle(xpos(ds), cy, 6, col, "#FFFFFF")
            else:
                c.circle(xpos(ds), cy, 6, "#FFFFFF", col, sw=2)
        y += rh
    lels = [{"id": "kind-%d" % kidx[k], "label": "Легенда: вид события «%s»" % k,
             "info": {"title": "Вид события «%s»" % k, "section": 4, "summary": "Вид внешних событий «%s»: %d %s на календаре." % (
                 k, sum(1 for e in ev if (e.get("kind") or "событие") == k), plural(sum(1 for e in ev if (e.get("kind") or "событие") == k), ("событие", "события", "событий"))),
                 "meaning": "Ближайшее: %s." % next(("«%s», %s" % (e.get("title", ""), parse_date(e["date"]).strftime("%d.%m.%Y"))
                                                     for e in ev if (e.get("kind") or "событие") == k), "—")},
             "highlight": "g-kind-%d" % kidx[k]} for k in kinds]
    h = legend_row(c, [(k, kcol[k], None) for k in kinds], x0, y + 26, x1 - x0, 12, els=lels)
    return c.finish(body + 30 + h), title, cap


def ch_competitors(C):
    rows = [x for x in C if isinstance(x, dict) and isinstance(x.get("features"), dict) and x["features"]]
    if not rows:
        return None
    feats = list(OrderedDict.fromkeys(f for x in rows for f in x["features"]))
    fl = feature_labels(C)
    lab = {f: fl.get(f) or humanize(f) for f in feats}
    natural = lambda t: [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", str(t))]
    rows = sorted(rows, key=lambda x: (not x.get("self"), natural(x.get("name") or x.get("slug"))))
    label_w = 230
    longest = max(text_w(w, 11, True) for f in feats for w in lab[f].split() or [lab[f]])
    need_cw = max(64.0, longest + 12)
    vertical = 2 * PAD + label_w + need_cw * len(feats) > 1200
    if vertical:   # тесно: подписи вертикально, целиком, без переноса и обрезки
        W = max(760, min(1200, int(2 * PAD + label_w + 40 * len(feats))))
    else:
        W = max(760, int(2 * PAD + label_w + need_cw * len(feats)))
    cw = (W - 2 * PAD - label_w) / len(feats)
    me = next((x for x in rows if x.get("self")), None)
    share = {f: sum(1 for x in rows if not x.get("self") and x["features"].get(f)) / max(1, sum(1 for x in rows if not x.get("self"))) for f in feats}
    gaps = [f for f in feats if me and not me["features"].get(f) and share[f] >= 0.5]
    title = "Функции конкурентов: %d %s × %d %s" % (len(rows), plural(len(rows), ("продукт", "продукта", "продуктов")),
                                                   len(feats), plural(len(feats), ("функция", "функции", "функций")))
    cap = ("Пробелы нашего продукта, которые есть у большинства конкурентов: %s." % ", ".join(lab[g] for g in gaps)) if gaps else (
        "У нашего продукта нет функций, которые были бы у большинства конкурентов и отсутствовали у нас." if me else "Строка нашего продукта (self) не задана.")
    c = Chart(W, title, cap, "Источник: data/competitors.json; ✓ — функция есть, пусто — нет или не найдено")
    others = [x for x in rows if not x.get("self")]
    planned = bool(me and (me.get("planned") or CONCEPT[0]))
    mine = "в нашей идее" if planned else "у нас"
    fid = {f: sid(f, "f%d" % i) for i, f in enumerate(feats)}

    def feat_info(f):
        have = [x for x in others if x["features"].get(f)]
        ours = bool(me and me["features"].get(f))
        if me and not ours and share[f] >= 0.5:
            verdict = "Пробел: функция есть у большинства конкурентов, но не %s." % mine
            acts = ["Решите, нужна ли функция для базовых ожиданий аудитории; если да — найдите или добавьте предложение в реестр."]
        elif me and ours and share[f] < 0.5:
            verdict = "Отличие: функция есть %s и у меньшинства конкурентов — опора для позиционирования." % mine
            acts = ["Используйте функцию в сообщениях и на посадочной (раздел 5)."]
        else:
            verdict = "Функция %s %s; у конкурентов — %d из %d." % ("есть" if ours else "отсутствует", mine, len(have), len(others)) if me else \
                "Функция есть у %d из %d продуктов." % (len(have), len(others))
            acts = []
        return have, ours, verdict, acts
    if vertical:
        hh = max(text_w(lab[f], 11, True) for f in feats) + 14
    else:
        hdr = [wrap(lab[f], cw - 6, 11, True) for f in feats]
        hh = max(len(h) for h in hdr) * 14 + 8
    for j, f in enumerate(feats):
        have, ours, verdict, acts = feat_info(f)
        with c.item("feature-%s" % fid[f], "Функция «%s»: у %d из %d конкурентов%s" % (lab[f], len(have), len(others), (", " + mine + (" есть" if ours else " нет")) if me else ""),
                    "column", {"title": "Функция «%s»" % lab[f], "section": [3, 5], "actions": acts,
                               "summary": "Функция «%s»: есть у %s." % (lab[f], ", ".join(str(x.get("name") or x.get("slug")) for x in have[:6]) or "ни у кого из конкурентов"),
                               "meaning": verdict,
                               "metrics": [{"label": "Доля конкурентов с функцией", "value": "%d %%" % round(100 * share[f]), "tag": "факт"}],
                               "links": [{"label": "Конкурент: %s" % (x.get("name") or x.get("slug")), "href": "#competitor/%s" % x["slug"]} for x in have[:3] if x.get("slug")]},
                    highlight="g-feat-%s" % fid[f]):
            if vertical:
                hx, hy = PAD + label_w + j * cw + cw / 2 + 4, c.top + hh - 6
                c.add('<text x="%.1f" y="%.1f" font-size="11" font-weight="600" fill="%s" text-anchor="start" '
                      'transform="rotate(-90 %.1f %.1f)">%s</text>' % (hx, hy, THEME["ink"], hx, hy, esc(lab[f])))
            else:
                c.lines(PAD + label_w + j * cw + cw / 2, c.top + 12, hdr[j], 11, THEME["ink"], "middle", True, 1.2)
    y = c.top + hh
    for x in rows:
        tl = wrap(("★ " if x.get("self") else "") + str(x.get("name") or x.get("slug")), label_w - 10, 12)
        rh = max(26, len(tl) * 15 + 8)
        name = str(x.get("name") or x.get("slug"))
        slug = str(x.get("slug") or name)
        if x.get("self"):
            c.rect(PAD - 6, y, W - 2 * PAD + 12, rh, mix(PAL[1], "#FFFFFF", 0.85))
        nf = sum(1 for f in feats if x["features"].get(f))
        acts = ["Перенять: " + a for a in (x.get("adopt") or [])[:2] if isinstance(a, str)] + \
               ["Не повторять: " + a for a in (x.get("avoid") or [])[:2] if isinstance(a, str)]
        mean = []
        if x.get("better_than_us"):
            mean.append("Сильнее нас: " + ", ".join(map(str, x["better_than_us"][:4])))
        if x.get("we_better"):
            mean.append("Мы сильнее: " + ", ".join(map(str, x["we_better"][:4])))
        if x.get("complaints"):
            mean.append("Жалобы пользователей: " + ", ".join(map(str, x["complaints"][:3])))
        if x.get("why_it_worked_or_failed"):
            mean.append("Почему сработало или нет: " + str(x["why_it_worked_or_failed"]))
        mets = [{"label": "Функций из матрицы", "value": "%d из %d" % (nf, len(feats)), "tag": "факт"}]
        for k_, l_ in (("price", "Цена"), ("type", "Тип"), ("kind", "Вид"), ("audience", "Аудитория")):
            if x.get(k_) and not (k_ == "kind" and x.get("self")):
                mets.append({"label": l_, "value": str(x[k_]), "tag": "допущение" if planned and x.get("self") else "факт"})
        lk = [{"label": "Карточка конкурента: %s" % name, "href": "#competitor/%s" % x["slug"]}] if not x.get("self") and x.get("slug") else []
        summ = str(x.get("verdict_long") or x.get("verdict") or "")
        if x.get("self") and planned:
            summ = (summ + " " if summ else "") + "Продукта ещё нет: отмеченные функции — замысел MVP, а не существующие."
        with c.item("competitor-%s" % sid(slug), "%s%s: %d из %d функций" % ("★ наш продукт " if x.get("self") else "", name, nf, len(feats)), "row",
                    {"title": ("★ " if x.get("self") else "") + name, "section": [3] if not x.get("self") else [3, 5], "actions": acts, "metrics": mets, "links": lk,
                     "summary": summ or ("Наш продукт в матрице функций." if x.get("self") else "Конкурент «%s»." % name),
                     "meaning": ". ".join(mean)}, highlight="g-co-%s" % sid(slug)):
            c.lines(PAD, y + (rh - len(tl) * 15) / 2 + 12, tl, 12, THEME["ink"], bold=bool(x.get("self")))
        for j, f in enumerate(feats):
            has = bool(x["features"].get(f))
            cx = PAD + label_w + j * cw
            have, ours, verdict, _ = feat_info(f)
            with c.item("cell-%s-%s" % (sid(slug), fid[f]), "%s — %s: %s" % (name, lab[f], "есть" if has else "нет"), "cell",
                        {"title": "%s — %s" % (name, lab[f]), "section": 3, "links": lk,
                         "summary": "«%s»: функция «%s» — %s." % (name, lab[f], ("запланирована" if has else "не запланирована") if x.get("self") and planned
                                                                  else ("есть" if has else "нет или не найдена")),
                         "meaning": verdict},
                        groups=["g-feat-%s" % fid[f], "g-co-%s" % sid(slug)]):
                c.rect(cx + 2, y + 2, cw - 4, rh - 4, PAL[0] if has else THEME["panel"], rx=3)
                if has:
                    c.text(cx + cw / 2, y + rh / 2 + 5, "✓", 14, "#FFFFFF", "middle", True)
        y += rh
    return c.finish(y - c.top + 4), title, cap


# ---------------------------------------------------------------- деньги и подписи
def money(x, M, nd=0):
    """Сумма с символом валюты модели."""
    sym = (M or {}).get("currency_symbol") or (M or {}).get("currency") or ""
    return ("%s %s" % (fmt(x, nd), sym)).strip()


ABBR = {"api", "mcp", "ai", "seo", "pdf", "csv", "rss", "sso", "ui", "ux", "vk", "tg", "oss", "cli", "sdk", "er", "crm",
        "json", "ios", "url", "og", "pwa", "id", "2fa", "llm", "gpt", "faq", "kpi", "cta", "utm", "ab", "b2b", "b2c"}


def humanize(key):
    """snake_case/kebab-case → «Читаемая подпись» (аббревиатуры прописными); уже человекочитаемое не трогается."""
    s = str(key)
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", s) or ("_" not in s and "-" not in s and not s.islower()):
        return s
    parts = [w for w in re.split(r"[_\-]+", s) if w]
    out = [w.upper() if w.lower() in ABBR else w.lower() for w in parts]
    if out and out[0] == out[0].lower():
        out[0] = out[0][:1].upper() + out[0][1:]
    return " ".join(out)


def feature_labels(C):
    """Подписи функций: features_labels из записей competitors.json (первое значение побеждает), иначе humanize."""
    labels = {}
    for x in C if isinstance(C, list) else []:
        if isinstance(x, dict) and isinstance(x.get("features_labels"), dict):
            for k, v in x["features_labels"].items():
                if isinstance(v, str) and v.strip() and k not in labels:
                    labels[k] = v.strip()
    return labels


def arrow(c, x1, y1, x2, y2, color, sw=1.4, dash=None, hit=False):
    """Кривая Безье слева направо с треугольником-наконечником (без marker/url — правило «без внешних ссылок»).
    hit=True — невидимая широкая обводка для попадания мышью (элемент-стрелка)."""
    mx = (x1 + x2) / 2
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    if hit:
        c.add('<path d="M %.1f %.1f C %.1f %.1f, %.1f %.1f, %.1f %.1f" fill="none" stroke="#000000" stroke-opacity="0" stroke-width="12"/>'
              % (x1, y1, mx, y1, mx, y2, x2 - 6, y2))
    c.add('<path d="M %.1f %.1f C %.1f %.1f, %.1f %.1f, %.1f %.1f" fill="none" stroke="%s" stroke-width="%s"%s/>'
          % (x1, y1, mx, y1, mx, y2, x2 - 6, y2, color, sw, d))
    c.poly([(x2, y2), (x2 - 8, y2 - 4.5), (x2 - 8, y2 + 4.5)], color)


# ---------------------------------------------------------------- зависимости
def ch_critical_path(CP, S, P=None):
    props_ids = {p.get("id") for p in P or [] if isinstance(p, dict)}
    edges = [e for e in (CP or {}).get("edges") or [] if isinstance(e, list) and len(e) == 2]
    if not edges:
        return None
    meta = {n["id"]: n for n in CP.get("nodes") or [] if isinstance(n, dict) and n.get("id")}
    srow = {r["id"]: r for r in S or []}
    used = sorted({x for e in edges for x in e}, key=lambda v: (meta.get(v, {}).get("rank") or srow.get(v, {}).get("rank") or 10 ** 6, v))
    order = [v for v in CP.get("order") or [] if v in used]
    on = set(order)
    path_edges = {(a, b) for a, b in zip(order, order[1:])}
    preds = {v: [a for a, b in edges if b == v] for v in used}
    level = {}
    for _ in range(len(used) + 1):   # самый длинный путь от истоков (DAG; циклы разорваны score.py)
        changed = False
        for v in used:
            lv = 1 + max((level.get(u, 0) for u in preds[v]), default=-1)
            if level.get(v) != lv:
                level[v], changed = lv, True
        if not changed:
            break
    ncol = max(level.values()) + 1
    gap = 46
    W = 1160
    bw = (W - 2 * PAD - (ncol - 1) * gap) / ncol
    if bw < 150:
        bw = 150
        W = int(2 * PAD + ncol * bw + (ncol - 1) * gap)
    bw = min(bw, 260)
    rank = lambda v: meta.get(v, {}).get("rank") or srow.get(v, {}).get("rank")
    title_of = lambda v: meta.get(v, {}).get("title") or srow.get(v, {}).get("title") or ""
    top_n = CP.get("top_n", 20)
    steps = len(order)
    if order:
        title = "Критический путь к топ-%d: %d %s — %s" % (top_n, steps, plural(steps, ("шаг", "шага", "шагов")), " → ".join(order))
    else:
        title = "Зависимости топ-%d: %d %s, критической цепочки нет" % (top_n, len(edges), plural(len(edges), ("связь", "связи", "связей")))
    out_top = sum(1 for v in used if not meta.get(v, {}).get("in_top", True))
    cap = ("Цепочка с наибольшей суммой composite, ведущая в топ-%d (выделена). Стрелка — «нужно сделать до»; "
           "пунктирная рамка — предпосылка вне топа (%d). Порядок работ — dep_rank, а не rank." % (top_n, out_top))
    c = Chart(W, title, cap, "Источник: data/critical-path.json, data/scores.json (score.py: blocked_by, dep_rank)")
    boxes, colh = {}, {}
    x0 = PAD + (W - 2 * PAD - (ncol * bw + (ncol - 1) * gap)) / 2
    for col in range(ncol):
        y = c.top + 6
        for v in [u for u in used if level[u] == col]:
            tl = wrap(title_of(v), bw - 16, 11)
            h = 22 + len(tl) * 13.5 + 10
            boxes[v] = (x0 + col * (bw + gap), y, h, tl)
            y += h + 14
        colh[col] = y - c.top
    body = max(colh.values())
    hot = THEME["bad"]

    def edge(a, b, color, sw, crit):
        xa, ya, ha, _ = boxes[a]
        xb, yb, hb, _ = boxes[b]
        lab = "Зависимость: %s нужно сделать до %s%s" % (a, b, " (критический путь)" if crit else "")
        with c.item("edge-%s-%s" % (a, b), lab, "link",
                    {"title": "%s → %s" % (a, b), "gloss": gl("terms", "critical_path" if crit else "dependency"), "plinks": [a, b],
                     "summary": "%s «%s» нужно сделать до %s «%s»." % (a, title_of(a), b, title_of(b)),
                     "meaning": ("Звено критического пути: задержка %s сдвигает всю цепочку." % a) if crit else
                     "Обычная зависимость вне критического пути: её можно планировать с запасом."},
                    groups=["g-path"] if crit else ["g-dep"]):
            arrow(c, xa + bw, ya + ha / 2, xb, yb + hb / 2, color, sw, hit=True)
    for a, b in edges:
        if a in boxes and b in boxes and (a, b) not in path_edges:
            edge(a, b, THEME["axis"], 1.2, False)
    for a, b in sorted(path_edges):     # порядок отрисовки детерминирован (set зависит от PYTHONHASHSEED)
        edge(a, b, hot, 2.6, True)
    for v, (x, y, h, tl) in boxes.items():
        in_top = meta.get(v, {}).get("in_top", True)
        fill = mix(hot, "#FFFFFF", 0.88) if v in on else THEME["bg"]
        stroke = hot if v in on else (PAL[0] if in_top else THEME["axis"])
        dash = "" if in_top else ' stroke-dasharray="5 4"'
        dr = meta.get(v, {}).get("dep_rank") or srow.get(v, {}).get("dep_rank")
        before = [a for a, b in edges if b == v]
        after = [b for a, b in edges if a == v]
        role = ("шаг %d из %d критического пути" % (order.index(v) + 1, steps)) if v in on else ("в топ-%d" % top_n if in_top else "предпосылка вне топа")
        mean = "%s; ранг %s%s." % (role.capitalize(), rank(v) or "—", (", порядок работ (dep_rank) %s" % dr) if dr else "")
        if before:
            mean += " Сначала нужно: %s." % ", ".join(before)
        if after:
            mean += " Открывает: %s." % ", ".join(after)
        with c.item(v, "%s — %s: %s" % (v, title_of(v), role), "node",
                    {"pid": v, "gloss": gl("terms", "critical_path") if v in on else None, "meaning": mean,
                     "summary": "" if v in props_ids else "Предложение %s «%s» (нет в data/proposals.json)." % (v, title_of(v))},
                    groups=["g-path"] if v in on else (["g-top"] if in_top else ["g-out"])):
            c.add('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="6" fill="%s" stroke="%s" stroke-width="%s"%s/>'
                  % (x, y, bw, h, fill, stroke, 2 if v in on else 1.2, dash))
            c.text(x + 8, y + 16, "%s · ранг %s%s" % (v, rank(v) or "—", " · порядок %s" % dr if dr else ""), 11,
                   hot if v in on else THEME["ink"], bold=True)
            c.lines(x + 8, y + 32, tl, 11, THEME["ink"], lh=1.23)
    lel = lambda i, k, lab: {"id": "legend-%s" % k, "label": "Легенда: " + lab, "info": {"gloss": gl("charts", "critical-path", "elements", "legend-%s" % k)},
                             "highlight": "g-%s" % k}
    h = legend_row(c, [("критический путь", hot, None), ("в топ-%d" % top_n, PAL[0], None), ("вне топа (пунктир)", THEME["axis"], None)],
                   PAD, c.top + body + 22, W - 2 * PAD, 12,
                   els=[lel(0, "path", "критический путь"), lel(1, "top", "в топ-%d" % top_n), lel(2, "out", "вне топа (пунктир)")])
    return c.finish(body + 22 + h), title, cap


# ---------------------------------------------------------------- каналы привлечения
CHANNELS = [
    ("seo", "SEO и поисковые страницы", r"\bseo\b|страниц\w*[- ]ответ|поисков|мета-?тег|sitemap|google|яндекс|serp|ключев\w* запрос|выдач"),
    ("community", "Сообщества и форумы", r"сообществ|форум|reddit|r/\w+|хабр|habr|hacker ?news|show hn|vc\.ru|пикабу|discord|community|чат\w* (админ|разработ)"),
    ("content", "Контент и PR", r"стать|блог|обзор|видео|youtube|подкаст|пресс|\bpr\b|анонс|рассылк|newsletter|кейс|гайд|инструкц"),
    ("catalogs", "Каталоги и магазины приложений", r"каталог|awesome|product ?hunt|alternativeto|маркетплейс|store\b|rustore|google play|app ?store|f-droid|реестр|directory|winget|homebrew|pypi"),
    ("viral", "Виральность и шаринг", r"шаринг|поделит|\bshare|wrapped|итог\w* года|приглаш|referral|реферал|вирус|подпис\w* «|watermark|карточк\w* для"),
    ("partners", "Партнёрства и интеграции", r"партн[её]р|интеграц|амбассад|ambassador|сотруднич|bundle|колла"),
    ("events", "События и конференции", r"конференц|митап|meetup|хакатон|fosdem|40c3|доклад"),
    ("paid", "Платная реклама", r"реклам|\bads\b|таргет|контекстн|promoted|sponsor"),
    ("site", "Сайт, демо и посадочные", r"лендинг|landing|посадочн|сайт|github pages|демо|demo"),
]


def channel_of(p):
    """Канал предложения: совпадения в тегах и названии ×3, в описании ×1; ничья — по порядку CHANNELS."""
    tags = " ".join(map(str, p.get("tags") or [])).lower()
    title = str(p.get("title") or "").lower()
    desc = "%s %s" % (p.get("description") or "", p.get("segment") or "")
    best = (0, None)
    for k, (key, _, rx) in enumerate(CHANNELS):
        s = 3 * len(re.findall(rx, tags + " " + title)) + len(re.findall(rx, desc.lower()))
        if s > best[0]:
            best = (s, key)
    return best[1] or "other"


def ch_channel_mix(P, S):
    acq = [p for p in P if isinstance(p, dict) and p.get("category") == "acquisition"]
    if not acq:
        return None
    comp = {r["id"]: max(0.0, r.get("composite") or 0.0) for r in S or []}
    names = dict((k, lab) for k, lab, _ in CHANNELS)
    names["other"] = "Прочее"
    cnt, csum, ids = Counter(), Counter(), {}
    for p in acq:
        ch = channel_of(p)
        cnt[ch] += 1
        csum[ch] += comp.get(p.get("id"), 0.0)
        ids.setdefault(ch, []).append(p.get("id"))
    tot_n, tot_c = sum(cnt.values()), sum(csum.values())
    has_c = tot_c > 0
    keys = sorted(cnt, key=lambda k: (-(csum[k] if has_c else cnt[k]), -cnt[k], k))
    lead = keys[0]
    W = 980
    title = "Каналы привлечения: «%s» — %d %% предложений%s" % (
        names[lead], round(100 * cnt[lead] / tot_n), (" и %d %% суммарного composite" % round(100 * csum[lead] / tot_c)) if has_c else "")
    cap = ("Структура %d %s категории «Привлечение» по каналам: доля по числу и по сумме composite (вклад с учётом оценки). "
           "Канал определён по тегам и тексту предложения (эвристика по ключевым словам)." % (tot_n, plural(tot_n, ("предложения", "предложений", "предложений"))))
    c = Chart(W, title, cap, "Источник: data/proposals.json (category=acquisition, tags, title, description), data/scores.json (composite)")
    label_w = 260
    x0, x1 = PAD + label_w, W - PAD - 150
    y = c.top + 4
    c_n, c_c = PAL[0], PAL[1 % len(PAL)]
    rk = {r["id"]: r.get("rank", 10 ** 6) for r in S or []}
    for k in keys:
        tl = wrap(names[k], label_w - 12, 12)
        rh = max(44, len(tl) * 15 + 14)
        sn = cnt[k] / tot_n
        wn = sn * (x1 - x0)
        sc = csum[k] / tot_c if has_c else None
        best = sorted(ids[k], key=lambda i: (rk.get(i, 10 ** 6), str(i)))[:3]
        mets = [{"label": "Предложений", "value": str(cnt[k]), "tag": "факт"}, {"label": "Доля по числу", "value": "%d %%" % round(sn * 100), "tag": "расчёт"}]
        if has_c:
            mets.append({"label": "Доля по composite", "value": "%d %%" % round(sc * 100), "tag": "расчёт"})
        with c.item("ch-%s" % k, "Канал «%s»: %d %% предложений%s" % (names[k], round(sn * 100), (", %d %% composite" % round(sc * 100)) if has_c else ""), "bar",
                    {"gloss": gl("channels", k), "related": best, "registry": {"category": "acquisition"}, "metrics": mets, "section": 6,
                     "meaning": "%d %s привлечения%s%s." % (cnt[k], plural(cnt[k], ("предложение", "предложения", "предложений")),
                                                       (" дают %d %% суммарного composite" % round(sc * 100)) if has_c else "",
                                                       ("; это сильнее среднего — предложения канала оценены выше" if has_c and sc > sn + 0.05 else
                                                        ("; слабее среднего — предложения канала оценены ниже" if has_c and sc < sn - 0.05 else "")))}):
            c.lines(PAD, y + (rh - len(tl) * 15) / 2 + 12, tl, 12, THEME["ink"])
            c.add('<g data-ps-group="g-count">')
            c.rect(x0, y + 6, wn, 13, c_n, rx=2)
            c.add("</g>")
            c.text(x0 + wn + 6, y + 17, "%d %% · %d %s" % (round(sn * 100), cnt[k], plural(cnt[k], ("предложение", "предложения", "предложений"))), 11, THEME["ink"])
            if has_c:
                wc = sc * (x1 - x0)
                c.add('<g data-ps-group="g-composite">')
                c.rect(x0, y + 22, wc, 13, c_c, rx=2)
                c.add("</g>")
                c.text(x0 + wc + 6, y + 33, "%d %% composite" % round(sc * 100), 11, THEME["ink"])
        y += rh
    c.line(x0, c.top, x0, y, THEME["axis"])
    lels = [{"id": "legend-count", "label": "Легенда: доля по числу предложений", "info": {"gloss": gl("charts", "channel-mix", "elements", "legend-count")},
             "highlight": "g-count"},
            {"id": "legend-composite", "label": "Легенда: доля по сумме composite", "info": {"gloss": gl("charts", "channel-mix", "elements", "legend-composite")},
             "highlight": "g-composite"}]
    h = legend_row(c, [("доля по числу предложений", c_n, None)] + ([("доля по сумме composite", c_c, None)] if has_c else []),
                   x0, y + 24, x1 - x0, 12, els=lels)
    return c.finish(y - c.top + 24 + h), title, cap


# ---------------------------------------------------------------- дерево метрик
KPI_FAMILIES = [
    ("acquisition", "Привлечение: визиты, установки, охват", r"визит|посетит|трафик|переход|установ|install|скачив|загруз|охват|показ|просмотр|клик|ctr|звёзд|звезд|stars|упоминан|органич|подписчик"),
    ("activation", "Активация: первый результат", r"активац|перв\w+ (результат|запуск|отчёт|отчет)|онбординг|мастер|время до|завершен|подключ|регистрац|time to"),
    ("retention", "Удержание и возвраты", r"удержан|retention|отток|churn|d30|d7|возврат|возвращ|недельн\w* актив|wau|mau|dau"),
    ("engagement", "Вовлечённость: регулярное использование", r"использован|открыти|частот|сесси|повторн|поиск|доля пользовател|ежеднев|еженедел"),
    ("revenue", "Монетизация", r"\bpro\b|оплат|выручк|revenue|платящ|конверси\w* в|подписк|arppu|arpu|ltv|тариф|доход|спонсор|донат"),
    ("referral", "Рекомендации и шаринг", r"приглаш|шаринг|поделил|referral|реферал|вирус|репост|карточк|nps|рекоменд"),
    ("quality", "Качество и доверие", r"ошибк|сбо[йе]|crash|скорост|время ответ|доступност|контраст|отзыв|доверие|жалоб|безопасн|приватн"),
]
CAT_TO_FAMILY = {"acquisition": "acquisition", "conversion": "activation", "retention": "retention", "monetization": "revenue",
                 "analytics": "quality", "product": "engagement", "partnerships": "acquisition", "localization": "acquisition",
                 "new_lines": "acquisition", "platform": "quality"}


def kpi_families(ns):
    """Семейства входных метрик: из north-star.json inputs ([{name, match}] или строки), иначе встроенные."""
    inputs = ns.get("inputs") if isinstance(ns, dict) else None
    fams = []
    for k, x in enumerate(inputs or []):
        if isinstance(x, dict) and x.get("name"):
            rx = x.get("match") or "|".join(re.escape(w.lower()[:5]) for w in str(x["name"]).split() if len(w) > 3) or re.escape(str(x["name"]).lower())
            fams.append(("in%d" % k, str(x["name"]), rx))
        elif isinstance(x, str) and x.strip():
            rx = "|".join(re.escape(w.lower()[:5]) for w in x.split() if len(w) > 3) or re.escape(x.lower())
            fams.append(("in%d" % k, x.strip(), rx))
    return fams or KPI_FAMILIES


def north_star(cfg, ns):
    for v in ((ns or {}).get("metric"), (ns or {}).get("name"), ((cfg or {}).get("strategy") or {}).get("north_star"),
              ((cfg or {}).get("project") or {}).get("north_star"), (cfg or {}).get("north_star")):
        if isinstance(v, str) and v.strip():
            return v.strip(), True
    return "Целевая метрика (North Star не задана)", False


def ch_kpi_tree(P, S, cfg, ns):
    props = [p for p in P if isinstance(p, dict) and p.get("id")]
    if not any(isinstance(p.get("effect_kpi"), list) and p["effect_kpi"] for p in props):
        return None
    rank = {r["id"]: r.get("rank", 10 ** 6) for r in S or []}
    fams = kpi_families(ns)
    custom = fams is not KPI_FAMILIES
    members = {k: set() for k, _, _ in fams}
    for p in props:
        hit = set()
        for kp in p.get("effect_kpi") or []:
            txt = str(kp.get("kpi") if isinstance(kp, dict) else kp or "").lower().replace("ё", "е")
            for k, _, rx in fams:
                if re.search(rx, txt):
                    hit.add(k)
                    break
        if not hit and not custom:
            hit.add(CAT_TO_FAMILY.get(p.get("category"), "engagement"))
        for k in hit:
            members[k].add(p["id"])
    show = [(k, lab) for k, lab, _ in fams if members[k]]
    if not show:
        return None
    title_of = {p["id"]: p.get("title", "") for p in props}
    ns_name, ns_set = north_star(cfg, ns)
    W = 1180
    col1, col2 = PAD, PAD + 250
    col3 = col2 + 290
    c_w3 = W - PAD - col3
    nprop = sum(min(3, len(members[k])) for k, _ in show)
    title = "Дерево метрик: «%s» ← %d %s ← %d %s" % (
        ns_name if ns_set else "целевая метрика", len(show), plural(len(show), ("входная метрика", "входные метрики", "входных метрик")),
        nprop, plural(nprop, ("предложение", "предложения", "предложений")))
    cap = ("Входные метрики выведены из effect_kpi реестра по ключевым словам%s; у каждой — до трёх лучших предложений по рангу, "
           "в скобках — сколько всего предложений на неё влияет.%s" % (
               "" if custom else " (без совпадения — по категории предложения)",
               "" if ns_set else " North Star не задана: впишите её в data/north-star.json (ключ metric)."))
    c = Chart(W, title, cap, "Источник: data/proposals.json (effect_kpi), data/scores.json (rank), %s"
              % ("data/north-star.json или run-config" if ns_set else "North Star не задана"))
    y = c.top + 4
    blocks = []
    for k, lab in show:
        ids = sorted(members[k], key=lambda i: (rank.get(i, 10 ** 6), i))
        top3 = ids[:3]
        lines = []
        for i in top3:
            tl = wrap("%s %s" % (i, title_of.get(i, "")), c_w3 - 10, 11)
            lines.append((i, tl))
        lab_l = wrap("%s (%d)" % (lab, len(ids)), 270 - 16, 12, True)
        bh = max(len(lab_l) * 15 + 16, sum(len(tl) * 13.5 + 8 for _, tl in lines))
        blocks.append((k, lab_l, lines, y, bh))
        y += bh + 16
    body = y - c.top
    ns_l = wrap(ns_name, 220 - 16, 13, True)
    nh = len(ns_l) * 17 + 34
    ny = c.top + max(0, (body - nh) / 2)
    hot = PAL[0]
    fam_sec = {"acquisition": 6, "activation": 7, "retention": 9, "engagement": 10, "revenue": 8, "referral": 6, "quality": 11}
    flab = dict(show)
    kpis_of = {p["id"]: [str(kp.get("kpi") if isinstance(kp, dict) else kp) for kp in p.get("effect_kpi") or []] for p in props}
    for k, lab_l, lines, by, bh in blocks:
        cy = by + bh / 2
        ids = sorted(members[k], key=lambda i: (rank.get(i, 10 ** 6), i))
        with c.item("edge-north-star-%s" % k, "Связь: «%s» двигает North Star" % flab[k], "link",
                    {"title": "«%s» → North Star" % flab[k], "gloss": gl("terms", "north_star"), "section": 12,
                     "summary": "Входная метрика «%s» — одна из величин, которые двигают North Star «%s»." % (flab[k], ns_name),
                     "meaning": "На неё влияет %d %s реестра." % (len(ids), plural(len(ids), ("предложение", "предложения", "предложений")))},
                    groups=["g-fam-%s" % k]):
            arrow(c, col1 + 220, ny + nh / 2, col2, cy, THEME["axis"], 1.3, hit=True)
        ly = by
        for i, tl in lines:
            h = len(tl) * 13.5 + 8
            hits = [x for x in kpis_of.get(i, []) if x]
            with c.item("leaf-%s-%s" % (k, i), "%s — %s: влияет на «%s»" % (i, title_of.get(i, ""), flab[k]), "node",
                        {"pid": i, "deep": [("kpi-tree", "kpi-%s" % k, "Метрика «%s» в дереве" % flab[k])],
                         "meaning": "Ранг %s; влияет на входную метрику «%s»%s." % (
                             rank.get(i) if rank.get(i, 10 ** 6) < 10 ** 6 else "—", flab[k], (" через effect_kpi: " + "; ".join(hits[:3])) if hits else " (по категории предложения)")},
                        groups=["g-fam-%s" % k]):
                arrow(c, col2 + 270, cy, col3, ly + h / 2, THEME["grid"], 1.1)
                c.lines(col3 + 6, ly + 14, tl, 11, THEME["ink"], lh=1.23)
            ly += h
        lh = len(lab_l) * 15 + 16
        g_ = gl("kpi_families", k) + gl("kpi_families", "custom")
        with c.item("kpi-%s" % k, "Входная метрика «%s»: %d %s" % (flab[k], len(ids), plural(len(ids), ("предложение", "предложения", "предложений"))), "node",
                    {"title": flab[k], "gloss": g_, "related": ids[:3], "section": [12, fam_sec.get(k)] if fam_sec.get(k) else 12,
                     "summary": "" if not custom else "Входная метрика «%s» из data/north-star.json (inputs)." % flab[k],
                     "meaning": "На метрику влияет %d %s реестра; лучшие по рангу: %s." % (
                         len(ids), plural(len(ids), ("предложение", "предложения", "предложений")), ", ".join(ids[:3])),
                     "metrics": [{"label": "Предложений влияет", "value": str(len(ids)), "tag": "расчёт"}]},
                    highlight="g-fam-%s" % k):
            c.rect(col2, cy - lh / 2, 270, lh, mix(hot, "#FFFFFF", 0.88), hot, rx=6)
            c.lines(col2 + 8, cy - lh / 2 + 19, lab_l, 12, THEME["ink"], bold=True)
    with c.item("kpi-north-star", "North Star: %s" % ns_name, "node",
                {"title": "North Star: %s" % ns_name, "gloss": gl("terms", "north_star"), "section": 12,
                 "summary": ("North Star продукта — «%s»: главная метрика ценности для пользователя." % ns_name) if ns_set else "",
                 "meaning": ("" if ns_set else "North Star не задана: дерево построено вокруг условной «целевой метрики». ") +
                 "Её двигают %d %s: %s." % (len(show), plural(len(show), ("входная метрика", "входные метрики", "входных метрик")),
                                             ", ".join("«%s»" % l for _, l in show)),
                 "actions": [] if ns_set else ["Задайте North Star в data/north-star.json (ключ metric) и перестройте графики."]}):
        c.rect(col1, ny, 220, nh, hot, rx=8)
        c.text(col1 + 10, ny + 18, "North Star", 11, "#FFFFFF")
        c.lines(col1 + 10, ny + 36, ns_l, 13, "#FFFFFF", bold=True, lh=1.3)
    return c.finish(body), title, cap


# ---------------------------------------------------------------- спрос без объёмов
def ch_keywords_clusters(K):
    rows = [k for k in K if isinstance(k, dict) and k.get("query")]
    if not rows:
        return None
    cl = OrderedDict()
    for k in rows:
        cl.setdefault(str(k.get("cluster") or "без кластера"), []).append(k)
    stats = []
    for name, ks in cl.items():
        comp = [k["competition"] for k in ks if isinstance(k.get("competition"), (int, float)) and not isinstance(k.get("competition"), bool)]
        vol = [k["volume"] for k in ks if isinstance(k.get("volume"), (int, float)) and not isinstance(k.get("volume"), bool) and k["volume"] > 0]
        stats.append((name, len(ks), statistics.mean(comp) if comp else None, sum(vol) if vol else None, len(vol)))
    stats.sort(key=lambda s: (-s[1], s[2] if s[2] is not None else 9, s[0]))
    nvol = sum(s[4] for s in stats)
    with_c = [s for s in stats if s[2] is not None]
    easy = min(with_c, key=lambda s: (s[2], -s[1])) if with_c else None
    title = "Спрос по кластерам: больше всего запросов в «%s» (%d)%s" % (
        stats[0][0], stats[0][1], ("; наименьшая конкуренция — «%s» (%s из 5)" % (easy[0], fmt(easy[2], 1))) if easy else "")
    cap = ("%d %s в %d %s; %s. Длина полосы — число запросов кластера, цвет — средняя конкуренция (1 — слабая, "
           "5 — сильная); недоступные объёмы не придумываются." % (
               len(rows), plural(len(rows), ("запрос", "запроса", "запросов")), len(stats), plural(len(stats), ("кластере", "кластерах", "кластерах")),
               ("объёмы известны для %d из них" % nvol) if nvol else "объёмов поиска нет ни для одного (нужен вход в Wordstat/Keyword Planner)"))

    def ccol(v):
        if v is None:
            return THEME["neutral"]
        return THEME["good"] if v < 2.5 else (PAL[1 % len(PAL)] if v < 3.5 else THEME["bad"])

    items = [(s[0], s[1]) for s in stats]

    def clev(v):
        return "none" if v is None else ("low" if v < 2.5 else ("mid" if v < 3.5 else "high"))
    els = []
    for i, st in enumerate(stats, 1):
        name, n_q, comp, vol, nv = st
        qs = [k.get("query", "") for k in cl[name]][:5]
        mets = [{"label": "Запросов", "value": str(n_q), "tag": "факт"}]
        if comp is not None:
            mets.append({"label": "Средняя конкуренция (1–5)", "value": fmt(comp, 1), "tag": "оценка"})
        if vol:
            mets.append({"label": "Объём в месяц (известный)", "value": fmt(vol), "tag": "факт"})
        els.append({"id": "cluster-%d" % i, "label": "Кластер «%s»: %d %s, конкуренция %s" % (
            name, n_q, plural(n_q, ("запрос", "запроса", "запросов")), (fmt(comp, 1) + " из 5") if comp is not None else "не оценена"),
                    "info": {"title": "Кластер «%s»" % name, "gloss": gl("terms", "keyword_competition"), "section": [4, 6], "metrics": mets,
                             "summary": "Кластер поисковых запросов «%s»: %s%s." % (name, ", ".join("«%s»" % q for q in qs), " и др." if n_q > len(qs) else ""),
                             "meaning": "%d %s, средняя конкуренция %s; объём известен для %d из них.%s" % (
                                 n_q, plural(n_q, ("запрос", "запроса", "запросов")), (fmt(comp, 1) + " из 5") if comp is not None else "не оценена", nv,
                                 " Наименьшая конкуренция среди кластеров — хорошая точка входа." if easy and easy[0] == name else "")},
                    "groups": ["g-comp-%s" % clev(comp)]})
    lels = [{"id": "legend-comp-%s" % lv, "label": "Легенда: %s" % lab,
             "info": {"gloss": gl("charts", "keywords-clusters", "elements", "legend-comp-%s" % lv),
                      "meaning": "Таких кластеров: %d." % sum(1 for st in stats if clev(st[2]) == lv)},
             "highlight": "g-comp-%s" % lv}
            for lv, lab in (("low", "конкуренция < 2,5"), ("mid", "конкуренция 2,5–3,5"), ("high", "конкуренция ≥ 3,5"), ("none", "нет оценки конкуренции"))]

    def value_fmt_factory():
        it = iter(stats)

        def f(v):
            s = next(it)
            parts = ["%d %s" % (s[1], plural(s[1], ("запрос", "запроса", "запросов")))]
            parts.append("конкуренция %s/5" % fmt(s[2], 1) if s[2] is not None else "конкуренция —")
            if s[3]:
                parts.append("%s в мес." % fmt(s[3]))
            return " · ".join(parts)
        return f
    svg = hbar_chart(title, cap, "Источник: data/keywords.json (cluster, competition%s)" % (", volume" if nvol else ""), items, W=1040,
                     colors=[ccol(s[2]) for s in stats], value_fmt=value_fmt_factory(), right_pad=270 if nvol else 200, int_ticks=True,
                     legend=[("конкуренция < 2,5", THEME["good"], None), ("2,5–3,5", PAL[1 % len(PAL)], None), ("≥ 3,5", THEME["bad"], None),
                             ("нет оценки", THEME["neutral"], None)], els=els, legend_els=lels)
    return svg, title, cap


# ---------------------------------------------------------------- нулевой бюджет
def small_note(M):
    """Оговорка с абсолютными суммами для малого числа платящих (базовый сценарий)."""
    sc = (M.get("scenarios") or {}).get("base") or {}
    t = sc.get("totals") or {}
    n = t.get("new_paying")
    if n is None or n >= 50:
        return ""
    return "базовый сценарий за %s мес.: %s %s, %s чистой выручки" % (
        M.get("horizon_months", "—"), fmt(n, 1 if n < 10 else 0), plural(round(n), ("новый платящий", "новых платящих", "новых платящих")),
        money(t.get("net_revenue") or 0, M))


def ch_cac_ltv_solo(M):
    solo = M.get("solo") or {}
    sc = solo.get("scenarios") or {}
    names = [k for k in SCEN_RU if k in sc]
    if not names:
        return None
    base = sc.get("base", sc[names[0]])
    rate = ((solo.get("params") or {}).get("hourly_rate") or {}).get("value")
    W = 960
    hpa = base.get("hours_per_activated")
    title = ("Нулевой бюджет: %s ч разработчика на одного активированного пользователя (базовый сценарий)" % fmt(hpa, 1)
             if hpa is not None else "Нулевой бюджет: активированных пользователей в базовом сценарии нет")
    note = small_note(M)
    cap = ("CAC неприменим — платного привлечения нет, цена роста — время разработчика (доля ёмкости на привлечение — допущение). "
           "Справа — валовая выручка на час разработчика против его ставки%s." % ("; " + note if note else ""))
    c = Chart(W, title, cap, "Источник: data/model.json (solo, %s) [допущение]" % M.get("currency", ""))
    REG.variant = "cac-ltv-solo"
    ph = 320
    pw = (W - 2 * PAD - 60) / 2
    panels = [("hours_per_activated", "Часов на активированного", lambda v: fmt(v, 1) + " ч", None),
              ("revenue_per_hour", "Выручка на час разработчика", lambda v: money(v, M, 0) + "/ч", rate)]
    short = {"hours_per_activated": "hpa", "revenue_per_hour": "rph"}
    for pi, (key, lab, vf, ref) in enumerate(panels):
        x0 = PAD + 50 + pi * (pw + 60)
        x1 = x0 + pw - 40
        y0, y1 = c.top + 30, c.top + ph - 60
        bv = base.get(key)
        with c.item("panel-%s" % short[key], "Панель «%s»: базовый сценарий %s" % (lab, vf(bv) if bv is not None else "—"), "legend",
                    {"gloss": gl("charts", "cac-ltv-solo", "elements", "panel-%s" % short[key]),
                     "meaning": "Базовый сценарий: %s." % (vf(bv) if bv is not None else "нет значения")}, highlight="g-%s" % short[key]):
            c.text(x0, c.top + 14, lab, 13, THEME["ink"], bold=True)
        vals = [max(0.0, sc[k].get(key) or 0.0) for k in names]
        vmax = max(vals + ([ref] if ref else []) + [1e-9])
        ticks, _ = nice_ticks(0, vmax, 4)
        top = ticks[-1] or 1
        sy = lambda v: y1 - v / top * (y1 - y0)
        for t in ticks:
            c.line(x0, sy(t), x1, sy(t), THEME["grid"])
            c.text(x0 - 6, sy(t) + 4, fmt(t, 0 if t >= 10 or t == 0 else 1), 11, THEME["muted"], "end")
        gw = (x1 - x0) / len(names)
        bw = min(56, gw * 0.55)
        for i, k in enumerate(names):
            gx = x0 + i * gw + gw / 2
            v = sc[k].get(key)
            vv = max(0.0, v or 0.0)
            if key == "revenue_per_hour":
                mean = "%s сценарий: %s выручки на час разработчика%s." % (
                    SCEN_RU[k], vf(v) if v is not None else "нет значения",
                    (" — ниже ставки %s/ч" % money(ref, M) if v is not None and v < ref else " — не ниже ставки %s/ч" % money(ref, M)) if ref else "")
            else:
                mean = "%s сценарий: %s разработчика на одного активированного пользователя (часов на привлечение %s)." % (
                    SCEN_RU[k], vf(v) if v is not None else "нет значения", fmt(sc[k].get("growth_hours"), 0))
            mets = [{"label": lab, "value": vf(v) if v is not None else "—", "tag": "допущение"}]
            for mk, ml, mf in (("dev_hours", "Часы разработки", lambda x: fmt(x, 0) + " ч"), ("paying_new_total", "Новых платящих", lambda x: fmt(x, 1)),
                               ("net_revenue_total", "Чистая выручка", lambda x: money(x, M))):
                if isinstance(sc[k].get(mk), (int, float)):
                    mets.append({"label": ml, "value": mf(sc[k][mk]), "tag": "допущение"})
            with c.item("%s-%s" % (short[key], k), "%s, %s сценарий: %s" % (lab, SCEN_RU[k].lower(), vf(v) if v is not None else "нет значения"), "bar",
                        {"title": "%s — %s сценарий" % (lab, SCEN_RU[k].lower()), "gloss": gl("charts", "cac-ltv-solo", "elements", "panel-%s" % short[key]),
                         "section": 8, "meaning": mean, "metrics": mets},
                        groups=["g-%s" % short[key], "g-scen-%s" % k]):
                c.rect(gx - bw / 2, sy(vv), bw, y1 - sy(vv), scol(k), rx=2)
                c.text(gx, sy(vv) - 6, vf(v) if v is not None else "—", 11, THEME["ink"], "middle", True)
                c.text(gx, y1 + 16, SCEN_RU[k], 11, THEME["ink"], "middle")
        if ref:
            with c.item("rate", "Ставка часа разработчика: %s/ч" % money(ref, M), "line",
                        {"gloss": gl("charts", "cac-ltv-solo", "elements", "rate"), "section": 8,
                         "meaning": "Ставка часа — %s (%s); выручка на час выше неё означает, что время окупается лучше альтернативы." % (
                             money(ref, M), ((solo.get("params") or {}).get("hourly_rate") or {}).get("label") or "допущение"),
                         "metrics": [{"label": "Ставка часа", "value": money(ref, M), "tag": ((solo.get("params") or {}).get("hourly_rate") or {}).get("label") or "допущение"}]}):
                c.hit([(x0, sy(ref)), (x1, sy(ref))])
                c.line(x0, sy(ref), x1, sy(ref), THEME["bad"], 1.4, "6 4")
                c.text(x1, sy(ref) - 6, "ставка %s/ч" % money(ref, M), 11, THEME["bad"], "end", True)
    return c.finish(ph), title, cap


def ch_payback_solo(M):
    solo = M.get("solo") or {}
    sc = solo.get("scenarios") or {}
    names = [k for k in SCEN_RU if k in sc and sc[k].get("monthly")]
    if not names:
        return None
    base = sc.get("base", sc[names[0]])
    ok = [SCEN_RU[k].lower() for k in names if sc[k].get("time_breakeven_month")]
    nb = base.get("paying_new_total") or 0
    head = ("%s: %s %s, %s выручки против %s ч разработчика (≈ %s)" % (
        "базовый", fmt(nb, 1 if nb < 10 else 0), plural(round(nb), ("новый платящий", "новых платящих", "новых платящих")),
        money(base.get("net_revenue_total") or 0, M), fmt(base.get("dev_hours"), 0), money(base.get("time_cost") or 0, M)))
    title = (("Безубыточность по времени достигается в сценариях: %s; " % ", ".join(ok)) if ok else
             "Безубыточность по времени за %s мес. не достигается; " % M.get("horizon_months", "—")) + head
    rate = ((solo.get("params") or {}).get("hourly_rate") or {}).get("value")
    cap = ("Сплошная — накопленная валовая выручка, пунктир — стоимость времени разработчика (ёмкость × ставка %s/ч) плюс "
           "постоянные затраты. Денежная «безубыточность» при нулевом бюджете вводит в заблуждение — сравнивается время." % money(rate or 0, M))
    c = Chart(960, title, cap, "Источник: data/model.json (solo.scenarios.*.monthly, %s) [допущение]" % M.get("currency", ""))
    REG.variant = "payback-solo"
    W = 960
    ph = 380
    x0, x1, y0, y1 = PAD + 80, W - PAD - 150, c.top + 8, c.top + ph - 70
    n = len(sc[names[0]]["monthly"])
    vmax = max(max(max(m["cum_margin"], m["cum_time_cost"]) for m in sc[k]["monthly"]) for k in names) or 1
    ticks, _ = nice_ticks(0, vmax, 5)
    top = ticks[-1] or 1
    sx = lambda i: x0 + (i / max(1, n - 1)) * (x1 - x0)
    sy = lambda v: y1 - v / top * (y1 - y0)
    for t in ticks:
        c.line(x0, sy(t), x1, sy(t), THEME["grid"])
        c.text(x0 - 6, sy(t) + 4, fmt(t), 11, THEME["muted"], "end")
    step = max(1, int(math.ceil(n / 12.0)))
    for i in range(0, n, step):
        c.text(sx(i), y1 + 16, str(i + 1), 11, THEME["muted"], "middle")
    ends = []
    drawn = []
    for k in names:   # стоимость времени почти одинакова во всех сценариях (та же ёмкость) — без повторов
        mo = sc[k]["monthly"]
        tc = [m["cum_time_cost"] for m in mo]
        if any(max(abs(a - b) for a, b in zip(tc, d)) <= 0.01 * (max(tc) or 1) for d in drawn):
            continue
        drawn.append(tc)
        tid = "timecost-%d" % len(drawn)
        tpts = [(sx(i), sy(v)) for i, v in enumerate(tc)]
        with c.item(tid, "Стоимость времени разработчика: %s за %d мес." % (money(tc[-1], M), n), "line",
                    {"title": "Стоимость времени разработчика", "gloss": gl("terms", "time_cost"), "section": 8,
                     "meaning": "К концу горизонта накопленная стоимость часов разработчика и постоянных затрат — %s (%s сценарий%s)." % (
                         money(tc[-1], M), SCEN_RU[k].lower(), "; в остальных сценариях почти так же" if len(drawn) == 1 else ""),
                     "metrics": [{"label": "Стоимость времени накопленная", "value": money(tc[-1], M), "tag": "допущение"}]},
                    groups=["g-time"]):
            c.hit(tpts)
            c.add('<polyline points="%s" fill="none" stroke="%s" stroke-width="1.8" stroke-dasharray="6 4"/>'
                  % (" ".join("%.1f,%.1f" % p for p in tpts), THEME["muted"] if len(drawn) == 1 else scol(k)))
        ends.append((sy(tc[-1]), "время: %s" % money(tc[-1], M), THEME["muted"], tid))
    for k in names:
        mo = sc[k]["monthly"]
        col = scol(k)
        tb = sc[k].get("time_breakeven_month")
        mpts = [(sx(i), sy(m["cum_margin"])) for i, m in enumerate(mo)]
        with c.item("margin-%s" % k, "%s сценарий: накопленная выручка %s за %d мес." % (SCEN_RU[k], money(mo[-1]["cum_margin"], M), n), "line",
                    {"title": "Выручка накопленная — %s сценарий" % SCEN_RU[k].lower(), "gloss": gl("terms", "time_cost"), "section": 8,
                     "summary": "Накопленная валовая выручка в сценарии «%s»." % SCEN_RU[k].lower(),
                     "meaning": "К концу горизонта — %s против стоимости времени %s; %s." % (
                         money(mo[-1]["cum_margin"], M), money(mo[-1]["cum_time_cost"], M),
                         ("безубыточность по времени с %d-го месяца" % tb) if tb else "по времени за горизонт не окупается"),
                     "metrics": [{"label": "Выручка накопленная", "value": money(mo[-1]["cum_margin"], M), "tag": "допущение"}]},
                    groups=["g-scen-%s" % k]):
            c.hit(mpts)
            c.poly(mpts, "none", col, sw=2.4, closed=False)
        if tb:
            with c.item("be-%s" % k, "%s сценарий: безубыточность по времени с %d-го месяца" % (SCEN_RU[k], tb), "point",
                        {"title": "Безубыточность по времени — %s сценарий" % SCEN_RU[k].lower(), "gloss": gl("terms", "time_cost"), "section": 8,
                         "meaning": "В %d-м месяце накопленная выручка догоняет стоимость времени разработчика." % tb,
                         "metrics": [{"label": "Месяц безубыточности по времени", "value": str(tb), "tag": "допущение"}]},
                        groups=["g-scen-%s" % k]):
                c.circle(sx(tb - 1), sy(mo[tb - 1]["cum_margin"]), 5, col, "#FFFFFF", sw=1.5)
        ends.append((sy(mo[-1]["cum_margin"]), "%s: %s" % (SCEN_RU[k].lower(), money(mo[-1]["cum_margin"], M)), col, "margin-%s" % k))
    ends.sort()
    last = -1e9
    for yy, lab, col, ref in ends:
        yy = max(yy, last + 15)
        with c.ref(ref):
            c.text(x1 + 8, yy + 4, lab, 11, col, bold=True)
        last = yy
    with c.item("axis-x", "Ось: месяц горизонта модели", "axis", {"gloss": gl("charts", "payback-solo", "elements", "axis-x")}):
        c.text((x0 + x1) / 2, y1 + 34, "Месяц", 12, THEME["ink"], "middle")
    h = legend_row(c, [("стоимость времени (пунктир)", THEME["muted"], None)] +
                   [("выручка: " + SCEN_RU[k].lower(), scol(k), None) for k in names], x0, y1 + 58, W - PAD - x0, 12,
                   els=[{"id": "legend-time", "label": "Легенда: стоимость времени разработчика (пунктир)",
                         "info": {"gloss": gl("charts", "payback-solo", "elements", "legend-time")}, "highlight": "g-time"}] +
                       [{"id": "legend-scen-%s" % k, "label": "Легенда: выручка, %s сценарий" % SCEN_RU[k].lower(),
                         "info": {"gloss": gl("scenarios", k)}, "highlight": "g-scen-%s" % k} for k in names])
    return c.finish(ph + max(0, h - 12)), title, cap


# ---------------------------------------------------------------- main
SECTIONS = {"effort-impact": "scores", "bubble": "scores", "metrics-heatmap": "scores", "radar-top10": "scores", "pareto": "scores",
            "tornado": "scores", "dist-category": "registry", "dist-evidence": "registry", "dist-horizon": "registry",
            "channel-mix": "registry", "gantt": "plan", "critical-path": "plan", "kpi-tree": "plan", "funnel": "model",
            "forecast-fan": "model", "cac-ltv": "model", "payback": "model", "keywords-volume": "market",
            "keywords-clusters": "market", "events-calendar": "market", "competitors-heatmap": "market"}


def load_inputs(out_dir):
    """Все входы графиков (отсутствующий файл → пустое значение)."""
    S = load(out_dir, "data/scores.json") or []
    S = [r for r in S if isinstance(r, dict) and all(k in r for k in ("id", "value_index", "cost_index", "risk_index", "composite"))]
    S.sort(key=lambda r: r.get("rank", 0))
    return {"S": S, "sens": load(out_dir, "data/sensitivity.json") or {}, "check": load(out_dir, "data/registry-check.json"),
            "G": load(out_dir, "data/gantt.json") or [], "M": load(out_dir, "data/model.json") or {},
            "K": load(out_dir, "data/keywords.json") or [], "E": load(out_dir, "data/events.json") or [],
            "C": load(out_dir, "data/competitors.json") or [], "P": load(out_dir, "data/proposals.json") or [],
            "CP": load(out_dir, "data/critical-path.json") or {}, "NS": load(out_dir, "data/north-star.json") or {},
            "cfg": load(out_dir, "build/run-config.json") or {}}


def plan_jobs(D, top_n=15):
    """[(ключ, раздел, причина пропуска или None, построитель)] — причина считается по данным, без построения."""
    S, sens, M, K, P, CP = D["S"], D["sens"], D["M"], D["K"], D["P"], D["CP"]
    no_s = "нет data/scores.json (фаза 6: score.py)"
    sc = M.get("scenarios") or {} if isinstance(M, dict) else {}
    no_m = "нет data/model.json (model.py)"
    valid_g = [g for g in D["G"] if isinstance(g, dict) and isinstance(g.get("start_month"), (int, float)) and isinstance(g.get("end_month"), (int, float))] if isinstance(D["G"], list) else []
    kw = [k for k in K if isinstance(k, dict) and k.get("query")] if isinstance(K, list) else []
    kw_vol = [k for k in kw if isinstance(k.get("volume"), (int, float)) and not isinstance(k.get("volume"), bool) and k["volume"] > 0]
    ev = [e for e in D["E"] if isinstance(e, dict) and parse_date(e.get("date"))] if isinstance(D["E"], list) else []
    comp = [x for x in D["C"] if isinstance(x, dict) and isinstance(x.get("features"), dict) and x["features"]] if isinstance(D["C"], list) else []
    props = [p for p in P if isinstance(p, dict)] if isinstance(P, list) else []
    tor = [e for e in (sens.get("tornado") or []) if "low_rank_shift" in e and "high_rank_shift" in e] if isinstance(sens, dict) else []

    def why(cond, reason):
        return None if cond else reason
    tornado_ok = bool(tor) and sens.get("top_n", 20) >= 2 and max(max(e["low_rank_shift"], e["high_rank_shift"]) for e in tor) > 0
    solo = bool(M.get("solo")) if isinstance(M, dict) else False
    return [
        ("effort-impact", why(S, no_s), lambda: ch_effort_impact(S, top_n)),
        ("bubble", why(S, no_s), lambda: ch_bubble(S, top_n)),
        ("metrics-heatmap", why(S, no_s), lambda: ch_heatmap(S, top_n)),
        ("radar-top10", why(S, no_s), lambda: ch_radar(S, top_n)),
        ("pareto", why(S, no_s) or why(sum(r["risk_adjusted"] for r in S) > 0, "ценность с поправкой на риск везде 0"),
         lambda: ch_pareto(S, top_n)),
        ("tornado", why(sens, "нет data/sensitivity.json (score.py)") or why(tornado_ok, "ранги не сдвигаются (мало предложений или полные ничьи)"),
         lambda: ch_tornado(sens)),
        ("dist-category", why(S, no_s), lambda: ch_dist_category(S, D["check"])),
        ("dist-evidence", why(S, no_s), lambda: ch_dist_evidence(S)),
        ("dist-horizon", why(S, no_s), lambda: ch_dist_horizon(S)),
        ("gantt", why(valid_g, "нет data/gantt.json (фаза 7; график строится сразу после её записи)"), lambda: ch_gantt(valid_g)),
        ("critical-path", why(CP, "нет data/critical-path.json (score.py)") or why(CP.get("edges"), "нет зависимостей среди топа и их предпосылок"),
         lambda: ch_critical_path(CP, S, props)),
        ("channel-mix", why(props, "нет data/proposals.json") or why(any(p.get("category") == "acquisition" for p in props),
                                                                      "в реестре нет предложений категории acquisition"),
         lambda: ch_channel_mix(props, S)),
        ("kpi-tree", why(props, "нет data/proposals.json") or why(any(isinstance(p.get("effect_kpi"), list) and p["effect_kpi"] for p in props),
                                                                   "в реестре нет effect_kpi"),
         lambda: ch_kpi_tree(props, S, D["cfg"], D["NS"])),
        ("funnel", why(sc, no_m) or why(any(sc[k].get("funnel") for k in SCEN_RU if k in sc), "в model.json нет воронки"), lambda: ch_funnel(M, S)),
        ("forecast-fan", why(sc, no_m) or why(all(k in sc and sc[k].get("monthly") for k in SCEN_RU), "нужны все три сценария с monthly"),
         lambda: ch_fan(M)),
        ("cac-ltv", why(sc, no_m) or why(solo or any(sc[k].get("ltv") is not None for k in sc), "в model.json нет LTV"), lambda: ch_cac_ltv(M)),
        ("payback", why(sc, no_m) or why(solo or any(sc[k].get("monthly") and "cum_margin" in sc[k]["monthly"][0] for k in sc),
                                         "в model.json нет накопленных сумм (cum_margin)"), lambda: ch_payback(M)),
        ("keywords-volume", why(kw, "нет data/keywords.json") or why(kw_vol, "в data/keywords.json нет объёмов — используйте keywords-clusters"),
         lambda: ch_keywords(K)),
        ("keywords-clusters", why(kw, "нет data/keywords.json"), lambda: ch_keywords_clusters(kw)),
        ("events-calendar", why(ev, "нет data/events.json с датами"), lambda: ch_events(D["E"])),
        ("competitors-heatmap", why(comp, "нет data/competitors.json с features"), lambda: ch_competitors(D["C"])),
    ]


def list_keys(out_dir):
    """Допустимые ключи и пропущенные с причиной — по данным, без построения."""
    avail, skipped = [], {}
    for key, reason, _ in plan_jobs(load_inputs(out_dir)):
        if reason:
            skipped[key] = reason
        else:
            avail.append(key)
    return {"available": avail, "skipped": skipped}


def build_all(out_dir, only=None, top_n=15, warnings=None):
    """Строит все доступные графики и их метаданные пояснений (charts/<ключ>.meta.json);
    возвращает (index, skipped {ключ: причина}, палитра). warnings — список, куда дописываются предупреждения пояснений."""
    pal_note = load_palette(out_dir)
    D = load_inputs(out_dir)
    cfg = D.get("cfg") if isinstance(D.get("cfg"), dict) else {}
    CONCEPT[0] = cfg.get("mode") == "concept"
    cdir = out_dir / "charts"
    cdir.mkdir(parents=True, exist_ok=True)
    old = load(out_dir, "charts/charts-index.json") or []
    index, skipped, snaps = [], {}, {}
    for key, reason, fn in plan_jobs(D, top_n):
        section = SECTIONS[key]
        meta_path = cdir / ("%s.meta.json" % key)
        if only and key not in only:
            prev = next((e for e in old if isinstance(e, dict) and e.get("key") == key), None)
            if prev and (cdir / ("%s.svg" % key)).exists():
                index.append(prev)
            continue
        path = cdir / ("%s.svg" % key)
        REG.reset(key)
        res = None if reason else fn()
        if not res:
            skipped[key] = reason or "недостаточно данных для графика"
            for p_ in (path, meta_path):
                if p_.exists():
                    p_.unlink()
            continue
        svg, title, cap = res
        path.write_text(svg, encoding="utf-8")
        snaps[key] = ({"els": REG.els, "variant": REG.variant}, title, cap, section)
        index.append({"key": key, "svg": "charts/%s.svg" % key, "title": title, "caption": cap, "section": section,
                      "meta": "charts/%s.meta.json" % key})
    REG.reset(None)
    # пояснения: заметки → данные → глоссарий; глубокие ссылки — по элементам всех графиков сборки
    notes = load(out_dir, chart_meta.NOTES)
    ctx = chart_meta.Context(out_dir, D, notes=notes if isinstance(notes, dict) else None)
    if notes is not None and not isinstance(notes, dict):
        ctx.warnings.append("data/chart-notes.json: ожидается объект {ключ: {id: {…}}} — заметки не применены")
    own = {}
    for e in index:
        if e["key"] in snaps:
            own[e["key"]] = set(snaps[e["key"]][0]["els"])
        else:
            pm = load(out_dir, e.get("meta") or "charts/%s.meta.json" % e["key"]) or {}
            own[e["key"]] = set((pm.get("elements") or {}).keys())
    ctx.available = own
    for nk, nv in (ctx.notes or {}).items():     # заметки к несуществующим графикам/элементам — предупредить
        if nk not in own:
            ctx.warnings.append("chart-notes: нет графика «%s» в этой сборке — заметки не применены" % nk)
        elif not isinstance(nv, dict):
            ctx.warnings.append("chart-notes: «%s» — ожидается объект {id: {…}}" % nk)
        else:
            for nid in nv:
                if nid != "_chart" and nid not in own[nk]:
                    ctx.warnings.append("chart-notes: нет элемента %s/%s — заметка не применена" % (nk, nid))
    for key, (snap, title, cap, section) in snaps.items():
        meta = chart_meta.build_meta(key, snap, ctx, own, title, cap, section)
        (cdir / ("%s.meta.json" % key)).write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for e in index:      # старые записи без meta (до 1.4) — дописать путь, если файл есть
        if "meta" not in e and (cdir / ("%s.meta.json" % e["key"])).exists():
            e["meta"] = "charts/%s.meta.json" % e["key"]
    if warnings is not None:
        warnings.extend(ctx.warnings)
    (cdir / "charts-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index, skipped, pal_note


def main(argv=None):
    ap = argparse.ArgumentParser(description="SVG-графики стратегии (stdlib) → charts/*.svg + charts-index.json.")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--only", help="ключи через запятую (остальные графики не трогаются)")
    ap.add_argument("--top", type=int, default=15, help="сколько лидеров подписывать на матрице усилие–влияние (15)")
    ap.add_argument("--list-keys", action="store_true", help="напечатать JSON допустимых ключей и пропущенных с причиной")
    ap.add_argument("--check-meta", action="store_true",
                    help="только проверить разметку и пояснения построенных графиков (код 1 при проблемах)")
    ap.add_argument("--list-generic", action="store_true",
                    help="напечатать JSON элементов с обобщённым пояснением (только глоссарий) — для брифа chart-notes")
    a = ap.parse_args(argv)
    out_dir = Path(a.out).resolve()
    if a.list_keys:
        print(json.dumps(list_keys(out_dir), ensure_ascii=False, indent=2))
        return 0
    if a.check_meta:
        return report_check(out_dir)
    if a.list_generic:
        rows = chart_meta.list_generic(out_dir)
        print(json.dumps([{"chart": k, "id": i, "title": t, "reason": r} for k, i, t, r in rows], ensure_ascii=False, indent=1))
        return 0
    only = set(a.only.split(",")) if a.only else None
    unknown = sorted((only or set()) - set(KNOWN_KEYS))
    if unknown:
        print("неизвестные ключи: %s (допустимые: %s)" % (", ".join(unknown), ", ".join(KNOWN_KEYS)))
    warns = []
    index, skipped, pal = build_all(out_dir, only, a.top, warns)
    print("Палитра: %s" % pal)
    for e in index:
        print("  %-20s %s" % (e["key"], e["title"]))
    if skipped:
        print("Пропущены: %s" % "; ".join("%s (%s)" % kv for kv in skipped.items()))
    print("Графиков: %d → %s" % (len(index), out_dir / "charts"))
    for w in warns:
        print("  предупреждение: %s" % w)
    return report_check(out_dir)


def report_check(out_dir):
    """Проверка разметки и пояснений (chart_meta.check_meta): печать итога, код 0/1."""
    probs = chart_meta.check_meta(out_dir)
    n_el = 0
    for e in load(out_dir, "charts/charts-index.json") or []:
        m = load(out_dir, (e or {}).get("meta") or "charts/%s.meta.json" % (e or {}).get("key")) if isinstance(e, dict) else None
        n_el += len((m or {}).get("elements") or {})
    if probs:
        print("Проверка пояснений графиков: %d %s" % (len(probs), plural(len(probs), ("проблема", "проблемы", "проблем"))))
        for p in probs[:60]:
            print("  ✗ %s" % p)
        return 1
    print("Проверка пояснений графиков: ок (%d %s)" % (n_el, plural(n_el, ("элемент", "элемента", "элементов"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
