'use strict';
// axe-core по списку URL. Только чтение страницы: никаких кликов и отправок.
// node a11y.js URL [URL...] [--url URL] [--urls-file f] [--rules rules.json] [--log blocked.jsonl] [--browser chromium|firefox|webkit]
//      [--width 1440 --height 900] [--tags wcag2a,wcag2aa,wcag21aa,wcag22aa] [--throttle 1500] [--out a11y.json]
//      URL: http(s), file:///… or a path to a local file (inside site.local_roots of rules.json)
//      [--frames all|main]  all (default): axe enters iframes; the result lists innerText length per frame so that
//                           an app inside an iframe (page text ~250 chars) is visible. main: iframes excluded.
//      [--locales ru-RU,de-DE,ar-SA]  every URL in every locale (context locale + Accept-Language); lang/dir in results
const { parseArgs, loadRules, guardContext, sleep, writeOut, urlsFromArgs, launchOptions, trackPage, closeTab } = require('./lib');
const pw = require('playwright');
const { AxeBuilder } = require('@axe-core/playwright');
const { pageText } = require('./frames');
const { guardedPage } = require('./guard');

(async () => {
  const args = parseArgs(process.argv.slice(2), { browser: 'chromium', width: '1440', height: '900',
    tags: 'wcag2a,wcag2aa,wcag21a,wcag21aa,wcag22aa,best-practice', throttle: '1500', frames: 'all' });
  const urls = urlsFromArgs(args);
  const rules = loadRules(args.rules);
  const locales = args.locales && args.locales !== true ? String(args.locales).split(',').map(s => s.trim()).filter(Boolean) : [null];
  const browser = await pw[args.browser].launch(launchOptions({}, rules));
  const blocked = [];
  const results = [];
  try {
    for (const locale of locales) {
      const context = await browser.newContext({ viewport: { width: +args.width, height: +args.height },
        ...(locale ? { locale, extraHTTPHeaders: { 'Accept-Language': locale } } : {}) });
      await guardContext(context, rules, blocked);
      const page = await context.newPage();
      const tabId = trackPage(page, { profile: `${args.width}x${args.height}` + (locale ? '@' + locale : ''), engine: args.browser });
      page.on('dialog', d => d.dismiss().catch(() => {}));
      const g = guardedPage(page, rules, { log: blocked, logFile: args.log, throttleMs: 0 });
      for (const url of urls) {
        try {
          // url_guard first (http(s) and file:// inside local_roots); a denied URL is reported, not opened
          const nav = await g.goto(url, { waitUntil: 'load', timeout: 45000 });
          if (!nav.performed) { results.push({ url, ...(locale ? { locale } : {}), blocked: { rule: nav.rule, reason: nav.reason } }); continue; }
          await page.waitForTimeout(800);
          let builder = new AxeBuilder({ page }).withTags(args.tags.split(','));
          if (args.frames === 'main') builder = builder.exclude('iframe');
          const r = await builder.analyze();
          const text = await pageText(page, args.frames === 'main' ? 'main' : 'all');
          const ld = await page.evaluate(() => ({ lang: document.documentElement.lang || null, dir: getComputedStyle(document.documentElement).direction }));
          results.push({
            url, ...(locale ? { locale } : {}), lang: ld.lang, dir: ld.dir, text,
            ...(text.frames.length && text.main < 500 ? { note: `текст страницы ${text.main} симв., основное содержимое во фреймах (iframe)` } : {}),
            violations: r.violations.map(v => ({
              id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl, tags: v.tags.filter(t => /wcag|best/.test(t)),
              nodes: v.nodes.slice(0, 10).map(n => ({ target: n.target.join(' '), html: n.html.slice(0, 200), summary: n.failureSummary })),
              count: v.nodes.length,
            })),
            incomplete: r.incomplete.map(v => ({ id: v.id, help: v.help, count: v.nodes.length })),
            passes: r.passes.length,
          });
        } catch (e) {
          if (e && e.exitCode === 4) throw e;  // guard unavailable: stop
          results.push({ url, ...(locale ? { locale } : {}), error: String(e.message || e) });
        }
        await sleep(+args.throttle);
      }
      await context.close().catch(() => {});
      closeTab(tabId);
    }
  } finally { await browser.close(); }
  writeOut(args.out, { tool: 'axe-core', frames: args.frames, browser: args.browser, viewport: `${args.width}x${args.height}`,
    ...(locales[0] ? { locales } : {}), blocked, results });
})().catch(e => { console.error(e); process.exit((e && e.exitCode) || 1); });
