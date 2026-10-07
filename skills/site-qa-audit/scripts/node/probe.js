'use strict';
// Проверка запуска браузеров Playwright: node probe.js chromium firefox webkit -> JSON.
const pw = require('playwright');
(async () => {
  const out = {};
  for (const name of process.argv.slice(2)) {
    try {
      const b = await pw[name].launch({ timeout: 30000 });
      out[name] = { ok: true, version: b.version() };
      await b.close();
    } catch (e) {
      const msg = String(e.message || e).replace(/\x1b\[[0-9;]*m/g, '');
      const m = msg.match(/\[err\][^\n]*/g);
      out[name] = { ok: false, error: (m ? m[m.length - 1] : msg.split('\n')[0]).slice(0, 160) };
    }
  }
  console.log(JSON.stringify(out));
})();
