'use strict';
// Emulated devices with (or without) the user's login (references/devices-auth.md).
//
//   node device_context.js list
//   node device_context.js media --devices pixel7,412x915,412x915@mobile [--browser chromium]
//        pointer/hover media of each configuration (S-4): a phone must report (pointer: coarse), otherwise touch-target
//        measurements on it are invalid.
//   node device_context.js state --cdp http://127.0.0.1:9222 --out <RUN_DIR>/logs/auth-state.json
//        (--rules <RUN_DIR>/rules.json | --config <RUN_DIR>/run-config.yaml | --domains example.com,*.example.com)
//        auth: manual-cdp — read the login of the browser the user already logged in to. Nothing is cleared, nothing is
//        navigated. Only cookies of allowed_domains are kept (others are dropped and only counted); localStorage and
//        sessionStorage are read from OPEN tabs of the site's origins. The file is a secret: mode 600, written
//        atomically, never printed; delete it with `state-rm` (also done at the end of the run, step 11).
//   node device_context.js state-rm --out <RUN_DIR>/logs/auth-state.json      overwrite + delete the state file
//   node device_context.js run --devices pixel7,iphone15,ipad,360x640,pixel7-landscape --url URL
//        [--state auth-state.json [--delete-state] | --cdp URL] [--scenario scenario.js] [--rules rules.json]
//        [--browser chromium|webkit] [--locale de-DE] [--out result.json]
//        One scenario, list of devices, strictly sequential (shared login session — see references/parallelism.md).
//        scenario.js: module.exports = async ({ page, guarded, device, context }) => anyJson
//        --delete-state: the state file is deleted after the run, also when it fails.
//
// Devices: catalog names, any playwright.devices name, "WxH" (a plain DESKTOP window of that size) or "WxH@mobile"
// (phone: isMobile + hasTouch + mobile UA). Browser window: visible by default, SITE_QA_HEADLESS=1 hides it,
// SITE_QA_SLOWMO=<ms> slows visible actions down.
//
// API: openDevice({ device, browser, cdp, storageState, rules, logFile, locale }) ->
//        { browser, context, page, close, device, media }
//      configsFrom({ sizes, devices }) -> [{ name, options, engine }]
//      filterState(state, domains) -> { state, kept, dropped }
const fs = require('fs');
const path = require('path');
const { parseArgs, loadRules, writeOut, hostMatches, launchOptions, loadRunConfig, toUrl } = require('./lib');

const PIXEL7_UA = 'Pixel 7';
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
  '360x640': { options: { viewport: { width: 360, height: 640 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 }, base: PIXEL7_UA },
  '640x360': { options: { viewport: { width: 640, height: 360 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 }, base: PIXEL7_UA, note: 'малый телефон, landscape' },
};

function resolveDevice(name, browserOverride) {
  const pw = require('playwright');
  let options, engine = 'chromium', label = name;
  const m = /^(\d+)x(\d+)(@mobile)?$/.exec(name);
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
  } else if (m && m[3]) {
    // Phone of an arbitrary size: touch + mobile viewport + mobile UA, so the site's touch CSS is active.
    options = { viewport: { width: +m[1], height: +m[2] }, isMobile: true, hasTouch: true, deviceScaleFactor: 2.625,
      userAgent: pw.devices[PIXEL7_UA].userAgent };
  } else if (m) {
    options = { viewport: { width: +m[1], height: +m[2] } };
  } else {
    throw new Error(`неизвестное устройство «${name}»: ${Object.keys(CATALOG).join(', ')}, WxH, WxH@mobile или имя из playwright.devices`);
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

// ---- media features (S-4) ------------------------------------------------------------------------------
async function probeMedia(page) {
  return page.evaluate(() => ({
    pointerCoarse: matchMedia('(pointer: coarse)').matches, hoverNone: matchMedia('(hover: none)').matches,
    anyPointerCoarse: matchMedia('(any-pointer: coarse)').matches, maxTouchPoints: navigator.maxTouchPoints,
    innerWidth, webdriver: navigator.webdriver === true,
  })).catch(() => null);
}

// A touch device must report (pointer: coarse); if the engine did not, force the media features through CDP
// (Chromium) and report whether touch-target measurements are valid on this configuration.
async function ensureTouchMedia(page, context, d) {
  const expectsTouch = !!(d && d.options && d.options.hasTouch);
  let media = await probeMedia(page);
  let forced = false, session = null;
  if (expectsTouch && media && !media.pointerCoarse && d.engine === 'chromium') {
    try {
      session = await context.newCDPSession(page);
      await session.send('Emulation.setEmulatedMedia', { features: [{ name: 'pointer', value: 'coarse' }, { name: 'any-pointer', value: 'coarse' },
        { name: 'hover', value: 'none' }, { name: 'any-hover', value: 'none' }] });
      forced = true;
      media = await probeMedia(page);
    } catch { /* not available: reported below */ }
  }
  const narrow = media && media.innerWidth && media.innerWidth < 600;
  const touchValid = expectsTouch ? !!(media && media.pointerCoarse) : !narrow;
  const warning = expectsTouch && !touchValid ? 'pointer:coarse = false на телефоне — измерения целей нажатия НЕДЕЙСТВИТЕЛЬНЫ'
    : !expectsTouch && narrow ? `узкое окно ${media.innerWidth} px без касаний (десктоп): для телефона используйте pixel7 или WxH@mobile`
      : null;
  return { ...(media || {}), expectsTouch, forced, touchValid, ...(warning ? { warning } : {}), _session: session };
}

// ---- login state (S-3) ---------------------------------------------------------------------------------
function domainList(a) {
  if (a.domains && a.domains !== true) return String(a.domains).split(',').map(s => s.trim()).filter(Boolean);
  if (a.rules) return (loadRules(a.rules).rules.allowed_domains || []);
  if (a.config) return ((loadRunConfig(a.config).site || {}).allowed_domains || []);
  return [];
}

function cookieAllowed(c, patterns) {
  const raw = String(c.domain || '').toLowerCase();
  const d = raw.replace(/^\./, '');
  return patterns.some(p => {
    p = String(p).toLowerCase();
    if (hostMatches(d, p)) return true;
    // A parent-domain cookie (".example.com") is sent to an allowed subdomain (app.example.com): keep it.
    const base = p.startsWith('*.') ? p.slice(2) : p;
    return raw.startsWith('.') && d.includes('.') && (base === d || base.endsWith('.' + d));
  });
}

function originAllowed(origin, patterns) {
  try { const h = new URL(origin).hostname; return patterns.some(p => hostMatches(h, p)); } catch { return false; }
}

function filterState(state, domains) {
  const cookies = (state.cookies || []).filter(c => cookieAllowed(c, domains));
  const origins = (state.origins || []).filter(o => originAllowed(o.origin, domains));
  const sessionStorage = (state.sessionStorage || []).filter(o => originAllowed(o.origin, domains));
  return { state: { cookies, origins, ...(sessionStorage.length ? { sessionStorage } : {}) },
    kept: cookies.length, dropped: (state.cookies || []).length - cookies.length };
}

// localStorage / sessionStorage of the OPEN tabs of the site (connectOverCDP storageState() has no origins).
async function storageOfOpenTabs(ctx, domains) {
  const local = new Map(), session = new Map();
  for (const p of ctx.pages()) {
    let origin;
    try { origin = new URL(p.url()).origin; } catch { continue; }
    if (!/^https?:/.test(origin) || !originAllowed(origin, domains)) continue;
    const s = await p.evaluate(() => {
      const dump = (st) => { const out = []; for (let i = 0; i < st.length; i++) { const k = st.key(i); out.push({ name: k, value: st.getItem(k) }); } return out; };
      return { local: dump(localStorage), session: dump(sessionStorage) };
    }).catch(() => null);
    if (!s) continue;
    if (!local.has(origin)) local.set(origin, s.local);
    if (!session.has(origin) && s.session.length) session.set(origin, s.session);
  }
  return { origins: [...local].map(([origin, localStorage]) => ({ origin, localStorage })),
    sessionStorage: [...session].map(([origin, items]) => ({ origin, items })) };
}

// -> { state, kept, dropped }. Without domains the state is not filtered (in-memory use only, never written).
async function captureStateReport(cdpUrl, domains) {
  const { chromium } = require('playwright');
  const browser = await chromium.connectOverCDP(cdpUrl);
  try {
    const ctx = browser.contexts()[0];
    if (!ctx) throw new Error('в браузере по CDP нет контекста');
    const st = await ctx.storageState();
    if (!domains || !domains.length) return { state: st, kept: st.cookies.length, dropped: 0 };
    const tabs = await storageOfOpenTabs(ctx, domains);
    const merged = { cookies: st.cookies, origins: tabs.origins.length ? tabs.origins : st.origins, sessionStorage: tabs.sessionStorage };
    return filterState(merged, domains);
  } finally { await browser.close().catch(() => {}); }  // connectOverCDP: close() only disconnects
}

const captureState = async (cdpUrl, domains) => (await captureStateReport(cdpUrl, domains)).state;

// Atomic write with mode 600: a failure never leaves a partial secret behind.
function writeState(state, out) {
  fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true });
  const tmp = `${out}.tmp-${process.pid}`;
  try {
    fs.writeFileSync(tmp, JSON.stringify(state), { mode: 0o600 });
    fs.chmodSync(tmp, 0o600);
    fs.renameSync(tmp, out);
    fs.chmodSync(out, 0o600);
  } catch (e) { try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ } throw e; }
}

// Overwrite and delete the state file (and stray temp files next to it).
function removeState(file) {
  let removed = false;
  const dir = path.dirname(path.resolve(file)), base = path.basename(file);
  const victims = [path.resolve(file)];
  try { for (const f of fs.readdirSync(dir)) if (f.startsWith(base + '.tmp-')) victims.push(path.join(dir, f)); } catch { /* no dir */ }
  for (const f of victims) {
    try {
      const size = fs.statSync(f).size;
      fs.writeFileSync(f, Buffer.alloc(size));
      fs.rmSync(f, { force: true });
      removed = true;
    } catch { /* missing */ }
  }
  return removed;
}

function storageForContext(state) {
  if (!state) return { storageState: undefined, sessionStorage: [] };
  const { sessionStorage = [], ...rest } = state;
  return { storageState: rest, sessionStorage };
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
  return { browser, context, page, close: async () => { if (created) await page.close().catch(() => {}); await browser.close().catch(() => {}); }, device: null, media: null };
}

async function openDevice({ device, browser: engineOverride, cdp, storageState, rules, logFile, headless, pageMatch, locale, readOnly } = {}) {
  if (cdp && !device) return attachCdp(cdp, pageMatch);
  const d = resolveDevice(device || 'desktop', engineOverride);
  const pw = require('playwright');
  let state = storageState;
  if (cdp) state = await captureState(cdp, rules ? rules.rules.allowed_domains : null);  // in memory only
  const { storageState: st, sessionStorage } = storageForContext(state);
  const browser = await pw[d.engine].launch(launchOptions(headless === undefined ? {} : { headless }));
  const ctxOpts = { ...d.options, ...(st ? { storageState: st } : {}),
    ...(locale ? { locale, extraHTTPHeaders: { 'Accept-Language': locale } } : {}) };
  const context = await browser.newContext(ctxOpts);
  if (sessionStorage.length) {
    await context.addInitScript((list) => {
      const hit = list.find(o => o.origin === location.origin);
      if (hit) for (const { name, value } of hit.items) if (sessionStorage.getItem(name) === null) sessionStorage.setItem(name, value);
    }, sessionStorage);
  }
  if (rules) await require('./guard').guardContext(context, rules, { logFile, readOnly });
  const page = await context.newPage();
  const media = await ensureTouchMedia(page, context, d);
  const { _session, ...mediaOut } = media;
  return { browser, context, page, device: d, media: mediaOut, _session, close: () => browser.close() };
}

module.exports = { CATALOG, resolveDevice, configsFrom, captureState, captureStateReport, writeState, removeState, filterState, cookieAllowed,
  attachCdp, openDevice, probeMedia, ensureTouchMedia };

if (require.main === module) {
  (async () => {
    const a = parseArgs(process.argv.slice(2));
    a.url = toUrl(a.url);
    const cmd = a._[0];
    if (cmd === 'list') {
      const pw = require('playwright');
      const rows = Object.entries(CATALOG).map(([k, v]) => {
        const r = resolveDevice(k);
        return { name: k, engine: r.engine, viewport: `${r.options.viewport.width}x${r.options.viewport.height}`,
          mobile: !!r.options.isMobile, touch: !!r.options.hasTouch, note: v.note || v.descriptor || '' };
      });
      console.log(JSON.stringify({ devices: rows, also: ['WxH (десктоп)', 'WxH@mobile (телефон: касания, мобильный UA)'], playwrightDevices: Object.keys(pw.devices).length }, null, 2));
    } else if (cmd === 'media') {
      if (!a.devices) throw new Error('нужен --devices');
      const rows = [];
      for (const name of a.devices.split(',').map(s => s.trim()).filter(Boolean)) {
        let dev;
        try { dev = await openDevice({ device: name, browser: a.browser, headless: true }); rows.push({ device: name, engine: dev.device.engine, ...dev.media }); }
        catch (e) { rows.push({ device: name, error: String(e.message || e).split('\n')[0] }); }
        finally { if (dev) await dev.close().catch(() => {}); }
      }
      console.log(JSON.stringify({ media: rows }, null, 2));
    } else if (cmd === 'state') {
      if (!a.cdp || !a.out) throw new Error('нужны --cdp URL и --out файл');
      const domains = domainList(a);
      if (!domains.length) throw new Error('нужен фильтр доменов: --rules rules.json, --config run-config.yaml или --domains example.com,*.example.com — без него выгружались бы cookie всех сайтов браузера');
      const res = await captureStateReport(a.cdp, domains);
      writeState(res.state, a.out);
      const kept = [...new Set(res.state.cookies.map(c => String(c.domain).replace(/^\./, '')))].sort();
      const warnings = [];
      if (!res.state.origins.length) warnings.push('localStorage не выгружен: нет открытой вкладки сайта в браузере пользователя — откройте её и повторите');
      process.stderr.write('ВНИМАНИЕ: файл состояния входа — секрет (права 600). Не печатать, не прикладывать к issues и заданиям; ' +
        `удалить после прогона: node device_context.js state-rm --out ${a.out}\n`);
      // Only counts and kept cookie domains: cookie values are secrets, foreign domains are not listed.
      console.log(JSON.stringify({ out: path.resolve(a.out), mode: '600', cookies: res.kept, dropped: res.dropped, domains: kept,
        origins: res.state.origins.length, sessionStorage: (res.state.sessionStorage || []).length, warnings }));
    } else if (cmd === 'state-rm') {
      if (!a.out) throw new Error('нужен --out файл состояния');
      console.log(JSON.stringify({ out: path.resolve(a.out), removed: removeState(a.out) }));
    } else if (cmd === 'run') {
      if (!a.url || !a.devices) throw new Error('нужны --url и --devices');
      const cleanup = () => { if (a.state && a['delete-state']) removeState(a.state); };
      process.once('SIGINT', () => { cleanup(); process.exit(130); });
      process.once('SIGTERM', () => { cleanup(); process.exit(143); });
      const results = [];
      try {
        const rules = loadRules(a.rules);
        const scenario = a.scenario ? require(path.resolve(a.scenario)) : null;
        let state = a.state ? JSON.parse(fs.readFileSync(a.state, 'utf8')) : undefined;
        if (a.cdp) state = await captureState(a.cdp, rules ? rules.rules.allowed_domains : null);
        for (const name of a.devices.split(',').map(s => s.trim()).filter(Boolean)) {  // sequential on purpose
          let dev;
          try {
            dev = await openDevice({ device: name, browser: a.browser, storageState: state, rules, logFile: a.log, locale: a.locale });
            const { guardedPage } = require('./guard');
            const guarded = guardedPage(dev.page, rules, { logFile: a.log });
            const nav = await guarded.goto(a.url, { waitUntil: 'load', timeout: 45000 });
            let data;
            if (!nav.performed) data = { blocked: nav };
            else if (scenario) data = await scenario({ page: dev.page, guarded, device: dev.device, context: dev.context });
            else data = await dev.page.evaluate(() => ({ title: document.title, innerWidth, innerHeight,
              scrollWidth: document.documentElement.scrollWidth, horizontalOverflow: document.documentElement.scrollWidth > innerWidth }));
            results.push({ device: name, engine: dev.device.engine, viewport: dev.device.options.viewport, auth: state ? 'storageState' : 'guest', media: dev.media, data });
          } catch (e) {
            if (e && e.exitCode === 4) throw e;  // guard unavailable: stop the whole run
            results.push({ device: name, error: String(e.message || e).split('\n')[0] });
          } finally { if (dev) await dev.close().catch(() => {}); }
        }
      } finally { cleanup(); }
      writeOut(a.out, { tool: 'device_context', url: a.url, results, ...(a['delete-state'] ? { stateDeleted: true } : {}) });
    } else {
      console.error('команды: list | media --devices a,b | state --cdp URL --out FILE (--rules|--config|--domains) | state-rm --out FILE | ' +
        'run --devices a,b --url URL [--state f [--delete-state]|--cdp URL] [--scenario f.js]');
      process.exit(1);
    }
  })().catch(e => { console.error(String(e.message || e)); process.exit((e && e.exitCode) || 1); });
}
