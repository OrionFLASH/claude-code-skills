#!/usr/bin/env python3
"""Проверка ссылок прогона: data/sources.json, data/proposals.json (evidence, steps.doc_url), data/competitors.json.

HEAD, при 400/403/404/405/410/429/501 — повтор GET (мёртвой считается только ссылка, у которой и GET вернул 404/410);
пауза между запросами к одному хосту; certifi, если установлен (иначе системные сертификаты); браузерный User-Agent.
Ответы 403/429 (и 503 от анти-бот-прокси) — «анти-бот: требует перепроверки в браузере», мёртвыми не считаются.
Таймауты и ошибки SSL (кроме CERTIFICATE_VERIFY_FAILED) — повтор с паузой (--retries, --backoff), итог «не проверено: …»;
после двух подряд таких URL одного хоста остальные его URL — «не проверено: хост не отвечает» (без ожидания таймаутов).

Проход браузером (--browser auto|on|off, по умолчанию auto — если найдены Node и модуль playwright: --node-dir, PS_NODE_DIR,
~/.cache/product-strategy/node, <OUT>/build/node): URL с ответом 403/404/410/429 и URL доменов, отвечающих скриптам
иначе, чем браузеру (support.google.com, play.google.com и др., --browser-domains), открываются в Chromium.
Открылась (2xx/3xx) — вердикт «отказ клиента: в браузере открывается» (не мёртвая); 404 и в браузере — «мёртвая
(подтверждено браузером)». Без Playwright такие домены с 403/404 получают «не проверено: … перепроверить в браузере».

Файлы: сетевой режим — data/links-check.net.csv, --offline — data/links-check.offline.csv; data/links-check.csv —
копия сетевого, если он есть (офлайн-проверка сетевой результат не затирает), иначе копия офлайн-файла.
Сетевой режим обновляет status / date_checked в data/sources.json.

  check_links.py <OUT> [--offline] [--timeout 10] [--per-host-delay 1.0] [--workers 8] [--retries 1] [--backoff 2]
                       [--browser auto|on|off] [--browser-domains a.com,b.org] [--node-dir DIR] [--strict] [--json]

--offline — без сети: только формат URL и дубли (для тестов и черновой проверки); sources.json не меняется.
--strict  — код выхода 1, если есть мёртвые ссылки, ссылки неверного формата или записи sources.json без названия.
--json    — печатать итог в виде JSON (проблемные URL, файлы, где они используются, записи без названия).

Дополнения 1.1: URL, извлечённые из текста (research/strategy.md, research/specs/*.md) и не прошедшие проверку формата
(плейсхолдеры «…», <…>, {…}, example.*, незакрытые скобки), только попадают в отчёт и НИКОГДА не записываются в sources.json;
для каждого мёртвого/проблемного URL в отчёте и в колонке `files` links-check.csv перечислены файлы, где он используется
(data/*.json, research/**/*.md, design-refs/*); записи sources.json, у которых title пуст, равен URL или начинается с http(s)://,
выводятся отдельным списком.
Только стандартная библиотека (certifi и Playwright для Node — по желанию).
"""
import argparse
import csv
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
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
NOT_CHECKED = "не проверено"
CLIENT_REFUSED = "отказ клиента: в браузере открывается"
DEAD_BROWSER = "мёртвая (подтверждено браузером)"
FIELDS = ["url", "status", "verdict", "final_url", "checked", "origins", "files", "browser"]
# Домены, которые отвечают скриптам иначе, чем браузеру (ложные 404/403 по User-Agent и т. п.) — второй проход браузером.
CLIENT_REFUSAL_HOSTS = ("support.google.com", "play.google.com", "developers.google.com", "stackoverflowteams.com", "krut.top",
                        "apps.apple.com", "linkedin.com", "x.com", "twitter.com", "instagram.com", "facebook.com", "medium.com",
                        "reddit.com", "vk.com", "rustore.ru", "consultant.ru", "garant.ru", "pravo.gov.ru")
BROWSER_CODES = (403, 404, 410, 429)
HOST_GIVE_UP = 2           # подряд «не проверено» на хосте → остальные его URL не ждём
URL_RE = re.compile(r"https?://[^\s<>\]\"'`]+", re.I)
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


def clean_text_url(raw):
    """Срезает хвостовую пунктуацию и лишние «)» у URL, найденного в тексте."""
    u = raw
    while u and u[-1] in ".,;:!?»”*":
        u = u[:-1]
    while u.endswith(")") and u.count(")") > u.count("("):
        u = u[:-1]
    return u


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
    for f in [out / "research" / "strategy.md"] + sorted((out / "research" / "specs").glob("*.md")):
        if f.is_file():
            try:
                text = f.read_text(encoding="utf-8")
            except OSError:
                continue
            for m in URL_RE.finditer(text):
                add(clean_text_url(m.group(0)), "text:%s" % f.relative_to(out).as_posix())
    return urls


def format_problem(u, text_origin=False):
    """Причина неверного формата или None. Плейсхолдеры «…», <…>, {…}, незакрытые скобки — всегда; example.* — для URL из текста."""
    if any(ch.isspace() for ch in u):
        return "неверный формат: пробел в URL"
    if "…" in u or "..." in u:
        return "неверный формат: плейсхолдер «…»"
    if re.search(r"[<>{}]", u):
        return "неверный формат: плейсхолдер <…> или {…}"
    if u.count("(") > u.count(")"):
        return "неверный формат: незакрытая скобка"
    try:
        parts = urlsplit(u)
    except ValueError as e:
        return "неверный формат: %s" % e
    if parts.scheme not in ("http", "https"):
        return "неверный формат: схема не http(s)"
    if not parts.hostname or "." not in parts.hostname and parts.hostname != "localhost":
        return "неверный формат: нет домена"
    if text_origin and re.fullmatch(r"(?:www\.)?example\.[a-z.]+", parts.hostname.lower()):
        return "неверный формат: плейсхолдер example.*"
    return None


def is_text_only(urls_origins):
    """URL встречается только в текстах (origins все начинаются с «text:») — для него действуют правила плейсхолдеров example.*."""
    return all(o.startswith("text:") for o in urls_origins)


def title_problems(out):
    """Записи sources.json без названия: пусто, равно URL или начинается с http(s):// → [(id, url, title)]."""
    res = []
    for s in load_json(out / "data" / "sources.json", []) or []:
        if not isinstance(s, dict):
            continue
        t = (s.get("title") or "").strip()
        u = (s.get("url") or "").strip()
        if not t or t == u or t.rstrip("/") == u.rstrip("/") or t.lower().startswith(("http://", "https://")):
            res.append((s.get("id", "?"), u, t))
    return res


def usage_files(out, bad_urls):
    """URL → список файлов (относительно <OUT>), где он встречается: data/*.json, research/**/*.md, design-refs/*."""
    files = sorted((out / "data").glob("*.json")) + sorted((out / "research").rglob("*.md")) + \
        sorted(p for p in (out / "design-refs").glob("*") if p.suffix in (".json", ".md"))
    res = {u: [] for u in bad_urls}
    for f in files:
        try:
            if f.stat().st_size > 8 * 1024 * 1024:
                continue
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for u in bad_urls:
            if u in text:
                res[u].append(f.relative_to(out).as_posix())
    return res


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


def host_in(host, domains):
    host = (host or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def transient_kind(reason):
    """Таймаут / SSL / сброс соединения → короткое имя (повторяемая ошибка) или None."""
    text = str(reason)
    if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in text.lower() or "timeout" in text.lower():
        return "таймаут"
    if isinstance(reason, ssl.SSLError) or "SSL" in text:
        return "SSL: %s" % (text[:60] or type(reason).__name__)
    if isinstance(reason, (ConnectionResetError, ConnectionAbortedError)) or "reset by peer" in text.lower():
        return "соединение сброшено"
    return None


def probe_once(u, timeout, ctx):
    """→ ((status|None, verdict, final_url), transient). HEAD, при 400/403/404/405/410/429/501 и сетевой ошибке — GET."""
    last = None
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(u, method=method, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return (r.status, verdict_for(r.status, r.headers), r.geturl()), False
        except urllib.error.HTTPError as e:
            last = (e.code, verdict_for(e.code, e.headers), u)
            if method == "HEAD" and e.code in (400, 403, 404, 405, 410, 429, 501):
                continue                                      # 404 на HEAD ещё не «мёртвая»: решает GET
            return last, False
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError, OSError, ValueError) as e:
            reason = getattr(e, "reason", e)
            text = str(reason)
            if "CERTIFICATE_VERIFY_FAILED" in text:
                if not _cert_warned.is_set():
                    _cert_warned.set()
                    print("ошибка сертификата (CERTIFICATE_VERIFY_FAILED): Python не нашёл корневые сертификаты. "
                          "Установите certifi (pip install certifi) или запустите «Install Certificates.command» "
                          "из папки Python (сборка python.org для macOS), затем повторите.", file=sys.stderr)
                return (None, "ошибка сертификата", u), False
            kind = transient_kind(reason)
            if method == "HEAD":
                last = (None, kind or "сеть: %s" % type(reason).__name__, u)
                continue
            if kind:
                return (None, kind, u), True
            return (None, "сеть: %s" % (text[:80] or type(reason).__name__), u), False
    return (last or (None, "сеть: нет ответа", u)), False


def probe(u, timeout, ctx, retries=1, backoff=2.0, sleep=time.sleep):
    """→ (status|None, verdict, final_url). Таймаут/SSL — повтор с паузой backoff·2^n; не помогло — «не проверено: …»."""
    attempt = 0
    while True:
        res, transient = probe_once(u, timeout, ctx)
        if not transient:
            return res
        if attempt >= retries:
            return None, "%s: %s (попыток: %d)" % (NOT_CHECKED, res[1], attempt + 1), u
        sleep(backoff * (2 ** attempt))
        attempt += 1


def check_online(urls, timeout, delay, workers, retries=1, backoff=2.0, probe_fn=None):
    ctx, _ = ssl_context()
    probe_fn = probe_fn or (lambda u: probe(u, timeout, ctx, retries, backoff))
    by_host = {}
    for u in urls:
        by_host.setdefault((urlsplit(u).hostname or "").lower(), []).append(u)
    results = {}
    lock = threading.Lock()
    done = [0]

    def run_host(items):
        streak = 0
        for i, u in enumerate(items):
            if streak >= HOST_GIVE_UP:
                res = (None, "%s: хост не отвечает (пропущено после %d неудач подряд)" % (NOT_CHECKED, HOST_GIVE_UP), u)
            else:
                if i:
                    time.sleep(delay)
                res = probe_fn(u)
                streak = streak + 1 if res[1].startswith(NOT_CHECKED) else 0
            with lock:
                results[u] = res
                done[0] += 1
                if done[0] % 25 == 0:
                    print("  проверено %d/%d" % (done[0], len(urls)), file=sys.stderr)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(run_host, by_host.values()))
    return results


# ---------------------------------------------------------------- второй проход браузером (Playwright, необязательно)

BROWSER_JS = r"""
const pw = require(process.env.PS_PW_MODULE);
const fs = require('fs');
const urls = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const timeout = parseInt(process.env.PS_PW_TIMEOUT || '20000', 10);
(async () => {
  const browser = await pw.chromium.launch({headless: true});
  const ctx = await browser.newContext({locale: 'ru-RU'});
  const out = [];
  for (const u of urls) {
    const page = await ctx.newPage();
    const rec = {url: u, status: null, final_url: '', title: '', error: ''};
    try {
      const resp = await page.goto(u, {waitUntil: 'domcontentloaded', timeout});
      rec.status = resp ? resp.status() : null;
      rec.final_url = page.url();
      rec.title = ((await page.title()) || '').slice(0, 120);
    } catch (e) { rec.error = String((e && e.message) || e).slice(0, 160); }
    await page.close();
    out.push(rec);
  }
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String((e && e.message) || e)); process.exit(1); });
"""
SOFT_404 = re.compile(r"\b404\b|not found|не найден|страница не существует|page (?:does not|doesn't) exist", re.I)


def find_playwright(out, node_dir=None):
    """→ (node, путь к модулю playwright) или (None, причина)."""
    node = shutil.which("node")
    if not node:
        return None, "нет node"
    cands = [node_dir, os.environ.get("PS_NODE_DIR"), str(Path.home() / ".cache" / "product-strategy" / "node"),
             str(Path(out) / "build" / "node"), str(Path(__file__).resolve().parent / "node")]
    for d in cands:
        if d:
            mod = Path(d).expanduser() / "node_modules" / "playwright"
            if (mod / "package.json").is_file():
                return node, str(mod)
    return None, "нет модуля playwright (check_env.py --install-node)"


def run_browser(urls, node, module, timeout):
    """Открывает URL в Chromium → {url: {status, final_url, title, error}} или исключение RuntimeError."""
    with tempfile.TemporaryDirectory(prefix="ps-links-") as td:
        js = Path(td) / "check_links_browser.cjs"
        js.write_text(BROWSER_JS, encoding="utf-8")
        lst = Path(td) / "urls.json"
        lst.write_text(json.dumps(urls), encoding="utf-8")
        env = dict(os.environ, PS_PW_MODULE=module, PS_PW_TIMEOUT=str(int(timeout * 2000)))
        try:
            r = subprocess.run([node, str(js), str(lst)], capture_output=True, text=True, env=env,
                               timeout=60 + len(urls) * timeout * 3)
        except subprocess.TimeoutExpired:
            raise RuntimeError("проход браузером не уложился во время")
        if r.returncode != 0:
            raise RuntimeError((r.stderr.strip().splitlines() or ["ошибка Playwright"])[-1][:200])
        try:
            return {x["url"]: x for x in json.loads(r.stdout or "[]")}
        except (json.JSONDecodeError, KeyError, TypeError):
            raise RuntimeError("ответ прохода браузером не разобран")


def browser_candidates(results, domains):
    """URL для прохода браузером: 403/404/410/429 и проблемные URL доменов из списка отказов клиента."""
    res = []
    for u, (status, verdict, _f) in results.items():
        if status in BROWSER_CODES or (host_in(urlsplit(u).hostname, domains) and not verdict.startswith("ok")):
            res.append(u)
    return sorted(res)


def browser_verdict(rec):
    """Вердикт по ответу браузера → (verdict|None, заметка). None — оставить вердикт скрипта."""
    if rec.get("error"):
        return None, "браузер: %s" % rec["error"][:80]
    st = rec.get("status")
    note = "браузер: %s" % (st if st is not None else "нет ответа")
    if st is not None and 200 <= st < 400:
        if SOFT_404.search(rec.get("title") or ""):
            return DEAD_BROWSER, note + ", заголовок «%s»" % (rec.get("title") or "")[:60]
        return CLIENT_REFUSED, note
    if st in (404, 410):
        return DEAD_BROWSER, note
    if st in (403, 429) or st == 503:
        return ANTIBOT, note
    return None, note


def apply_browser(results, browser_map):
    """Переписывает результаты по проходу браузером → {url: заметка}."""
    notes = {}
    for u, rec in browser_map.items():
        if u not in results:
            continue
        verdict, note = browser_verdict(rec)
        notes[u] = note
        status, _v, final = results[u]
        if verdict:
            results[u] = (status, verdict, rec.get("final_url") or final)
    return notes


def unverified_refusals(results, domains, why):
    """Без браузера: 403/404/410/429 на доменах из списка отказов клиента → «не проверено» (не мёртвая)."""
    n = 0
    for u, (status, verdict, final) in list(results.items()):
        if status in BROWSER_CODES and host_in(urlsplit(u).hostname, domains):
            results[u] = (status, "%s: %s только для скрипта (домен отвечает скриптам иначе; %s) — перепроверить в браузере"
                          % (NOT_CHECKED, status, why), final)
            n += 1
    return n


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
        if r["verdict"].startswith(NOT_CHECKED):
            continue                                          # не проверено — date_checked не трогаем
        status = int(r["status"]) if str(r["status"]).isdigit() else None
        if r["verdict"] == CLIENT_REFUSED:
            m = re.search(r"браузер: (\d+)", r.get("browser") or "")
            mark = "%s (скрипту — %s)" % (CLIENT_REFUSED, status)
            status = int(m.group(1)) if m else status
            if CLIENT_REFUSED not in (s.get("note") or ""):
                s["note"] = ((s.get("note") or "") + ("; " if s.get("note") else "") + mark)
        s["status"] = status
        s["date_checked"] = today
        if r["verdict"] == ANTIBOT and ANTIBOT not in (s.get("note") or ""):
            s["note"] = ((s.get("note") or "") + ("; " if s.get("note") else "") + ANTIBOT)
        n += 1
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return n


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def csv_is_network(path):
    """Старый data/links-check.csv из сетевой проверки (колонка checked заполнена) — его офлайн не затирает."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return any((row.get("checked") or "").strip() for row in csv.DictReader(f))
    except (OSError, csv.Error):
        return False


def save_results(out, rows, offline):
    """Пишет links-check.net.csv / links-check.offline.csv и обновляет links-check.csv → (файл, сообщение)."""
    data = out / "data"
    main_csv, net = data / "links-check.csv", data / "links-check.net.csv"
    if offline and not net.exists() and main_csv.exists() and csv_is_network(main_csv):
        shutil.copyfile(main_csv, net)                        # прежний сетевой результат (до 1.4) — сохранить
    path = data / ("links-check.offline.csv" if offline else "links-check.net.csv")
    write_csv(path, rows)
    if not offline or not net.exists():
        shutil.copyfile(path, main_csv)
        return path, "links-check.csv = %s" % path.name
    return path, "links-check.csv не тронут: в нём сетевой результат (links-check.net.csv); офлайн — в %s" % path.name


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--offline", action="store_true", help="без сети: только формат и дубли")
    ap.add_argument("--timeout", type=float, default=10.0, help="таймаут запроса, с (по умолчанию 10)")
    ap.add_argument("--per-host-delay", type=float, default=1.0, help="пауза между запросами к одному хосту, с (по умолчанию 1.0)")
    ap.add_argument("--workers", type=int, default=8, help="параллельных хостов (по умолчанию 8)")
    ap.add_argument("--retries", type=int, default=1, help="повторов при таймауте/SSL (по умолчанию 1)")
    ap.add_argument("--backoff", type=float, default=2.0, help="пауза перед повтором, с; удваивается (по умолчанию 2)")
    ap.add_argument("--browser", choices=("auto", "on", "off"), default="auto",
                    help="второй проход Chromium (Playwright) для 403/404/410/429 и доменов из списка (по умолчанию auto)")
    ap.add_argument("--browser-domains", default="", help="дополнительные домены для прохода браузером, через запятую")
    ap.add_argument("--node-dir", help="папка Node-модулей с playwright (иначе PS_NODE_DIR, ~/.cache/product-strategy/node)")
    ap.add_argument("--strict", action="store_true", help="код 1 при мёртвых ссылках, неверном формате или записях sources.json без названия")
    ap.add_argument("--json", action="store_true", help="печатать итог в JSON")
    a = ap.parse_args(argv)
    real_stdout = sys.stdout
    if a.json:
        sys.stdout = sys.stderr          # человекочитаемый вывод — в stderr, в stdout только JSON
    out = Path(a.out).resolve()
    if not (out / "data").is_dir():
        print("ошибка: нет папки %s/data" % out, file=sys.stderr)
        return 2
    urls = collect(out)
    dups = source_duplicates(out)
    today = date.today().isoformat()
    bad = {u: format_problem(u, is_text_only(urls[u])) for u in urls if format_problem(u, is_text_only(urls[u]))}
    to_check = [u for u in urls if u not in bad]
    domains = CLIENT_REFUSAL_HOSTS + tuple(d.strip().lower() for d in a.browser_domains.split(",") if d.strip())
    browser_notes, browser_info = {}, "выключен"
    if a.offline:
        results = {u: (None, "не проверялось (офлайн)", "") for u in to_check}
        print("офлайн-режим: %d уникальных URL, сеть не используется" % len(urls))
    else:
        _, src = ssl_context()
        print("проверка %d уникальных URL (сертификаты: %s, таймаут %ss, пауза по хосту %ss, повторов %d)" % (
            len(to_check), src, a.timeout, a.per_host_delay, a.retries))
        results = check_online(to_check, a.timeout, a.per_host_delay, a.workers, a.retries, a.backoff)
        cands = browser_candidates(results, domains)
        why = "проход браузером выключен (--browser off)"
        if cands and a.browser != "off":
            node, module = find_playwright(out, a.node_dir)
            if node:
                print("проход браузером: %d URL (Playwright)" % len(cands))
                try:
                    browser_notes = apply_browser(results, run_browser(cands, node, module, a.timeout))
                    browser_info = "проверено %d URL" % len(browser_notes)
                    why = None
                except RuntimeError as e:
                    why = "проход браузером не удался: %s" % e
            else:
                why = "проход браузером недоступен: %s" % module
            if why:
                browser_info = why
                print(("ВНИМАНИЕ: " if a.browser == "on" else "") + why, file=sys.stderr)
        elif not cands:
            browser_info = "не нужен (нет 403/404/429)"
        if why and cands:
            unverified_refusals(results, domains, why.split(":")[0])
    rows = []
    for u in sorted(urls):
        if u in bad:
            status, verdict, final = None, bad[u], ""
        else:
            status, verdict, final = results.get(u, (None, "не проверялось", ""))
        if u in dups:
            verdict += "; дубль в sources.json: " + ", ".join(dups[u])
        rows.append({"url": u, "status": "" if status is None else str(status), "verdict": verdict, "final_url": final if final and final != u else "",
                     "checked": "" if a.offline else today, "origins": "; ".join(urls[u]), "files": "", "browser": browser_notes.get(u, "")})
    problem = [r["url"] for r in rows if not r["verdict"].startswith(("ok", "не проверялось", CLIENT_REFUSED))]
    used = usage_files(out, problem) if problem else {}
    for r in rows:
        r["files"] = "; ".join(used.get(r["url"], []))
    no_title = title_problems(out)
    path, saved_note = save_results(out, rows, a.offline)
    updated = 0 if a.offline else update_sources(out, rows, today)
    count = lambda pred: sum(1 for r in rows if pred(r["verdict"]))
    dead = count(lambda v: v.startswith(("мёртвая", "ошибка 4")))
    print(saved_note)
    if not a.offline:
        print("проход браузером: %s" % browser_info)
    print("%s: %s — URL %d; ok %d; анти-бот %d; отказ клиента %d; мёртвых %d; не проверено %d; ошибок сети/сервера %d; неверный формат %d; "
          "дублей в sources.json %d" % (path.name, path, len(rows), count(lambda v: v.startswith("ok")), count(lambda v: v.startswith(ANTIBOT)),
                                        count(lambda v: v.startswith(CLIENT_REFUSED)), dead, count(lambda v: v.startswith(NOT_CHECKED)),
                                        count(lambda v: v.startswith(("сеть", "ошибка сервера", "ошибка сертификата"))), len(bad), len(dups)))
    if updated:
        print("sources.json: обновлены status/date_checked у %d записей" % updated)
    for r in rows:
        if not r["verdict"].startswith(("ok", "не проверялось")):
            print("  %-4s %s — %s" % (r["status"] or "—", r["url"], r["verdict"]))
            if r["files"]:
                print("       используется в: %s" % r["files"])
    if no_title:
        print("sources.json: записей без названия (title пуст или равен URL): %d — %s" % (len(no_title), ", ".join(i for i, _, _ in no_title[:15])))
    if a.json:
        print(json.dumps({"file": "data/" + path.name, "urls": len(rows), "dead": dead, "bad_format": len(bad), "duplicates": len(dups),
                          "not_checked": count(lambda v: v.startswith(NOT_CHECKED)), "client_refused": count(lambda v: v.startswith(CLIENT_REFUSED)),
                          "browser": browser_info, "no_title": [{"id": i, "url": u, "title": t} for i, u, t in no_title],
                          "problems": [{"url": r["url"], "status": r["status"], "verdict": r["verdict"], "files": r["files"].split("; ") if r["files"] else []}
                                       for r in rows if not r["verdict"].startswith(("ok", "не проверялось", CLIENT_REFUSED))]},
                         ensure_ascii=False, indent=2), file=real_stdout)
    return 1 if a.strict and (dead or bad or no_title) else 0


if __name__ == "__main__":
    raise SystemExit(main())
