'use strict';
// Guard of the run for a SEPARATE Playwright MCP server of a local app (references/local-files.md → «Playwright MCP»).
// `browser_mode.py mcp <RUN_DIR>` writes <RUN_DIR>/playwright-mcp.json with browser.initPage = [<RUN_DIR>/mcp-guard.js]
// (a two-line module that calls make() below). Playwright MCP loads it for every new tab, and the tab's context gets
// the same route guard as the node scripts (guard.js: main-frame navigation, frames, resources; file:// only inside
// site.local_roots, never through a symlink; forbidden paths) — the flag allowUnrestrictedFileAccess, which MCP needs to
// open file:// at all, no longer opens the rest of the disk. Decisions go to the log (blocked-mcp.jsonl); native
// dialogs are dismissed, as in the node scripts. Fail closed: without a readable rules.json make() throws and MCP
// cannot open a tab («Failed to load init page»).
const { loadRules } = require('./lib');
const { guardContext } = require('./guard');

function make(rulesFile, logFile) {
  const rules = loadRules(rulesFile);
  if (!rules) throw new Error('mcp_guard: нужен rules.json прогона');
  const done = new WeakSet();
  return async ({ page }) => {
    const context = page.context();
    if (done.has(context)) return;
    done.add(context);
    await guardContext(context, rules, { logFile });
  };
}

module.exports = { make };
