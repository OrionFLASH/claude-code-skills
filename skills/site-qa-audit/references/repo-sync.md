# Сверка с issues и публикация

## 1. Права и подготовка (шаг 3 прогона)

Для каждого репозитория из run-config:
```bash
python3 scripts/fetch_issues.py meta owner/repo                       # права, метки, has_issues
python3 scripts/read_templates.py fetch owner/repo --out <run>/raw/templates-owner__repo.json
python3 scripts/fetch_issues.py sync owner/repo --cache qa-runs/.cache/issues   # все issues + комментарии, инкрементально
```
После всех: `fetch_issues.py registry owner/a owner/b --cache qa-runs/.cache/issues --out <run>/registry.json`.

| Роль | Нужно | Если нет |
|------|-------|----------|
| `check` | чтение репозитория | без доступа — исключить репозиторий |
| `write-new`, `copies`, `comment` | `has_issues: true`; для приватного — доступ к репозиторию; для публичного достаточно авторизованного gh | понизить до `check` / другой репозиторий / только черновики |
| метки `existing` | метки ставит только `triage`+ (иначе GitHub молча их отбросит) | писать метки строкой в теле |
| метки `create` | `push`+ (`gh label create`) | `existing` или строкой |
| скриншоты `commit` | `push` | не класть, ссылаться на локальные файлы в отчёте |
| скриншоты `web-upload` | право создавать issues/комментировать + вход пользователя на GitHub в браузере с CDP | `commit` (если есть `push`) или ссылки на локальные файлы в отчёте |

Также прочитать `CONTRIBUTING` (из read_templates): требования к заголовкам, языку, обязательным полям — соблюдать.
**Обязательно прочитать документы, на которые ссылаются формы, `config.yml` (`contact_links`) и CONTRIBUTING** (инструкция по тестированию, правила вложений, шкала серьёзности). `read_templates.py fetch` скачивает такие `*.md` из того же репозитория в `<out без .json>-docs/` и печатает список «прочитать: …». Внешние ссылки только перечисляются в `external_links`. Шкалу серьёзности из этих документов записать в `run-config.yaml → repos[].severity_map`, значения выпадающих списков формы — в `target_forms` находок.

## 2. Реестр и отпечатки

- Отпечаток находки: `fingerprint.py` = sha1(direction | check_id | шаблон URL | элемент)[:16]. Не зависит от формулировки.
- В каждом созданном issue/комментарии — скрытый маркер `<!-- site-qa-audit:fp=<fingerprint> -->`. По нему повторный прогон находит свои прошлые записи точно.
- `fingerprint.py match <run>/findings.json <run>/registry.json --out <run>/matches.json` → для каждой находки `exact` (по маркеру) и `candidates` (нечёткие: заголовок/текст + путь URL, score ≥ 0.35).
- Кандидатов **всегда читает агент**: открыть issue, сравнить шаги/URL/элемент. Числу не доверять вслепую.
- **Срез реестра — в задание исполнителю** (`brief.py` делает сам): `python3 <SKILL_DIR>/scripts/fetch_issues.py brief <RUN_DIR>/registry.json --limit 150` — строка на issue: номер, статус (закрытый как исправленный — «исправлено»: повтор = регрессия), заголовок, ключевые слова. Исполнитель сверяет находку со срезом и пишет `dup_check: done` (и `dup_of` / `dup_candidates`, если похоже) или `skipped`. Находки со `skipped` и все остальные всё равно проходят `fingerprint.py match` — сверка исполнителя ускоряет, но не заменяет её.

## 3. Статусы

| Статус | Когда | Действие |
|--------|-------|----------|
| `NEW` | нет ни точных, ни подходящих кандидатов | роль `write-new` → issue по их шаблону; `copies` → подробная копия |
| `DUPLICATE-OPEN` | есть открытый issue о том же | не создавать; в отчёте ссылка; `copies` → копия со ссылкой на оригинал (если ещё нет) |
| `FIXED-OK` | issue закрыт как исправленный / в комментариях «исправлено», и проблема **не воспроизводится** | только в отчёте (подтверждение исправления) |
| `FIXED-INSUFFICIENT` | заявлено исправленным, но воспроизводится частично / в другом месте / в другом браузере | роль `comment` → комментарий `templates/issue-comment.md` с объяснением **почему** недостаточно |
| `REGRESSION` | было исправлено (закрыто completed / подтверждено), снова воспроизводится полностью | `comment` → комментарий + предложить переоткрыть (сам не переоткрывать без подтверждения) |
| `ALREADY-COPIED` | в репозитории-копии уже есть issue с этим fp | не дублировать; обновить комментарием, если изменились детали |
| `UNSURE-MATCH` | кандидат похож, но уверенности нет | **спросить пользователя**: «то же самое» / «новое» / «показать оба» |

Закрыт как `not_planned` → это не «исправлено»: находку пометить `DUPLICATE-OPEN`-аналогом «отклонено ранее» (`known-wontfix` в заметке) и не публиковать повторно без вопроса.

### Перепроверка заявленных исправлений
Отдельный шаг: **все** issues реестра с `fix_claimed: true`, относящиеся к проверяемому сайту/разделу (по URL в теле и заголовку), перепроверить по их шагам воспроизведения, даже если в этом прогоне находки нет. Порядок и команды — `references/claims.md` (`claims.py extract` → `plan` → `set`). Результат: `FIXED-OK` / `FIXED-INSUFFICIENT` / `REGRESSION` / `NOT-CHECKED` с причиной (`logout-required`, `other-account-type`, `forbidden`, …). Находка-недоработка получает `claim_ref {repo, number, quote}`. Ограничение по времени: при глубине smoke — только issues, закрытые за последние 90 дней (`plan --since-days 90`).

## 4. Публикация (шаг 9 прогона)

0. **Независимая перепроверка** (обязательно, `parallelism.md` → «Независимая перепроверка»): `recheck.py run <RUN_DIR>` (каждая находка воспроизводится дважды по `repro`), что не перезапускается скриптом — отдельный исполнитель и `recheck.py set`; правовые нормы — `recheck.py legal`. `recheck.py gate <RUN_DIR>` — что можно публиковать. Не подтвердилось — в отчёт, без issue.
1. **Сводная таблица** перед публикацией: `build_report.py publish-table <RUN_DIR>` (`references/run-files.md`) — статус | severity по шкале репозитория | заголовок | куда | действие (issue/комментарий/пропуск) и над ней политика `closed_claims` каждого репозитория. Если `confirm_before_publish: true` — ждать «да» (можно частично: «публикуй всё, кроме 3 и 7»).
   **Недоработка в закрытом issue** (`FIXED-INSUFFICIENT`, `REGRESSION`) — по `repos[].closed_claims`: `comment` (по умолчанию) — комментарий в закрытом issue, не переоткрывать; `new` — новый issue, связь с исходным, если `cross_links` разрешены; `skip` — не публиковать, только отчёт.
2. **Чувствительные находки** (`evidence.sensitive: true`, `safety-rules.md` §6) в публичные репозитории не публикуются — только по отдельному решению пользователя.
3. **dry-run**: вместо публикации — файлы в `<run>/drafts/<repo>/<NN>-<status>-<fp>.md` (первая строка — заголовок, далее тело, внизу — метки и команда `gh`, которой это опубликовалось бы).
3. **Чужой репозиторий** (`write-new`): строго их шаблон.
   - `.md`-шаблон: заполнить секции под их заголовками, ничего не добавляя сверху; свои поля (окружение, fp) — в конец, в существующую секцию «Additional context»/«Дополнительно» или после неё.
   - YAML issue form: `read_templates.py render <templates.json> --template <name> --values values.json --format body` → только тело (секции `### <label>` в порядке полей формы); `--format json` (по умолчанию) — `{title, body, labels}`, `--format draft` — черновик с `TITLE:`. Обязательные поля — всегда заполнены; dropdown/checkboxes — только допустимые варианты (значения — из `target_forms[repo]`, серьёзность — по `severity_map`).
   - Префикс заголовка и метки шаблона (`title:`, `labels:`) сохраняются.
4. **Репозиторий-копия** (`copies`): `templates/issue-detailed.md`, все находки, включая DUPLICATE-OPEN (со ссылкой на оригинал).
5. **Маркер** `<!-- site-qa-audit:fp=<fp> -->` — последней строкой каждого тела issue и комментария. Настройки репозитория в `run-config.yaml → repos[]` (флаги `render_draft.py` главнее):
   | Ключ | Значения | Флаг | Что делает |
   |---|---|---|---|
   | `disclosure` | `full` (по умолчанию) / `none` | `--disclosure` | `none`: без подписи «Создано site-qa-audit», без источников и id прогона, без маркера скила |
   | `cross_links` | `true` / `false` | `--no-links` | `false`: без ссылок на issues других репозиториев (связанные, совпадения, ссылка на копию) |
   | `marker` | `skill` / `neutral` / `none` | `--marker` | `neutral`: `<!-- qa-fp:<fp> -->` (повторный прогон его тоже находит); по умолчанию `skill` при `full` и `none` при `disclosure: none` |
   | `severity_map` | `{critical: …, high: …, medium: …, low: …, info: …}` | — | шкала репозитория ↔ шкала скила: метка в заголовке и поле Severity; обратно — `render_draft.py severity --label …` |
   | `closed_claims` | `comment` / `new` / `skip` | — | что делать с недоработкой закрытого issue (п. 1) |

   Пример: `render_draft.py detailed <RUN_DIR>/findings.json --id F-003 --config <RUN_DIR>/run-config.yaml --repo owner/repo --out <RUN_DIR>/drafts/owner__repo/03.md`. При `disclosure: none` скрипт предупреждает, если «site-qa-audit» или «Claude» остались в данных находки — поправить текст вручную.
6. **Перекрёстные ссылки** (если `cross_links` не `false`): в копии — ссылка на issue в основном репозитории и наоборот (комментарием в копии, а не правкой чужого issue).
7. **Скриншоты**: gh не прикладывает картинки к issue. При `screenshots: commit` — закоммитить в выбранный репозиторий в `runs/<YYYY-MM-DD>-<host>/` (отдельный коммит, через `gh api` contents или клон в `<run>/repo-<name>`), ссылаться как `https://github.com/owner/repo/blob/<branch>/runs/…/file.png?raw=true`. Для приватных репозиториев картинка видна только тем, у кого есть доступ. Перед коммитом — проверить, что на скриншоте нет персональных данных.
   При `screenshots: web-upload` (чужой или приватный репозиторий без `push`) — `references/web-upload.md`: `node/publish_web.mjs` (issue) / `node/comment_web.mjs` (комментарий, в том числе к закрытому issue) в браузере пользователя с выполненным входом; по умолчанию dry-run, реально — `--confirm-publish` после «да» на сводную таблицу; результат (`number`, `url`, `kind`) → `published` в findings.json (п. 11). `screenshots: none` — картинки не публикуются, ссылки на локальные файлы — в отчёте.
8. **Метки** по политике: `existing` — только из `meta.labels` (подбирать по смыслу: bug, a11y, ux, performance, severity:*); `create` — `gh label create` с описанием, затем ставить; `inline` — строка `Метки: …` в теле.
9. **Команды**:
   ```bash
   gh issue create -R owner/repo --title "<title>" --body-file <draft.md> [--label a --label b]
   gh issue comment <N> -R owner/repo --body-file <comment.md>
   ```
   Тело — всегда через файл (`--body-file`), не в командной строке.
10. **Лимиты API**: пауза 3 с между созданиями, не больше 20 issues в минуту; при `secondary rate limit` / 403 / 5xx — пауза 60 с, повтор до 3 раз; при повторной ошибке — остановиться, оставшиеся сохранить в drafts и сообщить.
11. После публикации записать в `findings.json` для каждой находки: `published: [{repo, number, url, kind: issue|comment}]` — это защищает от дублей при сбое на середине (перед каждым созданием проверять, нет ли уже `published` для этого repo).

### Мелкие находки и предложения — одним issue по теме
Несколько мелких недочётов (`low`, `info`) или предложений одной темы — один issue с таблицей «№ · где · что не так / сейчас · ожидалось / предлагаю · скриншот» и подробностями, по маркеру на каждую находку (повторный прогон находит каждую):
```bash
python3 <SKILL_DIR>/scripts/render_draft.py group <RUN_DIR>/findings.json --ids F-003,F-007,F-009 [--type suggestion] \
  --config <RUN_DIR>/run-config.yaml --repo owner/repo --out <RUN_DIR>/drafts/owner__repo/group-texts.md
python3 <SKILL_DIR>/scripts/render_draft.py groups <RUN_DIR>/findings.json --run-dir <RUN_DIR>   # темы автоматически
```
Тип `suggestion` (предложение) — с теми же скриншотами, колонки «Сейчас / Предлагаю». Если у репозитория своя форма для предложений — сначала их шаблон (`read_templates.py render`), таблица — в поле описания.

## 4a. Прямая публикация (`publish_mode: direct`, по запросу пользователя)
Пользователь просит «сразу в репозиторий», без накопления черновиков и сводной таблицы. Каждая находка проходит по очереди:
1. **воспроизвести дважды**: `recheck.py run <RUN_DIR> --id F-NNN` (или независимый исполнитель + `recheck.py set`);
2. **поиск дублей**: выгрузка issues уже есть (`fetch_issues.py sync` + `registry`), затем `python3 <SKILL_DIR>/scripts/direct_publish.py check <RUN_DIR> --id F-NNN --repo owner/repo`: код 0 — публиковать (печатает команды), 1 — gate закрыт (нет перепроверки, правовые нормы без второй проверки, чувствительная находка), 2 — похожие issues: прочитать, решить (дубль — `DUPLICATE-OPEN`, новое — `--ack-candidates`), 3 — уже опубликовано или точный дубль по маркеру;
3. **issue**: `render_draft.py detailed … --body-only --out <RUN_DIR>/published/<owner>__<repo>/F-NNN.md` (печатает `TITLE:`) → при `confirm_before_publish: true` — вопрос «Опубликовать F-NNN …?» по одной находке → `gh issue create -R owner/repo --title "<TITLE>" --body-file …`;
4. **скриншоты**: `screenshots: web-upload` — `node <SKILL_DIR>/scripts/node/publish_web.mjs --attach-to <N> --repo owner/repo --shots-dir <RUN_DIR>/screenshots --cdp … --confirm-publish` (плейсхолдеры в теле → вложения; по одному номеру); `commit` — как в п. 7;
5. **запись**: `direct_publish.py record <RUN_DIR> --id F-NNN --repo owner/repo --number <N> --url <URL>` → `published.json` и `findings.json → published` (после сбоя повторный `check` вернёт 3).
`direct_publish.py next <RUN_DIR> --repo owner/repo` — следующая находка по severity; `status` — что опубликовано. Лимиты API (п. 10) действуют; в конце — обычный отчёт (`build_report.py report`).

## 5. Итоговый issue
Если есть репозиторий с ролью `copies` — после всех находок создать итоговый issue «QA-аудит <host> от <дата>» по `templates/run-report.md` со ссылками на все созданные issues. Маркер: `<!-- site-qa-audit:run=<YYYY-MM-DD>-<host> -->`; при повторном прогоне в тот же день — комментарий к нему, а не новый issue.

То же для репозитория из `report_destinations` (`type: github`, `intake.md`, вопрос 18), даже без роли `copies`: итоговый issue с телом из `summary.md` (`build_report.py summary`, без локальных путей) и ссылками на созданные issues; права — как для `write-new` (§1), раскрытие и маркер — из `repos[]` этого репозитория; показывается в сводной таблице и ждёт подтверждения, в dry-run — черновик `drafts/<owner>__<repo>/summary.md`.
