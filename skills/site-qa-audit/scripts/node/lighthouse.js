'use strict';
// Lighthouse mobile/desktop по списку URL. Chrome — из кэша Playwright (или CHROME_PATH).
// node lighthouse.js URL [URL...] [--form mobile|desktop|both] [--categories performance,accessibility,best-practices,seo]
//      [--out lighthouse.json] [--reports-dir DIR]  (полные HTML-отчёты)
const fs = require('fs');
const path = require('path');
const { parseArgs, sleep, writeOut, urlsFromArgs } = require('./lib');

(async () => {
  const args = parseArgs(process.argv.slice(2), { form: 'both', categories: 'performance,accessibility,best-practices,seo' });
  const all = urlsFromArgs(args);
  // file:// (local app): Lighthouse measures network loading of a site — not applicable, reported as such
  const notApplicable = all.filter(u => /^file:/i.test(u)).map(url => ({ url, reason: 'не применимо к file:// — скорость загрузки по сети не измеряется' }));
  const urls = all.filter(u => !/^file:/i.test(u));
  if (!urls.length) { writeOut(args.out, { tool: 'lighthouse', results: [], notApplicable }); return; }
  const { default: lighthouse, desktopConfig } = await import('lighthouse');
  const chromeLauncher = await import('chrome-launcher');
  const chromePath = process.env.CHROME_PATH || require('playwright').chromium.executablePath();
  const chrome = await chromeLauncher.launch({ chromePath, chromeFlags: ['--headless=new', '--no-sandbox'] });
  const forms = args.form === 'both' ? ['mobile', 'desktop'] : [args.form];
  const results = [];
  try {
    for (const url of urls) for (const form of forms) {
      const flags = { port: chrome.port, output: args['reports-dir'] ? 'html' : 'json', logLevel: 'error',
        onlyCategories: args.categories.split(',') };
      const config = form === 'desktop' ? desktopConfig : undefined;
      try {
        const r = await lighthouse(url, flags, config);
        const lhr = r.lhr, a = lhr.audits;
        const metric = id => a[id] ? { value: a[id].numericValue, display: a[id].displayValue, score: a[id].score } : null;
        const opportunities = Object.values(a).filter(x => x.details && x.details.type === 'opportunity' && x.score !== null && x.score < 0.9)
          .map(x => ({ id: x.id, title: x.title, savingsMs: x.details.overallSavingsMs, savingsBytes: x.details.overallSavingsBytes, display: x.displayValue }));
        const failed = Object.values(a).filter(x => x.score !== null && x.score < 0.9 && x.scoreDisplayMode === 'binary')
          .map(x => ({ id: x.id, title: x.title }));
        let report = null;
        if (args['reports-dir']) {
          fs.mkdirSync(args['reports-dir'], { recursive: true });
          report = path.join(args['reports-dir'], `${new URL(url).hostname}-${results.length}-${form}.html`);
          fs.writeFileSync(report, r.report);
        }
        results.push({ url, form, scores: Object.fromEntries(Object.entries(lhr.categories).map(([k, v]) => [k, v.score])),
          metrics: { LCP: metric('largest-contentful-paint'), CLS: metric('cumulative-layout-shift'), TBT: metric('total-blocking-time'),
            FCP: metric('first-contentful-paint'), SI: metric('speed-index'), TTI: metric('interactive') },
          totalBytes: a['total-byte-weight'] && a['total-byte-weight'].numericValue,
          requests: a['network-requests'] && a['network-requests'].details ? a['network-requests'].details.items.length : null,
          opportunities, failed, report, runWarnings: lhr.runWarnings });
      } catch (e) { results.push({ url, form, error: String(e.message || e) }); }
      await sleep(1000);
    }
  } finally { await chrome.kill(); }
  writeOut(args.out, { tool: 'lighthouse', version: require('lighthouse/package.json').version, results, ...(notApplicable.length ? { notApplicable } : {}) });
})().catch(e => { console.error(e); process.exit((e && e.exitCode) || 1); });
