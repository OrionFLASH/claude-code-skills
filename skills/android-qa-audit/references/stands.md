# Стенды: эмуляторы, образы, устройства

Скрипт — `scripts/avd_manager.py` (Android SDK находится сам: `ANDROID_HOME`, `ANDROID_SDK_ROOT`, типовые папки; PATH не нужен). Всё, что прогон создал и запустил, записывается в `<RUN_DIR>/stands.json` — по нему работает уборка.

## Обнаружение
```bash
python3 <SKILL_DIR>/scripts/check_env.py --fast --json <RUN_DIR>/env.json   # образы, AVD, устройства, ускорение, ресурсы
python3 <SKILL_DIR>/scripts/avd_manager.py list                              # AVD: владелец, API, ABI, ОЗУ, ядра, экран, запущен ли
python3 <SKILL_DIR>/scripts/adb_helpers.py devices                           # устройства: эмулятор / реальное, API, модель
python3 <SKILL_DIR>/scripts/avd_manager.py images --available --api 34       # что можно скачать (sdkmanager --list, сеть, только чтение)
```
Владелец AVD: **скил** — имя начинается с `qa-` **и** в папке AVD есть метка `android-qa-audit.json` (её пишет `create`); **пользователь** — всё остальное (в том числе `qa-…` без метки). AVD пользователя не меняются, не удаляются и не запускаются без разрешения.

## Образ системы: ABI хоста
| Хост | ABI образа | Ускорение |
|------|-----------|-----------|
| macOS Apple Silicon (M1–M4) | `arm64-v8a` | Hypervisor.framework (HVF), встроено |
| macOS Intel | `x86_64` | HVF |
| Windows x64 | `x86_64` | WHPX («Платформа низкоуровневой оболочки Windows») или AEHD; HAXM — устарел |
| Linux x64 | `x86_64` | KVM (`/dev/kvm`, группа `kvm`) |

Образ чужого ABI работает без ускорения — в разы медленнее, для теста непригоден. Приложение только с x86-нативным кодом не установится на arm64-эмулятор (`INSTALL_FAILED_NO_MATCHING_ABIS`) — `apk_info.py` предупреждает (`compat.note`); тогда — реальное устройство или x86_64-хост. На x86_64-образах API 30+ ARM-код работает через трансляцию (медленнее).

Варианты образа (`--tag`): `google_apis` (по умолчанию: сервисы Google, без Play Store, есть `adb root`), `google_apis_playstore` (Play Store; покупки и вход в аккаунт запрещены правилами), `default` (AOSP, без сервисов Google). Если нужный уже установлен — берётся он, чтобы не качать.

## Установка образа (только после согласия)
```bash
python3 <SKILL_DIR>/scripts/avd_manager.py install-image --api 34            # план: пакет, оценка размера, свободное место
python3 <SKILL_DIR>/scripts/avd_manager.py install-image --api 34 --yes      # после «да» пользователя
```
Оценка: загрузка ≈ 1–2 ГБ, на диске ≈ 3–6 ГБ на образ; AVD — до размера раздела данных. Нужно ≥ 8 ГБ свободно. Лицензии SDK принимает пользователь: `sdkmanager --licenses` (интерактивно) или явное согласие → `--accept-licenses`. Имя пакета берётся из `sdkmanager --list` (`system-images;android-34;google_apis;arm64-v8a`; для новых версий бывает `android-36.1`, `android-37.0`).

## Создание AVD
```bash
python3 <SKILL_DIR>/scripts/avd_manager.py plan   --api 34 --profile small --ram 2048 --cores 2 --data 4G
python3 <SKILL_DIR>/scripts/avd_manager.py create --api 34 --profile small --ram 2048 --cores 2 --data 4G --yes --run-dir <RUN_DIR>
```
| Параметр | Ключ config.ini | По умолчанию |
|----------|-----------------|--------------|
| `--api N` | образ `system-images;android-N;<tag>;<abi>` | — |
| `--profile phone \| small \| large \| tablet \| fold \| <id>` | `hw.device.name` (pixel_7, small_phone, pixel_7_pro, pixel_tablet, pixel_fold; `avd_manager.py profiles`) | phone |
| `--ram МБ` | `hw.ramSize` | 2048 |
| `--cores N` | `hw.cpu.ncore` | 2 |
| `--data 6G` | `disk.dataPartition.size` | 6G |
| `--size WxH`, `--density N` | `hw.lcd.width/height`, `hw.lcd.density` | из профиля |
| `--orientation` | `hw.initialOrientation` | portrait |

Имя: `qa-api<API>-<профиль>-<ОЗУ>gb-<ядра>c[-play|-aosp][-<суффикс>]`, например `qa-api34-pixel7-2gb-4c`, `qa-api36-small-2gb-2c`. Такой AVD уже есть и он свой — переиспользуется (`"reused": true`); есть, но чужой — отказ (выбрать `--suffix`). Ограничения: 1 ГБ ОЗУ — только API ≤ 29; складной профиль — API ≥ 32.

## Запуск, загрузка, остановка
```bash
python3 <SKILL_DIR>/scripts/avd_manager.py start qa-api34-pixel7-2gb-4c --run-dir <RUN_DIR> [--headless] [--cold-boot] \
        [--netspeed lte --netdelay lte] [--locale ru-RU] [--timezone Europe/Moscow] [--wipe-data]
python3 <SKILL_DIR>/scripts/avd_manager.py wait-boot emulator-5554 --unlock --run-dir <RUN_DIR> [--disable-animations]
python3 <SKILL_DIR>/scripts/avd_manager.py snapshot save emulator-5554 qa-clean        # быстрый сброс к чистому состоянию
python3 <SKILL_DIR>/scripts/avd_manager.py snapshot load emulator-5554 qa-clean
python3 <SKILL_DIR>/scripts/avd_manager.py stop emulator-5554 --run-dir <RUN_DIR>
```
- Порт выбирается свободный (5554, 5556, … до 5682; занятые и зарезервированные прогоном пропускаются); serial — `emulator-<порт>`.
- Всегда `-no-snapshot-save` (состояние AVD между прогонами не копится) и `-no-metrics`; `--cold-boot` — без загрузки снимка; `--headless` — `-no-window -no-audio -gpu swiftshader_indirect` (на сервере, в фоне; скриншоты работают).
- Язык системы и часовой пояс надёжнее всего задавать при запуске (`--locale`, `--timezone`): adb меняет язык только у приложения (API 33+).
- `wait-boot` ждёт `sys.boot_completed=1`, конец анимации и готовность менеджера пакетов; если процесс эмулятора завершился — показывает хвост журнала `logs/emulator-<AVD>-<порт>.log` (нет ускорения, мало места, образ повреждён).
- `stop` останавливает только эмуляторы, запущенные этим прогоном (`stands.json`), или свои `qa-*` с `--any-qa`. Эмуляторы пользователя — никогда.

## Чужой AVD (только с разрешения)
`start <AVD> --allow-foreign` — принудительно `-read-only -no-snapshot-save`: изменения не сохраняются в AVD пользователя, можно запустить параллельно с его экземпляром. `--wipe-data` для чужого AVD запрещён.

## Реальное устройство
1. Пользователь включает «Параметры разработчика» и «Отладку по USB», подключает кабель, подтверждает ключ на телефоне (состояние `unauthorized` → `device`). Беспроводная отладка (Android 11+): `adb pair` / `adb connect` — выполняет пользователь.
2. Скил спрашивает согласие (intake, 9a): `read-only` / `app-only` / `full` → `stands.consent`.
3. Один поток на устройство. Скорость сети ограничить нельзя (только эмулятор); Wi-Fi и данные — с согласия `full`.
4. По окончании — вернуть изменённые настройки (тема, шрифт, поворот, анимации), удалить приложение — только если его установил прогон и пользователь согласен.

## Установка приложения
```bash
python3 <SKILL_DIR>/scripts/adb_helpers.py install <RUN_DIR>/apk/app-release.apk --serial emulator-5554 --run-dir <RUN_DIR>
python3 <SKILL_DIR>/scripts/adb_helpers.py install <RUN_DIR>/apk/base.apk <RUN_DIR>/apk/split_config.arm64_v8a.apk --serial …   # split
python3 <SKILL_DIR>/scripts/apk_info.py build-apks <RUN_DIR>/apk/app.aab --out <RUN_DIR>/apk/app.apks --universal                # AAB
```
`install` сверяет пакет APK с `app.package` (чужой APK — запрет), флаги: `--replace` (обновление поверх), `--downgrade`, `--grant-all` (выдать все разрешения — не для проверки диалогов разрешений), `--allow-test`. Ошибка — код `INSTALL_FAILED_*` и подсказка (`INSTALL.md` → «Частые проблемы»). Для `.apks` после `build-apks` — распаковать `universal.apk` (`--universal`) или поставить набор split.

## Уборка
В конце прогона — вопрос (SKILL.md, шаг 13), затем:
```bash
python3 <SKILL_DIR>/scripts/avd_manager.py cleanup --run-dir <RUN_DIR> --stop                    # план
python3 <SKILL_DIR>/scripts/avd_manager.py cleanup --run-dir <RUN_DIR> --stop --delete-avds --yes
```
`--delete-avds` удаляет только AVD, **созданные этим прогоном** (`stands.json → avds_created`), со своей меткой и не запущенные; `--delete-apk-copies` — копии в `<RUN_DIR>/apk/`; `--delete-recordings` — видео в `<RUN_DIR>/recordings/`. Без `--yes` — только план. Удаление одного своего AVD: `avd_manager.py delete <qa-…> --yes`.
