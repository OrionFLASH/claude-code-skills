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
raw/              ui-*.xml/json, metrics.jsonl, crashes-*.json, findings-<поток>.json, issues-*.json,
                  messages/ (сообщения исполнителей с блоком qa-findings — ingest_findings.py)
drafts/           черновики issues (dry-run)
questions.json    вопросы исполнителей (ingest_findings.py)   published.json   прямая публикация (direct_publish.py)
published/        тела опубликованных issues (прямая публикация, render_draft.py --body-only)
```
В `findings.json` у находки: `repro` (как перезапустить проверку), `recheck` (результат независимой перепроверки, `recheck.py`), `legal` (нормы и вторая проверка); в `stands.json` у эмулятора — `owner` (поток).
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
3. `folder` — последним: **только итоговые файлы**, не папка прогона:
   ```bash
   python3 <SKILL_DIR>/scripts/export_results.py <RUN_DIR> --to <path>            # → <path>/<YYYY-MM-DD>-<package>/
   python3 <SKILL_DIR>/scripts/export_results.py <RUN_DIR> --to <path> --dry-run  # план
   ```
   | Копируется | Не копируется никогда |
   |------------|-----------------------|
   | `summary.md`, `report.md`, `findings.json`; скриншоты, на которые ссылаются находки (`findings[].screenshots` из `screenshots/`), с тем же относительным путём | `apk/` (APK, AAB, `SHA256SUMS`), `logs/` (`logcat-*`, `actions.jsonl`, `blocked.jsonl`, журналы эмулятора), `raw/`, `recordings/`, `drafts/`, `journal.md`, `run-config.yaml`, `env.json`, `stands.json`, `rules.json`, прочие скриншоты |

   `--screenshots all` — все изображения из `screenshots/`, `none` — без них. Одноимённый файл с другим содержимым не перезаписывается: код 1 и список → спросить «Перезаписать» (`--overwrite`) / «Другое имя» (`--name`); одинаковые файлы пропускаются. Последняя строка вывода — готовая строка для «Куда записаны итоги». `.gitignore` в папке назначения не трогается: это место, которое выбрал пользователь. `custom` — только после подтверждения.
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
**Если пользователь в запросе явно не разрешил класть результаты в репозиторий, папка результатов обязана быть в `.gitignore`.** Проверка — сразу после выбора `<OUTPUT_ROOT>` и **до создания `<RUN_DIR>`** (SKILL.md, шаг 2), вопроса «Добавить в .gitignore?» в конце прогона нет.
```bash
python3 <SKILL_DIR>/scripts/gitignore_helper.py ensure <OUTPUT_ROOT>                          # по умолчанию: всё в .gitignore
python3 <SKILL_DIR>/scripts/gitignore_helper.py ensure <OUTPUT_ROOT> --allow-commit-results   # явное «коммить результаты»
python3 <SKILL_DIR>/scripts/gitignore_helper.py ensure <OUTPUT_ROOT> --text "<запрос>"         # разрешение из текста (RU/EN)
python3 <SKILL_DIR>/scripts/gitignore_helper.py ensure <OUTPUT_ROOT> --config <run-config.yaml> # git.* из конфига (повтор)
python3 <SKILL_DIR>/scripts/gitignore_helper.py untrack <OUTPUT_ROOT> [--yes]                 # git rm -r --cached qa-runs/ — после «да»
python3 <SKILL_DIR>/scripts/gitignore_helper.py check <OUTPUT_ROOT> --json                    # только состояние
```
| `run-config.yaml → git` | По умолчанию | Что делает `ensure` |
|-------------------------|--------------|---------------------|
| `allow_commit_results` | `false` | `false` — строка `/<путь от корня>/qa-runs/` в `.gitignore` корня репозитория (в т.ч. `.app-context/`); `true` (только явное разрешение) — `qa-runs/` не трогается (если уже игнорируется — сказать, правило не удаляется) |
| `allow_commit_apk` | `false` | `false` — `*.apk`, `*.aab`, `*.apks`, `*.xapk`, `*.keystore`, `*.jks` по всему репозиторию (сборки и ключи подписи не место в git) — даже при `allow_commit_results: true`; `true` — отдельное явное «да» на APK |

Коды `ensure`: 0 — готово (или `<OUTPUT_ROOT>` не в git; папки может ещё не быть); 1 — файлы `qa-runs/` уже в индексе git: **не удаляются**, показывается команда `git rm -r --cached <путь>` и задаётся **один** вопрос, выполнить ли её → `untrack --yes` только после «да» (файлы остаются на диске, коммит — решение пользователя); 2 — ошибка; 3 — строка записана, но её перекрывает правило с «!» (`git check-ignore -v`). Уже отслеживаемые APK проекта вне `qa-runs/` скил не трогает и о них не спрашивает. `--mode exclude` — те же строки в `.git/info/exclude` (только если пользователь не хочет менять `.gitignore`). Старый ответ «буду коммитить» (`qa-runs/.gitignore-decision`, `apply --mode keep`) больше не действует сам — нужно явное разрешение в запросе или `git.allow_commit_results: true`. `--json` — состояние по каждому шаблону, `tracked_results`, `still_not_ignored`.

## Уборка
1. `adb_helpers.py logcat stop` на каждом стенде (файл маскируется).
2. Вернуть настройки вариаций (`device-matrix.json → variants.*.reset`), особенно на реальных устройствах; `battery reset`, `animations on`.
3. Вопрос (один, SKILL.md шаг 13): «Остановить эмуляторы, AVD qa-* оставить (Recommended)» / «Остановить и удалить AVD qa-*, созданные прогоном» / «Удалить ещё копии APK и видео прогона» / «Ничего не трогать» → `avd_manager.py cleanup --run-dir <RUN_DIR> --stop [--delete-avds] [--delete-apk-copies] [--delete-recordings]` — сначала план, затем `--yes`. AVD пользователя и эмуляторы, запущенные не этим прогоном, не трогаются никогда.
4. Ответ можно запомнить на будущее: `stands.cleanup: keep | delete-run-avds` в конфиге (при повторе прогона — без вопроса, но с показом плана).
5. Тестируемое приложение на реальном устройстве — удалить только если его поставил прогон и пользователь согласен.
6. `journal.py done <RUN_DIR> "Отчёт"` и запись о завершении.
