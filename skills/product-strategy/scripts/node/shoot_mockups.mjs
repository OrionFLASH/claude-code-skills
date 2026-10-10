#!/usr/bin/env node
// Снимки макетов из <OUT>/data/mockups-index.json и их проверка (product-strategy).
//
//   node shoot_mockups.mjs <OUT> [--only M01-x,M02-y] [--full-page] [--no-fail] [--node-dir <dir>]
//
// Для каждой записи: открывает <OUT>/<html> (только file:// внутри <OUT>), viewport из поля "viewport" (WxH,
// мобильные <600px — с deviceScaleFactor 2), снимает PNG в <OUT>/<png> и проверяет: ошибки консоли, внешние
// запросы (блокируются и перечисляются), горизонтальное переполнение, наличие бейджа «Концепт» (для kind=concept).
// Итог: <OUT>/data/mockups-check.json. Код выхода: 0 — всё чисто (или --no-fail), 1 — есть замечания,
// 2 — ошибка аргументов/индекса, 3 — нет playwright/Chromium.
// Модули: --node-dir | $PS_NODE_DIR | <OUT>/build/node | папка скрипта.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(HERE, '..', '..');
const USAGE = 'node shoot_mockups.mjs <OUT> [--only key1,key2] [--full-page] [--no-fail] [--node-dir <dir>]';

function parseArgs(argv, flags) {
  const pos = []; const opt = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') { opt.help = true; continue; }
    if (a.startsWith('--')) {
      const eq = a.indexOf('=');
      const k = eq > 0 ? a.slice(2, eq) : a.slice(2);
      if (eq > 0) opt[k] = a.slice(eq + 1); else if (flags.has(k)) opt[k] = true; else opt[k] = argv[++i];
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

const { pos, opt } = parseArgs(process.argv.slice(2), new Set(['full-page', 'no-fail']));
if (opt.help || pos.length < 1) { console.log(USAGE); process.exit(opt.help ? 0 : 2); }
const OUT = path.resolve(pos[0]);
const indexPath = path.join(OUT, 'data', 'mockups-index.json');
if (!fs.existsSync(indexPath)) { console.error('ошибка: нет ' + indexPath); process.exit(2); }
let items;
try { items = JSON.parse(fs.readFileSync(indexPath, 'utf8')); } catch (e) { console.error('ошибка: не разобран mockups-index.json: ' + e.message); process.exit(2); }
if (!Array.isArray(items)) { console.error('ошибка: mockups-index.json должен быть списком'); process.exit(2); }
const only = new Set((opt.only || '').split(',').map((s) => s.trim()).filter(Boolean));
const OUT_REAL = fs.realpathSync(OUT);

function inside(p) {
  let real; try { real = fs.realpathSync(p); } catch { real = path.resolve(p); }
  return real === OUT_REAL || real.startsWith(OUT_REAL + path.sep);
}

const BADGE_RE = /Концепт|Concept/i;
const pw = loadPlaywright(opt, OUT);
let browser;
try { browser = await pw.chromium.launch({ headless: true }); }
catch (e) {
  console.error('не запустился Chromium: ' + String(e.message || e).split('\n')[0]);
  console.error(`поставьте браузер: python3 ${path.join(SKILL_DIR, 'scripts', 'check_env.py')} --install-node ${OUT}`);
  process.exit(3);
}

const results = [];
for (const it of items) {
  if (!it || typeof it !== 'object') continue;
  if (only.size && !only.has(it.key)) continue;
  const rec = { key: it.key, html: it.html, png: it.png || (it.html || '').replace(/\.html?$/i, '.png'), viewport: it.viewport || '1440x900',
    kind: it.kind || 'concept', badge: null, external_requests: [], console_errors: [], overflow_x: false, scroll_width: null, scroll_height: null,
    error: null, ok: false };
  const htmlAbs = path.resolve(OUT, it.html || '');
  const pngAbs = path.resolve(OUT, rec.png);
  if (!it.html || !fs.existsSync(htmlAbs)) { rec.error = 'нет HTML-файла'; results.push(rec); console.log(`FAIL ${it.key}: нет ${it.html}`); continue; }
  if (!inside(htmlAbs) || !pngAbs.startsWith(OUT_REAL + path.sep) && !pngAbs.startsWith(OUT + path.sep)) {
    rec.error = 'путь вне <OUT>'; results.push(rec); console.log(`FAIL ${it.key}: путь вне <OUT>`); continue;
  }
  const m = /^(\d{2,5})x(\d{2,5})$/.exec(String(rec.viewport));
  const width = m ? +m[1] : 1440; const height = m ? +m[2] : 900;
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: width < 600 ? 2 : 1, isMobile: width < 600,
    hasTouch: width < 600, acceptDownloads: false, serviceWorkers: 'block' });
  await ctx.route('**/*', (route) => {
    const u = route.request().url();
    if (u.startsWith('data:') || u.startsWith('blob:') || u === 'about:blank') return route.continue();
    if (u.startsWith('file:')) {
      let p; try { p = fileURLToPath(u); } catch { return route.abort(); }
      if (inside(p)) return route.continue();
      rec.external_requests.push('file вне <OUT>: ' + u.slice(0, 140));
      return route.abort('accessdenied');
    }
    rec.external_requests.push(u.slice(0, 160));
    return route.abort('blockedbyclient');
  });
  const page = await ctx.newPage();
  page.on('dialog', (d) => d.dismiss().catch(() => {}));
  page.on('console', (msg) => { if (msg.type() === 'error' && !/net::ERR_BLOCKED_BY_CLIENT|ERR_ACCESS_DENIED/.test(msg.text())) rec.console_errors.push(msg.text().slice(0, 200)); });
  page.on('pageerror', (e) => rec.console_errors.push('pageerror: ' + String(e).slice(0, 200)));
  try {
    await page.goto('file://' + htmlAbs, { waitUntil: 'load', timeout: 30000 });
    await page.evaluate(() => document.fonts && document.fonts.ready).catch(() => {});
    await page.waitForTimeout(300);
    const info = await page.evaluate(([src, vw]) => {
      const re = new RegExp(src, 'i');
      const de = document.documentElement;
      const cand = [...document.querySelectorAll('[class*=concept i], [data-badge], [class*=badge i], [id*=concept i]')];
      const badgeEl = cand.find((e) => re.test(e.textContent || '')) || null;
      const text = document.body ? document.body.innerText : '';
      return { badge: !!badgeEl || re.test(text), overflow: de.scrollWidth > Math.min(de.clientWidth, vw) + 1, w: de.scrollWidth, h: de.scrollHeight,
        viewportMeta: !!document.querySelector('meta[name=viewport]') };
    }, [BADGE_RE.source, width]);
    rec.viewport_meta = info.viewportMeta;
    rec.badge = info.badge; rec.overflow_x = info.overflow; rec.scroll_width = info.w; rec.scroll_height = info.h;
    fs.mkdirSync(path.dirname(pngAbs), { recursive: true });
    const so = { path: pngAbs, timeout: 20000 };
    if (opt['full-page']) so.fullPage = true;
    await page.screenshot(so);
  } catch (e) { rec.error = String(e.message || e).split('\n')[0].slice(0, 200); }
  await ctx.close();
  const problems = [];
  if (rec.error) problems.push(rec.error);
  if (rec.console_errors.length) problems.push(`ошибок консоли ${rec.console_errors.length}`);
  if (rec.external_requests.length) problems.push(`внешних запросов ${rec.external_requests.length}`);
  if (rec.overflow_x) problems.push(`горизонтальное переполнение ${rec.scroll_width}px > ${width}px`);
  if (rec.kind === 'concept' && rec.badge === false) problems.push('нет бейджа «Концепт»');
  if (width < 600 && rec.viewport_meta === false) problems.push('мобильный макет без <meta name=viewport>');
  rec.problems = problems; rec.ok = problems.length === 0;
  results.push(rec);
  console.log(`${rec.ok ? 'OK  ' : 'FAIL'} ${it.key} ${width}x${height} → ${rec.png}${problems.length ? ' | ' + problems.join('; ') : ''}`);
}
await browser.close();
const summary = { total: results.length, ok: results.filter((r) => r.ok).length, failed: results.filter((r) => !r.ok).length,
  no_badge: results.filter((r) => r.kind === 'concept' && r.badge === false).length,
  external: results.filter((r) => r.external_requests.length).length, overflow: results.filter((r) => r.overflow_x).length,
  console: results.filter((r) => r.console_errors.length).length };
fs.writeFileSync(path.join(OUT, 'data', 'mockups-check.json'), JSON.stringify({ date: new Date().toISOString().slice(0, 10), tool: 'shoot_mockups.mjs', summary, items: results }, null, 2));
console.log(`итого: ${summary.ok}/${summary.total} без замечаний → data/mockups-check.json`);
process.exit(summary.failed && !opt['no-fail'] ? 1 : 0);
