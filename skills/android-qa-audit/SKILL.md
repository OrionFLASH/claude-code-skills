---
name: android-qa-audit
description: >
  QA-тестирование Android-приложения по APK, AAB или установленному пакету на эмуляторах и устройствах через
  adb, без исходников: функциональность, логика, UX/UI, разные версии Android и конфигурации (ОЗУ, ядра, экран,
  шрифт, тема, язык, сеть), жизненный цикл, доступность, скорость, пассивная безопасность; матрица стендов, до 4
  потоков, черновики GitHub issues. Используй, когда просят протестировать или проверить приложение, APK,
  Android, мобильное приложение, эмулятор, найти баги в приложении, проверить на разных версиях Android или на
  слабом телефоне, UI мобильного приложения, или дают путь к .apk: «протестируй APK», «проверь приложение на
  Android 10 и 14»; "test this APK", "QA my Android app", "find bugs in the app", "test on emulator". Не используй
  для разработки приложения и правки кода, написания тестов Espresso/Appium, сайтов и веб-приложений (там
  site-qa-audit), нагрузочного теста и пентеста. Вызов без /android-qa-audit — сначала подтвердить намерение.
---

# android-qa-audit

QA-тестирование Android-приложения на эмуляторах и устройствах через adb. Скил не содержит конкретных приложений, пакетов, репозиториев и учётных данных — всё получает на входе.

`<SKILL_DIR>` — папка этого файла. `<RUN_DIR>` — `<OUTPUT_ROOT>/qa-runs/<YYYY-MM-DD>-<package>/`; `<OUTPUT_ROOT>` — путь из запроса, иначе `output_dir` повторяемого конфига, иначе `ANDROID_QA_OUTPUT_DIR`, иначе `<cwd>` (`references/intake.md` → «Папка прогона»). Не в репозитории скилов и не в домашней папке. Скрипты — `python3 <SKILL_DIR>/scripts/<имя>.py` (Windows: `python` или `py -3`); Android SDK не обязан быть в PATH — скрипты находят его сами (`sdkutil.py`).

**Одно место для всего.** Всё, что порождает прогон, лежит только в `<RUN_DIR>`: `run-config.yaml`, `env.json`, `apk-info.json`, `device-matrix.json`, `stands.json`, `journal.md`, `findings.json`, `report.md`, `summary.md`, копии APK `apk/` (с `SHA256SUMS`), `screenshots/`, `recordings/`, `logs/` (logcat, журнал действий, сработавшие запреты), `raw/` (дампы UI, метрики, падения), `drafts/`. Скриншоты и записи — только через `adb_helpers.py` с `--run-dir` или с абсолютным путём в `<RUN_DIR>`.

## Запуск: подтверждение намерения
- **Явный вызов** — пользователь набрал `/android-qa-audit` (в ходе есть `<command-name>/android-qa-audit</command-name>`): подтверждение не нужно, сразу «Порядок работы».
- **Скил подхвачен по смыслу запроса** (без команды): **первым действием**, до `check_env`, файлов и любых команд adb — один вопрос `AskUserQuestion`: «Похоже, вы хотите протестировать Android-приложение <что понято: файл APK, пакет, версии Android, устройства — только названное>. Запустить?» Варианты: «Да (Recommended)» / «Да, но сначала уточнить» / «Нет, это другое».
  - «Да» → обычный порядок, понятое из запроса не переспрашивать; «уточнить» → опрос с вопроса «Что за приложение и для чего»;
  - «Нет» → скил прекращает работу и **ничего не создаёт** (ни папок, ни файлов, ни проверок, ни adb), запрос выполняется как обычный. Нет ответа — не начинать.
  Подробно — `references/intake.md` → «Подтверждение намерения».

## Главное правило
**Безопасность важнее полноты.** До любых действий на устройстве прочитай `references/safety-rules.md`. Все изменения устройства и все нажатия — только через `scripts/adb_helpers.py`: он проверяет каждое действие `scripts/guard.py` (код 3 — запрет, не выполняется и пишется в `logs/blocked.jsonl`; код 2 — спросить пользователя и повторить с `--confirmed` только после «да»). Прямые `adb shell …`, меняющие состояние, — только после `guard.py adb "<команда>" --stand … --config …`. Реальные устройства и чужие AVD — только с явного разрешения пользователя (`stands.consent`, `stands.use_avds`); AVD пользователя не меняются и не удаляются. Блок правил §4 — дословно в задание каждого исполнителя. Запрещённое не выполняется, а попадает в отчёт как «не проверено: запрет <правило>».

**Журнал** `<RUN_DIR>/journal.md` (`scripts/journal.py`, `references/run-files.md`): после каждого крупного шага — `done`, новые задачи — `todo`. В новой сессии сначала `journal.py status <RUN_DIR>` и продолжить с первого открытого пункта (стенды проверить заново: `avd_manager.py list`, `adb_helpers.py devices`).

В командах не использовать разделители из знаков равенства (`echo =====`): в zsh они ломают команду.

## Порядок работы

1. **Окружение** — `references/setup.md`: `scripts/check_env.sh` (Windows: `check_env.ps1`). Таблица: Java, SDK, adb (в т.ч. «найден, но не в PATH»), emulator, cmdline-tools, build-tools, образы и их ABI, AVD (свои `qa-*` и чужие), устройства, ускорение (HVF/WHPX/KVM), ОЗУ, диск, необязательные (bundletool, scrcpy, Maestro, Appium). Обязательное не в порядке → предложить исправление по `INSTALL.md`; глобальные установки — только после подтверждения.
2. **Приложение** — что тестируем: путь к APK (несколько — split), `.apks`, `.aab` (нужен bundletool) или пакет установленного приложения. `apk_info.py analyze <файлы> --copy-to <RUN_DIR>/apk --out <RUN_DIR>/apk-info.json --summary` (установленное — `apk_info.py installed --package … --pull-to <RUN_DIR>/apk`). Показать резюме: пакет, версии, minSdk/targetSdk, разрешения, launcher, ABI (подходит ли эмулятору хоста), debuggable/backup/cleartext, экспортируемые компоненты, deep links, подпись. Пакет теперь известен.
3. **Память о приложении** — `<OUTPUT_ROOT>/qa-runs/.app-context/<package>/context.md`: есть → показать резюме в 3–6 строк и спросить «Использовать как есть (Recommended)» / «Обновить» / «Изучить заново» → `context.reuse` (`intake.md` → «Память о приложении»).
4. **Опрос и конфиг** — `references/intake.md`: по 1–3 вопроса `AskUserQuestion`, рекомендуемый вариант первым, переданное в запросе не переспрашивать. Свободный запрос — сначала `intake.py from-text --file <запрос> --output-dir <OUTPUT_ROOT> --out <RUN_DIR>/run-config.yaml` и показать черновик. Сразу `journal.py init <RUN_DIR> --todo …`. Порции: что за приложение и для чего, откуда узнать о нём → что тестируем и что успех → версии Android (рекомендация из min/target) → конфигурации устройства → виды тестов и направления, глубина → стенды (реальные устройства — отдельный вопрос о согласии) → запреты → потоки (1–4) → репозитории и issues → куда записать итоги. Записать `run-config.yaml` (схема — `templates/run-config.example.yaml`), `guard.py export --config … --out <RUN_DIR>/rules.json`, `check_env.py --fast --json <RUN_DIR>/env.json`. Показать сводку, ждать «старт».
5. **Матрица и стенды** — `matrix.py build --config <RUN_DIR>/run-config.yaml` → `device-matrix.json` (API × железо × вариации по `references/depth-matrix.md`, потоки до 4 по ресурсам). Показать таблицу; недостающие образы — `avd_manager.py install-image --api N` (сначала план с оценкой размера, `--yes` — только после «да», лицензии принимает пользователь). AVD — `avd_manager.py create … --yes --run-dir <RUN_DIR>` (имена `qa-api34-pixel7-2gb-4c`), запуск — `avd_manager.py start <AVD> [--headless] --run-dir …` → `wait-boot <serial> --unlock`. Установка — `adb_helpers.py install <RUN_DIR>/apk/<файл> --serial …` (код `INSTALL_FAILED_*` → подсказка из вывода, `INSTALL.md`). Подробно — `references/stands.md`.
6. **Разведка** (основной стенд, ячейка primary): `logcat start`, `launch --cold`, `dump-ui` + `screenshot` на каждом экране; пройти основные сценарии из памяти и ответов, составить карту экранов (activity → как попасть, элементы, опасные кнопки — их тексты добавить в правила), проверить deep links из манифеста (`deeplink`). Изучить источники из `context.sources` (только чтение) и записать **до прогона** `.app-context/<package>/context.md` по `templates/app-context.md` и `sources.json`. Показать карту и план (ячейки × направления), спросить исключения.
7. **Прогон по матрице** — `references/parallelism.md` + `references/checklists/<направление>.md` + `references/device-control.md`:
   - поток = очередь ячеек на своём эмуляторе/устройстве (`threads` в `device-matrix.json`, до `parallel.max_workers`, по умолчанию 2, **максимум 4**); одно устройство — одно взаимодействие в момент времени; оркестратор ведёт основной поток, остальные — субагенты с заданием из `parallelism.md`;
   - в ячейке: вариации из матрицы (`matrix.py variants`: тёмная тема, шрифт, поворот, RTL, сеть, батарея, Doze…) по очереди с возвратом настроек; чек-листы по глубине (Smoke / Standard / Deep);
   - всегда фоном: `logcat start` на стенде, после каждого сценария `crashes` (падения, ANR) и метрики (`start-time`, `meminfo`, `gfxinfo`) → `raw/`;
   - собственный чек-лист выполняется всегда; усилители из `env.json → enhancers` (`references/plugins-map.md`) только дополняют, запрещённые (`banned`) не используются.
   Каждая находка → `<RUN_DIR>/findings.json` по `templates/finding.schema.json` (id, direction, check_id, type, severity по `references/severity.md`, title, screen, element, steps, expected, actual, environment {api, device_profile, ram_mb, abi, stand, cell…}, repro_rate, crash, logcat_excerpt, screenshots, sources). Каждую находку воспроизвести ещё раз (repro_rate) и проверить на соседней ячейке, где уместно (environment_list). Секреты и персональные данные — маскировать сразу.
8. **Дедупликация**: свести находки потоков и скриптов; `fingerprint.py compute` → `dedupe` → `validate_findings.py <RUN_DIR>/findings.json`. Противоречия — перепроверить, неясно — спросить.
9. **Сверка с issues** (если есть репозиторий) — `references/repo-sync.md`: выгрузка `gh issue list … --json` (только чтение) → `fingerprint.py match` → статусы NEW / DUPLICATE-OPEN / FIXED-OK / FIXED-INSUFFICIENT / REGRESSION / UNSURE-MATCH (спросить).
10. **Вопросы по ходу** (не копить до конца, если блокируют): баг или задумано; нужен вход; запрет блокирует важную проверку; confirm-действие от guard; стенд не стартует; нужно скачать образ.
11. **Публикация** — по умолчанию **dry-run**: `render_draft.py all <RUN_DIR>/findings.json --run-dir <RUN_DIR> --repo owner/repo` → `drafts/<owner__repo>/` (черновики + `index.md` с командами `gh`). Во внешние сервисы — **ничего без явного «да»**: `build_report.py publish-table <RUN_DIR>` → подтверждение → `gh issue create … --body-file …` по одной, с паузами; результат → `published` в findings.json.
12. **Отчёт** — `build_report.py report <RUN_DIR>` и `build_report.py summary <RUN_DIR>`; итог в 3–5 строк по `goal.success` дописать вручную (`templates/run-report.md`). Обязательно: статистика, матрица стендов, падения и ANR, метрики, что не проверено и почему, сработавшие запреты, задействованные усилители.
13. **Итоги, память, git, уборка** (`references/run-files.md`):
   - **куда записать итоги** — по `report_destinations` (папка / GitHub — черновик или после «да» / Artifact, если инструмент есть / свой вариант), раздел «Куда записаны итоги» в `report.md`;
   - **память о приложении** — дополнить `context.md` (сценарии, термины, «задумано так», известные проблемы, строка в «Истории»), без секретов и персональных данных;
   - **git** — `gitignore_helper.py check <OUTPUT_ROOT>`: код 1 → **один** вопрос «Добавить в .gitignore `qa-runs/` и `*.apk`, `*.aab`, `*.apks`, `*.keystore`?» — «Да, всё (Recommended)» / «Только qa-runs/» / «Использовать .git/info/exclude» / «Нет, буду коммитить» → `apply … --mode gitignore|exclude|keep [--pattern qa-runs/]`;
   - **уборка** — `logcat stop` (маскирует файл), вернуть настройки вариаций; вопрос «Что сделать с эмуляторами и AVD прогона?» — «Остановить эмуляторы, AVD qa-* оставить (Recommended)» / «Остановить и удалить AVD qa-*, созданные прогоном» / «Удалить ещё копии APK и видео прогона» / «Ничего не трогать» → `avd_manager.py cleanup --run-dir <RUN_DIR> --stop [--delete-avds] [--delete-apk-copies] [--delete-recordings]` (план, затем `--yes`); ответ на будущее — `stands.cleanup` в конфиге. Отметить завершение в журнале.

## Режимы
- **Быстрая проверка (smoke)** — одна ячейка, основные сценарии, падения, запуск.
- **Только установленное приложение / реальное устройство** — без AVD (`stands.create_avds: false`), один поток на устройство, согласие обязательно.
- **Повтор прогона** — `<OUTPUT_ROOT>/qa-runs/` уже есть конфиг для пакета → «Повторить конфиг от <дата>» / «Повторить, но изменить…» / «Новый опрос»; при новой версии APK — сравнить с прошлым `findings.json` (FIXED-OK / REGRESSION).

## Справочники
| Файл | Когда читать |
|------|--------------|
| `references/setup.md` | шаг 1, требования и поведение при сбоях |
| `references/intake.md` | шаги 3–4: подтверждение намерения, вопросы, папка прогона, память о приложении |
| `references/safety-rules.md` | **всегда, до первой команды adb**; блок §4 — в задания исполнителей |
| `references/stands.md` | шаг 5: образы, создание и запуск AVD, реальные устройства, уборка |
| `references/device-control.md` | шаги 6–7: работа с интерфейсом и журналами через `adb_helpers.py` |
| `references/depth-matrix.md` | шаг 5: матрица API × железо × вариации по глубине |
| `references/parallelism.md` | шаг 7: потоки (до 4), ресурсы, задание субагенту |
| `references/checklists/*.md` | шаг 7: 11 направлений, check_id |
| `references/severity.md` | оценка находок |
| `references/plugins-map.md` | усилители: скилы, Maestro, Appium; что запрещено |
| `references/repo-sync.md` | шаги 9, 11: сверка с issues, черновики, публикация |
| `references/run-files.md` | журнал, отчёт, итоги, память о приложении, git, уборка |
| `templates/app-context.md` | память о приложении (шаги 3, 6, 13) |
| `INSTALL.md` | установка и обновление (macOS, Windows, Linux), настройка Android SDK, промпты для Claude Code |

## Скрипты (`scripts/`, Python 3.9+, только стандартная библиотека)
| Скрипт | Назначение |
|--------|-----------|
| `check_env.py` (`.sh`, `.ps1`) | окружение и стенды → таблица и `env.json`; только чтение |
| `apk_info.py` | `analyze` (APK, split, .apks, .aab) / `installed` / `summary` / `build-apks` (AAB → .apks через bundletool) |
| `avd_manager.py` | `list` / `images` / `plan` / `install-image` / `create` / `start` / `wait-boot` / `snapshot` / `stop` / `delete` / `cleanup`; трогает только свои AVD `qa-*` с меткой |
| `adb_helpers.py` | установка, запуск, UI (`dump-ui`, `tap`, `text`, `swipe`, `key`), снимки и видео, конфигурация (поворот, шрифт, тема, язык, сеть, батарея, Doze), разрешения, logcat, падения и ANR, метрики, monkey — всё через guard |
| `guard.py` | `action` / `package` / `deeplink` / `adb` / `export` / `selftest`; коды 0 allow, 2 confirm, 3 deny |
| `matrix.py` | `build` / `show` / `variants`: матрица и распределение по потокам |
| `intake.py` | `from-text`: свободный запрос → черновик `run-config.yaml` |
| `journal.py` | `init` / `todo` / `done` / `note` / `status` |
| `fingerprint.py` | `compute` / `dedupe` / `match` / `one` |
| `validate_findings.py` | схема findings.json, немаскированные данные, файлы доказательств |
| `render_draft.py` | черновики issues (`detailed`, `all`, `summary`), ничего не публикует |
| `build_report.py` | `report` / `summary` / `publish-table` |
| `gitignore_helper.py` | `check` / `apply --mode gitignore\|exclude\|keep` для `qa-runs/` и `*.apk`, `*.aab`, `*.apks`, `*.keystore` |
| `masking.py`, `sdkutil.py` | маскирование; поиск SDK, инструментов, AVD |

`scripts/shared/` — вендоренные общие модули репозитория скилов. Тесты — `tests/unit.sh` (офлайн, фейковый adb и SDK).
