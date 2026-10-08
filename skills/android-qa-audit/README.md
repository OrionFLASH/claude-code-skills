# android-qa-audit

QA-тестирование Android-приложения — по APK, split APK, `.apks`, AAB или уже установленному пакету — на эмуляторах и подключённых устройствах через adb, без исходного кода. Скил разбирает APK, сам находит и готовит стенды (создаёт AVD `qa-*` с нужной версией Android, ОЗУ, ядрами, экраном), строит матрицу «версии Android × железо × настройки», проходит приложение как пользователь и как инструменты (дерево элементов, logcat, dumpsys, monkey), до 4 стендов одновременно, и складывает находки, отчёт и черновики GitHub issues в папку прогона.

Внутри скила нет конкретных приложений, пакетов, репозиториев, логинов и токенов: всё передаётся на входе.

**Установка, настройка Android SDK и обновление** (macOS, Windows, Linux, промпты для Claude Code) — [INSTALL.md](INSTALL.md).

**Запуск.** Командой `/android-qa-audit` или обычной просьбой протестировать или проверить приложение, APK, Android-приложение, найти баги, проверить на разных версиях Android или на слабом телефоне, в том числе с путём к `.apk`. Если скил подхвачен по смыслу, он сначала спрашивает: «Похоже, вы хотите протестировать Android-приложение <что понял>. Запустить?» — при «Нет, это другое» ничего не создаёт. На разработку приложения, написание тестов Espresso/Appium и сайты (для них — `site-qa-audit`) не срабатывает.

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

Результаты — в `<OUTPUT_ROOT>/qa-runs/<YYYY-MM-DD>-<package>/`: `run-config.yaml`, `env.json`, `apk-info.json`, `device-matrix.json`, `stands.json`, `journal.md`, `findings.json`, `report.md`, `summary.md`, `apk/` (копии с SHA256), `screenshots/`, `recordings/`, `logs/` (logcat, действия, запреты), `raw/`, `drafts/`. Память о приложении — `<OUTPUT_ROOT>/qa-runs/.app-context/<package>/context.md`. Если папка внутри git-репозитория — в конце один вопрос про `.gitignore` для `qa-runs/` и `*.apk`, `*.aab`, `*.apks`, `*.keystore`; и вопрос, что сделать с эмуляторами и AVD прогона.

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
python3 $S/apk_info.py analyze app.apk --copy-to $R/apk --out $R/apk-info.json --summary
python3 $S/intake.py from-text --file request.txt --output-dir <OUTPUT_ROOT> --out $R/run-config.yaml
python3 $S/matrix.py build --config $R/run-config.yaml                      # матрица и потоки
python3 $S/avd_manager.py install-image --api 34                            # план загрузки образа; --yes после «да»
python3 $S/avd_manager.py create --api 34 --profile small --ram 2048 --cores 2 --yes --run-dir $R
python3 $S/avd_manager.py start qa-api34-small-2gb-2c --headless --run-dir $R && python3 $S/avd_manager.py wait-boot emulator-5554 --unlock
python3 $S/adb_helpers.py install $R/apk/app.apk --serial emulator-5554 --run-dir $R
python3 $S/adb_helpers.py dump-ui --serial emulator-5554 --run-dir $R      # дерево элементов + кандидаты a11y/visual
python3 $S/adb_helpers.py tap --text "Далее" --serial emulator-5554 --run-dir $R   # нажатие под guard (3 — запрет, 2 — спросить)
python3 $S/adb_helpers.py kill-bg --serial emulator-5554 --run-dir $R      # смерть процесса в фоне
python3 $S/adb_helpers.py start-time --mode cold --runs 5 --serial emulator-5554 --run-dir $R
python3 $S/adb_helpers.py crashes --serial emulator-5554 --run-dir $R
python3 $S/fingerprint.py compute $R/findings.json && python3 $S/fingerprint.py dedupe $R/findings.json
python3 $S/validate_findings.py $R/findings.json
python3 $S/render_draft.py all $R/findings.json --run-dir $R --repo owner/repo   # черновики, ничего не публикует
python3 $S/build_report.py report $R && python3 $S/build_report.py summary $R
python3 $S/gitignore_helper.py check <OUTPUT_ROOT>
python3 $S/avd_manager.py cleanup --run-dir $R --stop --delete-avds         # план; --yes после ответа
```

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
| Скилы ui-ux-pro-max, laws-of-ux, ux-heuristics, ux-audit, ux-design-principles, qa-skills (resilience-audit, adversarial-audit — только пассивно) | методики для направлений, `references/plugins-map.md` |

## Ограничения
- Только то, что видно через интерфейс и adb: причина дефекта — гипотеза, код не анализируется.
- Кириллица и emoji через `adb input text` не вводятся — вручную в окне эмулятора или ADBKeyBoard с согласия пользователя.
- Экраны без дерева элементов (игры на canvas, видео, `FLAG_SECURE`) проверяются по скриншотам; нажатия по координатам — с оценкой смысла кнопки исполнителем.
- Язык системы и часовой пояс надёжно меняются только перезапуском эмулятора (`--locale`, `--timezone`); язык приложения через adb — с API 33.
- Ограничение скорости сети — только на эмуляторе; на реальном устройстве — только Wi-Fi/данные с согласия.
- Образы старше API 24 под arm64 (Apple Silicon) обычно отсутствуют: нижняя граница minSdk проверяется на реальном устройстве или x86_64-хосте.
- Подпись AAB проверяется только у собранных из него APK (bundletool подписывает отладочным ключом — подпись отличается от магазинной).
- GitHub не принимает картинки через `gh`: вложения — коммитом в свой репозиторий или ссылками на локальные файлы.
- Безопасность — только пассивная; это не пентест.
- Версия 1.0.0 проверена офлайн (фейковые adb и SDK) и только чтением на машине с Android SDK; живой прогон на эмуляторе — следующий шаг (статус «в разработке»).

## Структура
```text
SKILL.md                порядок работы
INSTALL.md              установка и обновление, настройка Android SDK, промпты для Claude Code
references/             setup, intake, safety-rules, stands, device-control, depth-matrix, parallelism,
                        plugins-map, severity, repo-sync, run-files, checklists/ (11 направлений)
templates/              run-config.example.yaml, finding.schema.json, issue-detailed.md, run-report.md, app-context.md
scripts/                check_env (.py/.sh/.ps1), apk_info, avd_manager, adb_helpers, guard, masking, matrix, intake,
                        journal, fingerprint, validate_findings, render_draft, build_report, gitignore_helper, sdkutil,
                        shared/ (вендоренные модули репозитория)
tests/                  unit.sh, helpers/ (фейковые adb и SDK), fixtures/
```
