# Работа с устройством: `scripts/adb_helpers.py`

Общие опции: `--serial S` (или `ANDROID_SERIAL`, или единственное устройство), `--run-dir <RUN_DIR>` (файлы прогона, журналы, `run-config.yaml` оттуда), `--config`, `--confirmed` (только после «да» пользователя на код 2). `PKG` по умолчанию — `app.package` из run-config. Вывод — JSON (кроме `dump-ui`). Коды: 0 — выполнено, 2 — нужно подтверждение (не выполнено), 3 — запрещено guard (не выполнено, `logs/blocked.jsonl`), 4 — не поддерживается на этом устройстве, 5 — ошибка.

Журналы: `logs/actions.jsonl` — каждое выполненное действие; `logs/blocked.jsonl` — запреты; `raw/metrics.jsonl` — метрики; `raw/crashes-<serial>.json` — падения (`items` — приложения, `other_processes` — чужие процессы).

## Цикл работы с интерфейсом
Аналог «снимок страницы → действие → проверка» для браузера:
1. `dump-ui` — дерево элементов активного окна (uiautomator): строки вида `[5] Button "Далее" id=btn_next @540,1500 (clickable)`, файл `raw/ui-<время>.xml` (замаскирован) и кандидаты находок (`a11y.missing-label`, `a11y.touch-target`, `visual.offscreen`, `visual.overlap`, `visual.text-ellipsized`). Подписи в списке обрезаны до 60 символов: **`dump-ui --texts`** — все тексты и contentDescription целиком, с границами и `box=x,y,w,h` (для `--mark`); `--grep "регэксп"` — только подходящие узлы. `--json raw/ui-<экран>.json` — все узлы с границами и `screen` (размер, поворот, источник). Размер экрана для `visual.offscreen` — по повороту **этого** дампа (`<hierarchy rotation="N">` + `wm size`), запасной путь — `dumpsys window displays` (`cur=WxH` — логический экран с системными панелями и вырезом); после `rotate landscape` границы сверяются с 2400×1080, а не с 1080×2400.
2. Выбрать элемент по **тексту, id или contentDescription**, не по координатам: `tap --text "Далее"`, `tap --id btn_next`, `tap --desc "Закрыть"`. Совпадения ранжируются: точный текст раньше подстроки, кликабельный элемент (или внутри кликабельного) раньше простого текста, включённый раньше выключенного, короткий текст раньше абзаца, который лишь содержит слово (кнопка «Расшифровать», а не вопрос «…Расшифровать?» в диалоге). Несколько **равных** кандидатов в разных местах → код 2 и `ambiguous: N matches` со списком (`index`, текст, границы) — уточнить `--exact` / `--id` / `--desc` или выбрать `--index N`.
3. Скрипт снова снимает дерево, находит элемент и проверяет его `guard.py` (текст, описание, id, класс, пакет, activity, тексты экрана как контекст). Затем нажатие, пауза `parallel.throttle_ms`, вывод `focus` — какой пакет и activity теперь на экране. Открылось чужое приложение → `left_app` в выводе и запись в `blocked.jsonl`: `key BACK`. **Проверить, что экран изменился**: `--expect-text "…"` (появился текст), `--expect-gone "…"` (пропал), `--expect-change` (дерево другое), ждать до `--wait` секунд; не выполнено → код 5, `"ok": false`, `expect.reason` (нажатие прошло, но ничего не произошло).
4. `screenshot` (→ `screenshots/`) до и после важного шага; для находки — с понятным именем и сразу с разметкой: `screenshot <RUN_DIR>/screenshots/F-003-profile-overlap.png --mark "text=Сохранить|Подпись обрезана|error"` (`screenshots.md`).
5. Если дерево пустое или элемента нет (игры, canvas, видео, `FLAG_SECURE`): смотреть скриншот; нажатие по координатам `tap X Y` — guard проверит элемент под точкой, а смысл кнопки на картинке исполнитель оценивает сам (`safety-rules.md` §1).

```bash
export QA_RUN_DIR=<RUN_DIR>                                   # папка прогона для обёртки qa
<SKILL_DIR>/scripts/qa emulator-5554 launch --cold             # запуск с остановкой процесса; TotalTime, фокус окна
<SKILL_DIR>/scripts/qa emulator-5554 dump-ui --texts
<SKILL_DIR>/scripts/qa emulator-5554 tap --text "Каталог" --expect-change
<SKILL_DIR>/scripts/qa emulator-5554 text "test query" --into-id search_field
<SKILL_DIR>/scripts/qa emulator-5554 key ENTER
<SKILL_DIR>/scripts/qa emulator-5554 scroll down               # changed: false — конец списка
<SKILL_DIR>/scripts/qa emulator-5554 screenshot
<SKILL_DIR>/scripts/qa emulator-5554 key BACK
```
**Обёртка `qa`** (`scripts/qa`, Windows — `scripts\qa.ps1`): `qa <serial> <команда adb_helpers.py> [аргументы]` добавляет `--serial` и `--run-dir "$QA_RUN_DIR"`; `-` вместо serial — `ANDROID_SERIAL` или единственное устройство. Так примеры работают и в zsh, и в bash; переменные-команды вида «A равно python3 …» с вызовом `$A …` в zsh не делятся на слова — их не использовать. Полная форма: `python3 <SKILL_DIR>/scripts/adb_helpers.py <команда> … --serial emulator-5554 --run-dir <RUN_DIR>`.

## Экраны без дерева элементов (бесконечная анимация)
На экране с непрерывной анимацией (запись, таймер, эквалайзер) uiautomator отвечает «could not get idle state».
- `dump-ui --retry 6` — больше попыток с нарастающей паузой; `--ignore-animations` — на время дампа масштаб анимаций 0 (`settings put global …` через guard — на реальном устройстве нужно согласие `full`), затем прежние значения; бесконечные `ValueAnimator` при этом останавливаются.
- **`tap X Y --no-ui`** — нажатие без нового дерева: элемент под точкой берётся из **последнего снимка дерева** этого стенда (не старше 120 с и на той же activity) и проверяется guard как обычно; снимка нет — guard проверяет **пакет и экран** переднего плана (чужое приложение, запрещённый экран, системное приложение — как всегда), в выводе `element_checked: false` и `screenshot_before` — снимок до нажатия (посмотреть его до нажатия по смыслу, `safety-rules.md` §3 п. 1). Нажатие пишется в `logs/actions.jsonl`.
- `tap` без `--no-ui` на таком экране — код 5 с подсказкой, ничего не нажато.
- `--expect-text/--expect-gone/--expect-change` после `--no-ui` — только если следующий экран без анимации (их проверка снимает дерево); иначе — `screenshot` после нажатия или `soak --service` (сервис работает / остановлен).

## Файлы и системный выбор файла
| Команда | Что делает |
|---------|-----------|
| `push-media FILE [--folder Download] [--name N]` | файл → `/sdcard/<папка>/qa-<имя>` (только имена `qa-*`: их можно удалить) + медиасканер; `--remove N` — удалить свой файл |
| `import-file --name qa-<имя> [--folder Download] [--retries 4] [--scroll 6]` | приложение уже открыло системный выбор файла (Documents UI): открыть список папок («Show roots» / «Показать корневые папки»), папку (Download / Загрузки, Music / Музыка…), найти файл по имени с повторами и прокруткой, нажать; кнопка «Выбрать / Select» — тоже. Выбор файла не открыт — код 4 |

Выбор файла — системное приложение: каждое нажатие в нём guard отдаёт на подтверждение (код 2). **Одно `--confirmed` покрывает весь вызов `import-file`** (одно согласие на импорт, а не на каждое нажатие); `rules.preapproved_packages: [com.google.android.documentsui]` в run-config — согласие на весь прогон после одного вопроса пользователю («Разрешить работу с системным выбором файла на стендах прогона?»). Запреты (`deny`) это не снимает.

## Ввод текста
`text "abc"` — через `adb shell input text` (пробелы передаются как `%s`). **Кириллица, emoji и другой не-ASCII через `adb input` не вводятся.** По умолчанию — отказ (код 4) с подсказкой, ничего не нажимается и не вводится. Варианты:
| Вариант | Команда | Что получится |
|---------|---------|---------------|
| Латиница | `text "QA Тест" --translit` | вводится `QA Test`; в выводе `"translit": true` и `typed` — указать в шагах находки «введено латиницей»; emoji и неизвестные символы — отказ (4); секрет (`--env`) транслитерировать нельзя (2) |
| Буфер обмена | `text "QA Тест" --clipboard` | **без установки чего-либо**: на эмуляторе скила, запущенном с `--mic-inject` (gRPC с токеном, `audio-input.md`), текст кладётся в буфер обмена эмулятора (`setClipboard`) и вставляется `KEYCODE_PASTE` в поле с фокусом (`--into-id` / `--into-text`); буфер эмулятора синхронизируется с хостом — **не для секретов** (`--env` → код 2) |
| ADBKeyBoard | `text "QA Тест" --adbkeyboard` | только на **эмуляторе скила** (`qa-*`) и только если ADBKeyBoard на нём уже установлен (`ime status`): `ime set` → `am broadcast ADB_INPUT_B64` → прежняя клавиатура возвращается; поставить: `ime install-adbkeyboard --apk <ADBKeyboard.apk>` — APK даёт пользователь (скил не скачивает), стороннее приложение — код 2, повтор с `--confirmed` после «да»; реальное устройство и чужой AVD — отказ (4) |
| Вручную | — | ввести в окне эмулятора (не headless) или проверить значения на экране, где они уже есть |

Секреты — `text --env QA_PASSWORD`: значение берётся из переменной, не печатается и не пишется в журнал (с `--adbkeyboard` — тоже). Если в запросе есть проверки на кириллице (поиск по русскому тексту, названия папок), `intake.py` сразу подсказывает `--clipboard` или ADBKeyBoard.

## Приложение
| Команда | Что делает |
|---------|-----------|
| `install APK… [--replace] [--downgrade] [--grant-all] [--allow-test]` | установка (split — несколько файлов); пакет сверяется с `app.package` |
| `uninstall [PKG] [--keep-data]`, `clear [PKG]` | только тестируемое приложение |
| `launch [PKG] [--activity A] [--cold] [--wait-focus 5]` | `am start -W` (ждёт первый кадр): `LaunchState`, `TotalTime`; затем до `--wait-focus` секунд ждёт, пока окно приложения получит фокус (`focused`, `focus_wait_ms`) — после заставки `dump-ui` и `tap` видят приложение; без activity — launcher из `cmd package resolve-activity` |
| `stop [PKG]` | `am force-stop` |
| `kill-bg [PKG]` | HOME → `am kill` → процесс убит в фоне (как системой при нехватке памяти); вернуться через `key APP_SWITCH` и нажатие на карточку или `launch` — проверить восстановление состояния |
| `trim-memory LEVEL [PKG]` | `am send-trim-memory`: `RUNNING_LOW`, `RUNNING_CRITICAL`, `COMPLETE`… |
| `deeplink URI [--package P]` | `am start -a VIEW -d URI` после `guard.py deeplink` |
| `appinfo [PKG]`, `current`, `info` | версия, флаги и разрешения; экран на переднем плане; модель, API, экран, density, ОЗУ, шрифт, тема, батарея |

## Конфигурация (вариации матрицы, `matrix.py variants`)
| Команда | Реализация | Ограничения |
|---------|-----------|-------------|
| `rotate portrait\|landscape\|reverse-portrait\|reverse-landscape\|auto` | `cmd window user-rotation lock` (API 31+) или `settings put system user_rotation`; ждёт поворота до 5 с и возвращает **фактический** размер (`screen`), `rotation_index`, `applied` | приложение может запрещать поворот (`applied: false`) — это не дефект само по себе |
| `font-scale 1.3` | `settings put system font_scale` | 2.0 — максимум на Android 14+ |
| `density N\|reset` | `wm density` (масштаб экрана) | вернуть `reset` |
| `dark-mode on\|off\|auto` | `cmd uimode night` | API 29+ |
| `locale ru-RU [PKG]` | `cmd locale set-app-locales` — язык приложения | API 33+; системный язык — `avd_manager.py start … --locale`; после смены — `stop` + `launch` |
| `timezone Europe/Moscow` | `cmd alarm set-timezone` / `service call alarm` | не сработало — `avd_manager.py start … --timezone` |
| `network offline\|online\|4g\|3g\|edge\|gprs\|full\|switch [--seconds N]` | режим полёта (`cmd connectivity airplane-mode`, API 30+) или `svc wifi/data`; скорость — `adb emu network speed/delay` | скорость — только свой эмулятор; `switch` — Wi-Fi выключить на N секунд |
| `battery level N\|unplug\|reset\|saver-on\|saver-off` | `dumpsys battery`, `cmd power set-mode` / `settings put global low_power` | после теста — `battery reset` |
| `doze enter\|exit`, `standby on\|off [PKG]` | `dumpsys deviceidle force-idle`, `am set-inactive` | |
| `animations off\|on` | масштаб анимаций 0/1 | для стабильных UI-проверок; на метрики jank — включённые |

На реальном устройстве настройки устройства — только при согласии `full` (иначе код 2). После ячейки — вернуть всё (команды сброса в `device-matrix.json → variants.*.reset`).

## Разрешения и уведомления
`permissions [PKG]` — runtime-разрешения и состояние; `grant PERM [PKG]` / `revoke PERM [PKG]` (короткое имя `CAMERA` или полное); `shade open|close` — шторка. Диалоги разрешений при первом запросе проверять нажатиями «Разрешить» / «Только сейчас» / «Запретить» — это системный интерфейс, guard их разрешает.

`notifications [PKG]` — **все активные** уведомления этого приложения (замаскированы), в том числе постоянные и foreground-сервиса: `id`, `channel`, `importance`, `category` (`progress`, `service`…), `flags`, `ongoing`, `foreground_service`, `title` / `text` / `sub_text` / `big_text`, `progress` / `progress_max` / `percent` / `indeterminate`, `actions` (тексты кнопок). Архив и история уведомлений не считаются. `foreground_services` — сервисы приложения на переднем плане (`dumpsys activity services`); есть сервис, а его уведомления в списке нет — `note`: проверить шторку глазами (`shade open` + `screenshot`).

## Журналы и падения
| Команда | Что делает |
|---------|-----------|
| `logcat start [--out F] [--package P] [--all]` | фоновая запись `logcat -v threadtime -b main,system,crash` в `logs/logcat-<serial>.txt`; **по умолчанию только приложение** (`app.package` или `--package`): строки его процессов (PID, в т.ч. `pkg:service`; после перезапуска — новый PID по «Start proc» и опросу `ps`), строки с именем пакета (запуск, ANR, смерть процесса) и продолжения многострочных записей; фоновый шум (сервисы Google, система) не пишется. `--all` — весь журнал устройства |
| `logcat stop [--summary]` | остановить и **замаскировать** файл; `--summary` — `logs/logcat-<serial>.summary.json` и вывод: строк по уровням, частые теги, различные ошибки (числа свёрнуты: «overflow at N ms» ×12), падения и ANR, сколько строк шума отброшено |
| `logcat dump [--package P] [--all] [--lines N] [--out F] [--summary]` | снимок журнала (замаскирован), по умолчанию с тем же фильтром по приложению; `--all` — весь |

**Шум эмулятора.** В фильтре по приложению строки уровней V/D/I с тегами графики и буферов эмулятора (`EGL_emulation` — `app_time_stats`, `BufferPoolAccessor*`, `HostConnection`, `eglCodecCommon`, `gralloc4`, `goldfish-*`…) отбрасываются и считаются (`noise_dropped`); W/E/F этих тегов остаются. Свои теги — `logcat.noise_tags: [Тег, Префикс*]` в run-config, всё оставить — `--keep-noise` или `logcat.keep_noise: true`.
| `logcat clear` | `logcat -c` — на реальном устройстве нужно согласие `full` |
| `crashes [PKG]` | FATAL EXCEPTION, ANR, нативные падения по **полному** журналу устройства и `dumpsys dropbox` → `raw/crashes-<serial>.json` (замаскировано). Падение приложения — только его процесс: «Process: <pkg>[:…]» или PID приложения («Start proc», `ps`); ANR — только «ANR in <pkg>». Падения других процессов — `other_processes` с `owner`: `tool` (UiAutomation от `dump-ui`, monkey, am), `system` (system_server, сервисы Google), `other-app`; `related_to_app` — процесс запущен для приложения (WebView) — проверить вручную. Это не находки приложения |

## Метрики (в `raw/metrics.jsonl`, сводка — в report.md)
| Команда | Что меряет | Ориентиры |
|---------|-----------|-----------|
| `start-time [PKG] --mode cold\|warm\|hot --runs 5` | `am start -W` TotalTime: медиана, мин, макс | Android vitals: холодный > 5 с, тёплый > 2 с, горячий > 1,5 с — чрезмерно |
| `meminfo [PKG]` | PSS, RSS, Java/Native heap, Graphics, Views, Activities | рост Activities/Views после повторов — подозрение на утечку |
| `gfxinfo [PKG] [--reset]` | кадры, jank %, p50/p90/p95/p99 | `--reset` → сценарий → `gfxinfo`; p90 > 16 мс при 60 Гц — заметные подёргивания |
| `batterystats [PKG] [--reset]` | сырой отчёт в `logs/`, wakelocks | `--reset` меняет статистику устройства |
| `size [PKG]` | размер APK на устройстве, данные, кэш (`dumpsys diskstats`, приблизительно) | |
| `monkey [PKG] --events 500 --seed 42 --throttle 300` | случайные нажатия только по этому пакету, `--pct-syskeys 0`; падение/ANR и строка для повтора | только свой эмулятор; есть аккаунты на устройстве — спросить |

Каждый замер записывает **загрузку хоста** (`host`: эмуляторов рядом, load average, ядра); `start-time` при нескольких работающих эмуляторах пишет `note` — время искажено, замеры скорости — на свободном хосте (`long-runs.md` → «Замеры времени»). Долгие сценарии с метриками по таймеру — `soak`, фоном — `job` (`long-runs.md`); звук в микрофон — `mic-status` / `mic-inject` (`audio-input.md`).

Общая опция **`--journal-done "<пункт>"`** — после успешной команды отметить пункт `journal.md` (`journal.py done`).

## Снимки и видео
`screenshot [OUT] [--mark "x,y,w,h|подпись|вид"]…` (`exec-out screencap -p`; `--mark` — сразу аннотированная копия `-annotated.png` и spec, `screenshots.md`), `screenrecord [OUT] --seconds 20` (до 180 с, во временный `/sdcard/qa-rec-*.mp4`, затем `pull` в `recordings/` и удаление с устройства). Экран с `FLAG_SECURE` снимается чёрным или с ошибкой — это защита приложения, не дефект. Скриншоты с персональными данными не публиковать.

**Ролики находок** (1.5.0, `clips.md`) — короткие, без звука, сжатые под бюджет, с лентой кадров для просмотра:
| Подкоманда | Что делает |
|---|---|
| `clip-start --name F-003-menu [--seconds 10] [--size 720] [--bit-rate 2000000] [--touches auto\|on\|off]` | `screenrecord` фоном во временный `/sdcard/qa-clip-<name>.mp4`, состояние `raw/clip-<serial>.json`; касания — на эмуляторе прогона; уже идёт — код 2 |
| `clip-stop [--finding F-003 --caption "…" --kind error\|ok\|note\|after] [--mark …] [--step …] [--force]` | SIGINT записи, `pull`, удаление с устройства, возврат `show_touches`, «чёрный экран» (код 5 без `--force`), сжатие → `clips/`, запись в находку |
| `clip-stop --restore-only` | остановить запись без ролика и вернуть настройки |
| `clip --name … [--seconds 8] [--lead 0.5] [--tail 1] [--fallback auto\|frames\|none] [--dry-run] -- <шаг> --then <шаг> …` | старт → шаги (подкоманды этого скрипта через guard; `wait S`) → стоп; запрещённый шаг не выполняется и обрывает цепочку; нет кодека — ролик из скриншотов |
| `clip-rolling start [--segment 8] [--keep 3] \| save --name … [--finding …] [--last 10] \| stop \| status` | непрерывная запись сегментами (для падений), сохранение последних секунд |

```bash
python3 <SKILL_DIR>/scripts/adb_helpers.py clip --name F-003-menu --finding F-003 --caption "Меню закрывается само" --serial emulator-5554 --run-dir <RUN_DIR> -- tap --text "Меню" --then wait 1
```
Коды: 4 — не поддерживается на стенде (API < 19, нет `screenrecord`, нет кодека: эмулятор headless со swiftshader — `avd_manager.py start … --gpu host`).

## Усилители
Если установлены (`check_env` → `optional`): Maestro — сценарии YAML (`maestro test flow.yaml`), Appium с драйвером uiautomator2 — сложные жесты и ожидания, scrcpy — показать экран устройства пользователю. Их действия обходят guard: использовать только для чтения/наблюдения или на своём эмуляторе для сценариев, которые сначала проверены по правилам (`plugins-map.md`).
