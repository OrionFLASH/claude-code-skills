#!/usr/bin/env node
// Проверка блок-схем (charts/flows/*.svg) на пересечения блоков и подписей (product-strategy).
//
//   node check_flow.mjs <OUT> [--only key1,key2] [--draw <папка>] [--tolerance 2] [--no-fail] [--node-dir <dir>]
//
// Схемы — из data/flows.json (key, svg); нет файла — все charts/flows/*.svg. Каждый SVG открывается в Chromium
// (только file:// внутри <OUT>, внешние запросы блокируются), рамки берутся из getBoundingClientRect:
//   - блок — элемент с data-node="<key>:<n>"; его рамка — первая фигура внутри (rect, ellipse, circle, polygon, path),
//     иначе вся группа;
//   - подпись — каждый <text> (многострочный <text> с <tspan> — одна подпись); подпись внутри data-node — подпись блока,
//     остальные — подписи стрелок и заголовки.
// Замечания (FAIL):
//   node_overlap   — рамки двух блоков пересекаются (глубже --tolerance px по обеим осям);
//   text_overflow  — подпись блока выходит за его рамку;
//   text_overlap   — две подписи накладываются (по высоте больше четверти строки);
//   label_on_node  — подпись стрелки или заголовок лежит на чужом блоке;
//   text_clipped   — подпись выходит за край рисунка (viewBox).
// Предупреждения: data-node без записи в nodes[] схемы и наоборот; повтор data-node; в схеме нет ни одного data-node.
// Итог: data/flows-check.json {date, tool, summary, items: [{key, svg, ok, nodes, texts, problems[], warnings[]}]}.
// --draw <папка> — PNG <key>.png со схемой и красными рамками замечаний (для проверки глазами через Read).
// Код выхода: 0 — замечаний нет (или --no-fail), 1 — есть замечания, 2 — ошибка аргументов/данных, 3 — нет playwright/Chromium.
// Модули: --node-dir | $PS_NODE_DIR | <OUT>/build/node | ~/.cache/product-strategy/node | папка скрипта.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(HERE, '..', '..');
const USAGE = 'node check_flow.mjs <OUT> [--only key1,key2] [--draw <папка>] [--tolerance 2] [--no-fail] [--node-dir <dir>]';

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

const { pos, opt } = parseArgs(process.argv.slice(2), new Set(['no-fail']));
if (opt.help || pos.length < 1) { console.log(USAGE); process.exit(opt.help ? 0 : 2); }
const OUT = path.resolve(pos[0]);
if (!fs.existsSync(OUT)) { console.error('ошибка: нет папки ' + OUT); process.exit(2); }
const OUT_REAL = fs.realpathSync(OUT);
const TOL = Number(opt.tolerance ?? 2);
if (!Number.isFinite(TOL) || TOL < 0) { console.error('ошибка: --tolerance — число ≥ 0'); process.exit(2); }
const only = new Set((opt.only || '').split(',').map((s) => s.trim()).filter(Boolean));
const DRAW = opt.draw ? path.resolve(String(opt.draw)) : null;

function inside(p) {
  let real; try { real = fs.realpathSync(p); } catch { real = path.resolve(p); }
  return real === OUT_REAL || real.startsWith(OUT_REAL + path.sep);
}

// ------------------------------------------------------------ список схем
let flows = [];
const flowsPath = path.join(OUT, 'data', 'flows.json');
if (fs.existsSync(flowsPath)) {
  let d; try { d = JSON.parse(fs.readFileSync(flowsPath, 'utf8')); } catch (e) { console.error('ошибка: data/flows.json не разобран: ' + e.message); process.exit(2); }
  if (!Array.isArray(d)) { console.error('ошибка: data/flows.json должен быть списком'); process.exit(2); }
  flows = d.filter((f) => f && f.key).map((f) => ({ key: String(f.key), svg: f.svg || `charts/flows/${f.key}.svg`, nodes: (f.nodes || []).map((n) => n && n.id).filter(Boolean), json: true }));
} else {
  const dir = path.join(OUT, 'charts', 'flows');
  if (fs.existsSync(dir)) flows = fs.readdirSync(dir).filter((f) => /\.svg$/i.test(f)).sort().map((f) => ({ key: f.replace(/\.svg$/i, ''), svg: `charts/flows/${f}`, nodes: null, json: false }));
}
if (only.size) flows = flows.filter((f) => only.has(f.key));
if (!flows.length) { console.error('ошибка: нет схем (data/flows.json или charts/flows/*.svg)' + (only.size ? ' с ключами ' + [...only].join(', ') : '')); process.exit(2); }

function svgSize(src) {
  const tag = (/<svg\b[^>]*>/i.exec(src) || [''])[0];
  const num = (a) => { const m = new RegExp(`\\b${a}\\s*=\\s*["']\\s*([\\d.]+)(px)?\\s*["']`, 'i').exec(tag); return m ? +m[1] : null; };
  const vb = /viewBox\s*=\s*["']\s*([-\d.]+)[\s,]+([-\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/i.exec(tag);
  const w = num('width') || (vb ? +vb[3] : 1200); const h = num('height') || (vb ? +vb[4] : 800);
  return { w: Math.min(Math.max(Math.round(w), 50), 6000), h: Math.min(Math.max(Math.round(h), 50), 6000) };
}

const pw = loadPlaywright(opt, OUT);
let browser;
try { browser = await pw.chromium.launch({ headless: true }); }
catch (e) {
  console.error('не запустился Chromium: ' + String(e.message || e).split('\n')[0]);
  console.error(`поставьте браузер: python3 ${path.join(SKILL_DIR, 'scripts', 'check_env.py')} --install-node ${OUT}`);
  process.exit(3);
}

const items = [];
for (const f of flows) {
  const rec = { key: f.key, svg: f.svg, ok: false, nodes: 0, texts: 0, problems: [], warnings: [] };
  items.push(rec);
  const abs = path.resolve(OUT, f.svg);
  if (!fs.existsSync(abs) || !inside(abs)) { rec.problems.push({ type: 'missing', msg: 'нет SVG внутри <OUT>: ' + f.svg }); console.log(`FAIL ${f.key}: нет ${f.svg}`); continue; }
  const src = fs.readFileSync(abs, 'utf8');
  const { w, h } = svgSize(src);
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, serviceWorkers: 'block' });
  await ctx.route('**/*', (route) => {
    const u = route.request().url();
    if (u.startsWith('data:') || u.startsWith('blob:')) return route.continue();
    if (u.startsWith('file:')) { try { if (inside(fileURLToPath(u))) return route.continue(); } catch { /* */ } }
    rec.warnings.push('заблокирован внешний запрос: ' + u.slice(0, 120));
    return route.abort('blockedbyclient');
  });
  const page = await ctx.newPage();
  let data;
  try {
    await page.goto(pathToFileURL(abs).href, { waitUntil: 'load', timeout: 30000 });
    await page.evaluate(() => document.fonts && document.fonts.ready).catch(() => {});
    data = await page.evaluate(() => {
      const box = (el) => { const r = el.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; };
      const root = document.documentElement; const rb = box(root);
      const nodes = [...document.querySelectorAll('[data-node]')].map((g) => {
        const shape = g.matches('rect, ellipse, circle, polygon, path') ? g : g.querySelector('rect, ellipse, circle, polygon, path');
        return { id: g.getAttribute('data-node'), box: box(shape || g) };
      });
      const texts = [...document.querySelectorAll('text')].filter((t) => (t.textContent || '').trim()).map((t) => {
        const g = t.closest('[data-node]');
        return { text: t.textContent.replace(/\s+/g, ' ').trim().slice(0, 60), node: g ? g.getAttribute('data-node') : null, box: box(t) };
      }).filter((t) => t.box.w > 0 && t.box.h > 0);
      return { root: rb, nodes, texts };
    });
  } catch (e) { rec.problems.push({ type: 'error', msg: String(e.message || e).split('\n')[0].slice(0, 200) }); }
  if (data) {
    rec.nodes = data.nodes.length; rec.texts = data.texts.length;
    const ov = (a, b) => ({ w: Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x), h: Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) });
    const inBox = (t, b, tol) => t.x >= b.x - tol && t.y >= b.y - tol && t.x + t.w <= b.x + b.w + tol && t.y + t.h <= b.y + b.h + tol;
    const r1 = (b) => ({ x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.w), h: Math.round(b.h) });
    const add = (type, msg, boxes) => rec.problems.push({ type, msg, boxes: boxes.map(r1) });
    const N = data.nodes; const T = data.texts;
    for (let i = 0; i < N.length; i++) for (let j = i + 1; j < N.length; j++) {
      const o = ov(N[i].box, N[j].box);
      if (o.w > TOL && o.h > TOL) add('node_overlap', `блоки ${N[i].id} и ${N[j].id} пересекаются (${Math.round(o.w)}×${Math.round(o.h)} px)`, [N[i].box, N[j].box]);
    }
    const nodeBox = new Map(N.map((n) => [n.id, n.box]));
    for (const t of T) {
      if (t.node && nodeBox.has(t.node) && !inBox(t.box, nodeBox.get(t.node), TOL)) add('text_overflow', `подпись «${t.text}» выходит за блок ${t.node}`, [t.box, nodeBox.get(t.node)]);
      if (!inBox(t.box, data.root, 1)) add('text_clipped', `подпись «${t.text}» выходит за край рисунка`, [t.box]);
      if (!t.node) for (const n of N) {
        const o = ov(t.box, n.box);
        if (o.w > TOL && o.h > TOL) add('label_on_node', `подпись «${t.text}» лежит на блоке ${n.id}`, [t.box, n.box]);
      }
    }
    for (let i = 0; i < T.length; i++) for (let j = i + 1; j < T.length; j++) {
      const o = ov(T[i].box, T[j].box);
      if (o.w > TOL && o.h > Math.max(TOL, 0.25 * Math.min(T[i].box.h, T[j].box.h))) add('text_overlap', `подписи «${T[i].text}» и «${T[j].text}» накладываются`, [T[i].box, T[j].box]);
    }
    const ids = N.map((n) => n.id);
    const dupl = [...new Set(ids.filter((x, k) => ids.indexOf(x) !== k))];
    if (dupl.length) rec.warnings.push('повтор data-node: ' + dupl.join(', '));
    if (!N.length) rec.warnings.push('в схеме нет ни одного data-node — узлы на странице не кликабельны');
    if (f.nodes) {
      const miss = f.nodes.filter((x) => !ids.includes(x)); const extra = [...new Set(ids)].filter((x) => !f.nodes.includes(x));
      if (miss.length) rec.warnings.push('узлы из data/flows.json без data-node в SVG: ' + miss.join(', '));
      if (extra.length) rec.warnings.push('data-node без записи в nodes[] data/flows.json: ' + extra.join(', '));
    }
    if (DRAW && rec.problems.length) {
      const shot = await page.screenshot({ fullPage: false });
      const boxes = rec.problems.flatMap((p) => p.boxes || []).map((b) =>
        `<div style="position:absolute;left:${b.x - 2}px;top:${b.y - 2}px;width:${b.w + 4}px;height:${b.h + 4}px;border:2px solid #e5112d;background:rgba(229,17,45,.12);box-sizing:border-box"></div>`).join('');
      const html = `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;width:${w}px;height:${h}px;overflow:hidden;background:#fff}img{position:absolute;left:0;top:0}</style></head>` +
        `<body><img src="data:image/png;base64,${shot.toString('base64')}">${boxes}</body></html>`;
      const dp = await ctx.newPage();
      await dp.setContent(html, { waitUntil: 'load' });
      fs.mkdirSync(DRAW, { recursive: true });
      await dp.screenshot({ path: path.join(DRAW, `${f.key.replace(/[^\w.-]+/g, '_')}.png`) });
    }
  }
  await ctx.close();
  rec.ok = rec.problems.length === 0;
  const byType = {}; rec.problems.forEach((p) => { byType[p.type] = (byType[p.type] || 0) + 1; });
  console.log(`${rec.ok ? 'OK  ' : 'FAIL'} ${f.key}: блоков ${rec.nodes}, подписей ${rec.texts}${rec.ok ? '' : ' | ' + Object.entries(byType).map(([k, v]) => `${k} ${v}`).join(', ')}`);
  for (const p of rec.problems.slice(0, 8)) console.log(`     ${p.msg}`);
  if (rec.problems.length > 8) console.log(`     … и ещё ${rec.problems.length - 8}`);
  for (const wmsg of rec.warnings) console.log(`     предупреждение: ${wmsg}`);
}
await browser.close();

const summary = { flows: items.length, ok: items.filter((r) => r.ok).length, failed: items.filter((r) => !r.ok).length,
  problems: items.reduce((a, r) => a + r.problems.length, 0), warnings: items.reduce((a, r) => a + r.warnings.length, 0) };
const outFile = path.join(OUT, 'data', 'flows-check.json');
let prev = {}; try { prev = JSON.parse(fs.readFileSync(outFile, 'utf8')); } catch { /* нет прежнего */ }
const merged = only.size ? [...(prev.items || []).filter((r) => r && !only.has(r.key)), ...items] : items;
const sumAll = only.size ? { flows: merged.length, ok: merged.filter((r) => r.ok).length, failed: merged.filter((r) => !r.ok).length,
  problems: merged.reduce((a, r) => a + (r.problems || []).length, 0), warnings: merged.reduce((a, r) => a + (r.warnings || []).length, 0) } : summary;
fs.mkdirSync(path.dirname(outFile), { recursive: true });
const tmp = `${outFile}.${process.pid}.tmp`;
fs.writeFileSync(tmp, JSON.stringify({ date: new Date().toISOString().slice(0, 10), tool: 'check_flow.mjs', tolerance: TOL, summary: sumAll, items: merged }, null, 2) + '\n');
fs.renameSync(tmp, outFile);
console.log(`итого: схем без замечаний ${summary.ok}/${summary.flows}, замечаний ${summary.problems} → data/flows-check.json${DRAW && summary.problems ? `; рисунки — ${DRAW}` : ''}`);
process.exit(summary.failed && !opt['no-fail'] ? 1 : 0);
