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
3. `folder` — последним: скопировать `report.md` и `summary.md` в `<path>/<YYYY-MM-DD>-<host>/` (одноимённые файлы не перезаписывать без вопроса).
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
После отчёта — `scripts/gitignore_helper.py check <OUTPUT_ROOT>` и, если код 1, один вопрос (`intake.md` → «В конце прогона: qa-runs/ и git»):
```bash
python3 <SKILL_DIR>/scripts/gitignore_helper.py check <OUTPUT_ROOT>              # 0 — ничего, 1 — спросить, 2 — ошибка
python3 <SKILL_DIR>/scripts/gitignore_helper.py apply <OUTPUT_ROOT> --mode gitignore   # строка /<путь>/qa-runs/ в .gitignore корня
python3 <SKILL_DIR>/scripts/gitignore_helper.py apply <OUTPUT_ROOT> --mode exclude     # то же в .git/info/exclude (локально)
python3 <SKILL_DIR>/scripts/gitignore_helper.py apply <OUTPUT_ROOT> --mode keep        # «буду коммитить» — больше не спрашивать
```
`--json` — состояние (`in_repo`, `repo`, `path`, `ignored`, `tracked_files`, `decision`). Уже отслеживаемые файлы скрипт не трогает, а печатает команду `git rm -r --cached …` для пользователя.

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

Таблицу показать пользователю и ждать «да» (если `confirm_before_publish: true`).
