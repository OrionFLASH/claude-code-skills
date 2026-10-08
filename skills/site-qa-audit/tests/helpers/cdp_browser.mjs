// Starts a headless Chromium with a CDP port for tests (stands in for the user's logged-in Chrome).
// Usage: node cdp_browser.mjs <port>   — runs until killed.
import path from 'node:path';
import { createRequire } from 'node:module';
const here = path.dirname(new URL(import.meta.url).pathname);
const require = createRequire(path.join(here, '..', '..', 'scripts', 'node', 'package.json'));
const { chromium } = require('playwright');
const port = process.argv[2] || '9339';
const browser = await chromium.launch({ headless: true, args: [`--remote-debugging-port=${port}`] });
process.stdout.write(`ready ${port}\n`);
const stop = async () => { await browser.close().catch(() => {}); process.exit(0); };
process.on('SIGTERM', stop); process.on('SIGINT', stop);
setInterval(() => {}, 1 << 30);
