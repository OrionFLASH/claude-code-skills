'use strict';
// Screenshot + element boxes + annotation in one call (references/screenshots.md, «shot.js»).
// CDP/Playwright counterpart of snap_mcp.js; draws with annotate.js.
//
//   node shot.js --out <RUN_DIR>/screenshots/F-001-bell.png
//        (--url URL | --cdp http://127.0.0.1:9222 [--page-match substr] [--url URL])
//        [--device pixel7 | --size 1440x813] [--setup setup.js] [--rules rules.json] [--log blocked.jsonl]
//        [--state auth-state.json] [--frames all|main] [--max-cost 100] [--no-neighbors] [--wait 500] [--locales de-DE,ar-SA]
//        [--gutter auto|on|off]   portrait shots (phone): captions in a dark field to the RIGHT of the image, never over the UI
//        "selector|подпись|kind[|row]" ...           kind: error|question|note (default error); row — обвести строку/карточку
//        "selector|@avoid"  или  "rect:x,y,w,h|@avoid" зона, которую подпись не должна закрывать
//        Селектор внутри iframe: "iframe#app >>> button.save" (координаты кадра прибавляются автоматически).
//   node shot.js --batch shots.json --dir <RUN_DIR>/screenshots [--cdp ...] [--sheet contact.png]
//        shots.json: [{ "name": "F-001-bell", "url"?, "device"?, "size"?, "setup"?, "targets": ["sel|label|kind", ...] }]
//   node shot.js sheet --out contact.png a-annotated.png b-annotated.png ... [--cols 3] [--per 9]
//
// --cdp: attaches to the user's browser and changes NOTHING (no cookie/localStorage cleanup, no navigation
// unless --url is given). With --device the login state is copied from that browser into an emulated context.
// setup.js: module.exports = async ({ page, guarded }) => { ... }   — actions go through guard.js rules.
// Automation: neighbours (visible interactive elements near the targets) are added to avoid; when overlapCost of any
// label exceeds --max-cost, other label widths are tried; the result is self-checked (label inside the image, no
// cover of other boxes, contrast >= 2 against the ring around the box). Output JSON: files, items, checks, warnings.
const fs = require('fs');
const path = require('path');
const { parseArgs, loadRules, multiArg, writeOut } = require('./lib');
const { locate, listFrames } = require('./frames');
const { openDevice, attachCdp } = require('./device_context');
const { render } = require('./annotate');
const { guardedPage } = require('./guard');
const { INTERACTIVE } = require('./occlusion');

function parseTarget(raw) {
  if (typeof raw === 'object') return raw;
  const parts = String(raw).split('|');
  const [selector, label = '', kind = 'error', flag = ''] = parts;
  return { selector: selector.trim(), label: label.trim(), kind: (kind || 'error').trim(), row: flag.trim() === 'row', avoid: label.trim() === '@avoid' };
}

async function boxOf(page, t) {
  if (t.selector.startsWith('rect:')) {
    const [x, y, w, h] = t.selector.slice(5).split(',').map(Number);
    return [x, y, w, h];
  }
  const loc = locate(page, t.selector).filter({ visible: true }).first();
  if (!(await loc.count())) return null;
  let b = await loc.boundingBox();
  if (!b) return null;
  if (t.row) {
    // Same rule as snap_mcp.js: nearest clickable container (<= 200 px high); frame offset = boundingBox delta.
    const local = await loc.evaluate((e) => {
      const r0 = e.getBoundingClientRect(); let n = e, best = null;
      while (n && n !== document.body) {
        const r = n.getBoundingClientRect(); if (r.height > 200) break;
        if (n.matches('button, a, li, [role=option], [role=button], [role=menuitem], tr')) { best = n; break; }
        if (getComputedStyle(n).cursor === 'pointer') best = n; else if (best) break;
        n = n.parentElement;
      }
      const r = (best || e).getBoundingClientRect();
      return { dx: r.x - r0.x, dy: r.y - r0.y, width: r.width, height: r.height };
    });
    b = { x: b.x + local.dx, y: b.y + local.dy, width: local.width, height: local.height };
  }
  return [b.x, b.y, b.width, b.height].map(v => Math.round(v));
}

// Visible interactive elements of all frames, in main-viewport px.
async function neighbours(page, frames) {
  const out = [];
  for (const f of await listFrames(page, frames)) {
    const boxes = await f.frame.evaluate((SEL) => {
      const vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
      return [...document.querySelectorAll(SEL)].map(e => {
        const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
        if (!r.width || !r.height || cs.visibility === 'hidden' || r.right < 0 || r.bottom < 0 || r.left > vw || r.top > vh) return null;
        return [r.left, r.top, r.width, r.height];
      }).filter(Boolean);
    }, INTERACTIVE).catch(() => []);
    for (const b of boxes) out.push([b[0] + f.offset.x, b[1] + f.offset.y, b[2], b[3]].map(Math.round));
  }
  return out;
}

const contains = (a, b) => a[0] <= b[0] + 1 && a[1] <= b[1] + 1 && a[0] + a[2] >= b[0] + b[2] - 1 && a[1] + a[3] >= b[1] + b[3] - 1;
const gap = (a, b) => Math.max(0, Math.max(a[0], b[0]) - Math.min(a[0] + a[2], b[0] + b[2])) + Math.max(0, Math.max(a[1], b[1]) - Math.min(a[1] + a[3], b[1] + b[3]));

function selfCheck(report, items, maxCost) {
  const warnings = [];
  report.forEach((r, i) => {
    const name = items[i] ? items[i].label || items[i].selector : '#' + i;
    if (r.label && !r.inside) warnings.push(`«${name}»: подпись выходит за край снимка`);
    if (r.covers > 0) warnings.push(`«${name}»: подпись закрывает ${r.covers} px² чужих рамок/avoid`);
    if (r.contrast !== null && r.contrast !== undefined && r.contrast < 2) warnings.push(`«${name}»: цвет ${r.color} слабо контрастен фону (${r.contrast}:1)`);
    if (r.overlapCost > maxCost) warnings.push(`«${name}»: overlapCost ${r.overlapCost} > ${maxCost} — подпись легла неудачно`);
  });
  return warnings;
}

const WIDTHS = [240, 180, 320, 140];

// Draw with retries: pick the variant with the lowest worst overlapCost (then fewest covers).
async function annotateBest(browser, png, spec, maxCost) {
  let best = null;
  for (const w of WIDTHS) {
    const r = await render(browser, png, { ...spec, labelWidth: w });
    const worst = Math.max(0, ...r.report.map(x => x.overlapCost || 0));
    const covers = r.report.reduce((s, x) => s + (x.covers || 0), 0);
    const score = worst + covers / 50;
    if (!best || score < best.score) best = { ...r, score, labelWidth: w, worst };
    if (worst <= maxCost && covers === 0) break;
  }
  return best;
}

async function shoot(page, opts) {
  const targets = (opts.targets || []).map(parseTarget);
  const items = [], avoid = [], missing = [];
  for (const t of targets) {
    const b = await boxOf(page, t).catch(() => null);
    if (!b) { missing.push(t.selector); continue; }
    if (t.avoid) avoid.push(b); else items.push({ box: b, label: t.label, kind: t.kind || 'error', style: t.style || 'both', selector: t.selector, ...(t.color ? { color: t.color } : {}) });
  }
  let auto = [];
  if (!opts.noNeighbors && items.length) {
    auto = (await neighbours(page, opts.frames || 'all'))
      .filter(n => !items.some(it => contains(n, it.box) || contains(it.box, n)))
      .filter(n => items.some(it => gap(n, it.box) < 260));
    avoid.push(...auto);
  }
  fs.mkdirSync(path.dirname(path.resolve(opts.out)), { recursive: true });
  await page.screenshot({ path: opts.out, scale: 'css' });
  const spec = { scale: 1, items: items.map(({ selector, ...i }) => i), avoid, viewport: page.viewportSize(), missing, gutter: opts.gutter || 'auto' };
  const base = opts.out.replace(/\.png$/i, '');
  fs.writeFileSync(base + '.spec.json', JSON.stringify(spec, null, 1));
  const res = { out: path.resolve(opts.out), spec: path.resolve(base + '.spec.json'), missing, autoAvoid: auto.length };
  if (!items.length) { res.warnings = ['нет целей для разметки'].concat(missing.length ? ['не найдены: ' + missing.join(', ')] : []); return res; }
  const { chromium } = require('playwright');
  const browser = await chromium.launch();
  try {
    const best = await annotateBest(browser, opts.out, spec, opts.maxCost);
    const annotated = base + '-annotated.png';
    fs.writeFileSync(annotated, best.buffer);
    Object.assign(res, { annotated: path.resolve(annotated), labelWidth: best.labelWidth, items: best.report, canvas: best.canvas,
      warnings: selfCheck(best.report, items, opts.maxCost).concat(missing.length ? ['не найдены: ' + missing.join(', ')] : []) });
    res.ok = res.warnings.length === 0;
  } finally { await browser.close(); }
  return res;
}

// Contact sheet: thumbnails with captions, `per` images per sheet (6–9 for one-glance review).
async function contactSheet(files, out, { cols = 3, per = 9, thumb = 460 } = {}) {
  const { chromium } = require('playwright');
  const browser = await chromium.launch();
  const outs = [];
  try {
    for (let i = 0; i < files.length; i += per) {
      const chunk = files.slice(i, i + per);
      const cells = chunk.map(f => `<figure><img src="data:image/png;base64,${fs.readFileSync(f).toString('base64')}"><figcaption>${path.basename(f).replace(/&/g, '&amp;').replace(/</g, '&lt;')}</figcaption></figure>`).join('');
      const page = await browser.newPage({ viewport: { width: cols * (thumb + 16) + 16, height: 400 } });
      await page.setContent(`<!doctype html><meta charset="utf-8"><style>body{margin:0;padding:8px;background:#1b1b1b;font:12px -apple-system,Segoe UI,Arial,sans-serif;color:#eee;display:grid;grid-template-columns:repeat(${cols},${thumb}px);gap:16px}figure{margin:0}img{width:${thumb}px;height:auto;display:block;border:1px solid #444;background:#fff}figcaption{padding:4px 0;word-break:break-all}</style>${cells}`);
      await page.waitForFunction(() => [...document.images].every(im => im.complete));
      const name = files.length > per ? out.replace(/\.png$/i, `-${i / per + 1}.png`) : out;
      await page.screenshot({ path: name, fullPage: true });
      await page.close();
      outs.push(path.resolve(name));
    }
  } finally { await browser.close(); }
  return outs;
}

async function openTarget(a, shotOpts = {}) {
  const rules = loadRules(a.rules);
  const device = shotOpts.device || a.device || shotOpts.size || a.size;
  const locale = shotOpts.locale || null;
  const dev = a.cdp && !device && !locale ? await attachCdp(a.cdp, a['page-match'])
    : await openDevice({ device: device || 'desktop', cdp: a.cdp, storageState: a.state ? JSON.parse(fs.readFileSync(a.state, 'utf8')) : undefined, rules, logFile: a.log, locale });
  const guarded = guardedPage(dev.page, rules, { logFile: a.log, throttleMs: 0 });
  const url = shotOpts.url || a.url;
  if (url) {
    const nav = await guarded.goto(url, { waitUntil: 'load', timeout: 45000 });
    if (!nav.performed) { await dev.close(); throw new Error('переход запрещён: ' + nav.reason); }
  } else if (!a.cdp) { await dev.close(); throw new Error('нужен --url или --cdp'); }
  await dev.page.waitForTimeout(+(shotOpts.wait || a.wait || 500));
  const setupFile = shotOpts.setup || a.setup;
  if (setupFile) await require(path.resolve(setupFile))({ page: dev.page, guarded });
  return dev;
}

function cli() {
  return (async () => {
    // Boolean flags get an explicit value so that a following target string is not taken as their value.
    const argv = process.argv.slice(2).flatMap(x => (x === '--no-neighbors' ? [x, 'true'] : [x]));
    const a = parseArgs(argv, { frames: 'all', 'max-cost': '100' });
    if (a._[0] === 'sheet') {
      const files = a._.slice(1);
      if (!a.out || !files.length) throw new Error('sheet --out contact.png a.png b.png ...');
      console.log(JSON.stringify({ sheets: await contactSheet(files, a.out, { cols: +(a.cols || 3), per: +(a.per || 9) }) }));
      return;
    }
    const common = { frames: a.frames, maxCost: +a['max-cost'], noNeighbors: !!a['no-neighbors'], gutter: a.gutter && a.gutter !== true ? String(a.gutter) : 'auto' };
    if (a.batch) {
      const list = JSON.parse(fs.readFileSync(a.batch, 'utf8'));
      const dir = a.dir || path.dirname(path.resolve(a.batch));
      const results = [];
      for (const s of list) {
        let dev;
        try {
          dev = await openTarget(a, s);
          results.push({ name: s.name, ...(await shoot(dev.page, { ...common, targets: s.targets, out: path.join(dir, s.name + '.png') })) });
        } catch (e) { if (e && e.exitCode === 4) throw e; results.push({ name: s.name, error: String(e.message || e).split('\n')[0] }); }
        finally { if (dev) await dev.close().catch(() => {}); }
      }
      const annotated = results.filter(r => r.annotated).map(r => r.annotated);
      const sheets = annotated.length ? await contactSheet(annotated, a.sheet || path.join(dir, 'contact-sheet.png'), { cols: +(a.cols || 3), per: +(a.per || 9) }) : [];
      writeOut(a.json, { results, sheets, warnings: results.reduce((n, r) => n + ((r.warnings || []).length) + (r.error ? 1 : 0), 0) });
      return;
    }
    if (!a.out) throw new Error('нужен --out <RUN_DIR>/screenshots/F-NNN-name.png');
    const targets = a._.concat(multiArg(argv, 'target'));
    const locales = a.locales && a.locales !== true ? String(a.locales).split(',').map(s => s.trim()).filter(Boolean) : null;
    if (locales) {
      // One shot per locale: F-001-menu-de-DE.png, F-001-menu-ar-SA.png … (G-9)
      const results = [];
      for (const locale of locales) {
        let dev;
        const out = a.out.replace(/(\.png)?$/i, `-${locale}.png`);
        try { dev = await openTarget(a, { locale }); results.push({ locale, ...(await shoot(dev.page, { ...common, targets, out })) }); }
        catch (e) { if (e && e.exitCode === 4) throw e; results.push({ locale, error: String(e.message || e).split('\n')[0] }); }
        finally { if (dev) await dev.close().catch(() => {}); }
      }
      console.log(JSON.stringify({ locales: results }, null, 1));
      return;
    }
    const dev = await openTarget(a);
    try {
      const res = await shoot(dev.page, { ...common, targets, out: a.out });
      console.log(JSON.stringify(res, null, 1));
    } finally { await dev.close().catch(() => {}); }
  })().catch(e => { console.error(String(e.message || e)); process.exit((e && e.exitCode) || 1); });
}

module.exports = { shoot, contactSheet, parseTarget, boxOf, annotateBest, selfCheck, cli };

if (require.main === module) cli();
