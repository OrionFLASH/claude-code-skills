#!/usr/bin/env python3
"""Сборка интерактивной веб-страницы стратегии: одна самодостаточная офлайн-страница <OUT>/deliverables/index.html.

Читает папку прогона <OUT> по references/data-contract.md; каждый раздел пропускается, если для него нет данных:
research/strategy.md, data/*.json (реестр, оценки, Гант, Kanban, схемы, конкуренты, модель, источники…),
charts/charts-index.json, mockups/ (tokens.css, current/, concepts/), design-refs/, competitors/shots/, build/run-config.json.

CSS, JS, данные и картинки встроены в страницу: каждая картинка — один раз (карта IMG, data URI, ссылка по ключу),
JSON — в <script type="application/json">, CSP без внешних источников, ни одного внешнего запроса.
Весь текст из данных экранируется: HTML и скрипты в данных — это данные, не код.

  build_html.py <OUT> [--out <file>] [--title "…"]

В конце печатает размер страницы, топ-10 самых тяжёлых вложений и предупреждения. Только стандартная библиотека.
"""
import argparse
import base64
import colorsys
import hashlib
import html
import json
import math
import os
import re
import struct
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

# ---------------------------------------------------------------- подписи
CAT_LABELS = {"product": "Продукт", "acquisition": "Привлечение", "conversion": "Конверсия", "retention": "Удержание",
              "monetization": "Монетизация", "analytics": "Аналитика", "partnerships": "Партнёрства",
              "localization": "Локализация", "new_lines": "Новые направления", "platform": "Платформа"}
HORIZON_LABELS = {"now": "Сейчас · 0–3 мес.", "next": "Далее · 3–12 мес.", "later": "Позже · 1–2 года",
                  "vision": "Видение · 2+ года"}
HORIZON_SHORT = {"now": "сейчас", "next": "далее", "later": "позже", "vision": "видение"}
QUADRANT_LABELS = {"quick_win": "Быстрая победа", "big_bet": "Крупная ставка", "filler": "Заполнитель",
                   "money_pit": "Ловушка стоимости"}
LABEL_LABELS = {"important": "важное", "effective": "эффективное", "expensive": "дорогое", "risky": "рискованное",
                "fast": "быстрое", "slow": "долгое", "strategic": "стратегическое", "tempting_weak": "заманчивое, но слабое"}
KANO_LABELS = {"must": "обязательное", "linear": "линейное", "delight": "восхищение", "indifferent": "безразличное"}
MOSCOW_LABELS = {"must": "Must", "should": "Should", "could": "Could", "wont": "Won't"}
EVIDENCE_LABELS = {"competitor": "конкурент", "community": "сообщество", "issue": "issue", "docs": "документация",
                   "repo": "репозиторий", "research": "исследование", "analytics": "аналитика", "own_app": "наше приложение"}
RISK_LABELS = {"legal": "право", "ip": "IP", "platform": "платформа", "privacy": "приватность", "tech": "техника",
               "reputation": "репутация"}
SCORE_LABELS = {"value": "Ценность", "cost": "Стоимость", "risk": "Риск", "confidence": "Уверенность", "reach": "Охват",
                "impact": "Влияние", "acquisition": "Привлечение", "activation": "Активация", "conversion": "Конверсия",
                "retention": "Удержание", "revenue": "Выручка", "virality": "Виральность", "seo": "SEO",
                "trust": "Доверие", "moat": "Защищённость", "fit": "Соответствие", "demand": "Спрос",
                "season": "Сезонность", "testability": "Проверяемость", "spread": "Разброс оценок"}
SUBSCALES = ["reach", "impact", "acquisition", "activation", "conversion", "retention", "revenue", "virality", "seo",
             "trust", "moat", "fit", "demand", "season"]
METRIC_LABELS = {"rank": "Ранг", "composite": "Итоговый балл (composite)", "rice": "RICE", "ice": "ICE", "wsjf": "WSJF",
                 "value_per_effort": "Ценность / усилие", "risk_adjusted": "С поправкой на риск",
                 "confidence_calc": "Уверенность (расчёт)", "value_index": "Индекс ценности",
                 "cost_index": "Индекс стоимости", "risk_index": "Индекс риска", "effort_days_mid": "Дни (середина)",
                 "cost_of_delay": "Стоимость задержки", "reach_units": "Охват (единицы)",
                 "n_rice": "RICE (норм.)", "n_ice": "ICE (норм.)", "n_wsjf": "WSJF (норм.)",
                 "n_risk_adjusted": "Риск-скорр. (норм.)"}
COMP_TYPE_LABELS = {"direct": "прямой", "indirect": "косвенный", "substitute": "замена"}
SCENARIO_LABELS = {"pessimistic": "Пессимистичный", "base": "Базовый", "optimistic": "Оптимистичный"}
CHART_SECTION_LABELS = {"scores": "Оценки и приоритеты", "registry": "Реестр", "market": "Рынок",
                        "competitors": "Конкуренты", "model": "Модель и сценарии", "roadmap": "План",
                        "gantt": "План", "research": "Исследование", "product": "Продукт", "repo": "Репозиторий",
                        "community": "Сообщества", "keywords": "Поисковый спрос", "events": "События",
                        "plan": "План и дорожная карта", "flows": "Схемы", "design": "Дизайн"}
MONTHS_RU = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
# порядок «по возрастанию по умолчанию» для метрик, где меньше — лучше
ASC_METRICS = {"rank", "s_cost", "s_risk", "effort_min", "effort_max", "effort_avg", "cost_min", "cost_max", "ttfr",
               "risk_sum", "risk_max", "cost_index", "risk_index", "effort_days_mid"}
PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#B279A2", "#E45756", "#72B7B2", "#9D755D", "#EECA3B"]

PID_RE = re.compile(r"(?<![\w-])(P\d{3})(?![\w-])")
PID_FULL = re.compile(r"^P\d{3}$")


# ---------------------------------------------------------------- мелкие помощники
def esc(s):
    """Экранирование текста и атрибутов (& < > " ')."""
    return html.escape("" if s is None else str(s), quote=True)


def num(v):
    """Число или None (строки «3», «2,5» тоже)."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    if isinstance(v, str):
        try:
            x = float(v.strip().replace(",", ".").replace("\u202f", "").replace(" ", ""))
            return x if math.isfinite(x) else None
        except ValueError:
            return None
    return None


def to_int(v):
    x = num(v)
    return int(round(x)) if x is not None else None


def fmt_num(v):
    """Число по-русски: пробелы в тысячах, запятая в дробях."""
    x = num(v)
    if x is None:
        return "" if v is None else str(v)
    if x.is_integer():
        return "{:,}".format(int(x)).replace(",", "\u202f")
    s = "{:,.2f}".format(x) if abs(x) < 1000 else "{:,.0f}".format(x)
    return s.replace(",", "\u202f").replace(".", ",")


def money(v):
    if not isinstance(v, dict):
        return text_of(v)
    lo, hi, cur = v.get("min"), v.get("max"), v.get("currency") or ""
    if lo is None and hi is None:
        s = ""
    elif lo == hi or hi is None:
        s = fmt_num(lo)
    elif lo is None:
        s = "до " + fmt_num(hi)
    else:
        s = fmt_num(lo) + "–" + fmt_num(hi)
    s = (s + " " + str(cur)).strip()
    if v.get("note"):
        s += " (" + str(v["note"]) + ")"
    return s


def text_of(v):
    """Любое значение из данных → короткий текст для показа."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "да" if v else "нет"
    if isinstance(v, (int, float)):
        return fmt_num(v)
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "; ".join(text_of(x) for x in v)
    if isinstance(v, dict):
        if "min" in v and "max" in v:
            return money(v)
        if "value" in v:
            lab = v.get("label") or v.get("note")
            return text_of(v["value"]) + (" [" + str(lab) + "]" if lab else "")
        return "; ".join(str(k) + ": " + text_of(x) for k, x in v.items())
    return str(v)


def as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        return [x.strip() for x in re.split(r"[;,\n]+", v) if x.strip()]
    return [v]


def str_list(v):
    return [text_of(x) for x in as_list(v) if text_of(x) != ""]


def parse_range(v):
    """effort_days: [3, 8] | 5 | "3-8" | {"min":…, "max":…} → (min, max)."""
    if isinstance(v, dict):
        lo, hi = num(v.get("min")), num(v.get("max"))
    elif isinstance(v, (list, tuple)):
        xs = [num(x) for x in v if num(x) is not None]
        lo, hi = (min(xs), max(xs)) if xs else (None, None)
    elif isinstance(v, str):
        xs = [num(x) for x in re.findall(r"\d+(?:[.,]\d+)?", v)]
        xs = [x for x in xs if x is not None]
        lo, hi = (min(xs), max(xs)) if xs else (None, None)
    else:
        lo = hi = num(v)
    if lo is None:
        lo = hi
    if hi is None:
        hi = lo
    return lo, hi


def clean_json(o):
    """NaN/Infinity → null (иначе JSON.parse упадёт)."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {str(k): clean_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean_json(v) for v in o]
    return o


def json_script(id_, obj):
    """JSON в <script type="application/json">: < > & → \\u003c… (в том числе </script>)."""
    s = json.dumps(clean_json(obj), ensure_ascii=False, separators=(",", ":"))
    s = s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    s = s.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return '<script type="application/json" id="' + id_ + '">' + s + "</script>"


def safe_url(u):
    """Разрешены http(s), mailto, якоря и относительные пути; javascript:, data:, file: и прочие схемы — нет."""
    u = ("" if u is None else str(u)).strip()
    if not u:
        return ""
    low = re.sub(r"[\x00-\x20]", "", u).lower()
    if low.startswith(("http://", "https://", "mailto:", "#")):
        return u
    if re.match(r"^[a-z][a-z0-9+.-]*:", low) or low.startswith("//"):
        return ""
    return u


def ext_link(url, text=None, cls=""):
    """Внешняя ссылка (новая вкладка) или просто текст, если схема не разрешена."""
    s = safe_url(url)
    t = esc(text if text not in (None, "") else url)
    if not s:
        return t
    c = ' class="' + cls + '"' if cls else ""
    return '<a' + c + ' href="' + esc(s) + '" target="_blank" rel="noopener noreferrer">' + t + "</a>"


def plural(n, forms):
    """1 элемент, 2 элемента, 5 элементов."""
    n = abs(int(n))
    i = 0 if n % 10 == 1 and n % 100 != 11 else 1 if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 2
    return "%d %s" % (n, forms[i])


EL_FORMS = ("элемент", "элемента", "элементов")


def slug(s):
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(s)).strip("-")
    return s or "x"


def plain(html_text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", html_text or ""))).strip()


# ---------------------------------------------------------------- картинки
def sniff_mime(data, suffix):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    head = data[:4096].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if (suffix.lower() == ".svg" or head.startswith(b"<?xml") or head.startswith(b"<svg")) and b"<svg" in data[:65536].lower():
        return "image/svg+xml"
    return None


def _svg_len(v):
    m = re.match(r"^\s*([\d.]+)\s*(px)?\s*$", v or "")
    return float(m.group(1)) if m else None


def svg_size(text):
    m = re.search(r"<svg\b[^>]*>", text, re.I | re.S)
    if not m:
        return None, None
    tag = m.group(0)

    def attr(name):
        mm = re.search(r"\s" + name + r"\s*=\s*([\"'])(.*?)\1", tag, re.I | re.S)
        return mm.group(2) if mm else None
    w, h = _svg_len(attr("width")), _svg_len(attr("height"))
    vb = attr("viewBox")
    if (w is None or h is None) and vb:
        parts = [num(x) for x in re.split(r"[\s,]+", vb.strip())]
        if len(parts) == 4 and parts[2] and parts[3]:
            if w is None and h is None:
                w, h = parts[2], parts[3]
            elif w is None:
                w = h * parts[2] / parts[3]
            else:
                h = w * parts[3] / parts[2]
    return (round(w) if w else None), (round(h) if h else None)


def image_size(data, mime):
    """Размер картинки без PIL: PNG/GIF/JPEG/WebP/SVG."""
    try:
        if mime == "image/png" and len(data) >= 24:
            w, h = struct.unpack(">II", data[16:24])
            return w, h
        if mime == "image/gif":
            return struct.unpack("<HH", data[6:10])
        if mime == "image/jpeg":
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker == 0xFF:
                    i += 1
                    continue
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                seg = struct.unpack(">H", data[i + 2:i + 4])[0]
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return w, h
                i += 2 + seg
        if mime == "image/webp":
            chunk = data[12:16]
            if chunk == b"VP8X":
                return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
            if chunk == b"VP8L":
                bits = int.from_bytes(data[21:25], "little")
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            if chunk == b"VP8 ":
                w, h = struct.unpack("<HH", data[26:30])
                return w & 0x3FFF, h & 0x3FFF
        if mime == "image/svg+xml":
            return svg_size(data[:65536].decode("utf-8", "replace"))
    except (struct.error, IndexError, ValueError):
        pass
    return None, None


class Images:
    """Каждая картинка встраивается один раз: ключ → data URI; повторные ссылки на тот же файл получают тот же ключ."""

    def __init__(self, base, warn):
        self.base = base.resolve()
        self.warn = warn
        self.map = {}
        self.meta = {}
        self.by_path = {}

    def resolve(self, rel):
        """Путь внутри <OUT> или None (URL, data:, выход за пределы папки прогона — отказ)."""
        if not rel or not isinstance(rel, str):
            return None
        rel = rel.strip()
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", rel) and not re.match(r"^[a-zA-Z]:[\\/]", rel):
            return None
        p = Path(rel)
        p = p if p.is_absolute() else self.base / p
        try:
            rp = p.resolve()
            rp.relative_to(self.base)
        except (ValueError, OSError):
            self.warn("путь вне папки прогона, не встраивается: " + rel)
            return None
        return rp

    def add(self, rel, hint):
        p = self.resolve(rel) if not isinstance(rel, Path) else self.resolve(str(rel))
        if p is None or not p.is_file():
            return None
        if p in self.by_path:
            return self.by_path[p]
        try:
            data = p.read_bytes()
        except OSError as e:
            self.warn("не прочитать " + str(rel) + ": " + str(e))
            return None
        mime = sniff_mime(data, p.suffix)
        if not mime:
            self.warn("не картинка (PNG/JPEG/GIF/WebP/SVG), пропущено: " + self.rel(p))
            return None
        key = slug(hint)
        k, n = key, 2
        while k in self.map:
            k, n = key + "-" + str(n), n + 1
        uri = "data:" + mime + ";base64," + base64.b64encode(data).decode("ascii")
        w, h = image_size(data, mime)
        self.map[k] = uri
        self.meta[k] = {"src": self.rel(p), "bytes": len(uri), "w": w, "h": h, "mime": mime}
        self.by_path[p] = k
        if len(data) > 8 * 1024 * 1024:
            self.warn("тяжёлая картинка %s (%.1f МБ) — лучше WebP/меньший размер" % (self.rel(p), len(data) / 1048576))
        return k

    def rel(self, p):
        try:
            return p.relative_to(self.base).as_posix()
        except ValueError:
            return str(p)


# ---------------------------------------------------------------- SVG для встраивания в DOM (блок-схемы)
def scope_css(css, scope, prefix, ids):
    """Изолировать <style> из SVG: селекторы → «#scope …», классы → prefix-класс, id → scope-id; @font-face/@import — убрать."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"@(charset|import|namespace)[^;]*;", "", css, flags=re.I)

    def sel_fix(sel):
        out = []
        for s in sel.split(","):
            s = s.strip()
            if not s:
                continue
            s = re.sub(r"\.(-?[_a-zA-Z][\w-]*)", lambda m: "." + prefix + m.group(1), s)
            s = re.sub(r"#(-?[_a-zA-Z][\w-]*)", lambda m: "#" + scope + "-" + m.group(1) if m.group(1) in ids else m.group(0), s)
            s = re.sub(r"^(:root|html|body)\b", "", s).strip()
            out.append("#" + scope + (" " + s if s else ""))
        return ", ".join(out)

    def rules(text):
        res, pos, n = [], 0, len(text)
        while pos < n:
            j = text.find("{", pos)
            if j == -1:
                break
            sel = text[pos:j].strip()
            depth, k = 1, j + 1
            while k < n and depth:
                if text[k] == "{":
                    depth += 1
                elif text[k] == "}":
                    depth -= 1
                k += 1
            body = text[j + 1:k - 1]
            low = sel.lower()
            if low.startswith(("@media", "@supports")):
                res.append(sel + "{" + rules(body) + "}")
            elif low.startswith("@keyframes"):
                res.append(sel + "{" + body + "}")
            elif low.startswith("@"):
                pass
            elif sel:
                res.append(sel_fix(sel) + "{" + body + "}")
            pos = k
        return "".join(res)
    return rules(css)


def sanitize_svg(src, scope, known_nodes=None):
    """SVG из файла → безопасный фрагмент для DOM: без скриптов, обработчиков, внешних ссылок; id/классы изолированы."""
    m = re.search(r"<svg\b.*</svg\s*>", src, re.S | re.I)
    if not m:
        return None
    s = m.group(0)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", lambda mm: mm.group(1).replace("<", "&lt;"), s, flags=re.S)
    for tag in ("script", "foreignObject", "iframe", "object", "embed", "audio", "video", "canvas", "handler",
                "listener", "set", "animate"):
        s = re.sub(r"<" + tag + r"\b.*?</" + tag + r"\s*>", "", s, flags=re.S | re.I)
        s = re.sub(r"<" + tag + r"\b[^>]*>", "", s, flags=re.I)
    s = re.sub(r"\s+on[a-zA-Z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", s)

    def href_fix(mm):
        v = mm.group(3).strip()
        if v.startswith("#") or re.match(r"data:image/(png|jpe?g|gif|webp);base64,", v, re.I):
            return mm.group(0)
        return ""
    s = re.sub(r"\s((?:xlink:)?href)\s*=\s*([\"'])(.*?)\2", href_fix, s, flags=re.I | re.S)
    s = re.sub(r"@import[^;]*;?", "", s, flags=re.I)
    s = re.sub(r"url\(\s*(['\"]?)(?!#)(?!data:image/)[^)]*\)", "none", s, flags=re.I)
    ids = set(re.findall(r"\sid\s*=\s*\"([^\"]+)\"", s)) | set(re.findall(r"\sid\s*=\s*'([^']+)'", s))
    s = re.sub(r"(<style\b[^>]*>)(.*?)(</style\s*>)",
               lambda mm: mm.group(1) + scope_css(mm.group(2), scope, "f-", ids) + mm.group(3), s, flags=re.S | re.I)
    s = re.sub(r"(\sclass\s*=\s*([\"']))(.*?)(\2)",
               lambda mm: mm.group(1) + " ".join("f-" + c for c in mm.group(3).split()) + mm.group(4), s, flags=re.S)
    if ids:
        s = re.sub(r"(\sid\s*=\s*([\"']))(.*?)(\2)", lambda mm: mm.group(1) + scope + "-" + mm.group(3) + mm.group(4), s)
        s = re.sub(r"url\(\s*(['\"]?)#([^)'\"]+)\1\s*\)",
                   lambda mm: "url(#" + scope + "-" + mm.group(2) + ")" if mm.group(2) in ids else mm.group(0), s)
        s = re.sub(r"(\s(?:xlink:)?href\s*=\s*([\"']))#(.*?)(\2)",
                   lambda mm: mm.group(1) + "#" + scope + "-" + mm.group(3) + mm.group(4) if mm.group(3) in ids else mm.group(0), s)
    # корень: без фиксированных width/height (масштаб по viewBox)
    root = re.match(r"<svg\b[^>]*>", s, re.S).group(0)
    w, h = svg_size(root)
    new = re.sub(r"\s(width|height)\s*=\s*([\"']).*?\2", "", root, flags=re.S)
    if w:
        cap = "max-width:%dpx" % max(480, int(w * 1.4))
        if re.search(r"\sstyle\s*=\s*\"", new):
            new = re.sub(r"(\sstyle\s*=\s*\")([^\"]*)\"", lambda mm: mm.group(1) + mm.group(2).rstrip("; ") + ";" + cap + '"', new, count=1)
        else:
            new = new[:-1] + ' style="' + cap + '">'
    if not re.search(r"\sviewBox\s*=", new) and w and h:
        new = new[:-1] + ' viewBox="0 0 %d %d">' % (w, h)
    new = re.sub(r"(\sclass\s*=\s*\")", r'\1flow-svg ', new, count=1) if re.search(r"\sclass\s*=\s*\"", new) \
        else new[:-1] + ' class="flow-svg">'
    if new.endswith("/>"):
        new = new[:-2] + ">"
    s = new + s[len(root):]

    def mark(mm):
        tag_open, attrs, close = mm.group(1), mm.group(2), mm.group(4)
        node_id = html.unescape(mm.group(3))
        if known_nodes is not None and node_id not in known_nodes:
            return mm.group(0)
        if re.search(r"\sclass\s*=\s*\"", attrs):
            attrs = re.sub(r"(\sclass\s*=\s*\")", r"\1fnode ", attrs, count=1)
        else:
            attrs += ' class="fnode"'
        if "tabindex" not in attrs:
            attrs += ' tabindex="0" role="button"'
        return tag_open + attrs + close
    s = re.sub(r"(<[a-zA-Z][\w:-]*)(\s(?:[^>]*?\s)?data-node\s*=\s*\"([^\"]+)\"[^>]*?)(/?>)", mark, s)
    return s


# ---------------------------------------------------------------- тема
def parse_color(v):
    v = (v or "").strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{3,8})", v)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            return tuple(int(c * 2, 16) for c in h[:3])
        if len(h) in (6, 8):
            return tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))
        return None
    m = re.fullmatch(r"rgba?\(\s*([\d.]+)(%?)[\s,]+([\d.]+)(%?)[\s,]+([\d.]+)(%?)(?:\s*[,/]\s*[\d.]+%?)?\s*\)", v)
    if m:
        out = []
        for val, pct in ((m.group(1), m.group(2)), (m.group(3), m.group(4)), (m.group(5), m.group(6))):
            x = float(val) * (2.55 if pct else 1)
            out.append(max(0, min(255, int(round(x)))))
        return tuple(out)
    m = re.fullmatch(r"hsla?\(\s*([\d.]+)(?:deg)?[\s,]+([\d.]+)%[\s,]+([\d.]+)%(?:\s*[,/]\s*[\d.]+%?)?\s*\)", v)
    if m:
        r, g, b = colorsys.hls_to_rgb(float(m.group(1)) / 360 % 1, float(m.group(3)) / 100, float(m.group(2)) / 100)
        return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))
    return {"white": (255, 255, 255), "black": (0, 0, 0)}.get(v)


def luminance(c):
    def ch(x):
        x /= 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def hexc(c):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, x))) for x in c)


def mix(a, b, t):
    return tuple(int(round(a[k] * (1 - t) + b[k] * t)) for k in range(3))


def fit_contrast(c, bg, target=4.5):
    """Сдвинуть светлоту цвета, пока контраст с фоном не станет ≥ target."""
    if contrast(c, bg) >= target:
        return c
    h, l, s = colorsys.rgb_to_hls(*(x / 255.0 for x in c))
    darker = luminance(bg) > 0.35
    for step in range(1, 41):
        l2 = max(0.0, min(1.0, l - step * 0.025 if darker else l + step * 0.025))
        c2 = tuple(int(round(x * 255)) for x in colorsys.hls_to_rgb(h, l2, s))
        if contrast(c2, bg) >= target:
            return c2
    return (0, 0, 0) if darker else (255, 255, 255)


ROLE_KEYS = {
    "accent": ["accent", "primary", "brand", "color-primary", "color-accent", "color-brand", "brand-primary", "link",
               "color-link", "gold", "highlight", "main"],
    "bg": ["bg", "background", "color-bg", "bg-color", "color-background", "page-bg", "bg-page", "surface-0", "base"],
    "surface": ["surface", "panel", "card", "bg-2", "surface-1", "color-surface", "bg-elevated", "bg-card", "bg-panel"],
    "text": ["text", "fg", "foreground", "color-text", "text-color", "ink", "text-primary", "color-fg", "on-bg"],
    "muted": ["muted", "text-muted", "text-2", "color-muted", "text-secondary", "fg-muted", "text-70", "text-soft"],
    "border": ["border", "line", "divider", "color-border", "stroke", "border-color"],
    "font": ["font", "font-family", "font-sans", "font-body", "ff", "family", "font-base", "font-ui"],
    "radius": ["radius", "border-radius", "radius-md", "radius-base", "rounded", "radius-card"],
}
NEUTRAL = {
    "light": {"bg": "#f6f7f9", "surface": "#ffffff", "surface-2": "#eef0f3", "text": "#1d2127", "muted": "#59606b",
              "border": "#d9dde3", "accent": "#2f5bd3"},
    "dark": {"bg": "#111316", "surface": "#191c20", "surface-2": "#23272c", "text": "#e7e9ec", "muted": "#a2a9b3",
             "border": "#30353c", "accent": "#7ea2ff"},
}
FONT_STACK = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'


def parse_tokens(css):
    """Пользовательские свойства из tokens.css: (обычные, тёмные). Тёмные — из @media (prefers-color-scheme: dark) и
    селекторов со словом dark. Никакие правила и url() из файла в страницу не попадают."""
    css = re.sub(r"/\*.*?\*/", "", css or "", flags=re.S)
    base, dark = {}, {}

    def collect(body, target):
        for name, val in re.findall(r"--([\w-]+)\s*:\s*([^;{}]+)", body):
            target[name.lower()] = val.strip()

    def walk(text, in_dark):
        pos, n = 0, len(text)
        while pos < n:
            j = text.find("{", pos)
            if j == -1:
                break
            sel = text[pos:j].strip().split(";")[-1].strip().lower()
            depth, k = 1, j + 1
            while k < n and depth:
                if text[k] == "{":
                    depth += 1
                elif text[k] == "}":
                    depth -= 1
                k += 1
            body = text[j + 1:k - 1]
            is_dark = in_dark or "dark" in sel
            if sel.startswith("@media") or sel.startswith("@supports"):
                walk(body, is_dark)
            elif not sel.startswith("@"):
                collect(body, dark if is_dark else base)
            pos = k
    walk(css, False)

    def resolve(d, fallback):
        out = {}
        for k, v in d.items():
            val, guard = v, 0
            while "var(" in val and guard < 8:
                val = re.sub(r"var\(\s*--([\w-]+)\s*(?:,\s*([^()]*))?\)",
                             lambda m: d.get(m.group(1).lower(), fallback.get(m.group(1).lower(), (m.group(2) or "").strip())), val)
                guard += 1
            out[k] = val
        return out
    base_r = resolve(base, {})
    return base_r, resolve(dark, base_r)


def pick(tokens, role, want_color=True):
    for k in ROLE_KEYS[role]:
        v = tokens.get(k)
        if v is None:
            continue
        if want_color:
            c = parse_color(v)
            if c:
                return c
        else:
            return v
    if want_color and role == "accent":
        for k, v in tokens.items():
            if any(w in k for w in ("accent", "primary", "brand")) and not any(w in k for w in ("text", "on-", "bg", "soft")):
                c = parse_color(v)
                if c:
                    return c
    return None


def theme_vars(base_tokens, dark_tokens):
    """CSS-переменные --ps-* для светлой и тёмной темы с учётом токенов продукта (контраст текста ≥ 4,5:1)."""
    modes = {m: {k: parse_color(v) for k, v in NEUTRAL[m].items()} for m in ("light", "dark")}
    accent = pick(base_tokens, "accent")
    if accent:
        modes["light"]["accent"] = accent
        modes["dark"]["accent"] = pick(dark_tokens, "accent") or accent
    for tokens, forced in ((base_tokens, None), (dark_tokens, "dark")):
        bg, text = pick(tokens, "bg"), pick(tokens, "text")
        if not bg or not text or contrast(bg, text) < 4.5:
            continue
        mode = forced or ("dark" if luminance(bg) < 0.2 else "light")
        md = modes[mode]
        md["bg"], md["text"] = bg, text
        surf = pick(tokens, "surface")
        md["surface"] = surf if surf and contrast(surf, text) >= 4.5 else (mix(bg, (255, 255, 255), 0.6) if mode == "light" else mix(bg, (255, 255, 255), 0.05))
        md["surface-2"] = mix(md["surface"], text, 0.06)
        brd = pick(tokens, "border")
        md["border"] = brd if brd else mix(md["surface"], text, 0.16)
        mut = pick(tokens, "muted")
        md["muted"] = mut if mut and contrast(mut, md["surface-2"]) >= 4.5 else fit_contrast(mix(text, md["surface"], 0.38), md["surface-2"])
    font = pick(base_tokens, "font", want_color=False)
    font = re.sub(r"url\([^)]*\)|[;{}<>\\]", "", font or "").strip()
    font = (font + ", " + FONT_STACK) if font and "sans-serif" not in font and "serif" not in font else (font or FONT_STACK)
    radius = pick(base_tokens, "radius", want_color=False) or ""
    radius = radius if re.fullmatch(r"\d+(\.\d+)?(px|rem|em)", radius.strip()) else "10px"
    out = {}
    for m, md in modes.items():
        acc = md["accent"]
        link = fit_contrast(acc, md["surface"])
        link = fit_contrast(link, md["bg"])
        on_acc = (255, 255, 255) if contrast(acc, (255, 255, 255)) >= contrast(acc, (17, 17, 17)) else (17, 17, 17)
        out[m] = {
            "--ps-bg": hexc(md["bg"]), "--ps-surface": hexc(md["surface"]), "--ps-surface-2": hexc(md["surface-2"]),
            "--ps-text": hexc(md["text"]), "--ps-muted": hexc(md["muted"]), "--ps-border": hexc(md["border"]),
            "--ps-accent": hexc(acc), "--ps-link": hexc(link), "--ps-accent-text": hexc(link), "--ps-on-accent": hexc(on_acc),
            "--ps-accent-soft": "rgba(%d,%d,%d,%s)" % (acc[0], acc[1], acc[2], ".13" if m == "light" else ".22"),
            "--ps-font": font, "--ps-radius": radius.strip(),
        }
    return out


def theme_css(tokens_text):
    base, dark = parse_tokens(tokens_text) if tokens_text else ({}, {})
    v = theme_vars(base, dark)

    def block(d):
        return ";".join(k + ":" + val for k, val in d.items())
    return (":root{" + block(v["light"]) + ";color-scheme:light}"
            "@media (prefers-color-scheme: dark){:root:not([data-theme=\"light\"]){" + block(v["dark"]) + ";color-scheme:dark}}"
            ":root[data-theme=\"dark\"]{" + block(v["dark"]) + ";color-scheme:dark}"
            "@media print{:root,:root[data-theme=\"dark\"],:root:not([data-theme=\"light\"]){" + block(v["light"]) + ";color-scheme:light}}")


# ---------------------------------------------------------------- Markdown (stdlib)
EMBED_RE = re.compile(r"!\[\[(chart|mockup|ref|flow):([^\]\s]+)\]\]")
EMBED_LINE_RE = re.compile(r"^\s*!\[\[(chart|mockup|ref|flow):([^\]\s]+)\]\]\s*$")
FENCE_RE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})\s*([^`\s]*)[^`]*$")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
HR_RE = re.compile(r"^\s{0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
QUOTE_RE = re.compile(r"^\s{0,3}>[ ]?(.*)$")
LIST_RE = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])(?:[ \t]+(.*))?$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(?:\|\s*:?-{1,}:?\s*)*\|?\s*$")
IMAGE_LINE_RE = re.compile(r"^\s*!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)\s*$")
URL_PART = r"((?:[^()\s]|\([^()\s]*\))+)"


def _indent(line):
    return len(line) - len(line.lstrip(" "))


class Markdown:
    """Мини-конвертер Markdown → HTML: заголовки, абзацы, списки (вложенные, нумерованные, задачи), таблицы, цитаты,
    код (строчный и блоки), жирный/курсив/зачёркнутый, ссылки и автоссылки, линия. Сырой HTML экранируется.
    Вставки ![[chart:key]] / ![[mockup:key]] / ![[ref:NN-slug]] / ![[flow:key]] отдаются в embed(kind, key, inline)."""

    def __init__(self, embed=None, image=None, link_fix=None, min_heading=1):
        self.embed = embed
        self.image = image
        self.link_fix = link_fix
        self.min_heading = min_heading

    def render(self, text):
        if not text:
            return ""
        text = str(text).replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").replace("\x01", "").replace("\x02", "")
        text = text.expandtabs(4)
        return "\n".join(h for _, h in self._blocks(text.split("\n")))

    # --- блоки
    def _starts_block(self, lines, i):
        line = lines[i]
        return bool(FENCE_RE.match(line) or EMBED_LINE_RE.match(line) or HEADING_RE.match(line) or HR_RE.match(line)
                    or QUOTE_RE.match(line) or LIST_RE.match(line) or self._is_table(lines, i) or IMAGE_LINE_RE.match(line))

    @staticmethod
    def _is_table(lines, i):
        return ("|" in lines[i] and i + 1 < len(lines) and "|" in lines[i + 1] and "-" in lines[i + 1]
                and TABLE_SEP_RE.match(lines[i + 1]) is not None)

    def _blocks(self, lines):
        out, i, n = [], 0, len(lines)
        while i < n:
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            m = FENCE_RE.match(line)
            if m:
                fence, lang, body = m.group(2), m.group(3), []
                close = re.compile(r"^\s{0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$")
                i += 1
                while i < n and not close.match(lines[i]):
                    body.append(lines[i])
                    i += 1
                i += 1
                cls = ' class="lang-' + esc(slug(lang)) + '"' if lang else ""
                out.append(("pre", "<pre><code" + cls + ">" + esc("\n".join(body)) + "</code></pre>"))
                continue
            m = EMBED_LINE_RE.match(line)
            if m:
                out.append(("embed", self._embed(m.group(1), m.group(2), False)))
                i += 1
                continue
            m = HEADING_RE.match(line)
            if m:
                lvl = min(6, max(len(m.group(1)), self.min_heading))
                out.append(("h", "<h%d>%s</h%d>" % (lvl, self.inline(m.group(2) or ""), lvl)))
                i += 1
                continue
            if HR_RE.match(line):
                out.append(("hr", "<hr>"))
                i += 1
                continue
            if QUOTE_RE.match(line):
                buf = []
                while i < n and lines[i].strip():
                    mq = QUOTE_RE.match(lines[i])
                    if mq:
                        buf.append(mq.group(1))
                    elif buf and not self._starts_block(lines, i):
                        buf.append(lines[i])
                    else:
                        break
                    i += 1
                out.append(("quote", "<blockquote>" + "\n".join(h for _, h in self._blocks(buf)) + "</blockquote>"))
                continue
            if self._is_table(lines, i):
                h, i = self._table(lines, i)
                out.append(("table", h))
                continue
            if LIST_RE.match(line):
                h, i = self._list(lines, i)
                out.append(("list", h))
                continue
            m = IMAGE_LINE_RE.match(line)
            if m:
                out.append(("img", self._image_block(m.group(1), m.group(2))))
                i += 1
                continue
            buf = [line]
            i += 1
            while i < n and lines[i].strip() and not self._starts_block(lines, i):
                buf.append(lines[i])
                i += 1
            out.append(("p", "<p>" + self._para(buf) + "</p>"))
        return out

    def _para(self, buf):
        parts = []
        for k, ln in enumerate(buf):
            hard = (ln.endswith("  ") or ln.rstrip().endswith("\\")) and k < len(buf) - 1
            ln = ln.strip()
            if ln.endswith("\\") and hard:
                ln = ln[:-1]
            parts.append(ln + ("\x01" if hard else ""))
        return self.inline("\n".join(parts)).replace("\x01\n", "<br>\n").replace("\x01", "")

    def _split_row(self, line):
        s = line.strip()
        codes = []

        def keep(m):
            codes.append(m.group(0))
            return "\x02%d\x02" % (len(codes) - 1)
        s = re.sub(r"(`+)(.+?)\1", keep, s)
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|") and not s.endswith("\\|"):
            s = s[:-1]
        cells = re.split(r"(?<!\\)\|", s)
        return [re.sub(r"\x02(\d+)\x02", lambda m: codes[int(m.group(1))], c).replace("\\|", "|").strip() for c in cells]

    def _table(self, lines, i):
        head, seps = self._split_row(lines[i]), self._split_row(lines[i + 1])
        aligns = []
        for s in seps:
            s = s.strip()
            aligns.append("c" if s.startswith(":") and s.endswith(":") else "r" if s.endswith(":") else "")
        ncol, rows = len(head), []
        i += 2
        while i < len(lines) and lines[i].strip() and "|" in lines[i] and not FENCE_RE.match(lines[i]):
            rows.append(self._split_row(lines[i]))
            i += 1

        def cell(tag, txt, k):
            al = aligns[k] if k < len(aligns) else ""
            return "<" + tag + (' class="al-' + al + '"' if al else "") + ">" + self.inline(txt) + "</" + tag + ">"
        thead = "".join(cell("th", head[k], k) for k in range(ncol))
        body = "".join("<tr>" + "".join(cell("td", r[k] if k < len(r) else "", k) for k in range(ncol)) + "</tr>" for r in rows)
        return '<div class="tbl"><table><thead><tr>' + thead + "</tr></thead><tbody>" + body + "</tbody></table></div>", i

    def _list(self, lines, i):
        n = len(lines)
        m = LIST_RE.match(lines[i])
        base = len(m.group(1))
        ordered = m.group(2)[0].isdigit()
        start = int(m.group(2)[:-1]) if ordered else 1
        items, cur, off, loose = [], None, base + 2, False
        while i < n:
            line = lines[i]
            if not line.strip():
                j = i + 1
                while j < n and not lines[j].strip():
                    j += 1
                if j >= n:
                    i = j
                    break
                nxt = lines[j]
                mi = LIST_RE.match(nxt)
                sib = mi and _indent(nxt) <= base + 1 and not HR_RE.match(nxt) and mi.group(2)[0].isdigit() == ordered
                if _indent(nxt) >= base + 2 or sib:
                    if cur is not None:
                        cur.append("")
                    loose = True
                    i = j
                    continue
                break
            ind = _indent(line)
            mi = LIST_RE.match(line)
            if mi and ind <= base + 1 and not HR_RE.match(line):
                if mi.group(2)[0].isdigit() != ordered or ind < base:
                    break
                rest = line[len(mi.group(1)) + len(mi.group(2)):]
                sp = len(rest) - len(rest.lstrip(" "))
                sp = sp if 1 <= sp <= 4 else 1
                off = ind + len(mi.group(2)) + sp
                cur = [mi.group(3) or ""]
                items.append(cur)
                i += 1
                continue
            if cur is not None and ind >= base + 2:
                cur.append(line[min(ind, off):])
                i += 1
                continue
            if cur is not None and lines[i - 1].strip() and not self._starts_block(lines, i):
                cur.append(line.strip())
                i += 1
                continue
            break
        lis = []
        for it in items:
            task = ""
            if it and re.match(r"^\[( |x|X)\]\s+", it[0]):
                task = "☑ " if it[0][1] in "xX" else "☐ "
                it = [it[0][4:].lstrip()] + it[1:]
            blocks = self._blocks(it)
            if blocks and blocks[0][0] == "p" and not loose:
                blocks[0] = ("p", blocks[0][1][3:-4])
            inner = "\n".join(h for _, h in blocks)
            lis.append("<li" + (' class="task"' if task else "") + ">" + esc(task) + inner + "</li>")
        tag = "ol" if ordered else "ul"
        st = ' start="%d"' % start if ordered and start != 1 else ""
        return "<" + tag + st + ">" + "".join(lis) + "</" + tag + ">", i

    # --- вставки и картинки
    def _embed(self, kind, key, inline):
        if self.embed:
            return self.embed(kind, key, inline)
        return esc("![[" + kind + ":" + key + "]]")

    def _image_block(self, alt, url):
        if self.image:
            h = self.image(alt, url, False)
            if h:
                return h
        return "<p>" + self._image_link(alt, url) + "</p>"

    def _image_link(self, alt, url):
        s = safe_url(url)
        label = "[изображение: " + (alt or url) + "]"
        if s and s.startswith(("http://", "https://")):
            return ext_link(s, label)
        return '<span class="muted">' + esc(label) + "</span>"

    # --- строчная разметка
    def inline(self, text):
        if not text:
            return ""
        store = []

        def put(h):
            store.append(h)
            return "\x00%d\x00" % (len(store) - 1)
        text = re.sub(r"(`+)(.+?)\1", lambda m: put("<code>" + esc(m.group(2).strip()) + "</code>"), text)
        text = EMBED_RE.sub(lambda m: put(self._embed(m.group(1), m.group(2), True)), text)
        text = esc(text)
        text = re.sub(r"&lt;br\s*/?&gt;", lambda m: put("<br>"), text, flags=re.I)
        text = re.sub(r"&lt;((?:https?://|mailto:)[^\s]*?)&gt;", lambda m: put(self._a(m.group(1), m.group(1))), text)
        text = re.sub(r"!\[([^\]]*)\]\(" + URL_PART + r"(?:\s+&quot;.*?&quot;)?\)",
                      lambda m: put(self._inline_image(m.group(1), m.group(2))), text)
        text = re.sub(r"\[((?:[^\[\]]|\[[^\[\]]*\])+)\]\(" + URL_PART + r"(?:\s+&quot;(.*?)&quot;)?\)",
                      lambda m: put(self._a(m.group(2), None, inner=self._emph(m.group(1)), title=m.group(3))), text)

        def bare(m):
            url, tail = m.group(1), ""
            cut = [k for k in (url.find(s) for s in ("&gt;", "&lt;", "&quot;", "&#x27;")) if k != -1]
            if cut:
                k = min(cut)
                url, tail = url[:k], url[k:]
            while url and (url[-1] in ".,;:!?»]" or (url[-1] == ")" and url.count("(") < url.count(")"))):
                tail = url[-1] + tail
                url = url[:-1]
            return (put(self._a(url, url)) + tail) if len(url) > 8 else m.group(0)
        text = re.sub(r"(?<![\w/=])(https?://[^\s<>\x00]+)", bare, text)
        text = self._emph(text)
        for _ in range(6):
            if "\x00" not in text:
                break
            text = re.sub(r"\x00(\d+)\x00", lambda m: store[int(m.group(1))], text)
        return text

    @staticmethod
    def _emph(t):
        t = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<!\*)\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?!\*)", r"<em>\1</em>", t)
        t = re.sub(r"(?<!\w)_(?=[^\s_])(.+?)(?<=[^\s_])_(?!\w)", r"<em>\1</em>", t)
        t = re.sub(r"~~(?=\S)(.+?)(?<=\S)~~", r"<del>\1</del>", t)
        return t

    def _a(self, url_esc, text_esc, inner=None, title=None):
        raw = html.unescape(url_esc)
        s = safe_url(raw)
        if s and self.link_fix:
            s = self.link_fix(s)
        label = inner if inner is not None else text_esc
        if not s:
            return label
        ext = s.startswith(("http://", "https://", "mailto:"))
        attrs = ' href="' + esc(s) + '"'
        if ext:
            attrs += ' target="_blank" rel="noopener noreferrer"'
        if title:
            attrs += ' title="' + esc(html.unescape(title)) + '"'
        return "<a" + attrs + ">" + label + "</a>"

    def _inline_image(self, alt_esc, url_esc):
        alt, url = html.unescape(alt_esc), html.unescape(url_esc)
        if self.image:
            h = self.image(alt, url, True)
            if h:
                return h
        return self._image_link(alt, url)


def strip_h1(text):
    """Убрать первый заголовок «# …» (у раздела страницы свой заголовок)."""
    return re.sub(r"^\s*#\s+[^\n]*\n?", "", text or "", count=1)


# ---------------------------------------------------------------- ссылки на предложения
LINKIFY_SKIP = {"a", "script", "style", "svg", "textarea", "title", "select", "option", "button"}


def linkify(fragment, titles):
    """P\\d{3} в текстовых узлах (не в атрибутах, не внутри <a>/<button>/<svg>…) → ссылка на карточку предложения.
    titles: {id: title} — ссылаются только существующие в реестре id."""
    if not fragment or not titles or "P" not in fragment:
        return fragment
    out, depth = [], 0
    for part in re.split(r"(<[^>]*>)", fragment):
        if part.startswith("<"):
            m = re.match(r"<(/?)([a-zA-Z][\w-]*)", part)
            if m and m.group(2).lower() in LINKIFY_SKIP and not part.endswith("/>"):
                depth = max(0, depth + (-1 if m.group(1) else 1))
            out.append(part)
        elif depth or "P" not in part:
            out.append(part)
        else:
            out.append(PID_RE.sub(lambda mm: pid_link(mm.group(1), titles) if mm.group(1) in titles else mm.group(0), part))
    return "".join(out)


def pid_link(pid, titles):
    t = titles.get(pid, "")
    return ('<a class="pid" href="#p=' + pid + '" data-pid="' + pid + '" title="' + esc(pid + (" — " + t if t else "")) + '">'
            + pid + "</a>")


# ---------------------------------------------------------------- сборщик
class Builder:
    def __init__(self, out, out_file, title=None):
        self.out = out.resolve()
        self.out_file = out_file
        self.warnings = []
        self.img = Images(self.out, self.warn)
        self.cfg = self.json("build/run-config.json", dict) or {}
        self.author = self.cfg.get("author") if isinstance(self.cfg.get("author"), dict) else {}
        created = str(self.cfg.get("created") or "")
        self.date = created if re.match(r"^\d{4}-\d{2}-\d{2}$", created) else date.today().isoformat()
        self.title_arg = title
        self.nav = []          # (id, label, group)
        self.sections = []     # html
        self.figs = 0
        self.load()

    # --- ввод
    def warn(self, msg):
        if msg not in self.warnings:
            self.warnings.append(msg)

    def json(self, rel, kind=None):
        p = self.out / rel
        if not p.is_file():
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as e:
            self.warn(rel + ": не читается как JSON (" + str(e)[:80] + ") — раздел пропущен")
            return None
        if kind is not None and not isinstance(d, kind):
            self.warn(rel + ": ожидался " + ("список" if kind is list else "объект") + " — пропущен")
            return None
        return d

    def text(self, rel):
        p = self.out / rel
        if not p.is_file():
            return None
        try:
            return p.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return None

    def dicts(self, rel):
        d = self.json(rel, list) or []
        bad = sum(1 for x in d if not isinstance(x, dict))
        if bad:
            self.warn("%s: %d записей не объекты — пропущены" % (rel, bad))
        return [x for x in d if isinstance(x, dict)]

    def load(self):
        props, seen = [], set()
        for p in self.dicts("data/proposals.json"):
            pid = str(p.get("id") or "").strip()
            if not pid:
                self.warn("data/proposals.json: запись без id — пропущена")
                continue
            if pid in seen:
                self.warn("data/proposals.json: повтор id " + pid + " — оставлен первый")
                continue
            seen.add(pid)
            p = dict(p)
            p["id"] = pid
            props.append(p)
        self.P = props
        self.titles = {p["id"]: str(p.get("title") or "") for p in props if PID_FULL.match(p["id"])}
        self.S = {}
        for s in self.dicts("data/scores.json"):
            sid = str(s.get("id") or "")
            if sid:
                self.S[sid] = s
        extra = [k for k in self.S if k not in seen]
        if extra and props:
            self.warn("data/scores.json: %d id нет в реестре (%s…)" % (len(extra), ", ".join(extra[:3])))
        self.sens = self.json("data/sensitivity.json", dict)
        self.weights = self.json("data/weights.json", dict)
        jev = self.json("data/typesafe-jev.json", dict) or {}
        self.jev = jev
        self.jev_items = jev.get("items") if isinstance(jev.get("items"), dict) else {}
        self.model = self.json("data/model.json", dict)
        self.gantt = self.dicts("data/gantt.json")
        kb = self.json("data/kanban.json", dict) or {}
        self.kanban_cols = [c for c in as_list(kb.get("columns")) if isinstance(c, (dict, str))]
        self.kanban_cards = [c for c in as_list(kb.get("cards")) if isinstance(c, dict)]
        self.flows = self.dicts("data/flows.json")
        self.mockups = self.dicts("data/mockups-index.json")
        self.comp = self.dicts("data/competitors.json")
        self.communities = self.dicts("data/communities.json")
        self.keywords = self.dicts("data/keywords.json")
        self.events = self.dicts("data/events.json")
        self.sources = self.dicts("data/sources.json")
        self.strategy = self.text("research/strategy.md")
        self.questions = self.text("research/questions-owner.md")
        self.tokens = self.text("mockups/tokens.css")
        self.load_charts()
        self.load_refs()
        self.load_mockups()
        self.load_flows()

    def load_charts(self):
        idx = self.json("charts/charts-index.json", list)
        entries = []
        if idx is None and (self.out / "charts").is_dir():
            files = sorted(p for p in (self.out / "charts").iterdir() if p.suffix.lower() in (".svg", ".png", ".jpg", ".jpeg", ".webp"))
            if files:
                self.warn("charts/charts-index.json нет — графики взяты из charts/*.svg|png по именам файлов")
            idx = [{"key": p.stem, "svg": "charts/" + p.name, "title": p.stem.replace("-", " ").replace("_", " "), "caption": "",
                    "section": ""} for p in files]
        for c in idx or []:
            if not isinstance(c, dict) or not c.get("key"):
                continue
            path = c.get("svg") or c.get("png") or c.get("file")
            k = self.img.add(path, "c-" + str(c["key"])) if path else None
            if not k:
                self.warn("график %s: нет файла %s" % (c.get("key"), path))
            entries.append({"key": str(c["key"]), "img": k, "title": text_of(c.get("title")) or str(c["key"]),
                            "caption": text_of(c.get("caption")), "section": str(c.get("section") or "")})
        self.charts = entries
        self.charts_by_key = {c["key"]: c for c in entries}

    def load_refs(self):
        self.refs = {}
        d = self.out / "design-refs"
        if not d.is_dir():
            self.refs_readme = None
            return
        self.refs_readme = self.text("design-refs/README.md")
        for jf in sorted(d.glob("*.json")):
            try:
                r = json.loads(jf.read_text(encoding="utf-8-sig"))
            except (ValueError, OSError) as e:
                self.warn("design-refs/" + jf.name + ": не JSON (" + str(e)[:60] + ")")
                continue
            if not isinstance(r, dict):
                continue
            stem = jf.stem
            png = r.get("png") or ("design-refs/" + stem + ".png")
            key = self.img.add(png, "r-" + stem)
            if not key and (d / (stem + ".png")).is_file():
                key = self.img.add("design-refs/" + stem + ".png", "r-" + stem)
            r["stem"] = stem
            r["img"] = key
            r["md"] = self.text("design-refs/" + stem + ".md") or ""
            self.refs[stem] = r

    def load_mockups(self):
        self.mock = {}
        for m in self.mockups:
            key = str(m.get("key") or Path(str(m.get("html") or m.get("png") or "")).stem or "")
            if not key:
                continue
            m = dict(m)
            m["key"] = key
            m["img"] = self.img.add(m.get("png"), "m-" + key) if m.get("png") else None
            self.mock[key] = m
        # картинки референсов без своего PNG → PNG макета того же HTML
        for stem, r in self.refs.items():
            if r.get("img"):
                continue
            f = str(r.get("file") or "")
            for m in self.mock.values():
                if f and (str(m.get("html") or "") == f or Path(f).stem == m["key"]) and m.get("img"):
                    r["img"] = m["img"]
                    r["img_from_mockup"] = True
                    break

    # --- ссылки и пути
    def rel_link(self, rel_to_out):
        """Относительная ссылка от страницы на файл внутри <OUT> (для открытия HTML-макетов рядом)."""
        try:
            target = (self.out / rel_to_out).resolve()
            target.relative_to(self.out)
        except (ValueError, OSError):
            return ""
        r = os.path.relpath(str(target), str(self.out_file.parent.resolve()))
        return quote(Path(r).as_posix(), safe="/._-~")

    def md_link_fix(self, base_rel):
        def fix(u):
            if u.startswith(("http://", "https://", "mailto:", "#", "/")):
                return u
            path, _, frag = u.partition("#")
            if not path:
                return u
            link = self.rel_link((Path(base_rel) / path).as_posix())
            return (link + ("#" + frag if frag else "")) if link else u
        return fix

    def md(self, base_rel="research", min_heading=3):
        return Markdown(embed=self.embed, image=self.md_image(base_rel), link_fix=self.md_link_fix(base_rel),
                        min_heading=min_heading)

    def md_image(self, base_rel):
        def image(alt, url, inline):
            if safe_url(url).startswith(("http://", "https://")) or not safe_url(url):
                return None
            path = url.split("#")[0]
            key = self.img.add((Path(base_rel) / path).as_posix(), "o-" + Path(path).stem) or self.img.add(path, "o-" + Path(path).stem)
            if not key:
                return None
            if inline:
                return '<a class="emb" href="#lb=' + esc(key) + '">[' + esc(alt or "изображение") + "]</a>"
            return self.fig(key, esc(alt), alt or Path(path).name, "other")
        return image

    def links(self, text):
        return linkify(text, self.titles)

    # --- фигуры
    def fig(self, key, caption_html, cap_text, group, cls="", ref="", extra=""):
        meta = self.img.meta.get(key, {})
        w, h = meta.get("w"), meta.get("h")
        size = (' width="%d" height="%d"' % (w, h)) if w and h else ""
        self.figs += 1
        return ('<figure class="lb ' + cls + '" data-key="' + esc(key) + '" data-group="' + esc(group) + '" data-ref="' + esc(ref)
                + '" data-cap="' + esc(cap_text) + '" tabindex="0" role="button" aria-label="Увеличить: ' + esc(cap_text) + '">'
                + '<img data-img="' + esc(key) + '" alt="' + esc(cap_text) + '"' + size + ' loading="lazy" decoding="async">'
                + "<figcaption>" + caption_html + ' <span class="zoom">⤢ увеличить</span>' + extra + "</figcaption></figure>")

    def is_mobile_img(self, key, hint=""):
        meta = self.img.meta.get(key or "", {})
        if "390" in hint or "mobile" in hint.lower():
            return True
        w, h = meta.get("w"), meta.get("h")
        return bool(w and h and w <= 600 and h > w * 1.3)

    def chips(self, pids):
        out = []
        for p in str_list(pids):
            out.append(pid_link(p, self.titles) if p in self.titles else '<span class="tag">' + esc(p) + "</span>")
        return " ".join(out)

    # --- вставки из strategy.md
    def embed(self, kind, key, inline):
        if kind == "chart":
            c = self.charts_by_key.get(key)
            if c and c.get("img"):
                if inline:
                    return '<a class="emb" href="#lb=' + esc(c["img"]) + '">график «' + esc(c["title"]) + "»</a>"
                return self.chart_fig(c)
            self.warn("research/strategy.md: ![[chart:%s]] — нет графика в charts/charts-index.json" % key)
            return self.missing("график «" + key + "» ещё не построен (charts/charts-index.json)", inline)
        if kind == "mockup":
            m = self.mock.get(key)
            if m:
                return self.mock_fig(m, inline=inline)
            self.warn("research/strategy.md: ![[mockup:%s]] — нет в data/mockups-index.json" % key)
            return self.missing("макет «" + key + "» не найден (data/mockups-index.json)", inline)
        if kind == "flow":
            fl = self.flow_by_key.get(key)
            if fl:
                if inline:
                    return '<a class="emb" href="#flow-' + esc(slug(key)) + '">схема «' + esc(fl["title"]) + "»</a>"
                return self.flow_block(fl, embedded=True)
            self.warn("research/strategy.md: ![[flow:%s]] — нет схемы в data/flows.json" % key)
            return self.missing("схема «" + key + "» не найдена (data/flows.json)", inline)
        if kind == "ref":
            r = self.refs.get(key)
            if r:
                if inline or not r.get("img"):
                    return '<a class="emb" href="#ref-' + esc(key) + '">референс «' + esc(text_of(r.get("title")) or key) + "»</a>"
                return self.ref_fig(r, with_link=True)
            self.warn("research/strategy.md: ![[ref:%s]] — нет design-refs/%s.json" % (key, key))
            return self.missing("референс «" + key + "» не найден (design-refs/)", inline)
        return esc(key)

    @staticmethod
    def missing(text, inline):
        if inline:
            return '<span class="missing">[' + esc(text) + "]</span>"
        return '<p class="missing">' + esc(text) + "</p>"

    def chart_fig(self, c):
        cap = "<b>" + esc(c["title"]) + "</b>" + (" — " + esc(c["caption"]) if c.get("caption") else "")
        return self.fig(c["img"], self.links(cap), c["title"] + (" — " + c["caption"] if c.get("caption") else ""), "charts", "chart")

    def ref_for_mock(self, m):
        """Референс того же макета: design-refs/*.json с file == html макета (или тем же ключом)."""
        for stem, r in self.refs.items():
            f = str(r.get("file") or "")
            if f and (f == str(m.get("html") or "") or Path(f).stem == m["key"]):
                return stem, r
        return "", None

    def mock_ref(self, m):
        """Зоны референса показываются поверх PNG макета, если это та же картинка или те же пропорции."""
        stem, r = self.ref_for_mock(m)
        if not r or not m.get("img"):
            return ""
        if r.get("img") == m.get("img"):
            return stem
        a, b = self.img.meta.get(r.get("img") or "", {}), self.img.meta.get(m["img"], {})
        if a.get("w") and a.get("h") and b.get("w") and b.get("h") and abs(a["w"] / a["h"] - b["w"] / b["h"]) < 0.01:
            return stem
        return ""

    def mock_fig(self, m, inline=False, group="mockups"):
        title = text_of(m.get("title")) or m["key"]
        concept = str(m.get("kind") or "concept") != "current"
        badge = '<span class="badge-concept">Концепт, не существующая функция</span>' if concept else '<span class="tag">факт</span>'
        pr = self.chips(m.get("proposals"))
        html_rel = self.rel_link(str(m.get("html"))) if m.get("html") else ""
        open_html = ' · <a href="' + esc(html_rel) + '" target="_blank" rel="noopener">HTML-макет</a>' if html_rel else ""
        if inline:
            if m.get("img"):
                return '<a class="emb" href="#lb=' + esc(m["img"]) + '">макет «' + esc(title) + "»</a>"
            return '<span class="emb">макет «' + esc(title) + "»</span>"
        cap = "<b>" + esc(title) + "</b> " + badge + (" · " + pr if pr else "") + (" · " + esc(m.get("viewport")) if m.get("viewport") else "")
        if not m.get("img"):
            return ('<div class="ph mock-ph" id="mock-' + esc(slug(m["key"])) + '"><div class="ph-t">Нет PNG макета</div>'
                    + cap + open_html + "</div>")
        mob = "mobile" if self.is_mobile_img(m["img"], str(m.get("viewport") or "")) else ""
        return self.fig(m["img"], cap, title, group, mob, self.mock_ref(m), extra=open_html)

    def ref_fig(self, r, with_link=False):
        title = text_of(r.get("title")) or r["stem"]
        n = len([h for h in as_list(r.get("hotspots")) if isinstance(h, dict)])
        cap = "<b>" + esc(title) + "</b>" + (" · " + plural(n, EL_FORMS) if n else "")
        link = ' · <a href="#ref-' + esc(r["stem"]) + '">карточка референса →</a>' if with_link else ""
        mob = "mobile" if (str(r.get("kind")) == "mobile" or self.is_mobile_img(r["img"])) else ""
        return self.fig(r["img"], cap, title, "mockups", mob, r["stem"], extra=link)

    # --- разделы
    def add(self, sid, label, body, group=""):
        if body:
            self.sections.append(body)
            self.nav.append((sid, label, group))

    def section(self, sid, title, inner, cls=""):
        return ('<section id="' + sid + '"' + (' class="' + cls + '"' if cls else "") + "><h2>" + title + "</h2>" + inner + "</section>")

    def page_title(self):
        if self.title_arg:
            return self.title_arg
        if self.strategy:
            m = re.search(r"^\s{0,3}#\s+(.+?)\s*#*\s*$", self.strategy, re.M)
            if m:
                return m.group(1).strip()
        name = (self.cfg.get("product") or {}).get("name") if isinstance(self.cfg.get("product"), dict) else None
        return ("Стратегия развития " + str(name)) if name else "Стратегия развития продукта"

    def author_line(self):
        a = self.author or {}
        name, nick = str(a.get("name") or "").strip(), str(a.get("nick") or "").strip()
        who = (name + (" (" + nick + ")" if nick and nick != name else "")) if name else nick
        cp = str(a.get("copyright") or "").strip()
        if not cp and who:
            cp = "© " + self.date[:4] + " " + who
        return who, cp

    def build_all(self):
        self.rows = self.build_rows()
        self.sec_top()
        self.sec_strategy()
        self.sec_registry()
        self.sec_scores()
        self.sec_charts()
        self.sec_flows()
        self.sec_gantt()
        self.sec_kanban()
        self.sec_mockups()
        self.sec_refs()
        self.sec_current()
        self.sec_model()
        self.sec_competitors()
        self.sec_market()
        self.sec_sources()
        self.sec_questions()
        return self.assemble()

    # --- реестр: строки для JS
    def proposal_concepts(self, p):
        """Концепты дизайна предложения: макеты (поле mockup и mockups-index.proposals) и референсы design-refs;
        макет и его же референс — одна запись (картинка референса с зонами)."""
        pid, out, seen_m, seen_r = p["id"], [], set(), set()
        stem = Path(str(p.get("mockup") or "")).stem if p.get("mockup") else ""
        for m in self.mock.values():
            hit = (stem and (m["key"] == stem or str(m.get("html") or "").endswith(str(p.get("mockup"))))) or pid in str_list(m.get("proposals"))
            if not hit or m["key"] in seen_m or str(m.get("kind") or "concept") == "current":
                continue
            seen_m.add(m["key"])
            rstem, r = self.ref_for_mock(m)
            img, ref = m.get("img"), ""
            if r is not None:
                seen_r.add(rstem)
                if r.get("img"):
                    img, ref = r["img"], rstem
            out.append({"title": text_of(m.get("title")) or m["key"], "img": img, "ref": ref or (rstem if r is not None and img else ""),
                        "mock": m["key"], "html": self.rel_link(str(m.get("html"))) if m.get("html") else "",
                        "mobile": self.is_mobile_img(img, str(m.get("viewport") or ""))})
        for st, r in self.refs.items():
            if st in seen_r:
                continue
            hs_p = [str(h.get("proposal")) for h in as_list(r.get("hotspots")) if isinstance(h, dict) and h.get("proposal")]
            if pid in str_list(r.get("proposals")) or pid in hs_p:
                seen_r.add(st)
                out.append({"title": text_of(r.get("title")) or st, "img": r.get("img"), "ref": st, "mock": "", "html": "",
                            "mobile": str(r.get("kind")) == "mobile"})
        if stem and not out:
            out.append({"title": stem, "img": None, "ref": "", "mock": "", "mobile": False,
                        "html": self.rel_link("mockups/" + str(p.get("mockup")))})
        return out

    def build_rows(self):
        mentions = {}

        def mention(pid, kind, item):
            mentions.setdefault(pid, {}).setdefault(kind, []).append(item)
        for i, g in enumerate(self.gantt_tasks()):
            for pid in g["proposal_ids"]:
                mention(pid, "gantt", {"i": i, "t": g["task"]})
        for i, c in enumerate(self.kanban_cards):
            cid = str(c.get("id") or "")
            if cid:
                mention(cid, "kanban", {"i": i, "t": text_of(c.get("column"))})
        for f in self.flows:
            for n in as_list(f.get("nodes")):
                if isinstance(n, dict):
                    for pid in str_list(n.get("proposals")):
                        mention(pid, "flows", {"id": str(n.get("id")), "t": text_of(n.get("label")) or str(n.get("id")),
                                               "f": text_of(f.get("title"))})
        rdeps = {}
        for p in self.P:
            for d in str_list(p.get("dependencies")):
                rdeps.setdefault(d, []).append(p["id"])
        rows = []
        for p in self.P:
            s = self.S.get(p["id"], {})
            sc = p.get("scores") if isinstance(p.get("scores"), dict) else {}
            m = {}
            for k, v in s.items():
                if k in ("id",) or isinstance(v, bool):
                    continue
                x = num(v) if isinstance(v, (int, float)) else None
                if x is not None:
                    m[k] = x
            val = num(sc.get("value"))
            for k in ["value", "cost", "risk", "confidence"] + SUBSCALES + [k for k in sc if k not in SCORE_LABELS]:
                x = num(sc.get(k))
                if x is None and k in SUBSCALES:
                    x = val
                if x is not None:
                    m["s_" + k] = x
            lo, hi = parse_range(p.get("effort_days"))
            if lo is not None:
                m["effort_min"], m["effort_max"], m["effort_avg"] = lo, hi, (lo + hi) / 2
            cm = p.get("cost_money") if isinstance(p.get("cost_money"), dict) else {}
            if num(cm.get("min")) is not None:
                m["cost_min"] = num(cm.get("min"))
            if num(cm.get("max")) is not None:
                m["cost_max"] = num(cm.get("max"))
            if num(p.get("time_to_first_result_days")) is not None:
                m["ttfr"] = num(p.get("time_to_first_result_days"))
            risks = p.get("risks") if isinstance(p.get("risks"), dict) else {}
            rv = [num(v) for k, v in risks.items() if k != "note" and num(v) is not None]
            if rv:
                m["risk_sum"], m["risk_max"] = sum(rv), max(rv)
            ts = s.get("typesafe") if isinstance(s.get("typesafe"), dict) else {}
            jev = self.jev_items.get(p["id"]) if isinstance(self.jev_items.get(p["id"]), dict) else {}
            for k, v in list(ts.items()) + list(jev.items()):
                x = num(v) if isinstance(v, (int, float)) else None
                if x is not None:
                    m["ts_" + str(k)] = x
            m["evidence_n"] = float(len(as_list(p.get("evidence"))))
            concepts = self.proposal_concepts(p)
            labels = [str(x) for x in as_list(s.get("labels"))]
            row = {
                "id": p["id"], "title": text_of(p.get("title")), "category": str(p.get("category") or ""),
                "segment": text_of(p.get("segment")), "description": text_of(p.get("description")),
                "rationale": text_of(p.get("rationale")), "evidence": as_list(p.get("evidence")),
                "evidence_class": str(p.get("evidence_class") or ""), "current_feature": text_of(p.get("current_feature")),
                "effect_kpi": as_list(p.get("effect_kpi")), "steps": as_list(p.get("steps")),
                "dependencies": str_list(p.get("dependencies")), "effort": [lo, hi], "cost_money": cm,
                "risks": risks, "ttfr": p.get("time_to_first_result_days"), "cheap_test": text_of(p.get("cheap_test")),
                "scores": sc, "kano": str(p.get("kano") or ""), "horizon": str(p.get("horizon") or ""),
                "horizon_years": p.get("horizon_years"), "tags": str_list(p.get("tags")), "mockup": p.get("mockup"),
                "source_group": text_of(p.get("source_group")), "merged_from": str_list(p.get("merged_from")),
                "quadrant": str(s.get("quadrant") or ""), "priority": str(s.get("priority") or ""),
                "moscow": str(s.get("moscow") or ""), "labels": labels,
                "typesafe": ts or None, "jev": jev or None, "m": m, "concepts": concepts,
                "has_mockup": bool(concepts), "mentions": mentions.get(p["id"], {}), "rdeps": rdeps.get(p["id"], []),
            }
            hay = " ".join([row["id"], row["title"], row["description"], row["rationale"], row["segment"],
                            " ".join(row["tags"]), CAT_LABELS.get(row["category"], row["category"]), row["current_feature"],
                            row["cheap_test"], " ".join(LABEL_LABELS.get(x, x) for x in labels)])
            row["_hay"] = hay.lower().replace("ё", "е")
            rows.append(row)
        return rows

    def metrics_def(self):
        """Метрики для сортировки: только те, у которых есть хотя бы одно значение."""
        keys = []
        for r in self.rows:
            for k in r["m"]:
                if k not in keys:
                    keys.append(k)
        groups = {"calc": [], "scale": [], "cost": [], "ts": [], "other": []}
        cost_keys = {"effort_min": "Дни: минимум", "effort_max": "Дни: максимум", "effort_avg": "Дни: среднее",
                     "cost_min": "Деньги: минимум", "cost_max": "Деньги: максимум", "ttfr": "Дней до первого результата",
                     "risk_sum": "Риски: сумма", "risk_max": "Риски: максимум", "evidence_n": "Число доказательств"}
        out = []
        for k in keys:
            if k.startswith("s_"):
                g, lab = "scale", SCORE_LABELS.get(k[2:], k[2:]) + " (1–5)"
            elif k in cost_keys:
                g, lab = "cost", cost_keys[k]
            elif k.startswith("ts_"):
                g, lab = "ts", "TypeSafe: " + k[3:]
            elif k in METRIC_LABELS:
                g, lab = "calc", METRIC_LABELS[k]
            else:
                g, lab = "other", k
            out.append({"k": k, "label": lab, "g": g, "dir": 1 if k in ASC_METRICS else -1})
        order = {"calc": 0, "scale": 1, "cost": 2, "ts": 3, "other": 4}
        calc_order = list(METRIC_LABELS)
        out.sort(key=lambda d: (order[d["g"]], calc_order.index(d["k"]) if d["k"] in calc_order else 99, d["label"]))
        return out

    # --- 1. резюме
    def sec_top(self):
        title = self.page_title()
        who, cp = self.author_line()
        prod = self.cfg.get("product") if isinstance(self.cfg.get("product"), dict) else {}
        st = self.cfg.get("strategy") if isinstance(self.cfg.get("strategy"), dict) else {}
        facts = []
        if prod.get("name"):
            facts.append(("Продукт", esc(prod["name"]) + (" · " + ext_link(prod["url"]) if prod.get("url") else "")))
        if st.get("goal"):
            facts.append(("Цель", esc(st["goal"])))
        kind = {"growth": "рост", "gtm": "выход на рынок", "monetization": "монетизация", "tech-roadmap": "техническая дорожная карта",
                "oss-community": "открытый проект и сообщество", "full": "полная"}.get(str(st.get("kind")), st.get("kind"))
        if kind:
            facts.append(("Тип стратегии", esc(kind)))
        hm, vy = to_int(st.get("horizon_months")), to_int(st.get("vision_years"))
        if hm:
            facts.append(("Горизонт", "%d мес." % hm + (" + видение на %d г." % vy if vy else "")))
        if st.get("markets"):
            facts.append(("Рынки", esc(", ".join(str_list(st.get("markets"))))))
        facts.append(("Дата", esc(self.date)))
        tiles = []
        n = len(self.rows)
        if n:
            ab = sum(1 for r in self.rows if r["evidence_class"] in ("A", "B"))
            tiles.append((str(n), "предложений в реестре", ""))
            tiles.append(("%d%%" % round(100 * ab / n), "с доказательствами A/B", "%d из %d" % (ab, n)))
            if self.S:
                p0 = sum(1 for r in self.rows if r["priority"] == "P0")
                qw = sum(1 for r in self.rows if r["quadrant"] == "quick_win")
                tiles.append((str(p0), "приоритет P0", "быстрых побед: %d" % qw))
        if self.sens and num(self.sens.get("top20_stability")) is not None:
            tiles.append(("%d%%" % round(100 * num(self.sens["top20_stability"])), "устойчивость топ-20",
                          "к изменению весов ×0,5…×1,5"))
        nc = len([c for c in self.comp if not c.get("self")])
        if nc:
            tiles.append((str(nc), "конкурентов разобрано", ""))
        if self.sources:
            ok = sum(1 for s in self.sources if to_int(s.get("status")) and 200 <= to_int(s.get("status")) < 400)
            tiles.append((str(len(self.sources)), "источников", "проверено: %d" % ok))
        nm = len([m for m in self.mock.values() if str(m.get("kind") or "concept") != "current"])
        if nm:
            tiles.append((str(nm), "макетов-концептов", ""))
        if self.refs:
            tiles.append((str(len(self.refs)), "референсов дизайна", ""))
        if self.charts:
            tiles.append((str(len([c for c in self.charts if c.get("img")])), "графиков", ""))
        kpi = "".join('<div class="kpi"><div class="n">' + esc(a) + '</div><div class="l">' + esc(b) + "</div>"
                      + ('<div class="s">' + esc(c) + "</div>" if c else "") + "</div>" for a, b, c in tiles)
        pre = ""
        if self.strategy:
            pre_text = self.split_strategy()[0]
            if pre_text.strip():
                pre = '<div class="prose">' + self.links(self.md(min_heading=3).render(pre_text)) + "</div>"
        top10 = ""
        ranked = sorted([r for r in self.rows if r["m"].get("rank") is not None], key=lambda r: r["m"]["rank"])[:10]
        if ranked:
            trs = "".join("<tr><td class=\"num\">" + fmt_num(r["m"]["rank"]) + "</td><td>"
                          + (pid_link(r["id"], self.titles) if r["id"] in self.titles else esc(r["id"]))
                          + "</td><td>" + esc(r["title"]) + "</td><td>" + self.badge("q", r["quadrant"]) + "</td><td>"
                          + self.badge("p", r["priority"]) + "</td><td class=\"num\">" + fmt_num(r["m"].get("composite")) + "</td></tr>"
                          for r in ranked)
            top10 = ('<h3>Топ-10 по итоговому баллу</h3><div class="tbl"><table class="data"><thead><tr><th>#</th><th>ID</th>'
                     "<th>Предложение</th><th>Квадрант</th><th>Приоритет</th><th>Балл</th></tr></thead><tbody>" + trs
                     + "</tbody></table></div>")
        assum = str_list(self.cfg.get("assumptions"))
        assum_html = ("<details class=\"assum\"><summary>Допущения прогона (%d)</summary><ul>" % len(assum)
                      + "".join("<li>" + esc(a) + "</li>" for a in assum) + "</ul></details>") if assum else ""
        author = ""
        if who or cp:
            author = '<p class="author">' + ("Автор: <b>" + esc(who) + "</b>" if who else "") + (" · " if who and cp else "") + esc(cp) + "</p>"
        body = ('<section id="top" class="top"><p class="eyebrow">Стратегия развития продукта · ' + esc(self.date) + "</p><h1>"
                + esc(title) + "</h1>" + author + '<dl class="facts">' + "".join("<dt>" + a + "</dt><dd>" + b + "</dd>" for a, b in facts)
                + "</dl>" + ('<div class="kpis">' + kpi + "</div>" if kpi else "") + pre + self.links(top10) + assum_html
                + '<p class="hint muted">Как читать: любой номер предложения (например, P001) открывает его карточку; любая картинка '
                "увеличивается по клику; строки Ганта, карточки Kanban и блоки схем раскрываются. Esc закрывает верхнее окно.</p></section>")
        self.add("top", "Резюме и ключевые цифры", body)

    def badge(self, kind, v):
        if not v:
            return ""
        if kind == "q":
            return '<span class="b b-' + esc(slug(v)) + '">' + esc(QUADRANT_LABELS.get(v, v)) + "</span>"
        if kind == "p":
            return '<span class="b b-' + esc(slug(v)) + '">' + esc(v) + "</span>"
        if kind == "c":
            return '<span class="b b-' + esc(slug(v)) + '">' + esc(v) + "</span>"
        return '<span class="tag">' + esc(v) + "</span>"

    # --- 2. разделы стратегии
    def split_strategy(self):
        if hasattr(self, "_split"):
            return self._split
        lines = (self.strategy or "").replace("\r\n", "\n").split("\n")
        pre, secs, cur, fence, h1_done = [], [], None, None, False
        for line in lines:
            fm = FENCE_RE.match(line)
            if fence:
                if re.match(r"^\s{0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$", line):
                    fence = None
                (cur[1] if cur else pre).append(line)
                continue
            if fm:
                fence = fm.group(2)
                (cur[1] if cur else pre).append(line)
                continue
            m = re.match(r"^\s{0,3}##\s+(.+?)\s*#*\s*$", line)
            if m:
                cur = [m.group(1).strip(), []]
                secs.append(cur)
                continue
            if not h1_done and cur is None and re.match(r"^\s{0,3}#\s+", line):
                h1_done = True
                continue
            (cur[1] if cur else pre).append(line)
        self._split = ("\n".join(pre), secs)
        return self._split

    def sec_strategy(self):
        if not self.strategy:
            return
        _, secs = self.split_strategy()
        used = set()
        for i, (title, body) in enumerate(secs, 1):
            m = re.match(r"^(\d+)[.)]\s", title)
            sid = "s-" + m.group(1) if m and ("s-" + m.group(1)) not in used else "s-x" + str(i)
            used.add(sid)
            inner = self.md(min_heading=3).render("\n".join(body))
            html_ = ('<section id="' + sid + '" class="prose strat"><h2>' + Markdown().inline(title) + "</h2>" + inner + "</section>")
            self.add(sid, title, self.links(html_), "Стратегия")

    # --- 3. реестр
    def options(self, field, order, labels, all_label, values):
        counts = {}
        for v in values:
            if v not in ("", None):
                counts[v] = counts.get(v, 0) + 1
        if not counts:
            return ""
        keys = [k for k in order if k in counts] + sorted(k for k in counts if k not in order)
        opts = '<option value="">' + esc(all_label) + "</option>" + "".join(
            '<option value="' + esc(k) + '">' + esc(labels.get(k, k)) + " (" + str(counts[k]) + ")</option>" for k in keys)
        return '<select data-f="' + field + '" aria-label="' + esc(all_label) + '">' + opts + "</select>"

    def sec_registry(self):
        if not self.rows:
            return
        R = self.rows
        f = [
            self.options("category", list(CAT_LABELS), CAT_LABELS, "Все категории", [r["category"] for r in R]),
            self.options("horizon", list(HORIZON_LABELS), HORIZON_LABELS, "Все горизонты", [r["horizon"] for r in R]),
            self.options("evidence_class", list("ABCD"), {k: "Класс " + k for k in "ABCD"}, "Все классы доказательств",
                         [r["evidence_class"] for r in R]),
            self.options("priority", ["P0", "P1", "P2", "P3"], {}, "Все приоритеты", [r["priority"] for r in R]),
            self.options("quadrant", list(QUADRANT_LABELS), QUADRANT_LABELS, "Все квадранты", [r["quadrant"] for r in R]),
            self.options("labels", list(LABEL_LABELS), LABEL_LABELS, "Все метки", [x for r in R for x in r["labels"]]),
            self.options("kano", list(KANO_LABELS), KANO_LABELS, "Кано: все", [r["kano"] for r in R]),
            self.options("has_mockup", ["yes", "no"], {"yes": "с макетом", "no": "без макета"}, "Макет: все",
                         ["yes" if r["has_mockup"] else "no" for r in R]) if any(r["has_mockup"] for r in R) else "",
            self.options("tags", [], {}, "Все теги", [x for r in R for x in r["tags"]]),
        ]
        mets = self.metrics_def()
        gl = {"calc": "Расчётные метрики", "scale": "Оценки 1–5", "cost": "Затраты, сроки, риски", "ts": "TypeSafe", "other": "Прочее"}
        sort_opts, last = "", None
        for d in mets:
            if d["g"] != last:
                sort_opts += ("</optgroup>" if last else "") + '<optgroup label="' + esc(gl[d["g"]]) + '">'
                last = d["g"]
            sort_opts += '<option value="' + esc(d["k"]) + '">' + esc(d["label"]) + "</option>"
        sort_opts += ("</optgroup>" if last else "") + '<optgroup label="Поля"><option value="id">ID</option>' \
            '<option value="title">Название</option><option value="category">Категория</option>' \
            '<option value="horizon">Горизонт</option><option value="evidence_class">Класс доказательств</option></optgroup>'
        inner = ('<p class="lead">Все предложения с оценками. Клик по строке раскрывает карточку, по номеру — открывает её в окне. '
                 "Сортировка — по заголовку столбца или по любой метрике из списка; фильтры и поиск сочетаются. "
                 "Экспорт сохраняет то, что сейчас показано.</p>"
                 '<div class="toolbar" role="search"><input id="q" type="search" placeholder="Поиск: ID, название, описание, сегмент, теги…" '
                 'aria-label="Поиск по реестру">' + "".join(f) + "</div>"
                 '<div class="toolbar"><label class="lbl">Сортировка <select id="sortby" aria-label="Сортировать по метрике">'
                 + sort_opts + '</select></label><button id="sortdir" type="button" aria-label="Направление сортировки">по возрастанию ↑</button>'
                 '<button id="reg-reset" type="button">Сбросить фильтры</button><span id="reg-count" class="count" aria-live="polite"></span>'
                 '<span class="spacer"></span><button id="exp-csv" type="button" title="Отфильтрованный реестр в CSV (UTF-8, Excel)">↓ CSV</button>'
                 '<button id="exp-json" type="button" title="Отфильтрованный реестр в JSON">↓ JSON</button></div>'
                 '<div class="reg-wrap"><table id="reg" class="reg"><thead><tr id="reg-head"></tr></thead><tbody id="tb"></tbody></table></div>'
                 '<noscript><p class="missing">Реестр показывается скриптом страницы; без JavaScript см. data/proposals.json.</p></noscript>')
        self.add("registry", "Реестр предложений", self.section("registry", "Реестр предложений <span class=\"muted\">(%d)</span>" % len(R), inner))

    # --- 4. оценки и чувствительность
    def sec_scores(self):
        parts = []
        if self.S and self.rows:
            by_q = {}
            for r in sorted(self.rows, key=lambda r: (r["m"].get("rank") if r["m"].get("rank") is not None else 1e9, r["id"])):
                if r["quadrant"]:
                    by_q.setdefault(r["quadrant"], []).append(r)
            if by_q:
                cells = []
                desc = {"quick_win": "высокая ценность, низкая стоимость", "big_bet": "высокая ценность, высокая стоимость",
                        "filler": "низкая ценность, низкая стоимость", "money_pit": "низкая ценность, высокая стоимость"}
                for q in ("quick_win", "big_bet", "filler", "money_pit"):
                    rs = by_q.get(q, [])
                    top = "".join("<li>" + pid_link(r["id"], self.titles) + " " + esc(r["title"]) + "</li>" for r in rs[:5]
                                  if PID_FULL.match(r["id"]))
                    cells.append('<div class="quad q-' + q + '"><div class="qh">' + self.badge("q", q) + ' <b>' + str(len(rs))
                                 + '</b></div><div class="qd muted">' + desc[q] + "</div><ol>" + top + "</ol></div>")
                parts.append('<h3>Квадранты: ценность × стоимость</h3><div class="quads">' + "".join(cells) + "</div>")
            dist = []
            for title, field, order, labels in (("Приоритеты", "priority", ["P0", "P1", "P2", "P3"], {}),
                                                ("MoSCoW", "moscow", list(MOSCOW_LABELS), MOSCOW_LABELS),
                                                ("Горизонт", "horizon", list(HORIZON_LABELS), HORIZON_LABELS)):
                cnt = {}
                for r in self.rows:
                    if r[field]:
                        cnt[r[field]] = cnt.get(r[field], 0) + 1
                if cnt:
                    mx = max(cnt.values())
                    keys = [k for k in order if k in cnt] + [k for k in cnt if k not in order]
                    bars = "".join('<div class="brow"><span class="bl">' + esc(labels.get(k, k)) + '</span><span class="bt"><span class="bv" style="width:'
                                   + "%.1f" % (100.0 * cnt[k] / mx) + '%"></span></span><span class="bn">' + str(cnt[k]) + "</span></div>" for k in keys)
                    dist.append('<div class="bars"><h4>' + title + "</h4>" + bars + "</div>")
            lab_cnt = {}
            for r in self.rows:
                for x in r["labels"]:
                    lab_cnt[x] = lab_cnt.get(x, 0) + 1
            if lab_cnt:
                mx = max(lab_cnt.values())
                keys = [k for k in LABEL_LABELS if k in lab_cnt] + [k for k in lab_cnt if k not in LABEL_LABELS]
                dist.append('<div class="bars"><h4>Метки</h4>' + "".join(
                    '<div class="brow"><span class="bl">' + esc(LABEL_LABELS.get(k, k)) + '</span><span class="bt"><span class="bv" style="width:'
                    + "%.1f" % (100.0 * lab_cnt[k] / mx) + '%"></span></span><span class="bn">' + str(lab_cnt[k]) + "</span></div>" for k in keys) + "</div>")
            if dist:
                parts.append('<h3>Распределения</h3><div class="dists">' + "".join(dist) + "</div>")
        if self.sens:
            stab = num(self.sens.get("top20_stability"))
            runs = to_int(self.sens.get("runs"))
            always = str_list(self.sens.get("always_top20"))
            head = "<p>"
            if stab is not None:
                head += "Устойчивость топ-%s к изменению весов: <b>%d%%</b>" % (esc(self.sens.get("top_n") or 20), round(stab * 100))
            if runs:
                head += " · прогонов: %d" % runs
            head += "</p>"
            if always:
                head += "<p>Всегда в топе: " + self.chips(always) + "</p>"
            tor = [t for t in as_list(self.sens.get("tornado")) if isinstance(t, dict)]
            if tor:
                mx = max([abs(num(t.get("low_rank_shift")) or 0) for t in tor] + [abs(num(t.get("high_rank_shift")) or 0) for t in tor] + [1e-9])
                trs = ""
                for t in tor[:20]:
                    lo, hi = num(t.get("low_rank_shift")) or 0.0, num(t.get("high_rank_shift")) or 0.0
                    trs += ('<tr><td>' + esc(t.get("param")) + '</td><td class="tor"><span class="tl"><span style="width:'
                            + "%.1f" % (50 * abs(lo) / mx) + '%"></span></span><span class="th"><span style="width:' + "%.1f" % (50 * abs(hi) / mx)
                            + '%"></span></span></td><td class="num">' + fmt_num(lo) + '</td><td class="num">' + fmt_num(hi) + "</td></tr>")
                head += ('<h3>Торнадо: сдвиг рангов при весе ×0,5 и ×1,5</h3><div class="tbl"><table class="data tornado"><thead><tr>'
                         "<th>Параметр</th><th>Сдвиг (×0,5 | ×1,5)</th><th>×0,5</th><th>×1,5</th></tr></thead><tbody>" + trs + "</tbody></table></div>")
            parts.append("<h3>Чувствительность</h3>" + head)
        if self.weights:
            flat = []

            def walk(prefix, o):
                if isinstance(o, dict):
                    for k, v in o.items():
                        walk(prefix + "." + str(k) if prefix else str(k), v)
                else:
                    flat.append((prefix, text_of(o)))
            walk("", self.weights)
            if flat:
                parts.append('<details><summary>Действующие веса формул (data/weights.json, %d)</summary><div class="tbl"><table class="data">'
                             "<thead><tr><th>Параметр</th><th>Значение</th></tr></thead><tbody>" % len(flat)
                             + "".join("<tr><td><code>" + esc(k) + "</code></td><td>" + esc(v) + "</td></tr>" for k, v in flat)
                             + "</tbody></table></div></details>")
        if self.jev:
            parts.append('<p class="muted">TypeSafe: модель ' + esc(self.jev.get("model") or "") + (", " + esc(self.jev.get("date")) if self.jev.get("date") else "")
                         + (" · пропущено: " + esc(self.jev.get("skipped")) if self.jev.get("skipped") else "")
                         + ". Значения — в карточках предложений и в сортировке реестра («TypeSafe: …»).</p>")
        sch = [c for c in self.charts if c.get("img") and c["section"] in ("scores", "registry")]
        if parts and sch:
            parts.append('<p class="muted">Графики оценок: ' + ", ".join('<a class="emb" href="#lb=' + esc(c["img"]) + '">' + esc(c["title"]) + "</a>" for c in sch) + "</p>")
        if parts:
            self.add("scores", "Оценки и чувствительность", self.section("scores", "Оценки и чувствительность", self.links("".join(parts))))

    # --- 5. графики
    def sec_charts(self):
        ch = [c for c in self.charts if c.get("img")]
        if not ch:
            return
        groups = {}
        for c in ch:
            groups.setdefault(c["section"], []).append(c)
        inner = '<p class="lead">Нажмите на график, чтобы открыть его крупно (вписать, 1:1, 2×) и листать стрелками.</p>'
        for sec, cs in groups.items():
            if len(groups) > 1 or sec:
                inner += "<h3>" + esc(CHART_SECTION_LABELS.get(sec, sec or "Прочее")) + "</h3>"
            inner += '<div class="gallery charts">' + "".join(self.chart_fig(c) for c in cs) + "</div>"
        self.add("charts", "Графики", self.section("charts", "Графики", inner))

    # --- 6. блок-схемы
    def load_flows(self):
        """data/flows.json → описания узлов (для модалок) и ключи схем (для раздела и вставок ![[flow:key]])."""
        self.flow_nodes, self.flow_list, self.flow_by_key, self._flow_n = {}, [], {}, 0
        for fi, f in enumerate(self.flows):
            key = str(f.get("key") or "flow-%d" % (fi + 1))
            nodes = [n for n in as_list(f.get("nodes")) if isinstance(n, dict) and n.get("id")]
            title = text_of(f.get("title")) or key
            for n in nodes:
                nid = str(n["id"])
                self.flow_nodes[nid] = {"id": nid, "label": text_of(n.get("label")) or nid, "what": text_of(n.get("what")),
                                        "now": text_of(n.get("now")), "todo": str_list(n.get("todo")),
                                        "proposals": str_list(n.get("proposals")), "metrics": text_of(n.get("metrics")), "flow": title}
            src = None
            if f.get("svg"):
                pth = self.img.resolve(str(f["svg"]))
                if pth and pth.is_file():
                    try:
                        src = pth.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        src = None
                if src is None:
                    self.warn("блок-схема %s: нет или не читается %s" % (key, f.get("svg")))
            item = {"key": key, "title": title, "nodes": nodes, "src": src}
            self.flow_list.append(item)
            self.flow_by_key.setdefault(key, item)

    def flow_block(self, fl, embedded=False):
        """Живой SVG схемы с кликабельными узлами; у каждой вставки своя область id (схема может стоять и в тексте, и в разделе)."""
        self._flow_n += 1
        key, title, nodes = fl["key"], fl["title"], fl["nodes"]
        scope = "fl-" + slug(key) + "-" + str(self._flow_n)
        svg_html = sanitize_svg(fl["src"], scope, {str(n["id"]) for n in nodes}) if fl.get("src") else ""
        if fl.get("src") and not svg_html:
            self.warn("блок-схема %s: в файле нет <svg>" % key)
        chips = "".join('<button type="button" class="nchip" data-node="' + esc(n["id"]) + '">' + esc(text_of(n.get("label")) or n["id"])
                        + "</button>" for n in nodes)
        anchor = "" if embedded else ' id="flow-' + esc(slug(key)) + '"'
        body = '<div class="flow' + (" embedded" if embedded else "") + '"' + anchor + "><h3>" + esc(title) + "</h3>"
        if svg_html:
            body += ('<div class="flowsvg" id="' + scope + '" data-imgkey="flow-' + esc(slug(key)) + '" data-cap="' + esc(title) + '">'
                     + svg_html + "</div>")
        if chips:
            body += '<div class="nchips"><span class="muted">Блоки схемы:</span> ' + chips + "</div>"
        if svg_html:
            body += ('<p class="muted small">Нажмите на блок схемы — откроется расшифровка: что это, как сейчас, что сделать, '
                     'как измерять и связанные предложения. <button type="button" class="lb linkbtn" data-key="flow-' + esc(slug(key))
                     + '" data-group="flows" data-ref="" data-cap="' + esc(title) + '">⤢ открыть схему как картинку</button></p>')
        return body + "</div>"

    def sec_flows(self):
        if not self.flow_list:
            return
        blocks = "".join(self.flow_block(fl) for fl in self.flow_list)
        self.add("flows", "Блок-схемы", self.section("flows", "Блок-схемы", blocks))

    # --- 7. Гант
    def gantt_tasks(self):
        if hasattr(self, "_gt"):
            return self._gt
        tasks = []
        for g in self.gantt:
            s, e = to_int(g.get("start_month")), to_int(g.get("end_month"))
            if s is None and e is None:
                self.warn("data/gantt.json: задача без месяцев — пропущена (%s)" % text_of(g.get("task"))[:40])
                continue
            s = s if s is not None else e
            e = e if e is not None else s
            if e < s:
                s, e = e, s
            s, e = max(1, s), max(1, e)
            tasks.append({"id": text_of(g.get("id")), "phase": text_of(g.get("phase")) or "—", "task": text_of(g.get("task")) or "—",
                          "proposal_ids": str_list(g.get("proposal_ids")), "start": s, "end": e,
                          "type": "milestone" if str(g.get("type")) == "milestone" else "task", "owner": text_of(g.get("owner")),
                          "done": text_of(g.get("done_criteria")), "deps": str_list(g.get("dependencies"))})
        self._gt = tasks
        return tasks

    def month_label(self, m, with_year=False):
        y0, m0 = int(self.date[:4]), int(self.date[5:7]) - 1
        idx = m0 + m - 1
        name, year = MONTHS_RU[idx % 12], y0 + idx // 12
        return name + (" " + str(year) if with_year else "")

    def sec_gantt(self):
        tasks = self.gantt_tasks()
        if not tasks:
            return
        st = self.cfg.get("strategy") if isinstance(self.cfg.get("strategy"), dict) else {}
        H = to_int(st.get("horizon_months")) or 12
        H = max(1, H)
        plan_end = max([t["end"] for t in tasks if t["phase"].lower() != "vision" and t["start"] <= H] + [1])
        H = max(H, min(plan_end, 36))
        max_end = max(t["end"] for t in tasks)
        V = 0 if max_end <= H else int(math.ceil((max_end - H) / 12.0)) * 12
        Wm = 100.0 if not V else 74.0

        def pos(m0):  # m0 — граница месяца (0…H+V)
            if m0 <= H:
                return m0 / float(H) * Wm
            return Wm + (m0 - H) / float(V) * (100.0 - Wm)
        step = 1 if H <= 15 else 2 if H <= 30 else 3
        scale = ""
        for m in range(1, H + 1):
            if (m - 1) % step:
                continue
            lab = self.month_label(m)
            idx = int(self.date[5:7]) - 1 + m - 1
            if m == 1 or idx % 12 == 0:
                lab += "’" + str(int(self.date[:4]) + idx // 12)[2:]
            scale += ('<span style="left:%.2f%%;width:%.2f%%" title="месяц %d · %s">%s</span>'
                      % (pos(m - 1), pos(min(H, m - 1 + step)) - pos(m - 1), m, self.month_label(m, True), esc(lab)))
        for y in range(V // 12):
            a, b = H + 12 * y, H + 12 * (y + 1)
            lab = ("год %d" % (b // 12)) if H % 12 == 0 else "мес. %d–%d" % (a + 1, b)
            scale += '<span class="yr" style="left:%.2f%%;width:%.2f%%">%s</span>' % (pos(a), pos(b) - pos(a), esc(lab))
        phases, order = {}, []
        for i, t in enumerate(tasks):
            if t["phase"] not in phases:
                phases[t["phase"]] = []
                order.append(t["phase"])
            phases[t["phase"]].append(i)
        rows = ""
        js = []
        for i, t in enumerate(tasks):
            when = self.when(t["start"], t["end"], H)
            js.append(dict(t, i=i, when=when))
        for pi, ph in enumerate(order):
            vis = ph.lower() in ("vision", "видение")
            rows += '<div class="gphase"><span class="gdot c%d"></span>%s</div>' % (pi % 8, esc("Видение" if ph.lower() == "vision" else ph))
            for i in phases[ph]:
                t = tasks[i]
                left, right = pos(t["start"] - 1), pos(t["end"])
                if t["type"] == "milestone":
                    bar = '<span class="gms c%d" style="left:%.2f%%" title="веха: %s"></span>' % (pi % 8, (left + right) / 2, esc(js[i]["when"]))
                else:
                    bar = '<span class="gbar c%d%s" style="left:%.2f%%;width:%.2f%%" title="%s"></span>' % (
                        pi % 8, " vis" if vis or t["start"] > H else "", left, max(0.8, right - left), esc(js[i]["when"]))
                sep = '<span class="gsep" style="left:%.2f%%"></span>' % Wm if V else ""
                rows += ('<div class="grow" data-g="%d" tabindex="0" role="button" aria-label="%s"><div class="glabel">%s%s%s</div>'
                         '<div class="gtrack">%s%s</div></div>') % (
                    i, esc(t["task"] + ", " + js[i]["when"]), ('<span class="gid">' + esc(t["id"]) + "</span> " if t["id"] else ""),
                    self.links(esc(t["task"])), (' <span class="muted">· ' + esc(t["owner"]) + "</span>" if t["owner"] else ""), sep, bar)
        self.gantt_js = js
        gch = self.charts_by_key.get("gantt")
        legend = ('<p class="muted small">Шкала: месяцы плана 1–%d (с %s)%s. Полоса — работа, ромб — веха. Нажмите на строку: '
                  "критерий готовности, зависимости и шаги связанных предложений.%s</p>") % (
            H, self.month_label(1, True), (", дальше — годы видения" if V else ""),
            (' <a class="emb" href="#lb=' + esc(gch["img"]) + '">Гант как картинка</a>' if gch and gch.get("img") else ""))
        inner = (legend + '<div class="gantt"><div class="gin"><div class="ghead"><div class="gl">Задача</div><div class="gscale">'
                 + scale + "</div></div>" + rows + "</div></div>")
        self.add("gantt", "План и диаграмма Ганта", self.section("gantt", "План действий и диаграмма Ганта", inner))

    def when(self, s, e, H):
        if e <= H:
            cal = self.month_label(s, True) if s == e else self.month_label(s, True) + " – " + self.month_label(e, True)
            return ("месяц %d" % s if s == e else "месяцы %d–%d" % (s, e)) + " · " + cal
        return ("месяц %d" % s if s == e else "месяцы %d–%d" % (s, e)) + " · видение, год %d" % (int(math.ceil(e / 12.0)))

    # --- 8. Kanban
    def sec_kanban(self):
        cards = self.kanban_cards
        if not cards:
            return
        cols = []
        for c in self.kanban_cols:
            name = text_of(c.get("name")) if isinstance(c, dict) else text_of(c)
            if name and name not in [x[0] for x in cols]:
                cols.append((name, to_int(c.get("wip")) if isinstance(c, dict) else None))
        names = [x[0] for x in cols]
        orphan = [k for k in cards if text_of(k.get("column")) not in names]
        if orphan:
            cols.append(("Без колонки", None))
        out = []
        for name, wip in cols:
            items = [(i, k) for i, k in enumerate(cards) if (text_of(k.get("column")) == name) or (name == "Без колонки" and k in orphan)]
            over = wip is not None and len(items) > wip
            cnt = str(len(items)) + (" / " + str(wip) if wip is not None else "")
            html_cards = ""
            for i, k in items:
                lo, hi = parse_range(k.get("effort_days"))
                eff = (fmt_num(lo) + ("–" + fmt_num(hi) if hi != lo else "") + " дн.") if lo is not None else ""
                pr = text_of(k.get("priority"))
                html_cards += ('<div class="kcard" data-k="%d" tabindex="0" role="button"><div class="kid">%s</div><div class="kt">%s</div>'
                               '<div class="kmeta">%s%s</div>%s</div>') % (
                    i, esc(text_of(k.get("id"))), esc(text_of(k.get("title"))), (self.badge("p", pr) + " " if pr else ""),
                    ('<span class="muted">' + esc(eff) + "</span>" if eff else ""),
                    ('<div class="ktags">' + "".join('<span class="tag">' + esc(t) + "</span>" for t in str_list(k.get("tags"))) + "</div>"
                     if k.get("tags") else ""))
            out.append('<div class="kcol"><div class="khead"><b>' + esc(name) + '</b><span class="kcount' + (" over" if over else "")
                       + '" title="карточек / лимит WIP">' + cnt + "</span></div>" + (html_cards or '<div class="kempty muted">пусто</div>') + "</div>")
        inner = ('<p class="muted small">Нажмите на карточку: цель, KPI, шаги, ссылки и карточка предложения. Красный счётчик — превышен лимит WIP.</p>'
                 '<div class="kanban">' + "".join(out) + "</div>")
        self.add("kanban", "Kanban", self.section("kanban", "Доска Kanban <span class=\"muted\">(%d)</span>" % len(cards), self.links(inner)))

    # --- 9. макеты
    def sec_mockups(self):
        ms = [m for m in self.mock.values() if str(m.get("kind") or "concept") != "current"]
        if not ms:
            return
        inner = ('<p class="lead">Все макеты — концепты, а не существующие функции. Нажмите на макет, чтобы рассмотреть его крупно; '
                 "у макетов с референсом поверх картинки видны нумерованные элементы с описанием.</p>"
                 '<div class="gallery mocks">' + "".join(self.mock_fig(m) for m in ms) + "</div>")
        self.add("mockups", "Макеты (концепты)", self.section("mockups", "Макеты предлагаемых функций", self.links(inner)))

    # --- 10. референсы дизайна
    def sec_refs(self):
        if not self.refs:
            return
        cards = []
        self.refs_js = {}
        for stem, r in self.refs.items():
            hs = []
            W = num(r.get("width"))
            Hh = num(r.get("height"))
            meta = self.img.meta.get(r.get("img") or "", {})
            scale = num(r.get("scale")) or 1.0
            if not W and meta.get("w"):
                W = meta["w"] / scale
            if not Hh and meta.get("h"):
                Hh = meta["h"] / scale
            for h in as_list(r.get("hotspots")):
                if not isinstance(h, dict):
                    continue
                x, y, w, hh = (num(h.get(k)) or 0.0 for k in ("x", "y", "w", "h"))
                item = {"n": text_of(h.get("n")), "title": text_of(h.get("title")), "text": text_of(h.get("text")),
                        "proposal": text_of(h.get("proposal")), "state": text_of(h.get("state"))}
                if W and Hh:
                    cl = lambda v: max(0.0, min(100.0, v))
                    item.update({"l": round(cl(x / W * 100), 3), "t": round(cl(y / Hh * 100), 3)})
                    item.update({"w": round(max(0.0, min(100.0 - item["l"], w / W * 100)), 3),
                                 "h": round(max(0.0, min(100.0 - item["t"], hh / Hh * 100)), 3)})
                hs.append(item)
            if W and Hh:
                self.place_pins(hs, as_list(r.get("hotspots")), W, Hh)
            title = text_of(r.get("title")) or stem
            self.refs_js[stem] = {"title": title, "kind": text_of(r.get("kind")), "summary": text_of(r.get("summary")),
                                  "entry": text_of(r.get("entry")), "proposals": str_list(r.get("proposals")), "hotspots": hs,
                                  "todo": str_list(r.get("todo")), "w": W, "h": Hh, "scale": scale}
            media = self.ref_fig(r) if r.get("img") else '<div class="ph"><div class="ph-t">Нет картинки референса</div>' + esc(r.get("png") or "") + "</div>"
            items = "".join('<li><span class="hsn">' + esc(h["n"]) + "</span><b>" + esc(h["title"]) + "</b>"
                            + (' <span class="st st-' + esc(slug(h["state"])) + '">' + esc({"new": "новое", "changed": "изменено", "shared": "общий дизайн"}.get(h["state"], h["state"])) + "</span>" if h["state"] else "")
                            + (" — " + esc(h["text"]) if h["text"] else "") + (" " + self.chips([h["proposal"]]) if h["proposal"] else "") + "</li>" for h in hs)

            def det(title_, lst, open_=False):
                lst = str_list(lst)
                if not lst:
                    return ""
                return ("<details" + (" open" if open_ else "") + "><summary>" + title_ + " (" + str(len(lst)) + ")</summary><ul>"
                        + "".join("<li>" + esc(x) + "</li>" for x in lst) + "</ul></details>")
            md_html = self.md("design-refs").render(strip_h1(r.get("md") or "")) if r.get("md") else ""
            body = ('<article class="ref" id="ref-' + esc(stem) + '"><div class="ref-media">' + media + '</div><div class="ref-body"><h3>'
                    + esc(title) + '</h3><p class="meta">' + esc(text_of(r.get("kind")) or "экран") + (" · " + plural(len(hs), EL_FORMS) if hs else "")
                    + (" · предложения: " + self.chips(r.get("proposals")) if str_list(r.get("proposals")) else "")
                    + " · <code>design-refs/" + esc(stem) + ".md</code></p>"
                    + ("<p>" + esc(r.get("summary")) + "</p>" if r.get("summary") else "")
                    + ('<p class="muted">Точка входа: ' + esc(r.get("entry")) + "</p>" if r.get("entry") else "")
                    + ("<details open><summary>Элементы экрана (" + str(len(hs)) + ")</summary><ol class=\"hslist\">" + items + "</ol></details>" if hs else "")
                    + det("Что нужно доделать", r.get("todo")) + det("Открытые вопросы", r.get("questions"))
                    + det("Новые элементы", r.get("new_elements")) + det("Общие элементы дизайна", r.get("shared"))
                    + ('<details><summary>Полное описание</summary><div class="prose">' + md_html + "</div></details>" if md_html else "")
                    + "</div></article>")
            cards.append(body)
        intro = ""
        if self.refs_readme:
            intro = '<details class="readme"><summary>О папке design-refs/</summary><div class="prose">' + self.md("design-refs").render(strip_h1(self.refs_readme)) + "</div></details>"
        inner = ('<p class="lead">Карточки для постановки задач на интерфейс: что это, как выглядит, как взаимодействовать, что доделать. '
                 "Нажмите на картинку: элементы экрана отмечены номерами, описание — в боковой панели.</p>" + intro + "".join(cards))
        self.add("design-refs", "Референсы дизайна", self.section("design-refs", "Референсы дизайна", self.links(inner)))

    @staticmethod
    def place_pins(items, raw, W, H, gap=34.0):
        """Номера зон: в левом верхнем углу зоны; если два номера ближе gap (в пикселях исходного размера) — сдвинуть
        следующий вправо (а у правого края — вниз), чтобы номера не перекрывали друг друга и оба были кликабельны."""
        placed = []
        src = [h for h in raw if isinstance(h, dict)]
        for item, h in zip(items, src):
            if item.get("l") is None:
                continue
            x = max(13.0, min(W - 13.0, (num(h.get("x")) or 0.0) + 16.0))
            y = max(13.0, min(H - 13.0, (num(h.get("y")) or 0.0) + 16.0))
            for _ in range(60):
                hit = next((q for q in placed if abs(q[0] - x) < gap and abs(q[1] - y) < gap), None)
                if not hit:
                    break
                if hit[0] + gap <= W - 13.0:
                    x = hit[0] + gap
                else:
                    x, y = max(13.0, min(W - 13.0, (num(h.get("x")) or 0.0) + 16.0)), min(H - 13.0, hit[1] + gap)
            placed.append((x, y))
            item["pl"], item["pt"] = round(x / W * 100, 3), round(y / H * 100, 3)

    # --- 11. текущее состояние
    def sec_current(self):
        items, seen = [], set()
        d = self.out / "mockups" / "current"
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                    k = self.img.add("mockups/current/" + p.name, "cur-" + p.stem)
                    if k and k not in seen:
                        seen.add(k)
                        items.append((k, p.stem.replace("_", " ").replace("-", " "), p.name))
        for m in self.mock.values():
            if str(m.get("kind")) == "current" and m.get("img") and m["img"] not in seen:
                seen.add(m["img"])
                items.append((m["img"], text_of(m.get("title")) or m["key"], str(m.get("viewport") or "")))
        if not items:
            return
        figs = "".join(self.fig(k, "<b>" + esc(t) + '</b> <span class="tag">факт</span>', "Текущее состояние — " + t, "current",
                                "mobile" if self.is_mobile_img(k, hint) else "") for k, t, hint in items)
        inner = ('<p class="lead">Скриншоты того, что есть сейчас (факт на ' + esc(self.date) + "). Концепты их не заменяют.</p>"
                 '<div class="gallery">' + figs + "</div>")
        self.add("current", "Текущее состояние", self.section("current", "Текущее состояние (скриншоты)", inner))

    # --- 12. модель
    MODEL_NAMES = {"month": "Месяц", "visitors": "Посетители", "signups": "Регистрации", "users": "Активные", "paying": "Платящие",
                   "new_paying": "Новые платящие", "revenue": "Выручка", "net_revenue": "Чистая выручка", "cost": "Затраты",
                   "marketing": "Маркетинг", "cum_margin": "Накопл. маржа", "cum_cost": "Накопл. затраты", "margin": "Маржа",
                   "profit": "Прибыль"}

    @staticmethod
    def model_val(k, v, cur=""):
        """Значение метрики модели: доли оттока/ROI — в процентах, деньги — с валютой."""
        if isinstance(v, dict) and "value" in v:
            v = v["value"]
        x = num(v) if isinstance(v, (int, float)) else None
        if x is None:
            return esc(text_of(v)) if v is not None else '<span class="muted">—</span>'
        if k in ("churn", "roi", "churn_monthly") and abs(x) <= 5:
            return esc(fmt_num(round(x * 100, 1)) + " %")
        if cur and k in ("cac", "ltv", "arpu", "arppu", "net_revenue", "cost", "marketing", "revenue"):
            return esc(fmt_num(x) + " " + cur)
        return esc(fmt_num(x))

    def sec_model(self):
        md = self.model
        if not md or not isinstance(md.get("scenarios"), dict) or not md["scenarios"]:
            return
        sc = {k: v for k, v in md["scenarios"].items() if isinstance(v, dict)}
        if not sc:
            return
        cur = text_of(md.get("currency"))
        keys = [k for k in ("pessimistic", "base", "optimistic") if k in sc] + [k for k in sc if k not in ("pessimistic", "base", "optimistic")]
        head = "<tr><th>Показатель</th>" + "".join('<th class="num">' + esc(SCENARIO_LABELS.get(k, k)) + "</th>" for k in keys) + "</tr>"

        def row(label, vals, extra=""):
            return "<tr><td>" + esc(label) + "</td>" + "".join('<td class="num">' + v + "</td>" for v in vals) + extra + "</tr>"
        summary = ""
        metric_names = [("cac", "CAC — стоимость привлечения платящего"), ("ltv", "LTV — ценность клиента"), ("ltv_cac", "LTV / CAC"),
                        ("payback_months", "Окупаемость привлечения, мес."), ("breakeven_month", "Месяц безубыточности"),
                        ("arpu", "ARPU"), ("arppu", "ARPPU"), ("churn", "Отток в месяц"), ("roi", "ROI за горизонт")]
        known = {k for k, _ in metric_names} | {"assumptions", "funnel", "monthly", "totals", "notes"}
        for k, lab in metric_names:
            if not any(k in sc[s] for s in keys) and k != "ltv_cac":
                continue
            vals = []
            for s in keys:
                v = sc[s].get(k)
                if k == "ltv_cac" and v is None and num(sc[s].get("ltv")) and num(sc[s].get("cac")):
                    v = num(sc[s]["ltv"]) / num(sc[s]["cac"])
                if k == "breakeven_month" and k in sc[s] and v is None:
                    vals.append('<span class="muted">не достигается</span>')
                    continue
                vals.append(self.model_val(k, v, cur))
            if any("—" not in v for v in vals):
                summary += row(lab, vals)
        for k in sorted({k for s in keys for k, v in sc[s].items() if k not in known and isinstance(v, (int, float)) and not isinstance(v, bool)}):
            summary += row(k, [self.model_val(k, sc[s].get(k), cur) for s in keys])
        tot_keys = []
        for s in keys:
            t = sc[s].get("totals")
            if isinstance(t, dict):
                tot_keys += [k for k in t if k not in tot_keys]
        if tot_keys:
            for k in tot_keys:
                summary += row(self.MODEL_NAMES.get(k, k) + " за горизонт", [self.model_val(k, (sc[s].get("totals") or {}).get(k), cur) for s in keys])
        else:
            for s in keys:
                mon = [x for x in as_list(sc[s].get("monthly")) if isinstance(x, dict)]
                sc[s]["_tot"] = {"revenue": sum(num(x.get("revenue")) or 0 for x in mon), "cost": sum(num(x.get("cost")) or 0 for x in mon)} if mon else {}
            if any(sc[s].get("_tot") for s in keys):
                for k in ("revenue", "cost"):
                    summary += row(self.MODEL_NAMES[k] + " за горизонт", [self.model_val(k, sc[s]["_tot"].get(k), cur) for s in keys])
        parts = []
        meta = []
        if md.get("revenue_model"):
            meta.append("модель выручки: " + esc(text_of(md["revenue_model"])))
        if cur:
            meta.append("валюта: " + esc(cur))
        if md.get("horizon_months"):
            meta.append("горизонт: " + esc(text_of(md["horizon_months"])) + " мес.")
        if meta:
            parts.append('<p class="muted">' + " · ".join(meta).rstrip(".") + ". Все входы — допущения с метками; замените их фактами владельца.</p>")
        if summary:
            parts.append('<h3>Сводка по сценариям</h3><div class="tbl"><table class="data"><thead>' + head + "</thead><tbody>" + summary + "</tbody></table></div>")
        akeys = []
        for s in keys:
            a = sc[s].get("assumptions")
            if isinstance(a, dict):
                akeys += [k for k in a if k not in akeys]
        if akeys:
            body = ""
            for k in akeys:
                vals, lab, note = [], "", ""
                for s in keys:
                    a = sc[s].get("assumptions") if isinstance(sc[s].get("assumptions"), dict) else {}
                    v = a.get(k)
                    if isinstance(v, dict):
                        lab = lab or text_of(v.get("label"))
                        note = note or text_of(v.get("note"))
                    vals.append(self.model_val(k, v))
                body += row(k, vals, "<td>" + (self.badge("t", lab) if lab else "") + "</td><td>" + esc(note) + "</td>")
            parts.append('<details><summary>Допущения модели (' + str(len(akeys)) + ')</summary><div class="tbl"><table class="data"><thead>'
                         + head.replace("</tr>", "<th>Метка</th><th>Что это</th></tr>") + "</thead><tbody>" + body + "</tbody></table></div></details>")
        stages, slabel = [], {}
        for s in keys:
            for st in as_list(sc[s].get("funnel")):
                if isinstance(st, dict) and text_of(st.get("stage")):
                    k = text_of(st.get("stage"))
                    if k not in stages:
                        stages.append(k)
                    if st.get("label"):
                        slabel.setdefault(k, text_of(st.get("label")))
        if stages:
            def fval(s, stage):
                for st in as_list(sc[s].get("funnel")):
                    if isinstance(st, dict) and text_of(st.get("stage")) == stage:
                        return self.model_val("funnel", st.get("value"))
                return ""
            parts.append('<h3>Воронка за горизонт</h3><div class="tbl"><table class="data"><thead>' + head.replace("Показатель", "Этап") + "</thead><tbody>"
                         + "".join(row(slabel.get(stg, stg) + (" (" + stg + ")" if slabel.get(stg) else ""), [fval(s, stg) for s in keys]) for stg in stages)
                         + "</tbody></table></div>")
        for s in keys:
            mon = [x for x in as_list(sc[s].get("monthly")) if isinstance(x, dict)]
            if not mon:
                continue
            cols = []
            for x in mon:
                cols += [k for k in x if k not in cols]
            parts.append("<details><summary>Помесячно: " + esc(SCENARIO_LABELS.get(s, s)) + " (" + str(len(mon)) + " мес.)</summary><div class=\"tbl\"><table class=\"data\"><thead><tr>"
                         + "".join('<th class="num">' + esc(self.MODEL_NAMES.get(c, c)) + "</th>" for c in cols) + "</tr></thead><tbody>"
                         + "".join("<tr>" + "".join('<td class="num">' + esc(text_of(x.get(c))) + "</td>" for c in cols) + "</tr>" for x in mon)
                         + "</tbody></table></div></details>")
        notes = str_list(md.get("notes"))
        if notes:
            parts.append("<h3>Примечания</h3><ul>" + "".join("<li>" + esc(n) + "</li>" for n in notes) + "</ul>")
        self.add("model", "Модель юнит-экономики", self.section("model", "Модель юнит-экономики и сценарии", self.links("".join(parts))))

    # --- 13. конкуренты
    def sec_competitors(self):
        comps = [c for c in self.comp if not c.get("self")]
        if not comps:
            return
        feats = []
        for c in self.comp:
            if isinstance(c.get("features"), dict):
                for f in c["features"]:
                    if f not in feats:
                        feats.append(str(f))
        js = []
        for i, c in enumerate(self.comp):
            slug_ = str(c.get("slug") or "c%d" % i)
            img = None
            if c.get("shot") and not c.get("shot_blocked"):
                img = self.img.add(str(c["shot"]), "comp-" + slug_)
                if not img:
                    self.warn("конкурент %s: нет скриншота %s" % (slug_, c.get("shot")))
            feat = c.get("features") if isinstance(c.get("features"), dict) else {}
            o = {"slug": slug_, "self": bool(c.get("self")), "name": text_of(c.get("name")) or slug_, "url": text_of(c.get("url")),
                 "type": str(c.get("type") or ""), "img": img, "shot_blocked": bool(c.get("shot_blocked")), "shot_error": text_of(c.get("shot_error")),
                 "features": {str(k): (v if isinstance(v, bool) or v is None else text_of(v)) for k, v in feat.items()}}
            for k in ("segment", "price", "monetization", "languages", "audience", "freshness", "traffic", "design_note", "verdict"):
                o[k] = text_of(c.get(k))
            for k in ("better_than_us", "we_better", "best_solutions", "complaints", "adopt", "avoid", "sources"):
                o[k] = str_list(c.get(k))
            hay = " ".join([o["name"], o["url"], o["segment"], o["price"], o["monetization"], o["languages"], o["audience"],
                            o["design_note"], o["verdict"], COMP_TYPE_LABELS.get(o["type"], o["type"])]
                           + o["better_than_us"] + o["we_better"] + o["best_solutions"] + o["complaints"] + o["adopt"] + o["avoid"]
                           + [k for k, v in o["features"].items() if v])
            o["_hay"] = hay.lower().replace("ё", "е")
            js.append(o)
        self.comp_js = js
        self.comp_features = feats
        types = []
        for c in comps:
            t = str(c.get("type") or "")
            if t and t not in types:
                types.append(t)
        type_sel = ('<select id="ctype" aria-label="Тип конкурента"><option value="">Все типы</option>' + "".join(
            '<option value="' + esc(t) + '">' + esc(COMP_TYPE_LABELS.get(t, t)) + " (" + str(sum(1 for c in comps if str(c.get("type") or "") == t)) + ")</option>"
            for t in types) + "</select>") if types else ""
        inner = ('<p class="lead">Где они сильнее, где мы, их лучшие решения и дизайн. Поиск — по названию, функциям и выводам; '
                 "нажмите на скриншот, чтобы рассмотреть дизайн.</p>"
                 '<div class="toolbar" role="search"><input id="cq" type="search" placeholder="Поиск: название, функции, решения…" aria-label="Поиск по конкурентам">'
                 + type_sel + '<label class="chk"><input type="checkbox" id="cthem" checked> где лучше они</label>'
                 '<label class="chk"><input type="checkbox" id="cus" checked> где лучше мы</label>'
                 '<label class="chk"><input type="checkbox" id="cbest" checked> лучшие решения</label>'
                 '<label class="chk"><input type="checkbox" id="cdesign" checked> дизайн</label>'
                 '<span id="ccount" class="count" aria-live="polite"></span></div>'
                 + ('<details class="cm-wrap" open><summary>Матрица функций (' + str(len(feats)) + ')</summary><div id="cmatrix" class="cmatrix"></div><p class="muted small">✓ есть · — нет · ? нет данных · ~ частично; '
                    'красная рамка — у нас нет, а у большинства показанных конкурентов есть. Матрица учитывает поиск и фильтр типа.</p></details>' if feats else "")
                 + '<div id="cgrid" class="cgrid"></div>'
                 '<noscript><p class="missing">Карточки конкурентов показываются скриптом страницы; без JavaScript см. data/competitors.json.</p></noscript>')
        self.add("competitors", "Конкуренты", self.section("competitors", "Конкуренты <span class=\"muted\">(%d)</span>" % len(comps), inner))

    # --- 14. сообщества, запросы, события
    def sec_market(self):
        parts = []
        if self.communities:
            trs = ""
            for c in self.communities:
                br = to_int(c.get("ban_risk"))
                trs += ("<tr><td>" + ext_link(c.get("url"), text_of(c.get("name")) or c.get("url")) + "</td><td>" + esc(text_of(c.get("platform")))
                        + "</td><td>" + esc(text_of(c.get("language"))) + '</td><td class="num">' + esc(text_of(c.get("audience_size")) or "—")
                        + "</td><td>" + esc(text_of(c.get("self_promo_rules"))) + "</td><td>" + esc(", ".join(str_list(c.get("allowed_formats"))))
                        + '</td><td class="num" data-v="' + str(br if br is not None else "") + '"><span class="risk r' + str(br or 0) + '">'
                        + (str(br) if br is not None else "—") + "</span></td><td>" + (ext_link(c.get("source"), "источник") if c.get("source") else "") + "</td></tr>")
            parts.append("<h3>Сообщества (%d)</h3>" % len(self.communities) + '<div class="tbl"><table class="data sortable"><thead><tr><th>Площадка</th>'
                         "<th>Платформа</th><th>Язык</th><th class=\"num\">Аудитория</th><th>Правила самопромо</th><th>Форматы</th><th class=\"num\">Риск бана</th><th>Источник</th>"
                         "</tr></thead><tbody>" + trs + "</tbody></table></div>")
        if self.keywords:
            trs = ""
            for k in self.keywords:
                vol = num(k.get("volume"))
                trs += ("<tr><td>" + esc(text_of(k.get("query"))) + "</td><td>" + esc(text_of(k.get("lang"))) + "</td><td>" + esc(text_of(k.get("cluster")))
                        + "</td><td>" + esc(text_of(k.get("intent"))) + '</td><td class="num" data-v="' + ("%g" % vol if vol is not None else "") + '">'
                        + (fmt_num(vol) if vol is not None else '<span class="muted">нет данных</span>') + "</td><td>" + esc(text_of(k.get("volume_source")))
                        + '</td><td class="num">' + esc(text_of(k.get("competition")) or "—") + "</td></tr>")
            parts.append("<h3>Поисковые запросы (%d)</h3>" % len(self.keywords) + '<div class="toolbar"><input type="search" data-filter-table="kw-table" '
                         'placeholder="Фильтр запросов…" aria-label="Фильтр запросов"></div><div class="tbl tall"><table id="kw-table" class="data sortable"><thead><tr>'
                         "<th>Запрос</th><th>Язык</th><th>Кластер</th><th>Намерение</th><th class=\"num\">Объём</th><th>Источник объёма</th><th class=\"num\">Конкуренция</th>"
                         "</tr></thead><tbody>" + trs + "</tbody></table></div>")
        if self.events:
            evs = sorted(self.events, key=lambda e: str(e.get("date") or "9999"))
            trs = ""
            for e in evs:
                d = text_of(e.get("date")) + ((" – " + text_of(e.get("date_end"))) if e.get("date_end") else "")
                ver = e.get("verified")
                trs += ('<tr><td data-v="' + esc(text_of(e.get("date"))) + '">' + esc(d) + "</td><td>" + esc(text_of(e.get("title"))) + "</td><td>"
                        + esc(text_of(e.get("kind"))) + "</td><td>" + esc(text_of(e.get("relevance"))) + "</td><td>"
                        + ('<span class="ok">✓ проверено</span>' if ver is True else '<span class="muted">не проверено</span>') + "</td><td>"
                        + (ext_link(e.get("source"), "источник") if e.get("source") else "") + "</td></tr>")
            parts.append("<h3>События (%d)</h3>" % len(self.events) + '<div class="tbl"><table class="data sortable"><thead><tr><th>Дата</th><th>Событие</th>'
                         "<th>Тип</th><th>Значимость</th><th>Проверка</th><th>Источник</th></tr></thead><tbody>" + trs + "</tbody></table></div>")
        if parts:
            self.add("market", "Сообщества, запросы, события", self.section("market", "Сообщества, поисковые запросы и события", self.links("".join(parts))))

    # --- 15. источники
    def sec_sources(self):
        if not self.sources:
            return
        ok = bad = unk = 0
        trs = ""
        for s in self.sources:
            st = to_int(s.get("status"))
            if st is None:
                unk += 1
                badge = '<span class="st-unk">не проверено</span>'
            elif 200 <= st < 400:
                ok += 1
                badge = '<span class="st-ok">' + str(st) + "</span>"
            else:
                bad += 1
                badge = '<span class="st-bad">' + str(st) + "</span>"
            trs += ("<tr><td>" + esc(text_of(s.get("id"))) + '</td><td class="url">' + ext_link(s.get("url")) + "</td><td>" + esc(text_of(s.get("title")))
                    + "</td><td>" + esc(text_of(s.get("date_checked"))) + "</td><td>" + esc(text_of(s.get("used_for"))) + '</td><td data-v="'
                    + (str(st) if st is not None else "") + '">' + badge + "</td><td>" + esc(text_of(s.get("note"))) + "</td></tr>")
        summary = ('<p class="srcsum"><span class="tag">всего: %d</span> <span class="st-ok">доступны: %d</span> <span class="st-bad">ошибки: %d</span> '
                   '<span class="st-unk">не проверено: %d</span></p>') % (len(self.sources), ok, bad, unk)
        inner = (summary + '<div class="toolbar"><input type="search" data-filter-table="src-table" placeholder="Фильтр источников…" aria-label="Фильтр источников"></div>'
                 '<div class="tbl tall"><table id="src-table" class="data sortable src"><thead><tr><th>ID</th><th>URL</th><th>Название</th><th>Проверено</th>'
                 "<th>Для чего</th><th>Статус</th><th>Примечание</th></tr></thead><tbody>" + trs + "</tbody></table></div>")
        self.add("sources", "Источники", self.section("sources", "Источники <span class=\"muted\">(%d)</span>" % len(self.sources), self.links(inner)))

    # --- 16. вопросы владельцу
    def sec_questions(self):
        if not self.questions or not self.questions.strip():
            return
        inner = self.md(min_heading=3).render(strip_h1(self.questions))
        self.add("questions", "Вопросы владельцу", self.links('<section id="questions" class="prose"><h2>Вопросы владельцу</h2>' + inner + "</section>"))

    # --- сборка страницы
    def nav_html(self):
        out, cur = [], ""
        for sid, label, group in self.nav:
            if group != cur:
                out.append('<div class="grp">' + esc(group or "Материалы") + "</div>")
                cur = group
            out.append('<a href="#' + sid + '" data-sec="' + sid + '"' + (' class="sub"' if group else "") + ">" + esc(label) + "</a>")
        return "".join(out)

    def meta_js(self):
        return {
            "date": self.date,
            "title": self.page_title(),
            "labels": {"category": CAT_LABELS, "horizon": HORIZON_LABELS, "horizon_short": HORIZON_SHORT, "quadrant": QUADRANT_LABELS,
                       "label": LABEL_LABELS, "kano": KANO_LABELS, "moscow": MOSCOW_LABELS, "evidence": EVIDENCE_LABELS,
                       "risk": RISK_LABELS, "score": SCORE_LABELS, "metric": METRIC_LABELS, "comp_type": COMP_TYPE_LABELS},
            "dims": {k: [m["w"], m["h"]] for k, m in self.img.meta.items() if m.get("w") and m.get("h")},
            "comp_features": getattr(self, "comp_features", []),
            "subscales": SUBSCALES,
        }

    def assemble(self):
        title = self.page_title()
        who, cp = self.author_line()
        rows = [{k: v for k, v in r.items()} for r in self.rows]
        data_blocks = [
            json_script("d-meta", self.meta_js()),
            json_script("d-registry", rows),
            json_script("d-metrics", self.metrics_def() if self.rows else []),
            json_script("d-refs", getattr(self, "refs_js", {})),
            json_script("d-gantt", getattr(self, "gantt_js", [])),
            json_script("d-kanban", [dict(c) for c in self.kanban_cards]),
            json_script("d-flows", getattr(self, "flow_nodes", {})),
            json_script("d-comp", getattr(self, "comp_js", [])),
            json_script("d-img", self.img.map),
        ]
        js = JS
        head_js = HEAD_JS
        h1 = base64.b64encode(hashlib.sha256(js.encode("utf-8")).digest()).decode()
        h2 = base64.b64encode(hashlib.sha256(head_js.encode("utf-8")).digest()).decode()
        csp = ("default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'sha256-" + h1 + "' 'sha256-" + h2 + "'; "
               "font-src data:; connect-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; "
               "base-uri 'none'; form-action 'none'")
        metas = '<meta name="generator" content="product-strategy build_html.py">'
        if who:
            metas += '<meta name="author" content="' + esc(who) + '">'
        if cp:
            metas += '<meta name="copyright" content="' + esc(cp) + '">'
        foot = '<footer class="copy">'
        if cp or who:
            foot += "<p>" + esc(cp or ("© " + self.date[:4] + " " + who)) + (" · автор: " + esc(who) if who else "") + ". Все права защищены.</p>"
        foot += ("<p class=\"muted\">Страница собрана " + esc(self.date) + " скриптом product-strategy build_html.py; работает офлайн, "
                 "без внешних запросов. Концепты и макеты — не существующие функции; цифры помечены [факт]/[оценка]/[допущение].</p></footer>")
        nav = ('<nav class="side" id="nav" aria-label="Разделы"><div class="here"><small>Вы здесь</small><b class="here-t">Резюме</b></div>'
               + self.nav_html() + '<div class="grp">Вид</div><button type="button" class="theme-btn" data-theme-btn>Тема: авто</button>'
               + ('<div class="grp">Автор</div><div class="nav-author">' + esc(who) + ("<br>" + esc(cp) if cp else "") + "</div>" if who else "")
               + "</nav>")
        mbar = ('<header class="mbar"><button type="button" id="navtoggle" aria-controls="nav" aria-expanded="false">☰ Разделы</button>'
                '<span class="here-t">Резюме</span><button type="button" class="theme-btn" data-theme-btn>Тема</button></header>')
        layers = (
            '<div id="pm" class="layer modal" role="dialog" aria-modal="true" aria-labelledby="pmtitle" aria-hidden="true"><div class="mbox">'
            '<div class="mhead"><button type="button" id="pmback" class="ghost" hidden title="Назад к предыдущей карточке">←</button>'
            '<div class="mtitle" id="pmtitle"></div><button type="button" id="pm-reg">Показать в реестре</button>'
            '<button type="button" data-close data-autofocus aria-label="Закрыть (Esc)">✕</button></div><div class="mchips" id="pmchips"></div>'
            '<div class="mbody" id="pmbody"></div></div></div>'
            '<div id="im" class="layer modal" role="dialog" aria-modal="true" aria-labelledby="imtitle" aria-hidden="true"><div class="mbox">'
            '<div class="mhead"><div class="mtitle" id="imtitle"></div><button type="button" data-close data-autofocus aria-label="Закрыть (Esc)">✕</button></div>'
            '<div class="mbody" id="imbody"></div></div></div>'
            '<div id="lb" class="layer" role="dialog" aria-modal="true" aria-label="Просмотр картинки" aria-hidden="true"><div id="lbbar">'
            '<button type="button" id="lbprev" title="Предыдущая (←)" aria-label="Предыдущая">‹</button><button type="button" id="lbnext" title="Следующая (→)" aria-label="Следующая">›</button>'
            '<span id="lbcount"></span><span id="lbcap"></span><button type="button" data-z="fit" class="on">Вписать</button><button type="button" data-z="1">1:1</button>'
            '<button type="button" data-z="2">2×</button><button type="button" id="lbhs" title="Показать/скрыть элементы (H)">Элементы</button>'
            '<button type="button" data-close data-autofocus title="Закрыть (Esc)">✕ Закрыть</button></div><div id="lbview"><div id="lbwrap"><img id="lbimg" alt=""></div></div>'
            '<aside id="lbside" aria-label="Описание элементов"></aside><div class="lbhint">клик — 1:1 / вписать · Ctrl+колесо — масштаб · перетаскивание · ←/→ · H — элементы · Esc</div></div>')
        page = ("<!doctype html>\n<html lang=\"ru\"><head><meta charset=\"utf-8\">"
                '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
                '<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light dark">'
                + metas + '<link rel="icon" href="data:,"><title>' + esc(title) + "</title><style>" + theme_css(self.tokens) + CSS + "</style>"
                "<script>" + head_js + "</script></head><body>"
                '<a class="skip" href="#main">К содержанию</a>' + mbar + '<div class="wrap">' + nav + '<main id="main">'
                + "".join(self.sections) + foot + "</main></div>" + layers + "".join(data_blocks) + "<script>" + js + "</script></body></html>\n")
        return page


# ---------------------------------------------------------------- CSS
CSS = r"""
*,*::before,*::after{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:16px;-webkit-text-size-adjust:100%}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
html.locked,html.locked body{overflow:hidden}
body{margin:0;background:var(--ps-bg);color:var(--ps-text);font:15px/1.6 var(--ps-font);overflow-x:hidden}
a{color:var(--ps-link);text-underline-offset:2px}
a:hover{text-decoration-thickness:2px}
:focus-visible{outline:2px solid var(--ps-accent);outline-offset:2px}
code{font:12.5px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--ps-surface-2);padding:1px 5px;border-radius:5px;overflow-wrap:anywhere}
pre{background:var(--ps-surface-2);padding:12px 14px;border-radius:10px;overflow:auto;max-width:100%}
pre code{background:none;padding:0}
.skip{position:absolute;left:-9999px;top:0}.skip:focus{left:8px;top:8px;z-index:3000;background:var(--ps-surface);padding:6px 10px;border-radius:6px}
.muted{color:var(--ps-muted)}.small{font-size:12.5px}
.wrap{display:grid;grid-template-columns:270px minmax(0,1fr);min-height:100vh}
main{min-width:0;padding:28px 44px 80px;max-width:1280px;width:100%}
nav.side{position:sticky;top:0;height:100vh;overflow-y:auto;overflow-x:hidden;background:var(--ps-surface);border-right:1px solid var(--ps-border);padding:0 10px 28px;font-size:13px}
nav.side .here{position:sticky;top:0;z-index:2;background:var(--ps-surface);margin:0 -10px 8px;padding:14px 18px 10px;border-bottom:1px solid var(--ps-border)}
nav.side .here small{display:block;color:var(--ps-muted);font-size:10.5px;text-transform:uppercase;letter-spacing:.08em}
nav.side .here b{display:block;font-weight:600;line-height:1.3;font-size:13.5px}
nav.side a{display:block;padding:5px 10px;border-radius:7px;color:var(--ps-muted);text-decoration:none;border-left:3px solid transparent;line-height:1.3;overflow-wrap:anywhere}
nav.side a.sub{padding-left:16px;font-size:12.5px}
nav.side a:hover{background:var(--ps-surface-2);color:var(--ps-text)}
nav.side a.active{background:var(--ps-accent-soft);color:var(--ps-text);border-left-color:var(--ps-accent);font-weight:600}
nav.side .grp{margin:14px 10px 4px;font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--ps-muted)}
nav.side .theme-btn{margin:2px 8px;font-size:12.5px}
.nav-author{padding:0 10px;font-size:12px;color:var(--ps-muted);line-height:1.45}
.mbar{display:none}
h1{font-size:30px;line-height:1.2;margin:4px 0 10px;letter-spacing:-.01em}
h2{font-size:23px;line-height:1.25;margin:48px 0 12px;padding-top:18px;border-top:1px solid var(--ps-border)}
h3{font-size:17px;line-height:1.3;margin:26px 0 8px}
h4{font-size:14.5px;margin:16px 0 6px}
.top h1{margin-top:2px}
.eyebrow{margin:0;color:var(--ps-muted);font-size:12.5px;text-transform:uppercase;letter-spacing:.08em}
.author{margin:0 0 12px;color:var(--ps-muted)}
.author b{color:var(--ps-text)}
.facts{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 16px;margin:14px 0;font-size:14px}
.facts dt{color:var(--ps-muted)}.facts dd{margin:0;overflow-wrap:anywhere}
.lead{color:var(--ps-muted);max-width:860px}
.hint{font-size:13px;margin-top:18px}
.prose{max-width:900px}
.prose p,.prose li{overflow-wrap:break-word}
.prose li{margin:3px 0}.prose li>p{margin:4px 0}
.prose blockquote{margin:12px 0;padding:6px 14px;border-left:3px solid var(--ps-accent);background:var(--ps-surface);border-radius:0 8px 8px 0;color:var(--ps-muted)}
.prose hr{border:0;border-top:1px solid var(--ps-border);margin:24px 0}
li.task{list-style:none;margin-left:-18px}
.tbl{overflow-x:auto;margin:12px 0;border:1px solid var(--ps-border);border-radius:10px;background:var(--ps-surface);max-width:100%}
.tbl.tall{max-height:70vh;overflow:auto}
.tbl table{border-collapse:collapse;width:100%;font-size:13.5px}
.tbl th,.tbl td{padding:7px 10px;text-align:left;vertical-align:top;border-bottom:1px solid var(--ps-border)}
.tbl thead th{background:var(--ps-surface-2);font-weight:600;white-space:nowrap;position:sticky;top:0}
.tbl tbody tr:last-child td{border-bottom:0}
.al-c{text-align:center!important}.al-r{text-align:right!important}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.url{word-break:break-all;min-width:180px}
table.sortable th{cursor:pointer;user-select:none}
table.sortable th[aria-sort=ascending]::after{content:" ▲";font-size:10px}
table.sortable th[aria-sort=descending]::after{content:" ▼";font-size:10px}
.tag{display:inline-block;font-size:11.5px;line-height:1.5;padding:0 8px;border-radius:999px;border:1px solid var(--ps-border);color:var(--ps-muted);background:var(--ps-surface);white-space:nowrap;margin:1px 2px 1px 0;vertical-align:baseline}
.b{display:inline-block;font-size:11.5px;font-weight:600;line-height:1.55;padding:0 7px;border-radius:6px;color:#fff;background:#5b6170;white-space:nowrap}
.b-P0{background:#b42318}.b-P1{background:#a15c07}.b-P2{background:#1d4ed8}.b-P3{background:#5b6170}
.b-A{background:#15803d}.b-B{background:#4d7c0f}.b-C{background:#a15c07}.b-D{background:#b42318}
.b-quick_win{background:#15803d}.b-big_bet{background:#6d28d9}.b-filler{background:#5b6170}.b-money_pit{background:#b42318}
.risk{display:inline-block;min-width:22px;text-align:center;border-radius:6px;padding:0 6px;font-weight:600;font-size:12px;color:#fff;background:#5b6170}
.risk.r1{background:#15803d}.risk.r2{background:#4d7c0f}.risk.r3{background:#a15c07}.risk.r4{background:#c2410c}.risk.r5{background:#b42318}
.badge-concept{display:inline-block;font-size:11px;font-weight:600;padding:0 7px;border-radius:6px;background:#b42318;color:#fff;white-space:nowrap}
a.pid{font-weight:600;text-decoration:none;border-bottom:1px dotted currentColor;white-space:nowrap}
a.pid:hover{border-bottom-style:solid}
a.emb{font-weight:500}
.missing{border:1px dashed var(--ps-border);border-radius:8px;padding:8px 12px;color:var(--ps-muted);font-size:13px;background:var(--ps-surface)}
span.missing{padding:1px 6px}
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,168px),1fr));gap:12px;margin:18px 0}
.kpi{background:var(--ps-surface);border:1px solid var(--ps-border);border-radius:var(--ps-radius);padding:12px 14px}
.kpi .n{font-size:26px;font-weight:650;line-height:1.1;color:var(--ps-accent-text);font-variant-numeric:tabular-nums}
.kpi .l{font-size:12.5px;color:var(--ps-text);margin-top:4px;line-height:1.3}
.kpi .s{font-size:11.5px;color:var(--ps-muted);margin-top:2px}
details{margin:10px 0}
summary{cursor:pointer;color:var(--ps-link);font-weight:500}
figure{margin:16px 0}
figure img{display:block;max-width:100%;height:auto;border:1px solid var(--ps-border);border-radius:8px;background:#fff}
figcaption{font-size:12.5px;color:var(--ps-muted);margin-top:6px;line-height:1.45}
.lb{cursor:zoom-in}
figure.lb:hover img,figure.lb:focus-visible img{border-color:var(--ps-accent);box-shadow:0 0 0 3px var(--ps-accent-soft)}
.zoom{float:right;font-size:11.5px;color:var(--ps-link);margin-left:8px}
figure.mobile img{max-height:540px;width:auto;margin:0 auto}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,340px),1fr));gap:18px;align-items:start}
.gallery figure{margin:0}
.gallery.charts{grid-template-columns:repeat(auto-fill,minmax(min(100%,560px),1fr))}
.ph{border:1px dashed var(--ps-border);border-radius:10px;padding:16px;background:var(--ps-surface);font-size:13px;color:var(--ps-muted)}
.ph .ph-t{font-weight:600;color:var(--ps-text);margin-bottom:6px}
.linkbtn{background:none;border:0;padding:0;color:var(--ps-link);font-size:inherit;cursor:pointer;text-decoration:underline;text-underline-offset:2px}
input,select,button{font:inherit;font-size:13.5px;color:var(--ps-text);background:var(--ps-surface);border:1px solid var(--ps-border);border-radius:8px;padding:6px 10px;max-width:100%}
button{cursor:pointer}
button:hover{border-color:var(--ps-accent)}
input[type=checkbox]{padding:0;vertical-align:-2px;margin:0 4px 0 0}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0}
.toolbar input[type=search]{flex:1 1 260px;min-width:0}
.toolbar .lbl{display:inline-flex;align-items:center;gap:6px;color:var(--ps-muted);font-size:13px;max-width:100%}
.toolbar .lbl select{min-width:0}
.toolbar .chk{font-size:13px;white-space:nowrap}
.count{color:var(--ps-muted);font-size:13px}
.spacer{flex:1}
.reg-wrap{overflow:auto;max-height:76vh;border:1px solid var(--ps-border);border-radius:10px;background:var(--ps-surface)}
table.reg{border-collapse:separate;border-spacing:0;width:100%;font-size:13px}
table.reg th,table.reg td{padding:7px 8px;text-align:left;vertical-align:top;border-bottom:1px solid var(--ps-border)}
table.reg thead th{position:sticky;top:0;z-index:2;background:var(--ps-surface-2);cursor:pointer;user-select:none;white-space:nowrap}
table.reg thead th:hover{color:var(--ps-link)}
table.reg th[aria-sort=ascending]::after{content:" ▲";font-size:10px}
table.reg th[aria-sort=descending]::after{content:" ▼";font-size:10px}
table.reg th.extra{color:var(--ps-link)}
table.reg tr.row{cursor:pointer}
table.reg tr.row:hover>td{background:var(--ps-accent-soft)}
table.reg tr.row.open>td{background:var(--ps-surface-2)}
table.reg td.c-title{min-width:240px}
table.reg td.c-title b{font-weight:600}
tr.detail>td{background:var(--ps-surface-2);padding:6px 16px 16px}
tr.flash>td{animation:flash 2s}
@keyframes flash{0%,55%{background:var(--ps-accent-soft)}100%{background:transparent}}
.detail{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:0 28px;font-size:13.5px}
.dsec{min-width:0}
.dsec.wide{grid-column:1/-1}
.dsec h4{margin:12px 0 4px;font-size:11.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--ps-muted)}
.dsec ul,.dsec ol{margin:4px 0;padding-left:20px}.dsec li{margin:3px 0}
dl.kv{display:grid;grid-template-columns:minmax(96px,max-content) minmax(0,1fr);gap:4px 12px;margin:4px 0}
dl.kv dt{color:var(--ps-muted)}dl.kv dd{margin:0;min-width:0;overflow-wrap:anywhere}
.concepts{display:flex;flex-wrap:wrap;gap:12px}
.concepts figure{margin:0;width:260px;max-width:100%}
.concepts figure.mobile{width:140px}
.concepts .ph{width:260px;max-width:100%}
.quads{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.quad{background:var(--ps-surface);border:1px solid var(--ps-border);border-radius:var(--ps-radius);padding:12px 14px;min-width:0}
.quad .qh{display:flex;align-items:center;gap:8px;font-size:15px}
.quad .qd{font-size:12px;margin:2px 0 6px}
.quad ol{margin:0;padding-left:20px;font-size:13px}.quad li{margin:2px 0;overflow-wrap:anywhere}
.dists{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,260px),1fr));gap:12px 24px}
.bars h4{margin:6px 0}
.brow{display:grid;grid-template-columns:minmax(80px,40%) minmax(0,1fr) 34px;gap:8px;align-items:center;font-size:13px;margin:3px 0}
.bt{display:block;height:10px;background:var(--ps-surface-2);border-radius:5px;overflow:hidden}
.bv{display:block;height:100%;background:var(--ps-accent);border-radius:5px}
.bn{text-align:right;font-variant-numeric:tabular-nums}
.tornado td.tor{min-width:200px;white-space:nowrap}
.tor .tl,.tor .th{display:inline-flex;width:50%;height:10px;vertical-align:middle}
.tor .tl{justify-content:flex-end;border-right:1px solid var(--ps-muted)}
.tor .tl span{background:#4C78A8;height:100%;display:block}
.tor .th span{background:#F58518;height:100%;display:block}
.flow{background:var(--ps-surface);border:1px solid var(--ps-border);border-radius:var(--ps-radius);padding:12px 16px;margin:16px 0}
.flow h3{margin:4px 0 10px}
.flowsvg{background:#fff;border-radius:8px;padding:8px;overflow:auto;max-width:100%;color:#111}
.flowsvg svg.flow-svg{display:block;width:100%;height:auto;max-height:78vh;margin:0 auto;font-family:var(--ps-font)}
.flowsvg .fnode{cursor:pointer;transition:opacity .15s}
.flowsvg text:not(.fnode),.flowsvg tspan{pointer-events:none}
.flowsvg .fnode:hover,.flowsvg .fnode:focus{opacity:.78;outline:none}
.flowsvg .fnode.on{stroke:#111;stroke-width:3}
.nchips{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:13px}
.nchip{font-size:12.5px;padding:3px 10px;border-radius:999px}
.gantt{overflow-x:auto;border:1px solid var(--ps-border);border-radius:10px;background:var(--ps-surface)}
.gin{min-width:860px}
.ghead,.grow{display:grid;grid-template-columns:280px minmax(0,1fr)}
.ghead{position:sticky;top:0;z-index:1;background:var(--ps-surface-2);border-bottom:1px solid var(--ps-border);font-size:11.5px;color:var(--ps-muted)}
.ghead .gl{padding:8px 10px;font-weight:600}
.gscale{position:relative;height:34px}
.gscale span{position:absolute;top:0;bottom:0;border-left:1px solid var(--ps-border);padding:8px 3px 0;white-space:nowrap;overflow:hidden}
.gscale span.yr{background:repeating-linear-gradient(135deg,transparent 0 6px,var(--ps-accent-soft) 6px 8px);color:var(--ps-text);font-weight:600}
.gphase{display:flex;align-items:center;gap:8px;padding:6px 10px;font-weight:600;font-size:13px;background:var(--ps-surface-2);border-bottom:1px solid var(--ps-border)}
.gdot{width:10px;height:10px;border-radius:3px;display:inline-block}
.grow{border-bottom:1px solid var(--ps-border);cursor:pointer}
.grow:hover,.grow:focus-visible{background:var(--ps-accent-soft)}
.glabel{padding:6px 10px;font-size:13px;line-height:1.35;min-width:0;overflow-wrap:anywhere}
.gid{font:11px ui-monospace,Menlo,monospace;color:var(--ps-muted)}
.gtrack{position:relative;min-height:32px}
.gbar{position:absolute;top:9px;height:14px;border-radius:4px;opacity:.92}
.gbar.vis{background-image:repeating-linear-gradient(135deg,rgba(255,255,255,.35) 0 4px,transparent 4px 8px)}
.gms{position:absolute;top:9px;width:14px;height:14px;transform:translateX(-50%) rotate(45deg);border-radius:2px}
.gsep{position:absolute;top:0;bottom:0;border-left:2px dashed var(--ps-border)}
.c0{background:#4C78A8}.c1{background:#F58518}.c2{background:#54A24B}.c3{background:#B279A2}.c4{background:#E45756}.c5{background:#72B7B2}.c6{background:#9D755D}.c7{background:#EECA3B}
.kanban{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(230px,1fr);gap:12px;overflow-x:auto;padding-bottom:8px}
.kcol{background:var(--ps-surface-2);border:1px solid var(--ps-border);border-radius:var(--ps-radius);padding:8px;min-height:120px;min-width:0}
.khead{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:2px 4px 8px;font-size:13.5px}
.kcount{font-size:12px;color:var(--ps-muted);background:var(--ps-surface);border:1px solid var(--ps-border);border-radius:999px;padding:0 8px;white-space:nowrap}
.kcount.over{background:#b42318;color:#fff;border-color:#b42318}
.kcard{background:var(--ps-surface);border:1px solid var(--ps-border);border-radius:9px;padding:8px 10px;margin-bottom:8px;font-size:13px;cursor:pointer}
.kcard:hover,.kcard:focus-visible{border-color:var(--ps-accent)}
.kid{font:11.5px ui-monospace,Menlo,monospace;color:var(--ps-muted)}
.kt{font-weight:600;line-height:1.3;margin:2px 0 4px;overflow-wrap:anywhere}
.kmeta{font-size:12px}
.kempty{font-size:12.5px;padding:8px}
.ref{display:grid;grid-template-columns:minmax(0,360px) minmax(0,1fr);gap:18px;background:var(--ps-surface);border:1px solid var(--ps-border);border-radius:var(--ps-radius);padding:14px;margin:14px 0}
.ref figure{margin:0}
.ref h3{margin:0 0 4px}
.ref .meta{font-size:12.5px;color:var(--ps-muted);margin:0 0 8px}
.ref p{margin:6px 0}
.hslist{padding-left:0;list-style:none;margin:6px 0}.hslist li{margin:4px 0}
.hsn{display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:20px;border-radius:50%;background:#ffcc33;color:#111;font-size:11px;font-weight:700;margin-right:6px;padding:0 4px}
.st{font-size:10.5px;border-radius:999px;padding:0 6px;border:1px solid var(--ps-border);color:var(--ps-muted);margin-left:4px}
.st-new{color:#15803d;border-color:#15803d}
.cgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,460px),1fr));gap:14px;margin-top:12px}
.ccard{background:var(--ps-surface);border:1px solid var(--ps-border);border-radius:var(--ps-radius);padding:12px 14px;display:grid;grid-template-columns:170px minmax(0,1fr);gap:12px;font-size:13px;min-width:0}
.ccard.noimg{grid-template-columns:minmax(0,1fr)}
.ccard figure{margin:0}
.ccard figure img{width:100%;aspect-ratio:16/10;object-fit:cover;object-position:top}
.ccard .noshot{border:1px dashed var(--ps-border);border-radius:8px;aspect-ratio:16/10;display:flex;align-items:center;justify-content:center;text-align:center;color:var(--ps-muted);font-size:11.5px;padding:6px}
.ccard h4{margin:0 0 2px;font-size:15px}
.ccard .cmeta{color:var(--ps-muted);font-size:12px;margin-bottom:4px}
.ccard .lblh{font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--ps-muted);margin-top:6px}
.ccard ul{margin:2px 0;padding-left:18px}
.ccard .them li::marker{color:#b42318}.ccard .us li::marker{color:#15803d}.ccard .best li::marker{color:#a15c07}
.cmatrix{overflow:auto;max-height:70vh;border:1px solid var(--ps-border);border-radius:10px;background:var(--ps-surface)}
table.cm{border-collapse:separate;border-spacing:0;font-size:12.5px;width:100%}
table.cm th,table.cm td{padding:5px 8px;border-bottom:1px solid var(--ps-border);text-align:center;white-space:nowrap}
table.cm thead th{position:sticky;top:0;background:var(--ps-surface-2);z-index:2;white-space:normal;min-width:72px;vertical-align:bottom}
table.cm th[scope=row]{position:sticky;left:0;background:var(--ps-surface);text-align:left;z-index:1;max-width:220px;overflow:hidden;text-overflow:ellipsis}
table.cm thead th:first-child{left:0;z-index:3}
table.cm tr.self th,table.cm tr.self td{background:var(--ps-accent-soft);font-weight:600}
table.cm td.y{color:#15803d;font-weight:700}table.cm td.n{color:var(--ps-muted)}table.cm td.u{color:var(--ps-muted)}
table.cm td.gap{outline:2px solid #b42318;outline-offset:-3px}
table.cm tfoot th,table.cm tfoot td,table.cm tfoot th[scope=row]{background:var(--ps-surface-2);font-weight:600}
.st-ok,.st-bad,.st-unk,.ok{display:inline-block;font-size:12px;padding:0 7px;border-radius:999px;white-space:nowrap}
.st-ok,.ok{background:rgba(21,128,61,.14);color:#15803d}.st-bad{background:rgba(180,35,24,.14);color:#b42318}.st-unk{background:var(--ps-surface-2);color:var(--ps-muted)}
:root[data-theme=dark] .st-ok,:root[data-theme=dark] .ok{color:#4ade80}:root[data-theme=dark] .st-bad{color:#f87171}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]) .st-ok,:root:not([data-theme=light]) .ok{color:#4ade80}:root:not([data-theme=light]) .st-bad{color:#f87171}:root:not([data-theme=light]) table.cm td.y{color:#4ade80}}
:root[data-theme=dark] table.cm td.y{color:#4ade80}
footer.copy{margin-top:56px;padding-top:14px;border-top:1px solid var(--ps-border);font-size:12.5px}
footer.copy p{margin:4px 0}
.modal{position:fixed;inset:0;display:none;justify-content:center;align-items:flex-start;overflow:auto;padding:40px 16px;background:rgba(12,14,18,.58)}
.modal.open{display:flex}
.mbox{width:min(1100px,100%);background:var(--ps-surface);color:var(--ps-text);border:1px solid var(--ps-border);border-radius:14px;box-shadow:0 24px 70px rgba(0,0,0,.35);margin-bottom:40px}
.mhead{position:sticky;top:-40px;z-index:3;display:flex;flex-wrap:wrap;align-items:flex-start;gap:8px;padding:14px 18px;background:var(--ps-surface);border-bottom:1px solid var(--ps-border);border-radius:14px 14px 0 0}
.mtitle{flex:1 1 260px;min-width:0;font-size:17px;font-weight:600;line-height:1.35;overflow-wrap:break-word}
.mhead button{flex:none}
.mchips{padding:10px 18px 0;display:flex;flex-wrap:wrap;gap:4px;align-items:center}
.mchips:empty{display:none}
.mbody{padding:10px 18px 20px;font-size:14px}
.mbody ul,.mbody ol{padding-left:20px}
button.ghost{background:none}
#lb{position:fixed;inset:0;display:none;grid-template-columns:minmax(0,1fr) 340px;grid-template-rows:auto minmax(0,1fr);background:rgba(12,12,14,.97);color:#ececec}
#lb.open{display:grid}
#lb.nopanel{grid-template-columns:minmax(0,1fr)}#lb.nopanel #lbside{display:none}
#lbbar{grid-column:1/-1;display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:8px 12px;background:#1b1b1f;border-bottom:1px solid #34343a}
#lbbar button{background:#2b2b31;color:#f2f2f2;border:1px solid #4a4a52;padding:5px 10px;border-radius:7px;font-size:13px}
#lbbar button:hover{border-color:#bbb}
#lbbar button.on{background:#f2f2f2;color:#111;border-color:#f2f2f2}
#lbbar button:disabled{opacity:.4;cursor:default}
#lbcount{font-size:12.5px;color:#aaa;font-variant-numeric:tabular-nums}
#lbcap{flex:1 1 180px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}
#lbview{position:relative;overflow:auto;cursor:grab;min-height:0}
#lbview.drag{cursor:grabbing}
#lbwrap{position:relative;width:fit-content;margin:16px auto}
#lbwrap img{display:block;max-width:none;background:#fff;user-select:none;-webkit-user-drag:none}
#lbwrap .pin{position:absolute;min-width:26px;height:26px;margin:-13px 0 0 -13px;padding:0 5px;border-radius:13px;background:#ffcc33;color:#111;font-weight:700;font-size:12px;display:flex;align-items:center;justify-content:center;border:2px solid #111;box-shadow:0 2px 8px rgba(0,0,0,.6);cursor:pointer;z-index:3}
#lbwrap .pin.on{background:#fff;transform:scale(1.18)}
#lbwrap .hsbox{position:absolute;border:1px dashed rgba(255,204,51,.7);border-radius:6px;cursor:pointer;z-index:1}
#lbwrap .hsbox:hover{background:rgba(255,204,51,.14)}
#lbwrap .hsel{position:absolute;border:2px solid #ffcc33;border-radius:6px;box-shadow:0 0 0 4000px rgba(0,0,0,.38);display:none;pointer-events:none;z-index:2}
#lbwrap .hsel.on{display:block}
#lb.nohs .pin,#lb.nohs .hsbox,#lb.nohs .hsel{display:none!important}
#lbside{overflow:auto;background:#17171a;border-left:1px solid #34343a;padding:14px;font-size:13px;min-height:0}
#lbside h3{margin:0 0 6px;font-size:15px}
#lbside .meta{color:#a8a8b0;font-size:12px;margin-bottom:8px}
#lbside a{color:#9cc3ff}
#lbside .hsitem{display:grid;grid-template-columns:26px minmax(0,1fr);gap:8px;padding:6px;border-radius:8px;cursor:pointer;border:1px solid transparent}
#lbside .hsitem:hover,#lbside .hsitem.on{background:rgba(255,255,255,.07);border-color:#5a5a62}
#lbside .hsitem b{display:block;color:#fff}
#lbside .hsitem .hsn{margin:0}
#lbside .tag{background:transparent;color:#ccc;border-color:#555}
#lbside .st{color:#bbb;border-color:#555}
#lbside ul{padding-left:18px}
.lbhint{position:absolute;right:12px;bottom:8px;font-size:11px;color:#9a9aa2;pointer-events:none}
@media (max-width:900px){
  html{scroll-padding-top:58px}
  .mbar{display:flex;position:sticky;top:0;z-index:600;align-items:center;gap:8px;padding:8px 12px;background:var(--ps-surface);border-bottom:1px solid var(--ps-border);height:50px}
  .mbar .here-t{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13.5px;font-weight:600}
  .mbar button{font-size:13px;padding:5px 9px;white-space:nowrap}
  .wrap{grid-template-columns:minmax(0,1fr)}
  nav.side{position:fixed;top:50px;left:0;right:0;bottom:0;height:auto;z-index:590;display:none;border-right:0;padding-bottom:40px}
  body.nav-open nav.side{display:block}
  nav.side .here{display:none}
  main{padding:16px 16px 64px}
  h1{font-size:24px}h2{font-size:20px;margin-top:36px}
  .ref{grid-template-columns:minmax(0,1fr)}
  .ccard{grid-template-columns:minmax(0,1fr)}
  .quads{grid-template-columns:minmax(0,1fr)}
  .ghead,.grow{grid-template-columns:150px minmax(0,1fr)}
  .gin{min-width:680px}
  #lb{grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr) 36vh}
  #lb.nopanel{grid-template-rows:auto minmax(0,1fr)}
  #lbside{border-left:0;border-top:1px solid #34343a}
  .lbhint{display:none}
  .modal{padding:12px 8px}
  .mhead{top:-12px;padding:12px}
  .mbody{padding:10px 12px 16px}
  .facts{gap:4px 12px}
}
@media print{
  nav.side,.mbar,.toolbar,.layer,.zoom,.skip,.lbhint,button,.hint,noscript{display:none!important}
  body{background:#fff;color:#000;font-size:11pt}
  .wrap{display:block}main{padding:0;max-width:none}
  .reg-wrap,.cmatrix,.tbl,.tbl.tall,.gantt,.kanban,.flowsvg{max-height:none!important;overflow:visible!important}
  table.reg thead th,.tbl thead th,table.cm thead th,table.cm th[scope=row]{position:static}
  .gin{min-width:0}.kanban{display:block}.kcol{margin-bottom:8px}
  figure,.kpi,.ref,.ccard,.flow,.quad,tr,.kcard{break-inside:avoid}
  h2,h3{break-after:avoid}
  a{color:inherit;text-decoration:none}
  h2{border-top:1px solid #999}
}
"""

# ---------------------------------------------------------------- JS
HEAD_JS = "try{var t=localStorage.getItem('ps-theme');if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t)}catch(e){}"

JS = r"""
(function () {
'use strict';
var $ = function (s, r) { return (r || document).querySelector(s); };
var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
function J(id) { var el = document.getElementById(id); if (!el) return null; try { return JSON.parse(el.textContent); } catch (e) { console.error('JSON ' + id + ': ' + e); return null; } }
function safe(name, fn) { try { fn(); } catch (e) { console.error('[' + name + '] ' + (e && e.stack || e)); } }
var IMG = J('d-img') || {}, META = J('d-meta') || {}, REG = J('d-registry') || [], METRICS = J('d-metrics') || [];
var REFS = J('d-refs') || {}, GANTT = J('d-gantt') || [], KAN = J('d-kanban') || [], NODES = J('d-flows') || {}, COMP = J('d-comp') || [];
var L = META.labels || {}, DIMS = META.dims || {};
var BYID = {}; REG.forEach(function (r) { BYID[r.id] = r; });
var MET = {}; METRICS.forEach(function (m) { MET[m.k] = m; });
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
function safeUrl(u) { u = String(u == null ? '' : u).trim(); if (!u) return ''; var l = u.replace(/[\u0000-\u0020]/g, '').toLowerCase(); if (/^(https?:|mailto:|#)/.test(l)) return u; if (/^[a-z][a-z0-9+.\-]*:/.test(l) || l.indexOf('//') === 0) return ''; return u; }
function link(u, text) { var s = safeUrl(u); var t = esc(text == null || text === '' ? u : text); return s ? '<a href="' + esc(s) + '" target="_blank" rel="noopener noreferrer">' + t + '</a>' : t; }
function lab(g, v) { return (L[g] && L[g][v]) || (v == null ? '' : String(v)); }
function txt(v) { if (v == null) return ''; if (typeof v === 'boolean') return v ? 'да' : 'нет'; if (typeof v === 'number') return fmt(v); if (Array.isArray(v)) return v.map(txt).join('; '); if (typeof v === 'object') { if ('min' in v && 'max' in v) return money(v); if ('value' in v) return txt(v.value) + (v.label ? ' [' + v.label + ']' : ''); return Object.keys(v).map(function (k) { return k + ': ' + txt(v[k]); }).join('; '); } return String(v); }
function fmt(v) { if (v == null || v === '') return ''; if (typeof v !== 'number') return String(v); if (!isFinite(v)) return '—'; if (Number.isInteger(v)) return v.toLocaleString('ru-RU'); return v.toLocaleString('ru-RU', { maximumFractionDigits: Math.abs(v) < 10 ? 2 : 1 }); }
function money(c) { if (!c || typeof c !== 'object') return txt(c); var lo = c.min, hi = c.max, s = ''; if (lo == null && hi == null) s = ''; else if (lo === hi || hi == null) s = fmt(lo); else if (lo == null) s = 'до ' + fmt(hi); else s = fmt(lo) + '–' + fmt(hi); s = (s + ' ' + (c.currency || '')).trim(); if (c.note) s += ' (' + c.note + ')'; return s; }
function norm(s) { return String(s || '').toLowerCase().replace(/ё/g, 'е').trim(); }
function badge(kind, v) { if (!v) return ''; var t = kind === 'q' ? lab('quadrant', v) : v; return '<span class="b b-' + esc(String(v).replace(/[^\w-]/g, '-')) + '">' + esc(t) + '</span>'; }
function tag(t, cls) { return t === '' || t == null ? '' : '<span class="tag' + (cls ? ' ' + cls : '') + '">' + esc(t) + '</span>'; }
function pidLink(id) { var r = BYID[id]; if (!r) return esc(id); return '<a class="pid" href="#p=' + esc(id) + '" data-pid="' + esc(id) + '" title="' + esc(id + ' — ' + r.title) + '">' + esc(id) + '</a>'; }
function plist(ids) { return (ids || []).map(function (id) { var r = BYID[id]; return '<li>' + pidLink(id) + (r ? ' ' + esc(r.title) + ' ' + badge('p', r.priority) + ' ' + badge('q', r.quadrant) : ' <span class="muted">(нет в реестре)</span>') + '</li>'; }).join(''); }
function fillImgs(root) { $$('img[data-img]', root).forEach(function (im) { if (!im.getAttribute('src')) { var u = IMG[im.getAttribute('data-img')]; if (u) im.src = u; } }); }
var PIDRE = /(^|[^\p{L}\p{N}_-])(P\d{3})(?![\p{L}\p{N}_-])/gu;   /* без lookbehind: старые Safari */
var SKIP = { A: 1, SCRIPT: 1, STYLE: 1, TEXTAREA: 1, SELECT: 1, OPTION: 1, BUTTON: 1, TITLE: 1, INPUT: 1 };
function linkifyEl(root) {
  if (!root || !REG.length) return;
  var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: function (n) {
    if (!/P\d{3}/.test(n.nodeValue)) return NodeFilter.FILTER_REJECT;
    for (var p = n.parentNode; p && p !== root.parentNode; p = p.parentNode) { if (p.nodeType === 1 && (SKIP[p.nodeName] || p.namespaceURI === 'http://www.w3.org/2000/svg')) return NodeFilter.FILTER_REJECT; }
    return NodeFilter.FILTER_ACCEPT; } });
  var nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(function (n) {
    var t = n.nodeValue, re = new RegExp(PIDRE.source, 'gu'), m, last = 0, any = false, frag = document.createDocumentFragment();
    while ((m = re.exec(t))) { var id = m[2], at = m.index + m[1].length; if (!BYID[id]) continue; any = true; frag.appendChild(document.createTextNode(t.slice(last, at)));
      var a = document.createElement('a'); a.className = 'pid'; a.href = '#p=' + id; a.setAttribute('data-pid', id); a.title = id + ' — ' + BYID[id].title; a.textContent = id; frag.appendChild(a); last = at + id.length; }
    if (!any) return; frag.appendChild(document.createTextNode(t.slice(last))); n.parentNode.replaceChild(frag, n); });
}

/* ---------- слои: модалки и лайтбокс, Esc закрывает верхний ---------- */
var stack = [], baseHash = null;
var pm = $('#pm'), im = $('#im'), lb = $('#lb');
var LB = { items: [], idx: 0, zoom: 'fit', cur: null };
function layerHash(el) { if (el === lb) return LB.cur ? '#lb=' + encodeURIComponent(LB.cur.getAttribute('data-key')) : null; if (el === pm) return pm.getAttribute('data-id') ? '#p=' + pm.getAttribute('data-id') : null; return null; }
function syncHash() {
  try {
    var plainUrl = location.pathname + location.search;
    if (!stack.length) { if (baseHash !== null) { history.replaceState(null, '', baseHash || plainUrl); baseHash = null; } return; }
    if (baseHash === null) baseHash = /^#(lb|p)=/.test(location.hash) ? '' : location.hash;
    var h = null; for (var i = stack.length - 1; i >= 0 && !h; i--) h = layerHash(stack[i]);
    history.replaceState(null, '', h || baseHash || plainUrl);
  } catch (e) { /* file:// без history — не критично */ }
}
function restack() { stack.forEach(function (el, i) { el.style.zIndex = String(1000 + i * 10); }); document.documentElement.classList.toggle('locked', stack.length > 0); syncHash(); }
function openLayer(el) { var i = stack.indexOf(el); if (i >= 0) stack.splice(i, 1); else el._opener = document.activeElement; stack.push(el); el.classList.add('open'); el.setAttribute('aria-hidden', 'false'); restack(); var f = el.querySelector('[data-autofocus]'); if (f) { try { f.focus({ preventScroll: true }); } catch (e) {} } }
function closeLayer(el) {
  el = el || stack[stack.length - 1]; if (!el) return; var i = stack.indexOf(el); if (i < 0) return;
  stack.splice(i, 1); el.classList.remove('open'); el.setAttribute('aria-hidden', 'true');
  if (el === pm) { pm.removeAttribute('data-id'); pmHist.length = 0; }
  if (el === lb) { LB.cur = null; lbimg.removeAttribute('src'); }
  restack(); var o = el._opener; el._opener = null; if (o && o.focus && document.contains(o)) { try { o.focus({ preventScroll: true }); } catch (e) {} }
}
function closeAll() { while (stack.length) closeLayer(); }
function topLayer() { return stack[stack.length - 1] || null; }

/* ---------- карточка предложения ---------- */
var pmHist = [];
function sec(title, h, cls) { return h ? '<section class="dsec' + (cls ? ' ' + cls : '') + '"><h4>' + title + '</h4>' + h + '</section>' : ''; }
function kv(pairs) { var h = pairs.filter(function (p) { return p[1] !== '' && p[1] != null; }).map(function (p) { return '<dt>' + p[0] + '</dt><dd>' + p[1] + '</dd>'; }).join(''); return h ? '<dl class="kv">' + h + '</dl>' : ''; }
function asObj(x, key) { if (x && typeof x === 'object') return x; var o = {}; o[key] = x; return o; }
function conceptsHtml(r, inModal) {
  if (!r.concepts || !r.concepts.length) return '';
  return '<div class="concepts">' + r.concepts.map(function (c) {
    var html = c.html ? ' · <a href="' + esc(c.html) + '" target="_blank" rel="noopener">HTML-макет</a>' : '';
    if (c.img && IMG[c.img]) { var d = DIMS[c.img] || []; return '<figure class="lb' + (c.mobile ? ' mobile' : '') + '" data-key="' + esc(c.img) + '" data-group="mockups" data-ref="' + esc(c.ref || '') + '" data-cap="' + esc(c.title) + '" tabindex="0" role="button"><img data-img="' + esc(c.img) + '" alt="' + esc(c.title) + '"' + (d[0] ? ' width="' + d[0] + '" height="' + d[1] + '"' : '') + '><figcaption><b>' + esc(c.title) + '</b> <span class="badge-concept">концепт</span>' + (c.ref ? ' · <a href="#ref-' + esc(c.ref) + '">референс →</a>' : '') + html + '</figcaption></figure>'; }
    return '<div class="ph"><div class="ph-t">' + esc(c.title) + '</div>Концепт без PNG' + (c.ref ? ' · <a href="#ref-' + esc(c.ref) + '">референс →</a>' : '') + html + '</div>';
  }).join('') + '</div>';
}
function detail(r) {
  var sc = r.scores || {}, m = r.m || {};
  var essence = kv([['Что сделать', esc(r.description)], ['Почему сработает', esc(r.rationale)], ['Для кого', esc(r.segment)], ['Что есть сейчас', esc(r.current_feature)]]);
  var kpi = (r.effect_kpi || []).map(function (k) { k = asObj(k, 'kpi'); return '<li><b>' + esc(txt(k.kpi)) + '</b> ' + (k.direction === 'down' ? '↓' : k.direction === 'up' ? '↑' : '') + ' ' + esc(txt(k.range)) + (k.label ? ' <span class="muted">[' + esc(k.label) + ']</span>' : '') + '</li>'; }).join('');
  var steps = (r.steps || []).map(function (s) { s = asObj(s, 'what'); return '<li><b>' + esc(txt(s.what)) + '</b>' + (s.where ? ' — <span class="muted">' + esc(txt(s.where)) + '</span>' : '') + (s.how ? ': ' + esc(txt(s.how)) : '') + (s.doc_url ? ' · ' + link(s.doc_url, 'документация') : '') + '</li>'; }).join('');
  var ev = (r.evidence || []).map(function (e) { e = asObj(e, 'title'); var t = e.url ? link(e.url, e.title || e.url) : esc(e.title || ''); return '<li>' + tag(lab('evidence', e.kind)) + ' ' + t + (e.file ? ' <code>' + esc(e.file) + '</code>' : '') + (e.note ? ' — «' + esc(e.note) + '»' : '') + (e.checked ? ' <span class="muted">(проверено ' + esc(e.checked) + ')</span>' : '') + '</li>'; }).join('');
  var eff = r.effort && r.effort[0] != null ? fmt(r.effort[0]) + (r.effort[1] != null && r.effort[1] !== r.effort[0] ? '–' + fmt(r.effort[1]) : '') + ' дн.' : '';
  var costs = kv([['Трудозатраты', esc(eff)], ['Деньги', esc(money(r.cost_money))], ['До первого результата', r.ttfr != null && r.ttfr !== '' ? esc(txt(r.ttfr)) + ' дн.' : ''], ['Дешёвая проверка', esc(r.cheap_test)]]);
  var risks = r.risks && typeof r.risks === 'object' ? Object.keys(r.risks).filter(function (k) { return k !== 'note' && r.risks[k] != null && r.risks[k] !== ''; }).map(function (k) { var v = r.risks[k]; return '<span class="tag">' + esc(lab('risk', k)) + ' <span class="risk r' + esc(v) + '">' + esc(v) + '</span></span>'; }).join(' ') + (r.risks.note ? '<p class="muted">' + esc(r.risks.note) + '</p>' : '') : '';
  var subs = META.subscales || [];
  var scoreChips = Object.keys(sc).filter(function (k) { return typeof sc[k] === 'number' || typeof sc[k] === 'string'; }).map(function (k) { return '<span class="tag">' + esc(lab('score', k)) + ': <b>' + esc(sc[k]) + '</b></span>'; }).join(' ');
  var missingSubs = subs.filter(function (k) { return sc[k] == null; });
  var IDX = ['value_index', 'cost_index', 'risk_index', 'confidence_calc'], ORD = Object.keys(L.metric || {});
  var idx = kv(IDX.map(function (k) { return [esc(lab('metric', k)), m[k] != null ? '<b>' + esc(fmt(m[k])) + '</b>' + (k !== 'confidence_calc' ? ' <span class="muted">из 5</span>' : '') : '']; }));
  var calcKeys = Object.keys(m).filter(function (k) { return IDX.indexOf(k) < 0 && !/^(s_|ts_|effort_min|effort_max|effort_avg|cost_min|cost_max|ttfr|risk_sum|risk_max|evidence_n)/.test(k); })
    .sort(function (a, b) { var x = ORD.indexOf(a), y = ORD.indexOf(b); return (x < 0 ? 99 : x) - (y < 0 ? 99 : y); });
  var calc = calcKeys.map(function (k) { return '<span class="tag">' + esc(lab('metric', k)) + ': <b>' + esc(fmt(m[k])) + '</b></span>'; }).join(' ');
  var cls = kv([['Квадрант', badge('q', r.quadrant)], ['Приоритет', badge('p', r.priority)], ['MoSCoW', esc(lab('moscow', r.moscow))], ['Кано', esc(lab('kano', r.kano))], ['Горизонт', esc(lab('horizon', r.horizon)) + (r.horizon_years ? ' · лет: ' + esc(r.horizon_years) : '')], ['Метки', (r.labels || []).map(function (x) { return tag(lab('label', x)); }).join(' ')], ['Теги', (r.tags || []).map(function (x) { return tag(x); }).join(' ')]]);
  var ts = '';
  [['TypeSafe (score.py)', r.typesafe], ['TypeSafe Jev', r.jev]].forEach(function (p) { if (p[1] && typeof p[1] === 'object') { var h = Object.keys(p[1]).map(function (k) { return '<span class="tag">' + esc(k) + ': <b>' + esc(txt(p[1][k])) + '</b></span>'; }).join(' '); if (h) ts += '<p><span class="muted">' + p[0] + ':</span> ' + h + '</p>'; } });
  var deps = (r.dependencies || []).map(function (d) { return BYID[d] ? pidLink(d) : esc(d) + ' <span class="muted">(нет в реестре)</span>'; }).join(', ');
  var rdeps = (r.rdeps || []).map(pidLink).join(', ');
  var mn = r.mentions || {}, ment = [];
  (mn.gantt || []).forEach(function (g) { ment.push('<li>Гант: <a href="#gantt" data-g-open="' + g.i + '">' + esc(g.t) + '</a></li>'); });
  (mn.kanban || []).forEach(function (k) { ment.push('<li>Kanban: <a href="#kanban" data-k-open="' + k.i + '">колонка «' + esc(k.t) + '»</a></li>'); });
  (mn.flows || []).forEach(function (f) { ment.push('<li>Схема «' + esc(f.f) + '»: <a href="#flows" data-node-open="' + esc(f.id) + '">' + esc(f.t) + '</a></li>'); });
  var rel = kv([['Зависит от', deps], ['От него зависят', rdeps], ['Источник', esc(r.source_group) + ((r.merged_from || []).length ? ' · объединено из ' + esc(r.merged_from.join(', ')) : '')]]);
  return '<div class="detail">' + sec('Суть', essence) + sec('Эффект и KPI', kpi ? '<ul>' + kpi + '</ul>' : '') + sec('Шаги', steps ? '<ol>' + steps + '</ol>' : '')
    + sec('Затраты и проверка', costs) + sec('Риски (1–5)', risks) + sec('Классификация', cls)
    + sec('Оценки 1–5', scoreChips + (scoreChips && missingSubs.length && missingSubs.length < subs.length ? '<p class="muted small">Остальные подшкалы (' + missingSubs.length + ' из ' + subs.length + ') не заданы — в расчётах равны «Ценности».</p>' : ''))
    + sec('Расчётные метрики', idx + calc + ts) + sec('Доказательства (класс ' + esc(r.evidence_class || '—') + ')', ev ? '<ul>' + ev + '</ul>' : '')
    + sec('Связи', rel + (ment.length ? '<ul>' + ment.join('') + '</ul>' : '')) + sec('Концепт дизайна', conceptsHtml(r), 'wide') + '</div>';
}
function openProposal(id, fromHist) {
  var r = BYID[id]; if (!r) return;
  var cur = pm.getAttribute('data-id');
  if (!fromHist && pm.classList.contains('open') && cur && cur !== id) pmHist.push(cur);
  pm.setAttribute('data-id', id);
  $('#pmtitle').innerHTML = '<b>' + esc(r.id) + '</b> ' + esc(r.title);
  $('#pmchips').innerHTML = [r.m && r.m.rank != null ? tag('#' + fmt(r.m.rank)) : '', badge('p', r.priority), badge('q', r.quadrant), r.evidence_class ? badge('c', r.evidence_class) : '', tag(lab('category', r.category)), tag(lab('horizon', r.horizon)), r.m && r.m.composite != null ? tag('балл ' + fmt(r.m.composite)) : ''].join(' ');
  $('#pmback').hidden = !pmHist.length;
  var body = $('#pmbody'); body.innerHTML = detail(r); fillImgs(body); linkifyEl(body);
  openLayer(pm); pm.scrollTop = 0;
}
function openInfo(title, html) { $('#imtitle').innerHTML = title; var b = $('#imbody'); b.innerHTML = html; fillImgs(b); linkifyEl(b); openLayer(im); im.scrollTop = 0; }

/* ---------- реестр ---------- */
var expanded = {}, sortK = 'rank', sortD = 1, shown = [];
var HORD = { now: 0, next: 1, later: 2, vision: 3 };
var COLS = [
  { k: 'rank', t: '#', num: 1 }, { k: 'id', t: 'ID' }, { k: 'title', t: 'Предложение', cls: 'c-title' }, { k: 'category', t: 'Категория' },
  { k: 'horizon', t: 'Горизонт' }, { k: 'evidence_class', t: 'Класс' }, { k: ['value_index', 's_value'], t: 'Ценн.', num: 1 }, { k: ['cost_index', 's_cost'], t: 'Стоим.', num: 1 },
  { k: ['risk_index', 's_risk'], t: 'Риск', num: 1 }, { k: ['confidence_calc', 's_confidence'], t: 'Увер.', num: 1 }, { k: 'effort_avg', t: 'Дни', num: 1 }, { k: 'composite', t: 'Балл', num: 1 },
  { k: 'priority', t: 'Приор.' }, { k: 'quadrant', t: 'Квадрант' }, { k: 'kano', t: 'Кано' }, { k: 'labels', t: 'Метки' }
];
function val(r, k) {
  if (k === 'id' || k === 'title' || k === 'evidence_class' || k === 'priority') return r[k] || null;
  if (k === 'category') return lab('category', r.category) || null;
  if (k === 'horizon') return r.horizon in HORD ? HORD[r.horizon] : (r.horizon ? 9 : null);
  if (k === 'quadrant') return r.quadrant ? lab('quadrant', r.quadrant) : null;
  if (k === 'kano') return r.kano ? lab('kano', r.kano) : null;
  if (k === 'labels') return (r.labels || []).length || null;
  var v = r.m ? r.m[k] : null; return v == null ? null : v;
}
function cell(r, c) {
  var v = val(r, c.k);
  switch (c.k) {
    case 'id': return pidLink(r.id);
    case 'title': return '<b>' + esc(r.title) + '</b>' + (r.has_mockup ? ' <span class="tag" title="Есть концепт дизайна">◧ макет</span>' : '');
    case 'horizon': return esc(lab('horizon_short', r.horizon));
    case 'evidence_class': return badge('c', r.evidence_class);
    case 'priority': return badge('p', r.priority);
    case 'quadrant': return badge('q', r.quadrant);
    case 'labels': return (r.labels || []).map(function (x) { return tag(lab('label', x)); }).join(' ');
    case 'effort_avg': return r.effort && r.effort[0] != null ? esc(fmt(r.effort[0]) + (r.effort[1] !== r.effort[0] ? '–' + fmt(r.effort[1]) : '')) : '';
    default: return esc(fmt(v));
  }
}
COLS.forEach(function (c) { if (Array.isArray(c.k)) { var ks = c.k; c.k = ks.filter(function (k) { return REG.some(function (r) { return r.m && r.m[k] != null; }); })[0] || ks[ks.length - 1]; } });
var visCols = COLS.filter(function (c) { return REG.some(function (r) { var v = val(r, c.k); return v != null && v !== ''; }) || c.k === 'id' || c.k === 'title'; });
function metricLabel(k) { if (MET[k]) return MET[k].label; var c = COLS.filter(function (x) { return x.k === k; })[0]; return c ? c.t : k; }
function defaultDir(k) { if (MET[k]) return MET[k].dir; return ['id', 'title', 'category', 'horizon', 'evidence_class', 'priority', 'kano', 'quadrant'].indexOf(k) >= 0 ? 1 : -1; }
function filters() { var f = {}; $$('#registry [data-f]').forEach(function (s) { if (s.value) f[s.getAttribute('data-f')] = s.value; }); return f; }
function pass(r, f, q) {
  for (var k in f) { var v = f[k];
    if (k === 'labels' || k === 'tags') { if ((r[k] || []).indexOf(v) < 0) return false; }
    else if (k === 'has_mockup') { if ((v === 'yes') !== !!r.has_mockup) return false; }
    else if (String(r[k] || '') !== v) return false; }
  return !q || r._hay.indexOf(q) >= 0;
}
function renderReg() {
  var tb = $('#tb'); if (!tb) return;
  var f = filters(), q = norm($('#q').value);
  shown = REG.filter(function (r) { return pass(r, f, q); });
  shown.sort(function (a, b) { var x = val(a, sortK), y = val(b, sortK); if (x == null && y == null) return a.id < b.id ? -1 : 1; if (x == null) return 1; if (y == null) return -1;
    var d = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'ru', { numeric: true }); return d ? d * sortD : (a.id < b.id ? -1 : 1); });
  var cols = visCols.slice(), extra = null;
  if (!cols.some(function (c) { return c.k === sortK; })) { extra = { k: sortK, t: '↕ ' + metricLabel(sortK), num: 1, extra: 1 }; cols.push(extra); }
  $('#reg-head').innerHTML = cols.map(function (c) { return '<th data-k="' + esc(c.k) + '"' + (c.num ? ' class="num' + (c.extra ? ' extra' : '') + '"' : '') + (c.k === sortK ? ' aria-sort="' + (sortD > 0 ? 'ascending' : 'descending') + '"' : '') + ' title="Сортировать: ' + esc(metricLabel(c.k)) + '">' + esc(c.t) + '</th>'; }).join('');
  tb.innerHTML = shown.map(function (r) {
    var open = !!expanded[r.id], sv = val(r, sortK);
    return '<tr class="row' + (open ? ' open' : '') + '" data-id="' + esc(r.id) + '" data-cat="' + esc(r.category) + '" data-v="' + esc(sv == null ? '' : sv) + '" tabindex="0" aria-expanded="' + open + '">'
      + cols.map(function (c) { return '<td' + (c.num ? ' class="num"' : c.cls ? ' class="' + c.cls + '"' : '') + '>' + cell(r, c) + '</td>'; }).join('') + '</tr>'
      + (open ? '<tr class="detail"><td colspan="' + cols.length + '">' + detail(r) + '</td></tr>' : '');
  }).join('') || '<tr><td colspan="' + cols.length + '" class="muted">Ничего не найдено — измените фильтры или поиск.</td></tr>';
  $('#reg-count').textContent = 'Показано: ' + shown.length + ' из ' + REG.length;
  var sb = $('#sortby'); if (sb && sb.value !== sortK) { if ([].some.call(sb.options, function (o) { return o.value === sortK; })) sb.value = sortK; }
  var sd = $('#sortdir'); if (sd) sd.textContent = sortD > 0 ? 'по возрастанию ↑' : 'по убыванию ↓';
  fillImgs(tb); $$('tr.detail', tb).forEach(linkifyEl);
}
function setSort(k, dir) { if (dir) { sortK = k; sortD = dir; } else if (sortK === k) sortD = -sortD; else { sortK = k; sortD = defaultDir(k); } renderReg(); }
function toggleRow(id) { if (expanded[id]) delete expanded[id]; else expanded[id] = 1; renderReg(); }
function resetFilters() { $$('#registry [data-f]').forEach(function (s) { s.value = ''; }); var q = $('#q'); if (q) q.value = ''; }
function showInRegistry(id) {
  closeAll(); resetFilters(); expanded[id] = 1; renderReg();
  var tr = document.querySelector('#tb tr.row[data-id="' + id + '"]');
  var sec = document.getElementById('registry'); if (sec) sec.scrollIntoView({ behavior: 'instant', block: 'start' });
  if (tr) { tr.scrollIntoView({ behavior: 'instant', block: 'center' }); tr.classList.add('flash'); setTimeout(function () { tr.classList.remove('flash'); }, 2100); try { tr.focus({ preventScroll: true }); } catch (e) {} }
}
function download(name, text, type) { var blob = new Blob([text], { type: type }); var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.rel = 'noopener'; document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1500); }
function csvCell(v) { if (v == null) return ''; var s = typeof v === 'number' ? String(v) : String(v); if (typeof v !== 'number' && /^[=+\-@\t\r]/.test(s)) s = "'" + s; return /[",;\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
function exportRows(kind) {
  var stamp = (META.date || '') + '-' + shown.length;
  if (kind === 'json') {
    var data = shown.map(function (r) { var o = {}; Object.keys(r).forEach(function (k) { if (['m', '_hay', 'concepts', 'mentions', 'rdeps', 'has_mockup', 'effort'].indexOf(k) < 0) o[k] = r[k]; }); o.effort_days = r.effort; o.metrics = r.m; return o; });
    download('registry-' + stamp + '.json', JSON.stringify(data, null, 2), 'application/json;charset=utf-8'); return;
  }
  var mk = []; shown.forEach(function (r) { Object.keys(r.m || {}).forEach(function (k) { if (mk.indexOf(k) < 0) mk.push(k); }); });
  var head = ['id', 'title', 'category', 'segment', 'horizon', 'evidence_class', 'priority', 'quadrant', 'moscow', 'kano', 'labels', 'tags', 'dependencies', 'effort_min', 'effort_max', 'currency', 'description', 'rationale', 'cheap_test'];
  var extraM = mk.filter(function (k) { return head.indexOf(k) < 0; });
  var lines = [head.concat(extraM).join(',')];
  shown.forEach(function (r) {
    var base = [r.id, r.title, r.category, r.segment, r.horizon, r.evidence_class, r.priority, r.quadrant, r.moscow, r.kano, (r.labels || []).join('; '), (r.tags || []).join('; '), (r.dependencies || []).join('; '), r.effort ? r.effort[0] : '', r.effort ? r.effort[1] : '', r.cost_money && r.cost_money.currency || '', r.description, r.rationale, r.cheap_test];
    lines.push(base.concat(extraM.map(function (k) { return r.m[k]; })).map(csvCell).join(','));
  });
  download('registry-' + stamp + '.csv', '\ufeff' + lines.join('\r\n') + '\r\n', 'text/csv;charset=utf-8');
}

/* ---------- Гант, Kanban, узлы схем ---------- */
function openGantt(i) {
  var g = GANTT[i]; if (!g) return;
  var deps = (g.deps || []).map(function (d) { if (BYID[d]) return pidLink(d); var t = GANTT.filter(function (x) { return x.id === d; })[0]; return t ? '<a href="#gantt" data-g-open="' + t.i + '">' + esc(d) + ' ' + esc(t.task) + '</a>' : esc(d); }).join(', ');
  var steps = (g.proposal_ids || []).map(function (id) { var r = BYID[id]; if (!r || !(r.steps || []).length) return ''; return '<p><b>' + pidLink(id) + '</b> ' + esc(r.title) + '</p><ol>' + r.steps.map(function (s) { s = asObj(s, 'what'); return '<li><b>' + esc(txt(s.what)) + '</b>' + (s.where ? ' — ' + esc(txt(s.where)) : '') + (s.how ? ': ' + esc(txt(s.how)) : '') + '</li>'; }).join('') + '</ol>'; }).join('');
  openInfo('<span class="muted">Гант</span> ' + esc(g.task), kv([['Фаза', esc(g.phase === 'vision' ? 'видение' : g.phase)], ['Сроки', esc(g.when)], ['Тип', g.type === 'milestone' ? 'веха (контрольная точка)' : 'работа'], ['Ответственный', esc(g.owner)], ['Критерий готовности', esc(g.done)], ['Зависимости', deps]])
    + ((g.proposal_ids || []).length ? '<h4>Предложения в этой задаче</h4><ul>' + plist(g.proposal_ids) + '</ul>' : '') + (steps ? '<h4>Что сделать (шаги из карточек)</h4>' + steps : ''));
}
function openKanban(i) {
  var k = KAN[i]; if (!k) return; var r = BYID[k.id];
  var eff = Array.isArray(k.effort_days) ? k.effort_days.join('–') + ' дн.' : txt(k.effort_days);
  var steps = (k.steps || []).map(function (s) { return '<li>' + esc(txt(s)) + '</li>'; }).join('');
  var links = (k.links || []).map(function (l) { var u = typeof l === 'object' && l ? (l.url || '') : l; var t = typeof l === 'object' && l ? (l.title || l.url) : l; return '<li>' + link(u, t) + '</li>'; }).join('');
  openInfo('<span class="muted">Kanban · ' + esc(k.column) + '</span> ' + esc(k.id || '') + ' ' + esc(k.title || ''), kv([['Колонка', esc(k.column)], ['Приоритет', badge('p', k.priority || (r ? r.priority : ''))], ['Трудозатраты', esc(eff)], ['Цель', esc(txt(k.goal))], ['KPI', esc(txt(k.kpi))], ['Метки', (k.tags || []).map(function (t) { return tag(t); }).join(' ')]])
    + (steps ? '<h4>Шаги</h4><ol>' + steps + '</ol>' : '') + (links ? '<h4>Ссылки</h4><ul>' + links + '</ul>' : '') + (r ? '<h4>Карточка предложения</h4><ul>' + plist([k.id]) + '</ul>' : ''));
}
function openNode(id) {
  var n = NODES[id]; if (!n) return;
  $$('.flowsvg .fnode.on').forEach(function (x) { x.classList.remove('on'); });
  $$('.flowsvg [data-node]').forEach(function (x) { if (x.getAttribute('data-node') === id && x.classList.contains('fnode')) x.classList.add('on'); });
  openInfo('<span class="muted">Схема «' + esc(n.flow) + '»</span> ' + esc(n.label), (n.what ? '<h4>Что это</h4><p>' + esc(n.what) + '</p>' : '') + (n.now ? '<h4>Как сейчас</h4><p>' + esc(n.now) + '</p>' : '')
    + ((n.todo || []).length ? '<h4>Что сделать</h4><ul>' + n.todo.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '') + (n.metrics ? '<h4>Как измерять</h4><p>' + esc(n.metrics) + '</p>' : '')
    + ((n.proposals || []).length ? '<h4>Связанные предложения</h4><ul>' + plist(n.proposals) + '</ul>' : '') || '<p class="muted">Описание блока не задано.</p>');
}

/* ---------- лайтбокс ---------- */
var lbimg = $('#lbimg'), lbwrap = $('#lbwrap'), lbview = $('#lbview'), lbside = $('#lbside');
function lbFigs() { return $$('.lb[data-key]'); }
function openLB(el) {
  var g = el.getAttribute('data-group') || '', seen = {};
  LB.items = lbFigs().filter(function (f) { return (f.getAttribute('data-group') || '') === g && IMG[f.getAttribute('data-key')]; }).filter(function (f) { var k = f.getAttribute('data-key') + '|' + (f.getAttribute('data-ref') || ''); if (seen[k]) return false; seen[k] = 1; return true; });
  if (!LB.items.length) return;
  LB.idx = Math.max(0, LB.items.findIndex(function (f) { return f.getAttribute('data-key') === el.getAttribute('data-key') && (f.getAttribute('data-ref') || '') === (el.getAttribute('data-ref') || ''); }));
  LB.zoom = 'fit'; LB.cur = LB.items[LB.idx]; openLayer(lb); lbShow();
}
function lbStep(d) { if (LB.items.length < 2) return; LB.idx = (LB.idx + d + LB.items.length) % LB.items.length; lbShow(); }
function lbShow() {
  var f = LB.items[LB.idx]; LB.cur = f; var key = f.getAttribute('data-key'), ref = REFS[f.getAttribute('data-ref')] || null;
  lbimg.removeAttribute('style'); lbimg.src = IMG[key]; lbimg.alt = f.getAttribute('data-cap') || '';
  $('#lbcap').textContent = (f.getAttribute('data-cap') || '').replace(/\s+/g, ' ');
  $('#lbcount').textContent = (LB.idx + 1) + ' / ' + LB.items.length;
  $('#lbprev').disabled = $('#lbnext').disabled = LB.items.length < 2;
  lb.classList.toggle('nopanel', !ref); lb.classList.remove('nohs'); $('#lbhs').hidden = !ref || !(ref.hotspots || []).length;
  $$('.pin,.hsbox,.hsel', lbwrap).forEach(function (x) { x.remove(); });
  lbside.innerHTML = '';
  if (ref) {
    var hs = ref.hotspots || [];
    lbside.innerHTML = '<h3>' + esc(ref.title) + '</h3><div class="meta">' + ((ref.proposals || []).length ? 'Предложения: ' + ref.proposals.map(pidLink).join(' ') : 'Общий дизайн') + (ref.kind ? ' · ' + esc(ref.kind) : '') + '</div>'
      + (ref.summary ? '<p>' + esc(ref.summary) + '</p>' : '') + (ref.entry ? '<p class="meta">Точка входа: ' + esc(ref.entry) + '</p>' : '')
      + '<div class="hslist">' + hs.map(function (h) { return '<div class="hsitem" data-n="' + esc(h.n) + '"><span class="hsn">' + esc(h.n) + '</span><div><b>' + esc(h.title) + (h.state ? ' <span class="st st-' + esc(h.state) + '">' + esc({ new: 'новое', changed: 'изменено', shared: 'общий дизайн' }[h.state] || h.state) + '</span>' : '') + '</b><span>' + esc(h.text) + '</span>' + (h.proposal ? ' ' + pidLink(h.proposal) : '') + '</div></div>'; }).join('') + '</div>'
      + ((ref.todo || []).length ? '<details open><summary>Что доделать (' + ref.todo.length + ')</summary><ul>' + ref.todo.map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('') + '</ul></details>' : '')
      + '<p class="meta"><a href="#ref-' + esc(f.getAttribute('data-ref')) + '">Карточка референса →</a></p>';
    hs.forEach(function (h) { if (h.l == null) return;
      var box = document.createElement('div'); box.className = 'hsbox'; box.setAttribute('data-n', h.n); box.style.cssText = 'left:' + h.l + '%;top:' + h.t + '%;width:' + h.w + '%;height:' + h.h + '%'; lbwrap.appendChild(box);
      var sel = document.createElement('div'); sel.className = 'hsel'; sel.setAttribute('data-n', h.n); sel.style.cssText = box.style.cssText; lbwrap.appendChild(sel);
      var pin = document.createElement('div'); pin.className = 'pin'; pin.setAttribute('data-n', h.n); pin.textContent = h.n; pin.title = h.title; pin.style.left = (h.pl != null ? h.pl : h.l) + '%'; pin.style.top = (h.pt != null ? h.pt : h.t) + '%'; lbwrap.appendChild(pin); });
  }
  if (lbimg.complete && lbimg.naturalWidth) setZoom(LB.zoom); syncHash();
}
function baseWidth() { var key = LB.cur && LB.cur.getAttribute('data-key'); var d = DIMS[key] || [lbimg.naturalWidth, lbimg.naturalHeight]; var ref = REFS[LB.cur && LB.cur.getAttribute('data-ref')]; var nw = d[0] || 0, nh = d[1] || 0; if (ref && ref.w) { return [ref.w, ref.h || (nh * ref.w / (nw || 1))]; } var sc = ref && ref.scale > 0 ? ref.scale : 1; return [nw / sc, nh / sc]; }
function setZoom(z) {
  LB.zoom = z; var b = baseWidth(), bw = b[0], bh = b[1]; if (!bw || !bh) return;
  var aw = Math.max(60, lbview.clientWidth - 32), ah = Math.max(60, lbview.clientHeight - 32);
  var w = z === 'fit' ? Math.min(aw, ah * bw / bh, bw) : z === '1' ? bw : bw * 2;
  lbimg.style.width = Math.max(16, Math.round(w)) + 'px'; lbimg.style.height = 'auto';
  $$('#lbbar [data-z]').forEach(function (x) { x.classList.toggle('on', x.getAttribute('data-z') === z); }); lb.setAttribute('data-zoom', z);
}
function zoomStep(d) { var order = ['fit', '1', '2'], i = order.indexOf(LB.zoom); setZoom(order[Math.max(0, Math.min(2, i + d))]); }
function selectHS(n) { $$('.pin,.hsel', lbwrap).forEach(function (p) { p.classList.toggle('on', p.getAttribute('data-n') == n); }); $$('.hsitem', lbside).forEach(function (i) { var on = i.getAttribute('data-n') == n; i.classList.toggle('on', on); if (on) i.scrollIntoView({ block: 'nearest' }); }); }

/* ---------- конкуренты ---------- */
function compCard(c, show) {
  var media = c.img && IMG[c.img] ? '<figure class="lb" data-key="' + esc(c.img) + '" data-group="competitors" data-ref="" data-cap="' + esc(c.name + (c.url ? ' — ' + c.url : '')) + '" tabindex="0" role="button"><img data-img="' + esc(c.img) + '" alt="' + esc(c.name) + '"></figure>'
    : '<div class="noshot">' + (c.shot_blocked ? 'скриншот недоступен: защита сайта от ботов' : c.shot_error ? 'скриншот не снят: ' + esc(String(c.shot_error).slice(0, 90)) : 'скриншота нет') + '</div>';
  function lst(title, arr, cls) { return (arr || []).length ? '<div class="lblh">' + title + '</div><ul class="' + cls + '">' + arr.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : ''; }
  var meta = [lab('comp_type', c.type), c.segment, c.price, c.monetization, c.languages, c.audience, c.freshness, c.traffic ? 'трафик: ' + c.traffic : ''].filter(Boolean).map(esc).join(' · ');
  var srcs = (c.sources || []).map(function (u, i) { return link(u, 'источник ' + (i + 1)); }).join(', ');
  return '<article class="ccard" data-type="' + esc(c.type) + '" data-slug="' + esc(c.slug) + '">' + media + '<div><h4>' + link(c.url, c.name) + (c.verdict ? ' ' + tag(c.verdict) : '') + '</h4><div class="cmeta">' + meta + '</div>'
    + (show.them ? lst('Где лучше они', c.better_than_us, 'them') : '') + (show.us ? lst('Где лучше мы', c.we_better, 'us') : '') + (show.best ? lst('Их лучшие решения', c.best_solutions, 'best') + lst('Перенять', c.adopt, 'best') : '')
    + (show.design && c.design_note ? '<div class="lblh">Дизайн</div><p>' + esc(c.design_note) + '</p>' : '') + lst('Жалобы пользователей', c.complaints, 'them') + lst('Не повторять', c.avoid, 'them')
    + (srcs ? '<div class="cmeta">' + srcs + '</div>' : '') + '</div></article>';
}
function renderComp() {
  var grid = $('#cgrid'); if (!grid) return;
  var q = norm(($('#cq') || {}).value), ty = ($('#ctype') || {}).value || '';
  var show = { them: !$('#cthem') || $('#cthem').checked, us: !$('#cus') || $('#cus').checked, best: !$('#cbest') || $('#cbest').checked, design: !$('#cdesign') || $('#cdesign').checked };
  var all = COMP.filter(function (c) { return !c.self; });
  var list = all.filter(function (c) { return (!ty || c.type === ty) && (!q || c._hay.indexOf(q) >= 0); });
  $('#ccount').textContent = 'Показано: ' + list.length + ' из ' + all.length;
  grid.innerHTML = list.map(function (c) { return compCard(c, show); }).join('') || '<p class="muted">Ничего не найдено.</p>';
  fillImgs(grid); linkifyEl(grid); renderMatrix(list);
}
function renderMatrix(list) {
  var box = $('#cmatrix'); if (!box) return; var feats = META.comp_features || []; if (!feats.length) return;
  var self = COMP.filter(function (c) { return c.self; })[0], rows = (self ? [self] : []).concat(list);
  var cnt = feats.map(function (f) { return list.filter(function (c) { return c.features && c.features[f] === true; }).length; });
  function cellv(c, f, i) { var v = c.features ? c.features[f] : undefined; var gap = c.self && v !== true && list.length && cnt[i] / list.length >= 0.5;
    var cls = v === true ? 'y' : v === false ? 'n' : v == null ? 'u' : 'p'; var t = v === true ? '✓' : v === false ? '—' : v == null ? '?' : '~';
    var ti = v === true ? 'есть' : v === false ? 'нет' : v == null ? 'нет данных' : String(v); if (gap) ti += ' · у нас нет, у большинства конкурентов есть';
    return '<td class="' + cls + (gap ? ' gap' : '') + '" title="' + esc(ti) + '">' + t + '</td>'; }
  box.innerHTML = '<table class="cm"><thead><tr><th>Продукт</th>' + feats.map(function (f) { return '<th>' + esc(f) + '</th>'; }).join('') + '</tr></thead><tbody>'
    + rows.map(function (c) { return '<tr' + (c.self ? ' class="self"' : '') + '><th scope="row" title="' + esc(c.name) + '">' + esc(c.name) + (c.self ? ' <span class="tag">мы</span>' : '') + '</th>' + feats.map(function (f, i) { return cellv(c, f, i); }).join('') + '</tr>'; }).join('')
    + '</tbody><tfoot><tr><th scope="row">Есть у конкурентов</th>' + cnt.map(function (n) { return '<td>' + n + '/' + list.length + '</td>'; }).join('') + '</tr></tfoot></table>'
}

/* ---------- таблицы: сортировка и фильтр ---------- */
function initTables() {
  $$('table.sortable').forEach(function (t) { var ths = $$('thead th', t); ths.forEach(function (th, ci) { th.addEventListener('click', function () {
    var dir = th.getAttribute('aria-sort') === 'ascending' ? -1 : 1; ths.forEach(function (x) { x.removeAttribute('aria-sort'); }); th.setAttribute('aria-sort', dir > 0 ? 'ascending' : 'descending');
    var tb = t.tBodies[0], rows = Array.prototype.slice.call(tb.rows);
    function v(r) { var c = r.cells[ci]; if (!c) return ''; var d = c.getAttribute('data-v'); return d != null ? d : c.textContent.trim(); }
    var numeric = rows.every(function (r) { var x = v(r); return x === '' || !isNaN(parseFloat(String(x).replace(/\s/g, '').replace(',', '.'))); });
    rows.sort(function (a, b) { var x = v(a), y = v(b); if (x === '' && y === '') return 0; if (x === '') return 1; if (y === '') return -1;
      if (numeric) return (parseFloat(String(x).replace(/\s/g, '').replace(',', '.')) - parseFloat(String(y).replace(/\s/g, '').replace(',', '.'))) * dir;
      return String(x).localeCompare(String(y), 'ru', { numeric: true }) * dir; });
    rows.forEach(function (r) { tb.appendChild(r); }); }); }); });
  $$('input[data-filter-table]').forEach(function (inp) { inp.addEventListener('input', function () { var t = document.getElementById(inp.getAttribute('data-filter-table')); if (!t) return; var q = norm(inp.value);
    Array.prototype.forEach.call(t.tBodies[0].rows, function (r) { r.hidden = !!q && norm(r.textContent).indexOf(q) < 0; }); }); });
}

/* ---------- навигация: scrollspy, мобильное меню, тема ---------- */
var navLinks = $$('nav.side a[data-sec]'), spySecs = navLinks.map(function (a) { return document.getElementById(a.getAttribute('data-sec')); }), spyRaf = 0;
function spy() {
  spyRaf = 0; if (!navLinks.length) return;
  var th = 110, cur = 0, i;
  for (i = 0; i < spySecs.length; i++) { var s = spySecs[i]; if (s && s.getBoundingClientRect().top <= th) cur = i; }
  var doc = document.documentElement;
  if (window.innerHeight + window.scrollY >= doc.scrollHeight - 2) { for (i = spySecs.length - 1; i > cur; i--) { if (spySecs[i] && spySecs[i].getBoundingClientRect().top < window.innerHeight - 40) { cur = i; break; } } }
  navLinks.forEach(function (a, k) { var on = k === cur; a.classList.toggle('active', on); if (on) a.setAttribute('aria-current', 'location'); else a.removeAttribute('aria-current'); });
  var act = navLinks[cur], t = act ? act.textContent : '';
  $$('.here-t').forEach(function (el) { el.textContent = t; });
  var nav = $('#nav');
  if (nav && act && nav.scrollHeight > nav.clientHeight && getComputedStyle(nav).display !== 'none') { var top = act.offsetTop, h = nav.clientHeight; if (top < nav.scrollTop + 70 || top > nav.scrollTop + h - 40) nav.scrollTop = Math.max(0, top - h / 2); }
  if (nav) nav.scrollLeft = 0;
}
function toggleNav(on) { document.body.classList.toggle('nav-open', on); var b = $('#navtoggle'); if (b) b.setAttribute('aria-expanded', String(on)); }
var THEMES = ['auto', 'light', 'dark'], THEME_T = { auto: 'Тема: авто', light: 'Тема: светлая', dark: 'Тема: тёмная' }, theme = 'auto';
function applyTheme(t) { theme = THEMES.indexOf(t) >= 0 ? t : 'auto'; if (theme === 'auto') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', theme); $$('[data-theme-btn]').forEach(function (b) { b.textContent = THEME_T[theme]; b.setAttribute('data-mode', theme); }); }

/* ---------- схемы как картинки (для лайтбокса) ---------- */
function flowImages() {
  $$('.flowsvg').forEach(function (w) {
    var svg = w.querySelector('svg'), key = w.getAttribute('data-imgkey'); if (!svg || !key) return;
    var c = svg.cloneNode(true); c.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    var vb = (svg.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
    if (vb.length === 4 && vb[2] > 0 && vb[3] > 0) { c.setAttribute('width', vb[2]); c.setAttribute('height', vb[3]); DIMS[key] = [vb[2], vb[3]]; }
    c.setAttribute('style', 'font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#fff');
    $$('style', c).forEach(function (st) { st.textContent = st.textContent.split('#' + w.id + ' ').join('').split('#' + w.id).join('svg'); });
    IMG[key] = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(c));
  });
}

/* ---------- события ---------- */
document.addEventListener('click', function (e) {
  var t = e.target; if (!t || !t.closest) return;
  var p = t.closest('[data-pid]'); if (p) { e.preventDefault(); openProposal(p.getAttribute('data-pid')); return; }
  var c = t.closest('[data-close]'); if (c) { e.preventDefault(); closeLayer(c.closest('.layer')); return; }
  var go = t.closest('[data-g-open]'); if (go) { e.preventDefault(); openGantt(+go.getAttribute('data-g-open')); return; }
  var ko = t.closest('[data-k-open]'); if (ko) { e.preventDefault(); openKanban(+ko.getAttribute('data-k-open')); return; }
  var no = t.closest('[data-node-open]'); if (no) { e.preventDefault(); openNode(no.getAttribute('data-node-open')); return; }
  var f = t.closest('.lb[data-key]'); if (f && !t.closest('a') && !(t.closest('button') && !t.closest('button.lb'))) { e.preventDefault(); openLB(f); return; }
  var gr = t.closest('.grow[data-g]'); if (gr && !t.closest('a')) { openGantt(+gr.getAttribute('data-g')); return; }
  var kc = t.closest('.kcard[data-k]'); if (kc && !t.closest('a')) { openKanban(+kc.getAttribute('data-k')); return; }
  var nd = t.closest('[data-node]'); if (nd && (nd.closest('.flowsvg') || nd.classList.contains('nchip'))) { openNode(nd.getAttribute('data-node')); return; }
  var a = t.closest('a[href^="#"]'); if (a && stack.length && a.closest('.layer')) { closeAll(); }
});
document.addEventListener('keydown', function (e) {
  var top = topLayer();
  if (e.key === 'Escape') { if (top) { e.preventDefault(); closeLayer(top); } else if (document.body.classList.contains('nav-open')) toggleNav(false); return; }
  if (top === lb) {
    if (e.key === 'ArrowRight') { e.preventDefault(); lbStep(1); } else if (e.key === 'ArrowLeft') { e.preventDefault(); lbStep(-1); }
    else if (e.key === '+' || e.key === '=') zoomStep(1); else if (e.key === '-' || e.key === '_') zoomStep(-1); else if (e.key === '0') setZoom('fit');
    else if (e.key === 'h' || e.key === 'H' || e.key === 'р' || e.key === 'Р') lb.classList.toggle('nohs');
    return;
  }
  if (top) return;
  if (e.key !== 'Enter' && e.key !== ' ') return;
  var el = document.activeElement; if (!el || !el.matches) return;
  if (el.matches('.lb[data-key]') && el.tagName !== 'BUTTON') { e.preventDefault(); openLB(el); }
  else if (el.matches('tr.row')) { e.preventDefault(); toggleRow(el.getAttribute('data-id')); }
  else if (el.matches('.grow[data-g]')) { e.preventDefault(); openGantt(+el.getAttribute('data-g')); }
  else if (el.matches('.kcard[data-k]')) { e.preventDefault(); openKanban(+el.getAttribute('data-k')); }
  else if (el.matches('.flowsvg [data-node]')) { e.preventDefault(); openNode(el.getAttribute('data-node')); }
});
function hashOpen() {
  var h = location.hash || '', m; try { h = decodeURIComponent(h); } catch (e) {}
  if ((m = h.match(/^#lb=(.+)$/))) { var el = lbFigs().filter(function (f) { return f.getAttribute('data-key') === m[1]; })[0]; if (el) openLB(el); }
  else if ((m = h.match(/^#p=(P\d{3})$/))) { if (BYID[m[1]]) openProposal(m[1]); }
}

safe('images', function () { fillImgs(document); });
safe('flows', flowImages);
safe('registry', function () {
  if (!$('#tb')) return;
  if (!REG.some(function (r) { return r.m && r.m.rank != null; })) { sortK = 'id'; sortD = 1; }
  $('#reg-head').addEventListener('click', function (e) { var th = e.target.closest('th[data-k]'); if (th) setSort(th.getAttribute('data-k')); });
  $('#tb').addEventListener('click', function (e) { var t = e.target; if (t.closest('a,button,input,select,summary,.lb,[data-pid]')) return; if (t.closest('tr.detail')) return; var tr = t.closest('tr.row'); if (tr) toggleRow(tr.getAttribute('data-id')); });
  $$('#registry [data-f]').forEach(function (s) { s.addEventListener('change', renderReg); });
  $('#q').addEventListener('input', renderReg);
  var sb = $('#sortby'); if (sb) sb.addEventListener('change', function () { setSort(sb.value, defaultDir(sb.value)); });
  $('#sortdir').addEventListener('click', function () { sortD = -sortD; renderReg(); });
  $('#reg-reset').addEventListener('click', function () { resetFilters(); renderReg(); });
  $('#exp-csv').addEventListener('click', function () { exportRows('csv'); });
  $('#exp-json').addEventListener('click', function () { exportRows('json'); });
  renderReg();
});
safe('modal', function () {
  $('#pm-reg').addEventListener('click', function () { var id = pm.getAttribute('data-id'); if (id) showInRegistry(id); });
  $('#pmback').addEventListener('click', function () { if (pmHist.length) openProposal(pmHist.pop(), true); });
  [pm, im].forEach(function (m) { m.addEventListener('click', function (e) { if (e.target === m) closeLayer(m); }); });
});
safe('lightbox', function () {
  $('#lbprev').addEventListener('click', function () { lbStep(-1); }); $('#lbnext').addEventListener('click', function () { lbStep(1); });
  $$('#lbbar [data-z]').forEach(function (b) { b.addEventListener('click', function () { setZoom(b.getAttribute('data-z')); }); });
  $('#lbhs').addEventListener('click', function () { lb.classList.toggle('nohs'); });
  lbimg.addEventListener('load', function () { if (LB.cur) setZoom(LB.zoom); });
  lbwrap.addEventListener('click', function (e) { var p = e.target.closest('.pin,.hsbox'); if (p) { e.stopPropagation(); selectHS(p.getAttribute('data-n')); return; } if (e.target === lbimg && !lbview.classList.contains('nozoom')) setZoom(LB.zoom === 'fit' ? '1' : 'fit'); });
  lbside.addEventListener('click', function (e) { var i = e.target.closest('.hsitem'); if (i && !e.target.closest('a')) { selectHS(i.getAttribute('data-n')); var pin = lbwrap.querySelector('.pin[data-n="' + i.getAttribute('data-n') + '"]'); if (pin) pin.scrollIntoView({ block: 'center', inline: 'center' }); } });
  lbview.addEventListener('click', function (e) { if (e.target === lbview && !lbview.classList.contains('nozoom')) closeLayer(lb); });
  var drag = null;
  lbview.addEventListener('mousedown', function (e) { if (e.button !== 0 || e.target.closest('.pin,.hsbox')) return; drag = { x: e.clientX, y: e.clientY, sl: lbview.scrollLeft, st: lbview.scrollTop, moved: false }; lbview.classList.add('drag'); e.preventDefault(); });
  window.addEventListener('mousemove', function (e) { if (!drag) return; var dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true; lbview.scrollLeft = drag.sl - dx; lbview.scrollTop = drag.st - dy; });
  window.addEventListener('mouseup', function () { if (drag && drag.moved) { lbview.classList.add('nozoom'); setTimeout(function () { lbview.classList.remove('nozoom'); }, 30); } drag = null; lbview.classList.remove('drag'); });
  lbview.addEventListener('wheel', function (e) { if (e.ctrlKey || e.metaKey) { e.preventDefault(); zoomStep(e.deltaY < 0 ? 1 : -1); } }, { passive: false });
  window.addEventListener('resize', function () { if (lb.classList.contains('open')) setZoom(LB.zoom); });
});
safe('competitors', function () {
  if (!$('#cgrid')) return;
  ['cq', 'ctype', 'cthem', 'cus', 'cbest', 'cdesign'].forEach(function (id) { var el = document.getElementById(id); if (el) el.addEventListener(el.tagName === 'INPUT' && el.type === 'search' ? 'input' : 'change', renderComp); });
  renderComp();
});
safe('tables', initTables);
safe('nav', function () {
  window.addEventListener('scroll', function () { if (!spyRaf) spyRaf = requestAnimationFrame(spy); }, { passive: true });
  window.addEventListener('resize', function () { if (!spyRaf) spyRaf = requestAnimationFrame(spy); });
  window.addEventListener('load', spy);
  var nt = $('#navtoggle'); if (nt) nt.addEventListener('click', function () { toggleNav(!document.body.classList.contains('nav-open')); });
  navLinks.forEach(function (a) { a.addEventListener('click', function () { toggleNav(false); }); });
  spy();
});
safe('theme', function () {
  var t = 'auto'; try { t = localStorage.getItem('ps-theme') || 'auto'; } catch (e) {}
  applyTheme(t);
  $$('[data-theme-btn]').forEach(function (b) { b.addEventListener('click', function () { applyTheme(THEMES[(THEMES.indexOf(theme) + 1) % 3]); try { localStorage.setItem('ps-theme', theme); } catch (e) {} }); });
});
safe('print', function () { window.addEventListener('beforeprint', function () { $$('details').forEach(function (d) { d.open = true; }); fillImgs(document); }); });
safe('hash', function () { window.addEventListener('hashchange', hashOpen); hashOpen(); });
})();
"""


# ---------------------------------------------------------------- точка входа
def human(n):
    return "%.1f КБ" % (n / 1024.0) if n < 1048576 else "%.2f МБ" % (n / 1048576.0)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Сборка интерактивной офлайн-страницы стратегии (deliverables/index.html).")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--out", dest="out_file", help="куда записать страницу (по умолчанию <OUT>/deliverables/index.html)")
    ap.add_argument("--title", help="заголовок страницы (по умолчанию — H1 из research/strategy.md или имя продукта)")
    a = ap.parse_args(argv)
    out = Path(a.out).expanduser()
    if not out.is_dir():
        print("нет папки прогона: %s" % out, file=sys.stderr)
        return 2
    out_file = Path(a.out_file).expanduser() if a.out_file else out / "deliverables" / "index.html"
    out_file = out_file.resolve()
    b = Builder(out, out_file, a.title)
    page = b.build_all()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(page, encoding="utf-8")
    size = out_file.stat().st_size
    img_total = sum(m["bytes"] for m in b.img.meta.values())
    print("Готово: %s" % out_file)
    print("Размер страницы: %s; встроенных картинок: %d (%s)" % (human(size), len(b.img.map), human(img_total)))
    print("Разделы (%d): %s" % (len(b.nav), ", ".join(sid for sid, _, _ in b.nav)))
    print("Реестр: %d предложений; фигур: %d; ссылок на предложения: %d" % (len(b.rows), b.figs, page.count('class="pid"')))
    heavy = sorted(b.img.meta.items(), key=lambda kv: -kv[1]["bytes"])[:10]
    if heavy:
        print("Топ-10 самых тяжёлых вложений:")
        for i, (k, m) in enumerate(heavy, 1):
            print("  %2d. %10s  %s  (%s)" % (i, human(m["bytes"]), k, m["src"]))
    if b.warnings:
        print("Предупреждения (%d):" % len(b.warnings))
        for w in b.warnings:
            print("  - " + w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
