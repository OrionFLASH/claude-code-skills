# Проверка окружения при каждом запуске

## Команда
```bash
bash <SKILL_DIR>/scripts/check_env.sh                                  # macOS / Linux
powershell -ExecutionPolicy Bypass -File <SKILL_DIR>\scripts\check_env.ps1   # Windows
python3 <SKILL_DIR>/scripts/check_env.py --fast --json <RUN_DIR>/env.json     # после создания папки прогона
```
Только чтение: ничего не ставит и не меняет. `--fast` — без `emulator -accel-check`, `java -version`, `sdkmanager --version`, списка плагинов Claude Code и драйверов Appium; `--no-devices` — без `adb devices` (иначе он запускает сервер adb, если тот не запущен). До опроса папки прогона ещё нет — без `--json`.

## Что проверяется
| Компонент | Обязательно | Если нет |
|-----------|-------------|----------|
| Python 3.9+ | да | установить (только стандартная библиотека, pip не нужен) |
| Android SDK: platform-tools (adb) | да | `INSTALL.md` → «Android SDK»; найден, но не в PATH — **OK** (скил вызывает по полному пути), в примечании — строка для `~/.zshrc` / PowerShell для своего терминала |
| build-tools (aapt2, apksigner) | да (разбор APK) | `sdkmanager "build-tools;35.0.0"` |
| emulator + образ под ABI хоста + AVD или cmdline-tools | для эмуляторов | без них — только подключённые устройства; нет ни того, ни другого — FAIL «нет стенда» |
| cmdline-tools (sdkmanager, avdmanager) | для создания AVD и загрузки образов | Android Studio → SDK Manager или `brew install --cask android-commandlinetools` |
| Java (JDK 17+) | для sdkmanager, avdmanager, apksigner, bundletool | рекомендуется JDK 17 или 21 (Temurin LTS); ранние сборки (`-ea`) работают: обёртки cmdline-tools печатают «integer expression expected» — безвредно, при коде 0 скил скрывает строку, а `check_env` (без `--fast`) запускает `sdkmanager --version` и пишет в строке cmdline-tools «безвредно» |
| Аппаратное ускорение | для эмуляторов | HVF (macOS), WHPX/AEHD (Windows), KVM (Linux) — `INSTALL.md` |
| ОЗУ, ядра, диск | — | рекомендация числа потоков (`recommended_max_workers`); < 15 ГБ свободно — WARN |
| Устройства | — | `unauthorized` — подтвердить отладку на телефоне; `offline` — переподключить; `no permissions` — правила udev (Linux) |
| bundletool | для AAB | `brew install bundletool` или jar + `BUNDLETOOL_JAR` |
| scrcpy, Maestro, Appium, python uiautomator2 | нет | необязательные усилители (`plugins-map.md`) |
| виртуальное аудиоустройство (BlackHole, Loopback, snd-aloop, VB-Cable) | нет | только для подачи звука путём 2 (`audio-input.md`); скил **только проверяет** и подсказывает — ставит и выбирает устройство пользователь; пути gRPC и «файл» работают без него |
| ffmpeg и ffprobe | нет, **рекомендуется** для роликов находок | без него ролик сохраняется как есть (без сжатия под бюджет), нет GIF, постера и ленты кадров — вместо ленты скриншоты по шагам (`clips.md`); строка показывает libx264 и `drawtext`. Установка — системный пакет, **только с согласия**: `brew install ffmpeg` / `sudo apt install ffmpeg` / `winget install Gyan.FFmpeg`; свой путь — `QA_FFMPEG`, `QA_FFPROBE` |
| `screenrecord` на стендах | нет | строка «screenrecord на стендах (ролики)»: API ≥ 19 и `/system/bin/screenrecord` на каждом онлайн-стенде (только чтение); нет — ролики на этом стенде недоступны (скриншоты по шагам или `clip` из скриншотов) |
| Node.js 18+ и Playwright в `scripts/node` | нет | аннотации скриншотов (`screenshots.md`): `cd <SKILL_DIR>/scripts/node && npm install && npx playwright install chromium` — локально, с согласия; без них оригинал и spec сохраняются |
| gh + вход | только для GitHub issues | `gh auth login` |
| `ANDROID_QA_OUTPUT_DIR` | нет | без неё — `<cwd>/qa-runs/` (`intake.md` → «Папка прогона») |
| Скилы-усилители | нет | работа по собственным чек-листам |

## Поведение
- FAIL в обязательном → показать таблицу, предложить команду из колонки «Как исправить» и `INSTALL.md`; **глобальные установки — только после подтверждения** пользователя, одним списком.
- WARN → продолжать; ограничение записать в отчёт («API 26 не проверялся: нет образа», «скорость сети не ограничивалась: реальное устройство»).
- `env.json` — источник для `matrix.py` (образы, хост, ресурсы, устройства) и для `plugins-map.md` (`enhancers`, `banned`).
- Реальные устройства в списке — ещё не разрешение их использовать (`safety-rules.md` §3, п. 6).

## Оболочка
В командах не использовать разделители из знаков равенства (`echo =====`): в zsh они ломают команду. Пути с пробелами — в кавычках. На Windows вместо `python3` — `python` или `py -3`; `.sh`-обёртки — в Git Bash или WSL.
