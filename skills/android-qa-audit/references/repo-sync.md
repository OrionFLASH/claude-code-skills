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
| вложения `commit` | `push` в репозиторий | ссылки на локальные файлы прогона |

Их шаблон (`.md` или форма `.yml`) — заполнять их секции под их заголовками; свои поля (окружение, отпечаток) — в конец, в «Additional context» / «Дополнительно». Нет шаблона — `templates/issue-detailed.md`.

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
- Черновики: `<RUN_DIR>/drafts/<owner__repo>/NN-<статус>-<отпечаток>.md` (первая строка `TITLE:`), `….body.md` (тело для `--body-file`), `index.md` — заголовки, метки и команда `gh`, которой черновик **был бы** опубликован. Находки с `evidence.sensitive` в черновики не попадают (решение пользователя, `safety-rules.md` §6).
- Настройки из `repos[]` (флаги главнее): `disclosure: none` — без подписи скила и маркера; `cross_links: false` — без ссылок на issues других репозиториев; `marker: skill|neutral|none`; `severity_map` — метка шкалы репозитория в заголовке; `labels: existing|create|inline|none`, `extra_labels`.
- **Публикация:** показать сводную таблицу (`publish-table`) → ждать «да» (можно частично: «всё, кроме 3 и 7») → по одному:
  ```bash
  gh issue create -R owner/repo --title "<заголовок>" --body-file <RUN_DIR>/drafts/owner__repo/01-NEW-<fp>.body.md --label bug
  gh issue comment <N> -R owner/repo --body-file <файл>
  ```
  Тело — всегда через файл. Пауза 3 с между созданиями; ошибка лимита (403 secondary rate limit, 5xx) — пауза 60 с, до 3 повторов, затем остановиться, оставшееся — в черновиках. После каждой публикации — `published: [{repo, number, url, kind}]` в findings.json (защита от дублей при обрыве).
- **Вложения:** `gh` не прикладывает картинки к issue. `attachments: none` (по умолчанию) — в теле «скриншот: `screenshots/…` (файл в папке прогона, приложу по запросу)»; `attachments: commit` (нужен `push`, свой репозиторий) — закоммитить скриншоты и видео в отдельную папку/ветку (`qa-runs/<дата>/` в репозитории — после «да»), затем `render_draft.py … --attachments-base https://github.com/owner/repo/blob/<ветка>/<папка>`. Перед публикацией проверить, что на скриншотах нет персональных данных. logcat — только выдержкой в теле (замаскирован, ≤ 40 строк).

## 5. Итоговый issue (по `report_destinations: github`)
`build_report.py summary <RUN_DIR>` → `render_draft.py summary --run-dir <RUN_DIR> --repo owner/repo` → `drafts/<owner__repo>/summary.md` (без локальных путей, маркер `<!-- android-qa-audit:run=<id> -->`). Публикация — как в §4, после «да»; повторный прогон в тот же день — комментарий к нему, а не новый issue.
