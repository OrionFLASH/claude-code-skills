'use strict';
// Re-run of one measurement (finding.repro, S-9): opens the URL under guard.js and answers «is the defect still there?».
//
//   node repro.js --url URL (--js "expression: true if the defect is present" | --selector SEL [--assert "b.w < 24"])
//        [--device pixel7 | --size 1440x813] [--locale de-DE] [--setup setup.js] [--state auth-state.json]
//        [--rules rules.json] [--log blocked.jsonl] [--read-only] [--wait 500]
//
// --js: evaluated in the page (expression or `async () => …` body result); truthy = reproduced; the value is returned.
// --selector: found and visible = reproduced, or, with --assert, the expression over its box b = {x, y, w, h} decides.
// Output (stdout, one JSON line): { reproduced, value?, box?, url, device, media }.
// Exit code: 0 reproduced, 1 not reproduced, 4 guard unavailable, 2 other error (recheck.py treats it as an error).
const path = require('path');
const fs = require('fs');
const { parseArgs, loadRules, toUrl } = require('./lib');
const { openDevice } = require('./device_context');
const { guardedPage } = require('./guard');
const { locate } = require('./frames');

(async () => {
  const a = parseArgs(process.argv.slice(2), { wait: '500' });
  a.url = toUrl(a.url);
  if (!a.url || (!a.js && !a.selector)) {
    console.error('node repro.js --url URL (--js EXPR | --selector SEL [--assert EXPR]) [--device D|--size WxH] [--rules rules.json]');
    process.exit(2);
  }
  const rules = loadRules(a.rules);
  const state = a.state ? JSON.parse(fs.readFileSync(a.state, 'utf8')) : undefined;
  const dev = await openDevice({ device: a.device || a.size || 'desktop', rules, logFile: a.log, storageState: state, locale: a.locale, readOnly: !!a['read-only'] });
  let res;
  try {
    const g = guardedPage(dev.page, rules, { logFile: a.log, throttleMs: 0, readOnly: !!a['read-only'] });
    const nav = await g.goto(a.url, { waitUntil: 'load', timeout: 45000 });
    if (!nav.performed) throw Object.assign(new Error('переход запрещён: ' + nav.reason), { exitCode: 2 });
    await dev.page.waitForTimeout(+a.wait);
    if (a.setup) await require(path.resolve(a.setup))({ page: dev.page, guarded: g });
    if (a.js) {
      const value = await dev.page.evaluate(`(async () => (${a.js}))()`);
      res = { reproduced: !!value, value };
    } else {
      const loc = locate(dev.page, a.selector).filter({ visible: true }).first();
      const found = (await loc.count()) > 0;
      const bb = found ? await loc.boundingBox() : null;
      const b = bb ? { x: Math.round(bb.x), y: Math.round(bb.y), w: Math.round(bb.width), h: Math.round(bb.height) } : null;
      let reproduced = found && !!b;
      if (a.assert) reproduced = !!b && !!new Function('b', `return (${a.assert});`)(b);
      res = { reproduced, found, box: b };
    }
  } finally { await dev.close().catch(() => {}); }
  console.log(JSON.stringify({ ...res, url: a.url, device: a.device || a.size || 'desktop', media: dev.media }));
  process.exit(res.reproduced ? 0 : 1);
})().catch(e => { console.error(String(e.message || e)); process.exit((e && e.exitCode === 4) ? 4 : 2); });
