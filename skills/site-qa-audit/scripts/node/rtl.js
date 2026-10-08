'use strict';
// RTL detector (G-10; checklist content-i18n.md → «RTL»). Candidates for a human check, not verdicts:
//   - dir / lang of the document and the computed direction;
//   - side panels (nav, aside, fixed/sticky blocks narrower than half of the window) that stay on the LEFT in an RTL
//     page (not mirrored);
//   - blocks with RTL text and an explicit text-align: left;
//   - short Latin/number strings (user names, codes) inside RTL text without bidi isolation (<bdi>, dir=auto|ltr,
//     unicode-bidi: isolate|plaintext) that start or end with a neutral character — they render as «.Alex P»;
//   - words «left/right» («слева/справа», «يمين/يسار», «ימין/שמאל») in the text of a mirrored layout;
//   - horizontal overflow of the page.
// Read-only (guard.js, nothing is clicked).
//
//   node rtl.js URL [URL...] [--locales ar-SA,he-IL] [--device desktop|pixel7] [--rules rules.json] [--log blocked.jsonl]
//        [--out <RUN_DIR>/raw/rtl.json]
const { parseArgs, loadRules, writeOut, urlsFromArgs } = require('./lib');
const { configsFrom, openDevice } = require('./device_context');
const { guardedPage } = require('./guard');

function detectRtl() {
  const RTL_CHARS = /[֐-׿؀-ۿݐ-ݿࢠ-ࣿיִ-﷿ﹰ-﻿]/;
  const LATIN = /[A-Za-z0-9]/;
  const NEUTRAL_EDGE = /^[\s.,:;!?()[\]{}"'«»\-–—/\\@#]|[\s.,:;!?()[\]{}"'«»\-–—/\\@#]$/;
  const SIDE_WORDS = /(слева|справа|левой|правой|влево|вправо|\bleft\b|\bright\b|يمين|يسار|اليمين|اليسار|ימין|שמאל)/gi;
  const vw = document.documentElement.clientWidth;
  const path = (el) => { const p = []; for (let n = el; n && n.nodeType === 1 && p.length < 4; n = n.parentElement) { p.unshift(n.id ? '#' + n.id : n.tagName.toLowerCase()); if (n.id) break; } return p.join(' > '); };
  const vis = (e) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const docDir = document.documentElement.getAttribute('dir') || document.body.getAttribute('dir') || null;
  const computed = getComputedStyle(document.body).direction;
  const rtl = computed === 'rtl';
  // Isolation counts only on the string's own inline box and its inline ancestors (block elements are isolated by the
  // UA stylesheet anyway, which does not help a name in the middle of a sentence). A string alone in its block is fine.
  const isolated = (el, s) => {
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (!/^inline/.test(cs.display)) return ((n.innerText || '').trim() === s);
      if (n.tagName === 'BDI' || /^(auto|ltr)$/i.test(n.getAttribute('dir') || '') || /isolate|plaintext/.test(cs.unicodeBidi)) return true;
    }
    return false;
  };
  const panels = [...document.querySelectorAll('nav,aside,[role=navigation],[role=complementary],header *,body > *')].filter(e => {
    if (!vis(e)) return false;
    const cs = getComputedStyle(e), r = e.getBoundingClientRect();
    const sidey = /^(nav|aside)$/i.test(e.tagName) || /navigation|complementary/.test(e.getAttribute('role') || '') || cs.position === 'fixed' || cs.position === 'sticky';
    return sidey && r.width < vw / 2 && r.width > 20;
  }).map(e => { const r = e.getBoundingClientRect(); const side = r.left + r.width / 2 < vw / 2 ? 'left' : 'right'; return { selector: path(e), side, box: [r.left, r.top, r.width, r.height].map(Math.round) }; });
  const alignLeft = [...document.querySelectorAll('p,div,li,td,th,span,h1,h2,h3,h4,label')].filter(e => {
    if (!vis(e) || !RTL_CHARS.test(e.textContent || '')) return false;
    return getComputedStyle(e).textAlign === 'left' && e.children.length < 5;
  }).slice(0, 10).map(e => ({ selector: path(e), text: (e.innerText || '').trim().slice(0, 60) }));
  const bidi = [];
  if (rtl) {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let t = walker.nextNode(); t && bidi.length < 20; t = walker.nextNode()) {
      const s = (t.textContent || '').trim();
      const el = t.parentElement;
      if (!s || s.length > 40 || !el || !vis(el) || !LATIN.test(s) || RTL_CHARS.test(s)) continue;
      if (getComputedStyle(el).direction !== 'rtl' || isolated(el, s) || !NEUTRAL_EDGE.test(s)) continue;
      bidi.push({ selector: path(el), text: s });
    }
  }
  const text = document.body.innerText || '';
  const words = [];
  let m; while ((m = SIDE_WORDS.exec(text)) && words.length < 10) words.push(text.slice(Math.max(0, m.index - 30), m.index + m[0].length + 30).replace(/\s+/g, ' ').trim());
  return {
    lang: document.documentElement.lang || null, dir: docDir, computed, rtl,
    notMirrored: rtl ? panels.filter(p => p.side === 'left') : [], panels,
    alignLeft: rtl ? alignLeft : [], bidiNames: bidi, sideWords: rtl ? words : [],
    overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  };
}

module.exports = { detectRtl };

if (require.main === module) {
  (async () => {
    const a = parseArgs(process.argv.slice(2));
    const urls = urlsFromArgs(a);
    const rules = loadRules(a.rules);
    let configs = configsFrom({ devices: a.device, sizes: a.sizes });
    if (!configs.length) configs = configsFrom({ sizes: '1440x900' });
    const locales = a.locales && a.locales !== true ? String(a.locales).split(',').map(s => s.trim()).filter(Boolean) : [null];
    const runs = [];
    for (const url of urls) for (const cfg of configs) for (const locale of locales) {
      let dev;
      try {
        dev = await openDevice({ device: cfg.name, browser: cfg.engine, rules, logFile: a.log, locale });
        const g = guardedPage(dev.page, rules, { logFile: a.log, throttleMs: 0 });
        const nav = await g.goto(url, { waitUntil: 'load', timeout: 45000 });
        if (!nav.performed) { runs.push({ url, config: cfg.name, locale, blocked: nav }); continue; }
        await dev.page.waitForTimeout(+(a.wait || 500));
        const r = await dev.page.evaluate(detectRtl);
        r.candidates = r.notMirrored.length + r.alignLeft.length + r.bidiNames.length + r.sideWords.length + (r.rtl && r.overflowX ? 1 : 0);
        runs.push({ url, config: cfg.name, ...(locale ? { locale } : {}), ...r });
      } catch (e) {
        if (e && e.exitCode === 4) throw e;
        runs.push({ url, config: cfg.name, locale, error: String(e.message || e).split('\n')[0] });
      } finally { if (dev) await dev.close().catch(() => {}); }
    }
    writeOut(a.out, { tool: 'rtl', runs });
  })().catch(e => { console.error(String(e.message || e)); process.exit((e && e.exitCode) || 1); });
}
