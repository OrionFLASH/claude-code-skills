'use strict';
// Run regression stubs of findings (scripts/e2e_stub.py) with Playwright Test — the runner of the skill's own
// `playwright` package (@playwright/test is only a re-export of playwright/test: nothing extra to install).
// references/fix-cycle.md → «Заготовка e2e: запуск».
//
//   node e2e_run.js <F-001.spec.ts|.spec.js> [...] --rules <RUN_DIR>/rules.json
//        (--app-url file:///…/app/ | --base-url https://example.com) [--expect fail|pass] [--repeat-each N]
//        [--browser chromium|webkit|firefox] [--headed | --headless] [--slowmo 250] [--timeout 30000]
//        [--log <RUN_DIR>/logs/blocked.jsonl] [--out <RUN_DIR>/raw/e2e-F-001.json] [--keep]
//
// How: the specs are copied into a fresh temporary folder (no project node_modules around them) and run with
// NODE_PATH=scripts/node/e2e/shim — `import … from '@playwright/test'` there is playwright/test of the skill with ONE
// addition: every test context gets the guard of the run (guard.js routes: navigation outside the rules, file:// outside
// site.local_roots and forbidden paths are aborted and logged). Every page.goto(new URL("…", APP_URL|BASE_URL)) of the
// specs is checked by the guard BEFORE the run (exit 3 when denied). Window: --headed/--headless > run-config
// browser.headed (rules.json) > SITE_QA_HEADLESS > visible, slow-mo as for every script (lib.js browserMode).
//   --expect fail — BEFORE the fix: every run must fail on the check of the defect (an expect(...) of the stub);
//                   a failure elsewhere (navigation, timeout, broken selector) does not count. Default --repeat-each 1.
//   --expect pass — AFTER the fix: every run must pass; default --repeat-each 3 (fix-cycle: three runs in a row).
//   test.fixme (stub without repro) never counts as a pass: finish the stub first.
// Output JSON: { ok, expect, reason?, stats, specs: [{ file, tests: [{ title, outcome, runs: [{ status, error? }] }] }],
//   blocked: [...guard records], headed, slowMo, browser }. Exit: 0 as expected, 1 not as expected, 2 bad input or
//   runner error, 3 an address of the specs is denied by the rules, 4 guard unavailable (no or broken rules.json).
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { parseArgs, loadRules, navAllowed, browserMode, writeOut, toUrl, GuardUnavailableError, tabs, closeTab } = require('./lib');

const SHIM = path.join(__dirname, 'e2e', 'shim');
const CONFIG = path.join(__dirname, 'e2e', 'playwright.config.js');
const CLI = path.join(path.dirname(require.resolve('playwright/package.json')), 'cli.js');

function fail(code, msg, extra = {}) {
  const e = new Error(msg); e.exitCode = code; e.extra = extra; return e;
}

// Addresses the specs open: page.goto(new URL("rel", APP_URL|BASE_URL …).href) and literal page.goto("…").
function gotoTargets(text, base) {
  const out = [];
  for (const m of text.matchAll(/new URL\(\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')\s*,\s*(?:APP_URL|BASE_URL)\b/g)) {
    let rel; try { rel = JSON.parse(m[1].startsWith("'") ? '"' + m[1].slice(1, -1).replace(/"/g, '\\"') + '"' : m[1]); } catch { continue; }
    try { out.push(new URL(rel, base).href); } catch { /* not a URL */ }
  }
  for (const m of text.matchAll(/page\.goto\(\s*(["'])((?:https?|file):[^"']+)\1/g)) out.push(m[2]);
  return [...new Set(out)];
}

// Report entries -> one row per test (file + title); repeats (--repeat-each) are separate entries in the report and
// become runs[] of the same row.
function collect(suite, file, acc) {
  for (const s of suite.specs || []) {
    const f = suite.file || file;
    for (const t of s.tests || []) {
      const runs = (t.results || []).map(r => ({ status: r.status, duration: r.duration,
        ...(r.error || (r.errors || [])[0] ? { error: String(((r.error || r.errors[0]).message || '')).replace(/\u001b\[[0-9;]*m/g, '').split('\n').slice(0, 3).join(' ').slice(0, 400) } : {}) }));
      let row = acc.find(x => x.file === f && x.title === s.title);
      if (!row) acc.push(row = { file: f, title: s.title, outcome: t.status, expectedStatus: t.expectedStatus, annotations: [], runs: [] });
      row.runs.push(...runs);
      for (const a of (t.annotations || []).map(x => x.type)) if (!row.annotations.includes(a)) row.annotations.push(a);
      if (t.status !== 'expected') row.outcome = t.status;
    }
  }
  for (const c of suite.suites || []) collect(c, suite.file || file, acc);
}

// A failure «on the defect»: an assertion of the stub, not a navigation error / timeout / missing element.
const isAssertion = (r) => (r.status === 'failed' || r.status === 'timedOut') && /expect\(|toBeFalsy|toBeHidden|toBeNull|дефект/.test(r.error || '') &&
  !/page\.goto|net::|timeout of \d+ms exceeded|Timeout \d+ms exceeded/i.test(r.error || '');

function verdict(expect, tests) {
  const real = tests.filter(t => !(t.annotations || []).includes('fixme') && t.outcome !== 'skipped');
  if (!tests.length) return { ok: false, reason: 'тестов не найдено (файл не похож на заготовку Playwright)' };
  if (!real.length) return { ok: false, reason: 'только test.fixme / пропущенные: в заготовке нет проверки — довести до рабочей' };
  if (expect === 'pass') {
    const bad = real.filter(t => t.runs.some(r => r.status !== 'passed'));
    return bad.length ? { ok: false, reason: `не прошли (${bad.length}): ` + bad.map(t => `${t.title}: ${(t.runs.find(r => r.status !== 'passed') || {}).error || t.outcome}`).join('; ') }
      : { ok: true };
  }
  const passed = real.filter(t => t.runs.some(r => r.status === 'passed'));
  if (passed.length) return { ok: false, reason: 'тест проходит до исправления — дефект не воспроизводится или проверка неверна: ' + passed.map(t => t.title).join('; ') };
  const other = real.filter(t => t.runs.some(r => !isAssertion(r)));
  return other.length ? { ok: false, reason: 'упал не на проверке дефекта: ' + other.map(t => `${t.title}: ${(t.runs.find(r => !isAssertion(r)) || {}).error || t.outcome}`).join('; ') }
    : { ok: true };
}

async function main() {
  const argv = process.argv.slice(2);
  const a = parseArgs(argv, { expect: 'pass', timeout: '30000' });
  const specs = a._.map(s => path.resolve(s));
  if (!specs.length) throw fail(2, 'нужен файл заготовки: node e2e_run.js F-001.spec.ts --rules <RUN_DIR>/rules.json --app-url file:///…/app/');
  for (const s of specs) if (!fs.existsSync(s) || !/\.(spec|test)\.[cm]?[jt]s$/.test(s)) throw fail(2, `нет файла заготовки *.spec.ts|js: ${s}`);
  if (!['fail', 'pass'].includes(a.expect)) throw fail(2, '--expect fail|pass');
  if (!a.rules) throw new GuardUnavailableError('нужен --rules <RUN_DIR>/rules.json: заготовки запускаются только под guard прогона');
  const rules = loadRules(a.rules);
  const appUrl = a['app-url'] && a['app-url'] !== true ? toUrl(String(a['app-url'])) : null;
  const baseUrl = a['base-url'] && a['base-url'] !== true ? String(a['base-url']) : null;
  if (!appUrl && !baseUrl) throw fail(2, 'нужен --app-url file:///…/папка-приложения/ или --base-url https://…');
  const app = appUrl ? (appUrl.endsWith('/') ? appUrl : appUrl + '/') : null;
  // guard before the run: every address the specs open
  const checks = [];
  for (const s of specs) {
    const text = fs.readFileSync(s, 'utf8');
    const base = /APP_URL/.test(text) ? app : baseUrl;
    if (!base) throw fail(2, `${path.basename(s)}: заготовка ждёт ${/APP_URL/.test(text) ? '--app-url' : '--base-url'}`);
    for (const u of gotoTargets(text, base).concat([base])) {
      const v = navAllowed(u, rules);
      checks.push({ url: u, ok: v.ok, ...(v.ok ? {} : { rule: v.rule, reason: v.reason }) });
    }
  }
  const denied = checks.filter(c => !c.ok);
  if (denied.length) throw fail(3, 'адрес заготовки запрещён правилами прогона: ' + denied.map(d => `${d.url} (${d.rule || d.reason})`).join('; '), { checks });

  const mode = browserMode(rules);
  const repeat = Math.max(1, +(a['repeat-each'] || (a.expect === 'pass' ? 3 : 1)) || 1);
  const tmp = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'sqa-e2e-')));
  const names = new Map();
  for (const s of specs) {
    let n = path.basename(s);
    if (names.has(n)) n = `${names.size}-${n}`;
    names.set(n, s);
    fs.copyFileSync(s, path.join(tmp, n));
  }
  const report = path.join(tmp, 'report.json');
  const env = { ...process.env,
    NODE_PATH: [SHIM, process.env.NODE_PATH].filter(Boolean).join(path.delimiter),
    SITE_QA_E2E_DIR: tmp, SITE_QA_E2E_REPORT: report, SITE_QA_E2E_RULES: path.resolve(a.rules),
    SITE_QA_E2E_LOG: a.log && a.log !== true ? path.resolve(String(a.log)) : '',
    SITE_QA_E2E_HEADLESS: mode.headless ? '1' : '0', SITE_QA_E2E_SLOWMO: String(mode.slowMo),
    SITE_QA_E2E_BROWSER: a.browser && a.browser !== true ? String(a.browser) : '', SITE_QA_E2E_TIMEOUT: String(+a.timeout || 30000),
    ...(app ? { APP_URL: app } : {}), ...(baseUrl ? { BASE_URL: baseUrl } : {}) };
  delete env.PLAYWRIGHT_JSON_OUTPUT_NAME;
  const t0 = Date.now();
  // tabs.json of the run: one record for the browsers of Playwright Test (they live in its worker process)
  const reg = tabs();
  const tabId = reg ? reg.open({ profile: 'e2e', tool: 'node', url: (checks[0] || {}).url || null, engine: env.SITE_QA_E2E_BROWSER || 'playwright-test' }) : null;
  let r;
  try {
    r = spawnSync(process.execPath, [CLI, 'test', '--config', CONFIG, '--repeat-each', String(repeat)],
      { cwd: tmp, env, encoding: 'utf8', timeout: (+a.timeout || 30000) * repeat * specs.length + 120000 });
  } finally { closeTab(tabId); }
  let data = null;
  try { data = JSON.parse(fs.readFileSync(report, 'utf8')); } catch { /* no report */ }
  const blocked = [];
  if (env.SITE_QA_E2E_LOG && fs.existsSync(env.SITE_QA_E2E_LOG)) {
    for (const line of fs.readFileSync(env.SITE_QA_E2E_LOG, 'utf8').split('\n').filter(Boolean)) {
      try { const x = JSON.parse(line); if (Date.parse(x.ts) >= t0 - 1000 && x.decision !== 'allow') blocked.push({ url: x.url, rule: x.rule, reason: x.reason }); } catch { /* skip */ }
    }
  }
  if (!a.keep) fs.rmSync(tmp, { recursive: true, force: true });
  if (!data) throw fail(2, 'Playwright Test не выдал отчёт: ' + ((r.stderr || '') + (r.stdout || '')).replace(/\u001b\[[0-9;]*m/g, '').trim().split('\n').slice(-6).join(' | ').slice(0, 600));
  const tests = [];
  for (const s of data.suites || []) collect(s, s.file, tests);
  for (const t of tests) t.file = names.get(path.basename(t.file || '')) || t.file;
  const v = verdict(a.expect, tests);
  const errors = (data.errors || []).map(e => String(e.message || '').replace(/\u001b\[[0-9;]*m/g, '').split('\n')[0]);
  if (errors.length && v.ok) Object.assign(v, { ok: false, reason: 'ошибки загрузки: ' + errors.join('; ') });
  const bySpec = specs.map(s => ({ file: s, tests: tests.filter(t => t.file === s).map(({ file, ...t }) => t) }));
  return { tool: 'e2e_run', expect: a.expect, ok: v.ok, ...(v.reason ? { reason: v.reason } : {}), repeatEach: repeat,
    browser: env.SITE_QA_E2E_BROWSER || 'по устройству заготовки (chromium)', headed: !mode.headless, slowMo: mode.slowMo, windowSource: mode.source,
    stats: data.stats ? { expected: data.stats.expected, unexpected: data.stats.unexpected, flaky: data.stats.flaky, skipped: data.stats.skipped, durationMs: Math.round(data.stats.duration || 0) } : null,
    specs: bySpec, checked: checks, blocked, ...(errors.length ? { errors } : {}) };
}

if (require.main === module) {
  main().then(res => {
    const a = parseArgs(process.argv.slice(2));
    writeOut(a.out, res);
    process.stderr.write(`e2e_run: ${res.ok ? 'как ожидалось' : 'НЕ как ожидалось'} (--expect ${res.expect}, повторов ${res.repeatEach})` + (res.reason ? ': ' + res.reason : '') + '\n');
    process.exit(res.ok ? 0 : 1);
  }).catch(e => {
    const code = (e && e.exitCode) || 2;
    console.log(JSON.stringify({ tool: 'e2e_run', ok: false, error: String(e.message || e), ...(e.extra || {}) }, null, 1));
    console.error(String(e.message || e));
    process.exit(code);
  });
}

module.exports = { gotoTargets, verdict, isAssertion };
