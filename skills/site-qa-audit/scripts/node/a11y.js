'use strict';
// axe-core по списку URL. Только чтение страницы: никаких кликов и отправок.
// node a11y.js URL [URL...] [--urls-file f] [--rules rules.json] [--browser chromium|firefox|webkit]
//      [--width 1440 --height 900] [--tags wcag2a,wcag2aa,wcag21aa,wcag22aa] [--throttle 1500] [--out a11y.json]
//      [--frames all|main]  all (default): axe enters iframes; the result lists innerText length per frame so that
//                           an app inside an iframe (page text ~250 chars) is visible. main: iframes excluded.
const { parseArgs, loadRules, guardContext, sleep, writeOut, urlsFromArgs } = require('./lib');
const pw = require('playwright');
const { AxeBuilder } = require('@axe-core/playwright');
const { pageText } = require('./frames');

(async () => {
  const args = parseArgs(process.argv.slice(2), { browser: 'chromium', width: '1440', height: '900',
    tags: 'wcag2a,wcag2aa,wcag21a,wcag21aa,wcag22aa,best-practice', throttle: '1500', frames: 'all' });
  const urls = urlsFromArgs(args);
  const rules = loadRules(args.rules);
  const browser = await pw[args.browser].launch();
  const context = await browser.newContext({ viewport: { width: +args.width, height: +args.height } });
  const blocked = [];
  await guardContext(context, rules, blocked);
  const page = await context.newPage();
  page.on('dialog', d => d.dismiss().catch(() => {}));
  const results = [];
  for (const url of urls) {
    try {
      await page.goto(url, { waitUntil: 'load', timeout: 45000 });
      await page.waitForTimeout(800);
      let builder = new AxeBuilder({ page }).withTags(args.tags.split(','));
      if (args.frames === 'main') builder = builder.exclude('iframe');
      const r = await builder.analyze();
      const text = await pageText(page, args.frames === 'main' ? 'main' : 'all');
      results.push({
        url, lang: await page.evaluate(() => document.documentElement.lang || null), text,
        ...(text.frames.length && text.main < 500 ? { note: `текст страницы ${text.main} симв., основное содержимое во фреймах (iframe)` } : {}),
        violations: r.violations.map(v => ({
          id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl, tags: v.tags.filter(t => /wcag|best/.test(t)),
          nodes: v.nodes.slice(0, 10).map(n => ({ target: n.target.join(' '), html: n.html.slice(0, 200), summary: n.failureSummary })),
          count: v.nodes.length,
        })),
        incomplete: r.incomplete.map(v => ({ id: v.id, help: v.help, count: v.nodes.length })),
        passes: r.passes.length,
      });
    } catch (e) { results.push({ url, error: String(e.message || e) }); }
    await sleep(+args.throttle);
  }
  await browser.close();
  writeOut(args.out, { tool: 'axe-core', frames: args.frames, browser: args.browser, viewport: `${args.width}x${args.height}`, blocked, results });
})().catch(e => { console.error(e); process.exit((e && e.exitCode) || 1); });
