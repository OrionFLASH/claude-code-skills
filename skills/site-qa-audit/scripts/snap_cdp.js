#!/usr/bin/env node
'use strict';
// Snapshot + annotation through CDP / plain Playwright (no MCP): the counterpart of snap_mcp.js.
// Thin entry point; the implementation (targets, @avoid, frames, devices, retries, self-check, contact sheet)
// is scripts/node/shot.js. Arguments are passed through unchanged, for example:
//   node <SKILL_DIR>/scripts/snap_cdp.js --cdp http://127.0.0.1:9222 --out <RUN_DIR>/screenshots/F-001-x.png "#bell|Подпись|error"
// Dependencies: cd <SKILL_DIR>/scripts/node && npm install
require('./node/shot.js').cli();
