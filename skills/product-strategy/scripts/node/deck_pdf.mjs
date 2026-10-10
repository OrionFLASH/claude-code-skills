#!/usr/bin/env node
// PDF колоды: HTML-двойник <OUT>/build/deck.json (16:9, тот же контент, что в PPTX) → печать Chromium
// (Playwright) → <OUT>/deliverables/strategy.pdf. LibreOffice не нужен.
//
//   node deck_pdf.mjs <OUT> [--node-dir <dir>]
//
// Модули: --node-dir, env PS_NODE_DIR, <OUT>/build/node, ~/.cache/product-strategy/node, папка скрипта (<dir>/node_modules). Нет playwright —
// код 3 и совет по установке. HTML-двойник остаётся в <OUT>/build/deck.html (для отладки вёрстки).
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(SCRIPT_DIR, '..', '..');

function parseArgs(argv) {
  const a = { out: null, nodeDir: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--node-dir') a.nodeDir = argv[++i];
    else if (argv[i] === '-h' || argv[i] === '--help') { console.log('node deck_pdf.mjs <OUT> [--node-dir <dir>]'); process.exit(0); }
    else if (!a.out) a.out = argv[i];
  }
  return a;
}
function loadModule(name, dirs) {
  for (const d of dirs.filter(Boolean)) {
    try {
      return createRequire(path.join(path.resolve(d), 'node_modules', '_resolver.cjs'))(name);
    } catch (e) {
      if (e.code !== 'MODULE_NOT_FOUND') throw e;
    }
  }
  return null;
}

const args = parseArgs(process.argv.slice(2));
if (!args.out) { console.error('использование: node deck_pdf.mjs <OUT> [--node-dir <dir>]'); process.exit(2); }
const OUT = path.resolve(args.out);
const pw = loadModule('playwright', [args.nodeDir, process.env.PS_NODE_DIR, path.join(OUT, 'build', 'node'), path.join(process.env.HOME || process.env.USERPROFILE || '', '.cache', 'product-strategy', 'node'), SCRIPT_DIR]);
if (!pw) {
  console.error(`нет playwright: python3 ${path.join(SKILL_DIR, 'scripts', 'check_env.py')} --install-node ${OUT}`);
  process.exit(3);
}
const deckPath = path.join(OUT, 'build', 'deck.json');
if (!fs.existsSync(deckPath)) {
  console.error(`нет ${deckPath}: сначала python3 ${path.join(SKILL_DIR, 'scripts', 'build_deck_json.py')} ${OUT}`);
  process.exit(2);
}
const deck = JSON.parse(fs.readFileSync(deckPath, 'utf8'));
const meta = deck.meta || {};
const T = { bg: 'FFFFFF', surface: 'F3F5F8', text: '1F2933', muted: '5F6B7A', accent: '2563EB', accent2: 'D97706', border: 'D5DBE3', font: 'Calibri', ...(meta.theme || {}) };
const FOOT = meta.footer || [meta.product, meta.copyright || meta.author].filter(Boolean).join(' · ');

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const cut = (s, n) => { s = String(s ?? '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n).replace(/\s+\S*$/, '') + '…' : s; };
const MIME = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif', '.svg': 'image/svg+xml' };
function img(rel) {
  if (!rel) return '';
  const f = path.resolve(OUT, rel);
  if (!fs.existsSync(f)) return '';
  return `data:${MIME[path.extname(f).toLowerCase()] || 'image/png'};base64,${fs.readFileSync(f).toString('base64')}`;
}
const ul = (items, cls = '') => items?.length ? `<ul class="${cls}">${items.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>` : '';
const figure = (rel, cap, cls = '') => {
  const src = img(rel);
  return src ? `<figure class="${cls}"><img src="${src}" alt=""><figcaption>${esc(cap || '')}</figcaption></figure>`
    : `<p class="missing">Картинка не найдена: ${esc(rel || '—')}</p>`;
};

const total = (deck.slides || []).length;
let n = 0;
const slides = (deck.slides || []).map((s) => {
  n++;
  const foot = `<footer><span>${esc(FOOT)}</span><span class="num">${n} / ${total}</span></footer>`;
  const h2 = `<h2>${esc(s.title || '')}</h2>`;
  switch (s.type) {
    case 'title': return `<section class="slide title"><div class="bar"></div><h1>${esc(s.title)}</h1><p class="sub">${esc(s.subtitle || '')}</p>${foot}</section>`;
    case 'section': return `<section class="slide section"><div class="rule"></div><h1>${esc(s.title)}</h1><p class="sub">${esc(s.subtitle || '')}</p>${foot}</section>`;
    case 'bullets': {
      const im = s.image ? figure(s.image, s.caption) : '';
      return `<section class="slide">${h2}<div class="body ${im ? 'two' : ''}">${ul(s.bullets, 'big')}${im}</div>${!im && s.caption ? `<p class="cap">${esc(s.caption)}</p>` : ''}${foot}</section>`;
    }
    case 'image': return `<section class="slide">${h2}<div class="body">${figure(s.image, s.caption, 'full')}</div>${foot}</section>`;
    case 'stats': return `<section class="slide">${h2}<div class="stats">${(s.stats || []).slice(0, 6).map((x) => `<div class="stat"><div class="v">${esc(x.value)}</div><div class="l">${esc(x.label)}</div></div>`).join('')}</div>${ul(s.bullets, 'big')}${foot}</section>`;
    case 'table': {
      const cols = s.columns || [];
      const widths = s.colW && s.colW.length === cols.length ? s.colW : null;
      return `<section class="slide">${h2}<table style="font-size:${s.fontSize || (cols.length > 7 ? 9 : 11)}pt">${widths ? `<colgroup>${widths.map((w) => `<col style="width:${w}in">`).join('')}</colgroup>` : ''}`
        + `<thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${(s.rows || []).map((r) => `<tr>${cols.map((_, i) => `<td>${esc(cut(r[i], 160))}</td>`).join('')}</tr>`).join('')}</tbody></table>`
        + `${s.caption ? `<p class="cap">${esc(s.caption)}</p>` : ''}${foot}</section>`;
    }
    case 'card': {
      const c = s.card || {};
      const metaLine = [c.category, c.segment, c.evidence_class && `класс ${c.evidence_class}`, c.priority, c.horizon, c.quadrant, c.kano && `Кано: ${c.kano}`, c.effort, c.cost, ...(c.labels || [])].filter(Boolean).join(' · ');
      const mock = c.mockup ? img(c.mockup) : '';
      return `<section class="slide card">${h2}<div class="tiles">${(c.metrics || []).slice(0, 6).map(([l, v]) => `<div class="stat"><div class="v">${esc(v)}</div><div class="l">${esc(l)}</div></div>`).join('')}</div>`
        + `<p class="meta">${esc(cut(metaLine, 230))}</p><div class="cols ${mock ? 'three' : ''}">`
        + `<div><p><b>Что сделать:</b> ${esc(cut(c.description, mock ? 330 : 430))}</p><p><b>Почему:</b> ${esc(cut(c.rationale, mock ? 260 : 330))}</p><p><b>Сейчас:</b> ${esc(cut(c.current_feature, 160))}</p></div>`
        + `<div><p><b>Шаги:</b></p><ol>${(c.steps || []).slice(0, 4).map((t) => `<li>${esc(cut(t, 110))}</li>`).join('')}</ol>`
        + `<p><b>KPI:</b> ${esc(cut((c.kpi || []).join('; '), 160))}</p><p><b>Дешёвая проверка:</b> ${esc(cut(c.cheap_test, 170))}</p><p><b>Риски:</b> ${esc(cut(c.risks, 140))}</p>`
        + `${s.sources?.length ? `<p class="src">Источники: ${s.sources.slice(0, 4).map(esc).join(' · ')}</p>` : ''}</div>`
        + `${mock ? `<figure><img src="${mock}" alt=""><figcaption>Концепт, не существующая функция</figcaption></figure>` : ''}</div>${foot}</section>`;
    }
    default: return '';
  }
}).filter(Boolean);

const c = (h) => '#' + h;
const html = `<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>${esc(meta.title || 'Стратегия')}</title>
<meta name="author" content="${esc(meta.author || '')}"><meta name="copyright" content="${esc(meta.copyright || '')}"><style>
@page { size: 13.333in 7.5in; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; background: ${c(T.bg)}; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: '${T.font}', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif; color: ${c(T.text)}; }
.slide { width: 13.333in; height: 7.5in; padding: 0.4in 0.6in 0.75in; position: relative; overflow: hidden; background: ${c(T.bg)}; page-break-after: always; break-after: page; }
.slide:last-child { page-break-after: auto; break-after: auto; }
.slide.section { background: ${c(T.surface)}; }
.title .bar { position: absolute; left: 0; top: 0; bottom: 0; width: 0.18in; background: ${c(T.accent)}; }
.title h1 { font-size: 40pt; font-weight: 600; color: ${c(T.accent)}; margin: 2.0in 0 0.2in; line-height: 1.1; }
.section .rule { width: 1.2in; height: 0.08in; background: ${c(T.accent)}; margin-top: 2.15in; }
.section h1 { font-size: 34pt; font-weight: 600; margin: 0.15in 0 0.15in; line-height: 1.15; }
.sub { font-size: 17pt; color: ${c(T.muted)}; max-width: 11.5in; margin: 0; }
h2 { font-size: 23pt; font-weight: 600; color: ${c(T.accent)}; margin: 0 0 0.22in; line-height: 1.15; max-height: 0.9in; overflow: hidden; }
footer { position: absolute; left: 0.6in; right: 0.6in; bottom: 0.25in; display: flex; justify-content: space-between; gap: 0.3in; font-size: 9pt; color: ${c(T.muted)}; border-top: 0.75pt solid ${c(T.border)}; padding-top: 0.07in; }
.title footer, .section footer { border-top: 0; }
.body.two { display: grid; grid-template-columns: 1fr 1fr; gap: 0.35in; align-items: start; }
ul { margin: 0; padding-left: 0.3in; } li { margin-bottom: 0.1in; line-height: 1.35; }
ul.big li { font-size: 16pt; }
figure { margin: 0; text-align: center; } figure img { max-width: 100%; max-height: 4.9in; object-fit: contain; display: block; margin: 0 auto; }
figure.full img { max-height: 5.05in; }
figcaption, .cap { font-size: 10pt; color: ${c(T.muted)}; font-style: italic; margin-top: 0.08in; text-align: left; }
.missing { color: ${c(T.muted)}; font-size: 14pt; margin-top: 1.5in; text-align: center; }
.stats, .tiles { display: flex; gap: 0.22in; margin-bottom: 0.3in; }
.stat { flex: 1; background: ${c(T.surface)}; border: 1pt solid ${c(T.accent)}; border-radius: 0.1in; padding: 0.15in; }
.stat .v { font-size: 34pt; font-weight: 700; color: ${c(T.accent)}; line-height: 1.1; } .stat .l { font-size: 12pt; margin-top: 0.08in; }
.tiles { margin-bottom: 0.12in; } .tiles .stat { padding: 0.06in 0.1in; } .tiles .v { font-size: 19pt; } .tiles .l { font-size: 9pt; color: ${c(T.muted)}; margin-top: 0; }
.card .meta { font-size: 10pt; color: ${c(T.muted)}; margin: 0 0 0.12in; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 0.3in; font-size: 11pt; line-height: 1.38; }
.cols.three { grid-template-columns: 4.5in 4.0in 1fr; gap: 0.25in; }
.cols p { margin: 0 0 0.07in; } .cols b { color: ${c(T.accent2)}; } .cols ol { margin: 0 0 0.07in; padding-left: 0.25in; } .cols ol li { margin-bottom: 0.03in; }
.cols figure img { max-height: 3.3in; } .src { font-size: 8pt; color: ${c(T.muted)}; word-break: break-all; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; }
th { background: ${c(T.accent)}; color: #fff; text-align: left; padding: 0.04in 0.06in; border: 0.5pt solid ${c(T.border)}; }
td { padding: 0.035in 0.06in; border: 0.5pt solid ${c(T.border)}; vertical-align: top; overflow-wrap: anywhere; }
tbody tr:nth-child(odd) td { background: ${c(T.surface)}; }
</style></head><body>${slides.join('\n')}</body></html>`;

const htmlPath = path.join(OUT, 'build', 'deck.html');
fs.mkdirSync(path.dirname(htmlPath), { recursive: true });
fs.writeFileSync(htmlPath, html);
const outFile = path.join(OUT, 'deliverables', 'strategy.pdf');
fs.mkdirSync(path.dirname(outFile), { recursive: true });
let browser;
try {
  browser = await pw.chromium.launch();
} catch (e) {
  console.error('Chromium не запустился: ' + e.message.split('\n')[0]);
  console.error(`установите браузер: python3 ${path.join(SKILL_DIR, 'scripts', 'check_env.py')} --install-node ${OUT}`);
  process.exit(3);
}
try {
  const page = await browser.newPage();
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'load' });
  await page.pdf({ path: outFile, width: '13.333in', height: '7.5in', printBackground: true, preferCSSPageSize: true,
    margin: { top: 0, right: 0, bottom: 0, left: 0 } });
} finally {
  await browser.close();
}
const kb = Math.round(fs.statSync(outFile).size / 1024);
console.log(`PDF: ${outFile} (${kb} КБ) — страниц ${slides.length}; HTML-двойник ${htmlPath}`);
