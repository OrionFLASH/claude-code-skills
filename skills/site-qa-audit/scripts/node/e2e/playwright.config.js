'use strict';
// Playwright Test configuration of scripts/node/e2e_run.js — not for direct use: e2e_run.js sets the environment
// (folder with the copied specs, report file, window of the run, browser, timeout).
const path = require('path');

const e = process.env;
if (!e.SITE_QA_E2E_DIR) throw new Error('playwright.config.js: запускать через node scripts/node/e2e_run.js');

module.exports = {
  testDir: e.SITE_QA_E2E_DIR,
  outputDir: path.join(e.SITE_QA_E2E_DIR, 'test-results'),
  timeout: +e.SITE_QA_E2E_TIMEOUT || 30000,
  workers: 1,
  retries: 0,
  fullyParallel: false,
  forbidOnly: true,
  reporter: [['json', { outputFile: e.SITE_QA_E2E_REPORT }], ['line']],
  use: {
    // browserName only when --browser is given: otherwise the device of the stub decides (iPad -> WebKit)
    ...(e.SITE_QA_E2E_BROWSER ? { browserName: e.SITE_QA_E2E_BROWSER } : {}),
    headless: e.SITE_QA_E2E_HEADLESS !== '0',
    launchOptions: { slowMo: +e.SITE_QA_E2E_SLOWMO || 0 },
    trace: 'off',
    video: 'off',
  },
};
