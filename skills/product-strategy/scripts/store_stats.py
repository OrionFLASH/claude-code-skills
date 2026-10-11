#!/usr/bin/env python3
"""Публичная статистика карточек приложения в магазинах → <OUT>/data/store-stats.json (+ research/store-stats.md).

  store_stats.py <OUT> [--url URL …] [--rustore PKG] [--gplay PKG] [--appstore ID] [--huawei ID]
                 [--reviews 50] [--lang ru] [--country ru] [--timeout 20]
                 [--offline-fixture DIR] [--save-fixture DIR] [--stdout]

Без --url/--rustore/… карточки берутся из run-config: sources.stores и sources.external.stores (их заполняет
intake.py из ответа «Адрес»). Только чтение публичных страниц и открытых API, без входа и ключей:

  RuStore    — страница www.rustore.ru/catalog/app/<pkg> (JSON-LD: рейтинг и число оценок; данные страницы: загрузки
               за 7 и 30 дней, метка «N тыс +», версия, дата обновления, «что нового», разработчик) и отзывы
               backapi.rustore.ru/comment/comment (оценка, дата, текст, ответ разработчика → доля ответов);
  Google Play — страница play.google.com/store/apps/details (JSON-LD: рейтинг, число оценок; текст страницы: метка
               скачиваний «1 млн+», «Последнее обновление», «Что нового» — разбор HTML, может сломаться при смене вёрстки).
               Отзывы и ответы разработчика — только внутренний API: не собираются (поле null с причиной);
  App Store  — iTunes Lookup API (рейтинг, число оценок, версия, дата, «что нового») и RSS отзывов (без ответов
               разработчика). Загрузок App Store не публикует;
  AppGallery — публичного API без ключа нет: skipped с причиной (данные — вручную со страницы).

У каждого поля: value, as_of (дата сбора), source (URL), kind (факт | оценка) и note — смысл поля и оговорки
(например, «monthlyDownloads — загрузки за 30 дней по данным страницы; смысл не документирован [допущение]»).
Нет сети — карточка получает status: skipped и причину; файл всё равно пишется (код 0). --offline-fixture DIR —
ответы берутся из файлов (тесты, повтор без сети): rustore-<pkg>.html, rustore-<pkg>-comments-<стр>.json,
gplay-<pkg>.html, appstore-<id>-lookup.json, appstore-<id>-reviews.json. --save-fixture DIR — сохранить живые
ответы в таком же виде. Имена авторов отзывов не сохраняются. Схема — references/external-product.md.
Только стандартная библиотека.
"""
import argparse
import html as htmlmod
import json
import re
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
STORES = ("rustore", "gplay", "appstore", "huawei")
STORE_TITLES = {"rustore": "RuStore", "gplay": "Google Play", "appstore": "App Store", "huawei": "AppGallery"}


class FixtureMissing(Exception):
    pass


CA_CANDIDATES = ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt",
                 "/opt/homebrew/etc/openssl@3/cert.pem", "/usr/local/etc/openssl@3/cert.pem", "/usr/local/etc/openssl/cert.pem")


def ssl_contexts():
    """Контексты TLS с проверкой сертификатов: системный по умолчанию, затем явные наборы корневых сертификатов
    (у Python с python.org на macOS свой набор часто не установлен). Проверка не отключается никогда."""
    yield ssl.create_default_context()
    seen = set()
    cands = [os.environ.get("SSL_CERT_FILE")] + list(CA_CANDIDATES)
    try:
        import certifi                                                    # noqa: WPS433 — необязательно, если установлен
        cands.insert(1, certifi.where())
    except ImportError:
        pass
    for c in cands:
        if c and c not in seen and os.path.isfile(c):
            seen.add(c)
            yield ssl.create_default_context(cafile=c)


class Fetcher:
    """HTTP GET только на чтение; при --offline-fixture — файлы вместо сети; при --save-fixture — сохранение ответов."""

    def __init__(self, fixture=None, save=None, timeout=20, pause=0.4):
        self.fixture = Path(fixture) if fixture else None
        self.save = Path(save) if save else None
        self.timeout = timeout
        self.pause = pause
        self.calls = 0

    def get(self, key, url, lang="ru"):
        if self.fixture:
            p = self.fixture / key
            if not p.is_file():
                raise FixtureMissing("нет файла фикстуры %s" % key)
            return p.read_text(encoding="utf-8", errors="replace")
        if self.calls:
            time.sleep(self.pause)
        self.calls += 1
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "%s,en;q=0.7" % lang})
        last = None
        for ctx in ([self.ctx] if getattr(self, "ctx", None) else ssl_contexts()):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as r:   # noqa: S310 — https магазинов
                    text = r.read().decode("utf-8", errors="replace")
                self.ctx = ctx
                break
            except urllib.error.URLError as e:
                if not isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
                    raise
                last = e
        else:
            raise urllib.error.URLError("TLS: нет доверенных корневых сертификатов (Python с python.org на macOS — запустите "
                                        "«Install Certificates.command» или задайте SSL_CERT_FILE): %s" % getattr(last, "reason", last))
        if self.save:
            self.save.mkdir(parents=True, exist_ok=True)
            (self.save / key).write_text(text, encoding="utf-8")
        return text


def parse_store_url(url):
    """URL карточки → (store, id, lang|None) или None. RuStore, Google Play, App Store, AppGallery."""
    u = str(url or "").strip()
    low = u.lower()
    m = re.search(r"rustore\.ru/(?:catalog/)?app/([A-Za-z0-9_.]+)", u)
    if m:
        return ("rustore", m.group(1), "ru")
    if "play.google.com" in low:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
        if q.get("id"):
            return ("gplay", q["id"][0], (q.get("hl") or [None])[0])
    m = re.search(r"apps\.apple\.com/(?:([a-z]{2})/)?app/(?:[^/?#]+/)?id(\d+)", low)
    if m:
        return ("appstore", m.group(2), m.group(1))
    m = re.search(r"appgallery\.(?:cloud\.)?huawei\.com/.*?(?:app/)?(C\d+)", u, re.I)
    if m:
        return ("huawei", m.group(1), None)
    return None


def field(value, source, note="", kind="факт", as_of=None):
    return {"value": value, "as_of": as_of or date.today().isoformat(), "source": source, "kind": kind, "note": note}


def jsonld(page):
    """Первый JSON-LD с SoftwareApplication (в т. ч. внутри @graph) → dict или {}."""
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        items = d.get("@graph") if isinstance(d, dict) and isinstance(d.get("@graph"), list) else [d] if isinstance(d, dict) else d
        for it in items or []:
            if isinstance(it, dict) and "SoftwareApplication" in str(it.get("@type")):
                return it
    return {}


def _num(v):
    try:
        f = float(str(v).replace(",", "."))
        return int(f) if f == int(f) else round(f, 3)
    except (TypeError, ValueError):
        return None


def page_text(page):
    """HTML → текст строками (для разбора меток Google Play)."""
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "\n", page)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = htmlmod.unescape(t).replace(" ", " ").replace("\xa0", " ")
    return re.sub(r"\n\s*\n+", "\n", t)


# ---------------------------------------------------------------- RuStore
def _flight(page):
    """Данные Next.js (self.__next_f.push) со снятым экранированием кавычек."""
    return page.replace('\\"', '"')


def _near(u, pos, key, kind="str", window=15000):
    """Значение ключа, ближайшее к позиции pos (объект приложения на странице RuStore; рядом — карточки похожих)."""
    best, bd = None, None
    rx = re.compile(r'"%s":\s*(?:"((?:[^"\\]|\\.)*)"|(-?\d+(?:\.\d+)?)|null)' % re.escape(key))
    for m in rx.finditer(u, max(0, pos - window), min(len(u), pos + window)):
        d = abs(m.start() - pos)
        if bd is None or d < bd:
            raw = m.group(1) if m.group(1) is not None else m.group(2)
            if raw is not None and m.group(1) is not None:
                try:
                    raw = json.loads('"%s"' % raw.replace("\\\\", "\\"))
                except ValueError:
                    raw = raw.replace("\\n", "\n")
            best, bd = raw, d
    if kind == "num":
        return _num(best)
    return best


def rustore(f, pkg, n_reviews, lang):
    url = "https://www.rustore.ru/catalog/app/%s" % pkg
    res = {"store": "rustore", "id": pkg, "url": url, "status": "ok", "fields": {}, "reviews": [], "warnings": []}
    page = f.get("rustore-%s.html" % pkg, url, lang)
    ld = jsonld(page)
    u = _flight(page)
    mpos = re.search(r'"packageName":\s*"%s"' % re.escape(pkg), u)
    pos = mpos.start() if mpos else -1
    F = res["fields"]
    agg = ld.get("aggregateRating") or {}
    if ld.get("name"):
        F["name"] = field(ld["name"], url)
    if agg:
        F["rating"] = field(_num(agg.get("ratingValue")), url, "средняя оценка 1–5 из JSON-LD карточки (округлена магазином)")
        F["ratings_count"] = field(_num(agg.get("ratingCount")), url, "число оценок из JSON-LD карточки")
    if pos < 0:
        res["warnings"].append("на странице не найден объект приложения %s — данные о загрузках и версии не разобраны" % pkg)
    else:
        for key, name, kind, note, fkind in (
                ("monthlyDownloads", "downloads_30d", "num", "загрузки за 30 дней по данным страницы RuStore (поле monthlyDownloads); "
                 "смысл поля не документирован — [допущение]: установки за последние 30 дней", "оценка"),
                ("weeklyDownloads", "downloads_7d", "num", "загрузки за 7 дней (поле weeklyDownloads); смысл — [допущение]", "оценка"),
                ("downloads", "downloads_label", "str", "округлённая метка установок за всё время на карточке («1 тыс +»)", "факт"),
                ("versionName", "version", "str", "версия на карточке", "факт"),
                ("appVerUpdatedAt", "updated", "str", "дата публикации текущей версии (UTC)", "факт"),
                ("whatsNew", "whats_new", "str", "«Что нового» текущей версии", "факт"),
                ("companyName", "developer", "str", "разработчик на карточке", "факт"),
                ("minAndroidVersion", "min_android", "str", "минимальная версия Android", "факт")):
            v = _near(u, pos, key, kind)
            if v not in (None, ""):
                F[name] = field(v, url, note, fkind)
        if "name" not in F:
            v = _near(u, pos, "appName")
            if v:
                F["name"] = field(v, url)
    # отзывы: backapi (открытый JSON), постранично
    got, page_no, size = [], 0, min(50, max(1, n_reviews))
    while len(got) < n_reviews and page_no < 20:
        api = "https://backapi.rustore.ru/comment/comment?packageName=%s&pageNumber=%d&pageSize=%d" % (pkg, page_no, size)
        try:
            body = json.loads(f.get("rustore-%s-comments-%d.json" % (pkg, page_no), api, lang)).get("body") or {}
        except FixtureMissing:
            break
        except ValueError:
            res["warnings"].append("отзывы: ответ не JSON (%s)" % api)
            break
        items = body.get("content") or []
        for c in items:
            got.append({"id": c.get("commentId"), "date": str(c.get("commentDate") or "")[:10], "rating": c.get("appRating"),
                        "text": (c.get("commentText") or "")[:400], "has_reply": bool(c.get("devResponse")),
                        "reply_date": str(c.get("devResponseDate") or "")[:10] or None, "version_code": c.get("userVerCode")})
        if len(items) < size:
            break
        page_no += 1
    res["reviews"] = got[:n_reviews]
    api0 = "https://backapi.rustore.ru/comment/comment?packageName=%s" % pkg
    # ответы разработчика: в API поле devResponse часто пустое — новые ответы лежат в «replies» страницы отзывов
    rev_url = "https://www.rustore.ru/catalog/app/%s/reviews" % pkg
    replies = {}
    try:
        replies = rustore_replies(f.get("rustore-%s-reviews.html" % pkg, rev_url, lang))
    except FixtureMissing:
        pass
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        res["warnings"].append("страница отзывов не получена (%s) — доля ответов только по полю devResponse" % str(e)[:100])
    for r in res["reviews"]:
        if not r["has_reply"] and r.get("id") in replies:
            r["has_reply"] = replies[r["id"]]
        elif not r["has_reply"] and replies:
            r["has_reply"] = None                                 # отзыва нет на странице — ответ неизвестен
    if res["reviews"]:
        n = len(res["reviews"])
        known = [r for r in res["reviews"] if r["has_reply"] is not None]
        replied = sum(1 for r in known if r["has_reply"])
        F["reviews_sampled"] = field(n, api0, "последние отзывы с текстом (не все оценки)")
        if known:
            F["dev_reply_share"] = field(round(replied / len(known), 3), rev_url if replies else api0,
                                         "доля отзывов с ответом разработчика: %d из %d последних, для которых ответ известен "
                                         "(страница отзывов RuStore и поле devResponse API)" % (replied, len(known)), "оценка")
        F["reviews_avg_rating"] = field(round(sum(r["rating"] or 0 for r in res["reviews"]) / n, 2), api0,
                                        "средняя оценка в выборке последних отзывов (смещена к пишущим отзывы)", "оценка")
    return res


def rustore_replies(page):
    """Страница отзывов RuStore → {id отзыва: есть ли ответ разработчика (userType DEV)}."""
    u = _flight(page)
    out = {}
    starts = [(m.start(), int(m.group(1))) for m in re.finditer(r'\{"id":\s*(\d+),\s*"rating":', u)]
    for i, (pos, rid) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(u)
        m = re.search(r'"totalRepliesCount":\s*(\d+)', u[pos:end])
        seg = u[pos:pos + m.end()] if m else u[pos:end]
        dev = bool(re.search(r'"userType":\s*"DEV"', seg))
        out[rid] = out.get(rid, False) or dev
    return out


# ---------------------------------------------------------------- Google Play
GP_INSTALLS = re.compile(r"\n[ \t]*(\d[\d \t.,]*[ \t]*(?:тыс\.|млн|млрд|K|M|B)?[ \t]*\+)[ \t]*\n\s*\(?(?:количество скачиваний|Downloads|скачивани)", re.I)
GP_UPDATED = re.compile(r"(?:Последнее обновление|Обновлено|Updated on)\s*\n\s*([^\n]{4,32})", re.I)
GP_WHATSNEW = re.compile(r"(?:Что нового|What[’']s new)\s*\n(.{3,1500}?)\n\s*(?:Оценки и отзывы|Ratings and reviews|Безопасность данных|"
                         r"Data safety|Связаться с разработчиком|App support|Поддержка приложения|Последнее обновление|Updated on|"
                         r"arrow_forward)", re.I | re.S)


def gplay(f, pkg, n_reviews, lang, country):
    url = "https://play.google.com/store/apps/details?id=%s&hl=%s&gl=%s" % (pkg, lang, country.upper())
    res = {"store": "gplay", "id": pkg, "url": url, "status": "ok", "fields": {}, "reviews": [], "warnings": []}
    page = f.get("gplay-%s.html" % pkg, url, lang)
    ld = jsonld(page)
    F = res["fields"]
    if not ld:
        res["warnings"].append("нет JSON-LD на странице — карточка не найдена или вёрстка изменилась")
    if ld.get("name"):
        F["name"] = field(ld["name"], url)
    agg = ld.get("aggregateRating") or {}
    if agg:
        F["rating"] = field(round(float(agg.get("ratingValue")), 2) if _num(agg.get("ratingValue")) is not None else None, url,
                            "средняя оценка 1–5 из JSON-LD (страна gl=%s)" % country.upper())
        F["ratings_count"] = field(_num(agg.get("ratingCount")), url, "число оценок из JSON-LD")
    if (ld.get("author") or {}).get("name"):
        F["developer"] = field(ld["author"]["name"], url)
    t = page_text(page)
    m = GP_INSTALLS.search(t)
    if m:
        F["downloads_label"] = field(re.sub(r"\s+", " ", m.group(1)).strip(), url,
                                     "метка установок за всё время («1 млн+»), разбор текста страницы — может сломаться при смене вёрстки")
    m = GP_UPDATED.search(t)
    if m:
        F["updated"] = field(m.group(1).strip(), url, "«Последнее обновление» как на странице (локализованная дата)")
    m = GP_WHATSNEW.search(t)
    if m:
        F["whats_new"] = field(re.sub(r"\s*\n\s*", " ", m.group(1)).strip()[:800], url, "«Что нового», разбор текста страницы")
    F["dev_reply_share"] = field(None, url, "Google Play отдаёт отзывы и ответы разработчика только через внутренний API — не собирается; "
                                 "оценить вручную по карточке", "оценка")
    return res


# ---------------------------------------------------------------- App Store
def appstore(f, app_id, n_reviews, lang, country):
    cc = (country or "us").lower()
    url = "https://itunes.apple.com/lookup?id=%s&country=%s" % (app_id, cc)
    page_url = "https://apps.apple.com/%s/app/id%s" % (cc, app_id)
    res = {"store": "appstore", "id": app_id, "url": page_url, "status": "ok", "fields": {}, "reviews": [], "warnings": []}
    d = json.loads(f.get("appstore-%s-lookup.json" % app_id, url, lang))
    r = (d.get("results") or [None])[0]
    if not r:
        res["status"] = "error"
        res["reason"] = "приложение id%s не найдено в App Store страны %s" % (app_id, cc)
        return res
    F = res["fields"]
    F["name"] = field(r.get("trackName"), url)
    F["rating"] = field(_num(r.get("averageUserRating")), url, "средняя оценка 1–5, страна %s (Lookup API)" % cc)
    F["ratings_count"] = field(_num(r.get("userRatingCount")), url, "число оценок, страна %s" % cc)
    F["version"] = field(r.get("version"), url)
    F["updated"] = field(str(r.get("currentVersionReleaseDate") or "")[:10] or None, url, "дата текущей версии")
    if r.get("releaseNotes"):
        F["whats_new"] = field(str(r["releaseNotes"])[:800], url, "«Что нового» текущей версии")
    F["developer"] = field(r.get("sellerName") or r.get("artistName"), url)
    F["price"] = field(r.get("formattedPrice") or r.get("price"), url)
    F["downloads_label"] = field(None, url, "App Store не публикует число загрузок", "оценка")
    rss = "https://itunes.apple.com/%s/rss/customerreviews/page=1/id=%s/sortby=mostrecent/json" % (cc, app_id)
    try:
        feed = json.loads(f.get("appstore-%s-reviews.json" % app_id, rss, lang)).get("feed") or {}
        for e in (feed.get("entry") or [])[:n_reviews]:
            if not isinstance(e, dict) or "im:rating" not in e:
                continue
            res["reviews"].append({"date": str((e.get("updated") or {}).get("label") or "")[:10],
                                   "rating": _num((e.get("im:rating") or {}).get("label")),
                                   "text": str((e.get("content") or {}).get("label") or "")[:400], "has_reply": None})
    except FixtureMissing:
        pass
    except (ValueError, urllib.error.URLError, socket.timeout) as e:
        res["warnings"].append("отзывы RSS не получены: %s" % str(e)[:120])
    if res["reviews"]:
        F["reviews_sampled"] = field(len(res["reviews"]), rss, "последние отзывы из RSS")
    F["dev_reply_share"] = field(None, rss, "ответы разработчика в RSS App Store не передаются — не собирается", "оценка")
    return res


def huawei(f, app_id, n_reviews, lang, country):
    return {"store": "huawei", "id": app_id, "url": "https://appgallery.huawei.com/app/%s" % app_id, "status": "skipped",
            "reason": "AppGallery: публичного API без ключа нет — рейтинг и загрузки снять вручную со страницы", "fields": {},
            "reviews": [], "warnings": []}


COLLECT = {"rustore": rustore, "gplay": gplay, "appstore": appstore, "huawei": huawei}


def collect_one(f, store, sid, n_reviews, lang, country):
    t0 = time.time()
    try:
        if store in ("rustore",):
            res = COLLECT[store](f, sid, n_reviews, lang)
        else:
            res = COLLECT[store](f, sid, n_reviews, lang, country)
    except FixtureMissing as e:
        res = {"store": store, "id": sid, "status": "skipped", "reason": "офлайн: %s" % e, "fields": {}, "reviews": [], "warnings": []}
    except urllib.error.HTTPError as e:
        res = {"store": store, "id": sid, "status": "error", "reason": "HTTP %s — карточка не найдена или доступ закрыт" % e.code,
               "fields": {}, "reviews": [], "warnings": []}
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
        res = {"store": store, "id": sid, "status": "skipped", "reason": "сеть недоступна: %s" % str(getattr(e, "reason", e))[:160],
               "fields": {}, "reviews": [], "warnings": []}
    res["fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    res["duration_s"] = round(time.time() - t0, 2)
    if res["status"] == "ok" and not res["fields"]:
        res["status"] = "error"
        res["reason"] = "страница получена, но поля не разобраны (вёрстка изменилась?)"
    return res


def targets_from_config(out):
    try:
        cfg = json.loads((Path(out) / "build" / "run-config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], {}
    src = cfg.get("sources") or {}
    items = list(src.get("stores") or []) + list((src.get("external") or {}).get("stores") or [])
    seen, out_ = set(), []
    for it in items:
        if isinstance(it, dict) and it.get("store") in STORES and it.get("id") and (it["store"], it["id"]) not in seen:
            seen.add((it["store"], it["id"]))
            out_.append((it["store"], it["id"]))
    return out_, cfg


def summarize(stores):
    rows = []
    for s in stores:
        F = s.get("fields") or {}
        g = lambda k: (F.get(k) or {}).get("value")                      # noqa: E731
        rows.append({"store": s["store"], "id": s["id"], "status": s["status"], "name": g("name"), "rating": g("rating"),
                     "ratings_count": g("ratings_count"), "downloads_30d": g("downloads_30d"), "downloads_label": g("downloads_label"),
                     "updated": g("updated"), "dev_reply_share": g("dev_reply_share"), "reviews_sampled": g("reviews_sampled")})
    return rows


def render_md(doc):
    L = ["# Статистика магазинов", "", "Собрано `store_stats.py` %s%s. Только публичные страницы и открытые API; у каждого поля — дата, "
         "источник и оговорка в `data/store-stats.json`. Поля с меткой [оценка] — интерпретация (смысл поля магазином не "
         "документирован) [допущение]." % (doc["generated"][:10], " (офлайн-фикстуры)" if doc.get("offline") else ""), "",
         "| Магазин | Приложение | Рейтинг | Оценок | Загрузки | Обновление | Ответы разработчика | Статус |", "|---|---|---|---|---|---|---|---|"]
    for r in doc["summary"]:
        dl = " / ".join(str(x) for x in (("%s за 30 дн. [оценка]" % r["downloads_30d"]) if r["downloads_30d"] is not None else None,
                                          r["downloads_label"]) if x) or "—"
        share = ("%d %% из %s" % (round(r["dev_reply_share"] * 100), r["reviews_sampled"])) if isinstance(r["dev_reply_share"], (int, float)) else "—"
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (STORE_TITLES.get(r["store"], r["store"]), r["name"] or r["id"],
                                                             r["rating"] if r["rating"] is not None else "—",
                                                             r["ratings_count"] if r["ratings_count"] is not None else "—", dl,
                                                             str(r["updated"] or "—")[:10] if r["store"] != "gplay" else (r["updated"] or "—"),
                                                             share, r["status"]))
    for s in doc["stores"]:
        if s.get("reason") or s.get("warnings"):
            L.append("")
            L.append("- %s %s: %s" % (STORE_TITLES.get(s["store"], s["store"]), s["id"], "; ".join(([s["reason"]] if s.get("reason") else []) + s.get("warnings", []))))
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--url", action="append", default=[], help="ссылка на карточку (можно несколько)")
    for s in STORES:
        ap.add_argument("--" + s, action="append", default=[], help="id приложения в %s" % STORE_TITLES[s])
    ap.add_argument("--reviews", type=int, default=50, help="сколько последних отзывов брать (RuStore, App Store), по умолчанию 50")
    ap.add_argument("--lang", default="ru")
    ap.add_argument("--country", default="ru")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--offline-fixture", help="папка с сохранёнными ответами вместо сети")
    ap.add_argument("--save-fixture", help="сохранить живые ответы в папку (для повторов и тестов)")
    ap.add_argument("--stdout", action="store_true", help="печать JSON вместо записи файлов")
    a = ap.parse_args(argv)
    out = Path(a.out).expanduser().resolve()
    targets = []
    for u in a.url:
        hit = parse_store_url(u)
        if not hit:
            print("предупреждение: не карточка магазина — %s" % u, file=sys.stderr)
            continue
        targets.append(hit[:2])
    for s in STORES:
        targets += [(s, x) for x in getattr(a, s)]
    cfg = {}
    if not targets:
        targets, cfg = targets_from_config(out)
    targets = list(dict.fromkeys(targets))
    if not targets:
        print("ошибка: нет карточек — передайте --url/--rustore/--gplay/--appstore или заполните sources.stores в run-config "
              "(intake.py update <OUT> --set product.url=\"<ссылки>\")", file=sys.stderr)
        return 2
    f = Fetcher(a.offline_fixture, a.save_fixture, a.timeout)
    stores = [collect_one(f, s, sid, a.reviews, a.lang, a.country) for s, sid in targets]
    doc = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "tool": "store_stats.py", "offline": bool(a.offline_fixture),
           "lang": a.lang, "country": a.country, "stores": stores, "summary": summarize(stores),
           "assumptions": ["Загрузки за 7/30 дней RuStore — поля страницы weeklyDownloads/monthlyDownloads; смысл не документирован [допущение]",
                           "Средняя по выборке отзывов смещена к пользователям, пишущим отзывы [допущение]",
                           "Метки установок («1 тыс +», «1 млн+») — нижняя граница диапазона за всё время"]}
    if a.stdout:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
    else:
        (out / "data").mkdir(parents=True, exist_ok=True)
        (out / "research").mkdir(parents=True, exist_ok=True)
        (out / "data" / "store-stats.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "research" / "store-stats.md").write_text(render_md(doc), encoding="utf-8")
        print("→ %s\n→ %s" % (out / "data" / "store-stats.json", out / "research" / "store-stats.md"))
    for s in stores:
        print("store_stats: %s %s — %s%s" % (STORE_TITLES.get(s["store"]), s["id"], s["status"], (": " + s["reason"]) if s.get("reason") else ""),
              file=sys.stderr if a.stdout else sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
