'use strict';
// Safety rules applied directly to Playwright actions (references/browser-guard.md).
//
//   const { loadGuardRules, guardContext, guardedPage } = require('./guard');
//   const rules = loadGuardRules('<RUN_DIR>/rules.json');            // url_guard.py export --out rules.json
//   await guardContext(context, rules, { logFile: '<RUN_DIR>/logs/blocked.jsonl' });
//   const g = guardedPage(page, rules, { logFile: ... });
//   await g.goto(url); await g.click('text=Поддержать');            // deny -> skipped + logged
//
// guardContext: route-level block of forbidden resources, main-frame navigation outside the rules,
//   forbidden iframe documents; closes popups/tabs that go to foreign domains; dismisses native dialogs.
// guardedPage: wraps click / dblclick / fill / check / uncheck / selectOption / setInputFiles / press / goto.
//   Before the action it reads role, accessible name, visible text and nearby context of the element and asks
//   url_guard.check_action (the same Python code as `url_guard.py action`, through a stdin bridge).
//   allow -> performed; deny -> skipped, written to blocked.jsonl; confirm -> GuardConfirmError (stop + question),
//   unless opts.onConfirm(decision) resolves to true.
//   FAIL CLOSED: the bridge failed (no Python, url_guard.py missing, broken rules, bad answer) -> decision
//   'unavailable' -> GuardUnavailableError (exitCode 4): nothing is clicked or navigated, the run stops.
//   opts.readOnly (S-8, `nav --read-only`): goto may open read-only pages; every click/fill/check/... is denied.
//
// CLI (manual check of one element on a page):
//   node guard.js check --url URL --selector "text=Поддержать" --rules rules.json [--log blocked.jsonl]
const path = require('path');
const { execFile } = require('child_process');
const { parseArgs, loadRules, navAllowed, resourceBlocked, appendJsonl, sleep, GuardUnavailableError, launchOptions } = require('./lib');
const { locate } = require('./frames');

const SCRIPTS_DIR = path.join(__dirname, '..');
const PY = process.env.SITE_QA_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');

// Python bridge: exact url_guard.check_action / check_url decisions for a batch of queries.
const BRIDGE = `
import json, sys
sys.path.insert(0, sys.argv[1])
import url_guard
req = json.loads(sys.stdin.read())
cfg = req["cfg"]
out = []
for q in req["queries"]:
    if q["kind"] == "action":
        out.append(url_guard.check_action(q.get("text") or "", cfg, q.get("role"), q.get("selector"),
                                          q.get("url"), q.get("context"), q.get("name")))
    else:
        out.append(url_guard.check_url(q["url"], cfg, q["kind"], read_only=bool(q.get("read_only"))))
sys.stdout.write(json.dumps(out, ensure_ascii=False))
`;
const KNOWN = new Set(['allow', 'confirm', 'deny']);
// Test hook only: SITE_QA_GUARD_PY_DIR points the bridge at another scripts folder (e.g. a missing one).
const bridgeDir = () => process.env.SITE_QA_GUARD_PY_DIR || SCRIPTS_DIR;

function cfgFromRules(rules) {
  const r = (rules && rules.rules) || {};
  return {
    site: { allowed_domains: r.allowed_domains || [] },
    scope: { exclude_patterns: r.exclude_patterns || [] },
    rules: {
      forbidden_domains: r.forbidden_domains || [], forbidden_url_patterns: r.forbidden_url_patterns || [],
      forbidden_actions: r.forbidden_actions || [], require_confirmation_actions: r.require_confirmation_actions || [],
      preapproved_actions: r.preapproved_actions || [], read_only_urls: r.read_only_urls || [],
    },
  };
}

function pyCheck(rules, queries) {
  return new Promise((resolve) => {
    // Fail closed: any failure of the bridge is «unavailable» (stop), never allow and never a plain question.
    const unavailable = (reason) => resolve(queries.map(q => ({ decision: 'unavailable', kind: q.kind, target: q,
      reason: 'guard недоступен — СТОП: ' + reason, rule: 'guard:unavailable' })));
    let child;
    try {
      child = execFile(PY, ['-c', BRIDGE, bridgeDir()], { encoding: 'utf8', timeout: 20000 }, (err, stdout, stderr) => {
        if (err) return unavailable('url_guard: ' + String(stderr || err.message).trim().split('\n').pop());
        let out;
        try { out = JSON.parse(stdout); } catch { return unavailable('url_guard: неверный ответ'); }
        if (!Array.isArray(out) || out.length !== queries.length || out.some(d => !d || !KNOWN.has(d.decision)))
          return unavailable('url_guard: ответ не совпадает с запросом');
        resolve(out);
      });
    } catch (e) { return unavailable('не удалось запустить ' + PY + ': ' + e.message); }
    child.on('error', (e) => unavailable('не удалось запустить ' + PY + ': ' + e.message));
    child.stdin.on('error', () => { /* reported by the exit callback */ });
    child.stdin.end(JSON.stringify({ cfg: cfgFromRules(rules), queries }));
  });
}

const checkAction = async (rules, q) => (await pyCheck(rules, [{ kind: 'action', ...q }]))[0];
const checkUrl = async (rules, url, kind = 'nav', opts = {}) => (await pyCheck(rules, [{ kind, url, read_only: !!opts.readOnly }]))[0];

function loadGuardRules(file) { return loadRules(file); }

function normalizeOpts(opts) {
  if (Array.isArray(opts)) return { log: opts };
  return opts || {};
}

// ---- context level -------------------------------------------------------------------------------------
async function guardContext(context, rules, opts = {}) {
  opts = normalizeOpts(opts);
  const log = opts.log || [];
  const record = (ev) => { log.push(ev); appendJsonl(opts.logFile, ev); if (opts.onEvent) opts.onEvent(ev); };
  const popups = new WeakSet();
  if (!rules) return { log };

  const ro = { readOnly: !!opts.readOnly };
  await context.route('**/*', async (route) => {
    const req = route.request();
    const url = req.url();
    let isNav = false;
    try {
      isNav = req.isNavigationRequest();
      // Read-only mode: nothing is sent to the site — only GET/HEAD/OPTIONS requests pass.
      if (ro.readOnly && !/^(GET|HEAD|OPTIONS)$/i.test(req.method())) {
        record({ type: isNav ? 'nav' : 'resource', decision: 'deny', url, rule: 'read-only', reason: `режим только чтения: ${req.method()} не отправляется` });
        return route.abort('blockedbyclient');
      }
      if (!isNav && resourceBlocked(url, rules)) {
        record({ type: 'resource', decision: 'deny', url, reason: 'forbidden_domains / base blocked_origins' });
        return route.abort('blockedbyclient');
      }
      if (isNav) {
        let frame = null;
        try { frame = req.frame(); } catch { frame = null; }
        if (!frame) {
          // The first navigation of a new tab/popup (window.open, target=_blank): the frame does not exist yet.
          const v0 = navAllowed(url, rules, 'nav', ro);
          if (!v0.ok) {
            record({ type: 'tab', decision: 'deny', url, reason: v0.reason, rule: v0.rule });
            await route.abort('blockedbyclient');
            setTimeout(async () => {
              for (const p of context.pages()) {
                const u = p.url();
                if ((!u || u === 'about:blank' || u === url) && await p.opener().catch(() => null)) p.close().catch(() => {});
              }
            }, 300);
            return;
          }
          return route.continue();
        }
        const main = frame === frame.page().mainFrame();
        let v = navAllowed(url, rules, main ? 'nav' : 'subframe', ro);
        if (v.ok && resourceBlocked(url, rules)) v = { ok: false, reason: 'base blocked_origins', rule: 'base:blocked-origin' };
        if (!v.ok) {
          const page = frame.page();
          const isPopup = main && (popups.has(page) || !!(await page.opener().catch(() => null)));
          record({ type: isPopup ? 'tab' : main ? 'nav' : 'subframe', decision: 'deny', url, reason: v.reason, rule: v.rule });
          await route.abort('blockedbyclient');
          if (isPopup) page.close().catch(() => {});
          return;
        }
      }
    } catch (e) {
      if (process.env.QA_GUARD_DEBUG) console.error('guard route error', url, e.message);
      // Fail closed for navigations: a rule error is never a pass.
      if (isNav) {
        record({ type: 'nav', decision: 'unavailable', url, rule: 'guard:unavailable', reason: 'ошибка правил: ' + e.message });
        return route.abort('blockedbyclient').catch(() => {});
      }
    }
    return route.continue();
  });

  const onPage = async (page) => {
    page.on('dialog', d => { record({ type: 'dialog', decision: 'dismissed', url: page.url(), reason: d.message().slice(0, 200) }); d.dismiss().catch(() => {}); });
    const opener = await page.opener().catch(() => null);
    if (opener) {
      popups.add(page);
      // A popup that is already on a foreign URL (e.g. opened before routing) is closed right away.
      const u = page.url();
      if (/^chrome-error:/.test(u)) { page.close().catch(() => {}); return; }  // error page of a blocked popup
      if (u && u !== 'about:blank') {
        const v = navAllowed(u, rules, 'nav');
        if (!v.ok) { record({ type: 'tab', decision: 'deny', url: u, reason: v.reason, rule: v.rule }); page.close().catch(() => {}); }
      }
    }
  };
  context.on('page', onPage);
  for (const p of context.pages()) p.on('dialog', d => { record({ type: 'dialog', decision: 'dismissed', url: p.url(), reason: d.message().slice(0, 200) }); d.dismiss().catch(() => {}); });
  return { log };
}

// ---- element description (role, accessible name, text, context) ------------------------------------------
function describeInPage(el) {
  const tag = el.tagName.toLowerCase();
  const BTN = ['button', 'submit', 'reset', 'image'];
  let role = el.getAttribute('role');
  if (!role) {
    if (tag === 'input') {
      const t = (el.getAttribute('type') || 'text').toLowerCase();
      role = { checkbox: 'checkbox', radio: 'radio', button: 'button', submit: 'button', reset: 'button', image: 'button',
        file: 'button', range: 'slider', search: 'searchbox' }[t] || 'textbox';
    } else role = { a: el.hasAttribute('href') ? 'link' : null, button: 'button', select: 'combobox', textarea: 'textbox',
      summary: 'button', option: 'option' }[tag] || null;
  }
  const squash = s => String(s || '').replace(/\s+/g, ' ').trim();
  const byIds = ids => ids.split(/\s+/).map(id => document.getElementById(id)).filter(Boolean).map(e => e.innerText || e.textContent).join(' ');
  let name = el.getAttribute('aria-label') || (el.getAttribute('aria-labelledby') ? byIds(el.getAttribute('aria-labelledby')) : '');
  if (!name && el.labels && el.labels.length) name = [...el.labels].map(l => l.innerText || l.textContent).join(' ');
  if (!name) name = el.getAttribute('title') || el.getAttribute('alt') || '';
  if (!name && tag === 'input' && BTN.includes((el.type || '').toLowerCase())) name = el.value;
  let text = tag === 'input' ? (BTN.includes((el.type || '').toLowerCase()) ? el.value : '') : (el.innerText || el.textContent || '');
  const box = el.closest('dialog,[role=dialog],[role=alertdialog],form,fieldset,section,article,nav,aside,header,footer,main,[aria-label]');
  const parts = [];
  if (box && box !== el) {
    const h = box.querySelector('h1,h2,h3,h4,legend,[role=heading]');
    parts.push(box.getAttribute('aria-label'), h && h.innerText, (box.innerText || '').slice(0, 300));
  } else if (el.parentElement) parts.push((el.parentElement.innerText || '').slice(0, 300));
  parts.push(document.title);
  const a = el.closest('a[href]');
  return { tag, role, name: squash(name).slice(0, 200), text: squash(text).slice(0, 200),
    context: squash(parts.filter(Boolean).join(' | ')).slice(0, 600), href: a ? a.href : null,
    checked: 'checked' in el ? !!el.checked : null, docUrl: location.href };
}

class GuardConfirmError extends Error {
  constructor(decision) {
    super('Нужно подтверждение пользователя: ' + decision.reason);
    this.name = 'GuardConfirmError';
    this.decision = decision;
    this.question = decision.question;
  }
}

function questionFor(action, info, d) {
  const what = info.text || info.name || info.selector;
  return `Действие «${action}» по элементу «${what}» (${info.role || info.tag || 'элемент'}) требует подтверждения: ${d.reason}. Выполнить один раз / пропустить / разрешить такой класс действий в этом прогоне?`;
}

// ---- page wrapper -----------------------------------------------------------------------------------------
function guardedPage(page, rules, opts = {}) {
  const log = opts.log || [];
  const throttle = opts.throttleMs !== undefined ? +opts.throttleMs : ((rules && rules.throttle_ms) || 0);
  const record = (ev) => { log.push(ev); appendJsonl(opts.logFile, ev); if (opts.onEvent) opts.onEvent(ev); };
  const sideEffects = opts.sideEffects || [];
  const readOnly = !!opts.readOnly;
  const stop = (ev) => { record(ev); throw new GuardUnavailableError(ev.reason, ev); };

  async function decide(action, target, extra = {}) {
    const loc = typeof target === 'string' ? locate(page, target) : target;
    const selector = typeof target === 'string' ? target : String(target);
    const handle = await loc.first().elementHandle({ timeout: opts.timeout || 5000 });
    const info = { selector, ...(await handle.evaluate(describeInPage)) };
    // Read-only mode (nav --read-only): reading the page is allowed, any action is not.
    if (readOnly) return { loc, handle, info, d: { decision: 'deny', rule: 'read-only', reason: 'режим только чтения: действия на странице запрещены' } };
    // A guarded action that hits a declared side effect must go through invariants.js (runSideEffect).
    if (!extra.viaSideEffect) {
      for (const se of sideEffects) {
        if (!se.target || String(se.target).includes('>>>')) continue;
        const hit = se.target === selector || await handle.evaluate((e, s) => { try { return e.matches(s); } catch { return false; } }, se.target);
        if (hit) {
          const d = { decision: 'confirm', kind: 'action', target: info, rule: `side_effect:${se.id}`,
            reason: `действие с побочным эффектом ${se.id} (${se.effect || se.label || ''}) — выполнять через invariants.js exec` };
          return { loc, handle, info, d };
        }
      }
    }
    if (!rules) return { loc, handle, info, d: { decision: 'allow', reason: 'rules.json не задан', rule: null } };
    let d = await checkAction(rules, { text: info.text, name: info.name, role: info.role, selector, url: info.docUrl, context: info.context });
    // A link click is also a navigation: check its destination as `nav`.
    if (d.decision === 'allow' && info.href && action === 'click') {
      const n = await checkUrl(rules, info.href, 'nav');
      if (n.decision === 'deny' || n.decision === 'unavailable') d = { ...n, kind: 'action', reason: (n.decision === 'deny' ? 'ссылка ведёт на запрещённый адрес: ' : '') + n.reason };
    }
    // Typing into a field does not send anything: confirm-level categories (send-to-people, destructive) apply
    // to the button that submits, not to the field. Deny still applies.
    if (extra.fillLike && d.decision === 'confirm') d = { ...d, decision: 'allow', reason: 'ввод в поле (подтверждение — на отправке): ' + d.reason };
    return { loc, handle, info, d };
  }

  async function guarded(action, target, run, extra = {}) {
    if (throttle) await sleep(throttle);
    const { loc, handle, info, d } = await decide(action, target, extra);
    await handle.dispose().catch(() => {});
    const ev = { type: 'action', action, decision: d.decision, rule: d.rule, reason: d.reason, url: page.url(),
      element: { selector: info.selector, role: info.role, name: info.name, text: info.text } };
    if (d.decision === 'unavailable' || !['allow', 'confirm', 'deny'].includes(d.decision)) stop({ ...ev, decision: 'unavailable', rule: 'guard:unavailable' });
    if (d.decision === 'deny') { record(ev); return { performed: false, ...ev }; }
    if (d.decision === 'confirm') {
      const question = questionFor(action, info, d);
      const approved = opts.onConfirm ? await opts.onConfirm({ ...ev, question }) : false;
      if (!approved) {
        record({ ...ev, question });
        if (opts.confirmMode === 'return') return { performed: false, ...ev, question };
        throw new GuardConfirmError({ ...ev, question });
      }
      record({ ...ev, decision: 'confirm-approved' });
    }
    await run(loc.first());
    if (opts.logAllowed) record(ev);
    return { performed: true, ...ev };
  }

  const g = {
    page, log, readOnly,
    click: (t, o) => guarded('click', t, l => l.click(o)),
    dblclick: (t, o) => guarded('dblclick', t, l => l.dblclick(o)),
    check: (t, o) => guarded('check', t, l => l.check(o)),
    uncheck: (t, o) => guarded('uncheck', t, l => l.uncheck(o)),
    press: (t, key, o) => guarded('press ' + key, t, l => l.press(key, o), { fillLike: !/^enter$/i.test(key) }),
    fill: (t, v, o) => guarded('fill', t, l => l.fill(v, o), { fillLike: true }),
    selectOption: (t, v, o) => guarded('selectOption', t, l => l.selectOption(v, o)),
    setInputFiles: (t, files, o, extra = {}) => guarded('setInputFiles', t, l => l.setInputFiles(files, o), extra),
    async goto(url, o) {
      let first = null;
      if (rules) {
        first = await checkUrl(rules, url, 'nav', { readOnly });
        const ev = { type: 'nav', decision: first.decision, rule: first.rule, reason: first.reason, url };
        if (first.decision === 'unavailable' || !['allow', 'confirm', 'deny'].includes(first.decision)) stop({ ...ev, decision: 'unavailable', rule: 'guard:unavailable' });
        if (first.decision !== 'allow') { record(ev); return { performed: false, ...ev }; }
        if (first.read_only) record({ type: 'read-only', decision: 'allow', rule: first.rule, url, reason: 'прочитано без действий' });
      }
      await page.goto(url, o);
      // Redirect check (safety-rules §3.5): the final URL must also pass.
      if (rules && page.url() !== url) {
        const d2 = await checkUrl(rules, page.url(), 'nav', { readOnly });
        if (d2.decision === 'unavailable') { await page.goBack().catch(() => {}); stop({ type: 'redirect', decision: 'unavailable', rule: 'guard:unavailable', reason: d2.reason, url: page.url(), from: url }); }
        if (d2.decision === 'deny') { record({ type: 'redirect', decision: 'deny', rule: d2.rule, reason: d2.reason, url: page.url(), from: url }); await page.goBack().catch(() => {}); return { performed: false, ...d2 }; }
      }
      return { performed: true, decision: 'allow', url: page.url(), ...(first && first.read_only ? { readOnly: true } : {}) };
    },
    locator: (s) => locate(page, s),
  };
  return g;
}

module.exports = { guardContext, guardedPage, checkAction, checkUrl, loadGuardRules, GuardConfirmError, GuardUnavailableError, describeInPage, cfgFromRules };

if (require.main === module) {
  (async () => {
    const a = parseArgs(process.argv.slice(2));
    if (a._[0] !== 'check' || !a.url || !a.selector) {
      console.error('node guard.js check --url URL --selector SEL --rules rules.json [--log blocked.jsonl] [--browser chromium]');
      process.exit(1);
    }
    const pw = require('playwright');
    const rules = loadRules(a.rules);
    if (!rules) throw new GuardUnavailableError('нужен --rules <RUN_DIR>/rules.json');
    const browser = await pw[a.browser || 'chromium'].launch(launchOptions({ headless: true }));
    let res;
    try {
      const context = await browser.newContext();
      await guardContext(context, rules, { logFile: a.log });
      const page = await context.newPage();
      const g = guardedPage(page, rules, { logFile: a.log, throttleMs: 0 });
      const nav = await g.goto(a.url, { waitUntil: 'load' });
      res = nav;
      if (nav.performed) {
        const loc = locate(page, a.selector).first();
        const h = await loc.elementHandle({ timeout: 5000 });
        const info = await h.evaluate(describeInPage);
        res = { element: info, decision: await checkAction(rules, { text: info.text, name: info.name, role: info.role, selector: a.selector, url: info.docUrl, context: info.context }) };
      }
    } finally { await browser.close(); }
    console.log(JSON.stringify(res, null, 2));
    const dec = typeof res.decision === 'string' ? res.decision : res.decision.decision;
    process.exit({ deny: 3, confirm: 2, unavailable: 4, allow: 0 }[dec] ?? 4);
  })().catch(e => { console.error(String(e.message || e)); process.exit((e && e.exitCode) || 1); });
}
