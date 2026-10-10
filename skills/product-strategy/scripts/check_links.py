#!/usr/bin/env python3
"""Проверка ссылок прогона: data/sources.json, data/proposals.json (evidence, steps.doc_url), data/competitors.json.

HEAD, при 400/403/405/501 — GET; пауза между запросами к одному хосту; certifi, если установлен (иначе
системные сертификаты); браузерный User-Agent. Ответы 403/429 (и 503 от анти-бот-прокси) — «анти-бот:
требует перепроверки в браузере», мёртвыми не считаются. Пишет data/links-check.csv и обновляет
status / date_checked в data/sources.json.

  check_links.py <OUT> [--offline] [--timeout 10] [--per-host-delay 1.0] [--workers 8] [--strict]

--offline — без сети: только формат URL и дубли (для тестов и черновой проверки); sources.json не меняется.
--strict  — код выхода 1, если есть мёртвые ссылки или ссылки неверного формата.
Только стандартная библиотека (certifi — по желанию).
"""
import argparse
import csv
import json
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "ru,en;q=0.8"}
ANTIBOT = "анти-бот: требует перепроверки в браузере"
FIELDS = ["url", "status", "verdict", "final_url", "checked", "origins"]
_cert_warned = threading.Event()


def ssl_context():
    try:
        import certifi  # noqa: необязательная зависимость
        return ssl.create_default_context(cafile=certifi.where()), "certifi"
    except Exception:
        return ssl.create_default_context(), "системные"


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as e:
        print("предупреждение: не удалось прочитать %s: %s" % (path, e), file=sys.stderr)
        return default


def collect(out):
    """URL → список происхождений («sources:S001», «P003:evidence», «competitors:slug»)."""
    urls = {}

    def add(u, origin):
        if isinstance(u, str) and u.strip():
            urls.setdefault(u.strip(), []).append(origin)
    for s in load_json(out / "data" / "sources.json", []) or []:
        if isinstance(s, dict):
            add(s.get("url"), "sources:%s" % s.get("id", "?"))
    for p in load_json(out / "data" / "proposals.json", []) or []:
        if not isinstance(p, dict):
            continue
        for e in p.get("evidence") or []:
            add((e or {}).get("url"), "%s:evidence" % p.get("id", "?"))
        for st in p.get("steps") or []:
            add((st or {}).get("doc_url"), "%s:steps" % p.get("id", "?"))
    for c in load_json(out / "data" / "competitors.json", []) or []:
        if not isinstance(c, dict):
            continue
        add(c.get("url"), "competitors:%s" % c.get("slug", "?"))
        for u in c.get("sources") or []:
            add(u, "competitors:%s:sources" % c.get("slug", "?"))
    return urls


def format_problem(u):
    if any(ch.isspace() for ch in u):
        return "неверный формат: пробел в URL"
    try:
        parts = urlsplit(u)
    except ValueError as e:
        return "неверный формат: %s" % e
    if parts.scheme not in ("http", "https"):
        return "неверный формат: схема не http(s)"
    if not parts.hostname or "." not in parts.hostname and parts.hostname != "localhost":
        return "неверный формат: нет домена"
    return None


def source_duplicates(out):
    """URL, встречающиеся в sources.json больше одного раза → список id."""
    seen = {}
    for s in load_json(out / "data" / "sources.json", []) or []:
        if isinstance(s, dict) and s.get("url"):
            seen.setdefault(s["url"].strip(), []).append(s.get("id", "?"))
    return {u: ids for u, ids in seen.items() if len(ids) > 1}


def verdict_for(code, headers=None):
    server = ((headers or {}).get("Server") or (headers or {}).get("server") or "").lower()
    if code in (403, 429) or (code == 503 and any(x in server for x in ("cloudflare", "ddos-guard", "akamai", "sucuri"))):
        return ANTIBOT
    if 200 <= code < 400:
        return "ok"
    if code in (404, 410):
        return "мёртвая"
    if code >= 500:
        return "ошибка сервера"
    return "ошибка %d" % code


def probe(u, timeout, ctx):
    """→ (status|None, verdict, final_url)."""
    last = None
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(u, method=method, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return r.status, verdict_for(r.status, r.headers), r.geturl()
        except urllib.error.HTTPError as e:
            last = (e.code, verdict_for(e.code, e.headers), u)
            if method == "HEAD" and e.code in (400, 403, 405, 429, 501):
                continue
            return last
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError, OSError, ValueError) as e:
            reason = getattr(e, "reason", e)
            text = str(reason)
            if "CERTIFICATE_VERIFY_FAILED" in text:
                if not _cert_warned.is_set():
                    _cert_warned.set()
                    print("ошибка сертификата (CERTIFICATE_VERIFY_FAILED): Python не нашёл корневые сертификаты. "
                          "Установите certifi (pip install certifi) или запустите «Install Certificates.command» "
                          "из папки Python (сборка python.org для macOS), затем повторите.", file=sys.stderr)
                return None, "ошибка сертификата", u
            if method == "HEAD":
                last = (None, "сеть: %s" % type(reason).__name__, u)
                continue
            return None, "сеть: %s" % (text[:80] or type(reason).__name__), u
    return last or (None, "сеть: нет ответа", u)


def check_online(urls, timeout, delay, workers):
    ctx, _ = ssl_context()
    by_host = {}
    for u in urls:
        by_host.setdefault((urlsplit(u).hostname or "").lower(), []).append(u)
    results = {}
    lock = threading.Lock()
    done = [0]

    def run_host(items):
        for i, u in enumerate(items):
            if i:
                time.sleep(delay)
            res = probe(u, timeout, ctx)
            with lock:
                results[u] = res
                done[0] += 1
                if done[0] % 25 == 0:
                    print("  проверено %d/%d" % (done[0], len(urls)), file=sys.stderr)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(run_host, by_host.values()))
    return results


def update_sources(out, rows, today):
    path = out / "data" / "sources.json"
    data = load_json(path, None)
    if not isinstance(data, list):
        return 0
    by_url = {r["url"]: r for r in rows}
    n = 0
    for s in data:
        r = by_url.get((s.get("url") or "").strip()) if isinstance(s, dict) else None
        if not r or r["verdict"].startswith("неверный формат"):
            continue
        s["status"] = int(r["status"]) if str(r["status"]).isdigit() else None
        s["date_checked"] = today
        if r["verdict"] == ANTIBOT and ANTIBOT not in (s.get("note") or ""):
            s["note"] = ((s.get("note") or "") + ("; " if s.get("note") else "") + ANTIBOT)
        n += 1
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--offline", action="store_true", help="без сети: только формат и дубли")
    ap.add_argument("--timeout", type=float, default=10.0, help="таймаут запроса, с (по умолчанию 10)")
    ap.add_argument("--per-host-delay", type=float, default=1.0, help="пауза между запросами к одному хосту, с (по умолчанию 1.0)")
    ap.add_argument("--workers", type=int, default=8, help="параллельных хостов (по умолчанию 8)")
    ap.add_argument("--strict", action="store_true", help="код 1 при мёртвых ссылках или неверном формате")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if not (out / "data").is_dir():
        print("ошибка: нет папки %s/data" % out, file=sys.stderr)
        return 2
    urls = collect(out)
    dups = source_duplicates(out)
    today = date.today().isoformat()
    bad = {u: format_problem(u) for u in urls if format_problem(u)}
    to_check = [u for u in urls if u not in bad]
    if a.offline:
        results = {u: (None, "не проверялось (офлайн)", "") for u in to_check}
        print("офлайн-режим: %d уникальных URL, сеть не используется" % len(urls))
    else:
        _, src = ssl_context()
        print("проверка %d уникальных URL (сертификаты: %s, таймаут %ss, пауза по хосту %ss)" % (len(to_check), src, a.timeout, a.per_host_delay))
        results = check_online(to_check, a.timeout, a.per_host_delay, a.workers)
    rows = []
    for u in sorted(urls):
        if u in bad:
            status, verdict, final = None, bad[u], ""
        else:
            status, verdict, final = results.get(u, (None, "не проверялось", ""))
        if u in dups:
            verdict += "; дубль в sources.json: " + ", ".join(dups[u])
        rows.append({"url": u, "status": "" if status is None else str(status), "verdict": verdict, "final_url": final if final and final != u else "",
                     "checked": "" if a.offline else today, "origins": "; ".join(urls[u])})
    path = out / "data" / "links-check.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    updated = 0 if a.offline else update_sources(out, rows, today)
    count = lambda pred: sum(1 for r in rows if pred(r["verdict"]))
    dead = count(lambda v: v.startswith(("мёртвая", "ошибка 4")))
    print("links-check.csv: %s — URL %d; ok %d; анти-бот %d; мёртвых %d; ошибок сети/сервера %d; неверный формат %d; дублей в sources.json %d"
          % (path, len(rows), count(lambda v: v.startswith("ok")), count(lambda v: v.startswith(ANTIBOT)), dead,
             count(lambda v: v.startswith(("сеть", "ошибка сервера", "ошибка сертификата"))), len(bad), len(dups)))
    if updated:
        print("sources.json: обновлены status/date_checked у %d записей" % updated)
    for r in rows:
        if not r["verdict"].startswith(("ok", "не проверялось")):
            print("  %-4s %s — %s" % (r["status"] or "—", r["url"], r["verdict"]))
    return 1 if a.strict and (dead or bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())
