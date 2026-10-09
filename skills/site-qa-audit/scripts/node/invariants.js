'use strict';
// Side effects and invariants (references/side-effects.md).
// run-config.yaml:
//   side_effects:            # actions with consequences outside the test (public rating, mailing, account link…)
//     - id: SE1
//       action: upload       # upload | click | check
//       target: "#upload"    # selector (">>>" enters iframes)
//       effect: "сохранение попадает в публичный рейтинг без флажка «Чужое сохранение»"
//       leaves: ["локальная копия сохранения в браузере (localStorage)"]
//   invariants:
//     - id: INV1
//       after: SE1           # side effect id (or action type: upload | click | check)
//       within_ms: 5000
//       require:
//         role: checkbox     # checkbox | button | … (optional)
//         name: "Чуж(ой|ое)" # regex on the accessible name / label (case-insensitive)
//         selector: null     # alternative to role+name
//         state: checked     # present | checked | unchecked | absent
//         ensure: false      # true: the runner ticks it itself (guarded) if it appeared unchecked
//         only_after_action: true   # must NOT exist before the action
//       vocabulary: "Чужое сохранение"   # exact label seen last time (preflight compares)
//       else: abort          # abort (stop, exit 3) | warn
//     - id: INV2             # a DIALOG OF RADIO BUTTONS after the action (G-2), e.g. «Моё / Чужое» + «Запомнить / Не сейчас»
//       after: SE1
//       within_ms: 20000     # how long to wait for the first radio
//       dialog:
//         choose:            # in this order; each: role radio (role=radio / input[type=radio]) by name regex or selector
//           - name: "Чуж(ой|ое)"
//           - name: "Не сейчас"
//         confirm:           # button that applies the choice; pressed only after EVERY choice reads as checked
//           role: button
//           name: "^Готово$"
//         then:              # what must be true after the confirmation (same fields as require)
//           role: checkbox
//           name: "Чуж(ой|ое)"
//           state: checked
//           within_ms: 10000
//       vocabulary: "Чужое сохранение"   # compared with the label found by `then`
//       else: abort
//     A radio is «checked» by aria-checked="true" or the checked property. If a radio does not appear, does not become
//     checked after the click, or `then` fails — the run stops (exit 3) and the confirm button is NOT pressed.
//
// Commands:
//   node invariants.js preflight --config run-config.yaml --url URL --run-dir DIR [--prev-vocab old/vocabulary.json]
//        Checks the interface vocabulary of protective elements against the config and the previous run.
//        Exit 0 ok, 2 mismatch -> stop and ask the user (question in JSON).
//   node invariants.js exec --config run-config.yaml --effect SE1 --url URL --run-dir DIR [--file path]
//        [--rules rules.json] [--cdp URL] [--setup setup.js] [--prev-vocab …]
//        preflight -> guarded action -> watch invariants -> side_effects.md entry. Exit 0 ok, 2 confirm/vocab, 3 abort.
//   node invariants.js log --run-dir DIR --what "…" [--effect SE1] [--result "…"] [--left "…"]
//        Manual entry (actions done through MCP or by hand).
// API: runSideEffect(page, guarded, cfg, effectId, { file, runDir, prevVocab }) -> result
const fs = require('fs');
const path = require('path');
const { parseArgs, loadRules, loadRunConfig, toUrl } = require('./lib');
const { locate, listFrames } = require('./frames');

const LOG_HEADER = '# Побочные эффекты прогона\n\nЧто загружено, включено и что осталось в браузере или на сайте после действий прогона.\n\n' +
  '| Время | Эффект | Действие | Результат | Инвариант | Что осталось |\n|---|---|---|---|---|---|\n';
const cell = (s) => String(s == null ? '' : s).replace(/\|/g, '\\|').replace(/\r?\n/g, ' ');

function logSideEffect(runDir, e) {
  const file = path.join(runDir, 'side_effects.md');
  fs.mkdirSync(runDir, { recursive: true });
  if (!fs.existsSync(file)) fs.writeFileSync(file, LOG_HEADER);
  const row = [new Date().toISOString().replace('T', ' ').slice(0, 19), e.effect, e.what, e.result, e.invariant, e.left].map(cell);
  fs.appendFileSync(file, '| ' + row.join(' | ') + ' |\n');
  return file;
}

// Find the protective element in every frame: by selector, or by role + accessible-name regex.
async function findRequired(page, req) {
  if (req.selector) {
    const loc = locate(page, req.selector).first();
    if (!(await loc.count())) return null;
    return loc.evaluate((e) => ({ label: (e.labels && e.labels[0] ? e.labels[0].innerText : e.getAttribute('aria-label') || e.innerText || '').trim(),
      checked: 'checked' in e ? !!e.checked : (e.getAttribute('aria-checked') === 'true' ? true : e.getAttribute('aria-checked') === 'false' ? false : null),
      visible: !!(e.offsetWidth || e.offsetHeight) })).then(i => ({ ...i, locator: loc }));
  }
  for (const f of await listFrames(page, 'all')) {
    const hit = await f.frame.evaluate(({ role, name }) => {
      const rx = new RegExp(name || '.', 'i');
      const roleOf = (e) => e.getAttribute('role') || (e.tagName === 'INPUT' ? ({ checkbox: 'checkbox', radio: 'radio', button: 'button', submit: 'button' }[e.type] || 'textbox') : e.tagName === 'BUTTON' ? 'button' : e.tagName === 'A' ? 'link' : null);
      const nameOf = (e) => (e.getAttribute('aria-label') || (e.labels && e.labels.length ? [...e.labels].map(l => l.innerText).join(' ') : '') || e.innerText || e.value || '').replace(/\s+/g, ' ').trim();
      const all = [...document.querySelectorAll('input,button,a,select,textarea,[role]')];
      const i = all.findIndex(e => (!role || roleOf(e) === role) && rx.test(nameOf(e)));
      if (i < 0) return null;
      const e = all[i];
      document.querySelectorAll('[data-qa-inv]').forEach(x => x.removeAttribute('data-qa-inv'));
      e.setAttribute('data-qa-inv', '1');
      const aria = e.getAttribute('aria-checked');
      return { label: nameOf(e), checked: 'checked' in e ? !!e.checked : aria === 'true' ? true : aria === 'false' ? false : null,
        visible: !!(e.offsetWidth || e.offsetHeight) };
    }, { role: req.role || null, name: req.name || null }).catch(() => null);
    if (hit) {
      const loc = f.frame.locator('[data-qa-inv="1"]').first();
      return { ...hit, locator: loc };
    }
  }
  return null;
}

function invariantsFor(cfg, effect) {
  return (cfg.invariants || []).filter(i => i.after === effect.id || i.after === effect.action);
}

function readVocab(file) { try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return null; } }

// Compare an observed label with the configured vocabulary and with the previous run.
function vocabProblem(inv, observed, prev) {
  if (observed == null) return null;
  const expected = inv.vocabulary;
  const last = prev && prev[inv.id] && prev[inv.id].observed;
  if (expected && observed !== expected) return { id: inv.id, expected, observed, previous: last || null };
  if (last && observed !== last) return { id: inv.id, expected: expected || null, observed, previous: last };
  return null;
}

function vocabQuestion(p) {
  return `Защитный элемент ${p.id} называется «${p.observed}», а ожидалось «${p.expected || p.previous}»` +
    (p.previous && p.previous !== p.expected ? ` (в прошлом прогоне — «${p.previous}»)` : '') +
    '. Это тот же элемент и та же защита? Варианты: обновить словарь и продолжить / остановиться и проверить вручную.';
}

async function preflight(page, cfg, { runDir, prevVocab, effectId } = {}) {
  const prev = prevVocab ? readVocab(prevVocab) : null;
  const vocabFile = runDir ? path.join(runDir, 'vocabulary.json') : null;
  const vocab = (vocabFile && readVocab(vocabFile)) || {};
  const problems = [], checks = [];
  const effects = (cfg.side_effects || []).filter(e => !effectId || e.id === effectId);
  for (const se of effects) {
    for (const inv of invariantsFor(cfg, se)) {
      if (inv.dialog) {
        // A dialog appears only after the action: its first radio must not be there yet.
        const first = (inv.dialog.choose || [])[0];
        const early = first ? await findRequired(page, { role: first.role || 'radio', name: first.name, selector: first.selector }) : null;
        checks.push({ id: inv.id, before: early ? 'диалог уже открыт до действия' : 'диалога нет до действия (ожидаемо)' });
        if (early) problems.push({ id: inv.id, kind: 'present-before', observed: early.label,
          question: `Вариант «${early.label}» диалога ${inv.id} виден до действия ${se.id}. Интерфейс изменился? Проверить вручную перед действием.` });
        continue;
      }
      const req = inv.require || {};
      const found = await findRequired(page, req);
      if (req.only_after_action) {
        checks.push({ id: inv.id, before: found ? 'есть до действия' : 'нет до действия (ожидаемо)' });
        if (found) problems.push({ id: inv.id, kind: 'present-before', observed: found.label,
          question: `Элемент ${inv.id} («${found.label}») уже есть до действия ${se.id}, а должен появляться только после него. Интерфейс изменился? Проверить вручную перед действием.` });
        continue;
      }
      if (!found) {
        if (req.state === 'absent') { checks.push({ id: inv.id, before: 'отсутствует (ожидаемо)' }); continue; }
        problems.push({ id: inv.id, kind: 'not-found', question: `Защитный элемент ${inv.id} (${req.selector || `${req.role || ''} /${req.name}/`}) не найден до действия ${se.id}. Интерфейс изменился? Действие не выполняется.` });
        continue;
      }
      vocab[inv.id] = { observed: found.label, when: 'preflight', at: new Date().toISOString() };
      const p = vocabProblem(inv, found.label, prev);
      checks.push({ id: inv.id, label: found.label, checked: found.checked });
      if (p) problems.push({ ...p, kind: 'vocabulary', question: vocabQuestion(p) });
    }
  }
  if (vocabFile) { fs.mkdirSync(runDir, { recursive: true }); fs.writeFileSync(vocabFile, JSON.stringify(vocab, null, 2)); }
  return { ok: problems.length === 0, checks, problems };
}

async function watch(page, inv, { guarded }) {
  const req = inv.require || {};
  const until = Date.now() + (+inv.within_ms || 5000);
  let found = null;
  while (Date.now() < until) {
    found = await findRequired(page, req);
    if (req.state === 'absent') { if (!found) return { ok: true, detail: 'элемент отсутствует' }; }
    else if (found) break;
    await page.waitForTimeout(100);
  }
  if (req.state === 'absent') return { ok: false, detail: `элемент «${found && found.label}» не исчез за ${inv.within_ms} мс` };
  if (!found) return { ok: false, detail: `элемент ${req.selector || `${req.role || ''} /${req.name}/`} не появился за ${inv.within_ms} мс` };
  if (req.state === 'checked' && !found.checked && req.ensure) {
    const r = await guarded.check(found.locator);
    found = await findRequired(page, req) || found;
    if (!r.performed) return { ok: false, label: found.label, detail: `элемент «${found.label}» не отмечен, отметить не удалось: ${r.reason}` };
  }
  if (req.state === 'checked' && !found.checked) return { ok: false, label: found.label, detail: `элемент «${found.label}» появился, но не отмечен` };
  if (req.state === 'unchecked' && found.checked) return { ok: false, label: found.label, detail: `элемент «${found.label}» отмечен, а должен быть снят` };
  return { ok: true, label: found.label, detail: `«${found.label}» ${found.checked ? 'отмечен' : 'есть'}` };
}

const describeReq = (req) => req.selector || `${req.role || ''} /${req.name}/`;

// Dialog of radio buttons (G-2): choose each radio, verify it reads as checked, only then press confirm, then `then`.
async function watchDialog(page, inv, { guarded }) {
  const dlg = inv.dialog || {};
  const within = +inv.within_ms || 5000;
  const steps = [];
  const choices = dlg.choose || [];
  for (let i = 0; i < choices.length; i++) {
    const ch = choices[i];
    const req = { role: ch.role || 'radio', name: ch.name, selector: ch.selector };
    const limit = i === 0 ? within : (+ch.within_ms || 3000);
    const until = Date.now() + limit;
    let found = null;
    while (Date.now() < until) { found = await findRequired(page, req); if (found) break; await page.waitForTimeout(100); }
    if (!found) return { ok: false, steps, detail: `диалог: вариант ${describeReq(req)} не появился за ${limit} мс — подтверждение не нажато` };
    if (found.checked !== true) {
      const r = await guarded.click(found.locator);
      if (!r.performed) return { ok: false, steps, label: found.label, detail: `диалог: выбрать «${found.label}» не удалось (${r.decision}: ${r.reason}) — подтверждение не нажато` };
      for (let k = 0; k < 10; k++) { await page.waitForTimeout(100); found = await findRequired(page, req) || found; if (found.checked === true) break; }
    }
    steps.push({ choose: found.label, checked: found.checked });
    if (found.checked !== true) return { ok: false, steps, label: found.label, detail: `диалог: «${found.label}» не выбран после нажатия (aria-checked/checked не true) — подтверждение не нажато` };
  }
  if (dlg.confirm) {
    const req = { role: dlg.confirm.role || 'button', name: dlg.confirm.name, selector: dlg.confirm.selector };
    const found = await findRequired(page, req);
    if (!found) return { ok: false, steps, detail: `диалог: кнопка подтверждения ${describeReq(req)} не найдена` };
    const r = await guarded.click(found.locator);
    if (!r.performed) return { ok: false, steps, detail: `диалог: «${found.label}» не нажата (${r.decision}: ${r.reason})` };
    steps.push({ confirm: found.label });
  }
  if (dlg.then) {
    const w = await watch(page, { ...inv, within_ms: +dlg.then.within_ms || within, require: dlg.then }, { guarded });
    return { ...w, steps, detail: (w.ok ? 'диалог пройден; ' : 'после диалога: ') + w.detail };
  }
  return { ok: true, steps, detail: 'диалог пройден: ' + steps.map(s => s.choose || s.confirm).join(' → ') };
}

async function runSideEffect(page, guarded, cfg, effectId, { file, runDir, prevVocab } = {}) {
  const se = (cfg.side_effects || []).find(e => e.id === effectId);
  if (!se) throw new Error(`side_effects: нет ${effectId}`);
  const left = (se.leaves || []).join('; ');
  const pf = await preflight(page, cfg, { runDir, prevVocab, effectId });
  if (!pf.ok) {
    logSideEffect(runDir, { effect: se.id, what: `${se.action} ${se.target} — НЕ выполнено`, result: 'остановлено до действия (предполётная проверка)', invariant: pf.problems.map(p => p.id).join(', '), left: '—' });
    return { status: 'stopped-preflight', exit: 2, questions: pf.problems.map(p => p.question), preflight: pf };
  }
  let r;
  const extra = { viaSideEffect: true };
  if (se.action === 'upload') r = await guarded.setInputFiles(se.target, file, undefined, extra);
  else if (se.action === 'check') r = await guarded.check(se.target);
  else r = await guarded.click(se.target);
  if (!r.performed) {
    logSideEffect(runDir, { effect: se.id, what: `${se.action} ${se.target} — НЕ выполнено`, result: `guard: ${r.decision} (${r.reason})`, invariant: '—', left: '—' });
    return { status: 'blocked', exit: r.decision === 'deny' ? 3 : 2, guard: r, questions: r.question ? [r.question] : [] };
  }
  const what = se.action === 'upload' ? `загружен файл ${path.basename(String(file))} в ${se.target}` : `${se.action} ${se.target}`;
  const results = [];
  const vocabFile = runDir ? path.join(runDir, 'vocabulary.json') : null;
  const vocab = (vocabFile && readVocab(vocabFile)) || {};
  const prev = prevVocab ? readVocab(prevVocab) : null;
  for (const inv of invariantsFor(cfg, se)) {
    const w = inv.dialog ? await watchDialog(page, inv, { guarded }) : await watch(page, inv, { guarded });
    if (w.label) {
      vocab[inv.id] = { observed: w.label, when: 'after-action', at: new Date().toISOString() };
      const p = vocabProblem(inv, w.label, prev);
      if (p) { w.vocabulary = p; w.question = vocabQuestion(p); }
    }
    results.push({ id: inv.id, else: inv.else || 'abort', ...w });
  }
  if (vocabFile) fs.writeFileSync(vocabFile, JSON.stringify(vocab, null, 2));
  const failed = results.filter(x => !x.ok);
  const abort = failed.some(x => (x.else || 'abort') === 'abort');
  const vocabChanged = results.filter(x => x.vocabulary);
  const status = abort ? 'aborted' : failed.length ? 'warned' : vocabChanged.length ? 'vocabulary-changed' : 'ok';
  const resultText = abort ? `ОСТАНОВЛЕНО: ${failed.map(f => f.detail).join('; ')}. Эффект «${se.effect || ''}» мог произойти — проверить вручную и сообщить пользователю`
    : failed.length ? `предупреждение: ${failed.map(f => f.detail).join('; ')}` : 'выполнено, инварианты соблюдены' + (vocabChanged.length ? ' (название защитного элемента изменилось)' : '');
  logSideEffect(runDir, { effect: se.id, what, result: resultText, invariant: results.map(x => `${x.id}: ${x.ok ? 'ok' : 'нарушен'} — ${x.detail}`).join('; '), left: left || '—' });
  const alert = abort ? `Внимание: после действия ${se.id} не выполнен инвариант (${failed.map(f => f.detail).join('; ')}). Прогон остановлен. Возможный эффект: ${se.effect || 'см. side_effects.md'}.` + (left ? ` Осталось: ${left}.` : '') : null;
  return { status, exit: abort ? 3 : vocabChanged.length ? 2 : 0, alert, invariants: results, questions: results.filter(x => x.question).map(x => x.question), leaves: se.leaves || [] };
}

module.exports = { preflight, runSideEffect, logSideEffect, findRequired, watchDialog };

if (require.main === module) {
  (async () => {
    const a = parseArgs(process.argv.slice(2));
    a.url = toUrl(a.url);
    const cmd = a._[0];
    if (cmd === 'log') {
      if (!a['run-dir'] || !a.what) throw new Error('log --run-dir DIR --what "…" [--effect SE1] [--result "…"] [--left "…"]');
      console.log(JSON.stringify({ file: logSideEffect(a['run-dir'], { effect: a.effect || '—', what: a.what, result: a.result || 'выполнено', invariant: a.invariant || '—', left: a.left || '—' }) }));
      return;
    }
    if (!['preflight', 'exec'].includes(cmd) || !a.config || !a['run-dir'] || (!a.url && !a.cdp)) {
      console.error('preflight|exec --config run-config.yaml --run-dir DIR (--url URL | --cdp URL) [--effect SE1] [--file f] [--rules rules.json]');
      process.exit(1);
    }
    const cfg = loadRunConfig(a.config);
    const rules = loadRules(a.rules);
    const { openDevice, attachCdp } = require('./device_context');
    const { guardedPage } = require('./guard');
    const dev = a.cdp ? await attachCdp(a.cdp, a['page-match']) : await openDevice({ device: a.device || 'desktop', rules, logFile: a.log });
    let out, code = 0;
    try {
      const guarded = guardedPage(dev.page, rules, { logFile: a.log, sideEffects: cfg.side_effects || [], confirmMode: 'return' });
      if (a.url) { const nav = await guarded.goto(a.url, { waitUntil: 'load', timeout: 45000 }); if (!nav.performed) throw new Error('переход запрещён: ' + nav.reason); }
      if (a.setup) await require(path.resolve(a.setup))({ page: dev.page, guarded });
      if (cmd === 'preflight') { out = await preflight(dev.page, cfg, { runDir: a['run-dir'], prevVocab: a['prev-vocab'], effectId: a.effect }); code = out.ok ? 0 : 2; }
      else {
        if (!a.effect) throw new Error('нужен --effect');
        out = await runSideEffect(dev.page, guarded, cfg, a.effect, { file: a.file, runDir: a['run-dir'], prevVocab: a['prev-vocab'] });
        code = out.exit;
      }
    } finally { await dev.close().catch(() => {}); }
    console.log(JSON.stringify(out, null, 2));
    if (out.alert) console.error(out.alert);
    process.exit(code);
  })().catch(e => { console.error(String(e.message || e)); process.exit((e && e.exitCode) || 1); });
}
