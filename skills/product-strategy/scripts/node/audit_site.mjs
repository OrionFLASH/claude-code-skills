#!/usr/bin/env node
// Аудит сайта или локально запущенного приложения для product-strategy (только чтение).
//
//   node audit_site.mjs <url> <OUT> [--pages /,/#/demo,/pricing] [--routes-from links|hash] [--max-pages 12] [--mobile]
//                       [--themes light,dark] [--theme-toggle <selector>] [--click-safe "sel1,sel2"] [--max-clicks 6]
//                       [--locales ru,en] [--full-page] [--timeout 30000] [--delay 400] [--node-dir <dir>]
//
// Обход: страницы из --pages или ссылки главной в пределах хоста (до --max-pages); --routes-from hash — хэш-маршруты
// SPA (a[href^="#/"], a[href^="#!/"] главной). Слаг файла — из полного адреса, включая query и #… («/#/demo» →
// «hash-demo»); совпавшие слаги получают суффикс -2, -3 — файлы не перезаписываются.
// Десктоп 1440×900 всегда, мобайл 390×844 с --mobile; --themes light,dark — снимки обеих тем: тёмная через
// prefers-color-scheme: dark, иначе клик по --theme-toggle, иначе атрибут/класс тёмной темы из CSS продукта
// ([data-theme=dark], .dark); суффикс файла -dark. Доп. локали из --locales (вторая и далее) — 3 страницы на десктопе.
// Клики: по умолчанию нет. --click-safe "sel1,sel2" (можно пустым: --click-safe=) включает клики только по элементам
// этих селекторов и с атрибутом data-audit-safe (data-audit-safe="false" — нельзя); после клика — снимок раскрытого
// состояния <slug>-<vp>--<n>.png, затем перезагрузка страницы. Запреты сохраняются: формы и поля, выход, корзина,
// оплата, OAuth, admin, api, удаление, внешние ссылки, download, новые окна — не кликаются; навигации на такие
// адреса и не-GET навигации блокируются.
// Пишет: <OUT>/mockups/current/<slug>-<vp>.png, <OUT>/mockups/tokens.css, <OUT>/data/site-audit.json.
// tokens.css: CSS custom properties продукта из :root и тёмной темы ([data-theme=dark], .dark, @media
// (prefers-color-scheme: dark)) — через document.styleSheets (CORS-таблицы пропускаются) и computed style; плюс роли
// --c-bg … --c-border (частотный анализ computed CSS) для обеих тем. Тёмный блок идёт первым, с большей
// специфичностью и значениями rgb(): простые парсеры (charts.py, build_deck_json.py) берут светлую тему.
// Собирает meta/OG/hreflang/JSON-LD/canonical, тайминги, сторонние домены, имена cookie (без значений).
// Только чтение: формы не отправляются (навигации не-GET блокируются), вход не выполняется,
// загрузки запрещены, диалоги закрываются. file:// разрешён только внутри папки стартового файла.
// Модули: --node-dir | $PS_NODE_DIR | <OUT>/build/node | ~/.cache/product-strategy/node | папка скрипта (каждая — <dir>/node_modules/playwright).
// Код выхода: 0 — готово, 2 — ошибка аргументов, 3 — нет playwright/Chromium.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(HERE, '..', '..');
const USAGE = 'node audit_site.mjs <url> <OUT> [--pages /,/#/demo] [--routes-from links|hash] [--max-pages 12] [--mobile] [--themes light,dark] [--theme-toggle <sel>] [--click-safe "sel1,sel2"] [--max-clicks 6] [--locales ru,en] [--full-page] [--timeout 30000] [--node-dir <dir>]';

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
      else if (i + 1 >= argv.length || argv[i + 1].startsWith('--')) opt[k] = '';
      else opt[k] = argv[++i];
    } else pos.push(a);
  }
  return { pos, opt };
}

function loadPlaywright(opt, out) {
  const cands = opt['node-dir'] ? [opt['node-dir']] : [process.env.PS_NODE_DIR, out && path.join(out, 'build', 'node'), path.join(process.env.HOME || process.env.USERPROFILE || '', '.cache', 'product-strategy', 'node'), HERE].filter(Boolean);
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
const THEMES = [...new Set((opt.themes || 'light').split(',').map((s) => s.trim().toLowerCase()).filter((t) => t === 'light' || t === 'dark'))];
if (!THEMES.length) THEMES.push('light');
const THEME_TOGGLE = opt['theme-toggle'] || null;
const CLICK = Object.prototype.hasOwnProperty.call(opt, 'click-safe');
const CLICK_SELS = CLICK ? String(opt['click-safe'] || '').split(',').map((s) => s.trim()).filter(Boolean) : [];
const MAX_CLICKS = Math.max(0, parseInt(opt['max-clicks'] || '6', 10));
const ROUTES_FROM = (opt['routes-from'] || 'links').toLowerCase();
if (!['links', 'hash'].includes(ROUTES_FROM)) { console.error('ошибка: --routes-from links|hash'); process.exit(2); }
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

const clean = (x) => x.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase();
function slugFor(u) {
  const hash = u.hash && u.hash.length > 1 ? 'hash-' + (clean(u.hash.replace(/^#!?\/?/, '')) || 'root') : '';
  let base;
  if (u.protocol === 'file:') base = clean(path.relative(FILE_ROOT, fileURLToPath(u)).replace(/\.html?$/i, ''));
  else base = clean(u.pathname + (u.search ? '-' + u.search : ''));
  if (base === 'index' && hash) base = '';
  return ([base, hash].filter(Boolean).join('-') || 'home').slice(0, 80);
}
const SLUGS = new Map(); const USED = new Set();
function uniqueSlug(href) {
  if (SLUGS.has(href)) return SLUGS.get(href);
  const base = slugFor(new URL(href)); let s = base; let n = 2;
  while (USED.has(s)) s = `${base}-${n++}`;
  USED.add(s); SLUGS.set(href, s);
  return s;
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
  // CSS custom properties: :root/html/body (светлая) и тёмная тема ([data-theme=dark], .dark, @media dark)
  const cssv = { root: {}, dark: {}, darkSel: null, sheets: 0, blocked: 0 };
  const ROOT_SEL = /^(?::root|html|body|:host|\[data-theme=["']?light["']?\]|(?::root|html)\[data-theme=["']?light["']?\]|(?:html|:root|body)?\.(?:light|theme-light))$/i;
  const DARK_SEL = /\[(data-(?:theme|color-scheme|mode|bs-theme))\s*=\s*["']?dark["']?\]|(?:^|[\s>(])(?:html|:root|body)?\.(dark|theme-dark|dark-mode|dark-theme)\b/i;
  const take = (style, target) => { for (const pr of style) if (pr.startsWith('--') && (pr in target || Object.keys(target).length < 400)) target[pr] = style.getPropertyValue(pr).trim().slice(0, 200); };
  const walkRules = (rules, inDark, depth) => {
    if (depth > 8 || !rules) return;
    for (const r of rules) {
      try {
        if (r.media && r.cssRules) { walkRules(r.cssRules, inDark || /prefers-color-scheme\s*:\s*dark/i.test(r.media.mediaText), depth + 1); continue; }
        if (r.styleSheet) { try { walkRules(r.styleSheet.cssRules, inDark, depth + 1); } catch { cssv.blocked++; } continue; }
        if (r.cssRules && !r.selectorText) { walkRules(r.cssRules, inDark, depth + 1); continue; }
        if (!r.selectorText || !r.style) continue;
        const sels = r.selectorText.split(',').map((x) => x.trim());
        const dm = sels.map((x) => DARK_SEL.exec(x)).find(Boolean);
        if (dm) { take(r.style, cssv.dark); if (!cssv.darkSel) cssv.darkSel = dm[1] ? { type: 'attr', name: dm[1] } : { type: 'class', name: dm[2] }; }
        else if (sels.some((x) => ROOT_SEL.test(x))) { take(r.style, inDark ? cssv.dark : cssv.root); if (inDark && !cssv.darkSel) cssv.darkSel = { type: 'media' }; }
      } catch { /* правило недоступно */ }
    }
  };
  for (const sh of document.styleSheets) { let rules; try { rules = sh.cssRules; } catch { cssv.blocked++; continue; } cssv.sheets++; walkRules(rules, false, 0); }
  const csRoot = getComputedStyle(document.documentElement); const csBody = getComputedStyle(document.body);
  cssv.computed = {};
  for (const n of new Set([...Object.keys(cssv.root), ...Object.keys(cssv.dark)])) {
    const v = (csRoot.getPropertyValue(n) || csBody.getPropertyValue(n) || '').trim();
    if (v) cssv.computed[n] = v.slice(0, 200);
  }
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
    tokens: { counts: T, bodyBg: effBg, bodyColor: bodyS.color, bodyFont: bodyS.fontFamily, bodySize: bodyS.fontSize, h1Font: h1 ? getComputedStyle(h1).fontFamily : null, rootVars, cssVars: cssv },
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
  const hx = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(String(c || '').trim());
  if (hx) { const h = hx[1].length === 3 ? hx[1].split('').map((x) => x + x).join('') : hx[1]; return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), 1]; }
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

// ---- цвета в любом виде (#rgb, #rrggbb(aa), rgb()/rgba()) → [r,g,b,a]
function normColor(v) {
  const t = String(v || '').trim().toLowerCase();
  let m = /^#([0-9a-f]{3,4})$/.exec(t);
  if (m) { const h = m[1]; return [parseInt(h[0] + h[0], 16), parseInt(h[1] + h[1], 16), parseInt(h[2] + h[2], 16), h[3] ? parseInt(h[3] + h[3], 16) / 255 : 1]; }
  m = /^#([0-9a-f]{6})([0-9a-f]{2})?$/.exec(t);
  if (m) return [parseInt(m[1].slice(0, 2), 16), parseInt(m[1].slice(2, 4), 16), parseInt(m[1].slice(4, 6), 16), m[2] ? parseInt(m[2], 16) / 255 : 1];
  return parseColor(t.replace(/\s*\/\s*/, ', '));
}
const sameColor = (a, b) => { const p = normColor(a), q = normColor(b); return !!(p && q) && Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]) < 2 && Math.abs(p[3] - q[3]) < 0.02; };
function rgbStr(v) {            // тёмные значения — в rgb(): старые парсеры палитры (только hex) их не возьмут
  const p = normColor(v);
  if (!p) return v;
  return p[3] >= 0.999 ? `rgb(${p[0]} ${p[1]} ${p[2]})` : `rgb(${p[0]} ${p[1]} ${p[2]} / ${+p[3].toFixed(2)})`;
}
const hexOf = (v) => { const p = normColor(v); return p ? toCss(`rgba(${p[0]}, ${p[1]}, ${p[2]}, ${p[3]})`) : v; };
const COLOR_ROLES = ['--c-bg', '--c-surface', '--c-text', '--c-muted', '--c-accent', '--c-on-accent', '--c-border'];
const ROLE_HINT = { '--c-bg': /bg|background|paper|canvas|base|page/, '--c-surface': /surface|card|panel|paper|elev/, '--c-text': /text|ink|fg|foreground|body/,
  '--c-muted': /muted|subtle|secondary|ink-2|ink-3|text-2/, '--c-accent': /accent|primary|brand|link|cobalt/, '--c-on-accent': /on-|contrast/, '--c-border': /border|line|divider|stroke/ };
const SYNTH_DARK = { '--c-bg': '#111316', '--c-surface': '#191c20', '--c-text': '#e7e9ec', '--c-muted': '#a2a9b3', '--c-border': '#30353c' };

function lighten(c, bg) {
  let x = c;
  for (let t = 0; t <= 1.0001 && contrast(x, bg) < 4.5; t += 0.1) x = mix(c, 'rgb(255, 255, 255)', t);
  return x;
}

// Итоговые токены: роли (обе темы) + переменные продукта (обе темы) и откуда взяты
function buildTokenSets(lightTok, darkTok, cssList, darkCssList) {
  const root = {}, darkRaw = {}, compLight = {}, compDark = {};
  let darkSel = null, blocked = 0, sheets = 0;
  for (const c of cssList) {
    Object.assign(root, c.root); Object.assign(darkRaw, c.dark);
    for (const [k, v] of Object.entries(c.computed || {})) if (!(k in compLight)) compLight[k] = v;
    darkSel = darkSel || c.darkSel; blocked += c.blocked || 0; sheets += c.sheets || 0;
  }
  for (const c of darkCssList) for (const [k, v] of Object.entries(c.computed || {})) if (!(k in compDark)) compDark[k] = v;
  const names = [...new Set([...Object.keys(root), ...Object.keys(darkRaw)])].sort();
  const prodLight = {}, prodDark = {};
  for (const n of names) {
    const lv = compLight[n] ?? root[n];
    if (lv !== undefined && lv !== '') prodLight[n] = lv;
    const dv = darkCssList.length ? (compDark[n] ?? darkRaw[n]) : darkRaw[n];
    if (dv !== undefined && dv !== '' && !(lv !== undefined && (dv === lv || sameColor(dv, lv)))) prodDark[n] = dv;
  }
  const rolesLight = { ...lightTok.vars };
  // тёмные роли: снятые с тёмной темы → через переменные продукта (по совпадению светлого значения) → синтез
  const rolesDark = {}; const darkFrom = {};
  for (const r of COLOR_ROLES) {
    if (darkTok) { rolesDark[r] = darkTok.vars[r]; darkFrom[r] = 'audited'; continue; }
    const cands = Object.keys(prodLight).filter((n) => sameColor(prodLight[n], rolesLight[r]) && prodDark[n] && normColor(prodDark[n]));
    if (cands.length) {
      cands.sort((a, b) => (ROLE_HINT[r].test(b) - ROLE_HINT[r].test(a)) || a.length - b.length);
      rolesDark[r] = hexOf(prodDark[cands[0]]); darkFrom[r] = 'stylesheet:' + cands[0];
    }
  }
  for (const r of COLOR_ROLES) {
    if (rolesDark[r]) continue;
    if (r === '--c-accent') rolesDark[r] = toCss(lighten(rolesLight['--c-accent'], rolesDark['--c-surface'] || SYNTH_DARK['--c-surface']));
    else if (r === '--c-on-accent') rolesDark[r] = lum(rolesDark['--c-accent'] || rolesLight['--c-accent']) > 0.45 ? '#0b1020' : '#ffffff';
    else rolesDark[r] = SYNTH_DARK[r];
    darkFrom[r] = 'synthesized';
  }
  if (darkTok?.vars?.['--shadow']) rolesDark['--shadow'] = darkTok.vars['--shadow'];
  const kinds = new Set(Object.values(darkFrom).map((v) => v.split(':')[0]));
  const darkSource = kinds.size === 1 ? [...kinds][0] : 'mixed';
  return { rolesLight, rolesDark, prodLight, prodDark, darkFrom, darkSource, darkSel, blocked, sheets,
    source: names.length ? 'custom-properties' : 'computed', names };
}

function tokensCss(ts, src) {
  const safe = (v) => String(v).replace(/[;{}]/g, '').replace(/\s+/g, ' ').trim();
  const L = [`/* Токены интерфейса ${src}, снято audit_site.mjs ${DATE}.`,
    `   Источник: ${ts.source === 'custom-properties' ? `CSS custom properties продукта (${Object.keys(ts.prodLight).length} светлых, ${Object.keys(ts.prodDark).length} тёмных)` : 'частотный анализ computed CSS (своих переменных у продукта нет)'};`,
    `   роли --c-* — частотный анализ computed CSS; тёмная тема: ${ts.darkSource}. Проверьте глазами по mockups/current/.`,
    '   Тёмный блок идёт первым (специфичность выше, значения rgb()), чтобы простые парсеры брали светлую тему. */', '',
    ':root[data-theme="dark"], [data-theme="dark"]:not(:root) {'];
  for (const [k, v] of Object.entries(ts.rolesDark)) L.push(`  ${k}: ${safe(rgbStr(v))};`);
  const pd = Object.entries(ts.prodDark);
  if (pd.length) L.push('  /* переменные продукта */');
  for (const [k, v] of pd) L.push(`  ${k}: ${safe(normColor(v) ? rgbStr(v) : v)};`);
  L.push('}', '', ':root, [data-theme="light"] {');
  for (const [k, v] of Object.entries(ts.rolesLight)) L.push(`  ${k}: ${safe(v)};`);
  const pl = Object.entries(ts.prodLight);
  if (pl.length) L.push('  /* переменные продукта */');
  for (const [k, v] of pl) L.push(`  ${k}: ${safe(v)};`);
  L.push('}', '');
  return L.join('\n');
}

// ------------------------------------------------------------ основной сценарий
const pw = loadPlaywright(opt, OUT);
const browser = await launch(pw, OUT);
const blocked = [];

function riskyHref(u) {
  try { const x = new URL(u); return RISKY.test(x.pathname + x.search + x.hash); } catch { return true; }
}

async function newContext(kind, locale, theme) {
  const base = { acceptDownloads: false, serviceWorkers: 'block', locale: locale || undefined, timezoneId: 'UTC',
    colorScheme: theme === 'dark' ? 'dark' : 'light', extraHTTPHeaders: locale ? { 'Accept-Language': locale } : undefined };
  const ctx = await browser.newContext(kind === 'mobile'
    ? { ...base, viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2,
        userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1' }
    : { ...base, viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  ctx.psState = { clicking: false };
  ctx.on('page', (pg) => { if (ctx.psState.clicking) pg.close().catch(() => {}); });     // новые окна после клика закрываются
  await ctx.route('**/*', (route) => {
    const req = route.request(); const u = req.url();
    if (u.startsWith('file:')) {
      if (!FILE_ROOT || !insideRoot(u)) { blocked.push({ url: u.slice(0, 160), reason: 'file:// вне разрешённой папки' }); return route.abort('accessdenied'); }
      return route.continue();
    }
    if (req.isNavigationRequest() && !['GET', 'HEAD'].includes(req.method())) { blocked.push({ url: u.slice(0, 160), reason: 'навигация ' + req.method() + ' (форма) заблокирована' }); return route.abort('blockedbyclient'); }
    if (ctx.psState.clicking && req.isNavigationRequest()) {
      let ok = false; try { ok = sameSite(new URL(u)) && !riskyHref(u); } catch { ok = false; }
      if (!ok) { blocked.push({ url: u.slice(0, 160), reason: 'переход после клика заблокирован (внешний или запрещённый адрес)' }); return route.abort('blockedbyclient'); }
    }
    return route.continue();
  });
  return ctx;
}

const SCHEME = () => {
  const tr = (c) => !c || c === 'transparent' || /rgba\([^)]*,\s*0\)$/.test(c);
  const b = getComputedStyle(document.body); const h = getComputedStyle(document.documentElement);
  return { bg: !tr(b.backgroundColor) ? b.backgroundColor : !tr(h.backgroundColor) ? h.backgroundColor : 'rgb(255, 255, 255)', fg: b.color };
};
const isDarkNow = async (page) => { const c = await page.evaluate(SCHEME).catch(() => null); return !!c && lum(c.bg) < lum(c.fg) && lum(c.bg) < 0.4; };
const DARK_HINT = () => {
  const re = /\[(data-(?:theme|color-scheme|mode|bs-theme))\s*=\s*["']?dark["']?\]|(?:^|[\s>(])(?:html|:root|body)?\.(dark|theme-dark|dark-mode|dark-theme)\b/i;
  const walk = (rules, d) => {
    for (const r of rules || []) {
      try {
        if (r.cssRules && !r.selectorText && d < 6) { const x = walk(r.cssRules, d + 1); if (x) return x; }
        const m = r.selectorText && re.exec(r.selectorText);
        if (m) return m[1] ? { type: 'attr', name: m[1] } : { type: 'class', name: m[2] };
      } catch { /* */ }
    }
    return null;
  };
  for (const sh of document.styleSheets) { try { const x = walk(sh.cssRules, 0); if (x) return x; } catch { /* CORS */ } }
  return null;
};
async function ensureDark(page) {
  if (await isDarkNow(page)) return 'prefers-color-scheme';
  if (THEME_TOGGLE) {
    for (let i = 0; i < 2; i++) {
      const loc = page.locator(THEME_TOGGLE).first();
      if (!(await loc.count().catch(() => 0))) break;
      const bad = await loc.evaluate((el) => !!el.closest('form') || (el.closest('a[href]') && !/^#|^javascript:/i.test(el.getAttribute('href') || el.closest('a').getAttribute('href') || ''))).catch(() => true);
      if (bad) break;
      await loc.click({ timeout: 3000 }).catch(() => {});
      await page.waitForTimeout(400);
      if (await isDarkNow(page)) return 'toggle';
    }
  }
  const hint = await page.evaluate(DARK_HINT).catch(() => null);
  if (hint && hint.type !== 'media') {
    await page.evaluate((h) => { const el = document.documentElement; if (h.type === 'attr') el.setAttribute(h.name, 'dark'); else el.classList.add(h.name); }, hint).catch(() => {});
    await page.waitForTimeout(200);
    if (await isDarkNow(page)) return hint.type === 'attr' ? `attribute ${hint.name}="dark"` : `class .${hint.name}`;
  }
  return 'none';
}

const CANDIDATES = ([sels, riskySrc]) => {
  const RISKY_URL = new RegExp(riskySrc, 'i');
  const RISKY_TXT = /выйти|выход|log ?out|sign ?out|удал|delete|remove|оплат|купить|buy\b|pay\b|checkout|корзин|cart|подписаться|subscribe|admin|войти через|sign in with|oauth/i;
  document.querySelectorAll('[data-ps-click]').forEach((el) => el.removeAttribute('data-ps-click'));
  const seen = new Set(); const all = [];
  const add = (el) => { if (!seen.has(el)) { seen.add(el); all.push(el); } };
  document.querySelectorAll('[data-audit-safe]').forEach(add);
  for (const q of sels) { try { document.querySelectorAll(q).forEach(add); } catch { /* неверный селектор */ } }
  const ok = []; const skipped = [];
  for (const el of all) {
    const label = (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || el.tagName).trim().replace(/\s+/g, ' ').slice(0, 60);
    if (el.getAttribute('data-audit-safe') === 'false') { skipped.push([label, 'data-audit-safe=false']); continue; }
    const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    if (!r.width || !r.height || st.visibility === 'hidden' || st.display === 'none') continue;
    if (el.closest('form') || el.matches('input, textarea, select, [type=submit], [contenteditable=true]')) { skipped.push([label, 'форма или поле']); continue; }
    const a = el.closest('a[href]');
    if (a) {
      if (a.hasAttribute('download') || a.target === '_blank') { skipped.push([label, 'download/новое окно']); continue; }
      let u; try { u = new URL(a.getAttribute('href'), location.href); } catch { skipped.push([label, 'неверная ссылка']); continue; }
      if (u.protocol === 'javascript:' || (u.origin !== location.origin && u.protocol !== 'file:')) { skipped.push([label, 'внешняя ссылка']); continue; }
      if (RISKY_URL.test(u.pathname + u.search + u.hash)) { skipped.push([label, 'запрещённый адрес']); continue; }
    }
    if (RISKY_TXT.test(label)) { skipped.push([label, 'опасное действие по тексту']); continue; }
    el.setAttribute('data-ps-click', String(ok.length));
    ok.push(label);
  }
  return { ok, skipped };
};

async function settle(page) {
  await page.waitForLoadState('networkidle', { timeout: Math.min(10000, TIMEOUT) }).catch(() => {});
  await page.waitForTimeout(800);
}

async function auditPage(ctx, url, vp, o = {}) {
  const page = await ctx.newPage();
  page.on('dialog', (d) => d.dismiss().catch(() => {}));
  const hosts = {}; const failed = []; const consoleErrors = []; let reqCount = 0;
  page.on('request', (r) => { reqCount++; try { const h = new URL(r.url()).hostname; if (h) hosts[h] = (hosts[h] || 0) + 1; } catch { /* data: */ } });
  page.on('response', (r) => { if (r.status() >= 400) { try { const u = new URL(r.url()); failed.push({ status: r.status(), url: (u.origin + u.pathname).slice(0, 160) }); } catch { /* */ } } });
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });
  page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + String(e).slice(0, 200)));
  const u = new URL(url);
  const suffix = [o.localeSuffix, o.theme === 'dark' ? 'dark' : null].filter(Boolean).join('-');
  const slug = uniqueSlug(url) + (suffix ? '-' + suffix : '');
  let status = null; let error = null; const t0 = Date.now(); let themeMethod = null;
  try {
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: TIMEOUT });
    status = resp ? resp.status() : (u.protocol === 'file:' ? 200 : null);
    await settle(page);
    if (o.theme === 'dark') themeMethod = await ensureDark(page);
  } catch (e) { error = String(e.message || e).split('\n')[0].slice(0, 200); }
  const wall = Date.now() - t0;
  const info = await page.evaluate(PAGE_INFO).catch((e) => ({ eval_error: String(e).slice(0, 200) }));
  const shotRel = path.posix.join('mockups', 'current', `${slug}-${vp}.png`);
  let shot = null;
  const snap = async (rel) => {
    const so = { path: path.join(OUT, rel), timeout: 20000 };
    if (FULL && info.scroll) { so.fullPage = true; so.clip = { x: 0, y: 0, width: page.viewportSize().width, height: Math.min(info.scroll.h, 8000) }; }
    await page.screenshot(so);
    return rel;
  };
  try { shot = await snap(shotRel); }
  catch (e) { error = (error ? error + '; ' : '') + 'screenshot: ' + String(e.message || e).split('\n')[0].slice(0, 120); }
  // безопасные клики: раскрытые состояния
  const states = []; let clickSkipped = [];
  if (CLICK && !error && MAX_CLICKS) {
    let cand = await page.evaluate(CANDIDATES, [CLICK_SELS, RISKY.source]).catch(() => ({ ok: [], skipped: [] }));
    clickSkipped = cand.skipped;
    const total = Math.min(cand.ok.length, MAX_CLICKS);
    for (let n = 0; n < total; n++) {
      const label = cand.ok[n];
      if (n > 0) {
        try {
          await page.goto(url, { waitUntil: 'domcontentloaded', timeout: TIMEOUT });
          if (page.url() === url && u.hash) await page.reload({ waitUntil: 'domcontentloaded', timeout: TIMEOUT });
          await settle(page);
          if (o.theme === 'dark') await ensureDark(page);
          cand = await page.evaluate(CANDIDATES, [CLICK_SELS, RISKY.source]);
        } catch (e) { states.push({ n: n + 1, label, error: 'перезагрузка: ' + String(e.message || e).split('\n')[0].slice(0, 120) }); continue; }
        if (cand.ok[n] !== label) { states.push({ n: n + 1, label, error: 'после перезагрузки элемент не найден' }); continue; }
      }
      const before = page.url();
      ctx.psState.clicking = true;
      try {
        await page.locator(`[data-ps-click="${n}"]`).first().click({ timeout: 3000 });
        await page.waitForTimeout(700);
      } catch (e) { ctx.psState.clicking = false; states.push({ n: n + 1, label, error: 'клик: ' + String(e.message || e).split('\n')[0].slice(0, 120) }); continue; }
      ctx.psState.clicking = false;
      const rel = path.posix.join('mockups', 'current', `${slug}-${vp}--${n + 1}.png`);
      let st = null;
      try { st = await snap(rel); } catch { st = null; }
      states.push({ n: n + 1, label, screenshot: st, url_after: page.url(), navigated: page.url() !== before });
    }
  }
  const third = Object.keys(hosts).filter((h) => h && h.replace(/^www\./, '') !== HOST && !h.endsWith('.' + HOST));
  const tokens = info.tokens; delete info.tokens;
  const finalUrl = page.url();
  await page.close();
  const rec = { path: u.protocol === 'file:' ? '/' + path.relative(FILE_ROOT, fileURLToPath(u)).split(path.sep).join('/') + (u.hash || '') : u.pathname + u.search + u.hash,
    url, slug, final_url: finalUrl, viewport: vp, theme: o.theme || 'light', theme_method: themeMethod, locale: o.locale || null, status, error, wall_ms: wall,
    screenshot: shot, states, clicks_skipped: clickSkipped.slice(0, 20).map(([label, why]) => ({ label, why })),
    requests: reqCount, third_party: third.sort(), failed: failed.slice(0, 20), console_errors: consoleErrors.slice(0, 20), ...info };
  console.log(`${vp.padEnd(7)} ${(o.theme || 'light').padEnd(5)} ${rec.path} → ${status ?? error} | ${(info.title || '').slice(0, 40)} | ${wall} мс | 3p ${third.length}` +
    `${themeMethod ? ' | тема: ' + themeMethod : ''}${states.length ? ' | состояний ' + states.filter((x) => x.screenshot).length : ''}`);
  return { rec, tokens, hosts };
}

async function discover() {
  if (opt.pages) {
    const list = opt.pages.split(',').map((p) => p.trim()).filter(Boolean)
      .map((p) => new URL(p.startsWith('#') ? p : p.replace(/^\//, start.protocol === 'file:' ? '' : '/'), start).href);
    return [...new Set(list)].slice(0, MAX_PAGES);
  }
  const ctx = await newContext('desktop', LOCALES[0], THEMES[0]);
  const page = await ctx.newPage();
  page.on('dialog', (d) => d.dismiss().catch(() => {}));
  let links = [];
  try {
    await page.goto(start.href, { waitUntil: 'domcontentloaded', timeout: TIMEOUT });
    await settle(page);
    links = await page.evaluate((mode) => (mode === 'hash'
      ? [...document.querySelectorAll('a[href^="#/"], a[href^="#!/"]')].map((a) => a.getAttribute('href'))
      : [...document.querySelectorAll('a[href]')].map((a) => a.href)), ROUTES_FROM);
  } catch (e) { console.error('главная не открылась: ' + String(e.message || e).split('\n')[0]); }
  await ctx.close();
  const home = new URL(start.href);
  if (ROUTES_FROM === 'hash') {
    home.hash = '';
    const seen = new Set(); const out = [];
    for (const h of links) {
      if (!h || seen.has(h) || RISKY.test(h)) continue;
      seen.add(h);
      const x = new URL(home.href); x.hash = h; out.push(x.href);
    }
    const homeHref = home.href;
    return [homeHref, ...out.filter((x) => x !== homeHref && !/#!?\/?$/.test(x))].slice(0, MAX_PAGES);
  }
  const counts = new Map();
  for (const h of links) {
    let x; try { x = new URL(h); } catch { continue; }
    x.hash = ''; x.search = '';
    if (!sameSite(x) || NON_HTML.test(x.pathname) || RISKY.test(x.pathname)) continue;
    if (x.protocol === 'file:' && !/\.html?$/i.test(x.pathname)) continue;
    counts.set(x.href, (counts.get(x.href) || 0) + 1);
  }
  home.hash = '';
  const ordered = [...counts.entries()].filter(([h]) => h !== home.href).sort((a, b) => b[1] - a[1] || a[0].length - b[0].length).map(([h]) => h);
  return [home.href, ...ordered].slice(0, MAX_PAGES);
}

const urls = await discover();
for (const x of urls) uniqueSlug(x);                     // слаги — в порядке обхода, совпадения получают -2, -3
console.log(`страниц к обходу: ${urls.length}${ROUTES_FROM === 'hash' ? ' (хэш-маршруты)' : ''}; темы: ${THEMES.join(', ')}${CLICK ? `; клики: data-audit-safe${CLICK_SELS.length ? ' + ' + CLICK_SELS.join(', ') : ''}` : ''}`);
const pages = []; const tokLight = []; const tokDark = []; const allHosts = {}; const cookieMap = new Map();
const plan = [];
for (const theme of THEMES) {
  plan.push(['desktop', LOCALES[0], urls, null, theme]);
  if (opt.mobile) plan.push(['mobile', LOCALES[0], urls, null, theme]);
}
for (const loc of LOCALES.slice(1)) plan.push(['desktop', loc, urls.slice(0, 3), loc, THEMES[0]]);
for (const [vp, loc, list, locSuffix, theme] of plan) {
  const ctx = await newContext(vp, loc, theme);
  for (const x of list) {
    const { rec, tokens, hosts } = await auditPage(ctx, x, vp, { locale: loc, localeSuffix: locSuffix, theme });
    pages.push(rec);
    if (tokens && !rec.error) {
      if (theme === 'dark') { if (rec.theme_method && rec.theme_method !== 'none') tokDark.push(tokens); }
      else tokLight.push(tokens);
    }
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
const lightBase = tokLight.length ? tokLight : tokDark;
const tokens = lightBase.length ? deriveTokens(lightBase) : null;
let tokenSets = null;
if (tokens) {
  const darkDerived = tokDark.length && tokLight.length ? deriveTokens(tokDark) : null;
  tokenSets = buildTokenSets(tokens, darkDerived, lightBase.map((t) => t.cssVars || {}), tokDark.map((t) => t.cssVars || {}));
  tokens.source = tokenSets.source;
  tokens.custom_properties = { light: Object.keys(tokenSets.prodLight).length, dark: Object.keys(tokenSets.prodDark).length,
    names: tokenSets.names.slice(0, 200), dark_selector: tokenSets.darkSel, stylesheets_read: tokenSets.sheets, stylesheets_blocked: tokenSets.blocked };
  tokens.dark = { source: tokenSets.darkSource, vars: tokenSets.rolesDark, from: tokenSets.darkFrom };
}
const thirdAll = Object.fromEntries(Object.entries(allHosts).filter(([h]) => h && h.replace(/^www\./, '') !== HOST && !h.endsWith('.' + HOST)).sort((a, b) => b[1] - a[1]));
const result = {
  url: start.href, host: HOST, date: DATE, tool: 'audit_site.mjs',
  viewports: plan.map(([vp, loc, , , theme]) => ({ viewport: vp, locale: loc || null, theme, size: vp === 'mobile' ? '390x844' : '1440x900' })),
  routes_from: ROUTES_FROM, themes: THEMES, clicks: CLICK ? { selectors: CLICK_SELS, data_audit_safe: true, max_per_page: MAX_CLICKS } : null,
  pages, third_party_domains: thirdAll, services, cookies: [...cookieMap.values()],
  tokens, tokens_css: tokens ? 'mockups/tokens.css' : null, blocked: blocked.slice(0, 50),
  summary: {
    pages: pages.length, errors: pages.filter((p) => p.error || (p.status && p.status >= 400)).length,
    no_description: pages.filter((p) => !p.meta?.description).length, no_canonical: pages.filter((p) => !p.canonical).length,
    no_og: pages.filter((p) => !p.og || !Object.keys(p.og).length).length, no_h1: pages.filter((p) => !p.h1?.length).length,
    overflow_x: pages.filter((p) => p.overflow_x).length, console_errors: pages.reduce((s, p) => s + (p.console_errors?.length || 0), 0),
    states: pages.reduce((s, p) => s + (p.states || []).filter((x) => x.screenshot).length, 0),
    dark_not_applied: pages.filter((p) => p.theme === 'dark' && p.theme_method === 'none').length,
    jsonld_types: [...new Set(pages.flatMap((p) => p.jsonld_types || []))], hreflang: [...new Set(pages.flatMap((p) => (p.hreflang || []).map((h) => h.lang)))],
  },
  notes: [CLICK ? 'Клики только по data-audit-safe и --click-safe (без форм, выхода, оплаты, OAuth, admin, api, внешних ссылок); вход не выполнялся; значения cookie не сохранялись.'
    : 'Только чтение: формы не отправлялись, клики не выполнялись, вход не выполнялся; значения cookie не сохранялись.'],
};
if (THEMES.includes('dark') && result.summary.dark_not_applied) result.notes.push(`тёмная тема не включилась на ${result.summary.dark_not_applied} снимках: нет prefers-color-scheme, укажите --theme-toggle`);
fs.writeFileSync(path.join(OUT, 'data', 'site-audit.json'), JSON.stringify(result, null, 2));
if (tokenSets) fs.writeFileSync(path.join(OUT, 'mockups', 'tokens.css'), tokensCss(tokenSets, start.protocol === 'file:' ? 'локальных файлов' : start.origin));
console.log(`готово: ${pages.length} снимков${result.summary.states ? ` + ${result.summary.states} раскрытых состояний` : ''} → ${path.join(OUT, 'data', 'site-audit.json')}` +
  `${tokens ? `, mockups/tokens.css (${tokens.source}, переменных ${tokens.custom_properties.light}/${tokens.custom_properties.dark}, тёмная: ${tokens.dark.source})` : ''}`);
