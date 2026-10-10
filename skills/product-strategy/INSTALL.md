# Установка и обновление product-strategy

Скилл пишет подробную стратегию развития продукта по репозиторию, из которого запущен. Обязательны только Python 3.10+ и git. Остальное — усилители: Node.js, Playwright и Chromium для скриншотов и PDF, pptxgenjs для PPTX, gh для Issues, ключ TypeSafe для оценки предложений, а также скиллы-помощники для аудита, маркетинга и данных. Без них скилл всё равно работает: заменяет недостающее и честно пишет об этом в отчёте.

## Быстрый способ: промпты для Claude Code

Откройте Claude Code в любой папке и вставьте промпт целиком. Claude сначала проверит машину, потом задаст вопросы с вариантами, покажет план и только после вашего «да» начнёт ставить. В конце он запустит проверку `check_env.py` и покажет итог.

### Промпт: установка

````text
Установи на этой машине скилл product-strategy из репозитория
https://github.com/OrionFLASH/claude-code-skills (папка skills/product-strategy).
Сначала прочитай skills/product-strategy/INSTALL.md из этого репозитория (разделы «Установка»,
«Проверка», «Дополнительные модули»), затем действуй по шагам ниже. Отвечай мне по-русски.

ПРАВИЛА
- Порядок: разведка (только чтение) -> вопросы -> план -> мое «да» -> действия -> проверка -> итог.
- Вопросы - через AskUserQuestion, по 1-4 за раз, рекомендуемый вариант первым с пометкой (Recommended).
- Глобальные установки (плагины, brew, pip, npm -g) - только после моего «да». Перед правкой
  ~/.claude/settings.json - резервная копия settings.json.bak-ГГГГММДД, JSON проверь парсером.
- Не печатай секреты (токены gh, ключ TYPESAFE_API_KEY) - только факт, что они есть.
- Не ставь скилл двумя способами сразу (плагин и папка ~/.claude/skills/product-strategy дают два
  одинаковых скилла). Существующую папку не удаляй - перенеси в ~/.claude/backups/product-strategy.bak-ГГГГММДД.
- Если права Claude Code не дают что-то сделать, не обходи запрет: покажи команду, я выполню сам.

ШАГ 0. РАЗВЕДКА (только чтение)
1) ОС и оболочка. Версии: claude, git, python3 (нужно >= 3.10), node (>= 18), npm, gh (и авторизован ли).
2) Установлен ли уже product-strategy: claude plugin list, ~/.claude/skills/product-strategy.
3) Какие помощники уже есть (claude plugin list и ~/.claude/skills): superpowers, typesafe-triage, typesafe,
   marketing, product-management, data, cro-audit-and-test-kit, marketing-ideas-kit, churn-prevention-kit,
   frontend-design, playwright, seo, ux-audit, ui-ux-pro-max.
4) Задан ли TYPESAFE_API_KEY (только да/нет). Есть ли Chromium в кэше Playwright (~/Library/Caches/ms-playwright
   или ~/.cache/ms-playwright).
Покажи сводку таблицей.

ШАГ 1. ВОПРОСЫ
1) Способ: «Маркетплейс плагинов (Recommended)» / «Клон репозитория + tools/install.sh (правки подхватываются
   сразу)» / «Копия папки без git».
2) Для кого: «Все проекты, ~/.claude (Recommended)» / «Только текущий проект».
3) Дополнительные модули (мультивыбор, только недостающие): «Рекомендуемые: superpowers и typesafe-triage
   (Recommended)» / «Маркетинг и продукт: marketing, product-management, data» / «CRO, идеи, удержание:
   cro-audit-and-test-kit, marketing-ideas-kit, churn-prevention-kit» / «Ничего». Подробности и команды -
   раздел «Дополнительные модули» в INSTALL.md.
4) Node и браузер: «Проверить node и Chromium, недостающее - предложить (Recommended)» / «Не нужно: только
   HTML и XLSX».

ШАГ 2. ПЛАН. Покажи команды, папки и файлы (с путями резервных копий). Жди «да».

ШАГ 3. УСТАНОВКА
- Маркетплейс: claude plugin marketplace add OrionFLASH/claude-code-skills;
  claude plugin install product-strategy@claude-code-skills (для проекта: --scope project).
- Клон: git clone https://github.com/OrionFLASH/claude-code-skills.git ~/dev/claude-code-skills;
  ~/dev/claude-code-skills/tools/install.sh product-strategy (Windows: tools\install.ps1).
- Копия: skills/product-strategy -> ~/.claude/skills/product-strategy (без __pycache__).
- Выбранные модули - командами из раздела «Дополнительные модули».
- Node-модули скилл ставит сам в кэш пользователя (~/.cache/product-strategy/node, общий для прогонов; результат остаётся чистым) - глобально (npm -g) ничего не ставь.
  Если нет node - предложи brew install node (macOS) / https://nodejs.org (после моего «да»).

ШАГ 4. ПРОВЕРКА
- <SKILL_DIR> = python3 <путь к скиллу>/scripts/skill_dir.py (для плагина - installPath из claude plugin list --json).
- python3 <SKILL_DIR>/scripts/check_env.py - покажи таблицу и строку «Итог».
- Демо-сборка без сети: python3 <SKILL_DIR>/scripts/make_demo.py /tmp/ps-demo &&
  python3 <SKILL_DIR>/scripts/build_all.py /tmp/ps-demo --skip links - покажи таблицу шагов;
  если есть node: python3 <SKILL_DIR>/scripts/check_env.py --install-node и повтори build_all
  (появятся PPTX, PDF и smoke-тест страницы).

ШАГ 5. ИТОГ
Таблица: что установлено и где (путь, версия, способ), какие модули добавлены, результат check_env и демо-сборки,
что сделать мне вручную (новая сессия Claude Code - в текущей скилл не виден; gh auth login, если нужен;
ключ TypeSafe в env, если хочу оценку Jev), как откатить (claude plugin uninstall product-strategy@claude-code-skills
или удалить ссылку/папку, вернуть .bak).
````

### Промпт: обновление

````text
Обнови на этой машине скилл product-strategy до последней версии из репозитория
https://github.com/OrionFLASH/claude-code-skills (папка skills/product-strategy) и проверь результат.
Ориентируйся на skills/product-strategy/INSTALL.md (раздел «Обновление»). Отвечай мне по-русски.

1) Разведка (только чтение): способ установки (claude plugin list -> product-strategy, либо ~/.claude/skills/
   product-strategy - ссылка на клон или копия), текущая версия (.claude-plugin/plugin.json), последняя версия
   (CHANGELOG.md репозитория, теги product-strategy/v*). Если версия последняя - ничего не меняй, скажи об этом.
2) Покажи, что изменится (записи CHANGELOG между версиями), и жди моего «да».
3) Обнови:
   - плагин: claude plugin marketplace update claude-code-skills; claude plugin update product-strategy@claude-code-skills;
   - клон: git -C <клон> pull --ff-only (ссылка подхватит сама);
   - копия: старую папку - в ~/.claude/backups/product-strategy.bak-ГГГГММДД, новую - скопировать.
4) Проверка: python3 <SKILL_DIR>/scripts/check_env.py; демо-сборка (make_demo.py + build_all.py --skip links).
   Незавершённые прогоны (<OUT>/build/STATUS.md) обновление не трогает: их данные совместимы в пределах
   MAJOR-версии; при смене MAJOR - смотри CHANGELOG.
5) Итог: версия было -> стало, результат проверки, нужна ли новая сессия (да, если обновлялся плагин).
````

### Промпт: проверка режима «идея → концепция» после установки или обновления

````text
Проверь, что в установленном плагине product-strategy работает режим «идея → концепция» (версия 1.3.0 и выше).
Отвечай по-русски, ничего не ставь без моего «да».
1) Версия: claude plugin list -> product-strategy (нужна >= 1.3.0). Если старее - выполни промпт «обновление» выше.
2) В НОВОЙ сессии (или после /reload-plugins) проверь, что видны скилл product-strategy:product-concept и команда
   /product-strategy:concept. Не видны - покажи вывод `claude plugin validate <папка плагина>` и скажи, что исправить.
3) Демо без сети и без моих данных: python3 <SKILL_DIR>/scripts/make_concept_demo.py /tmp/pc-demo
   && python3 <SKILL_DIR>/scripts/build_all.py /tmp/pc-demo --skip links; покажи итоговую строку.
4) Покажи, как запускать: /product-strategy:concept <идея>, метки !concept / concept: / !идея.
````

### Промпт: отслеживание выполнения стратегии

````text
В этом репозитории уже есть стратегия, сделанная скиллом product-strategy. Проверь, что из неё выполнено.
Используй режим «Отслеживание» (skills product-strategy → references/tracking.md). Отвечай по-русски.
1) Найди прошлые стратегии (intake.py detect); если их несколько - спроси, какую контролировать (AskUserQuestion), по умолчанию самая свежая полная.
2) Запусти сверку (strategy_track.py check): git, issues и PR репозитория только чтением (gh должен быть авторизован; нет gh - скажи, как поставить, и работай по git и коду).
3) Неочевидные связи issue ↔ предложение задай вопросами (ask-list), ответы примени.
4) Покажи сводку: сделано, в работе, отстаёт, заблокировано, следующие шаги, работа вне стратегии, предлагаемые корректировки.
5) Спроси, обновлять ли текст стратегии (режим «пересмотреть») и заводить ли issues из черновиков. Без моего «да» ничего в GitHub не создавай.
6) Пересобери результат (build_all.py) и покажи пути. Не удаляй прежние файлы стратегии: старый текст сохраняется в tracking/<дата>/.
````

### Промпт: дополнительные модули

````text
Проверь и доустанови дополнительные модули, которые использует скилл product-strategy
(список и команды - skills/product-strategy/INSTALL.md, раздел «Дополнительные модули»). Отвечай по-русски.

1) Разведка (только чтение): python3 <SKILL_DIR>/scripts/check_env.py --plan (SKILL_DIR - через
   scripts/skill_dir.py или claude plugin list --json). Покажи три списка: «поставлю сам локально», «нужно
   согласие», «необязательно».
2) Одним вопросом AskUserQuestion (мультивыбор) спроси, что ставить из недостающего: группы
   «Рекомендуемые (superpowers, typesafe-triage)», «Маркетинг и продукт», «CRO, идеи, удержание»,
   «Дизайн и SEO (frontend-design, seo, ui-ux-pro-max, ux-audit)», «Python-пакеты certifi, openpyxl».
3) Ставь только выбранное, командами из INSTALL.md. Для модулей без официального маркетплейса (seo,
   ui-ux-pro-max, ux-audit) сначала найди их репозиторий, покажи мне ссылку и описание и жди «да».
   В режиме без pip (Work) Python-пакеты не предлагай.
4) Ключ TypeSafe не запрашивай и не печатай: скажи, как задать TYPESAFE_API_KEY самому.
5) Повтори check_env.py и покажи итог; напомни, что новые плагины видны в новой сессии.
````

## Что понадобится

| Компонент | Нужен для | Обязательно |
|---|---|---|
| Python 3.10+ | все скрипты (только стандартная библиотека) | да |
| git | история репозитория, ветка результата | да |
| Node.js 18+ и npm | скриншоты, smoke-тест страницы, PPTX, PDF | рекомендуется |
| Playwright + Chromium | аудит сайта, макеты в PNG, скриншоты конкурентов, PDF; ставится в кэш пользователя `~/.cache/product-strategy/node` командой `check_env.py --install-node` | рекомендуется |
| pptxgenjs | PPTX; ставится туда же | рекомендуется |
| gh (авторизованный) | Issues и PR репозитория, только чтение; для отслеживания выполнения стратегии — основной источник статусов (без него — только git и код) | рекомендуется |
| `TYPESAFE_API_KEY` | оценка предложений TypeSafe (Jev) отдельной колонкой | нет |
| certifi, openpyxl (pip) | сертификаты для проверки ссылок; доп. проверка XLSX в тестах | нет |

## Установка

### Способ 1. Маркетплейс (обычное использование)
```bash
claude plugin marketplace add OrionFLASH/claude-code-skills
claude plugin install product-strategy@claude-code-skills
```

### Способ 2. Клон репозитория + ссылка (разработка)
```bash
git clone https://github.com/OrionFLASH/claude-code-skills.git ~/dev/claude-code-skills
~/dev/claude-code-skills/tools/install.sh product-strategy        # Windows: tools\install.ps1 product-strategy
```
Создаются **две** ссылки: `~/.claude/skills/product-strategy` и `~/.claude/skills/product-concept` (режим идеи, с 1.3.0).

### Способ 3. Ручное копирование
Скопируйте `skills/product-strategy` в `~/.claude/skills/product-strategy` и `skills/product-strategy/product-concept` в `~/.claude/skills/product-concept` (режим идеи, с 1.3.0).

## Проверка
```bash
S=$(python3 ~/.claude/skills/product-strategy/scripts/skill_dir.py 2>/dev/null || ls -d ~/.claude/plugins/cache/claude-code-skills/product-strategy/* | tail -1)
python3 "$S/scripts/check_env.py"
python3 "$S/scripts/make_demo.py" /tmp/ps-demo && python3 "$S/scripts/build_all.py" /tmp/ps-demo --skip links
python3 "$S/scripts/check_env.py" --install-node && python3 "$S/scripts/build_all.py" /tmp/ps-demo --skip links
```
Ожидаемо: `check_env` — «Итог: можно работать»; `build_all` — шаги `OK` или `SKIP` с причиной, итог «всё собрано»; в `/tmp/ps-demo/deliverables/` — `index.html`, `strategy.xlsx` (и `strategy.pptx`, `strategy.pdf`, если поставлены Node-модули).

Режим идеи (с 1.3.0): `python3 "$S/scripts/make_concept_demo.py" /tmp/pc-demo && python3 "$S/scripts/build_all.py" /tmp/pc-demo --skip links` — ожидаемо тот же итог «всё собрано». Плагин даёт **два скилла**: `product-strategy` (стратегия по репозиторию) и `product-concept` (идея → концепция; команда `/product-strategy:concept`).

Только что установленный скилл виден в **новой** сессии Claude Code. В текущей можно прочитать `<SKILL_DIR>/SKILL.md` и идти по шагам вручную.

## Дополнительные модули

Скилл находит их сам (`check_env.py`) и применяет, если они есть. Если какого-то нет, эту фазу он делает своими средствами и отмечает это в отчёте.

| Модуль | Где помогает | Установка |
|---|---|---|
| superpowers | план и брейншторм (фаза 0) | `claude plugin install superpowers@claude-plugins-official` |
| typesafe-triage | выбор модели субагентов (`--batch`) | `claude plugin marketplace add OrionFLASH/claude-code-skills && claude plugin install typesafe-triage@claude-code-skills` |
| typesafe | основа оценки TypeSafe (Jev) | `claude plugin marketplace add typesafe-ai/skills && claude plugin install typesafe@typesafe-ai`; ключ — `TYPESAFE_API_KEY` |
| marketing, product-management, data | конкуренты, кампании, спеки, анализ данных | `claude plugin marketplace add anthropics/knowledge-work-plugins`, затем `claude plugin install marketing@knowledge-work-plugins` (и `product-management@…`, `data@…`) |
| cro-audit-and-test-kit, marketing-ideas-kit, churn-prevention-kit | CRO-аудит и A/B, идеи и окупаемость, удержание | `claude plugin install <имя>@anthropic-plugin-directory` |
| frontend-design | дизайн макетов | `claude plugin install frontend-design@claude-plugins-official` |
| playwright (MCP) | ручной просмотр в браузере | `claude plugin install playwright@claude-plugins-official` |
| site-qa-audit | глубокий аудит сайта перед стратегией | `claude plugin install site-qa-audit@claude-code-skills` |
| seo, ui-ux-pro-max, ux-audit | SEO/GEO, дизайн-решения, UX-аудит | внешние скиллы сообщества: найдите репозиторий, проверьте его и поставьте по его инструкции (промпт «дополнительные модули» выше делает это с подтверждением) |
| certifi, openpyxl | сертификаты для проверки ссылок, доп. проверка XLSX | `python3 -m pip install --user certifi openpyxl` (не в режиме без pip) |

## Обновление
```bash
claude plugin marketplace update claude-code-skills
claude plugin update product-strategy@claude-code-skills       # затем новая сессия или /reload-plugins
```
При установке клоном достаточно `git -C ~/dev/claude-code-skills pull --ff-only`. Если скил поставлен ссылками (`tools/install.sh`), после обновления клона выполните `tools/install.sh product-strategy` ещё раз: он создаст и вторую ссылку `~/.claude/skills/product-concept` (при установке плагином она не нужна — оба скилла приходят вместе). Обновление до 1.3.0 ничего не меняет в прежних прогонах: режим идеи — отдельный вход, данные совместимы. Изменения по версиям описаны в `CHANGELOG.md`, релизы помечены тегами `product-strategy/vX.Y.Z`.

## Переменные окружения
| Переменная | Что делает |
|---|---|
| `PRODUCT_STRATEGY_DIR` | путь к скиллу, если автоопределение (`skill_dir.py`) не подходит |
| `PS_NODE_DIR` | папка с `node_modules` (playwright, pptxgenjs) вместо кэша `~/.cache/product-strategy/node`; то же — `tools.node_dir` в run-config; папку печатает `check_env.py --print-node-dir` |
| `PS_SESSION_SKILLS` | скиллы, видимые в сессии (через запятую), если не передан `--session-skills`; обычно список запоминается в `<OUT>/build/session-skills.txt` |
| `TYPESAFE_API_KEY` | ключ TypeSafe для `typesafe_eval.py`; значение нигде не печатается |
| `PLAYWRIGHT_BROWSERS_PATH` | нестандартный кэш браузеров Playwright |
| `PS_STRATEGY_DIR` | папка стратегии (или папка со стратегиями) для поиска при отслеживании выполнения, если она вне репозитория |
| `PS_GH_BIN` | путь к `gh` (подмена в тестах) |

## Частые проблемы
Список проблем и решений — в `references/troubleshooting.md`. Самые частые:
- **«нет playwright» или «нет pptxgenjs» (код 3).** Выполните `check_env.py --install-node` (модули встанут в кэш пользователя; прежние `<OUT>/build/node` тоже работают).
- **Unknown skill.** Скилл установлен в текущей сессии; начните новую или выполните `/reload-plugins`.
- **`CERTIFICATE_VERIFY_FAILED` при проверке ссылок.** Поставьте `certifi` или запустите `check_links.py --offline`.
- **Папка прогона в репозитории не попала в коммит.** Корневое правило `.gitignore` вроде `build/` молча исключает `<OUT>/build`: `check_gitignore.py <OUT> --fix`.
- **Страница слишком тяжёлая (> 12 МБ) для пересылки или Artifact.** `build_all.py <OUT> --lite` (картинки отдельными файлами рядом, страница ≈ 3–4 МБ).
- **Нужно перенести готовую папку прогона.** `init_run.py <OUT> --relocate <NEW>`, затем `build_all.py <NEW>`.
- **На macOS нет `timeout`.** Используйте `gtimeout` (coreutils) или `subprocess` с таймаутом; скрипты скилла от этого не зависят.
