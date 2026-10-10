# P059. CI в GitHub Actions: validate и тесты на Linux, macOS и Windows
Приоритет: P0 · Горизонт: now · Предпосылки: нет (`blocked_by` пуст) · Связанные: P061, P067, P064, P066, P068, P071, P072, P073 (ждут CI), P043, P069 (их тесты запускаются здесь), P029 (бейдж), P033 (заявленные платформы) · Макет: не предусмотрен (дизайн выключен выбором, у продукта нет UI)

Обоснование — P059 в реестре, раздел 10 стратегии; бесплатность стандартных раннеров для публичных репозиториев — в `evidence` P059 реестра. Здесь — только как сделать.

## Проблема
- CI нет: каталога `.github/` в репозитории нет, проверки (`tools/validate.sh`, `tests/`) запускаются вручную [факт: ls, 2026-10-10; `research/product-understanding.md`].
- ≈600 тестовых функций в 32 файлах [факт: repo-facts] разложены по четырём разным схемам запуска: `skills/site-qa-audit/tests/unit.sh` (bash, браузерные наборы — SKIP без Playwright, `skills/site-qa-audit/tests/unit.sh:131-134`); `skills/android-qa-audit/tests/unit.sh` (bash, фейковые adb и SDK, `skills/android-qa-audit/tests/README.md:15`); pytest рядом со скриптами у typesafe-triage (`skills/typesafe-triage/tests/README.md:3`, `:7`); pytest в `skills/product-strategy/tests/` (а `skills/product-strategy/tests/README.md:3` — незаполненная заготовка).
- Заявлены macOS и Windows (`README.md:20`), Linux — «как macOS» (`skills/site-qa-audit/INSTALL.md:3`); автоматически ни одна платформа не подтверждена [факт].
- Минимальные версии Python различаются: 3.8+ для `tools/` (`tools/lib/skillsrepo.py:8`), 3.9+ для site и android (`skills/site-qa-audit/SKILL.md:183`, `skills/android-qa-audit/tests/unit.sh:4`), 3.10+ для product-strategy (`skills/product-strategy/scripts/check_env.py:165`) [факт]. Шаг реестра «матрица Python 3.9 и 3.12» для всех наборов не подходит product-strategy.
- Файла `.gitattributes` нет [факт: ls]: на Windows-раннере git по умолчанию переводит переводы строк в CRLF [ДОПУЩЕНИЕ: стандартная настройка Git for Windows], и bash-скрипты (`*.sh`, 24 файла) могут падать на `\r`. Суммы `SHA256SUMS` к этому устойчивы (`shared/scripts/skill_sums.py:9`), bash — нет.

## Цель и метрики успеха
- **Основная:** 100 % коммитов в main и PR с зелёной проверкой после включения обязательного статуса [факт-метрика: история Actions].
- **Вспомогательные:** платформ, подтверждённых автоматически: 0 → 3 (ubuntu, macos, windows) к 2026-12-15 (порог критерия отказа ставки 3, `build/strategy-facts.md`) [ДОПУЩЕНИЕ: дата из стратегии]; время полного прогона ≤ 15 мин на ОС [оценка].
- **Защитные:** 0 секретов в workflow (ни одного `secrets.*`; тесты, которым нужна сеть или ключ TypeSafe, не запускаются); действия закреплены по SHA; права `contents: read`; локальный запуск тестов работает как раньше.

## Решение
Один workflow `.github/workflows/ci.yml`, события `push` (main) и `pull_request`, `concurrency` с отменой устаревших запусков, `permissions: contents: read`.

| Job | ОС | Python | Что запускает |
|---|---|---|---|
| `validate` | ubuntu | 3.12 | `tools/validate.sh` (код 1 при ошибках, `tools/lib/skillsrepo.py:331`) |
| `validate-windows` | windows | 3.12 | `tools/validate.ps1` (PowerShell-обёртка, `tools/validate.ps1:4-5`) |
| `qa-unit` | ubuntu, macos, windows (bash) | 3.9, 3.12 | `QA_SKIP_BROWSER=1 bash skills/site-qa-audit/tests/unit.sh`; `bash skills/android-qa-audit/tests/unit.sh` (`PY` — из setup-python, `skills/android-qa-audit/tests/unit.sh:7`) |
| `triage-pytest` | ubuntu, macos, windows | 3.9, 3.12 | `python -m pytest skills/typesafe-triage/scripts -q -p no:cacheprovider` и `typesafe_triage.py --selftest --heuristic` (офлайн, `skills/typesafe-triage/tests/README.md:7`, `:19`) |
| `strategy-pytest` | ubuntu, macos, windows | 3.10, 3.12 | `python -m pytest skills/product-strategy/tests -q` |
| `tools-tests` | ubuntu | 3.8, 3.12 | тесты `tools/` (появятся с P043 и P069) |
| `browser` (ручной, `workflow_dispatch`) | ubuntu | 3.12 | `npm ci` в `skills/site-qa-audit/scripts/node` + `npx playwright install --with-deps chromium`, затем `skills/site-qa-audit/tests/unit.sh` без `QA_SKIP_BROWSER` (наборы B/C, v140/v150/v170 browser) |

Дополнительно:
- **`.gitattributes`**: `*.sh text eol=lf` (и `*.py`, `*.md` — `text`), чтобы bash-скрипты на Windows не получали CRLF.
- **Установка pytest только в CI** (`pip install pytest`); скилы остаются на стандартной библиотеке (`CONVENTIONS.md:36`).
- **Закрепление действий по SHA** (`actions/checkout`, `actions/setup-python`, `actions/setup-node`) с комментарием версии.
- **Windows — поэтапно**: первые недели job-ы Windows с `continue-on-error: true` (не блокируют), после починки — обязательные.
- **Документация**: раздел «CI» в `CONVENTIONS.md` (что и как запускается, как повторить локально, правило «PR зелёный перед merge»); бейдж статуса в README (в составе P029). Отдельный `tests/CI.md` из реестра не нужен: корневого каталога `tests/` нет, а наборы описаны в `skills/*/tests/README.md`.
- Заполнить `skills/product-strategy/tests/README.md` (сейчас заготовка) перечнем наборов — по образцу трёх других скилов.

**Не входит:** живые прогоны с сетью, браузером пользователя, эмулятором или ключом TypeSafe (`--selftest` без `--heuristic`, `dry-run-todomvc.md`, живые проверки android); публикация релизов и Pages из CI; `claude plugin validate --strict` и линтер SKILL.md (P061); Dependabot и секрет-скан (P067); ночные проверки дрейфа (P061).

## Пользовательские сценарии
1. Как владелец, я хочу, чтобы каждый пуш в main проверялся на трёх ОС, чтобы регрессии при темпе до 113 коммитов в день ловились сразу.
   - Given workflow в main; When пушу коммит; Then запускаются validate и офлайн-наборы на ubuntu, macos, windows; итог виден на коммите и в бейдже README.
2. Как вкладчик, я хочу видеть результат проверок в PR, чтобы не просить владельца запускать тесты.
   - Given PR из форка; When он открыт; Then CI запускается с правами только на чтение, без секретов; статус в PR.
3. Как владелец, я хочу знать, работает ли скил на Windows, до заявления этого в README.
   - Given job-ы Windows с `continue-on-error`; When прогон завершён; Then видно, какие наборы падают; после исправлений статус становится обязательным, а заявление о Windows в README (P033) подтверждено.
4. Как владелец, я хочу вручную прогнать браузерные наборы, когда меняю `scripts/node`.
   - Given job `browser` с `workflow_dispatch`; When запускаю его из вкладки Actions; Then ставятся Node-зависимости и Chromium, проходят наборы B/C и browser-наборы; без Playwright они бы SKIP-нулись.
5. Как владелец, я хочу повторить CI локально одной командой на своей ОС.
   - Given раздел «CI» в `CONVENTIONS.md`; When выполняю перечисленные команды; Then получаю те же PASS/FAIL, что в CI.

## Требования
**Функциональные**
- F1. `.github/workflows/ci.yml` с job-ами из таблицы; матрица ОС × Python; `fail-fast: false`.
- F2. Минимальные версии Python в матрице — по коду каждого скила (3.8 для `tools/`, 3.9 для site/android/typesafe, 3.10 для product-strategy) и 3.12 как верхняя.
- F3. Ни одного обращения к сети из офлайн-job-ов, кроме установки pytest; переменные `TYPESAFE_API_KEY` и т. п. не задаются.
- F4. `QA_SKIP_BROWSER=1` в офлайн-job-ах site-qa-audit (`skills/site-qa-audit/tests/unit.sh:132`); наборы, которые сами печатают SKIP без инструментов, считаются пройденными.
- F5. `.gitattributes` с LF для `*.sh`.
- F6. Действия закреплены по SHA; `permissions: contents: read`; `concurrency` для отмены устаревших запусков.
- F7. Исправления, найденные первым прогоном, — по одному коммиту на причину, с записью в CHANGELOG затронутого скила (PATCH).

**Нефункциональные**
- Стоимость: только стандартные раннеры (бесплатны для публичного репозитория — P059.evidence); без кэшей, требующих платного хранилища.
- Скорость: ≤ 15 мин на ОС [оценка]; кэш pip и npm — по желанию.
- Безопасность: PR из форков без секретов; закреплённые SHA (защита цепочки поставки).
- Надёжность: тесты, зависящие от времени и сигналов (`signal.SIGKILL` под защитой, `data/repo-scan.json` → platform_compat), на Windows пропускаются по платформе, а не падают.

## Затрагиваемые части системы
- Новые: `.github/workflows/ci.yml`, `.gitattributes`.
- Запускаемые без изменений (если первый прогон не найдёт причин): `tools/validate.sh:5-6`, `tools/validate.ps1:4-5`, `skills/site-qa-audit/tests/unit.sh:131-152`, `skills/android-qa-audit/tests/unit.sh:4-7`, `:51-52` (поиск старого Python 3.9–3.11 для части проверок), `skills/typesafe-triage/scripts/test_*.py` (+ `conftest.py`), `skills/product-strategy/tests/test_*.py`.
- Вероятные места правок под Windows: `shared/scripts/find-python.sh:3-5`, `shared/scripts/find-python.ps1:3-9`, bash-наборы `skills/*/tests/*.sh`, пути в тестах.
- Документация: `CONVENTIONS.md:41-48` (разделы «Перед коммитом» и «Git» — добавить «CI»); `skills/product-strategy/tests/README.md:3` (заполнить); `README.md` — бейдж (P029).

## Аналитика
| Событие | Когда | Свойства | Источник |
|---|---|---|---|
| `ci_run` | каждый запуск workflow | job, os, python, conclusion, duration, sha | история GitHub Actions |
| `ci_red_main` | красный статус в main | job, os, причина (первая строка FAIL) | история Actions + ручная строка в журнале P043 |
| `platform_confirmed` | job ОС стал обязательным | os, дата | ручная строка в журнале P043 |

## Риски и меры
- Windows почти наверняка найдёт расхождения (P059.risks) → `continue-on-error` на старте, бюджет 1–3 дня на правки, критерий отказа ставки 3: не зелено к 2026-12-15 — убрать заявление о Windows из README.
- product-strategy на 3.9 упадёт → матрица 3.10/3.12 для него (F2).
- Тесты зависят от локальных инструментов (git, node, ffmpeg) → наборы уже печатают SKIP без них (`skills/site-qa-audit/tests/unit.sh:152`); git на раннерах есть.
- Медленный CI → `fail-fast: false`, отмена устаревших запусков, браузерные наборы — только вручную.
- Цепочка поставки → SHA, минимальные права.

## План выпуска
- Флаг: `continue-on-error` у Windows-job-ов (снимается после зелёного прогона). Ветка `feature/ci`.
- Этап 1 (cheap test реестра): workflow только с `validate` и `unit.sh` на трёх ОС — посчитать падения.
- Этап 2: pytest typesafe-triage и product-strategy; `.gitattributes`; исправления Linux/macOS.
- Этап 3: исправления Windows, снятие `continue-on-error`, обязательный статус для main (настройка защиты ветки — делает владелец).
- Этап 4: ручной job `browser`; раздел «CI» в `CONVENTIONS.md`; бейдж в README.
- A/B: неприменимо.
- Откат: удалить или отключить workflow (`git revert`); `.gitattributes` оставить.

## Оценка
| Часть | Дни |
|---|---|
| Инвентаризация офлайн-наборов, README тестов product-strategy | 0,5 |
| Workflow, матрица, SHA, `.gitattributes` | 0,5 |
| Первые прогоны и правки Linux/macOS | 0,5–1 |
| Правки Windows | 1–3 |
| Ручной job `browser` | 0,5 |
| `CONVENTIONS.md`, бейдж | 0,25 |
| **Итого** | **3,25–5,75** |

Согласовано с `effort_days` 3–7. Зависимостей нет. P059 разблокирует P061, P064, P066, P067, P068, P071, P072, P073 и даёт место для тестов P043 и P069.

## Открытые вопросы
1. Делать ли статус CI обязательным для прямых пушей в main (сейчас владелец сливает ветки сам) или только для PR?
2. Оставлять ли Python 3.8 для `tools/`, если скилы требуют ≥ 3.9 (проще поднять общий минимум до 3.9)?
3. Нужна ли macOS в матрице для каждого PR (самый медленный раннер) или достаточно push в main?
