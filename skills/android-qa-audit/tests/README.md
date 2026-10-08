# Самопроверка android-qa-audit

| Файл | Что проверяет | Как запускать |
|------|---------------|---------------|
| `unit.sh` | все скрипты без устройства, эмулятора и сети: синтаксис Python 3.9; `guard.py` (selftest и CLI); шаблоны и схема; `sdkutil` (поиск SDK, `adb devices`, владельцы AVD); `check_env` на фейковом SDK; `apk_info` (aapt2, aapt v1, `.apks`, копия с SHA256); `avd_manager` (план, создание, переиспользование, запуск на свободном порту, загрузка, остановка, отказ для чужих AVD, лицензии, уборка); `adb_helpers` (дерево элементов и кандидаты, запреты нажатий и adb-команд, реальное устройство и согласие, секреты в журнале, метрики, падения, logcat, monkey, скриншот, уведомления, сеть); `matrix`; `intake`; `validate_findings`, `fingerprint`, `render_draft`, `build_report`; `gitignore_helper`; маскирование; универсальность; SKILL.md | `bash tests/unit.sh`; другой Python — `PY=/usr/bin/python3 bash tests/unit.sh` (минимум 3.9) |
| `helpers/fake_adb.py` | фейковый adb: устройства, getprop, uiautomator, dumpsys, am, pm, logcat, emu, install; журнал вызовов `FAKE_ADB_LOG` | вызывается из `unit.sh` через обёртку в фейковом SDK |
| `helpers/fake_tools.py` | фейковые aapt2, apksigner, emulator (пишет состояние в `FAKE_ADB_STATE`), avdmanager, sdkmanager | то же |
| `fixtures/` | обезличенные данные: `com.example.app`, вывод `aapt2 dump badging` и `xmltree`, `apksigner`, `adb devices`, `getprop`, `window_dump.xml`, `dumpsys` (meminfo, gfxinfo, package, notification, diskstats), `am start -W`, logcat с падением и ANR, monkey, `sdkmanager --list`, findings.json, issues.json, run-config.yaml | — |

`unit.sh` изолирует окружение: временные `HOME`, `ANDROID_HOME` (фейковый SDK) и `ANDROID_AVD_HOME`; настоящие `~/.android`, AVD пользователя и подключённые устройства не затрагиваются.

## Живая проверка (вручную, на машине с Android SDK)
Не входит в `unit.sh`, выполняется по просьбе пользователя:
1. Только чтение: `check_env.sh`, `apk_info.py analyze <свой APK> --summary` (без `--copy-to`), `avd_manager.py list`.
2. На своём эмуляторе: `avd_manager.py create --api <установленный> --yes --run-dir <tmp>` → `start --headless` → `wait-boot` → `adb_helpers.py install` → `launch --cold` → `dump-ui` → `tap` безопасной кнопки → `crashes` → `cleanup --stop --delete-avds --yes`.
3. Попытка нажать кнопку покупки — код 3 и запись в `logs/blocked.jsonl`.
