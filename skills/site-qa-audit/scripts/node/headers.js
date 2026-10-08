'use strict';
// Пассивные проверки по HTTP: заголовки безопасности, HTTPS/HSTS, кэш, сжатие, robots.txt, sitemap,
// доступность sourcemaps, mixed content в HTML. Только GET/HEAD, без атак и перебора.
// node headers.js URL [URL...] [--urls-file f] [--throttle 800] [--out headers.json]
const { parseArgs, sleep, writeOut, urlsFromArgs } = require('./lib');

const UA = 'Mozilla/5.0 site-qa-audit (passive check)';
const SEC_HEADERS = ['strict-transport-security', 'content-security-policy', 'x-content-type-options', 'x-frame-options',
  'referrer-policy', 'permissions-policy', 'cross-origin-opener-policy', 'cross-origin-resource-policy', 'cross-origin-embedder-policy'];
const LEAK_HEADERS = ['server', 'x-powered-by', 'x-aspnet-version', 'x-aspnetmvc-version', 'x-generator', 'via'];

async function get(url, method = 'GET', redirect = 'follow') {
  const t0 = Date.now();
  const res = await fetch(url, { method, redirect, headers: { 'user-agent': UA, 'accept-encoding': 'gzip, br, deflate' } });
  const body = method === 'GET' ? await res.text() : '';
  return { res, body, ms: Date.now() - t0 };
}

function headerObj(res) { const o = {}; res.headers.forEach((v, k) => { o[k] = v; }); return o; }

async function checkPage(url) {
  const out = { url, issues: [] };
  const issue = (id, severity, msg, data) => out.issues.push({ id, severity, msg, ...(data ? { data } : {}) });
  // Редирект http -> https
  const u = new URL(url);
  if (u.protocol === 'https:') {
    try {
      const plain = await fetch('http://' + u.host + u.pathname, { redirect: 'manual', headers: { 'user-agent': UA } });
      out.httpRedirect = { status: plain.status, location: plain.headers.get('location') };
      if (!(plain.status >= 300 && plain.status < 400 && (plain.headers.get('location') || '').startsWith('https://')))
        issue('http-no-redirect', 'medium', 'HTTP-версия не перенаправляет на HTTPS', out.httpRedirect);
    } catch (e) { out.httpRedirect = { error: String(e.message || e) }; }
  } else issue('no-https', 'high', 'Страница отдаётся по HTTP');
  const { res, body, ms } = await get(url);
  const h = headerObj(res);
  Object.assign(out, { status: res.status, finalUrl: res.url, redirected: res.redirected, timeMs: ms, bytes: body.length,
    contentType: h['content-type'], encoding: h['content-encoding'] || null, cacheControl: h['cache-control'] || null,
    security: Object.fromEntries(SEC_HEADERS.map(k => [k, h[k] || null])),
    leaks: Object.fromEntries(LEAK_HEADERS.filter(k => h[k]).map(k => [k, h[k]])) });
  if (res.status >= 400) issue('status', res.status >= 500 ? 'high' : 'medium', `HTTP ${res.status}`);
  if (!h['strict-transport-security'] && url.startsWith('https')) issue('no-hsts', 'medium', 'Нет Strict-Transport-Security');
  if (!h['content-security-policy']) issue('no-csp', 'low', 'Нет Content-Security-Policy');
  if (h['content-security-policy'] && /'unsafe-inline'|'unsafe-eval'/.test(h['content-security-policy'])) issue('weak-csp', 'low', 'CSP содержит unsafe-inline/unsafe-eval');
  if (!h['x-content-type-options']) issue('no-xcto', 'low', 'Нет X-Content-Type-Options: nosniff');
  if (!h['x-frame-options'] && !/frame-ancestors/.test(h['content-security-policy'] || '')) issue('no-clickjacking', 'low', 'Нет X-Frame-Options и frame-ancestors');
  if (!h['referrer-policy']) issue('no-referrer-policy', 'info', 'Нет Referrer-Policy');
  if (Object.entries(out.leaks).some(([k, v]) => k !== 'via' && /\/\s*v?\d+(\.\d+)+|\bv?\d+\.\d+\.\d+/.test(v))) issue('version-leak', 'low', 'Заголовки раскрывают версии ПО', out.leaks);
  if (!out.encoding && body.length > 2048 && /text|json|javascript/.test(h['content-type'] || '')) issue('no-compression', 'medium', 'Ответ не сжат (gzip/br)');
  if (/set-cookie/.test(Object.keys(h).join(' '))) {
    const c = h['set-cookie'];
    if (!/secure/i.test(c) || !/httponly/i.test(c) || !/samesite/i.test(c)) issue('cookie-flags', 'low', 'Cookie без Secure/HttpOnly/SameSite (проверить вручную, что это не служебная cookie)');
  }
  if (url.startsWith('https')) {
    // Только загружаемые ресурсы: src, <link href>, action форм. Обычные ссылки <a> — не mixed content.
    const mixed = [...body.matchAll(/<(?:script|img|iframe|audio|video|source|embed|link|form)\b[^>]*\b(?:src|href|action)\s*=\s*["'](http:\/\/[^"']+)/gi)].map(m => m[1])
      .filter(x => !/^http:\/\/(www\.)?w3\.org/.test(x));
    if (mixed.length) issue('mixed-content', 'medium', 'HTTP-ресурсы на HTTPS-странице', mixed.slice(0, 20));
  }
  // Скрипты страницы и их sourcemaps
  const scripts = [...body.matchAll(/<script[^>]+src=["']([^"']+)["']/gi)].map(m => new URL(m[1], res.url).href).slice(0, 15);
  out.sourcemaps = [];
  for (const s of scripts) {
    if (new URL(s).host !== new URL(res.url).host) continue;
    try {
      const js = await get(s);
      const m = js.body.match(/\/\/# sourceMappingURL=([^\s]+)\s*$/m);
      const mapUrl = m && !m[1].startsWith('data:') ? new URL(m[1], s).href : s + '.map';
      const head = await fetch(mapUrl, { method: 'HEAD', headers: { 'user-agent': UA } });
      if (head.ok) out.sourcemaps.push(mapUrl);
      const secret = [...js.body.matchAll(/(api[_-]?key|secret|password|token)["']?\s*[:=]\s*["']([A-Za-z0-9_\-]{20,})["']/gi)]
        .map(m => m[2]).find(v => /[a-z]/.test(v) && /[A-Z]/.test(v) && /\d/.test(v));  // смешанный набор символов, не CONSTANT_NAME
      if (secret)
        issue('secret-in-js', 'high', 'Похоже на секрет в клиентском JS (проверить вручную, замаскировать в отчёте)', { script: s });
      await sleep(200);
    } catch { /* ресурс недоступен — не ошибка проверки */ }
  }
  if (out.sourcemaps.length) issue('public-sourcemaps', 'low', 'Публично доступны sourcemaps', out.sourcemaps);
  return out;
}

async function checkSite(origin) {
  const site = { origin };
  try {
    const r = await get(origin + '/robots.txt');
    site.robots = { status: r.res.status, sitemaps: [...r.body.matchAll(/^sitemap:\s*(\S+)/gim)].map(m => m[1]),
      disallowAll: /^user-agent:\s*\*[\s\S]*?^disallow:\s*\/\s*$/im.test(r.body) };
  } catch (e) { site.robots = { error: String(e.message || e) }; }
  const smUrl = (site.robots.sitemaps && site.robots.sitemaps[0]) || origin + '/sitemap.xml';
  try {
    const r = await get(smUrl);
    site.sitemap = { url: smUrl, status: r.res.status, urls: (r.body.match(/<loc>/g) || []).length };
  } catch (e) { site.sitemap = { url: smUrl, error: String(e.message || e) }; }
  try {
    const r = await get(origin + '/.well-known/security.txt');
    site.securityTxt = r.res.status === 200;
  } catch { site.securityTxt = false; }
  return site;
}

(async () => {
  const args = parseArgs(process.argv.slice(2), { throttle: '800' });
  const urls = urlsFromArgs(args);
  const origins = [...new Set(urls.map(u => new URL(u).origin))];
  const sites = [];
  for (const o of origins) { sites.push(await checkSite(o)); await sleep(+args.throttle); }
  const pages = [];
  for (const u of urls) {
    try { pages.push(await checkPage(u)); } catch (e) { pages.push({ url: u, error: String(e.message || e) }); }
    await sleep(+args.throttle);
  }
  writeOut(args.out, { tool: 'headers', sites, pages });
})().catch(e => { console.error(e); process.exit((e && e.exitCode) || 1); });
