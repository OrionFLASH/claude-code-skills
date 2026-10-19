#!/usr/bin/env python3
"""Сборка интерактивной веб-страницы стратегии: по умолчанию сайт из нескольких файлов <OUT>/deliverables/ (режим site),
работающий офлайн по двойному клику (file://); `--single` — прежняя одна самодостаточная страница index.html.

Читает папку прогона <OUT> по references/data-contract.md; каждый раздел пропускается, если для него нет данных:
research/strategy.md, data/*.json (реестр, оценки, Гант, Kanban, схемы, конкуренты, модель, источники…),
charts/charts-index.json, mockups/ (tokens.css, current/, concepts/), design-refs/, competitors/shots/, build/run-config.json.

  build_html.py <OUT> [--site | --single | --lite] [--zip] [--site-csp self|none] [--out <file>] [--title "…"]
                      [--lite-encoder auto|pillow|ffmpeg|none] [--strict]

Режим site (по умолчанию), спецификация — references/interactive-site.md, раздел 1:
  deliverables/index.html           оболочка: разметка и текст разделов (≤ 1 МБ), относительные ссылки с ?v=<хеш содержимого>
  deliverables/assets/app.css|app.js|head.js   стили, логика страницы, ранняя установка темы
  deliverables/assets/data.js       window.PS_DATA = {реестр, оценки, конкуренты, Гант, Kanban, ссылки на картинки…} — JS, не JSON
                                    (fetch() по file:// запрещён)
  deliverables/assets/img/…         картинки: одна копия на изображение, WebP при Pillow/ffmpeg, иначе как есть; thumbs/ — миниатюры
  deliverables/assets/extra.css|extra.js   пользовательские правки из <OUT>/build/extra.css|js (если файлы есть)
  deliverables/assets/charts-<группа>.js   window.PS_CHARTS[ключ] = {svg, meta}: SVG интерактивных графиков и пояснения к их
                                    элементам по группам (scores, registry, plan, model, market…); подключаются динамическим
                                    <script src> при первом показе графика группы или по глубокой ссылке #chart/<ключ>/<id>
Интерактивные графики (references/interactive-site.md, п. 2.3): график с charts/<ключ>.meta.json — встроенный SVG с панелью
пояснений (клик/Enter/Space по элементу, ←/→, Esc), подсветкой легенды, «Как читать график»; единый роутер ссылок страницы
(#s<N>, #p/<P-id>, #registry?…, #gantt/…, #kanban/…, #competitor/…, #mockup/…, #flow/…, #chart/<ключ>/<id>; старые #p=…, #s-N
работают). Цели всех ссылок из meta проверяются по собранной странице: ссылка без цели в панель не попадает (предупреждение;
с --strict — код выхода 1). Графики без meta (старые прогоны) — статичные картинки, как раньше.
  deliverables/data/…               открытые данные рядом: proposals.json|csv, scores.csv, competitors.csv, gantt.csv, kanban.csv, sources.csv
  deliverables/strategy-site.zip    с --zip
  deliverables/.ps-site.json        манифест созданных файлов: пересборка в другом режиме удаляет их (и файлы --lite); чужие не трогает
CSP site: default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' (хеши не нужны). Внешних запросов нет.

--single: CSS, JS, данные и картинки встроены в страницу: каждая картинка — один раз (карта IMG, data URI, ссылка по ключу),
JSON — в <script type="application/json">, CSP с хешами sha256 без внешних источников. Страница > 12 МБ — совет собрать сайт или --lite.
--lite: single, но крупные растровые картинки пишутся файлами в <папка страницы>/assets/ (WebP, если есть Pillow или ffmpeg; иначе
PNG/JPEG как есть), в странице — относительные ссылки и миниатюры ≤ 320 px в data: для превью (полная картинка подгружается,
когда превью видно и крупнее миниатюры). SVG и мелкие картинки встраиваются всегда.
Весь текст из данных экранируется: HTML и скрипты в данных — это данные, не код.

В конце печатает размеры (index.html, assets/, data/, весь сайт), топ-10 самых тяжёлых вложений и предупреждения
(index.html > 1 МБ; сайт > 25 МБ — совет). Только стандартная библиотека (Pillow и ffmpeg — необязательны).
"""
import argparse
import base64
import colorsys
import hashlib
import html
import io
import ipaddress
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from collections import OrderedDict
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlsplit

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

# ---------------------------------------------------------------- отслеживание выполнения (1.2): подписи и значки
# Статус всегда показывается значком и текстом (не только цветом); порядок — для сортировки реестра.
STATUS_ORDER = ["done", "partial", "in_progress", "planned", "blocked", "not_started", "unknown", "obsolete", "dropped"]
STATUS_LABELS = {"done": "выполнено", "partial": "частично", "in_progress": "в работе", "planned": "запланировано",
                 "not_started": "не начато", "blocked": "заблокировано", "dropped": "исключено", "obsolete": "устарело",
                 "unknown": "неясно"}
STATUS_ICONS = {"done": "✓", "partial": "◐", "in_progress": "▸", "planned": "◇", "not_started": "·", "blocked": "⊘",
                "dropped": "✕", "obsolete": "⌀", "unknown": "?"}
STATUS_CLOSED = {"done", "dropped", "obsolete"}
GSTATUS_LABELS = {"done": "выполнено", "partial": "частично", "behind": "отстаёт", "on_track": "по плану", "upcoming": "впереди"}
GSTATUS_ICONS = {"done": "✓", "partial": "◐", "behind": "!", "on_track": "▸", "upcoming": "·"}
SOURCE_LABELS = {"auto": "авто (движок)", "override": "решение владельца", "link": "сохранённая связь"}
MATCH_LABELS = {"explicit": "явно", "saved": "сохранено", "similar": "по сходству", "files": "по файлам", "terms": "по словам"}
ISSUE_STATE_LABELS = {"open": "открыт", "closed": "закрыт", "merged": "влит"}
REVISION_LABELS = {"mark_done": "Отметить выполненным", "obsolete": "Пометить устаревшим", "reprioritize": "Сменить приоритет",
                   "add": "Добавить предложение", "reschedule": "Перенести сроки", "unblock": "Снять блокировку",
                   "drop": "Исключить из плана"}
FACT_LABELS = {"repo_visibility": "Видимость репозитория", "license": "Лицензия", "tests": "Тесты", "prices": "Цены",
               "platform": "Платформа", "stack": "Стек", "routes": "Маршруты", "integrations": "Интеграции"}
SUGGEST_LABELS = {"candidate-proposal": "кандидат в предложения", "bug": "ошибка", "chore": "служебная работа"}
CODE_KIND_LABELS = {"path": "файл", "route": "маршрут", "feature": "функция"}
GH_REMOTE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$")
GH_URL_RE = re.compile(r"^https://github\.com/[A-Za-z0-9._~%/#?=&+:@-]+$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
PROGRESS_MARK_RE = re.compile(r"^\s{0,3}<!--\s*progress:(?:start|end)\s*-->\s*$")


def gh_remote(v):
    """owner/repo из run-config.repo.remote («owner/repo», «https://github.com/owner/repo(.git)», «git@» + «github.com:…» (ssh-форма)) или ""."""
    s = str(v or "").strip()
    m = re.match(r"^(?:https://github\.com/|git@github\.com:)?([^/\s]+/[^/\s]+?)(?:\.git)?/?$", s)
    s = m.group(1) if m else ""
    return s if GH_REMOTE_RE.match(s) and ".." not in s else ""


def gh_url(url, remote="", kind="", ref=None):
    """Ссылка на GitHub: url из данных, только если это https://github.com/…; иначе — собранная из owner/repo
    (issues/N, pull/N, commit/sha); иначе "" (показывается текстом)."""
    u = str(url or "").strip()
    if u and GH_URL_RE.match(u):
        try:
            p = urlsplit(u)
            if p.hostname == "github.com" and p.port is None and not p.username:
                return u
        except ValueError:
            pass
    if not remote or ref in (None, ""):
        return ""
    if kind in ("issue", "pr"):
        n = to_int(ref)
        return "https://github.com/%s/%s/%d" % (remote, "issues" if kind == "issue" else "pull", n) if n and n > 0 else ""
    if kind == "commit":
        return "https://github.com/%s/commit/%s" % (remote, str(ref)) if SHA_RE.match(str(ref)) else ""
    return ""


def gh_link(url, text):
    """<a> на GitHub (новая вкладка) или просто текст."""
    t = esc(text)
    return ('<a class="gh" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + t + "</a>") if url else t


def fmt1(v):
    """Число с одним знаком после запятой без лишнего нуля: 16.7 → «16,7», 2.0 → «2»."""
    x = num(v)
    if x is None:
        return ""
    s = ("%.1f" % x).replace(".", ",")
    return s[:-2] if s.endswith(",0") else s


def ru_date(d):
    """2026-12-19 → «19.12.2026» (иначе как есть)."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(d or ""))
    return "%s.%s.%s" % (m.group(3), m.group(2), m.group(1)) if m else str(d or "")


def st_chip(st, labels=None, icons=None, prefix="pst"):
    """Статусный чип: значок + текст (цвет — дополнительно)."""
    labels, icons = labels or STATUS_LABELS, icons or STATUS_ICONS
    if not st:
        return ""
    return ('<span class="' + prefix + " " + prefix + "-" + esc(slug(st)) + '"><i aria-hidden="true">' + esc(icons.get(st, "•"))
            + "</i> " + esc(labels.get(st, st)) + "</span>")


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


def js_literal(obj):
    """Значение для assets/*.js (JSON как литерал JS): < > & и U+2028/2029 экранированы — безопасно и внутри <script>."""
    t = json.dumps(clean_json(obj), ensure_ascii=False, separators=(",", ":"))
    return t.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


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


HOST_RE = re.compile(r"(?:[\w-]+\.)+[\w-]{2,}", re.U)


def http_url(u):
    """Валидный http(s)-URL (схема, хост с доменом/localhost/IP, без пробелов) или "". «Локальный запуск…»,
    «https://…» (заглушка) и относительные пути — не URL."""
    u = ("" if u is None else str(u)).strip()
    if not re.match(r"^https?://\S+$", u, re.I):
        return ""
    try:
        host = (urlsplit(u).hostname or "").strip(".")
    except ValueError:
        return ""
    if not host:
        return ""
    if host == "localhost" or HOST_RE.fullmatch(host) and not host.startswith("-"):
        return u
    try:
        ipaddress.ip_address(host)
        return u
    except ValueError:
        return ""


def data_url(u):
    """Ссылка из данных (источник, сайт продукта, конкурента): только http(s) или mailto:, иначе ""."""
    s = ("" if u is None else str(u)).strip()
    if re.match(r"^mailto:[^\s@]+@[^\s@]+$", s, re.I):
        return s
    return http_url(s)


def ext_link(url, text=None, cls=""):
    """Внешняя ссылка (новая вкладка) или просто текст, если это не валидный http(s)/mailto-адрес."""
    s = data_url(url)
    t = esc(text) if text not in (None, "") else wbr_long(esc(url))     # голый URL вместо названия — с мягкими переносами
    if not s:
        return t
    c = ' class="' + cls + '"' if cls else ""
    return '<a' + c + ' href="' + esc(s) + '" target="_blank" rel="noopener noreferrer">' + t + "</a>"


def short_url(u, n=48):
    """Домен без www + путь, сокращённо: «example.com/docs/guide/…»."""
    s = ("" if u is None else str(u)).strip()
    try:
        p = urlsplit(s)
        host = (p.hostname or "").lower()
    except ValueError:
        p, host = None, ""
    if host:
        host = host[4:] if host.startswith("www.") else host
        s = host + (p.path if p.path not in ("", "/") else "") + ("?" + p.query if p.query else "")
    else:
        s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", s, flags=re.I)
    s = s.rstrip("/")
    return s if len(s) <= n else s[:n - 1].rstrip("/.-_") + "…"


def url_like_title(title, url):
    """Название источника пустое, равно URL или является обрезанным URL («https://exa…», «example.com/do…»)."""
    raw = str(title or "").strip()
    t = re.sub(r"[\s…]+$|\.{2,}$", "", raw).strip()
    cut_mark = t != raw                       # оканчивалось на «…» или «...»
    if not t:
        return True
    if re.match(r"^(https?://|www\.)", t, re.I):
        return True
    u = str(url or "").strip()
    if not u:
        return False

    def norm(s):
        return re.sub(r"^(https?://)?(www\.)?", "", s.strip().lower()).rstrip("/")
    nt, nu = norm(t), norm(u)
    if not nt or " " in t:
        return False
    if nt == nu:
        return True
    # префикс URL — обрезка, только если похоже на адрес («example.com/do», «exa.») или стоит многоточие; «Example» — название
    return len(nt) >= 6 and nu.startswith(nt) and (cut_mark or "." in t or "/" in t)


def humanize_key(k):
    """Ключ функции snake_case → подпись: «own_channel_analytics» → «Own channel analytics» (целые слова)."""
    s = re.sub(r"\s+", " ", str(k).replace("_", " ")).strip()
    return (s[:1].upper() + s[1:]) if s else str(k)


VERDICT_MAX = 45


def verdict_parts(verdict, verdict_long):
    """(короткий ≤ 45 знаков + «…», длинный текст для карточки, усечён ли короткий без verdict_long)."""
    v = re.sub(r"\s+", " ", str(verdict or "")).strip()
    vl = re.sub(r"\s+", " ", str(verdict_long or "")).strip()
    cut = len(v) > VERDICT_MAX
    short = (v[:VERDICT_MAX].rstrip(" ,.;:—–-") + "…") if cut else v
    if not short and vl:
        short = (vl[:VERDICT_MAX].rstrip(" ,.;:—–-") + "…") if len(vl) > VERDICT_MAX else vl
    return short, (vl or (v if cut else "")), bool(cut and not vl)


# число в ячейке: «12 000», «~50k», «1,5 млн», «≈ 30 %», «12 000+», «$9.99», «12–15k»; «—» и пусто — нейтральны
_NUM_PART = r"\d[\d\s  .,]*\s*(?:%|[kKmMкКмМ]|тыс\.?|млн\.?|млрд\.?|[$€₽£])?"
NUM_CELL_RE = re.compile(r"[~≈<>±+\-−]?\s*[$€₽£]?\s*" + _NUM_PART + r"(?:\s*[–—\-]\s*[$€₽£]?\s*" + _NUM_PART + r")?\s*\+?")


def is_num_text(v):
    """Значение выглядит как число (с разрядами, знаком, % или сокращением тыс./млн/k/M) — без слов вокруг."""
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    return bool(NUM_CELL_RE.fullmatch(str(v or "").strip()))


def num_col(values):
    """Класс num (вправо, без переноса) — только если ВСЕ непустые значения колонки числа (A-1.13, B-48): длинная текстовая
    «аудитория» в колонке num с white-space:nowrap раздувала таблицу «Сообщества» за рамку."""
    vals = [v for v in values if not (v is None or (isinstance(v, str) and v.strip() in ("", "—", "-", "–")))]
    return bool(vals) and all(is_num_text(v) for v in vals)


LONG_TOKEN_RE = re.compile(r"[^\s<>]{22,}")


def wbr_long(html_text):
    """Мягкие переносы <wbr> в длинных «словах» без пробелов (URL, пути, camelCase, snake_case) внутри текста HTML —
    только вне тегов. Обычные слова не трогаются: колонка таблицы не сжимается до обрывков, но и не раздувается."""
    def fix(m):
        ents = []

        def keep(e):                       # сущности (&amp; &#39;) — целиком, без переносов внутри
            ents.append(e.group(0))
            return "\x00%d\x00" % (len(ents) - 1)
        t = re.sub(r"&(?:\w+|#\d+|#x[0-9a-fA-F]+);", keep, m.group(0))
        t = re.sub(r"([/_.=?\-:,;])(?=[^\s/_.=?\-:,;\x00])", r"\1<wbr>", t)
        t = re.sub(r"(?<=[a-zа-яё])(?=[A-ZА-ЯЁ])", "<wbr>", t)
        t = re.sub(r"(\x00\d+\x00)(?=[^\s\x00])", r"\1<wbr>", t) if "\x00" in t else t
        return re.sub(r"\x00(\d+)\x00", lambda e: ents[int(e.group(1))], t)
    parts = re.split(r"(<[^>]*>)", html_text or "")
    return "".join(p if p.startswith("<") else LONG_TOKEN_RE.sub(fix, p) for p in parts)


def _same_value(a, b):
    """Значения TypeSafe совпадают по смыслу: числа — с точностью округления score.py, строки — без регистра."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 0.005 + 1e-9
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().casefold() == b.strip().casefold()
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_same_value(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same_value(x, y) for x, y in zip(a, b))
    return a == b


def merge_typesafe(ts, jev):
    """Один блок TypeSafe для карточки из scores.json (typesafe) и typesafe-jev.json: совпадающие по смыслу значения —
    один раз; расходящиеся — «score.py / Jev» в одном поле. None — данных нет."""
    ts = ts if isinstance(ts, dict) else {}
    jev = jev if isinstance(jev, dict) else {}
    if not ts and not jev:
        return None
    if not ts or not jev:
        return {"title": "TypeSafe Jev" if jev else "TypeSafe (score.py)", "items": dict(jev or ts), "conflicts": []}
    items, conflicts = {}, []
    for k in list(jev) + [k for k in ts if k not in jev]:
        if k not in ts:
            items[k] = jev[k]
        elif k not in jev:
            items[k] = ts[k]
        elif _same_value(ts[k], jev[k]):
            items[k] = jev[k]
        else:
            items[k] = {"score.py": ts[k], "Jev": jev[k]}
            conflicts.append(str(k))
    title = "TypeSafe Jev" + (" (score.py = Jev)" if not conflicts else " и score.py (расходятся: " + ", ".join(conflicts) + ")")
    return {"title": title, "items": items, "conflicts": conflicts}


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


LITE_INLINE_MAX = 32 * 1024    # --lite: картинки меньше этого (и все SVG) встраиваются как есть
THUMB_MAX = 320                # --lite: миниатюра — не больше 320 px по большей стороне
ASSETS_MANIFEST = ".ps-assets.json"


class LiteEncoder:
    """Перекодирование для --lite: Pillow (если установлен и умеет WebP) → ffmpeg → без перекодирования.
    full() — полная картинка (WebP, если он меньше исходника), thumb() — миниатюра ≤ 320 px (WebP или JPEG)."""

    def __init__(self, want="auto", warn=None):
        self.warn = warn or (lambda m: None)
        self.kind, self.ffmpeg, self.ff_webp, self.Image = "none", None, False, None
        if want in ("auto", "pillow"):
            try:
                from PIL import Image, features   # необязательная зависимость
                if features.check("webp"):
                    self.kind, self.Image = "pillow", Image
            except Exception:                      # нет Pillow или он без WebP
                pass
        if self.kind == "none" and want in ("auto", "ffmpeg"):
            ff = shutil.which("ffmpeg")
            if ff:
                self.ffmpeg, self.kind = ff, "ffmpeg"
                try:
                    enc = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30).stdout
                    self.ff_webp = " libwebp " in enc
                except (OSError, subprocess.SubprocessError):
                    self.ff_webp = False
        if want in ("pillow", "ffmpeg") and self.kind != want:
            self.warn("--lite-encoder %s недоступен — использую: %s" % (want, self.label()))

    def label(self):
        return {"pillow": "Pillow (WebP)", "ffmpeg": "ffmpeg (" + ("WebP" if self.ff_webp else "JPEG-миниатюры, полные — как есть") + ")",
                "none": "без перекодирования (нет Pillow и ffmpeg): файлы как есть, без миниатюр"}[self.kind]

    # --- Pillow
    def _pil_open(self, data):
        im = self.Image.open(io.BytesIO(data))
        im.load()
        has_alpha = "A" in im.getbands() or (im.mode == "P" and "transparency" in im.info)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if has_alpha else "RGB")
        return im

    def _pil_save(self, im, quality):
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=quality, method=4)
        return buf.getvalue()

    # --- ffmpeg
    def _ff(self, src, out_name, vf=None, codec=None):
        with tempfile.TemporaryDirectory(prefix="ps-lite-") as td:
            dst = os.path.join(td, out_name)
            cmd = [self.ffmpeg, "-v", "error", "-nostdin", "-y", "-i", str(src)]
            if vf:
                cmd += ["-vf", vf]
            cmd += codec + ["-frames:v", "1", dst]
            r = subprocess.run(cmd, capture_output=True, timeout=120)
            if r.returncode != 0 or not os.path.isfile(dst):
                raise RuntimeError((r.stderr or b"").decode("utf-8", "replace").strip()[:160] or "ffmpeg: ошибка")
            with open(dst, "rb") as f:
                return f.read()

    def full(self, src, data, mime):
        """(байты, mime) полной картинки для assets/."""
        if mime not in ("image/png", "image/jpeg", "image/webp") or self.kind == "none":
            return data, mime
        try:
            if self.kind == "pillow":
                out = self._pil_save(self._pil_open(data), 82)
            elif self.ff_webp:
                out = self._ff(src, "full.webp", codec=["-c:v", "libwebp", "-quality", "82", "-compression_level", "4"])
            else:
                return data, mime
        except Exception as e:  # битая картинка, ошибка кодировщика — оставить как есть
            self.warn("--lite: не перекодировать %s (%s) — файл как есть" % (Path(str(src)).name, str(e)[:100]))
            return data, mime
        return (out, "image/webp") if out and len(out) < len(data) else (data, mime)

    def thumb(self, src, data, mime):
        """(байты, mime) миниатюры ≤ 320 px или None (нет кодировщика / ошибка)."""
        if self.kind == "none" or mime not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
            return None
        try:
            if self.kind == "pillow":
                im = self._pil_open(data)
                im.thumbnail((THUMB_MAX, THUMB_MAX))
                return self._pil_save(im, 72), "image/webp"
            vf = ("scale=w='min(%d,iw)':h='min(%d,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2" % (THUMB_MAX, THUMB_MAX))
            if self.ff_webp:
                return self._ff(src, "t.webp", vf, ["-c:v", "libwebp", "-quality", "72"]), "image/webp"
            return self._ff(src, "t.jpg", vf, ["-c:v", "mjpeg", "-q:v", "5", "-pix_fmt", "yuvj420p"]), "image/jpeg"
        except Exception as e:
            self.warn("--lite: нет миниатюры для %s (%s)" % (Path(str(src)).name, str(e)[:100]))
            return None


class LiteStore:
    """Файлы --lite: <папка страницы>/assets/<ключ>-<хеш>.<ext>; повторная сборка не перекодирует одинаковые файлы
    (имя по хешу исходника), а файлы прошлых сборок, которых больше нет на странице, удаляются по манифесту."""

    EXT = {"image/webp": ".webp", "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif"}

    def __init__(self, page_dir, encoder):
        self.dir = Path(page_dir) / "assets"
        self.enc = encoder
        self.written = {}            # имя файла → байты
        self.thumb_bytes = 0

    def wants(self, mime, size):
        """--lite: растровые картинки крупнее LITE_INLINE_MAX — файлом; SVG и мелочь — встраиваются."""
        return mime != "image/svg+xml" and size > LITE_INLINE_MAX

    def store(self, src, data, mime, key):
        """→ (относительный URL, размер файла, (data URI миниатюры, ширина) | None)."""
        h = hashlib.sha1(data).hexdigest()[:10]
        stem = slug(key)[:60] + "-" + h
        existing = [p for p in (self.dir.glob(stem + ".*") if self.dir.is_dir() else []) if p.suffix in self.EXT.values()]
        if existing:
            name, size = existing[0].name, existing[0].stat().st_size
        else:
            out, omime = self.enc.full(src, data, mime)
            name = stem + self.EXT.get(omime, Path(str(src)).suffix.lower() or ".bin")
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / name).write_bytes(out)
            size = len(out)
        self.written[name] = size
        th = self.enc.thumb(src, data, mime)
        thumb = None
        if th:
            tb, tm = th
            tw, _ = image_size(tb, tm)
            uri = "data:" + tm + ";base64," + base64.b64encode(tb).decode("ascii")
            self.thumb_bytes += len(uri)
            thumb = (uri, tw or THUMB_MAX)
        return "assets/" + quote(name), size, thumb

    def finish(self):
        """Манифест и удаление файлов прошлых сборок, которых нет на этой странице (только свои, по манифесту)."""
        old = read_manifest(self.dir)
        for name in old:
            if name not in self.written and "/" not in name and "\\" not in name:
                try:
                    (self.dir / name).unlink()
                except OSError:
                    pass
        if self.written:
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / ASSETS_MANIFEST).write_text(json.dumps(sorted(self.written), ensure_ascii=False, indent=1), encoding="utf-8")
        elif (self.dir / ASSETS_MANIFEST).is_file():
            (self.dir / ASSETS_MANIFEST).unlink()


class SiteStore(LiteStore):
    """Картинки режима site: assets/img/<ключ>-<хеш>.<ext> (одна копия на изображение; WebP при Pillow/ffmpeg, иначе как есть),
    миниатюры (картинки > 32 КБ) — assets/img/thumbs/. SVG пишется как есть. В странице — только относительные ссылки.
    written: путь относительно папки страницы → размер (для манифеста и очистки)."""

    EXT = dict(LiteStore.EXT, **{"image/svg+xml": ".svg"})

    def __init__(self, page_dir, encoder):
        super().__init__(page_dir, encoder)
        self.dir = Path(page_dir) / "assets" / "img"
        self.tdir = self.dir / "thumbs"

    def wants(self, mime, size):
        return mime in self.EXT

    def store(self, src, data, mime, key):
        """→ (относительный URL, размер файла, (URL миниатюры, ширина) | None)."""
        h = hashlib.sha1(data).hexdigest()[:10]
        stem = slug(key)[:60] + "-" + h
        existing = [p for p in (self.dir.glob(stem + ".*") if self.dir.is_dir() else []) if p.suffix in self.EXT.values()]
        if existing:
            name, size = existing[0].name, existing[0].stat().st_size
        else:
            out, omime = (data, mime) if mime == "image/svg+xml" else self.enc.full(src, data, mime)
            name = stem + self.EXT.get(omime, Path(str(src)).suffix.lower() or ".bin")
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / name).write_bytes(out)
            size = len(out)
        self.written["assets/img/" + name] = size
        thumb = None
        th = self.enc.thumb(src, data, mime) if len(data) > LITE_INLINE_MAX else None
        if th:
            tb, tm = th
            tname = stem + self.EXT.get(tm, ".webp")
            self.tdir.mkdir(parents=True, exist_ok=True)
            (self.tdir / tname).write_bytes(tb)
            self.written["assets/img/thumbs/" + tname] = len(tb)
            self.thumb_bytes += len(tb)
            tw, _ = image_size(tb, tm)
            thumb = ("assets/img/thumbs/" + quote(tname), tw or THUMB_MAX)
        return "assets/img/" + quote(name), size, thumb

    def finish(self):
        pass                                   # манифест и очистка — cleanup_previous() в main()


SITE_MANIFEST = ".ps-site.json"
ZIP_NAME = "strategy-site.zip"


def read_site_manifest(page_dir):
    try:
        v = json.loads((Path(page_dir) / SITE_MANIFEST).read_text(encoding="utf-8"))
        return [str(x) for x in v.get("files", [])] if isinstance(v, dict) else []
    except (OSError, ValueError):
        return []


def write_site_manifest(page_dir, files):
    f = Path(page_dir) / SITE_MANIFEST
    if files:
        f.write_text(json.dumps({"version": 1, "note": "файлы, созданные build_html.py (режим site); пересборка в другом режиме удаляет их",
                                 "files": sorted(files)}, ensure_ascii=False, indent=1), encoding="utf-8")
    elif f.is_file():
        f.unlink()


def cleanup_previous(page_dir, keep):
    """Удалить файлы прошлых сборок (site по .ps-site.json и --lite по assets/.ps-assets.json), которых нет в keep
    (пути относительно папки страницы, posix). Чужие файлы не трогаются. → число удалённых файлов."""
    page_dir = Path(page_dir).resolve()
    old = set(read_site_manifest(page_dir))
    old.update("assets/" + n for n in read_manifest(page_dir / "assets"))
    n = 0
    for rel in sorted(old - set(keep)):
        parts = rel.replace("\\", "/").split("/")
        if rel.startswith("/") or ".." in parts or not rel:
            continue
        f = (page_dir / rel)
        try:
            f.resolve().relative_to(page_dir)
            if f.is_file():
                f.unlink()
                n += 1
        except (OSError, ValueError):
            pass
    for d in sorted({(page_dir / r).parent for r in old}, key=lambda x: -len(x.parts)):     # пустые папки, оставшиеся от режима
        while d != page_dir and page_dir in d.parents:
            try:
                d.rmdir()
            except OSError:
                break
            d = d.parent
    return n


def read_manifest(d):
    try:
        v = json.loads((Path(d) / ASSETS_MANIFEST).read_text(encoding="utf-8"))
        return [str(x) for x in v] if isinstance(v, list) else []
    except (OSError, ValueError):
        return []


def drop_stale_assets(page_dir):
    """Обычная (автономная) сборка: файлы прошлой --lite-сборки рядом со страницей больше не нужны — удалить свои."""
    d = Path(page_dir) / "assets"
    names = read_manifest(d)
    for name in names:
        if "/" not in name and "\\" not in name:
            try:
                (d / name).unlink()
            except OSError:
                pass
    try:
        (d / ASSETS_MANIFEST).unlink()
        d.rmdir()
    except OSError:
        pass
    return len(names)


class Images:
    """Каждая картинка встраивается один раз: ключ → data URI; повторные ссылки на тот же файл получают тот же ключ.
    С lite (LiteStore) крупные растровые картинки — файлы в assets/: ключ → относительный URL, миниатюра — в thumbs."""

    def __init__(self, base, warn, lite=None):
        self.base = base.resolve()
        self.warn = warn
        self.lite = lite
        self.map = {}
        self.meta = {}
        self.thumbs = {}
        self.alias = {}          # ключ → ключ с тем же содержимым (PNG макета и его референса — один файл под двумя путями)
        self.by_path = {}
        self.by_hash = {}

    def has(self, k):
        return bool(k) and (k in self.map or k in self.alias)

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
        while k in self.map or k in self.alias:
            k, n = key + "-" + str(n), n + 1
        w, h = image_size(data, mime)
        digest = hashlib.sha1(data).hexdigest()
        if digest in self.by_hash:          # то же содержимое по другому пути — свой ключ, общие байты
            first = self.by_hash[digest]
            self.alias[k] = first
            self.meta[k] = dict(self.meta[first], src=self.rel(p), bytes=0, alias=first)
            self.meta[k].pop("asset_bytes", None)
            self.meta[k].pop("asset", None)
            self.by_path[p] = k
            return k
        self.by_hash[digest] = k
        if self.lite and self.lite.wants(mime, len(data)):
            url, size, thumb = self.lite.store(p, data, mime, k)
            self.map[k] = url
            self.meta[k] = {"src": self.rel(p), "bytes": len(thumb[0]) if thumb else 0, "w": w, "h": h, "mime": mime,
                            "asset": url, "asset_bytes": size}
            if thumb:
                self.thumbs[k] = [thumb[0], thumb[1]]
        else:
            uri = "data:" + mime + ";base64," + base64.b64encode(data).decode("ascii")
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


def chart_svg_fragment(src):
    """SVG интерактивного графика → фрагмент для DOM страницы. В отличие от sanitize_svg классы и id не переименовываются
    (панель пояснений ищет .ps-el и data-ps-*), а <style> удаляется целиком: встроенный стиль действовал бы на всю страницу."""
    m = re.search(r"<svg\b.*</svg\s*>", src or "", re.S | re.I)
    if not m:
        return None
    s = m.group(0)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", lambda mm: mm.group(1).replace("<", "&lt;"), s, flags=re.S)
    for tag in ("script", "style", "foreignObject", "iframe", "object", "embed", "audio", "video", "canvas", "handler",
                "listener", "set", "animate", "a"):
        s = re.sub(r"<" + tag + r"\b[^>]*?/>", "", s, flags=re.I)
        s = re.sub(r"<" + tag + r"\b.*?</" + tag + r"\s*>", "", s, flags=re.S | re.I) if tag != "a" else \
            re.sub(r"</?a\b[^>]*>", "", s, flags=re.I)
        s = re.sub(r"<" + tag + r"\b[^>]*>", "", s, flags=re.I)
    s = re.sub(r"\s+on[a-zA-Z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", s)
    s = re.sub(r"\s((?:xlink:)?href)\s*=\s*([\"'])(?!#)(.*?)\2", "", s, flags=re.I | re.S)
    s = re.sub(r"url\(\s*(['\"]?)(?!#)[^)]*\)", "none", s, flags=re.I)
    root = re.match(r"<svg\b[^>]*>", s, re.S).group(0)
    new = re.sub(r"\s(width|height)\s*=\s*([\"']).*?\2", "", root, flags=re.S)
    if not re.search(r"\sviewBox\s*=", new):
        w, h = svg_size(root)
        if w and h:
            new = new[:-1] + ' viewBox="0 0 %d %d">' % (w, h)
    return new + s[len(root):]


def svg_viewbox(s):
    """(ширина, высота) из viewBox корневого <svg> (или width/height); None — не найдено."""
    m = re.search(r"<svg\b[^>]*>", s or "", re.S | re.I)
    if not m:
        return None
    vb = re.search(r"\sviewBox\s*=\s*[\"']\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)", m.group(0))
    if vb and float(vb.group(1)) > 0 and float(vb.group(2)) > 0:
        return float(vb.group(1)), float(vb.group(2))
    w, h = svg_size(m.group(0))
    return (float(w), float(h)) if w and h else None


def flow_a11y(svg_html, scope, nodes, title):
    """Доступность встроенной схемы (FB-038): корень — role="group" (role="img" прятал блоки-кнопки от экранного диктора),
    aria-labelledby — только на существующие (переименованные областью) id, иначе aria-label = название схемы; у каждого блока
    data-node — <title> (из flows.json → nodes[].what, иначе label) и aria-label «… — открыть расшифровку». <title> уже есть —
    не трогается."""
    if not svg_html:
        return svg_html
    ids = set(re.findall(r"\sid\s*=\s*\"([^\"]+)\"", svg_html))
    root = re.match(r"<svg\b[^>]*>", svg_html, re.S).group(0)
    new = root
    if re.search(r"\srole\s*=\s*\"img\"", new):
        new = re.sub(r"\srole\s*=\s*\"img\"", ' role="group"', new, count=1)
    elif not re.search(r"\srole\s*=", new):
        new = new[:-1] + ' role="group">'
    lab = re.search(r"\saria-labelledby\s*=\s*\"([^\"]*)\"", new)
    keep = []
    if lab:
        for tok in lab.group(1).split():
            if scope + "-" + tok in ids:
                keep.append(scope + "-" + tok)
            elif tok in ids:
                keep.append(tok)
        new = new.replace(lab.group(0), (' aria-labelledby="' + " ".join(keep) + '"') if keep else "", 1)
    if not keep and not re.search(r"\saria-label\s*=", new):
        new = new[:-1] + ' aria-label="' + esc(title) + '">'
    s = new + svg_html[len(root):]

    def node(mm):
        tag, node_id, end = mm.group(0), html.unescape(mm.group(2)), mm.group(3)
        n = nodes.get(node_id) or {}
        label = text_of(n.get("label")) or node_id
        if "aria-label" not in tag:
            tag = tag[:-len(end)] + ' aria-label="' + esc(label + " — открыть расшифровку") + '"' + end
        if end == "/>":
            return tag
        rest = s[mm.end():mm.end() + 400]
        if re.match(r"\s*<title\b", rest):
            return tag
        what = text_of(n.get("what")).strip()
        return tag + '<title class="ps-nt">' + esc(label + (": " + what if what and what != label else "")) + "</title>"
    return re.sub(r"<([a-zA-Z][\w:-]*)\s(?:[^>]*?\s)?data-node\s*=\s*\"([^\"]+)\"[^>]*?(/?>)", node, s)


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
            # «dark» внутри :not(...) — это НЕ тёмная тема (:root:not([data-theme="dark"]) в светлом @media — B-48: светлые
            # токены уходили в тёмную тему, и статус-метки #4ade80 оказывались на светлом фоне)
            sel_pos = re.sub(r":not\([^()]*(?:\([^()]*\)[^()]*)*\)", "", sel)
            if sel.startswith("@media") and re.search(r"prefers-color-scheme\s*:\s*light", sel):
                is_dark = False
            else:
                is_dark = in_dark or "dark" in sel_pos
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
        if (mode == "dark") != (luminance(bg) < 0.2):
            continue      # «тёмные» токены со светлым фоном (или наоборот) — тема страницы остаётся нейтральной, а не перевёрнутой
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
        link = fit_contrast(link, md["surface-2"])      # раскрытая строка реестра, шапки таблиц
        on_acc = (255, 255, 255) if contrast(acc, (255, 255, 255)) >= contrast(acc, (17, 17, 17)) else (17, 17, 17)
        ok, bad = status_colors(md, m)
        out[m] = {
            "--ps-bg": hexc(md["bg"]), "--ps-surface": hexc(md["surface"]), "--ps-surface-2": hexc(md["surface-2"]),
            "--ps-text": hexc(md["text"]), "--ps-muted": hexc(md["muted"]), "--ps-border": hexc(md["border"]),
            "--ps-accent": hexc(acc), "--ps-link": hexc(link), "--ps-accent-text": hexc(link), "--ps-on-accent": hexc(on_acc),
            "--ps-accent-soft": "rgba(%d,%d,%d,%s)" % (acc[0], acc[1], acc[2], ".13" if m == "light" else ".22"),
            "--ps-ok": hexc(ok), "--ps-bad": hexc(bad),
            "--ps-font": font, "--ps-radius": radius.strip(),
        }
    return out


STATUS_BASE = {"light": ((22, 101, 52), (159, 31, 20)), "dark": ((74, 222, 128), (248, 113, 113))}


def status_colors(md, mode):
    """Цвета статус-меток (.st-ok/.ok/✓ матрицы, .st-bad) под фон темы: ≥ 4,5:1 на surface, surface-2, на своей
    полупрозрачной подложке и на строке «мы» матрицы (accent-soft) — B-48: цвет не должен расходиться с фоном."""
    surf, surf2, acc = md["surface"], md["surface-2"], md["accent"]
    soft = 0.13 if mode == "light" else 0.22
    out = []
    for base, tint in zip(STATUS_BASE[mode], ((21, 128, 61), (180, 35, 24))):
        bgs = [surf, surf2, mix(surf, tint, 0.14), mix(surf2, tint, 0.14), mix(surf, acc, soft), mix(surf2, acc, soft)]
        c = base
        for _ in range(3):
            for bg in bgs:
                c = fit_contrast(c, bg)
            if all(contrast(c, bg) >= 4.5 for bg in bgs):
                break
        out.append(c)
    return out[0], out[1]


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
            body = self.inline(txt)
            return "<" + tag + (' class="al-' + al + '"' if al else "") + ">" + (wbr_long(body) if tag == "td" else body) + "</" + tag + ">"

        def blank(v):
            return not re.sub(r"[\s—–\-]+", "", v or "")
        # FB-039: колонка, пустая во всех строках (или только тире), не выводится — «пустая колонка “Значение”»
        cols = [k for k in range(ncol) if not (rows and all(blank(r[k] if k < len(r) else "") for r in rows))] or list(range(ncol))
        thead = "".join(cell("th", head[k], k) for k in cols)
        body = "".join("<tr>" + "".join(cell("td", r[k] if k < len(r) else "", k) for k in cols) + "</tr>" for r in rows)
        many = ' class="many"' if len(cols) >= 7 else ""     # много столбцов — компактнее, чтобы на 1440 влезть в рамку
        return '<div class="tbl"><table' + many + '>' + self._colgroup(head, rows, cols) + '<thead><tr>' + thead + "</tr></thead><tbody>" + body + "</tbody></table></div>", i

    @staticmethod
    def _colgroup(head, rows, cols):
        """Ширины колонок, если у колонки короткие значения (медиана < 20 знаков), но одно-два длинных (> 40 знаков и в 2,5 раза длиннее
        медианы): без подсказки браузер отдаёт такой колонке пол-таблицы («пустая область», smoke). Ширина такой колонки — по медиане
        длины, остальных — по 75-му перцентилю (4…60 знаков, не уже заголовка); таблицы без таких колонок не меняются."""
        if len(cols) < 3 or len(rows) < 2:
            return ""
        plain_len = lambda v: len(re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", re.sub(r"[*_`]", "", v or "")).strip())
        stats, need = [], False
        for k in cols:
            ls = sorted(plain_len(r[k] if k < len(r) else "") for r in rows)
            ls = [x for x in ls if x] or [0]
            med, top, p75 = ls[len(ls) // 2], ls[-1], ls[min(len(ls) - 1, int(len(ls) * 0.75))]
            outlier = med < 20 and top > 40 and top > 2.5 * max(med, 1)
            need = need or outlier
            # колонке-«выбросу» — ширина по медиане (длинное значение переносится), остальным — по 75-му перцентилю
            stats.append(max(4, min(60, max(med if outlier else p75, plain_len(head[k]) if k < len(head) else 0))))
        if not need:
            return ""
        tot = float(sum(stats))
        return "<colgroup>" + "".join('<col style="width:%.1f%%">' % (100.0 * s / tot) for s in stats) + "</colgroup>"

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


# ---------------------------------------------------------------- слой интерактивности 1.5 (FB-035): обёртки, кнопки, подсказки
PSI_HINT = "Графики и схемы кликабельны: наведите — подсказка, нажмите — подробности, 🔍 — увеличить."
SITE_TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "site"
LAYER_JS_FILES = ("ps-interact.js", "ps-search.js", "ps-ents.js")
LAYER_CSS_FILE = "ps-layer.css"
LAYER_MARK = ("/* ps-1.5:start — слои страницы (templates/site) */\n", "\n/* ps-1.5:end */\n")


def psi_hint(top=False):
    return ('<p class="psi-hint"' + (' data-psi-top="1"' if top else "") + '><span aria-hidden="true">👆</span> ' + esc(PSI_HINT) + "</p>")


def psi_wrap(kind, box, title):
    """Обёртка графика или схемы: видимая кнопка «🔍 Увеличить» в углу (на телефоне — над картинкой) и плашка при наведении.
    Разметка закрывается сразу после плашки — так её можно однозначно найти и в тестах, и в регрессии."""
    what = "схему" if kind == "flow" else "график"
    cue = ("Наведите на блок — подсказка · нажмите — расшифровка · фон — увеличить" if kind == "flow"
           else "Наведите на элемент — подсказка · нажмите — подробности · фон — увеличить")
    return ('<div class="psi-wrap psi-' + kind + '">' + box + '<button type="button" class="psi-zoom" aria-label="Увеличить ' + what + " «"
            + esc(title) + '» и открыть подробности" title="Открыть крупно: масштаб, подсказки и подробности по каждому элементу">'
            '<span aria-hidden="true">🔍</span> Увеличить</button><span class="psi-cue" aria-hidden="true">' + cue + "</span></div>")


def layer_assets(warn):
    """JS и CSS слоёв страницы из templates/site (просмотр графиков и схем, поиск, сущности). Нет файлов — страница без слоёв
    и предупреждение (сборщик скопирован без папки templates/)."""
    js, css = [], ""
    for name in LAYER_JS_FILES:
        p = SITE_TEMPLATES / name
        try:
            js.append(p.read_text(encoding="utf-8"))
        except OSError:
            warn("нет templates/site/%s — слой страницы не подключён (переустановите плагин)" % name)
    try:
        css = LAYER_MARK[0] + (SITE_TEMPLATES / LAYER_CSS_FILE).read_text(encoding="utf-8") + LAYER_MARK[1]
    except OSError:
        warn("нет templates/site/%s — стили слоёв не подключены" % LAYER_CSS_FILE)
    return "\n".join(js), css


GLOSS_ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")
GLOSS_TERM_RE = re.compile(r"^- \*\*(.+?)\*\*(?: \[синонимы: (.+?)\])? — (.+)$")


def parse_glossary(text, dictionary=""):
    """research/glossary.md (build_appendix.py: таблица «| Термин | Значение |» + термины, дописанные оркестратором) →
    [{key, label, forms, ci, what, src}]; синонимы — из словаря templates/glossary.md (строки «- **Термин** [синонимы: a; b] — …»)."""
    syn = {}
    for ln in (dictionary or "").splitlines():
        m = GLOSS_TERM_RE.match(ln.strip())
        if m:
            syn[m.group(1).strip()] = [x.strip() for x in (m.group(2) or "").split(";") if x.strip()]
    out, seen = [], set()
    for ln in (text or "").splitlines():
        m = GLOSS_ROW_RE.match(ln.strip())
        if m:
            term, what = m.group(1).strip(), m.group(2).strip()
            if term.lower() in ("термин", "term") or set(term) <= set("-: "):
                continue
        else:
            m = GLOSS_TERM_RE.match(ln.strip())
            if not m:
                continue
            term, what = m.group(1).strip(), m.group(3).strip()
            syn.setdefault(term, [x.strip() for x in (m.group(2) or "").split(";") if x.strip()])
        term = re.sub(r"[*_`]", "", term).strip()
        what = re.sub(r"\*\*|__|`", "", what).strip()
        key = re.sub(r"[^\w]+", "-", term.lower()).strip("-_") or "t%d" % len(out)
        if not term or key in seen:
            continue
        seen.add(key)
        forms = [term] + [x for x in syn.get(term, []) if x and x != term]
        src = ""
        ms = re.search(r"\s*\((?:источник|source):\s*([^)]+)\)\s*$", what, re.I)
        if ms:
            src, what = ms.group(1).strip(), what[:ms.start()].strip()
        out.append({"key": key, "label": term, "forms": forms, "ci": True, "what": what, "src": src})
    return out


def md_blocks(text, limit=200000):
    """Текст исследования для поиска: без разметки Markdown, не длиннее limit знаков."""
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    t = re.sub(r"!\[\[[^\]]*\]\]", " ", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"[*_`>|]", " ", t)
    t = re.sub(r"[ \t]+", " ", t)
    return t[:limit]


# ---------------------------------------------------------------- сборщик
class Builder:
    def __init__(self, out, out_file, title=None, lite=False, lite_encoder="auto", site=False, site_csp="self"):
        self.out = out.resolve()
        self.out_file = out_file
        self.warnings = []
        self.strict_errors = []                # --strict: эти предупреждения — ошибка (код выхода 1)
        self.lite = None
        self.site = bool(site)                 # режим site: оболочка + assets/ + data/ (см. references/interactive-site.md)
        self.site_csp = site_csp               # "self" (CSP 'self') | "none" (запасной вариант без CSP-мета)
        self.site_files = {}                   # относительный путь → байты (app.css, app.js, data.js, head.js, extra.*, charts.js)
        if self.site:
            self.lite = SiteStore(out_file.parent, LiteEncoder(lite_encoder, self.warn))
        elif lite:
            self.lite = LiteStore(out_file.parent, LiteEncoder(lite_encoder, self.warn))
        self.img = Images(self.out, self.warn, self.lite)
        self.cfg = self.json("build/run-config.json", dict) or {}
        self.author = self.cfg.get("author") if isinstance(self.cfg.get("author"), dict) else {}
        created = str(self.cfg.get("created") or "")
        self.date = created if re.match(r"^\d{4}-\d{2}-\d{2}$", created) else date.today().isoformat()
        self.title_arg = title
        self.nav = []          # (id, label, group)
        self.sections = []     # html
        self.figs = 0
        self.anchors = {"gantt": set(), "kanban": set(), "mockup": set(), "flow": set()}   # цели ссылок #gantt/…, #kanban/…, #mockup/…, #flow/…
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
        # режим «Идея → концепция» (run-config mode: concept): продукта ещё нет, репозиторий не сканировался
        self.concept = self.cfg.get("mode") == "concept"
        self.idea = (self.json("data/idea.json", dict) or {}) if self.concept else {}
        self.viab = (self.json("data/typesafe-concept.json", dict) or {}) if self.concept else {}
        self.load_charts()
        self.load_refs()
        self.load_mockups()
        self.load_flows()
        self.load_progress()
        # 1.5: есть графики/схемы с интерактивностью → подсказки «кликабельны» и кнопки увеличения; глоссарий и прочие исследования
        self.has_psi = bool(self.ich) or any(fl.get("src") for fl in self.flow_list)
        self.gloss = self.load_glossary()
        self.docs = self.load_docs()

    def load_glossary(self):
        """research/glossary.md (build_appendix.py) → термины для раздела «Глоссарий», подсказок и кликабельных терминов текста."""
        text = self.text("research/glossary.md")
        if not text or not text.strip():
            return []
        try:
            dic = (SITE_TEMPLATES.parent / "glossary.md").read_text(encoding="utf-8")
        except OSError:
            dic = ""
        g = parse_glossary(text, dic)
        if not g:
            self.warn("research/glossary.md: нет строк «| Термин | Значение |» — глоссарий и термины текста не показаны")
        return g

    DOCS_SKIP = {"strategy.md", "questions-owner.md", "glossary.md"}
    DOCS_TOTAL_MAX = 3 * 1024 * 1024

    def load_docs(self):
        """Прочие исследования research/**/*.md (кроме выведенных на страницу) — только для сквозного поиска: текст без разметки,
        не больше 200 000 знаков на файл и 3 МБ всего; ссылка на файл рядом."""
        d = self.out / "research"
        if not d.is_dir():
            return []
        out, total = [], 0
        for p in sorted(d.rglob("*.md")):
            rel = p.relative_to(self.out).as_posix()
            if p.name in self.DOCS_SKIP and p.parent == d or p.name.endswith(".generated.md"):
                continue
            try:
                raw = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = re.search(r"^\s{0,3}#\s+(.+?)\s*#*\s*$", raw, re.M)
            text = md_blocks(raw)
            if total + len(text) > self.DOCS_TOTAL_MAX:
                self.warn("поиск: исследования больше 3 МБ текста — %s и дальше в индекс не вошли" % rel)
                break
            total += len(text)
            out.append({"path": rel, "title": (m.group(1).strip() if m else p.stem), "text": text, "href": self.rel_link(rel)})
        return out

    # --- отслеживание выполнения (1.2): data/progress.json и сопутствующие; нет progress.json — страница прежняя
    def load_progress(self):
        self.pg = None
        pg = self.json("data/progress.json", dict)
        if not pg:
            return
        repo = self.cfg.get("repo") if isinstance(self.cfg.get("repo"), dict) else {}
        self.gh_repo = gh_remote(repo.get("remote")) or gh_remote(pg.get("remote"))     # движок пишет remote в progress.json
        raw = pg.get("items") if isinstance(pg.get("items"), dict) else {}
        if not raw:
            self.warn("data/progress.json: нет items — статусы предложений не показаны")
        known = {p["id"] for p in self.P}
        extra = [k for k in raw if k not in known]
        if extra and known:
            self.warn("data/progress.json: %d id нет в реестре (%s…)" % (len(extra), ", ".join(map(str, extra[:3]))))
        self.pg_items = {str(k): self.norm_item(v) for k, v in raw.items() if isinstance(v, dict) and str(k) in known}
        self.pg = pg
        self.pg_month = to_int(pg.get("month_index"))
        self.pg_elapsed = num(pg.get("months_elapsed"))
        # Гант по фактам: {"current_month", "tasks"} или просто список задач
        gp = self.json("data/gantt-progress.json")
        tasks, cm = [], None
        if isinstance(gp, dict):
            tasks, cm = [t for t in as_list(gp.get("tasks")) if isinstance(t, dict)], to_int(gp.get("current_month"))
        elif isinstance(gp, list):
            tasks = [t for t in gp if isinstance(t, dict)]
        elif gp is not None:
            self.warn("data/gantt-progress.json: ожидался объект {current_month, tasks} или список — пропущен")
        self.pg_cur = cm or self.pg_month
        self.pg_gantt = {}
        for t in tasks:
            st = str(t.get("status") or "")
            st = st if st in GSTATUS_LABELS else ("upcoming" if not st else "partial")
            pr = num(t.get("progress"))
            item = {"status": st, "progress": max(0.0, min(1.0, pr if pr is not None else (1.0 if st == "done" else 0.0))),
                    "done_ids": str_list(t.get("done_ids")), "open_ids": str_list(t.get("open_ids"))}
            for key in (text_of(t.get("id")), "task:" + text_of(t.get("task"))):
                if key and key != "task:":
                    self.pg_gantt.setdefault(key, item)
        kp = self.json("data/kanban-progress.json", dict) or {}
        cols = kp.get("columns") if isinstance(kp.get("columns"), dict) else {}
        self.pg_kanban = {"columns": {str(k): str_list(v) for k, v in cols.items()},
                          "moves": [m for m in as_list(kp.get("moves")) if isinstance(m, dict) and m.get("id")],
                          "off_board": [m for m in as_list(kp.get("off_board")) if isinstance(m, dict) and m.get("id")]}
        self.pg_rev = self.dicts("data/revision.json")
        self.pg_hist = sorted([h for h in self.dicts("tracking/history.json") if re.match(r"^\d{4}-\d{2}-\d{2}", str(h.get("date") or ""))],
                              key=lambda h: str(h["date"]))
        # отстающие предложения: незакрытые из задач overdue
        self.pg_overdue = [o for o in as_list(pg.get("overdue")) if isinstance(o, dict)]
        self.pg_behind = {}
        for o in self.pg_overdue:
            for pid in str_list(o.get("proposals")):
                if self.pg_items.get(pid, {}).get("status") not in STATUS_CLOSED:
                    self.pg_behind.setdefault(pid, []).append(text_of(o.get("task")))

    def norm_item(self, it):
        """Запись items[P…] → безопасная для страницы форма: статус из списка, ссылки только https://github.com/…"""
        st = str(it.get("status") or "")
        st = st if st in STATUS_LABELS else "unknown"
        sug = str(it.get("suggested") or "")
        conf = num(it.get("confidence"))
        src = str(it.get("source") or "")
        issues, prs, commits, code = [], [], [], []
        for x in as_list(it.get("issues")):
            if not isinstance(x, dict):
                continue
            n, kind = to_int(x.get("number")), ("pr" if str(x.get("kind")) == "pr" else "issue")
            issues.append({"n": n, "kind": kind, "state": text_of(x.get("state")), "reason": text_of(x.get("state_reason")), "title": text_of(x.get("title")),
                           "url": gh_url(x.get("url"), self.gh_repo, kind, n), "labels": str_list(x.get("labels")),
                           "closed_at": text_of(x.get("closed_at")), "match": text_of(x.get("match")), "score": num(x.get("score")),
                           "sus": x.get("suspicious") is True})
        for x in as_list(it.get("prs")):
            if not isinstance(x, dict):
                continue
            n = to_int(x.get("number"))
            prs.append({"n": n, "state": text_of(x.get("state")), "title": text_of(x.get("title")), "url": gh_url(x.get("url"), self.gh_repo, "pr", n),
                        "merged_at": text_of(x.get("merged_at")), "match": text_of(x.get("match")), "sus": x.get("suspicious") is True})
        mentions = []
        for x in as_list(it.get("mentions"))[:10]:      # эпики и списки, где упомянут P-id (на статус не влияют)
            if isinstance(x, dict):
                n, kind = to_int(x.get("number")), ("pr" if str(x.get("kind")) == "pr" else "issue")
                mentions.append({"n": n, "kind": kind, "state": text_of(x.get("state")), "title": text_of(x.get("title")),
                                 "url": gh_url(x.get("url"), self.gh_repo, kind, n)})
        for x in as_list(it.get("commits")):
            if not isinstance(x, dict):
                continue
            s = text_of(x.get("sha"))
            commits.append({"sha": s[:12], "date": text_of(x.get("date")), "subject": text_of(x.get("subject")), "match": text_of(x.get("match")),
                            "url": gh_url(x.get("url"), self.gh_repo, "commit", s)})
        for x in as_list(it.get("code")):
            if isinstance(x, dict):
                code.append({"file": text_of(x.get("file")), "kind": text_of(x.get("kind")), "evidence": text_of(x.get("evidence"))})
            elif text_of(x):
                code.append({"file": text_of(x), "kind": "", "evidence": ""})
        return {"status": st, "suggested": sug if sug in STATUS_LABELS and sug != st else "",
                "confidence": max(0.0, min(1.0, conf)) if conf is not None else None, "source": src,
                "issues": issues, "prs": prs, "mentions": mentions, "commits": commits, "code": code, "scan_diff": str_list(it.get("scan_diff")),
                "blocked_by_open": str_list(it.get("blocked_by_open")), "note": text_of(it.get("note")), "since": text_of(it.get("since"))}

    def pg_status(self, pid):
        return (self.pg_items.get(pid) or {}).get("status", "") if self.pg else ""

    def load_charts(self):
        """charts/charts-index.json → графики. С charts/<ключ>.meta.json и SVG — интерактивный встроенный SVG с панелью пояснений
        (references/interactive-site.md, п. 2.3): в single/lite SVG — в разметке, пояснения — блок d-charts; в site SVG и пояснения —
        в assets/charts-<группа>.js (подгружаются при показе). Без meta (старые прогоны) — статичная картинка, как раньше."""
        idx = self.json("charts/charts-index.json", list)
        entries, static_old = [], []
        if idx is None and (self.out / "charts").is_dir():
            files = sorted(p for p in (self.out / "charts").iterdir() if p.suffix.lower() in (".svg", ".png", ".jpg", ".jpeg", ".webp"))
            if files:
                self.warn("charts/charts-index.json нет — графики взяты из charts/*.svg|png по именам файлов")
            idx = [{"key": p.stem, "svg": "charts/" + p.name, "title": p.stem.replace("-", " ").replace("_", " "), "caption": "",
                    "section": ""} for p in files]
        for c in idx or []:
            if not isinstance(c, dict) or not c.get("key"):
                continue
            key = str(c["key"])
            path = c.get("svg") or c.get("png") or c.get("file")
            e = {"key": key, "img": None, "svg": None, "meta": None, "title": text_of(c.get("title")) or key,
                 "caption": text_of(c.get("caption")), "section": str(c.get("section") or "")}
            meta = self.load_chart_meta(c, key)
            if meta is not None and path and str(path).lower().endswith(".svg") and re.fullmatch(r"[\w-]+", key):
                svg = self.inline_chart_svg(path, key)
                if svg:
                    e["svg"], e["meta"] = svg, meta
            if not e["svg"]:
                k = self.img.add(path, "c-" + key) if path else None
                if not k:
                    self.warn("график %s: нет файла %s" % (key, path))
                elif meta is None:
                    static_old.append(key)
                e["img"] = k
            entries.append(e)
        if static_old:
            self.warn("графики без пояснений (нет charts/<ключ>.meta.json — старый прогон): %s — показаны статичными картинками без панели; "
                      "перестройте графики: charts.py <OUT>" % (", ".join(static_old[:8]) + (" и ещё %d" % (len(static_old) - 8) if len(static_old) > 8 else "")))
        self.charts = entries
        self.charts_by_key = {c["key"]: c for c in entries}
        # есть интерактивные графики → якоря целей ссылок (data-gid/kid/mock/flow), стили панели; без них страница прежняя байт в байт
        self.ich = any(c.get("svg") for c in entries)
        self.chart_n = 0                       # счётчик вставок интерактивных графиков (уникальные id блоков «Как читать график»)

    def load_chart_meta(self, c, key):
        rel = c.get("meta") if isinstance(c.get("meta"), str) else "charts/%s.meta.json" % key
        p = self.img.resolve(rel)
        if p is None or not p.is_file():
            return None
        m = self.json(Path(p).relative_to(self.out).as_posix(), dict)
        if not m or not isinstance(m.get("elements"), dict):
            self.warn("график %s: %s без elements — показан статичной картинкой" % (key, rel))
            return None
        return m

    def inline_chart_svg(self, path, key):
        """SVG графика (charts.py) → фрагмент для встраивания в страницу: без скриптов, обработчиков, стилей и внешних ссылок;
        классы и data-ps-* сохраняются (на них держится панель), размеры — по viewBox."""
        p = self.img.resolve(str(path))
        if p is None or not p.is_file():
            return None
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        s = chart_svg_fragment(src)
        if not s or 'data-ps-chart="' + key + '"' not in s:
            self.warn("график %s: в %s нет корня <svg data-ps-chart> — показан статичной картинкой" % (key, path))
            return None
        return s

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
        hsfile = self.json("mockups/hotspots.json", dict) or {}
        hs_by = hsfile.get("mockups") if isinstance(hsfile.get("mockups"), dict) else {}
        for m in self.mockups:
            key = str(m.get("key") or Path(str(m.get("html") or m.get("png") or "")).stem or "")
            if not key:
                continue
            m = dict(m)
            m["key"] = key
            m["img"] = self.img.add(m.get("png"), "m-" + key) if m.get("png") else None
            # вторая тема снимка (shoot_mockups.mjs): themes {light, dark} | png_dark | png_light | png_alt
            alt, alt_name = None, ""
            themes = m.get("themes") if isinstance(m.get("themes"), dict) else {}
            for name, rel in list(themes.items()) + [("dark", m.get("png_dark")), ("light", m.get("png_light")), ("alt", m.get("png_alt"))]:
                if rel and str(rel) != str(m.get("png") or "") and m.get("img"):
                    k = self.img.add(str(rel), "m-" + key + "-" + slug(name))
                    if k and k != m["img"]:
                        alt, alt_name = k, str(name)
                        break
            m["alt_img"], m["alt_theme"] = alt, alt_name
            m["hs_ref"] = self.mock_hotspots(m, hs_by.get(key) if isinstance(hs_by.get(key), dict) else None)
            self.mock[key] = m
        self.mock_hs_count = sum(len(v["hotspots"]) for v in getattr(self, "mock_refs", {}).values())
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

    HS_TAG_RE = re.compile(r"<[a-zA-Z][\w-]*\s[^>]*\bdata-hs-title\s*=[^>]*>", re.S)
    HS_ATTR_RE = re.compile(r"\s(data-hs(?:-[a-z]+)?)\s*=\s*(\"([^\"]*)\"|'([^']*)')", re.S)

    def mock_hotspots(self, m, rec):
        """Подсказки к элементам макета (стандарт data-hs-*, mockup-kit/_hotspots.js) для просмотра на странице: зоны с номерами
        поверх снимка и описания в боковой панели. Координаты — mockups/hotspots.json {mockups: {ключ: {items: [{n, id, title, what,
        why, p, sec, r: [x, y, w, h] — доли снимка]}}}} (пишет shoot_mockups.mjs) или поле hotspots записи mockups-index.json (r —
        доли, либо x/y/w/h в пикселях снимка); без координат — список из атрибутов data-hs-* самого HTML-макета (зон нет, описания
        есть). Возвращает ключ псевдореференса «m:<ключ>» в d-refs или ""."""
        if not hasattr(self, "mock_refs"):
            self.mock_refs = OrderedDict()
        meta = self.img.meta.get(m.get("img") or "", {})
        W = num(m.get("width")) or meta.get("w") or 1440.0
        H = num(m.get("height")) or meta.get("h") or 900.0
        items = rec.get("items") if rec and isinstance(rec.get("items"), list) else m.get("hotspots") if isinstance(m.get("hotspots"), list) else None
        raw = []
        if items is None and m.get("html"):
            p = self.img.resolve(str(m.get("html")))
            try:
                src = p.read_text(encoding="utf-8", errors="replace") if p and p.is_file() else ""
            except OSError:
                src = ""
            items = []
            for tag in self.HS_TAG_RE.findall(src):
                at = {mm.group(1): html.unescape(mm.group(3) if mm.group(3) is not None else mm.group(4)) for mm in self.HS_ATTR_RE.finditer(tag)}
                if at.get("data-hs-title"):
                    items.append({"id": at.get("data-hs", ""), "title": at.get("data-hs-title"), "what": at.get("data-hs-what", ""),
                                  "why": at.get("data-hs-why", ""), "p": at.get("data-hs-p", ""), "sec": at.get("data-hs-sec", "")})
        out = []
        for i, it in enumerate(items or [], 1):
            if not isinstance(it, dict) or not text_of(it.get("title")):
                continue
            pids = [x for x in re.split(r"[\s,;]+", " ".join(str_list(it.get("p"))) if isinstance(it.get("p"), list) else text_of(it.get("p"))) if PID_FULL.match(x)]
            secs = [int(x) for x in re.split(r"[\s,;]+", " ".join(map(str, it.get("sec"))) if isinstance(it.get("sec"), list) else text_of(it.get("sec"))) if x.isdigit()]
            item = {"n": text_of(it.get("n")) or str(i), "title": text_of(it.get("title")), "text": text_of(it.get("what") or it.get("text")),
                    "why": text_of(it.get("why")), "proposal": pids[0] if pids else text_of(it.get("proposal")), "pids": pids, "sec": secs,
                    "state": text_of(it.get("state"))}
            r = it.get("r")
            box = None
            if isinstance(r, list) and len(r) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in r):
                box = [float(v) * 100 for v in r]
            elif all(isinstance(it.get(k), (int, float)) and not isinstance(it.get(k), bool) for k in ("x", "y", "w", "h")):
                box = [it["x"] / W * 100, it["y"] / H * 100, it["w"] / W * 100, it["h"] / H * 100]
            if box:
                cl = lambda v: max(0.0, min(100.0, v))
                l, t = round(cl(box[0]), 3), round(cl(box[1]), 3)
                item.update({"l": l, "t": t, "w": round(max(0.0, min(100.0 - l, box[2])), 3), "h": round(max(0.0, min(100.0 - t, box[3])), 3)})
                raw.append({"x": l / 100 * W, "y": t / 100 * H})
            else:
                raw.append({})
            out.append(item)
        if not out:
            return ""
        self.place_pins(out, raw, W, H)
        key = "m:" + m["key"]
        self.mock_refs[key] = {"title": text_of(m.get("title")) or m["key"], "kind": "макет", "summary": text_of(m.get("summary")),
                               "entry": "", "proposals": str_list(m.get("proposals")), "hotspots": out, "todo": [], "w": W, "h": H, "scale": 1.0,
                               "html": self.rel_link(str(m.get("html"))) if m.get("html") else "", "mock": True}
        return key

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
    def fig(self, key, caption_html, cap_text, group, cls="", ref="", extra="", attrs=""):
        meta = self.img.meta.get(key, {})
        w, h = meta.get("w"), meta.get("h")
        size = (' width="%d" height="%d"' % (w, h)) if w and h else ""
        if w and h:
            # ленивая картинка до загрузки — уже своего размера (FB-037): ширина, которую она займёт (max-width:100% сожмёт), и
            # пропорции; телефонный макет (figure.mobile, max-height 540) — ширина по высоте 540
            fw = min(w, int(round(540.0 * w / h))) if "mobile" in cls.split() else w
            size += ' style="width:%dpx;aspect-ratio:%d / %d"' % (fw, w, h)
        self.figs += 1
        return ('<figure class="lb ' + cls + '"' + attrs + ' data-key="' + esc(key) + '" data-group="' + esc(group) + '" data-ref="' + esc(ref)
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
            if c and (c.get("img") or c.get("svg")):
                if inline:
                    return '<a class="emb" href="' + esc(self.chart_href(c)) + '">график «' + esc(c["title"]) + "»</a>"
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

    def chart_fig(self, c, primary=False):
        cap = "<b>" + esc(c["title"]) + "</b>" + (" — " + esc(c["caption"]) if c.get("caption") else "")
        if c.get("svg"):
            return self.ichart_fig(c, cap, primary)
        return self.fig(c["img"], self.links(cap), c["title"] + (" — " + c["caption"] if c.get("caption") else ""), "charts", "chart")

    @staticmethod
    def chart_href(c):
        """Ссылка на график: интерактивный — #chart/<ключ> (роутер страницы), статичный — #lb=<картинка> (лайтбокс)."""
        return "#chart/" + c["key"] if c.get("svg") else "#lb=" + str(c.get("img") or "")

    def chart_group(self, c):
        """Файл assets/charts-<группа>.js режима site: группа — раздел графика (scores, registry, plan, model, market…)."""
        return slug(c.get("section") or "other").lower()

    def ichart_fig(self, c, cap, primary):
        """Интерактивный график: встроенный SVG (single/lite) или место под него (site: SVG подгружается из assets/charts-<группа>.js
        при показе), подпись, кнопки «Как читать график» и «увеличить», блок howto + легенда (виден и без скрипта по кнопке)."""
        key, meta = c["key"], c["meta"]
        self.chart_n += 1
        hid = "howto-%s-%d" % (key, self.chart_n)
        if self.site:
            g = self.chart_group(c)
            # заглушка ленивого графика — сразу размером с график (FB-037): aspect-ratio из viewBox; на телефоне (≤ 699 px) SVG не
            # уже 560 px и прокручивается в рамке → высота = 560·H/W + рамка; страница не сдвигается при подгрузке
            vb = svg_viewbox(c["svg"])
            size = (' style="--ps-ar:%g / %g;--ps-mh:%dpx"' % (round(vb[0], 2), round(vb[1], 2), round(560 * vb[1] / vb[0] + 2))) if vb else ""
            box = ('<div class="ps-svg ps-wait" data-chart="' + esc(key) + '" data-ps-src="@@charts-' + esc(g) + '@@"' + size + '>'
                   '<p class="ps-ph muted">График загружается…</p><noscript><p class="missing">Интерактивный график показывается скриптом '
                   "страницы; без JavaScript см. charts/" + esc(key) + ".svg.</p></noscript></div>")
        else:
            box = '<div class="ps-svg" data-chart="' + esc(key) + '">' + c["svg"] + "</div>"
        box = psi_wrap("chart", box, c["title"])
        legend = [x for x in as_list(meta.get("legend")) if isinstance(x, dict) and text_of(x.get("label"))]
        howto = text_of(meta.get("howto"))
        how = ('<div class="ps-howto" id="' + esc(hid) + '" hidden>' + ("<p>" + esc(howto) + "</p>" if howto else "")
               + ('<dl class="ps-legend">' + "".join("<dt>" + esc(text_of(x.get("label"))) + "</dt><dd>" + esc(text_of(x.get("text"))) + "</dd>"
                                                    for x in legend) + "</dl>" if legend else "")
               + '<p class="small muted">Нажмите на элемент графика (или выберите его клавишей Tab и нажмите Enter) — справа откроется '
                 "панель: что это, что значит, что делать и ссылки. ←/→ — соседний элемент, Esc — закрыть. «🔍 Увеличить» или клик по фону — "
                 "крупный просмотр с живым графиком: масштаб, подсказки и подробности по каждому элементу.</p></div>")
        acts = ('<span class="ps-acts"><button type="button" class="linkbtn ps-howto-btn" aria-expanded="false" aria-controls="' + esc(hid)
                + '">Как читать график</button></span>')
        self.anchors.setdefault("chart", set()).add(key)
        return ('<figure class="ps-ichart' + (" ps-primary" if primary else "") + '" data-chart="' + esc(key) + '"'
                + (' id="chart-' + esc(key) + '"' if primary else "") + ">" + box + "<figcaption>" + self.links(cap) + " " + acts
                + "</figcaption>" + how + "</figure>")

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
        badge = ('<span class="badge-concept">' + ("Концепт продукта, не существующая функция" if self.concept else "Концепт, не существующая функция")
                 + "</span>") if concept else '<span class="tag">факт</span>'
        pr = self.chips(m.get("proposals"))
        html_rel = self.rel_link(str(m.get("html"))) if m.get("html") else ""
        open_html = ' · <a href="' + esc(html_rel) + '" target="_blank" rel="noopener">HTML-макет</a>' if html_rel else ""
        if inline:
            if m.get("img"):
                return '<a class="emb" href="#lb=' + esc(m["img"]) + '">макет «' + esc(title) + "»</a>"
            return '<span class="emb">макет «' + esc(title) + "»</span>"
        cap = "<b>" + esc(title) + "</b> " + badge + (" · " + pr if pr else "") + (" · " + esc(m.get("viewport")) if m.get("viewport") else "")
        self.anchors["mockup"].add(m["key"])
        # 1.5: у каждого макета — ключ (цель #mockup/…, M-ключи текста), связанные P-id и ссылка на живой HTML для просмотра
        # («Открыть интерактивный макет»), вторая тема снимка (переключатель в просмотре)
        mattr = (' data-mock="' + esc(m["key"]) + '"' + (' data-pids="' + esc(" ".join(str_list(m.get("proposals")))) + '"' if str_list(m.get("proposals")) else "")
                 + (' data-html="' + esc(html_rel) + '"' if html_rel else "")
                 + (' data-alt="' + esc(m["alt_img"]) + '" data-alt-theme="' + esc(m.get("alt_theme") or "") + '"' if m.get("alt_img") else ""))
        if not m.get("img"):
            return ('<div class="ph mock-ph" id="mock-' + esc(slug(m["key"])) + '"' + mattr + ' tabindex="-1"><div class="ph-t">Нет PNG макета</div>'
                    + cap + open_html + "</div>")
        mob = "mobile" if self.is_mobile_img(m["img"], str(m.get("viewport") or "")) else ""
        return self.fig(m["img"], cap, title, group, mob, self.mock_ref(m) or m.get("hs_ref") or "", extra=open_html, attrs=mattr)

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
            if sid != "top" and 'class="psi-wrap' in body and "</h2>" in body:   # раздел с графиками или схемами — строка-подсказка под заголовком
                i = body.index("</h2>") + 5
                body = body[:i] + psi_hint() + body[i:]
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
        if self.concept:
            return ("Концепция продукта " + str(name)) if name else "Концепция нового продукта"
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
        self.sec_viability()
        self.sec_strategy()
        self.sec_registry()
        self.sec_progress()
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
        self.sec_glossary()
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
            out.append({"title": text_of(m.get("title")) or m["key"], "img": img, "ref": ref or (rstem if r is not None and img else "") or (m.get("hs_ref") or ""),
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
            ts_block = merge_typesafe(ts, jev)
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
                "typesafe": ts or None, "jev": jev or None, "ts_block": ts_block, "m": m, "concepts": concepts,
                "has_mockup": bool(concepts), "mentions": mentions.get(p["id"], {}), "rdeps": rdeps.get(p["id"], []),
            }
            hay = " ".join([row["id"], row["title"], row["description"], row["rationale"], row["segment"],
                            " ".join(row["tags"]), CAT_LABELS.get(row["category"], row["category"]), row["current_feature"],
                            row["cheap_test"], " ".join(LABEL_LABELS.get(x, x) for x in labels)])
            if self.pg:                         # поля выполнения — только в режиме отслеживания (иначе строка прежняя)
                it = self.pg_items.get(p["id"])
                row["status"] = it["status"] if it else ""
                if it:
                    row["pg"] = dict(it, behind=self.pg_behind.get(p["id"], []))
                    hay += " " + STATUS_LABELS.get(it["status"], "") + " " + " ".join(
                        "#%s %s" % (x["n"], x["title"]) for x in it["issues"] + it["prs"] if x.get("n"))
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
        if prod.get("name") or prod.get("url"):
            u = text_of(prod.get("url")).strip()
            # ссылка — только валидный http(s)-адрес; «Локальный запуск…» и прочий текст — текстом
            where = (ext_link(u) if http_url(u) else '<span class="muted">' + esc(u) + "</span>") if u else ""
            facts.append(("Продукт", esc(text_of(prod.get("name"))) + (" · " + where if where and prod.get("name") else where)))
        if self.concept:
            pitch = text_of((self.cfg.get("idea") or {}).get("pitch") if isinstance(self.cfg.get("idea"), dict) else "")
            facts.append(("Стадия", "идея — продукта ещё нет"))
            if pitch:
                facts.append(("Идея", esc(pitch)))
        if st.get("goal"):
            facts.append(("Цель", esc(st["goal"])))
        kind = {"growth": "рост", "gtm": "выход на рынок", "monetization": "монетизация", "tech-roadmap": "техническая дорожная карта",
                "oss-community": "открытый проект и сообщество", "full": "полная"}.get(str(st.get("kind")), st.get("kind"))
        if self.concept:
            facts.append(("Тип", "концепция: продукт, рынок, запуск"))
        elif kind:
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
        if self.pg and any(r.get("status") for r in self.rows):
            sr = [r for r in self.rows if r.get("status")]
            dn = sum(1 for r in sr if r["status"] == "done")
            tiles.append(("%d%%" % round(100.0 * dn / len(sr)), "выполнено по проверке", text_of(self.pg.get("checked")) + " · %d из %d" % (dn, len(sr))))
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
            tiles.append((str(len([c for c in self.charts if c.get("img") or c.get("svg")])), "графиков", ""))
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
        body = ('<section id="top" class="top"><p class="eyebrow">' + ("Концепция нового продукта" if self.concept else "Стратегия развития продукта")
                + " · " + esc(self.date) + "</p><h1>"
                + esc(title) + "</h1>" + author + (psi_hint(top=True) if self.has_psi else "")
                + '<dl class="facts">' + "".join("<dt>" + a + "</dt><dd>" + b + "</dd>" for a, b in facts)
                + "</dl>" + ('<div class="kpis">' + kpi + "</div>" if kpi else "") + pre + self.links(top10) + assum_html
                + '<p class="hint muted">Как читать: любой номер предложения (например, P001) открывает его карточку; любая картинка '
                "увеличивается по клику; строки Ганта, карточки Kanban и блоки схем раскрываются. Esc закрывает верхнее окно.</p></section>")
        self.add("top", "Резюме и ключевые цифры", body)

    # --- режим идеи: предпроверка жизнеспособности (data/typesafe-concept.json, typesafe_concept.py)
    def sec_viability(self):
        v = self.viab
        if not self.concept or not v or not v.get("verdict"):
            return
        verdict = text_of(v.get("verdict"))
        items = v.get("items") if isinstance(v.get("items"), dict) else {}
        trs = []
        for q in as_list(v.get("questions")):
            if not isinstance(q, dict) or q.get("key") not in items or not isinstance(items[q["key"]], dict):
                continue
            it = items[q["key"]]
            p = num(it.get("p"))
            if p is None:
                continue
            good = p if q.get("good") != "low" else 1 - p
            cls = "vb-ok" if good >= 0.6 else ("vb-mid" if good >= 0.4 else "vb-bad")
            trs.append("<tr><td>" + esc(text_of(q.get("label") or it.get("label") or q["key"])) + "</td><td class=\"num\">"
                       + '<span class="vbar ' + cls + '" aria-hidden="true"><i style="width:' + str(int(round(p * 100))) + '%"></i></span> '
                       + "%d%%" % round(p * 100) + ("" if q.get("good") != "low" else ' <span class="muted small">(меньше — лучше)</span>')
                       + "</td><td>" + esc(text_of(it.get("note"))) + "</td></tr>")
        heur = text_of(v.get("source")) != "jev"
        src = ("эвристика по ответам владельца, уверенность низкая — ориентир, не прогноз" if heur
               else "TypeSafe Jev по обезличенной идее и ответам")
        skipped = text_of(v.get("skipped"))
        lead = ('<p class="lead"><span class="vverdict vv-' + esc(slug(verdict)) + '">' + esc({"green": "Зелёный", "yellow": "Жёлтый", "red": "Красный"}.get(verdict, verdict))
                + "</span> " + esc(text_of(v.get("verdict_label"))) + ". Жизнеспособность %s, риск запрета %s. Источник: %s%s.</p>" % (
                    fmt_num(v.get("viability")), fmt_num(v.get("risk")), esc(src), (" (Jev не спрашивали: " + esc(skipped) + ")") if skipped and heur else ""))
        first = str_list(v.get("check_first"))
        tail = ("<p>Проверить в первую очередь: <b>" + esc(", ".join(first)) + "</b>.</p>") if first else ""
        table = ('<div class="tbl"><table class="data"><thead><tr><th>Вопрос</th><th>Вероятность «да»</th><th>Пояснение</th></tr></thead><tbody>'
                 + "".join(trs) + "</tbody></table></div>") if trs else ""
        self.add("viability", "Жизнеспособность идеи", self.section("viability", "Жизнеспособность идеи", lead + table + tail))

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
            if PROGRESS_MARK_RE.match(line):
                # маркеры автоблока strategy_track.py (<!-- progress:start/end -->) — служебные, на страницу не попадают;
                # пустая строка вместо маркера отделяет таблицу блока от соседнего текста
                (cur[1] if cur else pre).append("")
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
        if self.pg:                             # фильтр статуса выполнения — только в режиме отслеживания
            f.insert(0, self.options("status", STATUS_ORDER, {k: STATUS_ICONS[k] + " " + v for k, v in STATUS_LABELS.items()},
                                     "Все статусы", [r.get("status", "") for r in R]))
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
        quick = ""
        if self.pg:
            sort_opts = sort_opts.replace('<option value="title">Название</option>',
                                          '<option value="title">Название</option><option value="status">Статус выполнения</option>', 1)
            quick = ('<div class="toolbar pg-quick" role="group" aria-label="Быстрые фильтры выполнения"><span class="lbl">Выполнение:</span>'
                     '<button type="button" data-qf="notdone" aria-pressed="false">Не сделано</button>'
                     '<button type="button" data-qf="work" aria-pressed="false">В работе</button>'
                     '<button type="button" data-qf="behind" aria-pressed="false">Отстаёт</button>'
                     '<a class="small" href="#progress">Сводка выполнения →</a></div>')
        inner = ('<p class="lead">Все предложения с оценками. Клик по строке раскрывает карточку, по номеру — открывает её в окне. '
                 "Сортировка — по заголовку столбца или по любой метрике из списка; фильтры и поиск сочетаются. "
                 "Экспорт сохраняет то, что сейчас показано.</p>"
                 '<div class="toolbar" role="search"><input id="q" type="search" placeholder="Поиск: ID, название, описание, сегмент, теги…" '
                 'aria-label="Поиск по реестру">' + "".join(f) + "</div>" + quick +
                 '<div class="toolbar"><label class="lbl">Сортировка <select id="sortby" aria-label="Сортировать по метрике">'
                 + sort_opts + '</select></label><button id="sortdir" type="button" aria-label="Направление сортировки">по возрастанию ↑</button>'
                 '<button id="reg-reset" type="button">Сбросить фильтры</button><span id="reg-count" class="count" aria-live="polite"></span>'
                 '<span class="spacer"></span><button id="exp-csv" type="button" title="Отфильтрованный реестр в CSV (UTF-8, Excel)">↓ CSV</button>'
                 '<button id="exp-json" type="button" title="Отфильтрованный реестр в JSON">↓ JSON</button></div>'
                 '<div class="reg-wrap"><table id="reg" class="reg"><thead><tr id="reg-head"></tr></thead><tbody id="tb"></tbody></table></div>'
                 '<noscript><p class="missing">Реестр показывается скриптом страницы; без JavaScript см. data/proposals.json.</p></noscript>')
        self.add("registry", "Реестр предложений", self.section("registry", "Реестр предложений <span class=\"muted\">(%d)</span>" % len(R), inner))

    # --- 3а. прогресс выполнения (режим «Отслеживание», data/progress.json)
    def pg_counts(self, rows):
        c = {k: 0 for k in STATUS_ORDER}
        for r in rows:
            if r.get("status") in c:
                c[r["status"]] += 1
        return c

    def pg_bars(self, field, order, labels):
        groups = {}
        for r in self.rows:
            if r.get("status") and r.get(field):
                groups.setdefault(r[field], []).append(r)
        if not groups:
            return ""
        keys = [k for k in order if k in groups] + sorted(k for k in groups if k not in order)
        out = ""
        for k in keys:
            rs = groups[k]
            c, t = self.pg_counts(rs), len(rs)
            segs = "".join('<span class="pgs s-%s" style="width:%.2f%%"></span>' % (s, 100.0 * c[s] / t) for s in ("done", "partial", "in_progress") if c[s])
            pct = round(100.0 * c["done"] / t)
            aria = "%s: выполнено %d из %d, частично %d, в работе %d" % (labels.get(k, k), c["done"], t, c["partial"], c["in_progress"])
            out += ('<div class="pgrow"><span class="pgl">' + esc(labels.get(k, k)) + '</span><span class="pgt" role="img" aria-label="'
                    + esc(aria) + '">' + segs + '</span><span class="pgn">' + "%d/%d · %d%%" % (c["done"], t, pct)
                    + (' <span class="muted">◐%d ▸%d</span>' % (c["partial"], c["in_progress"]) if c["partial"] or c["in_progress"] else "")
                    + "</span></div>")
        return out

    def pg_chart(self):
        """Динамика выполнения из tracking/history.json: линия «% выполнено» (SVG без текста — подписи HTML-таблицей ниже)."""
        pts = []
        for h in self.pg_hist:
            s = h.get("summary") if isinstance(h.get("summary"), dict) else {}
            tot, done = num(s.get("total")), num(s.get("done"))
            pct = num(s.get("percent_done"))
            if pct is None and tot:
                pct = 100.0 * (done or 0) / tot
            if pct is None:
                continue
            pts.append((str(h["date"])[:10], max(0.0, min(100.0, pct)), s))
        if not pts:
            return ""
        rows = "".join("<tr><td>" + esc(d) + '</td><td class="num">' + esc(fmt1(p)) + ' %</td><td class="num">'
                       + esc(fmt_num(s.get("done"))) + '</td><td class="num">' + esc(fmt_num((num(s.get("in_progress")) or 0) + (num(s.get("partial")) or 0)))
                       + '</td><td class="num">' + esc(fmt_num(s.get("blocked"))) + "</td></tr>" for d, p, s in pts)
        table = ('<div class="tbl"><table class="data"><thead><tr><th>Дата проверки</th><th class="num">Выполнено</th><th class="num">Сделано, шт.</th>'
                 '<th class="num">В работе и частично</th><th class="num">Заблокировано</th></tr></thead><tbody>' + rows + "</tbody></table></div>")
        if len(pts) < 2:
            return '<p class="muted">Одна проверка — график динамики появится после следующей.</p>' + table
        try:
            days = [(date.fromisoformat(d) - date.fromisoformat(pts[0][0])).days for d, _, _ in pts]
        except ValueError:
            days = list(range(len(pts)))           # даты не по ISO — точки через равные промежутки
        if sorted(days) != days:
            days = list(range(len(pts)))
        span = max(1, days[-1] - days[0])
        ymax = max(10.0, math.ceil(max(p for _, p, _ in pts) / 10.0) * 10.0)
        W, H, L, Rm, T, B = 640.0, 170.0, 8.0, 8.0, 10.0, 10.0
        xy = [(L + (W - L - Rm) * (dd - days[0]) / span, T + (H - T - B) * (1 - p / ymax)) for dd, (_, p, _) in zip(days, pts)]
        grid = "".join('<line class="pgc-grid" x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f"/>' % (L, W - Rm, T + (H - T - B) * k / 4, T + (H - T - B) * k / 4) for k in range(5))
        line = " ".join("%.1f,%.1f" % p for p in xy)
        area = "M%.1f,%.1f L" % (xy[0][0], H - B) + " L".join("%.1f,%.1f" % p for p in xy) + " L%.1f,%.1f Z" % (xy[-1][0], H - B)
        dots = "".join('<circle class="pgc-dot" cx="%.1f" cy="%.1f" r="4.5"/>' % p for p in xy)
        label = "Динамика выполнения: " + "; ".join("%s — %s %%" % (d, fmt1(p)) for d, p, _ in pts)
        svg = ('<svg class="pgc" viewBox="0 0 640 170" role="img" aria-label="' + esc(label) + '"><title>' + esc(label) + "</title>" + grid
               + '<path class="pgc-area" d="' + area + '"/><polyline class="pgc-line" points="' + line + '"/>' + dots + "</svg>")
        axis = ('<div class="pgc-axis"><span>' + esc(pts[0][0]) + "</span><span>шкала 0–" + esc(fmt_num(ymax)) + " % выполненного</span><span>"
                + esc(pts[-1][0]) + "</span></div>")
        return '<div class="pgc-wrap">' + svg + axis + "</div>" + table

    def pg_changed(self):
        """« С прошлой проверки (дата) статус сменили N предложений» — из summary.changed_since_last / previous_check."""
        s = self.pg.get("summary") if isinstance(self.pg.get("summary"), dict) else {}
        n, prev = to_int(s.get("changed_since_last")), text_of(s.get("previous_check"))
        if n is None or not prev:
            return ""
        return " С прошлой проверки (%s) статус сменили: <b>%d</b>." % (esc(prev), n)

    def issue_ref(self, x, kind="issue"):
        """«#12 · открыт · заголовок» со ссылкой на GitHub (только https://github.com/…)."""
        n = x.get("n")
        kind = x.get("kind") or kind
        lab = (("PR #%d" if kind == "pr" else "#%d") % n) if n else ("PR" if kind == "pr" else "issue")
        state = ISSUE_STATE_LABELS.get(x.get("state"), x.get("state") or "")
        return (gh_link(x.get("url"), lab) + (' <span class="tag">' + esc(state) + "</span>" if state else "")
                + (" " + esc(x.get("title")) if x.get("title") else ""))

    def sec_progress(self):
        if not self.pg:
            return
        pg, R = self.pg, [r for r in self.rows if r.get("status")]
        c, total = self.pg_counts(R), len(R)
        st = self.cfg.get("strategy") if isinstance(self.cfg.get("strategy"), dict) else {}
        H = to_int(st.get("horizon_months")) or 12
        checked = text_of(pg.get("checked"))
        base = pg.get("baseline") if isinstance(pg.get("baseline"), dict) else {}
        pct = (100.0 * c["done"] / total) if total else 0.0
        outside = [o for o in as_list(pg.get("outside_strategy")) if isinstance(o, dict)]
        behind_tasks = [o for o in self.pg_overdue if str(o.get("status") or "behind") == "behind"]
        month = self.pg_month or self.pg_cur

        def tile(n, label, sub, href, attrs=""):
            return ('<a class="kpi pgk" href="' + href + '"' + attrs + '><div class="n">' + esc(n) + '</div><div class="l">' + esc(label)
                    + "</div>" + ('<div class="s">' + esc(sub) + "</div>" if sub else "") + "</a>")
        tiles = (tile("%s%%" % fmt1(pct), "выполнено", "%d из %d · частично %d" % (c["done"], total, c["partial"]), "#registry", ' data-st-go="done"' if c["done"] else "")
                 + tile(str(c["in_progress"] + c["partial"]), "в работе", "в работе %d, частично %d, запланировано %d" % (c["in_progress"], c["partial"], c["planned"]),
                        "#registry", ' data-qf-go="work"' if c["in_progress"] + c["partial"] else "")
                 + tile(str(len(behind_tasks)), "отстаёт по плану", "задач Ганта; предложений: %d" % len(self.pg_behind), "#registry", ' data-qf-go="behind"' if self.pg_behind else "")
                 + tile(str(c["blocked"]), "заблокировано", "ждут невыполненных предпосылок", "#registry", ' data-st-go="blocked"' if c["blocked"] else "")
                 + tile(str(len(outside)), "вне стратегии", "issues и PR без связи с предложениями", "#pg-outside")
                 + tile(ru_date(checked) or "—", "дата проверки", ("месяц плана %d из %d" % (month, H) if month else "")
                        + (" · прошло %s мес." % fmt1(self.pg_elapsed) if self.pg_elapsed is not None else ""), "#pg-dyn", ' data-date="1"'))
        legend = "".join('<a class="pst-go" href="#registry" data-st-go="' + s + '">' + st_chip(s) + ' <b>' + str(c[s]) + "</b></a>"
                         for s in STATUS_ORDER if c[s])
        nodata = len(self.rows) - total
        parts = ['<p class="lead">Срез выполнения стратегии на <b>' + esc(checked or "—") + "</b>" + (" (стратегия от " + esc(text_of(base.get("created"))) + ")" if base.get("created") else "")
                 + ". Статусы — по репозиторию, git-логу, issues и PR; решение владельца побеждает автоматику. Плитки и чипы открывают реестр с фильтром."
                 + self.pg_changed() + "</p>",
                 '<div class="kpis pg-kpis">' + tiles + "</div>",
                 '<div class="pg-legend" aria-label="Статусы предложений">' + legend + "</div>"
                 + ('<p class="muted small">Без статуса (нет в срезе): %d.</p>' % nodata if nodata > 0 else "")]
        hz = self.pg_bars("horizon", list(HORIZON_LABELS), HORIZON_LABELS)
        pr = self.pg_bars("priority", ["P0", "P1", "P2", "P3"], {})
        bars_legend = ('<p class="pg-bl muted small"><span class="pgsw s-done"></span>' + STATUS_ICONS["done"] + " выполнено "
                       '<span class="pgsw s-partial"></span>' + STATUS_ICONS["partial"] + " частично "
                       '<span class="pgsw s-in_progress"></span>' + STATUS_ICONS["in_progress"] + " в работе "
                       '<span class="pgsw s-rest"></span> остальное · справа: сделано / всего</p>')
        if hz or pr:
            parts.append('<h3>По горизонтам и приоритетам</h3>' + bars_legend + '<div class="dists pg-dists">'
                         + ('<div class="bars"><h4>Горизонт</h4>' + hz + "</div>" if hz else "")
                         + ('<div class="bars"><h4>Приоритет</h4>' + pr + "</div>" if pr else "") + "</div>")
        chart = self.pg_chart()
        parts.append('<h3 id="pg-dyn">Динамика</h3>' + (chart or '<p class="muted">Нет tracking/history.json — динамика появится после нескольких проверок.</p>'))
        # изменившиеся факты
        facts = [f for f in as_list(pg.get("facts_changed")) if isinstance(f, dict)]
        if facts:
            lis = "".join("<li><b>" + esc(FACT_LABELS.get(text_of(f.get("fact")), text_of(f.get("fact")))) + "</b>: "
                          + '<span class="pg-was">' + esc(text_of(f.get("was")) or "—") + '</span> → <span class="pg-now">' + esc(text_of(f.get("now")) or "—") + "</span>"
                          + (" · затрагивает: " + self.chips(f.get("affects")) if str_list(f.get("affects")) else "") + "</li>" for f in facts)
            parts.append("<h3>Изменились факты</h3><ul class=\"pg-list\">" + lis + "</ul>")
        # «считали отсутствующим, а оно уже есть» (движок: discrepancies)
        dis = [d for d in as_list(pg.get("discrepancies")) if isinstance(d, dict)]
        if dis:
            lis = ""
            for d in dis:
                pid, n = text_of(d.get("id")), to_int(d.get("number"))
                url = gh_url(d.get("url"), self.gh_repo, "issue", n)
                lis += ("<li>" + (pid_link(pid, self.titles) + " " + esc(self.titles.get(pid, "")) if pid in self.titles else esc(pid))
                        + '<div class="pg-sub">' + esc(text_of(d.get("text"))) + (" · " + gh_link(url, "#%d" % n) if n else "") + "</div></li>")
            parts.append('<h3>Считали отсутствующим, а оно уже есть</h3><p class="muted small">В стратегии «нет …», а похожий или явно связанный '
                         "issue закрыт ещё до неё — проверьте и поправьте карточку предложения.</p><ul class=\"pg-list\">" + lis + "</ul>")
        # следующие шаги
        nxt = [p for p in str_list(pg.get("next_actions")) if p in self.titles]
        if nxt:
            by = {r["id"]: r for r in self.rows}
            lis = ""
            for pid in nxt:
                r = by.get(pid, {})
                it = self.pg_items.get(pid) or {}
                deps = r.get("dependencies") or []
                open_deps = [d for d in deps if self.pg_status(d) not in STATUS_CLOSED]
                if not deps:
                    pre = '<span class="muted">предпосылок нет</span>'
                elif not open_deps:
                    pre = '<span class="pg-ok">✓ предпосылки выполнены</span>'
                else:
                    pre = '<span class="pg-warn">ждёт: </span>' + self.chips(open_deps)
                iss = [x for x in it.get("issues", []) if x.get("state") == "open"] or it.get("issues", [])
                issue = self.issue_ref(iss[0]) if iss else '<span class="tag">нет issue</span>'
                lis += ("<li>" + pid_link(pid, self.titles) + " " + esc(r.get("title", "")) + " " + st_chip(it.get("status", ""))
                        + (" " + self.badge("p", r.get("priority")) if r.get("priority") else "") + '<div class="pg-sub">' + pre + " · " + issue + "</div></li>")
            parts.append('<h3>Следующие шаги</h3><p class="muted small">Не начатые и запланированные предложения с выполненными предпосылками, '
                         "по важности. «нет issue» — черновик задачи есть в data/issues-drafts.md.</p><ol class=\"pg-list\">" + lis + "</ol>")
        # отстаёт по плану — списком (на телефоне таблица из 4 колонок рвёт слова)
        if self.pg_overdue:
            gt = {t["id"]: dict(t, _i=i) for i, t in enumerate(self.gantt_tasks()) if t.get("id")}
            lis = ""
            for o in self.pg_overdue:
                tid = text_of(o.get("task"))
                t = gt.get(tid, {})
                end = to_int(o.get("planned_end_month"))
                when = ("месяц %d · %s" % (end, self.month_label(end, True))) if end else "—"
                name = '<span class="gid">' + esc(tid) + "</span> " + esc(t.get("task", ""))
                props = " ".join('<span class="pg-pp">' + (pid_link(p, self.titles) if p in self.titles else esc(p)) + " " + st_chip(self.pg_status(p)) + "</span>"
                                 for p in str_list(o.get("proposals")))
                lis += ("<li>" + (('<a href="#gantt" data-g-open="%d">' % t["_i"]) + name + "</a>" if "_i" in t else name) + " "
                        + st_chip(str(o.get("status") or "behind"), GSTATUS_LABELS, GSTATUS_ICONS, "gst")
                        + '<div class="pg-sub">срок по плану: ' + esc(when) + (" · " + props if props else "") + "</div></li>")
            parts.append('<h3>Отстаёт по плану</h3><ul class="pg-list">' + lis + "</ul>")
        # работа вне стратегии
        if outside:
            lis = ""
            for o in outside:
                kind = "pr" if str(o.get("kind")) == "pr" else "issue"
                n = to_int(o.get("number"))
                url = gh_url(o.get("url"), self.gh_repo, kind, n)
                lab = ("PR" if kind == "pr" else "issue") + (" #%d" % n if n else "")
                sug = text_of(o.get("suggest"))
                lis += ("<li>" + gh_link(url, lab) + ' <span class="tag">' + esc(ISSUE_STATE_LABELS.get(text_of(o.get("state")), text_of(o.get("state")))) + "</span> "
                        + esc(text_of(o.get("title"))) + (' <span class="tag pg-sug">' + esc(SUGGEST_LABELS.get(sug, sug)) + "</span>" if sug else "")
                        + (" · похоже на " + self.chips(o.get("similar_to")) if str_list(o.get("similar_to")) else "") + "</li>")
            parts.append('<h3 id="pg-outside">Работа вне стратегии</h3><p class="muted small">Issues и PR, не связанные ни с одним предложением. '
                         "Кандидата в предложения стоит добавить в реестр (корректировка «добавить»), ошибки и служебную работу — оставить как есть; "
                         "связать с предложением: <code>strategy_track.py link &lt;OUT&gt; &lt;P-id&gt; &lt;номер issue&gt;</code>.</p><ul class=\"pg-list\">" + lis + "</ul>")
        # предлагаемые корректировки
        if self.pg_rev:
            secs = set(re.findall(r'<section id="s-(\d+)"', "".join(self.sections)))
            lis = ""
            for v in self.pg_rev:
                typ = text_of(v.get("type"))
                sl = []
                for s_ in as_list(v.get("sections")):
                    k = text_of(s_)
                    sl.append(('<a href="#s-' + esc(k) + '">§' + esc(k) + "</a>") if k in secs else "§" + esc(k))
                pid = text_of(v.get("id"))
                ev = str_list(v.get("evidence"))
                sub = [x for x in (("основание: " + esc(text_of(v.get("reason")))) if text_of(v.get("reason")) else "",
                                   ("доказательства: " + esc("; ".join(ev))) if ev else "",
                                   ("разделы: " + ", ".join(sl)) if sl else "") if x]
                lis += ('<li><span class="tag pg-rt pg-rt-' + esc(slug(typ)) + '">' + esc(REVISION_LABELS.get(typ, typ)) + "</span> "
                        + (pid_link(pid, self.titles) + " — " if pid in self.titles else "") + esc(text_of(v.get("text")))
                        + ('<div class="pg-sub">' + " · ".join(sub) + "</div>" if sub else "") + "</li>")
            parts.append('<h3>Предлагаемые корректировки</h3><p class="muted small">Вход для обновления стратегии (бриф strategy-update): '
                         "сама стратегия не меняется, пока владелец не согласится.</p><ul class=\"pg-list pg-rev\">" + lis + "</ul>")
        src = pg.get("sources") if isinstance(pg.get("sources"), dict) else {}
        names = {"repo": "репозиторий", "git_log": "git-лог", "scan_diff": "разница сканов", "issues": "issues", "prs": "PR"}
        srcs = [names[k] + (" ✓" if src.get(k) is True else " —") for k in names if k in src]
        if src.get("gh"):
            srcs.append("gh: " + text_of(src.get("gh")))
        warns = str_list(pg.get("warnings")) + str_list(pg.get("notes"))
        if srcs or warns:
            parts.append('<p class="muted small">Источники проверки: ' + esc(", ".join(srcs) or "—") + ".</p>"
                         + ('<details><summary>Предупреждения проверки (%d)</summary><ul>' % len(warns) + "".join("<li>" + esc(w) + "</li>" for w in warns)
                            + "</ul></details>" if warns else ""))
        self.add("progress", "Прогресс выполнения", self.section("progress", "Прогресс выполнения", self.links("".join(parts)), "pg"))

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
        sch = [c for c in self.charts if (c.get("img") or c.get("svg")) and c["section"] in ("scores", "registry")]
        if parts and sch:
            parts.append('<p class="muted">Графики оценок: ' + ", ".join('<a class="emb" href="' + esc(self.chart_href(c)) + '">' + esc(c["title"]) + "</a>" for c in sch) + "</p>")
        if parts:
            self.add("scores", "Оценки и чувствительность", self.section("scores", "Оценки и чувствительность", self.links("".join(parts))))

    # --- 5. графики
    def sec_charts(self):
        ch = [c for c in self.charts if c.get("img") or c.get("svg")]
        if not ch:
            return
        groups = {}
        for c in ch:
            groups.setdefault(c["section"], []).append(c)
        if any(c.get("svg") for c in ch):
            inner = ('<p class="lead">Графики интерактивные: нажмите на точку, столбец, ступень или ячейку — справа откроется панель «что это, '
                     "что значит, что делать» со ссылками на разделы и предложения; ←/→ — соседний элемент, Esc — закрыть. "
                     "«Как читать график» — под каждым графиком, «увеличить» — крупный просмотр.</p>")
        else:
            inner = '<p class="lead">Нажмите на график, чтобы открыть его крупно (вписать, 1:1, 2×) и листать стрелками.</p>'
        for sec, cs in groups.items():
            if len(groups) > 1 or sec:
                inner += "<h3>" + esc(CHART_SECTION_LABELS.get(sec, sec or "Прочее")) + "</h3>"
            inner += '<div class="gallery charts">' + "".join(self.chart_fig(c, primary=True) for c in cs) + "</div>"
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
        if svg_html:
            svg_html = flow_a11y(svg_html, scope, {str(n["id"]): n for n in nodes}, title)
        chips = "".join('<button type="button" class="nchip" data-node="' + esc(n["id"]) + '">' + esc(text_of(n.get("label")) or n["id"])
                        + "</button>" for n in nodes)
        anchor = "" if embedded else ' id="flow-' + esc(slug(key)) + '"' + (' tabindex="-1"' if self.ich else "")
        if not embedded:
            self.anchors["flow"].add(key)
        body = '<div class="flow' + (" embedded" if embedded else "") + '"' + (' data-flow="' + esc(key) + '"' if self.ich else "") + anchor + "><h3>" + esc(title) + "</h3>"
        if svg_html:
            body += psi_wrap("flow", '<div class="flowsvg" id="' + scope + '" data-imgkey="flow-' + esc(slug(key)) + '" data-cap="' + esc(title) + '">'
                             + svg_html + "</div>", title)
        if chips:
            body += '<div class="nchips"><span class="muted">Блоки схемы:</span> ' + chips + "</div>"
        if svg_html:
            body += ('<p class="muted small">Нажмите на блок схемы — откроется расшифровка: что это, как сейчас, что сделать, '
                     "как измерять и связанные предложения; «🔍 Увеличить» или клик по фону — крупный просмотр с живой схемой.</p>")
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
        # видение — до конца года, в котором кончается последняя задача (горизонт 6 мес. и задачи до 24-го → шкала 7–12 и «год 2»,
        # а не «мес. 7–18, 19–30»); при горизонте, кратном 12, — как раньше
        V = 0 if max_end <= H else int(math.ceil(max_end / 12.0)) * 12 - H
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
        a = H
        while a < H + V:                       # блоки видения по годам; первый — до конца года горизонта (короткая подпись «7–12»)
            b = (a // 12 + 1) * 12
            lab = ("год %d" % (b // 12)) if a % 12 == 0 else "%d–%d" % (a + 1, b)
            tip = "" if a % 12 == 0 else ' title="месяцы %d–%d · видение, год %d"' % (a + 1, b, b // 12)
            scale += '<span class="yr" style="left:%.2f%%;width:%.2f%%"%s>%s</span>' % (pos(a), pos(b) - pos(a), tip, esc(lab))
            a = b
        # пробелы плана: месяцы горизонта и видения без единой задачи (SM: «месяцев 7–12 нет») — заштрихованы, в легенде и в предупреждении
        covered = set()
        for t in tasks:
            covered.update(range(t["start"], t["end"] + 1))
        gaps, g0 = [], None
        for m in range(1, max_end + 2):
            if m <= max_end and m not in covered:
                g0 = m if g0 is None else g0
            elif g0 is not None:
                gaps.append((g0, m - 1))
                g0 = None
        self.gantt_gaps = gaps
        phases, order = {}, []
        for i, t in enumerate(tasks):
            if t["phase"] not in phases:
                phases[t["phase"]] = []
                order.append(t["phase"])
            phases[t["phase"]].append(i)
        rows = ""
        js = []
        pgon = bool(self.pg)                    # режим отслеживания: статусы задач и линия «Сегодня»
        for i, t in enumerate(tasks):
            when = self.when(t["start"], t["end"], H)
            js.append(dict(t, i=i, when=when))
            if pgon:
                pgt = self.pg_gantt.get(t["id"]) or self.pg_gantt.get("task:" + t["task"])
                if pgt:
                    js[-1]["pg"] = pgt
        for pi, ph in enumerate(order):
            vis = ph.lower() in ("vision", "видение")
            rows += '<div class="gphase"><span class="gdot c%d"></span>%s</div>' % (pi % 8, esc("Видение" if ph.lower() == "vision" else ph))
            for i in phases[ph]:
                t = tasks[i]
                left, right = pos(t["start"] - 1), pos(t["end"])
                pgt = js[i].get("pg")
                plab, aria_st = "", ""
                if pgt:
                    gs, pct = pgt["status"], int(round(pgt["progress"] * 100))
                    gtxt = GSTATUS_LABELS.get(gs, gs)
                    tip = js[i]["when"] + " · " + gtxt + " · выполнено " + str(pct) + "%"
                    aria_st = ", " + gtxt + ", выполнено " + str(pct) + "%"
                    if t["type"] == "milestone":
                        bar = '<span class="gms gs-%s" style="left:%.2f%%" title="веха: %s"></span>' % (esc(gs), (left + right) / 2, esc(tip))
                        a, b = (left + right) / 2, (left + right) / 2
                    else:
                        bar = ('<span class="gbar gs-%s%s" style="left:%.2f%%;width:%.2f%%" title="%s"><span class="gfill" style="width:%d%%"></span></span>'
                               % (esc(gs), " vis" if vis or t["start"] > H else "", left, max(0.8, right - left), esc(tip), pct))
                        a, b = left, right
                    txt = esc(GSTATUS_ICONS.get(gs, "•") + " " + str(pct) + "%" + (" · " + gtxt if gs in ("behind", "done") else ""))
                    # подпись — после полосы, перед ней (у правого края) или внутри (полоса во всю ширину); всегда на подложке
                    if b <= 78:
                        plab = '<span class="gpl gpl-%s" style="left:calc(%.2f%% + 8px)">%s</span>' % (esc(gs), b, txt)
                    elif a >= 22:
                        plab = '<span class="gpl gpl-%s" style="right:calc(%.2f%% + 8px)">%s</span>' % (esc(gs), 100 - a, txt)
                    else:
                        plab = '<span class="gpl gpl-%s" style="left:calc(%.2f%% + 4px)">%s</span>' % (esc(gs), a, txt)
                elif t["type"] == "milestone":
                    bar = '<span class="gms c%d" style="left:%.2f%%" title="веха: %s"></span>' % (pi % 8, (left + right) / 2, esc(js[i]["when"]))
                else:
                    bar = '<span class="gbar c%d%s" style="left:%.2f%%;width:%.2f%%" title="%s"></span>' % (
                        pi % 8, " vis" if vis or t["start"] > H else "", left, max(0.8, right - left), esc(js[i]["when"]))
                sep = '<span class="gsep" style="left:%.2f%%"></span>' % Wm if V else ""
                gid = (' data-gid="' + esc(t["id"]) + '"') if self.ich and t["id"] and t["id"] not in self.anchors["gantt"] else ""
                if t["id"]:
                    self.anchors["gantt"].add(t["id"])
                rows += ('<div class="grow" data-g="%d"%s tabindex="0" role="button" aria-label="%s"><div class="glabel">%s%s%s</div>'
                         '<div class="gtrack">%s%s</div></div>') % (
                    i, gid, esc(t["task"] + ", " + js[i]["when"] + aria_st), ('<span class="gid">' + esc(t["id"]) + "</span> " if t["id"] else ""),
                    self.links(esc(t["task"])), (' <span class="muted">· ' + esc(t["owner"]) + "</span>" if t["owner"] else ""), sep, bar + plab)
        self.gantt_js = js
        gch = self.charts_by_key.get("gantt")
        legend = ('<p class="muted small">Шкала: месяцы плана 1–%d (с %s)%s. Полоса — работа, ромб — веха. Нажмите на строку: '
                  "критерий готовности, зависимости и шаги связанных предложений.%s</p>") % (
            H, self.month_label(1, True), (", дальше — годы видения" if V else ""),
            (' <a class="emb" href="' + esc(self.chart_href(gch)) + '">Гант как ' + ("интерактивный график" if gch.get("svg") else "картинка") + "</a>"
             if gch and (gch.get("img") or gch.get("svg")) else ""))
        today, gin_cls = "", ""
        if pgon and self.pg_cur:
            cur = self.pg_cur
            m0 = self.pg_elapsed if self.pg_elapsed is not None and int(self.pg_elapsed) + 1 == cur else cur - 0.5
            m0 = max(0.0, min(float(H + V), m0))
            x = pos(m0)
            # подпись справа от линии (слева — закреплённый столбец задач на телефоне), у правого края — слева от линии
            tx = "translateX(4px)" if x <= 70 else "translateX(calc(-100% - 4px))"
            scale += '<b class="gtd" style="left:%.2f%%;transform:%s">Сегодня · мес. %d</b>' % (x, tx, cur)
            today = '<div class="gtoday" style="--x:%.4f" aria-hidden="true"></div>' % (x / 100.0)
            gin_cls = " pgon"
            used = [js[i]["pg"]["status"] for i in range(len(js)) if js[i].get("pg")]
            legend += ('<p class="pg-glegend small">' + " ".join(st_chip(s, GSTATUS_LABELS, GSTATUS_ICONS, "gst") for s in GSTATUS_LABELS if s in used)
                       + ' <span class="muted">· заливка полосы — доля выполненного; красная линия — сегодня (месяц плана %d, проверка %s)</span></p>'
                       % (cur, esc(text_of(self.pg.get("checked")) or "—")))
        gap_ovl = ""
        if gaps:
            names = ", ".join(("%d" % a if a == b else "%d–%d" % (a, b)) for a, b in gaps)
            for a, b in gaps:
                x0, x1 = pos(a - 1) / 100.0, pos(b) / 100.0
                gap_ovl += ('<div class="ggap" style="--x0:%.4f;--x1:%.4f" title="месяцы %s: задач нет" aria-hidden="true"></div>'
                            % (x0, x1, ("%d" % a if a == b else "%d–%d" % (a, b))))
                scale += '<b class="ggap-l" style="left:%.2f%%;width:%.2f%%" title="задач нет">нет задач</b>' % (pos(a - 1), pos(b) - pos(a - 1))
            gin_cls += " has-gaps"
            legend += ('<p class="small gaps-note">Месяцы без задач: %s — план не покрывает весь горизонт; на диаграмме заштрихованы. '
                       "Дополните data/gantt.json задачами или вехами на эти месяцы.</p>" % esc(names))
            self.warn("data/gantt.json: месяцы %s без задач — диаграмма показывает весь горизонт (план 1–%d и видение до %d-го месяца), "
                      "пробелы заштрихованы; контракт Ганта — все месяцы горизонта и видения" % (names, H, H + V or max_end))
        inner = (legend + '<div class="gantt"><div class="gin' + gin_cls + '"><div class="ghead"><div class="gl">Задача</div><div class="gscale">'
                 + scale + "</div></div>" + rows + today + gap_ovl + "</div></div>")
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
                kid = text_of(k.get("id"))
                kattr = (' data-kid="' + esc(kid) + '"') if self.ich and kid and kid not in self.anchors["kanban"] else ""
                if kid:
                    self.anchors["kanban"].add(kid)
                html_cards += ('<div class="kcard" data-k="%d"%s tabindex="0" role="button"><div class="kid">%s</div><div class="kt">%s</div>'
                               '<div class="kmeta">%s%s</div>%s</div>') % (
                    i, kattr, esc(text_of(k.get("id"))), esc(text_of(k.get("title"))), (self.badge("p", pr) + " " if pr else ""),
                    ('<span class="muted">' + esc(eff) + "</span>" if eff else ""),
                    ('<div class="ktags">' + "".join('<span class="tag">' + esc(t) + "</span>" for t in str_list(k.get("tags"))) + "</div>"
                     if k.get("tags") else ""))
            out.append('<div class="kcol"><div class="khead"><b>' + esc(name) + '</b><span class="kcount' + (" over" if over else "")
                       + '" title="карточек / лимит WIP">' + cnt + "</span></div>" + (html_cards or '<div class="kempty muted">пусто</div>') + "</div>")
        inner = ('<p class="muted small">Нажмите на карточку: цель, KPI, шаги, ссылки и карточка предложения. Красный счётчик — превышен лимит WIP.</p>'
                 '<div class="kanban">' + "".join(out) + "</div>")
        kp = self.pg_kanban if self.pg else None
        if kp and kp["columns"]:
            inner = self.kanban_facts(cards, cols, out, kp)
        self.add("kanban", "Kanban", self.section("kanban", "Доска Kanban <span class=\"muted\">(%d)</span>" % len(cards), self.links(inner)))

    def kanban_facts(self, cards, cols, plan_cols_html, kp):
        """Две доски: «Как в плане» (kanban.json) и «По фактам» (kanban-progress.json) с меткой «перенесено из …».
        Переключатель — радиокнопки и CSS (работает и без скрипта)."""
        idx = {text_of(k.get("id")): i for i, k in enumerate(cards) if text_of(k.get("id"))}
        moves = {}
        for m in kp["moves"]:
            moves[text_of(m.get("id"))] = m
        wip = dict(cols)
        names = [n for n, _ in cols if n != "Без колонки"] + [n for n in kp["columns"] if n not in [x for x, _ in cols]]
        fout = []
        for name in names:
            ids = kp["columns"].get(name, [])
            w = wip.get(name)
            over = w is not None and len(ids) > w
            html_cards = ""
            for pid in ids:
                i = idx.get(pid)
                k = cards[i] if i is not None else {}
                title = text_of(k.get("title")) or self.titles.get(pid, "")
                st = self.pg_status(pid)
                mv = moves.get(pid)
                moved = ""
                if mv and text_of(mv.get("from")) and text_of(mv.get("from")) != name:
                    moved = ('<div class="kmoved" title="' + esc(text_of(mv.get("reason"))) + '">↪ перенесено из «' + esc(text_of(mv.get("from"))) + "»"
                             + (' <span class="muted">— ' + esc(text_of(mv.get("reason"))) + "</span>" if mv.get("reason") else "") + "</div>")
                attr = ('data-k="%d"' % i) if i is not None else ('data-pid="' + esc(pid) + '"' if pid in self.titles else "")
                html_cards += ('<div class="kcard%s" %s tabindex="0" role="button"><div class="kid">%s</div><div class="kt">%s</div><div class="kmeta">%s</div>%s</div>'
                               % (" moved" if moved else "", attr, esc(pid), esc(title), st_chip(st), moved))
            fout.append('<div class="kcol"><div class="khead"><b>' + esc(name) + '</b><span class="kcount' + (" over" if over else "")
                        + '" title="карточек / лимит WIP">' + str(len(ids)) + (" / " + str(w) if w is not None else "") + "</span></div>"
                        + (html_cards or '<div class="kempty muted">пусто</div>') + "</div>")
        nmoves = sum(1 for m in kp["moves"] if text_of(m.get("from")) != text_of(m.get("to")))
        return ('<p class="muted small">Нажмите на карточку: цель, KPI, шаги, ссылки и карточка предложения. Красный счётчик — превышен лимит WIP. '
                "«По фактам» — карточки в колонках по реальным статусам (проверка " + esc(text_of(self.pg.get("checked")) or "—")
                + "); план в kanban.json не меняется.</p>"
                '<div class="kbv" role="group" aria-label="Вид доски"><span class="lbl muted small">Вид доски:</span>'
                '<input type="radio" name="kbv" id="kbv-plan" class="kbv-r" checked><label for="kbv-plan">Как в плане</label>'
                '<input type="radio" name="kbv" id="kbv-facts" class="kbv-r"><label for="kbv-facts">По фактам <span class="kbv-n">· перенесено: '
                + str(nmoves) + "</span></label>"
                '<div class="kanban kb-plan">' + "".join(plan_cols_html) + '</div><div class="kanban kb-facts">' + "".join(fout) + "</div>"
                + self.kanban_off(kp) + "</div>")

    def kanban_off(self, kp):
        """Предложения в работе или сделанные, которых нет на доске (kanban-progress.off_board)."""
        off = [m for m in kp.get("off_board") or [] if text_of(m.get("id"))]
        if not off:
            return ""
        return ('<p class="kb-off small">Не на доске, но уже в работе или сделано: ' + " ".join(
            '<span class="pg-pp">' + (pid_link(text_of(m["id"]), self.titles) if text_of(m["id"]) in self.titles else esc(text_of(m["id"]))) + " "
            + st_chip(self.pg_status(text_of(m["id"])) or text_of(m.get("status"))) + "</span>" for m in off) + "</p>")

    # --- 9. макеты
    def sec_mockups(self):
        ms = [m for m in self.mock.values() if str(m.get("kind") or "concept") != "current"]
        if not ms:
            return
        lead = ("Продукта ещё нет: все макеты — концепт продукта целиком, а не существующие экраны. " if self.concept
                else "Все макеты — концепты, а не существующие функции. ")
        # 1.5: галерея вариантов дизайна и рабочий прототип рядом с макетами (если есть) — живые HTML, открываются в новой вкладке
        more = []
        for rel, label in (("mockups/gallery.html", "галерея вариантов дизайна"), ("prototype/index.html", "рабочий прототип")):
            if (self.out / rel).is_file() and self.rel_link(rel):
                more.append('<a href="' + esc(self.rel_link(rel)) + '" target="_blank" rel="noopener">' + label + " ↗</a>")
        inner = ('<p class="lead">' + lead + "Нажмите на макет, чтобы рассмотреть его крупно; "
                 "у макетов с референсом поверх картинки видны нумерованные элементы с описанием.</p>"
                 + ('<p class="small">Также: ' + " · ".join(more) + " — «Открыть интерактивный макет» в просмотре ведёт на живой HTML.</p>" if more else "")
                 + '<div class="gallery mocks">' + "".join(self.mock_fig(m) for m in ms) + "</div>")
        self.add("mockups", "Макеты (концепты)", self.section("mockups", "Макеты ключевых экранов" if self.concept else "Макеты предлагаемых функций", self.links(inner)))

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
        if self.concept:            # режим идеи: текущего состояния продукта нет
            return
        items, seen = [], set()
        d = self.out / "mockups" / "current"
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                    k = self.img.add("mockups/current/" + p.name, "cur-" + p.stem)
                    if k and k not in seen:
                        seen.add(k)
                        items.append((k, p.stem.replace("_", " ").replace("-", " "), p.name))       # (ключ, подпись, подсказка[, ключ макета])
        for m in self.mock.values():
            if str(m.get("kind")) == "current" and m.get("img") and m["img"] not in seen:
                seen.add(m["img"])
                items.append((m["img"], text_of(m.get("title")) or m["key"], str(m.get("viewport") or ""), m["key"]))
        if not items:
            return
        for it in items:
            if len(it) > 3:
                self.anchors["mockup"].add(it[3])
        figs = "".join(self.fig(it[0], "<b>" + esc(it[1]) + '</b> <span class="tag">факт</span>', "Текущее состояние — " + it[1], "current",
                                "mobile" if self.is_mobile_img(it[0], it[2]) else "", attrs=(' data-mock="' + esc(it[3]) + '"' if len(it) > 3 and self.ich else ""))
                       for it in items)
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
            ncls = {c: (' class="num"' if num_col([x.get(c) for x in mon]) else "") for c in cols}
            parts.append("<details><summary>Помесячно: " + esc(SCENARIO_LABELS.get(s, s)) + " (" + str(len(mon)) + " мес.)</summary><div class=\"tbl\"><table class=\"data\"><thead><tr>"
                         + "".join("<th" + ncls[c] + ">" + esc(self.MODEL_NAMES.get(c, c)) + "</th>" for c in cols) + "</tr></thead><tbody>"
                         + "".join("<tr>" + "".join("<td" + ncls[c] + ">" + esc(text_of(x.get(c))) + "</td>" for c in cols) + "</tr>" for x in mon)
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
        feats, flabels = [], {}
        for c in sorted(self.comp, key=lambda x: not x.get("self")):   # подписи строки self — приоритетнее
            fl = c.get("features_labels") if isinstance(c.get("features_labels"), dict) else {}
            for k, v in fl.items():
                if text_of(v).strip() and str(k) not in flabels:
                    flabels[str(k)] = text_of(v).strip()
        for c in self.comp:
            if isinstance(c.get("features"), dict):
                for f in c["features"]:
                    if str(f) not in feats:
                        feats.append(str(f))
        # подпись функции: features_labels, иначе ключ по-человечески (snake_case → слова), без обрезки по буквам
        self.comp_feature_labels = {f: flabels.get(f) or humanize_key(f) for f in feats}
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
            # verdict ≤ 45 знаков — в заголовке карточки и в подсказке матрицы; длинный — verdict_long или раскрытие
            o["verdict_short"], o["verdict_long"], o["verdict_cut"] = verdict_parts(o["verdict"], text_of(c.get("verdict_long")))
            for k in ("better_than_us", "we_better", "best_solutions", "complaints", "adopt", "avoid", "sources"):
                o[k] = str_list(c.get(k))
            hay = " ".join([o["name"], o["url"], o["segment"], o["price"], o["monetization"], o["languages"], o["audience"],
                            o["design_note"], o["verdict"], o["verdict_long"], COMP_TYPE_LABELS.get(o["type"], o["type"])]
                           + o["better_than_us"] + o["we_better"] + o["best_solutions"] + o["complaints"] + o["adopt"] + o["avoid"]
                           + [self.comp_feature_labels.get(k, k) for k, v in o["features"].items() if v])
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
            # «Аудитория» — числовая колонка, только если все значения числа; иначе текст с переносом (A-1.13, B-48)
            aud_num = num_col([c.get("audience_size") for c in self.communities])
            aud_cls = ' class="num"' if aud_num else ' class="aud"'
            for c in self.communities:
                br = to_int(c.get("ban_risk"))
                trs += ("<tr><td>" + ext_link(c.get("url"), text_of(c.get("name")) or None) + "</td><td>" + esc(text_of(c.get("platform")))
                        + "</td><td>" + esc(text_of(c.get("language"))) + "</td><td" + aud_cls + ">" + wbr_long(esc(text_of(c.get("audience_size")) or "—"))
                        + '</td><td class="rules">' + wbr_long(esc(text_of(c.get("self_promo_rules")))) + "</td><td>" + wbr_long(esc(", ".join(str_list(c.get("allowed_formats")))))
                        + '</td><td class="num" data-v="' + str(br if br is not None else "") + '"><span class="risk r' + str(br or 0) + '">'
                        + (str(br) if br is not None else "—") + "</span></td><td>" + (ext_link(c.get("source"), "источник") if c.get("source") else "") + "</td></tr>")
            parts.append("<h3>Сообщества (%d)</h3>" % len(self.communities) + '<div class="tbl"><table class="data sortable comm"><thead><tr><th>Площадка</th>'
                         "<th>Платформа</th><th>Язык</th><th" + aud_cls + ">Аудитория</th><th class=\"rules\">Правила самопромо</th><th>Форматы</th><th class=\"num\">Риск бана</th><th>Источник</th>"
                         "</tr></thead><tbody>" + trs + "</tbody></table></div>")
        if self.keywords:
            trs = ""
            comp_cls = ' class="num"' if num_col([k.get("competition") for k in self.keywords]) else ""
            for k in self.keywords:
                vol = num(k.get("volume"))
                trs += ("<tr><td>" + esc(text_of(k.get("query"))) + "</td><td>" + esc(text_of(k.get("lang"))) + "</td><td>" + esc(text_of(k.get("cluster")))
                        + "</td><td>" + esc(text_of(k.get("intent"))) + '</td><td class="num" data-v="' + ("%g" % vol if vol is not None else "") + '">'
                        + (fmt_num(vol) if vol is not None else '<span class="muted">нет данных</span>') + "</td><td>" + esc(text_of(k.get("volume_source")))
                        + "</td><td" + comp_cls + ">" + esc(text_of(k.get("competition")) or "—") + "</td></tr>")
            parts.append("<h3>Поисковые запросы (%d)</h3>" % len(self.keywords) + '<div class="toolbar"><input type="search" data-filter-table="kw-table" '
                         'placeholder="Фильтр запросов…" aria-label="Фильтр запросов"></div><div class="tbl tall"><table id="kw-table" class="data sortable"><thead><tr>'
                         "<th>Запрос</th><th>Язык</th><th>Кластер</th><th>Намерение</th><th class=\"num\">Объём</th><th>Источник объёма</th><th" + comp_cls + ">Конкуренция</th>"
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
        ok = bad = unk = untitled = 0
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
            url, title = text_of(s.get("url")).strip(), text_of(s.get("title")).strip()
            if url_like_title(title, url):
                # название пустое, равно URL или обрезанный URL — домен и путь сокращённо + пометка
                shown = short_url(url or title) if (url or title) else "—"
                title_html = ('<span class="untitled" title="' + esc(url or title) + '">' + esc(shown) + '</span> <span class="tag">без названия</span>')
                untitled += 1
            else:
                title_html = esc(title)
            trs += ("<tr><td>" + esc(text_of(s.get("id"))) + '</td><td class="url">' + ext_link(url) + '</td><td class="stitle">' + title_html
                    + "</td><td>" + esc(text_of(s.get("date_checked"))) + "</td><td>" + esc(text_of(s.get("used_for"))) + '</td><td data-v="'
                    + (str(st) if st is not None else "") + '">' + badge + "</td><td>" + esc(text_of(s.get("note"))) + "</td></tr>")
        summary = ('<p class="srcsum"><span class="tag">всего: %d</span> <span class="st-ok">доступны: %d</span> <span class="st-bad">ошибки: %d</span> '
                   '<span class="st-unk">не проверено: %d</span>%s</p>') % (
            len(self.sources), ok, bad, unk, (' <span class="st-unk">без названия: %d</span>' % untitled) if untitled else "")
        if untitled:
            self.warn("data/sources.json: %d записей без названия (title пуст, равен URL или обрезанный URL) — показаны доменом и путём" % untitled)
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

    # --- 17. глоссарий (research/glossary.md от build_appendix.py; термины текста кликабельны — ps-ents.js)
    def sec_glossary(self):
        if not self.gloss:
            return
        trs = "".join('<tr id="gl-' + esc(g["key"]) + '"><td>' + esc(g["label"])
                      + (' <span class="muted small">(' + esc(", ".join(g["forms"][1:])) + ")</span>" if len(g["forms"]) > 1 else "")
                      + "</td><td>" + esc(g["what"]) + (' <span class="muted small">Источник: ' + esc(g["src"]) + "</span>" if g["src"] else "")
                      + "</td></tr>" for g in self.gloss)
        inner = ('<p class="lead">Термины, которые встречаются в тексте (research/glossary.md). В тексте термин подчёркнут пунктиром: наведите — '
                 "определение, нажмите — где ещё упоминается.</p>"
                 '<div class="toolbar"><input type="search" data-filter-table="gl-table" placeholder="Фильтр терминов…" aria-label="Фильтр терминов"></div>'
                 '<div class="tbl"><table id="gl-table" class="data gl-table"><thead><tr><th>Термин</th><th>Что это</th></tr></thead><tbody>'
                 + trs + "</tbody></table></div>")
        self.add("glossary", "Глоссарий", self.section("glossary", "Глоссарий <span class=\"muted\">(%d)</span>" % len(self.gloss), self.links(inner)))

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
            "comp_feature_labels": getattr(self, "comp_feature_labels", {}),
            "subscales": SUBSCALES,
            "lite": bool(self.lite),
        }

    # --- интерактивные графики: проверка целей ссылок и пояснения для страницы
    REG_FILTERS = ("category", "horizon", "class", "quadrant", "priority")

    def link_target_ok(self, href):
        """Есть ли на собранной странице цель ссылки из meta графика (схема ссылок — references/data-contract.md;
        переводит их в действия роутер страницы: см. parseHref/go в JS)."""
        h = text_of(href)
        secs = {sid for sid, _, _ in self.nav}
        m = re.fullmatch(r"#s(\d+)", h)
        if m:
            return "s-" + str(int(m.group(1))) in secs
        m = re.fullmatch(r"#p/(P\d+)", h)
        if m:
            return "registry" in secs and m.group(1) in {r["id"] for r in self.rows}
        m = re.fullmatch(r"#registry(?:\?(.*))?", h)
        if m:
            pairs = [x.split("=", 1) for x in m.group(1).split("&")] if m.group(1) else []
            return "registry" in secs and all(len(p) == 2 and p[0] in self.REG_FILTERS and p[1] for p in pairs)
        m = re.fullmatch(r"#(gantt|kanban|mockup|flow)/(.+)", h)
        if m:
            return m.group(2) in self.anchors[m.group(1)]
        m = re.fullmatch(r"#competitor/(.+)", h)
        if m:
            if "competitors" not in secs:
                return False
            c = next((x for x in getattr(self, "comp_js", []) if x["slug"] == m.group(1)), None)
            return bool(c) and (not c["self"] or bool(getattr(self, "comp_features", [])))
        m = re.fullmatch(r"#chart/([\w-]+)(?:/(.+))?", h)
        if m:
            c = self.charts_by_key.get(m.group(1))
            if not c or not c.get("svg") or m.group(1) not in self.anchors.get("chart", ()):
                return False
            return m.group(2) is None or m.group(2) in (c["meta"].get("elements") or {})
        return False

    def prepare_chart_meta(self):
        """Пояснения встроенных графиков в компактном виде {ключ: {title, howto, elements: [{id, title, kind, …}]}} (порядок
        meta.elements — порядок ←/→). Ссылки без цели на этой странице не попадают в панель: предупреждение, в --strict — ошибка."""
        out, drops, total = OrderedDict(), {}, 0
        for c in self.charts:
            if not c.get("svg") or c["key"] not in self.anchors.get("chart", ()):
                continue
            meta = c["meta"]
            els = []
            for eid, e in (meta.get("elements") or {}).items():
                if not isinstance(e, dict):
                    continue
                o = OrderedDict([("id", str(eid))])
                for f in ("title", "kind", "summary", "meaning", "highlight"):
                    v = text_of(e.get(f)).strip()
                    if v:
                        o[f] = v
                acts = [text_of(x).strip() for x in (e.get("actions") if isinstance(e.get("actions"), list) else []) if text_of(x).strip()]
                if acts:
                    o["actions"] = acts
                mx = [OrderedDict([("label", text_of(x.get("label"))), ("value", text_of(x.get("value"))), ("tag", text_of(x.get("tag")))])
                      for x in (e.get("metrics") if isinstance(e.get("metrics"), list) else []) if isinstance(x, dict) and text_of(x.get("label"))]
                if mx:
                    o["metrics"] = mx
                links = []
                for l in e.get("links") if isinstance(e.get("links"), list) else []:
                    href = text_of(l.get("href")) if isinstance(l, dict) else ""
                    total += 1
                    if self.link_target_ok(href):
                        links.append(OrderedDict([("label", text_of(l.get("label")) or href), ("href", href)]))
                    else:
                        drops[href] = drops.get(href, 0) + 1
                if links:
                    o["links"] = links
                els.append(o)
            out[c["key"]] = OrderedDict([("title", c["title"]), ("elements", els)])
        self.chart_page_meta = out
        self.chart_link_total = total
        self.chart_link_drops = drops
        if drops:
            n = sum(drops.values())
            top = sorted(drops.items(), key=lambda kv: (-kv[1], kv[0]))
            msg = ("пояснения графиков: %d из %d ссылок без цели на этой странице не показаны в панели: %s%s — нет раздела стратегии "
                   "(research/strategy.md), блока или элемента; проверьте полноту разделов" % (
                       n, total, ", ".join("%s ×%d" % kv for kv in top[:10]), " и ещё %d" % (len(top) - 10) if len(top) > 10 else ""))
            self.warn(msg)
            self.strict_errors.append(msg)
        return out

    def chart_layers(self):
        """Панель пояснений графиков (справа; на экранах < 700 px — нижний лист), подсказка при наведении и живая область."""
        return ('<aside id="cp" class="cpanel" role="dialog" aria-modal="false" aria-labelledby="cp-title" hidden>'
                '<div class="cp-head"><div class="cp-hg"><div class="cp-chart small muted" id="cp-chart"></div><h3 id="cp-title"></h3>'
                '<span class="cp-kind" id="cp-kind"></span></div><button type="button" class="cp-x" data-cp-close aria-label="Закрыть панель (Esc)">✕</button></div>'
                '<div class="cp-body" id="cp-body"></div><div class="cp-nav"><button type="button" data-cp-step="-1" aria-label="Предыдущий элемент (←)">← Пред.</button>'
                '<span id="cp-pos" class="small muted"></span><button type="button" data-cp-step="1" aria-label="Следующий элемент (→)">След. →</button></div></aside>'
                '<div id="cp-tip" class="ps-tip" role="tooltip" hidden></div><div id="cp-live" class="ps-sr" aria-live="polite"></div>')

    def assemble(self):
        title = self.page_title()
        self.prepare_chart_meta()
        who, cp = self.author_line()
        rows = [{k: v for k, v in r.items()} for r in self.rows]
        pairs = [
            ("d-meta", self.meta_js()),
            ("d-registry", rows),
            ("d-metrics", self.metrics_def() if self.rows else []),
            ("d-refs", getattr(self, "refs_js", {})),
            ("d-gantt", getattr(self, "gantt_js", [])),
            ("d-kanban", [dict(c) for c in self.kanban_cards]),
            ("d-flows", getattr(self, "flow_nodes", {})),
            ("d-comp", getattr(self, "comp_js", [])),
            ("d-img", self.img.map),
            ("d-thumb", self.img.thumbs),
            ("d-alias", self.img.alias),
        ]
        if self.pg:                             # режим отслеживания: подписи статусов для скрипта страницы
            pairs.append(("d-progress", {
                "labels": STATUS_LABELS, "icons": STATUS_ICONS, "order": {k: i for i, k in enumerate(STATUS_ORDER)},
                "closed": sorted(STATUS_CLOSED), "glabels": GSTATUS_LABELS, "gicons": GSTATUS_ICONS, "source": SOURCE_LABELS,
                "match": MATCH_LABELS, "state": ISSUE_STATE_LABELS, "code": CODE_KIND_LABELS,
                "reason": {"completed": "выполнено", "not_planned": "не планируется", "reopened": "переоткрыт", "duplicate": "дубликат"}, "checked": text_of(self.pg.get("checked"))}))
        if self.chart_page_meta and not self.site:     # single/lite: пояснения графиков — в странице (SVG уже в разметке разделов)
            pairs.append(("d-charts", self.chart_page_meta))
        if getattr(self, "mock_refs", None):            # подсказки элементов макетов (data-hs-*) — те же зоны, что у референсов
            for i, (k, v) in enumerate(pairs):
                if k == "d-refs":
                    merged = dict(v)
                    merged.update(self.mock_refs)
                    pairs[i] = (k, merged)
        if self.gloss:                                  # глоссарий: подсказки и кликабельные термины текста (ps-ents.js), поиск
            pairs.append(("d-gloss", self.gloss))
        if self.docs and not self.site:                 # прочие исследования для поиска (site — лениво, assets/search-docs.js)
            pairs.append(("d-docs", self.docs))
        layer_js, self.layer_css = layer_assets(self.warn)
        # слои 1.5 (просмотр графиков и схем, поиск, сущности) — в том же скрипте сразу после app.js: хеш CSP считается по всему тексту
        js = JS + ("\n" + layer_js if layer_js else "")
        head_js = HEAD_JS
        self.extra = self.extras()
        if self.site:
            csp = None
        else:
            h1 = base64.b64encode(hashlib.sha256(js.encode("utf-8")).digest()).decode()
            h2 = base64.b64encode(hashlib.sha256(head_js.encode("utf-8")).digest()).decode()
            # хуки расширения (build/extra.js, build/extra/*.js) в single/lite — свои встроенные скрипты со своими хешами
            hx = "".join(" 'sha256-" + base64.b64encode(hashlib.sha256(t.encode("utf-8")).digest()).decode() + "'" for _, kind, t in self.extra if kind == "js")
            # --lite: картинки — файлы рядом со страницей (assets/), 'self' — только тот же источник, внешних по-прежнему нет
            img_src = "img-src data: 'self'" if self.lite else "img-src data:"
            csp = ("default-src 'none'; " + img_src + "; style-src 'unsafe-inline'; script-src 'sha256-" + h1 + "' 'sha256-" + h2 + "'" + hx + "; "
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
                 "без внешних запросов" + ("; страница состоит из нескольких файлов — index.html, assets/ и data/: пересылайте папку целиком (или strategy-site.zip)"
                                           if self.site else "; полноразмерные картинки — в папке assets/ рядом со страницей (пересылайте вместе с ней)" if self.lite else "")
                 + ". Концепты и макеты — не существующие функции; цифры помечены [факт]/[оценка]/[допущение].</p></footer>")
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
        # просмотр макетов (1.5): связанные P-id, «Открыть интерактивный макет», переключатель темы снимка
        layers = layers.replace('<span id="lbcap"></span>', '<span id="lbcap"></span><span id="lbpids" hidden></span>'
                                '<a id="lbopen" class="lbopen" target="_blank" rel="noopener" hidden>Открыть интерактивный макет ↗</a>'
                                '<button type="button" id="lbtheme" hidden>Тема</button>')
        if self.chart_page_meta:
            layers += self.chart_layers()
        if self.site:
            return self.assemble_site(pairs, title, metas, foot, nav, mbar, layers, js, head_js)
        data_blocks = [json_script(i, o) for i, o in pairs]
        x_css = "".join("<style>" + t.replace("</", "<\\/") + "</style>" for _, kind, t in self.extra if kind == "css")
        x_js = "".join("<script>" + t + "</script>" for _, kind, t in self.extra if kind == "js")
        page = ("<!doctype html>\n<html lang=\"ru\"><head><meta charset=\"utf-8\">"
                '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
                '<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light dark">'
                + metas + '<link rel="icon" href="data:,"><title>' + esc(title) + "</title><style>" + theme_css(self.tokens) + CSS + (CHART_CSS if self.ich else "") + (PROGRESS_CSS if self.pg else "")
                + (CONCEPT_CSS if self.concept else "") + self.layer_css + "</style>" + x_css
                + "<script>" + head_js + "</script></head><body>"
                '<a class="skip" href="#main">К содержанию</a>' + mbar + '<div class="wrap">' + nav + '<main id="main">'
                + "".join(self.sections) + foot + "</main></div>" + layers + "".join(data_blocks) + "<script>" + js + "</script>" + x_js + "</body></html>\n")
        return page

    EXTRA_MAX = 2 * 1024 * 1024

    def extras(self):
        """Хуки расширения страницы (подключаемые слои) во всех режимах: build/extra.css, build/extra.js и папка build/extra/*.css|*.js
        (по имени файла). site — файлы assets/extra.* и assets/extra/<имя>; single/lite — встроенные <style>/<script> (у скрипта —
        свой хеш CSP). Скрипт расширения идёт после app.js: API window.PS (on/emit/replace, data, router — references/interactive-site.md)."""
        out = []
        cands = [(self.out / "build" / "extra.css", "assets/extra.css", "css"), (self.out / "build" / "extra.js", "assets/extra.js", "js")]
        d = self.out / "build" / "extra"
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if p.is_file() and p.suffix.lower() in (".css", ".js") and re.fullmatch(r"[\w.-]+", p.name):
                    cands.append((p, "assets/extra/" + p.name, p.suffix.lower()[1:]))
        for p, rel, kind in cands:
            if not p.is_file():
                continue
            try:
                t = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                self.warn("%s не прочитан (%s) — не подключён" % (p.relative_to(self.out).as_posix(), str(e)[:80]))
                continue
            if len(t.encode("utf-8")) > self.EXTRA_MAX:
                self.warn("%s больше 2 МБ — не подключён" % p.relative_to(self.out).as_posix())
                continue
            if kind == "js" and not self.site and re.search(r"</script", t, re.I):
                self.warn("%s содержит «</script» — в single/lite не встраивается (используйте сборку site)" % p.relative_to(self.out).as_posix())
                continue
            out.append((rel, kind, t))
        return out

    # --- режим site: оболочка index.html + assets/app.css, app.js, data.js, head.js (+ extra.*, charts.js)
    def assemble_site(self, pairs, title, metas, foot, nav, mbar, layers, js, head_js):
        css = theme_css(self.tokens) + CSS + (CHART_CSS if self.ich else "") + (PROGRESS_CSS if self.pg else "") + (CONCEPT_CSS if self.concept else "") + self.layer_css
        body_data = json.dumps({i: clean_json(o) for i, o in pairs}, ensure_ascii=False, separators=(",", ":"))
        body_data = body_data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        body_data = body_data.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        data_js = "/* product-strategy: данные страницы (реестр, оценки, конкуренты, Гант, Kanban…); JS, а не JSON — fetch() по file:// запрещён */\n" \
                  "window.PS_DATA=" + body_data + ";\n"
        files = {"assets/app.css": css, "assets/app.js": js, "assets/data.js": data_js, "assets/head.js": head_js + "\n"}
        # интерактивные графики: assets/charts-<группа>.js — window.PS_CHARTS[ключ] = {svg, meta}; подключаются динамически при показе
        groups = OrderedDict()
        for c in self.charts:
            if c["key"] in self.chart_page_meta:
                groups.setdefault(self.chart_group(c), []).append(c)
        for g, cs in groups.items():
            body = "".join("(window.PS_CHARTS=window.PS_CHARTS||{})[" + json.dumps(c["key"]) + "]=" + js_literal(
                {"svg": c["svg"], "meta": self.chart_page_meta[c["key"]]}) + ";\n" for c in cs)
            files["assets/charts-%s.js" % g] = ("/* product-strategy: интерактивные графики группы «%s» — SVG и пояснения к элементам "
                                                "(подключается страницей при показе графика) */\n" % g) + body
        for rel, kind, t in self.extra:                    # хуки расширения: build/extra.{css,js}, build/extra/*.{css,js}
            files[rel] = t
        if self.docs:                                      # прочие исследования для поиска — подгружаются при первом поиске
            files["assets/search-docs.js"] = ("/* product-strategy: тексты research/*.md для сквозного поиска (подключается при первом поиске) */\n"
                                              "window.PS_DOCS=" + js_literal(self.docs) + ";\n")
        self.site_files = {k: v.encode("utf-8") for k, v in files.items()}

        def url(rel):
            return rel + "?v=" + hashlib.sha1(self.site_files[rel]).hexdigest()[:10]
        if self.site_csp == "self":
            # Решение по CSP режима site: целевая политика с 'self' (без хешей). Проверка на file:// (smoke_html.mjs, Playwright 1.64):
            #   Chromium 156 — assets/*.js|css|img под 'self' грузятся и выполняются, инлайн-скрипт блокируется (как задумано);
            #   WebKit 27.2 — то же; Firefox — в этой среде не запускается (Playwright firefox-1543: «Could not find profile folder»),
            #   поведение 'self' на file:// там НЕ проверено. Запасной вариант на случай пустой страницы в Firefox:
            #   `build_html.py <OUT> --site-csp none` — без CSP-мета, но с referrer no-referrer и проверкой smoke «внешних запросов 0».
            sec = ('<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\' data:; '
                   'style-src \'self\' \'unsafe-inline\'; script-src \'self\'; base-uri \'none\'; form-action \'none\'">')
        else:
            sec = ""                                       # запасной вариант (--site-csp none): без CSP-мета; внешних запросов нет, проверяет smoke
        head = ('<meta name="referrer" content="no-referrer"><meta name="viewport" content="width=device-width, initial-scale=1">'
                '<meta name="color-scheme" content="light dark">')
        links = '<link rel="stylesheet" href="' + url("assets/app.css") + '">'
        for rel, kind, _ in self.extra:
            if kind == "css":
                links += '<link rel="stylesheet" href="' + url(rel) + '">'
        if "assets/search-docs.js" in self.site_files:
            head += '<meta name="ps-docs" content="' + url("assets/search-docs.js") + '">'
        scripts = '<script src="' + url("assets/data.js") + '"></script>'
        scripts += '<script src="' + url("assets/app.js") + '"></script>'
        for rel, kind, _ in self.extra:
            if kind == "js":
                scripts += '<script src="' + url(rel) + '"></script>'
        page = ("<!doctype html>\n<html lang=\"ru\"><head><meta charset=\"utf-8\">" + sec + head + metas
                + '<link rel="icon" href="data:,"><title>' + esc(title) + "</title>" + links
                + '<script src="' + url("assets/head.js") + '"></script></head><body>'
                '<a class="skip" href="#main">К содержанию</a>' + mbar + '<div class="wrap">' + nav + '<main id="main">'
                + re.sub(r"@@(charts-[\w-]+)@@", lambda m: url("assets/%s.js" % m.group(1)), "".join(self.sections))
                + foot + "</main></div>" + layers + scripts + "</body></html>\n")
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
main{min-width:0;padding:28px 44px 80px;max-width:1280px;width:100%;overflow-wrap:break-word}
/* перенос длинных «слов» (идентификаторы, URL, camelCase) в любом блоке: overflow-wrap наследуется; в таблицах break-word не
   меняет минимальную ширину колонки — слова целые, а длинные токены рвутся по <wbr> (wbr_long) */
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
/* шапки переносятся между словами, как ячейки: длинная шапка не раздувает столбец и не обрезает последний */
.tbl thead th{background:var(--ps-surface-2);font-weight:600;white-space:normal;overflow-wrap:normal;position:sticky;top:0}
.tbl tbody tr:last-child td{border-bottom:0}
.al-c{text-align:center!important}.al-r{text-align:right!important}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.tbl thead th.num{white-space:normal}
/* универсально для ячеек: перенос между словами и по <wbr>; число — только в td.num (num_col), текстовая колонка не nowrap */
.tbl td{overflow-wrap:break-word;word-break:normal}
table.comm td.rules,table.comm th.rules{min-width:220px}table.comm td.aud,table.comm th.aud{min-width:96px}
.tbl table.many{font-size:12.5px}.tbl table.many th,.tbl table.many td{padding:6px 7px;hyphens:auto;-webkit-hyphens:auto}
td.url{word-break:break-all;min-width:180px}
td.stitle{overflow-wrap:anywhere;min-width:140px}
.untitled{font-style:italic;color:var(--ps-muted);overflow-wrap:anywhere}
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
/* Раскрытая строка реестра. Класс detail есть и у <tr class="detail">, и у карточки <div class="detail">: правила
   карточки пишутся только для div.detail, иначе строка становится сеткой, ячейка с colspan выпадает из таблицы в
   анонимную ячейку первого столбца (~40 px) и текст идёт по букве в строку (строки 15–35 тыс. px). */
table.reg tr.detail{display:table-row}
table.reg tr.detail>td{display:table-cell;background:var(--ps-surface-2);padding:6px 0 16px}
/* карточка — в видимой части реестра при его горизонтальной прокрутке (16 столбцов шире экрана): ширина = видимая
   ширина .reg-wrap (100cqw), position:sticky держит её у левого края */
.reg-wrap{container-type:inline-size}
table.reg tr.detail>td>div.detail{position:sticky;left:0;width:100%;max-width:100cqw;padding:0 16px}
tr.flash>td{animation:flash 2s}
@keyframes flash{0%,55%{background:var(--ps-accent-soft)}100%{background:transparent}}
/* Карточка (строка реестра и окно P-id): сбалансированные колонки ≥ 280 px вместо строк сетки, растянутых по самой
   высокой секции; «Суть» и «Концепт дизайна» — во всю ширину. Карточка — контейнер: раскладка зависит от её ширины. */
div.detail{display:block;columns:3 280px;column-gap:28px;font-size:13.5px;container-type:inline-size}
.dsec{min-width:0}
div.detail>.dsec{break-inside:avoid;-webkit-column-break-inside:avoid;page-break-inside:avoid}
div.detail>.dsec:first-child,div.detail>.dsec.wide{column-span:all;-webkit-column-span:all}
.dsec h4{margin:12px 0 4px;font-size:11.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--ps-muted)}
/* padding, не margin: поля обрезаются на разрыве колонок (по-разному в Chrome и Safari) → неровный верх колонок */
div.detail>.dsec>h4{margin-top:0;padding-top:12px}
div.detail>.dsec:first-child>h4{padding-top:8px}
/* длинные списки (KPI, шаги, доказательства) могут продолжаться в следующей колонке между пунктами; заголовок держит
   ≥ 4em своего списка в той же колонке (Safari не соблюдает break-after:avoid в колонках — отсюда распорка ::after) */
div.detail>.dsec:has(> h4 + ul, > h4 + ol){break-inside:auto;-webkit-column-break-inside:auto;page-break-inside:auto}
div.detail>.dsec:has(> h4 + ul, > h4 + ol)>h4{break-inside:avoid;-webkit-column-break-inside:avoid;break-after:avoid}
div.detail>.dsec:has(> h4 + ul, > h4 + ol)>h4::after{content:"";display:block;height:4em;margin-bottom:-4em}
div.detail li{break-inside:avoid;-webkit-column-break-inside:avoid}
div.detail>.dsec>h4+ul>li:first-child,div.detail>.dsec>h4+ol>li:first-child{break-inside:auto;-webkit-column-break-inside:auto}
/* длинные фишки (kano_probs, метки) переносятся внутри колонки, а не вылезают в соседнюю */
div.detail .tag{white-space:normal;max-width:100%}
/* свёрнутая секция (телефон): строка-заголовок, по нажатию раскрывается */
div.detail>details.dsec{margin:0;border-top:1px solid var(--ps-border);break-inside:avoid}
div.detail>details.dsec>summary{font-size:11.5px;text-transform:uppercase;letter-spacing:.07em;padding:10px 0 8px;font-weight:600}
div.detail>details.dsec[open]>summary{padding-bottom:4px}
.dsec ul,.dsec ol{margin:4px 0;padding-left:20px}.dsec li{margin:3px 0}
/* столбец значения — не уже 120 px: подписи переносятся, значение не идёт «по букве» */
dl.kv{display:grid;grid-template-columns:minmax(96px,max-content) minmax(120px,1fr);gap:4px 12px;margin:4px 0}
dl.kv dt{color:var(--ps-muted)}dl.kv dd{margin:0;min-width:0;overflow-wrap:anywhere}
/* узкая карточка (телефон): в «Сути» подпись над текстом — длинным текстам вся ширина */
@container (max-width:560px){
  div.detail>.dsec:first-child dl.kv{grid-template-columns:minmax(0,1fr);row-gap:0}
  div.detail>.dsec:first-child dl.kv dt{margin-top:6px;font-size:12.5px}
}
@supports not (container-type:inline-size){@media (max-width:560px){
  div.detail>.dsec:first-child dl.kv{grid-template-columns:minmax(0,1fr);row-gap:0}
}}
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
/* padding-right: ромб вехи в последнем месяце (повёрнутый квадрат ~20 px) не вылезает за правый край диаграммы */
.ghead,.grow{display:grid;grid-template-columns:280px minmax(0,1fr);padding-right:12px}
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
/* контраст ≥ 4,5:1 в обеих темах (было 3,4 в тёмной) */
.st-new{color:var(--ps-ok,#166534);border-color:var(--ps-ok,#166534)}
.cgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,460px),1fr));gap:14px;margin-top:12px}
.ccard{background:var(--ps-surface);border:1px solid var(--ps-border);border-radius:var(--ps-radius);padding:12px 14px;display:grid;grid-template-columns:170px minmax(0,1fr);gap:12px;font-size:13px;min-width:0}
.ccard.noimg{grid-template-columns:minmax(0,1fr)}
.ccard figure{margin:0}
.ccard figure img{width:100%;aspect-ratio:16/10;object-fit:cover;object-position:top}
.ccard .noshot{border:1px dashed var(--ps-border);border-radius:8px;aspect-ratio:16/10;display:flex;align-items:center;justify-content:center;text-align:center;color:var(--ps-muted);font-size:11.5px;padding:6px}
.ccard h4{margin:0 0 2px;font-size:15px}
.ccard h4 .tag{white-space:normal;max-width:100%}
.ccard .cverdict{margin:4px 0}.ccard .cverdict summary{font-size:12.5px}.ccard .cverdict p,.ccard p.cverdict{margin:4px 0}
.ccard .cmeta{color:var(--ps-muted);font-size:12px;margin-bottom:4px}
.ccard .lblh{font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--ps-muted);margin-top:6px}
.ccard ul{margin:2px 0;padding-left:18px}
.ccard .them li::marker{color:#b42318}.ccard .us li::marker{color:#15803d}.ccard .best li::marker{color:#a15c07}
.cmatrix{overflow:auto;max-height:70vh;border:1px solid var(--ps-border);border-radius:10px;background:var(--ps-surface)}
table.cm{border-collapse:separate;border-spacing:0;font-size:12.5px;width:100%}
table.cm th,table.cm td{padding:5px 8px;border-bottom:1px solid var(--ps-border);text-align:center;white-space:nowrap}
table.cm thead th{position:sticky;top:0;background:var(--ps-surface-2);z-index:2;white-space:normal;overflow-wrap:normal;word-break:normal;min-width:72px;vertical-align:bottom;line-height:1.3}
table.cm th[scope=row]{position:sticky;left:0;background:var(--ps-surface);text-align:left;z-index:1;max-width:220px;overflow:hidden;text-overflow:ellipsis}
table.cm thead th:first-child{left:0;z-index:3}
table.cm tr.self th,table.cm tr.self td{background:var(--ps-accent-soft);font-weight:600}
table.cm td.y{color:var(--ps-ok,#166534);font-weight:700}table.cm td.n{color:var(--ps-muted)}table.cm td.u{color:var(--ps-muted)}
table.cm tr.self td.n,table.cm tr.self td.u{color:var(--ps-text)}
table.cm td.gap{outline:2px solid #b42318;outline-offset:-3px}
table.cm tfoot th,table.cm tfoot td,table.cm tfoot th[scope=row]{background:var(--ps-surface-2);font-weight:600}
.st-ok,.st-bad,.st-unk,.ok{display:inline-block;font-size:12px;padding:0 7px;border-radius:999px;white-space:nowrap}
/* «✓ проверено», «доступны»: #15803d на своей зелёной подложке давал 3,9–4,1 — темнее до ≥ 4,5:1 */
.st-ok,.ok{background:rgba(21,128,61,.14);color:var(--ps-ok,#166534)}.st-bad{background:rgba(180,35,24,.14);color:var(--ps-bad,#9f1f14)}.st-unk{background:var(--ps-surface-2);color:var(--ps-muted)}
/* цвета --ps-ok/--ps-bad считает theme_vars под фон каждой темы (status_colors) — без жёстких #4ade80 на чужом фоне */
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
  /* телефон: диаграмма прокручивается внутри своей рамки; ширина — чтобы подписи месяцев («окт’26») не обрезались,
     столбец задач закреплён слева при прокрутке */
  .ghead,.grow{grid-template-columns:150px minmax(0,1fr)}
  .gin{min-width:820px}
  .gscale span{font-size:10.5px;padding:8px 2px 0}
  .glabel{position:sticky;left:0;z-index:1;background:var(--ps-surface);border-right:1px solid var(--ps-border)}
  .ghead .gl{position:sticky;left:0;z-index:2;background:var(--ps-surface-2);border-right:1px solid var(--ps-border)}
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
@media (max-width:699px){
  /* телефон: длинные теги и статус-метки (вердикт, «без названия», статусы) переносятся, а не раздвигают страницу */
  main .tag,main .st-ok,main .st-bad,main .st-unk,main .ok{white-space:normal;max-width:100%;overflow-wrap:anywhere}
}
"""

# Стили режима «Отслеживание» — добавляются в страницу, только если есть data/progress.json (иначе страница прежняя).
# Чипы статусов — белый текст на насыщенном фоне (≥ 5:1 в любой теме) + значок; подписи Ганта — текст темы на подложке.
CONCEPT_CSS = r"""
/* режим идеи: светофор и шкалы предпроверки жизнеспособности */
.vverdict{display:inline-block;font-weight:700;font-size:13px;padding:1px 10px;border-radius:999px;color:#fff;background:#5b6170;margin-right:4px}
.vv-green{background:#15803d}.vv-yellow{background:#a15c07}.vv-red{background:#b42318}
.vbar{display:inline-block;width:90px;height:8px;border-radius:4px;background:var(--ps-surface-2);vertical-align:middle;overflow:hidden;border:1px solid var(--ps-border)}
.vbar i{display:block;height:100%;background:#5b6170}
.vbar.vb-ok i{background:#15803d}.vbar.vb-mid i{background:#a15c07}.vbar.vb-bad i{background:#b42318}
"""

PROGRESS_CSS = r"""
.pst,.gst{display:inline-flex;align-items:center;gap:3px;font-size:11.5px;font-weight:600;line-height:1.55;padding:0 7px;border-radius:999px;color:#fff;background:#5b6170;white-space:nowrap;vertical-align:baseline}
.pst i,.gst i{font-style:normal;font-weight:700}
.pst-done,.gst-done,.pgs.s-done,.pgsw.s-done{background:#15803d}
.pst-partial,.gst-partial,.pgs.s-partial,.pgsw.s-partial{background:#a15c07}
.pst-in_progress,.gst-on_track,.pgs.s-in_progress,.pgsw.s-in_progress{background:#1d4ed8}
.pst-planned{background:#6d28d9}.pst-not_started,.gst-upcoming{background:#5b6170}.pst-blocked,.gst-behind{background:#b42318}
.pst-dropped{background:#44403c}.pst-obsolete{background:#5f6b7a}.pst-unknown{background:#86198f}
.pst-dropped{text-decoration:line-through}
.pg-kpis .pgk{display:block;color:var(--ps-text);text-decoration:none}
.pg-kpis .pgk[data-date] .n{font-size:22px;line-height:1.2}
.pg-kpis .pgk:hover,.pg-kpis .pgk:focus-visible{border-color:var(--ps-accent);box-shadow:0 0 0 3px var(--ps-accent-soft)}
.pg-legend{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;margin:6px 0 4px}
.pst-go{color:var(--ps-text);text-decoration:none;white-space:nowrap;font-size:13px}
.pst-go:hover b{text-decoration:underline}
.pgrow{display:grid;grid-template-columns:minmax(70px,34%) minmax(0,1fr) max-content;gap:8px;align-items:center;font-size:13px;margin:4px 0}
.pgl{overflow-wrap:anywhere}
.pgt{display:flex;height:12px;background:var(--ps-surface-2);border:1px solid var(--ps-border);border-radius:6px;overflow:hidden}
.pgs{display:block;height:100%}
.pgn{font-variant-numeric:tabular-nums;white-space:nowrap}
.pgsw{display:inline-block;width:11px;height:11px;border-radius:3px;vertical-align:-1px;margin:0 3px 0 8px;background:var(--ps-surface-2);border:1px solid var(--ps-border)}
.pgsw:first-child{margin-left:0}
.pgc-wrap{background:var(--ps-surface);border:1px solid var(--ps-border);border-radius:var(--ps-radius);padding:10px 12px;max-width:760px}
.pgc{display:block;width:100%;height:auto}
.pgc-grid{stroke:var(--ps-border);stroke-width:1}
.pgc-area{fill:var(--ps-accent-soft)}
.pgc-line{fill:none;stroke:var(--ps-accent);stroke-width:3;stroke-linejoin:round;stroke-linecap:round}
.pgc-dot{fill:var(--ps-surface);stroke:var(--ps-accent);stroke-width:3}
.pgc-axis{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;font-size:12px;color:var(--ps-muted);margin-top:4px}
.pg-list{padding-left:22px}.pg-list li{margin:6px 0;overflow-wrap:anywhere}
.pg-sub{font-size:12.5px;color:var(--ps-muted);margin-top:2px}
.pg-ok{color:var(--ps-ok,#166534);font-weight:600}.pg-warn{color:var(--ps-bad,#9f1f14);font-weight:600}
.pg-was{text-decoration:line-through;color:var(--ps-muted)}.pg-now{font-weight:600}
.pg-pp{white-space:nowrap;display:inline-block;margin:1px 6px 1px 0}
.pg-rev .pg-rt{font-weight:600;color:var(--ps-text)}
a.gh{font-weight:600}
.pg-quick{margin-top:-2px}
.pg-quick button[aria-pressed=true]{background:var(--ps-accent-soft);border-color:var(--ps-accent);color:var(--ps-text);font-weight:600}
.pg-glegend{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:4px 0 8px}
/* Гант по фактам: полоса — светлая подложка цвета статуса + заливка по доле выполненного; подпись со значком на подложке */
.gin.pgon{position:relative;--glw:280px}
.gin.pgon .ghead{z-index:3}
.gin.pgon .gscale{height:50px}
.gin.pgon .gtrack{min-height:34px}
.gbar.gs-done,.gbar.gs-partial,.gbar.gs-behind,.gbar.gs-on_track,.gbar.gs-upcoming{top:10px;height:14px;opacity:1;overflow:hidden;border:1.5px solid}
.gbar.gs-done{border-color:#15803d;background:rgba(21,128,61,.18)}.gbar.gs-done .gfill{background:#15803d}
.gbar.gs-partial{border-color:#a15c07;background:rgba(161,92,7,.18)}.gbar.gs-partial .gfill{background:#a15c07}
.gbar.gs-behind{border-color:#b42318;background:rgba(180,35,24,.16)}.gbar.gs-behind .gfill{background:#b42318}
.gbar.gs-on_track{border-color:#1d4ed8;background:rgba(29,78,216,.16)}.gbar.gs-on_track .gfill{background:#1d4ed8}
.gbar.gs-upcoming{border-color:#5b6170;border-style:dashed;background:rgba(91,97,112,.14)}.gbar.gs-upcoming .gfill{background:#5b6170}
.gfill{display:block;height:100%}
.gms.gs-done{background:#15803d}.gms.gs-partial{background:#a15c07}.gms.gs-behind{background:#b42318}.gms.gs-on_track{background:#1d4ed8}.gms.gs-upcoming{background:#5b6170}
.gpl{position:absolute;top:7px;font-size:11px;font-weight:600;line-height:18px;padding:0 6px;border-radius:5px;white-space:nowrap;color:var(--ps-text);background:var(--ps-surface);border:1px solid var(--ps-border);pointer-events:none;z-index:3}
.gpl-behind{border-color:#b42318}.gpl-done{border-color:#15803d}
.gtoday{position:absolute;top:0;bottom:0;width:0;left:calc(var(--glw) + (100% - var(--glw) - 12px) * var(--x));border-left:2px solid #b42318;z-index:2;pointer-events:none}
.gtd{position:absolute;bottom:3px;z-index:2;font-size:10.5px;font-weight:700;line-height:16px;padding:0 5px;border-radius:4px;color:#fff;background:#b42318;white-space:nowrap;pointer-events:none}
/* Kanban: переключатель «Как в плане / По фактам» — радиокнопки + CSS */
.kbv{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.kbv>.kanban{flex:1 1 100%;min-width:0;margin-top:6px}
.kbv-r{position:absolute;opacity:0;width:1px;height:1px;margin:0;pointer-events:none}
.kbv-r+label{display:inline-block;font-size:13px;padding:5px 12px;border:1px solid var(--ps-border);border-radius:8px;background:var(--ps-surface);color:var(--ps-text);cursor:pointer}
.kbv-r:checked+label{background:var(--ps-accent-soft);border-color:var(--ps-accent);font-weight:600}
.kbv-r:focus-visible+label{outline:2px solid var(--ps-accent);outline-offset:2px}
#kbv-plan:checked~.kb-facts,#kbv-facts:checked~.kb-plan{display:none}
.kbv-n{font-weight:400;color:var(--ps-muted)}
.kb-off{flex:1 1 100%;margin:4px 0 0;color:var(--ps-text)}
#kbv-plan:checked~.kb-off{display:none}
.pg-sus{border-color:#b42318;color:var(--ps-bad,#9f1f14);font-weight:600}
.kcard.moved{border-left:3px solid var(--ps-accent)}
.kmoved{font-size:11.5px;margin-top:4px;color:var(--ps-text);overflow-wrap:anywhere}
.kcard .pst{margin-top:2px}
.dsec.pg .pg-items{list-style:none;padding-left:0}.dsec.pg .pg-items li{margin:4px 0;overflow-wrap:anywhere}
.dsec.pg code{font-size:12px}
@media (max-width:900px){
  .gin.pgon{--glw:150px}
  .gin.pgon .glabel{z-index:5}
  .pgrow{grid-template-columns:minmax(64px,30%) minmax(0,1fr) max-content}
}
@media print{.kb-facts{display:grid!important}.kbv-r,.kbv-r+label{display:none}.gtoday,.gtd{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
"""

# Интерактивные графики (references/interactive-site.md, п. 2.3): SVG на белой подложке в обеих темах (цвета графиков — из
# charts.py), поэтому контур выбранного элемента — тёмно-синий 3 px с белым ореолом (контраст с подложкой 10:1, с тёмной
# заливкой элемента отделяет ореол); толщина в экранных пикселях (vector-effect). Панель — цвета темы.
CHART_CSS = r"""
figure.ps-ichart{margin:16px 0;min-width:0}
.gallery figure.ps-ichart{margin:0}
.ps-svg{border:1px solid var(--ps-border);border-radius:8px;background:#fff;overflow:hidden;line-height:0}
.ps-svg svg{display:block;width:100%;height:auto}
.ps-svg.ps-wait{min-height:180px;display:flex;align-items:center;justify-content:center;line-height:1.4}
.ps-ph{margin:0;color:#4b5260;font-size:13px}
.ps-svg .ps-el,.ps-svg [data-ps-ref]{cursor:pointer}
.ps-svg .ps-el:focus,.ps-svg .ps-el:focus-visible{outline:none}
svg.ps-hl-on [data-ps-group]:not(.ps-hl){opacity:.18}
.ps-ovl rect{fill:none;vector-effect:non-scaling-stroke}
.ps-sel-halo{stroke:#fff;stroke-width:8}
.ps-sel-line{stroke:#0b3d91;stroke-width:3.5}
.ps-foc-halo{stroke:#fff;stroke-width:6}
.ps-foc-line{stroke:#0b3d91;stroke-width:2;stroke-dasharray:6 3}
.ps-acts{white-space:nowrap}
.ps-howto{margin:8px 0 0;padding:10px 14px;border:1px solid var(--ps-border);border-radius:8px;background:var(--ps-surface);font-size:13.5px;line-height:1.5}
.ps-howto[hidden]{display:none}
.ps-howto p{margin:4px 0}
.ps-legend{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:2px 12px;margin:8px 0}
.ps-legend dt{font-weight:600}.ps-legend dd{margin:0}
.ps-flash{animation:psflash 2.2s}
@keyframes psflash{0%,60%{box-shadow:0 0 0 4px var(--ps-accent)}100%{box-shadow:0 0 0 0 transparent}}
.cpanel{position:fixed;top:0;right:0;bottom:0;width:400px;max-width:92vw;z-index:700;background:var(--ps-surface);color:var(--ps-text);
  border-left:1px solid var(--ps-border);box-shadow:-8px 0 24px rgba(0,0,0,.18);display:flex;flex-direction:column}
.cpanel[hidden]{display:none}
.cp-head{display:flex;gap:10px;align-items:flex-start;padding:14px 16px 10px;border-bottom:1px solid var(--ps-border)}
.cp-hg{flex:1;min-width:0}
.cp-head h3{margin:2px 0 6px;font-size:16.5px;line-height:1.3;overflow-wrap:anywhere}
.cp-chart{line-height:1.3;overflow-wrap:anywhere}
.cp-kind{display:inline-block;font-size:11.5px;font-weight:600;line-height:1.6;padding:0 8px;border-radius:999px;background:var(--ps-surface-2);color:var(--ps-text);border:1px solid var(--ps-border)}
.cp-kind:empty{display:none}
.cp-x{flex:none}
.cp-body{flex:1;min-height:0;overflow:auto;padding:4px 16px 12px;font-size:13.5px;line-height:1.5;overscroll-behavior:contain}
.cp-body h4{margin:12px 0 4px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--ps-muted)}
.cp-body p{margin:4px 0}
.cp-body ul{margin:4px 0;padding-left:18px}
.cp-body li{margin:3px 0}
.cp-mx{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,auto);gap:3px 12px;margin:4px 0}
.cp-mx dt{color:var(--ps-muted)}.cp-mx dd{margin:0;text-align:right;font-variant-numeric:tabular-nums}
.cp-links a{overflow-wrap:anywhere}
.cp-nav{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 16px;border-top:1px solid var(--ps-border)}
.ps-tip{position:fixed;z-index:720;max-width:300px;padding:5px 9px;border-radius:6px;background:#1d2127;color:#fff;font-size:12.5px;line-height:1.35;pointer-events:none;box-shadow:0 2px 8px rgba(0,0,0,.25)}
.ps-tip[hidden]{display:none}
.ps-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap}
@media (min-width:1100px){body.cp-open{padding-right:400px}}
@media (max-width:699px){
  .cpanel{top:auto;left:0;width:auto;max-width:none;max-height:62vh;border-left:0;border-top:1px solid var(--ps-border);border-radius:14px 14px 0 0;box-shadow:0 -8px 24px rgba(0,0,0,.22)}
  .ps-svg{overflow-x:auto;overscroll-behavior-x:contain}
  .ps-svg svg{min-width:560px}
}
#lbpids{font-size:12.5px;color:#ccc}#lbpids a{color:#a8c7ff}
@media print{#cp,.ps-tip,.ps-ovl,.ps-acts{display:none!important}.ps-howto{display:block!important}body.cp-open{padding-right:0}.ps-svg{overflow:visible}.ps-svg svg{min-width:0}}
"""

# ---------------------------------------------------------------- JS
HEAD_JS ="try{var t=localStorage.getItem('ps-theme');if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t)}catch(e){}"

JS = r"""
(function () {
'use strict';
var $ = function (s, r) { return (r || document).querySelector(s); };
var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
function J(id) { var D = window.PS_DATA; if (D && Object.prototype.hasOwnProperty.call(D, id)) return D[id]; var el = document.getElementById(id); if (!el) return null; try { return JSON.parse(el.textContent); } catch (e) { console.error('JSON ' + id + ': ' + e); return null; } }
function safe(name, fn) { try { fn(); } catch (e) { console.error('[' + name + '] ' + (e && e.stack || e)); } }
var IMG = J('d-img') || {}, META = J('d-meta') || {}, REG = J('d-registry') || [], METRICS = J('d-metrics') || [];
var REFS = J('d-refs') || {}, GANTT = J('d-gantt') || [], KAN = J('d-kanban') || [], NODES = J('d-flows') || {}, COMP = J('d-comp') || [];
var L = META.labels || {}, DIMS = META.dims || {};
var BYID = {}; REG.forEach(function (r) { BYID[r.id] = r; });
var MET = {}; METRICS.forEach(function (m) { MET[m.k] = m; });
/* режим «Отслеживание» (d-progress есть только при data/progress.json): статус — значок + текст */
var PG = J('d-progress'), PGL = (PG && PG.labels) || {}, PGI = (PG && PG.icons) || {}, PGO = (PG && PG.order) || {};
function stChip(st, labels, icons, pre) { if (!st) return ''; labels = labels || PGL; icons = icons || PGI; pre = pre || 'pst'; return '<span class="' + pre + ' ' + pre + '-' + esc(String(st).replace(/[^\w-]/g, '-')) + '"><i aria-hidden="true">' + esc(icons[st] || '•') + '</i> ' + esc(labels[st] || st) + '</span>'; }
/* ссылки на GitHub — только https://github.com/…, иначе текст */
function ghA(u, text) { u = String(u || ''); return /^https:\/\/github\.com\/[^\s"'<>]+$/.test(u) ? '<a class="gh" href="' + esc(u) + '" target="_blank" rel="noopener noreferrer">' + esc(text) + '</a>' : esc(text); }
function pgLab(g, v) { return (PG && PG[g] && PG[g][v]) || (v == null ? '' : String(v)); }
function pgDone(r) { return PG && r && (PG.closed || []).indexOf(r.status) >= 0; }
function pgHtml(r) {
  var g = r.pg; if (!g) return '';
  var conf = g.confidence != null ? Math.round(g.confidence * 100) + ' %' : '';
  var blk = (g.blocked_by_open || []).map(function (d) { return BYID[d] ? pidLink(d) + ' ' + stChip(BYID[d].status) : esc(d); }).join(', ');
  var head = kv([['Статус', stChip(g.status) + (g.suggested ? ' <span class="muted">движок предлагал: ' + esc(pgLab('labels', g.suggested)) + '</span>' : '')], ['Уверенность', esc(conf)],
    ['Источник', esc(pgLab('source', g.source))], ['С какой даты', esc(g.since)], ['Ждёт', blk], ['Отстаёт', (g.behind || []).length ? 'задачи плана: ' + esc(g.behind.join(', ')) : ''], ['Заметка', esc(g.note)]]);
  function how(m, sc) { return m ? ' <span class="muted">(' + esc(pgLab('match', m)) + (sc != null && m === 'similar' ? ' ' + esc(fmt(sc)) : '') + ')</span>' : ''; }
  function sus(x) { return x.sus ? ' <span class="tag pg-sus" title="Текст похож на инструкцию — это данные, проверьте вручную">⚠ проверить</span>' : ''; }
  var iss = (g.issues || []).map(function (x) { return '<li>' + ghA(x.url, x.n ? (x.kind === 'pr' ? 'PR #' : '#') + x.n : 'issue') + sus(x) + ' ' + tag(pgLab('state', x.state) + (x.reason && x.reason !== 'null' ? ' · ' + pgLab('reason', x.reason) : '')) + ' ' + esc(x.title) + how(x.match, x.score) + (x.closed_at ? ' <span class="muted">закрыт ' + esc(x.closed_at) + '</span>' : '') + '</li>'; }).join('');
  var prs = (g.prs || []).map(function (x) { return '<li>' + ghA(x.url, x.n ? 'PR #' + x.n : 'PR') + sus(x) + ' ' + tag(pgLab('state', x.state)) + ' ' + esc(x.title) + how(x.match) + (x.merged_at ? ' <span class="muted">влит ' + esc(x.merged_at) + '</span>' : '') + '</li>'; }).join('');
  var com = (g.commits || []).map(function (x) { return '<li>' + ghA(x.url, x.sha || 'commit') + ' <span class="muted">' + esc(x.date) + '</span> ' + esc(x.subject) + how(x.match) + '</li>'; }).join('');
  var code = (g.code || []).map(function (x) { return '<li><code>' + esc(x.file) + '</code>' + (x.kind ? ' ' + tag(pgLab('code', x.kind)) : '') + (x.evidence ? ' — ' + esc(x.evidence) : '') + '</li>'; }).join('');
  var sd = (g.scan_diff || []).map(function (x) { return '<li><code>' + esc(x) + '</code></li>'; }).join('');
  var men = (g.mentions || []).map(function (x) { return '<li>' + ghA(x.url, x.n ? (x.kind === 'pr' ? 'PR #' : '#') + x.n : 'issue') + ' ' + tag(pgLab('state', x.state)) + ' ' + esc(x.title) + '</li>'; }).join('');
  return head + (iss ? '<h4>Issues</h4><ul class="pg-items">' + iss + '</ul>' : '') + (prs ? '<h4>Pull requests</h4><ul class="pg-items">' + prs + '</ul>' : '')
    + (com ? '<h4>Коммиты</h4><ul class="pg-items">' + com + '</ul>' : '') + (code ? '<h4>Следы в коде</h4><ul class="pg-items">' + code + '</ul>' : '')
    + (sd ? '<h4>Изменения сканирования</h4><ul class="pg-items">' + sd + '</ul>' : '')
    + (men ? '<h4>Упоминается в эпиках и списках</h4><ul class="pg-items">' + men + '</ul>' : '') + (!iss && !prs && !com && !code ? '<p class="muted small">Связанных issues, PR и коммитов не найдено.</p>' : '');
}
function pgList(ids) { return (ids || []).map(function (id) { var r = BYID[id]; return '<li>' + pidLink(id) + (r ? ' ' + esc(r.title) + ' ' + stChip(r.status) : ' <span class="muted">(нет в реестре)</span>') + '</li>'; }).join(''); }
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
/* ссылки из данных (доказательства, конкуренты, источники): только валидный http(s) или mailto:, иначе — текст */
function dataUrl(u) {
  u = String(u == null ? '' : u).trim(); if (/^mailto:[^\s@]+@[^\s@]+$/i.test(u)) return u;
  if (!/^https?:\/\/\S+$/i.test(u)) return ''; var h = '';
  try { h = new URL(u).hostname.replace(/^\[|\]$/g, '').replace(/\.$/, ''); } catch (e) { return ''; }
  if (h === 'localhost' || /^(?:[\p{L}\p{N}_-]+\.)+[\p{L}\p{N}_-]{2,}$/u.test(h) && h.charAt(0) !== '-' || /^[\d.]+$/.test(h) && h.split('.').length === 4 || /^[0-9a-f:]+$/i.test(h) && h.indexOf(':') >= 0) return u;
  return '';
}
function link(u, text) { var s = dataUrl(u); var t = esc(text == null || text === '' ? u : text); return s ? '<a href="' + esc(s) + '" target="_blank" rel="noopener noreferrer">' + t + '</a>' : t; }
function lab(g, v) { return (L[g] && L[g][v]) || (v == null ? '' : String(v)); }
function txt(v) { if (v == null) return ''; if (typeof v === 'boolean') return v ? 'да' : 'нет'; if (typeof v === 'number') return fmt(v); if (Array.isArray(v)) return v.map(txt).join('; '); if (typeof v === 'object') { if ('min' in v && 'max' in v) return money(v); if ('value' in v) return txt(v.value) + (v.label ? ' [' + v.label + ']' : ''); return Object.keys(v).map(function (k) { return k + ': ' + txt(v[k]); }).join('; '); } return String(v); }
function fmt(v) { if (v == null || v === '') return ''; if (typeof v !== 'number') return String(v); if (!isFinite(v)) return '—'; if (Number.isInteger(v)) return v.toLocaleString('ru-RU'); return v.toLocaleString('ru-RU', { maximumFractionDigits: Math.abs(v) < 10 ? 2 : 1 }); }
function money(c) { if (!c || typeof c !== 'object') return txt(c); var lo = c.min, hi = c.max, s = ''; if (lo == null && hi == null) s = ''; else if (lo === hi || hi == null) s = fmt(lo); else if (lo == null) s = 'до ' + fmt(hi); else s = fmt(lo) + '–' + fmt(hi); s = (s + ' ' + (c.currency || '')).trim(); if (c.note) s += ' (' + c.note + ')'; return s; }
function norm(s) { return String(s || '').toLowerCase().replace(/ё/g, 'е').trim(); }
/* поиск в реестре, конкурентах и таблицах: несколько слов — все в любом порядке, «фраза в кавычках» — целиком; регистр и е/ё не важны */
function qWords(q) { var out = [], m, re = /"([^"]+)"|«([^»]+)»|(\S+)/g; q = norm(q); while ((m = re.exec(q))) { var w = (m[1] || m[2] || m[3] || '').replace(/\s+/g, ' ').trim(); if (w) out.push(w); } return out; }
function hayHas(h, ws) { for (var i = 0; i < ws.length; i++) if (h.indexOf(ws[i]) < 0) return false; return true; }
function badge(kind, v) { if (!v) return ''; var t = kind === 'q' ? lab('quadrant', v) : v; return '<span class="b b-' + esc(String(v).replace(/[^\w-]/g, '-')) + '">' + esc(t) + '</span>'; }
function tag(t, cls) { return t === '' || t == null ? '' : '<span class="tag' + (cls ? ' ' + cls : '') + '">' + esc(t) + '</span>'; }
function pidLink(id) { var r = BYID[id]; if (!r) return esc(id); return '<a class="pid" href="#p=' + esc(id) + '" data-pid="' + esc(id) + '" title="' + esc(id + ' — ' + r.title) + '">' + esc(id) + '</a>'; }
function plist(ids) { return (ids || []).map(function (id) { var r = BYID[id]; return '<li>' + pidLink(id) + (r ? ' ' + esc(r.title) + ' ' + badge('p', r.priority) + ' ' + badge('q', r.quadrant) : ' <span class="muted">(нет в реестре)</span>') + '</li>'; }).join(''); }
/* --lite: превью — миниатюра из THUMB (data:), полная картинка (assets/…) подгружается, когда превью видно и крупнее миниатюры */
var THUMB = J('d-thumb') || {}, ALIAS = J('d-alias') || {};
Object.keys(ALIAS).forEach(function (k) { var a = ALIAS[k]; if (IMG[a] != null) IMG[k] = IMG[a]; if (THUMB[a]) THUMB[k] = THUMB[a]; });
function upgradeImg(im) { var k = im.getAttribute('data-img'), t = THUMB[k]; if (!t || im.getAttribute('data-full') !== '0') return; var need = im.getBoundingClientRect().width * (window.devicePixelRatio || 1); if (need > t[1] + 1 || !need) { im.src = IMG[k]; im.setAttribute('data-full', '1'); } }
var thumbIO = ('IntersectionObserver' in window) ? new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) { thumbIO.unobserve(e.target); upgradeImg(e.target); } }); }, { rootMargin: '300px' }) : null;
function fillImgs(root) { $$('img[data-img]', root).forEach(function (im) { if (im.getAttribute('src')) return; var k = im.getAttribute('data-img'), u = IMG[k], t = THUMB[k];
  if (t) { im.src = t[0]; im.setAttribute('data-full', '0'); if (thumbIO) thumbIO.observe(im); else if (u) { im.src = u; im.setAttribute('data-full', '1'); } } else if (u) im.src = u; }); }
var PIDRE = /(^|[^\p{L}\p{N}_-])(P\d{3})(?![\p{L}\p{N}_-])/gu;   /* без lookbehind: старые Safari */
var SKIP = { A: 1, SCRIPT: 1, STYLE: 1, TEXTAREA: 1, SELECT: 1, OPTION: 1, BUTTON: 1, TITLE: 1, INPUT: 1 };
function linkifyEl(root) {
  if (root && window.PS && window.PS.ents) safe('ents', function () { window.PS.ents(root); });   /* G-id, «раздел N», термины… — ps-ents.js */
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
function openLayer(el) { var i = stack.indexOf(el); if (i >= 0) stack.splice(i, 1); else el._opener = document.activeElement; stack.push(el); el.classList.add('open'); el.setAttribute('aria-hidden', 'false'); restack(); var f = el.querySelector('[data-autofocus]'); if (f) { try { f.focus({ preventScroll: true }); } catch (e) {} } emitPS('layer:open', el.id); }
function closeLayer(el) {
  el = el || stack[stack.length - 1]; if (!el) return; var i = stack.indexOf(el); if (i < 0) return;
  stack.splice(i, 1); el.classList.remove('open'); el.setAttribute('aria-hidden', 'true');
  if (el === pm) { pm.removeAttribute('data-id'); pmHist.length = 0; }
  if (el === lb) { LB.cur = null; lbimg.removeAttribute('src'); }
  restack(); var o = el._opener; el._opener = null; if (o && o.focus && document.contains(o)) { try { o.focus({ preventScroll: true }); } catch (e) {} }
  emitPS('layer:close', el.id);
}
function closeAll() { while (stack.length) closeLayer(); }
function topLayer() { return stack[stack.length - 1] || null; }

/* ---------- карточка предложения ---------- */
var pmHist = [];
/* телефон и планшет (≤ 900 px): карточка свёрнута по умолчанию — открыта только «Суть» (и «Выполнение»), остальное (KPI, шаги, затраты,
   оценки, доказательства, связи, концепт) — строки «Подробнее» с числом пунктов (<details>); иначе в одну колонку карточка — 2,5–4,5 тыс. px
   (FB-039, SM 6.4) */
var NARROW = window.matchMedia ? window.matchMedia('(max-width: 900px)') : { matches: false };
function sec(title, h, cls, fold, n) {
  if (!h) return '';
  if (fold && NARROW.matches) return '<details class="dsec fold' + (cls ? ' ' + cls : '') + '"><summary>' + title + (n ? ' <span class="dsec-n">· ' + n + '</span>' : '') + '</summary>' + h + '</details>';
  return '<section class="dsec' + (cls ? ' ' + cls : '') + '"><h4>' + title + '</h4>' + h + '</section>';
}
function kv(pairs) { var h = pairs.filter(function (p) { return p[1] !== '' && p[1] != null; }).map(function (p) { return '<dt>' + p[0] + '</dt><dd>' + p[1] + '</dd>'; }).join(''); return h ? '<dl class="kv">' + h + '</dl>' : ''; }
function asObj(x, key) { if (x && typeof x === 'object') return x; var o = {}; o[key] = x; return o; }
function conceptsHtml(r, inModal) {
  if (!r.concepts || !r.concepts.length) return '';
  /* много концептов (10–20 макетов на предложение) — первые три видны, остальные под «Ещё» (иначе карточка 3 тыс. px и на 1440) */
  if (r.concepts.length > 3) { var head = { concepts: r.concepts.slice(0, 3) }, rest = { concepts: r.concepts.slice(3) };
    return conceptsHtml(head, inModal) + '<details class="more-concepts"><summary>Ещё концептов: ' + rest.concepts.length + '</summary>' + conceptsHtml(rest, inModal) + '</details>'; }
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
  /* один блок TypeSafe: score.py и typesafe-jev.json сведены сборщиком (совпадающее — один раз, расхождения — в поле) */
  var ts = '', tb = r.ts_block;
  if (tb && tb.items && typeof tb.items === 'object') { var th = Object.keys(tb.items).map(function (k) { return '<span class="tag">' + esc(k) + ': <b>' + esc(txt(tb.items[k])) + '</b></span>'; }).join(' '); if (th) ts = '<p class="tsb"><span class="muted">' + esc(tb.title) + ':</span> ' + th + '</p>'; }
  var deps = (r.dependencies || []).map(function (d) { return BYID[d] ? pidLink(d) : esc(d) + ' <span class="muted">(нет в реестре)</span>'; }).join(', ');
  var rdeps = (r.rdeps || []).map(pidLink).join(', ');
  var mn = r.mentions || {}, ment = [];
  (mn.gantt || []).forEach(function (g) { ment.push('<li>Гант: <a href="#gantt" data-g-open="' + g.i + '">' + esc(g.t) + '</a></li>'); });
  (mn.kanban || []).forEach(function (k) { ment.push('<li>Kanban: <a href="#kanban" data-k-open="' + k.i + '">колонка «' + esc(k.t) + '»</a></li>'); });
  (mn.flows || []).forEach(function (f) { ment.push('<li>Схема «' + esc(f.f) + '»: <a href="#flows" data-node-open="' + esc(f.id) + '">' + esc(f.t) + '</a></li>'); });
  var rel = kv([['Зависит от', deps], ['От него зависят', rdeps], ['Источник', esc(r.source_group) + ((r.merged_from || []).length ? ' · объединено из ' + esc(r.merged_from.join(', ')) : '')]]);
  var nk = (r.effect_kpi || []).length, ns = (r.steps || []).length, ne = (r.evidence || []).length;
  return '<div class="detail">' + sec('Суть', essence) + (r.pg ? sec('Выполнение', pgHtml(r), 'wide pg') : '') + sec('Эффект и KPI', kpi ? '<ul>' + kpi + '</ul>' : '', '', 1, nk) + sec('Шаги', steps ? '<ol>' + steps + '</ol>' : '', '', 1, ns)
    + sec('Затраты и проверка', costs, '', 1) + sec('Риски (1–5)', risks, '', 1) + sec('Классификация', cls, '', 1)
    + sec('Оценки 1–5', scoreChips + (scoreChips && missingSubs.length && missingSubs.length < subs.length ? '<p class="muted small">Остальные подшкалы (' + missingSubs.length + ' из ' + subs.length + ') не заданы — в расчётах равны «Ценности».</p>' : ''), '', 1)
    + sec('Расчётные метрики', idx + calc + ts, '', 1) + sec('Доказательства (класс ' + esc(r.evidence_class || '—') + ')', ev ? '<ul>' + ev + '</ul>' : '', '', 1, ne)
    + sec('Связи', rel + (ment.length ? '<ul>' + ment.join('') + '</ul>' : ''), '', 1) + sec('Концепт дизайна', conceptsHtml(r), 'wide', 1, (r.concepts || []).length) + '</div>';
}
function openProposal(id, fromHist) {
  var r = BYID[id]; if (!r) return;
  var cur = pm.getAttribute('data-id');
  if (!fromHist && pm.classList.contains('open') && cur && cur !== id) pmHist.push(cur);
  pm.setAttribute('data-id', id);
  $('#pmtitle').innerHTML = '<b>' + esc(r.id) + '</b> ' + esc(r.title);
  $('#pmchips').innerHTML = [r.m && r.m.rank != null ? tag('#' + fmt(r.m.rank)) : '', stChip(r.status), badge('p', r.priority), badge('q', r.quadrant), r.evidence_class ? badge('c', r.evidence_class) : '', tag(lab('category', r.category)), tag(lab('horizon', r.horizon)), r.m && r.m.composite != null ? tag('балл ' + fmt(r.m.composite)) : ''].join(' ');
  $('#pmback').hidden = !pmHist.length;
  var body = $('#pmbody'); body.innerHTML = detail(r); fillImgs(body); linkifyEl(body);
  openLayer(pm); pm.scrollTop = 0;
}
function openInfo(title, html) { $('#imtitle').innerHTML = title; var b = $('#imbody'); b.innerHTML = html; fillImgs(b); linkifyEl(b); openLayer(im); im.scrollTop = 0; }

/* ---------- реестр ---------- */
var expanded = {}, sortK = 'rank', sortD = 1, shown = [];
var HORD = { now: 0, next: 1, later: 2, vision: 3 };
var COLS = [
  { k: 'rank', t: '#', num: 1 }, { k: 'id', t: 'ID' }, { k: 'title', t: 'Предложение', cls: 'c-title' }, { k: 'status', t: 'Статус', cls: 'c-st' }, { k: 'category', t: 'Категория' },
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
  if (k === 'status') return r.status ? (r.status in PGO ? PGO[r.status] : 99) : null;
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
    case 'status': return stChip(r.status);
    case 'effort_avg': return r.effort && r.effort[0] != null ? esc(fmt(r.effort[0]) + (r.effort[1] !== r.effort[0] ? '–' + fmt(r.effort[1]) : '')) : '';
    default: return esc(fmt(v));
  }
}
COLS.forEach(function (c) { if (Array.isArray(c.k)) { var ks = c.k; c.k = ks.filter(function (k) { return REG.some(function (r) { return r.m && r.m[k] != null; }); })[0] || ks[ks.length - 1]; } });
var visCols = COLS.filter(function (c) { return REG.some(function (r) { var v = val(r, c.k); return v != null && v !== ''; }) || c.k === 'id' || c.k === 'title'; });
function metricLabel(k) { if (MET[k]) return MET[k].label; var c = COLS.filter(function (x) { return x.k === k; })[0]; return c ? c.t : k; }
function defaultDir(k) { if (MET[k]) return MET[k].dir; return ['id', 'title', 'category', 'horizon', 'evidence_class', 'priority', 'kano', 'quadrant', 'status'].indexOf(k) >= 0 ? 1 : -1; }
/* быстрые фильтры выполнения: не сделано / в работе / отстаёт */
var QF = '';
function qpass(r) { if (!QF) return true; if (QF === 'notdone') return !!r.status && !pgDone(r); if (QF === 'work') return r.status === 'in_progress' || r.status === 'partial'; if (QF === 'behind') return !!(r.pg && (r.pg.behind || []).length); return true; }
function setQF(v) { QF = v || ''; $$('#registry [data-qf]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-qf') === QF)); }); }
function filters() { var f = {}; $$('#registry [data-f]').forEach(function (s) { if (s.value) f[s.getAttribute('data-f')] = s.value; }); return f; }
function pass(r, f, q) {
  for (var k in f) { var v = f[k];
    if (k === 'labels' || k === 'tags') { if ((r[k] || []).indexOf(v) < 0) return false; }
    else if (k === 'has_mockup') { if ((v === 'yes') !== !!r.has_mockup) return false; }
    else if (String(r[k] || '') !== v) return false; }
  if (QF && !qpass(r)) return false;
  return !q || hayHas(r._hay, q);
}
function renderReg() {
  var tb = $('#tb'); if (!tb) return;
  var f = filters(), q = norm($('#q').value);
  var qs = qWords(q); shown = REG.filter(function (r) { return pass(r, f, qs.length ? qs : ''); });
  shown.sort(function (a, b) { var x = val(a, sortK), y = val(b, sortK); if (x == null && y == null) return a.id < b.id ? -1 : 1; if (x == null) return 1; if (y == null) return -1;
    var d = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'ru', { numeric: true }); return d ? d * sortD : (a.id < b.id ? -1 : 1); });
  var cols = visCols.slice(), extra = null;
  if (!cols.some(function (c) { return c.k === sortK; })) { extra = { k: sortK, t: '↕ ' + metricLabel(sortK), num: 1, extra: 1 }; cols.push(extra); }
  $('#reg-head').innerHTML = cols.map(function (c) { return '<th data-k="' + esc(c.k) + '"' + (c.num ? ' class="num' + (c.extra ? ' extra' : '') + '"' : '') + (c.k === sortK ? ' aria-sort="' + (sortD > 0 ? 'ascending' : 'descending') + '"' : '') + ' title="Сортировать: ' + esc(metricLabel(c.k)) + '">' + esc(c.t) + '</th>'; }).join('');
  tb.innerHTML = shown.map(function (r) {
    var open = !!expanded[r.id], sv = val(r, sortK);
    return '<tr class="row' + (open ? ' open' : '') + '" data-id="' + esc(r.id) + '" data-cat="' + esc(r.category) + '"' + (r.status ? ' data-st="' + esc(r.status) + '"' : '') + ' data-v="' + esc(sv == null ? '' : sv) + '" tabindex="0" aria-expanded="' + open + '">'
      + cols.map(function (c) { return '<td' + (c.num ? ' class="num"' : c.cls ? ' class="' + c.cls + '"' : '') + '>' + cell(r, c) + '</td>'; }).join('') + '</tr>'
      + (open ? '<tr class="detail"><td colspan="' + cols.length + '">' + detail(r) + '</td></tr>' : '');
  }).join('') || '<tr><td colspan="' + cols.length + '" class="muted">Ничего не найдено — измените фильтры или поиск.</td></tr>';
  $('#reg-count').textContent = 'Показано: ' + shown.length + ' из ' + REG.length + (PG ? ' · выполнено: ' + shown.filter(function (r) { return r.status === 'done'; }).length : '');
  var sb = $('#sortby'); if (sb && sb.value !== sortK) { if ([].some.call(sb.options, function (o) { return o.value === sortK; })) sb.value = sortK; }
  var sd = $('#sortdir'); if (sd) sd.textContent = sortD > 0 ? 'по возрастанию ↑' : 'по убыванию ↓';
  fillImgs(tb); $$('tr.detail', tb).forEach(linkifyEl);
}
function setSort(k, dir) { if (dir) { sortK = k; sortD = dir; } else if (sortK === k) sortD = -sortD; else { sortK = k; sortD = defaultDir(k); } renderReg(); }
function toggleRow(id) { if (expanded[id]) delete expanded[id]; else expanded[id] = 1; renderReg(); }
function resetFilters() { $$('#registry [data-f]').forEach(function (s) { s.value = ''; }); var q = $('#q'); if (q) q.value = ''; setQF(''); }
function goRegistry(st, qf) { closeAll(); resetFilters(); var s = $('#registry select[data-f="status"]'); if (s && st) s.value = st; setQF(qf || ''); renderReg(); var sec = document.getElementById('registry'); if (sec) sec.scrollIntoView({ behavior: 'instant', block: 'start' }); }
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
  var pgHead = PG ? ['status', 'status_confidence', 'status_source', 'issues', 'prs', 'last_commit', 'status_note', 'status_since'] : [];
  var lines = [head.concat(pgHead, extraM).join(',')];
  shown.forEach(function (r) {
    var base = [r.id, r.title, r.category, r.segment, r.horizon, r.evidence_class, r.priority, r.quadrant, r.moscow, r.kano, (r.labels || []).join('; '), (r.tags || []).join('; '), (r.dependencies || []).join('; '), r.effort ? r.effort[0] : '', r.effort ? r.effort[1] : '', r.cost_money && r.cost_money.currency || '', r.description, r.rationale, r.cheap_test];
    var g = r.pg || {}, c0 = (g.commits || [])[0];
    var pgv = PG ? [r.status || '', g.confidence, g.source || '', (g.issues || []).map(function (x) { return '#' + x.n + ' ' + (x.state || ''); }).join('; '), (g.prs || []).map(function (x) { return '#' + x.n + ' ' + (x.state || ''); }).join('; '), c0 ? c0.sha + ' ' + (c0.date || '') + ' ' + (c0.subject || '') : '', g.note || '', g.since || ''] : [];
    lines.push(base.concat(pgv, extraM.map(function (k) { return r.m[k]; })).map(csvCell).join(','));
  });
  download('registry-' + stamp + '.csv', '\ufeff' + lines.join('\r\n') + '\r\n', 'text/csv;charset=utf-8');
}

/* ---------- Гант, Kanban, узлы схем ---------- */
function openGantt(i) {
  var g = GANTT[i]; if (!g) return;
  var deps = (g.deps || []).map(function (d) { if (BYID[d]) return pidLink(d); var t = GANTT.filter(function (x) { return x.id === d; })[0]; return t ? '<a href="#gantt" data-g-open="' + t.i + '">' + esc(d) + ' ' + esc(t.task) + '</a>' : esc(d); }).join(', ');
  var steps = (g.proposal_ids || []).map(function (id) { var r = BYID[id]; if (!r || !(r.steps || []).length) return ''; return '<p><b>' + pidLink(id) + '</b> ' + esc(r.title) + '</p><ol>' + r.steps.map(function (s) { s = asObj(s, 'what'); return '<li><b>' + esc(txt(s.what)) + '</b>' + (s.where ? ' — ' + esc(txt(s.where)) : '') + (s.how ? ': ' + esc(txt(s.how)) : '') + '</li>'; }).join('') + '</ol>'; }).join('');
  var gp = g.pg, gph = gp ? kv([['Выполнение', stChip(gp.status, PG.glabels, PG.gicons, 'gst') + ' <b>' + Math.round((gp.progress || 0) * 100) + ' %</b>'], ['Сделано', (gp.done_ids || []).map(pidLink).join(', ')], ['Открыто', (gp.open_ids || []).map(pidLink).join(', ')]]) : '';
  openInfo('<span class="muted">Гант</span> ' + esc(g.task), kv([['Фаза', esc(g.phase === 'vision' ? 'видение' : g.phase)], ['Сроки', esc(g.when)], ['Тип', g.type === 'milestone' ? 'веха (контрольная точка)' : 'работа'], ['Ответственный', esc(g.owner)], ['Критерий готовности', esc(g.done)], ['Зависимости', deps]])
    + gph + ((g.proposal_ids || []).length ? '<h4>Предложения в этой задаче</h4><ul>' + (PG ? pgList(g.proposal_ids) : plist(g.proposal_ids)) + '</ul>' : '') + (steps ? '<h4>Что сделать (шаги из карточек)</h4>' + steps : ''));
}
function openKanban(i) {
  var k = KAN[i]; if (!k) return; var r = BYID[k.id];
  var eff = Array.isArray(k.effort_days) ? k.effort_days.join('–') + ' дн.' : txt(k.effort_days);
  var steps = (k.steps || []).map(function (s) { return '<li>' + esc(txt(s)) + '</li>'; }).join('');
  var links = (k.links || []).map(function (l) { var u = typeof l === 'object' && l ? (l.url || '') : l; var t = typeof l === 'object' && l ? (l.title || l.url) : l; return '<li>' + link(u, t) + '</li>'; }).join('');
  openInfo('<span class="muted">Kanban · ' + esc(k.column) + '</span> ' + esc(k.id || '') + ' ' + esc(k.title || ''), kv([['Колонка', esc(k.column)], ['Статус по фактам', r ? stChip(r.status) : ''], ['Приоритет', badge('p', k.priority || (r ? r.priority : ''))], ['Трудозатраты', esc(eff)], ['Цель', esc(txt(k.goal))], ['KPI', esc(txt(k.kpi))], ['Метки', (k.tags || []).map(function (t) { return tag(t); }).join(' ')]])
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
  if (window.PS && window.PS.isReplaced('lightbox')) return;              /* просмотр картинок взяло расширение (PS.replace) */
  var g = el.getAttribute('data-group') || '', seen = {};
  LB.items = lbFigs().filter(function (f) { return (f.getAttribute('data-group') || '') === g && IMG[f.getAttribute('data-key')]; }).filter(function (f) { var k = f.getAttribute('data-key') + '|' + (f.getAttribute('data-ref') || ''); if (seen[k]) return false; seen[k] = 1; return true; });
  if (!LB.items.length) return;
  LB.idx = Math.max(0, LB.items.findIndex(function (f) { return f.getAttribute('data-key') === el.getAttribute('data-key') && (f.getAttribute('data-ref') || '') === (el.getAttribute('data-ref') || ''); }));
  LB.zoom = 'fit'; LB.cur = LB.items[LB.idx]; openLayer(lb); lbShow();
}
function lbStep(d) { if (LB.items.length < 2) return; LB.idx = (LB.idx + d + LB.items.length) % LB.items.length; lbShow(); }
function lbShow() {
  var f = LB.items[LB.idx]; LB.cur = f; LB.alt = false; var key = f.getAttribute('data-key'), ref = REFS[f.getAttribute('data-ref')] || null;
  lbimg.removeAttribute('style'); lbimg.src = IMG[key]; lbimg.alt = f.getAttribute('data-cap') || '';
  /* 1.5: «Открыть интерактивный макет» (живой HTML; с подсказками элементов — #hs) и переключатель второй темы снимка */
  var lo = $('#lbopen'), hu = f.getAttribute('data-html') || (ref && ref.html) || '';
  if (lo) { lo.hidden = !hu; if (hu) lo.setAttribute('href', hu + (ref && ref.mock && (ref.hotspots || []).length && hu.indexOf('#') < 0 ? '#hs' : '')); else lo.removeAttribute('href'); }
  var lt = $('#lbtheme'), alt = f.getAttribute('data-alt');
  if (lt) { lt.hidden = !(alt && IMG[alt]); lt.textContent = 'Тема: ' + themeName(f.getAttribute('data-alt-theme')); lt.setAttribute('aria-pressed', 'false'); }
  $('#lbcap').textContent = (f.getAttribute('data-cap') || '').replace(/\s+/g, ' ');
  var lpp = $('#lbpids'), pids = (f.getAttribute('data-pids') || '').split(/\s+/).filter(function (x) { return BYID[x]; });
  if (lpp) { lpp.innerHTML = pids.length ? 'Предложения: ' + pids.map(pidLink).join(' ') : ''; lpp.hidden = !pids.length; }
  $('#lbcount').textContent = (LB.idx + 1) + ' / ' + LB.items.length;
  $('#lbprev').disabled = $('#lbnext').disabled = LB.items.length < 2;
  lb.classList.toggle('nopanel', !ref); lb.classList.remove('nohs'); $('#lbhs').hidden = !ref || !(ref.hotspots || []).length;
  $$('.pin,.hsbox,.hsel', lbwrap).forEach(function (x) { x.remove(); });
  lbside.innerHTML = '';
  if (ref) {
    var hs = ref.hotspots || [];
    lbside.innerHTML = '<h3>' + esc(ref.title) + '</h3><div class="meta">' + ((ref.proposals || []).length ? 'Предложения: ' + ref.proposals.map(pidLink).join(' ') : 'Общий дизайн') + (ref.kind ? ' · ' + esc(ref.kind) : '') + '</div>'
      + (ref.summary ? '<p>' + esc(ref.summary) + '</p>' : '') + (ref.entry ? '<p class="meta">Точка входа: ' + esc(ref.entry) + '</p>' : '')
      + '<div class="hslist">' + hs.map(function (h) { var pids = (h.pids && h.pids.length ? h.pids : h.proposal ? [h.proposal] : []), secs = (h.sec || []).filter(function (n) { return document.getElementById('s-' + n); });
        return '<div class="hsitem" data-n="' + esc(h.n) + '"><span class="hsn">' + esc(h.n) + '</span><div><b>' + esc(h.title) + (h.state ? ' <span class="st st-' + esc(h.state) + '">' + esc({ new: 'новое', changed: 'изменено', shared: 'общий дизайн' }[h.state] || h.state) + '</span>' : '') + '</b><span>' + esc(h.text) + '</span>'
          + (h.why ? '<span class="hs-sec">Для чего: ' + esc(h.why) + '</span>' : '') + (pids.length ? ' ' + pids.map(pidLink).join(' ') : '')
          + (secs.length ? ' <span class="hs-sec">' + secs.map(function (n) { return '<a href="#s' + n + '">раздел ' + n + '</a>'; }).join(', ') + '</span>' : '') + '</div></div>'; }).join('') + '</div>'
      + ((ref.todo || []).length ? '<details open><summary>Что доделать (' + ref.todo.length + ')</summary><ul>' + ref.todo.map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('') + '</ul></details>' : '')
      + (ref.mock ? (hu ? '<p class="meta"><a href="' + esc(hu) + ((ref.hotspots || []).length && hu.indexOf('#') < 0 ? '#hs' : '') + '" target="_blank" rel="noopener">Открыть интерактивный макет с подсказками ↗</a></p>' : '')
        : '<p class="meta"><a href="#ref-' + esc(f.getAttribute('data-ref')) + '">Карточка референса →</a></p>');
    hs.forEach(function (h) { if (h.l == null) return;
      var box = document.createElement('div'); box.className = 'hsbox'; box.setAttribute('data-n', h.n); box.style.cssText = 'left:' + h.l + '%;top:' + h.t + '%;width:' + h.w + '%;height:' + h.h + '%'; lbwrap.appendChild(box);
      var sel = document.createElement('div'); sel.className = 'hsel'; sel.setAttribute('data-n', h.n); sel.style.cssText = box.style.cssText; lbwrap.appendChild(sel);
      var pin = document.createElement('div'); pin.className = 'pin'; pin.setAttribute('data-n', h.n); pin.textContent = h.n; pin.title = h.title; pin.style.left = (h.pl != null ? h.pl : h.l) + '%'; pin.style.top = (h.pt != null ? h.pt : h.t) + '%'; lbwrap.appendChild(pin); });
  }
  if (lbimg.complete && lbimg.naturalWidth) setZoom(LB.zoom); syncHash();
}
function themeName(t) { return { dark: 'тёмная', light: 'светлая' }[t] || 'другая'; }
function lbTheme() { var f = LB.cur, alt = f && f.getAttribute('data-alt'); if (!alt || !IMG[alt]) return; LB.alt = !LB.alt; lbimg.src = IMG[LB.alt ? alt : f.getAttribute('data-key')];
  var lt = $('#lbtheme'); if (lt) { lt.setAttribute('aria-pressed', String(LB.alt)); lt.textContent = 'Тема: ' + (LB.alt ? 'основная' : themeName(f.getAttribute('data-alt-theme'))); } }
function baseWidth() { var key = LB.cur && (LB.alt && LB.cur.getAttribute('data-alt') || LB.cur.getAttribute('data-key')); var d = DIMS[key] || [lbimg.naturalWidth, lbimg.naturalHeight]; var ref = REFS[LB.cur && LB.cur.getAttribute('data-ref')]; var nw = d[0] || 0, nh = d[1] || 0; if (ref && ref.w) { return [ref.w, ref.h || (nh * ref.w / (nw || 1))]; } var sc = ref && ref.scale > 0 ? ref.scale : 1; return [nw / sc, nh / sc]; }
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
  /* вердикт: в заголовке — до 45 знаков; полный текст — verdict_long или раскрытие усечённого */
  var vlong = c.verdict_long ? (c.verdict_cut ? '<details class="cverdict"><summary>Вывод полностью</summary><p>' + esc(c.verdict_long) + '</p></details>'
    : '<div class="lblh">Вывод</div><p class="cverdict">' + esc(c.verdict_long) + '</p>') : '';
  return '<article class="ccard" data-type="' + esc(c.type) + '" data-slug="' + esc(c.slug) + '">' + media + '<div><h4>' + link(c.url, c.name) + (c.verdict_short ? ' ' + tag(c.verdict_short, 'verdict') : '') + '</h4><div class="cmeta">' + meta + '</div>' + vlong
    + (show.them ? lst('Где лучше они', c.better_than_us, 'them') : '') + (show.us ? lst('Где лучше мы', c.we_better, 'us') : '') + (show.best ? lst('Их лучшие решения', c.best_solutions, 'best') + lst('Перенять', c.adopt, 'best') : '')
    + (show.design && c.design_note ? '<div class="lblh">Дизайн</div><p>' + esc(c.design_note) + '</p>' : '') + lst('Жалобы пользователей', c.complaints, 'them') + lst('Не повторять', c.avoid, 'them')
    + (srcs ? '<div class="cmeta">' + srcs + '</div>' : '') + '</div></article>';
}
function renderComp() {
  var grid = $('#cgrid'); if (!grid) return;
  var q = norm(($('#cq') || {}).value), ty = ($('#ctype') || {}).value || '';
  var show = { them: !$('#cthem') || $('#cthem').checked, us: !$('#cus') || $('#cus').checked, best: !$('#cbest') || $('#cbest').checked, design: !$('#cdesign') || $('#cdesign').checked };
  var all = COMP.filter(function (c) { return !c.self; });
  var qs = qWords(q), list = all.filter(function (c) { return (!ty || c.type === ty) && (!qs.length || hayHas(c._hay, qs)); });
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
  var FL = META.comp_feature_labels || {};
  box.innerHTML = '<table class="cm"><thead><tr><th>Продукт</th>' + feats.map(function (f) { return '<th title="' + esc(f) + '">' + esc(FL[f] || f) + '</th>'; }).join('') + '</tr></thead><tbody>'
    + rows.map(function (c) { return '<tr' + (c.self ? ' class="self"' : '') + ' data-slug="' + esc(c.slug) + '"><th scope="row" title="' + esc(c.name + (c.verdict_short ? ' — ' + c.verdict_short : '')) + '">' + esc(c.name) + (c.self ? ' <span class="tag">мы</span>' : '') + '</th>' + feats.map(function (f, i) { return cellv(c, f, i); }).join('') + '</tr>'; }).join('')
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
    var qs = qWords(q); Array.prototype.forEach.call(t.tBodies[0].rows, function (r) { r.hidden = !!qs.length && !hayHas(norm(r.textContent), qs); }); }); });
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

/* схемы увеличиваются живыми в просмотре ps-interact.js (кнопка «🔍 Увеличить»); старые ссылки #lb=flow-<ключ> открывают его же */
function openViewer(key, sel) { return !!(window.PSI && window.PSI.open(key, sel)); }

/* ---------- интерактивные графики: панель пояснений, подсветка, ленивая подгрузка (references/interactive-site.md, 2.3) ---------- */
/* single/lite: SVG — в разметке, пояснения — блок d-charts {ключ: meta}; site: window.PS_CHARTS[ключ] = {svg, meta} из
   assets/charts-<группа>.js (динамическое подключение скрипта при первом показе графика группы или по глубокой ссылке) */
var DCH = J('d-charts') || {}, SVGNS = 'http://www.w3.org/2000/svg';
var KIND_T = { stage: 'этап', point: 'точка', bar: 'столбец', node: 'узел', cell: 'ячейка', event: 'событие', link: 'связь', legend: 'легенда', axis: 'ось', area: 'область', line: 'линия', row: 'строка', column: 'столбец', shape: 'фигура' };
var CP = { fig: null, key: null, id: null, el: null, open: false };
var cpEl = $('#cp'), cpTip = $('#cp-tip');
function cssq(s) { return window.CSS && CSS.escape ? CSS.escape(String(s)) : String(s).replace(/["\\\]\[]/g, '\\$&'); }
function chMeta(key) { var P = window.PS_CHARTS; if (P && P[key] && P[key].meta) return P[key].meta; return DCH[key] || null; }
function chEls(key) { var m = chMeta(key); return (m && m.elements) || []; }
function chFind(key, id) { var a = chEls(key); for (var i = 0; i < a.length; i++) if (a[i].id === id) return i; return -1; }
function figOf(n) { return n && n.closest ? n.closest('figure.ps-ichart') : null; }
function svgOf(fig) { return fig ? fig.querySelector('svg[data-ps-chart]') : null; }
function elOf(fig, id) { var s = svgOf(fig); return s ? s.querySelector('[data-ps-el="' + cssq(id) + '"]') : null; }
function chartFig(key) { return $('figure.ps-ichart.ps-primary[data-chart="' + cssq(key) + '"]') || $('figure.ps-ichart[data-chart="' + cssq(key) + '"]'); }
function initChart(fig) {
  if (!fig || fig.classList.contains('ps-ready')) return;
  var svg = svgOf(fig), key = fig.getAttribute('data-chart'); if (!svg || !chMeta(key)) return;
  /* увеличение — живой SVG в просмотре ps-interact.js (кнопка «🔍 Увеличить»), плоская картинка-копия больше не нужна */
  $$('.ps-el[data-ps-el]', svg).forEach(function (g, i) {
    for (var ch = g.firstElementChild; ch; ch = ch.nextElementSibling) { if (ch.localName === 'title') { g.setAttribute('data-tip', ch.textContent); g.removeChild(ch); break; } }
    g.setAttribute('tabindex', i ? '-1' : '0');   /* одна остановка Tab на график, внутри — ←/→ */
  });
  var ovl = document.createElementNS(SVGNS, 'g'); ovl.setAttribute('class', 'ps-ovl'); ovl.setAttribute('aria-hidden', 'true'); ovl.setAttribute('pointer-events', 'none'); svg.appendChild(ovl);
  fig.classList.add('ps-ready');
}
function bboxIn(svg, el) {
  try {
    var b = el.getBBox(), m = svg.getScreenCTM().inverse().multiply(el.getScreenCTM()), xs = [], ys = [];
    [[b.x, b.y], [b.x + b.width, b.y], [b.x, b.y + b.height], [b.x + b.width, b.y + b.height]].forEach(function (p) { var q = svg.createSVGPoint(); q.x = p[0]; q.y = p[1]; q = q.matrixTransform(m); xs.push(q.x); ys.push(q.y); });
    var x0 = Math.min.apply(null, xs), y0 = Math.min.apply(null, ys);
    return { x: x0, y: y0, w: Math.max.apply(null, xs) - x0, h: Math.max.apply(null, ys) - y0 };
  } catch (e) { return null; }
}
function ring(svg, el, cls) {
  var ovl = svg && svg.querySelector('.ps-ovl'); if (!ovl) return;
  $$('.' + cls, ovl).forEach(function (x) { ovl.removeChild(x); });
  if (!el) return;
  var b = bboxIn(svg, el); if (!b) return;
  var vb = svg.viewBox && svg.viewBox.baseVal, k = vb && vb.width && svg.getBoundingClientRect().width ? vb.width / svg.getBoundingClientRect().width : 1, pad = 5 * k;
  var w = Math.max(b.w + 2 * pad, 12 * k), h = Math.max(b.h + 2 * pad, 12 * k), x = b.x + b.w / 2 - w / 2, y = b.y + b.h / 2 - h / 2;
  ['halo', 'line'].forEach(function (part) {
    var r = document.createElementNS(SVGNS, 'rect');
    r.setAttribute('class', cls + ' ' + cls + '-' + part); r.setAttribute('x', x); r.setAttribute('y', y); r.setAttribute('width', w); r.setAttribute('height', h); r.setAttribute('rx', 3 * k);
    ovl.appendChild(r);
  });
}
function hl(svg, grp) {
  if (!svg) return 0; svg.classList.remove('ps-hl-on'); $$('.ps-hl', svg).forEach(function (x) { x.classList.remove('ps-hl'); });
  if (!grp) return 0; var n = 0;
  $$('[data-ps-group]', svg).forEach(function (x) { if ((' ' + x.getAttribute('data-ps-group') + ' ').indexOf(' ' + grp + ' ') >= 0) { x.classList.add('ps-hl'); n++; } });
  if (n) svg.classList.add('ps-hl-on'); return n;
}
function focusEl(el) {
  var svg = el && el.ownerSVGElement; if (!svg) return;
  $$('.ps-el[tabindex="0"]', svg).forEach(function (x) { if (x !== el) x.setAttribute('tabindex', '-1'); });
  el.setAttribute('tabindex', '0'); try { el.focus({ preventScroll: true }); } catch (e) { el.focus(); }
}
function cpHtml(e, hlN) {
  var h = '';
  if (e.summary) h += '<section><h4>Что это</h4><p>' + esc(e.summary) + '</p></section>';
  if (e.meaning) h += '<section><h4>Что значит</h4><p>' + esc(e.meaning) + '</p></section>';
  if ((e.actions || []).length) h += '<section><h4>Что делать</h4><ul>' + e.actions.map(function (a) { return '<li>' + esc(a) + '</li>'; }).join('') + '</ul></section>';
  if ((e.metrics || []).length) h += '<section><h4>Метрики</h4><dl class="cp-mx">' + e.metrics.map(function (x) { return '<dt>' + esc(x.label) + '</dt><dd>' + esc(x.value === '' || x.value == null ? '—' : x.value) + (x.tag ? ' <span class="tag" title="метка достоверности">' + esc(x.tag) + '</span>' : '') + '</dd>'; }).join('') + '</dl></section>';
  /* FB-035, п. 4: «Связанные предложения» (ссылки #p/… — строка реестра; P-id в тексте — карточка) и «Где на странице» (разделы, план, макеты…) */
  var ls = (e.links || []).filter(function (l) { return /^#[\w\/?=&.-]+$/.test(String(l.href || '')); });
  var lp = ls.filter(function (l) { return /^#p[\/=]P\d+$/.test(l.href); }), lo = ls.filter(function (l) { return !/^#p[\/=]P\d+$/.test(l.href); });
  var li = function (l) { var m = /^#p[\/=](P\d+)$/.exec(l.href), r = m && BYID[m[1]]; return '<li><a href="' + esc(l.href) + '">' + esc(l.label || l.href) + '</a>' + (r && (l.label || '').indexOf(r.title) < 0 ? ' <span class="muted">' + esc(r.title) + '</span>' : '') + '</li>'; };
  if (lp.length) h += '<section><h4>Связанные предложения</h4><ul class="cp-links">' + lp.map(li).join('') + '</ul></section>';
  if (lo.length) h += '<section><h4>Где на странице</h4><ul class="cp-links">' + lo.map(li).join('') + '</ul></section>';
  if (hlN) h += '<p class="small muted">На графике подсвечено элементов: ' + hlN + '.</p>';
  return h || '<p class="muted">Пояснение к элементу не задано.</p>';
}
function setChartHash(h) { if (stack.length) return; try { if (h) history.replaceState(null, '', h); else if (/^#chart\//.test(location.hash)) history.replaceState(null, '', location.pathname + location.search); } catch (e) { /* file:// без history */ } }
function selectEl(fig, id, opt) {
  opt = opt || {}; if (!fig || !cpEl) return false;
  var key = fig.getAttribute('data-chart'), els = chEls(key), i = chFind(key, id); if (i < 0) return false;
  var e = els[i], el = elOf(fig, id), svg = svgOf(fig);
  if (CP.fig && CP.fig !== fig) { ring(svgOf(CP.fig), null, 'ps-sel'); hl(svgOf(CP.fig), null); }
  if (CP.el) CP.el.classList.remove('ps-on');
  CP.fig = fig; CP.key = key; CP.id = id; CP.el = el; CP.open = true;
  if (el) el.classList.add('ps-on');
  var n = hl(svg, e.highlight || (el && el.getAttribute('data-ps-highlight')) || '');
  $('#cp-chart').textContent = (chMeta(key) || {}).title || '';
  $('#cp-title').textContent = e.title || id;
  $('#cp-kind').textContent = KIND_T[e.kind] || e.kind || '';
  $('#cp-pos').textContent = (i + 1) + ' из ' + els.length;
  var b = $('#cp-body'); b.innerHTML = cpHtml(e, n); b.scrollTop = 0; linkifyEl(b);
  cpEl.hidden = false; cpEl.classList.add('open'); document.body.classList.add('cp-open');
  var live = $('#cp-live'); if (live) live.textContent = (e.title || id) + '. Панель пояснений открыта, Esc — закрыть.';
  ring(svg, el, 'ps-sel'); ring(svg, null, 'ps-foc');
  if (el && opt.focus !== false) focusEl(el);
  if (el) ensureVisible(el);
  setChartHash('#chart/' + key + '/' + id);
  emitPS('chart:select', { key: key, id: id });
  return true;
}
function closePanel(ret) {
  if (!CP.open) return; var el = CP.el, svg = svgOf(CP.fig);
  ring(svg, null, 'ps-sel'); hl(svg, null); if (el) el.classList.remove('ps-on');
  cpEl.classList.remove('open'); cpEl.hidden = true; document.body.classList.remove('cp-open');
  CP.open = false; CP.fig = null; CP.el = null; CP.id = null; setChartHash('');
  if (ret && el && document.contains(el)) focusEl(el);
}
function stepEl(d) { if (!CP.open) return; var els = chEls(CP.key), n = els.length; if (!n) return; var i = chFind(CP.key, CP.id); selectEl(CP.fig, els[((i < 0 ? 0 : i) + d + n) % n].id, { focus: true }); }
function moveFocus(fig, el, d) { var els = chEls(fig.getAttribute('data-chart')), n = els.length; if (!n) return; var i = chFind(fig.getAttribute('data-chart'), el.getAttribute('data-ps-el')); var nx = elOf(fig, els[((i < 0 ? 0 : i) + d + n) % n].id); if (nx) focusEl(nx); }
function ensureVisible(el) {
  requestAnimationFrame(function () {
    if (!CP.open || CP.el !== el) return;            /* за кадр успели перейти по ссылке или выбрать другой элемент */
    try { el.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' }); } catch (e) { /* старый движок */ }
    var r = el.getBoundingClientRect(), pr = cpEl.getBoundingClientRect(), top = innerWidth <= 900 ? 60 : 8;
    var bottom = pr.width >= innerWidth - 2 && pr.top > 0 ? pr.top : innerHeight;      /* нижний лист закрывает низ экрана */
    if (r.top < top || r.bottom > bottom - 8) window.scrollBy({ top: r.top - top - Math.max(0, (bottom - top - r.height) / 3), behavior: 'instant' });
  });
}
function focusRing(el) { var svg = el && el.ownerSVGElement; if (svg) ring(svg, CP.open && el === CP.el ? null : el, 'ps-foc'); }   /* у выбранного — сплошной контур выбора */
/* подгрузка assets/charts-<группа>.js (site) */
var CHQ = {};
function mountAll() {
  var P = window.PS_CHARTS || {};
  $$('figure.ps-ichart').forEach(function (fig) {
    if (fig.classList.contains('ps-ready')) return;
    var box = fig.querySelector('.ps-svg'), key = fig.getAttribute('data-chart');
    if (box && !svgOf(fig) && P[key] && P[key].svg) { box.innerHTML = P[key].svg; box.classList.remove('ps-wait'); }   /* SVG очищен сборщиком */
    initChart(fig);
  });
}
function loadSrc(src, cb) {
  var q = CHQ[src] || (CHQ[src] = { st: 0, cbs: [] });
  if (q.st === 2) { if (cb) cb(); return; }
  if (cb) q.cbs.push(cb);
  if (q.st === 1) return; q.st = 1;
  var s = document.createElement('script'); s.src = src; s.async = true;
  s.onload = function () { q.st = 2; safe('charts-mount', mountAll); var cs = q.cbs; q.cbs = []; cs.forEach(function (f) { safe('charts-cb', f); }); };
  s.onerror = function () { q.st = 0; console.error('[charts] не загрузился ' + src); };
  document.head.appendChild(s);
}
function ensureChart(fig, cb) {
  if (fig.classList.contains('ps-ready')) { cb(); return; }
  var box = fig.querySelector('.ps-svg[data-ps-src]');
  if (box && !svgOf(fig)) loadSrc(box.getAttribute('data-ps-src'), cb); else { initChart(fig); cb(); }
}
function loadAllCharts(cb) {
  var srcs = []; $$('.ps-svg[data-ps-src]').forEach(function (b) { var s = b.getAttribute('data-ps-src'); if (srcs.indexOf(s) < 0) srcs.push(s); });
  var left = srcs.length; if (!left) { mountAll(); if (cb) cb(); return; }
  srcs.forEach(function (s) { loadSrc(s, function () { if (--left === 0 && cb) cb(); }); });
}

/* ---------- единый роутер ссылок страницы ----------
   #s<N> — раздел стратегии N (на странице id="s-N"); #p/<P-id> — строка реестра раскрыта; #registry?category|horizon|class|quadrant|priority=… —
   реестр с фильтром; #gantt/<G>, #kanban/<P>, #competitor/<slug>, #mockup/<ключ>, #flow/<ключ> — показать блок; #chart/<ключ>[/<id>] — график и его
   элемент. Старые #p=<P-id> (окно карточки), #lb=<картинка> (лайтбокс) и #s-N (обычный якорь) работают как раньше. */
var REGF = { category: 'category', horizon: 'horizon', 'class': 'evidence_class', quadrant: 'quadrant', priority: 'priority' };
function parseHref(h) {
  h = String(h || ''); try { h = decodeURIComponent(h); } catch (e) { /* как есть */ }
  var m;
  if ((m = h.match(/^#s(-?)(\d+)$/))) return { t: 'sec', n: +m[2], legacy: !!m[1] };
  if ((m = h.match(/^#p\/(P\d+)$/))) return { t: 'prow', id: m[1] };
  if ((m = h.match(/^#p=(P\d+)$/))) return { t: 'pcard', id: m[1] };
  if ((m = h.match(/^#registry(?:\?(.*))?$/))) {     /* без «?» — обычный якорь раздела (навигация не сбрасывает фильтры) */
    var f = {}, bad = false;
    (m[1] ? m[1].split('&') : []).forEach(function (kv) { var p = kv.split('='); if (p.length === 2 && REGF[p[0]] && p[1]) f[REGF[p[0]]] = p[1]; else bad = true; });
    return { t: 'reg', f: f, bad: bad, bare: m[1] == null };
  }
  if ((m = h.match(/^#(gantt|kanban|competitor|mockup|flow)\/(.+)$/))) return { t: m[1], id: m[2] };
  if ((m = h.match(/^#chart\/([\w-]+)(?:\/(.+))?$/))) return { t: 'chart', key: m[1], id: m[2] || '' };
  if ((m = h.match(/^#lb=(.+)$/))) return { t: 'lb', key: m[1] };
  return null;
}
function compTarget(slug) { return $('#cgrid .ccard[data-slug="' + cssq(slug) + '"]') || $('#cmatrix tr[data-slug="' + cssq(slug) + '"]'); }
/* цель ссылки без побочных действий (для проверок и для go): элемент или null */
function resolveTarget(r) {
  if (typeof r === 'string') r = parseHref(r);
  if (!r) return null;
  switch (r.t) {
    case 'sec': return document.getElementById('s-' + r.n);
    case 'prow': case 'pcard': return BYID[r.id] ? (r.t === 'prow' ? document.getElementById('registry') : pm) : null;
    case 'reg': return r.bad ? null : document.getElementById('registry');
    case 'gantt': return $('#gantt [data-gid="' + cssq(r.id) + '"]');
    case 'kanban': return $('#kanban [data-kid="' + cssq(r.id) + '"]');
    case 'competitor': return compTarget(r.id) || (COMP.some(function (c) { return c.slug === r.id && !c.self; }) ? $('#cgrid') : null);
    case 'mockup': var q = '[data-mock="' + cssq(r.id) + '"]'; return $('#mockups ' + q) || $('#current ' + q) || $('main ' + q);
    case 'flow': return $('#flows .flow[data-flow="' + cssq(r.id) + '"]') || $('main .flow[data-flow="' + cssq(r.id) + '"]');
    case 'chart': var f = chartFig(r.key); if (!f || !r.id) return f; return !chMeta(r.key) || chFind(r.key, r.id) >= 0 ? f : null;
  }
  return null;
}
function flash(el) { if (!el) return; el.classList.remove('ps-flash'); void el.offsetWidth; el.classList.add('ps-flash'); setTimeout(function () { el.classList.remove('ps-flash'); }, 2300); }
function reveal(el) {
  if (!el) return false;
  el.scrollIntoView({ behavior: 'instant', block: 'center' }); flash(el);
  if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1');
  try { el.focus({ preventScroll: true }); } catch (e) { /* не фокусируется */ }
  return true;
}
function goRegFilters(f) {
  closeAll(); resetFilters();
  Object.keys(f).forEach(function (k) {
    var s = $('#registry select[data-f="' + k + '"]'); if (!s) return;
    if (![].some.call(s.options, function (o) { return o.value === f[k]; })) { var o = document.createElement('option'); o.value = f[k]; o.textContent = (k === 'evidence_class' ? 'Класс ' + f[k] : lab(k, f[k])) + ' (0)'; s.appendChild(o); }
    s.value = f[k];
  });
  renderReg();
  var sec = document.getElementById('registry'); if (sec) { sec.scrollIntoView({ behavior: 'instant', block: 'start' }); flash($('#reg-count')); }
}
function go(h) {
  var r = parseHref(h); if (!r) return false;
  if (r.t !== 'chart') closePanel(false);          /* цель вне графика — панель закрывается */
  switch (r.t) {
    case 'sec': if (r.legacy) return false; var s = document.getElementById('s-' + r.n); if (!s) return false; closeAll(); s.scrollIntoView({ behavior: 'instant', block: 'start' }); flash(s.querySelector('h2') || s); return true;
    case 'prow': if (!BYID[r.id]) return false; showInRegistry(r.id); return true;
    case 'pcard': if (!BYID[r.id]) return false; openProposal(r.id); return true;
    case 'reg': if (r.bare) return false; goRegFilters(r.f); return true;
    case 'kanban': closeAll(); var pl = document.getElementById('kbv-plan'); if (pl && !pl.checked) pl.checked = true; return reveal(resolveTarget(r));
    case 'competitor':
      closeAll(); var el = compTarget(r.id);
      if (!el || !el.classList.contains('ccard')) { var cq = $('#cq'), ct = $('#ctype'); if (cq) cq.value = ''; if (ct) ct.value = ''; renderComp(); el = compTarget(r.id) || el; }
      return reveal(el);
    case 'gantt': case 'mockup': case 'flow': closeAll(); return reveal(resolveTarget(r));
    case 'chart':
      var f = chartFig(r.key); if (!f) return false; closeAll();
      ensureChart(f, function () {
        f.scrollIntoView({ behavior: 'instant', block: 'center' });
        if (r.id && selectEl(f, r.id, { focus: true })) { var el = elOf(f, r.id); if (el) el.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'nearest' }); return; }
        flash(f);
      });
      return true;
    case 'lb': var ck = /^c-(.+)$/.exec(r.key); if (ck && chartFig(ck[1])) return go('#chart/' + ck[1]);
      var fk = /^flow-(.+)$/.exec(r.key); if (fk) return openViewer(fk[1]); return false;
  }
  return false;
}
window.PS_ROUTER = { parse: parseHref, resolve: resolveTarget, go: go, select: function (key, id) { var f = chartFig(key); return !!f && f.classList.contains('ps-ready') && selectEl(f, id); },
  close: function () { closePanel(true); }, loadAll: loadAllCharts, meta: chMeta, state: function () { return { open: CP.open, key: CP.key, id: CP.id }; } };

/* ---------- хуки расширения (1.5): window.PS — данные, роутер, окна и события страницы ----------
   Слои страницы (ps-interact.js, ps-search.js, ps-ents.js) и пользовательские build/extra.js, build/extra/*.js работают через него:
   PS.on('ready'|'chart:select'|'layer:open'|'layer:close'|'viewer:open'|'viewer:close'|'viewer:select'|'search:open', fn) — событие уже
   было (ready) → fn вызывается сразу; PS.replace('lightbox'|'viewer'|'search'|'entities') — расширение берёт компонент на себя: встроенный
   слой не срабатывает, smoke_html.mjs пропускает его проверки с пояснением (<html data-ps-replaced="…">). */
var HOOKS = {}, FIRED = {}, REPLACED = {};
window.PS = {
  version: '1.5', data: J, esc: esc, router: window.PS_ROUTER,
  openProposal: openProposal, openInfo: openInfo, openNode: openNode, openGantt: openGantt, openKanban: openKanban,
  openLayer: openLayer, closeLayer: closeLayer, closeAll: closeAll, linkify: function (root) { linkifyEl(root); },
  on: function (ev, fn) { (HOOKS[ev] = HOOKS[ev] || []).push(fn); if (FIRED[ev]) safe('hook ' + ev, function () { fn(FIRED[ev].arg); }); return window.PS; },
  emit: function (ev, arg) { if (ev === 'ready') FIRED[ev] = { arg: arg }; (HOOKS[ev] || []).slice().forEach(function (fn) { safe('hook ' + ev, function () { fn(arg); }); }); },
  replace: function (name) { REPLACED[name] = 1; document.documentElement.setAttribute('data-ps-replaced', Object.keys(REPLACED).join(' ')); return window.PS; },
  isReplaced: function (name) { return !!REPLACED[name]; }, replaced: function () { return Object.keys(REPLACED); }
};
function emitPS(ev, arg) { if (window.PS && window.PS.emit) window.PS.emit(ev, arg); }

/* ---------- события ---------- */
document.addEventListener('click', function (e) {
  var t = e.target; if (!t || !t.closest) return;
  var pe = t.closest('svg[data-ps-chart] [data-ps-ref], svg[data-ps-chart] .ps-el'), pf = figOf(pe);
  if (pe && pf && pf.classList.contains('ps-ready')) { e.preventDefault(); selectEl(pf, pe.getAttribute('data-ps-ref') || pe.getAttribute('data-ps-el'), { focus: true }); return; }
  if (t.closest('[data-cp-close]')) { e.preventDefault(); closePanel(true); return; }
  var cs = t.closest('[data-cp-step]'); if (cs) { e.preventDefault(); stepEl(+cs.getAttribute('data-cp-step')); return; }
  var hb = t.closest('.ps-howto-btn'); if (hb) { e.preventDefault(); var hw = document.getElementById(hb.getAttribute('aria-controls')); if (hw) { hw.hidden = !hw.hidden; hb.setAttribute('aria-expanded', String(!hw.hidden)); } return; }
  var sg = t.closest('[data-st-go],[data-qf-go]'); if (sg) { e.preventDefault(); goRegistry(sg.getAttribute('data-st-go'), sg.getAttribute('data-qf-go')); return; }
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
  if (e.key === 'Escape') { if (top) { e.preventDefault(); closeLayer(top); } else if (CP.open) { e.preventDefault(); closePanel(true); } else if (document.body.classList.contains('nav-open')) toggleNav(false); return; }
  if (top === lb) {
    if (e.key === 'ArrowRight') { e.preventDefault(); lbStep(1); } else if (e.key === 'ArrowLeft') { e.preventDefault(); lbStep(-1); }
    else if (e.key === '+' || e.key === '=') zoomStep(1); else if (e.key === '-' || e.key === '_') zoomStep(-1); else if (e.key === '0') setZoom('fit');
    else if (e.key === 'h' || e.key === 'H' || e.key === 'р' || e.key === 'Р') lb.classList.toggle('nohs');
    return;
  }
  if (top) return;
  if (chartKeys(e)) return;
  if (e.key !== 'Enter' && e.key !== ' ') return;
  var el = document.activeElement; if (!el || !el.matches) return;
  if (el.matches('.lb[data-key]') && el.tagName !== 'BUTTON') { e.preventDefault(); openLB(el); }
  else if (el.matches('tr.row')) { e.preventDefault(); toggleRow(el.getAttribute('data-id')); }
  else if (el.matches('.grow[data-g]')) { e.preventDefault(); openGantt(+el.getAttribute('data-g')); }
  else if (el.matches('.kcard[data-k]')) { e.preventDefault(); openKanban(+el.getAttribute('data-k')); }
  else if (el.matches('.kcard[data-pid]')) { e.preventDefault(); openProposal(el.getAttribute('data-pid')); }
  else if (el.matches('.flowsvg [data-node]')) { e.preventDefault(); openNode(el.getAttribute('data-node')); }
});
function hashOpen() {
  var h = location.hash || '', m; try { h = decodeURIComponent(h); } catch (e) {}
  if ((m = h.match(/^#lb=(.+)$/))) {      /* #lb=c-<ключ> интерактивного графика — к самому графику (прежде это была картинка в лайтбоксе) */
    var ck = /^c-(.+)$/.exec(m[1]), el = ck && chartFig(ck[1]) ? null : lbFigs().filter(function (f) { return f.getAttribute('data-key') === m[1]; })[0];
    if (el) openLB(el); else go(h);
  }
  else if ((m = h.match(/^#p=(P\d{3})$/))) { if (BYID[m[1]]) openProposal(m[1]); }
  else go(h);
}
function chartKeys(e) {
  var a = document.activeElement; if (!a || !a.matches) return false;
  var onEl = a.matches('svg[data-ps-chart] .ps-el'), inCp = !!(cpEl && cpEl.contains(a));
  var d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
  if (d && !e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
    if (onEl) { e.preventDefault(); var fig = figOf(a); if (CP.open && CP.fig === fig) stepEl(d); else moveFocus(fig, a, d); return true; }
    if (inCp && CP.open && !/^(INPUT|SELECT|TEXTAREA)$/.test(a.tagName)) { e.preventDefault(); stepEl(d); return true; }
  }
  if ((e.key === 'Enter' || e.key === ' ') && onEl && figOf(a) && figOf(a).classList.contains('ps-ready')) { e.preventDefault(); selectEl(figOf(a), a.getAttribute('data-ps-el'), { focus: true }); return true; }
  return false;
}
/* ссылки роутера: свой переход (и запись в историю), без прокрутки браузера к несуществующему id */
document.addEventListener('click', function (e) {
  if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
  var a = e.target && e.target.closest && e.target.closest('a[href^="#"]'); if (!a) return;
  var h = a.getAttribute('href'), r = parseHref(h); if (!r || r.t === 'pcard' || r.t === 'lb' || (r.t === 'sec' && r.legacy) || r.bare) return;
  e.preventDefault();
  try { if (location.hash !== h) history.pushState(null, '', h); } catch (x) { /* file:// без history */ }
  go(h);
});
document.addEventListener('focusin', function (e) { var t = e.target; if (t && t.matches && t.matches('svg[data-ps-chart] .ps-el')) { focusRing(t); tipFocus(t); } });
document.addEventListener('focusout', function (e) { var t = e.target; if (t && t.matches && t.matches('svg[data-ps-chart] .ps-el')) { ring(t.ownerSVGElement, null, 'ps-foc'); if (cpTip && cpTip._focus) { cpTip.hidden = true; cpTip._focus = false; } } });
/* подсказка при наведении и фокусе — мгновенная, «название + первое предложение „что это“» (FB-035, п. 3); системный <title> снят */
function firstSent(s) { var w = String(s || ''), m = w.match(/^[\s\S]*?[.!?](?=\s|$)/); w = m ? m[0] : w; return w.length > 150 ? w.slice(0, 147) + '…' : w; }
function tipHtml(g) {
  var f = figOf(g); if (!g || !f || !f.classList.contains('ps-ready')) return null;
  var id = g.getAttribute('data-ps-ref') || g.getAttribute('data-ps-el'), key = f.getAttribute('data-chart'), i = chFind(key, id);
  if (i < 0) return g.getAttribute('data-tip') ? '<b>' + esc(g.getAttribute('data-tip')) + '</b>' : null;
  var e = chEls(key)[i], s = firstSent(e.summary);
  return '<b>' + esc(e.title || id) + '</b>' + (s ? '<span>' + esc(s) + '</span>' : '') + '<em>Нажмите — подробности</em>';
}
function tipFor(t) { var g = t && t.closest ? t.closest('svg[data-ps-chart] [data-ps-ref], svg[data-ps-chart] .ps-el') : null; return g ? tipHtml(g) : null; }
function tipPlace(html, x, y) {
  if (cpTip.getAttribute('data-h') !== html) { cpTip.innerHTML = html; cpTip.setAttribute('data-h', html); }
  cpTip.hidden = false; var w = cpTip.offsetWidth, hgt = cpTip.offsetHeight;
  cpTip.style.left = Math.max(4, Math.min(innerWidth - w - 4, x + 14)) + 'px';
  cpTip.style.top = Math.max(4, Math.min(innerHeight - hgt - 4, y - hgt - 12 < 4 ? y + 18 : y - hgt - 12)) + 'px';
}
function tipMove(e) {
  if (!cpTip) return; var html = e.pointerType === 'touch' ? null : tipFor(e.target);
  if (!html) { if (!cpTip.hidden && !cpTip._focus) cpTip.hidden = true; return; }
  cpTip._focus = false; tipPlace(html, e.clientX, e.clientY);
}
function tipFocus(el) {
  if (!cpTip) return; var kb = true; try { kb = el.matches(':focus-visible'); } catch (x) { /* старый движок */ }
  var html = kb ? tipHtml(el) : null; if (!html) return;
  var r = el.getBoundingClientRect(); cpTip._focus = true; tipPlace(html, r.left + Math.min(r.width / 2, 60), r.top);
}
document.addEventListener('pointermove', tipMove, { passive: true });
document.addEventListener('pointerover', tipMove, { passive: true });
document.addEventListener('pointerleave', function () { if (cpTip) cpTip.hidden = true; });
window.addEventListener('scroll', function () { if (cpTip && !cpTip.hidden) cpTip.hidden = true; }, { passive: true });

safe('images', function () { fillImgs(document); });
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
  $$('#registry [data-qf]').forEach(function (b) { b.addEventListener('click', function () { var v = b.getAttribute('data-qf'); setQF(QF === v ? '' : v); renderReg(); }); });
  $('#exp-csv').addEventListener('click', function () { exportRows('csv'); });
  $('#exp-json').addEventListener('click', function () { exportRows('json'); });
  renderReg();
  var onNarrow = function () { renderReg(); var id = pm.getAttribute('data-id'); if (id && pm.classList.contains('open')) { var b = $('#pmbody'); b.innerHTML = detail(BYID[id]); fillImgs(b); linkifyEl(b); } };
  if (NARROW.addEventListener) NARROW.addEventListener('change', onNarrow); else if (NARROW.addListener) NARROW.addListener(onNarrow);
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
  var lt = $('#lbtheme'); if (lt) lt.addEventListener('click', lbTheme);
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
safe('print', function () { window.addEventListener('beforeprint', function () { $$('details').forEach(function (d) { d.open = true; }); fillImgs(document); $$('img[data-full="0"]').forEach(function (im) { im.src = IMG[im.getAttribute('data-img')]; im.setAttribute('data-full', '1'); }); }); });
safe('charts', function () {
  mountAll();                                                     /* single/lite: SVG уже в разметке */
  var boxes = $$('.ps-svg[data-ps-src]'); if (!boxes.length) return;
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (es) { es.forEach(function (en) { if (en.isIntersecting) { io.unobserve(en.target); loadSrc(en.target.getAttribute('data-ps-src')); } }); }, { rootMargin: '900px 0px' });
    boxes.forEach(function (b) { io.observe(b); });
  } else loadAllCharts();
  window.addEventListener('beforeprint', function () { loadAllCharts(); });
});
safe('hash', function () { window.addEventListener('hashchange', hashOpen); hashOpen(); });
emitPS('ready', { version: '1.5' });
})();
"""


# ---------------------------------------------------------------- открытые данные рядом со страницей (режим site)
def csv_cell(v):
    """Ячейка CSV: списки — через « | », словари — «ключ=значение; …»; текст, похожий на формулу (= + - @), экранируется апострофом."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return "" if not math.isfinite(v) else repr(v)
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        t = " | ".join(x for x in (csv_cell(i) for i in v) if x != "")
    elif isinstance(v, dict):
        t = "; ".join("%s=%s" % (k, csv_cell(x)) for k, x in v.items() if x not in (None, ""))
    else:
        t = str(v)
    if t[:1] in ("=", "+", "@", "\t", "\r") or (t[:1] == "-" and not re.match(r"^-?\d+([.,]\d+)?$", t)):
        t = "'" + t
    return t


def csv_bytes(rows, cols):
    import csv
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([c for c, _ in cols])
    for r in rows:
        w.writerow([csv_cell(f(r)) for _, f in cols])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")        # BOM — чтобы Excel узнал UTF-8


def _union_cols(rows, skip=()):
    keys = []
    for r in rows:
        for k in r:
            if k not in keys and k not in skip:
                keys.append(k)
    return [(k, (lambda r, k=k: r.get(k))) for k in keys]


def _range(v, i):
    return v[i] if isinstance(v, (list, tuple)) and len(v) > i else None


def open_data(out, warn):
    """Открытые данные для людей и импорта: {путь относительно папки страницы → байты}. Страница от них не зависит.
    proposals.json — копия исходного реестра; CSV — плоские таблицы (proposals, scores, competitors, gantt, kanban, sources)."""
    data = Path(out) / "data"
    res = {}

    def load(name):
        f = data / name
        if not f.is_file():
            return None
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            warn("открытые данные: не прочитать data/%s (%s)" % (name, str(e)[:80]))
            return None
    f = data / "proposals.json"
    props = load("proposals.json")
    if isinstance(props, list):
        res["data/proposals.json"] = f.read_bytes()
        cols = [("id", lambda r: r.get("id")), ("title", lambda r: r.get("title")), ("category", lambda r: r.get("category")),
                ("segment", lambda r: r.get("segment")), ("description", lambda r: r.get("description")),
                ("rationale", lambda r: r.get("rationale")), ("evidence_class", lambda r: r.get("evidence_class")),
                ("horizon", lambda r: r.get("horizon")), ("kano", lambda r: r.get("kano")),
                ("effort_days_min", lambda r: _range(r.get("effort_days"), 0)), ("effort_days_max", lambda r: _range(r.get("effort_days"), 1)),
                ("time_to_first_result_days", lambda r: r.get("time_to_first_result_days")), ("cheap_test", lambda r: r.get("cheap_test")),
                ("current_feature", lambda r: r.get("current_feature")),
                ("steps", lambda r: [x.get("what") if isinstance(x, dict) else x for x in (r.get("steps") or [])]),
                ("dependencies", lambda r: r.get("dependencies")),
                ("effect_kpi", lambda r: [("%s %s %s" % (x.get("kpi"), x.get("range") or "", ("[" + str(x["label"]) + "]") if x.get("label") else "")).strip()
                                           if isinstance(x, dict) else x for x in (r.get("effect_kpi") or [])]),
                ("evidence_urls", lambda r: [x.get("url") for x in (r.get("evidence") or []) if isinstance(x, dict) and x.get("url")]),
                ("tags", lambda r: r.get("tags")), ("mockup", lambda r: r.get("mockup")), ("merged_from", lambda r: r.get("merged_from"))]
        sc = []
        for k in ("value", "cost", "risk", "confidence", "reach", "impact"):
            sc.append(("score_" + k, lambda r, k=k: (r.get("scores") or {}).get(k) if isinstance(r.get("scores"), dict) else None))
        res["data/proposals.csv"] = csv_bytes([r for r in props if isinstance(r, dict)], cols + sc)
    f = data / "scores.csv"
    if f.is_file():
        res["data/scores.csv"] = f.read_bytes()
    else:
        sc = load("scores.json")
        if isinstance(sc, list) and sc and all(isinstance(r, dict) for r in sc):
            res["data/scores.csv"] = csv_bytes(sc, _union_cols(sc))
    comp = load("competitors.json")
    if isinstance(comp, dict):
        comp = comp.get("competitors")
    if isinstance(comp, list) and comp and all(isinstance(r, dict) for r in comp):
        res["data/competitors.csv"] = csv_bytes(comp, _union_cols(comp, skip=("features_labels",)))
    for name in ("gantt", "sources"):
        rows = load(name + ".json")
        if isinstance(rows, dict):
            rows = rows.get("tasks") if name == "gantt" else rows.get("sources")
        if isinstance(rows, list) and rows and all(isinstance(r, dict) for r in rows):
            res["data/%s.csv" % name] = csv_bytes(rows, _union_cols(rows))
    kb = load("kanban.json")
    cards = kb.get("cards") if isinstance(kb, dict) else kb
    if isinstance(cards, list) and cards and all(isinstance(r, dict) for r in cards):
        res["data/kanban.csv"] = csv_bytes(cards, _union_cols(cards))
    return res


def make_zip(page_dir, page_name, rels):
    """strategy-site.zip: страница и перечисленные файлы сайта (без самого архива и служебных манифестов)."""
    import zipfile
    zp = Path(page_dir) / ZIP_NAME
    names = sorted({page_name, *rels} - {ZIP_NAME})
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in names:
            f = Path(page_dir) / rel
            if f.is_file() and not Path(rel).name.startswith("."):
                z.write(f, rel)
    return zp


# ---------------------------------------------------------------- точка входа
def human(n):
    return "%.1f КБ" % (n / 1024.0) if n < 1048576 else "%.2f МБ" % (n / 1048576.0)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Сборка интерактивной офлайн-страницы стратегии (по умолчанию — сайт deliverables/index.html + assets/ + data/).")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--out", dest="out_file", help="куда записать страницу (по умолчанию <OUT>/deliverables/index.html)")
    ap.add_argument("--title", help="заголовок страницы (по умолчанию — H1 из research/strategy.md или имя продукта)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--site", action="store_true",
                   help="режим по умолчанию: оболочка index.html + assets/ (app.css, app.js, data.js, img/) + data/ (открытые CSV/JSON); "
                        "работает по двойному клику (file://)")
    g.add_argument("--single", action="store_true",
                   help="прежний автономный файл: CSS, JS, данные и картинки внутри index.html (Artifact ≤ 16 МБ, пересылка одним файлом)")
    g.add_argument("--lite", action="store_true",
                   help="single, но крупные картинки — файлами в <папка страницы>/assets/ (WebP при наличии Pillow/ffmpeg), в странице — "
                        "ссылки и миниатюры ≤ 320 px; цель — страница ≤ 8 МБ")
    ap.add_argument("--lite-encoder", choices=["auto", "pillow", "ffmpeg", "none"], default="auto",
                    help="кодировщик картинок для --lite и site: auto (Pillow → ffmpeg → как есть), pillow, ffmpeg, none (без перекодирования)")
    ap.add_argument("--site-csp", choices=["self", "none"], default="self",
                    help="CSP режима site: self (default-src 'none'; script-src 'self'…) или none — запасной вариант без CSP-мета "
                         "(если браузер не принимает 'self' на file://; внешних запросов всё равно нет)")
    ap.add_argument("--zip", action="store_true", help="режим site: собрать <папка страницы>/strategy-site.zip (страница + assets/ + data/)")
    ap.add_argument("--strict", action="store_true",
                    help="ссылка из пояснений графиков (charts/<ключ>.meta.json) без цели на странице — ошибка (код выхода 1); "
                         "без флага — предупреждение, ссылка не показывается")
    a = ap.parse_args(argv)
    out = Path(a.out).expanduser()
    if not out.is_dir():
        print("нет папки прогона: %s" % out, file=sys.stderr)
        return 2
    site = not (a.single or a.lite)
    mode = "site" if site else "lite" if a.lite else "single"
    out_file = Path(a.out_file).expanduser() if a.out_file else out / "deliverables" / "index.html"
    out_file = out_file.resolve()
    b = Builder(out, out_file, a.title, lite=a.lite, lite_encoder=a.lite_encoder, site=site, site_csp=a.site_csp)
    page = b.build_all()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(page, encoding="utf-8")
    pdir = out_file.parent
    dropped = 0
    produced = {}                                  # путь относительно папки страницы → размер (файлы режима site)
    zip_path = None
    if site:
        for rel, blob in b.site_files.items():
            f = pdir / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(blob)
            produced[rel] = len(blob)
        produced.update(b.lite.written)
        od = open_data(out, b.warn)
        for rel, blob in od.items():
            f = pdir / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(blob)
            produced[rel] = len(blob)
        dropped = drop_stale_assets(pdir)          # хвосты прошлой --lite-сборки
        dropped += cleanup_previous(pdir, set(produced) | ({ZIP_NAME} if a.zip else set()))
        if a.zip:
            zip_path = make_zip(pdir, out_file.name, list(produced))
            produced[ZIP_NAME] = zip_path.stat().st_size
        write_site_manifest(pdir, list(produced))
    else:
        if b.lite:
            b.lite.finish()
            dropped = cleanup_previous(pdir, {"assets/" + n for n in b.lite.written})
        else:
            dropped = drop_stale_assets(pdir) + cleanup_previous(pdir, set())
        write_site_manifest(pdir, [])
        if a.zip:
            print("--zip: архив собирается только в режиме site — пропущено", file=sys.stderr)
    size = out_file.stat().st_size
    img_total = sum(m["bytes"] for m in b.img.meta.values())
    print("Готово: %s" % out_file)
    if site:
        n_img = len([m for m in b.img.meta.values() if m.get("asset")])
        assets_bytes = sum(v for k, v in produced.items() if k.startswith("assets/"))
        data_bytes = sum(v for k, v in produced.items() if k.startswith("data/"))
        total = size + assets_bytes + data_bytes
        core = {k: v for k, v in produced.items() if k in ("assets/app.css", "assets/app.js", "assets/data.js", "assets/head.js",
                                                           "assets/extra.css", "assets/extra.js", "assets/search-docs.js")
                or re.fullmatch(r"assets/charts-[\w-]+\.js", k) or k.startswith("assets/extra/")}
        print("Режим site (кодировщик: %s; CSP: %s)" % (b.lite.enc.label(), "'self'" if a.site_csp == "self" else "нет (запасной вариант --site-csp none)"))
        print("  index.html: %s (оболочка без данных)" % human(size))
        print("  assets/: %s — %s; картинок-файлов: %d (%s), миниатюр: %d (%s), повторов по содержимому: %d"
              % (human(assets_bytes), ", ".join("%s %s" % (Path(k).name, human(v)) for k, v in core.items()), n_img,
                 human(sum(v for k, v in produced.items() if k.startswith("assets/img/") and "/thumbs/" not in k)),
                 len(b.img.thumbs), human(b.lite.thumb_bytes), len(b.img.alias)))
        print("  data/: %d файлов (%s): %s" % (len([k for k in produced if k.startswith("data/")]), human(data_bytes),
                                              ", ".join(sorted(Path(k).name for k in produced if k.startswith("data/")))))
        print("Размер сайта: %s (index.html %s + assets/ %s + data/ %s); откройте %s двойным кликом, пересылайте папку %s целиком"
              % (human(total), human(size), human(assets_bytes), human(data_bytes), out_file.name, pdir))
        if zip_path:
            print("Архив: %s (%s)" % (zip_path, human(zip_path.stat().st_size)))
        if dropped:
            print("Удалены файлы прошлой сборки другого режима: %d" % dropped)
        if size > 1048576:
            print("ВНИМАНИЕ: index.html %s — больше 1 МБ без данных: проверьте объём research/strategy.md и встроенных SVG" % human(size))
        if total > 25 * 1048576:
            print("СОВЕТ: сайт %s — больше 25 МБ: перекодируйте картинки в WebP (установите Pillow или ffmpeg) и уменьшите скриншоты; "
                  "для пересылки одним файлом — --single" % human(total))
    elif b.lite:
        n_assets = len([m for m in b.img.meta.values() if m.get("asset")])
        n_alias = len(b.img.alias)
        a_bytes = sum(b.lite.written.values())
        print("Режим --lite (%s): в assets/ — %d файлов (%s), миниатюр в странице: %d (%s), встроено как есть: %d, повторов по содержимому: %d"
              % (b.lite.enc.label(), n_assets, human(a_bytes), len(b.img.thumbs), human(b.lite.thumb_bytes), len(b.img.map) - n_assets, n_alias))
        print("Размер страницы: %s (+ assets/ %s); пересылайте страницу вместе с папкой %s" % (human(size), human(a_bytes), out_file.parent / "assets"))
        if dropped:
            print("Удалены файлы прошлой сборки другого режима: %d" % dropped)
    else:
        print("Размер страницы: %s; встроенных картинок: %d (%s)%s" % (human(size), len(b.img.map), human(img_total),
              ("; повторов по содержимому (встроены один раз): %d" % len(b.img.alias)) if b.img.alias else ""))
        if dropped:
            print("Удалены файлы прошлой сборки другого режима (assets/, data/): %d" % dropped)
    print("Разделы (%d): %s" % (len(b.nav), ", ".join(sid for sid, _, _ in b.nav)))
    print("Слои страницы: увеличение графиков и схем — кнопок %d, строк-подсказок %d; поиск по странице%s; глоссарий — терминов %d; "
          "подсказок элементов макетов %d" % (page.count('class="psi-zoom"'), page.count('class="psi-hint"'),
                                              " (+ исследований: %d)" % len(b.docs) if b.docs else "", len(b.gloss), getattr(b, "mock_hs_count", 0)))
    if b.extra:
        print("Расширения страницы (хуки): %s%s" % (", ".join(rel for rel, _, _ in b.extra), "" if site else " — встроены в страницу"))
    ich = b.chart_page_meta
    if ich or b.charts:
        n_el = sum(len(m["elements"]) for m in ich.values())
        print("Графики: интерактивных %d (элементов %d, ссылок в пояснениях %d, без цели — %d), статичных %d"
              % (len(ich), n_el, b.chart_link_total, sum(b.chart_link_drops.values()), len([c for c in b.charts if c.get("img")])))
    print("Реестр: %d предложений; фигур: %d; ссылок на предложения: %d" % (len(b.rows), b.figs, page.count('class="pid"')))
    heavy = sorted(b.img.meta.items(), key=lambda kv: -(kv[1]["bytes"] + kv[1].get("asset_bytes", 0)))[:10]
    if heavy:
        print("Топ-10 самых тяжёлых вложений:")
        for i, (k, m) in enumerate(heavy, 1):
            if m.get("asset"):
                print("  %2d. %10s  %s  (%s → %s, миниатюра %s)" % (i, human(m["asset_bytes"]), k, m["src"], m["asset"], human(m["bytes"])))
            else:
                print("  %2d. %10s  %s  (%s)" % (i, human(m["bytes"]), k, m["src"]))
    if mode == "single" and size > 12 * 1048576:
        print("ВНИМАНИЕ: страница %s — больше 12 МБ (медленно открывается, близко к лимиту публикации 16 МБ); "
              "соберите сайт (по умолчанию) или --lite: build_html.py %s" % (human(size), out))
    elif mode == "lite" and size > 8 * 1048576:
        print("ВНИМАНИЕ: страница --lite всё ещё %s (> 8 МБ): проверьте самые тяжёлые вложения выше и объём data/*.json" % human(size))
    if b.warnings:
        print("Предупреждения (%d):" % len(b.warnings))
        for w in b.warnings:
            print("  - " + w)
    if a.strict and b.strict_errors:
        print("ОШИБКА (--strict): " + "; ".join(b.strict_errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
