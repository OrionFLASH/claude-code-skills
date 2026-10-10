#!/usr/bin/env node
// Аудит сайта или локально запущенного приложения для product-strategy (только чтение).
//
//   node audit_site.mjs <url> <OUT> [--pages /,/pricing,…] [--max-pages 12] [--mobile] [--locales ru,en]
//                       [--full-page] [--timeout 30000] [--delay 400] [--node-dir <dir>]
//
// Обход: страницы из --pages или ссылки главной в пределах хоста (до --max-pages). Десктоп 1440×900 всегда,
// мобайл 390×844 с --mobile; дополнительные локали из --locales (вторая и далее) — первые 3 страницы на десктопе.
// Пишет: <OUT>/mockups/current/<slug>-<vp>.png, <OUT>/mockups/tokens.css, <OUT>/data/site-audit.json.
// Собирает meta/OG/hreflang/JSON-LD/canonical, тайминги, сторонние домены, имена cookie (без значений),
// design-токены из computed CSS (частотный топ).
// Только чтение: формы не отправляются (навигации не-GET блокируются), клики не выполняются, вход не выполняется,
// загрузки запрещены, диалоги закрываются. file:// разрешён только внутри папки стартового файла.
// Модули: --node-dir | $PS_NODE_DIR | <OUT>/build/node | папка скрипта (каждая — <dir>/node_modules/playwright).
// Код выхода: 0 — готово, 2 — ошибка аргументов, 3 — нет playwright/Chromium.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(HERE, '..', '..');
const USAGE = 'node audit_site.mjs <url> <OUT> [--pages /,/pricing] [--max-pages 12] [--mobile] [--locales ru,en] [--full-page] [--timeout 30000] [--node-dir <dir>]';

function parseArgs(argv, flags) {
  const pos = []; const opt = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') { opt.help = true; continue; }
    if (a.startsWith('--')) {
      const eq = a.indexOf('=');
      const k = eq > 0 ? a.slice(2, eq) : a.slice(2);
      if (eq > 0) opt[k] = a.slice(eq + 1);
      else if (flags.has(k)) opt[k] = true;
      else opt[k] = argv[++i];
    } else pos.push(a);
  }
  return { pos, opt };
}

function loadPlaywright(opt, out) {
  const cands = opt['node-dir'] ? [opt['node-dir']] : [process.env.PS_NODE_DIR, out && path.join(out, 'build', 'node'), HERE].filter(Boolean);
  for (const d of cands) {
    const p = path.join(path.resolve(d), 'node_modules', 'playwright');
    if (fs.existsSync(path.join(p, 'package.json'))) {
      try { return createRequire(import.meta.url)(p); } catch { /* следующий кандидат */ }
    }
  }
  console.error(`нет playwright: python3 ${path.join(SKILL_DIR, 'scripts', 'check_env.py')} --install-node ${out || '<OUT>'}`);
  process.exit(3);
}

async function launch(pw, out) {
  try { return await pw.chromium.launch({ headless: true }); }
  catch (e) {
    console.error('не запустился Chromium: ' + String(e.message || e).split('\n')[0]);
    console.error(`поставьте браузер: python3 ${path.join(SKILL_DIR, 'scripts', 'check_env.py')} --install-node ${out || '<OUT>'}`);
    process.exit(3);
  }
}

// ------------------------------------------------------------ разбор аргументов
const { pos, opt } = parseArgs(process.argv.slice(2), new Set(['mobile', 'full-page']));
if (opt.help || pos.length < 2) { console.log(USAGE); process.exit(opt.help ? 0 : 2); }
const OUT = path.resolve(pos[1]);
let start;
try { start = new URL(pos[0]); } catch { console.error('ошибка: неверный URL ' + pos[0]); process.exit(2); }
if (!['http:', 'https:', 'file:'].includes(start.protocol)) { console.error('ошибка: поддерживаются только http(s):// и file://'); process.exit(2); }
const MAX_PAGES = Math.max(1, parseInt(opt['max-pages'] || '12', 10));
const TIMEOUT = parseInt(opt.timeout || '30000', 10);
const DELAY = parseInt(opt.delay || '400', 10);
const LOCALES = (opt.locales || '').split(',').map((s) => s.trim()).filter(Boolean);
const FULL = !!opt['full-page'];
const DATE = new Date().toISOString().slice(0, 10);

// file:// — корень разрешённой папки
let FILE_ROOT = null;
if (start.protocol === 'file:') {
  const p = fileURLToPath(start);
  if (!fs.existsSync(p)) { console.error('ошибка: нет файла ' + p); process.exit(2); }
  const st = fs.statSync(p);
  FILE_ROOT = fs.realpathSync(st.isDirectory() ? p : path.dirname(p));
  if (st.isDirectory()) {
    if (fs.existsSync(path.join(p, 'index.html'))) start = pathToFileURL(path.join(p, 'index.html'));
    else {
      const htmls = fs.readdirSync(p).filter((f) => /\.html?$/i.test(f) && !f.startsWith('_')).sort();
      if (!htmls.length) { console.error('ошибка: в папке нет HTML-файлов ' + p); process.exit(2); }
      start = pathToFileURL(path.join(p, htmls[0]));
      if (!opt.pages) opt.pages = htmls.join(',');           // папка без index.html — все её HTML-файлы
    }
  }
}
const HOST = start.protocol === 'file:' ? 'file' : start.hostname.replace(/^www\./, '');

const SHOTS = path.join(OUT, 'mockups', 'current');
fs.mkdirSync(SHOTS, { recursive: true });
fs.mkdirSync(path.join(OUT, 'data'), { recursive: true });

function insideRoot(u) {
  try {
    const p = fileURLToPath(u);
    let real; try { real = fs.realpathSync(p); } catch { real = path.resolve(p); }
    return real === FILE_ROOT || real.startsWith(FILE_ROOT + path.sep);
  } catch { return false; }
}

function sameSite(u) {
  if (u.protocol === 'file:') return FILE_ROOT && insideRoot(u.href);
  if (!['http:', 'https:'].includes(u.protocol) || start.protocol === 'file:') return false;
  return u.hostname.replace(/^www\./, '') === HOST;
}

const RISKY = /log-?out|sign-?out|delete|remove|unsubscribe|\/cart|checkout|basket|add-to-cart|purchase|\/pay(ment)?\b|oauth|callback|wp-admin|\/admin|\/api\//i;
const NON_HTML = /\.(pdf|zip|gz|rar|7z|dmg|exe|apk|png|jpe?g|gif|webp|svg|ico|mp4|webm|mp3|wav|json|xml|rss|txt|csv|xlsx?|docx?|pptx?)$/i;

function slugFor(u) {
  if (u.protocol === 'file:') {
    const rel = path.relative(FILE_ROOT, fileURLToPath(u)).replace(/\.html?$/i, '');
    return (rel.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase() || 'home').slice(0, 80);
  }
  const s = (u.pathname + (u.search ? '-' + u.search : '')).replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase();
  return (s || 'home').slice(0, 80);
}

// ------------------------------------------------------------ сбор в странице
const PAGE_INFO = () => {
  const q = (s) => [...document.querySelectorAll(s)];
  const transparent = (c) => !c || c === 'transparent' || /rgba\([^)]*,\s*0\)$/.test(c);
  const add = (o, k, w = 1) => { if (k) o[k] = (o[k] || 0) + w; };
  const T = { bg: {}, text: {}, border: {}, accent: {}, radius: {}, font: {}, shadow: {}, fontSize: {} };
  const els = q('body, body *').slice(0, 6000);
  for (const el of els) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none' || parseFloat(s.opacity) === 0) continue;
    const area = Math.min(r.width * r.height, 1440 * 900);
    if (!transparent(s.backgroundColor)) add(T.bg, s.backgroundColor, area / 1000);
    let tl = 0;
    for (const n of el.childNodes) if (n.nodeType === 3) tl += n.textContent.trim().length;
    if (tl > 1) { add(T.text, s.color, tl); add(T.font, s.fontFamily, tl); add(T.fontSize, s.fontSize, tl); }
    if (parseFloat(s.borderTopWidth) > 0 && s.borderTopStyle !== 'none' && !transparent(s.borderTopColor)) add(T.border, s.borderTopColor, 1);
    if (s.borderTopLeftRadius && s.borderTopLeftRadius !== '0px') add(T.radius, s.borderTopLeftRadius, 1);
    if (s.boxShadow && s.boxShadow !== 'none') add(T.shadow, s.boxShadow, 1);
    if (el.matches('button, a[role=button], input[type=submit], input[type=button], [class*=btn], [class*=button], [class*=cta]')) {
      if (!transparent(s.backgroundColor)) add(T.accent, s.backgroundColor, 3);
    }
    if (el.tagName === 'A' && tl > 1) add(T.accent, s.color, 1);
  }
  const bodyS = getComputedStyle(document.body); const htmlS = getComputedStyle(document.documentElement);
  const effBg = !transparent(bodyS.backgroundColor) ? bodyS.backgroundColor : !transparent(htmlS.backgroundColor) ? htmlS.backgroundColor : 'rgb(255, 255, 255)';
  const rootVars = {};
  try {
    for (const sh of document.styleSheets) {
      let rules; try { rules = sh.cssRules; } catch { continue; }
      for (const r of rules) {
        if (r.selectorText && /(^|,)\s*(:root|html|body)\s*(,|$)/.test(r.selectorText)) {
          for (const p of r.style) if (p.startsWith('--') && Object.keys(rootVars).length < 80) rootVars[p] = r.style.getPropertyValue(p).trim().slice(0, 120);
        }
      }
    }
  } catch { /* недоступные таблицы стилей */ }
  const meta = {}; const og = {}; const tw = {};
  for (const m of q('meta')) {
    const k = m.getAttribute('name') || m.getAttribute('property') || m.getAttribute('http-equiv');
    const v = (m.getAttribute('content') || '').slice(0, 300);
    if (!k) continue;
    if (/^og:/i.test(k)) og[k.toLowerCase()] = v; else if (/^twitter:/i.test(k)) tw[k.toLowerCase()] = v;
    else if (/^(description|keywords|robots|viewport|theme-color|author|generator|application-name|apple-mobile-web-app-title|google-site-verification|yandex-verification)$/i.test(k)) meta[k.toLowerCase()] = /verification/i.test(k) ? '(есть)' : v;
  }
  const jsonldTypes = [];
  for (const s of q('script[type="application/ld+json"]')) {
    try {
      const d = JSON.parse(s.textContent);
      const walk = (x) => { if (Array.isArray(x)) x.forEach(walk); else if (x && typeof x === 'object') { if (x['@type']) jsonldTypes.push([].concat(x['@type']).join(',')); if (x['@graph']) walk(x['@graph']); } };
      walk(d);
    } catch { jsonldTypes.push('(невалидный JSON-LD)'); }
  }
  const nav = performance.getEntriesByType('navigation')[0];
  const res = performance.getEntriesByType('resource');
  const h1 = q('h1')[0];
  const text = (document.body?.innerText || '').replace(/\s+/g, ' ').trim();
  return {
    title: document.title, lang: document.documentElement.lang || '', dir: document.documentElement.dir || '',
    meta, og, twitter: tw,
    canonical: document.querySelector('link[rel=canonical]')?.href || null,
    hreflang: q('link[rel=alternate][hreflang]').map((l) => ({ lang: l.hreflang, href: l.href })).slice(0, 40),
    manifest: document.querySelector('link[rel=manifest]')?.href || null,
    favicon: !!document.querySelector('link[rel~=icon]'),
    jsonld_types: jsonldTypes.slice(0, 30),
    h1: q('h1').map((h) => h.innerText.trim().slice(0, 140)).slice(0, 5),
    h2: q('h2').map((h) => h.innerText.trim().slice(0, 140)).slice(0, 20),
    words: text ? text.split(' ').length : 0,
    text_excerpt: text.slice(0, 1000),
    links_internal: q('a[href]').filter((a) => a.href.startsWith(location.origin)).length,
    links_external: [...new Set(q('a[href]').map((a) => a.href).filter((h) => /^https?:/.test(h) && !h.startsWith(location.origin)).map((h) => { try { return new URL(h).hostname; } catch { return ''; } }))].filter(Boolean).slice(0, 40),
    images: q('img').length, images_no_alt: q('img:not([alt])').length,
    forms: q('form').length, inputs: q('input:not([type=hidden]),textarea,select').length, buttons: q('button').length,
    landmarks: ['header', 'nav', 'main', 'aside', 'footer'].filter((t) => document.querySelector(t)),
    overflow_x: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    scroll: { w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight },
    timing: nav ? { ttfb_ms: Math.round(nav.responseStart), dcl_ms: Math.round(nav.domContentLoadedEventEnd), load_ms: Math.round(nav.loadEventEnd), transfer_kb: Math.round((nav.transferSize || 0) / 1024) } : null,
    resources: { count: res.length, total_kb: Math.round(res.reduce((s, r) => s + (r.transferSize || 0), 0) / 1024) },
    storage_keys: (() => { try { return Object.keys(localStorage).slice(0, 30); } catch { return []; } })(),
    service_worker: !!navigator.serviceWorker?.controller,
    tokens: { counts: T, bodyBg: effBg, bodyColor: bodyS.color, bodyFont: bodyS.fontFamily, bodySize: bodyS.fontSize, h1Font: h1 ? getComputedStyle(h1).fontFamily : null, rootVars },
  };
};

// ------------------------------------------------------------ распознавание сервисов по хостам
const SERVICES = [
  ['analytics', 'Google Analytics / GTM', /google-analytics\.com|googletagmanager\.com|analytics\.google\.com/],
  ['analytics', 'Yandex Metrica', /mc\.yandex\.(ru|com|by|kz)|metrika/],
  ['analytics', 'Amplitude', /amplitude\.com/], ['analytics', 'Mixpanel', /mixpanel\.com|mxpnl\.com/],
  ['analytics', 'PostHog', /posthog\.com/], ['analytics', 'Segment', /segment\.(com|io)/],
  ['analytics', 'Plausible', /plausible\.io/], ['analytics', 'Umami', /umami\./], ['analytics', 'Matomo', /matomo|piwik/],
  ['analytics', 'Cloudflare Web Analytics', /cloudflareinsights\.com/], ['analytics', 'Microsoft Clarity', /clarity\.ms/],
  ['analytics', 'Hotjar', /hotjar\.(com|io)/], ['analytics', 'Heap', /heapanalytics\.com/],
  ['analytics', 'Top Mail.ru', /top-fwz1\.mail\.ru|top\.mail\.ru/], ['analytics', 'LiveInternet', /counter\.yadro\.ru/],
  ['analytics', 'Meta Pixel', /connect\.facebook\.net/], ['analytics', 'VK Pixel', /vk\.com\/rtrg|top-fwz1/],
  ['analytics', 'TikTok Pixel', /analytics\.tiktok\.com/],
  ['ads', 'Google Ads / AdSense', /doubleclick\.net|googlesyndication\.com|adservice\.google|googleadservices\.com/],
  ['ads', 'Yandex Ads', /an\.yandex\.ru|yandex\.ru\/ads|yandexadexchange/], ['ads', 'VK Ads / myTarget', /ad\.mail\.ru|ads\.vk\.com/],
  ['ads', 'Criteo/Taboola/Outbrain', /criteo|taboola|outbrain/], ['ads', 'Carbon/EthicalAds', /carbonads|ethicalads/],
  ['payments', 'Stripe', /stripe\.(com|network)/], ['payments', 'Paddle', /paddle\.com/], ['payments', 'YooKassa', /yookassa|yoomoney/],
  ['payments', 'CloudPayments', /cloudpayments/], ['payments', 'PayPal', /paypal\.com|paypalobjects/], ['payments', 'Lemon Squeezy', /lemonsqueezy/],
  ['crash', 'Sentry', /sentry\.io|sentry-cdn/], ['crash', 'Bugsnag', /bugsnag/], ['crash', 'Datadog', /datadoghq|browser-intake-datadog/],
  ['crash', 'LogRocket', /logrocket/], ['crash', 'New Relic', /nr-data\.net|newrelic/],
  ['support', 'Intercom', /intercom(cdn)?\.(io|com)/], ['support', 'Crisp', /crisp\.chat/], ['support', 'JivoSite', /jivosite|jivo\.ru/],
  ['support', 'Tawk.to', /tawk\.to/], ['support', 'Zendesk', /zdassets|zendesk/], ['support', 'Carrot quest', /carrotquest/],
  ['consent', 'Cookiebot', /cookiebot/], ['consent', 'OneTrust', /onetrust|cookielaw/], ['consent', 'Didomi', /didomi/], ['consent', 'Usercentrics', /usercentrics/],
  ['fonts_cdn', 'Google Fonts', /fonts\.(googleapis|gstatic)\.com/], ['fonts_cdn', 'Adobe Fonts', /typekit/],
  ['fonts_cdn', 'Public CDN', /cdnjs\.cloudflare\.com|jsdelivr\.net|unpkg\.com/],
  ['video', 'YouTube', /youtube\.com|ytimg\.com|youtube-nocookie/], ['video', 'Vimeo', /vimeo/],
];

// ------------------------------------------------------------ токены
function parseColor(c) {
  const m = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/.exec(c || '');
  if (!m) return null;
  let a = m[4] === undefined ? 1 : m[4].endsWith('%') ? parseFloat(m[4]) / 100 : parseFloat(m[4]);
  return [+m[1], +m[2], +m[3], a];
}
const hex2 = (n) => Math.round(n).toString(16).padStart(2, '0');
function toCss(c) {
  const p = parseColor(c);
  if (!p) return c;
  return p[3] >= 0.999 ? `#${hex2(p[0])}${hex2(p[1])}${hex2(p[2])}` : `rgba(${p[0]}, ${p[1]}, ${p[2]}, ${+p[3].toFixed(2)})`;
}
function hsl(c) {
  const p = parseColor(c); if (!p) return null;
  const [r, g, b] = p.slice(0, 3).map((v) => v / 255); const mx = Math.max(r, g, b), mn = Math.min(r, g, b); const l = (mx + mn) / 2;
  const s = mx === mn ? 0 : l > 0.5 ? (mx - mn) / (2 - mx - mn) : (mx - mn) / (mx + mn);
  return { s, l, a: p[3] };
}
function lum(c) {
  const p = parseColor(c); if (!p) return 0.5;
  const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(p[0]) + 0.7152 * f(p[1]) + 0.0722 * f(p[2]);
}
function contrast(a, b) { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
function mix(a, b, t) { const p = parseColor(a), q = parseColor(b); if (!p || !q) return a; return `rgb(${Math.round(p[0] + (q[0] - p[0]) * t)}, ${Math.round(p[1] + (q[1] - p[1]) * t)}, ${Math.round(p[2] + (q[2] - p[2]) * t)})`; }
function dist(a, b) { const p = parseColor(a), q = parseColor(b); if (!p || !q) return a === b ? 0 : 999; return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]); }
const top = (o, n = 12) => Object.entries(o).sort((a, b) => b[1] - a[1]).slice(0, n);
function merge(into, from) { for (const [k, v] of Object.entries(from || {})) into[k] = (into[k] || 0) + v; }

function deriveTokens(pagesTok) {
  const C = { bg: {}, text: {}, border: {}, accent: {}, radius: {}, font: {}, shadow: {}, fontSize: {} };
  const bodyBg = {}, h1Font = {}, rootVars = {};
  for (const t of pagesTok) {
    for (const k of Object.keys(C)) merge(C[k], t.counts[k]);
    bodyBg[t.bodyBg] = (bodyBg[t.bodyBg] || 0) + 1;
    if (t.h1Font) h1Font[t.h1Font] = (h1Font[t.h1Font] || 0) + 1;
    Object.assign(rootVars, t.rootVars);
  }
  const bg = top(bodyBg, 1)[0]?.[0] || 'rgb(255, 255, 255)';
  const textTop = top(C.text, 20).map(([c]) => c).filter((c) => (hsl(c)?.a ?? 1) >= 0.5);
  const text = textTop.find((c) => contrast(c, bg) >= 4.5) || textTop.find((c) => contrast(c, bg) >= 3)
    || pagesTok[0]?.bodyColor || (lum(bg) > 0.5 ? 'rgb(17, 17, 17)' : 'rgb(240, 240, 240)');
  const solid = (c) => (hsl(c)?.a ?? 1) >= 0.5;
  const accentCand = top(C.accent, 30).map(([c]) => c).filter((c) => { const h = hsl(c); return h && h.s >= 0.25 && h.l > 0.15 && h.l < 0.85 && solid(c) && dist(c, bg) > 60 && dist(c, text) > 40; });
  const satAny = [...top(C.text, 30), ...top(C.bg, 30)].map(([c]) => c).filter((c) => { const h = hsl(c); return h && h.s >= 0.35 && h.l > 0.2 && h.l < 0.8 && solid(c) && dist(c, bg) > 60; });
  const accent = accentCand[0] || satAny[0] || text;
  const muted = textTop.find((c) => c !== text && dist(c, text) > 25 && contrast(c, bg) >= 2.5 && (hsl(c)?.s ?? 1) < 0.3) || mix(text, bg, 0.4);
  const surface = top(C.bg, 20).map(([c]) => c).find((c) => dist(c, bg) > 6 && solid(c) && (hsl(c)?.s ?? 1) < 0.4 && dist(c, accent) > 30) || bg;
  const border = top(C.border, 10).map(([c]) => c).find((c) => dist(c, bg) > 6) || mix(text, bg, 0.85);
  const radii = top(C.radius, 12).map(([r]) => parseFloat(r)).filter((r) => r > 0 && r <= 48);
  const radius = radii.find((r) => r <= 24) ?? 8;
  const radiusLg = Math.max(radius, ...radii.slice(0, 6).filter((r) => r <= 32));
  const font = top(C.font, 1)[0]?.[0] || 'system-ui, sans-serif';
  const fontHeading = top(h1Font, 1)[0]?.[0] || font;
  const fontSize = top(C.fontSize, 1)[0]?.[0] || '16px';
  const shadow = top(C.shadow, 1)[0]?.[0] || 'none';
  const vars = {
    '--c-bg': toCss(bg), '--c-surface': toCss(surface), '--c-text': toCss(text), '--c-muted': toCss(muted),
    '--c-accent': toCss(accent), '--c-on-accent': lum(accent) > 0.45 ? '#111111' : '#ffffff', '--c-border': toCss(border),
    '--radius': `${radius}px`, '--radius-lg': `${radiusLg}px`, '--font': font, '--font-heading': fontHeading,
    '--font-size': fontSize, '--shadow': shadow,
  };
  const rows = (o, n) => top(o, n).map(([k, v]) => [toCss(k), Math.round(v)]);
  return { vars, top: { backgrounds: rows(C.bg, 10), text: rows(C.text, 10), accents: rows(C.accent, 10), borders: rows(C.border, 6), radii: top(C.radius, 8), fonts: top(C.font, 5), font_sizes: top(C.fontSize, 6), shadows: top(C.shadow, 4) }, root_vars: rootVars };
}

function tokensCss(tok, src) {
  const lines = [`/* Токены интерфейса ${src}, снято audit_site.mjs ${DATE}.`, '   Частотный анализ computed CSS — проверьте глазами по скриншотам mockups/current/. */', ':root {'];
  for (const [k, v] of Object.entries(tok.vars)) lines.push(`  ${k}: ${String(v).replace(/[;{}]/g, '')};`);
  lines.push('}', '');
  return lines.join('\n');
}

// ------------------------------------------------------------ основной сценарий
const pw = loadPlaywright(opt, OUT);
const browser = await launch(pw, OUT);
const blocked = [];

async function newContext(kind, locale) {
  const base = { acceptDownloads: false, serviceWorkers: 'block', locale: locale || undefined, timezoneId: 'UTC',
    extraHTTPHeaders: locale ? { 'Accept-Language': locale } : undefined };
  const ctx = await browser.newContext(kind === 'mobile'
    ? { ...base, viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2,
        userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1' }
    : { ...base, viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await ctx.route('**/*', (route) => {
    const req = route.request(); const u = req.url();
    if (u.startsWith('file:')) {
      if (!FILE_ROOT || !insideRoot(u)) { blocked.push({ url: u.slice(0, 160), reason: 'file:// вне разрешённой папки' }); return route.abort('accessdenied'); }
      return route.continue();
    }
    if (req.isNavigationRequest() && !['GET', 'HEAD'].includes(req.method())) { blocked.push({ url: u.slice(0, 160), reason: 'навигация ' + req.method() + ' (форма) заблокирована' }); return route.abort('blockedbyclient'); }
    return route.continue();
  });
  return ctx;
}

async function auditPage(ctx, url, vp, slugSuffix) {
  const page = await ctx.newPage();
  page.on('dialog', (d) => d.dismiss().catch(() => {}));
  const hosts = {}; const failed = []; const consoleErrors = []; let reqCount = 0;
  page.on('request', (r) => { reqCount++; try { const h = new URL(r.url()).hostname; if (h) hosts[h] = (hosts[h] || 0) + 1; } catch { /* data: */ } });
  page.on('response', (r) => { if (r.status() >= 400) { try { const u = new URL(r.url()); failed.push({ status: r.status(), url: (u.origin + u.pathname).slice(0, 160) }); } catch { /* */ } } });
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });
  page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + String(e).slice(0, 200)));
  const u = new URL(url);
  const slug = slugFor(u) + (slugSuffix ? '-' + slugSuffix : '');
  let status = null; let error = null; const t0 = Date.now();
  try {
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: TIMEOUT });
    status = resp ? resp.status() : (u.protocol === 'file:' ? 200 : null);
    await page.waitForLoadState('networkidle', { timeout: Math.min(10000, TIMEOUT) }).catch(() => {});
    await page.waitForTimeout(800);
  } catch (e) { error = String(e.message || e).split('\n')[0].slice(0, 200); }
  const wall = Date.now() - t0;
  const info = await page.evaluate(PAGE_INFO).catch((e) => ({ eval_error: String(e).slice(0, 200) }));
  const shotRel = path.posix.join('mockups', 'current', `${slug}-${vp}.png`);
  let shot = null;
  try {
    const so = { path: path.join(OUT, shotRel), timeout: 20000 };
    if (FULL && info.scroll) { so.fullPage = true; so.clip = { x: 0, y: 0, width: page.viewportSize().width, height: Math.min(info.scroll.h, 8000) }; }
    await page.screenshot(so); shot = shotRel;
  } catch (e) { error = (error ? error + '; ' : '') + 'screenshot: ' + String(e.message || e).split('\n')[0].slice(0, 120); }
  const third = Object.keys(hosts).filter((h) => h && h.replace(/^www\./, '') !== HOST && !h.endsWith('.' + HOST));
  const tokens = info.tokens; delete info.tokens;
  const finalUrl = page.url();
  await page.close();
  const rec = { path: u.protocol === 'file:' ? '/' + path.relative(FILE_ROOT, fileURLToPath(u)).split(path.sep).join('/') : u.pathname + u.search,
    url, final_url: finalUrl, viewport: vp, locale: slugSuffix || LOCALES[0] || null, status, error, wall_ms: wall, screenshot: shot,
    requests: reqCount, third_party: third.sort(), failed: failed.slice(0, 20), console_errors: consoleErrors.slice(0, 20), ...info };
  console.log(`${vp.padEnd(7)} ${rec.path} → ${status ?? error} | ${(info.title || '').slice(0, 50)} | ${wall} мс | 3p ${third.length}`);
  return { rec, tokens, hosts };
}

async function discover() {
  if (opt.pages) {
    return opt.pages.split(',').map((p) => p.trim()).filter(Boolean).map((p) => new URL(p.replace(/^\//, start.protocol === 'file:' ? '' : '/'), start).href).slice(0, MAX_PAGES);
  }
  const ctx = await newContext('desktop', LOCALES[0]);
  const page = await ctx.newPage();
  page.on('dialog', (d) => d.dismiss().catch(() => {}));
  let links = [];
  try {
    await page.goto(start.href, { waitUntil: 'domcontentloaded', timeout: TIMEOUT });
    await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
    links = await page.evaluate(() => [...document.querySelectorAll('a[href]')].map((a) => a.href));
  } catch (e) { console.error('главная не открылась: ' + String(e.message || e).split('\n')[0]); }
  await ctx.close();
  const counts = new Map();
  for (const h of links) {
    let u; try { u = new URL(h); } catch { continue; }
    u.hash = ''; u.search = '';
    if (!sameSite(u) || NON_HTML.test(u.pathname) || RISKY.test(u.pathname)) continue;
    if (u.protocol === 'file:' && !/\.html?$/i.test(u.pathname)) continue;
    counts.set(u.href, (counts.get(u.href) || 0) + 1);
  }
  const home = new URL(start.href); home.hash = '';
  const ordered = [...counts.entries()].filter(([h]) => h !== home.href).sort((a, b) => b[1] - a[1] || a[0].length - b[0].length).map(([h]) => h);
  return [home.href, ...ordered].slice(0, MAX_PAGES);
}

const urls = await discover();
console.log(`страниц к обходу: ${urls.length}`);
const pages = []; const tokList = []; const allHosts = {}; const cookieMap = new Map();
const plan = [['desktop', LOCALES[0], urls, null]];
if (opt.mobile) plan.push(['mobile', LOCALES[0], urls, null]);
for (const loc of LOCALES.slice(1)) plan.push(['desktop', loc, urls.slice(0, 3), loc]);
for (const [vp, loc, list, suffix] of plan) {
  const ctx = await newContext(vp, loc);
  for (const u of list) {
    const { rec, tokens, hosts } = await auditPage(ctx, u, vp, suffix);
    pages.push(rec);
    if (tokens && !rec.error) tokList.push(tokens);
    merge(allHosts, hosts);
    if (DELAY) await new Promise((r) => setTimeout(r, DELAY));
  }
  const cookies = await ctx.cookies().catch(() => []);
  for (const c of cookies) cookieMap.set(c.name + '@' + c.domain, { name: c.name, domain: c.domain, http_only: c.httpOnly, secure: c.secure, same_site: c.sameSite });
  await ctx.close();
}
await browser.close();

const services = {};
for (const h of Object.keys(allHosts)) for (const [cat, name, rx] of SERVICES) if (rx.test(h)) { services[cat] = services[cat] || []; if (!services[cat].includes(name)) services[cat].push(name); }
const tokens = tokList.length ? deriveTokens(tokList) : null;
const thirdAll = Object.fromEntries(Object.entries(allHosts).filter(([h]) => h && h.replace(/^www\./, '') !== HOST && !h.endsWith('.' + HOST)).sort((a, b) => b[1] - a[1]));
const result = {
  url: start.href, host: HOST, date: DATE, tool: 'audit_site.mjs',
  viewports: plan.map(([vp, loc]) => ({ viewport: vp, locale: loc || null, size: vp === 'mobile' ? '390x844' : '1440x900' })),
  pages, third_party_domains: thirdAll, services, cookies: [...cookieMap.values()],
  tokens, tokens_css: tokens ? 'mockups/tokens.css' : null, blocked: blocked.slice(0, 50),
  summary: {
    pages: pages.length, errors: pages.filter((p) => p.error || (p.status && p.status >= 400)).length,
    no_description: pages.filter((p) => !p.meta?.description).length, no_canonical: pages.filter((p) => !p.canonical).length,
    no_og: pages.filter((p) => !p.og || !Object.keys(p.og).length).length, no_h1: pages.filter((p) => !p.h1?.length).length,
    overflow_x: pages.filter((p) => p.overflow_x).length, console_errors: pages.reduce((s, p) => s + (p.console_errors?.length || 0), 0),
    jsonld_types: [...new Set(pages.flatMap((p) => p.jsonld_types || []))], hreflang: [...new Set(pages.flatMap((p) => (p.hreflang || []).map((h) => h.lang)))],
  },
  notes: ['Только чтение: формы не отправлялись, клики не выполнялись, вход не выполнялся; значения cookie не сохранялись.'],
};
fs.writeFileSync(path.join(OUT, 'data', 'site-audit.json'), JSON.stringify(result, null, 2));
if (tokens) fs.writeFileSync(path.join(OUT, 'mockups', 'tokens.css'), tokensCss(tokens, start.protocol === 'file:' ? 'локальных файлов' : start.origin));
console.log(`готово: ${pages.length} снимков → ${path.join(OUT, 'data', 'site-audit.json')}${tokens ? ', mockups/tokens.css' : ''}`);
