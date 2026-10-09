# Раунд 3 (исполнитель G): #12, #32, #33 — что сделано, что отложено и почему

Ветка `feature/round3-android-triage` (от `main` 3bfe508). #10 и #11 не делались по заданию (#10 — нужно решение владельца по приватности, #11 — вне репозитория). Подробности сделанного — в CHANGELOG скилов: android-qa-audit 1.3.0, typesafe-triage 2.4.0.

## Чек-лист
- [x] #12: общий тестовый модуль — `shared/tests/doc_commands.py`, `doc_zsh.py`; строки `tests/<файл>` в `.shared` → копия в `skills/<имя>/tests/helpers/shared/` (`tools/validate.sh --fix`, побайтовая проверка); копии в скилах удалены; CONVENTIONS.md — одно правило
- [x] #32: график PSS (SVG + спарклайн), контактный лист (`annotate_android.py sheet`, `node/sheet.js`), `job stop` на Windows со сводкой (файл-запрос, `--grace`), loopback на Windows — честно в документации и подсказке `mic-status`
- [x] #33 (а): автозапись факта хуком плагина (`PostToolUse` Agent|Task, `SubagentStop`), опция, выкл. по умолчанию
- [x] #33 (б): «доля чтения/записи» и «накопленные факты» из служебных полей стенограммы, без текста
- [x] документация, версии (android 1.3.0, triage 2.4.0), тесты, validate, коммиты

## Сделано (кратко)

| Issue | Сделано |
|---|---|
| #12 | `doc_commands.py` — общий: android-специфика (обёртка `qa`, `job … -- <команда>`) стала опциями `--wrapper qa=adb_helpers --nested adb_helpers:job`; распознавание скриптов-обёрток общих модулей — единое (site теперь проверяет 373 примера вместо 332, ошибок 0). `doc_zsh.py` тоже в `shared/tests` (общий по смыслу; подключён у android). `doc_node_flags.py` остался в site: он про `scripts/node` и флаги `lib.js` site. `tools/lib/skillsrepo.py`: `shared_pair()` — `tests/…` → `shared/tests` → `tests/helpers/shared/`. В site изменены только `.shared` (одна строка в конце) и строка вызова в `tests/test_v130.sh`. |
| #32 | `build_report.py`: `charts/soak-<tag>-<serial>-pss.svg` рядом с отчётом (stdlib, светлая/тёмная тема, события, экран выкл., подсказки на точках) + спарклайн в таблице. `annotate_android.py sheet` (файлы / `--dir --glob` / `--soak`; 8 на лист; HTML-лист всегда, PNG — Playwright через новый `node/sheet.js`). `job stop`: файл-запрос `raw/jobs/<id>.stop` → soak сам пишет сводку `stopped`; POSIX — ещё SIGTERM; Windows — ждёт `--grace` (120 с), потом снимает дерево, статус `killed`. Windows loopback — «автоматически не поддерживается» с объяснением и ручным путём. |
| #33 | `scripts/triage_autofact.py` + `hooks/hooks.json`; привязка: метка `triage:<id>` → `<id>:` от `--batch` → единственный агент после решения сессии → без привязки; ручной `--fact` дополняет автоматический. `triage_session.work`: инструменты по видам, факты, реплики, токены контекста, после `compact_boundary`; `write_share`, `tool_share`, профиль; правило 10 — ещё при 30+ фактах и в сессии-диалоге; `--check` показывает. |

## Отложено или сделано частично

| Пункт | Что не сделано | Почему |
|---|---|---|
| #32: «контактный лист — вместе с общим модулем» | Общего node-модуля листа для site и android нет: у android своя `node/sheet.js` (идея и вёрстка из `shot.js` site) | Скрипты site в этом круге правит другой исполнитель; механизм `.shared` для node-файлов не проектировался (`require('./lib')` у копий разный — `lib.js` android и site уже расходятся). Кандидат: `shared/scripts/node/contact_sheet.js` без зависимостей от `lib.js`, вендорить в обе `scripts/shared/node/`. |
| #32: loopback на Windows | Автоматизации нет — только документация и подсказка | Без сторонних модулей нельзя узнать устройства вывода и ввода по умолчанию (Win32_SoundDevice их только перечисляет, Core Audio — COM), а игра «вслепую» ушла бы в динамики и дала бы ложный вывод. Автоматически — gRPC или файл. Так и велено заданием. |
| #12: `doc_zsh.py` в site | Не подключён в тестах site | Минимальное пересечение с исполнителем site; документация site его сейчас проходит (код 0). Подключить — строка `tests/doc_zsh.py` в `skills/site-qa-audit/.shared` и одна проверка. |
| #33: исход факта | Автоматически не ставится | Исход (ok/review/rework…) — оценка человека или оркестратора; ни ввод хука, ни стенограмма его не содержат. Остаётся `--fact <id> --outcome …`, который дополняет автоматический факт. |
| #33: реплики пользователя | Служебные сообщения среды, пришедшие как реплика пользователя (например, уведомление о завершении фонового агента), считаются репликами | Отличить их можно только по тексту, а текст не читается. Порог профиля «диалог» (от 3 реплик, работа < 30 %) на это рассчитан с запасом. |

## Не проверено вживую
- **`job stop` на Windows** — Windows нет. Поведение Windows проверено режимом `ANDROID_QA_JOB_STOP=file` на macOS (soak сам дописывает сводку `stopped`; зависший замер `FAKE_ADB_MEMINFO_DELAY` → `killed` после `--grace`); сам `taskkill /T /F` и отвязанный процесс (`DETACHED_PROCESS`) — как в 1.2.0, не проверялись.
- **Автозапись факта в настоящей сессии Claude Code** — не запускали (не трогали `~/.claude`, отдельную сессию `claude -p --plugin-dir` с включённой опцией не открывали). Формат ввода — по документации Claude Code (hooks: PostToolUse для Agent — `status`, `agentId`, `resolvedModel`, `totalTokens`, `totalDurationMs`, `totalToolUseCount`; фоновый — `async_launched` без расхода; SubagentStop — `agent_id`, `agent_transcript_path`) и сверен со стенограммой этой машины (только служебные поля): `toolUseResult` фонового `Agent` и файл `subagents/agent-<agentId>.jsonl` с `usage`/`timestamp` совпадают по `agentId`. `claude plugin validate --strict` — «Validation passed»; на испорченной копии валидатор отклоняет неизвестное событие и тип хука, то есть хуки он проверяет.
- **Счётчики «чем занята сессия»** — проверены `--check` на настоящей стенограмме основной сессии (чтение 3, команды 35, агенты 5, фактов 42, контекст ~239 тыс. токенов — числа, без текста).
- **Контактный лист и график** — отрисованы вживую: `sheet` с Playwright из установленного android-qa-audit 1.2.0 (`ANDROID_QA_NODE_MODULES`, ничего не ставили) на синтетических снимках 1080×2400 (2 листа по 8, подписи, естественный порядок); SVG графика — просмотр через QuickLook (`qlmanage`). На реальном прогоне soak не проверялись (эмуляторы не запускались).

## Найдено по дороге (исправлено)
- `annotate_android.py render` с относительным `--in` падал: Node запускается в `scripts/node`, а пути spec/снимка передавались относительными. Теперь абсолютные (и у `sheet`).
- `sheet`: на macOS `relpath` между `/private/var/…` (resolve) и `/var/…` давал ссылку через корень — HTML-лист сравнивает уже разрешённые пути (найдено тестом до коммита).
- soak: повторный SIGTERM во время записи сводки обрывал её; ожидание итога после стопа теперь не прерывается запросом остановки.
- `doc_commands.py` в site не распознавал `direct_publish.py` и `recheck.py` (обёртки `qa_direct.cli` / `qa_recheck.cli`) — их примеры не проверялись; теперь проверяются (ошибок нет).
- `claude plugin validate` при корректных хуках печатает только строку манифеста — проверку хуков видно лишь при ошибках.

## Проверки
- `skills/android-qa-audit/tests/unit.sh` — PASS 233, FAIL 0 (Python 3.14.0 и /usr/bin/python3 3.9.6); было 222.
- `skills/site-qa-audit/tests/unit.sh` — PASS 64, FAIL 0 (поток v1.3.0 с `doc_commands` — PASS 56; потоки B/C пропущены: нет `node_modules` в рабочей копии).
- `pytest skills/typesafe-triage/scripts` — 352 passed (3.14 и 3.9.6 из venv в scratchpad); было 334. `--selftest --heuristic`: train 65/65, holdout 17/17 по модели, «ниже ожидаемого» 0.
- `bash tools/validate.sh` — 2 ожидаемые ошибки: версии marketplace.json (android 1.2.0 ≠ 1.3.0, triage 2.3.0 ≠ 2.4.0); на копии после `skillsrepo.py sync` — 0 ошибок.

## Где остановился
2026-10-09: #12, #32, #33 сделаны в ветке `feature/round3-android-triage` (три коммита + этот файл), кроме пунктов таблицы «Отложено». Следующий шаг (оркестратор): слить ветку; `python3 tools/lib/skillsrepo.py sync` (marketplace.json и таблица README: android-qa-audit 1.3.0, typesafe-triage 2.4.0); корневой CHANGELOG; теги `android-qa-audit/v1.3.0`, `typesafe-triage/v2.4.0`; закрыть #12, #32, #33 со ссылкой на этот файл (отложенное — новыми issues при желании: общий node-модуль контактного листа, `doc_zsh` в site); живые проверки — `job stop` на Windows, автозапись факта в сессии с `TYPESAFE_TRIAGE_PROJECT_LOG=on` и `TYPESAFE_TRIAGE_AUTO_FACT=on` (агент на переднем плане и фоновый, затем `--calibrate`). Возможный конфликт слияния с исполнителем site: `skills/site-qa-audit/.shared` (строка в конце) и `skills/site-qa-audit/tests/test_v130.sh` (одна строка вызова `doc_commands.py`).
