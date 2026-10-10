#!/usr/bin/env node
// Сборка <OUT>/deliverables/strategy.pptx из <OUT>/build/deck.json (build_deck_json.py) через pptxgenjs.
//
//   node build_pptx.mjs <OUT> [--node-dir <dir>]
//
// Модули ищутся в <dir>/node_modules: --node-dir, затем env PS_NODE_DIR, затем <OUT>/build/node,
// затем папка этого скрипта. Ничего не ставится глобально. Нет pptxgenjs — код 3 и совет по установке.
// Мастер-слайды TITLE / SECTION / CONTENT, тема — meta.theme (из mockups/tokens.css), подвал с авторством
// и номером на каждом слайде, pres.author/company/title. SVG-графики растрируются в PNG через Chromium
// (playwright), если он доступен; иначе вставляются как SVG (PowerPoint 2016+ их показывает).
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(SCRIPT_DIR, '..', '..');

function parseArgs(argv) {
  const a = { out: null, nodeDir: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--node-dir') a.nodeDir = argv[++i];
    else if (argv[i] === '-h' || argv[i] === '--help') { console.log('node build_pptx.mjs <OUT> [--node-dir <dir>]'); process.exit(0); }
    else if (!a.out) a.out = argv[i];
  }
  return a;
}

function loadModule(name, dirs) {
  for (const d of dirs.filter(Boolean)) {
    try {
      const req = createRequire(path.join(path.resolve(d), 'node_modules', '_resolver.cjs'));
      return req(name);
    } catch (e) {
      if (e.code !== 'MODULE_NOT_FOUND') throw e;
    }
  }
  return null;
}

const args = parseArgs(process.argv.slice(2));
if (!args.out) { console.error('использование: node build_pptx.mjs <OUT> [--node-dir <dir>]'); process.exit(2); }
const OUT = path.resolve(args.out);
const DIRS = [args.nodeDir, process.env.PS_NODE_DIR, path.join(OUT, 'build', 'node'), SCRIPT_DIR];
const pptxgen = loadModule('pptxgenjs', DIRS);
if (!pptxgen) {
  console.error(`нет pptxgenjs: python3 ${path.join(SKILL_DIR, 'scripts', 'check_env.py')} --install-node ${OUT}`);
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
// шрифт из токенов веба часто не установлен у зрителя PPTX — берём его, только если он из «офисного» набора
const SAFE_FONTS = ['calibri', 'arial', 'helvetica', 'helvetica neue', 'segoe ui', 'verdana', 'tahoma', 'trebuchet ms', 'georgia', 'cambria', 'aptos'];
if (!SAFE_FONTS.includes(String(T.font).toLowerCase())) T.font = 'Arial';
const FOOT = meta.footer || [meta.product, meta.copyright || meta.author].filter(Boolean).join(' · ');

// ---------------------------------------------------------------- картинки
const sizeCache = new Map();
function imageSize(buf, ext) {
  try {
    if (ext === '.png' && buf.readUInt32BE(12) === 0x49484452) return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) };
    if (ext === '.jpg' || ext === '.jpeg') {
      let i = 2;
      while (i < buf.length) {
        if (buf[i] !== 0xff) { i++; continue; }
        const m = buf[i + 1];
        const len = buf.readUInt16BE(i + 2);
        if (m >= 0xc0 && m <= 0xc3) return { w: buf.readUInt16BE(i + 7), h: buf.readUInt16BE(i + 5) };
        i += 2 + len;
      }
    }
    if (ext === '.svg') {
      const s = buf.toString('utf8', 0, Math.min(buf.length, 4000));
      const vb = s.match(/viewBox\s*=\s*["']\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)/i);
      if (vb) return { w: parseFloat(vb[1]), h: parseFloat(vb[2]) };
      const w = s.match(/\swidth\s*=\s*["']([\d.]+)/i), h = s.match(/\sheight\s*=\s*["']([\d.]+)/i);
      if (w && h) return { w: parseFloat(w[1]), h: parseFloat(h[1]) };
    }
  } catch { /* размер не определён */ }
  return { w: 16, h: 9 };
}

let browser = null; let browserTried = false; let svgAsSvg = 0;
async function rasterSvg(file) {
  if (!browserTried) {
    browserTried = true;
    const pw = loadModule('playwright', DIRS);
    if (pw) {
      try { browser = await pw.chromium.launch(); } catch (e) { console.error('Chromium не запустился, SVG пойдут как есть: ' + e.message.split('\n')[0]); }
    }
  }
  if (!browser) return null;
  const svg = fs.readFileSync(file);
  const { w, h } = imageSize(svg, '.svg');
  const scale = Math.max(1, Math.min(3, 2400 / Math.max(w, 1)));
  const page = await browser.newPage({ viewport: { width: Math.ceil(w), height: Math.ceil(h) }, deviceScaleFactor: scale });
  try {
    const html = `<!doctype html><html><head><style>html,body{margin:0;background:transparent}img{display:block;width:${w}px;height:${h}px}</style></head>`
      + `<body><img src="data:image/svg+xml;base64,${svg.toString('base64')}"></body></html>`;
    await page.setContent(html, { waitUntil: 'load' });
    const png = await page.locator('img').screenshot({ omitBackground: true });
    return { data: 'image/png;base64,' + png.toString('base64'), w, h };
  } finally { await page.close(); }
}

async function loadImage(rel) {
  if (!rel) return null;
  const file = path.resolve(OUT, rel);
  if (!fs.existsSync(file)) return null;
  if (sizeCache.has(file)) return sizeCache.get(file);
  const ext = path.extname(file).toLowerCase();
  let res;
  if (ext === '.svg') {
    res = await rasterSvg(file);
    if (!res) {
      const buf = fs.readFileSync(file);
      svgAsSvg++;
      res = { data: 'image/svg+xml;base64,' + buf.toString('base64'), ...imageSize(buf, ext) };
    }
  } else {
    const buf = fs.readFileSync(file);
    const mime = ext === '.jpg' || ext === '.jpeg' ? 'jpeg' : ext.slice(1) || 'png';
    res = { data: `image/${mime};base64,` + buf.toString('base64'), ...imageSize(buf, ext) };
  }
  sizeCache.set(file, res);
  return res;
}

function fit(img, x, y, w, h) {
  const r = Math.min(w / img.w, h / img.h);
  const iw = img.w * r, ih = img.h * r;
  return { x: x + (w - iw) / 2, y: y + (h - ih) / 2, w: iw, h: ih };
}

// ---------------------------------------------------------------- колода
const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE'; // 13.333 × 7.5 дюйма
pres.author = meta.author || '';
pres.company = meta.copyright || meta.author || '';
pres.title = meta.title || 'Стратегия';
pres.subject = meta.subtitle || '';
pres.theme = { headFontFace: T.font, bodyFontFace: T.font };
const W = 13.333, H = 7.5, M = 0.6;
const cut = (s, n) => { s = String(s ?? '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n).replace(/\s+\S*$/, '') + '…' : s; };
const footerObjs = (y) => [
  { text: { text: FOOT, options: { x: M, y, w: W - 2 * M - 1, h: 0.3, fontSize: 9, color: T.muted, fontFace: T.font, margin: 0 } } },
];
const slideNo = (y) => ({ x: W - M - 0.6, y, w: 0.6, h: 0.3, fontSize: 9, color: T.muted, fontFace: T.font, align: 'right' });
pres.defineSlideMaster({ title: 'TITLE', background: { color: T.bg }, slideNumber: slideNo(H - 0.6), objects: [
  { rect: { x: 0, y: 0, w: 0.18, h: H, fill: { color: T.accent } } },
  { placeholder: { options: { name: 'title', type: 'title', x: M, y: 2.2, w: W - 2 * M, h: 1.6, fontSize: 40, color: T.accent, fontFace: T.font, align: 'left', valign: 'bottom', margin: 0 }, text: '' } },
  { placeholder: { options: { name: 'body', type: 'body', x: M, y: 4.0, w: W - 2 * M, h: 1.4, fontSize: 18, color: T.muted, fontFace: T.font, align: 'left', valign: 'top', margin: 0 }, text: '' } },
  ...footerObjs(H - 0.6),
] });
pres.defineSlideMaster({ title: 'SECTION', background: { color: T.surface }, slideNumber: slideNo(H - 0.55), objects: [
  { rect: { x: M, y: 2.55, w: 1.2, h: 0.08, fill: { color: T.accent } } },
  { placeholder: { options: { name: 'title', type: 'title', x: M, y: 2.75, w: W - 2 * M, h: 1.3, fontSize: 34, color: T.text, fontFace: T.font, align: 'left', valign: 'top', margin: 0 }, text: '' } },
  { placeholder: { options: { name: 'body', type: 'body', x: M, y: 4.1, w: W - 2 * M, h: 1.2, fontSize: 16, color: T.muted, fontFace: T.font, align: 'left', valign: 'top', margin: 0 }, text: '' } },
  ...footerObjs(H - 0.55),
] });
pres.defineSlideMaster({ title: 'CONTENT', background: { color: T.bg }, slideNumber: slideNo(H - 0.52), objects: [
  { placeholder: { options: { name: 'title', type: 'title', x: M, y: 0.4, w: W - 2 * M, h: 0.85, fontSize: 24, color: T.accent, fontFace: T.font, align: 'left', valign: 'top', margin: 0 }, text: '' } },
  { line: { x: M, y: H - 0.62, w: W - 2 * M, h: 0, line: { color: T.border, width: 0.75 } } },
  ...footerObjs(H - 0.52),
] });

function bullets(slide, items, x, y, w, h, size = 16) {
  if (!items?.length) return;
  const arr = items.map((t, i) => ({ text: String(t), options: { bullet: { indent: 18 }, breakLine: i < items.length - 1, paraSpaceAfter: 8 } }));
  slide.addText(arr, { x, y, w, h, fontSize: size, color: T.text, fontFace: T.font, valign: 'top', margin: 0, fit: 'shrink' });
}
function caption(slide, text, x, y, w) {
  if (text) slide.addText(cut(text, 220), { x, y, w, h: 0.3, fontSize: 10, color: T.muted, fontFace: T.font, margin: 0, italic: true });
}
function notes(slide, s) {
  const parts = [s.notes || ''];
  if (s.sources?.length) parts.push('Источники:\n' + s.sources.join('\n'));
  const n = parts.filter(Boolean).join('\n\n');
  if (n) slide.addNotes(n);
}
const label = (t) => ({ text: t + ' ', options: { bold: true, color: T.accent2 } });

let currentSection = null; let sectionCount = 0;
for (const s of deck.slides || []) {
  if (s.section && s.section !== currentSection) { pres.addSection({ title: cut(s.section, 60) }); currentSection = s.section; sectionCount++; }
  const opt = currentSection ? { sectionTitle: cut(currentSection, 60) } : {};
  let slide;
  switch (s.type) {
    case 'title':
      slide = pres.addSlide({ masterName: 'TITLE', ...opt });
      slide.addText(s.title || '', { placeholder: 'title' });
      slide.addText(s.subtitle || '', { placeholder: 'body' });
      break;
    case 'section':
      slide = pres.addSlide({ masterName: 'SECTION', ...opt });
      slide.addText(s.title || '', { placeholder: 'title' });
      slide.addText(s.subtitle || '', { placeholder: 'body' });
      break;
    case 'bullets': {
      slide = pres.addSlide({ masterName: 'CONTENT', ...opt });
      slide.addText(s.title || '', { placeholder: 'title' });
      const img = await loadImage(s.image);
      bullets(slide, s.bullets, M, 1.45, img ? 6.0 : W - 2 * M, 5.1, img ? 14 : 17);
      if (img) slide.addImage({ data: img.data, ...fit(img, 6.9, 1.45, W - M - 6.9, 4.9) });
      caption(slide, s.caption, img ? 6.9 : M, 6.5, img ? W - M - 6.9 : W - 2 * M);
      break; }
    case 'image': {
      slide = pres.addSlide({ masterName: 'CONTENT', ...opt });
      slide.addText(s.title || '', { placeholder: 'title' });
      const img = await loadImage(s.image);
      if (img) slide.addImage({ data: img.data, ...fit(img, M, 1.35, W - 2 * M, 5.05) });
      else slide.addText('Картинка не найдена: ' + (s.image || '—'), { x: M, y: 3, w: W - 2 * M, h: 0.6, fontSize: 14, color: T.muted });
      caption(slide, s.caption, M, 6.5, W - 2 * M);
      break; }
    case 'stats': {
      slide = pres.addSlide({ masterName: 'CONTENT', ...opt });
      slide.addText(s.title || '', { placeholder: 'title' });
      const st = (s.stats || []).slice(0, 6); const n = Math.max(st.length, 1); const gap = 0.25;
      const tw = (W - 2 * M - gap * (n - 1)) / n;
      st.forEach((x, i) => {
        const xx = M + i * (tw + gap);
        slide.addShape(pres.ShapeType.roundRect, { x: xx, y: 1.6, w: tw, h: 2.1, fill: { color: T.surface }, line: { color: T.accent, width: 1 }, rectRadius: 0.1 });
        slide.addText(String(x.value ?? ''), { x: xx + 0.15, y: 1.75, w: tw - 0.3, h: 1.0, fontSize: n > 4 ? 30 : 38, bold: true, color: T.accent, fontFace: T.font, margin: 0, valign: 'middle' });
        slide.addText(cut(x.label, 60), { x: xx + 0.15, y: 2.8, w: tw - 0.3, h: 0.8, fontSize: 12, color: T.text, fontFace: T.font, margin: 0, valign: 'top' });
      });
      bullets(slide, s.bullets, M, 4.1, W - 2 * M, 2.3, 15);
      break; }
    case 'table': {
      slide = pres.addSlide({ masterName: 'CONTENT', ...opt });
      slide.addText(s.title || '', { placeholder: 'title' });
      const cols = s.columns || [];
      const fsz = s.fontSize || (cols.length > 7 ? 9 : 11);
      const head = cols.map((c) => ({ text: String(c), options: { bold: true, color: 'FFFFFF', fill: { color: T.accent }, fontSize: fsz } }));
      const rows = (s.rows || []).map((r, ri) => cols.map((_, ci) => ({ text: cut(r[ci], 160), options: { color: T.text, fontSize: fsz, fill: { color: ri % 2 ? T.bg : T.surface } } })));
      const colW = s.colW && s.colW.length === cols.length ? s.colW : cols.map(() => (W - 2 * M) / Math.max(cols.length, 1));
      slide.addTable([head, ...rows], { x: M, y: 1.35, w: W - 2 * M, colW, border: { type: 'solid', pt: 0.5, color: T.border }, fontFace: T.font, valign: 'top', margin: 0.04, autoPage: false });
      caption(slide, s.caption, M, 6.5, W - 2 * M);
      break; }
    case 'card': {
      slide = pres.addSlide({ masterName: 'CONTENT', ...opt });
      const c = s.card || {};
      slide.addText(cut(s.title || `#${c.rank} · ${c.id} · ${c.title}`, 110), { placeholder: 'title' });
      const tiles = (c.metrics || []).slice(0, 6); const tg = 0.18;
      const tw = (W - 2 * M - tg * (tiles.length - 1)) / Math.max(tiles.length, 1);
      tiles.forEach(([lab, val], i) => {
        const x = M + i * (tw + tg);
        slide.addShape(pres.ShapeType.roundRect, { x, y: 1.3, w: tw, h: 0.85, fill: { color: T.surface }, line: { color: T.accent, width: 0.75 }, rectRadius: 0.08 });
        slide.addText(String(val ?? '—'), { x: x + 0.1, y: 1.32, w: tw - 0.2, h: 0.5, fontSize: 20, bold: true, color: T.accent, fontFace: T.font, margin: 0, valign: 'middle' });
        slide.addText(lab, { x: x + 0.1, y: 1.8, w: tw - 0.2, h: 0.3, fontSize: 9, color: T.muted, fontFace: T.font, margin: 0 });
      });
      const metaLine = [c.category, c.segment, c.evidence_class && `класс ${c.evidence_class}`, c.priority, c.horizon, c.quadrant, c.kano && `Кано: ${c.kano}`, c.effort, c.cost, ...(c.labels || [])].filter(Boolean).join(' · ');
      slide.addText(cut(metaLine, 230), { x: M, y: 2.25, w: W - 2 * M, h: 0.35, fontSize: 10, color: T.muted, fontFace: T.font, margin: 0 });
      const mock = await loadImage(c.mockup);
      const colL = mock ? 4.5 : 6.1; const xR = M + colL + 0.3; const colR = mock ? 4.0 : W - M - xR;
      slide.addText([
        label('Что сделать:'), { text: cut(c.description, mock ? 330 : 430), options: { breakLine: true } },
        label('Почему:'), { text: cut(c.rationale, mock ? 260 : 330), options: { breakLine: true } },
        label('Сейчас:'), { text: cut(c.current_feature, 160) },
      ], { x: M, y: 2.7, w: colL, h: 3.75, fontSize: 11, color: T.text, fontFace: T.font, valign: 'top', margin: 0, paraSpaceAfter: 6, fit: 'shrink' });
      const steps = (c.steps || []).slice(0, 4).map((t, i) => ({ text: `${i + 1}. ${cut(t, 110)}`, options: { breakLine: true } }));
      slide.addText([
        { ...label('Шаги:'), options: { ...label('').options, breakLine: true } }, ...steps,
        label('KPI:'), { text: cut((c.kpi || []).join('; '), 160), options: { breakLine: true } },
        label('Дешёвая проверка:'), { text: cut(c.cheap_test, 170), options: { breakLine: true } },
        label('Риски:'), { text: cut(c.risks, 140) },
      ], { x: xR, y: 2.7, w: colR, h: 3.75, fontSize: 10.5, color: T.text, fontFace: T.font, valign: 'top', margin: 0, paraSpaceAfter: 4, fit: 'shrink' });
      if (mock) {
        const bx = xR + colR + 0.25;
        slide.addImage({ data: mock.data, ...fit(mock, bx, 2.75, W - M - bx, 3.3) });
        slide.addText('Концепт, не существующая функция', { x: bx, y: 6.1, w: W - M - bx, h: 0.3, fontSize: 8, color: T.muted, fontFace: T.font, margin: 0, italic: true });
      }
      break; }
    default:
      console.error('пропущен слайд неизвестного типа: ' + s.type);
      continue;
  }
  notes(slide, s);
}

const outFile = path.join(OUT, 'deliverables', 'strategy.pptx');
fs.mkdirSync(path.dirname(outFile), { recursive: true });
// writeFile в pptxgenjs 4 игнорирует compression для nodebuffer — пишем сами через STREAM + DEFLATE
const buf = await pres.write({ outputType: 'STREAM', compression: true });
fs.writeFileSync(outFile, buf);
if (browser) await browser.close();
const kb = Math.round(fs.statSync(outFile).size / 1024);
console.log(`PPTX: ${outFile} (${kb} КБ) — слайдов ${(deck.slides || []).length}, разделов ${sectionCount}` + (svgAsSvg ? `; SVG без растра: ${svgAsSvg}` : ''));
