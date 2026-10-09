'use strict';
// Legally relevant UI elements seen by a FIRST-TIME GUEST (G-1, G-9; checklist references/checklists/legal-ui.md).
// A fresh, empty context per locale (no cookies, no storage): what is stored right after the load and N ms later
// WITHOUT any interaction, which third-party hosts are contacted, whether a cookie/consent banner is shown and what its
// buttons say, links to the documents (privacy, terms, offer, cookies, imprint), operator details, age marks.
// Read-only: nothing is clicked; navigation is under guard.js. Facts only — no legal conclusions (legal-ui.md).
//
//   node legal_guest.js URL [URL...] --rules rules.json [--locales ru-RU,en-US,de-DE,ar-SA] [--wait 7000]
//        [--cdp http://127.0.0.1:9222] [--device desktop] [--shots <RUN_DIR>/screenshots/legal] [--log blocked.jsonl]
//        [--out <RUN_DIR>/raw/legal-guest.json]
//
// --cdp: a NEW empty context inside the user's own Chrome (not automated: navigator.webdriver is false there, so
//        analytics counters that skip automated browsers do set their cookies); the user's tabs are not touched and the
//        context is closed at the end. Without --cdp a Playwright browser is used and navigator.webdriver is true —
//        the result notes that counters may be missing then.
// Output: runs[] = { url, locale, lang, dir, webdriver, cookies: {t0: [...], tN: [...]}, storage: {t0, tN},
//   hosts: {first, third}, banner, consent, links, operator, age, dialogs, note? }. Cookie VALUES are never stored.
const fs = require('fs');
const path = require('path');
const { parseArgs, loadRules, writeOut, urlsFromArgs, hostMatches, launchOptions, trackPage, closeTab } = require('./lib');
const { guardContext, guardedPage } = require('./guard');
const { resolveDevice, targetIdOf } = require('./device_context');

const CONSENT_RX = '(cookie|куки|кукис|согласи|персональн\\w* данн|обработк\\w* данн|consent|privacy|datenschutz|einwilligung|' +
  'consentement|confidentialit|consentimiento|privacidad|zgod|prywatno|同意|동의|クッキー|개인정보|ملفات تعريف الارتباط|موافق|' +
  'עוגיות|הסכמ)';
const LINK_RX = '(privacy|policy|terms|cookie|legal|oferta|offer|impressum|imprint|datenschutz|agb|conditions|confidential|' +
  'персональн|конфиденц|политик|соглашен|оферт|правил|условия|cgu|mentions)';
const OPERATOR_RX = '(ИНН|ОГРН|ОГРНИП|оператор персональных данных|юридический адрес|VAT|USt-IdNr|Handelsregister|SIRET|' +
  'registered office|company number|ABN)';

function partyOf(host, firstHosts, allowed) {
  host = String(host || '').replace(/^\./, '').toLowerCase();
  if (allowed.length) return allowed.some(p => hostMatches(host, p) || (p.startsWith('*.') ? false : host.endsWith('.' + p))) ? 'first' : 'third';
  return firstHosts.some(h => host === h || host.endsWith('.' + h) || h.endsWith('.' + host)) ? 'first' : 'third';
}

function cookieRows(cookies, firstHosts, allowed) {
  const nowS = Date.now() / 1000;
  return cookies.map(c => ({ name: c.name, domain: c.domain, party: partyOf(c.domain, firstHosts, allowed),
    expires: c.expires > 0 ? Math.round((c.expires - nowS) / 86400) + 'd' : 'session',
    httpOnly: c.httpOnly, secure: c.secure, sameSite: c.sameSite }));
}

function inspect({ CONSENT_RX, LINK_RX, OPERATOR_RX }) {
  const crx = new RegExp(CONSENT_RX, 'i'), lrx = new RegExp(LINK_RX, 'i'), orx = new RegExp(OPERATOR_RX, 'i');
  const vis = (e) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && +cs.opacity !== 0; };
  const text = document.body ? document.body.innerText || '' : '';
  const snippets = (rx, max) => { const out = []; const g = new RegExp('.{0,60}' + rx.source + '[^\\n]{0,80}', 'gi'); let m; while ((m = g.exec(text)) && out.length < max) out.push(m[0].replace(/\s+/g, ' ').trim()); return out; };
  // Banner: a visible dialog/region/fixed block with consent words.
  const cands = [...document.querySelectorAll('[role=dialog],[role=alertdialog],[role=region],aside,[id*=cookie i],[class*=cookie i],[id*=consent i],[class*=consent i],[id*=gdpr i],[class*=gdpr i]')]
    .concat([...document.querySelectorAll('body *')].filter(e => { const p = getComputedStyle(e).position; return (p === 'fixed' || p === 'sticky') && e.children.length < 40; }));
  const banner = cands.find(e => vis(e) && crx.test(e.innerText || ''));
  const keys = (st) => { const out = []; try { for (let i = 0; i < st.length; i++) out.push(st.key(i)); } catch { /* blocked */ } return out; };
  return {
    lang: document.documentElement.lang || null, dir: document.documentElement.dir || getComputedStyle(document.documentElement).direction,
    webdriver: navigator.webdriver === true,
    banner: banner ? { present: true, text: (banner.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 200),
      buttons: [...banner.querySelectorAll('button,[role=button],a')].filter(vis).map(b => (b.innerText || b.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim()).filter(Boolean).slice(0, 8) } : { present: false },
    consent: snippets(crx, 8),
    links: [...document.querySelectorAll('a[href]')].filter(a => lrx.test(a.getAttribute('href')) || lrx.test(a.innerText || ''))
      .map(a => ({ text: (a.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60), href: a.href })).slice(0, 20),
    operator: snippets(orx, 4),
    age: [...new Set((text.match(/(^|[^\d])(0|6|12|16|18)\+/g) || []).map(s => s.replace(/^[^\d]/, '')))].slice(0, 5),
    storage: { local: keys(localStorage), session: keys(sessionStorage) },
  };
}

async function inspectLocale(browser, url, locale, a, rules, allowed) {
  const d = resolveDevice(a.device || 'desktop');
  const ctxOpts = { ...d.options, ...(locale ? { locale, extraHTTPHeaders: { 'Accept-Language': locale } } : {}) };
  const context = await browser.newContext(ctxOpts);
  const blocked = [];
  let tabId = null;
  try {
    if (rules) await guardContext(context, rules, { logFile: a.log, log: blocked });
    const page = await context.newPage();
    // tabs.json: over CDP the page is a tab of the user's Chrome (tool cdp, target id) — closed with the context below
    tabId = a.cdp ? trackPage(page, { profile: 'cdp' + (locale ? '@' + locale : ''), tool: 'cdp', targetId: await targetIdOf(context, page), engine: 'chromium' })
      : trackPage(page, { profile: (a.device || 'desktop') + (locale ? '@' + locale : ''), engine: 'chromium' });
    const hosts = new Set();
    page.on('request', r => { try { hosts.add(new URL(r.url()).hostname); } catch { /* data: */ } });
    const g = guardedPage(page, rules, { logFile: a.log, throttleMs: 0 });
    const nav = await g.goto(url, { waitUntil: 'load', timeout: 45000 });
    if (!nav.performed) return { url, locale, blocked: nav };
    const firstHosts = [new URL(page.url()).hostname.toLowerCase()];
    const t0 = { cookies: cookieRows(await context.cookies(), firstHosts, allowed), info: await page.evaluate(inspect, { CONSENT_RX, LINK_RX, OPERATOR_RX }) };
    await page.waitForTimeout(+a.wait);
    const tN = { cookies: cookieRows(await context.cookies(), firstHosts, allowed), info: await page.evaluate(inspect, { CONSENT_RX, LINK_RX, OPERATOR_RX }) };
    let shot = null;
    if (a.shots) {
      fs.mkdirSync(a.shots, { recursive: true });
      shot = path.resolve(a.shots, `legal-${new URL(url).hostname}-${locale || 'default'}.png`);
      await page.screenshot({ path: shot });
    }
    const third = [...hosts].filter(h => partyOf(h, firstHosts, allowed) === 'third').sort();
    const info = tN.info;
    return { url, finalUrl: page.url(), locale, lang: info.lang, dir: info.dir, webdriver: info.webdriver,
      cookies: { t0: t0.cookies, tN: tN.cookies, waitMs: +a.wait }, storage: { t0: t0.info.storage, tN: info.storage },
      hosts: { first: [...hosts].filter(h => !third.includes(h)).sort(), third },
      banner: info.banner, consent: info.consent, links: info.links, operator: info.operator, age: info.age,
      dialogs: blocked.filter(e => e.type === 'dialog').map(e => e.reason), ...(shot ? { screenshot: shot } : {}),
      ...(info.webdriver ? { note: 'navigator.webdriver = true: счётчики (Метрика и т.п.) могут не ставить cookie в автоматизированном браузере — повторить с --cdp в обычном Chrome' } : {}) };
  } finally { if (await context.close().then(() => true, () => false)) closeTab(tabId); }
}

function summary(r) {
  if (r.blocked || r.error) return `${r.locale || '-'} ${r.url}: ${r.error || 'переход запрещён'}`;
  const c0 = r.cookies.t0, cN = r.cookies.tN;
  return `${r.locale || '-'} ${r.url}: cookie сразу ${c0.length} (третьих сторон ${c0.filter(c => c.party === 'third').length}), ` +
    `через ${r.cookies.waitMs} мс ${cN.length}; сторонних хостов ${r.hosts.third.length}; баннер: ${r.banner.present ? 'есть' : 'нет'}; ` +
    `ссылок на документы ${r.links.length}; lang=${r.lang || '-'} dir=${r.dir}`;
}

module.exports = { inspect, partyOf, cookieRows };

if (require.main === module) {
  (async () => {
    const a = parseArgs(process.argv.slice(2), { wait: '7000' });
    const urls = urlsFromArgs(a);
    const rules = loadRules(a.rules);
    const allowed = rules ? rules.rules.allowed_domains || [] : [];
    const locales = a.locales && a.locales !== true ? String(a.locales).split(',').map(s => s.trim()).filter(Boolean) : [null];
    const pw = require('playwright');
    const browser = a.cdp ? await pw.chromium.connectOverCDP(String(a.cdp)) : await pw.chromium.launch(launchOptions({}, rules));
    const runs = [];
    try {
      for (const url of urls) for (const locale of locales) {
        try { runs.push(await inspectLocale(browser, url, locale, a, rules, allowed)); }
        catch (e) { if (e && e.exitCode === 4) throw e; runs.push({ url, locale, error: String(e.message || e).split('\n')[0] }); }
      }
    } finally { await browser.close().catch(() => {}); }  // over CDP: only disconnects, the user's browser stays
    for (const r of runs) process.stderr.write(summary(r) + '\n');
    writeOut(a.out, { tool: 'legal_guest', cdp: !!a.cdp, runs });
  })().catch(e => { console.error(String(e.message || e)); process.exit((e && e.exitCode) || 1); });
}
