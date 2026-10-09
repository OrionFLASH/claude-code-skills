# Журнал прогона, report.md, итоги и память о сайте

## journal.md — продолжение после обрыва
`<RUN_DIR>/journal.md` ведётся с начала прогона: что сделано, что осталось, куда записаны побочные эффекты и решения пользователя. В новой сессии сначала `journal.py status` и продолжить с первого открытого пункта.
```bash
python3 <SKILL_DIR>/scripts/journal.py init <RUN_DIR> --todo "Разведка" --todo "Перепроверка заявлений (claims-plan.md)" --todo "Отчёт"
python3 <SKILL_DIR>/scripts/journal.py todo <RUN_DIR> "Мобильный Pixel 7: functional"
python3 <SKILL_DIR>/scripts/journal.py done <RUN_DIR> "Разведка" --note "карта в raw/links.json"
python3 <SKILL_DIR>/scripts/journal.py note <RUN_DIR> "side_effects.md: загружен тестовый файл, флажок отмечен"
python3 <SKILL_DIR>/scripts/journal.py status <RUN_DIR>
```
`done` принимает номер из `status` или часть текста пункта. Если совпадений ноль или несколько, вернётся код 2. `status` без журнала возвращает код 1. Файл — обычный Markdown, его можно править руками.

## report.md — собирается из файлов прогона
```bash
python3 <SKILL_DIR>/scripts/build_report.py report <RUN_DIR>
```
Источники (из `<RUN_DIR>`, если не заданы флагами `--findings`, `--config`, `--rechecks`, `--registry`, `--side-effects`):
`findings.json` (находки, `not_checked`, `rechecks`), `run-config.yaml`, `rechecks.json` (`claims.py`), `registry.json` (состояние issues), `side_effects.md`, `logs/blocked.jsonl` (сработавшие запреты).

Разделы:
- шапка;
- итог: числа по severity и статусам, перепроверка, не проверено, побочные эффекты;
- статистика severity × статус;
- по направлениям;
- находки;
- **перепроверка заявленных исправлений**: №, issue, цитата заявления, статус (у NOT-CHECKED — с причиной), что проверено, чем;
- что не проверено;
- сработавшие запреты;
- побочные эффекты (содержимое `side_effects.md`);
- публикация (сводная таблица ниже).

`templates/run-report.md` — образец структуры. Итог в 3–5 строк агент может дописать вручную после сборки; вывод — по `goal.success`: `findings` — главные проблемы по приоритету, `scenarios` — таблица «сценарий — прошёл / нет», `release-gate` — «блокеры есть / нет» (critical и high со статусом NEW, REGRESSION).

## summary.md — сводка для других мест
```bash
python3 <SKILL_DIR>/scripts/build_report.py summary <RUN_DIR>
```
Шапка, «Итог», «Статистика» и «По направлениям» из report.md (без таблицы находок) и ссылка на `report.md` рядом. Те же флаги, что у `report`.

## Куда записаны итоги (`report_destinations`)
Выполняется после отчёта (SKILL.md, шаг 11), по `run-config.yaml → report_destinations`; что значит каждый `type` — `intake.md`, вопрос 18.
1. `github` и `artifact` — сначала, чтобы получить ссылки. Перед публикацией за пределы машины убрать локальные пути (строка «Папка прогона» в шапке) и находки с `evidence.sensitive`; секреты и персональные данные уже замаскированы (`validate_findings.py`). `github` в dry-run — только черновик `drafts/<repo>/summary.md`.
2. В конец `report.md` дописать раздел:
   ```markdown
   ## Куда записаны итоги
   | Куда | Результат |
   |------|-----------|
   | <RUN_DIR> | report.md, summary.md |
   | /abs/path/2026-10-08-example.com/ | скопировано |
   | owner/repo | https://github.com/owner/repo/issues/12 (или «черновик drafts/owner__repo/summary.md») |
   | Artifact | ссылка или «не опубликовано — инструмент недоступен в сессии» |
   ```
   Повторный `build_report.py report` этот раздел затирает — дописать снова.
3. `folder` — последним: **только итоговые файлы**, не папка прогона:
   ```bash
   python3 <SKILL_DIR>/scripts/export_results.py <RUN_DIR> --to <path>            # → <path>/<YYYY-MM-DD>-<host>/
   python3 <SKILL_DIR>/scripts/export_results.py <RUN_DIR> --to <path> --dry-run  # план
   ```
   | Копируется | Не копируется никогда |
   |------------|-----------------------|
   | `summary.md`, `report.md`, `findings.json`; скриншоты, на которые ссылаются находки (`findings[].screenshots` из `screenshots/`, в т.ч. `-annotated.png`), с тем же относительным путём | `raw/`, `logs/` (`blocked.jsonl`, `auth-state.json`), `drafts/`, `journal.md`, `run-config.yaml`, `env.json`, `rules.json`, `registry.json`, `claims*`, `rechecks.json`, `side_effects.md`, прочие скриншоты |

   `--screenshots all` — все изображения из `screenshots/`, `none` — без них. Одноимённый файл с другим содержимым не перезаписывается: код 1 и список → спросить «Перезаписать» (`--overwrite`) / «Другое имя» (`--name`); одинаковые файлы пропускаются. Последняя строка вывода — готовая строка для «Куда записаны итоги». `.gitignore` в папке назначения не трогается.
4. Запись в журнал: `journal.py note <RUN_DIR> "итоги: …"`.

## Память о сайте (`.site-context/<host>/`)
`<OUTPUT_ROOT>/qa-runs/.site-context/<host>/` — общая для всех прогонов этого хоста (как `.cache/`), лежит внутри `qa-runs/` и вместе с ним исключается из git.
```text
context.md      что известно о сайте (шаблон templates/site-context.md)
sources.json    источники и даты изучения
context.prev.md прошлая версия (только после «Изучить заново»)
```
`context.md` — разделы: назначение; роли и состояния аккаунта; основные сценарии; терминология; устройство; известные особенности и ограничения (в том числе ответы «баг или задумано»); источники с датой изучения; история изменений.

`sources.json`:
```json
{"host": "example.com", "updated": "2026-10-08",
 "sources": [{"type": "site", "ref": "https://example.com/", "studied": "2026-10-08"},
             {"type": "github", "ref": "owner/repo", "studied": "2026-10-08"}]}
```
`type`: `site` | `docs` | `github` | `file` | `chat`; для `chat` в `ref` — «описание в чате» без текста, если в нём есть личное.

Когда что делается:
- начало прогона (шаг 2) — найти файл, показать резюме, спросить «как есть / обновить / заново» (`intake.md` → «Память о сайте»);
- разведка (шаг 4) — изучить источники и записать файл до прогона, путь передать исполнителям;
- конец прогона (шаг 11) — дополнить: новые сценарии и термины, ответы «баг или задумано», известные проблемы со ссылками на issues; обновить даты и строку в «Истории»; при `as-is` — только если появилось новое.

**Не сохранять:** пароли, токены, cookies, `auth-state.json` и его содержимое, e-mail, телефоны, имена и данные реальных людей, содержимое личных кабинетов и платных разделов, находки с `evidence.sensitive`. Факты — обобщённо («у аккаунта с подпиской есть экспорт»), без значений из чужих аккаунтов.

## qa-runs/ и git
**Если пользователь в запросе явно не разрешил класть результаты в репозиторий, папка результатов обязана быть в `.gitignore`.** Проверка — сразу после выбора `<OUTPUT_ROOT>` и **до создания `<RUN_DIR>`** (SKILL.md, шаг 2; `intake.md` → «Результаты и git»), вопроса в конце прогона нет.
```bash
python3 <SKILL_DIR>/scripts/gitignore_helper.py ensure <OUTPUT_ROOT>                           # по умолчанию: qa-runs/ в .gitignore
python3 <SKILL_DIR>/scripts/gitignore_helper.py ensure <OUTPUT_ROOT> --allow-commit-results    # явное «коммить результаты»
python3 <SKILL_DIR>/scripts/gitignore_helper.py ensure <OUTPUT_ROOT> --text "<запрос>"          # разрешение из текста (RU/EN)
python3 <SKILL_DIR>/scripts/gitignore_helper.py untrack <OUTPUT_ROOT> [--yes]                  # git rm -r --cached qa-runs/ — после «да»
python3 <SKILL_DIR>/scripts/gitignore_helper.py check <OUTPUT_ROOT> --json                     # только состояние
```
`run-config.yaml → git.allow_commit_results` (по умолчанию `false`): `false` — строка `/<путь от корня>/qa-runs/` в `.gitignore` корня репозитория (идемпотентно; `<OUTPUT_ROOT>` может ещё не существовать); `true` — `.gitignore` не трогается (если `qa-runs/` уже игнорируется — сказать, правило не удаляется).
Коды `ensure`: 0 — готово (или не в git); 1 — файлы `qa-runs/` уже в индексе: не удаляются, показывается команда `git rm -r --cached <путь>` и задаётся **один** вопрос → `untrack --yes` только после «да» (файлы остаются на диске, коммит — решение пользователя); 2 — ошибка; 3 — строку перекрывает правило с «!» (`git check-ignore -v`). `--mode exclude` — то же в `.git/info/exclude` (если пользователь не хочет менять `.gitignore`). Ответ «буду коммитить» из 1.2.0 (`qa-runs/.gitignore-decision`) сам больше не действует. `--json` — `in_repo`, `repo`, `path`, `ignored`, `tracked_results`, `still_not_ignored`.

## Сводная таблица перед публикацией
```bash
python3 <SKILL_DIR>/scripts/build_report.py publish-table <RUN_DIR>
```
Для каждой находки и каждого репозитория с ролью записи: статус, severity по шкале репозитория (`target_forms[repo].severity_label` или `severity_map`), куда, действие. Над таблицей — политика каждого репозитория: `closed_claims`, раскрытие, ссылки.
- `FIXED-INSUFFICIENT` и `REGRESSION` в **открытом** issue — комментарий.
- В **закрытом** issue — по `closed_claims`. Если `registry.json` нет, состояние неизвестно, и тоже действует `closed_claims`:
  - `comment` — комментарий в закрытом issue;
  - `new` — новый issue (связь с исходным, если `cross_links` разрешены);
  - `skip` — пропуск, только отчёт.
- `FIXED-OK`, `NOT-CHECKED` — только отчёт; `UNSURE-MATCH` — вопрос пользователю; `evidence.sensitive` — не публиковать без решения.
- Колонка **«Перепроверка»**: находка без независимой перепроверки (`recheck.status` не `confirmed`, меньше 2 воспроизведений, ручное подтверждение тем же исполнителем) или с правовыми нормами без второй проверки получает в действии «— НЕ публиковать до перепроверки» (`recheck.py gate`, `parallelism.md` → «Независимая перепроверка»).

Таблицу показать пользователю и ждать «да» (если `confirm_before_publish: true`).

## Файлы исполнителей и публикации
| Файл | Кто пишет | Что |
|------|-----------|-----|
| `skill/` | `skill_snapshot.py --update-config` | копия скила на весь прогон (`run-config.skill_dir`); не пропадёт при обновлении плагина |
| `app/` | `local_app.py copy --update-config` | копия локального приложения (`file://`, `local-files.md`) — тесты не трогают оригинал |
| `playwright-cli.json` | `browser_mode.py`, `local_app.py` | `playwright-cli open --config`: окно прогона, доступ к `file://` для локального приложения |
| `briefs/<поток>.md` | `brief.py` | задание исполнителю целиком (блок правил §4, срез реестра, формат результата) |
| `threads.json` | `brief.py` | потоки: направления, страницы, лимит, время начала (для метрик) |
| `logs/guard-<поток>.jsonl` | `url_guard.py --trace` | решения guard потока (без значений query и контекста) — метрики `coverage.py` |
| `findings/<поток>.json` | `ingest_findings.py` | массив находок потока — место правды вместо пересказа в сообщении |
| `coverage/<поток>.json`, `.md`, `summary.md` | `ingest_findings.py`, `coverage.py` | проверено / не проверено / вопросы и метрики потока |
| `run.json` | `ingest_findings.py` | сведения о прогоне (схема `run`) |
| `waves/<n>/plan.md`, `plan.json`, `<поток>.json` | `coverage.py again` | вторая (и следующие) волна по «не проверено» |
| `raw/messages/index.json` | `ingest_findings.py` | хэши принятых сообщений: повторное уведомление ничего не меняет |
| `raw/messages/<время>-<поток>.md` | `ingest_findings.py` | последнее сообщение исполнителя с блоком ```` ```qa-findings ```` (след для проверки) |
| `questions.json` | `ingest_findings.py` | вопросы исполнителей («баг или задумано», confirm-действия) — оркестратор задаёт их пользователю |
| `tabs.json` | `tabs.py` | реестр вкладок прогона: кто открыл, профиль устройства, инструмент, сессия, закрыта ли |
| `logs/read-only.jsonl` | `url_guard.py nav --read-only --log`, `guard.js` (`readOnly`) | страницы, открытые только для чтения («прочитано без действий») |
| `published.json` | `direct_publish.py record` | что опубликовано в режиме прямой публикации (защита от двойной публикации после сбоя) |
| `published/<owner>__<repo>/F-NNN.md` | `render_draft.py --body-only` | тело опубликованного issue (режим прямой публикации — вместо `drafts/`) |
| `findings.json → recheck`, `legal` | `recheck.py` | результат независимой перепроверки и второй проверки правовых норм |
| `logs/auth-state.json` | `device_context.js state` | секрет: только cookie `allowed_domains` + localStorage/sessionStorage сайта; удаляется `state-rm` |
