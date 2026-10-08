# Работа с устройством: `scripts/adb_helpers.py`

Общие опции: `--serial S` (или `ANDROID_SERIAL`, или единственное устройство), `--run-dir <RUN_DIR>` (файлы прогона, журналы, `run-config.yaml` оттуда), `--config`, `--confirmed` (только после «да» пользователя на код 2). `PKG` по умолчанию — `app.package` из run-config. Вывод — JSON (кроме `dump-ui`). Коды: 0 — выполнено, 2 — нужно подтверждение (не выполнено), 3 — запрещено guard (не выполнено, `logs/blocked.jsonl`), 4 — не поддерживается на этом устройстве, 5 — ошибка.

Журналы: `logs/actions.jsonl` — каждое выполненное действие; `logs/blocked.jsonl` — запреты; `raw/metrics.jsonl` — метрики; `raw/crashes-<serial>.json` — падения.

## Цикл работы с интерфейсом
Аналог «снимок страницы → действие → проверка» для браузера:
1. `dump-ui` — дерево элементов активного окна (uiautomator): строки вида `[5] Button "Далее" id=btn_next @540,1500 (clickable)`, файл `raw/ui-<время>.xml` (замаскирован) и кандидаты находок (`a11y.missing-label`, `a11y.touch-target`, `visual.offscreen`, `visual.overlap`, `visual.text-ellipsized`). `--json raw/ui-<экран>.json` — все узлы с границами.
2. Выбрать элемент по **тексту, id или contentDescription**, не по координатам: `tap --text "Далее"`, `tap --id btn_next`, `tap --desc "Закрыть"` (`--index N` при нескольких совпадениях, `--exact` — точное совпадение).
3. Скрипт снова снимает дерево, находит элемент и проверяет его `guard.py` (текст, описание, id, класс, пакет, activity, тексты экрана как контекст). Затем нажатие, пауза `parallel.throttle_ms`, вывод `focus` — какой пакет и activity теперь на экране. Открылось чужое приложение → `left_app` в выводе и запись в `blocked.jsonl`: `key BACK`.
4. `screenshot` (→ `screenshots/`) до и после важного шага; для находки — с понятным именем: `screenshot <RUN_DIR>/screenshots/F-003-profile-overlap.png`.
5. Если дерево пустое или элемента нет (игры, canvas, видео, `FLAG_SECURE`): смотреть скриншот; нажатие по координатам `tap X Y` — guard проверит элемент под точкой, а смысл кнопки на картинке исполнитель оценивает сам (`safety-rules.md` §1).

```bash
S=<SKILL_DIR>/scripts; R=<RUN_DIR>; D="--serial emulator-5554 --run-dir $R"
python3 $S/adb_helpers.py launch --cold $D               # запуск с остановкой процесса; TotalTime в выводе
python3 $S/adb_helpers.py dump-ui $D
python3 $S/adb_helpers.py tap --text "Каталог" $D
python3 $S/adb_helpers.py text "test query" --into-id search_field $D
python3 $S/adb_helpers.py key ENTER $D
python3 $S/adb_helpers.py scroll down $D
python3 $S/adb_helpers.py screenshot $D
python3 $S/adb_helpers.py key BACK $D
```

## Ввод текста
`text "abc"` — через `adb shell input text` (пробелы передаются как `%s`). **Кириллица, emoji и другой не-ASCII через adb не вводятся** (код 4): ввести вручную в окне эмулятора, или поставить на свой эмулятор ADBKeyBoard (стороннее приложение — с согласия пользователя; скрипт использует его сам, если он установлен), или проверить такие значения на экране, где они уже есть. Секреты — `text --env QA_PASSWORD`: значение берётся из переменной, не печатается и не пишется в журнал.

## Приложение
| Команда | Что делает |
|---------|-----------|
| `install APK… [--replace] [--downgrade] [--grant-all] [--allow-test]` | установка (split — несколько файлов); пакет сверяется с `app.package` |
| `uninstall [PKG] [--keep-data]`, `clear [PKG]` | только тестируемое приложение |
| `launch [PKG] [--activity A] [--cold]` | `am start -W`: `LaunchState`, `TotalTime`; без activity — launcher из `cmd package resolve-activity` |
| `stop [PKG]` | `am force-stop` |
| `kill-bg [PKG]` | HOME → `am kill` → процесс убит в фоне (как системой при нехватке памяти); вернуться через `key APP_SWITCH` и нажатие на карточку или `launch` — проверить восстановление состояния |
| `trim-memory LEVEL [PKG]` | `am send-trim-memory`: `RUNNING_LOW`, `RUNNING_CRITICAL`, `COMPLETE`… |
| `deeplink URI [--package P]` | `am start -a VIEW -d URI` после `guard.py deeplink` |
| `appinfo [PKG]`, `current`, `info` | версия, флаги и разрешения; экран на переднем плане; модель, API, экран, density, ОЗУ, шрифт, тема, батарея |

## Конфигурация (вариации матрицы, `matrix.py variants`)
| Команда | Реализация | Ограничения |
|---------|-----------|-------------|
| `rotate portrait\|landscape\|reverse-portrait\|reverse-landscape\|auto` | `cmd window user-rotation lock` (API 31+) или `settings put system user_rotation` | приложение может запрещать поворот — это не дефект само по себе |
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
`permissions [PKG]` — runtime-разрешения и состояние; `grant PERM [PKG]` / `revoke PERM [PKG]` (короткое имя `CAMERA` или полное); `notifications [PKG]` — уведомления только этого приложения (замаскированы); `shade open|close` — шторка. Диалоги разрешений при первом запросе проверять нажатиями «Разрешить» / «Только сейчас» / «Запретить» — это системный интерфейс, guard их разрешает.

## Журналы и падения
| Команда | Что делает |
|---------|-----------|
| `logcat start [--out F]` | фоновая запись `logcat -v threadtime -b main,system,crash` в `logs/logcat-<serial>.txt` |
| `logcat stop` | остановить и **замаскировать** файл |
| `logcat dump [--package P] [--lines N] [--out F]` | снимок журнала (замаскирован), с фильтром по процессу приложения |
| `logcat clear` | `logcat -c` — на реальном устройстве нужно согласие `full` |
| `crashes [PKG]` | FATAL EXCEPTION, ANR, нативные падения из logcat и `dumpsys dropbox` → `raw/crashes-<serial>.json` (замаскировано) |

## Метрики (в `raw/metrics.jsonl`, сводка — в report.md)
| Команда | Что меряет | Ориентиры |
|---------|-----------|-----------|
| `start-time [PKG] --mode cold\|warm\|hot --runs 5` | `am start -W` TotalTime: медиана, мин, макс | Android vitals: холодный > 5 с, тёплый > 2 с, горячий > 1,5 с — чрезмерно |
| `meminfo [PKG]` | PSS, RSS, Java/Native heap, Graphics, Views, Activities | рост Activities/Views после повторов — подозрение на утечку |
| `gfxinfo [PKG] [--reset]` | кадры, jank %, p50/p90/p95/p99 | `--reset` → сценарий → `gfxinfo`; p90 > 16 мс при 60 Гц — заметные подёргивания |
| `batterystats [PKG] [--reset]` | сырой отчёт в `logs/`, wakelocks | `--reset` меняет статистику устройства |
| `size [PKG]` | размер APK на устройстве, данные, кэш (`dumpsys diskstats`, приблизительно) | |
| `monkey [PKG] --events 500 --seed 42 --throttle 300` | случайные нажатия только по этому пакету, `--pct-syskeys 0`; падение/ANR и строка для повтора | только свой эмулятор; есть аккаунты на устройстве — спросить |

## Снимки и видео
`screenshot [OUT]` (`exec-out screencap -p`), `screenrecord [OUT] --seconds 20` (до 180 с, во временный `/sdcard/qa-rec-*.mp4`, затем `pull` в `recordings/` и удаление с устройства). Экран с `FLAG_SECURE` снимается чёрным или с ошибкой — это защита приложения, не дефект. Скриншоты с персональными данными не публиковать.

## Усилители
Если установлены (`check_env` → `optional`): Maestro — сценарии YAML (`maestro test flow.yaml`), Appium с драйвером uiautomator2 — сложные жесты и ожидания, scrcpy — показать экран устройства пользователю. Их действия обходят guard: использовать только для чтения/наблюдения или на своём эмуляторе для сценариев, которые сначала проверены по правилам (`plugins-map.md`).
