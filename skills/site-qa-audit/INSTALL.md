# Установка и обновление site-qa-audit

Одна инструкция для macOS и Windows (Linux — как macOS). Скил ставится тремя способами: плагином из маркетплейса, клоном репозитория со ссылкой в `~/.claude/skills` или простой копией папки. После любого способа нужны Node-зависимости в `scripts/node` и браузеры Playwright, затем проверка `check_env`.

Репозиторий: https://github.com/OrionFLASH/claude-code-skills (папка `skills/site-qa-audit`), маркетплейс `claude-code-skills`.

Ниже `<SKILL_DIR>` — папка установленного скила (где лежит `SKILL.md`):

| Способ | macOS / Linux | Windows |
|--------|---------------|---------|
| Маркетплейс | `~/.claude/plugins/cache/claude-code-skills/site-qa-audit/<версия>/` (точный путь — `installPath` в `claude plugin list --json`) | `%USERPROFILE%\.claude\plugins\cache\claude-code-skills\site-qa-audit\<версия>\` |
| Клон + ссылка, копия | `~/.claude/skills/site-qa-audit/` | `%USERPROFILE%\.claude\skills\site-qa-audit\` |
| Только для проекта | `<проект>/.claude/skills/site-qa-audit/` | `<проект>\.claude\skills\site-qa-audit\` |

## Быстрый способ: промпт для Claude Code

Откройте Claude Code в любой папке и вставьте промпт целиком. Claude определит ОС, задаст вопросы с вариантами, покажет план, сделает резервные копии и поставит или обновит скил, затем запустит `check_env` и покажет итог.

### Промпт: установка

````text
Установи на этой машине скилл site-qa-audit из репозитория
https://github.com/OrionFLASH/claude-code-skills (папка skills/site-qa-audit).
Сначала прочитай skills/site-qa-audit/INSTALL.md из этого репозитория (разделы «Установка»,
«Проверка», «Папка результатов»), затем действуй по шагам ниже. Отвечай мне по-русски.

ПРАВИЛА
- Порядок: разведка (только чтение) -> вопросы -> план -> мое «да» -> действия -> проверка -> итог.
- Вопросы - через AskUserQuestion (нет инструмента - нумерованным списком), по 1-3 за раз,
  рекомендуемый вариант первым с пометкой (Recommended).
- Перед действиями покажи план: какие папки создашь, какие файлы изменишь, какие глобальные установки
  сделаешь (плагины, npm -g, браузеры Playwright). Глобальное - только после моего «да».
- Перед правкой существующего файла настроек (settings.json) сделай резервную копию рядом
  (settings.json.bak-ГГГГММДД). JSON правь аккуратно: прочитай, добавь только свои ключи, ничего
  не затирай; если блок env уже есть - допиши в него; результат проверь парсером JSON.
- Не печатай секреты: токены gh, значения переменных с паролями (QA_*), содержимое файлов входа.
  Про gh - только факт авторизации.
- Не ставь скилл двумя способами сразу (плагин и папка в ~/.claude/skills дают два одинаковых скилла).
  Существующую папку скилла не удаляй - переименуй в site-qa-audit.bak-ГГГГММДД.
- Если права Claude Code не дают что-то сделать, не обходи запрет: покажи команду, я выполню сам.

ШАГ 0. РАЗВЕДКА (только чтение)
1) ОС и оболочка; на Windows - версия PowerShell (5.1 или 7) и есть ли Git Bash.
2) Версии: claude, git, node (нужно >= 18), npm, npx, gh; рабочая команда Python 3 из
   python3 / python / py -3 (запусти --version у каждой).
3) Уже установлен ли site-qa-audit: ~/.claude/skills/site-qa-audit (папка, симлинк или junction -
   куда ведет), .claude/skills текущего проекта, плагин (claude plugin list). Версия - в
   .claude-plugin/plugin.json.
4) Подключен ли Playwright MCP (claude plugin list -> playwright, или claude mcp list).
5) Задана ли SITE_QA_OUTPUT_DIR (~/.claude/settings.json -> env или окружение) - только путь.
Покажи сводку таблицей.

ШАГ 1. ВОПРОСЫ
1) Способ: «Маркетплейс плагинов (Recommended)» / «Клон репозитория + tools/install.sh
   (macOS/Linux) или tools\install.ps1 (Windows): ссылка, правки подхватываются сразу» /
   «Копия папки без git».
2) Для кого: «Все проекты, ~/.claude (Recommended)» / «Только текущий проект, .claude».
3) Для клона - куда: «~/dev/claude-code-skills (Recommended)» / «Указать путь».
4) Папка результатов: «По умолчанию <папка запуска>/qa-runs (Recommended)» / «Одна папка для всех
   прогонов: задать SITE_QA_OUTPUT_DIR (укажу путь)».
5) Дополнительно (мультивыбор): «Браузеры WebKit и Firefox (Recommended)» / «playwright-cli для
   параллельных потоков (npm -g)» / «Ничего». Chromium ставится всегда. Если Playwright MCP не
   подключен - отдельный вопрос: он обязателен, поставить плагин playwright@claude-plugins-official?

ШАГ 2. ПЛАН. Покажи команды, папки и файлы (с путями резервных копий). Жди «да».

ШАГ 3. УСТАНОВКА
- Маркетплейс: claude plugin marketplace add OrionFLASH/claude-code-skills;
  claude plugin install site-qa-audit@claude-code-skills (для проекта: --scope project).
  <SKILL_DIR> = installPath из claude plugin list --json.
- Клон: git clone https://github.com/OrionFLASH/claude-code-skills.git <путь>; затем
  macOS/Linux: tools/install.sh site-qa-audit (для проекта:
  CLAUDE_SKILLS_DIR=<проект>/.claude/skills tools/install.sh site-qa-audit);
  Windows: powershell -ExecutionPolicy Bypass -File tools\install.ps1 site-qa-audit
  (для проекта - переменная CLAUDE_SKILLS_DIR перед запуском).
- Копия: скопируй skills/site-qa-audit в <корень .claude>/skills/site-qa-audit без node_modules
  и __pycache__.
- В <SKILL_DIR>/scripts/node: npm install (локально, не глобально), затем
  npx playwright install chromium (+ webkit firefox, если выбрано).
- Playwright MCP (если согласен): claude plugin install playwright@claude-plugins-official.
- playwright-cli (если выбрано): npm install -g @playwright/cli@latest.
- SITE_QA_OUTPUT_DIR (если выбрано): резервная копия settings.json, затем env.SITE_QA_OUTPUT_DIR =
  абсолютный путь (Windows: в JSON обратные слэши удваиваются или пишутся прямые); создай папку.
  Путь не должен вести в репозиторий скилов.

ШАГ 4. ПРОВЕРКА
- check_env из <SKILL_DIR>: macOS/Linux - bash scripts/check_env.sh; Windows -
  powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1 (или <python> scripts\check_env.py).
  Покажи таблицу и строку «Итог». FAIL в обязательном - предложи исправление (глобальное - после «да»).
- Если есть bash: bash tests/unit.sh из <SKILL_DIR> - покажи последнюю строку (PASS/FAIL).

ШАГ 5. ИТОГ
Таблица: что установлено и где (путь, версия, способ), что изменено (файлы и резервные копии),
результат check_env и тестов, что мне сделать вручную (начать новую сессию Claude Code - в этой скилл и
Playwright MCP не видны, вызов даст «Unknown skill»; продолжить здесь можно, прочитав <SKILL_DIR>/SKILL.md и
выполняя шаги по нему; gh auth login, если нужен), как откатить (вернуть .bak, удалить
ссылку или папку, либо claude plugin uninstall site-qa-audit@claude-code-skills).
````

### Промпт: обновление

````text
Обнови на этой машине скилл site-qa-audit до последней версии из репозитория
https://github.com/OrionFLASH/claude-code-skills (папка skills/site-qa-audit) и проверь результат.
Ориентируйся на skills/site-qa-audit/INSTALL.md (раздел «Обновление»). Отвечай мне по-русски.

ПРАВИЛА - те же, что при установке: разведка -> вопросы -> план -> мое «да» -> действия;
резервные копии (старую папку скилла - в site-qa-audit.bak-ГГГГММДД, settings.json -
в settings.json.bak-ГГГГММДД); секреты не печатать; глобальное - только после «да»;
папки результатов (qa-runs/, в том числе .site-context/ и .cache/) не трогать.

ШАГ 0. РАЗВЕДКА (только чтение)
1) ОС; где и как стоит скилл: плагин (claude plugin list --json -> installPath, version),
   симлинк или junction на клон (куда ведет), копия; нет ли дубля (плагин + папка).
2) Текущая версия - <SKILL_DIR>/.claude-plugin/plugin.json. Последняя: в клоне - git fetch, затем
   plugin.json и CHANGELOG.md в origin/main; для плагина - claude plugin marketplace update
   claude-code-skills и claude plugin list; иначе - CHANGELOG.md скилла на GitHub.
3) Для клона: git status (есть ли мои локальные правки) и текущая ветка.
Покажи сводку: текущая версия -> последняя, заголовки изменений из CHANGELOG.md между ними.

ШАГ 1. ВОПРОСЫ: обновить X -> Y? Способ - по разведке. Есть дубль - что оставить (плагин или папку)?
Есть локальные правки в клоне - «Отложить их (git stash) и обновить» / «Не обновлять».

ШАГ 2. ОБНОВЛЕНИЕ
- Плагин: claude plugin marketplace update claude-code-skills;
  claude plugin update site-qa-audit@claude-code-skills. Папка версии меняется - npm install
  в scripts/node НОВОЙ папки (installPath).
- Клон: git pull --ff-only; повторно tools/install.sh site-qa-audit (Windows -
  powershell -ExecutionPolicy Bypass -File tools\install.ps1 site-qa-audit), он проверит ссылку;
  npm install в scripts/node, если менялись package.json или package-lock.json.
- Копия: переименуй старую папку в site-qa-audit.bak-ГГГГММДД, скопируй новую (без node_modules
  и __pycache__), npm install в scripts/node.
- Если изменилась версия playwright в scripts/node/package.json - npx playwright install chromium
  (+ webkit firefox, если они стояли).

ШАГ 3. ПРОВЕРКА: версия в plugin.json совпадает с последней; check_env (как при установке);
bash tests/unit.sh, если есть bash.

ШАГ 4. ИТОГ: таблица (версия до и после, способ, дубли, check_env, тесты), что сделать вручную
(перезапустить Claude Code), как откатить (в клоне - git checkout site-qa-audit/v<старая версия>;
копия - вернуть .bak; плагин - переустановить нужную версию из клона или копией).
````

Нет доступа к GitHub из Claude Code — скачайте репозиторий ZIP-ом (Code → Download ZIP), распакуйте и добавьте в промпт строку «Репозиторий уже лежит в папке <путь>».

## Что понадобится

| Компонент | Обязательно | macOS | Windows | Проверка |
|-----------|-------------|-------|---------|----------|
| Claude Code | да | https://claude.com/claude-code | то же | `claude --version` |
| Node.js ≥ 18, npm, npx | да | https://nodejs.org (LTS) или `brew install node` | https://nodejs.org (LTS) | `node --version` |
| Python 3.8+ (только стандартная библиотека, `pip` не нужен) | да | обычно есть: `python3` | https://python.org, команда `python` или `py -3` | `python3 --version` / `python --version` |
| git | да | `xcode-select --install` или `brew install git` | https://git-scm.com (вместе с Git Bash) | `git --version` |
| gh (GitHub CLI) + вход | для репозиториев; `check_env` считает обязательным | `brew install gh` | https://cli.github.com | `gh auth status` |
| Playwright MCP | да | `/plugin install playwright@claude-plugins-official` | то же | `claude plugin list` |
| Браузеры Playwright | Chromium — да; WebKit, Firefox — желательно | `npx playwright install …` в `scripts/node` | то же | `check_env` (реальный запуск) |
| `@playwright/cli` | нет — нужен для параллельных потоков (до 4) | `npm install -g @playwright/cli@latest` | то же | `playwright-cli --version` |
| Claude in Chrome | нет — режим «текущий экран» | расширение «Claude» в Chrome + `claude --chrome` | то же | `check_env` |

Плагины-усилители (ux-audit, qa-skills и др.) необязательны — список в [README.md](README.md) и `references/plugins-map.md`.

## Установка

Выберите один способ. Не ставьте скил одновременно плагином и папкой в `~/.claude/skills` — будет два одинаковых скила.

### Способ 1. Маркетплейс (обычное использование)

В Claude Code:

```text
/plugin marketplace add OrionFLASH/claude-code-skills
/plugin install site-qa-audit@claude-code-skills
/plugin install playwright@claude-plugins-official
```

Или в терминале (любая ОС): `claude plugin marketplace add OrionFLASH/claude-code-skills`, затем `claude plugin install site-qa-audit@claude-code-skills` (только для текущего проекта — `--scope project`).

Node-зависимости и браузеры — в папке плагина (путь — `installPath` из `claude plugin list --json`):

```bash
# macOS / Linux
cd ~/.claude/plugins/cache/claude-code-skills/site-qa-audit/<версия>/scripts/node
npm install && npx playwright install chromium webkit firefox
```

```powershell
# Windows (PowerShell)
cd $HOME\.claude\plugins\cache\claude-code-skills\site-qa-audit\<версия>\scripts\node
npm install; npx playwright install chromium webkit firefox
```

Папка плагина зависит от версии: после каждого обновления `npm install` нужно повторить в новой папке.

### Способ 2. Клон репозитория + ссылка (разработка)

Правки в клоне подхватываются сразу, без переустановки. `tools/install.sh` создаёт симлинк, `tools/install.ps1` на Windows — junction (права администратора не нужны). Целевую папку можно переопределить переменной `CLAUDE_SKILLS_DIR` (например, `.claude/skills` проекта).

macOS / Linux:

```bash
git clone https://github.com/OrionFLASH/claude-code-skills.git ~/dev/claude-code-skills
cd ~/dev/claude-code-skills
tools/install.sh site-qa-audit                 # ~/.claude/skills/site-qa-audit -> клон
cd skills/site-qa-audit/scripts/node && npm install && npx playwright install chromium webkit firefox
```

Windows (PowerShell):

```powershell
git clone https://github.com/OrionFLASH/claude-code-skills.git $HOME\dev\claude-code-skills
cd $HOME\dev\claude-code-skills
powershell -ExecutionPolicy Bypass -File tools\install.ps1 site-qa-audit   # junction в %USERPROFILE%\.claude\skills
cd skills\site-qa-audit\scripts\node; npm install; npx playwright install chromium webkit firefox
```

Убрать ссылку: `tools/install.sh --uninstall site-qa-audit` (Windows: `… tools\install.ps1 -Uninstall site-qa-audit`).

### Способ 3. Ручное копирование (без git)

Скачайте репозиторий ZIP-ом (https://github.com/OrionFLASH/claude-code-skills → Code → Download ZIP), распакуйте и скопируйте папку `skills/site-qa-audit` (без `node_modules` и `__pycache__`, если они есть):

```bash
# macOS / Linux
mkdir -p ~/.claude/skills && cp -R <распаковано>/skills/site-qa-audit ~/.claude/skills/
cd ~/.claude/skills/site-qa-audit/scripts/node && npm install && npx playwright install chromium webkit firefox
```

```powershell
# Windows (PowerShell)
New-Item -ItemType Directory -Force $HOME\.claude\skills | Out-Null
Copy-Item -Recurse <распаковано>\skills\site-qa-audit $HOME\.claude\skills\site-qa-audit
cd $HOME\.claude\skills\site-qa-audit\scripts\node; npm install; npx playwright install chromium webkit firefox
```

После установки любым способом **начните новую сессию Claude Code**: скил и Playwright MCP появляются только в новой сессии. В той сессии, где скил поставили, `/site-qa-audit` отвечает «Unknown skill» — это не ошибка установки; продолжить там можно, попросив Claude прочитать `<SKILL_DIR>/SKILL.md` и идти по шагам (скрипты — по полным путям).

## Проверка

```bash
# macOS / Linux
bash <SKILL_DIR>/scripts/check_env.sh                       # полная проверка, браузеры запускаются по-настоящему
bash <SKILL_DIR>/scripts/check_env.sh --fast --no-browsers  # быстро
bash <SKILL_DIR>/tests/unit.sh                              # тесты скила без сети, 1–2 мин (последняя строка: unit: PASS N, FAIL 0)
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File <SKILL_DIR>\scripts\check_env.ps1
python <SKILL_DIR>\scripts\check_env.py --fast --no-browsers   # то же без обёртки (или py -3)
# тесты — в Git Bash: bash <SKILL_DIR>/tests/unit.sh
```

`check_env` печатает таблицу «компонент / версия / статус / как исправить» и строку «Итог: можно работать» или «нужно исправить: …» (код выхода 0 или 1). Затем в Claude Code: `/site-qa-audit` должен быть в списке команд, а просьба «протестируй https://example.com» — приводить к вопросу «Похоже, вы хотите протестировать … Запустить QA-аудит?».

## Обновление

**Текущая версия:**

```text
# macOS / Linux
grep '"version"' <SKILL_DIR>/.claude-plugin/plugin.json
# Windows (PowerShell)
Select-String '"version"' <SKILL_DIR>\.claude-plugin\plugin.json
```

Плагин — также `claude plugin list` (строка Version). Что изменилось — `CHANGELOG.md` скила (верхняя запись — последняя версия); теги релизов — `site-qa-audit/vX.Y.Z`.

| Установка | Как обновить |
|-----------|--------------|
| Маркетплейс | `/plugin marketplace update claude-code-skills`, затем `/plugin update site-qa-audit@claude-code-skills` (или `claude plugin marketplace update claude-code-skills` и `claude plugin update site-qa-audit@claude-code-skills`); перезапуск Claude Code; `npm install` в `scripts/node` **новой** папки версии |
| Клон + ссылка | `git pull` в клоне; `tools/install.sh site-qa-audit` (Windows: `install.ps1`) ещё раз — проверит ссылку; `npm install` в `scripts/node`, если менялись `package.json`/`package-lock.json` |
| Копия | скачать заново, старую папку переименовать в `site-qa-audit.bak-ГГГГММДД`, скопировать новую, `npm install` |

Если в `scripts/node/package.json` сменилась версия `playwright` — `npx playwright install chromium webkit firefox` ещё раз. После обновления — `check_env` и перезапуск Claude Code.

Результаты прогонов, память о сайтах (`qa-runs/.site-context/`) и кэш issues лежат в папке результатов, а не в папке скила, — обновление их не затрагивает.

**Откат:** клон — `git checkout site-qa-audit/v<версия>` (вернуться — `git checkout main`); копия — вернуть папку `.bak`; плагин — удалить (`claude plugin uninstall site-qa-audit@claude-code-skills`) и поставить нужную версию из клона способом 2.

## Папка результатов: `SITE_QA_OUTPUT_DIR`

По умолчанию результаты пишутся в `<папка запуска Claude Code>/qa-runs/<дата>-<хост>/`. Если папка запуска внутри git-репозитория, скил **сразу, до первой записи**, добавляет `qa-runs/` в `.gitignore` этого репозитория — без вопроса, если вы в запросе явно не разрешили класть результаты в репозиторий («коммить результаты»); уже закоммиченные результаты не удаляет, а спрашивает, убрать ли их из индекса (`git rm -r --cached`). Чтобы все прогоны складывались в одно место, задайте переменную `SITE_QA_OUTPUT_DIR` — результаты будут в `<SITE_QA_OUTPUT_DIR>/qa-runs/…`. Путь — абсолютный, не внутри репозитория скилов.

Надёжнее всего — блок `env` файла настроек Claude Code (сделайте резервную копию файла; если `env` уже есть — допишите строку в него):

macOS / Linux — `~/.claude/settings.json`:

```json
{
  "env": {
    "SITE_QA_OUTPUT_DIR": "/Users/<имя>/qa-results"
  }
}
```

Windows — `%USERPROFILE%\.claude\settings.json`; в JSON обратный слэш удваивается (или пишите прямые слэши `C:/Users/<имя>/qa-results`):

```json
{
  "env": {
    "SITE_QA_OUTPUT_DIR": "C:\\Users\\<имя>\\qa-results"
  }
}
```

Альтернатива — переменная окружения системы: macOS — `export SITE_QA_OUTPUT_DIR=…` в `~/.zshrc` (видна, только если Claude Code запущен из терминала); Windows — `setx SITE_QA_OUTPUT_DIR "C:\Users\<имя>\qa-results"` и новый терминал. После изменения перезапустите Claude Code; `check_env` покажет путь в строке `SITE_QA_OUTPUT_DIR`.

## Частые проблемы

| Симптом | Что сделать |
|---------|-------------|
| `/site-qa-audit` нет в списке, «Unknown skill» сразу после установки | скил виден только в новой сессии Claude Code; в текущей — попросить Claude прочитать `<SKILL_DIR>/SKILL.md` и работать по нему; иначе проверить, что есть `<SKILL_DIR>/SKILL.md`; для плагина — `claude plugin list` (включён ли) |
| Два одинаковых скила | стоит и плагин, и папка/ссылка в `~/.claude/skills` — оставить один способ |
| `check_env`: Playwright MCP «не подключён» | `/plugin install playwright@claude-plugins-official`, перезапуск |
| `Cannot find module 'playwright'` или FAIL у `playwright`, `lighthouse` | `npm install` в `<SKILL_DIR>/scripts/node`; для плагина — в папке текущей версии (после обновления путь другой) |
| Браузер не запускается | `npx playwright install chromium` в `scripts/node`; если Bash в песочнице — повторить вне её; Firefox на части macOS не стартует — `references/environment-notes.md` |
| `gh auth`: FAIL | `gh auth login`; для приватных репозиториев — `gh auth refresh -s repo` |
| Windows: `python3` открывает Microsoft Store | использовать `python` или `py -3`; отключить псевдонимы в «Параметры → Приложения → Псевдонимы выполнения приложений» |
| Windows: «выполнение сценариев отключено» | запускать `.ps1` через `powershell -ExecutionPolicy Bypass -File …` |
| Windows: `tests/unit.sh` не запускается | нужен bash: Git Bash или WSL |
| zsh: `= not found` в командах | разделители из `=` в zsh не работают — `references/environment-notes.md` → «Оболочка zsh» |
| Результаты появились в папке проекта | так работает значение по умолчанию (`<cwd>/qa-runs/`, сразу в `.gitignore` репозитория); задать `SITE_QA_OUTPUT_DIR` |
| Скил запустился, хотя вы не просили аудит | ответить «Нет, это другое» — скил ничего не создаст |

Подробности — [README.md](README.md) (параметры, примеры, ограничения) и [SKILL.md](SKILL.md) (порядок работы).
