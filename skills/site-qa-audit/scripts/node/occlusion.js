'use strict';
// Deterministic occlusion detector (references/layout-detectors.md).
// For every visible interactive element: document.elementFromPoint at 5 points of its VISIBLE part
// (viewport ∩ clipping ancestors). If the top element is neither the element nor its ancestor/descendant
// (nor its <label>), the pair «закрыт / закрывает» is recorded with the covered area and z-index.
// Elements covered only by a fixed/sticky panel that a user scroll would move away are "transient", not defects.
// Iframes (--frames all): elements are tested inside the frame and against the parent document.
// Filters against false positives (G-11): the tested element must be visible (not display:none / visibility:hidden /
// opacity:0, non-zero visible part) and accept clicks (pointer-events is not none); a pair is reported only if the
// covered area is at least --min-area px² (default 16). An invisible occluder (opacity 0) is kept — it still eats
// clicks — but marked occluderInvisible. Counts of filtered elements/pairs: runs[].filtered.
//
//   node occlusion.js URL [URL...] [--sizes 1280x720,1024x768,768x1024,720x450] [--device pixel7,iphone15]
//        [--frames all|main] [--rules rules.json] [--setup setup.js] [--state auth-state.json | --cdp URL]
//        [--min-area 16] [--locales ru-RU,ar-SA] [--log blocked.jsonl] [--out occlusion.json]
// Exit code 0 (4 — guard unavailable); result JSON: runs[].pairs[] = { occluded, occluder, area: {w, h, px}, points, transient? }.
const path = require('path');
const { parseArgs, loadRules, writeOut, urlsFromArgs } = require('./lib');
const { listFrames } = require('./frames');
const { configsFrom, openDevice, captureState, attachCdp } = require('./device_context');

const INTERACTIVE = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=checkbox],' +
  '[role=radio],[role=switch],[role=tab],[role=menuitem],[role=option],[role=slider],[role=combobox],[tabindex]:not([tabindex="-1"]),[onclick]';

// Runs inside one frame. Returns pairs found in this frame + the list of clean points for the parent-document check.
function detectInFrame({ INTERACTIVE, minArea = 0 }) {
  const vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
  const inter = (a, b) => { const x = Math.max(a.x, b.x), y = Math.max(a.y, b.y), r = Math.min(a.x + a.w, b.x + b.w), btm = Math.min(a.y + a.h, b.y + b.h); return r > x && btm > y ? { x, y, w: r - x, h: btm - y } : null; };
  const R = (r) => ({ x: r.left, y: r.top, w: r.width, h: r.height });
  const cssPath = (el) => {
    if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) return '#' + CSS.escape(el.id);
    const parts = [];
    for (let n = el; n && n.nodeType === 1 && n !== document.documentElement && parts.length < 5; n = n.parentElement) {
      if (n.id && document.querySelectorAll('#' + CSS.escape(n.id)).length === 1) { parts.unshift('#' + CSS.escape(n.id)); break; }
      let s = n.tagName.toLowerCase();
      const sib = n.parentElement ? [...n.parentElement.children].filter(c => c.tagName === n.tagName) : [];
      if (sib.length > 1) s += `:nth-of-type(${sib.indexOf(n) + 1})`;
      parts.unshift(s);
    }
    return parts.join(' > ');
  };
  const label = (el) => (el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText || el.value || el.getAttribute('alt') || '').replace(/\s+/g, ' ').trim().slice(0, 60);
  const styleVisible = (el) => {
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden' || cs.visibility === 'collapse' || +cs.opacity === 0) return false;
    }
    return true;
  };
  const clips = (cs) => [cs.overflowX, cs.overflowY].some(v => v !== 'visible');
  // Visible part of el: viewport ∩ padding boxes of clipping ancestors (stops at position:fixed).
  const visibleRect = (el) => {
    let r = inter(R(el.getBoundingClientRect()), { x: 0, y: 0, w: vw, h: vh });
    let fixed = getComputedStyle(el).position === 'fixed';
    for (let n = el.parentElement; r && n && n !== document.documentElement && !fixed; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (n !== document.body && clips(cs)) {
        const b = n.getBoundingClientRect();
        r = inter(r, { x: b.left + n.clientLeft, y: b.top + n.clientTop, w: n.clientWidth, h: n.clientHeight });
      }
      if (cs.position === 'fixed') fixed = true;
    }
    return r && r.w >= 1 && r.h >= 1 ? r : null;
  };
  const points = (r) => {
    // 25% inset keeps corner points inside rounded (border-radius: 50%) controls.
    const ix = Math.max(1, r.w / 4), iy = Math.max(1, r.h / 4);
    return [[r.x + r.w / 2, r.y + r.h / 2], [r.x + ix, r.y + iy], [r.x + r.w - 1 - ix, r.y + iy], [r.x + ix, r.y + r.h - 1 - iy], [r.x + r.w - 1 - ix, r.y + r.h - 1 - iy]];
  };
  const related = (el, top) => top === el || el.contains(top) || top.contains(el) ||
    (el.labels && [...el.labels].some(l => l === top || l.contains(top))) || (top.closest('label') && top.closest('label').control === el);
  const occluderRoot = (top) => top.closest(INTERACTIVE) || (() => {
    for (let n = top; n && n !== document.body; n = n.parentElement) if (getComputedStyle(n).position !== 'static') return n;
    return top;
  })();
  const zInfo = (el) => {
    let z = 'auto', pos = 'static';
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (pos === 'static' && cs.position !== 'static') pos = cs.position;
      if (cs.zIndex !== 'auto') { z = cs.zIndex; if (pos !== 'static') break; }
    }
    return { zIndex: z === 'auto' ? z : +z, position: pos };
  };
  const pinned = (el) => { for (let n = el; n && n !== document.documentElement; n = n.parentElement) { const p = getComputedStyle(n).position; if (p === 'fixed' || p === 'sticky') return true; } return false; };
  // User-scrollable ancestors, inner to outer (overflow auto/scroll with overflow; the document unless hidden).
  const userScrollers = (el) => {
    const out = [];
    for (let n = el.parentElement; n; n = n.parentElement) {
      if (n === document.body || n === document.documentElement) break;
      const cs = getComputedStyle(n);
      if ((/(auto|scroll)/.test(cs.overflowY) && n.scrollHeight > n.clientHeight) || (/(auto|scroll)/.test(cs.overflowX) && n.scrollWidth > n.clientWidth)) out.push(n);
    }
    const se = document.scrollingElement, cs = getComputedStyle(document.documentElement), bs = getComputedStyle(document.body);
    if (se && se.scrollHeight > se.clientHeight && cs.overflowY !== 'hidden' && bs.overflowY !== 'hidden') out.push(se);
    return out;
  };
  const test = (el) => {
    const r = visibleRect(el);
    if (!r) return null;
    const hits = new Map(); const clean = [];
    for (const [x, y] of points(r)) {
      const top = document.elementFromPoint(x, y);
      if (!top) continue;
      if (related(el, top)) { clean.push([x, y]); continue; }
      const occ = occluderRoot(top);
      if (related(el, occ)) { clean.push([x, y]); continue; }
      hits.set(occ, (hits.get(occ) || 0) + 1);
    }
    return { r, hits, clean };
  };

  const pairs = []; const cleanPoints = []; let checked = 0, transient = 0;
  const filtered = { inert: 0, small: 0 };
  const invisible = (n) => { for (; n && n.nodeType === 1; n = n.parentElement) { const cs = getComputedStyle(n); if (+cs.opacity === 0 || cs.visibility === 'hidden') return true; } return false; };
  const els = [...document.querySelectorAll(INTERACTIVE)].filter(styleVisible);
  for (const el of els) {
    if (getComputedStyle(el).pointerEvents === 'none') { filtered.inert++; continue; }  // not clickable anyway
    const t = test(el);
    if (!t) continue;
    checked++;
    if (t.clean.length) cleanPoints.push({ path: cssPath(el), name: label(el), box: t.r, points: t.clean });
    for (const [occ, n] of t.hits) {
      // Transient: covered by a pinned panel, but a user scroll moves the element out from under it.
      if (pinned(occ) && !pinned(el)) {
        const scs = userScrollers(el);
        if (scs.length) {
          const prev = scs.map(sc => [sc.scrollLeft, sc.scrollTop]);
          for (const sc of scs) {  // center the element in each scroller, inner to outer (what a user scroll does)
            const er = el.getBoundingClientRect();
            const area = sc === document.scrollingElement ? { top: 0, h: vh } : (() => { const b = sc.getBoundingClientRect(); return { top: b.top + sc.clientTop, h: sc.clientHeight }; })();
            sc.scrollTo({ top: sc.scrollTop + (er.top + er.height / 2) - (area.top + area.h / 2), behavior: 'instant' });
          }
          const again = test(el);
          scs.forEach((sc, i) => sc.scrollTo({ left: prev[i][0], top: prev[i][1], behavior: 'instant' }));
          if (again && !again.hits.has(occ)) { transient++; continue; }
        }
      }
      const ob = occ.getBoundingClientRect();
      const ov = inter(t.r, inter(R(ob), { x: 0, y: 0, w: vw, h: vh }) || { x: 0, y: 0, w: 0, h: 0 }) || { x: 0, y: 0, w: 0, h: 0 };
      const zi = zInfo(occ), ze = zInfo(el);
      const px = Math.round(ov.w * ov.h);
      if (px < minArea) { filtered.small++; continue; }
      pairs.push({
        occluded: { selector: cssPath(el), tag: el.tagName.toLowerCase(), name: label(el), box: [t.r.x, t.r.y, t.r.w, t.r.h].map(Math.round), zIndex: ze.zIndex },
        occluder: { selector: cssPath(occ), tag: occ.tagName.toLowerCase(), name: label(occ), box: [ob.left, ob.top, ob.width, ob.height].map(Math.round), zIndex: zi.zIndex, position: zi.position,
          ...(invisible(occ) ? { invisible: true } : {}) },
        area: { x: Math.round(ov.x), y: Math.round(ov.y), w: Math.round(ov.w), h: Math.round(ov.h), px },
        points: n,
        ...(invisible(occ) ? { occluderInvisible: true } : {}),
      });
    }
  }
  return { pairs, cleanPoints, checked, transient, filtered, viewport: [vw, vh] };
}

// Points that are clean inside a frame must hit the <iframe> element in the parent document.
function parentCheck(iframeEl, { pts, INTERACTIVE }) {
  const out = [];
  const label = (el) => (el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60);
  for (const p of pts) {
    const occ = new Map();
    for (const [x, y] of p.points) {
      const top = document.elementFromPoint(x, y);
      if (!top || top === iframeEl || iframeEl.contains(top) || top.contains(iframeEl)) continue;
      const root = top.closest(INTERACTIVE) || top;
      occ.set(root, (occ.get(root) || 0) + 1);
    }
    for (const [o, n] of occ) {
      const b = o.getBoundingClientRect(), cs = getComputedStyle(o);
      out.push({ idx: p.idx, occluder: { selector: o.id ? '#' + o.id : o.tagName.toLowerCase() + (o.className && typeof o.className === 'string' ? '.' + o.className.trim().split(/\s+/).join('.') : ''),
        tag: o.tagName.toLowerCase(), name: label(o), box: [b.left, b.top, b.width, b.height].map(Math.round), zIndex: cs.zIndex === 'auto' ? 'auto' : +cs.zIndex, position: cs.position }, points: n });
    }
  }
  return out;
}

const shift = (box, o) => [box[0] + Math.round(o.x), box[1] + Math.round(o.y), box[2], box[3]];

async function detect(page, { frames = 'main', minArea = 16 } = {}) {
  const list = await listFrames(page, frames);
  const res = { pairs: [], checked: 0, transient: 0, filtered: { inert: 0, small: 0 }, frames: [] };
  for (const f of list) {
    let r;
    try { r = await f.frame.evaluate(detectInFrame, { INTERACTIVE, minArea }); } catch (e) { res.frames.push({ url: f.url, error: String(e.message || e).split('\n')[0] }); continue; }
    res.checked += r.checked; res.transient += r.transient;
    res.filtered.inert += r.filtered.inert; res.filtered.small += r.filtered.small;
    res.frames.push({ url: f.url, depth: f.depth, offset: f.offset, checked: r.checked });
    for (const p of r.pairs) {
      p.frame = f.depth ? f.url : null;
      p.occluded.box = shift(p.occluded.box, f.offset); p.occluder.box = shift(p.occluder.box, f.offset);
      p.area.x += Math.round(f.offset.x); p.area.y += Math.round(f.offset.y);
      res.pairs.push(p);
    }
    // Parent-document check for frame content (one level up is enough per spec; repeated per nesting level).
    if (f.depth && r.cleanPoints.length) {
      const parent = f.frame.parentFrame();
      const pOff = list.find(x => x.frame === parent);
      const el = await f.frame.frameElement();
      const local = { x: f.offset.x - (pOff ? pOff.offset.x : 0), y: f.offset.y - (pOff ? pOff.offset.y : 0) };
      const pts = r.cleanPoints.map((c, idx) => ({ idx, points: c.points.map(([x, y]) => [x + local.x, y + local.y]) }));
      const hits = await el.evaluate(parentCheck, { pts, INTERACTIVE }).catch(() => []);
      await el.dispose();
      for (const h of hits) {
        const c = r.cleanPoints[h.idx];
        const ob = shift(h.occluder.box, pOff ? pOff.offset : { x: 0, y: 0 });
        const cb = shift(c.box.x !== undefined ? [c.box.x, c.box.y, c.box.w, c.box.h].map(Math.round) : c.box, f.offset);
        const x = Math.max(cb[0], ob[0]), y = Math.max(cb[1], ob[1]);
        const w = Math.max(0, Math.min(cb[0] + cb[2], ob[0] + ob[2]) - x), hh = Math.max(0, Math.min(cb[1] + cb[3], ob[1] + ob[3]) - y);
        if (w * hh < minArea) { res.filtered.small++; continue; }
        res.pairs.push({ frame: f.url, crossFrame: true, occluded: { selector: c.path, name: c.name, box: cb },
          occluder: { ...h.occluder, box: ob }, area: { x, y, w, h: hh, px: w * hh }, points: h.points });
      }
    }
  }
  return res;
}

module.exports = { detect, detectInFrame, INTERACTIVE };

if (require.main === module) {
  (async () => {
    const a = parseArgs(process.argv.slice(2), { frames: 'main', 'min-area': '16' });
    const urls = a.cdp && !a._.length && !a.url ? [null] : urlsFromArgs(a);
    const rules = loadRules(a.rules);
    const setup = a.setup ? require(path.resolve(a.setup)) : null;
    let configs = configsFrom({ sizes: a.sizes, devices: a.device, browser: a.browser });
    let state = a.state ? JSON.parse(require('fs').readFileSync(a.state, 'utf8')) : undefined;
    if (a.cdp && configs.length) state = await captureState(a.cdp, rules && rules.rules.allowed_domains);
    if (!configs.length && !a.cdp) configs = configsFrom({ sizes: '1440x900' });
    const locales = a.locales && a.locales !== true ? String(a.locales).split(',').map(s => s.trim()).filter(Boolean) : [null];
    const runs = [];
    const targets = configs.length ? configs : [null];  // null = the user's CDP page as is
    for (const url of urls) for (const cfg of targets) for (const locale of (cfg ? locales : [null])) {
      let dev;
      try {
        dev = cfg ? await openDevice({ device: cfg.name, browser: cfg.engine, storageState: state, rules, logFile: a.log, locale }) : await attachCdp(a.cdp, a['page-match']);
        const { guardedPage } = require('./guard');
        const guarded = guardedPage(dev.page, rules, { logFile: a.log, throttleMs: 0 });
        if (url) { const nav = await guarded.goto(url, { waitUntil: 'load', timeout: 45000 }); if (!nav.performed) { runs.push({ url, config: cfg && cfg.name, locale, blocked: nav }); continue; } }
        await dev.page.waitForTimeout(+(a.wait || 500));
        if (setup) await setup({ page: dev.page, guarded });
        const r = await detect(dev.page, { frames: a.frames, minArea: +a['min-area'] });
        runs.push({ url: url || dev.page.url(), config: cfg ? cfg.name : 'cdp', engine: cfg ? cfg.engine : 'chromium',
          ...(locale ? { locale } : {}), viewport: dev.page.viewportSize(), ...(dev.media ? { media: dev.media } : {}), ...r });
      } catch (e) {
        if (e && e.exitCode === 4) throw e;  // guard unavailable: stop
        runs.push({ url, config: cfg && cfg.name, locale, error: String(e.message || e).split('\n')[0] });
      } finally { if (dev) await dev.close().catch(() => {}); }
    }
    writeOut(a.out, { tool: 'occlusion', frames: a.frames, minArea: +a['min-area'], runs, total: runs.reduce((s, r) => s + ((r.pairs || []).length), 0) });
  })().catch(e => { console.error(e); process.exit((e && e.exitCode) || 1); });
}
