'use strict';
// Reachability of interactive elements that lie outside the window (references/layout-detectors.md).
// For each visible interactive element whose box is not fully visible (viewport ∩ clipping ancestors):
//   1) structure: user-scrollable ancestors (overflow auto/scroll and scrollHeight > clientHeight; document unless hidden);
//   2) mouse wheel over the clipping container (repeated until the element is visible or nothing moves);
//   3) touch/mouse gesture Input.synthesizeScrollGesture (Chromium only).
// Verdict «достижим» if the wheel or the gesture brings it into view, else «недостижим».
// Scroll positions are restored after every element (scrollTop assignment, which works even for overflow:hidden).
//
//   node reachability.js URL [URL...] [--sizes 720x450,863x360] [--device pixel7-landscape,iphone15-landscape]
//        [--selector "#a" --selector "#b"] [--frames all|main] [--max 40] [--rules rules.json] [--setup setup.js]
//        [--state auth-state.json | --cdp URL] [--out reachability.json]
// Default configurations when none given: 720x450 and pixel7-landscape (low windows and landscape are mandatory).
const fs = require('fs');
const path = require('path');
const { parseArgs, loadRules, writeOut, urlsFromArgs, multiArg } = require('./lib');
const { listFrames } = require('./frames');
const { configsFrom, openDevice, captureState } = require('./device_context');
const { INTERACTIVE } = require('./occlusion');

// In-page helpers installed once per frame as window.__qaReach.
function installHelpers() {
  if (window.__qaReach) return;
  const inter = (a, b) => { const x = Math.max(a.x, b.x), y = Math.max(a.y, b.y), r = Math.min(a.x + a.w, b.x + b.w), bt = Math.min(a.y + a.h, b.y + b.h); return r > x && bt > y ? { x, y, w: r - x, h: bt - y } : null; };
  const clipsOf = (el) => {
    const out = []; let fixed = getComputedStyle(el).position === 'fixed';
    for (let n = el.parentElement; n && !fixed; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if ([cs.overflowX, cs.overflowY].some(v => v !== 'visible')) out.push(n);
      if (cs.position === 'fixed') fixed = true;
    }
    return out;
  };
  const visibleFraction = (el) => {
    const b = el.getBoundingClientRect(); const full = b.width * b.height; if (!full) return 0;
    const vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
    let r = inter({ x: b.left, y: b.top, w: b.width, h: b.height }, { x: 0, y: 0, w: vw, h: vh });
    for (const n of clipsOf(el)) {
      if (!r) break;
      if (n === document.body || n === document.documentElement) continue;
      const c = n.getBoundingClientRect();
      r = inter(r, { x: c.left + n.clientLeft, y: c.top + n.clientTop, w: n.clientWidth, h: n.clientHeight });
    }
    return r ? (r.w * r.h) / full : 0;
  };
  const scrollers = (el) => {
    const out = [];
    for (let n = el.parentElement; n; n = n.parentElement) {
      const cs = getComputedStyle(n);
      const canY = n.scrollHeight > n.clientHeight + 1, canX = n.scrollWidth > n.clientWidth + 1;
      if (!canY && !canX) continue;
      const isRoot = n === document.body || n === document.documentElement;
      out.push({ node: n, root: isRoot, overflowY: cs.overflowY, overflowX: cs.overflowX, scrollHeight: n.scrollHeight, clientHeight: n.clientHeight,
        scrollWidth: n.scrollWidth, clientWidth: n.clientWidth,
        user: isRoot ? cs.overflowY !== 'hidden' && cs.overflowY !== 'clip' : /(auto|scroll|overlay)/.test(cs.overflowY + cs.overflowX) });
    }
    return out;
  };
  const els = [];
  const describe = (el) => (el.getAttribute('aria-label') || el.innerText || el.value || el.getAttribute('title') || '').replace(/\s+/g, ' ').trim().slice(0, 60);
  const cssPath = (el) => {
    if (el.id) return '#' + CSS.escape(el.id);
    const parts = [];
    for (let n = el; n && n.nodeType === 1 && n !== document.documentElement && parts.length < 5; n = n.parentElement) {
      if (n.id) { parts.unshift('#' + CSS.escape(n.id)); break; }
      let s = n.tagName.toLowerCase(); const sib = n.parentElement ? [...n.parentElement.children].filter(c => c.tagName === n.tagName) : [];
      if (sib.length > 1) s += `:nth-of-type(${sib.indexOf(n) + 1})`; parts.unshift(s);
    }
    return parts.join(' > ');
  };
  const positions = () => {
    const all = [document.scrollingElement, ...document.querySelectorAll('*')].filter(n => n && (n.scrollTop || n.scrollLeft));
    return all.map(n => [n, n.scrollLeft, n.scrollTop]);
  };
  window.__qaReach = {
    candidates(selectors, INTERACTIVE) {
      const list = selectors && selectors.length ? selectors.flatMap(s => [...document.querySelectorAll(s)]) : [...document.querySelectorAll(INTERACTIVE)];
      const out = [];
      for (const el of list) {
        const cs = getComputedStyle(el); const b = el.getBoundingClientRect();
        if (!b.width || !b.height || cs.visibility === 'hidden' || cs.display === 'none') continue;
        let hidden = false; for (let n = el; n; n = n.parentElement) { const c = getComputedStyle(n); if (c.display === 'none' || +c.opacity === 0) { hidden = true; break; } }
        if (hidden) continue;
        const frac = visibleFraction(el);
        if (frac >= 0.9) continue;
        const vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
        const side = b.top >= vh ? 'below' : b.bottom <= 0 ? 'above' : b.left >= vw ? 'right' : b.right <= 0 ? 'left' : b.bottom > vh ? 'below' : b.right > vw ? 'right' : 'clipped';
        els.push(el);
        out.push({ idx: els.length - 1, selector: cssPath(el), name: describe(el), box: [b.left, b.top, b.width, b.height].map(Math.round), side, visible: +frac.toFixed(2),
          scrollers: scrollers(el).map(({ node, ...s }) => ({ selector: node === document.documentElement ? 'html' : node === document.body ? 'body' : cssPath(node), ...s })) });
      }
      return out;
    },
    state(idx) {
      const el = els[idx]; const b = el.getBoundingClientRect();
      // Wheel/gesture point: centre of the innermost clipping container's visible part, else the viewport centre.
      const vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
      let pt = [vw / 2, vh / 2];
      const c = clipsOf(el).find(n => n !== document.body && n !== document.documentElement);
      if (c) { const r = inter((() => { const q = c.getBoundingClientRect(); return { x: q.left, y: q.top, w: q.width, h: q.height }; })(), { x: 0, y: 0, w: vw, h: vh }); if (r) pt = [r.x + r.w / 2, r.y + r.h / 2]; }
      const sig = positions().map(p => p[1] + ',' + p[2]).join(';') + '|' + Math.round(b.top) + ',' + Math.round(b.left);
      return { visible: visibleFraction(el), top: b.top, left: b.left, bottom: b.bottom, right: b.right, vw, vh, pt, sig };
    },
    save() { window.__qaReachSaved = positions(); },
    restore() {
      for (const n of [document.scrollingElement, ...document.querySelectorAll('*')]) if (n && (n.scrollTop || n.scrollLeft)) { n.scrollTop = 0; n.scrollLeft = 0; }
      for (const [n, l, t] of window.__qaReachSaved || []) { n.scrollLeft = l; n.scrollTop = t; }
    },
  };
}

async function tryReach(frame, page, cdp, idx, offset, opts) {
  const st0 = await frame.evaluate(i => window.__qaReach.state(i), idx);
  const dirY = st0.top >= st0.vh || st0.bottom > st0.vh ? 1 : st0.bottom <= 0 || st0.top < 0 ? -1 : 0;
  const dirX = st0.left >= st0.vw || st0.right > st0.vw ? 1 : st0.right <= 0 || st0.left < 0 ? -1 : 0;
  const px = st0.pt[0] + offset.x, py = st0.pt[1] + offset.y;
  const res = { wheel: false, gesture: null };
  await frame.evaluate(() => window.__qaReach.save());
  // 1) mouse wheel
  await page.mouse.move(px, py);
  let still = 0, last = st0.sig, st = st0;
  // Step = remaining distance to the viewport (300..1500 px), like a user flicking the wheel.
  const dist = (q) => ({ y: Math.min(1500, Math.max(300, dirY > 0 ? q.bottom - q.vh : -q.top)), x: Math.min(1500, Math.max(300, dirX > 0 ? q.right - q.vw : -q.left)) });
  for (let i = 0; i < opts.steps; i++) {
    const d = dist(st);
    try { await page.mouse.wheel(dirX * d.x, dirY * d.y); } catch (e) { res.wheel = null; res.wheelError = String(e.message || e).split('\n')[0]; break; }
    await page.waitForTimeout(120);
    st = await frame.evaluate(j => window.__qaReach.state(j), idx);
    if (st.visible >= 0.9) { res.wheel = true; break; }
    if (st.sig === last) { if (++still >= 2) break; } else { still = 0; last = st.sig; }
  }
  await frame.evaluate(() => window.__qaReach.restore());
  // 2) synthesized scroll gesture (touch on touch devices) — only when the wheel did not help
  if (res.wheel === true) res.gesture = 'skipped';
  else if (cdp) {
    res.gesture = false;
    let sg = st0;
    for (let i = 0; i < 4 && !res.gesture; i++) {
      const d = dist(sg);
      try {
        await cdp.send('Input.synthesizeScrollGesture', { x: Math.round(px), y: Math.round(py), xDistance: -dirX * Math.min(d.x, 800), yDistance: -dirY * Math.min(d.y, 800),
          gestureSourceType: opts.touch ? 'touch' : 'mouse', speed: 1600 });
      } catch (e) { res.gestureError = String(e.message || e).split('\n')[0]; break; }
      await page.waitForTimeout(150);
      sg = await frame.evaluate(j => window.__qaReach.state(j), idx);
      if (sg.visible >= 0.9) res.gesture = true;
    }
    await frame.evaluate(() => window.__qaReach.restore());
  }
  return res;
}

async function check(page, { frames = 'main', selectors = [], max = 40, steps = 12, touch = false, engine = 'chromium' } = {}) {
  let cdp = null;
  if (engine === 'chromium') { try { cdp = await page.context().newCDPSession(page); } catch { cdp = null; } }
  const out = [];
  for (const f of await listFrames(page, frames)) {
    await f.frame.evaluate(installHelpers);
    const cands = await f.frame.evaluate(([s, I]) => window.__qaReach.candidates(s, I), [selectors, INTERACTIVE]);
    // Elements with the same scroll chain and side share the verdict: 2 are tested with input, the rest inherit.
    const tested = new Map();
    for (const c of cands.slice(0, max)) {
      const key = c.side + '|' + c.scrollers.map(s => s.selector + ':' + s.user).join('>');
      const prev = tested.get(key) || [];
      let r;
      if (prev.length >= 2 && prev.every(p => p.verdictKey === prev[0].verdictKey)) r = { ...prev[0].r, inferred: true };
      else { r = await tryReach(f.frame, page, cdp, c.idx, f.offset, { steps, touch }); prev.push({ r, verdictKey: String(r.wheel === true || r.gesture === true) }); tested.set(key, prev); }
      const reachable = r.wheel === true || r.gesture === true;
      const untested = r.wheel === null && r.gesture === null;
      delete c.idx;
      c.box = [c.box[0] + Math.round(f.offset.x), c.box[1] + Math.round(f.offset.y), c.box[2], c.box[3]];
      out.push({ ...c, frame: f.depth ? f.url : null, inferred: r.inferred || undefined, wheel: r.wheel, gesture: r.gesture, gestureError: r.gestureError,
        wheelError: r.wheelError, userScrollable: c.scrollers.some(s => s.user),
        verdict: reachable ? 'достижим' : untested ? 'не проверено' : 'недостижим' });
    }
    if (cands.length > max) out.push({ note: `ещё ${cands.length - max} элементов не проверено (--max ${max})`, frame: f.url });
  }
  if (cdp) await cdp.detach().catch(() => {});
  return out;
}

module.exports = { check };

if (require.main === module) {
  (async () => {
    const a = parseArgs(process.argv.slice(2), { frames: 'main', max: '40' });
    const urls = urlsFromArgs(a);
    const rules = loadRules(a.rules);
    const setup = a.setup ? require(path.resolve(a.setup)) : null;
    let configs = configsFrom({ sizes: a.sizes, devices: a.device, browser: a.browser });
    if (!configs.length) configs = configsFrom({ sizes: '720x450', devices: 'pixel7-landscape' });
    let state = a.state ? JSON.parse(fs.readFileSync(a.state, 'utf8')) : undefined;
    if (a.cdp) state = await captureState(a.cdp, rules && rules.rules.allowed_domains);
    const selectors = multiArg(process.argv.slice(2), 'selector');
    const runs = [];
    for (const cfg of configs) {
      // Mobile WebKit has neither mouse wheel nor CDP gestures: emulate the same device in Chromium.
      if (cfg.engine === 'webkit' && cfg.options.isMobile && !a.browser) { cfg.engine = 'chromium'; cfg.engineNote = 'мобильный WebKit не поддерживает колесо и жест CDP — эмуляция устройства в Chromium'; }
    }
    for (const url of urls) for (const cfg of configs) {
      let dev;
      try {
        dev = await openDevice({ device: cfg.name, browser: cfg.engine, storageState: state, rules, logFile: a.log });
        const { guardedPage } = require('./guard');
        const guarded = guardedPage(dev.page, rules, { logFile: a.log, throttleMs: 0 });
        const nav = await guarded.goto(url, { waitUntil: 'load', timeout: 45000 });
        if (!nav.performed) { runs.push({ url, config: cfg.name, blocked: nav }); continue; }
        await dev.page.waitForTimeout(+(a.wait || 500));
        if (setup) await setup({ page: dev.page, guarded });
        const items = await check(dev.page, { frames: a.frames, selectors, max: +a.max, touch: !!cfg.options.hasTouch, engine: cfg.engine });
        runs.push({ url, config: cfg.name, engine: cfg.engine, engineNote: cfg.engineNote, viewport: dev.page.viewportSize(), items,
          unreachable: items.filter(i => i.verdict === 'недостижим').length });
      } catch (e) { if (e && e.exitCode === 4) throw e; runs.push({ url, config: cfg.name, error: String(e.message || e).split('\n')[0] }); }
      finally { if (dev) await dev.close().catch(() => {}); }
    }
    writeOut(a.out, { tool: 'reachability', runs, unreachable: runs.reduce((s, r) => s + (r.unreachable || 0), 0) });
  })().catch(e => { console.error(e); process.exit((e && e.exitCode) || 1); });
}
