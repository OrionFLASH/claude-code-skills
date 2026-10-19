#!/usr/bin/env node
// Снимки макетов из <OUT>/data/mockups-index.json и их проверка (product-strategy).
//
//   node shoot_mockups.mjs <OUT> [--only M01-x,M02-y] [--no-index] [--full-page] [--contrast] [--no-fail] [--no-discover]
//                          [--kit] [--targets[=auto|pointer|touch]] [--no-targets] [--layout] [--other-theme] [--hotspots N]
//                          [--node-dir <dir>]
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
// 1.5 (дизайн-этап, WP-F):
// Бейдж концепта ищется по классу .ps-concept-badge (текст бейджа не важен); старые макеты без класса — по тексту
//   «Концепт|Concept» с предупреждением. Обрезанный текст бейджа (scrollWidth > clientWidth) — замечание.
// --targets — цели нажатия: pointer — ≥ 32 px, touch — ≥ 44 px (auto: touch при ширине < 600, иначе pointer);
//   ссылки внутри строки текста не считаются (WCAG 2.5.8); [draggable=true]/[data-drag] без data-drag-alt="<селектор
//   кнопок>" — замечание «перетаскивание без дублирования кнопками». Включается само при run-config design.pointer_first
//   (--no-targets — выключить) и в --kit.
// --layout — дочерние элементы, вылезающие из однострочных flex-рядов, и скрытая горизонтальная прокрутка (кроме
//   .is-scroll, [data-scroll], .ps-table-wrap): «обрезанные кнопки». Само включается в --kit.
// --other-theme — после основного снимка переключить <html data-theme> на противоположную тему и снять
//   <ключ>.theme-<тема>.png: переполнение, запасные цвета и (с --contrast) контраст второй темы — тоже замечания.
// --contrast учитывает текст в SVG (цвет — fill) и заливку SVG-фигур под текстом (elementsFromPoint).
// Подсветка элементов (data-hs, data-hs-title/-what/-why/-p/-sec, шаблон _hotspots.js): запуск без --only пишет ещё
//   mockups/hotspots.json {version, mockups: {<ключ>: {items: [{n, id, title, what, why, p, sec, r: [x, y, w, h] — доли PNG]}}}}
//   (для просмотра макетов на странице); в mockups-check.<ключ>.json —
//   hotspots {count, untitled, duplicates, zones[{id,n,title,what,why,p,sec,x,y,w,h}]} (CSS px от угла страницы, scale =
//   deviceScaleFactor); --hotspots N — замечание, если у концепта размечено меньше N элементов.
// data-proposals/ps:proposals принимают P-id и id черновиков (G8-01): --only их больше не отбрасывает.
// Поле date — локальная дата (не UTC).
// Код выхода: 0 — всё чисто (или --no-fail), 1 — есть замечания, 2 — ошибка аргументов/индекса, 3 — нет playwright/Chromium.
// Модули: --node-dir | $PS_NODE_DIR | <OUT>/build/node | ~/.cache/product-strategy/node | папка скрипта.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(HERE, '..', '..');
function pngSize(file) {   // ширина и высота PNG из заголовка IHDR (без зависимостей)
  try {
    const fd = fs.openSync(file, 'r'); const buf = Buffer.alloc(24); fs.readSync(fd, buf, 0, 24, 0); fs.closeSync(fd);
    if (buf.readUInt32BE(0) !== 0x89504e47) return null;
    return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) };
  } catch (e) { return null; }
}
const USAGE = 'node shoot_mockups.mjs <OUT> [--only key1,key2] [--no-index] [--full-page] [--contrast] [--no-fail] [--no-discover] [--kit] [--targets[=auto|pointer|touch]] [--no-targets] [--layout] [--other-theme] [--hotspots N] [--node-dir <dir>]';

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
const { pos, opt } = parseArgs(process.argv.slice(2), new Set(['full-page', 'no-fail', 'no-discover', 'kit', 'no-index', 'contrast', 'targets', 'no-targets', 'layout', 'other-theme']));
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
// run-config: design.pointer_first → проверка целей нажатия по умолчанию
const RUN_CFG = readJson(path.join(OUT, 'build', 'run-config.json'), {}) || {};
const POINTER_FIRST = !!(RUN_CFG.design && RUN_CFG.design.pointer_first);
const TARGETS = opt['no-targets'] ? null : (typeof opt.targets === 'string' ? opt.targets : (opt.targets || opt.kit || POINTER_FIRST) ? 'auto' : null);
if (TARGETS && !['auto', 'pointer', 'touch'].includes(TARGETS)) { console.error('ошибка: --targets=auto|pointer|touch'); process.exit(2); }
const LAYOUT = !!(opt.layout || opt.kit);
const HS_MIN = opt.hotspots ? parseInt(opt.hotspots, 10) : 0;
if (opt.hotspots && !(HS_MIN >= 0)) { console.error('ошибка: --hotspots N — число'); process.exit(2); }

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
  const props = (get('data-proposals', 'proposals') || '').split(/[,\s]+/).map((s) => s.trim()).filter((s) => /^(P\d{3,}|G\d+-\d{2,})$/.test(s));
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

// Проверка контраста для --contrast (та же логика, что в kit-demo: градиенты — худший цвет, картинки пропускаются).
// 1.5: текст в SVG — цвет из fill; фон — заливка SVG-фигуры под центром текста (elementsFromPoint), если она ближе
// предка с непрозрачным фоном; HTML-подпись поверх SVG-графика — так же.
const CONTRAST_JS = `(() => {
  const cv = document.createElement('canvas'); cv.width = cv.height = 1;
  const cx = cv.getContext('2d', { willReadFrequently: true });
  const COLOR_RE = /(?:rgba?|hsla?|color|oklab|oklch|lab|lch)\\((?:[^()]|\\([^()]*\\))*\\)|#[0-9a-fA-F]{3,8}\\b/g;
  const rgba = (c) => { if (!c || c === 'transparent' || c === 'none') return [0, 0, 0, 0]; cx.clearRect(0, 0, 1, 1); cx.fillStyle = '#000'; cx.fillStyle = c; cx.fillRect(0, 0, 1, 1);
    const d = cx.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255]; };
  const over = (t, u) => { const a = t[3]; return [t[0] * a + u[0] * (1 - a), t[1] * a + u[1] * (1 - a), t[2] * a + u[2] * (1 - a), 1]; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const SHAPES = new Set(['rect', 'circle', 'ellipse', 'path', 'polygon', 'polyline']);
  const backgrounds = (el) => {
    const layers = [];
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      if (e instanceof SVGElement && !(e instanceof SVGSVGElement)) continue;          // внутри SVG фон HTML не задаётся
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
  // заливка SVG-фигуры под текстом: первая фигура в стопке под точкой, которая не является предком el и лежит выше
  // ближайшего предка el с фоном; null — фигуры нет (обычный путь по предкам)
  const svgUnder = (el, r) => {
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return null;
    const stack = document.elementsFromPoint(x, y); const i = stack.indexOf(el);
    const from = i >= 0 ? i + 1 : 0;
    for (let k = from; k < stack.length; k++) {
      const e = stack[k];
      if (e === el || e.contains(el)) { if (!(e instanceof SVGElement) || e instanceof SVGSVGElement) return null; continue; }
      if (!SHAPES.has(e.tagName.toLowerCase()) || !(e instanceof SVGElement)) { if (i < 0) continue; return null; }
      const cs = getComputedStyle(e); const f = rgba(cs.fill);
      const a = f[3] * (parseFloat(cs.fillOpacity) || (cs.fillOpacity === '0' ? 0 : 1)) * (parseFloat(cs.opacity) || (cs.opacity === '0' ? 0 : 1));
      if (a <= 0.02) continue;
      const svg = e.ownerSVGElement; const base = backgrounds(svg ? svg.parentElement : document.body) || [[255, 255, 255, 1]];
      return base.map((b) => over([f[0], f[1], f[2], a], b));
    }
    return null;
  };
  const fails = []; let checked = 0, svg = 0;
  document.querySelectorAll('body *').forEach((el) => {
    if (el.closest('[aria-hidden="true"], script, style, template, .ps-lock-body, #hs-ui')) return;
    let own = false; for (let n = el.firstChild; n; n = n.nextSibling) if (n.nodeType === 3 && n.textContent.trim()) { own = true; break; }
    if (!own) return;
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) return;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none' || +s.opacity === 0 || el.matches(':disabled, .is-disabled')) return;
    const inSvg = el instanceof SVGElement;
    if (inSvg && !/^(text|tspan|textPath)$/i.test(el.tagName)) return;
    let col = inSvg ? rgba(s.fill) : rgba(s.color);
    if (inSvg) { if (/url\\(/.test(s.fill) || col[3] === 0) return; col = [col[0], col[1], col[2], col[3] * (parseFloat(s.fillOpacity) || 1)]; svg++; }
    const bgs = svgUnder(el, r) || backgrounds(el); if (!bgs) return;
    let k = Infinity; bgs.forEach((bg) => { k = Math.min(k, ratio(over(col, bg), bg)); });
    const size = parseFloat(s.fontSize), bold = parseInt(s.fontWeight, 10) >= 700;
    const need = (size >= 24 || (bold && size >= 18.66)) ? 3 : 4.5; checked++;
    if (k + 1e-6 < need) {
      const theme = (el.closest('[data-theme]') || document.documentElement).getAttribute('data-theme') || 'light';
      const cn = typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal) || '';
      const cls = cn.trim() ? '.' + cn.trim().split(/\\s+/).join('.') : el.tagName.toLowerCase();
      const rec = { theme, el: cls, text: el.textContent.trim().slice(0, 40), ratio: Math.round(k * 100) / 100, need, svg: inSvg };
      fails.push(rec); console.error('контраст ' + rec.ratio + ':1 < ' + need + ' — ' + rec.el + ' «' + rec.text + '» (' + theme + ')');
    }
  });
  window.psContrast = { checked, fails, svg };
})()`;

// Описание элемента для замечаний: tag.class1.class2 «текст»
const DESC_JS = `const desc = (el) => { const cn = typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal) || '';
  return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (cn.trim() ? '.' + cn.trim().split(/\\s+/).slice(0, 3).join('.') : ''); };`;

// Цели нажатия: интерактивные элементы меньше min × min CSS px; ссылки в строке текста — исключение (WCAG 2.5.8)
const TARGETS_JS = `(min) => { ${DESC_JS}
  const SEL = 'button, a[href], input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab], [role=switch], [role=checkbox], [role=radio], [role=slider], [role=menuitem], [role=option], [tabindex]:not([tabindex="-1"])';
  const inText = (el) => { let e = el; while (e.parentElement && getComputedStyle(e.parentElement).display === 'inline') e = e.parentElement;
    const d = getComputedStyle(el).display; if (d !== 'inline' && d !== 'inline-block' && e === el) return false;
    const p = e.parentElement; if (!p) return false;
    for (const n of p.childNodes) if (n !== e && n.nodeType === 3 && n.textContent.trim()) return true; return false; };
  const seen = new Set(); const small = []; let checked = 0;
  for (const el0 of document.querySelectorAll(SEL)) {
    let el = el0;
    if (el0.matches('input, select, textarea')) { const lab = el0.closest('label'); if (lab) el = lab; }
    if (seen.has(el)) continue; seen.add(el);
    if (el.closest('[aria-hidden="true"], [data-hs-ui], #hs-ui, .ps-concept-badge, template, [inert]')) continue;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none' || +s.opacity === 0 || s.pointerEvents === 'none' || el0.disabled) continue;
    const r = el.getBoundingClientRect(); if (r.width < 2 || r.height < 2) continue;
    if (el.tagName === 'A' && inText(el)) continue;
    checked++;
    if (r.width + 0.5 < min || r.height + 0.5 < min) small.push({ el: desc(el), text: (el.innerText || el.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ').slice(0, 30), w: Math.round(r.width), h: Math.round(r.height) });
  }
  const drag = [];
  for (const el of document.querySelectorAll('[draggable="true"], [data-drag]')) {
    const alt = el.getAttribute('data-drag-alt'); let ok = false;
    if (alt) { try { ok = !!document.querySelector(alt); } catch (e) { ok = false; } }
    if (!ok) drag.push(desc(el));
  }
  return { checked, small, drag };
}`;

// Раскладка: дети, вылезающие из однострочного flex-ряда, и скрытая горизонтальная прокрутка
const LAYOUT_JS = `() => { ${DESC_JS}
  const scrollOk = (el) => el.matches('.is-scroll, [data-scroll], .ps-table-wrap, pre, .ps-code, textarea, html, body');
  const issues = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('[aria-hidden="true"], template, #hs-ui, svg')) continue;
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue;
    if (/(auto|scroll)/.test(s.overflowX) && el.scrollWidth > el.clientWidth + 1 && !scrollOk(el)) {
      issues.push({ type: 'hidden_scroll', el: desc(el), over: el.scrollWidth - el.clientWidth }); continue; }
    if (!/flex/.test(s.display) || !/^row/.test(s.flexDirection) || s.flexWrap !== 'nowrap' || scrollOk(el)) continue;
    const right = r.right - parseFloat(s.paddingRight) - parseFloat(s.borderRightWidth);
    const left = r.left + parseFloat(s.paddingLeft) + parseFloat(s.borderLeftWidth);
    for (const c of el.children) {
      const cs = getComputedStyle(c); if (cs.position === 'absolute' || cs.position === 'fixed' || cs.display === 'none') continue;
      const cr = c.getBoundingClientRect(); if (!cr.width) continue;
      if (cr.right > right + 1.5 || cr.left < left - 1.5) {
        issues.push({ type: 'flex_overflow', el: desc(el), child: desc(c), text: (c.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 30), over: Math.round(Math.max(cr.right - right, left - cr.left)) });
        break;
      }
    }
  }
  return issues.slice(0, 50);
}`;

// Подсветка элементов макета (data-hs-*): число, зоны в координатах страницы
const HS_JS = `() => {
  const by = new Map(); const untitled = []; const dup = [];
  for (const el of document.querySelectorAll('[data-hs]')) {
    if (el.closest('template')) continue;
    const id = el.getAttribute('data-hs'); if (!id) continue;
    let it = by.get(id); if (!it) { it = { id, el: null, parts: [] }; by.set(id, it); }
    if (el.hasAttribute('data-hs-title')) { if (it.el) dup.push(id); else it.el = el; } else it.parts.push(el);
  }
  const zones = []; let n = 0;
  for (const it of by.values()) {
    if (!it.el) { untitled.push(it.id); continue; }
    let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
    for (const e of [it.el, ...it.parts]) { const r = e.getBoundingClientRect(); if (!r.width && !r.height) continue;
      x1 = Math.min(x1, r.left); y1 = Math.min(y1, r.top); x2 = Math.max(x2, r.right); y2 = Math.max(y2, r.bottom); }
    const g = (a) => (it.el.getAttribute(a) || '').trim();
    const z = { id: it.id, n: ++n, title: g('data-hs-title'), what: g('data-hs-what'), why: g('data-hs-why'),
      p: g('data-hs-p').split(/[\\s,]+/).filter(Boolean), sec: g('data-hs-sec').split(/[\\s,]+/).filter(Boolean) };
    if (x1 !== Infinity) Object.assign(z, { x: Math.round(x1 + scrollX), y: Math.round(y1 + scrollY), w: Math.round(x2 - x1), h: Math.round(y2 - y1) });
    zones.push(z);
  }
  return { count: zones.length, untitled, duplicates: [...new Set(dup)], incomplete: zones.filter((z) => !z.what || !z.why).map((z) => z.id), zones };
}`;

// Сводка страницы: бейдж концепта (по классу; старые макеты — по тексту), переполнение, запасные цвета по темам и режимам
const INFO_FN = ([src, vw, core, optional]) => {
  const re = new RegExp(src, 'i');
  const de = document.documentElement;
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const byClass = [...document.querySelectorAll('.ps-concept-badge')].filter(vis);
  let badgeEl = byClass[0] || null; let by = badgeEl ? 'class' : null;
  if (!badgeEl) {
    const cand = [...document.querySelectorAll('[class*=concept i], [data-badge], [class*=badge i], [id*=concept i]')];
    badgeEl = cand.find((e) => re.test(e.textContent || '')) || null;
    if (badgeEl) by = 'text';
  }
  const text = document.body ? document.body.innerText : '';
  if (!badgeEl && re.test(text)) by = 'text';
  const truncated = byClass.filter((e) => e.scrollWidth > e.clientWidth + 1).map((e) => ({ text: (e.textContent || '').trim().slice(0, 80), need: e.scrollWidth, have: e.clientWidth }));
  const roots = []; const themes = new Set();
  for (const el of [de, ...document.querySelectorAll('[data-theme], [data-mode]')]) {
    const t = (el.getAttribute('data-theme') || (el.closest('[data-theme]') || de).getAttribute('data-theme') || 'light') + (el.closest('[data-mode]') ? ':' + el.closest('[data-mode]').getAttribute('data-mode') : '');
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
  return { badge: !!by, badge_by: by, badge_truncated: truncated, overflow: de.scrollWidth > Math.min(de.clientWidth, vw) + 1, w: de.scrollWidth, h: de.scrollHeight,
    viewportMeta: !!document.querySelector('meta[name=viewport]'), contrast: window.psContrast || null,
    board: !!document.querySelector('.pm-board, .pm-frame'), kit, colors, mono, theme: de.getAttribute('data-theme') || 'light' };
};

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

const _d = new Date();
const DATE = `${_d.getFullYear()}-${String(_d.getMonth() + 1).padStart(2, '0')}-${String(_d.getDate()).padStart(2, '0')}`;   // локальная дата, не UTC
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
  let sink = rec.console_errors;                                   // ошибки консоли второй темы — отдельно
  page.on('dialog', (d) => d.dismiss().catch(() => {}));
  page.on('console', (msg) => { if (msg.type() === 'error' && !/net::ERR_BLOCKED_BY_CLIENT|ERR_ACCESS_DENIED/.test(msg.text())) sink.push(msg.text().slice(0, 200)); });
  page.on('pageerror', (e) => sink.push('pageerror: ' + String(e).slice(0, 200)));
  const targetMin = TARGETS === 'touch' ? 44 : TARGETS === 'pointer' ? 32 : width < 600 ? 44 : 32;
  const fallbackOf = (info, decl) => info.colors.filter((c) => c.fallback && !declared(decl, c.theme.startsWith('dark') ? 'dark' : 'light', c.role))
    .map((c) => ({ theme: c.theme, var: '--c-' + c.role, value: c.value, core: c.core }));
  let decl = null;
  try {
    await page.goto(pathToFileURL(htmlAbs).href, { waitUntil: 'load', timeout: 30000 });
    await page.evaluate(() => document.fonts && document.fonts.ready).catch(() => {});
    await page.waitForTimeout(300);
    if (opt.contrast) await page.evaluate(`window.psContrast ? 0 : ${CONTRAST_JS}`).catch((e) => rec.console_errors.push('проверка контраста: ' + String(e).slice(0, 120)));
    const info = await page.evaluate(INFO_FN, [BADGE_RE.source, width, CORE_ROLES, OPT_ROLES]);
    rec.viewport_meta = info.viewportMeta;
    rec.badge = info.badge; rec.badge_by = info.badge_by; rec.overflow_x = info.overflow; rec.scroll_width = info.w; rec.scroll_height = info.h;
    if (info.badge_truncated.length) rec.badge_truncated = info.badge_truncated;
    if (info.badge_by === 'text' && rec.kind === 'concept') rec.warnings.push('бейдж найден по тексту, без класса .ps-concept-badge — разметьте бейдж классом набора');
    if (info.contrast) rec.contrast = { checked: info.contrast.checked, fails: (info.contrast.fails || []).length, svg: info.contrast.svg || 0 };
    if (info.kit) {
      // запасной = значение совпало с --k-def-* И роль не объявлена страницей (ни --c-*, ни имя моста) для этой темы
      decl = pageDecls(htmlAbs);
      rec.page_vars = decl.light.size + decl.dark.size;
      rec.fallback_colors = fallbackOf(info, decl);
      const bad = info.colors.filter((c) => c.bad);
      if (bad.length) rec.bad_colors = bad.map((c) => ({ theme: c.theme, var: '--c-' + c.role, value: c.value }));
      if (info.mono && !/Menlo|SF Mono|Consolas/i.test(info.mono)) rec.warnings.push(`--font-mono «${info.mono.slice(0, 60)}» без Menlo/"SF Mono"/Consolas перед monospace — кириллица на macOS выйдет шрифтом с засечками`);
    }
    if (TARGETS) {
      const t = await page.evaluate(`(${TARGETS_JS})(${targetMin})`);
      rec.targets = { mode: TARGETS === 'auto' ? (targetMin === 44 ? 'touch' : 'pointer') : TARGETS, min: targetMin, checked: t.checked, small: t.small.slice(0, 20), small_total: t.small.length, drag_without_buttons: t.drag };
    }
    if (LAYOUT) rec.layout = await page.evaluate(`(${LAYOUT_JS})()`);
    const hs = await page.evaluate(`(${HS_JS})()`);
    if (hs.count || hs.untitled.length) {
      rec.hotspots = Object.assign(hs, { scale: width < 600 ? 2 : 1 });
      if (hs.duplicates.length) rec.warnings.push('data-hs: повторяется data-hs-title у id ' + hs.duplicates.slice(0, 5).join(', '));
      if (hs.untitled.length) rec.warnings.push('data-hs без data-hs-title ни у одного элемента: ' + hs.untitled.slice(0, 5).join(', '));
      if (hs.incomplete.length) rec.warnings.push(`подсказки без «что это»/«для чего» (data-hs-what/-why): ${hs.incomplete.length}`);
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
    // вторая тема: тот же макет с противоположным data-theme на <html>
    if (opt['other-theme'] && rec.kind !== 'kit') {
      const theme = info.theme === 'dark' ? 'light' : 'dark';
      const rootColors = () => page.evaluate(() => { const cs = getComputedStyle(document.documentElement);
        return ['--c-bg', '--c-surface', '--c-text'].map((v) => cs.getPropertyValue(v).trim()).join('|') + '|' + getComputedStyle(document.body).backgroundColor; });
      const before = await rootColors();
      const o = { theme, png: rec.png.replace(/\.png$/i, '') + `.theme-${theme}.png`, console_errors: [], problems: [] };
      sink = o.console_errors;
      await page.evaluate((t) => { document.documentElement.setAttribute('data-theme', t); delete window.psContrast; }, theme);
      await page.waitForTimeout(200);
      if (opt.contrast || info.contrast) await page.evaluate(CONTRAST_JS).catch((e) => o.console_errors.push('проверка контраста: ' + String(e).slice(0, 120)));
      const i2 = await page.evaluate(INFO_FN, [BADGE_RE.source, width, CORE_ROLES, OPT_ROLES]);
      if (info.kit && before === await rootColors()) o.problems.push(`вторая тема не отличается от первой (фон и текст те же) — в tokens.css нет блока [data-theme="${theme}"] или он перекрыт :root`);
      if (i2.overflow) o.problems.push(`горизонтальное переполнение ${i2.w}px > ${width}px`);
      if (i2.contrast && i2.contrast.fails.length) { o.contrast = { checked: i2.contrast.checked, fails: i2.contrast.fails.length }; o.problems.push(`нарушений контраста ${i2.contrast.fails.length}`); }
      if (i2.kit) {
        const fb = fallbackOf(i2, decl || pageDecls(htmlAbs)).filter((c) => c.core && c.theme.startsWith(theme));
        if (fb.length && (TOKENS_VARS > 0 || rec.page_vars > 0)) o.problems.push(`использован запасной цвет набора (${fb.map((c) => c.var).join(', ')}) — в tokens.css нет блока [data-theme="${theme}"] для этих ролей`);
      }
      const other = o.console_errors.filter((e) => !/^контраст /.test(e));
      if (other.length) o.problems.push(`ошибок консоли ${other.length}`);
      await page.screenshot(Object.assign({}, so, { path: path.resolve(OUT, o.png) }));
      rec.other_theme = o;
    }
  } catch (e) { rec.error = String(e.message || e).split('\n')[0].slice(0, 200); }
  await ctx.close();
  const problems = [];
  if (rec.error) problems.push(rec.error);
  if (rec.console_errors.length) problems.push(`ошибок консоли ${rec.console_errors.length}`);
  if (rec.external_requests.length) problems.push(`внешних запросов ${rec.external_requests.length}`);
  if (rec.overflow_x) problems.push(`горизонтальное переполнение ${rec.scroll_width}px > ${width}px`);
  if (rec.kind === 'concept' && rec.badge === false) problems.push('нет бейджа «Концепт» (.ps-concept-badge)');
  if (rec.kind !== 'current' && rec.badge_truncated) problems.push('текст бейджа концепта обрезан: «' + rec.badge_truncated[0].text.slice(0, 50) + `» (нужно ${rec.badge_truncated[0].need}px, есть ${rec.badge_truncated[0].have}px) — короче текст или .is-strip/.is-inline`);
  if (width < 600 && rec.viewport_meta === false) problems.push('мобильный макет без <meta name=viewport>');
  if (rec.contrast && rec.contrast.fails) problems.push(`нарушений контраста ${rec.contrast.fails}`);
  if (rec.tall) problems.push(rec.tall);
  if (rec.targets && rec.targets.small_total) problems.push(`цели нажатия меньше ${rec.targets.min}px (${rec.targets.mode}): ${rec.targets.small_total} — ` +
    rec.targets.small.slice(0, 3).map((x) => `${x.el}${x.text ? ' «' + x.text + '»' : ''} ${x.w}×${x.h}`).join('; '));
  if (rec.targets && rec.targets.drag_without_buttons.length) problems.push(`перетаскивание без дублирования кнопками (data-drag-alt): ${rec.targets.drag_without_buttons.slice(0, 3).join(', ')}`);
  if (rec.layout && rec.layout.length) problems.push(`элементы обрезаны/вылезают из ряда: ${rec.layout.length} — ` +
    rec.layout.slice(0, 3).map((x) => x.type === 'hidden_scroll' ? `${x.el} прячет ${x.over}px за прокруткой` : `${x.child}${x.text ? ' «' + x.text + '»' : ''} вылезает из ${x.el} на ${x.over}px`).join('; '));
  if (HS_MIN && rec.kind === 'concept' && !rec.error && (rec.hotspots ? rec.hotspots.count : 0) < HS_MIN) problems.push(`размечено элементов data-hs ${(rec.hotspots ? rec.hotspots.count : 0)} < ${HS_MIN} (стандарт — 12–25, references/design.md)`);
  if (rec.bad_colors) problems.push('значение роли — не цвет: ' + rec.bad_colors.map((c) => `${c.var} (${c.theme}) = «${c.value.slice(0, 40)}»`).join(', ') +
    ' — в tokens.css задайте цвет целиком (#hex, rgb(), hsl()), «голые» тройки HSL набор не понимает');
  const fbCore = rec.fallback_colors.filter((c) => c.core); const fbOpt = rec.fallback_colors.filter((c) => !c.core);
  const fbText = (list) => [...new Set(list.map((c) => c.theme))].map((t) => `${t}: ` + list.filter((c) => c.theme === t)
    .map((c) => (list.length <= 3 ? `${c.var} = ${c.value}` : c.var.slice(4))).join(', ')).join('; ');
  if (fbCore.length) {
    if (TOKENS_VARS > 0 || rec.page_vars > 0) {
      problems.push(`использован запасной цвет набора (${fbText(fbCore)}) — токены продукта не дошли до набора: в mockups/tokens.css нет --c-* ` +
        'и имён моста (--primary, --bg, --surface/--card, --text, --muted, --border)' +
        (fbCore.some((c) => c.theme.startsWith('dark')) ? '; для тёмной темы нужен блок [data-theme="dark"]' : '') +
        (fbCore.some((c) => c.theme.includes(':')) ? '; для режима — --c-* в tokens-<режим>.css под [data-mode="<режим>"]' : ''));
    } else rec.warnings.push(`tokens.css пуст — макет нарисован запасной палитрой набора (${fbText(fbCore)})`);
  }
  if (fbOpt.length && (TOKENS_VARS > 0 || rec.page_vars > 0)) rec.warnings.push(`запасные значения необязательных ролей (${fbText(fbOpt)})`);
  if (rec.other_theme) for (const pr of rec.other_theme.problems) problems.push(`тема ${rec.other_theme.theme}: ${pr}`);
  rec.problems = problems; rec.ok = problems.length === 0;
  finish();
  console.log(`${rec.ok ? 'OK  ' : 'FAIL'} ${it.key} ${width}x${height} → ${rec.png}${rec.other_theme ? ' + ' + rec.other_theme.png : ''}${problems.length ? ' | ' + problems.join('; ') : ''}`);
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
    // координаты подсказок для просмотра макетов на странице (E): mockups/hotspots.json, r — доли ширины и высоты PNG (0…1)
    const hsOut = { version: 1, date: DATE, tool: 'shoot_mockups.mjs', mockups: {} };
    for (const r of merged) {
      const zs = (r.hotspots && r.hotspots.zones) || [];
      const dim = zs.length ? pngSize(path.resolve(OUT, r.png || '')) : null;
      if (!dim) continue;
      const sc = (r.hotspots && r.hotspots.scale) || 1, W = dim.w / sc, H = dim.h / sc, f = (v) => Math.round(v * 10000) / 10000;
      const items = zs.filter((z) => z.w && z.h).map((z) => ({ n: z.n, id: z.id, title: z.title, what: z.what, why: z.why, p: z.p, sec: z.sec,
        r: [f(z.x / W), f(z.y / H), f(z.w / W), f(z.h / H)] }));
      if (items.length) hsOut.mockups[r.key] = { items };
    }
    if (Object.keys(hsOut.mockups).length) {
      fs.mkdirSync(path.join(OUT, 'mockups'), { recursive: true });
      writeAtomic(path.join(OUT, 'mockups', 'hotspots.json'), JSON.stringify(hsOut, null, 1) + '\n');
    }
    console.log(`итого в этом запуске: ${runSummary.ok}/${runSummary.total} без замечаний; в агрегате ${summary.ok}/${summary.total}` +
      `${summary.not_shot ? ` (не снято ${summary.not_shot})` : ''} → data/mockups-check.json`);
  });
} else {
  console.log(`набор компонентов: ${runSummary.ok}/${runSummary.total} без замечаний → data/mockups-check._*.json`);
}
process.exit(runSummary.failed && !opt['no-fail'] ? 1 : 0);
