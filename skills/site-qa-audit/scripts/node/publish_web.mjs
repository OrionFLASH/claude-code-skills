#!/usr/bin/env node
// publish_web.mjs — create a GitHub issue whose body carries screenshots uploaded through the web UI
// (strategy `screenshots: web-upload`, references/web-upload.md).
//
// Flow (only with --confirm-publish; the default is a dry-run that prints the plan):
//   1. connect to the user's logged-in browser over CDP and check the login (no login -> stop);
//   2. `gh issue create` with the body where every screenshot is a {{qa-shot:<file>}} placeholder;
//   3. open the new issue page, upload each file through the comment box ("Use Markdown to format
//      your comment") WITHOUT submitting it, collect the attachment links, then clear the box;
//   4. `gh issue edit --body-file` with placeholders replaced by the attachment links;
//   5. `gh api repos/<repo>/issues/<n>`: the body must contain the attachments and no placeholders.
// No button is clicked on the GitHub page except the file-attach button.
//
// Usage:
//   node publish_web.mjs --repo owner/repo --title "<title>" --body-file draft.md --shot a.png [--shot b.png]
//        [--label bug] [--cdp http://127.0.0.1:9222] [--base-url https://github.com]
//        [--issue-url-template "{base}/{repo}/issues/{number}"] [--login-url-template "{base}/{repo}/issues"]
//        [--gh gh] [--upload-timeout 60000] [--throttle 1500] [--blocked-log <run>/logs/blocked.jsonl]
//        [--out result.json] [--confirm-publish]
//   node publish_web.mjs --verify-only --repo owner/repo --number 12 --expect 2      # API check only
//   node publish_web.mjs --attach-to 12 --repo owner/repo (--shot a.png … | --shots-dir <RUN_DIR>/screenshots)
//        [--cdp …] [--confirm-publish]
//        ADD screenshots to an EXISTING issue (created earlier with gh): placeholders «**[Скриншот: file.png]**» or
//        {{qa-shot:file.png}} in its body are replaced by attachments uploaded through the comment box (not submitted);
//        ONE issue number per call (several at once failed with 404 on the second one); the issue page is re-opened
//        on 404 with a growing pause. Missing files stop the run before the browser is touched.
//   Clips (1.7.0, references/clips.md): --shot / placeholders may name .mp4 / .mov / .webm (and the clip's .gif); the
//   draft link «[▶ ролик…](…/F-004.mp4)» becomes a placeholder, GitHub shows a player. GitHub limit — 10 MB per file:
//   a bigger file stops the run BEFORE the browser is touched ([--max-attach-mb N] when the plan allows more).
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import * as L from './web_upload_lib.mjs';

const { EXIT, StopError } = L;

const maxMb = (a) => (a['max-attach-mb'] && a['max-attach-mb'] !== true ? Number(a['max-attach-mb']) : L.ATTACH_LIMIT_MB) || L.ATTACH_LIMIT_MB;

async function main() {
  const a = L.parseArgs(process.argv.slice(2));
  const repo = L.validateRepo(a.repo);
  const bin = L.ghBin(a);

  if (a['verify-only']) {
    if (!a.number) throw new StopError(EXIT.USAGE, 'Для --verify-only нужен --number.');
    const issue = L.ghIssue(bin, repo, a.number);
    const v = L.checkBody(issue.body || '', Number(a.expect || 1));
    L.emit({ ok: v.ok, repo, number: Number(a.number), problems: v.problems, attachments: v.attachments }, a.out);
    if (!v.ok) process.stderr.write(`Проверка не пройдена: ${v.problems.join('; ')}\n`);
    return v.ok ? EXIT.OK : EXIT.VERIFY_FAILED;
  }

  const base = String(a['base-url'] && a['base-url'] !== true ? a['base-url'] : 'https://github.com').replace(/\/$/, '');
  const issueTpl = a['issue-url-template'] && a['issue-url-template'] !== true ? String(a['issue-url-template']) : '{base}/{repo}/issues/{number}';
  const loginTpl = a['login-url-template'] && a['login-url-template'] !== true ? String(a['login-url-template']) : '{base}/{repo}/issues';
  const cdp = a.cdp && a.cdp !== true ? String(a.cdp) : 'http://127.0.0.1:9222';
  const throttle = Number(a.throttle ?? 1500);
  const uploadTimeout = Number(a['upload-timeout'] ?? 60000);

  if (a['attach-to'] !== undefined) return attachExisting(a, { repo, bin, base, issueTpl, cdp, throttle, uploadTimeout });
  if (!a.title || a.title === true) throw new StopError(EXIT.USAGE, 'Нужен --title.');
  const shots = a.shot.map(s => path.resolve(s));
  L.checkShots(shots, maxMb(a));
  const rawBody = L.readText(a['body-file'], '--body-file');
  const body = L.preparePlaceholders(rawBody, shots);
  const loginUrl = L.fillTemplate(loginTpl, { base, repo });
  L.assertSameHost(loginUrl, base);
  L.assertSameHost(L.fillTemplate(issueTpl, { base, repo, number: 1 }), base);

  const steps = [
    `подключиться к браузеру пользователя по CDP ${cdp} (вход на GitHub выполняет только пользователь)`,
    `открыть ${loginUrl} и проверить вход (meta user-login); нет входа — остановка`,
    `gh issue create -R ${repo} --title «${a.title}» с плейсхолдерами: ${shots.map(s => L.tokenFor(path.basename(s))).join(', ')}` +
      (a.label.length ? ` и метками ${a.label.join(', ')}` : ''),
    `открыть страницу нового issue (${L.fillTemplate(issueTpl, { base, repo, number: '<N>' })}), в поле «${L.COMMENT_PLACEHOLDER}» загрузить ${shots.length} файл(ов), комментарий НЕ отправлять, поле очистить`,
    `gh issue edit <N> -R ${repo} --body-file: плейсхолдеры заменить ссылками на вложения`,
    `gh api repos/${repo}/issues/<N>: в теле ≥ ${shots.length} вложений и нет плейсхолдеров`,
  ];
  if (!a['confirm-publish']) {
    L.printPlan(`План публикации issue в ${repo} (стратегия web-upload):`, steps);
    L.emit({ ok: true, dryRun: true, repo, title: a.title, shots: shots.map(s => path.basename(s)), steps, body }, a.out);
    return EXIT.OK;
  }

  const blockedLog = a['blocked-log'] && a['blocked-log'] !== true ? String(a['blocked-log']) : null;
  const { context } = await L.connect(cdp);

  // 1. Login check before anything is created.
  const loginPage = await L.openPage(context, loginUrl, { baseUrl: base, blockedLog });
  const user = await L.ensureLoggedIn(loginPage);
  await loginPage.close();
  await L.sleep(throttle);

  // 2. Create the issue with placeholders (gh owns the auth).
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'qa-web-'));
  const draft = path.join(tmp, 'body.md');
  fs.writeFileSync(draft, body);
  const createArgs = ['issue', 'create', '-R', repo, '--title', String(a.title), '--body-file', draft];
  for (const l of a.label) createArgs.push('--label', l);
  const created = L.gh(bin, createArgs).trim();
  const m = created.match(/\/issues\/(\d+)\s*$/m);
  if (!m) throw new StopError(EXIT.ENV, `gh issue create не вернул ссылку на issue: ${created.slice(0, 200)}`);
  const number = Number(m[1]);
  const result = { ok: false, repo, number, url: created.split('\n').pop(), kind: 'issue', user, attachments: {} };
  await L.sleep(throttle);

  // 3. Upload every file through the comment box of the new issue (never submitted).
  const page = await L.openPage(context, L.fillTemplate(issueTpl, { base, repo, number }), { baseUrl: base, blockedLog });
  try {
    await L.ensureLoggedIn(page);
    const box = await L.findCommentBox(page);
    for (const shot of shots) {
      const { url, snippet } = await L.uploadOne(page, box, shot, { timeoutMs: uploadTimeout });
      result.attachments[path.basename(shot)] = { url, snippet };
      await L.sleep(Math.min(throttle, 1000));
    }
    await box.fill(''); // leave no draft behind
  } catch (e) {
    if (e instanceof StopError) {
      e.extra = { ...e.extra, repo, number, url: result.url, note: 'issue создан, плейсхолдеры остались — исправьте вручную или повторите загрузку' };
    }
    throw e;
  } finally {
    await page.close().catch(() => {});
  }

  // 4. Replace placeholders through the API.
  const snippets = Object.fromEntries(Object.entries(result.attachments).map(([k, v]) => [k, v.snippet]));
  const finalBody = L.replacePlaceholders(body, snippets);
  fs.writeFileSync(draft, finalBody);
  L.gh(bin, ['issue', 'edit', String(number), '-R', repo, '--body-file', draft]);
  fs.rmSync(tmp, { recursive: true, force: true });
  await L.sleep(throttle);

  // 5. Verify through the API.
  const issue = L.ghIssue(bin, repo, number);
  const v = L.checkBody(issue.body || '', shots.length);
  result.ok = v.ok; result.problems = v.problems; result.verified_attachments = v.attachments;
  L.emit(result, a.out);
  if (!v.ok) { process.stderr.write(`Проверка по API не пройдена (#${number}): ${v.problems.join('; ')}\n`); return EXIT.VERIFY_FAILED; }
  process.stderr.write(`Готово: ${result.url} — вложений ${v.attachments.length}, плейсхолдеров нет.\n`);
  return EXIT.OK;
}

// --attach-to N: screenshots into an existing issue (G-8).
async function attachExisting(a, { repo, bin, base, issueTpl, cdp, throttle, uploadTimeout }) {
  const raw = String(a['attach-to']);
  if (!/^\d+$/.test(raw)) throw new StopError(EXIT.USAGE, `--attach-to: один номер issue за вызов (получено «${raw}»). Несколько номеров — отдельными запусками.`);
  const number = Number(raw);
  // gh may also answer 404 right after creation: retry the API read a few times.
  let issue = null;
  for (let i = 0; i < 3 && !issue; i++) {
    try { issue = L.ghIssue(bin, repo, number); }
    catch (e) { if (i === 2 || !/404|Not Found/i.test(e.message)) throw e; await L.sleep(2000 * (i + 1)); }
  }
  const body = issue.body || '';
  const ph = L.existingPlaceholders(body);
  if (!ph.length) {
    L.emit({ ok: true, repo, number, kind: 'attach', note: 'в теле нет плейсхолдеров «**[Скриншот: файл]**» / {{qa-shot:файл}} — нечего добавлять' }, a.out);
    return EXIT.OK;
  }
  const byName = new Map(a.shot.map(s => [path.basename(s), path.resolve(s)]));
  const dir = a['shots-dir'] && a['shots-dir'] !== true ? path.resolve(String(a['shots-dir'])) : null;
  const files = [];
  for (const p of ph) {
    const f = byName.get(p.name) || (dir ? path.join(dir, p.name) : null);
    if (!f || !fs.existsSync(f)) throw new StopError(EXIT.USAGE, `Нет файла для плейсхолдера «${p.token}»: ${f || p.name} (--shot или --shots-dir). Ничего не изменено.`);
    files.push({ ...p, file: f });
  }
  L.checkShots([...new Set(files.map(f => f.file))], maxMb(a));
  const steps = [
    `gh api repos/${repo}/issues/${number}: плейсхолдеров ${ph.length} (${ph.map(p => p.name).join(', ')})`,
    `открыть ${L.fillTemplate(issueTpl, { base, repo, number })} (при 404 — повтор с паузой), проверить вход`,
    `в поле «${L.COMMENT_PLACEHOLDER}» загрузить ${files.length} файл(ов), комментарий НЕ отправлять, поле очистить`,
    `gh issue edit ${number} -R ${repo} --body-file: плейсхолдеры заменить вложениями`,
    `gh api: вложений не меньше ${files.length}, плейсхолдеров нет`,
  ];
  if (!a['confirm-publish']) {
    L.printPlan(`План: добавить скриншоты в существующий issue ${repo}#${number}:`, steps);
    L.emit({ ok: true, dryRun: true, repo, number, kind: 'attach', placeholders: ph.map(p => p.name), steps }, a.out);
    return EXIT.OK;
  }
  const blockedLog = a['blocked-log'] && a['blocked-log'] !== true ? String(a['blocked-log']) : null;
  const { context } = await L.connect(cdp);
  const page = await L.openPageRetry(context, L.fillTemplate(issueTpl, { base, repo, number }), { baseUrl: base, blockedLog },
    { tries: Number(a['retries'] ?? 3), pauseMs: Number(a['retry-pause'] ?? 2000) });
  const snippets = {};
  try {
    await L.ensureLoggedIn(page);
    const box = await L.findCommentBox(page);
    for (const f of files) {
      if (snippets[f.name]) continue;
      snippets[f.name] = (await L.uploadOne(page, box, f.file, { timeoutMs: uploadTimeout })).snippet;
      await L.sleep(Math.min(throttle, 1000));
    }
    await box.fill('');
  } finally { await page.close().catch(() => {}); }
  let finalBody = body;
  for (const f of files) finalBody = finalBody.split(f.token).join(snippets[f.name]);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'qa-web-'));
  const draft = path.join(tmp, 'body.md');
  fs.writeFileSync(draft, finalBody);
  L.gh(bin, ['issue', 'edit', String(number), '-R', repo, '--body-file', draft]);
  fs.rmSync(tmp, { recursive: true, force: true });
  await L.sleep(throttle);
  const after = L.ghIssue(bin, repo, number);
  const v = L.checkBody(after.body || '', new Set(files.map(f => f.name)).size);
  L.emit({ ok: v.ok, repo, number, kind: 'attach', url: after.html_url || after.url, problems: v.problems, attachments: v.attachments }, a.out);
  if (!v.ok) { process.stderr.write(`Проверка по API не пройдена (#${number}): ${v.problems.join('; ')}\n`); return EXIT.VERIFY_FAILED; }
  process.stderr.write(`Готово: #${number} — вложений ${v.attachments.length}, плейсхолдеров нет.\n`);
  return EXIT.OK;
}

L.runMain(main);
