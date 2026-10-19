"""WP-F (1.5), FB-031: shoot_competitors.mjs не кликает по cookie-баннерам по умолчанию.

Критерий приёмки: без флага в журнале нет кликов (сервер не получил ни одного запроса от кнопок «Принять»), на 5 сайтах
с баннером снимки без перекрытия (в PNG нет красного цвета баннеров); карточка получает cookie: hidden | accepted | none;
--accept-cookies — прежнее поведение (клик), cookie: accepted.

Запуск: python3 -m pytest tests/test_design_fb_competitors.py -q -p no:cacheprovider
"""
import functools
import http.server
import json
import os
import shutil
import socketserver
import struct
import subprocess
import threading
import zlib
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
NODE_DIR = SKILL / "scripts" / "node"


def find_node_dir():
    for d in [os.environ.get("PS_NODE_DIR"), str(NODE_DIR), str(Path.home() / ".cache" / "product-strategy" / "node")]:
        if d and (Path(d) / "node_modules" / "playwright" / "package.json").exists():
            return d
    return None


NODE = shutil.which("node")
PW_DIR = find_node_dir()
needs_pw = pytest.mark.skipif(not NODE or not PW_DIR, reason="playwright недоступен")

BODY = "<h1>Сайт конкурента</h1>" + "".join("<p>Обычный абзац текста страницы номер %d про продукт.</p>" % i for i in range(60))
RED = "background:#ff0000;color:#ffffff"
CLICK = "onclick=\"fetch('/clicked?'+location.pathname);this.closest('[data-b]').remove()\""
PAGES = {
    "onetrust": '<div id="onetrust-banner-sdk" data-b style="position:fixed;bottom:0;left:0;right:0;height:140px;%s">We use cookies <button id="onetrust-accept-btn-handler" %s>Accept all</button></div>' % (RED, CLICK),
    "cookiebot": '<div id="CybotCookiebotDialog" data-b style="position:fixed;top:30%%;left:30%%;width:500px;height:240px;%s">Cookies <button id="CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll" %s>Allow all</button></div>' % (RED, CLICK),
    "generic": '<div class="cookie-banner" data-b style="position:fixed;bottom:0;left:0;right:0;height:120px;%s">Мы используем куки <button class="cookie-accept" %s>Принять</button></div>' % (RED, CLICK),
    "textonly": '<div class="bar-x" data-b style="position:fixed;bottom:20px;left:20px;width:600px;height:110px;%s">Этот сайт использует cookie и персональные данные. <button %s>Понятно</button></div>' % (RED, CLICK),
    "didomi": '<div id="didomi-host" data-b><div style="position:fixed;inset:auto 0 0 0;height:160px;%s">Consent <button id="didomi-notice-agree-button" %s>Agree</button></div></div>' % (RED, CLICK),
}


def png_pixels(path):
    """(w, h, bytes per pixel, rows) — минимальный декодер PNG (8 бит, RGB/RGBA, без чересстрочности)."""
    data = Path(path).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w = 8, b"", 0
    while pos < len(data):
        n, typ = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + n]
        if typ == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", chunk[:10])
            assert depth == 8 and ctype in (2, 6)
            bpp = 3 if ctype == 2 else 4
        elif typ == b"IDAT":
            idat += chunk
        pos += 12 + n
    raw = zlib.decompress(idat)
    stride = w * bpp
    rows, prev = [], bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(bytes(line))
        prev = line
    return w, h, bpp, rows


def red_pixels(path):
    w, h, bpp, rows = png_pixels(path)
    n = 0
    for y in range(0, h, 4):
        r = rows[y]
        for x in range(0, w, 4):
            i = x * bpp
            if r[i] > 230 and r[i + 1] < 30 and r[i + 2] < 30:
                n += 1
    return n


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "www"
    root.mkdir()
    for name, banner in PAGES.items():
        (root / name).mkdir()
        (root / name / "index.html").write_text('<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>%s</title></head><body>%s%s</body></html>'
                                                % (name, BODY, banner), encoding="utf-8")
    (root / "clean").mkdir()
    (root / "clean" / "index.html").write_text("<!doctype html><html><head><meta charset='utf-8'><title>clean</title></head><body>%s</body></html>" % BODY, encoding="utf-8")
    hits = []

    class H(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/clicked"):
                hits.append(self.path)
                self.send_response(204)
                self.end_headers()
                return
            return super().do_GET()

        def log_message(self, *a):
            pass

    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(H, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1], hits
    srv.shutdown()


def make_out(tmp_path, base):
    out = tmp_path / "out"
    (out / "data").mkdir(parents=True)
    cards = [{"slug": n, "name": n, "url": "%s/%s/" % (base, n)} for n in list(PAGES) + ["clean"]]
    (out / "data" / "competitors.json").write_text(json.dumps(cards), encoding="utf-8")
    return out


def shoot(out, *extra):
    return subprocess.run([NODE, str(NODE_DIR / "shoot_competitors.mjs"), str(out), "--delay", "0", "--timeout", "15000", *extra, "--node-dir", PW_DIR],
                          capture_output=True, text=True, timeout=300)


@needs_pw
def test_fb031_no_clicks_by_default_banners_hidden(tmp_path, site):
    base, hits = site
    out = make_out(tmp_path, base)
    r = shoot(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert hits == [], hits                                                                     # ни одного клика «Принять»
    cards = {c["slug"]: c for c in json.loads((out / "data" / "competitors.json").read_text(encoding="utf-8"))}
    for name in PAGES:
        assert cards[name]["cookie"] == "hidden", (name, cards[name])
        assert cards[name]["shot"] and not cards[name]["shot_blocked"]
        assert red_pixels(out / cards[name]["shot"]) == 0, name                                  # снимок без перекрытия баннером
    assert cards["clean"]["cookie"] == "none"
    assert "скрыто стилем" in r.stdout


@needs_pw
def test_fb031_accept_cookies_flag_clicks(tmp_path, site):
    base, hits = site
    out = make_out(tmp_path, base)
    r = shoot(out, "--only", "onetrust,generic", "--accept-cookies")
    assert r.returncode == 0, r.stdout + r.stderr
    assert sorted(hits) == ["/clicked?/generic/", "/clicked?/onetrust/"], hits
    cards = {c["slug"]: c for c in json.loads((out / "data" / "competitors.json").read_text(encoding="utf-8"))}
    assert cards["onetrust"]["cookie"] == "accepted" and cards["generic"]["cookie"] == "accepted"


def test_fb031_docs():
    src = (NODE_DIR / "shoot_competitors.mjs").read_text(encoding="utf-8")
    assert "--accept-cookies" in src and "cookie: hidden" in src and "accepted" in src
    ref = (SKILL / "references" / "competitors.md").read_text(encoding="utf-8")
    assert "по умолчанию ничего не нажимаем" in ref and "--accept-cookies" in ref and "cookie: hidden" in ref
    assert "`cookie`" in (SKILL / "templates" / "briefs" / "competitor-cards.md").read_text(encoding="utf-8")
