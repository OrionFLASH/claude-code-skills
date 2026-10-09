# Установка и обновление android-qa-audit

Одна инструкция для macOS и Windows (и кратко Linux): окружение (Java, Android SDK, эмулятор, образы, ускорение), необязательные программы, сам скил, проверка, обновление и откат. Скил — Python 3.9+ без сторонних пакетов (gRPC эмулятора — тоже на стандартной библиотеке: `grpcio` и `protoc` не нужны). Node.js и Playwright нужны только для **аннотаций скриншотов** — локально в `<SKILL_DIR>/scripts/node` (ниже «Аннотации скриншотов»); без них всё остальное работает.

Репозиторий: https://github.com/OrionFLASH/claude-code-skills (папка `skills/android-qa-audit`), маркетплейс `claude-code-skills`.

`<SKILL_DIR>` — папка установленного скила (где лежит `SKILL.md`):

| Способ | macOS / Linux | Windows |
|--------|---------------|---------|
| Маркетплейс | `~/.claude/plugins/cache/claude-code-skills/android-qa-audit/<версия>/` (точный путь — `installPath` в `claude plugin list --json`) | `%USERPROFILE%\.claude\plugins\cache\claude-code-skills\android-qa-audit\<версия>\` |
| Клон + ссылка, копия | `~/.claude/skills/android-qa-audit/` | `%USERPROFILE%\.claude\skills\android-qa-audit\` |
| Только для проекта | `<проект>/.claude/skills/android-qa-audit/` | `<проект>\.claude\skills\android-qa-audit\` |

## Быстрый способ: промпт для Claude Code

Откройте Claude Code в любой папке и вставьте промпт целиком. Claude определит ОС, проверит, что уже есть, задаст вопросы с вариантами, покажет план, сделает резервные копии и всё поставит, затем запустит `check_env` и покажет итог.

### Промпт: установка

````text
Установи на этой машине скилл android-qa-audit из репозитория
https://github.com/OrionFLASH/claude-code-skills (папка skills/android-qa-audit) и подготовь окружение для
тестирования Android-приложений. Сначала прочитай skills/android-qa-audit/INSTALL.md из этого репозитория
(разделы «Что понадобится», «Окружение», «Установка скила», «Проверка»), затем действуй по шагам. Отвечай по-русски.

ПРАВИЛА
- Порядок: разведка (только чтение) -> вопросы -> план -> мое «да» -> действия -> проверка -> итог.
- Вопросы - через AskUserQuestion (нет инструмента - нумерованным списком), по 1-3 за раз, рекомендуемый
  вариант первым с пометкой (Recommended).
- Перед действиями покажи план: что скачаешь (с размерами: образы систем по 1-2 ГБ), какие папки создашь,
  какие файлы изменишь, какие глобальные установки сделаешь (brew/winget, sdkmanager, npm -g).
  Глобальное и загрузки - только после моего «да».
- Перед правкой файла настроек (~/.zshrc, ~/.bashrc, профиль PowerShell, ~/.claude/settings.json) сделай
  резервную копию рядом (<файл>.bak-ГГГГММДД). Дописывай только свои строки, ничего не затирай; JSON проверь
  парсером. Переменные Windows - через [Environment]::SetEnvironmentVariable(..., 'User'), покажи значения до и после.
- Лицензии Android SDK (sdkmanager --licenses) - покажи, что принимаешь, и спроси меня; не принимай молча.
- Не трогай существующие AVD и не удаляй ничего из Android SDK. Не печатай секреты (токены gh, пароли).
- Не ставь скилл двумя способами сразу (плагин и папка в ~/.claude/skills дают два одинаковых скилла).
  Существующую папку скилла не удаляй - переименуй в android-qa-audit.bak-ГГГГММДД.
- Если права Claude Code не дают что-то сделать, не обходи запрет: покажи команду, я выполню сам.

ШАГ 0. РАЗВЕДКА (только чтение)
1) ОС, архитектура процессора (Apple Silicon / Intel / x64 / ARM), оболочка; на Windows - версия PowerShell,
   есть ли Git Bash или WSL, включена ли виртуализация (systeminfo: «Hyper-V Requirements» / «Платформа низкоуровневой оболочки»).
2) Версии: claude, git, рабочая команда Python 3 (python3 / python / py -3, нужна 3.9+), java -version и JAVA_HOME,
   gh (только факт входа), brew (macOS) или winget (Windows).
3) Android SDK: переменные ANDROID_HOME и ANDROID_SDK_ROOT; типовые папки (macOS ~/Library/Android/sdk,
   /opt/homebrew/share/android-commandlinetools; Windows %LOCALAPPDATA%\Android\Sdk; Linux ~/Android/Sdk);
   в найденном SDK: platform-tools (adb version), emulator (emulator -version), cmdline-tools/*/bin
   (sdkmanager, avdmanager), build-tools/*, system-images/* (API, тег, ABI), есть ли adb в PATH.
4) Существующие AVD (emulator -list-avds или файлы ~/.android/avd/*.ini) - только перечислить.
5) Уже установлен ли android-qa-audit: ~/.claude/skills/android-qa-audit (папка/симлинк/junction - куда ведет),
   .claude/skills текущего проекта, плагин (claude plugin list). Задана ли ANDROID_QA_OUTPUT_DIR.
Покажи сводку таблицей и какой ABI образов нужен (Apple Silicon - arm64-v8a, остальные - x86_64).

ШАГ 1. ВОПРОСЫ
1) Android SDK, если его нет: «Android Studio (Recommended: SDK, эмулятор и менеджер в комплекте)» /
   «Только command-line tools (brew --cask android-commandlinetools / zip)» / «Укажу путь к своему SDK».
2) Java, если нет JDK 17+: «Temurin 21 (Recommended)» / «Temurin 17» / «Уже есть - укажу JAVA_HOME».
3) Образы систем (мультивыбор, по 1-2 ГБ каждый): «API 35 (Recommended)» / «API 34» / «API 30» / «API 26»
   (под нужный ABI); или «Не сейчас - скил предложит при прогоне».
4) Необязательное (мультивыбор): «bundletool (AAB)» / «scrcpy (показ экрана)» / «Maestro» / «Appium + uiautomator2»;
   «Аннотации скриншотов: Node.js 18+ и локально npm install + npx playwright install chromium в <SKILL_DIR>/scripts/node».
   Виртуальное аудиоустройство (BlackHole и т. п.) не ставь - только скажи, что оно нужно лишь для пути loopback.
5) Способ установки скила: «Маркетплейс плагинов (Recommended)» / «Клон репозитория + tools/install.sh
   (macOS/Linux) или tools\install.ps1 (Windows)» / «Копия папки без git»; для кого: «Все проекты (~/.claude)» /
   «Только текущий проект (.claude)»; для клона - куда: «~/dev/claude-code-skills (Recommended)» / «Указать путь».
6) Переменные: «Добавить ANDROID_HOME и PATH в профиль оболочки (Recommended)» / «Не трогать профиль»;
   папка результатов: «По умолчанию <папка запуска>/qa-runs (Recommended)» / «Одна папка: ANDROID_QA_OUTPUT_DIR (укажу путь)».

ШАГ 2. ПЛАН. Команды, загрузки с размерами, папки, файлы (с путями резервных копий). Жди «да».

ШАГ 3. УСТАНОВКА (по разделам «Окружение» и «Установка скила» INSTALL.md)
- Java, SDK (Android Studio: после установки открыть SDK Manager и поставить «Android SDK Command-line Tools
  (latest)», «Android Emulator», «Android SDK Platform-Tools», «Android SDK Build-Tools»; или command-line tools).
- sdkmanager --licenses (после моего «да»), затем sdkmanager "platform-tools" "emulator" "build-tools;35.0.0"
  и выбранные "system-images;android-<N>;google_apis;<ABI>".
- Ускорение: macOS - ничего; Windows - компоненты «Платформа низкоуровневой оболочки Windows» (WHPX) и
  «Платформа виртуальной машины» (нужны права администратора и перезагрузка - скажи и остановись);
  Linux - KVM и группа kvm.
- Профиль оболочки: ANDROID_HOME, ANDROID_SDK_ROOT, PATH (platform-tools, emulator, cmdline-tools/latest/bin).
- Скил: маркетплейс (claude plugin marketplace add OrionFLASH/claude-code-skills;
  claude plugin install android-qa-audit@claude-code-skills) или клон + tools/install.sh android-qa-audit
  (Windows: powershell -ExecutionPolicy Bypass -File tools\install.ps1 android-qa-audit) или копия.
- ANDROID_QA_OUTPUT_DIR (если выбрано): env в ~/.claude/settings.json (резервная копия; путь не в репозитории скилов).

ШАГ 4. ПРОВЕРКА
- <SKILL_DIR>/scripts/check_env.sh (Windows: powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1):
  таблица и строка «Итог». FAIL в обязательном - предложи исправление (глобальное - после «да»).
- emulator -accel-check (ускорение «installed and usable»).
- bash <SKILL_DIR>/tests/unit.sh (если есть bash) - последняя строка «unit: PASS N, FAIL 0».
Эмуляторы не запускай и AVD не создавай - это делает скил во время прогона.

ШАГ 5. ИТОГ
Таблица: что установлено и где (версии, пути), что скачано (образы, размер), что изменено (файлы и резервные
копии), результат check_env и тестов, что сделать вручную (перезапустить терминал и начать новую сессию
Claude Code - в этой сессии скилл не виден, вызов даст «Unknown skill»; продолжить здесь можно, прочитав
<SKILL_DIR>/SKILL.md и выполняя шаги по нему; перезагрузка Windows после включения WHPX; gh auth login - если нужны issues),
как откатить (вернуть .bak, удалить ссылку/папку или claude plugin uninstall android-qa-audit@claude-code-skills;
пакеты SDK - sdkmanager --uninstall <пакет>).
````

### Промпт: обновление

````text
Обнови на этой машине скилл android-qa-audit до последней версии из репозитория
https://github.com/OrionFLASH/claude-code-skills (папка skills/android-qa-audit) и проверь окружение.
Ориентируйся на skills/android-qa-audit/INSTALL.md (раздел «Обновление»). Отвечай по-русски.

ПРАВИЛА - те же, что при установке: разведка -> вопросы -> план -> мое «да» -> действия; резервные копии
(старую папку скилла - в android-qa-audit.bak-ГГГГММДД, файлы настроек - в <файл>.bak-ГГГГММДД); секреты не печатать;
глобальное и загрузки - только после «да»; папки результатов (qa-runs/, в том числе .app-context/) и AVD не трогать.

ШАГ 0. РАЗВЕДКА (только чтение)
1) ОС; где и как стоит скилл: плагин (claude plugin list --json -> installPath, version), симлинк или junction на клон
   (куда ведет), копия; нет ли дубля (плагин + папка).
2) Текущая версия - <SKILL_DIR>/.claude-plugin/plugin.json. Последняя: в клоне - git fetch, затем plugin.json и
   CHANGELOG.md в origin/main; для плагина - claude plugin marketplace update claude-code-skills и claude plugin list;
   иначе - CHANGELOG.md скилла на GitHub.
3) Для клона: git status (есть ли локальные правки) и текущая ветка.
4) check_env --fast: не появились ли новые требования (раздел «Что понадобится» в новой версии INSTALL.md).
Покажи сводку: текущая версия -> последняя, заголовки изменений из CHANGELOG.md между ними.

ШАГ 1. ВОПРОСЫ: обновить X -> Y? Есть дубль - что оставить? Есть локальные правки в клоне - «Отложить (git stash)
и обновить» / «Не обновлять». Новые требования окружения - ставить ли (с размерами загрузок).

ШАГ 2. ОБНОВЛЕНИЕ
- Плагин: claude plugin marketplace update claude-code-skills; claude plugin update android-qa-audit@claude-code-skills.
- Клон: git pull --ff-only; повторно tools/install.sh android-qa-audit (Windows -
  powershell -ExecutionPolicy Bypass -File tools\install.ps1 android-qa-audit), он проверит ссылку.
- Копия: переименуй старую папку в android-qa-audit.bak-ГГГГММДД, скопируй новую (без __pycache__).

ШАГ 3. ПРОВЕРКА: версия в plugin.json совпадает с последней; check_env; bash tests/unit.sh, если есть bash.
Если раньше ставились аннотации скриншотов - в папке новой версии снова cd <SKILL_DIR>/scripts/node && npm install
(после «да»), затем python3 <SKILL_DIR>/scripts/annotate_android.py check.

ШАГ 4. ИТОГ: таблица (версия до и после, способ, дубли, check_env, тесты), что сделать вручную (перезапустить
Claude Code), как откатить (в клоне - git checkout android-qa-audit/v<старая версия>; копия - вернуть .bak;
плагин - переустановить нужную версию из клона или копией).
````

Нет доступа к GitHub из Claude Code — скачайте репозиторий ZIP-ом (Code → Download ZIP), распакуйте и добавьте в промпт строку «Репозиторий уже лежит в папке <путь>».

## Что понадобится

| Компонент | Обязательно | macOS | Windows | Проверка |
|-----------|-------------|-------|---------|----------|
| Claude Code | да | https://claude.com/claude-code | то же | `claude --version` |
| Python 3.9+ (только стандартная библиотека, `pip` не нужен) | да | обычно есть: `python3` | https://python.org или `winget install Python.Python.3.12`; команда `python` или `py -3` | `python3 --version` |
| git | для клона и `.gitignore` папки результатов | `xcode-select --install` или `brew install git` | https://git-scm.com (с Git Bash) | `git --version` |
| JDK 17+ (рекомендуется 17 или 21 LTS) | для sdkmanager, avdmanager, apksigner, bundletool | `brew install --cask temurin@21` | `winget install EclipseAdoptium.Temurin.21.JDK` | `java -version` |
| Android SDK: platform-tools (adb) | да | Android Studio или `brew install --cask android-commandlinetools` + sdkmanager; только adb — `brew install --cask android-platform-tools` | Android Studio (`winget install Google.AndroidStudio`) или zip command-line tools; только adb — `winget install Google.PlatformTools` | `adb version` |
| build-tools (aapt2, apksigner) | да (разбор APK) | `sdkmanager "build-tools;35.0.0"` | то же | `check_env` |
| emulator + образ системы + cmdline-tools | для эмуляторов | `sdkmanager "emulator" "system-images;android-35;google_apis;arm64-v8a"` | `sdkmanager "emulator" "system-images;android-35;google_apis;x86_64"` | `emulator -version` |
| Аппаратное ускорение | для эмуляторов | встроено (HVF) | WHPX или AEHD (ниже) | `emulator -accel-check` |
| bundletool | для AAB | `brew install bundletool` | jar с https://github.com/google/bundletool/releases + `BUNDLETOOL_JAR` | `bundletool version` |
| gh + вход | только для GitHub issues | `brew install gh` | `winget install GitHub.cli` | `gh auth status` |
| scrcpy | нет — показ экрана устройства | `brew install scrcpy` | `winget install Genymobile.scrcpy` | `scrcpy --version` |
| Maestro | нет — повторяемые сценарии | `curl -fsSL "https://get.maestro.mobile.dev" \| bash` | через WSL (документация Maestro) | `maestro --version` |
| Appium + uiautomator2 | нет — сложные сценарии | Node 18+, `npm i -g appium && appium driver install uiautomator2` | то же | `appium --version` |
| Node.js 18+ и Playwright (Chromium) в `scripts/node` | нет — аннотированные скриншоты и PNG контактного листа | `brew install node`; затем локально: `cd <SKILL_DIR>/scripts/node && npm install && npx playwright install chromium` | `winget install OpenJS.NodeJS.LTS`; то же в PowerShell | `python3 <SKILL_DIR>/scripts/annotate_android.py check` |
| Виртуальное аудиоустройство | нет — только подача звука путём loopback (`references/audio-input.md`) | BlackHole: `brew install --cask blackhole-2ch` (или Loopback); выбрать входом и выходом по умолчанию — вручную | VB-Audio Virtual Cable (сайт VB-Audio); путь loopback на Windows — только вручную (`audio-input.md` → «Windows»), автоматически — gRPC или файл | строка «виртуальное аудиоустройство» в `check_env` |
| ADBKeyBoard (APK) | нет — ввод кириллицы клавиатурой (`text --adbkeyboard`) | APK скачивает пользователь (github.com/senzhk/ADBKeyBoard); поставить на свой эмулятор — `adb_helpers.py ime install-adbkeyboard --apk <файл> --confirmed` после согласия | то же | `adb_helpers.py ime status` |

Ресурсы: эмулятор с 2 ГБ ОЗУ занимает ≈ 3 ГБ памяти хоста; 2 потока — от 16 ГБ ОЗУ, 4 — от 32 ГБ и 8 ядер. Диск: образ ≈ 3–6 ГБ, AVD ≈ 2–8 ГБ; держите свободными 15+ ГБ.

Плагины-усилители (ui-ux-pro-max, laws-of-ux, ux-heuristics, ux-audit, qa-skills) необязательны — `references/plugins-map.md`.

## Окружение

### 1. Java (JDK 17+)
- macOS: `brew install --cask temurin@21` (или `temurin@17`); `JAVA_HOME` — `export JAVA_HOME="$(/usr/libexec/java_home -v 21)"` в `~/.zshrc`.
- Windows: `winget install EclipseAdoptium.Temurin.21.JDK` (установщик сам задаёт `JAVA_HOME` и PATH, если отметить опции); проверка в новом окне: `java -version`.
- Linux: `sudo apt install openjdk-21-jdk` (или `openjdk-17-jdk`).

Совместимость: cmdline-tools требуют JDK 17+. **Рекомендуется JDK 17 или 21 (Temurin LTS).** Ранние сборки (например, `25-ea`) работают, но обёртки `sdkmanager`/`avdmanager` печатают «… integer expression expected» (скрипт не понимает суффикс версии), `apksigner` — предупреждения JVM о native access. Это безвредно: если команда завершилась с кодом 0, скил скрывает эти строки и пишет короткую пометку, а `check_env` (без `--fast`) запускает `sdkmanager --version` и отмечает в строке cmdline-tools «шум … безвредно»; при ошибке вывод показывается целиком.

### 2. Android SDK
**Вариант А — Android Studio (проще всего).** Установить (macOS: `brew install --cask android-studio`; Windows: `winget install Google.AndroidStudio`; или https://developer.android.com/studio), запустить мастер первого запуска. Затем **Settings → Languages & Frameworks → Android SDK → SDK Tools**: отметить «Android SDK Command-line Tools (latest)», «Android Emulator», «Android SDK Platform-Tools», «Android SDK Build-Tools». SDK окажется в `~/Library/Android/sdk` (macOS), `%LOCALAPPDATA%\Android\Sdk` (Windows), `~/Android/Sdk` (Linux) — скил найдёт его сам.

**Вариант Б — только command-line tools.**
- macOS (Homebrew): `brew install --cask android-commandlinetools` → SDK в `/opt/homebrew/share/android-commandlinetools` (Apple Silicon) или `/usr/local/share/android-commandlinetools` (Intel), `sdkmanager` в PATH.
- Вручную (любая ОС): скачать «Command line tools only» с https://developer.android.com/studio#command-line-tools-only и распаковать так, чтобы получилось `<SDK>/cmdline-tools/latest/bin/sdkmanager` (папку `cmdline-tools` из архива переименовать в `latest` внутри `<SDK>/cmdline-tools/`). Иначе sdkmanager пишет «Could not determine SDK root».

Пакеты (лицензии — один раз, ответить `y` на каждую после прочтения):
```bash
sdkmanager --licenses
sdkmanager "platform-tools" "emulator" "build-tools;35.0.0" "platforms;android-35"
sdkmanager "system-images;android-35;google_apis;arm64-v8a"     # Apple Silicon
sdkmanager "system-images;android-35;google_apis;x86_64"        # Intel Mac, Windows, Linux
sdkmanager --list | grep system-images                          # какие ещё есть (Windows: | findstr system-images)
```
Образы других версий скил предложит сам по матрице прогона (`avd_manager.py install-image`, с оценкой размера и только после «да»).

### 3. Переменные окружения
Скилу PATH не нужен (он находит SDK по `ANDROID_HOME`, `ANDROID_SDK_ROOT` и типовым папкам), но adb, emulator и sdkmanager удобнее и в терминале.

macOS (zsh, `~/.zshrc`; для Homebrew-варианта путь — `/opt/homebrew/share/android-commandlinetools`):
```bash
export ANDROID_HOME="$HOME/Library/Android/sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
```
Linux (bash, `~/.bashrc`): то же с `ANDROID_HOME="$HOME/Android/Sdk"`.

Windows (PowerShell, для текущего пользователя; затем открыть новое окно):
```powershell
$sdk = "$env:LOCALAPPDATA\Android\Sdk"
[Environment]::SetEnvironmentVariable('ANDROID_HOME', $sdk, 'User')
[Environment]::SetEnvironmentVariable('ANDROID_SDK_ROOT', $sdk, 'User')
$p = [Environment]::GetEnvironmentVariable('Path', 'User')
[Environment]::SetEnvironmentVariable('Path', "$p;$sdk\platform-tools;$sdk\emulator;$sdk\cmdline-tools\latest\bin", 'User')
```
Claude Code, запущенный не из терминала, может не видеть переменные профиля — добавьте их в `env` файла `~/.claude/settings.json` (раздел «Папка результатов» ниже).

### 4. Аппаратное ускорение
| Хост | Что сделать | Проверка |
|------|-------------|----------|
| macOS Apple Silicon | ничего (Hypervisor.framework); только образы `arm64-v8a` | `emulator -accel-check` → «HVF … is installed and usable» |
| macOS Intel | ничего; образы `x86_64` | то же |
| Windows | включить виртуализацию в BIOS/UEFI; компоненты «Платформа низкоуровневой оболочки Windows» и «Платформа виртуальной машины» (`optionalfeatures.exe`, или PowerShell от администратора: `Enable-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform -All` и `… -FeatureName VirtualMachinePlatform -All`), перезагрузка. Без Hyper-V — драйвер AEHD: `sdkmanager "extras;google;Android_Emulator_Hypervisor_Driver"` и его установщик. HAXM устарел | `emulator -accel-check` → «WHPX … usable» или «AEHD … usable» |
| Linux | `sudo apt install qemu-kvm`, `sudo usermod -aG kvm $USER`, перелогиниться | `emulator -accel-check` → «KVM … usable»; `ls -l /dev/kvm` |

### 5. Реальное устройство (если нужно)
На телефоне: «О телефоне» → 7 раз нажать «Номер сборки» → «Для разработчиков» → «Отладка по USB». Подключить кабель, разблокировать, нажать «Разрешить» в диалоге отладки (`adb devices` → `device`, а не `unauthorized`). Xiaomi/Redmi: включить ещё «Установка через USB». Без кабеля (Android 11+): «Отладка по Wi-Fi» → `adb pair <ip:порт>` → `adb connect <ip:порт>`. Linux: правила udev для Android (пакет `android-sdk-platform-tools-common`). Скил использует устройство только после вашего ответа, что на нём можно делать.

## Установка скила

Выберите один способ. Не ставьте скил одновременно плагином и папкой в `~/.claude/skills` — будет два одинаковых скила.

### Способ 1. Маркетплейс (обычное использование)
```text
/plugin marketplace add OrionFLASH/claude-code-skills
/plugin install android-qa-audit@claude-code-skills
```
Или в терминале: `claude plugin marketplace add OrionFLASH/claude-code-skills`, затем `claude plugin install android-qa-audit@claude-code-skills` (только для текущего проекта — `--scope project`).

### Способ 2. Клон репозитория + ссылка (разработка)
Правки в клоне подхватываются сразу. `tools/install.sh` создаёт симлинк, `tools/install.ps1` на Windows — junction (права администратора не нужны). Целевую папку можно переопределить `CLAUDE_SKILLS_DIR`.
```bash
git clone https://github.com/OrionFLASH/claude-code-skills.git ~/dev/claude-code-skills
cd ~/dev/claude-code-skills
tools/install.sh android-qa-audit                 # ~/.claude/skills/android-qa-audit -> клон
```
```powershell
git clone https://github.com/OrionFLASH/claude-code-skills.git $HOME\dev\claude-code-skills
cd $HOME\dev\claude-code-skills
powershell -ExecutionPolicy Bypass -File tools\install.ps1 android-qa-audit
```
Убрать ссылку: `tools/install.sh --uninstall android-qa-audit` (Windows: `… tools\install.ps1 -Uninstall android-qa-audit`).

### Способ 3. Копия (без git)
Скачайте ZIP (https://github.com/OrionFLASH/claude-code-skills → Code → Download ZIP), скопируйте `skills/android-qa-audit` (без `__pycache__`):
```bash
mkdir -p ~/.claude/skills && cp -R <распаковано>/skills/android-qa-audit ~/.claude/skills/
```
```powershell
New-Item -ItemType Directory -Force $HOME\.claude\skills | Out-Null
Copy-Item -Recurse <распаковано>\skills\android-qa-audit $HOME\.claude\skills\android-qa-audit
```
После установки любым способом **начните новую сессию Claude Code**: скил появляется в списке только в новой сессии. В той сессии, где его поставили, `/android-qa-audit` и вызов скила отвечают «Unknown skill» — это не ошибка установки. Продолжить в той же сессии можно: попросите Claude прочитать `<SKILL_DIR>/SKILL.md` и идти по «Порядку работы» вручную (скрипты — по полным путям `<SKILL_DIR>/scripts/…`); в следующий раз — новая сессия.

## Проверка
```bash
bash <SKILL_DIR>/scripts/check_env.sh             # таблица и «Итог: можно работать» (только чтение)
emulator -accel-check                             # ускорение
bash <SKILL_DIR>/tests/unit.sh                    # тесты скила без устройства и сети (последняя строка: unit: PASS N, FAIL 0)
```
```powershell
powershell -ExecutionPolicy Bypass -File <SKILL_DIR>\scripts\check_env.ps1
python <SKILL_DIR>\scripts\check_env.py --fast    # то же без обёртки (или py -3)
# тесты — в Git Bash: bash <SKILL_DIR>/tests/unit.sh
```
Затем в **новой** сессии Claude Code: `/android-qa-audit` есть в списке команд, а просьба «протестируй ~/Downloads/app.apk» приводит к вопросу «Похоже, вы хотите протестировать Android-приложение … Запустить?».

## Принудительный запуск (хук плагина, с 1.4.0)

Плагин приносит хук `UserPromptSubmit` (`hooks/hooks.json` → `scripts/shared/qa_force.py`, без сети, только Python): запрос с меткой `!qa …`, `qa: …`, `!android-qa …` или фразой «запусти скилл android-qa-audit» получает строку «ЯВНЫЙ ВЫЗОВ (qa-force)», и скил стартует без вопроса о намерении (опции метки: `autopilot`, `smoke|standard|deep`). Хук не блокирует запрос и ничего не печатает при ошибке. Проверка: `echo '{"prompt":"!qa deep https://example.com"}' | python3 <SKILL_DIR>/scripts/shared/qa_force.py --hook --skill android-qa-audit` печатает JSON с `additionalContext`. При установке без плагина (симлинк или копия) хука нет: метки распознаёт только сама модель по `SKILL.md`; слэш `/android-qa-audit` работает всегда. Хук подхватывается после перезапуска Claude Code или `/reload-plugins`.

## Обновление
Текущая версия — `"version"` в `<SKILL_DIR>/.claude-plugin/plugin.json` (плагин — также `claude plugin list`); что изменилось — `CHANGELOG.md` скила; теги — `android-qa-audit/vX.Y.Z`.

| Установка | Как обновить |
|-----------|--------------|
| Маркетплейс | шаги ниже: «Обновление через маркетплейс» |
| Клон + ссылка | `git pull --ff-only` в клоне; `tools/install.sh android-qa-audit` (Windows: `install.ps1`) ещё раз — проверит ссылку |
| Копия | скачать заново, старую папку переименовать в `android-qa-audit.bak-ГГГГММДД`, скопировать новую |

### Обновление через маркетплейс (по шагам)
1. `/plugin marketplace update claude-code-skills` (или в терминале `claude plugin marketplace update claude-code-skills`).
2. `/plugin update android-qa-audit@claude-code-skills` (или `claude plugin update android-qa-audit@claude-code-skills`).
3. Новая папка версии — `installPath` из `claude plugin list --json` (`~/.claude/plugins/cache/claude-code-skills/android-qa-audit/<новая версия>/`): в заданиях исполнителей `<SKILL_DIR>` — этот путь, а не прежний (папка старой версии может исчезнуть).
4. Перезапустить Claude Code (новая версия видна только в новой сессии).
5. Проверить: `bash <installPath>/scripts/check_env.sh --fast` и `python3 <installPath>/scripts/guard.py selftest`; при желании `bash <installPath>/tests/unit.sh`.
6. Аннотации скриншотов (если нужны): в папке новой версии ещё раз `cd <installPath>/scripts/node && npm install` (папка `node_modules` в новую версию не переносится), проверка — `python3 <installPath>/scripts/annotate_android.py check`.
Android SDK, образы и AVD обновление не затрагивает.

## Аннотации скриншотов (необязательно)
Рамки, стрелки и подписи на скриншотах находок (`references/screenshots.md`) рисует `scripts/node/annotate.js` в Chromium через Playwright, контактный лист (`annotate_android.py sheet`) — `scripts/node/sheet.js` там же. Ставится **локально в папку скила** (ничего глобального, кроме самого Node.js), только с согласия пользователя:
```bash
cd <SKILL_DIR>/scripts/node && npm install && npx playwright install chromium
python3 <SKILL_DIR>/scripts/annotate_android.py check        # {"ok": true, …}
```
Если Playwright уже стоит для site-qa-audit, можно не ставить второй раз: `ANDROID_QA_NODE_MODULES=<папка site-qa-audit>/scripts/node/node_modules` в `env` настроек Claude Code. Без Node.js: скриншоты и разметка (`*.spec.json`) сохраняются, рисование — «не поддерживается», контактный лист — только HTML, остальное работает. График PSS в отчёте Node не нужен (SVG на стандартной библиотеке).

## Звук в микрофон эмулятора (по необходимости)
Ставить ничего не нужно: `avd_manager.py start <AVD> --mic-inject` запускает эмулятор с gRPC и токеном, `adb_helpers.py mic-inject --wav <файл>` подаёт звук (`references/audio-input.md`). Виртуальное аудиоустройство (BlackHole и др.) — только для пути loopback, ставит и выбирает пользователь сам; скил его не трогает. Короткая проверка: `adb_helpers.py mic-status --serial <serial> --run-dir <RUN_DIR>`.

## Обёртка `qa` для zsh и bash
`<SKILL_DIR>/scripts/qa <serial> <команда adb_helpers.py> …` (Windows — `qa.ps1`) добавляет `--serial` и `--run-dir "$QA_RUN_DIR"`. Удобно для своего терминала: `export QA_RUN_DIR=<RUN_DIR>` и `alias qa=<SKILL_DIR>/scripts/qa` в `~/.zshrc`.

После обновления — `check_env` (новые требования) и перезапуск Claude Code. Результаты прогонов, память о приложениях (`qa-runs/.app-context/`) и AVD лежат вне папки скила — обновление их не затрагивает.

**Откат:** клон — `git checkout android-qa-audit/v<версия>` (вернуться — `git checkout main`); копия — вернуть папку `.bak`; плагин — `claude plugin uninstall android-qa-audit@claude-code-skills` и поставить нужную версию из клона способом 2.

## Папка результатов: `ANDROID_QA_OUTPUT_DIR`
По умолчанию результаты пишутся в `<папка запуска Claude Code>/qa-runs/<дата>-<пакет>/` (копии APK — там же, в `apk/`). Если папка внутри git-репозитория, скил **сразу, до первой записи**, добавляет в `.gitignore` репозитория `qa-runs/` и `*.apk`, `*.aab`, `*.apks`, `*.xapk`, `*.keystore`, `*.jks` — без вопроса, если вы в запросе явно не разрешили класть результаты в репозиторий («коммить результаты»); APK и ключи — только по отдельному явному разрешению. Уже закоммиченные файлы `qa-runs/` скил не удаляет, а спрашивает, убрать ли их из индекса (`git rm -r --cached`). «Другая папка» для итогов получает только `summary.md`, `report.md`, `findings.json` и скриншоты находок. Чтобы все прогоны складывались в одно место — задайте `ANDROID_QA_OUTPUT_DIR` (абсолютный путь, не внутри репозитория скилов) в `env` файла настроек Claude Code (сначала резервная копия; если `env` уже есть — допишите строки в него):

macOS / Linux — `~/.claude/settings.json`:
```json
{
  "env": {
    "ANDROID_QA_OUTPUT_DIR": "/Users/<имя>/qa-results",
    "ANDROID_HOME": "/Users/<имя>/Library/Android/sdk"
  }
}
```
Windows — `%USERPROFILE%\.claude\settings.json` (обратный слэш в JSON удваивается или пишутся прямые слэши):
```json
{
  "env": {
    "ANDROID_QA_OUTPUT_DIR": "C:/Users/<имя>/qa-results",
    "ANDROID_HOME": "C:/Users/<имя>/AppData/Local/Android/Sdk"
  }
}
```
После изменения перезапустите Claude Code; `check_env` покажет путь в строке `ANDROID_QA_OUTPUT_DIR`.

## Переменные окружения скила

| Переменная | Что делает | По умолчанию |
|------------|-----------|--------------|
| `ANDROID_QA_OUTPUT_DIR` | папка результатов (раздел выше) | `<папка запуска>/qa-runs/` |
| `ANDROID_HOME`, `ANDROID_SDK_ROOT` | Android SDK (раздел «Переменные окружения» выше) | типовые папки SDK |
| `QA_RUN_DIR` (или `ANDROID_QA_RUN_DIR`) | папка прогона: обёртка `qa` (`scripts/qa`, `qa.ps1`) добавляет `--run-dir` к каждой команде; вместо serial можно писать `-` — берётся `ANDROID_SERIAL` или единственное устройство | не задана |
| `ANDROID_QA_EMU_RUNNING_DIR` | ещё одна папка, где искать файлы `pid_<pid>.ini` запущенных эмуляторов (gRPC `mic-inject`), если эмулятор пишет их не в стандартное место | стандартные папки ОС |
| `SITE_QA_PYTHON`, `SITE_QA_HEADLESS`, `SITE_QA_SLOWMO` | node-скрипты (аннотации скриншотов): команда Python для моста к `guard.py`, окно браузера без интерфейса (`1`), замедление в мс | `python3` (Windows — `python`), окно видно, `250` |
| `ANDROID_QA_STOP_FILE` | **задаёт сам скил** фоновой задаче (`job run`): файл запроса остановки `raw/jobs/<id>.stop`; вручную не задавать | — |
| `ANDROID_QA_SLEEP_SCALE`, `ANDROID_QA_LOOPBACK`, `ANDROID_QA_PLAYER` | **только для тестов** (`tests/`): масштаб пауз UI, подмена звукового loopback и проигрывателя | не заданы |

## Частые проблемы

| Симптом | Что сделать |
|---------|-------------|
| `/android-qa-audit` нет в списке, «Unknown skill» сразу после установки | скил виден только в новой сессии Claude Code; в текущей — попросить Claude прочитать `<SKILL_DIR>/SKILL.md` и работать по нему; иначе проверить, есть ли `<SKILL_DIR>/SKILL.md` и включён ли плагин (`claude plugin list`) |
| Два одинаковых скила | стоит и плагин, и папка/ссылка в `~/.claude/skills` — оставить один способ |
| `guard.py` — код 4, `adb_helpers.py` — код 6 «guard недоступен» | так и задумано (fail closed): нет или битый `run-config.yaml` (`--config` / `<RUN_DIR>/run-config.yaml`), неверный регэксп в правилах — исправить и повторить; на устройстве при этом ничего не выполнено |
| `avd_manager.py start` — код 3 «AVD уже запущен» | один стенд — один исполнитель: работать в уже запущенном эмуляторе (serial в сообщении), второй экземпляр — только `--read-only` |
| `adb: command not found`, а check_env видит adb | adb не в PATH — скил работает и так (в `check_env` это OK, не WARN); для терминала — «Переменные окружения» выше |
| check_env: «Android SDK не найден» | задать `ANDROID_HOME` (в профиле и в `env` настроек Claude Code) или поставить SDK по разделу «Android SDK» |
| `sdkmanager`: «Could not determine SDK root» / «JAVA_HOME is not set» | структура `<SDK>/cmdline-tools/latest/bin`; задать `JAVA_HOME` (JDK 17+) |
| `sdkmanager`/`avdmanager`: «integer expression expected» | ранняя сборка Java (`-ea`) — безвредно (скил скрывает при успешной команде); рекомендуется JDK 17 или 21 (Temurin) |
| Эмулятор не стартует, «PANIC: Missing emulator engine» / «x86_64 emulation currently requires hardware acceleration» | ускорение («Аппаратное ускорение»); образ под ABI хоста (Apple Silicon — `arm64-v8a`); `sdkmanager "emulator"` обновить |
| Эмулятор стартует, но чёрный экран / зависает | `avd_manager.py start … --cold-boot`; `--gpu swiftshader_indirect`; меньше потоков; проверить ОЗУ хоста |
| «Not enough space» / `INSTALL_FAILED_INSUFFICIENT_STORAGE` | освободить диск (15+ ГБ); AVD с большим `--data 8G` |
| `adb devices`: `offline` | `adb reconnect offline`; переподключить кабель; `adb kill-server && adb start-server`; перезапустить эмулятор |
| `adb devices`: `unauthorized` | разблокировать телефон, «Разрешить» в диалоге отладки; если диалога нет — «Отозвать авторизацию отладки» в настройках разработчика и переподключить |
| `adb devices`: `no permissions` (Linux) | правила udev, пользователь в группе `plugdev` |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | подпись отличается от установленной версии — удалить старую (данные пропадут; скил спросит) |
| `INSTALL_FAILED_VERSION_DOWNGRADE` | версия ниже установленной — удалить или `install --downgrade` (только debuggable) |
| `INSTALL_FAILED_NO_MATCHING_ABIS` | в APK нет нативного кода под ABI устройства — другой образ (x86_64/arm64) или реальное устройство |
| `INSTALL_FAILED_OLDER_SDK` | minSdk приложения выше версии Android стенда — образ новее |
| `INSTALL_FAILED_TEST_ONLY` | testOnly-сборка — `install --allow-test` |
| `INSTALL_FAILED_MISSING_SPLIT` / `INSTALL_FAILED_INVALID_APK` | передать все split APK вместе; для AAB — `apk_info.py build-apks … --universal` |
| `INSTALL_PARSE_FAILED_NO_CERTIFICATES` | APK не подписан — нужна подписанная (хотя бы отладочным ключом) сборка |
| `INSTALL_FAILED_DEPRECATED_SDK_VERSION` | targetSdk < 23 на Android 14+ — `adb install --bypass-low-target-sdk-block` вручную |
| `INSTALL_FAILED_USER_RESTRICTED` (Xiaomi и др.) | включить «Установка через USB» в параметрах разработчика |
| `INSTALL_FAILED_VERIFICATION_FAILURE` | установку заблокировал Play Protect — решение пользователя |
| Кириллица не вводится | ограничение `adb input text`: `text … --clipboard` (эмулятор, запущенный с `--mic-inject`; не для паролей), `text … --adbkeyboard` (ADBKeyBoard на эмуляторе скила: `ime install-adbkeyboard --apk …` с вашего согласия), `text … --translit` (латиницей) или вручную в окне эмулятора |
| `mic-inject`: «token is invalid» / UNAUTHENTICATED | эмулятор запущен без `--mic-inject` (или из Android Studio — там JWT) — перезапустить `avd_manager.py start <AVD> --mic-inject`; токен консоли `~/.emulator_console_auth_token` для gRPC не подходит |
| `mic-inject`: «не поддерживается: …» | так и задумано: в сообщении причина и следующий путь (gRPC → loopback → файл); файл — `mic-inject --via file` и импорт в приложении |
| `dump-ui`: «could not get idle state» | экран с бесконечной анимацией: `dump-ui --retry 6 --ignore-animations`; нажатие — `tap X Y --no-ui` после скриншота |
| `annotate_android.py`: «не поддерживается: нет модуля playwright» | «Аннотации скриншотов» выше; оригинал и spec сохранены |
| Windows: `python3` открывает Microsoft Store | `python` или `py -3`; отключить псевдонимы в «Параметры → Приложения → Псевдонимы выполнения приложений» |
| Windows: «выполнение сценариев отключено» | `powershell -ExecutionPolicy Bypass -File …` |
| Windows: `tests/unit.sh` не запускается | нужен bash: Git Bash или WSL |
| Скил запустился, хотя вы не просили тест | ответить «Нет, это другое» — скил ничего не создаст |

Подробности — [README.md](README.md) (параметры, примеры, ограничения) и [SKILL.md](SKILL.md) (порядок работы).
