# Файлы прогона, отчёт, итоги, память о приложении, git и уборка

## Папка прогона `<RUN_DIR>`
```text
run-config.yaml   конфиг прогона (опрос)              env.json          окружение (check_env --json)
apk-info.json     разбор APK (apk_info.py)            device-matrix.json матрица и потоки (matrix.py)
stands.json       созданные AVD, запущенные эмуляторы  rules.json        правила guard (guard.py export)
journal.md        журнал для продолжения               findings.json     находки (finding.schema.json)
matches.json      сверка с issues                     report.md, summary.md
apk/              копии APK/AAB + SHA256SUMS          screenshots/      снимки экрана (PNG)
recordings/       видео (screenrecord)                 logs/             logcat-*.txt, actions.jsonl, blocked.jsonl, emulator-*.log
raw/              ui-*.xml/json, metrics.jsonl, crashes-*.json, findings-<поток>.json, issues-*.json
drafts/           черновики issues (dry-run)
```
Общее для прогонов: память о приложении `<OUTPUT_ROOT>/qa-runs/.app-context/<package>/`.

## journal.md — продолжение после обрыва
```bash
python3 <SKILL_DIR>/scripts/journal.py init <RUN_DIR> --todo "Стенды" --todo "Разведка" --todo "Прогон c01" --todo "Отчёт"
python3 <SKILL_DIR>/scripts/journal.py todo <RUN_DIR> "c03 (API 26, слабый): functional, lifecycle"
python3 <SKILL_DIR>/scripts/journal.py done <RUN_DIR> "Стенды" --note "AVD: qa-api34-pixel7-4gb-4c, qa-api26-small-2gb-2c"
python3 <SKILL_DIR>/scripts/journal.py note <RUN_DIR> "пользователь: вход тестовым аккаунтом, QA_USERNAME"
python3 <SKILL_DIR>/scripts/journal.py status <RUN_DIR>
```
`done` принимает номер или часть текста пункта (ноль или несколько совпадений — код 2). В новой сессии: `journal.py status`, затем `avd_manager.py list` и `adb_helpers.py devices` (какие стенды живы), продолжить с первого открытого пункта.

## report.md и summary.md
```bash
python3 <SKILL_DIR>/scripts/build_report.py report <RUN_DIR>
python3 <SKILL_DIR>/scripts/build_report.py summary <RUN_DIR>
```
`report.md`: шапка (приложение, версия, min/target, стенды, sha256 APK, время, папка), итог (severity, статусы, падения, не проверено, запреты; для `release-gate` — есть ли блокеры), статистика severity × статус, по направлениям, матрица стендов (находки по ячейкам), падения и ANR (из находок и `raw/crashes-*.json`), метрики (`raw/metrics.jsonl`), находки, пассивная проверка APK (кандидаты), что не проверено, сработавшие запреты (`logs/blocked.jsonl`), публикация. `summary.md` — шапка, итог, статистика, направления и ссылка на `report.md`. Итог в 3–5 строк дописать вручную по `goal.success` (образец — `templates/run-report.md`): `findings` — главные проблемы, `scenarios` — таблица «сценарий — прошёл / нет», `release-gate` — блокеры. Повторный `report` затирает ручные дополнения — дописывать после последней сборки.

## Куда записаны итоги (`report_destinations`)
1. `github` и `artifact` — сначала, чтобы получить ссылки. Перед выходом за пределы машины убрать локальные пути и находки с `evidence.sensitive`. `github` — по `repo-sync.md` §5 (в dry-run — черновик `drafts/<owner__repo>/summary.md`); `artifact` — если в сессии есть инструмент Artifact: страница из `report.md`, иначе «не опубликовано — инструмента нет».
2. В конец `report.md` — раздел:
   ```markdown
   ## Куда записаны итоги
   | Куда | Результат |
   |------|-----------|
   | <RUN_DIR> | report.md, summary.md |
   | /abs/path/2026-10-08-com.example.app/ | скопировано |
   | owner/repo | черновик drafts/owner__repo/summary.md (или ссылка на issue) |
   ```
3. `folder` — последним: копии `report.md` и `summary.md` в `<path>/<YYYY-MM-DD>-<package>/` (одноимённые файлы не перезаписывать без вопроса). `custom` — только после подтверждения.
4. `journal.py note <RUN_DIR> "итоги: …"`.

## Память о приложении (`.app-context/<package>/`)
```text
context.md       что известно о приложении (шаблон templates/app-context.md)
sources.json     источники и даты изучения
context.prev.md  прошлая версия (после «Изучить заново»)
```
`sources.json`:
```json
{"package": "com.example.app", "updated": "2026-10-08", "version": "2.3.1 (42)",
 "sources": [{"type": "app", "ref": "APK 2.3.1", "studied": "2026-10-08"},
             {"type": "store", "ref": "https://play.google.com/store/apps/details?id=com.example.app", "studied": "2026-10-08"}]}
```
`type`: `app` | `store` | `site` | `docs` | `github` | `file` | `chat`; для `chat` — «описание в чате» без личного.

Когда: шаг 3 — найти и спросить «как есть / обновить / заново»; разведка (шаг 6) — изучить источники и записать до прогона, путь передать исполнителям; конец (шаг 13) — дополнить: сценарии и экраны, термины, «задумано так», известные проблемы со ссылками на issues, версия и строка в «Истории».

**Не сохранять:** пароли, токены, ключи, содержимое аккаунтов, e-mail, телефоны, имена реальных людей, serial реальных устройств, находки с `evidence.sensitive`. Факты — обобщённо («у аккаунта с подпиской есть экспорт»).

## qa-runs/, APK и git
```bash
python3 <SKILL_DIR>/scripts/gitignore_helper.py check <OUTPUT_ROOT>                       # 0 — ничего, 1 — спросить, 2 — ошибка
python3 <SKILL_DIR>/scripts/gitignore_helper.py apply <OUTPUT_ROOT> --mode gitignore       # все шаблоны в .gitignore корня репозитория
python3 <SKILL_DIR>/scripts/gitignore_helper.py apply <OUTPUT_ROOT> --mode gitignore --pattern qa-runs/   # только qa-runs/
python3 <SKILL_DIR>/scripts/gitignore_helper.py apply <OUTPUT_ROOT> --mode exclude         # то же в .git/info/exclude (локально)
python3 <SKILL_DIR>/scripts/gitignore_helper.py apply <OUTPUT_ROOT> --mode keep            # «буду коммитить» — больше не спрашивать
```
Шаблоны по умолчанию: `qa-runs/` (строка `/<путь от корня>/qa-runs/` — только папка результатов) и `*.apk`, `*.aab`, `*.apks`, `*.keystore` (по всему репозиторию: сборки и ключи подписи не место в git). Код 1 → **один** вопрос: «Да, всё (Recommended)» / «Только qa-runs/» / «Использовать .git/info/exclude» / «Нет, буду коммитить». Без ответа ничего не правится; `apply` идемпотентен; уже отслеживаемые файлы скрипт не трогает, а печатает команду `git rm -r --cached …` для пользователя. `--json` — состояние по каждому шаблону.

## Уборка
1. `adb_helpers.py logcat stop` на каждом стенде (файл маскируется).
2. Вернуть настройки вариаций (`device-matrix.json → variants.*.reset`), особенно на реальных устройствах; `battery reset`, `animations on`.
3. Вопрос (один, SKILL.md шаг 13): «Остановить эмуляторы, AVD qa-* оставить (Recommended)» / «Остановить и удалить AVD qa-*, созданные прогоном» / «Удалить ещё копии APK и видео прогона» / «Ничего не трогать» → `avd_manager.py cleanup --run-dir <RUN_DIR> --stop [--delete-avds] [--delete-apk-copies] [--delete-recordings]` — сначала план, затем `--yes`. AVD пользователя и эмуляторы, запущенные не этим прогоном, не трогаются никогда.
4. Ответ можно запомнить на будущее: `stands.cleanup: keep | delete-run-avds` в конфиге (при повторе прогона — без вопроса, но с показом плана).
5. Тестируемое приложение на реальном устройстве — удалить только если его поставил прогон и пользователь согласен.
6. `journal.py done <RUN_DIR> "Отчёт"` и запись о завершении.
