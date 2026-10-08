# compatibility — Совместимость с версиями Android

Направление: `compatibility` · Инструменты: `<SKILL_DIR>/scripts/apk_info.py analyze|summary` (minSdk, targetSdk, разрешения и с какого API они запрашиваются, ABI, `risks`), `matrix.py` (ячейки по API: min, target, последний), `avd_manager.py start`, `adb_helpers.py` (ниже без пути и общих опций `--serial S --run-dir <RUN_DIR>`; PKG — `app.package` из run-config): `install`, `permissions`, `grant`, `revoke`, `notifications`, `crashes` · Усилители: Maestro или Appium — один сценарий на всех API, если установлены

## Цель
Проверить поведение на минимальном, целевом и последнем API матрицы: изменения платформы в разрешениях, хранилище, уведомлениях, фоне, навигации «назад» и отображении от края до края. Для каждой находки указать, на каких API она воспроизводится и на каких нет.

## Безопасность в этом направлении
- Перед каждым нажатием `adb_helpers.py tap …` guard.py проверяет действие сам: код 3 — запрет, записать «не проверено: запрет <rule>»; код 2 — спросить пользователя и повторить с `--confirmed` только после «да».
- Системные экраны (выбор фото и файлов, настройки, камера) guard пропускает только с подтверждением; Play Store, браузер, звонилка — запрет, сразу `key BACK`.
- `install` и `uninstall` на реальном устройстве — только с согласием из `stands.consent`; удаление стирает данные — спросить пользователя.
- `grant` и `revoke` — только разрешения тестируемого пакета.

## Smoke
- [ ] `compat.target-sdk` — кандидат из `risks` (targetSdk ниже требования Google Play) → сверить с требованием на дату релиза → Info, для обновления в магазине — выше.
- [ ] `compat.install` — `install APK` на каждой ячейке API → дефект: `INSTALL_FAILED_OLDER_SDK` при заявленной поддержке, `INSTALL_FAILED_NO_MATCHING_ABIS`, `INSTALL_PARSE_FAILED_MANIFEST_MALFORMED` (компонент с intent-filter без `android:exported` при targetSdk 31+).
- [ ] `compat.min-api` — основной сценарий на ячейке minSdk → `crashes` → дефект: `NoSuchMethodError`, `NoClassDefFoundError`, `VerifyError`, функции молча отсутствуют.
- [ ] `compat.latest-api` — основной сценарий на последнем API матрицы → дефект: падения и поведение, которого нет на target API.
- [ ] `compat.notifications-33` — API 33+: `POST_NOTIFICATIONS` запрашивается в момент нужды, отказ не ломает приложение; `notifications PKG` после разрешения; на API < 33 уведомления работают без запроса → дефект: запроса нет и уведомления молча не приходят, падение после отказа.

## Standard (в дополнение к smoke)
- [ ] `compat.media-permissions` — API 33+: `READ_MEDIA_IMAGES|VIDEO|AUDIO` вместо `READ_EXTERNAL_STORAGE`; API 34+: частичный доступ («Выбрать фото») → выбрать часть фото → дефект: приложение видит пустую галерею, падает, требует полный доступ без причины.
- [ ] `compat.location` — API 31+: приблизительное и точное местоположение; фоновое — отдельным запросом (API 30+) → `revoke`, повторный запрос → дефект: падение при приблизительном, просьба «всегда» без объяснения.
- [ ] `compat.scoped-storage` — API 29/30+: сохранение и экспорт файлов, вложения, загрузки → дефект: `SecurityException` или `FileNotFoundException` в `crashes`, файл не сохраняется.
- [ ] `compat.pending-intent` — targetSdk 31+: уведомления, виджеты, будильники создаются без падения → дефект: `IllegalArgumentException` с требованием `FLAG_IMMUTABLE` или `FLAG_MUTABLE`.
- [ ] `compat.exact-alarms` — напоминания и будильники: API 31+ `SCHEDULE_EXACT_ALARM`, API 33+ `USE_EXACT_ALARM`, на API 34+ разрешение не выдаётся по умолчанию → `permissions PKG` → дефект: напоминание не срабатывает без сообщения, `SecurityException`.
- [ ] `compat.fgs-type` — targetSdk 34+: запуск foreground service (загрузка, плеер, навигация) → дефект: `MissingForegroundServiceTypeException` или `SecurityException` в `crashes`.
- [ ] `compat.background-limits` — фоновый запуск сервисов (API 26+) и activity (API 29+): `key HOME` во время операции → дефект: `IllegalStateException: Not allowed to start service`, операция обрывается.
- [ ] `compat.receivers-intents` — targetSdk 34+: регистрация receiver без флага экспорта, неявные интенты к своим компонентам → дефект: `SecurityException` в `crashes`, функция молча не работает.
- [ ] `compat.predictive-back` — API 34+ (opt-in), системные анимации на 35+, при targetSdk 36 включено по умолчанию (`onBackPressed` не вызывается) → `key BACK` на экранах со своей обработкой «назад» → дефект: Back закрывает экран мимо диалога «сохранить?», выход из приложения вместо шага назад.
- [ ] `compat.edge-to-edge` — API 35+ при targetSdk 35+ (на targetSdk 36 отключить нельзя) → скриншоты тех же экранов на API 34 и 35+ → дефект: контент под статус-баром и панелью навигации только на 35+.
- [ ] `compat.package-visibility` — targetSdk 30+: «Открыть в…», «Поделиться», карты, почта → только наблюдать системный выбор, `key BACK` → дефект: «нет приложений для открытия» при их наличии.

## Deep (в дополнение к standard)
- [ ] `compat.every-api` — все основные сценарии на всех ячейках API матрицы → таблица «сценарий × API».
- [ ] `compat.abi` — образы x86_64 и arm64 (или реальное устройство): установка и запуск с нативным кодом → дефект: `UnsatisfiedLinkError`, падение только на одном ABI.
- [ ] `compat.page-size-16k` — если пользователь предоставил стенд с 16 КБ страницами памяти (Android 15+): запуск приложения с нативным кодом → дефект: падение при загрузке библиотеки (`dlopen failed`).
- [ ] `compat.webview` — экраны на WebView на ячейке minSdk со старым WebView образа → дефект: пустая страница, сломанная вёрстка, ошибки в logcat.
- [ ] `compat.upgrade-across-target` — старая версия → `install NEW.apk --replace` на API 33+ → дефект: после обновления пропали уведомления или доступ к медиа без нового запроса.
- [ ] `compat.old-api-theme` — API < 29 (нет системной тёмной темы): переключатель темы в самом приложении и вид компонентов → дефект: сломанные цвета, отсутствующие иконки.

## Типовые находки и severity
| Пример | Severity (см. `references/severity.md`) |
|---|---|
| Падение основного сценария на поддерживаемом API (minSdk или последнем) | Critical / High |
| `MissingForegroundServiceTypeException` или `FLAG_IMMUTABLE` — падение функции | High |
| На API 33+ уведомления молча не приходят без запроса разрешения | High / Medium |
| Контент под системными барами только на API 35+ | Medium |
| Частичный доступ к фото показывает пустую галерею | Medium |
| Напоминание не срабатывает на API 34+ без сообщения | Medium |
| targetSdk ниже требования Google Play | Info |

## Что записывать в находку
- API, где воспроизводится, и API, где нет (поле `environment_list`), targetSdk и minSdk из `apk-info.json`.
- Экран — activity из `current`; элемент — `id=<resource-id>` или `text="…"` + класс; шаги с чистого запуска; repro_rate («3/3») на каждом API.
- Окружение: профиль железа, ABI образа, вариация, ячейки матрицы `c01…`.
- `logcat_excerpt` из `crashes` (замаскированный) с именем исключения; состояние разрешений из `permissions PKG`.
- Скриншоты одного экрана на разных API: `screenshots/<id>-api34.png`, `screenshots/<id>-api35.png`.
