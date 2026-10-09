# android-qa-audit 1.2.0 (отзывы второго круга, issues #13–#21): ход работы и отложенное

Ветка `feature/android-qa-1-2-0` (от `docs/feedback-round2`). Источник — отзыв реального прогона (голосовое приложение с офлайн-расшифровкой, Android 14, три эмулятора, записи до 60 минут, публикация в чужой трекер по его формам). В скил не перенесены конкретные приложения, пакеты, репозитории и устройства (тест универсальности дополнен этими именами). Что сделано, описано в `skills/android-qa-audit/CHANGELOG.md` (1.2.0).

## Чек-лист
- [x] Фаза 1: masking (токены), guard (флаги эмулятора, push медиа, run-as, `emu avd discoverypath`, `preapproved_packages`, `hostmicon`)
- [x] Фаза 2: `grpc_emu.py` (gRPC поверх HTTP/2 на stdlib), `mic-inject` / `mic-status` (3 пути), `avd_manager start --extra-args / --mic-inject`, loopback в `check_env`
- [x] Фаза 3: `tap --no-ui`, `dump-ui --retry/--texts/--grep/--ignore-animations`, неоднозначность `tap`, `--expect-text/--expect-gone/--expect-change`, `scroll` (изменился ли экран), `launch --wait-focus`, `find` с `box`
- [x] Фаза 4: `notifications` (прогресс, ongoing, FGS, действия)
- [x] Фаза 5: `soak`, `job`, `build_report` «Длинные сценарии», загрузка хоста, шумовые теги logcat, `logcat stop --summary`
- [x] Фаза 6: аннотации (`node/annotate.js` — вендорная копия), `annotate_android.py`, `screenshot --mark`, `finding.py add`, `render_draft` — аннотированный снимок
- [x] Фаза 7: публикация — `shared/qa_issueforms.py`, `qa_known.py`, `qa_attachments.py`, обёртки, `render_draft --form/--human-steps`, `disclosure: tool|none`
- [x] Фаза 8: `import-file`, `push-media`, `ime install-adbkeyboard`, `text --clipboard`, обёртка `qa`, примеры без переменных-команд
- [x] Фаза 9: матрица — `phone-8gb`, существующие `qa-*` AVD, `matrix.cells`, время «ручное + фон»
- [x] Фаза 10: `intake --lite`, явный вызов по имени, мелочи (`check_env` adb вне PATH, `wait-boot` «готов», `--journal-done`)
- [x] Фаза 11: документация (SKILL.md, references, templates, README, INSTALL, CHANGELOG, plugin.json 1.2.0)
- [x] Фаза 12: тесты (3.14 и 3.9), validate, тесты site-qa-audit, коммиты

## Отложено и почему
| Пункт | Что не сделано | Почему |
|-------|----------------|--------|
| #15 (3.3) | График PSS картинкой в отчёте | В отчёте таблица (мин–макс, рост МБ/ч) и сырые точки `raw/soak-*.jsonl`; картинка потребовала бы рисования без сторонних библиотек или Node — отдельная задача, если таблицы мало. |
| #17 (прототип contact_sheet) | Контактный лист скриншотов | У site-qa-audit он есть в `shot.js sheet` (Playwright); перенос — вместе с общим модулем снимков, не в этом круге. Просмотр аннотаций — по одному (Read) + `finding.py viewed`. |
| #18 (приёмка «одна команда publish») | Одна команда «формы + картинки + создание issues» | Намеренно: создание issues по правилам скила идёт только после сводной таблицы и «да» пользователя. Есть цепочка: `issue_forms.py fetch` → `attachments.py push --yes` → `render_draft.py --form auto --attachments-base …` → `gh issue create` по одной (или субагент с блоком правил). |
| #14 (3.2) | `uiautomator dump --compressed` | Сжатое дерево скрывает «неважные» узлы, в том числе тексты, — вредно для поиска элементов и a11y-кандидатов. Вместо него `--retry` с нарастающей паузой и `--ignore-animations`. |
| #19 (3.10) | Скачивание ADBKeyBoard скилом | Стороннее приложение из интернета: APK даёт пользователь, скил только ставит его на свой эмулятор после «да». Без установки — `text --clipboard` (буфер эмулятора по gRPC). |
| #13 (путь 2) | Воспроизведение в loopback на Windows | Нет штатного проигрывателя с выбором устройства без сторонних программ: путь отвечает «не поддерживается», дальше — gRPC или файл. |
| — | Windows: `job stop` для soak | `taskkill /T /F` завершает задачу без сигнала — сводка soak при остановке на Windows не пишется (по окончании сама — пишется). |

## Не проверено вживую
- **gRPC эмулятора** (`--mic-inject`, `mic-status`, `mic-inject --via grpc`, `text --clipboard`): живого эмулятора с `-grpc-use-token` не было (эмуляторы в работе не запускались). Клиент проверен на поддельном сервере HTTP/2 (`tests/helpers/fake_grpc.py`: Bearer-токен, ответы с HPACK-индексацией и Хаффманом, окно потока 4 КБ, Trailers-Only с UNAUTHENTICATED) и на примерах RFC 7541 C.4/C.6. Схема авторизации (discovery-файл `pid_<pid>.ini`, ключи `grpc.port` / `grpc.token`, заголовок `authorization: Bearer <token>`, путь — `adb emu avd discoverypath`) — по документации эмулятора (release notes 30.0.26) и открытым клиентам (android-emulator-rs: `grpc.token`, «Bearer {token}»); поля `AudioPacket` / `AudioFormat` — по `emulator_controller.proto` (platform/tools/base). Первое живое использование: `mic-status`, затем 5–10 с речи, проверить уровень в приложении.
- **Loopback** (`system_profiler` для устройств по умолчанию на macOS, `paplay --device` на Linux, `adb emu avd hostmicon/hostmicoff`) — на фейках.
- **Реальный формат `dumpsys notification --noredact`** с уведомлением foreground-сервиса — разбор сделан устойчивым (все записи пакета, CRLF, архив отдельно, сверка с `dumpsys activity services`), но на живом выводе с прогрессом не проверен; причину исходного «count: 0» по одному отзыву воспроизвести не удалось — гипотеза: разбор по позициям записей и `extras` с переносами строк.
- **`import-file`** в настоящем Documents UI (подписи «Show roots», «Downloads» зависят от версии Android и языка; учтены RU/EN варианты) и `--ignore-animations` на настоящем экране с анимацией.
- **`soak` / `job`** на эмуляторе (время, выключение экрана, `--result-file` с реальной записью), `ime install-adbkeyboard` с настоящим APK.
- **Аннотации** — проверены вживую на этой машине: `annotate_android.py render` с настоящим Node 22 и Playwright из установленного site-qa-audit (`ANDROID_QA_NODE_MODULES`) на синтетическом снимке 1080×2400 — пунктирные рамки, стрелки, подписи в поле справа, проверки `inside`/`covers` пройдены. В тестах — поддельный node.
- **Формы issue и вложения веткой** — на поддельном `gh` (contents API, ветки); на настоящем GitHub не публиковалось.

## Найдено по дороге
- Пример в `references/device-control.md` с переменной из нескольких опций (`D="--serial … --run-dir …"` и `… $D`) — тот самый, что ломается в zsh; переписан на обёртку `qa`, добавлен тест `helpers/doc_zsh.py`.
- `guard.py emulator-args "-allow-host-audio"` (цель, начинающаяся с «-») argparse принимал за опцию → код 4 «неверные аргументы»; исправлено для `emulator-args` и `adb`.
- `tools/validate.sh --fix` заодно выполняет `sync` (корневые README.md и marketplace.json) — после него корневые файлы возвращались к исходному состоянию (их обновляет оркестратор).

## Где остановился
2026-10-09: всё по #13–#21 сделано в ветке `feature/android-qa-1-2-0` (несколько коммитов), кроме пунктов таблицы «Отложено». Проверки: `android-qa-audit/tests/unit.sh` — PASS 222, FAIL 0 (Python 3.14 и 3.9.6); `site-qa-audit/tests/unit.sh` — PASS 53, FAIL 0 (потоки B/C пропущены: в рабочей копии нет `node_modules`); `tools/validate.sh` — одна ожидаемая ошибка (версия marketplace.json 1.1.0 ≠ 1.2.0), на копии после `skillsrepo.py sync` — 0 ошибок. Следующий шаг (оркестратор): слияние, `python3 tools/lib/skillsrepo.py sync`, корневой CHANGELOG, тег `android-qa-audit/v1.2.0`, живая проверка по `tests/README.md` → «Живая проверка», п. 4.
