// Fixture behaviour shared by gh-new-issue.html and gh-closed-issue.html.
// Emulates the new GitHub issue page: no <form>, no name="comment[body]" on the live editor,
// buttons recognised by text. Every click on a page button is reported as GET /__event?... so the
// test can read it from the python http.server log.
(function () {
  const q = new URLSearchParams(location.search);
  const issue = q.get('n') || '1';
  const report = (params) => fetch('/__event?' + new URLSearchParams({ issue, ...params }).toString(), { keepalive: true }).catch(() => {});
  if (q.get('loggedout') === '1') {
    document.querySelector('meta[name="user-login"]').setAttribute('content', '');
    document.getElementById('editor').remove();
    document.getElementById('signin').hidden = false;
    return;
  }
  const ta = document.getElementById('new-comment');
  const file = document.getElementById('file');
  const attach = document.getElementById('attach');
  if (q.get('attach') === 'input') attach.remove();
  else attach.addEventListener('click', () => file.click());
  file.addEventListener('change', () => {
    for (const f of file.files) {
      const stub = `![Uploading ${f.name}…]()`;
      ta.value += (ta.value && !ta.value.endsWith('\n') ? '\n' : '') + stub;
      ta.dispatchEvent(new Event('input'));
      if (q.get('upload') === 'fail') continue; // never finishes
      setTimeout(() => {
        const id = crypto.randomUUID();
        const done = q.get('upload') === 'broken'
          ? `![${f.name}]()`
          : `<img width="320" alt="${f.name}" src="${location.origin}/user-attachments/assets/${id}" />`;
        ta.value = ta.value.replace(stub, done);
        ta.dispatchEvent(new Event('input'));
      }, 400);
    }
    file.value = '';
  });
  const closeBtn = document.getElementById('state-btn');
  const baseLabel = closeBtn.dataset.label;
  ta.addEventListener('input', () => {
    // like GitHub: the state button changes its text when the box has content
    closeBtn.querySelector('span').textContent = ta.value.trim() ? closeBtn.dataset.withComment : baseLabel;
  });
  closeBtn.addEventListener('click', () => { report({ type: 'click', button: closeBtn.dataset.event }); document.body.dataset.state = closeBtn.dataset.event; });
  const decoy = document.getElementById('decoy');
  if (q.get('decoy') === '1') decoy.hidden = false;
  decoy.addEventListener('click', () => report({ type: 'click', button: 'decoy-close' }));
  const commentBtn = document.getElementById('comment-btn');
  if (q.get('nocomment') === '1') commentBtn.remove();
  commentBtn.addEventListener('click', async () => {
    const body = ta.value;
    await report({ type: 'click', button: 'comment' });
    await report({ type: 'comment', body });
    const li = document.createElement('li'); li.textContent = body; document.getElementById('timeline').append(li);
    ta.value = ''; ta.dispatchEvent(new Event('input'));
  });
})();
