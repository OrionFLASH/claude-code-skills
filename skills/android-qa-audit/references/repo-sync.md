# Сверка с GitHub issues и публикация

Минимальная схема: выгрузка issues (только чтение) → отпечатки и сверка → черновики → сводная таблица → публикация только после «да». **По умолчанию dry-run: ничего не уходит во внешние сервисы без явного согласия пользователя.**

## 1. Доступ и шаблоны (только чтение)
```bash
gh auth status                                                       # вход выполнен? (токен не печатать)
gh repo view owner/repo --json name,hasIssuesEnabled,viewerPermission,isPrivate
gh api repos/owner/repo/contents/.github/ISSUE_TEMPLATE --jq '.[].name'   # их шаблоны (если есть)
gh api repos/owner/repo/contents/CONTRIBUTING.md --jq .content | base64 --decode   # правила оформления (Windows: [Convert]::FromBase64String)
```
| Роль | Нужно | Если нет |
|------|-------|----------|
| `check` | чтение репозитория | без доступа — исключить репозиторий |
| `write-new`, `copies`, `comment` | issues включены; право создавать issues (для приватного — доступ) | понизить до `check` или оставить только черновики |
| метки `existing` | `triage`+ (иначе GitHub молча отбросит метки) | метки строкой в теле (`inline`) |
| вложения `commit` / `branch` | `push` в репозиторий картинок (`attachments_repo`, может быть другим, своим) | ссылки на локальные файлы прогона |

### Их формы issue (`.github/ISSUE_TEMPLATE/*.yml`)
```bash
python3 <SKILL_DIR>/scripts/issue_forms.py fetch --repo owner/repo --out <RUN_DIR>/raw/forms/owner__repo
python3 <SKILL_DIR>/scripts/issue_forms.py show <RUN_DIR>/raw/forms/owner__repo/bug.yml
python3 <SKILL_DIR>/scripts/render_draft.py all <RUN_DIR>/findings.json --run-dir <RUN_DIR> --repo owner/repo --form auto --form-map <RUN_DIR>/raw/forms/owner__repo/map.json
```
- `fetch` — формы и Markdown-шаблоны репозитория (только чтение, `gh api`); `show` — поля (`id`, тип, обязательность, варианты) и из какого поля находки они заполнятся (`← steps`, `← severity`…).
- `render_draft.py --form auto` — форма ошибки для находок и форма предложения для `proposal` / `suggestion` / `user-story`; тело **как из веб-формы**: `### <Название поля>` и значение, пустое — `_No response_`, флажки `- [X]` / `- [ ]`, поле с `render: shell` — блок кода; заголовок — с префиксом формы (`[Bug]: …`), метки — метки формы. Markdown-описание формы (`type: markdown`) в тело не попадает.
- **Выпадающие списки — только точный текст варианта**: серьёзность находки подбирается по словам (`high` → «Высокая» / «Major» / «P1»), иначе — вопрос пользователю. Обязательное поле без значения и обязательный флажок («Я поискал среди открытых issues») скил сам не заполняет — колонка «Проверить» в `index.md`; ответы пользователя — `map.json` (`{"<id или название поля>": "<значение или точный вариант>", "<текст флажка>": true}`), затем `render_draft.py … --form-map map.json`.
- Только Markdown-шаблон (`.md`) — заполнять его разделы под его заголовками; свои поля (окружение, отпечаток) — в конец, в «Additional context» / «Дополнительно». Нет ни форм, ни шаблона — `templates/issue-detailed.md`.

### Уже известно: документы проекта
Если у проекта есть документы «известные ограничения», «не ошибка», «задумано», FAQ (`context.sources: github` или ссылка пользователя) — до публикации сверить с ними находки:
```bash
python3 <SKILL_DIR>/scripts/known_docs.py fetch --repo owner/repo --path docs/KNOWN.md --path docs/FAQ.md --out <RUN_DIR>/raw/known
python3 <SKILL_DIR>/scripts/known_docs.py check <RUN_DIR>/findings.json --doc <RUN_DIR>/raw/known
python3 <SKILL_DIR>/scripts/known_docs.py set <RUN_DIR>/findings.json --id F-006 --doc <RUN_DIR>/raw/known/docs__KNOWN.md --quote "Размеры моделей указаны примерно"
```
`check` пишет в находки `known_candidates` с цитатой и пометкой, говорит ли абзац «задумано / известно / примерно». **Автоматически ничего не снимается**: агент читает цитату; если документ действительно описывает находку — `set` (статус `KNOWN`, документ, цитата): она не публикуется, в `report.md` — раздел «Уже известно». Сомнение — вопрос пользователю.

## 2. Выгрузка и отпечатки
```bash
gh issue list -R owner/repo --state all --limit 1000 --json number,title,body,state,url > <RUN_DIR>/raw/issues-owner__repo.json
```
Репозиторий каждого issue берётся из его `url`; файлов может быть несколько (по одному на репозиторий).
```bash
python3 <SKILL_DIR>/scripts/fingerprint.py compute <RUN_DIR>/findings.json
python3 <SKILL_DIR>/scripts/fingerprint.py dedupe  <RUN_DIR>/findings.json
python3 <SKILL_DIR>/scripts/fingerprint.py match   <RUN_DIR>/findings.json <RUN_DIR>/raw/issues-owner__repo.json --out <RUN_DIR>/matches.json
```
Отпечаток = sha1(направление | check_id | пакет | экран | элемент)[:16] — не зависит от формулировки. В каждом созданном issue — скрытый маркер `<!-- android-qa-audit:fp=<отпечаток> -->` (или нейтральный `<!-- qa-fp:… -->`): повторный прогон находит свои записи точно. Нечёткие кандидаты (заголовок, текст, экран; score ≥ 0.35) **всегда читает агент** — числу не доверять.

## 3. Статусы
| Статус | Когда | Действие |
|--------|-------|----------|
| `NEW` | нет совпадений | `write-new` → черновик issue; `copies` → копия своим шаблоном |
| `DUPLICATE-OPEN` | есть открытый issue о том же | не создавать; ссылка в отчёте |
| `FIXED-OK` | issue закрыт как исправленный и не воспроизводится на этой версии APK | только отчёт |
| `FIXED-INSUFFICIENT` | закрыт, но воспроизводится частично / на другой версии Android / на другом устройстве | `comment` → черновик комментария с объяснением, где и почему |
| `REGRESSION` | был исправлен, снова воспроизводится полностью | `comment` → черновик комментария; переоткрывать — только по решению пользователя |
| `ALREADY-COPIED` | в репозитории-копии уже есть issue с этим отпечатком | не дублировать |
| `UNSURE-MATCH` | кандидат похож, уверенности нет | спросить: «то же самое» / «новое» / «показать оба» |
Закрыт как `not planned` — не «исправлено»: не публиковать повторно без вопроса.

## 4. Черновики (всегда) и публикация (только после «да»)
```bash
python3 <SKILL_DIR>/scripts/render_draft.py all <RUN_DIR>/findings.json --run-dir <RUN_DIR> --repo owner/repo [--status NEW,REGRESSION] [--min-severity low]
python3 <SKILL_DIR>/scripts/render_draft.py detailed <RUN_DIR>/findings.json --id F-003 --repo owner/repo --config <RUN_DIR>/run-config.yaml
python3 <SKILL_DIR>/scripts/build_report.py publish-table <RUN_DIR>
```
- Ролики (`findings[].clips`, `clips.md`): в черновик — только **просмотренные**: GIF inline (если есть) и ссылка `[▶ ролик, 6 с, 0,4 МБ]` на mp4 (веткой — `blob/<ветка>/…?raw=true`); непросмотренный ролик в тело не попадает и стоит в колонке «Проверить» `index.md`. Перед публикацией — `validate_findings.py <RUN_DIR>/findings.json --publish` (непросмотренный / изменённый / отсутствующий ролик — ошибка).
- Черновики: `<RUN_DIR>/drafts/<owner__repo>/NN-<статус>-<отпечаток>.md` (первая строка `TITLE:`), `….body.md` (тело для `--body-file`), `index.md` — заголовки, метки и команда `gh`, которой черновик **был бы** опубликован. Находки с `evidence.sensitive` в черновики не попадают (решение пользователя, `safety-rules.md` §6).
- Настройки из `repos[]` (флаги главнее, затем `publish.*` run-config): `disclosure: tool|none` (ниже); `cross_links: false` — без ссылок на issues других репозиториев; `marker: skill|neutral|none` (только при `tool`); `severity_map` — метка шкалы репозитория в заголовке; `labels: existing|create|inline|none`, `extra_labels`; `form` — путь к форме или `auto`; `steps: human`; `attachments: branch` с `attachments_repo`, `attachments_branch`, `attachments_dir`; `ours: true` — свой репозиторий.
- **Раскрытие (`disclosure`).** `tool` — **по умолчанию**: внизу «_Создано android-qa-audit…_», скрытый маркер отпечатка (повторный прогон находит свои issues точно), источник и id прогона в таблице. `none` — по явной просьбе пользователя («без упоминания скила / инструмента / Claude»): нет подписи, маркеров (в том числе скрытых), строк «Источник» и «Прогон», меток с именем инструмента; поиск дублей при повторном прогоне — только нечёткий. Для **чужого трекера** (`ours` не `true`) `render_draft.py` печатает и пишет в `index.md` предупреждение: публикация без пометки об автоматизации может ввести мейнтейнеров в заблуждение — показать его пользователю перед «да». Трейлеры коммитов Claude Code (`Co-Authored-By` и т. п.) `disclosure` не затрагивает: скил их не добавляет и не удаляет.
- **Человеческие шаги** (`--human-steps`, `repos[].steps: human`, `publish.steps: human`): шаги с командами (`adb_helpers.py font-scale 2.0`, `kill-bg`, `network offline`, `tap --text "…"`) переписываются действиями пользователя («Настройки Android → Экран → Размер шрифта: максимальный», «Свернуть приложение… открыть из «Недавних»», «Включить режим полёта», «Нажать «…»»); команда без перевода остаётся как есть и попадает в «Проверить» — переписать вручную.
- **Перед публикацией — независимая перепроверка** (`parallelism.md`): `recheck.py run <RUN_DIR> --subst SERIAL=<serial>` (каждая находка дважды по `repro`), многошаговые — другой исполнитель и `recheck.py set`, правовые нормы — `recheck.py legal`; `recheck.py gate <RUN_DIR>`. В сводной таблице колонка «Перепроверка»: без подтверждения — «НЕ публиковать до перепроверки».
- **Публикация:** показать сводную таблицу (`publish-table`) → ждать «да» (можно частично: «всё, кроме 3 и 7») → по одному:
  ```bash
  gh issue create -R owner/repo --title "<заголовок>" --body-file <RUN_DIR>/drafts/owner__repo/01-NEW-<fp>.body.md --label bug
  gh issue comment <N> -R owner/repo --body-file <файл>
  ```
  Тело — всегда через файл. Пауза 3 с между созданиями; ошибка лимита (403 secondary rate limit, 5xx) — пауза 60 с, до 3 повторов, затем остановиться, оставшееся — в черновиках. После каждой публикации — `published: [{repo, number, url, kind}]` в findings.json (защита от дублей при обрыве).
- **Вложения:** `gh` не прикладывает картинки к issue — они должны **уже лежать в репозитории**, когда issue создаётся. `attachments: none` (по умолчанию) — в теле «скриншот: `screenshots/…` (файл в папке прогона, приложу по запросу)». `attachments: branch` — **вложения веткой** (ниже). logcat — только выдержкой в теле (замаскирован, ≤ 40 строк). Перед публикацией проверить, что на скриншотах нет персональных данных.

### Вложения веткой и порядок публикации со скриншотами
```bash
python3 <SKILL_DIR>/scripts/attachments.py plan <RUN_DIR> --repo owner/repo --branch qa-screens --dir qa/2026-10-09
python3 <SKILL_DIR>/scripts/attachments.py push <RUN_DIR> --repo owner/repo --branch qa-screens --dir qa/2026-10-09 --yes
python3 <SKILL_DIR>/scripts/attachments.py verify <RUN_DIR> --repo owner/repo --branch qa-screens --dir qa/2026-10-09
python3 <SKILL_DIR>/scripts/render_draft.py all <RUN_DIR>/findings.json --run-dir <RUN_DIR> --repo owner/repo --attachments-base https://github.com/owner/repo/blob/qa-screens/qa/2026-10-09
```
1. **plan** (без сети): какие файлы (скриншоты публикуемых находок — аннотированные вместо оригиналов; `KNOWN`, дубли и `evidence.sensitive` пропускаются), куда, какими ссылками. Показать пользователю: репозиторий картинок (может быть свой приватный, а issues — в чужом: тогда у читателей issue должен быть доступ к картинкам), ветка, папка.
2. **push --yes** — только после «да»: через GitHub contents API (`gh api`), без локального клона — рабочая копия и ветки пользователя не трогаются; нет ветки — создаётся от головы ветки по умолчанию; тот же файл повторно не загружается. Сообщение коммита — `--message` (при `disclosure: none` — без имени инструмента).
3. **verify** — каждый файл есть в ветке (`attachments.json` → `ok`).
   **Ролики находок** (`clips.md`): без `--file` в набор входят и mp4 и GIF **просмотренных** роликов (`finding.py clip-viewed`) тех же находок; `--no-clips` — только скриншоты. Ролик публично виден — публиковать по тому же согласию, что скриншоты.
4. Черновики с `--attachments-base` (или `repos[].attachments: branch` — база собирается сама): ссылки `https://github.com/<repo>/blob/<ветка>/<папка>/<файл>?raw=true` — открываются и в приватном репозитории у всех, у кого есть доступ (`raw.githubusercontent.com` — нет).
5. Только потом — сводная таблица, «да» и `gh issue create … --body-file …` по одной (§4); массовую публикацию можно поручить субагенту с этим порядком и блоком правил.

## 4a. Прямая публикация (`publish_mode: direct`, только по запросу пользователя)
Пользователь просит «сразу в репозиторий» — без накопления черновиков. Для каждой находки по очереди:
1. **воспроизвести дважды** — `recheck.py run <RUN_DIR> --id F-NNN --subst SERIAL=<serial>` (или другой исполнитель + `recheck.py set`);
2. **поиск дублей** — выгрузка `gh issue list … --json number,title,body,state,url > <RUN_DIR>/raw/issues-owner__repo.json` (§2), затем `python3 <SKILL_DIR>/scripts/direct_publish.py check <RUN_DIR> --id F-NNN --repo owner/repo`: 0 — публиковать (печатает команды), 1 — gate закрыт (нет перепроверки, нормы без второй проверки, чувствительная находка, нет выгрузки), 2 — похожие issues: прочитать и решить (`--ack-candidates` — новое), 3 — уже опубликовано или точный дубль по маркеру;
3. **issue** — `render_draft.py detailed … --body-only --out <RUN_DIR>/published/owner__repo/F-NNN.md` (печатает `TITLE:`) → при `confirm_before_publish: true` — вопрос по этой находке → `gh issue create -R owner/repo --title "<TITLE>" --body-file …`;
4. **запись** — `direct_publish.py record <RUN_DIR> --id F-NNN --repo owner/repo --number <N> --url <URL>` → `published.json` и `findings.json → published`.
`direct_publish.py next <RUN_DIR> --repo owner/repo` — следующая по severity; `status` — что опубликовано. Паузы и лимиты — как в §4.

## 5. Итоговый issue (по `report_destinations: github`)
`build_report.py summary <RUN_DIR>` → `render_draft.py summary --run-dir <RUN_DIR> --repo owner/repo` → `drafts/<owner__repo>/summary.md` (без локальных путей, маркер `<!-- android-qa-audit:run=<id> -->`). Публикация — как в §4, после «да»; повторный прогон в тот же день — комментарий к нему, а не новый issue.
