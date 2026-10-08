#!/usr/bin/env node
// comment_web.mjs — post a comment with screenshots to a GitHub issue (typically a closed one, e.g.
// FIXED-INSUFFICIENT / REGRESSION) through the web UI (strategy `screenshots: web-upload`).
//
// Flow (only with --confirm-publish; the default is a dry-run that prints the plan):
//   1. read the issue state through `gh api` (remembered to prove it did not change);
//   2. connect to the user's logged-in browser over CDP, open the issue, check the login;
//   3. upload every file through the comment box ("Use Markdown to format your comment");
//   4. put the final text into the box (placeholders replaced) and make sure no placeholder is left;
//   5. click the button whose text is exactly "Comment". Close / Reopen are NEVER clicked: candidates
//      are filtered by visible text, aria-label and title and re-checked right before the click;
//   6. `gh api`: the new comment (found by a hidden nonce) has the attachments and no placeholders,
//      and the issue state is the same as before (a closed issue stays closed).
//
// Usage:
//   node comment_web.mjs --repo owner/repo --number 12 --body-file comment.md --shot a.png [--shot b.png]
//        [--cdp http://127.0.0.1:9222] [--base-url https://github.com]
//        [--issue-url-template "{base}/{repo}/issues/{number}"] [--gh gh] [--upload-timeout 60000]
//        [--throttle 1500] [--blocked-log <run>/logs/blocked.jsonl] [--out result.json] [--confirm-publish]
//   node comment_web.mjs --verify-only --repo owner/repo --number 12 --nonce <hex> --expect 1
import path from 'node:path';
import * as L from './web_upload_lib.mjs';

const { EXIT, StopError } = L;
const nonceMarker = (n) => `<!-- site-qa-audit:web=${n} -->`;

function verifyComment(bin, repo, number, nonce, expect) {
  const comments = L.ghComments(bin, repo, number);
  const mine = comments.filter(c => (c.body || '').includes(nonceMarker(nonce)));
  if (!mine.length) return { ok: false, problems: [`комментарий с отметкой ${nonce} не найден по API`], attachments: [] };
  const c = mine[mine.length - 1];
  const v = L.checkBody(c.body || '', expect);
  if (mine.length > 1) v.problems.push(`комментариев с этой отметкой ${mine.length} (дубль)`), v.ok = false;
  return { ...v, comment_id: c.id, comment_url: c.html_url };
}

async function main() {
  const a = L.parseArgs(process.argv.slice(2));
  const repo = L.validateRepo(a.repo);
  const number = Number(a.number);
  if (!Number.isInteger(number) || number <= 0) throw new StopError(EXIT.USAGE, 'Нужен --number <номер issue>.');
  const bin = L.ghBin(a);

  if (a['verify-only']) {
    if (!a.nonce || a.nonce === true) throw new StopError(EXIT.USAGE, 'Для --verify-only нужен --nonce.');
    const v = verifyComment(bin, repo, number, String(a.nonce), Number(a.expect || 1));
    L.emit({ ok: v.ok, repo, number, ...v }, a.out);
    if (!v.ok) process.stderr.write(`Проверка не пройдена: ${v.problems.join('; ')}\n`);
    return v.ok ? EXIT.OK : EXIT.VERIFY_FAILED;
  }

  const base = String(a['base-url'] && a['base-url'] !== true ? a['base-url'] : 'https://github.com').replace(/\/$/, '');
  const issueTpl = a['issue-url-template'] && a['issue-url-template'] !== true ? String(a['issue-url-template']) : '{base}/{repo}/issues/{number}';
  const cdp = a.cdp && a.cdp !== true ? String(a.cdp) : 'http://127.0.0.1:9222';
  const throttle = Number(a.throttle ?? 1500);
  const uploadTimeout = Number(a['upload-timeout'] ?? 60000);
  const shots = a.shot.map(s => path.resolve(s));
  L.checkShots(shots);
  const nonce = L.nonce();
  let body = L.preparePlaceholders(L.readText(a['body-file'], '--body-file'), shots).replace(/\s*$/, '');
  body += `\n${nonceMarker(nonce)}\n`;
  const issueUrl = L.fillTemplate(issueTpl, { base, repo, number });
  L.assertSameHost(issueUrl, base);

  const steps = [
    `gh api repos/${repo}/issues/${number}: запомнить состояние issue (open/closed)`,
    `подключиться к браузеру пользователя по CDP ${cdp}, открыть ${issueUrl}, проверить вход; нет входа — остановка`,
    `в поле «${L.COMMENT_PLACEHOLDER}» загрузить ${shots.length} файл(ов) и вставить текст комментария с заменёнными плейсхолдерами`,
    'нажать только кнопку с текстом ровно «Comment» (Close/Reopen не нажимаются никогда)',
    `gh api: найти комментарий по отметке ${nonce}, проверить вложения и отсутствие плейсхолдеров; состояние issue не изменилось`,
  ];
  if (!a['confirm-publish']) {
    L.printPlan(`План комментария к ${repo}#${number} (стратегия web-upload):`, steps);
    L.emit({ ok: true, dryRun: true, repo, number, shots: shots.map(s => path.basename(s)), steps, body }, a.out);
    return EXIT.OK;
  }

  const before = L.ghIssue(bin, repo, number);
  const stateBefore = before.state;
  const blockedLog = a['blocked-log'] && a['blocked-log'] !== true ? String(a['blocked-log']) : null;
  const { context } = await L.connect(cdp);
  const page = await L.openPage(context, issueUrl, { baseUrl: base, blockedLog });
  const result = { ok: false, repo, number, kind: 'comment', nonce, state_before: stateBefore, attachments: {} };
  try {
    result.user = await L.ensureLoggedIn(page);
    const box = await L.findCommentBox(page);
    if ((await box.inputValue()).trim()) await box.fill(''); // start from an empty box
    for (const shot of shots) {
      const { url, snippet } = await L.uploadOne(page, box, shot, { timeoutMs: uploadTimeout });
      result.attachments[path.basename(shot)] = { url, snippet };
      await L.sleep(Math.min(throttle, 1000));
    }
    const finalText = L.replacePlaceholders(body, Object.fromEntries(Object.entries(result.attachments).map(([k, v]) => [k, v.snippet])));
    await box.fill(finalText);
    const pre = L.checkBody(await box.inputValue(), shots.length);
    if (!pre.ok) throw new StopError(EXIT.VERIFY_FAILED, `Текст комментария не готов, кнопка не нажата: ${pre.problems.join('; ')}`);
    await L.sleep(Math.min(throttle, 1000));
    result.clicked = await L.clickExactComment(page, box);
    // wait for the box to be cleared (comment accepted) — at most 20 s
    for (let i = 0; i < 80; i++) { if (!(await box.inputValue().catch(() => '')).includes(nonce)) break; await L.sleep(250); }
  } finally {
    await page.close().catch(() => {});
  }
  await L.sleep(throttle);

  const v = verifyComment(bin, repo, number, nonce, shots.length);
  const after = L.ghIssue(bin, repo, number);
  result.state_after = after.state;
  if (after.state !== stateBefore) { v.ok = false; v.problems.push(`состояние issue изменилось: ${stateBefore} → ${after.state}`); }
  Object.assign(result, { ok: v.ok, problems: v.problems, comment_url: v.comment_url, verified_attachments: v.attachments });
  L.emit(result, a.out);
  if (!v.ok) { process.stderr.write(`Проверка по API не пройдена: ${v.problems.join('; ')}\n`); return EXIT.VERIFY_FAILED; }
  process.stderr.write(`Готово: комментарий к ${repo}#${number} — вложений ${v.attachments.length}, состояние «${after.state}» не изменилось.\n`);
  return EXIT.OK;
}

L.runMain(main);
