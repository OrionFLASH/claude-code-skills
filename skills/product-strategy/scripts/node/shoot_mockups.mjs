#!/usr/bin/env node
// Снимки макетов из <OUT>/data/mockups-index.json и их проверка (product-strategy).
//
//   node shoot_mockups.mjs <OUT> [--only M01-x,M02-y] [--full-page] [--no-fail] [--no-discover] [--kit] [--node-dir <dir>]
//
// Автообнаружение: каждый <OUT>/mockups/concepts/*.html (кроме имён с «_») без записи в индексе добавляется в
// data/mockups-index.json: key — имя файла без .html, viewport — data-viewport в <html>/<body> (WxH; mobile → 390x844,
// иначе 1440x900), title — <title>, proposals — data-proposals="P001,P002". Существующие записи не меняются.
// Для каждой записи: открывает <OUT>/<html> (только file:// внутри <OUT>), viewport из поля "viewport" (мобильные
// <600px — с deviceScaleFactor 2), снимает PNG в <OUT>/<png> и проверяет: ошибки консоли, внешние запросы
// (блокируются и перечисляются), горизонтальное переполнение, бейдж «Концепт» (для kind=concept).
// Итог: data/mockups-check.<key>.json по каждому снятому ключу + агрегат data/mockups-check.json (слияние по ключу
// из всех файлов по ключам индекса; запись атомарная — временный файл + rename, под файлом-замком), поэтому
// параллельные запуски с --only не затирают чужие результаты.
// --kit: снять служебные _*.html (набор компонентов, kit-demo) полностраничными PNG; в индекс не добавляются,
//   результаты — data/mockups-check.<_key>.json; data-viewports="1440x900,390x844" — снимок на каждой ширине.
// Код выхода: 0 — всё чисто (или --no-fail), 1 — есть замечания, 2 — ошибка аргументов/индекса, 3 — нет playwright/Chromium.
// Модули: --node-dir | $PS_NODE_DIR | <OUT>/build/node | ~/.cache/product-strategy/node | папка скрипта.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(HERE, '..', '..');
const USAGE = 'node shoot_mockups.mjs <OUT> [--only key1,key2] [--full-page] [--no-fail] [--no-discover] [--kit] [--node-dir <dir>]';

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

// ------------------------------------------------------------ атомарная запись и замок
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function writeAtomic(file, data) {
  const tmp = `${file}.${process.pid}.${Date.now()}.tmp`;
  fs.writeFileSync(tmp, data);
  fs.renameSync(tmp, file);
}
async function withLock(lockFile, fn, timeoutMs = 60000) {
  const t0 = Date.now();
  for (;;) {
    try { const fd = fs.openSync(lockFile, 'wx'); fs.writeSync(fd, String(process.pid)); fs.closeSync(fd); break; }
    catch (e) {
      if (e.code !== 'EEXIST') throw e;
      try { if (Date.now() - fs.statSync(lockFile).mtimeMs > 30000) { fs.unlinkSync(lockFile); continue; } } catch { /* замок уже снят */ }
      if (Date.now() - t0 > timeoutMs) throw new Error('не дождались замка ' + lockFile);
      await sleep(25 + Math.random() * 50);
    }
  }
  try { return await fn(); } finally { try { fs.unlinkSync(lockFile); } catch { /* */ } }
}
const readJson = (p, dflt) => { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return dflt; } };
const safeKey = (k) => String(k).replace(/[^\w.-]+/g, '_');

// ------------------------------------------------------------ аргументы
const { pos, opt } = parseArgs(process.argv.slice(2), new Set(['full-page', 'no-fail', 'no-discover', 'kit']));
if (opt.help || pos.length < 1) { console.log(USAGE); process.exit(opt.help ? 0 : 2); }
const OUT = path.resolve(pos[0]);
if (!fs.existsSync(OUT)) { console.error('ошибка: нет папки ' + OUT); process.exit(2); }
const DATA = path.join(OUT, 'data');
fs.mkdirSync(DATA, { recursive: true });
const indexPath = path.join(DATA, 'mockups-index.json');
const LOCK = path.join(DATA, '.mockups.lock');
const CONCEPTS = path.join(OUT, 'mockups', 'concepts');
const OUT_REAL = fs.realpathSync(OUT);
const only = new Set((opt.only || '').split(',').map((s) => s.trim()).filter(Boolean));

function htmlMeta(file) {
  let src = '';
  try { src = fs.readFileSync(file, 'utf8').slice(0, 200000); } catch { return {}; }
  const tag = (name) => (new RegExp(`<${name}\\b[^>]*>`, 'i').exec(src) || [''])[0];
  const attr = (t, a) => { const m = new RegExp(`\\b${a}\\s*=\\s*(["'])(.*?)\\1`, 'i').exec(t); return m ? m[2].trim() : null; };
  const h = tag('html'); const b = tag('body');
  const vpRaw = attr(h, 'data-viewport') || attr(b, 'data-viewport');
  let viewport = '1440x900';
  if (vpRaw && /^\d{2,5}x\d{2,5}$/.test(vpRaw)) viewport = vpRaw; else if (vpRaw && /mobile|phone|390/i.test(vpRaw)) viewport = '390x844';
  const vps = (attr(h, 'data-viewports') || attr(b, 'data-viewports') || '').split(',').map((s) => s.trim()).filter((s) => /^\d{2,5}x\d{2,5}$/.test(s));
  const title = ((/<title[^>]*>([^<]*)<\/title>/i.exec(src) || [])[1] || '').replace(/\s+/g, ' ').trim();
  const props = (attr(h, 'data-proposals') || attr(b, 'data-proposals') || '').split(/[,\s]+/).map((s) => s.trim()).filter((s) => /^P\d{3,}$/.test(s));
  return { viewport, viewports: vps, title, proposals: props };
}

// ------------------------------------------------------------ автообнаружение
async function discover() {
  if (!fs.existsSync(CONCEPTS)) return { added: [] };
  const files = fs.readdirSync(CONCEPTS).filter((f) => /\.html?$/i.test(f) && !f.startsWith('_')).sort();
  if (!files.length) return { added: [] };
  return withLock(LOCK, () => {
    let items = fs.existsSync(indexPath) ? readJson(indexPath, null) : [];
    if (!Array.isArray(items)) throw new Error('mockups-index.json должен быть списком');
    const keys = new Set(items.map((i) => i && i.key)); const htmls = new Set(items.map((i) => i && i.html));
    const added = [];
    for (const f of files) {
      const key = f.replace(/\.html?$/i, ''); const rel = `mockups/concepts/${f}`;
      if (keys.has(key) || htmls.has(rel)) continue;
      const m = htmlMeta(path.join(CONCEPTS, f));
      const rec = { key, html: rel, png: rel.replace(/\.html?$/i, '.png'), title: m.title || key, proposals: m.proposals || [],
        viewport: m.viewport || '1440x900', kind: 'concept', discovered: true };
      items.push(rec); added.push(key);
    }
    if (added.length) writeAtomic(indexPath, JSON.stringify(items, null, 2) + '\n');
    return { added };
  });
}

let items = [];
if (opt.kit) {
  if (!fs.existsSync(CONCEPTS)) { console.error('ошибка: нет ' + CONCEPTS); process.exit(2); }
  for (const f of fs.readdirSync(CONCEPTS).filter((x) => /^_.*\.html?$/i.test(x)).sort()) {
    const key = f.replace(/\.html?$/i, ''); const m = htmlMeta(path.join(CONCEPTS, f));
    const vps = m.viewports.length ? m.viewports : [m.viewport];
    vps.forEach((vp, i) => items.push({ key: i ? `${key}-${vp}` : key, html: `mockups/concepts/${f}`,
      png: `mockups/concepts/${key}${i ? '-' + vp : ''}.png`, viewport: vp, kind: 'kit', title: m.title }));
  }
  if (!items.length) { console.error('ошибка: в mockups/concepts нет файлов _*.html (набор компонентов)'); process.exit(2); }
} else {
  if (!opt['no-discover']) {
    try { const { added } = await discover(); if (added.length) console.log(`автообнаружение: добавлено в mockups-index.json — ${added.join(', ')}`); }
    catch (e) { console.error('ошибка: ' + e.message); process.exit(2); }
  }
  if (!fs.existsSync(indexPath)) { console.error('ошибка: нет ' + indexPath + ' (и нет mockups/concepts/*.html для автообнаружения)'); process.exit(2); }
  items = readJson(indexPath, null);
  if (!Array.isArray(items)) { console.error('ошибка: mockups-index.json не разобран или не список'); process.exit(2); }
}

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

const DATE = new Date().toISOString().slice(0, 10);
const results = [];
for (const it of items) {
  if (!it || typeof it !== 'object') continue;
  if (only.size && !only.has(it.key)) continue;
  const rec = { key: it.key, html: it.html, png: it.png || (it.html || '').replace(/\.html?$/i, '.png'), viewport: it.viewport || '1440x900',
    kind: it.kind || 'concept', badge: null, external_requests: [], console_errors: [], overflow_x: false, scroll_width: null, scroll_height: null,
    error: null, ok: false, date: DATE };
  const htmlAbs = path.resolve(OUT, it.html || '');
  const pngAbs = path.resolve(OUT, rec.png);
  const finish = () => {
    results.push(rec);
    writeAtomic(path.join(DATA, `mockups-check.${safeKey(rec.key)}.json`), JSON.stringify(rec, null, 2) + '\n');
  };
  if (!it.html || !fs.existsSync(htmlAbs)) { rec.error = 'нет HTML-файла'; rec.problems = [rec.error]; finish(); console.log(`FAIL ${it.key}: нет ${it.html}`); continue; }
  if (!inside(htmlAbs) || !pngAbs.startsWith(OUT_REAL + path.sep) && !pngAbs.startsWith(OUT + path.sep)) {
    rec.error = 'путь вне <OUT>'; rec.problems = [rec.error]; finish(); console.log(`FAIL ${it.key}: путь вне <OUT>`); continue;
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
    await page.goto(pathToFileURL(htmlAbs).href, { waitUntil: 'load', timeout: 30000 });
    await page.evaluate(() => document.fonts && document.fonts.ready).catch(() => {});
    await page.waitForTimeout(300);
    const info = await page.evaluate(([src, vw]) => {
      const re = new RegExp(src, 'i');
      const de = document.documentElement;
      const cand = [...document.querySelectorAll('[class*=concept i], [data-badge], [class*=badge i], [id*=concept i]')];
      const badgeEl = cand.find((e) => re.test(e.textContent || '')) || null;
      const text = document.body ? document.body.innerText : '';
      return { badge: !!badgeEl || re.test(text), overflow: de.scrollWidth > Math.min(de.clientWidth, vw) + 1, w: de.scrollWidth, h: de.scrollHeight,
        viewportMeta: !!document.querySelector('meta[name=viewport]'), contrast: window.psContrast || null };
    }, [BADGE_RE.source, width]);
    rec.viewport_meta = info.viewportMeta;
    rec.badge = info.badge; rec.overflow_x = info.overflow; rec.scroll_width = info.w; rec.scroll_height = info.h;
    if (info.contrast) rec.contrast = { checked: info.contrast.checked, fails: (info.contrast.fails || []).length };
    fs.mkdirSync(path.dirname(pngAbs), { recursive: true });
    const so = { path: pngAbs, timeout: 20000 };
    if (opt['full-page'] || rec.kind === 'kit') so.fullPage = true;
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
  if (rec.contrast && rec.contrast.fails) problems.push(`нарушений контраста ${rec.contrast.fails}`);
  rec.problems = problems; rec.ok = problems.length === 0;
  finish();
  console.log(`${rec.ok ? 'OK  ' : 'FAIL'} ${it.key} ${width}x${height} → ${rec.png}${problems.length ? ' | ' + problems.join('; ') : ''}`);
}
await browser.close();

const runSummary = { total: results.length, ok: results.filter((r) => r.ok).length, failed: results.filter((r) => !r.ok).length };
if (!opt.kit) {
  // агрегат из всех файлов по ключам индекса (чужие результаты сохраняются; старый агрегат — запасной источник)
  await withLock(LOCK, () => {
    const index = readJson(indexPath, []);
    const keys = (Array.isArray(index) ? index : []).filter((i) => i && i.key).map((i) => i.key);
    const prev = readJson(path.join(DATA, 'mockups-check.json'), {});
    const prevBy = new Map((prev.items || []).filter((i) => i && i.key).map((i) => [i.key, i]));
    const merged = [];
    for (const k of keys) {
      const rec = readJson(path.join(DATA, `mockups-check.${safeKey(k)}.json`), null) || prevBy.get(k);
      if (rec) merged.push(rec);
    }
    const summary = { total: merged.length, ok: merged.filter((r) => r.ok).length, failed: merged.filter((r) => !r.ok).length,
      no_badge: merged.filter((r) => r.kind === 'concept' && r.badge === false).length,
      external: merged.filter((r) => (r.external_requests || []).length).length, overflow: merged.filter((r) => r.overflow_x).length,
      console: merged.filter((r) => (r.console_errors || []).length).length, not_shot: keys.length - merged.length };
    writeAtomic(path.join(DATA, 'mockups-check.json'), JSON.stringify({ date: DATE, tool: 'shoot_mockups.mjs', summary, items: merged }, null, 2) + '\n');
    console.log(`итого в этом запуске: ${runSummary.ok}/${runSummary.total} без замечаний; в агрегате ${summary.ok}/${summary.total}` +
      `${summary.not_shot ? ` (не снято ${summary.not_shot})` : ''} → data/mockups-check.json`);
  });
} else {
  console.log(`набор компонентов: ${runSummary.ok}/${runSummary.total} без замечаний → data/mockups-check._*.json`);
}
process.exit(runSummary.failed && !opt['no-fail'] ? 1 : 0);
