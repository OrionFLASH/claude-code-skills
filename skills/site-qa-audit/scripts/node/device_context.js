'use strict';
// Emulated devices with (or without) the user's login (references/devices-auth.md).
//
//   node device_context.js list
//   node device_context.js state --cdp http://127.0.0.1:9222 --out <RUN_DIR>/logs/auth-state.json
//        auth: manual-cdp — read storageState of the browser the user already logged in to. Nothing is cleared,
//        nothing is navigated. The file is a secret (mode 600): never print, never commit, delete at the end.
//   node device_context.js run --devices pixel7,iphone15,ipad,360x640,pixel7-landscape --url URL
//        [--state auth-state.json | --cdp URL] [--scenario scenario.js] [--rules rules.json] [--browser chromium|webkit]
//        [--out result.json]
//        One scenario, list of devices, strictly sequential (shared login session — see references/parallelism.md).
//        scenario.js: module.exports = async ({ page, guarded, device, context }) => anyJson
//
// API: openDevice({ device, browser, cdp, storageState, rules, logFile }) -> { browser, context, page, close, device }
//      configsFrom({ sizes, devices }) -> [{ name, options, engine }]
const fs = require('fs');
const path = require('path');
const { parseArgs, loadRules, writeOut } = require('./lib');

// name -> Playwright descriptor name or explicit options. Viewports are CSS px.
const CATALOG = {
  desktop: { options: { viewport: { width: 1440, height: 900 } }, note: 'десктоп 1440×900' },
  'desktop-1280': { options: { viewport: { width: 1280, height: 720 } } },
  laptop: { options: { viewport: { width: 1024, height: 768 } } },
  low: { options: { viewport: { width: 720, height: 450 } }, note: 'низкое окно (обязательный прогон достижимости)' },
  pixel7: { descriptor: 'Pixel 7' },
  'pixel7-landscape': { descriptor: 'Pixel 7 landscape', note: 'альбомная 863×360' },
  iphone15: { descriptor: 'iPhone 15' },
  'iphone15-landscape': { descriptor: 'iPhone 15 landscape' },
  ipad: { descriptor: 'iPad (gen 7)', note: 'iPad 810×1080, WebKit' },
  'ipad-landscape': { descriptor: 'iPad (gen 7) landscape' },
  '360x640': { options: { viewport: { width: 360, height: 640 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 }, base: 'Pixel 7' },
  '640x360': { options: { viewport: { width: 640, height: 360 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 }, base: 'Pixel 7', note: 'малый телефон, landscape' },
};

function resolveDevice(name, browserOverride) {
  const pw = require('playwright');
  let options, engine = 'chromium', label = name;
  const m = /^(\d+)x(\d+)$/.exec(name);
  const entry = CATALOG[name];
  if (entry && entry.descriptor) {
    const d = pw.devices[entry.descriptor];
    const { defaultBrowserType, ...rest } = d;
    options = rest; engine = defaultBrowserType || 'chromium'; label = entry.descriptor;
  } else if (entry) {
    options = { ...entry.options };
    if (entry.base) options.userAgent = pw.devices[entry.base].userAgent;
  } else if (pw.devices[name]) {
    const { defaultBrowserType, ...rest } = pw.devices[name];
    options = rest; engine = defaultBrowserType || 'chromium';
  } else if (m) {
    options = { viewport: { width: +m[1], height: +m[2] } };
  } else {
    throw new Error(`неизвестное устройство «${name}»: ${Object.keys(CATALOG).join(', ')}, WxH или имя из playwright.devices`);
  }
  if (browserOverride) engine = browserOverride;
  if (engine === 'firefox') delete options.isMobile;  // Firefox does not support isMobile
  return { name, label, options, engine };
}

// --sizes 1280x720,720x450 and --device pixel7,iphone15 -> one list of configurations.
function configsFrom({ sizes, devices, browser } = {}) {
  const out = [];
  for (const s of String(sizes || '').split(',').map(x => x.trim()).filter(Boolean)) out.push(resolveDevice(s, browser || 'chromium'));
  for (const d of String(devices || '').split(',').map(x => x.trim()).filter(Boolean)) out.push(resolveDevice(d, browser));
  return out;
}

async function captureState(cdpUrl) {
  const { chromium } = require('playwright');
  const browser = await chromium.connectOverCDP(cdpUrl);
  try {
    const ctx = browser.contexts()[0];
    if (!ctx) throw new Error('в браузере по CDP нет контекста');
    return await ctx.storageState();
  } finally { await browser.close().catch(() => {}); }  // connectOverCDP: close() only disconnects
}

function writeState(state, out) {
  fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true });
  fs.writeFileSync(out, JSON.stringify(state), { mode: 0o600 });
  fs.chmodSync(out, 0o600);
}

// Attach to the user's browser without touching its state. Picks an existing page (by URL substring) or the last one.
async function attachCdp(cdpUrl, pageMatch) {
  const { chromium } = require('playwright');
  const browser = await chromium.connectOverCDP(cdpUrl);
  const context = browser.contexts()[0] || await browser.newContext();
  const pages = context.pages();
  let page = pageMatch ? pages.find(p => p.url().includes(pageMatch)) : pages[pages.length - 1];
  const created = !page;
  if (!page) page = await context.newPage();
  return { browser, context, page, close: async () => { if (created) await page.close().catch(() => {}); await browser.close().catch(() => {}); }, device: null };
}

async function openDevice({ device, browser: engineOverride, cdp, storageState, rules, logFile, headless = true, pageMatch } = {}) {
  if (cdp && !device) return attachCdp(cdp, pageMatch);
  const d = resolveDevice(device || 'desktop', engineOverride);
  const pw = require('playwright');
  let state = storageState;
  if (cdp) state = await captureState(cdp);  // in memory only, never written here
  const browser = await pw[d.engine].launch({ headless });
  const context = await browser.newContext({ ...d.options, ...(state ? { storageState: state } : {}) });
  if (rules) await require('./guard').guardContext(context, rules, { logFile });
  const page = await context.newPage();
  return { browser, context, page, device: d, close: () => browser.close() };
}

module.exports = { CATALOG, resolveDevice, configsFrom, captureState, writeState, attachCdp, openDevice };

if (require.main === module) {
  (async () => {
    const a = parseArgs(process.argv.slice(2));
    const cmd = a._[0];
    if (cmd === 'list') {
      const pw = require('playwright');
      const rows = Object.entries(CATALOG).map(([k, v]) => {
        const r = resolveDevice(k);
        return { name: k, engine: r.engine, viewport: `${r.options.viewport.width}x${r.options.viewport.height}`,
          mobile: !!r.options.isMobile, touch: !!r.options.hasTouch, note: v.note || v.descriptor || '' };
      });
      console.log(JSON.stringify({ devices: rows, playwrightDevices: Object.keys(pw.devices).length }, null, 2));
    } else if (cmd === 'state') {
      if (!a.cdp || !a.out) throw new Error('нужны --cdp URL и --out файл');
      const st = await captureState(a.cdp);
      writeState(st, a.out);
      // Only counts: cookie values are secrets.
      console.log(JSON.stringify({ out: path.resolve(a.out), cookies: st.cookies.length, origins: st.origins.length }));
    } else if (cmd === 'run') {
      if (!a.url || !a.devices) throw new Error('нужны --url и --devices');
      const rules = loadRules(a.rules);
      const scenario = a.scenario ? require(path.resolve(a.scenario)) : null;
      const results = [];
      let state = a.state ? JSON.parse(fs.readFileSync(a.state, 'utf8')) : undefined;
      if (a.cdp) state = await captureState(a.cdp);
      for (const name of a.devices.split(',').map(s => s.trim()).filter(Boolean)) {  // sequential on purpose
        let dev;
        try {
          dev = await openDevice({ device: name, browser: a.browser, storageState: state, rules, logFile: a.log });
          const { guardedPage } = require('./guard');
          const guarded = guardedPage(dev.page, rules, { logFile: a.log });
          const nav = await guarded.goto(a.url, { waitUntil: 'load', timeout: 45000 });
          let data;
          if (!nav.performed) data = { blocked: nav };
          else if (scenario) data = await scenario({ page: dev.page, guarded, device: dev.device, context: dev.context });
          else data = await dev.page.evaluate(() => ({ title: document.title, innerWidth, innerHeight,
            scrollWidth: document.documentElement.scrollWidth, horizontalOverflow: document.documentElement.scrollWidth > innerWidth }));
          results.push({ device: name, engine: dev.device.engine, viewport: dev.device.options.viewport, auth: state ? 'storageState' : 'guest', data });
        } catch (e) { results.push({ device: name, error: String(e.message || e).split('\n')[0] }); }
        finally { if (dev) await dev.close().catch(() => {}); }
      }
      writeOut(a.out, { tool: 'device_context', url: a.url, results });
    } else {
      console.error('команды: list | state --cdp URL --out FILE | run --devices a,b --url URL [--state f|--cdp URL] [--scenario f.js]');
      process.exit(1);
    }
  })().catch(e => { console.error(String(e.message || e)); process.exit(1); });
}
