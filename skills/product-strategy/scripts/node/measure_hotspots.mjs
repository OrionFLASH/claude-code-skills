#!/usr/bin/env node
// Замер кликабельных зон карточки референса дизайна (product-strategy).
//
//   node measure_hotspots.mjs <OUT> <design-ref.json> --spec <spec.json> [--min 24] [--node-dir <dir>]
//
// <design-ref.json> — карточка design-refs/NN-slug.json (путь от текущей папки или от <OUT>); из неё берутся
// file (HTML внутри <OUT>), width×height (по умолчанию 1440×900), scale (deviceScaleFactor, по умолчанию 1), png.
// <spec.json> — список [{n, selector, title, text, proposal, state}] (или {"hotspots": [...]}).
// Синтаксис selector: "a || b" — объединение рамок; "sel@2" — третье совпадение; "sel@all" — все совпадения;
// без @ селектор должен находить ровно один элемент (иначе предупреждение и берётся первый).
// Необязательно: "clipBottom": "<selector>" — обрезать рамку по верхнему краю этого элемента.
// Рамки — CSS-пиксели исходного размера (getBoundingClientRect), обрезаются по экрану, минимум --min×--min.
// Записывает hotspots в карточку (на месте) и PNG карточки (<OUT>/<png>). Внешние запросы блокируются.
// Код выхода: 0 — все селекторы найдены, 1 — есть ненайденные (найденные всё равно записаны),
// 2 — ошибка аргументов, 3 — нет playwright/Chromium.
// Модули: --node-dir | $PS_NODE_DIR | <OUT>/build/node | папка скрипта.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(HERE, '..', '..');
const USAGE = 'node measure_hotspots.mjs <OUT> <design-ref.json> --spec <spec.json> [--min 24] [--node-dir <dir>]';

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

const { pos, opt } = parseArgs(process.argv.slice(2), new Set());
if (opt.help || pos.length < 2 || !opt.spec) { console.log(USAGE); process.exit(opt.help ? 0 : 2); }
const OUT = path.resolve(pos[0]);
const OUT_REAL = fs.realpathSync(OUT);
const resolveIn = (p) => (fs.existsSync(path.resolve(p)) ? path.resolve(p) : path.resolve(OUT, p));
const cardPath = resolveIn(pos[1]);
const specPath = resolveIn(opt.spec);
const MIN = parseInt(opt.min || '24', 10);
let card, spec;
try { card = JSON.parse(fs.readFileSync(cardPath, 'utf8')); } catch (e) { console.error('ошибка: карточка не прочитана: ' + e.message); process.exit(2); }
try { spec = JSON.parse(fs.readFileSync(specPath, 'utf8')); } catch (e) { console.error('ошибка: spec не прочитан: ' + e.message); process.exit(2); }
if (spec && !Array.isArray(spec)) spec = spec.hotspots;
if (!Array.isArray(spec) || !spec.length) { console.error('ошибка: spec должен быть непустым списком [{n, selector, …}]'); process.exit(2); }
if (!card.file) { console.error('ошибка: в карточке нет поля file'); process.exit(2); }

function inside(p) {
  let real; try { real = fs.realpathSync(p); } catch { real = path.resolve(p); }
  return real === OUT_REAL || real.startsWith(OUT_REAL + path.sep);
}
const htmlAbs = path.resolve(OUT, card.file);
if (!fs.existsSync(htmlAbs) || !inside(htmlAbs)) { console.error('ошибка: HTML карточки не найден внутри <OUT>: ' + card.file); process.exit(2); }
const W = parseInt(card.width || 1440, 10); const H = parseInt(card.height || 900, 10);
const SCALE = Number(card.scale || 1);
const base = path.basename(cardPath).replace(/\.json$/i, '');
const pngRel = card.png || `design-refs/${base}.png`;
const pngAbs = path.resolve(OUT, pngRel);
if (!pngAbs.startsWith(OUT_REAL + path.sep) && !pngAbs.startsWith(OUT + path.sep)) { console.error('ошибка: png вне <OUT>'); process.exit(2); }

const pw = loadPlaywright(opt, OUT);
let browser;
try { browser = await pw.chromium.launch({ headless: true }); }
catch (e) {
  console.error('не запустился Chromium: ' + String(e.message || e).split('\n')[0]);
  console.error(`поставьте браузер: python3 ${path.join(SKILL_DIR, 'scripts', 'check_env.py')} --install-node ${OUT}`);
  process.exit(3);
}
const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: SCALE, acceptDownloads: false, serviceWorkers: 'block' });
const external = [];
await ctx.route('**/*', (route) => {
  const u = route.request().url();
  if (u.startsWith('data:') || u.startsWith('blob:')) return route.continue();
  if (u.startsWith('file:')) { try { if (inside(fileURLToPath(u))) return route.continue(); } catch { /* */ } }
  external.push(u.slice(0, 160));
  return route.abort('blockedbyclient');
});
const page = await ctx.newPage();
const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)));
await page.goto(pathToFileURL(htmlAbs).href, { waitUntil: 'load', timeout: 30000 });
await page.evaluate(() => document.fonts && document.fonts.ready).catch(() => {});
await page.waitForTimeout(300);

async function measure(sel) {
  return page.evaluate((spec) => {
    const warn = [];
    const pick = (part) => {
      const toks = part.trim().split(/\s+/);
      let roots = [document]; let buf = [];
      const flush = (idx) => {
        const s = buf.join(' '); buf = []; const out = [];
        for (const r of roots) {
          let all; try { all = [...r.querySelectorAll(s)]; } catch { warn.push(`неверный селектор: ${s}`); all = []; }
          if (idx === undefined) { if (all.length !== 1) warn.push(`${s}: совпадений ${all.length}`); if (all[0]) out.push(all[0]); }
          else if (idx === 'all') out.push(...all);
          else { const el = all[+idx]; if (!el) warn.push(`${s}@${idx}: нет`); else out.push(el); }
        }
        roots = out;
      };
      for (const t of toks) { const m = t.match(/^(.*)@(all|\d+)$/); if (m) { buf.push(m[1]); flush(m[2]); } else buf.push(t); }
      if (buf.length) flush();
      return roots;
    };
    const els = spec.split('||').flatMap((p) => pick(p));
    if (!els.length) return { error: 'элементы не найдены', warn };
    let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
    for (const el of els) {
      const r = el.getBoundingClientRect();
      if (!r.width && !r.height) { warn.push('нулевой размер: ' + (el.className || el.tagName)); continue; }
      x1 = Math.min(x1, r.left); y1 = Math.min(y1, r.top); x2 = Math.max(x2, r.right); y2 = Math.max(y2, r.bottom);
    }
    if (x1 === Infinity) return { error: 'все элементы нулевого размера', warn };
    return { raw: [x1, y1, x2 - x1, y2 - y1], n: els.length, warn };
  }, sel);
}

function fit(raw) {
  let [x, y, w, h] = raw;
  if (w < MIN) { x -= (MIN - w) / 2; w = MIN; }
  if (h < MIN) { y -= (MIN - h) / 2; h = MIN; }
  const x1 = Math.max(0, Math.round(x)), y1 = Math.max(0, Math.round(y));
  const x2 = Math.min(W, Math.round(x + w)), y2 = Math.min(H, Math.round(y + h));
  return { x: x1, y: y1, w: Math.max(0, x2 - x1), h: Math.max(0, y2 - y1) };
}

const hotspots = []; const report = []; let missing = 0;
for (const [i, s] of spec.entries()) {
  const n = s.n ?? i + 1;
  if (!s.selector) { report.push({ n, error: 'нет selector' }); missing++; continue; }
  const m = await measure(s.selector);
  if (m.raw && s.clipBottom) {
    const top = await page.evaluate((q) => document.querySelector(q)?.getBoundingClientRect().top ?? null, s.clipBottom).catch(() => null);
    if (top !== null) m.raw[3] = Math.max(0, Math.min(m.raw[3], top - m.raw[1]));
  }
  if (!m.raw) { missing++; report.push({ n, selector: s.selector, error: m.error, warn: m.warn }); console.log(`ERR  ${String(n).padStart(2)} ${s.selector} — ${m.error}`); continue; }
  const box = fit(m.raw);
  if (!box.w || !box.h) { missing++; report.push({ n, selector: s.selector, error: 'рамка вне экрана', warn: m.warn }); console.log(`ERR  ${String(n).padStart(2)} ${s.selector} — вне экрана`); continue; }
  hotspots.push({ n, ...box, title: s.title || '', text: s.text || '', proposal: s.proposal ?? null, state: s.state || 'new' });
  report.push({ n, selector: s.selector, matched: m.n, warn: m.warn });
  console.log(`OK   ${String(n).padStart(2)} ${box.x},${box.y},${box.w}×${box.h} [${m.n}] ${s.selector}${m.warn.length ? ' | ' + m.warn.join('; ') : ''}`);
}
fs.mkdirSync(path.dirname(pngAbs), { recursive: true });
await page.screenshot({ path: pngAbs, fullPage: false });
await browser.close();

card.hotspots = hotspots.sort((a, b) => a.n - b.n);
card.png = pngRel; card.width = W; card.height = H; card.scale = SCALE;
fs.writeFileSync(cardPath, JSON.stringify(card, null, 2) + '\n');
console.log(`зон: ${hotspots.length}/${spec.length}${missing ? `, не найдено ${missing}` : ''}${external.length ? `, заблокировано внешних запросов ${external.length}` : ''}${pageErrors.length ? `, ошибок страницы ${pageErrors.length}` : ''}`);
console.log(`→ ${path.relative(OUT, cardPath) || cardPath}, ${pngRel}`);
process.exit(missing ? 1 : 0);
