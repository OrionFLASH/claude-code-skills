#!/usr/bin/env node
// Снимки макетов из <OUT>/data/mockups-index.json и их проверка (product-strategy).
//
//   node shoot_mockups.mjs <OUT> [--only M01-x,M02-y] [--no-index] [--full-page] [--contrast] [--no-fail] [--no-discover]
//                          [--kit] [--node-dir <dir>]
//
// Автообнаружение: каждый <OUT>/mockups/concepts/*.html (кроме имён с «_») без записи в индексе добавляется в
// data/mockups-index.json: key — имя файла без .html; метаданные — атрибуты <html>/<body> или <meta name="ps:…">:
//   viewport — data-viewport | ps:viewport (WxH; mobile → 390x844, иначе 1440x900), title — ps:title | <title>,
//   proposals — data-proposals | ps:proposals ("P001,P002"), kind — data-kind | ps:kind (concept | component; по
//   умолчанию concept; kit — копия демо набора — считается component; component снимается всей страницей),
//   links — data-links | ps:links ("false" — не связывать с реестром, см. link_mockups.py).
// Записи с "discovered": true (их добавил скрипт) обновляются из HTML при каждом запуске: viewport, title, proposals,
// kind, links. Ручные записи (без discovered) не меняются. Индекс сливается по ключу (дубли ключей — первая запись).
// Для каждой записи: открывает <OUT>/<html> (только file:// внутри <OUT>), viewport из поля "viewport" (мобильные
// <600px — с deviceScaleFactor 2), снимает PNG в <OUT>/<png> и проверяет: ошибки консоли, внешние запросы
// (блокируются и перечисляются), горизонтальное переполнение, бейдж «Концепт» (для kind=concept), запасные цвета
// набора (см. ниже), высоту (раскадровка .pm-board выше viewport — замечание, прочие страницы — предупреждение).
// Запасные цвета: если страница подключает _kit.css, вычисленные --c-bg/surface/text/muted/border/accent сравниваются
// с запасными --k-def-* набора в каждой теме страницы. Совпадение — «использован запасной цвет»: FAIL, если в
// mockups/tokens.css есть свои переменные (значит, токены не дошли до набора: нет --c-* и имён моста), иначе
// предупреждение. Необязательные роли (--c-on-accent, success, warning, danger) и --font-mono без Menlo/SF Mono/
// Consolas — предупреждения. Значение роли, которое не является цветом, — FAIL.
// Общие файлы: без --only/--no-index пишутся data/mockups-index.json (автообнаружение) и агрегат
// data/mockups-check.json (слияние по ключу из всех файлов по ключам индекса; атомарно, под файлом-замком).
// С --only или --no-index общие файлы НЕ пишутся — только data/mockups-check.<ключ>.json (агенты снимают свои
// ключи параллельно; новые HTML находятся в памяти, индекс собирает оркестратор запуском без --only).
// --contrast — проверка контраста текста на любой странице (как в kit-demo; нарушения — замечания).
// --kit: снять служебные _*.html (набор компонентов, kit-demo, мобильный слой) полностраничными PNG; в индекс не
//   добавляются, результаты — data/mockups-check.<_key>.json; data-viewports="1440x900,390x844" — снимок на каждой ширине.
// Код выхода: 0 — всё чисто (или --no-fail), 1 — есть замечания, 2 — ошибка аргументов/индекса, 3 — нет playwright/Chromium.
// Модули: --node-dir | $PS_NODE_DIR | <OUT>/build/node | ~/.cache/product-strategy/node | папка скрипта.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(HERE, '..', '..');
const USAGE = 'node shoot_mockups.mjs <OUT> [--only key1,key2] [--no-index] [--full-page] [--contrast] [--no-fail] [--no-discover] [--kit] [--node-dir <dir>]';

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
const { pos, opt } = parseArgs(process.argv.slice(2), new Set(['full-page', 'no-fail', 'no-discover', 'kit', 'no-index', 'contrast']));
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
// общие файлы (индекс и агрегат) пишет только полный запуск оркестратора
const WRITE_SHARED = !opt.kit && !only.size && !opt['no-index'];

function htmlMeta(file) {
  let src = '';
  try { src = fs.readFileSync(file, 'utf8').slice(0, 200000); } catch { return {}; }
  const tag = (name) => (new RegExp(`<${name}\\b[^>]*>`, 'i').exec(src) || [''])[0];
  const attr = (t, a) => { const m = new RegExp(`\\b${a}\\s*=\\s*(["'])(.*?)\\1`, 'i').exec(t); return m ? m[2].trim() : null; };
  const meta = {};
  for (const m of src.matchAll(/<meta\b[^>]*>/gi)) {
    const name = attr(m[0], 'name'); const content = attr(m[0], 'content');
    if (name && /^ps:/i.test(name) && content !== null) meta[name.slice(3).toLowerCase()] = content;
  }
  const h = tag('html'); const b = tag('body');
  const get = (a, k) => attr(h, a) || attr(b, a) || meta[k] || null;
  const vpRaw = get('data-viewport', 'viewport');
  let viewport = '1440x900';
  if (vpRaw && /^\d{2,5}x\d{2,5}$/.test(vpRaw)) viewport = vpRaw; else if (vpRaw && /mobile|phone|390/i.test(vpRaw)) viewport = '390x844';
  const vps = (get('data-viewports', 'viewports') || '').split(',').map((s) => s.trim()).filter((s) => /^\d{2,5}x\d{2,5}$/.test(s));
  const title = (meta.title || (/<title[^>]*>([^<]*)<\/title>/i.exec(src) || [])[1] || '').replace(/\s+/g, ' ').trim();
  const props = (get('data-proposals', 'proposals') || '').split(/[,\s]+/).map((s) => s.trim()).filter((s) => /^P\d{3,}$/.test(s));
  const kindRaw = (get('data-kind', 'kind') || '').toLowerCase();
  // kit — копия демо набора (M00-design-language из _kit-demo): в индексе это служебный component
  const kind = kindRaw === 'kit' ? 'component' : ['concept', 'component', 'current'].includes(kindRaw) ? kindRaw : 'concept';
  const linksRaw = (get('data-links', 'links') || '').toLowerCase();
  const res = { viewport, viewports: vps, title, proposals: props, kind };
  if (/^(false|no|0|нет)$/.test(linksRaw)) res.links = false;
  return res;
}

// ------------------------------------------------------------ автообнаружение
// Возвращает список записей (индекс + найденные HTML). write=true — под замком, с записью индекса при изменениях.
function mergeDiscovered(items) {
  if (!Array.isArray(items)) throw new Error('mockups-index.json должен быть списком');
  const seen = new Set(); const out = []; const dups = [];
  for (const it of items) {                                     // слияние по ключу: дубли ключей отбрасываются
    if (!it || typeof it !== 'object' || !it.key) { out.push(it); continue; }
    if (seen.has(it.key)) { dups.push(it.key); continue; }
    seen.add(it.key); out.push(it);
  }
  const added = []; const updated = [];
  const files = fs.existsSync(CONCEPTS) ? fs.readdirSync(CONCEPTS).filter((f) => /\.html?$/i.test(f) && !f.startsWith('_')).sort() : [];
  const htmls = new Map(out.filter((i) => i && i.html).map((i) => [i.html, i]));
  for (const f of files) {
    const key = f.replace(/\.html?$/i, ''); const rel = `mockups/concepts/${f}`;
    const m = htmlMeta(path.join(CONCEPTS, f));
    const cur = out.find((i) => i && i.key === key) || htmls.get(rel);
    if (cur) {
      if (cur.discovered !== true) continue;                     // ручная запись — не трогаем
      const want = { viewport: m.viewport || '1440x900', title: m.title || key, proposals: m.proposals || [], kind: m.kind || 'concept' };
      const diff = Object.keys(want).filter((k) => JSON.stringify(cur[k]) !== JSON.stringify(want[k]));
      if ('links' in m ? cur.links !== false : 'links' in cur) diff.push('links');
      if (diff.length) {
        Object.assign(cur, want);
        if (m.links === false) cur.links = false; else delete cur.links;
        updated.push(`${key} (${diff.join(', ')})`);
      }
      continue;
    }
    const rec = { key, html: rel, png: rel.replace(/\.html?$/i, '.png'), title: m.title || key, proposals: m.proposals || [],
      viewport: m.viewport || '1440x900', kind: m.kind || 'concept', discovered: true };
    if (m.links === false) rec.links = false;
    out.push(rec); added.push(key);
  }
  return { items: out, added, updated, dups };
}

async function discover(write) {
  const load = () => (fs.existsSync(indexPath) ? readJson(indexPath, null) : []);
  if (!write) return mergeDiscovered(load());
  return withLock(LOCK, () => {
    const r = mergeDiscovered(load());
    if (r.added.length || r.updated.length || r.dups.length) writeAtomic(indexPath, JSON.stringify(r.items, null, 2) + '\n');
    return r;
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
} else if (opt['no-discover']) {
  if (!fs.existsSync(indexPath)) { console.error('ошибка: нет ' + indexPath + ' (--no-discover: только записи индекса)'); process.exit(2); }
  items = readJson(indexPath, null);
  if (!Array.isArray(items)) { console.error('ошибка: mockups-index.json не разобран или не список'); process.exit(2); }
} else {
  let r;
  try { r = await discover(WRITE_SHARED); } catch (e) { console.error('ошибка: ' + e.message); process.exit(2); }
  const where = WRITE_SHARED ? 'в mockups-index.json' : 'в памяти (индекс не пишется: --only/--no-index)';
  if (r.added.length) console.log(`автообнаружение: добавлено ${where} — ${r.added.join(', ')}`);
  if (r.updated.length) console.log(`автообнаружение: обновлено из HTML ${where} — ${r.updated.join('; ')}`);
  if (r.dups.length) console.log(`предупреждение: дубли ключей в mockups-index.json (оставлена первая запись) — ${[...new Set(r.dups)].join(', ')}`);
  items = r.items;
  if (!items.length) { console.error('ошибка: нет ' + indexPath + ' и нет mockups/concepts/*.html для автообнаружения'); process.exit(2); }
  const missing = [...only].filter((k) => !items.some((i) => i && i.key === k));
  if (missing.length) { console.error('ошибка: --only: нет таких ключей ни в индексе, ни среди mockups/concepts/*.html — ' + missing.join(', ')); process.exit(2); }
}

// токены продукта: сколько своих custom properties в mockups/tokens.css (0 — набор рисует запасной палитрой осознанно)
const TOKENS_VARS = (() => { try { return (fs.readFileSync(path.join(OUT, 'mockups', 'tokens.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').match(/--[\w-]+\s*:/g) || []).length; } catch { return 0; } })();
const CORE_ROLES = ['bg', 'surface', 'text', 'muted', 'border', 'accent'];
const OPT_ROLES = ['on-accent', 'success', 'warning', 'danger'];
// имена моста — как в _kit.css (слой ps-defaults)
const BRIDGE = { bg: ['--bg', '--background', '--color-bg'], surface: ['--surface', '--card', '--color-surface'],
  text: ['--text', '--foreground', '--color-text'], muted: ['--text-muted', '--muted-foreground', '--muted', '--color-muted'],
  border: ['--border', '--line', '--color-border'], accent: ['--primary', '--brand', '--color-primary'],
  'on-accent': ['--on-primary', '--primary-foreground'], success: ['--success', '--color-success'], warning: ['--warning', '--color-warning'],
  danger: ['--danger', '--error', '--color-danger'] };
const KIT_FILES = new Set(['_kit.css', '_icons.css', '_mobile.css']);

// Какие custom properties страница объявляет сама (tokens.css, свои слои, <style>): {light:Set, dark:Set}
const cssCache = new Map();
function cssDecls(text) {
  const res = { light: new Set(), dark: new Set() };
  let s = text.replace(/\/\*[\s\S]*?\*\//g, '');
  const add = (body, dark) => { for (const m of body.matchAll(/(--[\w-]+)\s*:/g)) res[dark ? 'dark' : 'light'].add(m[1]); };
  s = s.replace(/@media[^{]*prefers-color-scheme\s*:\s*dark[^{]*\{((?:[^{}]*\{[^{}]*\})*)[^{}]*\}/gi, (_, inner) => {
    for (const r of inner.matchAll(/([^{}]*)\{([^{}]*)\}/g)) add(r[2], true);
    return '';
  });
  for (const r of s.matchAll(/([^{}]*)\{([^{}]*)\}/g)) add(r[2], /dark/i.test(r[1]));
  return res;
}
function pageDecls(htmlAbs) {
  const all = { light: new Set(), dark: new Set() };
  let src = ''; try { src = fs.readFileSync(htmlAbs, 'utf8'); } catch { return all; }
  const merge = (d) => { d.light.forEach((x) => all.light.add(x)); d.dark.forEach((x) => all.dark.add(x)); };
  for (const m of src.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/gi)) merge(cssDecls(m[1]));
  for (const m of src.matchAll(/<link\b[^>]*>/gi)) {
    if (!/rel\s*=\s*["']?stylesheet/i.test(m[0])) continue;
    const href = (/href\s*=\s*["']([^"']+)["']/i.exec(m[0]) || [])[1];
    if (!href || /^[a-z]+:/i.test(href)) continue;
    const f = path.resolve(path.dirname(htmlAbs), href.split(/[?#]/)[0]);
    if (KIT_FILES.has(path.basename(f)) || !inside(f)) continue;
    if (!cssCache.has(f)) { let t = ''; try { t = fs.readFileSync(f, 'utf8'); } catch { /* нет файла — консоль покажет */ } cssCache.set(f, cssDecls(t)); }
    merge(cssCache.get(f));
  }
  return all;
}
const declared = (decl, theme, role) => {
  const names = ['--c-' + role, ...(BRIDGE[role] || [])];
  const set = theme === 'dark' ? decl.dark : decl.light;
  return names.some((n) => set.has(n));
};

// Проверка контраста для --contrast (та же логика, что в kit-demo: градиенты — худший цвет, картинки пропускаются)
const CONTRAST_JS = `(() => {
  const cv = document.createElement('canvas'); cv.width = cv.height = 1;
  const cx = cv.getContext('2d', { willReadFrequently: true });
  const COLOR_RE = /(?:rgba?|hsla?|color|oklab|oklch|lab|lch)\\((?:[^()]|\\([^()]*\\))*\\)|#[0-9a-fA-F]{3,8}\\b/g;
  const rgba = (c) => { if (!c || c === 'transparent') return [0, 0, 0, 0]; cx.clearRect(0, 0, 1, 1); cx.fillStyle = '#000'; cx.fillStyle = c; cx.fillRect(0, 0, 1, 1);
    const d = cx.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255]; };
  const over = (t, u) => { const a = t[3]; return [t[0] * a + u[0] * (1 - a), t[1] * a + u[1] * (1 - a), t[2] * a + u[2] * (1 - a), 1]; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const backgrounds = (el) => {
    const layers = [];
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const s = getComputedStyle(e), img = s.backgroundImage; let done = false;
      if (img && img !== 'none') { if (!/gradient/.test(img) || /url\\(/.test(img)) return null;
        const g = (img.match(COLOR_RE) || []).map(rgba); if (!g.length) return null; layers.push(g); done = g.every((x) => x[3] >= 0.999); }
      if (!done) { const c = rgba(s.backgroundColor); if (c[3] > 0) { layers.push([c]); done = c[3] >= 0.999; } }
      if (done) break;
    }
    let bases = [[255, 255, 255, 1]];
    for (let i = layers.length - 1; i >= 0; i--) { const n = []; bases.forEach((b) => layers[i].forEach((l) => n.push(over(l, b)))); bases = n.slice(0, 32); }
    return bases;
  };
  const fails = []; let checked = 0;
  document.querySelectorAll('body *').forEach((el) => {
    if (el.closest('[aria-hidden="true"], script, style, template, .ps-lock-body')) return;
    let own = false; for (let n = el.firstChild; n; n = n.nextSibling) if (n.nodeType === 3 && n.textContent.trim()) { own = true; break; }
    if (!own) return;
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) return;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || +s.opacity === 0 || el.matches(':disabled, .is-disabled')) return;
    const bgs = backgrounds(el); if (!bgs) return;
    const col = rgba(s.color); let k = Infinity; bgs.forEach((bg) => { k = Math.min(k, ratio(over(col, bg), bg)); });
    const size = parseFloat(s.fontSize), bold = parseInt(s.fontWeight, 10) >= 700;
    const need = (size >= 24 || (bold && size >= 18.66)) ? 3 : 4.5; checked++;
    if (k + 1e-6 < need) {
      const theme = (el.closest('[data-theme]') || document.documentElement).getAttribute('data-theme') || 'light';
      const cls = (el.className && typeof el.className === 'string') ? '.' + el.className.trim().split(/\\s+/).join('.') : el.tagName.toLowerCase();
      const rec = { theme, el: cls, text: el.textContent.trim().slice(0, 40), ratio: Math.round(k * 100) / 100, need };
      fails.push(rec); console.error('контраст ' + rec.ratio + ':1 < ' + need + ' — ' + rec.el + ' «' + rec.text + '» (' + theme + ')');
    }
  });
  window.psContrast = { checked, fails };
})()`;

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
    fallback_colors: [], warnings: [], error: null, ok: false, date: DATE };
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
    if (opt.contrast) await page.evaluate(`window.psContrast ? 0 : ${CONTRAST_JS}`).catch((e) => rec.console_errors.push('проверка контраста: ' + String(e).slice(0, 120)));
    const info = await page.evaluate(([src, vw, core, optional]) => {
      const re = new RegExp(src, 'i');
      const de = document.documentElement;
      const cand = [...document.querySelectorAll('[class*=concept i], [data-badge], [class*=badge i], [id*=concept i]')];
      const badgeEl = cand.find((e) => re.test(e.textContent || '')) || null;
      const text = document.body ? document.body.innerText : '';
      // запасные цвета набора: по одной точке на каждую тему страницы
      const roots = []; const themes = new Set();
      for (const el of [de, ...document.querySelectorAll('[data-theme]')]) {
        const t = el.getAttribute('data-theme') || 'light';
        if (!themes.has(t)) { themes.add(t); roots.push([t, el]); }
      }
      const colors = []; let kit = false; let mono = null;
      for (const [t, el] of roots) {
        const cs = getComputedStyle(el);
        if (!cs.getPropertyValue('--k-def-accent').trim()) continue;
        kit = true;
        if (mono === null) mono = cs.getPropertyValue('--font-mono').trim();
        for (const role of [...core, ...optional]) {
          const v = cs.getPropertyValue('--c-' + role).trim(); const d = cs.getPropertyValue('--k-def-' + role).trim();
          const isColor = !!v && CSS.supports('color', v);
          colors.push({ theme: t, role, value: v, fallback: !!v && v.toLowerCase() === d.toLowerCase(), bad: !isColor, core: core.includes(role) });
        }
      }
      return { badge: !!badgeEl || re.test(text), overflow: de.scrollWidth > Math.min(de.clientWidth, vw) + 1, w: de.scrollWidth, h: de.scrollHeight,
        viewportMeta: !!document.querySelector('meta[name=viewport]'), contrast: window.psContrast || null,
        board: !!document.querySelector('.pm-board, .pm-frame'), kit, colors, mono };
    }, [BADGE_RE.source, width, CORE_ROLES, OPT_ROLES]);
    rec.viewport_meta = info.viewportMeta;
    rec.badge = info.badge; rec.overflow_x = info.overflow; rec.scroll_width = info.w; rec.scroll_height = info.h;
    if (info.contrast) rec.contrast = { checked: info.contrast.checked, fails: (info.contrast.fails || []).length };
    if (info.kit) {
      // запасной = значение совпало с --k-def-* И роль не объявлена страницей (ни --c-*, ни имя моста) для этой темы
      const decl = pageDecls(htmlAbs);
      rec.page_vars = decl.light.size + decl.dark.size;
      rec.fallback_colors = info.colors.filter((c) => c.fallback && !declared(decl, c.theme === 'dark' ? 'dark' : 'light', c.role)).map((c) => ({ theme: c.theme, var: '--c-' + c.role, value: c.value, core: c.core }));
      const bad = info.colors.filter((c) => c.bad);
      if (bad.length) rec.bad_colors = bad.map((c) => ({ theme: c.theme, var: '--c-' + c.role, value: c.value }));
      if (info.mono && !/Menlo|SF Mono|Consolas/i.test(info.mono)) rec.warnings.push(`--font-mono «${info.mono.slice(0, 60)}» без Menlo/"SF Mono"/Consolas перед monospace — кириллица на macOS выйдет шрифтом с засечками`);
    }
    fs.mkdirSync(path.dirname(pngAbs), { recursive: true });
    const so = { path: pngAbs, timeout: 20000 };
    if (opt['full-page'] || rec.kind === 'kit' || rec.kind === 'component') so.fullPage = true;   // демо набора — длинные страницы
    rec.full_page = !!so.fullPage;
    if (!so.fullPage && info.h > height + 2) {
      const msg = `страница выше viewport: ${info.h}px > ${height}px — низ не попадёт в PNG`;
      if (info.board) rec.tall = msg + ' (раскадровка: поднимите высоту data-viewport до ≥ ' + Math.ceil((info.h + 8) / 10) * 10 + ' или --full-page)';
      else rec.warnings.push(msg + ' (если прокрутка по замыслу — снимайте с --full-page)');
    }
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
  if (rec.tall) problems.push(rec.tall);
  if (rec.bad_colors) problems.push('значение роли — не цвет: ' + rec.bad_colors.map((c) => `${c.var} (${c.theme}) = «${c.value.slice(0, 40)}»`).join(', ') +
    ' — в tokens.css задайте цвет целиком (#hex, rgb(), hsl()), «голые» тройки HSL набор не понимает');
  const fbCore = rec.fallback_colors.filter((c) => c.core); const fbOpt = rec.fallback_colors.filter((c) => !c.core);
  const fbText = (list) => [...new Set(list.map((c) => c.theme))].map((t) => `${t}: ` + list.filter((c) => c.theme === t)
    .map((c) => (list.length <= 3 ? `${c.var} = ${c.value}` : c.var.slice(4))).join(', ')).join('; ');
  if (fbCore.length) {
    if (TOKENS_VARS > 0 || rec.page_vars > 0) {
      problems.push(`использован запасной цвет набора (${fbText(fbCore)}) — токены продукта не дошли до набора: в mockups/tokens.css нет --c-* ` +
        'и имён моста (--primary, --bg, --surface/--card, --text, --muted, --border)' +
        (fbCore.some((c) => c.theme === 'dark') ? '; для тёмной темы нужен блок [data-theme="dark"]' : ''));
    } else rec.warnings.push(`tokens.css пуст — макет нарисован запасной палитрой набора (${fbText(fbCore)})`);
  }
  if (fbOpt.length && (TOKENS_VARS > 0 || rec.page_vars > 0)) rec.warnings.push(`запасные значения необязательных ролей (${fbText(fbOpt)})`);
  rec.problems = problems; rec.ok = problems.length === 0;
  finish();
  console.log(`${rec.ok ? 'OK  ' : 'FAIL'} ${it.key} ${width}x${height} → ${rec.png}${problems.length ? ' | ' + problems.join('; ') : ''}`);
  for (const w of rec.warnings) console.log(`     предупреждение ${it.key}: ${w}`);
}
await browser.close();

const runSummary = { total: results.length, ok: results.filter((r) => r.ok).length, failed: results.filter((r) => !r.ok).length };
if (!opt.kit && !WRITE_SHARED) {
  console.log(`итого: ${runSummary.ok}/${runSummary.total} без замечаний → data/mockups-check.<ключ>.json ` +
    `(mockups-index.json и mockups-check.json не изменены: ${only.size ? '--only' : '--no-index'}; агрегат соберёт запуск без --only)`);
} else if (!opt.kit) {
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
