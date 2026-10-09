# android-qa-audit

QA-тестирование Android-приложения — по APK, split APK, `.apks`, AAB или уже установленному пакету — на эмуляторах и подключённых устройствах через adb, без исходного кода. Скил разбирает APK, сам находит и готовит стенды (создаёт AVD `qa-*` с нужной версией Android, ОЗУ, ядрами, экраном), строит матрицу «версии Android × железо × настройки», проходит приложение как пользователь и как инструменты (дерево элементов, logcat, dumpsys, monkey), до 4 стендов одновременно, и складывает находки, отчёт и черновики GitHub issues в папку прогона.

Внутри скила нет конкретных приложений, пакетов, репозиториев, логинов и токенов: всё передаётся на входе.

**Установка, настройка Android SDK и обновление** (macOS, Windows, Linux, промпты для Claude Code) — [INSTALL.md](INSTALL.md).

**Запуск.** Командой `/android-qa-audit`, названием скила в просьбе («используя скилл Android qa audit…») или обычной просьбой протестировать или проверить приложение, APK, Android-приложение, найти баги, проверить на разных версиях Android или на слабом телефоне, в том числе с путём к `.apk`. Если скил подхвачен по смыслу (не назван), он сначала спрашивает: «Похоже, вы хотите протестировать Android-приложение <что понял>. Запустить?» — при «Нет, это другое» ничего не создаёт. На разработку приложения, написание тестов Espresso/Appium и сайты (для них — `site-qa-audit`) не срабатывает. Исследовательский прогон, когда задача уже описана, — **лёгкий режим**: один вопрос «только неясное», затем сразу работа (`references/intake.md`).

**Что нового в 1.3.0:** график PSS картинкой (SVG) и спарклайн в разделе «Длинные сценарии» отчёта; контактный лист скриншотов (`annotate_android.py sheet` — 8 снимков на картинку, HTML-лист рядом); `job stop` на Windows дожидается сводки soak (запрос остановки файлом, `--grace`); честное описание пути loopback на Windows. Подробно — [CHANGELOG.md](CHANGELOG.md).

**Что нового в 1.2.0** (по отзыву реального прогона голосового приложения): звук в микрофон эмулятора (`mic-inject`: gRPC с токеном, loopback, файл), долгие сценарии с проверкой предусловий и фоновые задачи (`soak`, `job`), нажатия на экранах с бесконечной анимацией (`tap X Y --no-ui`), полные тексты экрана (`dump-ui --texts`), неоднозначные совпадения и проверка результата нажатия, уведомления с прогрессом, аннотированные скриншоты (`screenshot --mark`, `finding.py add`), публикация по их формам issue со скриншотами веткой и документами «уже известно», `disclosure: tool|none`, выбор файла в системном пикере (`import-file`), кириллица через буфер обмена, обёртка `qa` для zsh, переиспользование своих AVD в матрице.

## Что проверяется
| Направление | Кратко |
|-------------|--------|
| `functional` | запуск без падений, основные сценарии, навигация и «Назад», формы и валидация, списки и пустые состояния, ошибки сети, уведомления, deep links, разрешения (запрос, отказ, «только сейчас», отзыв), установка и обновление поверх |
| `logic-state` | сохранение данных и состояния, повторные нажатия, гонки при медленной сети, кэш и офлайн, время и часовой пояс |
| `ux` | эвристики, платформенные паттерны, онбординг, понятность ошибок, объяснение разрешений, шаги до цели |
| `visual-ui` | обрезанный текст, перекрытия, выход за экран, отступы, тёмная тема, системные панели и вырез |
| `device-config-compat` | малый экран, планшет, складной, density, шрифт 1.3/2.0, ориентация, язык и RTL, мало ОЗУ и слабый CPU, сеть, батарея |
| `lifecycle-resilience` | поворот, сворачивание, смерть процесса в фоне, trim-memory, смена конфигурации на лету, Doze, прерывания, утечки Activity |
| `accessibility` | метки TalkBack, цели 48×48 dp, контраст, шрифт 2.0, фокус и порядок, состояния |
| `performance` | холодный/тёплый/горячий старт, jank, память, размер, батарея, ANR |
| `security-passive` | debuggable, allowBackup, cleartext, экспортируемые компоненты, разрешения, подпись, секреты в logcat — **только пассивно** |
| `compatibility` | различия поведения между версиями Android (уведомления 33+, медиа-доступ, edge-to-edge 35+, фоновые ограничения), ABI |
| `content-i18n` | опечатки, непереведённые строки, форматы дат и чисел, RTL, длинные переводы, терминология |

## Входные параметры (опрос)
Если параметр не передан в запросе, скил спросит его с вариантами ответа (подробно — `references/intake.md`).

| # | Параметр | По умолчанию |
|---|----------|--------------|
| 1 | Приложение: путь к APK/AAB/APKS или пакет установленного; что это и для чего; откуда узнать (само приложение, магазин, README, документация, файл) | — (обязательно); изучить само приложение |
| 2 | Что тестируем и что считать успехом (`goal`) | основные сценарии; список проблем |
| 3 | Версии Android (API) | по глубине: min / середина / target из манифеста |
| 4 | Железо: ОЗУ 1/2/4/8 ГБ, ядра, диск, экран (телефон, малый, планшет, складной) | по глубине |
| 5 | Настройки: тёмная тема, шрифт 1.3/2.0, ориентация, масштаб экрана, язык и RTL, сеть (Wi-Fi/4G/3G/EDGE/офлайн/смена), низкий заряд, экономия, Doze, часовой пояс | по глубине |
| 6 | Виды тестов: ручные сценарии, monkey с seed, UI по дереву элементов, жизненный цикл, разрешения, уведомления, deep links, фон, нехватка памяти, падения и ANR, производительность, доступность, безопасность, установка/обновление, краевой ввод | ручные сценарии + падения |
| 7 | Направления (11) и глубина: smoke / standard / deep | все, standard |
| 8 | Стенды: эмуляторы скила / мои устройства (с согласием: только чтение / только приложение / всё) / мои AVD (только `-read-only`); headless | эмуляторы скила |
| 9 | Запреты и куда не заходить | только базовые |
| 10 | Параллельные потоки (стенды одновременно) | 2 (максимум 4, по ресурсам) |
| 11 | GitHub issues: репозиторий, роли, шаблон, метки, вложения, раскрытие | нет; режим dry-run |
| 12 | Куда записать итоги: папка, GitHub, Artifact, свой вариант | только папка прогона |
| 13 | Папка результатов | путь из запроса / `ANDROID_QA_OUTPUT_DIR` / `<cwd>/qa-runs/` |

Результаты — в `<OUTPUT_ROOT>/qa-runs/<YYYY-MM-DD>-<package>/`: `run-config.yaml`, `env.json`, `apk-info.json`, `device-matrix.json`, `stands.json`, `journal.md`, `findings.json`, `report.md`, `summary.md`, `apk/` (копии с SHA256), `screenshots/`, `recordings/`, `logs/` (logcat, действия, запреты), `raw/`, `drafts/`. Память о приложении — `<OUTPUT_ROOT>/qa-runs/.app-context/<package>/context.md`. Если папка внутри git-репозитория — сразу, до первой записи, `qa-runs/` и `*.apk`, `*.aab`, `*.apks`, `*.xapk`, `*.keystore`, `*.jks` попадают в `.gitignore` (без вопроса; коммитить результаты — только по явному разрешению в запросе, `git.allow_commit_results`); уже закоммиченные результаты не удаляются — один вопрос про `git rm -r --cached`. «Другая папка» для итогов (`report_destinations: folder`) получает только `summary.md`, `report.md`, `findings.json` и скриншоты находок. В конце — вопрос, что сделать с эмуляторами и AVD прогона.

## Примеры вызова
```text
/android-qa-audit
Протестируй ~/Downloads/app-release.apk — smoke, основные сценарии, без репозиториев.
Проверь приложение "/abs/path/My App.apk" на Android 10, 13 и 15, на слабом телефоне с 2 ГБ ОЗУ и на планшете,
тёмная тема и крупный шрифт, медленная сеть. Не нажимай «Купить» и «Опубликовать». В 3 потока.
QA установленного приложения com.example.app на моём телефоне по USB: только смотреть, ничего не менять.
Глубокий тест app.aab: жизненный цикл, разрешения, уведомления, monkey; ошибки — черновиками в owner/repo.
Test this APK on emulators: Android 12 and 14, accessibility and performance, English report.
```

## Команды (основные)
```bash
S=<SKILL_DIR>/scripts; R=<RUN_DIR>
bash $S/check_env.sh                                                         # окружение (Windows: check_env.ps1)
python3 $S/apk_info.py analyze app.apk --summary                             # пакет; файлы ещё не пишутся
python3 $S/gitignore_helper.py ensure <OUTPUT_ROOT>                          # до <RUN_DIR>: qa-runs/ и *.apk… в .gitignore
python3 $S/apk_info.py analyze app.apk --copy-to $R/apk --out $R/apk-info.json --summary
python3 $S/intake.py from-text --file request.txt --output-dir <OUTPUT_ROOT> --out $R/run-config.yaml
python3 $S/matrix.py build --config $R/run-config.yaml                      # матрица и потоки
python3 $S/avd_manager.py install-image --api 34 --run-dir $R              # план загрузки образа; --yes после «да»
python3 $S/avd_manager.py create --api 34 --profile small --ram 2048 --cores 2 --yes --run-dir $R
python3 $S/avd_manager.py start qa-api34-small-2gb-2c --headless --run-dir $R && python3 $S/avd_manager.py wait-boot emulator-5554 --unlock
python3 $S/adb_helpers.py install $R/apk/app.apk --serial emulator-5554 --run-dir $R
python3 $S/adb_helpers.py dump-ui --serial emulator-5554 --run-dir $R      # дерево элементов + кандидаты a11y/visual
python3 $S/adb_helpers.py tap --text "Далее" --serial emulator-5554 --run-dir $R   # нажатие под guard (3 — запрет, 2 — спросить)
python3 $S/adb_helpers.py kill-bg --serial emulator-5554 --run-dir $R      # смерть процесса в фоне
python3 $S/adb_helpers.py start-time --mode cold --runs 5 --serial emulator-5554 --run-dir $R
python3 $S/adb_helpers.py crashes --serial emulator-5554 --run-dir $R      # только процессы приложения; чужие — other_processes
python3 $S/fingerprint.py compute $R/findings.json && python3 $S/fingerprint.py dedupe $R/findings.json
python3 $S/validate_findings.py $R/findings.json
python3 $S/render_draft.py all $R/findings.json --run-dir $R --repo owner/repo   # черновики, ничего не публикует
python3 $S/build_report.py report $R && python3 $S/build_report.py summary $R
python3 $S/export_results.py $R --to /abs/path/reports                     # report_destinations: folder — только итоги
python3 $S/avd_manager.py cleanup --run-dir $R --stop --delete-avds         # план; --yes после ответа
# 1.1.0: находки исполнителей текстом, независимая перепроверка, прямая публикация, стенды потоков
python3 $S/ingest_findings.py $R --from $R/raw/w2-message.md --thread w2  # блок qa-findings из сообщения → findings.json
python3 $S/recheck.py run $R --subst SERIAL=emulator-5554                  # repro каждой находки дважды
python3 $S/recheck.py gate $R                                              # что можно публиковать (код 1 — не всё)
python3 $S/direct_publish.py check $R --id F-001 --repo owner/repo         # publish_mode: direct — gate и дубли
python3 $S/avd_manager.py start qa-api34-small-2gb-2c --owner w2 --run-dir $R   # стенд потока; повторный start того же AVD — 3
# 1.2.0: звук в микрофон, долгие сценарии, экраны без дерева, аннотации, формы issue, вложения веткой
python3 $S/avd_manager.py start qa-api34-pixel7-8gb-4c --mic-inject --run-dir $R   # gRPC с токеном (не печатается)
python3 $S/adb_helpers.py mic-inject --wav $R/raw/speech-16k.wav --serial emulator-5554 --run-dir $R   # gRPC → loopback → файл
python3 $S/adb_helpers.py job start --name rec30 --serial emulator-5556 --run-dir $R -- soak --minutes 30 --expect-text "Идёт запись" --stop-xy 540,2040 --expect-duration
python3 $S/adb_helpers.py job status --run-dir $R                          # прогресс фоновых задач; invalid — предусловие не выполнено
python3 $S/adb_helpers.py dump-ui --texts --serial emulator-5554 --run-dir $R   # все тексты целиком с границами
python3 $S/adb_helpers.py tap 540 2040 --no-ui --serial emulator-5554 --run-dir $R   # экран с бесконечной анимацией
python3 $S/finding.py add $R --title "…" --severity medium --direction visual-ui --shot $R/screenshots/x.png --mark "80,1440,920,120|Подпись обрезана|error"
python3 $S/issue_forms.py fetch --repo owner/repo --out $R/raw/forms/owner__repo     # их формы issue (только чтение)
python3 $S/render_draft.py all $R/findings.json --run-dir $R --repo owner/repo --form auto --human-steps
python3 $S/attachments.py push $R --repo owner/repo --branch qa-screens --dir qa/run1 --yes    # скриншоты веткой — до issues
# 1.3.0: график PSS, контактный лист, job stop на Windows
python3 $S/build_report.py report $R                                      # + charts/soak-*-pss.svg под «Длинными сценариями»
python3 $S/annotate_android.py sheet --soak $R/raw/soak-rec30-emulator-5556.json --out $R/screenshots/rec30-sheet.png   # 8 снимков на лист
python3 $S/adb_helpers.py job stop rec30 --grace 180 --run-dir $R          # Windows: ждёт сводку soak до 180 с
```
Короткая форма для zsh и bash — обёртка `qa`: `export QA_RUN_DIR=<RUN_DIR>` и `<SKILL_DIR>/scripts/qa emulator-5554 tap --text "Далее"` (Windows — `qa.ps1`).

**Fail closed.** `guard.py` отвечает кодом 4, `adb_helpers.py` — кодом 6, если guard не может решить (нет или битый `run-config.yaml`, неверное правило): на устройстве ничего не выполняется, исполнитель останавливается. `adb kill-server` запрещён (обрывает все стенды всех потоков).

## Базовые запреты (всегда)
Не покупать, не оформлять подписки и не платить — и в эмуляторе тоже; не входить через внешние аккаунты и не добавлять аккаунты; не звонить и не отправлять SMS и письма; не отправлять сообщения, отзывы и приглашения людям без разрешения на каждое; не удалять аккаунты и данные пользователей; не давать права администратора и специальных возможностей; не взаимодействовать с чужими приложениями; не трогать реальные устройства и чужие эмуляторы без явного разрешения; не менять и не удалять AVD пользователя; никаких атак, инъекций и нагрузки; маскирование секретов и персональных данных. Подробно — `references/safety-rules.md`; проверка — `scripts/guard.py`.

## Зависимости
| Обязательно | Как поставить (подробно — INSTALL.md) |
|-------------|---------------------------------------|
| Python 3.9+ (только стандартная библиотека) | python.org / системный |
| Android SDK: platform-tools (adb), build-tools (aapt2, apksigner) | Android Studio или command-line tools + `sdkmanager` |
| Для эмуляторов: emulator, system image под ABI хоста, cmdline-tools (avdmanager, sdkmanager), JDK 17+, аппаратное ускорение | `sdkmanager "emulator" "system-images;android-34;google_apis;arm64-v8a"` |

| Желательно | Зачем |
|------------|-------|
| bundletool | AAB → APK |
| gh + вход | сверка с issues и (после «да») публикация |
| scrcpy, Maestro, Appium (uiautomator2) | показ экрана, повторяемые сценарии — необязательные усилители |
| Node.js 18+ и Playwright в `scripts/node` (`npm install` локально) | аннотированные скриншоты (`annotate.js` — вендорная копия из site-qa-audit) и PNG контактного листа (`sheet.js`); без них — HTML-лист |
| виртуальное аудиоустройство (BlackHole / Loopback / snd-aloop / VB-Cable) | только для пути loopback подачи звука (macOS, Linux; на Windows — только вручную); скил его не ставит, только проверяет |
| Скилы ui-ux-pro-max, laws-of-ux, ux-heuristics, ux-audit, ux-design-principles, qa-skills (resilience-audit, adversarial-audit — только пассивно) | методики для направлений, `references/plugins-map.md` |

## Ограничения
- Только то, что видно через интерфейс и adb: причина дефекта — гипотеза, код не анализируется.
- Кириллица и emoji через `adb input text` не вводятся: `text … --clipboard` (буфер обмена эмулятора по gRPC, эмулятор с `--mic-inject`; не для секретов), `text … --adbkeyboard` (ADBKeyBoard на эмуляторе скила: `ime install-adbkeyboard --apk …` с согласия пользователя, APK даёт пользователь), `text … --translit` (латиницей, с пометкой) или вручную в окне эмулятора.
- Звук в микрофон: путь gRPC — только свой эмулятор, запущенный с `--mic-inject`, файл WAV PCM; loopback — только если пользователь сам поставил и выбрал виртуальное устройство (на Windows автоматически не поддерживается: без сторонних модулей не узнать устройство по умолчанию — `references/audio-input.md`); иначе — импорт файла (живой микрофон тогда не проверяется). Клиент gRPC проверен только на поддельном сервере — живой прогон с эмулятором не выполнялся.
- Новый скил виден только в новой сессии Claude Code (в текущей — «Unknown skill»); продолжить в той же сессии — прочитать `SKILL.md` и идти по шагам.
- Экраны без дерева элементов (игры на canvas, видео, `FLAG_SECURE`) проверяются по скриншотам; нажатия по координатам — с оценкой смысла кнопки исполнителем.
- Язык системы и часовой пояс надёжно меняются только перезапуском эмулятора (`--locale`, `--timezone`); язык приложения через adb — с API 33.
- Ограничение скорости сети — только на эмуляторе; на реальном устройстве — только Wi-Fi/данные с согласия.
- Образы старше API 24 под arm64 (Apple Silicon) обычно отсутствуют: нижняя граница minSdk проверяется на реальном устройстве или x86_64-хосте.
- Подпись AAB проверяется только у собранных из него APK (bundletool подписывает отладочным ключом — подпись отличается от магазинной).
- GitHub не принимает картинки через `gh`: вложения — веткой в репозиторий до создания issues (`attachments.py`, ссылки `blob/…?raw=true`) или ссылками на локальные файлы.
- Безопасность — только пассивная; это не пентест.
- Версия 1.0.0 проверена офлайн и первым боевым прогоном на эмуляторе (smoke, API 34); 1.0.1 — исправления по нему, проверены офлайн (фейковые adb и SDK); 1.1.0 (fail closed, находки текстом, перепроверка, прямая публикация, стенды потоков) — только офлайн; 1.2.0 (микрофон, soak и job, экраны без дерева, аннотации, формы issue, вложения веткой) — офлайн на фейковых adb, SDK, gh, node и поддельном сервере gRPC; 1.3.0 — офлайн, контактный лист и SVG-график дополнительно отрисованы вживую (Chromium через Playwright, просмотр в macOS), `job stop` на Windows не проверялся (поведение Windows проверено режимом `ANDROID_QA_JOB_STOP=file`); статус «в разработке».
- Правовые утверждения (разрешения, персональные данные, реклама) — только факты и «возможно применимо»; вторая проверка другим исполнителем и юристом обязательна.

## Структура
```text
SKILL.md                порядок работы
INSTALL.md              установка и обновление, настройка Android SDK, промпты для Claude Code
references/             setup, intake, safety-rules, stands, device-control, audio-input, long-runs, screenshots,
                        depth-matrix, parallelism, plugins-map, severity, repo-sync, run-files,
                        checklists/ (11 направлений + audio-voice)
templates/              run-config.example.yaml, finding.schema.json, issue-detailed.md, run-report.md, app-context.md
scripts/                check_env (.py/.sh/.ps1), apk_info, avd_manager, adb_helpers, guard, masking, matrix, intake,
                        journal, fingerprint, validate_findings, render_draft, build_report, gitignore_helper,
                        export_results, sdkutil, grpc_emu, mic, soak, annotate_android, finding, issue_forms,
                        known_docs, attachments, qa (+ qa.ps1), node/ (annotate.js — копия из site-qa-audit, sheet.js),
                        shared/ (вендоренные модули репозитория)
tests/                  unit.sh + v12.sh + v13.sh, helpers/ (фейковые adb, SDK, gh, node, сервер gRPC), helpers/shared/
                        (общие проверки примеров документации — копии shared/tests), fixtures/
```
