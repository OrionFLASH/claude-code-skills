# Обновление typesafe-triage

Для тех, кто уже поставил скилл ([INSTALL.md](INSTALL.md)) и хочет перейти на новую версию. Ключ, журнал, потолок расходов и настройки лежат вне папки скилла (`~/.claude/typesafe-triage/`, Windows: `%USERPROFILE%\.claude\typesafe-triage\`) и при обновлении сохраняются.

## Какая версия у вас сейчас

```text
# macOS / Linux
grep '"version"' ~/.claude/skills/typesafe-triage/.claude-plugin/plugin.json
# Windows (PowerShell)
Select-String '"version"' $HOME\.claude\skills\typesafe-triage\.claude-plugin\plugin.json
```

Для установки через маркетплейс версию показывает `/plugin` (или `claude plugin list`). Последняя версия — в [CHANGELOG.md](CHANGELOG.md).

## Что нового (коротко)

| Версия | Главное |
|---|---|
| 2.1.1 | таймаут хука 5 с, один повтор при ошибках 5xx/529, первая пауза после сбоя 1 мин вместо 5 |
| 2.1.0 | вторая ось — `effort` (low…max) вместе с моделью; `low` и `max` только с подтверждения; много источников автоопределения; свой хук в плагине (`hooks/hooks.json`); хук не дублирует заметку при двух установленных хуках |
| 2.0.0 | любые задачи (не только код); четыре уровня haiku/sonnet/opus/fable, haiku и fable только с подтверждения; запасная оценка по тексту без TypeSafe |

## Способ обновления (по тому, как ставили)

**Клонирование + `tools/install.sh` (macOS / Linux, симлинк):**

```bash
cd ~/dev/claude-code-skills && git pull
```

Симлинк подхватит новую версию сам.

**Клонирование + копирование (в том числе Windows):**

```powershell
cd $HOME\dev\claude-code-skills; git pull
Rename-Item $HOME\.claude\skills\typesafe-triage typesafe-triage.bak
Copy-Item -Recurse $HOME\dev\claude-code-skills\skills\typesafe-triage $HOME\.claude\skills\typesafe-triage
```

(macOS / Linux: `mv` для переименования и `cp -R` для копирования.) Старую копию `.bak` удалите после проверки.

**Маркетплейс:**

```text
/plugin marketplace update claude-code-skills
/plugin update typesafe-triage@claude-code-skills
```

Либо в терминале: `claude plugin update typesafe-triage@claude-code-skills`. Для применения нужен перезапуск Claude Code. Если версия не изменилась, значит, маркетплейс её ещё не увидел: повторите `marketplace update`.

**ZIP:** скачайте репозиторий заново, замените папку `skills/typesafe-triage` в `~/.claude/skills/` (старую переименуйте в `.bak`).

## Что проверить после обновления

1. **Хук не дублируется.** С версии 2.1.0 плагин приносит свой хук (`hooks/hooks.json`). Если скилл стоит через маркетплейс и при этом в `settings.json` остался ручной хук `typesafe_triage.py --hook`, выполнятся оба (заметка придёт одна, но лучше оставить один хук). У поставивших через клонирование/копирование хук остаётся ручным, менять его не нужно. Если хук в `settings.json` ведёт в папку плагина с номером версии в пути (`…/plugins/cache/…/2.0.0/…`), поправьте путь или удалите ручной хук.
2. **Правило для `effort` в `CLAUDE.md`** (нужно с 2.1.0, иначе я не буду ставить `effort` агентам — это требование инструмента Agent). Добавьте в раздел «Триаж модели» строку:

```markdown
- Заметка содержит и `effort` (low…max): при вызове `Agent` ставь `effort=<значение из заметки>`; `low` и `max` — только после подтверждения (один AskUserQuestion с моделью); нет «да» → medium / xhigh.
```

3. **Проверка:**

```text
# macOS / Linux
python3 ~/.claude/skills/typesafe-triage/scripts/typesafe_triage.py --check
# Windows (PowerShell)
python $HOME\.claude\skills\typesafe-triage\scripts\typesafe_triage.py --check
```

Должны быть «ключ: есть» и ответ сервиса. Затем отправьте любую задачу длиннее 40 символов: заметка должна содержать «уровень <модель>, effort <уровень>».
4. **Пауза.** Если до обновления сервис давал сбои и скилл на паузе: `… typesafe_triage.py --status`, затем `--resume`.

## Откат

Верните папку `typesafe-triage.bak` на место (или `git checkout typesafe-triage/v<версия>` в клоне и скопируйте заново). Для маркетплейса откат на конкретную версию не гарантирован: для управляемого отката ставьте через клонирование и тег `typesafe-triage/v<версия>`. Ключ и журнал откат не затрагивает.

## Обновление промптом (Claude Code сделает сам)

Вставьте в Claude Code на своей машине:

````text
Обнови на этой машине скилл typesafe-triage до последней версии из публичного репозитория
https://github.com/OrionFLASH/claude-code-skills (папка skills/typesafe-triage).
Прочитай UPDATE.md и CHANGELOG.md этого скилла (в репозитории) и действуй по ним.
Отвечай мне по-русски.

ПРАВИЛА
- Сначала разведка (только чтение), потом вопросы, затем действия.
- Ничего не удаляй: старую копию скилла переименуй в *.bak-ГГГГММДД. Перед правкой settings.json
  и CLAUDE.md сделай резервную копию рядом и покажи, что именно изменишь. JSON правь аккуратно
  (читай, дополняй, ничего не затирай, проверь парсером).
- Ключ TypeSafe не печатай и не проси присылать в чат; существующий ключ не трогай.
- Если права Claude Code не разрешают правку settings.json, не обходи запрет: покажи точный
  текст, я вставлю сам.

ШАГ 0. РАЗВЕДКА
1) Найди, где и как стоит скилл: ~/.claude/skills/typesafe-triage (симлинк или папка; для
   симлинка покажи, куда ведёт), .claude/skills проекта, плагин из маркетплейса
   (claude plugin list), клон репозитория (git rev-parse в целевой папке).
2) Узнай текущую версию (.claude-plugin/plugin.json) и последнюю в репозитории (CHANGELOG.md,
   теги typesafe-triage/v*). Если версии совпадают - скажи об этом и остановись.
3) Найди хук typesafe_triage.py --hook в settings.json (глобальном и проектном) и его путь;
   проверь, нет ли одновременно ручного хука и плагинного (дубль); найди строку про effort
   в CLAUDE.md (глобальном и проектном) и ключ TYPESAFE_API_KEY (только факт наличия).
4) Определи ОС и рабочую команду Python 3 (python3, python, py -3).
Покажи краткую сводку.

ШАГ 1. ВОПРОСЫ (мне; через AskUserQuestion, по 1-3 за раз)
1) Обновить с версии X до Y? Показать мне главное из CHANGELOG (коротко).
2) Способ обновления (предложи подходящий по результату разведки): git pull в клоне,
   замена копии, /plugin update из маркетплейса.
3) Если найден дубль хука (ручной + плагин) - какой оставить?
4) Добавить в CLAUDE.md (глобальный/проектный) строку про effort из UPDATE.md, если её нет?

ШАГ 2. ОБНОВЛЕНИЕ
- Выполни выбранный способ. Для замены копии: переименуй старую в *.bak-ГГГГММДД, скопируй
  новую папку скилла, без __pycache__. Для симлинка - git pull в клоне. Для маркетплейса -
  claude plugin marketplace update claude-code-skills, затем claude plugin update
  typesafe-triage@claude-code-skills (потребуется перезапуск Claude Code).
- Поправь путь хука в settings.json, только если он вёл в старую версионную папку плагина или
  если выбрано убрать дубль. Остальное в settings.json не трогай.
- Добавь строку про effort в CLAUDE.md, если я согласился.

ШАГ 3. ПРОВЕРКА
- Версия после обновления (plugin.json) = ожидаемой.
- Запусти: <python> <путь>/typesafe_triage.py --check (ключ не печатай). Если состояние на
  паузе - покажи --status и спроси, снять ли паузу (--resume).
- Проверь хук без сети: echo '{"prompt":"Подготовь план миграции базы данных с проверкой отката","cwd":".","session_id":"upd1"}' | <python> <путь>/typesafe_triage.py --hook
  В JSON должна быть заметка с «уровень … effort …».
- Итог: что обновлено (версии, пути), что изменено (с путями резервных копий), что осталось
  сделать вручную (перезапуск Claude Code), как откатить.
````
