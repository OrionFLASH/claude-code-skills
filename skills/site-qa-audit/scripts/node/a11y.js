'use strict';
// axe-core по списку URL. Только чтение страницы: никаких кликов и отправок.
// node a11y.js URL [URL...] [--urls-file f] [--rules rules.json] [--browser chromium|firefox|webkit]
//      [--width 1440 --height 900] [--tags wcag2a,wcag2aa,wcag21aa,wcag22aa] [--throttle 1500] [--out a11y.json]
//      [--frames all|main]  all (default): axe enters iframes; the result lists innerText length per frame so that
//                           an app inside an iframe (page text ~250 chars) is visible. main: iframes excluded.
//      [--locales ru-RU,de-DE,ar-SA]  every URL in every locale (context locale + Accept-Language); lang/dir in results
const { parseArgs, loadRules, guardContext, sleep, writeOut, urlsFromArgs } = require('./lib');
const pw = require('playwright');
const { AxeBuilder } = require('@axe-core/playwright');
const { pageText } = require('./frames');

(async () => {
  const args = parseArgs(process.argv.slice(2), { browser: 'chromium', width: '1440', height: '900',
    tags: 'wcag2a,wcag2aa,wcag21a,wcag21aa,wcag22aa,best-practice', throttle: '1500', frames: 'all' });
  const urls = urlsFromArgs(args);
  const rules = loadRules(args.rules);
  const locales = args.locales && args.locales !== true ? String(args.locales).split(',').map(s => s.trim()).filter(Boolean) : [null];
  const browser = await pw[args.browser].launch();
  const blocked = [];
  const results = [];
  try {
    for (const locale of locales) {
      const context = await browser.newContext({ viewport: { width: +args.width, height: +args.height },
        ...(locale ? { locale, extraHTTPHeaders: { 'Accept-Language': locale } } : {}) });
      await guardContext(context, rules, blocked);
      const page = await context.newPage();
      page.on('dialog', d => d.dismiss().catch(() => {}));
      for (const url of urls) {
        try {
          await page.goto(url, { waitUntil: 'load', timeout: 45000 });
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
        } catch (e) { results.push({ url, ...(locale ? { locale } : {}), error: String(e.message || e) }); }
        await sleep(+args.throttle);
      }
      await context.close().catch(() => {});
    }
  } finally { await browser.close(); }
  writeOut(args.out, { tool: 'axe-core', frames: args.frames, browser: args.browser, viewport: `${args.width}x${args.height}`,
    ...(locales[0] ? { locales } : {}), blocked, results });
})().catch(e => { console.error(e); process.exit((e && e.exitCode) || 1); });
