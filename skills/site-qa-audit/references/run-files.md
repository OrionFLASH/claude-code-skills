# Журнал прогона, report.md и сводная таблица публикации

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

`templates/run-report.md` — образец структуры. Итог в 3–5 строк агент может дописать вручную после сборки.

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
