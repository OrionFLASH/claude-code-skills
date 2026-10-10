#!/usr/bin/env python3
"""Сборка <OUT>/deliverables/strategy.xlsx на чистой стандартной библиотеке.

Листы: «Реестр» (все поля плоско), «Оценки» (шкалы, редактируемые веса и формулы SUMPRODUCT /
нормализация / RANK — после правки весов Excel пересчитывает ранги), «Модель» (сценарии из
data/model.json), «Источники», «KPI», «Kanban», «Конкуренты», «Гант».
Свойства документа (creator / title / description) — из build/run-config.json → author.

Необязательные входы (scores.json, weights.json, model.json, links-check.csv) используются, если есть.

  build_xlsx.py <OUT>

Свой минимальный OOXML-писатель: zipfile + sharedStrings, стили заголовков, ширины колонок,
закреплённые строки, автофильтр. Схемы входных файлов — references/data-contract.md.
"""
import argparse
import csv
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

CATS = {"product": "Продукт", "acquisition": "Привлечение", "conversion": "Конверсия", "retention": "Удержание",
        "monetization": "Монетизация", "analytics": "Аналитика", "partnerships": "Партнёрства",
        "localization": "Локализация", "new_lines": "Новые линии", "platform": "Платформа"}
SUBSCALES = ["reach", "impact", "acquisition", "activation", "conversion", "retention", "revenue",
             "virality", "seo", "trust", "moat", "fit", "demand", "season"]
DEFAULT_COMPOSITE = {"rice": 0.30, "ice": 0.20, "wsjf": 0.25, "risk_adj": 0.25}
MAX_CELL = 32000  # предел Excel — 32767 знаков в ячейке
_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


# ---------------------------------------------------------------- минимальный OOXML-писатель
class F(str):
    """Формула Excel (без ведущего «=»)."""


# индексы стилей cellXfs (см. _styles_xml)
ST_DEFAULT, ST_HEAD, ST_WRAP, ST_EDIT, ST_TITLE, ST_NUM3, ST_NOTE, ST_BAR, ST_MILE, ST_INT = range(10)


def col_letter(n):
    """1 → A, 27 → AA."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def ref(r, c, abs_=False):
    if abs_:
        return "$%s$%d" % (col_letter(c), r)
    return "%s%d" % (col_letter(c), r)


class Sheet:
    def __init__(self, name):
        self.name = name[:31]
        self.cells = {}          # (row, col) -> (value, style)
        self.widths = {}
        self.freeze = None       # (row, col): первая незакреплённая ячейка
        self.autofilter = None   # "A1:D10"
        self.merges = []

    def set(self, r, c, v, style=None):
        if v is None:
            return
        if style is None:
            style = ST_WRAP if isinstance(v, str) and not isinstance(v, F) and ("\n" in v or len(v) > 60) else ST_DEFAULT
        self.cells[(r, c)] = (v, style)

    def row(self, r, values, style=None, start=1):
        for i, v in enumerate(values):
            self.set(r, start + i, v, style)

    def header(self, r, names, freeze_col=1):
        self.row(r, names, ST_HEAD)
        self.freeze = (r + 1, freeze_col)

    def width(self, widths, start=1):
        for i, w in enumerate(widths):
            self.widths[start + i] = w

    @property
    def max_rc(self):
        if not self.cells:
            return 1, 1
        return max(r for r, _ in self.cells), max(c for _, c in self.cells)


class Workbook:
    def __init__(self):
        self.sheets = []
        self.strings = []
        self._sidx = {}
        self.props = {"creator": "", "title": "", "description": ""}

    def add(self, name):
        s = Sheet(name)
        self.sheets.append(s)
        return s

    def _si(self, text):
        if text not in self._sidx:
            self._sidx[text] = len(self.strings)
            self.strings.append(text)
        return self._sidx[text]

    @staticmethod
    def _clean(text):
        text = _BAD_XML.sub("", str(text))
        return text if len(text) <= MAX_CELL else text[:MAX_CELL - 1] + "…"

    def _cell_xml(self, r, c, v, st):
        a = ref(r, c)
        s = ' s="%d"' % st if st else ""
        if isinstance(v, F):
            return '<c r="%s"%s><f>%s</f></c>' % (a, s, escape(self._clean(v)))
        if isinstance(v, bool):
            return '<c r="%s"%s t="b"><v>%d</v></c>' % (a, s, int(v))
        if isinstance(v, (int, float)):
            if v != v or v in (float("inf"), float("-inf")):
                return '<c r="%s"%s t="inlineStr"><is><t>%s</t></is></c>' % (a, s, "н/д")
            return '<c r="%s"%s><v>%s</v></c>' % (a, s, repr(v) if isinstance(v, float) else v)
        idx = self._si(self._clean(v))
        return '<c r="%s"%s t="s"><v>%d</v></c>' % (a, s, idx)

    def _sheet_xml(self, sh):
        mr, mc = sh.max_rc
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
               'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
               '<dimension ref="A1:%s"/>' % ref(mr, mc)]
        if sh.freeze and (sh.freeze[0] > 1 or sh.freeze[1] > 1):
            fr, fc = sh.freeze
            xs, ys = fc - 1, fr - 1
            pane = "bottomRight" if xs and ys else ("bottomLeft" if ys else "topRight")
            attrs = (' xSplit="%d"' % xs if xs else "") + (' ySplit="%d"' % ys if ys else "")
            out.append('<sheetViews><sheetView workbookViewId="0"%s><pane%s topLeftCell="%s" activePane="%s" state="frozen"/>'
                       '<selection pane="%s" activeCell="%s" sqref="%s"/></sheetView></sheetViews>'
                       % (' tabSelected="1"' if sh is self.sheets[0] else "", attrs, ref(fr, fc), pane, pane, ref(fr, fc), ref(fr, fc)))
        else:
            out.append('<sheetViews><sheetView workbookViewId="0"%s/></sheetViews>' % (' tabSelected="1"' if sh is self.sheets[0] else ""))
        out.append('<sheetFormatPr defaultRowHeight="15"/>')
        if sh.widths:
            out.append("<cols>" + "".join('<col min="%d" max="%d" width="%s" customWidth="1"/>' % (c, c, w)
                                          for c, w in sorted(sh.widths.items())) + "</cols>")
        out.append("<sheetData>")
        rows = {}
        for (r, c), (v, st) in sh.cells.items():
            rows.setdefault(r, []).append((c, v, st))
        for r in sorted(rows):
            out.append('<row r="%d">' % r + "".join(self._cell_xml(r, c, v, st) for c, v, st in sorted(rows[r], key=lambda x: x[0])) + "</row>")
        out.append("</sheetData>")
        if sh.autofilter:
            out.append('<autoFilter ref="%s"/>' % sh.autofilter)
        if sh.merges:
            out.append('<mergeCells count="%d">' % len(sh.merges) + "".join('<mergeCell ref="%s"/>' % m for m in sh.merges) + "</mergeCells>")
        out.append('<pageMargins left="0.5" right="0.5" top="0.6" bottom="0.6" header="0.3" footer="0.3"/></worksheet>')
        return "".join(out)

    @staticmethod
    def _styles_xml():
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<numFmts count="1"><numFmt numFmtId="164" formatCode="0.000"/></numFmts>'
                '<fonts count="4">'
                '<font><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
                '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font>'
                '<font><b/><sz val="13"/><color rgb="FF1F3A5F"/><name val="Calibri"/><family val="2"/></font>'
                '<font><i/><sz val="9"/><color rgb="FF666666"/><name val="Calibri"/><family val="2"/></font>'
                '</fonts>'
                '<fills count="6"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
                '<fill><patternFill patternType="solid"><fgColor rgb="FF1F3A5F"/><bgColor indexed="64"/></patternFill></fill>'
                '<fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/><bgColor indexed="64"/></patternFill></fill>'
                '<fill><patternFill patternType="solid"><fgColor rgb="FF4F81BD"/><bgColor indexed="64"/></patternFill></fill>'
                '<fill><patternFill patternType="solid"><fgColor rgb="FFF5A623"/><bgColor indexed="64"/></patternFill></fill>'
                '</fills>'
                '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
                '<border><left style="thin"><color rgb="FFBFBFBF"/></left><right style="thin"><color rgb="FFBFBFBF"/></right>'
                '<top style="thin"><color rgb="FFBFBFBF"/></top><bottom style="thin"><color rgb="FFBFBFBF"/></bottom><diagonal/></border></borders>'
                '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                '<cellXfs count="10">'
                '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
                '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
                '<alignment vertical="top" wrapText="1"/></xf>'
                '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
                '<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1"/>'
                '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
                '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
                '<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
                '<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1"/>'
                '<xf numFmtId="0" fontId="0" fillId="5" borderId="1" xfId="0" applyFill="1" applyBorder="1"/>'
                '<xf numFmtId="1" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
                '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
                '</styleSheet>')

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        sheet_xml = [self._sheet_xml(s) for s in self.sheets]  # до sharedStrings: наполняет таблицу строк
        n = len(self.sheets)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
              + "".join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1) for i in range(n))
              + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
              '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
              '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
              '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
              '</Types>')
        rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
                '</Relationships>')
        defined = []
        for i, s in enumerate(self.sheets):
            if s.autofilter:
                a, b = s.autofilter.split(":")
                fix = lambda x: re.sub(r"([A-Z]+)(\d+)", r"$\1$\2", x)
                defined.append('<definedName name="_xlnm._FilterDatabase" localSheetId="%d" hidden="1">\'%s\'!%s:%s</definedName>'
                               % (i, escape(s.name.replace("'", "''")), fix(a), fix(b)))
        wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
              '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
              'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
              '<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="28800" windowHeight="16000"/></bookViews><sheets>'
              + "".join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(s.name, {'"': "&quot;"}), i + 1, i + 1) for i, s in enumerate(self.sheets))
              + "</sheets>" + ("<definedNames>%s</definedNames>" % "".join(defined) if defined else "")
              + '<calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>')
        wb_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1) for i in range(n))
                   + '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' % (n + 1)
                   + '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>' % (n + 2)
                   + "</Relationships>")
        sst = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="%d" uniqueCount="%d">' % (len(self.strings), len(self.strings))
               + "".join('<si><t xml:space="preserve">%s</t></si>' % escape(t) for t in self.strings) + "</sst>")
        p = {k: escape(self._clean(v)) for k, v in self.props.items()}
        core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
                'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                '<dc:title>%s</dc:title><dc:creator>%s</dc:creator><cp:lastModifiedBy>%s</cp:lastModifiedBy><dc:description>%s</dc:description>'
                '<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified>'
                '</cp:coreProperties>') % (p["title"], p["creator"], p["creator"], p["description"], now, now)
        app = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
               'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>product-strategy build_xlsx.py</Application>'
               '<TitlesOfParts><vt:vector size="%d" baseType="lpstr">%s</vt:vector></TitlesOfParts></Properties>'
               % (n, "".join("<vt:lpstr>%s</vt:lpstr>" % escape(s.name) for s in self.sheets)))
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", ct)
            z.writestr("_rels/.rels", rels)
            z.writestr("docProps/core.xml", core)
            z.writestr("docProps/app.xml", app)
            z.writestr("xl/workbook.xml", wb)
            z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
            z.writestr("xl/styles.xml", self._styles_xml())
            z.writestr("xl/sharedStrings.xml", sst)
            for i, x in enumerate(sheet_xml):
                z.writestr("xl/worksheets/sheet%d.xml" % (i + 1), x)
        return path


# ---------------------------------------------------------------- чтение данных
def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as e:
        print("предупреждение: не удалось прочитать %s: %s" % (path, e), file=sys.stderr)
        return default


def author_line(cfg):
    a = cfg.get("author") or {}
    name, nick = a.get("name") or "", a.get("nick") or ""
    return (name + (" (%s)" % nick if nick else "")).strip() or nick, a.get("copyright") or ""


def product_name(cfg):
    return (cfg.get("product") or {}).get("name") or (cfg.get("repo") or {}).get("name") or "продукт"


def j(v):
    """Плоское текстовое представление любого значения для ячейки."""
    if v is None:
        return ""
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, list):
        return "\n".join(str(j(x)) for x in v)
    if isinstance(v, dict):
        return "; ".join("%s: %s" % (k, j(x)) for k, x in v.items() if x not in (None, "", [], {}))
    return str(v)


def fmt_evidence(ev):
    out = []
    for e in ev or []:
        loc = e.get("url") or e.get("file") or ""
        out.append("[%s] %s%s%s" % (e.get("kind", ""), e.get("title", ""), (" — " + loc) if loc else "",
                                     (" «%s»" % e["note"]) if e.get("note") else ""))
    return "\n".join(out)


def fmt_steps(steps):
    out = []
    for i, s in enumerate(steps or [], 1):
        line = "%d. %s" % (i, s.get("what", ""))
        if s.get("where"):
            line += " — " + s["where"]
        if s.get("how"):
            line += ": " + s["how"]
        if s.get("doc_url"):
            line += " (%s)" % s["doc_url"]
        out.append(line)
    return "\n".join(out)


def fmt_kpi(kpis):
    if isinstance(kpis, str):
        return kpis
    return "\n".join("%s %s %s [%s]" % (k.get("kpi", ""), {"up": "↑", "down": "↓"}.get(k.get("direction"), k.get("direction", "")),
                                        k.get("range", ""), k.get("label", "")) for k in kpis or [])


def fmt_money(m):
    if not isinstance(m, dict):
        return j(m)
    s = "%s–%s %s" % (m.get("min", ""), m.get("max", ""), m.get("currency", ""))
    return s + (": " + m["note"] if m.get("note") else "")


def score_val(p, key):
    sc = p.get("scores") or {}
    v = sc.get(key)
    if isinstance(v, dict):  # допускаем вложенные структуры старых реестров
        v = v.get("value")
    if v is None and key in SUBSCALES:
        v = sc.get("value")
    if isinstance(v, (int, float)):
        return v
    return None


def composite_weights(weights):
    """Веса композита из data/weights.json, если структура узнаваема; иначе по умолчанию."""
    cand = None
    if isinstance(weights, dict):
        for k in ("composite", "weights"):
            v = weights.get(k)
            if isinstance(v, dict):
                cand = v.get("composite") if isinstance(v.get("composite"), dict) else v
                break
    out = dict(DEFAULT_COMPOSITE)
    src = "по умолчанию"
    if isinstance(cand, dict):
        found = {k: float(cand[k]) for k in DEFAULT_COMPOSITE if isinstance(cand.get(k), (int, float))}
        if found:
            out.update(found)
            src = "data/weights.json"
    return out, src


def value_weights(weights):
    out = {"value": 1.0, **{k: 0.0 for k in SUBSCALES}}
    if isinstance(weights, dict) and isinstance(weights.get("value"), dict):
        for k, v in weights["value"].items():
            if k in out and isinstance(v, (int, float)):
                out[k] = float(v)
    return out


# ---------------------------------------------------------------- листы
def sheet_registry(wb, props, scores):
    sh = wb.add("Реестр")
    score_keys = ["value", "cost", "risk", "confidence"] + SUBSCALES
    cols = (["Ранг", "ID", "Название", "Категория", "Сегмент", "Описание", "Обоснование", "Доказательства", "Класс доказательства",
             "Текущая функция", "Эффект и KPI", "Шаги", "Зависимости", "Трудозатраты, дн. мин", "Трудозатраты, дн. макс", "Деньги",
             "Риски", "Дней до первого результата", "Дешёвая проверка"]
            + ["s.%s" % k for k in score_keys]
            + ["Кано", "Горизонт", "Горизонт, лет", "Теги", "Макет", "Группа", "Объединено из",
               "Composite", "RICE", "ICE", "WSJF", "Квадрант", "Приоритет", "MoSCoW", "Метки", "TypeSafe"])
    sh.header(1, cols, freeze_col=4)
    for r, p in enumerate(props, 2):
        s = scores.get(p.get("id"), {})
        ed = p.get("effort_days") or [None, None]
        vals = ([s.get("rank"), p.get("id"), p.get("title"), CATS.get(p.get("category"), p.get("category")), p.get("segment"),
                 p.get("description"), p.get("rationale"), fmt_evidence(p.get("evidence")), p.get("evidence_class"),
                 p.get("current_feature"), fmt_kpi(p.get("effect_kpi")), fmt_steps(p.get("steps")), ", ".join(p.get("dependencies") or []),
                 ed[0] if len(ed) > 0 else None, ed[1] if len(ed) > 1 else None, fmt_money(p.get("cost_money")), j(p.get("risks")),
                 p.get("time_to_first_result_days"), p.get("cheap_test")]
                + [score_val(p, k) for k in score_keys]
                + [p.get("kano"), p.get("horizon"), p.get("horizon_years"), ", ".join(p.get("tags") or []), p.get("mockup"),
                   p.get("source_group"), ", ".join(p.get("merged_from") or []),
                   s.get("composite"), s.get("rice"), s.get("ice"), s.get("wsjf"), s.get("quadrant"), s.get("priority"), s.get("moscow"),
                   ", ".join(s.get("labels") or []), j(s.get("typesafe")) if s.get("typesafe") else ("" if not s else "нет данных")])
        for c, v in enumerate(vals, 1):
            sh.set(r, c, j(v) if isinstance(v, (list, dict)) else v, ST_WRAP if isinstance(v, str) else None)
    widths = [6, 7, 38, 14, 18, 50, 44, 50, 8, 30, 30, 50, 12, 9, 9, 22, 30, 10, 36] + [6] * len(score_keys) + \
             [10, 9, 7, 16, 24, 7, 14, 9, 8, 8, 8, 11, 8, 8, 22, 18]
    sh.width(widths)
    sh.autofilter = "A1:%s" % ref(len(props) + 1, len(cols))
    return sh


def sheet_scores(wb, props, scores, weights):
    """Оценки: блок весов (строки 1–4), данные с заголовком в строке HR и формулами."""
    sh = wb.add("Оценки")
    cw, cw_src = composite_weights(weights)
    vw = value_weights(weights)
    vkeys = ["value"] + SUBSCALES
    sh.set(1, 1, "Веса — жёлтые ячейки редактируемые; после правки Excel пересчитает индексы и ранги (источник весов композита: %s)" % cw_src, ST_TITLE)
    HR = 6  # заголовок данных ниже блока весов — не пересекается с ним
    base = ["ID", "Название", "Категория", "Класс", "effort_mid", "cost", "risk", "confidence"]
    calc = ["value_index", "RICE", "ICE", "WSJF", "risk_adj", "n_RICE", "n_ICE", "n_WSJF", "n_risk_adj", "composite", "Ранг (формула)"]
    tail = ["Ранг (скрипт)", "Composite (скрипт)", "Приоритет", "Квадрант"]
    head = base + vkeys + calc + tail
    col = {h: i for i, h in enumerate(head, 1)}
    # блок весов: строка 2 — подписи, строка 3 — значения; каждый вес стоит над своей колонкой
    WROW_L, WROW = 2, 3
    wpos = {}
    for k in vkeys:
        wpos["w." + k] = (col[k], vw[k])
    for k, m in (("rice", "RICE"), ("ice", "ICE"), ("wsjf", "WSJF"), ("risk_adj", "risk_adj")):
        wpos["w." + k] = (col["n_" + m], cw[k])
    for lab, (c, val) in wpos.items():
        sh.set(WROW_L, c, lab, ST_NOTE)
        sh.set(WROW, c, val, ST_EDIT)
    sh.set(WROW, 1, "Веса →", ST_HEAD)
    wcol = {lab: c for lab, (c, _) in wpos.items()}
    sh.set(4, 1, ("value_index = SUMPRODUCT(шкалы ценности; веса)/SUM(веса). RICE = reach·impact·(confidence/5)/max(effort_mid; 0,5). "
                  "ICE = impact·confidence·(6−cost). WSJF = (value_index + season + moat)/cost. risk_adj = value_index·(1−(risk−1)/8). "
                  "n_* — нормализация min–max по колонке; composite = Σ w·n_*; ранг — RANK(composite)."), ST_DEFAULT)
    sh.header(HR, head, freeze_col=3)
    n = len(props)
    first, last = HR + 1, HR + max(n, 1)
    rng = lambda name: "%s:%s" % (ref(first, col[name], True), ref(last, col[name], True))
    v0, v1 = col[vkeys[0]], col[vkeys[-1]]
    w0, w1 = ref(WROW, wcol["w." + vkeys[0]], True), ref(WROW, wcol["w." + vkeys[-1]], True)
    for r, p in enumerate(props, first):
        ed = p.get("effort_days") or [1, 1]
        mid = (float(ed[0]) + float(ed[-1])) / 2 if ed else 1.0
        s = scores.get(p.get("id"), {})
        sh.row(r, [p.get("id"), p.get("title"), CATS.get(p.get("category"), p.get("category")), p.get("evidence_class"), mid,
                   score_val(p, "cost"), score_val(p, "risk"), score_val(p, "confidence")])
        for k in vkeys:
            sh.set(r, col[k], score_val(p, k))
        a = lambda name: ref(r, col[name])
        sh.set(r, col["value_index"], F("IF(SUM(%s:%s)=0,%s,SUMPRODUCT(%s:%s,%s:%s)/SUM(%s:%s))"
                                        % (w0, w1, a("value"), ref(r, v0), ref(r, v1), w0, w1, w0, w1)), ST_NUM3)
        sh.set(r, col["RICE"], F("%s*%s*(%s/5)/MAX(%s,0.5)" % (a("reach"), a("impact"), a("confidence"), a("effort_mid"))), ST_NUM3)
        sh.set(r, col["ICE"], F("%s*%s*(6-%s)" % (a("impact"), a("confidence"), a("cost"))), ST_NUM3)
        sh.set(r, col["WSJF"], F("(%s+%s+%s)/MAX(%s,1)" % (a("value_index"), a("season"), a("moat"), a("cost"))), ST_NUM3)
        sh.set(r, col["risk_adj"], F("%s*(1-(%s-1)/8)" % (a("value_index"), a("risk"))), ST_NUM3)
        for m in ("RICE", "ICE", "WSJF", "risk_adj"):
            R = rng(m)
            sh.set(r, col["n_" + m], F("IF(MAX(%s)=MIN(%s),0,(%s-MIN(%s))/(MAX(%s)-MIN(%s)))" % (R, R, a(m), R, R, R)), ST_NUM3)
        sh.set(r, col["composite"], F("%s*%s+%s*%s+%s*%s+%s*%s" % (
            ref(WROW, wcol["w.rice"], True), a("n_RICE"), ref(WROW, wcol["w.ice"], True), a("n_ICE"),
            ref(WROW, wcol["w.wsjf"], True), a("n_WSJF"), ref(WROW, wcol["w.risk_adj"], True), a("n_risk_adj"))), ST_NUM3)
        sh.set(r, col["Ранг (формула)"], F("RANK(%s,%s,0)" % (a("composite"), rng("composite"))), ST_INT)
        sh.row(r, [s.get("rank"), s.get("composite"), s.get("priority"), s.get("quadrant")], start=col["Ранг (скрипт)"])
    sh.width([7, 36, 13, 6, 9, 6, 6, 9] + [7] * len(vkeys) + [10] * len(calc) + [9, 10, 9, 11])
    sh.autofilter = "%s:%s" % (ref(HR, 1), ref(last, len(head)))
    return sh


def sheet_model(wb, model):
    sh = wb.add("Модель")
    if not model or not isinstance(model.get("scenarios"), dict) or not model["scenarios"]:
        sh.set(1, 1, "data/model.json не найден или пуст — запустите model.py и пересоберите XLSX.", ST_TITLE)
        sh.width([90])
        return sh
    order = [k for k in ("pessimistic", "base", "optimistic") if k in model["scenarios"]] + \
            [k for k in model["scenarios"] if k not in ("pessimistic", "base", "optimistic")]
    names = {"pessimistic": "Пессимистичный", "base": "Базовый", "optimistic": "Оптимистичный"}
    sc = model["scenarios"]
    sh.set(1, 1, "Модель юнит-экономики: сценарии и допущения (все входы — допущения с метками)", ST_TITLE)
    r = 3
    sh.header(r, ["Параметр"] + [names.get(k, k) for k in order], freeze_col=2)
    params = []
    for k in order:
        for p in (sc[k].get("assumptions") or {}):
            if p not in params:
                params.append(p)
    for p in params:
        r += 1
        sh.set(r, 1, p)
        for i, k in enumerate(order, 2):
            v = (sc[k].get("assumptions") or {}).get(p)
            sh.set(r, i, j(v) if isinstance(v, (dict, list)) else v, ST_EDIT)
    r += 2
    sh.row(r, ["Показатель"] + [names.get(k, k) for k in order], ST_HEAD)
    mrow = {}
    for m in ("cac", "ltv", "payback_months", "arpu", "churn", "roi"):
        r += 1
        mrow[m] = r
        sh.set(r, 1, m)
        for i, k in enumerate(order, 2):
            v = sc[k].get(m)
            sh.set(r, i, v if isinstance(v, (int, float)) else j(v), ST_NUM3 if isinstance(v, float) else None)
    r += 1
    sh.set(r, 1, "LTV/CAC (формула)")
    for i in range(2, 2 + len(order)):
        L, C = ref(mrow["ltv"], i), ref(mrow["cac"], i)
        sh.set(r, i, F('IF(AND(ISNUMBER(%s),ISNUMBER(%s),%s<>0),%s/%s,"")' % (L, C, C, L, C)), ST_NUM3)
    # воронка
    stages = []
    for k in order:
        for st in sc[k].get("funnel") or []:
            if st.get("stage") not in stages:
                stages.append(st.get("stage"))
    if stages:
        r += 2
        sh.row(r, ["Воронка"] + [names.get(k, k) for k in order], ST_HEAD)
        for stg in stages:
            r += 1
            sh.set(r, 1, stg)
            for i, k in enumerate(order, 2):
                v = next((x.get("value") for x in sc[k].get("funnel") or [] if x.get("stage") == stg), None)
                sh.set(r, i, v)
    # помесячно: по сценариям столбцы users/paying/revenue/cost
    if any(sc[k].get("monthly") for k in order):
        r += 2
        sh.set(r, 1, "Помесячный прогноз", ST_TITLE)
        r += 1
        fields = ["users", "paying", "revenue", "cost"]
        hdr = ["Месяц"]
        for k in order:
            hdr += ["%s: %s" % (names.get(k, k)[:5], f) for f in fields]
        sh.row(r, hdr, ST_HEAD)
        months = []
        for k in order:
            for m in sc[k].get("monthly") or []:
                if m.get("month") not in months:
                    months.append(m.get("month"))
        top = r + 1
        for mo in months:
            r += 1
            sh.set(r, 1, mo)
            for si, k in enumerate(order):
                rec = next((x for x in sc[k].get("monthly") or [] if x.get("month") == mo), {})
                for fi, f in enumerate(fields):
                    sh.set(r, 2 + si * len(fields) + fi, rec.get(f))
        if months:
            r += 1
            sh.set(r, 1, "Итого (формула)", ST_HEAD)
            for c in range(2, 2 + len(order) * len(fields)):
                sh.set(r, c, F("SUM(%s:%s)" % (ref(top, c), ref(r - 1, c))), ST_NUM3)
    notes = model.get("notes") or []
    if notes:
        r += 2
        sh.set(r, 1, "Примечания", ST_TITLE)
        for nt in notes:
            r += 1
            sh.set(r, 1, j(nt), ST_NOTE)
    sh.width([30] + [16] * max(len(order) * 4, 3))
    return sh


def sheet_sources(wb, sources, links):
    sh = wb.add("Источники")
    cols = ["ID", "URL", "Название", "Проверено", "Статус", "Использовано для", "Примечание", "Линк-чекер"]
    sh.header(1, cols, freeze_col=2)
    for r, s in enumerate(sources, 2):
        lc = links.get(s.get("url") or "", {})
        sh.row(r, [s.get("id"), s.get("url"), s.get("title"), s.get("date_checked"), s.get("status"), j(s.get("used_for")),
                   s.get("note"), " ".join(x for x in (lc.get("status"), lc.get("verdict")) if x)])
    sh.width([7, 60, 40, 12, 8, 20, 30, 24])
    sh.autofilter = "A1:%s" % ref(max(len(sources), 1) + 1, len(cols))
    return sh


def sheet_kpi(wb, props, model):
    sh = wb.add("KPI")
    cols = ["KPI", "Направление", "Диапазон", "Метка", "ID", "Предложение", "Категория"]
    sh.header(1, cols, freeze_col=2)
    rows = []
    for p in props:
        kp = p.get("effect_kpi") or []
        if isinstance(kp, str):
            kp = [{"kpi": kp}]
        for k in kp:
            rows.append([k.get("kpi"), {"up": "рост", "down": "снижение"}.get(k.get("direction"), k.get("direction")), k.get("range"),
                         k.get("label"), p.get("id"), p.get("title"), CATS.get(p.get("category"), p.get("category"))])
    rows.sort(key=lambda x: (str(x[0] or ""), str(x[4] or "")))
    for r, row in enumerate(rows, 2):
        sh.row(r, row)
    last = len(rows) + 1
    # сводка по KPI — справа от таблицы (колонки I…)
    uniq = sorted({str(x[0]) for x in rows if x[0]})
    sh.set(1, 9, "KPI", ST_HEAD)
    sh.set(1, 10, "Предложений (формула)", ST_HEAD)
    for i, k in enumerate(uniq, 2):
        sh.set(i, 9, k)
        sh.set(i, 10, F("COUNTIF($A$2:$A$%d,%s)" % (max(last, 2), ref(i, 9))), ST_INT)
    sh.width([24, 12, 14, 10, 7, 40, 14, 2, 24, 12])
    sh.autofilter = "A1:%s" % ref(max(last, 2), len(cols))
    return sh


def sheet_kanban(wb, kanban):
    sh = wb.add("Kanban")
    cols = ["ID", "Название", "Колонка", "WIP колонки", "Цель", "Шаги", "KPI", "Ссылки", "Теги", "Приоритет", "Трудозатраты, дн."]
    sh.header(1, cols, freeze_col=3)
    wip = {c.get("name"): c.get("wip") for c in (kanban or {}).get("columns") or []}
    order = list(wip)
    cards = sorted((kanban or {}).get("cards") or [], key=lambda c: (order.index(c.get("column")) if c.get("column") in order else 99, str(c.get("id"))))
    for r, c in enumerate(cards, 2):
        ed = c.get("effort_days")
        sh.row(r, [c.get("id"), c.get("title"), c.get("column"), wip.get(c.get("column")), c.get("goal"), "\n".join(map(str, c.get("steps") or [])),
                   j(c.get("kpi")), "\n".join(map(str, c.get("links") or [])), ", ".join(c.get("tags") or []), c.get("priority"),
                   ("%s–%s" % (ed[0], ed[-1])) if isinstance(ed, list) and ed else j(ed)])
    sh.width([7, 38, 18, 8, 30, 40, 20, 30, 14, 9, 12])
    sh.autofilter = "A1:%s" % ref(max(len(cards), 1) + 1, len(cols))
    return sh


def sheet_competitors(wb, comps):
    sh = wb.add("Конкуренты")
    feats = []
    for c in comps:
        for f in (c.get("features") or {}):
            if f not in feats:
                feats.append(f)
    cols = (["Slug", "Название", "Мы?", "URL", "Тип", "Сегмент", "Цена", "Монетизация", "Языки", "Аудитория", "Свежесть", "Трафик",
             "Лучше нас", "Мы лучше", "Лучшие решения", "Дизайн", "Жалобы", "Перенять", "Не повторять", "Вердикт", "Скриншот", "Источники"]
            + ["ф: %s" % f for f in feats])
    sh.header(1, cols, freeze_col=3)
    for r, c in enumerate(comps, 2):
        shot = c.get("shot") or ""
        if c.get("shot_blocked"):
            shot = (shot + " (анти-бот)").strip()
        sh.row(r, [c.get("slug"), c.get("name"), "да" if c.get("self") else "", c.get("url"), c.get("type"), c.get("segment"), j(c.get("price")),
                   j(c.get("monetization")), j(c.get("languages")), j(c.get("audience")), j(c.get("freshness")), j(c.get("traffic")),
                   j(c.get("better_than_us")), j(c.get("we_better")), j(c.get("best_solutions")), c.get("design_note"), j(c.get("complaints")),
                   j(c.get("adopt")), j(c.get("avoid")), c.get("verdict"), shot, j(c.get("sources"))])
        for i, f in enumerate(feats):
            v = (c.get("features") or {}).get(f)
            sh.set(r, 23 + i, "✓" if v is True else ("—" if v is False else j(v)))
    sh.width([12, 20, 5, 34, 9, 12, 12, 14, 9, 14, 14, 10, 24, 24, 24, 24, 24, 24, 24, 30, 20, 34] + [10] * len(feats))
    sh.autofilter = "A1:%s" % ref(max(len(comps), 1) + 1, len(cols))
    return sh


def sheet_gantt(wb, gantt, horizon):
    sh = wb.add("Гант")
    months = max([horizon] + [int(g.get("end_month") or 0) for g in gantt if isinstance(g.get("end_month"), (int, float))])
    cols = ["ID", "Фаза", "Задача", "Предложения", "Начало, мес", "Конец, мес", "Тип", "Ответственный", "Критерий готовности", "Зависимости"]
    sh.header(1, cols + ["М%d" % m for m in range(1, months + 1)], freeze_col=4)
    for r, g in enumerate(sorted(gantt, key=lambda x: (x.get("start_month") or 0, x.get("end_month") or 0, str(x.get("id")))), 2):
        sh.row(r, [g.get("id"), g.get("phase"), g.get("task"), ", ".join(g.get("proposal_ids") or []), g.get("start_month"), g.get("end_month"),
                   g.get("type"), g.get("owner"), g.get("done_criteria"), ", ".join(g.get("dependencies") or [])])
        s, e = g.get("start_month"), g.get("end_month")
        if isinstance(s, (int, float)) and isinstance(e, (int, float)):
            for m in range(int(s), int(e) + 1):
                if 1 <= m <= months:
                    sh.set(r, len(cols) + m, "◆" if g.get("type") == "milestone" else "", ST_MILE if g.get("type") == "milestone" else ST_BAR)
    sh.width([6, 14, 34, 16, 8, 8, 9, 14, 30, 14] + [3.6] * months)
    sh.autofilter = "A1:%s" % ref(max(len(gantt), 1) + 1, len(cols))
    return sh


def load_links(out):
    path = out / "data" / "links-check.csv"
    res = {}
    if path.exists():
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                res[row.get("url", "")] = row
    return res


def build(out):
    out = Path(out).resolve()
    props = load_json(out / "data" / "proposals.json", None)
    if not isinstance(props, list):
        print("ошибка: нет data/proposals.json (список предложений) в %s" % out, file=sys.stderr)
        return None
    cfg = load_json(out / "build" / "run-config.json", {})
    scores_list = load_json(out / "data" / "scores.json", [])
    scores = {s.get("id"): s for s in scores_list if isinstance(s, dict)} if isinstance(scores_list, list) else {}
    if scores:
        props = sorted(props, key=lambda p: (scores.get(p.get("id"), {}).get("rank") or 10 ** 6, str(p.get("id"))))
    weights = load_json(out / "data" / "weights.json", {})
    model = load_json(out / "data" / "model.json", {})
    horizon = int(((cfg.get("strategy") or {}).get("horizon_months")) or 12)

    wb = Workbook()
    who, copyright_ = author_line(cfg)
    wb.props = {"creator": who, "title": "Стратегия развития %s" % product_name(cfg),
                "description": " · ".join(x for x in (copyright_, "Собрано product-strategy, %s" % (cfg.get("created") or "")) if x)}
    sheet_registry(wb, props, scores)
    sheet_scores(wb, props, scores, weights)
    sheet_model(wb, model)
    sheet_sources(wb, load_json(out / "data" / "sources.json", []) or [], load_links(out))
    sheet_kpi(wb, props, model)
    sheet_kanban(wb, load_json(out / "data" / "kanban.json", {}))
    sheet_competitors(wb, load_json(out / "data" / "competitors.json", []) or [])
    sheet_gantt(wb, load_json(out / "data" / "gantt.json", []) or [], horizon)
    return wb.save(out / "deliverables" / "strategy.xlsx")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", help="папка прогона <OUT>")
    a = ap.parse_args(argv)
    path = build(a.out)
    if path is None:
        return 2
    print("XLSX: %s (%d КБ)" % (path, path.stat().st_size // 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
