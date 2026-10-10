#!/usr/bin/env python3
"""Графики стратегии в SVG на стандартной библиотеке (без matplotlib) → <OUT>/charts/<key>.svg + charts-index.json.

  charts.py <OUT> [--only key1,key2] [--top N]

Источники: data/scores.json, proposals.json, sensitivity.json, registry-check.json, gantt.json, model.json,
keywords.json, events.json, competitors.json. Каждый график пропускается, если для него нет данных.
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
from collections import Counter, OrderedDict
from datetime import date
from pathlib import Path

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
              "keywords-volume", "events-calendar", "competitors-heatmap"]


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
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
                'font-family="{f}">\n<title>{t}</title>\n<desc>{d}</desc>\n<rect x="0" y="0" width="{w}" height="{h}" fill="{bg}"/>\n{body}\n</svg>\n'
                ).format(w=self.W, h=int(math.ceil(H)), f=esc(FONT), t=esc(self.title), d=esc(self.caption or ""),
                         bg=THEME["bg"], body="\n".join(head + self.el + foot))


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


def place_labels(c, pts, labels, box, obstacles, size=11, color=None, bold=True, reserved=None):
    """Жадная раскладка подписей точек без наложений: кольца смещений вокруг точки, проверка рамки графика,
    других подписей и маркеров; при отходе от точки — тонкая выноска. Возвращает число вынужденных наложений."""
    placed, forced = list(reserved or []), 0
    x0, y0, x1, y1 = box
    obs = [(ox - orr, oy - orr, 2 * orr, 2 * orr) for ox, oy, orr in obstacles]
    dirs = [(1, -0.2), (1, 0.9), (-1, -0.2), (-1, 0.9), (0, -1.2), (0, 1.6), (1, -1.2), (-1, -1.2), (1, 1.8), (-1, 1.8)]
    h = size * 1.15
    for (px, py), lab in zip(pts, labels):
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
        if r > 7:
            ax = min(max(px, bb[0]), bb[0] + bb[2])
            ay = min(max(py, bb[1]), bb[1] + bb[3])
            c.line(px, py, ax, ay, THEME["axis"], 0.8)
        c.rect(bb[0] - 1, bb[1], bb[2] + 2, bb[3], THEME["bg"], op=0.85)
        c.text(bb[0], bb[1] + h * 0.8, lab, size, color or THEME["ink"], "start", bold)
        placed.append(bb)
    return forced


def legend_row(c, items, x, y, max_w, size=12):
    """Горизонтальная легенда с переносом; items: (label, color, shape|None). Возвращает занятую высоту."""
    cx, cy = x, y
    row_h = size * 1.7
    for lab, col, shape in items:
        w = 18 + text_w(lab, size) + 18
        if cx + w > x + max_w and cx > x:
            cx, cy = x, cy + row_h
        if shape is None:
            c.rect(cx, cy - size * 0.75, 12, 12, col, rx=2)
        else:
            c.marker(shape, cx + 6, cy - size * 0.3, 5.5, col)
        c.text(cx + 18, cy, lab, size, THEME["ink"])
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
    c.text((x0 + x1) / 2, y1 + 34, "Усилие — индекс стоимости (1 — дёшево, 5 — дорого)", 12, THEME["ink"], "middle")
    c.add('<text x="%.1f" y="%.1f" font-size="12" fill="%s" text-anchor="middle" transform="rotate(-90 %.1f %.1f)">%s</text>'
          % (PAD + 8, (y0 + y1) / 2, THEME["ink"], PAD + 8, (y0 + y1) / 2, esc("Ценность — индекс от 1 до 5")))
    top_ids = {r["id"] for r in top}
    for r in sorted(S, key=lambda r: r["id"] in top_ids):
        col, shp = cat_color(r.get("category"))
        c.marker(shp, sx(r["cost_index"]), sy(r["value_index"]), 6.5 if r["id"] in top_ids else 5, col)
    for (qx, qy, qa, qt, qc), qb in zip(quads, qboxes):
        c.rect(qb[0], qb[1], qb[2], qb[3], THEME["bg"], op=0.85, rx=3)
        c.text(qx, qy + 12, qt, 12, qc, qa, True)
    obstacles = [(sx(r["cost_index"]), sy(r["value_index"]), 7) for r in S]
    place_labels(c, [(sx(r["cost_index"]), sy(r["value_index"])) for r in top], [r["id"] for r in top],
                 (x0, y0, x1, y1), obstacles, 11, reserved=[b[:4] for b in qboxes])
    cats = [k for k in CAT_RU if any(r.get("category") == k for r in S)] + sorted({r.get("category") for r in S if r.get("category") not in CAT_RU}, key=str)
    legend_row(c, [(cat_name(k), cat_color(k)[0], cat_color(k)[1]) for k in cats], x0, y1 + 56, x1 - x0, 11)
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

    order = sorted(S, key=lambda r: -r["confidence_calc"])
    for r in order:
        rad = 4 + 14 * math.sqrt(max(0.0, min(1.0, r["confidence_calc"])))
        c.circle(sx(max(0.5, r["effort_days_mid"])), sy(r["value_index"]), rad, rcol(r["risk_index"]), "#FFFFFF", 0.55, 1)
    obstacles = [(sx(max(0.5, r["effort_days_mid"])), sy(r["value_index"]), 4) for r in S]
    place_labels(c, [(sx(max(0.5, r["effort_days_mid"])), sy(r["value_index"])) for r in top], [r["id"] for r in top],
                 (x0, y0, x1, y1), obstacles, 11)
    c.text((x0 + x1) / 2, y1 + 34, "Трудозатраты, чел.-дни (лог. шкала)", 12, THEME["ink"], "middle")
    c.add('<text x="%.1f" y="%.1f" font-size="12" fill="%s" text-anchor="middle" transform="rotate(-90 %.1f %.1f)">%s</text>'
          % (PAD + 8, (y0 + y1) / 2, THEME["ink"], PAD + 8, (y0 + y1) / 2, esc("Ценность — индекс от 1 до 5")))
    legend_row(c, [("риск < 2,2", THEME["good"], None), ("риск 2,2–3", THEME["neutral"], None), ("риск ≥ 3", THEME["bad"], None),
                   ("больше круг — выше уверенность; подписаны топ-10", THEME["bg"], None)], x0, y1 + 58, x1 - x0, 11)
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
    for j, h in enumerate(hdr):
        cx = PAD + label_w + j * cell_w + cell_w / 2
        c.lines(cx, c.top + 12, h, 11, THEME["ink"], "middle", True, 1.2)
    for r in top:
        tl = wrap("%d. %s %s" % (r["rank"], r["id"], r.get("title", "")), label_w - 10, 11)
        rh = max(24, len(tl) * 13.5 + 8)
        c.lines(PAD, y + (rh - len(tl) * 13.5) / 2 + 10.5, tl, 11, THEME["ink"], lh=1.23)
        for j, (k, _, inv, lo, hi) in enumerate(cols):
            v = r[k]
            t = (v - lo) / (hi - lo) if hi > lo else 0
            t = max(0.0, min(1.0, 1 - t if inv else t))
            fill = mix(THEME["seq_lo"], PAL[0], 0.08 + 0.92 * t)
            x = PAD + label_w + j * cell_w
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
            c.text(lx, ly + 4, lab, 10, THEME["muted"], anc)
        colr = PAL[i % len(PAL)]
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
        c.rect(x0 + i * bw + bw * 0.12, y1 - h, bw * 0.76, h, PAL[0] if i < k80 else mix(PAL[0], "#FFFFFF", 0.55))
    pts = [(x0 + (i + 0.5) * bw, y1 - cv * (y1 - y0)) for i, cv in enumerate(cum)]
    c.poly(pts, "none", PAL[1], sw=2.2, closed=False)
    for p in (0, 0.25, 0.5, 0.75, 1.0):
        c.text(x1 + 6, y1 - p * (y1 - y0) + 4, "%d %%" % (p * 100), 11, THEME["muted"])
    for k, lab in ((k50, "50 %"), (k80, "80 %")):
        px = x0 + (k - 0.5) * bw
        py = y1 - cum[k - 1] * (y1 - y0)
        c.line(px, py, px, y1, PAL[1], 1, "3 3")
        c.circle(px, py, 4, PAL[1], "#FFFFFF")
        txt = "%s — первые %d" % (lab, k)
        anc = "start" if px + text_w(txt, 11) + 8 < x1 else "end"
        c.rect(px + (6 if anc == "start" else -text_w(txt, 11, True) - 8), py - 22, text_w(txt, 11, True) + 4, 16, THEME["bg"], op=0.9)
        c.text(px + (8 if anc == "start" else -8), py - 10, txt, 11, THEME["ink"], anc, True)
    step = max(1, int(math.ceil(n / 15.0)))
    for i in range(0, n, step):
        c.text(x0 + (i + 0.5) * bw, y1 + 15, str(i + 1), 10, THEME["muted"], "middle")
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
    c.text(mid - 8, c.top + 12, "вес ×0,5", 11, THEME["muted"], "end")
    c.text(mid + 8, c.top + 12, "вес ×1,5", 11, THEME["muted"], "start")
    for e, rh in zip(t, rows_h):
        tl = wrap(pname(e["param"]), label_w - 10, 12)
        c.lines(PAD, y + (rh - len(tl) * 15) / 2 + 12, tl, 12, THEME["ink"])
        lw = e["low_rank_shift"] / mx * half
        hw = e["high_rank_shift"] / mx * half
        c.rect(mid - lw, y + 5, lw, rh - 10, PAL[0], rx=2)
        c.rect(mid, y + 5, hw, rh - 10, PAL[1], rx=2)
        c.text(mid - lw - 5, y + rh / 2 + 4, fmt(e["low_rank_shift"], 2), 11, THEME["ink"], "end")
        c.text(mid + hw + 5, y + rh / 2 + 4, fmt(e["high_rank_shift"], 2), 11, THEME["ink"], "start")
        y += rh
    c.line(mid, c.top + 18, mid, y, THEME["ink"], 1.2)
    c.text(mid, y + 22, "Средний сдвиг ранга, позиций", 12, THEME["ink"], "middle")
    return c.finish(ph), title, cap


def hbar_chart(title, cap, source, items, W=860, color=None, marks=None, value_fmt=None, colors=None, legend=None):
    """Горизонтальные столбцы: items — [(label, value)], marks — {label: требуемый минимум} (риска)."""
    c = Chart(W, title, cap, source)
    label_w = 230
    x0, x1 = PAD + label_w, W - PAD - 60
    vmax = max([v for _, v in items] + list((marks or {}).values()) + [1])
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
    for k, (lab, v, tl, rh) in enumerate(rows):
        c.lines(PAD, y + (rh - len(tl) * 15) / 2 + 12, tl, 12, THEME["ink"])
        w = v / top * (x1 - x0)
        col = (colors[k] if colors else None) or color or PAL[0]
        c.rect(x0, y + 5, w, rh - 10, col, rx=2)
        c.text(x0 + w + 6, y + rh / 2 + 4, value_fmt(v) if value_fmt else fmt(v), 12, THEME["ink"])
        if marks and lab in marks:
            mx = x0 + marks[lab] / top * (x1 - x0)
            c.line(mx, y + 2, mx, y + rh - 2, THEME["ink"], 2)
        y += rh
    extra = 0
    if marks:
        c.line(PAD, y + 34, PAD + 14, y + 34, THEME["ink"], 2)
        c.text(PAD + 20, y + 38, "чёрная риска — требуемый минимум категории", 11, THEME["muted"])
        extra = 22
    if legend:
        extra += legend_row(c, legend, PAD, y + 38 + extra, W - 2 * PAD, 12)
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
    return hbar_chart(title, cap, "Источник: data/proposals.json, data/registry-check.json", items, marks=marks or None,
                      colors=[cat_color(k)[0] for k in keys]), title, cap


def ch_dist_evidence(S):
    cnt = Counter(r.get("evidence_class") for r in S)
    ab = (cnt.get("A", 0) + cnt.get("B", 0)) / len(S)
    title = "Классы доказательств: A+B = %d %% (порог 60 %%)" % round(ab * 100)
    cap = ("Доля сильных доказательств достаточна." if ab >= 0.6 else "Доля сильных доказательств ниже порога — нужно усилить источники.")
    names = {"A": "A — первоисточник / живая функция", "B": "B — несколько независимых упоминаний", "C": "C — одно упоминание", "D": "D — логический вывод"}
    items = [(names[k], cnt.get(k, 0)) for k in "ABCD"]
    cols = [THEME["good"], PAL[5 % len(PAL)], PAL[1], THEME["bad"]]
    return hbar_chart(title, cap, "Источник: data/proposals.json", items, colors=cols), title, cap


def ch_dist_horizon(S):
    cnt = Counter(r.get("horizon") for r in S)
    keys = [k for k in HORIZON_RU] + sorted((k for k in cnt if k not in HORIZON_RU), key=str)
    items = [(HORIZON_RU.get(k, str(k)), cnt.get(k, 0)) for k in keys if cnt.get(k, 0) or k in HORIZON_RU]
    near = cnt.get("now", 0) + cnt.get("next", 0)
    title = "Горизонты: %d из %d %s — на ближайший год" % (near, len(S), plural(len(S), ("предложения", "предложений", "предложений")))
    cap = "Сейчас — 0–3 мес., дальше — 3–12 мес., позже — 1–2 года, видение — 2+ года."
    return hbar_chart(title, cap, "Источник: data/proposals.json (horizon)", items,
                      colors=[mix(PAL[0], "#FFFFFF", 0.18 * i) for i in range(len(items))]), title, cap


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
        c.rect(x0 + 12 * mw, y, (maxm - 12) * mw, body_h, THEME["panel"])
    for m in range(1, maxm + 1):
        if (m - 1) % step == 0:
            c.text(x0 + (m - 0.5) * mw, c.top + 14, str(m), 11, THEME["muted"], "middle")
        c.line(x0 + (m - 1) * mw, y, x0 + (m - 1) * mw, y + body_h, THEME["grid"], 0.8)
    pcol = {p: PAL[i % len(PAL)] for i, p in enumerate(phases)}
    for ph in phases:
        c.text(PAD, y + 15, ph or "без фазы", 12, pcol[ph], bold=True)
        y += 22
        for g, tl, rh in rows:
            if g.get("phase", "") != ph:
                continue
            c.lines(PAD + 10, y + (rh - len(tl) * 15) / 2 + 12, tl, 12, THEME["ink"])
            s, e = g["start_month"], g["end_month"]
            if g.get("type") == "milestone" or s == e and g.get("type") == "milestone":
                cx, cy = x0 + (e - 0.5) * mw, y + rh / 2
                c.poly([(cx, cy - 8), (cx + 8, cy), (cx, cy + 8), (cx - 8, cy)], pcol[ph], "#FFFFFF")
            else:
                c.rect(x0 + (s - 1) * mw + 1, y + 6, (e - s + 1) * mw - 2, rh - 12, pcol[ph], rx=3)
            y += rh
    c.text((x0 + x1) / 2, y + 22, "Месяц от старта", 12, THEME["ink"], "middle")
    return c.finish(body_h + 56), title, cap


# ---------------------------------------------------------------- модель
def ch_funnel(M):
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
            c.text(sx(t), y + total + 16, fmt(t, 0 if t >= 1 else 1), 11, THEME["muted"], "middle")
    for si, st in enumerate(stages):
        tl = wrap(st, label_w - 12, 12)
        c.lines(PAD, y + (gh - len(tl) * 15) / 2 + 12, tl, 12, THEME["ink"], bold=True)
        for k, nm in enumerate(names):
            v = sc[nm]["funnel"][si].get("value", 0) if si < len(sc[nm]["funnel"]) else 0
            yy = y + 8 + k * bh
            c.rect(x0, yy, sx(max(v, lo)) - x0, bh - 3, scol(nm), rx=2)
            c.text(sx(max(v, lo)) + 5, yy + bh - 6, fmt(v, 0 if v >= 10 else 1), 11, THEME["ink"])
        y += gh
    h = legend_row(c, [(SCEN_RU[k], scol(k), None) for k in names], x0, y + 40, x1 - x0, 12)
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
    c.poly(band, scol("base"), None, 0.16)
    c.poly([(sx(i), sy(v)) for i, v in enumerate(mo["pessimistic"])], "none", scol("pessimistic"), sw=1.4, closed=False)
    c.poly([(sx(i), sy(v)) for i, v in enumerate(mo["optimistic"])], "none", scol("optimistic"), sw=1.4, closed=False)
    c.poly([(sx(i), sy(v)) for i, v in enumerate(mo["base"])], "none", scol("base"), sw=2.6, closed=False)
    c.text((x0 + x1) / 2, y1 + 34, "Месяц", 12, THEME["ink"], "middle")
    legend_row(c, [("оптимистичный", scol("optimistic"), None), ("базовый", scol("base"), None), ("пессимистичный", scol("pessimistic"), None),
                   ("диапазон", mix(scol("base"), "#FFFFFF", 0.8), None)], x0, y1 + 58, x1 - x0, 12)
    return c.finish(ph), title, cap


def ch_cac_ltv(M):
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
    for i, k in enumerate(names):
        gx = x0 + i * gw + gw / 2
        for j, (key, lab, col) in enumerate((("cac", "CAC", PAL[1 % len(PAL)]), ("ltv", "LTV", PAL[0]))):
            v = sc[k].get(key) or 0
            bx = gx - bw - 4 + j * (bw + 8)
            c.rect(bx, sy(v), bw, y1 - sy(v), col, rx=2)
            c.text(bx + bw / 2, sy(v) - 6, fmt(v, 0), 12, THEME["ink"], "middle", True)
        lt = sc[k].get("ltv_cac")
        sub = "LTV/CAC %s · окупаемость %s мес." % (fmt(lt, 1), fmt(sc[k].get("payback_months"), 1)) if lt else "без платного привлечения"
        c.text(gx, y1 + 18, SCEN_RU[k], 12, THEME["ink"], "middle", True)
        for q, ln in enumerate(wrap(sub, gw - 10, 11)):
            c.text(gx, y1 + 34 + q * 14, ln, 11, THEME["muted"], "middle")
    legend_row(c, [("CAC — стоимость привлечения платящего", PAL[1 % len(PAL)], None), ("LTV — валовая ценность клиента", PAL[0], None)],
               x0, c.top + 14, x1 - x0, 12)
    return c.finish(ph), title, cap


def ch_payback(M):
    sc = M.get("scenarios") or {}
    names = [k for k in SCEN_RU if k in sc and sc[k].get("monthly") and "cum_margin" in sc[k]["monthly"][0]]
    if not names:
        return None
    W = 960
    be = {k: sc[k].get("breakeven_month") for k in names}
    ok = [SCEN_RU[k].lower() for k in names if be[k]]
    title = ("Безубыточность за горизонт достигается в сценариях: %s" % ", ".join(ok)) if ok else "Ни один сценарий не выходит на безубыточность за горизонт"
    cap = "Сплошная линия — накопленная валовая выручка, пунктир — накопленные затраты (постоянные + маркетинг); точка — месяц безубыточности."
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
        c.poly([(sx(i), sy(m["cum_margin"])) for i, m in enumerate(mo)], "none", col, sw=2.4, closed=False)
        pts = " ".join("%.1f,%.1f" % (sx(i), sy(m["cum_cost"])) for i, m in enumerate(mo))
        c.add('<polyline points="%s" fill="none" stroke="%s" stroke-width="1.6" stroke-dasharray="6 4"/>' % (pts, col))
        if be[k]:
            i = be[k] - 1
            c.circle(sx(i), sy(mo[i]["cum_margin"]), 5, col, "#FFFFFF", sw=1.5)
    c.text((x0 + x1) / 2, y1 + 34, "Месяц", 12, THEME["ink"], "middle")
    legend_row(c, [("%s%s" % (SCEN_RU[k], ": безубыточность с мес. %d" % be[k] if be[k] else ": не окупается"), scol(k), None)
                   for k in names], x0, y1 + 58, x1 - x0, 12)
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
    svg = hbar_chart(title, cap, "Источник: data/keywords.json; объёмы: %s" % (", ".join(srcs) or "не указан"), items, W=960,
                     colors=[ccol[k.get("cluster") or "без кластера"] for k in top],
                     legend=[(cl, ccol[cl], None) for cl in clusters])
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

    for e, tl, rh in rows:
        c.lines(PAD, y + (rh - len(tl) * 15) / 2 + 12, tl, 12, THEME["ink"])
        col = kcol[e.get("kind") or "событие"]
        ds, de = parse_date(e["date"]), parse_date(e.get("date_end"))
        cy = y + rh / 2
        if de and de > ds:
            c.rect(xpos(ds), cy - 5, max(4, xpos(de) - xpos(ds)), 10, col, rx=3)
        elif e.get("verified", True):
            c.circle(xpos(ds), cy, 6, col, "#FFFFFF")
        else:
            c.circle(xpos(ds), cy, 6, "#FFFFFF", col, sw=2)
        y += rh
    h = legend_row(c, [(k, kcol[k], None) for k in kinds], x0, y + 26, x1 - x0, 12)
    return c.finish(body + 30 + h), title, cap


def ch_competitors(C):
    rows = [x for x in C if isinstance(x, dict) and isinstance(x.get("features"), dict) and x["features"]]
    if not rows:
        return None
    feats = list(OrderedDict.fromkeys(f for x in rows for f in x["features"]))
    natural = lambda t: [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", str(t))]
    rows = sorted(rows, key=lambda x: (not x.get("self"), natural(x.get("name") or x.get("slug"))))
    W = max(760, min(1200, 300 + 96 * len(feats)))
    label_w = 230
    cw = (W - 2 * PAD - label_w) / len(feats)
    me = next((x for x in rows if x.get("self")), None)
    share = {f: sum(1 for x in rows if not x.get("self") and x["features"].get(f)) / max(1, sum(1 for x in rows if not x.get("self"))) for f in feats}
    gaps = [f for f in feats if me and not me["features"].get(f) and share[f] >= 0.5]
    title = "Функции конкурентов: %d %s × %d %s" % (len(rows), plural(len(rows), ("продукт", "продукта", "продуктов")),
                                                   len(feats), plural(len(feats), ("функция", "функции", "функций")))
    cap = ("Пробелы нашего продукта, которые есть у большинства конкурентов: %s." % ", ".join(gaps)) if gaps else (
        "У нашего продукта нет функций, которые были бы у большинства конкурентов и отсутствовали у нас." if me else "Строка нашего продукта (self) не задана.")
    c = Chart(W, title, cap, "Источник: data/competitors.json; ✓ — функция есть, пусто — нет или не найдено")
    hdr = [wrap(f, cw - 6, 11, True) for f in feats]
    hh = max(len(h) for h in hdr) * 14 + 8
    for j, h in enumerate(hdr):
        c.lines(PAD + label_w + j * cw + cw / 2, c.top + 12, h, 11, THEME["ink"], "middle", True, 1.2)
    y = c.top + hh
    for x in rows:
        tl = wrap(("★ " if x.get("self") else "") + str(x.get("name") or x.get("slug")), label_w - 10, 12)
        rh = max(26, len(tl) * 15 + 8)
        if x.get("self"):
            c.rect(PAD - 6, y, W - 2 * PAD + 12, rh, mix(PAL[1], "#FFFFFF", 0.85))
        c.lines(PAD, y + (rh - len(tl) * 15) / 2 + 12, tl, 12, THEME["ink"], bold=bool(x.get("self")))
        for j, f in enumerate(feats):
            has = bool(x["features"].get(f))
            cx = PAD + label_w + j * cw
            c.rect(cx + 2, y + 2, cw - 4, rh - 4, PAL[0] if has else THEME["panel"], rx=3)
            if has:
                c.text(cx + cw / 2, y + rh / 2 + 5, "✓", 14, "#FFFFFF", "middle", True)
        y += rh
    return c.finish(y - c.top + 4), title, cap


# ---------------------------------------------------------------- main
def build_all(out_dir, only=None, top_n=15):
    """Строит все доступные графики; возвращает (index, skipped)."""
    pal_note = load_palette(out_dir)
    S = load(out_dir, "data/scores.json") or []
    sens = load(out_dir, "data/sensitivity.json") or {}
    check = load(out_dir, "data/registry-check.json")
    G = load(out_dir, "data/gantt.json") or []
    M = load(out_dir, "data/model.json") or {}
    K = load(out_dir, "data/keywords.json") or []
    E = load(out_dir, "data/events.json") or []
    C = load(out_dir, "data/competitors.json") or []
    S = [r for r in S if isinstance(r, dict) and all(k in r for k in ("id", "value_index", "cost_index", "risk_index", "composite"))]
    S.sort(key=lambda r: r.get("rank", 0))
    jobs = [
        ("effort-impact", "scores", lambda: ch_effort_impact(S, top_n) if S else None),
        ("bubble", "scores", lambda: ch_bubble(S, top_n) if S else None),
        ("metrics-heatmap", "scores", lambda: ch_heatmap(S, top_n) if S else None),
        ("radar-top10", "scores", lambda: ch_radar(S, top_n) if S else None),
        ("pareto", "scores", lambda: ch_pareto(S, top_n) if S and sum(r["risk_adjusted"] for r in S) > 0 else None),
        ("tornado", "scores", lambda: ch_tornado(sens) if sens else None),
        ("dist-category", "registry", lambda: ch_dist_category(S, check) if S else None),
        ("dist-evidence", "registry", lambda: ch_dist_evidence(S) if S else None),
        ("dist-horizon", "registry", lambda: ch_dist_horizon(S) if S else None),
        ("gantt", "plan", lambda: ch_gantt(G) if G else None),
        ("funnel", "model", lambda: ch_funnel(M) if M else None),
        ("forecast-fan", "model", lambda: ch_fan(M) if M else None),
        ("cac-ltv", "model", lambda: ch_cac_ltv(M) if M else None),
        ("payback", "model", lambda: ch_payback(M) if M else None),
        ("keywords-volume", "market", lambda: ch_keywords(K) if K else None),
        ("events-calendar", "market", lambda: ch_events(E) if E else None),
        ("competitors-heatmap", "market", lambda: ch_competitors(C) if C else None),
    ]
    cdir = out_dir / "charts"
    cdir.mkdir(parents=True, exist_ok=True)
    old = load(out_dir, "charts/charts-index.json") or []
    index, skipped = [], []
    for key, section, fn in jobs:
        if only and key not in only:
            prev = next((e for e in old if isinstance(e, dict) and e.get("key") == key), None)
            if prev and (cdir / ("%s.svg" % key)).exists():
                index.append(prev)
            continue
        res = fn()
        path = cdir / ("%s.svg" % key)
        if not res:
            skipped.append(key)
            if path.exists():
                path.unlink()
            continue
        svg, title, cap = res
        path.write_text(svg, encoding="utf-8")
        index.append({"key": key, "svg": "charts/%s.svg" % key, "title": title, "caption": cap, "section": section})
    (cdir / "charts-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index, skipped, pal_note


def main(argv=None):
    ap = argparse.ArgumentParser(description="SVG-графики стратегии (stdlib) → charts/*.svg + charts-index.json.")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--only", help="ключи через запятую (остальные графики не трогаются)")
    ap.add_argument("--top", type=int, default=15, help="сколько лидеров подписывать на матрице усилие–влияние (15)")
    a = ap.parse_args(argv)
    out_dir = Path(a.out).resolve()
    only = set(a.only.split(",")) if a.only else None
    index, skipped, pal = build_all(out_dir, only, a.top)
    print("Палитра: %s" % pal)
    for e in index:
        print("  %-20s %s" % (e["key"], e["title"]))
    if skipped:
        print("Пропущены (нет данных): %s" % ", ".join(skipped))
    print("Графиков: %d → %s" % (len(index), out_dir / "charts"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
