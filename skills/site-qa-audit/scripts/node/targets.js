'use strict';
// Touch-target summary (G-12, WCAG 2.5.8 / 2.5.5): how many interactive elements are smaller than 24×24 and 44×44 CSS px,
// by type, in one line. Read-only: the page is opened under guard.js and nothing is clicked.
//
//   node targets.js URL [URL...] [--device pixel7 | --sizes 1440x900] [--rules rules.json] [--log blocked.jsonl]
//        [--state auth-state.json] [--locales ru-RU,en-US] [--frames main|all] [--top 10] [--out targets.json]
//
// Size of a target = its border box; for a checkbox/radio with a <label> the label box counts too (it is clickable).
// Links inside running text (a sentence around the link) are the WCAG 2.5.8 «inline» exception: counted separately,
// not in the violations. Hidden elements, zero-size elements and pointer-events:none are skipped.
// On a phone configuration the result is valid only if (pointer: coarse) is true (media.touchValid, S-4): sites switch
// to larger touch targets only for coarse pointers — a desktop window of phone width measures the wrong layout.
// Output: runs[] = { url, config, locale?, media, valid, total, lt24: {count, byType}, lt44: {count, byType}, inline,
//   smallest: [{selector, type, name, w, h}], summary }.
const path = require('path');
const { parseArgs, loadRules, writeOut, urlsFromArgs } = require('./lib');
const { listFrames } = require('./frames');
const { configsFrom, openDevice } = require('./device_context');
const { INTERACTIVE } = require('./occlusion');

function measureInFrame({ INTERACTIVE, top }) {
  const cssPath = (el) => {
    if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) return '#' + CSS.escape(el.id);
    const parts = [];
    for (let n = el; n && n.nodeType === 1 && n !== document.documentElement && parts.length < 4; n = n.parentElement) {
      let s = n.tagName.toLowerCase();
      const sib = n.parentElement ? [...n.parentElement.children].filter(c => c.tagName === n.tagName) : [];
      if (sib.length > 1) s += `:nth-of-type(${sib.indexOf(n) + 1})`;
      parts.unshift(s);
    }
    return parts.join(' > ');
  };
  const visible = (el) => {
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return false;
    }
    return true;
  };
  const typeOf = (el) => {
    const tag = el.tagName.toLowerCase(), role = el.getAttribute('role'), t = (el.getAttribute('type') || '').toLowerCase();
    if (role === 'checkbox' || role === 'radio' || role === 'switch' || (tag === 'input' && (t === 'checkbox' || t === 'radio'))) return 'checkbox';
    if (tag === 'button' || role === 'button' || (tag === 'input' && ['button', 'submit', 'reset', 'image'].includes(t)) || tag === 'summary') return 'button';
    if ((tag === 'a' && el.hasAttribute('href')) || role === 'link') return 'link';
    if (['input', 'select', 'textarea'].includes(tag) || role === 'combobox' || role === 'slider') return 'field';
    return 'other';
  };
  const label = (el) => (el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText || el.value || '').replace(/\s+/g, ' ').trim().slice(0, 50);
  // A link in running text: the nearest block has noticeably more text than the link itself.
  const inline = (el) => {
    if (typeOf(el) !== 'link' || getComputedStyle(el).display !== 'inline') return false;
    let b = el.parentElement;
    while (b && getComputedStyle(b).display === 'inline') b = b.parentElement;
    const own = (el.innerText || '').trim().length, all = b ? (b.innerText || '').trim().length : own;
    return all - own >= 20;
  };
  const els = [...document.querySelectorAll(INTERACTIVE)].filter(el => visible(el) && getComputedStyle(el).pointerEvents !== 'none' && !el.disabled);
  const rows = [];
  let inl = 0;
  for (const el of els) {
    let r = el.getBoundingClientRect();
    let w = r.width, h = r.height;
    if (!w || !h) continue;
    if (el.labels && el.labels.length) for (const l of el.labels) { const lr = l.getBoundingClientRect(); if (lr.width * lr.height > w * h) { w = lr.width; h = lr.height; } }
    if (inline(el)) { inl++; continue; }
    rows.push({ selector: cssPath(el), type: typeOf(el), name: label(el), w: Math.round(w * 10) / 10, h: Math.round(h * 10) / 10 });
  }
  return { rows, inline: inl };
}

function summarize(rows, inline) {
  const by = (lim) => { const sel = rows.filter(r => r.w < lim || r.h < lim); const byType = {}; for (const r of sel) byType[r.type] = (byType[r.type] || 0) + 1; return { count: sel.length, byType }; };
  const lt24 = by(24), lt44 = by(44);
  const fmt = (o) => Object.entries(o.byType).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${v}`).join(', ');
  const summary = `${lt24.count} из ${rows.length} меньше 24×24` + (lt24.count ? ` (${fmt(lt24)})` : '') +
    `; меньше 44×44: ${lt44.count}` + (lt44.count ? ` (${fmt(lt44)})` : '') + (inline ? `; ссылок в тексте (исключение 2.5.8): ${inline}` : '');
  return { total: rows.length, lt24, lt44, inline, summary };
}

async function measure(page, { frames = 'main', top = 10 } = {}) {
  const rows = []; let inline = 0;
  for (const f of await listFrames(page, frames)) {
    const r = await f.frame.evaluate(measureInFrame, { INTERACTIVE, top }).catch(() => null);
    if (!r) continue;
    rows.push(...r.rows.map(x => (f.depth ? { ...x, frame: f.url } : x))); inline += r.inline;
  }
  const s = summarize(rows, inline);
  s.smallest = rows.slice().sort((a, b) => a.w * a.h - b.w * b.h).slice(0, top);
  return s;
}

module.exports = { measure, summarize, measureInFrame };

if (require.main === module) {
  (async () => {
    const a = parseArgs(process.argv.slice(2), { frames: 'main', top: '10' });
    const urls = urlsFromArgs(a);
    const rules = loadRules(a.rules);
    let configs = configsFrom({ sizes: a.sizes, devices: a.device, browser: a.browser });
    if (!configs.length) configs = configsFrom({ sizes: '1440x900' });
    const state = a.state ? JSON.parse(require('fs').readFileSync(a.state, 'utf8')) : undefined;
    const locales = a.locales && a.locales !== true ? String(a.locales).split(',').map(s => s.trim()).filter(Boolean) : [null];
    const runs = [];
    for (const url of urls) for (const cfg of configs) for (const locale of locales) {
      let dev;
      try {
        dev = await openDevice({ device: cfg.name, browser: cfg.engine, storageState: state, rules, logFile: a.log, locale, readOnly: false });
        const { guardedPage } = require('./guard');
        const g = guardedPage(dev.page, rules, { logFile: a.log, throttleMs: 0 });
        const nav = await g.goto(url, { waitUntil: 'load', timeout: 45000 });
        if (!nav.performed) { runs.push({ url, config: cfg.name, locale, blocked: nav }); continue; }
        await dev.page.waitForTimeout(+(a.wait || 500));
        const m = await measure(dev.page, { frames: a.frames, top: +a.top });
        const valid = dev.media ? dev.media.touchValid !== false || !dev.media.expectsTouch : true;
        runs.push({ url, config: cfg.name, ...(locale ? { locale } : {}), viewport: dev.page.viewportSize(), media: dev.media, valid,
          ...(valid ? {} : { warning: dev.media.warning }), ...m });
      } catch (e) {
        if (e && e.exitCode === 4) throw e;
        runs.push({ url, config: cfg.name, locale, error: String(e.message || e).split('\n')[0] });
      } finally { if (dev) await dev.close().catch(() => {}); }
    }
    for (const r of runs) if (r.summary) process.stderr.write(`${r.config}${r.locale ? ' ' + r.locale : ''} ${r.url}: ${r.summary}${r.valid ? '' : ' — НЕДЕЙСТВИТЕЛЬНО: ' + r.warning}\n`);
    writeOut(a.out, { tool: 'targets', runs });
  })().catch(e => { console.error(String(e.message || e)); process.exit((e && e.exitCode) || 1); });
}
