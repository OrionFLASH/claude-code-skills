'use strict';
// `@playwright/test` for specs run by scripts/node/e2e_run.js (found through NODE_PATH, never installed anywhere):
// playwright/test of the skill's own `playwright` package — the real Playwright Test — with ONE addition: every test
// context gets the guard of the run (guard.js routes: navigation, frames and resources outside the rules are aborted
// and logged to SITE_QA_E2E_LOG). Nothing else is changed: test, expect, devices, defineConfig… are the originals.
const path = require('path');
const base = require('playwright/test');

const NODE_DIR = path.resolve(__dirname, '..', '..', '..', '..');
let test = base.test;
if (process.env.SITE_QA_E2E_RULES) {
  const { loadRules } = require(path.join(NODE_DIR, 'lib.js'));
  const { guardContext } = require(path.join(NODE_DIR, 'guard.js'));
  const rules = loadRules(process.env.SITE_QA_E2E_RULES);
  test = base.test.extend({
    context: async ({ context }, use) => {
      await guardContext(context, rules, { logFile: process.env.SITE_QA_E2E_LOG || undefined });
      await use(context);
    },
  });
}

module.exports = { ...base, test, default: test };
