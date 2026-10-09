'use strict';
// Self-check of the Playwright MCP configuration of a run (browser_mode.py mcp <RUN_DIR> --check): starts the SAME
// server the user would add (node <playwright>/cli.js mcp --config <RUN_DIR>/playwright-mcp.json) over stdio, as an
// MCP client: browser_navigate to the start URL (must open), then to each --outside URL (must be blocked by the guard
// of the run), browser_close. Nothing is added to Claude Code settings; the browser is the bundled Chromium with an
// in-memory profile (isolated) — the user's browser and windows are not touched.
//
//   node mcp_check.js --config <RUN_DIR>/playwright-mcp.json --url file:///…/app/index.html [--outside URL ...]
//        [--log <RUN_DIR>/logs/blocked-mcp.jsonl] [--timeout 60000]
// --log: an outside URL counts as blocked only if the guard wrote a deny record for it (a missing file would also
// «not open» — that is not proof of the guard).
// Output JSON: { ok, server, inside: { url, opened, title?, error? }, outside: [{ url, blocked, rule?, error? }] }.
// Exit: 0 ok (inside opened, every outside blocked), 1 not ok, 2 bad input / server did not start.
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const { parseArgs, multiArg, toUrl } = require('./lib');

const CLI = path.join(path.dirname(require.resolve('playwright/package.json')), 'cli.js');

function client(config, timeout) {
  const p = spawn(process.execPath, [CLI, 'mcp', '--config', config], { stdio: ['pipe', 'pipe', 'pipe'], cwd: path.dirname(config) });
  let buf = '', err = '', id = 0;
  const waiters = new Map();
  p.stdout.on('data', (d) => {
    buf += d;
    for (let i; (i = buf.indexOf('\n')) >= 0;) {
      const line = buf.slice(0, i); buf = buf.slice(i + 1);
      let m; try { m = JSON.parse(line); } catch { continue; }
      if (m.id && waiters.has(m.id)) { waiters.get(m.id)(m); waiters.delete(m.id); }
    }
  });
  p.stderr.on('data', (d) => { err += d; });
  const call = (method, params) => new Promise((resolve, reject) => {
    const k = ++id;
    const t = setTimeout(() => { waiters.delete(k); reject(new Error(`MCP: нет ответа на ${method} за ${timeout} мс ${err.slice(-300)}`)); }, timeout);
    waiters.set(k, (m) => { clearTimeout(t); resolve(m); });
    p.stdin.write(JSON.stringify({ jsonrpc: '2.0', id: k, method, params }) + '\n');
  });
  const notify = (method, params) => p.stdin.write(JSON.stringify({ jsonrpc: '2.0', method, ...(params ? { params } : {}) }) + '\n');
  const text = (m) => ((m.result && m.result.content) || []).map(c => c.text || '').join('\n');
  return { call, notify, text, stop: () => { try { p.stdin.end(); } catch { /* closed */ } p.kill(); }, stderr: () => err };
}

const readLog = (f) => { try { return fs.readFileSync(f, 'utf8').split('\n').filter(Boolean).map(l => { try { return JSON.parse(l); } catch { return {}; } }); } catch { return []; } };

async function main() {
  const argv = process.argv.slice(2);
  const a = parseArgs(argv, { timeout: '60000' });
  if (!a.config || a.config === true || !fs.existsSync(a.config) || !a.url) throw Object.assign(new Error('node mcp_check.js --config <RUN_DIR>/playwright-mcp.json --url URL [--outside URL]'), { exitCode: 2 });
  const inside = toUrl(String(a.url));
  const outside = multiArg(argv, 'outside').map(toUrl);
  const logFile = a.log && a.log !== true ? path.resolve(String(a.log)) : null;
  const c = client(path.resolve(String(a.config)), +a.timeout || 60000);
  const res = { tool: 'mcp_check', config: path.resolve(String(a.config)), ok: false };
  try {
    const init = await c.call('initialize', { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'site-qa-audit mcp_check', version: '1' } });
    if (!init.result) throw Object.assign(new Error('MCP не ответил на initialize: ' + JSON.stringify(init.error || {})), { exitCode: 2 });
    res.server = init.result.serverInfo;
    c.notify('notifications/initialized');
    const nav = await c.call('tools/call', { name: 'browser_navigate', arguments: { url: inside } });
    const t = c.text(nav);
    const title = (t.match(/Page Title: (.*)/) || [])[1];
    res.inside = { url: inside, opened: !nav.result.isError && new RegExp('Page URL: ' + inside.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).test(t), ...(title ? { title } : {}),
      ...(nav.result.isError ? { error: t.replace(/^### Error\n/, '').split('\n')[0].slice(0, 300) } : {}) };
    res.outside = [];
    for (const u of outside) {
      const r = await c.call('tools/call', { name: 'browser_navigate', arguments: { url: u } });
      const tx = c.text(r);
      const opened = !r.result.isError && new RegExp('Page URL: ' + u.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).test(tx);
      const rec = logFile ? readLog(logFile).find(x => x.url === u && x.decision === 'deny') : null;
      res.outside.push({ url: u, blocked: !opened && (!logFile || !!rec), ...(rec ? { rule: rec.rule } : {}),
        ...(r.result.isError ? { error: tx.replace(/^### Error\n/, '').split('\n')[0].slice(0, 300) } : {}) });
    }
    await c.call('tools/call', { name: 'browser_close', arguments: {} }).catch(() => {});
    res.ok = !!res.inside.opened && res.outside.every(o => o.blocked);
  } finally { c.stop(); }
  return res;
}

if (require.main === module) {
  main().then((res) => { console.log(JSON.stringify(res, null, 1)); process.exit(res.ok ? 0 : 1); })
    .catch((e) => { console.log(JSON.stringify({ tool: 'mcp_check', ok: false, error: String(e.message || e) })); process.exit((e && e.exitCode) || 2); });
}
