'use strict';
// Frame helpers shared by detectors and shot.js (references/layout-detectors.md, «Iframe»).
//   listFrames(page, 'all'|'main') -> [{ frame, url, depth, offset: {x, y} }]  offset = frame content origin
//                                     in main-viewport CSS px (iframe position + border + padding, nested frames summed)
//   frameOffset(frame)             -> {x, y}
//   locate(page, selector)         -> Locator; "iframe#app >>> button.save" enters frames (any depth)
//   pageText(page, mode)           -> { main, frames: [{url, chars}], total } — innerText length per frame

async function frameOffset(frame) {
  let x = 0, y = 0, f = frame;
  while (f && f.parentFrame()) {
    const el = await f.frameElement();
    const r = await el.evaluate((e) => {
      const b = e.getBoundingClientRect(), cs = getComputedStyle(e);
      return { x: b.left + e.clientLeft + parseFloat(cs.paddingLeft || 0), y: b.top + e.clientTop + parseFloat(cs.paddingTop || 0) };
    });
    await el.dispose();
    x += r.x; y += r.y; f = f.parentFrame();
  }
  return { x, y };
}

function depthOf(frame) { let d = 0; for (let f = frame.parentFrame(); f; f = f.parentFrame()) d++; return d; }

async function listFrames(page, mode = 'all') {
  const frames = mode === 'all' ? page.frames() : [page.mainFrame()];
  const out = [];
  for (const frame of frames) {
    if (frame.isDetached()) continue;
    try {
      if (frame.parentFrame()) {
        const el = await frame.frameElement();
        const visible = await el.evaluate(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; });
        await el.dispose();
        if (!visible) continue;
      }
      out.push({ frame, url: frame.url(), depth: depthOf(frame), offset: await frameOffset(frame) });
    } catch { /* frame navigated away or cross-process race — skip */ }
  }
  return out;
}

// "outer iframe >>> inner iframe >>> css" -> nested frameLocator chain. Plain selectors pass through.
function locate(page, selector) {
  const parts = String(selector).split('>>>').map(s => s.trim()).filter(Boolean);
  let scope = page;
  for (const fr of parts.slice(0, -1)) scope = scope.frameLocator(fr);
  return scope.locator(parts[parts.length - 1]);
}

async function pageText(page, mode = 'all') {
  const frames = await listFrames(page, mode);
  const res = { main: 0, frames: [], total: 0 };
  for (const f of frames) {
    const chars = await f.frame.evaluate(() => (document.body ? document.body.innerText : '').length).catch(() => null);
    if (f.depth === 0) res.main = chars || 0; else res.frames.push({ url: f.url, chars });
    res.total += chars || 0;
  }
  return res;
}

module.exports = { frameOffset, listFrames, locate, pageText };
