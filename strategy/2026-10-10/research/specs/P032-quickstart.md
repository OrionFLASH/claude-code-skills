# P032. Quickstart «первый результат за 5 минут» для каждого скила: промпт и ожидаемый вывод
Приоритет: P0 · Горизонт: now · Предпосылки: нет (`blocked_by` пуст) · Связанные: P029, P033, P060, P030, P024, P051, P069 · Макет: не предусмотрен (дизайн выключен выбором, у продукта нет UI)

Обоснование — P032 в реестре, раздел 10 стратегии. Здесь — только как сделать. Устаревшее допущение реестра («общего quickstart нет — писать с нуля») поправлено по `research/gap-audit.md`: основа уже есть.

## Проблема
- Путь от установки до первого результата описан в длинных INSTALL.md (у site-qa-audit — разделы на ≈ 370 строк, `skills/site-qa-audit/INSTALL.md:15-371`) и разный у каждого скила [факт].
- site-qa-audit после установки и каждого обновления требует `npm install` и браузеры Playwright в папке версии (`README.md:44`, `skills/site-qa-audit/SKILL.md:181`) и плагин Playwright MCP (`skills/site-qa-audit/INSTALL.md:171`) [факт].
- Готовые сценарии первого результата уже есть, но спрятаны: dry-run site-qa-audit на публичном стенде (`skills/site-qa-audit/tests/dry-run-todomvc.md:7`), демо product-strategy с ожидаемым выводом без токенов (`skills/product-strategy/INSTALL.md:158-165`), проверка заметки typesafe-triage (`skills/typesafe-triage/INSTALL.md:350`) [факт].
- android-qa-audit требует JDK, Android SDK и образ эмулятора на 3–6 ГБ (`skills/android-qa-audit/INSTALL.md:156-171`): «5 минут с нуля» для него недостижимы [оценка].

## Цель и метрики успеха
- **Основная:** время от «скил установлен» до первого файла результата на чистой машине, по каждому скилу, замер владельцем или знакомым: typesafe-triage ≤ 5 мин, product-strategy (демо) ≤ 5 мин, site-qa-audit ≤ 20 мин (включая `npm install` и Chromium), android-qa-audit ≤ 10 мин при уже установленном SDK [оценка; целевые значения — ДОПУЩЕНИЕ, уточнить первым замером].
- **Исход:** доля установивших, дошедших до первого отчёта, ↑ на +10..20 п. п. [ДОПУЩЕНИЕ: из реестра; прямого счётчика нет — прокси: просмотры quickstart-разделов (popular paths P043) и внешние Issues об установке].
- **Защитные:** все команды quickstart проходят проверку `doc_commands.py` (`shared/tests/doc_commands.py:9`); ни один quickstart не публикует в GitHub и не трогает чужие сайты (только публичные стенды, `CONVENTIONS.md:21`); `tools/validate.sh` без ошибок.

## Решение
Раздел **«Быстрый старт»** в начале `README.md` каждого скила (сразу после первого абзаца), в одном формате из трёх шагов:

1. **Поставить** — две команды маркетплейса + шаги, без которых первый результат невозможен.
2. **Запустить** — один готовый промпт или команда.
3. **Что получится и сколько займёт** — список файлов и замеренное время с пометкой «замер <дата>».

| Скил | Шаг «поставить» сверх маркетплейса | Первый результат | Что появится |
|---|---|---|---|
| typesafe-triage | перезапуск или `/reload-plugins`; `typesafe_triage.py --check` (`skills/typesafe-triage/INSTALL.md:343`); ключ не обязателен — без него локальные сигналы (`skills/typesafe-triage/README.md:29`) | любой запрос длиннее 40 символов | заметка «ДЕЙСТВИЕ: …» в контексте запроса (`skills/typesafe-triage/INSTALL.md:350`) |
| product-strategy | `check_env.py` | `make_demo.py /tmp/ps-demo` и `build_all.py /tmp/ps-demo --skip links` (`skills/product-strategy/INSTALL.md:162`) — без токенов | `/tmp/ps-demo/deliverables/index.html`, `strategy.xlsx` (`skills/product-strategy/INSTALL.md:165`); следующий шаг — настоящий прогон `!strategy автопилот` |
| site-qa-audit | Playwright MCP (`/plugin install playwright@claude-plugins-official`), `cd scripts/node && npm install && npx playwright install chromium`, `check_env.sh --fast --no-browsers` (`skills/site-qa-audit/INSTALL.md:260`) | промпт из `skills/site-qa-audit/tests/dry-run-todomvc.md:7` (smoke, три направления, dry-run, без репозиториев) | `./qa-runs/<дата>-demo.playwright.dev/`: `run-config.yaml`, `findings.json`, `report.md`, `summary.md`, `drafts/` (`skills/site-qa-audit/README.md:64`) |
| android-qa-audit | два уровня: (а) SDK уже есть — `check_env.sh` (`skills/android-qa-audit/INSTALL.md:271`); (б) с нуля — ссылка на «Окружение» INSTALL, без обещания 5 минут | (а) чтение APK без эмулятора: `apk_info.py analyze <свой APK> --summary` (`skills/android-qa-audit/tests/README.md:19`); затем smoke-промпт `skills/android-qa-audit/README.md:57` | сводка APK в терминале; после smoke — `report.md` в папке результатов |

Для Windows — те же шаги в PowerShell рядом (как в INSTALL.md каждого скила). На главной README (P029) — ссылки «Быстрый старт» на эти разделы.

**Почему раздел в README скила, а не `docs/quickstart/*.md` из реестра:** README скила едет вместе с плагином при установке из маркетплейса и уже проверяется тестом примеров команд (`shared/tests/doc_commands.py:120` сканирует SKILL.md, README.md, INSTALL.md и references) — неверная команда в quickstart уронит `unit.sh`. Отдельные файлы в `docs/` такой проверки не получат.

**Не входит:** автоматизация установки Node-зависимостей (P060); англоязычные quickstart (решение в P069); новый демо-режим android-qa-audit без эмулятора; видео (P030).

## Пользовательские сценарии
1. Как пользователь Claude Code, я хочу увидеть работу typesafe-triage сразу после установки, чтобы понять, что хук работает.
   - Given плагин установлен, ключа нет; When выполняю `/reload-plugins` и отправляю задачу длиннее 40 символов; Then в контексте есть заметка «ДЕЙСТВИЕ: …» с пометкой о локальных сигналах; время ≤ 5 мин.
2. Как основатель, я хочу посмотреть, как выглядит стратегия, не тратя токены, чтобы решить, запускать ли настоящий прогон.
   - Given плагин product-strategy установлен, Python 3.10+; When выполняю две команды из quickstart; Then открывается `deliverables/index.html` с пометкой «демо»; токены не расходуются.
3. Как QA-инженер, я хочу получить первый отчёт site-qa-audit на безопасной цели, чтобы оценить качество находок.
   - Given выполнены шаги «поставить» и `check_env` выдал «Итог: можно работать»; When вставляю промпт quickstart; Then в `./qa-runs/<дата>-demo.playwright.dev/` есть `report.md` и черновики, ни одного перехода за `demo.playwright.dev` и ни одного `gh issue create` (критерии `skills/site-qa-audit/tests/dry-run-todomvc.md:27-30`).
4. Как мобильный QA с готовым Android SDK, я хочу получить первый результат без эмулятора, чтобы убедиться, что скил видит мой APK.
   - Given SDK и build-tools установлены; When запускаю `check_env.sh` и `apk_info.py analyze app.apk --summary`; Then вижу сводку APK и «Итог: можно работать»; эмулятор не нужен.
5. Как владелец, я хочу знать, что команды quickstart не устарели, чтобы новичок не упёрся в ошибку.
   - Given раздел «Быстрый старт» в README скила; When запускаю `tests/unit.sh` (site, android) или pytest доков (typesafe, product-strategy); Then все `<скрипт>.py <подкоманда> --опция` из раздела проходят проверку парсером.

## Требования
**Функциональные**
- F1. Раздел «Быстрый старт» в `skills/<скил>/README.md` всех четырёх скилов, ≤ 25 строк, три шага.
- F2. Только существующие команды и опции (проверка `doc_commands.py`); для product-strategy и typesafe-triage — их собственные тесты доков (`skills/typesafe-triage/scripts/test_typesafe_docs.py`, `skills/product-strategy/tests/test_core.py:296`).
- F3. Цели — только публичные стенды и демо-данные; режим site-qa-audit — dry-run, без репозиториев.
- F4. Время каждого шага — из замера на чистой машине, с датой; без замера — «≈ N мин [оценка]».
- F5. Честная строка про повтор `npm install` после обновления site-qa-audit (до P060) и про Playwright MCP.
- F6. Ссылки из корневого README (карточки P029) на якоря разделов.

**Нефункциональные**
- Скорость: см. основную метрику; для site-qa-audit — глубина smoke и три направления, чтобы прогон был коротким и дешёвым.
- Приватность: никаких реальных сайтов, логинов, APK третьих лиц в примерах; путь к APK — заглушка `app.apk`.
- Кроссплатформенность: команды macOS/Linux и Windows (PowerShell) рядом.
- i18n: RU (решение владельца); английский — по решению в P069.

## Затрагиваемые части системы
- `skills/typesafe-triage/README.md` (вставка после вводного абзаца, до `## Входные параметры` на `:34`); источники — `skills/typesafe-triage/INSTALL.md:330-350`.
- `skills/product-strategy/README.md` (до `## Как запустить`, `:18`); источники — `skills/product-strategy/INSTALL.md:158-165`, `skills/product-strategy/scripts/make_demo.py:2-7`.
- `skills/site-qa-audit/README.md` (до `## Что проверяется`, `:11`); источники — `skills/site-qa-audit/tests/dry-run-todomvc.md:5-10`, `skills/site-qa-audit/INSTALL.md:255-271`, `README.md:44`.
- `skills/android-qa-audit/README.md` (до `## Что проверяется`, `:17`); источники — `skills/android-qa-audit/INSTALL.md:269-280`, `skills/android-qa-audit/tests/README.md:19`.
- Проверки: `shared/tests/doc_commands.py:120` (копии в `skills/*/tests/helpers/shared/`, не править вручную — `CONVENTIONS.md:39`).
- Версии скилов: PATCH каждого скила (документация) с записью в его `CHANGELOG.md` и тегом `<скил>/vX.Y.Z` (`CONVENTIONS.md:29-32`); `tools/validate.sh --fix` (SHA256SUMS typesafe-triage обновится сам — `tools/lib/skillsrepo.py:158-163`).
- `README.md` — ссылки из карточек (P029).

## Аналитика
| Событие | Когда | Свойства |
|---|---|---|
| `quickstart_test` | прогон на чистой машине | скил, ОС, шаг, минуты на шаг, итог (ok/fail), где застрял — ручная строка в журнале P043 |
| `gh_path_view` | снимок P043 | path=`…/tree/main/skills/<скил>` и `…/blob/main/skills/<скил>/README.md`, count, uniques |
| `install_issue_opened` | внешний Issue | скил, шаг, причина — ручная разметка |

## Риски и меры
- «5 минут» не выполняются для site и android → честные цифры по замеру (F4), двухуровневый quickstart android; заголовок «Быстрый старт», а не «за 5 минут», если замер больше.
- Скачивание браузеров Playwright долгое и при P060 не исчезнет (мягкая связь с P060, `research/gap-audit.md`) → только Chromium, остальное — по желанию.
- Публичный стенд todomvc изменится или пропадёт → запасная цель: локальная фикстура `skills/site-qa-audit/tests/fixtures/local-app` через `file://`.
- Прогон тратит токены пользователя → smoke, три направления, предупреждение в шаге 3.
- Нет чистой машины для замера → новая учётная запись ОС или виртуальная машина [ДОПУЩЕНИЕ: доступна владельцу]; для Windows — знакомый.

## План выпуска
- Флаг не нужен. Ветка `docs/quickstart`.
- Этап 1: typesafe-triage и product-strategy (основа готова, без токенов).
- Этап 2: site-qa-audit — замер на том же dry-run, что для P030/P033/P070.
- Этап 3: android-qa-audit, уровень (а).
- Этап 4: прогон на чистой машине (минимум macOS; Windows — по возможности), правки, PATCH-версии скилов, ссылки из README (P029).
- A/B: нет.
- Откат: `git revert` раздела; PATCH-версия скила откатывается следующим PATCH.

## Оценка
| Часть | Дни |
|---|---|
| Четыре раздела на готовых сценариях | 1–1,5 |
| Прогоны на чистой машине (android — тяжелее) | 1–1,5 |
| Исправления найденного (команды, пропущенные шаги) | 0,5 |
| PATCH-версии, CHANGELOG, validate, ссылки из README | 0,25 |
| **Итого** | **2,75–3,75** |

Согласовано с `effort_days` 2–4; ближе к середине, а не к нижней границе из gap-audit, потому что замер на чистой машине — самая дорогая часть. Зависимостей нет; мягко — P060 (сократит шаг «поставить» у site и android, когда будет сделан).

## Открытые вопросы
1. Целевые времена (5 / 5 / 20 / 10 мин) — устраивают ли владельца как публичные обещания до первого замера?
2. Для android-qa-audit уровень (а) — достаточно ли «сводки APK» как первого результата, или нужен сразу smoke на эмуляторе?
3. Нужен ли общий раздел «Быстрый старт» в корневом README или только ссылки из карточек (P029)?
